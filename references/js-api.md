# 事件 JS 里的四条引用通路（怎么写、怎么收）

本文是 [`SKILL.md`](../SKILL.md) 第五章 5.4 的展开 —— 四条引用通路的完整写法。
**选哪条通路**看 SKILL.md 第五章的总表与 5.1–5.3；本文给每条的**完整写法、回传处理与坑**。

| 通路 | 一行概要 | 代码写在 |
|---|---|---|
| `Wb.request` | 请求服务端片段，只要结果 | `events.*` |
| `Wb.open` | 打开子页面（列表页 / 弹窗） | `events.*` |
| `Wb.upload` | 文件上传 / 导入 | `events.*` |
| `Wb.requestAg` | 调后台 Spring 方法 | `events.*` |

> 事件 JS 一律用**单引号** —— xwl 的字符串里 `"` 必须写成 `\"`（见 SKILL.md 2.1）。

---

## 目录

- [1. `Wb.request`](#1-wbrequest--请求一个服务端片段)
- [2. `Wb.open`](#2-wbopen--打开子页面列表页--弹窗)
- [3. `Wb.upload`](#3-wbupload--文件上传--导入入口)
- [4. `Wb.requestAg`](#4-wbrequestag--调后台-spring-方法)

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
