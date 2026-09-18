# Changelog

`webbuilder-xwl-patch` 的全部重要变更。格式参考 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。**按时间倒序**，日期为 `YYYY-MM-DD`。

> **版本号怎么升**（本仓的判定尺子，严格按下面这条来，别凭"改动挺多"就升 minor）：
>
> | 升位 | 只在这种情况下 | 例 |
> |---|---|---|
> | **patch** `x.y.Z` | 修 bug、改文档、重构、加测试/CI、性能优化 —— **对外能力不变** | `1.2.0 → 1.2.1` |
> | **minor** `x.Y.0` | **新增对外能力**：新子命令、新参数、新输出、能被用户调用的新东西 | `1.1.0`（`itemids`）、`1.2.0`（`new`/`folders`） |
> | **major** `X.0.0` | **破坏性变更**：命令行为不兼容、产出格式变了、需要用户改用法 | —（至今没有过） |
>
> 反例（真踩过）：一次"文档大整改 + 修两个缺陷 + 性能优化"被错升成 `1.3.0` ——
> 里面**一个新子命令都没有**，按上表只该是 patch。判据不是"改了多"，而是"**对外能力有没有变**"。
>
> **关于本文件里的数字**：凡标「实测 / 复算」的，都是把工具跑在样本工程（`wb/` 下 2777 个 `.xwl`）
> 上得到的，可用 `scripts/selftest.py` 与 `scripts/xwl.py` 的各子命令复现。
> 「回放校验」指**把算法跑在既有文件上比对字节**，与某一次编辑的结果无关。

---

## [1.2.3] - 2026-09-18

**修 `edit` 的换行归一缺陷（其中一个会把文件写坏）+ 让「把多行拍平」不再静默。**

起因是核实 SkillHub v1.2.2 评测报告里的一条指控 ——
`errorHandling` 的评语：「多行源压成一行时没有任何校验能拦住（文档明确承认是静默语义损坏，
只能靠 git diff 发现）」。核实中发现这句话**比文档写得更严重**：不只是"文档承认拦不住"，
而是**工具自己在场时（`edit`）也会把多行静默拍平** —— 还返回成功、`check` 全绿。
顺带挖出两个换行缺陷，同一根因。

发布前又做了两条收尾：统一 `edit` 的「文件头 / `--help`」两处措辞；
并把 `expand --eol auto` 在无换行源上**回退 LF** 这条会真踩到的边界写进文档。

**无新增对外能力**（没有新子命令、新参数、新输出）⇒ 按上面的尺子是 **patch**。

### Fixed

- **`edit` 的锚点换行归一写死了 CRLF ⇒ LF 文件上跨行锚点永远匹配不到**。
  `normalize_eol()` 把 old / new 片段的换行一律转成 CRLF，而目标文本是**原样**读的 ——
  两者对不上就报「锚点出现次数: 0」，**看着像用户写错了锚点**（而文档还专门警告
  "锚点不唯一就中止，别用 `--expect` 绕过"，进一步把人推向自我怀疑）。
  实测：LF 文件 + 跨行锚点 → **必失败**；LF 文件 + 单行锚点 → 成功。
  **触发条件**：只在**含换行符的 LF 文件**上出现。实测样本工程 2780 个 xwl ——
  **1878 个全 CRLF、902 个是「单行且末尾无换行符」、0 个 LF** ⇒ 该工程**当前不触发**。
  但两个真实风险在：① skill 是通用资产，别的工程可能有 LF 文件；
  ② `expand --eol auto` 对「无换行的单行源」会产出 **LF**（实测：6532 B 的单行源 → 168 个 LF），
  而那 902 个正好都是这种文件 ⇒ **expand 之后工程里就出现了 LF 文件**，
  在它们上面做跨行替换就会踩到本缺陷。
  修法：`normalize_eol(text, eol)` 增加 `eol` 参数；`cmd_edit` 先读目标文件，按它**实际的**换行归一。
- **同一根因的第二个后果**：LF 文件 + 单行锚点 + **多行 new** 会把文件写成 CRLF/LF **混用**
  —— 锚点匹配成功、**文件已落盘**，走 `_post_check` 才发现 ② 换行混用 FAIL（为时已晚）。
- **`write_text()` 的 docstring 与实现不符**：写着「按 CRLF 落盘」，实际是**原样**落盘（不做换行转换）。

### Added

- **`edit` 现在会在「把多行拍平」时给 `[warn]`**：`old` 里的续行符比 `new` 多就提示
  「续行符从 N 个减到 M 个 —— 多行内容被拍平，换行会丢失（语义已变，`check` 查不出来）」。
  这是**唯一**能提示的地方 —— 只有 `edit` 手上同时有 old / new 两端；
  用编辑器 / 通用替换工具改的，工具看不到（而那才是绝大多数情况）。
- `edit` 对**换行混用**的目标文件会先给 `[warn]`（建议先修换行再替换）。

### Testing

- 断言 **65 → 66 项**：新增第 24 组「`edit` 的换行归一与拍平警示」，覆盖 5 个场景 ——
  LF 跨行锚点必须成功、LF + 多行 new 后必须仍是全 LF、CRLF 跨行锚点回归、
  拍平必须出现 `[warn]`、普通替换不得误报。
  **负向测试**：把归一化退回硬编码 CRLF → 报 3 项 FAIL；删掉警示块 → 报 1 项 FAIL；
  恢复后 66 项全绿且 `xwl.py` 逐字节还原。

### Documentation

- 同步「按目标换行归一」与「拍平会有 `[warn]`」到四处：`SKILL.md` 工具表 `edit` 行、
  `SKILL.md` §2.3 的「能不能压成一行」表与结论、`references/anti-patterns.md` 第 1 条、
  `references/faq.md` 的压行条。
- `xwl.py` 文件头的子命令清单修正过时说法（「保留 CRLF」→「按目标换行归一」）；
  `edit` 的 `--help` 同步。
- **补一条会真踩到的边界：`expand --eol auto` 在「连一个换行符都没有的源文件」上无从「沿用」，
  回退到 LF** —— 而样本工程那 902 个紧凑单行源**全是这种文件**，跑一遍默认参数就会在 CRLF
  工作区里新增 LF 文件（实测：6532 B 单行源 → 168 个 LF）。已在四处写明：`SKILL.md` §2.4
  与工具表 `expand` 行、`references/faq.md` 的 `expand` 条、`references/measured-data.md`
  的单行源行；`expand --eol` 的 `--help` 同步。（这一步**不静默** —— 输出里的
  `规范化后: … 换行=LF` 就在告诉你它选了哪个。）
- 统一 `edit` 的两处措辞：文件头子命令清单写「按目标换行归一」、`--help` 却写「保留目标文件的换行」，
  现统一为「锚点按目标换行归一、断言出现次数、拍平多行时警示」。
- **如实记一处行为变化**：目标文件**连一个换行符都没有**（那 902 个紧凑单行源）时，
  `edit` 的换行推断落到 **LF** —— 改前写死 CRLF，所以在 CRLF 工程里这类文件被 `edit` 加进
  多行内容后，现在得到的是 LF 文件（改前是 CRLF）。取 **LF** 是因为它与 `expand --eol auto`
  **同一规则**，且 LF 是设计器 / 仓库的原始形态（见 `check` 输出的那条 `[note]`）——
  两个子命令对同一情形给两种答案才是真的坑。该文件写盘后的自动校验会打出
  `[note] 该文件是 LF 换行…`，**不会静默**。已在 `SKILL.md` §2.4 与工具表 `edit` 行写明。

---

## [1.2.2] - 2026-09-17

本版是**三批改动的合集**（都发生在 `v1.2.1` 之后）：① 按评测补齐「反模式」入口；
② `SKILL.md` 分层瘦身；③ 一次「两套标准 × 18 个文件」全量复测的整改（1 个 P1 + 1 个 P2 + 8 个 P3）。
**无新增对外能力**（没有新子命令、新参数、新输出）⇒ 按上面的尺子是 **patch**。

### Added

- **`references/anti-patterns.md`（新文件，20 条）**：把散布在各章的「常见错误用法」收成一个入口。
  每条按「**错误做法 / 为什么诱人 / 实际后果 / 正确做法**」四段展开，并标出哪些是**静默**的
  （`check` 全部放行）—— 本工具的错误多数不报错，这是它最需要防的一面。
  内容**全部搬运**自原有各处（SKILL.md / faq.md / controls.md / sql-fragments.md / measured-data.md），
  未新增知识。配套：`SKILL.md` 导航表与参考材料清单各加一条指针，`selftest` 加守卫
  「`SKILL.md` 必须含 `anti-patterns.md` 入口」（负向测试通过）。
