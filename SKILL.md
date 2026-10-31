---
name: webbuilder-xwl-patch
slug: skill-webbuilder-xwl-patch
displayName: webbuilder-xwl-patch
version: 1.7.9
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
| **规模** | 跨 5 个工程 / **8 个 wb 根**已在 **≥2.5 万 .xwl** 上实测（口径：8 个 wb 根 `modules/**`、排除 `target/`；时点 2026-10-19；精确值、复算命令与语料快照指纹见 [`references/measured-data-skeleton.md`](references/measured-data-skeleton.md) §十），最大单文件 **728.8 KB**（746299 字节，按 1024 算）。该量级下 `check` 全开约 **0.56 s** —— **性能不是约束**。**工具没有任何文件大小上限**，但**未验证**过 1 MB 以上的文件、或单文件事件段极多的情形 |
| **能改的前提** | 目标文件能被加载器解析（即 `check` 的 ④ 通过）。已经是坏文件的，先用 `edit` 做文本级修复 |

> 上表「规模」是**样本实测值，不是硬上限** —— 换工程要自己测。别把两处数字混起来：**这里**是"跨 5 个
> 工程、最大到什么量级"；[`references/measured-data.md`](references/measured-data.md) 的 2780 / 2777 是
> **统计口径**（只取自其中**一个**工程）。大文件上 `check` 为什么慢、怎么绕开 —— 见
> [`references/faq.md`](references/faq.md)「`check` 慢，或者本机根本没装 `node`？」。

## 怎么用

| 入口 | 怎么进 |
|---|---|
| **① 对话里直接说**（推荐） | 在 Agent 对话中描述任务即可，不必记命令。以下说法都会命中本 skill：<br>「改 xxx.xwl / 加个按钮 / 挂个点击事件 / 改页面上的 SQL / 这个页面白屏了 / 报解析错误 / `app.X` 取不到值 / 新建一个页面或 SQL 文件 / 新建的页面在设计器里找不到 / 把 xwl 里的 SQL 抽出来灌库跑一遍」 |
| **② 命令行直调** | 不经过 Agent、要自己跑或写进脚本时：`python <skill根>/scripts/xwl.py <子命令>`（`<skill根>` ＝ 本 skill 的**安装目录**，⛔ 别写裸 `scripts/xwl.py` —— 你的 cwd 是业务工程）；`--help` 看全部子命令；⛔ 别往安装目录写 ops／业务 `.xwl`／备份／临时夹具（会被更新覆盖、且可能是只读） |

**本 skill 不提供 GUI / 菜单入口** —— 它是命令行工具 + Agent 指令集。非技术用户让 Agent 代跑就行。

**这张表兼作参考材料索引**（下表出现的 `.md` 就是本 skill 的全部参考材料，**不必通读，按需查**）：

