"""把 10 个 agent 技能的「## 关联技能」段落替换为「## 配套技能」。

遵循 markdown-bulk-edit 工作流：改之前先证明要改的地方确实存在、且只存在一处。
每个文件必须恰好命中 1 次，否则整体中止、不做任何写入。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from suite_deps import SUITES, render_companion_section  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# 匹配从 "## 关联技能"（旧标题）或 "## 配套技能"（新标题）到下一个 "---" 分隔线之前
# 保留 --- 及之后内容。
# 同时匹配新旧标题，使脚本幂等：首次把「关联技能」升级为「配套技能」，
# 之后每次重跑都是原地刷新「配套技能」内容（依赖表变更时同步）。
PATTERN = re.compile(r"## (?:关联技能|配套技能)\n.*?(?=\n---\n)", re.DOTALL)


def main(dry_run: bool = False) -> int:
    members = [m for s in SUITES.values() for m in s["members"]]
    failures: list[str] = []
    plan: list[tuple[Path, str]] = []

    for skill in members:
        path = SKILLS / skill / "SKILL.md"
        if not path.is_file():
            failures.append(f"{skill}: SKILL.md 不存在")
            continue

        text = path.read_text(encoding="utf-8")
        hits = PATTERN.findall(text)
        if len(hits) != 1:
            failures.append(
                f"{skill}: 「## 配套技能」(或旧标题) 命中 {len(hits)} 次（期望 1）"
            )
            continue

        new_section = render_companion_section(skill).rstrip("\n")
        new_text = PATTERN.sub(lambda _: new_section, text, count=1)

        # 写盘后自检：新段落必须在，旧标题必须消失
        if "## 配套技能" not in new_text:
            failures.append(f"{skill}: 替换后未出现「## 配套技能」")
            continue
        if "## 关联技能" in new_text:
            failures.append(f"{skill}: 替换后仍残留「## 关联技能」")
            continue

        plan.append((path, new_text))

    if failures:
        print(f"命中校验失败，共 {len(failures)} 项，未做任何写入：")
        for f in failures:
            print("  -", f)
        return 1

    changed = [(p, t) for p, t in plan if p.read_text(encoding="utf-8") != t]
    print(f"命中校验通过：{len(plan)} 个文件各命中 1 次，其中 {len(changed)} 个内容有变化")
    if dry_run:
        print("（dry-run，未写入）")
        return 0

    for path, new_text in plan:
        path.write_text(new_text, encoding="utf-8")
        print(f"  已更新 {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
