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

_REG_SRC_LINE_UNFOUND = "控件注册表: 未找到（normalName 白名单 = 注册表 ∪ 内置兜底）"

_GOLDEN_PAGE = '''{
 "hidden": false,
 "children": [{
  "configs": {"itemId": "module"},
  "expanded": false,
  "children": [],
  "type": "module"
 }],
 "roles": {"default": 1},
 "title": "金标页面",
 "iconCls": "",
 "inframe": false,
 "pageLink": ""
}'''

_GOLDEN_PANEL = '''{
 "hidden": false,
 "children": [{
  "configs": {"itemId": "module"},
  "expanded": false,
  "children": [{
   "configs": {"itemId": "panelTop"},
   "expanded": false,
   "children": [
    {
     "configs": {
      "itemId": "btnQuery",
      "text": "查询",
      "iconCls": "query_icon"
     },
     "expanded": false,
     "children": [],
     "type": "button"
    },
    {
     "configs": {
      "itemId": "btnReset",
      "text": "重置"
     },
     "expanded": false,
     "children": [],
     "type": "button"
    }
   ],
   "type": "panel"
  }],
  "type": "module"
 }],
 "roles": {"default": 1},
 "title": "金标页面",
 "iconCls": "",
 "inframe": false,
 "pageLink": ""
}'''

_GOLDEN_GRID = '''{
 "hidden": false,
 "children": [{
  "configs": {"itemId": "module"},
  "expanded": false,
  "children": [
   {
    "configs": {"itemId": "viewportMain"},
    "expanded": false,
    "children": [{
     "configs": {
      "itemId": "gridMain",
      "selType": "rowmodel"
     },
     "expanded": false,
     "children": [
      {
       "configs": {
        "itemId": "storeMain",
        "autoLoad": "false",
        "url": "demo/list"
       },
       "expanded": false,
       "children": [],
       "type": "store"
      },
      {
       "configs": {
        "itemId": "columns",
        "isConfig": "true"
       },
       "expanded": false,
       "children": [
        {
         "configs": {
          "itemId": "colCode",
          "dataIndex": "code",
          "text": "编码",
          "width": "140"
         },
         "expanded": false,
         "children": [],
         "type": "column"
        },
        {
         "configs": {
          "itemId": "colName",
          "dataIndex": "name",
          "text": "名称",
          "width": "200"
         },
         "expanded": false,
         "children": [],
         "type": "column"
        }
       ],
       "type": "array"
      }
     ],
     "type": "grid"
    }],
    "type": "viewport"
   },
   {
    "configs": {"itemId": "panelTop"},
    "expanded": false,
    "children": [{
     "configs": {
      "itemId": "btnQuery",
      "text": "查询",
      "iconCls": "query_icon"
     },
     "expanded": false,
     "children": [],
     "type": "button",
     "events": {"click": "app.storeMain.load();"}
    }],
    "type": "panel"
   }
  ],
  "type": "module"
 }],
 "roles": {"default": 1},
 "title": "金标页面",
 "iconCls": "",
 "inframe": false,
 "pageLink": ""
}'''

_GOLDEN_FORM = '''{
 "hidden": false,
 "children": [{
  "configs": {"itemId": "module"},
  "expanded": false,
  "children": [{
   "configs": {"itemId": "formEdit"},
   "expanded": false,
   "children": [
    {
     "configs": {
      "itemId": "fldName",
      "dataIndex": "name",
      "text": "名称",
      "xtype": "textfield"
     },
     "expanded": false,
     "children": [],
     "type": "field"
    },
    {
     "configs": {
      "itemId": "fldMemo",
      "dataIndex": "memo",
      "text": "备注",
      "xtype": "textarea"
     },
     "expanded": false,
     "children": [],
     "type": "field"
    }
   ],
   "type": "form"
  }],
  "type": "module"
 }],
 "roles": {"default": 1},
 "title": "金标页面",
 "iconCls": "",
 "inframe": false,
 "pageLink": ""
}'''

_GOLDEN_FLOAT_ONE = '''{
 "a": 1.0,
 "children": []
}'''

_GOLDEN_FLOAT_ZERO = '''{
 "a": 0.0,
 "children": []
}'''