| 你要做的事 / 想查的材料 | 去哪 |
|---|---|
| 先搞懂 xwl 是什么、有哪些硬规则 | 第一、二章 |
| 动手改（第一次用） | **第三章**，照第 0 → 5 步走 |
| 查子命令 / 退出码 / 环境依赖 | 第四章 |
| 改引用、传参、写 `events` 里的 JS | [`references/js-api.md`](references/js-api.md) |
| 加 / 改窗口（`createInstance`、`closeAction`、`app._X`） | [`references/js-api.md`](references/js-api.md) §5 |
| 提交前取 grid 的变更集（新增 / 修改 / 删除） | [`references/js-api.md`](references/js-api.md) §6《`Wb.getModified` —— 取 grid 的变更集（用法约定，非平台契约）》 |
| 改 SQL 片段（`serverScript` ↔ `dataprovider`） | [`references/sql-fragments.md`](references/sql-fragments.md) |
| 处理注册键重名 / `@itemId#N` 寻址 | [`references/faq.md`](references/faq.md)「附录：itemId 命名规范与重名处置」 |
| 出问题了（按症状查） | 第五章 + [`references/faq.md`](references/faq.md) |
| **动手前**扫一遍"别这么干" | [`references/anti-patterns.md`](references/anti-patterns.md) —— 23 条，标了哪些是**静默**的 |
| **交活前**逐条过 | 第六章 + [`references/checklist.md`](references/checklist.md) —— 30 项 |
| 换控件 / 不知道用哪个 / 该挂哪里 | [`references/controls.md`](references/controls.md) |
| 定布局：面板该多高、列宽与列网格、`region` 拉伸、工具条挂法 | [`references/layout.md`](references/layout.md) |
| 值映射：`keyName` vs `renderer`、多选三路来源、值往返与存储格式 | [`references/value-mapping.md`](references/value-mapping.md) |
| 脚本化生成：什么时候该写脚本、`configs` 归一、双层闸、换行对齐 | [`references/generation.md`](references/generation.md) |
| **HTML → xwl 转写**：默认做法 / 必须回问 / 不预设 | [`references/transcription-defaults.md`](references/transcription-defaults.md) |
| 想看一次完整实操（从零造页面 + SQL 载体） | [`references/walkthrough.md`](references/walkthrough.md) |
| **装到本机 / 升级卸载 / 命令该在哪个 cwd 跑** | [`references/distribution.md`](references/distribution.md) |
| 想跑最小示例（每条命令都真跑过） | [`examples/README.md`](examples/README.md)（示例 `.xwl` 用 `xwl.py new` 现场生成，不在仓库里预置） |
| 数字从哪来（引用次数 / 分布 / 统计口径） | [`references/measured-data.md`](references/measured-data.md) |
| **为什么这么定**（判据依据、踩过的坑、已作废的做法） | [`references/workflow-notes.md`](references/workflow-notes.md) |
| 查 **itemId / normalName 重名**的数据依据 | [`references/measured-data-addressing.md`](references/measured-data-addressing.md) |
| 查**设计器写回 / 控件 / 窗口**的实测 | [`references/measured-data-designer.md`](references/measured-data-designer.md) |
| 查 **SQL 分布 / 判据修正对照数** | [`references/measured-data-criteria.md`](references/measured-data-criteria.md) |
| 查**顶层骨架 / folder.json / 规模耗时** | [`references/measured-data-skeleton.md`](references/measured-data-skeleton.md) |
| 查**判据因果 / 守卫维护 / 豁免面** | [`references/workflow-notes-guards.md`](references/workflow-notes-guards.md) |
| 查**守卫维护 / 豁免 / 自检运行器** | [`references/workflow-notes-guards-maintenance.md`](references/workflow-notes-guards-maintenance.md) |

> `references/anti-patterns.md`、`references/faq.md` 是**查询式规格（规格层）**，不受 8k 约束（8k 只约束记忆类的"按需读一次"成本）；⚠️ 上表拆出的**主题文件属依据层，仍受 ≤8k 约束**（逐件字符数由自检复量）。

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

**两类的格式规则与处置方式完全相同**，区别只在于：改片段时你要额外确认"谁在用它"。SQL 类片段（`dataprovider` + `serverScript` + `{#…#}` / `{?…?}` 占位符）的写法见 §2.7。引用规则见 [`references/js-api.md`](references/js-api.md)「附录：引用通路总表与代码位置」。

### 1.2 控件节点的标准形态

**别凭印象拼节点字段。** 权威来源是设计器自带的控件注册表 `wb/system/controls.json`。
两种键集（**键序固定** `configs, expanded, children, type`，有事件时末尾多 `events`）、
`itemId` 的**唯一性**（工具寻址用 `@itemId`）与「少写 `expanded` / `children` 会**与设计器产物不一致**」见
[`references/controls.md`](references/controls.md) §4.2 典型骨架；查单个控件用 `xwl.py schema --help`。

