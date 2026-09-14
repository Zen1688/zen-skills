---
name: image-toolkit
description: "离线图片处理工具箱：格式转换（JPG/PNG/WEBP/BMP/TIFF/GIF/ICO/PDF 互转）、图片文字识别（OCR，中英文）、基于图片内容的智能分类（支持内置业务分类与用户自定义标准）、识别结果导出为 Word/Excel/PDF/TXT/Markdown。全程无网络调用，适配国内无网/内网环境。当用户需要处理图片、把图片里的文字提取出来、把图片内容整理成 Office 文档、给图片自动分类归档、或批量转换图片格式时使用。触发词：图片转文字、OCR、识别图片、图片转Word、图片转Excel、图片分类、图片格式转换、扫描件识别、发票识别、离线OCR。"
agent_created: true
---

# 图片处理工具箱 (image-toolkit)

## 核心承诺

| 特性 | 说明 |
|---|---|
| **零网络依赖** | 运行时无任何 HTTP 调用。OCR 模型随 pip 包落盘，装好即可断网使用 |
| **国内可用** | 不依赖任何境外服务；首次安装支持清华/阿里镜像 |
| **四大能力** | 格式转换 / 文字识别 / 内容分类 / 导出 Office |
| **纯本地处理** | 图片不出本机，适合内网与敏感资料 |

## 快速开始

**第一步永远是定位环境**——不要手写路径，让脚本自己算：

```bash
# 进入 skill 的 scripts 目录（或任意位置，用完整路径调用 env.py）
eval "$(python env.py --sh)"          # bash: 设好 $SK 和 $PY
```

> Windows cmd 用 `for /f "delims=" %i in ('python env.py --bat') do %i`
> PowerShell 用 `python env.py --ps`

然后：

```bash
# 全流程（最常用）：识别 + 分类 + 导出 Word/Excel
"$PY" "$SK/pipeline.py" ./图片目录 --out ./结果 --to docx,xlsx

# 先转格式再识别
"$PY" "$SK/pipeline.py" ./图片目录 --convert png --out ./结果 --to docx

# 环境自检（推荐装好后先跑一次）
"$PY" "$SK/selftest.py"

# 仅查依赖状态
"$PY" "$SK/setup_env.py" --check
```

**更省事的写法**——连变量都不用管：

```bash
python scripts/env.py --run pipeline.py ./图片目录 --out ./结果 --to docx,xlsx
```

`env.py` 会自动探测 skill 位置与可用的 Python 解释器（含依赖完整性验证），
因此 skill 搬到任何位置、装在任何 Python 下都能正常工作。

## 离线部署（内网机器）

一条命令打包，一条命令安装：

```bash
# 有网机器
"$PY" "$SK/deploy_offline.py" pack --bundle ./bundle

# 搬运到目标机器后
"$PY" "$SK/deploy_offline.py" install --bundle ./bundle
```

| 子命令 | 位置 | 作用 |
|---|---|---|
| `plan` | 目标机 | 诊断该机器需要哪些步骤 |
| `pack` | 有网机 | 打包依赖 + skill 本体 |
| `install` | 目标机 | 校验平台 → 装依赖 → 自检 |
| `status` | 任意 | 查看当前环境 |

脚本会自动处理平台差异（依赖 wheel 标记、系统库、字体），并在跨平台搬运时**提前拦截**。
详见 `references/offline-deploy.md`。

## 四大能力详解

### 1. 格式转换 `convert.py`

支持 **JPG / PNG / WEBP / BMP / TIFF / GIF / ICO / PDF** 互转，含多帧 GIF 与透明通道处理。

```bash
"$PY" "$SK/convert.py" 输入图.png --to jpg --out ./output --quality 92
"$PY" "$SK/convert.py" 输入目录 --to pdf --out ./output --dpi 200
```

| 参数 | 说明 |
|---|---|
| `--to` | 目标格式（必填） |
| `--out` | 输出目录，默认与源同目录 |
| `--quality` | JPEG/WEBP 质量 1-100，默认 92 |
| `--dpi` | 输出 PDF 的 DPI，默认 150 |

### 2. 文字识别 `ocr.py`

双引擎自适应：**RapidOCR（PP-OCRv4，中文首选）** → Tesseract 回退。

