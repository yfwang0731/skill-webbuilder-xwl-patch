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

@_cap
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
    # 起因：只留“破坏用例必须红”，会漏掉“check 对**任何**输入都判红”这种误报 —— 需要一条必绿的正例做对照，否则误报与真检出不辨。
    good = write("valid.xwl", VALID)
    code, out = _run_check([good], node)
    if code != 0:
        failures.append(f"合法样本被判 FAIL:\n{out}")
    else:
        print("[ok]  check 对合法样本判 OK")

    # ---- 2. 五种破坏必须被检出 ----
    # 起因：check 的价值全在“能检出破坏”；不逐类钉住就可能退化成永远判绿，缺陷漏到用户手里才发现。
    cases: list[tuple[str, str, str, bool]] = [
        # (用例名, 文件内容, 期望出现在输出里的关键词, 是否 BOM)
        ("裸LF", VALID.replace(CRLF, "\n", 1), "裸 LF", False),
        ("反斜杠+空格", VALID.replace(";\\" + CRLF, ";\\  " + CRLF, 1), "反斜杠+空白", False),
        ("JSON破坏", VALID.replace("]", "", 1), "加载器等价解析失败", False),
        ("带BOM", VALID, "BOM", True),
        # ⚠️ 关键词**不能用 `末行`** —— `check` 输出首行含**文件名** `bad_末行带续行符….xwl`，
        #   用它当关键词会恒真（旧用例即此弊、形同虚设）⇒ 改钉 ⑤ 自己的句子。
        ("末行带续行符", VALID[:-2] + "\\", "末行以反斜杠结尾", False),
        # `#79`：**同内容、末尾带换行** ⇒ ⑤ 也必须判到（原来 `lines[-1] == ""` 把真末行遮掉 ⇒ 漏判）。
        ("末行带续行符+换行", VALID[:-2] + "\\" + CRLF, "末行以反斜杠结尾", False),
        # `#79`：**末尾还有空行**（≥1 层）也必须判到 —— 「只剥一层」的旧修法对 +1/+2 尾空行漏判。
        ("末行带续行符+尾空行", VALID[:-2] + "\\" + CRLF + CRLF, "末行以反斜杠结尾", False),
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

    # ---- 2b. ④ 的宽容面：接受尾随逗号、放行前导内容、字符串内逗号不动 ----
    # 起因：加载器 org.json 接受「尾随逗号」（`{"a":1,}`），而工具按 `json.loads` 判会把**框架明明
    #       能加载**的文件报 ④ FAIL ——「工具比框架还严」会破坏 ④ 的保真承诺，故逐面钉住宽容。
    # 起因（反向）：框架解析前 `substring(indexOf('{'))` 丢掉 `{` 之前的内容 ⇒ 前导注释本就被
    #       接受、**不得**判 FAIL；这条防的是「将来有人顺手把 ④ 加严」。
    tc = write("tc.xwl", '{"a":1,}')
    code, out = _run_check([tc], node)
    if code != 0:
        failures.append("④ 宽容面：对象尾随逗号 `{\"a\":1,}` 被判 FAIL（框架能加载）:\n%s" % out)
    else:
        print("[ok]  ④ 宽容面：尾随逗号（对象）放行")

    if xwl._strip_trailing_commas("[1,2,]") != "[1,2]":
        failures.append("④ 宽容面：数组尾随逗号 `[1,2,]` 未被归一")
    else:
        print("[ok]  ④ 宽容面：尾随逗号（数组）归一")

    lead = write("lead.xwl", '// c\n{"a":1}')
    code, out = _run_check([lead], node)
    if code != 0:
        failures.append(
            "④ 宽容面：`{` 之前的前导内容被判 FAIL（框架 substring 会丢弃它）:\n%s" % out)
    else:
        print("[ok]  ④ 宽容面：`{` 之前的前导内容不判 FAIL（框架接受）")

    # 字符串感知（安全边界）：字符串内的 `,}` 不得被删、外层尾随逗号要删、其值不变。
    _src = '{"s":"a,}","b":2,}'
    _strip = xwl._strip_trailing_commas(_src)
    try:
        _parsed = xwl.parse_xwl(_src)
    except Exception as exc:  # noqa: BLE001
        _parsed = "ERR:%s" % exc
    if _strip != '{"s":"a,}","b":2}' or _parsed != {"s": "a,}", "b": 2}:
        failures.append("④ 宽容面：字符串内的逗号被误删或外层尾随逗号未删（预处理器非字符串感知）: "
                        "strip=%r parsed=%r" % (_strip, _parsed))
    else:
        print("[ok]  ④ 宽容面：字符串内的逗号不被误删（值不变）")

    # 反面钉住：④ 放宽了「尾随逗号」，但 equivalent 仍须严（两者取向不许统一）。
    if (xwl.equivalent({"a": 1}, {"a": 1.0}) or xwl.equivalent({"a": True}, {"a": 1})
            or xwl.equivalent({"a": 1, "b": 2}, {"b": 2, "a": 1})):
        failures.append("④ 放宽尾随逗号后 equivalent 被连带放宽（1≠1.0 / true≠1 / 键序不同仍须不等）")
    else:
        print("[ok]  反面：equivalent 仍严（1≠1.0 / true≠1 / 键序不同）")

    # ---- 2b-2. ④ 的**能力边界**：键位 token 面**不含 `-`**（`references/faq.md` ④）----
    # 起因：`xwl.loader_normalize` 的**键位**与**值位** token 面**有意不对称** —— 值位含 `-`、
    #   键位不含（见该函数 docstring「token 面在两处有意不对称」）。故 `{ label-width: "85" }`
    #   这类**键未加引号且键含 `-`** 的形态：加载器接受、工具不认 ⇒ ④ FAIL，属**已知能力边界**。
    #   `faq.md` ④ 明写了这半句（已复核确认它**可复现**，不是过时断言）⇒ 必须钉住。
    # 反例（注入即红）：把 `loader_normalize` 键位那两处 `"_$."` 改成 `"_$.-"` ⇒ 下面两条**同时**红
    #   （键被补上引号、解析由失败变为成功）。那正是 docstring 禁止的改法：会把
    #   「键名拼错」变成「静默补引号」。⚠️ 两条都只调**纯函数**，不起子进程。
    _dash_key = '{"configs":{"itemId":"v",label-width:"85"}}'
    _dash_norm = xwl.loader_normalize(_dash_key)
    if '"label-width"' in _dash_norm:
        failures.append(
            "④ 能力边界：键位 token 面被放宽了？键含 `-` 的**未加引号**键**不应**被补引号"
            "（`references/faq.md` ④ 的能力边界）: normalize=%r" % _dash_norm)
    else:
        print("[ok]  ④ 能力边界：键含 `-` 的未引号键不被补引号（归一化层）")
    if xwl.loader_parse_or_none(_dash_key) is not None:
        failures.append(
            "④ 能力边界：键含 `-` 的未引号键不应解析成功 —— 该形态应判 ④ FAIL"
            "（`check` rc=1；`params`／`dump` rc=2）")
    else:
        print("[ok]  ④ 能力边界：键含 `-` 的未引号键判解析失败（入口层，check ④ FAIL）")

    # ---- 2c. 第 ⑧ 维「加载链完整性」：**只提示、不进 rc**（五条 fixture） ----
    # 起因：⑧ 判据来自框架 `XwlBuffer` 的取键方式（`children` 取 getJSONArray、
    #   `children[0].configs` 与 `roles` 取 getJSONObject —— 缺失/类型不符即抛）⇒ 文件能被 ④ 解析、
    #   页面却在加载期打不开。官方定位「防手写 / 半成品」、实测数万样本 0 违规 ⇒ 必须**只 warn、不改 rc**。
    #   不钉住就会被后来的改动"接进 rc"（工具比框架严、CI 恒红）或被整段删掉。
    # 反例（注入即红）：把 ⑧ 的结果并进 `failed` ⇒ check 对下面样本 rc≠0 ⇒ 本条红。
    chain_cases = [
        ("children 非数组", '{"children":"x","roles":{}}', "children 不是数组"),
        ("children 缺失", '{"roles":{}}', "children 缺失"),
        ("children 空", '{"children":[],"roles":{}}', "children 为空数组"),
        ("roles 缺失", '{"children":[{"configs":{}}]}', "roles 缺失"),
        ("children[0].configs 缺失", '{"children":[{"type":"panel"}],"roles":{}}',
         "children[0].configs 缺失"),
    ]
    for _ci, (_cname, _csrc, _ckw) in enumerate(chain_cases):
        _cp = write("chain_%d.xwl" % _ci, _csrc)
        _crc, _cout = _run_check([_cp], node)
        _cwarn = [ln for ln in _cout.splitlines() if ln.strip().startswith("[warn] ⑧")]
        if _crc != 0:
            failures.append("⑧ 违规样本「%s」把 check 判成 rc=%d —— ⑧ 只该 warn、不进 rc:\n%s"
                            % (_cname, _crc, _cout))
        elif not any(_ckw in ln for ln in _cwarn):
            failures.append("⑧ 违规样本「%s」未打 `[warn] ⑧ …%s…`:\n%s" % (_cname, _ckw, _cout))
        else:
            print("[ok]  ⑧ 违规样本「%s」：只 warn、rc=0" % _cname)

    # ---- 2d. ⑧ 的三形态：无异常 / 有违规 / 因解析失败跳过（各出现一次） ----
    # 起因：⑧ 是"恒留一行"，用户与文档都靠这三行确认它跑没跑；删掉任一形态的打印行，本条必须红。
    _f_ok = write("chain_ok.xwl", '{"children":[{"configs":{}}],"roles":{}}')
    _f_bad = write("chain_bad.xwl", '{"children":"x","roles":{}}')
    _f_skip = write("chain_skip.xwl", '{"children": [')
    _ro, _oo = _run_check([_f_ok], node)
    _rb, _ob = _run_check([_f_bad], node)
    _rs, _os2 = _run_check([_f_skip], node)
    _want = {
        "[note] ⑧ 加载链完整性：无异常": _oo,
        "[warn] ⑧ 加载链完整性：": _ob,
        "[note] ⑧ 加载链完整性：因解析失败跳过": _os2,
    }
    _missing = [k for k, v in _want.items() if k not in v]
    if _missing or (_ro, _rb, _rs) != (0, 0, 1):
        failures.append("⑧ 三形态不齐（缺 %s）或 rc 不对（%s/%s/%s）"
                        % (_missing, _ro, _rb, _rs))
    else:
        print("[ok]  ⑧ 三形态各一：无异常 / 有违规 / 因解析失败跳过")

    # ---- 2e. 「写盘后自检不纳入 ⑧」：patch 对 ⑧-违规样本仍 rc=0 且输出无 ⑧ ----
    # 起因：⑧ 只该在 `check` 出现；若漏进 `_post_check`（`checks` 未去 8），写盘会多打一行 ⑧、
    #   甚至被误接进 rc。注入面 = `_post_check` 的 `checks` 里带上 8 ⇒ 本条**期望红**。
    _pc = write("chain_patch.xwl", '{"hidden":false,"children":"x","roles":{},"title":"t"}')
    _pc_ops = os.path.join(tmp, "chain_ops.json")
    with open(_pc_ops, "w", encoding="utf-8") as _fh:
        json.dump([{"op": "set", "path": ["title"], "value": "t2"}], _fh)
    _prc, _pout = _run(xwl.cmd_patch, file=_pc, ops=_pc_ops, indent=1, eol="auto",
                       dry_run=False, backup=False, node=None, no_js=True)
    if _prc != 0:
        failures.append("patch 对 ⑧-违规样本 rc=%d（应 0：⑧ 不进写盘后自检）:\n%s" % (_prc, _pout))
    elif "⑧" in _pout:
        failures.append("patch 的写盘后自检里出现了 ⑧ 行（⑧ 应只在 check 出现）:\n%s" % _pout)
    else:
        print("[ok]  写盘后自检不纳入 ⑧：patch 对 ⑧-违规样本 rc=0 且无 ⑧ 行")

    # ---- 3. edit：锚点不唯一必须拒绝且不落盘 ----
    # 起因：锚点不唯一时若照改或静默跳过，都会改错对象却不报错 —— 文件已被写坏，用户却以为成功。
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
    # 起因：上面的 §3 只证“该拒的拒了”；若 edit 对**合法**锚点也拒绝，就退化成没法用 —— 故配一条必成功的正例。
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
    # 起因：expand 的用途是把压平的单行还原成设计器保存的同款多行；产出形态若与设计器不一致，后续 diff／人工比对都会误判。
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
    # 起因：patch 的契约是“结构级编辑”（只改值、格式由序列化器统一产出）；哪条路径若退化成字符串拼接，会产出与序列化器不一致的键序／缩进／转义却看不出。
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

    # 尾部（非 UTF-8 文案 / 调用点探针 / 裸 NUL / ops 草稿 / NaN / 负零金标 / 写盘原子性）
    #   已下沉为模块级 `_check_basics_tail`（本函数 482 行，要进 400 的上限）。
    #   判据文本逐字未改，只换了宿主。
    _check_basics_tail(tmp, failures)

@_cap
def _check_basics_tail(tmp, failures) -> None:
    """`_check_basics` 的尾部（有界下沉，判据文本逐字未改）。

    只依赖 `tmp` 与 `failures` 两个入参，其余都是模块级名字。
    """
    # ---- 判据依据：`check` 与 `dump` 对非 UTF-8 必须报**同一段**可读文案 ----
    # 起因：`check` 曾直接甩 Python 的 codec 原文（既不说是编码问题、也不给修法），
    #   而 FAQ 与 `test-prompts.json` 引的正是"工具报「不是 UTF-8 文本」"这个问法 ⇒ 文档与实现对不上。
    _gbk = os.path.join(tmp, "k21-gbk.xwl")
    with open(_gbk, "wb") as _f:
        _f.write('{"title":"测试"}'.encode("gbk"))
    # ⚠️ 断言要覆盖**全部四个入口**：只查 check/dump、且只查"都含『不是 UTF-8 文本』"是不够的 ——
    #    那样"另外两个入口仍在甩 Python codec 原文"会被放过（实测过）。
    _k14: dict = {}
    for _sub in ("check", "dump", "params", "itemids"):
        _r = _cap_run([sys.executable, os.path.join(SKILL_ROOT, "scripts", "xwl.py"), _sub, _gbk], timeout=120)
        _k14[_sub] = (_r.stdout or "") + (_r.stderr or "")
    _k14_bad = [k for k, v in _k14.items()
                if "不是 UTF-8 文本" not in v or "工具不猜编码" not in v]
    if not _k14_bad:
        print("[ok]  四个入口（check/dump/params/itemids）对非 UTF-8 报同一段可读文案（含「工具不猜编码」）")
    else:
        failures.append("这些入口的非 UTF-8 文案不可读或不同源：%s（check=%r）"
                        % (_k14_bad, _k14["check"][:140]))

    # ---- 命令级等价比对（**调用点**守卫 · **改为行为级**）----
    # 为什么必须命令级：`equivalent` 的 helper 断言只证明函数本身对，证不了
    # expand/patch/new **真的调用它** —— 把三处调用点换成 `==` 时只有命令级断言能抓到。
    # ⚠️ 旧做法用「含浮点 `1.0` 的样本 ⇒ rc=2」间接证明：保真写出整数值浮点后往返等价（rc=0），
    #    该 round-trip 的判别力已归零（全样本 `equivalent` 与 `==` 同值）⇒ 改为**行为级**：
    #    进程内 monkeypatch `xwl.equivalent` 成探针，调三命令各一次，断言探针各被调用 ≥1 次。
    #    注入 = 把任一处 `equivalent(parse_xwl(out), obj)` 换成 `==` ⇒ 该命令探针 0 次 ⇒ 红。
    #    比源码文本断言更稳（调用被抽成 helper 时不假红）。
    _probe = {"n": 0}
    _real_equiv = xwl.equivalent

    def _counting_equiv(a, b):
        _probe["n"] += 1
        return _real_equiv(a, b)

    _k8 = os.path.join(tmp, "k8callsite.xwl")
    with open(_k8, "w", encoding="utf-8", newline="") as _f:
        _f.write('{\n "hidden": false,\n "children": [],\n "roles": {},\n'
                 ' "title": "K8",\n "iconCls": "",\n "inframe": "",\n "pageLink": ""\n}')
    _k8ops = os.path.join(tmp, "k8callsite_ops.json")
    with open(_k8ops, "w", encoding="utf-8") as _f:
        _f.write('[{"op": "set", "path": ["title"], "value": "K8b"}]')
    _k8_new = os.path.join(tmp, "k8callsite_new.xwl")
    _k8_fail = []
    try:
        xwl.equivalent = _counting_equiv      # type: ignore[assignment]
        for _lbl, _fn, _kw in (
                ("expand", xwl.cmd_expand,
                 {"file": _k8, "out": None, "indent": 1, "eol": "auto", "safe": False,
                  "dry_run": True, "backup": False, "node": None, "no_js": True}),
                ("patch", xwl.cmd_patch,
                 {"file": _k8, "ops": _k8ops, "indent": 1, "eol": "auto",
                  "dry_run": True, "backup": False, "node": None, "no_js": True}),
                ("new", xwl.cmd_new,
                 {"out": _k8_new, "kind": "page", "from_json": None, "title": "K8",
                  "roles": None, "eol": "lf", "indent": 1, "force": False,
                  "dry_run": True, "node": None, "no_js": True})):
            _before = _probe["n"]
            _buf = io.StringIO()
            with contextlib.redirect_stdout(_buf):
                _fn(type("NS", (), _kw)())
            if _probe["n"] <= _before:
                _k8_fail.append("%s 未调用模块级 equivalent（探针 0 次）" % _lbl)
    finally:
        xwl.equivalent = _real_equiv          # type: ignore[assignment]
    if _k8_fail:
        failures.extend("调用点：" + m for m in _k8_fail)
    else:
        print("[ok]  调用点：expand/patch/new 三命令各调用 equivalent ≥1 次（行为级探针）")

    # ---- `check` 对裸 NUL 的**集成面**守卫（调用点级）----
    # 起因：既有断言只直接调 `bare_nul_in_strings`，删掉 `cmd_check` 里整段
    # 裸 NUL 逻辑仍全绿（实测）。命令级断言：裸 NUL 文件 `check` 必须输出「裸 NUL」且 rc=0。
    _b2 = os.path.join(tmp, "k15nul.xwl")
    with open(_b2, "wb") as _f:
        _f.write(b'{"x":"a\x00b"}')
    _r2 = _cap_run([sys.executable, os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "check",
                    _b2, "--no-js"], timeout=120)
    _o2 = (_r2.stdout or "") + (_r2.stderr or "")
    if _r2.returncode != 0 or "裸 NUL" not in _o2:
        failures.append("check 未在集成面报出裸 NUL：rc=%s、含「裸 NUL」=%s"
                        "（删掉 cmd_check 里那段裸 NUL 逻辑应让它红）"
                        % (_r2.returncode, "裸 NUL" in _o2))
    else:
        print("[ok]  集成面：裸 NUL 文件 check 输出「裸 NUL」且 rc=0（命令级）")

    # ---- 断言：`itemids --name` 的 ops 草稿必须是合法 JSON ----
    # 落点错标的更正：`--suggest` 走的是"整表 json.dumps"，一直合法；
    # 真正坏的是 `--name`（`format_itemid_candidates` 用 `%r`）⇒ 断言必须打在 `--name` 上。
    _a1 = os.path.join(tmp, "a1dup.xwl")
    with open(_a1, "w", encoding="utf-8", newline="") as _f:
        _f.write('{"hidden":false,"children":[{"configs":{"itemId":"p1"},"expanded":false,'
                 '"children":[{"configs":{"itemId":"dup","text":"a"},"expanded":false,'
                 '"children":[],"type":"button"},{"configs":{"itemId":"dup","text":"b"},'
                 '"expanded":false,"children":[],"type":"button"}],"type":"panel"}],'
                 '"roles":{},"title":"t","iconCls":"","inframe":false,"pageLink":""}')
    _r3 = _cap_run([sys.executable, os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "itemids",
                    _a1, "--name", "dup"], timeout=120)
    _ops = [l.strip() for l in (_r3.stdout or "").splitlines() if '{"op":"set"' in l]
    try:
        for _l in _ops:
            json.loads(_l)
        _a1_ok = bool(_ops)
    except Exception:
        _a1_ok = False
    if not _a1_ok:
        failures.append("`itemids --name` 的 ops 草稿不是合法 JSON：%s"
                        "（把 format_itemid_candidates 的 json.dumps 换回 repr() 应让它红）" % (_ops[:1],))
    else:
        print("[ok]  `itemids --name` 的 ops 草稿可被 json.loads（%d 条）" % len(_ops))

    # ---- 断言：非有限值（NaN）必须判 `check` ④ 失败（rc=1）----
    _a2 = os.path.join(tmp, "a2nan.xwl")
    with open(_a2, "w", encoding="utf-8", newline="") as _f:
        _f.write('{"n": NaN}')
    _r4 = _cap_run([sys.executable, os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "check",
                    _a2, "--no-js"], timeout=120)
    _o4 = (_r4.stdout or "") + (_r4.stderr or "")
    if _r4.returncode != 1 or "④" not in _o4:
        failures.append("含 NaN 的样本 check 应为 rc=1 且报 ④，实得 rc=%s"
                        "（去掉 parse_constant 会让它 rc=0）" % _r4.returncode)
    else:
        print("[ok]  非有限值被判 check ④ 失败（rc=1）")

    # ---- 金标：含 -0.0 的样本，`expand` 的产出必须与**金标**逐字节相同 ----
    # 本臂证明的是与金标一致，⛔ 不是与自身自洽：旧臂只判 rc==0，而 rc 由**同一份** `expand` 决定
    #   ⇒ 序列化与等价判定**同向**误解时它照样绿（实测：负零折叠 ＋ `equivalent` 退化 ⇒ rc=0、
    #   产出 `{"n": 0}`，旧臂全绿）。⚠️ 单点注入（只折叠、等价判定仍严）会让 `expand` 自判 rc=2，
    #   那种情形旧臂也红 —— 本臂的增益在"同向误解"与"语义等价但字节变了"（排版／写法）这两类。
    _a3 = os.path.join(tmp, "a3negzero.xwl")
    with open(_a3, "w", encoding="utf-8", newline="") as _f:
        _f.write('{"n": -0.0}')
    _r5 = _cap_run([sys.executable, os.path.join(SKILL_ROOT, "scripts", "xwl.py"), "expand", _a3], timeout=120)
    with open(_a3, "rb") as _f:
        _a3_got = _f.read()
    _a3_want = _GOLDEN_NEGZERO.encode("utf-8")
    if _r5.returncode != 0:
        failures.append("含 -0.0 的样本 expand 应 rc=0，实得 %s" % _r5.returncode)
    elif _a3_got != _a3_want:
        failures.append("含 -0.0 的样本 expand 产出与金标不一致：金标 %d B／md5 %s，产出 %d B／md5 %s"
                        "（把 `_number` 的负零分支改回折叠成 `-0`／`0` 应让它红）"
                        % (len(_a3_want), hashlib.md5(_a3_want).hexdigest(),
                           len(_a3_got), hashlib.md5(_a3_got).hexdigest()))
    else:
        print("[ok]  含 -0.0 的样本 expand 产出与金标逐字节相同（与金标一致，不是与自身自洽）")

    # ---- 断言：写盘中途失败 => 目标**不被截断**、无临时残留 ----
    _a4 = os.path.join(tmp, "a4atomic.xwl")
    with open(_a4, "w", encoding="utf-8", newline="") as _f:
        _f.write('{"title":"ORIGINAL-KEEP-ME"}')
    _real_fdopen = os.fdopen

    class _BoomF:                       # 写 5 字节就失败，模拟磁盘满
        def __init__(self, f): self._f = f
        def write(self, d): self._f.write(d[:5]); self._f.flush(); raise OSError(28, "No space")
        def __enter__(self): return self
        def __exit__(self, *a): self._f.close(); return False
    os.fdopen = lambda fd, *a, **k: _BoomF(_real_fdopen(fd, *a, **k))
    try:
        xwl.write_text(_a4, '{"title":"NEW-SHOULD-NOT-LAND"}')
        _a4_raised = False
    except Exception:
        _a4_raised = True
    finally:
        os.fdopen = _real_fdopen
    _a4_body = open(_a4, encoding="utf-8").read()
    _a4_tmp = [n for n in os.listdir(tmp) if n.startswith(".xwlw_")]
    if (not _a4_raised) or _a4_body != '{"title":"ORIGINAL-KEEP-ME"}' or _a4_tmp:
        failures.append("写盘非原子：中途失败后 目标=%r 临时残留=%r raised=%s"
                        "（换回 open(path,\"w\") 直写会让目标被截断 ⇒ 红）"
                        % (_a4_body[:40], _a4_tmp, _a4_raised))
    else:
        print("[ok]  写盘中途失败后目标未被截断、无临时残留")

_GOLDEN_NEGZERO = '{"n": -0.0}'

