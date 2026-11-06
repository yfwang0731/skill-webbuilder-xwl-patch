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

def _check_edit_eol(tmp, node, failures, write) -> None:
    """`edit` 的锚点必须按**目标文件的实际换行**归一，且拍平多行要警示（第 24 组）。

    起因：`normalize_eol()` 写死 CRLF 会引出三个缺陷 —— ① LF 文件上**跨行锚点永远匹配不到**
    （报「锚点出现次数: 0」，看着像用户写错了锚点）；② 单行锚点 + 多行 new 会把
    LF 文件写成 CRLF/LF **混用**（文件已落盘、格式已坏）。③ 另外「把多行拍平」
    属于**静默**语义损坏（毫无提示），而 `check` 查不出（压平后仍是合法 JSON）。
    三条都在这里钉住（实测样本工程：1878 全 CRLF / 902「单行无换行符」/ **0 个 LF** ——
    两条路径都要覆盖，因为 `expand` 会把无换行的单行源产出成 LF）。
    """
    print("[24] edit 的换行归一与拍平警示")
    xwl_py = os.path.join(SKILL_ROOT, "scripts", "xwl.py")

    def _cli(argv):
        pr = _cap_run([sys.executable, xwl_py] + argv, timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    def _mk(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    def _eol_of(p):
        b = open(p, "rb").read()
        crlf = b.count(b"\r\n")
        return crlf, b.count(b"\n") - crlf

    BASE = ('{\n "hidden": false,\n "children": [],\n "roles": {},\n "title": "SELFTEST_T",\n'
            ' "iconCls": "",\n "inframe": false,\n "pageLink": ""\n}')

    ee: list[str] = []

    # ① LF 文件 + 跨行锚点 —— 改前必然报「锚点出现次数: 0」（误导成"锚点写错了"）
    t = _mk("ee_lf.xwl", BASE)
    o = _mk("ee_o1.txt", '"roles": {},\n "title": "SELFTEST_T"')
    n = _mk("ee_n1.txt", '"roles": {},\n "title": "ZZZ"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0 or "锚点出现次数: 0" in out:
        ee.append("LF 文件上跨行锚点应能匹配（归一化写死换行时会报「锚点出现次数: 0」）：rc=%s" % rc)
    elif _eol_of(t)[0]:
        ee.append("LF 文件写入后被混入 CRLF：CRLF=%d LF=%d" % _eol_of(t))

    # ② LF 文件 + 单行锚点 + 多行 new —— 改前会把 LF 写成 CRLF/LF 混用
    t = _mk("ee_lf2.xwl", BASE)
    o = _mk("ee_o2.txt", '"roles": {}')
    n = _mk("ee_n2.txt", '"roles": {\n  "default": 1\n}')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0:
        ee.append("LF 文件 + 多行 new 应成功：rc=%s" % rc)
    elif _eol_of(t)[0]:
        ee.append("LF 文件 + 多行 new 后混入 CRLF（CRLF=%d LF=%d），应保持全 LF" % _eol_of(t))

    # ③ CRLF 文件 + 跨行锚点 —— 回归：这条本来就该通，不能被改坏
    t = _mk("ee_crlf.xwl", BASE.replace("\n", "\r\n"))
    o = _mk("ee_o3.txt", '"roles": {},\n "title": "SELFTEST_T"')
    n = _mk("ee_n3.txt", '"roles": {},\n "title": "ZZZ"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0:
        ee.append("CRLF 文件 + 跨行锚点应成功：rc=%s" % rc)
    elif _eol_of(t)[1]:
        ee.append("CRLF 文件写入后被混入 LF：CRLF=%d LF=%d" % _eol_of(t))

    # ④ 拍平多行必须警示（工具是唯一能提示的地方：check 查不出）
    t = _mk("ee_flat.xwl",
            '{\n "hidden": false,\n "children": [],\n "roles": {},\n'
            ' "title": "a\\\nb\\\nc",\n "iconCls": "",\n "inframe": false,\n "pageLink": ""\n}')
    o = _mk("ee_o4.txt", '"title": "a\\\nb\\\nc"')
    n = _mk("ee_n4.txt", '"title": "abc"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if "[warn]" not in out or "续行符" not in out:
        ee.append("拍平多行时必须警示（[warn] 且提到「续行符」），否则是静默语义损坏")

    # ⑤ 普通单行替换不得误报
    t = _mk("ee_ok.xwl", BASE)
    o = _mk("ee_o5.txt", '"title": "SELFTEST_T"')
    n = _mk("ee_n5.txt", '"title": "BBB"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if "[warn]" in out:
        ee.append("普通单行替换不该出现 [warn]（误报）")

    if ee:
        failures.extend(ee)
    else:
        print("[ok]  edit 锚点按目标换行归一（LF/CRLF 均可）、拍平多行有 [warn]、普通替换不误报")

