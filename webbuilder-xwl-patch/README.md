# webbuilder-xwl-patch

[![selftest](https://github.com/yfwang0731/skill-webbuilder-xwl-patch/actions/workflows/selftest.yml/badge.svg)](https://github.com/yfwang0731/skill-webbuilder-xwl-patch/actions/workflows/selftest.yml)

处理 **WebBuilder（wb）平台 `.xwl` 定义文件**的 Agent Skill ——
**用结构级 `patch` 改 xwl，不碰文本层。**
面向**支持 Agent Skills 规范**的客户端（Codex / Cline / CodeBuddy 等）；WorkBuddy 同样可用 ——
把 **`webbuilder-xwl-patch/` 运行目录**放进它读取的 skill 目录即可，装法见 [`references/distribution.md`](references/distribution.md)。

`.xwl` 看起来像 JSON，但**不是严格 JSON** —— 磁盘上是「字面反斜杠 + 真实换行」的多行字符串。
直接拿编辑器改，**第一刀就会把文件改坏**（运行时解析失败、页面白屏）。

它能干两件事：**改**已有文件（结构级 `patch`）、**造**新文件（`new`，内置设计器真实键序的骨架）。

> **范围**（放最前面，因为它决定你要不要往下读）：只看 `.xwl` 文件本身 —— 格式、编辑、校验、抽取。
> **不含**菜单注册（`WB_MENU`）、后端代码、模块打包、`target/` 部署副本同步；
> **判定口径 = 单 webapp（单个 wb 根）** —— 引用解析只在**本根**内找；实测多模块工程的 `target/` 展开产物
> **只含其中一个模块**的 xwl（各 webapp 独立部署），所以"在别的 webapp 里找得到"≠"本根可用"；
> 也**不适用于**其他低代码平台的页面定义、`.vue`、普通 `.json`。

## 安装

```bash
npx skills add yfwang0731/skill-webbuilder-xwl-patch --skill webbuilder-xwl-patch -g -a codex
```

> 仓库根是**开发资产**；安装器会自动发现 `webbuilder-xwl-patch/` 子目录、只复制这一层，无需 `--full-depth`。
> 单技能时 `--skill webbuilder-xwl-patch` 可省略。

装到哪个目录取决于 `-a`，而 **CLI 的 agent 表里没有 `workbuddy`** ⇒ WorkBuddy 请**手工装**：
把目录放到 `~/.workbuddy/skills/<name>`。另两条命令（`update`／`remove`）、「`check` 与 `update`
是同一套实现 ⇒ 执行前假定它会写」这条注记、手工安装细节与环境依赖，全在
[`references/distribution.md`](references/distribution.md)。
⚠️ **别往安装目录写** ops／业务 `.xwl`／备份／临时夹具 —— 它会被 `update` 覆盖，也可能只读。

## 核心工作方式：结构级 `patch`

**不碰文本层。** 你只提供「值 / 子树」，工具按**设计器自己的算法**重建整份文件 ——
续行符、转义、缩进、换行全部由序列化器产出。

```bash
# 改标题 + 给工具栏加一个带多行 JS 的按钮：只写"要什么"，不写"怎么排版"
export SKILL_ROOT="$HOME/.agents/skills/webbuilder-xwl-patch"   # 换成你实际的安装目录
python "$SKILL_ROOT/scripts/xwl.py" patch page.xwl --ops ops.json --dry-run   # 先看 diff
python "$SKILL_ROOT/scripts/xwl.py" patch page.xwl --ops ops.json --backup    # 确认后落盘
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
（`op` 支持 `set` / `insertKey` / `insert` / `append` / `delete`）。

### 为什么这条路可靠

- **格式错误在构造上不会发生** —— 不接触文本层，就没有"改坏格式"这条路；**前提：候选通过等价比对／可解析校验**；`edit` 走文本层，候选解析不通过即拒写（`rc=2`）。
- 重建算法从设计器源码**完整复刻**（`IDE.updateModule` = `org.json toString(1)` + 两次 `replaceAll`），
  并做过**回放校验**：把算法跑在样本工程既有的上千个 xwl 上，还原出的字节与原件逐个比对
  → 所以重排**不会顺带改动无关内容**，**diff 只含这次真正改的内容**（**`--indent`／`--eol` 能主动触发的重排**会扩大 diff；非规范源即使不带参数也会被规整，见 `references/measured-data-designer.md`）
  （在多行源页面上加一个带多行 JS 的按钮并改标题，diff 仍只覆盖本次实际改动）；
- 写盘前强制「**重新解析后与改后对象的规范化文本一致**」的等价比对（**含键序与值类型**：`1` / `1.0` / `true` 互不通过），对不上**中止不写**。

> 文本级 `xwl.py edit` 只是例外手段（改一小段文本、又不希望整份重排时）。
> 两条路都**禁止**用普通编辑器 / 通用 Edit 工具改 xwl —— 会写成裸 LF。

## 三分钟上手

```bash
# 先设变量：SKILL_ROOT=本 skill 安装目录（把路径换成你的实际值）
export SKILL_ROOT="$HOME/.agents/skills/webbuilder-xwl-patch"

# 造新文件（内置设计器真实顶层键序，不需要种子文件）；<模块> 换成你的业务模块目录
python "$SKILL_ROOT/scripts/xwl.py" new wb/modules/<模块>/myPage.xwl --kind page --title "我的页面"
python "$SKILL_ROOT/scripts/xwl.py" new wb/modules/<模块>/xxxSql/queryXxx.xwl --kind sql --title "出库单查询"
python "$SKILL_ROOT/scripts/xwl.py" folders wb/modules/<模块>/myPage.xwl --register   # 登记（否则设计器里看不到）

# 改已有文件：0 check 基线 → 1 paths 拿路径 → 2 --dry-run → 3 --backup → 4 check 复核 → 5 diffguard
python "$SKILL_ROOT/scripts/xwl.py" check     page.xwl
python "$SKILL_ROOT/scripts/xwl.py" paths     page.xwl                            # 改 SQL/数据源时；其余改动用 dump 看层级
python "$SKILL_ROOT/scripts/xwl.py" patch     page.xwl --ops ops.json --dry-run
python "$SKILL_ROOT/scripts/xwl.py" patch     page.xwl --ops ops.json --backup
python "$SKILL_ROOT/scripts/xwl.py" check     page.xwl
python "$SKILL_ROOT/scripts/xwl.py" diffguard page.xwl                            # 有没有把多行内容悄悄压平？
```

> `<模块>` 是**你的业务模块目录名**占位（形如 `wb/modules/<模块>/`），跑前换成实际值；这是业务路径、随工程变，
> 不是脚本入口。上面第一条 `new` 直接照抄即可跑（先 `export SKILL_ROOT` 指向安装目录）。
> PowerShell 把 `export SKILL_ROOT=...` 换成 `$env:SKILL_ROOT = "...";`，其余命令里的 `"$SKILL_ROOT/…"` 换成 `"$env:SKILL_ROOT/…"` 即可。

> 最后一步补的是**唯一有自动化防线**的静默损坏：把「反斜杠 + 换行」直接删掉之后，
> 文件依然是合法 JSON、`check` 全绿、`node --check` 也可能返回 0，只有**相对 git 基线**才看得出。
> 它默认只告警；要让它拦住（CI / pre-commit）加 `--strict`。

一次完整的实操（新建页面 + 配套 SQL + 挂事件 + 校验 + 登记）见
[`references/walkthrough.md`](references/walkthrough.md)；
可直接跑的最小示例见 [`examples/README.md`](examples/README.md)。

## 工具速查

15 个子命令（`new`/`patch`/`check`/`diffguard`/`itemids`/`paths`/`params`/`sqlrefs`/`folders`/`schema`/`expand`/`edit`/`dump`/`sql`/`events`）的**逐条作用与边界**见
[`references/distribution.md`](references/distribution.md) §八「工具速查」，以及 `SKILL.md` §4.1 的参数细则 —— 本页不重复。

## 目录结构

```
webbuilder-xwl-patch/
├── SKILL.md                  # **入口文档**：适用边界、格式硬规则、处理流程、引用方式、SQL、itemId
├── README.md                 # 你正在看的这页：定位 + 上手 + 速查
├── CHANGELOG.md              # 变更历史（倒序，使用者向：哪一版改了什么、升了要注意什么）
├── metadata.json             # 能力与边界声明（SkillHub 打包 / 平台评测读它）
├── test-prompts.json         # 典型 prompt（供 skill 评估用）
├── examples/                 # 可直接跑的最小示例（示例 .xwl 由 new 现场生成）
├── references/               # 参考材料（每份的条数与作用见 SKILL.md 首页那张索引表）
└── scripts/
    └── xwl.py                # 全部子命令（纯标准库，零依赖）
```

> **`xwl.py` 是单文件程序，长不等于残缺**：它是纯标准库零依赖的**一个**文件，以 shebang 起、
> 以 `if __name__ == "__main__":` 收尾，全部子命令都在里面。判断是否完整看三条当场可复算的依据：
> `python "$SKILL_ROOT/scripts/xwl.py" --help` 列全 15 个子命令、`python -m py_compile …/xwl.py` 通过、
> 按 `examples` 跑一次 `check` 得 `ALL OK`。完整说明见 [`references/distribution.md`](references/distribution.md) §"如何确认程序完整"。

> `scripts/selftest.py`、`scripts/privacy_scan.py`、`scripts/privacy_patterns.example.json`、`tests/` 只存在于
> **源码仓根/开发树**，不属于安装副本；维护者自检见 [`references/distribution.md`](references/distribution.md)。
> 各文件的**条数/数字不在这里重复**（两处维护必然漂移）—— 每份文件自己的开头写着它的条数，
> `SKILL.md` 首页那张表是它们的索引。

## 依赖与许可

三件事分开算（缺哪件、后果不同）：

- 跑 `xwl.py` ⇒ **Python 3.9+**（纯标准库，零第三方依赖）；
- 事件的 JS 语法校验（`check` 第 ⑥ 项）⇒ **Node.js 可选** —— 缺失时该项降级为警告、少守一层，
  可用 `--node <path>` 或环境变量 `NODE_BIN` 指定；
- 用 `npx skills` 装／更新 ⇒ **Node ＋ npm**，这条**不是可选**。

MIT，见 [LICENSE](LICENSE)。
