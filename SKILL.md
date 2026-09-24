---
name: webbuilder-xwl-patch
slug: skill-webbuilder-xwl-patch
displayName: webbuilder-xwl-patch
version: 1.4.2
license: MIT
metadata:
  category: development-tools
  tags: [xwl, webbuilder, low-code, sql]
summary: WebBuilder（wb）低代码平台的 .xwl 页面与 SQL 定义文件处理：结构级安全编辑、格式校验与重名分级、页面传参链路核对、相对 git 基线的压平检测。仅适用于 WebBuilder 平台的 .xwl 文件。
description: >-
  WebBuilder（wb）平台 .xwl 定义文件的处理与安全编辑：结构级 patch —— 只给值和子树，
  工具按设计器算法重建整份文件（缩进、转义、换行全自动产出），
  格式错误在构造上不会发生，diff 只含真正改的内容。
  触发场景：改 wb/modules 下的页面 .xwl（加删控件、挂改事件、改配置、改网格列）、
  改被引用的 SQL 片段（用 @itemId 寻址 patch）、
  查改「参数控件到 store 再到 SQL」的传参链路（两条通路 out / params）、
  处理 itemId 重名（给候选清单）、从零新建页面或 SQL 文件、
  新建后设计器导航树里看不到它（folder.json 未登记）、
  判断 .xwl 格式是否合法、加载报解析错误或页面白屏、要不要压成一行、
  确认一次改动有没有把多行内容悄悄压平（diffguard）、
  抽取或校验 SQL 与事件 JS（sql / events / sqlrefs / params）。
  只对 WebBuilder（wb）平台的 .xwl 有效；其他低代码平台页面、Vue、普通 json 不适用。
agent_created: true
---

# WebBuilder .xwl 文件处理流程

WebBuilder 的页面与查询定义都写在 `.xwl` 里。它**看起来像 JSON，但不是严格 JSON** ——
磁盘上是「字面反斜杠 + 真实换行」的多行字符串。不懂这一点就去改，**第一刀就会把文件改坏**（运行时解析失败、页面白屏）。
**本 skill 的核心是「不碰文本层」**：用 `xwl.py patch` 做**结构级编辑** —— 你只给出「值 / 子树」，
序列化器按**设计器自己的算法**重建整份文件（续行、转义、缩进、换行全部自动产出）。于是：

- **格式错误在构造上不会发生**（不接触文本层，就没有"改坏格式"这条路）；
- 重建算法做过**回放校验**（把算法跑在既有文件上逐字节比对）⇒ 排版复刻正确，重排**不会顺带改动无关内容**，
  **diff 只含这次真正改的内容**；
- 写盘前强制「重新解析后，**规范化文本**与改后对象一致」的等价比对（**含键序与值类型**：`1` 与 `1.0`、
  `true` 与 `1`、`-0.0` 与 `0`、键序不同都算不一致），对不上就中止。

## 适用范围与前提

**这条边界先说清楚：本 skill 只对 WebBuilder（wb）平台的 `.xwl` 文件有效。**
换平台、换格式（别的低代码平台的页面定义、`.vue`、普通 `.json`）工具既读不了、
也不知道那些格式的规则 —— **不要拿它去试**。

| 项 | 边界 |
|---|---|
| **平台** | 仅 WebBuilder（wb）。**其他平台不适用** |
| **对象** | 仅 `.xwl` 文件本身：格式、编辑、校验、抽取。**不含**后端 Java、模块打包、`target/` 部署副本同步、数据库菜单注册（`WB_MENU`） |
| **操作系统** | Windows 与 POSIX（含 macOS）均支持；路径分隔符与换行按各平台惯例处理，跨平台时注意检出/存储形态差异 |
| **环境** | Python 3.9+，**纯标准库零依赖**；`node` 可选，只用于事件 JS 语法校验，找不到时自动降级为提示 |
| **规模** | 跨 5 个工程 / **8 个 wb 根**实测 **24986 个 xwl**，最大单文件 **728.8 KB**（746299 字节，按 1024 算；口径与耗时见 [`references/measured-data.md`](references/measured-data.md) §十）。该量级下 `check` 全开约 **0.56 s** —— **性能不是约束**。**工具没有任何文件大小上限**，但**未验证**过 1 MB 以上的文件、或单文件事件段极多的情形 |
| **能改的前提** | 目标文件能被加载器解析（即 `check` 的 ④ 通过）。已经是坏文件的，先用 `edit` 做文本级修复 |

> 上表「规模」是**样本实测值，不是硬上限** —— 换工程要自己测。别把两处数字混起来：**这里**是"跨 5 个
> 工程、最大到什么量级"；[`references/measured-data.md`](references/measured-data.md) 的 2780 / 2777 是
> **统计口径**（只取自其中**一个**工程）。大文件上 `check` 为什么慢、怎么绕开 —— 见
> [`references/faq.md`](references/faq.md)「`check` 慢，或者本机根本没装 `node`？」。

## 怎么用

| 入口 | 怎么进 |
|---|---|
| **① 对话里直接说**（推荐） | 在 Agent 对话中描述任务即可，不必记命令。以下说法都会命中本 skill：<br>「改 xxx.xwl / 加个按钮 / 挂个点击事件 / 改页面上的 SQL / 这个页面白屏了 / 报解析错误 / `app.X` 取不到值 / 新建一个页面或 SQL 文件 / 新建的页面在设计器里找不到 / 把 xwl 里的 SQL 抽出来灌库跑一遍」 |
| **② 命令行直调** | 不经过 Agent、要自己跑或写进脚本时：`python <本 skill 目录>/scripts/xwl.py <子命令>`；`--help` 看全部子命令 |

