#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
离线部署自动化脚本 —— 一键完成「打包 / 安装 / 校验」

两种模式, 分别在有网机器和内网机器上运行:

  ┌─ 有网机器 ────────────────────────────────────────────┐
  │  python deploy_offline.py pack                        │
  │    → 下载全部依赖到 bundle/packages/                   │
  │    → 写入 bundle/manifest.json (平台指纹)              │
  │    → 打包成 image-toolkit-offline.zip                  │
  └───────────────────────────────────────────────────────┘
              ↓ U盘 / 内网共享 搬运
  ┌─ 内网机器 ────────────────────────────────────────────┐
  │  python deploy_offline.py install --bundle <解压目录>  │
  │    → 校验平台指纹是否匹配                              │
  │    → pip install --no-index (纯离线)                   │
  │    → 自动安装 Linux 系统库 (若有权限)                  │
  │    → 端到端冒烟测试, 确认真的能用                      │
  └───────────────────────────────────────────────────────┘

平台差异已在脚本内自动分派, 无需人工判断。详见 --help 或
references/offline-deploy.md。
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 让本脚本的 print 与子进程输出严格按时间顺序交错,
# 避免 "子进程输出跑到父进程前面" 造成日志误读
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

MANIFEST_NAME = "manifest.json"
BUNDLE_VERSION = 1

# --------------------------------------------------------------- 依赖清单

# 核心依赖 (必需)
CORE_PKGS = [
    "Pillow", "openpyxl", "python-docx", "pypdf", "reportlab", "numpy",
]

# OCR 依赖 (可选, --no-ocr 时跳过; 跳过则失去识别与分类能力)
OCR_PKGS = [
    "rapidocr-onnxruntime", "pytesseract",
]

MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
    "ustc": "https://mirrors.ustc.edu.cn/pypi/simple/",
    "official": "https://pypi.org/simple",
}

# Linux 系统库依赖 (opencv / 字体)。apt 包名 -> 用途
LINUX_SYS_DEPS = {
    "libgl1": "opencv 图形库",
    "libglib2.0-0": "opencv 基础库",
    "fonts-wqy-microhei": "中文字体 (PDF/Word 输出必需)",
}


# ============================================================ 平台指纹

def platform_tag():
    """生成平台指纹字符串, 用于跨平台迁移校验。

    形如 win_amd64_cp313 / linux_x86_64_cp311 / macos_arm64_cp312
    wheel 的平台与 ABI 标记直接由此决定, 因此必须精确匹配。
    """
    sysname = platform.system().lower()
    if sysname == "windows":
        os_part = "win"
    elif sysname == "darwin":
        os_part = "macos"
    else:
        os_part = "linux"

    machine = platform.machine().lower()
    arch = {
        "amd64": "amd64", "x86_64": "x86_64", "x86": "i686",
        "arm64": "arm64", "aarch64": "aarch64",
        "armv7l": "armv7l", "loongarch64": "loongarch64",
        "mips64": "mips64", "sw_64": "sw_64",
    }.get(machine, machine)

    # CPython ABI 标记 (cp311 等); PyPy 等用实现名
    impl = platform.python_implementation().lower()
    if impl == "cpython":
        py_part = "cp%d%d" % sys.version_info[:2]
    else:
        py_part = "%s%d%d" % (impl, *sys.version_info[:2])

    # 解释器位数: 32/64 位 wheel 不通用
    bits = 64 if sys.maxsize > 2**32 else 32

    return f"{os_part}_{arch}_{py_part}_{bits}bit"


