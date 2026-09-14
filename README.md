# zen-skills

自研 Agent Skill 集合 —— 遵循 [Agent Skills](https://agentskills.io) 规范的通用技能仓库。

每个技能是一个自包含目录，可安装到任何支持 Agent Skills 的宿主环境。

---

## 技能清单

| 技能 | 说明 | 主要依赖 |
|---|---|---|
| [image-toolkit](skills/image-toolkit/) | 离线图片处理工具箱：格式转换 / OCR 文字识别 / 内容分类 / 导出 Office 文档。**全程无网络调用**，适配国内无网、内网环境 | Pillow, openpyxl, python-docx, reportlab, numpy, rapidocr-onnxruntime |

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

```
/plugin install image-toolkit@zen-skills
```

也可以用交互式菜单：`/plugin` → `Browse and install plugins` → `zen-skills` → `image-toolkit` → `Install now`。

**非交互式（脚本化）等价命令**

```bash
claude plugin marketplace add Zen1688/zen-skills
claude plugin install image-toolkit@zen-skills
```

安装后，可以显式调用：

```
/image-toolkit:image-toolkit
```

或者直接在对话里描述需求，由 Claude 依据技能描述自动触发。

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

---

## 技能目录规范

```
skills/<skill-name>/
├── SKILL.md          # 必需：YAML frontmatter（name + description）+ 指令正文
├── scripts/          # 可选：可执行脚本
├── references/       # 可选：按需加载进上下文的参考文档
└── assets/           # 可选：输出用素材（模板 / 图标 / 字体）
```

`SKILL.md` 的 frontmatter 最小形态：

```yaml
---
name: skill-name
description: 技能做什么、什么时候用（决定 AI 何时触发该技能）
---
```

---

## 开发：新增一个技能

```bash
mkdir -p skills/<new-skill>
# 编写 skills/<new-skill>/SKILL.md
git add skills/<new-skill>
git commit -m "feat: 新增 <new-skill> 技能"
git push
```

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
- 脚本内部**不要硬编码绝对路径**，用 `Path(__file__).resolve().parent` 定位自身
- 不要依赖宿主专有字段，保持技能平台中立
- 提交前确认没有 `__pycache__`、虚拟环境、日志等产物入库（`.gitignore` 已覆盖）

---

## 许可证

[MIT](LICENSE)
