# Changelog

`webbuilder-xwl-patch` 的全部重要变更。格式参考 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。**按时间倒序**，日期为 `YYYY-MM-DD`。

> **关于本文件里的数字**：凡标「实测 / 复算」的，都是把工具跑在样本工程（`wb/` 下 2777 个 `.xwl`）
> 上得到的，可用 `scripts/selftest.py` 与 `scripts/xwl.py` 的各子命令复现。
> 「回放校验」指**把算法跑在既有文件上比对字节**，与某一次编辑的结果无关。

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
  - diff 示例：**15 → 17 行**（377448 B 的 `transTrack.xwl` 加一个带多行 JS 的按钮 + 改标题，实测复现两次）。
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
