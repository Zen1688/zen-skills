#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skill 运行时自举 —— 让 Python 写的 Agent Skill「装完即用」

本文件**只用标准库**, 并且可以在依赖完全缺失时安全导入。
它是通用引擎: 不含任何某个 skill 特有的内容, 因此可以原样复制到任意 skill。
skill 特有的配置放在同目录的 deps.json 里。

deps.json 结构:
{
  "skill":                   "my-skill",
  "env_prefix":              "MY_SKILL",
  "groups": {
    "core": [["PIL", "Pillow"], ["openpyxl", "openpyxl"]],
    "ocr":  [["rapidocr_onnxruntime", "rapidocr-onnxruntime"]]
  },
  "default_groups":          ["core"],
  "runtime_dir":             ".my-skill",
  "extra_python_candidates": []
}

工作机制:
  1. 用 importlib.util.find_spec 探测依赖 —— 只查规格、不导入模块,
     因此不会为了探测而把 onnxruntime 这类重模块加载起来 (省 2~3 秒)
  2. 依赖齐全 -> 立即返回, 额外开销约 10ms
  3. 缺依赖   -> 先看本机有没有「已经装好依赖」的解释器, 有就直接复用;
                没有才建独立 venv 装上, 再用新解释器重跑当前脚本
  4. 有本地 wheel 目录 -> 走 pip --no-index 纯离线安装, 全程不联网
  5. 无网又无本地包   -> 立即报错并打印补齐方式, 不挂起、不静默重试

安装位置 (按优先级自动回退):
  1. ${PREFIX}_RUNTIME_DIR/venv
  2. ~/<runtime_dir>/venv      (默认: 跨副本共享, 只装一次, 不污染宿主环境)
  3. <skill>/.runtime/venv     (用户目录不可写时)
  4. 当前解释器                (最后兜底, 直接 pip install)

环境变量 (PREFIX 取 deps.json 的 env_prefix):
  ${PREFIX}_NO_AUTO_INSTALL=1   完全禁用自动安装 (只检测并提示)
  ${PREFIX}_RUNTIME_DIR=<dir>   指定运行时目录 (内网可指向固定盘符)
  ${PREFIX}_FIND_LINKS=<dirs>   指定本地 wheel 目录 (多个用 os.pathsep 隔开)
  ${PREFIX}_MIRROR=<name>       tsinghua(默认) / aliyun / ustc / official
  ${PREFIX}_GROUPS=a,b          覆盖要处理的分组
  ${PREFIX}_QUIET=1             安静模式 (只输出错误与最终结果)

命令行:
  python skill_bootstrap.py                # 检查依赖, 缺了就自动补齐
  python skill_bootstrap.py --check        # 只检查, 不安装 (有缺失时退出码 1)
  python skill_bootstrap.py --install      # 强制重装
  python skill_bootstrap.py --json         # 以 JSON 输出现状
  python skill_bootstrap.py --groups core,ocr