def platform_info():
    """收集完整平台信息, 写入 manifest 供安装侧校验"""
    from common import platform_report
    pr = platform_report()
    return {
        "tag": platform_tag(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_impl": platform.python_implementation(),
        "python_exe": sys.executable,
        "bits": 64 if sys.maxsize > 2**32 else 32,
        "cjk_fonts": [f[1] for f in pr["cjk_fonts"]],
    }


# ============================================================ 通用工具

def run(cmd, **kw):
    """执行命令并回显"""
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.call(cmd, **kw)


def run_capture(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def step(n, total, title):
    print(f"\n{'=' * 62}")
    print(f"  [{n}/{total}] {title}")
    print("=" * 62)


def ok(msg):
    print(f"  \u2713 {msg}")


def warn(msg):
    print(f"  ! {msg}")


def err(msg):
    print(f"  \u2717 {msg}", file=sys.stderr)


def ask_yes(question, default=False):
    """交互确认。非交互环境返回 default"""
    if not sys.stdin.isatty():
        return default
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        ans = input(f"  {question}{suffix}").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans in ("y", "yes", "是")


# ============================================================ pack 模式

def do_pack(args):
    t0 = time.time()
    bundle = Path(args.bundle).resolve()
    pkg_dir = bundle / "packages"
    skill_dst = bundle / "image-toolkit"

    total = 5
    print("=" * 62)
    print("  离线部署 —— 打包模式 (在有网机器上运行)")
    print("=" * 62)

    # ---- 1. 环境检查 ----
    step(1, total, "检查打包环境")
    pi = platform_info()
    print(f"  平台:   {pi['system']} {pi['release']} / {pi['machine']}")
    print(f"  Python: {pi['python_version']} ({pi['python_impl']}, {pi['bits']}bit)")
    print(f"  指纹:   {pi['tag']}")
    ok("平台指纹已生成 (安装侧将据此校验兼容性)")

    # ---- 2. 目标平台校验 (跨平台打包警告) ----
    step(2, total, "校验目标平台")
    if args.for_platform and args.for_platform != pi["tag"]:
        err(f"指定目标平台 {args.for_platform} 与当前 {pi['tag']} 不一致")
        print("\n  跨平台打包无法直接完成, 原因:")
        print("    pip download 只会下载【当前平台】的 wheel。")
        print("    要为目标平台准备依赖, 必须在该平台机器上运行 pack。")
        print("\n  可行的替代方案:")
        print("    1. 在目标平台的联网机器上执行 pack")
        print("    2. 用 pip download --platform/<--abi> 手动指定 (需自行处理依赖树)")
        print("    3. 目标机若无 Python, 考虑整体拷贝 venv (需同路径)")
        return 1
    ok(f"目标平台与打包平台一致: {pi['tag']}")

    # ---- 3. 下载依赖 ----
    step(3, total, "下载依赖包")
    if pkg_dir.exists() and args.clean:
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True, exist_ok=True)

    pkgs = list(CORE_PKGS)
    if not args.no_ocr:
        pkgs += OCR_PKGS
    else:
        warn("--no-ocr: 跳过 OCR 依赖, 部署后将失去识别与分类能力")

    mirror = MIRRORS.get(args.mirror, MIRRORS["tsinghua"])
    cmd = [sys.executable, "-m", "pip", "download", "-d", str(pkg_dir),
           "-i", mirror]
    host = mirror.split("//")[-1].split("/")[0]
    if "pypi.org" not in host:
        cmd += ["--trusted-host", host]
    cmd += pkgs

    print(f"  镜像: {args.mirror}  ({mirror})")
    rc = run(cmd)
    if rc != 0:
        err(f"下载失败 (退出码 {rc})")
        print("\n  可尝试换镜像: --mirror aliyun / --mirror ustc / --mirror official")
        return rc

    wheels = sorted(pkg_dir.glob("*.whl")) + sorted(pkg_dir.glob("*.tar.gz"))
    size = sum(f.stat().st_size for f in wheels)
    from common import human_size
    ok(f"下载完成: {len(wheels)} 个包, 共 {human_size(size)}")

    if not wheels:
        err("包目录为空, 下载异常")
        return 1

    # ---- 4. 复制 skill 本体 ----
    step(4, total, "复制 skill 本体")
    skill_src = HERE.parent
    if skill_dst.exists():
        shutil.rmtree(skill_dst)
    shutil.copytree(skill_src, skill_dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  ".pytest_cache"))
    n_files = sum(1 for _ in skill_dst.rglob("*") if _.is_file())
    ok(f"已复制 {n_files} 个文件 -> {skill_dst.name}/")

    # ---- 5. 写 manifest 并打包 ----
    step(5, total, "写入清单并打包")
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "builder": pi,
        "packages": [f.name for f in wheels],
        "package_count": len(wheels),
        "package_bytes": size,
        "with_ocr": not args.no_ocr,
        "install_targets": CORE_PKGS + ([] if args.no_ocr else OCR_PKGS),
    }
    (bundle / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"{MANIFEST_NAME} 已写入")

    # 可选: 打包成 zip 便于搬运
    zip_path = None
    if not args.no_zip:
        zip_base = str(bundle) + "-offline"
        zip_path = shutil.make_archive(zip_base, "zip", root_dir=bundle)
        zb = Path(zip_path)
        from common import human_size as hs
        ok(f"已打包: {zb.name}  ({hs(zb.stat().st_size)})")

    print(f"\n{'=' * 62}")
    print("  打包完成")
    print("=" * 62)
    print(f"  产物目录: {bundle}")
    if zip_path:
        print(f"  可搬运包: {zip_path}")
    print(f"  耗时: {time.time() - t0:.1f}s")
    print("\n  下一步: 把上述内容拷到内网机器, 执行")
    print(f"    python deploy_offline.py install --bundle <解压目录>")
    return 0


