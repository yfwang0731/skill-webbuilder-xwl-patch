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

@_cap
def _s1s3_named_cases(tmp) -> list:
    """序1-3 具名正反例（定向矩阵）：返回失败条目列表（空=全绿）。

    覆盖：序1 请求级 params 归属（A的load/自身params不为B背书、B自身params/out直调ok、动态仅未知、
    缺参与未知并存、占位与builtin豁免）；序2 sqlrefs 真实供给识别（注释/字符串/其他接收者不算、
    真实与空白调用算、动态=可能提供）；序3 判空与逐项诊断（无适用内容rc1、select 1 rc0、
    serverScript含禁止{#..#}逐项打印、加载失败rc2）。
    """
    fail: list[str] = []
    d = os.path.join(tmp, "s1s3")
    os.makedirs(d, exist_ok=True)
    boundary_note = (
        "[note] 本检查仅作文件内静态供给集合核对；不证明供给调用必经执行、消费前时序、分支或"
        "跨 module 生命周期有效。"
    )

    def _check_boundary(out, where, expected):
        count = out.splitlines().count(boundary_note)
        if count != (1 if expected else 0):
            fail.append("%s 证明边界 note 次数=%d（应%r）" % (
                where, count, 1 if expected else 0))
            return
        if expected:
            lines = out.splitlines()
            pos = lines.index(boundary_note)
            if pos + 1 >= len(lines) or not lines[pos + 1].startswith("=== 结果:"):
                fail.append("%s 证明边界 note 不在统一结果行之前" % where)

    def _w(path, obj):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(xwl.dumps_designer(obj, 1, CRLF))

    def _carrier(name, sql="select 1", ss="var x='';\nrequest.setAttribute('sql', x);"):
        dp = {"configs": {"itemId": "dp"}, "type": "dataprovider", "expanded": False, "children": []}
        if sql is not None:
            dp["configs"]["sql"] = sql
        p = os.path.join(d, name + ".xwl")
        _w(p, {"title": "c", "children": [{"configs": {"itemId": "mod", "serverScript": ss},
                                           "type": "module", "expanded": False, "children": [dp]}]})
        return p

    def _page(name, stores, events=None):
        tbar = [{"configs": {"itemId": "kw"}, "type": "text", "expanded": False, "children": []}]
        gc = []
        for st in stores:
            cfg = {"itemId": st["itemId"]}
            for k in ("url", "params"):
                if st.get(k) is not None:
                    cfg[k] = st[k]
            gc.append({"configs": cfg, "type": "store", "expanded": False, "children": []})
        btns = [{"configs": {"itemId": iid}, "type": "button", "expanded": False, "children": [],
                 "events": {"click": js}} for iid, js in (events or {}).items()]
        p = os.path.join(d, name + ".xwl")
        _w(p, {"title": "page", "children": [
            {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False, "children": [
                {"configs": {"itemId": "tbar"}, "type": "toolbar", "expanded": False, "children": tbar},
                {"configs": {"itemId": "grid1"}, "type": "grid", "expanded": False, "children": gc},
            ] + btns}]})
        return p

    _carrier("bSql", sql="select * from tb where id={?NEED?}")
    _carrier("aSql", sql="select 1")

    # 序1-1：A显式load供给不为B背书；默认rc0；strict rc1
    p = _page("p1", [{"itemId": "storeA", "url": "m?xwl=aSql"}, {"itemId": "storeB", "url": "m?xwl=bSql"}],
              {"bA": "app.storeA.load({ params: { NEED: app.kw.getValue() } });"})
    rc, o = _run(xwl.cmd_params, file=p, module_root=d, controls=None, list_fields=False)
    if rc != 0 or "缺参" not in o or "NEED" not in o:
        fail.append("序1-1 A显式load不为B背书 默认(rc=%r)" % rc)
    rc, o = _run(xwl.cmd_params, file=p, module_root=d, controls=None, list_fields=False, strict=True)
    if rc != 1 or "确缺参" not in o:
        fail.append("序1-1 A显式load不为B背书 strict(rc=%r)" % rc)

    # 序1-2：B自身params供给 ⇒ strict rc0
    p = _page("p2", [{"itemId": "storeB", "url": "m?xwl=bSql", "params": "{NEED: app.kw.getValue()}"}])
    rc, o = _run(xwl.cmd_params, file=p, module_root=d, controls=None, list_fields=False, strict=True)
    if rc != 0:
        fail.append("序1-2 B自身params供NEED strict(rc=%r)" % rc)

    # 序1-3：动态目标 ⇒ 仅未知 strict rc2
    p = _page("p3", [{"itemId": "storeB", "url": "m?xwl=bSql"}],
              {"b1": "Wb.request({ url: dynUrl, params: { NEED: 1 } });"})
    rc, o = _run(xwl.cmd_params, file=p, module_root=d, controls=None, list_fields=False, strict=True)
    if rc != 2 or "未核对" not in o:
        fail.append("序1-3 动态目标仅未知 strict(rc=%r)" % rc)

    # 序2：注释唯一供给 ⇒ rc1；其他接收者 ⇒ rc1；真实 ⇒ rc0；空白 ⇒ rc0；动态 ⇒ 可能提供
    for nm, ss, want in (
        ("c", "// request.setAttribute('x', 1);\nvar a='';", 1),
        ("o", "foo.setAttribute('x', 1);", 1),
        ("r", "request.setAttribute('x', 1);", 0),
        ("w", "request.setAttribute ('x', 1);", 0),
    ):
        p = _carrier("sr_" + nm, sql="select {#x#} from t", ss=ss)
        rc, o = _run(xwl.cmd_sqlrefs, file=p)
        if rc != want:
            fail.append("序2-供给[%s] rc=%r(应%r)" % (nm, rc, want))
        _check_boundary(o, "序2-供给[%s]" % nm, True)
    p = _carrier("sr_dyn", sql="select {#x#} from t", ss="request.setAttribute(name, 1);")
    rc, o = _run(xwl.cmd_sqlrefs, file=p)
    if rc != 1 or "可能提供" not in o:
        fail.append("序2-动态可能提供 rc=%r" % rc)
    _check_boundary(o, "序2-动态可能提供", True)

    # 序3：无适用内容 rc1；空dataprovider rc1；select 1 rc0；serverScript含禁止逐项 rc1；加载失败 rc2
    p = os.path.join(d, "e0.xwl"); _w(p, {"title": "e", "children": []})
    rc, o = _run(xwl.cmd_sqlrefs, file=p)
    if rc != 1 or "无适用检查内容" not in o:
        fail.append("序3-无适用内容 rc=%r" % rc)
    _check_boundary(o, "序3-无适用内容", False)
    p = os.path.join(d, "e1.xwl"); _w(p, {"title": "e", "children": [
        {"configs": {"itemId": "d", "sql": "select 1"}, "type": "dataprovider",
         "expanded": False, "children": []}]})
    rc, o = _run(xwl.cmd_sqlrefs, file=p)
    if rc != 0:
        fail.append("序3-select1 rc=%r(应0)" % rc)
    _check_boundary(o, "序3-select1", True)
    p = os.path.join(d, "e2.xwl"); _w(p, {"title": "e", "children": [
        {"configs": {"itemId": "m", "serverScript": "var a='{#bad#}';"}, "type": "module",
         "expanded": False, "children": []}]})
    rc, o = _run(xwl.cmd_sqlrefs, file=p)
    if rc != 1 or "{#…#}" not in o:
        fail.append("序3-serverScript禁止引用逐项 rc=%r" % rc)
    _check_boundary(o, "序3-serverScript禁止引用", True)
    if boundary_note in o:
        problem_pos = o.find("{#…#}")
        note_pos = o.find(boundary_note)
        if problem_pos < 0 or note_pos < problem_pos:
            fail.append("序3-serverScript禁止引用：note 盖在具体 [FAIL] 诊断之前")
    p = os.path.join(d, "e3.xwl")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write("{not json")
    rc, o = _run(xwl.cmd_sqlrefs, file=p)
    if rc != 2:
        fail.append("序3-加载失败 rc=%r(应2)" % rc)
    _check_boundary(o, "序3-加载失败", False)
    return fail

