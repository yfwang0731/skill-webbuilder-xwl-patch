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
    # ⚠️ 让 "columns" 组**被引用**（error 级）—— 否则未引用的重名落到 benign，
    #    `recommend_fixes` 会整组跳过、`sk` 为空 ⇒ 断言变成"恒真/恒假"的假绿。
    rep_arr = xwl.audit_itemids({"children": [
        {"type": "grid", "configs": {"itemId": "g1"}, "children": [
            {"type": "array", "configs": {"itemId": "columns"}, "children": [],
             "events": {"click": "app.columns.focus();"}}]},
        {"type": "grid", "configs": {"itemId": "g2"}, "children": [
            {"type": "array", "configs": {"itemId": "columns"}, "children": []}]},
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

