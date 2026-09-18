# examples —— 可直接跑的最小示例

这个目录里的每条命令**都真实跑过**，输出与下面写的一致。用它建立手感最快。

> **本目录不含预置的 `.xwl`** —— 示例页面由 `xwl.py new` **现场生成**（第一节）。这样示例与
> 你手上的工程完全同源，也不会过期；`ops-add-button.json` 是纯数据，直接给就好。
>
> 复现方式：先 `cd` 到本 skill 根目录（`examples/` 的上一层）。
> 生成出来的 `.xwl` 若不想留在仓库里，删掉即可（它是可复现的产物）。

## 一、先生成一个示例页面

```bash
python scripts/xwl.py new examples/demo-page.xwl --kind page --title "示例页面"
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

第一节生成的 `examples/demo-page.xwl` 是空 `module` 节点。
`examples/ops-add-button.json` 要往它的 `module.children` 里追加一个按钮。

```bash
# 1) 先看基线格式是否合法
python scripts/xwl.py check examples/demo-page.xwl

# 2) 看这次会改成什么样（不写盘）
python scripts/xwl.py patch examples/demo-page.xwl \
    --ops examples/ops-add-button.json --dry-run

# 3) 确认后落盘（--backup 会先写 examples/demo-page.xwl.bak）
python scripts/xwl.py patch examples/demo-page.xwl \
    --ops examples/ops-add-button.json --backup

# 4) 改完必跑校验
python scripts/xwl.py check examples/demo-page.xwl

# 5) 提交前扫一遍：有没有把多行内容悄悄压平（需要 git 仓库）
python scripts/xwl.py diffguard examples/demo-page.xwl
```

**预期**：第 2 步的 diff 只新增按钮那几行（不重排其它内容）；
第 4 步 `→ OK`；第 5 步在没有 git 时以 `[note]` 跳过并以 rc=0 结束。

关键点：
- 你**只提供「值 / 子树」**（`ops-add-button.json`），续行符、转义、缩进、换行全部由工具产出 —— 不碰文本层。
- 多行 JS 在 `ops.json` 里**就写 `\n`**（见该文件里 `click` 的值），工具会转成磁盘上的续行形态。
- JS 里一律用**单引号**。

## 四、从零造一个 SQL 载体

`new --kind sql` 产出的是两级结构：`module(serverScript)` → `dataprovider(sql)`。

```bash
python scripts/xwl.py new /tmp/<你的模块>/xxxSql/queryDemo.xwl --kind sql --title "示例查询"
python scripts/xwl.py check  /tmp/<你的模块>/xxxSql/queryDemo.xwl
python scripts/xwl.py sqlrefs /tmp/<你的模块>/xxxSql/queryDemo.xwl   # {#名字#} 与 serverScript 是否自洽
```

> 注意：`new` 之后还要**登记进所在目录的 `folder.json`**（否则设计器导航树里看不到）：
> `python scripts/xwl.py folders <文件> --register`。该目录必须已经被设计器管理（已有 `folder.json`）。

## 五、验证「压平」真的会被抓到（`diffguard` 的最小实验）

在 git 仓库里：

```bash
git init -q /tmp/flatdemo && cd /tmp/flatdemo
python <本 skill>/scripts/xwl.py new page.xwl --kind page --title "示例页面"
python <本 skill>/scripts/xwl.py patch page.xwl \
    --ops <本 skill>/examples/ops-add-button.json
git add -A && git commit -qm base

# 手动把多行 JS 的续行符删掉（= "合并行"，静默语义损坏）
python - <<'EOF'
import re, pathlib
p = pathlib.Path("page.xwl")
p.write_text(re.sub(r"\\\r?\n", "", p.read_text(encoding="utf-8")), encoding="utf-8")
EOF

python <本 skill>/scripts/xwl.py check page.xwl          # ← 七项全绿：格式校验查不出来
python <本 skill>/scripts/xwl.py diffguard page.xwl      # ← [warn] 疑似压平，并给出被合并的基线行号
python <本 skill>/scripts/xwl.py diffguard page.xwl --strict   # ← rc=1，可接进 CI
```

实测输出（5 处续行、6 行 JS 被合并成 1 行）：

```text
$ python scripts/xwl.py check page.xwl
  [ok]   ① BOM  ② 换行一致  ③ 续行空白  ④ 解析  ⑤ 末行结构
  === 结果: ALL OK            ← 注意：格式校验完全放行

$ python scripts/xwl.py diffguard page.xwl
  [warn] 疑似把多行内容压平（精确命中）—— 续行符 5 → 0（-5）| 最长行 66 → 139 字符 | 行数 29 → 24
         基线第 15–20 行（6 行）被合并成工作区第 15 行：'   "events": {"click": "var rec = app.demoGrid...'
  === 结果: ALL OK（疑似压平 1 / 无迹象 0 / 跳过 0）   ← 默认只告警

$ python scripts/xwl.py diffguard page.xwl --strict
  → rc=1
```

这是 `diffguard` 存在的全部理由：**`check` 查不出压平**（压平后文件仍自洽），
而 `diffguard` 能精确指出「基线的哪几行被并成了现在的哪一行」。
