"""zen-skills 依赖关系单一事实来源 (SSOT)。

本文件是仓库内所有依赖相关产物（.claude-plugin/marketplace.json、各 SKILL.md 的
「配套技能」段落、README 依赖图谱）的唯一数据源，避免多处手工维护导致漂移。

## 设计决策（2026-10-08 与作者拍板）

1. **语义分层**：区分两种"依赖"——
   - **技能间依赖**：一起用才能覆盖某个完整需求（如"创建一个 AI Agent"）；
   - **运行时依赖**：pip 层面的第三方包（如 image-toolkit 的 Pillow）。
   两者产物完全不同，不能混为一谈。

2. **不做强制带装**：不在 marketplace.json 使用 Claude Code 的 `dependencies` 字段。
   原因：那会让 `install A` 静默变成装 9 个，违背"单个技能可独立使用"的事实，
   也让用户无法只装一个。改用**软提醒**（bundle 入口 + description 提示 + SKILL.md 正文）。

3. **整套互提，而非只提直接依赖**：同套件成员互为提醒对象。
   依赖关系做**对称闭包**处理 —— 原文中大量单向外键（A 引用 B 但 B 不引用 A），
   对"安装提醒"这个用途无意义：用户装 B 时同样该知道 A 需要它。
   对称化后逻辑统一、不会漏提醒，代价是每个技能页列出 N-1 个配套。

4. **规范约束**：Agent Skills 规范只允许 name/description/license/compatibility/
   metadata/allowed-tools，**没有依赖字段**。因此技能自身无法声明依赖，
   只能落在「宿主安装层」(marketplace.json) 与「文档层」(SKILL.md 正文)。
   WorkBuddy 走手工拷贝、不读 marketplace.json，所以 SKILL.md 正文是它唯一的提醒通道。

用法：
    python tools/suite_deps.py              # 打印套件结构
    python tools/suite_deps.py --check      # 一致性自检
    python tools/suite_deps.py --emit-json  # 输出 JSON 供其他脚本消费
"""

# ============================================================
# 套件定义：一个套件 = 一个完整用户需求
# ============================================================
SUITES = {
    "zen-agent-suite": {
        "title": "AI Agent 全生命周期套件",
        "summary": "从需求分析到交付运维，覆盖构建一个 AI Agent 产品的完整链路",
        "triggers": [
            "创建 AI Agent",
            "搭建智能体",
            "从零做一个 Agent 产品",
            "Agent 全流程",
        ],
        # 顺序即推荐使用顺序（生命周期主线）
        "members": [
            "agent-requirement-analysis",
            "agent-paradigm-selection",
            "agent-framework-architecture",
            "agent-memory-rag-design",
            "agent-context-engineering",
            "agent-protocol-selection",
            "multi-agent-orchestration",
            "agent-evaluation-loop",
            "agent-delivery-ops",
            "agentic-rl-pipeline",
        ],
    },
}

# 技能一句话定位（用于生成提醒列表，避免 SKILL.md 里重复长描述）
BLURB = {
    "agent-requirement-analysis": "判断该不该用 Agent、拆解任务与定义验收标准",
    "agent-paradigm-selection": "选 ReAct / Plan-and-Solve / Reflection 范式",
    "agent-framework-architecture": "框架选型与分层架构设计",
    "agent-memory-rag-design": "记忆系统与 RAG 检索链路设计",
    "agent-context-engineering": "上下文工程与 GSSC 流水线",
    "agent-protocol-selection": "MCP / A2A / ANP 协议选型与集成",
    "multi-agent-orchestration": "多智能体协作编排与成本控制",
    "agent-evaluation-loop": "评估系统搭建与改进闭环",
    "agent-delivery-ops": "交付上线、成本控制与安全护栏",
    "agentic-rl-pipeline": "Agentic-RL 训练流水线（可选进阶）",
}

# 生命周期阶段标签（用于提醒时说明"还在哪一段"）
STAGE = {
    "agent-requirement-analysis": "① 需求",
    "agent-paradigm-selection": "② 设计",
    "agent-framework-architecture": "② 设计",
    "agent-memory-rag-design": "② 设计",
    "agent-context-engineering": "② 设计",
    "agent-protocol-selection": "② 设计",
    "multi-agent-orchestration": "② 设计",
    "agent-evaluation-loop": "③ 验证",
    "agent-delivery-ops": "④ 运维",
    "agentic-rl-pipeline": "⑤ 进阶",
}

