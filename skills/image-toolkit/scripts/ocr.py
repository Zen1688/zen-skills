#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图片文字识别 (OCR) 模块 —— 完全离线

引擎优先级:
  1. RapidOCR (PP-OCRv4 ONNX)  —— 中文准确率最高, 纯 pip 安装, 模型随包离线
  2. Tesseract (pytesseract)   —— 需系统安装 tesseract.exe + chi_sim 语言包

无任何网络调用。模型文件全部来自本地包目录。
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import INPUT_EXTS, iter_images, list_engines  # noqa: E402

# 首次调用时自动补齐依赖。**必须早于任何重依赖导入** ——
# 依赖缺失时会切到已就绪的解释器重跑本脚本。
from bootstrap import ensure_and_reexec  # noqa: E402
ensure_and_reexec(need_ocr=True)


# ---------------------------------------------------------------- RapidOCR

def ocr_rapidocr(img_path):
    """用 RapidOCR 识别, 返回 (lines, engine_name)
    lines: [{"text": str, "score": float, "box": [[x,y],...]}, ...]
    """
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    result, elapsed = engine(str(img_path))
    lines = []
    if result:
        for item in result:
            box, text, score = item[0], item[1], item[2]
            lines.append({
                "text": str(text),
                "score": round(float(score), 4),
                "box": [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in box],
            })
    return lines, "rapidocr"


# --------------------------------------------------------------- Tesseract

def _tess_cmd():
    """定位 tesseract 可执行文件 (跨平台)"""
    from common import find_tesseract
    return find_tesseract()


def ocr_tesseract(img_path, lang="chi_sim+eng"):
    """用 Tesseract 识别"""
    import pytesseract
    from PIL import Image

    exe = _tess_cmd()
    if not exe:
        raise RuntimeError("未找到 tesseract 可执行文件")
    pytesseract.pytesseract.tesseract_cmd = exe

    with Image.open(img_path) as im:
        data = pytesseract.image_to_data(
            im, lang=lang, output_type=pytesseract.Output.DICT)

    lines, cur, key = [], [], None
    for i in range(len(data["text"])):
        txt = (data["text"][i] or "").strip()
        blk = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if blk != key:
            if cur:
                lines.append(cur)
            cur, key = [], blk
        if txt:
            conf = float(data["conf"][i])
            if conf > 0:
                cur.append({
                    "text": txt, "score": round(conf / 100.0, 4),
                    "x": data["left"][i], "y": data["top"][i],
                    "w": data["width"][i], "h": data["height"][i],
                })
    if cur:
        lines.append(cur)

    out = []
    for ln in lines:
        if not ln:
            continue
        out.append({
            "text": " ".join(w["text"] for w in ln),
            "score": round(sum(w["score"] for w in ln) / len(ln), 4),
            "box": [[ln[0]["x"], ln[0]["y"]],
                    [ln[0]["x"] + max(w["w"] for w in ln), ln[0]["y"]],
                    [ln[0]["x"] + max(w["w"] for w in ln),
                     ln[0]["y"] + max(w["h"] for w in ln)],
                    [ln[0]["x"], ln[0]["y"] + max(w["h"] for w in ln)]],
        })
    return out, "tesseract"


# ------------------------------------------------------------------ 统一入口

def recognize(img_path, engine="auto", lang="chi_sim+eng"):
    """统一 OCR 入口, 自动选择可用引擎"""
    path = Path(img_path)
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")

    order = []
    if engine == "auto":
        order = ["rapidocr", "tesseract"]
    else:
        order = [engine]

    errs = []
    for eng in order:
        try:
            if eng == "rapidocr":
                lines, name = ocr_rapidocr(path)
            elif eng == "tesseract":
                lines, name = ocr_tesseract(path, lang)
            else:
                continue
            # 空结果也视为识别完成 (可能是纯图片无文字)
            return {
                "file": str(path),
                "engine": name,
                "text": "\n".join(l["text"] for l in lines),
                "lines": lines,
                "line_count": len(lines),
            }
        except Exception as e:
            errs.append(f"{eng}: {e}")
            continue

    raise RuntimeError("所有 OCR 引擎均不可用 -> " + " | ".join(errs))


def main():
    ap = argparse.ArgumentParser(description="图片文字识别 (完全离线)")
    ap.add_argument("input", help="图片文件或目录")
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "rapidocr", "tesseract"])
    ap.add_argument("--lang", default="chi_sim+eng", help="Tesseract 语言包")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--out", default=None, help="结果写入文件")
    ap.add_argument("--list-engines", action="store_true", help="仅列出可用引擎")
    args = ap.parse_args()

    if args.list_engines:
        for name, ok, info in list_engines():
            print(f"{'OK ' if ok else 'NO '} {name:12s} {info}")
        return 0

    src = Path(args.input)
    files = iter_images(src) if src.is_dir() else [src]
    if not files:
        print(f"[无图片] {src}", file=sys.stderr)
        return 1

    all_res, fails = [], []
    for f in files:
        try:
            all_res.append(recognize(f, args.engine, args.lang))
        except Exception as e:
            fails.append({"file": str(f), "error": str(e)})

    if args.json or args.out:
        payload = {"results": all_res, "errors": fails,
                   "count": len(all_res), "failed": len(fails)}
        blob = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(blob, encoding="utf-8")
            print(f"[已写入] {args.out}  ({len(all_res)} 张成功, {len(fails)} 张失败)")
        else:
            print(blob)
    else:
        for r in all_res:
            print(f"\n===== {r['file']}  [{r['engine']}] {r['line_count']} 行 =====")
            print(r["text"] if r["text"] else "(未识别到文字)")
        if fails:
            print("\n--- 失败 ---")
            for f in fails:
                print(f"  {f['file']}: {f['error']}")

    return 0 if all_res else 1


if __name__ == "__main__":
    sys.exit(main())
