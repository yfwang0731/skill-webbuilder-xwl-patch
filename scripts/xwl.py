#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xwl.py —— WebBuilder .xwl 文件处理工具（纯标准库）

设计目标：把「安全编辑 + 格式校验」从"凭记忆手工做"固化成可复跑的命令。

子命令（15 个）：
  check   <file...>                              七项校验：格式五项 + 事件 JS 语法 + 注册键重名分级
  new     <out.xwl> [--kind page|sql]            **从零生成** xwl（内置设计器骨架）
  patch   <file> --ops ops.json                  结构级编辑（改对象 → 按设计器规则重建）
  edit    <file> --old-file O --new-file N       文本级安全替换（锚点按目标换行归一、断言出现次数、拍平多行时警示）
  expand  <file> [--safe]                        单行源 → 设计器同款多行（写盘前语义等价比对）
  diffguard <path...> [--strict]                 相对 git 基线检测「多行内容被压平」（check 查不出的那类）
  paths   <file>                                 列出 sql / serverScript / url 等字段位置
  params  <page.xwl>                             核对「页面 → store → SQL」的传参链路
  itemids <file>                                 注册键重名报告（分级 + 候选清单 + 建议改名）
  sqlrefs <file>                                 校验 {#名字#} 与 serverScript 是否自洽
  folders <path> [--register [NAME]]             folder.json（导航树索引）一致性检查 / 登记
  schema  [<type>] --controls <…controls.json>   查控件注册表（合法 configs / events / 骨架）
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
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BOM = b"\xef\xbb\xbf"
CRLF = "\r\n"
# 任意一种换行（加载器接受三种：`\r\n` / `\r` / `\n`）。
# **切行必须用它，不能用 `text.split(CRLF)`** —— 后者在纯 LF 文件上切不出行
# （整份文件成一个元素），会让逐行检查静默退化成"只看最后一行"。
# 纯 LF 是设计器写在 Linux 服务器上的产物形态，也是 `new` 的默认产出；
# 它在**检出形态**下很稀少（实测 8 个 wb 根 / 24986 个 xwl 里 LF-only 只有 32 个），
# 所以这条长期没被测到。
ANY_EOL_RE = re.compile(r"\r\n|\r|\n")

# 风格名 → 真实换行串（`--eol` 的两层规则用**风格名**表达，避免 CR/LF 在字符串里肉眼难辨）
_EOL_CHAR = {"crlf": CRLF, "lf": "\n", "cr": "\r"}
_EOL_NAME = {"crlf": "CRLF", "lf": "LF", "cr": "CR"}


def eol_name(eol: str) -> str:
    """把真实换行串翻回可读风格名（给运行时的换行提示用）。"""
    for _k, _c in _EOL_CHAR.items():
        if eol == _c:
            return _EOL_NAME[_k]
    return "LF"


def eol_styles(text: str) -> set:
    """按「风格集合」返回文本里出现过的换行风格：`{"crlf"}` / `{"lf"}` / `{"cr"}` 的任意子集。

    判据与 `check ②` 同源 —— 混用 = 集合里有 ≥2 个元素；纯 CR = 集合恰为 `{"cr"}`。
    """
    n_crlf = text.count(CRLF)
    n_lf = text.count("\n") - n_crlf
    n_cr = text.count("\r") - n_crlf
    styles: set = set()
    if n_crlf:
        styles.add("crlf")
    if n_lf:
        styles.add("lf")
    if n_cr:
        styles.add("cr")
    return styles


def detect_eol(text: str) -> str | None:
    """文本的**单一**换行风格：`"crlf"` / `"lf"` / `"cr"`；无换行或多风格 → `None`。"""
    styles = eol_styles(text)
    if len(styles) == 1:
        return next(iter(styles))
    return None


def pick_eol_for_auto(text: str) -> str:
    """`--eol auto` 的两层规则（`patch` / `expand` / `edit` 三命令共用），返回风格名。

    ① 源**只有一种**风格 → **沿用它**（含纯 CR）；
    ② 源 **≥2 种** → **只在 CRLF/LF 里取多数**；等量（含两者皆 0）取 **CRLF**；**CR 不参与投票**；
    ③ 源**一个换行符都没有** → 回退 **LF**（无从"沿用"，且这一步在输出里写明）。
    """
    styles = eol_styles(text)
    if not styles:
        return "lf"
    if len(styles) == 1:
        return next(iter(styles))
    n_crlf = text.count(CRLF)
    n_lf = text.count("\n") - n_crlf
    return "crlf" if n_crlf >= n_lf else "lf"


def ensure_utf8_stdio() -> None:
    """把 stdout / stderr 切到 UTF-8，并尽量把 Windows 控制台也切过去。

    本工具的输出**全是中文**，而 Windows 上 Python 的标准流默认跟随控制台代码页
    （实测 GitHub 的 `windows-latest` runner 是 **cp1252**），一 `print` 中文就
    `UnicodeEncodeError: 'charmap' codec can't encode ...` —— 直接崩，且**第一行输出就崩**。
    ubuntu / git-bash 都是 UTF-8，所以这个坑只在 Windows 上炸，很容易漏。
    这里显式切到 UTF-8 + `errors="replace"`：**编码问题不该让工具崩掉**。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001  （流被替换过 / 不支持 reconfigure 时忽略）
            pass
    if os.name == "nt":
        # 让 cmd.exe / PowerShell 也按 UTF-8 解释这些字节，否则中文显示为乱码（等价于 chcp 65001）
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:  # noqa: BLE001
            pass


def safe_relpath(path: str, start: str | None = None) -> str:
    """`os.path.relpath` 的安全版：拿不到相对路径就退回原路径，**绝不抛**。

    Windows 上 `os.path.relpath(p)` 不带 `start` 时会以**当前工作目录**为基准；
    只要 `p` 与 cwd **不在同一个盘符**就抛
    `ValueError: path is on mount 'C:', start on mount 'D:'`。
    实测 GitHub 的 `windows-latest` runner 正好命中：仓库签出在 `D:\\a\\...`、
    而 `TEMP` 在 `C:\\...` —— 一句"提示用户怎么登记"的 print 就把命令打死了。

    相对路径在这里只是**给人看的**（缩短显示），所以拿不到就用绝对路径，不要崩。
    """
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return path


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


class XwlWriteError(Exception):
    """写盘失败（目标只读 / 目录不存在 / 路径过长 / 磁盘只读等）。

    单独一个类型，是为了让 `main()` 统一转成可读的 `[FAIL]` + 退出码 2；
    也方便自检脚本断言「写不进去时不冒裸 OSError」。
    """


def _write_file(path: str, data, binary: bool = False) -> None:
    """**所有写盘动作的唯一出口** —— 写不进去时抛 `XwlWriteError`，不冒裸 `OSError`。

    为什么要有这一层：`open(..., "w")` 失败会抛 `OSError`（`PermissionError` /
    `FileNotFoundError` / 路径过长…），使用者看到的会是一段 Python traceback。
    而"目标只读 / 父目录不存在"属于**前置条件不满足**，该给可读提示 + 退出码 2。
    兜在这一层，等于 6 个写盘调用点全部兜住。

    `UnicodeError` 一并兜：它**不是** `OSError` 的子类，所以原来漏在外面。
    正常路径下 `_quote` 已把孤立代理项转义掉，这里是第二道防线
    （写盘出口不该有任何一类"裸异常"漏出去）。
    """
    # 目标已存在但不可写 → 直接报。理由：`os.replace` 在 POSIX 上只受**目录**写权限约束，
    # 目录可写就能把**只读文件**悄悄换掉（`chmod 444` 的目标照样被覆盖）—— 那会让
    # 「目标只读 ⇒ rc=2」这条既有承诺在 Linux 上失效。`os.access` 同时认 Windows 只读属性与 POSIX 权限位。
    if os.path.exists(path) and not os.access(path, os.W_OK):
        raise XwlWriteError(f"无法写入 {path}：目标不可写（只读）")
    tmp = None
    try:
        # 原子写：先写**同目录**临时文件、再 `os.replace()` 覆盖目标。
        # 中途失败（磁盘满 / 进程被杀）只会留下临时文件，**目标内容不变**（不再被截断）。
        d = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp = tempfile.mkstemp(prefix=".xwlw_", suffix=".tmp", dir=d)
        if binary:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        else:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(data)
        if os.path.exists(path):        # mkstemp 建的是 0600，替换前恢复目标原有权限位
            try:
                os.chmod(tmp, os.stat(path).st_mode & 0o777)
            except OSError:
                pass
        os.replace(tmp, path)
        tmp = None
    except (OSError, UnicodeError) as exc:
        # UnicodeError 没有 .strerror，所以用 getattr 取
        raise XwlWriteError(f"无法写入 {path}：{getattr(exc, 'strerror', None) or exc}") from None
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass


def write_text(path: str, text: str) -> None:
    """按给定的文本**原样**落盘（UTF-8 无 BOM；newline='' 关掉自动换行转换）。

    注意**不做换行转换** —— 落盘后的换行完全由调用方给的字符串决定。
    """
    _write_file(path, text)


def write_bytes(path: str, data: bytes) -> None:
    """二进制落盘（目前只用于 `.bak` 备份），失败同样抛 `XwlWriteError`。"""
    _write_file(path, data, binary=True)


def normalize_eol(text: str, eol: str = CRLF) -> str:
    """把任意换行统一成 `eol`（用于 old/new 片段的归一化，便于用 LF 书写片段）。

    ⚠️ 调用方必须传**目标文件的实际换行**（见 `cmd_edit`）。写死 CRLF 会引出两个缺陷：
    **LF 文件上跨行锚点永远匹配不到**（报「锚点出现次数: 0」，
    看着像用户写错了锚点）；**单行锚点 + 多行 new 会把 LF 文件写成 CRLF/LF 混用**。
    两者都已改为按目标换行归一。
    """
    return re.sub(r"\r\n|\r|\n", eol, text)


# 续行符 = 反斜杠 + 真实换行，是多行字符串在磁盘上的形态（见 SKILL.md 2.1）
CONT_RE = re.compile(r"\\(?:\r\n|\r|\n)")


def count_cont(text: str) -> int:
    """数片段里「续行符」的个数 —— 用于识别「把多行拍平」这种静默语义损坏。"""
    return len(CONT_RE.findall(text))


def _byte_len(s: str) -> int:
    """字符串落盘后的字节数（**只用于打印进度**）。

    为什么不能直接 `len(s.encode("utf-8"))`：值里若含孤立代理项会抛
    UnicodeEncodeError —— 而"打印一行进度"绝不该是崩溃点。实测这在
    `patch` 的半途（已打印 `[ok] 已应用 N 个 op`、还没写盘）就把进程打崩，
    退出码 1、并附一段 Python traceback。这里兜住：代理项按 WTF-8 的 3 字节计。
    """
    try:
        return len(s.encode("utf-8"))
    except UnicodeEncodeError:
        return len(s.encode("utf-8", "surrogatepass"))


# --------------------------------------------------------------------------- #
# 加载器等价解析
# --------------------------------------------------------------------------- #
def loader_text(text: str) -> str:
    """复刻加载器：把「反斜杠 + 真实换行」转成「反斜杠 + 字母 n」。"""
    return re.sub(r"\\(?:\r\n|\r|\n)", r"\\n", text)


def _reject_nonfinite(name: str):
    """`json.loads` 的 `parse_constant` 回调：**拒绝** `NaN` / `Infinity` / `-Infinity`。

    Python 的 `json.loads` 默认接受这三个 token（`allow_nan=True`），而它们**不是合法 JSON**：
    工具会把 `NaN` 读成 `float nan`、再用 `repr()` 写出小写 `nan`（非法）⇒ 往返必失败；
    而框架的 `org.json` 把 `NaN` 当**字符串** `"NaN"`（`stringToValue` 只对数字/`-` 开头转数字）
    ⇒ 「工具放行、框架读到另一种类型」。故这里显式抛错，让 `check` ④ 直接判失败（假阴性转真报）。
    """
    raise ValueError("非有限数值 `%s` 不是合法 xwl（org.json 会把它当字符串，且工具写不回）" % name)


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
    return json.loads(t[i:], strict=False, parse_constant=_reject_nonfinite)


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

    四条容易被忽略的规则：
      1. 只转义 `"`、`\\` 与 <0x20 的控制符；**非 ASCII 原样保留**（中文不转成 \\uXXXX）。
      2. `</`（斜杠紧跟左尖括号之后）会写成 `\\/` —— org.json 防 `</script>` 的经典行为。
      3. 其余 `/` 不转义。
      4. **孤立代理项（U+D800–U+DFFF）转成 `\\uXXXX`**（见下方注释）。
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
        elif ord(ch) < 0x20 or 0xD800 <= ord(ch) <= 0xDFFF:
            # 孤立代理项：Python 3 的 str 里 astral 字符（如 emoji）**就是一个字符**，
            # 不会拆成代理对 ⇒ 值里出现 U+D800–U+DFFF 必然是**未配对**的。
            # 原样输出的话任何 .encode("utf-8") 都会抛 UnicodeEncodeError；
            # 实测 `patch` 会在打印字节数时就冒 traceback（rc=1，违反 4.1 的承诺）。
            # 转义成 \uXXXX 后：JSON 合法、能被加载器原样读回、语义等价比对仍成立。
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
        prev = ch
    out.append('"')
    return "".join(out)


def _number(v) -> str:
    """复刻 org.json 的 numberToString —— **但整数值浮点保真写出 `.0`**（K9）。

    与老版 org.json 的唯一差异：它把 `1.0` 写成 `1`（走 longValue），那会让
    `equivalent(parse_xwl(dumps(obj)), obj)` 判**不一致**（写回后值类型从 float 漂成 int）。
    本工具改为**保留 float 的 `.0`**（含 `0.0` / `2.0` …），让往返等价成立 —— 真实工程里
    **整数值浮点 0 例**（全量 24933 文件零例外），所以改动对外无副作用。
    非有限值（`NaN`/`Infinity`）已在解析阶段被拒，这里不重复兜。
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float) and v == 0 and str(v).startswith("-"):
        # 负零：**保留 `-0.0`**（不可折叠成 `-0`/`0`）。虽与下面的 float 分支同效，
        # 但单列出来是为了钉住这条"不可折叠"的语义（与 K9 的 `0.0` 同型参照）。
        return "-0.0"
    if isinstance(v, float):
        # repr(float) 天然给出最短的、能唯一读回该值的十进制写法（`1.0` → `"1.0"`、
        # `0.25` → `"0.25"`、`1e20` → `"1e+20"`）；**不再 rstrip 掉 `.0`** —— 那正是 K9 的病灶。
        return repr(v)
    return repr(v)


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
    事实上 WebBuilder 自己就踩了这个坑（根因与后果见 SKILL.md §2.5），这里做的是**安全版**。
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


