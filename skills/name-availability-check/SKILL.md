---
name: name-availability-check
description: 为一个产品/项目/库命名做可复现的可用性核验——查 Maven Central、GitHub、npm、PyPI、商标、域名的占用情况，并识别"撞名"与"显著性缺失"两类致命问题。当用户问"这个名字能用吗""帮我核验一下 XX 这个名字""这个产品该叫什么"或者提出某个候选名要落地（建仓库/注册域名/申请商标）之前，都应使用本技能。
agent_created: true
---

# 命名可用性核验

## 核心原则

**不要凭印象判断名字能不能用。** 每一次都实测，留原始证据。

**判定顺序不能反**：先查商标（决定生死）→ 再查 Maven/跨生态（决定技术可用）→ 最后查域名（不可逆支出，放最后）。

**不要先买域名。**

---

## 两类致命问题（先分清，再动手）

| 类型 | 特征 | 例子 | 能否绕开 |
|---|---|---|---|
| **被占用** | 已有同名 artifact / 包 / 活跃项目 / 在运营的产品 | `IntentLoom` ← `INTERLOOM` 商标同类目已注册 + `.com` 是运营中的 SaaS | ✅ 换名即可 |
| **显著性缺失** | 该词是行业标准术语或纯描述性词汇，不具备区分功能 | `IntentDrive` ← IETF RFC 7575 / TM Forum 定义的行业术语 | ❌ 绕不开，是词本身的属性 |

**第二类更本质**。撞名是运气问题，显著性缺失是命名路线问题。

识别信号：如果搜索结果里出现大量 `<候选词>*` 的**变体**（如 7/8 个仓库叫 `IntentDriven*`），说明这是**公共词汇**，不是独特品牌。

---

## 五步核验（全部可复现）

### ① Maven Central（Java 生态权威索引）

```bash
curl -s "https://search.maven.org/solrsearch/select?q=<name>&rows=20&wt=json" | jq .response.numFound
```

`numFound: 0` = 干净。同时看 `spellcheck.suggestions` —— 若给出高度近似的词（如 `intentengine`），值得顺手记一笔。

### ② GitHub（仓库 + 组织名）

```bash
curl -s "https://api.github.com/search/repositories?q=<name>" | jq '.total_count, [.items[] | {full_name, language, stargazers_count, pushed_at}]'
curl -s -o /dev/null -w "%{http_code}\n" "https://api.github.com/users/<name>"   # 404 = 组织名可用
```

**判读要点**：不只看数量，更要看**命名模式**。全是 `<name>*` 变体 → 通用词汇信号（见上文"两类致命问题"）。

**比数量更重要的是头部项目的「领域」**（实测反直觉：数量少 ≠ 风险低，数量多 ≠ 撞车）：

- `licensekit` —— GitHub 仅 **22** 个仓库，但头部 `Kankoda/LicenseKit` **96★**，描述即
  「Protect your software with **commercial licenses**」⇒ **同类且热度高，直接出局**。
- `licentia` —— GitHub **42** 个（比上一个多），但头部 41★ 是 Go 生态的**开源许可证**管理工具
  ⇒ **领域不同，可接受**。

⇒ 抓取时一并取 `description` 与 `stargazers_count`，**逐个判领域**；只有头部项目与你的品类同类，才算真撞车。

### ③ npm / PyPI（跨生态）

```bash
curl -s "https://registry.npmjs.org/<name>" | head -c 300
curl -s "https://pypi.org/pypi/<name>/json" | head -c 200
```

- **npm 包名不区分大小写** —— `IntentLoom` 在 npm 里**就是** `intentloom`，必须用小写查。
- **scope 要单独查**：`@<name>/cli`、`@<name>/skills` 可能已被占，这与包名是两套独立的占用关系。
- 看 `time.created` 和版本序列 —— 走完 alpha→beta→1.0 的是认真项目，不是占坑。

### ④ 商标（唯一不能靠搜索代替的一步）

- 中国商标网 <https://sbj.cnipa.gov.cn/sbj/sbcx/>
- USPTO <https://tmsearch.uspto.gov/>
- 辅助检索：WebSearch `"<name>" trademark USPTO registered`，常能带出 trademarkia / justia / furm 的条目

**要查两件事**：
1. **精确同名**是否已注册
2. **近似词**是否在**相同/相邻类别**已注册（重点看 Class 009 / 042，软件与 SaaS 的常驻类别）

**近似判定四维度**：外观、发音、含义、商品/服务的关联性。四项中中三项即高风险。

**同时判断显著性**：如果候选词是行业术语或纯描述性词汇，即使无人注册，也难以获得独占权（会被要求 disclaimer 或以 "merely descriptive" 驳回）。**判断方法**：搜 `<候选词> standard` / `<候选词> RFC` / `<候选词> white paper`，看是否有标准组织或主流厂商在用。

> 边界：这是**筛查**不是**法律意见**。查不到 / 查到冲突都只作为决策参考，商业化前应找代理人出正式检索意见。

### ⑤ 域名

**用 PowerShell `Resolve-DnsName`（可靠），不要用 shell 管道 + 退出码**（见下方"踩坑"）：

```powershell
$names = '<name>.com','<name>.dev','<name>.io','<name>.ai','<name>.org'
foreach ($n in $names) {
  $s = 'NXDOMAIN'
  try { $r = Resolve-DnsName -Name $n -Type A -ErrorAction Stop; if ($r.Count -gt 0) { $s = 'RESOLVED' } } catch { $s = 'NXDOMAIN' }
  "$n $s"
}
```

