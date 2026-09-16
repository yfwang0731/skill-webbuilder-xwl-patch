#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py —— xwl.py 的自检（不依赖任何外部 xwl 文件）

内置样本覆盖：
  · `check` 的格式判定（1 个合法样本 + 5 种典型破坏）
  · `edit` 的锚点拒绝与正例（含 CRLF / BOM 是否保持）
  · `expand` 的排版形态与语义等价（含 `--safe` 模式）
  · `patch` 的结构级编辑（新节点事件 JS、自动续行）
  · `new` 的从零生成（设计器真实键序 / 拒绝覆盖 / `--from-json` 补齐缺键）
  · `folders` 的 index 一致性检查与 `--register`（幂等 / 保键序 / 保单行形态）
  · `paths` 的「原路径」必须带 configs 层（照抄即可改对位置）
  · `schema --skeleton` 只含该控件允许的键，events 键按该控件实际事件决定
  · 文档一致性守卫（跨文件）：emoji 未入标题 / README↔SKILL 无逐字重复的表格行 /
    「见 N.M」的编号引用可解析 / 文档与工具里无业务路径与业务字段名（skill 是通用资产）
  · `@itemId` 寻址（唯一可定位 / 重名拒绝并给候选清单 / `#N` 点名与越界）
  · itemId 重名分级（列 benign / 按钮+被引用 error / 唯一 normalName benign / 未被引用 warn）
  · `params` 的两条通路识别与注释剔除

改完 xwl.py 先跑它；输出末尾应为 `selftest ALL OK`：

    python scripts/selftest.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("xwl", os.path.join(HERE, "xwl.py"))
xwl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xwl)  # type: ignore[union-attr]

CRLF = "\r\n"

# 合法样本：events.click 是「反斜杠 + 真实 CRLF」的多行字符串（JS 用单引号）
VALID = (
    "{" + CRLF
    + '  "title": "测试页",' + CRLF
    + '  "children": [' + CRLF
    + "    {" + CRLF
    + '      "xtype": "button",' + CRLF
    + '      "text": "测试",' + CRLF
    + '      "events": {' + CRLF
    + '        "click": "var a = app.x.getSelection();\\' + CRLF
    + "if (!a) { return; }\\" + CRLF
    + "Wb.info('ok');\"" + CRLF
    + "      }" + CRLF
    + "    }" + CRLF
    + "  ]," + CRLF
    + '  "sql": "select 1 from dual\\' + CRLF
    + 'where 1=1"' + CRLF
    + "}" + CRLF
)

# 合法样本里 click 的 JS 应被解析成 3 行
EXPECT_JS_LINES = 3


