# examples —— 可直接跑的最小示例

这个目录里的每条命令**都真实跑过**，输出与下面写的一致。用它建立手感最快。

> **本目录不含预置的 `.xwl`** —— 示例页面由 `xwl.py new` **现场生成**（第一节）。这样示例与
> 你手上的工程完全同源，也不会过期；`ops-add-button.json` 是纯数据，直接给就好。
>
> **复现方式**：下文每个可跑的命令块都先**设两个环境变量再引用**——
> `SKILL_ROOT` 指**本 skill 的安装目录**（`examples/` 的上一层），`TMP_DIR` 指**你自己的临时目录**（放**仓外**）。
> 命令统一写成 `python "$SKILL_ROOT/scripts/xwl.py" … "$TMP_DIR/demo-page.xwl"`（两侧加引号，
> 空格／中文路径也不会挂），**不必**先 `cd` 过去。
> 生成目标请放**仓外** —— `.xwl` 是业务格式、会被平台拒收，也不该混进分发面扫描；示例页面**本就不进仓库**，跑完随手删掉即可。
>
> 下面给 **bash** 与 **PowerShell** 两版；按你用的 shell 照抄对应那一块即可（首个代码块是"设变量"，设完后续块接着用）。

## 一、先生成一个示例页面

bash：

```bash
# 先设变量：把两个路径改成你的实际值（SKILL_ROOT=安装目录，TMP_DIR=仓外临时目录）
export SKILL_ROOT="$HOME/.agents/skills/webbuilder-xwl-patch"   # 或你实际的安装目录
export TMP_DIR="$HOME/tmp-xwl-demo" && mkdir -p "$TMP_DIR"
python "$SKILL_ROOT/scripts/xwl.py" new "$TMP_DIR/demo-page.xwl" --kind page --title "示例页面"
```

PowerShell：

```powershell
# 先设变量：把两个路径改成你的实际值（SKILL_ROOT=安装目录，TMP_DIR=仓外临时目录）
$env:SKILL_ROOT = "$HOME\.agents\skills\webbuilder-xwl-patch"   # 或你实际的安装目录
$env:TMP_DIR = "$HOME\tmp-xwl-demo"; New-Item -ItemType Directory -Force -Path $env:TMP_DIR | Out-Null
python "$env:SKILL_ROOT/scripts/xwl.py" new "$env:TMP_DIR/demo-page.xwl" --kind page --title "示例页面"
```

产出 238 B、单个空 `module` 节点，顶层 7 把钥匙的**键序与设计器一致**（不用手写顶层键）。
SQL 载体的写法见第三节。

> 为什么不让示例躺在仓库里：`.xwl` 是**业务格式**，不同平台/工具链对它的处理不一致
> （例如 SkillHub 的文件类型白名单就不收 `.xwl`）。现场生成能保证"你跑出来的"和"文档写的"
> 永远是同一个东西。

## 二、不适用（先看这条，省得白试）

- 其他低代码平台的页面定义、`.vue`、普通 `.json`
- 后端 Java、模块打包、`target/` 部署副本同步、数据库菜单注册（`WB_MENU`）

## 三、改一个已有文件：给页面加一个带多行 JS 的按钮

第一节生成的 `$TMP_DIR/demo-page.xwl` 是空 `module` 节点。
`examples/ops-add-button.json`（**留在仓内**，是样例数据）是**多 op 序列**：先往 `module.children`
追加一个 `grid`（`itemId=demoGrid`），再往这个网格里追加一个 `button`（`itemId=queryBtn`）。

bash（承接第一节已设的 `SKILL_ROOT` / `TMP_DIR`）：