**本 skill 不提供 GUI / 菜单入口** —— 它是命令行工具 + Agent 指令集。非技术用户让 Agent 代跑就行。

**这张表兼作参考材料索引**（下表出现的 `.md` 就是本 skill 的全部参考材料，**不必通读，按需查**）：

| 你要做的事 / 想查的材料 | 去哪 |
|---|---|
| 先搞懂 xwl 是什么、有哪些硬规则 | 第一、二章 |
| 动手改（第一次用） | **第三章**，照第 0 → 5 步走 |
| 查子命令 / 退出码 / 环境依赖 | 第四章 |
| 改引用、传参、写 `events` 里的 JS | 第五章 + [`references/js-api.md`](references/js-api.md) |
| 加 / 改窗口（`createInstance`、`closeAction`、`app._X`） | [`references/js-api.md`](references/js-api.md) §5 |
| 改 SQL 片段（`serverScript` ↔ `dataprovider`） | 第六章 + [`references/sql-fragments.md`](references/sql-fragments.md) |
| 处理注册键重名 / `@itemId#N` 寻址 | 第七章 |
| 出问题了（按症状查） | 第八章 + [`references/faq.md`](references/faq.md) |
| **动手前**扫一遍"别这么干" | [`references/anti-patterns.md`](references/anti-patterns.md) —— 23 条，标了哪些是**静默**的 |
| **交活前**逐条过 | 第九章 + [`references/checklist.md`](references/checklist.md) —— 30 项 |
| 换控件 / 不知道用哪个 / 该挂哪里 | [`references/controls.md`](references/controls.md) |
| 想看一次完整实操（从零造页面 + SQL 载体） | [`references/walkthrough.md`](references/walkthrough.md) |
| 想跑最小示例（每条命令都真跑过） | [`examples/README.md`](examples/README.md)（示例 `.xwl` 用 `xwl.py new` 现场生成，不在仓库里预置） |
| 数字从哪来（引用次数 / 分布 / 统计口径） | [`references/measured-data.md`](references/measured-data.md) |
| **为什么这么定**（判据依据、踩过的坑、已作废的做法） | [`references/workflow-notes.md`](references/workflow-notes.md) |

**触发场景**（正文里只留这三条，完整触发词见 frontmatter）：读懂或修改任何 `.xwl`
（PC 页面 / 弹窗 / store 数据源 / SQL 定义全是同一套格式）；从零新建页面或 SQL 载体；
判断格式是否合法、加载报错或白屏、要不要压成一行、改动有没有被悄悄压平。

行文约定：`##` 主题，`###` 子主题；列表项以 `**标签**：` 开头；`>` 放警告与补充说明（不放成段的规则正文）。

**维护纪律**：新增内容默认走 `references/` 承载，`SKILL.md` 只留**一行指针**指过去、不在正文里展开（篇幅红线由自检兜底）。
新增或修改守卫时也须同步写／更新其**「起因」备注**（写清不这么做会漏什么），细则见 `references/workflow-notes.md`。

## 一、xwl 是什么（先建立正确心智模型）

**一个 `.xwl` = 一棵 JSON 树**，描述一个"页面 / 资源"。顶层固定是那 7 把页面钥匙
（真实键序见 1.3），`children` 递归挂控件；控件上通常有

- `type` —— 控件类型（window / container / grid / store / button …）；
- `configs` —— 控件配置；**SQL 就在这里**（store 节点的 `configs.sql`，不是顶层键）；
- `events` —— 事件名 → JS 代码字符串（`click` / `change` / `tagEvents` …）。

> 所以"改 SQL"就是改树里某个 `configs.sql`；"改行为"就是改某个 `events.*`。

### 1.1 按用途分两类（**不要按文件结构分** —— 两类结构完全一样）

| 类别 | 说明 | 怎么认 |
|---|---|---|
| **独立页面** | 能由菜单 / `inframe` / 直接 URL 打开 | 一般 `title` + `roles` 齐备，`inframe` / `pageLink` 有值 |
| **被引用的片段** | 不是给人直接打开的页面，而是被别的 xwl 用 `url: 'm?xwl=…'` 加载：store 数据源、子面板、动作片段、SQL 载体 | 被别处引用；典型命名如 `xxxSql/queryXxx`、`.../insert`、`.../delete`、`.../fileUpload` |

**两类的格式规则与处置方式完全相同**，区别只在于：改片段时你要额外确认"谁在用它"。

> SQL 类片段（`dataprovider` + `serverScript` + `{#…#}` / `{?…?}` 占位符）的引用规则见**第五章**，
> 写法见**第六章**。

### 1.2 控件节点的标准形态

**别凭印象拼节点字段。** 权威来源是设计器自带的控件注册表 `wb/system/controls.json`。
两种键集（**键序固定** `configs, expanded, children, type`，有事件时末尾多 `events`）、
`itemId` 的**唯一性**（工具寻址用 `@itemId`）与「少写 `expanded` / `children` 会**与设计器产物不一致**」见
[`references/controls.md`](references/controls.md) §4.2 典型骨架；查单个控件用 `xwl.py schema --help`。

### 1.3 页面顶层骨架（7 把钥匙，键序固定）

顶层是固定的 7 把钥匙，**键序也是固定的**：

```text
hidden, children, roles, title, iconCls, inframe, pageLink
```

**独立页面与被引用的 SQL 载体完全一样**（键集合与顺序都不区分这两类）。
序列化按 dict 插入序输出（老 org.json 的 `json.toString(1)`，见第二章）⇒
**键序写错，产出即与设计器不一致**，下次被设计器保存就会产生额外 diff。