# 含第三方运行时依赖的技能（pip 层面，与技能间依赖不同）
RUNTIME_DEPS = {
    "image-toolkit": [
        "Pillow",
        "openpyxl",
        "python-docx",
        "reportlab",
        "numpy",
        "rapidocr-onnxruntime",
    ],
}


# ============================================================
# 派生函数
# ============================================================
def suite_of(skill: str) -> str | None:
    for name, spec in SUITES.items():
        if skill in spec["members"]:
            return name
    return None


def companions(skill: str) -> list[str]:
    """同套件内除自己以外的成员，按生命周期顺序返回（对称闭包）。"""
    s = suite_of(skill)
    if not s:
        return []
    return [m for m in SUITES[s]["members"] if m != skill]


def validate() -> list[str]:
    """一致性自检，返回问题列表（空 = 通过）。"""
    problems: list[str] = []

    for name, spec in SUITES.items():
        members = spec["members"]
        if len(members) != len(set(members)):
            problems.append(f"套件 {name} 存在重复成员")
        for m in members:
            if m not in BLURB:
                problems.append(f"{m} 缺少 BLURB 描述")
            if m not in STAGE:
                problems.append(f"{m} 缺少 STAGE 阶段标签")

    # 反向检查：套件外的技能不应出现在 BLURB/STAGE 中（除非有意）
    all_members = {m for s in SUITES.values() for m in s["members"]}
    for k in BLURB:
        if k not in all_members:
            problems.append(f"BLURB 中的 {k} 不属于任何套件")
    for k in STAGE:
        if k not in all_members:
            problems.append(f"STAGE 中的 {k} 不属于任何套件")

    return problems


def render_companion_section(skill: str) -> str:
    """生成某个技能的「配套技能」Markdown 段落（写入 SKILL.md）。"""
    s = suite_of(skill)
    if not s:
        return ""
    spec = SUITES[s]
    others = companions(skill)
    idx = spec["members"].index(skill) + 1

    lines = [
        "## 配套技能",
        "",
        f"本技能是 **{spec['title']}**（`{s}`）的第 {idx}/{len(spec['members'])} 环。",
        f"{spec['summary']}。",
        "",
        "> **只装本技能不足以覆盖完整需求。** 若你正在做的是"
        f"「{'/'.join(spec['triggers'][:2])}」这类完整任务，"
        f"建议一并安装同套件的其他 {len(others)} 个技能 —— "
        "它们分别负责需求、设计、验证、运维等环节，缺环会导致流程断在中途。",
        "",
        "**同套件技能**（按推荐使用顺序）：",
        "",
        "| 阶段 | 技能 | 作用 |",
        "|---|---|---|",
    ]
    for m in spec["members"]:
        mark = " ← **本技能**" if m == skill else ""
        lines.append(f"| {STAGE[m]} | `{m}`{mark} | {BLURB[m]} |")

    lines += [
        "",
        "**一键安装整套**：",
        "",
        "```bash",
        "# WorkBuddy（手工拷贝）",
        "git clone --depth 1 git@github.com:Zen1688/zen-skills.git",
        "cp -r zen-skills/skills/agent-* zen-skills/skills/multi-agent-orchestration \\",
        "      ~/.workbuddy/skills/",
        "```",
        "",
        "```bash",
        "# Claude Code（插件市场）",
        "claude plugin marketplace add Zen1688/zen-skills",
        "claude plugin install zen-agent-suite@zen-skills",
        "```",
        "",
        "**只想装这一个**：单个技能可独立使用 —— 例如你的需求只是"
        f"「{BLURB[skill]}」，装 `{skill}` 即可，后续需要时再补装对应环节。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    if "--check" in sys.argv:
        ps = validate()
        if ps:
            print(f"发现 {len(ps)} 个问题：")
            for p in ps:
                print("  -", p)
            sys.exit(1)
        print("依赖表校验通过")
        sys.exit(0)

    if "--emit-json" in sys.argv:
        print(
            json.dumps(
                {
                    "suites": SUITES,
                    "blurb": BLURB,
                    "stage": STAGE,
                    "runtime": RUNTIME_DEPS,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(0)

    if "--render" in sys.argv:
        skill = sys.argv[sys.argv.index("--render") + 1]
        print(render_companion_section(skill))
        sys.exit(0)

    for name, spec in SUITES.items():
        print(f"{name} — {spec['title']}（{len(spec['members'])} 个技能）")
        for i, m in enumerate(spec["members"], 1):
            print(f"  {i:2d}. [{STAGE[m]}] {m}")
            print(f"      {BLURB[m]}")
