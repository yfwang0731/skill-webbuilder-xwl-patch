# 实测数据与统计口径

> **样本**：本项目 `wb/` 下 **2777 个 `.xwl`**（`target/` 下的部署副本不计入）。
> **方式**：用 `scripts/xwl.py` 的解析器遍历 JSON 树统计；**已剔除 JS 注释**（注掉的 `out:` / `params:` 不计）。
> **日期**：2026-09-15。
> **定位**：数字分两类 ——
> ① **项目用法统计**（一~四、六节）：说明「**这个项目实际上怎么写**」，用于判断改动是否跟着现状走，
> **不是规范**，换项目要重新统计；
> ② **工具回放校验**（第五节）：说明「**脚本的复刻准不准**」，与某个项目的编码习惯无关。

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

本项目**没有**用 `proxy.extraParams` / `setExtraParams` / `Wb.getValues`（各 0 处）—— 别照搬别的项目习惯。

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
| `action` | **101** | **错位一位**（`action` 实际是 form），见 SKILL.md §5.5 |
| `form` | 32 | 顺序正确 |
| （无参） | 5 | 不需要返回值 |
| `resp` | 1 | 命名不规范 |


## 五、设计器写回算法的复刻一致性（回放校验）

**这不是某一次编辑的结果**，而是一次**批量回放校验**：把复刻出的算法
（`IDE.updateModule` 四步）**整体跑在本项目既有的全部 xwl 上**，
逐个比对「还原出的字节」与「文件原有字节」—— 检验的是**算法复刻得准不准**。

| 项 | 结果 |
|---|---|
| 多行源 | 1875 个中 **1830 个逐字节一致 = 97.6%** |
| 不一致的 45 个 | 都有明确外因：手工改过缩进（4 空格 + 行尾空格）、或另一种写法把 `\u201c` 转义 |
| 单行源（紧凑一行） | **902 个** —— 需要时可 `xwl.py expand` 转多行 |
| 解析失败 | 3 个：`modules/dev/template/{basic-dialog-edit,gridCrud,multiform_mainDetail}.xwl`（模板样本，不是纯 JSON） |

→ 结论：**算法复刻正确**，因此 `patch` 重排**不会顺带改动无关内容**，
diff 只含真正改的内容（实测：377 KB 的 `transTrack.xwl` 加一个带多行 JS 的按钮 + 改标题，diff **17 行**）。

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
| warn | 1856 | 未被事件 JS 引用 —— 老代码可留，新代码须区分 |
| error | 519 | **已被事件 JS 引用 —— `app.<名字>` 取值不确定** |

`error` 组按控件类型：`text` 202 / `combo` 178 / `toolbar` 46 / `item` 34 / `grid` 30 / `date` 24 /
`column` 23 / `number` 22 / `textarea` 19 / `datetime` 8。
`warn` 组 Top：`array` 364 / `item` 356 / `text` 277 / `combo` 257 / `store` 252 / `number` 152 / `feature` 144 / `toolbar` 121。

**关键结论：列控件的 3393 组重名里，被事件 JS 引用的有 0 组。**
印证了"列控件不直接取、取数走 `app.<grid>.getSelection(0).data.XXX`"这一用法。

### 7.3 列的命名约定

全项目 **20771 个** `column` / `tcolumn` 节点的 `itemId` 中，**14213 个（68.4%）**带
`_COL` / `Col` 后缀（如 `ORDER_NO_COL`、`ITEM_NAMECol`），其余 6558 个不带。

### 7.4 `itemId` 的字符集

绝大多数是合法 JS 标识符，但**并非全部**：全项目有 **57 个**节点的 `itemId` 含非 `[A-Za-z0-9_]` 字符 ——
中文（如 `query` 节点上写 `"检查是否存在重复记录"`）、空格、`.`、`(`、`)`、`-`、`+` 都出现过。
这类名字**不能用 `app.X` 点号访问**，只能用 `app.get('名字')`；`itemids` 因此把它们的重名判为无害。

**`#` 从未出现在任何 `itemId` 里** —— 所以 `@名字#N` 用 `#` 作序号分隔符不会与既有名字冲突。

### 7.5 框架侧机制（源码原文）

`wb/libs/ext/ext-all-debug.js:21689`（WebBuilder 改过的 `Ext.ComponentManager`）：

```js
register: function (item) {
    this.all.add(item);
    if (item.appScope && (item.normalName || item.itemId))
        item.appScope[item.normalName || item.itemId] = item;      // 普通赋值 ⇒ 后者覆盖前者
},
unregister: function (item) {
    var all = this.all;
    all.removeAtKey(all.getKey(item));
    if (item.appScope && (item.normalName || item.itemId))
        delete item.appScope[item.normalName || item.itemId];      // 按同名键 delete ⇒ 会误删别人
},
```

注册键 = **`normalName || itemId`**（normalName 优先）。
`unregister` 的 `delete` 是"重复会取不到值"的**确切机制**：任一重复项被销毁，
整个名字就从页面作用域消失，哪怕另一个同名控件还活着。
（另见 `ext-all-debug.js:453` 起：`appScope` 在 `Ext.clone` / `Ext.merge` 里被**特意保留引用、不深拷贝**。）
