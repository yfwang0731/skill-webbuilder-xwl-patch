# 实测数据与统计口径

> **样本**：样本工程 `wb/` 下 **2780 个 `.xwl`**（其中 **2777 个可解析** —— 3 个模板样本不是纯 JSON；
> `target/` 下的部署副本不计入）。引用「2777」的地方都是指可解析的那部分。
> **方式**：用 `scripts/xwl.py` 的解析器遍历 JSON 树统计；**已剔除 JS 注释**（注掉的 `out:` / `params:` 不计）。
> ⚠️ **比例不可外推**：本文是**单工程**样本。换到 8 个 wb 根 / 24957 个 xwl 的全量复算，
> 同一指标会显著不同（实测：url 未命中率在四个工程间是 **5.8%–19.6%**，差 3.4 倍）
> ⇒ **给用户看比例时必须标明样本**（本工程 vs 全量）。
> **日期**：2026-09-15。
> **定位**：数字分三类 ——
> ① **项目用法统计**（一~四、六~九节）：说明「**这个项目实际上怎么写**」，用于判断改动是否跟着现状走，
> **不是规范**，换项目要重新统计；
> ② **工具回放校验**（第五节）：说明「**脚本的复刻准不准**」，与某个项目的编码习惯无关；
> ③ **`new` / `folders` 的形态依据**（第九节）：顶层键序与 `folder.json` 的实测分布。

---

## 目录

