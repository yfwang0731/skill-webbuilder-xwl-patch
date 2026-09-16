# 实测数据与统计口径

> **样本**：样本工程 `wb/` 下 **2780 个 `.xwl`**（其中 **2777 个可解析** —— 3 个模板样本不是纯 JSON；
> `target/` 下的部署副本不计入）。引用「2777」的地方都是指可解析的那部分。
> **方式**：用 `scripts/xwl.py` 的解析器遍历 JSON 树统计；**已剔除 JS 注释**（注掉的 `out:` / `params:` 不计）。
> **日期**：2026-09-15（第九节为 2026-09-16 新增）。
> **定位**：数字分三类 ——
> ① **项目用法统计**（一~四、六~九节）：说明「**这个项目实际上怎么写**」，用于判断改动是否跟着现状走，
> **不是规范**，换项目要重新统计；
> ② **工具回放校验**（第五节）：说明「**脚本的复刻准不准**」，与某个项目的编码习惯无关；
> ③ **`new` / `folders` 的形态依据**（第九节）：顶层键序与 `folder.json` 的实测分布。

---

## 一、xwl 引用方式的使用次数

| 引用什么 | 写法 | 写在哪里 | 次数 |
|---|---|---|---|
| **数据源**（SQL 文件） | `store.configs.url = 'm?xwl=…'`（配合 `store.load({out})`） | store 节点的 `configs.url` | 2735 |
| **服务端片段**（SQL / 校验 / 取数） | `Wb.request({ url:'m?xwl=…', params, success })` | 控件的 `events.*` 里 | 1702 |
| **子页面**（列表页 / 弹窗） | `Wb.open({ url:'m?xwl=…', title, params })` | `events.*` 里 | 52 |
| **文件上传 / 导入入口** | `Wb.upload({ form: app.form1, url:'m?xwl=…', success })` | `events.*` 里 | 132 |
| **后台 Spring 方法** | `Wb.requestAg({ params:{ bean, method, …业务参数 } })` | `events.*` 里 | 1534 |
| **服务端 xwl 调 xwl** | `app.execute('m?xwl=…')` | `module.configs.serverScript` | 1 |

## 二、页面传参两条通路的分布

| 所在 API | `out` | `params: {显式键}` | `params: Wb.getValue` |
|---|---|---|---|
| `store.load` | 412 | 1509 | 2 |
| `Wb.requestAg` | — | 1569 | — |
| `Wb.request` | 144 | 1373 | 2 |
| 未识别 / 其它 | — | 255 | — |
| `Wb.upload` | — | 100 | — |
| `store.reload` | 28 | 23 | — |
| `Wb.download` | — | 3 | — |

- **页面维度**：只用 `out` **47** 个 / 只用 `params` **155** 个 / 两者都用 **219** 个 / 无传参 2356 个。
- **`out` 指向的容器 Top**：`app.tbar`(160)、`app.manageTopTbar`(42)、`app.editWin`(31)、
  `app.toolbar1`(29)、`app.gridBasicbar`(29)、`app.toolbar`(23)…
  → 一眼能看出 `out` 主要服务**查询条**与**编辑弹窗**。

**结论**：存量代码以显式 `params` 为主（历史习惯，改动跟着现状走）；
**新写查询用 `out`** —— 条件控件增减不用动 JS。

样本工程**没有**用 `proxy.extraParams` / `setExtraParams` / `Wb.getValues`（各 0 处）—— 别照搬别的项目习惯。

## 三、`Wb.requestAg` 的参数名频次

`bean` / `method` 各 **1400** 处（保留键）。其余业务参数（按 `params: {…}` 内的键名正则统计）：

| 参数名 | 次数 | | 参数名 | 次数 |
|---|---|---|---|---|
| `idList` | 451 | | `type` | 186 |
| `datatable` | 301 | | `panelData` | 113 |
| `className` | 258 | | `dataIds` | 87 |
| `deleteSql` | 258 | | `dataFeeBill` | 49 |
| `insertSql` | 243 | | `id` | 48 |
| `updateSql` | 243 | | `notes` | 46 |
| `data` | 203 | | `ID` | 40 |