`RESOLVED` 后**必须 `WebFetch` 看一眼实页**，区分三种情况：

| 实页内容 | 含义 | 严重度 |
|---|---|---|
| 完整产品页 + 定价页 | 已有商业产品在用 | 🔴 品牌阻断 |
| "Domain for sale" / 联系表单 | 域名投资者挂售 | 🟠 得花钱买（`.com` 常四到五位数美元） |
| 空 / 无站点 | 仅为占位 | 🟡 可尝试联系 |

**NXDOMAIN 是强信号但不是权威查询** —— 已注册但未配置 DNS 的域名也会返回 NXDOMAIN。它是筛子不是终审，终审要在注册商页面查。

---

## 踩坑清单（实测所得）

1. **Bash shim 裁掉 PATH 会让标准命令缺失，并【静默产生假结果】** —— 最危险的一类坑。
   `cmd 2>&1 | grep -q X && echo A || echo B` 在 `grep` 缺失时，管道恒失败 → 条件恒假 → `else` 分支无条件命中，**输出看起来完全合理但全错**。
   → 对策：先 `export PATH="/usr/bin:/bin:$PATH"`，或换 PowerShell/Python 实现，且**凡是拿退出码做判定必须同时检查 stderr**。

2. **`nslookup` 输出是 GBK 编码**，`grep` 会报 `Binary file (standard input) matches` → 加 `grep -a` 或只匹配 ASCII 关键词。

3. **`WebFetch` 对未注册域名返回 `fetch failed`** —— 无法区分"未注册"与"抓取被拦"，**不能作为注册判定依据**，必须用 DNS/WHOIS 交叉验证。

4. **别被大小写骗了** —— 包索引普遍不区分大小写，一律用小写查。

5. **沙箱可能阻断出网：`curl` 会挂住无响应，Python `urllib` 会整体超时被杀**（exit 1、无产物）
   —— 表现为**挂起而不是报错**，极易误判成"目标站点有问题"。
   实测原型：Python 一次批量查 5 个 HTTP ＋ 6 个 DNS ⇒ 整体超时。
   → 对策：联网核验一律走 **`WebFetch`**（宿主有网络）＋ **`Resolve-DnsName`**（PowerShell），
   不要用 shell / python 的原始 socket。

6. **域名的注册判定优先用 RDAP —— 可脚本化且权威**：
   `https://rdap.org/domain/<name>` ⇒ 返回 **`errorCode: 404` ＋ `"<name> not found"` ＝ 未注册**（强信号）。
   返回 JSON 里的 `events` 给 registration / expiration 日期，`nameservers` 给线索
   —— **`ns1.afternic.com` / `ns2.afternic.com` 意味着该域名正被投资者挂售**。

---

## 交付物

核验完写一份报告，必须包含：

- **核验分数 + 明确结论**（通过 / 不建议 / 待人工）
- **逐项原始证据**（贴返回码、numFound、JSON 片段、域名状态）
- **判定分级表** —— 哪些是真阻断、哪些可接受（不是所有撞名等价）
- **可复现命令**
- **人工待办清单**（商标、域名终审）与**顺序建议**

**命名问题要区分“技术可用”与“品牌可用”**：Maven Central 干净只说明 Java 生态没占位，不代表这个名字能当品牌（`IntentLoom` 就是 Maven 零占用但 `.com` 被在运营的产品占着）。

### 为什么“技术可行 / 品牌不可行”能同时成立 —— 两套独立判据

| 判据 | 约束的是什么 | 例子结论 |
|---|---|---|
| **技术层 · 唯一性** | 坐标/包名**是否合法且不冲突** | ✅ 合格 |
| **语义层 · 可辨识性** | 该名字作为**人对它的称呼**是否可用（依赖声明行、搜索结果、博客简称、类名锚点） | 🟠 不合格 |

⇒ 这两问**不是同一个问题**，答案自然可以相反。结论必须**指明是哪一层**，否则「可行 / 不可行」单说哪句都是错话。

**Maven 坐标是这个分叉最尖锐的场合**：`groupId` 已用域名所有权提供命名空间 ⇒
**`artifactId` 只须在该 groupId 内唯一，不需要全局唯一** ⇒ `license` 这类纯描述词在技术层完全合法，
在语义层却不可用（既有限义 = LICENSE 文件生成工具、`a:license*` 147 个、无法做商标）。

⚠️ **换 groupId 时，旧 artifactId 前缀会「失去来源」**：`com.acme.license` ＋ `acme-license-*` 是**三重复读**；
groupId 一改到别的域，该前缀就不再有任何依据 ⇒ 必须**重新决定前缀**，不能默认沿用。
此时「去掉旧前缀后剩下的那个词」（如 `license`）恰恰是**最容易随手选错**的一个。

---

## 命名策略要点

- **品类名与产品名必须分开**：客户搜的是品类（获客入口），产品名是记忆锚点。两者混同 → 搜索被行业术语淹没，品牌永远浮不上来。
- **古典意象词的红利期已结束**：纺织词（loom/weave/lattice/trellis）、建筑词、音乐词基本被注册干净。唯一性只能来自**组合**，不能来自单个词。
- **禁用前缀**：`gpt-`/`llm-`/`ai-`（技术换代就过时）、`agentic-`/`agent-`（采购方视为玩具）、`spring-`（Broadcom/VMware 注册商标，有法律风险）。
- **"技术代号 + 商业品牌"双名制**是低风险做法：包名/仓库/Maven 坐标用自有产品线的零风险组合（如 `acme-intent`），对外品牌用通过核验的独立名。