def equivalent(a, b) -> bool:
    """**规范化文本**等价判据 —— 比 `==` 严，用来替掉三处写盘前的等价比对。

    为什么不能用 `==`（K8）：Python 的 `==` 把 `1`/`1.0`/`True` 视为相等、把 `0`/`-0.0` 视为相等，
    并且**完全忽略 dict 的键序** ⇒ ① 值的**类型漂移**（float↔int、bool↔int）发现不了；
    ② **键序写错发现不了** —— 而"键序与设计器一致"正是本工具的核心卖点
    （`references/anti-patterns.md` 明写"键序写错，产出即与设计器不一致"）。
    `json.dumps(..., ensure_ascii=False)` 恰好**保留键序**，且能区分 `true`/`1`、`1.0`/`1`、`-0.0`/`0`。

    实测爆炸半径 = **0**：全量 24933 个可解析文件「dump → 再解析」往返，**用 `==` 与用
    `json.dumps` 得到的结论完全一致、零例外**（`-0.0` 只出现在合成样本里）⇒ 本判据的定位是
    "**防手写 / 防外部生成**"，不是修真实工程里的现存问题。
    """
    return json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)


def dumps_designer(obj, indent_factor: int = 1, eol: str = CRLF, safe: bool = False) -> str:
    """序列化成 xwl 的多行磁盘形态，与设计器写回（`IDE.updateModule`）一致。

    eol：设计器**写在服务器上**，产物换行 = 那台服务器的 `line.separator`（Linux 上就是 LF）；
    Windows 工作区因为 git `autocrlf` 看到的是 CRLF。默认按 CRLF 输出以贴合 Windows 工作区形态，
    要还原设计器原始产物用 `eol="\\n"`。

    两个模式**语义等价**（往返解析实测全部等价），**差异只在字节形态**：
    safe=False（默认）：复刻设计器的写回规则 —— 值里那处「字面反斜杠 + n」会被改写成
      「反斜杠 + 换行」（同一段文本的另一种写法，加载器还原回同一个值）。
      产出与设计器**逐字节一致**，要提交就用它。
    safe=True：逐转义对处理，值里那处保持原样，人读更直观；但产出与设计器**不一致**。

    两个模式都**语义无损**（往返解析后键序与值都不变）；选哪个**按"给谁看"决定** ——
    要提交 / 给设计器继续编辑就用默认（产出与设计器**逐字节相同**），只想人读一遍才用 `safe=True`。
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


_UESC_RE = re.compile(r"\\u[0-9a-fA-F]{4}")
_NUMTOK_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def rewrite_counts(text: str, out: str) -> tuple:
    """估「重排会顺带改写」的三类**处数**：缩进 / `\\uXXXX` 转义 / 数字形态。

    只为一个目的：把「非原样排版」这句泛泛提示**具体化**（给用户一个量级），
    **不追求逐字节等价、也不进任何判定**（`equivalent` 才是判定）。三类各返回一个整数：
      · 缩进   = 两版**行首空白长度不同**的行数（按行号对齐，够用）；
      · `\\uXXXX` = 两版里 `\\uXXXX` 转义**个数之差的绝对值**（被展开或反过来收拢）；
      · 数字形态 = 两版里数字 token 的**多重集之差**（如 `1.0`→`1` 算 1 处）。
    """
    la, lb = text.splitlines(), out.splitlines()
    indent = sum(1 for x, y in zip(la, lb)
                 if (len(x) - len(x.lstrip())) != (len(y) - len(y.lstrip())))
    uesc = abs(len(_UESC_RE.findall(text)) - len(_UESC_RE.findall(out)))
    numdiff = sum((collections.Counter(_NUMTOK_RE.findall(text))
                   - collections.Counter(_NUMTOK_RE.findall(out))).values())
    return indent, uesc, numdiff


class XwlLoadError(Exception):
    """读文件 / 解析 xwl 失败 —— 消息面向用户，可直接打印。"""


#: 非 UTF-8 的**唯一一份**可读文案 —— `read_xwl_text`（抛 `XwlLoadError`）与 `check`（`[FAIL]`）都引用它。
#: ⚠️ 两处必须同源：只改一侧会让另三个入口仍甩 Python codec 原文（`params` / `itemids` 同样走这条路）。
_NOT_UTF8_HINT = ("不是 UTF-8 文本（xwl 必须是无 BOM 的 UTF-8）。**工具不猜编码** —— "
                  "猜错会写成乱码，而乱码文件本身是合法 UTF-8、会一路放行；"
                  "请另存为 UTF-8 或用 `iconv` 转换后覆盖")


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
        raise XwlLoadError("%s（原始错误：%s）" % (_NOT_UTF8_HINT, exc)) from exc


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
            [node, "--check", tmp], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60
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


# 批量 JS 校验驱动：一次 node 进程里把 N 段代码全验完。
#
# **编译语义必须与 `node --check <x.js>` 对齐** —— 后者把 .js 当 **CommonJS 模块**
# （包一层函数），所以顶层 `return` 是**合法**的；而 `vm.Script` 是当**脚本**编译的，
# 会把 `return` 判成 Illegal return statement。
# 实测教训：用 `vm.Script` 写这版时，一个 486 KB 页面的 FAIL 数从 16 涨到 120 —— 全是误报。
# 所以这里用 `new Function(code)`（函数体语义），才与 CommonJS 行为一致。
_NODE_BATCH_JS = """
let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => { raw += d; });
process.stdin.on('end', () => {
  let segs;
  try { segs = JSON.parse(raw); } catch (e) { process.exit(3); }
  const out = [];
  for (const s of segs) {
    let ok = false, err = '';
    const tries = [s.code];
    const t = (s.code || '').trim();
    if (t.startsWith('{') && t.endsWith('}')) tries.push('(' + s.code + ')');
    for (const c of tries) {
      try { new Function(c); ok = true; err = ''; break; }
      catch (e) { err = (e && e.message) ? e.message : String(e); }
    }
    out.push({ ok: ok, err: err });
  }
  process.stdout.write(JSON.stringify(out));
});
"""


def node_check_many(node: str, codes: list) -> list:
    """批量校验多段 JS，返回与 `codes` 等长的 [(ok, err)]。

    **为什么批量**：逐段调 `node --check` 每次都要付 node 冷启动（本机实测 ~250 ms）。
    实测一个 486 KB 的页面有 246 个事件段 ⇒ 逐段校验要 63 s，占了整个 `check` 的 99%。
    批量后同样内容一次进程搞定（实测 63 s → 1.0 s）。

    **正确性怎么保证**：批量结果只用来**证明「合法」** —— 能让 `new Function` 编译过就一定
    也能过 `node --check`（后者是把 .js 包一层函数体编译，与 `new Function` 同语义）。
    凡是批量判**不合法**的，一律回到权威路径 `node_check`（真的 `node --check`）逐段复核。
    代价只在"确实有报错"时才付，而那种情况本来就很少。

    这条复核不能省：`new Function` 比 `node --check` **更严** —— Node 22 的 `--check`
    在 CJS 解析失败时会**自动按 ESM 重试**（`--experimental-detect-module` 默认开），
    因此接受**顶层 `await` / `import` / `export`**，而 `new Function` 不接受。
    实测：漏掉复核会把一个 486 KB 页面的 FAIL 数从 16 顶到 120（全是误报）。
    """
    if not codes:
        return []
    results = None
    try:
        proc = subprocess.run(
            [node, "-e", _NODE_BATCH_JS],
            input=json.dumps([{"code": c} for c in codes]),
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        if proc.returncode == 0:
            got = json.loads(proc.stdout)
            if isinstance(got, list) and len(got) == len(codes):
                results = [(bool(g.get("ok")), (g.get("err") or "").strip()) for g in got]
    except Exception:  # noqa: BLE001
        results = None
    if results is None:
        return [node_check(node, c) for c in codes]
    for i, (ok, _err) in enumerate(results):
        if not ok:
            results[i] = node_check(node, codes[i])
    return results


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def bare_nul_in_strings(text: str) -> int:
    """字符串字面量里出现**裸 NUL**（`\x00`）的处数。

    为什么单独查：工具刻意用 `json.loads(..., strict=False)`（org.json 允许字符串内裸换行/Tab），
    于是**裸 NUL 会被放行**、`check` 报 ALL OK；而 org.json 的 `JSONTokener` 有 `Unterminated string`
    分支、其 `next()` 对**真实 NUL 与 EOF 都返回 0** ⇒ 框架加载会失败 —— 属"工具放行、框架拒绝"的
    **假阴性**。⚠️ 证据等级：**高置信未直证**（来自字节码字符串 + 机制推理，**未实机跑 Java**）。
    写成 `\u0000` 的**转义**不算（那是对的做法）。
    """
    n = 0
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            elif ch == "\x00":
                n += 1
        elif ch == '"':
            in_str = True
    return n


# 设计器模板变量标记（`dev/template/**` 里那些 `#{…}`）—— 用来把「模板文件」与「真坏文件」分开报。
_TEMPLATE_RE = re.compile(r"#\{")


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
        except UnicodeDecodeError as exc:
            # 与 `decode` 的 `XwlLoadError` **同一段**文案（同一个常量）—— 两处必须同源。
            print("  [FAIL] " + _NOT_UTF8_HINT)
            print(f"         （原始错误：{exc}）")
            failed = True
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] 无法读取: {exc}")
            failed = True
            continue

        # ① BOM
        if has_bom:
            errors.append("① 文件带 UTF-8 BOM（必须无 BOM）")

        # ② 换行：按**风格集合**判 —— 混用（≥2 种）判 FAIL；**纯 CR 降为 [warn]**
        #    （加载器接受 CR，但设计器/仓库从不产出这种形态 ⇒ 值得注意、不算格式错）。
        eol_warns: list[str] = []
        n_crlf = text.count(CRLF)
        bare_lf = text.count("\n") - n_crlf
        bare_cr = text.count("\r") - n_crlf
        styles = eol_styles(text)
        if len(styles) > 1:
            errors.append(
                f"② 换行混用：{n_crlf} 个 CRLF + {bare_lf} 个裸 LF + {bare_cr} 个裸 CR"
                f"（同一文件必须一致）"
            )
        elif styles == {"cr"}:
            eol_warns.append(
                "该文件是 CR 换行（加载器接受，但设计器/仓库从不产出这种形态；改动它会整份 diff）"
            )

        notes: list[str] = []
        # 「单行形态」的判据 = **任何换行都没有** —— 用 `ANY_EOL_RE` 判真·无换行，
        # 而不是只数 `\n`/`\r\n`（那样纯 CR 文件会同时得到「单行形态」note 与纯 CR 提示，自相矛盾）。
        if text.strip() and not ANY_EOL_RE.search(text):
            notes.append(
                "该文件是单行形态（无任何换行）。可用 `xwl.py expand` 转成规范多行；"
                "**不要**把多行文件改成单行。"
            )
        elif styles == {"lf"}:
            notes.append("该文件是 LF 换行（设计器在服务器上的产物形态），合法。")

        lines = ANY_EOL_RE.split(text)

        # ③ 反斜杠 + 空白
        bad_ws = [i + 1 for i, ln in enumerate(lines) if re.search(r"\\[ \t]+$", ln)]
        if bad_ws:
            errors.append(
                f"③ 第 {bad_ws[:10]} 行以「反斜杠+空白」结尾（续行符后不能有空格/Tab）"
            )

        # ⑤ 末行不得以续行符结尾
        if lines and lines[-1].endswith("\\"):
            errors.append("⑤ 末行以反斜杠结尾（最后一行不能加续行符）")

        # ④ 加载器等价解析 —— 三类「不能加载」分开说：空文件 / 设计器模板 / 真坏。
        #    三者 rc 都是 1（确实加载不了），但把三句混成一句会让用户误判成"格式错误"，
        #    尤其空文件（尚未建内容）与 dev/template 下的模板（本就不是可加载页面）。
        obj = None
        try:
            obj = parse_xwl(text)
        except Exception as exc:  # noqa: BLE001
            if not text.strip():
                errors.append("④ 这是空文件（尚未建内容），不是格式错误 —— 但它无法被加载器加载")
                notes.append("空文件常**集中出现**、不是均匀形态（多半是脚本只建了文件、"
                             "没填内容）。")
            elif _TEMPLATE_RE.search(text):
                errors.append("④ 疑似设计器模板 / 含模板变量（结构位有 `#{…}`），本就不是可加载页面")
            else:
                errors.append(f"④ 加载器等价解析失败: {exc}")

        # ⑥ 事件 JS 语法
        events: list[tuple[str, str]] = []
        if obj is not None and node and not args.no_js:
            events = collect_events(obj)
            results = node_check_many(node, [code for _name, code in events])
            for (name, _code), (ok, err) in zip(events, results):
                if not ok:
                    head = err.splitlines()[0] if err else "语法错误"
                    errors.append(f"⑥ events.{name} JS 语法错误: {head}")

        # ⑦ 注册键重名（分级）—— 按 `normalName || itemId` 分组；只有「重名 **且** 已被
        #    事件 JS 引用」才算 FAIL（**只两级**：被引用 error / 未被引用 benign）
        itemid_warns: list[str] = []
        itemid_note = ""
        no_itemid = bool(getattr(args, "no_itemid", False))
        if obj is not None and not no_itemid:
            ctl_c = discover_controls(path)
            rep = audit_itemids(obj, controls_path=ctl_c)
            # H11：注册表来源 —— 与 `itemids` / `params` 逐字同一句（三处复用 controls_source_line）
            print("  " + controls_source_line(ctl_c))
            for m in rep["errors"]:
                errors.append(f"⑦ {m}")
            itemid_warns = rep["warns"]
            n_g = len(rep["groups"])
            if n_g:
                itemid_note = (f"⑦ 注册键重名 {n_g} 组（error {len(rep['errors'])} / "
                               f"benign {rep['n_benign']}）"
                               f" —— 明细: `xwl.py itemids {os.path.basename(path)}`")

        if errors:
            for e in errors:
                print(f"  [FAIL] {e}")
            print("  -> FAIL")
            failed = True
        else:
            print("  [ok]   ① BOM  ② 换行一致  ③ 续行空白  ④ 解析  ⑤ 末行结构")
            # ⑥⑦ 无论跑没跑都要留一行 —— 否则用户看到 6 行、文档写「七项」，
            # 而且 `--no-js` 与 `--no-js --no-itemid` 的输出会长得一模一样。
            if args.no_js:
                print("  [note] ⑥ 事件 JS 语法校验：已按 `--no-js` 跳过")
            elif node is None:
                print("  [note] ⑥ 事件 JS 语法校验：未找到 node，已跳过（见上方 warn）")
            elif events:
                print(f"  [ok]   ⑥ {len(events)} 个事件 JS 语法全部通过")
            else:
                print("  [ok]   ⑥ 无 events 节点")
            if no_itemid:
                print("  [note] ⑦ 注册键重名分级：已按 `--no-itemid` 跳过")
            elif itemid_note:
                print("  [ok]   " + itemid_note)
            else:
                print("  [ok]   ⑦ 无重名")
            print("  -> OK")
        n_nul = bare_nul_in_strings(text)
        if n_nul:
            print(f"  [warn] 字符串里含 {n_nul} 处**裸 NUL**（`\\x00`）：多数 JSON 解析器"
                  f"（含框架用的 org.json）会拒绝，请转义成 `\\u0000`")
            print("         ⚠️ 证据等级：**高置信未直证** —— 依据是 `org/json/JSONTokener.class` 的 "
                  "`Unterminated string` 分支、以及 `next()` 对 NUL 与 EOF 都返回 0 的机制推理，"
                  "**未实机跑 Java**")
            print("         本项**只告警、不进 rc**（工具自身按 `strict=False` 解析，会放行）")
        for w in eol_warns:
            print(f"  [warn] {w}")
        for w in itemid_warns:
            print(f"  [warn] {w}")
        for n in notes:
            print(f"  [note] {n}")

    print("=== 结果:", "FAIL" if failed else "ALL OK")
    return 1 if failed else 0


def _post_check(file: str, args) -> int:
    """写盘后的**格式**自检 —— 只回答「这次改动有没有破坏格式」。

    注册键重名（第 ⑦ 项）是**文件既有的质量属性**，不是本次改动造成的：
    若一并判定，会出现"写盘成功却返回非 0"的误导。所以这里显式跳过，只在末尾给一条指引。
    """
    print("--- 自动校验（本次改动是否破坏格式）---")
    ns = argparse.Namespace(files=[file], node=getattr(args, "node", None),
                            no_js=getattr(args, "no_js", False), no_itemid=True)
    rc = cmd_check(ns)
    print("提示：注册键重名不在本步判定范围；要连它一起体检，跑 "
          "`xwl.py itemids %s`" % os.path.basename(file))
    return rc


# --------------------------------------------------------------------------- #
# edit
# --------------------------------------------------------------------------- #
def cmd_edit(args) -> int:
    try:
        text, has_bom = read_xwl_text(args.target)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2
    if has_bom:
        print("[FAIL] 目标文件带 BOM，本工具不处理；请先确认它本来就不该有 BOM")
        return 2

    # 锚点按**目标文件的实际换行**归一化 —— 否则 LF 文件上跨行锚点永远匹配不到
    # （写死 CRLF 时，跨行锚点在 LF 文件上必然失配，而失败信息是误导性的
    #   「锚点出现次数: 0」，会让人以为锚点写错）
    # 换行判据与 `patch`/`expand` 同源（`pick_eol_for_auto`）：单风格沿用（含纯 CR）、
    # 混用只在 CRLF/LF 取多数、CR 不投票、无换行回退 LF。
    styles = eol_styles(text)
    eol = _EOL_CHAR[pick_eol_for_auto(text)]
    if len(styles) > 1:
        n_crlf = text.count(CRLF)
        n_lf = text.count("\n") - n_crlf
        n_cr = text.count("\r") - n_crlf
        print(f"[warn] 目标文件换行混用（{n_crlf} 个 CRLF + {n_lf} 个裸 LF + {n_cr} 个裸 CR）："
              f"锚点按 {eol_name(eol)} 归一化；若匹配不到，先修文件换行（`check` 第 ② 项）")

    with open(args.old_file, "r", encoding="utf-8", newline="") as f:
        old = normalize_eol(f.read(), eol)
    with open(args.new_file, "r", encoding="utf-8", newline="") as f:
        new = normalize_eol(f.read(), eol)

    count = text.count(old)
    print(f"锚点出现次数: {count} (期望 {args.expect})")
    if count != args.expect:
        print("[FAIL] 锚点出现次数与期望不符，未写文件（防止改错位置）")
        return 2

    # 「把多行拍平」是一种**静默**语义损坏：压平后文件仍是合法 JSON，`check` 全绿，
    # 只能靠 git diff 发现。这里手上同时有 old / new 两端，是唯一能主动提示的地方。
    c_old, c_new = count_cont(old), count_cont(new)
    if c_old > c_new:
        print(f"[warn] 锚点里的续行符从 {c_old} 个减到 {c_new} 个 —— 多行内容被拍平，"
              f"换行会丢失（语义已变，`check` 查不出来）")
        print("       若本意是改内容、同时保留换行，请改用结构级 `patch`（不碰文本层）")

    if args.dry_run:
        print("[dry-run] 未写入。变更后长度:", len(text) - count * len(old) + count * len(new))
        return 0

    if args.backup:
        bak = args.target + ".bak"
        write_bytes(bak, read_bytes(args.target))
        print(f"备份 -> {bak}")

    write_text(args.target, text.replace(old, new))
    print(f"已写入: {args.target}")

    # 立即自检（只判格式；注册键重名见 _post_check 注释）
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

    # EOL：auto = **两层规则**（① 源只有一种风格 → 沿用它（含纯 CR）；② 源 ≥2 种 →
    # 只在 CRLF/LF 取多数、等量取 CRLF、**CR 不投票**；③ 无换行 → 回退 LF）。
    # 这条规则由 patch / expand / edit **三命令共用**（`pick_eol_for_auto`）。
    # ⇒ 无换行源回退 LF、这一步**不静默**（各命令都会在输出里写明选了哪个换行）。
    styles = eol_styles(text)
    if args.eol == "auto":
        eol = _EOL_CHAR[pick_eol_for_auto(text)]
    else:
        eol = _EOL_CHAR[args.eol]
    if args.indent != 1:
        print(f"[warn] --indent {args.indent} ≠ 设计器缩进（1 个空格）：产出与设计器不一致，"
              f"设计器下次保存会产生整份 diff。除非在做排版复刻实验，否则用默认值")
    if args.safe:
        print("[warn] --safe 的产出与设计器不一致（值里那处「字面反斜杠 + n」保持原样）："
              "两个模式**语义等价**、只差字节形态，但设计器下次保存会产生整份 diff —— "
              "只想人读一遍请用 `xwl.py sql` / `events`，别用它覆盖要提交的文件")

    out = dumps_designer(obj, args.indent, eol, safe=args.safe)
    # 换行统计要和 `check` 的 ② 用**同一口径**：`n_lf - n_crlf` 才是"裸 LF"个数。
    # 打成 `LF=text.count("\n")` 会把 CRLF 里的 `\n` 也算进去 ——
    # 一份纯 CRLF 文件会显示成「CRLF=17101, LF=17101」，读者极易误读成"混用了"。
    n_crlf = text.count(CRLF)
    bare_lf = text.count(chr(10)) - n_crlf
    bare_cr = text.count(chr(13)) - n_crlf
    print(f"原文件: {_byte_len(text)} B, CRLF={n_crlf}, 裸LF={bare_lf}, 裸CR={bare_cr}")
    print(f"规范化后: {_byte_len(out)} B, 换行={eol_name(eol)}"
          f"{', 安全模式(--safe)' if args.safe else ''}")
    # C4：换行混用必须报（与 patch / edit 对齐）—— 重排会把整份统一成一种。
    if len(styles) > 1:
        print(f"[warn] 源文件换行混用（{n_crlf} 个 CRLF + {bare_lf} 个裸 LF + {bare_cr} 个裸 CR，"
              f"见 `check` 第 ② 项）：重排后整份统一为 {eol_name(eol)}，diff 会含换行差异")
    # H6：把「非原样排版」具体化（只提示、不改行为）—— 三类改写各给一个整数处数。
    if out != text and ANY_EOL_RE.search(text):
        _ci, _cu, _cn = rewrite_counts(text, out)
        print("[note] 本次还会顺带改写：缩进 %d 处 / \\uXXXX 转义 %d 处 / 数字形态 %d 处 "
              "—— 都无语义影响；建议先 --dry-run 看 diff" % (_ci, _cu, _cn))

    # 语义等价比对（**规范化文本**，必须过，否则不写）
    try:
        if not equivalent(parse_xwl(out), obj):
            print("[FAIL] 重新序列化后语义不一致，已中止（不写文件）")
            return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 重新序列化结果无法解析，已中止: {exc}")
        return 2
    print("[ok]   语义等价比对通过（规范化文本一致：含键序与值类型）")

    if args.dry_run:
        print("[dry-run] 未写入")
        return 0

    dest = args.out or args.file
    if args.backup and dest == args.file:
        bak = args.file + ".bak"
        write_bytes(bak, read_bytes(args.file))
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
# 「注册键重名」的严重度（**只两级**）—— 按**注册键** `normalName || itemId` 分组。
# 注册键与框架注册语义一致（`if(appScope && (normalName||itemId))`，normalName 优先、
# 空串视同缺失）⇒ **各自有唯一 normalName 的同名节点天然落到不同组**，无需再"豁免"。
#
#   error  — 真隐患：该注册键**已被事件 JS 引用**
#            （框架注册是普通赋值、后注册的覆盖先注册的，且任一重复项销毁时 `unregister`
#             会把整个名字 `delete` ⇒ `app.<键>` 取到的随时可能不是你要的那个）
#   benign — 未被事件 JS 引用：实践中无害
#            · 列控件 column / tcolumn：实测 3393 组重名、**0 组**被事件 JS 引用
#              （取数走 `app.<grid>.getSelection(0).data.*`，不会去取列控件本身）
#            · 名字不是合法 JS 标识符（含中文 / 空格 / `.` 等）：只能 `app.get('名')` / `app['名']` 取
#            · 按钮 / 面板 / 数据承载… 等其余类型重名：老代码可暂留，但新代码应区分
_IID_COL_TYPES = frozenset({"column", "tcolumn"})
_IID_JS_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
_IID_INDEX_RE = re.compile(r"^(?P<name>.+)#(?P<idx>\d+)$")
_APP_REF_BARE = re.compile(r"\bapp\.([A-Za-z_$][\w$]*)")
_APP_REF_GET = re.compile(r"""app\.get\(\s*['"]([^'"]+)['"]""")
# `app['名']` / `app["名"]`（B7）—— **要求闭合 `]`**：键内不许出现引号/加号/模板串，
# 故 `app['a' + b]`（动态）、`app[`x`]`（模板）**都不认**（它们本就不是静态可判的引用）。
_APP_REF_BRACKET = re.compile(r"""app\[\s*['"]([^'"]+)['"]\s*\]""")
# `app.<名字>` 里属于方法/框架成员而非「控件名（注册键）」的名字 —— 统计引用时排除
_APP_REF_RESERVED = frozenset({
    "get", "set", "add", "remove", "insert", "down", "up", "query", "queryBy", "find",
    "fireEvent", "on", "un", "suspendEvents", "resumeEvents", "getId", "getCmp",
    "getViewModel", "getController", "getStore", "getSelection", "getWidget",
    "ownerCt", "items", "store", "el", "body", "id", "is", "callParent",
})

# 合法接受 `normalName` 的控件类型 —— 权威来源是控件注册表（wb/system/controls.json）里
# 该控件 `configs` 是否含 `normalName` 键。下面这份内置清单取自样本工程实测
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


def _find_upward(start_file: str, rel: str) -> str | None:
    """从文件位置向上找工程内的 `wb/<rel>`（最多上溯 12 层）。"""
    d = os.path.dirname(os.path.abspath(start_file))
    for _ in range(12):
        for cand in (os.path.join(d, rel), os.path.join(d, "wb", rel)):
            if os.path.isfile(cand):
                return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def discover_controls(start_file: str) -> str | None:
    """从文件位置向上找设计器控件注册表 `wb/system/controls.json`。"""
    return _find_upward(start_file, os.path.join("system", "controls.json"))


def controls_source_line(ctl: str | None) -> str:
    """注册表来源提示 —— **`itemids` / `params` / `check ⑦` 三处复用同一句**（H11）。

    只改一处会让三个入口的措辞漂移（A 组同款陷阱），所以做成一个函数、逐字复用。
    未找到分支：`控件注册表: 未找到（normalName 白名单 = 注册表 ∪ 内置兜底）`。
    """
    return "控件注册表: %s（normalName 白名单 = 注册表 ∪ 内置兜底）" % (ctl or "未找到")


def normalname_types(controls_path: str | None = None) -> tuple:
    """合法接受 `normalName` 的控件类型 = **注册表推导 ∪ 内置兜底**。

    为什么必须并集（与 `field_types` 同构）：只取注册表时，**老工程会整类丢掉**
    实测新注册表有、老工程没有的类型（`month` / `colorfield` / `echart`）
    ⇒ 明明合法的类型被判"不在白名单里"，修法建议跟着错。并集只会**少报**，是安全方向。
    """
    ids: set[str] = set(_NORMALNAME_FALLBACK)
    if controls_path:
        try:
            reg = json.load(open(controls_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            reg = None
        if reg is not None:

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
    return tuple(sorted(ids))


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

    ⚠️ **用途边界（与 `iter_nodes` 的分工，别混用）**：
    - **本函数 = 控件树语义**（**跳过 `configs`**）—— 一切"这是不是一个控件 / 它的 itemId
      是什么 / 能不能被 `@itemId` 寻址到"的判断都用它。`patch` 的 `@` 寻址、`itemids`、
      `paths` 都走这条口径。
    - `iter_nodes`（下钻 `configs`）只在**确实需要看 `configs` 内嵌套结构**时用
      （如 `sqlrefs` 找 `serverScript` / `dataprovider`）。
    - ⚠️ **两处的 `path` 必须同源**：`paths` 推荐给 `patch` 的路径若来自另一条口径，
      就会出现"推荐了 `patch` 解不开的路径"。

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


def registry_key(cfg) -> str | None:
    """节点的**注册键** = `normalName || itemId`（normalName 优先；空串视同缺失）。

    与框架 `if(appScope && (normalName||itemId))` 的注册语义一致 —— 重名判定按它分组。
    两者都缺（含空串）⇒ `None`（该节点不进注册键分组）。
    """
    nn = cfg.get("normalName")
    if isinstance(nn, str) and nn:
        return nn
    iid = cfg.get("itemId")
    if isinstance(iid, str) and iid:
        return iid
    return None


def itemid_hits(o, name, by: str = "itemid"):
    """节点详情（重名时用来列候选）。

    `by="itemid"`（默认）：匹配 `configs.itemId == name` —— `@itemId` 寻址走它；
    `by="registry"`：匹配**注册键** `normalName || itemId` —— `itemids --name` 走它
    （这样 `--name` 也能用注册键点名，见 `--json` 契约）。
    """
    if by == "registry":
        return [h for h in _iter_controls(o) if registry_key(h[2]) == name]
    return [h for h in _iter_controls(o) if h[2].get("itemId") == name]


def js_refs_of(obj, filtered: bool = True) -> set:
    """文件内**事件 JS** 里引用到的控件名（`app.X` / `app.get('X')` / `app['X']`）。

    - 先 `strip_js_comments` 剔注释 —— 注释里的 `app.X` 不是引用（否则会误报）。
    - 三种写法都认：`app.X`、`app.get('X')`、`app['X']`（`_APP_REF_BRACKET`）。
    - `filtered=True`（默认）：再滤掉 `_APP_REF_RESERVED` 里的方法名/框架成员。
      判定"某个 itemId 是否被引用"时**应传 `filtered=False`** —— 那个名字既已确认是文件内的
      `itemId`，保留表那层"可能只是方法"的歧义就不存在了（`store` / `add` / `items` / `id`
      都是真实存在的 itemId，滤掉会漏判）。
    """
    blob = "\n".join(code for _n, code in collect_events(obj))
    if not blob:
        return set()
    clean = strip_js_comments(blob)
    names = (set(_APP_REF_BARE.findall(clean)) | set(_APP_REF_GET.findall(clean))
             | set(_APP_REF_BRACKET.findall(clean)))
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
            lines.append('    {"op":"set","path":%s,"value":%s}' % (
                "[" + ", ".join(json.dumps(x) if isinstance(x, str) else str(x) for x in p) + "]",
                json.dumps(s, ensure_ascii=False)))
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


def _fmt_keypath(path) -> str:
    """把 path 列表渲染成 `children[0].serverScript` 这种紧凑写法（给 `[warn]` / 报错里的人看）。"""
    out = ""
    for seg in path:
        if isinstance(seg, int):
            out += "[%d]" % seg
        else:
            out += ("." if out else "") + str(seg)
    return out


def _is_new_object_key(parent, key) -> bool:
    """末段是不是「一个尚不存在的对象键」（`A-a` 粒度）。

    **仅当容器是 dict 且该键缺失**才算新建键；末段是数组下标（容器是 list）**不算** ——
    那走 `A-c` 的越界判据（加数组元素用 append/insert，本就不是「新建键」）。
    """
    return isinstance(parent, dict) and key not in parent


def apply_ops(obj, ops, created=None, warned=None):
    """按 ops 就地修改对象。

    path 是「键 / 数组下标」列表；**以 `@` 开头的段按 `configs.itemId` 寻址**
    （例：`["@dataprovider1", "configs", "sql"]`），所以不用关心嵌套层级。

    op 形态：
      {"op":"set",    "path":[...], "value":...}
      {"op":"set",    "path":[...], "value":..., "create": true}   ← 显式声明「新建键」
      {"op":"insert", "path":[...], "index":n, "value":...}   缺省 index = 末尾
      {"op":"append", "path":[...], "value":...}
      {"op":"delete", "path":[...], "index":n}                给 index 删数组元素；否则删键

    `create` 是**逐 op 字段、只挂在 `set` 上**（不是 CLI 开关）：给「原本不存在的对象键」
    写值时用它显式放行；写到已存在的键上它是**幂等保护**（既不报错也不告警）。
    用在 `insert`/`append`/`delete` 上属**用法错误**，抛 `ValueError`（调用方据此返回 rc=2）。

    `created` / `warned` 是**可选的收集列表**（默认 `None` = 不收集）——调用方传列表即可拿到
    「本次新建了哪些键」（`<path>` 紧凑写法）：
      · `created`：带 `"create": true` 的新建键；
      · `warned` ：**不带** `create` 的新建键（本版仍放行，调用方据此打 `[warn]` 预告）。
    两者都是**向后兼容的可选关键字**，既有 `apply_ops(obj, ops)` 调用不受影响。

    越界 / 缺失键等用法错误统一抛 `ValueError`，文案走 `A-d` 模板
    （`第 K 个 op（<kind>）：<现象> —— <可能原因>；用 paths / dump 核对 path`），**不冒裸异常类型名**。
    """
    for i, op in enumerate(ops, 1):
        if not isinstance(op, dict):
            raise ValueError("第 %d 个 op 不是对象" % i)
        kind = op.get("op")
        path = op.get("path") or []
        if not path:
            raise ValueError("第 %d 个 op 的 path 为空" % i)
        want_create = bool(op.get("create"))
        if want_create and kind != "set":
            raise ValueError(
                "第 %d 个 op：`create` 只用于 `set`；`insert`/`append`/`delete` 不支持"
                "（加数组元素用 append/insert，本就不算新建键）" % i)
        if kind == "set":
            parent, key = resolve_parent(obj, path)
            if _is_new_object_key(parent, key):
                where = _fmt_keypath(path)
                if want_create:
                    if created is not None:
                        created.append(where)
                elif warned is not None:
                    warned.append(where)
            if isinstance(parent, list):
                idx = int(key)
                if not 0 <= idx < len(parent):
                    raise ValueError(
                        "第 %d 个 op（set）：下标 %d 越界 —— 数组长度 %d，合法区间 [0, %d]"
                        "；用 paths / dump 核对 path（末段是数组下标，不是对象键）"
                        % (i, idx, len(parent), len(parent) - 1))
                parent[idx] = op["value"]
            else:
                parent[key] = op["value"]
        elif kind in ("insert", "append"):
            arr = resolve_path(obj, path)
            if not isinstance(arr, list):
                raise ValueError("第 %d 个 op：path 指向的不是数组" % i)
            if kind == "append":
                arr.append(op["value"])
            else:
                idx = int(op.get("index", len(arr)))
                if not 0 <= idx <= len(arr):
                    raise ValueError(
                        "第 %d 个 op（insert）：下标 %d 越界 —— 数组长度 %d，合法区间 [0, %d]"
                        "；用 paths / dump 核对 path" % (i, idx, len(arr), len(arr)))
                arr.insert(idx, op["value"])
        elif kind == "delete":
            if "index" in op:
                arr = resolve_path(obj, path)
                if not isinstance(arr, list):
                    raise ValueError("第 %d 个 op：path 指向的不是数组" % i)
                idx = int(op["index"])
                if not 0 <= idx <= len(arr) - 1:
                    raise ValueError(
                        "第 %d 个 op（delete）：下标 %d 越界 —— 数组长度 %d，合法区间 [0, %d]"
                        "；用 paths / dump 核对 path" % (i, idx, len(arr), len(arr) - 1))
                del arr[idx]
            else:
                parent, key = resolve_parent(obj, path)
                if isinstance(parent, list):
                    ok = isinstance(key, int) and -len(parent) <= key < len(parent)
                elif isinstance(parent, dict):
                    ok = key in parent
                else:
                    ok = False
                if not ok:
                    raise ValueError(
                        '第 %d 个 op（delete）：键 "%s" 不存在 —— 无法删除'
                        "；用 paths / dump 核对 path" % (i, _fmt_keypath(path)))
                del parent[key]
        else:
            raise ValueError("第 %d 个 op 类型未知: %r" % (i, kind))
    return obj


def audit_itemids(obj, js_refs=None, controls_path=None) -> dict:
    """给文件里每个**注册键** `normalName || itemId` 重建组并定级（**只两级**），给出候选清单与两种修法。

    判据：
      ① 分组键 = **注册键** `normalName || itemId`（normalName 优先、空串视同缺失）——
         各自有唯一 normalName 的同名节点**天然分到不同组**（不再需要"豁免"）。
      ② 节点集纳入「只有 normalName、没有 itemId」的节点（B2）。
      ③ 组内 ≥2：该注册键**已被事件 JS 引用 → error**；未被引用 → **benign**（`warn` 级已取消）。

    返回 dict：nodes / js_refs / groups / errors / warns / n_benign
    """
    if js_refs is None:
        js_refs = js_refs_of(obj)
    # 判定"是否被引用"用**未过滤**集合：名字既已确认是文件内的控件名，
    # 就不该再被 `_APP_REF_RESERVED`（为区分方法名而设）滤掉 —— 否则 `store`/`add`/`items`/`id` 会漏判。
    refs_all = js_refs_of(obj, filtered=False)
    nodes = [(n, t, cfg, p, anc) for n, t, cfg, p, anc, _c, _k in _iter_controls(obj)
             if registry_key(cfg) is not None]
    # 去重集合 = 全文件所有 `itemId` ∪ 所有非空 `normalName`（B3：`taken` 换口径）
    taken_all: set = set()
    for _n, _t, _cfg, _p, _a in nodes:
        for _v in (_cfg.get("itemId"), _cfg.get("normalName")):
            if isinstance(_v, str) and _v:
                taken_all.add(_v)
    field_ty = set(field_types(controls_path))
    nn_ty = set(normalname_types(controls_path))
    by_key: dict = {}
    for it in nodes:
        by_key.setdefault(registry_key(it[2]), []).append(it)

    groups = []
    for name, items in sorted(by_key.items()):
        if len(items) < 2:
            continue
        types = {x[1] for x in items}
        # 运行时模块根级控件有 `app._X` **孪生键**（服务端生成：`app.X = app._X = …`）；
        # `app._X` 抽名会带下划线 ⇒ 只按原名判就**看不见这条引用**，⑦ 会把该判 error 的组判成 benign。
        # 前提：真实控件名以 `_` 开头的情况 = 0（全量实测）⇒ `_名字` 只可能是某控件 `名字` 的配置孪生体；
        # 若将来真出现名为 `_w` 的控件，两种解释会撞，届时再收紧。
        referenced = (name in refs_all) or ("_" + name in refs_all)
        have_nn = [isinstance(x[2].get("normalName"), str) and x[2].get("normalName") for x in items]

        # 措辞按组成分：纯列控件 / 非 JS 标识符 / 纯取值控件 / 含列控件的跨类型 / 其它
        if types <= _IID_COL_TYPES:
            head = "列控件注册键重名（取数走 `<grid>.getSelection(0).data.*`）"
        elif not _IID_JS_IDENT_RE.match(name):
            head = "注册键不是合法 JS 标识符（含中文/空格/点等）"
        elif types <= field_ty:
            miss = [i + 1 for i, x in enumerate(have_nn) if not x]
            head = "字段控件注册键重名、normalName %s" % (
                ("缺失的序号 %s" % miss) if miss else "彼此重复")
        elif types & _IID_COL_TYPES:
            head = ("**跨类型同名冲突**（组内含列控件：%s）—— 列本身可重名，"
                    "但它与另一种控件撞了同一个注册键" % "/".join(sorted(types)))
        else:
            head = "应唯一的类型（按钮/面板/数据承载…）注册键重名"

        if referenced:
            level = "error"
            reason = (head + "，且该注册键**已被事件 JS 引用**。框架注册键是 `normalName || itemId`、"
                      "是**普通赋值**（后注册的覆盖先注册的），且**任一重复项销毁时会把整个名字删掉**"
                      "（`unregister` 里 `delete`），所以 `app.%s` 随时可能不是你要的那个" % name)
            short = "注册键重名且被事件 JS 引用 —— `app.%s` 取值不确定" % name
        else:
            level = "benign"
            reason = head + "，但未被事件 JS 引用 —— 实践中无害（老代码可暂留，新代码宜区分）"
            short = "注册键重名但未被 JS 引用"

        # 修法 A：补/改 `normalName`（只补「缺」的，不动 itemId —— 零破坏）
        fix_nn = []
        if any(not x for x in have_nn):
            taken_nn = set(taken_all)
            for i, (n, t, cfg, p, anc) in enumerate(items):
                if isinstance(cfg.get("normalName"), str) and cfg.get("normalName"):
                    continue
                own = cfg.get("itemId") or name
                s, why = suggest_normalname(own, cfg, anc, taken_nn)
                taken_nn.add(s)
                fix_nn.append({"index": i + 1, "type": t, "suggest": s, "why": why,
                               "type_ok": t in nn_ty,
                               "path": p + ["configs", "normalName"]})
        # 修法 B：改 `itemId`（#1 保持原名，动 #2 起；须同步改 JS 里的引用）
        # `taken` = 全文件所有 `itemId` ∪ 所有非空 `normalName` ∪ 本组已建议值（B3）
        taken = set(taken_all)
        fix_id = []
        for i, (n, t, cfg, p, anc) in enumerate(items):
            if i == 0:
                continue
            own = cfg.get("itemId")
            if not (isinstance(own, str) and own):
                continue        # 只有 normalName 的节点没有 itemId 可改
            s, why = suggest_itemid(own, cfg, anc, taken)
            taken.add(s)
            fix_id.append({"index": i + 1, "type": t, "suggest": s, "why": why,
                           "type_ok": True, "path": p + ["configs", "itemId"]})

        groups.append({
            "name": name, "registryName": name, "level": level, "reason": reason,
            "short": short, "count": len(items), "types": sorted(types), "referenced": referenced,
            "itemIds": sorted({x[2].get("itemId") for x in items
                               if isinstance(x[2].get("itemId"), str) and x[2].get("itemId")}),
            "fix_normalname": fix_nn, "fix_itemid": fix_id,
            "nodes": [{"index": i + 1, "type": t, "path": p, "anc": anc,
                       "ancestor": _anc_str(anc), "hint": _node_hint(cfg),
                       "children": _children_summary(n), "normalName": cfg.get("normalName"),
                       "itemId": cfg.get("itemId")}
                      for i, (n, t, cfg, p, anc) in enumerate(items)],
        })

    order = {"error": 0, "warn": 1, "benign": 2}
    groups.sort(key=lambda g: (order[g["level"]], -g["count"], g["name"]))
    fmt = lambda g: "注册键 %r ×%d（%s）：%s" % (g["name"], g["count"], "/".join(g["types"]), g["short"])
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
            # 生成器产出的建议值一律落在「**可能尚不存在**的键」上（`normalName` / 新 `itemId`）
            # ⇒ 逐条带 `"create": true`，否则会被「新建键需显式放行」的执行契约拒掉
            # （这就是「生成器与执行器脱钩」的检测点：改了执行器、忘了同步生成器，产出就跑不通）。
            ops.append({"op": "set", "path": s["path"], "value": s["suggest"], "create": True})
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
    names = {registry_key(x[2]) for x in rep["nodes"]}

    if args.name:
        # `--name` **也认注册键**（`normalName || itemId`）—— 命中时下面会点明"这是注册键"
        hits = itemid_hits(obj, args.name, by="registry")
        if not hits:
            if args.json:   # 机器可读路径也要给 JSON，别混纯文本
                print(json.dumps({"error": "not_found", "name": args.name,
                                  "message": "找不到注册键（normalName||itemId）== %r" % args.name},
                                 ensure_ascii=False, indent=2))
            else:
                print(f"[FAIL] 找不到注册键（normalName||itemId）== {args.name!r}")
            return 1
        if args.json:
            # 每条候选若被消费方转成 ops，路径末端多半是「建议的新键」⇒ 带 `"create": true`
            # 供其直接复用（与 `--suggest` 产出同口径），免得转出来的 ops 被执行器拒掉。
            # node 项增 `itemId`（消费方拿它无歧义定位，不依赖 `name` 的语义）。
            print(json.dumps(
                [{"index": i + 1, "type": t, "path": p, "ancestor": _anc_str(anc),
                  "hint": _node_hint(cfg), "children": _children_summary(n),
                  "normalName": cfg.get("normalName"), "itemId": cfg.get("itemId"),
                  "create": True}
                 for i, (n, t, cfg, p, anc, _c, _k) in enumerate(hits)],
                ensure_ascii=False, indent=2))
        else:
            if not itemid_hits(obj, args.name):     # 该名字没有任何节点以它为 itemId ⇒ 它是注册键
                print(f"（{args.name!r} 是**注册键**（normalName||itemId），不是 itemId —— "
                      f"组内 itemId: {sorted({h[2].get('itemId') for h in hits if h[2].get('itemId')})}）")
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
    print(f"含注册键的控件 {len(rep['nodes'])} 个 / 去重注册键 {len(names)} 个；"
          f"重名组 {len(groups)} 组 —— error {counts['error']} / benign {counts['benign']}")
    print(f"事件 JS 引用的名字 {len(rep['js_refs'])} 个")
    print(controls_source_line(ctl))

    cols = [(n, cfg) for n, t, cfg, *_ in rep["nodes"] if t in _IID_COL_TYPES]
    if cols:
        ok = sum(1 for _n, c in cols if re.search(r"(_?[Cc][Oo][Ll])$", str(c.get("itemId") or "")))
        print(f"\n--- 命名规范 ---\n  列控件 itemId {len(cols)} 个，带 `_COL`/`Col` 后缀 {ok} 个"
              f"（约定：字段名 + Col，多 grid 时靠父级 itemId 区分）")

    if not groups:
        print("\n（无重名注册键）")
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
        print("  · 只改真正要改的那个：用 `--name <itemId 或注册键>` 看候选清单，"
              "或 ops 里写 `\"@名字#2\"` 点名第 2 个。")
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

    eol = _EOL_CHAR[pick_eol_for_auto(text)] if args.eol == "auto" else _EOL_CHAR[args.eol]

    _out0 = dumps_designer(obj, args.indent, eol)
    canonical = text == _out0
    styles = eol_styles(text)
    n_crlf = text.count(CRLF)
    bare_lf = text.count("\n") - n_crlf
    bare_cr = text.count("\r") - n_crlf
    eol_note = ""
    if args.eol == "auto" and not ANY_EOL_RE.search(text):
        # 「源连一个换行符都没有」时 auto 无从沿用 → 回退 LF（与 expand 同一条规则）。
        # 这类文件（紧凑单行源）在 CRLF 工作区里跑完 patch 会变成 LF 文件，必须说清楚。
        eol_note = "（源无换行符，auto 回退 LF）"
    print(f"源文件: {_byte_len(text)} B | 换行={eol_name(eol)}{eol_note} | "
          f"是否设计器原样排版: {'是（重排后与原文逐字节一致，diff 只含本次改动）' if canonical else '否（重排会顺带规整格式）'}")
    if not canonical:
        # H6：把「非原样排版」具体化 —— 三类改写各给一个整数处数（只提示、不改行为）。
        _ci, _cu, _cn = rewrite_counts(text, _out0)
        print("[note] 本次还会顺带改写：缩进 %d 处 / \\uXXXX 转义 %d 处 / 数字形态 %d 处 "
              "—— 都无语义影响；建议先 --dry-run 看 diff" % (_ci, _cu, _cn))
    if len(styles) > 1:
        # 与 `edit` 对齐：混用换行在源文件里是既有的格式问题，patch 会**静默统一**成一种，
        # 所以这里必须报出来（否则用户只能靠 diff 发现换行被动了）。
        print(f"[warn] 源文件换行混用（{n_crlf} 个 CRLF + {bare_lf} 个裸 LF + {bare_cr} 个裸 CR，"
              f"见 `check` 第 ② 项）：重排后整份统一为 {eol_name(eol)}，diff 会含换行差异")
    if args.indent != 1:
        print(f"[warn] --indent {args.indent} ≠ 设计器缩进（1 个空格）：产出与设计器不一致，"
              f"设计器下次保存会产生整份 diff。除非在做排版复刻实验，否则用默认值")
    if not canonical and not ANY_EOL_RE.search(text):
        print("[warn] 源是紧凑单行形态：重排会把它整份展开成多行（diff 是**整个文件**）。"
              "要把改动压到最小，改用 `edit` 做定点插入")

    try:
        with open(args.ops, "r", encoding="utf-8") as f:
            ops = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 读 ops 失败: {exc}")
        return 2
    if isinstance(ops, dict):
        ops = [ops]

    created, warned = [], []
    try:
        apply_ops(obj, ops, created=created, warned=warned)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "\n" in msg:  # 重名报错带候选清单，原样打印
            print("[FAIL] 应用 ops 失败:")
            print(msg)
        else:
            print(f"[FAIL] 应用 ops 失败: {msg}")
        return 2
    print(f"[ok]   已应用 {len(ops)} 个 op")
    if warned:
        # 中间态：新建键本版仍放行，只预告（默认拒绝在后续版本启用）—— 文案**不写版本号**。
        print("[warn] 本次新建了 %d 个键（本版仍允许；默认拒绝将在后续版本启用）：%s"
              % (len(warned), ", ".join(warned)))
        print('       届时给已存在的键 set 不受影响；新建键请加 "create": true')

    out = dumps_designer(obj, args.indent, eol)
    try:
        if not equivalent(parse_xwl(out), obj):
            print("[FAIL] 重建结果语义不一致，已中止（不写文件）")
            return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 重建结果无法解析，已中止: {exc}")
        return 2
    print(f"[ok]   语义等价比对通过（规范化文本：含键序与值类型） | 变更后 {_byte_len(out)} B "
          f"({_byte_len(out) - _byte_len(text):+d})")

    if args.dry_run:
        import difflib
        if not text.count("\n"):
            # K17：单行源整份就一行，逐行截断 diff 只会打出一行被截断 200 字符的长串（无信息量）
            # ⇒ 改打**一行摘要**，跳过逐行 diff（判据 = stdout 里 diff 段落行数）。
            print("  （单行源：整份重排为多行，diff = 整个文件）")
        else:
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
        if created:
            # A2：只列**带 create** 的新建键；不带 create 的那类走上面的 `[warn]` 预告（两条不混）。
            print('[new-key] 本次将新建 %d 个键（带 "create": true）：%s'
                  % (len(created), ", ".join(created)))
        print("[dry-run] 未写入")
        return 0

    if args.backup:
        bak = args.file + ".bak"
        write_bytes(bak, read_bytes(args.file))
        print(f"备份 -> {bak}")
    else:
        # L1：真跑到写盘却没让工具备份 ⇒ 只提醒一句（**只加输出，不改 rc、不改用法**）。
        print("[warn] 未使用 --backup：本次已直接写盘，出错请用 git checkout -- 回退（建议先 --dry-run 看 diff）")
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
        cfgs["itemId"] = "<必填：工具寻址用（@itemId）>"
        for cand in ("text", "title"):          # 只加该控件**确实允许**的「显示名」键
            if cand in cfg:
                cfgs[cand] = ""
        if args.type == "window":
            # 窗口这两个键**都是非缺省**（缺省分别是「真」与 'hide'），写错代价最大 ——
            # `closeAction=destroy` 时若仍复用实例、第二次打开即空白窗 ⇒ 预填「每次重建」那一档。
            # 纯查询（内嵌 grid 的常驻窗）靠缺省就对，不预填也不会错。
            cfgs["createInstance"] = "false"
            cfgs["closeAction"] = "destroy"
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
        print(f"> 提示：configs 只放上表列出的键（共 {len(cfg)} 个）；注册键（normalName||itemId）必须唯一。")
    return 0


def cmd_paths(args) -> int:
    """列出可编辑字段的位置：sql / totalSql / serverScript / url（给 patch 的 path 用）。"""
    try:
        text, _has_bom, obj = load_xwl(args.file)
    except XwlLoadError as exc:
        print(f"[FAIL] {exc}")
        return 2

    # ⚠️ 用 `_iter_controls`（**控件树语义**）而不是 `iter_nodes` —— 必须与 `patch` 的
    # `@itemId` 寻址**同源**：`iter_nodes` 会下钻 `configs` 内联对象，把那些"幻影控件"
    # 也报成可编辑字段、并推荐 `["@x","configs","sql"]` 这类路径，而 `patch` 解不开
    # （报 `ItemIdError`）。实测那些内联对象全量 1070 个、带 `itemId`/`sql` 的 = 0
    # ⇒ 统一后**不丢任何可编辑字段**。
    iid_count: dict = {}
    for _n, _t, _cfg, _p, _a, _c, _k in _iter_controls(obj):
        _i = _cfg.get("itemId")
        if isinstance(_i, str) and _i:
            iid_count[_i] = iid_count.get(_i, 0) + 1

    rows = []
    for _n, t, cfg, path, _a, _c, _k in _iter_controls(obj):
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

    # 语义等价比对（**规范化文本**，必须过，否则不写盘）
    try:
        if not equivalent(parse_xwl(out), obj):
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
    print(f"[ok]   语义等价比对通过（规范化文本：含键序与值类型） | {_byte_len(out)} B | 换行={eol_name}")

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

    print(f"将追加 index 项 {name!r} → {safe_relpath(jp)}（登记后共 {len(idx)} 项）")
    if args.dry_run:
        print(f"  before: {text.rstrip()[:140]}")
        print(f"  after : {out.rstrip()[:140]}")
        print("[dry-run] 未写入")
        return 0

    bak = jp + ".bak"
    write_bytes(bak, read_bytes(jp))
    write_text(jp, out)
    print(f"备份 -> {bak}")
    print(f"已写入: {jp}")
    print("> index 的顺序 = 设计器导航树里的显示顺序（追加在末尾）。")
    return 0


def cmd_folders(args) -> int:
    """检查 `folder.json`（设计器导航树的目录索引）与实际文件是否一致。

    `folder.json` 形如 `{"hidden":false,"index":[…],"title":"…","iconCls":"…"}`；
    **`index` 里带 `.xwl` 后缀的是文件，不带后缀的才是子目录**。
    新建一个 xwl 之后不登记进所在目录的 `index`，**不登记就看不到** —— 设计器导航树里没有它。

    `--register` **只认文件路径**（给目录会被拒绝：一个目录里可能有好几个文件，工具不知道登记哪个）；
    所在目录还没有 `folder.json` 时**不会替你创建**（会报错退出 2）。
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
        if args.register is not None:
            # 原来这里会**静默忽略** --register、只做只读扫描并以 0 退出 —— 用户以为登记了、其实没有。
            hint = (os.path.join(target, args.register) if args.register
                    else os.path.join(target, "<文件名>.xwl"))
            print(f"[FAIL] --register 要指到具体文件上：给一个目录，工具不知道该登记哪一个。")
            print(f"       正确写法：xwl.py folders {hint} --register")
            return 2
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
        rel = safe_relpath(d, base) if recursive else os.path.basename(d)
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
        print(f"[ok]   {nm} 已登记在 {safe_relpath(jp)} 的 index 第 {pos} 项。")
    else:
        print("[ok]   index 与实际文件一致。")
    if n_unreg and not recursive:
        print(f"\n登记：xwl.py folders {safe_relpath(target)} --register {os.path.basename(target)}")
    if n_unreg:
        print("\n> index 里带 `.xwl` 的是文件、不带后缀的是子目录；顺序 = 导航树显示顺序。")
    return 0


# --------------------------------------------------------------------------- #
# diffguard（相对 git 基线，检测「多行内容被压平」这种静默语义损坏）
# --------------------------------------------------------------------------- #
# 为什么需要它：SKILL.md 2.3 承认——把「反斜杠 + 换行」直接删掉（"合并行"）之后，
# 文件**依然是合法 JSON**、`check` 七项全绿、`node --check` 也可能返回 0，
# 唯一的发现手段是人工 `git diff`。这是本工具唯一"没有自动化防线"的损坏类型。
#
# 判据为什么是**两个条件**而不是"续行符变少"：
#   · 合法地删掉一段多行 JS / 删一个控件，续行符**也会**净减少 —— 只看数量必然误报；
#   · 压平的真正指纹是「**原来好几行的内容挤进了同一行**」⇒ **最长行长度暴增**。
#   两者同时成立才判疑似。实测对照：压平 → 最长行 96 → 412（+316，3.3 倍）；
#   而"删掉一段多行 JS" → 续行符减少但最长行长度基本不变 ⇒ 不报。
_FLAT_RATIO = 1.5      # 最长行至少变成原来的 1.5 倍
_FLAT_DELTA = 40       # 且绝对增量至少 40 字符（避免短行上比值虚高）


def _merged_line_hits(head_text: str, wd_text: str) -> list:
    """精确判据：找出「基线里**连续多行**被拼成了工作区的某一行」的位置。

    这是"压平"的**定义本身** —— 压平就是删掉「续行符 + 换行」，
    于是基线里 `line_i\\` `line_{i+1}\\` … `line_j` 会原样变成工作区的一条物理行：
        工作区该行 == (line_i 去掉续行符) + (line_{i+1} 去掉续行符) + … + line_j

    返回 [(起始行号, 结束行号, 工作区行号, 该行开头), …]（行号均 1-based）。

    为什么不能只用「最长行长度」当指纹（这是本函数存在的理由，实测两个漏报面）：
      · 被压平的内容若**短于文件里已有的最长行** ⇒ 最长行纹丝不动 ⇒ 完全看不见；
      · 压平增量 < 最长行 × 0.5 ⇒ 被 ratio 门槛吃掉。
    这两个漏报面的实测数字见 SKILL.md §2.6（这里只留结论，不拷贝第二份）。

    为什么不会误报「合法删减」与「单行改长」：
      · 起点必须是**以续行符结尾**的行（只有多行字符串内部的续行才长这样，
        JSON 结构行永远不会）；
      · 必须**至少跨过一条续行**（拼接 ≥2 行）才判；
      · 拼接结果必须与工作区的**某条物理行逐字相同** —— 删行会少内容、单行改长会多内容，
        两者都拼不出这条等式。
    """
    hl = ANY_EOL_RE.split(head_text)
    wl = ANY_EOL_RE.split(wd_text)
    if not hl or not wl:
        return []
    wset = set(wl)
    wset_r = {l.rstrip() for l in wl}
    wpos = {}
    for k, l in enumerate(wl, 1):
        wpos.setdefault(l, k)
    max_w = max((len(l) for l in wl), default=0)

    hits = []
    n = len(hl)
    for i in range(n - 1, -1, -1):          # 倒序：便于"跳过已合并组"的剪枝
        if not hl[i].endswith("\\"):
            continue                        # 起点必须是续行（字符串内部）
        acc = hl[i][:-1]                    # 去掉续行符
        for j in range(i + 1, n):
            acc += hl[j][:-1] if hl[j].endswith("\\") else hl[j]
            if len(acc) > max_w:
                break                       # 工作区不可能有这么长的行
            key = acc if acc in wset else (acc.rstrip() if acc.rstrip() in wset_r else None)
            if key is not None:
                hits.append((i + 1, j + 1, wpos.get(acc, wpos.get(acc.rstrip(), 0)),
                             acc[:70]))
                break
            if not hl[j].endswith("\\"):
                break                       # 组到头了（这一行没有续行符）
    return hits


def _norm_lf(text: str) -> str:
    """换行归一成 LF —— 只用于"两侧是否同一份内容"的比较。

    必须归一：git index 存 LF、工作区可能是 CRLF（`core.autocrlf`），
    不归一会把"仅仅换了行尾"误报成"内容变了"。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _longest_line(text: str) -> tuple:
    """返回 (最长行的长度, 该行的 1-based 行号)。"""
    best, best_no = 0, 0
    for i, ln in enumerate(ANY_EOL_RE.split(text), 1):
        if len(ln) > best:
            best, best_no = len(ln), i
    return best, best_no


@functools.lru_cache(maxsize=None)
def _git_prefix(cwd: str):
    """返回 `cwd` **相对仓库根**的路径（仓库根处为 `""`）；不在仓库 / 调不到 git ⇒ `None`。

    **为什么不让 Python 自己算相对路径**：`git rev-parse --show-toplevel` 给出的绝对
    路径与 `os.path.abspath` **不一定同源**。Windows 上 `TEMP` 常是 8.3 短名
    （`C:\\Users\\RUNNER~1\\…`），git 却把仓库根归一成长名 —— 前缀对不上时
    `os.path.relpath` 会算出 `..\\..\\XWL_SH~1\\…` 这种"绕行路径"。
    实测：那种路径以 `..` 开头，被 `_git_show` 当成"逃逸"**静默跳过**，
    于是 diffguard 整组断言在 `windows-latest` 上全挂（ubuntu 正常）。
    让 **git 自己报**相对路径之后，盘符 / 短名 / MSYS 风格 / 大小写全都不再相关。

    按 `cwd` 缓存：批量跑时同一目录的文件只起一次 git 进程。
    """
    try:
        p = subprocess.run(["git", "rev-parse", "--show-prefix"], cwd=cwd,
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return p.stdout.decode("utf-8", "replace").strip()


@functools.lru_cache(maxsize=None)
def _git_has_rev(rev: str, cwd: str) -> bool:
    """`rev` 在这个仓库里能否解析；调不到 git / 不在仓库 ⇒ `False`。

    按 `(rev, cwd)` 缓存：`diffguard` 会遍历整个目录，而 `rev` 对同一仓库是常量 ——
    不缓存的话每个文件都要多起一次 git 进程。
    """
    try:
        p = subprocess.run(["git", "rev-parse", "--verify", "--quiet", rev],
                           cwd=cwd, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


def _git_show(rev: str, rel: str, cwd: str, in_repo: bool):
    """取 `<rev>:<rel>` 的内容。返回 (ok, bytes|None, 失败原因|None)。

    找不到 git / 不在仓库 / 路径不在该 rev 里 —— 一律转成"跳过并说明"，
    因为这几件事都不是使用者的用法错误。
    `--rev` **本身不存在**是例外：那是用法错误，用哨兵 `"BADREV"` 报给调用方转成 rc=2。
    """
    if not in_repo:
        return False, None, "不在 git 仓库里（或调不到 git）"
    if not rel or rel.startswith(".."):     # 纯防御：rel 由 git 给出，正常不会含 ..
        return False, None, "路径不在该仓库内"
    try:
        if not _git_has_rev(rev, cwd):
            return False, None, "BADREV"
        got = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=cwd,
                             capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, None, f"git show 失败（{type(exc).__name__}）"
    if got.returncode != 0:
        return False, None, f"在 `{rev}` 里没有这个文件（新增文件？）"
    return True, got.stdout, None


def _expand_targets(targets: list) -> tuple:
    """把入参（文件或目录）摊平成 .xwl 文件清单。返回 (files, errors)。"""
    files: list[str] = []
    errors: list[str] = []
    for t in targets:
        if os.path.isdir(t):
            for dp, dn, fn in os.walk(t):
                dn[:] = [d for d in dn if d not in (".git", "__pycache__")]
                files.extend(os.path.join(dp, f) for f in sorted(fn) if f.endswith(".xwl"))
        elif os.path.isfile(t):
            files.append(t)
        else:
            errors.append(f"读不到 {t}")
    return files, errors


def cmd_diffguard(args) -> int:
    """相对 git 基线，检测工作区文件里**多行内容被压平**的迹象。

    它回答的是一个只有 git 才能回答的问题：「这份文件相对上次提交，有没有
    **悄悄把多行字符串挤成一行**」。这类改动**格式校验查不出**（压平后自洽），
    所以是 `check` 之外的一道独立防线（见 SKILL.md 2.3）。

    默认只告警（rc=0）；`--strict` 时才把"疑似压平"当成失败（rc=1），供 CI / pre-commit 用。
    """
    files, errors = _expand_targets(args.targets)
    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        return 2
    if not files:
        print(f"[FAIL] 没找到可检查的 .xwl（{len(args.targets)} 个入参里没有文件）")
        return 2

    n_suspect = n_skip = n_clean = 0
    for path in files:
        name = os.path.basename(path)
        try:
            wd_text, _bom = decode(path)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"=== diffguard: {safe_relpath(path)}")
            print(f"  [note] 跳过：读不出 UTF-8 文本（{getattr(exc, 'strerror', None) or exc}）")
            n_skip += 1
            continue

        abs_path = os.path.abspath(path)
        cwd = os.path.dirname(abs_path) or "."
        # 仓库内路径 = 「仓库根 → cwd」由 **git 自己**给出（带尾斜杠） + 文件名。
        # `basename` 只涉及同一个字符串，不可能算出 `..`；盘符/短名一概不相关。
        prefix = _git_prefix(cwd)
        rel = f"{prefix}{os.path.basename(abs_path)}" if prefix is not None else ""
        ok, head_bytes, why = _git_show(args.rev, rel, cwd, prefix is not None)

        print(f"=== diffguard: {safe_relpath(path)}")
        if why == "BADREV":
            print(f"[FAIL] 基线 `{args.rev}` 不存在（或不是一个能解析的 revision）")
            return 2
        if not ok:
            print(f"  [note] 跳过：{why} —— 无法与基线 `{args.rev}` 比对")
            n_skip += 1
            print("  -> 跳过")
            continue

        try:
            head_text = head_bytes.decode("utf-8")
        except UnicodeDecodeError:
            print(f"  [note] 跳过：`{args.rev}` 里的版本不是 UTF-8")
            n_skip += 1
            print("  -> 跳过")
            continue

        if _norm_lf(head_text) == _norm_lf(wd_text):
            print("  [ok]   与基线逐字节一致（忽略行尾差异），无压平迹象")
            n_clean += 1
            print("  -> OK")
            continue

        c_head, c_wd = count_cont(head_text), count_cont(wd_text)
        m_head, _n1 = _longest_line(head_text)
        m_wd, line_no = _longest_line(wd_text)
        n_head = len(ANY_EOL_RE.split(head_text))
        n_wd = len(ANY_EOL_RE.split(wd_text))

        # 判据一（精确，主判据）：基线里连续多行被拼成了工作区的某一行 —— "压平"的定义本身
        hits_all = _merged_line_hits(head_text, wd_text)
        # ⚠️ **前置必要条件**："压平"的定义就是"多条物理行并成一条" ⇒ **续行符数与行数至少要有一个
        #    减少**。缺了这条，`}` / `');'` 这类**极短行**的"内容恰好等于基线相邻两行的拼接"会被判成
        #    压平 —— 实测在**真实历史版本**上误报，且同一条输出里三个计数一个都没变
        #    （`行数 4470 → 4470` 在数学上就排除了压平），甚至同时报两条方向相反的命中。
        pressed = (c_wd < c_head) or (n_wd < n_head)
        hits = hits_all if pressed else []
        moved = bool(hits_all) and not pressed
        # 判据二（粗筛，补充）：续行符净减少 **且** 最长行显著变长。
        # 保留它是因为它能抓到"精确判据拼不出等式"的形态（例如压平**同时**还改了内容）；
        # 但它单独用会有两个漏报面（见 `_merged_line_hits` 注释），所以只当补充。
        grew = m_wd >= max(m_head * _FLAT_RATIO, m_head + _FLAT_DELTA)
        coarse = c_wd < c_head and grew
        suspect = bool(hits) or coarse

        stat = (f"续行符 {c_head} → {c_wd}（{c_wd - c_head:+d}）| "
                f"最长行 {m_head} → {m_wd} 字符 | 行数 {n_head} → {n_wd}")
        if suspect:
            n_suspect += 1
            why = "精确命中" if hits else "粗筛命中"
            print(f"  [warn] 疑似把多行内容压平（{why}）—— {stat}")
            for a, b, k, head70 in hits[:3]:
                print(f"         基线第 {a}–{b} 行（{b - a + 1} 行）被合并成工作区第 {k} 行："
                      f"{head70!r}")
            if len(hits) > 3:
                print(f"         （另有 {len(hits) - 3} 处精确命中）")
            if not hits:
                print(f"         第 {line_no} 行突然变长，开头是："
                      f"{wd_text.splitlines()[line_no - 1][:70]!r}")
            print("         这类改动**格式校验查不出**（压平后仍是合法 JSON）："
                  "`check` 会全绿、`node --check` 也可能返回 0，但字符串里的换行已经没了。")
            print(f"         复核：`git diff -w {safe_relpath(path)}`；确认是误改就 "
                  f"`git checkout -- {safe_relpath(path)}`")
            print("  -> FAIL" if args.strict else "  -> OK（仅告警；加 `--strict` 可让它阻塞）")
        else:
            n_clean += 1
            print(f"  [ok]   与基线有差异，但无压平迹象 —— {stat}")
            if moved:
                print(f"  [note] 另有 {len(hits_all)} 处「内容与基线相邻几行的拼接相同」，"
                      f"但**续行符与行数都没减少** ⇒ 判为**内容移动/复制，不是压平**"
                      f"（压平必然让行数或续行符减少），不计入告警")
            if c_wd < c_head and not grew:
                print("         续行符变少而最长行没变长 ⇒ 像是**正常删减**（删多行代码 / 删控件），"
                      "不是「把多行合并成一行」")
            print("  -> OK")

    print(f"=== 结果: {'FAIL' if (n_suspect and args.strict) else 'ALL OK'}"
          f"（疑似压平 {n_suspect} / 无迹象 {n_clean} / 跳过 {n_skip}）")
    if n_suspect and not args.strict:
        print("> 有疑似压平项，但默认只告警（rc=0）。要让它阻塞请加 `--strict`。")
    # 退出码优先级（`--strict` 下）：**可疑压平 > 跳过**
    #   理由：可疑压平是"真的可能改坏了"，而跳过只是"这个文件比不了"；
    #   若让跳过优先，任何一次带新增文件的提交都会让 CI 直接红，`--strict` 就没法用在 CI 里了。
    #   只有"一个文件都没比成"时才算前置条件不满足（rc=2）。
    if n_suspect and args.strict:
        return 1
    if n_skip and args.strict and not (n_clean + n_suspect):
        print("[FAIL] --strict 下至少要有一个文件能比对：本次全部跳过（"
              f"{n_skip} 个），先把原因解决掉（git 仓库 / 基线里有该文件）")
        return 2
    if n_skip and args.strict:
        print(f"[note] 另有 {n_skip} 个文件无法比对（已跳过）—— "
              "`--strict` 下这不阻塞，但别把它们当成「已检查通过」")
    return 0


# --------------------------------------------------------------------------- #
# sqlrefs（SQL 文件：serverScript ↔ dataprovider 的引用检查）
# --------------------------------------------------------------------------- #
_HASH_RE = re.compile(r"\{#([^}]{1,64})#\}")
_PARAM_RE = re.compile(r"\{\?([^}]{1,64})\?\}")
_SETATTR_RE = re.compile(r"""setAttribute\(\s*(['"])(.*?)\1""")
# 框架内置变量前缀的**内置兜底**。有文件来源的那部分由 `builtin_prefixes()` 从
# `wb/system/var.json` 顶层键推导后并进来 —— **必须取并集**：
#   · 只认内置 ⇒ 工程若在 `var.json` 加自定义命名空间（如 `myapp.`），`{?myapp.x?}` 会被判成 miss（假阳）；
#   · 只取文件 ⇒ 实测 8 个工程里只有 7 个有 `var.json`，会在整整一个根上崩。
# `Str.` 来自框架类 `Str.java`（`Str.format(request, key)`），**没有**工程文件来源
# （`wb/script/locale/**` 与 `wb/system/language.json` 里没有任何 `Str.*` 形态的键）⇒ 只能内置。
_BUILTIN_PREFIX = ("sys.", "Str.")

# 「类型前缀」白名单 —— 权威来源是框架 `DbUtil.sqlTypes` 的 **36 个 JDBC 类型名**，大小写不敏感。
# ⚠️ 只有 `params` 用它剥前缀；`sqlrefs` **绝不使用** —— `{#…#}` 是框架变量、没有类型前缀这回事，
#    套上会把 `{#timestamp.x#}` 误剥。
# ⚠️ 不要混进 `wb/system/database/types.json` 里那 7 个 DDL 名字：`DATETIME` **不在** JDBC 表里，
#    误剥会把 `{?datetime.start?}` 改成 `start`，而框架 `getFieldType("datetime")` 返回 null、
#    仍按整名 `datetime.start` 取 ⇒ 两侧不一致。
_SQL_TYPE_NAMES = frozenset("""
    BIT TINYINT SMALLINT INTEGER BIGINT FLOAT REAL DOUBLE NUMERIC DECIMAL CHAR VARCHAR
    LONGVARCHAR DATE TIME TIMESTAMP BINARY VARBINARY LONGVARBINARY NULL OTHER JAVA_OBJECT
    DISTINCT STRUCT ARRAY BLOB CLOB REF DATALINK BOOLEAN ROWID NCHAR NVARCHAR LONGNVARCHAR
    NCLOB SQLXML
""".split())


def builtin_prefixes(start_file: str | None = None) -> tuple:
    """框架内置变量前缀白名单 = `wb/system/var.json` 顶层键推导 ∪ 内置兜底。"""
    pref = set(_BUILTIN_PREFIX)
    if start_file:
        vp = _find_upward(start_file, os.path.join("system", "var.json"))
        if vp:
            try:
                v = json.load(open(vp, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                v = None
            if isinstance(v, dict):
                pref |= {"%s." % k for k in v if isinstance(k, str) and k}
    return tuple(sorted(pref))


def strip_sql_type_prefix(name: str, provided) -> str:
    """`{?timestamp.endDate?}` → `endDate`（只在确定是类型前缀时才剥）。

    三条规则都是实测定的：
    ① **只按 36 个 JDBC 类型名剥** —— 不复刻框架源码里"纯数字也算类型"那条分支；
    ② **精确匹配优先**：原名已在 `provided` 里就**不剥**（工程里确实存在带点的参数名），
       否则会出现"剥前缀反而新增 miss"；
    ③ 大小写不敏感（框架是 `equalsIgnoreCase`）。
    """
    if "." not in name or name in provided:
        return name
    head, _sep, tail = name.partition(".")
    if tail and head.upper() in _SQL_TYPE_NAMES:
        return tail
    return name


def iter_nodes(obj):
    """产出 (type, configs, path) 三元组（**下钻 `configs`**）。

    ⚠️ **用途边界**：它会把 `configs` 里的**内联配置对象**也当成"节点"吐出来 ——
    那些对象**没有 `itemId` / `sql`**（实测全量 1070 个、可编辑字段 0 个），
    对 `patch` 的 `@itemId` 寻址来说它们是**幻影控件**。
    ⇒ 只在确实需要看 `configs` 内嵌套结构时使用（如 `sqlrefs`）；
    一切"控件"判断请用 `_iter_controls`（见其 docstring 的用途边界）。
    """
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
    # 内置前缀白名单**按本文件所在工程推导**（`wb/system/var.json` 顶层键 ∪ 内置），
    # 而不是拿硬编码的常量 —— 工程自定义命名空间也要认（见 `builtin_prefixes`）。
    prefixes = builtin_prefixes(args.file)
    missing = []
    for name, cnt in sorted(used.items(), key=lambda kv: -kv[1]):
        if name in provided:
            print(f"  [ok]   {{#{name}#}} × {cnt}  ← serverScript 已提供")
        elif name.startswith(prefixes):
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
# 页面把值送出去有**两条通路**（框架源码实测，完整规则见 references/sql-fragments.md）：
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
# ⚠️ app-ref 正则**不在本段另立副本** —— 直接用 `js_refs_of` 侧共享的
#   `_APP_REF_BARE` / `_APP_REF_GET` / `_APP_REF_BRACKET`（F14 同源化）。
#   曾因这里各存一份，导致 `app['名']` 在 `params` 下认不出、与 `itemids` 判定漂移。
_OBJ_KEY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:")
_REQ_URL_RE = re.compile(r"url\s*:\s*['\"]([^'\"]*m\?xwl=[^'\"]*)['\"]")
# 有 getValue() 的控件 = 会被 out 收集的。权威来源是 wb/system/controls.json
# （general.type 以 `Ext.form.field.` 开头的那些）；这里是内置兜底名单。
_FIELD_FALLBACK = ("check", "combo", "date", "datetime", "displayfield", "file",
                   "hidden", "htmleditor", "number", "picker", "radio", "text",
                   "textarea", "time")
_SKIP_KEYS = {"out", "add", "callback", "scope", "success", "failure", "async",
              "url", "method", "bean", "params", "waitMsg", "timeout", "extraParams"}


def field_types(controls_path: str | None = None) -> tuple:
    """取值控件类型集合 = **注册表推导 ∪ 内置兜底**。

    ⚠️ **必须并集，只取注册表会出现「能找到注册表反而更不准」** —— 实测同一页面：
    有注册表 → 页面送出 5 个 / miss 40；用内置兜底 → 32 个 / miss 14。
    根因：那个工程把 `text` 注册成 `Ext.form.field.*` 之外的命名空间
    ⇒ 纯注册表推导会把**最高频的取值控件整类丢掉**，
    容器内 text 控件的 itemId 全部从 `provided` 消失 ⇒ 凭空多出假阳 miss。

    语义论证：这份清单回答的是"**某类型节点出现时算不算取值控件**"，
    而不是"该工程有没有这个控件" ⇒ 某类型不在页面里时清单有没有它对结论毫无影响
    ⇒ **union 无副作用**，而"更宽的清单"只会**少报** miss（安全方向）。
    """
    ids: set[str] = set(_FIELD_FALLBACK)
    if controls_path:
        try:
            reg = json.load(open(controls_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            reg = None
        if reg is not None:

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
    return tuple(sorted(ids))


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


def _app_refs_in(expr: str) -> list:
    """从一段 JS 表达式里取所有 `app.<名>` / `app['名']` 引用（**与 `js_refs_of` 同源**）。

    F14：`params` 侧不再自带正则副本 —— 复用 `js_refs_of` 用的同一批符号，保证
    「`params` 认定被引用的容器」与「`itemids` 认定被引用」对 `app['名']` 的判断一致。
    """
    return _APP_REF_BARE.findall(expr) + _APP_REF_BRACKET.findall(expr)


def find_transfers(js: str, field_set) -> list[tuple]:
    """从一段 JS 里提取传参点。

    返回 [(通路, 容器 itemId 列表, 显式参数名列表, 原文片段)]，
    通路 ∈ {"out", "params=Wb.getValue", "params=对象"}。
    """
    js = strip_js_comments(js)
    found: list[tuple] = []
    for m in _OUT_KEY_RE.finditer(js):
        expr = read_expr(js, m.end()).strip()
        conts = _app_refs_in(expr)
        if conts:
            found.append(("out", conts, [], expr))
    for m in _PARAMS_KEY_RE.finditer(js):
        expr = read_expr(js, m.end()).strip()
        if _GETVALUE_RE.match(expr):
            conts = _app_refs_in(expr)
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
    # H11：注册表来源 —— 与 `itemids` / `check ⑦` 逐字同一句（三处复用 controls_source_line）
    print(controls_source_line(getattr(args, "controls", None)))

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
            line += (f"\n      url={url!r}（非 m?xwl：可能是 Java bean / 其它数据源，"
                     f"也可能是「捷径 url」—— 框架支持、表在 wb/system/url.json；本工具不解析捷径）")
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
                # 先按**注册键** `normalName || itemId` 找容器：同一页多个 toolbar 常共用
                # itemId="tbar"、靠 normalName 区分，而事件 JS 引用的正是 normalName
                # ⇒ 只按 itemId 找会假报「找不到容器」、进而在下面凭空多出假「缺来源」。
                locs = [(h[5], h[6]) for h in itemid_hits(obj, a, by="registry")]
                if not locs:
                    locs = _find_all_by_itemid(obj, a)   # itemId 兜底（硬要求，别删）
                if not locs:
                    detail.append(f"app.{a} → [warn] 页面里找不到注册键（normalName||itemId）== {a!r} 的容器")
                    continue
                dup = f"（同注册键 ×{len(locs)}，取第一个）" if len(locs) > 1 else ""
                ids = _collect_name_islands(obj, locs[0][0][locs[0][1]], field_set)
                provided |= set(ids)
                detail.append(f"app.{a}{dup} → 容器内取值控件 {ids or '（无）'}")
            print(head + "; ".join(detail))
        else:
            provided |= set(keys)
            print(head + f"显式参数名 {keys}")
        print(f"      {'':16s} 原始: {raw[:150]}")

    # ---- D-a′：把 **store 自身 `configs.params`** 的键并入 `provided` ----
    # 嵌入点必须在传参点循环**之后**、`miss` **之前**：否则输出自相矛盾 ——
    # 上面那行写着"自身params配置(优先级最高)"，下面却说"未发现来源"。
    # 形态实测（全量 32519 个 store）：缺失 22755 / **对象字面量字符串** 9752 /
    # 其它字符串 12（全是 `'20'`）/ dict 0 / list 0 ⇒ **只按字符串形态解析**，
    # 只认 `{…}`、其余忽略并 note（`'20'` 这类天然被 `obj_keys` 挡掉）。
    store_keys: set[str] = set()
    ignored_store_params: list[tuple] = []
    for cfg in stores:
        raw_p = cfg.get("params")
        if not isinstance(raw_p, str) or not raw_p.strip():
            continue
        s = raw_p.strip()
        if s.startswith("{") and s.endswith("}"):
            store_keys |= set(obj_keys(s[1:-1]))
        else:
            ignored_store_params.append((cfg.get("itemId"), s))
    provided |= store_keys

    # ---- D-c′：`needed` **按来源分桶** ----
    # 两个来源若合并成一个 set，来源信息在合并那一刻就丢了，"单列展示"做不出来。
    # `need_req` = **请求级参数**：`serverScript` 的 `{?名?}` 与 `app.get(名)` ——
    # 框架 `Query.java` 一律 `WebUtil.fetchObject(request, paraName)`，值都从 request 取，
    # 与写在哪个字段无关 ⇒ 保留在 `needed` 里（剔除会把真实风险静默掉）。
    need_sql: set[str] = set()      # dataprovider 的 sql / totalSql 里的 `{?名?}`
    need_req: set[str] = set()      # serverScript 的 `{?名?}` / `app.get(名)`
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
                g, hs = _APP_REF_GET.findall(ss), _PARAM_RE.findall(ss)
                print(f"  serverScript: app.get(名)={g or []}  {{?名?}}={hs or []}")
                need_req |= set(g) | set(hs)
            if t == "dataprovider":
                for k in ("sql", "totalSql"):
                    if isinstance(cfg.get(k), str):
                        ps = _PARAM_RE.findall(cfg[k])
                        print(f"  {k}: {{?名?}} = {ps or []}")
                        need_sql |= set(ps)

    needed = need_sql | need_req
    if not needed:
        print("\n（SQL 侧没有 {?…?} / app.get，跳过交叉核对）")
        return 0

    # 真白名单：`sys.*` / `Str.*`（以及工程在 `wb/system/var.json` 里自定义的命名空间）
    # **不计 miss** —— 它们由框架往 request 里塞，不需要页面提供。
    prefixes = builtin_prefixes(args.file)
    # 类型前缀只在**确属类型名**（36 个 JDBC 名）时才剥，且**精确匹配优先**
    # （原名已在 provided 里就不剥）。两侧用**同一套剥完的名字**比对 ——
    # 否则会出现「SQL 需要 `timestamp.x`」与「页面送了 `x`、SQL 未用到」同时出现在屏幕上。
    need_cmp = {strip_sql_type_prefix(n, provided) for n in needed
                if not n.startswith(prefixes)}
    miss = sorted(n for n in need_cmp if n not in provided)
    extra = sorted(n for n in provided if n not in need_cmp)
    print("\n=== 交叉核对 ===")
    print(f"  页面送出 {len(provided)} 个: {sorted(provided)}")
    if store_keys:
        print(f"    └ 其中 **store 自身 params 提供 {len(store_keys)} 个**: {sorted(store_keys)}")
    if ignored_store_params:
        print(f"    [note] {len(ignored_store_params)} 个 store 的 `params` 不是对象字面量，已忽略: "
              + ", ".join("itemId=%s %r" % (i, v) for i, v in ignored_store_params[:3]))
    print(f"  SQL 侧需要 {len(needed)} 个 —— 按来源分桶：")
    print(f"    · dataprovider sql/totalSql 的 `{{?名?}}`: {sorted(need_sql)}")
    print(f"    · serverScript 的 `{{?名?}}` / `app.get(名)`（**请求级参数**）: {sorted(need_req)}")
    if miss:
        print(f"  [warn] SQL 需要但页面未发现来源: {miss}")
        print("         可能来自：上级容器 / 其它请求（Wb.request）/ sys.* 等框架内置变量；"
              "**由调用方页面传入**的那一类本工具不核对")
        print("         能力边界：只看**这一个页面**静态可见的来源。`Wb.open({params})` 传进本页的键"
              "写在调用方页面里，要核对请到调用方页面去跑")
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
# `--help` 纪律（与 references/workflow-notes.md 的落点分流表同源）：
#   1. `help=` 保持 ≤1 短行；细节进参数 help 或 `epilog`；
#   2. `epilog` 不进顶层 `--help` ⇒ 用法示例一律走 `epilog`；
#   3. 永不为"承载内容"新增选项（那会成为新的对外能力）；
#   4. 超出的长示例 → `references/` 或 `examples/README.md`（已在）。
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xwl.py", description="WebBuilder .xwl 文件处理工具"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="七项校验：格式五项 + 事件 JS 语法 + 注册键重名分级")
    c.add_argument("files", nargs="+", help="一个或多个 .xwl 文件")
    c.add_argument("--node", help="node 可执行文件路径")
    c.add_argument("--no-js", action="store_true", help="跳过事件 JS 语法校验")
    c.add_argument("--no-itemid", action="store_true", help="跳过注册键重名分级检查")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("edit", help="文本级安全替换（锚点按目标换行归一、断言出现次数、拍平多行时警示）")
    e.add_argument("target", help="要就地修改的 .xwl 文件")
    e.add_argument("--old-file", required=True, help="锚点文本文件（要替换掉的那段）")
    e.add_argument("--new-file", required=True, help="替换文本文件（替换成的内容）")
    e.add_argument("--expect", type=int, default=1, help="期望锚点出现次数（默认 1）")
    e.add_argument("--dry-run", action="store_true", help="不写盘，只报变更后长度")
    e.add_argument("--backup", action="store_true", help="写 <target>.bak")
    e.add_argument("--node", help="node 可执行文件路径（缺省从 NODE_BIN 与 PATH 找）")
    e.add_argument("--no-js", action="store_true", help="跳过写盘后的事件 JS 语法校验")
    e.set_defaults(func=cmd_edit)

    pt = sub.add_parser("patch", help="结构级编辑：改对象 + 按设计器规则整份重建（推荐）。"
                                      "产出**永远是设计器原样**（所以没有 --safe）",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        epilog="ops.json 是操作数组，path 是「键 / 数组下标」的列表，四种 op：\n"
                               "  [\n"
                               "    {\"op\": \"set\", \"path\": [\"title\"], \"value\": \"新标题\"},\n"
                               "    {\"op\": \"set\", \"path\": [\"@dataprovider\", \"configs\", \"sql\"],\n"
                               "     \"value\": \"select 1 from dual\"},\n"
                               "    {\"op\": \"insert\", \"path\": [\"children\"], \"index\": 0,\n"
                               "     \"value\": {\"configs\": {\"itemId\": \"firstBtn\"}, \"expanded\": false,\n"
                               "               \"children\": [], \"type\": \"button\"}},\n"
                               "    {\"op\": \"append\", \"path\": [\"children\", 0, \"children\"],\n"
                               "     \"value\": {\"configs\": {\"itemId\": \"newBtn\"}, \"expanded\": false,\n"
                               "               \"children\": [], \"type\": \"button\"}},\n"
                               "    {\"op\": \"delete\", \"path\": [\"children\", 0, \"children\"], \"index\": 3},\n"
                               "    {\"op\": \"set\", \"path\": [\"@panel1\", \"configs\", \"newKey\"],\n"
                               "     \"value\": \"v\", \"create\": true}\n"
                               "  ]\n"
                               "ops 按顺序执行，path 按执行到那一步时的结构解释。\n"
                               "任意一条 set 可带 \"create\": true：补**原本不存在的键**时用它；写到已存在的键上是幂等保护。\n"
                               "\n"
                               "path 里的对象键优先用 @itemId（数组元素仍用下标），重名时不猜顺序：\n"
                               "  [\"@名字#N\"]              点名第 N 个（N 从 1 起）\n"
                               "  [\"@外\", \"@内\", …]          串联 @，后一段只在上一段子树里找\n"
                               "  [\"@名字\", \"children\", 0]     按父子关系只改真正要改的那个")
    pt.add_argument("file", help="要修改的 .xwl 文件")
    pt.add_argument("--ops", required=True, help="ops JSON 文件：set/insert/append/delete 的数组")
    pt.add_argument("--indent", type=int, default=1, help="缩进因子（设计器固定用 1，一般不用改）")
    pt.add_argument("--eol", choices=["auto", "lf", "crlf"], default="auto",
                    help="换行：auto=沿用原文件（只有一种换行就沿用它；混用时只在 CRLF/LF 取多数、"
                         "等量取 CRLF、CR 不投票；无换行回退 lf）；lf / crlf=指定")
    pt.add_argument("--dry-run", action="store_true", help="只显示将产生的 diff，不写入")
    pt.add_argument("--backup", action="store_true", help="写盘前先备份为 <file>.bak")
    pt.add_argument("--node", help="node 可执行文件路径（缺省从 NODE_BIN 与 PATH 找）")
    pt.add_argument("--no-js", action="store_true", help="跳过写盘后的事件 JS 语法校验")
    pt.set_defaults(func=cmd_patch)

    pm = sub.add_parser("params", help="检查「页面 → store → SQL 文件」的传参链路（参数名交叉核对）")
    pm.add_argument("file", nargs="?", help="页面 xwl（配 --list-fields 时可省略）")
    pm.add_argument("--module-root", help="wb/modules 的绝对路径（缺省从文件位置向上找）")
    pm.add_argument("--controls", help="wb/system/controls.json；给了就从注册表推导「取值控件」类型")
    pm.add_argument("--list-fields", action="store_true", help="只打印取值控件类型清单后退出")
    pm.set_defaults(func=cmd_params)

    pa = sub.add_parser("paths", help="列出可编辑字段位置（sql / totalSql / serverScript / url），供 patch 用")
    pa.add_argument("file", help="要列出可编辑字段的 .xwl 文件")
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
                   help="换行：lf=设计器写在服务器上的产物形态（默认）；crlf=Windows 工作区形态"
                        "（new 无 auto —— 新文件没有源可沿用，直接选一种）")
    n.add_argument("--indent", type=int, default=1, help="缩进因子（设计器固定用 1，一般不用改）")
    n.add_argument("--force", action="store_true", help="允许覆盖已存在的文件")
    n.add_argument("--dry-run", action="store_true", help="只打印将写入的内容，不写盘")
    n.add_argument("--node", help="node 可执行文件路径（缺省从 NODE_BIN 与 PATH 找）")
    n.add_argument("--no-js", action="store_true", help="跳过写盘后的事件 JS 语法校验")
    n.set_defaults(func=cmd_new)

    fld = sub.add_parser("folders", help="folder.json（设计器导航树索引）一致性检查 / 登记")
    fld.add_argument("path", help=".xwl 文件，或要递归检查的目录")
    fld.add_argument("--register", nargs="?", const="", default=None, metavar="NAME",
                     help="写操作：把文件登记到所在目录 folder.json 的 index 末尾。"
                          "可裸用（--register）；NAME 值在 path 已指到文件时会被忽略，仅为兼容保留")
    fld.add_argument("--dry-run", action="store_true", help="只打印 before/after，不写盘")
    fld.set_defaults(func=cmd_folders)

    ii = sub.add_parser("itemids", help="注册键重名分级报告（按 normalName||itemId；候选清单 + 建议值），只读",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        epilog="常用三个选项（另有 --fix / --controls / --json）：\n"
                               "  --dups-only   只列重名组（长报告时用）\n"
                               "  --name NAME   只看一个名字的全部候选（itemId 或注册键）\n"
                               "  --suggest     生成改名 ops 草稿（需人工确认后再 patch）")
    ii.add_argument("file", help="要检查的 .xwl 文件")
    ii.add_argument("--name", help="只点名一个 itemId 或注册键（normalName||itemId），打印候选清单与建议值")
    ii.add_argument("--dups-only", action="store_true", help="benign 组不展开（长报告时用）")
    ii.add_argument("--suggest", action="store_true", help="输出「改名 ops 草稿」JSON（需人工确认后再 patch）")
    ii.add_argument("--fix", choices=["auto", "normalName", "itemId"], default="auto",
                    help="--suggest 用哪种修法：auto=能补 normalName 就补（默认）")
    ii.add_argument("--controls", help="wb/system/controls.json；缺省从文件位置向上自动找")
    ii.add_argument("--json", action="store_true",
                    help="机器可读输出（groups[] 的 name=注册键，另含 itemIds/registryName）")
    ii.set_defaults(func=cmd_itemids)

    sr = sub.add_parser("sqlrefs", help="检查 SQL 文件里 serverScript ↔ dataprovider 的引用是否自洽")
    sr.add_argument("file", help="要检查自洽性的 SQL 载体 .xwl 文件")
    sr.set_defaults(func=cmd_sqlrefs)

    dg = sub.add_parser("diffguard",
                        help="相对 git 基线检测「多行内容被压平」（格式校验查不出的那类损坏）")
    dg.add_argument("targets", nargs="+", metavar="PATH", help=".xwl 文件，或要递归检查的目录（可给多个）")
    dg.add_argument("--rev", default="HEAD", help="比对基线（默认 HEAD；也可给 origin/main 等）")
    dg.add_argument("--strict", action="store_true",
                    help="把「疑似压平」当成失败（rc=1）；且不允许跳过（跳过时 rc=2）。"
                         "默认只告警、rc=0")
    dg.set_defaults(func=cmd_diffguard)

    sc = sub.add_parser("schema", help="查设计器控件注册表：某控件合法的 configs / events",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        epilog="标准控件节点的键集合只有两种（键序固定）：\n"
                               "  [\"configs\", \"expanded\", \"children\", \"type\"]\n"
                               "  [\"configs\", \"expanded\", \"children\", \"type\", \"events\"]\n"
                               "少写 expanded / children 通常有默认值兜底，但会与设计器产物不一致；\n"
                               "用 --skeleton 生成骨架最稳。itemId 是工具寻址用的（@itemId）；运行时 app.<名> 取的是注册键（normalName||itemId）、必须唯一。\n"
                               "\n"
                               "例：\n"
                               "  xwl.py schema button --controls <工程>/wb/system/controls.json --skeleton")
    sc.add_argument("type", nargs="?", help="控件 id，如 button / grid / store；省略需配 --list")
    sc.add_argument("--controls", required=True, help="设计器控件注册表路径（工程里是 wb/system/controls.json）")
    sc.add_argument("--list", action="store_true", help="列出全部控件 id")
    sc.add_argument("--tree", action="store_true", help="按设计器面板分组打印控件树（含库/容器标记）")
    sc.add_argument("--skeleton", action="store_true", help="顺便输出设计器同款最小骨架节点")
    sc.set_defaults(func=cmd_schema)

    d = sub.add_parser("dump", help="按加载器规则解析后美化输出（拿不准嵌套层级时用它核对）")
    d.add_argument("file", help="要解析并美化输出的 .xwl 文件")
    d.set_defaults(func=cmd_dump)

    x = sub.add_parser("expand", help="规范成设计器同款多行形态（解析→按设计器算法重排，含语义等价比对）")
    x.add_argument("file", help="要规范成设计器形态的 .xwl 文件")
    x.add_argument("--out", help="输出到另一个文件（缺省原地覆盖）")
    x.add_argument("--indent", type=int, default=1, help="缩进因子（设计器固定用 1，一般不用改）")
    x.add_argument("--eol", choices=["auto", "lf", "crlf"], default="auto",
                   help="换行符：auto=沿用原文件（默认）。只有一种换行就沿用它；混用时只在 CRLF/LF "
                        "取多数、等量取 CRLF（CR 不投票）；连一个换行符都没有时回退 lf。"
                        "lf=设计器写在服务器上的产物形态（换行随服务器而定，Linux 上为 LF）；"
                        "crlf=Windows 工作区形态")
    x.add_argument("--safe", action="store_true",
                   help="安全模式：不动值里的「字面反斜杠 + n」。与默认模式**语义等价**，"
                        "差异只在字节形态 —— 产出与设计器不一致，别用于要提交的文件")
    x.add_argument("--dry-run", action="store_true", help="不写盘，只跑完校验")
    x.add_argument("--backup", action="store_true", help="原地覆盖时写 <file>.bak")
    x.add_argument("--node", help="node 可执行文件路径（缺省从 NODE_BIN 与 PATH 找）")
    x.add_argument("--no-js", action="store_true", help="跳过写盘后的事件 JS 语法校验")
    x.set_defaults(func=cmd_expand)

    s = sub.add_parser("sql", help="抽取 SQL 文本")
    s.add_argument("file", help="要抽取 SQL 文本的 .xwl 文件")
    s.set_defaults(func=cmd_sql)

    v = sub.add_parser("events", help="抽取事件 JS")
    v.add_argument("file", help="要抽取事件 JS 的 .xwl 文件")
    v.add_argument("--outdir", help="导出目录（缺省则打印到标准输出）")
    v.set_defaults(func=cmd_events)

    return p


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except XwlWriteError as exc:
        # 写盘失败属「前置条件不满足」——给可读提示 + 退出码 2，而不是抛 traceback
        print(f"[FAIL] {exc}")
        print("       可能原因：目标只读 / 所在目录不存在 / 路径过长 / 磁盘只读；")
        print("       若目标正被编辑器或同步工具占用，先关掉再试。")
        return 2


if __name__ == "__main__":
    sys.exit(main())
