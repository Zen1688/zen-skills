# 图片处理工具箱 —— 快速上手

## 运行环境

| 项 | 要求 |
|---|---|
| 操作系统 | **Windows 10+（已实测）** / macOS / Linux（理论支持，未实测） |
| Python | 3.8+ |
| 网络 | 运行时不需网络 |

**依赖不用手动装**：首次调用任一脚本时会自动补齐（详见 `SKILL.md` 的「依赖：首次调用自动安装」）。
macOS / Linux 使用前建议先跑一次 `setup_env.py --check`，确认中文字体与 OCR 引擎探测正常。

## 30 秒跑通

**不要手写路径。** 先让脚本自己定位环境：

```bash
# 在 skill 的 scripts 目录下执行（或写完整路径）
eval "$(python env.py --sh)"        # bash: 得到 $SK 和 $PY
```

Windows cmd / PowerShell 对应写法：

```bat
:: cmd
for /f "delims=" %i in ('python env.py --bat') do %i
```
```powershell
# PowerShell
Invoke-Expression (python env.py --ps | Out-String)
```

然后一条命令跑通：

```bash
"$PY" "$SK/pipeline.py" 你的图片目录 --out ./结果 --to docx,xlsx
```

**最省事的写法**——连变量都不用管：

```bash
python scripts/env.py --run pipeline.py 你的图片目录 --out ./结果 --to docx,xlsx
```

产出的 `结果/` 目录会有：

| 文件 | 内容 |
|---|---|
| `识别报告.docx` | 每张图的原图 + 元信息 + 识别文字 |
| `识别报告.xlsx` | 汇总 / 识别明细 / 分类统计 三个表 |
| `recognition.json` | 结构化中间结果（可复用，避免重复 OCR） |

> `env.py` 会自动探测 skill 位置与可用的 Python 解释器，并验证依赖完整性。
> skill 被搬到任何目录、装在任何 Python 下都能正常工作。

## 依赖从哪来（首次调用自动装）

**不需要手动 `pip install`。** 首次调用任一脚本时 `bootstrap.py` 会自动补齐：

| 情况 | 行为 |
|---|---|
| 依赖齐全 | 立即返回，几乎无额外开销 |
| 本机已有备好依赖的解释器 | 直接复用，不重复安装 |
| 需要安装 | 建独立 venv → 装依赖 → 用新解释器重跑当前脚本 |
| 有本地 wheel 目录 | `--no-index` **纯离线安装**，不联网 |
| 无网又无本地包 | 立即报错并给指引，不挂起 |

默认装到 `~/.image-toolkit/venv`（跨副本共享、不污染宿主环境）。
只装核心（`convert.py` / `export.py`）约 26MB；含 OCR（`pipeline.py` / `ocr.py` / `classify.py` / `selftest.py`）约 95MB。

```bash
# 想提前装好
"$PY" "$SK/bootstrap.py"
# 只检查
"$PY" "$SK/bootstrap.py" --check
# 关掉自动安装（改为只提示不下载）
IMAGE_TOOLKIT_NO_AUTO_INSTALL=1
```

内网无网：把 wheel 放到 `<skill>/wheelhouse/`，引导器会自动发现并离线安装。

## 四类典型场景

> 以下示例假定已执行 `eval "$(python env.py --sh)"`。

### 场景 A：扫描件 → Word 文档

把一堆纸质扫描的 PDF/JPG 变成可编辑的 Word。

```bash
"$PY" "$SK/pipeline.py" ./扫描件 --out ./文档 --to docx
```

### 场景 B：发票/单据批量整理成表格

```bash
"$PY" "$SK/pipeline.py" ./发票 --out ./整理 --to xlsx --threshold 0.3
```

Excel 的「识别明细」sheet 会尝试还原表格行列结构。

### 场景 C：按内容自动分类归档

```bash
"$PY" "$SK/pipeline.py" ./杂乱图片 --out ./归档 \
    --group-by-category --to txt
```

原图会按 `归档/按分类归档/发票/`、`归档/按分类归档/合同协议/` 自动分好。

### 场景 D：用自己的分类标准

先写规则文件 `my_rules.json`：

```json
{
  "报销单": { "keywords": ["报销", "费用", "审批"], "weak": ["金额"] },
  "会议纪要": { "keywords": ["会议纪要", "参会人员", "决议"], "weak": ["议题"] }
}
```

再跑：

```bash
"$PY" "$SK/pipeline.py" ./图片 --rules ./my_rules.json --out ./结果 --to docx
```

## 单独用某个能力

```bash
# 只转格式：PNG → JPG
"$PY" "$SK/convert.py" 图.png --to jpg --quality 90

# 只识别文字
"$PY" "$SK/ocr.py" 图.png

# 只分类（可复用已有 OCR 结果，省时间）
"$PY" "$SK/classify.py" ./图片 --ocr recognition.json

# 只导出（从已有 JSON）
"$PY" "$SK/export.py" recognition.json --to docx,pdf --out ./输出

# 查看 OCR 引擎状态
"$PY" "$SK/ocr.py" x --list-engines
```

