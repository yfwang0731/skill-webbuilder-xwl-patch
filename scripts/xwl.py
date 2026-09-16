#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xwl.py —— WebBuilder .xwl 文件处理工具（纯标准库）

设计目标：把「安全编辑 + 格式校验」从"凭记忆手工做"固化成可复跑的命令。

子命令：
  check   <file...>                              五项格式校验 + 事件 JS 语法校验
  new     <out.xwl> [--kind page|sql]            **从零生成** xwl（内置设计器骨架）
  patch   <file> --ops ops.json                  结构级编辑（改对象 → 按设计器规则重建）
  edit    <file> --old-file O --new-file N       安全替换（保留 CRLF，断言出现次数）
  paths   <file>                                 列出 sql / serverScript / url 等字段位置
  folders <path> [--register NAME]               folder.json（导航树索引）一致性检查 / 登记
  dump    <file>                                 按加载器规则解析后美化输出
  sql     <file>                                 抽取 SQL 文本（正确反转义）
  events  <file> [--outdir DIR]                  抽取事件 JS 到文件

关键实现说明（勿改错）：
  xwl 磁盘形态 = 「字面反斜杠 + 真实换行」的多行字符串。
  加载器先做 text.replaceAll("\\\\(\r\n|\r|\n)", "\\\\n")，即把「反斜杠 + 真实换行」
  替换成 **两个字符**：反斜杠 + 字母 n（JSON 的 \n 转义），再按严格 JSON 解析。
  所以本模块的 loader_text() 必须复刻这一点，且替换目标是 2 个字符而不是换行符。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BOM = b"\xef\xbb\xbf"
CRLF = "\r\n"


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #
def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def decode(path: str) -> tuple[str, bool]:
    """返回 (text, has_bom)。"""
    raw = read_bytes(path)
    has_bom = raw[:3] == BOM
    if has_bom:
        raw = raw[3:]
    return raw.decode("utf-8"), has_bom


def write_text(path: str, text: str) -> None:
    """按 CRLF 落盘，UTF-8 无 BOM。newline='' 关掉自动换行转换。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def normalize_eol(text: str) -> str:
    """把任意换行统一成 CRLF（用于 old/new 片段的归一化，便于用 LF 书写片段）。"""
    return re.sub(r"\r\n|\r|\n", CRLF, text)


# --------------------------------------------------------------------------- #
# 加载器等价解析
# --------------------------------------------------------------------------- #
def loader_text(text: str) -> str:
    """复刻加载器：把「反斜杠 + 真实换行」转成「反斜杠 + 字母 n」。"""
    return re.sub(r"\\(?:\r\n|\r|\n)", r"\\n", text)


def parse_xwl(text: str):
    """按加载器规则解析 xwl。

    注意 `strict=False`：加载器用的是 org.json，它**允许字符串里出现裸控制字符**
    （未转义的换行/Tab 也照收），而 Python 的 `json` 默认会报
    `Invalid control character`。不带这个参数会对合法文件误报。
    """
    t = loader_text(text)
    i = t.find("{")
    if i < 0:
        raise ValueError("文件里找不到 `{` —— 不是 xwl 内容（空文件或纯文本）")
    return json.loads(t[i:], strict=False)


# --------------------------------------------------------------------------- #
# 设计器等价序列化（单行 → 多行；与设计器写回逐字节一致）
# --------------------------------------------------------------------------- #
# 写回逻辑位于 WebBuilder 的 com.wb.interact.IDE#updateModule（Webplatform-1.0.jar）：
#     String s = json.toString(1);                                        // ← org.json
#     s = s.replaceAll("\\n", "\\\n");                                    // 字符串内转义 \n → 反斜杠+换行
#     s = s.replaceAll(System.getProperty("line.separator", "\n"), "\n"); // 换行归一
#     FileUtil.syncSave(file, s, "utf-8");
# 所以这里复刻的是 **老版 org.json 的 JSONObject.toString(1)** 排版规则，不是标准 JSON 美化。
# 两者差异（必须还原，否则与设计器输出对不齐）：
#   · 每级缩进 1 个空格（indentFactor=1）
#   · 只有 0 或 1 个元素的容器**不换行**（`{"itemId": "x"}` / `[3]` 内联在一行）
#   · 单元素容器在递归时传的是**当前缩进**而不是加过一层的缩进
_CTRL = {"\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _quote(s: str) -> str:
    """复刻 org.json 的 quote。

    三条容易被忽略的规则：
      1. 只转义 `"`、`\\` 与 <0x20 的控制符；**非 ASCII 原样保留**（中文不转成 \\uXXXX）。
      2. `</`（斜杠紧跟左尖括号之后）会写成 `\\/` —— org.json 防 `</script>` 的经典行为。
      3. 其余 `/` 不转义。
    """
    out = ['"']
    prev = ""
    for ch in s:
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ch == "/":
            out.append("\\/" if prev == "<" else "/")
        elif ch in _CTRL:
            out.append(_CTRL[ch])
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
        prev = ch
    out.append('"')
    return "".join(out)


def _number(v) -> str:
    """复刻 org.json 的 numberToString：整数值去掉尾部 '.0'。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = repr(v)
    if ("." in s) and ("e" not in s) and ("E" not in s):
        s = s.rstrip("0").rstrip(".")
    return s


def _value_to_string(v, f: int, ind: int) -> str:
    if isinstance(v, dict):
        return _obj_to_string(v, f, ind)
    if isinstance(v, list):
        return _arr_to_string(v, f, ind)
    if v is None:
        return "null"
    if isinstance(v, (bool, int, float)):
        return _number(v)
    if isinstance(v, str):
        return _quote(v)
    return _quote(str(v))


def _obj_to_string(o, f: int, ind: int) -> str:
    if not o:
        return "{}"
    # 只有一个键 → 不换行；且传 ind（不是 newind），与老版 org.json 一致
    if len(o) == 1:
        k, v = next(iter(o.items()))
        return "{" + _quote(str(k)) + ": " + _value_to_string(v, f, ind) + "}"
    newind = ind + f
    sb = "{"
    for k, v in o.items():
        if len(sb) > 1:
            sb += ","
        sb += "\n" + " " * newind + _quote(str(k)) + ": " + _value_to_string(v, f, newind)
    sb += "\n" + " " * ind
    return sb + "}"


def _arr_to_string(a, f: int, ind: int) -> str:
    if not a:
        return "[]"
    if len(a) == 1:
        return "[" + _value_to_string(a[0], f, ind) + "]"
    newind = ind + f
    sb = "["
    for i, x in enumerate(a):
        if i > 0:
            sb += ","
        sb += "\n" + " " * newind + _value_to_string(x, f, newind)
    sb += "\n" + " " * ind
    return sb + "]"


# 完整的 JSON 字符串 token（含转义），用于「只在引号内做换行改写」
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _reline_string_token(tok: str, eol: str) -> str:
    """把字符串 token 里的 `\\n` 转义换成「反斜杠 + 换行」，其余转义原样保留。

    逐转义对扫描 —— 直接对整段文本 replace 会误伤 `\\\\n`（值是字面反斜杠 + n）。
    事实上 WebBuilder 自己就踩了这个坑（见 SKILL.md「已知缺陷」），这里做的是**安全版**。
    """
    body = tok[1:-1]
    out = ['"']
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append("\\" + eol if nxt == "n" else c + nxt)
            i += 2
        else:
            out.append(c)
            i += 1
    out.append('"')
    return "".join(out)


def dumps_designer(obj, indent_factor: int = 1, eol: str = CRLF, safe: bool = False) -> str:
    """序列化成 xwl 的多行磁盘形态，与设计器写回（`IDE.updateModule`）一致。

    eol：设计器在服务器上写的是 **LF**；Windows 工作区因为 git `autocrlf` 看到的是 CRLF。
    默认按 CRLF 输出以贴合本项目**工作区**形态；要还原设计器原始产物用 `eol="\\n"`。

    safe=False（默认）：与设计器**逐字节一致**，包括它对「字面反斜杠 + n」的误伤
      —— 值里出现 `\\` + `n`（源码里的字面 `\\n`）时，设计器会把它改写成「反斜杠 + 换行」，
      这属于 WebBuilder 自身的缺陷（见 SKILL.md）。要复刻设计器产物就用这个模式。
    safe=True：逐转义对处理，不动字面 `\\` + `n`，语义无损；但产出与设计器会不一致。
    """
    t = _value_to_string(obj, indent_factor, 0)
    if safe:
        parts: list[str] = []
        pos = 0
        for m in _STRING_RE.finditer(t):
            parts.append(t[pos:m.start()].replace("\n", eol))   # 引号外：结构换行
            parts.append(_reline_string_token(m.group(0), eol))  # 引号内：转义 \n → 反斜杠+换行
            pos = m.end()
        parts.append(t[pos:].replace("\n", eol))
        return "".join(parts)
    # 忠实复刻 IDE.updateModule 的第一步 replaceAll（正则 = 字面反斜杠 + n）
    t = re.sub(r"\\n", lambda m: "\\\n", t)
    if eol != "\n":
        t = t.replace("\n", eol)
    return t  # 设计器不加尾换行


class XwlLoadError(Exception):
    """读文件 / 解析 xwl 失败 —— 消息面向用户，可直接打印。"""


def read_xwl_text(path: str):
    """**只读 + 解码**（不解析），返回 `(text, has_bom)`；失败抛 `XwlLoadError`。

    文本级 `edit` 用它 —— 它必须能处理**已经坏掉**的文件（那正是 `edit` 存在的意义），
    所以这条路径**不做解析**。
    """
    try:
        return decode(path)
    except OSError as exc:
        raise XwlLoadError("无法读取 %s：%s" % (path, exc)) from exc
    except UnicodeDecodeError as exc:
        raise XwlLoadError("不是 UTF-8 文本（xwl 必须是无 BOM 的 UTF-8）：%s" % exc) from exc


def load_xwl(path: str):
    """**读 + 解码 + 按加载器规则解析**，返回 `(text, has_bom, obj)`；失败抛 `XwlLoadError`。

    各子命令统一走它，避免把 `FileNotFoundError` / `JSONDecodeError` 冒到顶层变成裸 Traceback。
    """
    text, has_bom = read_xwl_text(path)
    try:
        return text, has_bom, parse_xwl(text)
    except Exception as exc:  # noqa: BLE001
        raise XwlLoadError("无法按加载器规则解析 %s：%s" % (os.path.basename(path), exc)) from exc