@_cap
def _check_subcommands(tmp, node, failures, write) -> None:
    """子命令冒烟 paths/sqlrefs/params + new + folders + paths 原路径 + schema 骨架（第 12~16 组）"""

    # ---- 12. 子命令冒烟：paths / sqlrefs / params 真跑一遍（防“改了内部函数名漏改调用”）----
    page_obj = {"title": "参数页", "children": [
        {"configs": {"itemId": "viewport"}, "expanded": False, "type": "viewport", "children": [
            {"configs": {"itemId": "tbar"}, "expanded": False, "type": "toolbar", "children": [
                {"configs": {"itemId": "kw", "fieldLabel": "关键字"}, "expanded": False,
                 "children": [], "type": "text"},
                {"configs": {"itemId": "queryBtn", "text": "查询"}, "expanded": False,
                 "children": [], "type": "button",
                 "events": {"click": "app.grid1.store.load({ out: app.tbar });"}},
            ]},
            {"configs": {"itemId": "grid1"}, "expanded": False, "type": "grid", "children": [
                {"configs": {"itemId": "gridStore", "url": "m?xwl=demo/xxxSql/demoSql"},
                 "expanded": False, "children": [], "type": "store"},
            ]},
        ]},
    ]}
    page_path = os.path.join(tmp, "page_smoke.xwl")
    with open(page_path, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(page_obj, 1, CRLF))

    smoke_fail = []
    for label, fn, kw, want, want_rc in (
        ("paths",   xwl.cmd_paths,   {"file": page_path}, "原路径", 0),
        # 本夹具只有 store url、无 module/dataprovider ⇒ **无适用检查内容** ⇒ rc=1
        #   （公开退出码表「空结果判 1」真实落在此断言；want="" 且不断言 rc 时契约无人守）。
        ("sqlrefs", xwl.cmd_sqlrefs, {"file": page_path}, "无适用检查内容", 1),
        ("params",  xwl.cmd_params,  {"file": page_path, "module_root": tmp,
                                      "controls": None, "list_fields": False}, "kw", 0),
        ("itemids", xwl.cmd_itemids, {"file": page_path, "name": None, "dups_only": True,
                                      "suggest": False, "fix": "auto", "controls": None,
                                      "json": False}, "重名组", 0),
        # dump 曾是 14 个子命令里唯一没被冒烟覆盖的（评审发现）
        ("dump",    xwl.cmd_dump,    {"file": page_path}, "itemId", 0),
    ):
        try:
            _code, out = _run(fn, **kw)
        except Exception as exc:  # noqa: BLE001
            smoke_fail.append("%s 抛异常: %s: %s" % (label, type(exc).__name__, exc))
            continue
        if want and want not in out:
            smoke_fail.append("%s 输出里没有 %r" % (label, want))
        if want_rc is not None and _code != want_rc:
            smoke_fail.append("%s rc=%r（应 %r）" % (label, _code, want_rc))
    if smoke_fail:
        failures.extend(smoke_fail)
    else:
        print("[ok]  子命令冒烟：paths / sqlrefs / params / itemids 均可直接调用（含真实 rc 断言）")

    # ---- 12c. 序1-3 具名正反例（请求级归属 / 真实供给识别 / 判空与逐项诊断）----
    #   定向负例：改坏判据即可被这些断言检出（旧全局 provided、裸 setAttribute 正则、空结果 rc）。
    _s13_fail = _s1s3_named_cases(tmp)
    if _s13_fail:
        failures.extend(_s13_fail)
    else:
        print("[ok]  序1-3 具名正反例：请求级归属 / 真实供给识别 / 判空与逐项诊断（定向矩阵）")

    # ---- 12b. sql / events / dump 的**命令级**断言（原来 sql/events 无任何断言、dump 仅冒烟）----
    # 起因（仪表审计实测三例"全绿但行为已坏"）：判据收紧 ⇒ `sql` 漏抽 `totalSql`（`[1/2]`→`[1/1]`）；
    #   `events --outdir` 不再自建目录 ⇒ 导出到新目录直接 rc=2；`dump` 去掉美化缩进 ⇒ 多行变 1 行。
    #   三者旧自检**零信号**（`sql`/`events` 完全无断言、`dump` 只查"输出含 itemId"）。
    #   ⇒ 补命令级断言：`sql` 必须抽全（含键名含 `sql` 的 `totalSql`）、`events --outdir` 指向
    #   **不存在的新目录**须自建并成功、`dump` 必须**多行**（保"按加载器规则美化输出"的用途）。
    #   ⚠️ 三条一律经 `_run_cli(...)`（**子进程跑真 CLI**）取值 —— **不许**直调 `_run(xwl.cmd_*)`：
    #     直调时被测行为一旦抛异常，异常冲出 `_run` ⇒ 下面那条**定向断言根本没跑到**
    #     （实测：`events --outdir` 不自建目录 ⇒ `XwlWriteError`）。
    #     ⚠️ 机制纠偏：`_run_block` 有兜底 ⇒ 普通异常／`SystemExit` 被兜住、红行**点名该块**
    #       （「块 X 内抛出 …」；并行档 worker 硬崩／re-raise 则记「块 X 的子进程异常退出（rc=N）」）；
    #       但 `KeyboardInterrupt`／`MemoryError`／`SystemError` 仍 re-raise ⇒ **串行档**下整进程退出、
    #       连汇总行都没有（异常不落地成失败条目，只剩调用栈）⇒ ⛔ 别读成"所有异常都被兜住"。
    #       而"定向断言仍未跑到"照旧成立 —— 兜底只让失败可读，⛔ 不替你跑断言。
    #     经 CLI 则拿**真实退出码**、异常被进程隔离 ⇒ 红行**必落在定向断言上**（见 `_run_cli` docstring）。
    ce_fail: list[str] = []
    _ce_obj = {"title": "ce页", "children": [
        {"configs": {"itemId": "dp", "sql": "select 1 from dual",
                     "totalSql": "select count(1) from dual"},
         "type": "dataprovider", "expanded": False, "children": []},
        {"configs": {"itemId": "btn"}, "type": "button", "expanded": False, "children": [],
         "events": {"click": "app.btn.setDisabled(true);"}},
    ]}
    _ce_page = os.path.join(tmp, "ce_page.xwl")
    with open(_ce_page, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(_ce_obj, 1, CRLF))
    _rc_s, _out_s, _err_s = _run_cli(["sql", _ce_page])
    if _rc_s != 0:
        ce_fail.append("sql 对含 2 条 SQL 的页面 rc=%s（应 0）：\n%s" % (_rc_s, _cli_text(_out_s, _err_s)))
    if "[1/2]" not in _out_s or "[2/2]" not in _out_s:
        ce_fail.append("sql 未把两条 SQL 都抽出（应见 [1/2] 与 [2/2]）：\n%s" % _out_s)
    if "totalSql" not in _out_s or "select count(1) from dual" not in _out_s:
        ce_fail.append("sql 漏抽 totalSql（判据是「键名**含** sql」，不是「以 sql 开头」）：\n%s" % _out_s)
    _ev_new = os.path.join(tmp, "ce_events_out")     # 故意指向**不存在**的新目录
    _rc_e, _out_e, _err_e = _run_cli(["events", _ce_page, "--outdir", _ev_new])
    if _rc_e != 0:
        ce_fail.append("events --outdir 指向新目录 rc=%s（应 0：工具须自建目录）：\n%s"
                       % (_rc_e, _cli_text(_out_e, _err_e)))
    if not os.path.isdir(_ev_new):
        ce_fail.append("events --outdir 未创建导出目录")
    elif not [n for n in os.listdir(_ev_new) if n.endswith(".js")]:
        ce_fail.append("events --outdir 目录里没有导出任何 .js")
    _rc_d, _out_d, _err_d = _run_cli(["dump", _ce_page])
    if _rc_d != 0:
        ce_fail.append("dump rc=%s（应 0）" % _rc_d)
    if len(_out_d.splitlines()) <= 1:
        ce_fail.append("dump 输出只有 %d 行（应 >1：dump 的用途是**美化**输出）" % len(_out_d.splitlines()))
    if ce_fail:
        failures.extend(ce_fail)
    else:
        print("[ok]  sql / events / dump 命令级：sql 抽全 2 条（含 totalSql）、"
              "events --outdir 自建新目录并落文件、dump 多行美化")

    # ---- 12c/12d/12e：events 落点与命名、expand --backup、--outdir 前置错误 ----
    #   这三段合起来约 280 行；`_check_subcommands` 已顶到 399/400（上限 400，⛔ 不许调高）
    #   ⇒ 单独成函数。⚠️ 判据文本逐字未改，只换了宿主。
    _check_events_and_expand(tmp, failures)
    # 跳链护栏：三跳里任一跳被删，下游断言会整段静默消失（行为面查不出来）⇒ 只能守形状。
    failures.extend(_block_chain_fails())
    # 尾段能执行到这里，才算这一跳完成。中途 return 时父进程会保持「未选择」，门禁下不得当通过。
    if REQUIRE_ALL:
        _mark_sub(_SUBCHECKS, "chain.tail", "通过", "subcommands 尾段已执行")

def _block_chain_fails() -> list[str]:
    """三跳调用链的**形状断言**：`_check_subcommands` → `_check_events_and_expand` → `_check_subcommands_tail`。

    为什么只能守形状（与 `_fn_cap_check` 同族、⛔ 不得用它替代行为判据）：三段都是"跑断言"的函数体，
    任何一跳被删，下游断言会**整段静默消失**而自检照绿 —— 没有行为面能把"少跑了一段"变成红。
    ⚠️ 判据是 `ast.Call` 的 `func.id`，比 `grep` 稳（注释/字符串里出现同名不会误判）。
    """
    import ast as _ast
    try:
        with io.open(os.path.abspath(__file__), encoding="utf-8", newline="") as _fh:
            _tree = _ast.parse(_fh.read())
    except (OSError, SyntaxError) as _exc:
        return ["块间跳链：读不出/解析不了 selftest.py（%s）⇒ 不敢判" % (_exc,)]
    _bodies = {n.name: n for n in _tree.body if isinstance(n, _ast.FunctionDef)}

    def _calls(_fn: str, _target: str) -> bool:
        _node = _bodies.get(_fn)
        if _node is None:
            return False
        return any(isinstance(_c, _ast.Call) and isinstance(_c.func, _ast.Name)
                   and _c.func.id == _target for _c in _ast.walk(_node))

    _out = []
    if not _calls("_check_subcommands", "_check_events_and_expand"):
        _out.append("块间跳链断了：`_check_subcommands` 函数体里没有 `_check_events_and_expand(...)` 调用")
    if not _calls("_check_events_and_expand", "_check_subcommands_tail"):
        _out.append("块间跳链断了：`_check_events_and_expand` 函数体里没有 `_check_subcommands_tail(...)` 调用")
    return _out

