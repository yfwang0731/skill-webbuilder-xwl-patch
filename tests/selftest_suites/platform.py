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

def _check_platform(tmp, node, failures, write) -> None:
    """node_check_many 等价性 + folders 给目录须报错 + 非 UTF-8 控制台 + 跨盘符 relpath（第 19~22 组）"""

    # ---- 19. node_check_many 必须与逐段 node_check 等价（性能优化不许改变结论）----
    # 背景：把逐段 `node --check` 改成一次进程批量校验，避免每个事件段各付一次 node 启动开销。
    # 但这个优化踩过两次坑，所以用「与权威路径逐项对照」把它钉住：
    #   ① `vm.Script` 按**脚本**编译，顶层 return 非法；而 `node --check <x.js>` 按 **CommonJS** 编译，合法
    #      ⇒ 误报 104 项（一个页面 16 → 120）。
    #   ② Node 22 的 `--check` 在 CJS 解析失败时会自动按 **ESM** 重试，因此接受顶层 await；
    #      批量驱动不会 ⇒ 又一处误报。
    # 结论：批量只能用来证明「合法」，报错的必须回 node_check 复核。下面就是守这条。
    node_bin = xwl.find_node(None)
    if node_bin:
        cases = [
            ("合法语句", "var a = 1; app.log(a);"),
            ("顶层 return（CJS 合法）", "if (!app.grid1) { return; }\napp.grid1.reload();"),
            ("顶层 await（--check 按 ESM 重试后合法）", "await foo();"),
            ("tagEvents 对象字面量", '{"beforeedit": function(e){ e.value = 1; }}'),
            ("tagEvents 对象-语法错", '{"beforeedit": function(e){ e.value = ; }}'),
            ("括号不闭合", "app.log(1;"),
            ("空串", ""),
        ]
        codes = [c for _n, c in cases]
        got = xwl.node_check_many(node_bin, codes)
        want = [xwl.node_check(node_bin, c) for c in codes]
        diff = [cases[i][0] for i in range(len(cases)) if got[i][0] != want[i][0]]
        if len(got) != len(codes):
            failures.append("node_check_many 返回条数与输入不符：%d vs %d" % (len(got), len(codes)))
        elif diff:
            failures.append("node_check_many 与逐段 node_check 结论不一致：%s" % diff)
        else:
            print("[ok]  node_check_many 与逐段 node_check 逐项等价（%d 例，含顶层 return / await 语义差异）"
                  % len(cases))
        # 批量必须真的快：空输入与规模输入都不能退化
        got2 = xwl.node_check_many(node_bin, [])
        if got2 != []:
            failures.append("node_check_many 对空输入应返回空列表")
        if REQUIRE_ALL:
            _mark_sub(_SUBCHECKS, "js.node_check_many", "通过", "node_check_many 已执行")
    else:
        print("[note] 未找到 node，跳过 node_check_many 等价性断言")
        if REQUIRE_ALL:
            _mark_sub(_SUBCHECKS, "js.node_check_many", "未完成", "未找到 node，JS 等价性断言未跑")

    # ---- 20. folders：给目录 + --register 必须显式报错（曾是静默无效）----
    # 起因：cmd_folders 在 isdir 分支里**直接忽略** --register，只做只读扫描并以 0 退出 ——
    # 用户以为登记成功了，其实什么都没发生。这类"静默无效"必须钉住。
    r_fail: list[str] = []
    rd = os.path.join(tmp, "folder_regdir")
    os.makedirs(rd, exist_ok=True)
    rfj = os.path.join(rd, "folder.json")
    rtxt = '{"hidden":false,"index":[],"title":"样本目录","iconCls":""}'
    with open(rfj, "w", encoding="utf-8", newline="") as f:
        f.write(rtxt)
    with open(os.path.join(rd, "c.xwl"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    code, out = _run(xwl.cmd_folders, path=rd, register="c.xwl", dry_run=False)
    if code != 2:
        r_fail.append("folders <目录> --register 应返回 2（明确报错），实际 %s" % code)
    if open(rfj, "r", encoding="utf-8", newline="").read() != rtxt:
        r_fail.append("folders <目录> --register 竟然改了 folder.json（应拒绝且不动文件）")
    if r_fail:
        failures.extend(r_fail)
    else:
        print("[ok]  folders <目录> --register 显式报错且不动 folder.json（原为静默忽略）")

    # ---- 21. 非 UTF-8 控制台下不能崩（回归守卫）----
    # 本工具的输出**全是中文**，而 Windows 上 Python 标准流默认跟随控制台代码页：
    # 实测 GitHub 的 windows-latest runner 是 **cp1252**，一 print 中文就
    # UnicodeEncodeError 崩掉（而且崩在第一行输出）。ubuntu / git-bash 都是 UTF-8，
    # 本地开发环境（含本仓工作区）也是 UTF-8 ⇒ **这个坑只在 Windows 上炸，极易漏**。
    # 第一次上 CI 就是这么挂的（ubuntu 4 格全绿、windows 2 格红）。
    # 用子进程钉住，本地也能跑到，不必等 CI 反馈。
    e_fail: list[str] = []
    env_cp = dict(os.environ)
    env_cp["PYTHONIOENCODING"] = "cp1252"
    xwl_py = os.path.join(SKILL_ROOT, "scripts", "xwl.py")
    for args in (["--help"], ["check", "--help"], ["folders", "--help"]):
        try:
            pr = _cap_run([sys.executable, xwl_py] + args, env=env_cp, timeout=90,
                          binary=True)
        except Exception as exc:  # noqa: BLE001
            e_fail.append("PYTHONIOENCODING=cp1252 下跑 `xwl.py %s` 抛异常：%s"
                          % (" ".join(args), exc))
            continue
        if pr.returncode != 0:
            tail = (pr.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            e_fail.append("PYTHONIOENCODING=cp1252 下 `xwl.py %s` 退出 %s：%s"
                          % (" ".join(args), pr.returncode,
                             (tail[-1] if tail else "")[:80]))
    if e_fail:
        failures.extend(e_fail)
    else:
        print("[ok]  非 UTF-8 控制台（cp1252）下输出中文不崩（UTF-8 输出回归守卫）")

    # ---- 22. 跨盘符不能崩：os.path.relpath 不带 start 时跨盘符会抛 ValueError ----
    # 实测 GitHub 的 windows runner：仓库签出在 `D:\a\...`、TEMP 在 `C:\...` ⇒
    # `os.path.relpath(target)`（以 cwd 为基准）直接抛
    # `ValueError: path is on mount 'C:', start on mount 'D:'`，
    # 把一句"提示用户怎么登记"的 print 变成了致命错误（第二次 CI 就挂在它上面）。
    # 相对路径在这里只是给人看的，拿不到就该退回绝对路径 —— 用桩把 relpath 变成必抛，
    # 验证 safe_relpath 的兜底真的接住了（而不是"恰好没触发"）。
    rp_fail: list[str] = []
    rd2 = os.path.join(tmp, "relpath_case")
    os.makedirs(rd2, exist_ok=True)
    with open(os.path.join(rd2, "folder.json"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"index":[],"title":"样本目录","iconCls":""}')
    with open(os.path.join(rd2, "d.xwl"), "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    real_relpath = os.path.relpath

    def _boom(*_a, **_k):
        raise ValueError("path is on mount 'C:', start on mount 'D:'")

    os.path.relpath = _boom
    try:
        for label, kw in (("只读扫描", dict(path=rd2, register=None, dry_run=False)),
                          ("登记", dict(path=os.path.join(rd2, "d.xwl"),
                                       register="d.xwl", dry_run=True))):
            try:
                _run(xwl.cmd_folders, **kw)
            except Exception as exc:  # noqa: BLE001
                rp_fail.append("relpath 抛 ValueError 时 cmd_folders(%s) 跟着崩：%s: %s"
                               % (label, type(exc).__name__, exc))
        got = xwl.safe_relpath("C:\\a\\b.xwl", "D:\\c")
        if not (isinstance(got, str) and got):
            rp_fail.append("safe_relpath 兜底未返回可用字符串：%r" % (got,))
    finally:
        os.path.relpath = real_relpath
    if rp_fail:
        failures.extend(rp_fail)
    else:
        print("[ok]  跨盘符 relpath 抛错时 folders 不崩（safe_relpath 兜底，Windows CI 实测场景）")

