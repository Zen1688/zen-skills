---
name: agent-evaluation-loop
description: 当用户需要评估智能体能力（工具调用 BFCL、通用能力 GAIA、生成数据质量 AIME）、搭建评估系统（Dataset/Evaluator/Metrics 三件套 + Tool 化）、做基准测试（AST 匹配、归一化、诊断指标）、或把"评估→反推改进"形成闭环（LLM Judge、Win Rate、生成质量评估、CI/CD 门控）时使用。解决"分数虚高不会归因、评估成本高、报告结论与指标口径打架、依赖冲突"等问题。
slug: agent-evaluation-loop
version: 1.0.0
displayName: 智能体性能评估与改进闭环
agent_created: true
triggers:
  - 评估智能体
  - 跑 BFCL GAIA 基准
  - 评估生成数据质量
  - LLM Judge 打分
  - 评估闭环改进
  - AST 匹配
tags:
  - evaluation
  - benchmark
  - rag
  - llm-judge
---

# 智能体性能评估与改进闭环

## R — 原理锚点

> 三层评估体系：① 工具调用能力（BFCL）② 通用能力（GAIA）③ 生成数据质量（AIME）；每层给出"选择理由 + 适用场景 + 评估方法"（第 12 章 12.1.3、12.5 节，本书组织）。

这段为什么重要：它给出了"评什么"的顶层框架，避免只盯一个维度（如只测工具调用）而高估整体能力。

> 评估系统三层架构 + Tool 化：Dataset（加载/合并 ground truth）→ Evaluator（跑流程）→ Metrics（算指标），最外层封装成 Tool 供 Agent 直接调用（第 12 章 12.2.5、12.5 节，本书自创）。

这段为什么重要：把评估从一次性脚本变成可复用的"工具"，Agent 能自己调用自己做评估，是闭环自动化的基础。

> 智能体评估三大固有挑战：① 输出不确定性——同一问题多个正确答案；② 评估标准多样性——工具调用查函数签名、问答看语义相似度；③ 评估成本高昂——每次评估大量 API 调用，成本可达数百元甚至更多（第 12 章 12.1.1 节）。

这段为什么重要：它定义了本领域的"难在哪"，后面所有原则（官方工具、渐进门控、单一变量）都是为应对这三条而生。

> GAIA 诊断指标组：Exact Match Rate（整体）+ Level-wise Accuracy（分级）+ Drop Rate ℓ→ℓ+1（难度衰减）+ Avg Reasoning Steps（仅正确样本）；用"下降率"定位能力边界（第 12 章 12.3.1 节）。

这段为什么重要：它把"一个总分"翻译成"哪里弱"，是评估数字变成改进方向的标准手法（见 C 轨 GAIA 推演）。

> 生成质量三方法互补矩阵：LLM Judge = 绝对多维打分；Win Rate = 对参考真题的相对成对对比；人工 = 最终把关（第 12 章 12.4.1 节，本书组合）。

这段为什么重要：三者互补——绝对分、相对胜率、人工终审各有盲区，单用任一都会误判。

## I — 骨架

下面结构均来自本书第十二章，可直接照做。

### 一、评估系统三层架构 + Tool 化（F2）

```
Dataset(加载/合并 ground truth) → Evaluator(跑流程) → Metrics(算指标)
                        最外层封装成 Tool 供 Agent 直接调用
```

### 二、基准测试五步流程（F3，通用）

```
1. 加载数据集并选类别
2. 运行 Agent 取预测
3. 解析为 AST
4. 匹配判对错
5. 计算指标 + 生成报告
```

### 三、Evaluator 内部三要点（F4）

- 提示词构造
- 函数调用提取：JSON / 代码块 / 纯文本 三格式兜底
- AST 匹配

### 四、AST 匹配等价三条件（T 轨，12.2.1）

- 函数名精确一致
- 参数键值对集合相等（忽略顺序）
- 参数值语义等价（`2+3`≡`5`、`"hello"`≡`'hello'`）
- 多函数调用：数量相同、逐个匹配、顺序可不同

### 五、BFCL 四类别难度阶梯（F6）