```bash
# 1) 先看基线格式是否合法
python "$SKILL_ROOT/scripts/xwl.py" check "$TMP_DIR/demo-page.xwl"

# 2) 看这次会改成什么样（不写盘）
python "$SKILL_ROOT/scripts/xwl.py" patch "$TMP_DIR/demo-page.xwl" \
    --ops "$SKILL_ROOT/examples/ops-add-button.json" --dry-run

# 3) 确认后落盘（--backup 会先写 $TMP_DIR/demo-page.xwl.bak）
python "$SKILL_ROOT/scripts/xwl.py" patch "$TMP_DIR/demo-page.xwl" \
    --ops "$SKILL_ROOT/examples/ops-add-button.json" --backup

# 4) 改完必跑校验（默认九项；要连 `configs` 键 / 内联 `[js]` 一起校就加 `--controls`）
python "$SKILL_ROOT/scripts/xwl.py" check "$TMP_DIR/demo-page.xwl"

# 5) 扫一遍：有没有把多行内容悄悄压平（需要 git 仓库；仓外页面不在仓库里 ⇒ 本步以 [note] 跳过、rc=0）
#    要看 diffguard 抓到压平的真实效果（含 --strict 的 rc=1），见第五节的最小实验
python "$SKILL_ROOT/scripts/xwl.py" diffguard "$TMP_DIR/demo-page.xwl"
```

PowerShell（承接第一节已设的 `$env:SKILL_ROOT` / `$env:TMP_DIR`）：

```powershell
python "$env:SKILL_ROOT/scripts/xwl.py" check "$env:TMP_DIR/demo-page.xwl"
python "$env:SKILL_ROOT/scripts/xwl.py" patch "$env:TMP_DIR/demo-page.xwl" `
    --ops "$env:SKILL_ROOT/examples/ops-add-button.json" --dry-run
python "$env:SKILL_ROOT/scripts/xwl.py" patch "$env:TMP_DIR/demo-page.xwl" `
    --ops "$env:SKILL_ROOT/examples/ops-add-button.json" --backup
python "$env:SKILL_ROOT/scripts/xwl.py" check "$env:TMP_DIR/demo-page.xwl"
python "$env:SKILL_ROOT/scripts/xwl.py" diffguard "$env:TMP_DIR/demo-page.xwl"
```

**预期**：第 2 步的 diff 只新增网格与按钮那几行（不重排其它内容）；
第 4 步 `→ OK`；第 5 步在没有 git 时以 `[note]` 跳过并以 rc=0 结束。

> 该样板 `click` 里的 `app.demoGrid` 引用的网格**由本样板自己创建**（先 `append` 了 `demoGrid`，
> 再 `append` 按钮），整份文件**同文件自洽**、可独立跑通。

ops 的完整规范见**第七节**。

## 四、从零造一个 SQL 载体

`new --kind sql` 产出的是两级结构：`module(serverScript)` → `dataprovider(sql)`。

bash：

```bash
mkdir -p "$TMP_DIR/xxxSql"
python "$SKILL_ROOT/scripts/xwl.py" new "$TMP_DIR/xxxSql/queryDemo.xwl" --kind sql --title "示例查询"
python "$SKILL_ROOT/scripts/xwl.py" check "$TMP_DIR/xxxSql/queryDemo.xwl"
python "$SKILL_ROOT/scripts/xwl.py" sqlrefs "$TMP_DIR/xxxSql/queryDemo.xwl"   # {#名字#} 与 serverScript 是否自洽
```

PowerShell：

```powershell
New-Item -ItemType Directory -Force -Path "$env:TMP_DIR/xxxSql" | Out-Null
python "$env:SKILL_ROOT/scripts/xwl.py" new "$env:TMP_DIR/xxxSql/queryDemo.xwl" --kind sql --title "示例查询"
python "$env:SKILL_ROOT/scripts/xwl.py" check "$env:TMP_DIR/xxxSql/queryDemo.xwl"
python "$env:SKILL_ROOT/scripts/xwl.py" sqlrefs "$env:TMP_DIR/xxxSql/queryDemo.xwl"
```

> 注意：`new` 之后还要**登记进所在目录的 `folder.json`**（否则设计器导航树里看不到）：
> `python "$SKILL_ROOT/scripts/xwl.py" folders "$TMP_DIR/xxxSql/queryDemo.xwl" --register`。
> 该目录必须已经被设计器管理（已有 `folder.json`）。

## 五、验证「压平」真的会被抓到（`diffguard` 的最小实验）