- **`references/js-api.md`（新文件，171 行）**：`Wb.request` / `Wb.open` / `Wb.upload` / `Wb.requestAg`
  四条引用通路的**完整写法** —— 回传四种形态怎么收、选项与回调签名、上传两步链、参数全表。
  从 `SKILL.md` §五 5.4–5.7 外移（原处只留总表 + 每通路一行骨架 + 三条最易踩的）。

### Fixed

- **`write_text()` 没有兜 `OSError` ⇒ 写盘失败直接抛 Python traceback**（P1）。
  它有 **6 个调用点**（`edit` / `expand` / `patch` / `new` / `folders --register` / `events`），
  实测 **5 个子命令 9 个场景**中招：目标只读、父目录不存在、输出目录不存在、路径过长。
  最误导的是 `patch` —— 它在崩之前已经打印了 `[ok] 已应用 1 个 op` 与 `[ok] 语义等价比对通过`；
  `folders --register` 也先说了"将追加 index 项"。
  这与 `SKILL.md` 4.1 的承诺（"前置条件不满足 → 退出码 2 + 提示"）不符。
  修法：新增 `_write_file()` 作为**所有写盘动作的唯一出口**，把 `OSError` 转成 `XwlWriteError`，
  由 `main()` 统一转成可读 `[FAIL]` + 退出码 2 —— **一处兜住，6 个调用点全部受益**。
  连带 `.bak` 备份也改走同一个出口。
- **`xwl.py` 残留项目代号 2 处**（P2，都在注释里）：去项目化的黑名单只列了业务模块名，
  没列项目代号 —— 已改为中性表述。

### Changed

- `check` 的输出补齐两处可观测性问题（P3）：
  无重名时补一行 `[ok] ⑦ 无重名`（此前**直接不输出**，而文档写「七项校验」、用户只看到 6 行）；
  `--no-js` / `--no-itemid` 时显式打印 `[note] … 已跳过` ——
  此前这两种参数组合在无重名文件上的输出**完全相同**，无从判断第 ⑦ 项到底跑没跑。
- 术语统一（P3）：`check` 运行时输出的是「末行结构」，而 `SKILL.md` 与 `faq.md` 写的是「续行结构」→
  文档改从实际输出，并把判据写细（"末行不以 `\` 结尾；首行之上的续行由 ③ 管"）。
- `references/anti-patterns.md` 的首段名由「**做法**」改为「**错误做法**」（P3）——
  `SKILL.md` 描述的是四段式「错误做法 / 为什么诱人 / 实际后果 / 正确做法」，文件里少了个"错误"。
- `faq.md`：「⑤ 与 ⑥ 的成本差异很大」→「**格式检查（①–⑤）**与 ⑥ 的成本差异很大」（指代不清，P3）。

### Testing

- `selftest.py` 结构重构：`main()` **1129 行 → 31 行**（P3）。
  按语义拆成 6 个模块级函数（`_check_basics` / `_check_params_paths` / `_check_itemids` /
  `_check_subcommands` / `_check_docs` / `_check_platform`），另新增 `_check_write_failures`。
  拆分前先做数据流分析，确认**真跨块依赖只有 4 个**（`FIELD` / `ns` / `a_sql` / `docs`，
  且都落在同一组内）；唯一的跨组依赖（嵌套函数 `_run`）提升为模块级。
  拆分后输出与拆分前**逐行一致**。
- 断言 **64 → 65 项**：新增第 23 组「写失败路径不得冒 traceback」（覆盖 `patch` / `expand` /
  `new` / `folders` 四类）。**负向测试**：临时抽掉兜底 → 精准报出 4 项 FAIL，恢复后回 65 项全绿。
- 补回分组注释：第 9 组的注释曾多缩进 4 格、第 10 组的注释整条缺失（现合并标为 `9–10`）。

### Documentation

- **`SKILL.md` 分层瘦身：933 → 740 行（−21%）**。把「特定任务才用得到的规格」外移，
  正文只留决策与流程 —— 判据是**一次典型任务是否必然用到**（同是表格，「退出码表 38 行」该走、
  「处理流程 186 行」必须留，因为后者每次任务都跟着走）。
  §五 5.4–5.7（153 行）→ [`references/js-api.md`](references/js-api.md)；
  §四 4.1 的部分内容 → [`references/faq.md`](references/faq.md)；
  §二 2.4 设计器写回算法（36 行）→ [`references/measured-data.md`](references/measured-data.md) §五；
  §七 7.5 并入 7.3（原为重复）；§一 1.2 / §二 2.1·2.3·2.5 / §三 第 4 步 / §七 7.1 逐处压缩。
  **章标题一个没删**（`selftest` 的章节守卫要求 9 个二级章存在）—— 瘦的是子节与重复表述。
  外移后做过**零丢失核对**（关键词清单逐项命中）与**引用完整性扫描**，并修掉 3 处随之失效的引用。
- **`SKILL.md` 的「N 份参考材料」清单不完整**（针对性深测发现）：写的是「五份」且只列 5 条，
  而 `references/` 实际已有 **8 个** —— 漏了 `walkthrough.md` / `faq.md` / `checklist.md`，
  读者会以为参考材料只有五份。已补全为「八份」，顺序与 README 目录树对齐。
  `selftest` 补守卫：**N = 清单条数 = 磁盘文件数**（三者必须相等），并做过负向测试。
- `CHANGELOG` 的小节分类统一（此前 `[1.2.1]` 与 `[1.2.0]` 混用了主题式与类型式标题）：
  `### 评测得分结构`、`### 本次实测依据` 降为引导句，`### selftest` → `### Testing` ——
  现在各版本段一律只用 `Added` / `Fixed` / `Changed` / `Documentation` / `Testing` / `Removed`。
- 删掉 `[1.2.1]` 段里一处重复表述（"三类改动都没有新增对外能力"说了两遍）。
- **清掉正文里「面向改动者」的元叙述**：有几句话是在向"改这份文档的人"交代，
  而不是在帮读者做事。共 6 处 ——
  `SKILL.md`「放在独立文件里是为了让本规范保持可扫读 —— 内容一条没少」与「清单**移到了**…」；
  `references/anti-patterns.md`「（旧版本在这里是静默忽略参数…；已修。）」；
  `references/walkthrough.md`「老的逐段实现要 63 s…现在已批量化」；
  `references/sql-fragments.md` 的「**读者**：…」与「…都已移到…」。
  分别改为：直接删（上方导航已完整）、「在…」、删（反模式只需要讲"你这么做会怎样"）、
  只讲现状、改问「什么时候看这份」、改问「数字与统计口径在…」。
  保留的是**面向读者**的边界声明与警告（如「不在本 skill 内」「只是样本量级参考，换工程自己测」）。

---

## [1.2.1] - 2026-09-16

**一次评测驱动的整改：按扣分项补文档与守卫 + 修 3 个真缺陷 + 一轮双尺子评审后的收尾。**

起因：把 v1.2.0 放到 SkillHub 上跑了一遍 TRACE 五维评测，得分 **4.6 / 5**。
本版针对评测里**站得住**的扣分项逐条补齐（边界、入口、FAQ、教程、退出码、CI）；
核实过程中又挖出 3 个真缺陷，其中**两个是接 CI 后连挂两次**才暴露的
（Windows 中文输出编码、Windows 跨盘符崩）—— 这两个只在 Windows 上复现，本地一直是绿的。
最后又跑了一轮独立评审，修掉它指出的 **8 处文档不一致**，并把过重的两章外移出 `SKILL.md`。

**以上改动都没有新增对外能力**（没有新子命令、没有新参数、产出格式不变），
所以按上面的尺子是 **patch**，不是 minor。

**评测得分结构（先说清楚「分是从哪丢的」）**

平台的计分方式是从前端 bundle 里读出来的，**不是推测**：5 维等权、**没有权重表** ——
`维分 = mean(该维子项)`，`总分 = mean(五维)`。所以**同样是"把 4.0 修到 5.0"，
在只有 2 个子项的维里值 +0.10，在 4 个子项的维里只值 +0.05** —— 先算杠杆再动手。

| 维度 | 子项 | 维分 |
|---|---|---|
| Trust 可信任度 | scan 5.0 · domestic 5.0 | 5.00 |
| Reliability 可靠性 | func 4.8 · stability 4.8 · errorHandling 4.5 | 4.70 |
| **Adaptability 适用性** | boundary 4.5 · **trigger 4.0** | **4.25** |
| **Convention 规范性** | structure 5.0 · progressive 4.5 · docQuality 4.3 · **antiPatternFaq 4.0** | **4.45** |
| Effectiveness 有效性 | accuracy 4.8 · completeness 4.8 · usability 4.8 · creativity 4.5 | 4.73 |

⇒ 总分 `(5.00+4.70+4.25+4.45+4.73)/5 = 4.625`，显示 4.6。
杠杆最大的两项是 `trigger`（+0.10）与 `boundary` / `antiPatternFaq`（各 +0.05）。

### Added