# --------------------------------------------------------------------------- #
# 遍历
# --------------------------------------------------------------------------- #
def walk(obj):
    """深度遍历 dict/list，产出 (dict, key, value) 与裸值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield obj, k, v
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def collect_events(obj) -> list[tuple[str, str]]:
    """抽取所有 events.<type> 的 JS 代码，返回 [(事件名, JS)]。"""
    out: list[tuple[str, str]] = []
    for _parent, key, value in walk(obj):
        if key == "events" and isinstance(value, dict):
            for ev_name, code in value.items():
                if isinstance(code, str):
                    out.append((str(ev_name), code))
    return out


def collect_sql(obj) -> list[tuple[str, str]]:
    """抽取所有键名含 'sql' 的字符串值，返回 [(键名, SQL)]。"""
    out: list[tuple[str, str]] = []
    for _parent, key, value in walk(obj):
        if isinstance(value, str) and "sql" in str(key).lower() and value.strip():
            out.append((str(key), value))
    return out


# --------------------------------------------------------------------------- #
# node 定位
# --------------------------------------------------------------------------- #
def _norm_exe(p: str) -> str:
    """把 MSYS/Git-Bash 风格路径（/c/Users/...）转成 Windows 原生路径。"""
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", p):
        p = p[1] + ":" + p[2:]
    return p


def find_node(explicit: str | None = None) -> str | None:
    if explicit:
        p = _norm_exe(explicit)
        return p if os.path.exists(p) else None
    env = os.environ.get("NODE_BIN")
    if env:
        p = _norm_exe(env)
        if os.path.exists(p):
            return p
    return shutil.which("node") or shutil.which("node.exe")


def node_check(node: str, code: str) -> tuple[bool, str]:
    """用 node --check 校验一段 JS 语法。返回 (ok, 错误信息)。

    注意：某些事件（如 tagEvents）的值是 **JSON 对象字面量字符串**
    （形如 `{"beforeedit": function(e){...}}`）。`node --check` 在"语句位置"看到
    以 `{` 开头的代码会当成块语句 → 误报。故先裸验，失败且形如对象字面量时，
    再包一层括号（表达式位置）复验，通过即视为合法。
    """
    candidates = [code]
    stripped = code.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append("(" + code + ")")

    last_err = ""
    for cand in candidates:
        ok, err = _node_check_once(node, cand)
        if ok:
            return True, ""
        last_err = err
    return False, last_err


def _node_check_once(node: str, code: str) -> tuple[bool, str]:
    fd, tmp = tempfile.mkstemp(suffix=".js", prefix="xwl_ev_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(code)
        proc = subprocess.run(
            [node, "--check", tmp], capture_output=True, text=True, timeout=60
        )
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout).strip()
    except Exception as exc:  # noqa: BLE001
        return False, f"node 调用失败: {exc}"
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def cmd_check(args) -> int:
    node = find_node(args.node)
    if node is None and not args.no_js:
        print("[warn] 未找到 node，事件 JS 语法校验被跳过（用 --node 指定，或 --no-js 静音）")

    failed = False
    for path in args.files:
        print(f"=== check: {path}")
        errors: list[str] = []
        try:
            text, has_bom = decode(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] 无法读取/解码: {exc}")
            failed = True
            continue

        # ① BOM
        if has_bom:
            errors.append("① 文件带 UTF-8 BOM（必须无 BOM）")

        # ② 换行：必须「全文件一致」，LF-only 与 CRLF-only 都合法（不能混用）
        n_lf, n_crlf, n_cr = text.count("\n"), text.count("\r\n"), text.count("\r")
        bare_lf, bare_cr = n_lf - n_crlf, n_cr - n_crlf
        if n_crlf and bare_lf:
            errors.append(
                f"② 换行混用：{n_crlf} 个 CRLF 里夹着 {bare_lf} 个裸 LF（同一文件必须一致）"
            )
        if bare_cr:
            errors.append(f"② 存在 {bare_cr} 处裸 CR（单独的 CR 不是合法换行）")

        notes: list[str] = []
        if n_crlf == 0 and n_lf == 0 and text.strip():
            notes.append(
                "该文件是单行形态（无任何换行）。可用 `xwl.py expand` 转成规范多行；"
                "**不要**把多行文件改成单行。"
            )
        elif n_crlf == 0 and n_lf:
            notes.append("该文件是 LF 换行（设计器/仓库的原始形态），合法。")

        lines = text.split(CRLF)

        # ③ 反斜杠 + 空白
        bad_ws = [i + 1 for i, ln in enumerate(lines) if re.search(r"\\[ \t]+$", ln)]
        if bad_ws:
            errors.append(
                f"③ 第 {bad_ws[:10]} 行以「反斜杠+空白」结尾（续行符后不能有空格/Tab）"
            )

        # ⑤ 末行不得以续行符结尾
        if lines and lines[-1].endswith("\\"):
            errors.append("⑤ 末行以反斜杠结尾（最后一行不能加续行符）")

        # ④ 加载器等价解析
        obj = None
        try:
            obj = parse_xwl(text)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"④ 加载器等价解析失败: {exc}")

        # ⑥ 事件 JS 语法
        events: list[tuple[str, str]] = []
        if obj is not None and node and not args.no_js:
            events = collect_events(obj)
            for name, code in events:
                ok, err = node_check(node, code)
                if not ok:
                    head = err.splitlines()[0] if err else "语法错误"
                    errors.append(f"⑥ events.{name} JS 语法错误: {head}")

        # ⑦ itemId 重名（分级）—— 只有「重名 **且** 已被事件 JS 引用」才算 FAIL
        itemid_warns: list[str] = []
        itemid_note = ""
        if obj is not None and not getattr(args, "no_itemid", False):
            rep = audit_itemids(obj, controls_path=discover_controls(path))
            for m in rep["errors"]:
                errors.append(f"⑦ {m}")
            itemid_warns = rep["warns"]
            n_g = len(rep["groups"])
            if n_g:
                itemid_note = (f"⑦ itemId 重名 {n_g} 组（error {len(rep['errors'])} / "
                               f"warn {len(rep['warns'])} / benign {rep['n_benign']}）"
                               f" —— 明细: `xwl.py itemids {os.path.basename(path)}`")

        if errors:
            for e in errors:
                print(f"  [FAIL] {e}")
            print("  -> FAIL")
            failed = True
        else:
            print("  [ok]   ① BOM  ② 换行一致  ③ 续行空白  ④ 解析  ⑤ 末行结构")
            if events:
                print(f"  [ok]   ⑥ {len(events)} 个事件 JS 语法全部通过")
            elif obj is not None and not args.no_js and node:
                print("  [ok]   ⑥ 无 events 节点")
            if itemid_note:
                print("  [ok]   " + itemid_note)
            print("  -> OK")
        for w in itemid_warns:
            print(f"  [warn] {w}")
        for n in notes:
            print(f"  [note] {n}")

    print("=== 结果:", "FAIL" if failed else "ALL OK")
    return 1 if failed else 0


def _post_check(file: str, args) -> int:
    """写盘后的**格式**自检 —— 只回答「这次改动有没有破坏格式」。

    itemId 重名（第 ⑦ 项）是**文件既有的质量属性**，不是本次改动造成的：
    若一并判定，会出现"写盘成功却返回非 0"的误导。所以这里显式跳过，只在末尾给一条指引。
    """
    print("--- 自动校验（本次改动是否破坏格式）---")
    ns = argparse.Namespace(files=[file], node=getattr(args, "node", None),
                            no_js=getattr(args, "no_js", False), no_itemid=True)
    rc = cmd_check(ns)
    print("提示：itemId 重名不在本步判定范围；要连它一起体检，跑 "
          "`xwl.py itemids %s`" % os.path.basename(file))
    return rc


# --------------------------------------------------------------------------- #
# edit
# --------------------------------------------------------------------------- #
def cmd_edit(args) -> int:
    with open(args.old_file, "r", encoding="utf-8", newline="") as f:
        old = normalize_eol(f.read())
    with open(args.new_file, "r", encoding="utf-8", newline="") as f:
        new = normalize_eol(f.read())

    try:
        text, has_bom = read_xwl_text(args.target)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2
    if has_bom:
        print("[FAIL] 目标文件带 BOM，本工具不处理；请先确认它本来就不该有 BOM")
        return 2

    count = text.count(old)
    print(f"锚点出现次数: {count} (期望 {args.expect})")
    if count != args.expect:
        print("[FAIL] 锚点出现次数与期望不符，未写文件（防止改错位置）")
        return 2

    if args.dry_run:
        print("[dry-run] 未写入。变更后长度:", len(text) - count * len(old) + count * len(new))
        return 0

    if args.backup:
        bak = args.target + ".bak"
        with open(bak, "wb") as f:
            f.write(read_bytes(args.target))
        print(f"备份 -> {bak}")

    write_text(args.target, text.replace(old, new))
    print(f"已写入: {args.target}")

    # 立即自检（只判格式；itemId 重名见 _post_check 注释）
    return _post_check(args.target, args)


# --------------------------------------------------------------------------- #
# expand
# --------------------------------------------------------------------------- #
def cmd_expand(args) -> int:
    """把（通常是单行的）xwl 规范成设计器同款多行形态。

    算法与 WebBuilder 的 `IDE.updateModule` 完全一致（见文件上方 dumps_designer 注释），
    所以输出与设计器保存结果**逐字节一致**（换行符按 --eol 决定）。
    """
    try:
        text, has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}（先修格式再转换）")
        return 2
    if has_bom:
        print("[FAIL] 目标文件带 BOM；本工具不处理，请先确认它本来就不该有 BOM")
        return 2

    # EOL：auto = 沿用原文件（全 CRLF 就 CRLF，否则 LF）
    if args.eol == "auto":
        eol = CRLF if text.count(CRLF) else "\n"
    else:
        eol = "\n" if args.eol == "lf" else CRLF

    out = dumps_designer(obj, args.indent, eol, safe=args.safe)
    print(f"原文件: {len(text.encode('utf-8'))} B, CRLF={text.count(CRLF)}, LF={text.count(chr(10))}")
    print(f"规范化后: {len(out.encode('utf-8'))} B, 换行={'CRLF' if eol == CRLF else 'LF'}"
          f"{', 安全模式(--safe)' if args.safe else ''}")

    # 语义等价比对（必须过，否则不写）
    try:
        if parse_xwl(out) != obj:
            print("[FAIL] 重新序列化后语义不一致，已中止（不写文件）")
            return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 重新序列化结果无法解析，已中止: {exc}")
        return 2
    print("[ok]   语义等价比对通过（重新解析后与原对象完全一致）")

    if args.dry_run:
        print("[dry-run] 未写入")
        return 0

    dest = args.out or args.file
    if args.backup and dest == args.file:
        bak = args.file + ".bak"
        with open(bak, "wb") as f:
            f.write(read_bytes(args.file))
        print(f"备份 -> {bak}")
    write_text(dest, out)
    print(f"已写入: {dest}")

    rc = _post_check(dest, args)
    if rc == 0:
        print("> 排版与设计器 `IDE.updateModule` 一致（org.json toString(1) 布局）。")
        print("> 若原文件已被设计器保存过，正常情况下本命令应产出**逐字节相同**的内容。")
    return rc


# --------------------------------------------------------------------------- #
# patch（结构级编辑：改对象 + 按设计器规则重建，不碰文本层）
# --------------------------------------------------------------------------- #
# itemId 的「重名严重度」不是一刀切 —— 取决于「控件类型 + 是否已被 JS 引用 + 字段有无 normalName」。
# 分级依据来自 TSHT 全项目实测（2780 个 xwl / 59791 个含 itemId 的控件节点 / 12304 段事件 JS）：
#
#   benign — 重名在实践中无害
#     · 列控件 column / tcolumn：实测 3393 组重名，**0 组**被事件 JS 引用。
#       取数走 `app.<grid>.getSelection(0).data.XXX`，不会去取列控件本身。
#       命名约定：字段名 + `_COL` / `Col` 后缀（实测 14213 / 20771 个列 itemId 带此后缀）。
#     · 取值控件（14 个 Ext.form.field.*）且**每个同名节点都有互不相同的非空 normalName**
#       —— 此时 JS 走 `app.<normalName>` 区分（实测 129 组已这样做）。
#     · itemId 不是合法 JS 标识符（含中文 / 空格 / `.` 等）—— 只能用 `app.get('名')` 取；
#       实测仅 57 个节点属于此类（多在 query / 描述性 itemId 上）。
#   warn  — 不规范；老代码可容忍，**新代码必须区分**
#     · 其余类型重名（button / item / panel / tab / toolbar / grid / store …）
#       实测 1651 组，其中 1488 组未被 JS 引用（仅不规范）
#     · 取值控件重名但 normalName 缺失或彼此重复（实测 745 组）
#   error — 真隐患：重名**且**该名字已被事件 JS 引用
#     （框架按 `normalName || itemId` 把控件注册到页面作用域，重名时取到的对象与
#      "你看着的那个节点"可能不是同一个；实测 must 类 163 组 / field 类 396 组被引用）
_IID_COL_TYPES = frozenset({"column", "tcolumn"})
_IID_JS_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
_IID_INDEX_RE = re.compile(r"^(?P<name>.+)#(?P<idx>\d+)$")
_APP_REF_BARE = re.compile(r"\bapp\.([A-Za-z_$][\w$]*)")
_APP_REF_GET = re.compile(r"""app\.get\(\s*['"]([^'"]+)['"]""")
# `app.<名字>` 里属于方法/框架成员而非控件 itemId 的名字 —— 统计引用时排除
_APP_REF_RESERVED = frozenset({
    "get", "set", "add", "remove", "insert", "down", "up", "query", "queryBy", "find",
    "fireEvent", "on", "un", "suspendEvents", "resumeEvents", "getId", "getCmp",
    "getViewModel", "getController", "getStore", "getSelection", "getWidget",
    "ownerCt", "items", "store", "el", "body", "id", "is", "callParent",
})

# 合法接受 `normalName` 的控件类型 —— 权威来源是控件注册表（wb/system/controls.json）里
# 该控件 `configs` 是否含 `normalName` 键。下面这份内置清单取自 TSHT 工程实测
# （注册表 133 个节点，其中 **89 个**接受 normalName、44 个不接受）。给了 --controls 就从注册表现算。
_NORMALNAME_FALLBACK = (
    "axis button buttongroup chart chartlabel check checkgroup colorfield column combo comp "
    "container datamodel dataview date datetime displayfield echart editing feature fieldcontainer "
    "fieldset file form grid hidden htmleditor image item label menu month number panel picker "
    "propertygrid radiogroup series slider store tab tableview taxis tbutton tchart tchartlabel "
    "tcheck tcolumn tcomp tcontainer tdataview tdate tdatetime text textarea tfieldset tfile "
    "tform tgrid thidden timage time tlabel tlist tmenu tnavigate tnlist tnumber toolbar tpanel "
    "tradio tree treestore tscroller tselect tseries tslider tspacer tspinner tstore ttab ttext "
    "ttitlebar ttoggle ttoolbar ttreestore tviewport viewport window"
).split()


def discover_controls(start_file: str) -> str | None:
    """从文件位置向上找设计器控件注册表 `wb/system/controls.json`。"""
    d = os.path.dirname(os.path.abspath(start_file))
    for _ in range(12):
        for cand in (os.path.join(d, "system", "controls.json"),
                     os.path.join(d, "wb", "system", "controls.json")):
            if os.path.isfile(cand):
                return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def normalname_types(controls_path: str | None = None) -> tuple:
    """合法接受 `normalName` 的控件类型（权威来源 = 注册表 configs 的键）。"""
    if controls_path:
        try:
            reg = json.load(open(controls_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            reg = None
        if reg is not None:
            ids: set[str] = set()

            def walk(o):
                if isinstance(o, dict):
                    if (isinstance(o.get("id"), str) and isinstance(o.get("configs"), dict)
                            and "normalName" in o["configs"]):
                        ids.add(o["id"])
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(reg)
            if ids:
                return tuple(sorted(ids))
    return tuple(_NORMALNAME_FALLBACK)


_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _distinguisher(parent_itemid: str) -> str:
    """取父级 itemId 的"区分段" —— 末个驼峰/下划线段（`gridW`→`W`、`gridUser`→`User`）。"""
    p = parent_itemid
    if "_" in p:
        tail = [x for x in p.split("_") if x]
        return tail[-1] if tail else p
    parts = _CAMEL_RE.findall(p)
    if len(parts) >= 2:
        return parts[-1]
    return p


def suggest_normalname(own, cfg, anc, taken) -> tuple:
    """给一个**缺 normalName** 的节点提建议值。返回 `(建议值, 依据)`。

    沿用项目实测惯例：**原名 + 父级 itemId 的区分段**（`tbar` 在 `gridW`/`grid2`/`gridUser` 下
    分别是 `tbarW` / `tbar2` / `tbarUser`）。
    """
    for _t, pi in reversed(anc):
        if not (isinstance(pi, str) and pi and pi != own):
            continue
        d = _distinguisher(pi)
        # 区分段 == 父级全名（说明没切出片段）→ 用下划线；原名是 DB 字段风格也统一用下划线
        sep = "" if (d != pi and own.upper() != own) else "_"
        for cand in ("%s%s%s" % (own, sep, d), "%s_%s" % (own, pi)):
            if cand != own and cand not in taken:
                return cand, "沿用项目惯例：原名 + 父级 '%s' 的区分段" % pi
    for k in ("dataIndex", "name", "text", "fieldLabel"):
        v = cfg.get(k)
        if isinstance(v, str) and v and _IID_JS_IDENT_RE.match(v):
            for cand in (own + v, "%s_%s" % (own, v)):
                if cand not in taken:
                    return cand, "后缀取自 %s=%r" % (k, v)
    n = 2
    while "%s%d" % (own, n) in taken:
        n += 1
    return "%s%d" % (own, n), "无更好线索，退化为序号"


def _iter_controls(obj, path=None, anc=None, container=None, key=None):
    """深度遍历控件节点，产出 `(node, type, configs, path, ancestors, container, key)`。

    `ancestors` 是由外到内的 `[(type, itemId), ...]`（不含自身）——
    这是重名时判断"哪个同名控件才是目标"的关键依据。
    `container` / `key` 是父容器与键（键可能是数组下标），供原地改写。
    """
    if path is None:
        path = []
    if anc is None:
        anc = []
    if isinstance(obj, dict):
        t = obj.get("type")
        if isinstance(t, str):
            cfg = obj.get("configs") if isinstance(obj.get("configs"), dict) else {}
            yield obj, t, cfg, list(path), list(anc), container, key
            anc = anc + [(t, cfg.get("itemId"))]
        for k, v in obj.items():
            # 不深入 `configs` —— 控件只挂在 `children` 下；`configs` 里偶尔会有带 `type` 键的
            # 内联配置对象（实测全项目 128 个），进来就成了"幻影控件"，`@itemId` 可能误指到它。
            if k == "configs":
                continue
            yield from _iter_controls(v, path + [k], anc, obj, k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_controls(v, path + [i], anc, obj, i)


def _find_all_by_itemid(o, name, parent=None, key=None, acc=None):
    """收集子树里所有 `configs.itemId == name` 的节点位置 `(容器, 键)`。"""
    if acc is None:
        acc = []
    for _n, _t, cfg, _p, _a, cont, k in _iter_controls(o):
        if cfg.get("itemId") == name:
            acc.append((cont, k))
    return acc


def itemid_hits(o, name):
    """所有 `configs.itemId == name` 的节点详情（重名时用来列候选）。"""
    return [h for h in _iter_controls(o) if h[2].get("itemId") == name]


def js_refs_of(obj, filtered: bool = True) -> set:
    """文件内**事件 JS** 里引用到的控件名（`app.X` 与 `app.get('X')`）。

    - 先 `strip_js_comments` 剔注释 —— 注释里的 `app.X` 不是引用（否则会误报）。
    - `filtered=True`（默认）：再滤掉 `_APP_REF_RESERVED` 里的方法名/框架成员。
      判定"某个 itemId 是否被引用"时**应传 `filtered=False`** —— 那个名字既已确认是文件内的
      `itemId`，保留表那层"可能只是方法"的歧义就不存在了（`store` / `add` / `items` / `id`
      都是真实存在的 itemId，滤掉会漏判）。
    """
    blob = "\n".join(code for _n, code in collect_events(obj))
    if not blob:
        return set()
    clean = strip_js_comments(blob)
    names = set(_APP_REF_BARE.findall(clean)) | set(_APP_REF_GET.findall(clean))
    if not filtered:
        return names
    return {x for x in names if x not in _APP_REF_RESERVED}


def _anc_str(anc) -> str:
    """祖先链 → `panel1 › form1`；没有带 itemId 的祖先时给「顶层」。"""
    named = ["%s[%s]" % (t, i) for t, i in anc if isinstance(i, str) and i]
    return " › ".join(named) if named else "顶层（无带 itemId 的祖先）"


_HINT_KEYS = ("dataIndex", "text", "header", "fieldLabel", "name", "boxLabel",
              "tooltip", "displayField", "value", "url")


def _node_hint(cfg) -> str:
    """挑几个能区分同名节点的短字段，拼成一行提示。"""
    bits = []
    for k in _HINT_KEYS:
        v = cfg.get(k)
        if isinstance(v, str) and v:
            bits.append("%s=%r" % (k, v[:36]))
        if len(bits) >= 3:
            break
    return "  ".join(bits) if bits else "（无可辨识的文本字段）"


def _children_summary(node) -> str:
    """子节点类型摘要（如 `3×column, 1×toolbar`）—— "其下有什么控件"这一线索。"""
    ch = node.get("children") if isinstance(node, dict) else None
    if not isinstance(ch, list):
        return ""
    cnt: dict = {}
    for c in ch:
        k = c.get("type") if isinstance(c, dict) else None
        if isinstance(k, str):
            cnt[k] = cnt.get(k, 0) + 1
    if not cnt:
        return ""
    return ", ".join("%d×%s" % (v, k) for k, v in sorted(cnt.items(), key=lambda x: (-x[1], x[0])))


def suggest_itemid(own, cfg, anc, taken) -> tuple:
    """给一个重名节点提**建议 itemId**（只建议，不自动改）。返回 `(建议值, 依据)`。

    优先级：父级 itemId 前缀（项目里 `panelCustomRecord_ID` 这类既有命名）
            → 自身可辨识字段 → 序号兜底。
    """
    for _t, pi in reversed(anc):
        if isinstance(pi, str) and pi and pi != own:
            cand = "%s_%s" % (pi, own)
            if cand not in taken:
                return cand, "父级 itemId '%s' 作前缀（项目已有此类命名）" % pi
    for k in ("dataIndex", "name", "text", "fieldLabel"):
        v = cfg.get(k)
        if isinstance(v, str) and v and _IID_JS_IDENT_RE.match(v):
            cand = "%s_%s" % (own, v)
            if cand not in taken:
                return cand, "后缀取自 %s=%r" % (k, v)
    n = 2
    while "%s_%d" % (own, n) in taken:
        n += 1
    return "%s_%d" % (own, n), "无更好线索，退化为序号"


class ItemIdError(KeyError):
    """itemId 定位失败（找不到 / 重名需点名）。

    继承 `KeyError` 以兼容旧调用方的 `except KeyError`；
    `str()` 返回可读原文，不带 `KeyError` 那层引号与 `\\n` 转义。
    """

    def __str__(self) -> str:
        return self.args[0] if self.args else ""


def format_itemid_candidates(name, hits, scope_desc="当前范围", all_names=None) -> str:
    """重名时输出「候选清单 + 建议值」——把选择权交回给用户，工具不猜顺序。"""
    taken = set(all_names or ())
    taken |= {h[2].get("itemId") for h in hits if isinstance(h[2].get("itemId"), str)}
    lines = [
        "configs.itemId == %r 在%s有 %d 个节点 —— `@%s` 不猜顺序。三种出路：" % (
            name, scope_desc, len(hits), name),
        "  ① 点名第 N 个：`@%s#N`（N 从 1 起）" % name,
        "  ② 点明父级作用域：路径里串联 `@` 段，如 [\"@panel1\", \"@%s\"]（后一段只在上一段子树里找）" % name,
        "  ③ 只改真正要改的那个 —— 由下面的父子关系判断",
        "",
        "候选清单：",
    ]
    sug = []
    for i, (node, t, cfg, path, anc, _c, _k) in enumerate(hits, 1):
        loc = "[" + ", ".join(json.dumps(x) if isinstance(x, str) else str(x) for x in path) + "]"
        lines.append("  #%d  %-12s 祖先: %s" % (i, t, _anc_str(anc)))
        lines.append("      位置: %s" % loc)
        lines.append("      特征: %s" % (_node_hint(cfg) or "（无）"))
        ch = _children_summary(node)
        lines.append("      其下: %s" % (ch or "（无子控件）"))
        if i > 1:
            s, why = suggest_itemid(name, cfg, anc, taken)
            sug.append((i, t, s, why))
            taken.add(s)
    if sug:
        lines.append("")
        lines.append("建议改名（**确认后再改**；改名前先确认该名字没有被 JS 引用）——只动 #2 起，#1 保持原名"
                     "（旧代码里 `app.%s` 若已存在，改 #1 才有风险）：" % name)
        for i, t, s, why in sug:
            lines.append("  #%d %-12s → %-28r 依据: %s" % (i, t, s, why))
        lines.append("")
        lines.append("  若采纳，可写成 ops（改完请跑 `xwl.py itemids` 复核，并同步改 JS 里的引用）：")
        for i, t, s, _w in sug[:3]:
            p = hits[i - 1][3] + ["configs", "itemId"]
            lines.append('    {"op":"set","path":%s,"value":%r}' % (
                "[" + ", ".join(json.dumps(x) if isinstance(x, str) else str(x) for x in p) + "]", s))
    lines.append("")
    lines.append("全量重名报告（含分级与建议）：python scripts/xwl.py itemids <file> --dups-only")
    return "\n".join(lines)


def _pick_itemid(cur, name, scope_desc="当前范围"):
    """按 itemId 定位唯一节点。

    支持 `名字#N`（N 从 1 起）在重名时点名第 N 个。
    重名且未给序号时**不猜** —— 抛出带「候选清单 + 建议值」的错误，由用户挑。
    """
    idx = None
    m = _IID_INDEX_RE.match(name)
    if m:
        name, idx = m.group("name"), int(m.group("idx"))
    hits = itemid_hits(cur, name)
    if not hits:
        raise ItemIdError("找不到 configs.itemId == %r 的节点" % name)
    if idx is not None:
        if not 1 <= idx <= len(hits):
            raise ItemIdError("itemId %r 在%s只有 %d 个节点，`#%d` 越界（序号从 1 起）"
                              % (name, scope_desc, len(hits), idx))
        return hits[idx - 1][5], hits[idx - 1][6]
    if len(hits) > 1:
        raise ItemIdError(format_itemid_candidates(
            name, hits, scope_desc,
            all_names={h[2].get("itemId") for h in _iter_controls(cur)
                       if isinstance(h[2].get("itemId"), str)}))
    return hits[0][5], hits[0][6]


def _step(cur, seg):
    """走一段路径；`@itemId` / `@itemId#N` 段在当前范围内按 itemId 定位。"""
    if isinstance(seg, str) and seg.startswith("@"):
        loc = _pick_itemid(cur, seg[1:])
        return loc[0][loc[1]]
    return cur[seg]


def resolve_path(obj, path):
    """按路径取值。支持 `@itemId` 段 —— 不必知道嵌套层级。"""
    cur = obj
    for seg in path:
        cur = _step(cur, seg)
    return cur


def resolve_parent(obj, path):
    """返回 (容器, 键)；键可能是下标。末段是 `@itemId` 时返回该节点所在的容器与键。"""
    cur = obj
    for seg in path[:-1]:
        cur = _step(cur, seg)
    last = path[-1]
    if isinstance(last, str) and last.startswith("@"):
        return _pick_itemid(cur, last[1:])
    return cur, last


def apply_ops(obj, ops):
    """按 ops 就地修改对象。

    path 是「键 / 数组下标」列表；**以 `@` 开头的段按 `configs.itemId` 寻址**
    （例：`["@dataprovider1", "configs", "sql"]`），所以不用关心嵌套层级。

    op 形态：
      {"op":"set",    "path":[...], "value":...}
      {"op":"insert", "path":[...], "index":n, "value":...}   缺省 index = 末尾
      {"op":"append", "path":[...], "value":...}
      {"op":"delete", "path":[...], "index":n}                给 index 删数组元素；否则删键
    """
    for i, op in enumerate(ops, 1):
        if not isinstance(op, dict):
            raise ValueError("第 %d 个 op 不是对象" % i)
        kind = op.get("op")
        path = op.get("path") or []
        if not path:
            raise ValueError("第 %d 个 op 的 path 为空" % i)
        if kind == "set":
            parent, key = resolve_parent(obj, path)
            parent[key] = op["value"]
        elif kind in ("insert", "append"):
            arr = resolve_path(obj, path)
            if not isinstance(arr, list):
                raise ValueError("第 %d 个 op：path 指向的不是数组" % i)
            if kind == "append":
                arr.append(op["value"])
            else:
                idx = int(op.get("index", len(arr)))
                arr.insert(idx, op["value"])
        elif kind == "delete":
            if "index" in op:
                arr = resolve_path(obj, path)
                if not isinstance(arr, list):
                    raise ValueError("第 %d 个 op：path 指向的不是数组" % i)
                del arr[int(op["index"])]
            else:
                parent, key = resolve_parent(obj, path)
                del parent[key]
        else:
            raise ValueError("第 %d 个 op 类型未知: %r" % (i, kind))
    return obj


def audit_itemids(obj, js_refs=None, controls_path=None) -> dict:
    """给文件里每个重名 itemId 定级，并给出「候选清单 + 两种修法的建议值」。

    判据（顺序即优先级）：
      ① 每个同名节点都有**互不相同的非空 normalName** → 无害。框架按
         `normalName || itemId` 注册到页面作用域，各自名字不同就不冲突。
      ② 全是列控件（column / tcolumn）且未被引用 → 无害。
      ③ itemId 不是合法 JS 标识符 → 无害（只能用 `app.get('名')` 取）。
      ④ 其余：**已被事件 JS 引用 → error；未被引用 → warn**。

    返回 dict：nodes / js_refs / groups / errors / warns / n_benign
    """
    if js_refs is None:
        js_refs = js_refs_of(obj)
    # 判定"是否被引用"用**未过滤**集合：名字既已确认是文件内的 itemId，
    # 就不该再被 `_APP_REF_RESERVED`（为区分方法名而设）滤掉 —— 否则 `store`/`add`/`items`/`id` 会漏判。
    refs_all = js_refs_of(obj, filtered=False)
    nodes = [(n, t, cfg, p, anc) for n, t, cfg, p, anc, _c, _k in _iter_controls(obj)
             if isinstance(cfg.get("itemId"), str) and cfg.get("itemId")]
    all_names = {x[2]["itemId"] for x in nodes}
    field_ty = set(field_types(controls_path))
    nn_ty = set(normalname_types(controls_path))
    by_name: dict = {}
    for it in nodes:
        by_name.setdefault(it[2]["itemId"], []).append(it)

    groups = []
    for name, items in sorted(by_name.items()):
        if len(items) < 2:
            continue
        types = {x[1] for x in items}
        referenced = name in refs_all
        nns = [x[2].get("normalName") for x in items]
        have_nn = [isinstance(x, str) and x for x in nns]
        ok_nn = all(have_nn) and len(set(nns)) == len(nns)

        if ok_nn:
            level = "benign"
            reason = ("每个同名节点都有**互不相同的 normalName** —— 框架按 `normalName || itemId` "
                      "注册，各自名字不同即不冲突，JS 走 `app.<normalName>`")
            short = "已有唯一 normalName，注册键不冲突"
        elif types <= _IID_COL_TYPES and not referenced:
            level = "benign"
            reason = ("列控件重名：取数走 `<grid>.getSelection(0).data.*`，"
                      "实测全项目 3393 组此类重名、**0 组**被事件 JS 引用")
            short = "列控件重名（取数不直接引用列控件）"
        elif types <= _IID_COL_TYPES:
            level = "warn"
            reason = ("列控件重名，且该名字出现在事件 JS 里 —— 列一般用 `<grid>.getSelection(0).data.*` "
                      "取数；若确实直接引用了列控件，需点名")
            short = "列控件重名但被 JS 引用 —— 需点名"
        elif not _IID_JS_IDENT_RE.match(name):
            level = "benign"
            reason = "itemId 不是合法 JS 标识符（含中文/空格/点等），只能 `app.get('名')` 取"
            short = "itemId 非 JS 标识符，dot 访问不适用"
        else:
            # 措辞按组成分三类：纯取值控件 / 含列控件的跨类型冲突 / 其它（按钮·面板·承载）
            if types <= field_ty:
                miss = [i + 1 for i, x in enumerate(have_nn) if not x]
                head = "字段控件重名、normalName %s" % (
                    ("缺失的序号 %s" % miss) if miss else "彼此重复")
            elif types & _IID_COL_TYPES:
                head = ("**跨类型同名冲突**（组内含列控件：%s）—— 列本身可重名，"
                        "但它与另一种控件撞了同一个名字" % "/".join(sorted(types)))
            else:
                head = "应唯一的类型（按钮/面板/数据承载…）重名"
            if referenced:
                level = "error"
                reason = (head + "，且该名字**已被事件 JS 引用**。框架注册键是 `normalName || itemId`、"
                          "是**普通赋值**（后注册的覆盖先注册的），且**任一重复项销毁时会把整个名字删掉**"
                          "（`unregister` 里 `delete`），所以 `app.%s` 随时可能不是你要的那个" % name)
                short = "重名且被事件 JS 引用 —— `app.%s` 取值不确定" % name
            else:
                level = "warn"
                reason = head + "，但未被事件 JS 引用 —— 老代码可暂留，**新代码必须区分**"
                short = "重名但未被 JS 引用 —— 老代码可留，新代码须区分"

        # 修法 A：补 normalName（只补「缺」的，不动 itemId —— 零破坏）
        fix_nn = []
        if not ok_nn:
            taken_nn = set(all_names) | {x for x in nns if isinstance(x, str) and x}
            for i, (n, t, cfg, p, anc) in enumerate(items):
                if isinstance(cfg.get("normalName"), str) and cfg.get("normalName"):
                    continue
                s, why = suggest_normalname(name, cfg, anc, taken_nn)
                taken_nn.add(s)
                fix_nn.append({"index": i + 1, "type": t, "suggest": s, "why": why,
                               "type_ok": t in nn_ty,
                               "path": p + ["configs", "normalName"]})
        # 修法 B：改 itemId（#1 保持原名，动 #2 起；须同步改 JS 里的引用）
        taken = set(all_names)
        fix_id = []
        for i, (n, t, cfg, p, anc) in enumerate(items):
            if i == 0:
                continue
            s, why = suggest_itemid(name, cfg, anc, taken)
            taken.add(s)
            fix_id.append({"index": i + 1, "type": t, "suggest": s, "why": why,
                           "type_ok": True, "path": p + ["configs", "itemId"]})

        groups.append({
            "name": name, "level": level, "reason": reason, "short": short, "count": len(items),
            "types": sorted(types), "referenced": referenced,
            "fix_normalname": fix_nn, "fix_itemid": fix_id,
            "nodes": [{"index": i + 1, "type": t, "path": p, "anc": anc,
                       "ancestor": _anc_str(anc), "hint": _node_hint(cfg),
                       "children": _children_summary(n), "normalName": cfg.get("normalName")}
                      for i, (n, t, cfg, p, anc) in enumerate(items)],
        })

    order = {"error": 0, "warn": 1, "benign": 2}
    groups.sort(key=lambda g: (order[g["level"]], -g["count"], g["name"]))
    fmt = lambda g: "itemId %r ×%d（%s）：%s" % (g["name"], g["count"], "/".join(g["types"]), g["short"])
    return {
        "nodes": nodes, "js_refs": sorted(js_refs), "groups": groups,
        "errors": [fmt(g) for g in groups if g["level"] == "error"],
        "warns": [fmt(g) for g in groups if g["level"] == "warn"],
        "n_benign": sum(1 for g in groups if g["level"] == "benign"),
        "nn_ty": sorted(nn_ty),
    }


def recommend_fixes(rep, mode="auto", skipped=None) -> list:
    """把「建议改名」整理成可 `patch` 的 ops 草稿（**需人工确认**）。

    `mode`：`auto` = 能补 `normalName` 就补（不动 `itemId`，零破坏），否则改 `itemId`；
            `normalName` = 只补 `normalName`；`itemId` = 只改 `itemId`。

    **类型不接受 `normalName` 的项永不写入** —— 那些类型（`array` / `dataprovider` / `query` 等 44 个）
    的 `configs` 里没有这个键，写了就是非法配置。`skipped` 给定时，被跳过的项会追加进去供调用方提示。
    """
    ops: list = []
    for g in rep["groups"]:
        if g["level"] not in ("error", "warn"):
            continue
        nn_ok = [s for s in g.get("fix_normalname", []) if s["type_ok"]]
        nn_bad = [s for s in g.get("fix_normalname", []) if not s["type_ok"]]
        if mode == "normalName":
            if skipped is not None:
                skipped.extend(dict(s, group=g["name"]) for s in nn_bad)
            src = nn_ok
        elif mode == "auto" and nn_ok and not nn_bad:
            src = nn_ok
        else:
            src = g.get("fix_itemid", [])
        for s in src:
            ops.append({"op": "set", "path": s["path"], "value": s["suggest"]})
    return ops


_LEVEL_TAG = {
    "error": "[error] 重名 + 已被 JS 引用 —— 需处理",
    "warn": "[warn]  重名，未被 JS 引用 —— 老代码可留，新代码必须区分",
    "benign": "[ok]    重名在实践中无害",
}


def _print_group(g, lv, show_nodes=True):
    print(f"\n[{lv}] {g['name']!r} ×{g['count']}（{'/'.join(g['types'])}）")
    print(f"    {g['reason']}")
    if show_nodes:
        for nd in g["nodes"]:
            loc = "[" + ", ".join(json.dumps(x) if isinstance(x, str) else str(x)
                                  for x in nd["path"]) + "]"
            nn = nd["normalName"]
            print(f"      #{nd['index']} {nd['type']:<12} 祖先: {nd['ancestor']}")
            print(f"           位置: {loc}")
            print(f"           特征: {nd['hint']}   normalName={nn!r}")
            if nd["children"]:
                print(f"           其下: {nd['children']}")
    if g["fix_normalname"]:
        usable = all(s["type_ok"] for s in g["fix_normalname"])
        head = ("修法 A（推荐）：补 `normalName`，**不动 itemId**，零破坏 —— JS 改用 `app.<normalName>`"
                if usable else
                "修法 A（**本组不可用**：该类型不在注册表的 normalName 白名单里）：补 `normalName`")
        print("    " + head)
        for s in g["fix_normalname"]:
            flag = "" if s["type_ok"] else "  ⚠ 该类型不在注册表的 normalName 白名单里，请先确认"
            print(f"      #{s['index']} {s['type']:<12} normalName → {s['suggest']!r}   依据: {s['why']}{flag}")
    if g["fix_itemid"]:
        print("    修法 B：改 `itemId`（#1 保持原名）—— 须**同步改事件 JS 里对它们的引用**")
        for s in g["fix_itemid"]:
            print(f"      #{s['index']} {s['type']:<12} itemId → {s['suggest']!r}   依据: {s['why']}")


def cmd_itemids(args) -> int:
    """itemId 全量报告：命名规范、重名分级、候选清单与**建议值**。

    **只读** —— 不修改文件。要改，由用户确认后走 `patch`。
    """
    try:
        text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2

    ctl = getattr(args, "controls", None) or discover_controls(args.file)
    rep = audit_itemids(obj, controls_path=ctl)
    groups = rep["groups"]
    counts = {lv: sum(1 for g in groups if g["level"] == lv) for lv in ("error", "warn", "benign")}
    names = {x[2]["itemId"] for x in rep["nodes"]}

    if args.name:
        hits = itemid_hits(obj, args.name)
        if not hits:
            if args.json:   # 机器可读路径也要给 JSON，别混纯文本
                print(json.dumps({"error": "not_found", "name": args.name,
                                  "message": "找不到 configs.itemId == %r" % args.name},
                                 ensure_ascii=False, indent=2))
            else:
                print(f"[FAIL] 找不到 configs.itemId == {args.name!r}")
            return 1
        if args.json:
            print(json.dumps(
                [{"index": i + 1, "type": t, "path": p, "ancestor": _anc_str(anc),
                  "hint": _node_hint(cfg), "children": _children_summary(n),
                  "normalName": cfg.get("normalName")}
                 for i, (n, t, cfg, p, anc, _c, _k) in enumerate(hits)],
                ensure_ascii=False, indent=2))
        else:
            print(format_itemid_candidates(args.name, hits, "文件全域", all_names=names))
        return 0

    if args.suggest:
        skipped: list = []
        ops = recommend_fixes(rep, args.fix, skipped=skipped)
        for s in skipped:
            print("[warn] 跳过 %r 的 #%d %s —— 该类型不接受 `normalName`"
                  "（改用 `--fix itemId` 可改 itemId）" % (s["group"], s["index"], s["type"]),
                  file=sys.stderr)
        if not ops:
            print("[]")
            print("（无需改名：没有 error/warn 组，或选定的修法对本文件不适用）")
            return 0
        print(json.dumps(ops, ensure_ascii=False, indent=2))
        return 0

    if args.json:
        print(json.dumps({k: v for k, v in rep.items() if k != "nodes"},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"=== itemids: {os.path.basename(args.file)} ===")
    print(f"含 itemId 的控件 {len(rep['nodes'])} 个 / 去重名字 {len(names)} 个；"
          f"重名组 {len(groups)} 组 —— error {counts['error']} / warn {counts['warn']} / benign {counts['benign']}")
    print(f"事件 JS 引用的名字 {len(rep['js_refs'])} 个 | "
          f"控件注册表: {ctl or '（未找到，normalName 白名单用内置清单）'}")

    cols = [(n, cfg) for n, t, cfg, *_ in rep["nodes"] if t in _IID_COL_TYPES]
    if cols:
        ok = sum(1 for _n, c in cols if re.search(r"(_?[Cc][Oo][Ll])$", str(c.get("itemId") or "")))
        print(f"\n--- 命名规范 ---\n  列控件 itemId {len(cols)} 个，带 `_COL`/`Col` 后缀 {ok} 个"
              f"（约定：字段名 + Col，多 grid 时靠父级 itemId 区分）")

    if not groups:
        print("\n（无重名 itemId）")
        return 0

    for lv in ("error", "warn", "benign"):
        if lv == "benign" and args.dups_only:
            continue
        gs = [g for g in groups if g["level"] == lv]
        if not gs:
            continue
        print(f"\n=== {_LEVEL_TAG[lv]}（{len(gs)} 组）===")
        limit = 5 if lv == "benign" else None
        for g in (gs if limit is None else gs[:limit]):
            _print_group(g, lv, show_nodes=(lv != "benign"))
        if limit is not None and len(gs) > limit:
            print(f"\n…（benign 组共 {len(gs)} 组，仅示 {limit} 组；全量用 --json）")

    if counts["error"] or counts["warn"]:
        print("\n--- 下一步 ---")
        print(f"  · 生成改名 ops 草稿：`xwl.py itemids <file> --suggest`"
              f"（默认修法 auto = 能补 normalName 就补，否则改 itemId；可用 --fix 指定）")
        print("  · 草稿**必须人工确认**：尤其修法 B 改 itemId 时，要同步改事件 JS 里的引用。")
        print("  · 只改真正要改的那个：用 `--name <itemId>` 看候选清单，或 ops 里写 `\"@名字#2\"` 点名第 2 个。")
    return 0


def cmd_patch(args) -> int:
    """结构级编辑：解析 → 改对象 → 用设计器算法整份重建 → 校验。

    这是「遵循设计器规则、不犯格式错」的正路：
    你不用碰续行符 / 转义 / 空白，全部由序列化器按 IDE.updateModule 的规则产生。
    """
    try:
        text, has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2
    if has_bom:
        print("[FAIL] 文件带 BOM；本工具不处理")
        return 2

    eol = (CRLF if text.count(CRLF) else "\n") if args.eol == "auto" else ("\n" if args.eol == "lf" else CRLF)

    canonical = text == dumps_designer(obj, args.indent, eol)
    print(f"源文件: {len(text.encode('utf-8'))} B | 换行={'CRLF' if eol == CRLF else 'LF'} | "
          f"是否设计器原样排版: {'是（重排后与原文逐字节一致，diff 只含本次改动）' if canonical else '否（重排会顺带规整格式）'}")

    try:
        with open(args.ops, "r", encoding="utf-8") as f:
            ops = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 读 ops 失败: {exc}")
        return 2
    if isinstance(ops, dict):
        ops = [ops]

    try:
        apply_ops(obj, ops)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "\n" in msg:  # 重名报错带候选清单，原样打印
            print("[FAIL] 应用 ops 失败:")
            print(msg)
        else:
            print(f"[FAIL] 应用 ops 失败: {msg}")
        return 2
    print(f"[ok]   已应用 {len(ops)} 个 op")

    out = dumps_designer(obj, args.indent, eol)
    try:
        if parse_xwl(out) != obj:
            print("[FAIL] 重建结果语义不一致，已中止（不写文件）")
            return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 重建结果无法解析，已中止: {exc}")
        return 2
    print(f"[ok]   语义等价比对通过 | 变更后 {len(out.encode('utf-8'))} B "
          f"({len(out.encode('utf-8')) - len(text.encode('utf-8')):+d})")

    if args.dry_run:
        import difflib
        a = text.splitlines()
        b = out.splitlines()
        shown = 0
        for line in difflib.unified_diff(a, b, "before", "after", lineterm="", n=1):
            if line.startswith(("---", "+++", "@@")):
                continue
            print("  " + line[:200])
            shown += 1
            if shown >= 40:
                print("  ...（略）")
                break
        print("[dry-run] 未写入")
        return 0

    if args.backup:
        bak = args.file + ".bak"
        with open(bak, "wb") as f:
            f.write(read_bytes(args.file))
        print(f"备份 -> {bak}")
    write_text(args.file, out)
    print(f"已写入: {args.file}")

    return _post_check(args.file, args)


# --------------------------------------------------------------------------- #
# schema（查设计器控件注册表）
# --------------------------------------------------------------------------- #
def cmd_schema(args) -> int:
    """从设计器的控件注册表（wb/system/controls.json）查某控件的合法 configs / events。

    这是「新建节点该写哪些字段」的**权威来源** —— 不用猜、也不用从 IDE 反编译。
    """
    try:
        reg = json.load(open(args.controls, "r", encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 读注册表失败: {exc}")
        return 2

    nodes: dict[str, dict] = {}

    def walk(o):
        if isinstance(o, dict):
            i = o.get("id")
            if isinstance(i, str) and i not in nodes:
                nodes[i] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(reg)

    if getattr(args, "tree", False):
        def brief(n):
            g = n.get("general") or {}
            lb = (g.get("tag") or {}).get("lib")
            parts = [(" [容器]" if g.get("container") else ""),
                     " [%s]" % {1: "桌面", 2: "移动", 3: "原生"}.get(lb, "结构/服务端")]
            if g.get("design", True) is False:
                parts.append(" [内部·面板里没有]")
            return "".join(parts)
        print("设计器左侧控件面板的分组结构（括号内为库 / 是否容器）：\n")
        for child in (reg.get("children") or []):
            if child.get("children"):
                print(f"{child.get('text') or child.get('id')}")
                for c in [x for x in child["children"] if not x.get("children")]:
                    print(f"  {c['id']:<18}{brief(c)}")
                for sub in [x for x in child["children"] if x.get("children")]:
                    print(f"  {sub.get('text') or sub.get('id')}:")
                    for c in sub["children"]:
                        print(f"    {c['id']:<18}{brief(c)}")
            else:
                print(f"(根) {child['id']}{brief(child)}")
        print("\n> 每个控件「干什么 / 该挂在哪里 / 哪种情况用哪个」见 "
              "skill 的 references/controls.md。")
        return 0

    if args.list:
        for k in sorted(k for k, v in nodes.items() if "general" in v):
            print(k)
        return 0

    node = nodes.get(args.type)
    if node is None:
        print(f"[FAIL] 注册表里没有 id={args.type!r}（用 `--list` 看全部）")
        return 2

    general = node.get("general") or {}
    lib = (general.get("tag") or {}).get("lib")
    libname = {1: "桌面 ExtJS", 2: "移动 Touch(t*)", 3: "原生 HTML"}.get(lib, "结构/服务端")
    print(f"type = {args.type}   [{libname}]")
    print(f"  xtype={general.get('xtype')!r}  ExtJS 类={general.get('type')!r}  "
          f"容器={bool(general.get('container'))}  "
          f"出现在面板={general.get('design', True) is not False}")
    if general.get("autoNames"):
        print(f"  自动 itemId（按父控件 type）: {json.dumps(general['autoNames'], ensure_ascii=False)}"
              "  ← 挂到哪个父控件下、自动叫什么名字")

    cfg = node.get("configs") or {}
    print(f"\n合法 configs（{len(cfg)} 个）：")
    for k, v in cfg.items():
        if isinstance(v, dict):
            t = v.get("type") or ""
            lst = v.get("list")
            extra = f"  取值={lst}" if lst else ""
            grp = f"  group={v['group']}" if v.get("group") else ""
            print(f"  {k:<20} [{t}]{grp}{extra}")
        else:
            print(f"  {k}")

    ev = node.get("events") or {}
    shown = {k: v for k, v in ev.items() if not (isinstance(v, dict) and v.get("hidden"))}
    print(f"\n合法 events（{len(shown)} 个，已隐藏 hidden 项）：")
    for k, v in shown.items():
        rn = v.get("rename") if isinstance(v, dict) else None
        print(f"  {k}" + (f"  (实际名 {rn})" if rn else ""))

    if args.skeleton:
        # 骨架必须**只含该控件允许的键** —— 否则照抄进 xwl 就是非法配置。
        # 所以 configs 从注册表声明推导（不是写死 text），events 键按「该控件是否真有事件」决定。
        sk = collections.OrderedDict()
        cfgs = collections.OrderedDict()
        cfgs["itemId"] = "<必填：app.<itemId> 用它寻址>"
        for cand in ("text", "title"):          # 只加该控件**确实允许**的「显示名」键
            if cand in cfg:
                cfgs[cand] = ""
        sk["configs"] = cfgs
        sk["expanded"] = False
        sk["children"] = []
        sk["type"] = args.type
        if "click" in shown:
            # 真实控件节点的键集合只有两种：无事件时**没有** events 键（见 SKILL 1.2）
            sk["events"] = {"click": ""}
        keys = ", ".join(sk.keys())
        print(f"\n设计器同款最小骨架（键序与设计器一致：{keys}）：")
        print(json.dumps(sk, ensure_ascii=False, indent=2))
        if not shown:
            print("\n> 该控件 events 为 0 个 —— 骨架里**不带** events 键（与真实文件形态一致）。")
        elif "click" not in shown:
            print(f"\n> 该控件没有 click 事件；可挂的是：{' / '.join(shown)} —— 需要时自己加 events 键。")
        print(f"> 提示：configs 只放上表列出的键（共 {len(cfg)} 个）；itemId 必须唯一。")
    return 0


def cmd_paths(args) -> int:
    """列出可编辑字段的位置：sql / totalSql / serverScript / url（给 patch 的 path 用）。"""
    try:
        text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2

    iid_count: dict = {}
    for _t, _cfg, _p in iter_nodes(obj):
        _i = _cfg.get("itemId")
        if isinstance(_i, str) and _i:
            iid_count[_i] = iid_count.get(_i, 0) + 1

    rows = []
    for t, cfg, path in iter_nodes(obj):
        iid = cfg.get("itemId")
        for k in ("sql", "totalSql", "serverScript", "url"):
            v = cfg.get(k)
            if not isinstance(v, str):
                continue
            # 注意必须带 "configs" 一层：iter_nodes 给出的 path 指向**节点本身**，
            # 而 sql / serverScript 是节点 `configs` 下的键。漏掉这一层时 patch 不会报错，
            # 而是把字段写到节点根上（静默语义损坏）。
            raw = "[" + ", ".join(json.dumps(x) if isinstance(x, str) else str(x)
                                  for x in path + ["configs", k]) + "]"
            if isinstance(iid, str) and iid:
                at = "[" + ", ".join(json.dumps(x) for x in ["@" + iid, "configs", k]) + "]"
            else:
                at = "（该节点无 itemId，只能用原路径）"
            dup = iid_count.get(iid, 0) if isinstance(iid, str) else 0
            rows.append((k, t, iid, raw, at, len(v), dup))

    if not rows:
        print("（没有 sql / totalSql / serverScript / url 字段）")
        return 1

    dup_any = False
    for k, t, iid, raw, at, ln, dup in rows:
        print(f"{k}  ({t}, itemId={iid!r}, {ln} 字符)")
        print(f"   原路径 : {raw}")
        if dup > 1:
            dup_any = True
            print(f"   ⚠ @写法 : 需点名 —— itemId {iid!r} 在全文件出现 {dup} 次，`@` 寻址不猜顺序")
            print(f"             · 若目标就是第 1 个：`@{iid}#1`（序号从 1 起）")
            print("             · 否则跑 `xwl.py itemids <file> --dups-only` 看候选清单（含建议改名）")
            print("             · 或路径里串联 `@` 段缩小范围：[\"@父级itemId\", \"@%s\"]" % iid)
        else:
            print(f"   推荐   : {at}")
    print("\n用法示例（ops.json）—— @写法不受嵌套层级变动影响：")
    print('  [{"op":"set","path":["@dataprovider1","configs","sql"],"value":"select 1 from dual"}]')
    print('  [{"op":"set","path":["@module","configs","serverScript"],"value":"var data = app.get();\\n..."}]')
    if dup_any:
        print("注意：上面标 ⚠ 的条目 itemId 不唯一 —— 用 `@名字#N` 点名第 N 个候选，")
        print("      或直接看 `xwl.py itemids <file>` 的候选清单与建议改名（工具不猜顺序）。")
    return 0


# --------------------------------------------------------------------------- #
# new（从零生成一个 xwl 文件）
# --------------------------------------------------------------------------- #
# 顶层页面钥匙的**真实键序** —— 实测样本工程 2780 个 xwl：2750 个是这个顺序，
# 且**独立页面与被引用的 SQL 载体完全一样**。
# 序列化按 dict 插入序输出 ⇒ 键序写错，产出即与设计器不一致（下次被设计器保存就产生额外 diff）。
_PAGE_KEYS = ("hidden", "children", "roles", "title", "iconCls", "inframe", "pageLink")
_PAGE_DEFAULTS = collections.OrderedDict([
    ("hidden", False), ("children", []), ("roles", {}), ("title", ""),
    ("iconCls", ""), ("inframe", False), ("pageLink", ""),
])

# SQL 载体的 serverScript 骨架：取参数用 app.get('名')（**serverScript 里禁止写 {#…#}**），
# 拼好的条件通过 request.setAttribute('sql', …) 交给 dataprovider 的 {#sql#}。
_SQL_SERVER_SCRIPT = "var sql = '';\nrequest.setAttribute('sql', sql);"
_SQL_BODY = "select * from WB_MISC\nwhere 1=1\n{#sql#}"


def _page_obj(title: str, roles: dict, children: list):
    """按设计器真实键序构造页面顶层对象。"""
    o = collections.OrderedDict()
    o["hidden"] = False
    o["children"] = children
    o["roles"] = roles
    o["title"] = title
    o["iconCls"] = ""
    o["inframe"] = False
    o["pageLink"] = ""
    return o


def _ctl(ntype: str, configs: dict, expanded: bool = False, children=None):
    """按设计器键序（configs, expanded, children, type）构造控件节点。"""
    n = collections.OrderedDict()
    n["configs"] = configs
    n["expanded"] = expanded
    n["children"] = [] if children is None else children
    n["type"] = ntype
    return n


def skeleton_page(title: str = "", roles: dict | None = None) -> dict:
    """独立页面骨架：顶层 7 把钥匙 + 一个空的 `module` 节点。"""
    return _page_obj(title, {"default": 1} if roles is None else roles,
                     [_ctl("module", {"itemId": "module"})])


def skeleton_sql(title: str = "", roles: dict | None = None) -> dict:
    """SQL 载体骨架：`module(serverScript)` → `dataprovider(sql)`。

    就是被页面用 `store.configs.url = 'm?xwl=…'` 引用的那种文件（惯用路径 `…/xxxSql/queryXxx`）。
    """
    dp = _ctl("dataprovider", collections.OrderedDict([
        ("itemId", "dataprovider"),
        ("sql", _SQL_BODY),
    ]))
    mod = _ctl("module", collections.OrderedDict([
        ("itemId", "module"),
        ("serverScript", _SQL_SERVER_SCRIPT),
    ]), expanded=True, children=[dp])
    return _page_obj(title, {"default": 1} if roles is None else roles, [mod])


def _parse_roles(spec) -> dict:
    """`"default"` → `{"default": 1}`；`""` → `{}`；支持逗号分隔多个角色。"""
    return {n: 1 for n in (x.strip() for x in (spec or "").split(",")) if n}


def _reorder_page_keys(obj: dict):
    """把顶层键按设计器真实键序重排；缺失的页面钥匙按默认值补齐。

    返回 `(new_obj, added_keys, extra_keys)`。
    缺 `inframe` / `pageLink` 这类键时，`check` 依然 ALL OK（格式合法），
    但**设计器/框架的行为会不一致** —— 所以这里显式补齐并回报。
    """
    out = collections.OrderedDict()
    added = []
    for k in _PAGE_KEYS:
        if k in obj:
            out[k] = obj[k]
        else:
            out[k] = _PAGE_DEFAULTS[k]
            added.append(k)
    extra = [k for k in obj if k not in _PAGE_KEYS]     # 非标准顶层键（如 url）原样保留
    for k in extra:
        out[k] = obj[k]
    return out, added, extra


def cmd_new(args) -> int:
    """**从零生成**一个 xwl 文件 —— 不依赖任何「种子文件」。

    为什么要这个子命令：`patch` / `expand` / `check` 的第一步都是**读已有文件**，
    所以「新建」在工具层原本没有入口，只能靠「复制一个文件当种子、再整树重写」。
    而种子是**继承式**的：

      · 顶层没被显式覆盖的键会**静默残留**（种子的 `roles:{"demo":1}` 会带进新页面）；
      · 顶层缺 `inframe` / `pageLink` 的种子（工程里确实存在这类文件）产出的页面
        **缺钥匙而 `check` 不告警**。

    本命令把「设计器真实顶层键序 + 键序齐全」固化成内置骨架，从构造上消掉这两类问题。
    """
    dest = args.out
    if os.path.exists(dest) and not args.force:
        print(f"[FAIL] 目标已存在：{dest}")
        print("       要改已有文件请用 `xwl.py patch`（结构级编辑，diff 最小）；")
        print("       确实要整份覆盖再加 --force。")
        return 2

    added: list = []
    extra: list = []
    if args.from_json:
        try:
            with open(args.from_json, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] 读 --from-json 失败: {exc}")
            return 2
        if not isinstance(raw, dict):
            print("[FAIL] --from-json 的顶层必须是对象（xwl 顶层是一棵树，不是数组）")
            return 2
        obj, added, extra = _reorder_page_keys(raw)
        if not isinstance(obj.get("children"), list):
            print("[FAIL] children 必须是数组")
            return 2
        kind = f"from-json({os.path.basename(args.from_json)})"
    else:
        roles = None if args.roles is None else _parse_roles(args.roles)
        obj = (skeleton_sql(args.title, roles) if args.kind == "sql"
               else skeleton_page(args.title, roles))
        kind = args.kind

    eol = "\n" if args.eol == "lf" else CRLF
    eol_name = "LF" if eol == "\n" else "CRLF"
    out = dumps_designer(obj, args.indent, eol)

    # 语义等价比对（必须过，否则不写盘）
    try:
        if parse_xwl(out) != obj:
            print("[FAIL] 重建结果语义不一致，已中止（不写文件）")
            return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 重建结果无法解析，已中止: {exc}")
        return 2

    top = list(obj.keys())
    print(f"骨架: {kind} | 顶层 {len(top)} 键，键序 = {top}")
    if added:
        print(f"[note] 已按设计器默认值补齐缺失的页面钥匙：{added}")
        print("       缺这些键的文件 `check` 也是 ALL OK（只查格式），但设计器/框架行为会不一致。")
    if extra:
        print(f"[note] 保留了非标准顶层键（原样追加在末尾）：{extra}")
    print(f"[ok]   语义等价比对通过 | {len(out.encode('utf-8'))} B | 换行={eol_name}")

    if args.dry_run:
        print("\n--- 将写入的内容 ---")
        print(out)
        print("[dry-run] 未写入")
        return 0

    write_text(dest, out)
    print(f"已写入: {dest}")

    rc = _post_check(dest, args)
    if rc == 0:
        print("> 新建之后必做：")
        print(f"  1) 设计器导航树里看不到它 → 跑 `xwl.py folders {dest}` 看 folder.json 登记情况")
        print("  2) 若这是 SQL 载体 → 跑 `xwl.py sqlrefs`；若是引用它的页面 → 跑 `xwl.py params`")
        print("  3) 要被用户打开还需在数据库 WB_MENU 里挂菜单（在 xwl 工具范围外）")
    return rc


# --------------------------------------------------------------------------- #
# folders（folder.json：设计器导航树索引的一致性检查 / 登记）
# --------------------------------------------------------------------------- #
_FOLDER_NAME = "folder.json"


def _read_folder_json(d: str):
    """返回 `(data, path)`；`data=None` 表示文件不存在，`data=False` 表示存在但解析失败。"""
    p = os.path.join(d, _FOLDER_NAME)
    if not os.path.exists(p):
        return None, p
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data if isinstance(data, dict) else False), p
    except Exception:  # noqa: BLE001
        return False, p


def _register_one(target: str, args) -> int:
    """把文件名追加到所在目录 `folder.json` 的 `index` 末尾（保留原键序与单行形态）。"""
    d = os.path.dirname(target)
    name = os.path.basename(target)
    if not os.path.exists(target):
        print(f"[FAIL] 文件不存在：{target}")
        return 2
    data, jp = _read_folder_json(d)
    if data is None:
        print(f"[FAIL] {d} 下没有 {_FOLDER_NAME} —— 该目录未被设计器管理，")
        print("       请先在设计器里建这个目录（或确认路径是否写错）。")
        return 2
    if data is False:
        print(f"[FAIL] {jp} 不是合法 JSON，本工具不动它")
        return 2
    idx = data.get("index")
    if not isinstance(idx, list):
        print(f"[FAIL] {jp} 的 index 不是数组，本工具不动它")
        return 2
    if name in idx:
        print(f"[ok]   {name} 已登记在 {jp} 的 index 第 {idx.index(name) + 1} 项，无需改动")
        return 0

    text, has_bom = decode(jp)
    if has_bom:
        print(f"[FAIL] {jp} 带 BOM，本工具不动它（先手工去掉 BOM）")
        return 2
    eol = CRLF if text.count(CRLF) else ("\n" if "\n" in text else "")
    tail = eol if text.endswith(("\n", "\r")) else ""
    idx.append(name)
    out = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + tail

    print(f"将追加 index 项 {name!r} → {os.path.relpath(jp)}（登记后共 {len(idx)} 项）")
    if args.dry_run:
        print(f"  before: {text.rstrip()[:140]}")
        print(f"  after : {out.rstrip()[:140]}")
        print("[dry-run] 未写入")
        return 0

    bak = jp + ".bak"
    with open(bak, "wb") as f:
        f.write(read_bytes(jp))
    write_text(jp, out)
    print(f"备份 -> {bak}")
    print(f"已写入: {jp}")
    print("> index 的顺序 = 设计器导航树里的显示顺序（追加在末尾）。")
    return 0


def cmd_folders(args) -> int:
    """检查 `folder.json`（设计器导航树的目录索引）与实际文件是否一致。

    `folder.json` 形如 `{"hidden":false,"index":[…],"title":"…","iconCls":"…"}`；
    **`index` 里带 `.xwl` 后缀的是文件，不带后缀的才是子目录**。
    新建一个 xwl 之后不登记进所在目录的 `index`，设计器导航树里就看不到它。

    默认**只读**；只有 `--register` 才写（把该文件名追加到 index 末尾）。
    """
    target = os.path.abspath(args.path)
    if os.path.isfile(target):
        if not target.lower().endswith(".xwl"):
            print(f"[FAIL] 不是 .xwl 文件：{target}")
            return 2
        if args.register is not None:
            return _register_one(target, args)
        jobs = [(os.path.dirname(target), [os.path.basename(target)])]
        base = os.path.dirname(target)
        recursive = False
    elif os.path.isdir(target):
        jobs = []
        base = target
        recursive = True
        for d, _subs, files in os.walk(target):
            xs = [x for x in files if x.endswith(".xwl")]
            if xs:
                jobs.append((d, xs))
        if not jobs:
            print(f"[FAIL] {target} 下没有 .xwl 文件")
            return 2
    else:
        print(f"[FAIL] 路径不存在：{target}")
        return 2

    n_dir = n_unreg = n_dangling = n_bad = 0
    detail: list = []
    registered_at = None
    for d, names in sorted(jobs):
        n_dir += 1
        rel = os.path.relpath(d, base) if recursive else os.path.basename(d)
        data, jp = _read_folder_json(d)
        if data is None:
            n_unreg += len(names)
            detail.append(("缺 folder.json", rel, f"{len(names)} 个 xwl 未登记"))
            continue
        if data is False:
            n_bad += 1
            detail.append(("folder.json 损坏", rel, os.path.basename(jp)))
            continue
        idx = data.get("index") if isinstance(data.get("index"), list) else []
        miss = [x for x in names if x not in idx]
        if miss:
            n_unreg += len(miss)
            shown = ", ".join(miss[:6]) + ("…" if len(miss) > 6 else "")
            detail.append(("未登记", rel, shown))
        elif not recursive and names:
            registered_at = (names[0], jp, idx.index(names[0]) + 1)
        # 悬空：index 项在磁盘上既不是文件也不是子目录（文件/目录被删了但登记还留着）
        for it in idx:
            if isinstance(it, str) and it and not os.path.exists(os.path.join(d, it)):
                n_dangling += 1
                detail.append(("index 悬空", rel, it))

    print(f"目录 {n_dir} 个 | 未登记的 xwl {n_unreg} 个 | "
          f"index 悬空项 {n_dangling} 个 | folder.json 损坏 {n_bad} 个")
    if detail:
        print("\n明细（最多 40 条）：")
        for kind, rel, info in detail[:40]:
            print(f"  [{kind}] {rel}/  {info}")
        if len(detail) > 40:
            print(f"  ...（另有 {len(detail) - 40} 条）")
    elif registered_at:
        nm, jp, pos = registered_at
        print(f"[ok]   {nm} 已登记在 {os.path.relpath(jp)} 的 index 第 {pos} 项。")
    else:
        print("[ok]   index 与实际文件一致。")
    if n_unreg and not recursive:
        print(f"\n登记：xwl.py folders {os.path.relpath(target)} --register {os.path.basename(target)}")
    if n_unreg:
        print("\n> index 里带 `.xwl` 的是文件、不带后缀的是子目录；顺序 = 导航树显示顺序。")
    return 0


# --------------------------------------------------------------------------- #
# sqlrefs（SQL 文件：serverScript ↔ dataprovider 的引用检查）
# --------------------------------------------------------------------------- #
_HASH_RE = re.compile(r"\{#([^}]{1,64})#\}")
_PARAM_RE = re.compile(r"\{\?([^}]{1,64})\?\}")
_SETATTR_RE = re.compile(r"""setAttribute\(\s*(['"])(.*?)\1""")
_BUILTIN_PREFIX = ("sys.", "Str.")


def iter_nodes(obj):
    """产出 (type, configs, path) 三元组。"""
    def walk(o, path):
        if isinstance(o, dict):
            t = o.get("type")
            if isinstance(t, str):
                yield t, (o.get("configs") if isinstance(o.get("configs"), dict) else {}), path
            for k, v in o.items():
                yield from walk(v, path + [str(k)])
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, path + [i])

    yield from walk(obj, [])


def cmd_sqlrefs(args) -> int:
    """检查 SQL 文件里 serverScript 与 dataprovider 的引用是否自洽。

    - dataprovider.sql / totalSql 里的 `{#name#}` 必须由 **同一个 module 的 serverScript**
      用 `request.setAttribute("name", …)` 提供（`{#sys.*#}` / `{#Str.*#}` 是框架内置，不用提供）；
    - `{?name?}` 是绑定参数（由 Query 解析成 PreparedStatement 参数），只做清点；
    - **serverScript 里不允许出现 `{#…#}`**（ServerScript 会直接报错）。
    """
    try:
        text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2

    nodes = list(iter_nodes(obj))
    modules = [(c, p) for t, c, p in nodes if t == "module" and isinstance(c.get("serverScript"), str)]
    dprovs = [(c, p) for t, c, p in nodes if t == "dataprovider"]

    print(f"文件: {args.file}")
    print(f"  module(带 serverScript): {len(modules)}   dataprovider: {len(dprovs)}")

    problems: list[str] = []
    warnings: list[str] = []

    # serverScript 侧
    provided: set[str] = set()
    for cfg, path in modules:
        ss = cfg["serverScript"]
        names = [m[1] for m in _SETATTR_RE.findall(ss)]
        provided.update(names)
        if "{" + "#" in ss:
            problems.append(
                "serverScript 里出现了 `{#…#}`（ServerScript 不支持该写法，"
                "应用 `app.get(param)`；见 controls.ServerScript 的报错原文）"
            )
        print(f"  serverScript @ {'/'.join(str(x) for x in path)}: setAttribute {sorted(set(names)) or '（无）'}")

    # dataprovider 侧
    used: dict[str, int] = {}
    params: dict[str, int] = {}
    for cfg, path in dprovs:
        sqls = {k: cfg[k] for k in ("sql", "totalSql") if isinstance(cfg.get(k), str)}
        if not sqls:
            continue
        print(f"  dataprovider @ {'/'.join(str(x) for x in path)} (itemId={cfg.get('itemId')!r}):")
        for k, s in sqls.items():
            hs = _HASH_RE.findall(s)
            ps = _PARAM_RE.findall(s)
            for h in hs:
                used[h] = used.get(h, 0) + 1
            for p in ps:
                params[p] = params.get(p, 0) + 1
            print(f"    {k}: {len(s)} 字符, {{#…#}} {len(hs)} 处, {{?…?}} {len(ps)} 处")

    # 逐个判定 {#name#}
    missing = []
    for name, cnt in sorted(used.items(), key=lambda kv: -kv[1]):
        if name in provided:
            print(f"  [ok]   {{#{name}#}} × {cnt}  ← serverScript 已提供")
        elif name.startswith(_BUILTIN_PREFIX):
            print(f"  [ok]   {{#{name}#}} × {cnt}  ← 框架内置变量")
        elif "." in name:
            warnings.append(f"{{#{name}#}} × {cnt} 未在 serverScript 里设置，名字带点（疑似内置变量，请确认）")
        else:
            missing.append(f"{{#{name}#}} × {cnt} 在 dataprovider.sql 里使用，但 serverScript 没有 setAttribute(\"{name}\", …)")

    for w in warnings:
        print(f"  [warn] {w}")
    for m in missing:
        print(f"  [FAIL] {m}")

    if params:
        top = ", ".join(f"{k}({v})" for k, v in sorted(params.items(), key=lambda kv: -kv[1])[:10])
        print(f"  [info] {{?param?}} 共 {len(params)} 个名字，Top: {top}")

    if problems or missing:
        print("=== 结果: FAIL")
        return 1
    print("=== 结果: OK" + ("（有警告）" if warnings else ""))
    return 0


# --------------------------------------------------------------------------- #
# params（页面 → SQL 的传参链路检查）
# --------------------------------------------------------------------------- #
# 页面把值送出去有**两条通路**（框架源码实测，详见 SKILL.md §4.5 与 §4.6）：
#   ① out    —— store.load({out: app.tbar}) / Wb.request({out: …}) / Wb.upload
#               容器内所有「取值控件」的值由框架自动整包送出，**不用枚举控件**。
#   ② params —— store.load({params:{名:值}}) / params: Wb.getValue(app.tbar)
#               显式写出「参数名 → 值」。
# 同名参数的合并优先级（框架源码实测，两条通路**方向相反**）：
#   store.load ：store 自身配置的 params > 调用时传入的 params > out
#   Wb.request ：out > params
_OUT_KEY_RE = re.compile(r"\bout\s*:")
_PARAMS_KEY_RE = re.compile(r"\bparams\s*:")
_GETVALUE_RE = re.compile(r"Wb\.getValue\s*\(")
_APP_REF_RE = re.compile(r"\bapp\.([A-Za-z_$][\w$]*)")
_OBJ_KEY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:")
_REQ_URL_RE = re.compile(r"url\s*:\s*['\"]([^'\"]*m\?xwl=[^'\"]*)['\"]")
_GETNAME_RE = re.compile(r"""app\.get\(\s*['"]([^'"]+)['"]""")
# 有 getValue() 的控件 = 会被 out 收集的。权威来源是 wb/system/controls.json
# （general.type 以 `Ext.form.field.` 开头的那些）；这里是内置兜底名单。
_FIELD_FALLBACK = ("check", "combo", "date", "datetime", "displayfield", "file",
                   "hidden", "htmleditor", "number", "picker", "radio", "text",
                   "textarea", "time")
_SKIP_KEYS = {"out", "add", "callback", "scope", "success", "failure", "async",
              "url", "method", "bean", "params", "waitMsg", "timeout", "extraParams"}


def field_types(controls_path: str | None = None) -> tuple:
    """取值控件类型集合：优先从设计器控件注册表推导，否则用内置兜底。"""
    if controls_path:
        try:
            reg = json.load(open(controls_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            reg = None
        if reg is not None:
            ids: set[str] = set()

            def walk(o):
                if isinstance(o, dict):
                    g = o.get("general")
                    if (isinstance(g, dict) and isinstance(g.get("type"), str)
                            and g["type"].startswith("Ext.form.field.")
                            and isinstance(o.get("id"), str)):
                        ids.add(o["id"])
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(reg)
            if ids:
                return tuple(sorted(ids))
    return _FIELD_FALLBACK


def strip_js_comments(js: str) -> str:
    """去掉 JS 的 `//` 行注释与 `/* */` 块注释（引号内不动）。

    目的：注释掉的 `out:` / `params:` 不该被当成有效传参点。注意只按**行**删注释、
    保留换行，避免把后面的代码粘到注释行上。
    """
    out: list[str] = []
    i, n, quote = 0, len(js), None
    while i < n:
        ch = js[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(js[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "/":
            while i < n and js[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "*":
            i += 2
            while i + 1 < n and not (js[i] == "*" and js[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def read_expr(js: str, i: int) -> str:
    """从 js[i] 起读一个表达式：括号配平，遇顶层 `,` / `}` 或收尾括号即停。"""
    depth = 0
    buf: list[str] = []
    while i < len(js):
        ch = js[i]
        if ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
            buf.append(ch)
        elif depth == 0 and ch in ",}":
            break
        else:
            buf.append(ch)
        i += 1
    return "".join(buf)


def obj_keys(inner: str) -> list[str]:
    """取对象字面量里的**顶层**键名（跳过字符串与嵌套层）。"""
    keys: list[str] = []
    i, depth, quote = 0, 0, None
    while i < len(inner):
        ch = inner[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            m = _OBJ_KEY_RE.match(inner, i)
            if m:
                k = m.group(1)
                if k not in _SKIP_KEYS:
                    keys.append(k)
                i = m.end()
                continue
        i += 1
    return keys


def find_transfers(js: str, field_set) -> list[tuple]:
    """从一段 JS 里提取传参点。

    返回 [(通路, 容器 itemId 列表, 显式参数名列表, 原文片段)]，
    通路 ∈ {"out", "params=Wb.getValue", "params=对象"}。
    """
    js = strip_js_comments(js)
    found: list[tuple] = []
    for m in _OUT_KEY_RE.finditer(js):
        expr = read_expr(js, m.end()).strip()
        conts = _APP_REF_RE.findall(expr)
        if conts:
            found.append(("out", conts, [], expr))
    for m in _PARAMS_KEY_RE.finditer(js):
        expr = read_expr(js, m.end()).strip()
        if _GETVALUE_RE.match(expr):
            conts = _APP_REF_RE.findall(expr)
            if conts:
                found.append(("params=Wb.getValue", conts, [], expr))
        elif expr.startswith("{"):
            keys = obj_keys(expr[1:-1])
            if keys:
                found.append(("params=对象", [], keys, expr))
    return found


def _js_of(node):
    """收集节点上的全部 JS 文本（configs 的字符串值 + events）。"""
    out = []
    c = node.get("configs")
    if isinstance(c, dict):
        out += [v for v in c.values() if isinstance(v, str)]
    ev = node.get("events")
    if isinstance(ev, dict):
        out += [v for v in ev.values() if isinstance(v, str)]
    return out


def _collect_name_islands(obj, container, field_set):
    """容器内所有「取值控件」的 itemId（`out:` 收集时它们就是参数名）。"""
    ids = []
    for t, cfg, _p in iter_nodes(container):
        if t in field_set and isinstance(cfg.get("itemId"), str):
            ids.append(cfg["itemId"])
    return ids


def cmd_params(args) -> int:
    """检查「页面 → store → SQL 文件」的传参链路（静态交叉核对）。

    **两条通路**（都能用，推荐 out）：

    ① `out`（推荐）—— `store.load({out: app.tbar})` / `Wb.request({out: …})`
       框架自动把容器内**全部取值控件**的值打包送出（`Wb.getValue` 递归整个子树）。
       好处：增删条件控件**不用改 JS**，挂在容器上就自动生效。

    ② `params` —— `store.load({params: {名: 值}})` / `params: Wb.getValue(app.tbar)`
       显式写出参数名；适合值不来自控件（如取当前行 `record.data.X`）或只需少数几个参数。

    同名参数的合并优先级（框架源码实测，两条通路方向相反）：
      · `store.load`  ：store 自身配置的 `params` > 调用时 `params` > `out`
      · `Wb.request`  ：`out` > `params`

    SQL 侧需求：`{?名字?}`（sql / totalSql / serverScript 里都算）与 `app.get('名字')`。
    """
    field_set = field_types(getattr(args, "controls", None))
    if getattr(args, "list_fields", False):
        print(f"取值控件类型（{len(field_set)} 种）:")
        for t in field_set:
            print(f"  {t}")
        return 0

    if not args.file:
        print("[FAIL] 需要给出页面文件路径（或改用 --list-fields）")
        return 2

    try:
        text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2

    root = args.module_root
    if not root:
        d = os.path.dirname(os.path.abspath(args.file))
        while d and os.path.basename(d).lower() != "modules":
            nd = os.path.dirname(d)
            if nd == d:
                d = None
                break
            d = nd
        root = d

    print(f"页面: {args.file}")
    print(f"模块根: {root or '（未找到 modules 目录，请用 --module-root 指定）'}")
    print(f"取值控件类型（{len(field_set)} 种）: {', '.join(field_set)}")

    stores: list[dict] = []
    transfers: list[tuple] = []   # (通路, 容器列表, 键列表, 原文, 来源文件相对路径)
    direct: list[str] = []        # Wb.request({url:'m?xwl=…'}) 直接调用的 SQL 文件

    def scan(node, path=()):
        if isinstance(node, dict):
            c = node.get("configs")
            if isinstance(c, dict) and node.get("type") == "store":
                stores.append(c)
            for js in _js_of(node):
                for kind, conts, keys, raw in find_transfers(js, field_set):
                    transfers.append((kind, conts, keys, raw, "/".join(str(x) for x in path)))
                for m in _REQ_URL_RE.finditer(js):
                    tgt = m.group(1).split("m?xwl=")[-1].split("&")[0]
                    if tgt and tgt not in direct:
                        direct.append(tgt)
            for k, v in node.items():
                scan(v, path + (k,))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, path + (i,))

    scan(obj)

    print(f"\n=== store（{len(stores)} 个）===")
    sql_files: list[tuple[str, str]] = []
    for cfg in stores:
        url, iid = cfg.get("url"), cfg.get("itemId")
        line = f"  itemId={iid!r} autoLoad={cfg.get('autoLoad')!r}"
        if isinstance(cfg.get("params"), (dict, list)) and cfg.get("params"):
            line += f"  自身params配置={cfg['params']!r}(优先级最高)"
        if isinstance(url, str) and "m?xwl=" in url:
            tgt = url.split("m?xwl=")[-1].split("&")[0]
            fp = os.path.join(root, tgt.replace("/", os.sep) + ".xwl") if root else None
            ok = bool(fp and os.path.exists(fp))
            line += f"\n      url={tgt} → {'存在' if ok else '未找到'}"
            if ok:
                sql_files.append((tgt, fp))
        else:
            line += f"\n      url={url!r}（非 m?xwl：可能是 Java bean 或其它数据源）"
        print(line)

    if direct:
        print(f"\n=== `Wb.request` 直接调用的 m?xwl（{len(direct)} 个）===")
        for tgt in direct:
            fp = os.path.join(root, tgt.replace("/", os.sep) + ".xwl") if root else None
            ok = bool(fp and os.path.exists(fp))
            print(f"  {tgt}.xwl → {'存在（纳入核对）' if ok else '未找到（可能是框架端点，如 common/save-all）'}")
            if ok and all(tgt != t for t, _ in sql_files):
                sql_files.append((tgt, fp))

    n_out = sum(1 for t in transfers if t[0] == "out")
    n_pm = len(transfers) - n_out
    print(f"\n=== 传参点（{len(transfers)} 处）: out {n_out} 处 / params {n_pm} 处 ===")
    provided: set[str] = set()
    for kind, conts, keys, raw, where in transfers:
        tag = {"out": "[out 推荐]", "params=Wb.getValue": "[params·等价out]",
               "params=对象": "[params·显式键]"}
        head = f"  {tag.get(kind, kind):18s}"
        if conts:
            detail = []
            for a in conts:
                locs = _find_all_by_itemid(obj, a)
                if not locs:
                    detail.append(f"app.{a} → [warn] 页面里找不到 itemId={a!r} 的容器")
                    continue
                dup = f"（同 itemId ×{len(locs)}，取第一个）" if len(locs) > 1 else ""
                ids = _collect_name_islands(obj, locs[0][0][locs[0][1]], field_set)
                provided |= set(ids)
                detail.append(f"app.{a}{dup} → 容器内取值控件 {ids or '（无）'}")
            print(head + "; ".join(detail))
        else:
            provided |= set(keys)
            print(head + f"显式参数名 {keys}")
        print(f"      {'':16s} 原始: {raw[:150]}")

    needed: set[str] = set()
    for tgt, fp in sql_files:
        try:
            so = parse_xwl(open(fp, "rb").read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== SQL 侧 {tgt}.xwl 读取失败: {exc}")
            continue
        print(f"\n=== SQL 侧: {tgt}.xwl ===")
        for t, cfg, _p in iter_nodes(so):
            if t == "module" and isinstance(cfg.get("serverScript"), str):
                ss = cfg["serverScript"]
                g, hs = _GETNAME_RE.findall(ss), _PARAM_RE.findall(ss)
                print(f"  serverScript: app.get(名)={g or []}  {{?名?}}={hs or []}")
                needed |= set(g) | set(hs)
            if t == "dataprovider":
                for k in ("sql", "totalSql"):
                    if isinstance(cfg.get(k), str):
                        ps = _PARAM_RE.findall(cfg[k])
                        print(f"  {k}: {{?名?}} = {ps or []}")
                        needed |= set(ps)

    if not needed:
        print("\n（SQL 侧没有 {?…?} / app.get，跳过交叉核对）")
        return 0

    miss = sorted(n for n in needed if n not in provided)
    extra = sorted(n for n in provided if n not in needed)
    print("\n=== 交叉核对 ===")
    print(f"  页面送出 {len(provided)} 个: {sorted(provided)}")
    print(f"  SQL 需要 {len(needed)} 个: {sorted(needed)}")
    if miss:
        print(f"  [warn] SQL 需要但页面未发现来源: {miss}")
        print("         可能来自：上级容器 / 其它请求（Wb.request）/ store 自身 params 配置 /"
              " sys.* 框架上下文 / 由调用方页面传入")
    else:
        print("  [ok]   SQL 需要的参数在页面侧都能找到来源")
    if extra:
        print(f"  [info] 页面送了但 SQL 未用到: {extra}")
    print("\n  提示：参数名 = 控件 `itemId`；改了 itemId 或把控件移出容器都会**静默失效**（取到空值）。")
    return 1 if miss else 0


# --------------------------------------------------------------------------- #
# dump / sql / events
# --------------------------------------------------------------------------- #
def cmd_dump(args) -> int:
    try:
        _text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return 0


def cmd_sql(args) -> int:
    try:
        _text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2
    items = collect_sql(obj)
    if not items:
        print("(未找到含 'sql' 的键)", file=sys.stderr)
        return 1
    for i, (key, sql) in enumerate(items, 1):
        print(f"----- [{i}/{len(items)}] key={key} -----")
        print(sql)
    return 0


def cmd_events(args) -> int:
    try:
        _text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2
    events = collect_events(obj)
    if not events:
        print("(无 events 节点)", file=sys.stderr)
        return 1
    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        written = []
        for i, (name, code) in enumerate(events, 1):
            fp = os.path.join(args.outdir, f"event_{i}_{name}.js")
            write_text(fp, code.replace(CRLF, "\n"))
            written.append(fp)
        print(f"已导出 {len(written)} 个事件 JS -> {args.outdir}")
        for fp in written:
            print(" ", fp)
    else:
        for i, (name, code) in enumerate(events, 1):
            print(f"----- [{i}/{len(events)}] events.{name} -----")
            print(code)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xwl.py", description="WebBuilder .xwl 文件处理工具"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="七项校验：格式五项 + 事件 JS 语法 + itemId 重名分级")
    c.add_argument("files", nargs="+")
    c.add_argument("--node", help="node 可执行文件路径")
    c.add_argument("--no-js", action="store_true", help="跳过事件 JS 语法校验")
    c.add_argument("--no-itemid", action="store_true", help="跳过 itemId 重名分级检查")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("edit", help="安全替换（保留 CRLF，断言出现次数）")
    e.add_argument("target")
    e.add_argument("--old-file", required=True)
    e.add_argument("--new-file", required=True)
    e.add_argument("--expect", type=int, default=1, help="期望锚点出现次数（默认 1）")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--backup", action="store_true", help="写 <target>.bak")
    e.add_argument("--node")
    e.add_argument("--no-js", action="store_true")
    e.set_defaults(func=cmd_edit)

    pt = sub.add_parser("patch", help="结构级编辑：改对象 + 按设计器规则整份重建（推荐）")
    pt.add_argument("file")
    pt.add_argument("--ops", required=True, help="ops JSON 文件：set/insert/append/delete 的数组")
    pt.add_argument("--indent", type=int, default=1)
    pt.add_argument("--eol", choices=["auto", "lf", "crlf"], default="auto")
    pt.add_argument("--dry-run", action="store_true", help="只显示将产生的 diff，不写入")
    pt.add_argument("--backup", action="store_true")
    pt.add_argument("--node")
    pt.add_argument("--no-js", action="store_true")
    pt.set_defaults(func=cmd_patch)

    pm = sub.add_parser("params", help="检查「页面 → store → SQL 文件」的传参链路（参数名交叉核对）")
    pm.add_argument("file", nargs="?", help="页面 xwl（配 --list-fields 时可省略）")
    pm.add_argument("--module-root", help="wb/modules 的绝对路径（缺省从文件位置向上找）")
    pm.add_argument("--controls", help="wb/system/controls.json；给了就从注册表推导「取值控件」类型")
    pm.add_argument("--list-fields", action="store_true", help="只打印取值控件类型清单后退出")
    pm.set_defaults(func=cmd_params)

    pa = sub.add_parser("paths", help="列出可编辑字段位置（sql / totalSql / serverScript / url），供 patch 用")
    pa.add_argument("file")
    pa.set_defaults(func=cmd_paths)

    n = sub.add_parser("new", help="从零生成一个 xwl 文件（内置设计器骨架，不需要种子文件）")
    n.add_argument("out", help="输出路径；默认拒绝覆盖已存在文件（除非 --force，或改用 patch）")
    n.add_argument("--kind", choices=["page", "sql"], default="page",
                   help="page=独立页面（顶层 + 空 module）；sql=SQL 载体（module→dataprovider）")
    n.add_argument("--from-json", dest="from_json",
                   help="改用这个 JSON 文件的顶层对象（给了它则忽略 --kind / --title / --roles）")
    n.add_argument("--title", default="", help="页面标题（title）")
    n.add_argument("--roles", default=None,
                   help='角色权限，逗号分隔（如 "default" / "default,developer"）；给空串得到 {}')
    n.add_argument("--eol", choices=["lf", "crlf"], default="lf",
                   help="换行：lf=设计器/仓库的原始形态（默认）；crlf=Windows 工作区形态")
    n.add_argument("--indent", type=int, default=1)
    n.add_argument("--force", action="store_true", help="允许覆盖已存在的文件")
    n.add_argument("--dry-run", action="store_true", help="只打印将写入的内容，不写盘")
    n.add_argument("--node")
    n.add_argument("--no-js", action="store_true")
    n.set_defaults(func=cmd_new)

    fld = sub.add_parser("folders", help="folder.json（设计器导航树索引）一致性检查 / 登记")
    fld.add_argument("path", help=".xwl 文件，或要递归检查的目录")
    fld.add_argument("--register", metavar="NAME",
                     help="写操作：把 NAME（一般是该 .xwl 的文件名）追加到所在目录 folder.json 的 index 末尾")
    fld.add_argument("--dry-run", action="store_true")
    fld.set_defaults(func=cmd_folders)

    ii = sub.add_parser("itemids", help="itemId 重名分级报告（候选清单 + 建议值），只读")
    ii.add_argument("file")
    ii.add_argument("--name", help="只点名一个 itemId，打印它的候选清单与建议值")
    ii.add_argument("--dups-only", action="store_true", help="benign 组不展开（长报告时用）")
    ii.add_argument("--suggest", action="store_true", help="输出「改名 ops 草稿」JSON（需人工确认后再 patch）")
    ii.add_argument("--fix", choices=["auto", "normalName", "itemId"], default="auto",
                    help="--suggest 用哪种修法：auto=能补 normalName 就补（默认）")
    ii.add_argument("--controls", help="wb/system/controls.json；缺省从文件位置向上自动找")
    ii.add_argument("--json", action="store_true", help="机器可读输出")
    ii.set_defaults(func=cmd_itemids)

    sr = sub.add_parser("sqlrefs", help="检查 SQL 文件里 serverScript ↔ dataprovider 的引用是否自洽")
    sr.add_argument("file")
    sr.set_defaults(func=cmd_sqlrefs)

    sc = sub.add_parser("schema", help="查设计器控件注册表：某控件合法的 configs / events")
    sc.add_argument("type", nargs="?", help="控件 id，如 button / grid / store；省略需配 --list")
    sc.add_argument("--controls", required=True, help="设计器控件注册表路径（工程里是 wb/system/controls.json）")
    sc.add_argument("--list", action="store_true", help="列出全部控件 id")
    sc.add_argument("--tree", action="store_true", help="按设计器面板分组打印控件树（含库/容器标记）")
    sc.add_argument("--skeleton", action="store_true", help="顺便输出设计器同款最小骨架节点")
    sc.set_defaults(func=cmd_schema)

    d = sub.add_parser("dump", help="解析后美化输出")
    d.add_argument("file")
    d.set_defaults(func=cmd_dump)

    x = sub.add_parser("expand", help="规范成设计器同款多行形态（解析→按设计器算法重排，含语义等价比对）")
    x.add_argument("file")
    x.add_argument("--out", help="输出到另一个文件（缺省原地覆盖）")
    x.add_argument("--indent", type=int, default=1, help="缩进因子（设计器固定用 1，一般不用改）")
    x.add_argument("--eol", choices=["auto", "lf", "crlf"], default="auto",
                   help="换行符：auto=沿用原文件（默认）；lf=设计器在服务器上的原始产物；crlf=Windows 工作区形态")
    x.add_argument("--safe", action="store_true",
                   help="安全模式：不动值里的「字面反斜杠 + n」（设计器会误改它）；产出可能与设计器不一致")
    x.add_argument("--dry-run", action="store_true")
    x.add_argument("--backup", action="store_true", help="原地覆盖时写 <file>.bak")
    x.add_argument("--node")
    x.add_argument("--no-js", action="store_true")
    x.set_defaults(func=cmd_expand)

    s = sub.add_parser("sql", help="抽取 SQL 文本")
    s.add_argument("file")
    s.set_defaults(func=cmd_sql)

    v = sub.add_parser("events", help="抽取事件 JS")
    v.add_argument("file")
    v.add_argument("--outdir", help="导出目录（缺省则打印到标准输出）")
    v.set_defaults(func=cmd_events)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
