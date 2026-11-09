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

def _check_patch_contract(tmp, node, failures, write) -> None:
    """`patch` 的 ops 契约：`create` 开关、数组下标越界、新建键/单行源/未备份三类输出。

    全部是**行为断言**（不是 help 文案断言）：把对应行为改回去，本组立刻红。

    ⚠️ **块头/组号说明**（`#10b②`）：本块原**无**任何 `# ---- N.` 块头。旧编号序列里它夹在
       `§11`（itemids）与 `§12`（subcommands）之间、**没有空槽整数** ⇒ 本块以**块名 `patch_contract`**
       标识，**不新造序号**（硬凑 `§12` 等会与既有号撞号）。守卫块头一律是 `# 17<字母>` 形状，不受影响。
    """
    pc_fail: list[str] = []

    def _md5(p):
        h = hashlib.md5()
        with open(p, "rb") as fh:
            for ch in iter(lambda: fh.read(65536), b""):
                h.update(ch)
        return h.hexdigest()

    def _mkops(name, ops):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(ops, fh, ensure_ascii=False, indent=1)
        return p

    def _patch(target, ops_name, ops, dry_run=False, backup=False, allow_new_key=False):
        return _run(xwl.cmd_patch, file=target, ops=_mkops(ops_name, ops), indent=1,
                    eol="auto", dry_run=dry_run, backup=backup, node=None, no_js=True,
                    allow_new_key=allow_new_key)

    def _page(extra_top=None, children=None):
        obj = {"hidden": False, "children": [] if children is None else children,
               "roles": {}, "title": "t", "iconCls": "", "inframe": "", "pageLink": ""}
        if extra_top:
            obj.update(extra_top)
        return json.dumps(obj, ensure_ascii=False, indent=1)

    def _ok(num, fails, msg):
        if fails:
            pc_fail.extend("§%s %s" % (num, m) for m in fails)
        else:
            print("[ok]  §%s %s" % (num, msg))

    # ⚠️ 让 "dp" 组**被引用**（error 级）：未被引用的重名是 benign，
    #    而 `recommend_fixes` 只处理 error/warn 组 ⇒ 否则 --suggest 恒空（假绿）。
    dup_children = [{"type": "panel", "configs": {"itemId": "dp"}, "children": []},
                    {"type": "panel", "configs": {"itemId": "dp"}, "children": [],
                     "events": {"click": "app.dp.hide();"}}]

    # ---- 默认拒绝新建键：apply_ops 抛错 + 真跑 rc=2、[FAIL] 直接教两条出路 ----
    f1 = []
    try:
        xwl.apply_ops({"title": "t"}, [{"op": "set", "path": ["nk"], "value": "v"}],
                      created=[], warned=[])
        f1.append("apply_ops 默认未拒新建键（应 ValueError）")
    except ValueError as exc:
        s1 = str(exc)
        if '"create": true' not in s1 or "--allow-new-key" not in s1:
            f1.append("apply_ops 报错未教两条出路：%s" % s1)
    p1 = write("pc_5_1.xwl", _page())
    rc1, o1 = _patch(p1, "pc_5_1_ops.json", [{"op": "set", "path": ["newTopKey"], "value": "v"}])
    if rc1 != 2:
        f1.append("默认新建键真跑 rc=%d（应 2）" % rc1)
    if "[FAIL]" not in o1 or '"create": true' not in o1 or "--allow-new-key" not in o1:
        f1.append("默认新建键真跑未打 [FAIL] 或未教两条出路:\n%s" % o1)
    if xwl.load_xwl(p1)[2].get("newTopKey") is not None:
        f1.append("被拒的新建键竟然写进了文件")
    _ok("5-1", f1, "set 新建键默认被拒绝（apply_ops ValueError ＋ 真跑 rc=2、[FAIL] 教两条出路、不写盘）")

    # ---- 全局逃生开关 `--allow-new-key` 恢复旧行为（放行 + 留痕 + rc=0）----
    # ⚠️ 这条**直调** `apply_ops(..., allow_new_key=True)`（与 `--strict` 夹具同理，见 `_check_new_guards` ①）：
    #    开关一被改坏就可能抛异常 ⇒ **必须自己兜异常**，否则整块崩、**没有定向 `[FAIL]` 行**、
    #    且同块后续检查全被跳过。`except` 里保持 `t2b` / `w2b` / `f2b` 已初始化 ⇒ 失败落成**定向红行**。
    f2b: list = []
    t2b = {"title": "t", "children": []}
    w2b: list = []
    try:
        xwl.apply_ops(t2b, [{"op": "set", "path": ["newTopKey"], "value": "v"}],
                      created=[], warned=w2b, allow_new_key=True)
    except Exception as exc:  # noqa: BLE001 —— 开关改坏本身就该红，别静默放过
        f2b.append("直调 `apply_ops(..., allow_new_key=True)` 抛异常: %s: %s"
                   % (type(exc).__name__, exc))
    # ⚠️ `patch --help` 的 **options 段**必须**直接**含 `--allow-new-key`（对称于 `_check_new_guards` ① 对 `--strict` 的 help 直断言）。
    #    起因：该选项**只靠 `_help_caps` 的「上限过松」臂间接保护**（cap=47）—— 把选项从 help 里删掉，
    #    只要行数仍落在 [实测, 实测+5] 内，cap 臂就看不见（本项目病根：**新能力靠间接保护**）。故补**直断言**。
    #    ⚠️ **只认 options 段那一行**（以 `--allow-new-key` 起头）；**不能用整篇 `in` 判**：patch 的
    #    **usage 行**与 **epilog** 里也出现该字样 ⇒ 整篇 `in` 会在「选项被删、epilog 尚在」时**假绿**（实测）。
    try:
        _p2b = xwl.build_parser()
        _s2b = next((a for a in _p2b._actions if getattr(a, "choices", None)), None)
        _patch_help2b = _s2b.choices["patch"].format_help() if _s2b is not None else ""
    except Exception as exc:  # noqa: BLE001
        _patch_help2b = ""
        f2b.append("取 `patch --help` 失败: %s: %s" % (type(exc).__name__, exc))
    if not any(ln.lstrip().startswith("--allow-new-key") for ln in _patch_help2b.splitlines()):
        f2b.append("`patch --help` 的 **options 段**里没有 `--allow-new-key`"
                   "（该选项只靠 cap 过松臂间接保护 ⇒ 补直断言）")
    p2b = write("pc_5_1b.xwl", _page())
    rc2b, o2b = _patch(p2b, "pc_5_1b_ops.json",
                       [{"op": "set", "path": ["newTopKey"], "value": "v"}], allow_new_key=True)
    if t2b.get("newTopKey") != "v":
        f2b.append("--allow-new-key 未放行新建键（键没被建）")
    if w2b != ["newTopKey"]:
        f2b.append("warned 未收集被放行的新建键：%r" % w2b)
    if rc2b != 0:
        f2b.append("真跑 rc=%d（应 0）" % rc2b)
    if "--allow-new-key" not in o2b or "已放行" not in o2b:
        f2b.append("真跑未打 --allow-new-key 放行留痕:\n%s" % o2b)
    if xwl.load_xwl(p2b)[2].get("newTopKey") != "v":
        f2b.append("--allow-new-key 真跑没把新键写进文件")
    _ok("5-1b", f2b, "--allow-new-key 逃生开关恢复旧行为：放行新建键、warned 收集、真跑 rc=0 且留痕")

    # ---- `create:true` 放行且无 `[warn]` ----
    t2 = {"title": "t", "children": []}
    w2, c2 = [], []
    xwl.apply_ops(t2, [{"op": "set", "path": ["k2"], "value": "v", "create": True}],
                  created=c2, warned=w2)
    p2 = write("pc_5_2.xwl", _page())
    rc2, o2 = _patch(p2, "pc_5_2_ops.json", [{"op": "set", "path": ["k2"], "value": "v", "create": True}])
    f2 = []
    if t2.get("k2") != "v":
        f2.append("带 create 的键没被建")
    if w2:
        f2.append("带 create 却进了 warned：%r" % w2)
    if c2 != ["k2"]:
        f2.append("created 未收集该键：%r" % c2)
    if rc2 != 0:
        f2.append("真跑 rc=%d（应 0）" % rc2)
    if "[warn] --allow-new-key" in o2:
        f2.append("带 create 却打了新建键预告")
    _ok("5-2", f2, "create:true 放行、created 收集、warned 为空、stdout 不含 [warn] 预告")

    # ---- 已存在键 + `create:true` ⇒ 不报错、不 `[warn]`（幂等保护）----
    t3 = {"title": "t", "children": []}
    w3: list = []
    xwl.apply_ops(t3, [{"op": "set", "path": ["title"], "value": "t2", "create": True}],
                  created=[], warned=w3)
    p3 = write("pc_5_3.xwl", _page())
    rc3, o3 = _patch(p3, "pc_5_3_ops.json",
                     [{"op": "set", "path": ["title"], "value": "t2", "create": True}])
    f3 = []
    if t3.get("title") != "t2":
        f3.append("已存在的键未被改写")
    if w3:
        f3.append("已存在键 + create 误报 [warn]：%r" % w3)
    if rc3 != 0:
        f3.append("真跑 rc=%d（应 0）" % rc3)
    if "[warn] --allow-new-key" in o3:
        f3.append("已存在键 + create 打了新建键预告")
    _ok("5-3", f3, "已存在键 + create:true ⇒ 不报错、不 [warn]、rc=0（幂等保护）")

    # ---- 非 `set` op 带 `create` ⇒ rc=2 ----
    f4 = []
    for k4, op4 in (
            ("insert", {"op": "insert", "path": ["children"], "value": {"type": "panel"}, "create": True}),
            ("append", {"op": "append", "path": ["children"], "value": {"type": "panel"}, "create": True}),
            ("delete", {"op": "delete", "path": ["children"], "create": True})):
        try:
            xwl.apply_ops({"children": []}, [op4])
            f4.append("%s 带 create 未报错（应 ValueError）" % k4)
        except ValueError as exc:
            s4 = str(exc)
            if "`create`" not in s4 or "只用于" not in s4:
                f4.append("%s 的报错文本不含「只用于 set」：%s" % (k4, s4))
    rc4, _o4 = _patch(write("pc_5_4.xwl", _page()), "pc_5_4_ops.json",
                      [{"op": "append", "path": ["children"],
                        "value": {"type": "panel"}, "create": True}])
    if rc4 != 2:
        f4.append("非 set 带 create 时 cmd_patch rc=%d（应 2）" % rc4)
    _ok("5-4", f4, "insert/append/delete 带 create ⇒ ValueError + cmd_patch rc=2")

    # ---- `insert` 下标越界（正、负各一）⇒ rc=2 ----
    f5 = []
    for idx5 in (4, -1):
        try:
            xwl.apply_ops({"children": [1, 2, 3]},
                          [{"op": "insert", "path": ["children"], "index": idx5, "value": 9}])
            f5.append("insert index=%d 未报错" % idx5)
        except ValueError as exc:
            s5 = str(exc)
            if any(w in s5 for w in ("IndexError", "KeyError", "ValueError")):
                f5.append("insert index=%d 冒了裸异常类型名：%s" % (idx5, s5))
            elif "数组长度" not in s5 or "合法区间" not in s5:
                f5.append("insert index=%d 报错缺长度/区间：%s" % (idx5, s5))
    _ok("5-5", f5, "insert 下标越界（+4 / -1）⇒ ValueError 含数组长度与合法区间")

    # ---- `delete` 越界 ⇒ rc=2；`delete` 缺失键 ⇒ rc=2，且不冒裸异常类型名 ----
    f6 = []
    try:
        xwl.apply_ops({"children": [1, 2, 3]}, [{"op": "delete", "path": ["children"], "index": 99}])
        f6.append("delete index=99 未报错")
    except ValueError as exc:
        s6 = str(exc)
        if "合法区间" not in s6:
            f6.append("delete 越界报错缺合法区间：%s" % s6)
        if any(w in s6 for w in ("IndexError", "KeyError", "ValueError")):
            f6.append("delete 越界报错冒了裸异常类型名：%s" % s6)
    try:
        xwl.apply_ops({"children": [{"configs": {"itemId": "a"}}]},
                      [{"op": "delete", "path": ["children", 0, "serverScript"]}])
        f6.append("delete 缺失键未报错")
    except ValueError as exc:
        s6 = str(exc)
        if "不存在" not in s6 or "children[0].serverScript" not in s6:
            f6.append("delete 缺失键报错未点名该键：%s" % s6)
        if any(w in s6 for w in ("IndexError", "KeyError", "ValueError")):
            f6.append("delete 缺失键报错冒了裸异常类型名：%s" % s6)
    rc6, o6 = _patch(write("pc_5_6.xwl", _page(children=[{"type": "panel",
                                                          "configs": {"itemId": "a"},
                                                          "children": []}])),
                     "pc_5_6_ops.json", [{"op": "delete", "path": ["children", 0, "serverScript"]}])
    if rc6 != 2:
        f6.append("delete 缺失键时 cmd_patch rc=%d（应 2）" % rc6)
    if "Traceback" in o6:
        f6.append("delete 缺失键冒了 traceback")
    _ok("5-6", f6, "delete 越界 / 缺失键 ⇒ rc=2，报错不冒裸异常类型名、无 traceback")

    # ---- `--dry-run` 的 `[new-key]` 与 `[warn]` 分列，且不写盘（逃生开关下两条都出现）----
    p7 = write("pc_5_7.xwl", _page())
    m7 = _md5(p7)
    rc7, o7 = _patch(p7, "pc_5_7_ops.json",
                     [{"op": "set", "path": ["kCreate"], "value": "v", "create": True},
                      {"op": "set", "path": ["kWarn"], "value": "v"}], dry_run=True,
                     allow_new_key=True)
    nk = [ln for ln in o7.splitlines() if ln.startswith("[new-key]")]
    wn = [ln for ln in o7.splitlines() if ln.startswith("[warn] --allow-new-key")]
    f7 = []
    if rc7 != 0:
        f7.append("dry-run rc=%d（应 0）" % rc7)
    if len(nk) != 1 or "kCreate" not in nk[0] or "kWarn" in nk[0]:
        f7.append("[new-key] 行应恰 1 条且只列 kCreate：%r" % nk)
    if len(wn) != 1 or "kWarn" not in wn[0] or "kCreate" in wn[0]:
        f7.append("[warn] 行应恰 1 条且只列 kWarn：%r" % wn)
    if _md5(p7) != m7:
        f7.append("--dry-run 竟然写了盘")
    # 同一组 ops 不给 `--allow-new-key` ⇒ 不带 create 的 kWarn 触发默认拒绝（rc=2）
    p7b = write("pc_5_7b.xwl", _page())
    rc7b, _o7b = _patch(p7b, "pc_5_7b_ops.json",
                        [{"op": "set", "path": ["kCreate"], "value": "v", "create": True},
                         {"op": "set", "path": ["kWarn"], "value": "v"}], dry_run=True)
    if rc7b != 2:
        f7.append("dry-run 不给 --allow-new-key 时 rc=%d（应 2）" % rc7b)
    _ok("5-7", f7, "--dry-run 下 [new-key]（只列带 create）与 [warn]（逃生开关放行的那批）分列、"
                   "不写盘；不给开关则 rc=2")

    # ---- `itemids --suggest` 产出逐条带 create:true，且能原样跑通 patch ----
    p8 = write("pc_5_8.xwl", _page(children=dup_children))
    rc8, o8 = _run(xwl.cmd_itemids, file=p8, name=None, dups_only=False, suggest=True,
                   fix="auto", controls=None, json=False)
    f8 = []
    ops8 = None
    if rc8 != 0:
        f8.append("itemids --suggest rc=%d" % rc8)
    else:
        try:
            ops8 = json.loads(o8)
        except ValueError as exc:
            f8.append("--suggest 产出不是合法 JSON：%s" % exc)
    if isinstance(ops8, list):
        if not ops8:
            f8.append("--suggest 未产出 ops（缺 warn/error 组？）")
        elif not all(isinstance(x, dict) and x.get("create") is True for x in ops8):
            f8.append("--suggest 产出未逐条带 create:true：%r" % ops8)
        else:
            p8b = write("pc_5_8_patch.xwl", _page(children=dup_children))
            rc8b, o8b = _patch(p8b, "pc_5_8_ops.json", ops8)
            if rc8b != 0:
                f8.append("--suggest 产出真跑 patch rc=%d（应 0 = 生成器/执行器不脱钩）:\n%s"
                          % (rc8b, o8b))
    _ok("5-8", f8, "itemids --suggest 产出逐条带 create:true 且能原样跑通 patch（rc=0）")

    # ---- `itemids --name --json` 产出也带 `create:true` ----
    rc9, o9 = _run(xwl.cmd_itemids, file=p8, name="dp", dups_only=False, suggest=False,
                   fix="auto", controls=None, json=True)
    f9 = []
    if rc9 != 0:
        f9.append("itemids --name --json rc=%d" % rc9)
    else:
        try:
            j9 = json.loads(o9)
        except ValueError as exc:
            f9.append("--name --json 不是合法 JSON：%s" % exc)
            j9 = None
        if isinstance(j9, list):
            if not j9 or not all(isinstance(x, dict) and x.get("create") is True for x in j9):
                f9.append("--name --json 候选未带 create:true：%r" % j9)
    _ok("5-9", f9, "itemids --name --json 每条候选带 create:true")

    # ---- 既有调用不回归（`apply_ops(tree, ops)` 签名兼容 + 已存在键不误报）----
    t10 = {"children": [{"configs": {"itemId": "s", "url": "a"}}]}
    w10: list = []
    xwl.apply_ops(t10, [{"op": "set", "path": ["children", 0, "configs", "url"], "value": "z"}],
                  created=[], warned=w10)
    f10 = []
    if t10["children"][0]["configs"]["url"] != "z":
        f10.append("既有调用（set 已存在键）没改对")
    if w10:
        f10.append("既有调用（set 已存在键）误报新建：%r" % w10)
    _ok("5-10", f10, "既有 apply_ops(tree, ops) 调用不回归（签名兼容 + 已存在键不误报）；"
                     "本文件 586/599/607/620 与 970-987 由前置用例一并覆盖")

    # ---- 真跑且无 --dry-run / --backup ⇒ 恰打一行「没备份」[warn]，rc 不变 ----
    p11 = write("pc_5_11.xwl", _page())
    rc11, o11 = _patch(p11, "pc_5_11_ops.json", [{"op": "set", "path": ["title"], "value": "t2"}])
    l1 = [ln for ln in o11.splitlines() if "未使用 --backup" in ln]
    p11b = write("pc_5_11b.xwl", _page())
    _rcb, ob = _patch(p11b, "pc_5_11b_ops.json", [{"op": "set", "path": ["title"], "value": "t2"}],
                      backup=True)
    p11c = write("pc_5_11c.xwl", _page())
    _rcc, oc = _patch(p11c, "pc_5_11c_ops.json", [{"op": "set", "path": ["title"], "value": "t2"}],
                      dry_run=True)
    f11 = []
    if rc11 != 0 or len(l1) != 1:
        f11.append("真跑无 --backup：rc=%d，该行 %d 条（应 1）" % (rc11, len(l1)))
    if "未使用 --backup" in ob:
        f11.append("带 --backup 却打了「没备份」[warn]")
    if "未使用 --backup" in oc:
        f11.append("--dry-run 却打了「没备份」[warn]")
    _ok("5-11", f11, "真跑且无 --dry-run/--backup ⇒ 恰一行「没备份」[warn]，rc 不变")

    # ---- --dry-run 对单行源打一行摘要；多行源仍逐行 diff ----
    single = ('{"hidden":false,"children":[],"roles":{},"title":"t",'
              '"iconCls":"","inframe":"","pageLink":""}')
    p12s = write("pc_5_12_single.xwl", single)
    rc12s, o12s = _patch(p12s, "pc_5_12s_ops.json",
                         [{"op": "set", "path": ["title"], "value": "T"}], dry_run=True)
    n12s = sum(1 for ln in o12s.splitlines() if ln.startswith("  "))
    p12m = write("pc_5_12_multi.xwl", _page())
    rc12m, o12m = _patch(p12m, "pc_5_12m_ops.json",
                         [{"op": "set", "path": ["title"], "value": "T"}], dry_run=True)
    n12m = sum(1 for ln in o12m.splitlines() if ln.startswith("  "))
    f12 = []
    if rc12s != 0 or rc12m != 0:
        f12.append("dry-run rc=%d/%d（应 0/0）" % (rc12s, rc12m))
    if n12s != 1:
        f12.append("单行源 diff 段落行数 = %d（应 1 = 一行摘要）" % n12s)
    if n12m <= 1:
        f12.append("多行源 diff 段落行数 = %d（应 >1 = 逐行 diff）" % n12m)
    _ok("5-12", f12, "单行源打一行摘要、多行源仍逐行 diff（判据 = diff 段落行数）")

    # ---- `#54`：`--dry-run` **不再按 40 行截断** ⇒ 大 diff 也全量（无「（略）」、段落 >40 行）----
    _big = [{"configs": {"itemId": "bb%d" % i, "text": "x"}, "type": "button",
             "expanded": False, "children": []} for i in range(30)]
    _big2 = [{"configs": {"itemId": "bb%d" % i, "text": "y"}, "type": "button",
              "expanded": False, "children": []} for i in range(30)]
    p12b = write("pc_5_12b.xwl", _page(children=_big))
    rc12b, o12b = _patch(p12b, "pc_5_12b_ops.json",
                         [{"op": "set", "path": ["children"], "value": _big2}], dry_run=True)
    _n12b = sum(1 for ln in o12b.splitlines() if ln.startswith("  "))
    # `#54`：**行宽也不静默截断** —— 超长单行须**整行**出现在 diff 里（原 `line[:200]` 会砍）。
    _long54 = "L" * 300
    p12c = write("pc_5_12c.xwl", _page())
    rc12c, o12c = _patch(p12c, "pc_5_12c_ops.json",
                         [{"op": "set", "path": ["title"], "value": _long54}], dry_run=True)
    f12b = []
    if rc12b != 0:
        f12b.append("大 diff 的 --dry-run rc=%d（应 0）" % rc12b)
    if "（略）" in o12b:
        f12b.append("`--dry-run` 仍截断 diff（出现「（略）」）—— `#54` 未生效")
    if _n12b <= 40:
        f12b.append("大 diff 段落行数 = %d（应 >40 = 未截断）" % _n12b)
    if rc12c != 0:
        f12b.append("超长值 dry-run rc=%d（应 0）" % rc12c)
    if _long54 not in o12c:
        f12b.append("`#54`：超长单行（%d 字符）未整行出现 ⇒ 行宽被静默截断" % len(_long54))
    _ok("5-12b", f12b, "`--dry-run` 不截断：大 diff 全量（无「（略）」、段落 >40 行）＋ 超长单行整行出现")

    # ---- `set` 末段数组下标越界 ⇒ rc=2 ----
    f13 = []
    try:
        xwl.apply_ops({"children": [1, 2, 3]}, [{"op": "set", "path": ["children", 99], "value": 0}])
        f13.append("set 末段数组下标越界未报错")
    except ValueError as exc:
        s13 = str(exc)
        if "合法区间" not in s13:
            f13.append("报错缺合法区间：%s" % s13)
        if "IndexError" in s13:
            f13.append("冒了 IndexError 字样：%s" % s13)
    except Exception as exc:  # noqa: BLE001 —— 非 ValueError 即不符契约
        f13.append("抛了非 ValueError：%r" % exc)
    p13 = write("pc_5_13.xwl", _page(children=dup_children))
    rc13, o13 = _patch(p13, "pc_5_13_ops.json",
                       [{"op": "set", "path": ["children", 99], "value": {"type": "panel"}}])
    if rc13 != 2:
        f13.append("cmd_patch rc=%d（应 2）" % rc13)
    if "合法区间" not in o13:
        f13.append("cmd_patch 报错未走 **统一模板**（缺合法区间）:\n%s" % o13)
    _ok("5-13", f13, "set 末段数组下标越界 ⇒ ValueError + rc=2，走 **统一模板**（非裸 IndexError）")

    # ---- 数字形态估算只读有效对象正文的数字值 token，expand/patch 共用同一口径 ----
    numeric_source = (
        "999, 1e2; loader prefix\n"
        "{\n"
        '    "hidden": false,\n'
        '    "children": [],\n'
        '    "roles": {},\n'
        '    "title": "99 1.5 SELECT 2.0",\n'
        '    "iconCls": "1e2",\n'
        '    "inframe": "a (1.0) b",\n'
        '    "pageLink": "",\n'
        '    "numberForms": [1.00, -2.50, 1e2, 3, 3]\n'
        "}\n"
    )
    p14e = write("pc_5_14_expand.xwl", numeric_source)
    rc14e, o14e = _run(xwl.cmd_expand, file=p14e, eol="auto", indent=1, safe=False,
                       dry_run=False, out=None, backup=False, node=None, no_js=True)
    p14p = write("pc_5_14_patch.xwl", numeric_source)
    rc14p, o14p = _patch(p14p, "pc_5_14_ops.json",
                         [{"op": "set", "path": ["title"], "value": "changed"}], dry_run=True)
    f14: list[str] = []
    pat14 = re.compile(
        r"数字形态 (\d+) 处（估算；0 仅表示本方向多重集无差异）")
    for who14, rc14, out14 in (("expand", rc14e, o14e), ("patch", rc14p, o14p)):
        m14 = pat14.search(out14)
        if rc14 != 0:
            f14.append("%s rc=%d（应 0）" % (who14, rc14))
        if not m14:
            f14.append("%s 未给出数字形态估算边界说明" % who14)
        elif int(m14.group(1)) != 3:
            f14.append("%s 数字形态估算 = %s（应 3；字符串与前导文本不得污染）"
                       % (who14, m14.group(1)))
    _ci14, _cu14, _cn14 = xwl.rewrite_counts(
        '{"first": 1, "second": 2}', '{"first": 2, "second": 1}')
    if (_ci14, _cu14, _cn14) != (0, 0, 0):
        f14.append("位置互换的多重集差应为 (0,0,0)，实得 %r" % ((_ci14, _cu14, _cn14),))
    _ok("5-14", f14,
        "expand/patch 数字形态=3：字符串、SQL/JS、转义及前导文本不计数；位置互换方向差=0")

    if pc_fail:
        failures.extend(pc_fail)

