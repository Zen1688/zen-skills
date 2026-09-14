#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图片格式转换模块 (离线)
支持: JPG / PNG / WEBP / BMP / TIFF / GIF / ICO / PDF 互转
依赖: Pillow (纯离线, 无网络调用)
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 首次调用时自动补齐依赖。**必须早于任何重依赖导入** ——
# 依赖缺失时会切到已就绪的解释器重跑本脚本。
from bootstrap import ensure_and_reexec  # noqa: E402
ensure_and_reexec(need_ocr=False)

try:
    from PIL import Image
except ImportError:
    print("ERROR: 缺少 Pillow, 请运行: pip install Pillow", file=sys.stderr)
    sys.exit(2)

# 可读的输入格式 (Pillow 支持的超集)
INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
              ".gif", ".ico", ".jfif", ".ppm", ".pgm", ".tga", ".avif"}

# 输出格式 -> Pillow 格式名 / 扩展名
OUTPUT_FORMATS = {
    "jpg": ("JPEG", ".jpg"),
    "jpeg": ("JPEG", ".jpg"),
    "png": ("PNG", ".png"),
    "webp": ("WEBP", ".webp"),
    "bmp": ("BMP", ".bmp"),
    "tiff": ("TIFF", ".tiff"),
    "tif": ("TIFF", ".tiff"),
    "gif": ("GIF", ".gif"),
    "ico": ("ICO", ".ico"),
    "pdf": ("PDF", ".pdf"),
}

# 不支持透明通道的格式, 需要先合成背景
NO_ALPHA = {"JPEG", "BMP", "PDF"}


def _flatten_alpha(img, bg=(255, 255, 255)):
    """把带透明通道的图合成到纯色背景上"""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas = Image.new("RGB", img.size, bg)
        canvas.paste(img, mask=img.split()[-1])
        return canvas
    return img


def convert_one(src, dst_fmt, out_dir=None, quality=92, dpi=150, bg=(255, 255, 255)):
    """转换单张图片, 返回输出路径"""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"源文件不存在: {src}")

    pillow_fmt, ext = OUTPUT_FORMATS[dst_fmt.lower()]

    out_dir = Path(out_dir) if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ext)
    # 防止自覆盖
    if dst.resolve() == src.resolve():
        dst = out_dir / (src.stem + "_converted" + ext)

    with Image.open(src) as img:
        img.load()
        frames = getattr(img, "n_frames", 1)

        # 多帧图 (GIF/TIFF) 转 GIF/PDF/TIFF 时保留全部帧, 其余只取首帧
        if frames > 1 and pillow_fmt in ("GIF", "PDF", "TIFF"):
            imgs = []
            for i in range(frames):
                img.seek(i)
                imgs.append(img.convert("RGB"))
            if pillow_fmt == "GIF":
                imgs[0].save(dst, save_all=True, append_images=imgs[1:],
                             format="GIF", loop=0)
            elif pillow_fmt == "PDF":
                imgs[0].save(dst, save_all=True, append_images=imgs[1:],
                             format="PDF", resolution=dpi)
            else:
                imgs[0].save(dst, save_all=True, append_images=imgs[1:],
                             format="TIFF")
            return str(dst)

        work = img
        if pillow_fmt in NO_ALPHA:
            work = _flatten_alpha(work, bg)
        elif pillow_fmt == "GIF":
            work = work.convert("P", palette=Image.ADAPTIVE)
        elif pillow_fmt == "ICO":
            work = work.convert("RGBA")
        elif pillow_fmt == "WEBP" and work.mode == "P":
            work = work.convert("RGBA")

        save_kw = {}
        if pillow_fmt == "JPEG":
            save_kw.update(quality=quality, optimize=True, progressive=True)
        elif pillow_fmt == "PNG":
            save_kw.update(optimize=True)
        elif pillow_fmt == "WEBP":
            save_kw.update(quality=quality, method=6)
        elif pillow_fmt == "PDF":
            save_kw.update(resolution=dpi)
        elif pillow_fmt == "ICO":
            # ICO 需要正方形尺寸集合
            save_kw.update(sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                                  (128, 128), (256, 256)])

        work.save(dst, format=pillow_fmt, **save_kw)
    return str(dst)


def batch_convert(src_dir, dst_fmt, out_dir=None, quality=92, dpi=150):
    """批量转换目录下所有图片"""
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise NotADirectoryError(f"目录不存在: {src_dir}")

    results, errors = [], []
    for f in sorted(src_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in INPUT_EXTS:
            try:
                rel = f.parent.relative_to(src_dir)
                target = (Path(out_dir) / rel) if out_dir else None
                results.append(convert_one(f, dst_fmt, target, quality, dpi))
            except Exception as e:
                errors.append((str(f), str(e)))
    return results, errors


def main():
    ap = argparse.ArgumentParser(
        description="图片格式转换 (完全离线)")
    ap.add_argument("input", help="源文件或源目录")
    ap.add_argument("--to", required=True, choices=sorted(OUTPUT_FORMATS.keys()),
                    help="目标格式")
    ap.add_argument("--out", default=None, help="输出目录 (默认与源同目录)")
    ap.add_argument("--quality", type=int, default=92, help="JPEG/WEBP 质量 1-100")
    ap.add_argument("--dpi", type=int, default=150, help="输出 PDF 的 DPI")
    args = ap.parse_args()

    src = Path(args.input)
    try:
        if src.is_dir():
            ok, err = batch_convert(src, args.to, args.out, args.quality, args.dpi)
            print(f"[批量转换] 成功 {len(ok)} 个, 失败 {len(err)} 个")
            for p in ok:
                print(f"  OK  {p}")
            for p, e in err:
                print(f"  ERR {p} -> {e}")
            return 0 if ok else 1
        else:
            out = convert_one(src, args.to, args.out, args.quality, args.dpi)
            print(f"[转换成功] {out}")
            return 0
    except Exception as e:
        print(f"[转换失败] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