> ⚠️ **缺 `inframe` / `pageLink` 这类键时，`check` 依然 ALL OK** —— 它只查格式，不查"骨架是否齐全"
> （工程里确实存在这种「缺钥匙」的文件，如 `dev/ide/add-file.xwl`）。
> 所以**新建时不要手写顶层键** —— 用 `xwl.py new`（内置了这套键序，见**第三章第 0 步**）。
> 7 把钥匙各自的**取值形态与实测分布**（1635 个页面类文件的计数）见
> [`references/measured-data.md`](references/measured-data.md) §九。

> **要补齐这类「缺钥匙」文件时**：`set` 一个**原本不存在**的顶层键就是**新建键**，该 op 要带 `"create": true`
> （`patch` 默认仍放行，只打一行预告，详见 §3.1）：

```json
[{"op": "set", "path": ["inframe"], "value": false, "create": true}]
```

## 二、格式硬规则与文件形态

### 2.1 硬规则（多行源的磁盘形态）

> 磁盘形态与 5 条硬规则（**无 BOM** / **换行一致** / **续行符 `\`** 后不能有空白 / **末行不加** `\` /
> 值里的 `"` 写成 `\"`、JS 用**单引号**）见 [`references/faq.md`](references/faq.md) §一。

### 2.2 单行源 vs 多行源（**决定性规则**）

改之前先判形态 —— `xwl.py check` 会给出提示。**两种源的处置完全不同**：

| 源形态 | 处置 |
|---|---|
| **多行源**（含结构换行） | **绝对不能压成一行**，任何理由都不行 |
| **单行源**（整份紧凑一行） | 就在一行形态上改；**可以**转成多行，且能做到与设计器逐字节一致 |

> 上表「单行源就在一行形态上改」只说**格式上允许** —— 用 `patch` 改单行源的结果**一定是多行**，
> 想保住单行形态只能走 3.2 的 `edit`（完整说明见 [`references/faq.md`](references/faq.md) §四）。

### 2.3 多行源为什么绝不能压成一行

「压缩」有两种，**只有第一种是对的**：

