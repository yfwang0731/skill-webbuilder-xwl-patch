# Changelog

`webbuilder-xwl-patch` 的全部重要变更。格式参考 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号**参考** [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。**按时间倒序**，日期为 `YYYY-MM-DD`。

>
> **关于本文件里的数字**：凡标「实测 / 复算」的，都是把工具跑在样本工程（`wb/` 下 2777 个 `.xwl`）
> 上得到的，可用 `scripts/selftest.py` 与 `scripts/xwl.py` 的各子命令复现。
> 「回放校验」指**把算法跑在既有文件上比对字节**，与某一次编辑的结果无关。
>
> **规模数的口径**：主口径 ＝ **8 个 wb 根 `modules/**`、排除 `target/`**；精确值、复算命令与语料快照指纹见
> `references/measured-data-skeleton.md` 第十节（**2026-10-19 复采**）。正文里的规模数分三类、**都不回改**：
> ① 同口径的**时点序列** `24957` → `24986` → `25161`；② 已认定**错误**的 `25250`（复算应为 `24957`）；③ 另一口径 `25 077 页`（**页数**、剪枝口径）。⛔ 别把三类当成"同一统计的多个版本"。

---

## [1.10.2] - 2026-11-26

交付收口（patch）：**变 1 处**。`patch` 与 `new --from-json` 的 `--slot-check` 默认由 `warn` 改为 `error`，要保留旧行为加 `--slot-check warn`。只覆盖这两条写前检查，不覆盖 `edit` / `expand`，`check` ⑪ 不变。
- 随包样板 `ops-set-store-url.json` 的 Grid 直接 store 使用槽位名 `store`，空页样板在默认 `error` 下仍可跑通。
- 记录坐标键不足以按上下文收窄 ⑨，`checkOnly` 没有注册定义，设计器落点仍待项目侧核对。不改 ⑨ 检查器。
- 说明新文件用 `new` 与生成后的结构校验；无基线时 `diffguard` 给出跳过提示。
- 说明 SQL 整行删改走 `patch` 改 `configs.sql`，`edit` 不提供续行开关。
- 说明 `patch` 预演的大 diff 先区分对象树变更与格式重排。
- 清单补页面交付闭环，复用既有 `folders` 条件；部署、菜单和数据库仍由项目侧处理。
- 补直接父级断言与 `dump` 对照，以及 `insertKey` 定点插入和相邻键复核。
- 补工程外逐字节快照、事件与父级寻址、执行入口记录，以及「路径 + 问题种类」对照。

## [1.10.1] - 2026-11-25

页面运行与 SQL 交付指引（patch）：**无对外能力变化**。无新子命令、新参数、判定、退出码或文件副作用。

- 补充空字符串 `text` / `value` 进入 `ExtControl.processConfigs` 与 `charAt(0)` 路径的风险、静态 `check` 的证据边界和正常对照。
- 补充窗口 `app._X` 模板键、`initialize` / `finalize` 时序、改名或删除后的 `app.X` / `app._X` / `app.get()` / `app["X"]` 引用复核。
- 补充单选字典 combo 的 `keyName` 最小写法，区分字典身份、业务键、提交值与显示值；说明 `pickList`、URL store 与异步空初始数据的实际展开和回填核对。
- 将分页、业务 Top N、自管分页、`totalSql` 与二次切页规则收敛到 `sql-fragments.md`，其他文档只保留指针；补充当前应用模块根、SQL 别名和查询投影核对。
- `layout.md` 区分 Grid 内 `summary` 与同一 `border` 父层的独立汇总；`js-api.md` 补充查询生效值、失败、旧响应晚到、按钮状态、`Wb.prompt` 原始输入和按模块核对的选择窗口短例。

## [1.10.0] - 2026-11-25

固定槽位、重复供给与多行查询（minor）。

- `grid`、`tree`、`propertygrid` 的固定槽位统一按父上下文识别。双 Grid 可各有一套 `store/tbar/columns`，同父级重复供给、错名槽位与同 Grid 完全重复列或重复列 `itemId` 由 ⑪ 提示。`itemids` 与任务级验收器复用同一判据；合法固定槽位不再生成改名建议，自主命名控件仍按原注册键规则处理。
- `patch` 与 `new --from-json` 新增 `--slot-check warn|error`，默认 `warn`。写前比较实际父对象身份与问题数量，只拦截本次新增问题；`error` 在目标与备份写入前返回 `1`，预演与实写同判。诊断保留 `@父/@槽位` 短名，并增加 `children[下标]` 完整结构路径以区分同名父对象。`new --from-json` 从输出位置发现 `controls.json`。
- `schema tree --skeleton` 改为 `treestore(store)`；双 Grid 示例分别通过父级路径追加列。布局文档补充 Grid 与 Panel 的 `dockedItems` 多行结构、两行字段的同次 `params`、边框、自然高度与字段宽度指导。
- 文档同步 ⑪ 的槽位供给、重复列和写前门禁口径；`edit` / `expand` 仍不新增槽位门禁，`check --strict` 仍只升级 ⑪。

## [1.9.3] - 2026-11-24

提交面内部编号清理（patch）：无新子命令或参数，命令参数、退出码、公开 JSON 形状与文件副作用不变。

- 活跃运行源码、公开文档与测试中的内部事项号、评审/案例号、轮次/批次号、版本化 helper 和用户输出内部短号改为行为名称。
- 文档守卫改用 `docs.<domain>.<rule>` 语义 ID；基线、登记表和现有断言同步，业务控件值、技术名、用户寻址和历史记录保持不变。
- 新增单一防回流守卫。版本化机器名从 SKILL 版本、metadata 当前版本与历史、CHANGELOG 动态派生；活跃提交面命中内部身份即失败。

## [1.9.2] - 2026-11-23

现役口径冲突统一修复（patch）：无新子命令或参数。

- 运行契约按命令和阶段收敛：`check` 的文件级 BOM、缺失、不可读为 `rc=1`；`patch/edit/expand` 的 BOM 或读取失败为 `rc=2`；坏 `--controls` 总码为 2 且 ⑪ 照常执行。`check --strict`、`params --strict`、`sqlrefs` 的边界分别说明。
- `params --list-fields` 对显式坏或缺失 `--controls` 在 stderr 给出降级说明，stdout 清单、单次读取与 `rc=0` 保持；`folders` 增加直接父索引检查，缺父索引默认只提示。
- `params` 支持已取证的 `app.<grid>.store.load/reload` 静态关联；事件 JS 引用过滤字符串、模板文字与注释，非标识符重名理由改用 `app.get(...)`／方括号访问。
- `events --outdir` 只在写入成功后宣称覆盖；`expand` 仅在忠实模式下承诺设计器布局，并报告候选与源文本是否逐字节相同。
- README 与 walkthrough 改为可执行的中性示例：按钮真实位于 `grid → toolbar → button`，querybar 使用内联本地 store，表格补齐四列与匹配 column。

## [1.9.1] - 2026-11-21

check 现役口径与计数守卫（patch）：**无新子命令或参数**，`check` 判定与退出码不变。

- 现役说明统一为**十项校验** = **8 项判定 ＋ 2 项默认提示**：⑧ 加载链完整性始终只提示、不进 rc；⑪ 错槽位默认警告、`--strict` 升级为 `[FAIL]` 并进 rc。`--controls` 的 ⑨ 仍是可选附加面，不计入十项；注册表读取失败仍照常执行 ①–⑧⑩⑪。
- `metadata.core_capabilities`、CLI 模块说明与 `check` help、`test-prompts` 的 id1/12/18/21 同步到上述口径；题号、题干和其他评测正文不变。
- 既有“自称数字”守卫扩到 `metadata.core_capabilities`、`xwl.py` 模块说明与 `check` help、`test-prompts.expected`，并逐切片识别已登记句式错数、正确句旁混错句、缺失、读取失败、空结构/容器、零命中及目标 expected 空或无声明。
- 判据只覆盖 **1–10 的有限登记句式**；历史记录段精确豁免，格式五项等合法分项不误报。该机制不声称覆盖所有自然语言或所有工程。

## [1.9.0] - 2026-11-21

保留名与错槽位（minor）。使用者装上后能看到三类变化：重名建议不再改槽位 `itemId`，`check` 新增 ⑪，`schema --skeleton` 给出槽位占位。

- 保留名是父 `type`、子 `type`、子 `itemId`。命中后不进 `check` ⑦，也不再建议改 `itemId`。页根 `toolbar` 与 module/folder 根上的 `store` 仍按普通重名。
- `check` ⑪ 默认 `[warn]`、不进 rc。`check --strict` 才把错槽位判 `[FAIL]`。`patch` / `edit` / `expand` 写盘后自检仍只跑 ①–⑥。
- `schema grid --skeleton` 的 `children` 含 `store`、`tbar`、`columns`；`tree` 只含 `store`、`tbar`。`column` 骨架不塞空 `editor`。无 `--skeleton` 的输出不变。

## [1.8.6] - 2026-11-13

工作区根治：契约登记、数据契约与老文件校正、统一扫描器与守卫等价、规则正本与宿主接入、文档精简、构建链接线、归档窗口（patch）：**无新子命令或参数**，不改 `xwl.py` 任何字节（`--help` 15 个子命令逐字节不变）。版本位依据：本次改动全为文档／工具／契约／规则／JSON 整理，使用者装好 skill 后**感知不到新的调用行为或输出**（`plans/30` §1.1 尺子「能感知 ⇒ 至少 minor；不能 ⇒ 至多 patch」），故判 **patch**、段 27、单一版本不拆号。

### 数据契约与校正

- 新增 `skill/contracts/registry.json` 契约登记表，覆盖各数据块序类型与绑定规则；老文件按统一 schema 校正块一致性、序与形态。
- 校正只改排列与形态、不改语义：`items.json` 的 `(id, kind, status, segment)` 与 `events.jsonl` 条数 before/after 逐项 **diff＝0**。
- 4.7 十六条常驻负例全族（含 G1–G6 具名负例）在统一契约扫描器下全绿，各注入一次命中对应 ID 并转红。

### 统一扫描器与守卫等价

- 形状白名单与绑定解析上线；块名集合 before/after **差集＝0**（`17*` 块名保留，不删不并）。
- 旧负例集与「新写法」注入集各跑整块 `--require-all`，两组均 `rc≠0`；note 不出现在门禁输出。

### 规则正本与宿主接入

- `AGENTS.md` 五处目标条文逐件展示完整内容并取得确认后写入（单一可维护正本、派生不作为第二份正本、授权边界、临时件位置、四处版本一致性由构建期保证）。
- gate 两侧 `settings.json` hooks 段回读同值；单侧改 → 「应拦／应放」各一条注入，附 `gate/log/gate-blocked.log` 新行；单边修改无两侧同步记录即判未生效。

### 文档契约与精简说明

- 包内副本篇数 ≤20、说明面 LF 行数 ≤6 000、跳转 ≤30、包外链接＝0（口径按 `plans/20-验收基线.md` 第二章）。
- 精简与归位只改说明面，不新增可调用行为或输出行。

### 工具、构建链与分发面

- `generate` 四路径接线（本地／CI／release 副本／打包），`derived-values.json` 作为派生条目进包；`collect()` 实际集与 `file-manifest` 双向差集＝空；基线预算超阈报红、未超不报。

### 归档窗口

- `CHANGELOG.md` 旧段逐字节迁入 `CHANGELOG-archive.md`（迁前迁后 md5 与字节相等，逐字节冻结），活层保留 12 段；`archive-audit` 一致。
- 索引由注册表派生，LAYOUT 分区与月度索引同步。

---

## [1.8.5] - 2026-11-12

文档/示例/打包/发布流程修复与任务级成果物验收执行器（patch）：**无新子命令或参数**，不改 `xwl.py` 任何字节。

① **FAQ 条数一致**：`references/faq.md` 首段「按四组归类」声明 **24 → 25 条**（实计 `^\*\*Q：` ＝ 25）；`scripts/selftest.py` 的「自称数字」判据 **新增行首锚 claim 形态** `(?m)^\*\*(\d+)\s*条按四组归类\*\*` 抓 `faq.md` 自身声明数、与实计比对，不等即红。双负例：声明数≠实计 → 红；行内非行首的 `**N 条按四组归类**` 不计入、不误红。

② **LICENSE 归一 + 派生进包**：`git mv` 到**仓库根 `skill/LICENSE`**（唯一正本，仓库根导航加 `[LICENSE]` 行）；`webbuilder-xwl-patch/README.md`、`references/distribution.md` 引用改指根 `LICENSE` 并明示「SkillHub 包不随附该文件」。打包 `collect` 改为**从根 LICENSE 派生 `LICENSE.md` 进包**（写 zip 时即时读取、不落仓、不持久化；`DROP_RULES_VERSION` 1→2 使旧缓存失效），zip 内 `LICENSE.md` 字节 == 根 LICENSE 字节（逐字节）。`release/scripts/selftest.py` 的 LICENSE 断言**反向改**（`LICENSE.md` 在包内、无扩展名 `LICENSE` 仍被排除），并新增**缺件负例**（临时移走根 LICENSE → `collect`/`doctor`/`zip` 报「缺 LICENSE」缺件、rc=2，非静默）。

③ **示例与 README 修复**：
- wave3：`examples/README.md` 的压平示范由**破坏性单行 `python -c "re.sub(r'\\\r?\n',…)"`**（经 universal newline 会把整份 CRLF 改写成 LF、换行被破坏）改为**字节级安全脚本**（只删「反斜杠+换行」续行对、其余字节含 CRLF/LF 原样保留），并写明正当做法一律走 `xwl.py patch`/`edit`（⛔ 不硬塞单行正则、不绕过 xwl.py）；对 CRLF 源跑换行不被破坏、`diffguard` 仍精确抓压平。
- wave2：`references/distribution.md` **删净 §八 工具速查整节**（不留指针）；速查表**归位** `README.md`「## 工具速查」（标题＝真表，移不复制）；README 风格统一（目录结构瘦身为纯树、`path`/`@itemId` 解释压缩、上手后 `>` 块合并），字节/LF **143 行 ≤150**（`--only docs` 的 3814 判定，阈值不抬）；⛔ 全仓除 CHANGELOG 外不再引用 `distribution.md §八`。
- wave1/4：两条规则落 `references/workflow-notes-guards-maintenance.md` 与 `plans/40`（⛔ 不动 AGENTS.md）——**①「整块文档守卫必须真跑才算通过，函数级替代整块输出不构成通过证据」②红线「判据先于产出：改产出前必须先有可失败的判据」**。

④ **`--changelog` 硬闸（防复发）**：`release/scripts/release.py` 与 `skillhub_publish.py` **两层都改为缺 `--changelog` 直接 fail**（作用域仅 `target` 含 skillhub 时生效，纯 github 不误拦），⛔ 无默认模板、无 `--allow-empty-changelog` 后门；`release/scripts/selftest.py` 新增缺值拒绝负例（fail 而非 note）与纯 github 不误拦正例。

⑤ **任务级成果物验收执行器（ITEM-1205）**：落 `skill/tests/task_acceptance.py`（selftest 家族，**不进 scripts/、不进分发包**），产出**机器可读 JSON + 人读摘要**；验收关联按 `.xwl` 页面关系**最多递归一层**、只做**静态应检清单**（不启 Tomcat）；golden 夹具（脱敏样本 + 黄金应检清单，候选待验收审定）给**覆盖率/精确率**；**三负例**——零对象（空任务→未执行/不通过，不假绿）/缺基线（无 git→UNVERIFIED，非通过）/歧义定位（itemId 重名→AMBIGUOUS，非任选）。以三证证明不改使用面（顶层 + 15 子命令 `--help` 改前/改后 diff 全空、既定子集 rc 全部 0、未改 xwl.py 一字节）。

> **更正 v1.8.4 在 SkillHub 的变更说明**：SkillHub 上 v1.8.4 曾以 “Initial release” 作为变更说明——该说明**不代表 v1.8.4 的真实内容**，且**历史已发布说明不可覆盖、不可改动**（平台侧已固化）。v1.8.4 的真实变更摘要为：**示例可复制即跑、现行面口径收敛、文档守卫补「照抄即执行」判据**（patch，无新子命令/参数，不改 `xwl.py`）—— 详见本文件 [`[1.8.4]`](#184---2026-11-11) 段。本更正**不重发 v1.8.4**、只在此登记事实，供读者对照。

## [1.8.4] - 2026-11-11

示例可复制即跑、现行面口径收敛与文档守卫补「照抄即执行」判据（patch）：**无新子命令或参数**，不改 `xwl.py` 任何字节。

① **示例可复制即跑**：`SKILL.md`、`README.md`、`examples/README.md`、`references/*` 里所有写命令的围栏块，把「`<skill根>`／`<你的临时目录>`／`<本skill目录>`／`<样例文件名>`」这类照抄即挂的占位写法，改为「先设 `SKILL_ROOT`／`TMP_DIR` 变量再引用」的可复制写法，并给 bash 与 PowerShell 双版；`examples/README.md` 的把多行 JS 压平的 POSIX heredoc（`python - <<'EOF'`）改为单行 `python -c`、双平台可跑。照抄任一被改围栏块的首条命令即可实跑（`new`→`rc=0`；含 `check`→`rc=0`）。

② **现行面口径收敛**：现行面（`SKILL.md`／`README.md`／`references/{distribution,faq,js-api,sql-fragments,walkthrough,workflow-notes-guards-maintenance}.md`）里会过期的语料规模数、文件大小数与样本占比，改为「形状描述 + 采集命令」，不再写死数值；确需引用处只注「历史口径见 `CHANGELOG.md`」。⛔ 历史记录类（本文件历史段、`metadata.update_history` 历史条、`references/measured-data*.md`）保持原样。

③ **程序完整性说明**：`references/distribution.md` 增「如何确认程序完整」小节、`README.md` 增一段简述——核心程序是单一 `scripts/xwl.py`（纯标准库零依赖），以 shebang 起、以 `if __name__ == "__main__":` 收尾，判断完整性看 `--help` 是否列全 15 个子命令、`python -m py_compile` 是否通过、跑一次 `check` 是否 `ALL OK`；⛔ 不新增 `--version`／入口脚本。

④ **文档守卫补「照抄即执行」判据**（`scripts/selftest.py` 的 docs 块，并入既有 `_check_prompt_cmds` 同块，⛔ 不改 `--list-blocks` 协议）：原判据 `_PROMPT_CMD_RE` 把 `<占位>/scripts/xwl.py` 前缀整段吃掉，只把 `new <占位路径>` 交给 argparse ⇒ **完全不可照抄的命令被判绿（假绿）**。新判据把脚本路径 token 单独捕获，含尖括号占位即判红；`$SKILL_ROOT`／`$env:SKILL_ROOT`／绝对路径／`scripts/xwl.py` 相对路径／`\` 续行等正确写法判绿、不误报。定向负例：注入占位路径样例，旧判据绿、新判据红；阳性对照 PASS，命中数＝注入数。

