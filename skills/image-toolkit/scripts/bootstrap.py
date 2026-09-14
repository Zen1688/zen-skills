#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
依赖引导器 —— 首次调用时自动补齐 Python 依赖, 让技能「装完即用」

本模块只依赖标准库, 并且可以在依赖缺失的情况下安全导入。

工作机制:
  1. 用 importlib.util.find_spec 探测依赖 —— 只查规格、不导入模块,
     因此不会为了探测而把 onnxruntime 加载起来 (那要 2~3 秒)
  2. 依赖齐全 -> 立即返回, 额外开销可忽略
  3. 缺依赖   -> 先看有没有别的解释器已经装好 (运行时 venv / 宿主环境);
                都没有就建一个独立 venv 装上, 再用新解释器重跑当前脚本
  4. 有本地 wheel 目录 -> 走 --no-index 纯离线安装;
     无网又无本地包 -> 明确报错并给指引, 不挂起、不静默重试

安装位置 (按优先级自动回退):
  1. $IMAGE_TOOLKIT_RUNTIME_DIR/venv
  2. ~/.image-toolkit/venv       (默认: 跨副本共享, 只装一次, 不污染宿主环境)
  3. <skill>/.runtime/venv       (用户目录不可写时)
  4. 当前解释器                   (最后兜底, 直接 pip install)

环境变量:
  IMAGE_TOOLKIT_NO_AUTO_INSTALL=1   完全禁用自动安装 (只检测并提示)
  IMAGE_TOOLKIT_RUNTIME_DIR=<dir>   指定运行时目录
  IMAGE_TOOLKIT_FIND_LINKS=<dirs>   指定本地 wheel 目录 (离线; 多个用系统分隔符隔开)
  IMAGE_TOOLKIT_MIRROR=aliyun       换镜像源 (tsinghua/aliyun/ustc/official)
  IMAGE_TOOLKIT_SKIP_OCR=1          只装核心依赖, 不装 OCR 引擎
  IMAGE_TOOLKIT_QUIET=1             安静模式 (只输出错误与最终结果)

用法:
  python bootstrap.py             # 检查依赖, 缺了就自动补齐
  python bootstrap.py --check     # 只检查, 不安装 (有缺失时退出码 1)
  python bootstrap.py --install   # 强制安装
  python bootstrap.py --json      # 以 JSON 输出现状
