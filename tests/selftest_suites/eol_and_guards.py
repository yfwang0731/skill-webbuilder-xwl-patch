# -*- coding: utf-8 -*-
"""自检块实现。由 scripts/selftest.py 按稳定块 ID 调度。"""
from __future__ import annotations

import ast as ast
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
from unittest import mock as _umock

def _load_selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(os.path.dirname(here)), "scripts", "selftest.py")
    name = "xwl_selftest_runtime"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod

_st = _load_selftest()
globals().update({k: getattr(_st, k) for k in dir(_st) if not k.startswith("__")})

# 套件自己的 @_cap。导入 selftest 会带入同名装饰器，必须在导入后重新定义。
_CAP_FN_NAMES = set()


def _cap(fn):
    _CAP_FN_NAMES.add(fn.__name__)
    return fn

def _check_eol_and_guards(tmp, node, failures, write) -> None:
    """换行形态 × 校验收尾 × 静默回退（第 25 组）。

    四条都是"实现了但没测到"的类型，成因一致：样本工程里纯 LF 稀少，
    而 LF 是设计器原样、仓库存的格式、`new` 的默认产出 —— 于是以 CRLF 为准写死的代码
    在这份样本上永远看不出问题。

    ① `check` 的 ③「续行空白」用 `text.split(CRLF)` 切行 ⇒ **纯 LF 文件切不出行**
       （整份成一个元素），③ 静默退化成"只看最后一行"。实测：同一处「反斜杠+空白」
       在 CRLF 上被 ③ 精准报到行号，在 LF 上 ③ 报 `[ok]`。
    ② 同一处切行还让纯 CR 文件同时得到「存在 N 处裸 CR」的 FAIL 与
       「该文件是单行形态（无任何换行）」的 note —— 自相矛盾。
    ③ `patch` 对**换行混用**的源会静默统一（`edit` 早有 `[warn]`，`patch` 没有）。
    ④ `patch --indent≠1` 会产出与设计器不一致的文件、却零提示 ——
       等于给了用户一把击穿「与设计器逐字节一致」的钥匙。
    ⑤ `patch` 在**无换行的单行源**上 `--eol auto` 回退 LF，且必然把整份展开成多行
       （diff = 整个文件），两条都要说清。
    ⑥ 值里的**孤立代理项**会让 `.encode("utf-8")` 崩 —— 实测 `patch` 在打印字节数时
       就冒 traceback（rc=1）。`_quote` 按 org.json 的 `\\uXXXX` 转义后语义仍等价。
    """
    print("[25] 换行形态 × 校验收尾 × 静默回退")
    xwl_py = os.path.join(SKILL_ROOT, "scripts", "xwl.py")

    def _cli(argv):
        pr = _cap_run([sys.executable, xwl_py] + argv, timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    def _mk(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    BS = chr(92)
    # 一份合法骨架，中间那行的续行符后挂一个空白 —— ③ 应当抓到它
    def _body(mid, eol):
        return eol.join([
            "{", ' "hidden": false,', ' "children": [{',
            '  "configs": {"itemId": "SELFTEST_BTN", "text": "SELFTEST_T"},',
            '  "expanded": false,', '  "children": [],', '  "type": "button",',
            '  "events": {', '   "click": "var a = 1;' + mid,
            'Wb.info(String(a));"', '  }', ' }],',
            ' "roles": {"default": 1},',
            ' "title": "SELFTEST_T", "iconCls": "", "inframe": false, "pageLink": ""', '}'])

    ge: list[str] = []

    # ① ③ 必须在三种换行下都生效（同一处破坏，三种文件都要报出行号）
    for eol, tag in (("\r\n", "CRLF"), ("\n", "LF"), ("\r", "CR")):
        f = _mk("ge_a_%s.xwl" % tag, _body(BS + BS + " ", eol))
        _rc, out = _cli(["check", f])
        if "③ 第" not in out:
            ge.append("③ 在 %s 文件上没报出「反斜杠+空白」所在行（切行写死 CRLF ⇒ 静默失效）" % tag)

    # ①b 干净文件不得因切行变更而误报 ③（注意：`[ok]` 行里本来就含「③ 续行空白」，
    #     所以只能匹配 FAIL 形态的「③ 第…行」，不能只找「③」）
    f = _mk("ge_ok_crlf.xwl", _body(BS, "\r\n"))
    _rc, out = _cli(["check", f])
    if "③ 第" in out:
        ge.append("干净的 CRLF 文件被 ③ 误报")

    # ①c 换行统计必须与 `check` 的 ② 同口径：`expand` 也要报"裸 LF"，不能把 CRLF 里的
    #     `\n` 算进"LF" —— 否则纯 CRLF 文件会显示成「CRLF=N, LF=N」，读者误读成混用。
    _rc, out = _cli(["expand", f, "--dry-run"])
    if "裸LF=0" not in out:
        ge.append("expand 的换行统计没按「裸 LF」口径报（纯 CRLF 文件应显示 裸LF=0）")

    # ② 纯 CR 文件：② 的 FAIL 与「无任何换行」的 note 不得同时出现（自相矛盾）
    f = _mk("ge_cr_note.xwl", _body(BS, "\r"))
    _rc, out = _cli(["check", f])
    if "裸 CR" in out and "无任何换行" in out:
        ge.append("纯 CR 文件同时报「存在 N 处裸 CR」与「该文件是单行形态（无任何换行）」")

    # ③ patch 对换行混用的源必须给 [warn]（对齐 edit）
    f = _mk("ge_mixed.xwl", _body(BS, "\r\n").replace("\r\n", "\n", 3))
    ops = _mk("ge_ops.json",
              '[{"op":"set","path":["title"],"value":"SELELTEST_NEW"}]')
    _rc, out = _cli(["patch", f, "--ops", ops, "--dry-run"])
    # 判据要连 `[warn]` 标记一起查：只查文本的话，把标记换成 `[xx]`（等于不再是警告）也照样过
    if "[warn]" not in out or "换行混用" not in out:
        ge.append("patch 在换行混用的源上没有 [warn]（会静默统一换行）")

    # ④ --indent ≠ 1 必须警示（patch 与 expand 都要）
    f = _mk("ge_ind.xwl", _body(BS, "\r\n"))
    for cmd in (["patch", f, "--ops", ops, "--indent", "4", "--dry-run"],
                ["expand", f, "--indent", "4", "--dry-run"]):
        _rc, out = _cli(cmd)
        if "[warn]" not in out:
            ge.append("%s 用 --indent 4 时没有 [warn]（会静默产出与设计器不一致的排版）" % cmd[0])

    # ⑤ 无换行的单行源：要说明「auto 回退 LF」与「整份展开」
    obj = xwl.parse_xwl(_body(BS, "\r\n"))
    compact = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if "\n" in compact:
        raise AssertionError("样本不是单行")
    f = _mk("ge_one.xwl", compact)
    _rc, out = _cli(["patch", f, "--ops", ops, "--dry-run"])
    if "回退 LF" not in out:
        ge.append("单行源上 patch 没有说明 `--eol auto` 回退 LF")
    if "[warn]" not in out or "整份展开" not in out:
        ge.append("单行源上 patch 没有以 [warn] 说明会把整份展开成多行")

    # ⑥ 孤立代理项：不得冒 traceback、必须转义落盘、且语义仍等价
    f = _mk("ge_sur.xwl", _body(BS, "\r\n"))
    ops_s = os.path.join(tmp, "ge_sur_ops.json")
    with open(ops_s, "w", encoding="utf-8") as fh:
        fh.write('[{"op":"set","path":["title"],"value":"\\ud800SELELTEST"}]')
    rc, out = _cli(["patch", f, "--ops", ops_s, "--backup"])
    if "Traceback" in out:
        ge.append("值含孤立代理项时抛了 Python traceback（应给可读结果）")
    elif rc != 0:
        ge.append("值含孤立代理项时应能写完（rc=0），实得 rc=%s" % rc)
    else:
        raw = open(f, "rb").read()
        if b"\\ud800" not in raw:
            ge.append("孤立代理项没有按 \\uXXXX 转义落盘")
        try:
            got = xwl.parse_xwl(raw.decode("utf-8"))["title"]
        except Exception as exc:  # noqa: BLE001
            ge.append("转义后的文件读不回原对象：%s" % exc)
        else:
            if got != "\ud800SELELTEST":
                ge.append("转义后语义不等价：%r" % got)
    # `_byte_len` 本身也不该抛
    try:
        if xwl._byte_len("\ud800") <= 0:      # noqa: SLF001
            ge.append("_byte_len 对孤立代理项返回了非正数")
    except Exception as exc:  # noqa: BLE001
        ge.append("_byte_len 对孤立代理项抛了 %s" % type(exc).__name__)

    if ge:
        failures.extend(ge)
    else:
        print("[ok]  ③ 在 CRLF/LF/CR 三种换行下都生效 + 纯 CR 的 note 不再自相矛盾 + "
              "patch 的换行混用/--indent/单行源回退都有 [warn] + 孤立代理项不冒 traceback")