"""
import argparse
import importlib.util as _ilu
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent            # <skill>/scripts
SKILL_ROOT = HERE.parent                          # <skill>
sys.path.insert(0, str(HERE))

# 引擎版本: 引擎文件在各 skill 之间应保持一致, 便于统一升级
ENGINE_VERSION = 1

# 这些参数只是「看看用法」, 不应该触发动辄上百 MB 的下载
HELP_FLAGS = ("-h", "--help", "--version")

DEVNULL = subprocess.DEVNULL

MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
    "ustc": "https://mirrors.ustc.edu.cn/pypi/simple/",
    "official": "https://pypi.org/simple",
}

_DEFAULT_CFG = {
    "skill": SKILL_ROOT.name,
    "env_prefix": "SKILL",
    "groups": {},
    "default_groups": [],
    "runtime_dir": ".skill-runtime",
    "extra_python_candidates": [],
}

_cfg = None


def cfg():
    """读取并缓存 deps.json (缺失或损坏时退回默认值, 不抛异常)"""
    global _cfg
    if _cfg is not None:
        return _cfg
    c = dict(_DEFAULT_CFG)
    p = HERE / "deps.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                c.update({k: v for k, v in data.items() if v is not None})
        except Exception as e:
            print(f"[环境] deps.json 解析失败, 使用默认配置: {e}", file=sys.stderr)
    _cfg = c
    return c


def env_name(suffix):
    """按 deps.json 的 env_prefix 拼出本 skill 的环境变量名"""
    return f"{cfg()['env_prefix']}_{suffix}"


def quiet():
    return os.environ.get(env_name("QUIET")) == "1"


def log(msg, err=False):
    # flush=True: 输出被管道重定向时 stdout 是块缓冲, 不立即 flush 会让
    # 「引导器消息」跑到子进程输出后面, 造成日志顺序误读
    if not quiet() or err:
        print(msg, file=sys.stderr if err else sys.stdout, flush=True)


# --------------------------------------------------------------- 依赖分组

def resolve(groups=None):
    """确定本次要处理的分组与模块清单。

    优先级: 显式参数 > 环境变量 ${PREFIX}_GROUPS > deps.json 的 default_groups

    返回 (分组名列表, [(模块名, pip 包名), ...])
    """
    c = cfg()
    table = c.get("groups") or {}

    want = list(groups) if groups else list(c.get("default_groups") or [])
    override = os.environ.get(env_name("GROUPS"))
    if override:
        want = [x.strip() for x in override.split(",") if x.strip()]

    mods, seen = [], set()
    for gname in want:
        for item in table.get(gname, []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                mod, pkg = item
            else:
                mod = pkg = item
            if mod in seen:
                continue
            seen.add(mod)
            mods.append((mod, pkg))
    return want, mods


def all_groups():
    return list((cfg().get("groups") or {}).keys())


# --------------------------------------------------------------- 探测

def has_module(name):
    """只查规格不导入 —— 毫秒级, 且不会触发重模块的加载"""
    try:
        return _ilu.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def missing(mods):
    """返回当前解释器缺失的模块名列表"""
    return [m for m, _ in mods if not has_module(m)]


def pkg_names(mods):
    return [pkg for _, pkg in mods]


def probe_python(exe, mods):
    """用子进程检查某个解释器是否具备指定模块。

    用 find_spec 而非真的 import —— 避免为了探测就加载 onnxruntime (省 2~3 秒)。
    """
    if not exe or not os.path.isfile(exe):
        return False
    code = ("import importlib.util as u, sys;"
            "sys.exit(0 if all(u.find_spec(m) for m in sys.argv[1:]) else 1)")
    try:
        return subprocess.call([exe, "-c", code, *mods],
                               stdout=DEVNULL, stderr=DEVNULL, timeout=60) == 0
    except Exception:
        return False


# --------------------------------------------------------------- 本地包目录

WHEEL_SUBDIRS = ("wheelhouse", "wheels", "vendor/wheelhouse")


def local_wheel_dirs():
    """可用的本地 wheel 目录 (离线安装用), 去重后按优先级返回"""
    out = []
    envv = os.environ.get(env_name("FIND_LINKS"))
    if envv:
        for part in envv.split(os.pathsep):
            if part.strip():
                p = Path(part).expanduser()
                if p.is_dir():
                    out.append(p)
    for base in (SKILL_ROOT, SKILL_ROOT.parent, Path.cwd()):
        for rel in WHEEL_SUBDIRS:
            p = base / rel
            if p.is_dir():
                out.append(p)

    seen, uniq = set(), []
    for p in out:
        try:
            key = str(p.resolve()).lower()
        except Exception:
            key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


# --------------------------------------------------------------- venv

def venv_python(venv_dir):
    """返回 venv 内的 python 可执行文件路径; 不存在返回 None"""
    v = Path(venv_dir)
    for rel in ("Scripts/python.exe",      # Windows
                "bin/python",              # POSIX
                "bin/python3"):
        p = v / rel
        if p.is_file():
            return str(p)
    return None


def runtime_venv_dirs():
    """运行时 venv 的候选位置, 按优先级返回 [(venv 路径, 说明)]"""
    out = []
    envd = os.environ.get(env_name("RUNTIME_DIR"))
    if envd:
        out.append((Path(envd).expanduser() / "venv",
                    f"环境变量 {env_name('RUNTIME_DIR')}"))
    out.append((Path.home() / cfg()["runtime_dir"] / "venv",
                "用户级运行时 venv"))
    out.append((SKILL_ROOT / ".runtime" / "venv",
                "skill 本地 .runtime/venv"))
    return out


def runtime_active():
    """返回当前实际存在的运行时 venv 信息; 没有则 None"""
    for vdir, desc in runtime_venv_dirs():
        py = venv_python(vdir)
        if py:
            return {"venv": str(vdir), "python": py, "source": desc}
    return None


def _writable(path):
    """判断路径是否可写, 且不产生任何副作用 (绝不创建目录)。

    向上找最近的已存在祖先, 只对它做可写性判断 ——
    否则 --check 这类只读操作会留下空目录。
    """
    p = Path(path)
    while not p.exists():
        parent = p.parent
        if parent == p:
            return False
        p = parent
    return os.access(str(p), os.W_OK)


def writable_runtime_venvs():
    """可写的运行时 venv 候选 —— 只判断, 不创建"""
    return [(Path(vdir), desc) for vdir, desc in runtime_venv_dirs()
            if _writable(Path(vdir).parent)]


def create_venv(venv_dir):
    """建 venv 并确认其中的 pip 可用"""
    venv_dir = Path(venv_dir)
    try:
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.call([sys.executable, "-m", "venv", str(venv_dir)])
    except Exception as e:
        log(f"  ! 创建 venv 失败: {e}", err=True)
        return False
    if rc != 0:
        log(f"  ! venv 创建返回码 {rc} (可能缺少 ensurepip)", err=True)
        return False
    py = venv_python(venv_dir)
    if not py:
        log("  ! venv 内未找到 python 可执行文件", err=True)
        return False
    try:
        rc = subprocess.call([py, "-m", "pip", "--version"],
                             stdout=DEVNULL, stderr=DEVNULL)
    except Exception:
        rc = 1
    if rc != 0:
        log("  ! venv 内 pip 不可用", err=True)
        return False
    return True


def pip_install(py, pkgs, find_links=None, mirror=None):
    """执行 pip install; 有本地包目录则纯离线安装"""
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check"]
    if find_links:
        cmd.append("--no-index")
        for d in find_links:
            cmd += ["--find-links", str(d)]
    elif mirror:
        cmd += ["-i", mirror]
        host = mirror.split("//")[-1].split("/")[0]
        if "pypi.org" not in host:
            cmd += ["--trusted-host", host]
    cmd += list(pkgs)

    log(f"  $ {' '.join(cmd)}")
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        log(f"  ! pip 执行失败: {e}", err=True)
        return 1


# --------------------------------------------------------------- 解释器候选

def _sibling_env():
    """如果同目录存在 env.py (环境定位器), 复用它定义的候选来源。

    这样「候选解释器」只有一处定义, 不会出现两套逻辑漂移。
    没有也不影响 —— 引擎自身有内置候选。
    """
    try:
        import env as _e
        if hasattr(_e, "iter_candidates"):
            return _e
    except Exception:
        pass
    return None


def iter_candidates():
    """候选解释器 [(路径, 说明)], 去重后按优先级返回"""
    cands = [(sys.executable, "当前运行的解释器")]

    # 1) 运行时 venv (引导器创建, 或用户用环境变量指定)
    for vdir, desc in runtime_venv_dirs():
        py = venv_python(vdir)
        if py:
            cands.append((py, desc))

    # 2) deps.json 显式指定的额外解释器
    for rel in cfg().get("extra_python_candidates") or []:
        p = Path(os.path.expanduser(str(rel)))
        if p.is_file():
            cands.append((str(p), "deps.json 指定"))

    # 3) 同目录 env.py 的候选, 或 PATH
    e = _sibling_env()
    if e is not None:
        try:
            cands.extend(list(e.iter_candidates())[1:])
        except Exception:
            pass
    else:
        for name in ("python", "python3", "py"):
            exe = shutil.which(name)
            if exe:
                cands.append((exe, f"PATH 中的 {name}"))

    seen, out = set(), []
    for exe, desc in cands:
        try:
            key = str(Path(exe).resolve()).lower()
        except Exception:
            key = str(exe).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((exe, desc))
    return out


# --------------------------------------------------------------- 主流程

def ensure(groups=None, auto=True, force=False):
    """确保依赖就绪。

    返回 dict:
      action   ok | switched | installed | disabled | failed
      switch   是否需要换解释器 (True 时调用方应重跑自身)
      python   应使用的解释器
      missing  缺失模块
      runtime  实际使用的运行时 venv (若有)
      detail   人类可读说明
    """
    want, mods = resolve(groups)
    miss = missing(mods)
    if not miss and not force:
        return dict(action="ok", switch=False, python=sys.executable,
                    missing=[], runtime=None, detail="依赖齐全", groups=want)

    # ---- 1) 先看有没有现成已装好的解释器 (避免重复安装) ----
    cur = os.path.normcase(os.path.abspath(sys.executable))
    mod_names = [m for m, _ in mods]
    for exe, desc in iter_candidates():
        try:
            if os.path.normcase(os.path.abspath(exe)) == cur:
                continue
        except Exception:
            pass
        if probe_python(exe, mod_names):
            return dict(action="switched", switch=True, python=exe,
                        missing=miss, runtime=None, groups=want,
                        detail=f"复用已就绪的解释器: {desc}")

    # ---- 2) 允许自动安装吗 ----
    if not auto or os.environ.get(env_name("NO_AUTO_INSTALL")) == "1":
        return dict(action="disabled", switch=False, python=sys.executable,
                    missing=miss, runtime=None, groups=want,
                    detail="自动安装已关闭")
    if os.environ.get(env_name("BOOTSTRAPPED")) == "1":
        return dict(action="failed", switch=False, python=sys.executable,
                    missing=miss, runtime=None, groups=want,
                    detail="已切换过一次解释器, 仍未找到依赖")

    find_links = local_wheel_dirs()
    mirror_name = os.environ.get(env_name("MIRROR"), "tsinghua")
    mirror = MIRRORS.get(mirror_name, MIRRORS["tsinghua"])
    if find_links:
        log(f"  使用本地包目录 (纯离线): {', '.join(str(d) for d in find_links)}")
    else:
        log(f"  下载源: {mirror_name}  ({mirror})")

    # ---- 3) 选安装位置: 优先独立 venv (不污染宿主环境) ----
    target_py, runtime, need_pkgs = None, None, pkg_names(mods)
    for vdir, desc in writable_runtime_venvs():
        py = venv_python(vdir)
        if not py:
            log(f"  创建运行时环境: {vdir}  ({desc})")
            if not create_venv(vdir):
                continue                      # 位置建不出来才换下一个
            py = venv_python(vdir)
        else:
            log(f"  使用已有运行时环境: {vdir}")
        target_py, runtime = py, str(vdir)
        break

    # 所有位置都建不出 venv -> 兜底装进当前解释器
    if target_py is None:
        target_py = sys.executable
        need_pkgs = [pkg for m, pkg in mods if m in miss]
        log(f"  无可用独立环境, 回退到当前解释器: {sys.executable}")

    # ---- 4) 安装 ----
    # 装不上不再换位置重试: 失败原因 (缺包 / 无网 / 平台不符) 与安装位置无关,
    # 重复尝试只会把同一份错误打印三遍。
    log(f"  安装 {len(need_pkgs)} 个依赖包 ...")
    rc = pip_install(target_py, need_pkgs, find_links, mirror)
    if rc == 0:
        return dict(action="installed",
                    switch=(os.path.normcase(os.path.abspath(target_py)) != cur),
                    python=target_py, missing=miss, runtime=runtime, groups=want,
                    detail=(f"已安装到 {runtime}" if runtime
                            else "已安装到当前解释器"))

    return dict(action="failed", switch=False, python=sys.executable,
                missing=miss, runtime=None, groups=want,
                detail=f"自动安装失败 (退出码 {rc})")


# --------------------------------------------------------------- 给脚本用的入口

def _guidance(r):
    name = cfg()["skill"]
    _, mods = resolve(r.get("groups"))
    pkgs = " ".join(pkg_names(mods)) or "<包名>"
    miss = ", ".join(r["missing"]) or "(未知)"
    P = cfg()["env_prefix"]
    print("", file=sys.stderr)
    print("-" * 62, file=sys.stderr)
    print(f"  {name} 依赖未就绪", file=sys.stderr)
    print("-" * 62, file=sys.stderr)
    print(f"  缺失模块: {miss}", file=sys.stderr)
    print(f"  原因:     {r['detail']}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  三种补齐方式 (任选其一):", file=sys.stderr)
    print("", file=sys.stderr)
    print("  1) 自动 (需联网)", file=sys.stderr)
    print(f'       python "{HERE / "skill_bootstrap.py"}"', file=sys.stderr)
    print("", file=sys.stderr)
    print("  2) 离线 (内网 / 无网络)", file=sys.stderr)
    print("       把 wheel 放到 <skill>/wheelhouse/ 后重跑, 或指定目录:", file=sys.stderr)
    print(f"       {P}_FIND_LINKS=/path/to/wheels \\", file=sys.stderr)
    print(f'         python "{HERE / "skill_bootstrap.py"}"', file=sys.stderr)
    print("", file=sys.stderr)
    print("  3) 手动", file=sys.stderr)
    print(f"       pip install {pkgs}", file=sys.stderr)
    print("-" * 62, file=sys.stderr)


def ensure_and_reexec(groups=None, on_fail="exit"):
    """各入口脚本在**模块顶部**调用的挂载点。

    必须早于重依赖的导入 —— 若某个模块级 try 块在导入失败时就 sys.exit,
    挂载点放在 main() 里根本来不及运行。

    - 依赖齐全:   立即返回, 什么都不做
    - 需要换解释器: 用目标解释器重跑当前脚本, 然后退出
    - 装进当前解释器: 直接继续
    - 装不上:     打印指引; on_fail="exit" 时以退出码 3 结束
    """
    if os.environ.get(env_name("BOOTSTRAPPED")) == "1":
        return                                    # 已经切过一次, 防递归
    if any(a in HELP_FLAGS for a in sys.argv[1:]):
        return                                    # 只是看用法, 不触发安装

    try:
        r = ensure(groups=groups)
    except Exception as e:                        # 引导器自身故障不应阻断技能
        log(f"[环境] 依赖自检异常, 跳过: {e}", err=True)
        return

    if r["action"] == "ok":
        return
    if r["action"] in ("switched", "installed"):
        log(f"[环境] {r['detail']}")

    if r["switch"]:
        try:
            script = Path(sys.argv[0]).resolve()
        except Exception:
            script = None
        if not script or not script.is_file():
            return                                # 无法可靠重跑, 交给调用方
        env = dict(os.environ)
        env[env_name("BOOTSTRAPPED")] = "1"
        cmd = [r["python"], str(script)] + list(sys.argv[1:])
        log(f"[环境] 切换解释器重跑: {r['python']}")
        try:
            sys.exit(subprocess.call(cmd, env=env))
        except KeyboardInterrupt:
            sys.exit(130)

    if r["action"] == "installed":
        return                                    # 已装进当前解释器, 继续跑

    _guidance(r)
    if on_fail == "exit":
        sys.exit(3)


# --------------------------------------------------------------- 命令行

def report(r):
    want, mods = resolve(r.get("groups"))
    print("=" * 62)
    print(f"  {cfg()['skill']} 依赖引导  (引擎 v{ENGINE_VERSION})")
    print("=" * 62)
    print(f"  当前解释器: {sys.executable}")
    print(f"  分组:       {', '.join(want) if want else '(未配置)'}")
    print(f"  需要依赖:   {len(mods)} 个")
    print(f"  缺失模块:   {', '.join(r['missing']) if r['missing'] else '(无)'}")

    wd = local_wheel_dirs()
    print(f"  本地包目录: {', '.join(str(d) for d in wd) if wd else '(无)'}")
    print("  运行时位置: " + (", ".join(str(v) for v, _ in writable_runtime_venvs())
                              or "(无可写位置)"))
    print(f"  结果:       {r['action']}  —— {r['detail']}")
    return r


def main():
    ap = argparse.ArgumentParser(
        description=f"{SKILL_ROOT.name} 依赖引导器 (首次调用自动补齐依赖)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python skill_bootstrap.py                    # 缺依赖就自动装
  python skill_bootstrap.py --check            # 只检查
  python skill_bootstrap.py --groups core,ocr  # 指定分组
  MY_SKILL_FIND_LINKS=./wheelhouse python skill_bootstrap.py   # 纯离线
""")
    ap.add_argument("--check", action="store_true", help="只检查, 不安装")
    ap.add_argument("--install", action="store_true", help="强制安装")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--groups", help="逗号分隔的分组名, 默认取 deps.json")
    ap.add_argument("--list-groups", action="store_true", help="列出已配置的分组")
    args = ap.parse_args()

    if args.list_groups:
        g = cfg().get("groups") or {}
        for name, items in g.items():
            mark = " *" if name in (cfg().get("default_groups") or []) else "  "
            print(f"{mark} {name:12s} {len(items)} 个包")
        print("   (* = 默认分组)")
        return 0

    groups = [x.strip() for x in args.groups.split(",")] if args.groups else None
    r = ensure(groups=groups, auto=not args.check, force=args.install)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        report(r)

    if r["action"] in ("ok", "installed", "switched"):
        return 0
    if r["action"] == "disabled":
        return 1
    return 3


if __name__ == "__main__":
    sys.exit(main())