注册键取 `normalName`（优先），否则取 `itemId`。**必须唯一**；重名且被事件 JS 引用会**静默取不到值**（`error`），未被引用为 `benign`。处置顺序：**先读父子关系判断真实目标 → 把候选交给用户选**，⛔ 不要"删一个"或"挑一个"；精确表达式与分类表见 [`references/faq.md`](references/faq.md) 附录，框架机制（`ComponentManager`／`unregister`）见 [`references/measured-data-addressing.md`](references/measured-data-addressing.md) 的 `7.5`。

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
> [`references/measured-data-skeleton.md`](references/measured-data-skeleton.md) §九。

引用三种写法：`m?xwl=<模块相对路径，不带 .xwl>`／注册短名／外部 URL，**外部地址须 `inframe:true`**；写在不同位置（事件／store／列配置／服务端脚本／页面顶层），位置表见 [`references/js-api.md`](references/js-api.md)「附录：引用通路总表与代码位置」。

> **要补齐这类「缺钥匙」文件时**：`set` 一个**原本不存在**的顶层键就是**新建键**，该 op 要带 `"create": true`
> （或命令行加 `--allow-new-key` 全局放行；不给则默认拒绝、rc=2 —— 示例与两条出路见 §3.1）。

## 二、格式硬规则与文件形态

### 2.1 硬规则（多行源的磁盘形态）

> 磁盘形态与 5 条硬规则（**无 BOM** / **换行一致** / **续行符 `\`** 后不能有空白 / **末行不加** `\` /
> 值里的 `"` 写成 `\"`、JS 用**单引号**）见 [`references/faq.md`](references/faq.md) §一。

### 2.2 单行源 vs 多行源（**决定性规则**）

改之前先判形态（`xwl.py check` 会给出提示）。**两种源的处置完全不同**：
**多行源**（含结构换行）**绝对不能压成一行**，任何理由都不行；
**单行源**（整份紧凑一行）就在一行形态上改，**可以**转成多行、且能做到与设计器逐字节一致。

> 上一句「单行源就在一行形态上改」只说**格式上允许** —— 用 `patch` 改单行源的结果**一定是多行**，
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
> [`references/measured-data-designer.md`](references/measured-data-designer.md) §五。

`auto` 怎么定：**只有一种**换行（全 CRLF / 全 LF / 全 CR）⇒ **沿用它**（含纯 CR）；**混用多种** ⇒ 只在
**CRLF / LF** 取多数（等量取 CRLF）、**裸 CR 不参与投票**；**一个换行符都没有**（紧凑单行源正属此类，样本工程 902 个）⇒ 无从"沿用"、**回退 LF**。

### 2.5 值里的「字面反斜杠 + n」为什么长得别扭

> 「字面反斜杠 + n」的**机制**、**语义无损**（与原文件**逐字节相同**）与**默认 / `--safe`** 的取舍
> （**按"这个文件给谁看"决定**：要提交用默认、只人读用 `--safe`）见
> [`references/measured-data-designer.md`](references/measured-data-designer.md) §5.2；反例与替代（人读用 `xwl.py sql` / `events`）见
> [`references/anti-patterns.md`](references/anti-patterns.md) 第 20 条。

### 2.6 压平检测：`diffguard`（相对 git 基线）

> `diffguard` 的**判据**（定义级 / **粗筛**）、漏报面、前置必要条件、跳过与退出码、成本与 `--rev` 用法见
> [`references/faq.md`](references/faq.md) §三 与 [`references/workflow-notes-guards.md`](references/workflow-notes-guards.md) §二③；
> **它只在 git 仓库里有意义**，且**只扫改动过的文件**，别对整个 `wb/` 跑。提交前该跑一次，见**第三章第 5 步**。

### 2.7 SQL 载体的两级结构

被 store 引用的 SQL 文件是固定的**两级结构**：

```text
(7 把钥匙，键序见 1.3)
└─ type="module"  configs{ itemId, serverScript }  ← 取参数、拼条件
   └─ type="dataprovider"  configs{ itemId, sql, totalSql?, … }  ← 执行 SQL、出数据
```