_GOLDEN_PATCHED = '''{
 "a": 1.0,
 "title": "t2",
 "children": []
}'''

@_cap
def _check_bc_contract(tmp, node, failures, write) -> None:
    """B/C 组「注册键口径 + 换行判据 + 整数值浮点保真 + 排版提示具体化 + 注册表来源同句」的**行为断言**（第 27 组）。
    逐条行为断言见各节注释；改写相关的已落在 `_check_itemids`；
    行为级调用点守卫已随 `equivalent` 探针落在本文件上方 —— 两者都不在此重复。
    全部是行为断言：把新行为改回旧行为即红。
    """
    print("[27] 注册键口径 / 换行判据 / 整数值浮点 / 排版提示 / 注册表来源（行为断言）")
    bc: list[str] = []

    def _ok(label, fails):
        if fails:
            bc.extend(fails)
        else:
            print("[ok]  " + label)

    def _page(extra=None, children=None):
        o = {"hidden": False, "children": [] if children is None else children,
             "roles": {}, "title": "t", "iconCls": "", "inframe": "", "pageLink": ""}
        if extra:
            o.update(extra)
        return o

    def _styles(p):
        with open(p, "rb") as fh:
            return xwl.eol_styles(fh.read().decode("utf-8"))

    def _reg_line(out):
        for ln in out.splitlines():
            if "控件注册表:" in ln:
                return ln.strip()
        return None

    # ---- 三类碰撞各一成组（按注册键）----
    tree1 = {"children": [
        {"type": "panel", "configs": {"itemId": "A"}, "children": []},
        {"type": "panel", "configs": {"itemId": "A"}, "children": []},
        {"type": "panel", "configs": {"itemId": "B1", "normalName": "B"}, "children": []},
        {"type": "panel", "configs": {"itemId": "B"}, "children": []},
        {"type": "panel", "configs": {"itemId": "C1", "normalName": "C"}, "children": []},
        {"type": "panel", "configs": {"itemId": "C2", "normalName": "C"}, "children": []},
    ]}
    keys1 = {g["name"] for g in xwl.audit_itemids(tree1)["groups"]}
    miss1 = [w for w in ("A", "B", "C") if w not in keys1]
    f1 = (["三类碰撞未按注册键各成一组，缺 %s（实得 %s）" % (miss1, sorted(keys1))] if miss1 else [])
    _ok("三类碰撞各一成组（同 itemId / normalName 撞 itemId / 两个 normalName 重复）", f1)

    # ---- 被引用 → error；未被引用 → benign（只两级）----
    tree2 = {"children": [
        {"type": "button", "configs": {"itemId": "refd"}, "children": [],
         "events": {"click": "app.refd.setDisabled(true);"}},
        {"type": "button", "configs": {"itemId": "refd"}, "children": []},
        {"type": "panel", "configs": {"itemId": "plain"}, "children": []},
        {"type": "panel", "configs": {"itemId": "plain"}, "children": []},
    ]}
    rep2 = xwl.audit_itemids(tree2)
    lv2 = {g["name"]: g["level"] for g in rep2["groups"]}
    f2 = []
    if lv2.get("refd") != "error":
        f2.append("被引用的注册键组未判 error：%r" % lv2.get("refd"))
    if lv2.get("plain") != "benign":
        f2.append("未被引用的注册键组未判 benign：%r" % lv2.get("plain"))
    if any(g["level"] == "warn" for g in rep2["groups"]):
        f2.append("仍出现 warn 级组（只两级：被引用 error / 未被引用 benign）")
    _ok("被引用 → error / 未被引用 → benign（只两级，全文无 warn 级组）", f2)

    # ---- 仅 normalName 的节点参与分组 + 空串 normalName 视同缺失 ----
    tree3 = {"children": [
        {"type": "panel", "configs": {"normalName": "only"}, "children": []},
        {"type": "panel", "configs": {"itemId": "only"}, "children": []},
        {"type": "panel", "configs": {"itemId": "z1", "normalName": ""}, "children": []},
        {"type": "panel", "configs": {"itemId": "z1"}, "children": []},
    ]}
    keys3 = {g["name"] for g in xwl.audit_itemids(tree3)["groups"]}
    f3 = []
    if "only" not in keys3:
        f3.append("只有 normalName 的节点未参与注册键分组（缺 only）")
    if "z1" not in keys3:
        f3.append("空串 normalName 未视同缺失（两个 itemId=z1 的节点未成组）")
    _ok("仅 normalName 的节点参与分组 + 空串 normalName 视同缺失", f3)

    # ---- app['名'] 被认成引用 ----
    tree4 = {"children": [
        {"type": "panel", "configs": {"itemId": "p1"}, "children": [],
         "events": {"click": "app['p1'].refresh(); app[\"p1\"].focus(); app['a' + b].y();"}},
    ]}
    refs4 = xwl.js_refs_of(tree4, filtered=False)
    f4 = []
    if "p1" not in refs4:
        f4.append("js_refs_of 未认 app['p1'] / app[\"p1\"] 为引用")
    if "a" in refs4:
        f4.append("动态键 app['a' + b] 被误认成引用（应不认）")
    _ok("app['名'] / app[\"名\"] 被认成引用；动态键 app['a' + b] 不认", f4)

    # ---- 三写盘命令对同一输入给出同一 eol ----
    base_json = json.dumps(_page(), ensure_ascii=False, indent=1)   # LF 多行
    crlf_src = base_json.replace("\n", "\r\n")
    cr_src = base_json.replace("\n", "\r")

    def _patch_src(src_text, tag):
        p = write("bc5p_%s.xwl" % tag, src_text)
        ops = os.path.join(tmp, "bc5p_%s_ops.json" % tag)
        with open(ops, "w", encoding="utf-8") as fh:
            json.dump([{"op": "set", "path": ["title"], "value": "t2"}], fh, ensure_ascii=False)
        _run(xwl.cmd_patch, file=p, ops=ops, indent=1, eol="auto",
             dry_run=False, backup=False, node=None, no_js=True)
        return p

    def _expand_src(src_text, tag):
        p = write("bc5e_%s.xwl" % tag, src_text)
        _run(xwl.cmd_expand, file=p, eol="auto", indent=1, safe=False,
             dry_run=False, out=None, backup=False, node=None, no_js=True)
        return p

    def _edit_src(src_text, tag):
        p = write("bc5t_%s.xwl" % tag, src_text)
        oldp = write("bc5o_%s.txt" % tag, '"title": "t"')
        newp = write("bc5n_%s.txt" % tag, '"title": "t2"')
        _run(xwl.cmd_edit, target=p, old_file=oldp, new_file=newp, expect=1,
             dry_run=False, backup=False, node=None, no_js=True)
        return p

    f5 = []
    st_crlf = [_styles(_expand_src(crlf_src, "crlf")), _styles(_patch_src(crlf_src, "crlf")),
               _styles(_edit_src(crlf_src, "crlf"))]
    if any(s != {"crlf"} for s in st_crlf):
        f5.append("CRLF 源上 expand/patch/edit 的产出换行不一致或非纯 CRLF：%s" % (st_crlf,))
    st_cr = [_styles(_expand_src(cr_src, "cr")), _styles(_patch_src(cr_src, "cr")),
             _styles(_edit_src(cr_src, "cr"))]
    if any("cr" not in s for s in st_cr):
        f5.append("纯 CR 源上 expand/patch/edit 的产出未保留 CR：%s" % (st_cr,))
    _ok("三写盘命令对同一输入给出同一 eol（CRLF 源 ⇒ 纯 CRLF；纯 CR 源 ⇒ 仍含 CR）", f5)

    # ---- 三类「不能加载」文案可区分且 rc 不变 ----
    p_e = write("bc6_empty.xwl", "")
    p_t = write("bc6_tpl.xwl", '{"children": [#{x}]}')
    p_b = write("bc6_bad.xwl", '{"children": [')
    rc_e, out_e = _run_check([p_e], node)
    rc_t, out_t = _run_check([p_t], node)
    rc_b, out_b = _run_check([p_b], node)
    f6 = []
    if (rc_e, rc_t, rc_b) != (1, 1, 1):
        f6.append("空文件 / 模板 / 真坏三类 rc 应均为 1，实得 %s" % ((rc_e, rc_t, rc_b),))
    if "这是空文件" not in out_e:
        f6.append("空文件未给「这是空文件（尚未建内容）」文案")
    if "疑似设计器模板" not in out_t:
        f6.append("设计器模板未给「疑似设计器模板」文案")
    if "加载器等价解析失败" not in out_b:
        f6.append("真坏文件未给「加载器等价解析失败」文案")
    _ok("空文件 / 设计器模板 / 真坏：三条文案互不相同且 rc 均 = 1", f6)

    # ---- 正面：整数值浮点保真写出（**与金标逐字节**，⛔ 不是与自身再解析结果比）----
    # 本臂证明的是与金标一致：旧臂把产出再解析回来跟手写期望比，而解析器与序列化器同源
    #   ⇒ 同一处理解错（例如把 `1.0` 写成 `1`）时两头一起错、比完仍相等。改成比冻结字节后立刻红。
    #   ⚠️ 单点注入（只折叠 `.0`、等价判定仍严）会让 `expand` 自判 rc=2 ⇒ 旧臂也红；本臂的增量在
    #   "序列化与等价判定同向误解"（实测 rc=0、旧臂全绿、本臂 3 条全红）与"字节变了但语义等价"。
    f7 = []
    for _lit, _gt in (("1.0", _GOLDEN_FLOAT_ONE), ("0.0", _GOLDEN_FLOAT_ZERO)):
        p = write("bc7_%s.xwl" % _lit, '{"a": %s, "children": []}' % _lit)
        rc, _o = _run(xwl.cmd_expand, file=p, eol="auto", indent=1, safe=False,
                      dry_run=False, out=None, backup=False, node=None, no_js=True)
        with open(p, "rb") as _fh7:
            _got7 = _fh7.read()
        _want7 = _gt.encode("utf-8")
        if rc != 0:
            f7.append("expand %s ⇒ rc=%d（应 0）" % (_lit, rc))
        elif _got7 != _want7:
            f7.append("expand %s 产出与金标不一致：金标 %d B／md5 %s，产出 %d B／md5 %s"
                      "（把 `.0` 折叠成整数、或改了排版都会落在这里）"
                      % (_lit, len(_want7), hashlib.md5(_want7).hexdigest(),
                         len(_got7), hashlib.md5(_got7).hexdigest()))
    p7p = write("bc7_patch.xwl", '{"a": 1.0, "title": "t", "children": []}')
    ops7 = os.path.join(tmp, "bc7_ops.json")
    with open(ops7, "w", encoding="utf-8") as fh:
        json.dump([{"op": "set", "path": ["title"], "value": "t2"}], fh, ensure_ascii=False)
    rc7p, _o = _run(xwl.cmd_patch, file=p7p, ops=ops7, indent=1, eol="auto",
                    dry_run=False, backup=False, node=None, no_js=True)
    with open(p7p, "rb") as _fh7p:
        _got7p = _fh7p.read()
    _want7p = _GOLDEN_PATCHED.encode("utf-8")
    if rc7p != 0:
        f7.append("patch 含 {\"a\": 1.0} 源 ⇒ rc=%d（应 0）" % rc7p)
    elif _got7p != _want7p:
        f7.append("patch 含 {\"a\": 1.0} 的产出与金标不一致：金标 %d B／md5 %s，产出 %d B／md5 %s"
                  % (len(_want7p), hashlib.md5(_want7p).hexdigest(),
                     len(_got7p), hashlib.md5(_got7p).hexdigest()))
    _ok("正面：{\"a\":1.0} / {\"a\":0.0} 保真写出且 expand/patch 产出与金标逐字节相同", f7)

    # ---- 反面：1 与 1.0 仍不相等（守值类型可区分）----
    f8 = []
    if xwl.equivalent({"a": 1}, {"a": 1.0}):
        f8.append("equivalent 把 1 与 1.0 判成相等（值类型漂移会重新静默通过）")
    if xwl.equivalent({"a": True}, {"a": 1}):
        f8.append("equivalent 把 true 与 1 判成相等")
    _ok("反面：equivalent 下 1 ≠ 1.0、true ≠ 1（值类型仍可区分）", f8)

    # ---- 金标固定点：`expand` 的产出必须与金标**逐字节**相同 ----
    # ⭐ 本臂证明的是**与金标一致**，⛔ 不是**与自身自洽**：金标是本文件里的冻结字面量（说明见模块级），
    #   两端同源的比对（`expand` 排的版再由 `expand` 判回自己）在这里换成了**外部期望值**。
    #   注入方式＝改金标一个字符（或改 `_number`／序列化）⇒ 本臂红；改回 ⇒ 绿。
    _gk = (("page", _GOLDEN_PAGE), ("panel", _GOLDEN_PANEL),
           ("grid", _GOLDEN_GRID), ("form", _GOLDEN_FORM))
    fg = []
    for _g_name, _g_text in _gk:
        _g_want = _g_text.encode("utf-8")
        _g_path = write("bcg_%s.xwl" % _g_name, _g_text)
        _g_rc, _g_out = _run(xwl.cmd_expand, file=_g_path, eol="auto", indent=1, safe=False,
                             dry_run=False, out=None, backup=False, node=None, no_js=True)
        with open(_g_path, "rb") as _g_fh:
            _g_got = _g_fh.read()
        if _g_rc != 0:
            fg.append("金标 %s 的 expand 应 rc=0，实得 %s（%s）"
                      % (_g_name, _g_rc, _g_out.strip().replace("\n", " ")[:160]))
        elif _g_got != _g_want:
            fg.append("金标 %s 的 expand 产出与金标不一致：金标 %d B／md5 %s，产出 %d B／md5 %s"
                      % (_g_name, len(_g_want), hashlib.md5(_g_want).hexdigest(),
                         len(_g_got), hashlib.md5(_g_got).hexdigest()))
    _ok("金标固定点：%d 份金标经 expand 后与金标逐字节相同（与金标一致，不是与自身自洽）"
        % len(_gk), fg)

    # ---- 纯 CR：check rc=0 且有 [warn]、非 FAIL ----
    p_cr = write("bc9_cr.xwl", cr_src)
    rc9, out9 = _run_check([p_cr], node)
    f9 = []
    if rc9 != 0:
        f9.append("纯 CR 源 check rc=%d（应 0：纯 CR 降为 warn）" % rc9)
    if "[warn] 该文件是 CR 换行" not in out9:
        f9.append("纯 CR 源未打「该文件是 CR 换行…」[warn] 文案")
    if "② 换行混用" in out9:
        f9.append("纯 CR 源被误判成 ② 换行混用")
    _ok("纯 CR：check rc=0 且有 [warn]、不含该文件的 ② FAIL", f9)

    # ---- CR 占多数的混合源产出不得是 CR（两层规则）----
    f10 = []
    if xwl.pick_eol_for_auto("a\rb\rc\rd\r\ne\n") != "crlf":
        f10.append("CR 占多数的混合源未按「只在 CRLF/LF 取多数」返回（得 %r）"
                   % xwl.pick_eol_for_auto("a\rb\rc\rd\r\ne\n"))
    if xwl.pick_eol_for_auto("a\r\nb\nc\n") != "lf":
        f10.append("LF 占多数的混合源应返回 lf")
    if xwl.pick_eol_for_auto("a\r\nb\n") != "crlf":
        f10.append("CRLF/LF 等量时应取 crlf")
    if xwl.pick_eol_for_auto("a\rb\r") != "cr":
        f10.append("纯 CR 源（单一风格）应沿用以 cr")
    if xwl.pick_eol_for_auto("nownewline") != "lf":
        f10.append("无换行源应回退 lf")
    _ok("pick_eol_for_auto：CR 占多数 ⇒ 取 CRLF/LF（绝不 cr）；等量取 CRLF；纯 CR 沿用 cr", f10)

    # ---- itemids / params / check ⑦ 打印同一句注册表来源 ----
    p11 = write("bc11.xwl", json.dumps(_page(), ensure_ascii=False, indent=1))
    _ri, out_i = _run(xwl.cmd_itemids, file=p11, controls=None, name=None, suggest=False,
                      fix="auto", json=False, dups_only=False)
    # 经 `_run_cli`（子进程真 CLI）取值：同 12b/15 的起因 —— 直调时被测行为一旦抛异常，异常冲出
    #   `_run` ⇒「注册表来源行」断言没跑到；经 CLI 则异常被隔离、红行必落在那条断言上。`params` 不传 = 与
    #   `cmd_params(file=p11, controls=None, list_fields=False, module_root=None)` 等价（argparse 默认值同）。
    _rp, out_p, _ep = _run_cli(["params", p11])
    _rc11, out_c = _run_check([p11], node)
    li, lp, lc = _reg_line(out_i), _reg_line(out_p), _reg_line(out_c)
    f11 = []
    if not li:
        f11.append("itemids 未打印「控件注册表:」来源行")
    if not lp:
        f11.append("params 未打印「控件注册表:」来源行")
    if not lc:
        f11.append("check ⑦ 未打印「控件注册表:」来源行")
    if li and lp and lc and not (li == lp == lc):
        f11.append("三命令的注册表来源行不逐字一致：%r / %r / %r" % (li, lp, lc))
    if li and li != _REG_SRC_LINE_UNFOUND:
        f11.append("来源行与**手写**期望 %r 不一致：%r"
                   % (_REG_SRC_LINE_UNFOUND, li))
    _ok("itemids / params / check ⑦ 打印同一句注册表来源（含「未找到」分支；期望为**手写**文案）", f11)

    # ---- --json 只增字段（name = 注册键）----
    p12 = write("bc12.xwl", json.dumps(_page(children=[
        {"type": "button", "configs": {"itemId": "iA"}, "children": [],
         "events": {"click": "app.iA.setDisabled(true);"}},
        {"type": "button", "configs": {"itemId": "iB", "normalName": "iA"}, "children": []},
    ]), ensure_ascii=False, indent=1))
    _r12, out12 = _run(xwl.cmd_itemids, file=p12, controls=None, name=None, suggest=False,
                       fix="auto", json=True, dups_only=False)
    f12 = []
    try:
        grps12 = json.loads(out12).get("groups") or []
    except Exception as exc:  # noqa: BLE001
        f12.append("itemids --json 输出不是 JSON：%s" % exc)
        grps12 = []
    if not grps12:
        f12.append("itemids --json 未给出 groups（样本应有一组重名）")
    else:
        g = grps12[0]
        if g.get("registryName") != "iA":
            f12.append("groups[].registryName 应为注册键 iA，实得 %r" % g.get("registryName"))
        if g.get("name") != "iA":
            f12.append("groups[].name 应为注册键 iA（语义：name = 注册键），实得 %r" % g.get("name"))
        if g.get("itemIds") != ["iA", "iB"]:
            f12.append("groups[].itemIds 应为 ['iA','iB']，实得 %r" % g.get("itemIds"))
    _r12b, out12b = _run(xwl.cmd_itemids, file=p12, controls=None, name="iA", suggest=False,
                         fix="auto", json=True, dups_only=False)
    try:
        nodes12 = json.loads(out12b)
        if not all(isinstance(n, dict) and "itemId" in n for n in nodes12):
            f12.append("--name --json 的 node 项缺 itemId 字段")
    except Exception as exc:  # noqa: BLE001
        f12.append("--name --json 输出不是 JSON：%s" % exc)
    _ok("--json 组项含 itemIds/registryName 且 name=注册键；--name --json 的 node 项含 itemId", f12)

    # ---- patch / expand 的具体化提示（三类计数）----
    noncanon = json.dumps(_page(), ensure_ascii=False, indent=4)   # 缩进 4 ≠ 设计器 1 ⇒ 非原样
    pe13 = write("bc13_expand.xwl", noncanon)
    _re13, out_e13 = _run(xwl.cmd_expand, file=pe13, eol="auto", indent=1, safe=False,
                          dry_run=False, out=None, backup=False, node=None, no_js=True)
    pp13 = write("bc13_patch.xwl", noncanon)
    ops13 = os.path.join(tmp, "bc13_ops.json")
    with open(ops13, "w", encoding="utf-8") as fh:
        json.dump([{"op": "set", "path": ["title"], "value": "t2"}], fh, ensure_ascii=False)
    _rp13, out_p13 = _run(xwl.cmd_patch, file=pp13, ops=ops13, indent=1, eol="auto",
                          dry_run=True, backup=False, node=None, no_js=True)
    f13 = []
    pat = re.compile(r"缩进 (\d+) 处 / \\uXXXX 转义 (\d+) 处 / 数字形态 (\d+) 处")
    for who, out in (("expand", out_e13), ("patch", out_p13)):
        m = pat.search(out)
        if not m:
            f13.append("%s 未给「缩进 N 处 / \\uXXXX 转义 N 处 / 数字形态 N 处」具体化提示" % who)
        elif int(m.group(1)) <= 0:
            f13.append("%s 的缩进计数为 0（非原样排版样本应 > 0）" % who)
    _ok("patch / expand 对非原样源给出三类改写计数（缩进 / \\uXXXX 转义 / 数字形态）", f13)

    # ---- 同源：params 侧与 itemids 侧对 app.<名> / app['名'] 的容器名认定逐名一致 ----
    # 注入判据：把 `_app_refs_in` 改回只 `_APP_REF_BARE`（丢掉 app['名']）⇒ 本条**必须转红**。
    # 样本含三种写法：app['p1'] + app.p2 + app.get('p3')（都写成 transfer 形态，
    # 否则 `find_transfers` 只在 `out:` / `params=` 之后扫表达式，扫不到）。
    # 注：`app.get('名')` 在 params 侧本就是**请求级参数**（xwl.py 里走 serverScript 分支的 `_APP_REF_GET`），
    #     故意不算容器名 —— 故比对只看两侧共用的符号类（app.<名> + app['名']），该对集合须逐名相等。
    # ⚠️ 纯"两侧一致"会被**对称失明**骗过（两侧同步丢掉 app['名'] ⇒ 等式照样成立）⇒ 下面三条**前置**
    #    把"双侧都必须**真的**认到 app['名'](p1)"钉死（用字面 {"p1"} / "p1" 比对，不写成"非空即可"）。
    js15 = ("g.load({ out: app.p2, params: Wb.getValue(app['p1']) }); "
            "h.load({ out: app.get('p3') });")
    tree15 = {"children": [{"type": "button", "configs": {}, "children": [],
                            "events": {"click": js15}}]}
    ids15 = xwl.js_refs_of(tree15, filtered=False)                 # itemids 侧（含 app.get 类）
    get_only15 = (set(xwl._APP_REF_GET.findall(js15))
                  - set(xwl._APP_REF_BARE.findall(js15))
                  - set(xwl._APP_REF_BRACKET.findall(js15)))       # 仅 app.get 才认到的名
    ids15_shared = ids15 - get_only15                             # 两侧共用符号类上的 itemids 侧
    pm15 = {n for _k, conts, _kk, _raw in xwl.find_transfers(js15, xwl.field_types(None))
            for n in conts}
    f15 = []
    # 前置①：样本里 `_APP_REF_BRACKET` 必须**恰好**认到 {p1}（字面比对，防样本被改空/改形）
    if set(xwl._APP_REF_BRACKET.findall(js15)) != {"p1"}:
        f15.append("fixture 失效：样本里 _APP_REF_BRACKET 未恰好认到 {p1}（实得 %s）"
                   % sorted(xwl._APP_REF_BRACKET.findall(js15)))
    # 前置②③：两侧都必须**真的**认到 app['名'](p1) —— 否则下面的"一致性"会因**对称失明**而假绿
    if "p1" not in pm15:
        f15.append("params 侧未认 app['名'](p1) ⇒ 断言空转（实得容器名 %s）" % sorted(pm15))
    if "p1" not in ids15_shared:
        f15.append("itemids 侧未认 app['名'](p1) ⇒ 断言空转（实得容器名 %s）" % sorted(ids15_shared))
    if ids15_shared != pm15:
        f15.append("params 侧与 itemids 侧对 app['名'] / app.<名> 的容器名不逐名一致："
                   "itemids=%s params=%s（差集 %s）"
                   % (sorted(ids15_shared), sorted(pm15), sorted(ids15_shared ^ pm15)))
    _ok("params 侧与 itemids 侧对 app['名'] / app.<名> 的容器名认定逐名一致", f15)

    # 尾部两组（`app._X` 欠报 / params 按注册键找容器）已下沉为 `_check_bc_contract_tail`
    #   （本函数 406 行，要进 400 的上限）。判据文本逐字未改。
    _check_bc_contract_tail(write, node, bc, _page, _ok)

    if bc:
        failures.extend(bc)