| 做法 | 替换内容 | JSON 合法？ | 加载后的 JS | 校验能拦住吗 |
|---|---|---|---|---|
| **A 正确** | `\`+换行 → `\n`（两个字符的转义） | ✅ | 换行**保留**，语义等价 | — |
| **B 错误** | `\`+换行 → **直接删除**（"合并行"） | ✅ **依然合法** | 换行**消失**，代码粘连 | ❌ 拦不住（走 `edit` 时会有 `[warn]`） |

> 静默语义损坏的逐条后果、"绝不能压一行"与相对基线判据见 [references/anti-patterns.md](references/anti-patterns.md) 第 4 条。

### 2.4 换行与展开：`expand` / `patch` / `edit` 的三个共同规则

> **单行源可以转成多行，且能做到与设计器逐字节一致**（写回算法 = `IDE.updateModule` 四步，
> 反编译复刻 + 回放校验）。三个共同规则：`--eol` 沿用·多数·**回退 LF**（三命令共用、不静默）；
> `patch` **整份重建**（单行源改完一定是多行）；`edit` 按目标文件的实际换行**推断**、无换行时按 LF。
> 详见 [`references/faq.md`](references/faq.md) §四，写回算法与规模占比见
> [`references/measured-data.md`](references/measured-data.md) §五。

| 源 | `auto` 怎么定 |
|---|---|
| **只有一种**换行（全 CRLF / 全 LF / 全 CR） | **沿用它**（含纯 CR） |
| **混用多种**换行 | 只在 **CRLF / LF** 取多数（等量取 CRLF）；**裸 CR 不参与投票** ⇒ 绝不产出 CR |
| **一个换行符都没有**（紧凑单行源正属此类，样本工程 902 个） | 无从"沿用" ⇒ **回退 LF** |

### 2.5 值里的「字面反斜杠 + n」为什么长得别扭

> 「字面反斜杠 + n」的**机制**、**语义无损**（与原文件**逐字节相同**）与**默认 / `--safe`** 的取舍
> （**按"这个文件给谁看"决定**：要提交用默认、只人读用 `--safe`）见
> [`references/measured-data.md`](references/measured-data.md) §5.2；反例与替代（人读用 `xwl.py sql` / `events`）见
> [`references/anti-patterns.md`](references/anti-patterns.md) 第 20 条。

### 2.6 压平检测：`diffguard`（相对 git 基线）

> `diffguard` 的**判据**（定义级 / **粗筛**）、漏报面、前置必要条件、跳过与退出码、成本与 `--rev` 用法见
> [`references/faq.md`](references/faq.md) §三 与 [`references/workflow-notes.md`](references/workflow-notes.md) §二③；
> **它只在 git 仓库里有意义**，且**只扫改动过的文件**，别对整个 `wb/` 跑。提交前该跑一次，见**第三章第 5 步**。

## 三、处理流程

> **先把结论说清楚**：改 xwl **可以完全遵循设计器规则、并且不犯错** —— 只给出「值」，
> 让工具按设计器算法重建文件（第 3 步的 `patch`），你根本不碰文本层。

**改已有文件从第 1 步起；从零造新文件先走第 0 步。**

### 第 0 步 · 新建文件

```bash
# 独立页面：顶层 7 把钥匙 + 一个空 module 节点
python scripts/xwl.py new wb/modules/<模块>/myPage.xwl --kind page --title "我的页面"
# SQL 载体：module(serverScript) → dataprovider(sql)，被页面用 store.url='m?xwl=…' 引用
python scripts/xwl.py new wb/modules/<模块>/xxxSql/queryXxx.xwl --kind sql --title "出库单查询"
```

`new` 内置了 1.3 那套**设计器真实键序**，所以：

- **顶层键不用管** —— 手写时漏掉 `inframe` / `pageLink`，`check` 照样 ALL OK，问题会被静默吞掉；
- **也不要用 `cp` 别的文件再整树重写** —— 种子是**继承式**的：它顶层没被显式覆盖的键会
  **静默残留**（种子的 `roles:{"demo":1}` 会跟着进新页面）。实测证据见
  [`references/measured-data.md`](references/measured-data.md) §九；
- 默认**拒绝覆盖已存在文件**（要覆盖得显式 `--force`；改已有文件应该用 `patch`）；
- `--from-json <obj.json>` 可以喂一个自己拼的顶层对象，它会**按设计器键序重排并补齐缺失的页面钥匙**
  （补齐了哪些会明确回报），且不覆盖你给的 `title` / `roles`。

**`new` 之后必做三件事** —— 只把文件写进磁盘是不够的：

| # | 做什么 | 怎么验 |
|---|---|---|
| ① | **登记进所在目录的 `folder.json`** —— 否则设计器导航树里看不到它 | `xwl.py folders <file>`；未登记则 `--register` |
| ② | SQL 载体验引用自洽 / 页面验传参链路 | `xwl.py sqlrefs` / `xwl.py params` |
| ③ | **在设计器里打开一次**（真正的冒烟） | `check` 只证"格式能加载"，不证"页面能用" |

> `folder.json` 的机制与前提（**不登记就看不到**、`--register` **只认文件路径**、缺 `folder.json` 时**不替你创建**）见 [references/faq.md](references/faq.md) §四。
> 想看一次**完整实操**（从零造页面 + SQL 载体，含 `folder.json` 登记与设计器冒烟）见 [references/walkthrough.md](references/walkthrough.md)。

### 第 1 步 · 定位文件

1. 找到目标 `.xwl`。手上只有 `m?xwl=xxx` 这类引用时，**补上 `.xwl`** 再去 `wb/modules/` 下找。
2. 分清这次要改的是**独立页面**还是**被引用的片段 / SQL 载体**（见第一章）——
   影响你改完怎么验证（片段往往没有独立入口，只能靠引用它的页面或直接调 SQL）。
3. 动手前先跑一次 `xwl.py check`：基线本来不合法的话先弄清原因，
   别把既有问题混进这次改动、也别误判成自己改坏的。

### 第 2 步 · 读懂加载机制

`text` 在磁盘上是「反斜杠 + 真实换行」的多行字符串，加载时被还原为 `\n` 转义后按严格 JSON 解析。
**据此得到一个关键推论**：只要能按加载器规则解析成功，就说明**框架能加载它** —— 这是**最强的校验手段**（见第 4 步 ④）。

### 第 3 步 · 编辑（**默认 `patch`；`edit` 仅例外**）

| 方式 | 命令 | 何时用 |
|---|---|---|
| **结构级 `patch`（默认）** | `xwl.py patch` | **几乎全部改动**：加/删/改控件、挂事件、改配置、换 SQL —— 只提供「对象 / 子树」 |
| 文本级 `edit`（例外） | `xwl.py edit` | 仅当：只改一小段纯文本、且不希望整份文件被重排 |

> 为什么默认是 `patch`：格式（续行 / 转义 / 缩进 / 换行）由序列化器保证，你不接触文本层；
> 且 `--dry-run` 能先看到 diff。**不要**用普通编辑器或通用 Edit 工具直接改 xwl —— 会写成裸 LF。

#### 3.1 结构级 `patch`（默认方式）

`ops.json` 是操作数组，`path` 是「键 / 数组下标」的列表。**节点请用设计器的标准形态**（见 [`references/controls.md`](references/controls.md) §4.2 典型骨架）：

> `ops.json` 的四种 op（`set` / `insert` / `append` / `delete`）示例见 `xwl.py patch --help`（`epilog`）。

> `path` 里对象键的 `@itemId` 写法与**不猜顺序**的三种出路（`@名字#N`、串联 `@`）见 `xwl.py patch --help`；重名处置见第七章。

> ⚠️ `paths` **只列** `sql` / `totalSql` / `serverScript` / `url` 四类字段 ——
> **按钮、网格等控件的 `itemId` 不在它的输出里**。要 `patch` 某个 `events.*`（如给按钮改 `click`）时，
> 用 **`xwl.py itemids <file>`** 看重名报告（第七章），或直接试跑并接受工具的候选清单报错。

> `paths` / `dump` 的用途与选项见各自的 `--help`（写 `path` 时**别漏 `configs` 一层**）。

> `set` 到一个**原本不存在**的**对象键**（如给缺 `inframe` 的页面补它）就是**新建键**。**这个开关只约束对象键** ——
> 补**数组元素**走 `append` / `insert`，本就不算新建键（`"create"` 挂在这两种 op 上属用法错误）。
> 任意一条 set 可带 `"create": true`：补**原本不存在的键**时用它；写到已存在的键上是幂等保护。
>
> 中间态：**现在仍允许新建键，只打 `[warn]`；到下一版本才默认拒绝，届时给已存在的键 `set` 不受影响、新建键要加 `"create": true`**（该版本号与升级须知写在 `CHANGELOG.md`）。

```json
[{"op": "set", "path": ["@panel1", "configs", "newKey"], "value": "v", "create": true}]
```

> 不带 `create` 的新建键，真跑时在 stdout 打这条预告（`--dry-run` 另把**带 `create`** 的待建键单列一行 `[new-key]`）：

```text
[warn] 本次新建了 N 个键（本版仍允许；默认拒绝将在后续版本启用）：<path1>, <path2>, …
       届时给已存在的键 set 不受影响；新建键请加 "create": true
```