即「**表格批量增删改**」的标准组合：`params.data`（`Wb.encode` 的 JSON 字符串）
+ `datatable` / `className` / `insertSql` / `updateSql` / `deleteSql`。

## 四、`Wb.requestAg` 成功回调里做什么（1534 个调用点）

统计 success 回调体内的动作出现比例（同一回调可含多个动作，故和 > 100%）：

| 处理动作 | 占比 | 说明 |
|---|---|---|
| `Wb.tip('保存成功')` / `Wb.info` 提示 | 91% | 最普遍 —— **多数场景根本不看返回值** |
| `store.load()` / `store.reload()` 刷新 | 78% | 列表 / 明细重新取数 |
| `win.close()` 关窗 | 29% | 弹窗式新增 / 编辑保存后的标配 |
| 读 `resp.responseText` | 66% | 返回值常是**普通文本 / 数字**，直接 `if (data == 1)` |
| `Wb.decode(resp.responseText)` | 43% | 返回值是 JSON 时才解析 |
| `Wb.warn(...)` 走失败分支 | — | 后台返回非预期值时常自己判 `else` |

相关：`Wb.upload` 的 `success` 回调里第一个参数名分布（共 139 个带 `success` 的调用点）：

| 第一个参数名 | 处数 | 含义 |
|---|---|---|
| `action` | **101** | **错位一位**（`action` 实际是 form），见 SKILL.md §5.6 |
| `form` | 32 | 顺序正确 |
| （无参） | 5 | 不需要返回值 |
| `resp` | 1 | 命名不规范 |


## 五、设计器写回算法的复刻一致性（回放校验）

**这不是某一次编辑的结果**，而是一次**批量回放校验**：把复刻出的算法
（`IDE.updateModule` 四步）**整体跑在样本工程既有的全部 xwl 上**，
逐个比对「还原出的字节」与「文件原有字节」—— 检验的是**算法复刻得准不准**。

| 项 | 结果 |
|---|---|
| 多行源 | 1875 个中 **1830 个逐字节一致 = 97.6%** |
| 不一致的 45 个 | 都有明确外因：手工改过缩进（4 空格 + 行尾空格）、或另一种写法把 `\u201c` 转义 |
| 单行源（紧凑一行） | **902 个** —— 需要时可 `xwl.py expand` 转多行 |
| 解析失败 | 3 个：`modules/dev/template/{basic-dialog-edit,gridCrud,multiform_mainDetail}.xwl`（模板样本，不是纯 JSON） |

→ 结论：**算法复刻正确**，因此 `patch` 重排**不会顺带改动无关内容**，
diff 只含真正改的内容（实测：377 KB 的一个多行源页面加一个带多行 JS 的按钮 + 改标题，diff **17 行**）。

## 六、控件使用频次与父子结构

见 [`controls.md`](controls.md)：总表有每个控件的「用过的次数」列，
第四节有实测父子结构 Top 45 与典型骨架。

## 七、itemId 与 normalName（重名分级的数据依据）

口径：全项目 **2780 个 xwl**（其中 **2777 个可解析**，3 个失败见第五节）、
**59791 个含 `itemId` 的控件节点**、**599 个文件带事件 JS（共 12304 段事件）**。

### 7.1 `normalName` 的合法性（权威来源 = 控件注册表）

注册表 `wb/system/controls.json` 共 **133 个控件节点**，其中 **89 个**的 `configs` 里含 `normalName`
（类型 `string`），**44 个不含**：

- 接受：`button` `panel` `tab` `toolbar` `grid` `store` `window` `viewport` `text` `combo` `item` `menu`
  `column` `tree` `dataview` `fieldset` `form` `image` `label` …（含全部 `t*` 触屏变体）
