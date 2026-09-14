# 内网 / 完全离线环境部署指南

> 目标：在一台**完全没有互联网**的机器上使用本 skill。

## 一、最快路径（推荐）

全程两条命令，无需手动处理任何细节：

```bash
# ── 有网机器 ──────────────────────────────────────
python deploy_offline.py pack --bundle ./bundle
# 产出 ./bundle/ 与 ./bundle-offline.zip

# ── 搬运（U盘 / 内网共享）──────────────────────────
# 把 bundle 目录或 zip 拷到目标机器

# ── 目标机器 ─────────────────────────────────────
python deploy_offline.py install --bundle ./bundle
```

`install` 会自动完成：平台指纹校验 → 离线装依赖 → 装系统库（Linux）→ 自检 → 端到端冒烟测试。

## 二、三种模式说明

| 命令 | 运行位置 | 作用 |
|---|---|---|
| `deploy_offline.py status` | 任意 | 查看当前机器环境，判断能否直接用 |
| `deploy_offline.py plan` | 目标机器 | **诊断**该机器需要哪些步骤（不执行） |
| `deploy_offline.py pack` | **有网机器** | 下载依赖 + 复制 skill + 打包 |
| `deploy_offline.py install` | **目标机器** | 校验 + 安装 + 自检 |

### 不确定从哪开始？先跑 `plan`

```bash
python deploy_offline.py plan
```

它会输出该机器**具体的**部署步骤（因平台而异），并提示风险点。

### 已装过环境的机器？跑 `status`

```bash
python deploy_offline.py status
```

## 三、脚本自动处理的平台差异

你**不需要**记住下面这些——脚本会按平台自动分派。此表仅作原理说明。

| 差异点 | Windows | macOS | Linux |
|---|---|---|---|
| 依赖 wheel 平台标记 | `win_amd64` | `macosx_*` | `manylinux_*` |
| Python ABI 标记 | `cp313` (随版本) | 同 | 同 |
| 系统级依赖 | VC++ 运行库（需时提示） | 无 | `libgl1`、`libglib2.0-0`、`fonts-wqy-microhei` |
| 中文字体来源 | 系统自带 | 系统自带苹方 | **需补装** |
| 包管理器 | 无（提示离线安装包） | 无 | `apt` / `dpkg` |
| Tesseract 位置 | `Program Files` | `/opt/homebrew/bin` | `/usr/bin` |

### 平台指纹机制

`pack` 时脚本会记录平台指纹，形如：

```
win_amd64_cp313_64bit      # Windows + AMD64 + CPython 3.13 + 64位
linux_x86_64_cp311_64bit   # Linux + x86_64 + CPython 3.11 + 64位
macos_arm64_cp312_64bit    # macOS + Apple Silicon + CPython 3.12
```

`install` 时自动比对：
- **指纹一致** → 直接安装
- **不一致** → **提前中止**并说明差异（而不是等 pip 报一堆难懂的错）
- 确认要试 → 加 `--force` 强行继续

> **为什么必须同平台**：`pip download` 只下载**当前平台**的 wheel。
> 跨平台的 wheel 文件名带不同平台标记，`pip install` 会直接拒绝。

## 四、常见场景

### 场景 1：目标机已有 Python（最常见）

```bash
# 有网机器
python deploy_offline.py pack --bundle ./bundle
# 搬运后, 目标机
python deploy_offline.py install --bundle ./bundle
```

### 场景 2：目标机没有 Python

先装 Python（需离线安装包），再走场景 1。或者：

```bash
# 有网机器: 打包时带上完整 venv
python deploy_offline.py pack --bundle ./bundle
# 额外把整个 venv 目录也拷过去（须放在相同路径）
```

> **限制**：venv 内嵌绝对路径，目标机必须放在**完全相同路径**下，且 Python 主版本一致。

### 场景 3：体积敏感（不要 OCR）

```bash
python deploy_offline.py pack --bundle ./lite --no-ocr
```

体积从 ~95MB 降到 ~25MB，但**失去文字识别与分类能力**，只剩格式转换与导出。

### 场景 4：Linux 内网（含国产化系统）

```bash
# 有网 Linux 机器（必须！不能用 Windows 打包）
python deploy_offline.py pack --bundle ./bundle

# 顺便准备系统库 deb（脚本会提示缺哪些）
apt-get download libgl1 libglib2.0-0 fonts-wqy-microhei
mkdir -p bundle/debs && mv *.deb bundle/debs/

# 目标机
python deploy_offline.py install --bundle ./bundle
```

若 bundle 内放了 `debs/`，脚本会优先用本地 deb 安装。

> **国产化环境**（麒麟 / 统信 UOS / ARM64 / 龙芯）：
> 先跑 `plan` 看风险提示。关键在于 `onnxruntime` 和 `opencv-python`
> 是否有对应架构的 wheel；没有则需源码编译，成本较高，建议先做可行性验证。

## 五、包内容与体积

`pack` 产出的目录结构：

