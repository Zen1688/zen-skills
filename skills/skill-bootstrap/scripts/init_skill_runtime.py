#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skill 运行时脚手架 —— 一条命令给任意 Python skill 装上「依赖惰性引导」

做三件事:
  1. 把通用引擎 skill_bootstrap.py 复制到 <skill>/scripts/
  2. 生成 <skill>/scripts/deps.json (依赖分组 + 环境变量前缀)
  3. 在指定入口脚本的**模块顶部**插入挂载点

为什么必须插在模块顶部:
  挂载点要早于重依赖的导入。很多脚本会在模块级的 try 块里导入第三方库,
  失败即 sys.exit —— 此时若挂载点写在 main() 里, 根本来不及运行。

用法:
  # 1) 先预览要改什么 (不改文件)
  python init_skill_runtime.py ./skills/my-skill \
      --core "PIL=Pillow,openpyxl=openpyxl" \
      --group "ocr=rapidocr_onnxruntime=rapidocr-onnxruntime" \
      --entry pipeline.py:core,ocr \
      --entry convert.py:core \
      --dry-run

  # 2) 确认无误后去掉 --dry-run 执行

  # 不写 --entry 时会自动探测 scripts/ 下带 __main__ 守卫的脚本
  python init_skill_runtime.py ./skills/my-skill --core "PIL=Pillow"

