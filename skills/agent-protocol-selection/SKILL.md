---
name: agent-protocol-selection
description: 当需要为智能体项目选择通信协议（MCP/A2A/ANP）、设计 MCP 工具集成、搭建多智能体通信或大规模智能体网络时使用。解决"该用哪个协议、怎么落地集成、有哪些坑"的问题。
slug: agent-protocol-selection
version: 1.0.0
displayName: 智能体通信协议选型与集成
agent_created: true
triggers:
  - 选择 MCP A2A ANP 协议
  - 接入外部工具或 API
  - 多智能体通信编排
tags:
  - 协议选型
  - MCP
  - A2A
  - ANP
---

# 智能体通信协议选型与集成

## R — 原理锚点

**R1（协议分层定位）。** MCP 是智能体↔工具，哲学"上下文共享"，用于增强单个智能体；A2A 是智能体↔智能体，哲学"对等通信"，用于小规模团队协作；ANP 是智能体↔网络，哲学"去中心化服务发现"，用于大规模开放网络。（第10章 10.1.2节）
> 为什么重要：先定位三类协议的职责边界，才能避免"用错协议做错事"——这是选型的第一步。

**R2（选型主判据）。** 需访问外部服务（文件/数据库/API）→ MCP；需多智能体协作完成任务 → A2A；需构建大规模生态 → ANP。规模是主判据："小规模协作用 A2A，大规模网络用 ANP"。（第10章 10.1.2(4)节）
> 为什么重要：把模糊的"要不要接协议"变成可判断的三叉决策，而不是凭感觉拍板。

**R3（MCP 三能力）。** Tools 是主动的（执行操作）／Resources 是被动的（提供数据）／Prompts 是指导性的（提供模板）。（第10章 10.2.1(3)节）
> 为什么重要：设计 MCP Server 时先区分能力类型，才能写对描述、让模型用对能力。

**R4（A2A 核心抽象）。** A2A 核心抽象 = Task + Artifact；任务生命周期：创建→协商→代理→执行中→完成/失败。（第10章 10.3.1节）
> 为什么重要：A2A 与 MCP 最大区别在于以 Task/Artifact 抽象为中心，集成前必须理解这一生命周期。

**R5（ANP 信任根基）。** ANP 三机制：①语义化服务发现（爬取各体 `.well-known/agent-descriptions` 建索引）②基于 DID 的身份验证（私钥签名、解析 DID 取公钥验签）③标准化服务执行。（第10章 10.4.1节）
> 为什么重要：ANP 靠 DID 建信任根 + 标准描述协议实现动态发现，这是它区别于前两者的根基。

## I — 骨架

### 骨架1：协议选型决策树（照着做）
```
判断需求：
1. 是否需要让智能体访问外部服务（文件/数据库/API）？
   → 是：选 MCP（如何访问工具）
2. 是否需要多个智能体协作完成任务？
   → 是：选 A2A（如何与其他智能体对话）
3. 是否需要构建大规模开放生态/网络？
   → 是：选 ANP（如何在大规模网络中发现和连接智能体）
规模主判据：小规模协作用 A2A，大规模网络用 ANP。
```
一句话映射表：

| 协议 | 通信对象 | 设计哲学 | 用途 |
|------|----------|----------|------|
| MCP | 智能体↔工具 | 上下文共享 | 增强单个智能体 |
| A2A | 智能体↔智能体 | 对等通信 | 小规模团队紧密协作 |
| ANP | 智能体↔网络 | 去中心化服务发现 | 大规模开放网络 |

### 骨架2：MCP 接入落地清单
**三层架构（Host/Client/Server）。** Host（用户界面 + 对话流程管理）→ Client（协议通信、连接 Server）→ Server（实际功能执行）。关注点分离：开发者只需写 Server。（第10章 10.2.2(2)节）

**工具选择五步流程。**
1. `list_tools()` 工具发现
2. 转成 LLM 可读格式注入系统提示（上下文构建）
3. 模型推理决策
4. Client 执行工具
5. 结果回灌 LLM 生成回答
（第10章 10.2.1(4)节）

**MCP 三能力区分。** Tools（主动/执行操作）／Resources（被动/提供数据）／Prompts（指导性/提供模板）。（第10章 10.2.1(3)节）

**传输方式选型表。**

| 传输 | 适用场景 |
|------|----------|
| Memory | 单测/原型 |
| Stdio | 本地开发调试 |
| HTTP | 生产/远程/微服务 |
| SSE | 实时流式长连接 |
| StreamableHTTP | 双向流式 |

（第10章 10.2.3节）

**封装层规则。**
- Stdio/Memory 用 MCPTool；HTTP/SSE/StreamableHTTP 用底层 MCPClient（MCPTool 只面向前两种传输）。
- 多 MCP Server 并存时，每个 MCPTool 必须指定唯一 `name`（会作为展开后工具名前缀，如 `fs_read_file`），否则冲突。
- 添加 MCPTool 时"自动展开"：该 Server 全部工具以 `name` 为前缀注册到 Agent 工具表，并按参数定义自动做类型转换。

