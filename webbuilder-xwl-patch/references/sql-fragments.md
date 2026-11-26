# SQL 片段：结构、字段与传参

> **什么算「SQL 片段」**：被别的 xwl 用 `store.configs.url = 'm?xwl=…'` 引用的 `.xwl`
> （典型路径 `…/xxxSql/queryXxx.xwl`）。它的**文件结构与普通页面完全一样**，
> 只是内容固定在 `module` + `dataprovider` 这两层。
>
> **本文件是 SQL 片段的完整内容**（[`SKILL.md`](../SKILL.md) 只在 §2.7 留骨架与入口）—— 编辑方式（`patch` / `@itemId` / 校验）见那边第三章。
> **什么时候看这份**：改 SQL 片段、或改「参数控件 → store → SQL」链路时。
>
> **数字与统计口径在 [`measured-data-criteria.md`](measured-data-criteria.md)**（SQL 相关口径在 §八）——
> 那只是一份样本工程的量级参考，换工程请以自己的为准。

---

## 目录

- [一、两级结构](#一两级结构)
- [二、两个字段的格式](#二两个字段的格式)
- [三、引用机制](#三引用机制核心)（3.1 方向一 / 3.2 三种占位符 / 3.3 方向二 / 3.4 url 三类写法与解析口径）
- [四、两条硬规则](#四两条硬规则)
- [五、页面怎么把值送进来](#五页面怎么把值送进来两条通路推荐-out)
- [六、分页、`totalSql` 与 SQL 投影](#六分页totalsql-与-sql-投影)
- [七、配套检查工具](#七配套检查工具)

## 一、两级结构

被 store 引用的「SQL 文件」**不是散装 SQL**，而是固定两级：

```text
(页面钥匙 7 把，键序见 SKILL.md §1.3)
└─ type="module"          configs{ itemId, serverScript }        ← 取参数、拼条件
   └─ type="dataprovider" configs{ itemId, sql, totalSql?, … }   ← 执行 SQL、出数据
```

> **新建这种文件**用 `xwl.py new <路径> --kind sql` —— 顶层键序与这两层结构都已内置。
> 改已有文件才走 `patch`（见 SKILL.md 第三章）。**不要** `cp` 别的文件当种子：种子里没被
> 显式覆盖的键（如 `roles:{"demo":1}`）会静默带进新文件。

**分布**：多数文件两者都有；也有一部分**只有 `serverScript`** —— 这些自己用 `app.run` /
`app.send` 直接出数据，不靠 `dataprovider`。（文件数见 [`measured-data-criteria.md`](measured-data-criteria.md) §八。）

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
# 先设变量：SKILL_ROOT=本 skill 安装目录（PowerShell：$env:SKILL_ROOT="…"）；<工程> 换成你的 wb 工程根
export SKILL_ROOT="$HOME/.agents/skills/webbuilder-xwl-patch"
python "$SKILL_ROOT/scripts/xwl.py" schema dataprovider --controls <工程>/wb/system/controls.json
python "$SKILL_ROOT/scripts/xwl.py" schema module       --controls <工程>/wb/system/controls.json
```

## 三、引用机制（核心）

### 3.1 方向一：`dataprovider.sql` 用 `{#名字#}` 引用 `serverScript` 注入的值

`{#x#}` 文本替换的是**片段**；`serverScript` 产条件片段（如 `whereSql`），值走 `{?orderNo?}` 绑定，dataprovider 保持单段 SELECT，别再拼入另一份完整 SELECT。

```js
// module.configs.serverScript
var data = app.get();                      // 取查询参数
var sql = "";
if (!Wb.isEmpty(data.BIZ_TYPE)) {
  if (data.BIZ_TYPE == '1') sql += " AND BIZ_KIND IN ('A','B','C') ";
  else                      sql += " and t.BIZ_CODE={?BIZ_TYPE?} ";
}
request.setAttribute('sql', sql);          // ← 注意：名字就叫 sql
```

```sql
-- dataprovider.configs.sql
select t.* from biz_table t
left join biz_state s on t.REF_ID = s.ID
where t.ID = {?ID?}            -- ← 绑定参数
{#sql#}                        -- ← 引用 serverScript 注入的 sql
```

实测交集（`{#x#}` 与 `setAttribute('x',…)` **同名**）：
**`sql` / `sql1` / `sql2` / `whereSql` / `joinsql` / `date` / `username`**，其中 `{#sql#}` 最常见
（次数见 [`measured-data-criteria.md`](measured-data-criteria.md) §八）。

### 3.2 三种占位符，来源不同（别混）

| 形态 | 来源 | 典型例 |
|---|---|---|
| `{#sys.*#}` / `{#Str.*#}` | **框架内置**（会话 / 权限 / 资源串），**不用自己提供** | `sys.username`、`sys.tenancyId`、`sys.id`、`sys.deptPermSql`、`sys.deptId`、`Str.home` |
| `{#任意名#}` | **同文件 `module` 的 serverScript** 用 `request.setAttribute('名字', …)` 提供 | `sql`、`sql1`、`whereSql` |
| `{?名字?}` | **绑定参数**（不是文本替换） | `ID`、`name`、`query`、`month` |

> 各例在样本工程里的出现次数见 [`measured-data-criteria.md`](measured-data-criteria.md) §八。

> `{?…?}` 由 `com.wb.tool.Query` 解析成 `PreparedStatement` 参数（常量可见 `"{?"`、`"?}"`），
> **所以不要在 SQL 里手工拼值**（也就不用操心转义 / 注入）。

### 3.3 方向二：store 用 `url` 指向 SQL 文件（页面 → 片段）

```json
// 页面里的 store 节点
{"type": "store",
 "configs": {"itemId": "store",
             "url": "m?xwl=<模块>/<业务目录>/xxxSql/queryBizList"}}
```

→ 文件是 `wb/modules/<模块>/<业务目录>/xxxSql/queryBizList.xwl`（**补上 `.xwl`**）。
反过来**从文件找引用方**：在工程里的 xwl 中搜 `m?xwl=<该路径去扩展名>`。
被引用的片段是**常态**（引用点数量级见 [`measured-data-criteria.md`](measured-data-criteria.md) §八）。

### 3.4 url 三类写法与解析口径

`Wb.request` / `Wb.open` / `Wb.upload` 的 `url` 可以给**完整带查询串**的形式，
但参数的规范位置是 `params`（或 `out`），不要手拼查询串。`Wb.requestAg` 是固定后台业务入口，
框架无条件把 `url` 写成 `m?xwl=common/save-all`，不要传自定义 SQL URL；它的参数只属于该入口。

**解析口径**：工具认的是 **`url:` 这个键**（不论包在 `Wb.request` / `Wb.open` / `Wb.run` /
`store.load` 里），且**只判本 wb 根** —— 跨 webapp / 跨工程的引用请在目标工程里跑；
"跨工程存在" ≠ "本工程可用"。

**按单 webapp 判定**：实测多模块工程的 `target/` 展开产物里**只含其中一个模块**的 xwl
（动态模块 jar 里没有 `wb/`）⇒ **各 webapp 是各自独立部署的**，不存在"部署时把别的 webapp
的页面合进来"这一步；但部署脚本 / 运维配置不在仓库里，**实际部署形态以运维为准**。

第二种短名（`/<短名>`，**捷径**，如 `/upload`）工具**不解析**、只提示 —— 它**不只会出现在理论上**：
全量语料里 `url:` 的写法分三类 —— **字面量含 `m?xwl=`（已覆盖）**、
**字面量不含 `m?xwl=`（捷径等）**、**变量 / 表达式（静态不可能解析）**，后两类工具都**不纳入核对**，各类占比要按你的工程现采。历史口径（具体文件数）见 `CHANGELOG.md`；采集命令：`grep -rc 'url:' <工程>/wb/modules --include='*.xwl' | wc -l` 之类，具体口径见 [`measured-data-criteria.md`](measured-data-criteria.md) 第十一节。

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

**serverScript 的常用 API**（按使用频次排序；数字见 [`measured-data-criteria.md`](measured-data-criteria.md) §八）：
`Wb.isEmpty` · `app.get` · `request.setAttribute` · `app.run` · `app.send` · `Wb.decode` ·
`Wb.each` · `Wb.encode` · `request.getParameter` · `SysUtil.getId` · `app.log` · `app.update`

## 五、页面怎么把值送进来：两条通路（**推荐 `out`**）

页面把参数送到 SQL 侧，只有两条通路。**都有效**；**新写查询推荐 `out`** ——
它把「哪些控件参与」交给容器，增删条件控件**不用改 JS**。

### 5.1 通路① `out`（推荐）：整包收容器内的控件值

```js
// 查询按钮
app.grid1.store.load({ out: app.tbar });
// 弹窗保存 / 任意请求
Wb.request({ url: 'm?xwl=<模块>/…/xxxSql/saveBiz', out: app.editWin, success: … });
```

`params` 静态核对支持已取证的 `app.<grid注册键>.store.load/reload` 形态：grid 注册键必须唯一，
其直接子节点必须恰有一个 `type=store`、`itemId=store` 的槽位，且没有未解析的显式绑定。
注册键歧义、多个 store、非槽位、别名和动态链都记“未核对”，不任选一个。

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
| `Wb.request` / `Wb.requestAg` / `Wb.upload` | `wb/script/wb.js`（`Wb.getValue(options.out)`；本 skill 别处引用的是源码版文件名 `wb-debug.js`，与它是同一文件的两种形态） |

容器用什么：查询条惯用 `toolbar`（典型 `app.tbar`）；表单 / 弹窗用 `form` / `window` / `container`。
`out` 最常指向 `app.tbar`，其次 `app.manageTopTbar` / `app.editWin`（次数见 [`measured-data.md`](measured-data.md) §二）。

### 5.2 通路② `params`：显式传「参数名 → 值」

```js
app.grid1.store.load({ params: { cId: rec.data.MR_ID } });     // 值不来自控件（当前行 / 上级变量）
app.grid1.store.load({ params: Wb.getValue(app.tbar) });       // 效果等同 out，只是写得更啰嗦
Wb.requestAg({ params: { bean: 'xxxController', method: 'del', BIZ_NO: … } });
```

适用场景：**值不来自控件**、只需少数几个参数、或参数名要和控件名**不一致**时。

> `params: Wb.getValue(app.tbar)` 与 `out: app.tbar` **运行时等价**（样本工程只有 4 处这种写法）。

### 5.3 两条通路同名时谁赢

| 调用 | 源码顺序 | 谁赢 |
|---|---|---|
| `store.load({ out, params })` | `options.params = Wb.apply(Wb.getValue(options.out), options.params)` | **`params` 覆盖 `out`** |
| 再叠加 store 自身配置 | `operation.params = Ext.apply({}, operation.params, me.params)` | **`params` 覆盖 `out`，再覆盖 store 静态 `params`** |
| `Wb.request` / `requestAg` | `Ext.apply({}, options.params, Wb.getValue(options.out))` | **`params` 覆盖 `out`** |

统一口径：`store.load` 调用为 **`params > out > store 静态 params`**；
`Wb.request` / `requestAg` 为 **显式 `params > out`**。直属 `beforeload` 在这些合并之后另行计算有效键。

### 5.4 命名契约：**参数名 = 控件的 `itemId`**

实测同一条链路上三处**完全同名**：

| 环节 | 名字 |
|---|---|
| `tbar` 内控件的 `itemId` | `BIZ_TYPE` · `START_DATE` · `END_DATE` · `STATUS` |
| `serverScript` 读取 | `data.BIZ_TYPE` · `data.START_DATE` · `data.END_DATE` · `data.STATUS` |
| SQL 绑定参数 | `{?BIZ_TYPE?}` · `{?START_DATE?}` · `{?END_DATE?}` · `{?STATUS?}` |

> **名字对不上不会报错** —— 只会取到 null，SQL 条件**静默失效**。所以改这类页面必须核对名字。

### 5.5 完整链路（示意）

```text
查询控件 tbar 内： combo BIZ_TYPE / date START_DATE / date END_DATE / combo STATUS
      ↑ 被 out: 收值
查询按钮 click →  app.grid1.store.load({ out: app.tbar })
      ↓
grid1.store   configs.url = 'm?xwl=<模块>/<业务目录>/xxxSql/queryBizList'
      ↓ HTTP（参数 = 容器内控件的值）
queryBizList.xwl
      ├─ module.serverScript :  var data = app.get();  →  data.BIZ_TYPE / data.START_DATE / …
      └─ dataprovider.sql    :  … where biz_type = {?BIZ_TYPE?} …   ← 绑定参数
```

### 5.6 存量代码怎么写（结论）

- **存量以显式 `params` 为主**（历史习惯，改动跟着现状走）；**新写查询用 `out`** ——
  条件控件增减不用动 JS。`out` 主要指向**查询条**（`app.tbar`）与**编辑弹窗**（`app.editWin`）。
- 样本工程**没有**用 `proxy.extraParams` / `setExtraParams` / `Wb.getValues`（各 0 处）——
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

## 六、分页、`totalSql` 与 SQL 投影

本节是分页、`totalSql`、手写切片与 SQL 投影的**唯一规则正本**。[`transcription-defaults.md`](transcription-defaults.md) 与 [`anti-patterns.md`](anti-patterns.md) 只保留指向本节的指针。

### 6.1 先判由谁分页

| 场景 | SQL 负责 | 页面 / store 负责 | 交付判据 |
|---|---|---|---|
| **框架接管分页** | `dataprovider` 声明 `autoPage`，SQL 返回逻辑结果集，不按本次页再加 `LIMIT` / `OFFSET` | 列表走 `store.load(...)`，分页条传 `page` / `start` / `limit` | 同一请求只切一次页；SQL 文本没有与本次页重复的切片 |
| **业务 Top N** | SQL 明确表达“最新 N 条 / 前 N 条”等业务上限 | 该入口按业务语义取数，不把业务上限伪装成用户翻页 | SQL 注释或交付说明写清 Top N 含义；不能据此复用为通用分页 |
| **自管分页** | 目标库或历史接口不支持框架分页时，SQL 自行处理 `start` / `limit` 或等价游标 | 调用方只传一次页参数，不再由框架重复切页 | 参数名、来源、返回 `total` 三者同链路核对 |
| **参考页已有 `totalSql`** | 保留参考页的总数 SQL 与过滤条件 | 保留同一场景的请求接线 | 参考页来源、SQL 条件与返回 `total` 一并核对 |

新建纯列表且没有参考 SQL 时，可以不写 `totalSql`，由框架补总数；参考页已经带 `totalSql` 时保留该逻辑。这个分场景结论来自使用者确认，本机没有执行 SQL 复现。

### 6.2 禁止二次切页

`autoPage` 接管后，**同一请求不得再次手写切页**。下列写法属于重复切页：

- SQL 已声明 `autoPage`，又在末尾按当前 `start` / `limit` 追加 `LIMIT` / `OFFSET`；
- 框架已把 `start` / `limit` 传到 SQL，再把结果集在服务端切片一次；
- 页面先取全量，再按页码手工 `splice` / `slice` 后显示。

业务 Top N 与自管分页可以在 SQL 内出现上限或切片，但它们必须与框架接管分页互斥，并在交付说明中写明场景。不要因为一条 Top N 需要 `LIMIT`，就给普通列表也复制同样的切片。

### 6.3 SQL 引用、别名与投影

核对范围固定在**当前应用模块根**。`m?xwl=` 路径相对 `wb/modules/`，不带 `.xwl`；把资源放到另一个 webapp 或另一个工程只能证明那里可用，不能证明当前应用可用。

投影核对按同一列链追到结果：

```text
SQL 物理列
  → SELECT 别名
    → store 返回 JSON 字段
      → grid column.dataIndex
        → renderer / keyName / 业务取数
```

例：

```sql
select t.BIZ_NO as BIZ_NO,
       t.STATE_NAME as STATE_NAME
  from demo_table t
 where t.STATE_CODE = {?STATUS?}
```

页面列必须用 `dataIndex: "BIZ_NO"` 与 `dataIndex: "STATE_NAME"`。只把列标题写成“状态”不建立映射；SQL 别名改了而 `dataIndex` 未改时，列可能空白或读到未定义值。

### 6.4 可复制的 Windows PowerShell 示例

在源码工作区仓库根目录依次执行下面整段 PowerShell 7 脚本。脚本只在系统临时目录创建中性页面和 SQL 载体，不写业务工程。

```powershell
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path '.').Path
$SkillRoot = Join-Path $RepoRoot 'skill/webbuilder-xwl-patch'
$Xwl = Join-Path $SkillRoot 'scripts/xwl.py'
$FixtureRoot = Join-Path $env:TEMP ('wb-xwl-copyable-' + [guid]::NewGuid().ToString('N'))
$ModuleRoot = Join-Path $FixtureRoot 'modules'
$SqlPath = Join-Path $ModuleRoot 'examples/demoSql/queryDemo.xwl'
$PagePath = Join-Path $ModuleRoot 'examples/pageDemo.xwl'
$SqlOpsPath = Join-Path $FixtureRoot 'sql-ops.json'
$PageOpsPath = Join-Path $FixtureRoot 'page-ops.json'
$StoreUrl = 'm?' + 'xwl=examples/demoSql/queryDemo'

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SqlPath) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PagePath) | Out-Null

$SqlOps = @'
[
  {
    "op": "set",
    "path": ["@module", "configs", "serverScript"],
    "value": "var data = app.get();\nvar whereSql = '';\nif (!Wb.isEmpty(data.STATUS)) {\n  whereSql = ' AND t.STATE_CODE = {?STATUS?}';\n}\nrequest.setAttribute('whereSql', whereSql);"
  },
  {
    "op": "set",
    "path": ["@dataprovider", "configs", "sql"],
    "value": "select t.BIZ_NO as BIZ_NO, t.STATE_NAME as STATE_NAME from demo_table t where 1=1 {#whereSql#}"
  },
  {
    "op": "set",
    "path": ["@dataprovider", "configs", "totalSql"],
    "value": "select count(1) as TOTAL from demo_table t where 1=1 {#whereSql#}",
    "create": true
  }
]
'@

$PageOps = @'
[
  {"op":"append","path":["children",0,"children"],"value":{"configs":{"itemId":"viewport1"},"expanded":false,"children":[],"type":"viewport"}},
  {"op":"append","path":["@viewport1","children"],"value":{"configs":{"itemId":"panel1","layout":"fit"},"expanded":false,"children":[],"type":"panel"}},
  {"op":"append","path":["@panel1","children"],"value":{"configs":{"itemId":"demoGrid"},"expanded":false,"children":[],"type":"grid"}},
  {"op":"append","path":["@demoGrid","children"],"value":{"configs":{"itemId":"store","autoLoad":"false","url":"STOREDEMO"},"expanded":false,"children":[],"type":"store"}},
  {"op":"append","path":["@demoGrid","children"],"value":{"configs":{"itemId":"tbar"},"expanded":false,"children":[],"type":"toolbar"}},
  {"op":"append","path":["@tbar","children"],"value":{"configs":{"itemId":"STATUS","fieldLabel":"Status"},"expanded":false,"children":[],"type":"text"}},
  {"op":"append","path":["@tbar","children"],"value":{"configs":{"itemId":"queryBtn","text":"Query"},"expanded":false,"children":[],"type":"button","events":{"click":"app.demoGrid.store.load({params:{STATUS:app.STATUS.getValue()}});"}}},
  {"op":"append","path":["@demoGrid","children"],"value":{"configs":{"itemId":"columns"},"expanded":false,"children":[],"type":"array"}},
  {"op":"append","path":["@columns","children"],"value":{"configs":{"itemId":"BIZ_NO","dataIndex":"BIZ_NO","text":"Biz No"},"expanded":false,"children":[],"type":"column"}},
  {"op":"append","path":["@columns","children"],"value":{"configs":{"itemId":"STATE_NAME","dataIndex":"STATE_NAME","text":"Status"},"expanded":false,"children":[],"type":"column"}}
]
'@

$PageOps = $PageOps.Replace('STOREDEMO', $StoreUrl)

[System.IO.File]::WriteAllText($SqlOpsPath, $SqlOps, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($PageOpsPath, $PageOps, [System.Text.UTF8Encoding]::new($false))

function Invoke-Xwl {
  param([string[]]$XwlArgs)
  python -B $Xwl @XwlArgs
  $code = $LASTEXITCODE
  Write-Output ("[xwl-rc] {0} = {1}" -f $XwlArgs[0], $code)
  if ($code -ne 0) { throw ("xwl {0} failed" -f $XwlArgs[0]) }
}

Invoke-Xwl @('new', $SqlPath, '--kind', 'sql', '--title', 'Demo SQL')
Invoke-Xwl @('patch', $SqlPath, '--ops', $SqlOpsPath)
Invoke-Xwl @('new', $PagePath, '--kind', 'page', '--title', 'Demo page')
Invoke-Xwl @('patch', $PagePath, '--ops', $PageOpsPath)
Invoke-Xwl @('sqlrefs', $SqlPath)
Invoke-Xwl @('params', $PagePath, '--strict', '--module-root', $ModuleRoot)
Invoke-Xwl @('check', $PagePath, $SqlPath, '--strict')
```

该链的 `sqlrefs` 应报告 `{#whereSql#}` 已由同文件 `serverScript` 提供，`params --strict --module-root $ModuleRoot` 应报告 `STATUS` 已由显式调用提供，末尾 `check --strict` 应为 `ALL OK`。

静态命令的证据分工：

| 命令 | 证明什么 | 不能证明什么 |
|---|---|---|
| `sqlrefs` | 本文件 `{#名字#}` 与字面量 `request.setAttribute(…)` 的集合是否自洽 | 执行时序、分支、跨 module、数据库可执行性 |
| `params --strict`，并把 `--module-root` 指向当前应用模块根 | 页面调用点与当前模块根内 SQL 参数需求是否一致 | SQL 实际执行、结果字段投影与数据库内容 |
| `paths` / `dump` | SQL 字段位置与页面结构 | 数据库返回列名 |

别名与投影不一致可能不触发 `sqlrefs` 或 `params --strict`。它们必须由人工或独立结构断言逐项比较 SELECT 别名、回包字段和 `dataIndex`；SQL 结果列与真实翻页仍要在业务库验证。

## 七、配套检查工具

完成上节 PowerShell 链后，`$Xwl`、`$SqlPath`、`$PagePath`、`$ModuleRoot` 已指向中性夹具。继续执行：

```powershell
python -B $Xwl paths $SqlPath
python -B $Xwl sqlrefs $SqlPath
python -B $Xwl params $PagePath --strict --module-root $ModuleRoot
```

核对其他 SQL 文件或页面时，把实际路径赋给 `$SqlPath` 或 `$PagePath` 后复用同一命令形状。`--controls` 接收当前 wb 工程的实际注册表路径，例如在 wb 工程根执行 `$ControlsPath = (Resolve-Path 'system/controls.json').Path`，再给 `check` 传入 `--controls $ControlsPath`。

- **`paths`** —— 同时给出「原路径」与「`@写法`」，改 SQL 前先跑它拿路径。
- **`sqlrefs`** —— 检查三件事：每个 `{#名字#}` 是否有 serverScript 提供（`sys.*` / `Str.*` 视为内置）、
  **serverScript 里是否误用了 `{#…#}`**、顺带列出所有 `{?参数?}` 名字。

  > 样本工程上的自洽率很高（明细与口径见 [`measured-data-criteria.md`](measured-data-criteria.md) §八；按你的工程现采，历史口径见 `CHANGELOG.md`）：
  > 少量告警是「由调用方传入」的正常场景，或 serverScript 误用 `{#…#}`。
  > 这类告警要**结合调用方判断**，不要一律当成错误。

- **`patch`** —— 改 SQL / 结构走 `ops.json`（操作数组），五种 `op`：`set` / `insertKey` / `insert` / `append` / `delete`；**`ops` 按顺序执行**，`path` 按执行到那一步时的结构解释。对象键优先用 `@itemId`，重名时**不猜顺序**（用 `@名字#N` 点名第 N 个、或**串联 `@`** 缩小范围）。
  值里的 JS / SQL 用**单引号**；完整示例见 `xwl.py patch --help`。
  SQL 要整行删掉或整行改写时，用 `patch` 改 `configs.sql` 的整段值。续行由序列化器按设计器规则重建。`edit` 不提供续行开关。

- **`params`** —— 自动做四件事：
  1. 列出页面里的 store 及其指向的 SQL 文件（解析 `m?xwl=`，补 `.xwl`，报文件是否存在），
     并标出 store **自身配置的 `params`**（作为 `store.load` 合并链的默认层）；
  2. 列出所有传参点并**标出通路**：`[out 推荐]` / `[params·等价out]` / `[params·显式键]`；
     `out` 会**展开容器内的取值控件 `itemId`**（哪些名字会被送出去）；
  3. 读 SQL 侧需要的名字（`{?名?}` + `app.get('名')`）做**交叉核对**：
     报「SQL 需要但页面未发现来源」与「页面送了但 SQL 用不到」；
  4. `--controls` 给了就用注册表推导取值控件类型（不给则用内置的同一份 14 个兜底）。

  示例输出（字段名示意）：

  ```text
  === 传参点（N 处）: out X 处 / params Y 处 ===
    [out 推荐]        app.tbar → 容器内取值控件 ['BIZ_NO','BIZ_TYPE','END_DATE','START_DATE','STATUS']
  === 交叉核对 ===
    页面送出 6 个: ['BIZ_NO','BIZ_TYPE','FORM_DATA','END_DATE','START_DATE','STATUS']
    SQL 需要 4 个: ['BIZ_TYPE','END_DATE','START_DATE','STATUS']
    [ok]   SQL 需要的参数在页面侧都能找到来源
    [info] 页面送了但 SQL 未用到: ['BIZ_NO','FORM_DATA']
  ```

  **这类告警要结合上下文判断**（可能来自上级容器 / 其它请求 / store 的固定 `params` / 框架上下文）。