幂等: 入口已含挂载点标记时会跳过, 不会重复插入。
"""
import argparse
import ast
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_SRC = HERE / "skill_bootstrap.py"

BEGIN = "# --- skill_bootstrap: 依赖惰性引导 (自动生成, 勿手改) ---"
END = "# --- /skill_bootstrap ---"

# 这些脚本不需要挂载点 (自身就是工具, 或被别的脚本导入时不承担引导职责)
SKIP_NAMES = {
    "skill_bootstrap.py",     # 引擎自身
    "init_skill_runtime.py",  # 本脚手架
    "env.py",                 # 环境定位器, 纯标准库
    "setup_env.py",           # 装包工具, 自己就是入口
    "deploy_offline.py",      # 离线部署器, 应显式指定解释器
    "common.py",              # 被导入的共享工具
}


# --------------------------------------------------------------- 解析

def parse_pkg_list(text):
    """'PIL=Pillow,openpyxl' -> [['PIL','Pillow'], ['openpyxl','openpyxl']]"""
    out = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            mod, pkg = part.split("=", 1)
            mod, pkg = mod.strip(), pkg.strip()
        else:
            mod = pkg = part
        if mod:
            out.append([mod, pkg or mod])
    return out


def parse_group(text):
    """'ocr=rapidocr_onnxruntime=rapidocr-onnxruntime' -> ('ocr', [...])"""
    if "=" not in text:
        raise ValueError(f"分组格式应为 NAME=mod=pkg[,mod=pkg...], 收到: {text}")
    name, rest = text.split("=", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"分组名不能为空: {text}")
    return name, parse_pkg_list(rest)


def to_env_prefix(skill_name):
    s = re.sub(r"[^0-9A-Za-z]+", "_", skill_name).strip("_").upper()
    if not s or s[0].isdigit():
        s = "SKILL_" + s
    return s


# --------------------------------------------------------------- 入口探测

def has_dunder_main(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            t = node.test
            if (isinstance(t, ast.Compare)
                    and isinstance(t.left, ast.Name)
                    and t.left.id == "__name__"
                    and any(isinstance(c, ast.Constant) and c.value == "__main__"
                            for c in t.comparators)):
                return True
    return False


def discover_entries(scripts_dir):
    """扫描 scripts/ 下带 __main__ 守卫、且不在跳过名单里的脚本"""
    out = []
    for p in sorted(scripts_dir.glob("*.py")):
        if p.name in SKIP_NAMES:
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if has_dunder_main(src):
            out.append(p.name)
    return out


# --------------------------------------------------------------- 插入挂载点

def hook_block(groups):
    gl = json.dumps(list(groups), ensure_ascii=False)
    return (
        f"{BEGIN}\n"
        f"import os as _os, sys as _sys\n"
        f"_sys.path.insert(0, _os.path.dirname(_os.path.realpath(__file__)))\n"
        f"try:\n"
        f"    import skill_bootstrap as _skill_bs\n"
        f"    _skill_bs.ensure_and_reexec(groups={gl})\n"
        f"except SystemExit:\n"
        f"    raise\n"
        f"except Exception as _skill_bs_err:\n"
        f'    print("[环境] 依赖引导跳过: %s" % (_skill_bs_err,), file=_sys.stderr)\n'
        f"{END}\n"
    )


def _insert_after_line(src):
    """算出「模块顶部」在源码里的行号 (0 基, 表示插在这一行之后)。

    顺序: 文档字符串 -> __future__ 导入。
    没有文档字符串时, 跳过开头的 shebang / 编码声明 / 注释块。
    """
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return len(lines)

    body = tree.body
    line = None
    i = 0
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        line = body[0].end_lineno
        i = 1
    while (i < len(body) and isinstance(body[i], ast.ImportFrom)
           and body[i].module == "__future__"):
        line = max(line or 0, body[i].end_lineno)
        i += 1

    if line is not None:
        return line

    # 无文档字符串: 保留开头的注释块 (shebang / coding)
    n = 0
    for ln in lines:
        s = ln.strip()
        if s == "" or s.startswith("#"):
            n += 1
        else:
            break
    return n


def patch_file(path, groups):
    """把挂载点插入入口脚本。返回 (状态, 说明)"""
    src = path.read_text(encoding="utf-8")
    if BEGIN in src:
        return "skip", "已含挂载点"

    at = _insert_after_line(src)
    lines = src.splitlines(keepends=True)
    # 补一个空行, 避免与后文黏在一起
    block = "\n" + hook_block(groups)
    new = "".join(lines[:at]) + block + "".join(lines[at:])
    path.write_text(new, encoding="utf-8")

    try:
        ast.parse(new)
    except SyntaxError as e:
        path.write_text(src, encoding="utf-8")     # 回滚, 不留坏文件
        return "error", f"插入后语法错误, 已还原: {e}"
    return "ok", f"挂载点已插入第 {at + 2} 行 (groups={','.join(groups)})"


# --------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(
        description="给 Python skill 装上依赖惰性引导",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python init_skill_runtime.py ./skills/my-skill \\
      --core "PIL=Pillow,openpyxl=openpyxl" \\
      --entry pipeline.py:core \\
      --dry-run
""")
    ap.add_argument("skill_dir", help="目标 skill 目录 (含 SKILL.md 的那一层)")
    ap.add_argument("--core", default="",
                    help="核心分组, 格式 mod=pkg[,mod=pkg]")
    ap.add_argument("--group", action="append", default=[],
                    help="额外分组, 格式 NAME=mod=pkg[,mod=pkg] (可重复)")
    ap.add_argument("--entry", action="append", default=[],
                    help="入口脚本, 格式 文件名[:分组,分组] (可重复; 省略则自动探测)")
    ap.add_argument("--env-prefix", help="环境变量前缀, 默认按 skill 名推导")
    ap.add_argument("--runtime-dir", help="运行时目录名, 默认 .<skill 名>")
    ap.add_argument("--engine-from", help="引擎源文件, 默认取本脚本同级")
    ap.add_argument("--no-copy-engine", action="store_true",
                    help="不复制引擎 (引擎已在目标 scripts/ 里时)")
    ap.add_argument("--force", action="store_true", help="覆盖已有 deps.json")
    ap.add_argument("--dry-run", action="store_true", help="只预览, 不改文件")
    args = ap.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"error: skill 目录不存在: {skill_dir}", file=sys.stderr)
        return 2
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        print(f"error: 未找到 scripts 目录: {scripts_dir}", file=sys.stderr)
        return 2

    skill_name = skill_dir.name
    env_prefix = args.env_prefix or to_env_prefix(skill_name)
    runtime_dir = args.runtime_dir or ("." + skill_name)

    # ---- 组装分组 ----
    groups = {}
    if args.core:
        groups["core"] = parse_pkg_list(args.core)
    for g in args.group:
        try:
            name, items = parse_group(g)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        groups[name] = items
    if not groups:
        print("error: 至少要有一个分组 (--core 或 --group)", file=sys.stderr)
        return 2
    default_groups = ["core"] if "core" in groups else [next(iter(groups))]

    # ---- 组装入口 ----
    entries = []
    if args.entry:
        for spec in args.entry:
            fname, _, gl = spec.partition(":")
            fname = fname.strip()
            glist = [x.strip() for x in gl.split(",") if x.strip()] or default_groups
            entries.append((fname, glist))
    else:
        for fname in discover_entries(scripts_dir):
            entries.append((fname, default_groups))

    if not entries:
        print("warn: 没有找到入口脚本, 只装引擎与配置", file=sys.stderr)

    print("=" * 62)
    print(f"  目标 skill:   {skill_name}")
    print(f"  目录:         {skill_dir}")
    print(f"  环境前缀:     {env_prefix}_*")
    print(f"  运行时目录:   ~/{runtime_dir}/venv")
    print("=" * 62)
    print("  依赖分组:")
    for name, items in groups.items():
        star = " *" if name in default_groups else "  "
        print(f"  {star} {name:12s} {', '.join(p for _, p in items)}")
    print("   (* = 默认分组)")
    print("  入口脚本:")
    for fname, glist in entries:
        print(f"      {fname:24s} groups={','.join(glist)}")
    if args.dry_run:
        print("\n[dry-run] 未改动任何文件")
        return 0
    print()

    # ---- 1) 复制引擎 ----
    engine_dst = scripts_dir / "skill_bootstrap.py"
    src = Path(args.engine_from).resolve() if args.engine_from else ENGINE_SRC
    if args.no_copy_engine:
        print("  [1/3] 跳过引擎复制 (--no-copy-engine)")
    else:
        if not src.is_file():
            print(f"error: 引擎源文件不存在: {src}", file=sys.stderr)
            return 2
        if engine_dst.exists() and engine_dst.read_bytes() == src.read_bytes():
            print(f"  [1/3] 引擎已是最新: {engine_dst.name}")
        else:
            shutil.copyfile(src, engine_dst)
            print(f"  [1/3] 引擎已复制: {engine_dst.name}")

    # ---- 2) 写 deps.json ----
    cfg = {
        "skill": skill_name,
        "env_prefix": env_prefix,
        "groups": groups,
        "default_groups": default_groups,
        "runtime_dir": runtime_dir,
        "extra_python_candidates": [],
    }
    cfg_dst = scripts_dir / "deps.json"
    if cfg_dst.exists() and not args.force:
        print(f"  [2/3] deps.json 已存在, 跳过 (--force 可覆盖)")
    else:
        cfg_dst.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"  [2/3] 配置已写入: deps.json")

    # ---- 3) 插入挂载点 ----
    print("  [3/3] 插入挂载点:")
    bad = 0
    for fname, glist in entries:
        p = scripts_dir / fname
        if not p.is_file():
            print(f"      ! 未找到 {fname}")
            bad += 1
            continue
        status, msg = patch_file(p, glist)
        mark = {"ok": "✓", "skip": "-", "error": "!"}[status]
        print(f"      {mark} {fname:24s} {msg}")
        if status == "error":
            bad += 1

    print()
    if bad:
        print(f"完成, 但有 {bad} 处需要注意。")
        return 1
    print("完成。下一步:")
    print(f'    python "{scripts_dir / "skill_bootstrap.py"}" --check')
    return 0


if __name__ == "__main__":
    sys.exit(main())
