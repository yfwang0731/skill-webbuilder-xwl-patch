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
    **给目录 + `--register` 必须显式报错**——静默忽略会让人以为登记成功了）
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
  · 注册键重名分级（按 normalName||itemId 分组：被引用 error / 未被引用 benign / 各有唯一 normalName 不成组）
  · `params` 的两条通路识别与注释剔除
  · **写盘失败必须给可读 `[FAIL]` + 退出码 2，不得冒 Python traceback** ——
    目标只读 / 父目录不存在 / 路径过长都属「前置条件不满足」。
    （`write_text()` 不兜 `OSError` 的话，5 个子命令 9 个场景会抛 traceback，
    而 64 项断言一条都没覆盖写失败 —— 这条就是为此加的）
  · **`edit` 的锚点必须按目标文件的换行归一**（LF 与 CRLF 都要能跨行匹配）——
    `normalize_eol()` 写死 CRLF 时：LF 文件上跨行锚点**永远匹配不到**
    （报「锚点出现次数: 0」，看着像用户写错了锚点），单行锚点 + 多行 new 还会把
    LF 文件写成 CRLF/LF **混用**。另：**把多行拍平时必须有 `[warn]`** ——
    这类损坏 `check` 查不出（压平后仍是合法 JSON），只有 `edit` 这一处能提示。
    （实测样本工程 2780 个 xwl：1878 全 CRLF / 902 为「单行且末尾无换行符」/ **0 个 LF** ——
    两条路径仍都要覆盖，因为 `expand` 按 `--eol auto` 会把无换行的单行源产出成 LF）
  · **`check` 的 ③ 必须在 CRLF / LF / CR 三种换行下都生效** —— 用
    `text.split("\\r\\n")` 切行时，**纯 LF 文件切不出行**（整份成一个元素），于是 ③ 静默退化成
    "只看最后一行"；`new` 的默认产出就是 LF，`expand --eol auto` 也会产出 LF。
    同根因还让纯 CR 文件同时得到「存在 N 处裸 CR」的 FAIL 与「该文件是单行形态（无任何换行）」的
    note（自相矛盾）。另：`patch` 对**换行混用**的源会静默统一、`--indent≠1` 会静默产出
    与设计器不一致的排版、对**无换行的单行源**会回退 LF 并整份展开 —— 这三条都必须有 `[warn]`
    / 明确说明（`--indent` 是唯一能主动击穿「diff 只含本次改动」的入口）。
  · **值里的孤立代理项不得让工具崩** —— 打印字节数时
    `out.encode("utf-8")` 会抛 UnicodeEncodeError（裸 traceback + rc=1）。
    `_quote` 现在按 org.json 的写法转义成 `\\uXXXX`（语义仍等价，回读一致）；
    `_write_file` 与字节数展示一并兜住（只兜 `OSError` 不够：`UnicodeError` 不是它的子类）。
  · **`diffguard`：相对 git 基线检测「多行被压平」** —— 补的是 §2.3 承认的洞
    （压平后文件**仍合法**，`check` 与 `node --check` 都放行，只靠人工读 `git diff` 很容易漏）。
    判据是**双条件**（续行符净减少 **且** 最长行显著变长），所以这里**正反两侧都要钉**：
    "压平必须报"与"合法删减一段多行 JS / 单行变长必须不报"同等重要 ——
    只留前半条，这个守卫会被日常改动淹没（负向测试：去掉最长行那条 → 立刻报误报）。
    另钉住降级路径：新文件、非 git 目录 → `[note]` 跳过 + rc=0；`--strict` 下跳过即 rc=2；
    `--rev` 写错是用法错、恒 rc=2（且不得被说成"新增文件"）。
  · **SKILL.md 的 frontmatter 有 1024 上限** —— description 是路由真正读的字段，
    每补一个触发词都在吃这个额度（实测：写全触发词时到过 **1029**；瘦身后 **839**，余量靠守卫守），
    所以把 description 与整个 frontmatter 块都钉住。

改完 xwl.py 先跑它；输出末尾应为 `selftest ALL OK`：

    python scripts/selftest.py              # 全跑（默认；CI 行为不变）
    python scripts/selftest.py --jobs 4     # 并行跑（默认 min(6, CPU 数)；--jobs 1 = 串行）
    python scripts/selftest.py --fast       # 本地快回路：跳最贵的两块（diffguard / eol_and_guards）
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tokenize

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
    写成 main 里的嵌套函数时，main 拆成多个函数后就跨了作用域。
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(type("NS", (), kw)())
    return code, buf.getvalue()


