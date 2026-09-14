#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
环境定位器 —— 自动探测 skill 路径与可用 Python 解释器

用途: 解决「文档里的路径是别人机器的」问题。
无论本 skill 被放在哪里、装在什么 Python 下, 此脚本都能算出正确路径。

用法:
  python env.py              # 人类可读输出
  python env.py --sh         # 输出 shell 变量 (可 eval)
  python env.py --bat        # 输出 Windows cmd 变量 (可 for /f)
  python env.py --json       # 输出 JSON
  python env.py --run <脚本> [参数...]   # 用探测到的 Python 运行本 skill 的脚本

示例 (bash):
  eval "$(python env.py --sh)"
  "$PY" "$SK/pipeline.py" ./图片 --out ./结果

示例 (Windows cmd):
  for /f "delims=" %i in ('python env.py --bat') do %i
  %PY% %SK%\\pipeline.py 图片目录 --out 结果

示例 (最省事, 无需管变量):
  python env.py --run pipeline.py ./图片 --out ./结果
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../image-toolkit/scripts
SKILL_ROOT = HERE.parent                         # .../image-toolkit
SKILL_NAME = SKILL_ROOT.name


# --------------------------------------------------------- Python 探测

def _looks_like_skill_python(exe):
    """判断一个 python 是否装了本 skill 的核心依赖"""
    if not exe or not os.path.isfile(exe):
        return False
    import subprocess
    try:
        rc = subprocess.call(
            [exe, "-c", "import PIL, openpyxl, docx, reportlab"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        return rc == 0
    except Exception:
        return False


def find_python(prefer_with_deps=True):
    """按优先级探测可用的 Python 解释器。

    参数:
      prefer_with_deps=True  —— 优先返回已装依赖的解释器 (运行 skill 时用)
      prefer_with_deps=False —— 只返回当前解释器, 不做跨环境搜索
                                (安装依赖时用, 避免装错地方)

    返回 (解释器路径, 说明)。
    """
    cands = []

    if not prefer_with_deps:
        # 安装场景: 就用当前解释器, 不跨环境找
        return (sys.executable, "当前运行的解释器")

    # 1) 当前解释器
    cands.append((sys.executable, "当前运行的解释器"))

    # 2) 宿主托管的 venv (若存在则优先使用, 省去用户手动装依赖)
    home = Path.home()
    for rel in [
        ".workbuddy/binaries/python/envs/default/Scripts/python.exe",   # win
        ".workbuddy/binaries/python/envs/default/bin/python",           # posix
        ".workbuddy/binaries/python/envs/default/bin/python3",
    ]:
        p = home / rel
        if p.is_file():
            cands.append((str(p), "宿主托管 venv"))
            break

    # 3) PATH
    for name in ("python", "python3", "py"):
        exe = shutil.which(name)
        if exe:
            cands.append((exe, f"PATH 中的 {name}"))

    # 去重并验证
    seen, good, fallback = set(), [], None
    for exe, desc in cands:
        try:
            key = str(Path(exe).resolve()).lower()
        except Exception:
            key = str(exe).lower()
        if key in seen:
            continue
        seen.add(key)
        has_deps = _looks_like_skill_python(exe)
        if has_deps:
            good.append((exe, desc + " [依赖齐全]"))
        elif fallback is None:
            fallback = (exe, desc + " [未验证依赖]")

    if good:
        return good[0]
    if fallback:
        return fallback
    return (sys.executable, "回退到当前解释器")


def find_skill_scripts():
    """定位 skill 的 scripts 目录。

    优先用本脚本所在目录; 若 skill 已被拷贝到别处,
    也支持通过环境变量 IMAGE_TOOLKIT_HOME 显式指定。
    """
    env_home = os.environ.get("IMAGE_TOOLKIT_HOME")
    if env_home:
        p = Path(env_home)
        cand = p / "scripts" if (p / "scripts").is_dir() else p
        if (cand / "pipeline.py").is_file():
            return cand, "环境变量 IMAGE_TOOLKIT_HOME"
    return HERE, "脚本自身所在位置"


def collect():
    py, py_desc = find_python()
    sk, sk_desc = find_skill_scripts()
    return {
        "skill_root": str(SKILL_ROOT),
        "skill_name": SKILL_NAME,
        "scripts": str(sk),
        "scripts_source": sk_desc,
        "python": py,
        "python_source": py_desc,
        "platform": sys.platform,
        "has_deps": _looks_like_skill_python(py),
    }


# --------------------------------------------------------------- 输出

def out_human(info):
    print("=" * 62)
    print("  image-toolkit 环境定位")
    print("=" * 62)
    print(f"  skill 根目录: {info['skill_root']}")
    print(f"  scripts 目录: {info['scripts']}")
    print(f"    (来源: {info['scripts_source']})")
    print(f"  Python:       {info['python']}")
    print(f"    (来源: {info['python_source']})")
    print(f"  依赖状态:     "
          f"{'齐全' if info['has_deps'] else '不齐全 —— 需先安装依赖'}")

    print("\n  shell 用法 (bash):")
    print('    eval "$(<本脚本> env.py --sh)"')
    print('    "$PY" "$SK/pipeline.py" ./图片 --out ./结果')

    print("\n  最省事用法 (无需管变量):")
    print('    python env.py --run pipeline.py ./图片 --out ./结果')

    if not info["has_deps"]:
        print("\n  \u26a0 依赖不齐全, 请先执行自检查看明细:")
        print(f'    "{info["python"]}" "{info["scripts"]}/selftest.py"')
    return 0


def out_sh(info):
    """输出可直接 eval 的 shell 变量

    注意: 在 Windows 的 Git Bash / MSYS 下, 反斜杠路径会导致命令解析失败,
    因此统一转成正斜杠形式 —— Windows 的 Python 同样接受正斜杠路径。
    """
    def q(s):
        s = str(s).replace("\\", "/")     # MSYS/Git Bash 友好
        return "'" + s.replace("'", "'\\''") + "'"
    print(f"SK={q(info['scripts'])}")
    print(f"PY={q(info['python'])}")
    print(f"SKILL_ROOT={q(info['skill_root'])}")
    return 0


def out_bat(info):
    """输出 Windows cmd 变量赋值"""
    print(f"set SK={info['scripts']}")
    print(f"set PY={info['python']}")
    print(f"set SKILL_ROOT={info['skill_root']}")
    return 0


def out_ps(info):
    """输出 PowerShell 变量赋值"""
    def q(s):
        return "'" + str(s).replace("'", "''") + "'"
    print(f"$SK = {q(info['scripts'])}")
    print(f"$PY = {q(info['python'])}")
    print(f"$SKILL_ROOT = {q(info['skill_root'])}")
    return 0


def out_json(info):
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def do_run(info, argv):
    """用探测到的 Python 运行 skill 内的脚本"""
    if not argv:
        print("用法: env.py --run <脚本名或路径> [参数...]", file=sys.stderr)
        return 2
    target = Path(argv[0])
    if not target.is_file():
        # 当作 skill 内的脚本名处理
        cand = Path(info["scripts"]) / argv[0]
        if not cand.suffix:
            cand = cand.with_suffix(".py")
        if not cand.is_file():
            print(f"未找到脚本: {argv[0]}", file=sys.stderr)
            print(f"已尝试: {target} 与 {cand}", file=sys.stderr)
            return 2
        target = cand

    import subprocess
    cmd = [info["python"], str(target)] + list(argv[1:])
    print(f"$ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser(
        description="自动探测 image-toolkit 的路径与 Python 解释器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python env.py                       # 查看探测结果
  eval "$(python env.py --sh)"        # bash: 设好 $SK 和 $PY
  python env.py --run pipeline.py ./图片 --out ./结果
""")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sh", action="store_true", help="输出 shell 变量 (bash)")
    g.add_argument("--bat", action="store_true", help="输出 cmd 变量")
    g.add_argument("--ps", action="store_true", help="输出 PowerShell 变量")
    g.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--run", nargs=argparse.REMAINDER,
                    help="用探测到的 Python 运行脚本")
    args = ap.parse_args()

    info = collect()

    if args.run is not None:
        return do_run(info, args.run)
    if args.sh:
        return out_sh(info)
    if args.bat:
        return out_bat(info)
    if args.ps:
        return out_ps(info)
    if args.json:
        return out_json(info)
    return out_human(info)


if __name__ == "__main__":
    sys.exit(main())
