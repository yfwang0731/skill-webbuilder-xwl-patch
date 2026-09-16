# 一次完整的实操：从零造一个查询页面 + 它的 SQL 载体

本文件是**手把手走一遍**：把 SKILL.md 第三章的「处理流程」落到一个具体例子上。
读它比读规则快 —— 但**规则以 SKILL.md 为准**，这里只演示顺序、命令与预期输出。

**目标**：造一个「出库单查询」页面 —— 它带自己的 SQL 载体、一个查询工具栏、一个表格，
并且工具栏上的按钮挂了点击事件。

> 下文的 `<模块>` 是占位符，指你自己的业务模块目录（形如 `wb/modules/<模块>/`）。
> **把 `<模块>` 换成实际目录名后再跑**；文件名同理，这里用的都是示意名。

---

## 第 0 步 · 先确认两件事

```bash
python --version                                  # 需要 3.9+
python <本skill目录>/scripts/xwl.py --help        # 能列出子命令就说明工具可用
```

然后确认**要造的是哪一类** —— 这决定 `--kind`：

| 要造的 | `--kind` | 特征 |
|---|---|---|
| **页面**（PC 页面 / 弹窗 / 子面板） | `page` | 用户会直接打开，或被别的页面用 `Wb.open` 打开 |
| **SQL 载体**（数据源片段） | `sql` | 不被打开，只被别的 xwl 用 `store.url = 'm?xwl=…'` 或 `Wb.request` 引用 |

> 拿不准就搜现有工程里有没有人引用它 —— 见 SKILL.md 1.1。

---

## 第 1 步 · 造 SQL 载体

```bash
python <本skill目录>/scripts/xwl.py new wb/modules/<模块>/xxxSql/queryOrder.xwl --kind sql --title "出库单查询"
```

产出两层，各管一件事（见 SKILL.md 第六章）：

```
module(serverScript)  → 取参数、拼条件
  └ dataprovider(sql) → 拿拼好的 SQL 去执行
```

**预期**：命令正常结束，末行为 `=== 结果: ALL OK`。
它还会顺手把「新建之后必做」三条提示打出来（`folder.json` 登记 / `sqlrefs`|`params` / `WB_MENU` 挂菜单）。

> 新生成的骨架里，`module` 的 `itemId` 就叫 `module`、`dataprovider` 的 `itemId` 就叫 `dataprovider`
> —— 记住这两个名字，下一步的 `@寻址` 要用。**别自己猜**，跑 `paths` 看一眼最准。

---

## 第 2 步 · 填 serverScript 与 sql

`patch` 只吃「值 / 子树」，格式（续行、转义、缩进）由序列化器产出 —— 你**不需要**关心文本层。

先看一眼可编辑字段的位置与推荐写法：

```bash
python <本skill目录>/scripts/xwl.py paths wb/modules/<模块>/xxxSql/queryOrder.xwl
```

输出会给出两套路径（`@` 写法不受嵌套层数影响，优先用）：

```
serverScript  (module, itemId='module', …)
   推荐   : ["@module", "configs", "serverScript"]
sql  (dataprovider, itemId='dataprovider', …)
   推荐   : ["@dataprovider", "configs", "sql"]
```

写 `ops-sql.json`：

```json
[
  {"op": "set", "path": ["@module", "configs", "serverScript"],
   "value": "var sql = 'select ORDER_NO, CUSTOMER, QTY, CREATED_ON from ORDER_FILE where 1=1';\nvar orderNo = app.get('orderNo');\nif (orderNo) { sql += \" and ORDER_NO = '\" + orderNo + \"'\"; }\nrequest.setAttribute('sql', sql);"},
  {"op": "set", "path": ["@dataprovider", "configs", "sql"],
   "value": "select ORDER_NO, CUSTOMER, QTY, CREATED_ON from ORDER_FILE where 1=1\n{#sql#}"}
]
```

> JSON 里的 `\n` 会被序列化器写成磁盘上的「反斜杠 + 真实换行」，也就是设计器同款形态 ——
> **这正是 `patch` 的价值**：你不用自己写那种续行符，写错了也不可能。

先看 diff，再真改：

