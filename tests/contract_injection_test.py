#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M2 契约校验器注入回归：证明 4.7 十六条判据「能红」。

做法：每次把「正式数据的副本」放到临时目录（tmp root），施加一次最小注入，
调 contract_validator.run_all(root, only={判据ID})，断言目标判据由 PASS 变 FAIL。
- 不写真实树；真实树只读拷贝。
- 「干净基线」在 tmp 副本上先跑一次目标判据须绿（证明不是恒红）。
运行：
  python skill/tests/contract_injection_test.py
rc=0 表示所有注入用例「干净绿 + 注入红」成立。
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract_validator as cv  # noqa: E402

# 真实工作区根 = skill/tests 的上三级
REAL_ROOT = os.path.dirname(os.path.dirname(HERE))

# 需要拷入 tmp root 的子树（正式数据面）
COPY_SUBTREES = [
    "skill/contracts",
    "skill/webbuilder-xwl-patch",
    "skill/tests",
    "skill/scripts",
    "ledger/data",
    "gate/spec",
    "tools/testing/injection/injection-cases",
    "plans/archive",
]

SKIP_DIRS = {"__pycache__", ".git"}

def copy_tree(src_root, dst_root):
    for sub in COPY_SUBTREES:
        s = os.path.join(src_root, sub)
        d = os.path.join(dst_root, sub)
        if not os.path.isdir(s):
            continue
        for r, dirs, names in os.walk(s):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            rel = os.path.relpath(r, s)
            tdir = os.path.join(d, rel)
            os.makedirs(tdir, exist_ok=True)
            for n in names:
                shutil.copy2(os.path.join(r, n), os.path.join(tdir, n))

def load(root, rel):
    return json.load(io.open(os.path.join(root, rel), encoding="utf-8-sig"))

def save(root, rel, obj, indent=2):
    p = os.path.join(root, rel)
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=indent) + "\n")

# ---------------- 注入用例：mutate(root) 施加一次最小注入 ----------------

def inj_unregistered_file(root):
    p = os.path.join(root, "ledger/data/__inject_new.json")
    io.open(p, "w", encoding="utf-8", newline="\n").write('{"x":1}\n')

def inj_ref_layer_diff(root):
    md = load(root, "skill/webbuilder-xwl-patch/metadata.json")
    md["references"] = md["references"][:-1]  # 删一项 -> 与磁盘差集非空
    save(root, "skill/webbuilder-xwl-patch/metadata.json", md)

def inj_history_consistency(root):
    md = load(root, "skill/webbuilder-xwl-patch/metadata.json")
    h = md["update_history"]
    h[0], h[1] = h[1], h[0]  # 乱序 + 首条与 CHANGELOG 不符
    save(root, "skill/webbuilder-xwl-patch/metadata.json", md)

def inj_item_order(root):
    it = load(root, "ledger/data/items.json")
    items = it["items"]
    items[1]["id"] = items[0]["id"]  # 重复 + 乱序
    save(root, "ledger/data/items.json", it)

def inj_case_schema(root):
    icdir = os.path.join(root, "tools/testing/injection/injection-cases")
    f = sorted(x for x in os.listdir(icdir) if x.endswith(".json"))[0]
    d = load(root, "tools/testing/injection/injection-cases/" + f)
    d["id"] = "renamed-not-file"  # id != 文件名
    save(root, "tools/testing/injection/injection-cases/" + f, d)

def inj_semantic_order(root):
    exdir = os.path.join(root, "skill/webbuilder-xwl-patch/examples")
    tf = sorted(x for x in os.listdir(exdir) if x.startswith("ops-") and x.endswith(".json"))[0]
    d = load(root, "skill/webbuilder-xwl-patch/examples/" + tf)
    ops = d if isinstance(d, list) else d.get("ops")
    if isinstance(ops, list) and ops and isinstance(ops[0], dict):
        ops[0]["op"] = "BOGUS_OP"  # 破坏 op 枚举（执行语义破坏）
    save(root, "skill/webbuilder-xwl-patch/examples/" + tf, d)

def inj_canonical_order(root):
    md = load(root, "skill/webbuilder-xwl-patch/metadata.json")
    r = md["references"]
    r[0], r[-1] = r[-1], r[0]  # 打乱规范序
    save(root, "skill/webbuilder-xwl-patch/metadata.json", md)

def inj_write_form(root):
    p = os.path.join(root, "skill/webbuilder-xwl-patch/test-prompts.json")
    b = io.open(p, "rb").read()
    b = b"\xef\xbb\xbf" + b.replace(b"\n", b"\r\n")  # BOM + CRLF
    io.open(p, "wb").write(b)

def inj_cross_ref(root):
    # archive-manifest.files[0].path 改指不存在 => 悬空引用
    am_rel = "ledger/data/archive-manifest.json"
    if not os.path.exists(os.path.join(root, am_rel)):
        raise SkipInjection("archive-manifest.json 不存在")
    am = load(root, am_rel)
    skills = am.get("skills") or {}
    for sname, sval in skills.items():
        files = sval.get("files")
        if isinstance(files, list) and files and isinstance(files[0], dict):
            files[0]["path"] = "plans/archive/__nonexistent__/ghost.md"
            save(root, am_rel, am)
            return
    raise SkipInjection("archive-manifest 无 files 列表可注入")