| 类别 | 含义 | 难度 |
|---|---|---|
| simple | 单函数 | 低 |
| multiple | 多函数中选 | ↑ |
| parallel | 并行调用 | ↑↑ |
| irrelevance | 判断是否需要调用 | ↑↑↑ |

### 六、GAIA 五能力 × 三难度（F7）

- 能力：多步推理 / 知识运用 / 多模态理解 / 网页浏览 / 文件操作
- 难度：Level 1 / 2 / 3，共 466 题

### 七、归一化函数 N(·) 按类型分派（F10，GAIA 官方）

- 数字：去逗号 / 去 $ %
- 字符串：小写、去冠词、压空格、去尾标点
- 列表：逗号切分 → 逐元素归一化 → 字母序排序 → 重连
- 准精确匹配：`Quasi_EM = 1 iff N(A_pred) = N(A_true)`

### 八、指标组速查

**GAIA 诊断指标组（F8）**
- Exact Match Rate（整体）
- Level-wise Accuracy（分级）
- Drop Rate ℓ→ℓ+1 = (Acc_ℓ − Acc_{ℓ+1}) / Acc_ℓ，0 为理想
- Avg Reasoning Steps（仅对正确样本求平均）

**BFCL 指标组（F9）**
- Accuracy = AST 匹配率
- Category-wise Accuracy
- Weighted Accuracy = Σ w_c · Acc_c（Σw = 1）
- Error Rate = 1 − Accuracy

### 九、生成质量评估：LLM Judge 四维 + 三指标（F12）

- 维度（1–5 分）：正确性 / 清晰度 / 难度匹配 / 完整性
- 指标：Average Score、Pass Rate(≥3.5)、Excellent Rate(≥4.5)

### 十、渐进式评估门控（F13，本书自创）

```
5 样本快测 → 若 Acc>0.8 跑 50 → 若仍>0.8 跑全量(max_samples=0)
```

### 十一、三种使用层次（F14）

- Tool 一键：快速看表现
- CLI 脚本：批量、CI/CD
- Dataset + Evaluator：深度定制

### 十二、放行阈值（P9，12.4.8）

- LLM Judge 平均分 ≥ 4.0 / 5.0
- Win Rate ≥ 45%（接近 50%，Win Rate ≈50% 即"质量接近真题"）
- Pass Rate ≥ 80%
- 人工验证通过率 ≥ 90%

### 十三、完整闭环脚本（F15，12.4.7–12.4.8）

```
生成 30 题 → LLM Judge → Win Rate → 综合报告(含改进建议+下一步行动) → 人工验证 UI
```

## A1 — 案例

**GAIA 10 样本指标推演（12.3.1）**
- 场景：小样本跑 GAIA 看能力剖面。
- 做法：EM 70%，Level 1/2/3 = 100%/67%/50%，Drop 1→2 = 33%、2→3 = 25%。
- 可迁移教训：总分掩盖结构性问题，**分级 + 下降率**才能读出"中等难度已明显衰减、Level 3 是能力边界"——这是把评估数字翻译成改进方向的标准手法。

**BFCL 一键评估全流程（12.2.3）**
- 场景：快速看工具调用能力。
- 做法：4 步骤输出（跑评估 → 导出官方格式 → 官方复核 → 生成 md 报告）；报告含分类准确率、逐样本预测 vs 正确答案表、准确率条形可视化、建议段。
- 可迁移教训：评估产物必须包含"可回溯的逐样本明细"，否则无法做错误分析。

**GAIA 失败样本 `24000` vs 正确 `17`（12.3.3）**
- 场景：GAIA 某题答错。
- 做法：暴露的是缺工具（搜索/计算器）而非格式问题。
- 可迁移教训：诊断要区分"格式错"与"能力错"，别把工具缺失误判为格式问题。

**AIME 生成 + 评估闭环（12.4.7–12.4.8）**
- 场景：用 963 道真题作参考生成 30 题并评估。
- 做法：Judge 4.2/5.0、通过率 85%、优秀率 40% → Win 45%/Loss 40%/Tie 15% → 综合报告给主题分布（代数 33.3%…）与改进建议。
- 可迁移教训：**绝对分 + 相对胜率 + 分布统计**三者并列才能判断"能否投入使用"。