- **`SKILL.md` 新增「适用范围与前提」** —— 直接回应 `boundary` 的扣分
  （原文说"未明确声明仅适用 WebBuilder 平台""未说明输入文件大小等性能约束"，**核实成立**：
  全文只有一处"不适用"，讲的是点号访问，确无平台边界声明）。现在明确写出：
  平台（**仅 WebBuilder，其他平台不适用**）、对象（只 `.xwl` 本身，不含后端/打包/部署副本/`WB_MENU`）、
  环境（Python 3.9+ 纯标准库，`node` 可选）、**规模（实测最大单文件 486 KB，该文件上 `patch` 0.6 s、
  `check` 全开 1 s）**、以及"能改的前提"。
- **`SKILL.md` 新增「怎么用」** —— 回应 `trigger` 的扣分（"未明确说明用户从哪儿触发"，**核实成立**）。
  给出两个入口：① 对话里直接描述任务（列出会命中的说法）；② 命令行直调。
  并**明说本 skill 不提供 GUI / 菜单入口**，非技术用户让 Agent 代跑 ——
  与其含糊其辞，不如把定位讲清楚（评测用"普通用户找入口"的框架来评有偏差，但把话说白没有坏处）。
- **`SKILL.md` 新增「按任务找章节」导航表** —— 部分回应 `progressive` 的扣分（880 行偏重）。
- **`references/walkthrough.md`（新文件）** —— 回应 `docQuality` 的扣分
  （"缺少 step-by-step 实践指南，如完整的新建页面→加控件→挂事件→验证流程"，**核实成立**）。
  一次端到端实操，9 步、每步一条命令一个预期输出，末尾附回退处置表。
  **本文件里的每条命令都在临时目录里逐字跑过**，命令与预期输出一致。
- **`SKILL.md` 4.1「退出码与输出约定」** —— 回应 `errorHandling` 的扣分（无系统化错误码）。
  退出码 0/1/2 的语义 + `[ok]/[FAIL]/[warn]/[note]` 标记 + "判断成败看退出码别 grep 文本"。
  并诚实标注一处不一致：同是"文件不存在"，`check` 给 1（检查结论）、`patch` 给 2（前置条件）。
- **`.github/workflows/selftest.yml`** —— 回应评测 summary 点名的"selftest 未见与 CI 集成"。
  ubuntu + windows × Python 3.9 / 3.13 四格矩阵（两个脚本都有 `from __future__ import annotations`，
  3.9 可跑），并装 node 以免 ⑥ 的断言被跳过。

### Fixed

- **`check` 的 ⑥ 事件 JS 校验：逐段调 node → 一次性批量校验。**
  实测 486 KB 页面有 **246 个事件段**，原来每段起一次 `node --check` 子进程
  （本机冷启动 ~250 ms）⇒ **63 s**，占了整个 `check` 的 99%；批量后 **~1 s**。
  - 批量驱动用 `new Function(code)` 编译（函数体语义），以对齐 `node --check <x.js>` 的
    **CommonJS** 行为。这里踩过两次坑，都是**用等价性对照测出来的**：
    ① 先写成 `vm.Script`（**脚本**语义）⇒ 顶层 `return` 被判非法，一个页面的 FAIL 数从 16 涨到 120，全是误报；
    ② 换成 `new Function` 后仍有一处：Node 22 的 `--check` 在 CJS 解析失败时会**自动按 ESM 重试**
       （`--experimental-detect-module` 默认开），因此接受**顶层 `await`**，而批量驱动不接受。
  - 最终设计：**批量只用来证明「合法」**（能过 `new Function` 就一定能过 `node --check`），
    凡是批量判不合法的**一律回权威路径 `node_check` 逐段复核** —— 代价只在真有报错时才付。
  - 回归证据：486 KB 页面改动前后 FAIL 集合**完全一致**（16 项，全为 ⑦ 重名）；
    18 项语义边界用例（顶层 return / await / tagEvents 对象字面量 / `with` 与严格模式 /
    `new.target` / 重复 `let` / 正则 / 模板串 …）批量与逐段**逐项一致**。
- **`folders <目录> --register` 是静默无效的**（真缺陷）：`cmd_folders` 在 `isdir` 分支里
  **直接忽略** `--register`，只做只读扫描并以退出码 0 结束 —— 用户以为登记成功了，其实什么都没发生。
  现在改为**明确报错并退出 2**，并提示正确写法（`--register` 只接文件路径；
  一个目录里可能有好几个文件，工具不该猜）。断言已钉住：给目录必须返回 2 且**不得改动 `folder.json`**。
- **`--register` 必须带值才能用**（易用性缺陷）：`argparse` 原本要求 `--register NAME`，
  于是最自然的写法 `folders <file.xwl> --register --dry-run` 会被判成"缺参数"而失败。
  改为 `nargs="?"`，**裸 `--register` 与 `--register NAME` 都接受**（向后兼容）。
- **`new` 之后 `--register` 的前提没写清**：实测目录里没有 `folder.json` 时它会明确报错退出 2
  （**不会**替你创建）。这条既是正确行为也该写进文档 —— 已补进 SKILL.md 第三章第 0 步与 walkthrough。
- **Windows 上输出中文会直接崩**（真缺陷，**只在 Windows 上复现** —— 由第一次接 CI 暴露）：
  Python 在 Windows 的标准流编码跟随控制台代码页，实测 GitHub 的 `windows-latest` runner 是
  **cp1252**；而本工具的输出**全是中文**，于是 `print` **第一行**就
  `UnicodeEncodeError: 'charmap' codec can't encode characters...`，进程退出 1。
  ubuntu（UTF-8）、git-bash、以及本机工作区（`PYTHONIOENCODING=utf-8`）都不会暴露
  ⇒ **本地怎么测都是绿的，一上 CI 的 windows job 就红**。首跑结果：ubuntu 4 格全绿、windows 2 格全红。
  - 修法：`xwl.py` 新增 `ensure_utf8_stdio()`，把 stdout/stderr 显式 `reconfigure` 到
    UTF-8 + `errors="replace"`（**编码问题不该让工具崩掉**）；Windows 上顺带
    `SetConsoleOutputCP(65001)`，让 cmd.exe / PowerShell 也能正确显示中文而不是乱码。
    `selftest.py` 在 `main()` 开头复用同一个函数。
  - 同类隐患一并修：`_node_check_once` 调 `node --check` 时用了 `text=True` 却没指定编码 ——
    node 的报错里若有非 ASCII，在 cp1252 下解码同样出问题。已补 `encoding="utf-8", errors="replace"`。
  - **回归守卫**：`selftest` 新增第 21 组断言 —— 用子进程把 `PYTHONIOENCODING` 设为 `cp1252`
    跑 `xwl.py --help` / `check --help` / `folders --help`，要求全部退出 0。
    这样**本地就能复现 Windows runner 的条件**，不必等 CI 反馈。
  - CI 里**故意不设** `PYTHONUTF8` / `PYTHONIOENCODING` —— 设了就把这个问题盖住了，windows job 就白跑。
- CI 矩阵的 node 版本扩成 `["20", "22"]`：⑥ 的 JS 校验语义与 node 版本相关 ——
  node 22 的 `--check` 在 CJS 解析失败时会自动按 ESM 重试（`--experimental-detect-module` 默认开），
  因而接受顶层 `await`；node 20 不会。这个差异正是本轮批量优化踩过的坑，所以两边都要测。
- - **Windows 上跨盘符执行会崩**（接 CI 第二次才暴露）：`os.path.relpath(p)` 不带 `start` 时以**当前工作目录**为基准，
  只要 `p` 与 cwd **不在同一个盘符**就抛
  `ValueError: path is on mount 'C:', start on mount 'D:'`。
  GitHub 的 `windows-latest` runner 正好命中：仓库签出在 `D:\a\...`，而 `TEMP` 在 `C:\...` ——
  **一句"提示用户怎么登记"的 print 就把 `folders` 整个打死了**。
  影响面不止 CI：任何用户在 D 盘放代码、从 C 盘终端执行（或反之）都会撞上。
  - 修法：`xwl.py` 新增 `safe_relpath()` —— 拿不到相对路径就**退回绝对路径**，绝不抛
    （相对路径在这个工具里的用途只是"缩短显示"，不该成为致命错误）。**4 处调用点全部替换**。
  - **回归守卫**：`selftest` 新增第 22 组断言 —— 把 `os.path.relpath` 换成**必抛 ValueError 的桩**，
    再跑 `folders`（只读扫描 + 登记两条路径），要求不崩、且 `safe_relpath` 兜底返回可用字符串。
    用桩是因为**本机只有一个盘符**，没法真实构造跨盘符场景；桩能把"恰好没触发"这种假阴性排掉。

### Documentation

