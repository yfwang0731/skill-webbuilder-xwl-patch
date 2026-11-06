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

def _check_diffguard(tmp, node, failures, write) -> None:
    """`diffguard` 相对 git 基线检测「多行被压平」（第 26 组）。

    这个能力补的是 §2.3 承认的那个洞：把「反斜杠 + 换行」直接删掉之后
    文件**依然是合法 JSON**，`check` 全绿、`node --check` 还可能返回 0 ——
    靠人工读 `git diff` 去找这种损坏，规模一大就找不过来。

    判据为什么不能只看计数（这里正反两侧都钉住）：
      · 只看"续行符变少" ⇒ 合法地删掉一段多行 JS / 删一个控件也会净减少 ⇒ **必然误报**；
      · 主判据是**定义级**的：工作区某行 == 基线连续多行去掉续行符后的拼接，且**只认新发生的合并**
        （续行组涉及基线变更行 ＋ 工作区出现次数多于基线）；「续行符净减少 且 最长行显著变长」只是**粗筛**。
      · 但净计数也不能当**否决**：别处新增续行会把净计数抵消，真压平反而不报（"补偿式压平"）。
    所以「压平必须报」与「合法删减 / 内容移动 / 极短行巧合必须不报」同等重要，缺一条这个能力就没法用。
    """
    print("[26] diffguard（相对 git 基线的压平检测）")
    xwl_py = os.path.join(SKILL_ROOT, "scripts", "xwl.py")
    repo = os.path.join(tmp, "dg_repo")
    os.makedirs(repo, exist_ok=True)
    BS = chr(92)

    # ⑩ **超时降级：有界返回、不许挂死**（四态里唯一没有常驻用例的那一态）。
    #   ⚠️ **必须放在本块最前面**：下面建 git 夹具时有两处 `return`（建库超时 / 建库失败），
    #     放在函数末尾的话，那两条路径会让本臂**根本不执行**，而块内其余断言仍可能全绿 ⇒ 看着"过了"。
    #     本臂只依赖 `_cap_run` 与 `_git_show_batch`、**不需要一个可用的仓库** ⇒ 前置无害。
    #   起因（不这么做会漏什么）：`_cap_run` 弃用 `capture_output` 的全部理由就是"管道下等 EOF
    #     永不返回" —— 但那条结论只有一次性脚本验过；用例一旦缺失，把实现改回 `capture_output`
    #     也能全绿（"杀了 ≠ 守住了"）。
    #   ⚠️ 阈值取**毫秒级**（0.001s）：真跑满 60s 才验到一次超时的用例没人会留着。
    dg: list[str] = []
    import time as _time       # 本块专用：量"是否按时返回"（模块头无 time，就近引入）
    _t0 = _time.monotonic()
    _to = xwl._cap_run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.001)
    _el = _time.monotonic() - _t0
    if not _to.timed_out:
        dg.append("超时降级：1ms 阈值下 `_cap_run` 没标 `timed_out`（退化成无界等待 ⇒ 会挂死）")
    if "[TIMEOUT]" not in (_to.stderr or ""):
        dg.append("超时降级：`_cap_run` 超时后没在 stderr 写 [TIMEOUT]（静默降级 —— "
                  "用户分不清「超时」与「跑完了但失败」）")
    if _el > 2:
        dg.append("超时降级：1ms 阈值却耗时 %.1fs —— 超时没生效（子进程被真跑满）" % _el)
    #    diffguard 自己那条路径：只钉「**不能静默**」，⛔ 不钉「必须是超时」。
    #    ⚠️ 为什么不能钉分支：1ms 阈值下走哪一支**取决于机器** —— Windows 上 git 起进程 > 1ms ⇒ 必超时；
    #      Linux 上 `cat-file` 在非仓库里**秒退**（rc≠0、stdout 空）⇒ 拿到的是「输出不可解析」。
    #      钉"必须超时"＝**断言一个竞态**：档 2 在 ubuntu 上 5 个 job 全红就是它（本机 Windows 全绿）。
    #      ⇒ 只要 `why` 落在闭集里且**不是 None**，就说明"没比成"被**显式说出来了**，这正是本臂要保的。
    #      "拆掉 timeout 会不会漏"由上面 `_cap_run` 那两条钉住（同一机制、且完全确定性）。
    _bres, _bwhy, _bdone = xwl._git_show_batch("HEAD", ["dg.xwl"], repo, timeout=0.001)
    if _bwhy is None:
        dg.append("超时降级：`_git_show_batch` 在 1ms 阈值下没给 `why`（超时被当成「正常取到」⇒ "
                  "diffguard 会把「没比成」读成「没改动」）")
    elif not ("超时" in _bwhy or "不可解析" in _bwhy or "调不到 git" in _bwhy):
        dg.append("超时降级：`_git_show_batch` 的降级原因不在闭集里（why=%r）" % _bwhy)

    def _git(*a):
        return _cap_run(["git", *a], cwd=repo, timeout=120)

    def _cli(*a, cwd=None):
        pr = _cap_run([sys.executable, xwl_py, *a], cwd=cwd or repo, timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    def _mk(name, text):
        p = os.path.join(repo, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    SRC = "\r\n".join([
        "{", ' "hidden": false,', ' "children": [{',
        '  "configs": {"itemId": "SELFTEST_BTN", "text": "SELFTEST_T"},',
        '  "expanded": false,', '  "children": [],', '  "type": "button",',
        '  "events": {', '   "click": "var rec = app.g.getSelection()[0];' + BS,
        "if (!rec) { Wb.info('pick one'); return; }" + BS,
        "Wb.requestAg({ params: { bean: 'b', method: 'm' } });" + BS,
        'Wb.info(\'done\');"',
        '  }', ' }],',
        ' "roles": {"default": 1},',
        ' "title": "SELFTEST_T", "iconCls": "", "inframe": false, "pageLink": ""', '}'])

    # 只起必要的 git 进程：身份用 `-c` 内联（省 2 次 `git config`）、仓库是否建起来由
    # 首次 commit 的 returncode 判定（省 1 次 `git rev-parse`）；已跟踪文件的改动一律用
    # `commit -am` 一条收口（省 `git add`）。基线内容另用变量 `BASE` 跟踪，恢复基线直接
    # `_mk` 写回（省掉 8 次 `git checkout -- dg.xwl`）—— 语义等价：`checkout` 本来也只是
    # 把文件恢复成基线内容。
    GIT_ID = ("-c", "user.email=selftest@local", "-c", "user.name=selftest")
    # ⭐ `_git` 的超时**显式收口**（起因：本批给 `_git` 加了 `timeout=120` 后，超时 ⇒ `returncode`
    #   为 `None`，会被下面那条 `!= 0` 判**误读成「无法建立仓库」**并**静默跳过 ⇒ 整块判绿**）。
    #   ⇒ 建库三步（`init`/`add`/`commit`）任一 `timed_out` ⇒ **显式判红**（与「无法建立仓库」区分开）。
    _g_init = _git("init", "-q")
    _mk("dg.xwl", SRC)                          # 新文件 ⇒ 首次入库仍须 `git add`
    _g_add = _git("add", "-A")
    _g_commit = _git(*GIT_ID, "commit", "-q", "-m", "base")
    if _g_init.timed_out or _g_add.timed_out or _g_commit.timed_out:
        failures.append("diffguard 夹具：`git` 调用超时（已终止，timeout=120s）—— "
                        "≠「无法建立临时 git 仓库」；超时**不得静默跳过**"
                        "（diffguard 断言未执行 ⇒ 判红）")
        if dg:      # ⑩ 不依赖仓库：已经拿到的结论必须带走，⛔ 别跟着一起丢
            failures.extend(dg)
        return
    if _g_commit.returncode != 0:
        print("[note] 无法建立临时 git 仓库，跳过 diffguard 断言")
        # ⚠️ 这条 `return` 是"整块跳过"的**出口**：⑩ 超时臂不依赖仓库，它的结论必须在这里带走，
        #   否则"建库失败 ＋ 超时判据真的坏了"会表现成一句无害的 [note]（静默降级）。
        if dg:
            failures.extend(dg)
        return
    BASE = SRC                                  # dg.xwl 的当前基线（= 最近一次提交的内容）

    # `dg` 已在函数开头初始化（⑩ 超时臂先跑）—— ⛔ 别在这里再 `dg = []`，那会把 ⑩ 的结论清掉。

    def _flat(s):
        return s.replace(BS + "\r\n", "")

    def _build(js_first, js_rest):
        """按**物理行**拼一份文件：续行符必须紧贴 CRLF（写成 BS+'\\n' 是无效夹具）。"""
        return "\r\n".join([
            "{", ' "hidden": false,', ' "children": [{',
            '  "configs": {"itemId": "SELFTEST_BTN", "text": "SELFTEST_T"},',
            '  "expanded": false,', '  "children": [],', '  "type": "button",',
            '  "events": {', '   "click": "' + js_first + BS]
            + [x + BS for x in js_rest]
            + ['Wb.info(\'done\');"', '  }', ' }],', ' "roles": {"default": 1},',
               ' "title": "SELFTEST_T", "iconCls": "", "inframe": false, "pageLink": ""', '}'])

    # ① 未改动 → 不能报
    rc, out = _cli("diffguard", "dg.xwl")
    if rc != 0 or "[warn]" in out:
        dg.append("diffguard 对未改动文件应 rc=0 且无告警（rc=%s）" % rc)

    # ② 压平（删掉续行符把 4 行挤成 1 行）→ 必须报；默认 rc=0，--strict 下 rc=1
    _mk("dg.xwl", _flat(SRC))
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" not in out or "压平" not in out:
        dg.append("diffguard 没报出被压平的文件（反向退化 ⇒ 这个能力等于没有）")
    if rc != 0:
        dg.append("diffguard 默认应只告警（rc=0），实得 rc=%s" % rc)
    rc, out = _cli("diffguard", "dg.xwl", "--strict")
    if rc != 1:
        dg.append("diffguard --strict 下疑似压平应 rc=1，实得 rc=%s" % rc)

    # ③ 反面对照：合法删掉两行多行 JS → 续行符也净减少，但**不得**报（否则天天误报）
    _mk("dg.xwl", BASE)
    lines = SRC.split("\r\n")
    del lines[9]
    del lines[9]
    _mk("dg.xwl", "\r\n".join(lines))
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" in out:
        dg.append("diffguard 把「合法删除一段多行 JS」误报成压平（续行符净减少≠压平）")
    if rc != 0:
        dg.append("diffguard 对合法删减应 rc=0，实得 rc=%s" % rc)

    # ④ 反面对照：只在同一行里加长内容（续行符不变）→ 不得报
    _mk("dg.xwl", BASE)
    _mk("dg.xwl", SRC.replace('"title": "SELFTEST_T"', '"title": "' + "X" * 300 + '"'))
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" in out:
        dg.append("diffguard 把「单行变长但没删续行符」误报成压平")

    # ④b **精确判据必须补上的两个漏报面**（旧的双条件判据在这里全都漏）
    #     · 短内容压平：合并后仍比文件里已有的最长行短 ⇒ 最长行纹丝不动
    #     · 文件本就有超长行：ratio 门槛把增量吃掉
    for label, first, rest in (
        ("短内容压平（最长行不变）", "var a = 1;", ["var b = 2;", "var c = 3;"]),
        ("已有超长行 + 并入 3 行", "var z = '" + "y" * 180 + "';", ["q = 1;", "r = 2;"]),
    ):
        short = _build(first, rest)
        _mk("dg.xwl", short)
        _git(*GIT_ID, "commit", "-q", "-am", "short")
        BASE = short
        new = _flat(short)
        if new == short:
            dg.append("夹具无效：%s 的变异没改变文件" % label)
            continue
        _mk("dg.xwl", new)
        rc, out = _cli("diffguard", "dg.xwl", "--strict")
        if "[warn]" not in out:
            dg.append("diffguard 漏报「%s」（精确判据没生效，退回了只认最长行）" % label)
        elif "精确命中" not in out:
            dg.append("diffguard 报「%s」时没标出是精确命中" % label)
        if rc != 1:
            dg.append("「%s」--strict 下应 rc=1，实得 %s" % (label, rc))
        _mk("dg.xwl", BASE)

    # ④c **行号落点必须真实**（起因 diffguard 行号落 0）：精确判据报出的「工作区第 N 行」必须是**真实物理行号**、
    #     不是取不到键时兜底的哨兵 0。夹具＝「基线两行续行 → 工作区把它们并成**一行且带尾随空白**」，
    #     此时命中只能靠 rstrip 匹配（工作区那一行不在原始行表里），行号表若只按原始行建就会落 0。
    #     修法（`_merged_line_hits`）：raw 命中查 raw 表、rstrip 命中查 rstrip 表 ⇒ 行号恒真实。
    _mk("dg.xwl", BASE)
    _a7a_base = "aa " + BS + "\r\n" + "bb"          # 基线：第 1 行续行、第 2 行普通
    _mk("dg.xwl", _a7a_base)
    _git(*GIT_ID, "commit", "-q", "-am", "a7a")
    BASE = _a7a_base
    _mk("dg.xwl", "aa bb ")                          # 工作区：并成一行，且该行带尾随空白
    _a7a: list[str] = []
    _rc, _out = _cli("diffguard", "dg.xwl")
    if "被合并成" not in _out:
        _a7a.append("合并行号：续行被并成一行（带尾随空白）时应精确命中合并位置，实得无「被合并成」行")
    if "第 0 行" in _out:
        _a7a.append("合并行号：合并后的工作区行号落到了哨兵 0 —— 行号表与命中判定用了两张不同的键"
                    "（raw 建表、rstrip 查表），rstrip 命中时取不到行号")
    elif "工作区第 1 行" not in _out:
        _a7a.append("合并行号：合并后的工作区行号应为真实物理行 1，实得其它行号")
    _mk("dg.xwl", BASE)
    if _a7a:
        dg.extend(_a7a)
    else:
        print("[ok]  合并行号：续行被并成一行（带尾随空白）时，报出的工作区行号为真实物理行 1（非哨兵 0）")

    # ⑤ 正常走一遍 patch 之后不得报（否则这个守卫会被日常改动淹没）
    #    ⚠️ 夹具必须是**可 patch 的合法 xwl**：④c 留下的裸文本夹具会让 patch 直接失败，
    #       那样"patch 后不误报"就成了空断言（patch 根本没成功也能绿）⇒ 先恢复 SRC 并入库再 patch。
    _mk("dg.xwl", SRC)
    _git(*GIT_ID, "commit", "-q", "-am", "patch-base")
    BASE = SRC
    ops = os.path.join(repo, "dg_ops.json")
    with open(ops, "w", encoding="utf-8") as fh:
        fh.write('[{"op":"append","path":["children",0,"children"],"value":'
                 '{"configs":{"itemId":"dgNew","text":"新"},"expanded":false,'
                 '"children":[],"type":"button","events":{"click":"Wb.info(1);"}}}]')
    _prc, _pout = _cli("patch", "dg.xwl", "--ops", "dg_ops.json", "--backup")
    if _prc != 0:
        dg.append("夹具：正常 patch 没有成功（rc=%s）—— 「patch 后不误报」会退化成空断言" % _prc)
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" in out:
        dg.append("diffguard 把正常的 patch 改动误报成压平")

    # ⑥ 降级：新文件（不在基线里）→ note 跳过、rc=0；**全部跳过**时 --strict 必须 rc=2
    _mk("dg_fresh.xwl", SRC)
    rc, out = _cli("diffguard", "dg_fresh.xwl")
    if rc != 0 or "跳过" not in out:
        dg.append("diffguard 对新文件应提示跳过且 rc=0（rc=%s）" % rc)
    rc, out = _cli("diffguard", "dg_fresh.xwl", "--strict")
    if rc != 2:
        dg.append("diffguard --strict 下一个文件都没比成时应 rc=2（实得 %s）" % rc)

    # ⑥b 退出码优先级：**可疑压平 > 跳过**（否则带新增文件的 CI 会永远红）
    big = _build("var rec = app.g.getSelection()[0];",
                 ["if (!rec) { Wb.info('pick'); return; }",
                  "Wb.requestAg({ params: { bean: 'b', method: 'm', id: rec.data.ID } });"])
    _mk("dg.xwl", big)
    _git(*GIT_ID, "commit", "-q", "-am", "prio")
    BASE = big
    _mk("dg.xwl", _flat(big))
    _mk("dg_fresh2.xwl", SRC)
    rc, out = _cli("diffguard", "dg.xwl", "dg_fresh2.xwl", "--strict")
    if rc != 1:
        dg.append("同时有可疑压平与跳过项时 --strict 应 rc=1（可疑优先），实得 %s" % rc)

    # ⑦ --rev 写错是用法错 → rc=2（且不得被说成"新增文件"）
    rc, out = _cli("diffguard", "dg.xwl", "--rev", "no-such-ref")
    if rc != 2 or "不存在" not in out:
        dg.append("diffguard 对不存在的 --rev 应 rc=2 并明说基线不存在（rc=%s）" % rc)

    # ⑧ 不在 git 仓库里 → 跳过而不是崩
    nogit = os.path.join(tmp, "dg_nogit")
    os.makedirs(nogit, exist_ok=True)
    with open(os.path.join(nogit, "n.xwl"), "w", encoding="utf-8", newline="") as fh:
        fh.write(SRC)
    rc, out = _cli("diffguard", "n.xwl", cwd=nogit)
    if rc != 0 or "跳过" not in out or "Traceback" in out:
        dg.append("diffguard 在非 git 目录应提示跳过、rc=0、不冒 traceback（rc=%s）" % rc)

    # ⑨ **cwd 的另一种写法**（Windows 8.3 短名 ↔ 长名）下必须仍能比对。
    #     这一条补的是一个真实事故：`windows-latest` 上 diffguard 整组 8 项 FAIL、
    #     ubuntu 全绿。根因是 rel 由 `os.path.relpath(abspath(path), toplevel)` 反推 ——
    #     CI 的 `TEMP` 是短名（`C:\Users\RUNNER~1\…`），而 git 把仓库根归一成长名，
    #     前缀对不上时 relpath 给出 `..\..\XWL_SH~1\…`，被 `_git_show` 当成"路径逃逸"
    #     **静默跳过**（于是压平也不报、`--strict` 变成 rc=2、`--rev` 写错也只给 rc=0）。
    #     现在 rel 由 git 自报（`git rev-parse --show-prefix`），两种写法都必须命中。
    #     本机 repo 是长名 ⇒ 这里测短名；CI 上 repo 是短名 ⇒ 这里测长名。
    _mk("dg.xwl", BASE)
    _mk("dg.xwl", _flat(big))                   # `big` 已在 ⑥b 提交
    for _label, _api in (("短名", "GetShortPathNameW"), ("长名", "GetLongPathNameW")):
        _alt = _win_path(repo, _api)
        if not _alt or os.path.normcase(_alt) == os.path.normcase(os.path.abspath(repo)):
            continue
        _rc, _out = _cli("diffguard", "dg.xwl", cwd=_alt)
        if "[warn]" not in _out:
            dg.append("cwd 用%s写法（%s）时 diffguard 没报出压平 —— 相对路径只能由 git "
                      "自报（用 os.path.relpath 反推会在短名/盘符不同源时静默跳过）"
                      % (_label, _alt))

    # ---- 判据一「只认新发生的合并」：旧「内容移动」夹具重写为正例 ＋ 三种反误报 ----
    # 旧夹具（内容与基线相邻两行拼接相同、但续行符与行数都没减少 ⇒ 判"内容移动"不报）
    #   **正是本序要改的缺陷样本**：那两条基线行确实被并成了一行，只是工作区别处新增了续行符
    #   把净计数抵消掉了 ⇒ 「净计数否决」会漏报。现在它必须是**正例**（见 ④d）。

    # ④d **补偿式压平必报**：第 1–2 行确实被合并，但工作区别处**新增了续行符**
    #     ⇒ 续行符 1→1、行数 4→4，净计数完全抵消。净计数只作说明、**不是否决条件**。
    _mk("dg.xwl", BASE)
    _comp0 = 'MOvE_A' + BS + '\n"x"\nP\nQ'                 # 行数 4 / 续行符 1
    _mk("dg.xwl", _comp0)
    _git(*GIT_ID, "commit", "-q", "-am", "comp-flatten")
    BASE = _comp0
    _mk("dg.xwl", 'MOvE_A"x"' + "\nR" + BS + "\nS\nT")    # 行数 4 / 续行符 1（都没减少）
    _rc, _out = _cli("diffguard", "dg.xwl")
    if "[warn]" not in _out or "精确命中" not in _out:
        dg.append("补偿式压平（别处新增续行把净计数抵消）漏报 —— 净计数不得再当否决条件")
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if _rc != 1:
        dg.append("补偿式压平 --strict 下应 rc=1，实得 %s" % _rc)
    if "工作区第 1 行" not in _out:
        dg.append("补偿式压平应报出合并后的真实工作区行号 1")
    _mk("dg.xwl", BASE)

    # ④e **极短行拼接连巧**（反误报）：基线第 1–2 行本次未改，工作区另起一行恰好等于两者拼接
    #     ⇒ 不得报压平（`}` / `');'` 这类极短行在真语料上是天然误报源）。
    _coin0 = "AA" + BS + "\nBB\nP\nQ\nS" + BS + "\nT"
    _mk("dg.xwl", _coin0)
    _git(*GIT_ID, "commit", "-q", "-am", "short-coincidence")
    BASE = _coin0
    _mk("dg.xwl", "AA" + BS + "\nBB\nAABB\nP\nQ\nT")
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" in _out:
        dg.append("极短行拼接连巧（基线行本次未改）被误报成压平 —— 这类在真语料上会恒亮")
    if _rc != 0:
        dg.append("极短行拼接连巧 --strict 下应 rc=0，实得 %s" % _rc)
    if "本次未改" not in _out:
        dg.append("极短行拼接连巧应给 [note] 说明「基线行本次未改」，用户才知道为什么不告警")
    _mk("dg.xwl", BASE)

    # ④f **真实结构移动**（反误报）：多行块整体搬到别处，没有被压平 ⇒ 不得报。
    _mv0 = "H1" + BS + "\nH2\nP\nQ"
    _mk("dg.xwl", _mv0)
    _git(*GIT_ID, "commit", "-q", "-am", "real-move")
    BASE = _mv0
    _mk("dg.xwl", "P\nQ\nH1" + BS + "\nH2")
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" in _out:
        dg.append("真实结构移动（多行块整体搬家）被误报成压平")
    if _rc != 0:
        dg.append("真实结构移动 --strict 下应 rc=0，实得 %s" % _rc)
    _mk("dg.xwl", BASE)

    # ④g **多位置 ＋ 有界展示**：同一拼接文本在工作区出现 4 处 ⇒ 展开前 3 处 ＋「另有 1 处」；
    #     去重按 (起始, 结束, 工作区行)，⛔ 同一位置不重复刷屏。
    _ml0 = "MM" + BS + "\nNN\nZ"
    _mk("dg.xwl", _ml0)
    _git(*GIT_ID, "commit", "-q", "-am", "multi-position")
    BASE = _ml0
    _mk("dg.xwl", "MMNN\nMMNN\nMMNN\nMMNN\nZ")
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" not in _out:
        dg.append("多位置压平没有告警")
    if _out.count("被合并成") != 3 or "另有 1 处精确命中" not in _out:
        dg.append("多位置展示应有界：展开 3 处 ＋「另有 1 处精确命中」（实得 %d 处展开）"
                  % _out.count("被合并成"))
    if _rc != 1:
        dg.append("多位置压平 --strict 下应 rc=1，实得 %s" % _rc)
    _mk("dg.xwl", BASE)

    # ④h/④i **既有同文本行**（例如这段在更早的提交里已压平入库，基线里已有该拼接文本）：
    #     正例 —— 真压平 ＋ 基线已有同文本行 ⇒ 工作区**多出现**一处，仍必报；
    #     反例 —— 只改了组内一行、基线已有同文本行 ⇒ 工作区未多出现，不报（⛔ 不误报既有内容）。
    _ex0 = "AA" + BS + "\nBB\nZ\nAABB"
    _mk("dg.xwl", _ex0)
    _git(*GIT_ID, "commit", "-q", "-am", "existing-text")
    BASE = _ex0
    _mk("dg.xwl", "AABB\nZ\nAABB")                      # 第 1–2 行真被合并 ⇒ 新出现一处
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" not in _out or "精确命中" not in _out:
        dg.append("真压平且基线已有同文本行时漏报 —— 出现次数闸只应排除「没有多出来」的命中")
    if _rc != 1:
        dg.append("真压平 ＋ 基线已有同文本行 --strict 下应 rc=1，实得 %s" % _rc)
    _mk("dg.xwl", "AA2" + BS + "\nBB\nZ\nAABB")         # 只改组内一行，命中既有同文本行
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" in _out:
        dg.append("只改组内一行却命中了基线里的既有同文本行 ⇒ 被误报成压平")
    if _rc != 0:
        dg.append("既有同文本行、工作区未多出现时应 rc=0，实得 %s" % _rc)
    # 新口径：组内仍有行本次未改 ⇒ 不是新压平；`[note]` 要说明原因（R2 收口后文案）。
    if not any(k in _out for k in ("仍有行本次未改", "本次未改", "既有同文本行", "多出现")):
        dg.append("既有同文本行被排除时应给 [note] 说明原因（组内仍有行本次未改/命中既有行）")
    _mk("dg.xwl", BASE)

    # ④j **相似度档同受插入行闸约束**：新行与拼接高度相似（ratio 过阈值），但基线那组续行
    #     本次未改（或命中位置是既有行）⇒ 不得报（否则"在别处加一行像拼接的内容"也会被当成压平）。
    _sm0 = "SIM_ARG_1" + BS + "\nSIM_ARG_2\nZ"
    _mk("dg.xwl", _sm0)
    _git(*GIT_ID, "commit", "-q", "-am", "sim-changed")
    BASE = _sm0
    _mk("dg.xwl", "SIM_ARG_1" + BS + "\nSIM_ARG_2\nSIM_ARG_1SIM_ARG_2Q\nZ")
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" in _out:
        dg.append("相似度档没受基线变更行约束：基线组未改动也被判成压平")
    if _rc != 0:
        dg.append("相似度档 ＋ 基线行未改 --strict 下应 rc=0，实得 %s" % _rc)
    _mk("dg.xwl", BASE)

    # ④k/④l **R2 边界收口（只改组首/组尾＋别处多出同文本行 ⇒ 不得报）**：基线里已有同文本行，
    #     组内只有一行被改（组尾 / 组首），工作区又新增一处同文本行 —— 旧口径按"变更行闸＋出现次数
    #     闸"会放行，属**已登记误报**。新口径：组内**每一行**都须本次改过，且命中位置须是工作区新行
    #     （`difflib` `insert`/`replace` 产出）⇒ 这两种都不得报。
    _r2a = "AABB" + "\n" + "AA" + BS + "\nBB\nZ"
    _mk("dg.xwl", _r2a)
    _git(*GIT_ID, "commit", "-q", "-am", "r2-group")
    BASE = _r2a
    for _lbl, _work in (
        ("组尾行", "AABB\nAA" + BS + "\nBBX\nAABB"),
        ("组首行", "AABB\nAA2" + BS + "\nBB\nAABB"),
    ):
        _mk("dg.xwl", _work)
        _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
        if "[warn]" in _out or "精确命中" in _out:
            dg.append("只改%s＋别处多出一处同文本行：新口径不得报压平（R2 已登记误报面）\n%s"
                      % (_lbl, _out))
        if _rc != 0:
            dg.append("只改%s＋别处多出一处同文本行 --strict 下应 rc=0，实得 %s"
                      % (_lbl, _rc))
        if not any(k in _out for k in ("仍有行本次未改", "本次未改")):
            dg.append("只改%s被排除时应说明原因「组内仍有行本次未改」" % _lbl)
    _mk("dg.xwl", BASE)

    # ④p **R1 漏报收口（真压平 ＋ 同时删掉基线既有同文本行）**：旧口径按出现次数闸（1 == 1）挡下
    #     ⇒ 漏报；新口径只看「组内每行是否本次改过 ＋ 命中位置是否工作区新行」⇒ 必报。
    _r1_0 = "AA" + BS + "\nBB\nZ\nAABB"
    _mk("dg.xwl", _r1_0)
    _git(*GIT_ID, "commit", "-q", "-am", "r1-flatten")
    BASE = _r1_0
    _mk("dg.xwl", "AABB\nZ")
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" not in _out or "精确命中" not in _out:
        dg.append("R1：真压平＋删掉基线既有同文本行时应报精确命中（旧口径按出现次数闸漏报）")
    if _rc != 1:
        dg.append("R1 --strict 下应 rc=1，实得 %s" % _rc)
    if "工作区第 1 行" not in _out:
        dg.append("R1：应报出合并后的真实工作区行号 1")
    _mk("dg.xwl", BASE)

    # ④q **XL 窄误报收口**：组内只改 1 个字符（ratio≈1）＋基线已有与拼接逐字相同的行 —— 旧口径
    #     相似度档以高 ratio 报；新口径要求窗口每行都本次改过、命中位置须是工作区新行 ⇒ 不得报。
    _xl_base = "\r\n".join(["AAAA" + "x" * 60 + BS, "BBBB" + "y" * 60, "Z",
                            "AAAA" + "x" * 60 + "BBBB" + "y" * 60])
    _xl_work = "\r\n".join(["AAAA" + "x" * 59 + "Q" + BS, "BBBB" + "y" * 60, "Z",
                            "AAAA" + "x" * 60 + "BBBB" + "y" * 60])
    _mk("dg.xwl", _xl_base)
    _git(*GIT_ID, "commit", "-q", "-am", "xl-sim")
    BASE = _xl_base
    _mk("dg.xwl", _xl_work)
    _rc, _out = _cli("diffguard", "dg.xwl", "--strict")
    if "[warn]" in _out or "相似度命中" in _out:
        dg.append("XL：组内只改一字＋基线已有逐字同文本行时不得报相似度命中（已登记误报）")
    if _rc != 0:
        dg.append("XL --strict 下应 rc=0，实得 %s" % _rc)
    _mk("dg.xwl", BASE)

    # ④m/④n/④o **预算触顶三态**（测试进程内 monkeypatch 上限，⛔ 不改产品默认）：
    #     默认档 rc=0 但末行**不得** `ALL OK`；strict 下「仅未完成」rc=2、「疑似＋未完成」rc=1、
    #     「完整且无问题」rc=0 且末行含「完整通过」。`sim_capped` 必须独立于命中是否为空报告。
    def _dg_inproc(strict, cap=None):
        """进程内跑 `cmd_diffguard`（cwd=夹具仓库）；`cap` 给数字时把两档预算上限临时压到该值。"""
        ns = argparse.Namespace(targets=["dg.xwl"], rev="HEAD", strict=strict)
        _old_caps = (xwl._SIM_MAX_CMP, xwl._SIM_MAX_GATE)
        _cwd = os.getcwd()
        _buf = io.StringIO()
        try:
            if cap is not None:
                xwl._SIM_MAX_CMP = xwl._SIM_MAX_GATE = cap
            os.chdir(repo)
            with contextlib.redirect_stdout(_buf):
                _r = xwl.cmd_diffguard(ns)
        finally:
            xwl._SIM_MAX_CMP, xwl._SIM_MAX_GATE = _old_caps
            os.chdir(_cwd)
        return _r, _buf.getvalue()

    # ④m 仅「未完成」：精确不命中 ＋ 相似度触顶（上限 0）⇒ strict rc=2 / 默认 rc=0，末行均非 ALL OK
    _cap_only = "QQQQQQQQ" + BS + "\nRRRRRRRR\nP\nQ"
    _mk("dg.xwl", _cap_only)
    _git(*GIT_ID, "commit", "-q", "-am", "capped-only")
    BASE = _cap_only
    _mk("dg.xwl", "QQQQQQQQRRRRRRRX\nP\nQ")
    _rc, _out = _dg_inproc(False, cap=0)
    if _rc != 0:
        dg.append("预算触顶（默认档）应 rc=0，实得 %s" % _rc)
    if "ALL OK" in _out or "未完成" not in _out:
        dg.append("预算触顶（默认档）末行不得标 ALL OK，且必须报「未完成」")
    if "-> OK（未完成" not in _out:
        dg.append("预算触顶的单文件结论应是「-> OK（未完成：…）」")
    _rc, _out = _dg_inproc(True, cap=0)
    if _rc != 2:
        dg.append("预算触顶（strict）应 rc=2（没查完），实得 %s" % _rc)
    if "ALL OK" in _out or "未完成" not in _out:
        dg.append("预算触顶（strict）末行应为「未完成」而非 ALL OK")
    _mk("dg.xwl", BASE)

    # ④n 「疑似 ＋ 未完成」：疑似优先 rc=1（并列未完成仍 1），且未完成要被计入并报告
    _cap_sus = "KKKKKKKK" + BS + "\nLLLLLLLL\nP\n" + "QQQQQQQQ" + BS + "\nRRRRRRRR\nZ"
    _mk("dg.xwl", _cap_sus)
    _git(*GIT_ID, "commit", "-q", "-am", "suspect-capped")
    BASE = _cap_sus
    _mk("dg.xwl", "KKKKKKKKLLLLLLLL\nP\nQQQQQQQQRRRRRRRX\nZ")
    _rc, _out = _dg_inproc(True, cap=0)
    if _rc != 1:
        dg.append("疑似＋未完成（strict）应 rc=1（疑似优先），实得 %s" % _rc)
    if "FAIL" not in _out or "未完成 1" not in _out:
        dg.append("疑似＋未完成（strict）应给 FAIL 并在计数里报「未完成 1」")
    _rc, _out = _dg_inproc(False, cap=0)
    if _rc != 0:
        dg.append("疑似＋未完成（默认档）应 rc=0，实得 %s" % _rc)
    if "ALL OK" in _out:
        dg.append("疑似＋未完成（默认档）末行不得标 ALL OK")
    _mk("dg.xwl", BASE)

    # ④o 「完整且无问题」：strict / 默认均 rc=0，末行明确「完整通过」
    _ok_base = "AA\nBB\nCC"
    _mk("dg.xwl", _ok_base)
    _git(*GIT_ID, "commit", "-q", "-am", "complete-ok")
    BASE = _ok_base
    _mk("dg.xwl", "AA\nBB\nCC\nDD")
    for _strict in (True, False):
        _rc, _out = _dg_inproc(_strict, cap=None)
        if _rc != 0:
            dg.append("完整且无问题（strict=%s）应 rc=0，实得 %s" % (_strict, _rc))
        if "完整通过" not in _out or "ALL OK" not in _out or "未完成" in _out:
            dg.append("完整且无问题（strict=%s）末行应明确「完整通过」且无「未完成」" % _strict)
    _mk("dg.xwl", BASE)

    # （⑩ 超时臂已前置到本块最前面 —— 放在这里会被"建库超时／建库失败"两处 `return` 挡住。）
    if dg:
        failures.extend(dg)
    else:
        print("[ok]  压平必报 / 合法删减与单行变长不误报 / patch 改动不误报 / "
              "新文件与非仓库干净跳过 / --strict 与 --rev 的退出码正确 / "
              "短名与长名两种 cwd 写法都能比对 / "
              "**补偿式压平必报、基线行未改的极短行拼接与真实移动不误报 / "
              "多位置逐个列出且有界 / 既有同文本行按「组内每行是否本次改过＋命中位置是否新行」判 / "
              "相似度档同闸（R2a/R2b 不报、XL 不报、R1 必报）** / "
              "**预算触顶三态：strict 仅未完成 rc=2 / 疑似＋未完成 rc=1 / 完整通过 rc=0，"
              "默认档末行不得 ALL OK** / "
              "**1ms 阈值下超时有界返回且原因显式**")