def _run_check(files: list[str], node: str | None):
    """跑 check，返回 (exit_code, stdout)。"""
    buf = io.StringIO()
    ns = type("NS", (), {"files": files, "node": node, "no_js": node is None})()
    with contextlib.redirect_stdout(buf):
        code = xwl.cmd_check(ns)
    return code, buf.getvalue()


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="xwl_selftest_")
    node = xwl.find_node()
    print(f"node: {node or '(未找到，跳过事件 JS 校验)'}")
    failures: list[str] = []

    def write(name: str, text: str, bom: bool = False) -> str:
        p = os.path.join(tmp, name)
        with open(p, "wb") as f:
            if bom:
                f.write(b"\xef\xbb\xbf")
            f.write(text.encode("utf-8"))
        return p

    # ---- 0. 前置：合法样本必须能被解析，且 JS 是真实换行 ----
    try:
        obj = xwl.parse_xwl(VALID)
        clicks = [c for n, c in xwl.collect_events(obj) if n == "click"]
        assert len(clicks) == 1, clicks
        assert len(clicks[0].splitlines()) == EXPECT_JS_LINES, repr(clicks[0])
        sqls = xwl.collect_sql(obj)
        assert any("select 1 from dual" in s for _, s in sqls), sqls
        assert all('\\"' not in s for _, s in sqls)
        print("[ok]  前置：合法样本解析、事件抽取、SQL 抽取均正确")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"前置样本自检失败: {exc}")

    # ---- 1. 合法样本：check 必须通过 ----
    good = write("valid.xwl", VALID)
    code, out = _run_check([good], node)
    if code != 0:
        failures.append(f"合法样本被判 FAIL:\n{out}")
    else:
        print("[ok]  check 对合法样本判 OK")

    # ---- 2. 五种破坏必须被检出 ----
    cases: list[tuple[str, str, str, bool]] = [
        # (用例名, 文件内容, 期望出现在输出里的关键词, 是否 BOM)
        ("裸LF", VALID.replace(CRLF, "\n", 1), "裸 LF", False),
        ("反斜杠+空格", VALID.replace(";\\" + CRLF, ";\\  " + CRLF, 1), "反斜杠+空白", False),
        ("JSON破坏", VALID.replace("]", "", 1), "加载器等价解析失败", False),
        ("带BOM", VALID, "BOM", True),
        ("末行带续行符", VALID[:-2] + "\\", "末行", False),
    ]
    for name, text, keyword, bom in cases:
        p = write(f"bad_{name}.xwl", text, bom=bom)
        code, out = _run_check([p], node)
        if code == 0:
            failures.append(f"破坏用例「{name}」未被检出")
        elif keyword not in out:
            failures.append(f"破坏用例「{name}」被检出，但缺少关键词「{keyword}」:\n{out}")
        else:
            print(f"[ok]  破坏用例「{name}」已检出（关键词 {keyword}）")

    # ---- 3. edit：锚点不唯一必须拒绝且不落盘 ----
    p = write("edit.xwl", VALID)
    old = os.path.join(tmp, "old.txt")
    new = os.path.join(tmp, "new.txt")
    with open(old, "w", encoding="utf-8") as f:
        f.write("x")  # 出现 0 次
    with open(new, "w", encoding="utf-8") as f:
        f.write("y")
    ns = type("NS", (), {
        "target": p, "old_file": old, "new_file": new, "expect": 1,
        "dry_run": False, "backup": False, "node": node, "no_js": node is None,
    })()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = xwl.cmd_edit(ns)
    same = open(p, "rb").read().decode("utf-8") == VALID
    if rc == 0 or not same:
        failures.append("edit 对不存在的锚点未拒绝，或文件被改动")
    else:
        print("[ok]  edit 对锚点不匹配已拒绝且未落盘")

    # ---- 4. edit：唯一锚点正例 ----
    old2 = os.path.join(tmp, "old2.txt")
    new2 = os.path.join(tmp, "new2.txt")
    with open(old2, "w", encoding="utf-8") as f:
        f.write('"text": "测试"')
    with open(new2, "w", encoding="utf-8") as f:
        f.write('"text": "测试2"')
    ns.old_file, ns.new_file = old2, new2
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = xwl.cmd_edit(ns)
    after = open(p, "rb").read()
    ok = (
        rc == 0
        and after.decode("utf-8").count('"text": "测试2"') == 1
        and after[:3] != b"\xef\xbb\xbf"
        and after.count(b"\r\n") == after.count(b"\n")
    )
    if not ok:
        failures.append(f"edit 正例失败:\n{buf.getvalue()}")
    else:
        print("[ok]  edit 正例：替换成功、CRLF 与无 BOM 均保持")

    # ---- 5. expand：单行源 → 设计器同款多行 ----
    one = os.path.join(tmp, "one.xwl")
    compact = (
        '{"hidden":false,"children":[{"configs":{"itemId":"module"},'
        '"events":{"click":"Wb.info(\'hi\');"}}]}'
    )
    with open(one, "w", encoding="utf-8", newline="") as f:
        f.write(compact)

    def _expand_ns(p, **kw):
        d = {"file": p, "out": None, "indent": 1, "eol": "auto", "safe": False,
             "dry_run": False, "backup": False, "node": node, "no_js": node is None}
        d.update(kw)
        return type("NS", (), d)()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = xwl.cmd_expand(_expand_ns(one))
    text_out = open(one, "rb").read().decode("utf-8")
    checks = {
        "expand 返回码 0": rc == 0,
        "expand 产出多行": text_out.count("\n") >= 4,
        "expand 语义等价": xwl.parse_xwl(text_out) == xwl.parse_xwl(compact),
        "expand 单元素对象内联": '"configs": {"itemId": "module"}' in text_out,
        "expand 数组紧凑 [{": "[{" in text_out,
        "expand 无尾换行": not text_out.endswith("\n"),
    }
    for name, cond in checks.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败；产出={text_out!r}")

    # ---- 6. 值里的「字面反斜杠 + n」：两种模式都应语义无损 ----
    # 值 = SQL 里的字面 \n（该值在 JSON 里写作 \\n）
    lit_compact = '{"sql":"select 1 SEPARATOR\'\\\\n\'"}'
    obj_lit = xwl.parse_xwl(lit_compact)
    safe_out = xwl.dumps_designer(obj_lit, 1, "\r\n", safe=True)
    faithful_out = xwl.dumps_designer(obj_lit, 1, "\r\n", safe=False)
    for name, cond in {
        "忠实模式保语义": xwl.parse_xwl(faithful_out) == obj_lit,
        "安全模式保语义": xwl.parse_xwl(safe_out) == obj_lit,
        "两种模式磁盘形态不同": safe_out != faithful_out,
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败（忠实={faithful_out!r} 安全={safe_out!r}）")

    # ---- 7. patch：结构级编辑（只给值，格式由序列化器产出） ----
    pf = write("patch.xwl", VALID)
    ops = [
        {"op": "set", "path": ["title"], "value": "改后标题"},
        {"op": "append", "path": ["children"],
         "value": {"type": "button", "configs": {"itemId": "n", "text": "新"},
                   "events": {"click": "var x = 1;\nWb.info(x);"}}},
    ]
    opsf = os.path.join(tmp, "ops.json")
    with open(opsf, "w", encoding="utf-8") as f:
        json.dump(ops, f, ensure_ascii=False)
    ns3 = type("NS", (), {"file": pf, "ops": opsf, "indent": 1, "eol": "auto",
                          "dry_run": False, "backup": False,
                          "node": node, "no_js": node is None})()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = xwl.cmd_patch(ns3)
    after = open(pf, "rb").read().decode("utf-8")
    po = xwl.parse_xwl(after)
    for name, cond in {
        "patch 返回码 0": rc == 0,
        "patch 已改 title": po.get("title") == "改后标题",
        "patch 已追加子节点": len(po.get("children", [])) == 2,
        "patch 新节点事件 JS 未被破坏": po["children"][1]["events"]["click"] == "var x = 1;\nWb.info(x);",
        "patch 自动生成续行形态": ("\\" + "\r\n") in after,
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败（产出前 200 字符={after[:200]!r}）")

    # ---- 8. params：两条通路的识别（out / params） ----
    FIELD = xwl.field_types(None)
    js_out = "app.grid1.store.load({ out: app.tbar });"
    js_gv = "app.grid1.store.load({ params: Wb.getValue(app.tbar) });"
    js_obj = "app.grid1.store.load({ params: { cId: rec.data.MR_ID, sql: 'a,b:c', nested: {x: 1} } });"
    js_both = "Wb.request({ url: 'm?xwl=demo/x', out: app.editWin, params: { a: 1 }, success: fn });"
    tr_out = xwl.find_transfers(js_out, FIELD)
    tr_gv = xwl.find_transfers(js_gv, FIELD)
    tr_obj = xwl.find_transfers(js_obj, FIELD)
    tr_both = xwl.find_transfers(js_both, FIELD)
    for name, cond in {
        "识别 out 通路（容器 app.tbar）":
            [t[0] for t in tr_out] == ["out"] and tr_out[0][1] == ["tbar"],
        "识别 params: Wb.getValue（等价 out）":
            [t[0] for t in tr_gv] == ["params=Wb.getValue"] and tr_gv[0][1] == ["tbar"],
        "识别 params: 对象键（跳过字符串值与嵌套层）":
            bool(tr_obj) and tr_obj[0][0] == "params=对象" and tr_obj[0][2] == ["cId", "sql", "nested"],
        "out 与 params 同时出现时各自独立识别":
            {t[0] for t in tr_both} == {"out", "params=对象"},
        "read_expr 括号配平":
            xwl.read_expr(js_both, js_both.index("out:") + 4).strip() == "app.editWin",
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(
                f"{name} 失败（out={tr_out} gv={tr_gv} obj={tr_obj} both={tr_both}）")

            # ---- 9. 注释剔除与多容器 out ----
    for name, cond in {
        "行注释里的 out 不被误判":
            [t[1] for t in xwl.find_transfers(
                "// g.load({ out: app.tbar });\ng.load({ out: app.tbar2 });", FIELD)] == [["tbar2"]],
        "块注释里的 params 不被误判":
            [t[2] for t in xwl.find_transfers(
                "/* params: { a: 1 } */\ng.load({ params: { b: 2 } });", FIELD)] == [["b"]],
        "字符串里的 // 不被当注释":
            [t[2] for t in xwl.find_transfers(
                "g.load({ params: { u: 'http://x/y' } });", FIELD)] == [["u"]],
        "多容器 out: [app.a, app.b]":
            [t[1] for t in xwl.find_transfers("g.load({ out: [app.a, app.b] });", FIELD)] == [["a", "b"]],
        "剔注释不粘连代码":
            xwl.strip_js_comments("var a = 1; // c\nvar b = 2;") == "var a = 1; \nvar b = 2;",
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败")

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

    # ---- 11b. itemId 重名分级：类型 + 是否被 JS 引用 + normalName ----
    #   column 重名        → benign（取数走 grid.getSelection(0).data.*）
    #   button 重名+被引用 → error（app.btn 取值不确定）
    #   text   重名+各有唯一 normalName → benign（框架按 normalName || itemId 注册）
    #   panel  重名但未被引用 → warn（老代码可留，新代码须区分）
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
           {"FCol": "benign", "btn": "error", "same": "benign", "pnl": "warn"}.items()
           if lv.get(k) != v}
    if bad:
        failures.append("itemId 分级不符（期望 vs 实得）: %s" % bad)
    else:
        print("[ok]  itemId 重名分级：列=benign / 按钮+被引用=error / 有唯一 normalName=benign / 未被引用的面板=warn")

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
    rep_arr = xwl.audit_itemids({"children": [
        {"type": "grid", "configs": {"itemId": "g1"}, "children": [
            {"type": "array", "configs": {"itemId": "columns"}, "children": []}]},
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
    rep_mix = xwl.audit_itemids({"children": [
        {"type": "column", "configs": {"itemId": "mixed"}, "children": []},
        {"type": "combo", "configs": {"itemId": "mixed"}, "children": []}]})
    if "跨类型" in rep_mix["groups"][0]["reason"]:
        print("[ok]  含列控件的跨类型混名单独措辞（不再误称「应唯一的类型」）")
    else:
        failures.append("跨类型混名的理由措辞未区分: %s" % rep_mix["groups"][0]["reason"][:60])

    # ---- 11f. 读文件失败一律给 XwlLoadError（不冒裸 OSError/JSONDecodeError）----
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
    try:
        xwl.recommend_fixes({"groups": [{"level": "error"}, {"level": "warn"}]}, "auto")
        xwl.recommend_fixes({"groups": [{"level": "error"}]}, "normalName", skipped=[])
        print("[ok]  recommend_fixes 对缺 fix_* 键的 group 不崩（防御性取值）")
    except Exception as exc:  # noqa: BLE001
        failures.append("recommend_fixes 对缺键 group 抛错: %s: %s" % (type(exc).__name__, exc))

    # ---- 11j. itemids --name 找不到名字时，--json 路径要给 JSON（不能混纯文本）----
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

    # ---- 11k. SKILL.md 章节顺序守卫（语义分组：认知→格式→操作→专题→经验→收尾）----
    skill_md = os.path.join(os.path.dirname(HERE), "SKILL.md")
    if os.path.exists(skill_md):
        with open(skill_md, "r", encoding="utf-8", newline="") as f:
            titles = [l.rstrip("\r\n") for l in f if l.startswith("## ")]
        want_order = ["一", "二", "三", "四", "五", "六", "七", "八", "九"]
        got_order = [t[3] for t in titles if len(t) > 4 and t[3] in want_order]
        want_keys = ["是什么", "格式硬规则", "处理流程", "工具", "引用方式", "SQL 片段",
                     "itemId", "常见坑", "自检清单"]
        if got_order == want_order and all(k in t for k, t in zip(want_keys, [x for x in titles if x.startswith("## ") and x[3] in want_order])):
            print("[ok]  SKILL.md 章节顺序符合语义分组（认知→格式→操作→专题→经验→收尾）")
        else:
            failures.append("SKILL.md 章节顺序错位: %s" % [t[:22] for t in titles])
        if any("单行源" in t for t in titles):
            failures.append("「单行源 vs 多行源」应并入格式章，不该单列一章")
    else:
        print("[note] 未找到 SKILL.md，跳过章节顺序守卫")

    # ---- 12. 子命令冒烟：paths / sqlrefs / params 真跑一遍（防“改了内部函数名漏改调用”）----
    page_obj = {"title": "参数页", "children": [
        {"configs": {"itemId": "viewport"}, "expanded": False, "type": "viewport", "children": [
            {"configs": {"itemId": "tbar"}, "expanded": False, "type": "toolbar", "children": [
                {"configs": {"itemId": "kw", "fieldLabel": "关键字"}, "expanded": False,
                 "children": [], "type": "text"},
                {"configs": {"itemId": "queryBtn", "text": "查询"}, "expanded": False,
                 "children": [], "type": "button",
                 "events": {"click": "app.grid1.store.load({ out: app.tbar });"}},
            ]},
            {"configs": {"itemId": "grid1"}, "expanded": False, "type": "grid", "children": [
                {"configs": {"itemId": "gridStore", "url": "m?xwl=demo/xxxSql/demoSql"},
                 "expanded": False, "children": [], "type": "store"},
            ]},
        ]},
    ]}
    page_path = os.path.join(tmp, "page_smoke.xwl")
    with open(page_path, "w", encoding="utf-8", newline="") as f:
        f.write(xwl.dumps_designer(page_obj, 1, CRLF))

    def _run(fn, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(type("NS", (), kw)())
        return code, buf.getvalue()

    smoke_fail = []
    for label, fn, kw, want in (
        ("paths",   xwl.cmd_paths,   {"file": page_path}, "原路径"),
        ("sqlrefs", xwl.cmd_sqlrefs, {"file": page_path}, ""),
        ("params",  xwl.cmd_params,  {"file": page_path, "module_root": tmp,
                                      "controls": None, "list_fields": False}, "kw"),
        ("itemids", xwl.cmd_itemids, {"file": page_path, "name": None, "dups_only": True,
                                      "suggest": False, "fix": "auto", "controls": None,
                                      "json": False}, "重名组"),
    ):
        try:
            _code, out = _run(fn, **kw)
        except Exception as exc:  # noqa: BLE001
            smoke_fail.append("%s 抛异常: %s: %s" % (label, type(exc).__name__, exc))
            continue
        if want and want not in out:
            smoke_fail.append("%s 输出里没有 %r" % (label, want))
    if smoke_fail:
        failures.extend(smoke_fail)
    else:
        print("[ok]  子命令冒烟：paths / sqlrefs / params / itemids 均可直接调用")

    # ---- 13. new：从零生成（内置骨架 / 设计器键序 / 拒绝覆盖 / 补齐缺键）----
    new_fail: list[str] = []
    a_sql = os.path.join(tmp, "new_sql.xwl")
    code, _out = _run(xwl.cmd_new, out=a_sql, kind="sql", from_json=None, title="出库单查询",
                      roles=None, eol="lf", indent=1, force=False, dry_run=False,
                      node=None, no_js=True)
    if code != 0:
        new_fail.append("new --kind sql 返回 %d" % code)
    else:
        _t, _b, o = xwl.load_xwl(a_sql)
        if list(o.keys()) != list(xwl._PAGE_KEYS):
            new_fail.append("new 生成的顶层键序不是设计器键序: %s" % list(o.keys()))
        c2, cout = _run_check([a_sql], None)
        if c2 != 0:
            new_fail.append("new 的产出没通过 check:\n%s" % cout)
        cb = io.StringIO()
        with contextlib.redirect_stdout(cb):
            rc2 = xwl.cmd_sqlrefs(type("NS", (), {"file": a_sql})())
        if rc2 != 0:
            new_fail.append("new --kind sql 的 {#sql#} 与 serverScript 不自洽:\n%s" % cb.getvalue())

    # 默认必须拒绝覆盖已存在文件，且不得改动原文件
    before = open(a_sql, "rb").read()
    code, _out = _run(xwl.cmd_new, out=a_sql, kind="page", from_json=None, title="X",
                      roles=None, eol="lf", indent=1, force=False, dry_run=False,
                      node=None, no_js=True)
    if code != 2 or open(a_sql, "rb").read() != before:
        new_fail.append("new 未拒绝覆盖已存在文件（exit=%d）" % code)

    # --from-json：补齐缺失的页面钥匙，但不许覆盖用户给的值
    inc_p = os.path.join(tmp, "inc.json")
    with open(inc_p, "w", encoding="utf-8") as f:
        json.dump({"hidden": False, "children": [], "roles": {"demo": 1}, "title": "残缺页"},
                  f, ensure_ascii=False)
    fixd = os.path.join(tmp, "fixed.xwl")
    code, _out = _run(xwl.cmd_new, out=fixd, kind="page", from_json=inc_p, title="",
                      roles=None, eol="lf", indent=1, force=False, dry_run=False,
                      node=None, no_js=True)
    _t, _b, o2 = xwl.load_xwl(fixd)
    if list(o2.keys()) != list(xwl._PAGE_KEYS):
        new_fail.append("--from-json 未按设计器键序补齐: %s" % list(o2.keys()))
    if o2.get("roles") != {"demo": 1} or o2.get("title") != "残缺页":
        new_fail.append("--from-json 覆盖了用户给的值: roles=%s title=%s"
                        % (o2.get("roles"), o2.get("title")))
    if new_fail:
        failures.extend(new_fail)
    else:
        print("[ok]  new：生成物可 check + sqlrefs、拒绝覆盖、--from-json 按设计器键序补齐")

    # ---- 14. folders：未登记/悬空检出；--register 幂等、保键序、保单行 ----
    fd = os.path.join(tmp, "folder_case")
    os.makedirs(fd, exist_ok=True)
    fj = os.path.join(fd, "folder.json")
    with open(fj, "w", encoding="utf-8", newline="") as f:
        f.write('{"hidden":false,"index":[],"title":"样本目录","iconCls":""}')
    for nm in ("a.xwl", "b.xwl"):
        with open(os.path.join(fd, nm), "w", encoding="utf-8", newline="") as f:
            f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    fl_fail: list[str] = []
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"), register=None, dry_run=False)
    if "未登记" not in out:
        fl_fail.append("folders 未报出未登记: %s" % out)
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"),
                     register="a.xwl", dry_run=True)
    if "未写入" not in out or json.load(open(fj, encoding="utf-8")).get("index") != []:
        fl_fail.append("folders --register --dry-run 竟然写了盘")
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"),
                     register="a.xwl", dry_run=False)
    txt = open(fj, "r", encoding="utf-8", newline="").read()
    j = json.loads(txt)
    if j.get("index") != ["a.xwl"]:
        fl_fail.append("register 后 index 不对: %s" % j.get("index"))
    if list(j.keys()) != ["hidden", "index", "title", "iconCls"]:
        fl_fail.append("register 改了 folder.json 的键序: %s" % list(j.keys()))
    if "\n" in txt or "\r" in txt:
        fl_fail.append("register 把单行 folder.json 写成了多行")
    code, out = _run(xwl.cmd_folders, path=os.path.join(fd, "a.xwl"),
                     register="a.xwl", dry_run=False)
    if open(fj, "r", encoding="utf-8", newline="").read() != txt:
        fl_fail.append("重复 register 改动了 folder.json（应幂等）")
    jj = json.loads(txt)
    jj["index"].append("gone.xwl")
    with open(fj, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(jj, ensure_ascii=False, separators=(",", ":")))
    code, out = _run(xwl.cmd_folders, path=fd, register=None, dry_run=False)
    if "悬空" not in out:
        fl_fail.append("folders 未检出 index 悬空项: %s" % out)
    if fl_fail:
        failures.extend(fl_fail)
    else:
        print("[ok]  folders：未登记/悬空检出、register 幂等且保键序保单行形态")

    # ---- 15. paths 的「原路径」必须带 configs 层，照抄就该改对地方 ----
    p_fail: list[str] = []
    code, out = _run(xwl.cmd_paths, file=a_sql)
    if '["children", 0, "configs", "serverScript"]' not in out:
        p_fail.append("paths 的原路径没带 configs 层（照抄会把字段写到节点根上）:\n%s" % out)
    if '["children", 0, "children", 0, "configs", "sql"]' not in out:
        p_fail.append("paths 的 sql 原路径没带 configs 层:\n%s" % out)
    ops_p = os.path.join(tmp, "ops_from_paths.json")
    with open(ops_p, "w", encoding="utf-8") as f:
        json.dump([{"op": "set", "path": ["children", 0, "configs", "serverScript"],
                    "value": "var sql='PATCHED';"}], f, ensure_ascii=False)
    pt_target = os.path.join(tmp, "paths_patch.xwl")
    with open(pt_target, "wb") as f:
        f.write(open(a_sql, "rb").read())
    code, _out = _run(xwl.cmd_patch, file=pt_target, ops=ops_p, indent=1, eol="auto",
                      dry_run=False, backup=False, node=None, no_js=True)
    _t, _b, o3 = xwl.load_xwl(pt_target)
    mod = o3["children"][0]
    if mod.get("configs", {}).get("serverScript") != "var sql='PATCHED';":
        p_fail.append("照抄 paths 的原路径没改到 configs.serverScript")
    if "serverScript" in mod:
        p_fail.append("照抄 paths 的原路径把字段写到了节点根上")
    if p_fail:
        failures.extend(p_fail)
    else:
        print("[ok]  paths 原路径带 configs 层，照抄即可改到正确位置")

    # ---- 16. schema --skeleton 只输出该控件允许的键 ----
    reg = os.path.join(tmp, "mini_controls.json")
    with open(reg, "w", encoding="utf-8") as f:
        json.dump({"children": [
            {"id": "dataprovider", "general": {"design": False},
             "configs": {"itemId": {"type": "string"}, "sql": {"type": "sql"}}, "events": {}},
            {"id": "button", "general": {"design": True, "xtype": "button"},
             "configs": {"itemId": {"type": "string"}, "text": {"type": "string"}},
             "events": {"click": {"type": ""}}},
        ]}, f, ensure_ascii=False)
    s_fail: list[str] = []
    code, out = _run(xwl.cmd_schema, type="dataprovider", controls=reg, list=False,
                     tree=False, skeleton=True)
    if '"events"' in out:
        s_fail.append("dataprovider（0 个 events）的骨架不该带 events 键")
    if '"text"' in out:
        s_fail.append("dataprovider 的 configs 里不该有 text（不是它的合法键）")
    code, out = _run(xwl.cmd_schema, type="button", controls=reg, list=False,
                     tree=False, skeleton=True)
    if '"text"' not in out or '"click"' not in out:
        s_fail.append("button 的骨架应含 text + click:\n%s" % out)
    if s_fail:
        failures.extend(s_fail)
    else:
        print("[ok]  schema --skeleton：只含该控件允许的键，events 键按该控件实际事件决定")

    # ---- 17. 文档一致性守卫（跨文件）----
    # 这几类缺陷人眼复核必漏（实测：一轮评审发现的 4 个缺陷里 3 个是"改了这处忘了那处"），所以机械扫。
    doc_fail: list[str] = []
    root = os.path.dirname(HERE)
    doc_names = ["SKILL.md", "README.md", "CHANGELOG.md",
                 "references/controls.md", "references/sql-fragments.md", "references/measured-data.md"]
    docs: dict = {}
    for nm in doc_names:
        fp = os.path.join(root, nm.replace("/", os.sep))
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8", newline="") as fh:
                docs[nm] = fh.read().splitlines()

    # 17a emoji 不得进标题
    for nm, ls in docs.items():
        for i, l in enumerate(ls, 1):
            if l.startswith("#") and any(ch in l for ch in ("⚠", "❗", "✅", "❌")):
                doc_fail.append("%s:%d 标题里混入 emoji" % (nm, i))

    # 17b README 与 SKILL 不得有逐字重复的表格行（同一张表不该在两处各写一遍）
    def _trows(ls):
        return {l.strip() for l in ls
                if l.strip().startswith("|") and l.strip().endswith("|")
                and not set(l.strip()) <= set("|-: ")}
    if "README.md" in docs and "SKILL.md" in docs:
        dup = _trows(docs["README.md"]) & _trows(docs["SKILL.md"])
        if dup:
            doc_fail.append("README 与 SKILL 有 %d 行表格逐字重复（同一张表别写两处）：%s"
                            % (len(dup), sorted(dup)[0][:70]))

    # 17c 「见 N.M」必须能在本文件里找到对应小节（带文件名线索的行是跨文件引用，跳过）
    for nm, ls in docs.items():
        heads = "\n".join(l for l in ls if l.startswith("#"))
        for i, l in enumerate(ls, 1):
            if re.search(r"`?[\w-]+\.md`?|references/", l):
                continue
            for m in re.finditer(r"见\s*\*{0,2}(\d\.\d)", l):
                if ("### " + m.group(1)) not in heads:
                    doc_fail.append("%s:%d 引用「见 %s」但本文件没有该编号小节" % (nm, i, m.group(1)))

    # 17d 去项目化：文档与工具里不得出现任何具体工程的路径（skill 是通用资产）
    # 判据用**结构**而不是业务名黑名单 —— 后者等于把业务名又写进代码里。
    #   · `m?xwl=` 后面必须是占位符（`<…>` / `…`），只有框架端点 `common/` 例外；
    #   · 出现的 `.xwl` 路径若是**多段**且不含占位符标记、又不属于平台自带目录，即视为真实业务路径。
    mref = re.compile(r"m\?xwl=(?!<|…)([A-Za-z0-9_./-]+)")
    paths = re.compile(r"[A-Za-z0-9_<>.…/-]+\.xwl")
    plat = re.compile(r"(^|/)(dev|examples|wb)/", re.I)
    marks = re.compile(r"[<…]|xxx|Xxx|file\.xwl$|page\.xwl$|out\.xwl$")
    for nm, ls in docs.items():
        for i, l in enumerate(ls, 1):
            for m in mref.finditer(l):
                g = m.group(1)
                if not (g.startswith("common/") or g.lower().startswith("xxx")):
                    doc_fail.append("%s:%d `m?xwl=%s` 不是占位符（换成 <模块>/… 写法）"
                                    % (nm, i, g[:40]))
            if marks.search(l):     # 该行已用占位符 / 示意名写法，路径无须再查
                continue
            for m in paths.finditer(l):
                s = m.group(0)
                if "/" not in s or plat.search(s):
                    continue
                doc_fail.append("%s:%d 出现多段真实路径 `%s`（应改成占位符写法）" % (nm, i, s))
    with open(os.path.join(HERE, "xwl.py"), "r", encoding="utf-8") as fh:
        for i, l in enumerate(fh.read().splitlines(), 1):
            for m in mref.finditer(l):
                g = m.group(1)
                if not (g.startswith("common/") or g.lower().startswith("xxx")):
                    doc_fail.append("scripts/xwl.py:%d `m?xwl=%s` 不是占位符" % (i, g[:40]))

    if doc_fail:
        failures.extend(doc_fail[:12])
    else:
        print("[ok]  文档守卫：emoji 未入标题 / README↔SKILL 无重复表格 / 编号引用可解析 / 无业务路径残留")

    print()
    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        print(f"=== selftest FAIL（{len(failures)} 项）")
        return 1
    print("=== selftest ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