1. **能用 `@itemId` 就别手写下标** —— `paths` 给出的 `["@dataprovider","configs","sql"]`
   不受嵌套层数影响，比 `["children",0,"children",0,"configs","sql"]` 稳得多。
   必须手写下标时，先用 `dump` 确认那一层**确实有**那个元素。
   > `paths` 的「原路径」**已经带 `configs` 一层**（`["children",0,"configs","serverScript"]`），照抄即可。
   > 手写时**别漏这一层** —— 漏了 `patch` **不会报错**，而是把字段写到节点根上（静默语义损坏，`check` 不拦）。
2. 写 `ops.json`（`set` / `insert` / `append` / `delete`）。
3. **`--dry-run` 是硬闸门，不是建议** —— **没看过 diff 就不许真跑**。
   工具**不会**替你拦这一步（它没法知道你脑子里确认过没有），所以这条靠自律；
   `--backup` 是**兜底**，不是"跳过 dry-run 的理由"。

```bash
# 先看将产生的 diff（不写入）
python scripts/xwl.py patch <file.xwl> --ops ops.json --dry-run
# 真改（--backup 会先写 <file>.bak）
python scripts/xwl.py patch <file.xwl> --ops ops.json --backup
```

**报错怎么办** —— `patch` 的失败都是**拒绝写盘**，不会留下坏文件：

| 现象 | 原因 | 处理 |
|---|---|---|
| `找不到 …` / 下标越界 | `path` 写错，或那一层没这个元素 | 用 `paths` / `dump` 核对后改 `path`，**别猜** |
| `… itemId == 'x' 有 N 个节点` | `@itemId` 重名，工具不替你猜 | 用 `paths` 给出的**原路径**（带下标），或先把该节点 `itemId` 改成唯一值 |
| 等价比对失败 → 中止 | `value` 里有内容重建后，**规范化文本**（含键序与值类型）与原对象不一致 | 检查 `value` 是否混入异常控制字符、数字是否写成 `1.0` 这类会变形的形态；文件**没被动过** |
| 改完 `check` 不通过 | 极少数：`value` 内含异常字符 | 恢复：`cp <file>.bak <file>`（`--backup` 写的备份），或 `git checkout -- <file>` |

三点须知：

1. **ops 按顺序执行**，`path` 按**执行到那一步时的当前结构**解释 ——
   同一个数组上先 `insert` 再 `delete`，下标要按前一步之后的数组算。
2. **事件 JS / SQL / serverScript 都写普通多行字符串**（`\n` 照常写）—— 序列化器会按设计器规则
   转成续行形态，你不用管。JS 里请用**单引号**。
> 重排的"顺带规整"与 diff 最小化口径见 [references/measured-data.md](references/measured-data.md) §五；想压小 diff 改用 3.2 的 `edit`（语义相同、只含你改的那一处）。

> 改 **SQL / serverScript** 时，`path` 用 `["@dataprovider","configs","sql"]` 这类写法 —— 见第六章。

#### 3.2 文本级 `edit`（例外情况）

用它就得自己守两条硬要求：`newline=''` 保留原换行 + **替换前断言锚点唯一**。

```bash
python scripts/xwl.py edit <file.xwl> --old-file old.txt --new-file new.txt --expect 1 --dry-run
```

> 「锚点出现次数」是**信息**不是障碍：工具会报出实际次数。出现多次时把锚点**扩到足够上下文**
> 直到唯一，**不要**用 `--expect N` 去批量替换。

> **两条路都禁止**用普通编辑器 / 通用 Edit 工具直接改 xwl —— 它们会写成裸 LF，破坏格式。

### 第 4 步 · 格式校验（**改完必跑**）

`check` 共 **八项** = **7 项判定 ＋ 1 项只提示**。7 项判定 = **格式五项 ①–⑤**（无 BOM / 换行一致 / 无「反斜杠 + 空白」行 /
**加载器等价解析** / 末行结构）+ **⑥ 事件 JS 语法**（提取后交 `node` 校验）+ **⑦ 注册键重名分级**；
**第 ⑧ 维「加载链完整性」只提示、不进 rc**（判据对齐框架取键方式：`children` 须是**非空数组**、
`children[0].configs` 与 `roles` 须是**对象**，否则文件能被 ④ 解析、页面却在加载期抛）。逐项判据与报错处置见
[`references/faq.md`](references/faq.md)；不通过时先用 `--backup` 的 `<file>.bak` 回退再排查。

```bash
python scripts/xwl.py check <file.xwl> [more.xwl ...]
python scripts/xwl.py check <file.xwl> --no-js              # 本机没有 node 时跳过 JS 校验
python scripts/xwl.py check <file.xwl> --no-itemid          # 跳过注册键重名分级（只查格式）
```

三点必须记住：

- **④ 是最强的校验手段**：**④ 通过 ⇒ 框架一定能加载它**（**反向不成立** —— 框架比 ④ 更宽，未对齐的宽容面见 `references/faq.md` §一）。它与严格 JSON 解析器**不是一回事** —— 加载器（org.json）**接受尾随逗号**（如 `{"a":1,}`）、`{` 之前的前导内容也直接丢弃。
- **⑦ 的 `[FAIL]` 与 ①–⑥ 性质不同** —— ①–⑤ 是**格式**（文件坏了）、⑥ 是**事件 JS 语法**，⑦ 是**命名质量**
  （文件能用但取值有风险）。所以 `patch` / `edit` / `expand` **写盘后的自动校验只判 ①–⑥**，
  否则会出现"写盘成功却返回非 0"。要看 ⑦ 请单独跑 `check`，或直接 `itemids`。