### 骨架3：HelloAgents 协议三层架构
```
协议实现层：MCP=FastMCP、A2A=a2a-sdk、ANP=自研概念实现
工具封装层：三者均继承 BaseTool，统一 run()
智能体集成层：Agent 只面对 Tool System
```
（第10章 10.1.3节）

### 骨架4：A2A 任务生命周期与请求流程
- 核心抽象：Task + Artifact
- 任务生命周期：创建 → 协商 → 代理 → 执行中 → 完成/失败
- 请求生命周期四步：代理发现 → 身份验证 → 发送消息 API → 发送消息流 API
（第10章 10.3.1节）

### 骨架5：ANP 三机制流程
1. 语义化服务发现：爬取各体 `.well-known/agent-descriptions` 建索引
2. 基于 DID 的身份验证：私钥签名、解析 DID 取公钥验签
3. 标准化服务执行
核心：用 DID 构建去中心化信任根 + 标准描述协议实现动态发现。
（第10章 10.4.1节）

### 骨架6：工程落地原则清单
- 优先复用成熟社区 MCP 服务，不要造轮子（协议处早期，生态在演进，自研成本高且易过时）。
- 选 MCP 工具优先挑大公司背书的（工具时效性取决于维护者）。
- 工具描述质量直接决定调用效果，必须写清晰准确（LLM 完全依据描述决定是否用、怎么用）。
- MCP 连接用 `async with`，调用套 try/except（确保连接正确关闭；工具调用可能失败，需重试/默认值/上报三选一）。
- 执行用户表达式先做字符白名单：`allowed_chars = set('0123456789+-*/(). ')` 全量校验。
- Dify 中 MCP 优选 SSE 模式，并删除 `mcp-server` 前缀（通信更流畅稳定）。

## A1 — 案例

**案例1：Function Calling vs MCP 同任务双实现对比（第10章 10.2.1(5)节）**
- 场景：同一"调用外部能力"任务分别用 Function Calling 与 MCP 实现。
- 做法：FC 路径需为 OpenAI（`parameters`）和 Claude（`input_schema`）分别定义 schema、自己实现函数、分别解析响应；MCP 路径直接连社区 server，统一 `list_tools`/`call_tool`。
- 可迁移教训：二者互补不竞争——FC 是模型的内在智能（"学会打电话"），MCP 是工程层的连接标准（"全球统一电话标准"）；换模型时痛点在适配层，标准化收益也在适配层。

**案例2：多 Agent 协作文档助手（第10章 10.2.4(3)节）**
- 场景：需要一个能搜索 GitHub 并生成报告的助手。
- 做法：GitHub 搜索专家（挂 `gh` MCP）产出结构化结果 → 文档生成专家（挂 `fs` MCP）转报告；用 system_prompt 强约束单一职责与输出格式（"保持简洁，不要额外解释""直接输出 Markdown，不要用工具保存"），把前一个 Agent 输出当后一个输入拼进 prompt。
- 可迁移教训：这是最低成本的编排方式。

**案例3：智能客服三角色（第10章 10.3.4(2)节）**
- 场景：接待员要能把问题路由到技术专家或销售顾问。
- 做法：接待员（SimpleAgent）+ 技术专家/销售顾问（两个 A2AServer，端口 6000/6001），用 A2ATool 的 `description` 让接待员完成路由。
- 可迁移教训：A2A 场景下"路由"靠工具描述的语义区分实现，而非硬编码 if-else。

**案例4：ANP 分布式任务调度（第10章 10.4.3节）**
- 场景：有 10 个带元数据的计算节点，需智能选节点。
- 做法：注册 10 个带 `load/cpu_cores/memory_gb/gpu` 元数据的节点，让调度 Agent 读元数据自行选节点并说明理由；同节负载均衡函数则是 `min(services, key=load)` 的确定性版本。
- 可迁移教训：把选型依据写进 service metadata，调度决策就能交给 LLM。

**案例5：自定义天气 MCP Server 全链路（第10章 10.5节）**
- 场景：要为 Agent 提供天气查询能力并发布。
- 做法：wttr.in 取数 → 三个工具函数（含 `get_server_info` 自描述）→ `add_tool` 注册 → MCPClient 测试脚本 → Agent 挂载 → Smithery 发布。
- 可迁移教训：工具函数统一返回 `json.dumps(..., ensure_ascii=False)` 且异常也返回结构化 `{"error":...}`，让 Agent 始终拿到可解析结果；中文入参需内建 `CITY_MAP` 做本地化映射。

## A2 — 触发场景