```bash
python <本skill目录>/scripts/xwl.py patch wb/modules/<模块>/xxxSql/queryOrder.xwl --ops ops-sql.json --dry-run
python <本skill目录>/scripts/xwl.py patch wb/modules/<模块>/xxxSql/queryOrder.xwl --ops ops-sql.json --backup
```

⏭️ 下一步：确认 SQL 引用自洽。

---

## 第 3 步 · 校验 SQL 载体

```bash
python <本skill目录>/scripts/xwl.py sqlrefs wb/modules/<模块>/xxxSql/queryOrder.xwl
```

它核对 `{#名字#}` 与 `serverScript` 里 `setAttribute` 的名字对不对得上。
**对不上是静默失效** —— 页面不报错，只是查不出数据。所以这步不能跳。

**预期**：出现 `[ok] {#sql#} × 1 ← serverScript 已提供`，末行 `=== 结果: OK`。

⏭️ SQL 侧完成，开始造页面。

---

## 第 4 步 · 造页面

```bash
python <本skill目录>/scripts/xwl.py new wb/modules/<模块>/orderQuery.xwl --kind page --title "出库单查询"
```

产出：顶层 7 把钥匙 + 一个空 `module` 节点。**键序已经是对的**，你不用管（这也是不用"拿别的文件当种子"的原因）。

---

## 第 5 步 · 把控件树搭进去

新建页面里 `module.children` 是空的 —— 所以这次用 `set` 一次把整棵子树写进去，最省事。
**节点形态照 SKILL.md 1.2 的标准形态写**：键序 `configs, expanded, children, type`，有事件才加 `events`。

写 `ops-page.json`：

```json
[
  {"op": "set", "path": ["children", 0, "children"], "value": [
    {"configs": {"itemId": "viewport"}, "expanded": false, "children": [
      {"configs": {"itemId": "tbar"}, "expanded": false, "type": "toolbar", "children": [
        {"configs": {"itemId": "orderNo", "fieldLabel": "订单号"}, "expanded": false, "children": [], "type": "text"},
        {"configs": {"itemId": "queryBtn", "text": "查询"}, "expanded": false, "children": [], "type": "button",
         "events": {"click": "app.gridStore.load({ out: app.tbar });"}},
        {"configs": {"itemId": "exportBtn", "text": "导出"}, "expanded": false, "children": [], "type": "button",
         "events": {"click": "var s = app.grid1.getSelection();\nif (!s.length) { Wb.info('请先选中一行'); return; }\nWb.info('准备导出 ' + s[0].data.ORDER_NO);"}}
      ]},
      {"configs": {"itemId": "grid1"}, "expanded": false, "type": "grid", "children": [
        {"configs": {"itemId": "gridStore", "url": "m?xwl=<模块>/xxxSql/queryOrder"}, "expanded": false, "children": [], "type": "store"}
      ]}
    ], "type": "viewport"}]
  },
  {"op": "set", "path": ["roles"], "value": {"default": 1}}
]
```

```bash
python <本skill目录>/scripts/xwl.py patch wb/modules/<模块>/orderQuery.xwl --ops ops-page.json --dry-run
python <本skill目录>/scripts/xwl.py patch wb/modules/<模块>/orderQuery.xwl --ops ops-page.json --backup
```

> `path` 的 `["children", 0, "children"]` 就是「顶层 `children[0]`（`module` 节点）的 children」。
> **能用 `@itemId` 就尽量用**（如 `["@module", "children"]`），它不受嵌套层数影响。

**这三处最容易写错，改完对一眼**：

1. `store` 是 **`grid` 的子节点**，不是 `grid` 的兄弟（骨架见 `references/controls.md` §4.2）；
2. `store.url` 用**模块相对路径、不带 `.xwl` 后缀**；
3. 新增控件的 `itemId` **在文件内唯一**（列控件可重名，见 SKILL.md 第七章）。

**预期**：`patch` 报告已应用 2 个 op、语义等价比对通过，`--backup` 生成 `.bak`，自动校验 `ALL OK`。

---

## 第 6 步 · 核对「页面 → store → SQL」的传参

```bash
python <本skill目录>/scripts/xwl.py params wb/modules/<模块>/orderQuery.xwl --module-root wb/modules
```

它列出 store、展开两条通路（`out` / `params`）传参点，并与 SQL 侧交叉核对。

