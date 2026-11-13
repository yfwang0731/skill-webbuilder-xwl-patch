#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py —— xwl.py 的自检（不依赖任何外部 xwl 文件）

内置样本覆盖：
  · `check` 的格式判定（1 个合法样本 + 5 种典型破坏）
  · `edit` 的锚点拒绝与正例（含 CRLF / BOM 是否保持）
  · `expand` 的排版形态与语义等价（含 `--safe` 模式）
  · `patch` 的结构级编辑（新节点事件 JS、自动续行）
  · `new` 的从零生成（设计器真实键序 / 拒绝覆盖 / `--from-json` 补齐缺键）
  · `folders` 的 index 一致性检查与 `--register`（幂等 / 保键序 / 保单行形态 /
    **给目录 + `--register` 必须显式报错**——静默忽略会让人以为登记成功了）
  · `paths` 的「原路径」必须带 configs 层（照抄即可改对位置）
  · `schema --skeleton` 只含该控件允许的键，events 键按该控件实际事件决定
  · `node_check_many` 与逐段 `node_check` **必须逐项等价**（批量优化不许改变结论；
    守的是 CommonJS 与 Script/ESM 的编译语义差异 —— 顶层 `return` / 顶层 `await`）
  · SKILL.md 必须声明**平台边界、调用入口与规模约束**（这三样容易被精简掉，钉住）
  · **非 UTF-8 控制台（cp1252）下输出中文不能崩** —— Windows 上是这个编码，
    本地开发环境却是 UTF-8，所以只有 CI 的 windows job 能发现（第一次上 CI 就这么挂的）
  · **跨盘符不能崩**：`os.path.relpath` 不带 `start` 时在 Windows 跨盘符会抛 ValueError
    （CI 仓库在 D:、TEMP 在 C:），用桩把 relpath 变成必抛来验证兜底（第二次 CI 挂在它上面）
  · 文档一致性守卫（跨文件）：emoji 未入标题 / **任意两文档间**无逐字重复的表格行 /
    「§N.M」「见 N.M」「第 N 章」「第 N 步」引用可解析（**含跨文件**：`见 SKILL.md 2.1`、
    `controls.md §4.2`、`§五`）/ 本地链接都存在 / **外移点两侧都在**（主文档有指针 + references 有承载内容）/
    **格式五项**（表格列数 / 标题跳级 / 代码块闭合 / 行尾空白 / 末尾换行）/
    **自称数字与实际一致**（FAQ / 清单 / 反模式 / prompt 条数、清单拆分、工具表覆盖全部子命令）/
     **索引一致**（导航表目标存在、references 无孤儿无悬空、README 目录树 ↔ 磁盘）/
     文档与工具里无业务路径与业务字段名（skill 是通用资产）
  · `dump` 冒烟（它是最后一个补上冒烟覆盖的子命令）
  · `@itemId` 寻址（唯一可定位 / 重名拒绝并给候选清单 / `#N` 点名与越界）
  · 注册键重名分级（按 normalName||itemId 分组：被引用 error / 未被引用 benign / 各有唯一 normalName 不成组）
  · `params` 的两条通路识别与注释剔除
  · **写盘失败必须给可读 `[FAIL]` + 退出码 2，不得冒 Python traceback** ——
    目标只读 / 父目录不存在 / 路径过长都属「前置条件不满足」。
    （`write_text()` 不兜 `OSError` 的话，5 个子命令 9 个场景会抛 traceback，
    而 64 项断言一条都没覆盖写失败 —— 这条就是为此加的）
  · **`edit` 的锚点必须按目标文件的换行归一**（LF 与 CRLF 都要能跨行匹配）——
    `normalize_eol()` 写死 CRLF 时：LF 文件上跨行锚点**永远匹配不到**
    （报「锚点出现次数: 0」，看着像用户写错了锚点），单行锚点 + 多行 new 还会把
    LF 文件写成 CRLF/LF **混用**。另：**把多行拍平时必须有 `[warn]`** ——
    这类损坏 `check` 查不出（压平后仍是合法 JSON），只有 `edit` 这一处能提示。
    （样本工程以 CRLF 与无换行单行源为主，纯 LF 稀少；两条路径仍都要覆盖，
    因为 `expand` 按 `--eol auto` 会把无换行的单行源产出成 LF）
  · **`check` 的 ③ 必须在 CRLF / LF / CR 三种换行下都生效** —— 用
    `text.split("\\r\\n")` 切行时，**纯 LF 文件切不出行**（整份成一个元素），于是 ③ 静默退化成
    "只看最后一行"；`new` 的默认产出就是 LF，`expand --eol auto` 也会产出 LF。
    同根因还让纯 CR 文件同时得到「存在 N 处裸 CR」的 FAIL 与「该文件是单行形态（无任何换行）」的
    note（自相矛盾）。另：`patch` 对**换行混用**的源会静默统一、`--indent≠1` 会静默产出
    与设计器不一致的排版、对**无换行的单行源**会回退 LF 并整份展开 —— 这三条都必须有 `[warn]`
    / 明确说明（`--indent`／`--eol` 是能主动击穿「diff 只含本次改动」的入口）。
  · **值里的孤立代理项不得让工具崩** —— 打印字节数时
    `out.encode("utf-8")` 会抛 UnicodeEncodeError（裸 traceback + rc=1）。
    `_quote` 现在按 org.json 的写法转义成 `\\uXXXX`（语义仍等价，回读一致）；
    `_write_file` 与字节数展示一并兜住（只兜 `OSError` 不够：`UnicodeError` 不是它的子类）。
  · **`diffguard`：相对 git 基线检测「多行被压平」** —— 补的是 §2.3 承认的洞
    （压平后文件**仍合法**，`check` 与 `node --check` 都放行，只靠人工读 `git diff` 很容易漏）。
    主判据是**定义级**的（工作区某行 == 基线连续多行去掉续行符后的拼接），且只认**新发生的合并**
    （续行组每行都涉及基线变更行 ＋ 命中位置是工作区新行）；最长行粗筛与相似度档补充其他形态。
    正反两侧都要钉：压平必须报（含净计数被别处新增续行抵消的补偿式压平）、
    合法删减 / 单行变长 / 内容移动 / 极短行拼接连巧必须不报。
    另钉住降级路径：新文件、非 git 目录 → `[note]` 跳过 + rc=0；`--strict` 下跳过即 rc=2；
    `--rev` 写错是用法错、恒 rc=2（且不得被说成"新增文件"）。
  · **SKILL.md 的 frontmatter 有 1024 上限** —— description 是路由真正读的字段，
    每补一个触发词都在吃这个额度（实测：写全触发词时到过 **1029**；瘦身后 **839**，余量靠守卫守），
    所以把 description 与整个 frontmatter 块都钉住。

改完 xwl.py 先跑它；输出末尾应为 `selftest ALL OK`：

    python scripts/selftest.py              # 全跑（默认；普通档 rc 只看断言失败）
    python scripts/selftest.py --jobs 4     # 并行跑（默认 min(6, CPU 数)；--jobs 1 = 串行）
    python scripts/selftest.py --fast       # 本地快回路：跳最贵的两块（diffguard / eol_and_guards）
    python scripts/selftest.py --require-all --profile package
                                        # 必需范围门禁：package 与 development 同口径
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
# 运行面（skill）根：分发目录重排后，SKILL.md/metadata/CHANGELOG/references/examples/scripts/xwl.py
# 都在 `<repo>/webbuilder-xwl-patch/`；`HERE` 仍是开发树 `scripts/`（自扫描与 tests 基线仍用它）。
# 可用 XWL_SKILL_ROOT 覆盖（如隔离安装/测试用）。
SKILL_ROOT = os.environ.get(
    "XWL_SKILL_ROOT",
    os.path.join(os.path.dirname(HERE), "webbuilder-xwl-patch"),
)

_BASELINE_PATH = os.path.join(os.path.dirname(HERE), "tests", "baseline.json")


def _baseline_read():
    """读独立基线，返回 `(data_or_None, err)`；`err` ∈ `None` / `"missing"` / `"badjson"` / `"notdict"`。

    基线守卫（块清单/文档守卫多重集）**必须用本函数** —— 基线缺失 / 坏 JSON / 非对象时**显式失败**，
    ⛔ 不回退当前源码自举当通过。
    """
    if not os.path.isfile(_BASELINE_PATH):
        return None, "missing"
    try:
        with io.open(_BASELINE_PATH, encoding="utf-8") as _f:
            _d = json.load(_f)
    except Exception:
        return None, "badjson"
    if not isinstance(_d, dict):
        return None, "notdict"
    return _d, None


_CAP_FN_NAMES = set()


def _cap(fn):
    _CAP_FN_NAMES.add(fn.__name__)
    return fn


def _cap_fns():
    return tuple(sorted(_CAP_FN_NAMES))
_spec = importlib.util.spec_from_file_location("xwl", os.path.join(SKILL_ROOT, "scripts", "xwl.py"))
xwl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xwl)  # type: ignore[union-attr]

CRLF = "\r\n"

# 合法样本：events.click 是「反斜杠 + 真实 CRLF」的多行字符串（JS 用单引号）
VALID = (
    "{" + CRLF
    + '  "title": "测试页",' + CRLF
    + '  "children": [' + CRLF
    + "    {" + CRLF
    + '      "xtype": "button",' + CRLF
    + '      "text": "测试",' + CRLF
    + '      "events": {' + CRLF
    + '        "click": "var a = app.x.getSelection();\\' + CRLF
    + "if (!a) { return; }\\" + CRLF
    + "Wb.info('ok');\"" + CRLF
    + "      }" + CRLF
    + "    }" + CRLF
    + "  ]," + CRLF
    + '  "sql": "select 1 from dual\\' + CRLF
    + 'where 1=1"' + CRLF
    + "}" + CRLF
)

# 合法样本里 click 的 JS 应被解析成 3 行
EXPECT_JS_LINES = 3


def _run_check(files: list[str], node: str | None):
    """跑 check，返回 (exit_code, stdout)。"""
    buf = io.StringIO()
    ns = type("NS", (), {"files": files, "node": node, "no_js": node is None})()
    with contextlib.redirect_stdout(buf):
        code = xwl.cmd_check(ns)
    return code, buf.getvalue()


def _run(fn, **kw):
    """跑一个 `cmd_xxx` 并把它的 stdout 收进 buffer，返回 (rc, text)。

    放在模块级是因为它被两组以上用到（子命令冒烟 / 平台回归）——
    写成 main 里的嵌套函数时，main 拆成多个函数后就跨了作用域。
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(type("NS", (), kw)())
    return code, buf.getvalue()


# ⭐ 同形面收口：`_cap_run` 的返回值 —— 只暴露调用点用到的四属性（`subprocess.run` 的最小替身）。
_Cap = collections.namedtuple("_Cap", ("returncode", "stdout", "stderr", "timed_out"))


def _cap_run(cmd, *, cwd=None, timeout=None, env=None, input=None, binary=False):
    """跑子进程：`stdout`/`stderr` 落**临时文件**（⛔ 不是管道）＋ `timeout` ⇒ **有界返回**。

    ⭐ 为什么弃 `capture_output=True`（本仓"同形面"病灶）：管道下**后代进程**可能一直持着写端
      ⇒ 收尾等 EOF **永不返回** —— 连 `timeout` 都卡在"等管道"那一步（对照实测：`capture_output`
      被阻塞时**不返回**）。改落临时文件后只等**直子**退出，后代持不持都不阻塞 ⇒ `timeout` 到即返回。
    ⭐ 超时 ⇒ `subprocess.run` 杀掉子进程、`timed_out=True`、`returncode=None`，并把原因**显式**
      写进 `.stderr` 开头（⛔ 不静默降级 —— 本仓判据：静默一律算缺陷）。
    ⚠️ `stdout`/`stderr` **两路分开**（⛔ 不合并）：合并会污染 `stdout` 上的判据（如
      `stdout.strip() == "true"` 一类），与 `_run_cli` 的"断言只看 stdout"同源。
    返回 `_Cap(returncode, stdout, stderr, timed_out)`：`binary=False` ⇒ 二者为 `str`
      （`utf-8` ＋ `errors="replace"` ＋ 通用换行，与 `text=True` **同口径**）；`binary=True` ⇒ `bytes`。
    """
    with tempfile.TemporaryFile() as _fo, tempfile.TemporaryFile() as _fe:
        _kw = {"cwd": cwd, "env": env, "stdout": _fo, "stderr": _fe, "timeout": timeout}
        if input is not None:      # `input` ⇒ `subprocess.run` 自会置 `stdin=PIPE`（此处别显式传 stdin）
            _kw["input"] = input.encode("utf-8") if isinstance(input, str) else input
        try:
            _rc, _to = subprocess.run(cmd, **_kw).returncode, False
        except OSError as _exc:
            # Windows 高并发 CreateProcess 会偶发 WinError 1920。同一命令再试一次，
            # 仍失败才落成错误，不把这一下记成被测断言失败。
            if getattr(_exc, "winerror", None) != 1920:
                raise
            time.sleep(0.2)
            _rc, _to = subprocess.run(cmd, **_kw).returncode, False
        except subprocess.TimeoutExpired:
            _rc, _to = None, True
        _fo.seek(0)
        _out = _fo.read()
        _fe.seek(0)
        _err = _fe.read()
    if not binary:
        _out = _out.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
        _err = _err.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    if _to:
        _m = "[TIMEOUT] 子进程超过 %ss 未退出，已终止" % timeout
        if binary:      # ⛔ binary 档 `_err` 仍为 bytes：超时提示也须编码成 bytes（str＋bytes ⇒ TypeError 崩块）
            _m = _m.encode("utf-8")
            _nl = b"\n"
        else:
            _nl = "\n"
        _err = (_m + _nl + _err) if _err else _m
    return _Cap(_rc, _out, _err, _to)


def _run_cli(argv: list) -> tuple:
    """把命令经**真实 CLI**（子进程跑 `xwl.py`）执行，返回 `(rc, stdout, stderr)`。

    起因（按守卫维护纪律写清）：命令级断言若走 `_run(xwl.cmd_*)` **直调**，一旦被测行为
    **坏到会抛异常**，异常会冲出 `_run` ⇒ 那条**定向断言根本没跑到** —— 这叫 **"杀了 ≠ 守住了"**
    （实测：`events --outdir` 不再自建目录时抛 `XwlWriteError`，"events rc 应 0"那条断言从未执行）。
    ⚠️ **机制纠偏**：`_run_block` 现有三支 `except`（`SystemExit`／`KeyboardInterrupt`／`BaseException`）
    ⇒ 普通异常与 `SystemExit` **被兜住**、记成「块 X 内抛出 …」后**接着跑下一块**（**仅非 re-raise
    路径**）；"异常把整块打崩"那套形态在**这条路径上**不成立（并行档下 worker 硬崩／re-raise 仍会以
    「块 X 的子进程异常退出（rc=N）」报出：点名形式不同、**点名效果相同**）——
    所以**走子进程 CLI 的理由不是"它会崩"**，而是下面那两条（真实退出码 ＋ 进程隔离）。
    但 **"定向断言仍未跑到"照旧成立** —— 兜底只让失败可读，⛔ 不会替你跑那条断言。
    ⚠️ 兜底并非全接：`KeyboardInterrupt` 是 **re-raise**（Ctrl-C 仍能打断整个自检）；
    `MemoryError`／`SystemError` 也是 **re-raise** ⇒ **串行档**下这三**类异常**仍会整进程退出、
    **连汇总行都没有**（异常**不落地成失败条目** —— `KeyboardInterrupt` 不 append，
    `MemoryError`／`SystemError` 的 append 随异常一并丢弃 —— 现场只剩调用栈）
    ⇒ 这三**类**不在"兜底让失败可读"之列，⛔ 别读成"所有异常都被兜住"。
    改走**子进程真 CLI** 后：
      · 拿的是**真实退出码**（含 `main()` 把 `XwlWriteError` → `rc=2` 的对外契约）；
      · **异常被进程隔离** —— 工具崩了也只是 `rc≠0` ＋ 文本，**红行必落在那条定向断言上**。
    ⚠️ **stdout / stderr 分开返回**（起因）：断言写的是"工具的**输出**里应有什么"；若把 stderr 并进去，
    **错误流里恰好含期望串**就会**误判通过**（"错误流混入"）。故断言**只看 stdout**；要展示诊断时用
    `_cli_text(out, err)` 明确标注 stderr（工具的错误提示多走 stdout，如 `main()` 的 `[FAIL] …`）。
    ⇒ 凡"以 rc／输出判行为"的命令级断言一律走本函数；**不要**直调 `_run(xwl.cmd_*)`。
    （⚠️ **不改 `_run` 本身**：`_check_write_failures` 等块**就是要看异常**，改它会破坏那些断言。）
    """
    try:
        _pr = _cap_run(
            [sys.executable, "-B", os.path.join(SKILL_ROOT, "scripts", "xwl.py"), *argv], timeout=120)
        return _pr.returncode, (_pr.stdout or ""), (_pr.stderr or "")
    except Exception as exc:      # noqa: BLE001 —— 连 CLI 都起不来也要落成断言，不许炸块
        return None, "", "（CLI 起不来）%s: %s" % (type(exc).__name__, exc)


def _run_cli_env(argv: list, env_extra: dict) -> tuple:
    """同 `_run_cli`，但把 `env_extra` 叠加进子进程环境（供 `#71` 的 `PYTHONHASHSEED` 比对用）。

    ⚠️ 用 `env=` 会**整体替换**环境 ⇒ 先 `dict(os.environ)` 再 update，别让子进程丢 PATH。
    """
    _env = dict(os.environ)
    _env.update({k: str(v) for k, v in env_extra.items()})
    try:
        _pr = _cap_run(
            [sys.executable, "-B", os.path.join(SKILL_ROOT, "scripts", "xwl.py"), *argv],
            timeout=120, env=_env)
        return _pr.returncode, (_pr.stdout or ""), (_pr.stderr or "")
    except Exception as exc:      # noqa: BLE001 —— 连 CLI 都起不来也要落成断言，不许炸块
        return None, "", "（CLI 起不来）%s: %s" % (type(exc).__name__, exc)


# `#71`：`node_check` 落盘用的临时文件名形如 `xwl_ev_<随机>.js`（`tempfile` 生成，逐次不同）
#   ⇒ 「同一输入、换 seed 输出逐字节一致」这条断言必须先把这个**与本条无关的随机名**规范化掉，
#   否则永远为红（不是 #71 的病灶）。只替换该名本身，不碰其前后内容。
_TMP_EV_RE = re.compile(r"xwl_ev_[A-Za-z0-9_]+\.js")


_SUITE_DIR = os.path.join(os.path.dirname(HERE), "tests", "selftest_suites")
_SUITE_MODULES = {}


def _load_suite(block):
    """按块名加载 tests/selftest_suites/<block>.py，并缓存模块。"""
    mod = _SUITE_MODULES.get(block)
    if mod is not None:
        return mod
    path = os.path.join(_SUITE_DIR, block + ".py")
    spec = importlib.util.spec_from_file_location("xwl_selftest_suite_" + block, path)
    if spec is None or spec.loader is None:
        raise ImportError("读不到自检套件：%s" % path)
    mod = importlib.util.module_from_spec(spec)
    # 套件按块 import，读不到本模块的门禁开关。注入的是同一份对象，不是拷贝。
    mod.REQUIRE_ALL = REQUIRE_ALL
    mod.REQUIRE_PROFILE = REQUIRE_PROFILE
    # 绑定当前这份表。套件若先被别的块加载，_activate_block 会再改到本块自己的表。
    mod._SUBCHECKS = _SUBCHECKS
    mod._mark_sub = _mark_sub
    spec.loader.exec_module(mod)
    # 套件加载时会从自检模块抄走全局名。抄完后再钉一次，避免抄到另一份模块的默认值。
    mod.REQUIRE_ALL = REQUIRE_ALL
    mod.REQUIRE_PROFILE = REQUIRE_PROFILE
    mod._SUBCHECKS = _SUBCHECKS
    mod._mark_sub = _mark_sub
    for _name in getattr(mod, "_CAP_FN_NAMES", ()):
        _obj = getattr(mod, _name, None)
        if callable(_obj):
            _cap(_obj)
    _SUITE_MODULES[block] = mod
    return mod


def _suite_fn(block, name):
    """返回套件模块里的真实实现。名称缺失时给出可定位的错误。"""
    fn = getattr(_load_suite(block), name, None)
    if not callable(fn):
        raise AttributeError("自检套件 %s 没有可调用的 %s" % (block, name))
    return fn

def _cli_text(out: str, err: str) -> str:
    """把 stdout 与「非空 stderr」拼成**断言文案**用文本（stderr 明确标注，免与 stdout 混淆）。"""
    err = (err or "").strip()
    return out + (("\n[stderr] " + err) if err else "")


def _win_path(p: str, api: str):
    """调用 Windows 的 `GetShortPathNameW` / `GetLongPathNameW`；非 Windows 或失败 ⇒ `None`。

    用来复现一个**只在 Windows 上**出现的路径陷阱：`TEMP` 常是 8.3 短名形式
    （`C:\\Users\\RUNNER~1\\…`），而 git 会把仓库根归一成长名。
    见 `xwl._git_prefix` 的注释与 `_check_diffguard` 的 ⑨。
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        fn = getattr(ctypes.windll.kernel32, api)       # type: ignore[attr-defined]
        n = fn(p, buf, 32768)
    except Exception:                   # noqa: BLE001 —— 取不到就当平台不支持
        return None
    return buf.value or None






# `field_types` 的**手写**内置兜底清单（本轮仪表审计整改 ⑤：破可判定的自证循环）。
#   起因：若把期望写成 `set(xwl._FIELD_FALLBACK) | {...}` —— 期望**由被测常量自己拼出**，
#   于是 `_FIELD_FALLBACK` 被清空 / 被砍短时，那个"子集"谓词**恒为真**（定点实测：清空、砍到只剩
#   一项，谓词都返回 True）⇒ 兜底清单退化完全无感。改成**手写**期望后，兜底一旦清空/退化即判红。
#   📌 与 `xwl.py` 的 `_FIELD_FALLBACK` 是**两份独立**清单：改任何一侧都要人工同步本表（这正是目的）。


















# ---- `_check_new_guards` 的原局部助手（拆函数时上提为模块级；四个族共用）----





















































# 「块 → 未执行前置」：登记在这里的块，前置不满足时打 `[note] 本块未执行：…` 并跳过，
# 汇总行据此**单列**「未执行 N 块」（⛔ 不许把"没跑"混进"通过"）。配置错误（判红）不进这一桶。
# ⚠️ 当前为**空表**。profile 门禁不走这张表：三处块内跳过由各块自己记成「未完成」。
_BLOCK_PRECONDITIONS = {}

# 完成状态闭集。普通档只展示；`--require-all` 才据此定退出码。
COMPLETION_STATES = ("通过", "失败", "未完成", "不适用", "未选择")
REQUIRE_PROFILES = ("package", "development")

# 本次门禁上下文。只在顶层进程的 `main` 里赋值；worker 走 `--result` 时由父进程透传。
REQUIRE_ALL = False
REQUIRE_PROFILE = None
_SUBCHECKS = {}
_SELFTEST_SENTINEL = True
# 套件按这个名字加载自检。必须是正在执行的这一份，不能再执行出第二份。
if __name__ in sys.modules:
    sys.modules["xwl_selftest_runtime"] = sys.modules[__name__]

# 子检查身份。键是稳定 id，值是给人读的名字。
# 三处块内跳过都在这里：profile 两档都把它们当必需，缺了就是未完成，不得改成不适用。
_BLOCK_SUBCHECKS = {
    "basics": (("block", "basics 整块"),),
    "params_paths": (("block", "params_paths 整块"),),
    "itemids": (("block", "itemids 整块"),),
    "patch_contract": (("block", "patch_contract 整块"),),
    "subcommands": (
        ("block", "subcommands 整块"),
        ("chain.tail", "subcommands 尾段"),
    ),
    "new_guards": (
        ("block", "new_guards 整块"),
        ("js.71", "new_guards 的 #71 JS 档"),
    ),
    "docs": (
        ("block", "docs 整块"),
        ("git.chron", "docs 编年守卫"),
        ("git.dist", "docs 分发面自包含"),
    ),
    "platform": (
        ("block", "platform 整块"),
        ("js.node_check_many", "platform 的 node_check_many"),
    ),
    "write_failures": (
        ("block", "write_failures 整块"),
        ("js.write_gate", "write_failures 的写前 JS 门禁"),
        ("js.write_post", "write_failures 的写后 JS 采集"),
        ("js.write_fault", "write_failures 的写后 node 故障"),
    ),
    "edit_eol": (("block", "edit_eol 整块"),),
    "eol_and_guards": (("block", "eol_and_guards 整块"),),
    "diffguard": (
        ("block", "diffguard 整块"),
        ("repo", "diffguard 临时仓库与压平断言"),
    ),
    "bc_contract": (("block", "bc_contract 整块"),),
}


def _fresh_subchecks(block_id: str) -> dict:
    """按登记表造一份子检查状态。未登记的块不自造子检查。"""
    return {
        sid: {"id": sid, "name": name, "state": "未选择", "reason": "尚未执行"}
        for sid, name in _BLOCK_SUBCHECKS.get(block_id, ())
    }


def _mark_sub(checks: dict, sid: str, state: str, reason: str) -> None:
    """改一条已登记子检查。未登记的 id 直接留下，避免静默丢掉。

    套件里的调用只传它自己的表。嵌套函数可能拿着加载时的空表，
    所以非空标记一律写到当前块的 `_SUBCHECKS`。
    """
    if state not in COMPLETION_STATES:
        raise ValueError("未知完成状态：%s" % state)
    target = _SUBCHECKS if _SUBCHECKS else checks
    if sid not in target and sid in checks:
        target = checks
    cur = target.get(sid)
    if cur is None:
        target[sid] = {"id": sid, "name": sid, "state": state, "reason": reason}
        return
    cur["state"] = state
    cur["reason"] = reason


def _completion_of(failures, checks: dict) -> tuple:
    """由失败清单和子检查推出块完成状态。失败优先于未完成。"""
    if failures:
        return "失败", "断言失败 %d 条" % len(failures)
    pending = [c for c in checks.values() if c.get("state") in ("未完成", "未选择")]
    if pending:
        return "未完成", "；".join("%s：%s" % (c["id"], c.get("reason") or c["state"]) for c in pending)
    bad = [c for c in checks.values() if c.get("state") not in ("通过", "不适用")]
    if bad:
        return "未完成", "；".join("%s：%s" % (c["id"], c.get("state")) for c in bad)
    return "通过", "必需子检查均已通过"


def _block_record(block_id: str, failures, checks: dict) -> dict:
    state, reason = _completion_of(failures, checks)
    return {
        "block_id": block_id,
        "state": state,
        "reason": reason,
        "failures": list(failures),
        "subchecks": [checks[sid] for sid, _name in _BLOCK_SUBCHECKS.get(block_id, ()) if sid in checks]
        + [checks[sid] for sid in checks if sid not in dict(_BLOCK_SUBCHECKS.get(block_id, ()))],
    }


def _blocks_unexecuted(blocks) -> list:
    """返回 `[(块名, 理由)]`：本次**没执行**（前置不满足）的块。"""
    _out = []
    for _bn, _bf in blocks:
        _pre = _BLOCK_PRECONDITIONS.get(_bn)
        if _pre is None:
            continue
        _root, _why, _fatal = _pre()
        if _root is None and not _fatal:
            _out.append((_bn, _why))
    return _out


def _summary_line(registered, ran_names, failures, unexecuted) -> str:
    """汇总末行。分母固定为注册块数；未跑与未执行分开点名。

    全部注册块都跑完且没有失败、没有块级未执行时，保留裸词
    `「=== selftest ALL OK」`。其余情况不再用这个无范围词。
    """
    _registered = [n for n, _fn in registered]
    _denom = len(_registered)
    _ran = set(ran_names)
    _skipped = dict(unexecuted)
    _ran_count = sum(1 for n in _registered if n in _ran and n not in _skipped)
    _missing = [n for n in _registered if n not in _ran and n not in _skipped]
    _parts = ["%d/%d 块" % (_ran_count, _denom)]
    if _missing:
        _parts.append("未跑：" + "、".join(_missing))
    if _skipped:
        _parts.append("未执行：" + "、".join(
            "%s（%s）" % (n, _skipped[n]) for n in _registered if n in _skipped))
    _detail = "；".join(_parts)
    if failures:
        return "=== selftest FAIL（%s）" % _detail
    if _missing or _skipped:
        return "=== selftest OK（%s）" % _detail
    return "=== selftest ALL OK"


# ---- 跨守卫分工表（**原寄居 `_check_docs` 函数体**；#15「减负」时移出，函数体只留指向本常量的指针）----
#   位置口径：移出函数体是为了给 `_check_docs`（曾实测 1337 行）减负（阈值 `>1300 行` 触发）。
#   选"模块级常量"而非"`references/workflow-notes.md`"：后者是**分发面文档**，改动会牵动 `17p`/`17r`/`17b` 等守卫，
#   而本表是**实现内注**、不该进正文文档。
# ⚠️ **围栏四面分工**（四条与「围栏」沾边的守卫，互不替代；改任一条先核此表）：
_FENCE_FOUR_ARM_DIVISION = """\
① 格式面 —— 表列数／标题跳级／代码块闭合／行尾空白／末尾换行。
   围栏只豁免「标题跳级」（`_fence % 2 == 0`）；表列数与行尾空白没有围栏条件 ⇒ 围栏内照判
   （两树对照实测：围栏内注入列数不齐的表，两树都报「表格本行 3 格、表头 2 格」）；闭合按 ``` 计数判。
② 承诺文案面（17j-6）—— 只扫 SKILL.md 全行（含围栏内），判行内反引号里
   `[note]/[warn]/[FAIL]/[ok]` 文案的**前 16 字**是否在**真跑语料**里存在（⛔ 不比 `xwl.py` 源码串）。
③ 跨文件指针面（本臂 17j-12）—— 扫 docs 全行（含围栏内）（遍历时跳过 CHANGELOG.md），
   判跨文件节号指针是否存在，零豁免。
④ 围栏内输出文案面（17j-14）—— 仅围栏内、仅裸以 `[note]/[warn]/[FAIL]/[ok]` 开头的行，
   扫全 docs（不含 CHANGELOG.md、不含 examples/README.md）。
⟂ 互斥（两树对照实测）：② 要反引号包裹、④ 要裸行首标记 ⇒ 对「同一个标记的出现」互斥，
   而不是"同一行至多一条"：一行同时含裸 `[note]` 与反引号 `[ok]` 时两臂都报（实测 2 条）。
⚠️ 双报的归属别挂错（两树对照实测）：围栏外的 `§N.M`／`§N` 死指针被本臂与另一条引用守卫
   各报一行 = 既有（基线树也报 2 条）；围栏内同款各报一行 = 本版新增
   （基线树只报 1 条〈另一条守卫〉，本版因取消跳围栏才变 2 条）。
"""


# ---- `17g` 外移点表（**原寄居 `_check_docs` 函数体**；#15「有界下沉」时移出，函数体只留引用）----
#   位置口径：移出函数体是为了给 `_check_docs` 减负（阈值 `>1300 行` 触发）。
#   ⚠️ **拆成两张表**（原 `_splits` 一条元组同时管"主文档留了指针"与"目标文件有承载词"两件事，
#   主文档一改结构就一起碎）。拆开后两侧各管一件：
#   · `_SPLIT_CARRIERS` —— 承载词表：目标文件里这些词必须还在（与锚点无关）。**全部 26 条都在**，
#     承载词原样搬来，一个没丢。
#   · `_SPLIT_POINTERS` —— 指针表：主文档的某个章节区间里必须出现指向目标文件的指针。
#     **20 条**。不进的 6 条，其外移点所在小节随 §五／§七 整章删除（改完后主文档不再有该锚点）：
#     `### 5.1 怎么读一个`／`### 5.2 url 的三种写法`／`### 5.4 四条最容易踩的`／
#     `### 7.1 框架怎么把控件交给 JS`／`### 7.2 三类控件`／`### 7.3 遇到重名`。
#     这 6 条的承载词仍在 `_SPLIT_CARRIERS` 里守着。
#   锚点一律**去编号**改成语义关键词，由 `_region_after_anchor` 按「标题包含关键词」匹配；
#   关键词在**改前与改后两种标题里都能匹配**（逐条核过，且每条在 SKILL.md 里只命中一个标题）。
#   条数守恒：26 ＝ POINTERS 20 ＋ 只进 CARRIERS 的 6。
# ⚠️ **零损合并（32 → 26）** 的来历保留：有 6 组条目的 `(anchor, dst)` 完全相同，合并后 `keys` 取并集，
#   承载词槽位一个没丢（并集没有重复词）。⛔ 这不是"为凑数退役条目"。
_SPLIT_CARRIERS = [
    ("第五章 5.4 四条通路／五 5.4 四条易踩", "references/js-api.md",
     ["Wb.request", "Wb.open", "Wb.upload", "Wb.requestAg",
      "能力边界不是错误", "不用写", "错误对象"]),
    ("第 4 步 逐项判据／三第4步 两坑", "references/faq.md",
     ["无 BOM", "换行一致", "重名", "别写成", "不是替换成换行符"]),
    ("4.2 退出码与输出约定／四 4.2 退出码", "references/faq.md",
     ["退出码", "不影响退出码", "严格二分", "行首标记", "报告类"]),
    ("2.4 写回算法／2.4 规模占比", "references/measured-data-designer.md",
     ["toString(1)", "syncSave", "updateModule", "≈ 三成", "别把 diff 当", "本次改动"]),
    ("7.1 框架侧源码", "references/measured-data-addressing.md",
     ["ComponentManager", "unregister"]),
    ("FAQ 全量问答", "references/faq.md", ["怎么排查"]),
    ("改完自检清单", "references/checklist.md", ["- [ ]"]),
    ("反模式清单", "references/anti-patterns.md", ["为什么诱人"]),
    ("端到端实操", "references/walkthrough.md", ["第 1 步"]),
    ("2.6 diffguard 判据细节", "references/faq.md", ["粗筛", "定义级"]),
    ("2.6 diffguard 因果", "references/workflow-notes-guards.md", ["定义级", "粗筛"]),
    # ---- 结构下沉（第一步）：下面这些是正文从 SKILL.md 搬进 references/ 后的外移点 ----
    # 承载词取「必须存活」清单：把 SKILL 里的叙述搬进 references 后，
    # 目标文件里这些词必须还在。迁到 `--help`（通道 B）的那几处，其承载词同样在目标
    # references 里留一份兜底（`17g` 只加载 markdown，读不到 `scripts/*.py` 的 `--help`/注释）。
    ("2.3 静默语义损坏", "references/anti-patterns.md",
     ["静默", "绝不能", "相对基线"]),
    # （原「2.4 规模占比」已并入表首的「2.4 写回算法／2.4 规模占比」—— 同锚点同目标，keys 取并集）
    ("2.4 --eol 回退", "references/faq.md",
     ["不静默", "回退 LF", "三命令共用"]),
    # ⚠️ 本外移点原指 `references/measured-data.md` 一份 ⇒ 拆分后其承载词**跨两份**：
    #    「语义无损」「给谁看」落 §五（→ designer），「逐字节相同」落 §九（→ skeleton）
    #    ⇒ 拆成两条（各指其新文件），以保住「承载词缺一即判红」的力度。
    ("2.5 字面反斜杠 n", "references/measured-data-designer.md",
     ["语义无损", "给谁看"]),
    ("2.5 骨架侧（种子无关性）", "references/measured-data-skeleton.md",
     ["逐字节相同"]),
    ("三第0步 folder", "references/faq.md",
     ["不登记就看不到", "只认文件路径", "不替你创建"]),
    ("三第3步 三点#3", "references/measured-data-designer.md",
     ["顺带规整", "语义等价", "diff 只含", "重定向"]),
    # （原「三第4步 两坑」已并入「第 4 步 逐项判据／三第4步 两坑」；原「四 4.2 退出码」已并入
    #   「4.2 退出码与输出约定／四 4.2 退出码」—— 均为同锚点同目标，keys 取并集）
    ("五 5.2 url 口径", "references/sql-fragments.md",
     ["不解析", "只判本 wb 根", "单 webapp", "url:"]),
    ("七 7.2 normalName", "references/measured-data-addressing.md",
     ["不是所有控件都接受", "非法配置", "会跳过并回报"]),
    ("七 7.3 重名建议／七 7.3 命令示例", "references/measured-data-addressing.md",
     ["不猜顺序", "能用 normalName 就用", "必须同步改 JS", "tbarGrid",
      "--dups-only", "--name", "--suggest"]),
    ("1.2 控件骨架", "references/controls.md",
     ["必须唯一", "会与设计器产物不一致", "取值相反"]),
    ("三第3步 ops 示例／三第3步 @itemId", "references/sql-fragments.md",
     ["insert", "append", "delete", "按顺序执行", "@名字#N", "串联", "不猜顺序"]),
    ("三第3步 改前核对", "references/anti-patterns.md",
     ["configs` 一层", "照抄"]),
    # （原「五 5.4 四条易踩」已并入表首的「第五章 5.4 四条通路／五 5.4 四条易踩」）
    ("五 5.1 引用读法", "references/sql-fragments.md",
     ["补上 `.xwl`", "被引用的片段是", "从文件找引用方"]),
    # （原「七 7.3 命令示例」已并入上面的「七 7.3 重名建议／七 7.3 命令示例」）
    # ---- 核心 8 块结构下沉时新增的外移点 ----
    # 2.1：5 条硬规则搬进 faq §一（第 4 步的 ①–⑤ 清单是就地承载体）；
    # 4.3：环境依赖搬进 README（SKILL 适用范围表的环境行是就地承载体）。
    ("2.1 硬规则", "references/faq.md",
     ["无 BOM", "换行一致", "末行结构"]),
    ("4.3 环境依赖", "README.md",
     ["Python 3.9+", "NODE_BIN"]),
]

# ① 指针表：主文档的某个章节区间里，必须出现指向目标文件的指针。
#    锚点是**去编号的语义关键词**（标题包含即命中），层级仍取该小节标题的层号。
#    ⚠️ 关键词必须在改前与改后两种标题里都能匹配；`多行源的磁盘形态` 不用更短的「硬规则」，
#    因为「硬规则」同时包含在 `## 二、格式硬规则与文件形态` 里，会命中两个标题。
_SPLIT_POINTERS = [
    ("第 4 步 逐项判据／三第4步 两坑", "SKILL.md", "references/faq.md", "格式校验", 3),
    ("4.2 退出码与输出约定／四 4.2 退出码", "SKILL.md", "references/faq.md", "退出码与输出约定", 3),
    ("2.4 写回算法／2.4 规模占比", "SKILL.md", "references/measured-data-designer.md", "换行与展开", 3),
    ("FAQ 全量问答", "SKILL.md", "references/faq.md", "常见问题", 2),
    ("改完自检清单", "SKILL.md", "references/checklist.md", "自检清单", 2),
    ("反模式清单", "SKILL.md", "references/anti-patterns.md", "自检清单", 2),
    ("端到端实操", "SKILL.md", "references/walkthrough.md", "新建文件", 3),
    ("2.6 diffguard 判据细节", "SKILL.md", "references/faq.md", "压平检测", 3),
    ("2.6 diffguard 因果", "SKILL.md", "references/workflow-notes-guards.md", "压平检测", 3),
    ("2.3 静默语义损坏", "SKILL.md", "references/anti-patterns.md", "多行源为什么绝不能压成一行", 3),
    ("2.4 --eol 回退", "SKILL.md", "references/faq.md", "换行与展开", 3),
    ("2.5 字面反斜杠 n", "SKILL.md", "references/measured-data-designer.md", "值里的", 3),
    ("2.5 骨架侧（种子无关性）", "SKILL.md", "references/measured-data-skeleton.md", "页面顶层骨架", 3),
    ("三第0步 folder", "SKILL.md", "references/faq.md", "新建文件", 3),
    ("三第3步 三点#3", "SKILL.md", "references/measured-data-designer.md", "第 3 步", 3),
    ("1.2 控件骨架", "SKILL.md", "references/controls.md", "控件节点的标准形态", 3),
    ("三第3步 ops 示例／三第3步 @itemId", "SKILL.md", "references/sql-fragments.md", "两级结构", 3),
    ("三第3步 改前核对", "SKILL.md", "references/anti-patterns.md", "常见问题", 2),
    ("2.1 硬规则", "SKILL.md", "references/faq.md", "多行源的磁盘形态", 3),
    ("4.3 环境依赖", "SKILL.md", "README.md", "环境依赖与自检", 3),
]


# ---- `17j-7` `--help` 行数上限表（**原寄居 `_check_docs` 函数体**；#15「有界下沉」时移出，函数体只留引用）----
#   纯数据、被 `_check_docs` 的 `17j-7` 循环读取 ⇒ 搬到模块级不改任何上限值、不改判据。
#   ⚠️ 新增子命令必须**同步在此登记**上限（`_check_docs` 的 `_h_unreg` 会把漏登的报红）。
_help_caps = {
    # 顶层 `xwl.py --help`（实测 **27** 行：子命令简介折行占 2 行）。
    #   ⚠️ 上限 36 不动 —— `36-27=9 ≤ 10`，仍满足"上限不得比实测大 10 行以上"的设计余量。
    None: 36,
    # `check`：实测 15（新增 `--no-cfgtype` 后 +1）⇒ 15 ＋ 设计余量 5 ＝ 20。
    # `diffguard`：COLUMNS=80 实测 9 ⇒ 9 ＋ 5 ＝ 14；`params` 实测 17 ⇒ 上限 22。
    "check": 20, "edit": 22, "patch": 47, "params": 22, "paths": 12,
    "new": 29, "folders": 15, "itemids": 27, "sqlrefs": 12, "diffguard": 14,
    "schema": 26, "dump": 12, "expand": 26, "sql": 12, "events": 13,
}


# ---- `17l` 编年守卫的词表 / 正则（**原寄居 `_check_docs` 函数体**；#15「有界下沉」时移出）----
#   纯数据、被 `_check_docs` 的 `17l` 三条臂读取 ⇒ 搬到模块级不改任何判据。
#   ⚠️ `_chron` 词表用**相邻字面量拼接**写（整词直写会让 `selftest.py` 自己被这三条臂判红）——
#     移出后**保持拼接形态**（保持 `"曾" "经"` 两段字面量，不要合并成一整词）。
_chron = ["曾" "经", "原" "先", "早" "先", "此" "前", "一" "度", "当" "年", "旧" "版",
          "旧" "实现", "旧" "判据", "原" "判据", "上" "一轮", "上" "一版", "当" "时", "历史" "上",
          "以" "前"]
_date_verb = ("实测", "真机", "复现", "审查", "修正", "发布", "事故")
_date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
_ver_re = re.compile(r"\d+\.\d+\.\d+")


# ---- 层归属与编年豁免面（`17l`）的**结构判据**（「名单 → 结构判据 → 单一真源」三段改造的末段）----
#   ⚠️ 本注释头**有意不写 `# 17x` 头**：本仓「块名多重集基线」按 `# 17<字母>` 计块名，若给这段
#      加个 `# 17l` 头，会被当成**新增守卫块** ⇒ 基线对不上（块名多重集 37 → 38 只应来自下面
#      `_check_docs` 里的 `# 17u` 那一块）。
#   起因（不这么做会漏什么）：编年三臂的**豁免面**原写死 4 条。按记忆规范把 `measured-data.md` 与
#     `workflow-notes.md` 拆成多份、并把拆出的文件登记进分发面后，拆出的新文件**不在**写死的豁免集里
#     ⇒ 编年三臂（事件词 / 施工日期 / 发版号）会全扫它们、必红；而把新文件名再逐条写死一遍，只是换个
#     形式的硬编码清单（下次再拆仍漏）。故改为**按层归属机械选取**：登记即豁免、注销即失效。
#   层归属的**唯一真源** ＝ `metadata.json` 的 `layers`（`references/<文件名>` → `spec` / `evidence`）：
#     **依据层 → `evidence`**、**规格层 → `spec`**。
#     ⚠️ 代码里的符号名（`_DECL_LAYER` / `_auth_*` / `_authority_files` / `_auth_layer_misfits`）
#       **沿用旧名不改** —— 它们说的是"依据层"这个**概念**，不是字面值。
#   起因（为什么从"每份首行"搬到这里）：同一个事实原写在每份参考材料各自的第 1 行
#     「层归属：…」里 ⇒ 对外可见的层归属＝「参考材料份数 ＋ 1（打包元数据）」，任何一处漂移都没有
#     守卫能发现（`17u` 只逐份看"自己那份写没写"，看不到"两份互相矛盾"）。搬迁后只剩 1 处，
#     且「`references` 数组 ↔ `layers` 键集」可机械双向对账（见 `17x` 的同名对账臂）。
#   为什么不用「层归属」这两个中文字面值当键：字面值必须与文档措辞一致、改措辞就得改数据；
#     用 `spec` / `evidence` 两个**闭集字面量**，键值域由代码钉死（`_DECL_LAYER`），
#     非法值在读入口就折成 `None`（见 `_layers_map`）⇒ 坏数据不会伪装成"合法但选错对象"。
#   ⇒ **依据层**（`layers[rel] == "evidence"` 且 stem 属依据层家族）＝ measured-data 主＋4、
#     workflow-notes 主＋2 ＝ **8 份**；
#     **编年豁免面** ＝ {`CHANGELOG.md`, `metadata.json`} ∪ 依据层 ＝ 2 ＋ 8 ＝ **10 份**。
_DECL_LAYER = ("spec", "evidence")

# 依据层**家族前缀**（结构佐证）：只有 stem 落在这些前缀内的文件，登记 `evidence` 才**真的**享豁免。
#   起因（按守卫维护纪律，不这么做会漏什么）：豁免面改成"按层归属机械选取"后，`17u` 只校验「值合法」、
#     不校验归属**对不对** ⇒ 把某份**规格层**文件（如 `faq.md`）的 `layers` 值改成 `evidence`，它**悄悄获得
#     编年三臂全豁免**、却没有任何守卫会响（改造前豁免面是 4 条**封闭集**、改不动）= 本改造引入的**新静默面**。
#   判据意图（要的**不对称**）：**家族内加文件无需改代码**（登记驱动），但**给无关文件开豁免必须改代码**（显式、会被 review）。
#   ⛔ 不许把「依据层」退化成**逐文件名单**（那正是本轮在修的病）。
_AUTH_STEMS = ("measured-data", "workflow-notes")


def _layers_map(root):
    """读 `<root>/metadata.json` 的 `layers` ⇒ `{rel: "spec"|"evidence"}`。

    **读不出 / 不是对象 / 值非法 ⇒ `None`** —— 调用方据 `None` **判红**。
    起因（不这么做会漏什么）：若把"元数据坏了"折成空集合返回，调用方看到的是"每份文件都缺条目"，
    于是报错文案指向**文件**、而病根在**元数据**；更要紧的是空集合下 `_authority_files` 会返回 `[]`
    ⇒ 编年三臂的豁免面凭空缩成 2 份 ⇒ 一堆本该豁免的依据层文件被判红，**错误方向指向正文**。
    故"读不到"必须是 `None`（一个可判红的显式状态），⛔ 不许静默降级成 `{}`。
    """
    _p = os.path.join(root, "metadata.json")
    try:
        with open(_p, "r", encoding="utf-8") as _f:
            _md = json.load(_f)
    except (OSError, ValueError):
        return None
    if not isinstance(_md, dict):
        return None
    _lay = _md.get("layers")
    if not isinstance(_lay, dict):
        return None
    for _k, _v in _lay.items():
        if not isinstance(_k, str) or _v not in _DECL_LAYER:
            return None
    return dict(_lay)


def _decl_layer(fp):
    """`fp` 的层归属（`spec` / `evidence`）；`layers` 读不到或该文件没条目 ⇒ `None`。

    签名不变（仍只吃一个绝对路径）⇒ 调用点无需改：`root` 与 `rel` 由 `fp` 现算
    （`fp` 恒在 `<root>/references/` 下 —— 由 `_refs_md` 产出，见其实现）。
    """
    _fp = os.path.abspath(fp)
    _root = os.path.dirname(os.path.dirname(_fp))
    _rel = os.path.relpath(_fp, _root).replace(os.sep, "/")
    _lay = _layers_map(_root)
    if _lay is None:
        return None
    return _lay.get(_rel)


def _refs_md(root):
    """`references/` 下全部 `.md` 的 `(相对路径, 绝对路径)` 列表 —— **动态遍历**（不硬编码清单）。

    列不出目录 ⇒ 返回 `[]`（调用方据空表**判红**，不在空集合上静默通过）。
    """
    _d = os.path.join(root, "references")
    try:
        _nms = sorted(os.listdir(_d))
    except OSError:
        return []
    return [("references/" + _n, os.path.join(_d, _n)) for _n in _nms if _n.endswith(".md")]


def _auth_stem_ok(rel):
    """`rel` 的 stem 是否落在依据层家族前缀内（`_AUTH_STEMS`）—— 依据层声明的**结构佐证**。"""
    _stem = os.path.basename(rel)
    if _stem.endswith(".md"):
        _stem = _stem[:-3]
    return any(_stem == _s or _stem.startswith(_s + "-") for _s in _AUTH_STEMS)


def _authority_files(root):
    """**依据层**文件（`layers[rel] == "evidence"` **且** stem 属依据层家族的全部 `.md`，按路径排序）。

    `layers` 读不到 ⇒ `_decl_layer` 一律 `None` ⇒ 返回 `[]`（该情形由 `17u` 显式判红，
    ⛔ 不在这里静默通过）。
    """
    return [_rel for _rel, _fp in _refs_md(root)
            if _decl_layer(_fp) == "evidence" and _auth_stem_ok(_rel)]


def _auth_layer_misfits(root):
    """登记 `evidence` 但 stem **不**属任何依据层家族的文件（**自授豁免**候选）—— 按路径排序，供 `17u` 判红。

    起因（按守卫维护纪律，不这么做会漏什么）：`17u` 只校验层归属**值合法**、不校验归属**对不对**
    ⇒ 把某份**规格层**文件（如 `faq.md`）的 `layers` 值改成 `evidence`，它**悄悄获得编年三臂全豁免**、
    无守卫会响（改造前豁免面是 4 条**封闭集**、改不动）= 本「名单 → 结构判据」改造引入的**新静默面**。
    结构佐证：依据层家族由代码里的 `_AUTH_STEMS` **显式**声明 ⇒ 家族内加文件无需改代码（登记驱动），
    但给无关文件开豁免必须改代码（显式、会被 review）= 要的**不对称**。
    """
    return [_rel for _rel, _fp in _refs_md(root)
            if _decl_layer(_fp) == "evidence" and not _auth_stem_ok(_rel)]


def _chron_exempt(root):
    """`17l` 编年三臂的豁免面（**结构判据**）：{`CHANGELOG.md`, `metadata.json`} ∪ 依据层文件。

    起因（不这么做会漏什么）：原为写死 4 条 —— 拆分后新增的文件不在其中，会被编年三臂全扫、必红；
    改成按层归属机械选取后，**登记即豁免、注销即失效**（可注入验证）。
    """
    _ex = set()
    _ex.add("CHANGELOG.md")
    _ex.add("CHANGELOG-archive.md")
    _ex.add("metadata.json")
    _ex.update(_authority_files(root))
    return _ex


# ---- 文档守卫扫描面清单（**原寄居 `_check_docs` 函数体**；#15「有界下沉」时移出，函数体只留引用）----
#   **磁盘推导**（本轮改造）：根三份**写死**（`_ROOTS_MD`：结构性、固定）＋ `references/` 下**实际 `*.md`**
#     （`_refs_md(root)` 用 `os.listdir` 遍历 + `sorted` 定序）—— 函数体只读模块级 `doc_names`。
#   起因（按守卫维护纪律，不这么做会漏什么）：原为**17 条逐条写死**的字面量清单，它驱动 `17b`/`17c`/`17d`/`17h`/`17i`
#     一整族守卫 ⇒ 下次再加 / 再拆 `references/` 文件时，新文件对**整族守卫静默隐形**（看着绿、其实没在管），
#     而逐条补写只是换个形式的硬编码（下次再拆仍漏）= 本仓"静默失效"缺陷类。
#     改为按**磁盘实际文件集**推导后：**加文件即被扫、删文件即退出扫描面**，无需改代码。
#   ⛔ 不许退化成"写死的名单"（那正是本轮在修的病）。
_ROOTS_MD = ("SKILL.md", "README.md", "CHANGELOG.md")   # 结构性根文档：固定，写死无妨


def _doc_names(root):
    """文档守卫扫描面清单：根三份（固定）＋ `references/` 下实际 `*.md`（**磁盘推导**、`sorted` 定序）。"""
    return list(_ROOTS_MD) + [_rel for _rel, _fp in _refs_md(root)]


doc_names = _doc_names(SKILL_ROOT)


# ---- 本轮仪表审计整改（本版段内）所需的模块级常量与助手 ----
#   位置放在函数体外：这些常量/助手若写进 `_check_docs` 函数体，会把它推过 1300 行阈值。

# 破计数遮蔽：`_check_docs` 里 `# 17<字母>` 命名守卫块的**基线标识清单**（块名，按文件出现序）。
#   起因（有意保留的"丢守卫即红"）：合并大绿行把 80+ 个判据落点压成 1 行 ⇒ 整块删掉一个文档守卫后，
#     `[ok]` 计数与大绿行文案**都不变**、rc 仍 0
#     （定点实测：删掉反模式入口那一整块后 `[ok]` 仍 134、末行仍 ALL OK、合并行照样宣称该守卫通过）。
#   ⇒ 把"跑了哪些块"显式化并**内置基线**。
#   判据（2026-10-19 起，**只放宽 `_extra` 一侧，保留 `_miss`**）：
#     ① **每个基线块名的份数不得低于基线**（丢块 / 同名副本被删 ⇒ 红）；
#     ② **基线外的块名**必须在 `CHANGELOG.md` 里被**独立提及**（带词边界；新增＝显式，一行字即可）。
#   📌 为什么放宽：「块名多重集 == 基线多重集」这一判据下**新开一个块名必撞基线** ⇒ 反向压制新增覆盖
#     （一条通用解析式守卫被迫并进别的块）。⭐ `_miss` 与"允许新增"**并不冲突** ⇒ 保留它，
#     "注释掉 A ＋ 新增 B（净 0 偷换）"仍会因 A 的份数下降而红（只放宽被压制的那一侧）。
#   ⚠️ 取"**块名**"（`# 17x` 里的编号，如 `17j-10`）而非整行文本 ⇒ 块头注释**措辞可改**、不必动基线。
#   📌 **有意增删守卫块时如何更新基线**：改完块后跑下面这条量一次（只量不改），把结果抄回本清单：
#      python -B -c "import re;print([re.match(r'^\s*# (17[^\s：:（(]*)',l).group(1) for l in open('scripts/selftest.py',encoding='utf-8') if re.match(r'^\s*# 17[a-z]',l)])"
#      —— **仅在"块名确因有意增删而变"时改**；改完跑 `python -B scripts/selftest.py` 复核绿。
_DOC_GUARD_BLOCK_BASE = collections.Counter()
# 基线读取失败原因（None = 正常）。非 None 时 `_doc_guard_block_mismatch()` **显式判红**，
# ⛔ 不回退到 `_doc_guard_block_ids()`（当前源码自举）—— 否则基线坏掉时删块也判绿（序5）。
_DOC_GUARD_BASE_ERR = None


def _doc_guard_block_ids():
    """扫描主入口与自检套件，返回全部 `# 17<字母>` 守卫块的**块名多重集**（`Counter`）；读不出 ⇒ `None`。"""
    try:
        _paths = [os.path.join(HERE, "selftest.py")]
        for _suite_name in sorted(os.listdir(_SUITE_DIR)):
            if _suite_name.endswith(".py"):
                _paths.append(os.path.join(_SUITE_DIR, _suite_name))
        _lines = []
        for _path in _paths:
            with open(_path, encoding="utf-8", newline="") as _f:
                _lines.extend(_f.read().splitlines())
    except OSError:
        return None
    _c: collections.Counter = collections.Counter()
    for _l in _lines:
        _m = re.match(r"^\s*# (17[^\s：:（(]*)", _l)
        if _m:
            _c[_m.group(1)] += 1
    return _c


def _doc_guard_block_base():
    global _DOC_GUARD_BASE_ERR
    _data, _err = _baseline_read()
    if _err is not None:
        _DOC_GUARD_BASE_ERR = _err
        return collections.Counter()
    _b = _data.get("doc_guard_blocks")
    if not isinstance(_b, dict) or not _b:
        _DOC_GUARD_BASE_ERR = "empty:doc_guard_blocks"
        return collections.Counter()
    if not all(isinstance(k, str) and isinstance(v, int) for k, v in _b.items()):
        _DOC_GUARD_BASE_ERR = "badshape:doc_guard_blocks"
        return collections.Counter()
    return collections.Counter(_b)


_DOC_GUARD_BLOCK_BASE = _doc_guard_block_base()


def _gate_note(_msg: str) -> None:
    """**无门禁效力**的提示统一走这里：写 stderr，不进门禁 stdout、不进 rc。

    起因（§七 / §4.7）：观察期 `note` 混在门禁 stdout 里，会让"全绿输出"读起来像
    有判定、实际不进 rc ⇒ 语义被噪声稀释。凡"只提示、不阻断、不进 rc"的提示一律经本函数
    走 stderr；门禁 stdout 只留 `[ok]`／`[FAIL]`／块结论等**有门禁效力**的输出。
    """
    print("[note] " + _msg, file=sys.stderr)


def _blk_declared(_k, _txt) -> bool:
    """块名是否在给定文本里被**独立**提及（带词边界）。

    起因：`k in 文本` 会把 `17j` 误判为已声明（`17j-10` 含该子串）⇒ 声明类判据必须按**独立词**匹配。
    """
    return re.search(r"(?<![0-9A-Za-z_-])" + re.escape(_k) + r"(?![0-9A-Za-z_-])", _txt) is not None


def _doc_guard_block_mismatch():
    """判「每个基线块名的份数不降」＋「基线外块名已在 `CHANGELOG.md` 独立提及」。

    判据与残余见模块级 `_DOC_GUARD_BLOCK_BASE` 的注释
    —— 2026-10-19 只放宽"新增块"一侧（`_extra`），**保留**"丢块必红"（`_miss`）。
    放在函数体外（写法同上）：这段若留在 `_check_docs` 函数体里会把它推近 1300 行阈值。
    """
    _ids = _doc_guard_block_ids()
    if _DOC_GUARD_BASE_ERR is not None:
        return ("文档守卫块基线**不可用**（%s）⇒ 无法比对，判红（⛔ 不回退当前源码自举当通过）。"
                "请修复/重建 `%s`（维护者用 `--write-baselines` 显式生成）。"
                % (_DOC_GUARD_BASE_ERR, _BASELINE_PATH))
    if _ids is None:
        return "文档守卫块清单跑不起来（读不出 selftest.py）—— 本项无法判定，判红"
    _miss = sorted(k for k in _DOC_GUARD_BLOCK_BASE if _ids.get(k, 0) < _DOC_GUARD_BLOCK_BASE[k])
    if _miss:
        return ("文档守卫块份数低于基线：%s —— 有守卫被整块删掉 / 被注释 / 同名副本被删"
            "（丢块必须响）；确系**有意退役**时，用 `--write-baselines` 显式更新基线，"
                "并在 `CHANGELOG.md` 写明退役项与被撤下的判据。" % _miss)
    _base_total = sum(_DOC_GUARD_BLOCK_BASE.values())
    _total = sum(_ids.values())
    if _total < _base_total:
        return ("文档守卫块总数 %d < 基线 %d —— 有守卫被删（丢块必须响）。"
                % (_total, _base_total))
    _new = sorted(k for k in _ids if k not in _DOC_GUARD_BLOCK_BASE)
    if _new:
        try:
            with open(os.path.join(SKILL_ROOT, "CHANGELOG.md"),
                      encoding="utf-8", newline="") as _cf:
                _cl_txt = _cf.read()
        except OSError as _exc:
            return ("新增了基线外的守卫块 %s，但读不出 `CHANGELOG.md`（%s）"
                    "—— 无法判定是否已声明，判红" % (_new, _exc))
        _undeclared = [k for k in _new if not _blk_declared(k, _cl_txt)]
        if _undeclared:
            return ("新增了**未在 `CHANGELOG.md` 声明**的守卫块：%s —— 新增＝显式"
                    "（在 CHANGELOG 里写一行含**该块名**的话即可；按**独立词**匹配，"
                    "`17j` 不会被 `17j-10` 顶替）。" % _undeclared)
    return None


# 非 git 静默变绿的收窄：默认**判红**；确无 `.git`（zip 分发解包）时须**显式** `--allow-nogit` 才降级。
#   起因（有意收窄一处"非 git 只标注"的口径）：原处置"取不到 `git ls-files` ⇒ 只打 `[note]`、不判红"
#   在 zip 分发场景**可辩护**，但副作用是 —— **一个本就没跑的守卫族，全绿输出仍读得出"一切正常"**
#   （标注淹没在长输出里）⇒ **静默绿是病根**。故默认判红，加了 `--allow-nogit` 才降级为
#   "标注继续、rc 按其他项定"（此时**仍保留**非 git 两族未执行的那句汇总行标注）。
ALLOW_NOGIT = False


def _nogit_gate(arm: str, doc_fail: list, nogit_arms: list) -> None:
    """`git ls-files` 门控守卫"取不到 git"时的统一处置（口径见上方 `ALLOW_NOGIT` 起因）。"""
    if ALLOW_NOGIT:
        nogit_arms.append(arm)
        print("[note] %s：取不到 `git ls-files` 清单 ⇒ 本次**没扫**"
              "（`--allow-nogit` 降级：不算通过也不算失败）" % arm)
    else:
        doc_fail.append(
            "%s：取不到 `git ls-files` 清单 ⇒ 本次**没扫**（默认判红 —— 静默绿是病根）。"
            "确无 `.git`（如 zip 分发解包后）需降级时，显式加 `--allow-nogit`。" % arm)


def _docs_git_arm(arm: str, shipped, doc_fail: list, nogit_arms: list, checks: dict, sid: str) -> bool:
    """Git 守卫族的统一入口。取不到清单时返回 False，调用方不要再扫。

    普通档维持原口径：默认判红，显式 `--allow-nogit` 才降级成 note。
    `--require-all` 不接受这次降级：两档 profile 都把该臂记成未完成。
    """
    if shipped is not None:
        _mark_sub(checks, sid, "通过", "%s 已取得 git 清单" % arm)
        return True
    if REQUIRE_ALL:
        _mark_sub(checks, sid, "未完成", "%s 取不到 git 清单，本次没扫" % arm)
        print("[note] %s：取不到 `git ls-files` 清单 ⇒ 必需范围未完成" % arm)
        return False
    _nogit_gate(arm, doc_fail, nogit_arms)
    if ALLOW_NOGIT:
        _mark_sub(checks, sid, "不适用", "%s 按 --allow-nogit 降级，本次没扫" % arm)
    else:
        _mark_sub(checks, sid, "失败", "%s 取不到 git 清单，默认判红" % arm)
    return False


def _git_scan_scope(root: str):
    """`git ls-files` 门控守卫的扫描面：`ls-files` ∪ 磁盘新增（`--others --exclude-standard`）。

    返回 `(scope, why)`：取不到 git ⇒ `(None, 原因)`。

    起因（未跟踪文件对内容守卫隐形，定点实测）：只扫 `git ls-files` 时，**新增但未 `git add`** 的
    文件对「编年三臂 / 旧措辞 / 分发面自包含」**完全隐形** —— 往 `references/` 放一份未 `git add`
    的 md、内容含内容守卫该拦的字样，两族一条都不命中；`git add` 之后立刻新增 3 条 `[FAIL]`。
    ⇒ 把扫描面扩成「已跟踪 ∪ 未跟踪（排除 `.gitignore` 忽略项）」：**未 `git add` 的新文件也要被看到**。
    """
    scope: list = []
    _seen: set = set()
    for _c in (["ls-files"], ["ls-files", "--others", "--exclude-standard"]):
        try:
            _pr = _cap_run(["git", "-C", root, *_c], timeout=120, env=dict(os.environ))
        except (OSError, ValueError) as _exc:
            return None, "%s: %s" % (type(_exc).__name__, _exc)
        if _pr.timed_out:
            return None, "`git %s` 超时未返回" % " ".join(_c)
        if _pr.returncode != 0:
            return None, "`git %s` 返回 %s" % (" ".join(_c), _pr.returncode)
        for _x in _pr.stdout.splitlines():
            _x = _x.strip()
            if _x and _x not in _seen:
                _seen.add(_x)
                scope.append(_x)
    return scope, None


def _real_out_corpus(tmp: str) -> str:
    """**真跑**一批 `cmd_*`（含加载失败分支），把工具**实际打印过**的输出行收成语料。

    供 `17j-6` / `17j-14` 做 oracle：这两条守卫的 oracle **取错了源** —— 把 `xwl.py` 的
    **源码串（含注释）**当期望：
    只要源码里**出现过**这段文字（**哪怕是注释、或一个永不执行的字符串常量**）就算"文案承诺成立"。
    ⇒ 那是**可判定的自证循环**：工具把文案改坏、文档同步改，判据恒真；纯注释也能满足它。
    改法：期望值必须是工具**真的打印出来**的文本 —— `17j-6` 比前 16 字、`17j-14` 比整串 —— 于是注释与死字符串再也满足不了。

    ⚠️ 语料面**有意做窄**（只覆盖被这两条守卫引到的真实文案）；若将来文档开始承诺**新的**输出文案，
    需在下面**补一次真实调用**把该文案跑出来，否则守卫会报红 —— 这正是要的：承诺必须能被真跑复现。
    返回：逐行剔除空白后、以换行拼接的真实输出语料（调用方做子串匹配）。
    """
    _buf: list = []

    def _cap(fn, **kw):
        try:
            _buf.append(_run(fn, **kw)[1])
        except Exception:   # noqa: BLE001 —— 语料构造失败不该让守卫崩（缺语料 ⇒ 调用方判红）
            pass

    def _capchk(paths):
        try:
            _buf.append(_run_check(paths, None)[1])
        except Exception:   # noqa: BLE001
            pass

    def _w(nm, text):
        p = os.path.join(tmp, nm)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return p

    # ⑧ 加载链完整性：无异常 / 有告警 / 因解析失败跳过（三态都来自 `check`）
    _capchk([_w("corpus_ok.xwl", xwl.dumps_designer(
        {"title": "c", "roles": {}, "children": [
            {"configs": {"itemId": "v"}, "type": "viewport",
             "expanded": False, "children": []}]}, 1, CRLF))])
    _capchk([_w("corpus_chain.xwl", xwl.dumps_designer(
        {"title": "c", "children": {}, "roles": {}}, 1, CRLF))])
    _capchk([_w("corpus_badjson.xwl", "{ not json")])
    # 非 UTF-8 文本 ⇒ 加载失败分支的 `[FAIL] 不是 UTF-8 文本（…）`
    _nu = os.path.join(tmp, "corpus_notutf8.xwl")
    with open(_nu, "wb") as f:
        f.write(b"\xff\xfe\x00bad")
    _capchk([_nu])
    # `[ok] SQL 需要的参数在页面侧都能找到来源` ⇒ `params` 在「有需求且无 miss」时的输出：
    #   造一个 SQL 载体（dataprovider 的 sql 含 `{?kw?}`）+ 一个引用它的页面（用 `out: app.tbar`
    #   把容器内取值控件 `kw` 送出）⇒ 页面送出与 SQL 需要相等、无 miss。
    _w("corpus_sqlcarrier.xwl", xwl.dumps_designer(
        {"title": "carrier", "roles": {"default": 1}, "children": [
            {"configs": {"itemId": "module",
                         "serverScript": "var sql = '';\nrequest.setAttribute('sql', sql);"},
             "type": "module", "expanded": True, "children": [
                 {"configs": {"itemId": "dp", "sql": "select 1 from t where a={?kw?}"},
                  "type": "dataprovider", "expanded": False, "children": []}]}]}, 1, CRLF))
    _pp = _w("corpus_params.xwl", xwl.dumps_designer(
        {"title": "p", "roles": {"default": 1}, "children": [
            {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False, "children": [
                {"configs": {"itemId": "tbar"}, "type": "toolbar", "expanded": False, "children": [
                    {"configs": {"itemId": "kw"}, "type": "text", "expanded": False, "children": []}]},
                {"configs": {"itemId": "gs", "url": "m?xwl=corpus_sqlcarrier"},
                 "type": "store", "expanded": False, "children": []},
                {"configs": {"itemId": "btn"}, "type": "button", "expanded": False, "children": [],
                 "events": {"click": "app.gs.load({ out: app.tbar });"}}]}]}, 1, CRLF))
    _cap(xwl.cmd_params, file=_pp, module_root=tmp, controls=None, list_fields=False)
    # `[warn] 本次写入含 N 处 configs 非字符串值（<itemId>.<key>, …）：check 的 ⑩ 会判 FAIL，请改成字符串`
    #   ⇒ `patch`（及 edit / expand / new）**写盘后自检**里那条预告。造一个含**非字符串** `configs` 值的
    #   夹具（`width: 40` 是 int）＋ 一条无害 op（改 `title`），真跑一次 `patch`。
    #   ⚠️ `no_js=True` ⇒ 免依赖 node（本语料只用它的 stdout 做 oracle，不判 JS）。
    #   ⚠️ 必须**真打出**那条 warn：`configs` 全为字符串时本工具有意**不打**（正常文件输出不变的承诺）
    #      ⇒ 夹具里那个 int 是这条语料成立的前提，别"顺手改成字符串"。
    _pw = _w("corpus_cfgwarn.xwl", xwl.dumps_designer(
        {"title": "c", "roles": {}, "children": [
            {"configs": {"itemId": "t1", "html": "x", "width": 40},
             "type": "text", "expanded": False, "children": []}]}, 1, CRLF))
    _pops = os.path.join(tmp, "corpus_cfgwarn_ops.json")
    with open(_pops, "w", encoding="utf-8") as f:
        json.dump([{"op": "set", "path": ["title"], "value": "c2"}], f)
    _cap(xwl.cmd_patch, file=_pw, ops=_pops, eol="auto", indent=1, dry_run=False,
         backup=False, allow_new_key=False, node=None, no_js=True)
    # `--allow-new-key` 放行新建键的那条 `[warn]`：两个新建键、真写盘。
    # 文档围栏里的例子就是这一次的输出（`@panel1.configs.newKeyA` / `newKeyB`），
    # 不补这一次，那行在语料里找不到。
    _ank = _w("corpus_allownew.xwl", xwl.dumps_designer(
        {"title": "c", "roles": {}, "children": [
            {"configs": {"itemId": "panel1", "html": "x"},
             "type": "text", "expanded": False, "children": []}]},
        1, CRLF))
    _ank_ops = os.path.join(tmp, "corpus_allownew_ops.json")
    with open(_ank_ops, "w", encoding="utf-8") as f:
        json.dump([
            {"op": "set", "path": ["@panel1", "configs", "newKeyA"], "value": "v1"},
            {"op": "set", "path": ["@panel1", "configs", "newKeyB"], "value": "v2"},
        ], f)
    _cap(xwl.cmd_patch, file=_ank, ops=_ank_ops, eol="auto", indent=1, dry_run=False,
         backup=False, allow_new_key=True, node=None, no_js=True)
    # itemids 全量重名报告：两个按钮共用注册键 `btn`，其中一个被事件 JS 引用
    # ⇒ 打出 `[error] 重名 + 已被 JS 引用` 与「全量重名报告」这一族。不补这一次，文档里对这些句的承诺在语料里找不到。
    _idup = _w("corpus_itemids.xwl", xwl.dumps_designer(
        {"title": "dups", "roles": {}, "children": [
            {"configs": {"itemId": "btn", "text": "a"},
             "type": "button", "expanded": False, "children": [],
             "events": {"click": "app.btn.setText('x');"}},
            {"configs": {"itemId": "btn", "text": "b"},
             "type": "button", "expanded": False, "children": []}]},
        1, CRLF))
    _cap(xwl.cmd_itemids, file=_idup, name=None, dups_only=False, suggest=False,
         fix="auto", controls=None, json=False)
    # 「全量重名报告」那句不在 itemids 的报告里，它在重名寻址失败时由
    # `format_itemid_candidates` 抛出。用一次会撞上重名 `@btn` 的 patch 把它打出来。
    _iops = os.path.join(tmp, "corpus_itemids_ops.json")
    with open(_iops, "w", encoding="utf-8") as f:
        json.dump([{"op": "set", "path": ["@btn", "configs", "text"], "value": "z"}], f)
    _cap(xwl.cmd_patch, file=_idup, ops=_iops, eol="auto", indent=1, dry_run=True,
         backup=False, allow_new_key=False, node=None, no_js=True)
    # diffguard 重跑提示：不在 git 仓的文件会走「跳过」支，文案要求用户改完再跑一次。
    # ⚠️ 用独立临时目录，不把 skill 仓自己的 .git 当成本条的基线。
    _dg = tempfile.mkdtemp(prefix="xwl_corpus_dg_")
    try:
        _dgf = os.path.join(_dg, "plain.xwl")
        with open(_dgf, "w", encoding="utf-8", newline="") as _fh:
            _fh.write("{not json")
        _cap(xwl.cmd_diffguard, targets=[_dgf], rev="HEAD", strict=False)
    finally:
        shutil.rmtree(_dg, ignore_errors=True)
    return "\n".join(re.sub(r"\s+", "", _ln) for _t in _buf for _ln in _t.splitlines())


# ---- `_check_docs` 有界下沉（本轮）：自包含的纯数据 / 词表 / 正则表外移为模块级常量 ----
#   位置口径：与既有 `_splits` / `_help_caps` / `_chron` / `doc_names` / `_DOC_GUARD_BLOCK_BASE`
#     同法 —— 移出函数体是为了给 `_check_docs` 减负（阈值 `>1300 行` 触发）。
#   下沉＝**只搬位置**：判据、注释、扫描面**逐字未改**，函数体只留引用（指针）；被搬物**变量名不变**。
#   只搬**自包含**项；引用了 `_check_docs` 局部量的（`_has_sec` 依赖 `docs`、`_real` 依赖 `_txt`）**不搬**。

_fn = re.compile(r"([\w-]+\.md)")


_cn = "一二三四五六七八九十"


mref = re.compile(r"m\?xwl=(?!<|…)([A-Za-z0-9_./-]+)")
paths = re.compile(r"[A-Za-z0-9_<>.…/-]+\.xwl")
# 路径**首段**白名单：通用目录 / 占位段。真实业务路径的首段（工程代号、模块名）不在此列。
# ⚠️ **`wb` 不在此列** —— 合法写法 `wb/modules/<模块>/xxxSql/queryXxx.xwl` 靠行内占位符豁免，
#    把 `wb` 放进来会让 `wb/modules/<真实模块>/…xwl` 这条业务路径一并逃过（实测过）。
ok_head = re.compile(r"^(?:…|<[^/]*>|xxx|dev|examples|common)$", re.I)
# 单段 `.xwl`：只有这些通用示例名放行。
generic = re.compile(
    r"^(?:page|file|out|sql|big|x|t|p|g|smoke|one|two|valid|edit|noname|fixed|"
    r"demo-page|demo-querySql|queryXxx|myPage|queryBizList|queryOrder|orderQuery)"
    r"[A-Za-z0-9_.-]*\.xwl$")
# 本机路径（盘符 + 目录段）同样算环境信息 —— 它也能定位到具体环境。
rx_env = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/](?![.\\/])([A-Za-z0-9_.-]{2,})")
skip_env = re.compile(r"RUNNER|[<…]")     # CI 短名示例 / 占位写法
marks = re.compile(r"[<…]|xxx|Xxx")


link = re.compile(r"\]\((?!https?:|#)([^)]+\.(?:md|json|yml|py))\)")


_cn2 = "一二三四五六七八九十"


_pt_file = re.compile(r"([A-Za-z0-9][A-Za-z0-9-]*\.md)")
_pt_num = re.compile(r"§\s*([0-9]+(?:\.[0-9]+)?)")
_pt_cn = re.compile(r"§\s*([一二三四五六七八九十]+)")
_pt_jie = re.compile(r"第\s*([一二三四五六七八九十]+)\s*节")
_pt_tail = re.compile(r"[）)的\s]{0,2}「([^」]{2,60})」")


_fence_ph = re.compile(r"[<>]|…|%[sd]|\.\.\.")
_VOLATILE_RE = re.compile(r"0x[0-9a-fA-F]{2}|position\s*\d+|第\s*\d+\s*行|\bline\s*\d+")
"""`17j-14` 的**可变段**占位。

实测：参与判定的围栏行里，`references/faq.md` 那条 `[FAIL] 不是 UTF-8 文本…` 一旦从
「前 16 字前缀」收紧到「整句」就红，成因有两层：① 该行后半截是**示意拼接**（工具实际分两行打印）；
② 真输出里的 `0xff` / `position 0` 这类**样本相关数字**换样本必变。
⇒ 本常量抹掉第 ② 类；第 ① 类由文档侧改正（⛔ 守卫不能替文档编）。
"""


def _vn(_s):
    """抹掉可变段。⚠️ 比对**两侧都要过**本函数，⛔ 只抹一侧（那会把"文案被改坏"也一起豁免掉）。"""
    return _VOLATILE_RE.sub("«V»", _s)


def _fence_mask(_lines):
    """返回与 `_lines` 等长的布尔序列：该行是否落在代码围栏内。

    围栏行本身（以 ``` 开头）不算围栏内。三面共用这一份，⛔ 不许各自再数一遍。
    """
    _inside = False
    _out = []
    for _line in _lines:
        if _line.strip().startswith("```"):
            _inside = not _inside
            _out.append(False)
        else:
            _out.append(_inside)
    return _out


_trig = ["加删控件", "挂改事件", "改网格列", "SQL 片段", "传参链路", "重名", "从零新建页面",
         "folder.json", "白屏", "压成一行", "压平", "事件 JS", "WebBuilder"]


_MEASURE_COUNT_NUM = r"\d(?:[\d,_，]|\s+(?=\d))*(?:\.\d+)?"
_MEASURE_COUNT_LINK = (
    r"(?:共计|合计|总计|总数(?:为|是|共|合计|总计|达到|有)?|"
    r"总量(?:为|是|共|合计|总计|达到|有)?|数量(?:为|是|共|合计|总计|达到|有)?|"
    r"数(?:为|是|共)?|页数(?:为|是|共|合计|总计|达到|有)?|共有?|累计|"
    r"量|达到|为|是|等于|is|was|has|have|约(?:为|有)?|有|总|"
    r"count(?:ed)?(?:\s*(?:is|was|equals?))?|total|contains?|equals?)"
)
_MEASURE_COUNT_APPROX = r"(?:约|大约|about)"
_MEASURE_COUNT_RELATION = r"(?:为|是|有|达到|is|was|equals?|has|have)"
_MEASURE_COUNT_OBJECT = (
    r"(?:"
    r"\.?xwl\s*(?:(?:文件|页面|页|页数|样本|对象|files?|pages?|samples?)"
    r"(?:\s*(?:文件|页面|页|页数|样本|对象|files?|pages?|samples?))*"
    r"|(?:数量|总数|总量|数|count|total))"
    r"|(?:语料|文件|页面|页|页数|样本|对象|资源)"
    r"(?:\s*(?:数量|总数|总量|数|页数))?"
    r"\s*[（(【\[]?\s*\.?xwl\s*[）)】\]]?"
    r")"
)
_MEASURE_SIZE_UNIT = r"(?:[KMGTP]i?B|(?:千|兆|吉|太|拍)字节)"
_MEASURE_SIZE_BASE_UNIT = r"(?:bytes?|b|(?<![千兆吉太拍])字节)"
_MEASURE_SIZE_BASE_CONTEXT = (
    r"(?:(?:样本|文件|数据)大小|缓存(?:大小|占用|容量)|内存容量|"
    r"归档(?:大小|容量|体积)|(?:磁盘|存储)(?:大小|容量|占用)|"
    r"大小|容量|占用|体积)"
)
_MEASURE_SIZE_VALUE = _MEASURE_COUNT_NUM
_MEASURE_SIZE_DESC = r"(?:大小|容量|体积|占用|尺寸|数值|size|capacity)"
_MEASURE_SIZE_LINK = r"(?:为|是|有|达到|is|was|equals|:|：|=|~|≈)"
_MEASURE_DURATION_BASE_UNIT = r"(?:ms|毫秒|s|秒|sec(?:ond)?s?|min(?:ute)?s?|分钟)"
_MEASURE_DURATION_HOUR_UNIT = r"(?:h|hrs?|hours?|小时|钟头)"
_MEASURE_DURATION_UNIT = (
    r"(?:" + _MEASURE_DURATION_BASE_UNIT + r"|" + _MEASURE_DURATION_HOUR_UNIT + r")"
)
_MEASURE_DURATION_CUE = (
    r"(?:耗时|用时|执行时间|运行时间|花费(?:时间)?|花了|"
    r"took|elapsed|duration|time)"
)
_MEASURE_PATTERNS = (
    ("语料文件数", re.compile(
        r"(?<![A-Za-z0-9_.])" + _MEASURE_COUNT_NUM
        + r"\s*(?:(?:万|萬|千|仟|k)\s*)?(?:个|份)?\s*\.?xwl"
        + r"(?![A-Za-z0-9_]|\.\w)", re.I)),
    ("语料文件数", re.compile(
        r"(?<![A-Za-z0-9_.])(?P<reverse_count>"
        + _MEASURE_COUNT_OBJECT
        + r"\s*[,，:：]?\s*" + _MEASURE_COUNT_LINK
        + r"\s*[,，:：]?\s*(?:" + _MEASURE_COUNT_APPROX + r"\s*)?"
        + r"(?:" + _MEASURE_COUNT_RELATION + r"\s*)?"
        + r"[:：]?\s*" + _MEASURE_COUNT_NUM
        + r"\s*(?:(?:万|萬|千|仟|k)\s*)?"
        + r"(?:个|份|页|items?|files?|pages?|samples?)?)"
        + r"(?![A-Za-z0-9_]|\.\w)", re.I)),
    ("样本大小", re.compile(
        r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?\s*" + _MEASURE_SIZE_UNIT
        + r"(?![A-Za-z])",
        re.I)),
    ("样本大小", re.compile(
        _MEASURE_SIZE_BASE_CONTEXT
        + r"\s*(?:为|是|=|:|：)?\s*(?P<base_size_forward>"
        + _MEASURE_SIZE_VALUE + r"\s*"
        + _MEASURE_SIZE_BASE_UNIT + r")(?![A-Za-z0-9_])", re.I)),
    ("样本大小", re.compile(
        r"(?<![A-Za-z0-9_.])(?P<reverse_size>" + _MEASURE_SIZE_UNIT
        + r"\s*[,，]?\s*(?:" + _MEASURE_SIZE_DESC
        + r"\s*(?:约|大约)?\s*(?:" + _MEASURE_SIZE_LINK + r")?\s*"
        + _MEASURE_SIZE_VALUE
        + r"|(?:约|大约)?\s*" + _MEASURE_SIZE_LINK + r"\s*"
        + _MEASURE_SIZE_VALUE + r"))(?![A-Za-z])", re.I)),
    ("样本大小", re.compile(
        r"(?<![A-Za-z0-9_.])(?P<base_size_reverse>"
        + _MEASURE_SIZE_BASE_UNIT + r"(?![A-Za-z0-9_])\s*[,，]?\s*"
        + _MEASURE_SIZE_DESC + r"\s*(?:约|大约)?\s*(?:"
        + _MEASURE_SIZE_LINK + r")?\s*" + _MEASURE_SIZE_VALUE
        + r")(?![A-Za-z])", re.I)),
    ("命令耗时", re.compile(
        r"(?<![A-Za-z0-9_.])(?:\d+(?:\.\d+)?\s+"
        + _MEASURE_DURATION_BASE_UNIT
        + r"|\d+\.\d+\s*" + _MEASURE_DURATION_BASE_UNIT + r")(?![A-Za-z])",
        re.I)),
    ("命令耗时", re.compile(
        _MEASURE_DURATION_CUE
        + r"\s*(?:数值|时间|时长|值)?\s*(?:约|大约)?\s*(?:"
        + _MEASURE_SIZE_LINK + r")?\s*(?P<context_token>\d+(?:\.\d+)?\s*"
        + _MEASURE_DURATION_UNIT + r")(?![A-Za-z])"
        + r"|(?<![A-Za-z0-9_.])(?P<suffix_token>\d+(?:\.\d+)?\s*"
        + _MEASURE_DURATION_UNIT + r")(?![A-Za-z])\s*(?:的)?\s*"
        + _MEASURE_DURATION_CUE,
        re.I)),
    ("命令耗时", re.compile(
        r"(?<![A-Za-z0-9_.])(?P<reverse_duration>"
        + _MEASURE_DURATION_UNIT + r"\s*(?:的)?\s*"
        + _MEASURE_DURATION_CUE + r"\s*(?:约|大约)?\s*(?:"
        + _MEASURE_SIZE_LINK + r")?\s*\d+(?:\.\d+)?)(?![A-Za-z])",
        re.I)),
)
_MEASURE_REQUIRED = (
    "webbuilder-xwl-patch/SKILL.md",
    "webbuilder-xwl-patch/README.md",
    "webbuilder-xwl-patch/metadata.json",
    "webbuilder-xwl-patch/scripts/xwl.py",
    "webbuilder-xwl-patch/test-prompts.json",
    "scripts/selftest.py",
    "tests/baseline.json",
    "tests/selftest_suites/__init__.py",
    ".github/workflows/selftest.yml",
)


def _json_update_history_lines(text):
    """返回 `metadata.json` 的 `update_history` 值覆盖行号（1-based）。"""
    _key = '"update_history"'
    _kp = text.find(_key)
    if _kp < 0:
        return set()
    _start = text.find("[", _kp + len(_key))
    if _start < 0:
        return set()
    try:
        _, _size = json.JSONDecoder().raw_decode(text[_start:])
    except ValueError:
        return set()
    _first = text.count("\n", 0, _start) + 1
    _last = text.count("\n", 0, _start + _size) + 1
    return set(range(_first, _last + 1))


def _measurement_tokens(rel, text):
    """在给定文本里找三类禁写实测数字；返回 `(行号, 类别, token, 原行)`。"""
    _rel = rel.replace("\\", "/")
    if _rel == "webbuilder-xwl-patch/CHANGELOG.md":
        return []
    if _rel == "webbuilder-xwl-patch/CHANGELOG-archive.md":
        return []
    if _rel == "tests/baseline.json":
        return []
    if (_rel.startswith("webbuilder-xwl-patch/references/measured-data")
            and _rel.endswith(".md")):
        return []
    _skip = _json_update_history_lines(text) if _rel == "webbuilder-xwl-patch/metadata.json" else set()
    _hits = []
    for _ln, _line in enumerate(text.splitlines(), 1):
        if _ln in _skip:
            continue
        _seen = set()
        for _label, _rx in _MEASURE_PATTERNS:
            for _match in _rx.finditer(_line):
                _named = [v for v in _match.groupdict().values() if v]
                _tok = _named[0] if _named else _match.group(0)
                if _label == "样本大小" and re.sub(r"\s+", "", _tok).upper() == "1MB":
                    continue
                if (_label, _tok) in _seen:
                    continue
                _seen.add((_label, _tok))
                _hits.append((_ln, _label, _tok, _line.strip()))
    return _hits


def _measurement_regression_failures():
    """17q 的持久语法回归面。

    覆盖三类数字的正反分支：语料计数与对象的大小写、量词、分隔与量级；
    样本大小的空格/紧排、十进制/二进制单位别名与常见中文字节单位；命令
    耗时的空格/紧排、秒/毫秒/分钟/小时别名，以及对象、单位、线索与数值
    的两种先后语序。另钉住四类豁免、
    metadata 历史段边界、能力边界和普通常量，防止扩展语法时误伤。
    """
    _rel = "webbuilder-xwl-patch/references/probe.rst"
    _positive = (
        ("count-quantifier", "共纳入 " + str(713) + " 份 .xw" + "l 页面",
         ("语料文件数",)),
        ("count-upper", "覆盖 24," + str(986) + " 个XW" + "L 文件",
         ("语料文件数",)),
        ("count-tight", "当前语料为" + str(713) + "份.xw" + "l页面",
         ("语料文件数",)),
        ("count-underscore", "样本 1_" + str(234) + " 份.XW" + "L",
         ("语料文件数",)),
        ("count-space-group", "样本 23 " + str(451) + " 个 xw" + "l",
         ("语料文件数",)),
        ("count-wan", "样本 1." + str(8) + "万.xw" + "l",
         ("语料文件数",)),
        ("count-object-quantity",
         "页面数量（.xw" + "l）为 " + str(7) + " " + str(409) + " 份",
         ("语料文件数",)),
        ("count-object-magnitude",
         "本批 xw" + "l 样本约有 " + str(6) + "k 份",
         ("语料文件数",)),
        ("count-object-punctuation",
         ".XW" + "L 文件数量：" + str(713) + " 个",
         ("语料文件数",)),
        ("count-object-case-space",
         "Xw" + "L 页面样本合计 24," + str(986),
         ("语料文件数",)),
        ("count-object-english",
         "XW" + "L count is 1_" + str(234) + " files",
         ("语料文件数",)),
        ("count-link-approx-relation",
         "XW" + "L 页面合计约为 " + str(843) + " 份",
         ("语料文件数",)),
        ("count-object-punctuation-combo",
         "页面数量（.xw" + "l）：合计约 " + str(7) + " " + str(409) + " 份",
         ("语料文件数",)),
        ("count-english-about",
         "XW" + "L pages count is about 1," + str(24),
         ("语料文件数",)),
        ("size-lower", "缓存 " + str(5) + " g" + "b",
         ("样本大小",)),
        ("size-tight", "缓存" + str(5) + "gi" + "b",
         ("样本大小",)),
        ("size-decimal-alias", "样本 " + str(2) + "." + str(3) + " Ti" + "B",
         ("样本大小",)),
        ("size-chinese-megabyte",
         "缓存占用 " + str(640) + " 兆字节",
         ("样本大小",)),
        ("size-chinese-gigabyte-tight",
         "样本大小" + str(5) + "吉字节",
         ("样本大小",)),
        ("size-base-forward",
         "样本大小 " + str(512) + " B",
         ("样本大小",)),
        ("size-base-forward-word",
         "缓存占用 " + str(1) + "." + str(5) + " byte",
         ("样本大小",)),
        ("size-base-reverse",
         "bytes 大小是 " + str(640),
         ("样本大小",)),
        ("size-base-compact",
         "样本大小为" + str(512) + "B",
         ("样本大小",)),
        ("duration-compact-prefix", "耗时" + str(7) + "s",
         ("命令耗时",)),
        ("duration-compact-suffix", str(7) + "s 的耗时",
         ("命令耗时",)),
        ("duration-minute", "运行时间=" + str(2) + "分钟",
         ("命令耗时",)),
        ("duration-min-alias", "time: " + str(2) + "min",
         ("命令耗时",)),
        ("duration-ms", "took " + str(850) + "ms",
         ("命令耗时",)),
        ("duration-decimal", "duration=" + str(2) + "." + str(5) + "s",
         ("命令耗时",)),
        ("duration-hour-decimal",
         "基准运行耗时 " + str(1) + "." + str(5) + " 小时",
         ("命令耗时",)),
        ("duration-hour-english",
         "benchmark took " + str(2) + " hours",
         ("命令耗时",)),
        ("duration-hour-compact",
         "单次运行耗时 " + str(3) + "h",
         ("命令耗时",)),
        ("duration-value-link",
         "耗时数值是 " + str(7) + "s",
         ("命令耗时",)),
        ("duration-value-unit-context",
         str(1) + "." + str(25) + "钟头用时",
         ("命令耗时",)),
        ("count-reverse", "XW" + "L 页面共计 " + str(843) + " 份",
         ("语料文件数",)),
        ("count-reverse-upper", "xw" + "l 文件合计 24," + str(986) + " 个",
         ("语料文件数",)),
        ("count-reverse-mixed-case", "Xw" + "L页面总数为" + str(713),
         ("语料文件数",)),
        ("count-reverse-magnitude",
         "XW" + "L 文件累计 2." + str(5) + " 万份",
         ("语料文件数",)),
        ("count-reverse-punctuation",
         ".XW" + "L 页面量：" + str(843) + "份",
         ("语料文件数",)),
        ("count-reverse-english",
         "XW" + "L pages total 1," + str(234),
         ("语料文件数",)),
        ("size-reverse", "G" + "B 大小是 " + str(3) + "." + str(5),
         ("样本大小",)),
        ("size-reverse-lower", "g" + "b 容量约为 " + str(5),
         ("样本大小",)),
        ("size-reverse-punctuation", "M" + "B大小：" + str(2) + "." + str(5),
         ("样本大小",)),
        ("size-reverse-direct", "Ti" + "B 占用 " + str(4),
         ("样本大小",)),
        ("size-reverse-prefix",
         "单位 G" + "B，大小是 " + str(3) + "." + str(5),
         ("样本大小",)),
        ("size-reverse-colon", "G" + "B：" + str(3) + "." + str(5),
         ("样本大小",)),
        ("size-reverse-english",
         "G" + "B capacity is " + str(3) + "." + str(5),
         ("样本大小",)),
        ("duration-reverse", "sec" + "onds 用时 3." + str(25),
         ("命令耗时",)),
        ("duration-reverse-ms", "m" + "s耗时" + str(8),
         ("命令耗时",)),
        ("duration-reverse-minute", "分钟用时为" + str(2),
         ("命令耗时",)),
        ("duration-reverse-min", "m" + "in took 2." + str(5),
         ("命令耗时",)),
        ("duration-reverse-elapsed", "s elapsed: " + str(3),
         ("命令耗时",)),
        ("duration-reverse-de", "秒 的 耗时 " + str(7),
         ("命令耗时",)),
    )
    _negative = (
        ("guard-label", "块 " + str(17) + "s 缺起因"),
        ("timeout-constant", "timeout=" + str(7) + "s"),
        ("python-version", "Python " + str(3) + "." + str(9) + "+"),
        ("size-boundary", str(1) + " MB 以上未验证"),
        ("file-name", "文件名为 a.xw" + "l"),
        ("ordinary-label", "guard " + str(17) + "b 不是统计"),
        ("count-reverse-not-count",
         "XW" + "L 格式适合 " + str(3) + " 个场景"),
        ("count-reverse-version",
         "XW" + "L 页面版本是 " + str(843)),
        ("count-bare-xwl-unrelated",
         "XW" + "L 有 " + str(3) + " 个命令"),
        ("count-batch-xwl-unrelated",
         "本批 xw" + "l 有 " + str(3) + " 个命令"),
        ("size-unit-only", "G" + "B 字段说明"),
        ("size-boundary-word", "G" + "B 大小为能力边界"),
        ("size-base-block-lower", "块 " + str(17) + "b 缺起因"),
        ("size-base-block-upper", "块 " + str(17) + "B 缺起因"),
        ("size-base-file-name", "file-" + str(512) + "B.log"),
        ("size-base-variable", "变量 sample" + str(512) + "B"),
        ("size-base-field-word", "bytes 字段名"),
        ("size-base-no-value", "样本大小字段名不含值"),
        ("size-base-unrelated-context",
         "单行样本保持单行）；" + str(11) + " B"),
        ("size-base-js-binding", "var b = " + str(2)),
        ("size-base-js-field", "b: " + str(2)),
        ("duration-unit-only", "sec" + "onds 字段名"),
    )
    _failures = []
    for _name, _text, _want in _positive:
        _got = tuple(hit[1] for hit in _measurement_tokens(_rel, _text))
        if _got != _want:
            _failures.append("%s：期望 %r，实际 %r" % (_name, _want, _got))
    for _name, _text in _negative:
        _got = tuple(hit[1] for hit in _measurement_tokens(_rel, _text))
        if _got:
            _failures.append("%s：合法反例误命中 %r" % (_name, _got))

    _all = " / ".join((
        str(713) + " 份 .xw" + "l",
        str(5) + " g" + "b",
        "耗时" + str(7) + "s",
        "XW" + "L 页面共计 " + str(843) + " 份",
        "XW" + "L 页面合计约为 " + str(843) + " 份",
        "页面数量（.xw" + "l）为 " + str(7) + " " + str(409) + " 份",
        "G" + "B 大小是 " + str(3) + "." + str(5),
        "样本大小 " + str(512) + " B",
        "缓存占用 " + str(640) + " 兆字节",
        "sec" + "onds 用时 3." + str(25),
        "benchmark took " + str(2) + " hours",
    ))
    for _name, _exempt_rel in (
        ("changelog", "webbuilder-xwl-patch/CHANGELOG.md"),
        ("baseline", "tests/baseline.json"),
        ("measured-data", "webbuilder-xwl-patch/references/measured-data.md"),
    ):
        if _measurement_tokens(_exempt_rel, _all):
            _failures.append("%s：豁免面误命中" % _name)
    _history = (
        '{\n  "update_history": [\n    {"summary": "'
        + _all
        + '"}\n  ]\n}\n'
    )
    if _measurement_tokens("webbuilder-xwl-patch/metadata.json", _history):
        _failures.append("metadata.update_history：豁免面误命中")
    _outside = _measurement_tokens(
        "webbuilder-xwl-patch/metadata.json", '{"summary": "' + _all + '"}'
    )
    if {hit[1] for hit in _outside} != {
            "语料文件数", "样本大小", "命令耗时"}:
        _failures.append("metadata 历史段外：三类 token 未完整命中")
    return _failures


def _measurement_scan_paths(root):
    """数字禁令扫描面：分发包全树、主自检、tests 与 CI workflow。

    候选按文件身份枚举，不按扩展名白名单；`.git` 与编译缓存目录只是目录遍历排除。
    """
    _repo = os.path.dirname(HERE)
    _roots = (
        root,
        os.path.join(_repo, "tests"),
        os.path.join(_repo, ".github", "workflows"),
    )
    _paths = []
    for _root in _roots:
        for _dp, _dns, _fns in os.walk(_root):
            _dns[:] = [_d for _d in _dns if _d not in (".git", "__pycache__")]
            for _fn in _fns:
                _p = os.path.join(_dp, _fn)
                _paths.append(_p)
    _paths.append(os.path.abspath(__file__))
    return sorted(set(_paths))


def _measurement_expected_paths(root):
    """用独立目录遍历生成 17q 应有的完整候选集合（不按扩展名筛选）。"""
    _repo = os.path.dirname(HERE)
    _roots = (
        os.path.abspath(root),
        os.path.join(_repo, "tests"),
        os.path.join(_repo, ".github", "workflows"),
    )
    _paths = []

    def _walk(directory):
        try:
            _entries = list(os.scandir(directory))
        except OSError:
            return
        for _entry in _entries:
            try:
                if _entry.is_dir(follow_symlinks=False):
                    if _entry.name not in (".git", "__pycache__"):
                        _walk(_entry.path)
                elif _entry.is_file(follow_symlinks=False):
                    _paths.append(os.path.abspath(_entry.path))
            except OSError:
                continue

    for _scan_root in _roots:
        _walk(_scan_root)
    _paths.append(os.path.abspath(__file__))
    return {os.path.normcase(os.path.abspath(path)) for path in _paths}


def _measurement_coverage(root):
    """比较独立预期集合、实际扫描集合与最小必需文件；返回问题列表。"""
    _repo = os.path.dirname(HERE)
    _expected = _measurement_expected_paths(root)
    _actual = {
        os.path.normcase(os.path.abspath(path))
        for path in _measurement_scan_paths(root)
    }
    _required = {
        os.path.normcase(os.path.abspath(os.path.join(_repo, rel)))
        for rel in _MEASURE_REQUIRED
    }
    _issues = []
    if not _actual:
        _issues.append("实际扫描集合为空")
    if not _expected:
        _issues.append("独立预期集合为空")
    _missing_required = sorted(_required - _actual)
    _missing_expected = sorted(_expected - _actual)
    _unexpected = sorted(_actual - _expected)
    if _missing_required:
        _issues.append("缺最小必需文件：%s" % "、".join(
            os.path.relpath(path, _repo).replace(os.sep, "/") for path in _missing_required))
    if _missing_expected:
        _issues.append("实际扫描漏件：%s" % "、".join(
            os.path.relpath(path, _repo).replace(os.sep, "/") for path in _missing_expected))
    if _unexpected:
        _issues.append("实际扫描越界：%s" % "、".join(
            os.path.relpath(path, _repo).replace(os.sep, "/") for path in _unexpected))
    return _issues


def _measurement_hits(root):
    """返回 `(扫描文件数, 命中列表, 扫描面问题)`；命中项绑定仓库相对路径。"""
    _repo = os.path.dirname(HERE)
    _paths = _measurement_scan_paths(root)
    _hits = []
    for _path in _paths:
        _rel = os.path.relpath(_path, _repo).replace(os.sep, "/")
        try:
            with open(_path, "r", encoding="utf-8", newline="") as _fh:
                _text = _fh.read()
        except (OSError, UnicodeDecodeError) as _exc:
            _hits.append((_rel, 0, "读取失败", type(_exc).__name__, str(_exc)))
            continue
        for _ln, _label, _tok, _line in _measurement_tokens(_rel, _text):
            _hits.append((_rel, _ln, _label, _tok, _line))
    return len(_paths), _hits, _measurement_coverage(root)


_b17r_docs = ("《验收基线》", "《落地清单》", "施工索引", "施工单")
# 条代号判据（**结构化**）：覆盖**已知形态** —— 「字母-短横-数字」与「单字母-数字」，
#   以及原「SITE ＋ 数字」形态。无短横那一半**只收单字母** ⇒ **已收窄的假阳性面（无短横的多字母缩写）**不再误抓；
#   右侧界定符只排除「点 ＋ 词字符」⇒ 带扩展名的文件名不误抓、句末 ASCII 句点仍判。
_b17r_code = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-L]\d{1,2}|[A-Z]{1,3}-\d{1,2}|[A-L]-[a-z])(?![A-Za-z0-9_]|\.\w)"
    r"|(?<![A-Za-z0-9_])SITE\d(?![A-Za-z0-9_])")
# 词形豁免（**结构化，非逐文件/逐条名单**）：**字符编码名**一类 —— 按**真实字符集族的字符集形状**
#   逐 match 判词形后放过（含带编号族、四位／五位数字族与带下划线的族名）。
_b17r_code_ok = re.compile(
    r"^(?:UTF-?8|UTF-?16|UTF-?32|UTF8|UTF16|UTF32|UCS-?[24]|ISO-8859-\d{1,2}"
    r"|GB\d{4}|GBK|GB18030|CP\d{3,5}|KOI8-[RU]|SHIFT_JIS|EUC-[A-Z]{2})$", re.I)
_b17r_sec = re.compile(r"§\d{1,3}-\d{1,2}")
_b17r_proc = re.compile(r"\bPRE\d+\b|\b(?:eng|qa|pm|arch|reg|tl)-\d{1,3}\b")








_META_REQUIRED_FIELDS = {"name", "version", "description", "input_schema",
                         "output_schema", "error_handling"}


# ---- 同批「有界下沉」续：`_check_docs` 内的**纯助手**（自包含、只依赖入参与模块导入）----
#   位置口径同前述：移出函数体是为 `_check_docs` 减负（阈值 `>1300 行` 触发）；
#   判据、注释、扫描面**逐字未改**，函数体只留引用（指针）；**函数名不变**。
#   只搬**纯**助手：引用了 `_check_docs` 局部量的（`_has_sec` 依赖 `docs`）**不搬**，留在原位。

def _region_after_anchor(_lines, _anchor, _lvl):
    """返回 `(区间行, 命中标题的层号)`；找不到返回 `(None, None)`。

    区间取命中标题行到「下一个**层号 ≤ 本标题**的标题」之间的行（不含标题行）。

    匹配是**包含**（`_anchor` 出现在标题文本里），不是前缀：锚点已改成去编号的语义关键词，
    要在改前（带编号）与改后（重编号）两种标题里都能命中。层级仍按命中标题自身的层号计。

    围栏内的标题行不算命中。同层命中超过一次也返回 `(None, None)`：命中第一个就返回
    只能挡住异层，挡不住同层多命中。
    """
    _mask = _fence_mask(_lines)
    _hits = []
    for _k, _l in enumerate(_lines):
        if _mask[_k]:
            continue
        _hm0 = re.match(r"^(#{1,6}) (.*)$", _l)
        if _hm0 and _anchor in _hm0.group(2):
            _hits.append((_k, len(_hm0.group(1))))
    if len(_hits) != 1:
        return None, None
    _k, _own = _hits[0]
    # 层级取**命中标题自身**的层号，不取调用方传入的 `_lvl`：锚点已是关键词，
    # 标题写了几个 `#` 只有命中那一行知道。`_lvl` 保留在签名里是为了不改调用处。
    _out = []
    _fen = 0
    for _j in range(_k + 1, len(_lines)):
        _cur = _lines[_j]
        if _cur.strip().startswith("```"):
            _fen += 1
        elif _fen % 2 == 0:
            _hm = re.match(r"^(#{1,6}) ", _cur)
            if _hm and len(_hm.group(1)) <= _own:
                break
        _out.append(_cur)
    return _out, _own


def _pt_heads(_ls):
    return "\n".join(_x for _x in _ls if re.match(r"^#{1,6}\s", _x))

def _pt_norm(_t):
    return re.sub(r"\s+", "", _t).replace("`", "")



def _toc_link(_t):
    _m = re.search(r"\[(.+?)\]\(#([^)]+)\)", _t)
    return _m

def _toc_key(_t):
    _s = _t.strip().replace("`", "")
    _s = re.sub(r"[*_~]", "", _s).lower()
    _s = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", _s)
    return re.sub(r"[-]", "", _s).replace(" ", "")


# 目录完整性臂的豁免清单：标题**有意不进目录**的小节。每条是 `(文件, 标题前缀)`，
#   用前缀而不是全文，避免标题后半句一改说法就静默对不上。
#   存在性由下面的自校验钉住：每条必须命中目标文件里**恰好一个** `##` 标题。
#   0 个 ⇒ 标题改了、豁免失效；≥2 个 ⇒ 前缀太泛。两种都判红。
#   ⚠️ 新增带 `## 目录` 的文件时本臂仍会把它的小节当缺失判红，
#     需人工确认"该补目录项"还是"该补豁免"，⛔ 别默认往这里加。
_TOC_HEAD_EXEMPT = {
    ("references/anti-patterns.md", "速查"),
    ("references/anti-patterns.md", "只记三条的话"),
    ("references/measured-data.md", "主题文件索引"),
    ("references/walkthrough.md", "一句话回顾"),
}

# 「**这份文件必须有 `## 目录`**」的登记表。⛔ 它与上面的豁免清单**不是**同一件事：
#   豁免清单管"某个小节有意不进目录"，本表管"整份文件的目录**标题**不许消失"。
#   起因（不这么做会漏什么）：目录族的四臂（锚点解析／顺序／完整性／新加的"条目在而标题没了"）
#     **全部**从一个 `## 目录` 标题出发；把标题**连同全部条目**一起删掉，四臂会一起静默 ——
#     实测 `--only docs` 得 `rc=0 / FAIL 0`。而"条目段还在"这条反推兜不住它（段没了就无从反推）。
#   ⇒ 只有**登记为必须有**的文件，才判得出"整块被删"。⚠️ 已知盲区：本表是**写死的清单** ——
#     新增一份带目录的文件时它**不会**自动被要求（⛔ 别据此说"目录完整性已全覆盖"），
#     反向也不会假红；文件被改名时下面的"登记了但文件不在"会报出来，不会静默失效。
_TOC_REQUIRED = frozenset({
    "references/anti-patterns.md",
    "references/controls.md",
    "references/faq.md",
    "references/js-api.md",
    "references/measured-data.md",
    "references/sql-fragments.md",
    "references/walkthrough.md",
})


# ---- #15「有界下沉」续 3：`17j-12`／`17j-13`／`17j-14` 三臂（原寄居 `_check_docs` 函数体）----
#   起因（按守卫维护纪律，不这么做会漏什么）：`_check_docs` 函数体逼近 1300 行阈值（余量只剩 5、
#     低于「余量 < 20 先下沉」的设计下限）⇒ 再加任何一条文档守卫都会越阈判红。这三臂编号连续、
#     自成一段（跨文件节号指针 ＋ 目录顺序 ＋ 围栏输出文案），且只依赖 `docs`／`doc_fail`／
#     `real_out` 三个入参 ＋ 模块级常量与助手 ⇒ 是"漂移为零"的切法（函数体内只留一行调用）。
#   ⛔ 不许在函数体内再内联回去（那条路会让余量立刻回到危险区）。
@_cap
def _doc_guard_xfile_pt(docs, doc_fail, real_out):
    """17j-12 跨文件节号指针可解析 ＋ 17j-13 目录顺序一致 ＋ 17j-14 围栏输出文案符实。"""
    # 17j-12 跨文件节号指针必须指向**真实存在**的小节（③ 引用漂移）。
    #   起因：文档里「见某 references/*.md 的 §九 / §3.3 / 紧贴文件名的「小节名」」这类指针，
    #     有**两类一直没人守** —— `第N节`（**中文数字**）与紧贴文件名的「小节名」；而 `§N.M` 由
    #     另一条引用守卫守、`§N`／`§中文数字` 由本函数另一条「节号」臂守（那两条都不跳围栏）。
    #     没人守的那两类一旦目标小节被改名 / 搬走 / 删掉，指针就成了**死指针**（指向空气）。
    #   判据：只看**文件与小节标记落在同一格 / 同一句**的指针（同句 = 按 。；！？ 切、同格 = 按表格 | 切）；
    #     小节标记 = `§N` / `§N.M` / `§中文数字` / `第N节` / **紧贴文件名**的「小节名」。
    #     ⚠️ `第N章` **不算** —— 那是 SKILL 自身章号：首页「怎么用」索引表把「第五/六/八/九章」
    #       与同一行的 references 文件名并列，不加这条会把 SKILL 自己的章号误当成指针目标（实测误报 3–4 条）。
    #   围栏内也纳入（不再跳过代码围栏块）：代码围栏块里同样会写跨文件指针（示例命令、片段引用）。
    #     ⚠️ 前提如实化（两树对照实测）：`§N.M` 由另一条引用守卫守、`§N`／`§中文数字` 由本函数「节号」臂守
    #       （两条都与围栏无关）⇒ 本臂的**净增只有两处**：`第N节`（**只认中文数字**，阿拉伯写法不触发）
    #       与紧贴文件名的「小节名」。实测（副本对照跑）围栏内指针误报面为 0 ⇒ 直接纳入、**不加任何豁免**。
    #     ⚠️ 别照搬 `[:16]` 前缀法 —— 那是 `17j-6`（SKILL.md 行内反引号承诺文案，比对真跑语料）的判法；
    #       围栏臂「围栏块输出文案符实」比的是整串。本守卫判「节号存在性」，不是同一个面。
    #   现状全绿（**含围栏内指针在内**全部解析）⇒ 纯**防回归**。
    #   ⚠️ **围栏四面分工表**（四条与「围栏」沾边的守卫，互不替代；改任一条先核那张表）
    #     已**移出函数体**（#15 减负）⇒ 见模块级常量 `_FENCE_FOUR_ARM_DIVISION`（本文件 `_check_docs` 之前）。
    _pt_base = {k.split("/")[-1]: k for k in docs}
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":
            continue
        _mask12 = _fence_mask(_ls)
        for _i, _l in enumerate(_ls, 1):
            if _mask12[_i - 1]:
                continue
            _segs = _l.split("|") if _l.strip().startswith("|") else re.split(r"[。；！？]", _l)
            for _seg in _segs:
                _fils = [(_m.start(), _m.end(), _m.group(1))
                         for _m in _pt_file.finditer(_seg) if _m.group(1) in _pt_base]
                if not _fils:
                    continue
                _dsg = []
                for _m in _pt_num.finditer(_seg):
                    _dsg.append((_m.start(), _m.end(), "num", _m.group(1)))
                for _m in _pt_cn.finditer(_seg):
                    _dsg.append((_m.start(), _m.end(), "cn", _m.group(1)))
                for _m in _pt_jie.finditer(_seg):
                    _dsg.append((_m.start(), _m.end(), "cn", _m.group(1)))
                for _ds, _de, _kind, _tok in _dsg:
                    _fx = min(_fils, key=lambda _f: min(abs(_ds - _f[1]), abs(_f[0] - _de)))
                    _tg = _pt_base[_fx[2]]
                    _hs = _pt_heads(docs[_tg])
                    if _kind == "num":
                        _hit = re.search(r"^#{1,6}\s*" + re.escape(_tok) + r"(?:[.\s、）)]|$)", _hs, re.M)
                        _sy = "§"
                    else:
                        _hit = re.search(r"^#{1,6}\s*" + re.escape(_tok) + r"(?:[、.\s]|$)", _hs, re.M)
                        _sy = "§"
                    if not _hit:
                        doc_fail.append("17j-12 %s:%d 跨文件指针「%s %s%s」在目标文件 %s 里没有对应小节"
                                        "（按标题文本匹配，不许按行号）" % (_nm, _i, _fx[2], _sy, _tok, _fx[2]))
            # 紧贴文件名的「小节名」指针：整行扫描（句读会把「…？」里的标题切断，故不按句切）
            for _fm in _pt_file.finditer(_l):
                if _fm.group(1) not in _pt_base:
                    continue
                _tm = _pt_tail.match(_l[_fm.end():])
                if _tm and _pt_norm(_tm.group(1)) not in _pt_norm("\n".join(docs[_pt_base[_fm.group(1)]])):
                    doc_fail.append("17j-12 %s:%d 跨文件指针「%s「%s」」在目标文件 %s 里找不到"
                                    % (_nm, _i, _fm.group(1), _tm.group(1)[:20], _fm.group(1)))

    # 17j-13 结构顺序（④）：目录条目顺序与实际小节顺序一致。
    #   ⚠️「标题不跳级」由 17h 按同一判据守，此处不再重复（曾作冗余双保险，会让**一处缺陷报两行**）。
    #   目录：带 `## 目录` 的文件，TOC 条目（`- [label](#anchor)`）必须**逐个**对得上正文小节
    #     （锚点按标题 slug **前缀**匹配 —— 标签可缩写），且顺序与正文出现顺序**单调一致**。
    #   现状全绿（带目录文件里每个目录项都能解析、且顺序单调）⇒ 纯**防回归**。
    #     起因：章节被搬动后，目录条目顺序若与正文不一致，读者按目录跳会到错处；此臂只作防回归（现状全绿）。
    for _nm, _ls in docs.items():
        _ti = next((_k for _k, _l in enumerate(_ls) if re.match(r"^##\s*目录\s*$", _l)), None)
        if _ti is None:
            # ⭐「该有目录却没有」两臂（**一处缺陷只报一行**）：
            #   ① 登记表里点名要有的文件 ⇒ 直接判"整份文件的目录没了"（这条兜"标题 ＋ 条目一起删"，
            #     另一种臂兜不住：段没了就无从"由条目反推"）；
            #   ② 未登记的 ⇒ 看"目录条目还在、标题没了"这个结构特征。
            #   起因（不这么做会漏什么）：下面三臂（锚点解析／顺序单调／完整性）**都从这个 `_ti` 出发**
            #     ⇒ 标题一改名就同时 `continue`，实测改名后 `rc=0`、`FAIL 0`（整族**静默失效**）。
            if _nm in _TOC_REQUIRED:
                doc_fail.append("17j-13 %s **登记为必须有目录**，却找不到 `## 目录` 标题"
                                "（标题被改名／整块删掉了）—— 本族各臂都靠它定位，缺了会整族静默失效"
                                % _nm)
                continue
            # 判据：连续 ≥3 条「`- [label](#anchor)`」是目录条目的**结构特征**（与标题怎么写无关）⇒
            #   有这种段却没有 `## 目录` 标题，就是标题被改坏了。⛔ 不逐个追近义写法
            #   （`## 目 录`／`## 目录表`／`## 索引`）：条目段在、标题不对即红，改名成什么都不影响判定。
            _run = _mx = 0
            for _l2 in _ls:
                if re.match(r"^\s*[-*]\s*\[[^\]]+\]\(#[^)]+\)", _l2):
                    _run += 1
                    _mx = max(_mx, _run)
                else:
                    _run = 0
            if _mx >= 3:
                doc_fail.append("17j-13 %s 有 %d 条连续的目录条目（`- [x](#y)`）却找不到 `## 目录` 标题"
                                "—— 标题被改名／删掉了？（锚点解析／顺序／完整性三臂都靠它定位，"
                                "缺了会整族静默失效）" % (_nm, _mx))
            continue
        _j = _ti + 1
        _toc = []
        while _j < len(_ls) and not re.match(r"^#", _ls[_j]):
            if _ls[_j].strip():
                _toc.append(_ls[_j])
            _j += 1
        _mask13 = _fence_mask(_ls)
        _body = [_toc_key(_hm.group(1)) for _hm in
                 (re.match(r"^#{1,6}\s*(.+?)\s*$", _x) for _k, _x in enumerate(_ls[_j:])
                  if not _mask13[_j + _k]) if _hm]
        _idxs = []
        for _t in _toc:
            _m = _toc_link(_t)
            if not _m:
                continue
            _anch = _toc_key(_m.group(2))
            _cand = [_bi for _bi, _s in enumerate(_body) if _s.startswith(_anch)]
            if not _cand:
                doc_fail.append("17j-13 %s 目录条目「%s」的锚点 #%s 在正文找不到对应小节"
                                % (_nm, _m.group(1)[:24], _m.group(2)[:40]))
            else:
                _idxs.append(_cand[0])
        if any(_idxs[_z] >= _idxs[_z + 1] for _z in range(len(_idxs) - 1)):
            doc_fail.append("17j-13 %s 目录条目顺序与正文小节顺序不一致" % _nm)

        # 目录完整性（**与 17j-13 同族、⛔ 不新开编号**）：带 `## 目录` 的文件里，每个 `##` 级小节
        #   必须有**至少一条**目录项命中它。
        #   起因（不这么做会漏什么）：`17j-13` 只 `for _t in _toc` 遍历**已存在**的条目 ⇒ 条目被**删掉**
        #     时没有可遍历对象、无从判红（实测：删掉一条目录项后 `--only docs` 与**全量 13 块**均
        #     `rc=0`、`[FAIL] 0`）⇒ 本臂补的正是"条目缺失"这一面。
        #   ⛔ **顺序仍归 17j-13**：此处只判"有没有／重复几条"，不复判单调（重复判会让一处缺陷报两行）。
        #   ⚠️ **本臂无独立守卫编号** ⇒「把这段整块删掉」**不会被块名基线抓到** —— 属**已知盲区**。
        #     不开 `17j-15` 的理由：块名基线要求"基线外新块名须在 `CHANGELOG.md` 被独立提及"，
        #     而未发布的批不许写版本段 ⇒ 开号会当场撞红。这是**制度互斥、不是漏做**。
        #   ⚠️ 覆盖面**只到 `##` 级**：`###` 及更深的子标题**不进目录也不判**（本仓的目录只索引到二级）；
        #     另有一处**已知盲区**：新增一份带 `## 目录` 的文件时，本臂**不知道**它里面哪些小节是
        #     "有意不进目录"的 ⇒ 会当缺失判红，需人工确认后再决定是否补豁免（⛔ 别据此说"已全覆盖"）。
        #   ⭐ **配对方式：按锚点解析结果（`_idxs`）判，⛔ 不按 TOC 标签的前导整数判** ——
        #     标签**允许缩写**（`- [\`Wb.request\`](#1-wbrequest)` 就是合法写法，去掉后半句也不算错），
        #     按整数配对会把这种合法写法判成"第 1 节没有目录条目"（假红）；而且 `3.1` 这类**子条目**
        #     的前导整数是 3，会跟 `## 3.` 撞车（假重复）。⇒ 只认"这个正文小节有没有被某条目录项命中"。
        _tc_num_bi = []
        _tc_k = -1
        for _tco, _tcx in enumerate(_ls[_j:]):
            if _mask13[_j + _tco]:
                continue
            _tch = re.match(r"^#{1,6}\s*(.+?)\s*$", _tcx)
            if not _tch:
                continue
            _tc_k += 1                      # 与 `_body` 同一构造顺序 ⇒ 下标一一对应
            if re.match(r"^##\s", _tcx):    # 二级标题（`###` 起不匹配：`##` 后须紧跟空白）
                _tc_num_bi.append((_tc_k, _tch.group(1)))
        for _tcbi, _tctitle in _tc_num_bi:
            # 一次性豁免清单：**标题有意不进目录**的小节，逐条写全（文件 ＋ 标题逐字，锚点式）。
            #   ⛔ 不建"免目录登记机制" —— 那等于写死名单（与"⛔ 不许退化成写死的名单"那条明令相撞），
            #     且每条都要人填，与"制度靠人记"同病 ⇒ 只豁免现网这几处，⛔ 不预留扩充机制。
            if any(_nm == _ef and _tctitle.startswith(_ep) for _ef, _ep in _TOC_HEAD_EXEMPT):
                continue
            _tcc = _idxs.count(_tcbi)
            if _tcc == 0:
                doc_fail.append("17j-13 %s 小节「%s」**没有目录条目**（每个 `##` 级小节须至少一条；"
                                "若是有意不进目录，请登记到模块级 `_TOC_HEAD_EXEMPT`）"
                                % (_nm, _tctitle[:28]))
            elif _tcc > 1:
                doc_fail.append("17j-13 %s 小节「%s」的目录条目**重复 %d 条**"
                                % (_nm, _tctitle[:28], _tcc))

    # 豁免存在性自校验：每条前缀必须命中目标文件里**恰好一个** `##` 标题。
    #   0 个 ⇒ 标题改了、这条豁免已经对不上（静默失效）；≥2 个 ⇒ 前缀太泛，会放过不该放的标题。
    for _ef, _ep in sorted(_TOC_HEAD_EXEMPT):
        _els = docs.get(_ef)
        if _els is None:
            doc_fail.append("17j-13 豁免条目 %s「%s」的目标文件读不到 —— 改名了？" % (_ef, _ep))
            continue
        _emask = _fence_mask(_els)
        _ehits = [(_ei, _el[3:].strip()) for _ei, _el in enumerate(_els, 1)
                  if _el.startswith("## ") and not _emask[_ei - 1]
                  and _el[3:].strip().startswith(_ep)]
        if len(_ehits) == 0:
            doc_fail.append("17j-13 豁免条目 %s「%s」失效，标题改了？（前缀一个 `##` 都对不上）"
                            % (_ef, _ep))
        elif len(_ehits) >= 2:
            doc_fail.append("17j-13 豁免条目 %s「%s」前缀太泛，收紧（命中 %d 个 `##`：%s）"
                            % (_ef, _ep, len(_ehits),
                               "、".join(_et[:20] for _en, _et in _ehits)))

    # 「有目录就必须登记」：精确 `^## 目录$` 的文件若不在 `_TOC_REQUIRED` 里 ⇒ 判红。
    #   ⛔ 用精确匹配，不用前缀 —— `## 目录结构` 不是目录节（README.md 就是这种）。
    #   现网精确 7 份与表内 7 份对齐，所以这条上线后现网 0 红；证据靠注入，不靠这次绿。
    for _tn, _tls in docs.items():
        if _tn == "CHANGELOG.md":
            continue
        if any(re.match(r"^##\s*目录\s*$", _tl) for _tl in _tls) and _tn not in _TOC_REQUIRED:
            doc_fail.append("17j-13 %s 有目录但未登记 `_TOC_REQUIRED`（新增文件请登记）" % _tn)

    # 登记表自校验：登记了却读不到的 ⇒ 报红（⛔ 不许静默跳过）。**没有它**，文件一改名，
    #   `_TOC_REQUIRED` 就悄悄变成一条什么都管不着的死条目 —— 而"少判一份"不会有任何症状。
    _toc_absent = sorted(_TOC_REQUIRED - set(docs))
    if _toc_absent:
        doc_fail.append("17j-13 目录登记表里有读不到的文件：%s —— 改名了？（⛔ 别把死条目留在表里）"
                        % _toc_absent)

    # 17j-14 把 17j-6 扩到**围栏块**：围栏里以 `[note]/[warn]/[FAIL]/[ok]` 开头的**示例输出**，
    #   其文案**整串**也必须在工具**真跑出来的输出**里找得到（oracle 同 17j-6：来自 `_real_out_corpus()`）。
    #   扫描面 = `docs` 的围栏块（**含**全部正文 md，**不含 `CHANGELOG.md`** —— 它是历史记录，
    #     按写入时的事实记，与全族其它臂的"历史豁免"口径一致；**也不含 `examples/README.md`**）。
    #     ⚠️ **跳 `CHANGELOG.md`**：本臂若**无**该跳过 ⇒ CHANGELOG 的历史围栏输出会按**当前** `xwl.py`
    #       校验（历史文案早于现实现的即被误判）。现围栏内标签行实测为 0 ⇒ 属**潜伏误报源**，非现网红。
    #     ⚠️ 不纳入 `examples/README.md` 是**有意**的：该文件里有**运行期 f-string 拼出来**的示意输出
    #       （模板形如 `（{why}）—— {stat}`、在 `xwl.py` 一带），其**整串在真实输出里也拼不出来** ⇒
    #       纳入会**误报**（QA 实测：那一行在真跑语料里找不到、而同文件别的 tag 行找得到）。
    #   起因：17j-6 只扫 SKILL 的**行内反引号**、且不扫 faq.md ⇒ 写在 ``` 块里的输出文案对它
    #     **零覆盖**（绿但空）⇒ 本臂补上"围栏块"这一面。
    #   误报控制：围栏示例可能是**示意**（占位符 `<path>` / `…` / `%s` / `%d`）⇒ 含这类占位符的行
    #     **跳过**（不判），避免把"示例"当成"承诺文案"。实测：3 条围栏输出行，1 条含占位符被跳过、
    #     2 条被检查且都在真实输出里 ⇒ 全绿（这档 = 加白名单）。
    #   ⚠️ 边界（⛔ 臂归属别串）：本臂比的是**整串** —— `_nf` 是"去标签后抹掉空白"的整串，本文件对
    #     它不切片（判据形如 `_vn_body not in _real_vn`，两侧都过 `_vn`）；`[:16]` **不属本臂**，
    #     它属 `17j-6` 的行内反引号臂。⇒ 本臂**验不了运行期拼接**出来的文案 —— 拼接结果在真跑
    #     语料里没有字面**整串**，所以这类**不是漏扫、是扫了会错**（故排除）。
    _real_vn = _vn(real_out)      # 抹一次就够：⛔ 别放进逐行循环里重复抹（纯浪费，且容易改错一侧）
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":       # 历史记录：按写入时的事实记，不按当前 xwl.py 校验
            continue
        _fence = 0
        for _i, _l in enumerate(_ls, 1):
            if _l.strip().startswith("```"):
                _fence += 1
                continue
            if _fence % 2 == 0:
                continue
            _st = _l.strip()
            _tag = next((_t for _t in ("[note]", "[warn]", "[FAIL]", "[ok]") if _st.startswith(_t)), None)
            if not _tag:
                continue
            _body2 = _st[len(_tag):].strip()
            if _fence_ph.search(_body2):
                continue
            _nf = re.sub(r"\s+", "", _body2)
            if len(_nf) < 8:
                continue
            _vn_body = _vn(_nf)
            # ⚠️ **抹完只剩可变段**的行验不了：`[note] position9876543` 抹后是 `[note]«V»`，
            #   而「[note]«V»」这种串在语料里必然存在 ⇒ 恒真。这种行**判红**（"该写实词"），
            #   ⛔ 不许用"整句都是 0x??/position N"来占位 —— 那等于把一行免检。
            if len(_vn_body.replace("«V»", "")) < 8:
                doc_fail.append("17j-14 %s:%d 围栏输出行抹掉可变段后只剩 %d 个字 —— "
                                "这一行验不了（占位把判据掏空了），请写实词"
                                % (_nm, _i, len(_vn_body.replace("«V»", ""))))
            elif _vn_body not in _real_vn:
                doc_fail.append("17j-14 %s:%d 围栏块输出文案 `%s…` 在工具的**真实输出**里找不到"
                                "（若确为工具会打印的新文案，请在 `_real_out_corpus()` 里补一次真实调用）"
                                % (_nm, _i, (_tag + _body2)[:34]))

    # 行号锚点四形：现值面一律 0 命中（本函数第 4 臂，与 17j-12／17j-13／17j-14 同族）。
    #   起因（不这么做会漏什么）：行号随平台版本漂移、且**本机不可复核**（同一工程不同版本
    #     行号必不相同）⇒ 本仓早把它列为「已证伪的维护手段」，却一直只是**说法** —— 没有任何
    #     一条判据管它，于是现值面残留 4 处行号 ＋ 2 处「行号取自样本工程版本」的免责句。
    #   ⭐ 面切（最重要的一条）：**只扫现值面**，⛔ 不扫 `plan/`／`rules/` —— 那两面是**历史记录**，
    #     改它等于改写那一刻的结论。判据是「同一个数字，位置决定它是现值还是历史」。
    #   ⚠️ `doc_names` 的扫描面**含 `CHANGELOG.md`**（历史面，实测四形 **6 行 / 8 处**）⇒ 必须**显式排除**，
    #     否则守卫上线即红。⛔ 别把这条排除删掉"求干净"。
    #   ⚠️ 已知盲区：`examples/README.md` 有 1 处四形命中，而它**不在** `doc_names` 里 ⇒ 本臂不扫
    #     （示例说明允许写形态示例）；⛔ 别据此说"全仓 0 命中"。
    #   ⚠️ **本臂无独立守卫编号**（并入 `17j` 家族、不开 `17j-15`）⇒「把这段整块删掉」**不会被
    #     块名基线抓到**（块名基线只认 `# 17<字母>` 块头，本臂挂在 `_doc_guard_xfile_pt` 体内）。
    #     不开号的理由是制度互斥：基线外新块名须在 `CHANGELOG.md` 被独立提及，而未发布的批不许写
    #     版本段 ⇒ 开号当场撞红。⇒ 这是**已知盲区、不是漏做**；翻掉它要等发布批连带开号。
    #   第 3 形取**5 类扩展名**（`js|py|md|json|xwl`）：只禁恰好撞见的那一种 ＝ 下一个人写 `.py:`
    #     就静默通过。⚠️ `.sql`／`.ts`／无扩展名**不在面内**（扩到全扩展名会与 `a.com:8080` 的
    #     host:port 撞车）⇒ ⛔ 别读成"任何 文件:行号 都禁"。
    #   ⚠️ 第 3 形的**唯一已知误伤**：URL 带端口（`https://a.com/x.js:8080`，匹配文本以 `//` 开头）
    #     ⇒ 含 `//` 的匹配直接放过（真正的行号引用不会含 `//`）。
    _ln4 = (
        ("裸行号 `:N`", re.compile(r"`:[0-9]{1,5}`")),
        ("`L` 编号", re.compile(r"`L[0-9]{1,4}`")),
        ("文件:行号", re.compile(r"[A-Za-z0-9_./-]+\.(?:js|py|md|json|xwl):[0-9]+")),
        ("中文「第 N 行」", re.compile(r"第\s*[0-9]+\s*行")),
    )
    for _nm4, _ls4 in docs.items():
        if _nm4 == "CHANGELOG.md":     # 历史记录：按写入时的事实记，不按现值面判
            continue
        for _i4, _l4 in enumerate(_ls4, 1):
            for _lab4, _rx4 in _ln4:
                _m4 = _rx4.search(_l4)
                if _m4:
                    # ⚠️ 第 3 形的**唯一已知误伤**：URL 带端口（`https://a.com/x.js:8080`）会被
                    #   `文件:行号` 形命中（匹配文本以 `//` 开头）。URL 与"行号锚点"是两回事 ⇒
                    #   含 `//` 的匹配直接放过（真正的行号引用不会含 `//`）。
                    if "//" in _m4.group(0):
                        continue
                    doc_fail.append("行号锚点（%s）%s:%d 出现 `%s` —— 现值面不写行号"
                                    "（行号随平台版本漂移、本机不可复核）；要定位就写**符号名**"
                                    % (_lab4, _nm4, _i4, _m4.group(0)))


def _b17r_mask_strings(_text):
    """把 .py 里字符串字面量的内容抹成空格（保留行列结构），供 17r 判据使用。"""
    try:
        _toks = list(tokenize.generate_tokens(io.StringIO(_text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    _starts, _acc = [], 0
    for _ln in _text.split("\n"):
        _starts.append(_acc)
        _acc += len(_ln) + 1
    _buf = list(_text)
    for _tk in _toks:
        _nm = tokenize.tok_name.get(_tk.type, "")
        if _nm == "STRING" or _nm.startswith("FSTRING"):
            _a = _starts[_tk.start[0] - 1] + _tk.start[1]
            _b = _starts[_tk.end[0] - 1] + _tk.end[1]
            for _k in range(_a, min(_b, len(_buf))):
                if _buf[_k] != "\n":
                    _buf[_k] = " "
    return "".join(_buf)


def _b17r_history_skip(_rel, _text):
    """「历史记录类载体」中应**整段跳过**扫描的行号集合（1 基）；无 ⇒ 空集。

    判据（**按语义、非按文件名单**）：`CHANGELOG.md` 已有整体豁免（它是历史记录）；`metadata.json` 的
    `update_history` 段是**同语义**（契约字段、只记录历史、不改写）⇒ 把既有豁免**按语义推广**到该段 ——
    该段整体跳过，**其余字段仍在扫描面**（⛔ 不整文件豁免 `metadata.json`）。
    实现：定位 `update_history` 键值后的 `[`，做**字符串感知**的括号配对找闭合 `]`，再折算成行号区间。
    """
    if not _rel.endswith(".json"):
        return set()
    _k = _text.find('"update_history"')
    if _k < 0:
        return set()
    _j = _text.find("[", _k + len('"update_history"'))
    if _j < 0:
        return set()
    _depth = 0
    _in = False
    _esc = False
    _p = _j
    while _p < len(_text):
        _c = _text[_p]
        if _in:
            if _esc:
                _esc = False
            elif _c == "\\":
                _esc = True
            elif _c == '"':
                _in = False
        else:
            if _c == '"':
                _in = True
            elif _c == "[":
                _depth += 1
            elif _c == "]":
                _depth -= 1
                if _depth == 0:
                    break
        _p += 1
    _ls = _text.count("\n", 0, _j) + 1
    _le = _text.count("\n", 0, _p) + 1
    return set(range(_ls, _le + 1))



# ---- 同批「有界下沉」续 2：`_check_docs` 内的**纯助手**（`_trows`，只依赖入参）----
#   位置口径同前述；判据、注释、扫描面**逐字未改**，函数体只留引用（指针）。

def _trows(ls):
    return {l.strip() for l in ls
            if l.strip().startswith("|") and l.strip().endswith("|")
            and not set(l.strip()) <= set("|-: ")}


# ---- `#82` 的**通用解析式守卫**（并入既有 17h 块，⛔ 不新增块名）----
#   起因（按守卫维护纪律写清"不这么做会漏什么"）：`#82` 的既有裁定是「**登记为已知无守卫、
#     ⛔ 不加窄守卫**」—— 因为候选处置（硬编码某一个 flag 名的断言）属「纸糊式」：
#     那个 flag 一改名断言照样绿、而新写错的另一条样例照样绿。⇒ **正解是机械验证「照抄能跑通」**：
#     把文档里写给用户看的 `xwl.py <命令> …` 逐条喂 `build_parser().parse_args()`，
#     解析器拒哪条就红哪条 —— 与具体 flag 名、与子命令清单**都无关**（解析器本身是唯一权威）。
#   ⚠️ 抽取面**可枚举、⛔ 不写死文件清单**：走 `_doc_names(root)`（根三份 + `references/` 磁盘推导）
#     ⇒ 后续在 `references/faq.md` 增删一条命令样例会**自动进/出**本守卫，不必改代码；
#     只排除 `CHANGELOG.md`（历史记录按写入时的事实记）。
#   ⚠️ 只收**围栏块内、整行以 `xwl.py` 起头**的形态（＝真能照抄的形态）：行内反引号里的
#     `xwl.py new`（散文提及、无参数）不算 —— 拿它判会把"提个名字"误判成"样例坏了"。
#   ⚠️ 含模板记法（`…` ／ `|`）的行 ⇒ **截断到第一个模板记号之前、`[` 起的可选组舍去** 后
#     **仍送解析器判一次**（`_prompt_cmd_prefix_argv`）：能过 ＝ 合法的省略写法，过不了 ＝ 照样红
#     —— 否则**加个 `…` 就能免检**（实测：只要文档里还有别的合法样例，坏样例带 `…` 即整体仍绿）；
#     条数仍打进 `[ok]` 行。
#   ⭐ 序3（1.8.4）：`<占位>/scripts/xwl.py` 类命令**照抄即失败**，但旧抽取把脚本路径整段当
#     「`(?:\S*/)?xwl\.py`」前缀吃掉，只把 `new <占位路径>` 交给 argparse ⇒ **完全不可照抄的命令被判绿（假绿）**。
#     新版把**脚本路径 token 单独捕获**（引号包裹 / `$VAR` / `$env:VAR` / 绝对 / 相对 均可），
#     再判它是否为**尖括号占位**（`<...>`）：含 `<`／`>` ⇒ 无法照抄 ⇒ 判红；`$SKILL_ROOT`／绝对路径／
#     相对 `scripts/xwl.py` 等正确写法 ⇒ 判绿。同时保留原判：命令体仍逐条喂 `parse_args()`。
#     ⚠️ 续行（行尾 `\`）先剥掉再判，`$SKILL_ROOT`/引号包裹**不误报**。
_PROMPT_CMD_RE = re.compile(
    r'^\s*(?:python3?\s+)?'
    r'(?P<path>"[^"]*xwl\.py"|\'[^\']*xwl\.py\'|(?:\$[^\s"]*|~?[^\s"]*|)[^\s"]*xwl\.py)'
    r'(?P<rest>(?:\s+.*)?)$'
)
_PROMPT_TEMPLATE_MARKS = ("…", "|")


def _prompt_cmd_strip_comment(s):
    """去掉行尾 shell 注释（`#` 前须为行首或空白；引号内的 `#` 不动）。"""
    _q = None
    for _i, _ch in enumerate(s):
        if _q:
            if _ch == _q:
                _q = None
        elif _ch in ("'", '"'):
            _q = _ch
        elif _ch == "#" and (_i == 0 or s[_i - 1].isspace()):
            return s[:_i]
    return s


def _prompt_cmd_prefix_argv(body):
    """模板记法行 ⇒ 可判定的**前缀 argv**（截到第一个模板记号前；`[` 起的可选组整段舍去）。

    ⚠️ 为什么不能直接跳过：`xwl.py check a.xwl --no-such-flag …` 这类**坏样例**一旦带 `…`
    就会被静默放行（实测：只要文档里还有别的合法样例，整体仍绿）⇒ 守卫漏检。
    截断后仍送解析器：`--no-such-flag` 不存在就会红；而 `xwl.py params <page.xwl> [--controls …]`
    截成 `params <page.xwl>` 能过 —— 两边都不冤。
    """
    _cut = len(body)
    for _t in _PROMPT_TEMPLATE_MARKS:
        _i = body.find(_t)
        if 0 <= _i < _cut:
            _cut = _i
    _out = []
    for _tok in body[:_cut].split():
        if _tok.startswith("["):
            break
        _out.append(_tok)
    return _out


def _prompt_cmd_script_path_is_placeholder(path_token):
    """脚本路径 token 是否为**尖括号占位**（`<skill根>/scripts/xwl.py` 之类 ⇒ 照抄必挂）。

    正确写法（`$SKILL_ROOT/scripts/xwl.py`、`$env:SKILL_ROOT/…`、绝对路径、相对 `scripts/xwl.py`）
    都不含 `<`／`>` ⇒ 判绿、不误报。去掉两侧引号后判断。
    """
    _pb = path_token.strip().strip("\"'")
    return ("<" in _pb) or (">" in _pb)


def _doc_prompt_cmds(root):
    """从文档围栏块里抽 `xwl.py <命令> …` 样例。

    返回 `(参与判定的 [(rel,行号,argv 文本)], 模板记法行 [(rel,行号,argv 文本)], 占位路径行 [(rel,行号,路径 token,argv 文本)])`。
    ⚠️ 占位路径行（脚本路径含 `<...>`）**单列一栏**：它们照抄必失败，先于可解析性判红。
    """
    _got, _skip, _ph = [], [], []
    for _rel in [n for n in _doc_names(root) if n != "CHANGELOG.md"]:
        try:
            with open(os.path.join(root, _rel.replace("/", os.sep)), encoding="utf-8") as _fh:
                _lines = _fh.read().splitlines()
        except OSError:
            continue
        _in = False
        _idx = 0
        while _idx < len(_lines):
            _ln = _lines[_idx]
            _no = _idx + 1
            _idx += 1
            if _ln.strip().startswith("```"):
                _in = not _in
                continue
            if not _in:
                continue
            if not _PROMPT_CMD_RE.match(_ln):
                continue
            # ⭐ 续行处理：行尾 `\` ⇒ 与后续物理行拼成**一条逻辑命令**再判
            #   （`python … patch x.xwl \` + `  --ops ops.json` 必须整体喂 argparse，
            #    否则缺 `--ops` 会被误判红 —— 这正是「续行不误报」的要求）。
            _merged = _ln
            while _merged.rstrip().endswith("\\") and _idx < len(_lines):
                _merged = _merged.rstrip()[:-1].rstrip() + " " + _lines[_idx].strip()
                _idx += 1
            _m = _PROMPT_CMD_RE.match(_merged)
            if not _m:
                continue
            _body = _prompt_cmd_strip_comment(_m.group("rest") or "").strip()
            if _body.endswith("\\"):
                _body = _body[:-1].rstrip()
            if not _body:
                continue
            _path = _m.group("path")
            if _prompt_cmd_script_path_is_placeholder(_path):
                _ph.append((_rel, _no, _path.strip().strip("\"'"), _body))
                continue
            if any(_t in _body for _t in _PROMPT_TEMPLATE_MARKS):
                _skip.append((_rel, _no, _body))
                continue
            _got.append((_rel, _no, _body))
    return _got, _skip, _ph


def _doc_prompt_cmd_probe(root):
    """判**每条文档命令样例都能被解析器接住** ⇒ `(FAIL 文案 or None, 判定条数, 模板记法条数)`。"""
    _got, _skip, _ph = _doc_prompt_cmds(root)
    if not (_got or _skip or _ph):
        return ("prompt 命令样例守卫：一条 `xwl.py <命令>` 样例都没抽到 ⇒ 本项无法判定，判红"
                "（抽取面可能已失效：围栏块标记或起头形态变了）", 0, len(_skip))
    # ⭐ 序3：**脚本路径含尖括号占位 ⇒ 照抄必失败**，先于可解析性判红（旧判据在此处是假绿）。
    if _ph:
        _pb = ["%s:%d 脚本路径「%s」含尖括号占位 —— 照抄到 shell 必失败"
               "（PowerShell 报 Invalid argument；POSIX 把 < > 当重定向）⇒ 先设 SKILL_ROOT 变量再引用，"
               "如 `python \"$SKILL_ROOT/scripts/xwl.py\" …`" % (_rel, _no, _path)
               for _rel, _no, _path, _body in _ph]
        return ("prompt 里的命令样例有 %d 条**照抄跑不通**（脚本路径是尖括号占位，不是可执行的真实路径）：%s"
                % (len(_ph), "；".join(_pb[:6])), len(_got), len(_skip))
    try:
        _ap = xwl.build_parser()
    except Exception as _exc:  # noqa: BLE001
        return "prompt 命令样例守卫：`build_parser()` 跑不起来：%s" % _exc, len(_got), len(_skip)
    _bad = []
    for _rel, _no, _body in _got:
        try:
            _argv = shlex.split(_body)
        except ValueError as _exc:
            _bad.append("%s:%d 「%s」引号不闭合（%s）" % (_rel, _no, _body, _exc))
            continue
        _err, _out = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stderr(_err), contextlib.redirect_stdout(_out):
                _ap.parse_args(_argv)
        except SystemExit as _exc:
            if _exc.code not in (0, None):     # `--help` 走 `SystemExit(0)`：能跑通，不算红
                _last = (_err.getvalue().strip().splitlines() or ["（解析器没给错因）"])[-1]
                _bad.append("%s:%d 「%s」⇒ %s" % (_rel, _no, _body, _last))
        except Exception as _exc:  # noqa: BLE001
            _bad.append("%s:%d 「%s」⇒ %s: %s" % (_rel, _no, _body, type(_exc).__name__, _exc))
    # ⭐ 模板记法行（`…` / `|`）**不再免检**：截断到第一个记号之前、可选组舍去后仍判一次。
    for _rel, _no, _body in _skip:
        _p_argv = _prompt_cmd_prefix_argv(_body)
        if not _p_argv:
            continue
        _p_err, _p_out = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stderr(_p_err), contextlib.redirect_stdout(_p_out):
                _ap.parse_args(_p_argv)
        except SystemExit as _exc:
            if _exc.code not in (0, None):
                _p_last = (_p_err.getvalue().strip().splitlines() or ["（解析器没给错因）"])[-1]
                _bad.append("%s:%d 「%s」⇒ 截断前缀「%s」被判 %s（模板记法**不等于**可以写错参数）"
                            % (_rel, _no, _body, " ".join(_p_argv), _p_last))
        except Exception as _exc:  # noqa: BLE001
            _bad.append("%s:%d 「%s」⇒ %s: %s" % (_rel, _no, _body, type(_exc).__name__, _exc))
    if _bad:
        return ("prompt 里的命令样例「照抄跑不通」%d/%d 条（文档写的命令必须能被 `xwl.py` 的解析器接住；"
                "改了参数 / 子命令请**同批**改文档）：%s"
                % (len(_bad), len(_got) + len(_skip), "；".join(_bad[:6])), len(_got), len(_skip))
    return None, len(_got), len(_skip)


# ---- 源码行号引用守卫的模块级助手（并入 17m 块，⛔ 不新开块名）----
#   起因：全仓「源码行号引用」实测 5 处已过期，且 4 处**裸冒号**（只写行号、不写符号名）4/4 全废 ——
#     行号不随代码一起走，「只写数字」的引用一旦漂了，人眼复核必漏（改一处行为、引用还指着旧位置）。
#   判据两形态：
#     ① `` `符号名`（`:N`） ``（全角 / 半角括号）⇒ **可校验**：目标文件第 N 行（±1 行窗口）必须含该符号名；
#     ② `xxx.py:N` ⇒ 只校验「行号不越界」：目标行语义千变万化，机械判不了「像不像符号」，
#       强判会造一片假阳性（故**只挡越界**，不判内容）。
#   ⛔ 不扫「第 N 行」（工作区第 0 行 / 参考材料第 1 行 / 基线第 1 行 是**业务语义**，与源码行号无关）。
_SRC_REF_FILES = ("scripts/xwl.py", "scripts/selftest.py")


def _src_ref_abspath(rel: str) -> str:
    """源码行号引用守卫的**按文件分别定根**：`xwl.py` 在运行面 `SKILL_ROOT/scripts/`，
    `selftest.py` 仍在开发树 `HERE`（分发目录重排后两者不同根，⛔ 不能共用一个 root）。"""
    if rel == "scripts/xwl.py":
        return os.path.join(SKILL_ROOT, "scripts", "xwl.py")
    return os.path.join(HERE, "selftest.py")


def _src_line_ref_fails(root: str) -> list[str]:
    """校验 `scripts/` 下两个文件的源码行号引用是否仍指得准（读不出 ⇒ 判红，不算「没命中」）。

    `root` 保留为签名参数（既有调用方传技能根），实际路径由 `_src_ref_abspath` **按文件**定根。
    """
    _f1 = re.compile(r"`([^`\n]{1,80})`\s*[（(]\s*`:(\d+)`")
    _f2 = re.compile(r"([A-Za-z0-9_./\\-]+\.py):(\d+)")
    _src: dict = {}
    for _r in _SRC_REF_FILES:
        try:
            with open(_src_ref_abspath(_r),
                      encoding="utf-8", newline="") as _fh:
                _src[_r] = _fh.read().splitlines()
        except OSError as _exc:
            return ["源码行号引用守卫跑不起来：读不出 %s（%s）—— 报错，不算「没命中」" % (_r, _exc)]
    _bad: list[str] = []
    for _r, _ls in _src.items():
        for _i, _l in enumerate(_ls, 1):
            # 形态①：目标文件 = 本行里该引用**之前**最近的一处 `xxx.py`；一处都没有 ⇒ 本文件（自引用）。
            for _m in _f1.finditer(_l):
                _sym, _n = _m.group(1).strip(), int(_m.group(2))
                _pre = _f2.findall(_l[:_m.start()])
                _tgt = os.path.basename(_pre[-1][0]) if _pre else os.path.basename(_r)
                _tl = _src.get("scripts/" + _tgt)
                if _tl is None:
                    continue                     # 指向本仓其它 .py ⇒ 不在扫描面，无从判定
                _win = _tl[max(0, _n - 2):_n + 1]      # 第 N 行 ±1（0 基切片）
                if _sym and not any(_sym in _x for _x in _win):
                    _seen = _tl[_n - 1] if 1 <= _n <= len(_tl) else "（行号越界）"
                    _bad.append("%s:%d 引用处 → 声称 `%s`（`:%d`），但 %s 第 %d 行是 `%.60s`，"
                                "疑已漂移，请按符号名重定位"
                                % (_r, _i, _sym, _n, _tgt, _n, _seen.strip()))
            # 形态②：`xxx.py:N` ⇒ 只挡越界（内容判不了，强判会假阳性）。
            for _m in _f2.finditer(_l):
                _tgt, _n = os.path.basename(_m.group(1)), int(_m.group(2))
                _tl = _src.get("scripts/" + _tgt)
                if _tl is None:
                    continue
                if not (1 <= _n <= len(_tl)):
                    _bad.append("%s:%d 引用处 → `%s:%d` 越界（该文件只有 %d 行）"
                                % (_r, _i, _tgt, _n, len(_tl)))
    return _bad


# 跨段变量缺席探针的**重入闸**：探针要真调 `_docs_tail_scaffold`，而该段自己也会跑这条探针
#   ⇒ 用模块级单元素 list 挡重入（在无嵌套函数处用不上 `nonlocal`）。
_ABSENT_S_PROBE = [False]


# ---- 入口形态守卫（并入 `17j` 家族、⛔ 不开独立编号）----
#   起因（不这么做会漏什么）：工具失败时打印的"重跑"提示是现场**唯一自救手段**，而它一旦写裸相对
#     路径（`python scripts/xwl.py …`），调用方的 cwd 是业务工程时必然找不到脚本；路径带空格／中文
#     又不加引号时还粘不上。同一条口径在文档里另有 40 余处，逐处靠人抄对没人拦得住。
#   ⛔ 无独立守卫编号的理由：块名基线要求"基线外新块名须在 `CHANGELOG.md` 被独立提及"，而**未发布的
#     批不许写版本段** ⇒ 开号当场撞红（制度互斥、不是漏做）。⇒ **已知盲区**：整段删掉不会被块名基线抓到。
#   ⚠️ `examples/README.md` **有意不进** `_doc_names`（该文件有运行期 f-string 拼出的示意输出，纳入会让
#     8 个文档守卫的逐字比对臂误报）⇒ 它的调用形态由本臂**独立只读**判，⛔ 别把它塞进 `_doc_names`。
#   ⚠️ 扫描面 ＝ 文档守卫的扫描面（`_doc_names`，**排除 `CHANGELOG.md`** —— 历史记录按写入时的事实记）
#     ＋ `examples/README.md`（后者**有意不进** `_doc_names`：它有运行期 f-string 拼出的示意输出，
#     纳入会让 8 个文档守卫的逐字比对臂误报）。⛔ 别把 `examples/README.md` 塞进 `_doc_names`。
#   ⚠️ 已知盲区：本臂**没有**"某份文件必须先抽到样例"的要求（只有"全仓一条都抽不到"才判红）——
#     把命令样例整体下沉到 `references/` 是**被预算守卫鼓励**的动作，逼每份文件必须有样例会与之相撞。
_ENTRY_SKIP = ("CHANGELOG.md",)

# 入口形态的**唯一判据**：`python` 家族命令里，`scripts/xwl.py` 与 `scripts/selftest.py` 前
#   必须有**路径前缀**（占位符 `<…>` ／ Unix 绝对 `/…` ／ 盘符绝对 `X:…` ／ **变量前缀**
#   `$SKILL_ROOT/…`、`${SKILL_ROOT}/…`、`$env:SKILL_ROOT/…`、`%SKILL_ROOT%/…`）。写成"整条命令能命中本正则"
#   而非手工找斜杠，是因为手工写法要先剥引号、再处理空格与反斜杠，三处任一漏掉就假绿（实测栽过两处）。
#   ⚠️ 变量前缀（round2 新增）与 `<…>`/绝对路径**同权**：它们同样**不是裸相对路径**、脚本可定位
#     （调用方先 `export SKILL_ROOT=…` 再引用，cwd 无关）⇒ 视为"有前缀"；⛔ **裸 `scripts/xwl.py`（无前缀）仍判红**。
#   ⚠️ `selftest.py` 与 `xwl.py` **同一条规则**，不另造一套。只扩文档面（`.md` ＋ `examples/README.md`），
#   ⛔ 不扩到 `.py` 源码：`selftest.py` 自己的 docstring 在 skill 根下跑，裸写是对的。
_ENTRY_OK_RE = re.compile(
    r"""(?:\A|[\s"'])(?:<[^>\n]*>|/|[A-Za-z]:|\$\{[^}\n]*\}|\$[A-Za-z_][A-Za-z0-9_]*(?::[A-Za-z_][A-Za-z0-9_]*)?|%[^%\n]+%)[^"\n]*?/scripts/(?:xwl|selftest)\.py""")

# `python` 家族的命令头：`python`／`python3`／`py -3`／`uv run python`。
#   ⚠️ 只认 `python ` 会让后三种写法**完全不在射程内**（实测抽取数 0 ⇒ 绿得毫无道理）。
_ENTRY_HEAD_RE = re.compile(
    r"^\$?\s*(?:python[\d.]*|py(?:\s+-[\d.]+)?|uv\s+run(?:\s+python[\d.]*)?)\s+")


def _entry_cmds(line: str) -> list:
    """从一行里抽「以 `python` 家族命令起头的调用原文」（容忍 `$ ` 提示符、`> ` 引用块、行内反引号）。"""
    _t = line.strip()
    if _t.startswith(">"):
        _t = _t.lstrip(">").strip()
    _out = []
    if _ENTRY_HEAD_RE.match(_t):
        _out.append(_t)
    for _m in re.finditer(r"`([^`]+)`", _t):
        _c = _m.group(1).strip()
        if _ENTRY_HEAD_RE.match(_c):
            _out.append(_c)
    return _out


def _entry_prefix_missing(cmd: str) -> bool:
    """命令里的 `scripts/xwl.py` 或 `scripts/selftest.py` 是否**缺路径前缀**。

    `<…>` 占位符／Unix 绝对／盘符绝对／**变量前缀**（`$SKILL_ROOT/…`、`${SKILL_ROOT}/…`、
    `$env:SKILL_ROOT/…`、`%SKILL_ROOT%/…`）都不算缺；只有**裸相对**（无任何路径前缀）才算缺。两条脚本同一条规则。
    ⚠️ 两处归一化缺一即错：① **反斜杠视同 `/`**（Windows 写法；否则 `scripts\\xwl.py` 会被上层的
    "含 `scripts/xwl.py`"过滤整条跳过 ⇒ 判绿）；② **引号包裹必须放行**（`python "<skill根>/scripts/xwl.py"`
    正是文档教人"路径带空格就加引号"时的写法，不放行会假红）。
    """
    _c = cmd.replace("\\", "/")
    if "scripts/xwl.py" not in _c and "scripts/selftest.py" not in _c:
        return False
    return not _ENTRY_OK_RE.search(_c)


def _entry_form_problems(root: str) -> list:
    """入口形态：① `xwl.py` 两处提示的实际打印形态 ② 文档里的 `python …xwl.py` 是否都带路径前缀。"""
    _bad = []
    # ① 静态面：源码里任何 `python [-B] <前缀>scripts/xwl.py` 都必须带前缀（裸形态即旧文案回潮）
    try:
        with io.open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), encoding="utf-8") as _fh:
            _src = _fh.read()
    except OSError as _exc:
        _bad.append("入口形态：读不出 scripts/xwl.py（%s）—— 报错，不算「没命中」" % _exc)
        _src = ""
    for _m in re.finditer(r"python\s+(?:-B\s+)?(\S*?)scripts[/\\]xwl\.py", _src):
        if not _m.group(1):
            _bad.append("入口形态 scripts/xwl.py：提示文案仍写**裸相对路径**（`%s`）—— 调用方 cwd 不是"
                        " skill 根，照抄必然找不到脚本；须走 `cmd_hint()` 打成绝对路径"
                        % _m.group(0).strip()[:70])
    # ⚠️ 计数要**排除 `def cmd_hint(` 那一行**：把 `def` 也算进来时，"def ＋ 1 处调用"就能满足 `< 2`，
    #   另一处退回自拼路径不会红（实测计数 3 = 1 个 def ＋ 2 处调用）。
    _hint_calls = len([_l for _l in _src.splitlines()
                       if "cmd_hint(" in _l and not _l.lstrip().startswith("def ")])
    if _src and _hint_calls < 2:
        _bad.append("入口形态 scripts/xwl.py：`cmd_hint(` 的**调用**只有 %d 处（应为 2）—— 两处提示"
                    "（重名报告 / diffguard 重跑）必须都经它拼入口，别各拼一份" % _hint_calls)
    # ② 运行时面：`cmd_hint()` 打出来的实际形态（绝对路径 ＋ `scripts/xwl.py` 尾段 ＋ 可被 shell 切开）
    for _tail in ("itemids <file> --dups-only", "diffguard <文件>"):
        try:
            _h = xwl.cmd_hint(_tail)
        except AttributeError as _exc:
            _bad.append("入口形态：`xwl.cmd_hint()` 不见了（%s）—— 两处提示改回自拼路径就等于把"
                        "「换 cwd 就粘不上」这个病根带回来" % _exc)
            break
        if "scripts/xwl.py" not in _h:
            _bad.append("入口形态：提示 `%s` 里没有 `scripts/xwl.py` 尾段（入口形态与文档口径脱钩）"
                        % _h[:70])
            continue
        _tok = [t for t in shlex.split(_h) if t.endswith("scripts/xwl.py")]
        if not _tok:
            _bad.append("入口形态：提示 `%s` 切不出脚本路径 —— 引号形态不可粘贴" % _h[:70])
        elif not os.path.isabs(_tok[0]):
            _bad.append("入口形态：提示里的脚本路径不是绝对路径（%s）" % _tok[0])
        elif not os.path.exists(_tok[0]):
            _bad.append("入口形态：提示里的脚本路径在本机不存在（%s）" % _tok[0])
    # ③ 文档面：扫描面 ＝ 文档守卫的扫描面（排除 CHANGELOG）＋ examples/README.md
    _targets = [n for n in _doc_names(root) if n not in _ENTRY_SKIP]
    if "examples/README.md" not in _targets:
        _targets.append("examples/README.md")
    _cnt_all = 0
    for _rel in _targets:
        try:
            with io.open(os.path.join(root, _rel.replace("/", os.sep)), encoding="utf-8") as _fh:
                _ls = _fh.read().splitlines()
        except (OSError, UnicodeDecodeError) as _exc:
            _bad.append("入口形态：读不出 %s（%s: %s）—— 报错，不算「没命中」"
                        % (_rel, type(_exc).__name__, _exc))
            continue
        for _ln, _l in enumerate(_ls):
            for _c in _entry_cmds(_l):
                if "scripts/xwl.py" not in _c and "scripts/selftest.py" not in _c:
                    continue
                _cnt_all += 1
                # 同行 `cd <…> && python …` 的写法放行（cwd 由这一行自己给定，不是"靠环境"）。
                # ⚠️ ⛔ **不做"围栏块里有 cd 行就整块放行"**：那个豁免不校验 cd 目标，块里加一句
                #   `cd /tmp/demo` 就能把整块裸形态放过（仓内就有 `cd /tmp/flatdemo` 这种写法）。
                if re.search(r"\bcd\s+\S+\s*&&", _c):
                    continue
                if _entry_prefix_missing(_c):
                    _bad.append("入口形态 %s:%d `%s` 用了**裸相对路径** —— 调用方 cwd 多半是业务工程，"
                                "须写成 `<skill根>/scripts/xwl.py` 或绝对路径"
                                % (_rel, _ln + 1, _c[:60]))
    # 只有"**全仓一条都抽不到**"才判红：单份文件 0 条是**正常**的（把命令样例下沉到 references/
    #   是预算守卫鼓励的动作，逼每份文件必须有样例会跟它相撞）。
    if not _cnt_all:
        _bad.append("入口形态：全部 %d 份文档里一条 `python …xwl.py` 调用样例都没抽到 ⇒ 本项无法判定，"
                    "判红（抽取面可能已失效：提示符／命令头／反引号形态变了）" % len(_targets))
    return _bad


def _desc_block(fm_text: str) -> str:
    """从 frontmatter 文本里按**行**切出 `description` 折叠块（把缩进行拼起来）。

    ⚠️ 不用正则回溯：若 description 正好是 frontmatter 的**最后一个键**（后面只有 `---`），
       那种「下一行是顶格键」的模式匹配不到 ⇒ 会误报「读不出」。frontmatter 的键一律顶格，
       所以判据就是「往下收到第一个不缩进的非空行」。
    """
    _lines = fm_text.splitlines()
    for _i, _l in enumerate(_lines):
        if _l.strip().startswith("description:"):
            _got: list[str] = []
            for _nxt in _lines[_i + 1:]:
                if not _nxt.strip():
                    continue
                if _nxt[:1] in (" ", "\t"):
                    _got.append(_nxt)
                    continue
                break
            return "\n".join(_got)
    return ""


@_cap
def _docs_contract(_S) -> None:
    """文档契约：该有的句子在，不该有的一句都不能有（命中按**子串出现次数**算）。

    起因：施工单把这几条写成「文档里应有／不应有某句」，但自检里没有对应断言 ——
    把文档改回旧措辞，文档块照样绿，判据只活在纸面上。

    ⚠️ 命中一律用**子串计数**，不用正则判文本：`（）` `*` 这类元字符会把判据带偏。
       只有「从 frontmatter 切出 description 段」那一处用正则 —— 那是**取数**、不是判命中，
       且与既有的 frontmatter 守卫同一个模式（两处口径必须一致）。
    ⚠️ 余量与既有上限是**两条**：那条只管「不超过」，这条管「留出下次可改的空间」。
    """
    docs = _S["docs"]
    root = _S["root"]
    doc_fail = _S["doc_fail"]
    _txt = {k: "\n".join(v) for k, v in docs.items()}
    _bad: list[str] = []

    def _cnt(rel, needle):
        """这句在某个文档里出现了几次（文档没被扫到就是 0，由调用方按「必须有」判红）。"""
        return _txt.get(rel, "").count(needle)

    def _zero(rel, needle, why):
        _c = _cnt(rel, needle)
        if _c:
            _bad.append("%s 不该含「%s」（%s），实际命中 %d 次" % (rel, needle, why, _c))

    def _has(rel, needle, why):
        _c = _cnt(rel, needle)
        if _c < 1:
            _bad.append("%s 必须含「%s」（%s），实际命中 %d 次" % (rel, needle, why, _c))

    # 旧措辞清场：这些句子已被更准确的说法取代，退回旧措辞等于把结论说过头。
    _zero("SKILL.md", "拒绝写盘", "该说法已废，改成「未写入」一类的事实描述")
    _zero("references/faq.md", "框架一定能加载", "解析通过只证「能读」，不证框架一定能加载")
    _zero("references/generation.md", "一定是**外部来源**", "把来源一口咬定成外部，是过强断言")
    _zero("references/generation.md", "str() 只写一遍", "该说法已废，改成按类型分别处理")
    _zero("references/generation.md", "所有键都过它", "该说法已废，不是所有键都走同一条路")

    # 承载句不许被删：这几句都被删过一轮，删了就等于不再向读者交代。
    _has("references/generation.md", "≠ 一定是外部来源", "保留「不能一口咬定外部来源」的边界句式")
    _has("SKILL.md", "diff 只含", "改动范围承诺的承载句")
    _has("README.md", "diff 只含", "diff 最小化的承诺要在 README 也在")
    _has("README.md", "前提：候选", "候选先通过的承载句")
    _has("README.md", "能主动触发的重排", "重排可见的承载句")
    _has("SKILL.md", "node 调用失败", "事件校验失败的归类句")
    _has("SKILL.md", "操作前副本", "回退首选操作前副本")
    _has("SKILL.md", "会丢", "直接回退会丢未提交编辑的提醒")
    _has("references/generation.md", "分类型", "按类型分别处理的方案名")
    _has("references/generation.md", "cfg_str", "按类型处理的助手名")

    # 独占式表述（把能力说成只有本工具能做）本仓已裁定不用 —— 两个面都要清掉。
    # ⚠️ 这个针**拼接**出来：整词直写会把自己算进 selftest.py 的命中里（自命中）。
    _sole = "唯一能" + "主动"
    _zero("SKILL.md", _sole, "独占式表述已被裁定不用")
    _st_path = os.path.join(HERE, "selftest.py")   # 开发树自扫描（运行面无 selftest.py）
    try:
        with open(_st_path, encoding="utf-8", newline="") as _fh:
            _st_src = _fh.read()
    except OSError as _exc:
        _bad.append("scripts/selftest.py 读不出（%s）—— 报错，不算「没命中」" % _exc)
    else:
        _c = _st_src.count(_sole)
        if _c:
            _bad.append("scripts/selftest.py 不该含「%s」（独占式表述已被裁定不用），实际命中 %d 次"
                        % (_sole, _c))

    # frontmatter 两条：不超过上限 ＋ **余量**（余量这半正是本节要补的）。
    _sk = _txt.get("SKILL.md", "")
    _fm = _sk.split("---")[1] if _sk.startswith("---") else ""
    if not _fm:
        _bad.append("SKILL.md 的 frontmatter 读不出（应前后各一个 `---`）")
    elif len(_fm) > 800:
        _bad.append("SKILL.md 的 frontmatter 已 %d 字符，余量不足 100（护栏 900，要求 ≤800）"
                    % len(_fm))

    # description 段：承诺句不许进触发面，边界句与触发段必须在。
    _dsc = _desc_block(_fm)
    # 自测：description 落在 frontmatter **最后一个键**（后面只有 `---`）时也必须取得出来 ——
    #   若用「下一行是顶格键」的正则，这种形态会误报「读不出」。
    _probe_fm = "name: t\nmetadata:\n  category: x\ndescription: >-\n  第一行\n  第二行\n"
    if _desc_block(_probe_fm) != "  第一行\n  第二行":
        _bad.append("description 截段自测失败：末位键取到 %r（应为两行缩进内容）"
                    % (_desc_block(_probe_fm),))
    if not _dsc:
        _bad.append("SKILL.md 的 description 段读不出（应保持 `description: >-` 折叠块）")
    else:
        for _w in ("等价比对", "格式错误在构造上不会发生", "rc=", "diff 只含"):
            _c = _dsc.count(_w)
            if _c:
                _bad.append("SKILL.md 的 description 段不该含「%s」（承诺不进触发面），"
                            "实际命中 %d 次" % (_w, _c))
        if not ("触发场景" in _dsc or "Trigger phrases" in _dsc):
            _bad.append("SKILL.md 的 description 段必须含「触发场景」或「Trigger phrases」"
                        "（不许只剩一句身份），实际命中 0 次")
        if not ("仅适用" in _dsc or "不适用" in _dsc):
            _bad.append("SKILL.md 的 description 段必须含「仅适用」或「不适用」（边界句），"
                        "实际命中 0 次")

    if _bad:
        doc_fail.extend(_bad)
    else:
        print("[ok]  文档契约：该有的句子都在、不该有的一句没有"
              "（含 frontmatter 余量、description 的触发段与边界句）")


# ---- 版本三处机械守卫与仓库根 README 机械守卫（验收缺口的机械收口）----
#   两条臂都**并进** `--only docs` 的既有文档守卫块（⛔ 不新开 `# 17<字母>` 块名：
#   新块名会撞 `_DOC_GUARD_BLOCK_BASE`）；判定文本只在失败时进 `doc_fail`，
#   ⛔ 不新增 `[ok]` 行（避免改动文档守卫大绿行的计数口径）。
#   位置放在函数体外：这两段若塞进 `_docs_numbers_and_tables` 函数体，会把该受管函数推向 400 行上限。
_VER_HEAD_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]\s*-\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)
# 仓库根 README 的过程词闭集（与分发面编年纪律同一组；用**相邻字面量**写，避免本文件被自扫命中）
_README_PROCESS_WORDS = ("此" "前", "原" "先", "早" "先", "旧" "实现", "旧" "判据",
                         "原" "判据", "上" "一轮", "上" "一版", "当" "年", "一" "度")
# 仓库根 README 不得提供的**仓外**链接前缀（这些对象在工作区维护、不随本仓库分发）
_README_OUTSIDE_PREFIXES = ("release/", "plans/", "ledger/", "artifacts/")
_README_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _doc_guard_version_three(root: str, md: dict) -> list:
    """版本三处机械对账：CHANGELOG 首段 ↔ `metadata.version` ↔ `update_history[0]`。

    判据（全部进 `doc_fail`，可读文案）：
      ① `update_history` 必须是非空 list、首条必须是 dict；
      ② `metadata.update_history[0].version == metadata.version`；
      ③ `CHANGELOG.md` 首个 `## [x.y.z] - YYYY-MM-DD` 段的版本 == `metadata.version`；
      ④ 该段日期 == `update_history[0].date`；
      ⑤ 结构异常（无版本段／`update_history` 非 list／首条非 dict／字段缺失或形态不对）逐项报。
    起因（不这么做会漏什么）：只改 CHANGELOG 新段标题版本、或只改 `update_history[0]` 的
    version/date 漂移时 `--only docs` 仍绿 ⇒ 版本三处缺机械臂；本守卫覆盖此面（验收 §2.4/§5-A 的注入面）。
    返回失败文案列表（空 = 通过）。
    """
    fail: list = []
    hist = md.get("update_history")
    if not isinstance(hist, list) or not hist:
        return ["版本三处：metadata.json 的 `update_history` 缺失或不是非空 list"]
    first = hist[0]
    if not isinstance(first, dict):
        return ["版本三处：metadata.json 的 `update_history[0]` 不是对象（{version,date,summary}）"]
    hver, hdate = first.get("version"), first.get("date")
    if not isinstance(hver, str) or not hver:
        fail.append("版本三处：metadata.json 的 `update_history[0].version` 缺失或不是非空字符串")
    if not isinstance(hdate, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", hdate):
        fail.append("版本三处：metadata.json 的 `update_history[0].date` 缺失或不是 YYYY-MM-DD")
    mdver = md.get("version")
    if not isinstance(mdver, str) or not mdver:
        fail.append("版本三处：metadata.json 顶层 `version` 缺失或不是非空字符串")
    elif isinstance(hver, str) and hver and mdver != hver:
        fail.append("版本三处：metadata.version=%r 与 update_history[0].version=%r 不一致"
                    % (mdver, hver))
    try:
        with io.open(os.path.join(root, "CHANGELOG.md"), "r", encoding="utf-8", newline="") as _clf:
            _cl = _clf.read()
    except (OSError, UnicodeDecodeError) as _exc:
        return fail + ["版本三处：读不出 CHANGELOG.md（%s: %s）—— 报错，不算通过"
                       % (type(_exc).__name__, _exc)]
    _m = _VER_HEAD_RE.search(_cl)
    if _m is None:
        return fail + ["版本三处：CHANGELOG.md 里找不到首个 `## [x.y.z] - YYYY-MM-DD` 版本段"]
    _cver, _cdate = _m.group(1), _m.group(2)
    if isinstance(mdver, str) and mdver and _cver != mdver:
        fail.append("版本三处：CHANGELOG 首段版本 %s 与 metadata.version %s 不一致"
                    % (_cver, mdver))
    if isinstance(hdate, str) and hdate and _cdate != hdate:
        fail.append("版本三处：CHANGELOG 首段日期 %s 与 update_history[0].date %s 不一致"
                    % (_cdate, hdate))
    return fail


def _doc_guard_root_readme() -> list:
    """仓库根 `README.md` 机械守卫（它**不在** `_check_docs` 的 `root=SKILL_ROOT` 扫描面）。

    判据（全部进 `doc_fail`，可读文案）：
      ① 文件必须存在；② 全文 `ITEM-\\d{4}` 命中 0；③ 过程词闭集命中 0；
      ④ 文档内 Markdown 相对链接的目标须是本仓库内**存在**的路径（外链不校验）；
      ⑤ 不得有指向仓外 `release/`／`plans/`／`ledger/`／`artifacts/` 的链接。
    起因（不这么做会漏什么）：根 README 只作仓库导航、易被注入计划内部编号或仓外指针，
    且它不在文档守卫扫描面 ⇒ `--only docs` 对该文件无覆盖；本守卫补此面（验收 §2.4-F/§5-C 的缺口）。
    返回失败文案列表（空 = 通过）。
    """
    fail: list = []
    repo = os.path.dirname(os.path.abspath(SKILL_ROOT))
    path = os.path.join(repo, "README.md")
    if not os.path.isfile(path):
        return ["仓库根 README：缺少 %s（技能开发仓库的导航入口）" % path]
    try:
        with io.open(path, "r", encoding="utf-8", newline="") as _rf:
            text = _rf.read()
    except (OSError, UnicodeDecodeError) as _exc:
        return ["仓库根 README：读不出（%s: %s）—— 报错，不算通过"
                % (type(_exc).__name__, _exc)]
    for _i, _l in enumerate(text.splitlines(), 1):
        if re.search(r"ITEM-\d{4}", _l):
            fail.append("仓库根 README:%d 出现计划内部编号 ITEM-XXXX：%s"
                        % (_i, _l.strip()[:60]))
        for _w in _README_PROCESS_WORDS:
            if _w in _l:
                fail.append("仓库根 README:%d 出现过程词「%s」：%s"
                            % (_i, _w, _l.strip()[:60]))
    for _m in _README_LINK_RE.finditer(text):
        _tgt = _m.group(1).strip()
        if _tgt.startswith("<") and _tgt.endswith(">"):
            _tgt = _tgt[1:-1]
        if _tgt.startswith(("http://", "https://", "mailto:", "#")):
            continue
        _path = _tgt.split("#", 1)[0]
        if not _path:
            continue
        while _path.startswith("./"):
            _path = _path[2:]
        if any(_path.startswith(_bad) for _bad in _README_OUTSIDE_PREFIXES):
            fail.append("仓库根 README：链接指向仓外对象（不随本仓库分发）：%s" % _tgt)
            continue
        try:
            _abs = os.path.abspath(os.path.join(repo, _path))
            _inside = os.path.commonpath([_abs, repo]) == repo
        except (OSError, ValueError):
            _inside = False
        if not _inside:
            fail.append("仓库根 README：链接越出仓库根：%s" % _tgt)
        elif not os.path.exists(_abs):
            fail.append("仓库根 README：链接目标不存在：%s" % _tgt)
    return fail


def _read_doc_chars(root, rel):
    """读文档字符数（＝ `wc -m` 口径）：返回 `(chars, None)`；读不出 `(None, exc)`。

    B1 迁入：`17j-4` 篇幅上限的读字符数助手（原 inline 于 `_docs_layers_and_distribution`），
    现作为 `contract_scanner.guard_length_caps` 的注入依赖。
    """
    try:
        return len(io.open(os.path.join(root, rel), encoding="utf-8", newline="").read()), None
    except (OSError, UnicodeDecodeError) as _exc:   # UnicodeDecodeError 是 ValueError 子类 ⇒ 必须并列
        return None, _exc


def _load_contract_scanner():
    """按需加载 `skill/tests/contract_scanner.py`（与 `_contract_scan_fails` 同路径；失败 ⇒ `None`）。

    B1 迁入：17b/17l/17r/17j-4 的判定逻辑已物理迁入该模块，本文件的对应段函数改为调用其函数。
    模块级缓存到 `sys.modules`；加载失败返回 `None`，调用方**判红**（不算通过），与 M3 接入门一致。
    """
    name = "xwl_contract_scanner"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    tests_dir = os.path.join(os.path.dirname(HERE), "tests")
    path = os.path.join(tests_dir, "contract_scanner.py")
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(name, path)
        mod = _ilu.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001
        return None


def _contract_scan_fails(repo_root):
    """M3 契约扫描/校验接入门禁（§7 / B2）：把「未绑定 / 漂移 / 待登记 + 4.7 十六条」并入判定。

    起因（B2）：独立脚本 `contract_scanner.py` / `contract_validator.py` 此前只报告不判红，
    `--require-all --profile package` 的 rc 因此不反映契约判定。本函数把两者并入 docs 块的
    `doc_fail`（进而进 rc）：任一违规即红。

    面与门控：
      - 仅当 `<repo>/skill/contracts/registry.json` 存在时执行（契约登记表不进分发包 ⇒
        隔离安装/分发解包时无此文件，属**不适用**，走 `_gate_note`，不判红）。
      - `repo_root` = `SKILL_ROOT` 的父级（扫描器/校验器按工作区根取 `skill/…`、`ledger/…`）。
    """
    reg_rel = "skill/contracts/registry.json"
    reg_path = os.path.join(repo_root, reg_rel.replace("/", os.sep))
    if not os.path.isfile(reg_path):
        _gate_note("契约扫描：无 skill/contracts/registry.json（非工作区/分发面）—— 本项不适用")
        return []
    import importlib.util as _ilu
    out = []

    def _load_mod(name, path):
        mod = sys.modules.get(name)
        if mod is None:
            spec = _ilu.spec_from_file_location(name, path)
            mod = _ilu.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        return mod

    tests_dir = os.path.join(os.path.dirname(HERE), "tests")
    try:
        cs = _load_mod("xwl_contract_scanner", os.path.join(tests_dir, "contract_scanner.py"))
        for x in cs.check_scan(repo_root, cs._load_registry(repo_root)):
            out.append("契约扫描：" + x)
    except Exception as _exc:  # noqa
        out.append("契约扫描跑不起来（%s: %s）—— 报错，不算通过" % (type(_exc).__name__, _exc))
    try:
        cv = _load_mod("xwl_contract_validator", os.path.join(tests_dir, "contract_validator.py"))
        res, _ = cv.run_all(repo_root)
        for jid, vs, st in res:
            if st == "SKIP":
                continue  # 域不适用（如 skill-only 树缺 workspace 数据）⇒ 不判红
            for x in vs:
                out.append("契约校验[%s]：%s" % (jid, x))
    except Exception as _exc:  # noqa
        out.append("契约校验跑不起来（%s: %s）—— 报错，不算通过" % (type(_exc).__name__, _exc))
    return out


@_cap
def _check_docs(tmp, node, failures, write) -> None:
    """文档一致性守卫（跨文件）：重复表格 / 引用可解析 / 格式 / 自称数字 / 索引与节号（第 17~18 组）"""
    # 薄编排器：只建共享状态并依次调四段（⛔ 别往这里加判据 —— 加了就没有行数上限保护了）。
    # 形参原样搬进 `_S`：四段的文本一字未改，仍按原名字取用。
    # ⚠️ 可选键**一律在这里给类型正确的初值**：四段的白名单里混着循环变量与条件赋值
    #    （`_hit` / `_miss` / `_probe` 等只在某个循环 / 某条分支里赋值），那段没跑到时它们
    #    **根本不在 `locals()` 里** ⇒ 后一段从 `_S` 取 `_hit` 时直接 `KeyError`、崩在报红之前
    #    （实测：无 `.git` 走 `--allow-nogit` 降级 ⇒ 编年臂不跑 ⇒ `KeyError: '_hit'`）。
    #    默认值口径 = 「没有这一项」的正常路径：计数 `0` / 文本 `""` / 集合 `set()` /
    #    正则与文件对象 `None` / 容器 `{}` `[]`。**⛔ 别改成 `None` 一把梭**（`_i - 1`、`len()`、
    #    `in` 都会当场炸）；也**⛔ 别删这些键**（删了＝缺席又回来了）。
    _S = {"tmp": tmp, "node": node, "failures": failures, "write": write,
          "_base": {}, "_body": "", "_chk_m": None, "_fence": False, "_fh": None,
          "_fm": None, "_got": None, "_hit": "", "_i": 0, "_j": 0, "_l": "", "_lab": "",
          "_listed": set(), "_ln": 0, "_m": None, "_md": {}, "_miss": [], "_n": 0,
          "_nm": "", "_nogit_arms": [], "_on_disk": set(), "_on_disk_ok": False,
          "_probe": "", "_r": "", "_rel": "", "_rm_txt": "", "_sk_txt": "", "_txt": {},
          "i": 0, "l": "", "ls": [], "nm": ""}
    _docs_xfile_consistency(_S)
    _docs_numbers_and_tables(_S)
    _docs_layers_and_distribution(_S)
    # 契约段必须在尾段**之前**：尾段把 `doc_fail` 并进 `failures`，之后再追加就落不到 rc 上。
    _docs_contract(_S)
    # M3 契约扫描/校验接入（B2）：未绑定/漂移/待登记 + 4.7 十六条并入 doc_fail ⇒ 进 rc。
    # repo_root = SKILL_ROOT 的上两级（SKILL_ROOT=<repo>/webbuilder-xwl-patch）。分发面无
    # skill/contracts 时 _contract_scan_fails 走 _gate_note 不适用。
    _S["doc_fail"].extend(_contract_scan_fails(os.path.dirname(os.path.dirname(SKILL_ROOT))))
    _docs_tail_scaffold(_S)


@_cap
def _docs_xfile_consistency(_S) -> None:
    """`_check_docs` 的第 1 段（机械切分，判据文本逐字未改）。

    段内通过 `_S` 共享状态：**读**的先取、**写**的末了写回 —— 拆函数不改变语义，
    也不改变任何一条判据的文本（只多了一层状态搬运）。
    """

    # ---- 17. 文档一致性守卫（跨文件）----
    # 这几类缺陷人眼复核必漏（实测：一轮评审发现的 4 个缺陷里 3 个是"改了这处忘了那处"），所以机械扫。
    doc_fail: list[str] = []
    root = SKILL_ROOT
    # 扫描面清单已**移出函数体**（#15 有界下沉）⇒ 见模块级常量 `doc_names`（本文件 `_check_docs` 之前）。
    docs: dict = {}
    for nm in doc_names:
        fp = os.path.join(root, nm.replace("/", os.sep))
        # 读不出必须**报红**、不算「没命中」：`PermissionError` 非 `FileNotFoundError`，非 UTF-8 ⇒ `UnicodeDecodeError`（`ValueError` 子类、非 `OSError`）。
        try:
            with open(fp, "r", encoding="utf-8", newline="") as fh:
                docs[nm] = fh.read().splitlines()
        except (OSError, UnicodeDecodeError) as _exc:
            doc_fail.append("文档守卫：读不出 %s（%s: %s）—— 报错，不算「没命中」"
                            % (nm, type(_exc).__name__, _exc))

    # 17a emoji 不得进标题
    # 起因：**样式一致性** —— 标题一律纯文本（emoji 只进正文 blockquote）；**非正确性缺陷**。
    #   本仓**无出处**（守卫清账裁定「保留、标无出处」），且**不做迁移** ⇒ 保留机械守卫。
    #   ⚠️ 2026-10-19 复核：接替方（工作区 `doc_lint.py`）**尚无**「标题禁 emoji」规则
    #     （`grep emoji` 命中 0）⇒ 在它落地之前**不得撤本块**，否则该约束完全无守卫。
    for nm, ls in docs.items():
        for i, l in enumerate(ls, 1):
            if l.startswith("#") and any(ch in l for ch in ("⚠", "❗", "✅", "❌")):
                doc_fail.append("%s:%d 标题里混入 emoji" % (nm, i))

    # 17b **任意两份文档**之间不得有逐字重复的表格行（同一张表不该在两处各写一遍）。
    #     原来只比 README↔SKILL —— 实测 SKILL↔faq 也会重复（退出码表就是这么漏掉的）。
    #     起因：只比 README↔SKILL 会漏掉其余文档对之间的重复（退出码表就因 SKILL↔faq 重复而漏检）—— 不扩到任意两文档，同一张表两处各写一遍发现不了。
    # B1 迁入：判定逻辑已迁入 `contract_scanner.guard_dup_table_rows`（`_trows` 由本文件注入保单一真源）。
    _cs_17b = _load_contract_scanner()
    if _cs_17b is None:
        doc_fail.append("17b 表格重复守卫跑不起来：contract_scanner 加载失败 —— 报错，不算通过")
    else:
        doc_fail.extend(_cs_17b.guard_dup_table_rows(docs, trows=_trows))

    # 17c 「§N.M」/「见 N.M」引用必须可解析 —— **本文件与跨文件都查**。
    #     原来含 `.md` 的行整行跳过 ⇒ 跨文件引用无人管：把 §五/§四 外移时漏掉两处
    #     （SKILL.md 还指向语义已变的小节、measured-data 指向已搬走的 §5.6）。
    #     判定：以该引用**左侧最近的文档名**为归属；没有则归属本文件。
    #     起因：含 `.md` 的行若整行跳过，跨文件引用就没人管 —— 外移章节后 SKILL.md 指向语义已变的小节、measured-data 指向已搬走的小节，都发现不了。
    _heads = {k: "\n".join(l for l in v if l.startswith("#")) for k, v in docs.items()}
    _base = {k: k.split("/")[-1] for k in docs}
    for nm, ls in docs.items():
        # CHANGELOG 是**历史记录**：里面的 `§5.5`→`§5.6` 是**写入时**的编号，不按当前结构校验
        # （否则每次重排章节都得回头改历史，而历史本来就该原样留着）。
        if nm == "CHANGELOG.md":
            continue
        for i, l in enumerate(ls, 1):
            for m in re.finditer(r"§(\d)\.(\d)|见\s*\*{0,2}(\d)\.(\d)", l):
                g = m.groups()
                a, b = (g[0], g[1]) if g[0] else (g[2], g[3])
                tgt = nm
                near = list(_fn.finditer(l[: m.start()]))
                if near:
                    cand = [k for k, v in _base.items() if v == near[-1].group(1)]
                    if cand:
                        tgt = cand[0]
                if ("### %s.%s" % (a, b)) not in _heads.get(tgt, ""):
                    doc_fail.append("%s:%d 引用 %s §%s.%s，但该文件没有这个编号小节"
                                    % (nm, i, _base.get(tgt, tgt), a, b))

    # 17c-2 「第 N 章」「第 N 步」也要能解析 —— 原来完全没查这一类引用。
    #     只在**能确定归属 SKILL.md** 时判：本文件是 SKILL，或该行里出现了 SKILL.md。
    #     references 里不带文档名的「第 N 步」多指该文件自己的步骤（如 walkthrough 的教程步骤），不判。
    #     起因：完全不查「第 N 章」「第 N 步」这类引用时，章/步被改名或搬走后就成了死指针、无人发现。
    _sk_lab = set()
    for _l in docs.get("SKILL.md", []):
        _m = re.match(r"^##\s*([" + _cn + r"]+)、", _l)
        if _m:
            _sk_lab.add(_m.group(1))
        _m = re.match(r"^###\s*第\s*(\d)\s*步", _l)
        if _m:
            _sk_lab.add("第" + _m.group(1) + "步")
    for nm, ls in docs.items():
        if nm == "CHANGELOG.md":
            continue
        for i, l in enumerate(ls, 1):
            if nm != "SKILL.md" and "SKILL.md" not in l:
                continue
            for _m in re.finditer(r"第\s*([" + _cn + r"]+)\s*章", l):
                if _m.group(1) not in _sk_lab:
                    doc_fail.append("%s:%d 引用「第%s章」但 SKILL.md 没有该章" % (nm, i, _m.group(1)))
            for _m in re.finditer(r"第\s*(\d)\s*步", l):
                if ("第" + _m.group(1) + "步") not in _sk_lab:
                    doc_fail.append("%s:%d 引用「第%s步」但 SKILL.md 没有该步" % (nm, i, _m.group(1)))

    # 17d 去项目化：文档与工具里不得出现任何具体工程的路径（skill 是通用资产）
    # 判据用**结构**而不是业务名黑名单 —— 后者等于把业务名又写进代码里。
    #   · `m?xwl=` 后面必须是占位符（`<…>` / `…`），只有框架端点 `common/` 例外；
    #   · 出现的 `.xwl` 路径若是**多段**且不含占位符标记、又不属于平台自带目录，即视为真实业务路径。
    #     起因：skill 是通用资产 —— 文档或工具里一旦写进具体工程路径／本机盘符路径，就等于绑定某个环境，别人照抄即错。
    # 有界下沉：正则组（`mref` / `paths` / `ok_head` / `generic` / `rx_env` / `skip_env` / `marks`）已移出函数体 ⇒ 见模块级同名常量。
    for nm, ls in docs.items():
        for i, l in enumerate(ls, 1):
            for m in mref.finditer(l):
                g = m.group(1)
                if not (g.startswith("common/") or g.lower().startswith("xxx")):
                    doc_fail.append("%s:%d `m?xwl=%s` 不是占位符（换成 <模块>/… 写法）"
                                    % (nm, i, g[:40]))
            if not skip_env.search(l):
                for _m in rx_env.finditer(l):
                    doc_fail.append("%s:%d 出现**本机路径** `%s`（环境信息，换成通用描述）"
                                    % (nm, i, _m.group(0)))
            if marks.search(l):     # 该行已用占位符 / 示意名写法，路径无须再查
                continue
            for m in paths.finditer(l):
                s = m.group(0)
                if "/" in s:
                    if not ok_head.match(s.split("/")[0]):
                        doc_fail.append("%s:%d 出现业务路径 `%s`"
                                        "（首段应是 `dev` / `examples` / `common` / `…` / `<…>` / `xxx` 这类通用段）"
                                        % (nm, i, s))
                elif not generic.match(s):
                    doc_fail.append("%s:%d 出现单段 `.xwl` 名 `%s`（不是通用示例名）" % (nm, i, s))
    with open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "r", encoding="utf-8") as fh:
        for i, l in enumerate(fh.read().splitlines(), 1):
            for m in mref.finditer(l):
                g = m.group(1)
                if not (g.startswith("common/") or g.lower().startswith("xxx")):
                    doc_fail.append("scripts/xwl.py:%d `m?xwl=%s` 不是占位符" % (i, g[:40]))
            if not skip_env.search(l):
                for _m in rx_env.finditer(l):
                    doc_fail.append("scripts/xwl.py:%d 出现**本机路径** `%s`"
                                    "（环境信息，换成通用描述）" % (i, _m.group(0)))
            if marks.search(l):
                continue
            for m in paths.finditer(l):
                s = m.group(0)
                if "/" in s and not ok_head.match(s.split("/")[0]):
                    doc_fail.append("scripts/xwl.py:%d 出现业务路径 `%s`" % (i, s))

    # 17e 文档里指向本地文件的 Markdown 链接必须真的存在
    # 起因：把 FAQ / 自检清单外移到 references/ 时，最容易出现的就是"SKILL.md 指了、
    # 文件却没建 / 后来改名字了"—— 这类断链人眼扫不出来，机械查一下。
    for nm, ls in docs.items():
        base = os.path.dirname(os.path.join(root, nm.replace("/", os.sep)))
        for i, l in enumerate(ls, 1):
            for m in link.finditer(l):
                tgt = os.path.normpath(os.path.join(base, m.group(1)))
                if not os.path.exists(tgt):
                    doc_fail.append("%s:%d 链接指向不存在的文件 -> %s" % (nm, i, m.group(1)))

    # 17f SKILL.md 必须给出「反模式」的入口
    # 起因：SkillHub 评测的 antiPatternFaq 只给 4.5，理由是"反模式内容散在各章、缺少集中章节"。
    # 内容搬到独立文件后，若主文档没有入口 = 等于没搬，所以钉住。
    if "SKILL.md" in docs:
        if not any("anti-patterns.md" in l for l in docs["SKILL.md"]):
            doc_fail.append("SKILL.md 没有指向 references/anti-patterns.md 的入口")

    # 17g **外移点两侧都还在**：主文档留了指针 + 目标文件有承载内容。
    # 起因：把 §五 5.4 / §四 4.1 / §二 2.4 / §七 7.1 的正文搬进 references 后，
    # 任何一侧后来被删或改名，都会变成「主文档说去哪看、去了却没有」—— 这类失义机器可查。
    # ⚠️ 表体已**移出函数体**（#15 有界下沉），**后又拆成两张表**（本文件 `_check_docs` 之前）：
    #    `_SPLIT_POINTERS`（指针表）管「主文档该锚点小节里有指向目标文件的指针」，
    #    `_SPLIT_CARRIERS`（承载词表）管「目标文件里这些词还在」。两张表各管一件，互不牵连
    #    （原 `_splits` 一表同时管两件事，主文档一改结构就一起碎）。
    # 断言①-机理（为什么把「全文 contains」收成「锚点小节区间 contains」）：`_dst` **恒**出现在
    #   `SKILL.md` 开头「怎么用」那张参考材料索引表里 ⇒ 只看「全文 contains」时这条臂**恒真**
    #   （等于没有）；收成「锚点小节的区间内 contains」后，才真能发现"该外移点处的局部指针被删"。
    # 残留盲区（**如实**）：区间 contains 仍**只**证明「该文件名出现在该小节」，
    #   **不**证明"该处就是那条指针"（区间内可能恰有别的 `references/` 引用）；
    #   要精确到"指针句"须逐条记句文本 ⇒ 会与措辞漂移持续摩擦，故不做。
    # 删掉它的代价：退回「全文 contains」⇒ 任一局部指针被删也**不红**，
    #   真正还在守的只剩 ②（承载词那半），而 ② 只证"词还在"、不证"语义还在"。
    # 有界下沉：`_region_after_anchor`（纯助手）已移出函数体 ⇒ 见模块级同名函数。
    # 锚点是**去编号的语义关键词**，按「标题包含关键词」匹配（见 `_region_after_anchor`）；
    # 截断仍用命中标题自身的层号。表里记的层号 `_lvl_noted` 必须与命中标题的 `#` 个数一致，
    # 不一致就判红（防锚点关键词命中了错误层级的标题而无人察觉）。

    for _lab, _src, _dst, _anchor, _lvl_noted in _SPLIT_POINTERS:
        _src_lines = docs.get(_src, [])
        _src_mask = _fence_mask(_src_lines)
        _n_hits = sum(
            1 for _k, _l in enumerate(_src_lines)
            if not _src_mask[_k]
            and (_hm := re.match(r"^(#{1,6}) (.*)$", _l))
            and _anchor in _hm.group(2))
        _region, _hit_lvl = _region_after_anchor(_src_lines, _anchor, _lvl_noted)
        if _n_hits > 1:
            doc_fail.append(
                "外移点「%s」：锚点「%s」在 %s 里同层命中 %d 次 —— 唯一性被打破，层号判红兜不住"
                % (_lab, _anchor, _src, _n_hits))
        elif _region is None:
            doc_fail.append(
                "外移点「%s」：锚点「%s」在 %s 里找不到 —— 这是**锚点问题**（锚点行被改或删），不是缺指针"
                % (_lab, _anchor, _src))
        else:
            if _lvl_noted != _hit_lvl:
                doc_fail.append(
                    "外移点「%s」：锚点「%s」记的层号是 %d，命中标题实际是 %d 个 #"
                    % (_lab, _anchor, _lvl_noted, _hit_lvl))
            if _dst not in "\n".join(_region):
                doc_fail.append(
                    "外移点「%s」：%s 的锚点小节「%s」区间内没有指向 %s 的指针"
                    % (_lab, _src, _anchor, _dst))
    for _lab, _dst, _keys in _SPLIT_CARRIERS:
        _body = "\n".join(docs.get(_dst, []))
        _miss = [k for k in _keys if k not in _body]
        if _miss:
            doc_fail.append("外移点「%s」：%s 里找不到承载内容 %s" % (_lab, _dst, _miss))

    # 17h 文档格式：表格列数一致 / 标题不跳级 / 代码块闭合 / 无行尾空白 / 末尾有换行。
    #     起因：外移与重排章节时最容易留下这五类瑕疵，而且人眼扫不出来。
    #     ⚠️ 本号另有一处（管 test-prompts 覆盖率：每个子命令至少被一条 prompt 提到）—— 见本文件 `_uncovered` 那段（grep `_uncovered`）。
    for nm, _lines in docs.items():
        _cur = None
        _fence = 0
        _prev = 0
        for i, l in enumerate(_lines, 1):
            s = l.strip()
            if s.startswith("```"):
                _fence += 1
            if s.startswith("|") and s.endswith("|"):
                _body = s.replace("\\|", "\x00")
                _nc = _body.count("|") - 1
                if set(_body) <= set("|-: "):
                    _cur = _nc
                elif _cur is not None and _nc != _cur:
                    doc_fail.append("%s:%d 表格本行 %d 格、表头 %d 格（表格会渲染错）" % (nm, i, _nc, _cur))
            else:
                _cur = None
            if _fence % 2 == 0 and re.match(r"^#{1,6} ", l):
                _lv = len(l) - len(l.lstrip("#"))
                if _prev and _lv > _prev + 1:
                    doc_fail.append("%s:%d 标题跳级（%s→%s）" % (nm, i, "#" * _prev, "#" * _lv))
                _prev = _lv
            if l != l.rstrip():
                doc_fail.append("%s:%d 行尾有多余空白" % (nm, i))
        if _fence % 2:
            doc_fail.append("%s 代码块未闭合（``` 出现 %d 次）" % (nm, _fence))
        with open(os.path.join(root, nm.replace("/", os.sep)), "rb") as _fh:
            if not _fh.read().endswith(b"\n"):
                doc_fail.append("%s 末尾没有换行" % nm)

    # 17i 文档自称的数字必须与实际一致 —— 外移/增删内容后最容易过期的一类。
    #     只按**具体句式**精确核对，不用「N 条」这类粗匹配（那会把反模式条数套到清单上）。
    #     ⚠️ 本号另有一处（管 metadata.json 打包元数据一致性）—— 见本文件 `_mdp` 那段（grep `_mdp`）。
    #     起因：外移或增删内容后，自称数字（FAQ／清单／反模式／prompt 条数）最容易过期，读者会照错数走。
    import json as _json
    _txt = {k: "\n".join(v) for k, v in docs.items()}
    _real = {
        "faq": len(re.findall(r"^\*\*Q：", _txt.get("references/faq.md", ""), re.M)),
        "ck": len(re.findall(r"- \[ \]", _txt.get("references/checklist.md", ""))),
        "ap": len(re.findall(r"^### ", _txt.get("references/anti-patterns.md", ""), re.M)),
    }
    with open(os.path.join(root, "test-prompts.json"), "r", encoding="utf-8") as _fh:
        _real["tp"] = len(_json.loads(_fh.read()))
    _sk_txt = _txt.get("SKILL.md", "")
    _rm_txt = _txt.get("README.md", "")
    _claims = []
    for _m in re.finditer(r"\*\*(\d+)\s*条\*\*高频问题", _sk_txt):
        _claims.append(("SKILL §八 FAQ 条数", int(_m.group(1)), _real["faq"]))
    for _m in re.finditer(r"faq\.md\s+#\s*(\d+)\s*条", _rm_txt):
        _claims.append(("README 的 FAQ 条数", int(_m.group(1)), _real["faq"]))
    # faq.md 自身的「**N 条按四组归类**」声明（本文件第 5 行）—— 起因：`faq.md` 首段的
    # 归类总数曾写「24 条」而正文实计 25 条，旧 17i 只核 SKILL「**25 条**高频问题」与
    # README「faq.md # N 条」（README 该句常缺=惰性），**faq.md 自身这句无守卫** ⇒ 陈旧数不红。
    # 行首锚 `(?m)^`：只认行首独立成句的声明，行内夹带的「见 **30 条按四组归类** 说明」不计入
    # （否则负例(ii) 无法自洽）。实计侧见 `_real["faq"]`（`^\*\*Q：` 计数）。
    for _m in re.finditer(r"(?m)^\*\*(\d+)\s*条按四组归类\*\*",
                          _txt.get("references/faq.md", "")):
        _claims.append(("FAQ 首段「按四组归类」条数", int(_m.group(1)), _real["faq"]))
    for _m in re.finditer(r"\*\*(\d+)\s*项\*\*清单", _sk_txt):
        _claims.append(("SKILL §九 清单项数", int(_m.group(1)), _real["ck"]))
    for _m in re.finditer(r"checklist\.md\s+#\s*(\d+)\s*项", _rm_txt):
        _claims.append(("README 的清单项数", int(_m.group(1)), _real["ck"]))
    for _m in re.finditer(r"anti-patterns\.md\s+#\s*(\d+)\s*条", _rm_txt):
        _claims.append(("README 的反模式条数", int(_m.group(1)), _real["ap"]))
    for _m in re.finditer(r"test-prompts\.json\s+#\s*(\d+)\s*条", _rm_txt):
        _claims.append(("README 的 prompt 条数", int(_m.group(1)), _real["tp"]))
    # 参考清单里的「清单项数」也要查 —— 正文与参考清单两处会各自漂移
    # （实测漂移一例：正文 §九 改成 30 项，同一文件的参考清单那行还写着 29 项）。
    for _m in re.finditer(r"改完自检清单\*\*：(\d+) 项", _sk_txt):
        _claims.append(("SKILL 参考清单的清单项数", int(_m.group(1)), _real["ck"]))
    for _lab, _got, _exp in _claims:
        if _got != _exp:
            doc_fail.append("自称数字不符：%s 写 %d，实际 %d" % (_lab, _got, _exp))
    # ★ 第 5 类 claim：`check` 的**判定项数**（代码里的判定集合 ↔ 文档里「N 项」的说法）。
    #   起源（不这么做会漏什么）：⑩ 落地时判定项从 8 变 9，文档里 12 处「九项」全靠人工同步 ——
    #     漏一处就是"文档说九项、代码只有八项"，而三种评审法都只看单边、看不出来。
    #   ⛔ **逐句式登记**，不是"整个文件只要有这个词就算"：下面每条形态都写清要匹配的句子，
    #     且**逐处 occurrence 必须被某条形态覆盖**（未被覆盖的 occurrence ⇒ 判红，逼登记）。
    #   数值侧**从代码取**（`checks = {…}` 的集合长度），⛔ 不在这里写死 9。
    with open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "r", encoding="utf-8") as _fh:
        _chk_m = re.search(r"checks = \{([0-9,\s]+)\}", _fh.read())
    # 入口形态（工具两处提示 ＋ 三份文档的调用形态）：见模块级 `_entry_form_problems` 的注释。
    doc_fail.extend(_entry_form_problems(root))
    _S.update({_n: _v for _n, _v in locals().items()
                   if _n in ('_base', '_body', '_chk_m', '_fence', '_fh', '_got', '_i', '_j', '_l', '_lab', '_m', '_miss', '_rm_txt', '_sk_txt', '_txt', 'doc_fail', 'docs', 'i', 'l', 'ls', 'nm', 'root')})


# ---- 历史文档「空代码 span 残骸」守卫（DIST-HIST-SPAN：围栏感知、白名单内容锚定）----
# 白名单（内容锚定，不按行号）：双反引号 delimiter 的 `content.strip()` 逐字属于以下四者才保留 ——
#   `:N` / `L`+数字 / | `cmd args` / | `cmd`。残骸 run 数 = 围栏外 run=2 总数 − 白名单 run 数。
_HIST_LEGAL_CONTENT_RE = (
    re.compile(r"^`:[^`]+`$"),
    re.compile(r"^`L`\+\S+$"),
    re.compile(r"^\| `[^`]+`$"),
)
# 自校验：白名单命中数（合法 span 会随版本段新增 ⇒ 新增时必须同步这里；不一致即判红提醒重算）
_HIST_LEGAL_RUNS = {"CHANGELOG": 8, "metadata": 0}
_HIST_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _hist_span_scan(text):
    """围栏外扫描：返回 `(run2_total, legal_runs, residue_samples)`；残骸 run 数 = 总数 − legal。"""
    total = legal = 0
    samples: list = []
    fence = 0
    for no, line in enumerate(text.splitlines(), 1):
        if _HIST_FENCE_RE.match(line):
            fence += 1
            continue
        if fence % 2 == 1:
            continue
        rs = [(m.start(), m.end() - m.start()) for m in re.finditer(r"`+", line)]
        i = 0
        while i < len(rs):
            s, ln = rs[i]
            if ln != 2:
                i += 1
                continue
            j = i + 1
            while j < len(rs) and rs[j][1] != 2:
                j += 1
            if j >= len(rs):
                total += 1
                samples.append((no, line.strip()[:80]))
                i += 1
                continue
            content = line[s + 2:rs[j][0]].strip()
            total += 2
            if any(rx.match(content) for rx in _HIST_LEGAL_CONTENT_RE):
                legal += 2
            else:
                samples.append((no, content[:40]))
            i = j + 1
    return total, legal, samples


def _doc_guard_hist_span_residue(root: str) -> list:
    """DIST-HIST-SPAN：历史面全文（`CHANGELOG.md` ＋ 归档冻结件 `CHANGELOG-archive.md`）
    ＋ `metadata.update_history[*].summary` 的围栏感知残骸检查。

    只看**围栏外**、反引号 run 长度恰为 2 的 run；白名单见上（内容锚定）。
    **legal 计数按件从内容派生**（根治方案 §6：废硬编码 8）——活层窗口外旧段迁入归档件后，
    两个文件的合法 span 分布会变，写死单文件的常量必误报；判据只看「残骸 run 数＝总数−合法数＝0」，
    不再与固定常量比对（残骸数才是判定语义）。缺 CHANGELOG.md 判红；归档件不存在时按「无旧段」跳过。
    """
    problems: list = []
    # 历史面按件：CHANGELOG.md 必在；CHANGELOG-archive.md 为归档冻结件（活层窗口外的旧版本段）。
    hist_files = [("CHANGELOG.md", True), ("CHANGELOG-archive.md", False)]
    for _rel, _required in hist_files:
        _p = os.path.join(root, _rel)
        if not os.path.exists(_p):
            if _required:
                problems.append("DIST-HIST-SPAN：%s 读不出（文件不存在）" % _rel)
            continue
        try:
            with open(_p, encoding="utf-8", newline="") as f:
                _txt = f.read()
        except OSError as exc:
            problems.append("DIST-HIST-SPAN：%s 读不出（%s）" % (_rel, exc))
            continue
        total, legal, samples = _hist_span_scan(_txt)
        # legal 按件从内容派生（不再与硬编码常量比对）；判据＝残骸 run 数为 0。
        if total - legal:
            problems.append(
                "DIST-HIST-SPAN：%s 有 %d 个空代码 span 残骸 run（围栏外 run=2 总数 %d − "
                "白名单 %d）；行例：%r" % (_rel, total - legal, total, legal, samples[:3]))
    md_path = os.path.join(root, "metadata.json")
    try:
        with open(md_path, encoding="utf-8-sig") as f:
            md = json.load(f)
    except (OSError, ValueError) as exc:
        return problems + ["DIST-HIST-SPAN：metadata.json 读不出/解析失败（%s）" % exc]
    mtotal = mlegal = 0
    msamp: list = []
    for h in md.get("update_history", []):
        sm = h.get("summary", "")
        if not isinstance(sm, str):
            continue
        t, lg, sp = _hist_span_scan(sm)
        mtotal += t
        mlegal += lg
        msamp += [("summary.version=%s" % h.get("version"), c[1]) for c in sp[:2]]
    if mtotal - mlegal:
        problems.append(
            "DIST-HIST-SPAN：metadata.update_history[*].summary 有 %d 个空代码 span 残骸 run；例：%r"
            % (mtotal - mlegal, msamp[:3]))
    return problems


@_cap
def _docs_numbers_and_tables(_S) -> None:
    """`_check_docs` 的第 2 段（机械切分，判据文本逐字未改）。

    段内通过 `_S` 共享状态：**读**的先取、**写**的末了写回 —— 拆函数不改变语义，
    也不改变任何一条判据的文本（只多了一层状态搬运）。
    """
    # ⚠️ 跨段键一律 `.get(默认)`（双保险：即便将来有人新增一段却忘了在 `_S` 里初始化，也不崩）。
    #    必填键（建 `_S` 时就给的 `doc_fail` / `docs` / `root`）仍**硬取** —— 它们缺席是调用方坏了，
    #    应当当场炸，不是静默用默认值。默认值口径见 `_check_docs` 建 `_S` 处的注释。
    _base = _S.get("_base", {})
    _body = _S.get("_body", "")
    _chk_m = _S.get("_chk_m", None)
    _fence = _S.get("_fence", False)
    _fh = _S.get("_fh", None)
    _i = _S.get("_i", 0)
    _j = _S.get("_j", 0)
    _l = _S.get("_l", "")
    _lab = _S.get("_lab", "")
    _m = _S.get("_m", None)
    _sk_txt = _S.get("_sk_txt", "")
    _txt = _S.get("_txt", {})
    doc_fail = _S["doc_fail"]
    docs = _S["docs"]
    i = _S.get("i", 0)
    l = _S.get("l", "")
    ls = _S.get("ls", [])
    nm = _S.get("nm", "")
    root = _S["root"]
    if not _chk_m:
        doc_fail.append("自称数字不符：取不到 `checks = {…}` ⇒ 无法核对「N 项」这类说法")
    else:
        _chk_n = len([_x for _x in _chk_m.group(1).replace(" ", "").split(",") if _x])
        _CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八",
               9: "九", 10: "十"}
        _num = _CN.get(_chk_n, str(_chk_n))
        # ⚠️ 形态表：`%s` 处填**由代码算出的中文数字**。改动文档句式时**必须同步登记这里**。
        _CHK_FORMS = (
            (r"`check` 共 \*\*%s项\*\*", "SKILL 的 check 总述"),
            (r"不计入上面%s项", "SKILL 的 --controls 不计入"),
            (r"第 \d+ 步的%s项", "SKILL 的「第 N 步的九项」"),
            (r"%s项校验", "工具表里的「九项校验」"),
            (r"%s项分别查什么", "faq 的「九项分别查什么」"),
            (r"不计入这%s项", "faq 的「不计入这九项」"),
            (r"也不计入%s项", "faq 的「也不计入九项」"),
            (r"上面那张%s项表", "faq 的「上面那张九项表」"),
            (r"%s项里哪几项", "faq 的「九项里哪几项真跑了」"),
            (r"默认%s项", "examples 的「默认九项」"),
            (r"%s项全绿", "examples 的「九项全绿」"),
        )
        _chk_files = ("SKILL.md", "README.md", "references/faq.md", "examples/README.md")
        _spans, _n_hit = [], 0
        for _form, _lab in _CHK_FORMS:
            _pat = _form % _num
            _n_this = 0
            for _rel in _chk_files:
                _fp = os.path.join(root, _rel.replace("/", os.sep))
                if not os.path.isfile(_fp):
                    continue
                _body = io.open(_fp, encoding="utf-8").read()
                for _m2 in re.finditer(_pat, _body):
                    _n_this += 1
                    _spans.append((_rel, _m2.start(), _m2.end()))
                    _n_hit += 1
            if _n_this == 0:
                doc_fail.append("自称数字不符：文档里找不到「%s」这种**已登记句式**"
                                "（%s，期望 %s 项）—— 要么补回该句，要么在 `_CHK_FORMS` 里改登记"
                                % (_lab, _lab, _num))
        # 逐处覆盖：每个「<期望数字>项」的出现都必须落在某条已登记形态里
        _uncov = []
        for _rel in _chk_files:
            _fp = os.path.join(root, _rel.replace("/", os.sep))
            if not os.path.isfile(_fp):
                continue
            _body = io.open(_fp, encoding="utf-8").read()
            for _m3 in re.finditer(_num + "项", _body):
                if not any(_s[0] == _rel and _s[1] <= _m3.start() < _s[2] for _s in _spans):
                    _line3 = _body[:_m3.start()].count("\n") + 1
                    _uncov.append("%s:%d「%s」" % (_rel, _line3,
                                                   _body[max(0, _m3.start() - 18):_m3.end() + 8]
                                                   .replace("\n", " ")))
        if _uncov:
            doc_fail.append("自称数字不符：这些「%s项」说法**没有登记句式**（⛔ 别整个文件粗匹配，"
                            "要么把句子登记进 `_CHK_FORMS`、要么改掉该句）：%s"
                            % (_num, "；".join(_uncov[:6])))
        if _n_hit and not _uncov:
            print("[ok]  自称数字（check 判定项数）：代码 %d 项 ↔ 文档 %d 处「%s项」，"
                  "逐句式登记 %d 条形态、逐处覆盖无遗漏"
                  % (_chk_n, _n_hit, _num, len(_CHK_FORMS)))

    # 注意：上面那几条针对 **README** 的计数断言（`faq.md # N 条` 等）现在是**惰性**的 ——
    # README 的目录树已不再写各文件的条数（两处维护必然漂移），计数只留在各文件自己 + SKILL。
    # 它们留着是为了"哪天有人把计数写回 README 时立刻查"，不是死代码。

    # 17w 测试 prompt 的**覆盖度**（比"条数对不对"有用得多）：每个子命令至少要被一条 prompt
    #     提到 —— 否则"新加了命令，但评测语料里没人测它"会一直没人发现。
    #     实测：`diffguard` 会在 prompt 语料里出现 **0 次**（其余 14 个命令都有），
    #     而三种评审方法（darwin / TRACE / 文档审计）**没有一个能看见这件事**。
    #     ⚠️ 本号另有一处（管 文档格式五查：表格列数/标题跳级/代码块闭合/行尾空白/末尾换行）—— 见本文件 `行尾有多余空白`（grep `行尾有多余空白`）。
    #     起因：新加子命令但评测语料里没人测它 ⇒ 无人发现（实测 `diffguard` 在语料里出现 0 次，三种评审法都没看见）。
    try:
        with open(os.path.join(root, "test-prompts.json"), "r", encoding="utf-8") as _fh:
            _tps = json.load(_fh)
        _tp_text = " ".join((str(t.get("prompt", "")) + " " + str(t.get("expected", "")))
                            for t in _tps)
        with open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "r", encoding="utf-8") as _fh:
            _allsubs = sorted(set(re.findall(r'sub\.add_parser\(\s*"([a-z]+)"', _fh.read())))
        _uncovered = [_s for _s in _allsubs if _s not in _tp_text]
        if _uncovered:
            doc_fail.append("test-prompts.json 里没有任何 prompt 覆盖这些子命令：%s" % _uncovered)
    except (OSError, ValueError) as _exc:
        doc_fail.append("test-prompts.json 读不了或不是合法 JSON：%s" % _exc)

    # ⭐ 并入本块（17w）：**文档里写给用户看的命令样例，照抄必须跑得通**（`#82` 的通用解析式守卫）。
    #     起因：`#82` 裁定「登记为已知无守卫、⛔ 不加窄守卫」（硬编码某个 flag 名属"纸糊式"）——
    #     正解即本臂：逐条喂 `build_parser().parse_args()`，与具体 flag / 子命令清单无关。
    #     抽取面与跳过口径见模块级 `_PROMPT_CMD_RE` 上方注释（**可枚举、不写死文件清单**）。
    #     ⚠️ 与 17w 同属一类：**样例/语料必须与命令行接口同步**（那边是 test-prompts 的覆盖度，
    #     这边是文档样例的可解析性）⇒ 故并入、⛔ 不新开块名（新块名会撞 `_DOC_GUARD_BLOCK_BASE`）。
    _pc_bad, _pc_n, _pc_skip = _doc_prompt_cmd_probe(root)
    if _pc_bad:
        doc_fail.append(_pc_bad)
    else:
        print("[ok]  文档命令样例可解析：%d 条 `xwl.py <命令>` 照抄全部能被解析器接住"
              "（另有模板记法 %d 条：`…`／`|` 截到记号前、可选组舍去后**也判过**，不因带省略号就免检）"
              % (_pc_n, _pc_skip))

    # 17x 打包元数据必须与 SKILL.md 一致。`metadata.json` 是**平台与本地评测器读的**打包声明
    #     （TRACE 的 T/R/E 维直接看它），却一直没有守卫 —— 版本号 / name / references 列表
    #     一旦漂移，评测读到的就是错的。而三种评审方法都只看工作树，**看不出这个**。
    #     ⚠️ 本号另有一处（管 文档自称数字）—— 见本文件 `自称数字不符`（grep `自称数字不符`）。
    #     起因：metadata.json 是平台与本地评测器读的打包声明却长期无守卫 —— version／name／references 一旦漂移，评测读到错值，而评审只看工作树、看不出。
    _mdp = os.path.join(root, "metadata.json")
    if not os.path.exists(_mdp):
        doc_fail.append("缺少 metadata.json（SkillHub 打包与平台评测会读它）")
    else:
        try:
            with open(_mdp, "r", encoding="utf-8") as _fh:
                _md = json.load(_fh)
            _skv = re.search(r"^version:\s*(\S+)", _sk_txt, re.M)
            if _skv and _md.get("version") != _skv.group(1):
                doc_fail.append("metadata.json 的 version=%r 与 SKILL.md 的 %r 不一致"
                                % (_md.get("version"), _skv.group(1)))
            _skn = re.search(r"^name:\s*(\S+)", _sk_txt, re.M)
            if _skn and _md.get("name") != _skn.group(1):
                doc_fail.append("metadata.json 的 name=%r 与 SKILL.md 的 %r 不一致"
                                % (_md.get("name"), _skn.group(1)))
            _mdrefs = sorted(os.path.basename(str(x)) for x in (_md.get("references") or []))
            _dkrefs = sorted(f for f in os.listdir(os.path.join(root, "references"))
                             if f.endswith(".md"))
            if _mdrefs != _dkrefs:
                doc_fail.append("metadata.json 的 references 列表与磁盘不一致：声明 %s / 实际 %s"
                                % (_mdrefs, _dkrefs))
            # ⭐ `references` 数组 ↔ `layers` 键集**双向相等** ＋ 数组内不得重复（层归属迁进
            #     metadata.json 后新增的对账臂）。
            #     起因（不这么做会漏什么）：层归属的唯一真源已是 `layers`，但"哪些文件随包发布"仍是
            #     `references` 数组 —— 两处各说一套时**没有单条守卫能同时看到两侧**：`17u` 按磁盘实际
            #     文件查 `layers`（看不到"数组里还留着一条已删文件"），而上一行只比数组与磁盘（看不到
            #     `layers` 的键）。故在此双面对账。
            #     ⚠️ 覆盖关系（如实登记）：在本守卫集下它**不是唯一命中者** —— 任何一处不一致通常也会
            #       被上一行（数组 vs 磁盘）或 `17u` 的"多出来的键"打中；本臂的价值是**报错文案直接指向
            #       "两处不一致"**，以及在磁盘列不出文件时仍能对账。
            _mdlay = _md.get("layers")
            if isinstance(_mdlay, dict):
                _lk = {str(_k) for _k in _mdlay}
                _rk = {str(_x) for _x in (_md.get("references") or [])}
                if _lk != _rk:
                    doc_fail.append("metadata.json 的 `layers` 键集与 `references` 数组不一致："
                                    "只在 references 不在 layers：%s ／ 只在 layers 不在 references：%s"
                                    % (sorted(_rk - _lk), sorted(_lk - _rk)))
            _rraw = [str(_x) for _x in (_md.get("references") or [])]
            _rdup = sorted({_x for _x in _rraw if _rraw.count(_x) > 1})
            if _rdup:
                doc_fail.append("metadata.json 的 `references` 数组里有重复项（同一份登记 ≥2 次）：%s" % _rdup)
            # ⭐ 打包声明与变更记录的**措辞对账**（note 级：⛔ 不进 `doc_fail`、⛔ 不改 `rc`）。
            #     起因（现象）：`update_history` 段按历史记录语义整段豁免，于是「同一事实在打包声明的
            #     最新版 summary 与变更记录里措辞不一致」无人发现 —— 最新版 summary 里的某个标识，
            #     在 CHANGELOG 与其余交付物正文里都找不到，读的人无从判断它指代什么。
            #     只提示、不下判：差集非空也可能是包内无法解析的内部标号，须人工确认。
            #     `update_history` 缺失／不是 list／首元素不是 dict／`summary` 缺失 ⇒ 静默跳过。
            _idn_re = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,4}\d{1,3}(?![A-Za-z0-9])|#\d{1,3}")
            _idn_hist = _md.get("update_history")
            _idn_own = set()
            if isinstance(_idn_hist, list) and _idn_hist and isinstance(_idn_hist[0], dict):
                _idn_sum = _idn_hist[0].get("summary")
                if isinstance(_idn_sum, str):
                    _idn_own = set(_idn_re.findall(_idn_sum))
            if _idn_own:
                _idn_pool = set()
                for _idn_t in _txt.values():
                    _idn_pool.update(_idn_re.findall(_idn_t if isinstance(_idn_t, str) else str(_idn_t)))
                try:
                    with open(os.path.join(root, "CHANGELOG.md"), "r", encoding="utf-8") as _idn_fh:
                        _idn_pool.update(_idn_re.findall(_idn_fh.read()))
                except OSError:
                    pass
                _idn_cand = sorted(_idn_own - _idn_pool)
                if _idn_cand:
                    _gate_note("17x-note 交付物标识一致性：最新版 summary 出现 %d 个别处没有的标识 %s"
                          " ⇒ 可能是包内无法解析的内部标号，须人工确认（不进 rc）"
                          % (len(_idn_cand), "、".join(_idn_cand)))
            # ⭐ 版本三处机械对账：CHANGELOG 首段 ↔ metadata.version ↔ update_history[0]
            doc_fail.extend(_doc_guard_version_three(root, _md))
        except (OSError, ValueError) as _exc:
            doc_fail.append("metadata.json 读不了或不是合法 JSON：%s" % _exc)
    # DIST-HIST-SPAN：历史文档空代码 span 残骸（围栏感知；白名单自校验 8/0）
    doc_fail.extend(_doc_guard_hist_span_residue(root))

    # 17t 清单的「改已有文件 X + 新建文件 Y」拆分须与参考清单实算一致（SKILL.md 内该形态出现 1 处；`finditer` 会核全部命中）
    #     起因：`SKILL.md` 自称的「改已有文件 X ＋ 新建文件 Y」拆分数字与实际参考清单不一致时**无人守**
    _grp2: dict = {}
    _g2 = None
    for _l in _txt.get("references/checklist.md", "").split("\n"):
        if _l.startswith("## "):
            _g2 = _l[3:].strip()
            _grp2[_g2] = 0
        elif _g2 and re.match(r"^- \[ \]", _l):
            _grp2[_g2] += 1
    _new2 = sum(v for k, v in _grp2.items() if "新建" in k)
    _old2 = sum(_grp2.values()) - _new2
    for _m in re.finditer(r"（改已有文件 (\d+)(?: 项)? \+ 新建文件 (\d+)(?: 项)?）", _sk_txt):
        if int(_m.group(1)) != _old2 or int(_m.group(2)) != _new2:
            doc_fail.append("清单拆分不符：SKILL.md 写「%s + %s」，实际「%d + %d」"
                            % (_m.group(1), _m.group(2), _old2, _new2))
    # 17k 判据描述一致性：`diffguard` 的**主判据是定义级**的（工作区某行 == 基线连续多行
    #     去掉续行符后拼接），而「续行符净减少 且 最长行显著变长」只是**粗筛**。
    #     凡把后者**当成判据来陈述**（"判据是…"/"比…"）却不标明"粗筛"的，都是升级判据时
    #     漏改的旧描述 —— 实测漏过 README 工具速查表 / checklist / faq 三处（正文改了、侧翼没跟上）。
    #     注意判据要"窄"：仅仅**提到**「最长行」不算 —— SKILL.md 2.3 有一段专门复盘
    #     "为什么不能只用最长行这一条"，那里提到它是**正确**的（误报就出在这）。
    #     围栏内的**工具真实输出**也要跳过（那里出现"最长行"是统计行原文）。
    #     起因：判据升级时最容易漏改侧翼的描述（实测漏 README 速查表／checklist／faq 三处）—— 正文改了、侧翼没跟上。
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":
            continue
        _fence = False
        for _i, _l in enumerate(_ls):
            if _l.strip().startswith("```"):
                _fence = not _fence
                continue
            if _fence:
                continue
            _asserts = ("续行符净减少" in _l
                        or ("最长行" in _l and ("判据" in _l or "比" in _l)))
            if _asserts:
                _win = "\n".join(_ls[max(0, _i - 5): _i + 6])
                if "粗筛" not in _win:
                    doc_fail.append("%s:%d 把「续行符净减少 / 最长行」当成判据陈述，"
                                    "却没标明它只是**粗筛**（主判据是定义级的）：%s"
                                    % (_nm, _i + 1, _l.strip()[:60]))
    with open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "r", encoding="utf-8") as _fh:
        _subs = set(re.findall(r'sub\.add_parser\(\s*"([a-z]+)"', _fh.read()))
    # 取**第一列**里出现的全部反引号命令名 —— 一行里可以合并几个命令
    # （如 ``| `sql` / `events` | …``），所以不能只认行首那一个。
    _tbl = set()
    for _ln in _sk_txt.splitlines():
        if not _ln.startswith("|") or _ln.count("|") < 2:
            continue
        _cell = _ln.split("|")[1]
        _tbl.update(re.findall(r"`([a-z]+)[^`]*`", _cell))
    if _subs - _tbl:
        doc_fail.append("SKILL 工具表没覆盖这些子命令：%s" % sorted(_subs - _tbl))

    #   —— 以下为**原 `17j-5` 的排他性断言**（并入本块，⛔ 不新开块名）：
    #      与上面那条同属一件事的**两个面** —— A 面：把「粗筛」当成判据陈述算漏改；
    #      B 面：说压平「只有 git diff / 只能靠人工」能发现、却不提 `diffguard`。
    #      ⛔ 两条判据都要保留：合并只省块名，不省判据。
    #     它所在的**小节**里必须出现 `diffguard`。
    #     只匹配字面词「续行符净减少 / 最长行」的守卫会漏掉"只有 `git diff` 能发现"
    #     这类同义改写 —— 实测漏掉 2 处，其中一处还是**文件内部自相矛盾**
    #     （同文件别处正说 diffguard 是唯一的自动化防线）。
    #     判据按**小节**取而不是按行取：同一节里出现过 diffguard 就算交代过了。
    #     起因：只匹配字面词的守卫会漏同义改写（实测漏 2 处、其一自相矛盾）—— 换个说法就不认了。
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":      # 历史文档，按写入时的事实记，不回改
            continue
        _sec_start, _fence = 0, False
        for _i, _l in enumerate(_ls):
            if _l.strip().startswith("```"):
                _fence = not _fence
                continue
            if _fence:
                continue
            if re.match(r"^#{1,4}\s", _l):
                _sec_start = _i
                continue
            if not re.search(r"(只有|唯一|只能靠)[^。；\n]{0,30}(git diff|人工|手动)", _l):
                continue
            _sec_end = len(_ls)
            for _j in range(_i + 1, len(_ls)):
                if re.match(r"^#{1,4}\s", _ls[_j]):
                    _sec_end = _j
                    break
            _sec = "\n".join(_ls[_sec_start:_sec_end])
            if ("压平" in _sec or "压成一行" in _sec or "合并行" in _sec) \
                    and "diffguard" not in _sec:
                doc_fail.append("%s:%d 「%s」说压平只有 `git diff` / 只能靠人工能发现，"
                                "但该小节里没有 `diffguard`（它已能自动发现）"
                                % (_nm, _i + 1, _l.strip()[:48]))

    # 17j 索引与节号：中文节号（`§五` / `§7`）可解析 + 导航表目标存在 +
    #     references 无孤儿/悬空 + README 目录树里的文件都在磁盘上。
    #     起因：压缩时材料清单与章节被搬动，索引/节号最容易「指了却没有」；references 里的孤儿与悬空文件也没人发现。
    def _has_sec(relp, key):
        for _l in docs.get(relp, []):
            if re.match(r"^##\s*" + re.escape(key) + r"\s*[、.]", _l):
                return True
        return False

    for nm, ls in docs.items():
        if nm == "CHANGELOG.md":
            continue
        for i, l in enumerate(ls, 1):
            # ⚠️ 数字分支加**内层**负前瞻 `(?!\d*\s*\.\d)`：只写外层 `(?!\s*\.\d)` 时，`\d+` 会
            #   在 `§12.3` 上贪吃 `12`、前瞻遇 `.3` 失败后**回退**成 `1`，把两位节号误判为 `§1`
            #   （既有 bug、非本版引入）。内层用 `\d*` 吃住整串数字再判，回溯即被堵死 ⇒ `§12.3`
            #   整体**不匹配**本臂（它归 `17j-12` 按标题文本判）。`§二.3` 类中文点号本就不该出现，
            #   外层前瞻保留作兜底。**去重**：由此本臂不再与 `17j-12` 在同一 `§N.M` 上各报一行。
            for _m in re.finditer(r"§\s*([" + _cn2 + r"]+|\d+(?!\d*\s*\.\d))(?!\s*\.\d)", l):
                _near = list(_fn.finditer(l[: _m.start()]))
                _tg = None
                if _near:
                    _c = [k for k, v in _base.items() if v == _near[-1].group(1)]
                    if _c:
                        _tg = _c[0]
                elif nm.startswith("references/") and "SKILL.md" in l:
                    _tg = "SKILL.md"
                if _tg is None:
                    continue      # 「见 §1」这类缩写没有文档名，判不了归属，放过
                if not _has_sec(_tg, _m.group(1)):
                    doc_fail.append("%s:%d 引用 §%s，但 %s 没有该编号小节"
                                    % (nm, i, _m.group(1), _base.get(_tg, _tg)))
    for i, l in enumerate(docs.get("SKILL.md", []), 1):
        _m = re.match(r"^\|\s*[^|]+\|\s*([^|]+)\|\s*$", l)
        if not _m:
            continue
        for _cm in re.finditer(r"第\s*([" + _cn2 + r"]+)\s*章", _m.group(1)):
            if not _has_sec("SKILL.md", _cm.group(1)):
                doc_fail.append("SKILL.md:%d 导航表指向「第%s章」，但没有这一章" % (i, _cm.group(1)))
        for _fm in re.finditer(r"references/([a-z0-9-]+\.md)", _m.group(1)):
            if not os.path.exists(os.path.join(root, "references", _fm.group(1))):
                doc_fail.append("SKILL.md:%d 导航表指向 %s，但文件不存在" % (i, _fm.group(1)))
    _listed = set(re.findall(r"references/([a-z0-9-]+\.md)", _sk_txt))
    # 列不出 references/ ⇒ **报红**且**跳过**孤儿/缺失两侧比较（读不出要报错、不算「没命中」；在空集合上默默通过＝静默降级）。
    try:
        _on_disk = set(f for f in os.listdir(os.path.join(root, "references")) if f.endswith(".md"))
        _on_disk_ok = True
    except OSError as _exc:
        _on_disk, _on_disk_ok = set(), False
        doc_fail.append("文档守卫：列不出 references/ 目录（%s: %s）—— 报错，不算「没命中」；"
                        "本轮跳过孤儿/缺失两侧比较" % (type(_exc).__name__, _exc))
    # 仓库根 README 机械守卫（不在本守卫的 root=SKILL_ROOT 扫描面；⛔ 不新开块名）
    doc_fail.extend(_doc_guard_root_readme())
    _S.update({_n: _v for _n, _v in locals().items()
                   if _n in ('_body', '_fh', '_fm', '_i', '_j', '_l', '_listed', '_ln', '_m', '_md', '_nm', '_on_disk', '_on_disk_ok', '_rel')})


@_cap
def _docs_layers_and_distribution(_S) -> None:
    """`_check_docs` 的第 3 段（机械切分，判据文本逐字未改）。

    段内通过 `_S` 共享状态：**读**的先取、**写**的末了写回 —— 拆函数不改变语义，
    也不改变任何一条判据的文本（只多了一层状态搬运）。
    """
    # ⚠️ 跨段键一律 `.get(默认)`（双保险：即便将来有人新增一段却忘了在 `_S` 里初始化，也不崩）。
    #    必填键（`doc_fail` / `docs` / `root` / `tmp`）仍**硬取**：它们缺席是调用方坏了。
    _body = _S.get("_body", "")
    _fh = _S.get("_fh", None)
    _got = _S.get("_got", None)
    _i = _S.get("_i", 0)
    _l = _S.get("_l", "")
    _listed = _S.get("_listed", set())
    _m = _S.get("_m", None)
    _nm = _S.get("_nm", "")
    _on_disk = _S.get("_on_disk", set())
    _on_disk_ok = _S.get("_on_disk_ok", False)
    _rel = _S.get("_rel", "")
    _rm_txt = _S.get("_rm_txt", "")
    _sk_txt = _S.get("_sk_txt", "")
    doc_fail = _S["doc_fail"]
    docs = _S["docs"]
    root = _S["root"]
    tmp = _S["tmp"]
    if _on_disk_ok:
        if _on_disk - _listed:
            doc_fail.append("references 里有 SKILL.md 从未提到的文件（孤儿）：%s" % sorted(_on_disk - _listed))
        if _listed - _on_disk:
            doc_fail.append("SKILL.md 提到的 references 文件不存在：%s" % sorted(_listed - _on_disk))
    _disk = set()
    for _r, _dn, _fs in os.walk(root):
        if ".git" in _r or "__pycache__" in _r:
            continue
        for _x in _fs:
            _disk.add(_x)
            _disk.add(os.path.relpath(os.path.join(_r, _x), root).replace(os.sep, "/"))
    _ghost = []
    # ① 根 README.md 的 ASCII 目录树：`[├└]──` 形态（原有面）。
    _tree = re.findall(r"[├└]──\s+([A-Za-z0-9_.\-]+\.(?:md|py|json))", _rm_txt)
    _ghost += [x for x in _tree if x not in _disk]
    # ② `examples/README.md` 表格里提到的 `ops-*.json`（本臂新增面）：
    #     起因：`examples/README.md` 是**对外清单**、逐一列出 `examples/ops-*.json` 并逐份讲"示范什么"，
    #       但 ① 只扫根 README 的 ASCII 树 ⇒ 删掉/改名一份样板后，那张表**照旧列着它**、无人报红
    #       （`17v` 只跑**磁盘上实际存在**的样板 ⇒ 也不报警）。两臂合起来才盖住"清单 ↔ 实物"两个方向。
    #     ⚠️ 抽取**限 `ops-<小写短横>.json` 族**：`examples/README.md` 里还有别的 `.json` 提法（如未来
    #       的工具输出样例），限族可避免把"非样板"的字面也当成承诺；本文件表形与行内提及**都收**。
    #     ⚠️ 读不出**报红**、不算「没命中」（与全仓其它读盘面同口径：空集合上默默通过＝静默降级）。
    _ex_rm = os.path.join(root, "examples", "README.md")
    try:
        with open(_ex_rm, "r", encoding="utf-8", newline="") as _fx:
            _ex_txt = _fx.read()
    except (OSError, UnicodeDecodeError) as _exc:
        _ex_txt = None
        doc_fail.append("文档守卫：读不出 examples/README.md（%s: %s）—— 报错，不算「没命中」"
                        % (type(_exc).__name__, _exc))
    if _ex_txt is not None:
        _ex_disk = set()
        _ex_dir = os.path.join(root, "examples")
        try:
            _ex_disk = set(f for f in os.listdir(_ex_dir) if f.endswith(".json"))
        except OSError as _exc:
            doc_fail.append("文档守卫：列不出 examples/ 目录（%s: %s）—— 报错，不算「没命中」"
                            % (type(_exc).__name__, _exc))
        _ex_ref = sorted(set(re.findall(r"`(ops-[a-z-]+\.json)`", _ex_txt)))
        _ghost += [x for x in _ex_ref if x not in _ex_disk]
    if _ghost:
        doc_fail.append("README 里列了磁盘上没有的文件：%s" % sorted(set(_ghost)))

    # 17j-3 索引双向登记：SKILL.md 里提到的每个 `references/*.md` 都必须在「怎么用」那张
    #     **参考材料索引表**里占一行（那张表是唯一的材料索引）。起因是压缩时把材料清单从
    #     §四 挪进「怎么用」表 —— 挪完若漏登记一个，读者就再也找不到它了。
    _idx: set[str] = set()
    _in_idx, _got_row = False, False
    for _l in _sk_txt.splitlines():
        if "兼作参考材料索引" in _l:
            _in_idx = True
            continue
        if not _in_idx:
            continue
        if _l.startswith("|"):
            _got_row = True
            _idx.update(re.findall(r"references/([a-z0-9-]+\.md)", _l))
        elif _got_row and not _l.strip():
            break      # 表收了行之后再遇到空行才算结束（marker 与表头之间本来就有空行）
    if not _idx:
        doc_fail.append("SKILL.md 的参考材料索引表为空或找不到（「兼作参考材料索引」那张表）")
    _unreg = sorted(set(re.findall(r"references/([a-z0-9-]+\.md)", _sk_txt)) - _idx)
    if _unreg:
        doc_fail.append("SKILL.md 提到但**未登记进参考材料索引表**的文件：%s" % _unreg)

    # 17j-4 篇幅上限：**不是目标，是防回弹的护栏**。压缩过一次之后，新增内容很容易又堆回
    #     SKILL.md；到了上限就该问"这条是不是该下沉到 references/"。数字留了余量，
    #     正常的小幅增补不会触发。
    #     起因：压缩过一轮后，新增内容很容易又堆回 SKILL.md —— 到上限该下沉到 references/，不该抬数字（防回弹护栏）。
    #     ⚠️ **两条上限独立报出**（⛔ 不合并 —— 并成一条会丢信息）：硬上限 **32 000 字符**、
    #       软上限 **28 000 字符**（越过 ＝「该外移了」的信号）；两条都进 `doc_fail`。
    #       ⭐ 换算依据（⛔ 别只写数，否则下批会以为是拍的）：**700 行 × 46.31 ≈ 32 418 ⇒ 取 32 000**；
    #       **600 行 × 46.31 ≈ 27 786 ⇒ 取 28 000**；46.31 ＝ 27 091 字符 ÷ 585 行（同一份 `SKILL.md`
    #       的两把量法；⚠️ 密度**随内容漂** ⇒ 只作换算依据，⛔ 不作判据）。
    #     ⚠️ **单位**：`SKILL.md` 按**字符数**（行数在中英混排里量不出 token，且与 `references/` 的
    #       字符口径不同单位 ⇒ 会造出"看着还有余量"的错觉）；`README.md` 仍按**行数** ——
    #       ⛔ 本格**没换单位**：它没有实测密度可换算（46.31 是 `SKILL.md` 的，⛔ 不可挪用），
    #       连带换等于又改了一条判据。
    #     ⚠️ **12 000 字符是远期目标、⛔ 不进判据**：只由通过态的 `[note]` 报差距。
    #       起因①：阈值须有缓冲 —— 越过上限是「该外移了」的**信号**，但 **severity 是真红**（走 `doc_fail`、`rc=1`），
    #              ⛔ 别读成"可以不管"；硬／软两条**各自报出**、⛔ 不合并。
    #       起因②：改阈值**必须走版本位 ＋ 写明起因**（防"顺手抬上限"）。
    #       起因③：**它证明不了"本次新增没让它涨"**（**跨版本**属性、单树判不了）；且**不为它引 git 历史**
    #              （多一条 `git ls-files` 门控守卫 ⇒ **非 git 时红** ⇒ zip 假报警，与既有方向冲突）。
    #     B1 迁入：判定逻辑已迁入 `contract_scanner.guard_length_caps`（读字符数/`_gate_note` 由本文件注入）。
    #       返回 `(violations, notes)`：violations 进 doc_fail（判红），notes 走 `_gate_note`（不进 rc）。
    _cs_17j4 = _load_contract_scanner()
    if _cs_17j4 is None:
        doc_fail.append("篇幅上限：contract_scanner 加载失败 —— 报错，不算通过")
    else:
        _sk_hard, _sk_soft, _sk_goal = 32000, 28000, 12000
        _l4_v, _l4_notes = _cs_17j4.guard_length_caps(
            root, docs, sk_hard=_sk_hard, sk_soft=_sk_soft, sk_goal=_sk_goal,
            read_chars=_read_doc_chars, gate_note=_gate_note)
        doc_fail.extend(_l4_v)
        for _l4_note in _l4_notes:
            _gate_note(_l4_note)

    # 17j-7 `--help` 篇幅上限（通道 B 的护栏）：把 §一/§三/§五/§七 的细节搬进
    #     `xwl.py` 的 `help=` / 参数 help / `epilog` 之后，`--help` 会变长；这条钉住它别再涨。
    #     做法：**内省解析器对象**（`xwl.build_parser()`）逐面 `format_help()` 计行数 ——
    #     **不比对文案**（文案本来就会随措辞改，快照式断言一改就假红），只比「行数 ≤ 上限」。
    #     宽度钉 80 列：这正是管道下 argparse 的默认宽度，也是本批实测表的量法；
    #     终端更窄会多折行、更宽会少折行，不钉死就会随环境漂（假红/假绿都可能）。
    #     上限 = 实测 + 余量（顶层 +10 / 单子命令 +5）。余量依据：给「某个子命令再加 1 条选项
    #     说明」留空间而不误报；再涨就该把内容挪去 `epilog` 或 `references/`（见 workflow-notes §二）。
    #     ⚠️ 两侧都判：`_got > _hcap` = 「超顶」（上限偏低）；`_hcap − _got > 设计余量` = 「上限过松」
    #       （上限被单向放宽、白留空行也无人发觉 —— 常驻注入用例把某子命令上限调大后仍全绿＝活证）。
    #       ⚠️ 只堵「过松」一侧：余量 **＜** 设计余量（＝「守卫偏严」）**不报**（本版已把 `new` /
    #       `expand` 按 `实测 + 5` 补满 ⇒ 现全表余量恰好等于设计余量、无偏严项）。
    #     ⚠️ 新增子命令必须同步在此登记上限（下面 `_h_unreg` 会把漏登的红出来）。
    #     起因：通道 B 把细节搬进 `--help` 后它会一路变长 —— 不钉住就会淹没「必读面」，读者找不到关键项。
    #     ⚠️ 表体已**移出函数体**（#15 有界下沉）⇒ 见**模块级常量 `_help_caps`**（本文件 `_check_docs` 之前）。
    try:
        _hp_top = xwl.build_parser()
        _hp_sub = next((_a for _a in _hp_top._actions if getattr(_a, "choices", None)), None)
        _wild = os.environ.get("COLUMNS")
        os.environ["COLUMNS"] = "80"
        try:
            _help_n = {None: len(_hp_top.format_help().splitlines())}
            if _hp_sub is not None:
                for _hn2, _hpar in _hp_sub.choices.items():
                    _help_n[_hn2] = len(_hpar.format_help().splitlines())
        finally:
            if _wild is None:
                os.environ.pop("COLUMNS", None)
            else:
                os.environ["COLUMNS"] = _wild
        for _hn, _hcap in _help_caps.items():
            _hn_lbl = "顶层 xwl.py --help" if _hn is None else "xwl.py %s --help" % _hn
            _got = _help_n.get(_hn)
            if _got is None:
                doc_fail.append("`--help` 行数守卫：找不到 %s 对应的 parser" % _hn_lbl)
            elif _got > _hcap:
                doc_fail.append("%s 已 %d 行，超过 %d 行上限（新增说明请走 `epilog` 或 `references/`）"
                                % (_hn_lbl, _got, _hcap))
            else:
                _slack = 10 if _hn is None else 5
                if _hcap - _got > _slack:
                    doc_fail.append("%s：上限 %d 比实测 %d 多出 %d 行、超过设计余量 %d"
                                    "（上限请按「实测 + %d」回填；新增说明请走 epilog 或 references/）"
                                    % (_hn_lbl, _hcap, _got, _hcap - _got, _slack, _slack))
        _h_unreg = sorted(k for k in _help_n if k not in _help_caps)
        if _h_unreg:
            doc_fail.append("`--help` 行数守卫：这些子命令没登记上限（新增子命令要同步补）：%s" % _h_unreg)
    except Exception as _hexc:  # noqa: BLE001 —— 解析器构造失败本身就该红，别静默放过
        doc_fail.append("`--help` 行数守卫跑不起来：%s" % _hexc)

    # 17j-8 支持矩阵的**操作系统**行必须存在（SKILL 适用范围表 + metadata.json limitations）。
    #     起因：跨平台是真实约束（Windows 检出/存储形态差异、路径分隔符、换行），
    #     平台适配性评测会看「有没有声明适用 OS」；而这条最容易在精简适用边界表时被顺手删掉。
    #     判据（窄）：SKILL.md 适用范围表里有一行**项 = 操作系统**且同时含 `Windows` 与
    #     `POSIX`（或 `macOS`）；`metadata.json` 的 `limitations` 里也有一条 OS 行（同口径）。
    _os_sk = any(("操作系统" in _l and "Windows" in _l and ("POSIX" in _l or "macOS" in _l))
                 for _l in docs.get("SKILL.md", []) if _l.strip().startswith("|"))
    if not _os_sk:
        doc_fail.append("SKILL.md 适用范围表缺「操作系统」行（须同时含 Windows 与 POSIX/macOS）")
    try:
        with open(os.path.join(root, "metadata.json"), "r", encoding="utf-8") as _fh:
            _mdos = json.load(_fh)
        _os_md = any(("Windows" in str(_x) and ("POSIX" in str(_x) or "macOS" in str(_x)))
                     for _x in (_mdos.get("limitations") or []))
        if not _os_md:
            doc_fail.append("metadata.json 的 limitations 缺「操作系统」行"
                            "（须同时含 Windows 与 POSIX/macOS）")
    except (OSError, ValueError) as _exc:
        doc_fail.append("metadata.json 读不了（OS 行检查）：%s" % _exc)

    # ⚠️ 非 git 停用面登记器：本函数里**依赖 `git ls-files`** 的守卫现为 **2 个** ——
    #   编年守卫（`17l`）／ `17r`；非 git（如平台把 skill 打成 zip 分发、解包后本无 `.git`）时二者
    #   取不到清单。既要**避免 zip 用户被假报警**、又要**避免"静默绿"** ⇒ 现为**默认判红**
    #   （`[FAIL]`、`rc=1`）；**仅**在**显式** `--allow-nogit` 的降级路径下，才把"没跑"的臂
    #   **收集起来**、只打 `[note] …本次没扫`，并在末尾汇总行**显式标注**「本次 … 未执行：无 git」。
    #   （`17p` 是**纯结构**守卫、不依赖 git，不计入本集合。）
    _nogit_arms: list[str] = []

    # 误导版措辞的字面量（供 `17j-9` / `17j-10` 用）：**相邻字面量拼接**写。
    #   拼接的原始理由（本文件也在全仓扫描面内）已随 `17j-9` 收窄而消失；**保留**拼接是为了
    #   将来若恢复全仓扫描时不致自命中 —— ⛔ 不要改回整词。
    _bad_lit = "app." "<itemId>"

    # 17j-9 分发**文档**里不得再出现误导版措辞字面量（豁免 CHANGELOG.md）。
    #   起因（删了会怎样）：误导版把「工具 `@itemId` 寻址」错说成「运行时用 itemId 取名」——
    #   而运行时注册键其实是 `normalName || itemId`。本仓有 4 处同源订正，而这**无自动化守卫**
    #   （QA 注入：4 处全改回误导版、或只漏改 SKILL.md 一处，selftest 仍 rc=0 / [FAIL]=0）。
    #   ⚠️ **射程（2026-10-19 收窄，⛔ 不是"重复"）**：只扫**已加载的分发文档**
    #     （`SKILL.md` / `README.md` / `references/*.md`），⛔ 不扫 CHANGELOG（按写入时的措辞留史）。
    #     `scripts/*.py` 里的同类措辞由 `17j-10` **行为级**守住（真跑 `schema --skeleton` 断言输出），
    #     故不重复做文本扫描。收窄后**不依赖 git** ⇒ 非 git 分发下同样生效。
    _a9_hits = []
    for _rel9, _ls9 in docs.items():
        if _rel9 == "CHANGELOG.md":
            continue
        for _i9, _l9 in enumerate(_ls9, 1):
            if _bad_lit in _l9:
                _a9_hits.append("17j-9 旧措辞残留：%s:%d 含「%s」—— 原文：%s"
                                % (_rel9, _i9, _bad_lit, _l9.strip()[:80]))
    if _a9_hits:
        doc_fail.extend(_a9_hits)
    else:
        print("[ok]  17j-9 分发文档无旧措辞「%s」残留（豁免 CHANGELOG.md）" % _bad_lit)

    # 17j-6 承诺的输出文案必须真的存在：SKILL.md 里用反引号引的、以行首标记开头的
    #     **工具输出字面量**，其内容必须能在工具**真跑出来的输出**里找到。
    #     起因：SKILL.md 承诺过「`edit` 写盘后给 `[note] 该文件是 LF 换行（…）`」，
    #     而代码对**无换行**文件走的是另一个分支（`[note] 该文件是单行形态（…）`）——
    #     文档承诺了一个工具不会打印的提示。这类"文案承诺"只有对着**真实输出**查才看得出。
    #     ⚠️ oracle 口径（本轮仪表审计整改）：**不再**拿 `xwl.py` 的源码串当期望 —— 源码串里
    #     注释、或永不执行的字符串常量，都能满足"源码里出现过"，那是**可判定的自证循环**；
    #     现在期望来自 `_real_out_corpus()` 的**真实输出**（见其 docstring 的语料面说明）。
    #     判据要窄：只看 `[note]/[warn]/[FAIL]/[ok]` 开头且正文 ≥8 字的；
    #     带省略号（`…`）的按省略号前的内容比对（作者是有意截断）。
    _real_out = _real_out_corpus(tmp)
    for _i, _l in enumerate(_sk_txt.splitlines(), 1):
        for _m in re.finditer(r"`(\[(?:note|warn|FAIL|ok)\])((?:(?!`).)*)`", _l):
            _body = _m.group(2)
            _body = _body.split("…")[0] if "…" in _body else _body
            _n = re.sub(r"\s+", "", _body)
            if len(_n) < 8:
                continue
            # 比对前缀取 16 字（而不是 8）—— 8 字太短，「设计器/仓库」这类**词序对调**
            # 发生在第 9 字之后，8 字比不出来（负向测试实测漏过）。
            _probe = _n[:16]
            if _probe not in _real_out:
                doc_fail.append("SKILL.md:%d 承诺的输出文案 `%s…` 在工具的**真实输出**里找不到"
                                "（若确为工具会打印的新文案，请在 `_real_out_corpus()` 里补一次真实调用）"
                                % (_i, (_m.group(1) + _body)[:34]))

    # 跨文件节号指针／目录顺序／围栏输出文案三臂**已移出函数体**（#15 有界下沉）——
    #   函数体逼近 1300 行阈值（余量只剩 5、低于设计下限 20）⇒ 三臂编号连续、自成一段，
    #   只依赖 `docs`／`doc_fail`／`_real_out` 三个入参 ⇒ 是「漂移为零」的切法。见模块级同名函数。
    _doc_guard_xfile_pt(docs, doc_fail, _real_out)

    # 17l 编年纪律（三条臂）：非编年文件里不得出现"哪天 / 哪一版发生过什么"。
    #     分工与豁免面的完整说明在 `references/workflow-notes.md` 第一节 —— 改词表或豁免面前先读它。
    #     ⚠️ 词表用**相邻字面量拼接**写：守卫扫的是全部分发文件（**含本文件**），
    #        整词直写会让本文件被自己这三条臂判红。
    #     ⚠️ 作用域 = `git ls-files` ∪ 磁盘新增未跟踪（见 `_git_scan_scope`）—— **未 `git add` 的新文件
    #        也要被看到**。取不到 git ⇒ **默认判红**（静默绿是病根）；确无 `.git` 时须显式 `--allow-nogit`
    #        才降级为"标注继续"，那时其"未执行"由 `_check_docs` 汇总大绿行**显式标注**（见 `_nogit_arms`）。
    #     起因：正文只该留结论；「哪天在哪一版发生过什么」属编年，只许进 CHANGELOG 与依据层 —— 混进正文会让现行事实与历史不分。
    # ⚠️ 三张词表/正则（`_chron`／`_date_verb`＋`_date_re`／`_ver_re`）已**移出函数体**（#15 有界下沉）
    #    ⇒ 见**模块级同名常量**（本文件 `_check_docs` 之前）；本函数只引用。
    # ⚠️ **豁免面是「结构判据」**：不写死名单，由 `_chron_exempt(root)` 现算 ——
    #    {`CHANGELOG.md`, `metadata.json`} ∪ `metadata.json` 的 `layers` 里登记为 `evidence` 的文件
    #    （唯一真源在打包元数据，各份参考材料的首行声明已删）⇒ 拆分后新增的依据层文件**自动**进豁免面；
    #    把某份的 `layers` 值改回 `spec` ⇒ 该份**立刻失豁免**（可注入验证）。
    # B1 迁入：判定逻辑已迁入 `contract_scanner.guard_chronology`；词表/正则、`_chron_exempt`、
    #   `_git_scan_scope`、`_docs_git_arm` 均由本文件注入（保持单一真源、结果逐条等价）。
    _cs_17l = _load_contract_scanner()
    if _cs_17l is None:
        doc_fail.append("编年守卫：contract_scanner 加载失败 —— 报错，不算通过")
    else:
        _cs_17l.guard_chronology(
            root, doc_fail, _nogit_arms, _SUBCHECKS, "编年守卫",
            chron=_chron, date_verb=_date_verb, date_re=_date_re, ver_re=_ver_re,
            chron_exempt=_chron_exempt, git_scan_scope=_git_scan_scope,
            docs_git_arm=_docs_git_arm)

    # 17m 判据溯源自检：`scripts/*.py` 里的**点名式引用**必须可解析（点名 = 写了文档名）。
    #     裸 `§N.M`（没写文档名）不判 —— 那会把各文件自己的节号当成跨文件引用，踩出一片误报。
    #     起因：两处"见 SKILL.md 4.1"其实该指 §4.2（退出码表在那儿）—— 说明这类引用没人守。
    _sk_heads = set()
    for _l in docs.get("SKILL.md", []):
        _mh = re.match(r"^#{1,4}\s*(\d+\.\d+)\s", _l)
        if _mh:
            _sk_heads.add(_mh.group(1))
    _refdir = os.path.join(root, "references")
    for _rel in ("scripts/xwl.py", "scripts/selftest.py"):
        try:
            _bl = open(_src_ref_abspath(_rel),
                       encoding="utf-8", newline="").read().splitlines()
        except OSError:
            continue
        for _i, _l in enumerate(_bl, 1):
            if "CHANGELOG" in _l:
                continue      # 历史条目按写入时的结构记，不按当前结构校验
            for _mh in re.finditer(r"SKILL\.md\s*§?\s*(\d)\.(\d)", _l):
                if "%s.%s" % (_mh.group(1), _mh.group(2)) not in _sk_heads:
                    doc_fail.append("%s:%d 引用 SKILL.md §%s.%s，但 SKILL.md 没有该编号小节"
                                    % (_rel, _i, _mh.group(1), _mh.group(2)))
            for _mh in re.finditer(r"SKILL\.md\s*「([^」]{1,24})」", _l):
                if "%" in _mh.group(1):
                    continue      # 格式化占位符（`SKILL.md「%s」`）不是引用
                if _mh.group(1) not in _sk_txt:
                    doc_fail.append("%s:%d 引用 SKILL.md「%s」，但 SKILL.md 里找不到这个说法"
                                    % (_rel, _i, _mh.group(1)))
            for _mh in re.finditer(r"references/([a-z0-9-]+\.md)", _l):
                if not os.path.exists(os.path.join(_refdir, _mh.group(1))):
                    doc_fail.append("%s:%d 引用 references/%s，但文件不存在"
                                    % (_rel, _i, _mh.group(1)))
    # 源码行号引用（`xxx.py:N` / `` `符号名`（`:N`） ``）必须还指得准 —— 判据与残余见 `_src_line_ref_fails`。
    doc_fail.extend(_src_line_ref_fails(root))
    _S.update({_n: _v for _n, _v in locals().items()
                   if _n in ('_fh', '_hit', '_i', '_l', '_m', '_n', '_nogit_arms', '_probe', '_r', '_rel')})


# ---- 函数体行数上限（**机械断言**，⛔ 不是注释里那句"约定 ≤400 行"）----
#   ⭐ 位置约束：本段**必须在受管函数的函数体之外**。它量的 `_CAP_FNS` 里就有 `_docs_tail_scaffold`
#     自己 ⇒ 写进任何一个受管函数体内即**自指**（判据住在被它自己限制的函数里）：函数长到 399 行、
#     上限 400 时，往那一段**加第一行就顶穿自己的上限**，而现场报错只会说"函数太长"，
#     与真实原因（判据占了自己的额度）无关。
#   ⚠️ 搬动时⛔ 不许改判据语义，也⛔ 不许"顺手"调 `_FN_CAP`。
#   起因（不这么做会漏什么）：这类"该拆了"的约定只写在注释里 ⇒ 没人量、也没人拦，
#     实测 `_check_docs` 一路长到 1200+ 行；等它长回来了再拆，成本远高于现在就钉一条上限。
#   量法：`ast` 的 `end_lineno - lineno + 1`（⛔ 不是数空行/注释的近似值）。
#   ⚠️ **`_check_new_guards` 薄壳（13 行）不入本表**；但它那 6 个判据族子函数**现已入表** ——
#     拆分只治"单函数过长"，治不了"子函数各长一截、无人拦"：`_ng_check_controls` 381 行、
#     `_ng_params_defaults` 337 行，都在 400 之下却没人管 ⇒ 纳管当场仍是**绿**，价值是防反弹。
_FN_CAP = 400
# _CAP_FNS 由 @_cap 自注册派生（_cap_fns()），不再手填常量

# ⭐ 独立纳管集合：**不能只拿装饰器派生集合自证** —— `@_cap` 一旦从某函数上
#   被摘掉，`_cap_fns()` 就少一个名字、而"集合与自身一致"照样绿 ⇒ 超限函数静默逃逸。
#   故这里冻结一份**独立清单**作 oracle：`_cap_fns()` 必须与它**逐名相等**（缺 / 多都判红）。
#   ⚠️ 有意增删纳管对象时：先改本清单 **并** 在 `CHANGELOG.md` 写明，再改函数装饰器；
#      ⛔ 不许为"让自检变绿"而单方面改它（本批不增删、不调 `_FN_CAP`）。
_CAP_FNS_BASELINE = (
    "_check_basics", "_check_basics_tail", "_check_bc_contract", "_check_bc_contract_tail",
    "_check_docs", "_check_events_and_expand", "_check_subcommands", "_check_subcommands_tail",
    "_check_write_gate", "_check_write_gate_rest", "_doc_guard_xfile_pt", "_docs_contract",
    "_docs_layers_and_distribution", "_docs_numbers_and_tables", "_docs_tail_scaffold",
    "_docs_xfile_consistency", "_ng_check_controls", "_ng_cli_readonly", "_ng_contract_and_unit",
    "_ng_params_defaults", "_ng_platform", "_ng_write_overwrite", "_s1s3_named_cases",
)


def _fn_cap_check(doc_fail) -> None:
    """量 `_CAP_FNS` 里每个真实实现的行数，超 `_FN_CAP` 就把名字与行数写进 `doc_fail`。

    真实实现按「模块文件 + 函数名」定位：docs 侧仍在本文件，其余在
    `tests/selftest_suites/`。主入口同名薄函数不参与行数。
    另核**装饰器派生集合 == 独立纳管清单 `_CAP_FNS_BASELINE`**（缺/多 → 红）：挡住「摘掉 `@_cap`
    即逃逸」；`_cap_seen` 也须与派生集合一致。
    """
    _CAP_FNS = _cap_fns()
    import ast as _ast          # 本判据专用：量函数体行数（模块头没有 import ast，就近引入）
    # ① 装饰器派生集合 vs **独立清单**（不靠集合自证）：缺装饰器 ⇒ 派生少名 ⇒ 红。
    if sorted(_CAP_FNS) != sorted(_CAP_FNS_BASELINE):
        _cap_miss = sorted(set(_CAP_FNS_BASELINE) - set(_CAP_FNS))
        _cap_extra = sorted(set(_CAP_FNS) - set(_CAP_FNS_BASELINE))
        doc_fail.append("函数行数上限：@_cap 派生集合与独立纳管清单不一致 —— 缺 %s / 多 %s"
                        "（缺 = 有函数**被摘掉 @_cap** 或将纳管对象删了却未同步 `_CAP_FNS_BASELINE`；"
                        "多 = 新加 @_cap 却未登记清单）。⛔ 别为变绿单方面改清单。"
                        % (_cap_miss, _cap_extra))
    try:
        _cap_hit, _cap_seen = [], set()
        _cap_files = {"selftest.py": os.path.join(HERE, "selftest.py")}
        for _suite_name in os.listdir(_SUITE_DIR):
            if _suite_name.endswith(".py") and _suite_name != "__init__.py":
                _cap_files[_suite_name] = os.path.join(_SUITE_DIR, _suite_name)
        for _cap_name, _cap_path in _cap_files.items():
            _cap_tree = _ast.parse(io.open(_cap_path, encoding="utf-8").read())
            for _cn in _cap_tree.body:
                if isinstance(_cn, _ast.FunctionDef) and _cn.name in _CAP_FNS:
                    _cap_seen.add(_cn.name)
                    _cap_n = _cn.end_lineno - _cn.lineno + 1
                    if _cap_n > _FN_CAP:
                        _cap_hit.append("%s %d 行" % (_cn.name, _cap_n))
        # ⭐ 两条判定**各自独立**（⛔ 不许写成 `elif`）：集合不一致说明"有函数改名/漏登记"，
        #   超标说明"有函数该拆了"，是**两件事**，可能同时成立。写成 `elif` 时前者成立就不报后者 ⇒
        #   现场看到"量不到这些函数"、却看不到"顺便还有一个已经 500 行"。
        #   ⚠️ 唯一能证明分支已拆的形态是**联合注入**（两个条件同时成立 ⇒ 两条都报）：单独注入任一条
        #   都证不了分支已拆 —— 撑爆时集合一致、走 `elif` 照样报，两条都绿。
        if sorted(_cap_seen) != sorted(_CAP_FNS):
            doc_fail.append("函数行数上限：量不到这些函数（改名**或不在模块顶层**了？）：%s"
                            % sorted(set(_CAP_FNS) - _cap_seen))
        if _cap_hit:
            doc_fail.append("函数行数上限：%d 个函数超过 %d 行（%s）—— 该拆了，⛔ 别把上限调高"
                            % (len(_cap_hit), _FN_CAP, "；".join(_cap_hit)))
    except (OSError, SyntaxError) as _cap_exc:  # noqa: BLE001
        doc_fail.append("函数行数上限：读不了或解析不了真实实现（%s）—— 报错，不算通过" % _cap_exc)


@_cap
def _docs_tail_scaffold(_S) -> None:
    """`_check_docs` 的第 4 段（机械切分，判据文本逐字未改）。

    段内通过 `_S` 共享状态：**读**的先取、**写**的末了写回 —— 拆函数不改变语义，
    也不改变任何一条判据的文本（只多了一层状态搬运）。
    """
    # ⚠️ 跨段键一律 `.get(默认)` —— 本段就是崩溃点（`KeyError: '_hit'`），`.get` 是兜底。必填键仍硬取。
    _fh = _S.get("_fh", None)
    _fm = _S.get("_fm", None)
    _hit = _S.get("_hit", "")
    _i = _S.get("_i", 0)
    _j = _S.get("_j", 0)
    _l = _S.get("_l", "")
    _ln = _S.get("_ln", 0)
    _m = _S.get("_m", None)
    _md = _S.get("_md", {})
    _miss = _S.get("_miss", [])
    _n = _S.get("_n", 0)
    _nogit_arms = _S.get("_nogit_arms", [])
    _probe = _S.get("_probe", "")
    _r = _S.get("_r", "")
    _rel = _S.get("_rel", "")
    _rm_txt = _S.get("_rm_txt", "")
    _sk_txt = _S.get("_sk_txt", "")
    _txt = _S.get("_txt", {})
    doc_fail = _S["doc_fail"]
    docs = _S["docs"]
    failures = _S["failures"]
    root = _S["root"]
    tmp = _S["tmp"]

    # 跨段变量缺席**不许崩**：用只含必填键的最小 `_S` 真调一次本段（重入由模块级标志挡住）。
    #   起因：白名单里混着循环变量 / 条件赋值（`_hit` / `_miss` / `_probe`）⇒ 某段没跑到时后一段
    #   取 `_hit` 就 `KeyError`、**崩在报红之前**。只验「不崩」不验产出：`doc_fail` / `failures`
    #   都传**局部空 list**，不污染真实判据（默认值下多出来的无关红忽略）。
    if not _ABSENT_S_PROBE[0]:
        _ABSENT_S_PROBE[0] = True
        # 静音：探针会真跑一遍本段（含 `[ok]` 打印）⇒ 不静音会把那些行重复打进 stdout。
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _docs_tail_scaffold({"tmp": tmp, "node": _S.get("node"),
                                     "failures": [], "write": _S.get("write", True),
                                     "docs": docs, "root": root, "doc_fail": []})
        except Exception as _ab_exc:  # noqa: BLE001 —— 崩了就是崩了，必须报红
            doc_fail.append("跨段变量缺席导致崩溃 —— `_S` 必须有默认值（%s: %s）"
                            % (type(_ab_exc).__name__, _ab_exc))
        finally:
            _ABSENT_S_PROBE[0] = False

    # 17n frontmatter description 的**触发场景下限**：少一条锚点就失败
    #     （description 是路由真正读的字段，瘦身时最容易顺手删掉的就是触发词）。
    #     起因：description 是路由真正读的字段，瘦身时最容易顺手删掉触发词 —— 少一条锚点，对应场景就路由不到本 skill。
    _skfm = _sk_txt.split("---")[1] if _sk_txt.startswith("---") else ""
    # ⚠️ 取段必须走 `_desc_block`（按行扫描）：description 若是 frontmatter **最后一个键**，
    #    「下一行是顶格键」的正则取不到 ⇒ `_dsc` 为空 ⇒ 13 个锚点全被判丢（假红）。
    _dsc = _desc_block(_skfm)
    _lost = [t for t in _trig if t not in _dsc]
    if _lost:
        doc_fail.append("SKILL.md 的 description 少了触发场景锚点：%s" % _lost)
    if len(_skfm) > 900:
        doc_fail.append("SKILL.md 的 frontmatter 已 %d 字符，超过 900 的护栏（平台上限 1024）"
                        % len(_skfm))

    # 17o `controlsold.json` 不得被当成注册表（`discover_controls` 只认 controls.json）
    #     起因：目录里可能并存 controls.json 与 controlsold.json；若把后者当注册表，推断出的控件会失真却看不出（故真跑一次钉住）。
    _probe = os.path.join(tmp, "regprobe", "a", "b")
    os.makedirs(os.path.join(_probe, "system"), exist_ok=True)
    with open(os.path.join(_probe, "system", "controlsold.json"), "w", encoding="utf-8") as _fh:
        _fh.write("{}")
    if xwl.discover_controls(os.path.join(_probe, "page.xwl")) is not None:
        doc_fail.append("`discover_controls` 把 controlsold.json 当成注册表了")

    # 17p 依据层的内容守卫：`references/workflow-notes.md` 三臂全豁免（它记的就是"什么时候发现了什么"），
    #     所以它的内容必须另有几条**形式**约束 —— 否则豁免会把它慢慢变成编年垃圾场。
    #     判据只认**结构**（小节锚点 + 发版编年的格式），不判语义 —— 语义判据会引来误报。
    #     起因：依据层两文件享有编年三臂全豁免 ⇒ 必须另有形式约束，否则豁免会把它慢慢变成编年垃圾场。
    # ⚠️ 检查对象改「**主文件 及其拆出的依据层文件**」（本轮）：由 `_authority_files(root)` **动态**取全部
    #    依据层文件 —— 拆分后 workflow-notes 主 ＋ 其拆出的 guards 文件都在内（不再指名两份）。
    _auth_rels = _authority_files(root)
    _wn_rels = [r for r in _auth_rels if os.path.basename(r).startswith("workflow-notes")]
    _wn = "\n".join(_txt.get(r, "") for r in _wn_rels)
    _lack = [k for k in ("判据的因果", "已作废的做法", "编年纪律") if k not in _wn]
    if _lack:
        # ⚠️ 文案符实（本轮修正）：`_wn` 是 **workflow-notes 家族**（主文件 ＋ 其拆出的依据层文件）的
        #    拼接 ⇒ 红行不得再单指 `references/workflow-notes.md` 一份（该文件可能已不含被搬走的节）。
        doc_fail.append("依据层 workflow-notes 家族（%s）缺小节：%s"
                        "（依据层只放 因果 / 作废记录 / 编年纪律说明 三类）"
                        % ("、".join(_wn_rels), _lack))
    # ⚠️ 依据层是**多份**文件（measured-data 主＋4、workflow-notes 主＋1）—— 它们都享编年三臂豁免，
    #    所以都不得出现发版编年的格式，否则豁免迟早变成编年垃圾场。
    #    ⚠️ 本臂是**负面约束、最易漏**：漏改 ⇒ 拆出的新文件可合法携带编年格式（正是本臂要防的事）。
    for _bn in _auth_rels:
        _bt = _txt.get(_bn, "")
        if re.search(r"^##\s*\[", _bt, re.M) or re.search(
                r"^###\s+(Added|Changed|Fixed|Testing)\b", _bt, re.M):
            doc_fail.append("%s 里出现了**发版编年**的格式"
                            "（版本段 `## [x.y.z]` 或 Added/Changed/Fixed/Testing 小节）"
                            "—— 发版编年只许写在 CHANGELOG.md" % _bn)

    # 17q 实测数字禁令。
    # 起因：语料文件数、样本大小与命令耗时在正文、帮助和测试注释里各留副本时，
    # 任一处复采都会让同一事实出现多个现值。实测值只由 measured-data 家族承载；
    # CHANGELOG、metadata.update_history 与 tests/baseline.json 保留各自历史/基线用途。
    # 扫描面：分发包全树、主自检、tests 与 CI workflow；候选不按扩展名筛选，
    # 仅排除版本库与编译缓存目录。三类 token 逐类可注入。
    _measure_n, _measure_hits, _measure_face = _measurement_hits(root)
    for _face_problem in _measure_face:
        doc_fail.append("17q 扫描面不完整：%s" % _face_problem)
    for _mrel, _mline, _mlabel, _mtok, _mtext in _measure_hits:
        doc_fail.append("%s:%d 含实测数字「%s」（%s）：只许留在 measured-data 账本、"
                        "CHANGELOG、metadata.update_history 或基线文件"
                        % (_mrel, _mline, _mtok, _mlabel))
    for _regression in _measurement_regression_failures():
        doc_fail.append("17q 数字禁令回归失败：%s" % _regression)
    if not _measure_hits and not _measure_face:
        print("[ok]  17q 实测数字禁令：扫描 %d 个文件；语料数/样本大小/耗时只由账本、"
              "历史段与基线承载" % _measure_n)

    # 17u 层归属声明：`references/` 下**每一份** md 在 `metadata.json` 的 `layers` 里**恰有一条**、
    #     值 ∈ {`spec`, `evidence`}；`layers` 里不得有 `references/` 以外的键、也不得指向不存在的文件。
    #     起因（不这么做会漏什么）：编年豁免面（`17l`）与引用权威面（`17p`）都按 `layers[rel] == "evidence"`
    #     机械选取 —— 条目缺失 / 值写错时那些守卫会**静默选错对象**（漏扫或误红），而单看它们的绿行看不出来，
    #     故把「条目齐不齐、值合不合法、有没有多出来的键」单列一块钉住。
    #     ⚠️ 扫描面**动态**取（遍历 `references/` 实际文件），⛔ 不许写死清单 —— 否则新文件对本块又静默隐形。
    #     ⚠️ 本条**只认** `metadata.json`：层归属的唯一真源在那一处（各份参考材料的首行声明已删），
    #       故这里不再读任何正文首行。
    #     ⭐ **判定补强（堵「自授豁免」）**：光判「值合法」不够 —— 把某份**规格层**文件的 `layers` 值改成
    #       `evidence` 即可悄悄拿到编年三臂全豁免。故 `evidence` 须有**结构佐证**：stem 落在 `_AUTH_STEMS`
    #       （依据层家族前缀）内，否则**判红**。家族内加文件无需改代码（登记驱动）；给无关文件开豁免须显式改代码。
    #     ⚠️ 已知边界（如实登记，不当已覆盖）：JSON 对象键唯一性由解析器保证（重复键**后者胜**）⇒
    #       「同一 rel 写了两次」不会红；能漏掉的只有「先写错值、再写对值」这种**结果正确**的情形。
    _b1_files = _refs_md(root)
    _b1_lay = _layers_map(root)
    if not _b1_files:
        doc_fail.append("17u 层归属声明：列不出 references/ 下的文件 ⇒ 本项无法判定，判红")
    elif _b1_lay is None:
        doc_fail.append("17u 层归属声明：metadata.json 的 `layers` 读不出 / 不是对象 / 有非法值"
                        "（须为 `{\"references/<文件名>\": \"spec\"|\"evidence\"}`，两个字面量之一）"
                        "⇒ 本项无法判定，判红")
    else:
        _b1_bad = [_r for _r, _fp in _b1_files if _b1_lay.get(_r) not in _DECL_LAYER]
        _b1_fake = _auth_layer_misfits(root)
        _b1_seen = {_r for _r, _fp in _b1_files}
        _b1_extra = sorted(_k for _k in _b1_lay if _k not in _b1_seen)
        if _b1_bad:
            doc_fail.append("17u 层归属声明：这些文件在 metadata.json 的 `layers` 里缺条目（或值不在 "
                            "spec/evidence 内）：%s" % _b1_bad[:12])
        if _b1_extra:
            doc_fail.append("17u 层归属声明：`layers` 里有 %d 个多出来的键（不指向 references/ 下实际存在的 "
                            "`.md` —— 多是已删文件残留或笔误）：%s" % (len(_b1_extra), _b1_extra[:12]))
        if _b1_fake:
            doc_fail.append("17u 层归属声明：这些文件在 `layers` 里登记为 `evidence` 但 stem 不属于任何依据层家族"
                            "（%s）⇒ 不予豁免（给无关文件开豁免须显式改代码 `_AUTH_STEMS`）：%s"
                            % ("、".join(_AUTH_STEMS), _b1_fake[:12]))
        if not (_b1_bad or _b1_fake or _b1_extra):
            print("[ok]  17u 层归属声明：references/ 下 %d 份在 metadata.json 的 `layers` 里均恰有一条、"
                  "值为 spec/evidence（evidence 均有家族结构佐证）" % len(_b1_files))

        # 起因：依据层单件过长会突破按需读取成本，新增家族成员也须受约束。
        # 8 000 ＝ 5 000 tokens × 1.61 字符/token ＝ 8 050，向下取整（取更严一侧）。
        # 依据：业界对 SKILL.md 的建议 ≈5k tokens（agentskills.io／Microsoft Learn 的 500 行口径）
        for _ev_rel in (_r for _r, _layer in _b1_lay.items() if _layer == "evidence"):
            try:
                with io.open(os.path.join(root, _ev_rel), encoding="utf-8", newline="") as _ev_fh:
                    _ev_chars = len(_ev_fh.read())
            except (OSError, UnicodeError) as _ev_exc:
                doc_fail.append("依据层字符上限：%s 读不出（%s）" % (_ev_rel, _ev_exc))
            else:
                if _ev_chars > 8000:
                    doc_fail.append("依据层字符上限：%s 为 %d 字符，超过 8000" % (_ev_rel, _ev_chars))
    # 17r 分发面自包含：扫描面（`git ls-files` ∪ 磁盘新增未跟踪，见 `_git_scan_scope`）里不得出现
    #     「指向 skill 包外」的引用。
    #     判据 = 包外文档名（四种，见下方 _b17r_docs 元组）
    #          + 外部计划文档的条目代号（**已知形态**：单字母-数字 ／ 字母-短横-数字 ／ 单字母-短横-小写字母，
    #            以及原「SITE ＋ 数字」形态）+ §N-M 形式的节号指针。
    #          + 前置批次号（PRE 加数字）与过程角色编号（eng-/qa-/pm-/arch-/reg-/tl- 加数字）。
    #     `.py` 只在**字符串字面量之外**判（词法掩码），免得把夹具/文案里的代号当残留。
    #     无短横那一半**只收单字母** ⇒ **已收窄的假阳性面（无短横的多字母缩写）**不误抓；
    #       带短横那一半仍覆盖多字母；另有一支「单字母 ＋ 短横 ＋ 单个小写字母」，右侧界定符只排除「点 ＋ 词字符」⇒ 带扩展名文件名不误抓、句末 ASCII 句点仍判。
    #     两处**按语义**的豁免（非逐文件 / 逐条名单）：`CHANGELOG.md` 整体（历史记录）；`metadata.json`
    #       的 `update_history` 段（**同属历史记录语义**，按段跳过、其余字段仍判）＋ **字符编码名词形**一类。
    #     ⚠️ 起因：说明文字本身也在扫描面内 ⇒ 注释里不得出现被禁字面量，否则守卫会把自己判红。
    # 有界下沉：`_b17r_docs` / `_b17r_code` / `_b17r_code_ok` / `_b17r_sec` / `_b17r_proc` 已移出函数体 ⇒ 见模块级同名常量。

    # 有界下沉：`_b17r_mask_strings` / `_b17r_history_skip`（纯助手）已移出函数体 ⇒ 见模块级同名函数。
    # B1 迁入：判定逻辑已迁入 `contract_scanner.guard_dist_selfcontained`；判据表/助手、`_git_scan_scope`、
    #   `_docs_git_arm` 均由本文件注入（保持单一真源、结果逐条等价）。
    _cs_17r = _load_contract_scanner()
    if _cs_17r is None:
        doc_fail.append("17r 分发面自包含：contract_scanner 加载失败 —— 报错，不算通过")
    else:
        _cs_17r.guard_dist_selfcontained(
            root, doc_fail, _nogit_arms, _SUBCHECKS, "17r 分发面自包含",
            b17r_docs=_b17r_docs, b17r_code=_b17r_code, b17r_code_ok=_b17r_code_ok,
            b17r_sec=_b17r_sec, b17r_proc=_b17r_proc,
            mask_strings=_b17r_mask_strings, history_skip=_b17r_history_skip,
            git_scan_scope=_git_scan_scope, docs_git_arm=_docs_git_arm,
            ok_print=lambda _files: print(
                "[ok]  17r 分发面自包含：%d 个分发文件里无包外引用"
                "（无《验收基线》/《落地清单》/施工索引/施工单、无施工单条目代号（**A–L 单字母**-数字 ／ 字母-短横-数字〔任意 1–3 个字母〕／ **A–L 单字母**-短横-小写字母 形态）、"
                "无 §N-M 形式的节号指针、无前置批次号/过程角色编号；"
                "`.py` 只判字符串字面量之外；CHANGELOG 整文件 ＋ 历史记录段 ＋ 编码名词形豁免）"
                % len(_files)))

    _check_docs_section_order(failures)

    # ⚠️ 破计数遮蔽（本轮仪表审计整改）：判**每个块名份数不降 ＋ 新增块名须在 `CHANGELOG` 声明**。
    #   起因与"如何有意增删块时更新基线"见模块级 `_DOC_GUARD_BLOCK_BASE` 的注释。
    _blk_bad = _doc_guard_block_mismatch()
    if _blk_bad:
        doc_fail.append(_blk_bad)

    # 函数体行数上限：判据本体在模块级 `_fn_cap_check`（⛔ 不许内联回函数体 —— 那会让判据住在
    #   被它自己限制的函数里，往这段加一行就顶穿自己的上限）。
    for _suite_name in sorted(os.listdir(_SUITE_DIR)):
        if _suite_name.endswith(".py") and _suite_name != "__init__.py":
            _load_suite(_suite_name[:-3])
    _fn_cap_check(doc_fail)

    if doc_fail:                # ⚠️ 截断必须显式（不说"还有 N 条"⇒ 读者以为"就这些"）。⛔ 别再加行。
        failures.extend(doc_fail[:12] + (["文档守卫：另有 %d 条失败**未展开**（上面只列前 12 条）" % (len(doc_fail) - 12)] if len(doc_fail) > 12 else []))
    else:
        # 非 git 时把"没跑的臂"**显式标在汇总大绿行上**（由上方两处分支收集的 `_nogit_arms`）。
        #   ⚠️ 该句现在**只在 `--allow-nogit` 降级路径下**才可能非空 —— 默认非 git 已判红、走不进本分支。
        _nogit_suffix = ("　（⚠️ **本次 %s 未执行：无 git** —— 臂依赖 `git ls-files`，"
                         "`--allow-nogit` 已降级；不计入通过）" % " / ".join(_nogit_arms)
                         ) if _nogit_arms else ""
        # ⚠️ 打印**实际**份数 / 基线（不取基线常量当分子）：新增基线外块后仍能看出真实块数。
        _blk_total = sum((_doc_guard_block_ids() or {}).values())
        print("[ok]  文档守卫：实际 %d / 基线 %d 块（每个块名份数不降；基线外新块须在 CHANGELOG 独立提及）"
              "—— 任意两文档间无重复表格 / "
              "编号·章·步·节号引用可解析（含跨文件）/ "
              "链接存在 / 外移点两侧都在 / 格式五项（表格·跳级·代码块·行尾·末尾）/ 自称数字一致 / "
              "导航表与目录索引一致 / 无业务路径残留 / 反模式有入口 / "
              "**编年三臂（事件词·施工日期·发版号）** / **scripts 里的点名式引用可解析** / "
              "**触发场景锚点未丢** / 注册表不认 controlsold / **依据层只放因果·作废·守卫说明** / "
              "**实测数字禁令（语料数·样本大小·命令耗时）** / **`--help` 行数上限（顶层 36 / 子命令实测+5）** / "
              "**支持矩阵 OS 行（SKILL 适用范围表 + metadata.json limitations）** / "
              "**跨文件节号指针可解析（17j-12）** / **目录顺序与实际小节一致（17j-13）** / "
              "**围栏块输出文案符实（17j-14）** / **行号锚点四形（现值面 0 命中）** / "
              "**目录条目完整性（每个 `##` 级小节至少一条；有意不进目录的走模块级豁免清单）**"
              % (_blk_total, sum(_DOC_GUARD_BLOCK_BASE.values()))
              + _nogit_suffix)

    # ---- 18. SKILL.md 必须声明平台边界、调用入口与规模约束 ----
    # 起因：SkillHub TRACE 评测的 adaptability 维给了这两个子项低分 ——
    # 「未明确声明仅适用 WebBuilder 平台」「未说明输入文件大小等性能约束」「普通用户不知道从哪儿调」。
    # 这几行很容易在后续精简文档时被删掉，所以钉成断言。
    b_fail: list[str] = []
    if "SKILL.md" in docs:
        body = "\n".join(docs["SKILL.md"])
        if "WebBuilder" not in body or not re.search(r"不适用|仅适用|仅支持", body):
            b_fail.append("SKILL.md 未声明平台边界（需同时出现 WebBuilder 与「不适用/仅适用」）")
        if not re.search(r"^##\s*怎么用", body, re.M):
            b_fail.append("SKILL.md 缺少「怎么用」小节（调用入口）")
        if "scripts/xwl.py" not in body:
            b_fail.append("SKILL.md 的「怎么用」未给出命令行入口（scripts/xwl.py）")
        if not re.search(r"KB|MB", body):
            b_fail.append("SKILL.md 未声明输入规模约束（应给出实测文件大小量级）")
        # frontmatter 有长度上限（平台侧 1024）：description 是路由真正读的字段，
        # 每次往里补触发词都在吃这个额度 —— 实测写全触发词时到过 **1029**、当前 **839**，
        # 是靠人工量出来的。钉住：description 与整个 frontmatter 块都必须留余量。
        _fm = body.split("---")[1] if body.startswith("---") else ""
        # ⚠️ 取段必须走 `_desc_block`（按行扫描）：正则取不到时 `_dlen` 会是 0，
        #    `0 > 1024` 恒假 ⇒ 这条护栏会**静默失效**（假绿），比假红危险得多。
        _dlen = len(_desc_block(_fm))
        if _dlen > 1024:
            b_fail.append("SKILL.md 的 description %d 字符，超过 1024 上限" % _dlen)
        if len(_fm) > 1024:
            b_fail.append("SKILL.md 的 frontmatter 块 %d 字符，超过 1024 上限" % len(_fm))
        # 打包声明：SkillHub 的平台评测读这几样。缺了就会在"必需文件 / 能力声明"上扣分，
        # 而它们都是**内容侧**可控制的（`_meta.json` 不是 —— 那是平台在发布时生成的，
        # CLI 源码 `_is_junk_zip_path()` 明确把 `_meta.json` 排除在内容哈希之外）。
        if not os.path.isdir(os.path.join(root, "examples")):
            b_fail.append("缺少 examples/ 目录（平台评测的「示例充分性」会扣分）")
        _mjp = os.path.join(root, "metadata.json")
        if not os.path.exists(_mjp):
            b_fail.append("缺少 metadata.json（平台评测读它拿能力/边界声明）")
        else:
            try:
                _md = json.load(open(_mjp, encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                b_fail.append("metadata.json 不是合法 JSON：%s" % exc)
            else:
                _miss = sorted(_META_REQUIRED_FIELDS - set(_md))
                if _miss:
                    b_fail.append("metadata.json 缺字段：%s" % _miss)
        if "metadata:" not in body[:500]:
            b_fail.append("SKILL.md 的**前 500 字**内没有 `metadata:` 字段"
                          "（SkillHub 自检只看前 500 字，放 frontmatter 末尾不算）")
    if b_fail:
        failures.extend(b_fail)
    else:
        print("[ok]  SKILL.md 声明了平台边界、调用入口与规模约束")



def _check_docs_section_order(failures) -> None:
    # ---- 11k.（**归位**）SKILL.md 章节结构守卫（格式不变式，不写死章名）----
    #   ⚠️ 本块原**寄居**于 `_check_itemids`（itemids 块）——它判的是 **SKILL.md 的章节结构**，
    #     与 itemids 无关。`#10b③` 归位到**文档守卫侧**；旧标识 `11k` 保留（不重编，免动全库引用）。
    #   换判据：原来把某次的 9 个章名抄进两个模块级常量，布局一改就红，那是快照不是判据。
    #   改判四条格式不变式（章序是否被打乱不再由机器判，改由人工评审看）。
    # 带编号章的中文序号：按「一」到「二十」的整词匹配（长的在前，免得「十一」被拆成「十」）。
    # 超出这张表的序号（二十一及以上）匹配不到 ⇒ 不计入、序号也就不连续，照样判红。
    _cn = ["二十", "十九", "十八", "十七", "十六", "十五", "十四", "十三", "十二", "十一",
           "十", "九", "八", "七", "六", "五", "四", "三", "二", "一"]
    _seq = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
    skill_md = os.path.join(SKILL_ROOT, "SKILL.md")
    if os.path.exists(skill_md):
        with open(skill_md, "r", encoding="utf-8", newline="") as f:
            raw = f.read().splitlines()
        # ① 带编号的 `##` 章：中文序号从「一」起连续、不缺号、不重复。
        numbered = []
        for i, line in enumerate(raw):
            m = re.match(r"^## (%s)、" % "|".join(_cn), line)
            if m:
                numbered.append((i, m.group(1), line))
        got = [c for _, c, _ in numbered]
        want = _seq[:len(got)]
        bad = []
        if got != want:
            bad.append("带编号章的序号不从「一」连续（得到 %s）" % "".join(got))
        # ② 每个带编号的 `##` 后必有非空正文（≥1 行非空，且不是紧接另一个 `##`）。
        for i, _c, line in numbered:
            body = []
            for nxt in raw[i + 1:]:
                if nxt.startswith("## "):
                    break
                if nxt.strip():
                    body.append(nxt)
            if not body:
                bad.append("带编号章「%s」下面没有正文" % line.strip()[:24])
        # ③ 下限：带编号的 `##` 至少 5 个。出处：闭环至少需要「是什么／硬规则／怎么做／工具／收口」五段。
        if len(numbered) < 5:
            bad.append("带编号的 ## 章有 %d 个，少于 5 个" % len(numbered))
        # 上限：超过 10 个只提示、不阻断。「10」没有任何可引用的出处，写成阻断就是拿拍的数当判据。
        # ⛔ 上限不再当阻断；要给上限找出处才可恢复阻断。
        if len(numbered) > 10:
            _gate_note("SKILL.md 带编号章 %d 个，超过 10 —— 只提示、不阻断"
                  "（上限没有出处；要恢复阻断先给出处）" % len(numbered))
        # ④ 「单行源 vs 多行源」不得单列一章（应并入格式章）。
        if any("单行源" in t for t in raw if t.startswith("## ")):
            bad.append("「单行源 vs 多行源」应并入格式章，不该单列一章")
        if bad:
            failures.extend("SKILL.md 章节结构：%s" % b for b in bad)
        else:
            print("[ok]  SKILL.md 章节结构合规（序号连续、无空节、章数 ≥5）")
    else:
        print("[note] 未找到 SKILL.md，跳过章节结构守卫")







# 依赖执行器（node）的写前门禁断言：node 不可用时一条都不跑 ⇒ 尾部必须点名，⛔ 不许静默跳过。
# 标签＝验收判据编号；⚠️ 新增任何 `if node:` 都要同步本表，条数由下面的 parity 断言盯住。
















# `itemids` / `params` / `check ⑦` 的「控件注册表:」来源行 —— **未找到**分支的**手写**逐字期望。
#   起因（本轮仪表审计整改 ⑤：破可判定的自证循环）：若判据写成 `li != xwl.controls_source_line(None)`
#   就是拿**产出该行的同一个函数**当期望 ⇒ 构造性恒真（三点打印点全部调用该 helper，`li` 必等于它），
#   只能验到"三命令用了同一 helper"，**验不了来源行文案本身**。改成与**手写**文案比后，
#   文案被改坏（而三命令仍逐字一致）也会判红。


# ---- 金标：`expand` 的**固定点**样本（模块级字面量，⛔ 不放函数体内）----
#   ⭐ 为什么要有金标：现网的往返臂两端**同源** —— `expand` 排出来的版，再由 `expand` 判回自己，
#     同一处误解会同时体现在两端、往返仍然绿。金标是**冻结的独立文本**（就是本文件里的字面量），
#     实现侧任何"自圆其说"的改动都会在此显出**字节差异** —— 同源比对做不到这件事。
#   ⚠️ 本组证明的是**与金标一致**，⛔ 不是**与自身自洽**。
#   ⚠️ 形态一律取 `expand` 稳态形：`new` 造骨架 → `patch` 补成已知正确结构 → `expand` 跑一次
#     ⇒ 断言 `expand(金标) ≡ 金标` 是**固定点**判据（金标自己若不再是固定点，也会当场红）。
#   ⚠️ 来源：四份全部用本仓 `xwl.py new` ＋ `xwl.py patch` 现场生成，⛔ 未取任何真实工程语料
#     （无业务路径、无客户标识、无真实工程名）；`check` 全绿（①–⑦⑩ ＋ ⑧ 无异常）后才冻结。
#   ⚠️ 每份附**字节数与 md5**：人工核对金标有没有被误改；改一个字符 ⇒ 断言红、md5 也对不上。
#   ⚠️ 已知盲区（⛔ 别指望本臂抓）：金标被改成**另一份同样合规的形态**（值改了但仍是稳态形）时，
#     固定点判据照样绿 ⇒ 那一路只能靠注释里的 md5 与人工评审。**改金标必须同时改注释里的 md5**。
# 来源：`new --kind page --title 金标页面`；形态：expand 稳态形（LF、无末尾换行、顶层七键按设计器序）；238 B；md5 aeb4a7962eb3d19cf248894cb6b1c14c
# 来源：`new` 骨架 ＋ `patch` 追加 panel／两个 button；形态：expand 稳态形；689 B；md5 07e1d7aa0e0430be19ee9d2ffdfc79c2
# 来源：`new` 骨架 ＋ `patch` 追加 viewport／grid／store／columns（两列）／panel／带 click 的 button；形态：expand 稳态形；1751 B；md5 5e919173677c839ae79c8a16b86e4c73
# 来源：`new` 骨架 ＋ `patch` 追加 form／两个 field（textfield 与 textarea）；形态：expand 稳态形；762 B；md5 29a5ce9346d4a72852b1617aa850b59e


# ---- 金标（续）：把**旧的两组往返臂**从"自己判自己"换成**对金标** ----
#   ⭐ 旧臂的 oracle 是被测实现自己，所以**判别力≈0**：
#     · `-0.0` 那条只断言 `expand` 的 **rc==0**（`_check_basics` 内）—— rc 由**同一份** `expand` 决定
#       ⇒ 只要"序列化"与"等价判定"**同向**误解（一起把 `-0.0` 当 `0`），它就照样 rc=0、照样绿。
#       ⚠️ 实测边界（⛔ 别把本臂说成"救单点注入"）：**单点**注入（只折叠负零、等价判定仍严）会让
#       `expand` 自判 `rc=2` ⇒ 那种情形**旧臂也会红**；本臂的增量在"同向误解"与"语义等价但字节变了"
#       （排版／写法）这两类上 —— 同向两点注入实测 `rc=0`、产出 `{"n": 0}`、旧臂全绿。
#     · `1.0`/`0.0` 那条把产出**再解析回来**跟手写期望比（`equivalent(parse_xwl(written), {...})`）
#       —— 解析器与序列化器是同一份实现，同一处理解错时**两头一起错**，比完仍相等。
#   下面四份把标准答案换成**冻结文本**：实现怎么改都改不动它，一旦写的字节变了就当场红。
#   ⚠️ 形态＝该命令的**真正产出**：单行样本 `expand` 后**保持单行**（不强行展开）；多键对象展开成设计器多行。
# 来源：`{"n": -0.0}` 经 `expand` 原地处理（单行样本保持单行）；11 B；md5 a077aae283a230d0fc7b4c05193dfbb3
# 来源：`{"a": 1.0, "children": []}` 经 `expand`；形态：设计器多行稳态形；30 B；md5 47d25653e0bc087092d510b283139779
# 来源：`{"a": 0.0, "children": []}` 经 `expand`；形态：设计器多行稳态形；30 B；md5 5aa5e69fbd165596c143cd2892e8e987
# 来源：`{"a": 1.0, "title": "t", "children": []}` 经 `patch` 把 title 改成 t2；形态：设计器多行稳态形；46 B；md5 649f8b5cc7dfe307587a721b8167227e







def _check_basics(tmp, node, failures, write) -> None:
    return _suite_fn("basics", "_check_basics")(tmp, node, failures, write)


def _check_params_paths(tmp, node, failures, write) -> None:
    return _suite_fn("params_paths", "_check_params_paths")(tmp, node, failures, write)


def _check_itemids(tmp, node, failures, write) -> None:
    return _suite_fn("itemids", "_check_itemids")(tmp, node, failures, write)


def _check_patch_contract(tmp, node, failures, write) -> None:
    return _suite_fn("patch_contract", "_check_patch_contract")(tmp, node, failures, write)


def _check_subcommands(tmp, node, failures, write) -> None:
    return _suite_fn("subcommands", "_check_subcommands")(tmp, node, failures, write)


def _check_new_guards(tmp, node, failures, write) -> None:
    return _suite_fn("new_guards", "_check_new_guards")(tmp, node, failures, write)


def _check_platform(tmp, node, failures, write) -> None:
    return _suite_fn("platform", "_check_platform")(tmp, node, failures, write)


def _check_write_failures(tmp, node, failures, write) -> None:
    return _suite_fn("write_failures", "_check_write_failures")(tmp, node, failures, write)


def _check_edit_eol(tmp, node, failures, write) -> None:
    return _suite_fn("edit_eol", "_check_edit_eol")(tmp, node, failures, write)


def _check_eol_and_guards(tmp, node, failures, write) -> None:
    return _suite_fn("eol_and_guards", "_check_eol_and_guards")(tmp, node, failures, write)


def _check_diffguard(tmp, node, failures, write) -> None:
    return _suite_fn("diffguard", "_check_diffguard")(tmp, node, failures, write)


def _check_bc_contract(tmp, node, failures, write) -> None:
    return _suite_fn("bc_contract", "_check_bc_contract")(tmp, node, failures, write)

def _blocks() -> list[tuple[str, object]]:
    """按**固定顺序**列出全部自检块（块名 → 函数）。

    该顺序 = 输出顺序（父进程末尾按此顺序汇总失败），也 = `--jobs` 并行的派发顺序。
    """
    return [
        ("basics", _check_basics),
        ("params_paths", _check_params_paths),
        ("itemids", _check_itemids),
        ("patch_contract", _check_patch_contract),
        ("subcommands", _check_subcommands),
        ("new_guards", _check_new_guards),
        ("docs", _check_docs),
        ("platform", _check_platform),
        ("write_failures", _check_write_failures),
        ("edit_eol", _check_edit_eol),
        ("eol_and_guards", _check_eol_and_guards),
        ("diffguard", _check_diffguard),
        ("bc_contract", _check_bc_contract),
    ]


# 自检块名基线：`_blocks()` 里那一组名字（即 `--list-blocks` 的输出）的**机器基线**。
#   起因（不这么做会漏什么）：`_blocks()` 只是"定义序"的清单 —— 删掉一个块 ⇒ 该块**连同它的
#     全部判据一起消失**，而剩下的块照旧全绿、汇总行照样 `ALL OK` ⇒ **整块删除没有任何守卫会响**
#     （与文档守卫那一族同病；那族已由 `_DOC_GUARD_BLOCK_BASE` 治过，本清单治的是**自检块**这一层）。
#   判据：① **少一块** ⇒ 红并**点名缺哪个**（丢块必须响；确系有意退役时改本基线并在 `CHANGELOG` 写明）；
#     ② **多一块** ⇒ 基线外的名字必须已在 `CHANGELOG.md` 被**独立提及**，否则红（新增＝显式；口径同
#     文档守卫那一族 —— 已声明的新块**放行**，否则谁都加不了块）；
#     ③ 只换块内实现、块名不动 ⇒ 绿（⛔ 别把正常重构判红）。
#   ⛔ **块序也是基线的一部分**：块序 ＝ 输出序，重排会让"拆分前后逐行 diff 为空"的对照失效。
#   📌 有意增删块时：先改 `_blocks()`，再按 `--list-blocks` 的输出**重抄**本清单（⛔ 别手抄）。
_BASELINE_BLOCKS_DATA, _BASELINE_BLOCKS_ERR = _baseline_read()
if _BASELINE_BLOCKS_ERR is None and not (
        isinstance(_BASELINE_BLOCKS_DATA.get("blocks"), list) and _BASELINE_BLOCKS_DATA.get("blocks")):
    _BASELINE_BLOCKS_ERR = "empty:blocks"
# ⚠️ 基线不可用 ⇒ **空清单 + 错误标记**（不再 `or _blocks()` 自举）：由 `_blocks_baseline_problem` 显式判红。
_BLOCKS_BASELINE = list((_BASELINE_BLOCKS_DATA or {}).get("blocks") or [])


def _blocks_baseline_problem():
    """把 `_blocks()` 的块名集合/顺序与基线比对；通过 ⇒ `None`，否则返回一句可打印的原因。"""
    if _BASELINE_BLOCKS_ERR is not None:
        return ("自检块基线**不可用**（%s）⇒ 无法比对，判红（⛔ 不回退当前 `_blocks()` 自举当通过）。"
                "请修复/重建 `%s`（维护者用 `--write-baselines` 显式生成）。"
                % (_BASELINE_BLOCKS_ERR, _BASELINE_PATH))
    _cur = [n for n, _f in _blocks()]
    _base = list(_BLOCKS_BASELINE)
    _miss = [n for n in _base if n not in _cur]
    if _miss:
        return ("自检块少于基线：缺 %s —— 有自检块被整块删掉 / 从 `_blocks()` 摘除"
                "（丢块必须响）。确系**有意退役**时，按 `--list-blocks` 现取重抄 `_BLOCKS_BASELINE`，"
                "并在 `CHANGELOG.md` 写明退役项与被撤下的判据。" % "，".join(_miss))
    _extra = [n for n in _cur if n not in _base]
    if _extra:
        try:
            with open(os.path.join(SKILL_ROOT, "CHANGELOG.md"),
                      encoding="utf-8", newline="") as _cf:
                _cl = _cf.read()
        except OSError as _exc:
            return ("自检块多了基线外的 %s，但读不出 `CHANGELOG.md`（%s）—— 判红"
                    % ("，".join(_extra), _exc))
        # ⚠️ 声明必须写成**反引号包裹**（`` `块名` ``）：词边界匹配**太松** —— 本文件很大，
        #   一个叫 `patch`／`platform`／`schema` 的新块名会在正文里随便撞到，等于"零门槛声明"。
        _und = [n for n in _extra if ("`%s`" % n) not in _cl]
        if _und:
            return ("新增了**未在 `CHANGELOG.md` 声明**的自检块：%s —— 新增＝显式"
                    "（写一行含 `` `该块名` ``（反引号包裹）的话即可；词边界不算，"
                    "否则常见单词会白送声明）。" % "，".join(_und))
        # ⚠️ 已声明的新块**放行**，但**基线名之间的相对顺序仍要判** —— 否则"加一个新块 ＋ 顺手重排
        #   既有块"会从这条分支静默溜过去（块序 ＝ 输出序，重排同样会让逐行 diff 对照失效）。
        _proj = [n for n in _cur if n in _base]
        if _proj != _base:
            return ("自检块**顺序**与基线不一致（块序 ＝ 输出序，重排会让逐行 diff 对照失效）："
                    "按基线名投影后为 %s" % "，".join(_proj))
        return None
    if _cur != _base:
        return ("自检块**顺序**与基线不一致（块序 ＝ 输出序，重排会让逐行 diff 对照失效）：现序 %s"
                % "，".join(_cur))
    return None


# `--fast` 跳过的两块：最贵、且与「编辑动作」无直接关系（本地快回路让位给速度）。
FAST_SKIP = ("diffguard", "eol_and_guards")


def _rmtree_force(path: str) -> None:
    """尽力删除临时目录：Windows 上只读/被占用的件先 chmod 再删；删不掉也**不抛**。"""
    def _onerr(func, p, exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_onerr)     # 3.12+ 新签名
    else:
        shutil.rmtree(path, onerror=_onerr)   # 3.9–3.11 只有 onerror


def _activate_block(name: str) -> dict:
    """给即将执行的块挂上一份子检查表，并让已加载套件看见它。"""
    checks = _fresh_subchecks(name)
    global _SUBCHECKS
    _SUBCHECKS = checks
    mod = _SUITE_MODULES.get(name)
    if mod is not None:
        mod.REQUIRE_ALL = REQUIRE_ALL
        mod.REQUIRE_PROFILE = REQUIRE_PROFILE
        mod._SUBCHECKS = checks
        mod._mark_sub = _mark_sub
    return checks


def _close_block(name: str, failures, checks: dict) -> dict:
    """块函数返回后收口。整块跑完才把 block 收成通过或失败。

    其余仍是「未选择」的子检查表示没执行到，记成未完成。
    提前 return 因此不能靠块级 rc=0 变成通过。
    """
    block = checks.get("block")
    if block is not None and block.get("state") == "未选择":
        if failures:
            _mark_sub(checks, "block", "失败", "断言失败 %d 条" % len(failures))
        else:
            _mark_sub(checks, "block", "通过", "已执行")
    for sid, cur in list(checks.items()):
        if sid != "block" and cur.get("state") == "未选择":
            _mark_sub(checks, sid, "未完成", "子检查未执行到")
    return _block_record(name, failures, checks)


def _run_block(name: str, fn, node):
    """在**独占**临时目录里跑一个块，返回 `(failures, record)`。

    每块独占一个 `mkdtemp`（并行时天然隔离；串行档也用它 ⇒ 两档语义一致，
    互不依赖 tmp 中的文件）。跑完删临时目录（失败也不抛）。
    """
    tmp = ""                    # 先占位：`mkdtemp` 进 try 之后，失败路径也拿得到"还没建"这个事实
    failures: list[str] = []
    checks = _activate_block(name)

    def write(nm: str, text: str, bom: bool = False) -> str:
        p = os.path.join(tmp, nm)
        with open(p, "wb") as f:
            if bom:
                f.write(b"\xef\xbb\xbf")
            f.write(text.encode("utf-8"))
        return p

    try:
        # ⚠️ `mkdtemp` 也必须在 try 里：建临时目录失败（配额／权限）时，串行档会**整进程崩、
        #   无 `[FAIL]`、无汇总行** —— 与"块内抛异常"是同一个可观测性病根，只修一半等于没修。
        tmp = tempfile.mkdtemp(prefix="xwl_selftest_%s_" % name)
        fn(tmp, node, failures, write)
    # ⛔ `try/finally` 少了 `except` ⇒ 块内抛出的异常会**穿透** `_run_serial`／`main`：
    #   `failures` 里已收集的内容与**汇总行**都不打印，现场只剩一个 `rc≠0` 且没有任何解释。
    #   `SystemExit` 属 `BaseException`（`except Exception` 也接不住）⇒ 必须单独接一支。
    #   ⚠️ 兜底**只负责让它可读**，⛔ 不许把异常改判成通过。
    #   ⚠️ 文案**不写"子进程"、也不编一个 rc**：串行档（`--jobs 1`）里根本没有子进程，
    #     写"子进程异常退出（rc=1）"是假话（`SystemExit(0)` 更会打出"rc=0"这种自相矛盾的串）。
    except SystemExit as exc:
        failures.append("块 %s 内抛出 SystemExit（code=%s）—— 已记成失败，⛔ 不是通过"
                        % (name, exc.code))
    except KeyboardInterrupt:
        # Ctrl-C 必须还能打断：记成"块失败"再接着跑下一块，等于把中断变成"再按 N 次"。
        # 注入：在**子进程**里让块函数抛 KeyboardInterrupt，
        #   父进程连跑 3 次都看到子进程 rc=3，且该块**没有被记成通过**（异常原样抛出，
        #   不进 failures、不打印汇总行）。所以本支的行为是"中断整个自检"，不是"记成失败后继续"。
        #   夹具在施工临时目录的 seq7_child.py / seq7_parent.py，不进仓。
        raise
    except BaseException as exc:        # noqa: BLE001
        # 先留调用栈再记一行：只记 `type: msg` 时，`RecursionError`／`MemoryError` 这类
        #   "其实已经崩了"的情形会退化成一行可读的失败，后面 13 个块带着坏掉的共享状态继续跑，
        #   最终"FAIL 40 项"把"崩过"这件事埋掉。
        traceback.print_exc()
        failures.append("块 %s 内抛出 %s: %s" % (name, type(exc).__name__, exc))
        if isinstance(exc, (MemoryError, SystemError)):
            raise                       # 这两种不是"这个块失败"，是进程状态已不可信 ⇒ 交回上层
    finally:
        if tmp:
            _rmtree_force(tmp)      # ⛔ 不留 tmp（直接 return 的写法每跑一次漏一批）
    return failures, _close_block(name, failures, checks)


def _skipped_record(name: str, why: str) -> dict:
    """前置不满足、整块没跑。普通档仍叫未执行；门禁下记成未选择。"""
    checks = _fresh_subchecks(name)
    state = "未选择" if REQUIRE_ALL else "不适用"
    for sid in list(checks):
        _mark_sub(checks, sid, state, why)
    record = _block_record(name, [], checks)
    record["state"] = "未选择" if REQUIRE_ALL else "不适用"
    record["reason"] = why
    record["skipped"] = True
    return record


def _run_serial(blocks, node):
    """串行（`--jobs 1`）：按块顺序在**本进程**逐个跑。返回 `(failures, records)`。"""
    failures: list[str] = []
    records = []
    for name, fn in blocks:
        _pre = _BLOCK_PRECONDITIONS.get(name)
        if _pre is not None:
            _root, _why, _fatal = _pre()
            if _root is None and not _fatal:
                print("[note] 本块未执行：%s（%s）" % (name, _why))
                records.append(_skipped_record(name, _why))
                continue
        _fails, _rec = _run_block(name, fn, node)
        failures.extend(_fails)
        records.append(_rec)
    return failures, records


# ⭐ 并行派发时单块的**兜底超时**（秒）：worker 卡住 ⇒ 杀掉并**显式报失败**（⛔ 不静默跳过／通过）。
#   起因：外层注入器虽有超时，但**内层派发侧不能裸奔** —— worker 一旦卡死，`poll()` 永不返回，
#   整个自检**无界挂住**（本批正是治这个）。默认 1800s；可用环境变量 `XWL_SELFTEST_JOB_TIMEOUT`
#   覆盖（≤ 0 视为关闭兜底，退回旧的无界行为）。
_JOB_TIMEOUT = 1800
try:
    _JOB_TIMEOUT = int(os.environ.get("XWL_SELFTEST_JOB_TIMEOUT") or _JOB_TIMEOUT)
except ValueError:
    pass


def _as_subchecks(raw) -> dict:
    """把 worker 交回的子检查列表收成字典。形状不对的项丢掉，由上层判协议错。"""
    out = {}
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        out[item["id"]] = {
            "id": item["id"],
            "name": item.get("name") or item["id"],
            "state": item.get("state") or "未选择",
            "reason": item.get("reason") or "",
        }
    return out


def _take_worker_record(name: str, payload, proto_fail) -> dict:
    """校验一份 worker JSON。身份不对、字段缺失、坏形状都记成协议错。"""
    extra = []
    if not isinstance(payload, dict):
        extra.append("块 %s 的 worker JSON 不可用" % name)
        payload = {}
    got_id = payload.get("block_id")
    if got_id != name:
        extra.append("块 %s 的 worker JSON 身份不符（block_id=%r）" % (name, got_id))
    fails = payload.get("failures")
    if not isinstance(fails, list) or any(not isinstance(x, str) for x in fails):
        extra.append("块 %s 的 failures 不是字符串列表" % name)
        fails = []
    checks = _as_subchecks(payload.get("subchecks"))
    expected = [sid for sid, _nm in _BLOCK_SUBCHECKS.get(name, ())]
    missing = [sid for sid in expected if sid not in checks]
    if missing:
        extra.append("块 %s 缺子检查：%s" % (name, "、".join(missing)))
        for sid in missing:
            _mark_sub(checks, sid, "未完成", "worker 未交回该子检查")
    for sid, cur in checks.items():
        if cur.get("state") not in COMPLETION_STATES:
            extra.append("块 %s 的子检查 %s 状态非法：%r" % (name, sid, cur.get("state")))
            _mark_sub(checks, sid, "未完成", "worker 交回的完成状态非法")
    if payload.get("state") not in COMPLETION_STATES or not isinstance(payload.get("reason"), str):
        extra.append("块 %s 缺完成状态或理由" % name)
    record = _block_record(name, fails, checks)
    if extra or proto_fail:
        record["state"] = "未完成"
        record["reason"] = "；".join([x for x in [proto_fail, *extra, record.get("reason")] if x])
    record["_parent_failures"] = extra
    return record


def _aggregate_gate(records) -> tuple:
    """按注册块身份聚合。返回 `(rc, lines)`。

    缺块、重复、坏协议是 2。只有断言失败是 1。失败与未完成同时存在时仍是 1，两类都点名。
    """
    lines = []
    by_id = {}
    dup = []
    for rec in records:
        bid = rec.get("block_id")
        if bid in by_id:
            dup.append(bid)
        by_id.setdefault(bid, []).append(rec)
    if dup:
        lines.append("[require-all] 重复块：%s" % "、".join(dup))
    missing = [bid for bid in _BLOCKS_BASELINE if bid not in by_id]
    extra = [bid for bid in by_id if bid not in _BLOCKS_BASELINE]
    if missing:
        lines.append("[require-all] 缺块：%s" % "、".join(missing))
    if extra:
        lines.append("[require-all] 基线外的块：%s" % "、".join(extra))
    failed, undone, proto = [], [], []
    ordered = []
    for bid in list(_BLOCKS_BASELINE) + [bid for bid in by_id if bid not in _BLOCKS_BASELINE]:
        for rec in by_id.get(bid, []):
            ordered.append(rec)
            subs = "，".join("%s=%s" % (s.get("id"), s.get("state")) for s in rec.get("subchecks") or [])
            lines.append("[block] %s %s：%s%s" % (
                rec.get("block_id"), rec.get("state"), rec.get("reason"),
                ("；子检查 " + subs) if subs else ""))
            if rec.get("_parent_failures") or "worker" in str(rec.get("reason")):
                proto.append(bid)
            if rec.get("state") == "失败" or rec.get("failures"):
                failed.append(bid)
            elif rec.get("state") != "通过":
                undone.append(bid)
            for sub in rec.get("subchecks") or []:
                if sub.get("state") == "失败" and bid not in failed:
                    failed.append(bid)
                elif sub.get("state") in ("未完成", "未选择") and bid not in undone and bid not in failed:
                    undone.append(bid)
    if failed:
        lines.append("[require-all] 失败块：%s" % "、".join(dict.fromkeys(failed)))
    if undone:
        lines.append("[require-all] 未完成块：%s" % "、".join(dict.fromkeys(undone)))
    if failed:
        if undone:
            lines.append("[require-all] 同时有断言失败与未完成，按断言失败")
        return 1, lines
    if proto or missing or extra or dup:
        lines.append("[require-all] 门禁未完成：协议、缺块或重复")
        return 2, lines
    if undone:
        lines.append("[require-all] 门禁未完成")
        return 2, lines
    lines.append("[require-all] 必需范围已完整执行（profile=%s）" % REQUIRE_PROFILE)
    return 0, lines


def _run_parallel(blocks, node, jobs: int):
    """并发（`--jobs N`）：每块在**独立子进程**里跑（各自 mkdtemp、失败写 JSON）。

    ⭐ 子进程的 stdout / stderr **一律落「每块独立临时文件」，不再继承 selftest 自己的句柄**。
    起因：继承会让「worker 的**后代**」也持着 selftest 的 stdout/stderr —— 一旦 selftest 的
    stdout 被外层以**管道**收（注入门禁 / CI 都会），外层「杀掉 selftest 直子后等管道 EOF」就
    会**永久卡死**（后代不退 ⇒ 管道永不 EOF）。改为落文件后，**整条「后代持外管道」的链被切断**
    （与门禁侧「输出落临时文件、不靠管道」是同一条结构性思路）。
    父进程收齐后按**固定块顺序**把各块捕获的 stdout 原样回放到 stdout、stderr 原样回放到 stderr
    （两路**不合并**：合并会改变 stdout 的判据语义 —— 错误流里恰好含期望串就会误判通过）。

    ⇒ 并行档的**展示行不再丢失**（每块独占一个文件、无「多进程并发写同一句柄」的整行丢失），
    且**顺序固定为块定义序** ⇒ 展示部分与 `--jobs 1` **逐字同序**（非并发交错、逐次不同）。
    失败（`[FAIL]`）仍走"每块 JSON 文件、父进程回收"⇒ **失败永不丢**。父进程收齐后只按
    **固定块顺序**汇总打印 `[FAIL]`。
    ⭐ 内层兜底（本批新增）：单块超过 `_JOB_TIMEOUT` 秒未退出 ⇒ **杀掉该 worker 并把它
    记进 `[FAIL]`**（⛔ 既不跳过、也不通过）—— 免"worker 卡死 ⇒ 整个自检**无界挂住**"。
    """
    rdir = tempfile.mkdtemp(prefix="xwl_selftest_res_")
    try:
        return _run_parallel_dispatch(rdir, blocks, node, jobs)
    finally:
        _rmtree_force(rdir)     # ⛔ 不留结果目录（建完不清理的写法每跑一次漏一批）


def _run_parallel_dispatch(rdir: str, blocks, node, jobs: int):
    """`_run_parallel` 的本体：`rdir` 由调用方创建、由调用方的 `finally` 清理（本体不管生命周期）。"""
    procs: dict[str, tuple] = {}
    started: dict[str, float] = {}      # 各 worker 的启动时刻（monotonic）⇒ 内层兜底超时判据
    timed_out: set = set()              # 被兜底超时杀掉的块名（回放阶段**显式报失败**，⛔ 不静默跳过）
    _skipped_names = {}
    for name, _fn in blocks:
        _pre = _BLOCK_PRECONDITIONS.get(name)
        if _pre is None:
            continue
        _root, _why, _fatal = _pre()
        if _root is None and not _fatal:
            print("[note] 本块未执行：%s（%s）" % (name, _why))
            _skipped_names[name] = _why
    pending = [(n, f) for n, f in blocks if n not in _skipped_names]
    active: list[str] = []
    while pending or active:
        while pending and len(active) < jobs:
            name, _fn = pending.pop(0)
            result = os.path.join(rdir, name + ".json")
            # 本机启动器负责临时目录补丁，并让 worker 与父进程是同一份模块。
            # 没有启动器时仍直接跑本文件，CI 不受影响。
            _entry = os.environ.get("XWL_SELFTEST_ENTRY") or os.path.abspath(__file__)
            _cmd = [sys.executable, "-B", _entry,
                    "--only", name, "--result", result, "--node", node or ""]
            if ALLOW_NOGIT:   # 子进程各自解析开关 ⇒ 必须透传
                _cmd.append("--allow-nogit")
            if REQUIRE_ALL:
                _cmd.extend(["--require-all", "--profile", REQUIRE_PROFILE or ""])
            # ⭐ 诱因侧修复：worker 的 stdout/stderr 落**每块独立临时文件**（不继承 selftest 句柄，
            #   切断"worker 的后代持外管道"；详见本函数 docstring）。
            outlog = os.path.join(rdir, name + ".out")
            errlog = os.path.join(rdir, name + ".err")
            fout = open(outlog, "w", encoding="utf-8")
            ferr = open(errlog, "w", encoding="utf-8")
            # ⭐ 诱因侧加固（批2b·P1）：子进程编码**不带 strict** —— 显式 `utf-8:backslashreplace`。
            #   真实生效路径：`xwl.ensure_utf8_stdio()` 会对 stdout/stderr 做
            #   `reconfigure(errors="replace")` ⇒ **在它生效的路径上，本环境变量里的 `errors` 会被它覆盖**。
            #   ⇒ 所以这一行是**兜底（belt）**、**不是**修复一个可复现的崩溃：复验已实测，夹具（某块打印
            #   孤立 surrogate）下本块 `rc` 恒为 0、代理项一律变 `?`，**并不会崩**。
            #   保留理由：**万一某条路径没走到 `ensure_utf8_stdio()`**，这一行仍能避免"编码把块搞崩"。
            #   backslashreplace 只把**个别**字符转义，**能打印的照旧能打印**。
            proc = subprocess.Popen(
                _cmd, env={**os.environ, "PYTHONIOENCODING": "utf-8:backslashreplace"},
                stdout=fout, stderr=ferr)
            procs[name] = (proc, result, fout, ferr, outlog, errlog)
            started[name] = time.monotonic()
            active.append(name)
        time.sleep(0.1)
        _now = time.monotonic()
        for name in list(active):
            if procs[name][0].poll() is not None:
                active.remove(name)
            elif _JOB_TIMEOUT > 0 and started[name] + _JOB_TIMEOUT < _now:
                # ⭐ 内层兜底：worker 卡住 ⇒ 杀掉、**显式**记成失败（⛔ 不是跳过、不是通过）。
                #   外层注入器虽有超时，内层不能裸奔 —— 否则 `poll()` 永不返回、整块无界挂住。
                _p = procs[name][0]
                _p.kill()
                try:
                    _p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                timed_out.add(name)
                active.remove(name)

    failures: list[str] = []
    records = []
    for name, _fn in blocks:
        if name in _skipped_names:
            records.append(_skipped_record(name, _skipped_names[name]))
            continue
        proc, result, fout, ferr, outlog, errlog = procs[name]
        fout.close()
        ferr.close()
        if name in timed_out:
            # ⭐ 被兜底超时杀掉的块：其捕获输出**必然是截断的**（可能停在半个 `[ok]` 行）
            #   ⇒ 先在回放前出一条 `[note]`，免"画面先出一串 `[ok]`、再报 `[FAIL]`"的误导。
            print("[note] 块 %s 已被兜底超时终止（超过 %ss 未退出）⇒ 以下为**截断**的捕获输出，"
                  "不是该块的完整结果" % (name, _JOB_TIMEOUT))
        # ⭐ 按**块定义序**回放：stdout → stdout、stderr → stderr（两路**不合并**）。
        # ⭐ 回放**绝不静默丢弃**（批2b·P2）：按**字节**读，先**严格**解一次（仅用于探测）；
        #   解不动 ⇒ 用 `errors="replace"` **照常回放**，并**打印一行可见提示**点名是哪块、发生了什么。
        #   起因：worker 可能被信号杀在**半个多字节字符中间**，捕获文件尾部即为非法 UTF-8；
        #   原实现是 strict 读 ＋ `except: pass` ⇒ **整块的展示输出被静默丢弃**。
        #   ⚠️ 等价性：数据合法时 `errors="replace"` 与 strict **同一条解码路径**，且仍走**通用换行**
        #   （`newline=None`）⇒ 展示输出与改前**逐字节一致**。判据不受影响（failures 仍**只**据 JSON）。
        for path, sink, _lbl in ((outlog, sys.stdout, "stdout"), (errlog, sys.stderr, "stderr")):
            try:
                with open(path, "rb") as fh:
                    _raw = fh.read()
            except OSError as exc:
                print("[note] 块 %s 的 %s 展示输出读不到（%s）：%s"
                      % (name, _lbl, os.path.basename(path), exc))
                continue
            if not _raw:
                continue
            try:
                _raw.decode("utf-8")
                _undecodable = None
            except UnicodeDecodeError as exc:
                _undecodable = exc
            text = io.TextIOWrapper(io.BytesIO(_raw), encoding="utf-8",
                                    errors="replace").read()
            if _undecodable is not None:
                print("[note] 块 %s 的 %s 展示输出含非法/被截断的 UTF-8（%s）"
                      "⇒ 已按 U+FFFD 替换后照常回放；判据不受影响（failures 仍据 JSON）"
                      % (name, _lbl, _undecodable))
            try:
                sink.write(text)
            except Exception as exc:  # noqa: BLE001 —— 回放失败不得影响判据（failures 仍据 JSON 定）
                print("[note] 块 %s 的 %s 展示输出写不到目标流：%s" % (name, _lbl, exc))
        _proto_fail = None
        if name in timed_out:
            # ⭐ 超时块**显式报出**（⛔ 不静默）：点名块与超时值；worker 已杀 ⇒ **有界返回**。
            _proto_fail = "块 %s 的子进程超过 %d 秒未退出（worker 卡住）⇒ 已终止" % (name, _JOB_TIMEOUT)
            failures.append(_proto_fail)
        elif proc.returncode != 0:
            _proto_fail = "块 %s 的子进程异常退出（rc=%s）" % (name, proc.returncode)
            failures.append(_proto_fail)
        # ⭐ 超时块**必然写不出** JSON（worker 被杀在写盘前）⇒ 不再叠加一条误导的
        #   「失败清单读不到：No such file …」——只保留上面那条正确的超时 `[FAIL]`。
        _payload = None
        if not (name in timed_out and not os.path.exists(result)):
            try:
                with open(result, encoding="utf-8") as fh:
                    _payload = json.load(fh)
            except Exception as exc:  # noqa: BLE001
                _proto_fail = "块 %s 的失败清单读不到：%s" % (name, exc)
                failures.append(_proto_fail)
        _rec = _take_worker_record(name, _payload, _proto_fail)
        failures.extend(_rec.pop("_parent_failures", []))
        records.append(_rec)
    return failures, records


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="selftest.py", description="xwl.py 的自检（内置样本，不依赖外部 xwl 文件）")
    ap.add_argument("--jobs", type=int, default=None,
                    help="并行跑的自检块数（默认 min(6, CPU 数)；1 = 串行，做对照用）")
    ap.add_argument("--fast", action="store_true",
                    help="本地快回路：跳过最贵的两块（diffguard / eol_and_guards）")
    # 非 git 时**默认判红**（静默绿是病根，见模块级 `ALLOW_NOGIT` 的起因）；
    # 确无 `.git`（如 zip 分发解包后）时用本开关**显式**降级为"标注继续、rc 按其他项定"。
    ap.add_argument("--allow-nogit", action="store_true",
                    help="允许在无 .git 时降级（不因 3 族 git 门控守卫没跑而判红；默认无此开关即判红）")
    ap.add_argument("--require-all", action="store_true",
                    help="启用必需范围门禁。必须同时给 --profile；与 --fast/--only/--list-blocks/--allow-nogit 冲突")
    ap.add_argument("--profile", choices=REQUIRE_PROFILES, default=None,
                    help="必需范围口径。package 与 development 都把三处块内跳过当未完成")
    # `--only` / `--list-blocks` 面向人工最小子集回归（进 --help）；`--result` 供并行派发的子进程落 JSON
    # （人工单跑可不给 ⇒ 只跑并打印），`--node` 仍纯内部（不写进 --help）。
    ap.add_argument("--only", default=None, metavar="<块名>",
                    help="只跑指定自检块（最小子集回归）；块名用 --list-blocks 查。"
                         "未给 --result 时只跑并打印、不落 JSON")
    ap.add_argument("--write-baselines", action="store_true",
                    help="把当前自检块名与文档守卫块计数写入 tests/baseline.json（有意增删才用）")
    ap.add_argument("--list-blocks", action="store_true",
                    help="按定义序逐行打印全部自检块名后退出 —— 它们是自检块（供 --only 选），"
                         "不是 _check_docs 内部的 17b–17v 守卫编号")
    ap.add_argument("--result", default=None, metavar="<路径>",
                    help="把本次自检块的失败清单落成 JSON（并行派发的子进程用；人工单跑可不给）")
    ap.add_argument("--node", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    global ALLOW_NOGIT, REQUIRE_ALL, REQUIRE_PROFILE
    ALLOW_NOGIT = bool(args.allow_nogit)
    REQUIRE_ALL = bool(args.require_all)
    REQUIRE_PROFILE = args.profile
    _usage_conflicts = []
    if args.require_all and not args.profile:
        _usage_conflicts.append("--require-all 必须同时给 --profile package|development")
    if args.profile and not args.require_all:
        _usage_conflicts.append("--profile 必须与 --require-all 同时给")
    # `--result` 是父进程派发的内部 worker。它必须带着本块的 --only 与门禁开关，
    # 这个组合不是人工用法，不能按冲突拒绝。
    _worker = args.result is not None
    if args.require_all and not _worker and (args.fast or args.only or args.list_blocks or args.allow_nogit):
        _hit = [n for n, on in ((" --fast", args.fast), (" --only", args.only),
                                (" --list-blocks", args.list_blocks), (" --allow-nogit", args.allow_nogit)) if on]
        _usage_conflicts.append("--require-all 与%s 冲突" % "、".join(x.strip() for x in _hit))
    if _usage_conflicts:
        for _msg in _usage_conflicts:
            sys.stderr.write("[usage] %s\n" % _msg)
        return 2

    xwl.ensure_utf8_stdio()     # 输出全是中文；Windows 控制台默认非 UTF-8 会直接 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(line_buffering=True)     # 并行时每行一次原子写，不与其他子进程交错
    except Exception:           # noqa: BLE001
        pass

    # ⭐ 显式声明兜底被关闭（本仓判据：静默一律算缺陷）—— `≤ 0` 的语义（关闭）**不变**，只是不许静默。
    #    只在**顶层**进程打印一次（并行派生的 worker 带 `--result` ⇒ 跳过，免每块各重复一行）。
    if args.result is None and _JOB_TIMEOUT <= 0:
        print("[note] XWL_SELFTEST_JOB_TIMEOUT=%s（≤ 0）⇒ 并行派发的单块兜底超时**已关闭**："
              "worker 若卡死将**无界挂住**（退回旧行为）。" % _JOB_TIMEOUT, flush=True)

    # ---- `--list-blocks`：按定义序逐行打印自检块名（供 `--only` 选块）后退出 ----
    if args.write_baselines:
        _blks = [n for n, _f in _blocks()]
        _dg = dict(_doc_guard_block_ids() or {})
        os.makedirs(os.path.dirname(_BASELINE_PATH), exist_ok=True)
        with io.open(_BASELINE_PATH, "w", encoding="utf-8", newline="") as _bf:
            json.dump({"blocks": _blks, "doc_guard_blocks": _dg}, _bf, ensure_ascii=False, indent=2)
            _bf.write("\n")
        print("baseline written: %s（blocks=%d, doc_guard=%d）" % (_BASELINE_PATH, len(_blks), len(_dg)))
        return 0
    if args.list_blocks:
        _blk_named = _blocks()
        for _bn, _bf in _blk_named:
            print(_bn)
        sys.stderr.write(
            "[note] 以上 %d 个是**自检块**（`_blocks()` 定义序，供 `--only <块名>`）——"
            "区别于 `_check_docs` 内部的 `17b`–`17v` **守卫编号**（那些不是块名）。\n"
            % len(_blk_named))
        # ⚠️ 本清单同时被当作"重抄基线"的来源（见 `_BLOCKS_BASELINE` 的注释）⇒ 若当前状态与基线
        #   已不一致，必须**在这里也说一句**，否则维护者会照着这份"已漂移的清单"把基线抄歪
        #   （顺手把一次误删固化成新基线）。
        _lb_prob = _blocks_baseline_problem()
        if _lb_prob:
            sys.stderr.write("[warn] 本清单与 `_BLOCKS_BASELINE` **不一致**：%s\n" % _lb_prob)
        return 0

    # ---- 单跑模式（`--only <块名>`）：人工最小子集回归；`--jobs>1` 派生的子进程也走此入口 ----
    if args.only:
        _blk_named = _blocks()
        fn = dict(_blk_named).get(args.only)
        if fn is None:
            sys.stderr.write("未知自检块：%s\n" % args.only)
            sys.stderr.write("可用自检块（共 %d 个，按定义序）：%s\n"
                             % (len(_blk_named), "，".join(n for n, _f in _blk_named)))
            return 2
        if args.result is None:
            # 人工单跑：**不许静默收窄** —— 明写"只跑了哪块／未跑哪些块"（对齐"收窄必显式打印"的既有口径）
            _others = [n for n, _f in _blk_named if n != args.only]
            # ⚠️ 名单上限**必须 ≥ 块总数**（现 13 块）：上限过小时末尾的块只显示「另有 N 块未列」，
            #    「收窄必显式」在这条路径上等于失效。
            #    ⚠️ 两个数（切片与下面的判断）必须**同一来源**，否则会既列全又谎报"另有未列"。
            _NAME_CAP = 20
            _shown = "，".join(_others[:_NAME_CAP])
            if len(_others) > _NAME_CAP:
                _shown += "，另有 %d 块未列" % (len(_others) - _NAME_CAP)
            print("[note] 只跑了 `%s`：1/%d 块；未跑 %d 块：%s"
                  % (args.only, len(_blk_named), len(_others), _shown))
        _only_skip = None
        _pre = _BLOCK_PRECONDITIONS.get(args.only)
        if _pre is not None:
            _root, _why, _fatal = _pre()
            if _root is None and not _fatal:
                _only_skip = _why
        if _only_skip is None:
            failures, _only_record = _run_block(args.only, fn, args.node or None)
        else:
            failures = []
            _only_record = _skipped_record(args.only, _only_skip)
            if args.result is None:
                print("[note] 本块未执行：%s（%s）" % (args.only, _only_skip))
        if args.result is None:
            # 人工单跑也过一遍块名基线：**删块正是"没跑到"的那类失败**，只在全量档判就抓不到它。
            # ⚠️ 只在 `--result is None`（人工单跑）时并入：并行派发的 worker 也走这条分支，
            #    若不加这个门 ⇒ 同一句话会被每个 worker 各报一遍。
            _blk_prob = _blocks_baseline_problem()
            if _blk_prob:
                failures = [_blk_prob] + list(failures)
            # 人工单跑、未给 `--result` ⇒ 只跑并打印、不落 JSON；rc 据本次结果。
            # node 并进这一行（行数不变，只加字段）：单块快照也要能自证跑在哪台机器上。
            _node_here = xwl.find_node()
            print("[note] 未给 `--result` ⇒ 只跑并打印、不落 JSON；要落 JSON 才加 `--result <路径>`"
                  "（node: %s）" % (_node_here or "(未找到)"))
            if failures:
                # 单跑也要**看得到失败原因**（"有 rc 却看不到原因"是病根）；逐条 + 汇总格式照全量分支
                for f in failures:
                    print(f"[FAIL] {f}")
            _only_unexecuted = ([(args.only, _only_skip)] if _only_skip is not None else [])
            _only_ran = ([] if _only_skip is not None else [args.only])
            print(_summary_line(_blk_named, _only_ran, failures, _only_unexecuted))
            return 1 if failures else 0
        # 内部契约（`--jobs>1` 父进程派发用）：写 JSON 即退出 0，rc 由父进程据 JSON 定。
        # 内容是 dict，不是 list：带上 node，跨机复跑时才看得出差异从哪来。
        # ⚠️ 取值在本分支内就地调，⛔ 不把下面那行 `node:` 的 print 提前到这里。
        with open(args.result, "w", encoding="utf-8") as fh:
            json.dump({
                "block_id": _only_record.get("block_id"),
                "state": _only_record.get("state"),
                "reason": _only_record.get("reason"),
                "subchecks": _only_record.get("subchecks") or [],
                "node": xwl.find_node() or "",
                "failures": failures,
            }, fh, ensure_ascii=False)
        return 0

    node = xwl.find_node()
    print(f"node: {node or '(未找到，跳过事件 JS 校验)'}", flush=True)

    blocks = _blocks()
    if args.fast:
        print("[note] --fast：已跳过 _check_diffguard / _check_eol_and_guards"
              "（本地快回路用；CI 与默认档仍全跑）", flush=True)
        _fast_skipped = [n for n, _f in blocks if n in FAST_SKIP]
        blocks = [(n, f) for n, f in blocks if n not in _fast_skipped]
    else:
        _fast_skipped = []

    jobs = args.jobs if args.jobs is not None else min(6, os.cpu_count() or 4)
    failures, _records = (_run_serial(blocks, node) if jobs <= 1
                          else _run_parallel(blocks, node, jobs))
    # 块名基线：**与 `--only` 选哪块无关**地生效（删块正是"没跑到"的那种失败，
    # 只挂进某个块里就永远抓不到它自己）⇒ 在汇总前统一并入 failures。
    _blk_prob = _blocks_baseline_problem()
    if _blk_prob:
        failures = [_blk_prob] + list(failures)

    print()
    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
    # ⭐ 分母固定为注册块数。`--fast` 跳过的块进「未跑」，前置不满足的块进「未执行」；
    #   两者都不算通过。只有 13 块全部实际通过才保留裸 `=== selftest ALL OK`。
    #   rc 仍只由 failures 决定：未跑、未执行不升级退出码。
    _registered = _blocks()
    _unrun = _blocks_unexecuted(_registered)
    _ran_names = [n for n, _fn in blocks if n not in dict(_unrun)]
    print(_summary_line(_registered, _ran_names, failures, _unrun))
    if not args.require_all:
        return 1 if failures else 0
    if args.fast:
        for _name in _fast_skipped:
            _records.append(_skipped_record(_name, "--fast 未选择"))
    _rc, _lines = _aggregate_gate(_records)
    for _line in _lines:
        print(_line)
    return _rc


if __name__ == "__main__":
    sys.exit(main())