- `SKILL.md` 第八章「常见坑」**重写为 FAQ** —— 回应 `antiPatternFaq` 的扣分
  （"没有独立 FAQ 章节，高频问题分散在各章节"，**核实成立**）。
  改成 **14 条**问答式，**内容是搬运不是新增**：原 6 条坑一条不少（含"别用严格 JSON 解析器判加载"
  与"不是所有 xwl 都由设计器写过"这两条容易丢的），另从 2.3 / 3.3 / 第五章 / 第七章归拢 7 条。
  **这一版它是净增的**：第八章 16 → 69 行，整个 `SKILL.md` **880 → 1009 行** ——
  而 `progressive` 的扣分理由恰恰是"880 行偏重"，等于**修一个子项的同时加重了另一个**。
  这个矛盾在本版末尾用**外移**解决（见下方 Documentation）。
- `SKILL.md` 2.5 补 **`expand` 忠实模式 vs `--safe` 的决策规则** —— 回应 `creativity` 的扣分
  （"多行 JS 的续行美学仍依赖用户判断"）。按"这个文件给谁看"决定而非"哪个好看"：
  要提交/要给设计器继续编辑 → 忠实；只想人读一遍 → `--safe`。
- `SKILL.md` 顶部补 `## 适用范围与前提` 后，删掉原来那段只有两行的 `> 范围：` 引用块（内容已并入表格）。
- **`test-prompts.json` 6 → 10 条** —— 评测 summary 另点了"测试用例仅 6 条且偏基础"。
  新增 4 条覆盖过去没测到的面：端到端走一遍全流程、大文件 `check` 的性能取舍、
  SQL 抽取的正确姿势（别用朴素替换）、以及"能不能批量文本替换"这类**用户会提出但答案是否**的情形。
- README：`--register` 写法同步；目录结构补 `references/walkthrough.md`；快速开始指向 walkthrough；
  补 CI 徽章。

- **把过重的两章外移出 `SKILL.md`**（本版末的收尾）—— 独立评审指出 `progressive` 仍是全表最低项，
  而根因正是上一段"补 FAQ"把主文档推到了 1009 行。解法不是继续加，而是**分层**：
  - 第八章 FAQ（69 行）→ [`references/faq.md`](references/faq.md)（14 条，内容一条不少）
  - 第九章自检清单（34 行）→ [`references/checklist.md`](references/checklist.md)
    （29 项，按「改文件 / 改引用与结构 / SQL 与传参 / `itemId` 命名 / 新建文件」分五组重排）
  - `SKILL.md` 两章只留**指针 + 索引**（并点明"出问题第一站是那份 FAQ"）
  - 结果：`SKILL.md` **1009 → 926 行**（v1.2.0 是 880 行）。这样 `antiPatternFaq` 与 `progressive`
    不再互相拉扯 —— 前者要"集中"、后者要"短"，分到两个文件后同时满足。
- **修掉独立评审指出的 8 处文档不一致**（都属"改了这处忘了那处"，靠机械审计才翻出来）：
  - `CHANGELOG` 的 `## [1.2.1]` 与 `## [1.2.0]` 两个版本头曾被误删（**正文还在、标题没了**）—— 已补齐，`[1.2.2]` 段合并进来。
  - 上面那条"净增行数接近 0"的自述**不实**，已改成实测数字。
  - FAQ 条数自述 13 条 → 实际 **14 条**，已改。
  - `SKILL.md` frontmatter 的子命令清单漏 `itemids`（列了 13 个 / 实际 14 个），已补。
  - `xwl.py` 模块 docstring 只列 9 个子命令，漏 `expand / itemids / params / schema / sqlrefs` —— 已补全 14 个；
    顺带修正其中 `check` 的说明（原文写"五项格式校验"，实际是**七项**）。
  - `measured-data.md` §7.2 的类型拆分与组总数**单位不同却没标**（`error` 拆到 `date` 已累计 473 > 组总数 456；
    `warn` 前 8 项累计 1962 > 1919）。差额不是矛盾：拆分是**控件节点数**、总数是**组数**。已就地标注单位。
  - `controls.md` 表头「用过的次数」未标单位 → 改成「用过的次数（**节点数**）」，并在章首加口径说明，
    顺带解释 `dataprovider` **1143 个节点 / 1142 个文件**为什么两个数都对。
  - `controls.md` §4.1 的「次数」列 → 「出现次数（节点数）」。

### Testing

断言 **59 → 63 项**，新增四组：

- **18 · SKILL.md 必须声明平台边界、调用入口与规模约束** —— 这三样正是评测扣分点，
  而它们**在后续精简文档时最容易被删掉**，所以钉成断言。
- **19 · `node_check_many` 必须与逐段 `node_check` 逐项等价** —— 守性能优化不许改变结论，
  用例覆盖 CommonJS 与 Script/ESM 的语义差异（顶层 `return` / 顶层 `await`）。
  这条断言就是上面那两个坑的"防腐层"。
- **20 · `folders <目录> --register` 必须显式报错且不动文件** —— 守"静默无效"不复发。
- **21 · 非 UTF-8 控制台（cp1252）下输出中文不能崩** —— 守的就是上面那条 Windows 编码缺陷。
  本地开发环境是 UTF-8、只有 CI 的 windows job 能发现，所以用子进程把条件造出来，本地也能跑到。
- 文档守卫的扫描清单补入 `references/walkthrough.md`（否则新文件里的去项目化问题没人守）。
- 章节顺序守卫的期望键从「常见坑」改为「常见问题」（第八章重命名为 FAQ 后它会误报 —— 实测被它挡住了）。



- 子命令冒烟补上 **`dump`** —— 它曾是 14 个子命令里唯一没被真跑过的（评审发现）。
- 文档守卫新增 **17e：文档里指向本地文件的 Markdown 链接必须真的存在** ——
  守的正是"外移时 `SKILL.md` 指了、文件却没建 / 后来改名"这类断链，人眼扫不出来。
  **负向测试**：故意插一条指向 `references/not_exist.md` 的链接 → 守卫报 FAIL；移除后恢复 ALL OK。
- 文档守卫的扫描清单补入 `references/faq.md` 与 `references/checklist.md`。

## [1.2.0] - 2026-09-16

**补上「新建」这条路 + 修两个会静默损坏文件的缺陷 + 全文去项目化。**

起因是一次评审提问：「能不能用它生成一个新页面 + 配套的 sql.xwl」。查下来是
**改已有文件完备，但「新建」在工具层没有入口** —— `patch` / `expand` / `check` 第一步都是读已有文件，
只能靠「复制一个文件当种子、再整树重写」；而种子是**继承式**的（顶层没被覆盖到的键会静默残留）。

### Added

- **新子命令 `new`**：`xwl.py new <out.xwl> --kind page|sql` —— **从零生成** xwl，
  内置设计器**真实顶层键序**的骨架，**不需要任何种子文件**。
  - `--kind page` = 顶层 7 把钥匙 + 一个空 `module` 节点；
    `--kind sql` = `module(serverScript)` → `dataprovider(sql)`（被页面用 `store.url='m?xwl=…'` 引用）。
  - `--from-json F`：喂一个自己拼的顶层对象，按设计器键序**重排 + 补齐缺失的页面钥匙**并明确回报
    补齐了哪些；不覆盖用户给的 `title` / `roles`。
  - 默认**拒绝覆盖已存在文件**（要改已有文件应该用 `patch`）；另有 `--eol lf|crlf` / `--indent` /
    `--dry-run` / `--force`。
  - 与既有子命令同一套保证：`dumps_designer` 序列化 → `parse_xwl(out) == obj` 语义等价比对 → `_post_check`。
- **新子命令 `folders`**：`xwl.py folders <path>` —— `folder.json`（**设计器导航树索引**）
  一致性检查，默认**只读**：报「未登记进 `index` 的 xwl」「`index` 悬空项」「缺 `folder.json` 的目录」。
  `--register NAME` 才写 —— 追加到 `index` 末尾，**保原键序、保单行紧凑形态、幂等**，写前备份。
- **`SKILL.md` 新增 1.4「页面顶层骨架（7 把钥匙，键序固定）」**：写出真实键序与 7 把钥匙的取值形态。
- **`SKILL.md` 新增「第 0 步 · 新建文件」**（第三章）：`new` 用法 + **新建后必做的三件事**
  （`folder.json` 登记 / `sqlrefs`+`params` / 设计器里打开一次），
  并点明「要让用户能打开还得在数据库 `WB_MENU` 挂菜单」属范围外。
- `selftest` 新增**第 17 条：文档一致性守卫（跨文件）** —— 四类检查：
  emoji 未入标题 / README↔SKILL 无逐字重复的表格行 / 「见 N.M」编号引用可解析 / **无业务路径残留**。
  判据用**结构**（`m?xwl=` 后必须是占位符、多段 `.xwl` 路径必须落在平台白名单内）而**不是业务名黑名单**
  —— 黑名单等于把业务名又写回代码里。**负向测试**：临时塞入两类真实业务路径，守卫均报 FAIL；
  移除后恢复 ALL OK。