"""
import argparse
import importlib.util as _ilu
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent            # .../image-toolkit/scripts
SKILL_ROOT = HERE.parent                          # .../image-toolkit
sys.path.insert(0, str(HERE))

# ------------------------------------------------------------ 依赖清单

# 模块名 -> pip 包名
CORE = [
    ("PIL", "Pillow"),
    ("openpyxl", "openpyxl"),
    ("docx", "python-docx"),
    ("reportlab", "reportlab"),
    ("numpy", "numpy"),
]
OCR = [
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime"),
]

MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
    "ustc": "https://mirrors.ustc.edu.cn/pypi/simple/",
    "official": "https://pypi.org/simple",
}

ENV_NO_AUTO = "IMAGE_TOOLKIT_NO_AUTO_INSTALL"
ENV_BOOTSTRAPPED = "IMAGE_TOOLKIT_BOOTSTRAPPED"
ENV_FIND_LINKS = "IMAGE_TOOLKIT_FIND_LINKS"
ENV_MIRROR = "IMAGE_TOOLKIT_MIRROR"
ENV_SKIP_OCR = "IMAGE_TOOLKIT_SKIP_OCR"
ENV_QUIET = "IMAGE_TOOLKIT_QUIET"

# 这些参数只是「看看用法」, 不应该触发动辄上百 MB 的下载
_HELP_FLAGS = ("-h", "--help", "--version", "--list-engines")

DEVNULL = subprocess.DEVNULL


def quiet():
    return os.environ.get(ENV_QUIET) == "1"


def log(msg, err=False):
    # flush=True: 输出被管道重定向时 stdout 是块缓冲,
    # 不立即 flush 会让「引导器消息」跑到子进程输出后面, 造成日志误读
    if not quiet() or err:
        print(msg, file=sys.stderr if err else sys.stdout, flush=True)


# ------------------------------------------------------------ 探测

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


# ------------------------------------------------------------ 本地包目录

def local_wheel_dirs():
    """可用的本地 wheel 目录 (离线安装用), 按优先级返回"""
    out = []
    envv = os.environ.get(ENV_FIND_LINKS)
    if envv:
        for part in envv.split(os.pathsep):
            if not part.strip():
                continue
            p = Path(part).expanduser()
            if p.is_dir():
                out.append(p)
    for base in (SKILL_ROOT, SKILL_ROOT.parent, Path.cwd()):
        for rel in ("wheelhouse", "wheels", "vendor/wheelhouse"):
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


# ------------------------------------------------------------ venv 与安装

def _env_mod():
    """导入 env.py (环境定位模块); 失败时返回 None"""
    try:
        import env as _e
        return _e
    except Exception:
        return None


def venv_python(venv_dir):
    e = _env_mod()
    if e is not None:
        return e.venv_python(venv_dir)
    v = Path(venv_dir)
    for rel in ("Scripts/python.exe", "bin/python", "bin/python3"):
        p = v / rel
        if p.is_file():
            return str(p)
    return None


def _writable(path):
    """判断路径是否可写, 且不产生任何副作用 (不创建目录)。

    向上找最近的已存在祖先, 只对它做可写性判断。
    """
    p = Path(path)
    while not p.exists():
        parent = p.parent
        if parent == p:
            return False
        p = parent
    return os.access(str(p), os.W_OK)


def writable_runtime_venvs():
    """可写的运行时 venv 候选 [(venv 路径, 说明)] —— 只判断, 不创建"""
    e = _env_mod()
    if e is not None:
        dirs = e.runtime_venv_dirs()
    else:
        dirs = [(Path.home() / ".image-toolkit" / "venv", "用户级运行时 venv"),
                (SKILL_ROOT / ".runtime" / "venv", "skill 本地运行时 venv")]

    return [(Path(vdir), desc) for vdir, desc in dirs
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
    """执行 pip install。有本地包目录则纯离线安装。"""
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


# ------------------------------------------------------------ 主流程

def ensure(need_ocr=True, auto=True, force=False):
    """确保依赖就绪。

    返回 dict:
      action   ok | switched | installed | disabled | failed
      switch   是否需要换解释器 (True 时调用方应重跑自身)
      python   应使用的解释器
      missing  缺失模块
      runtime  实际使用的运行时 venv (若有)
      detail   人类可读说明
    """
    mods = list(CORE)
    if need_ocr and not os.environ.get(ENV_SKIP_OCR) == "1":
        mods += list(OCR)

    miss = missing(mods)
    if not miss and not force:
        return dict(action="ok", switch=False, python=sys.executable,
                    missing=[], runtime=None, detail="依赖齐全")

    # ---- 1) 先看有没有现成已装好的解释器 (避免重复安装) ----
    cur = os.path.normcase(os.path.abspath(sys.executable))
    for exe, desc in _candidates():
        try:
            if os.path.normcase(os.path.abspath(exe)) == cur:
                continue
        except Exception:
            pass
        if _probe(exe, [m for m, _ in mods]):
            return dict(action="switched", switch=True, python=exe,
                        missing=miss, runtime=None,
                        detail=f"复用已就绪的解释器: {desc}")

    # ---- 2) 允许自动安装吗 ----
    if not auto or os.environ.get(ENV_NO_AUTO) == "1":
        return dict(action="disabled", switch=False, python=sys.executable,
                    missing=miss, runtime=None, detail="自动安装已关闭")
    if os.environ.get(ENV_BOOTSTRAPPED) == "1":
        return dict(action="failed", switch=False, python=sys.executable,
                    missing=miss, runtime=None,
                    detail="已切换过一次解释器, 仍未找到依赖")

    find_links = local_wheel_dirs()
    mirror = MIRRORS.get(os.environ.get(ENV_MIRROR, "tsinghua"),
                         MIRRORS["tsinghua"])
    if find_links:
        log(f"  使用本地包目录 (纯离线): {', '.join(str(d) for d in find_links)}")
    else:
        log(f"  下载源: {os.environ.get(ENV_MIRROR, 'tsinghua')}  ({mirror})")

    # ---- 3) 选安装位置: 优先独立 venv (不污染宿主环境) ----
    target_py, runtime = None, None
    need_pkgs = pkg_names(mods)
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
    # 装不上不再换位置重试: 失败原因 (缺包/无网/平台不符) 与安装位置无关,
    # 重复尝试只会把同一份错误打印三遍。
    log(f"  安装 {len(need_pkgs)} 个依赖包 ...")
    rc = pip_install(target_py, need_pkgs, find_links, mirror)
    if rc == 0:
        return dict(action="installed", switch=(target_py != sys.executable),
                    python=target_py, missing=miss, runtime=runtime,
                    detail=(f"已安装到 {runtime}" if runtime
                            else "已安装到当前解释器"))

    return dict(action="failed", switch=False, python=sys.executable,
                missing=miss, runtime=None, detail=f"自动安装失败 (退出码 {rc})")


def _candidates():
    """其他可选解释器 [(路径, 说明)]"""
    e = _env_mod()
    if e is not None:
        try:
            return list(e.iter_candidates())[1:]      # 跳过当前解释器
        except Exception:
            pass
    return []


def _probe(exe, mods):
    e = _env_mod()
    if e is not None:
        return e.probe_python(exe, tuple(mods))
    if not exe or not os.path.isfile(exe):
        return False
    code = ("import importlib.util as u, sys;"
            "sys.exit(0 if all(u.find_spec(m) for m in sys.argv[1:]) else 1)")
    try:
        return subprocess.call([exe, "-c", code, *mods],
                               stdout=DEVNULL, stderr=DEVNULL, timeout=60) == 0
    except Exception:
        return False


# ------------------------------------------------------------ 给脚本用的入口

def _guidance(r):
    miss = ", ".join(r["missing"]) or "(未知)"
    print("", file=sys.stderr)
    print("-" * 62, file=sys.stderr)
    print("  image-toolkit 依赖未就绪", file=sys.stderr)
    print("-" * 62, file=sys.stderr)
    print(f"  缺失模块: {miss}", file=sys.stderr)
    print(f"  原因:     {r['detail']}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  三种补齐方式 (任选其一):", file=sys.stderr)
    print("", file=sys.stderr)
    print("  1) 自动 (需联网)", file=sys.stderr)
    print(f'       python "{HERE / "bootstrap.py"}"', file=sys.stderr)
    print("", file=sys.stderr)
    print("  2) 离线 (内网 / 无网络)", file=sys.stderr)
    print("       把 wheel 放到 <skill>/wheelhouse/ 后重跑, 或指定目录:", file=sys.stderr)
    print("       IMAGE_TOOLKIT_FIND_LINKS=/path/to/wheels \\", file=sys.stderr)
    print(f'         python "{HERE / "bootstrap.py"}"', file=sys.stderr)
    print("", file=sys.stderr)
    print("  3) 手动", file=sys.stderr)
    print("       pip install Pillow openpyxl python-docx reportlab numpy \\",
          file=sys.stderr)
    print("                   rapidocr-onnxruntime", file=sys.stderr)
    print("-" * 62, file=sys.stderr)


def ensure_and_reexec(need_ocr=True, on_fail="exit"):
    """各脚本 main() 的首行调用点。

    - 依赖齐全: 立即返回, 什么都不做
    - 需要换解释器: 用目标解释器重跑当前脚本, 然后退出
    - 装上但不需要换: 直接继续
    - 装不上: 打印指引; on_fail="exit" 时以退出码 3 结束
    """
    if os.environ.get(ENV_BOOTSTRAPPED) == "1":
        return                                    # 已经切过一次, 防递归
    if any(a in _HELP_FLAGS for a in sys.argv[1:]):
        return                                    # 只是看用法, 不触发安装

    try:
        r = ensure(need_ocr=need_ocr)
    except Exception as e:                        # 引导器自身故障不应阻断技能
        log(f"[环境] 依赖自检异常, 跳过: {e}", err=True)
        return

    if r["action"] == "ok":
        return

    if r["action"] == "switched":
        log(f"[环境] {r['detail']}")
    elif r["action"] == "installed":
        log(f"[环境] {r['detail']}")

    if r["switch"]:
        argv = sys.argv
        try:
            script = Path(argv[0]).resolve()
        except Exception:
            script = None
        if not script or not script.is_file():
            return                                # 无法可靠重跑, 交给调用方
        env = dict(os.environ)
        env[ENV_BOOTSTRAPPED] = "1"
        cmd = [r["python"], str(script)] + list(argv[1:])
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


# ------------------------------------------------------------ 命令行

def report(r):
    print("=" * 62)
    print("  image-toolkit 依赖引导")
    print("=" * 62)
    print(f"  当前解释器: {sys.executable}")
    print(f"  需要依赖:   {len(CORE) + len(OCR)} 个 "
          f"(核心 {len(CORE)} + OCR {len(OCR)})")
    miss = missing(list(CORE) + list(OCR))
    print(f"  缺失模块:   {', '.join(miss) if miss else '(无)'}")

    wd = local_wheel_dirs()
    print(f"  本地包目录: {', '.join(str(d) for d in wd) if wd else '(无)'}")
    print(f"  运行时位置: " + (", ".join(str(v) for v, _ in writable_runtime_venvs())
                               or "(无可写位置)"))
    print(f"  结果:       {r['action']}  —— {r['detail']}")
    return r


def main():
    ap = argparse.ArgumentParser(
        description="image-toolkit 依赖引导器 (首次调用自动补齐依赖)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python bootstrap.py             # 缺依赖就自动装
  python bootstrap.py --check     # 只检查
  IMAGE_TOOLKIT_FIND_LINKS=./wheelhouse python bootstrap.py   # 纯离线
""")
    ap.add_argument("--check", action="store_true", help="只检查, 不安装")
    ap.add_argument("--install", action="store_true", help="强制安装")
    ap.add_argument("--no-ocr", action="store_true", help="不处理 OCR 引擎")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    need_ocr = not args.no_ocr
    if args.check:
        r = ensure(need_ocr=need_ocr, auto=False)
    else:
        r = ensure(need_ocr=need_ocr, force=args.install)

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