# ============================================================ install 模式

def check_manifest(bundle, force=False):
    """校验 manifest 与当前机器的兼容性。返回 (manifest, blockers)"""
    mf_path = bundle / MANIFEST_NAME
    if not mf_path.is_file():
        return None, [f"未找到 {MANIFEST_NAME}, 这不是有效的部署包"]

    mf = json.loads(mf_path.read_text(encoding="utf-8"))
    blockers, warnings_, matches = [], [], []
    cur = platform_info()
    b = mf.get("builder", {})

    # 平台指纹比对 (最关键)
    if b.get("tag") and b["tag"] != cur["tag"]:
        blockers.append(
            f"平台不匹配: 打包于 {b['tag']}, 当前机器为 {cur['tag']}")
    elif b.get("tag"):
        matches.append(f"平台指纹一致 ({cur['tag']})")

    # 逐项给出人类可读的差异说明
    if b.get("system") and b["system"] != cur["system"]:
        blockers.append(f"操作系统不同: {b['system']} -> {cur['system']}")
    if b.get("machine") and b["machine"].lower() != cur["machine"].lower():
        blockers.append(f"CPU 架构不同: {b['machine']} -> {cur['machine']}")
    if b.get("python_version"):
        bmaj = ".".join(b["python_version"].split(".")[:2])
        cmaj = ".".join(cur["python_version"].split(".")[:2])
        if bmaj != cmaj:
            # 主次版本不同 -> wheel 的 ABI 标记(cp313 等)可能不兼容, 阻塞
            blockers.append(
                f"Python 版本不兼容: 打包于 {b['python_version']}, "
                f"当前 {cur['python_version']} (ABI 标记可能不同)")
        elif b["python_version"] != cur["python_version"]:
            # 主次版本相同, 仅补丁号不同 -> 通常兼容, 仅提示
            warnings_.append(
                f"Python 补丁版本差异: {b['python_version']} -> "
                f"{cur['python_version']} (通常兼容)")
        else:
            matches.append(f"Python 版本一致 ({cur['python_version']})")

    # 中文字体提示 (不阻塞, 但要提醒)
    if cur["system"] == "Linux" and not cur["cjk_fonts"]:
        warnings_.append("当前系统未检测到中文字体, PDF/Word 中文可能显示为方框")

    return mf, blockers + warnings_, {
        "blockers": blockers, "warnings": warnings_, "matches": matches,
    }