- **第 ⑧ 维是"只提示"**：加载链完整性有问题（如 `children` 不是数组）时只打 `[warn] ⑧ 加载链完整性：…`，**不影响退出码**；正常打 `[note] ⑧ 加载链完整性：无异常`、④ 解析失败时打 `[note] ⑧ 加载链完整性：因解析失败跳过`（**它同样不进写盘后自检**）。
> 自己写校验脚本的两坑（② **别写成"必须 CRLF"**、④ **不是替换成换行符**）见 [references/faq.md](references/faq.md) §一。

### 第 5 步 · 提交前扫一遍（`diffguard`。**只在 git 仓库里有意义**）

第 4 步的八项**只能证明"文件自身格式没坏"**，证不了"没人把多行悄悄压平" —— 压平后文件是**自洽**的。
提交前补这一刀：

```bash
python scripts/xwl.py diffguard <改过的文件或目录>            # 默认只告警
python scripts/xwl.py diffguard <改过的文件或目录> --strict    # CI / pre-commit：让它阻塞
```

- **判据、已知边界与退出码都在 [`references/faq.md`](references/faq.md) §三** —— 这里不重复。
- **没有 git 也没关系**：这一项以 `[note]` 跳过，前四步不受影响。
- CI / pre-commit 里用 `--strict`（rc=1 阻塞）；给它的路径**尽量只列改过的文件**，
  别每次都把整个 `wb/` 拖一遍（大工程上万个 xwl，没必要）。

## 四、工具

`scripts/xwl.py`（纯标准库，无第三方依赖），共 15 个子命令。

### 4.1 子命令总表

| 子命令 | 作用 |
|---|---|
| `new` | **从零生成** xwl（内置设计器真实键序的骨架），`--kind page\|sql` |
| `patch` | **结构级编辑（默认方式）**：只给值 / 子树，按设计器算法重建整份文件 |
| `edit` | 文本级安全替换（**例外**手段，改一小段文本且不希望整份重排时用） |
| `expand` | 单行源 → 设计器同款多行 |
| `check` | 八项校验：格式五项 + 事件 JS 语法 + **注册键**重名分级 + 加载链完整性（只提示） |
| `diffguard` | **相对 git 基线**检测「多行内容被压平」 |
| `itemids` | 注册键重名报告 + 建议改名（只读） |
| `paths` | 列出 `sql` / `totalSql` / `serverScript` / `url` 四类字段的位置 |
| `params` | 核对「页面 → store → SQL」传参链路（`--strict` 缺来源判失败，本版与默认同效；`--upstream` 追加「谁在调用本页」的上游扫描） |
| `sqlrefs` | 校验 `{#名字#}` ↔ `serverScript` 是否自洽 |
| `folders` | `folder.json`（设计器导航树索引）一致性检查 / 登记 |
| `schema` | 查设计器控件注册表（合法 `configs` / `events` / 骨架） |
| `dump` | 按加载器规则解析后美化输出 |
| `sql` / `events` | 抽取 SQL 文本 / 导出事件 JS |

> **参数与全部选项看 `--help`**（与实现同源，不会过期）。
> 每个命令各自的**边界与警告**（换行回退、`--indent`、退出码…）写在用到它的那一节，这里不重复。

### 4.2 退出码与输出约定

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | **被检查对象或查询结果有问题**（`check` 有 `[FAIL]`；`paths` / `sqlrefs` 没找到目标字段） |
| `2` | **用法或前置条件不满足**（缺必填参数、`edit` 锚点次数不符、`new` 拒绝覆盖、读不到目标文件） |

两类**判定会随命令线宽严变化**的命令，各自三档（默认 / 收紧 / 放松）：

| 命令 | 默认 | 收紧（严格） | 放松（留痕） |
|---|---|---|---|
| `diffguard` | 疑似压平**只告警**（rc=0） | `--strict`：疑似压平判失败（rc=1）；一个文件都没比成才 rc=2 | 非 git 仓库 / 新文件以 `[note]` 跳过 |
| `params` | 缺来源判失败（rc=1） | `--strict`：**本版与默认同效**（rc=1）——为下一版翻转预留的逃生开关 | 缺来源时打一行 `[note]` 预告放松将生效 |

> **原则：判定变严要喧哗、放松要留痕** —— 收紧必须让调用方**当场**看得见（`[FAIL]` / rc≠0）；
> 放松必须留一条**可查的预告行**（`[note]`），不能悄悄改掉默认行为。
> 退出码与行首标记（`[warn]` **不影响退出码**，"1 与 2"**不是严格二分**）见 [references/faq.md](references/faq.md) §四。

### 4.3 环境依赖与自检

> 环境依赖（**Python 3.9+** / 纯标准库；`node` 可选，按 `--node` → `NODE_BIN` → `PATH` 定位、
> 找不到降级）见本文「适用范围与前提」的环境行与 [`README.md`](README.md)。
> 全部参考材料与示例的索引在**本文开头的「怎么用」表**里（那张表就是索引），此处不重复。

## 五、xwl 的引用方式（数据源 / 子页面 / 后台方法）

一个 `.xwl` 向外引用别的 xwl 或后台方法，只有下面这几条通路 —— **先看总表**：

| 引用什么 | 最短骨架 | 写在哪里 |
|---|---|---|
| **数据源**（SQL 文件） | `store.configs.url = 'm?xwl=…'`（配合 `store.load({out})`） | store 节点的 `configs.url` |
| **服务端片段**（SQL / 校验 / 取数） | `Wb.request({url:'m?xwl=…', params, success:fn})` | 控件的 `events.*` 里 |
| **子页面**（列表页 / 弹窗） | `Wb.open({url:'m?xwl=…', title:'…', params:{…}})` | `events.*` 里 |
| **文件上传 / 导入入口** | `Wb.upload({form: app.form1, url:'m?xwl=…', success:fn})`（`form` 里必须有 `file` 控件） | `events.*` 里 |
| **后台 Spring 方法** | `Wb.requestAg({params:{bean:'…', method:'…', …}})`（**不用写 `url`**） | `events.*` 里 |
| **服务端 xwl 调 xwl** | `app.execute('m?xwl=…')` | `module.configs.serverScript` |

