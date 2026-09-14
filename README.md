# zen-skills

WorkBuddy 技能（Skill）仓库 —— 自研 Skill 集合。

每个技能是一个自包含目录，复制到 WorkBuddy 的技能目录即可使用。

---

## 技能清单

| 技能 | 说明 | 主要依赖 |
|---|---|---|
| [image-toolkit](skills/image-toolkit/) | 离线图片处理工具箱：格式转换 / OCR 文字识别 / 内容分类 / 导出 Office 文档。**全程无网络调用**，适配国内无网、内网环境 | Pillow, openpyxl, python-docx, reportlab, numpy, rapidocr-onnxruntime |

---

## 安装

### 方式一：安装全部技能（推荐）

```bash
git clone git@github.com:Zen1688/zen-skills.git
cd zen-skills
cp -r skills/* ~/.workbuddy/skills/
```

### 方式二：只装某一个技能

```bash
git clone --depth 1 git@github.com:Zen1688/zen-skills.git

# macOS / Linux
cp -r zen-skills/skills/image-toolkit ~/.workbuddy/skills/

# Windows (Git Bash)
cp -r zen-skills/skills/image-toolkit /c/Users/<你的用户名>/.workbuddy/skills/
```

安装后**重启 WorkBuddy** 即可识别。

> **本机说明**：这台机器的 HTTPS 到 GitHub 不可用（schannel 吊销检查失败），
> 请使用上面的 SSH 地址；若在别的机器上克隆，可换成
> `https://github.com/Zen1688/zen-skills.git`。

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

## 安装位置

| 类型 | 路径 | 生效范围 |
|---|---|---|
| 用户级 | `~/.workbuddy/skills/` | 所有项目可用 |
| 项目级 | `{项目目录}/.workbuddy/skills/` | 仅该项目可用，适合团队共享 |

---

## 开发：新增一个技能

```bash
mkdir -p skills/<new-skill>
# 编写 skills/<new-skill>/SKILL.md
git add skills/<new-skill>
git commit -m "feat: 新增 <new-skill> 技能"
git push
```

约定：

- 一个技能一个目录，目录名与 frontmatter 的 `name` 保持一致
- 脚本内部**不要硬编码绝对路径**，用 `Path(__file__).resolve().parent` 定位自身
- 提交前确认没有 `__pycache__`、虚拟环境、日志等产物入库（`.gitignore` 已覆盖）

---

## 许可证

[MIT](LICENSE)
