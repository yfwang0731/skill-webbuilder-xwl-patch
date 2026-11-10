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

_OPS_AUTH = ["set", "insertKey", "insert", "append", "delete"]

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

def _f05_dep_cases(tmp):
    """F05 依赖读取面：`params` 的 SQL 载体 ＋ `_scan_upstream`（放在 `new_guards` 块）。

    判据：读失败 **默认与 `--strict` 均 rc=2**（"没检查完"），逐条点名路径与原因；
    `--strict` 下若另有**已确认内容失败**（确缺参／确悬空）⇒ 汇总 rc=1 并**同时列出**读取失败；
    默认档原本仅告警的缺参**不因并存而升级**。
    另核「宽容写法载体」（单引号键）经**公共加载入口**可正确解析并报缺（⛔ 不再当读失败吞掉）。
    返回失败文案列表（空 = 通过）；通过时单独打一行 `[ok]`。
    """
    fail: list = []

    # ① 全依赖失败（载体读不动）⇒ 默认/strict 均 rc=2，逐条点名（旧树：静默 continue ⇒ rc=0）
    r, m = _f05_proj(tmp, "carrier_bad")
    page = _f05_make_page(m)
    _f05_write_carrier(m, "{ 坏掉的 json")
    for _strict in (False, True):
        rc, out = _f05_run_params(page, m, strict=_strict)
        if rc != 2:
            fail.append("F05：SQL 载体读不动（strict=%s）应 rc=2，实得 %s\n%s"
                        % (_strict, rc, out))
        if "读取失败" not in out or "未完成" not in out:
            fail.append("F05：SQL 载体读不动（strict=%s）没留缺口（缺「读取失败/未完成」）：\n%s"
                        % (_strict, out))

    # ② 部分失败：一个载体成功 **不抵消** 一个失败 ⇒ 仍 rc=2，且成功那份的 SQL 侧照常打印
    r, m = _f05_proj(tmp, "carrier_partial")
    page = _f05_make_page(m)
    _f05_write_carrier(m)                       # 成功：demo/carrier.xwl
    with open(os.path.join(m, "demo", "bad2.xwl"), "w", encoding="utf-8", newline="") as f:
        f.write("{ 另一个坏载体")
    s1 = _store("s2", "m?xwl=demo/bad2")
    _dump({"title": "p", "children": [_store("s1", "m?xwl=demo/carrier"), s1]},
          os.path.join(m, "demo", "page.xwl"))
    rc, out = _f05_run_params(page, m)
    if rc != 2:
        fail.append("F05：部分失败（一成功一失败）应 rc=2（成功不抵消失败），实得 %s\n%s"
                    % (rc, out))
    if "SQL 侧: demo/carrier.xwl" not in out:
        fail.append("F05：部分失败时成功载体的 SQL 侧未照常打印（过早上抛）：\n%s" % out)

    # ③ 宽容写法（单引号键）载体：公共加载入口应正确解析并报缺（⛔ 不计读取失败）
    r, m = _f05_proj(tmp, "carrier_tolerant")
    page = _f05_make_page(m, provide=False)
    _f05_write_carrier(m, "{'children':[{'type':'dataprovider','configs':{'itemId':'dp',"
                          "'sql':'select * from t where a={?p?}'}}]}")
    rc, out = _f05_run_params(page, m)
    if rc != 0:
        fail.append("F05：宽容写法载体（单引号键）默认档应 rc=0（仅告警缺参），实得 %s\n%s"
                    % (rc, out))
    if "SQL 侧: demo/carrier.xwl" not in out or "读取失败" in out:
        fail.append("F05：宽容写法载体（单引号键）未被公共加载入口解析（仍按读失败）：\n%s" % out)
    if "缺参" not in out:
        fail.append("F05：宽容写法载体被解析后应报出确缺参：\n%s" % out)
    rc, out = _f05_run_params(page, m, strict=True)
    if rc != 1 or "缺参" not in out:
        fail.append("F05：宽容写法载体 strict 下应因确缺参 rc=1，实得 %s\n%s" % (rc, out))

    # ④ 读失败 ＋ 已确认悬空（strict）⇒ 汇总 rc=1 且**同时列出**读取失败；默认档读失败仍 2
    r, m = _f05_proj(tmp, "carrier_bad_dangling")
    page = _f05_make_page(m, extra=[_store("s2", "m?xwl=demo/missing")])
    _f05_write_carrier(m, "{ 坏掉的 json")
    rc1, out1 = _f05_run_params(page, m, strict=True)
    if rc1 != 1:
        fail.append("F05：strict 下「读失败＋已确认悬空」应 rc=1（内容失败优先），实得 %s\n%s"
                    % (rc1, out1))
    if "读取失败" not in out1:
        fail.append("F05：strict 内容失败时未同时列出读取失败：\n%s" % out1)
    rc0, out0 = _f05_run_params(page, m)
    if rc0 != 2:
        fail.append("F05：默认档「读失败＋悬空」应 rc=2（读失败本身升级），实得 %s\n%s"
                    % (rc0, out0))

    # ⑤ 反查扫描读取失败 ⇒ 两个汇总出口直接消费 `_scan_upstream.failed` 的原始相对路径。
    #    早返出口用“SQL 无占位符”使 `needed` 为空；末行出口仍保留一个真实占位符。
    #    路径夹具同时覆盖根文件、子目录普通 `.xwl` 和合法 `.xwl.xwl`。
    _upstream_paths = ("caller.xwl", "sub/caller.xwl", "double/name.xwl.xwl")

    def _exercise_upstream_failure_paths(case, carrier_body):
        _r5, _m5 = _f05_proj(tmp, case)
        _page5 = _f05_make_page(_m5)
        _f05_write_carrier(_m5, carrier_body)
        for _rel5 in _upstream_paths:
            _bad5 = os.path.join(_m5, *(_rel5.split("/")))
            os.makedirs(os.path.dirname(_bad5), exist_ok=True)
            with open(_bad5, "w", encoding="utf-8", newline="") as _fh5:
                _fh5.write("{ 坏掉的 caller")
        for _strict in (False, True):
            _rc5, _out5 = _f05_run_params(_page5, _m5, strict=_strict, upstream=True)
            _where5 = "%s strict=%s" % (case, _strict)
            if _rc5 != 2:
                fail.append("F05：反查扫描读失败（%s）应 rc=2，实得 %s\n%s"
                            % (_where5, _rc5, _out5))
            if "扫描范围：本根" not in _out5 or "读取失败 3" not in _out5:
                fail.append("F05：反查未给「扫描范围/读取失败 3 处分桶」（%s）：\n%s"
                            % (_where5, _out5))
            if "反查覆盖" not in _out5 or "未完成" not in _out5:
                fail.append("F05：反查有失败时未标「反查覆盖未完成」（%s）：\n%s"
                            % (_where5, _out5))
            _listed5 = []
            for _line5 in _out5.splitlines():
                _m5path = re.search(r"·\s+([^：]+)：", _line5)
                if _m5path:
                    _listed5.append(_m5path.group(1))
            if set(_upstream_paths) - set(_listed5):
                fail.append("F05：反查失败清单未按真实相对路径逐字列出（%s）：%r\n%s"
                            % (_where5, _listed5, _out5))
            for _wrong5 in ("caller.xwl.xwl", "sub/caller.xwl.xwl",
                            "double/name.xwl.xwl.xwl"):
                if _wrong5 in _out5:
                    fail.append("F05：反查失败路径被重复追加 `.xwl`（%s，出现 %r）：\n%s"
                                % (_where5, _wrong5, _out5))
            if "[FAIL] 依赖读取失败 3 处" not in _out5:
                fail.append("F05：汇总失败行未准确保留 3 个反查读取失败（%s）：\n%s"
                            % (_where5, _out5))

    _exercise_upstream_failure_paths(
        "upstream_bad_early", '{"children":[{"type":"dataprovider","configs":'
                             '{"itemId":"dp","sql":"select 1 from dual"}}]}')
    _exercise_upstream_failure_paths("upstream_bad_final", _F05_CARRIER_OK)

    # ⑥ 早返出口的「strict 悬空 ＋ 反查读取失败」仍是 rc=1，并同列读取失败。
    r, m = _f05_proj(tmp, "upstream_bad_early_dangling")
    page = os.path.join(m, "demo", "page.xwl")
    _dump({"title": "p", "children": [_store("s1", "m?xwl=demo/missing")]}, page)
    with open(os.path.join(m, "bad_caller.xwl"), "w", encoding="utf-8", newline="") as f:
        f.write("{ 坏掉的 caller")
    for _strict, _want in ((False, 2), (True, 1)):
        rc, out = _f05_run_params(page, m, strict=_strict, upstream=True)
        if rc != _want:
            fail.append("F05：早返「悬空＋反查读失败」strict=%s 应 rc=%s，实得 %s\n%s"
                        % (_strict, _want, rc, out))
        if "反查覆盖" not in out or "读取失败" not in out:
            fail.append("F05：早返「悬空＋反查读失败」strict=%s 未同列读取失败：\n%s"
                        % (_strict, out))
        if _strict and not any(l.strip().startswith("[warn]") and "#36" in l
                               for l in out.splitlines()):
            fail.append("F05：早返 strict 未报告 >0 处悬空：\n%s" % out)

    # ⑦ 上游候选不加入 `provided`；关闭 --upstream 的既有诊断保持。
    r, m = _f05_proj(tmp, "upstream_candidate")
    page = _f05_make_page(m, provide=False)
    _f05_write_carrier(m)
    _dump({"title": "caller", "children": [{
        "type": "button", "configs": {"itemId": "open"},
        "expanded": False, "children": [],
        "events": {"click": "Wb.open({url:'m?xwl=demo/page', params:{p:1}});"},
    }]}, os.path.join(m, "caller.xwl"))
    rc, out = _f05_run_params(page, m, strict=True, upstream=True)
    if rc != 1 or "外部可传入" not in out or "确缺参" not in out or "p" not in out:
        fail.append("F05：上游候选不得抵消本页确缺参（应 rc=1 且同时出现候选与缺参）：\n%s" % out)
    rc_off, out_off = _f05_run_params(page, m)
    if (rc_off != 0 or "确缺参" not in out_off or "外部可传入" in out_off
            or "扫描范围：本根" in out_off):
        fail.append("F05：关闭 --upstream 的既有 params 输出发生漂移：rc=%s\n%s"
                    % (rc_off, out_off))

    # ⑧ 未定位模块根必须明确提示跳过，不能把未执行反查说成成功。
    _r8 = os.path.join(tmp, "f05proj", "upstream_no_root")
    _p8 = os.path.join(_r8, "page.xwl")
    _dump({"title": "no-root", "children": []}, _p8)
    rc8, out8 = _f05_run_params(_p8, None, upstream=True)
    if (rc8 != 0 or "未找到模块根" not in out8 or "跳过跨页反查" not in out8
            or "反查成功" in out8):
        fail.append("F05：未定位模块根未明确跳过（rc=%s）：\n%s" % (rc8, out8))

    if fail:
        return fail
    print("[ok]  F05 依赖读取面：SQL 载体/反查扫描 读失败默认与 strict 均留缺口（2）；"
          "反查早返/末行出口均保留普通及双后缀文件的真实相对路径；"
          "早返悬空与读取失败按 2/1 汇总；上游候选不抵消缺参；"
          "未定位模块根明确跳过；部分失败不抵消；宽容写法载体可解析并报缺")
    return []

_AV03_REG = [
    {"id": "onlyinreg", "general": {"type": "Ext.form.field.text"},
     "configs": {"normalName": "x", "itemId": {"type": "str"}}},
    {"id": "onlynormal", "configs": {"normalName": "y"}},
]

def _av03_proj(tmp):
    r = os.path.join(tmp, "av03proj")
    ctrl = os.path.join(r, "wb", "system", "controls.json")
    page = os.path.join(r, "wb", "modules", "page.xwl")
    os.makedirs(os.path.dirname(ctrl), exist_ok=True)
    os.makedirs(os.path.dirname(page), exist_ok=True)
    _dump({"title": "t", "children": [{"type": "panel", "configs": {"itemId": "p"}}]}, page)
    return r, ctrl, page

def _av03_write(ctrl, body):
    with open(ctrl, "w", encoding="utf-8", newline="") as f:
        f.write(body)

def _av03_run_check(ctrl, page):
    return _run(xwl.cmd_check, files=[page], node=None, no_js=True,
                no_itemid=False, no_cfgtype=False, controls=ctrl)

def _av03_run_itemids(ctrl, page):
    return _run(xwl.cmd_itemids, file=page, controls=ctrl, name=None,
                dups_only=False, suggest=False, fix="auto", json=False)

def _av03_run_params(ctrl, page, **kw):
    kw.setdefault("module_root", None)
    kw.setdefault("list_fields", False)
    kw.setdefault("upstream", False)
    kw.setdefault("strict", False)
    return _run(xwl.cmd_params, file=page, controls=ctrl, **kw)

def _av03_registry_cases(tmp):
    """AV-03：注册表**一次命令上下文只加载一次**（强身份键）＋来源/身份/降级记录＋union 不回退。

    落 `new_guards` 块（含 `check --controls` / `itemids` 两面）；`params` 面另见 `_av03_params_cases`。
    返回失败文案列表（空 = 通过）；通过时单独打一行 `[ok]`。
    """
    fail: list = []
    r, ctrl, page = _av03_proj(tmp)
    reg_json = json.dumps(_AV03_REG, ensure_ascii=False)

    def _one(nm):
        n0 = xwl._REG_LOADS
        if nm == "check":
            rc, out = _av03_run_check(ctrl, page)
        elif nm == "itemids":
            rc, out = _av03_run_itemids(ctrl, page)
        else:
            rc, out = _av03_run_params(ctrl, page)
        return rc, out, xwl._REG_LOADS - n0

    # ① 正常注册表：三命令各解析 **1 次**、基线码值不变、都打来源行
    _av03_write(ctrl, reg_json)
    for nm in ("check", "itemids", "params"):
        rc, out, n = _one(nm)
        if n != 1:
            fail.append("AV-03：正常注册表下 `%s` 应解析 1 次，实得 %d" % (nm, n))
        if rc != 0:
            fail.append("AV-03：正常注册表下 `%s` 应 rc=0，实得 %s\n%s" % (nm, rc, out))
        if "读注册表失败" in out:
            fail.append("AV-03：正常注册表下 `%s` 误报读失败：\n%s" % (nm, out))
        if "控件注册表:" not in out:
            fail.append("AV-03：`%s` 未打「控件注册表:」来源行：\n%s" % (nm, out))

    # ② 坏注册表：三命令**都看得到不可用＋降级**，各自解析 1 次；码值差异按**改前基线**（2/0/0）
    _av03_write(ctrl, "{ not json")
    expect = {"check": 2, "itemids": 0, "params": 0}
    for nm in ("check", "itemids", "params"):
        rc, out, n = _one(nm)
        if n != 1:
            fail.append("AV-03：坏注册表下 `%s` 应解析 1 次（不反复解析），实得 %d" % (nm, n))
        if rc != expect[nm]:
            fail.append("AV-03：坏注册表下 `%s` 的 rc 应保持改前基线 %s，实得 %s\n%s"
                        % (nm, expect[nm], rc, out))
        if nm == "check":
            if "取不到控件注册表" not in out:
                fail.append("AV-03：`check` 未说明「取不到控件注册表」（资源不可用）：\n%s" % out)
        else:
            if "[warn] 读注册表失败：" not in out:
                fail.append("AV-03：`%s` 未打「读注册表失败」：\n%s" % (nm, out))
            if "已回退内置兜底" not in out:
                fail.append("AV-03：`%s` 未说明**据此降级**（已回退内置兜底）：\n%s" % (nm, out))
    st = xwl._registry_state(ctrl)
    if st["state"] != "failed" or not st["why"] or st["identity"] is None:
        fail.append("AV-03：坏注册表未记录「来源＋身份＋失败原因」：%r" % (st,))
    if st["path"] != os.path.abspath(ctrl):
        fail.append("AV-03：读取记录的来源路径不对：%r" % (st.get("path"),))

    # ③ 一次上下文内多次取用 ⇒ 只解析 1 次；第二次 `_registry_load` 不是新解析
    xwl._registry_reset()
    n0 = xwl._REG_LOADS
    r1 = xwl._registry_load(ctrl)
    r1_loaded = r1["loaded_now"]          # ⚠️ 记录是**同一对象**，r2 命中缓存会把 loaded_now 置 False
    xwl._registry_configs(ctrl)
    xwl.field_types(ctrl)
    xwl.normalname_types(ctrl)
    r2 = xwl._registry_load(ctrl)
    if xwl._REG_LOADS - n0 != 1:
        fail.append("AV-03：同一上下文内多入口取用应只解析 1 次，实得 %d"
                    % (xwl._REG_LOADS - n0))
    if r1_loaded is not True or r2["loaded_now"] is not False:
        fail.append("AV-03：`_registry_load` 的 loaded_now 语义不对：r1=%r r2=%r"
                    % (r1_loaded, r2.get("loaded_now")))

    # ④ 文件被改（身份变更）⇒ 新上下文重读，不沿用旧缓存
    old_ident = st["identity"]
    _av03_write(ctrl, json.dumps(_AV03_REG + [{"id": "onlynew2", "configs": {"normalName": "z"}}],
                                 ensure_ascii=False))
    rc, out, n = _one("itemids")
    if n != 1:
        fail.append("AV-03：注册表被改后新上下文应重读 1 次，实得 %d" % n)
    if "onlynew2" not in xwl.field_types(ctrl) and "onlynew2" not in xwl.normalname_types(ctrl):
        fail.append("AV-03：注册表被改后的新内容未被读到（onlynew2 缺失）")
    st2 = xwl._registry_state(ctrl)
    if st2["identity"] == old_ident:
        fail.append("AV-03：注册表被改后身份键未变化（mtime_ns/size 未进键）：%r" % (st2,))

    # ⑤ 跨命令不复用旧缓存：连续两次 `itemids` 各解析 1 次（入口 reset）
    d = []
    for _ in range(2):
        _rc, _out, _n = _one("itemids")
        d.append(_n)
    if d != [1, 1]:
        fail.append("AV-03：连续两命令应各解析 1 次（不跨命令复用），实得 %r" % (d,))

    # ⑥ union 回归：注册表里没有任何 Ext.form.field.* 时，`field_types` 仍含**全部内置兜底**；
    #    `normalname_types` 同理（只取注册表会整类丢 → 假阳 miss）。
    _av03_write(ctrl, json.dumps([{"id": "onlynormal", "configs": {"normalName": "y"}}],
                                 ensure_ascii=False))
    ft = set(xwl.field_types(ctrl))
    nt = set(xwl.normalname_types(ctrl))
    if not set(xwl._FIELD_FALLBACK) <= ft:
        fail.append("AV-03：`field_types` 丢了内置兜底（union 被破坏）：缺 %r"
                    % sorted(set(xwl._FIELD_FALLBACK) - ft)[:5])
    if not set(xwl._NORMALNAME_FALLBACK) <= nt:
        fail.append("AV-03：`normalname_types` 丢了内置兜底（union 被破坏）：缺 %r"
                    % sorted(set(xwl._NORMALNAME_FALLBACK) - nt)[:5])
    if "onlynormal" not in nt:
        fail.append("AV-03：`normalname_types` 未并进注册表里的 `onlynormal`")

    if fail:
        return fail
    print("[ok]  AV-03 注册表一次加载：三命令各解析 1 次、坏注册表三处可见「不可用＋降级」"
          "（rc 基线 2/0/0）、身份变更重读、一次上下文多入口共用、field_types/normalname union 未丢")
    return []