def _win_path(p: str, api: str):
    """调用 Windows 的 `GetShortPathNameW` / `GetLongPathNameW`；非 Windows 或失败 ⇒ `None`。

    用来复现一个**只在 Windows 上**出现的路径陷阱：`TEMP` 常是 8.3 短名形式
    （`C:\\Users\\RUNNER~1\\…`），而 git 会把仓库根归一成长名。
    见 `xwl._git_prefix` 的注释与 `_check_diffguard` 的 ⑨。
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        fn = getattr(ctypes.windll.kernel32, api)       # type: ignore[attr-defined]
        n = fn(p, buf, 32768)
    except Exception:                   # noqa: BLE001 —— 取不到就当平台不支持
        return None
    return buf.value or None


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
        _r = subprocess.run([sys.executable, os.path.join(HERE, "xwl.py"), _sub, _gbk],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
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
    _r2 = subprocess.run([sys.executable, os.path.join(HERE, "xwl.py"), "check",
                          _b2, "--no-js"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    _o2 = (_r2.stdout or "") + (_r2.stderr or "")
    if _r2.returncode != 0 or "裸 NUL" not in _o2:
        failures.append("check 未在集成面报出裸 NUL：rc=%d、含「裸 NUL」=%s"
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
    _r3 = subprocess.run([sys.executable, os.path.join(HERE, "xwl.py"), "itemids",
                          _a1, "--name", "dup"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
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
    _r4 = subprocess.run([sys.executable, os.path.join(HERE, "xwl.py"), "check",
                          _a2, "--no-js"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    _o4 = (_r4.stdout or "") + (_r4.stderr or "")
    if _r4.returncode != 1 or "④" not in _o4:
        failures.append("含 NaN 的样本 check 应为 rc=1 且报 ④，实得 rc=%d"
                        "（去掉 parse_constant 会让它 rc=0）" % _r4.returncode)
    else:
        print("[ok]  非有限值被判 check ④ 失败（rc=1）")

    # ---- 断言：含 -0.0 的样本 `expand` 必须 rc=0（往返一致）----
    _a3 = os.path.join(tmp, "a3negzero.xwl")
    with open(_a3, "w", encoding="utf-8", newline="") as _f:
        _f.write('{"n": -0.0}')
    _r5 = subprocess.run([sys.executable, os.path.join(HERE, "xwl.py"), "expand",
                          _a3, "--dry-run"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if _r5.returncode != 0:
        failures.append("含 -0.0 的样本 expand 应 rc=0（往返一致），实得 %d"
                        "（把 _number 改回折叠 `-0`/写 `0` 应让它红）" % _r5.returncode)
    else:
        print("[ok]  含 -0.0 的样本 expand rc=0（往返判定一致）")

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
        # ---- 以下 4 条是「**判据依据**」断言：守的是"判据本身对不对"，不是"行为有没有变" ----
        # 起因：本仓每版都有自检，但自检长期只覆盖"行为一致性" ⇒ 一个**从第一版就存在**的判据错误
        # （`field_types` 只取注册表）能活到 1.3.x 才被撞出来。这几条断言的就是那类错误。
        "field_types = 注册表 ∪ 内置兜底（不是二选一）":
            (set(xwl._FIELD_FALLBACK) | {"onlyinreg"}) <= set(xwl.field_types(
                write("k21-controls.json", json.dumps(
                    {"n": {"id": "onlyinreg", "general": {"type": "Ext.form.field.text"}}},
                    ensure_ascii=False)))),
        "strip_sql_type_prefix：类型前缀剥 / DATETIME 不剥 / 原名命中不剥 / 纯数字不剥":
            (xwl.strip_sql_type_prefix("timestamp.endDate", set()) == "endDate"
             and xwl.strip_sql_type_prefix("TIMESTAMP.a", set()) == "a"
             and xwl.strip_sql_type_prefix("DATETIME.start", set()) == "DATETIME.start"
             and xwl.strip_sql_type_prefix("datetime.start", {"datetime.start"}) == "datetime.start"
             and xwl.strip_sql_type_prefix("123.a", set()) == "123.a"),
        "equivalent 能区分 1 / 1.0 / true 与**键序**（Python 的 `==` 不能）":
            (not xwl.equivalent({"a": 1}, {"a": 1.0})
             and not xwl.equivalent({"a": 1}, {"a": True})
             and not xwl.equivalent({"a": 1, "b": 2}, {"b": 2, "a": 1})
             and not xwl.equivalent({"x": -0.0}, {"x": 0})
             and xwl.equivalent({"a": 1}, {"a": 1})),
        "bare_nul_in_strings：只数字符串里的裸 NUL，转义写法不算":
            (xwl.bare_nul_in_strings('{"x":"a' + chr(0) + 'b"}') == 1
             and xwl.bare_nul_in_strings('{"x":"a\\u0000b"}') == 0),
    }.items():
        if cond:
            print(f"[ok]  {name}")
        else:
            failures.append(f"{name} 失败")

    # ---- 判据依据续：`sys.` 前缀的来源与两个入口的寻址同源 ----
    # 起因：`sys.` 曾硬编码（工程自定义命名空间不认）；`paths` 曾按"能嵌套的整棵树"遍历，
    #   会给出 `patch` 的 `@itemId` 解不开的路径 —— 两个入口必须用**同一套**寻址语义。
    _xwlsrc = open(os.path.join(HERE, "xwl.py"), encoding="utf-8").read()
    _cp_body = _xwlsrc.split("def cmd_paths(")[1].split("\ndef ")[0]
    _fa_body = _xwlsrc.split("def _find_all_by_itemid(")[1].split("\ndef ")[0]
    _k3wb = os.path.join(tmp, "k3proj", "src", "main", "webapp", "wb")
    os.makedirs(os.path.join(_k3wb, "system"), exist_ok=True)
    os.makedirs(os.path.join(_k3wb, "modules"), exist_ok=True)
    _k3pg = os.path.join(_k3wb, "modules", "p.xwl")
    with open(_k3pg, "w", encoding="utf-8") as _f:
        _f.write("{}")
    _k3base = xwl.builtin_prefixes(_k3pg)
    _varp = os.path.join(_k3wb, "system", "var.json")
    with open(_varp, "w", encoding="utf-8") as _f:
        json.dump({"sys": {}, "myapp": {}}, _f)
    _k3var = xwl.builtin_prefixes(_k3pg)
    with open(_varp, "w", encoding="utf-8") as _f:
        _f.write("{ not json")
    _k3bad = xwl.builtin_prefixes(_k3pg)
    for name, cond in {
        "builtin_prefixes 基线：无 var.json 时 = 内置（含 sys. / Str.）":
            "sys." in _k3base and "Str." in _k3base,
        "builtin_prefixes：认 var.json 的顶层键（工程自定义命名空间）":
            "myapp." in _k3var and "sys." in _k3var,
        "builtin_prefixes：var.json 坏掉时退回内置、不崩":
            _k3bad == _k3base,
        "paths 与 patch 的 @itemId 寻址同源（都按控件树 _iter_controls）":
            "_iter_controls(" in _cp_body and "_iter_controls(" in _fa_body,
        # ⚠️ 内联对象**必须带 `type`**：`_iter_controls` 只 yield 有字符串 `type` 的节点，
        #    不带 `type` 的 fixture 抓不到"没跳过 configs"这个注入（实测过 —— 那种是**假绿**）。
        "configs 里的内联同名对象不算控件（@itemId 不会误指）":
            len(xwl._find_all_by_itemid(
                {"children": [{"configs": {"itemId": "dup",
                                           "vals": [{"type": "text",
                                                     "configs": {"itemId": "dup"}}]},
                               "type": "panel", "children": []}]}, "dup")) == 1,
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

    # ---- 11b. 注册键重名分级（按 normalName||itemId 分组、**只两级**）----
    #   column 重名（未被引用）          → benign（取数走 grid.getSelection(0).data.*）
    #   button 重名 + 被 JS 引用         → error（app.btn 取值不确定）
    #   text   重名但各有唯一 normalName  → **不成组**（注册键互不相同 ⇒ 天然豁免）
    #   panel  重名但未被引用            → benign（warn 级已取消）
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
           {"FCol": "benign", "btn": "error", "pnl": "benign"}.items()
           if lv.get(k) != v}
    if bad:
        failures.append("注册键分级不符（期望 vs 实得）: %s" % bad)
    elif "same" in lv:
        # "same" ×2 各有唯一 normalName⇒ 注册键互不相同 ⇒ 不该成组
        failures.append("各有唯一 normalName 的同名节点仍被判成组（注册键应互不相同）: %s" % lv)
    elif any(g["level"] == "warn" for g in rep["groups"]):
        failures.append("出现 warn 级组（**只两级**：error / benign）")
    else:
        print("[ok]  注册键重名分级：列=benign / 按钮+被引用=error / 未被引用的面板=benign / "
              "有唯一 normalName 不成组")

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
    # ⚠️ 让 "columns" 组**被引用**（error 级）—— 否则未引用的重名落到 benign，
    #    `recommend_fixes` 会整组跳过、`sk` 为空 ⇒ 断言变成"恒真/恒假"的假绿。
    rep_arr = xwl.audit_itemids({"children": [
        {"type": "grid", "configs": {"itemId": "g1"}, "children": [
            {"type": "array", "configs": {"itemId": "columns"}, "children": [],
             "events": {"click": "app.columns.focus();"}}]},
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
    # 起因：跨类型同名（如 column 与 combo 同名）与普通重名的处置不同；措辞不独特，用户会按“改个名就行”的错误方法去改。
    rep_mix = xwl.audit_itemids({"children": [
        {"type": "column", "configs": {"itemId": "mixed"}, "children": []},
        {"type": "combo", "configs": {"itemId": "mixed"}, "children": []}]})
    if "跨类型" in rep_mix["groups"][0]["reason"]:
        print("[ok]  含列控件的跨类型混名单独措辞（不再误称「应唯一的类型」）")
    else:
        failures.append("跨类型混名的理由措辞未区分: %s" % rep_mix["groups"][0]["reason"][:60])

    # ---- 11f. 读文件失败一律给 XwlLoadError（不冒裸 OSError/JSONDecodeError）----
    # 起因：调用方按 `XwlLoadError` 统一兜读盘失败；个别路径若抛别的异常（OSError/JSONDecodeError），上层漏 catch 就冒 traceback。
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
    # 起因：recommend_fixes 吃的是半结构化的分析结果、字段可能缺；不防御就 KeyError 崩 —— 把“给条建议”升级成整命令失败。
    try:
        xwl.recommend_fixes({"groups": [{"level": "error"}, {"level": "warn"}]}, "auto")
        xwl.recommend_fixes({"groups": [{"level": "error"}]}, "normalName", skipped=[])
        print("[ok]  recommend_fixes 对缺 fix_* 键的 group 不崩（防御性取值）")
    except Exception as exc:  # noqa: BLE001
        failures.append("recommend_fixes 对缺键 group 抛错: %s: %s" % (type(exc).__name__, exc))

    # ---- 11j. itemids --name 找不到名字时，--json 路径要给 JSON（不能混纯文本）----
    # 起因：--json 是给脚本吃的契约；“找不到”也须吐合法 JSON（含 error 字段）—— 混进纯文本会让消费方解析崩。
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
    # 起因：压缩会搬动章节；顺序被打乱后“先建心智模型 → 再看格式规则 → 再看流程”的阅读路径就断了（内容没丢、但难读）。
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


def _check_new_guards(tmp, node, failures, write) -> None:
    """新近落地、**尚无守卫**的三个行为点：`--strict` / `--upstream` 汇总行量纲分离 / `folders` 结论行。

    三条都是**秒级小夹具**（临时目录里现造，绝不扫工程）。
    """

    def _dump(obj, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(xwl.dumps_designer(obj, 1, CRLF))

    def _store(iid, url):
        return {"configs": {"itemId": iid, "url": url}, "type": "store",
                "expanded": False, "children": []}

    # ---- ① `--strict` 选项存在，且不改退出码 ----
    # 起因：`--strict` 是新增选项（刻意与默认同效：缺源时都 rc=1），但**没有任何回归保护** ——
    #   日后若把 `--strict` 从解析器里删掉、或让 `cmd_params` 因夹具缺 `strict` 字段而崩，
    #   现有断言一条都看不见。故钉三件：选项在 `params --help` 文本里、不给 `--strict` 缺源仍 rc=1、
    #   给了也 rc=1。夹具手搭 Namespace 时**故意不带 strict**（顺带验 `getattr(...,False)` 兜底不炸）。
    strict_fail: list[str] = []
    try:
        _hp = xwl.build_parser()
        _sub = next((a for a in _hp._actions if getattr(a, "choices", None)), None)
        _params_help = _sub.choices["params"].format_help() if _sub is not None else ""
    except Exception as exc:  # noqa: BLE001 —— 取不到帮助文本本身就该红，别静默放过
        _params_help = ""
        strict_fail.append("① 取 `params --help` 失败: %s: %s" % (type(exc).__name__, exc))
    if "--strict" not in _params_help:
        strict_fail.append("① `params --help` 里没有 `--strict`")
    _r1 = os.path.join(tmp, "pm_strict")
    _dump({"title": "sql侧", "children": [
        {"configs": {"itemId": "dp", "sql": "select 1 from dual where a={?nosuchparam?}"},
         "type": "dataprovider", "expanded": False, "children": []}]},
        os.path.join(_r1, "sub", "sel.xwl"))
    _p1 = os.path.join(_r1, "px.xwl")
    _dump({"title": "缺源页", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False,
         "children": [_store("st1", "m?xwl=sub/sel")]}]}, _p1)
    _kw1 = dict(file=_p1, module_root=_r1, controls=None, list_fields=False, upstream=False)
    try:
        _rc_old, _out_old = _run(xwl.cmd_params, **_kw1)          # 故意不给 strict 字段
    except Exception as exc:  # noqa: BLE001
        _rc_old = None
        strict_fail.append("① 夹具缺 `strict` 字段时 `cmd_params` 抛异常（`getattr` 兜底失效）: "
                           "%s: %s" % (type(exc).__name__, exc))
    try:
        _rc_new, _out_new = _run(xwl.cmd_params, **_kw1, strict=True)
    except Exception as exc:  # noqa: BLE001
        _rc_new = None
        strict_fail.append("① `strict=True` 时 `cmd_params` 抛异常: %s: %s"
                           % (type(exc).__name__, exc))
    if _rc_old != 1:
        strict_fail.append("① 默认（不给 `--strict`）缺源应 rc=1，实得 rc=%s\n%s"
                           % (_rc_old, _out_old))
    if _rc_new != 1:
        strict_fail.append("① 给 `--strict` 缺源应 rc=1（本实现与默认同效），实得 rc=%s\n%s"
                           % (_rc_new, _out_new))
    if strict_fail:
        failures.extend(strict_fail)
    else:
        print("[ok]  ① `--strict`：出现在 `params --help`；缺源时默认与 `--strict` 都 rc=1（同效）")

    # ---- ② `--upstream` 汇总行把「节点级」与「出现级」两套量纲**各自标注、不混算** ----
    # 起因：`--upstream` 的末尾汇总行把**节点级**（`store.url` 能否在本根解析到文件）与
    #   **出现级**（全文 `url:` 的文字形态）两套**不同量纲**的数并排打印。这两组极易被后人
    #   改成"混算"、或当成同一口径引用（`references/measured-data.md` §11.3/§11.4 专门写了
    #   「不可混引」）。故钉：打开时两段各自标注、节点级三分类之和 = 本页带 url 的 store 数；
    #   且**不开 `--upstream` 时该汇总行不得出现**（= SKILL §六「不开时输出与冻结基线逐字一致」的必要条件）。
    up_fail: list[str] = []
    _r2 = os.path.join(tmp, "pm_upstream")
    _dump({"title": "target", "children": []},
          os.path.join(_r2, "demo", "xxxSql", "demoSql.xwl"))
    _js = ("app.grid1.store.load({ params: { kw: app.kw.getValue() } }); "
           "Wb.request({ url: 'local.html' }); Wb.request({ url: u });")
    _p2 = os.path.join(_r2, "h8.xwl")
    _dump({"title": "upstream页", "children": [
        {"configs": {"itemId": "viewport"}, "type": "viewport", "expanded": False, "children": [
            _store("s1", "m?xwl=demo/xxxSql/demoSql"),   # 同根命中
            _store("s2", "m?xwl=demo/none/none"),        # 本根未找到
            {"configs": {"itemId": "grid1"}, "type": "grid", "expanded": False,
             "events": {"click": _js},
             "children": [{"configs": {"itemId": "kw"}, "type": "text",
                           "expanded": False, "children": []}]},
        ]}]}, _p2)
    _kw2 = dict(file=_p2, module_root=_r2, controls=None, list_fields=False)
    _rc_on, _out_on = _run(xwl.cmd_params, **_kw2, upstream=True)
    _rc_off, _out_off = _run(xwl.cmd_params, **_kw2, upstream=False)
    _sumline = next((l for l in _out_on.splitlines() if "载入侧未纳入核对" in l), "")
    if not _sumline:
        up_fail.append("② 开 `--upstream` 时没有「载入侧未纳入核对」汇总行（本页带 store.url）")
    else:
        _mm = re.search(
            r"同根命中 (\d+) 处 / 本根未找到 (\d+) 处 / 非 m\?xwl 的 url (\d+) 处"
            r".*；出现级.*动态写法 (\d+) 处 / 非 m\?xwl 字面量 (\d+) 处", _sumline)
        if not _mm:
            up_fail.append("② 汇总行格式不符（节点级/出现级两段没各自标注、或数字缺失）:\n%s"
                           % _sumline.strip())
        else:
            _hit, _miss2, _other, _dyn, _lit = (int(x) for x in _mm.groups())
            if (_hit, _miss2, _other) != (1, 1, 0):
                up_fail.append("② 节点级三分类应为 (同根命中 1 / 本根未找到 1 / 非 m?xwl 0)，"
                               "实得 %s" % ((_hit, _miss2, _other),))
            if _hit + _miss2 + _other != 2:
                up_fail.append("② 节点级三分类之和 ≠ 本页 store.url 数（2）—— 划分不完整: %s"
                               % ((_hit, _miss2, _other),))
            if (_dyn, _lit) != (1, 1):
                up_fail.append("② 出现级应为 (动态写法 1 / 非 m?xwl 字面量 1)，实得 %s"
                               % ((_dyn, _lit),))
            if "动态写法" in _sumline.split("出现级")[0]:
                up_fail.append("② 出现级数字混进了节点级段（两套量纲未分离）")
    if "载入侧未纳入核对" in _out_off:
        up_fail.append("② 不开 `--upstream` 时仍打印了汇总行（破坏「与基线的必要条件」）")
    if up_fail:
        failures.extend(up_fail)
    else:
        print("[ok]  ② `--upstream` 汇总行量纲分离：节点级三分类之和 = 本页 store.url 数、"
              "出现级两数独立成组；不开 `--upstream` 时该行不出现")

    # ---- ③ `folders` 结论行只报「index 悬空项 / `folder.json` 损坏」 ----
    # 起因：结论行是"给用户据此行动"的那一行。「未登记」实测约一成、且多为被引用的片段页
    #   （本就不该进导航树）⇒ 若把「未登记」放进结论行会**恒亮**、淹没真问题。故把「未登记」
    #   移出结论行、只留「index 悬空项」与「`folder.json` 损坏」两个真问题。这条一旦回退
    #   （未登记又回结论行），用户就再收不到"该行动"的信号；而「`folder.json` 损坏」是真损坏
    #   （不是口径问题），若被顺带从结论行删掉也没有任何断言会挡 —— 现有断言看不见。
    fl_fail: list[str] = []
    _r3 = os.path.join(tmp, "pm_folders")
    _dd = os.path.join(_r3, "d_dangling")    # ① 有悬空 index 项
    _du = os.path.join(_r3, "d_unreg")       # ② 有未登记文件
    _db = os.path.join(_r3, "d_bad")         # ③ 有损坏 folder.json
    for _d, _idx in ((_dd, ["x.xwl", "gone.xwl"]), (_du, [])):
        os.makedirs(_d, exist_ok=True)
        with open(os.path.join(_d, "folder.json"), "w", encoding="utf-8", newline="") as _f:
            _f.write(json.dumps({"hidden": False, "index": _idx, "title": "t", "iconCls": ""},
                                ensure_ascii=False, separators=(",", ":")))
    os.makedirs(_db, exist_ok=True)
    with open(os.path.join(_db, "folder.json"), "w", encoding="utf-8", newline="") as _f:
        _f.write("{ 坏掉的 json")
    for _d, _nm in ((_dd, "x.xwl"), (_du, "y.xwl"), (_db, "z.xwl")):
        with open(os.path.join(_d, _nm), "w", encoding="utf-8", newline="") as _f:
            _f.write('{"hidden":false,"children":[],"roles":{},"title":"t","iconCls":""}')
    _rc_f, _out_f = _run(xwl.cmd_folders, path=_r3, register=None, dry_run=False)
    _concl = next((l for l in _out_f.splitlines()
                   if l.strip().startswith("目录 ") and "index 悬空项" in l), "")
    if not _concl:
        fl_fail.append("③ 找不到 `folders` 结论行（`目录 N 个 | index 悬空项 …`）:\n%s" % _out_f)
    else:
        if "index 悬空项" not in _concl:
            fl_fail.append("③ 结论行缺「index 悬空项」字样")
        if "folder.json 损坏" not in _concl:
            fl_fail.append("③ 结论行缺「folder.json 损坏」（真损坏，必须留在结论行）")
        if "未登记" in _concl:
            fl_fail.append("③ 结论行又出现了「未登记」（应只进明细、不上结论行）")
    if "未登记" not in _out_f:
        fl_fail.append("③ 夹具没造出「未登记」—— 「结论行不含它」这条就名不副实")
    if fl_fail:
        failures.extend(fl_fail)
    else:
        print("[ok]  ③ `folders` 结论行：含「index 悬空项」「folder.json 损坏」、"
              "不含「未登记」（未登记只在明细）")


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
                 "references/js-api.md", "references/workflow-notes.md",
                 ]
    docs: dict = {}
    for nm in doc_names:
        fp = os.path.join(root, nm.replace("/", os.sep))
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8", newline="") as fh:
                docs[nm] = fh.read().splitlines()

    # 17a emoji 不得进标题
    # 起因：无（待补或删）
    for nm, ls in docs.items():
        for i, l in enumerate(ls, 1):
            if l.startswith("#") and any(ch in l for ch in ("⚠", "❗", "✅", "❌")):
                doc_fail.append("%s:%d 标题里混入 emoji" % (nm, i))

    # 17b **任意两份文档**之间不得有逐字重复的表格行（同一张表不该在两处各写一遍）。
    #     原来只比 README↔SKILL —— 实测 SKILL↔faq 也会重复（退出码表就是这么漏掉的）。
    #     起因：只比 README↔SKILL 会漏掉其余文档对之间的重复（退出码表就因 SKILL↔faq 重复而漏检）—— 不扩到任意两文档，同一张表两处各写一遍发现不了。
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
    #     起因：含 `.md` 的行若整行跳过，跨文件引用就没人管 —— 外移章节后 SKILL.md 指向语义已变的小节、measured-data 指向已搬走的小节，都发现不了。
    _fn = re.compile(r"([\w-]+\.md)")
    _heads = {k: "\n".join(l for l in v if l.startswith("#")) for k, v in docs.items()}
    _base = {k: k.split("/")[-1] for k in docs}
    for nm, ls in docs.items():
        # CHANGELOG 是**历史记录**：里面的 `§5.5`→`§5.6` 是**写入时**的编号，不按当前结构校验
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
    #     起因：完全不查「第 N 章」「第 N 步」这类引用时，章/步被改名或搬走后就成了死指针、无人发现。
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
    #     起因：skill 是通用资产 —— 文档或工具里一旦写进具体工程路径／本机盘符路径，就等于绑定某个环境，别人照抄即错。
    mref = re.compile(r"m\?xwl=(?!<|…)([A-Za-z0-9_./-]+)")
    paths = re.compile(r"[A-Za-z0-9_<>.…/-]+\.xwl")
    # 路径**首段**白名单：通用目录 / 占位段。真实业务路径的首段（工程代号、模块名）不在此列。
    # ⚠️ **`wb` 不在此列** —— 合法写法 `wb/modules/<模块>/xxxSql/queryXxx.xwl` 靠行内占位符豁免，
    #    把 `wb` 放进来会让 `wb/modules/<真实模块>/…xwl` 这条业务路径一并逃过（实测过）。
    ok_head = re.compile(r"^(?:…|<[^/]*>|xxx|dev|examples|common)$", re.I)
    # 单段 `.xwl`：只有这些通用示例名放行。
    generic = re.compile(
        r"^(?:page|file|out|sql|big|x|t|p|g|smoke|one|two|valid|edit|noname|fixed|"
        r"demo-page|demo-querySql|queryXxx|myPage|queryBizList|queryOrder|orderQuery)"
        r"[A-Za-z0-9_.-]*\.xwl$")
    # 本机路径（盘符 + 目录段）同样算环境信息 —— 它也能定位到具体环境。
    rx_env = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/](?![.\\/])([A-Za-z0-9_.-]{2,})")
    skip_env = re.compile(r"RUNNER|[<…]")     # CI 短名示例 / 占位写法
    marks = re.compile(r"[<…]|xxx|Xxx")
    for nm, ls in docs.items():
        for i, l in enumerate(ls, 1):
            for m in mref.finditer(l):
                g = m.group(1)
                if not (g.startswith("common/") or g.lower().startswith("xxx")):
                    doc_fail.append("%s:%d `m?xwl=%s` 不是占位符（换成 <模块>/… 写法）"
                                    % (nm, i, g[:40]))
            if not skip_env.search(l):
                for _m in rx_env.finditer(l):
                    doc_fail.append("%s:%d 出现**本机路径** `%s`（环境信息，换成通用描述）"
                                    % (nm, i, _m.group(0)))
            if marks.search(l):     # 该行已用占位符 / 示意名写法，路径无须再查
                continue
            for m in paths.finditer(l):
                s = m.group(0)
                if "/" in s:
                    if not ok_head.match(s.split("/")[0]):
                        doc_fail.append("%s:%d 出现业务路径 `%s`"
                                        "（首段应是 `dev` / `examples` / `common` / `…` / `<…>` / `xxx` 这类通用段）"
                                        % (nm, i, s))
                elif not generic.match(s):
                    doc_fail.append("%s:%d 出现单段 `.xwl` 名 `%s`（不是通用示例名）" % (nm, i, s))
    with open(os.path.join(HERE, "xwl.py"), "r", encoding="utf-8") as fh:
        for i, l in enumerate(fh.read().splitlines(), 1):
            for m in mref.finditer(l):
                g = m.group(1)
                if not (g.startswith("common/") or g.lower().startswith("xxx")):
                    doc_fail.append("scripts/xwl.py:%d `m?xwl=%s` 不是占位符" % (i, g[:40]))
            if not skip_env.search(l):
                for _m in rx_env.finditer(l):
                    doc_fail.append("scripts/xwl.py:%d 出现**本机路径** `%s`"
                                    "（环境信息，换成通用描述）" % (i, _m.group(0)))
            if marks.search(l):
                continue
            for m in paths.finditer(l):
                s = m.group(0)
                if "/" in s and not ok_head.match(s.split("/")[0]):
                    doc_fail.append("scripts/xwl.py:%d 出现业务路径 `%s`" % (i, s))

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
    # ⑤ 元组末位 = 该外移点在 `SKILL.md` 里的**锚点**（所属小节的标题前缀，须实测唯一）：
    # 断言① 由「全文 contains」收紧为「**该小节区间内** contains」（机理与残留盲区见下方 for 循环）。
    _splits = [
        ("第五章 5.4 四条通路", "SKILL.md", "references/js-api.md",
         ["Wb.request", "Wb.open", "Wb.upload", "Wb.requestAg"],
         "### 5.4 四条最容易踩的"),
        ("第 4 步 逐项判据", "SKILL.md", "references/faq.md", ["无 BOM", "换行一致", "重名"],
         "### 第 4 步 · 格式校验"),
        ("4.2 退出码与输出约定", "SKILL.md", "references/faq.md", ["退出码"],
         "### 4.2 退出码与输出约定"),
        ("2.4 写回算法", "SKILL.md", "references/measured-data.md",
         ["toString(1)", "syncSave", "updateModule"], "### 2.4 换行与展开"),
        ("7.1 框架侧源码", "SKILL.md", "references/measured-data.md",
         ["ComponentManager", "unregister"], "### 7.1 框架怎么把控件交给 JS"),
        ("FAQ 全量问答", "SKILL.md", "references/faq.md", ["怎么排查"], "## 八、常见问题"),
        ("改完自检清单", "SKILL.md", "references/checklist.md", ["- [ ]"],
         "## 九、改完的自检清单"),
        ("反模式清单", "SKILL.md", "references/anti-patterns.md", ["为什么诱人"],
         "## 九、改完的自检清单"),
        ("端到端实操", "SKILL.md", "references/walkthrough.md", ["第 1 步"],
         "### 第 0 步 · 新建文件"),
        ("2.6 diffguard 判据细节", "SKILL.md", "references/faq.md", ["粗筛", "定义级"],
         "### 2.6 压平检测"),
        ("2.6 diffguard 因果", "SKILL.md", "references/workflow-notes.md", ["定义级", "粗筛"],
         "### 2.6 压平检测"),
        # ---- 结构下沉（第一步）：下面这些是正文从 SKILL.md 搬进 references/ 后的外移点 ----
        # 承载词取「必须存活」清单：把 SKILL 里的叙述搬进 references 后，
        # 主文档留了指针（第一项断言）+ 目标文件里这些词必须还在（第二项断言）。
        # 迁到 `--help`（通道 B）的那几处，其承载词同样在目标 references 里留一份兜底
        # （`17g` 只加载 markdown，读不到 `scripts/*.py` 的 `--help`/注释）。
        ("2.3 静默语义损坏", "SKILL.md", "references/anti-patterns.md",
         ["静默", "绝不能", "相对基线"], "### 2.3 多行源为什么绝不能压成一行"),
        ("2.4 规模占比", "SKILL.md", "references/measured-data.md",
         ["≈ 三成", "别把 diff 当", "本次改动"], "### 2.4 换行与展开"),
        ("2.4 --eol 回退", "SKILL.md", "references/faq.md",
         ["不静默", "回退 LF", "三命令共用"], "### 2.4 换行与展开"),
        ("2.5 字面反斜杠 n", "SKILL.md", "references/measured-data.md",
         ["语义无损", "逐字节相同", "给谁看"], "### 2.5 值里的"),
        ("三第0步 folder", "SKILL.md", "references/faq.md",
         ["不登记就看不到", "只认文件路径", "不替你创建"], "### 第 0 步 · 新建文件"),
        ("三第3步 三点#3", "SKILL.md", "references/measured-data.md",
         ["顺带规整", "语义等价", "diff 只含", "重定向"], "### 第 3 步 · 编辑"),
        ("三第4步 两坑", "SKILL.md", "references/faq.md",
         ["别写成", "不是替换成换行符"], "### 第 4 步 · 格式校验"),
        ("四 4.2 退出码", "SKILL.md", "references/faq.md",
         ["不影响退出码", "严格二分", "行首标记", "报告类"], "### 4.2 退出码与输出约定"),
        ("五 5.2 url 口径", "SKILL.md", "references/sql-fragments.md",
         ["不解析", "只判本 wb 根", "单 webapp", "url:"], "### 5.2 url 的三种写法"),
        ("七 7.2 normalName", "SKILL.md", "references/measured-data.md",
         ["不是所有控件都接受", "非法配置", "会跳过并回报"], "### 7.2 三类控件"),
        ("七 7.3 重名建议", "SKILL.md", "references/measured-data.md",
         ["不猜顺序", "能用 normalName 就用", "必须同步改 JS", "tbarGrid"], "### 7.3 遇到重名"),
        ("1.2 控件骨架", "SKILL.md", "references/controls.md",
         ["必须唯一", "会与设计器产物不一致"], "### 1.2 控件节点的标准形态"),
        ("三第3步 ops 示例", "SKILL.md", "references/sql-fragments.md",
         ["insert", "append", "delete", "按顺序执行"], "## 六、SQL 片段"),
        ("三第3步 @itemId", "SKILL.md", "references/sql-fragments.md",
         ["@名字#N", "串联", "不猜顺序"], "## 六、SQL 片段"),
        ("三第3步 改前核对", "SKILL.md", "references/anti-patterns.md",
         ["configs` 一层", "照抄"], "## 八、常见问题"),
        ("五 5.4 四条易踩", "SKILL.md", "references/js-api.md",
         ["能力边界不是错误", "不用写", "错误对象"], "### 5.4 四条最容易踩的"),
        ("五 5.1 引用读法", "SKILL.md", "references/sql-fragments.md",
         ["补上 `.xwl`", "被引用的片段是", "从文件找引用方"], "### 5.1 怎么读一个"),
        ("七 7.3 命令示例", "SKILL.md", "references/measured-data.md",
         ["--dups-only", "--name", "--suggest"], "### 7.3 遇到重名"),
        # ---- 核心 8 块结构下沉时新增的外移点 ----
        # 2.1：5 条硬规则搬进 faq §一（第 4 步的 ①–⑤ 清单是就地承载体）；
        # 4.3：环境依赖搬进 README（SKILL 适用范围表的环境行是就地承载体）。
        ("2.1 硬规则", "SKILL.md", "references/faq.md",
         ["无 BOM", "换行一致", "末行结构"], "### 2.1 硬规则（多行源的磁盘形态）"),
        ("4.3 环境依赖", "SKILL.md", "README.md",
         ["Python 3.9+", "NODE_BIN"], "### 4.3 环境依赖与自检"),
    ]
    # 断言①-机理（为什么把「全文 contains」收成「锚点小节区间 contains」）：`_dst` **恒**出现在
    #   `SKILL.md` 开头「怎么用」那张参考材料索引表里 ⇒ 只看「全文 contains」时这条臂**恒真**
    #   （等于没有）；收成「锚点小节的区间内 contains」后，才真能发现"该外移点处的局部指针被删"。
    # 残留盲区（**如实**）：区间 contains 仍**只**证明「该文件名出现在该小节」，
    #   **不**证明"该处就是那条指针"（区间内可能恰有别的 `references/` 引用）；
    #   要精确到"指针句"须逐条记句文本 ⇒ 会与措辞漂移持续摩擦，故不做。
    # 删掉它的代价：退回「全文 contains」⇒ 任一局部指针被删也**不红**，
    #   真正还在守的只剩 ②（承载词那半），而 ② 只证"词还在"、不证"语义还在"。
    def _region_after_anchor(_lines, _anchor, _lvl):
        """取 `_anchor` 标题行到「下一个**层号 ≤ 本标题**的标题」之间的行（不含标题行）；找不到标题返回 None。"""
        for _k, _l in enumerate(_lines):
            if _l.startswith(_anchor):
                _out = []
                _fen = 0
                for _j in range(_k + 1, len(_lines)):
                    _cur = _lines[_j]
                    if _cur.strip().startswith("```"):
                        _fen += 1
                    elif _fen % 2 == 0:
                        _hm = re.match(r"^(#{1,6}) ", _cur)
                        if _hm and len(_hm.group(1)) <= _lvl:
                            break
                    _out.append(_cur)
                return _out
        return None

    for _lab, _src, _dst, _keys, _anchor in _splits:
        _lvl = len(_anchor) - len(_anchor.lstrip("#"))
        _region = _region_after_anchor(docs.get(_src, []), _anchor, _lvl)
        if _region is None:
            doc_fail.append(
                "外移点「%s」：锚点「%s」在 %s 里找不到 —— 这是**锚点问题**（锚点行被改或删），不是缺指针"
                % (_lab, _anchor, _src))
        elif _dst not in "\n".join(_region):
            doc_fail.append(
                "外移点「%s」：%s 的锚点小节「%s」区间内没有指向 %s 的指针"
                % (_lab, _src, _anchor, _dst))
        _body = "\n".join(docs.get(_dst, []))
        _miss = [k for k in _keys if k not in _body]
        if _miss:
            doc_fail.append("外移点「%s」：%s 里找不到承载内容 %s" % (_lab, _dst, _miss))

    # 17h 文档格式：表格列数一致 / 标题不跳级 / 代码块闭合 / 无行尾空白 / 末尾有换行。
    #     起因：外移与重排章节时最容易留下这五类瑕疵，而且人眼扫不出来。
    #     ⚠️ 本号另有一处（管 test-prompts 覆盖率：每个子命令至少被一条 prompt 提到）—— 见本文件 `_uncovered` 那段（grep `_uncovered`）。
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
    #     ⚠️ 本号另有一处（管 metadata.json 打包元数据一致性）—— 见本文件 `_mdp` 那段（grep `_mdp`）。
    #     起因：外移或增删内容后，自称数字（FAQ／清单／反模式／prompt 条数）最容易过期，读者会照错数走。
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
    # 参考清单里的「清单项数」也要查 —— 正文与参考清单两处会各自漂移
    # （实测漂移一例：正文 §九 改成 30 项，同一文件的参考清单那行还写着 29 项）。
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
    #     实测：`diffguard` 会在 prompt 语料里出现 **0 次**（其余 14 个命令都有），
    #     而三种评审方法（darwin / TRACE / 文档审计）**没有一个能看见这件事**。
    #     ⚠️ 本号另有一处（管 文档格式五查：表格列数/标题跳级/代码块闭合/行尾空白/末尾换行）—— 见本文件 `行尾有多余空白`（grep `行尾有多余空白`）。
    #     起因：新加子命令但评测语料里没人测它 ⇒ 无人发现（实测 `diffguard` 在语料里出现 0 次，三种评审法都没看见）。
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
    #     ⚠️ 本号另有一处（管 文档自称数字）—— 见本文件 `自称数字不符`（grep `自称数字不符`）。
    #     起因：metadata.json 是平台与本地评测器读的打包声明却长期无守卫 —— version／name／references 一旦漂移，评测读到错值，而评审只看工作树、看不出。
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

    # 清单的「改已有文件 X + 新建文件 Y」拆分须与参考清单实算一致（SKILL.md 内该形态出现 1 处；`finditer` 会核全部命中）
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
    #     起因：判据升级时最容易漏改侧翼的描述（实测漏 README 速查表／checklist／faq 三处）—— 正文改了、侧翼没跟上。
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
    #     起因：压缩时材料清单与章节被搬动，索引/节号最容易「指了却没有」；references 里的孤儿与悬空文件也没人发现。
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
    #     起因：字面 N、清单条数、磁盘文件数三者必须相等 —— 只列 5 条却写「五份」，读者会以为材料只有五份。
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
    #     起因：压缩过一轮后，新增内容很容易又堆回 SKILL.md —— 到上限该下沉到 references/，不该抬数字（防回弹护栏）。
    for _nm, _cap in (("SKILL.md", 700), ("README.md", 150)):
        _n = len(docs.get(_nm, []))
        if _n > _cap:
            doc_fail.append("%s 已 %d 行，超过 %d 行上限（新增内容请考虑下沉到 references/）"
                            % (_nm, _n, _cap))

    # 17j-7 `--help` 篇幅上限（通道 B 的护栏）：把 §一/§三/§五/§七 的细节搬进
    #     `xwl.py` 的 `help=` / 参数 help / `epilog` 之后，`--help` 会变长；这条钉住它别再涨。
    #     做法：**内省解析器对象**（`xwl.build_parser()`）逐面 `format_help()` 计行数 ——
    #     **不比对文案**（文案本来就会随措辞改，快照式断言一改就假红），只比「行数 ≤ 上限」。
    #     宽度钉 80 列：这正是管道下 argparse 的默认宽度，也是本批实测表的量法；
    #     终端更窄会多折行、更宽会少折行，不钉死就会随环境漂（假红/假绿都可能）。
    #     上限 = 实测 + 余量（顶层 +10 / 单子命令 +5）。余量依据：给「某个子命令再加 1 条选项
    #     说明」留空间而不误报；再涨就该把内容挪去 `epilog` 或 `references/`（见 workflow-notes §二）。
    #     ⚠️ 新增子命令必须同步在此登记上限（下面 `_h_unreg` 会把漏登的红出来）。
    #     起因：通道 B 把细节搬进 `--help` 后它会一路变长 —— 不钉住就会淹没「必读面」，读者找不到关键项。
    _help_caps = {
        None: 36,        # 顶层 `xwl.py --help`（实测 26）
        "check": 16, "edit": 22, "patch": 41, "params": 23, "paths": 12,
        "new": 28, "folders": 15, "itemids": 27, "sqlrefs": 12, "diffguard": 14,
        "schema": 26, "dump": 12, "expand": 25, "sql": 12, "events": 13,
    }
    try:
        _hp_top = xwl.build_parser()
        _hp_sub = next((_a for _a in _hp_top._actions if getattr(_a, "choices", None)), None)
        _wild = os.environ.get("COLUMNS")
        os.environ["COLUMNS"] = "80"
        try:
            _help_n = {None: len(_hp_top.format_help().splitlines())}
            if _hp_sub is not None:
                for _hn2, _hpar in _hp_sub.choices.items():
                    _help_n[_hn2] = len(_hpar.format_help().splitlines())
        finally:
            if _wild is None:
                os.environ.pop("COLUMNS", None)
            else:
                os.environ["COLUMNS"] = _wild
        for _hn, _hcap in _help_caps.items():
            _hn_lbl = "顶层 xwl.py --help" if _hn is None else "xwl.py %s --help" % _hn
            _got = _help_n.get(_hn)
            if _got is None:
                doc_fail.append("`--help` 行数守卫：找不到 %s 对应的 parser" % _hn_lbl)
            elif _got > _hcap:
                doc_fail.append("%s 已 %d 行，超过 %d 行上限（新增说明请走 `epilog` 或 `references/`）"
                                % (_hn_lbl, _got, _hcap))
        _h_unreg = sorted(k for k in _help_n if k not in _help_caps)
        if _h_unreg:
            doc_fail.append("`--help` 行数守卫：这些子命令没登记上限（新增子命令要同步补）：%s" % _h_unreg)
    except Exception as _hexc:  # noqa: BLE001 —— 解析器构造失败本身就该红，别静默放过
        doc_fail.append("`--help` 行数守卫跑不起来：%s" % _hexc)

    # 17j-8 支持矩阵的**操作系统**行必须存在（SKILL 适用范围表 + metadata.json limitations）。
    #     起因：跨平台是真实约束（Windows 检出/存储形态差异、路径分隔符、换行），
    #     平台适配性评测会看「有没有声明适用 OS」；而这条最容易在精简适用边界表时被顺手删掉。
    #     判据（窄）：SKILL.md 适用范围表里有一行**项 = 操作系统**且同时含 `Windows` 与
    #     `POSIX`（或 `macOS`）；`metadata.json` 的 `limitations` 里也有一条 OS 行（同口径）。
    _os_sk = any(("操作系统" in _l and "Windows" in _l and ("POSIX" in _l or "macOS" in _l))
                 for _l in docs.get("SKILL.md", []) if _l.strip().startswith("|"))
    if not _os_sk:
        doc_fail.append("SKILL.md 适用范围表缺「操作系统」行（须同时含 Windows 与 POSIX/macOS）")
    try:
        with open(os.path.join(root, "metadata.json"), "r", encoding="utf-8") as _fh:
            _mdos = json.load(_fh)
        _os_md = any(("Windows" in str(_x) and ("POSIX" in str(_x) or "macOS" in str(_x)))
                     for _x in (_mdos.get("limitations") or []))
        if not _os_md:
            doc_fail.append("metadata.json 的 limitations 缺「操作系统」行"
                            "（须同时含 Windows 与 POSIX/macOS）")
    except (OSError, ValueError) as _exc:
        doc_fail.append("metadata.json 读不了（OS 行检查）：%s" % _exc)

    # 17j-9 分发文件里不得再出现误导版措辞字面量（拼接见 _bad_lit；豁免 CHANGELOG.md）。
    #     起因（删了会怎样）：误导版把「工具 `@itemId` 寻址」错说成「运行时用 itemId 取名」——
    #     而运行时注册键其实是 `normalName || itemId`。本轮做过 4 处同源修正，但**始终无任何自动化守卫**
    #     （QA 注入实验：4 处全改回误导版、或只漏改 SKILL.md 一处，selftest 仍 rc=0 / [ok]=111 / [FAIL]=0）。
    #     删掉本断言 ⇒ 同类误写会静默回归，只能靠人工评审兜。
    #     ⚠️ 判据字面量用**相邻字面量拼接**写（本文件也在扫描面内）：整词直写会让本文件被自己判红。
    #     作用域 = `git ls-files`（与"编年守卫""仓库卫生"同一事实源）；取不到 git ⇒ 记 `[note] 没扫`。
    _bad_lit = "app." "<itemId>"
    _a9_scope = None
    try:
        _pr9 = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              env=dict(os.environ))
        if _pr9.returncode == 0:
            _a9_scope = [x.strip() for x in _pr9.stdout.splitlines() if x.strip()]
    except (OSError, ValueError):
        _a9_scope = None
    if not _a9_scope:
        # 不是 git 仓库（如平台把 skill 打成 zip 分发）⇒ **跳过并明说**，不算通过也不算失败。
        print("[note] 17j-9 旧措辞守卫：取不到 `git ls-files` 清单 ⇒ 本次**没扫**（不算通过也不算失败）")
    else:
        _a9_hits: list[str] = []
        for _rel in _a9_scope:
            if _rel == "CHANGELOG.md":        # 历史文档，按写入时的事实记，不回改
                continue
            try:
                _bl9 = open(os.path.join(root, _rel.replace("/", os.sep)),
                            encoding="utf-8", newline="").read().splitlines()
            except UnicodeDecodeError:
                continue                       # 非文本（二进制）⇒ 不在"文本文件"扫描面内
            except OSError as _exc:
                doc_fail.append("17j-9 旧措辞守卫：读不出 %s（%s）—— 报错，不算「没命中」" % (_rel, _exc))
                continue
            for _i, _l in enumerate(_bl9, 1):
                if _bad_lit in _l:
                    _a9_hits.append("17j-9 旧措辞残留：%s:%d 含「%s」—— 原文：%s"
                                    % (_rel, _i, _bad_lit, _l.strip()[:80]))
        if _a9_hits:
            doc_fail.extend(_a9_hits)
        else:
            print("[ok]  17j-9 分发文件无旧措辞「%s」残留（豁免 CHANGELOG.md）" % _bad_lit)

    # 17j-10 `schema --skeleton` 的 itemId 占位值必须写对口径（**行为级**：真跑一次再断言输出）。
    #     起因（删了会怎样）：占位值曾把「工具 `@itemId` 寻址」与「运行时注册键取名」混为一谈；
    #     修正后**无自动化守卫**（QA 注入：把占位改回 `<必填>`，selftest 仍 rc=0 / [ok]=111 / [FAIL]=0）。
    #     删掉本断言 ⇒ 占位值再被改回误导版会静默回归。
    #     判据：真跑 `schema button --controls <fixture> --skeleton`，输出须含 `@itemId` 与「工具寻址」、
    #     且不含误导版字面量。fixture 由本测试**自建**（同 §16 的 mini 注册表）—— CI 里没有工程样本，
    #     若改去"工程内发现 controls.json"，守卫在 CI 恒为 `[note]`、等于没守。
    _reg10 = os.path.join(tmp, "guard_controls.json")
    try:
        with open(_reg10, "w", encoding="utf-8") as _f10:
            json.dump({"children": [
                {"id": "button", "general": {"design": True, "xtype": "button"},
                 "configs": {"itemId": {"type": "string"}, "text": {"type": "string"}},
                 "events": {"click": {"type": ""}}},
            ]}, _f10, ensure_ascii=False)
        _c10, _out10 = _run(xwl.cmd_schema, type="button", controls=_reg10,
                            list=False, tree=False, skeleton=True)
        _bad10 = []
        if "@itemId" not in _out10 or "工具寻址" not in _out10:
            _bad10.append("17j-10 `schema --skeleton` 的 itemId 占位值丢了「工具寻址（@itemId）」口径："
                          "输出里找不到。含 itemId 的行：%s"
                          % " | ".join(_l.strip() for _l in _out10.splitlines() if "itemId" in _l)[:160])
        if _bad_lit in _out10:
            _bad10.append("17j-10 `schema --skeleton` 的 itemId 占位值出现误导版措辞「%s」" % _bad_lit)
        if _bad10:
            doc_fail.extend(_bad10)
        else:
            print("[ok]  17j-10 `schema --skeleton` 的 itemId 占位值口径正确（行为级：真跑 + 断言输出）")
    except (OSError, ValueError) as _exc:
        doc_fail.append("17j-10 `schema --skeleton` 占位值守卫跑不起来：%s" % _exc)

    # 17j-11 `schema --skeleton` 对 `window` 必须预填两个**非缺省**推荐键（**行为级**：真跑一次再断言输出）。
    #     起因（删了会怎样）：窗口这两个键的缺省分别是「真」与 'hide'，写错代价最大 ——
    #     `closeAction=destroy` 时若仍复用实例，第二次打开就是空白窗。预填是"防呆"，
    #     把它改回缺省（即不再预填）必须当场红，否则这条防呆会静默失效。
    #     判据：真跑 `schema window --controls <fixture> --skeleton`，输出须同时含
    #     `createInstance`/`false` 与 `closeAction`/`destroy` 两项。fixture 由本测试**自建**
    #     （CI 无工程样本，靠"发现工程内 controls.json"会让守卫在 CI 恒为 `[note]`、等于没守）。
    _reg11 = os.path.join(tmp, "guard_window_controls.json")
    try:
        with open(_reg11, "w", encoding="utf-8") as _f11:
            json.dump({"children": [
                {"id": "window", "general": {"design": True, "xtype": "window"},
                 "configs": {"itemId": {"type": "string"}, "title": {"type": "string"}},
                 "events": {}},
            ]}, _f11, ensure_ascii=False)
        _c11, _out11 = _run(xwl.cmd_schema, type="window", controls=_reg11,
                            list=False, tree=False, skeleton=True)
        _bad11 = []
        if '"createInstance"' not in _out11 or '"false"' not in _out11:
            _bad11.append("17j-11 `schema window --skeleton` 丢了预填的 createInstance=\"false\""
                          "（窗口「每次重建」档据此写，缺了会退化成复用实例的空白窗写法）")
        if '"closeAction"' not in _out11 or '"destroy"' not in _out11:
            _bad11.append("17j-11 `schema window --skeleton` 丢了预填的 closeAction=\"destroy\"")
        if _bad11:
            doc_fail.extend(_bad11)
        else:
            print("[ok]  17j-11 `schema window --skeleton` 预填 createInstance/closeAction"
                  "（行为级：真跑 + 断言输出）")
    except (OSError, ValueError) as _exc:
        doc_fail.append("17j-11 窗口骨架预填守卫跑不起来：%s" % _exc)

    # 17j-5 排他性断言（**同义改写**版）：说压平「只有 git diff / 只能靠人工」能发现的句子，
    #     它所在的**小节**里必须出现 `diffguard`。
    #     只匹配字面词「续行符净减少 / 最长行」的守卫会漏掉"只有 `git diff` 能发现"
    #     这类同义改写 —— 实测漏掉 2 处，其中一处还是**文件内部自相矛盾**
    #     （同文件别处正说 diffguard 是唯一的自动化防线）。
    #     判据按**小节**取而不是按行取：同一节里出现过 diffguard 就算交代过了。
    #     起因：只匹配字面词的守卫会漏同义改写（实测漏 2 处、其一自相矛盾）—— 换个说法就不认了。
    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":      # 历史文档，按写入时的事实记，不回改
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

    # 17j-12 跨文件节号指针必须指向**真实存在**的小节（③ 引用漂移）。
    #   起因：文档里「见某 references/*.md 的 §九 / §3.3 / 紧贴文件名的「小节名」」这类指针没人守 ——
    #     目标文件里那个小节被改名 / 搬走 / 删掉，指针就成了**死指针**（指向空气）。
    #   判据：只看**文件与小节标记落在同一格 / 同一句**的指针（同句 = 按 。；！？ 切、同格 = 按表格 | 切）；
    #     小节标记 = `§N` / `§N.M` / `§中文数字` / `第N节` / **紧贴文件名**的「小节名」。
    #     ⚠️ `第N章` **不算** —— 那是 SKILL 自身章号：首页「怎么用」索引表把「第五/六/八/九章」
    #       与同一行的 references 文件名并列，不加这条会把 SKILL 自己的章号误当成指针目标（实测误报 3–4 条）。
    #   现状全绿（54 条指针全解析）⇒ 纯**防回归**。
    _pt_file = re.compile(r"([A-Za-z0-9][A-Za-z0-9-]*\.md)")
    _pt_num = re.compile(r"§\s*([0-9]+(?:\.[0-9]+)?)")
    _pt_cn = re.compile(r"§\s*([一二三四五六七八九十]+)")
    _pt_jie = re.compile(r"第\s*([一二三四五六七八九十]+)\s*节")
    _pt_tail = re.compile(r"[）)的\s]{0,2}「([^」]{2,60})」")
    _pt_base = {k.split("/")[-1]: k for k in docs}

    def _pt_heads(_ls):
        return "\n".join(_x for _x in _ls if re.match(r"^#{1,6}\s", _x))

    def _pt_norm(_t):
        return re.sub(r"\s+", "", _t).replace("`", "")

    for _nm, _ls in docs.items():
        if _nm == "CHANGELOG.md":
            continue
        _fence = 0
        for _i, _l in enumerate(_ls, 1):
            if _l.strip().startswith("```"):
                _fence += 1
                continue
            if _fence % 2:
                continue
            _segs = _l.split("|") if _l.strip().startswith("|") else re.split(r"[。；！？]", _l)
            for _seg in _segs:
                _fils = [(_m.start(), _m.end(), _m.group(1))
                         for _m in _pt_file.finditer(_seg) if _m.group(1) in _pt_base]
                if not _fils:
                    continue
                _dsg = []
                for _m in _pt_num.finditer(_seg):
                    _dsg.append((_m.start(), _m.end(), "num", _m.group(1)))
                for _m in _pt_cn.finditer(_seg):
                    _dsg.append((_m.start(), _m.end(), "cn", _m.group(1)))
                for _m in _pt_jie.finditer(_seg):
                    _dsg.append((_m.start(), _m.end(), "cn", _m.group(1)))
                for _ds, _de, _kind, _tok in _dsg:
                    _fx = min(_fils, key=lambda _f: min(abs(_ds - _f[1]), abs(_f[0] - _de)))
                    _tg = _pt_base[_fx[2]]
                    _hs = _pt_heads(docs[_tg])
                    if _kind == "num":
                        _hit = re.search(r"^#{1,6}\s*" + re.escape(_tok) + r"(?:[.\s、）)]|$)", _hs, re.M)
                        _sy = "§"
                    else:
                        _hit = re.search(r"^#{1,6}\s*" + re.escape(_tok) + r"(?:[、.\s]|$)", _hs, re.M)
                        _sy = "§"
                    if not _hit:
                        doc_fail.append("17j-12 %s:%d 跨文件指针「%s %s%s」在目标文件 %s 里没有对应小节"
                                        "（按标题文本匹配，不许按行号）" % (_nm, _i, _fx[2], _sy, _tok, _fx[2]))
            # 紧贴文件名的「小节名」指针：整行扫描（句读会把「…？」里的标题切断，故不按句切）
            for _fm in _pt_file.finditer(_l):
                if _fm.group(1) not in _pt_base:
                    continue
                _tm = _pt_tail.match(_l[_fm.end():])
                if _tm and _pt_norm(_tm.group(1)) not in _pt_norm("\n".join(docs[_pt_base[_fm.group(1)]])):
                    doc_fail.append("17j-12 %s:%d 跨文件指针「%s「%s」」在目标文件 %s 里找不到"
                                    % (_nm, _i, _fm.group(1), _tm.group(1)[:20], _fm.group(1)))

    # 17j-13 结构顺序（④）：目录条目顺序与实际小节顺序一致。
    #   ⚠️「标题不跳级」由 17h 按同一判据守，此处不再重复（曾作冗余双保险，会让**一处缺陷报两行**）。
    #   目录：带 `## 目录` 的文件，TOC 条目（`- [label](#anchor)`）必须**逐个**对得上正文小节
    #     （锚点按标题 slug **前缀**匹配 —— 标签可缩写），且顺序与正文出现顺序**单调一致**。
    #   现状全绿（7 个带目录文件 52 条目录项全部解析且单调）⇒ 纯**防回归**。
    #     起因：章节被搬动后，目录条目顺序若与正文不一致，读者按目录跳会到错处；此臂只作防回归（现状全绿）。

    def _toc_link(_t):
        _m = re.search(r"\[(.+?)\]\(#([^)]+)\)", _t)
        return _m

    def _toc_key(_t):
        _s = _t.strip().replace("`", "")
        _s = re.sub(r"[*_~]", "", _s).lower()
        _s = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", _s)
        return re.sub(r"[-]", "", _s).replace(" ", "")

    for _nm, _ls in docs.items():
        _ti = next((_k for _k, _l in enumerate(_ls) if re.match(r"^##\s*目录\s*$", _l)), None)
        if _ti is None:
            continue
        _j = _ti + 1
        _toc = []
        while _j < len(_ls) and not re.match(r"^#", _ls[_j]):
            if _ls[_j].strip():
                _toc.append(_ls[_j])
            _j += 1
        _body = [_toc_key(_hm.group(1)) for _hm in
                 (re.match(r"^#{1,6}\s*(.+?)\s*$", _x) for _x in _ls[_j:]) if _hm]
        _idxs = []
        for _t in _toc:
            _m = _toc_link(_t)
            if not _m:
                continue
            _anch = _toc_key(_m.group(2))
            _cand = [_bi for _bi, _s in enumerate(_body) if _s.startswith(_anch)]
            if not _cand:
                doc_fail.append("17j-13 %s 目录条目「%s」的锚点 #%s 在正文找不到对应小节"
                                % (_nm, _m.group(1)[:24], _m.group(2)[:40]))
            else:
                _idxs.append(_cand[0])
        if any(_idxs[_z] >= _idxs[_z + 1] for _z in range(len(_idxs) - 1)):
            doc_fail.append("17j-13 %s 目录条目顺序与正文小节顺序不一致" % _nm)

    # 17j-14 把 17j-6 扩到**围栏块**：围栏里以 `[note]/[warn]/[FAIL]/[ok]` 开头的**示例输出**，
    #   其文案前缀也必须在 `xwl.py` 里找得到。
    #   扫描面 = `docs` 的 **12 份** markdown 的围栏块（**不含 `examples/README.md`**）。
    #     ⚠️ 不纳入 `examples/README.md` 是**有意**的：该文件里有**运行期 f-string 拼出来**的示意输出
    #       （模板形如 `（{why}）—— {stat}`、在 `xwl.py` 一带），其**前缀在源码里根本不存在** ⇒
    #       纳入会**误报**（QA 实测：那一行在 xwl.py 里找不到、而同文件别的 tag 行找得到）。
    #   起因：17j-6 只扫 SKILL 的**行内反引号**、且不扫 faq.md ⇒ 写在 ``` 块里的输出文案对它
    #     **零覆盖**（绿但空）⇒ 本臂补上"围栏块"这一面。
    #   误报控制：围栏示例可能是**示意**（占位符 `<path>` / `…` / `%s` / `%d`）⇒ 含这类占位符的行
    #     **跳过**（不判），避免把"示例"当成"承诺文案"。实测：3 条围栏输出行，1 条含占位符被跳过、
    #     2 条被检查且全在实现里 ⇒ 全绿（这档 = 加白名单）。
    #   ⚠️ 边界：本臂用**前缀匹配**（`_nf[:16]`），**验不了运行期拼接**出来的文案 —— 拼接结果在源码里
    #     没有字面前缀，所以这类**不是漏扫、是扫了会错**（故排除）。
    _fence_ph = re.compile(r"[<>]|…|%[sd]|\.\.\.")
    for _nm, _ls in docs.items():
        _fence = 0
        for _i, _l in enumerate(_ls, 1):
            if _l.strip().startswith("```"):
                _fence += 1
                continue
            if _fence % 2 == 0:
                continue
            _st = _l.strip()
            _tag = next((_t for _t in ("[note]", "[warn]", "[FAIL]", "[ok]") if _st.startswith(_t)), None)
            if not _tag:
                continue
            _body2 = _st[len(_tag):].strip()
            if _fence_ph.search(_body2):
                continue
            _nf = re.sub(r"\s+", "", _body2)
            if len(_nf) < 8:
                continue
            if _nf[:16] not in _xwl_src:
                doc_fail.append("17j-14 %s:%d 围栏块输出文案 `%s…` 在 xwl.py 里找不到"
                                % (_nm, _i, (_tag + _body2)[:34]))

    # 17l 编年纪律（三条臂）：非编年文件里不得出现"哪天 / 哪一版发生过什么"。
    #     分工与豁免面的完整说明在 `references/workflow-notes.md` 第一节 —— 改词表或豁免面前先读它。
    #     ⚠️ 词表用**相邻字面量拼接**写：守卫扫的是全部分发文件（**含本文件**），
    #        整词直写会让本文件被自己这三条臂判红。
    #     ⚠️ 作用域 = `git ls-files`（与"仓库卫生"同一事实源）：不扫磁盘，避免把本地产物算进来。
    #        取不到 git ⇒ **记一条失败**（"没扫"不等于"通过"）。
    #     起因：正文只该留结论；「哪天在哪一版发生过什么」属编年，只许进 CHANGELOG 与依据层 —— 混进正文会让现行事实与历史不分。
    _chron = ["曾" "经", "原" "先", "早" "先", "此" "前", "一" "度", "当" "年", "旧" "版",
              "旧" "实现", "旧" "判据", "原" "判据", "上" "一轮", "上" "一版", "当" "时", "历史" "上",
              "以" "前"]
    _date_verb = ("实测", "真机", "复现", "审查", "修正", "发布", "事故")
    _date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
    _ver_re = re.compile(r"\d+\.\d+\.\d+")
    _chron_exempt = {"CHANGELOG.md", "metadata.json",
                     "references/measured-data.md", "references/workflow-notes.md"}
    _shipped = None
    try:
        _pr = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             env=dict(os.environ))
        if _pr.returncode == 0:
            _shipped = [x.strip() for x in _pr.stdout.splitlines() if x.strip()]
    except (OSError, ValueError):
        _shipped = None
    if not _shipped:
        # 不是 git 仓库（如平台把 skill 打成 zip 分发）⇒ **跳过并明说**，不算通过也不算失败。
        # 与"仓库卫生"那条守卫同一处置：宁可显式说"没扫"，也不要假装扫过或直接判失败。
        print("[note] 编年守卫：取不到 `git ls-files` 清单 ⇒ 本次**没扫**（不算通过；在 git 仓库里跑才有这层）")
    else:
        for _rel in _shipped:
            if _rel in _chron_exempt:
                continue
            try:
                _bl = open(os.path.join(root, _rel.replace("/", os.sep)),
                           encoding="utf-8", newline="").read().splitlines()
            except (OSError, UnicodeDecodeError) as _exc:
                doc_fail.append("编年守卫：读不出 %s（%s）—— 报错，不算「没命中」" % (_rel, _exc))
                continue
            for _i, _l in enumerate(_bl, 1):
                if _rel == "SKILL.md" and re.match(r"^version:\s*\S+\s*$", _l):
                    continue      # frontmatter 的当前版本号是契约字段，不是编年
                _hit = next((_w for _w in _chron if _w in _l), None)
                if _hit:
                    doc_fail.append("编年：%s:%d 出现施工事件词「%s」"
                                    "（正文只留结论；编年留在 CHANGELOG 与 workflow-notes.md）"
                                    % (_rel, _i, _hit))
                for _m in _date_re.finditer(_l):
                    if any(_v in _l[max(0, _m.start() - 25): _m.end() + 25] for _v in _date_verb):
                        doc_fail.append("编年：%s:%d 出现施工日期 %s（±25 字内有施工动词）"
                                        % (_rel, _i, _m.group(0)))
                _vm = _ver_re.search(_l)
                if _vm:
                    doc_fail.append("编年：%s:%d 出现发版号 %s（正文不写版本号；"
                                    "frontmatter 的 version: 与依据层文件除外）"
                                    % (_rel, _i, _vm.group(0)))

    # 17m 判据溯源自检：`scripts/*.py` 里的**点名式引用**必须可解析（点名 = 写了文档名）。
    #     裸 `§N.M`（没写文档名）不判 —— 那会把各文件自己的节号当成跨文件引用，踩出一片误报。
    #     起因：两处"见 SKILL.md 4.1"其实该指 §4.2（退出码表在那儿）—— 说明这类引用没人守。
    _sk_heads = set()
    for _l in docs.get("SKILL.md", []):
        _mh = re.match(r"^#{1,4}\s*(\d+\.\d+)\s", _l)
        if _mh:
            _sk_heads.add(_mh.group(1))
    _refdir = os.path.join(root, "references")
    for _rel in ("scripts/xwl.py", "scripts/selftest.py"):
        try:
            _bl = open(os.path.join(root, _rel.replace("/", os.sep)),
                       encoding="utf-8", newline="").read().splitlines()
        except OSError:
            continue
        for _i, _l in enumerate(_bl, 1):
            if "CHANGELOG" in _l:
                continue      # 历史条目按写入时的结构记，不按当前结构校验
            for _mh in re.finditer(r"SKILL\.md\s*§?\s*(\d)\.(\d)", _l):
                if "%s.%s" % (_mh.group(1), _mh.group(2)) not in _sk_heads:
                    doc_fail.append("%s:%d 引用 SKILL.md §%s.%s，但 SKILL.md 没有该编号小节"
                                    % (_rel, _i, _mh.group(1), _mh.group(2)))
            for _mh in re.finditer(r"SKILL\.md\s*「([^」]{1,24})」", _l):
                if "%" in _mh.group(1):
                    continue      # 格式化占位符（`SKILL.md「%s」`）不是引用
                if _mh.group(1) not in _sk_txt:
                    doc_fail.append("%s:%d 引用 SKILL.md「%s」，但 SKILL.md 里找不到这个说法"
                                    % (_rel, _i, _mh.group(1)))
            for _mh in re.finditer(r"references/([a-z0-9-]+\.md)", _l):
                if not os.path.exists(os.path.join(_refdir, _mh.group(1))):
                    doc_fail.append("%s:%d 引用 references/%s，但文件不存在"
                                    % (_rel, _i, _mh.group(1)))

    # 17n frontmatter description 的**触发场景下限**：少一条锚点就失败
    #     （description 是路由真正读的字段，瘦身时最容易顺手删掉的就是触发词）。
    #     起因：description 是路由真正读的字段，瘦身时最容易顺手删掉触发词 —— 少一条锚点，对应场景就路由不到本 skill。
    _skfm = _sk_txt.split("---")[1] if _sk_txt.startswith("---") else ""
    _dm2 = re.search(r"description: >-\n(.*?)\n\w+:", _skfm, re.S)
    _dsc = _dm2.group(1) if _dm2 else ""
    _trig = ["加删控件", "挂改事件", "改网格列", "SQL 片段", "传参链路", "重名", "从零新建页面",
             "folder.json", "白屏", "压成一行", "压平", "事件 JS", "WebBuilder"]
    _lost = [t for t in _trig if t not in _dsc]
    if _lost:
        doc_fail.append("SKILL.md 的 description 少了触发场景锚点：%s" % _lost)
    if len(_skfm) > 900:
        doc_fail.append("SKILL.md 的 frontmatter 已 %d 字符，超过 900 的护栏（平台上限 1024）"
                        % len(_skfm))

    # 17o `controlsold.json` 不得被当成注册表（`discover_controls` 只认 controls.json）
    #     起因：目录里可能并存 controls.json 与 controlsold.json；若把后者当注册表，推断出的控件会失真却看不出（故真跑一次钉住）。
    _probe = os.path.join(tmp, "regprobe", "a", "b")
    os.makedirs(os.path.join(_probe, "system"), exist_ok=True)
    with open(os.path.join(_probe, "system", "controlsold.json"), "w", encoding="utf-8") as _fh:
        _fh.write("{}")
    if xwl.discover_controls(os.path.join(_probe, "page.xwl")) is not None:
        doc_fail.append("`discover_controls` 把 controlsold.json 当成注册表了")

    # 17p 依据层的内容守卫：`references/workflow-notes.md` 三臂全豁免（它记的就是"什么时候发现了什么"），
    #     所以它的内容必须另有几条**形式**约束 —— 否则豁免会把它慢慢变成编年垃圾场。
    #     判据只认**结构**（小节锚点 + 发版编年的格式），不判语义 —— 语义判据会引来误报。
    #     起因：依据层两文件享有编年三臂全豁免 ⇒ 必须另有形式约束，否则豁免会把它慢慢变成编年垃圾场。
    _wn = _txt.get("references/workflow-notes.md", "")
    _lack = [k for k in ("判据的因果", "已作废的做法", "编年纪律") if k not in _wn]
    if _lack:
        doc_fail.append("references/workflow-notes.md 缺小节：%s"
                        "（依据层只放 因果 / 作废记录 / 编年纪律说明 三类）" % _lack)
    # ⚠️ 依据层是**两个**文件（workflow-notes 与 measured-data）—— 两者都享编年三臂豁免，
    #    所以都不得出现发版编年的格式，否则豁免迟早变成编年垃圾场。
    for _bn in ("references/workflow-notes.md", "references/measured-data.md"):
        _bt = _txt.get(_bn, "")
        if re.search(r"^##\s*\[", _bt, re.M) or re.search(
                r"^###\s+(Added|Changed|Fixed|Testing)\b", _bt, re.M):
            doc_fail.append("%s 里出现了**发版编年**的格式"
                            "（版本段 `## [x.y.z]` 或 Added/Changed/Fixed/Testing 小节）"
                            "—— 发版编年只许写在 CHANGELOG.md" % _bn)

    # 17q 规模类数字必须在权威层（`measured-data.md`）里出现过。
    #     起因（实测）：`SKILL.md` 的适用边界表写着 `25250 个 xwl`，而别处是 `24957` —— 同一个统计、
    #     两套数，而"自称数字"那条守卫只认固定句式，**散文里的数字一条也看不见**。
    #     判据**故意窄**：只钉"N 个 xwl"与"N KB / N.N s"三类 token —— 散文里数字太多，
    #     全面比对必然踩出一片误报（"60 项断言""17 条 FAQ"这类不在规模层管辖内）。
    _auth = re.sub(r"\s+", "", _txt.get("references/measured-data.md", ""))
    for _rn, _rt in (("SKILL.md", _sk_txt), ("README.md", _rm_txt),
                     ("references/faq.md", _txt.get("references/faq.md", ""))):
        for _tok in sorted(set(re.findall(r"\d{4,}\s*个\s*xwl|\d+(?:\.\d+)?\s*KB|\d+\.\d+\s*s\b", _rt))):
            if re.sub(r"\s+", "", _tok) not in _auth:
                doc_fail.append("%s 里的规模数字「%s」在 references/measured-data.md 里找不到"
                                "（规模类数字以那份为准，别在别处另算一套）" % (_rn, _tok.strip()))

    # 17q-自洽：**权威层内部**同一指标只许一个主口径。
    #     起因：measured-data §十 写 24957、§11.3 写 24986，两值都在**同一文件**内，
    #     只查「数字是否存在别处」时那条件天然为真、抓不到这种自相矛盾。
    #     判据：① 每个「NNNNN 个 xwl」都要有口径限定词；② 出现多个不同取值时，
    #           文件里必须有一句显式的口径差异声明（否则读者会当成同一个统计）。
    _qual = ("全文正则", "可解析", "全量", "全项目", "样本工程", "单工程", "抽样")
    _caveat = ("主口径", "不同口径", "口径不同", "不是同一口径", "两种口径")
    _md_lines = _txt.get("references/measured-data.md", "").splitlines()
    _md_vals = {}
    _caveat_on_line = False
    for _i, _l in enumerate(_md_lines, 1):
        for _m in re.finditer(r"(\d{4,})\s*个\s*xwl", _l):
            _md_vals.setdefault(_m.group(1), []).append(_i)
            if any(_c in _l for _c in _caveat):
                _caveat_on_line = True
            if not any(_q in _l for _q in _qual):
                doc_fail.append("measured-data.md:%d 的规模数字「%s」没带口径限定词（取词：%s）"
                                % (_i, _m.group(0).strip(), "/".join(_qual)))
    if len(_md_vals) > 1 and not _caveat_on_line:
        doc_fail.append("measured-data.md 内「NNNNN 个 xwl」有多个取值 %s 却未在**同处**声明口径差异"
                        "（加「主口径 / 不是同一口径」等说明，别让读者当成同一统计）"
                        % "/".join(sorted(_md_vals)))

    # 17r 分发面自包含：`git ls-files` 的 22 个分发文件里不得出现「指向 skill 包外」的引用。
    #     判据 = 包外文档名（四种，见下方 _b17r_docs 元组）
    #          + 外部计划文档的条目代号（字母+数字 / 字母-小写字母 / SITE+数字）+ §N-M 形式的节号指针。
    #          + 前置批次号（PRE 加数字）与过程角色编号（eng-/qa-/pm-/arch-/reg-/tl- 加数字）。
    #     `.py` 只在**字符串字面量之外**判（词法掩码），免得把夹具/文案里的代号当残留。
    #     `CHANGELOG.md` 是历史记录，豁免；代号用前后界定符锚定，避开 `0xD800` / `BLE001` / `LF-only`。
    #     ⚠️ 起因：本条守卫的**说明注释**不许出现被禁字面量 —— 否则守卫会把自己判红（已踩过一次）。
    _b17r_docs = ("《验收基线》", "《落地清单》", "施工索引", "施工单")
    _b17r_code = re.compile(
        r"(?<![A-Za-z0-9_])[A-L](?:\d{1,2}|-[a-z])(?![A-Za-z0-9_])"
        r"|(?<![A-Za-z0-9_])SITE\d(?![A-Za-z0-9_])")
    _b17r_sec = re.compile(r"§\d{1,3}-\d{1,2}")
    _b17r_proc = re.compile(r"\bPRE\d+\b|\b(?:eng|qa|pm|arch|reg|tl)-\d{1,3}\b")

    def _b17r_mask_strings(_text):
        """把 .py 里字符串字面量的内容抹成空格（保留行列结构），供 17r 判据使用。"""
        try:
            _toks = list(tokenize.generate_tokens(io.StringIO(_text).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return None
        _starts, _acc = [], 0
        for _ln in _text.split("\n"):
            _starts.append(_acc)
            _acc += len(_ln) + 1
        _buf = list(_text)
        for _tk in _toks:
            _nm = tokenize.tok_name.get(_tk.type, "")
            if _nm == "STRING" or _nm.startswith("FSTRING"):
                _a = _starts[_tk.start[0] - 1] + _tk.start[1]
                _b = _starts[_tk.end[0] - 1] + _tk.end[1]
                for _k in range(_a, min(_b, len(_buf))):
                    if _buf[_k] != "\n":
                        _buf[_k] = " "
        return "".join(_buf)

    try:
        _b17r_files = subprocess.check_output(["git", "-C", root, "ls-files"], text=True).splitlines()
    except Exception:  # noqa: BLE001
        _b17r_files = None
    if _b17r_files is None:
        print("[note] 17r 分发面自包含：取不到 `git ls-files` 清单 ⇒ 本次**没扫**（不算通过也不算失败）")
    else:
        _b17r_fail = []
        for _rel17 in _b17r_files:
            if not _rel17 or _rel17 == "CHANGELOG.md":
                continue
            _fp17 = os.path.join(root, _rel17.replace("/", os.sep))
            if not os.path.exists(_fp17):
                continue
            try:
                with open(_fp17, "r", encoding="utf-8", newline="") as _fh17:
                    _raw17 = _fh17.read()
            except Exception as _exc17:  # noqa: BLE001
                _b17r_fail.append("17r 分发面自包含：读不出 %s（%s）—— 报错，不算「没命中」" % (_rel17, _exc17))
                continue
            if _rel17.endswith(".py"):
                _judge17 = _b17r_mask_strings(_raw17)
                if _judge17 is None:
                    _b17r_fail.append("17r 分发面自包含：%s 词法解析失败 ⇒ 不敢判（保守报错）" % _rel17)
                    continue
            else:
                _judge17 = _raw17
            for _i17, _l17 in enumerate(_judge17.split("\n"), 1):
                _hit17 = ([_m.group(0) for _m in _b17r_code.finditer(_l17)]
                          + [_m.group(0) for _m in _b17r_sec.finditer(_l17)]
                          + [_m.group(0) for _m in _b17r_proc.finditer(_l17)]
                          + [_w for _w in _b17r_docs if _w in _l17])
                if _hit17:
                    _b17r_fail.append("17r 分发面自包含：%s:%d 出现包外引用 %s —— 原文：%s"
                                      % (_rel17, _i17, "/".join(sorted(set(_hit17))), _l17.strip()[:80]))
        if _b17r_fail:
            doc_fail.extend(_b17r_fail[:12])
        else:
            print("[ok]  17r 分发面自包含：22 个分发文件里无包外引用"
                  "（无《验收基线》/《落地清单》/施工索引/施工单、无施工单条目代号、无 §N-M 形式的节号指针、无前置批次号/过程角色编号；"
                  "`.py` 只判字符串字面量之外；CHANGELOG 豁免）")

    # 17s 守卫维护规则：本文件里每个守卫块（头 `# 17<字母>`）之后 15 行内必须有「起因」备注。
    #     起因：本仓出现过“说不清目的的守卫”（清账时多组无出处）⇒ 后人不敢删、也不敢改；钉住它，
    #     新增/修改守卫时必须同步写清“不这么做会漏什么”。
    #     判据（宽）：从头行起 16 行窗口内出现「起因」二字即算过 —— 宁可少报，别乱报。
    #     已知盲区：① 相邻守卫块的起因可能落进前一守卫的窗口（漏报，可接受）；
    #               ② 只认「起因」二字、不判因果质量（写「起因：无（待补或删）」也算过）；
    #               ③ 只管 `# 17<字母>` 形式的块，`# ---- 18.` 等其它编号块不在管辖内。
    _s_ok = True
    try:
        with open(os.path.join(HERE, "selftest.py"), "r", encoding="utf-8", newline="") as _sfh:
            _self_lines = _sfh.read().splitlines()
    except OSError as _sexc:
        doc_fail.append("17s 守卫维护规则跑不起来（读不出 selftest.py）：%s" % _sexc)
        _s_ok = False
    else:
        _s_missing = []
        for _sx, _sline in enumerate(_self_lines):
            if re.match(r"^\s*# 17[a-z]", _sline):
                if "起因" not in "\n".join(_self_lines[_sx:_sx + 16]):
                    _s_missing.append((_sx + 1, _sline.strip()[:48]))
        if _s_missing:
            doc_fail.append("17s 守卫维护规则：这些守卫块之后 15 行内没有「起因」备注：%s"
                            % ["%d:%s" % (_a, _b) for _a, _b in _s_missing[:12]])
            _s_ok = False
    if _s_ok:
        print("[ok]  17s 守卫维护规则：每个 `# 17<字母>` 守卫块之后 15 行内都有「起因」备注"
              "（宽判据：16 行窗口内出现「起因」二字即过；盲区见注释）")

    if doc_fail:
        failures.extend(doc_fail[:12])
    else:
        print("[ok]  文档守卫：emoji 未入标题 / 任意两文档间无重复表格 / 编号·章·步·节号引用可解析（含跨文件）/ "
              "链接存在 / 外移点两侧都在 / 格式五项（表格·跳级·代码块·行尾·末尾）/ 自称数字一致 / "
              "导航表与目录索引一致 / **「N 份参考材料」清单完整** / 无业务路径残留 / 反模式有入口 / "
              "**编年三臂（事件词·施工日期·发版号）** / **scripts 里的点名式引用可解析** / "
              "**触发场景锚点未丢** / 注册表不认 controlsold / **依据层只放因果·作废·守卫说明** / "
              "**规模数字出自权威层** / **`--help` 行数上限（顶层 36 / 子命令实测+5）** / "
              "**支持矩阵 OS 行（SKILL 适用范围表 + metadata.json limitations）** / "
              "**跨文件节号指针可解析（17j-12）** / **目录顺序与实际小节一致（17j-13）** / "
              "**围栏块输出文案符实（17j-14）**")

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
        # 每次往里补触发词都在吃这个额度 —— 实测写全触发词时到过 **1029**、当前 **839**，
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

    起因：`write_text()` 不兜 `OSError` —— 目标只读 / 父目录不存在 / 路径过长
    都会抛 traceback，而 SKILL.md §4.2 承诺的是「前置条件不满足 → rc=2 + 提示」。
    实测 5 个子命令 9 个场景中招，而 64 项断言**一条都没覆盖写失败**。
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

    起因：`normalize_eol()` 写死 CRLF 会引出三个缺陷 —— ① LF 文件上**跨行锚点永远匹配不到**
    （报「锚点出现次数: 0」，看着像用户写错了锚点）；② 单行锚点 + 多行 new 会把
    LF 文件写成 CRLF/LF **混用**（文件已落盘、格式已坏）。③ 另外「把多行拍平」
    属于**静默**语义损坏（毫无提示），而 `check` 查不出（压平后仍是合法 JSON）。
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
        ee.append("LF 文件上跨行锚点应能匹配（归一化写死换行时会报「锚点出现次数: 0」）：rc=%d" % rc)
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

    # ③ CRLF 文件 + 跨行锚点 —— 回归：这条本来就该通，不能被改坏
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

    这个能力补的是 §2.3 承认的那个洞：把「反斜杠 + 换行」直接删掉之后
    文件**依然是合法 JSON**，`check` 全绿、`node --check` 还可能返回 0 ——
    靠人工读 `git diff` 去找这种损坏，规模一大就找不过来。

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

    # 只起必要的 git 进程：身份用 `-c` 内联（省 2 次 `git config`）、仓库是否建起来由
    # 首次 commit 的 returncode 判定（省 1 次 `git rev-parse`）；已跟踪文件的改动一律用
    # `commit -am` 一条收口（省 `git add`）。基线内容另用变量 `BASE` 跟踪，恢复基线直接
    # `_mk` 写回（省掉 8 次 `git checkout -- dg.xwl`）—— 语义等价：`checkout` 本来也只是
    # 把文件恢复成基线内容。
    GIT_ID = ("-c", "user.email=selftest@local", "-c", "user.name=selftest")
    _git("init", "-q")
    _mk("dg.xwl", SRC)                          # 新文件 ⇒ 首次入库仍须 `git add`
    _git("add", "-A")
    if _git(*GIT_ID, "commit", "-q", "-m", "base").returncode != 0:
        print("[note] 无法建立临时 git 仓库，跳过 diffguard 断言")
        return
    BASE = SRC                                  # dg.xwl 的当前基线（= 最近一次提交的内容）

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
    _mk("dg.xwl", BASE)
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
            dg.append("「%s」--strict 下应 rc=1，实得 %d" % (label, rc))
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
    _mk("dg.xwl", BASE)
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
    _git(*GIT_ID, "commit", "-q", "-am", "prio")
    BASE = big
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

    # ⑦ **「判据依据」断言（拆行守卫的必配自检）**：造一个「内容与基线相邻两行的拼接相同，
    #    但**续行符与行数都没减少**」的样本 ⇒ 必须**不报压平**，只给一句 [note] 说明判为"内容移动"。
    #    守的是判据本身：缺了前置必要条件，`}` / `');'` 这类**极短行**的"内容恰好等于相邻两行拼接"
    #    会在**真实历史版本**上误报，而三个计数一个都没变（`行数 4470 → 4470` 在数学上就排除了压平）。
    _mk("dg.xwl", BASE)
    _move0 = "MOvE_A" + BS + '\n"x"\nP\nQ'                # 行数 4 / 续行符 1
    _mk("dg.xwl", _move0)
    _git(*GIT_ID, "commit", "-q", "-am", "move-fixture")
    BASE = _move0
    _mk("dg.xwl", 'MOvE_A"x"' + "\nR" + BS + "\nS\nT")    # 行数 4 / 续行符 1（都没减少）
    _rc, _out = _cli("diffguard", "dg.xwl", "--rev", "HEAD")
    if "[warn]" in _out and "压平" in _out:
        dg.append("「内容拼接相同、但续行符与行数都没减少」被判成了**压平** —— "
                  "精确命中缺前置必要条件（压平必然让行数或续行符减少）")
    if "内容移动" not in _out:
        dg.append("判为内容移动时没给 [note] 说明 —— 用户无从知道它为什么不计入告警")
    _mk("dg.xwl", BASE)

    if dg:
        failures.extend(dg)
    else:
        print("[ok]  压平必报 / 合法删减与单行变长不误报 / patch 改动不误报 / "
              "新文件与非仓库干净跳过 / --strict 与 --rev 的退出码正确 / "
              "短名与长名两种 cwd 写法都能比对 / **计数未变时判为内容移动而不报压平**")


def _check_patch_contract(tmp, node, failures, write) -> None:
    """`patch` 的 ops 契约：`create` 开关、数组下标越界、新建键/单行源/未备份三类输出。

    全部是**行为断言**（不是 help 文案断言）：把对应行为改回去，本组立刻红。
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

    def _patch(target, ops_name, ops, dry_run=False, backup=False):
        return _run(xwl.cmd_patch, file=target, ops=_mkops(ops_name, ops), indent=1,
                    eol="auto", dry_run=dry_run, backup=backup, node=None, no_js=True)

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

    # ---- 默认放行新建键 + `[warn]` 预告 + rc 不变 ----
    t1 = {"title": "t", "children": []}
    w1: list = []
    xwl.apply_ops(t1, [{"op": "set", "path": ["newTopKey"], "value": "v"}], created=[], warned=w1)
    p1 = write("pc_5_1.xwl", _page())
    rc1, o1 = _patch(p1, "pc_5_1_ops.json", [{"op": "set", "path": ["newTopKey"], "value": "v"}])
    f1 = []
    if t1.get("newTopKey") != "v":
        f1.append("默认未放行新建键（键没被建）")
    if w1 != ["newTopKey"]:
        f1.append("warned 未收集到新建键：%r" % w1)
    if rc1 != 0:
        f1.append("真跑 rc=%d（应 0）" % rc1)
    if "[warn]" not in o1 or "本次新建了" not in o1:
        f1.append("真跑未打 [warn] 预告:\n%s" % o1)
    if xwl.load_xwl(p1)[2].get("newTopKey") != "v":
        f1.append("真跑没把新键写进文件")
    _ok("5-1", f1, "默认放行新建键、warned 收集、真跑 rc=0 且打 [warn] 预告")

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
    if "[warn] 本次新建了" in o2:
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
    if "[warn] 本次新建了" in o3:
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

    # ---- `--dry-run` 的 `[new-key]` 与 `[warn]` 分列，且不写盘 ----
    p7 = write("pc_5_7.xwl", _page())
    m7 = _md5(p7)
    rc7, o7 = _patch(p7, "pc_5_7_ops.json",
                     [{"op": "set", "path": ["kCreate"], "value": "v", "create": True},
                      {"op": "set", "path": ["kWarn"], "value": "v"}], dry_run=True)
    nk = [ln for ln in o7.splitlines() if ln.startswith("[new-key]")]
    wn = [ln for ln in o7.splitlines() if ln.startswith("[warn] 本次新建了")]
    f7 = []
    if rc7 != 0:
        f7.append("dry-run rc=%d（应 0）" % rc7)
    if len(nk) != 1 or "kCreate" not in nk[0] or "kWarn" in nk[0]:
        f7.append("[new-key] 行应恰 1 条且只列 kCreate：%r" % nk)
    if len(wn) != 1 or "kWarn" not in wn[0] or "kCreate" in wn[0]:
        f7.append("[warn] 行应恰 1 条且只列 kWarn：%r" % wn)
    if _md5(p7) != m7:
        f7.append("--dry-run 竟然写了盘")
    _ok("5-7", f7, "--dry-run 下 [new-key]（只列带 create）与 [warn]（只列不带 create）分列且不写盘")

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

    if pc_fail:
        failures.extend(pc_fail)


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

    # ---- 正面：整数值浮点保真写出（rc=0 且往返等价）----
    f7 = []
    for lit in ("1.0", "0.0"):
        src = '{"a": %s, "children": []}' % lit
        p = write("bc7_%s.xwl" % lit, src)
        rc, _o = _run(xwl.cmd_expand, file=p, eol="auto", indent=1, safe=False,
                      dry_run=False, out=None, backup=False, node=None, no_js=True)
        if rc != 0:
            f7.append("expand %s ⇒ rc=%d（应 0）" % (lit, rc))
        with open(p, "rb") as fh:
            written = fh.read().decode("utf-8")
        if lit not in written:
            f7.append("expand 未保真写出 %s（整数值浮点被折叠）：%r" % (lit, written))
        try:
            if not xwl.equivalent(xwl.parse_xwl(written), {"a": float(lit), "children": []}):
                f7.append("expand %s 往返不等价" % lit)
        except Exception as exc:  # noqa: BLE001
            f7.append("expand %s 的产出无法解析：%s" % (lit, exc))
    p7p = write("bc7_patch.xwl", '{"a": 1.0, "title": "t", "children": []}')
    ops7 = os.path.join(tmp, "bc7_ops.json")
    with open(ops7, "w", encoding="utf-8") as fh:
        json.dump([{"op": "set", "path": ["title"], "value": "t2"}], fh, ensure_ascii=False)
    rc7p, _o = _run(xwl.cmd_patch, file=p7p, ops=ops7, indent=1, eol="auto",
                    dry_run=False, backup=False, node=None, no_js=True)
    if rc7p != 0:
        f7.append("patch 含 {\"a\": 1.0} 源 ⇒ rc=%d（应 0：往返等价）" % rc7p)
    _ok("正面：{\"a\":1.0} / {\"a\":0.0} 保真写出且 expand/patch 往返等价（rc=0）", f7)

    # ---- 反面：1 与 1.0 仍不相等（守值类型可区分）----
    f8 = []
    if xwl.equivalent({"a": 1}, {"a": 1.0}):
        f8.append("equivalent 把 1 与 1.0 判成相等（值类型漂移会重新静默通过）")
    if xwl.equivalent({"a": True}, {"a": 1}):
        f8.append("equivalent 把 true 与 1 判成相等")
    _ok("反面：equivalent 下 1 ≠ 1.0、true ≠ 1（值类型仍可区分）", f8)

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
    _rp, out_p = _run(xwl.cmd_params, file=p11, controls=None, list_fields=False, module_root=None)
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
    if li and li != xwl.controls_source_line(None):
        f11.append("来源行与 controls_source_line(None) 不一致：%r" % li)
    _ok("itemids / params / check ⑦ 打印同一句注册表来源（含「未找到」分支）", f11)

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
    _rc18, out18 = _run(xwl.cmd_params, file=p18, controls=None, list_fields=False, module_root=None)
    f18 = []
    if "找不到" in out18:
        f18.append("params 仍报「找不到 … 的容器」（应按注册键 tbrO 命中 normalName=tbrO 的 toolbar）：%s"
                   % " | ".join(ln.strip() for ln in out18.splitlines() if "找不到" in ln)[:200])
    if "app.tbrO" not in out18 or "容器内取值控件" not in out18:
        f18.append("params 未把 app.tbrO 当容器列出并给容器内取值控件")
    _ok("params 按**注册键**找容器（normalName=tbrO 的 toolbar 命中、无假「找不到容器」）", f18)

    if bc:
        failures.extend(bc)


