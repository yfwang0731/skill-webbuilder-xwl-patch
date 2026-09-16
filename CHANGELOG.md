# Changelog

`webbuilder-xwl-patch` 的全部重要变更。格式参考 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。**按时间倒序**，日期为 `YYYY-MM-DD`。

> **关于本文件里的数字**：凡标「实测 / 复算」的，都是把工具跑在样本工程（`wb/` 下 2777 个 `.xwl`）
> 上得到的，可用 `scripts/selftest.py` 与 `scripts/xwl.py` 的各子命令复现。
> 「回放校验」指**把算法跑在既有文件上比对字节**，与某一次编辑的结果无关。

---

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

### 本次实测依据（样本工程 `wb/` 下 2780 个 xwl）

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
