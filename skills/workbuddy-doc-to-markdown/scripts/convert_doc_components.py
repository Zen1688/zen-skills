# -*- coding: utf-8 -*-
"""WorkBuddy 云上文档组件标记 -> Markdown 转换器。

用法:
    python convert_doc_components.py <input.txt> <output.md>

input.txt:  `doc/get_doc_reviews.py --page-id <id>` 的完整 stdout
            （首行可为 KS_DOC_REVIEWS 回执行，会自动剔除）
output.md:  落地文件，UTF-8 无 BOM / LF 换行
"""
import re
import sys

TAG_RE = re.compile(r'^(\s*)<([A-Z][A-Za-z0-9]*)((?:\s[^>]*)?)>\s*$')
CLOSE_RE = re.compile(r'^(\s*)</([A-Z][A-Za-z0-9]*)>\s*$')
MARK_RE = re.compile(r'<Mark(?:\s[^>]*)?>(.*?)</Mark>', re.S)
ESCAPE_RE = re.compile(r'\\([_*\[\]()#+\-.!~|{}>`])')
INLINE_TAGS = {"Mark", "Label", "Link", "InlineCode", "Paragraph"}


class Node:
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = attrs
        self.children = []
        self.raw = None


def parse(text):
    """按缩进建树；Code 节点整体截取，内部不做解析。"""
    lines = text.split("\n")
    root = Node("root", "")
    stack = [(root, -1)]
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = TAG_RE.match(line)
        if m:
            indent, tag, attrs = len(m.group(1)), m.group(2), m.group(3)
            if tag == "Code":
                buf, j = [], i + 1
                while j < len(lines):
                    cm = CLOSE_RE.match(lines[j])
                    if cm and cm.group(2) == "Code":
                        break
                    buf.append(lines[j])
                    j += 1
                while len(stack) > 1 and indent <= stack[-1][1]:
                    stack.pop()
                node = Node("Code", attrs)
                node.raw = "\n".join(buf)
                stack[-1][0].children.append(node)
                i = j + 1
                continue
            node = Node(tag, attrs)
            while len(stack) > 1 and indent <= stack[-1][1]:
                stack.pop()
            stack[-1][0].children.append(node)
            if not attrs.rstrip().endswith("/"):   # 自闭合（如 <Divider />）
                stack.append((node, indent))
            i += 1
            continue
        cm = CLOSE_RE.match(line)
        if cm:
            indent = len(cm.group(1))
            while len(stack) > 1 and indent <= stack[-1][1]:
                stack.pop()
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        while len(stack) > 1 and indent <= stack[-1][1]:
            stack.pop()
        stack[-1][0].children.append(line.strip())
        i += 1
    return root


def unescape(s):
    """行内 <Mark> -> **粗体**；还原 \\_ \\* 等 Markdown 转义。"""
    while MARK_RE.search(s):
        s = MARK_RE.sub(lambda m: "**" + m.group(1).strip() + "**", s)
    return ESCAPE_RE.sub(r'\1', s)


def inline_of(node, join="\n"):
    parts = []
    for c in node.children:
        if isinstance(c, str):
            if c.endswith("\\"):        # 行尾反斜杠 = 软换行
                parts.append(c[:-1])
                parts.append("\n")
            else:
                parts.append(c)
        elif c.tag == "Mark":
            parts.append("**" + inline_of(c, join=" ") + "**")
        elif c.tag == "Code":
            parts.append(c.raw or "")
        else:
            parts.append(inline_of(c, join=join))
    return unescape("".join(parts))


def item_text(it):
    """列表项文本：只取行内子节点，块级子节点另行渲染（防重复）。"""
    parts = []
    for c in it.children:
        if isinstance(c, str):
            parts.append(c)
        elif c.tag in INLINE_TAGS:
            parts.append(inline_of(c, join=" "))
    return unescape("".join(parts)).strip()


def dedent(raw):
    lines = raw.split("\n")
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(l[cut:] if len(l) >= cut else l for l in lines)


def render_table(node):
    rows = []
    for tr in node.children:
        if isinstance(tr, Node) and tr.tag == "TableRow":
            cells = []
            for tc in tr.children:
                if isinstance(tc, Node) and tc.tag == "TableCell":
                    txt = inline_of(tc, join=" ").replace("\n", "<br>").strip()
                    cells.append(txt.replace("|", "\\|"))
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def render(nodes):
    out = []
    i = 0
    while i < len(nodes):
        n = nodes[i]
        if isinstance(n, str):
            i += 1
            continue
        tag = n.tag
        if tag == "Heading":
            lv = int(re.search(r'level="(\d+)"', n.attrs).group(1))
            out.append("#" * lv + " " + inline_of(n, join=" ").strip())
        elif tag == "Paragraph":
            out.append(inline_of(n))
        elif tag == "Divider":
            out.append("---")
        elif tag == "Code":
            out.append(dedent(n.raw or "").strip("\n"))
        elif tag == "BlockQuote":
            inner = render(n.children)
            out.append("\n".join(("> " + l) if l.strip() else ">" for l in inner.split("\n")))
        elif tag == "Todo":
            out.append("- [ ] " + inline_of(n, join=" ").strip())
        elif tag == "Table":
            out.append(render_table(n))
        elif tag in ("NumberedList", "BulletedList"):
            ordered = tag == "NumberedList"
            items = []
            while i < len(nodes) and isinstance(nodes[i], Node) and nodes[i].tag == tag:
                items.append(nodes[i])
                i += 1
            i -= 1
            lines = []
            for idx, it in enumerate(items):
                lines.append(("%d. " % (idx + 1) if ordered else "- ") + item_text(it))
                for c in it.children:
                    if isinstance(c, Node) and c.tag not in INLINE_TAGS:
                        sub = render([c])
                        lines.extend(("    " + l).rstrip() for l in sub.split("\n"))
            out.append("\n".join(lines))
        else:
            sub = render(n.children)
            if sub.strip():
                out.append(sub)
        i += 1
    return "\n\n".join(x for x in out if x.strip() != "")


def convert(raw):
    lines = [l for l in raw.split("\n") if not l.startswith("KS_")]
    raw = "\n".join(lines)
    fm = re.match(r'^---\s*\n(.*?)\n---\s*\n', raw, re.S)
    title = None
    if fm:
        tm = re.search(r'^title:\s*(.+)$', fm.group(1), re.M)
        title = tm.group(1).strip() if tm else None
        raw = raw[fm.end():]
    body = render(parse(raw).children)
    md = body.rstrip() + "\n"
    outside = re.sub(r'```.*?```', '', md, flags=re.S)
    leftovers = re.findall(r'</?[A-Z][A-Za-z]+(?:\s[^>]*)?/?>', outside)
    return title, md, leftovers


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    raw = open(sys.argv[1], encoding="utf-8").read()
    title, md, leftovers = convert(raw)
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("[OK] %s -> %s | title=%s | %d bytes | 残留标签 %d %s"
          % (sys.argv[1], sys.argv[2], title, len(md.encode("utf-8")),
             len(leftovers), sorted(set(leftovers)) or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
