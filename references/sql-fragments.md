# SQL 片段：结构、字段与传参

> **什么算「SQL 片段」**：被别的 xwl 用 `store.configs.url = 'm?xwl=…'` 引用的 `.xwl`
> （典型路径 `…/transSql/queryXxx.xwl`）。它的**文件结构与普通页面完全一样**，
> 只是内容固定在 `module` + `dataprovider` 这两层。
>
> **本文是 [`SKILL.md`](../SKILL.md) 第六章的展开** —— 编辑方式（`patch` / `@itemId` / 校验）见那边第三章。
> **读者**：改 SQL 片段、或改「参数控件 → store → SQL」链路时查。

---

## 一、两级结构

被 store 引用的「SQL 文件」**不是散装 SQL**，而是固定两级：

```text
(页面钥匙: title / iconCls / inframe / pageLink / hidden / roles / children)
└─ type="module"          configs{ itemId, serverScript }        ← 取参数、拼条件
   └─ type="dataprovider" configs{ itemId, sql, totalSql?, … }   ← 执行 SQL、出数据
```

**分布**（本项目 `wb/` 下实测）：**1165 个文件带 `serverScript`、1142 个带 `dataprovider`、
687 个两者都有**；另有 **478 个只有 `serverScript`** —— 这些自己用 `app.run` / `app.send`
直接出数据，不靠 `dataprovider`。

## 二、两个字段的格式（权威来源：控件注册表）

查 `wb/system/controls.json`：

- **`module.serverScript`** —— 类型 **`ss`**（服务端 JS）。同层还有 `initHtml` / `finalHtml` /
  `jsLinks` / `cssLinks` / `importModules` / `method`（枚举 GET/POST/PUT/DELETE）/ `logMessage`。
- **`dataprovider`** 共 **22 个**合法 configs，关键的几个：
  `sql`（类型 `sql`）、`totalSql`（同为 `sql`）、`itemId`、`jndi`（数据源）、
  `type`（枚举 `array`/`object`/`tree`/`download`/`stream`/`image`）、`autoPage`、
  `limitRecords` / `limitExportRecords`、`fields` / `fieldsTag`、`keyDefines`、
  `loadParams` / `totalLoadParams`（`auto`/`load`/`none`）、`createColumns`、`dictFieldsMap`。
  **events 为 0 个**（dataprovider 挂不了事件）。

```bash
python scripts/xwl.py schema dataprovider --controls <工程>/wb/system/controls.json
python scripts/xwl.py schema module       --controls <工程>/wb/system/controls.json
```

## 三、引用机制（核心）

### 3.1 方向一：`dataprovider.sql` 用 `{#名字#}` 引用 `serverScript` 注入的值

```js
// module.configs.serverScript
var data = app.get();                      // 取查询参数
var sql = "";
if (!Wb.isEmpty(data.FILE_KIND_ID)) {
  if (data.FILE_KIND_ID == '1') sql += " AND FILE_KIND_ID IN ('QSD','GBD','SJD') ";
  else                          sql += " and ows.WORK_TYPE={?FILE_KIND_ID?} ";
}
request.setAttribute('sql', sql);          // ← 注意：名字就叫 sql
```

```sql
-- dataprovider.configs.sql
select ofi.* from order_file ofi
left join order_work_state ows on ofi.WORK_ID = ows.ID
where toc.ID = {?ID?}          -- ← 绑定参数
{#sql#}                        -- ← 引用 serverScript 注入的 sql
```

实测交集（`{#x#}` 与 `setAttribute('x',…)` **同名**）：
**`sql` / `sql1` / `sql2` / `whereSql` / `joinsql` / `date` / `username`**；
最常见是 `{#sql#}`（715 次）。

### 3.2 三种占位符，来源不同（别混）

| 形态 | 来源 | 实测例（出现次数） |
|---|---|---|
| `{#sys.*#}` / `{#Str.*#}` | **框架内置**（会话 / 权限 / 资源串），**不用自己提供** | `sys.username`(492)、`sys.tenancyId`(278)、`sys.id`(202)、`sys.deptPermSql`(76)、`sys.deptId`(27)、`Str.home`(26) |
| `{#任意名#}` | **同文件 `module` 的 serverScript** 用 `request.setAttribute('名字', …)` 提供 | `sql`(715)、`sql1`(55)、`whereSql`(19) |
| `{?名字?}` | **绑定参数**（不是文本替换） | `ID`(451)、`name`(247)、`query`(208)、`month`(132) |