在 git 仓库里。bash：

```bash
mkdir -p "$TMP_DIR/flatdemo" && cd "$TMP_DIR/flatdemo" && git init -q
python "$SKILL_ROOT/scripts/xwl.py" new page.xwl --kind page --title "示例页面"
python "$SKILL_ROOT/scripts/xwl.py" patch page.xwl \
    --ops "$SKILL_ROOT/examples/ops-add-button.json"
git add -A && git commit -qm base

# 手动把多行 JS 的续行符删掉（= "合并行"，静默语义损坏）—— 只为演示 diffguard。
# ✅ 字节级单行命令：只删「反斜杠+CRLF」/「反斜杠+LF」续行对（bytes([92,13,10]) / bytes([92,10])），
#    其余字节（含 CRLF / LF）原样保留。命令里用 bytes([92,…]) 表示反斜杠 ⇒ 一个反斜杠都不出现，免疫 shell 吞噬。
# ⛔ 不要用 `re.sub(r'\\\r?\n',…)`（universal newline 会把整份 CRLF 改写成 LF、换行被破坏），也不要用 heredoc（POSIX 可复制性差）。
python -c "import pathlib;p=pathlib.Path('page.xwl');b=p.read_bytes();p.write_bytes(b.replace(bytes([92,13,10]),b'').replace(bytes([92,10]),b''))"

python "$SKILL_ROOT/scripts/xwl.py" check page.xwl          # ← 九项全绿：格式校验查不出来
python "$SKILL_ROOT/scripts/xwl.py" diffguard page.xwl      # ← [warn] 疑似压平，并给出被合并的基线行号
python "$SKILL_ROOT/scripts/xwl.py" diffguard page.xwl --strict   # ← rc=1，可接进 CI
```

> **正当做法（日常编辑一律走这条）**：改 `.xwl` 用 `xwl.py patch`（结构化重建、天然保持原有换行），
> 或 `xwl.py edit`（文本级但只认候选可解析）；⛔ 不要手写正则 / 单行脚本去"压平或拼回"多行字符串
> —— 那正是本节要演示的破坏方式，diffguard 就是为抓它而存在。本节的删续行只为**造坏例**演示。

PowerShell：

```powershell
New-Item -ItemType Directory -Force -Path "$env:TMP_DIR\flatdemo" | Out-Null
Set-Location "$env:TMP_DIR\flatdemo"; git init -q
python "$env:SKILL_ROOT/scripts/xwl.py" new page.xwl --kind page --title "示例页面"
python "$env:SKILL_ROOT/scripts/xwl.py" patch page.xwl --ops "$env:SKILL_ROOT/examples/ops-add-button.json"
git add -A; git commit -qm base
# 手动把多行 JS 的续行符删掉（= "合并行"，静默语义损坏）—— 只为演示 diffguard。
# ✅ 字节级单行命令：只删「反斜杠+CRLF」/「反斜杠+LF」续行对（bytes([92,13,10]) / bytes([92,10])），
#    其余字节（含 CRLF / LF）原样保留。命令里用 bytes([92,…]) 表示反斜杠 ⇒ 一个反斜杠都不出现，免疫 shell 吞噬。
# ⛔ 不要用 `re.sub(r'\\\r?\n',…)`（universal newline 会把整份 CRLF 改写成 LF、换行被破坏），也不要用 heredoc。
python -c "import pathlib;p=pathlib.Path('page.xwl');b=p.read_bytes();p.write_bytes(b.replace(bytes([92,13,10]),b'').replace(bytes([92,10]),b''))"
python "$env:SKILL_ROOT/scripts/xwl.py" check page.xwl
python "$env:SKILL_ROOT/scripts/xwl.py" diffguard page.xwl
python "$env:SKILL_ROOT/scripts/xwl.py" diffguard page.xwl --strict
```

实测输出（5 处续行、6 行 JS 被合并成 1 行）：