- 不接受（**完整 44 个**）：`a` `array` `bbutton` `bcheck` `bform` `bimage` `br` `bradio` `clientscript`
  `dataprovider` `div` `eaxis` `egrid` `elabel` `elegend` `eseries` `etextstyle` `etitle` `etoolbox`
  `etooltip` `folder` `header` `hr` `input` `li` `mailer` `method` `module` `ol` `p` `query` `radio`
  `report` `response` `serverscript` `socket` `span` `sqlswitcher` `string` `treelist` `tsocket` `ul`
  `updater` `xwl`
  —— 绝大多数是纯 HTML 标签（`div` / `span` / `ul` / `p` …）、图表子元素（`eaxis` / `eseries` /
  `etitle` …）或后端节点（`module` / `dataprovider` / `serverscript` …），本来就没有 `normalName`
  这个概念。**给这些类型写 `normalName` 是非法配置**（`itemids --fix normalName` 会跳过并回报）。

### 7.2 重名组的实际分布（按「类型 + 是否被 JS 引用 + 有无 normalName」分级）

| 分级 | 组数 | 说明 |
|---|---:|---|
| benign | 3543 | 无害：**列控件 3393** + **已有唯一 normalName 150** |
| warn | 1919 | 未被事件 JS 引用 —— 老代码可留，新代码须区分 |
| error | 456 | **已被事件 JS 引用 —— `app.<名字>` 取值不确定** |

`error` 组**内的控件**按类型（单位＝**控件节点数**）：`text` 184 / `combo` 163 / `toolbar` 46 /
`grid` 30 / `item` 28 / `number` 22 / `column` 14 / `textarea` 10 / `panel` 6 / `date` 6 …
`warn` 组 **Top**（同单位）：`array` 364 / `item` 362 / `text` 295 / `combo` 272 / `store` 252 /
`number` 152 / `feature` 144 / `toolbar` 121。

> **这两行不能跟上面的组数直接相加** —— 组数是「有多少个重名组」，拆分是「组里有多少个控件节点」，
> **两套单位**。所以拆分项之和会大于组数（`error` 拆到 `date` 已累计 473 > 456；
> `warn` 前 8 项累计 1962 > 1919），这不是矛盾。表格里的 `benign` / `warn` / `error` 一律是**组数**。

**关键结论：列控件的 3393 组重名里，被事件 JS 引用的有 0 组。**
印证了"列控件不直接取、取数走 `app.<grid>.getSelection(0).data.XXX`"这一用法。

按"重名组**全部成员的类型**是否都是取值控件"再切一刀，共 **874 组**：

| 字段控件重名组 | 组数 | 说明 |
|---|---:|---|
| 已各有**互不相同**的 `normalName` | **129** | 已是正确做法：框架按 `normalName \|\| itemId` 注册，不冲突 |
| `normalName` 缺失或彼此重复 | **745** | **待补 `normalName`** —— 这正是"取值控件重名靠 `normalName` 区分"这条规则的落点 |

> ⚠️ **这些数字只是这一个样本工程的量级参考，不是通用阈值** —— 换工程必须重跑。
> 另外它们的口径随工具版本变过：修掉"注释里的 `app.X` 被当成引用"与
> "保留表（`store`/`add`/`items`/`id`）遮蔽真实引用"两个缺陷后，
> error 由 519 降到 456、warn 由 1856 升到 1919（少了 63 组**误报的** error）。
> 这正是"别把样本数字当阈值"的理由。

### 7.3 列的命名约定

全项目 **20771 个** `column` / `tcolumn` 节点的 `itemId` 中，**14213 个（68.4%）**带
`_COL` / `Col` 后缀（如 `ORDER_NO_COL`、`ITEM_NAMECol`），其余 6558 个不带。

### 7.4 `itemId` 的字符集

绝大多数是合法 JS 标识符，但**并非全部**：全项目有 **57 个**节点的 `itemId` 含非 `[A-Za-z0-9_]` 字符 ——
中文（如 `query` 节点上写 `"检查是否存在重复记录"`）、空格、`.`、`(`、`)`、`-`、`+` 都出现过。
这类名字**不能用 `app.X` 点号访问**，只能用 `app.get('名字')`；`itemids` 因此把它们的重名判为无害。

