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

    # 1.9.2 edit_eol_boundary/edit_dry_run_stage/expand_dry_run_stage/expand_output_contract：帮助的阶段边界、EOL 参数面与 expand 成功措辞。
    rc, out = _cli(["edit", "--help"])
    if rc != 0 or "候选解析" not in out or "写前门禁" not in out:
        ee.append("edit_dry_run_stage edit --dry-run 帮助必须说明仍执行锚点断言/文件读取/候选解析/写前门禁")
    if "--eol" in out:
        ee.append("edit_eol_boundary edit 不应出现 --eol 参数")

    rc, out = _cli(["expand", "--help"])
    if rc != 0 or "只执行解析、重建和语义等价比对" not in out:
        ee.append("expand_dry_run_stage expand --dry-run 帮助必须说明只到解析/重建/语义等价")
    if "不执行写后复检" not in out or "事件 JS" not in out:
        ee.append("expand_dry_run_stage expand --dry-run 帮助必须声明不执行写后复检（含事件 JS）")

    # 未命中与 BOM 都是写前拒写：目标字节不变、不得生成 .bak。
    t = _mk("ee_miss.xwl", BASE)
    o = _mk("ee_o6.txt", "NOT_PRESENT")
    n = _mk("ee_n6.txt", "X")
    before = open(t, "rb").read()
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n, "--dry-run"])
    if rc != 2 or open(t, "rb").read() != before or os.path.exists(t + ".bak"):
        ee.append("edit_dry_run_stage edit --dry-run 锚点次数不符应 rc=2、零写入、无 .bak")

    t = _mk("ee_twice.xwl", BASE.replace('"roles": {}',
                                         '"roles": {}, "roles": {}'))
    o = _mk("ee_o6_twice.txt", '"roles": {}')
    n = _mk("ee_n6_twice.txt", '"roles": {"default": 1}')
    before = open(t, "rb").read()
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n,
                    "--expect", "1", "--dry-run"])
    if rc != 2 or open(t, "rb").read() != before:
        ee.append("expect_count 两处命中配 --expect 1 应 rc=2 且零写入")
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n,
                    "--expect", "2", "--dry-run"])
    if rc != 0 or open(t, "rb").read() != before:
        ee.append("expect_count 两处命中配 --expect 2 应 rc=0 且 dry-run 零写入")

    t = _mk("ee_bom.xwl", "\ufeff" + BASE)
    o = _mk("ee_o7.txt", '"title": "SELFTEST_T"')
    n = _mk("ee_n7.txt", '"title": "BOM"')
    before = open(t, "rb").read()
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n, "--backup"])
    if rc != 2 or open(t, "rb").read() != before or os.path.exists(t + ".bak"):
        ee.append("exit_code_contract edit 目标 BOM 应 rc=2、零写入、无 .bak")

    for label, args, forbidden in (
        ("expand_output_contract expand --safe", ["expand", t.replace("ee_bom.xwl", "ee_safe.xwl"),
                               "--safe", "--backup"],
         "排版与设计器 `IDE.updateModule` 一致"),
        ("expand_output_contract expand --indent 4", ["expand", t.replace("ee_bom.xwl", "ee_indent.xwl"),
                                    "--indent", "4", "--backup"],
         "排版与设计器 `IDE.updateModule` 一致"),
    ):
        candidate = args[1]
        with open(candidate, "w", encoding="utf-8", newline="") as fh:
            fh.write(BASE)
        rc, out = _cli(args)
        if rc != 0:
            ee.append("%s 应成功，rc=%s：%s" % (label, rc, out[-300:]))
        elif forbidden in out:
            ee.append("%s 不得再承诺设计器一致布局" % label)

    # edit_anchor_eol_boundary：edit 的锚点归一与 patch/expand 的整文件 EOL 分离。
    mixed = BASE.replace('"children": [],\n', '"children": [],\r\n', 1)
    t = _mk("ee_mixed.xwl", mixed)
    o = _mk("ee_o8.txt", '"title": "SELFTEST_T"')
    n = _mk("ee_n8.txt", '"title": "MIXED"')
    expected = mixed.replace('"title": "SELFTEST_T"', '"title": "MIXED"').encode("utf-8")
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if open(t, "rb").read() != expected:
        ee.append("edit_anchor_eol_boundary edit 混用换行：应从目标实际风格归一锚点，"
                  "命中区域外字节保持不变")
    if "换行混用" not in out:
        ee.append("edit_anchor_eol_boundary edit 混用换行：应明确打印混用告警")

    compact = ('{"hidden":false,"children":[],"roles":{},"title":"SELFTEST_T",'
               '"iconCls":"","inframe":false,"pageLink":""}')
    t = _mk("ee_compact.xwl", compact)
    o = _mk("ee_o9.txt", '"roles":{}')
    n = _mk("ee_n9.txt", '"roles":{"default":1}')
    expected = compact.replace('"roles":{}', '"roles":{"default":1}').encode("utf-8")
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0 or open(t, "rb").read() != expected:
        ee.append("edit_anchor_eol_boundary edit 无换行源：不应引入整文件换行，rc=%s" % rc)
    if b"\r" in open(t, "rb").read() or b"\n" in open(t, "rb").read():
        ee.append("edit_anchor_eol_boundary edit 无换行源被意外加入换行")

    if ee:
        failures.extend(ee)
    else:
        print("[ok]  edit 锚点按目标换行归一（LF/CRLF 均可）、拍平多行有 [warn]、普通替换不误报")
        print("[ok]  1.9.2 edit_eol_boundary/edit_dry_run_stage/expand_dry_run_stage/expand_output_contract：edit/expand 帮助阶段边界、BOM/未命中零写入、"
              "safe/indent 不承诺设计器布局")
        print("[ok]  contract_phrase_set edit_anchor_eol_boundary：edit 混用/无换行源的未命中区域保持字节，"
              "help 不含 --eol，整文件 EOL 仅属 patch/expand")