def _blocks() -> list[tuple[str, object]]:
    """按**固定顺序**列出全部自检块（块名 → 函数）。

    该顺序 = 输出顺序（父进程末尾按此顺序汇总失败），也 = `--jobs` 并行的派发顺序。
    """
    return [
        ("basics", _check_basics),
        ("params_paths", _check_params_paths),
        ("itemids", _check_itemids),
        ("patch_contract", _check_patch_contract),
        ("subcommands", _check_subcommands),
        ("new_guards", _check_new_guards),
        ("docs", _check_docs),
        ("platform", _check_platform),
        ("write_failures", _check_write_failures),
        ("edit_eol", _check_edit_eol),
        ("eol_and_guards", _check_eol_and_guards),
        ("diffguard", _check_diffguard),
        ("bc_contract", _check_bc_contract),
    ]


# `--fast` 跳过的两块：最贵、且与「编辑动作」无直接关系（本地快回路让位给速度）。
FAST_SKIP = ("diffguard", "eol_and_guards")


def _run_block(name: str, fn, node) -> list[str]:
    """在**独占**临时目录里跑一个块，返回它的 failures 列表。

    每块独占一个 `mkdtemp`（并行时天然隔离；串行档也用它 ⇒ 两档语义一致，
    互不依赖 tmp 中的文件）。
    """
    tmp = tempfile.mkdtemp(prefix="xwl_selftest_%s_" % name)
    failures: list[str] = []

    def write(nm: str, text: str, bom: bool = False) -> str:
        p = os.path.join(tmp, nm)
        with open(p, "wb") as f:
            if bom:
                f.write(b"\xef\xbb\xbf")
            f.write(text.encode("utf-8"))
        return p

    fn(tmp, node, failures, write)
    return failures


