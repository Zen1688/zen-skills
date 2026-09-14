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

技能代码本身随仓库分发，但 Python 依赖需要执行一次安装。

```bash
# 方式一：直接装到当前环境
pip install Pillow openpyxl python-docx reportlab numpy rapidocr-onnxruntime

# 方式二：用技能自带的安装器（支持国内镜像加速、可验证环境）
python <技能目录>/scripts/setup_env.py --with-rapidocr

# 验证
python <技能目录>/scripts/setup_env.py --check
```

安装完成后可用端到端自检确认：

```bash
python <技能目录>/scripts/selftest.py
```

> **为什么需要手动装依赖**：Agent Skills 规范只约定技能的文件结构与加载方式，
> 不包含运行时依赖管理。技能里的脚本在宿主中执行时，依赖必须已存在于当前 Python 环境。

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
