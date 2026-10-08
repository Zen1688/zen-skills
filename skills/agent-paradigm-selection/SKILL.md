---
name: agent-paradigm-selection
description: 当需要从 ReAct、Plan-and-Solve、Reflection 三种经典智能体范式中选择适配方案并着手实现时使用。解决"面对探索性/需外部工具、逻辑确定性、极高准确性要求等不同任务时，该用哪种范式、怎么搭"的问题；也用于已实现的范式陷入循环或质量不达标时的换型决策。
slug: agent-paradigm-selection
version: 1.0.0
displayName: 智能体经典范式选型与实现
agent_created: true
triggers:
  - 智能体范式选型
  - ReAct还是Plan-and-Solve还是Reflection
  - 选哪种Agent范式
  - 多步推理智能体怎么搭
tags:
  - 智能体范式
  - 架构选型
  - ReAct
  - Plan-and-Solve
  - Reflection
---

# 智能体经典范式选型与实现（agent-paradigm-selection）

## R — 原理锚点

> ReAct → 探索性、需外部工具/实时输入、环境适应与动态纠错；Plan-and-Solve → 逻辑路径确定、内部推理密集、结构性与稳定性优先；Reflection → 对准确性/可靠性要求极高且实时性宽松（关键业务代码、技术报告、科研推演、决策支持）。（第4章 4.5 节）

这段为什么重要：选型是后续一切实现的前提。选错范式要么浪费成本（用 Reflection 做快速响应），要么质量不达标（用 ReAct 做关键业务代码），必须先按任务特征定范式再动手。

> ReAct 由 Thought（内心独白）→ Action（ToolName[input] 或 Finish[答案]）→ Observation（工具返回值）→ 追加进 history → 下一轮组成循环。（第4章 4.2.1 节）

这段为什么重要：这是三种范式中最基础的"与环境交互"闭环，Plan-and-Solve 与 Reflection 都建立在其"行动—反馈"思想之上，理解它才能理解后两者的变体定位。

> "纯思考"型能推理但无法与外部世界交互，容易产生事实幻觉；"纯行动"型直接输出动作，缺乏规划和纠错能力。（第4章 4.2.1 节）

这段为什么重要：它点明 ReAct 这类"思考+行动"混合范式存在的根本原因——单一能力都有致命缺陷，混合才能兼顾推理与交互。

> 规划：P = π_plan(q)，输出 n 步计划；执行：s_i = π_solve(q, P, (s_1…s_{i-1}))，最终答案 = s_n。（第4章 4.3.1 节）

这段为什么重要：Plan-and-Solve 把"规划"与"执行"解耦为两次独立 LLM 调用，使多步推理从"走一步看一步"变为"先定全局再逐步填"，稳定性来自 plan 的预先约束。

> F_i = π_reflect(Task, O_i)；O_{i+1} = π_refine(Task, O_i, F_i)。反思四个评估维度：事实性错误 / 逻辑漏洞 / 效率问题 / 遗漏信息。（第4章 4.4.1 节）

这段为什么重要：Reflection 是"事后自我校正"循环，用"以成本换质量"的方式把初版结果推上阶梯式跃迁，适用于容忍延迟但不可出错的关键任务。

## I — 骨架

### I.0 选型决策表（第4章 4.5 节，表4.1）

| 范式 | 适用信号（选它） | 不适用信号（别选它） |
|---|---|---|
| ReAct | 探索性、需外部工具/实时输入、环境适应与动态纠错 | 纯内部推理、对结构稳定性极高要求、长程确定路径 |
| Plan-and-Solve | 逻辑路径确定、内部推理密集、结构性与稳定性优先 | 中途需根据环境反馈改计划、任务含不可预知分支 |
| Reflection | 对准确性/可靠性要求极高且实时性宽松（关键业务代码、技术报告、科研推演、决策支持） | 需快速响应、或"大致正确"即够 |

### I.1 ReAct 实现骨架（第4章 4.2.1–4.2.3 节）