def _check_new_guards(tmp, node, failures, write) -> None:
    """新近落地、**尚无守卫**的行为点 —— **薄壳**（按判据族拆分，行为逐字未变）。

    ⭐ 子函数按**文件内的连续区间**切：块内输出顺序也是行为（`--jobs` 并行档按块定义序
    回放各块的 stdout）⇒ ⛔ 不许重排调用顺序、⛔ 不许把同一段判据拆到两个族里。
    `_dump`／`_store` 已上提为模块级助手（四个族共用）。
    """
    _ng_cli_readonly(tmp, node, failures, write)
    _ng_check_controls(tmp, node, failures, write)
    _ng_contract_and_unit(tmp, node, failures, write)
    _ng_write_overwrite(tmp, node, failures, write)
    _ng_params_defaults(tmp, node, failures, write)
    _ng_platform(tmp, node, failures, write)
    # F05：读依赖失败不得被吞（依赖面：SQL 载体／反查扫描；`var.json` 三态在 params_paths 块）
    failures.extend(_f05_dep_cases(tmp))
    # AV-03：注册表事实源一次加载（check --controls／itemids 两面；params 面在 params_paths 块）
    failures.extend(_av03_registry_cases(tmp))
    # ITEM-1229 序1：四类请求身份的 default/strict 真实 rc 与 stdout
    failures.extend(_request_identity_matrix(tmp))
    failures.extend(_request_identity_shape_cases(tmp))
    # ITEM-1230 序2：直属 beforeload 后的有效键（含与序1身份隔离的组合）
    failures.extend(_beforeload_matrix(tmp))
    # ITEM-1230 同请求多键：确定缺参与未知并存 / 仅未知
    failures.extend(_beforeload_perkey_regression(tmp))
    # F1–F5 返修：请求目标/供给边界与 beforeload 未知不得假绿
    failures.extend(_repair_regression_cases(tmp))
    # 请求完成状态：目标未知即使需求集为空也不得打印请求级 ok，并进入 strict 码值
    failures.extend(_request_completion_cases(tmp))


def _ri_carrier(module_root):
    path = os.path.join(module_root, "demo", "carrier.xwl")
    _dump({"children": [{"type": "dataprovider", "configs": {
        "itemId": "dp", "sql": "select * from t where a={?K?}"}}]}, path)
    return path


def _ri_store(item_id, *, auto_load=None, params=None):
    configs = {"itemId": item_id, "url": "m?xwl=demo/carrier"}
    if auto_load is not None:
        configs["autoLoad"] = auto_load
    if params is not None:
        configs["params"] = params
    return {"type": "store", "configs": configs, "expanded": False,
            "children": []}


def _ri_button(events):
    return {"type": "button", "configs": {"itemId": "btn"},
            "expanded": False, "children": [], "events": events}


def _ri_page(module_root, children):
    path = os.path.join(module_root, "demo", "page.xwl")
    _dump({"title": "p", "children": children}, path)
    return path


def _ri_case(tmp, name, family, variant):
    module_root = os.path.join(tmp, "ri_" + name, "modules")
    os.makedirs(os.path.join(module_root, "demo"), exist_ok=True)
    _ri_carrier(module_root)
    positive = variant == "positive"
    ambiguous = variant == "ambiguous"
    if family == "stores":
        good = _ri_store("good", auto_load="true", params="{K:1}")
        bad = _ri_store("bad", auto_load="true", params="{K:1}" if positive else None)
        if ambiguous:
            bad["configs"]["normalName"] = "good"
        children = [good, bad]
    elif family == "requests":
        first = "Wb.request({url:'m?xwl=demo/carrier',params:{K:1}});"
        second = ("Wb.request({url:'m?xwl=demo/carrier',params:{K:1}});" if positive
                  else "Wb.request({url:'m?xwl=demo/carrier',params:{other:1}});")
        unknown = "Wb.request({url:dynUrl,params:{K:1}});" if ambiguous else ""
        children = [_ri_button({"click": first + second + unknown})]
    elif family == "loads":
        first = "app.shared.load({params:{K:1}});"
        second = ("app.shared.load({params:{K:1}});" if positive
                  else "app.shared.load({params:{other:1}});")
        unknown = "Wb.request({url:dynUrl,params:{K:1}});" if ambiguous else ""
        children = [_ri_store("shared", auto_load="false"),
                    _ri_button({"click": first + second + unknown})]
    else:
        explicit = ("app.initial.load({params:{K:1}});" if positive
                    else "app.initial.load({params:{other:1}});")
        unknown = "app.initial.load({params:runtimeParams});" if ambiguous else ""
        children = [_ri_store("initial", auto_load="true", params="{K:1}"),
                    _ri_button({"click": explicit + unknown})]
    page = _ri_page(module_root, children)
    return page, module_root


def _request_identity_matrix(tmp):
    """四类夹具×三变体逐请求断言请求位置、键结论、stdout 与默认/strict rc。"""
    failures = []
    cases = [("stores", variant) for variant in ("positive", "missing", "ambiguous")]
    cases += [("requests", variant) for variant in ("positive", "missing", "ambiguous")]
    cases += [("loads", variant) for variant in ("positive", "missing", "ambiguous")]
    cases += [("initial", variant) for variant in ("positive", "missing", "ambiguous")]
    for family, variant in cases:
        page, module_root = _ri_case(tmp, family + "_" + variant, family, variant)
        for strict in (False, True):
            rc, out = _run(xwl.cmd_params, file=page, module_root=module_root,
                           controls=None, list_fields=False, upstream=False,
                           strict=strict)
            # F1：store 静态 params 是每次 load 的 defaults，初始化 + 显式 load 的
            # `missing` 变体实际由 store params 补上 K，属正例；动态 params 只留未知。
            positive_like = variant == "positive" or (
                family == "initial" and variant == "missing")
            if positive_like:
                expected_rc = 0
            elif family == "initial" and variant == "ambiguous":
                expected_rc = 0 if not strict else 2
            else:
                expected_rc = 0 if not strict else 1
            label = "%s/%s strict=%s" % (family, variant, strict)
            if rc != expected_rc:
                failures.append("ITEM-1229 %s：rc 应 %s，实得 %s\n%s"
                                % (label, expected_rc, rc, out))
            if out.count("=== SQL 侧: demo/carrier.xwl") != 1:
                failures.append("ITEM-1229 %s：SQL 侧需求段应恰打印一次\n%s" % (label, out))
            if family == "stores" and "（同载体 ×2）" not in out:
                failures.append("ITEM-1229 %s：同载体引用计数丢失\n%s" % (label, out))
            if out.count("· store[") < 2 if family == "stores" else out.count("→ 请求:") < 2:
                failures.append("ITEM-1229 %s：未按请求位置分开输出\n%s" % (label, out))
            if positive_like:
                if "SQL 需要的参数在页面侧都能找到来源" not in out or "[缺参]" in out:
                    failures.append("ITEM-1229 %s：确定正例应逐请求齐全\n%s" % (label, out))
            elif "[ok]   SQL 需要的参数在页面侧都能找到来源" in out:
                failures.append("ITEM-1229 %s：页面整体不得报齐全\n%s" % (label, out))
            if variant == "ambiguous" and "[未核对]" not in out:
                failures.append("ITEM-1229 %s：歧义/未知未落到输出\n%s" % (label, out))
            if (strict and not positive_like and family != "initial" and rc != 1):
                failures.append("ITEM-1229 %s：单请求确缺参须优先于未知判 rc=1\n%s"
                                % (label, out))
    if failures:
        return failures
    print("[ok]  ITEM-1229 请求身份矩阵：双 store／双 Wb.request／同 store 多 load／"
          "初始化与后续 load 的正例、单请求缺参、歧义未知均按请求分开")
    return []


