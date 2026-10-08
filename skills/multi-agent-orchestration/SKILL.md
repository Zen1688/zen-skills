---
name: multi-agent-orchestration
description: 当需要将复杂任务拆解为多个职责单一的智能体（如旅行规划、深度研究、AI NPC、多 Agent 文档处理）并设计它们的协作流程、数据契约与成本控制时使用；解决单 Agent 工具过多导致复杂度爆炸、串行调用成本高、并发成本失控、中央协调器单点故障等问题。
slug: multi-agent-orchestration
version: 1.0.0
displayName: 多智能体协作编排与成本控制
agent_created: true
triggers:
  - 多智能体协作
  - 多Agent编排
  - 智能体成本优化
tags:
  - 多智能体
  - 编排
  - 成本控制
---

# 多智能体协作编排与成本控制（multi-agent-orchestration）

## R — 原理锚点

> "AutoGen/CAMEL 靠角色 + 目标让协作涌现（灵活难预测）；LangGraph 显式定义每步（可控可审计但繁琐）。依可靠性需求取舍。"（第6章 6.6 节）

这段为什么重要：协作模式决定系统的可预测性与维护成本。可靠性要求高时选显式控制，探索性强时选涌现式，先定模式再选框架。

> "每个 Agent 只做一件事。"（第13章 13.3.2 节）

这段为什么重要：单一职责是拆分的前提。职责越窄，提示词越易写、输出越可控、跨任务可复用性越高。

> "多智能体用'问题分类器'做智能路由，为每个子体明确定义核心功能与任务范围。"（第5章 5.3.2 节）

这段为什么重要：没有分类路由，请求会错配到错误 Agent，导致结果错误或空转，协作失去意义。

> "MCP 实例共享（auto_expand=True）避免多 Agent 重复建连触发速率限制。"（第13章 13.4.3 节）

这段为什么重要：每个 Agent 各自建连会触发外部服务速率限制，共享实例是规模化协作的硬性前提。

> "中央协调器（星型拓扑）三大失败模式：单点故障导致整体瘫痪、所有通信过中心节点限制并发、增改智能体要动中心逻辑。"（第10章 10.3.1 节）

这段为什么重要：提醒架构选型避开单点瓶颈，协作拓扑本身就有可用性代价，不能无脑用中心化。

## I — 骨架

### 骨架一：前后端分离四层架构（第13/14/15章 13.1.2 / 14.1.2 / 15.1.2 节）

| 层 | 职责 | 技术 |
|---|---|---|
| 前端层 | 交互与展示 | Axios、html2canvas |
| 后端层 | 接口与编排 | FastAPI |
| 智能体层 | 多 Agent 协作 | HelloAgents |
| 外部服务层 | 工具与数据 | MCP、搜索 API |

### 骨架二：Pydantic 自底向上数据模型（第13章 13.2.4 节）

约束跨 Agent 数据契约，从原子到顶层逐级组合：
1. 定义原子 `Location`（名称/经纬度）
2. 组合 `Attraction` / `Meal` / `Hotel`（引用 Location）
3. 组合 `DayPlan`（含多个 Attraction/Meal/Hotel）
4. 顶层 `TripPlan`（含多个 DayPlan）

### 骨架三：多 Agent 顺序协作流程（第13章 13.3.3 节 / 第14章 14.3.3 节）

```
TripPlannerAgent.plan_trip():
  1. 搜景点  → AttractionSearch
  2. 查天气  → WeatherQuery
  3. 定酒店  → Hotel Agent
  4. 规划日程 → DayPlan 组合
  5. 组行程  → 输出 TripPlan
```

### 骨架四：TODO 驱动三阶段研究范式（第14章 14.2.1–14.2.2 节）

```
Planner  : 拆解 3–5 子任务（正则抽 JSON）
TaskAgent: 执行子任务 + 用 NoteTool 写笔记到 workspace/notes/*.md
Writer   : 汇总笔记 → 报告
```

### 骨架五：ToolAwareSimpleAgent（第14章 14.3.2 节）

继承 `SimpleAgent`，注入 `tool_call_listener` 回调捕获工具调用事件，驱动 SSE 经 `StreamingResponse` 推进度。

### 骨架六：NPC 记忆双层架构（第15章 15.2.3 节）

| 记忆层 | 类型 | 实现 | 容量/过期 |
|---|---|---|---|
| WorkingMemory | 短期 | 内存 | capacity=10, ttl=120min |
| EpisodicMemory | 长期 | SQLite + Qdrant 向量检索 | 持久 |

### 骨架七：批量生成 + 即时响应混合模式（第15章 15.2.4 节）