```bash
# 识别单图
"$PY" "$SK/ocr.py" 图片.png

# 批量识别并输出 JSON（供后续导出）
"$PY" "$SK/ocr.py" ./图片目录 --json --out ./ocr.json

# 查看引擎可用性
"$PY" "$SK/ocr.py" x --list-engines
```

### 3. 内容分类 `classify.py`

**内置业务分类**（未指定标准时默认使用）：

| 分类 | 主要判据 |
|---|---|
| 发票 | 发票代码/号码、价税合计、纳税人识别号、税率 |
| 合同/协议 | 甲方乙方、违约责任、合同编号、法定代表人 |
| 证件/证照 | 身份证、营业执照、统一社会信用代码、签发机关 |
| 表格/单据 | 序号、单价、数量、合计 + 背景规整度 |
| 幻灯片 | 目录、议程、CONTENTS、汇报人 |
| 图表/数据可视化 | 同比/环比、增长率、占比、单位:万元 |
| 聊天/网页截图 | 发送/微信/http/www + 竖长构图特征 |
| 手写笔记 | 有文字但行数少、置信度偏低 |
| 照片 | 无文字 + 色彩丰富度高 |

**用户自定义分类**：传 `--rules rules.json`，格式为

```json
{
  "我的分类A": {
    "keywords": ["强特征词1", "强特征词2"],
    "weak":     ["弱特征词1"],
    "veto":     ["命中则排除的干扰词"]
  },
  "我的分类B": ["简写形式：直接给强关键字数组"]
}
```

```bash
"$PY" "$SK/classify.py" ./图片目录 --rules ./my_rules.json --out ./cls.json
```

分类结果**带置信度与判据**（命中哪些关键字、哪些图像特征），便于人工复核。

### 4. 导出 Office `export.py`

```bash
"$PY" "$SK/export.py" ./ocr.json --to docx,xlsx,pdf,txt,md --out ./输出
```

| 格式 | 内容 |
|---|---|
| **docx** | 元信息表 + 原图嵌入 + 识别文字，每图一页 |
| **xlsx** | 3 个 sheet：汇总 / 识别明细（按坐标还原表格） / 分类统计 |
| **pdf** | 中文字体自动注册（msyh/SimSun/SimHei），图文混排 |
| **txt / md** | 纯文本；md 按分类分组 |

## 一体化管道 `pipeline.py`（推荐入口）

一次执行完成「转换 → 识别 → 分类 → 导出 → 归档」：

```bash
"$PY" "$SK/pipeline.py" <输入> --out <输出目录> [选项]
```

| 选项 | 说明 |
|---|---|
| `--to` | 导出格式，默认 `docx,xlsx` |
| `--convert` | 先转换格式（png/jpg/webp/pdf） |
| `--rules` | 自定义分类规则 JSON |
| `--engine` | `auto`（默认）/ `rapidocr` / `tesseract` |
| `--threshold` | 分类置信度阈值，默认 0.25 |
| `--group-by-category` | 额外按分类复制原图到子文件夹 |
| `--no-ocr` | 仅转换格式 |
| `--no-image` | 导出时不嵌入原图 |

## 环境要求

| 项 | 要求 |
|---|---|
| **操作系统** | Windows 10+ / macOS 11+ / Linux（详见下节） |
| Python | 3.8+（实测 3.13.14）。解释器路径**用 `env.py` 自动探测**，无需手写 |
| 必需包 | Pillow, openpyxl, python-docx, reportlab, numpy |
| OCR 引擎 | RapidOCR（推荐）或 Tesseract |
| 中文字体 | Windows/macOS 系统自带；Linux 需装 fonts-wqy-microhei |
| 网络 | **运行时不需要**；仅首次装包需要 |

首次准备：`python scripts/setup_env.py --with-rapidocr`
（该命令会一并打印当前平台与中文字体探测结果）

## 操作系统兼容性

### 结论