`serverScript` 只产**条件片段**（`{#x#}` 是**文本替换**，⛔ 别在 `dataprovider` 再写一遍完整 SELECT），其余见 [`references/sql-fragments.md`](references/sql-fragments.md)。`params --upstream` **默认关**：开时单根全扫、多两段分组、**不并入 `provided`、不改退出码**；零成本与那条 `[note]` 见 [`references/faq.md`](references/faq.md)，口径见 [`references/measured-data-criteria.md`](references/measured-data-criteria.md) 的 `11.3`／`11.4`。

## 三、处理流程

> **先把结论说清楚**：改 xwl **可以完全遵循设计器规则、并且不犯错** —— 只给出「值」，
> 让工具按设计器算法重建文件（第 3 步的 `patch`），你根本不碰文本层。

**改已有文件从第 1 步起；从零造新文件先走第 0 步。**

> **转写（HTML → xwl）的决策归属**：skill 直接拍三件**默认做法** —— ① 不可见参数 ⇒ 用其**语义类型**的控件（`text` / `combo` / `button`）＋ `configs.hidden:"true"` 属性（⛔ **不是** `type:"hidden"`）；② 列表分页 ⇒ **不填 `pageSize`**；③ 必填校验 ⇒ **命令式**写进触发按钮的 `click`。只**回问两件**：真实后台取数（表名 / 字段 / 接口）与页面标题 / 菜单名。产物落点（模块路径 / 页面名）**既不预设、也不回问**，留待使用时提供。⚠️ **同名不同型**：页面**顶层** `hidden` 是 **bool**，控件 **`configs` 级** `hidden` 是**字符串**。详见 [`references/transcription-defaults.md`](references/transcription-defaults.md)。

### 第 0 步 · 新建文件

```bash
# 独立页面：顶层 7 把钥匙 + 一个空 module 节点
python <skill根>/scripts/xwl.py new wb/modules/<模块>/myPage.xwl --kind page --title "我的页面"
# SQL 载体：module(serverScript) → dataprovider(sql)，被页面用 store.url='m?xwl=…' 引用
python <skill根>/scripts/xwl.py new wb/modules/<模块>/xxxSql/queryXxx.xwl --kind sql --title "出库单查询"
```

`new` 内置了 1.3 那套**设计器真实键序**，所以：

- **顶层键不用管** —— 手写时漏掉 `inframe` / `pageLink`，`check` 照样 ALL OK，问题会被静默吞掉；
- **也不要用 `cp` 别的文件再整树重写** —— 种子是**继承式**的：它顶层没被显式覆盖的键会
  **静默残留**（种子的 `roles:{"demo":1}` 会跟着进新页面）。实测证据见
  [`references/measured-data-skeleton.md`](references/measured-data-skeleton.md) §九；
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

> `ops.json` 的五种 op（`set` / `insertKey` / `insert` / `append` / `delete`）示例见 `xwl.py patch --help`（`epilog`）。

> `path` 里对象键的 `@itemId` 写法与**不猜顺序**的三种出路（`@名字#N`、串联 `@`）见 `xwl.py patch --help`，重名处置见 1.2 节。

> ⚠️ `paths` **只列** `sql` / `totalSql` / `serverScript` / `url` 四类字段 ——
> **按钮、网格等控件的 `itemId` 不在它的输出里**。要 `patch` 某个 `events.*`（如给按钮改 `click`）时，
> 用 **`xwl.py itemids <file>`** 看重名报告，或直接试跑并接受工具的候选清单报错；处置见 §1.2。

> `paths` / `dump` 的用途与选项见各自的 `--help`（写 `path` 时**别漏 `configs` 一层**）。

> `set` 到一个**原本不存在**的**对象键**（如给缺 `inframe` 的页面补它）就是**新建键**。**这个开关只约束对象键** ——
> 补**数组元素**走 `append` / `insert`，本就不算新建键（`"create"` 挂在这两种 op 上属用法错误）。
> 任意一条 set 可带 `"create": true`：补**原本不存在的键**时用它；写到已存在的键上是幂等保护。
>
> 默认：**`set` 到原本不存在的键会被拒绝（打印 `[FAIL]`、rc=2）**，报错会直接教两条出路 —— **给该 op 加 `"create": true`**（逐条放行）**或命令行加 `--allow-new-key`**（全局放行，两者任一即放行）；写到**已存在的键上不受影响**。