**提示词模板四要素（F2）**
1. 角色定义
2. 工具清单 `{tools}`（由 `getAvailableTools()` 输出 `- name: desc` 拼进 prompt）
3. 格式规约（Thought / Action 的书写要求）
4. 动态上下文 `{question}{history}`

**核心循环伪代码（F2）**
```
history = ""
for step in range(max_steps):            # max_steps 默认 5，安全阀
    prompt = template.format(question=q, history=history, tools=tool_list)
    raw = LLM(prompt, temperature=0)      # temperature=0 保确定性
    thought, action = _parse_output(raw)
    if action.startswith("Finish["):
        return action[len("Finish["):-1] # 终止动作
    name, inp = _parse_action(action)     # 正则 (\w+)\[(.*)\]
    obs = ToolExecutor.execute(name, inp) # 执行逻辑，封装为简洁自然语言
    history += f"\nAction: {action}\nObservation: {obs}"  # 回写形成闭环
```

**解析正则（F2，DOTALL）**
- Thought：`Thought:\s*(.*?)(?=\nAction:|$)`
- Action：`Action:\s*(.*?)$`
- Action 内部：`(\w+)\[(.*)\]`
- 注：当 Action 正则匹配不到时流程直接 `break`（见 B 段 A3）。

**工具三要素 + ToolExecutor（F3）**
- 工具 = 名称 Name（供 Action 调用）+ 描述 Description（**机制中最关键部分**，LLM 靠它选工具，须写"何时该用"）+ 执行逻辑 func。
- `ToolExecutor`：`registerTool(name, desc, func)` / `getTool` / `getAvailableTools()`（输出 `- name: desc` 拼进 prompt）；同名注册告警并覆盖。
- 描述示例（第4章 4.2.2 节）："当你需要回答关于时事、事实以及在你的知识库中找不到的信息时，应使用此工具"。

**搜索结果降级解析优先级（F4）**
`answer_box_list` → `answer_box.answer` → `knowledge_graph.description` → `organic_results` 前 3 条 title+snippet → 兜底话术。目的：给 LLM 尽可能"已收敛"的输入。

### I.2 Plan-and-Solve 实现骨架（第4章 4.3.1–4.3.3 节）

**两阶段（F5）**：规划 `P = π_plan(q)` 输出 n 步计划；执行 `s_i = π_solve(q, P, (s_1…s_{i-1}))`，最终答案 = `s_n`。

**三组件（F6）**
- Planner：强制输出 ```` ```python ["步骤1",…] ````，用 `split("```python")[1].split("```")[0]` + `ast.literal_eval` 安全解析；解析失败返 `[]`。
- Executor：提示词四要素 = 原始问题 + 完整计划 + 历史步骤与结果 + 当前步骤；要求"仅输出当前步骤答案"；`history` 累加 `步骤i: …\n结果: …`。
- PlanAndSolveAgent：只做协调者（Orchestrator），体现"组合优于继承"。

**伪代码**
```
P = planner.plan(q)                       # 强制 ```python [...]```
steps = safe_parse(P)                     # ast.literal_eval；失败返 []
history = ""
for i, step in enumerate(steps):
    out = executor.solve(q, P, history, step)   # 仅输出当前步骤答案
    history += f"步骤{i+1}: {step}\n结果: {out}\n"
return last_result
```

### I.3 Reflection 实现骨架（第4章 4.4.1–4.4.3 节）

**三角色提示词（F8）**：INITIAL / REFLECT / REFINE。
**Memory 模块（F8）**：`Memory.records` 存 `{type: execution|reflection, content}`；`get_trajectory()` 序列化成可插入提示词的轨迹文本。
**终止条件（F8）**：反馈含"无需改进" **或** `max_iterations`（默认 3）。

**伪代码**
```
trajectory = Memory()
output = initial.generate(task)            # INITIAL 提示词
trajectory.add("execution", output)
for it in range(max_iterations):           # 默认 3
    feedback = reflect.generate(task, trajectory.get_trajectory())  # REFLECT
    if "无需改进" in feedback: break
    output = refine.generate(task, output, feedback)                # REFINE
    trajectory.add("reflection", feedback)
    trajectory.add("execution", output)