**回传怎么取**（写 `success` 回调时最常用的一条）：`dataprovider` 出的数据是
`Wb.decode(resp.responseText).rows` / `.total`；`serverScript` 里 `app.send(x)` 出来的是 `x` 本身。

> **完整写法**（选项全表、四种响应形态怎么收、回调签名、上传两步链）见
> [`references/js-api.md`](references/js-api.md)；各条在样本工程里的**出现次数**见
> [`references/measured-data.md`](references/measured-data.md) §一（只作量级参考，与你怎么改无关）。

### 5.1 怎么读一个 `m?xwl=` 引用

> 引用写的是**模块相对路径、不带 `.xwl` 后缀**（**补上 `.xwl`** 即文件路径）；**从文件找引用方**见
> [`references/sql-fragments.md`](references/sql-fragments.md) §3.3（**被引用的片段是常态**）。

### 5.2 url 的三种写法

| 写法 | 例 | 说明 |
|---|---|---|
| `m?xwl=<模块相对路径，**不带 `.xwl`**>` | `m?xwl=<模块>/…/xxxSql/queryBizList` | **最常用**。相对 `wb/modules/`，补 `.xwl` 就是文件路径（见 [`references/sql-fragments.md`](references/sql-fragments.md) §3.3） |
| `/<短名>` | `/upload`、`/get-file`、`/download` | 短名注册表 **`wb/system/url.json`**，框架内部端点。改动时别自己编短名 |
| `http://…` 或任意 url | `Wb.open({url:'http://…', inframe:true})` | 外部地址必须 `inframe:true` |

> `url` 的解析口径（短名**不解析**、**只判本 wb 根**、**按单 webapp 判定**）见 [references/sql-fragments.md](references/sql-fragments.md) §3.4。

### 5.3 引用位置：这些代码写在 xwl 的哪一处

| 位置 | 放什么 |
|---|---|
| `控件.events.click` / `ok` / `beforeedit` / `select` … | `Wb.request` / `Wb.open` / `Wb.requestAg` / `Wb.upload`（**最常见**） |
| `store.configs.url` | 数据源指向 SQL 文件 |
| `store.configs.autoLoad` (+ `configs.params`) | 首屏自动加载，用固定参数 |
| `column.configs.renderer` | 列渲染时取数（少见） |
| `module.configs.serverScript` | 服务端 `app.get` / `app.run` / `app.send` / `app.rundomain` / **`app.execute(url)`** |
| xwl 顶层 `inframe` / `pageLink` | 页面本身的打开方式（是否 iframe、菜单/链接地址） |

> 事件 JS 一律用**单引号**（xwl 的字符串转义规则，见第二章）。

### 5.4 四条最容易踩的

> 四条易踩的完整说明见 [references/js-api.md](references/js-api.md) 与契约 `test-prompts.json`。

## 六、SQL 片段：`module.serverScript` ↔ `dataprovider`

被 store 引用的「SQL 文件」不是散装 SQL，而是固定的**两级结构**：

```text
(页面钥匙 7 把，真实键序见 1.3)
└─ type="module"          configs{ itemId, serverScript }        ← 取参数、拼条件
   └─ type="dataprovider" configs{ itemId, sql, totalSql?, … }   ← 执行 SQL、出数据
```

> 其余全部展开在 [`references/sql-fragments.md`](references/sql-fragments.md)：三条最易错规则、serverScript 的源码硬规则与常用 API、三种占位符（`{#sys.*#}` / `{#任意名#}` / `{?名字?}`）、`out` / `params` 两条通路（含同名谁赢、命名契约），以及 `paths` / `sqlrefs` / `params` 三个检查工具。

**`params --upstream`（可选能力，默认关）**：核对「**谁在调用本页**」—— 在 `--module-root` 内**单根全扫**一遍，
末尾加独立分组 `[外部可传入]`（各上游调用方与传入键），再给一行**载入侧汇总**（节点级「同根命中 / 本根未找到 / 非 m?xwl 的 url」＋
出现级「动态写法 / 非 `m?xwl` 字面量」；**两种量纲分开标**；节点级三数**之和 = 本页 store.url 数**）。**默认关 ⇒ 零成本**（不开时**不出现**这两段；**唯一例外**见 §4.2 的留痕规则 —— 缺来源时本就有一行 `[note]` 预告）；
开了才单根全扫一遍（≈5 秒量级）。它只认 `params: {名:值}` **字面量键**，`out: app.<容器>` 与运行时拼接的 url **只计数**；
**不并入 `provided`、不改退出码**。命中量级（同一批 8 个 wb 根：节点级「同根命中 26840 / 本根未找到 5006」；出现级「动态写法 867 / 非 `m?xwl` 字面量 440」）与**多根三分类**（同根命中 / 跨工程 / 全根不存在）的完整口径见 [`references/measured-data.md`](references/measured-data.md)。

## 七、itemId 命名规范与重名处置

`itemId` 是设计器里的节点名；框架真正用来注册与取值的是**注册键 `normalName || itemId`**（`normalName` 优先）。
重名**不是一律有问题** —— 判据只有**两级**：按**注册键**分组，组内 ≥2 且**被事件 JS 引用 → `error`**、**未被引用 → `benign`**。

### 7.1 框架怎么把控件交给 JS（这决定了重名的后果）

**注册键是 `normalName || itemId`** —— `normalName` **优先**。所以只要每个同名控件各有互不相同的
`normalName`，就根本不会撞车，JS 走 `app.<normalName>`。

