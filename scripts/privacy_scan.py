#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""privacy_scan.py —— 发布前的隐私 / 业务标识扫描（**只读、零写入**）。

定位：**补既有文档守卫覆盖不到的类**，不是从零建。分工边界（各守各的，别越界）：

  · 文档（登记清单里的 md）中的**本机路径 / 业务路径** —— 仍由 `scripts/selftest.py`
    的文档守卫负责（那条守卫的扫描面只到文档，够不着本脚本要补的第一项）。
  · 本脚本负责三类：
      ① `.py` 文件里的**本机路径**（文档守卫不扫 `.py` ⇒ 这是真实空洞）；
      ② **邮箱 / 手机号 / 长随机串（疑似 token）/ uid 形状**（形状类，不依赖任何名单）；
      ③ **外置业务标识清单**（真实清单落在**仓库之外**，用 `--patterns <路径>` 传入）。

设计要点（每条都有非做不可的理由）：

  · **平台锚点一律放行**：`wb/system/`、`wb/modules/`、`wb/script/`、`WEB-INF/lib/*.jar`、
    `com.wb.*` —— 它们是平台自带命名，不是某个工程的业务标识。
  · **绝不把业务名黑名单写进代码**：那等于把业务名又写回仓库。要拦的业务标识只从
    外置清单来。
  · **不依赖 `.gitignore` 兜底**：`.gitignore` 挡不住 `git add -f`，所以真实清单的落点
    是"仓库之外"这个硬约束，而不是忽略规则。
  · **清单缺失 / 为空 ⇒ 报错退出**：静默给出"0 命中"是把缺陷伪装成通过（本仓铁律：
    静默降级整类都是缺陷）。
  · **无 git 时显式降级**：取不到 `git ls-files` 默认**判红**，确无 `.git`（如 zip 分发
    解包后）须显式 `--allow-nogit` 才降级为"标注继续、按其它项定 rc"。

兼容：Python 3.9 起（不用 3.10+ 才有的语法）。

用法：
  python privacy_scan.py                                     # 只跑结构面（CI 用）
  python privacy_scan.py --patterns /path/to/patterns.json   # 结构面 ＋ 外置清单面
  python privacy_scan.py --selftest                          # 内置正反用例自检（含注入断言）

退出码：命中即非 0；无 git 且未 `--allow-nogit` 亦非 0。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


# --------------------------------------------------------------------------- #
# 平台锚点（放行面）：这些是平台自带命名，不是业务标识
# --------------------------------------------------------------------------- #
PLATFORM_ANCHORS = (
    "wb/system/",
    "wb/modules/",
    "wb/script/",
    "WEB-INF/lib/",
    ".jar",
    "com.wb.",
)


def _anchor_in(text: str) -> bool:
    """文本里是否含平台锚点（命中即放行，视为平台自带命名）。"""
    return any(a in text for a in PLATFORM_ANCHORS)


# --------------------------------------------------------------------------- #
# 形状类判据：本机路径 / 邮箱 / 手机号 / 疑似 token / uid 形状
#   —— 全部用**结构**（形状）表达，不写任何具体业务名。
# --------------------------------------------------------------------------- #
# 本机路径（Windows 盘符）：字母 + 冒号 + 斜杠，再跟一段真实路径。前后界定符避开 `http:` 之类。
#   `(?=[A-Za-z0-9_.-]*[A-Za-z0-9])` 要求路径段里**至少有一个字母数字** ⇒ `C:\...` 这类
#   纯省略号的截断示例不算真实路径（否则把"示意写法"当泄漏）。
_RE_DRIVE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/](?![\\/])(?=[A-Za-z0-9_.-]*[A-Za-z0-9])[A-Za-z0-9_.-]{2,}")
# 本机路径（类 Unix 家目录）：/home/、/Users/、/root/、/Volumes/ 下的个人目录。
_RE_UNIX_HOME = re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users|root|Volumes)/[A-Za-z0-9._-]{2,}")
# 「占位 / 示意行」放行：与既有文档守卫同口径（`RUNNER` 短名示例 / `<…>` 占位写法），
#   这类行里的路径是示意（如 CI runner 的 `C:\Users\RUNNER~1\…`），不算真实本机路径。
_RE_PLACEHOLDER_LINE = re.compile(r"RUNNER|[<\u2026]")
# 邮箱：本地部 @ 域名（域名至少含一个点）。
_RE_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
# 视网膜图资源名 `@2x` 之类：不是邮箱（域名以「数字+x.」起头）。
_RE_RETINA = re.compile(r"^\d+[xX]\.")
# 手机号（中国大陆段）：1 开头、第二位 3-9、共 11 位，前后不再接数字。
_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 疑似 token —— 高置信前缀式。
_RE_TOKEN_PREFIX = re.compile(
    r"(?<![A-Za-z0-9])("
    r"sk-[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|ASIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r")")