return output
```
**反思四维度（F7）**：事实性错误 / 逻辑漏洞 / 效率问题 / 遗漏信息。

### I.4 通用工程护栏（P 轨原则，可直接照做）
- 强制 LLM 输出结构化格式（Thought/Action、Python list），便于代码精确解析。
- 输出格式优先选"可程序化解析"；用 `ast.literal_eval` 而非 `eval`。
- 必设步数安全阀：`max_steps=5`、`max_iterations=3`。
- `temperature=0` 保证格式确定性。
- 工具描述必须写"何时该用"；描述是整个机制最关键部分。
- 反思提示词要"极其严格"、限定单一维度、规定"只有已达最优才能回答无需改进"；反馈须具体可操作（如"用筛法替代试除法"）。
- 执行器必须承担状态管理，把每步结果作为后续步骤上下文。

## A1 — 案例

**C1. ReAct + SerpApi 回答"华为最新手机"（第4章 4.2.3 节）**
- 场景：用户问时效性事实（华为最新手机型号），超出 LLM 知识库。
- 做法：两步收敛——第 1 步 Thought 自我识别"信息在我知识库之外"→ 调 Search；第 2 步汇总搜索结果并 `Finish`。
- 可迁移教训：ReAct 处理时效性问题的标准形态是"自我承认知识缺口 → 检索 → 归纳"。**局限**：当搜索摘要含营销噪声时，最终答案只能给"可能是 Pura 80 Pro+ 或 Mate 70"这类含糊结论——检索质量直接决定答案确定性。

**C2. Plan-and-Solve 解苹果销量题（第4章 4.3.4 节）**
- 场景：多步数值推理（求苹果总销量）。
- 做法：计划拆成 4 步并正确串接（步骤 2 用步骤 1 的 15，步骤 3 用步骤 2 的 30），得出 70。
- 可迁移教训：结构化计划 + 逐步状态传递能保证多步推理不偏离轨道。

**C3. Reflection 优化素数函数（第4章 4.4.4 节）**
- 场景：要求高效可靠的代码（素数判定）。
- 做法：初版试除法 `O(n·sqrt(n))` → 反思精准定位复杂度瓶颈并建议埃氏筛 → 优化到 `O(n log log n)` → 第二轮反思提及分段筛/奇数筛等方向，但判定"一般情况下无需改进"，触发收敛。
- 可迁移教训：Reflection 的价值不只是修 bug，而是驱动方案在质量与效率上阶梯式跃迁；且好的反思器要能识别"已达最优"并主动收敛。

## A2 — 触发场景

以下情况应调用本 skill（可判断，非空话）：
- 用户要构建能调用外部工具/搜索实时信息的 Agent，且任务带探索性、需环境适应（指向 ReAct）。
- 用户面对逻辑路径确定的多步推理题（如数学/计算/流程分解），要求结构稳定（指向 Plan-and-Solve）。
- 用户要求极高可靠性输出：关键业务代码、技术报告、科研推演、决策支持，且实时性宽松（指向 Reflection）。
- 用户明确问"我该用 ReAct 还是 Plan-and-Solve 还是 Reflection"或"多步推理智能体怎么搭"。
- 用户已实现某范式但出现：陷入原地打转/无限循环、格式解析失败、某步失败直接终止不重试、质量不达标——需要换型或修复。
- 用户在做工具注册/提示词模板/解析正则/步数安全阀等底层实现，需要按三范式规范落地。

## E — 执行步骤

1. **确认任务特征**：列出任务是否"需外部工具/实时""逻辑是否确定""对准确性/实时性要求"。→ 产出物：三维度判定；判断点：用 I.0 决策表初选范式。
2. **若选 ReAct**：写提示词四要素（角色+`{tools}`+格式规约+`{question}{history}`）→ 实现 `_parse_output`/`_parse_action` 正则 → 用 `ToolExecutor.registerTool` 注册工具（描述写清"何时该用"）→ 设 `max_steps=5`、`temperature=0` → 跑通 Action/Observation 闭环。→ 产出物：可运行的 ReAct 循环；判断点：能否稳定输出 `Finish[...]`。
3. **若选 Plan-and-Solve**：写 Planner 强制 ```` ```python [...] ```` → 用 `ast.literal_eval` 安全解析（失败返 `[]`）→ Executor 四要素提示词（原始问题+完整计划+历史+当前步骤，仅输出当前步答案）→ history 累加。→ 产出物：计划与逐步结果；判断点：步骤间状态是否正确串接。
4. **若选 Reflection**：写 INITIAL/REFLECT/REFINE 三套提示词（REFLECT 极严格、单一维度、规定"只有已达最优才能回答无需改进"，反馈须具体可操作）→ 接 `Memory` 模块存轨迹 → 设 `max_iterations=3`。→ 产出物：反思—优化迭代链；判断点：能否识别"无需改进"并收敛。
5. **调试（行为异常时按五条顺序）**：① 打印完整提示词 → ② 打印 LLM 原始输出 → ③ 验证工具输入/输出格式 → ④ 加 few-shot 成功案例 → ⑤ 换模型或调参。→ 产出物：定位结论（格式未遵循 or 解析逻辑有误）；判断点：决定改提示词还是改解析。