```json
[{"op": "set", "path": ["@panel1", "configs", "newKey"], "value": "v", "create": true}]
```

> 归全局开关 `--allow-new-key` 放行的那批新建键，真跑时在 stdout 打这条痕（`--dry-run` 另把**带 `create`** 的待建键单列一行 `[new-key]`）：

```text
[warn] --allow-new-key 已放行 2 个新建键：@panel1.configs.newKeyA, @panel1.configs.newKeyB
```

1. **能用 `@itemId` 就别手写下标** —— `paths` 给出的 `["@dataprovider","configs","sql"]`
   不受嵌套层数影响，比 `["children",0,"children",0,"configs","sql"]` 稳得多。
   必须手写下标时，先用 `dump` 确认那一层**确实有**那个元素。
   > `paths` 的「原路径」**已经带 `configs` 一层**（`["children",0,"configs","serverScript"]`），照抄即可。
   > 手写时**别漏这一层** —— 漏了 `patch` **不会报错**，而是把字段写到节点根上（静默语义损坏，`check` 不拦）。
2. 写 `ops.json`（`set` / `insertKey` / `insert` / `append` / `delete`）。
3. **`--dry-run` 是硬闸门，不是建议** —— **没看过 diff 就不许真跑**。
   工具**不会**替你拦这一步（它没法知道你脑子里确认过没有），所以这条靠自律；
   `--backup` 是**兜底**，不是"跳过 dry-run 的理由"。

```bash
# 先看将产生的 diff（不写入）
python <skill根>/scripts/xwl.py patch <file.xwl> --ops ops.json --dry-run
# 真改（--backup 会先写 <file>.bak）
python <skill根>/scripts/xwl.py patch <file.xwl> --ops ops.json --backup
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
> 重排的"顺带规整"与 diff 最小化口径见 [references/measured-data-designer.md](references/measured-data-designer.md) §五；想压小 diff 改用 3.2 的 `edit`（语义相同、只含你改的那一处）。

> 改 **SQL / serverScript** 时，`path` 用 `["@dataprovider","configs","sql"]` 这类写法 —— 见 §2.7。

#### 3.2 文本级 `edit`（例外情况）

用它就得自己守两条硬要求：`newline=''` 保留原换行 + **替换前断言锚点唯一**。

```bash
python <skill根>/scripts/xwl.py edit <file.xwl> --old-file old.txt --new-file new.txt --expect 1 --dry-run
```

> 「锚点出现次数」是**信息**不是障碍：工具会报出实际次数。出现多次时把锚点**扩到足够上下文**
> 直到唯一，**不要**用 `--expect N` 去批量替换。

> **两条路都禁止**用普通编辑器 / 通用 Edit 工具直接改 xwl —— 它们会写成裸 LF，破坏格式。

### 第 4 步 · 格式校验（**改完必跑**）

`check` 只做静态、文件级校验，不证页面可用；改完必跑，逐项判据与命令见 [references/faq.md](references/faq.md)「附录：格式校验与页面交付验收」。
页面类交付须过四道验收：`check`、`check --controls`、设计器打开、人工看布局交互；有库时条件追加连库实跑 SQL。
完整的 ①–⑩ 分工、写盘后自动校验边界、回退与脚本两坑一并在该附录，布局判据见 [references/layout.md](references/layout.md)。

### 第 5 步 · 提交前扫一遍（`diffguard`。**只在 git 仓库里有意义**）

第 4 步的九项**只能证明"文件自身格式没坏"**，证不了"没人把多行悄悄压平" —— 压平后文件是**自洽**的。
提交前补这一刀：

```bash
python <skill根>/scripts/xwl.py diffguard <改过的文件或目录>            # 默认只告警
python <skill根>/scripts/xwl.py diffguard <改过的文件或目录> --strict    # CI / pre-commit：让它阻塞
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
| `check` | 九项校验：格式五项 + 事件 JS 语法 + **注册键**重名分级 + **`configs` 值类型** + 加载链完整性（只提示）；**给了 `--controls` 时另校 `configs` 键（⑨）与内联 `[js]`** |
| `diffguard` | **相对 git 基线**检测「多行内容被压平」 |
| `itemids` | 注册键重名报告 + 建议改名（只读） |
| `paths` | 列出 `sql` / `totalSql` / `serverScript` / `url` 四类字段的位置 |
| `params` | 核对「页面 → store → SQL」传参链路（缺来源**默认只告警**、`--strict` 才判失败；`--upstream` 追加「谁在调用本页 / 谁引用本载体」的上游扫描） |
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
| `1` | **被检查对象或查询结果有问题**（`check` 有 `[FAIL]`；`paths` / `sqlrefs` / `sql` / `events` 没找到目标字段 —— 即无可抽取内容、空结果判 `1`） |
| `2` | **用法或前置条件不满足**（缺必填参数、`edit` 锚点次数不符、`new` 拒绝覆盖、读不到目标文件；**`check` 的 `--controls` 取不到控件注册表** —— 此时 ①–⑧⑩ 已照常判定，只有 ⑨ 与 configs 内联 `[js]` 未校） |

