#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键环境准备 (可选, 仅首次需要联网)

说明: 本 skill 的**运行时完全离线**。此脚本只用于首次安装 Python 依赖,
安装完成后即可断网使用。若目标机器已有依赖, 无需运行。

**通常不需要手动执行本脚本** —— 首次调用任一功能脚本时,
bootstrap.py 会自动检测并补齐依赖。本脚本用于:
  - 想提前把依赖装好 (例如部署阶段一次性完成)
  - 指定镜像源 / 只检查环境
  - 自动安装被禁用 (IMAGE_TOOLKIT_NO_AUTO_INSTALL=1) 时的手动兜底

用法:
  python setup_env.py            # 用清华镜像安装 (国内推荐)
  python setup_env.py --official # 用官方 PyPI
  python setup_env.py --check    # 只检查, 不安装
"""
import argparse
import subprocess
import sys
from pathlib import Path

REQUIRED = [
    ("PIL", "Pillow", "图像读写与格式转换"),
    ("openpyxl", "openpyxl", "Excel 输出"),
    ("docx", "python-docx", "Word 输出"),
    ("reportlab", "reportlab", "PDF 输出"),
    ("numpy", "numpy", "图像特征计算"),
]

OPTIONAL = [
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime",
     "OCR 引擎 (推荐, 中文准确率高, 模型随包离线)"),
    ("pytesseract", "pytesseract", "OCR 引擎 (需另装 tesseract.exe)"),
]

MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
    "official": "https://pypi.org/simple",
}


def check(mods):
    ok, miss = [], []
    for mod, pkg, desc in mods:
        try:
            __import__(mod)
            ok.append((pkg, desc))
        except ImportError:
            miss.append((pkg, desc))
    return ok, miss


def install(pkgs, index=None):
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    if index:
        cmd += ["-i", index]
        host = index.split("//")[-1].split("/")[0]
        if not host.endswith("pypi.org"):
            cmd += ["--trusted-host", host]
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", default="tsinghua", choices=list(MIRRORS))
    ap.add_argument("--official", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--with-rapidocr", action="store_true",
                    help="一并安装 RapidOCR 引擎 (推荐)")
    args = ap.parse_args()

    from common import platform_report
    pr = platform_report()

    print(f"Python: {sys.executable}")
    print(f"版本:   {pr['python']}")
    print(f"平台:   {pr['platform']}")

    print("\n=== 中文字体 (PDF/Word 输出需要) ===")
    if pr["cjk_fonts"]:
        for fp, alias, disp in pr["cjk_fonts"]:
            print(f"  OK  {alias:12s} {fp}")
    else:
        print("  NO  未找到中文字体")
        print("      Windows: 系统自带微软雅黑, 通常不会缺失")
        print("      Linux:   sudo apt install fonts-wqy-microhei")
        print("      macOS:   系统自带苹方, 通常不会缺失")
    print(f"  Word 将使用字体: {pr['docx_font']}")
    print()

    ok, miss = check(REQUIRED)
    print("=== 必需依赖 ===")
    for p, d in ok:
        print(f"  OK  {p:20s} {d}")
    for p, d in miss:
        print(f"  NO  {p:20s} {d}")

    ok_o, miss_o = check(OPTIONAL)
    print("\n=== OCR 引擎 ===")
    for p, d in ok_o:
        print(f"  OK  {p:20s} {d}")
    for p, d in miss_o:
        print(f"  NO  {p:20s} {d}")

    if args.check:
        return 1 if (miss and not ok_o) else 0

    to_install = [p for p, _ in miss]
    if args.with_rapidocr and any(p == "rapidocr-onnxruntime" for p, _ in miss_o):
        to_install.append("rapidocr-onnxruntime")

    if not to_install:
        print("\n所有依赖已就绪, 无需安装。")
        return 0

    index = None if args.official else MIRRORS[args.mirror]
    print(f"\n>>> 开始安装 {len(to_install)} 个包 (镜像: {args.mirror if index else 'official'})")
    rc = install(to_install, index)
    print(f"\n退出码: {rc}")
    if rc == 0:
        print("安装完成, 之后可断网使用。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
