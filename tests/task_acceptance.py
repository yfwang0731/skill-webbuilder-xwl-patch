# -*- coding: utf-8 -*-
"""ITEM-1205 · 任务级成果物验收执行器（静态应检清单）。

范式：给定一个「任务」目录（一组 .xwl 页面 / SQL 载体），按 **.xwl 页面关系最多递归一层**，
静态推导出「应检清单（expected checklist）」，再对照黄金应检清单给出**覆盖率 / 精确率**，
并把每个应检项判定为互斥四态之一。

⛔ 不进 scripts/、不进 SKILL 分发包（仅开发维护用，落 `skill/tests/`）。
⛔ 只做**静态**应检（不启 Tomcat、不连库、不打开页面）。
✅ 产出**机器可读 JSON**（--json）＋**人读摘要**（默认）。

四态（互斥）：
  PASS        应检项存在且自洽
  MISSING     应检项缺失（漏项 ⇒ 不通过）
  AMBIGUOUS   定位歧义（如同一文件内 itemId 重名、引用指向多个候选 ⇒ 报歧义，不替你任选）
  UNVERIFIED  无法验证（如缺 git 基线、缺基准数据 ⇒ 明确"未执行/无法验证"，⛔ 不当通过）

三负例（内建 `--selftest`）：
  ① 零对象：空任务 ⇒ 必须「不通过/未执行」，⛔ 不假绿
  ② 缺基线：无 git ⇒ 基线类应检项标 UNVERIFIED（非 PASS）
  ③ 歧义定位：itemId 重名 ⇒ 报 AMBIGUOUS（非任选其一）

用法：
  python tests/task_acceptance.py <task_dir> [--golden G.json] [--json] [--selftest]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# xwl.py 在技能运行面 `webbuilder-xwl-patch/scripts/`，不在开发树 `skill/scripts/`
SCRIPTS = os.path.join(os.path.dirname(HERE), "webbuilder-xwl-patch", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

STATE_PASS = "PASS"
STATE_MISSING = "MISSING"
STATE_AMBIGUOUS = "AMBIGUOUS"
STATE_UNVERIFIED = "UNVERIFIED"
ALL_STATES = (STATE_PASS, STATE_MISSING, STATE_AMBIGUOUS, STATE_UNVERIFIED)


# --------------------------------------------------------------------------- #
# 读 .xwl（复用 xwl.py 的宽容读取：字面反斜杠+真实换行）
# --------------------------------------------------------------------------- #
def _load_obj(path):
    import xwl  # scripts/xwl.py
    _text, _has_bom, obj = xwl.load_xwl(path)
    return obj


def _iter_nodes(obj, base=()):
    """递归遍历 children，产出 (node, path_tuple)。"""
    stack = [(obj, base)]
    while stack:
        node, path = stack.pop()
        yield node, path
        ch = node.get("children") if isinstance(node, dict) else None
        if isinstance(ch, list):
            for i, c in enumerate(ch):
                if isinstance(c, dict):
                    stack.append((c, path + ("children", i)))


def _iter_controls(obj, base=()):
    """只走 children 链（不深入 configs 内联对象）—— 与 @itemId 寻址同源。"""
    for node, path in _iter_nodes(obj, base):
        if isinstance(node, dict):
            yield node, path


def _cfg(node):
    c = node.get("configs")
    return c if isinstance(c, dict) else {}


# --------------------------------------------------------------------------- #
# 静态推导：应检清单
# --------------------------------------------------------------------------- #
def _rel_inside(task_dir, ref):
    """把 pageLink / url 之类的引用解析成 task 内的相对路径；不在 task 内返回 None。"""
    if not isinstance(ref, str) or not ref.strip():
        return None
    v = ref.strip()
    # 只认指向 .xwl 的引用（wb 页面 / SQL 载体都是 .xwl）
    if not v.lower().endswith(".xwl"):
        return None
    cand = v.replace("\\", "/")
    # 绝对/带路径：取其 basename 在 task 内匹配
    base = os.path.basename(cand)
    # 直接在 task 根找
    direct = os.path.join(task_dir, cand)
    if os.path.isfile(direct):
        return os.path.relpath(direct, task_dir).replace(os.sep, "/")
    # 退化为按 basename 在 task 内查找（只做一层，不深挖多义）
    hits = []
    for root, _dirs, names in os.walk(task_dir):
        for n in names:
            if n.lower() == base.lower():
                hits.append(os.path.relpath(os.path.join(root, n), task_dir).replace(os.sep, "/"))
    if len(hits) == 1:
        return hits[0]
    return None  # 0 或 >1：不在此处解（留给歧义/缺失判定）


def derive_expected(task_dir):
    """按 .xwl 页面关系（最多递归一层）推导应检清单。

    每个应检项为 dict：
      {"id": 稳定键, "kind": kind, "state": 初始判定, "detail": 说明, "source": 来源文件}
    kind:
      object        —— 任务内的每个 .xwl 文件（对象存在）
      sql-content   —— dataprovider 的 configs.sql 非空（SQL 载体有实质内容）
      page-link     —— pageLink 指向 task 内另一个 .xwl（一层关联存在）
      itemid-unique —— 同一文件内 controls 的 itemId 唯一（无重名）
    """
    files = []
    for root, dirs, names in os.walk(task_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for n in sorted(names):
            if n.lower().endswith(".xwl"):
                files.append(os.path.relpath(os.path.join(root, n), task_dir)
                             .replace(os.sep, "/"))
    files.sort()

    items = []
    objs = {}
    for rel in files:
        items.append({"id": "object:" + rel, "kind": "object", "state": STATE_PASS,
                      "detail": "任务内 .xwl 文件存在", "source": rel})
        try:
            objs[rel] = _load_obj(os.path.join(task_dir, rel))
        except Exception as exc:  # noqa: BLE001
            items[-1]["state"] = STATE_MISSING
            items[-1]["detail"] = "无法解析该 .xwl：%s" % exc
            continue

    for rel, obj in objs.items():
        # ① SQL 载体内容：任一节点 configs.sql 非空
        sql_nodes = []
        for node, _p in _iter_controls(obj):
            cfg = _cfg(node)
            s = cfg.get("sql")
            if isinstance(s, str) and s.strip():
                sql_nodes.append(cfg.get("itemId") or "?")
        if sql_nodes:
            items.append({"id": "sql-content:" + rel, "kind": "sql-content",
                          "state": STATE_PASS,
                          "detail": "dataprovider sql 非空（%d 处）" % len(sql_nodes),
                          "source": rel})

        # ② 同文件 itemId 唯一
        iids = {}
        for node, _p in _iter_controls(obj):
            i = _cfg(node).get("itemId")
            if isinstance(i, str) and i:
                iids[i] = iids.get(i, 0) + 1
        dups = sorted(k for k, c in iids.items() if c > 1)
        if dups:
            items.append({"id": "itemid-unique:" + rel, "kind": "itemid-unique",
                          "state": STATE_AMBIGUOUS,
                          "detail": "同文件 itemId 重名：%s（定位有歧义，不任选）" % ", ".join(dups),
                          "source": rel})
        elif iids:
            items.append({"id": "itemid-unique:" + rel, "kind": "itemid-unique",
                          "state": STATE_PASS, "detail": "itemId 唯一（%d 个）" % len(iids),
                          "source": rel})

        # ③ pageLink 指向 task 内另一个 .xwl（一层）
        pl = obj.get("pageLink")
        target = _rel_inside(task_dir, pl)
        if isinstance(pl, str) and pl.strip() and pl.strip().lower().endswith(".xwl"):
            if target:
                items.append({"id": "page-link:%s->%s" % (rel, target), "kind": "page-link",
                              "state": STATE_PASS,
                              "detail": "pageLink 指向任务内 %s" % target, "source": rel})
            else:
                # 指向了 .xwl 但 task 内找不到（或找到多个）⇒ 缺失/歧义
                state = STATE_AMBIGUOUS if _multi_hit(task_dir, pl) else STATE_MISSING
                items.append({"id": "page-link:%s->%s" % (rel, pl), "kind": "page-link",
                              "state": state,
                              "detail": "pageLink=%r 在任务内%s" % (
                                  pl, "命中多个候选（歧义）" if state == STATE_AMBIGUOUS else "找不到"),
                              "source": rel})
    return items


def _multi_hit(task_dir, ref):
    base = os.path.basename(str(ref).replace("\\", "/"))
    hits = 0
    for root, _d, names in os.walk(task_dir):
        for n in names:
            if n.lower() == base.lower():
                hits += 1
    return hits > 1


# --------------------------------------------------------------------------- #
# 基线核验（git 基线类应检项）—— 缺 git ⇒ UNVERIFIED（⛔ 不当通过）
# --------------------------------------------------------------------------- #
def _has_git(task_dir):
    try:
        r = subprocess.run(["git", "-C", task_dir, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def baseline_items(task_dir):
    """基线类应检项：有 git ⇒ PASS（可做 diffguard 基线核验）；无 git ⇒ UNVERIFIED（未执行）。"""
    if _has_git(task_dir):
        return [{"id": "baseline:git", "kind": "baseline", "state": STATE_PASS,
                 "detail": "git 基线可用（可跑 diffguard 基线核验）", "source": "."}]
    return [{"id": "baseline:git", "kind": "baseline", "state": STATE_UNVERIFIED,
             "detail": "无 git 基线 ⇒ 基线类核验未执行 / 无法验证（⛔ 不当通过）", "source": "."}]


# --------------------------------------------------------------------------- #
# 覆盖率 / 精确率（对照黄金应检清单）
# --------------------------------------------------------------------------- #
def evaluate(task_dir, golden=None):
    expected = derive_expected(task_dir) + baseline_items(task_dir)
    produced_ids = {it["id"] for it in expected}

    # 零对象负例语义：任务里一个 .xwl 都没有 ⇒ 判"不通过/未执行"，不假绿
    object_items = [it for it in expected if it["kind"] == "object"]
    zero_objects = (len(object_items) == 0)

    result = {
        "task_dir": os.path.abspath(task_dir),
        "object_count": len(object_items),
        "items": expected,
        "zero_objects": zero_objects,
    }

    if golden is not None:
        golden_ids = set(golden.get("expected_ids") or [])
        inter = produced_ids & golden_ids
        coverage = (len(inter) / len(golden_ids)) if golden_ids else None
        precision = (len(inter) / len(produced_ids)) if produced_ids else None
        missing = sorted(golden_ids - produced_ids)     # 漏项 = 不通过
        extra = sorted(produced_ids - golden_ids)        # 多报 = 须说明
        result.update({"golden_size": len(golden_ids),
                       "coverage": coverage, "precision": precision,
                       "missing_vs_golden": missing, "extra_vs_golden": extra})

    # 总体结论（四态汇总 + 漏项 + 零对象）
    states = {}
    for it in expected:
        states[it["state"]] = states.get(it["state"], 0) + 1
    result["state_counts"] = states

    hard_fail = zero_objects or states.get(STATE_MISSING, 0) > 0
    if golden is not None and result.get("missing_vs_golden"):
        hard_fail = True
    if zero_objects:
        result["verdict"] = "零对象（空任务）⇒ 未执行 / 不通过（⛔ 不假绿）"
    elif hard_fail:
        result["verdict"] = "不通过"
    elif states.get(STATE_AMBIGUOUS, 0) > 0:
        result["verdict"] = "有歧义项（需人工裁定，不任选）"
    elif states.get(STATE_UNVERIFIED, 0) > 0:
        result["verdict"] = "部分未验证（缺基线）"
    else:
        result["verdict"] = "通过（静态应检全 PASS）"
    result["pass"] = (result["verdict"].startswith("通过"))
    return result


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def _summary(result):
    lines = []
    lines.append("== 任务级成果物验收（静态应检） ==")
    lines.append("任务目录: %s" % result["task_dir"])
    lines.append("对象数（.xwl）: %d" % result["object_count"])
    sc = result["state_counts"]
    lines.append("四态分布: PASS=%d MISSING=%d AMBIGUOUS=%d UNVERIFIED=%d"
                 % (sc.get(STATE_PASS, 0), sc.get(STATE_MISSING, 0),
                    sc.get(STATE_AMBIGUOUS, 0), sc.get(STATE_UNVERIFIED, 0)))
    if "coverage" in result:
        cv = result["coverage"]
        pr = result["precision"]
        lines.append("覆盖率(coverage): %s   精确率(precision): %s" % (
            ("%.3f" % cv) if cv is not None else "N/A",
            ("%.3f" % pr) if pr is not None else "N/A"))
        if result.get("missing_vs_golden"):
            lines.append("漏项(结论不通过): %s" % ", ".join(result["missing_vs_golden"]))
        if result.get("extra_vs_golden"):
            lines.append("多报(须说明): %s" % ", ".join(result["extra_vs_golden"]))
    lines.append("结论: %s" % result["verdict"])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 内建三负例 + 黄金覆盖/精确率自检
# --------------------------------------------------------------------------- #
def _selftest():
    import io
    import shutil
    import tempfile

    def _write_xwl(path, obj):
        import xwl
        text = xwl.dumps_designer(obj, 1, "\n")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    fails = []
    tmp = tempfile.mkdtemp(prefix="taskacc1205_")

    def _page(title="P", page_link="", children=None):
        return {"hidden": False,
                "children": children if children is not None else [
                    {"configs": {"itemId": "module"}, "expanded": False,
                     "children": [], "type": "module"}],
                "roles": {"default": 1}, "title": title, "iconCls": "",
                "inframe": False, "pageLink": page_link}

    try:
        # ── 负例① 零对象：空任务 ⇒ 不假绿 ──
        empty = os.path.join(tmp, "empty_task")
        os.makedirs(empty, exist_ok=True)
        r0 = evaluate(empty)
        if not r0["zero_objects"] or r0["pass"]:
            fails.append("负例①(零对象)：空任务被判通过/假绿（verdict=%r）" % r0["verdict"])
        else:
            print("[ok]  负例① 零对象：空任务 ⇒ %s（不假绿）" % r0["verdict"])

        # ── 负例② 缺基线：无 git ⇒ UNVERIFIED（非 PASS） ──
        nogit = os.path.join(tmp, "nogit_task")
        os.makedirs(nogit, exist_ok=True)
        # 用独立子目录，确保不在本仓 git 里
        nb = os.path.join(tmp, "nogit_task", "p.xwl")
        _write_xwl(nb, _page("P"))
        r1 = evaluate(nogit)
        bl = [it for it in r1["items"] if it["kind"] == "baseline"][0]
        if bl["state"] != STATE_UNVERIFIED:
            fails.append("负例②(缺基线)：无 git 却把基线判成 %r（应 UNVERIFIED）" % bl["state"])
        else:
            print("[ok]  负例② 缺基线：无 git ⇒ baseline 项 %s（未执行/无法验证，非通过）" % bl["state"])

        # ── 负例③ 歧义定位：itemId 重名 ⇒ AMBIGUOUS（非任选） ──
        amb = os.path.join(tmp, "amb_task")
        os.makedirs(amb, exist_ok=True)
        dup_page = _page("DUP", children=[
            {"configs": {"itemId": "module"}, "expanded": False, "children": [], "type": "module"},
            {"configs": {"itemId": "same"}, "expanded": False, "children": [], "type": "container"},
            {"configs": {"itemId": "same"}, "expanded": False, "children": [], "type": "container"},
        ])
        _write_xwl(os.path.join(amb, "dup.xwl"), dup_page)
        r2 = evaluate(amb)
        amb_items = [it for it in r2["items"] if it["kind"] == "itemid-unique"]
        if not amb_items or amb_items[0]["state"] != STATE_AMBIGUOUS:
            fails.append("负例③(歧义定位)：itemId 重名未报 AMBIGUOUS（%r）"
                         % (amb_items[0]["state"] if amb_items else None))
        else:
            print("[ok]  负例③ 歧义定位：itemId 重名 ⇒ %s（报歧义、不任选）" % amb_items[0]["state"])

        # ── 黄金覆盖/精确率：一个含 page(→link sql载体) 的样例 ──
        golddir = os.path.join(tmp, "gold_task")
        os.makedirs(golddir, exist_ok=True)
        sql_page = {"hidden": False, "children": [
            {"configs": {"itemId": "module",
                         "serverScript": "var sql='';request.setAttribute('sql',sql);"},
             "expanded": True, "children": [
                 {"configs": {"itemId": "dataprovider",
                              "sql": "select * from WB_MISC\nwhere 1=1\n{#sql#}"},
                  "expanded": False, "children": [], "type": "dataprovider"}],
             "type": "module"}],
            "roles": {"default": 1}, "title": "SQL载体", "iconCls": "",
            "inframe": False, "pageLink": ""}
        _write_xwl(os.path.join(golddir, "query.xwl"), sql_page)
        _write_xwl(os.path.join(golddir, "pageA.xwl"), _page("页面A", page_link="query.xwl"))
        golden = {"expected_ids": [
            "object:pageA.xwl", "object:query.xwl",
            "sql-content:query.xwl",
            "page-link:pageA.xwl->query.xwl",
            "itemid-unique:pageA.xwl", "itemid-unique:query.xwl",
            "baseline:git",
        ]}
        rg = evaluate(golddir, golden=golden)
        if rg.get("coverage") != 1.0:
            fails.append("黄金样例覆盖率非 1.0（%r），漏项=%r"
                         % (rg.get("coverage"), rg.get("missing_vs_golden")))
        else:
            print("[ok]  黄金样例：覆盖率=%.3f 精确率=%s 漏项=%r"
                  % (rg["coverage"],
                     ("%.3f" % rg["precision"]) if rg.get("precision") is not None else "N/A",
                     rg.get("missing_vs_golden")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        for f in fails:
            print("[FAIL] " + f)
        return 1
    print("[ok]  ITEM-1205 执行器自检：三负例 + 黄金覆盖/精确率 全部符合")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(description="ITEM-1205 任务级成果物验收执行器（静态应检）")
    p.add_argument("task_dir", nargs="?", help="任务目录（含 .xwl）")
    p.add_argument("--golden", help="黄金应检清单 JSON")
    p.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    p.add_argument("--selftest", action="store_true", help="跑内建三负例 + 黄金自检")
    a = p.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.task_dir:
        p.error("需要 task_dir（或用 --selftest）")
    if not os.path.isdir(a.task_dir):
        print("[FAIL] 不是目录：%s" % a.task_dir)
        return 2
    golden = None
    if a.golden:
        with open(a.golden, "r", encoding="utf-8") as fh:
            golden = json.load(fh)
    result = evaluate(a.task_dir, golden=golden)
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_summary(result))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