> `{?…?}` 由 `com.wb.tool.Query` 解析成 `PreparedStatement` 参数（常量可见 `"{?"`、`"?}"`），
> **所以不要在 SQL 里手工拼值**（也就不用操心转义 / 注入）。

### 3.3 方向二：store 用 `url` 指向 SQL 文件（页面 → 片段）

```json
// 页面里的 store 节点
{"type": "store",
 "configs": {"itemId": "store",
             "url": "m?xwl=orderCenter/highwayTransportationManagement/transSql/queryDriverFile"}}
```

→ 文件是 `…/transSql/queryDriverFile.xwl`（**补 `.xwl`**）。
本项目实测 **2000 个被引用路径、5000+ 处引用**。

## 四、两条硬规则（有源码依据）

1. **serverScript 里禁止写 `{#…#}`**。`com.wb.controls.ServerScript` 里有明确报错：
   > `ServerScript does not support {#param#} feature, please use app.get(param) instead.`

   在 serverScript 内部取参数要用 **`app.get('名字')`** 或 `request.getParameter("名字")`。
2. **`{?...?}` 是绑定参数**，别拼字符串（见 3.2）。

**执行器（都在 `WEB-INF/lib/Webplatform-1.0.jar`）**：

| 类 | 作用 |
|---|---|
| `com.wb.controls.ServerScript` | 页面解析时执行 `serverScript`（`create()` / `static getScript(JSONObject,String)`） |
| `com.wb.tool.DataProvider` | 执行 SQL 并产出 store JSON（`getScript` / `output` / `getArray` / `getObject`；常量可见 `{"success":true`、`],"total":`、`],"rows":[`） |
| `com.wb.tool.Query` | SQL 执行 + `{?…?}` 参数绑定 |
| `com.wb.util.WebUtil#replaceParams(req, s)` | `{#…#}` 替换实现 |

**serverScript 的常用 API**（全项目词频）：
`Wb.isEmpty`(4750) · `app.get`(1328) · `request.setAttribute`(1052) · `app.run`(394) · `app.send`(247) ·
`Wb.decode`(191) · `Wb.each`(178) · `Wb.encode`(134) · `request.getParameter`(127) · `SysUtil.getId`(104) · `app.log`(88) · `app.update`(80)

## 五、页面怎么把值送进来：两条通路（**推荐 `out`**）

页面把参数送到 SQL 侧，只有两条通路。**都有效**；**新写查询推荐 `out`** ——
它把「哪些控件参与」交给容器，增删条件控件**不用改 JS**。

### 5.1 通路① `out`（推荐）：整包收容器内的控件值

```js
// 查询按钮
app.grid1.store.load({ out: app.tbar });
// 弹窗保存 / 任意请求
Wb.request({ url: 'm?xwl=orderCenter/…/transSql/saveOrder', out: app.editWin, success: … });
```

**收集规则**（= `Wb.getValue(容器)`，源码实测）：

- 在容器上 `queryBy(query)` —— **递归整个子树**，不是只看直接子节点；
- 收录条件：`item.getItemId() && item.getValue` —— 即**有 `itemId` 且实现 `getValue()`**，
  参数名就用 `itemId`；
- 所以**只要控件挂在那个容器里就会被带上**，JS 里不用列名字；
- 反过来，**控件移出容器 / 改 `itemId` / 换成没有 `getValue()` 的类型**（button、label、toolbar、
  panel、grid…）都会**静默不再送** —— 这是 `out` 唯一的风险面。

几个不显眼但会踩的细节：

| 行为 | 说明 |
|---|---|
| 额外送 **`%<itemId>`** | 有 `getTextValue()` 的（`combo` 等）会多送显示值 `rawValue`，键名带 `%` 前缀 |
| 额外送 **`$<itemId>`** | 文件控件送「是否标记删除」（0/1），键名带 `$` 前缀 |
| 值为 `null` | 变成空串 `''`；`number` 类型变成 `"0"` |
| **重名 `itemId`** | **只取第一个**，后面的重名控件被忽略 |
| **不看 `hidden` / `disabled`** | 隐藏 / 禁用的控件**照样送**（可以借它传「常量参数」） |
| 取值控件类型 | 权威名单见 `wb/system/controls.json`：`general.type` 以 `Ext.form.field.` 开头的 **14 个** —— `check` `combo` `date` `datetime` `displayfield` `file` `hidden` `htmleditor` `number` `picker` `radio` `text` `textarea` `time` |

