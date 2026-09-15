#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xwl.py —— WebBuilder .xwl 文件处理工具（纯标准库）

设计目标：把「安全编辑 + 格式校验」从"凭记忆手工做"固化成可复跑的命令。

子命令：
  check   <file...>                              五项格式校验 + 事件 JS 语法校验
  edit    <file> --old-file O --new-file N       安全替换（保留 CRLF，断言出现次数）
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
    return json.loads(t[t.index("{"):], strict=False)


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
            print("  -> OK")
        for n in notes:
            print(f"  [note] {n}")

    print("=== 结果:", "FAIL" if failed else "ALL OK")
    return 1 if failed else 0


# --------------------------------------------------------------------------- #
# edit
# --------------------------------------------------------------------------- #
def cmd_edit(args) -> int:
    with open(args.old_file, "r", encoding="utf-8", newline="") as f:
        old = normalize_eol(f.read())
    with open(args.new_file, "r", encoding="utf-8", newline="") as f:
        new = normalize_eol(f.read())

    text, has_bom = decode(args.target)
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

    # 立即自检
    print("--- 自动校验 ---")
    ns = argparse.Namespace(files=[args.target], node=args.node, no_js=args.no_js)
    return cmd_check(ns)


# --------------------------------------------------------------------------- #
# expand
# --------------------------------------------------------------------------- #
def cmd_expand(args) -> int:
    """把（通常是单行的）xwl 规范成设计器同款多行形态。

    算法与 WebBuilder 的 `IDE.updateModule` 完全一致（见文件上方 dumps_designer 注释），
    所以输出与设计器保存结果**逐字节一致**（换行符按 --eol 决定）。
    """
    text, has_bom = decode(args.file)
    if has_bom:
        print("[FAIL] 目标文件带 BOM；本工具不处理，请先确认它本来就不该有 BOM")
        return 2

    try:
        obj = parse_xwl(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法按加载器规则解析，先修格式再转换: {exc}")
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

    print("--- 自动校验 ---")
    ns = argparse.Namespace(files=[dest], node=args.node, no_js=args.no_js)
    rc = cmd_check(ns)
    if rc == 0:
        print("> 排版与设计器 `IDE.updateModule` 一致（org.json toString(1) 布局）。")
        print("> 若原文件已被设计器保存过，正常情况下本命令应产出**逐字节相同**的内容。")
    return rc


# --------------------------------------------------------------------------- #
# patch（结构级编辑：改对象 + 按设计器规则重建，不碰文本层）
# --------------------------------------------------------------------------- #
def _find_all_by_itemid(o, name, parent=None, key=None, acc=None):
    """收集当前子树里所有 `configs.itemId == name` 的节点位置 `(容器, 键)`。"""
    if acc is None:
        acc = []
    if isinstance(o, dict):
        c = o.get("configs")
        if parent is not None and isinstance(c, dict) and c.get("itemId") == name:
            acc.append((parent, key))
        for k, v in o.items():
            _find_all_by_itemid(v, name, o, k, acc)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _find_all_by_itemid(v, name, o, i, acc)
    return acc


def _pick_itemid(cur, name):
    """按 itemId 定位唯一节点；**重名时拒绝**（返回第一个会静默改错对象）。"""
    locs = _find_all_by_itemid(cur, name)
    if not locs:
        raise KeyError("找不到 configs.itemId == %r 的节点" % name)
    if len(locs) > 1:
        raise KeyError(
            "configs.itemId == %r 在当前范围内有 %d 个节点，`@` 寻址无法确定改哪一个 —— "
            "请改用下标路径（先跑 `xwl.py paths` / `dump` 看层级），或把目标节点的 itemId 改成唯一值"
            % (name, len(locs))
        )
    return locs[0]


def _step(cur, seg):
    """走一段路径；`@itemId` 段会在当前范围内按 itemId 定位（重名即拒绝）。"""
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


def cmd_patch(args) -> int:
    """结构级编辑：解析 → 改对象 → 用设计器算法整份重建 → 校验。

    这是「遵循设计器规则、不犯格式错」的正路：
    你不用碰续行符 / 转义 / 空白，全部由序列化器按 IDE.updateModule 的规则产生。
    """
    text, has_bom = decode(args.file)
    if has_bom:
        print("[FAIL] 文件带 BOM；本工具不处理")
        return 2

    eol = (CRLF if text.count(CRLF) else "\n") if args.eol == "auto" else ("\n" if args.eol == "lf" else CRLF)
    try:
        obj = parse_xwl(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法按加载器规则解析: {exc}")
        return 2

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
        print(f"[FAIL] 应用 ops 失败: {exc}")
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

    print("--- 自动校验 ---")
    ns = argparse.Namespace(files=[args.file], node=args.node, no_js=args.no_js)
    return cmd_check(ns)


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
        sk = collections.OrderedDict()
        sk["configs"] = {"itemId": "<必填：app.<itemId> 用它寻址>", "text": ""}
        sk["expanded"] = False
        sk["children"] = []
        sk["type"] = args.type
        sk["events"] = {"click": ""} if "click" in ev else {}
        print("\n设计器同款最小骨架（键序与设计器一致：configs, expanded, children, type, events）：")
        print(json.dumps(sk, ensure_ascii=False, indent=2))
        print("\n> 提示：configs 里只放该控件**允许**的键（见上表）；itemId 必须唯一。")
    return 0


def cmd_paths(args) -> int:
    """列出可编辑字段的位置：sql / totalSql / serverScript / url（给 patch 的 path 用）。"""
    text, _ = decode(args.file)
    try:
        obj = parse_xwl(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法解析: {exc}")
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
            raw = "[" + ", ".join(json.dumps(x) if isinstance(x, str) else str(x) for x in path + [k]) + "]"
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
            print(f"   ⚠ @写法 : 不可用 —— itemId {iid!r} 在全文件出现 {dup} 次，`@` 寻址会拒绝执行")
            print("             （用原路径，或先把目标节点 itemId 改成唯一值）")
        else:
            print(f"   推荐   : {at}")
    print("\n用法示例（ops.json）—— @写法不受嵌套层级变动影响：")
    print('  [{"op":"set","path":["@dataprovider1","configs","sql"],"value":"select 1 from dual"}]')
    print('  [{"op":"set","path":["@module","configs","serverScript"],"value":"var data = app.get();\\n..."}]')
    if dup_any:
        print("注意：上面标 ⚠ 的条目 itemId 不唯一 —— `@` 寻址对重名是**拒绝执行**而不是猜一个。")
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
    text, _ = decode(args.file)
    try:
        obj = parse_xwl(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法解析: {exc}")
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

    text, _ = decode(args.file)
    try:
        obj = parse_xwl(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法解析: {exc}")
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
    text, _ = decode(args.file)
    obj = parse_xwl(text)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return 0


def cmd_sql(args) -> int:
    text, _ = decode(args.file)
    obj = parse_xwl(text)
    items = collect_sql(obj)
    if not items:
        print("(未找到含 'sql' 的键)", file=sys.stderr)
        return 1
    for i, (key, sql) in enumerate(items, 1):
        print(f"----- [{i}/{len(items)}] key={key} -----")
        print(sql)
    return 0


def cmd_events(args) -> int:
    text, _ = decode(args.file)
    obj = parse_xwl(text)
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

    c = sub.add_parser("check", help="五项格式校验 + 事件 JS 语法校验")
    c.add_argument("files", nargs="+")
    c.add_argument("--node", help="node 可执行文件路径")
    c.add_argument("--no-js", action="store_true", help="跳过事件 JS 语法校验")
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