**`#` 从未出现在任何 `itemId` 里** —— 所以 `@名字#N` 用 `#` 作序号分隔符不会与既有名字冲突。

### 7.5 框架侧机制（源码原文）

源码原文见 `SKILL.md` §7.1（`wb/libs/ext/ext-all-debug.js:21689`，WebBuilder 改过的
`Ext.ComponentManager.register` / `unregister`）—— 那里是**规则依据**，这里只记结论，不重复贴。

注册键 = **`normalName || itemId`**（normalName 优先）。
`unregister` 的 `delete` 是"重复会取不到值"的**确切机制**：任一重复项被销毁，
整个名字就从页面作用域消失，哪怕另一个同名控件还活着。
（另见 `ext-all-debug.js:453` 起：`appScope` 在 `Ext.clone` / `Ext.merge` 里被**特意保留引用、不深拷贝**。）

### 7.6 命名惯例的实测证据（供 `itemids` 的建议值参考）

| 惯例 | 实测证据（样本工程） |
|---|---|
| 列名带 `_COL` / `Col` 后缀 | 20771 个列 `itemId` 中 14213 个（68.4%）带此后缀，如 `ORDER_NO_COL`、`ITEM_NAMECol` |
| **`normalName` = 原名 + 父级 `itemId` 的"区分段"** | 4 处：`tbar` 挂在 `gridW` / `grid2` / `gridUser` 下，分别叫 `tbarW` / `tbar2` / `tbarUser`；同一页里**唯一没给 `normalName` 的就是那个不合惯例的** |
| **`itemId` = 父级 `itemId` + `_` + 原名** | 7 处：父级 `itemId` 为 `panelX` 时，子项 `find` 写成 `panelX_find`（分布在 6 个文件） |

> ⚠️ 一个容易误引的例子：`panelCustomRecord_ID` 看着像"`itemId` 用父级作前缀"，但它实测是
> **`normalName`**（两个同名 `text` 靠它区分）—— 属"补 `normalName`"的语境，不要当成 `itemId` 的先例。

## 八、SQL 片段与 `serverScript` 的分布（`sql-fragments.md` 的数字口径）

**文件分布**（样本工程 `wb/` 下）：**1165 个文件带 `serverScript`、1142 个带 `dataprovider`，
其中 687 个两者都有**；另有 **478 个只有 `serverScript`** —— 这些自己用 `app.run` / `app.send`
直接出数据，不靠 `dataprovider`。

**`{#名字#}` 与 `setAttribute('名字',…)` 的同名交集**（按次数）：
`sql` **715**、`sql1` 55、`whereSql` 19…

**三类占位符的实测出现次数**：

| 形态 | 实测例（次数） |
|---|---|
| `{#sys.*#}` / `{#Str.*#}`（框架内置） | `sys.username` 492、`sys.tenancyId` 278、`sys.id` 202、`sys.deptPermSql` 76、`sys.deptId` 27、`Str.home` 26 |
| `{#任意名#}`（由同文件 `serverScript` 注入） | `sql` 715、`sql1` 55、`whereSql` 19 |
| `{?名字?}`（绑定参数，非文本替换） | `ID` 451、`name` 247、`query` 208、`month` 132 |

**被引用路径 / 引用点**：**2000 个被引用路径、5000+ 处引用**。

**`serverScript` 常用 API 词频**：`Wb.isEmpty` 4750 · `app.get` 1328 · `request.setAttribute` 1052 ·
`app.run` 394 · `app.send` 247 · `Wb.decode` 191 · `Wb.each` 178 · `Wb.encode` 134 ·
`request.getParameter` 127 · `SysUtil.getId` 104 · `app.log` 88 · `app.update` 80。

**`sqlrefs` 自洽率**：**1620 个**含 `serverScript` / `dataprovider` 的文件里，**1606 个引用自洽
（99.1%）**；其余为 14 个 `{#sql#}` 本文件未提供（多为「由调用方传入」的场景）、
1 处 `serverScript` 误用 `{#…#}`。

