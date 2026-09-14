---
name: skill-bootstrap
description: 给 Python 编写的 Agent Skill 加上「运行时自举」能力——首次调用自动补齐依赖、路径自动探测，让技能装到任何机器、任何目录都能直接跑。解决技能发布后别人必须先手动 pip install、内网无网装不上依赖、脚本里写死绝对路径导致换机器就报错的问题。当用户要为 skill 添加依赖自动安装、想让技能「装完即用」、需要支持纯离线/内网环境装依赖、或排查技能在新环境跑不起来时使用。
---

# skill-bootstrap

给 Python 编写的 Agent Skill 补上「装完即用」这一环。

Agent Skills 规范只约定技能的文件结构与加载方式，**不包含运行时依赖管理**；
`pip` 也没有 post-install 钩子，两个主流宿主都没有「安装后自动执行」的通用机制。
所以补齐依赖只能做成**首次调用时的惰性引导** —— 这也是本技能的做法。

> 本技能自身**零第三方依赖**，全部脚本只用标准库，因此不需要给自己装依赖。

## 它解决两件事

| 问题 | 症状 | 本技能的解法 |
|---|---|---|
| **依赖不会自动装** | 别人 clone 走技能后必须先手动 `pip install ...`，否则一调用就报 `ModuleNotFoundError` | 引擎挂在入口脚本**模块顶部**；依赖缺失时自动建独立 venv 装上，再用新解释器重跑原命令 |
| **路径写死在文档里** | `SKILL.md` 里的示例路径是作者机器的绝对路径，换台机器照抄就失败 | 环境定位器自动算出 skill 位置与可用解释器，支持 `eval "$(… --sh)"` 与直接代跑 |

## 快速开始

**场景一：给一个新 skill 装上引导器**

```bash
# 先预览要改什么（不改任何文件）
python <本技能>/scripts/init_skill_runtime.py ./skills/my-skill \
    --core "PIL=Pillow,openpyxl=openpyxl" \
    --group "ocr=rapidocr_onnxruntime=rapidocr-onnxruntime" \
    --entry pipeline.py:core,ocr \
    --entry convert.py:core \
    --dry-run

# 确认无误后去掉 --dry-run 执行
```

它会做三件事：把引擎复制进 `<skill>/scripts/`、生成 `deps.json`、把挂载点插到入口脚本的模块顶部。
**幂等**，重复执行会跳过已完成的部分。

**场景二：给已有 skill 排查环境**

```bash
python <skill>/scripts/skill_bootstrap.py --check          # 只检查，不安装
python <skill>/scripts/skill_bootstrap.py --list-groups    # 看依赖分组
python <skill>/scripts/skill_bootstrap.py                  # 缺什么装什么
```

**场景三：内网 / 无网环境**

```bash
# 把 wheel 目录放到 <skill>/wheelhouse/ 即可被自动发现
python <skill>/scripts/skill_bootstrap.py

# 或显式指定（多个目录用系统路径分隔符连接）
MY_SKILL_FIND_LINKS=/mnt/wheels python <skill>/scripts/skill_bootstrap.py
```

有本地 wheel 目录时走 `pip --no-index --find-links`，**全程不联网**。

## 引擎怎么工作

```
入口脚本被调用
      │
      ├─ 模块顶部挂载点执行
      │       │
      │       ├─ find_spec 探测依赖（只查规格，不导入 —— 不会为了探测而加载 onnxruntime）
      │       │
      │       ├─ 齐全 ──────────────► 立即返回（开销约 10ms）
      │       │
      │       └─ 缺失
      │             ├─ 本机已有装好依赖的解释器？──► 直接复用，一次都不装
      │             ├─ 有本地 wheel 目录？────────► pip --no-index 纯离线安装
      │             ├─ 否则 ────────────────────► 走镜像源在线安装
      │             └─ 都失败 ──────────────────► 立即报错 + 打印三种补齐方式
      │                                             （不挂起、不静默重试）
      │
      └─ 需要换解释器时：用新解释器重跑当前脚本（环境变量防递归）
```

**安装位置三级回退**（默认不污染宿主环境）：

1. `${PREFIX}_RUNTIME_DIR/venv` —— 环境变量显式指定
2. `~/<runtime_dir>/venv` —— **默认**，跨副本共享、只装一次
3. `<skill>/.runtime/venv` —— 用户目录不可写时
4. 当前解释器 —— 都不行时的兜底

