#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图片内容分类模块 —— 完全离线, 基于 OCR 文本 + 图像客观特征

两种模式:
  1. 内置业务分类 (默认): 发票/合同/证件/截图/表格/幻灯片/手写/图表/照片/其他
  2. 用户自定义分类: --rules rules.json  按关键字/特征命中打分

分类判据 = 文本关键字权重 + 图像特征 (长宽比/色彩丰富度/边缘密度/文字覆盖率)
每条结果给出置信度与命中判据, 便于人工复核。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import iter_images  # noqa: E402

try:
    from PIL import Image, ImageStat, ImageFilter
    import numpy as np
except ImportError:
    np = None


# ============================================================ 内置业务分类

# 每类: keywords(高权重词) / weak(低权重词) / veto(命中则排除)
BUILTIN_RULES = {
    "发票": {
        "keywords": ["发票代码", "发票号码", "开票日期", "价税合计", "纳税人识别号",
                     "销售方", "购买方", "税率", "税额", "增值税", "发票专用章",
                     "机器编号", "校验码"],
        "weak": ["金额", "合计", "¥", "元", "发票"],
        "veto": [],
    },
    "合同/协议": {
        "keywords": ["甲方", "乙方", "协议书", "本合同", "签订地点", "违约责任",
                     "合同编号", "法定代表人", "盖章", "生效日期", "条款"],
        "weak": ["协议", "约定", "签署", "双方", "权利", "义务"],
        "veto": [],
    },
    "证件/证照": {
        "keywords": ["身份证", "护照", "驾驶证", "营业执照", "统一社会信用代码",
                     "签发机关", "有效期限", "公民身份号码", "注册号"],
        "weak": ["证号", "有效期", "姓名", "性别", "民族"],
        "veto": ["发票代码"],
    },
    "表格/单据": {
        "keywords": ["序号", "合计", "小计", "备注", "单价", "数量", "金额",
                     "总计", "项目名称", "经办人"],
        "weak": ["名称", "单位", "日期"],
        "veto": [],
    },
    "幻灯片": {
        "keywords": ["目录", "议程", "Agenda", "CONTENTS", "汇报人", "演讲"],
        "weak": ["方案", "总结", "计划", "汇报"],
        "veto": ["发票代码", "甲方"],
    },
    "图表/数据可视化": {
        "keywords": ["同比", "环比", "增长率", "占比", "趋势", "单位: 万元",
                     "单位：万元", "%", "Q1", "Q2", "Q3", "Q4"],
        "weak": ["数据", "统计", "分析"],
        "veto": [],
    },
    "聊天/网页截图": {
        "keywords": ["发送", "朋友圈", "微信", "群聊", "http", "www.", ".com",
                     "登录", "搜索", "首页", "扫码"],
        "weak": ["点击", "分享", "关注", "评论", "回复"],
        "veto": [],
    },
    "手写笔记": {
        "keywords": [],
        "weak": [],
        "veto": [],
    },
    "照片": {
        "keywords": [],
        "weak": [],
        "veto": [],
    },
}


# ============================================================ 图像客观特征

