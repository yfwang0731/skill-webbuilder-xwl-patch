---
name: webbuilder-xwl-patch
slug: skill-webbuilder-xwl-patch
displayName: webbuilder-xwl-patch
version: 1.2.3
license: MIT
description: >-
  WebBuilder（wb）平台 .xwl 定义文件的处理与安全编辑。核心手段是**结构级 patch**：
  只提供「值 / 子树」，工具按设计器自己的算法重建整份文件，续行符、转义、缩进、换行全部自动产出
  —— 格式错误在构造上不会发生，且 diff 只含真正改的内容。
  触发场景：改 wb/modules/** 下的页面 .xwl（加删控件、挂改事件、改配置、改网格列）、
  改被引用的 SQL 片段 xxxSql/*.xwl（同样用 @itemId 寻址 patch）、
  查改「参数控件 → store → SQL」传参链路（两条通路 out / params，推荐 out）、
  处理 itemId 重名（按「类型 + 是否被 JS 引用 + 有无 normalName」分级，给候选清单与建议值；
  列控件允许重名、取值控件靠 normalName 区分、按钮/面板/承载必须唯一）、
  **从零新建页面或 SQL 文件**（`new` 内置设计器真实键序的骨架，不依赖任何「种子文件」）、
  新建后设计器导航树里看不到它（`folder.json` 未登记 —— `folders` 可查、可登记）、
  判断某个 .xwl 格式是否合法、xwl 加载报解析错误或页面白屏、要不要把 xwl 压成一行。
  附零依赖工具 xwl.py：check / new / patch / edit / params / paths / folders / itemids /
  sqlrefs / schema / dump / expand / sql / events。
agent_created: true
---

# WebBuilder .xwl 文件处理流程

WebBuilder 的页面与查询定义都写在 `.xwl` 里。它**看起来像 JSON，但不是严格 JSON** ——
磁盘上是「字面反斜杠 + 真实换行」的多行字符串。不懂这一点就去改，**第一刀就会把文件改坏**（运行时解析失败、页面白屏）。

**本 skill 的核心是「不碰文本层」**：用 `xwl.py patch` 做**结构级编辑** ——
你只给出「值 / 子树」，序列化器按**设计器自己的算法**重建整份文件（续行、转义、缩进、换行全部自动产出）。
于是：

- **格式错误在构造上不会发生**（不接触文本层，就没有"改坏格式"这条路）；
- 重建算法做过**回放校验**（把算法跑在既有文件上逐字节比对，绝大多数完全一致）
  → 说明排版复刻正确，因此重排**不会顺带改动无关内容**，**diff 只含这次真正改的内容**；
- 写盘前强制「重新解析 == 改后对象」的语义等价比对，对不上就中止。

## 适用范围与前提

**这条边界先说清楚：本 skill 只对 WebBuilder（wb）平台的 `.xwl` 文件有效。**
换平台、换格式（别的低代码平台的页面定义、`.vue`、普通 `.json`）工具既读不了、
也不知道那些格式的规则 —— **不要拿它去试**。

| 项 | 边界 |
|---|---|
| **平台** | 仅 WebBuilder（wb）。**其他平台不适用** |
| **对象** | 仅 `.xwl` 文件本身：格式、编辑、校验、抽取。**不含**后端 Java、模块打包、`target/` 部署副本同步、数据库菜单注册（`WB_MENU`） |
| **环境** | Python 3.9+，**纯标准库零依赖**；`node` 可选，只用于事件 JS 语法校验，找不到时自动降级为提示 |
| **规模** | 实测样本里最大单文件 **486 KB**（2780 个 xwl 中）。该文件上 `patch` 约 0.6 s、`check` 全开约 **1 s**。**未验证**过 1 MB 以上、或单文件事件段极多的情形 |
| **能改的前提** | 目标文件能被加载器解析（即 `check` 的 ④ 通过）。已经是坏文件的，先用 `edit` 做文本级修复 |

> 上表「规模」是**样本实测值，不是硬上限** —— 换工程要自己测。
> 大文件上 `check` 为什么慢、耗时花在哪、怎么绕开 —— 见 [`references/faq.md`](references/faq.md)「`check` 慢，或者本机根本没装 `node`？」。

## 怎么用

| 入口 | 怎么进 |
|---|---|
| **① 对话里直接说**（推荐） | 在 Agent 对话中描述任务即可，不必记命令。以下说法都会命中本 skill：<br>「改 xxx.xwl / 加个按钮 / 挂个点击事件 / 改页面上的 SQL / 这个页面白屏了 / 报解析错误 / `app.X` 取不到值 / 新建一个页面或 SQL 文件 / 新建的页面在设计器里找不到 / 把 xwl 里的 SQL 抽出来灌库跑一遍」 |
| **② 命令行直调** | 不经过 Agent、要自己跑或写进脚本时：`python <本 skill 目录>/scripts/xwl.py <子命令>`；`--help` 看全部子命令 |

**本 skill 不提供 GUI / 菜单入口** —— 它是命令行工具 + Agent 指令集。非技术用户让 Agent 代跑就行。

按任务找章节：

| 你要做的事 | 去哪 |
|---|---|
| 先搞懂 xwl 是什么、有哪些硬规则 | 第一章、第二章 |
| 动手改（第一次用） | **第三章**，照 0 → 4 步走 |
| 查某个子命令 / 退出码怎么写 | 第四章 |
| 改数据源、传参、调后台方法（写 `events` 里的 JS） | 第五章 + [`references/js-api.md`](references/js-api.md)、第六章 |
| 处理 `itemId` 重名 | 第七章 |
| 动手前扫一眼"别这么干" | [`references/anti-patterns.md`](references/anti-patterns.md) |
| 出问题了 | 第八章 FAQ |
| 交活前过一遍 | 第九章自检清单 |
| 想看一次完整的实操 | [`references/walkthrough.md`](references/walkthrough.md) |

行文约定：`##` 主题，`###` 子主题；列表项以 `**标签**：` 开头；`>` 放警告与补充说明（不放成段的规则正文）。

## 何时使用

- 要**读懂或修改任何 `.xwl`**。PC 页面、弹窗/子面板、store 数据源、SQL 定义，全都是同一套格式、同一套处置方式 —— 不按目录或操作类型设限。
- 常见改动：加/删/改控件与按钮、挂改事件 JS、改 `multiSelect` / `selType` / `columns` / `configs` 等配置、改 store 里的 SQL、改标题 / 权限 / 内嵌地址。
- 遇到 xwl 加载报解析错误、页面白屏 / 栅格不出来。
- 要**调整控件结构**（加 / 换 / 挪节点）：不知道该用哪个控件、该挂在哪个父控件下、`grid` 的列/工具栏/数据源分别挂在哪 —— 见 `references/controls.md`（控件清单）与第五章（引用方式）。
- 要**从零造一个新 xwl**（页面或 SQL 载体）—— 见**第三章第 0 步**与 `xwl.py new`（内置设计器真实顶层键序）。
- **新建的文件在设计器导航树里看不到**，或要确认某目录的 `folder.json` 登记与磁盘是否一致 —— 见 `xwl.py folders`（第三章第 0 步）。
- 要把 xwl 里的 SQL 或事件 JS 抽出来离线验证（灌真实库跑一遍、`node --check` 语法检查）。
- 要确认一次改动没破坏格式；或判断某个 xwl 是**独立页面**还是**被引用的片段**、是谁在引用它。
- 遇到 **`itemId` 重名**（事件 JS 里 `app.X` 取不到值 / 取错控件），或要判断某个重名到底该不该改 —— 见第七章。
- 要判断某段内容能不能写成一行、或把已经压成一行/紧凑格式的文件还原成规范多行。

## 一、xwl 是什么（先建立正确心智模型）

**一个 `.xwl` = 一棵 JSON 树**，描述一个"页面 / 资源"。顶层固定是那 7 把页面钥匙
（真实键序见 1.4），`children` 递归挂控件；控件上通常有

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

### 1.2 控件节点的标准形态（权威来源：设计器的控件注册表）

**别凭印象拼节点字段** —— 设计器自带一份控件注册表，工程里的位置是 **`wb/system/controls.json`**：
对每个控件 id 给出 `xtype` / ExtJS 类 / 是否容器 / `tag.lib`，**该控件允许的全部 `configs` 键**及类型，
以及**允许的全部事件名**。三套控件库的清单、配置载体说明与选型建议见
[`references/controls.md`](references/controls.md)。

查它（工具已内置）：

```bash
# 按设计器面板分组列出全部控件（带 库 / 容器 / 内部 标记）—— 不知道用什么控件时先看它
python scripts/xwl.py schema --tree --controls <工程>/wb/system/controls.json
# 看某控件的合法 configs / events，并给出设计器同款最小骨架
python scripts/xwl.py schema button --controls <工程>/wb/system/controls.json --skeleton
```

**真实控件节点的键集合只有两种**：

```text
["configs", "expanded", "children", "type"]            ← 无事件
["configs", "expanded", "children", "type", "events"]  ← 有事件
```

键序固定是 `configs, expanded, children, type, events`。例如一个真实按钮：

```json
{"configs": {"itemId": "receiveAddBtn", "text": "添加", "iconCls": "record_add_icon"},
 "expanded": false, "children": [], "type": "button",
 "events": {"click": "if (Wb.isEmpty(app.h..."}}
```

> 少写 `expanded` / `children` 运行时通常有默认值兜底，但**会与设计器产物不一致**，
> 下次被设计器保存就产生额外 diff。**用 `schema --skeleton` 生成骨架最稳。**
> `itemId` 是寻址用的（`app.<itemId>`），**必须唯一**。

### 1.3 谁在写它

xwl 是**图形化页面设计器的持久化格式**，设计器保存时会按自己的规则重新排版（写回算法见 2.4）。
所以手工把文件压成一行**维护不住**。

### 1.4 页面顶层骨架（7 把钥匙，键序固定）

顶层是固定的 7 把钥匙，**键序也是固定的**：

```text
hidden, children, roles, title, iconCls, inframe, pageLink
```

**独立页面与被引用的 SQL 载体完全一样**（键集合与顺序都不区分这两类）。
序列化按 dict 插入序输出（老 org.json 的 `json.toString(1)`，见第二章）⇒
**键序写错，产出即与设计器不一致**，下次被设计器保存就会产生额外 diff。

取值形态（实测）：

| 键 | 典型值 | 说明 |
|---|---|---|
| `hidden` | `false` | bool |
| `children` | 控件树 | 数组 |
| `roles` | `{"default": 1}` | **dict：角色名 → 1**；`{}` 也合法（如 `dev/ide/add-file.xwl`） |
| `title` | 页面标题 | 允许空串 |
| `iconCls` | `""` | 空串最常见 |
| `inframe` | `false` | bool |
| `pageLink` | `""` | 空串最常见 |

> ⚠️ **缺 `inframe` / `pageLink` 这类键时，`check` 依然 ALL OK** —— 它只查格式，不查"骨架是否齐全"。
> 工程里确实存在这种「缺钥匙」的文件（如 `dev/ide/add-file.xwl`）。
> 所以**新建时不要手写顶层键** —— 用 `xwl.py new`（内置了这套键序，见**第三章第 0 步**）。
> 分布与份额见 [`references/measured-data.md`](references/measured-data.md) §九。

## 二、格式硬规则与文件形态

### 2.1 硬规则（多行源的磁盘形态）

磁盘上的形态：

```text
{ ... "click": "var rec = app.headGrid.getSelection()[0];\
if (!rec) {\
  Wb.info('请选择一条记录！');\
  return;\
}" ... }
```

规则（**逐条都是硬要求**）：

1. **编码**：UTF-8，**无 BOM**。
2. **换行必须全文件一致**。加载器 LF / CRLF / CR 都接受（正则 `(\r\n|\r|\n)`），但**同一文件里不能混用**。
   - 设计器在服务器上写的是 **LF**；仓库（git index）里存的也是 LF。
   - Windows 上看到 CRLF，是本机 `core.autocrlf=true` 转出来的
     （实测 `git ls-files --eol` → `i/lf w/crlf`）。
   - → **不要手工改换行**：改了会和 git 的自动转换打架，产生无意义 diff。
3. **续行**：多行字符串里**每行末尾是单个 `\`，紧邻换行**；`\` 后**绝不能有空格或 Tab**。
4. **最后一行不加 `\`**（加了就等于把字符串没闭合）。
   （推论：字符串里的空行 = 该行只有 `\` 一个字符。）
5. **字符串内的 `"` 必须写成 `\"`** → 所以 **xwl 里的 JS 一律用单引号 `'`**，可完全避免转义地狱。

> **原理**：加载器先把「反斜杠 + 换行」换回 JSON 的 `\n` 转义
> （`text.replaceAll("\\\\(\r\n|\r|\n)", "\\\\n")`），再按 JSON 解析 ——
> 所以磁盘形态与运行时形态不是一回事。另外**加载器是 org.json、比标准 JSON 宽容**（字符串里的
> 裸控制字符照收）⇒ 判"能不能加载"别用严格 JSON 解析器下结论。

### 2.2 单行源 vs 多行源（**决定性规则**）

改之前先判形态 —— `xwl.py check` 会给出提示。**两种源的处置完全不同**：

| 源形态 | 处置 |
|---|---|
| **多行源**（含结构换行） | **绝对不能压成一行**，任何理由都不行 |
| **单行源**（整份紧凑一行） | 就在一行形态上改；**可以**转成多行，且能做到与设计器逐字节一致 |

### 2.3 多行源为什么绝不能压成一行

「压缩」有两种，**只有第一种是对的**：

| 做法 | 替换内容 | JSON 合法？ | 加载后的 JS | 校验能拦住吗 |
|---|---|---|---|---|
| **A 正确** | `\`+换行 → `\n`（两个字符的转义） | ✅ | 换行**保留**，语义等价 | — |
| **B 错误** | `\`+换行 → **直接删除**（"合并行"） | ✅ **依然合法** | 换行**消失**，代码粘连 | ❌ 拦不住（走 `edit` 时会有 `[warn]`） |

做法 B 是**静默语义损坏**：`//` 行注释会把后面的代码整段注释掉（实测这类结果 `node --check`
**返回 0** —— "只剩一句注释"本身是合法 JS）；ASI 依赖的换行一旦消失，`return` / `throw` /
`++` / `--` 的含义就变（`return` 换行 `{...}` 从"返回 undefined"变成"返回对象"）；
SQL 侧 token 会粘连（`select 1from dual`）。

→ "有没有被改坏"**只能靠 `git diff` 判断**（`git diff -w` 可忽略空白差异）。
> **一处例外**：这一步若走 `edit`，它手上有 old / new 两端，会把「续行符少了几个」用 `[warn]` 报出来；
> 用编辑器或通用替换工具改的，它看不到 —— 而那才是绝大多数情况。

### 2.4 单行源怎么转多行 —— **可行，且能字节级还原**

**结论：可行。** 设计器的写回逻辑已反编译确认并完整复刻（`IDE.updateModule` 四步），不需要猜排版。
**判读排版时要知道的两条**：缩进是 **1 个空格**；**只有 0 或 1 个元素的容器不换行**
（`{"itemId": "x"}`、`[3]` 内联在一行）—— 所以会看到 `[{`、`}]` 这类紧凑写法，
那是**设计器的原样，不是被压坏了**。

```bash
python scripts/xwl.py expand <file.xwl>             # 默认沿用原文件换行
python scripts/xwl.py expand <file.xwl> --eol crlf  # 工作区惯例是 CRLF 时显式指定
python scripts/xwl.py expand <file.xwl> --eol lf    # 取设计器服务器上的原始产物
```

> **`auto` 的一个边界 —— 源文件连一个换行符都没有时**：无从"沿用"，`auto` **回退到 LF**
> （即 `lf` 那一档）。**紧凑单行源正属此类**（样本工程有 902 个），所以对它们跑默认参数，
> 会在 CRLF 工作区里**新增一个 LF 文件**。工作区惯例是 CRLF 时请显式 `--eol crlf`。
> 这一步**不静默**：输出里的 `规范化后: … 换行=LF` 就是在告诉你它选了哪个。
>
> **同一条规则也用在 `edit` 上**：它按**目标文件的实际换行**归一锚点（混合换行按 CRLF 并给
> `[warn]`），目标**一个换行符都没有**时同样按 LF 处理 —— 写盘后的自动校验会给出
> `[note] 该文件是 LF 换行（设计器/仓库的原始形态）`，你会看到它。

反编译出的四步 Java 原文、`org.json toString(1)` 的三条排版规则、以及回放校验的完整口径与数字
（凭什么说"复刻正确"、少数不一致的外因是什么）见
[`references/measured-data.md`](references/measured-data.md) §五。

### 2.5 值里的「字面反斜杠 + n」为什么长得别扭

② 的正则是**「字面反斜杠 + n」**，所以值里本来就有这种序列时
（SQL / JS 源码里写的 `\n`，在 JSON 里是 `\\n`），磁盘上会呈现成
「`\\` + 反斜杠 + 换行」这种看着别扭的形态。

**这不是缺陷，语义无损**：加载器的正则 `\\(?:\r\n|\r|\n)` 恰好只吃「**一个**反斜杠 + 换行」，
所以这段在重新加载时会精确还原回原来的 `\n`。回放校验（两个多行源文件）：
忠实模式产出与原文件**逐字节相同**，且两种模式的回读值都与原值一致。

> `expand` 默认**忠实复刻**（产出与设计器逐字节一致）；`--safe` 写成更直观的 `\\n`
> （语义同样无损，但与设计器产物不同）。两种模式都在写盘前强制做
> 「**重新解析 == 原对象**」的语义等价比对，**对不上就中止**。

**该选哪个 —— 按"这个文件给谁看"决定，不要按"哪个好看"决定：**

| 场景 | 用哪个 | 理由 |
|---|---|---|
| 要提交 / 要给设计器继续编辑 / 要上生产 | **默认（忠实）** | 与设计器产物逐字节一致，设计器下次保存**不会产生额外 diff** |
| 只想**人读一遍**（把这段 JS 或 SQL 给人 review、或要粘贴到别处） | `--safe` | `\\n` 比「反斜杠 + 换行」直观，读起来不费劲 |

> 别为了"看着顺眼"把生产文件转成 `--safe` —— 那会让它与设计器产物不一致，
> 下次设计器一保存就冒出一堆与本次改动无关的 diff，把真正的改动淹没掉。
> 只是想看内容的话，`xwl.py sql` / `xwl.py events` 直接抽出来读更省事，连文件都不用动。

## 三、处理流程

> **先把结论说清楚**：改 xwl 时**可以完全遵循设计器的规则来改、并且不犯错** ——
> 做法是**只给出「值」，让工具按设计器算法重建文件**（第 3 步的结构级 `patch`）。
> 续行符、转义、缩进、换行全部由序列化器产出，你根本不碰文本层，格式错误在构造上就不会发生。

**改已有文件从第 1 步起；从零造新文件先走第 0 步。**

### 第 0 步 · 新建文件

```bash
# 独立页面：顶层 7 把钥匙 + 一个空 module 节点
python scripts/xwl.py new wb/modules/<模块>/myPage.xwl --kind page --title "我的页面"
# SQL 载体：module(serverScript) → dataprovider(sql)，被页面用 store.url='m?xwl=…' 引用
python scripts/xwl.py new wb/modules/<模块>/xxxSql/queryXxx.xwl --kind sql --title "出库单查询"
```

`new` 内置了 1.4 那套**设计器真实键序**，所以：

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

**`folder.json` 是设计器导航树的目录索引**（每个目录一个，形如
`{"hidden":false,"index":[…],"title":…}`）：`index` 里带 `.xwl` 后缀的是文件、不带后缀的是子目录；
新文件不登记进它就**在设计器里看不到**。它自身的**键序不固定、是单行紧凑形态** ——
用 `xwl.py folders <文件路径> --register` 来写（追加到 index 末尾，保原键序、保单行、幂等），别手工重排。

> **前提**：该目录得**已经被设计器管理**（目录里已有 `folder.json`）。没有的话 `--register` 会
> 明确报错并退出 2，**不会**替你创建 —— 新目录先在设计器里建，或从同类目录复制一份再改 `title`。
> 另外 `--register` 只认**文件路径**：给目录会被拒绝（一个目录里可能有好几个文件，工具不知道登记哪个）。

> **还有一步在 xwl 之外**：要让**用户**能打开这个页面，得在数据库 `WB_MENU` 里挂菜单
> （权限在 `WB_ROLE` / `WB_RESOURCE`）。那属于后端 / 数据库流程，本工具只负责 xwl 这一侧。

### 第 1 步 · 定位文件

1. 找到目标 `.xwl`。手上只有 `m?xwl=xxx` 这类引用时，**补上 `.xwl`** 再去 `wb/modules/` 下找。
2. 分清这次要改的是**独立页面**还是**被引用的片段 / SQL 载体**（见第一章）——
   影响你改完怎么验证（片段往往没有独立入口，只能靠引用它的页面或直接调 SQL）。
3. 动手前先跑一次 `xwl.py check`：基线本来不合法的话先弄清原因，
   别把既有问题混进这次改动、也别误判成自己改坏的。

### 第 2 步 · 读懂加载机制

`text` 在磁盘上是「反斜杠 + 真实换行」的多行字符串，加载时被还原为 `\n` 转义后按严格 JSON 解析。
**据此得到一个关键推论**：只要能按加载器规则解析成功，就说明格式没问题 —— 这是**最强的校验手段**（见第 4 步 ④）。

### 第 3 步 · 编辑（**默认 `patch`；`edit` 仅例外**）

| 方式 | 命令 | 何时用 |
|---|---|---|
| **结构级 `patch`（默认）** | `xwl.py patch` | **几乎全部改动**：加/删/改控件、挂事件、改配置、换 SQL —— 只提供「对象 / 子树」 |
| 文本级 `edit`（例外） | `xwl.py edit` | 仅当：只改一小段纯文本、且不希望整份文件被重排 |

> 为什么默认是 `patch`：格式（续行 / 转义 / 缩进 / 换行）由序列化器保证，你不接触文本层；
> 且 `--dry-run` 能先看到 diff。**不要**用普通编辑器或通用 Edit 工具直接改 xwl —— 会写成裸 LF。

#### 3.1 结构级 `patch`（默认方式）

`ops.json` 是操作数组，`path` 是「键 / 数组下标」的列表。**节点请用设计器的标准形态**（见 1.2）：

```json
[
  {"op": "set", "path": ["title"], "value": "新标题"},
  {"op": "set", "path": ["@dataprovider", "configs", "sql"], "value": "select 1 from dual\n{#sql#}"},
  {"op": "append", "path": ["children", 0, "children"],
   "value": {"configs": {"itemId": "newBtn", "text": "新按钮", "iconCls": "record_add_icon"},
             "expanded": false, "children": [], "type": "button",
             "events": {"click": "Wb.info('hi');"}}},
  {"op": "delete", "path": ["children", 0, "children"], "index": 3}
]
```

> `path` 里的**对象键**能用 `@itemId` 就用；**数组元素**（如 `children`、`columns`）仍要用下标 —— 两者可混写：`["@grid1","children",0,"configs","title"]`。
>
> **`@itemId` 要求唯一**。重名时工具**不猜顺序** —— 它会**报错并附上候选清单**：每个候选带
> 祖先链（`panel2 › tab1 › grid2`）、原路径、"其下有什么控件"、以及**建议改名与依据**。
> 三条出路：① `@名字#N` 点名第 N 个（N 从 1 起）；② 串联 `@` 段缩小范围（`["@grid2", "@tbar"]`）；
> ③ 按父子关系只改真正要改的那个。**重名的由来、分级与处置流程见第七章。**
>
> ⚠️ `paths` **只列** `sql` / `totalSql` / `serverScript` / `url` 四类字段 ——
> **按钮、网格等控件的 `itemId` 不在它的输出里**。要 `patch` 某个 `events.*`（如给按钮改 `click`）时，
> 用 **`xwl.py itemids <file>`** 看重名报告（第七章），或直接试跑并接受工具的候选清单报错。

**改前先核对（几十秒，省一次返工）**：

```bash
python scripts/xwl.py paths <file.xwl>    # ① 拿到目标字段的真实路径（含 @itemId 写法）
python scripts/xwl.py dump  <file.xwl>    # ② 要看清层级时：解析后美化输出
```

1. **能用 `@itemId` 就别手写下标** —— `paths` 给出的 `["@dataprovider","configs","sql"]`
   不受嵌套层数影响，比 `["children",0,"children",0,"configs","sql"]` 稳得多。
   必须手写下标时，先用 `dump` 确认那一层**确实有**那个元素。
   > `paths` 的「原路径」**已经带 `configs` 一层**（`["children",0,"configs","serverScript"]`），照抄即可。
   > 手写时**别漏这一层** —— 漏了 `patch` **不会报错**，而是把字段写到节点根上（静默语义损坏，`check` 不拦）。
2. 写 `ops.json`（`set` / `insert` / `append` / `delete`）。
3. **先 `--dry-run` 看 diff**，确认"只改了想改的"，再真跑。

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
| 语义等价比对失败 → 中止 | `value` 里有内容重建后解析不回原对象 | 检查 `value` 是否混入异常控制字符；文件**没被动过** |
| 改完 `check` 不通过 | 极少数：`value` 内含异常字符 | 恢复：`cp <file>.bak <file>`（`--backup` 写的备份），或 `git checkout -- <file>` |

三点须知：

1. **ops 按顺序执行**，`path` 按**执行到那一步时的当前结构**解释 ——
   同一个数组上先 `insert` 再 `delete`，下标要按前一步之后的数组算。
2. **事件 JS / SQL / serverScript 都写普通多行字符串**（`\n` 照常写）—— 序列化器会按设计器规则
   转成续行形态，你不用管。JS 里请用**单引号**。
3. **diff 最小化有保证**：工具先比对"源文件是否设计器原样排版"。是 → 重排后逐字节一致，
   diff **只含你真正改的内容**（口径与量级见 [`references/measured-data.md`](references/measured-data.md) §五）。源文件不是设计器原样时，重排会顺带规整整份格式，工具会明确提示。
   - ⚠️ 那种"顺带规整"除缩进外，还可能把值里的 `\uXXXX` 转义**还原成真实字符**（语义等价）。
     **先 `--dry-run` 数一下噪声行数再决定**：噪声只有一两行就照用 `patch`（省心，格式有保证——
     且还原后的形态反而与设计器产物一致）；噪声可观就改用 3.2 的 `edit` 做定点插入
     （语义相同，diff 只含你改的那一处）。
   - 判断噪声量：把 `--dry-run` 输出重定向到文件，数以 `  +` / `  -` 开头的行即可。

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

七项 = **①–⑥ 格式**（无 BOM / 换行一致 / 无「反斜杠 + 空白」行 / **加载器等价解析** /
末行结构 / 事件 JS 语法）+ **⑦ `itemId` 重名分级**。逐项判据与报错处置见
[`references/faq.md`](references/faq.md)；不通过时先用 `--backup` 的 `<file>.bak` 回退再排查。

```bash
python scripts/xwl.py check <file.xwl> [more.xwl ...]
python scripts/xwl.py check <file.xwl> --no-js              # 本机没有 node 时跳过 JS 校验
python scripts/xwl.py check <file.xwl> --no-itemid          # 跳过 itemId 重名分级（只查格式）
```

三点必须记住：

- **④ 是最强的校验手段**：加载器等价解析通过 ⇔ 格式没问题。
- **⑦ 的 `[FAIL]` 与 ①–⑥ 性质不同** —— ①–⑥ 是**格式**（文件坏了），⑦ 是**命名质量**
  （文件能用但取值有风险）。所以 `patch` / `edit` / `expand` **写盘后的自动校验只判 ①–⑥**，
  否则会出现"写盘成功却返回非 0"。要看 ⑦ 请单独跑 `check`，或直接 `itemids`。
- **自己写校验脚本时别踩两个坑**：② 别写成"必须 CRLF"（设计器与仓库存的都是 LF，
  那样会把合法文件判失败）；④ 是把「反斜杠 + 换行」替换成「**反斜杠 + 字母 n**」两个字符，
  **不是**替换成换行符。

## 四、工具

`scripts/xwl.py`（纯标准库，无第三方依赖）：

| 子命令 | 作用 |
|---|---|
| `new <out.xwl> [--kind page\|sql] [--from-json F] [--title T] [--roles R] [--eol lf\|crlf] [--force] [--dry-run]` | **从零生成 xwl（推荐入口）**：内置设计器真实键序的骨架 —— `page` = 顶层 7 钥匙 + 空 `module`；`sql` = `module(serverScript)` → `dataprovider(sql)`。**不需要种子文件**。默认拒绝覆盖已存在文件；`--from-json` 会按设计器键序重排并**补齐缺失的页面钥匙**（补齐项明确回报） |
| `patch <file> --ops ops.json [--eol auto\|lf\|crlf] [--indent N] [--dry-run] [--backup]` | **结构级编辑（推荐）**：改对象后按设计器规则整份重建，语义等价比对 + 自动校验。`path` 支持 **`@itemId`** 寻址 |
| `params <page.xwl> [--module-root <wb/modules>] [--controls <…/controls.json>]` | 检查「页面 → store → SQL」传参链路：列出 store 与**两条通路**（`out` / `params`）的传参点；`out` 会**展开容器内的取值控件名**，再与 SQL 的 `{?名?}` / `app.get('名')` 交叉核对；`--list-fields` 只打印取值控件名单 |
| `folders <path> [--register [NAME]] [--dry-run]` | **`folder.json`（设计器导航树索引）一致性检查（只读）**：报「未登记进 index 的 xwl」「index 悬空项」「缺 folder.json 的目录」。`--register` 才写（把该文件登记到 index 末尾；保原键序、保单行、幂等，写前备份）。`--register` **只接文件路径**，给目录会被明确拒绝 |
| `paths <file>` | 列出**四类字段**（`sql` / `totalSql` / `serverScript` / `url`）的位置，给「原路径」（**已含 `configs` 层**）与「`@写法`」；`itemId` 重名时标 ⚠ 并给出 `@名字#N` 点名写法 |
| `sqlrefs <file>` | 检查 SQL 文件里 `{#名字#}` ↔ `serverScript` 的 `setAttribute` 是否自洽；并抓 serverScript 里误用 `{#…#}` |
| `schema [<type>] --controls <wb/system/controls.json> [--tree] [--list] [--skeleton]` | 查设计器控件注册表：`--tree` 按面板分组列出全部控件（带库 / 容器 / 内部标记）、`--list` 只列 id、给 `<type>` 则列该控件合法的 `configs` / `events` 与 `autoNames`、`--skeleton` 出设计器同款骨架 |
| `check <file...> [--no-js] [--no-itemid]` | 七项校验：格式五项 + 事件 JS `node --check` + **itemId 重名分级**（只有「重名且被 JS 引用」判 FAIL）；任一 FAIL 返回非 0 |
| `itemids <file> [--name X] [--dups-only] [--suggest] [--fix auto\|normalName\|itemId] [--json] [--controls <…/controls.json>]` | **itemId 重名报告（只读）**：按「类型 + 是否被 JS 引用 + 有无 normalName」分级，给候选清单（祖先链 / 原路径 / 其下控件）与**建议改名**；`--suggest` 出改名 ops 草稿（需人工确认）；`--name` 配 `--json` 可机器读 |
| `edit <file> --old-file O --new-file F [--expect 1] [--dry-run] [--backup]` | 文本级安全替换：**按目标文件的换行**归一锚点（目标无换行时按 LF）、断言锚点出现次数、**拍平多行时给 `[warn]`**、可选备份 |
| `expand <file> [--out F] [--eol auto\|lf\|crlf] [--indent N] [--safe] [--dry-run] [--backup]` | 规范成设计器同款多行（复刻 `IDE.updateModule`），写盘前做语义等价比对；`auto` 在**无换行源**上回退 LF |
| `dump <file>` | 按加载器规则解析后美化输出（`ensure_ascii=False`） |
| `sql <file>` | 抽取所有含 `sql` 的键对应的 SQL 文本（已正确反转义） |
| `events <file> [--outdir DIR]` | 抽取所有事件 JS 到文件，便于单独检查 |

`node` 定位顺序：`--node <path>` → 环境变量 `NODE_BIN` → `PATH` 里的 `node`；找不到时 JS 校验降级为警告。

### 4.1 退出码与输出约定

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | **被检查对象或查询结果有问题**（`check` 有 `[FAIL]`；`paths` / `sqlrefs` 没找到目标字段） |
| `2` | **用法或前置条件不满足**（缺必填参数、`edit` 锚点次数不符、`new` 拒绝覆盖、读不到目标文件） |

行首标记：`[ok]` / `[FAIL]` / `[warn]`（**不影响退出码**）/ `[note]`。
带结论的命令最后一行为 `-> OK` 或 `-> FAIL`，便于脚本匹配。

> **判断成败看退出码，不要 grep 输出文本** —— `[warn]` 是有意设计成不阻塞的
> （老代码里的无害重名，见第七章）。
>
> 退出码也不是"1 与 2 严格二分"：同为"文件不存在"，`check` 给 1、`patch` 给 2
> （前者是检查结论、后者是前置条件）。要精确判断还是认子命令自己的输出。

八份参考材料（**不必通读，按需查**；顺序即大致的使用时机）：

- [`references/walkthrough.md`](references/walkthrough.md) —— **手把手实操**：从零造 SQL 载体 + 页面，一步一命令一预期，跟着做一遍最快建立手感。
- [`references/anti-patterns.md`](references/anti-patterns.md) —— **反模式清单（动手前扫）**：20 条"看起来对、实际有害"的做法，逐条给出「错误做法 / 为什么诱人 / 实际后果 / 正确做法」，并标出哪些是**静默**的（`check` 放行）。
- [`references/faq.md`](references/faq.md) —— **常见问题（排错第一站）**：15 条问答，按症状查 —— 出问题了先来这里。
- [`references/checklist.md`](references/checklist.md) —— **改完自检清单**：29 项（改已有文件 23 + 新建文件 6），交活前过一遍。
- [`references/controls.md`](references/controls.md) —— **控件清单**：按设计器面板分组的总表、三套控件库、配置载体说明、实测父子结构 Top 45、典型骨架与选型建议。
- [`references/js-api.md`](references/js-api.md) —— **事件 JS 四条引用通路**：`Wb.request` / `Wb.open` / `Wb.upload` / `Wb.requestAg` 各自的完整写法、回传四种形态怎么收、选项与回调签名、上传两步链。
- [`references/sql-fragments.md`](references/sql-fragments.md) —— **SQL 片段**：两级结构、字段全集、`{#…#}` / `{?…?}` 与 serverScript 的引用关系、执行器与源码依据、页面传参两条通路的完整规则与优先级、`sqlrefs` / `params` 用法。
- [`references/measured-data.md`](references/measured-data.md) —— **实测数据**：引用方式次数、传参两条通路分布、`Wb.requestAg` 参数名与回调动作频次、设计器复刻的回放校验结果、统计口径。

**环境依赖**：Python 3.9+（纯标准库）；Node.js 可选（仅用于事件 JS 语法校验）。
**改完 `xwl.py` 先跑 `python scripts/selftest.py`** 自检（内置样本验证各子命令的关键行为）。

## 五、xwl 的引用方式（数据源 / 子页面 / 后台方法）

一个 `.xwl` 向外引用别的 xwl 或后台方法，只有下面这几条通路。
**先看总表**；`m?xwl=` 写法的读法见 5.1；各条的**完整写法与「回传后前台怎么处理」**见 5.4
与 [`references/js-api.md`](references/js-api.md)。

| 引用什么 | 写法 | 写在哪里 |
|---|---|---|
| **数据源**（SQL 文件） | `store.configs.url = 'm?xwl=…'`（配合 `store.load({out})`） | store 节点的 `configs.url` |
| **服务端片段**（SQL / 校验 / 取数） | `Wb.request({ url:'m?xwl=…', params, success })` | 控件的 `events.*` 里 |
| **子页面**（列表页 / 弹窗） | `Wb.open({ url:'m?xwl=…', title, params })` | `events.*` 里 |
| **文件上传 / 导入入口** | `Wb.upload({ form: app.form1, url:'m?xwl=…', success })` | `events.*` 里 |
| **后台 Spring 方法** | `Wb.requestAg({ params:{ bean, method, …业务参数 } })` | `events.*` 里 |
| **服务端 xwl 调 xwl** | `app.execute('m?xwl=…')` | `module.configs.serverScript` |

> 各条通路在样本工程里的**出现次数**（哪个最常用）见
> [`references/measured-data.md`](references/measured-data.md) §一 —— 与你怎么改无关，只作量级参考。

### 5.1 怎么读一个 `m?xwl=` 引用

引用写的是**模块相对路径、不带 `.xwl` 后缀**：

```text
m?xwl=<模块>/<业务目录>/xxxSql/queryBizList
   → 文件 = wb/modules/<模块>/<业务目录>/xxxSql/queryBizList.xwl
```

- **从引用找文件**：补上 `.xwl` 即可。
- **从文件找引用方**：在 xwl 里搜 `m?xwl=<该路径去扩展名>`。
- 被引用的片段是**常态**而不是特例（同一个工程里引用点常有数千处）。

### 5.2 url 的三种写法

| 写法 | 例 | 说明 |
|---|---|---|
| `m?xwl=<模块相对路径，**不带 `.xwl`**>` | `m?xwl=<模块>/…/xxxSql/queryBizList` | **最常用**。相对 `wb/modules/`，补 `.xwl` 就是文件路径（见 5.1） |
| `/<短名>` | `/upload`、`/get-file`、`/download` | 短名注册表 **`wb/system/url.json`**，框架内部端点。改动时别自己编短名 |
| `http://…` 或任意 url | `Wb.open({url:'http://…', inframe:true})` | 外部地址必须 `inframe:true` |

> `Wb.request` / `Wb.open` / `Wb.upload` / `Wb.requestAg` 的 `url` 都可以给**完整带查询串**的形式，
> 但参数的规范位置是 `params`（或 `out`），不要手拼查询串。

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

### 5.4 四条通路怎么写

**什么时候用哪条**见上面的总表。完整写法（代码模板、回传怎么收、参数全表与坑）见
[`references/js-api.md`](references/js-api.md)；这里只给「最短骨架 + 最容易踩的」：

| 通路 | 什么时候用 | 最短骨架 |
|---|---|---|
| `Wb.request` | 不建页面，只要结果（查询 / 校验 / 取数） | `Wb.request({url:'m?xwl=…', params, success:function(resp){…}})` |
| `Wb.open` | 打开子页面（列表页 / 弹窗） | `Wb.open({url:'m?xwl=…', title:'…', params:{…}})` |
| `Wb.upload` | 文件上传 / 导入（`form` 里必须有 `file` 控件） | `Wb.upload({form: app.form1, url:'m?xwl=…', success:function(form,action,value){…}})` |
| `Wb.requestAg` | 调后台 Spring 方法（保存 / 落库） | `Wb.requestAg({params:{bean:'…', method:'…', …}})` |

**回传怎么取**（写 `success` 回调时最常用的一条）：`dataprovider` 出的数据是
`Wb.decode(resp.responseText).rows` / `.total`；`serverScript` 里 `app.send(x)` 出来的是 `x` 本身。
四种响应形态的对照表、四条通路各自的选项与回调签名见
[`references/js-api.md`](references/js-api.md)。

三条最容易踩的：

1. **别用 `Wb.request` 代替 store** —— 列表 / 分页 / 排序要用 `store.load(...)`，
   框架会带上 `page` / `start` / `limit` 并处理返回。
2. **`Wb.requestAg` 不用写 `url`**（框架固定改成 `m?xwl=common/save-all`），但 `bean` / `method`
   必须给；业务参数名要与后台取参名一致，否则取到空。
3. **上传类失败的错误对象与别的通路不同**（`action.response.responseText` → `{msg}`），别混用。

## 六、SQL 片段：`module.serverScript` ↔ `dataprovider`

被 store 引用的「SQL 文件」不是散装 SQL，而是固定的**两级结构**：

```text
(页面钥匙 7 把，真实键序见 1.4)
└─ type="module"          configs{ itemId, serverScript }        ← 取参数、拼条件
   └─ type="dataprovider" configs{ itemId, sql, totalSql?, … }   ← 执行 SQL、出数据
```

改 SQL 时最容易错的就是下面三条，先记住：

1. **`dataprovider.sql` 用 `{#名字#}` 引用 `serverScript` 注入的值** ——
   源头是 `request.setAttribute('sql', …)`，所以 SQL 里写 `{#sql#}`。
2. **`{#sys.*#}` / `{#Str.*#}` 是框架内置**（会话 / 权限），不用自己提供；
   **`{?名字?}` 是绑定参数**（`PreparedStatement`，不是文本替换 —— 别手工拼值）。
3. **参数名 = 控件的 `itemId`**，一路同名到 `{?名字?}`；**对不上不会报错，只取到 null，
   SQL 条件静默失效**。页面把值送出来有两条通路（`out` / `params`），**新写查询推荐 `out`**。

**一条硬规则（有源码原文）**：**serverScript 里禁止写 `{#…#}`** ——
`ServerScript does not support {#param#} feature, please use app.get(param) instead.`
在 serverScript 内部取参数要用 `app.get('名字')`。

改 SQL 同样走 `patch`，用 **`@itemId` 寻址**（不用知道嵌套层级）：

```bash
python scripts/xwl.py paths   <file.xwl>                            # 拿路径（同时给「原路径」与「@写法」）
python scripts/xwl.py patch   <file.xwl> --ops ops.json --dry-run   # 看 diff
python scripts/xwl.py sqlrefs <file.xwl>                            # 改完验 {#名字#} 与 serverScript 是否自洽
```

```json
[
  {"op": "set", "path": ["@dataprovider", "configs", "sql"],
   "value": "select t.* from biz_table t\nwhere 1=1\n{#sql#}"},
  {"op": "set", "path": ["@module", "configs", "serverScript"],
   "value": "var data = app.get();\nvar sql = '';\nrequest.setAttribute('sql', sql);"}
]
```

**展开内容** → [`references/sql-fragments.md`](references/sql-fragments.md)：
两个字段的合法 configs 全集、三种占位符对照表、执行器类与源码依据、serverScript 常用 API 词频、
`out` / `params` 两条通路的完整规则（收集机制、`%` / `$` 前缀、重名与 `hidden` 行为、
同名时谁覆盖谁）、命名契约与完整链路、`sqlrefs` / `params` 的用法与实测数字。

## 七、itemId 命名规范与重名处置

`itemId` 既是设计器里的节点名，**也是事件 JS 取控件的键**。重名**不是一律有问题** ——
判据是三条：**控件类型 + 是否已被 JS 引用 + 有没有 `normalName`**。

### 7.1 框架怎么把控件交给 JS（这决定了重名的后果）

WebBuilder 改过的 `Ext.ComponentManager`（在 `wb/libs/ext/ext-all-debug.js` 里，
**按符号名 `ComponentManager.register` 搜，别按行号找**）。源码原文见
[`references/measured-data.md`](references/measured-data.md) §7.5。两条结论各自对应一类现象：

1. **注册键是 `normalName || itemId`** —— `normalName` **优先**。所以只要每个同名控件各有互不相同的
   `normalName`，就根本不会撞车，JS 走 `app.<normalName>`。（这就是第二条规则的由来。）
2. 注册是**普通赋值**、`unregister` 是**按同名键直接 `delete`** ⇒
   **后创建的覆盖先创建的**，且**任一重复项被销毁时会把整个名字从页面作用域删掉** ——
   哪怕另一个同名控件还活着。这正是"重名后 `app.X` 取不到值 / 取到的不是你以为的那个"的确切来源：
   **打开一个窗口再关掉，另一个同名控件就"消失"了**（事件 JS 里表现为偶发、难复现的取不到值）。

### 7.2 三类控件，三种规则

| 类型 | 重名 | 依据与约定 |
|---|---|---|
| **grid 的列** `column` / `tcolumn` | **允许** | 命名约定：**字段名 + `_COL` / `Col` 后缀**。取数走 `app.<grid>.getSelection(0).data.XXX`，**不直接取列控件** ⇒ 列名撞车不影响取值 |
| **取值控件**（14 个 `Ext.form.field.*`） | **靠 `normalName` 区分** | 一般是"选中一条数据的详细展现"，`itemId` 默认就用字段名，重名不可避免。**加了 `normalName` 之后 JS 写 `app.<normalName>`** |
| **按钮 / `item` / 面板 / `tab` / `toolbar` / 数据承载** | **不允许** | 新代码**必须**把 `itemId` 区分开。老代码若已如此且**没被 JS 引用**，可以不改；**一旦被 JS 引用就是真 bug** |

第四种情况：`itemId` **不是合法 JS 标识符**（含中文 / 空格 / `.` 等）—— 这种名字只能用
`app.get('名')` 取，点号访问不适用，所以 `itemids` 把这类重名判为无害。

> `normalName` 是**合法 configs 键**，但**不是所有控件都接受**：注册表 `wb/system/controls.json` 里
> 有一部分控件的 `configs` 没有这个键（多是布局 / HTML / 后端节点）。给不接受它的类型写
> `normalName` 属**非法配置** —— `itemids --fix normalName` 会跳过并回报。查具体某控件：
> `xwl.py schema <type> --controls wb/system/controls.json`。

各类在**样本工程**里的实测组数、比例与按类型的分布见
[`references/measured-data.md`](references/measured-data.md) §七。那些数字只是**一个样本的量级参考**，
不要当成通用阈值 —— **在你自己的工程上跑 `itemids` / `check` 才是该工程的真实情况**。

### 7.3 遇到重名：先读父子关系，再把候选交给用户选

**不要**"删一个"、"随便挑一个"、或"重名就不处理"。按这个顺序做：

```bash
python scripts/xwl.py itemids <file.xwl> --dups-only       # 重名组：分级 + 候选清单 + 建议值
python scripts/xwl.py itemids <file.xwl> --name tbar       # 只看一个名字的全部候选
python scripts/xwl.py itemids <file.xwl> --suggest         # 生成改名 ops 草稿（**需人工确认**）
```

1. **读祖先链**判断"哪个才是真正要改的"。例如同名工具栏 `tbar` 分别挂在 4 个 `grid` 下，
   其中 3 个已经各有 `normalName`、只有 1 个没有 —— 要"补"的就是那一个，而不是去动别人。
2. **把候选列给用户，让他选**。工具只提建议、不替用户定；`itemids` 的建议值照**命名惯例**推：
   - **补 `normalName`**（推荐，不动 `itemId`，零破坏）：**原名 + 父级 `itemId` 的"区分段"** ——
     `tbar` 挂在 `gridLeft` 下 → `tbarLeft`；挂在 `gridUser` 下 → `tbarUser`。
   - **改 `itemId`**（须同步改 JS 引用，所以是**兜底手段**）：**父级 `itemId` 作前缀** ——
     父级 `panelX` 下的 `find` 按钮 → `panelX_find`。
3. 用户定了之后才走 `patch`；改 `itemId` 的**必须同步改事件 JS 里的引用**，并复查 `itemids`。

> 优先级：**能用 `normalName` 就用 `normalName`**（`--fix auto` 已如此）—— 它不动 `itemId`，
> 不会破坏任何已有引用；只有类型不接受 `normalName` 时才回退到改 `itemId`。

> 想知道**某个工程整体**有多少重名：在**你自己的工程**上跑一遍就是最新结果 ——
> `itemids <file> --dups-only`（单文件明细）、`check`（该文件的 error / warn 计数）、
> `itemids <file> --json`（机器可读，便于汇总）。
> 样本工程的一份完整分布（各档组数 + 按控件类型的 Top）见
> [`references/measured-data.md`](references/measured-data.md) §7.2，只作**量级参考**。

### 7.4 精确定位某一个：`@itemId#N` 与「串联 `@` 限定」

`path` 里 `@itemId` 段要求唯一；重名时**不猜顺序**，报错并附候选清单。想指名第 N 个（**N 从 1 起**）：

```json
[{"op": "set", "path": ["@tbar#3", "configs", "normalName"], "value": "tbarGrid"}]
```

或者**串联 `@` 段**当"带父级的限定名"用 —— 后一段只在上一段的子树里找：

```json
[{"op": "set", "path": ["@gridUser", "@tbar", "configs", "normalName"], "value": "tbarUser"}]
```

## 八、常见问题（FAQ）

**15 条**高频问题与排错处置在 [`references/faq.md`](references/faq.md)：
`check` 报 FAIL 怎么排查、`app.X` 取不到值、页面白屏 / 解析错误、能不能压成一行（以及压行的后果）、
设计器里看不到新文件、SQL 抽取报 `1064`、`node --check` 误报、改了 SQL 参数查询不对、
能不能批量文本替换、怎么确认没改坏、为什么不能用严格 JSON 解析器、`expand` 没变化、
`check` 慢或没装 `node`、`new` 骨架的 `itemId` 能不能改、脚本 / CI 里怎么判断成败。

> 出问题**第一站是那份 FAQ**（按症状查）；**动手前**想避开已知的坑，看
> [`references/anti-patterns.md`](references/anti-patterns.md)。

## 九、改完的自检清单

**29 项**清单（改已有文件 23 项 + 新建文件 6 项）在 [`references/checklist.md`](references/checklist.md) ——
交活前逐条过一遍。按主题分了五组：改文件 / 改引用与结构 / SQL 与传参 / `itemId` 命名 / 新建文件。

> 其中最容易跳过、后果最重的三条：① 多行源**绝不能**压成一行；
> ② 真跑 `patch` 必须带 `--backup`；③ 新建文件必须在**设计器里打开过一次**
> （`check` 只证"格式能加载"，不证"页面能用"）。
