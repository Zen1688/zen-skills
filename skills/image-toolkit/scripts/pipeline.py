#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一体化流水线: 图片 -> 识别 -> 分类 -> 导出 Office 文档

典型用法:
  # 全流程: 识别 + 内置业务分类 + 导出 Word/Excel
  python pipeline.py ./照片 --out ./结果 --to docx,xlsx

  # 自定义分类 + 按分类分文件夹归档
  python pipeline.py ./照片 --rules ./my_rules.json --to pdf --group-by-category

  # 只做格式转换
  python pipeline.py ./图 --convert png --out ./转好的

完全离线, 无网络调用。
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 首次调用时自动补齐依赖。**必须早于任何重依赖导入** ——
# 依赖缺失时会切到已就绪的解释器重跑本脚本。
from bootstrap import ensure_and_reexec  # noqa: E402
ensure_and_reexec(need_ocr=True)

from common import iter_images, pick_engine, list_engines, human_size  # noqa: E402
import convert as conv_mod  # noqa: E402
import ocr as ocr_mod  # noqa: E402
import classify as cls_mod  # noqa: E402
import export as exp_mod  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description="图片处理全流程 (格式转换 / OCR / 分类 / 导出 Office) —— 完全离线",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    ap.add_argument("input", help="输入图片文件或目录")
    ap.add_argument("--out", default="./out", help="输出目录 (默认 ./out)")
    ap.add_argument("--to", default="docx,xlsx",
                    help="导出格式, 逗号分隔: docx,xlsx,pdf,txt,md")
    ap.add_argument("--convert", default=None,
                    help="先做格式转换, 如 png/jpg/webp/pdf；不填则跳过")
    ap.add_argument("--rules", default=None, help="自定义分类规则 JSON")
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "rapidocr", "tesseract"], help="OCR 引擎")
    ap.add_argument("--threshold", type=float, default=0.25, help="分类置信度阈值")
    ap.add_argument("--group-by-category", action="store_true",
                    help="额外按分类把原图复制到子文件夹")
    ap.add_argument("--no-ocr", action="store_true", help="跳过 OCR, 仅转换")
    ap.add_argument("--no-image", action="store_true", help="导出时不嵌入原图")
    ap.add_argument("--json", action="store_true", help="额外输出结果 JSON")
    args = ap.parse_args()

    t0 = time.time()
    src = Path(args.input)
    if not src.exists():
        print(f"[错误] 输入不存在: {src}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = iter_images(src) if src.is_dir() else [src]
    if not files:
        print(f"[无图片] {src}", file=sys.stderr)
        return 1

    print("=" * 62)
    print(f"  图片处理流水线  |  {len(files)} 张  |  输出 -> {out_dir}")
    print("=" * 62)

    # ---------- 阶段 0: 格式转换 ----------
    if args.convert:
        cdir = out_dir / f"converted_{args.convert}"
        ok, err = conv_mod.batch_convert(src, args.convert, cdir)
        print(f"\n[阶段1] 格式转换 -> {args.convert}: 成功 {len(ok)}, 失败 {len(err)}")
        for p in ok[:5]:
            print(f"        {Path(p).name}")
        if len(ok) > 5:
            print(f"        ... 共 {len(ok)} 个")
        for p, e in err[:5]:
            print(f"        ERR {Path(p).name}: {e}")
        if args.no_ocr:
            print(f"\n完成 (仅转换), 耗时 {time.time()-t0:.1f}s")
            return 0

    # ---------- 阶段 1: 引擎自检 ----------
    eng = pick_engine()
    print("\n[引擎自检]")
    for name, ok, info in list_engines():
        print(f"  {'OK' if ok else 'NO'}  {name:12s} {info}")
    if not eng:
        print("\n[错误] 无可用 OCR 引擎。"
              "请先运行: python setup_env.py --with-rapidocr", file=sys.stderr)
        return 2
    print(f"  -> 使用引擎: {eng}")

    # ---------- 阶段 2: OCR ----------
    print(f"\n[阶段2] 文字识别 ({len(files)} 张)")
    results, fails = [], []
    for i, f in enumerate(files, 1):
        try:
            r = ocr_mod.recognize(f, args.engine)
            results.append(r)
            prev = (r["text"] or "").replace("\n", " ")[:40]
            print(f"  [{i}/{len(files)}] {f.name}  {r['line_count']} 行  {prev}")
        except Exception as e:
            fails.append({"file": str(f), "error": str(e)})
            print(f"  [{i}/{len(files)}] {f.name}  ERR {e}")

    if not results:
        print("\n[错误] 全部识别失败", file=sys.stderr)
        return 1

    # ---------- 阶段 3: 分类 ----------
    rules = cls_mod.load_rules(args.rules) if args.rules else None
    cat_name = Path(args.rules).stem if args.rules else "内置业务分类"
    print(f"\n[阶段3] 内容分类 (规则: {cat_name})")

    stats = {}
    for r in results:
        try:
            feats = cls_mod.image_features(r["file"])
            c = cls_mod.classify_one(r["text"], feats, r["line_count"],
                                     rules, args.threshold)
            r["category"] = c["label"]
            r["confidence"] = c["score"]
            r["evidence"] = c["evidence"]
            r["alternatives"] = c.get("alternatives", [])
            r["features"] = feats
            stats[c["label"]] = stats.get(c["label"], 0) + 1
            ev = c["evidence"][0] if c["evidence"] else ""
            print(f"  {Path(r['file']).name:32s} -> {c['label']:14s} "
                  f"({c['score']})  {ev}")
        except Exception as e:
            r["category"] = "分类失败"
            r["confidence"] = 0
            r["evidence"] = [str(e)]
            print(f"  {Path(r['file']).name:32s} -> ERR {e}")

    print("\n  分类统计:")
    for k in sorted(stats, key=lambda x: -stats[x]):
        bar = "#" * min(stats[k], 30)
        print(f"    {k:16s} {stats[k]:3d}  {bar}")

    # ---------- 阶段 4: 导出 ----------
    payload = {"results": results + fails, "count": len(results),
               "failed": len(fails)}
    json_path = out_dir / "recognition.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    fmts = [f.strip().lower() for f in args.to.split(",") if f.strip()]
    print(f"\n[阶段4] 导出: {', '.join(fmts)}")
    for f in fmts:
        fn = exp_mod.FORMATS.get(f)
        if not fn:
            print(f"  [跳过] 不支持的格式: {f}")
            continue
        dst = out_dir / f"识别报告.{f}"
        try:
            if f in ("docx", "pdf"):
                p = fn(payload, str(dst), embed_image=not args.no_image)
            else:
                p = fn(payload, str(dst))
            print(f"  [OK] {f:5s} -> {p}  ({human_size(Path(p).stat().st_size)})")
        except Exception as e:
            print(f"  [FAIL] {f}: {e}", file=sys.stderr)

    # ---------- 阶段 5: 按分类归档 (可选) ----------
    if args.group_by_category:
        import shutil
        adir = out_dir / "按分类归档"
        moved = 0
        for r in results:
            cat = r.get("category") or "未分类"
            safe = "".join(ch for ch in cat if ch not in r'\/:*?"<>|') or "未分类"
            d = adir / safe
            d.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(r["file"], d / Path(r["file"]).name)
                moved += 1
            except Exception:
                pass
        print(f"\n[阶段5] 按分类归档: {moved} 张 -> {adir}")

    if args.json:
        print(f"\n[JSON] {json_path}")

    print(f"\n{'=' * 62}")
    print(f"  完成: {len(results)} 张成功, {len(fails)} 张失败, "
          f"耗时 {time.time()-t0:.1f}s")
    print(f"  输出目录: {out_dir.resolve()}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
