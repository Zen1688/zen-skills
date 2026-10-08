#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成套文档架构级审阅的机械核验工具。

子命令：
  metrics  <dir>                        结构密度基线（行/章/节/表格行/代码块/行每章）
  refs     <dir>                        穷尽抓取交叉引用，供逐条回查目标是否存在
  terms    <dir> <dict_file> [--words ..]  术语覆盖矩阵（正文出现但词典未收录）
  versions <dir>                        抓出全部版本号写法，供时效核验

用法示例：
  python audit_checks.py metrics  ./docs
  python audit_checks.py refs     ./docs
  python audit_checks.py terms    ./docs ./docs/04-dict.md --words SmoothQuant,MLA
  python audit_checks.py versions ./docs
"""
import argparse
import os
import re
import sys
from pathlib import Path

MD = "*.md"

# ---------- metrics ----------

def cmd_metrics(d: Path):
    files = sorted(d.glob(MD))
    if not files:
        print("未找到 .md 文件"); return 1
    print("%-34s %7s %6s %6s %8s %7s %8s" %
          ("文件", "总行", "二级章", "三级节", "表格行", "代码块", "行/章"))
    print("-" * 84)
    for f in files:
        t = f.read_text(encoding="utf-8")
        lines = t.split("\n")
        h2 = sum(1 for l in lines if l.startswith("## "))
        h3 = sum(1 for l in lines if l.startswith("### "))
        tb = sum(1 for l in lines if l.startswith("|"))
        code = t.count("```") // 2
        # 只统计"章"级标题：## 第 N 章 / ## 第N章 / ## Chapter
        ch = sum(1 for l in lines if re.match(r"^##\s*(第\s*[0-9一二三四五六七八九十]+\s*[章讲]|Chapter)", l))
        dens = ("%.0f" % (len(lines) / ch)) if ch else "—"
        print("%-34s %7d %6d %6d %8d %7d %8s" %
              (f.name, len(lines), h2, h3, tb, code, dens))
    print("\n提示：各分册「行/章」相差 2 倍以上 = 信息密度失衡，通常说明有的册子在压缩。")
    return 0


# ---------- refs ----------

REF_PATTERNS = [
    r"见第\s*[0-9]+\s*[章节]",
    r"见\s*第?\s*[0-9]+(\.[0-9]+)+\s*节?",
    r"详见[^。；\n]{0,30}",
    r"见(提高篇|入门篇|精通篇|上篇|下篇|前文|后文)[^。；\n]{0,20}",
    r"对应[^。；\n]{0,6}(篇|章|节)[^。；\n]{0,10}",
    r"参见[^。；\n]{0,25}",
]

def cmd_refs(d: Path):
    pat = re.compile("|".join("(?:%s)" % p for p in REF_PATTERNS))
    total = 0
    for f in sorted(d.glob(MD)):
        hits = []
        for i, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            for m in pat.finditer(l):
                hits.append((i, m.group().strip()))
        if hits:
            print("=== %s" % f.name)
            for i, g in hits:
                print("  L%-6d %s" % (i, g))
            total += len(hits)
    print("\n共 %d 条引用。**逐条回原文确认目标章节真实存在**——"
          "失效引用（承诺了但没写）是迭代中最容易漏的缺陷。" % total)
    return 0


# ---------- terms ----------

def cmd_terms(d: Path, dict_file: Path, words):
    body_files = [f for f in sorted(d.glob(MD)) if f.resolve() != dict_file.resolve()]
    body = "".join(f.read_text(encoding="utf-8") for f in body_files)
    dic = dict_file.read_text(encoding="utf-8").lower()

    if not words:
        # 自动候选：抓正文里"首字母大写且非句首的英文串"，按出现次数排序
        cand = re.findall(r"(?<![A-Za-z0-9_])([A-Z][A-Za-z0-9]{2,}(?:-[A-Za-z0-9]+)*)", body)
        from collections import Counter
        words = [w for w, c in Counter(cand).most_common(120)]

    print("%-26s %8s  %s" % ("术语", "正文次数", "词典"))
    print("-" * 48)
    missing = []
    for w in words:
        n = body.count(w)
        has = w.lower() in dic
        if n and not has:
            missing.append(w)
        print("%-26s %8d  %s" % (w, n, "有" if has else "缺"))
    print("\n正文出现但词典未收录（按出现次数）：")
    for w in sorted(missing, key=lambda x: -body.count(x)):
        print("  %-24s %d 次" % (w, body.count(w)))
    print("\n提示：出现 1 次的专有名词最容易被漏——它们往往不是核心概念，"
          "但正是词典「收录全部名词」承诺的边界。")
    return 0


# ---------- versions ----------

VER_PATTERNS = [
    r"\b[vV]?[0-9]+\.[0-9]+(\.[0-9]+)?\b",
    r"\b[0-9]+\.x\b",
    r"[0-9]+\.[0-9]+(\.[0-9]+)?\+",
]

def cmd_versions(d: Path):
    pat = re.compile("|".join(VER_PATTERNS))
    for f in sorted(d.glob(MD)):
        seen = {}
        for i, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            for m in pat.finditer(l):
                seen.setdefault(m.group(), []).append(i)
        if seen:
            print("=== %s" % f.name)
            for v, ls in sorted(seen.items(), key=lambda kv: -len(kv[1])):
                loc = ",".join("L%d" % x for x in ls[:6]) + ("…" if len(ls) > 6 else "")
                print("  %-12s ×%-3d %s" % (v, len(ls), loc))
    print("\n把这份清单与文档开头声明的「撰写基线年月」对照："
          "基线越新、版本号越旧，说明内容实际锚定在过去。再用 WebSearch 核实 2~3 个关键项。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="成套文档架构级审阅-机械核验")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("metrics");  p.add_argument("dir")
    p = sub.add_parser("refs");     p.add_argument("dir")
    p = sub.add_parser("terms");    p.add_argument("dir"); p.add_argument("dict")
    p.add_argument("--words", default="")
    p = sub.add_parser("versions"); p.add_argument("dir")

    a = ap.parse_args()
    d = Path(a.dir)
    if not d.is_dir():
        print("目录不存在：%s" % d); return 2

    if a.cmd == "metrics":
        return cmd_metrics(d)
    if a.cmd == "refs":
        return cmd_refs(d)
    if a.cmd == "terms":
        words = [w.strip() for w in a.words.split(",") if w.strip()]
        return cmd_terms(d, Path(a.dict), words)
    if a.cmd == "versions":
        return cmd_versions(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
