# webbuilder-xwl-patch

[![selftest](https://github.com/yfwang0731/skill-webbuilder-xwl-patch/actions/workflows/selftest.yml/badge.svg)](https://github.com/yfwang0731/skill-webbuilder-xwl-patch/actions/workflows/selftest.yml)

处理 **WebBuilder（wb）平台 `.xwl` 定义文件**的 WorkBuddy Skill ——
**用结构级 `patch` 改 xwl，不碰文本层。**

`.xwl` 看起来像 JSON，但**不是严格 JSON** —— 磁盘上是「字面反斜杠 + 真实换行」的多行字符串。
直接拿编辑器改，**第一刀就会把文件改坏**（运行时解析失败、页面白屏）。

它能干两件事：**改**已有文件（结构级 `patch`）、**造**新文件（`new`，内置设计器真实键序的骨架）。

> **范围**（放最前面，因为它决定你要不要往下读）：只看 `.xwl` 文件本身 —— 格式、编辑、校验、抽取。
> **不含**菜单注册（`WB_MENU`）、后端代码、模块打包、`target/` 部署副本同步；
> 也**不适用于**其他低代码平台的页面定义、`.vue`、普通 `.json`。

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
  → 所以重排**不会顺带改动无关内容**，**diff 只含这次真正改的内容**
  （377 KB 的页面加一个带多行 JS 的按钮 + 改标题，diff 仅 17 行）；
- 写盘前强制「**重新解析 == 改后对象**」的语义等价比对，对不上**中止不写**。

> 文本级 `xwl.py edit` 只是例外手段（改一小段文本、又不希望整份重排时）。
> 两条路都**禁止**用普通编辑器 / 通用 Edit 工具改 xwl —— 会写成裸 LF。

## 三分钟上手

```bash
git clone <this-repo> ~/.workbuddy/skills/webbuilder-xwl-patch   # 或直接把目录拷进去

# 造新文件（内置设计器真实顶层键序，不需要种子文件）
python scripts/xwl.py new wb/modules/<模块>/myPage.xwl --kind page --title "我的页面"
python scripts/xwl.py new wb/modules/<模块>/xxxSql/queryXxx.xwl --kind sql --title "出库单查询"
python scripts/xwl.py folders wb/modules/<模块>/myPage.xwl --register   # 登记（否则设计器里看不到）

# 改已有文件：0 check 基线 → 1 paths 拿路径 → 2 --dry-run → 3 --backup → 4 check 复核 → 5 diffguard
python scripts/xwl.py check     page.xwl
python scripts/xwl.py paths     page.xwl                            # 改 SQL/数据源时；其余改动用 dump 看层级
python scripts/xwl.py patch     page.xwl --ops ops.json --dry-run
python scripts/xwl.py patch     page.xwl --ops ops.json --backup
python scripts/xwl.py check     page.xwl
python scripts/xwl.py diffguard page.xwl                            # 有没有把多行内容悄悄压平？
```

> 最后一步补的是**唯一有自动化防线**的静默损坏：把「反斜杠 + 换行」直接删掉之后，
> 文件依然是合法 JSON、`check` 全绿、`node --check` 也可能返回 0，只有**相对 git 基线**才看得出。
> 它默认只告警；要让它拦住（CI / pre-commit）加 `--strict`。

一次完整的实操（新建页面 + 配套 SQL + 挂事件 + 校验 + 登记）见
[`references/walkthrough.md`](references/walkthrough.md)；
可直接跑的最小示例见 [`examples/README.md`](examples/README.md)。

## 工具速查

**参数与各自的边界/警告见 [`SKILL.md`](SKILL.md) §4.1，本表只给一句话作用。**

| 子命令 | 干什么 |
|---|---|
| `new <out.xwl> --kind page\|sql [--from-json F]` | **从零生成**：内置设计器真实键序的骨架（页面 / SQL 载体）；默认拒绝覆盖已有文件 |
| `patch <file> --ops ops.json` | **结构级编辑（默认方式）**：只给值/子树，按设计器算法重建整份文件 |
| `folders <path> [--register]` | `folder.json`（设计器导航树索引）一致性检查（**只读**）；`--register` 才写（只接文件路径） |
| `check <file...>` | 七项校验：格式五项 + 事件 JS `node --check` + **itemId 重名分级**；任一 FAIL 返回非 0 |
| `diffguard <path...>` | **相对 git 基线检测「多行内容被压平」**（`check` 查不出的那类静默损坏）；默认只告警，`--strict` 才阻塞 |
| `itemids <file>` | **itemId 重名报告（只读）**：分级 + 候选清单 + 建议改名；`--suggest` 出 ops 草稿 |
| `paths <file>` | 列出 `sql` / `totalSql` / `serverScript` / `url` 四类字段的位置（含 `@itemId` 写法） |
| `params <page.xwl>` | 核对「参数控件 → store → SQL」传参链路（标出 `out` / `params` 两条通路） |
| `sqlrefs <file>` | 校验 SQL 片段里 `{#名字#}` 与 `serverScript` 是否自洽 |
| `schema [<type>] --controls <…/controls.json>` | 查控件注册表：`--tree` 面板分组树、`--list` 控件 id、`--skeleton` 设计器同款骨架 |
| `expand <file>` | 单行 → 设计器同款多行（含语义等价比对） |
| `edit <file> --old-file O --new-file N` | 文本级安全替换（**例外**手段） |
| `dump` / `sql` / `events` | 解析后美化输出 / 抽 SQL / 导出事件 JS |

## 目录结构

```
webbuilder-xwl-patch/
├── SKILL.md                  # **入口文档**：适用边界、格式硬规则、处理流程、引用方式、SQL、itemId
├── README.md                 # 你正在看的这页：定位 + 上手 + 速查
├── CHANGELOG.md              # 变更历史（倒序，含每一步的依据与实测数字）
├── metadata.json             # 能力与边界声明（SkillHub 打包 / 平台评测读它）
├── test-prompts.json         # 典型 prompt（供 skill 评估用）
├── examples/                 # 可直接跑的最小示例（示例 .xwl 由 new 现场生成）
├── references/               # 参考材料（每份的条数与作用见 SKILL.md 首页那张索引表）
└── scripts/
    ├── xwl.py                # 全部子命令（纯标准库，零依赖）
    └── selftest.py           # 内置样本自检：python scripts/selftest.py
```

> 各文件的**条数/数字不在这里重复**（两处维护必然漂移）—— 每份文件自己的开头写着它的条数，
> `SKILL.md` 首页那张表是它们的索引。

## 依赖与许可

- **Python 3.9+**（纯标准库，零第三方依赖）
- （可选）**Node.js** —— 仅用于事件 JS 语法校验；缺失时自动降级为警告。
  可用 `--node <path>` 或环境变量 `NODE_BIN` 指定。

MIT，见 [LICENSE](LICENSE)。
