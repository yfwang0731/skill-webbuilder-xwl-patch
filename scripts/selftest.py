#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py —— xwl.py 的自检（不依赖任何外部 xwl 文件）

内置样本覆盖：
  · `check` 的格式判定（1 个合法样本 + 5 种典型破坏）
  · `edit` 的锚点拒绝与正例（含 CRLF / BOM 是否保持）
  · `expand` 的排版形态与语义等价（含 `--safe` 模式）
  · `patch` 的结构级编辑（新节点事件 JS、自动续行）
  · `new` 的从零生成（设计器真实键序 / 拒绝覆盖 / `--from-json` 补齐缺键）
  · `folders` 的 index 一致性检查与 `--register`（幂等 / 保键序 / 保单行形态 /
    **给目录 + `--register` 必须显式报错**——它曾经是静默无效）
  · `paths` 的「原路径」必须带 configs 层（照抄即可改对位置）
  · `schema --skeleton` 只含该控件允许的键，events 键按该控件实际事件决定
  · `node_check_many` 与逐段 `node_check` **必须逐项等价**（批量优化不许改变结论；
    守的是 CommonJS 与 Script/ESM 的编译语义差异 —— 顶层 `return` / 顶层 `await`）
  · SKILL.md 必须声明**平台边界、调用入口与规模约束**（这三样容易被精简掉，钉住）
  · **非 UTF-8 控制台（cp1252）下输出中文不能崩** —— Windows 上是这个编码，
    本地开发环境却是 UTF-8，所以只有 CI 的 windows job 能发现（第一次上 CI 就这么挂的）
  · **跨盘符不能崩**：`os.path.relpath` 不带 `start` 时在 Windows 跨盘符会抛 ValueError
    （CI 仓库在 D:、TEMP 在 C:），用桩把 relpath 变成必抛来验证兜底（第二次 CI 挂在它上面）
  · 文档一致性守卫（跨文件）：emoji 未入标题 / **任意两文档间**无逐字重复的表格行 /
    「§N.M」「见 N.M」「第 N 章」「第 N 步」引用可解析（**含跨文件**：`见 SKILL.md 2.1`、
    `controls.md §4.2`、`§五`）/ 本地链接都存在 / **外移点两侧都在**（主文档有指针 + references 有承载内容）/
    **格式五项**（表格列数 / 标题跳级 / 代码块闭合 / 行尾空白 / 末尾换行）/
    **自称数字与实际一致**（FAQ / 清单 / 反模式 / prompt 条数、清单拆分、工具表覆盖全部子命令）/
     **索引一致**（导航表目标存在、references 无孤儿无悬空、README 目录树 ↔ 磁盘、
     SKILL 的「N 份参考材料」其 N = 清单条数 = 磁盘文件数）/
     文档与工具里无业务路径与业务字段名（skill 是通用资产）
  · `dump` 冒烟（它是最后一个补上冒烟覆盖的子命令）
  · `@itemId` 寻址（唯一可定位 / 重名拒绝并给候选清单 / `#N` 点名与越界）
  · itemId 重名分级（列 benign / 按钮+被引用 error / 唯一 normalName benign / 未被引用 warn）
  · `params` 的两条通路识别与注释剔除
  · **写盘失败必须给可读 `[FAIL]` + 退出码 2，不得冒 Python traceback** ——
    目标只读 / 父目录不存在 / 路径过长都属「前置条件不满足」。
    （原先 `write_text()` 没兜 `OSError`，5 个子命令 9 个场景抛 traceback，
    而 64 项断言一条都没覆盖写失败 —— 这条就是为此加的）
  · **`edit` 的锚点必须按目标文件的换行归一**（LF 与 CRLF 都要能跨行匹配）——
    原先 `normalize_eol()` 硬编码 CRLF：LF 文件上跨行锚点**永远匹配不到**
    （报「锚点出现次数: 0」，看着像用户写错了锚点），单行锚点 + 多行 new 还会把
    LF 文件写成 CRLF/LF **混用**。另：**把多行拍平时必须有 `[warn]`** ——
    这类损坏 `check` 查不出（压平后仍是合法 JSON），只有 `edit` 这一处能提示。
    （实测样本工程 2780 个 xwl：1878 全 CRLF / 902 为「单行且末尾无换行符」/ **0 个 LF** ——
    两条路径仍都要覆盖，因为 `expand` 按 `--eol auto` 会把无换行的单行源产出成 LF）
  · **`check` 的 ③ 必须在 CRLF / LF / CR 三种换行下都生效** —— 它原先用
    `text.split("\\r\\n")` 切行，**纯 LF 文件切不出行**（整份成一个元素），于是 ③ 静默退化成
    "只看最后一行"；`new` 的默认产出就是 LF，`expand --eol auto` 也会产出 LF。
    同根因还让纯 CR 文件同时得到「存在 N 处裸 CR」的 FAIL 与「该文件是单行形态（无任何换行）」的
    note（自相矛盾）。另：`patch` 对**换行混用**的源会静默统一、`--indent≠1` 会静默产出
    与设计器不一致的排版、对**无换行的单行源**会回退 LF 并整份展开 —— 这三条都必须有 `[warn]`
    / 明确说明（`--indent` 是唯一能主动击穿「diff 只含本次改动」的入口）。
  · **值里的孤立代理项不得让工具崩** —— `patch` 原先在打印字节数时
    `out.encode("utf-8")` 抛 UnicodeEncodeError（裸 traceback + rc=1）。
    `_quote` 现在按 org.json 的写法转义成 `\\uXXXX`（语义仍等价，回读一致）；
    `_write_file` 与字节数展示一并兜住（1.2.2 那次只兜了 `OSError`，`UnicodeError` 不是它的子类）。
  · **`diffguard`：相对 git 基线检测「多行被压平」** —— 补的是 §2.3 承认的洞
    （压平后文件**仍合法**，`check` 与 `node --check` 都放行，原先只能靠人工 `git diff`）。
    判据是**双条件**（续行符净减少 **且** 最长行显著变长），所以这里**正反两侧都要钉**：
    "压平必须报"与"合法删减一段多行 JS / 单行变长必须不报"同等重要 ——
    只留前半条，这个守卫会被日常改动淹没（负向测试：去掉最长行那条 → 立刻报误报）。
    另钉住降级路径：新文件、非 git 目录 → `[note]` 跳过 + rc=0；`--strict` 下跳过即 rc=2；
    `--rev` 写错是用法错、恒 rc=2（且不得被说成"新增文件"）。
  · **SKILL.md 的 frontmatter 有 1024 上限** —— description 是路由真正读的字段，
    每补一个触发词都在吃这个额度。1.3.0 加 `diffguard` 时曾把它撑到 **1029**，
    所以把 description 与整个 frontmatter 块都钉住。

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
import subprocess
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