**LaTeX 破坏 JSON 解析（12.4.3）**
- 场景：`\frac`/`\sqrt` 触发 `Invalid \escape`。
- 做法：用正则 `(?<!\\)\\(?!["\\/bfnrtu])` 把未转义反斜杠翻倍后重试。
- 可迁移教训：LLM 结构化输出解析要有"先直解、失败再修复"的两段式兜底。

**答案提取的多级兜底（12.3.5）**
- 场景：提取 GAIA 最终答案。
- 做法：先匹配 `FINAL ANSWER:`，再试"答案/最终答案/Answer"等模式，最后取最后一个非空行。
- 可迁移教训：解析要有多级兜底，单一模式会漏。

**Gradio 人工验证 UI（12.4.6）**
- 场景：人工给生成数据打分。
- 做法：四滑块打分 + 三态标注（approved/rejected/needs_revision）+ 评论，结果落 `<data_path>_verifications.json`（含 scores、total_score、status、verified_at）。
- 可迁移教训：给人工评估配低摩擦界面与结构化存档，人评才可能规模化。

## A2 — 触发场景

出现以下任一情况时调用本 skill（判断要具体）：

- 用户说"我想测一下我的 Agent 工具调用/通用能力行不行"——对应 BFCL/GAIA（F1/F6/F7）。
- 用户问"BFCL 四个类别怎么跑、simple/multiple/parallel/irrelevance 分别是什么"——对应 F6。
- 用户要做"AST 匹配、归一化、Quasi Exact Match、Level-wise Accuracy、Drop Rate"——对应 T 轨/F8/F9/F10。
- 用户要"评估我生成的数据质量、用 LLM Judge 打分、算 Win Rate"——对应 F11/F12。
- 用户问"评估报告怎么写、放行阈值多少、要不要接 CI/CD"——对应 F15/P9/P11。
- 用户遇到"分数虚高不会归因、报告结论和指标打架、numpy 版本冲突、GAIA 要申请权限"——对应 A 轨各陷阱。
- 用户要"把评估结果反推去改提示词、迭代生成"——对应 P10 闭环动作。

## E — 执行步骤

1. **定评估层**：按 F1 选 ① BFCL（工具）② GAIA（通用）③ AIME（生成质量），明确"评什么 + 适用场景 + 方法"。产出物：评估目标清单。
2. **搭三件套**：Dataset → Evaluator → Metrics，最外层封装 Tool（F2）。产出物：可调用评估工具。
3. **跑基准五步**：加载并选类别 → 跑 Agent 取预测 → 解析为 AST → 匹配判对错 → 算指标出报告（F3）。产出物：指标 + 报告。
4. **按类别阶梯推进**：从 simple 稳定后再上 multiple/parallel/irrelevance，逐类分析失败案例（P4）。产出物：每类准确率剖面。
5. **做 GAIA 诊断**：算 EM + Level-wise + Drop Rate + Avg Reasoning Steps，定位能力边界（F8/C 轨）。产出物：分级衰减诊断。
6. **生成质量评估**：LLM Judge 四维打分（F12）+ Win Rate 成对对比（F11）+ 人工把关；生成用英文、API 间加 2–3 秒延迟、启用 checkpoint、先小批 10 个试跑（P7/P8）。产出物：Judge 分、胜率、人评。
7. **渐进门控**：5 样本 → Acc>0.8 跑 50 → 仍>0.8 跑全量（F13），控制成本（应对 A1 成本高）。产出物：门控通过的样本规模。
8. **对比评估**：只改一个变量（默认 vs 优化提示词，同类别同样本数）（P5）；多类别横扫看剖面非单一总分（P6）。产出物：可比对的 A/B 结果。
9. **闭环改进**：按结果调生成提示词、分析低分共性、参考高分优点、持续迭代（P10）；集成 CI/CD 设阈值、报告归档（P11）；扩展新基准照抄 Dataset/Evaluator/Metrics 三件套（P12）。产出物：改进后下一轮评估。

## B — 边界与失效条件

