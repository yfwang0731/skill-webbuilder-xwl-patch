#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 统一契约扫描器双向回归（整块 --require-all 硬判据，B 组）。

证明（B 组双向回归）：
  A. 旧守卫现存负例集：把旧 17i 逐句式字面量改错（FAQ 25→24、清单 30→29），
     跑**整块** `--require-all --profile package`，须 rc≠0。
  B. 新写法/未绑定注入集：改到与重算不符的「新写法」声明（SKILL FAQ 25→99）、
     或注入「未登记/未绑定」的声明形状（加粗 `**99 项**清单`），
     跑**整块** `--require-all --profile package`，须 rc≠0。
  C. 干净基线：不改任何东西，整块须 rc=0（证明不是恒红）。

「整块」= 在完整临时副本上以子进程跑 `selftest.py --require-all --profile package`
（profile=package 把契约扫描/校验档并入必需范围；见 selftest `_contract_scan_fails`）。
rc=0 表示所有用例「干净绿 + 注入红」成立；任一不成立即 rc=1。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.dirname(os.path.dirname(HERE))   # skill/tests 的上两级 = 工作区根

# 整块 require-all 需要的子树（副本要自包含可跑 selftest）
COPY_SUBTREES = ["skill", "ledger", "gate", "tools", "plans"]
SKIP = shutil.ignore_patterns("__pycache__", ".git")


def copy_tree(dst):
    for sub in COPY_SUBTREES:
        s = os.path.join(REAL_ROOT, sub)
        if os.path.isdir(s):
            if sub == "skill":
                # skill/.git 必须一并复制：`--require-all` 的 git 臂（编年守卫 / 17r 分发面）
                # 依赖 `git ls-files`；无 .git 时这两臂记「未完成」⇒ 整块 rc=2，干净基线会假红。
                shutil.copytree(s, os.path.join(dst, sub),
                                ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copytree(s, os.path.join(dst, sub), ignore=SKIP)


def run_requireall(tmp):
    """在 tmp 副本上跑整块 --require-all --profile package，返回 rc。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["XWL_SKILL_ROOT"] = os.path.join(tmp, "skill", "webbuilder-xwl-patch")
    r = subprocess.run(
        [sys.executable, os.path.join(tmp, "skill", "scripts", "selftest.py"),
         "--require-all", "--profile", "package"],
        cwd=tmp, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    return r.returncode, r.stdout


def _edit(path, needle, repl):
    t = io.open(path, encoding="utf-8", newline="").read()
    assert needle in t, "needle not found: %r" % needle
    t = t.replace(needle, repl, 1)
    io.open(path, "w", encoding="utf-8", newline="\n").write(t)


# ---------------- 用例：mutate(tmp) 施加一次最小注入 ----------------
CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("A. 旧负例-改 FAQ 条数(25->24)")
def _(root):
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/references/faq.md"),
          "**25 条按四组归类**", "**24 条按四组归类**")


@case("A. 旧负例-改清单项数(30->29)")
def _(root):
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/SKILL.md"),
          "**30 项**清单", "**29 项**清单")


@case("B. 新写法-改 SKILL FAQ 高频问题条数(25->99)")
def _(root):
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/SKILL.md"),
          "**25 条**高频问题", "**99 条**高频问题")


@case("B. 未绑定-改子命令声明数(15->16)")
def _(root):
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/SKILL.md"),
          "共 15 个子命令", "共 16 个子命令")


@case("B. 待登记-注入未登记加粗声明(**99 项**清单)")
def _(root):
    p = os.path.join(root, "skill/webbuilder-xwl-patch/SKILL.md")
    t = io.open(p, encoding="utf-8", newline="").read()
    t += "\n**99 项**清单（未登记的声明形状，应判待登记）\n"
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)


# ===== B1 合流（W3）：17l / 17r / 17b / 17j-4 四守卫体的旧负例仍红 ＋ 新写法必红 =====
# 每个守卫体各一条「旧负例」（破坏该守卫所守形态）＋（适用时）一条「新写法」
# （用该守卫的另一种句法形态注入，证明通用实现覆盖多种形态，不只认旧写法）。

@case("B1-17l 旧负例-注入编年事件词(原先)")
def _(root):
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/references/generation.md"),
          "# ", "# 原先的做法是本文件旧版里的")


@case("B1-17l 新写法-注入发版号形态(x.y.z)")
def _(root):
    # 17l 第三臂：正文出现发版号 x.y.z（非 frontmatter 的 version:、非依据层文件）
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/references/value-mapping.md"),
          "# ", "# 1.8.3 起本文口径如下")


@case("B1-17r 旧负例-注入包外指针《落地清单》")
def _(root):
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/references/value-mapping.md"),
          "# ", "# 见《落地清单》")


@case("B1-17r 新写法-注入前置过程角色编号(PRE12)")
def _(root):
    # 17r 另一形态：施工单/过程角色编号（PRE 形态）出现在分发面
    _edit(os.path.join(root, "skill/webbuilder-xwl-patch/references/generation.md"),
          "# ", "# 见 PRE12 记录")


@case("B1-17b 旧负例-跨文档复制表格行")
def _(root):
    cp = os.path.join(root, "skill/webbuilder-xwl-patch/references/checklist.md")
    rows = [l for l in io.open(cp, encoding="utf-8").read().splitlines()
            if l.strip().startswith("|") and l.count("|") >= 2]
    assert rows, "no table row in checklist"
    lp = os.path.join(root, "skill/webbuilder-xwl-patch/references/layout.md")
    t = io.open(lp, encoding="utf-8").read()
    io.open(lp, "w", encoding="utf-8", newline="\n").write(rows[0] + "\n" + t)


@case("B1-17j-4 旧负例-SKILL 超篇幅硬上限")
def _(root):
    p = os.path.join(root, "skill/webbuilder-xwl-patch/SKILL.md")
    t = io.open(p, encoding="utf-8", newline="").read()
    t += "\n" + ("填充测试行用来顶穿篇幅硬上限。\n" * 500)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)



def main():
    print("== M3 契约扫描器双向回归（整块 --require-all 硬判据）==")
    all_ok = True
    # C. 干净基线
    tmp = tempfile.mkdtemp(prefix="m3reg-clean-")
    try:
        copy_tree(tmp)
        rc, _ = run_requireall(tmp)
        clean_ok = (rc == 0)
        print("%-44s 整块 rc=%d  clean=%s" % ("C. 干净基线（须 rc=0）", rc,
                                              "OK" if clean_ok else "FAIL"))
        all_ok = all_ok and clean_ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # A/B. 注入集（须 rc≠0）
    for name, mut in CASES:
        tmp = tempfile.mkdtemp(prefix="m3reg-")
        try:
            copy_tree(tmp)
            mut(tmp)
            rc, out = run_requireall(tmp)
            red = (rc != 0)
            ok = red
            all_ok = all_ok and ok
            tail = ""
            if not red:
                tail = " (未红：整块仍 rc=0)"
            print("%-44s 整块 rc=%d  注入红=%s%s" % (name, rc, "OK" if red else "FAIL", tail))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("")
    print("RESULT:", "PASS —— 干净绿 + 旧负例红 + 新写法/未绑定红（整块 rc 判定）"
          if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
