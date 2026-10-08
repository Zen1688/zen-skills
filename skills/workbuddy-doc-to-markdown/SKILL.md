---
name: workbuddy-doc-to-markdown
description: 把 WorkBuddy 资料库（library）里的在线文档节点（kind=doc）导出为本地 Markdown 文件。当用户给出 share 链接（workbuddy.link/p/xxx、workbuddy.cn/space/d/xxx）或节点 ID，并要求「落地/导出/下载/存一份到本地/转成 md」时使用。覆盖：节点类型判定、doc 原文抓取、组件标记 → Markdown 转换、落盘校验。
agent_created: true
---

# WorkBuddy 云上文档 → 本地 Markdown 落地

把资料库在线文档转成本地 `.md`。两个阶段：**抓取**（走 library skill 的脚本）+ **转换**（本 skill 自带脚本）。

## 适用与不适用

| 场景 | 是否适用 |
| --- | --- |
| 分享链接 / 节点 ID → 本地 md 文件 | ✅ |
| 一批 doc 子节点整包落地 | ✅ |
| 节点 kind 是 `web`（在线页面）| ⚠️ 页面产物是 `index.html`/`conversation-data.json`，本流程只处理其**下方挂的 doc 子节点** |
| drive 节点（docx/xlsx/pptx） | ❌ 走 `tencent-saas-docs` 或 library 的 `drive/entry.md` |
| database 节点（在线表格） | ❌ 走 library 的 `database/entry.md` |
| 反向导入（本地 md → 云上 doc） | ❌ 走 library 的 `doc/tasks/read_create.md` |

## 步骤 1 · 判定节点类型（必做，别跳过）

```bash
python3 "<LIB>/space_api.py" space.workspace.node-info --node-id <nodeId>
```

- `<LIB>` = WorkBuddy 内置 `library` 技能的目录，位于 WorkBuddy 安装目录下的
  `resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/library`。
  安装目录因机而异，首次使用时定位一次即可（不要把结果写回 SKILL.md）：
  ```bash
  LIB="$(find "$HOME" "/c/Program Files" "/c/Program Files (x86)" -maxdepth 8 \
       -type d -path '*workbuddy-builtin/skills/library' 2>/dev/null | head -1)"
  ```
- 从 `workbuddy.link/p/<id>` 或 `workbuddy.cn/space/d/<id>` 取出 `<id>`。**不要用 WebFetch/浏览器探这些链接**——登录墙只会返回登录页，据此推断的标题/类型都是编造。
- 返回里 `kind` 定路由；`nodes` 数组是子节点 ID 列表，`url` 是编辑态链接。
- kind=`web` 时，子节点往往是本次任务的产物集合（`nodes` 里逐个 `node-info` 看标题）。

## 步骤 2 · 抓取 doc 原文

```bash
python3 "<LIB>/doc/get_doc_reviews.py" --page-id <nodeId> > /tmp/doc_<nodeId>.txt
```

- 输出首行是 `KS_DOC_REVIEWS\t<id>\t<chars>\t<url>`，其后是组件标记正文。**回执行不属于正文，转换时要剔除**（脚本已处理）。
- 逐节点抓取；建议存成 `doc_<nodeId>.txt` 便于脚本循环。

## 步骤 3 · 组件标记转 Markdown

```bash
python3 scripts/convert_doc_components.py /tmp/doc_<nodeId>.txt "D:/out/<标题>.md"
```

输出：UTF-8 无 BOM、LF 换行、结尾单换行。脚本会打印 `(文件名, 标题, 字节数, 残留标签数, 残留标签样本)`，**残留标签数应为 0**（Java 泛型 `<String>` 之类的正文文本会误报，需人工确认）。

## 组件格式要点（改脚本前必读）

原文是组件标记，不是 Markdown：

```
<Heading id="…" level="2"> 标题 </Heading>
<Paragraph id="…"> 正文，可含 <Mark bold>加粗</Mark> </Paragraph>
<BlockQuote id="…"> <Paragraph>…</Paragraph> </BlockQuote>
<Divider id="…" />                      ← 自闭合
<Code id="…"> ``` … ``` </Code>          ← 内容已自带围栏，整体透传
<Table id="…" readonly rowHeader> <TableRow> <TableCell> … </TableCell> </TableRow> </Table>
<NumberedList id="…"> 一个条目 </NumberedList>   ← 每个条目一个独立节点！
<BulletedList id="…"> 一个条目 </BulletedList>
<Todo id="…"> 待办项 </Todo>
```

必须处理的 7 个坑：

1. **`<Code>` 内可能是任意文本**（Maven `<dependency>`、Java `List<String>`）。解析器遇到 `Code` 必须整体截取到 `</Code>`，绝不递归解析内部。
2. **`<Mark bold>` 多与正文同行**，不是独立节点。要在行文本上做正则 `<Mark[^>]*>(.*?)</Mark>` → `**\1**`，并循环处理多层。
3. **列表条目是独立兄弟节点**：连续的 `<NumberedList>` 要合并成一个列表并自行编号；连续 `<BulletedList>` 合并且统一用 `- `。
4. **列表项取文本要 shallow**：只取 `str` 与行内标签子节点，块级子节点（嵌套列表/表格/代码）另行缩进渲染——否则嵌套内容会重复出现两遍。
5. **表格统一带 `readonly rowHeader`** → 首行为表头；单元格内一般只有一个 `Paragraph`；单元格文本里的 `|` 要转义成 `\|`，段落内换行转 `<br>`。
6. **缩进即层级**：`<Tag>` 与其内容行按前导空格数判定父子，`</Tag>` 收栈。别按标签配对贪心匹配（代码块会破坏配对）。
7. **转义**：正文里的 `\_` `\*` 等是 Markdown 转义，要还原；行尾单独的 `\` 是软换行，转成换行。

## 步骤 4 · 落盘校验（必做）

```bash
cd <目标目录> && python3 -c "
import glob,re
for f in sorted(glob.glob('*.md')):
    b=open(f,'rb').read(); t=b.decode('utf-8')
    fences=len(re.findall(r'^\`\`\`', t, re.M))
    tags=set(re.findall(r'</?[A-Z][A-Za-z]+(?:\s[^>]*)?/?>', re.sub(r'\`\`\`.*?\`\`\`','',t,flags=re.S)))
    print(f, len(b), 'CRLF=', b.count(b'\r\n'), 'BOM=', b[:3]==b'\xef\xbb\xbf', 'fences=', fences, fences%2==0, '残留=', tags or '-')
"
```

判据：`CRLF=0`、`BOM=False`、`fences` 为偶数、`残留` 为空（除泛型文本误报）。

## 环境

- Windows + Git Bash 下建议用托管 Python 的绝对路径（避免 PATH 里混入其他 Python），形如
  `$HOME/.workbuddy/binaries/python/versions/<版本号>/python.exe`。
- 只用标准库，无三方依赖。
