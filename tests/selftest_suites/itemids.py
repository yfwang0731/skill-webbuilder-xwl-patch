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

def _check_itemids(tmp, node, failures, write) -> None:
    """@itemId 寻址、重名分级、引用判定、防御性取值（第 11~11j 组；`11k` 章节顺序已归位至文档守卫侧）"""

    # ---- 11. @itemId 寻址：唯一可定位、重名拒绝 ----
    dup_tree = {"children": [
        {"type": "container", "configs": {"itemId": "same"}, "children": []},
        {"type": "container", "configs": {"itemId": "same"}, "children": []},
    ]}
    try:
        xwl.apply_ops(dup_tree,
                      [{"op": "set", "path": ["@same", "configs", "itemId"], "value": "x"}])
        failures.append("@itemId 重名时应拒绝执行，实际却执行了（会静默改错对象）")
    except KeyError as exc:
        msg = str(exc)
        if "2 个节点" not in msg:
            failures.append("@itemId 重名的报错未说明重名数量: %s" % msg)
        elif not all(k in msg for k in ("#1", "祖先", "建议")):
            failures.append("@itemId 重名的报错未给出「候选清单 + 建议」（应含 #1 / 祖先 / 建议）")
        else:
            print("[ok]  @itemId 重名时拒绝执行，且给出候选清单 + 建议值")

    # 重名可用 `#N` 点名（N 从 1 起）；越界要报错
    xwl.apply_ops(dup_tree,
                  [{"op": "set", "path": ["@same#2", "configs", "itemId"], "value": "y"}])
    if (dup_tree["children"][1]["configs"]["itemId"] == "y"
            and dup_tree["children"][0]["configs"]["itemId"] == "same"):
        print("[ok]  @itemId#N 可点名第 N 个（不动第 1 个）")
    else:
        failures.append("@itemId#N 未精确点名第 N 个节点")
    try:
        xwl.apply_ops(dup_tree,
                      [{"op": "set", "path": ["@same#9", "configs", "itemId"], "value": "z"}])
        failures.append("@itemId#N 越界时应报错，实际却执行了")
    except xwl.ItemIdError as exc:
        if "越界" in str(exc):
            print("[ok]  @itemId#N 越界时报错（序号从 1 起）")
        else:
            failures.append("@itemId#N 越界的报错不清楚: %s" % exc)

    uniq_tree = {"children": [
        {"type": "store", "configs": {"itemId": "store", "url": "a"}, "children": []},
        {"type": "store", "configs": {"itemId": "store2", "url": "b"}, "children": []},
    ]}
    xwl.apply_ops(uniq_tree,
                  [{"op": "set", "path": ["@store2", "configs", "url"], "value": "z"}])
    if uniq_tree["children"][1]["configs"]["url"] == "z":
        print("[ok]  @itemId 唯一时正确定位目标节点")
    else:
        failures.append("@itemId 唯一时未定位到目标节点")

    # ---- 11b. 注册键重名分级（按 normalName||itemId 分组、**只两级**）----
    #   column 重名（未被引用）          → benign（取数走 grid.getSelection(0).data.*）
    #   button 重名 + 被 JS 引用         → error（app.btn 取值不确定）
    #   text   重名但各有唯一 normalName  → **不成组**（注册键互不相同 ⇒ 天然豁免）
    #   panel  重名但未被引用            → benign（warn 级已取消）
    idt_tree = {"children": [
        {"type": "viewport", "configs": {"itemId": "vp1"}, "children": [
            {"type": "text", "configs": {"itemId": "same", "normalName": "A1"}, "children": []},
            {"type": "button", "configs": {"itemId": "btn"}, "children": [],
             "events": {"click": "app.btn.setDisabled(true);"}},
            {"type": "column", "configs": {"itemId": "FCol"}, "children": []},
            {"type": "panel", "configs": {"itemId": "pnl"}, "children": []},
        ]},
        {"type": "window", "configs": {"itemId": "win1"}, "children": [
            {"type": "text", "configs": {"itemId": "same", "normalName": "A2"}, "children": []},
            {"type": "button", "configs": {"itemId": "btn"}, "children": []},
            {"type": "column", "configs": {"itemId": "FCol"}, "children": []},
            {"type": "panel", "configs": {"itemId": "pnl"}, "children": []},
        ]},
    ]}
    rep = xwl.audit_itemids(idt_tree)
    lv = {g["name"]: g["level"] for g in rep["groups"]}
    bad = {k: (v, lv.get(k)) for k, v in
           {"FCol": "benign", "btn": "error", "pnl": "benign"}.items()
           if lv.get(k) != v}
    if bad:
        failures.append("注册键分级不符（期望 vs 实得）: %s" % bad)
    elif "same" in lv:
        # "same" ×2 各有唯一 normalName⇒ 注册键互不相同 ⇒ 不该成组
        failures.append("各有唯一 normalName 的同名节点仍被判成组（注册键应互不相同）: %s" % lv)
    elif any(g["level"] == "warn" for g in rep["groups"]):
        failures.append("出现 warn 级组（**只两级**：error / benign）")
    else:
        print("[ok]  注册键重名分级：列=benign / 按钮+被引用=error / 未被引用的面板=benign / "
              "有唯一 normalName 不成组")

    # error 组应给出两种修法（补 normalName / 改 itemId），且 default(auto) 优先补 normalName
    btn_g = next(g for g in rep["groups"] if g["name"] == "btn")
    ops = xwl.recommend_fixes({"groups": [btn_g]}, "auto")
    if not btn_g["fix_normalname"] or not btn_g["fix_itemid"]:
        failures.append("error 组未同时给出「补 normalName」与「改 itemId」两种修法")
    elif not ops or ops[0]["path"][-1] != "normalName":
        failures.append("auto 修法应优先补 normalName，实得: %s" % (ops[:1],))
    else:
        print("[ok]  error 组给出两种修法，auto 优先补 normalName（不动 itemId）")

    # 类型不接受 normalName 时，auto 应回退到改 itemId（array 不在注册表白名单里）
    arr_g = {"level": "warn", "fix_normalname": [
        {"index": 2, "type": "array", "suggest": "n2", "why": "x", "type_ok": False,
         "path": ["children", 1, "configs", "normalName"]}],
        "fix_itemid": [{"index": 2, "type": "array", "suggest": "i2", "why": "x",
                        "type_ok": True, "path": ["children", 1, "configs", "itemId"]}]}
    ops2 = xwl.recommend_fixes({"groups": [arr_g]}, "auto")
    if ops2 and ops2[0]["path"][-1] == "itemId":
        print("[ok]  类型不接受 normalName 时 auto 回退到改 itemId")
    else:
        failures.append("类型不接受 normalName 时 auto 未回退到改 itemId: %s" % (ops2[:1],))

    # `--json` / `--suggest` 的产物必须可 JSON 序列化（否则子命令直接崩）
    try:
        json.dumps({k: v for k, v in rep.items() if k != "nodes"}, ensure_ascii=False)
        json.dumps(xwl.recommend_fixes(rep, "auto"), ensure_ascii=False)
        print("[ok]  itemids 的 --json / --suggest 产物可 JSON 序列化")
    except TypeError as exc:
        failures.append("itemids 的 JSON 产物不可序列化（--json / --suggest 会崩）: %s" % exc)

    # ---- 11c. 引用判定：剔注释 + 保留表不遮蔽真实 itemId ----
    cmt = {"events": {"click": "// app.commented\n/* app.blocked */\napp.real.setDisabled(true);"}}
    got = xwl.js_refs_of(cmt)
    if got == {"real"}:
        print("[ok]  js_refs_of 剔掉注释里的 app.X（只留真引用）")
    else:
        failures.append("js_refs_of 未剔注释，实得 %s" % sorted(got))

    # `store` 在保留表里，但它确实可以是 itemId —— 判定必须用未过滤集合
    st = {"children": [
        {"type": "store", "configs": {"itemId": "store"}, "children": [], "events": {}},
        {"type": "store", "configs": {"itemId": "store"}, "children": [],
         "events": {"load": "app.store.reload();"}},
    ]}
    if "store" not in xwl.js_refs_of(st) and "store" in xwl.js_refs_of(st, filtered=False):
        print("[ok]  js_refs_of(filtered=False) 保留表内名字不被滤掉（store 可判为被引用）")
    else:
        failures.append("js_refs_of 的 filtered 开关未生效")
    rep_st = xwl.audit_itemids(st)
    if next(g for g in rep_st["groups"] if g["name"] == "store")["level"] == "error":
        print("[ok]  重名 store 被 app.store 引用 → 判 error（不再被保留表遮蔽）")
    else:
        failures.append("重名 store 被引用却未判 error")

    # ---- 11d. 类型不接受 normalName 时，任何修法都不许写该键 ----
    # ⚠️ 让该组**被引用**（error 级）—— 否则未引用的重名落到 benign，
    #    `recommend_fixes` 会整组跳过、`sk` 为空 ⇒ 断言变成"恒真/恒假"的假绿。
    # 夹具不用槽位名 columns：那是保留名，不进重名组。合同仍是「array 不得写出 normalName」。
    rep_arr = xwl.audit_itemids({"children": [
        {"type": "grid", "configs": {"itemId": "g1"}, "children": [
            {"type": "array", "configs": {"itemId": "colArr"}, "children": [],
             "events": {"click": "app.colArr.focus();"}}]},
        {"type": "grid", "configs": {"itemId": "g2"}, "children": [
            {"type": "array", "configs": {"itemId": "colArr"}, "children": []}]},
    ]})
    bad_keys = [o["path"][-1] for mode in ("auto", "normalName", "itemId")
                for o in xwl.recommend_fixes(rep_arr, mode) if o["path"][-1] == "normalName"]
    if not bad_keys:
        print("[ok]  array（不接受 normalName）的任何修法都不写 configs.normalName")
    else:
        failures.append("修法 A 对不接受 normalName 的类型仍写了该键: %s" % bad_keys)
    sk: list = []
    xwl.recommend_fixes(rep_arr, "normalName", skipped=sk)
    if len(sk) == 2 and all(s["type"] == "array" for s in sk):
        print("[ok]  --fix normalName 跳过的不合法项会回报（skipped 2 项）")
    else:
        failures.append("--fix normalName 未回报被跳过的项: %s" % sk)

    # ---- 11e. 跨类型混名要单独措辞，不能说成「应唯一的类型」 ----
    # 起因：跨类型同名（如 column 与 combo 同名）与普通重名的处置不同；措辞不独特，用户会按“改个名就行”的错误方法去改。
    rep_mix = xwl.audit_itemids({"children": [
        {"type": "column", "configs": {"itemId": "mixed"}, "children": []},
        {"type": "combo", "configs": {"itemId": "mixed"}, "children": []}]})
    if "跨类型" in rep_mix["groups"][0]["reason"]:
        print("[ok]  含列控件的跨类型混名单独措辞（不再误称「应唯一的类型」）")
    else:
        failures.append("跨类型混名的理由措辞未区分: %s" % rep_mix["groups"][0]["reason"][:60])

    # ---- 11f. 读文件失败一律给 XwlLoadError（不冒裸 OSError/JSONDecodeError）----
    # 起因：调用方按 `XwlLoadError` 统一兜读盘失败；个别路径若抛别的异常（OSError/JSONDecodeError），上层漏 catch 就冒 traceback。
    miss = os.path.join(tmp, "definitely_missing.xwl")
    empty_p11 = os.path.join(tmp, "empty_p11.xwl")
    open(empty_p11, "w", encoding="utf-8").close()
    load_bad = []
    for label, path in (("不存在的文件", miss), ("空文件", empty_p11)):
        try:
            xwl.load_xwl(path)
            load_bad.append("%s 未报错" % label)
        except xwl.XwlLoadError as exc:
            if not str(exc).strip():
                load_bad.append("%s 的报错为空" % label)
        except Exception as exc:  # noqa: BLE001
            load_bad.append("%s 抛了非 XwlLoadError 的 %s: %s" % (label, type(exc).__name__, exc))
    if load_bad:
        failures.extend(load_bad)
    else:
        print("[ok]  read_xwl_text/load_xwl 读不到/解析不了时统一抛 XwlLoadError（可读消息）")

    # ---- 11g. walker 不深入 `configs`（那里的内联对象不是控件，别让 @itemId 指过去）----
    ph = {"children": [{"type": "tree", "configs": {
        "itemId": "t1", "store": {"type": "store", "configs": {"itemId": "phantom"}}}, "children": []}]}
    kinds = [t for _n, t, _c, _p, _a, _cc, _k in xwl._iter_controls(ph)]
    if kinds == ["tree"] and not xwl.itemid_hits(ph, "phantom"):
        print("[ok]  _iter_controls 不深入 configs（幻影节点不可被 @itemId 命中）")
    else:
        failures.append("_iter_controls 仍会产出 configs 内的幻影控件: %s" % kinds)

    # ---- 11h. 文本级 edit 不要求文件能解析（坏文件正是它的用途）----
    broken = os.path.join(tmp, "broken_p11.xwl")
    with open(broken, "w", encoding="utf-8", newline="") as f:
        f.write("this is not parseable at all")
    try:
        t, _b = xwl.read_xwl_text(broken)
        if t.startswith("this is not"):
            print("[ok]  edit 用的 read_xwl_text 不解析坏文件（能读即可）")
        else:
            failures.append("read_xwl_text 读到的内容不对")
    except Exception as exc:  # noqa: BLE001
        failures.append("read_xwl_text 不该对坏文件报错: %s" % exc)

    # ---- 11i. 防御性：recommend_fixes 不该因 group 缺键就崩 ----
    # 起因：recommend_fixes 吃的是半结构化的分析结果、字段可能缺；不防御就 KeyError 崩 —— 把“给条建议”升级成整命令失败。
    try:
        xwl.recommend_fixes({"groups": [{"level": "error"}, {"level": "warn"}]}, "auto")
        xwl.recommend_fixes({"groups": [{"level": "error"}]}, "normalName", skipped=[])
        print("[ok]  recommend_fixes 对缺 fix_* 键的 group 不崩（防御性取值）")
    except Exception as exc:  # noqa: BLE001
        failures.append("recommend_fixes 对缺键 group 抛错: %s: %s" % (type(exc).__name__, exc))

    # ---- 11j. itemids --name 找不到名字时，--json 路径要给 JSON（不能混纯文本）----
    # 起因：--json 是给脚本吃的契约；“找不到”也须吐合法 JSON（含 error 字段）—— 混进纯文本会让消费方解析崩。
    page_obj2 = {"children": [{"type": "panel", "configs": {"itemId": "p"}, "children": []}]}
    pj = os.path.join(tmp, "noname.xwl")
    with open(pj, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(page_obj2, 1, CRLF))
    _b = io.StringIO()
    with contextlib.redirect_stdout(_b):
        xwl.cmd_itemids(type("NS", (), {"file": pj, "name": "zzz", "dups_only": False,
                                       "suggest": False, "fix": "auto", "controls": None,
                                       "json": True})())
    out = _b.getvalue()
    try:
        o = json.loads(out)
        if o.get("error") == "not_found":
            print("[ok]  itemids --name 找不到时 --json 给结构化错误（不是纯文本 [FAIL]）")
        else:
            failures.append("itemids --name --json 的错误载荷不对: %s" % o)
    except Exception as exc:  # noqa: BLE001
        failures.append("itemids --name --json 的输出不是 JSON: %s | %r" % (exc, out[:80]))

    _check_reserved_slots(tmp, node, failures, write)