两类**判定会随命令线宽严变化**的命令，各自三档（默认 / 收紧 / 放松）：`diffguard`（疑似压平默认只告警，
`--strict` 判失败 rc=1、一个文件都没比成才 rc=2，非 git 仓库 / 新文件以 `[note]` 跳过）；`params`（缺来源默认只告警，`--strict` 判失败，
缺来源时打一行 `[note]` 告知怎么改成阻塞）。

> **原则：判定变严要喧哗、放松要留痕** —— 收紧必须让调用方**当场**看得见（`[FAIL]` / rc≠0）；
> 放松必须留一条**可查的预告行**（`[note]`），不能悄悄改掉默认行为。
> 退出码与行首标记（`[warn]` **不影响退出码**，"1 与 2"**不是严格二分**）见 [references/faq.md](references/faq.md) §四。

### 4.3 环境依赖与自检

> 环境依赖（**Python 3.9+** / 纯标准库；`node` 可选，按 `--node` → `NODE_BIN` → `PATH` 定位、
> 找不到降级）见本文「适用范围与前提」的环境行与 [`README.md`](README.md)。
> 全部参考材料与示例的索引在**本文开头的「怎么用」表**里（那张表就是索引），此处不重复。

## 五、常见问题（FAQ）

**24 条**高频问题在 [`references/faq.md`](references/faq.md)，按四组归类：① 格式与解析 / ② 命名与引用 /
③ 能不能这么改 / ④ 命令行为（设计器看不到新文件、SQL 抽取报 `1064`、`check` 慢或没装 `node`、脚本 / CI 怎么判断成败等）。

> 出问题**第一站是那份 FAQ**（按症状查）；**动手前**想避开已知的坑，看
> [`references/anti-patterns.md`](references/anti-patterns.md)。

## 六、改完的自检清单

**30 项**清单（改已有文件 24 项 + 新建文件 6 项）在 [`references/checklist.md`](references/checklist.md) ——
交活前逐条过一遍。按主题分了七组，**与 [`references/anti-patterns.md`](references/anti-patterns.md) 的分组对齐**（七组 ↔ 反模式组的对照表在 [`references/checklist.md`](references/checklist.md) 开头）。

> 其中最容易跳过、后果最重的三条：① 多行源**绝不能**压成一行（改完用 `diffguard` 扫一遍，
> 这是唯一能自动发现它的手段）；② 真跑 `patch` 必须带 `--backup`；③ 新建文件必须在**设计器里打开过一次**
> （`check` 只证"格式能加载"，不证"页面能用"）。