def install_linux_sysdeps(args):
    """Linux: 尝试安装 opencv 与字体所需系统库"""
    if platform.system() != "Linux":
        return True, "非 Linux, 跳过"

    missing = []
    # 检查关键库是否存在
    checks = {
        "libgl1": ["/usr/lib/x86_64-linux-gnu/libGL.so.1",
                   "/usr/lib/aarch64-linux-gnu/libGL.so.1"],
        "libglib2.0-0": ["/usr/lib/x86_64-linux-gnu/libglib-2.0.so.0",
                         "/usr/lib/aarch64-linux-gnu/libglib-2.0.so.0"],
    }
    for pkg, paths in checks.items():
        if not any(Path(p).exists() for p in paths):
            missing.append(pkg)

    # 中文字体
    from common import find_cjk_fonts
    if not find_cjk_fonts():
        missing.append("fonts-wqy-microhei")

    if not missing:
        return True, "系统库已齐全, 无需安装"

    print(f"  检测到缺失的系统库: {', '.join(missing)}")

    if args.no_sysdeps:
        warn("--no-sysdeps: 跳过系统库安装")
        warn("若后续 PDF 中文显示方框或 opencv 报错, 请手动安装:")
        print(f"    sudo apt install {' '.join(missing)}")
        return False, "已跳过"

    if not shutil.which("apt-get") and not shutil.which("dpkg"):
        warn("未找到 apt/dpkg, 无法自动安装。请手动处理:")
        print(f"    sudo apt install {' '.join(missing)}")
        return False, "无包管理器"

    # 优先用本地 deb (若 bundle 内附带)
    local_debs = list((args.bundle_dir / "debs").glob("*.deb")) \
        if hasattr(args, "bundle_dir") and args.bundle_dir else []
    if local_debs:
        if os.geteuid() != 0:
            warn("安装本地 deb 需要 root 权限, 请用 sudo 重新运行, 或手动执行:")
            print(f"    sudo dpkg -i {'debs/*.deb'}")
            return False, "需 sudo"
        rc = run(["dpkg", "-i"] + [str(d) for d in local_debs])
        return rc == 0, "本地 deb 安装"

    if os.geteuid() != 0:
        warn("自动安装系统库需要 root 权限")
        print("  请用 sudo 重新运行, 或手动执行:")
        print(f"    sudo apt install {' '.join(missing)}")
        return False, "需 sudo"

    rc = run(["apt-get", "install", "-y"] + missing)
    return rc == 0, "apt 安装"


