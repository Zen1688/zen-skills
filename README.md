# zen-skills

自研 Agent Skill 集合 —— 遵循 [Agent Skills](https://agentskills.io) 规范的通用技能仓库。

每个技能是一个自包含目录，可安装到任何支持 Agent Skills 的宿主环境。

---

## ⚠️ 技能之间有关系，别只装一个

仓库里的技能**不是孤立的**。有 10 个 Agent 技能构成一个套件 —— **AI Agent 全生命周期套件（`zen-agent-suite`）**，它们分别负责需求、设计、验证、运维等环节，**一起用才能覆盖「创建一个 AI Agent」这类完整需求**。

只装其中一个，流程会断在中途。装之前先看这张表：

| 阶段 | 技能 | 作用 |
|---|---|---|
| ① 需求 | `agent-requirement-analysis` | 判断该不该用 Agent、拆解任务与定义验收标准 |
| ② 设计 | `agent-paradigm-selection` | 选 ReAct / Plan-and-Solve / Reflection 范式 |
| ② 设计 | `agent-framework-architecture` | 框架选型与分层架构设计 |
| ② 设计 | `agent-memory-rag-design` | 记忆系统与 RAG 检索链路设计 |
| ② 设计 | `agent-context-engineering` | 上下文工程与 GSSC 流水线 |
| ② 设计 | `agent-protocol-selection` | MCP / A2A / ANP 协议选型与集成 |
| ② 设计 | `multi-agent-orchestration` | 多智能体协作编排与成本控制 |
| ③ 验证 | `agent-evaluation-loop` | 评估系统搭建与改进闭环 |
| ④ 运维 | `agent-delivery-ops` | 交付上线、成本控制与安全护栏 |
| ⑤ 进阶 | `agentic-rl-pipeline` | Agentic-RL 训练流水线（可选） |

### 怎么装才不出错

**要做完整件事（如创建 AI Agent）→ 一键装整套**

```bash
# Claude Code：一个 bundle 插件带装全部 10 个
claude plugin marketplace add Zen1688/zen-skills
claude plugin install zen-agent-suite@zen-skills

# WorkBuddy：手工拷贝整套
git clone --depth 1 git@github.com:Zen1688/zen-skills.git
cp -r zen-skills/skills/agent-* zen-skills/skills/multi-agent-orchestration \
      ~/.workbuddy/skills/
```

**只要某一环（如只做需求拆解）→ 单装即可，但要留意缺环**

单个技能可独立使用，安装时其 `SKILL.md` 的「配套技能」段落会列出同套件的其他成员，需要时再补装。

> **为什么不做强制带装**：Agent Skills 规范**没有依赖字段**（只允许 `name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools`），技能无法自行声明依赖。
> Claude Code 的插件层虽支持 `dependencies`，但强制带装会让「只装一个」变得不可能，反而更糟。
> 因此本仓库采用**软提醒 + bundle 入口**：整套走 bundle 一键装，单装则在文档层和对话中主动提示缺环。

---

## 技能清单

共 17 个技能，按用途分组。

### 智能体工程（Agent Engineering）

覆盖 Agent 产品从需求到运维的完整生命周期，外加若干横切方法论。

> 下表前 10 个技能构成 **AI Agent 全生命周期套件（`zen-agent-suite`）**，
> 建议整套安装（见文首「技能之间有关系，别只装一个」）。

| 技能 | 说明 |
|---|---|
| [agent-requirement-analysis](skills/agent-requirement-analysis/) | **生命周期的第一环**：判断需求该不该用 Agent、拆解任务/角色/工具、定义边界与验收标准 |
| [agent-paradigm-selection](skills/agent-paradigm-selection/) | 经典范式选型：ReAct / Plan-and-Solve / Reflection 的适配判断与实现 |
| [agent-framework-architecture](skills/agent-framework-architecture/) | 框架选型（AutoGen/AgentScope/CAMEL/LangGraph/自研）与分层架构设计 |
| [agent-protocol-selection](skills/agent-protocol-selection/) | 通信协议选型：MCP / A2A / ANP 的集成与多智能体通信 |
| [agent-memory-rag-design](skills/agent-memory-rag-design/) | 记忆系统（工作/情景/语义/感知）与 RAG 检索增强链路设计 |
| [agent-context-engineering](skills/agent-context-engineering/) | 上下文工程：GSSC 流水线（Gather→Select→Structure→Compress）与分层上下文架构 |
| [multi-agent-orchestration](skills/multi-agent-orchestration/) | 多智能体协作编排：角色拆分、数据契约、并发与成本治理 |
| [agentic-rl-pipeline](skills/agentic-rl-pipeline/) | Agentic-RL 训练流水线：六阶段端到端流程、GRPO 与故障归因 |
| [agent-evaluation-loop](skills/agent-evaluation-loop/) | 评估与改进闭环：评估系统三件套、基准测试、LLM Judge、CI/CD 门控 |
| [agent-delivery-ops](skills/agent-delivery-ops/) | **生命周期的最后一环**：交付上线、token 成本控制、可观测性与安全合规护栏 |

### 文档工程（Document Engineering）

| 技能 | 说明 |
|---|---|
| [doc-suite-architecture-audit](skills/doc-suite-architecture-audit/) | 成套文档架构级审阅：交叉引用解析、术语覆盖矩阵、结构密度量化，输出五维缺口清单 |
| [markdown-bulk-edit](skills/markdown-bulk-edit/) | 大体量 Markdown 多处精确替换：脚本化批处理 + 写盘前命中数校验 + 改后反查清单 |
| [markdown-to-pdf-merge](skills/markdown-to-pdf-merge/) | 多 Markdown 合并为带总纲目录的 PDF：A4 中文排版、章前分页、目录页码可跳转 |
| [workbuddy-doc-to-markdown](skills/workbuddy-doc-to-markdown/) | WorkBuddy 资料库在线文档落地为本地 Markdown：节点判定、原文抓取、组件标记转换 |

### 工具箱（Toolkit）

| 技能 | 说明 | 主要依赖 |
|---|---|---|
| [image-toolkit](skills/image-toolkit/) | 离线图片处理工具箱：格式转换 / OCR 文字识别 / 内容分类 / 导出 Office 文档。**全程无网络调用**，适配国内无网、内网环境 | Pillow, openpyxl, python-docx, reportlab, numpy, rapidocr-onnxruntime |
| [name-availability-check](skills/name-availability-check/) | 命名可用性核验：查 Maven Central / GitHub / npm / PyPI / 商标 / 域名占用，识别撞名与显著性缺失 | 无（纯标准库） |

### 开发支撑（Development）

| 技能 | 说明 | 主要依赖 |
|---|---|---|
| [skill-bootstrap](skills/skill-bootstrap/) | 给 Python 编写的 skill 加上**运行时自举**：首次调用自动补齐依赖、路径自动探测，支持纯离线/内网安装。也是本仓库其他技能依赖引导机制的来源 | 无（纯标准库） |


---

## WorkBuddy 安装

**方式一：安装全部技能**

```bash
git clone git@github.com:Zen1688/zen-skills.git
cd zen-skills
cp -r skills/* ~/.workbuddy/skills/
```

**方式二：只装某一个技能**

```bash
git clone --depth 1 git@github.com:Zen1688/zen-skills.git

# macOS / Linux
cp -r zen-skills/skills/image-toolkit ~/.workbuddy/skills/

# Windows (Git Bash)
cp -r zen-skills/skills/image-toolkit /c/Users/<你的用户名>/.workbuddy/skills/
```

安装后**重启 WorkBuddy** 即可识别。

**安装位置**

| 类型 | 路径 | 生效范围 |
|---|---|---|
| 用户级 | `~/.workbuddy/skills/` | 所有项目可用 |
| 项目级 | `{项目目录}/.workbuddy/skills/` | 仅该项目可用，适合团队共享 |

---

## Claude Code 安装

本仓库已配置为 Claude Code Plugin Marketplace，可直接通过插件命令安装。

**第一步：注册 marketplace**

```
/plugin marketplace add Zen1688/zen-skills
```

**第二步：安装插件**

本仓库共提供 18 个插件：1 个套件 bundle + 17 个单技能。

**推荐：要做完整的 Agent 产品，直接装套件**

```
/plugin install zen-agent-suite@zen-skills   # 一次带装全部 10 个 Agent 技能
```

**只要某一环，或非 Agent 类技能，按需单装**：

```
/plugin install agent-requirement-analysis@zen-skills # Agent 需求分析与任务拆解
/plugin install image-toolkit@zen-skills              # 离线图片处理工具箱
/plugin install markdown-to-pdf-merge@zen-skills      # Markdown 合订本 PDF
/plugin install skill-bootstrap@zen-skills            # skill 依赖自动引导（开发用）
```

也可以用交互式菜单：`/plugin` → `Browse and install plugins` → `zen-skills` → 选择目标 → `Install now`。

**非交互式（脚本化）等价命令**

```bash
claude plugin marketplace add Zen1688/zen-skills
claude plugin install zen-agent-suite@zen-skills
```

安装后可显式调用（`<插件名>:<技能名>`）：

```
/image-toolkit:image-toolkit
```

或者直接在对话里描述需求，由 Claude 依据技能描述自动触发。

**套件 bundle 的依赖解析**

`zen-agent-suite` 通过 Claude Code 原生的插件 `dependencies` 机制带装 10 个技能。安装时命令会列出实际装入了哪些依赖；若某个依赖后来丢失，`/reload-plugins` 会自动重装（前提是 marketplace 已注册）。

**安装位置与更新**

| 项 | 说明 |
|---|---|
| 插件缓存 | `~/.claude/plugins/cache/zen-skills/image-toolkit/<版本>/` |
| 刷新技能 | `claude plugin marketplace update zen-skills` |
| 校验清单 | `claude plugin validate .`（在仓库根执行） |

> 插件按版本号缓存，**更新技能后需要重新安装或刷新 marketplace**。

---

## 依赖安装（两种宿主通用）

**通常不需要手动操作** —— 技能内置依赖引导器（`bootstrap.py`），
首次调用任一功能脚本时会自动检测并补齐依赖。

| 情况 | 行为 |
|---|---|
| 依赖齐全 | 立即返回，几乎无额外开销 |
| 本机已有备好依赖的解释器 | 直接复用，不重复安装 |
| 需要安装 | 建独立 venv → 装依赖 → 用新解释器重跑当前脚本 |
| 有本地 wheel 目录 | `--no-index` **纯离线安装**，不联网 |
| 无网又无本地包 | 立即报错并打印补齐方式，不挂起 |

默认装到 `~/.image-toolkit/venv`：跨副本共享、只装一次，**不污染宿主环境**。
装核心依赖约 26MB，含 OCR 约 95MB（仅首次）。

想提前装好或排查：

```bash
python <技能目录>/scripts/bootstrap.py           # 缺什么装什么
python <技能目录>/scripts/bootstrap.py --check   # 只检查
python <技能目录>/scripts/selftest.py            # 端到端自检（10 项）
```

关掉自动安装（改为只提示不下载）：

```bash
IMAGE_TOOLKIT_NO_AUTO_INSTALL=1
```

**完全离线安装**（内网）：把 wheel 目录放到 `<技能目录>/wheelhouse/`，
或用 `IMAGE_TOOLKIT_FIND_LINKS=<wheel 目录>` 指定，引导器会自动发现并离线安装；
离线依赖包用技能自带的 `deploy_offline.py pack` 生成。

> **为什么用「首次调用引导」而不是安装后挂载**：Agent Skills 规范只约定
> 技能的文件结构与加载方式，不包含运行时依赖管理；`pip` 也没有
> post-install 钩子，两个宿主都没有「安装后自动执行」的通用机制。
> 因此本仓库把补齐依赖做成**首次调用时的惰性引导** —— 技能目录里不需要任何宿主专有配置，两个生态行为完全一致。
>
> 这套机制已抽成独立技能 [**skill-bootstrap**](skills/skill-bootstrap/)，
> 任何 Python 技能都可以用它一键接入。详见该技能的 `SKILL.md` 与 `references/integration.md`。

---

## 技能目录规范

```
skills/<skill-name>/
├── SKILL.md          # 必需：YAML frontmatter（name + description）+ 指令正文
├── scripts/          # 可选：可执行脚本
├── references/       # 可选：按需加载进上下文的参考文档
└── assets/           # 可选：输出用素材（模板 / 图标 / 字体）
```

仓库还有两个非技能目录：

```
bundles/<suite-name>/          # 套件 bundle 插件（仅含 .claude-plugin/plugin.json 的依赖清单）
tools/                         # 维护脚本：依赖表 SSOT、批量替换、marketplace 生成
```

`SKILL.md` 的 frontmatter 最小形态：

```yaml
---
name: skill-name
description: 技能做什么、什么时候用（决定 AI 何时触发该技能）
---
```

---

## 技能依赖维护（重要）

技能之间的「配套关系」是**由脚本生成、不要手工编辑**，避免多处入口漂移。

**单一事实来源**：[`tools/suite_deps.py`](tools/suite_deps.py) —— 套件成员、阶段标签、一句话定位都在这里。

改动依赖关系后，按顺序重跑：

```bash
# 1. 校验依赖表自洽（套件成员是否完整、BLURB/STAGE 是否齐全）
python tools/suite_deps.py --check

# 2. 重新生成 10 个 SKILL.md 的「配套技能」段落
#    （带写盘前命中数校验：每个文件必须恰好命中 1 次，否则整体中止不写入）
python tools/apply_companion_sections.py

# 3. 重新生成 marketplace.json（description 标注 + bundle 插件 + 版本号）
python tools/update_marketplace.py
```

三个脚本都是**幂等**的，重复执行不会产生重复内容。

> **为什么依赖不写在 SKILL.md frontmatter 里**：Agent Skills 规范只允许
> `name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools`，
> **没有依赖字段**。因此技能无法在元数据层声明依赖，只能落到两处：
> 宿主安装层（`marketplace.json`，仅 Claude Code 读）与文档层（`SKILL.md` 正文，所有宿主都读）。
> WorkBuddy 走手工拷贝、不读 marketplace.json，所以正文里的「配套技能」段落是它唯一的提醒通道。

---

## 开发：新增一个技能

```bash
mkdir -p skills/<new-skill>
# 编写 skills/<new-skill>/SKILL.md
# 若为 Python 技能：用 skill-bootstrap 装上依赖自动引导（含路径自动探测）
python skills/skill-bootstrap/scripts/init_skill_runtime.py skills/<new-skill> \
    --core "PIL=Pillow" --entry main.py:core --dry-run
git add skills/<new-skill>
git commit -m "feat: 新增 <new-skill> 技能"
git push
```

**若新技能属于某个套件**（如加入 `zen-agent-suite`），还需在 `tools/suite_deps.py` 的
`SUITES` / `BLURB` / `STAGE` 三处登记，然后重跑上面「技能依赖维护」的三个脚本，
让所有技能的配套表格与 marketplace 自动同步。

若新技能也要通过 Claude Code 安装，在 `.claude-plugin/marketplace.json` 的 `plugins` 数组里追加一条：

```json
{
  "name": "<new-skill>",
  "description": "一句话说明",
  "source": "./",
  "strict": false,
  "skills": ["./skills/<new-skill>"]
}
```

约定：

- 一个技能一个目录，目录名与 frontmatter 的 `name` 保持一致
- Python 技能请用 [skill-bootstrap](skills/skill-bootstrap/) 接入依赖自动引导；
  脚本内部**不要硬编码绝对路径**，用 `Path(__file__).resolve().parent` 定位自身
- 不要依赖宿主专有字段，保持技能平台中立
- 提交前确认没有 `__pycache__`、虚拟环境、日志等产物入库（`.gitignore` 已覆盖）

---

## 许可证

[MIT](LICENSE)