离线用 `NPCBatchGenerator` 一次 LLM 调用生成全部 NPC 对话省成本；在线仅做即时交互。

### 骨架八：协作模式选型（第6章 6.2.1 / 6.3.1 / 6.5.1 / 6.6 节）

| 模式 | 机制 | 适用 |
|---|---|---|
| RoundRobinGroupChat | 固定顺序发言 | 流程固定任务 |
| MsgHub 消息驱动 | 消息收发为单元 | 以消息代替状态机 |
| 状态机图 | State+Node+Edge+条件边 | 需容错/支持循环 |
| 涌现式 | 角色 + 目标 | 探索性任务 |

### 骨架九：原则清单（P1–P10）

- P1 复杂任务拆 3–5 子任务（14.2.1 / 14.5.1）
- P2 MCP 实例共享 `auto_expand=True`（13.4.3）
- P3 Agent 提示词简洁、单一职责（13.3.2）
- P4 搜索结果去重 + Token 限制 + 缓存（14.4.1）
- P5 JSON 解析多策略 + 字段验证（14.5.1）：正则提取 → 容错解析 → 校验后回填
- P6 NPC 忙碌状态锁防并发（15.4.2）
- P7 问题分类器做智能路由（5.3.2）
- P8 System Prompt 管长期准则与输出格式，User Prompt 管具体任务与数据源（5.2.2）
- P9 混合开发：平台快速验证 + 代码精细控制（5.1.1 / 5.6）
- P10 结构化输出用 BaseModel 约束规则（6.3.2）

## A1 — 案例

**C1 旅行助手（第13章）**
- 场景：用户要一站式旅行规划。
- 做法：AttractionSearch / WeatherQuery / Hotel / Planner 四 Agent 顺序产出 TripPlan；前端 Axios 超时设 120000ms，html2canvas 导出行程图。
- 可迁移教训：顺序协作 + 共享数据模型是多 Agent 落地的通用骨架。

**C2 深度研究（第14章）**
- 场景：开放式研究课题。
- 做法：`PlanningService._extract_tasks` 正则抽 JSON 子任务；`SearchService` 多引擎（Tavily / DuckDuckGo / Perplexity / SearXNG）；NoteTool 落盘 `workspace/notes/*.md`；SSE 经 `StreamingResponse` 推进度。
- 可迁移教训：TODO 驱动把"规划—执行—汇总"三段解耦，进度可观测、可审计。

**C3 赛博小镇（第15章）**
- 场景：游戏内多 NPC 持续对话。
- 做法：`create_npc_agent` 装配双层记忆；`NPCBatchGenerator` 一次 LLM 调用生成全部 NPC 对话；`RelationshipManager.analyze_sentiment`（友好 +5 / 中立 +2 / 不友好 −3，限 −3~5）；Godot `api_client.gd` 用 signal 通信。
- 可迁移教训：批量生成 + 双层记忆既控成本又保证长期一致性。

**C4 AutoGen 软件开发团队（第6章 6.2.2 节）**
- 场景：自动化软件开发。
- 做法：PM / 工程师 / 审查员 / UserProxy + 轮询群聊，需求 → 编码 → 审查 → 测试；`TextMentionTermination("TERMINATE")` + `max_turns` 控终止。
- 可迁移教训：用 System Message 做提示工程定义角色是多智能体设计核心。

**C5 AgentScope 三国狼人杀（第6章 6.3.2 节）**
- 场景：多角色博弈。
- 做法：以消息驱动代替状态机；`MsgHub` 临时私密频道；`fanout_pipeline` 并行收集投票。
- 可迁移教训：以消息驱动代替状态机，减少拓扑耦合。

**C6 CAMEL 拖延症电子书（第6章 6.4.2 节）**
- 场景：双专家协作产出。
- 做法：心理学家 + 作家双智能体，`init_chat()` / `step()` 驱动，`<CAMEL_TASK_DONE>` 终止。
- 可迁移教训：双专家角色扮演 + 引导性提示（一次一步骤、末尾标志）实现自主深度协作。

**C7 LangGraph 三步问答（第6章 6.5.2 节）**
- 场景：带检索的问答。
- 做法：understand → search → answer；search 失败用 `state["step"]="search_failed"` 回退 LLM 自身知识。
- 可迁移教训：用状态字段驱动条件边实现容错。

**C8 多 Agent 协作文档助手（第10章 10.2.4(3) 节）**
- 场景：文档生成。
- 做法：GitHub 搜索专家（挂 `gh` MCP）→ 文档生成专家（挂 `fs` MCP）；system_prompt 强约束单一职责与输出格式；前一 Agent 输出拼进后一 prompt。
- 可迁移教训：把前一输出当后一输入拼进 prompt，是最小成本编排。