## 文件结构

```
skills/<skill>/
├── SKILL.md
└── scripts/
    ├── deps.json                 # 配置：依赖分组 + 环境变量前缀
    ├── skill_bootstrap.py        # 通用引擎（各 skill 之间保持一致）
    ├── env.py                    # 环境定位器（可选，引擎会自动复用它的候选来源）
    └── <各入口脚本>.py            # 模块顶部含挂载点
```

`deps.json`：

```json
{
  "skill": "my-skill",
  "env_prefix": "MY_SKILL",
  "groups": {
    "core": [["PIL", "Pillow"], ["openpyxl", "openpyxl"]],
    "ocr":  [["rapidocr_onnxruntime", "rapidocr-onnxruntime"]]
  },
  "default_groups": ["core"],
  "runtime_dir": ".my-skill",
  "extra_python_candidates": []
}
```

`groups` 里每项是 `[模块名, pip 包名]`，两者不同时（如 `rapidocr_onnxruntime` / `rapidocr-onnxruntime`）必须分开写。
入口脚本可按自身需要声明分组，这样「只做格式转换」的脚本不必被拖去下载 OCR 引擎。

## ⚠️ 最关键的一条约束

**挂载点必须插在入口脚本的模块顶部，不能放进 `main()`。**

原因：很多技能脚本会在**模块级**的 `try` 块里导入重依赖，失败即 `sys.exit`：

```python
try:
    from PIL import Image          # 模块级，不是函数内
except ImportError:
    sys.exit("缺少 Pillow")        # ← 在这里就退出了
```

而另一个脚本可能在模块级就 `import` 它。挂载点若写在 `main()` 里，**根本来不及运行**。
`init_skill_runtime.py` 会自动插到文档字符串与 `__future__` 导入之后、其余所有导入之前，并在插入后做语法校验（失败自动回滚）。

## 环境变量

`PREFIX` 取 `deps.json` 的 `env_prefix`（如 `MY_SKILL`）。

| 变量 | 作用 |
|---|---|
| `${PREFIX}_NO_AUTO_INSTALL=1` | 关闭自动安装，只检测并提示 |
| `${PREFIX}_RUNTIME_DIR=<dir>` | 指定运行时目录（内网可指向固定盘符） |
| `${PREFIX}_FIND_LINKS=<dirs>` | 指定本地 wheel 目录，多个用系统路径分隔符隔开 |
| `${PREFIX}_MIRROR=aliyun` | 换镜像源：`tsinghua`（默认）/ `aliyun` / `ustc` / `official` |
| `${PREFIX}_GROUPS=core,ocr` | 覆盖要处理的分组 |
| `${PREFIX}_QUIET=1` | 安静模式，只输出错误与最终结果 |

## 验证

```bash
# 自检：现场造一个合法 wheel，端到端验证「建 venv → 离线装 → 重跑」
python <本技能>/scripts/selftest.py
```

自检**不需要联网**（用标准库现造 wheel），覆盖：探测准确性、快速路径开销、`--check` 无副作用、纯离线安装、二次调用复用、关闭开关、失败即时退出、插入位置正确、幂等、产物洁净。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| 提示缺少依赖，但明明装过 | 装在了**别的**解释器里。跑 `skill_bootstrap.py --json` 看 `python` 字段实际用的是哪个 |
| 每次调用都重新装 | 运行时目录不可写，退回「当前解释器」兜底了。检查 `${PREFIX}_RUNTIME_DIR` 指向的盘是否可写 |
| 挂载点没生效 | 大概率插在了函数里或重依赖导入之后。用 `--dry-run` 重看插入位置；已在 `SKILL.md` 的「最关键约束」一节说明 |
| 内网装不上 | 确认 wheel 目录里**包含全部传递依赖**；`pip` 的报错会指明缺哪个包 |
| 不想让它自动下载 | `export ${PREFIX}_NO_AUTO_INSTALL=1` |
| 想同时用两套依赖 | 用 `--group` 分成多个分组，入口脚本各声明所需 |

## 设计取舍

为什么是「惰性引导」而不是「安装后挂载」、为什么用 `find_spec` 而不是 `import`、
四个真实踩过的坑（挂载点位置、探测副作用、测试假通过、并行编辑丢改动）—— 见
`references/design.md`。

集成到已有 skill 的完整步骤与验收清单见 `references/integration.md`。