# 疑似 token —— 通用长随机串候选（≥32 且不含点，避免命中 URL / 版本号）。
_RE_LONE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9_])")
# uid 形状：标准 UUID。
_RE_UUID = re.compile(
    r"(?<![A-Za-z0-9])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![A-Za-z0-9])")

# 邮箱判据的占位域放行面（示例 / 保留域，不视为真实邮箱）。
_EMAIL_OK = ("example.com", "example.org", "example.net", "example.edu",
             "localhost", "invalid", "test")

# 明确按扩展名跳过的二进制（不做文本扫描，也不假装扫过）。
_BINARY_EXT = (".jar", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp",
               ".zip", ".gz", ".tar", ".tgz", ".7z", ".woff", ".woff2", ".ttf",
               ".otf", ".eot", ".pdf", ".exe", ".dll", ".so", ".dylib", ".bin",
               ".class", ".pyc", ".pyd", ".so.1")


def _email_allowed(domain: str) -> bool:
    """占位 / 保留域是否放行（`example.com` 一类不算真实邮箱）。"""
    d = domain.lower()
    if d.endswith(".example") or d == "example":
        return True
    return any(d == x or d.endswith("." + x) for x in _EMAIL_OK)


def _looks_like_secret(tok: str) -> bool:
    """长随机串（疑似 token）的通用启发式：够长、多字符类、不含点。"""
    if len(tok) < 32 or "." in tok:
        return False
    classes = 0
    classes += 1 if any(c.islower() for c in tok) else 0
    classes += 1 if any(c.isupper() for c in tok) else 0
    classes += 1 if any(c.isdigit() for c in tok) else 0
    classes += 1 if ("_" in tok or "-" in tok) else 0
    return classes >= 3


def _identity_hits(line: str):
    """形状类命中（逐条 yield `(类别, 命中串)`）；平台锚点命中即放行。"""
    for m in _RE_EMAIL.finditer(line):
        dom = m.group(2)
        if _RE_RETINA.match(dom) or _email_allowed(dom):
            continue
        tok = m.group(0)
        if _anchor_in(tok):
            continue
        yield ("邮箱", tok)
    for m in _RE_PHONE.finditer(line):
        tok = m.group(0)
        if _anchor_in(tok):
            continue
        yield ("手机号", tok)
    for m in _RE_TOKEN_PREFIX.finditer(line):
        tok = m.group(0)
        if _anchor_in(tok):
            continue
        yield ("疑似 token", tok)
    for m in _RE_LONE.finditer(line):
        tok = m.group(0)
        if _anchor_in(tok) or not _looks_like_secret(tok):
            continue
        yield ("疑似 token", tok)
    for m in _RE_UUID.finditer(line):
        tok = m.group(0)
        if _anchor_in(tok):
            continue
        yield ("uid 形状", tok)


def _scan_text(text: str, is_py: bool, patterns):
    """扫一段文本，返回 `[(行号, 类别, 命中串), ...]`。

    `is_py` 为真时才查**本机路径**（文档里的路径归既有文档守卫，本脚本不重复管）。
    `patterns` 为外置业务标识清单（可为空）。
    """
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        # 本机路径只查 `.py`，且放行平台锚点行与占位 / 示意行（口径同既有文档守卫）。
        if is_py and not _anchor_in(line) and not _RE_PLACEHOLDER_LINE.search(line):
            for m in _RE_DRIVE.finditer(line):
                out.append((i, "本机路径", m.group(0)))
            for m in _RE_UNIX_HOME.finditer(line):
                out.append((i, "本机路径", m.group(0)))
        for klass, tok in _identity_hits(line):
            out.append((i, klass, tok))
        for pat in patterns:
            if pat in line:
                out.append((i, "外置业务标识", pat))
    return out