def _run(fn, **kw):
    """跑一个 `cmd_xxx` 并把它的 stdout 收进 buffer，返回 (rc, text)。

    放在模块级是因为它被两组以上用到（子命令冒烟 / 平台回归）——
    原先是 main 里的嵌套函数，main 拆成多个函数后就跨了作用域。
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(type("NS", (), kw)())
    return code, buf.getvalue()


def _check_basics(tmp, node, failures, write) -> None:
    """前置样本 + check 破坏用例 + edit + expand + patch（第 0~7 组）"""

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


def _check_params_paths(tmp, node, failures, write) -> None:
    """params 两条通路 + 注释剔除与多容器 out（第 8~9 组）"""

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

    # ---- 9–10. 注释剔除 / 多容器 out / 剔注释不粘连 ----
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


def _check_itemids(tmp, node, failures, write) -> None:
    """@itemId 寻址、重名分级、引用判定、防御性取值、章节顺序（第 11a~11k 组）"""

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
                     "itemId", "常见问题", "自检清单"]
        if got_order == want_order and all(k in t for k, t in zip(want_keys, [x for x in titles if x.startswith("## ") and x[3] in want_order])):
            print("[ok]  SKILL.md 章节顺序符合语义分组（认知→格式→操作→专题→经验→收尾）")
        else:
            failures.append("SKILL.md 章节顺序错位: %s" % [t[:22] for t in titles])
        if any("单行源" in t for t in titles):
            failures.append("「单行源 vs 多行源」应并入格式章，不该单列一章")
    else:
        print("[note] 未找到 SKILL.md，跳过章节顺序守卫")


def _check_subcommands(tmp, node, failures, write) -> None:
    """子命令冒烟 paths/sqlrefs/params + new + folders + paths 原路径 + schema 骨架（第 12~16 组）"""

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

    smoke_fail = []
    for label, fn, kw, want in (
        ("paths",   xwl.cmd_paths,   {"file": page_path}, "原路径"),
        ("sqlrefs", xwl.cmd_sqlrefs, {"file": page_path}, ""),
        ("params",  xwl.cmd_params,  {"file": page_path, "module_root": tmp,
                                      "controls": None, "list_fields": False}, "kw"),
        ("itemids", xwl.cmd_itemids, {"file": page_path, "name": None, "dups_only": True,
                                      "suggest": False, "fix": "auto", "controls": None,
                                      "json": False}, "重名组"),
        # dump 曾是 14 个子命令里唯一没被冒烟覆盖的（评审发现）
        ("dump",    xwl.cmd_dump,    {"file": page_path}, "itemId"),
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


def _check_docs(tmp, node, failures, write) -> None:
    """文档一致性守卫（跨文件）：重复表格 / 引用可解析 / 格式 / 自称数字 / 索引与节号（第 17~18 组）"""

    # ---- 17. 文档一致性守卫（跨文件）----
    # 这几类缺陷人眼复核必漏（实测：一轮评审发现的 4 个缺陷里 3 个是"改了这处忘了那处"），所以机械扫。
    doc_fail: list[str] = []
    root = os.path.dirname(HERE)
    doc_names = ["SKILL.md", "README.md", "CHANGELOG.md", "references/walkthrough.md",
                 "references/faq.md", "references/checklist.md", "references/anti-patterns.md",
                 "references/controls.md",
                 "references/sql-fragments.md", "references/measured-data.md",
                 "references/js-api.md",
                 ]
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

    # 17b **任意两份文档**之间不得有逐字重复的表格行（同一张表不该在两处各写一遍）。
    #     原来只比 README↔SKILL —— 实测 SKILL↔faq 也会重复（退出码表就是这么漏掉的）。
    def _trows(ls):
        return {l.strip() for l in ls
                if l.strip().startswith("|") and l.strip().endswith("|")
                and not set(l.strip()) <= set("|-: ")}
    _names = [k for k in docs if k != "CHANGELOG.md"]
    for _i in range(len(_names)):
        for _j in range(_i + 1, len(_names)):
            _dup = _trows(docs[_names[_i]]) & _trows(docs[_names[_j]])
            if _dup:
                doc_fail.append("%s 与 %s 有 %d 行表格逐字重复（同一张表别写两处）：%s"
                                % (_names[_i], _names[_j], len(_dup), sorted(_dup)[0][:60]))

    # 17c 「§N.M」/「见 N.M」引用必须可解析 —— **本文件与跨文件都查**。
    #     原来含 `.md` 的行整行跳过 ⇒ 跨文件引用无人管：把 §五/§四 外移时漏掉两处
    #     （SKILL.md 还指向语义已变的小节、measured-data 指向已搬走的 §5.6）。
    #     判定：以该引用**左侧最近的文档名**为归属；没有则归属本文件。
    _fn = re.compile(r"([\w-]+\.md)")
    _heads = {k: "\n".join(l for l in v if l.startswith("#")) for k, v in docs.items()}
    _base = {k: k.split("/")[-1] for k in docs}
    for nm, ls in docs.items():
        # CHANGELOG 是**历史记录**：里面的 `§5.5`→`§5.6` 是「当时的」编号，不按当前结构校验
        # （否则每次重排章节都得回头改历史，而历史本来就该原样留着）。
        if nm == "CHANGELOG.md":
            continue
        for i, l in enumerate(ls, 1):
            for m in re.finditer(r"§(\d)\.(\d)|见\s*\*{0,2}(\d)\.(\d)", l):
                g = m.groups()
                a, b = (g[0], g[1]) if g[0] else (g[2], g[3])
                tgt = nm
                near = list(_fn.finditer(l[: m.start()]))
                if near:
                    cand = [k for k, v in _base.items() if v == near[-1].group(1)]
                    if cand:
                        tgt = cand[0]
                if ("### %s.%s" % (a, b)) not in _heads.get(tgt, ""):
                    doc_fail.append("%s:%d 引用 %s §%s.%s，但该文件没有这个编号小节"
                                    % (nm, i, _base.get(tgt, tgt), a, b))

    # 17c-2 「第 N 章」「第 N 步」也要能解析 —— 原来完全没查这一类引用。
    #     只在**能确定归属 SKILL.md** 时判：本文件是 SKILL，或该行里出现了 SKILL.md。
    #     references 里不带文档名的「第 N 步」多指该文件自己的步骤（如 walkthrough 的教程步骤），不判。
    _cn = "一二三四五六七八九十"
    _sk_lab = set()
    for _l in docs.get("SKILL.md", []):
        _m = re.match(r"^##\s*([" + _cn + r"]+)、", _l)
        if _m:
            _sk_lab.add(_m.group(1))
        _m = re.match(r"^###\s*第\s*(\d)\s*步", _l)
        if _m:
            _sk_lab.add("第" + _m.group(1) + "步")
    for nm, ls in docs.items():
        if nm == "CHANGELOG.md":
            continue
        for i, l in enumerate(ls, 1):
            if nm != "SKILL.md" and "SKILL.md" not in l:
                continue
            for _m in re.finditer(r"第\s*([" + _cn + r"]+)\s*章", l):
                if _m.group(1) not in _sk_lab:
                    doc_fail.append("%s:%d 引用「第%s章」但 SKILL.md 没有该章" % (nm, i, _m.group(1)))
            for _m in re.finditer(r"第\s*(\d)\s*步", l):
                if ("第" + _m.group(1) + "步") not in _sk_lab:
                    doc_fail.append("%s:%d 引用「第%s步」但 SKILL.md 没有该步" % (nm, i, _m.group(1)))

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

    # 17e 文档里指向本地文件的 Markdown 链接必须真的存在
    # 起因：把 FAQ / 自检清单外移到 references/ 时，最容易出现的就是"SKILL.md 指了、
    # 文件却没建 / 后来改名字了"—— 这类断链人眼扫不出来，机械查一下。
    link = re.compile(r"\]\((?!https?:|#)([^)]+\.(?:md|json|yml|py))\)")
    for nm, ls in docs.items():
        base = os.path.dirname(os.path.join(root, nm.replace("/", os.sep)))
        for i, l in enumerate(ls, 1):
            for m in link.finditer(l):
                tgt = os.path.normpath(os.path.join(base, m.group(1)))
                if not os.path.exists(tgt):
                    doc_fail.append("%s:%d 链接指向不存在的文件 -> %s" % (nm, i, m.group(1)))

    # 17f SKILL.md 必须给出「反模式」的入口
    # 起因：SkillHub 评测的 antiPatternFaq 只给 4.5，理由是"反模式内容散在各章、缺少集中章节"。
    # 内容搬到独立文件后，若主文档没有入口 = 等于没搬，所以钉住。
    if "SKILL.md" in docs:
        if not any("anti-patterns.md" in l for l in docs["SKILL.md"]):
            doc_fail.append("SKILL.md 没有指向 references/anti-patterns.md 的入口")

    # 17g **外移点两侧都还在**：主文档留了指针 + 目标文件有承载内容。
    # 起因：把 §五 5.4 / §四 4.1 / §二 2.4 / §七 7.1 的正文搬进 references 后，
    # 任何一侧后来被删或改名，都会变成「主文档说去哪看、去了却没有」—— 这类失义机器可查。
    _splits = [
        ("第五章 5.4 四条通路", "SKILL.md", "references/js-api.md",
         ["Wb.request", "Wb.open", "Wb.upload", "Wb.requestAg"]),
        ("第 4 步 逐项判据", "SKILL.md", "references/faq.md", ["无 BOM", "换行一致", "重名"]),
        ("4.1 退出码与约定", "SKILL.md", "references/faq.md", ["退出码"]),
        ("2.4 写回算法", "SKILL.md", "references/measured-data.md",
         ["toString(1)", "syncSave", "updateModule"]),
        ("7.1 框架侧源码", "SKILL.md", "references/measured-data.md",
         ["ComponentManager", "unregister"]),
        ("FAQ 全量问答", "SKILL.md", "references/faq.md", ["怎么排查"]),
        ("改完自检清单", "SKILL.md", "references/checklist.md", ["- [ ]"]),
        ("反模式清单", "SKILL.md", "references/anti-patterns.md", ["为什么诱人"]),
        ("端到端实操", "SKILL.md", "references/walkthrough.md", ["第 1 步"]),
    ]
    for _lab, _src, _dst, _keys in _splits:
        if _dst not in "\n".join(docs.get(_src, [])):
            doc_fail.append("外移点「%s」：%s 里没有指向 %s 的指针" % (_lab, _src, _dst))
        _body = "\n".join(docs.get(_dst, []))
        _miss = [k for k in _keys if k not in _body]
        if _miss:
            doc_fail.append("外移点「%s」：%s 里找不到承载内容 %s" % (_lab, _dst, _miss))

    # 17h 文档格式：表格列数一致 / 标题不跳级 / 代码块闭合 / 无行尾空白 / 末尾有换行。
    #     起因：外移与重排章节时最容易留下这五类瑕疵，而且人眼扫不出来。
    for nm, _lines in docs.items():
        _cur = None
        _fence = 0
        _prev = 0
        for i, l in enumerate(_lines, 1):
            s = l.strip()
            if s.startswith("```"):
                _fence += 1
            if s.startswith("|") and s.endswith("|"):
                _body = s.replace("\\|", "\x00")
                _nc = _body.count("|") - 1
                if set(_body) <= set("|-: "):
                    _cur = _nc
                elif _cur is not None and _nc != _cur:
                    doc_fail.append("%s:%d 表格本行 %d 格、表头 %d 格（表格会渲染错）" % (nm, i, _nc, _cur))
            else:
                _cur = None
            if _fence % 2 == 0 and re.match(r"^#{1,6} ", l):
                _lv = len(l) - len(l.lstrip("#"))
                if _prev and _lv > _prev + 1:
                    doc_fail.append("%s:%d 标题跳级（%s→%s）" % (nm, i, "#" * _prev, "#" * _lv))
                _prev = _lv
            if l != l.rstrip():
                doc_fail.append("%s:%d 行尾有多余空白" % (nm, i))
        if _fence % 2:
            doc_fail.append("%s 代码块未闭合（``` 出现 %d 次）" % (nm, _fence))
        with open(os.path.join(root, nm.replace("/", os.sep)), "rb") as _fh:
            if not _fh.read().endswith(b"\n"):
                doc_fail.append("%s 末尾没有换行" % nm)

    # 17i 文档自称的数字必须与实际一致 —— 外移/增删内容后最容易过期的一类。
    #     只按**具体句式**精确核对，不用「N 条」这类粗匹配（那会把反模式条数套到清单上）。
    import json as _json
    _txt = {k: "\n".join(v) for k, v in docs.items()}
    _real = {
        "faq": len(re.findall(r"^\*\*Q：", _txt.get("references/faq.md", ""), re.M)),
        "ck": len(re.findall(r"- \[ \]", _txt.get("references/checklist.md", ""))),
        "ap": len(re.findall(r"^### ", _txt.get("references/anti-patterns.md", ""), re.M)),
    }
    with open(os.path.join(root, "test-prompts.json"), "r", encoding="utf-8") as _fh:
        _real["tp"] = len(_json.loads(_fh.read()))
    _sk_txt = _txt.get("SKILL.md", "")
    _rm_txt = _txt.get("README.md", "")
    _claims = []
    for _m in re.finditer(r"\*\*(\d+)\s*条\*\*高频问题", _sk_txt):
        _claims.append(("SKILL §八 FAQ 条数", int(_m.group(1)), _real["faq"]))
    for _m in re.finditer(r"faq\.md\s+#\s*(\d+)\s*条", _rm_txt):
        _claims.append(("README 的 FAQ 条数", int(_m.group(1)), _real["faq"]))
    for _m in re.finditer(r"\*\*(\d+)\s*项\*\*清单", _sk_txt):
        _claims.append(("SKILL §九 清单项数", int(_m.group(1)), _real["ck"]))
    for _m in re.finditer(r"checklist\.md\s+#\s*(\d+)\s*项", _rm_txt):
        _claims.append(("README 的清单项数", int(_m.group(1)), _real["ck"]))
    for _m in re.finditer(r"anti-patterns\.md\s+#\s*(\d+)\s*条", _rm_txt):
        _claims.append(("README 的反模式条数", int(_m.group(1)), _real["ap"]))
    for _m in re.finditer(r"test-prompts\.json\s+#\s*(\d+)\s*条", _rm_txt):
        _claims.append(("README 的 prompt 条数", int(_m.group(1)), _real["tp"]))
    # 参考清单里的「清单项数」也要查 —— 它曾经漏网：正文 §九 改成了 30 项，
    # 而同一文件的参考材料清单那行还写着 29 项（旧守卫只认 `**N 项**清单` 那种句式）。
    for _m in re.finditer(r"改完自检清单\*\*：(\d+) 项", _sk_txt):
        _claims.append(("SKILL 参考清单的清单项数", int(_m.group(1)), _real["ck"]))
    for _lab, _got, _exp in _claims:
        if _got != _exp:
            doc_fail.append("自称数字不符：%s 写 %d，实际 %d" % (_lab, _got, _exp))
    # 注意：上面那几条针对 **README** 的计数断言（`faq.md # N 条` 等）现在是**惰性**的 ——
    # README 的目录树已不再写各文件的条数（两处维护必然漂移），计数只留在各文件自己 + SKILL。
    # 它们留着是为了"哪天有人把计数写回 README 时立刻查"，不是死代码。

    # 17h 测试 prompt 的**覆盖度**（比"条数对不对"有用得多）：每个子命令至少要被一条 prompt
    #     提到 —— 否则"新加了命令，但评测语料里没人测它"会一直没人发现。
    #     实测：1.3.0 的招牌能力 `diffguard` 在 11 条里出现 **0 次**（其余 14 个命令都有），
    #     而三种评审方法（darwin / TRACE / 文档审计）**没有一个能看见这件事**。
    try:
        with open(os.path.join(root, "test-prompts.json"), "r", encoding="utf-8") as _fh:
            _tps = json.load(_fh)
        _tp_text = " ".join((str(t.get("prompt", "")) + " " + str(t.get("expected", "")))
                            for t in _tps)
        with open(os.path.join(HERE, "xwl.py"), "r", encoding="utf-8") as _fh:
            _allsubs = sorted(set(re.findall(r'sub\.add_parser\(\s*"([a-z]+)"', _fh.read())))
        _uncovered = [_s for _s in _allsubs if _s not in _tp_text]
        if _uncovered:
            doc_fail.append("test-prompts.json 里没有任何 prompt 覆盖这些子命令：%s" % _uncovered)
    except (OSError, ValueError) as _exc:
        doc_fail.append("test-prompts.json 读不了或不是合法 JSON：%s" % _exc)

    # 17i 打包元数据必须与 SKILL.md 一致。`metadata.json` 是**平台与本地评测器读的**打包声明
    #     （TRACE 的 T/R/E 维直接看它），却一直没有守卫 —— 版本号 / name / references 列表
    #     一旦漂移，评测读到的就是错的。而三种评审方法都只看工作树，**看不出这个**。
    _mdp = os.path.join(root, "metadata.json")
    if not os.path.exists(_mdp):
        doc_fail.append("缺少 metadata.json（SkillHub 打包与平台评测会读它）")
    else:
        try:
            with open(_mdp, "r", encoding="utf-8") as _fh:
                _md = json.load(_fh)
            _skv = re.search(r"^version:\s*(\S+)", _sk_txt, re.M)
            if _skv and _md.get("version") != _skv.group(1):
                doc_fail.append("metadata.json 的 version=%r 与 SKILL.md 的 %r 不一致"
                                % (_md.get("version"), _skv.group(1)))
            _skn = re.search(r"^name:\s*(\S+)", _sk_txt, re.M)
            if _skn and _md.get("name") != _skn.group(1):
                doc_fail.append("metadata.json 的 name=%r 与 SKILL.md 的 %r 不一致"
                                % (_md.get("name"), _skn.group(1)))
            _mdrefs = sorted(os.path.basename(str(x)) for x in (_md.get("references") or []))
            _dkrefs = sorted(f for f in os.listdir(os.path.join(root, "references"))
                             if f.endswith(".md"))
            if _mdrefs != _dkrefs:
                doc_fail.append("metadata.json 的 references 列表与磁盘不一致：声明 %s / 实际 %s"
                                % (_mdrefs, _dkrefs))
        except (OSError, ValueError) as _exc:
            doc_fail.append("metadata.json 读不了或不是合法 JSON：%s" % _exc)

    # 清单的「改已有文件 X + 新建文件 Y」拆分在 SKILL.md 里出现两次（§九 与参考清单），两处都要对
    _grp2: dict = {}
    _g2 = None
    for _l in _txt.get("references/checklist.md", "").split("\n"):
        if _l.startswith("## "):
            _g2 = _l[3:].strip()
            _grp2[_g2] = 0
        elif _g2 and re.match(r"^- \[ \]", _l):
            _grp2[_g2] += 1
    _new2 = sum(v for k, v in _grp2.items() if "新建" in k)
    _old2 = sum(_grp2.values()) - _new2
    for _m in re.finditer(r"（改已有文件 (\d+)(?: 项)? \+ 新建文件 (\d+)(?: 项)?）", _sk_txt):
        if int(_m.group(1)) != _old2 or int(_m.group(2)) != _new2:
            doc_fail.append("清单拆分不符：SKILL.md 写「%s + %s」，实际「%d + %d」"
                            % (_m.group(1), _m.group(2), _old2, _new2))
    # 17k 判据描述一致性：`diffguard` 的**主判据是定义级**的（工作区某行 == 基线连续多行
    #     去掉续行符后拼接），而「续行符净减少 且 最长行显著变长」只是**粗筛**。
    #     凡把后者**当成判据来陈述**（"判据是…"/"比…"）却不标明"粗筛"的，都是升级判据时
    #     漏改的旧描述 —— 实测漏过 README 工具速查表 / checklist / faq 三处（正文改了、侧翼没跟上）。
    #     注意判据要"窄"：仅仅**提到**「最长行」不算 —— SKILL.md 2.3 有一段专门复盘
    #     "为什么不能只用最长行这一条"，那里提到它是**正确**的（误报就出在这）。
    #     围栏内的**工具真实输出**也要跳过（那里出现"最长行"是统计行原文）。
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":
            continue
        _fence = False
        for _i, _l in enumerate(_ls):
            if _l.strip().startswith("```"):
                _fence = not _fence
                continue
            if _fence:
                continue
            _asserts = ("续行符净减少" in _l
                        or ("最长行" in _l and ("判据" in _l or "比" in _l)))
            if _asserts:
                _win = "\n".join(_ls[max(0, _i - 5): _i + 6])
                if "粗筛" not in _win:
                    doc_fail.append("%s:%d 把「续行符净减少 / 最长行」当成判据陈述，"
                                    "却没标明它只是**粗筛**（主判据是定义级的）：%s"
                                    % (_nm, _i + 1, _l.strip()[:60]))
    _m = re.search(r"\*\*(\d+)\s*项\*\*清单（改已有文件\s*(\d+)\s*项\s*\+\s*新建文件\s*(\d+)\s*项）", _sk_txt)
    if _m:
        _grp, _g = {}, None
        for _l in _txt.get("references/checklist.md", "").split("\n"):
            if _l.startswith("## "):
                _g = _l[3:].strip()
                _grp[_g] = 0
            elif _g and re.match(r"^- \[ \]", _l):
                _grp[_g] += 1
        _new = sum(v for k, v in _grp.items() if "新建" in k)
        _old = sum(_grp.values()) - _new
        if _old != int(_m.group(2)) or _new != int(_m.group(3)):
            doc_fail.append("清单拆分不符：写「%s + %s」，实际「%d + %d」"
                            % (_m.group(2), _m.group(3), _old, _new))
    with open(os.path.join(HERE, "xwl.py"), "r", encoding="utf-8") as _fh:
        _subs = set(re.findall(r'sub\.add_parser\(\s*"([a-z]+)"', _fh.read()))
    # 取**第一列**里出现的全部反引号命令名 —— 一行里可以合并几个命令
    # （如 ``| `sql` / `events` | …``），所以不能只认行首那一个。
    _tbl = set()
    for _ln in _sk_txt.splitlines():
        if not _ln.startswith("|") or _ln.count("|") < 2:
            continue
        _cell = _ln.split("|")[1]
        _tbl.update(re.findall(r"`([a-z]+)[^`]*`", _cell))
    if _subs - _tbl:
        doc_fail.append("SKILL 工具表没覆盖这些子命令：%s" % sorted(_subs - _tbl))

    # 17j 索引与节号：中文节号（`§五` / `§7`）可解析 + 导航表目标存在 +
    #     references 无孤儿/悬空 + README 目录树里的文件都在磁盘上。
    def _has_sec(relp, key):
        for _l in docs.get(relp, []):
            if re.match(r"^##\s*" + re.escape(key) + r"\s*[、.]", _l):
                return True
        return False

    _cn2 = "一二三四五六七八九十"
    for nm, ls in docs.items():
        if nm == "CHANGELOG.md":
            continue
        for i, l in enumerate(ls, 1):
            for _m in re.finditer(r"§\s*([" + _cn2 + r"]+|\d+)(?!\s*\.\d)", l):
                _near = list(_fn.finditer(l[: _m.start()]))
                _tg = None
                if _near:
                    _c = [k for k, v in _base.items() if v == _near[-1].group(1)]
                    if _c:
                        _tg = _c[0]
                elif nm.startswith("references/") and "SKILL.md" in l:
                    _tg = "SKILL.md"
                if _tg is None:
                    continue      # 「见 §1」这类缩写没有文档名，判不了归属，放过
                if not _has_sec(_tg, _m.group(1)):
                    doc_fail.append("%s:%d 引用 §%s，但 %s 没有该编号小节"
                                    % (nm, i, _m.group(1), _base.get(_tg, _tg)))
    for i, l in enumerate(docs.get("SKILL.md", []), 1):
        _m = re.match(r"^\|\s*[^|]+\|\s*([^|]+)\|\s*$", l)
        if not _m:
            continue
        for _cm in re.finditer(r"第\s*([" + _cn2 + r"]+)\s*章", _m.group(1)):
            if not _has_sec("SKILL.md", _cm.group(1)):
                doc_fail.append("SKILL.md:%d 导航表指向「第%s章」，但没有这一章" % (i, _cm.group(1)))
        for _fm in re.finditer(r"references/([a-z0-9-]+\.md)", _m.group(1)):
            if not os.path.exists(os.path.join(root, "references", _fm.group(1))):
                doc_fail.append("SKILL.md:%d 导航表指向 %s，但文件不存在" % (i, _fm.group(1)))
    _listed = set(re.findall(r"references/([a-z0-9-]+\.md)", _sk_txt))
    _on_disk = set(f for f in os.listdir(os.path.join(root, "references")) if f.endswith(".md"))
    if _on_disk - _listed:
        doc_fail.append("references 里有 SKILL.md 从未提到的文件（孤儿）：%s" % sorted(_on_disk - _listed))
    if _listed - _on_disk:
        doc_fail.append("SKILL.md 提到的 references 文件不存在：%s" % sorted(_listed - _on_disk))
    # 17j-2 「N 份参考材料」的 N、清单条数、磁盘文件数 三者必须相等。
    #   曾漏过一次：写「五份」只列 5 条，而磁盘上已经有 8 个 —— 读者会以为只有五份。
    _cn_map = {c: i + 1 for i, c in enumerate(_cn2)}
    _sks = _sk_txt.split("\n")
    for _i, _l in enumerate(_sks):
        _m = re.search(r"([一二三四五六七八九十]+|\d+)\s*份参考材料", _l)
        if not _m:
            continue
        _raw = _m.group(1)
        _n = _cn_map.get(_raw) or (int(_raw) if _raw.isdigit() else -1)
        _cnt = 0
        for _j in range(_i + 1, len(_sks)):
            _s = _sks[_j]
            if _s.startswith("- [`references/"):
                _cnt += 1
            elif _s.strip() and not _s.startswith(("- ", " ", ">")):
                break
        if _n != _cnt or _cnt != len(_on_disk):
            doc_fail.append("SKILL.md 的「%s 份参考材料」与清单 %d 条 / 磁盘 %d 个不一致"
                            % (_raw, _cnt, len(_on_disk)))
        break
    _tree = re.findall(r"[├└]──\s+([A-Za-z0-9_.\-]+\.(?:md|py|json))", _rm_txt)
    _disk = set()
    for _r, _dn, _fs in os.walk(root):
        if ".git" in _r or "__pycache__" in _r:
            continue
        for _x in _fs:
            _disk.add(_x)
            _disk.add(os.path.relpath(os.path.join(_r, _x), root).replace(os.sep, "/"))
    _ghost = [x for x in _tree if x not in _disk]
    if _ghost:
        doc_fail.append("README 目录树列了磁盘上没有的文件：%s" % _ghost)

    # 17j-3 索引双向登记：SKILL.md 里提到的每个 `references/*.md` 都必须在「怎么用」那张
    #     **参考材料索引表**里占一行（那张表是唯一的材料索引）。起因是压缩时把材料清单从
    #     §四 挪进「怎么用」表 —— 挪完若漏登记一个，读者就再也找不到它了。
    _idx: set[str] = set()
    _in_idx, _got_row = False, False
    for _l in _sk_txt.splitlines():
        if "兼作参考材料索引" in _l:
            _in_idx = True
            continue
        if not _in_idx:
            continue
        if _l.startswith("|"):
            _got_row = True
            _idx.update(re.findall(r"references/([a-z0-9-]+\.md)", _l))
        elif _got_row and not _l.strip():
            break      # 表收了行之后再遇到空行才算结束（marker 与表头之间本来就有空行）
    if not _idx:
        doc_fail.append("SKILL.md 的参考材料索引表为空或找不到（「兼作参考材料索引」那张表）")
    _unreg = sorted(set(re.findall(r"references/([a-z0-9-]+\.md)", _sk_txt)) - _idx)
    if _unreg:
        doc_fail.append("SKILL.md 提到但**未登记进参考材料索引表**的文件：%s" % _unreg)

    # 17j-4 篇幅上限：**不是目标，是防回弹的护栏**。压缩过一次之后，新增内容很容易又堆回
    #     SKILL.md；到了上限就该问"这条是不是该下沉到 references/"。数字留了余量，
    #     正常的小幅增补不会触发。
    for _nm, _cap in (("SKILL.md", 800), ("README.md", 140)):
        _n = len(docs.get(_nm, []))
        if _n > _cap:
            doc_fail.append("%s 已 %d 行，超过 %d 行上限（新增内容请考虑下沉到 references/）"
                            % (_nm, _n, _cap))

    # 17j-5 排他性断言（**同义改写**版）：说压平「只有 git diff / 只能靠人工」能发现的句子，
    #     它所在的**小节**里必须出现 `diffguard`。
    #     上一轮的守卫只匹配字面词「续行符净减少 / 最长行」，于是"只有 `git diff` 能发现"
    #     这类同义改写全漏了 —— 实测漏掉 2 处，其中一处还是**文件内部自相矛盾**
    #     （同文件别处正说 diffguard 是唯一的自动化防线）。
    #     判据按**小节**取而不是按行取：同一节里出现过 diffguard 就算交代过了。
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":      # 历史文档，按当时的事实记，不回改
            continue
        _sec_start, _fence = 0, False
        for _i, _l in enumerate(_ls):
            if _l.strip().startswith("```"):
                _fence = not _fence
                continue
            if _fence:
                continue
            if re.match(r"^#{1,4}\s", _l):
                _sec_start = _i
                continue
            if not re.search(r"(只有|唯一|只能靠)[^。；\n]{0,30}(git diff|人工|手动)", _l):
                continue
            _sec_end = len(_ls)
            for _j in range(_i + 1, len(_ls)):
                if re.match(r"^#{1,4}\s", _ls[_j]):
                    _sec_end = _j
                    break
            _sec = "\n".join(_ls[_sec_start:_sec_end])
            if ("压平" in _sec or "压成一行" in _sec or "合并行" in _sec) \
                    and "diffguard" not in _sec:
                doc_fail.append("%s:%d 「%s」说压平只有 `git diff` / 只能靠人工能发现，"
                                "但该小节里没有 `diffguard`（它已能自动发现）"
                                % (_nm, _i + 1, _l.strip()[:48]))

    # 17j-6 承诺的输出文案必须真的存在：SKILL.md 里用反引号引的、以行首标记开头的
    #     **工具输出字面量**，其内容必须在 `xwl.py` 里找得到。
    #     起因：SKILL.md 曾承诺「`edit` 写盘后给 `[note] 该文件是 LF 换行（…）`」，
    #     而代码对**无换行**文件走的是另一个分支（`[note] 该文件是单行形态（…）`）——
    #     文档承诺了一个工具不会打印的提示。这类"文案承诺"只有对着实现查才看得出。
    #     判据要窄：只看 `[note]/[warn]/[FAIL]/[ok]` 开头且正文 ≥8 字的；
    #     带省略号（`…`）的按省略号前的内容比对（作者是有意截断）。
    _xwl_src = re.sub(r"\s+", "", open(os.path.join(HERE, "xwl.py"), encoding="utf-8").read())
    for _i, _l in enumerate(_sk_txt.splitlines(), 1):
        for _m in re.finditer(r"`(\[(?:note|warn|FAIL|ok)\])((?:(?!`).)*)`", _l):
            _body = _m.group(2)
            _body = _body.split("…")[0] if "…" in _body else _body
            _n = re.sub(r"\s+", "", _body)
            if len(_n) < 8:
                continue
            # 比对前缀取 16 字（而不是 8）—— 8 字太短，「设计器/仓库」这类**词序对调**
            # 发生在第 9 字之后，8 字比不出来（负向测试实测漏过）。
            _probe = _n[:16]
            if _probe not in _xwl_src:
                doc_fail.append("SKILL.md:%d 承诺的输出文案 `%s…` 在 xwl.py 里找不到"
                                % (_i, (_m.group(1) + _body)[:34]))

    if doc_fail:
        failures.extend(doc_fail[:12])
    else:
        print("[ok]  文档守卫：emoji 未入标题 / 任意两文档间无重复表格 / 编号·章·步·节号引用可解析（含跨文件）/ "
              "链接存在 / 外移点两侧都在 / 格式五项（表格·跳级·代码块·行尾·末尾）/ 自称数字一致 / "
              "导航表与目录索引一致 / **「N 份参考材料」清单完整** / 无业务路径残留 / 反模式有入口")

    # ---- 18. SKILL.md 必须声明平台边界、调用入口与规模约束 ----
    # 起因：SkillHub TRACE 评测的 adaptability 维给了这两个子项低分 ——
    # 「未明确声明仅适用 WebBuilder 平台」「未说明输入文件大小等性能约束」「普通用户不知道从哪儿调」。
    # 这几行很容易在后续精简文档时被删掉，所以钉成断言。
    b_fail: list[str] = []
    if "SKILL.md" in docs:
        body = "\n".join(docs["SKILL.md"])
        if "WebBuilder" not in body or not re.search(r"不适用|仅适用|仅支持", body):
            b_fail.append("SKILL.md 未声明平台边界（需同时出现 WebBuilder 与「不适用/仅适用」）")
        if not re.search(r"^##\s*怎么用", body, re.M):
            b_fail.append("SKILL.md 缺少「怎么用」小节（调用入口）")
        if "scripts/xwl.py" not in body:
            b_fail.append("SKILL.md 的「怎么用」未给出命令行入口（scripts/xwl.py）")
        if not re.search(r"KB|MB", body):
            b_fail.append("SKILL.md 未声明输入规模约束（应给出实测文件大小量级）")
        # frontmatter 有长度上限（平台侧 1024）：description 是路由真正读的字段，
        # 每次往里补触发词都在吃这个额度 —— 1.3.0 加 diffguard 时曾把它撑到 **1029**，
        # 是靠人工量出来的。钉住：description 与整个 frontmatter 块都必须留余量。
        _fm = body.split("---")[1] if body.startswith("---") else ""
        _dm = re.search(r"description: >-\n(.*?)\n\w+:", _fm, re.S)
        _dlen = len(_dm.group(1)) if _dm else 0
        if _dlen > 1024:
            b_fail.append("SKILL.md 的 description %d 字符，超过 1024 上限" % _dlen)
        if len(_fm) > 1024:
            b_fail.append("SKILL.md 的 frontmatter 块 %d 字符，超过 1024 上限" % len(_fm))
        # 打包声明：SkillHub 的平台评测读这几样。缺了就会在"必需文件 / 能力声明"上扣分，
        # 而它们都是**内容侧**可控制的（`_meta.json` 不是 —— 那是平台在发布时生成的，
        # CLI 源码 `_is_junk_zip_path()` 明确把 `_meta.json` 排除在内容哈希之外）。
        if not os.path.isdir(os.path.join(root, "examples")):
            b_fail.append("缺少 examples/ 目录（平台评测的「示例充分性」会扣分）")
        _mjp = os.path.join(root, "metadata.json")
        if not os.path.exists(_mjp):
            b_fail.append("缺少 metadata.json（平台评测读它拿能力/边界声明）")
        else:
            try:
                _md = json.load(open(_mjp, encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                b_fail.append("metadata.json 不是合法 JSON：%s" % exc)
            else:
                _miss = sorted({"name", "version", "description", "input_schema",
                                "output_schema", "error_handling"} - set(_md))
                if _miss:
                    b_fail.append("metadata.json 缺字段：%s" % _miss)
        if "metadata:" not in body[:500]:
            b_fail.append("SKILL.md 的**前 500 字**内没有 `metadata:` 字段"
                          "（SkillHub 自检只看前 500 字，放 frontmatter 末尾不算）")
    if b_fail:
        failures.extend(b_fail)
    else:
        print("[ok]  SKILL.md 声明了平台边界、调用入口与规模约束")


def _check_platform(tmp, node, failures, write) -> None:
    """node_check_many 等价性 + folders 给目录须报错 + 非 UTF-8 控制台 + 跨盘符 relpath（第 19~22 组）"""

    # ---- 19. node_check_many 必须与逐段 node_check 等价（性能优化不许改变结论）----
    # 背景：把逐段 `node --check` 改成一次进程批量校验，486 KB 页面的 check 从 63 s 降到 1 s。
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
    else:
        print("[note] 未找到 node，跳过 node_check_many 等价性断言")

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
    xwl_py = os.path.join(HERE, "xwl.py")
    for args in (["--help"], ["check", "--help"], ["folders", "--help"]):
        try:
            pr = subprocess.run([sys.executable, xwl_py] + args, capture_output=True,
                                env=env_cp, timeout=90)
        except Exception as exc:  # noqa: BLE001
            e_fail.append("PYTHONIOENCODING=cp1252 下跑 `xwl.py %s` 抛异常：%s"
                          % (" ".join(args), exc))
            continue
        if pr.returncode != 0:
            tail = (pr.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            e_fail.append("PYTHONIOENCODING=cp1252 下 `xwl.py %s` 退出 %d：%s"
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



def _check_write_failures(tmp, node, failures, write) -> None:
    """写盘失败必须给可读 [FAIL] + 退出码 2，不得冒 Python traceback（第 23 组）。

    起因：`write_text()` 原先没兜 `OSError` —— 目标只读 / 父目录不存在 / 路径过长
    都会抛 traceback，而 SKILL.md 4.1 承诺的是「前置条件不满足 → rc=2 + 提示」。
    实测 5 个子命令 9 个场景中招，而当时的 64 项断言**一条都没覆盖写失败**。
    所以这里用子进程跑真实 CLI，逐一确认「不冒 traceback + rc=2 + 有 [FAIL]」。
    """
    print("[23] 写失败路径不得冒 traceback")
    xwl_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xwl.py")
    ro = write("wf_ro.xwl", VALID)
    ops_p = os.path.join(tmp, "wf_ops.json")
    with open(ops_p, "w", encoding="utf-8", newline="") as fh:
        fh.write('[{"op": "set", "path": ["title"], "value": "x"}]')
    fdir = os.path.join(tmp, "wf_fld")
    os.makedirs(fdir, exist_ok=True)
    fpage = os.path.join(fdir, "p.xwl")
    with open(fpage, "w", encoding="utf-8", newline="") as fh:
        fh.write(VALID)
    fj = os.path.join(fdir, "folder.json")
    with open(fj, "w", encoding="utf-8", newline="") as fh:
        fh.write('{"hidden":false,"index":[],"title":"t","iconCls":""}')
    nodir = os.path.join(tmp, "wf_nodir")

    def _cli(argv):
        pr = subprocess.run([sys.executable, xwl_py] + argv, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    wf: list[str] = []
    try:
        os.chmod(ro, 0o444)
        os.chmod(fj, 0o444)
        for label, argv in (
            ("patch → 目标只读", ["patch", ro, "--ops", ops_p]),
            ("expand --out → 目录不存在",
             ["expand", ro, "--out", os.path.join(nodir, "o.xwl")]),
            ("new → 父目录不存在", ["new", os.path.join(nodir, "a.xwl"), "--kind", "page"]),
            ("folders --register → folder.json 只读", ["folders", fpage, "--register"]),
        ):
            rc, out = _cli(argv)
            if "Traceback" in out:
                wf.append("%s：抛了 Python traceback（应给 [FAIL] + rc=2）" % label)
            elif rc != 2:
                wf.append("%s：退出码 %d（应为 2）" % (label, rc))
            elif "[FAIL]" not in out:
                wf.append("%s：没有 [FAIL] 提示" % label)
    finally:
        for f in (ro, fj):
            try:
                os.chmod(f, 0o666)
            except OSError:
                pass

    if wf:
        failures.extend(wf)
    else:
        print("[ok]  写失败给可读 [FAIL] + rc=2，不冒 traceback"
              "（patch / expand / new / folders 四类）")

def _check_edit_eol(tmp, node, failures, write) -> None:
    """`edit` 的锚点必须按**目标文件的实际换行**归一，且拍平多行要警示（第 24 组）。

    起因：`normalize_eol()` 早先硬编码 CRLF —— ① LF 文件上**跨行锚点永远匹配不到**
    （报「锚点出现次数: 0」，看着像用户写错了锚点）；② 单行锚点 + 多行 new 会把
    LF 文件写成 CRLF/LF **混用**（文件已落盘、格式已坏）。③ 另外「把多行拍平」
    属于**静默**语义损坏，原先毫无提示，而 `check` 查不出（压平后仍是合法 JSON）。
    三条都在这里钉住（实测样本工程：1878 全 CRLF / 902「单行无换行符」/ **0 个 LF** ——
    两条路径都要覆盖，因为 `expand` 会把无换行的单行源产出成 LF）。
    """
    print("[24] edit 的换行归一与拍平警示")
    xwl_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xwl.py")

    def _cli(argv):
        pr = subprocess.run([sys.executable, xwl_py] + argv, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    def _mk(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    def _eol_of(p):
        b = open(p, "rb").read()
        crlf = b.count(b"\r\n")
        return crlf, b.count(b"\n") - crlf

    BASE = ('{\n "hidden": false,\n "children": [],\n "roles": {},\n "title": "SELFTEST_T",\n'
            ' "iconCls": "",\n "inframe": false,\n "pageLink": ""\n}')

    ee: list[str] = []

    # ① LF 文件 + 跨行锚点 —— 改前必然报「锚点出现次数: 0」（误导成"锚点写错了"）
    t = _mk("ee_lf.xwl", BASE)
    o = _mk("ee_o1.txt", '"roles": {},\n "title": "SELFTEST_T"')
    n = _mk("ee_n1.txt", '"roles": {},\n "title": "ZZZ"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0 or "锚点出现次数: 0" in out:
        ee.append("LF 文件上跨行锚点应能匹配（旧实现会报「锚点出现次数: 0」）：rc=%d" % rc)
    elif _eol_of(t)[0]:
        ee.append("LF 文件写入后被混入 CRLF：CRLF=%d LF=%d" % _eol_of(t))

    # ② LF 文件 + 单行锚点 + 多行 new —— 改前会把 LF 写成 CRLF/LF 混用
    t = _mk("ee_lf2.xwl", BASE)
    o = _mk("ee_o2.txt", '"roles": {}')
    n = _mk("ee_n2.txt", '"roles": {\n  "default": 1\n}')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0:
        ee.append("LF 文件 + 多行 new 应成功：rc=%d" % rc)
    elif _eol_of(t)[0]:
        ee.append("LF 文件 + 多行 new 后混入 CRLF（CRLF=%d LF=%d），应保持全 LF" % _eol_of(t))

    # ③ CRLF 文件 + 跨行锚点 —— 回归：这条旧实现本来是通的，不能被改坏
    t = _mk("ee_crlf.xwl", BASE.replace("\n", "\r\n"))
    o = _mk("ee_o3.txt", '"roles": {},\n "title": "SELFTEST_T"')
    n = _mk("ee_n3.txt", '"roles": {},\n "title": "ZZZ"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if rc != 0:
        ee.append("CRLF 文件 + 跨行锚点应成功：rc=%d" % rc)
    elif _eol_of(t)[1]:
        ee.append("CRLF 文件写入后被混入 LF：CRLF=%d LF=%d" % _eol_of(t))

    # ④ 拍平多行必须警示（工具是唯一能提示的地方：check 查不出）
    t = _mk("ee_flat.xwl",
            '{\n "hidden": false,\n "children": [],\n "roles": {},\n'
            ' "title": "a\\\nb\\\nc",\n "iconCls": "",\n "inframe": false,\n "pageLink": ""\n}')
    o = _mk("ee_o4.txt", '"title": "a\\\nb\\\nc"')
    n = _mk("ee_n4.txt", '"title": "abc"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if "[warn]" not in out or "续行符" not in out:
        ee.append("拍平多行时必须警示（[warn] 且提到「续行符」），否则是静默语义损坏")

    # ⑤ 普通单行替换不得误报
    t = _mk("ee_ok.xwl", BASE)
    o = _mk("ee_o5.txt", '"title": "SELFTEST_T"')
    n = _mk("ee_n5.txt", '"title": "BBB"')
    rc, out = _cli(["edit", t, "--old-file", o, "--new-file", n])
    if "[warn]" in out:
        ee.append("普通单行替换不该出现 [warn]（误报）")

    if ee:
        failures.extend(ee)
    else:
        print("[ok]  edit 锚点按目标换行归一（LF/CRLF 均可）、拍平多行有 [warn]、普通替换不误报")


def _check_eol_and_guards(tmp, node, failures, write) -> None:
    """换行形态 × 校验收尾 × 静默回退（第 25 组）。

    四条都是"实现了但没测到"的类型，成因一致：**样本工程 2780 个 xwl 里 LF 恰好 0 个**，
    而 LF 是设计器原样、仓库存的格式、`new` 的默认产出 —— 于是以 CRLF 为准写死的代码
    在这份样本上永远看不出问题。

    ① `check` 的 ③「续行空白」用 `text.split(CRLF)` 切行 ⇒ **纯 LF 文件切不出行**
       （整份成一个元素），③ 静默退化成"只看最后一行"。实测：同一处「反斜杠+空白」
       在 CRLF 上被 ③ 精准报到行号，在 LF 上 ③ 报 `[ok]`。
    ② 同一处切行还让纯 CR 文件同时得到「存在 N 处裸 CR」的 FAIL 与
       「该文件是单行形态（无任何换行）」的 note —— 自相矛盾。
    ③ `patch` 对**换行混用**的源会静默统一（`edit` 早有 `[warn]`，`patch` 没有）。
    ④ `patch --indent≠1` 会产出与设计器不一致的文件、却零提示 ——
       等于给了用户一把击穿「与设计器逐字节一致」的钥匙。
    ⑤ `patch` 在**无换行的单行源**上 `--eol auto` 回退 LF，且必然把整份展开成多行
       （diff = 整个文件），两条都要说清。
    ⑥ 值里的**孤立代理项**会让 `.encode("utf-8")` 崩 —— 实测 `patch` 在打印字节数时
       就冒 traceback（rc=1）。`_quote` 按 org.json 的 `\\uXXXX` 转义后语义仍等价。
    """
    print("[25] 换行形态 × 校验收尾 × 静默回退")
    xwl_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xwl.py")

    def _cli(argv):
        pr = subprocess.run([sys.executable, xwl_py] + argv, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180)
        return pr.returncode, (pr.stdout or "") + (pr.stderr or "")

    def _mk(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    BS = chr(92)
    # 一份合法骨架，中间那行的续行符后挂一个空白 —— ③ 应当抓到它
    def _body(mid, eol):
        return eol.join([
            "{", ' "hidden": false,', ' "children": [{',
            '  "configs": {"itemId": "SELFTEST_BTN", "text": "SELFTEST_T"},',
            '  "expanded": false,', '  "children": [],', '  "type": "button",',
            '  "events": {', '   "click": "var a = 1;' + mid,
            'Wb.info(String(a));"', '  }', ' }],',
            ' "roles": {"default": 1},',
            ' "title": "SELFTEST_T", "iconCls": "", "inframe": false, "pageLink": ""', '}'])

    ge: list[str] = []

    # ① ③ 必须在三种换行下都生效（同一处破坏，三种文件都要报出行号）
    for eol, tag in (("\r\n", "CRLF"), ("\n", "LF"), ("\r", "CR")):
        f = _mk("ge_a_%s.xwl" % tag, _body(BS + BS + " ", eol))
        _rc, out = _cli(["check", f])
        if "③ 第" not in out:
            ge.append("③ 在 %s 文件上没报出「反斜杠+空白」所在行（切行写死 CRLF ⇒ 静默失效）" % tag)

    # ①b 干净文件不得因切行变更而误报 ③（注意：`[ok]` 行里本来就含「③ 续行空白」，
    #     所以只能匹配 FAIL 形态的「③ 第…行」，不能只找「③」）
    f = _mk("ge_ok_crlf.xwl", _body(BS, "\r\n"))
    _rc, out = _cli(["check", f])
    if "③ 第" in out:
        ge.append("干净的 CRLF 文件被 ③ 误报")

    # ①c 换行统计必须与 `check` 的 ② 同口径：`expand` 也要报"裸 LF"，不能把 CRLF 里的
    #     `\n` 算进"LF" —— 否则纯 CRLF 文件会显示成「CRLF=N, LF=N」，读者误读成混用。
    _rc, out = _cli(["expand", f, "--dry-run"])
    if "裸LF=0" not in out:
        ge.append("expand 的换行统计没按「裸 LF」口径报（纯 CRLF 文件应显示 裸LF=0）")

    # ② 纯 CR 文件：② 的 FAIL 与「无任何换行」的 note 不得同时出现（自相矛盾）
    f = _mk("ge_cr_note.xwl", _body(BS, "\r"))
    _rc, out = _cli(["check", f])
    if "裸 CR" in out and "无任何换行" in out:
        ge.append("纯 CR 文件同时报「存在 N 处裸 CR」与「该文件是单行形态（无任何换行）」")

    # ③ patch 对换行混用的源必须给 [warn]（对齐 edit）
    f = _mk("ge_mixed.xwl", _body(BS, "\r\n").replace("\r\n", "\n", 3))
    ops = _mk("ge_ops.json",
              '[{"op":"set","path":["title"],"value":"SELELTEST_NEW"}]')
    _rc, out = _cli(["patch", f, "--ops", ops, "--dry-run"])
    # 判据要连 `[warn]` 标记一起查：只查文本的话，把标记换成 `[xx]`（等于不再是警告）也照样过
    if "[warn]" not in out or "换行混用" not in out:
        ge.append("patch 在换行混用的源上没有 [warn]（会静默统一换行）")

    # ④ --indent ≠ 1 必须警示（patch 与 expand 都要）
    f = _mk("ge_ind.xwl", _body(BS, "\r\n"))
    for cmd in (["patch", f, "--ops", ops, "--indent", "4", "--dry-run"],
                ["expand", f, "--indent", "4", "--dry-run"]):
        _rc, out = _cli(cmd)
        if "[warn]" not in out:
            ge.append("%s 用 --indent 4 时没有 [warn]（会静默产出与设计器不一致的排版）" % cmd[0])

    # ⑤ 无换行的单行源：要说明「auto 回退 LF」与「整份展开」
    obj = xwl.parse_xwl(_body(BS, "\r\n"))
    compact = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if "\n" in compact:
        raise AssertionError("样本不是单行")
    f = _mk("ge_one.xwl", compact)
    _rc, out = _cli(["patch", f, "--ops", ops, "--dry-run"])
    if "回退 LF" not in out:
        ge.append("单行源上 patch 没有说明 `--eol auto` 回退 LF")
    if "[warn]" not in out or "整份展开" not in out:
        ge.append("单行源上 patch 没有以 [warn] 说明会把整份展开成多行")

    # ⑥ 孤立代理项：不得冒 traceback、必须转义落盘、且语义仍等价
    f = _mk("ge_sur.xwl", _body(BS, "\r\n"))
    ops_s = os.path.join(tmp, "ge_sur_ops.json")
    with open(ops_s, "w", encoding="utf-8") as fh:
        fh.write('[{"op":"set","path":["title"],"value":"\\ud800SELELTEST"}]')
    rc, out = _cli(["patch", f, "--ops", ops_s, "--backup"])
    if "Traceback" in out:
        ge.append("值含孤立代理项时抛了 Python traceback（应给可读结果）")
    elif rc != 0:
        ge.append("值含孤立代理项时应能写完（rc=0），实得 rc=%d" % rc)
    else:
        raw = open(f, "rb").read()
        if b"\\ud800" not in raw:
            ge.append("孤立代理项没有按 \\uXXXX 转义落盘")
        try:
            got = xwl.parse_xwl(raw.decode("utf-8"))["title"]
        except Exception as exc:  # noqa: BLE001
            ge.append("转义后的文件读不回原对象：%s" % exc)
        else:
            if got != "\ud800SELELTEST":
                ge.append("转义后语义不等价：%r" % got)
    # `_byte_len` 本身也不该抛
    try:
        if xwl._byte_len("\ud800") <= 0:      # noqa: SLF001
            ge.append("_byte_len 对孤立代理项返回了非正数")
    except Exception as exc:  # noqa: BLE001
        ge.append("_byte_len 对孤立代理项抛了 %s" % type(exc).__name__)

    if ge:
        failures.extend(ge)
    else:
        print("[ok]  ③ 在 CRLF/LF/CR 三种换行下都生效 + 纯 CR 的 note 不再自相矛盾 + "
              "patch 的换行混用/--indent/单行源回退都有 [warn] + 孤立代理项不冒 traceback")


def _check_diffguard(tmp, node, failures, write) -> None:
    """`diffguard` 相对 git 基线检测「多行被压平」（第 26 组）。

    这是 1.3.0 新增的能力，补的是 §2.3 承认的那个洞：把「反斜杠 + 换行」直接删掉之后
    文件**依然是合法 JSON**，`check` 七项全绿、`node --check` 还可能返回 0 ——
    原先唯一的发现手段是人工 `git diff`。

    判据为什么必须是**两条**（这里正反两侧都钉住）：
      · 只看"续行符变少" ⇒ 合法地删掉一段多行 JS / 删一个控件也会净减少 ⇒ **必然误报**；
      · 压平的真正指纹是「原来好几行的内容挤进同一行」⇒ **最长行暴增**。
    所以「压平必须报」与「合法删减必须不报」两条同等重要，缺一条这个能力就没法用。
    """
    print("[26] diffguard（相对 git 基线的压平检测）")
    xwl_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xwl.py")
    repo = os.path.join(tmp, "dg_repo")
    os.makedirs(repo, exist_ok=True)
    BS = chr(92)

    def _git(*a):
        return subprocess.run(["git", *a], cwd=repo, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")

    def _cli(*a, cwd=None):
        pr = subprocess.run([sys.executable, xwl_py, *a], cwd=cwd or repo,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=180)
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

    _git("init", "-q")
    _git("config", "user.email", "selftest@local")
    _git("config", "user.name", "selftest")
    page = _mk("dg.xwl", SRC)
    _git("add", "-A")
    _git("commit", "-q", "-m", "base")
    if _git("rev-parse", "--verify", "HEAD").returncode != 0:
        print("[note] 无法建立临时 git 仓库，跳过 diffguard 断言")
        return

    dg: list[str] = []

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
        dg.append("diffguard 对未改动文件应 rc=0 且无告警（rc=%d）" % rc)

    # ② 压平（删掉续行符把 4 行挤成 1 行）→ 必须报；默认 rc=0，--strict 下 rc=1
    _mk("dg.xwl", _flat(SRC))
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" not in out or "压平" not in out:
        dg.append("diffguard 没报出被压平的文件（反向退化 ⇒ 这个能力等于没有）")
    if rc != 0:
        dg.append("diffguard 默认应只告警（rc=0），实得 rc=%d" % rc)
    rc, out = _cli("diffguard", "dg.xwl", "--strict")
    if rc != 1:
        dg.append("diffguard --strict 下疑似压平应 rc=1，实得 rc=%d" % rc)

    # ③ 反面对照：合法删掉两行多行 JS → 续行符也净减少，但**不得**报（否则天天误报）
    _git("checkout", "-q", "--", "dg.xwl")
    lines = SRC.split("\r\n")
    del lines[9]
    del lines[9]
    _mk("dg.xwl", "\r\n".join(lines))
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" in out:
        dg.append("diffguard 把「合法删除一段多行 JS」误报成压平（续行符净减少≠压平）")
    if rc != 0:
        dg.append("diffguard 对合法删减应 rc=0，实得 rc=%d" % rc)

    # ④ 反面对照：只在同一行里加长内容（续行符不变）→ 不得报
    _git("checkout", "-q", "--", "dg.xwl")
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
        _git("add", "-A")
        _git("commit", "-q", "-m", "short")
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
            dg.append("「%s」--strict 下应 rc=1，实得 %d" % (label, rc))
        _git("checkout", "-q", "--", "dg.xwl")

    # ⑤ 正常走一遍 patch 之后不得报（否则这个守卫会被日常改动淹没）
    _git("checkout", "-q", "--", "dg.xwl")
    ops = os.path.join(repo, "dg_ops.json")
    with open(ops, "w", encoding="utf-8") as fh:
        fh.write('[{"op":"append","path":["children",0,"children"],"value":'
                 '{"configs":{"itemId":"dgNew","text":"新"},"expanded":false,'
                 '"children":[],"type":"button","events":{"click":"Wb.info(1);"}}}]')
    _cli("patch", "dg.xwl", "--ops", "dg_ops.json", "--backup")
    rc, out = _cli("diffguard", "dg.xwl")
    if "[warn]" in out:
        dg.append("diffguard 把正常的 patch 改动误报成压平")

    # ⑥ 降级：新文件（不在基线里）→ note 跳过、rc=0；**全部跳过**时 --strict 必须 rc=2
    _mk("dg_fresh.xwl", SRC)
    rc, out = _cli("diffguard", "dg_fresh.xwl")
    if rc != 0 or "跳过" not in out:
        dg.append("diffguard 对新文件应提示跳过且 rc=0（rc=%d）" % rc)
    rc, out = _cli("diffguard", "dg_fresh.xwl", "--strict")
    if rc != 2:
        dg.append("diffguard --strict 下一个文件都没比成时应 rc=2（实得 %d）" % rc)

    # ⑥b 退出码优先级：**可疑压平 > 跳过**（否则带新增文件的 CI 会永远红）
    big = _build("var rec = app.g.getSelection()[0];",
                 ["if (!rec) { Wb.info('pick'); return; }",
                  "Wb.requestAg({ params: { bean: 'b', method: 'm', id: rec.data.ID } });"])
    _mk("dg.xwl", big)
    _git("add", "-A")
    _git("commit", "-q", "-m", "prio")
    _mk("dg.xwl", _flat(big))
    _mk("dg_fresh2.xwl", SRC)
    rc, out = _cli("diffguard", "dg.xwl", "dg_fresh2.xwl", "--strict")
    if rc != 1:
        dg.append("同时有可疑压平与跳过项时 --strict 应 rc=1（可疑优先），实得 %d" % rc)

    # ⑦ --rev 写错是用法错 → rc=2（且不得被说成"新增文件"）
    rc, out = _cli("diffguard", "dg.xwl", "--rev", "no-such-ref")
    if rc != 2 or "不存在" not in out:
        dg.append("diffguard 对不存在的 --rev 应 rc=2 并明说基线不存在（rc=%d）" % rc)

    # ⑧ 不在 git 仓库里 → 跳过而不是崩
    nogit = os.path.join(tmp, "dg_nogit")
    os.makedirs(nogit, exist_ok=True)
    with open(os.path.join(nogit, "n.xwl"), "w", encoding="utf-8", newline="") as fh:
        fh.write(SRC)
    rc, out = _cli("diffguard", "n.xwl", cwd=nogit)
    if rc != 0 or "跳过" not in out or "Traceback" in out:
        dg.append("diffguard 在非 git 目录应提示跳过、rc=0、不冒 traceback（rc=%d）" % rc)

    if dg:
        failures.extend(dg)
    else:
        print("[ok]  压平必报 / 合法删减与单行变长不误报 / patch 改动不误报 / "
              "新文件与非仓库干净跳过 / --strict 与 --rev 的退出码正确")


def main() -> int:
    xwl.ensure_utf8_stdio()     # 输出全是中文；Windows 控制台默认非 UTF-8 会直接 UnicodeEncodeError
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

    _check_basics(tmp, node, failures, write)
    _check_params_paths(tmp, node, failures, write)
    _check_itemids(tmp, node, failures, write)
    _check_subcommands(tmp, node, failures, write)
    _check_docs(tmp, node, failures, write)
    _check_platform(tmp, node, failures, write)
    _check_write_failures(tmp, node, failures, write)
    _check_edit_eol(tmp, node, failures, write)
    _check_eol_and_guards(tmp, node, failures, write)
    _check_diffguard(tmp, node, failures, write)


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
