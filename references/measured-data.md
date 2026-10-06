> 发布面：随 skill 发布 ｜ 层归属：依据层

# 实测数据与统计口径

> **样本**：样本工程 `wb/` 下 **2780 个 `.xwl`**（其中 **2777 个可解析** —— 3 个模板样本不是纯 JSON；
> `target/` 下的部署副本不计入）。引用「2777」的地方都是指可解析的那部分。
> **方式**：用 `scripts/xwl.py` 的解析器遍历 JSON 树统计；**已剔除 JS 注释**（注掉的 `out:` / `params:` 不计）。
> ⚠️ **比例不可外推**：本文是**单工程**样本。换到 8 个 wb 根 / 24986 个 xwl 的全量复算，
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
- [五、设计器写回算法的复刻一致性](measured-data-designer.md)
- [六、控件使用频次与父子结构](measured-data-designer.md)
- [七、itemId 与 normalName](measured-data-addressing.md)
- [八、SQL 片段与 serverScript 的分布](measured-data-criteria.md)
- [九、页面顶层骨架与 folder.json](measured-data-skeleton.md)
- [十、规模与耗时](measured-data-skeleton.md)
- [十一、判据修正的对照数](measured-data-criteria.md)
- [十二、窗口两种用法的实测分布](measured-data-designer.md)

## 主题文件索引

主文件只留**最常用**的 前言 / 目录 / 一~四；五~十二 各自并入对应主题文件（**原节号保持不变**）：

- **五 · 六 · 十二**（写回复刻一致性 / 控件 / 窗口）→ [`measured-data-designer.md`](measured-data-designer.md)
- **七**（itemId 与 normalName，重名分级的数据依据）→ [`measured-data-addressing.md`](measured-data-addressing.md)
- **八 · 十一**（SQL / serverScript 分布 / 判据修正对照数）→ [`measured-data-criteria.md`](measured-data-criteria.md)
- **九 · 十**（页面顶层骨架 / folder.json / 规模与耗时）→ [`measured-data-skeleton.md`](measured-data-skeleton.md)

> 这几个主题文件属**依据层**（首行已声明），**仍受 ≤8k 约束**（实测最大 7,202 字符）；不受 8k 约束的是**规格层**（`anti-patterns.md`／`faq.md` 一类）。

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