def do_install(args):
    t0 = time.time()
    bundle = Path(args.bundle).resolve()
    pkg_dir = bundle / "packages"

    total = 6
    print("=" * 62)
    print("  离线部署 —— 安装模式 (在目标机器上运行)")
    print("=" * 62)

    # ---- 1. 校验部署包 ----
    step(1, total, "校验部署包完整性")
    if not bundle.is_dir():
        err(f"部署包目录不存在: {bundle}")
        return 1

    mf, msgs, split = check_manifest(bundle, args.force)
    if mf is None:
        err(msgs[0])
        return 1

    cur = platform_info()
    b = mf.get("builder", {})
    print(f"  打包环境: {b.get('system')} {b.get('machine')} / "
          f"Python {b.get('python_version')}  [{b.get('tag')}]")
    print(f"  当前环境: {cur['system']} {cur['machine']} / "
          f"Python {cur['python_version']}  [{cur['tag']}]")
    print(f"  包数量:   {mf.get('package_count')}  "
          f"(含 OCR: {'是' if mf.get('with_ocr') else '否'})")

    for m in split["matches"]:
        ok(m)
    for w in split["warnings"]:
        warn(w)

    if split["blockers"]:
        print("\n  兼容性问题:")
        for bl in split["blockers"]:
            err(bl)
        if not args.force:
            print("\n  安装中止。如确认要强行继续 (可能失败), 加 --force")
            print("  正确做法: 在目标平台重新执行 pack 模式")
            return 2
        warn("--force: 忽略兼容性问题继续安装")

    # 关键文件检查
    if not pkg_dir.is_dir() or not list(pkg_dir.glob("*")):
        err(f"依赖包目录为空: {pkg_dir}")
        return 1
    ok("部署包校验通过")

    # ---- 2. 定位 Python ----
    step(2, total, "确认 Python 环境")
    if args.python:
        py = args.python
        py_src = "命令行指定"
    else:
        # 安装场景: 装到"当前解释器", 不跨环境搜索,
        # 避免用户本意装 A 却装进了 B
        try:
            import env as env_mod
            py, py_src = env_mod.find_python(prefer_with_deps=False)
        except Exception:
            py, py_src = sys.executable, "当前解释器 (探测失败)"
    rc, out = run_capture([py, "-V"])
    if rc != 0:
        err(f"Python 不可用: {py}")
        return 1
    print(f"  解释器: {py}")
    print(f"  来源:   {py_src}")
    print(f"  版本:   {out.strip()}")
    ok("Python 可用")
    if not args.python:
        print(f"  提示: 依赖将安装到上述解释器; 如需其他解释器请用 --python 指定")

    # ---- 3. 安装 Python 依赖 (纯离线) ----
    step(3, total, "安装 Python 依赖 (--no-index 模式)")
    pkgs = mf.get("install_targets") or (CORE_PKGS + OCR_PKGS)
    cmd = [py, "-m", "pip", "install", "--no-index",
           "--find-links", str(pkg_dir), "--disable-pip-version-check"]
    if args.upgrade:
        cmd.append("--upgrade")
    cmd += pkgs

    rc = run(cmd)
    if rc != 0:
        err(f"依赖安装失败 (退出码 {rc})")
        print("\n  排查建议:")
        print("    1. 确认 --find-links 路径正确且含 .whl 文件")
        print("    2. 确认平台与打包机一致 (见上方指纹对比)")
        print("    3. 查看 references/offline-deploy.md 的常见问题表")
        return rc
    ok("Python 依赖安装完成")

    # ---- 4. 系统级依赖 (平台分派) ----
    step(4, total, "处理系统级依赖")
    sysname = platform.system()
    if sysname == "Linux":
        args.bundle_dir = bundle
        good, desc = install_linux_sysdeps(args)
        if good:
            ok(f"Linux 系统库: {desc}")
        else:
            warn(f"Linux 系统库: {desc} (可能影响中文输出或 opencv)")
    elif sysname == "Windows":
        # Windows 特有: VC++ 运行库 (onnxruntime 依赖)
        ok("Windows: 无需额外系统库")
        print("    注意: 若启动时提示缺少 DLL, 需安装 VC++ 2015-2022 ")
        print("    可再发行组件 (x64), 离线包见 references/offline-deploy.md")
    elif sysname == "Darwin":
        ok("macOS: 无需额外系统库")
        if not shutil.which("tesseract"):
            print("    提示: 系统自带苹方字体; 若需 Tesseract 引擎请另行安装")
    else:
        warn(f"未知系统 {sysname}, 跳过系统级依赖")

    # ---- 5. 功能自检 ----
    step(5, total, "功能自检")
    sk_scripts = Path(args.skill) if args.skill else bundle / "image-toolkit" / "scripts"
    if not sk_scripts.is_dir():
        # 部署包里没有 skill 本体, 回退到脚本自身所在目录
        sk_scripts = HERE
        warn(f"部署包内未找到 skill 本体, 使用当前脚本目录: {sk_scripts}")

    rc = run([py, str(sk_scripts / "setup_env.py"), "--check"])
    if rc != 0:
        warn("自检发现缺失项 (详见上方输出)")
    else:
        ok("自检通过")

    # ---- 6. 端到端冒烟测试 ----
    step(6, total, "端到端冒烟测试")
    smoke = sk_scripts / "selftest.py"
    if smoke.is_file():
        rc = run([py, str(smoke)])
        if rc == 0:
            ok("冒烟测试通过 —— 部署成功, 可以离线使用")
        else:
            warn("冒烟测试未完全通过, 请检查上方输出")
    else:
        # 退化: 直接验证关键模块可导入
        code = ("import PIL,openpyxl,docx,reportlab,numpy;"
                "print('core-ok');"
                "\ntry:\n import rapidocr_onnxruntime;print('ocr-ok')\n"
                "except ImportError: print('ocr-missing')")
        rc, out = run_capture([py, "-c", code])
        print(out.strip())
        if "core-ok" in out:
            ok("核心依赖可导入")
        if "ocr-missing" in out:
            warn("OCR 引擎不可用, 识别与分类功能将失效")

    print(f"\n{'=' * 62}")
    print("  安装完成")
    print("=" * 62)
    print(f"  耗时: {time.time() - t0:.1f}s")
    print(f"\n  使用方式:")
    print(f'    "{py}" "{sk_scripts / "pipeline.py"}" <图片目录> --out ./结果 --to docx,xlsx')
    print(f"\n  如需再次验证: \"{py}\" \"{sk_scripts / 'setup_env.py'}\" --check")
    return 0