> 这些数字只是**一个样本**的量级参考，不是规范；换工程请以自己的为准。

## 九、页面顶层骨架与 `folder.json`（`new` / `folders` 的数据依据）

**顶层键序**（样本工程 `wb/` 下 2780 个 xwl）：**2750 个**的顶层键集合与顺序都是

```text
hidden, children, roles, title, iconCls, inframe, pageLink
```

**独立页面与被引用的 SQL 载体完全一样**（都是这一套）。少数派是缺 `inframe` / `pageLink` 的
（20 个，如 `dev/ide/add-file.xwl`）与顺序略异的（6 个）。

**7 把钥匙的取值形态**（在 1635 个页面类文件上计数）：

| 键 | 类型 | 实测分布 |
|---|---|---|
| `hidden` | bool | 1635 / 1635 均为 bool |
| `children` | array | 顶层控件树 |
| `roles` | dict | 1635 / 1635 均为 dict；典型 `{"default":1}` / `{"demo":1}` / `{}` |
| `title` | string | 1635 / 1635 出现；其中**空串 65 个** |
| `iconCls` | string | 空串 **1480** / 1635（其余是图标名，如 `add_icon` 28、`accept_icon` 14） |
| `inframe` | bool | 1615 / 1635 出现；**2 个是 `null`** |
| `pageLink` | string | 空串 **1593** / 1615（其余是 `{path:'home',…}` 之类 9 个、`{container:false}` 4 个） |

**`folder.json`（设计器导航树的目录索引）**：

- 覆盖：**565 个含 xwl 的目录中 558 个有它**（缺 7 个）。
- **未被所在目录 `folder.json` 登记进 `index` 的 xwl：322 个** —— 集中在若干**由脚本批量生成**的业务模块
  （未走设计器，路径形态与设计器产物不同）。
- `index` 项的形态：**2440 个带 `.xwl` 后缀，全部对得上文件**；
  **488 个不带后缀，全部对得上子目录**；**同名目录与同名文件并存 55 处**（`xxx`（目录）+ `xxx.xwl`（文件））。
  → 「带 `.xwl` 的是文件、不带的是子目录」这条判据成立，无实测反例。
- **悬空项 14 处**：`index` 里写了、但磁盘上文件/目录都已不在
  （13 个 `.xwl` + 1 个 `dev/autogenControl/2334`）。
- `folder.json` 自身的顶层键序**不固定**（`hidden,index,title,iconCls` 486 个，
  `index,title,hidden,iconCls` 36 个，`title,index,hidden,iconCls` 27 个，只有 `index` 的 8 个…）
  → **改它时不要重排键序、不要改单行形态**（`folders --register` 已按此实现）。

**「种子无关性」实验**（`new` 子命令形态的依据）：对 3 个内容毫不相干的种子套用**完全相同的 ops**
（`set title` / `set roles` / `set children` 整树）：

| 种子 | 顶层键 | 产出 |
|---|---|---|
| 平台自带示例里的最小 SQL 载体（313 B） | 7 键全 | 基准 |
| 工程内的一个最小独立页面（179 B） | 7 键全 | **与基准逐字节相同** |
| 平台自带的一个工具片段（200 B，`dev/ide/` 下） | **缺 `inframe` / `pageLink`** | 顶层少 2 把钥匙，**`check` 仍报 ALL OK** |

结论：**种子的内容相似度与产出无关** —— 种子唯一实质贡献是**顶层键序**（以及换行符）；
未 `set` 的键会**静默继承**（种子的 `roles:{"demo":1}` 会带进新页面）。

**`patch` 的 diff 规模（独立复核 —— 与第五节那个 377 KB 的用例不是同一个文件）**：
181 635 B 的多行源页面追加一个 `button` 节点 → diff **15 行**（含 2 行为 `\u201c`→`“` 的语义等价规整）。
