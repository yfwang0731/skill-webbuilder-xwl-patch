---
name: webbuilder-xwl-patch
description: >-
  WebBuilder（wb）平台 .xwl 定义文件的处理与安全编辑。核心手段是**结构级 patch**：
  只提供「值 / 子树」，工具按设计器自己的算法重建整份文件，续行符、转义、缩进、换行全部自动产出
  —— 格式错误在构造上不会发生，且 diff 只含真正改的内容。
  触发场景：改 wb/modules/** 下的页面 .xwl（加删控件、挂改事件、改配置、改网格列）、
  改被引用的 SQL 片段 transSql/*.xwl（同样用 @itemId 寻址 patch）、
  查改「参数控件 → store → SQL」传参链路（两条通路 out / params，推荐 out）、
  处理 itemId 重名（按「类型 + 是否被 JS 引用 + 有无 normalName」分级，给候选清单与建议值；
  列控件允许重名、取值控件靠 normalName 区分、按钮/面板/承载必须唯一）、
  判断某个 .xwl 格式是否合法、xwl 加载报解析错误或页面白屏、要不要把 xwl 压成一行。
  附零依赖工具 xwl.py：check / itemids / patch / edit / params / paths / sqlrefs / schema / dump / expand / sql / events。
agent_created: true
---

# WebBuilder .xwl 文件处理流程

WebBuilder 的页面与查询定义都写在 `.xwl` 里。它**看起来像 JSON，但不是严格 JSON** ——
磁盘上是「字面反斜杠 + 真实换行」的多行字符串。不懂这一点就去改，**第一刀就会把文件改坏**（运行时解析失败、页面白屏）。

**本 skill 的核心是「不碰文本层」**：用 `xwl.py patch` 做**结构级编辑** ——
你只给出「值 / 子树」，序列化器按**设计器自己的算法**重建整份文件（续行、转义、缩进、换行全部自动产出）。
于是：

- **格式错误在构造上不会发生**（不接触文本层，就没有"改坏格式"这条路）；
- 重建算法做过**回放校验**（把它跑在项目里既有的 1875 个多行源文件上，97.6% 还原出的字节与原件相同）
  → 说明排版复刻正确，因此重排**不会顺带改动无关内容**，**diff 只含这次真正改的内容**；
- 写盘前强制「重新解析 == 改后对象」的语义等价比对，对不上就中止。

文本级 `edit` 只在"改一小段、又不想整份重排"时作为**例外**使用。

> 范围：只看 `.xwl` 文件本身（格式、编辑、校验、抽取）。
> 不涉及后端代码、模块打包、部署副本同步等 —— 那些由各自流程负责。

行文约定：`##` 主题，`###` 子主题；列表项以 `**标签**：` 开头；`>` 只放警告。

## 何时使用

- 要**读懂或修改任何 `.xwl`**。PC 页面、弹窗/子面板、store 数据源、SQL 定义，全都是同一套格式、同一套处置方式 —— 不按目录或操作类型设限。
- 常见改动：加/删/改控件与按钮、挂改事件 JS、改 `multiSelect` / `selType` / `columns` / `configs` 等配置、改 store 里的 SQL、改标题 / 权限 / 内嵌地址。
- 遇到 xwl 加载报解析错误、页面白屏 / 栅格不出来。
- 要**新建/调整控件结构**：不知道该用哪个控件、该挂在哪个父控件下、`grid` 的列/工具栏/数据源分别挂在哪 —— 见 `references/controls.md`（控件清单）与第五章（引用方式）。
- 要把 xwl 里的 SQL 或事件 JS 抽出来离线验证（灌真实库跑一遍、`node --check` 语法检查）。
- 要确认一次改动没破坏格式；或判断某个 xwl 是**独立页面**还是**被引用的片段**、是谁在引用它。
- 要判断某段内容能不能写成一行、或把已经压成一行/紧凑格式的文件还原成规范多行。

## 一、xwl 是什么（先建立正确心智模型）

**一个 `.xwl` = 一棵 JSON 树**，描述一个"页面 / 资源"。顶层固定是那几把页面钥匙
（`title` / `iconCls` / `inframe` / `pageLink` / `hidden` / `roles` / `children`），
`children` 递归挂控件；控件上通常有

- `type` —— 控件类型（window / container / grid / store / button …）；
- `configs` —— 控件配置；**SQL 就在这里**（store 节点的 `configs.sql`，不是顶层键）；
- `events` —— 事件名 → JS 代码字符串（`click` / `change` / `tagEvents` …）。

> 所以"改 SQL"就是改树里某个 `configs.sql`；"改行为"就是改某个 `events.*`。

### 1.1 按用途分两类（**不要按文件结构分** —— 两类结构完全一样）

| 类别 | 说明 | 怎么认 |
|---|---|---|
| **独立页面** | 能由菜单 / `inframe` / 直接 URL 打开 | 一般 `title` + `roles` 齐备，`inframe` / `pageLink` 有值 |
| **被引用的片段** | 不是给人直接打开的页面，而是被别的 xwl 用 `url: 'm?xwl=…'` 加载：store 数据源、子面板、动作片段、SQL 载体 | 被别处引用；典型命名如 `transSql/queryXxx`、`.../insert`、`.../delete`、`.../fileUpload` |

**两类的格式规则与处置方式完全相同**，区别只在于：改片段时你要额外确认"谁在用它"。

> SQL 类片段（`dataprovider` + `serverScript` + `{#…#}` / `{?…?}` 占位符）有专门的
> 结构与引用规则，见**第四章**。

### 1.2 `m?xwl=` 引用怎么读（实测结论）

引用写的是**模块相对路径、不带 `.xwl` 后缀**：

```text
m?xwl=orderCenter/highwayTransportationManagement/transSql/queryDriverFile
   → 文件 = wb/modules/orderCenter/highwayTransportationManagement/transSql/queryDriverFile.xwl
```

- **从引用找文件**：补上 `.xwl` 即可。
- **从文件找引用方**：在 xwl 里搜 `m?xwl=<该路径去扩展名>`。
- 被引用的片段是**常态**而不是特例（实测引用点数量级在数千，口径见 [`references/measured-data.md`](references/measured-data.md)）。

### 1.3 控件节点的标准形态（权威来源：设计器的控件注册表）

**别凭印象拼节点字段**。设计器自带一份控件注册表，工程里的位置是
**`wb/system/controls.json`**（实测 133 个控件（另有 13 个面板分组节点）），它对每个控件 id 给出：

- `general` —— `xtype` / ExtJS 类 / 是否容器 / `tag.lib`；
- `configs` —— **该控件允许的全部 configs 键**及类型（`string` / `enum`(带取值列表) / `expBool` / `expJson` / `exp` …）；
- `events` —— **该控件允许的全部事件名**（含参数与类型，`hidden` 的表示面板不暴露）。

查它（工具已内置）：

```bash
# 按设计器面板分组列出全部控件（带 库 / 容器 / 内部 标记）—— 不知道用什么控件时先看它
python scripts/xwl.py schema --tree --controls <工程>/wb/system/controls.json
# 看某控件的合法 configs / events，并给出设计器同款最小骨架
python scripts/xwl.py schema button --controls <工程>/wb/system/controls.json --skeleton
```

**真实控件节点的键集合只有两种**：

```text
["configs", "expanded", "children", "type"]            ← 无事件
["configs", "expanded", "children", "type", "events"]  ← 有事件
```

键序固定是 `configs, expanded, children, type, events`。例如一个真实按钮：

```json
{"configs": {"itemId": "receiveAddBtn", "text": "添加", "iconCls": "record_add_icon"},
 "expanded": false, "children": [], "type": "button",
 "events": {"click": "if (Wb.isEmpty(app.h..."}}
```

> 少写 `expanded` / `children` 运行时通常有默认值兜底，但**会与设计器产物不一致**，
> 下次被设计器保存就产生额外 diff。**用 `schema --skeleton` 生成骨架最稳。**
> `itemId` 是寻址用的（`app.<itemId>`），**必须唯一**。

### 1.4 谁在写它

xwl 是**图形化页面设计器的持久化格式**，设计器保存时会按自己的规则重新排版
（写回算法已破解，见第六章）。所以手工把文件压成一行**维护不住**。

## 二、格式硬规则

磁盘上的形态：

```text
{ ... "click": "var rec = app.headGrid.getSelection()[0];\
if (!rec) {\
  Wb.info('请选择一条记录！');\
  return;\
}" ... }
```

规则（**逐条都是硬要求**）：

1. **编码**：UTF-8，**无 BOM**。
2. **换行必须全文件一致**。加载器 LF / CRLF / CR 都接受（正则 `(\r\n|\r|\n)`），但**同一文件里不能混用**。
   - 设计器在服务器上写的是 **LF**；仓库（git index）里存的也是 LF。
   - Windows 上看到 CRLF，是本机 `core.autocrlf=true` 转出来的
     （实测 `git ls-files --eol` → `i/lf w/crlf`）。
   - → **不要手工改换行**：改了会和 git 的自动转换打架，产生无意义 diff。
3. **续行**：多行字符串里**每行末尾是单个 `\`，紧邻换行**；`\` 后**绝不能有空格或 Tab**。
4. **最后一行不加 `\`**（加了就等于把字符串没闭合）。
   （推论：字符串里的空行 = 该行只有 `\` 一个字符。）
5. **字符串内的 `"` 必须写成 `\"`** → 所以 **xwl 里的 JS 一律用单引号 `'`**，可完全避免转义地狱。

> 为什么是"反斜杠 + 真实换行"：加载器先做
> `text.replaceAll("\\\\(\r\n|\r|\n)", "\\\\n")`，把「反斜杠 + 真实换行」还原成 JSON 的 `\n` 转义，
> 再 `new JSONObject(text.substring(indexOf('{')))`。所以磁盘形态与运行时形态不是一回事。
>
> **加载器用的是 org.json，它比标准 JSON 宽容**：字符串里出现未转义的裸控制字符（如裸换行）
> 它也照收。所以判"能不能加载"别用严格的 JSON 解析器下结论。

## 三、处理流程（四步）

> **先把结论说清楚**：改 xwl 时**可以完全遵循设计器的规则来改、并且不犯错** ——
> 做法是**只给出「值」，让工具按设计器算法重建文件**（第 3 步的结构级 `patch`）。
> 续行符、转义、缩进、换行全部由序列化器产出，你根本不碰文本层，格式错误在构造上就不会发生。

### 第 1 步 · 定位文件

1. 找到目标 `.xwl`。手上只有 `m?xwl=xxx` 这类引用时，**补上 `.xwl`** 再去 `wb/modules/` 下找。
2. 分清这次要改的是**独立页面**还是**被引用的片段 / SQL 载体**（见第一章）——
   影响你改完怎么验证（片段往往没有独立入口，只能靠引用它的页面或直接调 SQL）。
3. 动手前先跑一次 `xwl.py check`：基线本来不合法的话先弄清原因，
   别把既有问题混进这次改动、也别误判成自己改坏的。

### 第 2 步 · 读懂加载机制

`text` 在磁盘上是「反斜杠 + 真实换行」的多行字符串，加载时被还原为 `\n` 转义后按严格 JSON 解析。
**据此得到一个关键推论**：只要能按加载器规则解析成功，就说明格式没问题 —— 这是**最强的校验手段**（见第 4 步 ④）。

### 第 3 步 · 编辑（**默认 `patch`；`edit` 仅例外**）

| 方式 | 命令 | 何时用 |
|---|---|---|
| **结构级 `patch`（默认）** | `xwl.py patch` | **几乎全部改动**：加/删/改控件、挂事件、改配置、换 SQL —— 只提供「对象 / 子树」 |
| 文本级 `edit`（例外） | `xwl.py edit` | 仅当：只改一小段纯文本、且不希望整份文件被重排 |

> 为什么默认是 `patch`：格式（续行 / 转义 / 缩进 / 换行）由序列化器保证，你不接触文本层；
> 且 `--dry-run` 能先看到 diff。**不要**用普通编辑器或通用 Edit 工具直接改 xwl —— 会写成裸 LF。

#### 3.1 结构级 `patch`（默认方式）

`ops.json` 是操作数组，`path` 是「键 / 数组下标」的列表。**节点请用设计器的标准形态**（见 1.3）：

```json
[
  {"op": "set", "path": ["title"], "value": "新标题"},
  {"op": "set", "path": ["@dataprovider", "configs", "sql"], "value": "select 1 from dual\n{#sql#}"},
  {"op": "append", "path": ["children", 0, "children"],
   "value": {"configs": {"itemId": "newBtn", "text": "新按钮", "iconCls": "record_add_icon"},
             "expanded": false, "children": [], "type": "button",
             "events": {"click": "Wb.info('hi');"}}},
  {"op": "delete", "path": ["children", 0, "children"], "index": 3}
]
```

> `path` 里的**对象键**能用 `@itemId` 就用；**数组元素**（如 `children`、`columns`）仍要用下标 —— 两者可混写：`["@grid1","children",0,"configs","title"]`。
>
> **`@itemId` 要求唯一**。重名时工具**不猜顺序** —— 它会**报错并附上候选清单**：每个候选带
> 祖先链（`panel2 › tab1 › grid2`）、原路径、"其下有什么控件"、以及**建议改名与依据**。
> 三条出路：① `@名字#N` 点名第 N 个（N 从 1 起）；② 串联 `@` 段缩小范围（`["@grid2", "@tbar"]`）；
> ③ 按父子关系只改真正要改的那个。**重名的由来、分级与处置流程见第九章。**
>
> ⚠️ `paths` **只列** `sql` / `totalSql` / `serverScript` / `url` 四类字段 ——
> **按钮、网格等控件的 `itemId` 不在它的输出里**。要 `patch` 某个 `events.*`（如给按钮改 `click`）时，
> 用 **`xwl.py itemids <file>`** 看重名报告（第九章），或直接试跑并接受工具的候选清单报错。

**改前先核对（几十秒，省一次返工）**：

```bash
python scripts/xwl.py paths <file.xwl>    # ① 拿到目标字段的真实路径（含 @itemId 写法）
python scripts/xwl.py dump  <file.xwl>    # ② 要看清层级时：解析后美化输出
```

1. **能用 `@itemId` 就别手写下标** —— `paths` 给出的 `["@dataprovider","configs","sql"]`
   不受嵌套层数影响，比 `["children",0,"children",0,"sql"]` 稳得多。
   必须手写下标时，先用 `dump` 确认那一层**确实有**那个元素。
2. 写 `ops.json`（`set` / `insert` / `append` / `delete`）。
3. **先 `--dry-run` 看 diff**，确认"只改了想改的"，再真跑。

```bash
# 先看将产生的 diff（不写入）
python scripts/xwl.py patch <file.xwl> --ops ops.json --dry-run
# 真改（--backup 会先写 <file>.bak）
python scripts/xwl.py patch <file.xwl> --ops ops.json --backup
```

**报错怎么办** —— `patch` 的失败都是**拒绝写盘**，不会留下坏文件：

| 现象 | 原因 | 处理 |
|---|---|---|
| `找不到 …` / 下标越界 | `path` 写错，或那一层没这个元素 | 用 `paths` / `dump` 核对后改 `path`，**别猜** |
| `… itemId == 'x' 有 N 个节点` | `@itemId` 重名，工具不替你猜 | 用 `paths` 给出的**原路径**（带下标），或先把该节点 `itemId` 改成唯一值 |
| 语义等价比对失败 → 中止 | `value` 里有内容重建后解析不回原对象 | 检查 `value` 是否混入异常控制字符；文件**没被动过** |
| 改完 `check` 不通过 | 极少数：`value` 内含异常字符 | 恢复：`cp <file>.bak <file>`（`--backup` 写的备份），或 `git checkout -- <file>` |

三点须知：

1. **ops 按顺序执行**，`path` 按**执行到那一步时的当前结构**解释 ——
   同一个数组上先 `insert` 再 `delete`，下标要按前一步之后的数组算。
2. **事件 JS / SQL / serverScript 都写普通多行字符串**（`\n` 照常写）—— 序列化器会按设计器规则
   转成续行形态，你不用管。JS 里请用**单引号**。
3. **diff 最小化有保证**：工具先比对"源文件是否设计器原样排版"。是 → 重排后逐字节一致，
   diff **只含你真正改的内容**（实测给 377 KB 的页面加一个带多行 JS 的按钮 + 改标题，
   diff **只有 17 行**）。源文件不是设计器原样时，重排会顺带规整整份格式，工具会明确提示。
   - ⚠️ 那种"顺带规整"除缩进外，还可能把值里的 `\uXXXX` 转义**还原成真实字符**
     （实测某页面因此多出 1 处 `\u201c` → `“`，语义等价）。
     **先 `--dry-run` 数一下噪声行数再决定**：噪声只有一两行就照用 `patch`（省心，格式有保证——
     且还原后的形态反而与设计器产物一致）；噪声可观就改用 3.2 的 `edit` 做定点插入
     （语义相同，diff 只含你改的那一处）。
   - 判断噪声量：把 `--dry-run` 输出重定向到文件，数以 `  +` / `  -` 开头的行即可。

> 改 **SQL / serverScript** 时，`path` 用 `["@dataprovider","configs","sql"]` 这类写法 —— 见第四章。

#### 3.2 文本级 `edit`（例外情况）

用它就得自己守两条硬要求：`newline=''` 保留原换行 + **替换前断言锚点唯一**。

```bash
python scripts/xwl.py edit <file.xwl> --old-file old.txt --new-file new.txt --expect 1 --dry-run
```

> 「锚点出现次数」是**信息**不是障碍：工具会报出实际次数。出现多次时把锚点**扩到足够上下文**
> 直到唯一，**不要**用 `--expect N` 去批量替换。

> **两条路都禁止**用普通编辑器 / 通用 Edit 工具直接改 xwl —— 它们会写成裸 LF，破坏格式。

### 第 4 步 · 格式校验（**改完必跑**）

七项检查（**改完必跑**；不通过时先用 `--backup` 的 `<file>.bak` 回退再排查）：

```bash
python scripts/xwl.py check <file.xwl> [more.xwl ...]
python scripts/xwl.py check <file.xwl> --no-js              # 本机没有 node 时跳过 JS 校验
python scripts/xwl.py check <file.xwl> --no-itemid          # 跳过 itemId 重名分级（只查格式）
```

| # | 检查 | 判定 |
|---|---|---|
| ① | 无 BOM | 文件不以 `EF BB BF` 开头 |
| ② | **换行一致（不混用）** | LF-only 与 CRLF-only **都合法**（加载器都收），只有「同一文件里混用」才判失败；单独的裸 CR 也判失败 |
| ③ | 无「反斜杠 + 空白」行 | 任何行都不以 `\` + 空格/Tab 结尾 |
| ④ | **加载器等价解析** | 归一化后 `json.loads` 通过（**解析通过 ⇔ 格式没问题**） |
| ⑤ | 续行结构 | 末行不以 `\` 结尾 |
| ⑥ | 事件 JS 语法 | 抽出所有 `events.*` 的 JS 值 → `node --check` |
| ⑦ | **itemId 重名分级** | **只有「重名 且 已被事件 JS 引用」判 FAIL**；其余重名只出 `[warn]`，不影响结论（分级与处置见第九章） |

> ④ 的写法是**替换成「反斜杠 + 字母 n」两个字符**，不是替换成换行符 —— 写错会误报。
> 等价实现：`re.sub(r'\\(?:\r\n|\r|\n)', r'\\n', text)`，再对 `text[text.index('{'):]` 做 `json.loads`。
>
> ② 别写成「必须 CRLF」—— 设计器与仓库里存的都是 **LF**，那样会把合法文件判成失败。
>
> ⑦ 的 `[FAIL]` 与 ①–⑥ 性质不同：①–⑥ 是**格式**（文件坏了），⑦ 是**命名质量**（文件能用但取值有风险）。
> 所以 `patch` / `edit` / `expand` **写盘后的自动校验只判 ①–⑥** —— 否则会出现"写盘成功却返回非 0"。
> 要看 ⑦ 请单独跑 `check`，或直接 `itemids`。

## 四、SQL 片段：`module.serverScript` ↔ `dataprovider`

被 store 引用的「SQL 文件」不是散装 SQL，而是固定的**两级结构**：

```text
(页面钥匙: title / iconCls / inframe / pageLink / hidden / roles / children)
└─ type="module"          configs{ itemId, serverScript }        ← 取参数、拼条件
   └─ type="dataprovider" configs{ itemId, sql, totalSql?, … }   ← 执行 SQL、出数据
```

改 SQL 时最容易错的就是下面三条，先记住：

1. **`dataprovider.sql` 用 `{#名字#}` 引用 `serverScript` 注入的值** ——
   源头是 `request.setAttribute('sql', …)`，所以 SQL 里写 `{#sql#}`。
2. **`{#sys.*#}` / `{#Str.*#}` 是框架内置**（会话 / 权限），不用自己提供；
   **`{?名字?}` 是绑定参数**（`PreparedStatement`，不是文本替换 —— 别手工拼值）。
3. **参数名 = 控件的 `itemId`**，一路同名到 `{?名字?}`；**对不上不会报错，只取到 null，
   SQL 条件静默失效**。页面把值送出来有两条通路（`out` / `params`），**新写查询推荐 `out`**。

**一条硬规则（有源码原文）**：**serverScript 里禁止写 `{#…#}`** ——
`ServerScript does not support {#param#} feature, please use app.get(param) instead.`
在 serverScript 内部取参数要用 `app.get('名字')`。

改 SQL 同样走 `patch`，用 **`@itemId` 寻址**（不用知道嵌套层级）：

```bash
python scripts/xwl.py paths   <file.xwl>                            # 拿路径（同时给「原路径」与「@写法」）
python scripts/xwl.py patch   <file.xwl> --ops ops.json --dry-run   # 看 diff
python scripts/xwl.py sqlrefs <file.xwl>                            # 改完验 {#名字#} 与 serverScript 是否自洽
```

```json
[
  {"op": "set", "path": ["@dataprovider", "configs", "sql"],
   "value": "select ofi.* from order_file ofi\nwhere 1=1\n{#sql#}"},
  {"op": "set", "path": ["@module", "configs", "serverScript"],
   "value": "var data = app.get();\nvar sql = '';\nrequest.setAttribute('sql', sql);"}
]
```

**展开内容** → [`references/sql-fragments.md`](references/sql-fragments.md)：
两个字段的合法 configs 全集、三种占位符对照表、执行器类与源码依据、serverScript 常用 API 词频、
`out` / `params` 两条通路的完整规则（收集机制、`%` / `$` 前缀、重名与 `hidden` 行为、
同名时谁覆盖谁）、命名契约与完整链路、`sqlrefs` / `params` 的用法与实测数字。

## 五、xwl 的引用方式（数据源 / 子页面 / 后台方法）

一个 `.xwl` 向外引用别的 xwl 或后台方法，只有下面这几条通路。
**先看总表**，再看每条的写法与"回传后前台怎么处理"。

| 引用什么 | 写法 | 写在哪里 | 实测次数 |
|---|---|---|---|
| **数据源**（SQL 文件） | `store.configs.url = 'm?xwl=…'`（配合 `store.load({out})`） | store 节点的 `configs.url` | 2735 |
| **服务端片段**（SQL / 校验 / 取数） | `Wb.request({ url:'m?xwl=…', params, success })` | 控件的 `events.*` 里 | 1702 |
| **子页面**（列表页 / 弹窗） | `Wb.open({ url:'m?xwl=…', title, params })` | `events.*` 里 | 52 |
| **文件上传 / 导入入口** | `Wb.upload({ form: app.form1, url:'m?xwl=…', success })` | `events.*` 里 | 132 |
| **后台 Spring 方法** | `Wb.requestAg({ params:{ bean, method, …业务参数 } })` | `events.*` 里 | 1534 |
| **服务端 xwl 调 xwl** | `app.execute('m?xwl=…')` | `module.configs.serverScript` | 1 |

### 5.1 url 的三种写法

| 写法 | 例 | 说明 |
|---|---|---|
| `m?xwl=<模块相对路径，**不带 `.xwl`**>` | `m?xwl=orderCenter/…/transSql/queryOrderHead` | **最常用**。相对 `wb/modules/`，补 `.xwl` 就是文件路径（见 §1） |
| `/<短名>` | `/upload`、`/get-file`、`/download` | 短名注册表 **`wb/system/url.json`**，框架内部端点。改动时别自己编短名 |
| `http://…` 或任意 url | `Wb.open({url:'http://…', inframe:true})` | 外部地址必须 `inframe:true` |

> `Wb.request` / `Wb.open` / `Wb.upload` / `Wb.requestAg` 的 `url` 都可以给**完整带查询串**的形式，
> 但参数的规范位置是 `params`（或 `out`），不要手拼查询串。

### 5.2 引用位置：这些代码写在 xwl 的哪一处

| 位置 | 放什么 |
|---|---|
| `控件.events.click` / `ok` / `beforeedit` / `select` … | `Wb.request` / `Wb.open` / `Wb.requestAg` / `Wb.upload`（**最常见**） |
| `store.configs.url` | 数据源指向 SQL 文件 |
| `store.configs.autoLoad` (+ `configs.params`) | 首屏自动加载，用固定参数 |
| `column.configs.renderer` | 列渲染时取数（少见） |
| `module.configs.serverScript` | 服务端 `app.get` / `app.run` / `app.send` / `app.rundomain` / **`app.execute(url)`** |
| xwl 顶层 `inframe` / `pageLink` | 页面本身的打开方式（是否 iframe、菜单/链接地址） |

> 事件 JS 一律用**单引号**（xwl 的字符串转义规则，见 §2）。

### 5.3 `Wb.request`：请求一个服务端片段

```js
// 查询/校验/取数：不建页面，只要结果
Wb.request({
  url: 'm?xwl=agWeb/agWebAboutUs/aboutusdata/selectAboutUsInsertStatus',
  params: values,                 // 或 out: app.editWin（整包收容器内控件值）
  // async: false,                // 需要同步拿结果时
  success: function (resp) {
    var data = Wb.decode(resp.responseText);   // ← 回传后前台的标准取法
    ...
  },
  failure: function (resp) {
    Wb.info('失败：' + resp.responseText);
  }
});
```

回传后前台怎么处理（**四种响应形态对应四种取法**）：

| 响应的来源节点 | `resp.responseText` 是什么 | 前台怎么写 |
|---|---|---|
| `dataprovider`（执行 SQL） | JSON：`{"success":true,"rows":[…],"total":n}` | `Wb.decode(resp.responseText).rows` / `.total` |
| `serverScript` + `app.send(x)` | `x` 本身（字符串/数字/JSON 文本） | 直接比较或用 `Wb.decode` |
| `app.run(sql)`（serverScript 里执行 SQL） | 结果集（框架已处理 null） | `Wb.decode(...)` 后按 rows 用 |
| 出错 | 错误文本 / `{"msg":"…"}` | 交给默认 `Wb.except`，或自己 `Wb.info(...)` |

要点：

- **参数怎么给**：`params: {...}` 或 `out: app.<容器>` —— 完整规则（收哪些控件、两个 API 覆盖方向相反）
  见 [`references/sql-fragments.md`](references/sql-fragments.md) 第五节。
- **别用 `Wb.request` 代替 store**：列表/分页/排序要用 `store.load(...)`（框架会带上 `page`/`start`/`limit` 并处理返回）。
- 默认**失败自动弹错**；不想弹就 `showError: false`，自己处理 `failure`。
- `callback` 会先于 `success`/`failure` 被调用，签名是 **`(form, action, value, success)`**（比 `success` 多一个布尔），**返回 `false` 可跳过**后续处理（用于统一拦截）。
- 返回值是请求对象，可用于取消：`var req = Wb.request({...}); req.abort?` → 实际用 `Ext.Ajax.abort(req)`。
- 相关近亲：`Wb.submit(url, params, target, method, isUpload)`（常规表单提交，涉及文件必须用它）、`Wb.download(url, params, isUpload, method)`（下载）。

### 5.4 `Wb.open`：打开子页面（列表页 / 弹窗）

```js
Wb.open({
  url: 'm?xwl=settlementCenter/payFeeManagement/billPay/FFbillPayList',
  title: '应付对账单',
  iconCls: '',
  params: { FEE_BILL_NO: data.feeBillNo }     // 子页面里 app.get('FEE_BILL_NO') 可取
});
```

- 在首页 / IDE 环境下**开成 tab 页并复用**；否则新窗口打开。同路径已打开时**默认激活已有 tab**；
  想强制新开就带 `params`（或显式 `newTab: true`）。
- 常用选项：`title` / `iconCls` / `icon` / `params` / `mask` / `showError` /
  `inframe`（外部 url 用）/ `frameOnly`（只建 tab 不加载）/ `reload`（已存在则重载）/
  `container`（挂到指定容器）/ `newWin`（新窗口表单提交）/ `download`。
- 回调：`success(appScope, responseText)` / `failure(appScope, responseText)`，`this` 指向那个 tab 卡片。
- **只想请求不要 tab** → `Wb.run({url, params, success})`（= `Wb.open` + `container:false`）。

### 5.5 `Wb.upload`：文件上传 / 导入入口

```js
// ① 先把文件传到"上传承载页"，拿回服务端返回的值（通常是文件路径/新文件名）
Wb.upload({
  form: app.form1,                 // 必填：含 file 控件的 form 面板
  url: 'm?xwl=agWeb/AgWebDownload/downloaddata/fileUpload',
  showProgress: true,
  // out: app.form1,               // 也可显式指定取值的容器
  success: function (form, action, value) {
    app.DOWNLOAD_URL.setValue(value);   // ← value = action.result.value
  },
  failure: function (form, action, value) {
    var d = Wb.decode(action.response.responseText);
    Wb.info('导入失败：' + d.msg);
  }
});
```

**回调签名（框架改过 ExtJS，官方就是三参）** —— `ext-all-debug.js` 的
`Ext.form.Basic.afterAction`：`Ext.callback(action.success, scope, [me, action, value])`，
其中 `value = action.result.value`（服务端返回值），`action` 是 form action 对象：

| 回调 | 签名 | 关键取值 |
|---|---|---|
| `success` | `(form, action, value)` | `value` = 服务端返回值 |
| `failure` | `(form, action, value)` | `action.response.responseText` → `Wb.decode(...).msg` |
| `callback` | `(form, action, value, success)` | 返回 `false` 可跳过 success/failure |

> 项目里大量写成 `success: function(action, form1, value)`——**参数名与实际顺序错位一位**
> （`action` 实际是 form、`form1` 实际是 action）。只用到第 3 个参数 `value` 时**照样能跑**，
> 但新写代码请按官方顺序 `(form, action, value)`。失败分支里的 `failure: function(resp, action)`
> 同理：`action` 才是 action 对象，所以 `action.response.responseText` 能取到。
> 另外 `form.form.submit` 走的是 form 提交通道，`_jsonresp=1` 由框架自动加。

**导入类页面的典型两步链**（项目里最标准的导入写法）：

```text
① Wb.upload  → 上传承载页 xwl（如 agWeb/…/fileUpload.xwl）→ 拿到文件在服务端的值
② Wb.request → 校验页 xwl（可多个，如 selectXxxInsertStatus / …UpdateStatus）
③ Wb.requestAg → 落库（bean/method），成功回调里关窗 + store.load() + Wb.tip
```

### 5.6 `Wb.requestAg`：调后台 Spring 方法

**只看前台这一侧** —— 后台方法怎么写属于后端范围，不在本 skill 内；这里只说"怎么调、怎么收"。

```js
Wb.requestAg({
  params: {
    bean: 'OrderCenterController',   // 后台 bean 名（必须）
    method: 'saveMethod',            // 方法名（必须）
    ecPublicAboutUsData: values,     // 业务参数：键名就是后台取参名
    data: Wb.encode(rows)            // 表格批量数据用 data 键（JSON 字符串）
  },
  success: function (resp) {
    win.close();
    app.grid1.store.load();
    Wb.tip('保存成功');
  }
});
```

前台侧的约定：

| 项 | 约定 |
|---|---|
| url | **不用写**，框架固定改成 `m?xwl=common/save-all`（`wb-debug.js` 里写死） |
| 保留键 | `bean` / `method` —— 必须给，且与业务参数平铺在同一层 |
| 业务参数 | 其余键原样变成请求参数；**后台按同名取**（`app.get('x')` 同源）。参数名必须与后台一致，否则取到空 |
| `out` | 同样支持，合并规则与 `Wb.request` 一致（`out` 覆盖 `params`） |
| 表格批量增删改 | 用 `data`（`Wb.encode(...)` 的 JSON 字符串）+ 配套键 `datatable` / `className` / `insertSql` / `updateSql` / `deleteSql`（实测 Top 组合） |
| 同一 bean 多方法 | 只改 `method` 即可，`bean` 复用 |

> 实测常用业务参数名与频次（`idList` / `datatable` / `className` / `insertSql` / `updateSql` / `deleteSql`…）见 [`references/measured-data.md`](references/measured-data.md)。

**后台传回后，前台怎么处理**（1534 个调用点统计）：

| 处理动作 | 占比 | 说明 |
|---|---|---|
| `Wb.tip('保存成功')` / `Wb.info` 提示 | 91% | 最普遍 —— **多数场景根本不看返回值** |
| `store.load()` / `store.reload()` 刷新 | 78% | 列表/明细重新取数 |
| `win.close()` 关窗 | 29% | 弹窗式新增/编辑保存后的标配 |
| 读 `resp.responseText` | 66% | 返回值常是**普通文本/数字**，直接 `if (data == 1)` |
| `Wb.decode(resp.responseText)` | 43% | 返回值是 JSON 时才解析 |
| `Wb.warn(...)` 走失败分支 | — | 后台返回非预期值时常自己判 `else` 分支 |

要点：

- **成功/失败的分界由响应决定**：框架判断为成功才走 `success`；业务上的"失败"往往由后台返回一个
  非预期值，**前台自己 `if/else` 判**（例：`if (data == 1) {…} else { Wb.warn('操作失败') }`）。
- `failure` 回调拿到的是 `(resp, options)`；错误文本在 `resp.responseText`。
  默认**框架会自动弹错**（`Wb.except`），要自己接管就 `showError: false`。
- 上传类失败的错误对象不同（`action.response.responseText` → `{msg}`），见 §5.5 —— **别混用**。
- 保存成功后的标准三连：**关窗 → 刷新来源 store → `Wb.tip` 提示**。来源 store 可能是父页面
  （`app.grid1.store.load()`）或当前弹窗（`win.close()` 前先拿引用）。

## 六、单行源 vs 多行源（决定性规则）

改之前先判形态 —— `xwl.py check` 会给出提示。**两种源的处置完全不同**：

| 源形态 | 处置 |
|---|---|
| **多行源**（含结构换行） | **绝对不能压成一行**，任何理由都不行 |
| **单行源**（整份紧凑一行） | 就在一行形态上改；**可以**转成多行，且能做到与设计器逐字节一致 |

### 6.1 多行源为什么绝不能压成一行

「压缩」有两种，只有第一种是对的：

| 做法 | 替换内容 | JSON 合法？ | 加载后的 JS | 格式/语法校验能拦住吗 |
|---|---|---|---|---|
| **A 正确** | `\`+换行 → `\n`（两个字符的转义） | ✅ | 换行**保留**，语义等价 | — |
| **B 错误** | `\`+换行 → **直接删除**（"合并行"） | ✅ **依然合法** | 换行**消失**，代码粘连 | ❌ **拦不住** |

做法 B 是**静默语义损坏**：

- `//` 行注释会**把后面的代码整段注释掉** → 实测这类结果 `node --check` **返回 0（语法通过）**，
  因为"只剩一句注释"本身是合法 JS。**格式校验、语法校验全都放行。**
- 依赖换行的 ASI 语义会静默改变：`return` / `throw` / `++` / `--` 后面的换行一旦消失，含义就变
  （如 `return` 换行 `{...}` 从"返回 undefined"变成"返回对象"）。
- SQL 侧 token 会粘连（`select 1from dual`）。

→ 所以"有没有被改坏"**只能靠 `git diff` 判断**（`git diff -w` 可忽略空白差异）。

### 6.2 单行源怎么转多行 —— **可行，且能字节级还原**

**结论：可行。** 设计器的写回逻辑已反编译确认并完整复刻，不需要猜排版。

**实际逻辑在哪**

| 项 | 位置 |
|---|---|
| jar | `WEB-INF/lib/Webplatform-1.0.jar` |
| 入口 | `com.wb.interact.IDE#saveFile(...)` —— 按扩展名分派，`.xwl` 交给 `updateModule` |
| 真正写文件 | `com.wb.interact.IDE#updateModule(File, JSONObject, String[], boolean)` |

反编译出的四步（`javap -c -p com.wb.interact.IDE` 可见）：

```java
String s = json.toString(1);                                        // ① org.json 序列化，缩进因子 1
s = s.replaceAll("\\n", "\\\n");                                    // ② 字符串内的 \n 转义 → 反斜杠 + 换行
s = s.replaceAll(System.getProperty("line.separator", "\n"), "\n"); // ③ 换行归一
FileUtil.syncSave(file, s, "utf-8");                                // ④ UTF-8 落盘，不加尾换行
```

**① 不是标准 JSON 美化，是老版 org.json 的 `toString(1)`**，有三条反直觉规则：

1. 每级缩进 **1 个空格**（不是 2/4）。
2. **只有 0 或 1 个元素的容器不换行** → `{"itemId": "x"}`、`[3]` 内联在一行。
3. 单元素容器递归时传的是**当前缩进**而非加一层的缩进 —— 直接产生 `[{`、`}]` 的紧凑写法。

org.json 的字符串转义还有两条：**非 ASCII 原样保留**（中文不转 `\uXXXX`），
但 **`</` 写成 `<\/`**（防 `</script>`）。

**回放校验**（把复刻出的算法跑在项目里既有的文件上，看能否还原原字节）：多行源 1875 个中
**1830 个（97.6%）与原文件逐字节相同** → 说明复刻正确；剩下 45 个都有明确外因（手工改过缩进等）。
完整口径（含 902 个单行源、3 个模板解析失败）见 [`references/measured-data.md`](references/measured-data.md)。

→ 工具已内置：`xwl.py expand`（默认沿用原文件换行；`--eol lf` 取设计器服务器上的原始产物）。

### 6.3 值里的「字面反斜杠 + n」为什么长得别扭

② 的正则是**「字面反斜杠 + n」**，所以值里本来就有这种序列时
（SQL / JS 源码里写的 `\n`，在 JSON 里是 `\\n`），磁盘上会呈现成
「`\\` + 反斜杠 + 换行」这种看着别扭的形态。

**这不是缺陷，语义无损**：加载器的正则 `\\(?:\r\n|\r|\n)` 恰好只吃「**一个**反斜杠 + 换行」，
所以这段在重新加载时会精确还原回原来的 `\n`。回放校验（`queryApproval.xwl` / `queryTrackHead.xwl`）：
忠实模式产出与原文件**逐字节相同**，且两种模式的回读值都与原值一致。

- `expand` 默认**忠实复刻**，产出与设计器逐字节一致；
- `expand --safe` 写成更直观的 `\\n`（语义同样无损，但与设计器产物不同）。
- 两种模式都在写盘前强制做「**重新解析 == 原对象**」的语义等价比对，**对不上就中止**。

## 七、常见坑（都是踩过的）

1. **SQL 抽取别用「反斜杠+换行 → 换行」**：那样 `\"` 会残留成字面 `\"`，灌库直接报 `1064` 语法错。
   正确做法是按加载器规则解析后再取值（`xwl.py sql`）。
2. **`events.tagEvents` 的值是 JSON 对象字面量字符串**（形如 `{"beforeedit": function(e){…}}`），
   不是语句。`node --check` 在"语句位置"看到以 `{` 开头的代码会当成块语句 → **误报语法错误**。
   工具已处理（失败时再包一层括号复验），自己写脚本时要记得这一点。
3. **锚点不唯一就中止，不要"顺手"批量替换** —— 全文相同的 `select`、相同按钮文案都很常见，
   盲替换会把不该动的地方一起改掉。
4. **别只看"解析通过"就以为改对了**：格式校验证明的是"能加载"。
   语义层面的改动（JS 逻辑、SQL 条件）必须用 `git diff` 复核，或用抽取出来的 SQL 实跑。
5. **别用严格的 JSON 解析器判"能不能加载"**：加载器是 **org.json**，字符串里的裸控制字符
   （未转义的换行/Tab）它照收；Python `json` 默认会报 `Invalid control character`。
   本工具用 `json.loads(..., strict=False)` 对齐这个宽容度。
6. **不是所有 xwl 都由设计器写过**：手工改过的文件缩进可能不是 1 空格（见过 4 空格 + 行尾空格）。
   判断排版是否"设计器原样"，别用眼睛看，用 `expand --dry-run` 比字节。

## 八、工具

`scripts/xwl.py`（纯标准库，无第三方依赖）：

| 子命令 | 作用 |
|---|---|
| `patch <file> --ops ops.json [--eol auto\|lf\|crlf] [--indent N] [--dry-run] [--backup]` | **结构级编辑（推荐）**：改对象后按设计器规则整份重建，语义等价比对 + 自动校验。`path` 支持 **`@itemId`** 寻址 |
| `params <page.xwl> [--module-root <wb/modules>] [--controls <…/controls.json>]` | 检查「页面 → store → SQL」传参链路：列出 store 与**两条通路**（`out` / `params`）的传参点；`out` 会**展开容器内的取值控件名**，再与 SQL 的 `{?名?}` / `app.get('名')` 交叉核对；`--list-fields` 只打印取值控件名单 |
| `paths <file>` | 列出**四类字段**（`sql` / `totalSql` / `serverScript` / `url`）的位置，给「原路径」与「`@写法`」；`itemId` 重名时标 ⚠ 并给出 `@名字#N` 点名写法 |
| `sqlrefs <file>` | 检查 SQL 文件里 `{#名字#}` ↔ `serverScript` 的 `setAttribute` 是否自洽；并抓 serverScript 里误用 `{#…#}` |
| `schema [<type>] --controls <wb/system/controls.json> [--tree] [--list] [--skeleton]` | 查设计器控件注册表：`--tree` 按面板分组列出全部控件（带库 / 容器 / 内部标记）、`--list` 只列 id、给 `<type>` 则列该控件合法的 `configs` / `events` 与 `autoNames`、`--skeleton` 出设计器同款骨架 |
| `check <file...> [--no-js] [--no-itemid]` | 七项校验：格式五项 + 事件 JS `node --check` + **itemId 重名分级**（只有「重名且被 JS 引用」判 FAIL）；任一 FAIL 返回非 0 |
| `itemids <file> [--name X] [--dups-only] [--suggest] [--fix auto\|normalName\|itemId] [--json] [--controls <…/controls.json>]` | **itemId 重名报告（只读）**：按「类型 + 是否被 JS 引用 + 有无 normalName」分级，给候选清单（祖先链 / 原路径 / 其下控件）与**建议改名**；`--suggest` 出改名 ops 草稿（需人工确认）；`--name` 配 `--json` 可机器读 |
| `edit <file> --old-file O --new-file F [--expect 1] [--dry-run] [--backup]` | 文本级安全替换，保留原换行，断言出现次数，可选备份 |
| `expand <file> [--out F] [--eol auto\|lf\|crlf] [--indent N] [--safe] [--dry-run] [--backup]` | 规范成设计器同款多行（复刻 `IDE.updateModule`），写盘前做语义等价比对 |
| `dump <file>` | 按加载器规则解析后美化输出（`ensure_ascii=False`） |
| `sql <file>` | 抽取所有含 `sql` 的键对应的 SQL 文本（已正确反转义） |
| `events <file> [--outdir DIR]` | 抽取所有事件 JS 到文件，便于单独检查 |

`node` 定位顺序：`--node <path>` → 环境变量 `NODE_BIN` → `PATH` 里的 `node`；找不到时 JS 校验降级为警告。

三份参考材料（**不必通读，按需查**）：

- [`references/controls.md`](references/controls.md) —— **控件清单**：按设计器面板分组的总表（133 个）、三套控件库、配置载体说明、实测父子结构 Top 45、典型骨架与选型建议。
- [`references/sql-fragments.md`](references/sql-fragments.md) —— **SQL 片段**：两级结构、字段全集、`{#…#}` / `{?…?}` 与 serverScript 的引用关系、执行器与源码依据、页面传参两条通路的完整规则与优先级、`sqlrefs` / `params` 用法。
- [`references/measured-data.md`](references/measured-data.md) —— **实测数据**：引用方式次数、传参两条通路分布、`Wb.requestAg` 参数名与回调动作频次、设计器复刻的回放校验结果、统计口径。

**环境依赖**：Python 3.9+（纯标准库）；Node.js 可选（仅用于事件 JS 语法校验）。
**改完 `xwl.py` 先跑 `python scripts/selftest.py`** 自检（内置样本验证各子命令的关键行为）。

## 九、itemId 命名规范与重名处置

`itemId` 既是设计器里的节点名，**也是事件 JS 取控件的键**。重名**不是一律有问题** ——
判据是三条：**控件类型 + 是否已被 JS 引用 + 有没有 `normalName`**。

### 9.1 框架怎么把控件交给 JS（这决定了重名的后果）

WebBuilder 改过的 `Ext.ComponentManager`（`wb/libs/ext/ext-all-debug.js:21689`，原文）：

```js
register: function (item) {
    this.all.add(item);
    if (item.appScope && (item.normalName || item.itemId))
        item.appScope[item.normalName || item.itemId] = item;      // 普通赋值，不检重
},
unregister: function (item) {
    var all = this.all;
    all.removeAtKey(all.getKey(item));
    if (item.appScope && (item.normalName || item.itemId))
        delete item.appScope[item.normalName || item.itemId];      // 按同名键直接删
},
```

> 行号按某个版本的 `ext-all-debug.js` —— **换版本请按符号名 `ComponentManager.register`
> 去搜**，别按行号找。

两条结论，各自对应一类现象：

1. **注册键是 `normalName || itemId`** —— `normalName` **优先**。所以只要每个同名控件各有互不相同的
   `normalName`，就根本不会撞车，JS 走 `app.<normalName>`。（这就是第二条规则的由来。）
2. 注册是**普通赋值**、`unregister` 是**按同名键直接 `delete`** ⇒
   **后创建的覆盖先创建的**，且**任一重复项被销毁时会把整个名字从页面作用域删掉** ——
   哪怕另一个同名控件还活着。这正是"重名后 `app.X` 取不到值 / 取到的不是你以为的那个"的确切来源：
   **打开一个窗口再关掉，另一个同名控件就"消失"了**（事件 JS 里表现为偶发、难复现的取不到值）。

### 9.2 三类控件，三种规则

| 类型 | 重名 | 依据与约定 |
|---|---|---|
| **grid 的列** `column` / `tcolumn` | **允许** | 命名约定：**字段名 + `_COL` / `Col` 后缀**。取数走 `app.<grid>.getSelection(0).data.XXX`，**不直接取列控件** ⇒ 列名撞车不影响取值 |
| **取值控件**（14 个 `Ext.form.field.*`） | **靠 `normalName` 区分** | 一般是"选中一条数据的详细展现"，`itemId` 默认就用字段名，重名不可避免。**加了 `normalName` 之后 JS 写 `app.<normalName>`** |
| **按钮 / `item` / 面板 / `tab` / `toolbar` / 数据承载** | **不允许** | 新代码**必须**把 `itemId` 区分开。老代码若已如此且**没被 JS 引用**，可以不改；**一旦被 JS 引用就是真 bug** |

第四种情况：`itemId` **不是合法 JS 标识符**（含中文 / 空格 / `.` 等）—— 这种名字只能用
`app.get('名')` 取，点号访问不适用，所以 `itemids` 把这类重名判为无害。

> `normalName` 是**合法 configs 键**，但**不是所有控件都接受**：注册表 `wb/system/controls.json` 里
> 有一部分控件的 `configs` 没有这个键（多是布局 / HTML / 后端节点）。给不接受它的类型写
> `normalName` 属**非法配置** —— `itemids --fix normalName` 会跳过并回报。查具体某控件：
> `xwl.py schema <type> --controls wb/system/controls.json`。

各类在**样本工程**里的实测组数、比例与按类型的分布见
[`references/measured-data.md`](references/measured-data.md) §7。那些数字只是**一个样本的量级参考**，
不要当成通用阈值 —— **在你自己的工程上跑 `itemids` / `check` 才是该工程的真实情况**。

### 9.3 遇到重名：先读父子关系，再把候选交给用户选

**不要**"删一个"、"随便挑一个"、或"重名就不处理"。按这个顺序做：

```bash
python scripts/xwl.py itemids <file.xwl> --dups-only       # 重名组：分级 + 候选清单 + 建议值
python scripts/xwl.py itemids <file.xwl> --name tbar       # 只看一个名字的全部候选
python scripts/xwl.py itemids <file.xwl> --suggest         # 生成改名 ops 草稿（**需人工确认**）
```

1. **读祖先链**判断"哪个才是真正要改的"。例如同名工具栏 `tbar` 分别挂在 4 个 `grid` 下，
   其中 3 个已经各有 `normalName`、只有 1 个没有 —— 要"补"的就是那一个，而不是去动别人。
2. **把候选列给用户，让他选**。工具只提建议、不替用户定；`itemids` 的建议值照**命名惯例**推：
   - **补 `normalName`**（推荐，不动 `itemId`，零破坏）：**原名 + 父级 `itemId` 的"区分段"** ——
     `tbar` 挂在 `gridLeft` 下 → `tbarLeft`；挂在 `gridUser` 下 → `tbarUser`。
   - **改 `itemId`**（须同步改 JS 引用，所以是**兜底手段**）：**父级 `itemId` 作前缀** ——
     父级 `panelX` 下的 `find` 按钮 → `panelX_find`。
3. 用户定了之后才走 `patch`；改 `itemId` 的**必须同步改事件 JS 里的引用**，并复查 `itemids`。

> 优先级：**能用 `normalName` 就用 `normalName`**（`--fix auto` 已如此）—— 它不动 `itemId`，
> 不会破坏任何已有引用；只有类型不接受 `normalName` 时才回退到改 `itemId`。

### 9.4 精确定位某一个：`@itemId#N` 与「串联 `@` 限定」

`path` 里 `@itemId` 段要求唯一；重名时**不猜顺序**，报错并附候选清单。想指名第 N 个（**N 从 1 起**）：

```json
[{"op": "set", "path": ["@tbar#3", "configs", "normalName"], "value": "tbarGrid"}]
```

或者**串联 `@` 段**当"带父级的限定名"用 —— 后一段只在上一段的子树里找：

```json
[{"op": "set", "path": ["@gridUser", "@tbar", "configs", "normalName"], "value": "tbarUser"}]
```

### 9.5 想知道"某个工程里实际有多少重名"

不用问别人要数字 —— 在**你自己的工程**上跑一遍就是最新结果：

```bash
python scripts/xwl.py itemids <file.xwl> --dups-only      # 单文件：分级 + 候选 + 建议值
python scripts/xwl.py check <file.xwl>                    # ⑦ 给出该文件的 error / warn 计数
python scripts/xwl.py itemids <file.xwl> --json           # 机器可读，便于自己汇总
```

样本工程的一份完整分布（各档组数 + 按控件类型的 Top）见
[`references/measured-data.md`](references/measured-data.md) §7.2，可作**量级参考**。

## 十、改完的自检清单

- [ ] 用脚本/工具改的（**没有**用普通编辑器或 Edit 工具）
- [ ] **默认走了结构级 `patch`**（只提供值/子树，格式由序列化器产出）；用了 `edit` 的话能说清为什么
- [ ] **没有把多行源压成一行**（多行源压一行一律禁止）
- [ ] 若是单行源：只在一行形态上改，或已用 `expand` 转成设计器同款多行
- [ ] `xwl.py check` 全绿（含 ④ 加载器等价解析、⑥ 事件 JS 语法）
- [ ] 改了换行符没有？（**全文件一致**即可，别手工改、别和 git 的 autocrlf 打架）
- [ ] 新增/修改的 JS 用的是**单引号**，字符串内没有裸 `"`
- [ ] 若用了文本级 `edit`：锚点在文件里**唯一**（工具已强制）
- [ ] 语义层面的改动已用 `git diff` 复核（格式校验查不出语义变化）
- [ ] 真跑 `patch` 时带了 `--backup`（或改动在 git 里可回退）
- [ ] 改的是**被引用的片段**时，已确认引用它的页面/入口能正常取到
- [ ] 改了引用（`store.url` / `Wb.request` / `Wb.open` / `Wb.upload` / `Wb.requestAg`）时：url 写的是**模块相对路径且不带 `.xwl`**，目标文件确实存在，参数名与下游一致
- [ ] 新增控件时：类型/父节点选对（`container` 才能挂真子控件；`grid` 的列/数据源是**配置载体**，见 `references/controls.md`）
- [ ] 改 SQL 文件时：`xwl.py sqlrefs` 通过（`{#名字#}` 有 serverScript 提供，且 serverScript 里没写 `{#…#}`）
- [ ] 改 SQL 或查询页时：`xwl.py params` 无「SQL 需要但页面未发现来源」的告警（参数名 = 控件 `itemId`，对不上**静默失效**）
- [ ] 用 `out` 通路时：需要的参数控件**确实挂在该容器内**、`itemId` 没改过、类型是**取值控件**（button/label 之类没有 `getValue()`，不会被送）
- [ ] 没有在 `out` 与 `params` 里给**同名参数**写不同值（`store.load` 与 `Wb.request` 的覆盖方向相反）
- [ ] 改 SQL 用的是 `@itemId` 寻址（而不是硬编码 `children[0].children[0]`）
- [ ] `@itemId` 重名时**没有猜第一个**：用了 `@名字#N` 点名，或串联 `@` 段限定，或按父子关系确认过后再改
- [ ] 新增控件时 `itemId` **在文件内唯一**（列控件可重名，但要带 `_COL` / `Col` 后缀；按钮 / 面板 / `tab` / 数据承载**必须**区分开）
- [ ] 若目标是"同一字段名出现在多处明细面板"：**优先补 `normalName`**（`app.<normalName>`），而不是改 `itemId`
- [ ] 改了 `itemId` 的话：**事件 JS 里对它的引用已同步改**，且 `itemids` 复查过
- [ ] `xwl.py check` 的 ⑦ 没有 `[FAIL]`（`[warn]` 级重名知道了就行 —— 老代码可留，新代码别再加）
