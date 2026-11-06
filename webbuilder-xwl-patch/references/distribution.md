# 分发与安装：装到哪个目录、怎么升级、命令在哪个 cwd 跑

本文管**把这份 skill 装到本机**：有哪些渠道、装完落在哪、升级与卸载怎么走，以及
「命令在哪个目录里跑」这条最容易踩的边界。装好之后怎么用见 [`../SKILL.md`](../SKILL.md)；
可直接跑的最小示例见 [`../examples/README.md`](../examples/README.md)。

## 一、两种安装渠道

| 渠道 | 适合谁 | 怎么装 |
|---|---|---|
| **Agent Skills CLI**（`npx skills`） | 用支持 **Agent Skills** 规范的客户端（Codex / Cline / CodeBuddy 等） | 见下一节的五条命令 |
| **手工拷目录** | 只要一台机器、不想引入 npm；**或客户端不在 CLI 的 agent 表里** | 把**技能运行面目录**（`webbuilder-xwl-patch/`）整个拷进客户端的 skill 目录（或 `git clone` 仓库后把该子目录作为 skill 目录） |

目录本身就是通用布局（`SKILL.md` ＋ `references/` ＋ `examples/` ＋ `scripts/xwl.py`），
**没有平台专属封装**；两条渠道使用同一套技能内容，但 CLI 安装副本**可能不含 `metadata.json`** 等源码树文件，
开发用的 `scripts/selftest.py`、`tests/` 也不在副本里（见 §五），不能无条件承诺逐文件相同。

> **WorkBuddy 只能走手工那一条**：CLI 的 agent 表里没有它 ⇒ 把目录放到
> `~/.workbuddy/skills/<name>`（Windows 上即 `%USERPROFILE%\.workbuddy\skills\<name>`）。

## 二、五条命令

```bash
npx skills add yfwang0731/skill-webbuilder-xwl-patch --list
npx skills add yfwang0731/skill-webbuilder-xwl-patch --skill webbuilder-xwl-patch -g -a codex
npx skills check
npx skills update webbuilder-xwl-patch -g -y
npx skills remove webbuilder-xwl-patch -g -y
```

第一条**只看不装**（先确认清单）；第二条才是真装：`-g` 全局，`-a <agent>` 选客户端。

### 两条必须先读的注记

1. **`skills check` 与 `update` 是同一套实现**（`--help` 里没有列出 `check`）⇒
   **执行前请假定它会改动已装内容**。要"只看不写"，用第一条那种纯读命令，或先备份。
2. **装到哪个目录取决于 `-a`**：canonical 全局目录是 `~/.agents/skills`，但只有 `cline`／`codex`
   的字面等于它；`codebuddy` 落在 `~/.codebuddy/skills`。**CLI 的 agent 表里没有 `workbuddy`**
   ⇒ ⛔ 别假设"装完 WorkBuddy 就生效"，自装时要指到客户端真正读取的 skill 目录。

## 三、环境依赖三件（⛔ 别混成一句）

| 用途 | 需要什么 | 缺了会怎样 |
|---|---|---|
| 跑 `xwl.py` | **Python 3.9+**（纯标准库，无第三方依赖） | 跑不起来 |
| 事件的 JS 语法校验（`check` 的第 ⑥ 项） | **Node**（可选） | 少守一层：该项自动降级为警告 |
| 用 `npx skills` 装／更新 | **Node ＋ npm**（**不是可选**） | 装不了；此时改走"手工拷目录" |

## 四、命令在哪个目录里跑（最容易踩的一条）

`xwl.py` 是**独立脚本**，与业务工程没有位置关系 ⇒ **入口一律写全路径**：

```bash
python <skill根>/scripts/xwl.py check <业务工程>/wb/modules/<模块>/某页.xwl
```

- `<skill根>` ＝ **装好的那份 skill 目录**（`-a codex` 下即 `~/.agents/skills/webbuilder-xwl-patch`）；里面有 `SKILL.md`、`references/`、`examples/`、`scripts/xwl.py`。
- `<repo>` ＝ **源码树根**（git 仓库根，含 `webbuilder-xwl-patch/`、开发用的 `scripts/selftest.py` 与 `tests/`）—— 只用于开发自检（见 §五），**不是**安装目录，也不随安装副本分发。
- 在**业务工程**里 `cd` 着跑、却只写**裸相对路径** ⇒ **找不到脚本**（本页把 `<skill根>` / `<repo>` 都写全了）。
- 路径带空格或中文（Windows 上很常见）时**两侧都加引号**：
  `python "<带空格 的 skill根>/scripts/xwl.py" "<带空格 的工程>/某页.xwl"`。
- 工具失败时打印的"重跑"提示里，入口已经是**本机绝对路径**（尾段仍是 `scripts/xwl.py`），直接粘。

### ⛔ 别往 skill 安装目录写东西

安装目录会被 `skills update` **整体覆盖**，也可能是**只读**的。所以：

- `--ops` 用的 ops 文件、生成的 `.xwl`、`.bak` 备份、临时夹具 —— 一律放**业务工程或你自己的临时目录**；
- 唯一例外是 `examples/ops-*.json`：随包分发的样例数据，**读它、不改它**。
- 判据是"这次写的落点会不会被下一次更新抹掉"：会 ⇒ 不属于安装目录。

## 五、升级与卸载

- 升级：`npx skills update webbuilder-xwl-patch -g -y`（⚠️ 先读第二节注记 1，假定它会写）；
- 卸载：`npx skills remove webbuilder-xwl-patch -g -y`；
- 手工装的：删目录即可 —— 本 skill **不在系统任何位置留状态**（无缓存写、无注册表、无后台进程）；
- **安装副本不含自检脚本**：`selftest.py`、`tests/` 只存在于**源码树**（`<repo>`），任何安装渠道（CLI／手工拷目录）都不分发它们 ⇒ 装完只承诺 §六 的运行面冒烟（`xwl.py check`），⛔ 不要在安装目录里找 `selftest.py` 或 `--list-blocks`。
- **源码树自证**（仅开发／维护者）：在**源码树根**跑 `python <repo>/scripts/selftest.py`（内置样本、不需要业务工程；源码树须含 `webbuilder-xwl-patch/`（其中 `metadata.json` 等源码文件齐全）、`scripts/`、`tests/`；没有 `.git` 时加 `--allow-nogit`，并留意它打印的未执行守卫族清单）。
- **CLI 安装渠道**只承诺第六节的运行面冒烟三件：照 `examples` 生成一页、`xwl.py check`、`--help`；副本可能不含 `metadata.json` 等源码树文件，不承诺能跑完整 `selftest`。

## 六、装完先做这三步

1. 照 [`../examples/README.md`](../examples/README.md) 生成一个示例页面 —— 验证 `new` 路径可用；
2. `python <skill根>/scripts/xwl.py check <刚生成的页面>` —— 验证运行面能跑通（纯标准库，无第三方依赖）；
3. `--help` 过一遍子命令 —— 确认装的是你预期的那份（子命令数量与文档对得上）。

> 自检脚本不在安装副本里：装完**不要**找 `selftest.py` / `--list-blocks` —— 那是源码树的东西（见 §五）。