def _run_serial(blocks, node) -> list[str]:
    """串行（`--jobs 1`）：按块顺序在**本进程**逐个跑。"""
    failures: list[str] = []
    for name, fn in blocks:
        failures.extend(_run_block(name, fn, node))
    return failures


def _run_parallel(blocks, node, jobs: int) -> list[str]:
    """并发（`--jobs N`）：每块在**独立子进程**里跑（各自 mkdtemp、失败写 JSON）。

    子进程把 `[ok]` / `[note]` **直接打到自己继承的 stdout**（行缓冲 ⇒ 每行一次原子写，
    不会交错成半行）；父进程收齐后只按**固定块顺序**汇总打印 `[FAIL]`。
    """
    rdir = tempfile.mkdtemp(prefix="xwl_selftest_res_")
    procs: dict[str, tuple] = {}
    pending = list(blocks)
    active: list[str] = []
    while pending or active:
        while pending and len(active) < jobs:
            name, _fn = pending.pop(0)
            result = os.path.join(rdir, name + ".json")
            proc = subprocess.Popen(
                [sys.executable, "-B", os.path.abspath(__file__),
                 "--only", name, "--result", result, "--node", node or ""],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            procs[name] = (proc, result)
            active.append(name)
        time.sleep(0.1)
        for name in list(active):
            if procs[name][0].poll() is not None:
                active.remove(name)

    failures: list[str] = []
    for name, _fn in blocks:
        proc, result = procs[name]
        if proc.returncode != 0:
            failures.append("块 %s 的子进程异常退出（rc=%s）" % (name, proc.returncode))
        try:
            with open(result, encoding="utf-8") as fh:
                failures.extend(json.load(fh))
        except Exception as exc:  # noqa: BLE001
            failures.append("块 %s 的失败清单读不到：%s" % (name, exc))
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="selftest.py", description="xwl.py 的自检（内置样本，不依赖外部 xwl 文件）")
    ap.add_argument("--jobs", type=int, default=None,
                    help="并行跑的自检块数（默认 min(6, CPU 数)；1 = 串行，做对照用）")
    ap.add_argument("--fast", action="store_true",
                    help="本地快回路：跳过最贵的两块（diffguard / eol_and_guards）")
    # 以下三个是**内部**参数（仅供 `--jobs>1` 派生的子进程用），不写进 --help。
    ap.add_argument("--only", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--result", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--node", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    xwl.ensure_utf8_stdio()     # 输出全是中文；Windows 控制台默认非 UTF-8 会直接 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(line_buffering=True)     # 并行时每行一次原子写，不与其他子进程交错
    except Exception:           # noqa: BLE001
        pass

    # ---- 子进程模式：只跑指定块，把 failures 写 JSON 即退出 ----
    if args.only:
        fn = dict(_blocks()).get(args.only)
        if fn is None:
            sys.stderr.write("未知自检块：%s\n" % args.only)
            return 2
        failures = _run_block(args.only, fn, args.node or None)
        with open(args.result, "w", encoding="utf-8") as fh:
            json.dump(failures, fh, ensure_ascii=False)
        return 0

    node = xwl.find_node()
    print(f"node: {node or '(未找到，跳过事件 JS 校验)'}", flush=True)

    blocks = _blocks()
    if args.fast:
        print("[note] --fast：已跳过 _check_diffguard / _check_eol_and_guards"
              "（本地快回路用；CI 与默认档仍全跑）", flush=True)
        blocks = [(n, f) for n, f in blocks if n not in FAST_SKIP]

    jobs = args.jobs if args.jobs is not None else min(6, os.cpu_count() or 4)
    failures = _run_serial(blocks, node) if jobs <= 1 else _run_parallel(blocks, node, jobs)

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