## A2 — 触发场景

在以下具体情况下应调用本 skill：
1. 需要把"景点搜索 / 天气 / 酒店 / 行程"等多个职责拆成多个 Agent 顺序协作（C1）。
2. 需要做"先规划子任务 → 搜索 → 写笔记 → 汇总报告"的开放式研究（C2）。
3. 需要给游戏 NPC 配记忆，且担心多玩家并发 LLM 成本失控（C3 / A5）。
4. 需要用一个"问题分类器"把请求路由到不同专属 Agent（P7）。
5. 需要在 AutoGen / AgentScope / CAMEL / LangGraph 间选型协作模式（C4–C7、F8–F11）。
6. 遇到单 Agent 工具过多、中间结果靠参数传递导致复杂度爆炸（A1）。
7. 需要跨 Agent 统一数据契约（Pydantic 模型）或统一 MCP 实例共享（P2）。

## E — 执行步骤

1. **定模式**：按可靠性需求选涌现式或显式控制（F8）。产出：协作模式决策（固定流程 / 自由协作 / 状态机）。
2. **拆职责**：把任务拆成 3–5 个单一职责 Agent（P1 / P3）。产出：Agent 职责清单。
3. **建路由**：用问题分类器把请求分发到对应 Agent（P7）。产出：路由规则。
4. **定数据契约**：自底向上定义 Pydantic 模型（原子→组合→顶层）（F2）。产出：跨 Agent 数据结构。
5. **连外部服务**：MCP 实例共享 `auto_expand=True`（P2）；Agent 经 MCP 工具调用，禁止直接调 API（A3）。产出：共享 MCP 配置。
6. **排协作流程**：选顺序 / 轮询 / 消息驱动之一（F3 / F9 / F11）。产出：调用顺序或图。
7. **控成本**：搜索去重 + Token 限制 + 缓存（P4）；NPC 用批量生成 + 即时响应（F7）；并发加忙碌锁（P6）。产出：成本与并发方案。
8. **做结构化输出**：用 BaseModel 约束输出格式（P10）；JSON 解析多策略 + 校验（P5）。产出：稳定可解析输出。

## B — 边界与失效条件

- **不该用**：单 Agent 即可完成的简单任务（A8 过度工程化）；纯单轮对话无需协作（转 `agent-paradigm-selection`）。
- **风险 A1**：单 Agent 工具多、中间结果靠参数传递，复杂度爆炸 → 应拆多 Agent。
- **风险 A2**：ReactAgent 串行调用时间成本高 → 用分工并行 / 预取。
- **风险 A3**：直接调 API 绕过 Agent 会失去自主决策 → 必须经 MCP 工具。
- **风险 A4**：html2canvas 嵌套 Canvas / 跨域地图导出失败 → 改用隐藏地图方案。
- **风险 A5**：多玩家并发 LLM 调用成本失控 → 批量生成降本。
- **风险 A6**：AI NPC 成本 / 延迟 / 内容失控 → 需预算、缓存、内容审核三道防线。
- **风险 A7**：AutoGen 对话不确定性致偏离 / 循环，"对话式调试"难（只有对话历史无错误栈）。
- **风险 A8**：AgentScope 简单场景过度工程化。
- **风险 A9**：CAMEL 高度依赖提示质量、调试难、缺复杂路由 / 分布式状态 / 仲裁。
- **风险 A10**：LangGraph boilerplate 多、调试需全局理解图。
- **风险 A11**：中央协调器星型拓扑三大失败模式（单点故障 / 并发受限 / 改造需动中心）。
- **成本代价**：多 Agent 带来额外编排、调用与显存开销；混合开发需平台 + 代码两套投入（P9）。

## 配套技能

本技能是 **AI Agent 全生命周期套件**（`zen-agent-suite`）的第 7/10 环。
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
| ② 设计 | `multi-agent-orchestration` ← **本技能** | 多智能体协作编排与成本控制 |
| ③ 验证 | `agent-evaluation-loop` | 评估系统搭建与改进闭环 |
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

**只想装这一个**：单个技能可独立使用 —— 例如你的需求只是「多智能体协作编排与成本控制」，装 `multi-agent-orchestration` 即可，后续需要时再补装对应环节。
---

> **来源**：蒸馏自《Hello-Agents：从零开始构建智能体》V1.0.3（Datawhale 开源教材）第 6、13、14、15、16 章（多智能体协作与综合案例）。
原始蒸馏产物与知识卡片见 `<本地蒸馏输出目录>`。
