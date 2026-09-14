#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""共享工具: 图片枚举 / 引擎探测 / 输出目录约定"""
import os
import shutil
import sys
from pathlib import Path

INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
              ".gif", ".ico", ".jfif", ".ppm", ".pgm", ".tga", ".avif"}


def iter_images(src, recursive=True):
    """枚举目录下所有可处理图片"""
    src = Path(src)
    if src.is_file():
        return [src] if src.suffix.lower() in INPUT_EXTS else []
    if not src.is_dir():
        return []
    it = src.rglob("*") if recursive else src.glob("*")
    return sorted(f for f in it if f.is_file() and f.suffix.lower() in INPUT_EXTS)


def _rapidocr_ok():
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True, "已安装 (PP-OCRv4 ONNX)"
    except ImportError:
        return False, "未安装 -> pip install rapidocr-onnxruntime"


_TESS_CANDIDATES = {
    "win32": [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "%LOCALAPPDATA%\\Programs\\Tesseract-OCR\\tesseract.exe",
    ],
    "darwin": [
        "/opt/homebrew/bin/tesseract",       # Apple Silicon Homebrew
        "/usr/local/bin/tesseract",          # Intel Homebrew
        "/opt/local/bin/tesseract",          # MacPorts
        "/usr/bin/tesseract",
    ],
    "linux": [
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/snap/bin/tesseract",
        "/usr/lib/tesseract/tesseract",
    ],
}


def find_tesseract():
    """跨平台定位 tesseract 可执行文件, 找不到返回 None"""
    import sys as _sys
    exe = shutil.which("tesseract")
    if exe:
        return exe
    plat = "win32" if _sys.platform.startswith("win") else (
        "darwin" if _sys.platform == "darwin" else "linux")
    for c in _TESS_CANDIDATES.get(plat, []):
        c = os.path.expandvars(c)
        if os.path.isfile(c):
            return c
    return None


def _tesseract_ok():
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False, "pytesseract 未安装"
    exe = find_tesseract()
    if not exe:
        return False, "未找到 tesseract 可执行文件"
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = exe
        langs = pytesseract.get_languages()
        has_cn = "chi_sim" in langs
        return True, f"{exe} | 语言包 {'含' if has_cn else '缺少'} chi_sim"
    except Exception as e:
        return False, f"探测失败: {e}"


def list_engines():
    """返回引擎可用性列表 [(name, ok, info)]"""
    return [
        ("rapidocr", *_rapidocr_ok()),
        ("tesseract", *_tesseract_ok()),
    ]


def pick_engine():
    """返回优先级最高的可用引擎名"""
    for name, ok, _ in list_engines():
        if ok:
            return name
    return None


def default_out_dir(base=None):
    """默认输出目录: <base>/out"""
    base = Path(base) if base else Path.cwd()
    d = base / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ---------------------------------------------------------- 跨平台中文字体

# 各平台的候选中文字体 (路径, 用于 reportlab 注册的别名)
# 顺序即优先级。不存在时自动跳过。
_FONT_CANDIDATES = {
    "win32": [
        (r"C:\Windows\Fonts\msyh.ttc", "MSYH"),        # 微软雅黑
        (r"C:\Windows\Fonts\msyh.ttf", "MSYH"),
        (r"C:\Windows\Fonts\simhei.ttf", "SimHei"),    # 黑体
        (r"C:\Windows\Fonts\simsun.ttc", "SimSun"),    # 宋体
        (r"C:\Windows\Fonts\simkai.ttf", "KaiTi"),     # 楷体
    ],
    "darwin": [
        ("/System/Library/Fonts/PingFang.ttc", "PingFang"),          # 苹方
        ("/System/Library/Fonts/STHeiti Medium.ttc", "STHeiti"),     # 华文黑体
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", "Hiragino"),  # 冬青黑体
        ("/Library/Fonts/Arial Unicode.ttf", "ArialUnicode"),
    ],
    "linux": [
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WQY"),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WQY"),
        ("/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc", "WQY"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "NotoCJK"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoCJK"),
        ("/usr/share/fonts/truetype/arphic/uming.ttc", "ARPL"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVu"),
    ],
}


def find_cjk_fonts():
    """跨平台探测可用中文字体。

    返回 [(路径, 别名, 显示名)]，按优先级排序；找不到返回 []。
    Windows / macOS / Linux 各自查表，不存在的路径自动跳过。
    """
    import sys as _sys
    # 额外扫描常见目录, 兜住非标准安装位置
    extra_dirs = {
        "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
                  os.path.expandvars(r"%USERPROFILE%\AppData\Local\Microsoft\Windows\Fonts")],
        "darwin": ["/Library/Fonts", os.path.expanduser("~/Library/Fonts")],
        "linux": ["/usr/share/fonts", "/usr/local/share/fonts",
                  os.path.expanduser("~/.fonts"),
                  os.path.expanduser("~/.local/share/fonts")],
    }

    plat = "win32" if _sys.platform.startswith("win") else (
        "darwin" if _sys.platform == "darwin" else "linux")

    found, seen = [], set()
    for path, alias in _FONT_CANDIDATES.get(plat, []):
        if os.path.isfile(path) and path not in seen:
            found.append((path, alias, os.path.basename(path)))
            seen.add(path)

    # 兜底: 在常见目录里搜含 CJK 特征的文件名
    if not found:
        import glob as _glob
        pats = ["*yahei*", "*msyh*", "*simhei*", "*simsun*", "*PingFang*",
                "*Hiragino*", "*wqy*", "*NotoSansCJK*", "*uming*", "*ukai*",
                "*SourceHanSans*", "*NotoSerifCJK*"]
        for d in extra_dirs.get(plat, []):
            if not os.path.isdir(d):
                continue
            for pat in pats:
                for f in _glob.glob(os.path.join(d, "**", pat + "*"),
                                    recursive=True):
                    if os.path.isfile(f) and f not in seen:
                        found.append((f, "CJKFont", os.path.basename(f)))
                        seen.add(f)
                        break
                if found:
                    break
            if found:
                break

    return found


def cjk_font_for_docx():
    """返回适合 python-docx 的中文字体名 (逻辑名, 非路径)"""
    import sys as _sys
    if _sys.platform.startswith("win"):
        return "微软雅黑"
    if _sys.platform == "darwin":
        return "PingFang SC"
    return "Noto Sans CJK SC"


def platform_report():
    """返回当前平台与字体探测结果, 用于 --check"""
    import sys as _sys
    fonts = find_cjk_fonts()
    return {
        "platform": _sys.platform,
        "python": _sys.version.split()[0],
        "cjk_fonts": fonts,
        "docx_font": cjk_font_for_docx(),
    }


if __name__ == "__main__":
    print("=== 引擎可用性 ===")
    for n, ok, info in list_engines():
        print(f"{'OK' if ok else 'NO'}  {n:12s} {info}")
    print(f"\n优选引擎: {pick_engine() or '(无可用引擎)'}")