> 「重名后 `app.X` 取不到值 / 取到的不是你以为的那个」的**确切机制**（注册是**普通赋值**、
> `unregister` 按同名键直接 `delete` ⇒ **后创建的覆盖先创建的**、**任一重复项被销毁会删掉整个名字**）见
> [`references/measured-data.md`](references/measured-data.md) §7.5（含源码原文）。

### 7.2 三类控件，三种规则

| 类型 | 注册键重名时 | 依据与约定 |
|---|---|---|
| **grid 的列** `column` / `tcolumn` | **一般无害** | 命名约定：**字段名 + `_COL` / `Col` 后缀**。取数走 `app.<grid>.getSelection(0).data.XXX`，**不直接取列控件** ⇒ 列名撞车不影响取值 |
| **取值控件**（14 个 `Ext.form.field.*`） | **靠 `normalName` 区分** | 一般是"选中一条数据的详细展现"，`itemId` 默认就用字段名，重名不可避免。**各有唯一 `normalName` ⇒ 注册键不同、不成组**，JS 写 `app.<normalName>` |
| **按钮 / `item` / 面板 / `tab` / `toolbar` / 数据承载** | **被引用即 `error`** | 新代码**必须**把 `itemId` 区分开。老代码若已如此且**没被 JS 引用**，可以不改；**一旦被 JS 引用就是真 bug** |

第四种情况：注册键**不是合法 JS 标识符**（含中文 / 空格 / `.` 等）—— 点号访问不适用，只能用
`app.get('名')` **或** `app['名']` 取，所以 `itemids` 把这类重名判为无害（`configs.id` 命名空间不在本工具建模范围）。

> `normalName` 的合法性（**不是所有控件都接受**，写了属**非法配置**）见 [references/measured-data.md](references/measured-data.md) §7.1。

各类在**样本工程**里的实测组数、比例与按类型的分布见
[`references/measured-data.md`](references/measured-data.md) §七。那些数字只是**一个样本的量级参考**，
不要当成通用阈值 —— **在你自己的工程上跑 `itemids` / `check` 才是该工程的真实情况**。

### 7.3 遇到重名：先读父子关系，再把候选交给用户选

**不要**"删一个"、"随便挑一个"、或"重名就不处理"。按这个顺序做：

> `itemids` 的常用三个选项（`--dups-only` / `--name` / `--suggest`）见 `xwl.py itemids --help`（另有 `--fix` / `--controls` / `--json`）。

> 建议值的命名惯例与实测依据见 [references/measured-data.md](references/measured-data.md) §7.6。

> 想知道**某个工程整体**有多少重名：在**你自己的工程**上跑一遍就是最新结果 ——
> `itemids <file> --dups-only`（单文件明细）、`check`（该文件的 error / benign 计数）、
> `itemids <file> --json`（机器可读，便于汇总）。
> 样本工程的一份完整分布（各档组数 + 按控件类型的 Top）见
> [`references/measured-data.md`](references/measured-data.md) §7.2，只作**量级参考**。
>
> `itemids <file> --json` 的**字段契约**（脚本消费用）：`groups[].name` 的值 = **注册键**
> （`normalName || itemId`，**不是 `itemId`**）；`groups[]` 另有 `itemIds`（该组节点的 `itemId` 列表）
> 与 `registryName`；`--name --json` 的每个 node 项含 `itemId`。字段名不变、但 `name` 的**值**按
> 注册键走 —— 汇总一律用 `itemIds` / `registryName`，别再把 `name` 当 `itemId`。

> **怎么在 `path` 里精确指到其中一个**（`@itemId#N` 与串联 `@`）见 **§3.1** —— 与 `patch` 的
> 寻址规则是同一件事，写在那边，这里不重复。

## 八、常见问题（FAQ）

**19 条**高频问题在 [`references/faq.md`](references/faq.md)，**按四组归类**：
① 格式与解析（`check` 报 FAIL 怎么排查、页面白屏 / 解析错误、文件不是 UTF-8、为什么严格 JSON 解析会误判、**框架能打开但 ④ 报错**（加载器未对齐面））；
② 命名与引用（`app.X` 取不到值、改了 SQL 参数查询结果不对、参数明明由调用方页面传入却报"没发现来源"、**同一文件在不同目录下跑结论为何可能不同**）；
③ 能不能这么改（能不能压成一行、能不能文本替换批量改、怎么确认没改坏）；
④ 命令行为（设计器里看不到新文件、SQL 抽取报 `1064`、`node --check` 误报、`expand` 没变化、
`check` 慢或没装 `node`、`new` 骨架的 `itemId` 能不能改、脚本 / CI 里怎么判断成败）。

> 出问题**第一站是那份 FAQ**（按症状查）；**动手前**想避开已知的坑，看
> [`references/anti-patterns.md`](references/anti-patterns.md)。

## 九、改完的自检清单

**30 项**清单（改已有文件 24 项 + 新建文件 6 项）在 [`references/checklist.md`](references/checklist.md) ——
交活前逐条过一遍。按主题分了七组，**与 [`references/anti-patterns.md`](references/anti-patterns.md) 的分组对齐**：
源形态（↔ 反模式组一、二）/ 编辑方式与回退 / 验证 / 改引用与控件结构 / SQL 与传参（↔ 组六）/
`itemId` 命名（↔ 组五）/ 新建文件（↔ 组三）。

> 其中最容易跳过、后果最重的三条：① 多行源**绝不能**压成一行（改完用 `diffguard` 扫一遍，
> 这是唯一能自动发现它的手段）；② 真跑 `patch` 必须带 `--backup`；③ 新建文件必须在**设计器里打开过一次**
> （`check` 只证"格式能加载"，不证"页面能用"）。