def image_features(path):
    """提取图像客观特征"""
    with Image.open(path) as im:
        im.load()
        w, h = im.size
        n_frames = getattr(im, "n_frames", 1)
        mode = im.mode
        has_alpha = mode in ("RGBA", "LA") or (
            mode == "P" and "transparency" in im.info)

        rgb = im.convert("RGB")
        small = rgb.resize((min(w, 400), min(h, 400))) if max(w, h) > 400 else rgb

        feat = {
            "width": w, "height": h,
            "aspect_ratio": round(w / h, 3) if h else 0,
            "pixels": w * h,
            "mode": mode,
            "has_alpha": has_alpha,
            "frames": n_frames,
        }

        if np is not None:
            arr = np.asarray(small, dtype=np.float32)

            # 色彩丰富度: 唯一颜色数占比
            flat = arr.reshape(-1, 3).astype(np.uint8)
            uniq = len(np.unique(flat, axis=0))
            feat["color_richness"] = round(uniq / max(len(flat), 1), 4)

            # 饱和度 & 灰度倾向
            mx, mn = arr.max(axis=2), arr.min(axis=2)
            sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
            feat["mean_saturation"] = round(float(sat.mean()), 4)
            feat["is_grayscale_like"] = bool(sat.mean() < 0.06)

            # 亮度与对比度
            gray = arr.mean(axis=2)
            feat["mean_brightness"] = round(float(gray.mean()), 2)
            feat["contrast_std"] = round(float(gray.std()), 2)

            # 背景纯度: 边缘区域是否接近纯白/纯色
            edge = np.concatenate([
                gray[:max(1, h // 20)].ravel(),
                gray[-max(1, h // 20):].ravel(),
            ])
            feat["edge_uniformity"] = round(float(1 - min(edge.std() / 64, 1)), 3)

            # 二值化后暗像素占比 (近似文字覆盖率)
            thr = gray.mean() - 0.35 * gray.std()
            dark_ratio = float((gray < thr).mean())
            feat["dark_ratio"] = round(dark_ratio, 4)
        else:
            stat = ImageStat.Stat(small)
            feat["mean_saturation"] = -1
            feat["mean_brightness"] = round(sum(stat.mean) / 3, 2)
            feat["color_richness"] = -1
            feat["is_grayscale_like"] = (max(stat.mean) - min(stat.mean)) < 10
            gray = small.convert("L")
            feat["edge_uniformity"] = 0.5

        return feat


# ============================================================ 分类打分

def _text_signal(text, feats, ocr_line_count):
    """从文本+特征推导辅助信号"""
    text = text or ""
    n = len(text.strip())
    sig = {
        "text_len": n,
        "has_text": n > 0,
        "text_density": round(n / max(ocr_line_count, 1), 1) if n else 0,
        "digit_ratio": round(len(re.findall(r"\d", text)) / n, 3) if n else 0,
        "cjk_ratio": round(len(re.findall(r"[\u4e00-\u9fff]", text)) / n, 3) if n else 0,
    }
    return sig


def classify_one(text, feats, ocr_line_count=0, rules=None, threshold=0.25):
    """对单张图分类, 返回 (标签, 置信度, 判据列表)"""
    rules = rules or BUILTIN_RULES
    sig = _text_signal(text, feats, ocr_line_count)
    labels = []

    for label, spec in rules.items():
        kws = spec.get("keywords", [])
        weak = spec.get("weak", [])
        veto = spec.get("veto", [])

        if any(v in (text or "") for v in veto):
            continue

        hits, evidence = [], []
        strong = 0
        for k in kws:
            if k and k in (text or ""):
                strong += 1
                hits.append(k)
        if strong:
            evidence.append(f"命中强关键字 {strong} 个: {', '.join(hits[:5])}")

        wc = sum(1 for k in weak if k and k in (text or ""))
        if wc:
            evidence.append(f"命中弱关键字 {wc} 个")

        # 文本得分
        score = min(strong * 0.22, 0.75) + min(wc * 0.06, 0.18)

        # 图像特征补正
        if label == "照片":
            if not sig["has_text"] and feats.get("color_richness", 0) > 0.25:
                score = 0.8
                evidence.append("无文字 + 色彩丰富 -> 判定为照片")
            elif not sig["has_text"] and feats.get("mean_saturation", 0) > 0.2:
                score = 0.55
                evidence.append("无文字 + 高饱和 -> 倾向照片")
        if label == "表格/单据":
            if feats.get("edge_uniformity", 0) > 0.7 and sig["digit_ratio"] > 0.15:
                score += 0.15
                evidence.append("背景规整 + 数字占比高 -> 倾向表格")
        if label == "聊天/网页截图":
            ar = feats.get("aspect_ratio", 0)
            if ar < 0.85 and feats.get("edge_uniformity", 0) > 0.6:
                score += 0.12
                evidence.append("竖长构图 + 背景规整 -> 倾向手机截图")
        if label == "手写笔记":
            # OCR 置信度低但确有文字 -> 倾向手写
            if sig["has_text"] and 0 < ocr_line_count <= 12:
                score += 0.05
        if label == "证件/证照":
            ar = feats.get("aspect_ratio", 0)
            if 1.4 < ar < 1.8 and feats.get("edge_uniformity", 0) > 0.6:
                score += 0.1
                evidence.append("银行卡/证件比例 + 背景规整")

        score = min(score, 0.99)
        if score >= threshold:
            labels.append({
                "label": label,
                "score": round(score, 3),
                "evidence": evidence or ["弱特征综合"],
            })

    if not labels:
        # 兜底: 有文字但没匹配上
        fb = "文本密集文档" if sig["has_text"] else "未知图片"
        return {
            "label": fb, "score": 0.2,
            "evidence": [f"未命中内置规则 (文字 {sig['text_len']} 字)"],
            "alternatives": [],
        }

    labels.sort(key=lambda x: -x["score"])
    top = labels[0]
    return {
        "label": top["label"],
        "score": top["score"],
        "evidence": top["evidence"],
        "alternatives": labels[1:4],
        "signals": sig,
    }


# ============================================================ 自定义规则载入

def load_rules(path):
    """载入用户自定义分类规则
    格式:
    {
      "类名": {"keywords": [...], "weak": [...], "veto": [...]},
      ...
    }
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("规则文件应为 JSON 对象: {类名: {keywords:[], weak:[], veto:[]}}")
    norm = {}
    for k, v in data.items():
        if isinstance(v, list):
            norm[k] = {"keywords": v, "weak": [], "veto": []}
        elif isinstance(v, dict):
            norm[k] = {
                "keywords": v.get("keywords", []),
                "weak": v.get("weak", []),
                "veto": v.get("veto", []),
            }
        else:
            raise ValueError(f"类 '{k}' 的规则格式不正确")
    return norm


def main():
    ap = argparse.ArgumentParser(description="图片内容分类 (完全离线)")
    ap.add_argument("input", help="图片文件或目录")
    ap.add_argument("--ocr", default=None,
                    help="已识别的 OCR JSON (ocr.py --json --out 产物); 不传则自动现场识别")
    ap.add_argument("--rules", default=None, help="自定义规则 JSON 路径")
    ap.add_argument("--threshold", type=float, default=0.25, help="置信度阈值")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None, help="结果写入文件")
    args = ap.parse_args()

    src = Path(args.input)
    files = iter_images(src) if src.is_dir() else [src]

    # 载入 OCR 结果 (可选)
    ocr_map = {}
    if args.ocr:
        payload = json.loads(Path(args.ocr).read_text(encoding="utf-8"))
        for r in payload.get("results", []):
            ocr_map[str(r["file"])] = r

    rules = load_rules(args.rules) if args.rules else None

    import ocr as ocr_mod

    out = []
    for f in files:
        rec = ocr_map.get(str(f))
        if rec is None:
            try:
                rec = ocr_mod.recognize(f)
            except Exception as e:
                out.append({"file": str(f), "error": str(e)})
                continue
        try:
            feats = image_features(f)
        except Exception as e:
            out.append({"file": str(f), "error": f"特征提取失败: {e}"})
            continue

        c = classify_one(rec.get("text", ""), feats, rec.get("line_count", 0),
                         rules, args.threshold)
        out.append({
            "file": str(f),
            "category": c["label"],
            "confidence": c["score"],
            "evidence": c["evidence"],
            "alternatives": c.get("alternatives", []),
            "signals": c.get("signals", {}),
            "features": feats,
            "text_preview": (rec.get("text", "") or "")[:200],
        })

    if args.json or args.out:
        blob = json.dumps({"results": out, "count": len(out)},
                          ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(blob, encoding="utf-8")
            print(f"[已写入] {args.out} ({len(out)} 条)")
        else:
            print(blob)
    else:
        for r in out:
            if "error" in r:
                print(f"[ERR] {r['file']}: {r['error']}")
                continue
            print(f"\n{r['file']}")
            print(f"  分类: {r['category']}  (置信度 {r['confidence']})")
            print(f"  判据: {'; '.join(r['evidence'])}")
            if r["alternatives"]:
                alts = ", ".join(f"{a['label']}({a['score']})"
                                 for a in r["alternatives"])
                print(f"  备选: {alts}")

    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