- [一、xwl 引用方式的使用次数](#一xwl-引用方式的使用次数)
- [二、页面传参两条通路的分布](#二页面传参两条通路的分布)
- [三、`Wb.requestAg` 的参数名频次](#三wbrequestag-的参数名频次)
- [四、`Wb.requestAg` 成功回调里做什么](#四wbrequestag-成功回调里做什么)
- [五、设计器写回算法的复刻一致性](#五设计器写回算法的复刻一致性)
- [六、控件使用频次与父子结构](#六控件使用频次与父子结构)
- [七、itemId 与 normalName](#七itemid-与-normalname)
- [八、SQL 片段与 serverScript 的分布](#八sql-片段与-serverscript-的分布)
- [九、页面顶层骨架与 folder.json](#九页面顶层骨架与-folderjson)
- [十、规模与耗时](#十规模与耗时)
- [十一、判据修正的对照数](#十一判据修正的对照数)

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
| `action` | **101** | **错位一位**（`action` 实际是 form），见 [`js-api.md`](js-api.md) §3 |
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
| 单行源（紧凑一行） | **902 个** —— 需要时可 `xwl.py expand` 转多行。注意这类源**一个换行符都没有**，`--eol auto` 无从沿用 ⇒ 回退 LF；工作区惯例是 CRLF 时须显式 `--eol crlf`。⚠️ 上表口径是**检出形态**（**Windows 检出形态**示例），**与仓库存储形态可能不同**、跨平台会变 |
| 解析失败 | 3 个：`modules/dev/template/{basic-dialog-edit,gridCrud,multiform_mainDetail}.xwl`（模板样本，不是纯 JSON） |

→ 结论：**算法复刻正确**，因此 `patch` 重排**不会顺带改动无关内容**，
diff 只含真正改的内容（实测：377 KB 的一个多行源页面加一个带多行 JS 的按钮 + 改标题，diff **17 行**）。

> 反过来，**源文件不是设计器原样**时，`patch` 会**顺带规整**整份格式（纯空白缩进 / `\uXXXX` 展开 /
> 数字字面量形态），这些改动一律**语义等价**（见下表的 3 类计数）。噪声大就改用 `edit` 做定点插入。
>
> 动手前先估噪声量：**先 `--dry-run` 数一下噪声行数再决定** —— 把 `--dry-run` 的输出**重定向到文件**，
> 数其中以 `  +` / `  -` 开头的行即可。噪声只有一两行就照用 `patch`（省心、格式有保证，
> 且还原后的形态反而与设计器产物一致）；噪声可观就改用 `edit` 做定点插入（语义相同，diff 只含你改的那一处）。

⚠️ 但**"diff 只含本次改动"只对"设计器原样排版"的文件成立**。全量复算（8 个 wb 根 / 24933 个可解析文件）：
设计器原样 **17530（70.3%）** / 单行源 **6812（27.3%）** / 多行但非原样 **591（2.4%）**
⇒ **≈ 三成文件做一次 `patch` 会产生整份或大量与本次改动无关的 diff**。
591 个"多行非原样"的实际改写内容是：`\uXXXX` 转义被展开 **279** / 纯空白缩进（多为 Tab→空格）**168** /
数字字面量形态 **117** / 其他（同属缩进）**27** —— 三类语义都安全，但**别把 diff 当"本次改动"的证据**。

### 5.1 写回算法的四个步骤（反编译原文）

关键位置：

| 项 | 位置 |
|---|---|
| jar | `WEB-INF/lib/Webplatform-1.0.jar` |
| 入口 | `com.wb.interact.IDE#saveFile(...)` —— 按扩展名分派，`.xwl` 交给 `updateModule` |
| 真正写文件 | `com.wb.interact.IDE#updateModule(File, JSONObject, String[], boolean)` |

`javap -c -p com.wb.interact.IDE` 可见的四步：

```java
String s = json.toString(1);                                        // ① org.json 序列化，缩进因子 1
s = s.replaceAll("\\n", "\\\n");                                    // ② 字符串内的 \n 转义 → 反斜杠 + 换行
s = s.replaceAll(System.getProperty("line.separator", "\n"), "\n"); // ③ 换行归一
FileUtil.syncSave(file, s, "utf-8");                                // ④ UTF-8 落盘，不加尾换行
```

### 5.2 `org.json toString(1)` 的三条排版规则

**① 不是标准 JSON 美化，是老版 org.json 的 `toString(1)`**，有三条反直觉规则：

1. 每级缩进 **1 个空格**（不是 2/4）。
2. **只有 0 或 1 个元素的容器不换行** → `{"itemId": "x"}`、`[3]` 内联在一行。
3. 单元素容器递归时传的是**当前缩进**而非加一层的缩进 —— 直接产生 `[{`、`}]` 的紧凑写法。

字符串转义另有两条：**非 ASCII 原样保留**（中文不转 `\uXXXX`），但 **`</` 写成 `<\/`**（防 `</script>`）。

> ② 的正则是「**字面反斜杠 + n**」，所以值里本来就有这种序列时（SQL / JS 源码里写的 `\n`，
> 在 JSON 里是 `\\n`），磁盘上会呈现成「`\\` + 反斜杠 + 换行」的别扭形态 ——
> **语义无损**，加载器的正则 `\\(?:\r\n|\r|\n)` 恰好只吃「一个反斜杠 + 换行」。
>
> ⇒ 两个序列化模式（默认忠实 / `--safe`）都语义无损、差异只在字节形态；选哪个
> **按"给谁看"决定**（要提交用默认，人读用 `--safe`），不按"哪个好看"。

## 六、控件使用频次与父子结构

**哪个控件用得多 / 控件通常挂在什么下面** 这类数字，列在 `controls.md` 的总表与第四节里
（「用过的次数」列、实测父子结构 Top 45、典型骨架）—— 那是**规范文档该有的形态**，
本文件不重复列一遍（同一个数字两处维护必然漂移）。
本文件对这类数字只负责**统计口径**（见文首「定位」段与 §九）。

## 七、itemId 与 normalName（重名分级的数据依据）

口径：全项目 **2780 个 xwl**（其中 **2777 个可解析**，3 个失败见第五节）、
**59791 个含 `itemId` 的控件节点**、**599 个文件带事件 JS（共 12304 段事件）**。

### 7.1 `normalName` 的合法性（权威来源 = 控件注册表）

> ⚠️ **两条实测事实**（决定"注册表怎么用"）：
> ① **注册表版本会漂移** —— 8 个 wb 根的注册表推导出 **86 / 88 / 89 / 90** 四种集合
> （老工程缺 `month` / `colorfield` / `echart`，新工程多 `dateMonth` / `datetimedetail`），
> **同一工程内两个 webapp 也会不同**（实测有工程是 86 与 89）⇒ 判据必须"**注册表推导 ∪ 内置兜底**"，
> 否则会出现"**能找到注册表反而更不准**"。另：工程里可能另有一份 `controlsold.json`，
> **它不是注册表**，别拿它当权威。
> ② **同名副本 ≠ 同一逻辑文件** —— 全量里同名相对路径 **4379 组**：同工程内 84 组中
> **38 组（45.2%）内容不同**（如桌面端与网站端各一套）；跨工程 2921 组内容一致（同源复制件）。
> ⇒ **不要拿另一份副本的检查结论推断本根**。

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
  这个概念。**不是所有控件都接受 `normalName`** —— 给这些类型写它是**非法配置**
  （`itemids --fix normalName` 会跳过并回报）。

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

> **取值控件是靠"鸭子类型"认的，不是靠类型清单**：框架打包送出时判的是
> `item.getValue && …`（该控件实例有没有 `getValue` 方法），**根本不看类型名**。
> 工具的 `field_types` 只能做**类型级近似**（静态拿不到实例）——
> 所以"清单取宽一点"（注册表 ∪ 内置）只会**少报**参数缺口，方向与框架语义一致。

WebBuilder 改过的 `Ext.ComponentManager`（`wb/libs/ext/ext-all-debug.js`，原文）：

```js
register: function (item) {
    this.all.add(item);
    if (item.appScope && (item.normalName || item.itemId))
        item.appScope[item.normalName || item.itemId] = item;      // 普通赋值，不检重
},
unregister: function (item) {
    var all = this.all;
    all.removeAtKey(all.getKey(item));
    if (item.appScope && (item.normalName || item.itemId))
        delete item.appScope[item.normalName || item.itemId];      // 按同名键直接删
},
```

> 行号按某个版本的 `ext-all-debug.js`（实测为 `:21689`）——
> **换版本请按符号名 `ComponentManager.register` 去搜**，别按行号找。

规则本身（谁优先、为什么会"取不到值"）见 `SKILL.md` 7.1。

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

> 查重名用 `xwl.py itemids <file>`，常用三个选项：`--dups-only`（只列重名组）、`--name NAME`（只看一个名字的全部候选）、`--suggest`（生成改名 ops 草稿，**需人工确认**）；另有 `--fix` / `--controls` / `--json`。
>
> **照抄示例**（点名单个重名项、并给它补 `normalName`；两条都取自真实工程里的用法）：
> ```json
> [{"op": "set", "path": ["@tbar#3", "configs", "normalName"], "value": "tbarGrid"}]
> [{"op": "set", "path": ["@gridUser", "@tbar", "configs", "normalName"], "value": "tbarUser"}]
> ```
> ① `["@tbar#3"]` = **点名同名里的第 3 个**（写法 `@名字#N`，N 从 1 起）；
> ② `["@gridUser", "@tbar"]` = **串联 `@` 按父子关系定位**（后一段只在上一段的子树里找）。
> 两种写法都**只改真正要改的那一个**，**不要靠猜顺序**。

> ⚠️ 一个容易误引的例子：`panelCustomRecord_ID` 看着像"`itemId` 用父级作前缀"，但它实测是
> **`normalName`**（两个同名 `text` 靠它区分）—— 属"补 `normalName`"的语境，不要当成 `itemId` 的先例。

处置顺序（重名时）：**不猜顺序**（先读祖先链判断哪个才是真目标）→ 把候选交用户选 →
**能用 normalName 就用**（不动 `itemId`、零破坏）→ 只有类型不接受时才回退到改 `itemId`，
且**必须同步改 JS 引用**、并复查 `itemids`。

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

> `folder.json` **不只是设计器索引**：框架侧（`XwlBuffer` / `FileGenProcess` / `IDE`）三处都会读它
> ⇒ "没登记"在运行期也可能取不到，`folders` 命令的价值有依据。

**顶层键序**（样本工程 `wb/` 下 2780 个 xwl）：**2750 个**的顶层键集合与顺序都是

```text
hidden, children, roles, title, iconCls, inframe, pageLink
```

**独立页面与被引用的 SQL 载体完全一样**（都是这一套）：**两类格式规则完全相同**，
区别只在"改片段时你要额外确认谁在用它"。少数派是缺 `inframe` / `pageLink` 的
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

## 十、规模与耗时（`check` / `params` / `itemids` 的量级）

> **规模类数字以本文为准**：别处（`SKILL.md` / `README.md` / `faq.md` / `test-prompts.json`）
> 引用时只许照抄这里的值 —— 抄错会被自检抓住（`selftest.py` 里有一条"规模数字必须在本文出现"的守卫）。

**样本与口径**：**8 个 wb 根**（5 个工程）的 `modules/**` 全量 `.xwl`，**排除** `target/` 下的部署副本。
共 **24957 个文件**（**主口径**：8 个 wb 根 `modules/**`，排除 `target/` 部署副本），
其中 **24933 个可解析**（另 24 条的构成见《验收基线 v2》§4）。

**最大单文件**：**746299 字节** = **728.8 KB**（按 1024 算）= **746.3 KB**（按 1000 算）。
⚠️ **同一个数、两种单位**：引用时必须写明单位，否则会像"728 KB 与 746 KB"那样被当成两个互相矛盾的数。

**耗时**（在**上面这个最大文件**上实测）：

| 命令 | 耗时 |
|---|---|
| `check --no-js` | **0.08 s** |
| `check`（全开） | **0.56 s** |
| `params` | **0.05 s** |
| `itemids` | **0.07 s** |
| `diffguard` | 约 **0.9 s/文件**（每个文件起一次 `git show`；实测 60 个文件 52 s） |

**另一个样本**（**486 KB** 多行源 / 246 事件段 —— 与上表的 728.8 KB **不是同一个文件**）的分项耗时：
`check --no-js --no-itemid` **~0.4 s**（只跑格式五项）、`check --no-js` **~0.4 s**（加上 ⑦ 重名分级）、
`check`（全开）**~1 s**（⑥ 把全部事件段一次交给 node）。引用这两组数字（728.8 KB 样本的 0.08/0.56 s、
486 KB 样本的 ~0.4/~1 s）时都要**带上样本与命令** —— 它们不是同一个文件、也不是同一条命令。

**三条边界**（引用这些数字时必须带着讲）：

1. **是"实测到的最大值"，不是"能处理的最大值"** —— 工具源码里**没有任何文件大小判断**，
   换一批工程这个数就变。所以 `SKILL.md` 写的是"样本实测值，不是硬上限"。
2. **结果随扫描面变** —— 上面口径是 8 个根的 `modules/**`、排除 `target/` 部署副本；换口径要重测。
3. **耗时是本机单次测量**（Windows + 托管 Python），换机器、换负载都会漂 ⇒ 只作量级参考。
   `check` 全开为什么慢、怎么绕开，见 [`faq.md`](faq.md)「`check` 慢，或者本机根本没装 `node`？」。

## 十一、判据修正的对照数（`H10` / `K13` / `K7` 的依据）

> 本节放「判据改过之后结论变了多少」的对照 —— 供 `CHANGELOG` 的「放松留痕」与后续复核使用。
> 每小节都写清复现方式，**口径与样本随行注明**。

### 11.1 `field_types` / `normalname_types` 取并集前后的集合对照（`H10`）

**集合层面**（8 个 wb 根各自的 `wb/system/controls.json`）：

| wb 根 | 内置兜底 | 注册表推导 | 并集 | 交集 |
|---|---|---|---|---|
| **样本根 A** | 14 | 14 | **15** | 13 |
| 其余 7 个根 | 14 | 14 | 14 | 14 |

> 「**样本根 A**」= 8 个根里唯一把 `text` 注册成 `Ext.form.field.*` 之外类型的那个
> （**不点工程名与路径** —— 这是本仓的文档纪律，见 [`workflow-notes.md`](workflow-notes.md)）。

**样本根 A** 的**注册表独有 = `datetimedetail`**、**兜底独有 = `text`** —— 纯注册表推导会把
**最高频的取值控件 `text` 整类丢掉**（该根把 `text` 注册成 `Ext.form.field.*` 之外的类型），
容器内 text 控件的 `itemId` 全部从 `provided` 消失。
⇒ 其余 7 个根「并集 ≡ 注册表推导」（它们的注册表没丢类型）⇒ **这一改只在一类工程上有影响，无副作用**。

**页面层面**（样本根 A，**3128 页里 703 页有需求**；monkeypatch 旧实现跑两遍）：

| 量 | 注册表-only（改前） | 并集（改后） |
|---|---|---|
| miss 合计 | 2970 | **1913**（差 **1057 条假阳**） |
| provided 或 miss 不同的页面 | — | **402 页（57.2%）** |

### 11.2 `diffguard` 加前置必要条件前后的对照（`K13`）

**复现**：在受 git 管理的工程里跑 `xwl.py diffguard <file> --rev <历史 rev>`。

样本 = 某个改过多行 JS 的页面（`wb/modules/…/…xwl`）；
**rev 用 `git log -- <file>` 自取**（挑一个改过多行 JS 的历史提交）：

| | 续行符 | 最长行 | 行数 | 输出 |
|---|---|---|---|---|
| 改前 | 400 → 400 | 146 → 146 | 4470 → 4470 | `[warn] 疑似把多行内容压平（精确命中）` —— **三个计数一个都没变** ⇒ 数学上排除压平 |
| 改后 | 同上 | 同上 | 同上 | rc=0、**0 条精确命中**；`[note] 另有 5 处「内容与基线相邻几行的拼接相同」，但续行符与行数都没减少 ⇒ 判为内容移动 / 复制，不是压平` |

⇒ **修法只降级、不新增告警**：`}` / `';'` 这类**极短行**的拼接是天然的内容匹配误报源，
而 `--strict` 会把这类误报变成 CI 红灯 ⇒ 「续行符数或行数减少」这个前置必要条件是必须的。

### 11.3 `url:` 三类形态的计数（`K7`）

**口径**：8 个 wb 根 / **24986 个 xwl** 的**全文正则**扫描（与 §十 的 `modules/**` 计数**不是同一口径**，两者不矛盾、也不可混引）（`url\s*:\s*'…'` / `"…"` / 标识符开头），
**未按 JSON 树**、**未剔 JS 注释**。

| 形态 | 次数 | 工具是否纳入核对 |
|---|---|---|
| 字面量**含** `m?xwl=` | 29727 | ✅ 已覆盖 |
| 字面量**不含** `m?xwl=`（捷径等） | **355** | ❌ 不核对（只提示） |
| 变量 / 表达式（`url: urlStr` / `app.url.getValue()`） | 889 | ❌ 静态不可能解析 |
| 合计 | 30971 | — |

⚠️ **与《落地清单》K7 行的 29738 / 355 / 447 有差**（第 1 类 −11、第 3 类 +442）：本轮是**全文正则**，
会把字符串与注释里长得像 `url:` 的文本一并计入；那组是**按 JSON 树**统计。两种口径各自自洽，
但**不可混引** ⇒ 后续的汇总行以**工具内部（按 JSON 树）**统计为准；
本节只支撑一个结论：**非 `m?xwl` 的字面量 url 有量级（数百处），不是理论上才可能出现**。
