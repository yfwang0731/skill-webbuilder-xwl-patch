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

## [1.8.3] - 2026-11-11

说明与账本收口（patch）：**无新子命令或参数**。

① `diffguard --strict` 的帮助、`SKILL.md`、判据注释、套件概述与测试提示统一为现行严格口径：疑似压平优先 `rc=1`；仅检查未完成 `rc=2`；全部跳过 `rc=2`；部分跳过只记 `[note]`。

② `params --strict` 的帮助、metadata 现行能力说明与测试提示对齐现行退出码；删除过时的“同名同义”和规模耗时表述，既有评测提示、`CHANGELOG` 历史段与 `update_history` 历史条目保持原样。

③ 删除正本无调用的基线读取、实时自检模块和换行检测辅助函数；两份运行封装保持独立。

④ 维护说明对齐非 UTF-8 入口名单、`loader=True` 写后回读、行首标记、基线更新入口、依据层与豁免面份数，以及缺 `node` 且 `--require-all` 时记未完成的状态口径；不改变运行行为。

⑤ 语料文件数、样本大小与命令耗时只由 `measured-data*.md`、`CHANGELOG`、`update_history` 和基线文件承载。17q 数字禁令以定向负例先红后绿验证，并修复“千字节”等中文复合大小单位重复命中基础“字节”的问题；能力边界“未验证过 1 MB 以上”保持。

## [1.8.2] - 2026-11-10

`params` 供给判定：请求身份隔离与直属 beforeload 有效键（patch）：**无新子命令或参数**；默认/strict 码值继续按既有矩阵（已确认缺参默认 `rc=0`、`--strict` `rc=1`；仅未核对在 `--strict` 下 `rc=2`；读取失败按既有规则），不新增码值、不放宽判定。

① 请求身份隔离：供给结论按请求身份分别判定。请求身份由页面结构位置、事件或配置字段、静态调用位置组成，store 以节点身份计；SQL 物理路径只用于读取该载体的需求，不再充当请求身份，也不再把同载体上的多次请求并成一份。同一 SQL 的不同 store、同一 store 的不同 load、同一 SQL 的不同 `Wb.request` 互不补齐；同一请求内 `out`、`params` 与所属 store 配置仍按既有规则组合。`autoLoad=false` 或未配置既不证明永不加载，也不证明请求已经发出。注册名歧义或附着点未知时记入未核对，不任选一个；无关请求的动态供给不能把本请求的确定缺参遮成齐全。`#56` 的 SQL 侧需求段仍按物理载体合并打印一次并保留 `（同载体 ×N）`，逐请求结论写在交叉核对。

② 直属 beforeload 的有效键：store 静态 params 只有在直属 beforeload 之后仍然保留，才算该请求的已证明供给。按已核实的平台语义计算（`Ext.apply(target, config, defaults)` 中 `defaults` 先写、`config` 后写并覆盖同名键；`Store.load` 中 `beforeload` 的第二形参为当前 `operation`，其后 proxy 读取同一 `operation.params`）：整体赋值替换键集合，固定键追加只保证该键存在，`Ext.apply`／`Wb.apply` 按参数顺序并入字面量键，连续操作按源码顺序计算——先追加后整体覆盖不保留旧键，先覆盖后追加可恢复指定键。只证明键的来源与保留，不证明值非空、业务合法性或请求实际发出。

③ 已知边界：只处理直属 beforeload；动态整体覆盖、条件追加、语义未核实的辅助函数与别名按受影响请求和参数记未核对。跨事件可达性、外部触发、reload 历史参数推理、值合法性与 SQL 类型校验不在本版范围。结论来自静态源码核对，不声称平台运行期或全工程有效。

## [1.8.1] - 2026-11-09

检查正确性与说明收口（patch）：**无新子命令或参数**。`params` 与 `sqlrefs` 的供给算法和既有码值不扩张。

① 数字形态估算只统计有效对象正文中的数字值 token，按方向性多重集差显示；`0` 只表示本方向无差异，不证明语义等价或位置对应。

② `params --upstream` 的早返与正常汇总出口直接消费扫描返回的真实相对路径，普通扩展名与合法双后缀文件均不重复追加扩展名。

③ `SKILL.md`、FAQ、CLI 帮助与测量说明对齐 `params --upstream` 的默认/strict 码值矩阵：读取失败、已确认内容失败并存和仅无法静态核对分别按真实结果汇总。strict 返回 `1` 时仍并列报告读取未完成；上游候选不加入已证明供给，未定位模块根明确提示跳过。

④ `sqlrefs` 的说明统一为**本文件内静态集合近似**：`已提供` 表示字面量 `request.setAttribute(…)` 名字命中本文件静态集合，不证明调用必经执行、消费前时序、分支或跨 module 生命周期有效。

⑤ `sqlrefs` 对有适用内容的 OK、已确认内容 FAIL 和依赖读取失败各输出一次证明边界提示，位置在具体诊断之后、统一结果行之前；主输入无法读取或解析、无适用内容时不输出。剔除新增提示后，原 stdout、末行结果和 rc 保持不变。

⑥ `references/checklist.md` 增加给定对象上的任务级独立验收指引：用任务开始基线、最小允许路径和业务触发条件完成保护区结构比较与事件生命周期演练，并明确缺基线、零对象、定位歧义或运行证据不足不能包装为整体通过。关联范围深度、验证调度和任务级完成证据仍由上层范围机制决定。

## [1.8.0] - 2026-11-07

自检必需范围与成果物覆盖（minor）：**新增自检契约，不是新的 `xwl` 子命令**。

① `selftest` 增加 `--require-all` 与 `--profile package|development`，二者必须同时给出。与 `--fast`、`--only`、`--list-blocks`、`--allow-nogit` 同用为用法错。每块给出完成状态：通过、失败、未完成、不适用、未选择，并带理由和子检查状态。`package` 与 `development` 都把 diffguard 建临时仓库失败、Node 缺失下的 JS 档、`docs` 的 Git 守卫族降级记为未完成。门禁未完成、缺配置、协议错误为退出码 2，断言失败为 1。普通档不加该开关时，退出码仍只看断言失败。

② 成果物检测另记三个维度：调用成功、对象合格、覆盖完成。三者可同时成立，同一结果可以是对象合格且覆盖未完成。同一快照未变更时复用并说明；文件或依赖变更后旧证据失效。调用方声明该次 JS 必需且未跑时，覆盖为未完成，最终结论不得写合格。不声明必需时，`check` 缺 `node` 仍只提示，退出码不变。

## [1.7.15] - 2026-11-06

自检汇总区分与套件拆分：**无新子命令、无新参数**。

① selftest 汇总能区分全量通过、部分未跑和块级未执行。分母固定为注册块数；未跑和未执行不改变退出码。`--only` 的成功与失败末行都带范围。

② 12 个 xwl 块断言实现迁到源码仓 `tests/selftest_suites/`。主入口保留 13 个稳定块 ID、调度和汇总；`--only`、`--jobs`、`--list-blocks` 的对外协议不变。长度守卫改为量真实实现。`tests/` 仍只在源码仓/开发树，不属于安装副本。