**在哪生效**（都来自源码，不是推测）：

| 位置 | 文件 |
|---|---|
| `Ext.data.Store.load`、`Ext.data.TreeStore.load` | `wb/libs/ext/ext-all-debug.js`（WebBuilder 改过的 ExtJS） |
| `Wb.request` / `Wb.requestAg` / `Wb.upload` | `wb/script/wb.js`（`Wb.getValue(options.out)`） |

容器用什么：查询条惯用 `toolbar`（典型 `app.tbar`）；表单 / 弹窗用 `form` / `window` / `container`。
实测本项目 `out` 最常指向 `app.tbar`（160 处）、其次 `app.manageTopTbar` / `app.editWin`。

### 5.2 通路② `params`：显式传「参数名 → 值」

```js
app.grid1.store.load({ params: { cId: rec.data.MR_ID } });     // 值不来自控件（当前行 / 上级变量）
app.grid1.store.load({ params: Wb.getValue(app.tbar) });       // 效果等同 out，只是写得更啰嗦
Wb.requestAg({ params: { bean: 'xxxController', method: 'del', aboutUsNo: … } });
```

适用场景：**值不来自控件**、只需少数几个参数、或参数名要和控件名**不一致**时。

> `params: Wb.getValue(app.tbar)` 与 `out: app.tbar` **运行时等价**（本项目只有 4 处这种写法）。

### 5.3 两条通路同名时谁赢 —— **两个 API 方向相反**（最容易踩）

| 调用 | 源码顺序 | 谁赢 |
|---|---|---|
| `store.load({ out, params })` | `options.params = Wb.apply(Wb.getValue(options.out), options.params)` | **`params` 覆盖 `out`** |
| 再叠加 store 自身配置 | `operation.params = Ext.apply({}, operation.params, me.params)` | **store 配置里的 `params` 最强** |
| `Wb.request` / `requestAg` | `Ext.apply({}, options.params, Wb.getValue(options.out))` | **`out` 覆盖 `params`** |

> 别在两个通路里给**同名参数**写不同值 —— 谁生效取决于走的是 `store.load` 还是 `Wb.request`。

### 5.4 命名契约：**参数名 = 控件的 `itemId`**

实测同一条链路上三处**完全同名**：

| 环节 | 名字 |
|---|---|
| `tbar` 内控件的 `itemId` | `aboutUsTyp` · `startTim` · `endTim` · `status` |
| `serverScript` 读取 | `data.aboutUsTyp` · `data.startTim` · `data.endTim` · `data.status` |
| SQL 绑定参数 | `{?aboutUsTyp?}` · `{?startTim?}` · `{?endTim?}` · `{?status?}` |

> **名字对不上不会报错** —— 只会取到 null，SQL 条件**静默失效**。所以改这类页面必须核对名字。

### 5.5 完整链路（真实业务页 `AgWeb/AgWebAboutUs/aboutUs.xwl`）

```text
查询控件 tbar 内： combo aboutUsTyp / date startTim / date endTim / combo status
      ↑ 被 out: 收值
查询按钮 click →  app.grid1.store.load({ out: app.tbar })
      ↓
grid1.store   configs.url = 'm?xwl=agWeb/agWebAboutUs/aboutusdata/selectAboutUs'
      ↓ HTTP（参数 = 容器内控件的值）
selectAboutUs.xwl
      ├─ module.serverScript :  var data = app.get();  →  data.aboutUsTyp / data.startTim / …
      └─ dataprovider.sql    :  … and aboutus_typ = {?aboutUsTyp?} …   ← 绑定参数
```

### 5.6 存量代码怎么写（结论）

- **存量以显式 `params` 为主**（历史习惯，改动跟着现状走）；**新写查询用 `out`** ——
  条件控件增减不用动 JS。`out` 主要指向**查询条**（`app.tbar`）与**编辑弹窗**（`app.editWin`）。
