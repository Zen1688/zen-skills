#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mdmerge_pdf.py —— 把多个 Markdown 按顺序合并成一本带总纲目录的 PDF。

设计目标
--------
1. 中文友好：A4 排版、中文字体栈、表格 / 代码块保留。
2. 目录带**真实页码**：两遍打印法（第一遍占位 → 提取页码 → 回填 → 第二遍出片）。
3. 零手工后处理：篇 / 章 / 节自动编号打锚点，目录内可点击跳转。
4. 通用：不依赖任何具体项目的文件命名。

用法
----
    python mdmerge_pdf.py -o 合订本.pdf \
        -t "AI 工程师成长手册" -s "Java 工程师转型版 · 合订本" \
        -m "面向 5 年以上 Java 后端工程师" -m "内容快照 2025~2026" \
        01-入门篇.md 02-提高篇.md::提高篇 03-精通篇.md 04-词典.md::附录 · AI 名词词典

    # 用自定义卷首（front.md 中放 <!--TOC--> 作为目录占位）
    python mdmerge_pdf.py -o out.pdf --front-md front.md a.md b.md

    # 只要两级目录、不标页码、指定渲染引擎
    python mdmerge_pdf.py -o out.pdf --toc-depth 2 --no-page-number --engine chrome a.md b.md

输入说明
--------
- 每个输入文件视为一篇（part）。文件内 `# 标题` 作为篇标题；
  若文件没有 `# 级标题`，自动用文件名生成一个。
- 用 `路径::标题` 可覆盖该篇的标题（例如把 `04-词典.md` 显示为「附录 · AI 名词词典」）。
- 篇内 `## ` = 章（进目录、标页码、章前分页），`### ` = 节（进目录，不标页码）。

依赖
----
首次运行自动 pip 安装 `markdown` 与 `pypdf`（装到当前解释器环境）。
渲染引擎自动探测 Microsoft Edge / Google Chrome / Chromium（本机若无，用 --engine 指定绝对路径）。
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSS = os.path.join(HERE, os.pardir, 'assets', 'print.css')

FALLBACK_HEAD = ('<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">\n'
                 '<title>%s</title>\n<style>%s</style></head>\n<body>\n')

# ---------------------------------------------------------------- 依赖自举
def ensure_import(pkg, mod=None):
    mod = mod or pkg
    try:
        return __import__(mod)
    except ImportError:
        sys.stderr.write('[bootstrap] 安装依赖 %s ...\n' % pkg)
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', pkg])
        return __import__(mod)


