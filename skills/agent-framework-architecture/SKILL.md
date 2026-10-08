---
name: agent-framework-architecture
description: 当需要为智能体项目选择框架（AutoGen/AgentScope/CAMEL/LangGraph/自研）、设计自研框架的分层架构与工具系统、做多智能体编排或设置防无限循环的安全阀时使用。解决"选哪个框架、怎么自研、如何编排、有哪些坑"的问题。
slug: agent-framework-architecture
version: 1.0.0
displayName: 自研智能体框架架构方法论
agent_created: true
triggers:
  - 选择智能体框架
  - 自研智能体框架
  - 多智能体编排
tags:
  - 框架选型
  - 架构设计
  - 多智能体
  - 自研框架
---

# 自研智能体框架架构方法论

## R — 原理锚点

**R1（框架本质）。** 框架本质 = 抽象通用"规范"：封装主循环/状态/工具/日志，开发者专注业务逻辑。（第6章 6.1.1节）
> 为什么重要：理解"框架为什么存在"，才能决定自研还是复用，避免重复造轮子。

**R2（自建动机）。** 自建框架四动机：规避过度抽象、版本不稳定、黑盒、依赖膨胀，以获得完全控制权 + 可定制 + 教学透明。（第7章 7.1.1节）
> 为什么重要：这是判断"要不要自研"的判据来源，不是所有项目都值得自研。

**R3（两种协作哲学）。** 涌现式协作（AutoGen/CAMEL 靠角色+目标让协作涌现，灵活难预测）vs 显式控制（LangGraph 显式定义每步，可控可审计但繁琐）。（第6章 6.6节）
> 为什么重要：依可靠性需求取舍两种设计哲学——要灵活还是要可控。

**R4（核心架构原则）。** 分层解耦 / 职责单一 / 接口统一是核心架构原则。（第7章 7.1.3节）
> 为什么重要：这是 HelloAgents 自研架构的设计准绳，也是任何框架该有的骨架。

**R5（万物皆为工具）。** Memory/RAG/RL/MCP 统一抽象为 Tool，消除不必要抽象层。（第7章 7.1.2(4)节）
> 为什么重要：统一抽象能避免为每类能力各造一套抽象，降低复杂度。

## I — 骨架

### 骨架1：框架选型四维对比 + 决策
表 6.1 四维对比（协作模式 / 控制方式 / 适用场景）：

| 框架 | 协作模式 | 控制方式 | 适用场景 |
|------|----------|----------|----------|
| AutoGen | 对话/群聊 | 涌现式 | 灵活对话协作 |
| AgentScope | 消息驱动 | 消息交换 | 复杂多体流程 |
| CAMEL | 角色扮演 | 涌现式(引导提示) | 双专家自主协作 |
| LangGraph | 状态机图 | 显式控制 | 严格可追溯流程 |

（第6章 6.1.2节）

**自研 vs 复用决策。**
- 简单原型/快速验证 → 选轻量框架
- 7×24 高并发生产 → AgentScope
- 严格可追溯流程 → LangGraph
- 仅在需深度定制、教学透明、完全控制权、规避第三方黑盒/依赖/版本不稳定时，自研才划算（第7章 7.1.1节）

### 骨架2：HelloAgents 分层解耦架构
```
core（llm / message / config / agent）
agents（Simple / ReAct / Reflection / PlanSolve）
tools（base / registry / chain / async）
```
原则：分层解耦、职责单一、接口统一。（第7章 7.1.3节、7.6节）

### 骨架3：HelloAgentsLLM 自动检测决策树
优先级：**特定环境变量 > base_url（域名/端口）> API Key 格式 > 默认 auto**。（第7章 7.2.3节）

### 骨架4：ToolChain 图式编排
- 顺序执行 + 变量传递，借鉴第六章图概念（第7章 7.5.4节）。
- 工具单一职责 + 异常 + 输入验证（统一接口、安全优先验证）。