@_cap
def _check_bc_contract_tail(write, node, bc, _page, _ok) -> None:
    """`_check_bc_contract` 的尾部两组（有界下沉，判据文本逐字未改）。"""
    # ---- 回归：只以 `app._X` 形式被引用的重名组也必须判 error（欠报修复）----
    # 注入判据：把 `audit_itemids` 的 `referenced = (name in refs_all) or ("_" + name in refs_all)`
    #   改回 `referenced = name in refs_all` ⇒ 本条**必须转红**（该组退回 benign、check rc 变 0）。
    # 删掉本条 ⇒ `app._X` 这种引用写法导致的欠报会静默回归（⑦ 假绿）。
    p17 = write("bc17_regref.xwl", json.dumps(_page(children=[
        {"type": "button", "configs": {"itemId": "w"}, "children": [],
         "events": {"click": "app._w.show();"}},
        {"type": "button", "configs": {"itemId": "w"}, "children": []},
    ]), ensure_ascii=False, indent=1))
    rc17, out17 = _run_check([p17], node)
    f17 = []
    if rc17 == 0:
        f17.append("只以 `app._w` 引用的重名组未使 check 失败（rc=%d，应≠0）" % rc17)
    if "⑦" not in out17 or "被事件 JS 引用" not in out17:
        f17.append("check 未打「⑦ … 被事件 JS 引用」：%s"
                   % " | ".join(ln.strip() for ln in out17.splitlines() if "⑦" in ln))
    _ok("只以 `app._w` 引用的重名组判 error（check FAIL / rc≠0）", f17)

    # ---- 回归：params 按**注册键**找容器（假「找不到容器」修复）----
    # 注入判据：把 `cmd_params` 的 `locs = [(h[5], h[6]) for h in itemid_hits(obj, a, by="registry")]`
    #   改回 `locs = _find_all_by_itemid(obj, a)`（丢掉按注册键那一支）⇒ 本条**必须转红**。
    # 删掉本条 ⇒ 同页多 toolbar 共用 itemId、靠 normalName 区分时，params 会再假报「找不到容器」。
    p18 = write("bc18_regcontainer.xwl", json.dumps(_page(children=[
        {"type": "toolbar", "configs": {"itemId": "tbar", "normalName": "tbrO"}, "children": [
            {"type": "text", "configs": {"itemId": "jtServiceCode"}, "children": []},
            {"type": "text", "configs": {"itemId": "lineCo"}, "children": []},
        ]},
        {"type": "toolbar", "configs": {"itemId": "tbar"}, "children": [
            {"type": "text", "configs": {"itemId": "otherField"}, "children": []},
        ]},
        {"type": "button", "configs": {"itemId": "jsHost"}, "children": [],
         "events": {"click": "st.load({out: app.tbrO});"}},
    ]), ensure_ascii=False, indent=1))
    # 经 `_run_cli`（子进程真 CLI）取值：同 12b/15 的起因（直调抛异常 ⇒ 定向断言没跑到；块级兜底只让失败可读，⛔ 不替你跑断言）。
    #   `params` 不传 = 与 `cmd_params(file=p18, controls=None, list_fields=False, module_root=None)` 等价。
    _rc18, out18, _e18 = _run_cli(["params", p18])
    f18 = []
    if "找不到" in out18:
        f18.append("params 仍报「找不到 … 的容器」（应按注册键 tbrO 命中 normalName=tbrO 的 toolbar）：%s"
                   % " | ".join(ln.strip() for ln in out18.splitlines() if "找不到" in ln)[:200])
    if "app.tbrO" not in out18 or "容器内取值控件" not in out18:
        f18.append("params 未把 app.tbrO 当容器列出并给容器内取值控件")
    _ok("params 按**注册键**找容器（normalName=tbrO 的 toolbar 命中、无假「找不到容器」）", f18)