@_cap
def _check_events_and_expand(tmp, failures) -> None:
    """`events` 落点/命名 ＋ `expand --backup` ＋ `--outdir` 前置错误（12c/12d/12e）。

    只依赖 `tmp` 与 `failures`，其余都是模块级名字。
    """
    # 本函数有两处要 `mock` 与 `ast`（跨盘桩、调用点形状断言、realpath 次数），就近引入一次。
    import ast as _ast
    from unittest import mock as _umock

    # ---- 12c. events 的**落点**与**命名**（文件名来自数据 ⇒ 落点必须独立校验）----
    #   起因（删了会怎样）：事件键直接拼进文件名 ⇒ 键里带 `../` 就能把 `.js` 写到 `--outdir`
    #   之外；而"名字已白名单化"只防**输入**（名字里没有分隔符），防不了平台层让同一个安全名
    #   指向目录外（符号链接 / 短名 / 大小写折叠）⇒ 落点要有一道**独立**校验。
    #   两套夹具**各管一件事**（⛔ 不混用，否则红了归因不唯一）：
    #     · 夹具 A：只放 1 个逃逸键，专测**落点**（outdir 的父目录不许新增、探针字节不许变）；
    #     · 夹具 B：4 个键，专测**命名与索引行**（这一份不要求逃逸）。
    ev_fail: list[str] = []
    _ea_dir = os.path.join(tmp, "ce_ev_escape")
    os.makedirs(_ea_dir, exist_ok=True)
    _ea_out = os.path.join(_ea_dir, "out")          # 故意指向**不存在**的新目录
    _ea_probe = os.path.join(_ea_dir, "probe.txt")  # outdir 的**父目录**里的探针（越界就写这儿旁边）
    with open(_ea_probe, "wb") as _f:
        _f.write(b"probe-keep-me")
    _ea_md5 = hashlib.md5(open(_ea_probe, "rb").read()).hexdigest()
    # ⚠️ 快照必须在**夹具写完、CLI 跑之前**取 —— 否则 `ev_a.xwl` 与自建的 `out/` 会被当成"新增"。
    # ⚠️ 逃逸键为什么要**三层** `..`：文件名的前缀 `event_1_` 会吃掉第一个 `..`（它先拼进
    #   同一段名里），`../../evil` 规范化后仍落在 outdir 内 ⇒ 测不到越界。
    _ea_xwl = os.path.join(_ea_dir, "ev_a.xwl")
    with open(_ea_xwl, "w", encoding="utf-8", newline="") as _f:
        _f.write(xwl.dumps_designer({"title": "逃逸页", "children": [
            {"configs": {"itemId": "btn"}, "type": "button", "expanded": False, "children": [],
             "events": {"../../../evil": "var x = 1;"}}]}, 1, CRLF))
    _ea_before = sorted(os.listdir(_ea_dir))     # 夹具与 outdir 都还没跑 ⇒ 这里才是基线
    _rc_ea, _out_ea, _err_ea = _run_cli(["events", _ea_xwl, "--outdir", _ea_out])
    _ea_after = sorted(os.listdir(_ea_dir))
    # 父目录里"新增"的只允许是**自建的 outdir 本身**（导出目录当然会被创建）；其余任何新增都算越界。
    _ea_new = [n for n in _ea_after if n not in _ea_before and n != os.path.basename(_ea_out)]
    if _ea_new:
        ev_fail.append("events 把文件写到 `--outdir` **之外**（父目录新增 %s）：\n%s"
                       % (_ea_new, _cli_text(_out_ea, _err_ea)))
    if hashlib.md5(open(_ea_probe, "rb").read()).hexdigest() != _ea_md5:
        ev_fail.append("events 越界写改动了 outdir 外探针的字节")
    _ea_js = [n for n in (os.listdir(_ea_out) if os.path.isdir(_ea_out) else []) if n.endswith(".js")]
    if len(_ea_js) != 1:
        ev_fail.append("events 逃逸键场景下 outdir 里的 `.js` 应**恰好 1 个**，实得 %s" % (_ea_js,))
    if _rc_ea != 0:
        ev_fail.append("events 逃逸键场景 rc=%r（应 0：键只作标签、不该失败）：\n%s"
                       % (_rc_ea, _cli_text(_out_ea, _err_ea)))

    # 夹具 B：命名 + 清单。⚠️ 期望值**手推**（白名单 `[A-Za-z0-9_-]` / 不保留 `.` / 全被替换则省略
    #   标签段），⛔ 不许用被测助手现算 —— 那是自证循环（白名单写错两边一起错而"相等"）。
    _eb_dir = os.path.join(tmp, "ce_ev_name")
    os.makedirs(_eb_dir, exist_ok=True)
    _eb_out = os.path.join(_eb_dir, "out")
    _eb_keys = ("../../evil", "a/b", "click", "中文")
    _eb_xwl = os.path.join(_eb_dir, "ev_b.xwl")
    with open(_eb_xwl, "w", encoding="utf-8", newline="") as _f:
        _f.write(xwl.dumps_designer({"title": "命名页", "children": [
            {"configs": {"itemId": "btn"}, "type": "button", "expanded": False, "children": [],
             "events": {k: "var x = 1;" for k in _eb_keys}}]}, 1, CRLF))
    _rc_eb, _out_eb, _err_eb = _run_cli(["events", _eb_xwl, "--outdir", _eb_out])
    _eb_want = {"event_1_______evil.js", "event_2_a_b.js", "event_3_click.js", "event_4.js"}
    _eb_got = set(os.listdir(_eb_out)) if os.path.isdir(_eb_out) else set()
    if _eb_got != _eb_want:
        ev_fail.append("events 导出文件名与**独立规格**不符\n  实得 %s\n  期望 %s\n%s"
                       % (sorted(_eb_got), sorted(_eb_want), _cli_text(_out_eb, _err_eb)))
    _idx = [ln for ln in _out_eb.splitlines() if "← 原事件键：" in ln]
    if len(_idx) != 4:
        ev_fail.append("events 的「← 原事件键：」索引行应 4 行，实得 %d：\n%s" % (len(_idx), _out_eb))
    _got_json = [ln.split("← 原事件键：", 1)[1].strip() for ln in _idx]
    _want_json = [json.dumps(k, ensure_ascii=False) for k in _eb_keys]
    if sorted(_got_json) != sorted(_want_json):
        ev_fail.append("索引行里的原事件键不是 JSON 字符串表示（`ensure_ascii=False`）\n"
                       "  实得 %s\n  期望 %s" % (sorted(_got_json), sorted(_want_json)))
    for _ln in _idx:
        if _ln.lstrip().startswith("[ok]") or _ln.lstrip().startswith("[note]"):
            ev_fail.append("索引行被加了输出标记（会进本仓文案面）：%s" % _ln)
    # 「每个文件**后**跟一行」——只数总数不够：把索引行全挤到末尾也满足"共 4 行"（实测过）。
    #   判据：每出现一行"路径行"（两空格 + 非空白），**下一行**必须是索引行。
    _eb_lines = _out_eb.splitlines()
    _pair_bad = []
    for _i, _ln in enumerate(_eb_lines):
        if _ln.startswith("  ") and not _ln.lstrip().startswith("←") and _ln.strip():
            _nxt = _eb_lines[_i + 1] if _i + 1 < len(_eb_lines) else ""
            if "← 原事件键：" not in _nxt:
                _pair_bad.append(_ln.strip())
    if _pair_bad:
        ev_fail.append("索引行没有紧跟在其对应文件之后（应逐文件相邻）：%s" % (_pair_bad[:3],))

    # 「截断到 60」——标签上限改大也全绿过：用直调把边界钉住（期望值**手推**）。
    _tag60 = xwl._event_file_tag("a" * 70)
    if _tag60 != "a" * 60:
        ev_fail.append("安全标签没截断到 60（实得 %d 字符）" % len(_tag60))

    # 「无 events 节点」的老行为（rc=1）不许被顺手改成 0/2。
    _noev = os.path.join(tmp, "ce_ev_none.xwl")
    with open(_noev, "w", encoding="utf-8", newline="") as _f:
        _f.write(xwl.dumps_designer({"title": "空事件页", "children": []}, 1, CRLF))
    _rc_ne, _out_ne, _err_ne = _run_cli(["events", _noev])
    if _rc_ne != 1:
        ev_fail.append("无 events 节点时 rc=%r（应 1）：%s" % (_rc_ne, _cli_text(_out_ne, _err_ne)))
    if "无 events 节点" not in _err_ne:
        ev_fail.append("无 events 节点时没给提示（stderr 应含「无 events 节点」）：%s" % (_err_ne,))

    # 覆盖提示（`Q11`）：预置一个同名文件 ⇒ 必须打 `[note] 已存在、已覆盖`，且内容被替换。
    #   判据要**两条同时**：只判 note 会漏"note 打了但没真写"，只判内容会漏"静默覆盖"。
    _ov_dir = os.path.join(tmp, "ce_ev_overwrite")
    os.makedirs(_ov_dir, exist_ok=True)
    _ov_out = os.path.join(_ov_dir, "out")
    os.makedirs(_ov_out, exist_ok=True)
    _ov_xwl = os.path.join(_ov_dir, "ev_ov.xwl")
    with open(_ov_xwl, "w", encoding="utf-8", newline="") as _f:
        _f.write(xwl.dumps_designer({"title": "覆盖页", "children": [
            {"configs": {"itemId": "btn"}, "type": "button", "expanded": False, "children": [],
             "events": {"click": "var x = 1;"}}]}, 1, CRLF))
    _ov_stale = os.path.join(_ov_out, "event_1_click.js")
    with open(_ov_stale, "w", encoding="utf-8", newline="") as _f:
        _f.write("STALE-USER-FILE")
    _rc_ov, _out_ov, _err_ov = _run_cli(["events", _ov_xwl, "--outdir", _ov_out])
    if _rc_ov != 0:
        ev_fail.append("覆盖场景 rc=%r（应 0）：\n%s" % (_rc_ov, _cli_text(_out_ov, _err_ov)))
    if "[note] 已存在、已覆盖" not in _out_ov:
        ev_fail.append("覆盖已存在文件时没打 `[note] 已存在、已覆盖`（静默覆盖）：\n%s" % _out_ov)
    if open(_ov_stale, "r", encoding="utf-8", newline="").read() == "STALE-USER-FILE":
        ev_fail.append("预置的同名文件没被新内容替换（提示与实际不一致）")

    # `Q12`：`realpath(outdir)` 只在循环外算一次 ⇒ `os.path.realpath` 调用次数必须恰为 `1 + N`。
    #   ⚠️ **先有这条次数断言，再谈缓存**：没有它，"缓存"很容易退化成"跳过每个文件的校验"。
    #   ⚠️ 只数 `realpath`，⛔ 别把 `abspath` 也算进去（`_ensure_within` 里两者都有，数错会得 `2+2N`）。
    _rp_seen = []
    _rp_real = os.path.realpath

    def _rp_spy(_p, *a, **kw):
        _rp_seen.append(_p)
        return _rp_real(_p, *a, **kw)

    _q12_out = os.path.join(tmp, "ce_ev_realpath")
    with _umock.patch("os.path.realpath", _rp_spy):
        _q12_rc = xwl.cmd_events(type("NS", (), {"file": _eb_xwl, "outdir": _q12_out})())
    _q12_n = len(_eb_keys)                       # 夹具 B 有 4 个事件
    if _q12_rc != 0:
        ev_fail.append("`realpath` 次数场景 rc=%r（应 0）" % (_q12_rc,))
    if len(_rp_seen) != 1 + _q12_n:
        ev_fail.append("`os.path.realpath` 调用次数=%d（应 1＋%d＝%d）：outdir 应在循环外只算一次"
                       % (len(_rp_seen), _q12_n, 1 + _q12_n))

    # 落点校验本身（直调）：夹具 A 证明的是**清洗**，这条证明"清洗之后仍可能越界"那道防线还在。
    # ⚠️ 本机建符号链接报 `WinError 1314`（无权限）⇒ 不为它造真实链接，用 `..` 构造即可。
    try:
        xwl._ensure_within(_ea_out, os.path.join(_ea_out, "..", "x.js"))
        ev_fail.append("落点校验没拦住 `..` 越界（`_ensure_within` 未抛 XwlWriteError）")
    except xwl.XwlWriteError as _exc:
        if "落点越界" not in str(_exc):
            ev_fail.append("落点越界的报错文案里没有「落点越界」：%s" % _exc)
    except Exception as _exc:      # noqa: BLE001
        ev_fail.append("落点校验抛了非 XwlWriteError 的异常：%s: %s" % (type(_exc).__name__, _exc))
    # 单里 ⛔ 明令"不许用 `startswith` 判前缀"。只喂 `..` 分不出 `relpath` 与 `startswith`
    #   （实测：换成 startswith 的实现照样全绿）⇒ 补一个**近邻前缀**：`<out>2/x.js` 不是越界之外的另一回事，
    #   它必须被判**越界**（因为它确实不在 `<out>` 里）。
    try:
        xwl._ensure_within(_ea_out, _ea_out + "2" + os.sep + "x.js")
        ev_fail.append("落点校验对**近邻前缀**（`<out>2/x.js`）没拦住 —— `startswith` 式实现即此形态")
    except xwl.XwlWriteError:
        pass
    except Exception as _exc:      # noqa: BLE001
        ev_fail.append("近邻前缀校验抛了非 XwlWriteError 的异常：%s: %s" % (type(_exc).__name__, _exc))
    # 跨盘：`realpath` 解析后落在另一个驱动器 ⇒ `relpath` 抛 `ValueError`（单特意声明"不是死代码"）。
    #   ⚠️ 必须分两段验，否则这条断言**只会在 Windows 绿**（CI 实测：ubuntu 四组全红）：
    #     (a) **处理器**：桩住 `os.path.relpath` 直接抛 `ValueError` ⇒ 必须转成 `XwlWriteError`。
    #         POSIX 的 `relpath` 不认盘符，**不会**因跨盘抛错 ⇒ 只有桩住才验得到这一支；全平台可跑。
    #     (b) **真实触发**：ntpath 才会跨盘抛 `ValueError`，所以这一段只在 `os.name == "nt"` 跑，
    #         用桩把 **fp** 的 realpath 指到 D:（⛔ 不为它造跨盘真实文件）。
    with _umock.patch("os.path.relpath",
                      side_effect=ValueError("path is on mount 'D:', start on mount 'C:'")):
        try:
            xwl._ensure_within(_ea_out, os.path.join(_ea_out, "x.js"))
        except xwl.XwlWriteError:
            pass
        except Exception as _exc:      # noqa: BLE001
            ev_fail.append("跨盘校验抛了非 XwlWriteError 的异常：%s: %s"
                           % (type(_exc).__name__, _exc))
        else:
            ev_fail.append("跨盘（`relpath` 抛 `ValueError`）没被当成越界"
                           " —— `except ValueError` 这一支没接住")
    if os.name == "nt":
        _drive_fp = "C" + ":" + os.sep + "elsewhere" + os.sep + "x.js"
        try:
            with _umock.patch("os.path.realpath") as _rp:
                _rp.side_effect = (lambda p: ("D:" + os.sep + "elsewhere") if p == _drive_fp else _ea_out)
                xwl._ensure_within(_ea_out, _drive_fp)
            ev_fail.append("跨盘（另一个驱动器）没被当成越界")
        except xwl.XwlWriteError:
            pass
        except Exception as _exc:      # noqa: BLE001
            ev_fail.append("跨盘校验抛了非 XwlWriteError 的异常：%s: %s" % (type(_exc).__name__, _exc))
    # 调用点必须**在**：清洗已挡住所有可达输入 ⇒ 行为面造不出红，只能守形状（与 `_fn_cap_check` 同族）。
    _ce_src = io.open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), encoding="utf-8").read()
    _ce_fn = [n for n in _ast.parse(_ce_src).body
              if isinstance(n, _ast.FunctionDef) and n.name == "cmd_events"]
    _ce_has = any(
        isinstance(_c, _ast.Call) and isinstance(_c.func, _ast.Name) and _c.func.id == "_ensure_within"
        for _n in _ce_fn for _c in _ast.walk(_n))
    if not _ce_has:
        ev_fail.append("`cmd_events` 里没有调用 `_ensure_within`（落点防线被摘掉了）")
    for _lbl, _e in (("夹具 A", _err_ea), ("夹具 B", _err_eb)):
        if "Traceback" in (_e or ""):
            ev_fail.append("events（%s）stderr 冒了 traceback：%s" % (_lbl, _e))
    if ev_fail:
        failures.extend(ev_fail)
    else:
        print("[ok]  events：文件名只由「序号 + 安全标签」构成、落点独立校验拦得住 `..`、"
              "每个文件后跟一行「← 原事件键」")

    # ---- 12d. `expand --backup`：同文件判定按**路径 + 文件身份**，不按字符串相等 ----
    #   起因（删了会怎样）：`--out` 给的是同一文件的**别名**（同一路径里多一段 `./`）时，字符串相等判不出来
    #   ⇒ 该拍的 `.bak` 不拍、原文件被就地覆盖 —— 后果不是"备份写坏"，而是**唯一恢复点没了**。
    #   ⚠️ 能暴露旧缺陷的必要关系（三条同时成立，缺一条就测不到）：
    #     ① `--file` 与 `--out` 的**字符串不同**；② 两者**指向同一文件**；③ 真的写盘（非 dry-run）。
    #   ⇒ `expand <别名> --backup --out <别名>`（两个都给别名）**不满足**：字符串相等，
    #     旧代码照样拍备份 ⇒ 改前就绿。所以本段的用法固定为「`--file` 给原名、`--out` 给别名」。
    ex_fail: list[str] = []
    _flat = '{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}'
    _ex_c1 = os.path.join(tmp, "ce_ex_alias")
    os.makedirs(_ex_c1, exist_ok=True)
    _p1 = os.path.join(_ex_c1, "p.xwl")
    with open(_p1, "w", encoding="utf-8", newline="") as _f:
        _f.write(_flat)
    _p1_raw = open(_p1, "rb").read()
    _p1_alias = os.path.join(_ex_c1, ".", "p.xwl")   # 同一文件、**不同字符串**（`./` 段仍在串里）
    _rc_e1, _out_e1, _err_e1 = _run_cli(["expand", _p1, "--backup", "--out", _p1_alias, "--no-js"])
    if _rc_e1 != 0:
        ex_fail.append("expand --backup --out <别名> rc=%r（应 0）：\n%s"
                       % (_rc_e1, _cli_text(_out_e1, _err_e1)))
    if not os.path.exists(_p1 + ".bak"):
        ex_fail.append("`--out` 给同一文件的**别名**时没拍 `.bak`（原文件被就地覆盖 ⇒ 恢复点丢了）：\n%s"
                       % _cli_text(_out_e1, _err_e1))
    elif open(_p1 + ".bak", "rb").read() != _p1_raw:
        ex_fail.append("`.bak` 的字节 ≠ 原件原字节")
    _p1_now = open(_p1, "rb").read()
    if _p1_now == _p1_raw:
        ex_fail.append("expand 没改写原文件（夹具就不是单行压缩形态？）")
    elif len(_p1_now.decode("utf-8").splitlines()) <= 1:
        ex_fail.append("expand 的产出仍是单行（应扩成设计器多行形态）")

    # 写到**别的**文件：保持现语义（不拍备份、只覆盖那个文件）＋目标本来不存在时不许崩。
    _ex_c3 = os.path.join(tmp, "ce_ex_other")
    os.makedirs(_ex_c3, exist_ok=True)
    _p3 = os.path.join(_ex_c3, "p.xwl")
    with open(_p3, "w", encoding="utf-8", newline="") as _f:
        _f.write(_flat)
    _p3_raw = open(_p3, "rb").read()
    _new3 = os.path.join(_ex_c3, "new.xwl")          # 目标**不存在**（专治"用 samefile 不先判存在"）
    _rc_e3, _out_e3, _err_e3 = _run_cli(["expand", _p3, "--backup", "--out", _new3, "--no-js"])
    if _rc_e3 != 0:
        ex_fail.append("expand --out 指向别的文件 rc=%r（应 0）：\n%s"
                       % (_rc_e3, _cli_text(_out_e3, _err_e3)))
    if not os.path.exists(_new3):
        ex_fail.append("expand --out 指向别的文件时没生成目标")
    for _bad_bak in (_new3 + ".bak", _p3 + ".bak"):
        if os.path.exists(_bad_bak):
            ex_fail.append("`--out` 指向**别的**文件时不该拍备份，却生成了 %s" % _bad_bak)
    if open(_p3, "rb").read() != _p3_raw:
        ex_fail.append("`--out` 指向别的文件时，原文件字节被改了")

    # 硬链接别名：`./` 别名分辨不出"备份到 `file.bak` 还是 `dest.bak`"（两者是同一路径）。
    #   硬链接下这两个名字**不同** ⇒ 才能证明"备份名仍跟在 `--file` 上"。
    try:
        _p4 = os.path.join(_ex_c1, "hl.xwl")
        with open(_p4, "w", encoding="utf-8", newline="") as _f:
            _f.write(_flat)
        _p4_raw = open(_p4, "rb").read()
        _hl = os.path.join(_ex_c1, "hl_alias.xwl")
        os.link(_p4, _hl)
        _rc_e4, _out_e4, _err_e4 = _run_cli(["expand", _p4, "--backup", "--out", _hl, "--no-js"])
        if _rc_e4 != 0:
            ex_fail.append("硬链接别名 rc=%r（应 0）：\n%s" % (_rc_e4, _cli_text(_out_e4, _err_e4)))
        if not os.path.exists(_p4 + ".bak"):
            ex_fail.append("硬链接别名没按 `--file` 的名字拍 `.bak`（备份名跟着 `--out` 走了）")
        elif open(_p4 + ".bak", "rb").read() != _p4_raw:
            ex_fail.append("硬链接场景下 `.bak` 字节 ≠ 原件原字节")
        if os.path.exists(_hl + ".bak"):
            ex_fail.append("硬链接场景下多出了一份 `dest.bak`（备份名不该跟着 `--out` 走）")
    except OSError as _exc:
        ex_fail.append("硬链接夹具没造出来（%s）" % _exc)

    # `samefile` 抛 `OSError`（不支持/权限受限）时必须**退回规范化路径比较**，而不是判"不同文件"。
    try:
        with _umock.patch("os.path.samefile", side_effect=OSError("stub")):
            _sf_same = xwl._same_file(_p3, _p3)
        if not _sf_same:
            ex_fail.append("`samefile` 抛 OSError 时没退回规范化比较（同一文件竟判 False）"
                           " ⇒ 该拍备份的会被跳过")
    except Exception as _exc:      # noqa: BLE001
        ex_fail.append("`_same_file` 的 OSError 兜底跑不通：%s: %s" % (type(_exc).__name__, _exc))
    for _lbl, _e in (("别名同文件", _err_e1), ("写到别的文件", _err_e3)):
        if "Traceback" in (_e or ""):
            ex_fail.append("expand（%s）stderr 冒了 traceback：%s" % (_lbl, _e))
    if ex_fail:
        failures.extend(ex_fail)
    else:
        print("[ok]  expand --backup：`--out` 给同一文件的别名时按**文件身份**判、真拍 `.bak` 且字节一致；"
              "写到别的文件时不拍备份、原文件不动、目标不存在也不崩")

    # ---- 12e. `--outdir` 指到**普通文件**：必须走统一写盘出口，⛔ 不许冒 traceback ----
    #   起因（删了会怎样）：建目录那句原是**裸调用**，而 `main()` 只 catch `XwlWriteError`
    #   ⇒ 前置条件不满足时甩一段 Python traceback（本仓明令禁止）。
    #   ⚠️ 判据看 **rc==2 且文案点名「导出目录」**，⛔ 不判"非零"了事（别的失败也非零）。
    me_fail: list[str] = []
    _me_dir = os.path.join(tmp, "ce_ev_repbad")
    os.makedirs(_me_dir, exist_ok=True)
    _me_file = os.path.join(_me_dir, "not_a_dir")     # **普通文件**，不是目录
    with open(_me_file, "w", encoding="utf-8", newline="") as _f:
        _f.write("occupied")
    _me_xwl = os.path.join(_me_dir, "ev.xwl")
    with open(_me_xwl, "w", encoding="utf-8", newline="") as _f:
        _f.write(xwl.dumps_designer({"title": "占位页", "children": [
            {"configs": {"itemId": "btn"}, "type": "button", "expanded": False, "children": [],
             "events": {"click": "var x = 1;"}}]}, 1, CRLF))
    _rc_me, _out_me, _err_me = _run_cli(["events", _me_xwl, "--outdir", _me_file])
    if _rc_me != 2:
        me_fail.append("`--outdir` 指向普通文件时 rc=%r（应 2）：\n%s"
                       % (_rc_me, _cli_text(_out_me, _err_me)))
    if "[FAIL]" not in _out_me or "导出目录" not in _out_me:
        me_fail.append("`--outdir` 指向普通文件时的输出没走统一出口（应含 `[FAIL]` 与「导出目录」）：\n%s"
                       % _cli_text(_out_me, _err_me))
    if "Traceback" in ((_out_me or "") + (_err_me or "")):
        me_fail.append("`--outdir` 指向普通文件时冒了 traceback：\n%s" % _cli_text(_out_me, _err_me))
    # "走统一出口"与"自己 print 一句再 return 2"输出几乎一样 ⇒ 用 `main()` 的样板行做判据：
    #   只有**抛 XwlWriteError 交给 main** 才会有那三行「可能原因：…」（自己 return 的话没有）。
    if "可能原因" not in _out_me:
        me_fail.append("没走统一写盘出口（输出里缺 `main()` 对 XwlWriteError 的「可能原因：…」样板）")
    if open(_me_file, "r", encoding="utf-8", newline="").read() != "occupied":
        me_fail.append("`--outdir` 指向普通文件时，那个文件被改写了")
    if me_fail:
        failures.extend(me_fail)
    else:
        print("[ok]  events 的 `--outdir` 指到普通文件时走统一写盘出口（rc=2 ＋ 点名「导出目录」＋ 无 traceback）")

    # ---- 尾部（13. new … 17v）：整段下沉为模块级 `_check_subcommands_tail` ----
    #   起因：本函数实测 387 行、`_FN_CAP` 上限 400，余量只剩 13 行；本批要往本函数里加三段
    #   **命令级**断言（越界落点／备份同文件／目录前置错误）⇒ 先把尾段整段下沉，腾出预算。
    #   ⚠️ 判据文本**逐字未改**，只换了宿主；⛔ 不调 `_FN_CAP`、⛔ 不从 `_CAP_FNS` 删名字。
    _check_subcommands_tail(tmp, failures)

