# 合并 Markdown → PDF：坑位与排查手册

按「出错概率 × 排查成本」排序。遇到问题先查这里，再改脚本。

## P0：代码块里的 `#` 注释被当成 Markdown 标题

**症状**：目录里冒出 `[形态：完整可运行]`、`1) 安装`、`4) 挂载 LoRA` 这类条目；
正文代码块里被塞进 `{#part-1-ch-3-sec-2}` 之类的锚点残留；章序号被代码块里的 `#` 反复重置。

**根因**：`# ` 在 Markdown 里就是一级标题，而 Python / Shell 注释同样以 `#` 开头。

**解法**：扫描标题时必须维护代码围栏状态（` ``` ` 或 `~~~` 成对切换），围栏内一律跳过。
脚本 `scripts/mdmerge_pdf.py` 的 `build_parts()` 已实现；改脚本时**不要**把这个判断删掉。

**自检**（改完必跑）：

```python
in_f = False
for ln in merged_md.split('\n'):
    if ln.lstrip().startswith('```'): in_f = not in_f; continue
    if in_f and '{#' in ln: print('污染:', ln)
```

## P0：`--print-to-pdf` 给了相对路径，PDF 不生成且不报错

**症状**：命令退出码 0，但目标 PDF 文件不存在。

**根因**：Chromium 以自身安装目录为基准解析相对路径（写到 `C:\Program Files (x86)\Microsoft\Edge\Application\` 去了）。

**解法**：HTML 与 PDF 路径一律传**绝对路径**，URL 用 `file:///` + 正斜杠。

```bash
msedge.exe --headless=new --print-to-pdf="D:/abs/out.pdf" "file:///D:/abs/in.html"
```

## P1：目录页码不准 / 回填后整体偏移

**机制**：脚本用**两遍打印**取真实页码——第一遍目录页写占位 `000`，打印后
用 pypdf 逐页提取文本定位每个标题所在页，第二遍把页码写回目录再打印一次。

**为什么占位符必须是 3 位**：页码从 `000` 变 `128` 时行数不变，目录页数才不会变，
否则回填后整本页码会集体偏移。`--toc-depth` 变化会改变目录长度，需要重跑两遍。

**匹配算法**：页面文本与标题 key 都做「去所有空白」处理后再做子串匹配，
以对抗 PDF 提取时的换行与空格抖动；标题 key 取前 10 个非空白字符。

**偏移排查**：脚本结束会打印 `[check] 页码偏移 >1 的条目 N`。若 N > 0：

- 检查是否改了 `--toc-depth`（目录长度变了 → 两遍都要重跑）；
- 检查是否有标题文本重复（两个章同名，顺序匹配会错位）；
- 用 `--build-dir` 保留中间产物，看 `pages.json` 与 `pass1.pdf`。

## P1：PDF 文本提取不出中文 → 目录退化成无页码

**症状**：`[warn] PDF 文本提取异常，目录退化为无页码`。

**判定**：脚本取前 5 页，统计汉字数；低于阈值即判定提取失败并自动降级（不中断出片）。

**处理**：安装 pypdf 新版本；或直接用 `--no-page-number` 明确跳过（目录仍可点击跳转）。

## P2：相对 md 链接在合订本里失效

**症状**：正文出现 `[README](./README.md)`，PDF 里点了没反应或跳到错误位置。

**处理**：脚本的 `fix_links()` 会把 `*.md` 链接按文件名映射到本合订本的篇锚点；
**不在输入列表中的目标自动降级为纯文字**（保留可读文本，去掉死链）。
有特殊映射需求时，直接改源 md，或用 `--front-md` 自己写卷首说明。

## P2：目录太长（几十页）

- 用 `--toc-depth 2` 只保留篇 / 章两级；
- 或改 `assets/print.css` 里 `.toc-secs` 的 `columns: 2` → `columns: 3`、字号调小；
- 节级条目默认不标页码，只为导航，不必追求完整。

## P2：表格与代码块的显示问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 表格里 `A \| B` 被拆成两列 | Markdown 转义竖线 | Python-Markdown 的 `tables` 扩展支持 `\|`，确认源 md 用的是反斜杠转义 |
| `List<String>` 在正文消失 | 裸尖括号被当 HTML 标签吞掉 | 源 md 里用反引号包住；脚本的 `tables`/`fenced_code` 已转义行内代码 |
| 长代码行被截断 | `pre` 未换行 | CSS 已设 `white-space: pre-wrap; overflow-wrap: anywhere`，勿改 |
| 表格跨页断行难读 | — | CSS 已设 `tr { page-break-inside: avoid; }` |

## P2：Linux / macOS 无中文字体，正文变方块

修改 `assets/print.css` 的 `body.font-family`，加入本机已装的中文字体，例如
`Noto Sans CJK SC`、`Source Han Sans SC`、`WenQuanYi Zen Hei`。
Windows 环境默认走 `Microsoft YaHei`，无需处理。

## P3：大文档打印超时

`print_pdf()` 的 `--virtual-time-budget=20000`（20 秒）与 `subprocess timeout=900`（15 分钟）。
数百页的合订本通常 1~3 分钟出片；超时先改这两个值，再考虑拆分输入。

## P3：章前分页导致章末大片空白

`assets/print.css` 里 `h2 { page-break-before: always; }` 的取舍：
目录页码精准、跳转精准，代价是每章末尾留白。不想分页就删掉这两行 `page-break` 声明
（但目录页码仍会标在该章首次出现的页，不影响正确性）。

## 渲染引擎备忘

| 引擎 | 典型路径 | 备注 |
| --- | --- | --- |
| Microsoft Edge | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | Windows 首选，一般已预装 |
| Google Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` | Windows |
| Chrome (macOS) | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` | |
| Chromium | `which chromium` / `chromium-browser` | Linux |

`--engine edge` / `--engine chrome` 是别名，也可直接给绝对路径。
`--headless=new` 在 Edge 109+ / Chrome 112+ 可用；老版本退回 `--headless`。
`--no-pdf-header-footer`：不生成浏览器默认页眉页脚（PDF 阅读器仍显示页码）。