## B — 边界与失效条件

**ReAct 固有局限（第4章 4.2.4 节）**
- 强依赖底层 LLM：推理/指令遵循/格式化不足时，Thought 错误规划或 Action 不合格式，导致整个流程中断。
- 执行效率：串行多轮调用，复杂任务总耗时与费用高。
- 提示词脆弱性：模板微小变动即可改变 LLM 行为，并非所有模型能持续稳定遵循预设格式。
- 可能陷入局部最优：步进决策缺全局长远规划，可能"原地打转"。

**Plan-and-Solve 失效（第4章 4.3 节 + 习题4）**
- 计划是"静态"的：一次性生成不可修改；某步无法完成或不符预期时当前实现无重规划机制。
- Planner 解析失败只返回空列表，Agent 随即"任务终止"，无重试。→ 像"预订北京到上海商务旅行（机票+酒店+租车）"这类需重新权衡的任务不适合纯 Plan-and-Solve。

**Reflection 成本与不该用场景（第4章 4.4.5 节）**
- 每轮迭代至少额外 2 次 LLM 调用，多轮成本成倍。
- 串行结构总耗时显著延长，不适合实时性要求高的场景。
- 提示工程复杂度上升。
- 明确不该用：需要快速响应，或"大致正确"的答案已足够时。

**其他坑**
- 正则解析脆弱性（4.2.4）：Action 正则匹配不到时流程直接 `break`，需探索更鲁棒输出格式。
- 终止条件靠字符串匹配"无需改进"（4.4.3 + 习题5）：反馈措辞一变即失效；带条件的语义收敛靠子串命中侥幸。
- 反思时上下文冗余（4.4.2）：长轨迹须配记忆/检索模块，不要把全部上下文丢给"评审员"。
- 工具规模化失效（习题3）：可调用工具增至 50 甚至 100 个时，把全部工具描述拼进提示词不再有效，需从工程角度优化工具组织与检索。

## 关联技能

- [agent-context-engineering](./agent-context-engineering) — 上下文工程，为三范式组装输入上下文
- [agent-memory-rag-design](./agent-memory-rag-design) — Reflection 与长轨迹所需的记忆与检索模块
- [agent-framework-architecture](./agent-framework-architecture) — 将三范式组合进整体智能体框架
- [agent-evaluation-loop](./agent-evaluation-loop) — 验证范式选型后的实际表现

---

> **来源**：蒸馏自《Hello-Agents：从零开始构建智能体》V1.0.3（Datawhale 开源教材）第 1、4、5 章（ReAct / Plan-and-Solve / Reflection 三大经典范式）。
原始蒸馏产物与知识卡片见 `<本地蒸馏输出目录>`。