# ============================================================ 其它模式

def do_status(args):
    """查看当前环境状态 (不依赖部署包)"""
    import common
    pi = platform_info()
    print("=" * 62)
    print("  当前环境状态")
    print("=" * 62)
    print(f"  操作系统: {pi['system']} {pi['release']}")
    print(f"  CPU 架构: {pi['machine']}")
    print(f"  Python:   {pi['python_version']} ({pi['python_impl']}, {pi['bits']}bit)")
    print(f"  指纹:     {pi['tag']}")
    print(f"  解释器:   {pi['python_exe']}")

    print(f"\n  中文字体: {len(pi['cjk_fonts'])} 个 "
          f"{'(' + ', '.join(pi['cjk_fonts']) + ')' if pi['cjk_fonts'] else ''}")
    if pi["system"] == "Linux" and not pi["cjk_fonts"]:
        warn("缺中文字体 -> sudo apt install fonts-wqy-microhei")

    print("\n  依赖状态:")
    for name, okk, info in common.list_engines():
        print(f"    {'OK ' if okk else 'NO '} {name:12s} {info}")

    rc = run([sys.executable, str(HERE / "setup_env.py"), "--check"])
    return rc


def do_plan(args):
    """给出「我这台机器该怎么部署」的操作方案 (不执行任何操作)"""
    cur = platform_info()
    sysname = platform.system()

    print("=" * 62)
    print("  部署方案诊断")
    print("=" * 62)
    print(f"  目标机器: {cur['system']} {cur['release']} / {cur['machine']}")
    print(f"  Python:   {cur['python_version']} ({cur['python_impl']}, {cur['bits']}bit)")
    print(f"  平台指纹: {cur['tag']}")

    # ---- 已有环境判断 ----
    import common
    have = {}
    for name, okk, _info in common.list_engines():
        have[name] = okk
    fonts = cur["cjk_fonts"]

    print(f"\n  中文字体: {len(fonts)} 个" + (f" ({', '.join(fonts)})" if fonts else ""))

    deployed = have.get("rapidocr") or have.get("tesseract")
    if deployed and fonts:
        print("\n  \u2713 本机已具备运行条件, 无需部署。")
        print("    直接使用: python pipeline.py <图片目录> --out ./结果 --to docx,xlsx")
        rc = run([sys.executable, str(HERE / "selftest.py")])
        return rc

    # ---- 需要部署: 生成步骤 ----
    print("\n  \u2717 本机尚不满足运行条件, 需要部署。\n")

    steps = []

    # 步骤 1: 系统级依赖 (因平台而异)
    if sysname == "Linux":
        from common import find_cjk_fonts
        miss = []
        if not fonts:
            miss.append("fonts-wqy-microhei")
        lib_ok = any(Path(p).exists() for p in [
            "/usr/lib/x86_64-linux-gnu/libGL.so.1",
            "/usr/lib/aarch64-linux-gnu/libGL.so.1"])
        if not lib_ok:
            miss += ["libgl1", "libglib2.0-0"]
        if miss:
            steps.append(("安装 Linux 系统库", f"sudo apt install {' '.join(miss)}"))
    elif sysname == "Windows":
        steps.append(("确认 VC++ 运行库",
                      "若启动报 DLL 缺失, 安装 VC++ 2015-2022 可再发行组件 (x64)"))
    elif sysname == "Darwin":
        if not fonts:
            steps.append(("检查中文字体", "系统自带苹方; 若缺失请安装"))

    # 步骤 2: 依赖包准备 (取决于是否有网)
    steps.append((
        "在【同平台联网机器】上打包",
        f"python deploy_offline.py pack --bundle ./bundle  "
        f"(目标指纹须为 {cur['tag']})"))

    # 步骤 3: 搬运与安装
    steps.append(("搬运", "把 bundle 目录 (或 .zip) 拷到本机"))
    steps.append(("本机安装",
                  "python deploy_offline.py install --bundle ./bundle"))

    # 步骤 4: 验证
    steps.append(("验证", "python selftest.py"))

    print("  建议步骤:")
    for i, (title, cmd) in enumerate(steps, 1):
        print(f"\n    {i}. {title}")
        print(f"       {cmd}")

    # ---- 关键风险提示 ----
    print("\n  \u26a0 关键注意:")
    print(f"    - 打包机必须与目标机同平台同 Python 大版本")
    print(f"      目标指纹: {cur['tag']}")
    if "aarch64" in cur["tag"] or "arm" in cur["tag"]:
        print("    - 检测到 ARM 架构: onnxruntime/opencv 可能无现成 wheel,")
        print("      建议先确认 pip download 能否成功, 否则需源码编译")
    if sysname == "Linux" and any(k in platform.release().lower()
                                  for k in ("kylin", "uos", "deepin", "openeuler")):
        print("    - 检测到国产化发行版: 优先确认 Python 与 wheel 兼容性")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="image-toolkit 离线部署自动化 (打包 / 安装 / 诊断)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型流程:
  # 1. 目标机器上先诊断 (不确定该做什么时)
  python deploy_offline.py plan

  # 2. 有网机器: 打包
  python deploy_offline.py pack --bundle ./bundle

  # 3. 目标机器: 安装 (自动校验平台 + 装依赖 + 自检)
  python deploy_offline.py install --bundle ./bundle

