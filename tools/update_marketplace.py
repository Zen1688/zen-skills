"""更新 .claude-plugin/marketplace.json：
1. 为 10 个 agent 技能追加套件归属标注（软提醒，不改变 description 主体的可读性）
2. 新增 zen-agent-suite bundle 插件（一键装整套）
3. metadata 版本号 1.1.0 -> 1.2.0

注意：按 2026-10-08 拍板，不使用 plugin `dependencies` 字段做强制带装；
bundle 只在用户主动安装时才带装整套，单个技能保持可独立安装。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from suite_deps import SUITES, BLURB  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MP = ROOT / ".claude-plugin" / "marketplace.json"

SUITE_NAME = "zen-agent-suite"
SUITE_TAG = f"［套件：{SUITE_NAME}］"


def main(dry_run: bool = False) -> int:
    data = json.loads(MP.read_text(encoding="utf-8"))
    plugins = data["plugins"]
    by_name = {p["name"]: p for p in plugins}

    members = SUITES[SUITE_NAME]["members"]

    # 1. 为套件成员追加标注（幂等：已标注则不重复追加）
    added = 0
    for m in members:
        p = by_name.get(m)
        if p is None:
            print(f"错误：marketplace.json 缺少插件 {m}")
            return 1
        if SUITE_TAG not in p["description"]:
            p["description"] = f"{p['description']}{SUITE_TAG}"
            added += 1

    # 2. 插入 bundle 插件（若不存在）
    #    source 指向独立子目录 —— 若与单个技能插件共用 "./"（仓库根），
    #    bundle 的 plugin.json 会被所有插件读到，导致每个技能都带上整套依赖。
    bundle_source = f"./bundles/{SUITE_NAME}"
    if SUITE_NAME not in by_name:
        bundle = {
            "name": SUITE_NAME,
            "description": (
                f"{SUITES[SUITE_NAME]['title']}：{SUITES[SUITE_NAME]['summary']}。"
                f"安装本插件会一次性带装全部 {len(members)} 个 Agent 技能；"
                "只想要其中一环时，请改为单独安装对应的技能插件。"
            ),
            "source": bundle_source,
            "strict": False,
            "dependencies": list(members),
        }
        # 放在最前面：它是整套场景的首选入口
        plugins.insert(0, bundle)
        print(f"已插入 bundle 插件 {SUITE_NAME}（{len(members)} 个依赖）")
    else:
        by_name[SUITE_NAME]["source"] = bundle_source
        print(f"bundle 插件 {SUITE_NAME} 已存在，已校正 source")

    # 3. 版本号
    if data["metadata"]["version"] == "1.1.0":
        data["metadata"]["version"] = "1.2.0"

    # 写盘前自检：bundle 的依赖必须都能在同市场找到
    all_names = {p["name"] for p in plugins}
    missing = [d for d in members if d not in all_names]
    if missing:
        print(f"错误：bundle 依赖在同市场找不到：{missing}")
        return 1

    print(f"description 标注：新增 {added} 个，共 {len(members)} 个套件成员")
    print(f"插件总数：{len(plugins)}")

    if dry_run:
        print("（dry-run，未写入）")
        return 0

    MP.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {MP.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
