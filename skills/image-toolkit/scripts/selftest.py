#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自检脚本 —— 验证 image-toolkit 是否真的可离线使用

不依赖任何外部图片: 先用 Pillow 现场合成一张带中文的测试图,
再跑完整链路 (合成图 -> OCR -> 分类 -> 导出 Office), 最后清理临时文件。

用途:
  1. 离线部署后确认安装成功 (deploy_offline.py install 会自动调用)
  2. 日常排查环境问题
  3. 换机器后快速验证

用法:
  python selftest.py            # 完整自检
  python selftest.py --keep     # 保留临时文件以便排查
  python selftest.py --quick    # 只检查依赖, 不做端到端
"""
import argparse
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 首次调用时自动补齐依赖。**必须早于任何重依赖导入** ——
# 依赖缺失时会切到已就绪的解释器重跑本脚本。
from bootstrap import ensure_and_reexec  # noqa: E402
ensure_and_reexec(need_ocr=True, on_fail="continue")

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []


def record(name, status, detail=""):
    results.append((name, status, detail))
    icon = {PASS: "\u2713", FAIL: "\u2717", SKIP: "-"}[status]
    line = f"  {icon} {name}"
    if detail:
        line += f"  ({detail})"
    print(line)


# ============================================================ 各项检查

def check_deps():
    """检查核心依赖是否可导入"""
    mods = [
        ("PIL", "Pillow", "图像处理"),
        ("openpyxl", "openpyxl", "Excel"),
        ("docx", "python-docx", "Word"),
        ("reportlab", "reportlab", "PDF"),
        ("numpy", "numpy", "特征计算"),
    ]
    missing = []
    for mod, pkg, desc in mods:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        record("核心依赖", FAIL, f"缺少: {', '.join(missing)}")
        return False
    record("核心依赖", PASS, f"{len(mods)} 项齐全")
    return True


def check_ocr_engine():
    """检查 OCR 引擎可用性"""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        record("OCR 引擎", PASS, "RapidOCR")
        return "rapidocr"
    except ImportError:
        pass
    try:
        from common import find_tesseract
        exe = find_tesseract()
        import pytesseract  # noqa: F401
        if exe:
            record("OCR 引擎", PASS, f"Tesseract ({exe})")
            return "tesseract"
        record("OCR 引擎", FAIL, "pytesseract 已装但缺 tesseract 可执行文件")
        return None
    except ImportError:
        record("OCR 引擎", FAIL, "无可用引擎: 请装 rapidocr-onnxruntime")
        return None


def check_fonts():
    """检查中文字体"""
    from common import find_cjk_fonts, cjk_font_for_docx
    fonts = find_cjk_fonts()
    if not fonts:
        record("中文字体", FAIL, "未找到, PDF/Word 中文可能乱码")
        return False
    names = ", ".join(f[1] for f in fonts[:3])
    record("中文字体", PASS, f"{names} -> Word 用 {cjk_font_for_docx()}")
    return True


def make_sample_image(path):
    """合成一张含中文与典型单据特征的测试图 (不依赖外部素材)"""
    from PIL import Image, ImageDraw, ImageFont
    from common import find_cjk_fonts

    font = None
    for fp, _alias, _disp in find_cjk_fonts():
        try:
            font = ImageFont.truetype(fp, 24)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    W, H = 900, 560
    im = Image.new("RGB", (W, H), (253, 251, 246))
    d = ImageDraw.Draw(im)
    d.rectangle([8, 8, W - 8, H - 8], outline=(120, 90, 60), width=3)

    big = font
    try:
        from PIL import ImageFont as IF
        for fp, _a, _d in find_cjk_fonts():
            try:
                big = IF.truetype(fp, 30)
                break
            except Exception:
                continue
    except Exception:
        pass

    d.text((280, 28), "自检测试发票", font=big, fill=(90, 60, 40))
    rows = [
        ("发票代码", "011002100311"),
        ("发票号码", "08876655"),
        ("开票日期", "2026年09月14日"),
        ("纳税人识别号", "91110108MA01ABCD2X"),
        ("价税合计", "13250.00"),
        ("税额", "750.00"),
        ("校验码", "4123 5678 9012"),
    ]
    y = 100
    for k, v in rows:
        d.text((45, y), k, font=font, fill=(40, 40, 40))
        d.text((300, y), v, font=font, fill=(20, 20, 100))
        y += 42
    im.save(path)
    return str(path)


def run_e2e(tmp):
    """端到端: 合成图 -> OCR -> 分类 -> 导出三种 Office 格式"""
    import ocr as ocr_mod
    import classify as cls_mod
    import export as exp_mod

    # 1) 合成测试图
    img = tmp / "selftest_invoice.png"
    make_sample_image(img)
    record("合成测试图", PASS, img.name)

    # 2) OCR
    try:
        res = ocr_mod.recognize(img)
    except Exception as e:
        record("OCR 识别", FAIL, str(e))
        return False
    if res["line_count"] == 0:
        record("OCR 识别", FAIL, "未识别到任何文字")
        return False
    # 关键: 中文是否被正确识别 (能读到「发票」即说明中文模型工作正常)
    hit_cn = "发票" in (res["text"] or "")
    record("OCR 识别", PASS if hit_cn else FAIL,
           f"{res['line_count']} 行, 中文{'正常' if hit_cn else '异常'}")
    if not hit_cn:
        return False

    # 3) 分类
    try:
        feats = cls_mod.image_features(img)
        c = cls_mod.classify_one(res["text"], feats, res["line_count"])
    except Exception as e:
        record("内容分类", FAIL, str(e))
        return False
    record("内容分类", PASS, f"-> {c['label']} ({c['score']})")

    # 4) 导出 (模拟真实使用)
    payload = {"results": [res], "count": 1, "failed": 0}
    res["category"] = c["label"]
    res["confidence"] = c["score"]
    res["evidence"] = c["evidence"]

    for fmt, fn in [
        ("docx", lambda p, d: exp_mod.export_docx(p, d, embed_image=True)),
        ("xlsx", exp_mod.export_xlsx),
        ("pdf", lambda p, d: exp_mod.export_pdf(p, d, embed_image=True)),
    ]:
        dst = tmp / f"selftest_out.{fmt}"
        try:
            fn(payload, str(dst))
            size = dst.stat().st_size
            if size < 1024:
                record(f"导出 {fmt}", FAIL, f"文件过小 ({size}B)")
                return False
            record(f"导出 {fmt}", PASS, f"{size / 1024:.1f}KB")
        except Exception as e:
            record(f"导出 {fmt}", FAIL, str(e))
            return False

    return True


def check_offline():
    """验证无网络调用: 禁用 socket 后跑一次关键路径"""
    import socket
    orig = socket.socket
    blocked = []

    def ban(*a, **k):
        blocked.append(1)
        raise RuntimeError("网络被禁用 (自检)")

    socket.socket = ban
    socket.create_connection = ban
    socket.getaddrinfo = ban
    try:
        import ocr as ocr_mod
        tmp = Path(tempfile.mkdtemp(prefix="imgtk_offline_"))
        try:
            img = make_sample_image(tmp / "off.png")
            res = ocr_mod.recognize(img)
            if blocked:
                record("离线验证", FAIL, f"检测到 {len(blocked)} 次网络调用")
                return False
            record("离线验证", PASS, "禁用网络后 OCR 正常")
            return True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        record("离线验证", FAIL, str(e))
        return False
    finally:
        socket.socket = orig


# ============================================================ 主流程

def main():
    ap = argparse.ArgumentParser(description="image-toolkit 自检")
    ap.add_argument("--keep", action="store_true", help="保留临时文件")
    ap.add_argument("--quick", action="store_true", help="只检查依赖, 不跑端到端")
    args = ap.parse_args()

    print("=" * 62)
    print("  image-toolkit 自检")
    print("=" * 62)

    import platform
    print(f"  平台: {platform.system()} {platform.machine()} / "
          f"Python {platform.python_version()}")
    print()

    ok_deps = check_deps()
    engine = check_ocr_engine()
    check_fonts()

    if args.quick:
        _summary()
        return 0 if ok_deps else 1

    if not ok_deps:
        print("\n  核心依赖缺失, 跳过端到端测试")
        _summary()
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="imgtk_selftest_"))
    try:
        e2e_ok = run_e2e(tmp) if engine else False
        if not engine:
            record("端到端流程", SKIP, "无 OCR 引擎")
        check_offline()
    except Exception:
        print("\n  自检过程异常:")
        traceback.print_exc()
        e2e_ok = False
    finally:
        if args.keep:
            print(f"\n  临时文件保留在: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    return _summary()


def _summary():
    print("\n" + "=" * 62)
    n_pass = sum(1 for _, s, _ in results if s == PASS)
    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_skip = sum(1 for _, s, _ in results if s == SKIP)
    print(f"  结果: {n_pass} 通过, {n_fail} 失败, {n_skip} 跳过")

    if n_fail == 0:
        print("  \u2713 自检通过 —— 环境可用")
    else:
        print("  \u2717 自检未通过, 失败项:")
        for name, s, detail in results:
            if s == FAIL:
                print(f"      {name}: {detail}")
        print("\n  排查建议:")
        print("    - 依赖缺失 -> python deploy_offline.py install 或 setup_env.py")
        print("    - 字体缺失 -> Linux: sudo apt install fonts-wqy-microhei")
        print("    - 中文识别异常 -> 确认用 RapidOCR 引擎")
    print("=" * 62)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