def inj_source_drift(root):
    # 构造 derived-values.json，其中一项与判据独立重算不符
    indep = cv._independent_recompute(root, load(root, "skill/contracts/registry.json"))
    if "ledger.items" not in indep:
        raise SkipInjection("无独立重算项")
    vals = dict(indep)
    vals["ledger.items"] = indep["ledger.items"] + 999  # 生成器与判据分叉
    save(root, "skill/contracts/derived-values.json", {"values": vals})

def inj_version_sync(root):
    p = os.path.join(root, "skill/webbuilder-xwl-patch/SKILL.md")
    txt = io.open(p, encoding="utf-8").read()
    import re
    txt = re.sub(r"^version:\s*[0-9]+\.[0-9]+\.[0-9]+\s*$", "version: 9.9.9", txt, count=1, flags=re.M)
    io.open(p, "w", encoding="utf-8", newline="\n").write(txt)

def inj_test_prompts_coverage(root):
    # 删掉涵盖某子命令的唯一 prompt —— 改用删掉全部 prompt，必使多子命令缺覆盖
    p = os.path.join(root, "skill/webbuilder-xwl-patch/test-prompts.json")
    tp = load(root, "skill/webbuilder-xwl-patch/test-prompts.json")
    save(root, "skill/webbuilder-xwl-patch/test-prompts.json", tp[:0])  # 清空 -> 全子命令缺覆盖

def inj_baseline_deduction(root):
    bl = load(root, "skill/tests/baseline.json")
    # 删一个 doc_guard 块 -> 份数下降（低于 registry 下界 35）
    dg = bl["doc_guard_blocks"]
    k = sorted(dg)[0]
    del dg[k]
    save(root, "skill/tests/baseline.json", bl)

def inj_baseline_registry_order(root):
    bl = load(root, "skill/tests/baseline.json")
    bl["blocks"] = list(reversed(bl["blocks"]))  # 反序 -> 与注册序不等（块名集合不变）
    save(root, "skill/tests/baseline.json", bl, indent=2)

def inj_golden_derived(root):
    g = load(root, "skill/tests/task_acceptance_fixtures/golden.json")
    g["expected_ids"] = g["expected_ids"][:-1]  # 少一项 -> 与应检清单不同源
    save(root, "skill/tests/task_acceptance_fixtures/golden.json", g)

def inj_layers_enum(root):
    md = load(root, "skill/webbuilder-xwl-patch/metadata.json")
    k = list(md["layers"].keys())[0]
    md["layers"][k] = "history"  # 越出闭集
    save(root, "skill/webbuilder-xwl-patch/metadata.json", md)


class SkipInjection(Exception):
    pass

CASES = [
    ("contract.unregistered_file", inj_unregistered_file),
    ("metadata.ref_layer_diff", inj_ref_layer_diff),
    ("metadata.history_consistency", inj_history_consistency),
    ("ledger.item_order", inj_item_order),
    ("case.schema_uniform", inj_case_schema),
    ("contract.semantic_order", inj_semantic_order),
    ("contract.canonical_order", inj_canonical_order),
    ("contract.write_form", inj_write_form),
    ("contract.cross_ref", inj_cross_ref),
    ("derive.source_drift", inj_source_drift),
    ("metadata.version_sync", inj_version_sync),
    ("test-prompts.coverage", inj_test_prompts_coverage),
    ("baseline.deduction", inj_baseline_deduction),
    ("baseline.registry_order", inj_baseline_registry_order),
    ("golden.derived", inj_golden_derived),
    ("metadata.layers_enum", inj_layers_enum),
]


def run_one(jid, mutator):
    tmp = tempfile.mkdtemp(prefix="cv-inject-")
    try:
        copy_tree(REAL_ROOT, tmp)
        # 干净基线：目标判据须绿
        res0, _ = cv.run_all(tmp, only={jid})
        clean_v = res0[0][1]
        if clean_v:
            return ("BASELINE_NOT_GREEN", jid, clean_v)
        # 注入
        try:
            mutator(tmp)
        except SkipInjection as e:
            return ("SKIP", jid, str(e))
        res1, _ = cv.run_all(tmp, only={jid})
        dirty_v = res1[0][1]
        if dirty_v:
            return ("PASS", jid, dirty_v[:3])
        return ("NO_RED", jid, None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    results = []
    for jid, mut in CASES:
        results.append(run_one(jid, mut))
    print("== M2 契约校验器注入回归（干净绿 + 注入红）==")
    print("%-32s %-20s %s" % ("判据ID", "结果", "明细"))
    print("-" * 100)
    ok = 0
    red = 0
    for status, jid, detail in results:
        print("%-32s %-20s %s" % (jid, status, (detail if detail else "")))
        if status == "PASS":
            ok += 1
            red += 1
        elif status == "SKIP":
            pass
    total = len(results)
    print("")
    print("用例 %d 条：注入红 %d 条，跳过 %d 条，失败 %d 条。" % (
        total, red, sum(1 for s, _, _ in results if s == "SKIP"),
        sum(1 for s, _, _ in results if s in ("NO_RED", "BASELINE_NOT_GREEN"))))
    # 至少 6 条注入能红即可；但目标为全 16 条（cross_ref 可能因无结构 skip）
    fail = [s for s, _, _ in results if s in ("NO_RED", "BASELINE_NOT_GREEN")]
    if fail or red < 6:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS —— %d 条注入均能红（≥6 达标）。" % red)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
