#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
识别结果导出模块 —— 完全离线
支持输出: Word (.docx) / Excel (.xlsx) / PDF / TXT / Markdown

输入: ocr.py 或 classify.py 的 JSON 产物
输出: 可选的「原图 + 识别文字」对照排版 / 表格结构化 / 纯文本
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import human_size, find_cjk_fonts, cjk_font_for_docx  # noqa: E402

# 首次调用时自动补齐依赖。**必须早于任何重依赖导入** ——
# 依赖缺失时会切到已就绪的解释器重跑本脚本。
from bootstrap import ensure_and_reexec  # noqa: E402
ensure_and_reexec(need_ocr=False)


# ------------------------------------------------------------------ 数据准备

def load_payload(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"results": data}
    return data


def _rows_from_item(item):
    """把单条识别结果转成表格行 (用于 Excel)
    优先用 box 坐标做二维还原: 先按 y 聚类成行, 再按 x 排序分列。
    无坐标时退化为按文本行切分。
    """
    lines = item.get("lines") or []
    if lines and all("box" in l and l["box"] for l in lines):
        # 1) 收集条目: (ymid, xmin, xmax, text)
        entries = []
        for l in lines:
            ys = [p[1] for p in l["box"]]
            xs = [p[0] for p in l["box"]]
            h = max(ys) - min(ys)
            entries.append({
                "ymid": sum(ys) / len(ys),
                "xmin": min(xs),
                "xmax": max(xs),
                "h": h,
                "text": (l.get("text") or "").strip(),
            })
        entries = [e for e in entries if e["text"]]
        if not entries:
            return []

        # 2) 按 y 聚类成行: 与「当前行组的 y 均值」比较, 避免漂移累积
        #    表格行列高一致, 用中位字高推导容差
        heights = sorted(e["h"] for e in entries if e["h"] > 0)
        med_h = heights[len(heights) // 2] if heights else 20
        tol = max(med_h * 0.55, 8)
        entries.sort(key=lambda e: e["ymid"])

        rows, cur, cur_sum = [], [entries[0]], entries[0]["ymid"]
        for e in entries[1:]:
            cur_mean = cur_sum / len(cur)
            if abs(e["ymid"] - cur_mean) <= tol:
                cur.append(e)
                cur_sum += e["ymid"]
            else:
                rows.append(cur)
                cur, cur_sum = [e], e["ymid"]
        rows.append(cur)

        # 3) 二维还原: 表格各行列边界一致, 因此先跨所有行统计「列区间」,
        #    再把每个单元格归入最近的列。比逐行切分稳健得多。
        #    3a. 用 x 中心做一维聚类, 得到候选列
        centers = sorted((e["xmin"] + e["xmax"]) / 2 for grp in rows for e in grp)
        if not centers:
            return []

        # 相邻 x 中心差的中位数作为「同列」尺度
        diffs = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
        diffs = sorted(d for d in diffs if d > 1)
        # 同列内的 x 抖动通常远小于列间距; 取 20 分位避免被大间距拉偏
        unit = diffs[len(diffs) // 5] if diffs else 10
        col_tol = max(unit * 1.6, med_h * 0.7)

        # 3b. 聚类出列中心
        col_centers = []
        for c in centers:
            if col_centers and c - col_centers[-1][-1] <= col_tol:
                col_centers[-1].append(c)
            else:
                col_centers.append([c])
        col_axis = [sum(g) / len(g) for g in col_centers]

        # 3c. 每个单元格归入最近的列; 同列同行的多个碎片按顺序拼接
        out = []
        for grp in rows:
            buckets = {}
            for e in grp:
                ec = (e["xmin"] + e["xmax"]) / 2
                ci = min(range(len(col_axis)), key=lambda i: abs(col_axis[i] - ec))
                buckets.setdefault(ci, []).append(e)
            cells = []
            for ci in sorted(buckets):
                parts = sorted(buckets[ci], key=lambda x: x["xmin"])
                cells.append(" ".join(p["text"] for p in parts))
            out.append(cells)
        return out

    text = item.get("text", "")
    rows = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = re.split(r"\s{2,}|\t+", ln)
        rows.append([p.strip() for p in parts] if len(parts) > 1 else [ln])
    return rows


# ---------------------------------------------------------------- 各格式输出

def export_txt(payload, out_path, with_meta=True):
    buf = []
    for i, it in enumerate(payload.get("results", []), 1):
        if "error" in it:
            buf.append(f"[{i}] ERROR {it['file']}: {it['error']}")
            continue
        buf.append("=" * 68)
        buf.append(f"[{i}] {Path(it['file']).name}")
        if with_meta:
            meta = []
            if it.get("engine"):
                meta.append(f"引擎={it['engine']}")
            if it.get("category"):
                meta.append(f"分类={it['category']}({it.get('confidence')})")
            if it.get("line_count") is not None:
                meta.append(f"行数={it['line_count']}")
            if meta:
                buf.append("      " + " | ".join(meta))
        buf.append("=" * 68)
        buf.append(it.get("text", "") or "(无文字)")
        buf.append("")
    Path(out_path).write_text("\n".join(buf), encoding="utf-8")
    return str(out_path)


def export_md(payload, out_path):
    buf = ["# 图片识别结果\n"]
    group = {}
    for it in payload.get("results", []):
        if "error" in it:
            continue
        group.setdefault(it.get("category") or "未分类", []).append(it)

    for cat in sorted(group.keys()):
        buf.append(f"\n## {cat}  ({len(group[cat])} 张)\n")
        for it in group[cat]:
            name = Path(it["file"]).name
            buf.append(f"### {name}\n")
            if it.get("confidence"):
                buf.append(f"- 置信度: {it['confidence']}")
            if it.get("evidence"):
                buf.append(f"- 判据: {'; '.join(it['evidence'])}")
            buf.append("")
            buf.append("```")
            buf.append(it.get("text", "") or "(无文字)")
            buf.append("```\n")
    Path(out_path).write_text("\n".join(buf), encoding="utf-8")
    return str(out_path)


def export_docx(payload, out_path, embed_image=True):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    st = doc.styles["Normal"]
    cjk_name = cjk_font_for_docx()
    st.font.name = cjk_name
    st.font.size = Pt(10.5)
    # 中文字体需单独设置 eastasia
    try:
        from docx.oxml.ns import qn
        st.element.rPr.rFonts.set(qn("w:eastAsia"), cjk_name)
    except Exception:
        pass

    h = doc.add_heading("图片识别报告", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    results = [r for r in payload.get("results", []) if "error" not in r]
    errs = [r for r in payload.get("results", []) if "error" in r]

    p = doc.add_paragraph()
    p.add_run(f"共处理 {len(results)} 张图片").bold = True
    if errs:
        p.add_run(f"，失败 {len(errs)} 张")

    for i, it in enumerate(results, 1):
        doc.add_heading(f"{i}. {Path(it['file']).name}", level=1)

        # 元信息表
        meta = [("来源", it["file"])]
        if it.get("category"):
            meta.append(("分类", f"{it['category']}  (置信度 {it.get('confidence')})"))
        if it.get("evidence"):
            meta.append(("分类判据", "; ".join(it["evidence"])))
        if it.get("engine"):
            meta.append(("识别引擎", it["engine"]))
        if it.get("line_count") is not None:
            meta.append(("文本行数", str(it["line_count"])))

        t = doc.add_table(rows=0, cols=2)
        t.style = "Light Grid Accent 1"
        for k, v in meta:
            row = t.add_row().cells
            row[0].text = k
            row[1].text = str(v)

        # 原图
        if embed_image:
            fp = Path(it["file"])
            if fp.is_file():
                try:
                    doc.add_paragraph().add_run("原图").bold = True
                    doc.add_picture(str(fp), width=Cm(14))
                except Exception as e:
                    doc.add_paragraph(f"(原图嵌入失败: {e})")

        # 识别文本
        doc.add_paragraph().add_run("识别文字").bold = True
        text = it.get("text", "") or ""
        if text:
            for ln in text.splitlines():
                if ln.strip():
                    doc.add_paragraph(ln)
        else:
            r = doc.add_paragraph("(未识别到文字)")
            r.runs[0].font.color.rgb = RGBColor(0x99, 0x99, 0x99)

        if i < len(results):
            doc.add_page_break()

    if errs:
        doc.add_heading("处理失败", level=1)
        for e in errs:
            doc.add_paragraph(f"{e['file']}: {e['error']}")

    doc.save(out_path)
    return str(out_path)


def export_xlsx(payload, out_path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    # --- Sheet1: 汇总 ---
    ws = wb.active
    ws.title = "汇总"
    headers = ["序号", "文件名", "分类", "置信度", "识别引擎", "文本行数",
               "字符数", "源文件路径"]
    ws.append(headers)
    thin = Side(style="thin", color="BBBBBB")
    hdr_fill = PatternFill("solid", fgColor="2F5597")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    idx = 0
    for it in payload.get("results", []):
        if "error" in it:
            continue
        idx += 1
        ws.append([
            idx, Path(it["file"]).name, it.get("category", ""),
            it.get("confidence", ""), it.get("engine", ""),
            it.get("line_count", 0), len(it.get("text", "") or ""),
            it["file"],
        ])

    widths = [6, 28, 16, 10, 12, 10, 10, 50]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=len(headers)):
        for cell in row:
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # --- Sheet2: 识别明细 (结构化表格) ---
    ws2 = wb.create_sheet("识别明细")
    ws2.append(["文件名", "分类", "行号", "列1", "列2", "列3", "列4"])
    for c in range(1, 8):
        cell = ws2.cell(1, c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center")

    for it in payload.get("results", []):
        if "error" in it:
            continue
        rows = _rows_from_item(it)
        name = Path(it["file"]).name
        for r_i, r in enumerate(rows, 1):
            maxc = max(len(r), 1)
            vals = [name if r_i == 1 else "", it.get("category", "") if r_i == 1 else "",
                    r_i] + (r + [""] * (4 - maxc))[:4]
            ws2.append(vals[:7])

    for i, w in enumerate([28, 16, 8, 22, 22, 22, 22], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"

    # --- Sheet3: 按分类统计 ---
    ws3 = wb.create_sheet("分类统计")
    ws3.append(["分类", "数量", "占比"])
    for c in range(1, 4):
        cell = ws3.cell(1, c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hdr_fill
    counts = {}
    for it in payload.get("results", []):
        if "error" in it:
            continue
        k = it.get("category") or "未分类"
        counts[k] = counts.get(k, 0) + 1
    total = sum(counts.values()) or 1
    for k in sorted(counts, key=lambda x: -counts[x]):
        ws3.append([k, counts[k], f"{counts[k]/total*100:.1f}%"])
    for i, w in enumerate([22, 10, 10], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    wb.save(out_path)
    return str(out_path)


def export_pdf(payload, out_path, embed_image=True):
    """用 reportlab 生成 PDF。中文字体优先用系统 msyh/SimSun"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, Image as RLImage,
                                    PageBreak)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 注册中文字体 (跨平台自动探测)
    font_name = "Helvetica"
    cjk = find_cjk_fonts()
    for fp, alias, _disp in cjk:
        try:
            pdfmetrics.registerFont(TTFont(alias, fp))
            font_name = alias
            break
        except Exception:
            continue

    styles = getSampleStyleSheet()
    body = ParagraphStyle("cnbody", parent=styles["Normal"], fontName=font_name,
                          fontSize=10, leading=16)
    h1 = ParagraphStyle("cnh1", parent=styles["Heading1"], fontName=font_name,
                        fontSize=16, leading=22, spaceAfter=10)
    h2 = ParagraphStyle("cnh2", parent=styles["Heading2"], fontName=font_name,
                        fontSize=12.5, leading=18, spaceBefore=10, spaceAfter=6,
                        textColor=colors.HexColor("#2F5597"))

    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="图片识别报告")

    story = [Paragraph("图片识别报告", h1),
             Paragraph(f"共处理 {len([r for r in payload.get('results', []) if 'error' not in r])} 张图片", body),
             Spacer(1, 0.5 * cm)]

    results = [r for r in payload.get("results", []) if "error" not in r]
    for i, it in enumerate(results, 1):
        story.append(Paragraph(f"{i}. {Path(it['file']).name}", h2))

        meta = []
        if it.get("category"):
            meta.append(["分类", f"{it['category']} (置信度 {it.get('confidence')})"])
        if it.get("evidence"):
            meta.append(["判据", "; ".join(it["evidence"])])
        if it.get("engine"):
            meta.append(["引擎", str(it["engine"])])
        if it.get("line_count") is not None:
            meta.append(["行数", str(it["line_count"])])
        if meta:
            t = Table(meta, colWidths=[2.6 * cm, 14 * cm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF3FB")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.25 * cm))

        if embed_image:
            fp = Path(it["file"])
            if fp.is_file():
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(fp) as pim:
                        w, h = pim.size
                    maxw = 14 * cm
                    maxh = 9 * cm
                    ratio = min(maxw / w, maxh / h)
                    story.append(RLImage(str(fp), width=w * ratio, height=h * ratio))
                    story.append(Spacer(1, 0.25 * cm))
                except Exception:
                    pass

        text = it.get("text", "") or "(未识别到文字)"
        for ln in text.splitlines():
            if ln.strip():
                esc = (ln.replace("&", "&amp;").replace("<", "&lt;")
                         .replace(">", "&gt;"))
                story.append(Paragraph(esc, body))
        if i < len(results):
            story.append(PageBreak())

    doc.build(story)
    return str(out_path)


# ------------------------------------------------------------------- CLI

FORMATS = {
    "docx": export_docx,
    "xlsx": export_xlsx,
    "pdf": export_pdf,
    "txt": export_txt,
    "md": export_md,
}


def main():
    ap = argparse.ArgumentParser(description="识别结果导出为 Office/PDF/TXT")
    ap.add_argument("input", help="识别结果 JSON (ocr.py / classify.py 产物)")
    ap.add_argument("--to", required=True,
                    help="输出格式, 可多选逗号分隔: " + ",".join(FORMATS))
    ap.add_argument("--out", default=None, help="输出文件路径 (单格式) 或目录 (多格式)")
    ap.add_argument("--no-image", action="store_true", help="不嵌入原图")
    args = ap.parse_args()

    payload = load_payload(args.input)
    fmts = [f.strip().lower() for f in args.to.split(",") if f.strip()]
    bad = [f for f in fmts if f not in FORMATS]
    if bad:
        print(f"[错误] 不支持的格式: {bad}. 可选: {list(FORMATS)}", file=sys.stderr)
        return 1

    src_stem = Path(args.input).stem
    outs = []
    for f in fmts:
        if args.out and len(fmts) == 1:
            dst = Path(args.out)
        elif args.out:
            Path(args.out).mkdir(parents=True, exist_ok=True)
            dst = Path(args.out) / f"{src_stem}.{f}"
        else:
            dst = Path(args.input).parent / f"{src_stem}.{f}"
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            if f in ("docx", "pdf"):
                p = FORMATS[f](payload, str(dst), embed_image=not args.no_image)
            else:
                p = FORMATS[f](payload, str(dst))
            outs.append(p)
            print(f"[OK] {f:5s} -> {p}  ({human_size(Path(p).stat().st_size)})")
        except Exception as e:
            print(f"[FAIL] {f}: {e}", file=sys.stderr)
    return 0 if outs else 1


if __name__ == "__main__":
    sys.exit(main())