### 骨架5：主流框架架构速查
- **AutoGen（第6章 6.2.1节）**：`autogen-core` 底层 / `autogen-agentchat` 高层；异步优先 `async/await`；RoundRobinGroupChat 固定顺序发言，适合流程固定任务。
- **AgentScope（第6章 6.3.1节）**：基础组件层 → 智能体基础设施层 → 多智能体协作层 → 开发部署层；`MsgHub` 消息中心。
- **LangGraph（第6章 6.5.1节）**：State（TypedDict）+ Node（函数）+ Edge + Conditional Edge（原生支持循环）。
- **CAMEL（第6章 6.4.1节）**：AI User / AI Assistant 双智能体 + Inception Prompting 约束协议。

### 骨架6：安全阀与约束清单
- **安全阀阈值**（第6章 6.2.3节、第7章 7.4.1/7.4.2节）：`max_turns` / `max_tool_iterations` / `max_steps` 防无限循环；阈值依任务定。
- **结构化输出约束**（第6章 6.3.2节）：用 BaseModel 定义行为格式自动执行规则。
- **基于标准 API 务实选择**（第7章 7.1.2(2)节）：在 OpenAI 兼容接口上构建而非重造抽象。
- **扩展方式**：直接修改已安装库源码不被推荐（第7章 7.2.1节）→ 应继承扩展保升级。
- **OpenAI schema 限制**：不支持 `default` 字段，需塞进 description（第7章 7.5.1节）。

## A1 — 案例

**案例1：AutoGen 软件开发团队（第6章 6.2.2节）**
- 场景：用多智能体完成软件开发（需求→编码→审查→测试）。
- 做法：PM/工程师/审查员/UserProxy + 轮询群聊；`TextMentionTermination("TERMINATE")` + `max_turns` 控终止。
- 可迁移教训：用 System Message 做提示工程定义角色是多智能体设计核心；安全阀控制终止。

**案例2：AgentScope 三国狼人杀（第6章 6.3.2节）**
- 场景：复杂游戏流程需多智能体交互。
- 做法：以消息驱动代替状态机；`MsgHub` 临时私密频道；结构化输出约束；`fanout_pipeline` 并行收集投票。
- 可迁移教训：复杂流程用"消息交换模式"而非僵硬状态机。

**案例3：CAMEL 拖延症电子书（第6章 6.4.2节）**
- 场景：双专家自主深度协作产出长文。
- 做法：心理学家 + 作家双智能体，`init_chat()` / `step()` 驱动，`<CAMEL_TASK_DONE>` 终止。
- 可迁移教训：双专家角色扮演 + 引导性提示（一次一步骤、末尾标志）实现自主深度协作。

**案例4：LangGraph 三步问答（第6章 6.5.2节）**
- 场景：understand → search → answer 的容错问答。
- 做法：search 失败用 `state["step"]="search_failed"` 回退 LLM 自身知识。
- 可迁移教训：用状态字段驱动条件边实现容错。

**案例5：HelloAgents 工具链（第7章 7.5.4节）**
- 场景：多工具组合（先搜后算）。
- 做法：search → my_calculator 顺序链变量传递。
- 可迁移教训：多工具组合用 ToolChain 编排，统一 BaseTool + ToolRegistry。

## A2 — 触发场景

在以下具体情形下应调用本 skill：
- 要为项目选择智能体框架（AutoGen/AgentScope/CAMEL/LangGraph/自研）时，按四维对比做决策。
- 要自研智能体框架、设计分层架构（core/agents/tools）或工具系统（BaseTool/ToolRegistry）时。
- 要做多智能体编排（群聊/消息驱动/角色扮演/状态机图）时。
- 遇到智能体无限循环、需设 `max_turns`/`max_steps` 安全阀时。
- 要把 Memory/RAG/RL/MCP 统一抽象为工具（万物皆为工具）时。
- 要解决"该自研还是复用"的取舍问题时。

## E — 执行步骤

1. **判需求类型**：按骨架1四维对比 + 自研vs复用决策选框架。
   产出物：框架选型结论（含理由）。
2. **若复用现成框架**：按其特征落地——AutoGen 群聊/RoundRobin；AgentScope MsgHub；LangGraph 状态机图；CAMEL 角色扮演 + Inception Prompting。
   产出物：编排方案。