def _request_identity_shape_cases(tmp):
    """同调用 out+params、空参、嵌套伪供给与条件 store 的端到端形态。"""
    failures = []
    module_root = os.path.join(tmp, "ri_shapes", "modules")
    os.makedirs(os.path.join(module_root, "demo"), exist_ok=True)
    _ri_carrier(module_root)
    panel = {"type": "toolbar", "configs": {"itemId": "tbar"},
             "expanded": False,
             "children": [{"type": "text", "configs": {"itemId": "K"},
                           "expanded": False, "children": []}]}
    cases = [
        ("combined", [panel, _ri_button({
            "click": ("Wb.request({url:'m?xwl=demo/carrier',params:{K:1},"
                      "out:app.tbar});")})],
         0, ["传参点（2 处）", "请求身份（1 个）"], ["[缺参]"]),
        ("empty", [_ri_button({
            "click": "Wb.request({url:'m?xwl=demo/carrier'});"})],
         1, ["请求身份（1 个）", "[缺参]"], ["请求身份（0 个）"]),
        ("nested_pseudo", [_ri_button({
            "click": ("Wb.request({url:'m?xwl=demo/carrier',params:{K:1},"
                      "callback:function(){out:app.tbar;}});")})],
         0, ["传参点（1 处）", "请求身份（1 个）"],
         ["[缺参]", "[out 推荐]", "app.tbar"]),
        ("nested_function", [_ri_button({
            "click": ("function nested(){Wb.request({url:'m?xwl=demo/carrier',"
                      "params:{K:1}});} Wb.request({url:'m?xwl=demo/carrier',"
                      "params:{other:1}});")})],
         1, ["请求身份（2 个）", "[缺参]", "[ok] "],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("conditional_unrelated", [
            _ri_store("cond", auto_load="false"),
            _ri_store("other", auto_load="true"),
            _ri_button({"click": "app.other.load({params:{K:1}});"})],
         1, ["条件性 store 配置契约", "store[cond]", "[缺参]"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("conditional_config_combine", [
            _ri_store("cond", auto_load="false", params="{K:1}"),
            _ri_button({"click": "app.cond.load({params:{other:1}});"})],
         0, ["请求身份（1 个）", "需求键 ['K'] 均有本请求供给"],
         ["[缺参]", "条件性 store 配置契约"]),
    ]
    for name, children, expected_rc, required, forbidden in cases:
        page = _ri_page(module_root, children)
        rc, out = _run(xwl.cmd_params, file=page, module_root=module_root,
                       controls=None, list_fields=False, upstream=False,
                       strict=True)
        if rc != expected_rc:
            failures.append("ITEM-1229 %s：strict rc 应 %s，实得 %s\n%s"
                            % (name, expected_rc, rc, out))
        for token in required:
            if token not in out:
                failures.append("ITEM-1229 %s：输出缺少 %r\n%s" % (name, token, out))
        for token in forbidden:
            if token in out:
                failures.append("ITEM-1229 %s：输出不应含 %r\n%s" % (name, token, out))
    if failures:
        return failures
    print("[ok]  ITEM-1229 请求身份形态：同调用 out+params 归一、空参建身份、"
          "嵌套伪供给不附着、嵌套真实调用独立、条件 store 不被无关请求跳过")
    return []


def _bl_store(item_id, *, params="{K:1}", beforeload=None, auto_load="true"):
    configs = {"itemId": item_id, "url": "m?xwl=demo/carrier", "autoLoad": auto_load}
    if params is not None:
        configs["params"] = params
    node = {"type": "store", "configs": configs, "expanded": False, "children": []}
    if beforeload is not None:
        node["events"] = {"beforeload": beforeload}
    return node


def _beforeload_matrix(tmp):
    """静态保留、整体覆盖、追加恢复、合并、先追加后覆盖、条件/动态未知与身份组合。"""
    failures = []
    cases = [
        ("static", [_bl_store("st")],
         0, 0, ["SQL 需要的参数在页面侧都能找到来源"], []),
        ("replace", [_bl_store("st", beforeload="operation.params = {other: 1};")],
         0, 1, ["[缺参]", "事件前键未保留", "直属 beforeload 整体替换"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("append_restore", [_bl_store("st", params=None, beforeload=(
            "operation.params = {}; operation.params.K = 1;"))],
         0, 0, ["[ok] ", "SQL 需要的参数在页面侧都能找到来源"], []),
        ("merge_ext", [_bl_store("st", beforeload=(
            "operation.params = Ext.apply({}, operation.params, {other: 1});"))],
         0, 0, ["[ok] ", "SQL 需要的参数在页面侧都能找到来源"], []),
        ("merge_wb", [_bl_store("st", beforeload=(
            "Wb.apply(operation.params, {other: 1});"))],
         0, 0, ["[ok] ", "SQL 需要的参数在页面侧都能找到来源"], []),
        ("append_then_replace", [_bl_store("st", beforeload=(
            "operation.params.K = 1; operation.params = {other: 2};"))],
         0, 1, ["[缺参]", "事件前键未保留"], ["SQL 需要的参数在页面侧都能找到来源"]),
        ("conditional", [_bl_store("st", params=None, beforeload=(
            "if (flag) operation.params.K = 1;"))],
         0, 2, ["[未核对]", "条件固定键 K"], ["SQL 需要的参数在页面侧都能找到来源", "[缺参]"]),
        ("dynamic", [_bl_store("st", beforeload=(
            "operation.params = buildParams();"))],
         0, 2, ["[未核对]", "动态整体赋值"], ["SQL 需要的参数在页面侧都能找到来源", "[缺参]"]),
        ("d1_cond_miss", [_bl_store("st", beforeload=(
            "operation.params = {other:1}; "
            "if (window.flag) { operation.params = {Q:1}; }"))],
         0, 1, ["[缺参]", "事件前键未保留"], ["[未核对]", "SQL 需要的参数在页面侧都能找到来源"]),
        ("d2_unknown_then_determinate", [_bl_store("st", beforeload=(
            "var q; q = pick(); q.params = {Z:1}; "
            "var r = operation; r.params = {other:1};"))],
         0, 1, ["[缺参]", "事件前键未保留"], ["SQL 需要的参数在页面侧都能找到来源"]),
        ("e2_may_restore", [_bl_store("st", beforeload=(
            "operation.params = {other:1}; "
            "if (window.flag) { operation.params = {K:1}; }"))],
         0, 2, ["[未核对]", "条件整体/动态赋值"], ["[缺参]", "SQL 需要的参数在页面侧都能找到来源"]),
        ("identity_combo", [
            _bl_store("stA", beforeload="operation.params = {other: 1};"),
            _bl_store("stB", params="{K:1}")],
         0, 1, ["[缺参]", "[ok] ", "（同载体 ×2）"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
    ]
    for name, children, default_rc, strict_rc, required, forbidden in cases:
        module_root = os.path.join(tmp, "bl_" + name, "modules")
        os.makedirs(os.path.join(module_root, "demo"), exist_ok=True)
        _ri_carrier(module_root)
        page = _ri_page(module_root, children)
        for strict, expected in ((False, default_rc), (True, strict_rc)):
            rc, out = _run(xwl.cmd_params, file=page, module_root=module_root,
                           controls=None, list_fields=False, upstream=False,
                           strict=strict)
            label = "ITEM-1230 %s strict=%s" % (name, strict)
            if rc != expected:
                failures.append("%s：rc 应 %s，实得 %s\n%s" % (label, expected, rc, out))
            for token in required:
                if token not in out:
                    failures.append("%s：输出缺少 %r\n%s" % (label, token, out))
            for token in forbidden:
                if token in out:
                    failures.append("%s：输出不应含 %r\n%s" % (label, token, out))
    if failures:
        return failures
    print("[ok]  ITEM-1230 直属 beforeload：静态保留／整体覆盖删除／追加恢复／"
          "Ext.apply 与 Wb.apply 合并／先追加后覆盖／条件与动态未知／双请求身份隔离")
    return []


def _beforeload_perkey_regression(tmp):
    """同请求多键：确定缺参与未知并存、仅未知的码值与输出。"""
    failures = []

    def _carrier_multi(root):
        path = os.path.join(root, "demo", "carrier2.xwl")
        _dump({"children": [{"type": "dataprovider", "configs": {
            "itemId": "dp2",
            "sql": "select * from t where a={?K?} and b={?Q?}"}}]}, path)

    cases = [
        ("mixed_miss_and_unknown",
         "operation.params = {other:1}; "
         "if (window.flag) { operation.params = {Q:1}; }",
         "{K:1}", 0, 1,
         ["[缺参]", "['K']", "无法静态核对的参数", "['Q']"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("unknown_only",
         "if (window.flag) { operation.params = {K:1}; }",
         "{K:1,Q:1}", 0, 2,
         ["[未核对]", "['Q']"],
         ["[缺参]", "SQL 需要的参数在页面侧都能找到来源"]),
    ]
    for name, beforeload, params, default_rc, strict_rc, required, forbidden in cases:
        module_root = os.path.join(tmp, "pk_" + name, "modules")
        os.makedirs(os.path.join(module_root, "demo"), exist_ok=True)
        _carrier_multi(module_root)
        node = _bl_store("st", params=params, beforeload=beforeload)
        node["configs"]["url"] = "m?xwl=demo/carrier2"
        page = _ri_page(module_root, [node])
        for strict, expected in ((False, default_rc), (True, strict_rc)):
            rc, out = _run(xwl.cmd_params, file=page, module_root=module_root,
                           controls=None, list_fields=False, upstream=False,
                           strict=strict)
            label = "ITEM-1230 多键 %s strict=%s" % (name, strict)
            if rc != expected:
                failures.append("%s：rc 应 %s，实得 %s\n%s"
                                % (label, expected, rc, out))
            for token in required:
                if token not in out:
                    failures.append("%s：输出缺少 %r\n%s" % (label, token, out))
            for token in forbidden:
                if token in out:
                    failures.append("%s：输出不应含 %r\n%s" % (label, token, out))
    if failures:
        return failures
    print("[ok]  ITEM-1230 同请求多键：确定缺参与未知并列 strict=1，仅未知 strict=2")
    return []


def _repair_regression_cases(tmp):
    """F1–F5：请求目标/供给边界与 beforeload 未知不得假绿（默认/strict 双跑）。"""
    failures = []

    def _carrier(root, name, need):
        _dump({"children": [{"type": "dataprovider", "configs": {
            "itemId": "dp",
            "sql": "select * from t where a={?%s?}" % need}}]},
            os.path.join(root, "demo", name + ".xwl"))

    cases = [
        ("f1_autoload_explicit",
         [_bl_store("st"), _ri_button({"click": "app.st.load({params:{other:1}});"})],
         [("carrier", "K")], 0, 0,
         ["请求身份（2 个）", "[ok] store[st] · 显式调用",
          "SQL 需要的参数在页面侧都能找到来源"],
         ["[缺参]"]),
        ("f2_call_url",
         [_bl_store("st", params=None),
          _ri_button({"click": "app.st.load({url:'m?xwl=demo/other', params:{K:1}});"})],
         [("carrier", "K"), ("other", "Y")], 0, 1,
         ["[缺参]", "['Y']", "=== SQL 侧: demo/other.xwl"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f3_string_literal",
         [_ri_button({"click": (
             "var s = \"Wb.request({url:'m?xwl=demo/carrier', params:{K:1}})\";")})],
         [("carrier", "K")], 0, 0,
         ["请求身份（0 个）"],
         ["供给键", "=== SQL 侧: demo/carrier"]),
        ("f4a_helper_unknown",
         [_bl_store("st", beforeload="someHelper(operation.params);")],
         [("carrier", "K")], 0, 2,
         ["[未核对]", "直属 beforeload 后的键集合不完整"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f4b_alias_delete",
         [_bl_store("st", beforeload="var p = operation.params; delete p.K;")],
         [("carrier", "K")], 0, 2,
         ["[未核对]", "直属 beforeload 后的键集合不完整"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f4_append_unknown",
         [_bl_store("st", beforeload="Ext.apply(operation.params, runtime);")],
         [("carrier", "K")], 0, 0,
         ["[ok] ", "SQL 需要的参数在页面侧都能找到来源"],
         ["[未核对]", "传给未建语义"]),
        ("f4_discarded_apply",
         [_bl_store("st", beforeload="Ext.apply({}, operation.params, {other: 1});")],
         [("carrier", "K")], 0, 0,
         ["[ok] ", "SQL 需要的参数在页面侧都能找到来源"],
         ["[未核对]", "传给未建语义"]),
        ("f5_bracket",
         [_bl_store("st", beforeload="operation['params'] = {other: 1};")],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_op_alias",
         [_bl_store("st", beforeload="var op = operation; op.params = {other: 1};")],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_paren_alias",
         [_bl_store("st", beforeload="var op = (operation); op.params = {other: 1};")],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_chain_alias",
         [_bl_store("st", beforeload=(
             "var op = operation; var op2 = op; op2.params = {other: 1};"))],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_uncertain_alias",
         [_bl_store("st", beforeload="var op = getOperation(); op.params = {other: 1};")],
         [("carrier", "K")], 0, 2,
         ["[未核对]", "未识别接收者"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_uninit_alias_dynamic",
         [_bl_store("st", beforeload=(
             "var op; op = getOperation(); op.params = {other: 1};"))],
         [("carrier", "K")], 0, 2,
         ["[未核对]", "未识别接收者"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_uninit_alias_operation",
         [_bl_store("st", beforeload=(
             "var op; op = operation; op.params = {other: 1};"))],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_reassign_dynamic",
         [_bl_store("st", beforeload=(
             "var op = operation; op = getOperation(); op.params = {other: 1};"))],
         [("carrier", "K")], 0, 2,
         ["[未核对]", "未识别接收者"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_independent_then_reassigned",
         [_bl_store("st", beforeload=(
             "var op = {}; op.params = {other: 1}; op = operation;"))],
         [("carrier", "K")], 0, 0,
         ["SQL 需要的参数在页面侧都能找到来源"],
         ["[未核对]", "[缺参]"]),
        ("f5_unrelated_params",
         [_bl_store("st", beforeload="var other = {}; other.params = {X: 1};")],
         [("carrier", "K")], 0, 0,
         ["[ok] ", "SQL 需要的参数在页面侧都能找到来源"],
         ["[未核对]"]),
        ("f5_fn_iife",
         [_bl_store("st", beforeload="(function(){ operation.params = {other: 1}; })();")],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
        ("f5_arrow_iife",
         [_bl_store("st", beforeload="(() => { operation.params = {other: 1}; })();")],
         [("carrier", "K")], 0, 1,
         ["[缺参]", "事件前键未保留"],
         ["SQL 需要的参数在页面侧都能找到来源"]),
    ]
    for name, children, carriers, default_rc, strict_rc, required, forbidden in cases:
        module_root = os.path.join(tmp, "rep_" + name, "modules")
        os.makedirs(os.path.join(module_root, "demo"), exist_ok=True)
        for cname, need in carriers:
            _carrier(module_root, cname, need)
        page = _ri_page(module_root, children)
        for strict, expected in ((False, default_rc), (True, strict_rc)):
            rc, out = _run(xwl.cmd_params, file=page, module_root=module_root,
                           controls=None, list_fields=False, upstream=False,
                           strict=strict)
            label = "F1–F5 %s strict=%s" % (name, strict)
            if rc != expected:
                failures.append("%s：rc 应 %s，实得 %s\n%s" % (label, expected, rc, out))
            for token in required:
                if token not in out:
                    failures.append("%s：输出缺少 %r\n%s" % (label, token, out))
            for token in forbidden:
                if token in out:
                    failures.append("%s：输出不应含 %r\n%s" % (label, token, out))
            if name == "f1_autoload_explicit" and out.count("供给键 ['K']") < 2:
                failures.append("%s：autoLoad 与显式 load 都应合并 store 静态 K\n%s"
                                % (label, out))
    if failures:
        return failures
    print("[ok]  F1–F5 返修：autoLoad+显式 load 合并 store params／调用级 url 优先／"
          "字符串伪调用不建请求／beforeload 未知不被供给遮蔽／括号·别名·IIFE 不假绿")
    return []


def _request_completion_cases(tmp):
    """目标未知的 load：请求级不得 [ok]，仅未知 strict=2，另有确缺参 strict=1。"""
    failures = []
    dynamic_click = (
        "var target = getTarget(); "
        "app.st.load({url: target, params:{K:1}});")

    def _setup(name, *, need, children):
        module_root = os.path.join(tmp, "rc_" + name, "modules")
        os.makedirs(os.path.join(module_root, "demo"), exist_ok=True)
        sql = ("select * from t where a={?K?}" if need else "select 1")
        _dump({"children": [{"type": "dataprovider", "configs": {
            "itemId": "dp", "sql": sql}}]},
            os.path.join(module_root, "demo", "carrier.xwl"))
        return module_root, _ri_page(module_root, children)

    def _run_case(name, module_root, page, default_rc, strict_rc,
                  required, forbidden, strict_required=()):
        for strict, expected in ((False, default_rc), (True, strict_rc)):
            rc, out = _run(xwl.cmd_params, file=page, module_root=module_root,
                           controls=None, list_fields=False, upstream=False,
                           strict=strict)
            label = "请求完成 %s strict=%s" % (name, strict)
            if rc != expected:
                failures.append("%s：rc 应 %s，实得 %s\n%s"
                                % (label, expected, rc, out))
            tokens = list(required) + (list(strict_required) if strict else [])
            for token in tokens:
                if token not in out:
                    failures.append("%s：输出缺少 %r\n%s" % (label, token, out))
            for token in forbidden:
                if token in out:
                    failures.append("%s：输出不应含 %r\n%s" % (label, token, out))

    module_root, page = _setup(
        "dynamic_needs_k", need=True,
        children=[_ri_store("st"), _ri_button({"click": dynamic_click})])
    _run_case(
        "dynamic_needs_k", module_root, page, 0, 2,
        ["[未核对]"], ["  [ok] store[st] · 显式调用",
                      "SQL 需要的参数在页面侧都能找到来源"])

    module_root, page = _setup(
        "dynamic_empty_needs", need=False,
        children=[_ri_store("st"), _ri_button({"click": dynamic_click})])
    _run_case(
        "dynamic_empty_needs", module_root, page, 0, 2,
        [], ["  [ok] store[st] · 显式调用",
            "SQL 需要的参数在页面侧都能找到来源"],
        strict_required=["按 `--strict` 判未核对（rc=2）"])

    module_root, page = _setup(
        "unknown_plus_miss", need=True,
        children=[_ri_store("st1", auto_load="true"),
                  _ri_store("st2"),
                  _ri_button({"click": dynamic_click.replace("app.st.", "app.st2.")})])
    _run_case(
        "unknown_plus_miss", module_root, page, 0, 1,
        ["[缺参]", "[未核对]"],
        ["SQL 需要的参数在页面侧都能找到来源"])

    if failures:
        return failures
    print("[ok]  请求完成状态：目标未知不打印请求级 [ok]；空需求集 strict=2；"
          "与确缺参并存时 strict=1")
    return []


@_cap
def _ng_cli_readonly(tmp, node, failures, write) -> None:
    """① `--strict`／② `--upstream`／③ `folders` 结论行 —— **只读命令的行为面**。

    （从 `_check_new_guards` 原样搬出，判据一行未改。）
    """
    # ---- ① `--strict` 选项存在，缺源时默认只告警、`--strict` 才阻塞 ----
    # 起因：`--strict` 是 params 缺源判定的逃生开关（默认 rc=0 只告警、给了才 rc=1），但**没有回归保护** ——
    #   日后若把 `--strict` 从解析器里删掉、或让 `cmd_params` 因夹具缺 `strict` 字段而崩、
    #   或把默认退出码弄反，现有断言一条都看不见。故钉三件：选项在 `params --help` 文本里、
    #   不给 `--strict` 缺源 rc=0（只告警）、给了 rc=1。夹具手搭 Namespace 时**故意不带 strict**
    #   （顺带验 `getattr(...,False)` 兜底不炸）。
    strict_fail: list[str] = []
    try:
        _hp = xwl.build_parser()
        _sub = next((a for a in _hp._actions if getattr(a, "choices", None)), None)
        _params_help = _sub.choices["params"].format_help() if _sub is not None else ""
    except Exception as exc:  # noqa: BLE001 —— 取不到帮助文本本身就该红，别静默放过
        _params_help = ""
        strict_fail.append("① 取 `params --help` 失败: %s: %s" % (type(exc).__name__, exc))
    if "--strict" not in _params_help:
        strict_fail.append("① `params --help` 里没有 `--strict`")
    _r1 = os.path.join(tmp, "pm_strict")
    _dump({"title": "sql侧", "children": [
        {"configs": {"itemId": "dp", "sql": "select 1 from dual where a={?nosuchparam?}"},
         "type": "dataprovider", "expanded": False, "children": []}]},
        os.path.join(_r1, "sub", "sel.xwl"))
    _p1 = os.path.join(_r1, "px.xwl")
    _dump({"title": "缺源页", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st1", "m?xwl=sub/sel")]}]}, _p1)
    _kw1 = dict(file=_p1, module_root=_r1, controls=None, list_fields=False, upstream=False)
    # ⚠️ 这里**故意直调** `_run(xwl.cmd_params, **_kw1)`（**不走 `_run_cli`**）：本块要验的正是
    #    「`cmd_params` 在**缺 `strict` 字段**时靠 `getattr` 兜底不炸」——CLI 的 argparse 恒会给
    #    `strict` 赋默认值，走 CLI 就把这条兜底路径**测没了**（语义必须直调）。
    #    既然直调，就要自己兜异常：`except` 里**必须同时**置 `_rc_old` 与 `_out_old`。
    #    起因：`except` 分支若只置 `_rc_old = None`、不置 `_out_old`，异常一旦发生，下面
    #    `% (_rc_old, _out_old)` 就抛 `UnboundLocalError: '_out_old'` —— 把"缺字段抛异常"的
    #    **定向红行**盖成"块崩了"（实测成立）。`_out_new` 同理一并初始化。
    try:
        _rc_old, _out_old = _run(xwl.cmd_params, **_kw1)          # 故意不给 strict 字段
    except Exception as exc:  # noqa: BLE001
        _rc_old, _out_old = None, ""
        strict_fail.append("① 夹具缺 `strict` 字段时 `cmd_params` 抛异常（`getattr` 兜底失效）: "
                           "%s: %s" % (type(exc).__name__, exc))
    try:
        _rc_new, _out_new = _run(xwl.cmd_params, **_kw1, strict=True)
    except Exception as exc:  # noqa: BLE001
        _rc_new, _out_new = None, ""
        strict_fail.append("① `strict=True` 时 `cmd_params` 抛异常: %s: %s"
                           % (type(exc).__name__, exc))
    if _rc_old != 0:
        strict_fail.append("① 默认（不给 `--strict`）缺源应 rc=0（只告警），实得 rc=%s\n%s"
                           % (_rc_old, _out_old))
    if _rc_new != 1:
        strict_fail.append("① 给 `--strict` 缺源应 rc=1（逃生开关），实得 rc=%s\n%s"
                           % (_rc_new, _out_new))
    if strict_fail:
        failures.extend(strict_fail)
    else:
        print("[ok]  ① `--strict`：出现在 `params --help`；缺源默认 rc=0（只告警）、`--strict` 才 rc=1")

    # ---- ② `--upstream`：反查本体 + 「节点级 / 出现级」两套量纲各自标注、不混算 ----
    # 起因：`--upstream` 的末尾汇总行把**节点级**（`store.url` 能否在本根解析到文件）与
    #   **出现级**（全文 `url:` 的文字形态）两套**不同量纲**的数并排打印。这两组极易被后人
    #   改成"混算"、或当成同一口径引用（`references/measured-data.md` §11.3/§11.4 专门写了
    #   「不可混引」）。故钉：打开时两段各自标注、节点级三分类之和 = 本页带 url 的 store 数。
    # ⚠️ **反查本体与计数的断言一直是缺的**（仪表审计实测）：夹具里**根本没有上游调用方**（`calls` 恒空）、
    #   也没有**非 `m?xwl`** 的 `store.url` ⇒ 反查整体归零（`_page_ref_key` 不剥 `.xwl`）与
    #   「非 m?xwl 的 url 漏计」两个真实回归在旧自检上**全绿**。故这里补两样：
    #   ① 造**真实上游调用方**（另一页 `Wb.open({url:'m?xwl=<本页>', params:{…}})`）⇒ 断言能反查到；
    #   ② 造**非 `m?xwl` 的 `store.url`** ⇒ 断言节点级三分类**之和 = 本页 store.url 数**。
    # ⚠️ 「不开 `--upstream` 时该汇总行不得出现」是 SKILL 那句「不开时输出与冻结基线逐字一致」的
    #   **必要条件** —— 注意该口径**只对「无 miss 页面」成立**（有 miss 且未开 `--strict` 时本就多一行 `[note]`）。
    up_fail: list[str] = []
    _r2 = os.path.join(tmp, "pm_upstream")
    _dump({"title": "target", "children": []},
          os.path.join(_r2, "demo", "xxxSql", "demoSql.xwl"))
    # 真实上游调用方：另一页里 `Wb.open` 指向被测页 `h8`（引用键 = 相对模块根去扩展名 = `h8`）。
    _dump({"title": "caller", "children": [
        {"configs": {"itemId": "openBtn"}, "type": "button", "expanded": False,
         "events": {"click": "Wb.open({url:'m?xwl=h8', params:{a:1, b:2}});"},
         "children": []}]}, os.path.join(_r2, "demo", "caller.xwl"))
    _js = ("app.grid1.store.load({ params: { kw: app.kw.getValue() } }); "
           "Wb.request({ url: 'local.html' }); Wb.request({ url: u });")
    _p2 = os.path.join(_r2, "h8.xwl")
    _dump({"title": "upstream页", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False, "children": [
            _store("s1", "m?xwl=demo/xxxSql/demoSql"),   # 节点级：同根命中
            _store("s2", "m?xwl=demo/none/none"),        # 节点级：本根未找到
            _store("s3", "local.html"),                  # 节点级：非 m?xwl 的 url
            {"configs": {"itemId": "grid1"}, "type": "grid", "expanded": False,
             "events": {"click": _js},
             "children": [{"configs": {"itemId": "kw"}, "type": "text",
                           "expanded": False, "children": []}]},
        ]}]}, _p2)
    # 经 `_run_cli`（子进程真 CLI）取值：拿真实退出码、异常被隔离 —— 不许直调 `_run(xwl.cmd_*)`
    # （同 12b 的起因：直调抛异常 ⇒ 定向断言没跑到；块级兜底只让失败可读）。
    _rc_on, _out_on, _err_on = _run_cli(["params", _p2, "--module-root", _r2, "--upstream"])
    _rc_off, _out_off, _err_off = _run_cli(["params", _p2, "--module-root", _r2])
    # ① 反查本体：必须反查到 demo/caller.xwl，并给出传入键。
    if "本页被 1 处上游调用" not in _out_on:
        up_fail.append("② `--upstream` 未反查到**真实上游调用方**（应「本页被 1 处上游调用」）：\n%s"
                       % "\n".join(l for l in _out_on.splitlines()
                                   if "外部可传入" in l or "上游调用" in l or "传入键" in l))
    if not any("demo/caller.xwl" in l and "'a'" in l and "'b'" in l for l in _out_on.splitlines()):
        up_fail.append("② `--upstream` 未列出上游调用方清单（应含 demo/caller.xwl 与传入键 a/b）：\n%s"
                       % "\n".join(l for l in _out_on.splitlines() if "传入键" in l))
    _sumline = next((l for l in _out_on.splitlines() if "载入侧未纳入核对" in l), "")
    if not _sumline:
        up_fail.append("② 开 `--upstream` 时没有「载入侧未纳入核对」汇总行（本页带 store.url）")
    else:
        _mm = re.search(
            r"同根命中 (\d+) 处 / 本根未找到 (\d+) 处 / 非 m\?xwl 的 url (\d+) 处"
            r".*；出现级.*动态写法 (\d+) 处 / 非 m\?xwl 字面量 (\d+) 处", _sumline)
        if not _mm:
            up_fail.append("② 汇总行格式不符（节点级/出现级两段没各自标注、或数字缺失）:\n%s"
                           % _sumline.strip())
        else:
            _hit, _miss2, _other, _dyn, _lit = (int(x) for x in _mm.groups())
            if (_hit, _miss2, _other) != (1, 1, 1):
                up_fail.append("② 节点级三分类应为 (同根命中 1 / 本根未找到 1 / 非 m?xwl 1)，"
                               "实得 %s" % ((_hit, _miss2, _other),))
            if _hit + _miss2 + _other != 3:
                up_fail.append("② 节点级三分类之和 ≠ 本页 store.url 数（3）—— 划分不完整"
                               "（「非 m?xwl 的 url」漏计就会差一）: %s" % ((_hit, _miss2, _other),))
            if (_dyn, _lit) != (1, 1):
                up_fail.append("② 出现级应为 (动态写法 1 / 非 m?xwl 字面量 1)，实得 %s"
                               % ((_dyn, _lit),))
            if "动态写法" in _sumline.split("出现级")[0]:
                up_fail.append("② 出现级数字混进了节点级段（两套量纲未分离）")
    if "载入侧未纳入核对" in _out_off:
        up_fail.append("② 不开 `--upstream` 时仍打印了汇总行（这是「不开时输出与冻结基线逐字一致」"
                       "的必要条件；该口径只对**无 miss 页面**成立）")
    _params_help_flat = re.sub(r"\s+", " ", _params_help)
    for _need_help in ("候选不并入已证明供给", "缺参/悬空 0/1", "读取失败 2/2",
                       "读取失败并存 2/1", "仅未核对 0/2", "未定位模块根"):
        if _need_help not in _params_help_flat:
            up_fail.append("② `params --upstream --help` 缺少真实码值说明：%r" % _need_help)
    if "不改退出码" in _params_help:
        up_fail.append("② `params --upstream --help` 仍保留误导旧句「不改退出码」")
    if up_fail:
        failures.extend(up_fail)
    else:
        print("[ok]  ② `--upstream`：能反查到真实上游调用方（demo/caller.xwl，传入键 a/b）；"
              "汇总行量纲分离、节点级三分类之和 = 本页 store.url 数；不开 `--upstream` 时该行不出现")

    # ---- ③ `folders` 结论行只报「index 悬空项 / `folder.json` 损坏」 ----
    # 起因：结论行是"给用户据此行动"的那一行。「未登记」实测约一成、且多为被引用的片段页
    #   （本就不该进导航树）⇒ 若把「未登记」放进结论行会**恒亮**、淹没真问题。故把「未登记」
    #   移出结论行、只留「index 悬空项」与「`folder.json` 损坏」两个真问题。这条一旦回退
    #   （未登记又回结论行），用户就再收不到"该行动"的信号；而「`folder.json` 损坏」是真损坏
    #   （不是口径问题），若被顺带从结论行删掉也没有任何断言会挡 —— 现有断言看不见。
    fl_fail: list[str] = []
    _r3 = os.path.join(tmp, "pm_folders")
    _dd = os.path.join(_r3, "d_dangling")    # ① 有悬空 index 项
    _du = os.path.join(_r3, "d_unreg")       # ② 有未登记文件
    _db = os.path.join(_r3, "d_bad")         # ③ 有损坏 folder.json
    for _d, _idx in ((_dd, ["x.xwl", "gone.xwl"]), (_du, [])):
        os.makedirs(_d, exist_ok=True)
        with open(os.path.join(_d, "folder.json"), "w", encoding="utf-8", newline="") as _f:
            _f.write(json.dumps({"hidden": False, "index": _idx, "title": "t", "iconCls": ""},
                                ensure_ascii=False, separators=(",", ":")))
    os.makedirs(_db, exist_ok=True)
    with open(os.path.join(_db, "folder.json"), "w", encoding="utf-8", newline="") as _f:
        _f.write("{ 坏掉的 json")
    for _d, _nm in ((_dd, "x.xwl"), (_du, "y.xwl"), (_db, "z.xwl")):
        with open(os.path.join(_d, _nm), "w", encoding="utf-8", newline="") as _f:
            _f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    _rc_f, _out_f = _run(xwl.cmd_folders, path=_r3, register=None, dry_run=False)
    _concl = next((l for l in _out_f.splitlines()
                   if l.strip().startswith("目录 ") and "index 悬空项" in l), "")
    if not _concl:
        fl_fail.append("③ 找不到 `folders` 结论行（`目录 N 个 | index 悬空项 …`）:\n%s" % _out_f)
    else:
        if "index 悬空项" not in _concl:
            fl_fail.append("③ 结论行缺「index 悬空项」字样")
        if "folder.json 损坏" not in _concl:
            fl_fail.append("③ 结论行缺「folder.json 损坏」（真损坏，必须留在结论行）")
        if "未登记" in _concl:
            fl_fail.append("③ 结论行又出现了「未登记」（应只进明细、不上结论行）")
        if "读不动" not in _concl:
            fl_fail.append("③ 结论行缺「读不动」分列（确认问题与无法判断必须分开）")
    if _rc_f != 1:
        fl_fail.append("③ 悬空＋结构损坏目录应 rc=1（读不动才 2），实得 %s" % _rc_f)
    if "未登记" not in _out_f:
        fl_fail.append("③ 夹具没造出「未登记」—— 「结论行不含它」这条就名不副实")
    if fl_fail:
        failures.extend(fl_fail)
    else:
        print("[ok]  ③ `folders` 结论行：含「index 悬空项」「folder.json 损坏」、"
              "不含「未登记」（未登记只在明细）")

@_cap
def _ng_check_controls(tmp, node, failures, write) -> None:
    """④ `check --controls`（⑨／⑥-ext／⑩／拒写归因）／⑤ ⑥-ext 行序确定 —— **`check` 的开关面**。

    （从 `_check_new_guards` 原样搬出，判据一行未改。）
    """
    # ---- ④ `check --controls`：⑨ 校 configs 键合法性（`[warn]`）＋ ⑥ 扩到 configs 内联 `[js]`（`[FAIL]`）----
    # 起因（`#48`/`#49` 落地后**整条无覆盖**）：`check` 的 ⑨/⑥-ext **只在显式给 `--controls` 时才跑**，
    #   而本文件**没有一条断言**碰 `--controls`（`_run_check` 的 NS 根本没有 `controls` 字段）⇒
    #   两个新能力"绿但空"：把 `_check_registry_dims` 整段删掉、或把 ⑨ 误改成 `[FAIL]`、或把 ⑥-ext
    #   退回只校 events，**自检都不动**。故**双向钉**：真阳性（非法键 ⇒ ⑨ 报出；`[js]` 语法错 ⇒ ⑥ 进 rc）
    #   ＋ 假阳性守卫（合法键 ⇒ 不进 `[warn]`；不给 `--controls` ⇒ 默认面一行不出现）。
    # ⚠️ 夹具用**自造 mini 注册表**（同 §16 的 `mini_controls.json` 手法）：不依赖工程 `wb/system/controls.json`，
    #   故 CI 里照跑；`[js]` 语法错**必须真跑 node** ⇒ 无 node 时该半条跳过（非默认面，跳过要出声）。
    # ⚠️ ⑨ 取 `[warn]` 而非 `[FAIL]` 是**有意**（`#48` 的裁定，理由见 `_check_registry_dims` docstring）⇒
    #   本段的 `⑨` 断言**只判"warn 里出现、rc 仍 0"**，不判"进 rc"。
    reg_fail: list[str] = []
    reg4 = os.path.join(tmp, "mini_controls_reg.json")
    with open(reg4, "w", encoding="utf-8") as f:
        json.dump({"children": [
            {"id": "grid", "general": {"design": True},
             "configs": {"itemId": {"type": "string"}, "selType": {"type": "string"}},
             "events": {}},
            {"id": "label", "general": {"design": True, "xtype": "label"},
             "configs": {"itemId": {"type": "string"}, "html": {"type": "string"},
                         "renderer": {"type": "js"}},
             "events": {}},
        ]}, f, ensure_ascii=False)

    def _mkreg(name, cfg):
        p = os.path.join(tmp, "reg-%s.xwl" % name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(xwl.dumps_designer(
                {"title": "t", "roles": {}, "children": [
                    {"configs": cfg, "type": "label", "expanded": False, "children": []}]},
                1, CRLF))
        return p

    def _run_check_ctl(files, node_):
        buf = io.StringIO()
        ns = type("NS", (), {"files": files, "node": node_, "no_js": node_ is None,
                             "controls": reg4, "no_itemid": True})()
        with contextlib.redirect_stdout(buf):
            code = xwl.cmd_check(ns)
        return code, buf.getvalue()

    # ④-1 真阳性（⑨）：`grid.flex` 不在 mini 注册表的 grid.configs 里 ⇒ 应进 `[warn]`、rc 仍 0
    _rc9, _o9 = _run_check_ctl([_mkreg("okkey", {"itemId": "l1", "html": "<b>x</b>"})], node)
    _rc9b, _o9b = _run_check_ctl([_mkreg("gridflex", {"itemId": "g1", "selType": "rowmodel",
                                                      "flex": "1"})], node)
    if "⑨" not in _o9b or "flex" not in _o9b:
        reg_fail.append("④ ⑨ 真阳性：含非法键 `grid.flex` 的文件没被 `[warn]` 报出：\n%s" % _o9b)
    # ⚠️ 判**明细行**（带具体键名）而非只看 "⑨" —— 运行级汇总行（`[warn] ⑨ … N 个节点（涉及 M 个文件）`）
    #   由 `_check_registry_dims` 返回的计数驱动，即使"明细被弱化"它**照旧打印** ⇒ 只判 "⑨ 出现过"
    #   会被它兜住（**注入实测**：把 `warns.extend(bad_keys)` 改成 `pass`、断言仍绿）。故此处钉
    #   "文件名段里那行明细"（`⑨ grid 的 configs 键不在注册表：flex`）。
    if not any(l.strip().startswith("[warn] ⑨") and "flex" in l for l in _o9b.splitlines()):
        reg_fail.append("④ ⑨ 明细行缺失（只有汇总行 ⇒ 弱化 `warns.extend(bad_keys)` 会逃逸）：\n%s" % _o9b)
    if _rc9b != 0:
        reg_fail.append("④ ⑨ 是 `[warn]` 级（不进 rc），但含非法键时 rc=%s（应为 0）" % _rc9b)
    # ④-2 假阳性守卫（⑨）：只含注册表内合法键 ⇒ 应打 `[ok] ⑨ … 0 个非法键`、不进 warn
    if "[warn]" in _o9 and "⑨" in _o9:
        reg_fail.append("④ ⑨ 假阳性：全合法键的文件仍被 warn：\n%s" % _o9)
    # ④-2b（`#76`·⑨`[ok]` 量纲）`#76` 的**第二半**在 ⑨ 的 `[ok]` 明细行（`0 个非法键`）——
    #   既有断言只锚了运行级汇总行「N 个节点」；把这里的 `个` 改回 `处` **三块仍全绿**（复核实测）
    #   ⇒ 补钉该量纲词（与汇总行同一立意：**统一量纲为「个」**）。
    _ok9 = [l.strip() for l in _o9.splitlines() if "⑨ configs 键合法性" in l]
    if not _ok9:
        reg_fail.append("④ ⑨（`#76`）全合法键时未见 `[ok] ⑨ configs 键合法性` 行：\n%s" % _o9)
    else:
        if "个非法键" not in _ok9[0]:
            reg_fail.append("④ ⑨（`#76`）`[ok]` 行未用量纲词「个非法键」：%s" % _ok9[0])
        if "处非法键" in _ok9[0]:
            reg_fail.append("④ ⑨（`#76`）`[ok]` 行仍用「处非法键」：%s" % _ok9[0])
    # ④-3 真阳性（⑥-ext）：`configs.renderer`（注册表标 `[js]`）写入语法错 ⇒ 应 `[FAIL]` 且 rc≠0
    if node is not None:
        _rcj, _oj = _run_check_ctl([_mkreg("badjs", {"itemId": "l1",
                                                     "renderer": "function(v){ return ; ;;("})], node)
        if "⑥" not in _oj or "JS 语法" not in _oj:
            reg_fail.append("④ ⑥-ext 真阳性：`configs.renderer` 语法错没被 ⑥ 报出：\n%s" % _oj)
        if _rcj == 0:
            reg_fail.append("④ ⑥-ext 是 `[FAIL]` 级（进 rc），语法错时 rc 仍 0")
        # ④-3b（`#78`）⑥-ext 报错正文须是**真诊断**（含 `Error`），⛔ 不是「已删除的临时文件路径」死链。
        _fl8 = [l.strip() for l in _oj.splitlines() if l.strip().startswith("[FAIL] ⑥ configs.")]
        if not _fl8:
            reg_fail.append("④ ⑥-ext（`#78`）未找到 `[FAIL] ⑥ configs.` 行：\n%s" % _oj)
        elif "Error" not in _fl8[0]:
            reg_fail.append("④ ⑥-ext（`#78`）报错正文不含真诊断（`Error`）—— 疑似临时文件路径死链：\n%s" % _oj)
        if "xwl_ev_" in _oj:
            reg_fail.append("④ ⑥-ext（`#78`）输出含随机临时文件名（`xwl_ev_`）—— 应只给真诊断：\n%s" % _oj)
        # ④-3c（`#78`·⑥events 调用点）`_js_err_head` 有**两处调用点**：⑥-ext（`% (loc, _js_err_head(err))`，
        #   `p78` 的 `find` 只锚这处）与 ⑥ **events**（`head = _js_err_head(err)`）。把 events 那处退回
        #   `err.splitlines()[0]`（＝临时文件路径死链）**三块全绿**（复核实测）⇒ 补：事件 JS 语法错时，
        #   `[FAIL] ⑥ events.<名>` 的正文须含真诊断、⛔ 不含随机临时名。
        _pev = os.path.join(tmp, "reg-events-badjs.xwl")
        with io.open(_pev, "w", encoding="utf-8", newline="") as _fevw:
            _fevw.write(xwl.dumps_designer(
                {"title": "t", "roles": {}, "children": [
                    {"configs": {"itemId": "l1"},
                     "events": {"click": "function(){ return ; ;;("},
                     "type": "label", "expanded": False, "children": []}]},
                1, CRLF))
        _rcev, _oev = _run_check_ctl([_pev], node)
        _fev = [l.strip() for l in _oev.splitlines() if l.strip().startswith("[FAIL] ⑥ events.")]
        if not _fev:
            reg_fail.append("④ ⑥-events（`#78`）事件 JS 语法错没被 ⑥ 报出：\n%s" % _oev)
        elif "Error" not in _fev[0]:
            reg_fail.append("④ ⑥-events（`#78`）报错正文不含真诊断（`Error`）—— 疑似临时文件路径死链：\n%s" % _oev)
        if "xwl_ev_" in _oev:
            reg_fail.append("④ ⑥-events（`#78`）输出含随机临时文件名（`xwl_ev_`）—— 应只给真诊断：\n%s" % _oev)
    # ④-4 默认面（承重墙）：不给 `--controls` ⇒ ⑨/⑥-ext 一行都不出现
    _rc0, _o0 = _run_check([_mkreg("def", {"itemId": "g1", "flex": "1"})], node)
    if "⑨" in _o0 or "configs 内联" in _o0:
        reg_fail.append("④ 默认面：不给 `--controls` 时仍打了 ⑨/⑥-ext 的行（承重墙破）：\n%s" % _o0)
    # ④-5（`#76`）⑨ 运行级汇总的**量纲**须与明细一致 —— 用「N 个节点」而非「N 处」
    #   （明细是"按节点一行、列该节点**全部**非法键" ⇒ 汇总若按"处"数会与明细的键数对不上：
    #    一节点 3 非法键时明细 3 键、汇总却报"1 处"）。
    _rc9c, _o9c = _run_check_ctl([_mkreg("threebad", {"itemId": "m1", "aaa": "1",
                                                      "bbb": "2", "ccc": "3"})], node)
    if "个节点（涉及" not in _o9c:
        reg_fail.append("④ ⑨（`#76`）运行级汇总未用「N 个节点（涉及 M 个文件）」量纲：\n%s" % _o9c)
    if _rc9c != 0:
        reg_fail.append("④ ⑨（`#76`）量纲修正不应改 rc，实得 rc=%s" % _rc9c)
    def _run_check_nc(files, node_, **extra):
        """同 `_run_check`，但可加**额外属性**（本段只用 `no_cfgtype=True` / `controls=…`）。

        ⚠️ 单独造一个而不是改模块级 `_run_check` 的签名：那个被十余处断言共用，
           多一个参数就多一个"别处传错也静默生效"的面。
        """
        buf = io.StringIO()
        _attrs = {"files": files, "node": node_, "no_js": node_ is None}
        _attrs.update(extra)
        ns = type("NS", (), _attrs)()
        with contextlib.redirect_stdout(buf):
            code = xwl.cmd_check(ns)
        return code, buf.getvalue()

    # ④-6（⑩）真阳性：`configs` 里 `width` / `maxLength` 写成 int ⇒ `[FAIL] ⑩`、rc=1
    #   起因（按守卫维护纪律）：⑩ 是**零覆盖**项 —— 把 `_scan_cfg_types` 整段删掉、或把
    #   `--no-cfgtype` 开关删掉，本文件一条断言都不会红（`check --help` 行数 15→14 仍在上限内）。
    #   ⚠️ 夹具**必须含两个不同键**（`width` ＋ `maxLength`）：只锚 `width` 时，把判据改成
    #      "只查 width" 仍全绿 —— 那就等于没钉住"遍历整个 `configs`"这件事。
    _rc10, _o10 = _run_check([_mkreg("cfgint", {"itemId": "l1", "html": "x",
                                                "width": 300, "maxLength": 20})], node)
    _fl10 = [l.strip() for l in _o10.splitlines() if l.strip().startswith("[FAIL] ⑩")]
    if not _fl10:
        reg_fail.append("④ ⑩ 真阳性：`configs` 含 int 值却未见 `[FAIL] ⑩` 明细行：\n%s" % _o10)
    else:
        for _k in ("width", "maxLength"):
            if _k not in _o10:
                reg_fail.append("④ ⑩ 真阳性：明细行未点名非字符串键 `%s`"
                                "（判据疑似只查某一键）：\n%s" % (_k, _o10))
    if _rc10 == 0:
        reg_fail.append("④ ⑩ 是 `[FAIL]` 级（进 rc），`configs` 含 int 值时 rc 仍 0")

    # ④-7（⑩）`--no-cfgtype` ⇒ rc=0 且 **⑩ 的判定行一行都不出现**（开关真的关掉了判定面）
    #   ⚠️ 判据是"无 `[FAIL] ⑩` / 无 `[ok] … ⑩`"，⛔ 不是"输出里没有 ⑩ 这个字符"：
    #      跳过时**必须**留一行 `[note] ⑩ … 已按 --no-cfgtype 跳过`（否则与"跑了且干净"无法区分）。
    _rcnc, _onc = _run_check_nc([_mkreg("cfgint_nc", {"itemId": "l1", "html": "x",
                                                      "width": 300})], node, no_cfgtype=True)
    _jud10 = [l.strip() for l in _onc.splitlines()
              if ("⑩" in l) and (l.strip().startswith("[FAIL]") or l.strip().startswith("[ok]"))]
    if _jud10:
        reg_fail.append("④ ⑩ `--no-cfgtype`：开关给上了，仍有 ⑩ 的判定行：\n%s" % _onc)
    if not any(l.strip().startswith("[note]") and "⑩" in l and "--no-cfgtype" in l
               for l in _onc.splitlines()):
        reg_fail.append("④ ⑩ `--no-cfgtype`：未留 `[note] ⑩ … 已按 --no-cfgtype 跳过` 行"
                        "（分不清「跳过」与「没跑」）：\n%s" % _onc)
    if _rcnc != 0:
        reg_fail.append("④ ⑩ `--no-cfgtype`：跳过 ⑩ 后 rc 应为 0，实得 %s" % _rcnc)

    # ④-8（⑩）全字符串 ⇒ rc=0 且留 `[ok] ⑩ … N 个节点、0 个非字符串值`
    #   起因：⑩ 通过态**一行都不打**时，"跑了且干净"与"根本没跑"在输出上无法区分
    #   （`--no-cfgtype` 静音后更是完全一样）。
    _rcok, _ook = _run_check([_mkreg("cfgstr", {"itemId": "l1", "html": "x",
                                                "width": "300"})], node)
    _ok10 = [l.strip() for l in _ook.splitlines() if l.strip().startswith("[ok]") and "⑩" in l]
    if not _ok10:
        reg_fail.append("④ ⑩ 通过态：`configs` 全为字符串时未见 `[ok] ⑩ …` 行"
                        "（分不清「真跑了」与「没跑」）：\n%s" % _ook)
    elif "个节点" not in _ok10[0] or "0 个非字符串值" not in _ok10[0]:
        reg_fail.append("④ ⑩ 通过态：`[ok] ⑩` 行量纲/结论不符（期望 `N 个节点、0 个非字符串值`）：%s"
                        % _ok10[0])
    if _rcok != 0:
        reg_fail.append("④ ⑩ 通过态：全字符串时 rc 应为 0，实得 %s" % _rcok)

    # ④-9（⑩）**射程**：⑩ **只在 `check` 生效** —— 写盘后的自检（`_post_check`）不判它
    #   起因：`_post_check` 传的是 `checks={1..6}`。⑩ 是**文件既有的内容属性**（写盘只搬字节、
    #     不改值），在这里判会让"本来写得进"的存量坏文件突然 `patch` 失败（行为突变）。
    #     一旦有人把它并进写盘自检，`patch` / `expand` 会开始对这类文件 rc≠0 —— 本条钉的就是那个射程。
    #   判据（模板＝④-4「默认面一行都不出现」）：`configs` 含 **int** 的文件跑 `patch`（最小合法 ops）
    #     与 `expand` ⇒ **两者 rc=0**、且输出里**没有 `[FAIL] ⑩`**。
    #   ⚠️ 同时必须留那条 `[warn] … configs 非字符串值 …` 预告：它证明写盘路径**看见了**这些值、
    #     只是**不判**它 —— 否则「射程正确（不判）」与「根本没看见」在输出上分不清。
    _f9w = _mkreg("cfgint_write", {"itemId": "l1", "html": "x", "width": 300})
    _ops9w = os.path.join(tmp, "ops_cfgint_write.json")
    with open(_ops9w, "w", encoding="utf-8") as _fh9w:
        json.dump([{"op": "set", "path": ["title"], "value": "w"}], _fh9w)
    for _nm9w, _argv9w in (("patch", ["patch", _f9w, "--ops", _ops9w, "--no-js"]),
                           ("expand", ["expand", _f9w, "--no-js"])):
        _rc9w, _o9w, _e9w = _run_cli(_argv9w)
        _txt9w = _o9w or _e9w or ""
        _ln9w = _txt9w.splitlines()
        _fl9w = [l.strip() for l in _ln9w if l.strip().startswith("[FAIL]") and "⑩" in l]
        if _rc9w != 0:
            reg_fail.append("④-9（⑩）射程：`%s` 对 configs 含 int 的文件应 rc=0"
                            "（⑩ 不在写盘后自检里，判了会让存量坏文件写不进去），实得 %s：%s"
                            % (_nm9w, _rc9w, _txt9w.strip()[-200:]))
        if _fl9w:
            reg_fail.append("④-9（⑩）射程：`%s` 输出里出现了 `[FAIL] ⑩`"
                            "（⑩ 只该在 `check` 里判，不该进写盘后自检）：%s" % (_nm9w, _fl9w[0]))
        if not any(l.strip().startswith("[warn]") and "configs 非字符串值" in l for l in _ln9w):
            reg_fail.append("④-9（⑩）射程：`%s` 没留 `[warn] … configs 非字符串值 …` 预告"
                            "（分不清「射程正确：不判 ⑩」与「根本没看见非字符串值」）：%s"
                            % (_nm9w, _txt9w.strip()[-200:]))

    # ④-10（⑩）运行级汇总的**量纲**：节点**去重** / 处数＝命中条数 / 文件数（模板＝④-5 的量纲断言）
    #   起因：⑩ 的汇总是「N 个节点 / M 处（涉及 K 个文件）」三个数。一节点多键命中时，
    #     "节点数"必须是**去重后的节点数**、⛔ 不是命中条数 —— 否则与 ⑨ 的「N 个节点」量纲不一致
    #     （同一条纪律：明细是"按节点一行、列该节点**全部**非法键"，汇总按"处"数就与明细对不上）。
    #   夹具：A＝**一个节点里两个**非字符串键（width / maxLength）；B＝**一个节点里一个**（width）
    #     ⇒ 2 个节点（去重）/ 3 处（命中条数）/ 涉及 2 个文件。三个数**逐个**钉。
    #   ⚠️ 只钉其中一个数不够：把 `cfg_nodes_all += len({h[0] …})` 退回"命中条数"时，
    #     节点数会变成 3 而处数仍是 3 —— 只钉处数的断言照样绿（本仓的注入实测）。
    _a10w = _mkreg("cfgagg_two", {"itemId": "l1", "html": "x", "width": 300, "maxLength": 20})
    _b10w = _mkreg("cfgagg_one", {"itemId": "l2", "html": "y", "width": 300})
    _rc10w, _o10w = _run_check([_a10w, _b10w], node)
    if "2 个节点 / 3 处（涉及 2 个文件）" not in _o10w:
        reg_fail.append("④-10（⑩）聚合量纲：两文件（一节点 2 键 ＋ 一节点 1 键）的汇总行应为"
                        "「2 个节点 / 3 处（涉及 2 个文件）」（节点去重、处数＝命中条数、文件数），"
                        "实得：\n%s" % _o10w)
    if _rc10w == 0:
        reg_fail.append("④-10（⑩）聚合量纲：⑩ 是 `[FAIL]` 级（进 rc），两份含 int 的文件 rc 仍 0")

    # ④-11 `check --controls` 指到**一个目录** ⇒ rc=2 且**文案自解释**（不是裸 traceback）
    #   起因：`--controls` 给错（目录 / 坏 JSON）是**调用方配置错**，若只留一行 traceback，
    #     用户会去查被检文件的格式（错方向）。判据取 rc ＋ 一个关键字（⛔ 不钉整句，
    #     否则文案一改就红、维护面翻倍）。
    #   ⚠️ 编号原为 ④-9；现把 ④-9 / ④-10 归给 ⑩ 的两条断言（射程 / 聚合量纲），
    #     本条与下一条**内容一字未改**、只改编号（它们仍有价值，⛔ 不退役）。
    _f9 = os.path.join(tmp, "controls_dir_probe.xwl")
    with open(_f9, "w", encoding="utf-8", newline="") as _fh9:
        _fh9.write('{"hidden":false,"children":[],"roles":{},"title":"t",'
                   '"iconCls":"","inframe":true,"pageLink":""}\n')
    _d9 = os.path.join(tmp, "controls_isdir")
    os.makedirs(_d9, exist_ok=True)
    _rc9, _o9, _e9 = _run_cli(["check", _f9, "--controls", _d9, "--no-js"])
    _txt9 = _o9 or _e9 or ""
    if _rc9 != 2:
        reg_fail.append("④-11 `check --controls <目录>` 应 rc=2（调用方配置错），实得 %s：%s"
                        % (_rc9, _txt9.strip()[-160:]))
    elif "取不到控件注册表" not in _txt9:
        reg_fail.append("④-11 `check --controls <目录>` 的文案没自解释"
                        "（应说明「取不到控件注册表」而不是裸 traceback）：%s" % _txt9.strip()[-200:])

    # ④-12 `patch`／`expand` 对「非设计器产物」文件**被拒写** ⇒ **只断言 rc == 2**
    #   起因：宽容面接进了只读命令后，写盘路径若"能读就能写"，会把这类文件**整份重排**
    #     并 rc=0 绿灯（已由注入实测过这个事故）。⛔ 这里只钉 rc：文案的点名正确性由 ④-13 钉
    #     （那处文案有真缺陷：未引号值被报成未引号键）；再钉一次只会变成两处维护。
    #   ⚠️ 编号原为 ④-10；现让位给 ⑩ 的两条断言，**内容只改了这句注释**（钉 rc 的判据未变）。
    _f10 = os.path.join(tmp, "non_designer_probe.xwl")
    with open(_f10, "w", encoding="utf-8", newline="") as _fh10:
        _fh10.write("{'hidden':false,'children':[],'roles':{},'title':'t',"
                    "'iconCls':'','inframe':true,'pageLink':''}\n")
    _ops10 = os.path.join(tmp, "ops_non_designer.json")
    with open(_ops10, "w", encoding="utf-8") as _fh10b:
        json.dump([{"op": "set", "path": ["title"], "value": "x"}], _fh10b)
    for _cmd10 in (["patch", _f10, "--ops", _ops10, "--no-js"],
                   ["expand", _f10, "--dry-run", "--no-js"]):
        _rc10, _o10, _e10 = _run_cli(_cmd10)
        if _rc10 != 2:
            _tail10 = (_o10 or _e10 or "").strip().splitlines()[-1:]
            reg_fail.append("④-12 `%s` 对「非设计器产物」应 rc=2（拒写），实得 %s：%s"
                            % (_cmd10[0], _rc10, _tail10))

    # ④-13 **拒写归因的点名必须与夹具实际写法一致**（`_wide_kinds`，四类各一条）
    #   起因（归因文案的真缺陷）：归因是"把归一前后文本做字符级 diff 再分类"，其中两处判错：
    #     ① token 终止集漏了 `,` ⇒ 扫未引号**值**时会越过逗号吃到下个键的 `:` ⇒ 误报成未引号**键**；
    #     ② 归一给一个未引号 token 补**一对**引号（两次 insert）⇒ 每个 token 被数两遍（×2）。
    #   实测反例：`{"title":abc,"iconCls":"x"}` 报「未引号键 ×2」，连类别带数量都错。
    #   ⚠️ 拒写本身（rc=2、文件不动）一直是正确的 —— 错的只是**文案**，所以只有钉文案才抓得到。
    #   判据：四类各给一个最小夹具，逐条核「类别对 ＋ 数量对 ＋ 错误类别不出现 ＋ rc=2 ＋ 文件没动」。
    for _lab13, _fn13, _txt13, _want13, _n13, _bad13 in (
        ("sq_key（单引号键／值）", "rej_sq.xwl", "{'title':'t'}\n", "单引号键／值", 4, ()),
        ("two_obj（相邻 {...}{...}）", "rej_two.xwl", '{"title":"t"}{"x":1}\n', "相邻贪婪", None, ()),
        ("uq_value（未引号值）", "rej_uqv.xwl", '{"title":abc,"iconCls":"x"}\n',
         "未引号值", 1, ("未引号键",)),
        ("uq_key_simple（未引号键）", "rej_uqk.xwl", '{width:"85"}\n',
         "未引号键", 1, ("未引号值",)),
    ):
        _p13 = os.path.join(tmp, _fn13)
        with open(_p13, "w", encoding="utf-8", newline="") as _fh13:
            _fh13.write(_txt13)
        _before13 = open(_p13, "rb").read()
        _rc13, _o13, _e13 = _run_cli(["patch", _p13, "--ops", _ops10, "--no-js"])
        _txt13o = _o13 or _e13 or ""
        _rej13 = [l.strip() for l in _txt13o.splitlines() if "非设计器产物" in l]
        if _rc13 != 2:
            reg_fail.append("④-13 拒写归因：`%s` 应 rc=2（拒写），实得 %s：%s"
                            % (_lab13, _rc13, _txt13o.strip()[-200:]))
        if open(_p13, "rb").read() != _before13:
            reg_fail.append("④-13 拒写归因：`%s` 被拒写却改了文件（应一个字节都不动）" % _lab13)
        if not _rej13:
            reg_fail.append("④-13 拒写归因：`%s` 没有拒写行（找不到「非设计器产物」）：%s"
                            % (_lab13, _txt13o.strip()[-200:]))
            continue
        _ln13 = _rej13[0]
        if _want13 not in _ln13:
            reg_fail.append("④-13 拒写归因：`%s` 的类别点错了 —— 期望含「%s」，实得：%s"
                            % (_lab13, _want13, _ln13))
        if _n13 is not None and ("%s ×%d" % (_want13, _n13)) not in _ln13:
            reg_fail.append("④-13 拒写归因：`%s` 的**数量**点错了 —— 期望「%s ×%d」，实得：%s"
                            % (_lab13, _want13, _n13, _ln13))
        for _b13 in _bad13:
            if _b13 in _ln13:
                reg_fail.append("④-13 拒写归因：`%s` 报出了**不属于它的类别**「%s」"
                                "（token 扫描越界）：%s" % (_lab13, _b13, _ln13))

    if reg_fail:
        failures.extend(reg_fail)
    else:
        print("[ok]  ④ `check --controls`：⑨ 校 configs 键（非法键进 `[warn]`、rc 不变）＋ "
              "⑥ 扩到 configs 内联 `[js]`（语法错进 `[FAIL]`、rc≠0）；不给 `--controls` 时该段不出现"
              " ＋ ⑩ 值类型（int ⇒ rc=1；`--no-cfgtype` ⇒ 无 ⑩；全字符串 ⇒ `[ok] ⑩`）"
              " ＋ ⑩ 射程（patch/expand 不判 ⑩、只留 `[warn]` 预告）＋ ⑩ 聚合量纲"
              "（节点去重 / 处数 / 文件数三个数）＋ 拒写归因四类点名（含数量）")

    # ---- ⑤ `#71`（插队）：`check --controls` 的 ⑥-ext **行序确定**（与 seed 无关）----
    #   起因（按守卫维护纪律，不这么做会漏什么）：`_scan_configs_js` 迭代 `reg_types[t]["js"]`，而它是
    #     **`set`** ⇒ 同一节点 **≥2 个坏 `[js]` 键**时，`[FAIL]` 行的**顺序随 `PYTHONHASHSEED` 变**。
    #     CPython 默认开 str hash 随机化 ⇒ 同一命令跑两次都可能不同 ⇒ **破坏本仓「确定 / 可 diff」命门**
    #     （多处验收建立在逐字节比对之上）。修法 ＝ 迭代前 `sorted(...)`（一行）。
    #   判据（先红后绿）：同一输入、换 **≥5 个 `PYTHONHASHSEED`** 跑同一条 `check --controls`，
    #     **规范化后**输出必须**逐字节一致**。
    #     ⚠️ 「规范化」= 把 ⑥ 报错里的临时文件名 `xwl_ev_<随机>.js` 换成 `<TMP>`（`_TMP_EV_RE`）——
    #       该名由 `tempfile` 逐次随机、**与本条无关**。
    #       ⚠️ `#78` 后 ⑥-ext 报错正文已**不再含临时名**（改取真 `SyntaxError` 行）⇒ 该 `sub`
    #       现为 **no-op**（保留不删：防将来又引入随机名；届时它仍是必需的归一化）。
    #   触发面 narrow（如实记）：需"注册表**同类型**声明 ≥2 个 `js` 键"且"**同节点 ≥2 个都坏**"
    #     ⇒ 只声明 1 个 `js` 键时**复现不出来**（故夹具**必须** ≥2 个）。
    hash_fail: list[str] = []
    reg71 = os.path.join(tmp, "mini_controls_reg71.json")
    with open(reg71, "w", encoding="utf-8") as f:
        json.dump({"children": [
            {"id": "label71", "general": {"design": True},
             "configs": {"itemId": {"type": "string"},
                         "renderer": {"type": "js"}, "validator": {"type": "js"},
                         "formatter": {"type": "js"}, "handler": {"type": "js"}},
             "events": {}},
        ]}, f, ensure_ascii=False)
    _p71 = os.path.join(tmp, "reg71-multi.xwl")
    with open(_p71, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(
            {"title": "t", "roles": {}, "children": [
                {"configs": {"itemId": "l1",
                             "renderer": "function(){ return ; ;;(",
                             "validator": "function(){ return ; ;;(",
                             "formatter": "function(){ return ; ;;(",
                             "handler": "function(){ return ; ;;("},
                 "type": "label71", "expanded": False, "children": []}]},
            1, CRLF))
    if node is None:
        print("[note] ⑤ `#71` 行序确定：无 node ⇒ 跳过（⑥-ext 需真跑 node；`--only` 不自动找 node ⇒ 加 `--node`）")
        if REQUIRE_ALL:
            _mark_sub(_SUBCHECKS, "js.71", "未完成", "未找到 node，#71 JS 档未跑")
    else:
        _o71 = []
        for _sd in ("0", "1", "2", "3", "4"):
            _cc, _oo, _ee = _run_cli_env(
                ["check", "--node", node, "--controls", reg71, _p71],
                {"PYTHONHASHSEED": _sd})
            _o71.append(_TMP_EV_RE.sub("<TMP>", _oo))
        # 非空判据：夹具**必须**真产出 ≥2 条 ⑥-ext FAIL，否则本臂是"绿但空"。
        _nf71 = sum(1 for _l in _o71[0].splitlines() if "[FAIL] ⑥ configs." in _l)
        if _nf71 < 2:
            hash_fail.append("⑤ `#71` 前置失败：夹具应产出 ≥2 条 ⑥-ext FAIL，实得 %d 条：\n%s"
                             % (_nf71, _o71[0]))
        elif len(set(_o71)) != 1:
            hash_fail.append("⑤ `#71` ⑥-ext 行序随 `PYTHONHASHSEED` 变（应规范化后逐字节一致）：\n"
                             + "\n".join("  seed=%s:\n%s" % (i, o) for i, o in enumerate(_o71)))
        if hash_fail:
            failures.extend(hash_fail)
        else:
            print("[ok]  ⑤ `#71` ⑥-ext：同节点 ≥2 个坏 `[js]` 键时，换 5 个 `PYTHONHASHSEED` 输出规范化后逐字节一致")
        if REQUIRE_ALL:
            _mark_sub(_SUBCHECKS, "js.71", "通过", "#71 JS 档已执行")

@_cap
def _ng_contract_and_unit(tmp, node, failures, write) -> None:
    """⑬ `_OPS_AUTH` 五处清单一致／⑭ `_js_err_head` 单元级 —— **契约与单元面**。

    （从 `_check_new_guards` 原样搬出，判据一行未改。）
    """
    # ---- ⑬ `#77`：op 清单**逐处**都须对齐写死的权威清单 `_OPS_AUTH`（不只是「两侧互恰」）----
    #   起因（按守卫维护纪律，不这么做会漏什么）：`insertKey` 落地后 5 处 op 清单各自漂移；首版判据只比
    #     「epilog 计数 vs `--ops` help 清单」⇒ **两侧同改（都退成 4 个）仍绿**（互恰 ≠ 符实），
    #     且只覆盖第 1 处。现改为对**权威清单**（含顺序）逐处比对：
    #     ① `--ops` help 的清单；② epilog 的「<N> 种 op」计数；③ 3 份文档（`SKILL.md` 有 2 处）。
    _c5_fail: list[str] = []
    _CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    _repo = SKILL_ROOT   # 运行面文档（README/SKILL/references）在 SKILL_ROOT 下

    def _ops_lists(text):
        """抽「反引号包裹的 op 名、以 ` / ` 相连」的序列，只留含 `insertKey` 的（＝ op 清单）。"""
        out = []
        for _m in re.finditer(r"(?:`[A-Za-z]+`(?: / `[A-Za-z]+`)+)", text):
            _lst = re.findall(r"`([A-Za-z]+)`", _m.group(0))
            if "insertKey" in _lst:
                out.append(_lst)
        return out

    try:
        _pp = None
        for _a in xwl.build_parser()._actions:
            if getattr(_a, "choices", None) and "patch" in _a.choices:
                _pp = _a.choices["patch"]
                break
        _epi = (_pp.epilog or "") if _pp is not None else ""
        _oh = next(((_a.help or "") for _a in (_pp._actions if _pp is not None else [])
                    if _a.dest == "ops"), "")
        # ① `--ops` help（斜杠分隔、无引号）
        _ml = re.search(r"[A-Za-z]+(?:/[A-Za-z]+)+", _oh)
        _help_ops = _ml.group(0).split("/") if _ml else []
        if _help_ops != _OPS_AUTH:
            _c5_fail.append("⑬ `#77`「① `--ops` help」清单 %s != 权威 %s" % (_help_ops, _OPS_AUTH))
        # ② epilog 的「<N> 种 op」计数
        _mw = re.search(r"([一二三四五六七八九十]+)\s*种\s*op", _epi)
        _n_w = _CN.get(_mw.group(1)) if _mw else None
        if _n_w != len(_OPS_AUTH):
            _c5_fail.append("⑬ `#77`「② epilog」的「%s种 op」!= 权威长度 %d"
                            % (_mw.group(1) if _mw else "<缺计数词>", len(_OPS_AUTH)))
        # ③ 文档侧：每处清单都须 == 权威；处数下限＝**本仓实测**（`README.md` 1 处／`SKILL.md` **2 处**——「N 种 op（…）」示例 ＋ 「写 ops.json（…）」步骤／`references/sql-fragments.md` 1 处）。⚠️ 这 3 个数是**魔法数**：改本仓文档结构（如把 `SKILL.md` 两处合并成一处）时**必须同步这里**，否则 ⑬ 对合法合并会**假阳性**。
        for _rel, _min in (("README.md", 1), ("SKILL.md", 2), ("references/sql-fragments.md", 1)):
            _fp = os.path.join(_repo, _rel.replace("/", os.sep))
            _txt = io.open(_fp, encoding="utf-8", newline="").read()
            _ls = _ops_lists(_txt)
            if len(_ls) < _min:
                _c5_fail.append("⑬ `#77`「③ %s」op 清单处数 %d < %d" % (_rel, len(_ls), _min))
            for _lst in _ls:
                if _lst != _OPS_AUTH:
                    _c5_fail.append("⑬ `#77`「③ %s」op 清单 %s != 权威 %s" % (_rel, _lst, _OPS_AUTH))
    except Exception as _e:  # noqa: BLE001
        _c5_fail.append("⑬ `#77` 机械一致性检查自身出错：%r" % _e)
    if _c5_fail:
        failures.extend(_c5_fail)
    else:
        print("[ok]  ⑬ `#77`：`--ops` help ＋ epilog 计数 ＋ README／SKILL×2／sql-fragments 的 op 清单均 == 权威（%s）"
              % "/".join(_OPS_AUTH))

    # ---- ⑭ `#78`：`_js_err_head` 的**内部判据**（路径行 vs 真诊断）单元级 ----
    #   起因（按守卫维护纪律，不这么做会漏什么）：`p78` 的 `find` 锚的是**调用点**（`% (loc, _js_err_head(err))`）
    #     ⇒ 它只守「必须经 `_js_err_head`」；把函数**内部**第一臂退回「含 `Error`」（**路径**含 `Error`
    #     的行被误当诊断），`p78` **仍绿** ⇒ 防路径误判的核心价值无守卫。故补**单元级**断言。
    _j78_fail: list[str] = []
    for _in, _want, _why in (
        ("C:\\Error\\xwl_ev_ab.js:1\nSyntaxError: Unexpected token )\n    at x\n",
         "SyntaxError: Unexpected token )", "① 路径行**含 Error** 时须取真诊断、不得取路径"),
        ("C:\\Error\\xwl_ev_ab.js:1\n", "C:\\Error\\xwl_ev_ab.js:1",
         "② 反向臂：只有路径行（无真诊断）⇒ 按现实现返回该行（次臂「含 Error」）"),
        ("C:\\tmp\\xwl_ev_ab.js:1\n", "语法错误", "③ 无 Error 的路径行 ⇒ 退化为「语法错误」"),
        ("", "语法错误", "④ 空输入 ⇒ 「语法错误」"),
    ):
        _got = xwl._js_err_head(_in)
        if _got != _want:
            _j78_fail.append("⑭ `#78` %s：`_js_err_head(%r)` = %r（应 %r）" % (_why, _in, _got, _want))
    if _j78_fail:
        failures.extend(_j78_fail)
    else:
        print("[ok]  ⑭ `#78`：`_js_err_head` 单元级 —— 路径含 Error 时取真诊断、无诊断／空输入退化正确")

@_cap
def _ng_write_overwrite(tmp, node, failures, write) -> None:
    """⑥ `#72`：`patch` 覆盖**已存在的容器键**且新值是标量 ⇒ 必须打 `[warn]`（rc 不变）。

    （从 `_check_new_guards` 原样搬出，判据一行未改。）
    """
    # ---- ⑥ `#72`（插队）：`patch` 覆盖**已存在的容器键**（dict/list）且新值是标量 ⇒ 必须可见 ----
    #   起因（按守卫维护纪律）：`set`/`insertKey` 的 path 末段命中一个**已存在的容器键**（`configs`／`children`）
    #     且新值为**标量**时，现行为是**静默把整个容器替换成标量** ⇒ **结构损坏**，却 rc=0、无任何 `[warn]`
    #     （两组独立复测发现、lead 已复现）。修法 ＝ 该 op **打一条 `[warn]`**（⛔ **不改默认拒绝语义** ——
    #     "覆盖已存在的键"不是"新建键"，既有 `create`／`--allow-new-key` 闸门一律不碰）。
    #   判据（先红后绿）：覆盖容器键的 op ⇒ 输出**必须含 `[warn]`**、rc **仍 0**；而"标量→标量"的普通改键
    #     ⇒ **不得**出现该 `[warn]`（默认面其余行为逐字节不变）。夹具取自 `dumps_designer` 的**规范多行**形态
    #     ⇒ 不会混入"紧凑单行"那条与 `#72` 无关的 `[warn]`。
    ov_fail: list[str] = []
    _ov_base = xwl.dumps_designer(
        {"title": "t", "roles": {}, "children": [
            {"configs": {"itemId": "st1", "url": "m?xwl=sub/sel"}, "type": "store",
             "expanded": False, "children": []}]}, 1, CRLF)

    def _patch72(tag, op):
        """写一份**新鲜**夹具（cmd_patch 会改文件）＋ ops，跑 `--dry-run`，返回 `(rc, out)`。"""
        _p = os.path.join(tmp, "reg72_%s.xwl" % tag)
        with open(_p, "w", encoding="utf-8", newline="") as f:
            f.write(_ov_base)
        _ops = os.path.join(tmp, "reg72_ops_%s.json" % tag)
        with open(_ops, "w", encoding="utf-8") as fh:
            json.dump([op], fh, ensure_ascii=False)
        return _run(xwl.cmd_patch, file=_p, ops=_ops, indent=1, eol="auto",
                    dry_run=True, backup=False, node=None, no_js=True, allow_new_key=False)

    # A/B/C = 三种"容器 → 标量"覆盖（set 打 dict、set 打 list、insertKey 打 dict）：都须 `[warn]` 且 rc 0。
    for _tag, _op in (
        ("set_dict", {"op": "set", "path": ["children", 0, "configs"], "value": "1"}),
        ("set_list", {"op": "set", "path": ["children", 0, "children"], "value": "x"}),
        ("inkey_dict", {"op": "insertKey", "path": ["children", 0, "configs"], "value": "1"}),
    ):
        _rc, _o = _patch72(_tag, _op)
        if _rc != 0:
            ov_fail.append("⑥ `#72` %s：覆盖容器键后 rc=%s（应 0 —— 只加信号、不改默认语义）\n%s"
                           % (_tag, _rc, _o))
        if "[warn]" not in _o:
            ov_fail.append("⑥ `#72` %s：覆盖容器键**无 `[warn]`**（静默数据损坏）\n%s" % (_tag, _o))
    # D = 反面：标量 → 标量（普通改键）⇒ **不得**出现该 `[warn]`（默认面其余行为不变）。
    _rc, _o = _patch72("scalar", {"op": "set", "path": ["children", 0, "configs", "url"], "value": "u2"})
    if _rc != 0:
        ov_fail.append("⑥ `#72` scalar：普通改键 rc=%s（应 0）\n%s" % (_rc, _o))
    if "[warn]" in _o:
        ov_fail.append("⑥ `#72` scalar：普通的『标量→标量』改键**误报 `[warn]`**（应静默）\n%s" % _o)
    # E = 反面（质询 O7）：**容器 → 容器**（dict→dict）⇒ **不得**出现 `[warn]`（防"过度报警"）。
    _rc, _o = _patch72("cont2cont", {"op": "set", "path": ["children", 0, "configs"], "value": {"url": "u3"}})
    if _rc != 0:
        ov_fail.append("⑥ `#72` cont2cont：容器→容器 rc=%s（应 0）\n%s" % (_rc, _o))
    if "[warn]" in _o:
        ov_fail.append("⑥ `#72` cont2cont：『容器→容器』改键**误报 `[warn]`**"
                       "（应静默 —— 过度报警不被挡）\n%s" % _o)
    # F = 正面（本批补的 list 分支）：**list 分支**下标命中已存在的容器元素、新值为标量 ⇒ 须 `[warn]`
    #   （list 分支若漏收 `overwrites` ⇒ `#72` 只修了一半）。
    _rc, _o = _patch72("list_idx", {"op": "set", "path": ["children", 0], "value": "z"})
    if _rc != 0:
        ov_fail.append("⑥ `#72` list_idx：数组元素覆盖 rc=%s（应 0）\n%s" % (_rc, _o))
    if "[warn]" not in _o:
        ov_fail.append("⑥ `#72` list_idx：**list 分支**下标命中容器元素、新值为标量**无 `[warn]`**"
                       "（A1：#72 list 分支漏收 ⇒ 结构损坏静默）\n%s" % _o)
    if ov_fail:
        failures.extend(ov_fail)
    else:
        print("[ok]  ⑥ `#72` 覆盖容器键（dict/list/insertKey 三形态）⇒ `[warn]` 可见且 rc 仍 0；"
              "标量→标量 与 容器→容器改键均静默")

@_cap
def _ng_params_defaults(tmp, node, failures, write) -> None:
    """⑦–⑫ —— `params` 的剥注释／文案分句／`--upstream` 目标参数化／`--strict` 悬空（默认面 ＋ 开关面）。

    （从 `_check_new_guards` 原样搬出，判据一行未改。）
    """
    # ---- ⑦ `#50`（本段序 1）：`params` 需求侧提取 `{?名?}` **前剥注释**（与来源侧同口径）----
    #   起因（按守卫维护纪律）：需求侧（`module.serverScript` ＋ `dataprovider.sql/totalSql`）提取 `{?名?}` 时**不剥注释**
    #     ⇒ 注释里的占位符也计入 ⇒ **假阳性**（来源侧已剥、需求侧未剥 ⇒ 同工具内两套口径）。
    #   判据（先红后绿）：JS 注释（`//`）与 SQL 行注释（`--`）里的 `{?名?}` **不计入**；代码里的**仍计入**；
    #     且 SQL 串里 `'http://…'` 的 `//` **不被误切**（本段要求的前置正例）。
    p50_fail: list[str] = []
    _r50 = os.path.join(tmp, "pm_p50")
    _car50 = xwl.skeleton_sql("p50carrier")
    _mod50 = _car50["children"][0]
    _mod50["configs"]["serverScript"] = ("// {?ghost?} 这是注释\n"
                                         "function f(){ return '{?real?}'; }")
    _mod50["children"][0]["configs"]["sql"] = (
        "select u from t where u='http://h/x' and a={?real2?} -- {?ghost2?}\n"
        "/* {?blk?} */ and b=1 # {?hsh?}\n"
        "and d={#cols#} and e={?real4?}\n"
        "and c={?real3?}")
    _dump(_car50, os.path.join(_r50, "sub", "sel.xwl"))
    _p50 = os.path.join(_r50, "p50.xwl")
    _dump({"title": "p50", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st50", "m?xwl=sub/sel")]}]}, _p50)
    _rc50, _o50 = _run(xwl.cmd_params, file=_p50, module_root=_r50, controls=None,
                       list_fields=False, upstream=False)
    if _rc50 != 0:
        p50_fail.append("⑦ `#50`：params rc=%s（应 0）\n%s" % (_rc50, _o50))
    if "ghost" in _o50:
        p50_fail.append("⑦ `#50`：注释里的 `{?名?}` 仍被计入（需求侧未剥注释 ⇒ 假阳性）\n%s" % _o50)
    if "real" not in _o50:
        p50_fail.append("⑦ `#50`：代码里的 `{?名?}` 被误删（应保留）\n%s" % _o50)
    # `#50`（Q1/Q2/O2）：SQL **块注释** `/* … */` 也要剥 —— ⑦ 只测 `--` 行注释 ⇒ 块注释防线是空的
    #   （注入"块注释不剥" ⑦ 仍绿）。本条把该臂钉死。
    if "blk" in _o50:
        p50_fail.append("⑦ `#50`：SQL **块注释** `/* … */` 里的 `{?名?}` 仍被计入"
                        "（`strip_sql_comments` 未剥块注释 ⇒ 假阳性）\n%s" % _o50)
    # `#50`（P3）：SQL **`#` 行注释**（MySQL）也要剥 —— 不剥 `#` ⇒ 被注释掉的引用计入 ⇒ 假阳性。
    if "hsh" in _o50:
        p50_fail.append("⑦ `#50`：SQL **`#` 行注释**（MySQL）里的 `{?名?}` 仍被计入"
                        "（未剥 `#` ⇒ 假阳性）\n%s" % _o50)
    if "real3" not in _o50:
        p50_fail.append("⑦ `#50`：`/* */` / `#` 之后的代码里 `{?real3?}` 被误删（应保留）\n%s" % _o50)
    # `#83`：平台 SQL 的 `{#…#}` 是**模板定界符**（不是注释）—— **同行** `{#…#}` 之后紧跟的
    #   `{?名?}` **必须仍被识别**。⛔ 旧剥离器把 `#` 无条件当行注释 ⇒ 吞掉同行其后的 `{?名?}`
    #   ⇒ 假阴性（⑦ 原夹具把 `# {?hsh?}` 放**行尾**、`{?real3?}` 放**下一行** ⇒ 恰好绕开该形态）。
    if "real4" not in _o50:
        p50_fail.append("⑦ `#83`：**同行** `{#…#}` 之后的 `{?real4?}` 被吞"
                        "（`{#…#}` 是模板定界符、非注释）\n%s" % _o50)
    if p50_fail:
        failures.extend(p50_fail)
    else:
        print("[ok]  ⑦ `#50` 需求侧剥注释：`//` / `--` / `#` / `/* */` 注释里的 `{?名?}` 不计、"
              "代码里的仍计；`'http://…'` 的 `//` 不误切")

    # ---- ⑧ `#58`（本段序 2）：`params` 「0 个 store」与「有 store 但 SQL 侧无参」**分两句文案** ----
    #   起因（按守卫维护纪律）：两种**不同处境**（页面压根没有 store ／ 有 store 但 SQL 侧无 `{?名?}`）共用**同一句**
    #     `（SQL 侧没有 {?…?} / app.get，跳过交叉核对）` ⇒ 易读成"已核对完成"。⚠️ **落点核对已做**：该行在
    #     `if not needed:` 分支、**不给任何 flag 即达** ⇒ 属**默认面输出变更** ⇒ 已列入本段声明的
    #     **默认面变更清单**。
    #   判据（先红后绿）：0 store 与 有 store 两句**必须不同**；0 store 那半须含「未发现 store」。
    p58_fail: list[str] = []
    _r58 = os.path.join(tmp, "pm_p58")
    _dump(xwl.skeleton_sql("c58"), os.path.join(_r58, "sub", "sel58.xwl"))
    _pa58 = os.path.join(_r58, "p58a.xwl")
    _dump({"title": "p58a", "children": []}, _pa58)                       # 0 个 store
    _pb58 = os.path.join(_r58, "p58b.xwl")
    _dump({"title": "p58b", "children": [                                 # 1 个 store（载体无 {?名?}）
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st58", "m?xwl=sub/sel58")]}]}, _pb58)
    _rca58, _oa58 = _run(xwl.cmd_params, file=_pa58, module_root=_r58, controls=None,
                         list_fields=False, upstream=False)
    _rcb58, _ob58 = _run(xwl.cmd_params, file=_pb58, module_root=_r58, controls=None,
                         list_fields=False, upstream=False)
    _la58 = [ln for ln in _oa58.splitlines() if "跳过交叉核对" in ln]
    _lb58 = [ln for ln in _ob58.splitlines() if "跳过交叉核对" in ln]
    if _rca58 != 0 or _rcb58 != 0:
        p58_fail.append("⑧ `#58`：rc 应为 0/0，实得 %s/%s" % (_rca58, _rcb58))
    if len(_la58) != 1 or len(_lb58) != 1:
        p58_fail.append("⑧ `#58`：应各恰一行「跳过交叉核对」，0 store 得 %d、有 store 得 %d"
                        % (len(_la58), len(_lb58)))
    elif _la58 == _lb58:
        p58_fail.append("⑧ `#58`：0 store 与 有 store（SQL 侧无参）**共用同一句**（应拆两句）\n"
                        "  0 store: %s\n  有 store: %s" % (_la58[0], _lb58[0]))
    if "未发现 store" not in _oa58:
        p58_fail.append("⑧ `#58`：0 store 时未给「未发现 store」文案\n%s" % _oa58)
    # `#58`/O6（与 ⑩ 同族）：0-store 的「跳过」行既要有「未发现 store」、也要带 `[warn] ` 前缀。
    if not _la58 or "[warn]" not in _la58[0]:
        p58_fail.append("⑧ `#58`：0-store 的「跳过」行未带 `[warn] ` 前缀（可见性信号缺失）：%s" % _la58)
    if p58_fail:
        failures.extend(p58_fail)
    else:
        print("[ok]  ⑧ `#58`：0 store 与「有 store 但 SQL 侧无参」**分两句**"
              "（前者含「未发现 store」且带 `[warn] ` 前缀）")

    # ---- ⑨ `#56`（本段序 3）：同载体多 store ⇒ 合并同段输出 ＋ **保留引用计数**（⛔ 不裸去重）----
    #   起因（按守卫维护纪律）：`sql_files` 由 store 循环逐个 append ⇒ **同一载体被多 store 引用**时，
    #     下游「`=== SQL 侧: xxx.xwl ===`」段重复打印同一段 N 次（噪音）。本段要求的口径：
    #     **合并 ＋ 保留引用计数**（`（同载体 ×N）`），⛔ **不裸去重** —— 裸去重会把"被 N 处引用"
    #     这个信号一并删掉。⚠️ 落默认面 ⇒ 已列入本段声明的**默认面变更清单**（行数会变）。
    #   判据（先红后绿）：3 store 指向同一载体 ⇒ 「SQL 侧」段**只出现 1 次**且**含 `×3`**。
    p56_fail: list[str] = []
    _r56 = os.path.join(tmp, "pm_p56")
    _car56 = xwl.skeleton_sql("c56")
    _car56["children"][0]["children"][0]["configs"]["sql"] = "select 1 where a={?p?}"
    _dump(_car56, os.path.join(_r56, "sub", "sel56.xwl"))
    _p56 = os.path.join(_r56, "p56.xwl")
    _dump({"title": "p56", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("stA", "m?xwl=sub/sel56"), _store("stB", "m?xwl=sub/sel56"),
                      _store("stC", "m?xwl=sub/sel56")]}]}, _p56)
    _rc56, _o56 = _run(xwl.cmd_params, file=_p56, module_root=_r56, controls=None,
                       list_fields=False, upstream=False)
    _h56 = [ln for ln in _o56.splitlines() if "=== SQL 侧:" in ln]
    if _rc56 != 0:
        p56_fail.append("⑨ `#56`：rc=%s（应 0）" % _rc56)
    if len(_h56) != 1:
        p56_fail.append("⑨ `#56`：同载体（3 store）的「SQL 侧」段应合并为 1 次，实得 %d 次\n%s"
                        % (len(_h56), _o56))
    if _h56 and "×3" not in _h56[0]:
        p56_fail.append("⑨ `#56`：合并后未保留引用计数（应含「同载体 ×3」）：%s" % _h56[0])
    if p56_fail:
        failures.extend(p56_fail)
    else:
        print("[ok]  ⑨ `#56`：同载体多 store ⇒ 「SQL 侧」段**合并为 1 次**并**保留引用计数**（同载体 ×3）")

    # ---- ⑩ `#51`（本段序 4）：`params`「跳过交叉核对」默认面目带 `[warn] ` 前缀 ＋ `--upstream` 不扰动 off-mode ----
    #   起因（按守卫维护纪律）：该行原**无级别前缀** ⇒ 与"已核对完成"肉眼难分（与 `#58` 同族）；且它是 `M5`
    #     「静默跳过」的读数点（`M5` 跑**默认面**、首分支就判 `"[warn]" in out`）。本条**无条件**把
    #     `[warn] ` 前置到「跳过交叉核对」那两句上；⚠️ `rc` **不变**（该分支恒 `return 0`）。
    #   判据（先红后绿）：
    #     ① 有 store、SQL 侧无参页的**默认面**输出，该行**含 `[warn] `**（`rc` 仍 0）；
    #     ② 同页**开 / 不开 `--upstream`**，那行「跳过」文字**逐字一致**（不变式：`--upstream` 是纯加法，
    #        不得改变 off-mode 输出）。
    #   夹具：复用 ⑧ 的形态（1 store → 载体无 `{?名?}`）。
    p51_fail: list[str] = []
    _r51 = os.path.join(tmp, "pm_p51")
    _dump(xwl.skeleton_sql("c51"), os.path.join(_r51, "sub", "sel51.xwl"))
    _p51b = os.path.join(_r51, "p51b.xwl")
    _dump({"title": "p51b", "children": [                                 # 1 个 store（载体无 {?名?}）
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st51", "m?xwl=sub/sel51")]}]}, _p51b)
    _rc_a51, _o_a51 = _run(xwl.cmd_params, file=_p51b, module_root=_r51, controls=None,
                           list_fields=False, upstream=False)          # 默认面（off-mode）
    _rc_b51, _o_b51 = _run(xwl.cmd_params, file=_p51b, module_root=_r51, controls=None,
                           list_fields=False, upstream=True)           # 开 --upstream
    _sa51 = [ln for ln in _o_a51.splitlines() if "跳过交叉核对" in ln]
    _sb51 = [ln for ln in _o_b51.splitlines() if "跳过交叉核对" in ln]
    if _rc_a51 != 0:
        p51_fail.append("⑩ `#51`：默认面 rc=%s（应 0）" % _rc_a51)
    if len(_sa51) != 1 or "[warn]" not in _sa51[0]:
        p51_fail.append("⑩ `#51`：默认面「跳过」行未带 `[warn] `：%s" % _sa51)
    if _sa51 != _sb51:
        p51_fail.append("⑩ `#51`：`--upstream` 扰动了 off-mode 的「跳过」行：\n  关:%s\n  开:%s"
                        % (_sa51, _sb51))
    # `#51`/O6：**0-store 行**（`未发现 store`）也要带 `[warn] ` 前缀（⑩ 只测 1-store 行）。
    _r51z = os.path.join(tmp, "pm_p51z")
    _p51z = os.path.join(_r51z, "p51z.xwl")
    _dump({"title": "p51z", "children": [                                 # 0 个 store
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": []}]}, _p51z)
    _rc_z51, _o_z51 = _run(xwl.cmd_params, file=_p51z, module_root=_r51z, controls=None,
                           list_fields=False, upstream=False)
    _sz51 = [ln for ln in _o_z51.splitlines() if "跳过交叉核对" in ln]
    if _rc_z51 != 0:
        p51_fail.append("⑩ `#51`：0-store 页 rc=%s（应 0）" % _rc_z51)
    if len(_sz51) != 1 or "[warn]" not in _sz51[0] or "未发现 store" not in _sz51[0]:
        p51_fail.append("⑩ `#51`：0-store 页「跳过」行未带 `[warn] ` 或未用「未发现 store」文案：%s" % _sz51)
    if p51_fail:
        failures.extend(p51_fail)
    else:
        print("[ok]  ⑩ `#51`：「跳过」行默认面带 `[warn] `（1-store 与 0-store 两行都测）、rc 仍 0；"
              "`--upstream` 不扰动该行")

    # ---- ⑪ `#53`（本段序 5）：`params --upstream` 目标键**参数化** ⇒ 目标为 **SQL 载体** 时文案分场景 ----
    #   起因（按守卫维护纪律）：`_scan_upstream` 只反查"谁调用本页"，**载体**被谁引用**无反向引用能力**
    #     ⇒ 孤儿载体静默（`check` / `sqlrefs` 均无根，故落 `params --upstream`）。本条把目标键参数化
    #     （默认 ＝ 本文件键）：目标为 **页面**时输出**逐字节不变**（承重墙），目标为 **载体**时给
    #     "引用本载体的页面"。⛔ 不新增 CLI 参数。
    #   判据（先红后绿）：① 载体目标 ⇒ 段头含「引用本载体的页面」且**列出引用方文件**；
    #     ② 页面目标 ⇒ 段头仍「外部可传入」、**不含**「引用本载体」（文案分场景）。
    p53_fail: list[str] = []
    _r53 = os.path.join(tmp, "pm_p53")
    _dump(xwl.skeleton_sql("c53"), os.path.join(_r53, "sub", "sel53.xwl"))   # 载体（module→dataprovider）
    _p53page = os.path.join(_r53, "p53.xwl")
    _dump({"title": "p53", "children": [                                    # 引用该载体的页面
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st53", "m?xwl=sub/sel53")]}]}, _p53page)
    _rc53c, _o53c = _run(xwl.cmd_params, file=os.path.join(_r53, "sub", "sel53.xwl"),
                         module_root=_r53, controls=None, list_fields=False, upstream=True)
    _rc53p, _o53p = _run(xwl.cmd_params, file=_p53page, module_root=_r53, controls=None,
                         list_fields=False, upstream=True)
    if _rc53c != 0 or _rc53p != 0:
        p53_fail.append("⑪ `#53`：rc 应为 0/0，实得 %s/%s" % (_rc53c, _rc53p))
    if "引用本载体的页面" not in _o53c:
        p53_fail.append("⑪ `#53`：载体目标的 `--upstream` 未给「引用本载体的页面」段\n%s" % _o53c)
    if "p53.xwl" not in _o53c:
        p53_fail.append("⑪ `#53`：载体目标未列出引用方页面（p53.xwl）\n%s" % _o53c)
    if "引用本载体" in _o53p:
        p53_fail.append("⑪ `#53`：页面目标误用了载体文案（应「外部可传入」）\n%s" % _o53p)
    if "外部可传入" not in _o53p:
        p53_fail.append("⑪ `#53`：页面目标的 `--upstream` 丢了既有「外部可传入」段\n%s" % _o53p)
    if p53_fail:
        failures.extend(p53_fail)
    else:
        print("[ok]  ⑪ `#53`：`--upstream` 目标为**载体** ⇒ 「引用本载体的页面」并列出引用方；"
              "目标为**页面** ⇒ 仍「外部可传入」（文案分场景）")

    # ---- ⑫ `#36`（本段序 4）：`params --strict` 下「真·悬空」取数 url **判失败（rc=1）**；显式占位只 `[note]` ----
    #   起因（按守卫维护纪律）：`params` 对「取数 url 指向的文件不存在」不给信号（加 `--strict` 仍 rc=0）⇒ 与
    #     「SQL 缺来源判 rc=1」判据不对称。⭐ **本段"翻脸"**：真·悬空 ⇒ `--strict` 下**单列为失败项**；
    #     显式占位（`<…>` / `…` / `__MODULE__`）识别为**有意待定** ⇒ **永不判红**（否则批量页面对占位写法即大规模误判）。
    #   ⭐ **两条出口都要承载**：末行判定 ＋ **早返出口**（"悬空-only"页走的正是早返）——
    #     下面 ①（`p36dang`，悬空-only ⇒ 早返）与 ④（`p36final`，有 needed ⇒ 末行）**各钉一条**，⛔ 缺一即漏。
    #   判据（先红后绿）：① 悬空页 `--strict` ⇒ 含 `[warn]` ＋ `#36`、`rc` **＝ 1**；
    #     ② 占位页 `--strict` ⇒ 含 `[note]` ＋ `#36`、**无** `#36` 的 `[warn]`、`rc` 仍 0；
    #     ③ 悬空页**不给** `--strict` ⇒ **无** `#36` 行 ＋ `rc` **仍 0**（**默认面不动**）；
    #     ④ 有 needed ＋ 悬空（走末行）⇒ `[warn]` ＋ `rc` **＝ 1**。
    p36_fail: list[str] = []
    _r36 = os.path.join(tmp, "pm_p36")
    _p36d = os.path.join(_r36, "p36dang.xwl")
    _dump({"title": "p36dang", "children": [                               # 悬空（载体不存在）
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st36d", "m?xwl=sub/nope36")]}]}, _p36d)
    _p36p = os.path.join(_r36, "p36ph.xwl")
    _dump({"title": "p36ph", "children": [                                 # 显式占位
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st36p", "m?xwl=<待定>/querySql")]}]}, _p36p)
    _rc36d, _o36d = _run(xwl.cmd_params, file=_p36d, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=True)
    _rc36p, _o36p = _run(xwl.cmd_params, file=_p36p, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=True)
    _rc36n, _o36n = _run(xwl.cmd_params, file=_p36d, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=False)
    if _rc36d != 1:
        p36_fail.append("⑫ `#36`：悬空页 `--strict` rc=%s（应 1：真·悬空按 `--strict` 判失败）" % _rc36d)
    if not any(l.strip().startswith("[warn]") and "#36" in l for l in _o36d.splitlines()):
        p36_fail.append("⑫ `#36`：悬空页 `--strict` 未打 `[warn]`（`#36` 失败信号）\n%s" % _o36d)
    if _rc36p != 0:
        p36_fail.append("⑫ `#36`：占位页 `--strict` rc=%s（应 0）" % _rc36p)
    if not any(l.strip().startswith("[note]") and "#36" in l for l in _o36p.splitlines()):
        p36_fail.append("⑫ `#36`：占位页 `--strict` 未打 `[note]`（豁免未生效）\n%s" % _o36p)
    if any(l.strip().startswith("[warn]") and "#36" in l for l in _o36p.splitlines()):
        p36_fail.append("⑫ `#36`：显式占位被误判红（应只 `[note]`）\n%s" % _o36p)
    if "#36" in _o36n:
        p36_fail.append("⑫ `#36`：不给 `--strict` 时仍出现 `#36` 行（默认面被动）\n%s" % _o36n)
    if _rc36n != 0:
        p36_fail.append("⑫ `#36`：悬空页**不给 `--strict`** 时 rc=%s（应 0 —— 翻脸只发生在 `--strict` 下，"
                        "**默认面必须不动**）" % _rc36n)
    # `#36`/O3：**最终返回路径**（有 `needed` ⇒ 不走早返分支）也要打 `[warn]` 预告 —— ⑫ 只走早返
    #   ⇒ 撤最终路径那处 `_emit_36` 无人报红（盲点）。夹具须让 SQL 侧有 `{?名?}`（needed 非空 ⇒ 走最终返回）。
    _p36f = os.path.join(_r36, "p36final.xwl")
    _car36 = xwl.skeleton_sql("c36final")
    _car36["children"][0]["children"][0]["configs"]["sql"] = "select a from t where a={?x?}"
    _dump(_car36, os.path.join(_r36, "sub", "sel36.xwl"))
    _dump({"title": "p36final", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         # ⭐ 末行出口的判据必须**只由 dangling 决定** ⇒ 该 store 用**字符串**形态的 `params`
         #   （`xwl.py:5666`：只认字符串）把 SQL 侧的 `x` **给出来** ⇒ `miss` 为空。
         #   ⛔ 不给来源的话 `miss` 也会把 rc 顶到 1，那样"取消 dangling 判定"**测不出来**。
         "children": [{"configs": {"itemId": "st36v", "url": "m?xwl=sub/sel36",
                                   "params": "{x: 1}"},
                       "type": "store", "expanded": False, "children": []},
                      _store("st36f", "m?xwl=sub/nope36")]}]}, _p36f)   # 悬空
    _rc36f, _o36f = _run(xwl.cmd_params, file=_p36f, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=True)
    if not any(l.strip().startswith("[warn]") and "#36" in l for l in _o36f.splitlines()):
        p36_fail.append("⑫ `#36`：**最终返回路径**（有 needed）未打 `[warn]`"
                        "（撤最终路径那处 `_emit_36` 无人报红 ⇒ 盲点）\n%s" % _o36f)
    if _rc36f != 1:
        p36_fail.append("⑫ `#36`：**最终返回路径**（有 needed ＋ 悬空）`--strict` rc=%s"
                        "（应 1 —— 末行判定必须把 `dangling36` 一并计入）" % _rc36f)
    # `#36`/O4：`common/` **框架端点**豁免 ⇒ 不打任何 `#36` 行（改成判 dangling 则本条红）。
    _p36c = os.path.join(_r36, "p36common.xwl")
    _dump({"title": "p36common", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st36c", "m?xwl=common/nope36")]}]}, _p36c)
    _rc36c, _o36c = _run(xwl.cmd_params, file=_p36c, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=True)
    if "#36" in _o36c:
        p36_fail.append("⑫ `#36`：`common/` 框架端点**未被豁免**（不该出任何 `#36` 行）\n%s" % _o36c)
    # `#36`/`__MODULE__` **三态覆盖**（本块补齐：`__MODULE__` 在本块**零覆盖** —— 占位 / 真悬空 /
    #   真存在三态一条断言都没有 ⇒ 把 `_mod36_state` 改坏也没人报红）。
    #   ⭐ 起因（先红后绿）：`__MODULE__/<abc>` 原走 `resolved` ⇒ Windows 下 `<`/`>` 是**非法文件名字符**
    #     ⇒ `os.path.exists` 恒 `False` ⇒ 必进 `dangling36` ⇒ `--strict` 把"有意待定"**确定性判红**；
    #     而 `<abc>` 按 `_ref_kind36` 的语义本该永不判红 ⇒ 判据在"两段判"处漏了"**段内占位**"这一面。
    #   ① 纯函数直接判 `_mod36_state`（⛔ 不跑子进程、不依赖现网语料）：占位 / 真悬空 / 真存在三态；
    #   ② 端到端两条：占位页 `--strict` ⇒ `rc=0` ＋ `[note]`（⛔ 无 `#36` 的 `[warn]`）；
    #      **反向对照**（⛔ 不能省，否则等于用"放宽占位"换掉"真悬空"）：真悬空页 `--strict` ⇒ 仍 `rc=1`。
    _p36mod = os.path.join(_r36, "p36mod.xwl")
    _dump({"title": "p36mod", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st36m", "m?xwl=__MODULE__/<abc>")]}]}, _p36mod)
    _p36modx = os.path.join(_r36, "p36modx.xwl")
    _dump({"title": "p36modx", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st36x", "m?xwl=__MODULE__/missing")]}]}, _p36modx)
    _dump({"title": "here", "children": []}, os.path.join(_r36, "here.xwl"))   # ③ 的"真存在"靶
    # ① 纯函数三态：`(state, fp, why)` —— **why 的关键字**才是判据（`unresolved` 另有别的原因，
    #   只看状态会把"没给根 / 根不像根"误当成"占位放过"）。
    _s36a = xwl._mod36_state(_r36, _p36mod, "__MODULE__/<abc>", "ok")
    if _s36a[0] != "unresolved" or _s36a[1] is not None or "显式占位" not in (_s36a[2] or ""):
        p36_fail.append("⑫ `#36`：`__MODULE__/<abc>` 应**按显式占位放过**"
                        "（`unresolved` ＋ `fp is None` ＋ why 含「显式占位」），实得 %r" % (_s36a,))
    _s36b = xwl._mod36_state(_r36, _p36mod, "__MODULE__/missing", "ok")
    if _s36b[0] != "resolved" or not _s36b[1] or os.path.exists(_s36b[1]):
        p36_fail.append("⑫ `#36`：`__MODULE__/missing` 应**仍判真悬空**（`resolved` ＋ 指向不存在的文件），"
                        "实得 %r" % (_s36b,))
    _s36c = xwl._mod36_state(_r36, _p36mod, "__MODULE__/here", "ok")
    if _s36c[0] != "resolved" or not _s36c[1] or not os.path.exists(_s36c[1]):
        p36_fail.append("⑫ `#36`：`__MODULE__/here`（文件真存在）应 `resolved` ＋ `exists`，实得 %r" % (_s36c,))
    # ② 端到端：占位页 `--strict` ⇒ rc=0、只有 `[note]`；反向对照真悬空页 ⇒ rc 仍 1 ＋ `[warn]`。
    _rc36m, _o36m = _run(xwl.cmd_params, file=_p36mod, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=True)
    if _rc36m != 0:
        p36_fail.append("⑫ `#36`：`__MODULE__/<abc>`（显式占位）`--strict` rc=%s（应 0 —— "
                        "占位不该被 `dangling36` 判红）\n%s" % (_rc36m, _o36m))
    if not any(l.strip().startswith("[note]") and "#36" in l for l in _o36m.splitlines()):
        p36_fail.append("⑫ `#36`：`__MODULE__/<abc>` 未打 `[note]`（占位未交代）\n%s" % _o36m)
    if any(l.strip().startswith("[warn]") and "#36" in l for l in _o36m.splitlines()):
        p36_fail.append("⑫ `#36`：`__MODULE__/<abc>` 被误判成**真悬空**（应只 `[note]`）\n%s" % _o36m)
    _rc36x, _o36x = _run(xwl.cmd_params, file=_p36modx, module_root=_r36, controls=None,
                         list_fields=False, upstream=False, strict=True)
    if _rc36x != 1:
        p36_fail.append("⑫ `#36`：`__MODULE__/missing`（真悬空）`--strict` rc=%s（应 1 —— "
                        "反向对照：放宽占位不得连真悬空一起放过）\n%s" % (_rc36x, _o36x))
    if not any(l.strip().startswith("[warn]") and "#36" in l for l in _o36x.splitlines()):
        p36_fail.append("⑫ `#36`：`__MODULE__/missing` 未打 `[warn]`（真悬空未判）\n%s" % _o36x)
    if p36_fail:
        failures.extend(p36_fail)
    else:
        print("[ok]  ⑫ `#36`：`--strict` 下真·悬空取数 url ⇒ `[warn]` ＋ **rc=1**"
              "（⭐ **早返 ＋ 末行两出口都承载**）；显式占位 ⇒ 只 `[note]`、rc 仍 0；"
              "`common/` 端点 ⇒ 不出 `#36`；不给 `--strict` ⇒ 无 `#36` 行、**rc 仍 0（默认面不动）**；"
              "`__MODULE__` 三态 ⇒ 段内占位按占位 `[note]`（rc 0）／真悬空仍 `[warn]`（rc 1）／真存在 `resolved`")

@_cap
def _ng_platform(tmp, node, failures, write) -> None:
    """⑮ `#75` 模块根／⑯ `#74` 坏 `--controls`／⑰ `#80` 分组名 —— **平台面**（⑮ 的夹具被⑯⑰ 复用）。

    （从 `_check_new_guards` 原样搬出，判据一行未改。）
    """
    # ---- ⑮ `#75`（本段序）：模块根「**存在但不像模块根**」⇒ store 支 / direct 支**两站点**都改「未核对」----
    #   起因（按守卫维护纪律）：`--module-root` 误指向（如 webapp 根而非 `…/wb/modules`）时，`#75` 判据随**目录规模**
    #     变（实测：1 文件 ⇒ `suspect`；400 文件 ⇒ `suspect`；放 1 个 `.xwl` ⇒ 翻 `ok`）—— 若仍按
    #     `os.path.exists` 判 ⇒ 会**谎报「未找到」**（那是"载体悬空"的意思、`--strict` 下还冤枉判红）。
    #   ⭐ **两站点各一条**：store 支（`xwl.py:5563`）与 direct 支（`xwl.py:5612`）**独立** ⇒ 缺一即漏（故两处都造）。
    #   判据（先红后绿）：① 坏 root（非 `modules` 名、且**零 `.xwl`**）⇒ 两站点都出「未核对」＋原因；
    #     ② 正确 `modules` 根 ⇒ 两处**均无**「未核对」（防「永远未核对」）。
    #   ⚠️ 用 `_run` **直调**（实测 +0.02s；走 `_run_cli` 会 +1.0s 子进程启动）；本块不验异常隔离 ⇒ 直调可。
    p75_fail: list[str] = []
    _r75 = os.path.join(tmp, "pm_p75")
    _r75bad = os.path.join(_r75, "notmodules")      # 非 `modules` 名
    _r75ok = os.path.join(_r75, "modules")          # 正确模块根（判据直接认名）
    os.makedirs(_r75bad, exist_ok=True)
    os.makedirs(_r75ok, exist_ok=True)
    # ⭐ **规模自检（必须有）**：本守卫的判据随目录规模翻转 ⇒ 夹具**自带不变式** ——
    #   坏 root 下必须是**零 `.xwl`**（哪怕只塞进 1 个 `.xwl`，`_module_root_state` 就翻 `ok`、
    #   两站点断言全部落空却仍"绿"）⇒ 先断言该不变式、再谈行为断言。
    _x75 = [_f for _dp, _dn, _fs in os.walk(_r75bad) for _f in _fs if _f.endswith(".xwl")]
    if _x75:
        p75_fail.append("⑮ `#75` 夹具不变式破坏：坏 root %s 下应**零 `.xwl`**（否则判据翻 `ok`），实得 %s"
                        % (_r75bad, _x75))
    _p75 = os.path.join(_r75, "p75.xwl")
    _dump({"title": "p75", "children": [
        {"configs": {"itemId": "viewport",
                     "events": {"click": "Wb.request({url:'m?xwl=sub/d1'},function(){});"}},
         "type": "viewport", "expanded": False,
         "children": [_store("st75", "m?xwl=sub/missing")]}]}, _p75)
    _rc75b, _o75b = _run(xwl.cmd_params, file=_p75, module_root=_r75bad, controls=None,
                         list_fields=False, upstream=False)
    # ⚠️ 断言 A 必须用 **store 专属前缀** `url=sub/missing → …` —— 两支的**尾部**逐字相同
    #   （都是 `→ **未核对**（模块根不像模块根：`）⇒ 若 A 只用那段公共尾，撤 store 支后仍会被
    #   **direct 支那行**满足（假绿，与"先红后绿"要求冲突）。B 用 `sub/d1.xwl` 前缀，天然只命中 direct 支。
    if "url=sub/missing → **未核对**（模块根不像模块根：" not in _o75b:
        p75_fail.append("⑮ `#75`：坏 root 下 **store 支**未改「未核对」（`xwl.py:5563` 支失效）\n%s" % _o75b)
    if "sub/d1.xwl → **未核对**（模块根不像模块根：" not in _o75b:
        p75_fail.append("⑮ `#75`：坏 root 下 **direct 支**未改「未核对」（`xwl.py:5612` 支失效）\n%s" % _o75b)
    _rc75g, _o75g = _run(xwl.cmd_params, file=_p75, module_root=_r75ok, controls=None,
                         list_fields=False, upstream=False)
    if "未核对" in _o75g:
        p75_fail.append("⑮ `#75`：正确 `modules` 根下仍出现「未核对」（防「永远未核对」失效）\n%s" % _o75g)
    if p75_fail:
        failures.extend(p75_fail)
    else:
        print("[ok]  ⑮ `#75`：模块根存在但不像模块根 ⇒ store / direct **两站点**都改「未核对」＋原因；"
              "正确 `modules` 根 ⇒ 两处均无「未核对」；夹具自带「坏 root 零 `.xwl`」规模不变式")

    # ---- ⑯ `#74`（本段序）：**坏 `--controls`** 的诚实化行为（两站点各一条）----
    #   起因：给了 `--controls` 但**读不动（不是注册表）**时，`params` / `itemids` 曾把用户给的**坏路径**
    #     当"来源"打印（读起来像"真的读到了它"）、且是**静默回退** ⇒ 对齐 `check` 的诚实做法：
    #     先说读失败、来源按「**未找到**」。
    #   ⭐ 本守卫**只钉"坏 `--controls` 的行为"**：① 输出含 `[warn] 读注册表失败：`；
    #     ② **来源行 == 手写「未找到」文案**、且**不含**那个坏路径（⛔ 不再回退后仍打用户给的坏路径）。
    #   ⛔ 不重复 `f11`（见 `_ok("itemids / params / check ⑦ 打印同一句注册表来源…")` 那一支已钉的**文案字面**）
    #      —— 直接引用**手写**常量 `_REG_SRC_LINE_UNFOUND`（⚠️ 这里**有意不写行号**：函数已拆、行号整体前移，
    #      写死数字下一刻就又漂；按符号名／文案锚找才稳）；⛔ 不改 `controls_source_line`（`xwl.py:2151`，三处复用）。
    #   ⚠️ 坏 `--controls` 的**两种坏法都算**：`_registry_configs` 在「`json.load` 抛异常」**或**
    #      「能解析但一个控件 type 都没有（`{}` / `[]` / `{"foo":1}`）」时都返回 `None` ⇒ 两站点都会
    #      warn。夹具取最直白的一种（**非 JSON** 内容）。
    p74_fail: list[str] = []
    _bad74 = os.path.join(_r75, "bad-registry.json")   # 存在、但**不是**能解析的注册表

    def _src74(_o):
        for _ln in _o.splitlines():
            if "控件注册表:" in _ln:
                return _ln.strip()
        return None

    with open(_bad74, "w", encoding="utf-8") as _fh:
        _fh.write("这不是一份能解析的注册表 <<< >>>")
    _rc74p, _o74p = _run(xwl.cmd_params, file=_p75, module_root=_r75ok, controls=_bad74,
                         list_fields=False, upstream=False)
    _rc74i, _o74i = _run(xwl.cmd_itemids, file=_p75, controls=_bad74, name=None, suggest=False,
                         fix="auto", json=False, dups_only=False)
    for _site74, _o74 in (("params", _o74p), ("itemids", _o74i)):
        if "[warn] 读注册表失败：" not in _o74:
            p74_fail.append("⑯ `#74`（%s 站）：坏 `--controls` 未打 `[warn] 读注册表失败：`\n%s"
                            % (_site74, _o74))
        _sl74 = _src74(_o74)
        if _sl74 != _REG_SRC_LINE_UNFOUND:
            p74_fail.append("⑯ `#74`（%s 站）：来源行非**手写**「未找到」文案（应 %r，实 %r）"
                            % (_site74, _REG_SRC_LINE_UNFOUND, _sl74))
        if _bad74 in (_sl74 or ""):
            p74_fail.append("⑯ `#74`（%s 站）：来源行**仍打用户给的坏路径**：%r" % (_site74, _sl74))
    if p74_fail:
        failures.extend(p74_fail)
    else:
        print("[ok]  ⑯ `#74`：坏 `--controls` ⇒ `params` / `itemids` **两站点**都先给"
              "`[warn] 读注册表失败：`、来源行按**手写**「未找到」文案、⛔ 不再打那个坏路径")

    # ---- ⑰ `#80`（本段序）：**默认面**分组名不再误标「`Wb.request` 直接调用」（⛔ 不加任何开关）----
    #   起因：该清单由 `_REQ_URL_RE`（只看 `url:` ＋ `m?xwl=`）喂，里面 `Wb.request` / `Wb.open` /
    #     `store.load` **都有** ⇒ 旧组名「`Wb.request` 直接调用的 m?xwl」**以偏概全**（来源标签失真）。
    #   ⭐ 判据＝**默认面**（⛔ 不加 `--strict` / `--upstream` 等任何开关）输出含**手写**新组名逐字串。
    p80_fail: list[str] = []
    _rc80, _o80 = _run(xwl.cmd_params, file=_p75, module_root=_r75ok, controls=None,
                       list_fields=False, upstream=False)
    _want80 = "=== `url:'m?xwl=…'` 引用的 m?xwl（1 个；**不区分调用方**）==="
    if _want80 not in _o80:
        p80_fail.append("⑰ `#80`：默认面未出现**手写**新组名 %r\n%s" % (_want80, _o80))
    if p80_fail:
        failures.extend(p80_fail)
    else:
        print("[ok]  ⑰ `#80`：默认面 `params` 的 `m?xwl` 分组名 = **手写**"
              "「`url:'m?xwl=…'` 引用的 m?xwl（1 个；**不区分调用方**）」（⛔ 不加任何开关）")

_REG_SRC_LINE_UNFOUND = "控件注册表: 未找到（normalName 白名单 = 注册表 ∪ 内置兜底）"