```text
$ python "$SKILL_ROOT/scripts/xwl.py" check page.xwl
  [ok]   ① BOM  ② 换行一致  ③ 续行空白  ④ 解析  ⑤ 末行结构
  === 结果: ALL OK            ← 注意：格式校验完全放行

$ python "$SKILL_ROOT/scripts/xwl.py" diffguard page.xwl
  [warn] 疑似把多行内容压平（精确命中）—— 续行符 5 → 0（-5）| 最长行 66 → 139 字符 | 行数 29 → 24
         基线第 15–20 行（6 行）被合并成工作区第 15 行：'   "events": {"click": "var rec = app.demoGrid...'
  === 结果: ALL OK（疑似压平 1 / 无迹象 0 / 跳过 0）   ← 默认只告警

$ python "$SKILL_ROOT/scripts/xwl.py" diffguard page.xwl --strict
  → rc=1
```

> 上面的行数/字符数只是这一次实验的样例（会随内容变），要的只是形状：**diffguard 报「疑似压平」并给出被合并的基线行号**。

这是 `diffguard` 存在的全部理由：**`check` 查不出压平**（压平后文件仍自洽），
而 `diffguard` 能精确指出「基线的哪几行被并成了现在的哪一行」。

## 六、ops 样板清单

`examples/ops-*.json` 都是**多 op 序列**、**纯 JSON 数据**（无注释，说明以本节为准），
每一份都能**从一个 `new --kind page` 的空页开始、一路跑到表格里的"目标形态"**。
各份的 `path` 在**同文件内自洽** —— 目标形态用到的节点，都在同一份里按层级逐步 `append` 出来。

| 文件 | 目标形态（跑完长什么样） | 示范什么决策 | ⛔ 反例 |
|---|---|---|---|
| `ops-add-grid.json` | `module.children` → `grid`(`grid1`) → `store` ＋ `array(columns)` ＋ `column`×3（1 个勾选列、2 个数据列 `code`/`name`） | 层级：`store`／`array`／`column` 各挂谁；列 `itemId` **默认＝字段名**；勾选列用 `configs.xtype:"checkcolumn"` | 列名无条件加 `_COL` 后缀 |
| `ops-add-querybar.json` | `module.children` → `grid`(`grid1`) → `toolbar`(`tbar`) 在 **`grid.children` 里** → `text`＋`combo`＋`date`＋`button` | ⭐ **工具条是网格的 `children`**（不是网格的兄弟）；查询控件类型选择 | 把 `toolbar` 挂在容器下、与 `grid` 成兄弟 |
| `ops-hide-param.json` | `module.children` → `grid` → `toolbar` → 一个 `text` ＋ `configs.hidden:"true"` | ⭐ **不可见参数用其语义类型的控件 ＋ `configs.hidden`**；⭐ **同名不同型**（顶层 `hidden` 是 bool、`configs` 级是字符串 `"true"`） | 造 `type:"hidden"` 控件 |
| `ops-add-window.json` | `module.children` 直接子级 → **两个 `window`**：常驻档（`closeAction:"hide"`）＋ 重建档（`createInstance:"false"` ＋ `closeAction:"destroy"`，并设 `header:"false"`） | 弹层**两档**的区别与**成套**（重建档两键必须**齐**）；⚠️ 窗口**必须挂 `module` 直接子级**才拿得到 `app.<id>`；`layer` 的 `title:false` → `header:false` 的映射 | 档位张冠李戴（重建档只写一个键） |
| `ops-required-check.json` | `module.children` → `grid` → `toolbar` → `text`(`keyword`) ＋ `button`，其 `events.click` 内含**判空＋提示** | ⭐ **必填校验写在 `click` 里**（内联判空）；`app.keyword` 引用**同文件已创建**的控件 | 加 `allowBlank`／`blankText`（查询工具条不是表单） |
| `ops-renderer-body.json` | `grid` → `array(columns)` → `column`，其 `configs.renderer` ＝ **函数体形态** | ⭐ **`renderer` 取函数体**（`"return …;"`），**不是**函数表达式 | 写 `"function(v){…}"` |
| `ops-extlink.json` | `panel` → `label`（`html` 里含**展示类**外链）＋ `button`（`click` 里做 `window.open` **跳转类**） | ⭐ **外链两分法**（展示 vs 跳转）；平台 `a` 控件**无 `target`** ⇒ 要"新窗口"只能写进 JS | 把**展示用**行内链接**提升成独立控件** |
| `ops-set-store-url.json` | `grid` → `store`，其 `configs.url` ＝ `m?xwl=<模块>/xxxSql/queryDemo`（占位写法） | ⭐ **取数 url 的占位写法**；SQL 载体归 `new --kind sql`；服务端分页 `pageSize` **不填**；`totalSql` **分场景**（详见 `references/transcription-defaults.md`） | 写真实模块路径；`totalSql` 一律照抄 |
| `ops-add-button.json` | `module.children` → `grid`(`demoGrid`) ＋ 挂其上的 `button`(`queryBtn`)，`click` 里引用 `app.demoGrid` 的选中行 | 事件 JS 的**单引号**与**手写 `\n`**；`app.<id>` 必须**同文件已创建** | 引用未创建的控件（自洽性破坏） |