3. **若自研**：按 HelloAgents 分层（core/agents/tools）落地，遵循分层解耦/职责单一/接口统一。
   产出物：分层架构骨架。
4. **LLM 接入**：用自动检测决策树确定 provider（环境变量 > base_url > API Key > auto），在 OpenAI 兼容接口上构建。
   产出物：LLM 接入配置。
5. **工具系统**：统一 BaseTool + ToolRegistry，万物皆为工具（Memory/RAG/RL/MCP）；ToolChain 做顺序编排 + 变量传递。
   产出物：工具注册与编排。
6. **设安全阀**：设 `max_turns`/`max_tool_iterations`/`max_steps` 防无限循环，阈值依任务定。
   判断点：任务越复杂阈值越大，但必须有上限。
7. **输出约束**：用 BaseModel 结构化输出；OpenAI schema 的 `default` 塞进 description。
   产出物：结构化输出规范。
8. **扩展方式**：继承扩展而非改库源码；避免依赖膨胀/黑盒。
   产出物：可升级的扩展点。

## B — 边界与失效条件

- **AutoGen 局限（第6章 6.2.4节）**：对话不确定性致偏离/循环；"对话式调试"难题（只有对话历史无错误栈）。
- **AgentScope 过度工程（第6章 6.3.3节）**：消息驱动强大但对开发者要求高，简单场景"过度工程化"。
- **CAMEL 规模受限（第6章 6.4.3节）**：高度依赖提示质量、调试难、缺复杂路由/分布式状态/仲裁，规模受限；严格流程控制应改 LangGraph。
- **LangGraph 繁琐（第6章 6.5.3节）**：boilerplate 多、缺涌现式开放交互、调试需全局理解图。
- **改库源码反模式（第7章 7.2.1节）**：直接修改已安装库源码不被推荐，应继承扩展保升级。
- **OpenAI schema 限制（第7章 7.5.1节）**：不支持 `default` 字段，需塞进 description。
- **成本代价**：自研需投入长期维护，仅在确有深度定制/教学透明/完全控制权、规避第三方黑盒/依赖/版本不稳定需求时划算；否则优先复用现成框架（轻量原型/高并发生产/严格可追溯各有推荐）。

## 配套技能

本技能是 **AI Agent 全生命周期套件**（`zen-agent-suite`）的第 3/10 环。
从需求分析到交付运维，覆盖构建一个 AI Agent 产品的完整链路。

> **只装本技能不足以覆盖完整需求。** 若你正在做的是「创建 AI Agent/搭建智能体」这类完整任务，建议一并安装同套件的其他 9 个技能 —— 它们分别负责需求、设计、验证、运维等环节，缺环会导致流程断在中途。

**同套件技能**（按推荐使用顺序）：

| 阶段 | 技能 | 作用 |
|---|---|---|
| ① 需求 | `agent-requirement-analysis` | 判断该不该用 Agent、拆解任务与定义验收标准 |
| ② 设计 | `agent-paradigm-selection` | 选 ReAct / Plan-and-Solve / Reflection 范式 |
| ② 设计 | `agent-framework-architecture` ← **本技能** | 框架选型与分层架构设计 |
| ② 设计 | `agent-memory-rag-design` | 记忆系统与 RAG 检索链路设计 |
| ② 设计 | `agent-context-engineering` | 上下文工程与 GSSC 流水线 |
| ② 设计 | `agent-protocol-selection` | MCP / A2A / ANP 协议选型与集成 |
| ② 设计 | `multi-agent-orchestration` | 多智能体协作编排与成本控制 |
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

**只想装这一个**：单个技能可独立使用 —— 例如你的需求只是「框架选型与分层架构设计」，装 `agent-framework-architecture` 即可，后续需要时再补装对应环节。
---

> **来源**：蒸馏自《Hello-Agents：从零开始构建智能体》V1.0.3（Datawhale 开源教材）第 6、7 章（框架对比与自研 HelloAgents 架构）。
原始蒸馏产物与知识卡片留存于本地蒸馏输出目录，不随本仓库分发。
