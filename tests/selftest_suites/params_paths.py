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

_FIELD_FALLBACK_EXPECT = ("check", "combo", "date", "datetime", "displayfield", "file",
                          "hidden", "htmleditor", "number", "picker", "radio", "text",
                          "textarea", "time")

def _check_params_paths(tmp, node, failures, write) -> None:
    """params 两条通路 + 注释剔除与多容器 out（第 8~10 组）"""

    # ---- 8. params：两条通路的识别（out / params） ----
    FIELD = xwl.field_types(None)
    js_out = "app.grid1.store.load({ out: app.tbar });"
    js_gv = "app.grid1.store.load({ params: Wb.getValue(app.tbar) });"
    js_obj = "app.grid1.store.load({ params: { cId: rec.data.MR_ID, sql: 'a,b:c', nested: {x: 1} } });"
    js_both = "Wb.request({ url: 'm?xwl=demo/x', out: app.editWin, params: { a: 1 }, success: fn });"
    tr_out = xwl.find_transfers(js_out, FIELD)
    tr_gv = xwl.find_transfers(js_gv, FIELD)
    tr_obj = xwl.find_transfers(js_obj, FIELD)
    tr_both = xwl.find_transfers(js_both, FIELD)
    for name, cond in {
        "识别 out 通路（容器 app.tbar）":
            [t[0] for t in tr_out] == ["out"] and tr_out[0][1] == ["tbar"],
        "识别 params: Wb.getValue（等价 out）":
            [t[0] for t in tr_gv] == ["params=Wb.getValue"] and tr_gv[0][1] == ["tbar"],
        "识别 params: 对象键（跳过字符串值与嵌套层）":
            bool(tr_obj) and tr_obj[0][0] == "params=对象" and tr_obj[0][2] == ["cId", "sql", "nested"],
        "out 与 params 同时出现时各自独立识别":
            {t[0] for t in tr_both} == {"out", "params=对象"},
        "read_expr 括号配平":
            xwl.read_expr(js_both, js_both.index("out:") + 4).strip() == "app.editWin",
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(
                f"{name} 失败（out={tr_out} gv={tr_gv} obj={tr_obj} both={tr_both}）")

    # ---- 9–10. 注释剔除 / 多容器 out / 剔注释不粘连 ----
    for name, cond in {
        "行注释里的 out 不被误判":
            [t[1] for t in xwl.find_transfers(
                "// g.load({ out: app.tbar });\ng.load({ out: app.tbar2 });", FIELD)] == [["tbar2"]],
        "块注释里的 params 不被误判":
            [t[2] for t in xwl.find_transfers(
                "/* params: { a: 1 } */\ng.load({ params: { b: 2 } });", FIELD)] == [["b"]],
        "字符串里的 // 不被当注释":
            [t[2] for t in xwl.find_transfers(
                "g.load({ params: { u: 'http://x/y' } });", FIELD)] == [["u"]],
        "多容器 out: [app.a, app.b]":
            [t[1] for t in xwl.find_transfers("g.load({ out: [app.a, app.b] });", FIELD)] == [["a", "b"]],
        "剔注释不粘连代码":
            xwl.strip_js_comments("var a = 1; // c\nvar b = 2;") == "var a = 1; \nvar b = 2;",
        # ---- 以下 4 条是「**判据依据**」断言：守的是"判据本身对不对"，不是"行为有没有变" ----
        # 起因：本仓每版都有自检，但自检长期只覆盖"行为一致性" ⇒ 一个**从第一版就存在**的判据错误
        # （`field_types` 只取注册表）能活到 1.3.x 才被撞出来。这几条断言的就是那类错误。
        # ⚠️ 期望用**手写**清单 `_FIELD_FALLBACK_EXPECT`（**不再**由 `xwl._FIELD_FALLBACK` 自己拼出）：
        #   否则兜底清单被清空 / 砍短时谓词恒真、退化无感（定点实测）。
        "field_types = 注册表 ∪ 内置兜底（兜底为**手写**期望，不是二选一、也不是自比）":
            (set(_FIELD_FALLBACK_EXPECT) | {"onlyinreg"}) <= set(xwl.field_types(
                write("k21-controls.json", json.dumps(
                    {"n": {"id": "onlyinreg", "general": {"type": "Ext.form.field.text"}}},
                    ensure_ascii=False)))),
        "strip_sql_type_prefix：类型前缀剥 / DATETIME 不剥 / 原名命中不剥 / 纯数字不剥":
            (xwl.strip_sql_type_prefix("timestamp.endDate", set()) == "endDate"
             and xwl.strip_sql_type_prefix("TIMESTAMP.a", set()) == "a"
             and xwl.strip_sql_type_prefix("DATETIME.start", set()) == "DATETIME.start"
             and xwl.strip_sql_type_prefix("datetime.start", {"datetime.start"}) == "datetime.start"
             and xwl.strip_sql_type_prefix("123.a", set()) == "123.a"),
        "equivalent 能区分 1 / 1.0 / true 与**键序**（Python 的 `==` 不能）":
            (not xwl.equivalent({"a": 1}, {"a": 1.0})
             and not xwl.equivalent({"a": 1}, {"a": True})
             and not xwl.equivalent({"a": 1, "b": 2}, {"b": 2, "a": 1})
             and not xwl.equivalent({"x": -0.0}, {"x": 0})
             and xwl.equivalent({"a": 1}, {"a": 1})),
        "bare_nul_in_strings：只数字符串里的裸 NUL，转义写法不算":
            (xwl.bare_nul_in_strings('{"x":"a' + chr(0) + 'b"}') == 1
             and xwl.bare_nul_in_strings('{"x":"a\\u0000b"}') == 0),
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败")

    # ---- 判据依据续：`sys.` 前缀的来源与两个入口的寻址同源 ----
    # 起因：`sys.` 曾硬编码（工程自定义命名空间不认）；`paths` 曾按"能嵌套的整棵树"遍历，
    #   会给出 `patch` 的 `@itemId` 解不开的路径 —— 两个入口必须用**同一套**寻址语义。
    _xwlsrc = open(os.path.join(SKILL_ROOT, "scripts", "xwl.py"), encoding="utf-8").read()
    _cp_body = _xwlsrc.split("def cmd_paths(")[1].split("\ndef ")[0]
    _fa_body = _xwlsrc.split("def _find_all_by_itemid(")[1].split("\ndef ")[0]
    _k3wb = os.path.join(tmp, "k3proj", "src", "main", "webapp", "wb")
    os.makedirs(os.path.join(_k3wb, "system"), exist_ok=True)
    os.makedirs(os.path.join(_k3wb, "modules"), exist_ok=True)
    _k3pg = os.path.join(_k3wb, "modules", "p.xwl")
    with open(_k3pg, "w", encoding="utf-8") as _f:
        _f.write("{}")
    _k3base, _k3base_fail = xwl.builtin_prefixes(_k3pg)
    _varp = os.path.join(_k3wb, "system", "var.json")
    with open(_varp, "w", encoding="utf-8") as _f:
        json.dump({"sys": {}, "myapp": {}}, _f)
    _k3var, _k3var_fail = xwl.builtin_prefixes(_k3pg)
    with open(_varp, "w", encoding="utf-8") as _f:
        _f.write("{ not json")
    _k3bad, _k3bad_fail = xwl.builtin_prefixes(_k3pg)
    for name, cond in {
        "builtin_prefixes 基线：无 var.json 时 = 内置（含 sys. / Str.）且无读失败":
            "sys." in _k3base and "Str." in _k3base and _k3base_fail is None,
        "builtin_prefixes：认 var.json 的顶层键（工程自定义命名空间）":
            "myapp." in _k3var and "sys." in _k3var and _k3var_fail is None,
        "builtin_prefixes：var.json 坏掉时退回内置、**且记录读失败**（不再静默吞）":
            _k3bad == _k3base and _k3bad_fail is not None and _k3bad_fail[0] == _varp,
        "paths 与 patch 的 @itemId 寻址同源（都按控件树 _iter_controls）":
            "_iter_controls(" in _cp_body and "_iter_controls(" in _fa_body,
        # ⚠️ 内联对象**必须带 `type`**：`_iter_controls` 只 yield 有字符串 `type` 的节点，
        #    不带 `type` 的 fixture 抓不到"没跳过 configs"这个注入（实测过 —— 那种是**假绿**）。
        "configs 里的内联同名对象不算控件（@itemId 不会误指）":
            len(xwl._find_all_by_itemid(
                {"children": [{"configs": {"itemId": "dup",
                                           "vals": [{"type": "text",
                                                     "configs": {"itemId": "dup"}}]},
                               "type": "panel", "children": []}]}, "dup")) == 1,
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败")

    # F05：读依赖失败不得被吞（可选资源面：`var.json` 三分＋sqlrefs 同源；依赖面在 new_guards 块）
    failures.extend(_f05_var_cases(tmp))
    # params --upstream 五类默认/strict 真实 rc 矩阵
    failures.extend(_f05_upstream_matrix_cases(tmp))
    # AV-03：注册表一次加载的 `params` 面（check/itemids 面在 new_guards 块）
    failures.extend(_av03_params_cases(tmp))

def _dump(obj, path):
    """按设计器格式（缩进 1、CRLF）写一份 `.xwl` 夹具；父目录自动建。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(obj, 1, CRLF))

def _store(iid, url):
    """造一个最小 `store` 节点（`configs.itemId` ＋ `url`）。"""
    return {"configs": {"itemId": iid, "url": url}, "type": "store",
            "expanded": False, "children": []}

_F05_CARRIER_OK = ('{"children":[{"type":"dataprovider","configs":'
                   '{"itemId":"dp","sql":"select * from t where a={?p?}"}}]}')

def _f05_proj(tmp, case):
    r = os.path.join(tmp, "f05proj", case)
    m = os.path.join(r, "modules")
    os.makedirs(m, exist_ok=True)
    return r, m

def _f05_write_var(r, body=None):
    vp = os.path.join(r, "wb", "system", "var.json")
    os.makedirs(os.path.dirname(vp), exist_ok=True)
    if body is not None:
        with open(vp, "w", encoding="utf-8", newline="") as f:
            f.write(body)
    return vp

def _f05_write_carrier(m, body=_F05_CARRIER_OK):
    p = os.path.join(m, "demo", "carrier.xwl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    return p

def _f05_make_page(m, *, provide=True, extra=()):
    s1 = _store("s1", "m?xwl=demo/carrier")
    if provide:
        s1["configs"]["params"] = "{p:1}"
    _dump({"title": "p", "children": [s1] + list(extra)},
          os.path.join(m, "demo", "page.xwl"))
    return os.path.join(m, "demo", "page.xwl")

def _f05_run_params(page, m, strict=False, upstream=False):
    return _run(xwl.cmd_params, file=page, module_root=m, controls=None,
                list_fields=False, strict=strict, upstream=upstream)

def _f05_var_cases(tmp):
    """F05 可选资源面：`var.json` 三分 ＋ `sqlrefs` 同源（放在 `params_paths` 块）。

    三分：未发现（可选资源缺席 ⇒ **不算失败**）／合法（含空字典）／存在但读不出或结构不合（**失败**）。
    返回失败文案列表（空 = 通过）；通过时单独打一行 `[ok]`。
    """
    fail: list = []
    r, m = _f05_proj(tmp, "var_kinds")
    page = _f05_make_page(m)
    _f05_write_carrier(m)

    # ① 未发现 ⇒ 用内置兜底、不算失败（rc=0，且不出现「读依赖失败」）
    rc, out = _f05_run_params(page, m)
    if rc != 0 or "读依赖失败" in out:
        fail.append("F05：未发现 var.json 不应算失败（应 rc=0），实得 %s\n%s" % (rc, out))
    # ② 合法空字典 ⇒ 正常
    _f05_write_var(r, "{}")
    rc, out = _f05_run_params(page, m)
    if rc != 0 or "读依赖失败" in out:
        fail.append("F05：var.json 合法空字典不应算失败（应 rc=0），实得 %s\n%s" % (rc, out))
    # ③ 坏 JSON ⇒ 默认/strict 均 rc=2 且点名
    _f05_write_var(r, "{ not json")
    for _strict in (False, True):
        rc, out = _f05_run_params(page, m, strict=_strict)
        if rc != 2:
            fail.append("F05：var.json 坏 JSON（strict=%s）应 rc=2，实得 %s\n%s"
                        % (_strict, rc, out))
        if "读依赖失败" not in out:
            fail.append("F05：var.json 坏 JSON（strict=%s）未点名读失败：\n%s" % (_strict, out))
    # ④ 结构不合（顶层非对象）⇒ rc=2 且点名
    _f05_write_var(r, "[]")
    rc, out = _f05_run_params(page, m)
    if rc != 2 or "读依赖失败" not in out:
        fail.append("F05：var.json 结构不合（顶层非对象）应 rc=2 且点名，实得 %s\n%s" % (rc, out))

    # ⑤ strict「var 读失败 ＋ 已确认缺参」⇒ rc=1 并同时列读取失败；默认档仅有缺参时读失败才升 2
    r, m = _f05_proj(tmp, "var_bad_miss")
    page = _f05_make_page(m, provide=False)
    _f05_write_carrier(m)
    _f05_write_var(r, "{ not json")
    rc1, out1 = _f05_run_params(page, m, strict=True)
    if rc1 != 1:
        fail.append("F05：strict「var 读失败＋已确认缺参」应 rc=1，实得 %s\n%s" % (rc1, out1))
    if "读依赖失败" not in out1:
        fail.append("F05：strict 缺参时未同时列出 var 读取失败：\n%s" % out1)
    rc0, out0 = _f05_run_params(page, m)
    if rc0 != 2:
        fail.append("F05：默认档「var 读失败＋仅缺参」应 rc=2（读失败本身升级），实得 %s\n%s"
                    % (rc0, out0))

    # ⑥ 无 needed 的**早返**路径：坏 var ⇒ default/strict 均 rc=2 并点名；无 var ⇒ rc=0（未发现不算失败）
    #    （复核退回项：早返曾只合并 carrier/反查失败、漏 `_pref_fail`）
    r, m = _f05_proj(tmp, "noneed_var")
    _dump({"title": "p", "children": [{"configs": {"itemId": "btn"}, "type": "button",
                                       "expanded": False, "children": []}]},
          os.path.join(m, "demo", "empty.xwl"))
    page = os.path.join(m, "demo", "empty.xwl")
    rc, out = _f05_run_params(page, m)
    if rc != 0 or "读依赖失败" in out:
        fail.append("F05 早返：无 needed＋无 var.json 应 rc=0（未发现不算失败），实得 %s\n%s"
                    % (rc, out))
    _f05_write_var(r, "{ not json")
    for _strict in (False, True):
        rc, out = _f05_run_params(page, m, strict=_strict)
        if rc != 2:
            fail.append("F05 早返：无 needed＋var.json 坏（strict=%s）应 rc=2，实得 %s\n%s"
                        % (_strict, rc, out))
        if "读依赖失败" not in out:
            fail.append("F05 早返：无 needed＋var.json 坏（strict=%s）未点名读失败：\n%s"
                        % (_strict, out))

    # ⑦ `sqlrefs` 的 `var.json` 同源：未发现 ⇒ rc=0；坏 ⇒ rc=2 且点名
    r, m = _f05_proj(tmp, "sqlrefs_var")
    carrier = _f05_write_carrier(m)
    rc, out = _run(xwl.cmd_sqlrefs, file=carrier)
    if rc != 0:
        fail.append("F05：sqlrefs 未发现 var.json 应 rc=0，实得 %s\n%s" % (rc, out))
    _note = ("[note] 本检查仅作文件内静态供给集合核对；不证明供给调用必经执行、消费前时序、"
             "分支或跨 module 生命周期有效。")
    if out.splitlines().count(_note) != 1:
        fail.append("F05：sqlrefs 未发现 var.json 时证明边界 note 不是恰一次：\n%s" % out)
    _f05_write_var(r, "{ not json")
    rc, out = _run(xwl.cmd_sqlrefs, file=carrier)
    if rc != 2 or "读依赖失败" not in out:
        fail.append("F05：sqlrefs 的 var.json 坏 JSON 应 rc=2 且点名，实得 %s\n%s" % (rc, out))
    if out.splitlines().count(_note) != 1:
        fail.append("F05：sqlrefs 依赖读失败时证明边界 note 不是恰一次：\n%s" % out)
    _lines = out.splitlines()
    if _note in _lines:
        _pos = _lines.index(_note)
        if _pos + 1 >= len(_lines) or not _lines[_pos + 1].startswith("=== 结果:"):
            fail.append("F05：sqlrefs 依赖读失败时证明边界 note 不在统一结果行之前：\n%s" % out)

    if fail:
        return fail
    print("[ok]  F05 可选资源面：var.json 三分（未发现不算失败/空字典正常/坏或结构不合失败）"
          "＋ sqlrefs 同源；default/strict 与「同时有已确认缺参」组合按码值解释")
    return []

def _f05_upstream_matrix_cases(tmp):
    """`params --upstream` 五类场景的默认/strict rc 矩阵。"""
    fail: list = []
    cases = (
        ("normal", True, False, False, (0, 0)),
        ("confirmed_content_issue", False, False, False, (0, 1)),
        ("read_failure_only", True, True, False, (2, 2)),
        ("read_failure_and_content", False, True, False, (2, 1)),
        ("unknown_only", False, False, True, (0, 2)),
    )
    no_need_carrier = ('{"children":[{"type":"dataprovider","configs":'
                       '{"itemId":"dp","sql":"select 1 from dual"}}]}')
    for name, provide, reads_bad, unknown, expected in cases:
        r, m = _f05_proj(tmp, "upstream_matrix_" + name)
        extra = []
        if unknown:
            extra.append({
                "type": "button", "configs": {"itemId": "dyn"},
                "expanded": False, "children": [],
                "events": {"click": "Wb.request({url:dynUrl, params:{p:1}});"},
            })
        page = _f05_make_page(m, provide=provide, extra=extra)
        _f05_write_carrier(m, no_need_carrier if name == "read_failure_only"
                           else _F05_CARRIER_OK)
        if reads_bad:
            with open(os.path.join(m, "bad_caller.xwl"), "w",
                      encoding="utf-8", newline="") as f:
                f.write("{ broken caller")
        actual = tuple(_f05_run_params(page, m, strict=strict, upstream=True)[0]
                       for strict in (False, True))
        if actual != expected:
            fail.append("upstream 五类矩阵 %s 默认/strict 应 %r，实得 %r"
                        % (name, expected, actual))
    if fail:
        return fail
    print("[ok]  params --upstream 默认/strict rc 矩阵五类齐全")
    return []

_AV03_REG = [
    {"id": "onlyinreg", "general": {"type": "Ext.form.field.text"},
     "configs": {"normalName": "x", "itemId": {"type": "str"}}},
    {"id": "onlynormal", "configs": {"normalName": "y"}},
]

def _av03_write(ctrl, body):
    with open(ctrl, "w", encoding="utf-8", newline="") as f:
        f.write(body)

def _av03_run_params(ctrl, page, **kw):
    kw.setdefault("module_root", None)
    kw.setdefault("list_fields", False)
    kw.setdefault("upstream", False)
    kw.setdefault("strict", False)
    return _run(xwl.cmd_params, file=page, controls=ctrl, **kw)

def _av03_params_cases(tmp):
    """AV-03 的 `params` 面（挂 `params_paths`）：一次上下文只解析 1 次＋坏注册表可见降级＋union 生效。"""
    fail: list = []
    r = os.path.join(tmp, "av03params")
    ctrl = os.path.join(r, "wb", "system", "controls.json")
    page = os.path.join(r, "wb", "modules", "page.xwl")
    os.makedirs(os.path.dirname(ctrl), exist_ok=True)
    os.makedirs(os.path.dirname(page), exist_ok=True)
    _dump({"title": "t", "children": [{"type": "panel", "configs": {"itemId": "p"}}]}, page)

    # ① 正常注册表：rc=0、解析 1 次、来源行带路径
    _av03_write(ctrl, json.dumps(_AV03_REG, ensure_ascii=False))
    n0 = xwl._REG_LOADS
    rc, out = _av03_run_params(ctrl, page)
    if rc != 0 or xwl._REG_LOADS - n0 != 1:
        fail.append("AV-03(params)：正常注册表应 rc=0 且解析 1 次，实得 rc=%s n=%d\n%s"
                    % (rc, xwl._REG_LOADS - n0, out))
    if "控件注册表:" not in out or "读注册表失败" in out:
        fail.append("AV-03(params)：正常注册表下来源行/失败提示不对：\n%s" % out)

    # ② 坏注册表：rc 保持改前基线 0、解析 1 次、**可见「不可用＋据已降级」**
    _av03_write(ctrl, "{ not json")
    n0 = xwl._REG_LOADS
    rc, out = _av03_run_params(ctrl, page)
    if rc != 0 or xwl._REG_LOADS - n0 != 1:
        fail.append("AV-03(params)：坏注册表应保持 rc=0（改前基线）且解析 1 次，实得 rc=%s n=%d\n%s"
                    % (rc, xwl._REG_LOADS - n0, out))
    for k in ("[warn] 读注册表失败：", "已回退内置兜底"):
        if k not in out:
            fail.append("AV-03(params)：坏注册表缺少降级说明 %r：\n%s" % (k, out))

    # ③ `--list-fields` 也走同一事实源：注册表里的类型出现在字段清单、解析 1 次
    _av03_write(ctrl, json.dumps(_AV03_REG, ensure_ascii=False))
    n0 = xwl._REG_LOADS
    rc, out = _av03_run_params(ctrl, page, list_fields=True)
    if rc != 0 or xwl._REG_LOADS - n0 != 1:
        fail.append("AV-03(params)：--list-fields 应 rc=0 且解析 1 次，实得 rc=%s n=%d\n%s"
                    % (rc, xwl._REG_LOADS - n0, out))
    if "onlyinreg" not in out:
        fail.append("AV-03(params)：--list-fields 未并入注册表类型（onlyinreg）：\n%s" % out)

    if fail:
        return fail
    print("[ok]  AV-03(params) 注册表一次加载：正常/坏注册表均解析 1 次、坏注册表 rc 保持 0"
          " 且可见「不可用＋已回退内置兜底」、--list-fields 共用同一事实源")
    return []