- 本项目**没有**用 `proxy.extraParams` / `setExtraParams` / `Wb.getValues`（各 0 处）——
  别照搬别的项目习惯。
- 完整分布（按 API × 通路、`out` 容器 Top、页面维度）见 [`measured-data.md`](measured-data.md)。

### 5.7 参数从哪读（源码依据）

`wb/system/server.js` 里 `app.get` 的 JSDoc 原文：

> `@return {Object} 请求对象的 parameter 和 attribute 中的值组成的对象。`

- `app.get()` → 全部；`app.get('x')` → `WebUtil.fetchObject(request,'x')`；
  `app.get('x', true)` → 字符串形式。另有 `app.getBool` / `getInt` / `getFloat` / `getDate` / `getJavaDate`。
- **`{#名字#}` 与 `app.get('名字')` 走的是同一个 `WebUtil.fetch(request, 名字)`**
  （反编译 `WebUtil.replaceParams` 可见）→ 两者看到的参数完全一致。
- `{#sys.*#}` 走 `Var.getString('sys.x')`，来源是 **`wb/system/var.json`**
  （内置变量注册表，`sys` 下 20 个：`app`/`session`/`jndi`/`db`/`task`/`portal`/`service`/`locale`/
  `ide`/`cache`/`debug`/`log`/`home`/`homeMobile`/`controls`/`printError`/`sendStreamGzip`/
  `sendGzipMinSize`/`serverId`/`serverConsolePrint`）。

## 六、配套检查工具

```bash
python scripts/xwl.py paths   <file.xwl>                  # 列出 sql / totalSql / serverScript / url 的位置
python scripts/xwl.py sqlrefs <file.xwl>                  # {#名字#} 与 serverScript 是否自洽
python scripts/xwl.py params  <page.xwl> [--controls …]   # 页面 → store → SQL 的传参链路交叉核对
```

- **`paths`** —— 同时给出「原路径」与「`@写法`」，改 SQL 前先跑它拿路径。
- **`sqlrefs`** —— 检查三件事：每个 `{#名字#}` 是否有 serverScript 提供（`sys.*` / `Str.*` 视为内置）、
  **serverScript 里是否误用了 `{#…#}`**、顺带列出所有 `{?参数?}` 名字。

  > 实测全项目：**1620 个含 serverScript/dataprovider 的文件中，1606 个引用自洽（99.1%）**；
  > 14 个 `{#sql#}` 本文件未提供（多为「由调用方传入」的场景）、1 处 serverScript 误用 `{#…#}`。
  > 这类告警要**结合调用方判断**，不要一律当成错误。

- **`params`** —— 自动做四件事：
  1. 列出页面里的 store 及其指向的 SQL 文件（解析 `m?xwl=`，补 `.xwl`，报文件是否存在），
     并标出 store **自身配置的 `params`**（优先级最高那个）；
  2. 列出所有传参点并**标出通路**：`[out 推荐]` / `[params·等价out]` / `[params·显式键]`；
     `out` 会**展开容器内的取值控件 `itemId`**（哪些名字会被送出去）；
  3. 读 SQL 侧需要的名字（`{?名?}` + `app.get('名')`）做**交叉核对**：
     报「SQL 需要但页面未发现来源」与「页面送了但 SQL 用不到」；
  4. `--controls` 给了就用注册表推导取值控件类型（不给则用内置的同一份 14 个兜底）。

  实测 `aboutUs.xwl`：

  ```text
  === 传参点（N 处）: out X 处 / params Y 处 ===
    [out 推荐]        app.tbar → 容器内取值控件 ['aboutUsTyp','ecPublicAboutUsData','endTim','startTim','status']
  === 交叉核对 ===
    页面送出 6 个: ['aboutUsNo','aboutUsTyp','ecPublicAboutUsData','endTim','startTim','status']
    SQL 需要 4 个: ['aboutUsTyp','endTim','startTim','status']
    [ok]   SQL 需要的参数在页面侧都能找到来源
    [info] 页面送了但 SQL 未用到: ['aboutUsNo','ecPublicAboutUsData']
  ```

  **这类告警要结合上下文判断**（可能来自上级容器 / 其它请求 / store 的固定 `params` / 框架上下文）。