def _folders_f12_cases(tmp):
    """F12：`folders` 的**分层校验与应检枚举面**（挂在 subcommands 第 14 组同一块内）。

    覆盖：坏 JSON／`index` 结构不合法／读不动（＋同夹具正常路径阳性对照）／确认悬空／良性未登记／
    无 `folder.json` 只读／「只有 `folder.json`、没有 `.xwl`」的子目录必须被枚举／`--register` 前置失败。
    返回失败文案列表（空 = 通过）；通过时单独打一行 `[ok]`（⛔ 不新增自检块名）。
    """
    fail: list[str] = []
    root = os.path.join(tmp, "f12_folders")
    _XWL = '{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}'
    _FJ = '{"hidden":false,"index":%s,"title":"t","iconCls":""}'

    def _mkxwl(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(_XWL)

    def _mkfj(d, index):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "folder.json"), "w", encoding="utf-8", newline="") as f:
            f.write(_FJ % json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    def _run_folders(p, register=None):
        return _run(xwl.cmd_folders, path=p, register=register, dry_run=False)

    # ① JSON 坏 ⇒ rc=1（结构损坏，不是"读不动"、也不是"未登记"）
    d = os.path.join(root, "bad_json")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "folder.json"), "w", encoding="utf-8", newline="") as f:
        f.write("{ 坏掉的 json")
    _mkxwl(os.path.join(d, "a.xwl"))
    _rc, _out = _run_folders(d)
    if _rc != 1:
        fail.append("F12：folder.json 是坏 JSON 应 rc=1，实得 %s\n%s" % (_rc, _out))
    if "folder.json 损坏" not in _out:
        fail.append("F12：坏 JSON 未进「folder.json 损坏」明细：%s" % _out)

    # ② index 结构不合法（非数组／元素非字符串／顶层非对象）⇒ rc=1
    for _tag, _body in (
        ("index_not_list", '{"hidden":false,"index":{},"title":"t"}'),
        ("index_elem_not_str", '{"hidden":false,"index":[1],"title":"t"}'),
        ("top_not_obj", "[]"),
    ):
        d = os.path.join(root, _tag)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "folder.json"), "w", encoding="utf-8", newline="") as f:
            f.write(_body)
        _mkxwl(os.path.join(d, "a.xwl"))
        _rc, _out = _run_folders(d)
        if _rc != 1:
            fail.append("F12：结构不合法（%s）应 rc=1，实得 %s\n%s" % (_tag, _rc, _out))
        if "folder.json 损坏" not in _out:
            fail.append("F12：结构不合法（%s）未报「folder.json 损坏」：%s" % (_tag, _out))

    # ③ 读不动 ⇒ rc=2（**无法判断**，⛔ 不与「损坏」混同）；同一夹具换成正常索引 ⇒ rc=0（阳性对照）
    d = os.path.join(root, "unreadable")
    os.makedirs(os.path.join(d, "folder.json"))   # 用同名目录制造读失败（Windows 可构造）
    _mkxwl(os.path.join(d, "a.xwl"))
    _rc, _out = _run_folders(d)
    if _rc != 2:
        fail.append("F12：索引读不动应 rc=2（无法判断），实得 %s\n%s" % (_rc, _out))
    if "读不动（无法判断）" not in _out:
        fail.append("F12：读不动未单独标注（不得与「损坏」混同）：%s" % _out)
    if "读不动 0" in _out:
        fail.append("F12：读不动数量未计入结论行：%s" % _out)
    shutil.rmtree(os.path.join(d, "folder.json"))
    _mkfj(d, [])
    _rc, _out = _run_folders(d)
    if _rc != 0 or "未登记" not in _out:
        fail.append("F12 阳性对照：同一夹具换成正常索引应 rc=0＋列出未登记，实得 %s\n%s"
                    % (_rc, _out))

    # ④ 确认悬空（已登记、盘上无）⇒ rc=1，且与「读不动」分列
    d = os.path.join(root, "dangling")
    _mkfj(d, ["x.xwl", "gone.xwl"])
    _mkxwl(os.path.join(d, "x.xwl"))
    _rc, _out = _run_folders(d)
    if _rc != 1:
        fail.append("F12：确认悬空应 rc=1，实得 %s\n%s" % (_rc, _out))
    if "index 悬空（已登记、盘上无）" not in _out:
        fail.append("F12：确认悬空未单独标注：%s" % _out)
    if "index 悬空项 1 个" not in _out or "读不动 0 个" not in _out:
        fail.append("F12：结论行未把「确认悬空」与「读不动」分列：%s" % _out)

    # ⑤ 良性未登记（盘上有 .xwl、索引没登记）⇒ rc=0，只进明细、不宣称"一致"
    d = os.path.join(root, "benign")
    _mkfj(d, [])
    _mkxwl(os.path.join(d, "y.xwl"))
    _rc, _out = _run_folders(d)
    if _rc != 0:
        fail.append("F12：良性未登记应 rc=0，实得 %s\n%s" % (_rc, _out))
    if "未登记" not in _out or "index 与实际文件一致" in _out:
        fail.append("F12：良性未登记应只进明细、且不得宣称「一致」：%s" % _out)

    # ⑥ 无 folder.json（只读）⇒ rc=0 ＋ 明确的"未执行"note，⛔ 不宣称一致
    d = os.path.join(root, "nofj")
    _mkxwl(os.path.join(d, "c.xwl"))
    _rc, _out = _run_folders(os.path.join(d, "c.xwl"))
    if _rc != 0:
        fail.append("F12：无 folder.json 的只读检查应 rc=0，实得 %s\n%s" % (_rc, _out))
    if "[note] 未发现 folder.json，本次未执行索引检查" not in _out:
        fail.append("F12：无 folder.json 时缺「本次未执行索引检查」note：%s" % _out)
    if "index 与实际文件一致" in _out:
        fail.append("F12：无 folder.json 时不得宣称「index 与实际文件一致」：%s" % _out)

    # ⑦ 应检枚举面：**只有 folder.json、没有 .xwl** 的子目录也必须被枚举（否则悬空永远看不见）
    p = os.path.join(root, "empty_sub")
    _mkfj(p, ["x.xwl", "leaf"])
    _mkxwl(os.path.join(p, "x.xwl"))
    _mkfj(os.path.join(p, "leaf"), ["missing1.xwl", "missing2.xwl"])
    _rc, _out = _run_folders(p)
    if _rc != 1:
        fail.append("F12：空子目录＋悬空应 rc=1（rc=0 即假绿），实得 %s\n%s" % (_rc, _out))
    if "目录 2 个" not in _out or "leaf/" not in _out:
        fail.append("F12：无 .xwl 的子目录未被枚举（目录数/路径不对）：%s" % _out)
    if "index 悬空项 2 个" not in _out:
        fail.append("F12：子目录里的 2 个悬空项未计入结论：%s" % _out)
    if "index 与实际文件一致" in _out:
        fail.append("F12：存在悬空时仍宣称「index 与实际文件一致」（假绿）：%s" % _out)

    # ⑧ `--register` 写入前置：坏／结构不足／读不动 ⇒ rc=2 且**一个字节不动**；正常／幂等 ⇒ rc=0
    d = os.path.join(root, "reg_bad")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "folder.json"), "w", encoding="utf-8", newline="") as f:
        f.write("{ 坏")
    _mkxwl(os.path.join(d, "a.xwl"))
    _before = open(os.path.join(d, "folder.json"), "rb").read()
    _rc, _out = _run_folders(os.path.join(d, "a.xwl"), register="a.xwl")
    if _rc != 2 or open(os.path.join(d, "folder.json"), "rb").read() != _before:
        fail.append("F12 --register：坏 JSON 应 rc=2 且不动文件，实得 %s\n%s" % (_rc, _out))
    d = os.path.join(root, "reg_struct")
    _mkfj(d, [])
    _mkxwl(os.path.join(d, "a.xwl"))
    os.remove(os.path.join(d, "folder.json"))
    with open(os.path.join(d, "folder.json"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"index":{},"title":"t"}')
    _before = open(os.path.join(d, "folder.json"), "rb").read()
    _rc, _out = _run_folders(os.path.join(d, "a.xwl"), register="a.xwl")
    if _rc != 2 or open(os.path.join(d, "folder.json"), "rb").read() != _before:
        fail.append("F12 --register：index 结构不足应 rc=2 且不动文件，实得 %s\n%s"
                    % (_rc, _out))
    d = os.path.join(root, "reg_unread")
    os.makedirs(os.path.join(d, "folder.json"))
    _mkxwl(os.path.join(d, "a.xwl"))
    _rc, _out = _run_folders(os.path.join(d, "a.xwl"), register="a.xwl")
    if _rc != 2:
        fail.append("F12 --register：索引读不动应 rc=2，实得 %s\n%s" % (_rc, _out))
    d = os.path.join(root, "reg_ok")
    _mkfj(d, [])
    _mkxwl(os.path.join(d, "a.xwl"))
    _rc, _out = _run_folders(os.path.join(d, "a.xwl"), register="a.xwl")
    if _rc != 0 or json.load(open(os.path.join(d, "folder.json"), encoding="utf-8"))["index"] != ["a.xwl"]:
        fail.append("F12 --register：正常登记应 rc=0 且写入 index，实得 %s\n%s" % (_rc, _out))
    _snap = open(os.path.join(d, "folder.json"), "rb").read()
    _rc, _out = _run_folders(os.path.join(d, "a.xwl"), register="a.xwl")
    if _rc != 0 or open(os.path.join(d, "folder.json"), "rb").read() != _snap:
        fail.append("F12 --register：重复登记应幂等 rc=0 且不改文件，实得 %s\n%s" % (_rc, _out))

    if fail:
        return fail
    print("[ok]  F12 `folders` 分层校验：读不动/结构损坏/确认悬空/良性未登记/无索引/空子目录枚举/register 前置 全部按码值分开")
    return []

@_cap
def _check_subcommands_tail(tmp, failures) -> None:
    """`_check_subcommands` 的尾段（有界下沉，判据文本逐字未改）。

    只依赖 `tmp` 与 `failures` 两个入参，其余都是模块级名字。
    """
    # ---- 13. new：从零生成（内置骨架 / 设计器键序 / 拒绝覆盖 / 补齐缺键）----
    new_fail: list[str] = []
    a_sql = os.path.join(tmp, "new_sql.xwl")
    code, _out = _run(xwl.cmd_new, out=a_sql, kind="sql", from_json=None, title="出库单查询",
                      roles=None, eol="lf", indent=1, force=False, dry_run=False,
                      node=None, no_js=True)
    if code != 0:
        new_fail.append("new --kind sql 返回 %d" % code)
    else:
        _t, _b, o = xwl.load_xwl(a_sql)
        if list(o.keys()) != list(xwl._PAGE_KEYS):
            new_fail.append("new 生成的顶层键序不是设计器键序: %s" % list(o.keys()))
        c2, cout = _run_check([a_sql], None)
        if c2 != 0:
            new_fail.append("new 的产出没通过 check:\n%s" % cout)
        cb = io.StringIO()
        with contextlib.redirect_stdout(cb):
            rc2 = xwl.cmd_sqlrefs(type("NS", (), {"file": a_sql})())
        if rc2 != 0:
            new_fail.append("new --kind sql 的 {#sql#} 与 serverScript 不自洽:\n%s" % cb.getvalue())

    # 默认必须拒绝覆盖已存在文件，且不得改动原文件
    before = open(a_sql, "rb").read()
    code, _out = _run(xwl.cmd_new, out=a_sql, kind="page", from_json=None, title="X",
                      roles=None, eol="lf", indent=1, force=False, dry_run=False,
                      node=None, no_js=True)
    if code != 2 or open(a_sql, "rb").read() != before:
        new_fail.append("new 未拒绝覆盖已存在文件（exit=%d）" % code)

    # --from-json：补齐缺失的页面钥匙，但不许覆盖用户给的值
    inc_p = os.path.join(tmp, "inc.json")
    with open(inc_p, "w", encoding="utf-8") as f:
        json.dump({"hidden": False, "children": [], "roles": {"demo": 1}, "title": "残缺页"},
                  f, ensure_ascii=False)
    fixd = os.path.join(tmp, "fixed.xwl")
    code, _out = _run(xwl.cmd_new, out=fixd, kind="page", from_json=inc_p, title="",
                      roles=None, eol="lf", indent=1, force=False, dry_run=False,
                      node=None, no_js=True)
    _t, _b, o2 = xwl.load_xwl(fixd)
    if list(o2.keys()) != list(xwl._PAGE_KEYS):
        new_fail.append("--from-json 未按设计器键序补齐: %s" % list(o2.keys()))
    if o2.get("roles") != {"demo": 1} or o2.get("title") != "残缺页":
        new_fail.append("--from-json 覆盖了用户给的值: roles=%s title=%s"
                        % (o2.get("roles"), o2.get("title")))
    if new_fail:
        failures.extend(new_fail)
    else:
        print("[ok]  new：生成物可 check + sqlrefs、拒绝覆盖、--from-json 按设计器键序补齐")

    # ---- 14. folders：未登记/悬空检出；--register 幂等、保键序、保单行 ----
    fd = os.path.join(tmp, "folder_case")
    os.makedirs(fd, exist_ok=True)
    fj = os.path.join(fd, "folder.json")
    with open(fj, "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"index":[],"title":"样本目录","iconCls":""}')
    for nm in ("a.xwl", "b.xwl"):
        with open(os.path.join(fd, nm), "w", encoding="utf-8", newline="") as f:
            f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    fl_fail: list[str] = []
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"), register=None, dry_run=False)
    if "未登记" not in out:
        fl_fail.append("folders 未报出未登记: %s" % out)
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"),
                     register="a.xwl", dry_run=True)
    if "未写入" not in out or json.load(open(fj, encoding="utf-8")).get("index") != []:
        fl_fail.append("folders --register --dry-run 竟然写了盘")
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"),
                     register="a.xwl", dry_run=False)
    txt = open(fj, "r", encoding="utf-8", newline="").read()
    j = json.loads(txt)
    if j.get("index") != ["a.xwl"]:
        fl_fail.append("register 后 index 不对: %s" % j.get("index"))
    if list(j.keys()) != ["hidden", "index", "title", "iconCls"]:
        fl_fail.append("register 改了 folder.json 的键序: %s" % list(j.keys()))
    if "\n" in txt or "\r" in txt:
        fl_fail.append("register 把单行 folder.json 写成了多行")
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"),
                     register="a.xwl", dry_run=False)
    if open(fj, "r", encoding="utf-8", newline="").read() != txt:
        fl_fail.append("重复 register 改动了 folder.json（应幂等）")
    jj = json.loads(txt)
    jj["index"].append("gone.xwl")
    with open(fj, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(jj, ensure_ascii=False, separators=(",", ":")))
    code, out = _run(xwl.cmd_folders, path=fd, register=None, dry_run=False)
    if "悬空" not in out:
        fl_fail.append("folders 未检出 index 悬空项: %s" % out)
    # `#57`：建议行须按「目录有没有 folder.json」分岔 —— 缺 folder.json 时**不得**直接建议
    #   `--register`（该建议必 rc=2）⇒ 改提示"先在设计器里建这个目录/补 folder.json"；有则照旧。
    fdn = os.path.join(tmp, "folder_nofj")
    os.makedirs(fdn, exist_ok=True)
    with open(os.path.join(fdn, "c.xwl"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    code, out = _run(xwl.cmd_folders, path=os.path.join(fdn, "c.xwl"), register=None, dry_run=False)
    if "还没有 folder.json" not in out:
        fl_fail.append("`#57`：缺 folder.json 时未给「先建 folder.json」提示: %s" % out)
    if "登记：xwl.py folders" in out:
        fl_fail.append("`#57`：缺 folder.json 时仍直接建议 `--register`（必 rc=2）: %s" % out)
    fdy = os.path.join(tmp, "folder_yesfj")
    os.makedirs(fdy, exist_ok=True)
    with open(os.path.join(fdy, "folder.json"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"index":[],"title":"t","iconCls":""}')
    with open(os.path.join(fdy, "d.xwl"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    code, out = _run(xwl.cmd_folders, path=os.path.join(fdy, "d.xwl"), register=None, dry_run=False)
    if "登记：xwl.py folders" not in out or "--register" not in out:
        fl_fail.append("`#57`：有 folder.json 时未直接建议 `--register`（误伤正路）: %s" % out)
    # F12：分层校验 + 应检枚举面（坏 JSON／结构／读不动／悬空／良性／无索引／空子目录／register 前置）
    fl_fail.extend(_folders_f12_cases(tmp))
    if fl_fail:
        failures.extend(fl_fail)
    else:
        print("[ok]  folders：未登记/悬空检出、register 幂等且保键序保单行形态；缺 folder.json 时提示先建而非直接 --register")

    # ---- 15. paths 的「原路径」必须带 configs 层，照抄就该改对地方 ----
    # 经 `_run_cli`（子进程真 CLI）取值：同 12b 的起因 —— 直调时被测行为一旦抛异常，异常冲出 `_run`
    #   ⇒ 定向断言没跑到；经 CLI 则异常被进程隔离、红行必落在下面两条"原路径带 configs 层"断言上。
    p_fail: list[str] = []
    _c15, out, _e15 = _run_cli(["paths", a_sql])
    if '["children", 0, "configs", "serverScript"]' not in out:
        p_fail.append("paths 的原路径没带 configs 层（照抄会把字段写到节点根上）:\n%s" % out)
    if '["children", 0, "children", 0, "configs", "sql"]' not in out:
        p_fail.append("paths 的 sql 原路径没带 configs 层:\n%s" % out)
    ops_p = os.path.join(tmp, "ops_from_paths.json")
    with open(ops_p, "w", encoding="utf-8") as f:
        json.dump([{"op": "set", "path": ["children", 0, "configs", "serverScript"],
                    "value": "var sql='PATCHED';"}], f, ensure_ascii=False)
    pt_target = os.path.join(tmp, "paths_patch.xwl")
    with open(pt_target, "wb") as f:
        f.write(open(a_sql, "rb").read())
    code, _out = _run(xwl.cmd_patch, file=pt_target, ops=ops_p, indent=1, eol="auto",
                      dry_run=False, backup=False, node=None, no_js=True)
    _t, _b, o3 = xwl.load_xwl(pt_target)
    mod = o3["children"][0]
    if mod.get("configs", {}).get("serverScript") != "var sql='PATCHED';":
        p_fail.append("照抄 paths 的原路径没改到 configs.serverScript")
    if "serverScript" in mod:
        p_fail.append("照抄 paths 的原路径把字段写到了节点根上")
    if p_fail:
        failures.extend(p_fail)
    else:
        print("[ok]  paths 原路径带 configs 层，照抄即可改到正确位置")

    # ---- 15b. paths 对「恰好两个同名 itemId」必须给 ⚠ 点名告警（不许直接推荐有歧义的 @ 路径）----
    # 起因（仪表审计实测）：`paths` 的重名阈值被改成"重复 > 2 才告警"时，**恰好 2 个同名**的节点会被
    #   直接推荐一个会产生歧义的 `@` 路径（用户照抄，到 `patch` 执行才报"不猜顺序"）—— 而旧自检的
    #   夹具 `itemId` 全唯一、只做"输出含原路径"级冒烟 ⇒ 该回归**全绿**。故补"恰好两个同名"夹具。
    dup_fail: list[str] = []
    _dup_obj = {"title": "重名页", "children": [
        {"configs": {"itemId": "d1", "url": "a.html"}, "type": "store",
         "expanded": False, "children": []},
        {"configs": {"itemId": "d1", "url": "b.html"}, "type": "store",
         "expanded": False, "children": []},
    ]}
    _dup_page = os.path.join(tmp, "paths_dup.xwl")
    with open(_dup_page, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(_dup_obj, 1, CRLF))
    _rc_pd, _out_pd, _err_pd = _run_cli(["paths", _dup_page])
    if _rc_pd != 0:
        dup_fail.append("paths 对重名页 rc=%s（应 0）：\n%s" % (_rc_pd, _cli_text(_out_pd, _err_pd)))
    if "⚠ @写法" not in _out_pd or "出现 2 次" not in _out_pd:
        dup_fail.append("paths 对「恰好 2 个同名 itemId」未给 ⚠ 点名告警：\n%s" % _out_pd)
    if "推荐" in _out_pd:
        dup_fail.append("paths 对重名 itemId 直接推荐了有歧义的 `@` 路径（应只给 ⚠ 点名提示）：\n%s"
                        % _out_pd)
    if dup_fail:
        failures.extend(dup_fail)
    else:
        print("[ok]  paths 对「恰好 2 个同名 itemId」给 ⚠ 点名告警、不直接推荐有歧义的 @ 路径")

    # ---- 16. schema --skeleton 只输出该控件允许的键 ----
    reg = os.path.join(tmp, "mini_controls.json")
    with open(reg, "w", encoding="utf-8") as f:
        json.dump({"children": [
            {"id": "dataprovider", "general": {"design": False},
             "configs": {"itemId": {"type": "string"}, "sql": {"type": "sql"}}, "events": {}},
            {"id": "button", "general": {"design": True, "xtype": "button"},
             "configs": {"itemId": {"type": "string"}, "text": {"type": "string"}},
             "events": {"click": {"type": ""}}},
        ]}, f, ensure_ascii=False)
    s_fail: list[str] = []
    code, out = _run(xwl.cmd_schema, type="dataprovider", controls=reg, list=False,
                     tree=False, skeleton=True)
    if '"events"' in out:
        s_fail.append("dataprovider（0 个 events）的骨架不该带 events 键")
    if '"text"' in out:
        s_fail.append("dataprovider 的 configs 里不该有 text（不是它的合法键）")
    code, out = _run(xwl.cmd_schema, type="button", controls=reg, list=False,
                     tree=False, skeleton=True)
    if '"text"' not in out or '"click"' not in out:
        s_fail.append("button 的骨架应含 text + click:\n%s" % out)
    if s_fail:
        failures.extend(s_fail)
    else:
        print("[ok]  schema --skeleton：只含该控件允许的键，events 键按该控件实际事件决定")


    # ---- 序 7 归位：`17j-10`／`17j-11`／`17v` 从 `_check_docs` 移来（**块头与块名不变**）----
    #   起因（为什么该挪这儿）：这三块的实质是「**真跑 CLI 再断言输出**」，与 `_check_docs` 的
    #     文档一致性职责不同类；混在一个函数里会让两边职责互相渗透、行数也一路涨。
    #   ⛔ 块名一个都没改（块基线照旧咬得住它们）；⛔ 判据一条都没动（文本逐字搬过来）。
    #   `doc_fail` 在这里是**局部同名清单**（搬过来的文本一字未改）⇒ 末端并进 `failures`。
    _root_sub = SKILL_ROOT
    doc_fail: list[str] = []
    # `17j-10` 用的「误导版措辞」字面量：原来定义在 `_check_docs` 里，搬过来要**自带一份**。
    # ⛔ 保持这种**拼接**写法（本文件也在扫描面内，整词直写会自命中）。
    _bad_lit = "app." "<itemId>"

    # 17j-10 `schema --skeleton` 的 itemId 占位值必须写对口径（**行为级**：真跑一次再断言输出）。
    #     起因（删了会怎样）：占位值曾把「工具 `@itemId` 寻址」与「运行时注册键取名」混为一谈；
    #     修正后**无自动化守卫**（QA 注入：把占位改回 `<必填>`，selftest 仍 rc=0 / [ok]=111 / [FAIL]=0）。
    #     删掉本断言 ⇒ 占位值再被改回误导版会静默回归。
    #     判据：真跑 `schema button --controls <fixture> --skeleton`，输出须含 `@itemId` 与「工具寻址」、
    #     且不含误导版字面量。fixture 由本测试**自建**（同 §16 的 mini 注册表）—— CI 里没有工程样本，
    #     若改去"工程内发现 controls.json"，守卫在 CI 恒为 `[note]`、等于没守。
    _reg10 = os.path.join(tmp, "guard_controls.json")
    try:
        with open(_reg10, "w", encoding="utf-8") as _f10:
            json.dump(_GUARD10_FIXTURE, _f10, ensure_ascii=False)
        _c10, _out10 = _run(xwl.cmd_schema, type="button", controls=_reg10,
                            list=False, tree=False, skeleton=True)
        _bad10 = []
        if "@itemId" not in _out10 or "工具寻址" not in _out10:
            _bad10.append("17j-10 `schema --skeleton` 的 itemId 占位值丢了「工具寻址（@itemId）」口径："
                          "输出里找不到。含 itemId 的行：%s"
                          % " | ".join(_l.strip() for _l in _out10.splitlines() if "itemId" in _l)[:160])
        if _bad_lit in _out10:
            _bad10.append("17j-10 `schema --skeleton` 的 itemId 占位值出现误导版措辞「%s」" % _bad_lit)
        if _bad10:
            doc_fail.extend(_bad10)
        else:
            print("[ok]  17j-10 `schema --skeleton` 的 itemId 占位值口径正确（行为级：真跑 + 断言输出）")
    except (OSError, ValueError) as _exc:
        doc_fail.append("17j-10 `schema --skeleton` 占位值守卫跑不起来：%s" % _exc)

    # 17j-11 `schema --skeleton` 对 `window` 必须预填两个**非缺省**推荐键（**行为级**：真跑一次再断言输出）。
    #     起因（删了会怎样）：窗口这两个键的缺省分别是「真」与 'hide'，写错代价最大 ——
    #     `closeAction=destroy` 时若仍复用实例，第二次打开就是空白窗。预填是"防呆"，
    #     把它改回缺省（即不再预填）必须当场红，否则这条防呆会静默失效。
    #     判据：真跑 `schema window --controls <fixture> --skeleton`，输出须同时含
    #     `createInstance`/`false` 与 `closeAction`/`destroy` 两项。fixture 由本测试**自建**
    #     （CI 无工程样本，靠"发现工程内 controls.json"会让守卫在 CI 恒为 `[note]`、等于没守）。
    _reg11 = os.path.join(tmp, "guard_window_controls.json")
    try:
        with open(_reg11, "w", encoding="utf-8") as _f11:
            json.dump(_GUARD11_FIXTURE, _f11, ensure_ascii=False)
        _c11, _out11 = _run(xwl.cmd_schema, type="window", controls=_reg11,
                            list=False, tree=False, skeleton=True)
        _bad11 = []
        if '"createInstance"' not in _out11 or '"false"' not in _out11:
            _bad11.append("17j-11 `schema window --skeleton` 丢了预填的 createInstance=\"false\""
                          "（窗口「每次重建」档据此写，缺了会退化成复用实例的空白窗写法）")
        if '"closeAction"' not in _out11 or '"destroy"' not in _out11:
            _bad11.append("17j-11 `schema window --skeleton` 丢了预填的 closeAction=\"destroy\"")
        if _bad11:
            doc_fail.extend(_bad11)
        else:
            print("[ok]  17j-11 `schema window --skeleton` 预填 createInstance/closeAction"
                  "（行为级：真跑 + 断言输出）")
    except (OSError, ValueError) as _exc:
        doc_fail.append("17j-11 窗口骨架预填守卫跑不起来：%s" % _exc)

    # 17v 真跑 examples/ 下全部 ops-*.json 样板：空页 `new` → `patch --ops` → `check`，三步都要 rc=0。
    #   起因：样板是"从 `new --kind page` 空页出发、同文件自洽"的**对外承诺**，无守卫保证它**当下**跑得通 ——
    #     改了 `xwl.py` 的 ops 语义、或样板的 `path` 指错，样板跑不通了没人知道。经 `_run_cli`（子进程跑真 CLI）：
    #     拿真实退出码、异常被进程隔离；`new`/`patch` 带 `--no-js` 免依赖 node，`check` **不带**（连事件 JS 一起校验）。
    _b17v_dir = os.path.join(_root_sub, "examples")
    _b17v_names = sorted(_n for _n in (os.listdir(_b17v_dir) if os.path.isdir(_b17v_dir) else [])
                         if _n.startswith("ops-") and _n.endswith(".json"))
    _b17v_bad: list = []
    for _b17v_nm in _b17v_names:
        _b17v_x = os.path.join(tmp, "ops-sample-%s.xwl" % _b17v_nm[4:-5])
        for _b17v_cmd in (["new", _b17v_x, "--kind", "page", "--no-js"],
                          ["patch", _b17v_x, "--ops", os.path.join(_b17v_dir, _b17v_nm), "--no-js"],
                          ["check", _b17v_x]):
            _b17v_rc, _b17v_out, _b17v_err = _run_cli(_b17v_cmd)
            if _b17v_rc != 0:
                _b17v_tail = (_b17v_out or _b17v_err).strip().splitlines()
                _b17v_bad.append("真跑样板 %s 失败（%s rc=%s）：%s"
                                 % (_b17v_nm, _b17v_cmd[0], _b17v_rc,
                                    _b17v_tail[-1] if _b17v_tail else "（无输出）"))
                break
    if _b17v_bad:
        doc_fail.extend(_b17v_bad)
    else:
        print("[ok]  真跑 examples/ops-*.json 样板（%d 份）全部通过" % len(_b17v_names))

    if doc_fail:
        failures.extend(doc_fail)

_GUARD10_FIXTURE = {"children": [
    {"id": "button", "general": {"design": True, "xtype": "button"},
     "configs": {"itemId": {"type": "string"}, "text": {"type": "string"}},
     "events": {"click": {"type": ""}}},
]}

_GUARD11_FIXTURE = {"children": [
    {"id": "window", "general": {"design": True, "xtype": "window"},
     "configs": {"itemId": {"type": "string"}, "title": {"type": "string"}},
     "events": {}},
]}

