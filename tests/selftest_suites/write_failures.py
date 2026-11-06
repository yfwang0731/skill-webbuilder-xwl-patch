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

def _check_write_failures(tmp, node, failures, write) -> None:
    """写盘失败必须给可读 [FAIL] + 退出码 2，不得冒 Python traceback（第 23 组）。

    起因：`write_text()` 不兜 `OSError` —— 目标只读 / 父目录不存在 / 路径过长
    都会抛 traceback，而 SKILL.md §4.2 承诺的是「前置条件不满足 → rc=2 + 提示」。
    实测 5 个子命令 9 个场景中招，而 64 项断言**一条都没覆盖写失败**。
    所以这里用子进程跑真实 CLI，逐一确认「不冒 traceback + rc=2 + 有 [FAIL]」。
    """
    print("[23] 写失败路径不得冒 traceback")
    xwl_py = os.path.join(SKILL_ROOT, "scripts", "xwl.py")
    ro = write("wf_ro.xwl", VALID)
    ops_p = os.path.join(tmp, "wf_ops.json")
    with open(ops_p, "w", encoding="utf-8", newline="") as fh:
        fh.write('[{"op": "set", "path": ["title"], "value": "x"}]')
    fdir = os.path.join(tmp, "wf_fld")
    os.makedirs(fdir, exist_ok=True)
    fpage = os.path.join(fdir, "p.xwl")
    with open(fpage, "w", encoding="utf-8", newline="") as fh:
        fh.write(VALID)
    fj = os.path.join(fdir, "folder.json")
    with open(fj, "w", encoding="utf-8", newline="") as fh:
        fh.write('{"hidden":false,"index":[],"title":"t","iconCls":""}')
    nodir = os.path.join(tmp, "wf_nodir")

    def _cli(argv):
        pr = _cap_run([sys.executable, xwl_py] + argv, timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    wf: list[str] = []
    try:
        os.chmod(ro, 0o444)
        os.chmod(fj, 0o444)
        for label, argv in (
            ("patch → 目标只读", ["patch", ro, "--ops", ops_p]),
            ("expand --out → 目录不存在",
             ["expand", ro, "--out", os.path.join(nodir, "o.xwl")]),
            ("new → 父目录不存在", ["new", os.path.join(nodir, "a.xwl"), "--kind", "page"]),
            ("folders --register → folder.json 只读", ["folders", fpage, "--register"]),
        ):
            rc, out = _cli(argv)
            if "Traceback" in out:
                wf.append("%s：抛了 Python traceback（应给 [FAIL] + rc=2）" % label)
            elif rc != 2:
                wf.append("%s：退出码 %s（应为 2）" % (label, rc))
            elif "[FAIL]" not in out:
                wf.append("%s：没有 [FAIL] 提示" % label)
    finally:
        for f in (ro, fj):
            try:
                os.chmod(f, 0o666)
            except OSError:
                pass

    if wf:
        failures.extend(wf)
    else:
        print("[ok]  写失败给可读 [FAIL] + rc=2，不冒 traceback"
              "（patch / expand / new / folders 四类）")
    _check_write_gate(tmp, node, failures, write)

_JS_GATED_WRITE = ("G1", "G2a", "G4a", "G7", "G10", "G12a", "G12b", "G13a", "G13b", "G14",
                   "G15a", "G15b", "G17", "G22d", "G22b")

def _count_node_gates(fn_name: str) -> int:
    """数某函数体内 `if node:` 的处数（防「新增门控忘登记」）。"""
    import ast as _ast
    _t = _ast.parse(open(__file__, encoding="utf-8").read())
    for _n in _ast.walk(_t):
        if isinstance(_n, _ast.FunctionDef) and _n.name == fn_name:
            return sum(1 for _x in _ast.walk(_n)
                       if isinstance(_x, _ast.If) and isinstance(_x.test, _ast.Name)
                       and _x.test.id == "node")
    return -1

@_cap
def _check_write_gate(tmp, node, failures, write) -> None:
    """写盘前门禁：坏事件不先落盘、既有失败可证明、ops 类型错拒、非有限值进出都拒。"""
    import math as _math
    import subprocess as _sp
    print("[23b] 写前门禁 / 非有限值 / ops 类型")
    node = node or xwl.find_node()
    xwl_py = os.path.join(SKILL_ROOT, "scripts", "xwl.py")
    bad: list[str] = []

    def _cli(argv):
        pr = _cap_run([sys.executable, "-B", xwl_py] + argv, timeout=120)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    def _ops(name, ops):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(ops, ensure_ascii=False))
        return p

    def _bytes(path):
        with open(path, "rb") as fh:
            return fh.read()

    def _page(events=None, title="t", root_events=None, extra=None):
        obj = {"title": title, "hidden": False, "children": [], "roles": {},
               "iconCls": "", "inframe": "", "pageLink": ""}
        if extra:
            obj.update(extra)
        if events is not None:
            obj["children"] = [{"type": "button", "configs": {"itemId": "b"},
                                "events": events, "children": []}]
        if root_events is not None:
            obj["events"] = root_events
        return xwl.dumps_designer(obj)

    def _need(cond, msg):
        if not cond:
            bad.append(msg)

    if not node:
        print("[note] 未执行：Node 不可用，依赖真 node 的写前抽查跳过")

    p = write("wg_g1.xwl", _page({"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g1.json",
        [{"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(p) == before and "未能执行" not in out,
              "新增坏事件未按语法失败拒写 rc=%s" % rc)

    p = write("wg_g2.xwl", _page({"click": "function("}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g2.json",
        [{"op": "set", "path": ["title"], "value": "renamed"}])])
    if node:
        _need(rc == 1 and _bytes(p) != before and "既有" in out,
              "既有坏事件改标题未按既有失败写入 rc=%s" % rc)

    p = write("wg_g3.xwl", _page({"click": "void 0;"}))
    rc, out = _cli(["patch", p, "--no-js", "--ops", _ops("wg_g3.json",
        [{"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
    _need(rc == 0 and "⑥ 事件 JS 未执行" in out, "显式跳过事件校验未写盘或未留记 rc=%s" % rc)

    p = write("wg_g4a.xwl", _page({"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--dry-run", "--ops", _ops("wg_g4a.json",
        [{"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(p) == before and not os.path.exists(p + ".bak"),
              "预演坏事件未拒或已写盘 rc=%s" % rc)

    p = write("wg_g4b.xwl", _page({"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--dry-run", "--no-js", "--ops", _ops("wg_g4b.json",
        [{"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
    _need(rc == 0 and "[note]" in out and _bytes(p) == before,
          "预演且显式跳过未留记或已写盘 rc=%s" % rc)

    p = write("wg_g5.xwl", _page())
    before = _bytes(p)
    rc, out = _cli(["edit", p, "--old-file", write("wg_g5.old", '"title"'),
                    "--new-file", write("wg_g5.new", "NOT JSON {{{{"), "--expect", "1"])
    _need(rc == 2 and _bytes(p) == before, "候选不可解析未拒写 rc=%s" % rc)

    p = write("wg_ok.xwl", _page())
    rc, out = _cli(["patch", p, "--ops", _ops("wg_ok.json",
        [{"op": "set", "path": ["title"], "value": "ok"}])])
    _need(rc == 0 and b"ok" in _bytes(p), "合法 patch rc=%s" % rc)

    p = write("wg_g7.xwl", _page({"click": "void 0;"}))
    bak = p + ".bak"
    with open(bak, "wb") as fh:
        fh.write(b"KEEP")
    rc, out = _cli(["patch", p, "--backup", "--ops", _ops("wg_g7.json",
        [{"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(bak) == b"KEEP", "拒写时动了既有备份 rc=%s" % rc)

    raw = '{ "title": "t"'
    p = write("wg_g10.xwl", raw)
    before = _bytes(p)
    rc, out = _cli(["edit", p, "--old-file", write("wg_g10.old", '{ "title": "t"'),
                    "--new-file", write("wg_g10.new",
                        '{"title":"t","events":{"click":"function("}}'), "--expect", "1"])
    if node:
        _need(rc == 1 and _bytes(p) == before and "无法证明" in out,
              "原文不可解析加坏事件未拒 rc=%s" % rc)

    p = write("wg_g11.xwl", raw)
    before = _bytes(p)
    rc, out = _cli(["edit", p, "--old-file", write("wg_g11.old", '{ "title": "t"'),
                    "--new-file", write("wg_g11.new", _page()), "--expect", "1"])
    _need(rc == 0 and _bytes(p) != before, "原文不可解析换成合法页未写入 rc=%s" % rc)

    src12 = {"children": [
        {"a/b": {"events": {"click": "void 0;"}}},
        {"a": {"b": {"events": {"click": "void 0;"}}}},
    ]}
    p = write("wg_g12.xwl", xwl.dumps_designer(src12))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g12.json", [
        {"op": "set", "path": ["children", 0, "a/b", "events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(p) == before and "children[0].a/b#click" in out
              and "children[1].a.b#click" not in out, "同渲染两个身份未分开 rc=%s" % rc)
    p = write("wg_g12b.xwl", xwl.dumps_designer(src12))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g12b.json", [
        {"op": "set", "path": ["children", 1, "a", "b", "events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(p) == before and "children[1].a.b#click" in out,
              "同渲染的另一身份未拒 rc=%s" % rc)

    p = write("wg_g13a.xwl", _page({"click": "function ("}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g13a.json", [
        {"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(p) == before, "坏事件只改空白仍应拒写 rc=%s" % rc)

    p = write("wg_g13b.xwl", _page({"click": "function("}).replace("\r\n", "\n"))
    rc, out = _cli(["patch", p, "--eol", "crlf", "--ops", _ops("wg_g13b.json", [
        {"op": "set", "path": ["title"], "value": "t"}])])
    if node:
        _need(rc == 1 and "既有" in out, "只改外层换行时既有失败未按既有写入 rc=%s" % rc)

    p = write("wg_g14.xwl", _page({"click": "function("}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g14.json", [
        {"op": "set", "path": ["children", 0, "events"],
         "value": {"click": "function(", "blur": "function("}}])])
    if node:
        _need(rc == 1 and _bytes(p) == before, "既有坏事件再加新坏事件未整份拒写 rc=%s" % rc)

    p = write("wg_g15a.xwl", _page(root_events={"click": "function("}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g15a.json", [
        {"op": "set", "path": ["title"], "value": "renamed"}])])
    if node:
        _need(rc == 1 and _bytes(p) != before and "既有" in out,
              "根级既有坏事件未按既有写入 rc=%s" % rc)

    p = write("wg_g15b.xwl", _page(root_events={"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g15b.json", [
        {"op": "set", "path": ["events", "click"], "value": "function("}])])
    if node:
        _need(rc == 1 and _bytes(p) == before, "根级新增坏事件未拒写 rc=%s" % rc)

    p = write("wg_g16.xwl", _page({"click": "void 0;"}))
    rc, out = _cli(["patch", p, "--node", os.path.join(tmp, "no-such-node.exe"), "--ops",
                    _ops("wg_g16.json", [{"op": "set", "path": ["title"], "value": "n"}])])
    _need(rc == 0 and "⑥ 事件 JS 未执行" in out, "指定不存在的 node 未写盘或未留记 rc=%s" % rc)

    p = write("wg_g17.xwl", _page({"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["edit", p, "--old-file", write("wg_g17.old", "void 0;"),
                    "--new-file", write("wg_g17.new", "function("), "--expect", "1"])
    if node:
        _need(rc == 1 and _bytes(p) == before, "edit 把事件改坏未拒写 rc=%s" % rc)

    p = write("wg_g18b.xwl", _page({"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--node", sys.executable, "--ops", _ops("wg_g18b.json", [
        {"op": "set", "path": ["title"], "value": "x"}])])
    _need(rc == 2 and _bytes(p) == before and "未能执行" in out and "既有" not in out,
          "非 node 可执行未按调用失败拒写 rc=%s" % rc)

    real_cap = xwl._cap_run

    def _boom(*a, **k):
        raise _sp.TimeoutExpired(a[0] if a else "node", 60)

    xwl._cap_run = _boom
    try:
        v = xwl._js_verdict(sys.executable, "void 0;")
    finally:
        xwl._cap_run = real_cap
    _need(isinstance(v, str) and v.startswith("error:"), "超时未归入调用失败：%r" % (v,))

    p = write("wg_g19a.xwl", _page())
    bak = p + ".bak"
    probe = b"PROBE-OLD-BAK"
    with open(bak, "wb") as fh:
        fh.write(probe)
    rc, out = _cli(["patch", p, "--backup", "--ops", _ops("wg_g19a.json", [
        {"op": "set", "path": ["title"], "value": "after"}])])
    hist = [n for n in os.listdir(tmp) if n.startswith("wg_g19a.xwl.bak.")]
    kept = _bytes(os.path.join(tmp, hist[0])) if hist else b""
    _need(rc == 0 and kept == probe and _bytes(bak) != probe and "旧备份已保全" in out,
          "旧备份未轮换保全 rc=%s hist=%s" % (rc, hist))

    sub = os.path.join(tmp, "wg_rot")
    os.makedirs(sub, exist_ok=True)
    p = os.path.join(sub, "f.xwl")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(_page())
    with open(p + ".bak", "wb") as fh:
        fh.write(b"OLD")
    before_names = set(os.listdir(sub))
    real_stamp = xwl._bak_stamp
    xwl._bak_stamp = lambda: "20261103-110000"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc1 = xwl.cmd_patch(type("NS", (), {
                "file": p, "ops": _ops("wg_rot1.json", [
                    {"op": "set", "path": ["title"], "value": "one"}]),
                "eol": "auto", "indent": 1, "dry_run": False, "backup": True,
                "node": None, "no_js": True, "allow_new_key": False,
            })())
            rc2 = xwl.cmd_patch(type("NS", (), {
                "file": p, "ops": _ops("wg_rot2.json", [
                    {"op": "set", "path": ["title"], "value": "two"}]),
                "eol": "auto", "indent": 1, "dry_run": False, "backup": True,
                "node": None, "no_js": True, "allow_new_key": False,
            })())
    finally:
        xwl._bak_stamp = real_stamp
    after = set(os.listdir(sub))
    added = after - before_names
    stamps = sorted(added)
    _need(rc1 == 0 and rc2 == 0 and len(stamps) == 2
          and stamps[1] == stamps[0] + "-2"
          and after == before_names | added and len(after) == 4,
          "同秒两次轮换历史不对 rc=%s/%s added=%s" % (rc1, rc2, stamps))

    lit = '{"beforeedit": function(e){ return true; }}'
    p = write("wg_g22a.xwl", _page({"click": lit}))
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g22a.json", [
        {"op": "set", "path": ["title"], "value": "kept"}])])
    if node:
        _need(rc == 0 and b"kept" in _bytes(p), "对象字面量事件被门禁拒写 rc=%s" % rc)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            crc = xwl.cmd_check(type("NS", (), {
                "files": [p], "node": node, "no_js": False, "no_itemid": True,
                "checks": {6},
            })())
        _need(crc == 0 and "⑥" in buf.getvalue() and "FAIL" not in buf.getvalue(),
              "同一对象字面量 check 未过 rc=%s" % crc)

    clash_page = {
        "title": "t", "hidden": False, "children": [], "roles": {},
        "iconCls": "", "inframe": "", "pageLink": "",
        "a.b": {"events": {"click": "void 0;"}},
        "a": {"b": {"events": {"click": "void 0;"}}},
    }
    p = write("wg_clash.xwl", xwl.dumps_designer(clash_page))
    rc, out = _cli(["patch", p, "--ops", _ops("wg_clash.json", [
        {"op": "set", "path": ["title"], "value": "z"}])])
    # 撞名是身份渲染冲突，与执行器无关 ⇒ 断言不设 node 门控（无 node 时也照样要打这条 note）。
    _need(rc == 0 and "[note] 两处同名同渲染" in out,
          "撞名提示未出现在真写盘输出里 rc=%s" % rc)
    # 同一份夹具换成「执行器不存在」再跑：只覆盖有 node 机器的话，正常路径绿并不能证明
    #   这条提示不依赖执行器 —— 把 node 指到不存在的路径，它仍必须打出来。
    p = write("wg_clash2.xwl", xwl.dumps_designer(clash_page))
    _nrc, _nout = _cli(["patch", p, "--node", os.path.join(tmp, "no-such-node.exe"),
                        "--ops", _ops("wg_clash2.json", [
                            {"op": "set", "path": ["title"], "value": "z"}])])
    _need(_nrc == 0 and "[note] 两处同名同渲染" in _nout,
          "执行器不存在时撞名提示丢了 rc=%s" % _nrc)

    p = write("wg_g22b.xwl", _page({"click": "void 0;"}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_g22b.json", [
        {"op": "set", "path": ["children", 0, "events", "click"], "value": "function(){}"}])])
    if node:
        _need(rc == 1 and _bytes(p) == before, "裸 function 未拒写 rc=%s" % rc)

    calls = {"n": 0}

    class _Syn:
        returncode = 1
        stdout = ""
        stderr = "SyntaxError: Unexpected token"

    def _two(cmd, **k):
        calls["n"] += 1
        if calls["n"] == 1 and "--version" in cmd:
            class _Ver:
                returncode = 0
                stdout = "v" + "22" + "." + "1"
                stderr = ""
            return _Ver()
        if "--check" in cmd and calls["n"] == 2:
            return _Syn()
        raise _sp.TimeoutExpired(cmd, 60)

    xwl._cap_run = _two
    try:
        v = xwl._js_verdict(sys.executable, lit)
    finally:
        xwl._cap_run = real_cap
    _need(isinstance(v, str) and v.startswith("error:"),
          "对象字面量复验超时未归入调用失败：%r" % (v,))

    p = write("wg_g21.xwl", _page())
    before = _bytes(p)
    real_w = xwl.write_text

    def _wboom(path, text):
        raise xwl.XwlWriteError("injected")

    xwl.write_text = _wboom
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = xwl.cmd_patch(type("NS", (), {
                "file": p, "ops": _ops("wg_g21.json", [{"op": "set", "path": ["title"], "value": "z"}]),
                "eol": "auto", "indent": 1, "dry_run": False, "backup": False,
                "node": None, "no_js": True, "allow_new_key": False,
            })())
    finally:
        xwl.write_text = real_w
    text = buf.getvalue()
    _need(rc == 2 and _bytes(p) == before and "已直接写盘" not in text and "未使用 --backup" in text
          and "写盘失败" in text, "写盘异常未在命令内接住 rc=%s" % rc)

    p = write("wg_o1.xwl", _page())
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o1.json", [
        {"op": "set", "path": ["nope"], "value": "v", "create": "false"}])])
    _need(rc == 2 and _bytes(p) == before, "create 字符串 rc=%s" % rc)
    p = write("wg_o2.xwl", _page())
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o2.json", [
        {"op": "set", "path": ["nope"], "value": "v", "create": 1}])])
    _need(rc == 2 and _bytes(p) == before, "create 数字 rc=%s" % rc)
    p = write("wg_o3.xwl", _page(extra={"children": [{"type": "button"}, {"type": "button"}]}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o3.json", [
        {"op": "insert", "path": ["children"], "index": 1.5, "value": {"type": "x"}}])])
    _need(rc == 2 and _bytes(p) == before, "index 浮点 rc=%s" % rc)
    p = write("wg_o4.xwl", _page(extra={"children": [{"type": "a"}, {"type": "b"}]}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o4.json", [
        {"op": "delete", "path": ["children"], "index": True}])])
    _need(rc == 2 and _bytes(p) == before, "index 布尔 rc=%s" % rc)
    p = write("wg_o5.xwl", _page())
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o5.json", [
        {"op": "set", "path": ["title"], "value": "z", "creat": True}])])
    _need(rc == 0 and "[warn]" in out and "creat" in out, "未知字段 rc=%s" % rc)

    # ⚠️ 必须放在下面 `bad` 并进 `failures` **之前**：`_need` 只是往 `bad` 里追加，
    #   放 flush 之后就等于把这条判据静默丢掉（注入实测：删一项后仍全绿）。
    _need(_count_node_gates("_check_write_gate") == len(_JS_GATED_WRITE),
          "node 门控 %d 处 ≠ 登记表 %d 条（新增门控要同步 _JS_GATED_WRITE）"
          % (_count_node_gates("_check_write_gate"), len(_JS_GATED_WRITE)))

    if bad:
        failures.extend(bad)
    else:
        print("[ok]  写前门禁前半抽查通过")
    # 无 node 时上面那些门控一条都不跑 ⇒ 必须点名「哪些没跑」，否则输出与有 node 时逐行相同、
    #   ALL OK 照报，等于静默跳过。文案以「未执行」开头（⛔ 不用 [warn]：会被文档守卫当新增行）。
    if not node:
        print("[note] 未执行 %d 条写前门禁断言（Node 不可用）：%s"
              % (len(_JS_GATED_WRITE), "、".join(_JS_GATED_WRITE)))
    _check_write_gate_rest(tmp, node, failures, write, _cli, _ops, _bytes, _page, xwl_py)

@_cap
def _check_write_gate_rest(tmp, node, failures, write, _cli, _ops, _bytes, _page, xwl_py) -> None:
    """写前门禁后半：正例 ops、非有限值往返、写后采集、以及改前未覆盖的两条尽力项。"""
    import math as _math
    bad: list[str] = []

    def _need(cond, msg):
        if not cond:
            bad.append(msg)

    body = {"children": [{"configs": {"text": "a"}}, {"configs": {"text": "b"}}]}
    p = write("wg_o6.xwl", _page(extra={"children": [{"type": "a"}, {"type": "b"}]}))
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o6.json", [
        {"op": "insert", "path": ["children"], "index": 1, "value": {"type": "mid"}},
        {"op": "set", "path": ["fresh"], "value": "v", "create": True}])])
    _need(rc == 0, "合法整数下标与 create 真值 rc=%s" % rc)

    p = write("wg_o7.xwl", xwl.dumps_designer({"a": {"b": {"c": 1}}}))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o7.json", [
        {"op": "set", "path": "abc", "value": 2}])])
    _need(rc == 2 and _bytes(p) == before, "path 是字符串 rc=%s" % rc)

    p = write("wg_o8.xwl", xwl.dumps_designer(body))
    before = _bytes(p)
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o8.json", [
        {"op": "set", "path": ["children", True, "configs", "text"], "value": "z"}])])
    _need(rc == 2 and _bytes(p) == before, "path 段是布尔 rc=%s" % rc)

    p = write("wg_o9.xwl", xwl.dumps_designer(body))
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o9.json", [
        {"op": "set", "path": ["children", 0, "configs", "text"], "value": "z"}])])
    got0 = None
    try:
        got0 = xwl.parse_xwl(open(p, encoding="utf-8").read())
    except Exception:  # noqa: BLE001
        got0 = None
    _need(rc == 0 and isinstance(got0, dict)
          and got0["children"][0]["configs"]["text"] == "z",
          "整数下标 0 未落到第一项 rc=%s" % rc)

    p = write("wg_o10.xwl", xwl.dumps_designer(body))
    rc, out = _cli(["patch", p, "--ops", _ops("wg_o10.json", [
        {"op": "set", "path": ["children", 1, "configs", "text"], "value": "z"}])])
    got = None
    try:
        got = xwl.parse_xwl(open(p, encoding="utf-8").read())
    except Exception:  # noqa: BLE001
        got = None
    _need(rc == 0 and isinstance(got, dict)
          and got["children"][1]["configs"]["text"] == "z",
          "整数下标未落到第二项 rc=%s" % rc)

    raised = False
    try:
        xwl.parse_xwl('{"a":1e999}')
    except ValueError:
        raised = True
    _need(raised, "溢出字面量未抛")

    raised = False
    try:
        xwl.parse_xwl('{"a":NaN}')
    except ValueError:
        raised = True
    _need(raised, "NaN 字面量未抛")

    try:
        xwl.dumps_designer({"a": float("inf")})
        _need(False, "无穷大被序列化")
    except xwl.XwlWriteError:
        pass

    ok_rt = True
    for lit in ("1e308", "-0.0", "0.0", "12345678901234567890"):
        src = '{"a":%s}' % lit
        try:
            a = xwl.parse_xwl(src)
            dumped = xwl.dumps_designer(a)
            b2 = xwl.parse_xwl(dumped)
        except Exception:  # noqa: BLE001
            ok_rt = False
            break
        if lit == "-0.0":
            ok_rt = ok_rt and _math.copysign(1.0, a["a"]) < 0 and _math.copysign(1.0, b2["a"]) < 0
        else:
            ok_rt = ok_rt and a == b2
        ok_rt = ok_rt and dumped == xwl.dumps_designer(b2)
    _need(ok_rt, "有限值进出往返不一致")

    if node:
        p = write("wg_post.xwl", _page({"click": "function("}))
        rc, out = _cli(["patch", p, "--no-js", "--ops", _ops("wg_post.json", [
            {"op": "set", "path": ["children", 0, "events", "click"], "value": "function("}])])
        _need(rc == 0 and "已写入" in out, "写后采集前置未写入 rc=%s" % rc)
        detail: dict = {}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            prc = xwl.cmd_check(type("NS", (), {
                "files": [p], "node": node, "no_js": False, "no_itemid": True,
                "checks": {6}, "js_detail": detail,
            })())
        evs = ((detail.get("js") or {}).get("events") or [])
        _need(prc == 1 and any(e.startswith("children[0]#click ") for e in evs),
              "写后采集未走显示串：%r" % (evs,))
        shown = buf.getvalue()
        _need("⑥ events.click" in shown, "写后对外错误行改了口吻：%s" % shown[-240:])
        clash = {"box": {
            "a.b.c": {"events": {"click": "function("}},
            "a.b": {"c": {"events": {"click": "function("}}},
            "a": {"b": {"c": {"events": {"click": "function("}}}},
        }}
        p2 = write("wg_post2.xwl", xwl.dumps_designer(clash))
        detail2: dict = {}
        with contextlib.redirect_stdout(io.StringIO()):
            xwl.cmd_check(type("NS", (), {
                "files": [p2], "node": node, "no_js": False, "no_itemid": True,
                "checks": {6}, "js_detail": detail2,
            })())
        evs2 = ((detail2.get("js") or {}).get("events") or [])
        joined = " | ".join(evs2)
        _need("box.a.b.c#click " in joined
              and "box.a.b.c#click#2 " in joined
              and "box.a.b.c#click#3 " in joined,
              "同渲染撞名未加后缀：%r" % (evs2,))
    else:
        print("[note] 未执行 1 条（Node 不可用）：G20a-前置（--no-js 已写入）")

    # 备份目录不可写：chmod 之后先探测，目录真写不进去才算环境成立。
    try:
        sub = os.path.join(tmp, "wg_rodir")
        os.makedirs(sub, exist_ok=True)
        p = os.path.join(sub, "f.xwl")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(_page())
        before = _bytes(p)
        os.chmod(sub, 0o555)
        held = False
        try:
            with open(os.path.join(sub, "probe.tmp"), "w", encoding="utf-8") as fh:
                fh.write("x")
        except OSError:
            held = True
        if not held:
            print("[note] 未执行：Windows 目录位无效")
        else:
            rc, out = _cli(["patch", p, "--backup", "--ops", _ops("wg_g8.json", [
                {"op": "set", "path": ["title"], "value": "z"}])])
            _need(rc == 2 and _bytes(p) == before, "备份目录不可写仍写了目标 rc=%s" % rc)
    finally:
        try:
            os.chmod(os.path.join(tmp, "wg_rodir"), 0o777)
        except OSError:
            pass

    if node:
        p = write("wg_g20.xwl", _page({"click": "function("}))
        before = _bytes(p)
        real = xwl._js_verdicts
        seen = {"n": 0}

        def _err(node_exe, codes):
            seen["n"] += 1
            if seen["n"] == 1:
                return ["ok" for _c in codes]
            return ["error:injected node failure" for _c in codes]

        xwl._js_verdicts = _err
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = xwl.cmd_patch(type("NS", (), {
                    "file": p, "ops": _ops("wg_g20.json", [
                        {"op": "set", "path": ["title"], "value": "after"}]),
                    "eol": "auto", "indent": 1, "dry_run": False, "backup": False,
                    "node": node, "no_js": False, "allow_new_key": False,
                })())
        finally:
            xwl._js_verdicts = real
        text = buf.getvalue()
        wrote = _bytes(p) != before
        _need(rc == 1 and wrote and "已写入" in text and "写后" in text and "未写入" not in text,
              "写后 node 故障未按已写入回报 rc=%s wrote=%s" % (rc, wrote))
    else:
        print("[note] 未执行：Node 不可用")

    p = write("wg_ro.xwl", _page())
    before = _bytes(p)
    try:
        os.chmod(p, 0o444)
        if os.access(p, os.W_OK):
            print("[note] 本机只读位不生效，目标只读未计入必红")
        else:
            rc, out = _cli(["patch", p, "--backup", "--ops", _ops("wg_ro.json", [
                {"op": "set", "path": ["title"], "value": "z"}])])
            named = (".bak 已生成" in out) or (".bak 未生成" in out)
            _need(rc == 2 and "Traceback" not in out and "[FAIL]" in out and named
                  and _bytes(p) == before, "目标只读未按预期拒绝 rc=%s" % rc)
    finally:
        try:
            os.chmod(p, 0o666)
        except OSError:
            pass

    # 备份轮换失败：注入 os.rename 抛 PermissionError（errno 不能是 EEXIST、winerror 不能是 183，
    #   否则会被当成「撞名重试」）。这条**不依赖目录只读位**，任何平台都能跑。
    real_rename = xwl.os.rename

    def _deny(*_a, **_k):
        raise PermissionError(13, "Permission denied")

    p = write("wg_bakfail.xwl", _page())
    with open(p + ".bak", "wb") as fh:
        fh.write(b"OLD")
    before = _bytes(p)
    _ops_p = _ops("wg_bakfail.json", [{"op": "set", "path": ["title"], "value": "z"}])
    xwl.os.rename = _deny
    try:
        _raised = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                xwl.cmd_patch(type("NS", (), {
                    "file": p, "ops": _ops_p, "eol": "auto", "indent": 1,
                    "dry_run": False, "backup": True, "node": None,
                    "no_js": True, "allow_new_key": False,
                })())
        except xwl.XwlWriteError:
            _raised = True
        _buf2 = io.StringIO()
        with contextlib.redirect_stdout(_buf2):
            _rc2 = xwl.main(["patch", p, "--backup", "--no-js", "--ops", _ops_p])
    finally:
        xwl.os.rename = real_rename
    _txt2 = _buf2.getvalue()
    _need(_raised and _rc2 == 2 and _bytes(p) == before and "备份失败" in _txt2,
          "备份轮换失败未按 rc=2 拒绝（cmd_patch 抛出=%s rc=%s）" % (_raised, _rc2))

    if bad:
        failures.extend(bad)
    else:
        print("[ok]  写前门禁后半抽查通过")