def _check_reserved_slots(tmp, node, failures, write) -> None:
    """序1至序3：保留名三元组、错槽位⑪、schema 骨架。挂在既有 itemids 块上，不是新自检块。"""

    def _bar(iid):
        return {"type": "toolbar", "configs": {"itemId": iid}, "children": []}

    def _cols(array_iid, col_iid, editor_iid):
        return {"type": "array", "configs": {"itemId": array_iid}, "children": [
            {"type": "column", "configs": {"itemId": col_iid}, "children": [
                {"type": "text", "configs": {"itemId": editor_iid}, "children": []},
            ]},
        ]}

    def _grid(iid, children, events=None):
        node_ = {"type": "grid", "configs": {"itemId": iid}, "children": children}
        if events:
            node_["events"] = events
        return node_

    def _dump(name, obj):
        return write(name, xwl.dumps_designer(obj, 1, CRLF))

    def _ambiguous(tree, name):
        copied = json.loads(json.dumps(tree))
        try:
            xwl.apply_ops(copied, [{"op": "set", "path": ["@" + name, "configs", "itemId"],
                                    "value": "zz"}])
        except KeyError as exc:
            return str(exc)
        return "executed"

    def _itemids(path, **kw):
        attrs = {"file": path, "name": None, "dups_only": False, "suggest": False,
                 "fix": "auto", "controls": None, "json": False}
        attrs.update(kw)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = xwl.cmd_itemids(type("NS", (), attrs)())
        return rc, out.getvalue(), err.getvalue()

    def _check(files, **extra):
        attrs = {"files": files, "node": node, "no_js": node is None}
        attrs.update(extra)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = xwl.cmd_check(type("NS", (), attrs)())
        return rc, buf.getvalue()

    def _ok(cond, label, detail):
        if cond:
            print("[ok]  " + label)
        else:
            failures.append(label + ": " + detail)

    slot_page = {"children": [
        _grid("grid1", [_bar("tbar"), _bar("bbar"), _cols("columns", "colA", "editor")],
              {"click": "app.tbar.focus();"}),
        _grid("grid2", [_bar("tbar"), _bar("bbar"), _cols("columns", "colB", "editor")]),
    ]}
    for name, bad in (("tbar", "grid2_tbar"), ("bbar", "grid2_bbar"),
                      ("columns", "grid2_columns"), ("editor", "colB_editor")):
        msg = _ambiguous(slot_page, name)
        _ok(msg != "executed" and "建议改名" not in msg and bad not in msg,
            "槽位 @%s 的重名报错去掉建议改名（无 %s）" % (name, bad), msg[:240])

    root_page = {"children": [
        {"type": "module", "configs": {"itemId": "mod"}, "children": [_bar("tbar"), _bar("tbar")]},
    ]}
    root_msg = _ambiguous(root_page, "tbar")
    _ok("建议改名" in root_msg, "页根两个 tbar 仍出现建议改名", root_msg[:240])

    rep = xwl.audit_itemids(slot_page)
    hit = sorted({g["name"] for g in rep["groups"]} & {"tbar", "bbar", "columns", "editor"})
    ops = xwl.recommend_fixes(rep, "auto")
    _ok(not hit and not ops, "两个 grid 的 tbar/columns/editor/bbar 不进重名组、不生成修法",
        "groups=%s ops=%s" % (hit, ops[:2]))

    dock_page = {"children": [
        {"type": "tree", "configs": {"itemId": "tree1"}, "children": [_bar("tbar")]},
        {"type": "tree", "configs": {"itemId": "tree2"}, "children": [_bar("tbar")]},
        {"type": "propertygrid", "configs": {"itemId": "pg1"}, "children": [_bar("bbar")]},
        {"type": "propertygrid", "configs": {"itemId": "pg2"}, "children": [_bar("bbar")]},
    ]}
    dock_names = {g["name"] for g in xwl.audit_itemids(dock_page)["groups"]}
    _ok("tbar" not in dock_names and "bbar" not in dock_names,
        "tree 的 tbar 与 propertygrid 的 bbar 也不进重名组",
        "groups=%s" % sorted(dock_names))

    auto_ctl = write("autonames.json", json.dumps({"children": [
        {"id": "store", "general": {"autoNames": {"any": "store"}},
         "configs": {"itemId": {"type": "string"}, "normalName": {"type": "string"}}},
    ]}, ensure_ascii=False))
    root_stores = {"children": [
        {"type": "module", "configs": {"itemId": "mod"}, "children": [
            {"type": "store", "configs": {"itemId": "store"}, "children": [],
             "events": {"load": "app.store.reload();"}},
            {"type": "store", "configs": {"itemId": "store"}, "children": []},
        ]},
    ]}
    root_rep = xwl.audit_itemids(root_stores, controls_path=auto_ctl)
    root_lv = {g["name"]: g["level"] for g in root_rep["groups"]}
    _ok(root_lv.get("store") == "error",
        "module 根上的 store 不吃 autoNames.any，被 app.store 引用仍是 error",
        "levels=%s" % root_lv)
    grid_stores = {"children": [
        {"type": "grid", "configs": {"itemId": "g1"}, "children": [
            {"type": "store", "configs": {"itemId": "store"}, "children": []}]},
        {"type": "grid", "configs": {"itemId": "g2"}, "children": [
            {"type": "store", "configs": {"itemId": "store"}, "children": []}]},
    ]}
    grid_names = {g["name"] for g in xwl.audit_itemids(grid_stores, controls_path=auto_ctl)["groups"]}
    _ok("store" not in grid_names,
        "grid 下 itemId 等于 autoNames 首选名 store 的节点不进重名组",
        "groups=%s" % sorted(grid_names))

    slot_path = _dump("slots.xwl", slot_page)
    rc, out, err = _itemids(slot_path, suggest=True)
    _ok(rc == 0 and out.lstrip().startswith("[]") and "grid2_tbar" not in out
        and "保留名" in err and "@grid1/@tbar" in err and "children[" not in err,
        "--suggest 只剩槽位时 stdout 以 [] 开头、rc=0，保留名 note 在 stderr",
        "rc=%s stdout=%r stderr=%r" % (rc, out[:180], err[:180]))
    rc, out, err = _itemids(slot_path)
    _ok(rc == 0 and "保留名" in out and "@grid1/@tbar" in out and "@grid2/@bbar" in out
        and "children[" not in out, "itemids 打 [note] 保留名，定位用 @父itemId/@名",
        out[:300])

    rc, out = _check([slot_path])
    _ok(rc == 0 and "保留名" in out and "[FAIL] ⑦" not in out,
        "只因 app.tbar 引用重复槽位时 ⑦ rc=0 且有保留名 note",
        "rc=%s %s" % (rc, " | ".join(ln.strip() for ln in out.splitlines()
                                    if "⑦" in ln or "保留名" in ln)[:240]))

    bad_page = {"children": [
        _grid("grid1", [_bar("tb1"), _cols("cols", "colC", "ed1")]),
    ]}
    bad_path = _dump("badslot.xwl", bad_page)
    rc, out = _check([bad_path])
    _ok(rc == 0 and "⑪" in out and "[FAIL] ⑪" not in out
        and all(s in out for s in ("tbar", "columns", "editor"))
        and "grid1_tb1" not in out,
        "tb1/cols/错 editor 默认 check rc=0 且 ⑪ 警告给出 tbar/columns/editor",
        "rc=%s %s" % (rc, " | ".join(ln.strip() for ln in out.splitlines() if "⑪" in ln)[:300]))
    rc, out = _check([bad_path], strict=True)
    _ok(rc == 1 and "[FAIL] ⑪" in out and all(s in out for s in ("tbar", "columns", "editor")),
        "check --strict 对三条错槽位 FAIL 且 rc=1",
        "rc=%s %s" % (rc, " | ".join(ln.strip() for ln in out.splitlines() if "⑪" in ln)[:300]))

    bbar_path = _dump("bbar_min.xwl", {"children": [_grid("grid1", [_bar("bbar")])]})
    rc, out = _check([bbar_path])
    _ok(rc == 0 and "⑪" not in out, "bbar 最小夹具默认不警告",
        "rc=%s %s" % (rc, " | ".join(ln.strip() for ln in out.splitlines() if "⑪" in ln)[:200]))

    neg_path = _dump("neg_slot.xwl", {"children": [
        _grid("grid1", [
            {"type": "array", "configs": {"itemId": "features"}, "children": [
                {"type": "feature", "configs": {"itemId": "f1"}, "children": []}]},
            {"type": "store", "configs": {"itemId": "tripFileStore"}, "children": []},
        ]),
        {"type": "tgrid", "configs": {"itemId": "tg"}, "children": [
            {"type": "ttoolbar", "configs": {"itemId": "tb1"}, "children": []},
        ]},
    ]})
    rc, out = _check([neg_path])
    _ok(rc == 0 and "⑪" not in out, "features/feature、tripFileStore、触摸错名不进 ⑪",
        "rc=%s %s" % (rc, " | ".join(ln.strip() for ln in out.splitlines() if "⑪" in ln)[:200]))

    occ_path = _dump("occ_slot.xwl", {"children": [_grid("grid1", [_bar("tbar"), _bar("tb1")])]})
    rc, out = _check([occ_path])
    _ok(rc == 0 and "⑪" in out and "外置" in out and "tbar" in out and "grid1_tb1" not in out,
        "同级已占用 tbar 时不发明带前缀的新名，并说明外置",
        "rc=%s %s" % (rc, " | ".join(ln.strip() for ln in out.splitlines() if "⑪" in ln)[:300]))

    dup_path = _dump("dup_tb1.xwl", {"children": [
        _grid("grid1", [_bar("tb1")]), _grid("grid2", [_bar("tb1")]),
    ]})
    rc, out, err = _itemids(dup_path)
    _ok("grid2_tb1" not in out and "grid1_tb1" not in out,
        "两个错名彼此重复时 itemids 不再建议加前缀", out[:300])

    post = _dump("post_tb1.xwl", {"title": "t", "children": [_grid("grid1", [_bar("tb1")])]})
    ops = write("ops_tb1.json", json.dumps(
        [{"op": "set", "path": ["title"], "value": "w"}], ensure_ascii=False))
    rc, out = _run(xwl.cmd_patch, file=post, ops=ops, indent=1, eol="auto", dry_run=False,
                   backup=False, node=None, no_js=True, allow_new_key=False)
    _ok(rc == 0 and "⑪" not in out, "patch 写盘后自检不跑 ⑪", "rc=%s tail=%s" % (rc, out[-180:]))
    rc, out = _run(xwl.cmd_expand, file=post, eol="auto", indent=1, safe=False, dry_run=False,
                   out=None, backup=False, node=None, no_js=True)
    _ok(rc == 0 and "⑪" not in out, "expand 写盘后自检不跑 ⑪", "rc=%s tail=%s" % (rc, out[-180:]))
    src = open(post, encoding="utf-8").read()
    import re as _re
    found = _re.search(r'"title"\s*:\s*"[^"]*"', src)
    oldp = write("edit_old_tb1.txt", found.group(0) if found else '"title": "MISSING"')
    newp = write("edit_new_tb1.txt", '"title": "t2"')
    rc, out = _run(xwl.cmd_edit, target=post, old_file=oldp, new_file=newp, expect=1,
                   dry_run=False, backup=False, node=None, no_js=True)
    _ok(rc == 0 and "⑪" not in out, "edit 写盘后自检不跑 ⑪", "rc=%s tail=%s" % (rc, out[-180:]))

    reg = write("slot_controls.json", json.dumps({"children": [
        {"id": kind, "general": {"design": True},
         "configs": {"itemId": {"type": "string"}, "title": {"type": "string"}}, "events": {}}
        for kind in ("grid", "tree", "column")
    ]}, ensure_ascii=False))

    def _schema(kind, skeleton):
        return _run(xwl.cmd_schema, type=kind, controls=reg, list=False, tree=False,
                    skeleton=skeleton)

    def _kids(text):
        mark = "设计器同款最小骨架"
        if mark not in text:
            return None
        blob = text[text.find(mark):]
        sk, _end = json.JSONDecoder().raw_decode(blob[blob.find("{"):])
        return [c.get("configs", {}).get("itemId") for c in sk.get("children") or []]

    rc, out = _schema("grid", False)
    _ok(rc == 0 and "槽位不可改" not in out and '"itemId": "store"' not in out,
        "schema grid 无 --skeleton 的输出不含槽位骨架", out[:200])
    rc, out = _schema("grid", True)
    _ok(rc == 0 and _kids(out) == ["store", "tbar", "columns"] and "槽位不可改" in out
        and "必须唯一" not in out,
        "schema grid --skeleton 含 store/tbar/columns，提示改为槽位不可改",
        "kids=%s hint=%s" % (_kids(out), " | ".join(ln.strip() for ln in out.splitlines()
                                                    if "提示" in ln)[:160]))
    rc, out = _schema("tree", True)
    _ok(rc == 0 and _kids(out) == ["store", "tbar"] and '"itemId": "columns"' not in out
        and "槽位不可改" in out,
        "schema tree --skeleton 只含 store 和 tbar", "kids=%s" % (_kids(out),))
    rc, out = _schema("column", True)
    _ok(rc == 0 and _kids(out) == [] and "editor" not in out,
        "schema column --skeleton 不塞空 editor", "kids=%s has_editor=%s" % (_kids(out), "editor" in out))