- `test-prompts.json` 从 4 条扩到 **6 条**：新增「新建 SQL 文件」与「新页面在设计器里看不到」，
  覆盖本版新增的 `new` / `folders`（原 4 条全部只针对"改已有文件"）；原 4 条的路径改为占位符写法。

### Fixed

- **`paths` 的「原路径」漏了 `configs` 一层**（真 bug，**静默**损坏语义）：
  原来输出 `["children",0,"serverScript"]`，照抄跑 `patch` **不报错**，而是把字段写到**节点根上**
  （产出 `{"type":"module","serverScript":…}`），`check` 也拦不住。已改为 `[...,"configs","serverScript"]`，
  并补断言：照抄该路径跑 `patch` 必须改到 `configs` 里、且不得在节点根上留下该键。
- **`schema --skeleton` 生成的是非法骨架**：原来把 `configs:{itemId, text}` 写死 ——
  但 `module` / `dataprovider` 的合法 configs 里**没有 `text`**（`module` 只有 `title`），属非法配置；
  且无条件下发 `"events": {}`，而 `dataprovider` 的合法 events 是 **0 个**、
  真实节点形态是**没有 `events` 键**的。改为：`configs` 按注册表声明推导（只加该控件确实允许的
  「显示名」键），`events` 键只在「该控件真有 `click` 事件」时输出，否则只提示可挂哪些事件。
- 三处「页面钥匙」的**列举顺序**改为真实键序（原文写作
  `title / iconCls / inframe / pageLink / hidden / roles / children`，那是认知性列举，
  在"新建"场景容易被当成**写入顺序**；而序列化按 dict 插入序输出，键序错则产出与设计器不一致）。
  涉及 `SKILL.md` 1.4 与此前的 §一 / §六、`references/controls.md` §4.2、`references/sql-fragments.md` §1。
- `SKILL.md` 3.1 的手写路径示例 `["children",0,"children",0,"sql"]` → 补上 `configs` 层，
  并加警告：漏这一层 `patch` 不报错、只会写错位置。
- **文档交叉一致性**（darwin 评审发现，均为"改了这处忘了那处"类）：
  - `controls.md` §4.2 的**失效引用**「理由见 SKILL.md 1.4」—— 该论证本版已移出 1.4，改指第三章第 0 步。
  - `measured-data.md` **头部说明与实际章节脱节**：原文只把数字分两类（"一~四、六节"+"第五节"），
    漏了 §七 / §八 / §九；样本口径只写 2777 未说明 2780；日期未标 §九 为次日新增。已补齐三类归类。
  - `controls.md` §4.2 与 `measured-data.md` §九 的**样本计数口径混用**（`2750 / 2780` vs 其余处的 `2777`）
    → 改为定性表述 + 指针。
  - `measured-data.md` §五与§九各有一个 `patch` diff 规模数字（377 KB → 17 行 / 181 KB → 15 行），
    均真实但属**两次不同实验** → 已在 §九 标注，避免被读成自相矛盾。
  - `controls.md` 控件总表的 `(根)` 行称 `module` 是「每个 xwl 的**根节点**、顶层页面钥匙是它的属性」，
    与同文件 §4.2 的「`children[0]`」矛盾。结构上后者对（前者是设计器面板视角）→ 已改写。
  - 框架文件名混用（`wb/script/wb.js` vs 源码版名 `wb-debug.js`）→ 已在 `sql-fragments.md` 加注「同一文件的两种形态」。
- 修 `SKILL.md` 3.1 的错引用 `（见 1.3）` → `（见 1.2）`（控件节点标准形态在 1.2，1.3 是"谁在写它"——
  既有缺陷，与本次改动无关）；2.4 的伪标题 `**实际逻辑在哪**` 改为引出句。

### Changed

- `selftest` 断言 **54 → 59 项**（新增 5 组：`new` / `folders` / `paths` 原路径 / `schema --skeleton` / 文档守卫）。
- **README 精简 184 → 123 行**：删掉整节「从零新建一个 xwl」（36 行操作细节，且其中的
  「新建后必做三件事」表与 `SKILL.md` **逐字重复**）；**整节移除「itemId 重名怎么办」**（22 行）——
  它的判据表与 SKILL 7.2 是同一张表、命令已由「工具速查」承载、源码依据属实现机制，
  README 不承载这类深水区问题（且它原挂在「核心工作方式」之下，语义本就不搭）；
  新建只留「快速开始」里两条命令，并补 `### 造新文件` / `### 改已有文件` 分组标题；
  工具速查表去掉实现细节（使用者不需要动作的信息）；`依赖` 节范围补「不涉及菜单注册（`WB_MENU`）」。
- `SKILL.md` 结构整改：1.4 标题去掉"唯一权威"这类定位性修饰；删掉与第三章第 0 步**重复**的
  "为什么不能用种子"论证块（论证与数据归 `measured-data.md` §九，正文只留结论 + 指针）；
  第 0 步的 `folder.json` 说明由**引用块改为正文**（引用块只放警告与补充说明，不放成段规则正文）。
- `references/controls.md` §4.2 拆出「页面顶层（7 把钥匙）」与「控件树」两段，并写明**控件节点的键序**
  （`configs, expanded, children, type`；有事件才加 `events`）；§七 区分「新建文件」与「改结构」两条路，
  两条分支的形状统一。
- 文件头 docstring 的子命令清单同步（补 `new` / `patch` / `paths` / `folders`）。
- **去项目化**（skill 是通用资产，正文不应出现任何具体工程的业务信息）：
  - **隐去**：业务模块路径（→ `<模块>` / `<业务目录>` 占位）、业务 `.xwl` 文件名、
    业务字段名（→ `BIZ_TYPE` 这类中性名）、业务后台 bean 名（→ `xxxController`）、
    **以及该工程自己的目录命名习惯** —— 它给 SQL 载体目录起的名字是项目约定而非平台规范，
    已统一换成 `xxxSql/`，避免把「某工程的组织方式」当成通用规则传播。
  - **保留**：平台自带目录（`wb/system/`、`wb/script/`、`wb/libs/`、`dev/`、`examples/`、
    `modules/dev/template/`）、框架端点（`common/save-all`）、jar 与类名
    （`WEB-INF/lib/Webplatform-1.0.jar`、`com.wb.interact.IDE`、`com.wb.tool.Query`）——
    这些是**知识锚点**，读者要靠它们回工程查证，不能删。
  - 涉及 7 个文件共 **49 处**；复查后业务信息残留 **0 处**。

**本次实测依据（样本工程 `wb/` 下 2780 个 xwl）**

- **顶层键序**：**2750 / 2780** 为 `hidden, children, roles, title, iconCls, inframe, pageLink`；
  **独立页面与被引用的 SQL 载体完全一样**。取值形态：`hidden:false` / `roles:{"default":1}`（dict）/
  `iconCls:""`（1480 / 1635）/ `inframe:false` / `pageLink:""`（1593 / 1615）。
- **种子无关性（决定 `new` 形态的关键实验）**：两个内容毫不相干的种子
  （`examples/crud/crud-db-access/basic-select.xwl` 313 B 的 SQL 载体、与
  工程内的一个最小独立页面 179 B）在**完全相同的 ops** 下产出**逐字节相同**；
  而顶层缺 `inframe` / `pageLink` 的种子（`dev/ide/add-file.xwl`）产出**少 2 把钥匙**，`check` 仍报 ALL OK。
- **`folder.json`**：565 个含 xwl 的目录中 **558 个**有它；**322 个 xwl 未登记**进 `index`；
  `index` 里 2440 个带 `.xwl` 项全部对得上文件、488 个不带后缀项全部对得上目录
  （同名目录与同名文件可并存，55 处）；悬空项 14 处。
- **`patch` 的高保真**（复核）：181 KB 的多行源页面追加一个按钮，diff 仅 **15 行**
  （其中 2 行为 `\u201c`→`“` 的语义等价规整）。

---

## [1.1.0] - 2026-09-15

**「itemId 重名分级」+ 一次全文件深审修复**。

主线一：把 itemId 重名从「一律拒绝」改为**分级 + 给候选清单和建议值** —— 由项目维护者口述的
三条命名规则 + 第四点「重名要读父子关系」驱动。

主线二：用 `darwin-skill` 的 8 维 rubric 做全文件深审（7 个文件 + 样本工程 2780 个 xwl 交叉复算），
修完 P1 五项 / P2 三项 / P3 四项。深审发现：**skill 里不应出现"参考的哪个项目"与
该项目各分类的命中统计** —— 已把统计全部移到 `references/measured-data.md` §7。

### Added

