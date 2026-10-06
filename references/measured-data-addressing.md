> 发布面：随 skill 发布 ｜ 层归属：依据层

# 实测数据 · itemId 与 normalName（重名分级的数据依据）

> 本文件由主文件 [`measured-data.md`](measured-data.md) 拆出（承载原「七」，节号不变）；索引见主文件。

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

### 7.2 重名组的实际分布（按注册键 `normalName || itemId` 分组，按是否被 JS 引用分级）

**分级只两级** —— 被事件 JS 引用 → `error`；未被引用 → `benign`（`warn` 级已取消）：

| 分级 | 组数 | 说明 |
|---|---:|---|
| error | 456 | **已被事件 JS 引用 —— `app.<名字>` 取值不确定** |
| benign | 5312 | **未被引用 —— 实践中无害**：列控件 3393 + 其余未被引用 1919（原 `warn` 并入） |

> 旧口径下「同名节点各有唯一 `normalName`」的 **150 组**被算作 benign 豁免；新口径按**注册键**分组，
> 它们的注册键互不相同 ⇒ **本就不成组**，自然从统计里消失（不再单独计一档）。

`error` 组**内的控件**按类型（单位＝**控件节点数**）：`text` 184 / `combo` 163 / `toolbar` 46 /
`grid` 30 / `item` 28 / `number` 22 / `column` 14 / `textarea` 10 / `panel` 6 / `date` 6 …
`benign` 组 **Top**（同单位）：`array` 364 / `item` 362 / `text` 295 / `combo` 272 / `store` 252 /
`number` 152 / `feature` 144 / `toolbar` 121。

> **这两行不能跟上面的组数直接相加** —— 组数是「有多少个重名组」，拆分是「组里有多少个控件节点」，
> **两套单位**。所以拆分项之和会大于组数（`error` 拆到 `date` 已累计 473 > 456），这不是矛盾。
> 表格里的 `error` / `benign` 一律是**组数**。

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
这类名字**不能用 `app.X` 点号访问**，只能用 `app.get('名字')` **或** `app['名字']`；`itemids` 因此把它们的重名判为无害。

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

为什么会"取不到值"的机制见本文 §7.5（上面源码）；规则本身（谁优先、`normalName` 为什么优先）见 `SKILL.md` §7.1。

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