### 复现（每份都从空页跑到底）

把 `OPS_FILE` 设成表里任一份（如 `ops-add-grid.json`），生成的页面放**仓外**的 `$TMP_DIR`：

bash：

```bash
OPS_FILE="ops-add-grid.json"   # 换成表里任一份：ops-add-grid.json / ops-add-button.json / …
python "$SKILL_ROOT/scripts/xwl.py" new "$TMP_DIR/demo-page.xwl" --kind page --force
python "$SKILL_ROOT/scripts/xwl.py" patch "$TMP_DIR/demo-page.xwl" --ops "$SKILL_ROOT/examples/$OPS_FILE"
python "$SKILL_ROOT/scripts/xwl.py" check "$TMP_DIR/demo-page.xwl"
```

PowerShell：

```powershell
$OPS_FILE = "ops-add-grid.json"   # 换成表里任一份：ops-add-grid.json / ops-add-button.json / …
python "$env:SKILL_ROOT/scripts/xwl.py" new "$env:TMP_DIR/demo-page.xwl" --kind page --force
python "$env:SKILL_ROOT/scripts/xwl.py" patch "$env:TMP_DIR/demo-page.xwl" --ops "$env:SKILL_ROOT/examples/$OPS_FILE"
python "$env:SKILL_ROOT/scripts/xwl.py" check "$env:TMP_DIR/demo-page.xwl"
```

> 这些样板**都真跑过**，第 3 步的 `check` 一律 `ALL OK`。
> `--force` 只是省去「重复生成时先删旧的」这一步；`check` 通过即说明跑到了表里的目标形态。

## 七、怎么规范写 ops

写 `ops.json` 时**只给结构**，格式一律交给工具；下面这几条是踩过的坑，按它写基本不会返工。

1. **只给「值 / 子树」** —— 续行符 `\`、转义、缩进、换行**全部由工具产出**，不要碰文本层。
2. **多行 JS 手写 `\n`** —— 照 `ops-add-button.json` 里 `click` 的写法，工具会把它转成磁盘上的**续行形态**。
3. **JS 一律单引号** —— 见各份样板的 `events`。
4. **`path` 与结构的对应**：`["children",0,"children"]` 里的 `children[0]` 就是空页的**第一个子节点**（即 `module`），
   所以这个 `path` 指的就是 **`module.children`**；后续 op 建议改用 **`@itemId` 寻址**（形如 `["@grid1","children"]`），
   比硬编码数组下标健壮，且让**同一份文件内自洽**。
5. ⚠️ **看参数、别抄 `path`** —— `path` **依附结构**，结构一变 `path` 就失效；
   要照的是「**参数该是什么**」，不是「上次 `path` 写了啥」。
6. ⚠️ **给 `set` 赋一个还不存在的键会被默认拒绝**（设计如此，需显式放行）。三种解法，按推荐顺序：
   - **`append` 时就把该键带上**（**推荐**，见 `ops-set-store-url.json`）；
   - 给该 op 加 `"create": true`；
   - 命令行加 `--allow-new-key`。