其它:
  python deploy_offline.py status              # 查看当前环境
  python deploy_offline.py pack --no-ocr       # 精简包 (约 25MB, 无识别能力)
  python deploy_offline.py pack --mirror aliyun
""")

    sub = ap.add_subparsers(dest="mode", required=True)

    # pack
    p = sub.add_parser("pack", help="在有网机器上打包依赖")
    p.add_argument("--bundle", default="./offline-bundle",
                   help="部署包输出目录 (默认 ./offline-bundle)")
    p.add_argument("--mirror", default="tsinghua", choices=list(MIRRORS),
                   help="pip 镜像源 (默认清华)")
    p.add_argument("--no-ocr", action="store_true",
                   help="不打包 OCR 依赖 (体积小但失去识别能力)")
    p.add_argument("--no-zip", action="store_true", help="不生成 zip 包")
    p.add_argument("--clean", action="store_true", help="打包前清空已有包目录")
    p.add_argument("--for-platform", default=None,
                   help="指定目标平台指纹 (用于提前校验, 如 linux_x86_64_cp311_64bit)")

    # install
    i = sub.add_parser("install", help="在目标机器上安装")
    i.add_argument("--bundle", required=True, help="部署包目录 (pack 的产物)")
    i.add_argument("--python", default=None, help="目标 Python 解释器 (默认当前)")
    i.add_argument("--skill", default=None, help="skill scripts 目录 (默认从包内取)")
    i.add_argument("--force", action="store_true", help="忽略平台不匹配强制安装")
    i.add_argument("--upgrade", action="store_true", help="pip 使用 --upgrade")
    i.add_argument("--no-sysdeps", action="store_true",
                   help="跳过 Linux 系统库安装")

    # status
    sub.add_parser("status", help="查看当前机器环境状态")

    # plan
    sub.add_parser("plan", help="诊断当前机器需要哪些部署步骤 (不执行)")

    args = ap.parse_args()

    if args.mode == "pack":
        return do_pack(args)
    if args.mode == "install":
        return do_install(args)
    if args.mode == "status":
        return do_status(args)
    if args.mode == "plan":
        return do_plan(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
