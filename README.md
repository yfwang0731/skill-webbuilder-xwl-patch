# webbuilder-xwl-patch

处理 **WebBuilder（wb）平台 `.xwl` 定义文件**的 WorkBuddy Skill ——
**用结构级 `patch` 改 xwl，不碰文本层。**

`.xwl` 看起来像 JSON，但**不是严格 JSON** —— 磁盘上是「字面反斜杠 + 真实换行」的多行字符串。
直接拿编辑器改，**第一刀就会把文件改坏**（运行时解析失败、页面白屏）。

它能干两件事：**改**已有文件（结构级 `patch`）、**造**新文件（`new`，内置设计器真实键序的骨架）。

## 核心工作方式：结构级 `patch`

**不碰文本层。** 你只提供「值 / 子树」，工具按**设计器自己的算法**重建整份文件 ——
续行符、转义、缩进、换行全部由序列化器产出。

```bash
# 改标题 + 给工具栏加一个带多行 JS 的按钮：只写"要什么"，不写"怎么排版"
python scripts/xwl.py patch page.xwl --ops ops.json --dry-run   # 先看 diff
python scripts/xwl.py patch page.xwl --ops ops.json --backup    # 确认后落盘
```

```json
[
  {"op": "set", "path": ["title"], "value": "新标题"},
  {"op": "set", "path": ["@dataprovider", "configs", "sql"], "value": "select 1 from dual\n{#sql#}"},
  {"op": "append", "path": ["children", 0, "children"],
   "value": {"configs": {"itemId": "newBtn", "text": "新按钮"},
             "expanded": false, "children": [], "type": "button",
             "events": {"click": "Wb.info('hi');"}}}
]
```

`path` 段以 `@` 开头时按控件的 `configs.itemId` 寻址（`["@dataprovider","configs","sql"]`），
**不用关心嵌套层级**（但要求 `itemId` 唯一：重名时工具**拒绝执行**、不替你猜，
改用 `paths` 给出的原路径即可）；`xwl.py paths <file>` 会直接列出可改字段的两种写法
（`op` 支持 `set` / `insert` / `append` / `delete`）。

### 为什么这条路可靠

- **格式错误在构造上不会发生** —— 不接触文本层，就没有"改坏格式"这条路；
- 重建算法从设计器源码**完整复刻**（`IDE.updateModule` = `org.json toString(1)` + 两次 `replaceAll`），
  并做过**回放校验**：把算法跑在样本工程既有的上千个 xwl 上，还原出的字节与原件逐个比对
  （数字与口径见 [`references/measured-data.md`](references/measured-data.md)）
  → 所以重排**不会顺带改动无关内容**，**diff 只含这次真正改的内容**
  （377 KB 的页面加一个带多行 JS 的按钮 + 改标题，diff 仅 17 行）；
- 写盘前强制「**重新解析 == 改后对象**」的语义等价比对，对不上**中止不写**。

> 文本级 `xwl.py edit` 只是例外手段（改一小段文本、又不希望整份重排时）。
> 两条路都**禁止**用普通编辑器 / 通用 Edit 工具改 xwl —— 会写成裸 LF。

## 快速开始

```bash
git clone <this-repo> ~/.workbuddy/skills/webbuilder-xwl-patch   # 或直接把目录拷进去
```

### 造新文件

```bash
python scripts/xwl.py new wb/modules/<模块>/myPage.xwl --kind page --title "我的页面"
python scripts/xwl.py new wb/modules/<模块>/xxxSql/queryXxx.xwl --kind sql --title "出库单查询"
python scripts/xwl.py folders wb/modules/<模块>/myPage.xwl        # 登记检查（否则设计器里看不到）
```

### 改已有文件

```bash
python scripts/xwl.py check page.xwl                             # 1) 先看基线格式是否合法
python scripts/xwl.py paths page.xwl                             # 2) 改 SQL/数据源时：拿字段路径（含 @itemId 写法）
                                                                 #    其余改动用 dump 看层级
python scripts/xwl.py patch page.xwl --ops ops.json --dry-run     # 3) 看 diff
python scripts/xwl.py patch page.xwl --ops ops.json --backup      # 4) 落盘
python scripts/xwl.py check page.xwl                             # 5) 改完必跑校验
```

## 工具速查

| 子命令 | 干什么 |
|---|---|
| `new <out.xwl> --kind page\|sql [--from-json F]` | **从零生成**：内置设计器真实键序的骨架（页面 / SQL 载体）；默认拒绝覆盖已有文件 |
| `patch <file> --ops ops.json` | **结构级编辑（默认方式）**：只给值/子树，按设计器算法重建整份文件 |
| `folders <path> [--register NAME]` | `folder.json`（设计器导航树索引）一致性检查（**只读**）：未登记 / index 悬空 / 缺 folder.json；`--register` 才写 |
| `check <file...>` | 七项校验：格式五项 + 事件 JS `node --check` + **itemId 重名分级**；任一 FAIL 返回非 0 |
| `itemids <file>` | **itemId 重名报告（只读）**：分级（无害 / 待区分 / 需处理）+ 候选清单（祖先链、其下控件）+ 建议改名；`--suggest` 出 ops 草稿 |
| `paths <file>` | 列出 `sql` / `totalSql` / `serverScript` / `url` 四类字段的位置，给「原路径 + `@itemId` 写法」（重名时给 `@名字#N` 点名写法） |
| `params <page.xwl>` | 核对「参数控件 → store → SQL」传参链路（标出 `out` / `params` 两条通路） |
| `sqlrefs <file>` | 校验 SQL 片段里 `{#名字#}` 与 `serverScript` 是否自洽 |
| `schema [<type>] --controls <…/controls.json>` | 查控件注册表：`--tree` 面板分组树、`--list` 控件 id、`--skeleton` 设计器同款骨架 |
| `expand <file>` | 单行 → 设计器同款多行（含语义等价比对） |
| `edit <file> --old-file O --new-file N` | 文本级安全替换（**例外**手段） |
| `dump` / `sql` / `events` | 解析后美化输出 / 抽 SQL / 导出事件 JS |

## 目录结构

技能主体在 [`SKILL.md`](SKILL.md)，细节按需查 `references/`：

```
webbuilder-xwl-patch/
├── SKILL.md                  # 完整流程与规则：格式硬规则、新建/编辑流程、SQL 片段要点、引用方式、工具、坑
├── CHANGELOG.md              # 变更历史（倒序，含每一步的依据与实测数字）
├── test-prompts.json         # 6 条典型 prompt（供 skill 评估用）
├── references/
│   ├── controls.md           # 控件清单：有哪些 / 干什么 / 该挂哪里 / 怎么选
│   ├── sql-fragments.md      # SQL 片段：两级结构、字段全集、{#…#} 引用、页面传参两条通路
│   └── measured-data.md      # 实测数据：引用次数 / 传参分布 / 各频次与统计口径
└── scripts/
    ├── xwl.py                # 全部子命令（纯标准库，零依赖）
    └── selftest.py           # 内置样本自检：python scripts/selftest.py
```

## 依赖

- Python 3.9+（纯标准库）
- （可选）Node.js —— 仅用于事件 JS 语法校验；缺失时自动降级为警告。
  可用 `--node <path>` 或环境变量 `NODE_BIN` 指定。

> 范围：只看 `.xwl` 文件本身（格式、编辑、校验、抽取）。
> 不涉及菜单注册（`WB_MENU`）、后端代码、模块打包、部署副本同步。

## 许可

MIT，见 [LICENSE](LICENSE)。