```
bundle/
├── packages/              # 21 个 .whl, 约 95MB
├── image-toolkit/         # skill 本体（脚本 + 文档）
├── manifest.json          # 平台指纹 + 包清单 + 安装目标
└── debs/                  # (可选) Linux 系统库
```

| 包 | 用途 | 体积 |
|---|---|---|
| opencv-python | 图像预处理（OCR 依赖） | ~44 MB |
| onnxruntime | 推理运行时 | ~15 MB |
| numpy | 特征计算 | ~13 MB |
| rapidocr-onnxruntime | OCR 引擎 + **模型内嵌** | ~13 MB |
| python-docx + lxml | Word 输出 | ~5 MB |
| Pillow | 图像读写转换 | ~3 MB |
| reportlab | PDF 输出 | ~3 MB |
| 其他（pyclipper/shapely/pyyaml/protobuf…） | OCR 依赖 | ~5 MB |
| **合计** | | **约 95 MB** |

> RapidOCR 的 ONNX 模型（约 13MB）**已包含在 wheel 内**，无需单独准备。

## 六、手工兜底（脚本不可用时）

若目标机 Python 环境特殊，导致 `deploy_offline.py` 无法运行，分两步：

### 6.1 先试 env.py 探测路径

多数情况下 `env.py` 仍然可用（它只依赖标准库）。用它可以免去手填路径：

```bash
eval "$(python <skill>/scripts/env.py --sh)"
# 得到 $SK 和 $PY; 若提示依赖不齐全, 说明还需装包, 见下
```

### 6.2 完全手工执行

```bash
PY=<目标机 python 路径>
PKG=<bundle>/packages

# 离线安装（关键：--no-index 禁网 + --find-links 指向本地包）
"$PY" -m pip install --no-index --find-links "$PKG" \
  Pillow openpyxl python-docx pypdf reportlab numpy \
  rapidocr-onnxruntime pytesseract

# 验证
"$PY" <skill>/scripts/selftest.py
```

Linux 系统库手工安装：

```bash
sudo dpkg -i <bundle>/debs/*.deb
# 或
sudo apt install libgl1 libglib2.0-0 fonts-wqy-microhei
```

## 七、常见问题

| 问题 | 原因 | 处理 |
|---|---|---|
| `平台不匹配: 打包于 X, 当前机器为 Y` | 跨平台搬运 | 在目标平台重新 `pack`；或用 `--force` 尝试 |
| `No matching distribution found` | 包目录缺依赖或平台不符 | 确认打包机与目标机同平台同 Python 大版本 |
| `--no-index` 仍尝试联网 | `--find-links` 路径错 | 用绝对路径；确认目录内含 `.whl` |
| 启动报 DLL 缺失 | onnxruntime 缺 VC++ 运行库 | 装 VC++ 2015-2022 可再发行组件 (x64) |
| Linux 下 `libGL.so.1` 缺失 | opencv 依赖图形库 | `sudo apt install libgl1 libglib2.0-0` |
| PDF 中文是方框 | 缺中文字体 | Linux: `sudo apt install fonts-wqy-microhei` |
| venv 拷过去不能用 | 路径或版本不一致 | 在目标机**重建 venv**，用 bundle 安装 |
| OCR 模型加载失败 | wheel 不完整 | 重下 `rapidocr-onnxruntime`，校验约 12.3MB |
| 自动装系统库失败 | 无 root 权限 | 加 `sudo` 重跑，或用 `--no-sysdeps` 后手工装 |

## 八、验证部署成功

脚本 `install` 最后会自动跑自检。也可手动执行：

```bash
python <skill>/scripts/selftest.py
```

自检会**现场合成一张中文测试图**，跑完整链路（OCR → 分类 → 导出 docx/xlsx/pdf），
并在禁用网络的前提下验证——不依赖任何外部素材。

预期输出：

```
  ✓ 核心依赖  (5 项齐全)
  ✓ OCR 引擎  (RapidOCR)
  ✓ 中文字体  (MSYH, SimHei -> Word 用 微软雅黑)
  ✓ 合成测试图  (selftest_invoice.png)
  ✓ OCR 识别  (15 行, 中文正常)
  ✓ 内容分类  (-> 发票 (0.87))
  ✓ 导出 docx  (78.2KB)
  ✓ 导出 xlsx  (7.0KB)
  ✓ 导出 pdf   (82.7KB)
  ✓ 离线验证  (禁用网络后 OCR 正常)
  结果: 10 通过, 0 失败
```

看到「自检通过」即部署成功。

## 九、为什么运行期不需要网络

| 保证 | 说明 |
|---|---|
| 代码层面 | 所有脚本不 import requests / urllib / socket，无出网调用 |
| 模型层面 | RapidOCR 的 ONNX 模型随 wheel 落盘，运行时加载本地文件 |
| 实测验证 | `selftest.py` 在禁用 socket 的前提下跑通全流程 |
| 图片隐私 | 全程本机处理，不外传 |
