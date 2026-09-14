# 集成指南：给已有 skill 装上运行时自举

## 前置条件

- 目标 skill 是 **Python** 写的，脚本在 `<skill>/scripts/` 下
- 本机有 Python 3.8+（引擎只依赖标准库）

---

## 步骤

### 1. 列出真实依赖

扫一遍脚本，把第三方导入找出来：

```bash
grep -rhoE "^(import|from) [A-Za-z_][A-Za-z0-9_]*" <skill>/scripts/*.py \
  | awk '{print $2}' | sort -u
```

逐个确认哪些是第三方（`PIL` / `docx` / `openpyxl` / `yaml` …），哪些是标准库。

**注意模块名与 pip 包名不一致的情况**，这是最容易搞错的点：

| 导入名 | pip 包名 |
|---|---|
| `PIL` | `Pillow` |
| `docx` | `python-docx` |
| `yaml` | `PyYAML` |
| `cv2` | `opencv-python` |
| `sklearn` | `scikit-learn` |
| `rapidocr_onnxruntime` | `rapidocr-onnxruntime` |

### 2. 分组

把依赖按「谁需要」分组。好处是让轻量脚本不必被拖去下载重依赖：

- `core` —— 大部分脚本都要的（如 `Pillow`、`openpyxl`）
- `ocr` —— 只有识别相关脚本才要（如 `rapidocr-onnxruntime`，约 70MB）

### 3. 确认哪些是入口脚本

入口脚本 = 会被**直接执行**的脚本，以及**会被别的脚本在模块级 import** 的脚本。

> ⚠️ 第二类是容易漏的。若 `pipeline.py` 在模块级 `import convert`，那么 `convert.py` 也必须挂载点 ——
> 因为 `convert.py` 的重依赖导入会先于 `pipeline.py` 的 `main()` 执行。

### 4. 预览

```bash
python <skill-bootstrap>/scripts/init_skill_runtime.py <目标 skill 目录> \
    --core "PIL=Pillow,openpyxl=openpyxl" \
    --group "ocr=rapidocr_onnxruntime=rapidocr-onnxruntime" \
    --entry pipeline.py:core,ocr \
    --entry convert.py:core \
    --entry ocr.py:core,ocr \
    --dry-run
```

逐项核对输出：

- `环境前缀` —— 会变成环境变量名，必须唯一且合法（大写字母/数字/下划线）
- `运行时目录` —— 默认 `~/.<skill 名>/venv`，确认不会与别的技能撞名
- `依赖分组` —— `*` 标出的是默认分组
- `入口脚本` —— 每个脚本声明的分组是否与它的实际依赖面一致

### 5. 执行

去掉 `--dry-run` 跑一次。它会：复制引擎 → 写 `deps.json` → 插入挂载点（插入后语法校验，失败自动回滚）。

重复执行是**幂等**的，可以放心重跑。

### 6. 检查插入位置

打开一个入口脚本，确认挂载点在**所有第三方导入之前**：

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模块文档字符串"""
                                    # ← 挂载点应该出现在这一带
# --- skill_bootstrap: 依赖惰性引导 (自动生成, 勿手改) ---
import os as _os, sys as _sys
...
# --- /skill_bootstrap ---

try:                                # ← 必须晚于挂载点
    from PIL import Image
except ImportError:
    sys.exit(2)
```

### 7. 验证

```bash
# 只检查
python <skill>/scripts/skill_bootstrap.py --check

# 看分组
python <skill>/scripts/skill_bootstrap.py --list-groups

# 端到端（在干净环境里模拟首次调用）
python <skill>/scripts/skill_bootstrap.py
```

---

## 验收清单

在**新机器或全新用户环境**下逐项确认（模拟手法：把 `HOME` / `USERPROFILE` 指向空目录 + 裁剪 `PATH`）：

| # | 验收项 | 预期 |
|---|---|---|
| 1 | 依赖齐全时调用入口脚本 | 正常执行，无额外输出，开销约 10ms |
| 2 | 本机已有依赖齐全的解释器 | 输出「复用已就绪的解释器」，**不下载任何东西** |
| 3 | 全新环境 + 有本地 wheel | 建 venv → `--no-index` 安装 → 重跑成功，**全程不联网** |
| 4 | 全新环境 + 无本地包 | 走镜像源安装 → 重跑成功 |
| 5 | 离线包不完整 | **立即**报错并退出，不挂起、不重试 |
| 6 | `${PREFIX}_NO_AUTO_INSTALL=1` | 退出码 3，打印补齐指引，**不建任何目录** |
| 7 | `--check` | 退出码 0/1，**不产生任何文件系统变化** |
| 8 | 二次调用 | 复用运行时 venv，明显快于首次 |
| 9 | `--help` | 立即返回，**不触发展动辄上百 MB 的下载** |
| 10 | git status | 无运行时残留入库（`.runtime/`、`wheelhouse/` 应被 `.gitignore` 覆盖） |

第 7、9 两项最容易被忽略，也最容易在用户侧引发抱怨 —— 一个是「我只是想看看」却改了磁盘，一个是「我只是想看用法」却下载了几百 MB。

---

## 需要一并处理的文件

### `.gitignore`

运行时产物不能入库：

```gitignore
# ---------- skill 运行时产物 ----------
.runtime/
wheelhouse/
wheels/
```

### 文档

把「首次安装需要手动 pip install」的说明改成：

> 首次调用任一脚本时会自动补齐依赖，通常不需要手动操作。
> 想提前装好或排查：`python <skill>/scripts/skill_bootstrap.py`
> 关掉自动安装：`export <PREFIX>_NO_AUTO_INSTALL=1`

### 内网分发

若目标环境无网，把 wheel 目录随技能一起分发：

```bash
# 在有网的机器上
pip download -d ./wheelhouse \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    Pillow openpyxl python-docx

# 把 wheelhouse/ 放到 <skill>/wheelhouse/ 一起拷进内网
# 引导器会自动发现，全程离线安装
```

> 用 `pip download` 时**不要加 `--no-deps`**，否则传递依赖会缺失，安装时才报错。

---

## 排查

| 现象 | 诊断 |
|---|---|
| 说缺依赖但明明装过 | `skill_bootstrap.py --json` 看 `python` 字段，多半装在了别的解释器里 |
| 每次都重装 | 运行时目录不可写 → 退化成「装进当前解释器」。检查 `${PREFIX}_RUNTIME_DIR` 指向的盘 |
| 挂载点没生效 | 用 `--dry-run` 重看位置；确认没有被插到函数体内或第三方导入之后 |
| 循环重跑 | 环境变量 `${PREFIX}_BOOTSTRAPPED` 被清掉了。引擎用它防递归，不要手动 unset |
| 内网报缺包 | `pip` 会指明缺哪个。补齐 wheel 后重跑即可，引擎不缓存失败 |
| 想换镜像源 | `${PREFIX}_MIRROR=aliyun`（可选 `tsinghua` / `aliyun` / `ustc` / `official`） |