# --------------------------------------------------------------------------- #
# 外置业务标识清单
# --------------------------------------------------------------------------- #
class PatternError(Exception):
    """外置清单缺失 / 为空 / 形态不对 —— 一律报错退出，不静默 0 命中。"""


def _is_placeholder(s: str) -> bool:
    """`<客户名>` 这类尖括号占位符（空串也算占位）。"""
    return (not s.strip()) or ("<" in s) or (">" in s)


def _load_patterns(path: str):
    """读外置清单（JSON）：`{"identifiers": [...], "path_fragments": [...]}` 或纯数组。

    过滤掉占位符 / 平台锚点 / 示例域之后**仍为空 ⇒ 判错**（静默 0 命中是缺陷）。
    """
    if not os.path.isfile(path):
        raise PatternError("清单文件不存在：%s" % path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise PatternError("清单读不出 / 不是合法 JSON：%s（%s）" % (path, exc))
    if isinstance(data, dict):
        raw = list(data.get("identifiers") or []) + list(data.get("path_fragments") or [])
    elif isinstance(data, list):
        raw = list(data)
    else:
        raise PatternError("清单结构不对（应为对象或数组）：%s" % path)
    items = []
    for it in raw:
        s = str(it).strip()
        if _is_placeholder(s) or _anchor_in(s) or _email_allowed(s):
            continue
        items.append(s)
    if not items:
        raise PatternError(
            "清单为空（或全是占位符 / 示例域）⇒ 静默 0 命中是缺陷，判错退出：%s。"
            "请确认传入的是**真实清单**（真实清单应落在仓库之外）。" % path)
    return items


# --------------------------------------------------------------------------- #
# 扫描面：`git ls-files` ∪ 磁盘新增未跟踪（与文档守卫同口径）
# --------------------------------------------------------------------------- #
def _collect_files(root: str):
    """返回 `(文件相对路径列表, None)`；取不到 git ⇒ `(None, 原因)`。"""
    files = []
    seen = set()
    for extra in (["ls-files"], ["ls-files", "--others", "--exclude-standard"]):
        try:
            proc = subprocess.run(
                ["git", "-C", root] + extra,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace")
        except OSError as exc:
            return None, "无法执行 git：%s" % exc
        if proc.returncode != 0:
            return None, "`git %s` 返回 %d：%s" % (
                " ".join(extra), proc.returncode, (proc.stderr or "").strip())
        for line in (proc.stdout or "").splitlines():
            rel = line.strip()
            if not rel or rel in seen:
                continue
            seen.add(rel)
            files.append(rel)
    return files, None


def _scan_files(root: str, files, patterns):
    """扫文件集，返回 `(命中列表, 实扫文件数, 读不出的文件列表)`。"""
    hits = []
    skipped = []
    scanned = 0
    for rel in files:
        if os.path.splitext(rel)[1].lower() in _BINARY_EXT:
            skipped.append(rel)
            continue
        path = os.path.join(root, rel.replace("/", os.sep))
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            skipped.append(rel)
            continue
        scanned += 1
        is_py = rel.endswith(".py")
        for ln, klass, tok in _scan_text(text, is_py, patterns):
            hits.append((rel, ln, klass, tok))
    return hits, scanned, skipped


def _clip(tok: str, keep: int = 4) -> str:
    """命中串只露极少前缀（避免把疑似机密原样打进日志），其余只报长度。"""
    if len(tok) <= keep:
        return tok
    return tok[:keep] + "…（共 %d 字）" % len(tok)


def _ensure_utf8_stdio() -> None:
    """标准流切 UTF-8：输出全中文，Windows 下默认代码页会 `UnicodeEncodeError`。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001  （流被替换过 / 不支持 reconfigure 时忽略）
            pass


# --------------------------------------------------------------------------- #
# 内置正反用例自检
# --------------------------------------------------------------------------- #
def _run_selftest() -> int:
    """跑内置正反用例：正例 ≥4 全部命中 / 反例 ≥3 零误报 / 注入假标识必报红。"""
    fails = []

    # 正例（每条都是**拼装**出来的，源码里不落整串）——
    #   拼装有两个好处：① 不在源码里留可被扫到的成品串；② 源码自身不被本脚本判红。
    _drive = "C" + ":" + "\\" + "Users" + "\\" + "someone" + "\\" + "proj" + "\\" + "a.txt"
    _unix = "/ho" + "me/" + "someuser" + "/proj"
    _mail = "al" + "ice" + "@" + "mail" + "box" + "." + "dev"
    _phone = "138" + "0013" + "8000"
    _tok_pre = "AKIA" + "IOSFODNN7EXAMPLE"
    _tok_ran = "".join(["Aa1Bb2", "Cc3Dd4", "Ee5Ff6", "Gg7Hh8", "Ii9Jj0", "Kk1Ll2"])
    _uuid = "12345678" + "-" + "1234" + "-" + "1234" + "-" + "1234" + "-" + "123456789012"

    positives = (
        ("本机路径·盘符", _drive, "本机路径"),
        ("本机路径·家目录", _unix, "本机路径"),
        ("邮箱", _mail, "邮箱"),
        ("手机号", _phone, "手机号"),
        ("疑似 token·前缀", _tok_pre, "疑似 token"),
        ("疑似 token·长随机", _tok_ran, "疑似 token"),
        ("uid 形状", _uuid, "uid 形状"),
    )
    for name, text, klass in positives:
        got = _scan_text(text, True, [])
        if not any(k == klass for _, k, _ in got):
            fails.append("正例未命中：%s ⇒ 期望类别 %s，实得 %s" % (name, klass, got))

    # 反例（都不该命中）——
    _ph_win = "C" + ":" + "\\" + "Users" + "\\" + "RUNNER~1" + "\\" + "proj"
    _ph_dots = "C" + ":" + "\\" + "..."
    negatives = (
        ("平台锚点", "\n".join([
            "p = 'wb/modules/order/list.xwl'",
            "q = 'wb/system/controls.json'",
            "r = 'com.wb.foo.Bar'",
            "j = 'WEB-INF/lib/anything.jar'",
        ])),
        ("占位路径·示意行", "\n".join([
            "p = " + repr(_ph_win),
            "q = " + repr(_ph_dots),
        ])),
        ("占位邮箱", "e = " + repr("user" + "@" + "example" + "." + "com")),
        ("视网膜资源名", "css = " + repr("icon" + "@" + "2x" + "." + "png")),
        ("普通代码", "def add(a, b):\n    return a + b\n"),
    )
    for name, text in negatives:
        got = _scan_text(text, True, [])
        if got:
            fails.append("反例误报：%s ⇒ %s" % (name, got))

    # 注入断言：把**假业务标识**放进临时文件，用临时清单扫 ⇒ 必须报红（含外置清单面被扫到）。
    tmp = tempfile.mkdtemp(prefix="privacy_scan_selftest_")
    try:
        fake_id = "zq" + "x" + "acme" + "-" + "cust" + "9"
        leak_py = os.path.join(tmp, "leak.py")
        with open(leak_py, "w", encoding="utf-8") as fh:
            fh.write("value = " + repr(fake_id) + "\n")
        pat_json = os.path.join(tmp, "patterns.json")
        with open(pat_json, "w", encoding="utf-8") as fh:
            json.dump({"identifiers": [fake_id]}, fh, ensure_ascii=False)
        try:
            pats = _load_patterns(pat_json)
        except PatternError as exc:
            fails.append("注入用临时清单竟被拒：%s" % exc)
            pats = []
        with open(leak_py, "r", encoding="utf-8") as fh:
            leak_text = fh.read()
        injected = _scan_text(leak_text, True, pats)
        if not any(k == "外置业务标识" for _, k, _ in injected):
            fails.append("植入假业务标识竟未报红（外置清单面失效）⇒ %s" % injected)

        # 清单缺失 / 为空：都必须报错（不得静默 0 命中）。
        try:
            _load_patterns(os.path.join(tmp, "no_such.json"))
            fails.append("清单缺失竟未报错")
        except PatternError:
            pass
        empty_json = os.path.join(tmp, "empty.json")
        with open(empty_json, "w", encoding="utf-8") as fh:
            json.dump({"identifiers": []}, fh, ensure_ascii=False)
        try:
            _load_patterns(empty_json)
            fails.append("清单为空竟未报错")
        except PatternError:
            pass
        # 示例骨架（全占位符）也必须被拒 —— 防止把示例当清单用。
        try:
            _load_patterns(os.path.join(HERE, "privacy_patterns.example.json"))
            fails.append("示例骨架清单（全占位符）竟被当成有效清单")
        except PatternError:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        for f in fails:
            print("[FAIL] %s" % f)
        print("=== privacy_scan --selftest FAIL（%d 项）" % len(fails))
        return 1
    print("[ok]  privacy_scan --selftest：正例 %d 条全部命中"
          "（本机路径·盘符 / 本机路径·家目录 / 邮箱 / 手机号 / 疑似 token·前缀 / "
          "疑似 token·长随机 / uid 形状）；反例 %d 条零误报"
          "（平台锚点 / 占位路径·示意行 / 占位邮箱 / 视网膜资源名 / 普通代码）；"
          "植入假标识必报红；清单缺失·为空·纯占位示例均判错"
          % (len(positives), len(negatives)))
    print("=== privacy_scan --selftest ALL OK")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="privacy_scan.py",
        description="发布前隐私 / 业务标识扫描（只读）：本机路径(.py) / 邮箱 / 手机号 / "
                    "疑似 token / uid 形状 / 外置业务标识清单")
    ap.add_argument("--patterns", default=None, metavar="<路径>",
                    help="外置业务标识清单（JSON；真实清单应落在仓库之外）。"
                         "不给则只跑结构面，并**显式标注**「本地业务标识清单未参与」")
    ap.add_argument("--allow-nogit", action="store_true",
                    help="允许在无 .git 时降级（不因取不到 git 清单而判红；默认无此开关即判红）")
    ap.add_argument("--root", default=ROOT, metavar="<路径>",
                    help="扫描根目录（默认为本脚本的上级目录）")
    ap.add_argument("--selftest", action="store_true",
                    help="跑内置正反用例自检（含「植入假标识必报红」注入断言）")
    args = ap.parse_args(argv)

    _ensure_utf8_stdio()

    if args.selftest:
        return _run_selftest()

    root = os.path.abspath(args.root)

    # 外置清单面：给了就必须有效；没给就**显式标注**未参与（不静默跳过）。
    patterns = []
    if args.patterns:
        try:
            patterns = _load_patterns(args.patterns)
        except PatternError as exc:
            print("[FAIL] privacy_scan 外置业务标识清单：%s" % exc)
            print("=== privacy_scan FAIL（1 项）")
            return 1
        print("[note] 外置业务标识清单已参与：%s（%d 条标识）" % (args.patterns, len(patterns)))
    else:
        print("[note] 本地业务标识清单未参与：未提供 `--patterns <路径>` ⇒ 本次只跑**结构面**"
              "（本机路径·.py / 邮箱 / 手机号 / 疑似 token / uid 形状）。"
              "清单面须在本地用**真实清单**跑，且清单落在仓库之外。")

    files, why = _collect_files(root)
    if files is None:
        if args.allow_nogit:
            print("[note] privacy_scan：取不到 git 清单 ⇒ 本次**没扫**"
                  "（`--allow-nogit` 降级：不算通过也不算失败）：%s" % why)
            print("=== privacy_scan ALL OK")
            return 0
        print("[FAIL] privacy_scan：取不到 git 清单 ⇒ 本次**没扫**（默认判红 —— 静默绿是病根）。"
              "确无 `.git`（如 zip 分发解包后）需降级时，显式加 `--allow-nogit`。原因：%s" % why)
        print("=== privacy_scan FAIL（1 项）")
        return 1

    hits, scanned, skipped = _scan_files(root, files, patterns)
    list_tag = "／外置业务标识" if patterns else ""
    if skipped:
        shown = "，".join(skipped[:8])
        more = "，另有 %d 个未列" % (len(skipped) - 8) if len(skipped) > 8 else ""
        print("[note] 跳过 %d 个非文本 / 读不出的文件：%s%s" % (len(skipped), shown, more))
    if hits:
        for rel, ln, klass, tok in hits[:40]:
            print("[FAIL] privacy_scan：%s:%d 命中%s「%s」" % (rel, ln, klass, _clip(tok)))
        if len(hits) > 40:
            print("[note] 另有 %d 条命中未逐条列出" % (len(hits) - 40))
        print("=== privacy_scan FAIL（%d 项）" % len(hits))
        return 1
    print("[ok]  privacy_scan：扫 %d 个文件（跳过 %d 个非文本）—— "
          "本机路径（.py）/ 邮箱 / 手机号 / 疑似 token / uid 形状%s 均 0 命中"
          % (scanned, len(skipped), list_tag))
    print("=== privacy_scan ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
