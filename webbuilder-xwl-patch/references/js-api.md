# 事件 JS 的四条引用通路 ＋ 变更集（怎么写、怎么收）

本文展开四条通路的完整写法，另加**一节变更集**（`Wb.getModified`，见本文第 6 节）。
**选哪条通路**看本文的总表与「url 的三种写法」「引用位置」两节；`m?xwl=` 引用的读法见 [`sql-fragments.md`](sql-fragments.md) §3.3；本文给每条的**完整写法、回传处理与坑**。

| 通路 | 一行概要 | 代码写在 |
|---|---|---|
| `Wb.request` | 请求服务端片段，只要结果 | `events.*` |
| `Wb.open` | 打开子页面（列表页 / 弹窗） | `events.*` |
| `Wb.upload` | 文件上传 / 导入 | `events.*` |
| `Wb.requestAg` | 调后台 Spring 方法 | `events.*` |

> ⚠️ 上面四条都是**引用通路**（都要请求服务端）。**取 grid 的变更集**不属于通路 ⇒ 单独一节，见 §6 的 `Wb.getModified`。

> 事件 JS 一律用**单引号** —— xwl 的字符串里 `"` 必须写成 `\"`（见 [`faq.md`](faq.md) §一）。

---

## 目录

- [1. `Wb.request`](#1-wbrequest--请求一个服务端片段)
- [2. `Wb.open`](#2-wbopen--打开子页面列表页--弹窗)
- [3. `Wb.upload`](#3-wbupload--文件上传--导入入口)
- [4. `Wb.requestAg`](#4-wbrequestag--调后台-spring-方法)
- [5. 窗口：`createInstance` / `closeAction` 与 `app._X`](#5-窗口createinstance--closeaction-与-app_x)
- [6. `Wb.getModified` —— 取 grid 的变更集（用法约定，非平台契约）](#6-wbgetmodified--取-grid-的变更集用法约定非平台契约)
- [附录：引用通路总表与代码位置](#附录引用通路总表与代码位置)

## 1. `Wb.request` —— 请求一个服务端片段

```js
// 查询/校验/取数：不建页面，只要结果
Wb.request({
  url: 'm?xwl=<模块>/<业务目录>/selectBizStatus',
  params: values,                 // 或 out: app.editWin（整包收容器内控件值）
  // async: false,                // 需要同步拿结果时
  success: function (resp) {
    var data = Wb.decode(resp.responseText);   // ← 回传后前台的标准取法
    ...
  },
  failure: function (resp) {
    Wb.info('失败：' + resp.responseText);
  }
});
```

回传后前台怎么处理（**四种响应形态对应四种取法**）：

| 响应的来源节点 | `resp.responseText` 是什么 | 前台怎么写 |
|---|---|---|
| `dataprovider`（执行 SQL） | JSON：`{"success":true,"rows":[…],"total":n}` | `Wb.decode(resp.responseText).rows` / `.total` |
| `serverScript` + `app.send(x)` | `x` 本身（字符串/数字/JSON 文本） | 直接比较或用 `Wb.decode` |
| `app.run(sql)`（serverScript 里执行 SQL） | 结果集（框架已处理 null） | `Wb.decode(...)` 后按 rows 用 |
| 出错 | 错误文本 / `{"msg":"…"}` | 交给默认 `Wb.except`，或自己 `Wb.info(...)` |

要点：

- **参数怎么给**：`params: {...}` 或 `out: app.<容器>` —— 完整规则（收哪些控件、两个 API 覆盖方向相反）
  见 [`sql-fragments.md`](sql-fragments.md) 第五节。
- **别用 `Wb.request` 代替 store**：列表/分页/排序要用 `store.load(...)`（框架会带上 `page`/`start`/`limit` 并处理返回）。
- 默认**失败自动弹错**；不想弹就 `showError: false`，自己处理 `failure`。
- `callback` 会先于 `success`/`failure` 被调用，签名是 **`(form, action, value, success)`**（比 `success` 多一个布尔），**返回 `false` 可跳过**后续处理（用于统一拦截）。
- 返回值是请求对象，可用于取消：`var req = Wb.request({...}); req.abort?` → 实际用 `Ext.Ajax.abort(req)`。
- 相关近亲：`Wb.submit(url, params, target, method, isUpload)`（常规表单提交，涉及文件必须用它）、
  `Wb.download(url, params, isUpload, method)`（下载）。
- **跨页面传参不在核对范围**：`Wb.open({url:'m?xwl=…', params:{…}})` 传进**子页面**的键写在
  **调用方**页面里，子页面自己看不到（运行时值从 request 取，静态不可见）⇒ `params <子页面>`
  会把对应的 `{?名?}` 报成"未发现来源"，那是**能力边界不是错误**；要核对就到**调用方页面**跑。

## 2. `Wb.open` —— 打开子页面（列表页 / 弹窗）

```js
Wb.open({
  url: 'm?xwl=<模块>/<业务目录>/bizPayList',
  title: '业务单据',
  iconCls: '',
  params: { BIZ_NO: data.bizNo }              // 子页面里 app.get('BIZ_NO') 可取
});
```

- 在首页 / IDE 环境下**开成 tab 页并复用**；否则新窗口打开。同路径已打开时**默认激活已有 tab**；
  想强制新开就带 `params`（或显式 `newTab: true`）。
- 常用选项：`title` / `iconCls` / `icon` / `params` / `mask` / `showError` /
  `inframe`（外部 url 用）/ `frameOnly`（只建 tab 不加载）/ `reload`（已存在则重载）/
  `container`（挂到指定容器）/ `newWin`（新窗口表单提交）/ `download`。
- 回调：`success(appScope, responseText)` / `failure(appScope, responseText)`，`this` 指向那个 tab 卡片。
- **只想请求不要 tab** → `Wb.run({url, params, success})`（= `Wb.open` + `container:false`）。

## 3. `Wb.upload` —— 文件上传 / 导入入口

```js
// ① 先把文件传到"上传承载页"，拿回服务端返回的值（通常是文件路径/新文件名）
Wb.upload({
  form: app.form1,                 // 必填：含 file 控件的 form 面板
  url: 'm?xwl=<模块>/<业务目录>/fileUpload',
  showProgress: true,
  // out: app.form1,               // 也可显式指定取值的容器
  success: function (form, action, value) {
    app.DOWNLOAD_URL.setValue(value);   // ← value = action.result.value
  },
  failure: function (form, action, value) {
    var d = Wb.decode(action.response.responseText);
    Wb.info('导入失败：' + d.msg);
  }
});
```

**回调签名（框架改过 ExtJS，官方就是三参）** —— `ext-all-debug.js` 的
`Ext.form.Basic.afterAction`：`Ext.callback(action.success, scope, [me, action, value])`，
其中 `value = action.result.value`（服务端返回值），`action` 是 form action 对象：

| 回调 | 签名 | 关键取值 |
|---|---|---|
| `success` | `(form, action, value)` | `value` = 服务端返回值 |
| `failure` | `(form, action, value)` | `action.response.responseText` → `Wb.decode(...).msg` |
| `callback` | `(form, action, value, success)` | 返回 `false` 可跳过 success/failure |

> 样本工程里大量写成 `success: function(action, form1, value)`——**参数名与实际顺序错位一位**
> （`action` 实际是 form、`form1` 实际是 action）。只用到第 3 个参数 `value` 时**照样能跑**，
> 但新写代码请按官方顺序 `(form, action, value)`。失败分支里的 `failure: function(resp, action)`
> 同理：`action` 才是 action 对象，所以 `action.response.responseText` 能取到。
> 另外 `form.form.submit` 走的是 form 提交通道，`_jsonresp=1` 由框架自动加。

**导入类页面的典型两步链**（样本工程里最标准的导入写法）：

```text
① Wb.upload  → 上传承载页 xwl（如 <模块>/…/fileUpload.xwl）→ 拿到文件在服务端的值
② Wb.request → 校验页 xwl（可多个，如 selectXxxInsertStatus / …UpdateStatus）
③ Wb.requestAg → 落库（bean/method），成功回调里关窗 + store.load() + Wb.tip
```

## 4. `Wb.requestAg` —— 调后台 Spring 方法

**只看前台这一侧** —— 后台方法怎么写属于后端范围，不在本 skill 内；这里只说"怎么调、怎么收"。

```js
Wb.requestAg({
  params: {
    bean: 'xxxController',       // 后台 bean 名（必须）
    method: 'saveMethod',        // 方法名（必须）
    BIZ_DATA: values,            // 业务参数：键名就是后台取参名
    data: Wb.encode(rows)        // 表格批量数据用 data 键（JSON 字符串）
  },
  success: function (resp) {
    win.close();
    app.grid1.store.load();
    Wb.tip('保存成功');
  }
});
```

前台侧的约定：

| 项 | 约定 |
|---|---|
| url | **不用写**，框架固定改成 `m?xwl=common/save-all`（`wb-debug.js` 里写死） |
| 保留键 | `bean` / `method` —— 必须给，且与业务参数平铺在同一层 |
| 业务参数 | 其余键原样变成请求参数；**后台按同名取**（`app.get('x')` 同源）。参数名必须与后台一致，否则取到空 |
| `out` | 同样支持，合并规则与 `Wb.request` 一致（`out` 覆盖 `params`） |
| 表格批量增删改 | 用 `data`（`Wb.encode(...)` 的 JSON 字符串）+ 配套键 `datatable` / `className` / `insertSql` / `updateSql` / `deleteSql`（实测 Top 组合） |
| 同一 bean 多方法 | 只改 `method` 即可，`bean` 复用 |

> 实测常用业务参数名与频次（`idList` / `datatable` / `className` / `insertSql` / `updateSql` / `deleteSql`…）
> 见 [`measured-data.md`](measured-data.md) §三。

**后台传回后，前台怎么处理**：最常见的是**提示 + 刷新 + 关窗**这三件事
（实测占比 91% / 78% / 29%）；返回值本身只有约六成调用点会读，且多数是普通文本或数字，
直接 `if (data == 1)` 判，约四成才需要 `Wb.decode`。完整分布与口径见
[`measured-data.md`](measured-data.md) §四。

要点：

- **成功/失败的分界由响应决定**：框架判断为成功才走 `success`；业务上的"失败"往往由后台返回一个
  非预期值，**前台自己 `if/else` 判**（例：`if (data == 1) {…} else { Wb.warn('操作失败') }`）。
- `failure` 回调拿到的是 `(resp, options)`；错误文本在 `resp.responseText`。
  默认**框架会自动弹错**（`Wb.except`），要自己接管就 `showError: false`。
- 上传类失败的错误对象不同（`action.response.responseText` → `{msg}`），见本文 §3 —— **别混用**。
- 保存成功后的标准三连：**关窗 → 刷新来源 store → `Wb.tip` 提示**。来源 store 可能是父页面
  （`app.grid1.store.load()`）或当前弹窗（`win.close()` 前先拿引用）。

## 5. 窗口：`createInstance` / `closeAction` 与 `app._X`

**两条规则先记住**：

1. **`app._X` 是"配置模板键"，`app.X` 是"实例句柄"。** 二者在**生成期就指向同一对象**：
   控件 `createInstance` 为真（缺省）时，服务端直接生成 `app.X = app._X = new <type>({…})`
   ⇒ **两个键一开始就都是实例**；为 `"false"` 时生成 `app.X = app._X = {…}`
   ⇒ **两个键一开始都是配置**、页面加载时不会实例化任何东西。
2. **写法必须与 `closeAction` 配套**：

| 路线 | `createInstance` | 打开 | 关闭 | `closeAction` |
|---|---|---|---|---|
| **常驻** | 真 / 缺省 | 加载时框架已建好；之后只 `app.X.show()` | `app.X.hide()` | **`'hide'`** |
| **每次重建** | `"false"` | 每次 `new Ext.window.Window(app._X)` | 实例被销毁 | **`'destroy'`** |

**为什么"每次重建"必须用 `app._X`**：`closeAction` 为 `destroy` 时，控件销毁会连带
**把 `app.X` 从页面作用域里删掉**（框架按注册键注销）。之后 `app.X` 就是 `undefined`，
再拿它当构造参数会得到一个**空白窗**。`app._X` 是普通属性、**永不被注销**，所以可以反复取用。

**⚠️ 窗口挂在 `viewport` 下没有 `app._X`**：那对孪生键只会为 **`module` / `folder` 的直接子控件**
生成。挂在 `viewport` 下的窗口只有 `app.X`（由框架注册器写入）= 实例，
⇒ **想做"每次重建"就必须把窗口放到 `module` 直接子级**。

**用途建议**（是建议、不是校验项）：

- 常驻（`hide`）多用于**窗口内嵌 grid 做查询**。此时窗口在页面加载时就已实例化，
  窗口内的 grid / store **建议不要 `autoLoad`**，改为每次打开时再查询（否则页面一打开就发查询、且数据会放旧）。
- 每次重建（`destroy`）多用于**窗口内嵌 panel/form 做数据编辑**。每次销毁可避免旧数据残留，
  但**取数据必须在销毁之前完成**（销毁会连带销毁子控件，之后取不到值）。

**保活**：模块页签关闭/重载会清空整个模块作用域。常驻窗口若想活过这次清理，
需先把引用摘掉（`delete app.X; delete app._X;`），否则会被一并销毁。

**反例**：

- `new Ext.window.Window(app.X)` —— 把**实例当配置**。`closeAction` 是 `destroy` 时
  第二次打开得到空白窗；是 `hide` 时能显示但会留下泄漏的旧实例、并可能重复 id。
- `app.X = new Ext.window.Window(app.X);` —— **回写**写法：靠"第一次 `app.X` 恰好还是配置"
  侥幸成立；一旦销毁过就退化成空白窗。
- `closeAction` 留缺省却每次 `new` —— 旧的隐藏实例不会被销毁，越开越多。

**出处**：框架侧为 `ExtControl`（服务端生成那对孪生键）与 ExtJS 注册器（按注册键注销）；
平台自带示例 `examples/basic/import-module.xwl` 的注释把两种用法都演示了。
实测分布见 [`measured-data-designer.md`](measured-data-designer.md) §十二。

## 6. `Wb.getModified` —— 取 grid 的变更集（用法约定，非平台契约）

> 取证：2026-10-24 · 样本工程（内部语料，事件 JS 全量）· 依据 `Wb.getModified` 的调用形态与返回值取用方式 · 口径＝实现细节、非对外契约

**它取什么**：一个 grid 里**改动过、还没落库**的行 —— 哪些是新增、哪些改过、哪些删了。
"只提交变化"与"没改就别发请求"这两类写法都靠它；取到之后再交给 §4 的 `Wb.requestAg` 去落库。

### 6.1 三类键（有实现可证，按约定用）

返回对象按**变更类型**分桶，键名固定三个：

| 键 | 含义 | 怎么用 |
|---|---|---|
| `create` | 新增的行 | 逐行取业务键，拼插入参数 |
| `update` | 改过的行 | 逐行取主键 ＋ 改过的列 |
| `destroy` | 删掉的行 | 逐行取主键 |

```js
// 拦截：一条都没改就不发请求
if (Wb.isEmpty(Wb.getModified(app.<grid>).update)) {
  Wb.warn('没有改动，无需保存');
  return;
}

// 分桶：三个桶各拼一份参数
Wb.each(Wb.getModified(app.<grid>).create, function (row) { /* 新增 */ });
Wb.each(Wb.getModified(app.<grid>).update, function (row) { /* 更新 */ });
Wb.each(Wb.getModified(app.<grid>).destroy, function (row) { /* 删除 */ });
```

- **入参传 grid 句柄**（`app.<grid>`）；返回的是**变更集对象**，⛔ 不是行数组 —— 要行数组就取它的桶。
- ⚠️ 桶**可能是空数组**（该类变更没发生）⇒ ⛔ 别假定一定有元素。
- 近亲：store 侧的 `store.getModifiedRecords()`（原始行数组形态，判空常用）。

### 6.2 提交前的标记（半证：取决于后端签名）

- `update`／`destroy` 提交时，"**哪些列真要写回**"可以由一个标记表达；标记在**第二参**给出。
- ⚠️ **标记怎么解释、是否生效，取决于后端签名**（存 SQL 与 bean 方法各一套）⇒ 本节只说明这层依赖存在，**不承诺具体写法**。
- ⚠️ 本机语料**未覆盖**该写法（全部调用点为单参）⇒ 这一层属**半证**：知道有这件事，用之前到后端那一侧确认。

### 6.3 它不是引用通路

`Wb.getModified` **不请求服务端**，只读本地变更状态 ⇒ 它负责"取"；提交仍走 §1 的 `Wb.request` 或 §4 的 `Wb.requestAg`。

## 附录：引用通路总表与代码位置

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
> [`js-api.md`](js-api.md)；各条在样本工程里的**出现次数**见
> [`measured-data.md`](measured-data.md) §一（只作量级参考，与你怎么改无关）。

### 5.1 怎么读一个 `m?xwl=` 引用

> 引用写的是**模块相对路径、不带 `.xwl` 后缀**（**补上 `.xwl`** 即文件路径）；**从文件找引用方**见
> [`sql-fragments.md`](sql-fragments.md) §3.3（**被引用的片段是常态**）。

### 5.2 url 的三种写法

| 写法 | 例 | 说明 |
|---|---|---|
| `m?xwl=<模块相对路径，**不带 `.xwl`**>` | `m?xwl=<模块>/…/xxxSql/queryBizList` | **最常用**。相对 `wb/modules/`，补 `.xwl` 就是文件路径（见 [`sql-fragments.md`](sql-fragments.md) §3.3） |
| `/<短名>` | `/upload`、`/get-file`、`/download` | 短名注册表 **`wb/system/url.json`**，框架内部端点。改动时别自己编短名 |
| `http://…` 或任意 url | `Wb.open({url:'http://…', inframe:true})` | 外部地址必须 `inframe:true` |

> `url` 的解析口径（短名**不解析**、**只判本 wb 根**、**按单 webapp 判定**）见 [sql-fragments.md](sql-fragments.md) §3.4。

### 5.3 引用位置：这些代码写在 xwl 的哪一处

| 位置 | 放什么 |
|---|---|
| `控件.events.click` / `ok` / `beforeedit` / `select` … | `Wb.request` / `Wb.open` / `Wb.requestAg` / `Wb.upload`（**最常见**） |
| `store.configs.url` | 数据源指向 SQL 文件 |
| `store.configs.autoLoad` (+ `configs.params`) | 首屏自动加载，用固定参数 |
| `column.configs.renderer` | 列渲染时取数（少见） |
| `module.configs.serverScript` | 服务端 `app.get` / `app.run` / `app.send` / `app.rundomain` / **`app.execute(url)`** |
| xwl 顶层 `inframe` / `pageLink` | 页面本身的打开方式（是否 iframe、菜单/链接地址） |

> 事件 JS 一律用**单引号**（xwl 的字符串转义规则，见 SKILL.md 第二章）。

### 5.4 四条最容易踩的

> 四条易踩的完整说明见 [js-api.md](js-api.md) 与契约 `test-prompts.json`。