## 参数速查

| 参数 | 说明 | 默认 |
|---|---|---|
| `--to` | 导出格式 `docx,xlsx,pdf,txt,md` | `docx,xlsx` |
| `--convert` | 先转换格式 `png/jpg/webp/pdf` | 不转换 |
| `--rules` | 自定义分类规则 JSON | 内置业务分类 |
| `--threshold` | 分类置信度阈值 | 0.25 |
| `--group-by-category` | 按分类复制原图到子目录 | 关 |
| `--engine` | `auto` / `rapidocr` / `tesseract` | `auto` |
| `--no-ocr` | 只转格式不识别 | 关 |
| `--no-image` | 导出时不嵌原图（文件更小） | 关 |

## 输出效果预览

**Word 报告结构：**

```
图片识别报告
共处理 5 张图片

1. invoice.png
┌──────────┬─────────────────────────────┐
│ 来源      │ D:\...\invoice.png          │
│ 分类      │ 发票  (置信度 0.93)          │
│ 分类判据   │ 命中强关键字 12 个: 发票代码… │
│ 识别引擎   │ rapidocr                    │
└──────────┴─────────────────────────────┘
原图
[图片]
识别文字
增值税专用发票
发票代码  011002100311
...
```

**Excel 三表：**

| Sheet | 内容 |
|---|---|
| 汇总 | 每张图的文件名/分类/置信度/行数/字符数 |
| 识别明细 | 按坐标还原的表格行列 |
| 分类统计 | 各分类数量与占比 |

## 路径与迁移

本 skill **不硬编码任何绝对路径**，可以随意搬到别的位置。

| 位置 | 处理方式 |
|---|---|
| 脚本内部（`.py`） | 用 `Path(__file__).resolve().parent` 定位自身；用 `sys.executable` 取解释器 |
| 文档中的 `$PY` / `$SK` | **变量引用**，由 `env.py` 自动填充 |
| Python 解释器 | `env.py` 自动探测（当前解释器 → 运行时 venv → 托管 venv → PATH），并验证依赖完整性 |
| Python 依赖 | 首次调用自动补齐；默认装在 `~/.image-toolkit/venv`（`IMAGE_TOOLKIT_RUNTIME_DIR` 可改） |
| 字体 / Tesseract | 按 `sys.platform` 查表探测，含兜底目录扫描 |

### 迁移后怎么用

```bash
# 假设 skill 现在在 /opt/tools/image-toolkit
cd /opt/tools/image-toolkit
eval "$(python scripts/env.py --sh)"      # 自动拿到正确的 $SK 和 $PY
"$PY" "$SK/pipeline.py" ./图片 --out ./结果
```

或完全不管变量：

```bash
python /opt/tools/image-toolkit/scripts/env.py --run pipeline.py ./图片 --out ./结果
```

### 验证迁移是否成功

```bash
python <skill>/scripts/env.py             # 应显示正确的 skill 路径与 Python
python <skill>/scripts/selftest.py        # 应 10/10 通过
```

> 若 `env.py` 报「依赖不齐全」，不必手动装 —— 首次调用会自动补齐。
> 想提前装好：`python <skill>/scripts/bootstrap.py`；
> 内网机器见 `references/offline-deploy.md` 的 wheelhouse 做法。

## 常见问题

| 问题 | 解决 |
|---|---|
| 提示无 OCR 引擎 | 依赖没装全：跑 `"$PY" "$SK/bootstrap.py"`（自动装 RapidOCR） |
| 首次运行停在「安装依赖」 | 正常（约 95MB 含 OCR）。不想自动装：`IMAGE_TOOLKIT_NO_AUTO_INSTALL=1` |
| 识别结果为空 | 图可能确无文字，或分辨率太低 |
| 分类不准 | 加 `--rules` 自定义；或把 `--threshold` 降到 0.2 |
| 表格列错位 | 复杂表格（合并单元格）难免，建议人工复核 |
| 换机器/换目录后报错 | 先跑 `env.py` 重新定位，见上节 |
| 要断网使用 | 见 `references/offline-deploy.md` |

## 验证过的能力

| 能力 | 实测结果 |
|---|---|
| 中文印刷体识别 | ✅ 连「第X条」排版都能正确还原 |
| 五类业务分类 | ✅ 发票/合同/截图/表格/照片 5/5 正确 |
| 自定义分类 | ✅ 4/5 命中（未命中项属规则未覆盖） |
| 格式转换 | ✅ JPG/PNG/WEBP/BMP/PDF 互转通过 |
| 五种导出格式 | ✅ docx/xlsx/pdf/txt/md 全部产出 |
| 断网运行 | ✅ socket 全禁用下 100% 成功 |
| 换目录迁移 | ✅ 复制到新位置后自动定位，全流程通过 |