| 系统 | 支持状态 | 说明 |
|---|---|---|
| **Windows 10/11** | ✅ **首选，已完整实测** | 路径、字体、OCR 全部验证通过 |
| **macOS** | ✅ 理论支持 | 字体改用苹方/华文黑体；Tesseract 走 Homebrew 路径；**未实测** |
| **Linux (x86_64)** | ✅ 理论支持 | 需额外装中文字体；Tesseract 走 `/usr/bin`；**未实测** |
| **Linux (ARM / 国产芯片)** | ⚠️ 需确认 | onnxruntime / opencv 需有对应架构 wheel |
| Windows 7 及更早 | ❌ 不支持 | Python 3.9+ 已放弃 Win7 |

### 代码层面的平台处理

| 关注点 | 实现方式 | 跨平台 |
|---|---|---|
| 中文字体（PDF/Word） | 按 `sys.platform` 查表探测，含兜底目录扫描 | ✅ 已适配三平台 |
| Tesseract 定位 | `shutil.which()` + 平台候选路径表 | ✅ 已适配三平台 |
| 临时目录 / 路径分隔 | 全程 `pathlib.Path` | ✅ |
| 网络调用 | 无（已实测 socket 禁用下可用） | ✅ |
| 子进程调用 | 仅 Tesseract 用；RapidOCR 为纯 Python 库 | ✅ |

### 平台差异注意事项

| 差异点 | Windows | macOS | Linux |
|---|---|---|---|
| Word 中文字体 | 微软雅黑 | PingFang SC | Noto Sans CJK SC |
| PDF 字体来源 | `C:\Windows\Fonts` | `/System/Library/Fonts` | `/usr/share/fonts` |
| Linux 补装字体 | — | — | `sudo apt install fonts-wqy-microhei` |
| Tesseract 安装 | 官网 exe / winget | `brew install tesseract tesseract-lang` | `sudo apt install tesseract-ocr tesseract-ocr-chi-sim` |

> **推荐**：用 RapidOCR 而非 Tesseract。RapidOCR 是纯 Python 包，
> 三平台安装方式完全一致（`pip install rapidocr-onnxruntime`），
> 无系统级依赖，跨平台成本最低。


## 离线保证

1. 所有脚本**不 import** requests/urllib 等网络库，无任何出网调用。
2. RapidOCR 的 ONNX 模型文件随 pip 包安装到本地，运行时不下载。
3. 首次装包后可完全断网；镜像源仅用于加速首次安装。
4. 图片全程在本机内存与磁盘处理，不外传。

## 常见问题

| 现象 | 处理 |
|---|---|
| 提示无可用 OCR 引擎 | 运行 `setup_env.py --with-rapidocr` |
| 中文识别为乱码 | 确认用 RapidOCR 引擎；Tesseract 需装 `chi_sim` 语言包 |
| 识别为空 | 图片可能确无文字，或分辨率过低；可先用 `convert.py` 放大 |
| 分类不准 | 用 `--rules` 提供你的业务关键字；或调 `--threshold` |
| PDF 中文显示方框 | 系统缺中文字体。Windows/macOS 一般自带；Linux 装 `fonts-wqy-microhei` |
| 换到 mac/Linux 后报错 | 运行 `setup_env.py --check` 查看平台与字体探测结果 |

## 脚本清单

| 脚本 | 用途 |
|---|---|
| `env.py` | **环境定位**：自动探测 skill 路径与 Python 解释器 |
| `pipeline.py` | 一体化入口（转换→识别→分类→导出→归档） |
| `convert.py` | 格式转换 |
| `ocr.py` | 文字识别 |
| `classify.py` | 内容分类 |
| `export.py` | 导出 Office/PDF/TXT |
| `setup_env.py` | 环境自检与装包 |
| `deploy_offline.py` | 离线部署自动化 |
| `selftest.py` | 端到端自检（合成图跑全链路） |
| `common.py` | 共享工具（枚举/引擎探测/跨平台字体） |

> **路径说明**：所有脚本内部都用 `Path(__file__).resolve().parent`
> 与 `sys.executable` 定位自身，**不硬编码任何绝对路径**。
> 文档中的 `$PY` / `$SK` 是变量引用，由 `env.py` 自动填充。

## 参考文档

- `references/quickstart.md` — 快速上手与典型场景
- `references/classification-guide.md` — 分类判据原理与自定义规则调优指南
- `references/offline-deploy.md` — 内网机器离线部署完整步骤