在以下具体情形下应调用本 skill：
- 要判断"我的智能体该接 MCP、A2A 还是 ANP"时（按决策树做三叉判断）。
- 要把外部文件/数据库/API 接进**单个**智能体时（MCP 集成）。
- 要用多个智能体协作（如接待员路由到专家、文档助手流水线）时（A2A）。
- 要设计并网大规模智能体生态、做服务发现与去中心化身份时（ANP）。
- 要选择 MCP 传输方式（Stdio/SSE/HTTP 等）或处理多 Server 工具名冲突时。
- 要把 Function Calling 改造为标准 MCP 接入、或要把自研工具发布到 Smithery 时。

## E — 执行步骤

1. **判定协议类型**：按骨架1决策树判断需求属于 MCP / A2A / ANP。
   产出物：协议选型结论（含规模判据说明）。
2. **若是 MCP—搭架构**：按 Host/Client/Server 三层，开发者只写 Server；区分 Tools/Resources/Prompts。
   产出物：Server 定义与能力清单。
3. **选传输方式**：按骨架2传输表选 Memory/Stdio/HTTP/SSE/StreamableHTTP。
   判断点：若是 HTTP/SSE/StreamableHTTP，**必须用 MCPClient 而非 MCPTool**。
4. **注册工具**：多 Server 时给每个 MCPTool 指定唯一 `name`。
   判断点：检查是否会出现 `name_` 前缀冲突（如 `fs_read_file` vs `gh_read_file`）。
5. **写工具描述与返回**：描述清晰准确；统一返回 `json.dumps(..., ensure_ascii=False)`，异常也返回 `{"error":...}`；中文入参内建映射。
   产出物：工具描述 + 返回格式规范。
6. **连接与调用**：用 `async with` 连接；调用套 try/except，失败重试/默认值/上报三选一。
   产出物：稳定运行的连接与容错逻辑。
7. **若是 A2A**：用 A2ATool 的 `description` 做语义路由，定义 Task/Artifact 生命周期。
   产出物：多智能体协作编排。
8. **若是 ANP**：实现服务发现 + DID 验签（仅概念验证）。
   判断点：确认当前仅为概念框架，**不进生产**。
9. **安全补全**：对危险操作补权限控制、跨体通信补端到端加密、对网络补信任评估（材料公开的缺口）。
   产出物：风险补齐清单。

## B — 边界与失效条件

- **ANP 仅概念框架**：目前无成熟生态（第10章 10.1.2(3)、10.1.3），书中实现是"自研轻量级/概念模拟"。不要把 ANP 当生产可用组件选型。
- **A2A 实现多为 Sample Code**：现有实现大部分是 Sample Code，Python 实现"较为繁琐"（第10章 10.3.2）。选 A2A 前先确认语言栈可用性。
- **MCP 工具时效性风险**：工具时效性取决于维护者（第10章 10.1.2(4)），社区工具可能失修，优先挑大公司背书。
- **手写适配器四宗罪（反模式，第10章 10.1.1）**：代码重复、难维护、无法复用、扩展性差；另加"不同 LLM 平台 function call 差异巨大，换模型要重写大量代码"（第10章 10.2.1(1)）。应用统一协议而非手写。
- **中央协调器（星型拓扑）三大失败模式（第10章 10.3.1）**：单点故障导致整体瘫痪、所有通信过中心节点限制并发、增改智能体要动中心逻辑。
- **多 Server 不改 name 导致工具名冲突**（第10章 10.2.4(1)）。
- **误以为 MCPTool 支持全部五种传输**（第10章 10.2.3）——HTTP/SSE/StreamableHTTP 必须降到 MCPClient。
- **公开风险缺口（第10章 10.6 习题5）**：MCP 客户端可调用 Server 任意工具，若提供删除文件/执行系统命令等危险操作，缺少权限控制；A2A/ANP 跨体通信可能携带隐私与商业机密而无端到端加密；大规模网络中存在恶意智能体发假信息、DoS、窃取数据的可能，缺少信任评估。这三条是协议落地的公开缺口，设计边界时必须自行补齐。
- **成本代价**：协议处发展早期，自研成本高且易过时，优先复用成熟社区 MCP 服务。

## 配套技能

本技能是 **AI Agent 全生命周期套件**（`zen-agent-suite`）的第 6/10 环。
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
| ② 设计 | `agent-protocol-selection` ← **本技能** | MCP / A2A / ANP 协议选型与集成 |
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

**只想装这一个**：单个技能可独立使用 —— 例如你的需求只是「MCP / A2A / ANP 协议选型与集成」，装 `agent-protocol-selection` 即可，后续需要时再补装对应环节。
---

> **来源**：蒸馏自《Hello-Agents：从零开始构建智能体》V1.0.3（Datawhale 开源教材）第 10 章（MCP / A2A / ANP 通信协议）。
原始蒸馏产物与知识卡片留存于本地蒸馏输出目录，不随本仓库分发。