- **新子命令 `itemids`**（第 12 个）：`xwl.py itemids <file>` —— itemId 重名**只读**报告。
  - 三种分级：`benign`（无害）/ `warn`（未被 JS 引用，老代码可留、新代码须区分）/ `error`（**已被事件 JS 引用**）。
  - 每个重名组给**候选清单**：`#N` 序号 + 祖先链（`panel2 › tab1 › grid2`）+ 原路径 + 可辨识字段 + **其下有什么控件**。
  - `--name X` 只点名一个名字；`--dups-only` 折叠 benign 组；`--json` 机器可读；
    `--suggest [--fix auto|normalName|itemId]` 输出**可 `patch` 的改名 ops 草稿**（须人工确认）。
- **`@itemId#N` 寻址**：重名时点名第 N 个（N 从 1 起）。`@` 段串联即"带父级的限定名"（`["@grid2","@tbar"]`）。
- `audit_itemids()` / `js_refs_of()` / `itemid_hits()` / `format_itemid_candidates()` / `suggest_itemid()` /
  `suggest_normalname()` / `discover_controls()` / `normalname_types()`；`ItemIdError`（继承 `KeyError`，
  但 `str()` 给可读原文，不带引号包裹）。`_iter_controls()` 取代原 `_find_all_by_itemid` 的递归实现。
- `check` 新增**第 ⑦ 项**：itemId 重名分级。**只有「重名且被事件 JS 引用」判 FAIL**，其余出 `[warn]`。
  新增 `--no-itemid` 跳过。`selftest` 断言 **36 → 54 项**。

### Changed

- **重名不再只是"拒绝"**：`@itemId` 重名的报错改为**候选清单 + 建议值**（原来只有一句"请改用下标路径"）。
  `patch` 对这个多行报错**原样打印**（原来会被压成一行）。
- `paths` 的重名提示：从「@写法**不可用**」改为给出 **`@名字#N`** 与 `itemids` 两条出路。
- `check` 的帮助文本与判定表：六项 → 七项。
- **`SKILL.md` 全文重排**（第二轮深审：章节顺序语义错位）—— 从「按写作顺序」改为**按语义分组**：
  认知 → 格式 → 操作 → 专题 → 经验 → 收尾。具体：
  「六、单行源 vs 多行源」并入「二、格式硬规则与文件形态」（原稿把同类主题隔了 3 章）、
  「八、工具」提前到流程之后（第三章到处在用工具，工具清单却在 200 行外）、
  原「一.2 `m?xwl=` 怎么读」并入「五、引用方式」并成为 5.1（与 5.2 url 三种写法同源）、
  专题三章（引用 / SQL / itemId）连续排列，不再被格式与工具章隔断。
  十章 → **九章**；同步更新 6 处交叉引用（`第四章`×2 / `第六章`×1 / `第九章`×4 / `§5.5`→`§5.6`×2）。
- **写盘后的自动校验只判格式**：`patch` / `edit` / `expand` 末尾的自检抽成 `_post_check()` 并显式跳过 ⑦。
  itemId 重名是**文件既有的质量属性**、不是本次改动造成的 —— 若一并判定，会出现
  "写盘成功却返回非 0"的误导（实测：给含 5 组 error 级重名的页面打补丁，退出码由 1 改回 0）。
  自检末尾附一行指引，要看重名请单独跑 `itemids`。

### Fixed

- **原「itemId 不唯一就不处理」的判据是错的**。现在按 **控件类型 + 是否被 JS 引用 + 有无 `normalName`** 定级，
  依据是框架源码与样本工程实测。
- `_node_hint()` 里 `normalName` 与独立字段重复显示；`suggest_normalname()` 对全大写字段名会产生
  `XXX_CODET` 这类粘连（改为按需用 `_` 分隔）；父级名切不出"区分段"时会拼出 `editbutton2tbar`
  （改为 `editbutton2_tbar`）。
- `audit_itemids()` 返回值里的 `js_refs` 是 `set`，`itemids --json` **直接崩在 `json.dumps`** ——
  改为 `sorted(list)`。已加断言守住（抽检 120 个真实文件，`--json` / `--suggest` 产物全部可序列化）。

**深审修复（P1 · 5 项，由 darwin-skill 全文件审查发现）**：

- `recommend_fixes(mode="normalName")` 会对 **44 个不接受 `normalName` 的类型**（`array` / `dataprovider` /
  `query` …）写出 `configs.normalName` —— **非法配置键**（已复现 `array` 组）。现**永不写入**这类项，
  并通过新增的 `skipped` 参数回报：`--fix normalName` 会列出被跳过的类型。
- **文档归因错误**：`SKILL.md` §9.3 曾把 `panelCustomRecord_ID` 当作「改 `itemId` 用父级作前缀」的先例。
  实测它**只以 `normalName` 出现**，**不是任何节点的 `itemId`**。已换成样本工程里真实的 `itemId` 前缀先例（
  `panelX_find`）并把这个易错点在 `references/measured-data.md` §7.6 记清楚。
- `js_refs_of()` **不剔 JS 注释** → 注释里的 `app.X` 被当成引用（会把 benign/warn 组误判为 error）。
  现先过 `strip_js_comments`；并新增 `filtered=False` 供"判定是否被引用"使用。
- `_APP_REF_RESERVED` **无条件排除** `store` / `add` / `items` / `id`，**遮蔽真实引用** ——
  某页面里 3 个同名 `store` 明明被 `app.store` 引用，却只判 `warn`。现判定改用未过滤集合
  （理由：名字既已确认是文件内的 `itemId`，保留表那层歧义就不存在）。样本工程里 1 组受影响，已修。
- **`decode()` 在 12 个子命令里有 10 个未保护** —— 传一个读不到的文件就抛裸 `Traceback`
  （只有 `check` 处理了）。现抽出 `read_xwl_text()` / `load_xwl()` 统一抛 `XwlLoadError`，
  11 个子命令一律给 `[FAIL] 无法读取 …`；`edit` 走**只读**路径（不解析）以保住"能修坏文件"的用途。
  顺带把 `parse_xwl` 找不到 `{` 的报错从 `substring not found` 改成人话。

**深审修复（P2 · 3 项，文档一致性）**：

- `README.md` 目录树写 `test-prompts.json # 3 条典型 prompt`，实际已是 **4 条** —— 修正。
- `references/measured-data.md` §7.1 的「不接受 `normalName`」清单只列了 23/44，**补齐为完整 44 个**，
  并点明这些是纯 HTML 标签 / 图表子元素 / 后端节点（给它们写 `normalName` 属非法配置）。
- 本文件原 `### 本次复算的关键事实` **不是 Keep a Changelog 允许的小节名**（只允许
  Added / Changed / Deprecated / Removed / Fixed / Security）→ 改为引用块。

**深审修复（P3 · 4 项，健壮性与文档）**：

- `itemids --name X --json` 同时给时 `--json` 被**静默忽略**（`--name` 先返回）→ `--name` 现在也支持 `--json`。
- `itemids --suggest` 在"无事可做"时返回 **1**（其实不是错误）→ 改为返回 **0** 并给出说明；
  同时把 `--fix normalName` 跳过的项打到 stderr（配合 P1 第 1 条）。
- `_iter_controls()` 会深入 `configs`，把里面带 `type` 键的**内联配置对象**也当成控件
  （样本工程里 128 个，虽然都没 `itemId`，但 `@itemId` 理论上可能误指到它）→ 现在**不深入 `configs`**，
  控件只从 `children` 找。
- `SKILL.md` §9.2 补上**第四条规则**（`itemId` 不是合法 JS 标识符时只能 `app.get('名')`）；
  §8 的 `itemids` 行补 `--controls`；§9.1 的框架源码引用加「换版本按符号名搜、别按行号」提示。

**深审修复（第二轮 · 4 项）**：

- **字段重名统计丢失**：上一轮去项目化时，把「字段控件重名 129 组已有唯一 `normalName` / 745 组待补」
  从 `SKILL.md` 删掉却**没落到 `measured-data.md`** —— 已补进 §7.2（并补上"共 874 组"的口径）。
- `itemids --name X --json` 找不到名字时输出**纯文本** `[FAIL]`，JSON 消费者拿到非 JSON
  → 改为输出 `{"error":"not_found", ...}`。
- `recommend_fixes()` 对缺 `fix_normalname` / `fix_itemid` 键的 group 会 `KeyError`
  （只影响手工构造的 dict）→ 改用 `.get(..., [])` 防御。
- `SKILL.md` 与 `measured-data.md` 各贴了一遍 `ComponentManager` 源码 → 只留 `SKILL.md` §7.1
  （规则依据），statistics 侧改为指针。

**文档去项目化（深审提出的原则）**：

- `SKILL.md` 不再出现样本工程的名字，也不再列该工程的命中分类统计 ——
  第九章只保留**规则 + 框架机制 + 怎么查**，数字统一指向 `references/measured-data.md` §7。