- **低分别误归因（A2/A4）**：自定义格式 `[TOOL_CALL:...]`（SimpleAgent）是分数天花板，复杂场景弱于原生 Function Calling——低分可能是"接口协议问题"而非模型能力；只测最简类别会高估能力（A3）。
- **"流程跑通"≠"能力达标"（A4）**：演示用 Agent 分数不能代表框架能力，GAIA 结果不理想可能是缺工具（搜索/计算器）而非格式（见 C 轨 24000 vs 17）。
- **Win Rate 异常高要怀疑评估本身（A5）**：显著高于 50% 可能说明生成题超越真题或评估标准有偏——先审 judge/提示词。
- **自动化评估有盲区（A6）**：严格逻辑推理的数学内容人工验证不可替代；LLM Judge 与 Win Rate 只能减负不能取代终审。
- **LLM Judge 偏见风险（A7）**：需分析其对回答风格偏好、对长度敏感性等局限。
- **AST 匹配可能误判（A8）**：存在假阳性/假阴性；准精确匹配对"42"/"四十二"/"42.0"等语义等价覆盖不全（A9）。
- **报告文案与指标口径打架（A10）**：Win Rate 45% 在 12.4.1 属"略低于真题"，但报告模板可能输出"优秀"——自动结论文案必须与指标口径严格对齐。
- **工程性坑（A11）**：`bfcl-eval` 强制 `numpy<=2.0.0`，需单独 `pip install "numpy==1.26.4" bfcl-eval`（P13）；GAIA 是 Gated Dataset，需申请权限 + HF_TOKEN，首次下 114 个文件（12.3.2）；API 速率限制需延迟与 checkpoint（12.4.3/12.4.8）。
- **成本代价（A1）**：每次评估大量 API 调用，成本可达数百元——用 F13 渐进门控、P5 单一变量、P6 多类别横扫来节制。

## 配套技能

本技能是 **AI Agent 全生命周期套件**（`zen-agent-suite`）的第 8/10 环。
从需求分析到交付运维，覆盖构建一个 AI Agent 产品的完整链路。

> **只装本技能不足以覆盖完整需求。** 若你正在做的是「创建 AI Agent/搭建智能体」这类完整任务，建议一并安装同套件的其他 9 个技能 —— 它们分别负责需求、设计、验证、运维等环节，缺环会导致流程断在中途。

**同套件技能**（按推荐使用顺序）：

| 阶段 | 技能 | 作用 |
|---|---|---|
| ① 需求 | `agent-requirement-analysis` | 判断该不该用 Agent、拆解任务与定义验收标准 |
| ② 设计 | `agent-paradigm-selection` | 选 ReAct / Plan-and-Solve / Reflection 范式 |
| ② 设计 | `agent-framework-architecture` | 框架选型与分层架构设计 |
| ② 设计 | `agent-memory-rag-design` | 记忆系统与 RAG 检索链路设计 |
| ② 设计 | `agent-context-engineering` | 上下文工程与 GSSC 流水线 |
| ② 设计 | `agent-protocol-selection` | MCP / A2A / ANP 协议选型与集成 |
| ② 设计 | `multi-agent-orchestration` | 多智能体协作编排与成本控制 |
| ③ 验证 | `agent-evaluation-loop` ← **本技能** | 评估系统搭建与改进闭环 |
| ④ 运维 | `agent-delivery-ops` | 交付上线、成本控制与安全护栏 |
| ⑤ 进阶 | `agentic-rl-pipeline` | Agentic-RL 训练流水线（可选进阶） |

**一键安装整套**：

```bash
# WorkBuddy（手工拷贝）
git clone --depth 1 git@github.com:Zen1688/zen-skills.git
cp -r zen-skills/skills/agent-* zen-skills/skills/multi-agent-orchestration \
      ~/.workbuddy/skills/
```

```bash
# Claude Code（插件市场）
claude plugin marketplace add Zen1688/zen-skills
claude plugin install zen-agent-suite@zen-skills
```

**只想装这一个**：单个技能可独立使用 —— 例如你的需求只是「评估系统搭建与改进闭环」，装 `agent-evaluation-loop` 即可，后续需要时再补装对应环节。
---

> **来源**：蒸馏自《Hello-Agents：从零开始构建智能体》V1.0.3（Datawhale 开源教材）第 12 章（智能体性能评估）。
原始蒸馏产物与知识卡片留存于本地蒸馏输出目录，不随本仓库分发。