# ---------------------------------------------------------------- 引擎探测
def detect_engine(explicit=None):
    if explicit:
        p = explicit.lower()
        alias = {
            'edge': [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                     r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'],
            'chrome': [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                       r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                       '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
        }
        cands = alias.get(p, [explicit])
    else:
        cands = [
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ]
        for b in ('chromium', 'chromium-browser', 'google-chrome', 'chrome'):
            w = shutil.which(b)
            if w:
                cands.append(w)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


# ---------------------------------------------------------------- 文本工具
def plain(text):
    """去掉 markdown 强调/代码符号，得到纯文本（用于目录与页码匹配）"""
    return re.sub(r'[*_`]', '', text).strip()


def norm(s):
    """去所有空白，用于抗换行的子串匹配"""
    return re.sub(r'\s+', '', s)


# ---------------------------------------------------------------- 合并主体
def build_parts(inputs):
    """读取并预处理各篇，返回 (合并 markdown, 目录树, 文件名→锚点 映射)"""
    parts, toc, fname2id = [], [], {}
    for pi, spec in enumerate(inputs, 1):
        if '::' in spec and os.path.exists(spec.split('::')[0]):
            path, override = spec.split('::', 1)
        else:
            path, override = spec, None
        path = os.path.abspath(path)
        if not os.path.exists(path):
            sys.exit('!! 输入文件不存在：%s' % path)
        text = io.open(path, encoding='utf-8').read()
        lines = text.split('\n')

        # 篇内若无 H1，按文件名补一个
        has_h1 = any(re.match(r'^# .+', l) for l in lines if not l.startswith('```'))
        if not has_h1:
            fname = os.path.splitext(os.path.basename(path))[0]
            lines.insert(0, '# %s\n' % fname)

        ch = sec = 0
        in_fence = False
        for i, ln in enumerate(lines):
            # ★ 关键：代码块内的 `# 注释` / `// [形态：…]` 绝不是标题
            if ln.lstrip().startswith('```') or ln.lstrip().startswith('~~~'):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = re.match(r'^(#{1,3}) (.+)$', ln)
            if not m:
                continue
            lvl, title = len(m.group(1)), m.group(2).strip()
            if lvl == 1:
                if override:
                    title = override
                tid = 'part-%d' % pi
                ch = sec = 0
                fname2id[os.path.basename(path)] = tid
            elif lvl == 2:
                ch += 1
                sec = 0
                tid = 'part-%d-ch-%d' % (pi, ch)
            else:
                sec += 1
                tid = 'part-%d-ch-%d-sec-%d' % (pi, ch, sec)
            lines[i] = '%s %s {#%s}' % (m.group(1), title, tid)
            toc.append((lvl, plain(title), tid))
        parts.append('\n'.join(lines))
    return '\n\n---\n\n'.join(parts), toc, fname2id


def fix_links(md, fname2id):
    """合并后失效的相对 md 链接：能映射的转内部锚点，不能映射的降级为纯文本"""
    def repl(m):
        label, target = m.group(1), m.group(2)
        base = os.path.basename(target.split('#')[0])
        if base in fname2id:
            return '[%s](#%s)' % (label, fname2id[base])
        return label     # 目标不在本合订本内 → 去掉链接，保留文字
    return re.sub(r'\[([^\]]+)\]\(([^)]+\.md[^)]*)\)', repl, md)


def toc_html(toc, pages, depth):
    out, pending = [], []

    def flush():
        if pending:
            out.append('<div class="toc-secs">' + ''.join(
                '<div>%s</div>' % s for s in pending) + '</div>')
            pending.clear()

    for lvl, text, tid in toc:
        if lvl > depth:
            continue
        if lvl == 3:
            pending.append('<a href="#%s">%s</a>' % (tid, text))
            continue
        flush()
        pg = (pages or {}).get(tid)
        pgs = '<span class="pg">%s</span>' % (pg if pg else '000')
        cls = 'toc-l1' if lvl == 1 else 'toc-l2'
        out.append('<div class="toc-row %s"><a href="#%s">%s</a>%s</div>'
                   % (cls, tid, text, pgs))
    flush()
    return '\n'.join(out)


def default_front(args):
    """生成默认卷首：封面 + 总纲说明 + 目录占位"""
    cover = ''
    if args.title:
        meta = ''.join('<br/>%s' % m for m in args.meta)
        cover = ('<div class="cover">\n<h1 class="no-break">%s</h1>\n'
                 '<div class="sub">%s</div>\n<div class="meta">%s</div>\n'
                 '<div class="badge">%s</div>\n</div>\n'
                 % (args.title, args.subtitle or '', meta,
                    args.badge or '合订本'))
    return cover + '\n<h1 class="no-break" id="front">总纲</h1>\n\n<!--TOC-->\n'


def render(md):
    markdown = ensure_import('markdown')
    return markdown.markdown(md, extensions=['tables', 'fenced_code', 'attr_list',
                                             'sane_lists'])


def write_html(body_html, title, css_text, path):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(
        FALLBACK_HEAD % (title, css_text) + body_html + '\n</body></html>\n')


def print_pdf(engine, html_path, pdf_path):
    """Chromium 系 headless 打印。★ 输出路径必须绝对，否则会以浏览器安装目录为基准"""
    cmd = [engine, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
           '--run-all-compositor-stages-before-draw', '--virtual-time-budget=20000',
           '--user-data-dir=' + os.path.join(tempfile.gettempdir(), 'mdmerge-profile'),
           '--print-to-pdf=' + os.path.abspath(pdf_path),
           'file:///' + os.path.abspath(html_path).replace('\\', '/')]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=900)


def page_keys(toc, depth):
    """产出需要标页码的目录项 (tid, 匹配 key)"""
    ks = []
    for lvl, text, tid in toc:
        if lvl > depth or lvl == 3:
            continue
        ks.append((tid, norm(text)[:10]))
    return ks


def locate(pages_text_norm, key, start):
    for i in range(start, len(pages_text_norm)):
        if key in pages_text_norm[i]:
            return i + 1
    return None


def extract_texts(pdf_path):
    PdfReader = ensure_import('pypdf').PdfReader
    r = PdfReader(pdf_path)
    return [(p.extract_text() or '') for p in r.pages]


def main():
    ap = argparse.ArgumentParser(description='多 Markdown 合并为带目录的 PDF')
    ap.add_argument('inputs', nargs='+', help='输入 md，支持 路径::篇标题')
    ap.add_argument('-o', '--out', required=True, help='输出 PDF 路径')
    ap.add_argument('-t', '--title', default='', help='封面标题（留空则无封面）')
    ap.add_argument('-s', '--subtitle', default='', help='封面副标题')
    ap.add_argument('-m', '--meta', action='append', default=[], help='封面说明行（可重复）')
    ap.add_argument('--badge', default='合订本', help='封面徽标文字')
    ap.add_argument('--front-md', help='自定义卷首 markdown（含 <!--TOC--> 占位）')
    ap.add_argument('--toc-depth', type=int, default=3, choices=[1, 2, 3],
                    help='目录深度，默认 3（篇/章/节）')
    ap.add_argument('--no-page-number', action='store_true', help='目录不标页码（只打一遍）')
    ap.add_argument('--engine', help='渲染引擎：edge / chrome / 可执行文件绝对路径')
    ap.add_argument('--css', help='自定义打印 CSS 路径')
    ap.add_argument('--build-dir', help='中间产物目录，默认 <out>.build/')
    ap.add_argument('--clean', action='store_true', help='完成后删除中间产物')
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    build = os.path.abspath(args.build_dir or (out + '.build'))
    os.makedirs(build, exist_ok=True)

    engine = detect_engine(args.engine)
    if not engine:
        sys.exit('!! 未找到 Chromium 系浏览器（Edge/Chrome/Chromium），'
                 '请用 --engine 指定可执行文件路径')
    print('[engine] %s' % engine)

    css_path = args.css or DEFAULT_CSS
    css_text = (io.open(css_path, encoding='utf-8').read()
                if os.path.exists(css_path) else '')
    if not css_text:
        sys.stderr.write('[warn] 未找到 print.css，将使用浏览器默认样式\n')

    # 1) 合并 + 打锚点 + 修链接
    merged, toc, fname2id = build_parts(args.inputs)
    merged = fix_links(merged, fname2id)
    io.open(os.path.join(build, 'merged.md'), 'w', encoding='utf-8',
            newline='\n').write(merged)
    print('[merge] %d 篇，目录条目 %d 条' % (len(args.inputs), len(toc)))

    # 2) 卷首
    if args.front_md:
        front = io.open(args.front_md, encoding='utf-8').read()
    else:
        front = default_front(args)

    def assemble(pages):
        body = front.replace('<!--TOC-->', toc_html(toc, pages, args.toc_depth))
        return render(body + '\n\n' + merged)

    # 3) 第一遍：占位页码
    html_path = os.path.join(build, 'merged.html')
    write_html(assemble(None), args.title or '合订本', css_text, html_path)
    pass1 = os.path.join(build, 'pass1.pdf')
    print_pdf(engine, html_path, pass1)
    print('[pass1] %s（%.2f MB）' % (pass1, os.path.getsize(pass1) / 1048576))

    # 4) 提取页码（中文提取异常则自动降级为无页码）
    pages = {}
    if not args.no_page_number:
        texts = extract_texts(pass1)
        normed = [norm(t) for t in texts]
        keys = page_keys(toc, args.toc_depth)
        # 判定提取是否可用：直接看能否在页面文本里定位到标题（比统计字数可靠）
        probe = [k for _, k in keys[:3]]
        ok_extract = any(any(k in t for t in normed) for k in probe) if probe else False
        han = sum(1 for t in texts[:5] for c in t if '\u4e00' <= c <= '\u9fff')
        print('[pages] %d 页，前 5 页中文字符 %d，标题可定位 %s'
              % (len(texts), han, ok_extract))
        if ok_extract or han > 200:
            cur = 0
            for tid, key in keys:
                pg = locate(normed, key, cur)
                if pg:
                    pages[tid] = pg
                    cur = pg - 1
            total = len(page_keys(toc, args.toc_depth))
            print('[pages] 回填 %d / %d' % (len(pages), total))
            io.open(os.path.join(build, 'pages.json'), 'w', encoding='utf-8').write(
                json.dumps(pages, ensure_ascii=False, indent=1))
            if pages and len(pages) < total * 0.9:
                sys.stderr.write('[warn] 页码覆盖率过低，可增大 --build-dir 排查\n')
        else:
            sys.stderr.write('[warn] PDF 文本提取异常，目录退化为无页码\n')

    # 5) 第二遍：回填页码出片
    write_html(assemble(pages or None), args.title or '合订本', css_text, html_path)
    print_pdf(engine, html_path, out)
    print('[done] %s（%.2f MB）' % (out, os.path.getsize(out) / 1048576))

    # 6) 校验：页码是否因回填发生偏移
    if pages:
        texts2 = extract_texts(out)
        normed2 = [norm(t) for t in texts2]
        drift, miss = [], 0
        for tid, key in page_keys(toc, args.toc_depth):
            pg = locate(normed2, key, max(0, pages.get(tid, 1) - 2))
            if not pg:
                miss += 1
            elif abs(pg - pages[tid]) > 1:
                drift.append((tid, pages[tid], pg))
        print('[check] 页数 %d，页码偏移 >1 的条目 %d，未定位 %d'
              % (len(texts2), len(drift), miss))
        if drift:
            sys.stderr.write('[warn] 偏移样例：%s\n' % drift[:3])

    if args.clean:
        shutil.rmtree(build, ignore_errors=True)


if __name__ == '__main__':
    main()