- 原来的 §9.5「全项目基线」表改为「想知道某个工程里实际有多少重名」——教读者**在自己工程上跑**。
- §7.3 的示例改为与具体工程无关的通用命名（`gridLeft` / `panelX_find`），
  真实样本证据（`tbarW` / `panelX_find` / `panelCustomRecord_ID` 的辨析）挪进 measured-data §7.6。
- **命中分类统计全部移出** `SKILL.md`：引用方式表的「实测次数」列（2735/1702/52/132/1534/1）、
  `Wb.requestAg` 的「1534 个调用点」、注册表的「133 个控件」、回放校验的 1875/1830/97.6%/45/902、
  以及「377 KB → diff 17 行」——这些一律只留在 `measured-data.md`，`SKILL.md` 改为**结论 + 指针**。
- **`references/sql-fragments.md` 同样收敛**（它原本是「规范 + 实测」混排）：文件分布
  （1165/1142/687/478）、`{#名字#}` 交集次数（715/55/19）、三类占位符次数
  （492/278/202/76、451/247/208/132）、被引用路径与引用点（2000/5000+）、
  `serverScript` API 词频（4750/1328/1052/…）、`sqlrefs` 自洽率（1620/1606=99.1%）——
  全部先**收口到 `measured-data.md` 新增的 §八**，再在文内留下「结论 + 指针」。
  该文现在**一个三位数都没有**，文件头明说「本文只讲规范与机制」。
  （改法上严格先落库再删，避免重犯"删了没落库"的错。）

> **本次复算的关键事实**（都能用 `itemids` / `selftest` 复现）
>
> - **重名的后果有源码依据**：`wb/libs/ext/ext-all-debug.js:21689`（WebBuilder 改过的 `Ext.ComponentManager`）
>   —— 注册键是 **`normalName || itemId`**（normalName 优先），注册是**普通赋值**（后者覆盖前者），
>   注销是**按同名键直接 `delete`** ⇒ **任一重复项被销毁会把整个名字从页面作用域删掉**。
>   这正是"重名后 `app.X` 取不到值"的确切机制。
> - **`normalName` 是合法 configs 键**：注册表 133 个控件里 **89 个**接受、44 个不接受（多为布局/HTML/后端节点）。
> - **列控件重名确实无害**：样本工程 **3393 组**列重名（`column`/`tcolumn`），被事件 JS 引用的 **0 组**。
>   命名约定 `_COL`/`Col` 后缀：20771 个列 itemId 里 **14213 个（68.4%）**带此后缀。
> - **重名分级分布**（可解析 2777 个 xwl / 59791 个含 itemId 的节点 / 12304 段事件 JS）：
>   benign **3543**（列 3393 + 已有唯一 normalName 150）/ warn **1919** / error **456**。
>   ⚠️ 这些只是**该样本的量级参考，不是通用阈值**；且口径随工具版本变过 ——
>   修掉"注释里的 `app.X` 被当成引用""保留表遮蔽真实引用"两个缺陷后，error 由 519 降到 **456**
>   （少了 63 组**误报**）。完整分布与按类型的 Top 见 `references/measured-data.md` §7.2。
> - **`#` 从未出现在任何 `itemId` 里** ⇒ 用它作序号分隔符安全。
> - 实测最小 diff：在重名文件里用 `@名字#N` 改一处 `itemId`，diff **仅 2 行**。

---

## [1.0.0] - 2026-09-15

首次对外发布，提交至 <https://github.com/yfwang0731/skill-webbuilder-xwl-patch>。
本版为**全文本复审**（`SKILL.md` + `README.md` + 3 份 `references/` + 2 个脚本 + 配置文件）后的发布状态。

### Added

- `CHANGELOG.md`（本文件）。
- `scripts/selftest.py` 新增 **「子命令冒烟」** 用例：直接调用 `cmd_paths` / `cmd_sqlrefs` / `cmd_params`。
  这条守卫能拦住「改了内部函数名、漏改调用点」这类**静态检查发现不了**的故障（见下方 Fixed 第 2 条）。

### Changed

- **逐条复算并修正 5 处数字/表述错误**：
  - `Wb.upload` 的 `success` 回调错位计数：**94 → 101**，并补完整分布
    （首位名为 `action` 101 / `form` 32 / 无参 5 / `resp` 1，共 139 个调用点）。
  - diff 示例：**15 → 17 行**（377 KB 的一个多行源页面加一个带多行 JS 的按钮 + 改标题，实测复现两次）。
  - `wb/system/url.json` 短名数：**60 → 54 个**。
  - `bean` / `method` 保留键：**1399 → 1400**；`ID` 参数：**38 → 40**（并注明按 `params: {…}` 键名正则统计的口径）。
- `SKILL.md` §5.3：`callback` 签名按源码更正为 **`(form, action, value, success)`**；
  `Wb.download` 补全为 **`(url, params, isUpload, method)`**（原来只写了前两参）。
- `references/controls.md`：补全 §4.1 中 5 处空的「读法」单元格；为 `wb-debug.js:2633` / `ide-debug.js:4397`
  两处行号引用加**版本脆弱性提示**（换版本按符号名搜，别按行号找）。
- `README.md`：`paths` 的定位说明改为「改 SQL/数据源时用它拿字段路径，其余改动用 `dump` 看层级」。

### Fixed

- **`cmd_params` 里残留旧函数名**（函数重命名时漏改一处调用）→ 抛 `NameError`，`params` 子命令**直接崩溃**。
  由新增的「子命令冒烟」用例覆盖。

> **复审结论（结构面全绿）**：无 BOM / 纯 LF 一致、Markdown 代码围栏全部配平、
> `SKILL.md` 覆盖 11/11 子命令、frontmatter 524 字符（限制 1024）、内部链接 9/9 可达、
> `test-prompts.json` 合法、跨文件仅 1 处刻意重复（`ops.json` 示例）；
> `selftest` **36 项 ALL OK**；11 个子命令在真实文件上全部通过。

---

## [0.9.0] - 2026-09-15

### Changed

- **改名 `webbuilder-xwl` → `webbuilder-xwl-patch`**：旧名体现不出用途，新名点明「用结构级 `patch` 改 xwl」。
  目录、frontmatter `name`、README 标题与安装路径同步。
- **§4 下沉为独立分册**：新增 `references/sql-fragments.md`（两级结构 / 字段格式 / 引用机制 /
  硬规则与执行器 / 页面传参两条通路 / 配套工具 共六节）。
  `SKILL.md` §4 由 14968 B 压到 2.5 KB 的「要点 + 指针」，**全文 52.9 → 41.6 KB**；
  `§4.5`、`见第四章` 等交叉引用全部改指新文件。
- **修正 `97.6%` 的表述**：该数字是**回放校验**证据（把算法跑在项目既有文件上比对字节），
  不是读者某次编辑的结果。`SKILL.md` / `README.md` 改为「回放校验」叙述，只保留对读者的结论
  （重排不会顺带改动无关内容 → diff 最小化）；**`README.md` 删掉该数字**，只留指针；
  `measured-data.md` §五 标题加「（回放校验）」并在节首注明「这不是某一次编辑的结果」。

### Fixed

- **`@itemId` 重名时静默命中第一个** —— 会**改错对象且无任何提示**
  （`xwl.py paths` 对 4 个同名 `store` 全部推荐 `["@store", …]`；`examples/employee/dialog.xwl` 即此形态）。
  改为**重名即拒绝执行**（`KeyError` / exit 2 / **不写盘**），`paths` 输出标 ⚠ 并给出原路径；
  **`out` 通路不受影响**（只做分析，取第一个并注明 ×N）。
- 删除死代码：`_get_path`（无调用）、`dumps_canonical = dumps_designer`（旧名别名，无引用）。
- `scripts/selftest.py` 的 docstring 过期（写「5 种典型破坏」，实际已 30+ 项）→ 改写并列出覆盖范围。
- 工具表选项面补全（`patch --indent`、`expand --out/--indent`），`paths` 说明其只覆盖四类字段。

### Added

- `xwl.py paths` 输出增加**重名告警**；自检新增 `@itemId` 重名拒绝 / 唯一定位 2 项（自检 33 → 35 项）。

---

## [0.8.0] - 2026-09-15

经 darwin-skill 8 维评审做了 7 轮优化（72.7 → 87.0，全部保留）。

### Added

- **`references/measured-data.md`**：引用方式次数、传参两条通路分布、`Wb.requestAg` 参数名与回调动作频次、
  设计器复刻的回放校验结果、统计口径。`SKILL.md` 中相应的大段实测表格改为「结论 + 指针」。
- **`references/controls.md`**：按设计器面板分组的控件总表（133 个真控件 + 13 个面板分组节点）、
  三套控件库、配置载体说明、实测父子结构 Top 45、典型骨架与选型建议、改结构的安全顺序。