**看到 `url=… → 未找到` 就是路径写错了**（说明 `store.url` 指向的文件不存在）；
看到「SQL 需要但页面未发现来源」就查参数名 —— 参数名 = 控件 `itemId`，**对不上是静默失效的**。

---

## 第 7 步 · 格式与命名校验

```bash
python <本skill目录>/scripts/xwl.py check wb/modules/<模块>/orderQuery.xwl wb/modules/<模块>/xxxSql/queryOrder.xwl
```

**预期**：每个文件 `-> OK`，末行 `=== 结果: ALL OK`。有 `[FAIL]` 就按第八章 FAQ 排查。

> 大文件上先跑 `check --no-js` 快得多（486 KB 实测：全开约 1 s、`--no-js` 约 0.4 s）。
> 老的逐段实现要 63 s，现在已批量化 —— 数字与原因见 SKILL.md 4.1。

---

## 第 8 步 · 登记进 `folder.json`

先看有没有登记（**默认只读**）：

```bash
python <本skill目录>/scripts/xwl.py folders wb/modules/<模块>
```

**前提**：该目录必须**已经被设计器管理** —— 也就是目录里已经有一个 `folder.json`。
没有的话 `--register` 会明确报错并退出 2，它**不会**替你创建一个
（那是设计器的职责）。新目录请先在设计器里建，或从同类目录复制一份 `folder.json` 再改 `title`。

看到「未登记」就登记 —— **`--register` 要指到文件上**：

```bash
python <本skill目录>/scripts/xwl.py folders wb/modules/<模块>/orderQuery.xwl --register --dry-run
python <本skill目录>/scripts/xwl.py folders wb/modules/<模块>/orderQuery.xwl --register
```

**预期**：`--dry-run` 打印 before/after 且写明 `未写入`；真跑打印 `已写入` 并留下 `folder.json.bak`；
再跑一次会说「已登记在 index 第 N 项，无需改动」（**幂等**）。

**不登记的话，设计器左侧树里就没有它** —— 文件其实是好的，但你会以为它坏了。

> 给**目录**加 `--register` 会被明确拒绝（退出码 2）—— 一个目录里可能有好几个文件，
> 工具不知道你要登记哪一个。它**不会**静默地什么都不做。

---

## 第 9 步 · 交付前自检

过一遍 SKILL.md 第九章的清单。最常被跳过、也最要命的两条：

- [ ] **在设计器里打开一次**。`check` 只证明"格式能加载"，**不证明"页面能用"**；
      新文件又没有 `git diff` 可比 —— 所以这一步没有替代品。
- [ ] 知道**要让用户能打开，还得在数据库 `WB_MENU` 挂菜单**（权限在 `WB_ROLE` / `WB_RESOURCE`）——
      这超出本 skill 范围。别以为文件建好就能打开。

---

## 出错了怎么回退

| 症状 | 怎么办 |
|---|---|
| `patch` 报「语义等价比对失败」 | 它**没有写盘**，原文件完好。检查 ops 里是不是给了不合适的值（比如把对象写进了字符串字段） |
| 写盘后 `check` FAIL | 用同目录的 `<file>.bak` 覆盖回去再排查 —— 所以**真改时一定带 `--backup`** |
| 顺序搞错、想整体撤销 | 靠 git：`git checkout -- <file>`。格式校验救不了语义改错，git 可以 |
| `@itemId` 报重名 | 工具**不猜顺序**，会列候选清单。照清单选，或用 `@名字#N` 点名（见 SKILL.md 7.4） |
| 不知道某控件该挂在哪 | `xwl.py schema <type> --controls wb/system/controls.json`；骨架见 `references/controls.md` §4.2 |
| 不确定命令会不会写盘 | 先加 `--dry-run`。绝大多数子命令都支持 |

---

## 一句话回顾

```
确认环境与 --kind
  → new --kind sql   → paths → patch 填 serverScript/sql → sqlrefs
  → new --kind page  → patch 搭控件树 → params → check → folders --register
  → 设计器打开一次（+ 记得 WB_MENU 挂菜单）
```

每一步都守同一条习惯：**先 `--dry-run` 看 diff，确认后再真跑并带 `--backup`**。
这条习惯比记住任何子命令都值钱。