- `xwl.py schema --tree`：按面板分组打印全部控件（带 库 / 容器 / 内部 标记）。
- **`SKILL.md` 第五章「xwl 的引用方式」**：数据源 / 服务端片段 / 子页面 / 文件上传四类引用的写法、
  引用位置、回传后前台怎么处理；`Wb.open` 的选项表；`Wb.upload` 的**导入两步链**。

### Changed

- **把结构级 `patch` 立为默认编辑方式**，文本级 `edit` 降为「例外手段」；第 3 步、3.2 节标题、
  自检清单首条、frontmatter 描述同步。
- **`README.md` 精简 62%**（12896 B / 205 行 → 4882 B / 96 行），改为以 `patch` 为标题级主线的入口页；
  深度内容一律链向 `SKILL.md` 与 `references/`。
- 新增**改前核对**流程（`paths` → `dump` → 写 `ops` → `--dry-run`）与**报错怎么办**对照表
  （路径不存在 / 语义等价比对失败 / `check` 不通过，含 `cp <file>.bak <file>` 恢复指引）。
- 修正 `check` 的 ② 描述：从「无裸 LF」改为「**全文件换行一致**（LF-only 合法）」——
  原文与实现相反，会把设计器产出的合法 LF 文件判成失败。
- 统一数字口径（2780 → 2777）、统一 §1 小节编号（1.1–1.4）、示例改为以身作则使用 `@itemId`。

---

## [0.7.0] - 2026-09-15

### Added

- **`SKILL.md` 第四章「SQL 片段」**：`module.serverScript` ↔ `dataprovider` 的**两级结构**、
  两者互相引用的机制（`dataprovider.sql` 用 `{#名字#}` 引用 `serverScript` 注入的值）、
  三种占位符的来源区分（`{#sys.*#}` 内置 / `{#任意名#}` 由 serverScript 提供 / `{?名字?}` 绑定参数）、
  执行器类与源码依据。
- **页面传参两条通路**：`out`（推荐，整包收容器内控件值）与 `params`（显式传名值）；
  包括收集机制、`%` / `$` 前缀、`null`→`''`、重名 `itemId` 只取第一个、不看 `hidden`/`disabled`、
  **两个 API 同名参数的覆盖方向相反**、命名契约「参数名 = 控件 `itemId`」。
- 子命令 **`paths`**（列 `sql` / `totalSql` / `serverScript` / `url` 的位置，给「原路径 + `@写法`」）、
  **`sqlrefs`**（验 `{#…#}` 与 serverScript 自洽、抓 serverScript 内误用 `{#…#}`）、
  **`params`**（页面 → store → SQL 传参链路交叉核对，并展开 `out` 容器内的取值控件名）。
- `patch` 的 `path` 支持 **`@itemId` 寻址**：只给「值 / 子树」，不必知道嵌套层级。

### Fixed

- 扫描传参点时漏掉 `events`（它是 `configs` 的**兄弟键**，不在其内），词频少了两个数量级。
- `setAttribute` 的正则只认双引号 —— xwl 强制 JS 用**单引号**，导致误报「缺失」。

> - 全项目扫描：**1620 个含 serverScript/dataprovider 的文件，1606 个引用自洽（99.1%）**；
>   14 个 `{#sql#}` 本文件未提供（多为「由调用方传入」）、1 处 serverScript 误用 `{#…#}`。

---

## [0.6.0] - 2026-09-15

### Added

- **结构级编辑 `xwl.py patch`**（本次成为核心手段）：只提供「值 / 子树」，
  序列化器按设计器算法重建整份文件，支持 `set` / `insert` / `append` / `delete`；
  写盘前强制做「**重新解析 == 改后对象**」的语义等价比对，对不上**中止不写**。
- **子命令 `schema`**：查设计器控件注册表 `wb/system/controls.json`（133 个真控件），
  `--list` / `--skeleton` / 后续加入 `--tree`。
- `SKILL.md` §1.3「控件节点的标准形态」：控件节点的键集合**全项目只有两种**
  （`[configs, expanded, children, type]` 与再加 `events`），键序固定。

### Fixed

- `build_parser()` 内子命令误用了主 `p` 变量，**覆盖了主 parser**（`return p` 变成返回子命令），
  表现为 `patch: error: unrecognized arguments`。
- 文档示例与真实数据不符：原示例的 `button` 节点缺 `expanded` / `children`、
  `container` 是凭空拼的、`delete ["children",0,"configs","hidden"]` 的键在示例文件里并不存在。

---

## [0.5.0] - 2026-09-15

### Added

- **破解并复刻设计器的写回算法**：`WEB-INF/lib/Webplatform-1.0.jar` →
  `com.wb.interact.IDE#saveFile` → `updateModule(File, JSONObject, String[], boolean)`，
  四步 = `json.toString(1)` → `replaceAll("\\n","\\\n")` → `replaceAll(line.separator,"\n")`
  → `FileUtil.syncSave(file, s, "utf-8")`（**不加尾换行**）。
  `toString(1)` 是**老版 org.json**，三条反直觉规则：每级缩进 **1 个空格**；
  只有 0/1 个元素的容器不换行（`{"itemId": "x"}`、`[3]` 内联）；单元素容器递归时传**当前缩进**
  （于是有 `[{`、`}]` 紧凑写法）。另有「非 ASCII 原样保留」「`</` 写成 `<\/`」。
- **子命令 `expand`**：单行源 →（设计器同款）多行，含语义等价比对、`--eol`、`--safe`。
- `SKILL.md` 第六章「单行源 vs 多行源（决定性规则）」，含多行源**绝不能压成一行**的实测表格。

> - **回放校验**：复刻算法跑在项目既有文件上，多行源 **1830/1875 = 97.6% 逐字节相同**
>   → 证明复刻正确，因此 `patch` / `expand` 的 diff 只含真正改的内容。
> - 换行真相：设计器写 **LF**；`git ls-files --eol` → `i/lf w/crlf`，本机 `core.autocrlf=true`
>   ⇒ 工作区看到的 CRLF 是 git 转出来的 —— 规则是「**全文件一致**」，不是「必须 CRLF」。

---

## [0.4.0] - 2026-09-15

### Added

- `SKILL.md` 章节「把 xwl 压成一行：可以做，但只有一种做法是对的」——
  实测 4 个变体后确认：`\`+换行 → `\n` 转义**正确**（加载器自己的变换）；
  而**直接删掉换行**会让 JSON 依然合法、**格式校验与 `node --check` 全部放行**，
  但 JS 换行消失 → `//` 注释吃掉后续代码、ASI 语义改变（`return` / `throw` / `++` / `--`）——
  属**静默语义损坏**，只能靠 `git diff` 发现。

### Removed

- **收窄范围到「只讲 `.xwl` 文件本身」**：删除 `references/deploy.md`（前端同步 `target`、
  模块 jar 重打包、热加载、缓存 `?v=`、排错对照表），`SKILL.md` 的「五步流程」相应改回**四步**，
  frontmatter 与正文中部署相关的触发词一并移除。
- 删除「`<>` 别写进 mapper XML」这条坑（属于 MyBatis/SQL 侧，不属于 xwl 文件本身）。

---

## [0.1.0] - 2026-09-15

从「司机二维码提箱全流程」会话中固化的经验，建成本 skill。**首个可用版本。**

### Added

- `SKILL.md`：格式硬规则（UTF-8 无 BOM、换行全文件一致、续行符 `\` 紧邻换行、
  最后一行不加 `\`、字符串内 `"` 写 `\"` ⇒ **xwl 里的 JS 一律用单引号**）、加载机制、
  处理流程、常见坑、自检清单。
- `scripts/xwl.py`（纯标准库、零依赖）：`check` / `edit` / `dump` / `sql` / `events`。
- `scripts/selftest.py`：内置样本自检（合法样本 + 5 种典型破坏）。
- `README.md`、`LICENSE`（MIT）、`.gitignore`。

> - **加载器等价判据**：`text` 在磁盘上是「反斜杠 + 真实换行」的多行字符串，加载时先做
>   `replaceAll("\\\\(\r\n|\r|\n)", "\\\\n")` 还原成 JSON 的 `\n` 转义，再用 **org.json** 解析。
>   ⇒ **能按加载器规则解析成功 ⇔ 格式没问题**，这是最强的校验手段。
> - 加载器是 org.json，**比标准 JSON 宽容**（字符串里未转义的裸控制字符也照收），
>   所以工具用 `json.loads(..., strict=False)` 对齐。
> - `events.tagEvents` 的值是 **JSON 对象字面量字符串**，直接 `node --check` 会误报，需包一层括号复验。
>
> [1.0.0]: #100---2026-09-15
> [0.9.0]: #090---2026-09-15
> [0.8.0]: #080---2026-09-15
> [0.7.0]: #070---2026-09-15
> [0.6.0]: #060---2026-09-15
> [0.5.0]: #050---2026-09-15
> [0.4.0]: #040---2026-09-15
> [0.1.0]: #010---2026-09-15
