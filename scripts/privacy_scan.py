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

退出码（四格矩阵）：
  · 无命中 ＋ 全部应扫文本读完          ⇒ 0（有意排除的二进制另桶统计）
  · 有命中                              ⇒ 1（逐条列命中）
  · 无命中 ＋ 有应扫文本**读不出**      ⇒ 2（逐条列未完成；⛔ 不报 `ALL OK`）
  · 有命中 ＋ 有读不出                  ⇒ 1（命中与未完成**同时**列，未读文件不算干净）
  · 取不到 git 清单（超时／IO）          ⇒ 2；「确无 `.git`」⇒ 默认 1，`--allow-nogit` 才降级为 0
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
# 「占位 / 示意」的语法见下方 `_SEG_PLACEHOLDER`（判"某段是不是占位"，不是判"串里有没有"）。
# 占位豁免的判定单位 ＝ **路径段**（不是"候选串里出现过占位符"）。
#   语法：整段就是 `<…>` ／ `…` ／ `...` ／ `~` ／ `RUNNER`(`~N`)。
#   ⚠️ 为什么必须"整段"：`<` 出现在段中间（`a <b>/b`）是**真路径**，不是占位；
#   而"串里 search 到就算"会把「真路径 ＋ 行尾注释里的占位」整行放掉（实测 9 条应报里放过 6 条）。
_SEG_PLACEHOLDER = re.compile(r"^(?:<[^<>]*>|\u2026|\.\.\.|~|RUNNER(?:~\d+)?)$")
# 路径候选的**边界口径**（口径写错就是误报或漏报，两边都实测过）：
#   · 扩展条件 ＝ **不在终止集就继续**。⛔ **不许**再拿字符白名单当条件 ——
#     `(` 不在白名单里，会把 `Program Files (x86)\<user>` 截断在 `(` 前、占位符落到候选外 ⇒ 误报。
#   · 终止集 ＝ 引号 / 反引号 / `;` `,` `=` `&` `|` / 方括号与花括号（**不含**圆括号）。
#   · 向左：遇**空格即止**（`_RE_DRIVE`／`_RE_UNIX_HOME` 的匹配起点本身就是路径头）。
#   · 向右：遇空格时，**仅当**后面是新绝对路径起头（`[A-Za-z]:` 或 `/`）才止 —— 否则
#     `Program Files` / `My App` 这类真实目录名会被截断；而 `cp C:\a D:\bak\<user>` 这类
#     **同一行两条路径**又必须在这里切开，否则候选跨过空格吞掉第二条的占位段、真路径被漏报。
#     ⚠️ 不许写成 `/home|/Users|/root|/Volumes` 枚举：遇 `/opt`、`/mnt` 会静默漏。
_PATH_STOP = frozenset("\"'`;,=&|[]{}")
_NEW_ABS_PATH = re.compile(r"^(?:[A-Za-z]:|/)")


def _path_candidate(line: str, start: int, end: int) -> str:
    r"""从匹配区间向两侧扩展到"路径外字符"为止，返回**整段路径候选**。

    为什么必须扩展：`_RE_DRIVE` 只吃到盘符加**第一段**目录，若只判 `m.group(0)`，
    后面几段里的占位段（runner 短名、尖括号段）都落在候选**之外** ⇒ 该放行的反而误报。
    """
    i = start
    while i > 0:
        ch = line[i - 1]
        if ch in _PATH_STOP or ch == " ":
            break
        i -= 1
    j = end
    n = len(line)
    while j < n:
        ch = line[j]
        if ch in _PATH_STOP:
            break
        # 2 个字符：盘符判定要 `X:` 两位（切 1 位会让 `D:\` 判不出来）。
        if ch == " " and _NEW_ABS_PATH.match(line[j + 1:j + 3] or ""):
            break
        j += 1
    return line[i:j]


def _placeholder_segment(cand: str) -> bool:
    """候选里**有没有一段整段就是占位符**（按 `[\\\\/]` 切段后逐段整体匹配）。"""
    return any(_SEG_PLACEHOLDER.match(seg) for seg in re.split(r"[\\/]", cand))


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
        # 本机路径只查 `.py`；占位豁免按**路径段**判 —— ⛔ 不是"整行里有占位符就整行免检"，
        #   也 ⛔ 不是"候选串里 search 到占位就豁免"（后者会把同一行里的真路径一起放掉）。
        if is_py and not _anchor_in(line):
            for m in _RE_DRIVE.finditer(line):
                cand = _path_candidate(line, m.start(), m.end())
                if _placeholder_segment(cand):
                    continue
                out.append((i, "本机路径", cand))
            for m in _RE_UNIX_HOME.finditer(line):
                cand = _path_candidate(line, m.start(), m.end())
                if _placeholder_segment(cand):
                    continue
                out.append((i, "本机路径", cand))
        for klass, tok in _identity_hits(line):
            out.append((i, klass, tok))
        for pat in patterns:
            if pat in line:
                out.append((i, "外置业务标识", pat))
    # 去重：同一条路径会被两个正则各报一次（盘符正则吃前一段、家目录正则吃 `/Users/…` 那一段），
    #   但两者的**候选扩展后收敛成同一串** ⇒ 按 `(行号, 类别, 候选)` 去重即可。
    #   ⚠️ 键必须是三元组而不是"整条记录"：`tok` 已统一成候选，但顺序/类别也要参与比较。
    _seen = set()
    _uniq = []
    for _item in out:
        if _item in _seen:
            continue
        _seen.add(_item)
        _uniq.append(_item)
    return _uniq


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
        # 取 `raw` **之前**先验类型：`{"identifiers": "acme"}` 被 `list("acme")` 拆成四个单字母
        #   标识 ⇒ 全仓误报；元素非字符串则 `str(it)` 静默转串（＝静默降级）。两者都必须**报错退出**，
        #   ⛔ 不许改成"跳过它"。
        for _key in ("identifiers", "path_fragments"):
            _val = data.get(_key)
            if _val is None:
                continue
            if not isinstance(_val, (list, tuple)):
                raise PatternError("清单字段 `%s` 类型不对（应为数组，实得 %s）：%s"
                                   % (_key, type(_val).__name__, path))
        raw = ([("identifiers", _v) for _v in (data.get("identifiers") or [])]
               + [("path_fragments", _v) for _v in (data.get("path_fragments") or [])])
    elif isinstance(data, list):
        raw = [("顶层数组", _v) for _v in data]
    else:
        raise PatternError("清单结构不对（应为对象或数组）：%s" % path)
    # 元素类型对**两个分支都**先验（顶层数组同样不许出现非字符串）。
    #   ⚠️ 文案要能**定位**：报"字段名 + 该字段内序号"（报合并下标会让人在两个数组间找错位置）。
    _nth = {}
    for _fld, _it in raw:
        _nth[_fld] = _nth.get(_fld, 0) + 1
        if not isinstance(_it, str):
            raise PatternError("清单字段 `%s` 的第 %d 个元素类型不对（应为字符串，实得 %s）：%s"
                               % (_fld, _nth[_fld], type(_it).__name__, path))
    items = []
    for _fld, it in raw:
        s = it.strip()
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
# `git` 子进程的边界（三条都是"外部系统不可控"的收口，不靠"人不会这么跑"）：
#   · `timeout`：`git` 可能因索引锁／网络文件系统／凭据交互**永不返回** ⇒ 给一个**正**的上限；
#   · `GIT_TERMINAL_PROMPT=0`：禁掉凭据交互（否则子进程一直等 stdin，看起来就是"卡住"）；
#   · `GIT_OPTIONAL_LOCKS=0`：不抢可选锁（只读扫描没必要写 index，也少一类阻塞源）。
_GIT_TIMEOUT = 30


def _git_env() -> dict:
    """`git` 子进程的环境：`dict(os.environ)` 起手。

    ⚠️ `subprocess` 的 `env=` 会**整体替换**环境 ⇒ 不从 `os.environ` 拷一份就会丢 `PATH`。
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _split_z(out: str) -> list:
    """按 NUL 拆分 `git ls-files -z` 的输出（文件名边界**只有** NUL）。

    ⛔ 不许 `strip()` 单个名字（会吃掉前导／尾随空格 ⇒ 身份丢失）；
    ⛔ 不许把 `splitlines()` 当边界（名字里合法地可以含换行）。
    """
    return [x for x in (out or "").split("\0") if x != ""]


def _collect_files(root: str):
    """返回 `(文件相对路径列表, None)`；取不到 git ⇒ `(None, {"kind": …, "msg": …})`。

    `kind` 只在本模块内部用（⛔ 不新增公开开关），三档语义不同、**退出码也不同**：

      · `no_git`  —— 确无 `.git`（zip 解包后的分发形态）⇒ `main` 保留原语义，可 `--allow-nogit` 降级；
      · `timeout` —— `git` 超过 `_GIT_TIMEOUT` 秒 ⇒ `main` 一律 `2`，**不**受 `--allow-nogit` 影响；
      · `io`      —— 起不来／非零退出（且不是"不是 git 仓库"）⇒ 同上，`2` 且不降级。

    起因（不这么做会漏什么）：原来"任何非零"都混成同一句原因串 ⇒「确无 `.git`」与
    「有 git 但没跑成」**看不出区别**，于是 `--allow-nogit` 这种"给分发形态用的降级"
    会把真故障一起降级成绿。

    ⚠️ `subprocess.TimeoutExpired` **不是** `OSError` 的子类 ⇒ 必须**单独一支**，
    `except OSError` 兜不住它（缺了这支就是一段 traceback）。
    """
    files = []
    seen = set()
    for extra in (["ls-files", "-z"], ["ls-files", "--others", "--exclude-standard", "-z"]):
        try:
            proc = subprocess.run(
                ["git", "-C", root] + extra,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace",
                timeout=_GIT_TIMEOUT, env=_git_env())
        except subprocess.TimeoutExpired:
            return None, {"kind": "timeout",
                          "msg": "`git %s` 超时（上限 %d 秒），已终止"
                                 % (" ".join(extra), _GIT_TIMEOUT)}
        except OSError as exc:
            return None, {"kind": "io", "msg": "无法执行 git：%s" % exc}
        if proc.returncode != 0:
            err_txt = (proc.stderr or "").strip()
            # 「不是 git 仓库」是**形态**，别的非零是**故障** —— 两者退出码不同，⛔ 不许混成一个原因串。
            kind = "no_git" if "not a git repository" in err_txt.lower() else "io"
            return None, {"kind": kind,
                          "msg": "`git %s` 返回 %d：%s" % (" ".join(extra), proc.returncode, err_txt)}
        for rel in _split_z(proc.stdout):
            if not rel or rel in seen:
                continue
            seen.add(rel)
            files.append(rel)
    return files, None


def _scan_files(root: str, files, patterns):
    """扫文件集，返回 `(命中列表, 实扫文件数, 跳过列表, 读不出的列表, 缺失列表)`。

    三个"没扫"的桶**必须分开**（⛔ 不许合并，也不许互相塞）：

      · `skipped`    —— **有意排除**：二进制（按扩展名，见 `_BINARY_EXT`）＋ 目录项（子模块 gitlink）；
      · `unreadable` —— **应扫却读不出**：文件在、但坏编码／读不动，元素为 `(相对路径, 原因)`；
      · `missing`    —— **索引里有、盘上无**（staged 删除／sparse-checkout）：**没有内容可泄露**，
                       只打 `[note]`、**不计 rc**。

    起因（不这么做会漏什么）：前两者同桶时，"读不出"会被当成"有意排除"，扫描面残缺仍报
    `ALL OK`、`rc=0` —— 那是把缺陷伪装成通过；而把"缺失"算进"读不出"则相反：**假红**，
    实际后果是逼人给门禁加"失败也放行"的兜底写法。
    """
    hits = []
    skipped = []
    unreadable = []
    missing = []
    scanned = 0
    for rel in files:
        if os.path.splitext(rel)[1].lower() in _BINARY_EXT:
            skipped.append(rel)
            continue
        path = os.path.join(root, rel.replace("/", os.sep))
        if os.path.isdir(path):
            # `git ls-files` 会列出**目录项**（子模块 gitlink、稀疏检出的目录）——目录不是"文本读不出"，
            #   把它算进 `unreadable` 会让子模块仓一律 rc=2（新增假红）。有意的排除，进跳过桶。
            skipped.append(rel)
            continue
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                text = fh.read()
        except FileNotFoundError as exc:
            # ⚠️ 必须写在 `except OSError` **之前** —— 两者同为 `OSError` 子类，顺序反了会把
            #   "权限不足"也归成"文件缺失"，于是静静不计 rc（那是假绿）。
            #   语义：索引里有、盘上无（staged 删除／sparse-checkout）⇒ **没有内容可泄露**，
            #   扫描面并未残缺 ⇒ 第三桶，只打 `[note]`、**不计 rc**（判 2 是假红）。
            #   ⚠️ 原因串只留 **OS 原文**：外层 note 已经念过「索引里有、盘上无」，内层再念一遍
            #   就成了「…（索引里有、盘上无（No such file…））」（`W3`）。
            missing.append((rel, str(getattr(exc, "strerror", None) or exc)))
            continue
        except UnicodeDecodeError as exc:        # 坏编码：**不是** OSError，必须自己一支
            unreadable.append((rel, "坏编码（%s）" % type(exc).__name__))
            continue
        except OSError as exc:
            unreadable.append((rel, "读不动（%s）" % (getattr(exc, "strerror", None) or exc)))
            continue
        scanned += 1
        is_py = rel.endswith(".py")
        for ln, klass, tok in _scan_text(text, is_py, patterns):
            hits.append((rel, ln, klass, tok))
    return hits, scanned, skipped, unreadable, missing


def _clip(tok: str, keep: int = 4) -> str:
    """命中串只露极少前缀（避免把疑似机密原样打进日志），其余只报长度。"""
    if len(tok) <= keep:
        return tok
    return tok[:keep] + "…（共 %d 字）" % len(tok)


def _rmtree_tmp(path: str) -> None:
    """删临时目录 —— Windows 上**必须先去只读位**。

    起因（不这么做会漏什么）：`shutil.rmtree(path, ignore_errors=True)` 遇到只读文件会**静默失败**
    （`ignore_errors` 把异常吞了），而 `git init` 出来的 `.git/objects/*` 在 Windows 上是只读的
    ⇒ 每跑一次自检就在 `%TEMP%` 留一棵含仓库的树，永远删不掉（实测残留 41＋26 个）。
    """
    for _dirpath, _dirs, _files in os.walk(path):
        for _name in _files + _dirs:
            try:
                os.chmod(os.path.join(_dirpath, _name), 0o700)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


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
    # 本函数专用（都在标准库里，⛔ 不装新依赖）：`mock` 做参数 spy / 异常注入，`io`＋`contextlib`
    #   用来接住 `main()` 的输出（那些分支的判据是"输出里有没有那句话"）。
    from unittest import mock
    import contextlib
    import io

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
    # 省略号落在**中间**的形态：`_RE_DRIVE` 只吃到盘符加第一段，占位符在候选内 ⇒ 才真正考到"按候选判"。
    _ph_mid = "C" + ":" + "\\" + "Users" + "\\" + "\u2026" + "\\" + "proj"
    negatives = (
        ("平台锚点", "\n".join([
            "p = 'wb/modules/order/list.xwl'",
            "q = 'wb/system/controls.json'",
            "r = 'com.wb.foo.Bar'",
            "j = 'WEB-INF/lib/anything.jar'",
        ])),
        # ⚠️ 这一组必须用**裸串**：`repr()` 会把反斜杠变成双写 ⇒ `_RE_DRIVE` 的 `(?![\\/])` 直接不匹配
        #   ⇒ 夹具根本不进入被测量的分支，改前改后都"零误报"（那就是**空判**）。
        ("占位路径·示意行", "\n".join([
            "p = " + _ph_win,
            "q = " + _ph_dots,
            "r = " + _ph_mid,
        ])),
        ("占位邮箱", "e = " + repr("user" + "@" + "example" + "." + "com")),
        ("视网膜资源名", "css = " + repr("icon" + "@" + "2x" + "." + "png")),
        ("普通代码", "def add(a, b):\n    return a + b\n"),
    )
    for name, text in negatives:
        got = _scan_text(text, True, [])
        if got:
            fails.append("反例误报：%s ⇒ %s" % (name, got))

    # 阳性对照：证明上面那组「占位路径」夹具**不是空判** —— 把占位段换成真实用户名，同一前缀必须命中。
    _real_win = "C" + ":" + "\\" + "Users" + "\\" + "zh" + "ang" + "\\" + "proj"
    if not any(k == "本机路径" for _, k, _ in _scan_text(_real_win, True, [])):
        fails.append("「占位路径」夹具是空判：真实用户名形态竟也不命中（夹具没进入被测量的分支）：%s"
                     % (_scan_text(_real_win, True, []),))

    # ---- 占位豁免：按**路径段**判（口径定稿版）----
    #   判据一句话：**整段**才是占位（`<…>`／`…`／`...`／`~`／`RUNNER[~N]`），段中间出现 `<` 不算。
    #   ⚠️ 期望值一律**手推**并写死在表里，⛔ 不用被测函数现算（那是自证循环）。
    #   ⛔ 也不许把"该报的"写成"看它报不报"——每条都给 want，红了才归因得清。
    _P = "C" + ":" + "\\" + "Users" + "\\" + "zh" + "ang" + "\\" + "proj"
    _PU = "C" + ":" + "/" + "Users" + "/" + "zh" + "ang" + "/" + "proj"
    _pl_cases = (
        # 9 条「应报」：同一行别处有占位/尖括号，但**被匹配的那条路径是真的**
        ("L1 行尾注释含尖括号", 'p = "' + _P + '"  # 见 <文档>', True),
        ("L2 双空格＋注释", 'p = ' + _P + '  # 见 <文档>', True),
        ("L3 同一行两条路径（先真后占位）", "cp " + _P + " " + "D" + ":" + "\\" + "bak\\<user>\\", True),
        ("L4 空格＋中文占位", 'p = ' + _P + ' 与 <客户> 相关', True),
        ("L5 前置英文＋占位", "see <doc> at " + _P, True),
        ("L6 重定向到 nul", "dir " + _P + " > <nul>", True),
        ("L7 省略号在路径后", "p = " + _P + " \u2026 见上", True),
        ("L8 路径后跟 RUNNER", "p = " + _P + " RUNNER", True),
        ("L9 路径后跟尖括号", "x = " + _P + " <b>", True),
        ("F2 正斜杠＋行尾注释", 'p = "' + _PU + '"  # 参考 <文档>', True),
        # 应放：占位段整段成立
        ("Q8 括号目录＋占位段", "C" + ":" + "\\" + "Program Files (x86)" + "\\" + "<user>"
                                + "\\" + "proj", False),
        ("F1-1 runner 短名", "C" + ":" + "\\" + "Users" + "\\" + "RUNNER~1" + "\\" + "proj", False),
        ("F1-2 尖括号段", "C" + ":" + "\\" + "Users" + "\\" + "<user>" + "\\" + "proj", False),
        ("F1-3 省略号段", "C" + ":" + "\\" + "Users" + "\\" + "\u2026" + "\\" + "proj", False),
        ("F3-放 带空格目录＋占位段", '"' + "C" + ":" + "\\" + "Program Files" + "\\" + "<user>"
                                    + "\\" + "proj" + '"', False),
        # 应报：真实路径
        ("F3-报 带空格目录＋真实名", '"' + "C" + ":" + "\\" + "Program Files" + "\\" + "zh"
                                     + "ang" + "\\" + "proj" + '"', True),
        ("裸路径", _P, True),
        # 6 条压力例（定稿 §1.2）
        ("S1 括号目录＋真实名", "C" + ":" + "\\" + "Program Files (x86)" + "\\" + "zh"
                                + "ang" + "\\" + "proj", True),
        ("S2 真实路径带两个空格段", "C" + ":" + "\\" + "Program Files" + "\\" + "My App" + "\\"
                                    + "zh" + "ang", True),
        ("S3 注释里占位但路径真实", 'p = "' + _P + '"  # 见 <user>', True),
        ("S4 双路径先占位后真", "cp " + "C" + ":" + "\\" + "bak\\<user>\\ " + _P, True),
        ("S5 制表符后跟注释占位", "p = " + _P + "\t# 见 <user>", True),
        ("S6 MYRUNNERX 不是 runner 短名", "C" + ":" + "\\" + "Users" + "\\" + "MY" + "RUNNERX"
                                            + "\\" + "proj", True),
        ("S7 段中间有单个 `<`", "C" + ":" + "\\" + "Users" + "\\" + "zh" + "ang" + "\\" + "a<b.py", True),
    )
    for _pl_lbl, _pl_txt, _pl_want in _pl_cases:
        _pl_got = _scan_text(_pl_txt, True, [])
        _pl_hit = any(k == "本机路径" for _, k, _ in _pl_got)
        if _pl_hit != _pl_want:
            fails.append("占位判定错：%s ⇒ 应%s、实%s（实得 %s；行：%r）"
                         % (_pl_lbl, "报" if _pl_want else "放过", "报" if _pl_hit else "放过",
                            _pl_got, _pl_txt))

    # 「报告什么」与「报几次」：命中串必须是**整段候选**（不是盘符后那一段），
    #   且同一条路径只报一次（两个正则都会命中它，候选扩展后是同一串）。
    _dup_line = 'p = "' + _PU + '"  # x'
    _dup_got = [t for _, k, t in _scan_text(_dup_line, True, []) if k == "本机路径"]
    if len(_dup_got) != 1:
        fails.append("同一条路径被重复报（应 1 条，实 %d 条）：%s（行：%r）"
                     % (len(_dup_got), _dup_got, _dup_line))
    elif _dup_got[0] != _PU:
        fails.append("命中串不是整段候选（应 %r，实 %r）—— 报首段对定位无价值" % (_PU, _dup_got[0]))

    # 「夹具非空判」的控制：`C:\…`（盘符后直接省略号）**进不了** `_RE_DRIVE`
    #   （`{2,}` 那一段要求首段含字母数字）⇒ 用中间带省略号的形态来证明"占位判定真的跑到了"。
    if not list(_RE_DRIVE.finditer(_ph_mid)):
        fails.append("占位夹具 `%r` 根本没触发 `_RE_DRIVE`（夹具空判，测不到候选豁免）" % (_ph_mid,))

    # 平台锚点行仍放行（那条放行面不属本段射程，不许因此退）。
    #   ⚠️ 这条**只证"没退"，不证放行面**：夹具是相对路径，本来就不进两个正则（删掉 `_anchor_in`
    #   也绿）。平台锚点的放行面由上面那组"平台锚点"反例承担，此处别当它是防线。
    _f4 = "p = 'wb/modules/order/list.xwl'"
    _f4_got = _scan_text(_f4, True, [])
    if _f4_got:
        fails.append("平台锚点行不再放行 ⇒ %s" % (_f4_got,))

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

        # 清单**元素类型先验**：`{"identifiers": "acme"}` 会被 `list("acme")` 拆成四个单字母
        #   标识（⇒ 全仓误报），元素非字符串则被 `str()` 静默转串（⇒ 静默降级）。两者都必须报错。
        #   最后一组是**阳性对照**：正常清单不许被这条先验误拒。
        _bad_lists = (
            ("字段给了字符串而不是数组", {"identifiers": "acme"}),
            ("元素不是字符串", {"identifiers": [1]}),
            ("path_fragments 不是数组", {"path_fragments": {"a": 1}}),
            ("顶层数组里混了非字符串", ["ok_id", 7]),
        )
        for _bi, (_lbl, _payload) in enumerate(_bad_lists):
            _bp = os.path.join(tmp, "bad_list_%d.json" % _bi)
            with open(_bp, "w", encoding="utf-8") as _fh:
                json.dump(_payload, _fh, ensure_ascii=False)
            try:
                _load_patterns(_bp)
                fails.append("清单类型先验失效：%s 竟被当成有效清单" % _lbl)
            except PatternError:
                pass
        _good = os.path.join(tmp, "good_list.json")
        with open(_good, "w", encoding="utf-8") as _fh:
            json.dump({"identifiers": ["ok_id"]}, _fh, ensure_ascii=False)
        try:
            _good_items = _load_patterns(_good)
        except PatternError as _exc:
            fails.append("正常清单被类型先验误拒（阳性对照）：%s" % _exc)
        else:
            if _good_items != ["ok_id"]:
                fails.append("正常清单的解析结果不对（应为 ['ok_id']）：%r" % (_good_items,))

        # 畸形清单走 `main` 时**必须非零、且不吞错**（`PatternError` 不许被 catch 成"0 命中通过"）。
        _d4 = os.path.join(tmp, "bad_list_cli.json")
        with open(_d4, "w", encoding="utf-8") as _fh:
            json.dump({"identifiers": "acme"}, _fh, ensure_ascii=False)
        _d4_buf = io.StringIO()
        with contextlib.redirect_stdout(_d4_buf):
            _d4_rc = main(["--patterns", _d4, "--root", tmp])
        _d4_out = _d4_buf.getvalue()
        if _d4_rc == 0:
            fails.append("畸形清单走 CLI 竟 rc=0（吞错了）：%s" % _d4_out)
        if "[FAIL] privacy_scan 外置业务标识清单：" not in _d4_out:
            fails.append("畸形清单走 CLI 时没打印 `[FAIL] privacy_scan 外置业务标识清单：…`：%s" % _d4_out)
    finally:
        _rmtree_tmp(tmp)

    # ---- 子进程边界：`git` 的 timeout ／ 显式 env ／ 错误三档 ----
    #   五条各管一件事，⛔ 不合并：第一条量**入参**（不靠"代码里看着有"）、第二条量超时分支、
    #   第三条量"不降级"、第四条量真仓库能走通、第五条量"不是 git 仓库"仍按原语义。
    _g_tmp = tempfile.mkdtemp(prefix="privacy_scan_git_")
    try:
        # T1 参数 spy：截 `_collect_files` 里 `subprocess.run` 的**实际 kwargs**。
        _spy_calls = []

        class _SpyProc:
            returncode = 0
            stdout = ""
            stderr = ""

        def _spy_run(cmd, **kw):
            _spy_calls.append((cmd, kw))
            return _SpyProc()

        # ⚠️ 先把父环境里的这两个变量**改成错值**再断言 —— 否则本机 `os.environ` 里若已是 "0"，
        #   删掉实现也照样绿（实测过：父进程已带该值，这条断言本来是空的）。
        with mock.patch.dict(os.environ, {"GIT_TERMINAL_PROMPT": "1", "GIT_OPTIONAL_LOCKS": "1"}):
            with mock.patch("subprocess.run", _spy_run):
                _t1_files, _t1_err = _collect_files(_g_tmp)
        if len(_spy_calls) != 2:
            fails.append("T1 应跑满两条 `git ls-files`（含 `--others`），实得 %d 次调用" % len(_spy_calls))
        for _cmd, _kw in _spy_calls:
            if not _cmd or _cmd[-1] != "-z":
                fails.append("T1 有一处 `git ls-files` 没带 `-z`（文件名边界就丢了）：%r" % (_cmd,))
        _kw0 = _spy_calls[0][1] if _spy_calls else {}
        _to = _kw0.get("timeout")
        # `type(...) is not int`：`bool` 是 `int` 子类，`timeout=True` 会被 `isinstance` 放过（＝1 秒）。
        if type(_to) is not int or _to != _GIT_TIMEOUT or _to <= 0:
            fails.append("T1 子进程没带**正的 int** timeout（实得 %r，期望 %r）" % (_to, _GIT_TIMEOUT))
        _env0 = _kw0.get("env")
        if not isinstance(_env0, dict):
            fails.append("T1 子进程没带显式 env（实得 %r）" % (_env0,))
        else:
            if _env0.get("GIT_TERMINAL_PROMPT") != "0":
                fails.append("T1 env 没把 GIT_TERMINAL_PROMPT 改写成 0（实得 %r）"
                             % (_env0.get("GIT_TERMINAL_PROMPT"),))
            if _env0.get("GIT_OPTIONAL_LOCKS") != "0":
                fails.append("T1 env 没把 GIT_OPTIONAL_LOCKS 改写成 0（实得 %r）"
                             % (_env0.get("GIT_OPTIONAL_LOCKS"),))
            if not _env0.get("PATH"):
                fails.append("T1 env 丢了 PATH（`env=` 会整体替换环境，子进程会找不到 git）")

        # T2 超时分支：`TimeoutExpired` 不是 `OSError` 子类 ⇒ 少了那一支就是 traceback。
        _boom = subprocess.TimeoutExpired(["git"], _GIT_TIMEOUT)
        with mock.patch("subprocess.run", side_effect=_boom):
            _t2_files, _t2_err = _collect_files(_g_tmp)
        if not isinstance(_t2_err, dict) or _t2_err.get("kind") != "timeout":
            fails.append("T2 超时没被识别成 kind=timeout（实得 %r）" % (_t2_err,))
        _t2_buf, _t2_ebuf = io.StringIO(), io.StringIO()
        try:
            with mock.patch("subprocess.run", side_effect=_boom):
                with contextlib.redirect_stdout(_t2_buf), contextlib.redirect_stderr(_t2_ebuf):
                    _t2_rc = main(["--root", _g_tmp])
        except BaseException as _exc:      # noqa: BLE001 —— 抛出来本身就是"没接住"的证据
            fails.append("T2 超时路径抛了异常（应只回 rc=2）：%s: %s" % (type(_exc).__name__, _exc))
            _t2_rc = None
        _t2_out = _t2_buf.getvalue() + _t2_ebuf.getvalue()   # ⚠️ traceback 走 **stderr**，两路都要接
        if _t2_rc != 2:
            fails.append("T2 超时后 rc=%r（应 2）：%s" % (_t2_rc, _t2_out))
        if "超时" not in _t2_out:
            fails.append("T2 超时后输出里看不出「超时」：%s" % _t2_out)
        if "Traceback" in _t2_out:
            fails.append("T2 超时冒了 traceback：%s" % _t2_out)

        # T3 不降级：`--allow-nogit` 只对"确无 .git"生效，⛔ 不许把超时降级成 0。
        _t3_buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=_boom):
            with contextlib.redirect_stdout(_t3_buf):
                _t3_rc = main(["--root", _g_tmp, "--allow-nogit"])
        if _t3_rc != 2:
            fails.append("T3 超时 + `--allow-nogit` 被降级成 rc=%r（必须仍 2）：%s"
                         % (_t3_rc, _t3_buf.getvalue()))

        # T6 `io` 档（git 起不来）：单要求它与超时**同等**（一律 2、不降级），原来这档零覆盖。
        _io_boom = FileNotFoundError(2, "No such file or directory")
        with mock.patch("subprocess.run", side_effect=_io_boom):
            _t6_files, _t6_err = _collect_files(_g_tmp)
        if not isinstance(_t6_err, dict) or _t6_err.get("kind") != "io":
            fails.append("T6 `git` 起不来没被判成 kind=io（实得 %r）" % (_t6_err,))
        _t6_buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=_io_boom):
            with contextlib.redirect_stdout(_t6_buf):
                _t6_rc = main(["--root", _g_tmp])
        if _t6_rc != 2:
            fails.append("T6 `git` 起不来时 rc=%r（应 2）：%s" % (_t6_rc, _t6_buf.getvalue()))
        _t6b_buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=_io_boom):
            with contextlib.redirect_stdout(_t6b_buf):
                _t6b_rc = main(["--root", _g_tmp, "--allow-nogit"])
        if _t6b_rc != 2:
            fails.append("T6 `io` 档 + `--allow-nogit` 被降级成 rc=%r（必须仍 2）：%s"
                         % (_t6b_rc, _t6b_buf.getvalue()))

        # T4 阳性对照（真仓库）：临时目录 `git init` ＋ `git add -A`（⛔ 不 commit —— CI 无 user.email）。
        #   ⚠️ 仓库建在**临时目录**里（本仓之外），⛔ 不在本仓内 git init。
        _repo = os.path.join(_g_tmp, "repo")
        os.makedirs(_repo)
        _gi = subprocess.run(["git", "init", "-q", _repo],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if _gi.returncode != 0:
            fails.append("T4 建临时仓库失败（`git init` rc=%d）：%s"
                         % (_gi.returncode, (_gi.stderr or b"").decode("utf-8", "replace")))
        with open(os.path.join(_repo, "ok.py"), "w", encoding="utf-8", newline="") as fh:
            fh.write("x = 1\n")
        subprocess.run(["git", "-C", _repo, "add", "-A"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _t4_files, _t4_err = _collect_files(_repo)
        if _t4_err is not None:
            fails.append("T4 真仓库竟取不到清单（err=%r）" % (_t4_err,))
        elif "ok.py" not in (_t4_files or []):
            fails.append("T4 真仓库清单里没有 ok.py（实得 %r）" % (_t4_files,))
        _t4_buf = io.StringIO()
        with contextlib.redirect_stdout(_t4_buf):
            _t4_rc = main(["--root", _repo])
        if _t4_rc != 0:
            fails.append("T4 真仓库扫描 rc=%r（应 0）：%s" % (_t4_rc, _t4_buf.getvalue()))

        # T5 区分原因（非仓库）：`no_git` 走**原语义** —— 默认 1、`--allow-nogit` 降到 0 并留降级 note。
        _no_git = os.path.join(_g_tmp, "nogit")
        os.makedirs(_no_git)
        _t5_files, _t5_err = _collect_files(_no_git)
        if not isinstance(_t5_err, dict) or _t5_err.get("kind") != "no_git":
            fails.append("T5 非仓库目录没被识别成 kind=no_git（实得 %r）" % (_t5_err,))
        _t5_buf = io.StringIO()
        with contextlib.redirect_stdout(_t5_buf):
            _t5_rc = main(["--root", _no_git])
        if _t5_rc != 1:
            fails.append("T5 非仓库且未 `--allow-nogit` 时 rc=%r（应 1）：%s"
                         % (_t5_rc, _t5_buf.getvalue()))
        _t5b_buf = io.StringIO()
        with contextlib.redirect_stdout(_t5b_buf):
            _t5b_rc = main(["--root", _no_git, "--allow-nogit"])
        if _t5b_rc != 0:
            fails.append("T5 非仓库 + `--allow-nogit` 时 rc=%r（应 0）：%s"
                         % (_t5b_rc, _t5b_buf.getvalue()))
        if "降级" not in _t5b_buf.getvalue():
            fails.append("T5 `--allow-nogit` 降级时没留降级说明：%s" % _t5b_buf.getvalue())
    finally:
        _rmtree_tmp(_g_tmp)
    # 临时目录必须真删掉：Windows 上 `.git/objects/*` 只读，`rmtree(ignore_errors=True)` 会**静默失败**
    #   ⇒ 每跑一次就在 `%TEMP%` 留一棵含仓库的树（实测残留几十个）。这条断言守的就是那个坑。
    if os.path.exists(_g_tmp):
        fails.append("临时目录没删掉（Windows 只读文件 ⇒ rmtree 静默失败）：%s" % _g_tmp)

    # ---- 文件名边界（NUL 拆分）＋ 读失败分桶 ＋ 四格退出码 ----
    #   判据分两层取证：① 直接调 `_scan_files` 拿**四元组**（`main` 只回 int，看不到桶的归属）；
    #   ② 另跑 `main` 拿 rc 与输出。⛔ 不许拿 rc 去反推桶。
    # ⚠️ 样例要**带前导与尾随空格**：只给 `"a b"` 证不了"⛔ 不得 strip"（那种名字 strip 了也不变）。
    _z_ok = _split_z(" a b \0c\nd\0")
    if _z_ok != [" a b ", "c\nd"]:
        fails.append("NUL 拆分不对（前导/尾随空格与内嵌换行都要原样保留）：实得 %r，"
                     "期望 [' a b ', 'c\\nd']" % (_z_ok,))

    _g2 = tempfile.mkdtemp(prefix="privacy_scan_bucket_")

    def _mk_repo(_name, _files):
        """建一个**仓外**临时 git 仓库：只 `git add -A`，⛔ 不 commit（CI runner 无 user.email）。"""
        _d = os.path.join(_g2, _name)
        os.makedirs(_d, exist_ok=True)
        _gi = subprocess.run(["git", "init", "-q", _d],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if _gi.returncode != 0:
            fails.append("建临时仓库 %s 失败（`git init` rc=%d）：%s"
                         % (_name, _gi.returncode, (_gi.stderr or b"").decode("utf-8", "replace")))
        for _rel, _data in _files:
            _p = os.path.join(_d, _rel)
            _pd = os.path.dirname(_p)
            if _pd:
                os.makedirs(_pd, exist_ok=True)
            with open(_p, "wb") as _fh:
                _fh.write(_data)
        subprocess.run(["git", "-C", _d, "add", "-A"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return _d

    try:
        # 真实文件名实扫：前导空格 / 中文 / 单引号都必须**原样**回得来。
        #   ⚠️ Windows 表示不了"名字里含换行"的文件 ⇒ 那种形态只由上面的单元样例覆盖。
        _weird = (" lead.xwl", "中文.xwl", "a'b.xwl")
        _r2 = _mk_repo("names", [(n, b"x = 1\n") for n in _weird])
        _f2, _e2 = _collect_files(_r2)
        if _e2 is not None:
            fails.append("文件名实扫：取不到清单（err=%r）" % (_e2,))
        else:
            _missing = [n for n in _weird if n not in (_f2 or [])]
            if _missing:
                fails.append("文件名实扫：这些名字没原样回来 %r（实得 %r）—— 前导空格/引号被吃掉了？"
                             % (_missing, _f2))

        # 未跟踪文件：只能由第二处 `ls-files --others -z` 取到 ⇒ 那条命令删掉/丢 `-z` 都该红。
        _r2b = _mk_repo("untracked", [("tracked.py", b"x = 1\n")])
        with open(os.path.join(_r2b, "loose.py"), "w", encoding="utf-8", newline="") as _fh:
            _fh.write("y = 2\n")            # 故意**不** `git add` —— 只剩 `--others` 这条路
        _fu, _eu = _collect_files(_r2b)
        if "loose.py" not in (_fu or []):
            fails.append("未跟踪文件没被清单取到（第二处 `ls-files --others` 失效）：实得 %r" % (_fu,))
        _hu, _su, _sku, _unu, _mu = _scan_files(_r2b, _fu or [], [])
        if _su != 2:
            fails.append("未跟踪文件没被实扫（scanned=%r，应 2：tracked.py ＋ loose.py）" % (_su,))

        # 读失败分桶：① 四元组看桶归属；② main 看 rc 与输出。
        _bad = b"\xff\xfe\x00\x41"          # 不是合法 UTF-8，且扩展名不是二进制
        _r3 = _mk_repo("unreadable", [("bad.txt", _bad)])
        _f3, _e3 = _collect_files(_r3)
        _h3, _s3, _sk3, _un3, _m3 = _scan_files(_r3, _f3 or [], [])
        if [r for r, _why in _un3] != ["bad.txt"]:
            fails.append("读失败没进 `unreadable` 桶（实得 %r）" % (_un3,))
        if "bad.txt" in _sk3:
            fails.append("读失败被塞进了**跳过**桶（那是「有意排除的二进制」的位置）")
        if _s3 != 0:
            fails.append("读失败的文件竟被计入实扫数（scanned=%r，应 0）" % (_s3,))
        _b3 = io.StringIO()
        with contextlib.redirect_stdout(_b3):
            _rc3 = main(["--root", _r3])
        _o3 = _b3.getvalue()
        if _rc3 != 2:
            fails.append("全部应扫文本读不出时 rc=%r（应 2）：%s" % (_rc3, _o3))
        # ⚠️ 判"整段不出现"而不是"末行不是"：在 FAIL 行**之前**插一句 `ALL OK` 也能骗过末行判法。
        if "=== privacy_scan ALL OK" in _o3:
            fails.append("读失败时输出里仍出现 `ALL OK`（读失败不算通过）：%s" % _o3)
        if "未完成" not in _o3 and "读不出" not in _o3:
            fails.append("读失败时输出里看不出「未完成／读不出」：%s" % _o3)
        if "实扫 0 个" not in _o3:
            fails.append("全读失败时没明示「实扫 0 个」（单：scanned==0 必须被看见）：%s" % _o3)

        # 第三桶 `missing`：索引里有、盘上无（staged 删除）⇒ 只打 `[note]`、**不计 rc**。
        #   ⚠️ 这条同时守着 `except FileNotFoundError` 与 `except OSError` 的**先后**：
        #   顺序反了，「缺失」会被归成「读不出」⇒ rc 变 2（假红）。
        _rm = _mk_repo("missing", [("gone.py", b"x = 1\n"), ("keep.py", b"y = 2\n")])
        os.remove(os.path.join(_rm, "gone.py"))
        _fm, _em = _collect_files(_rm)
        _hm, _sm, _skm, _unm, _mm = _scan_files(_rm, _fm or [], [])
        if [r for r, _w in _mm] != ["gone.py"]:
            fails.append("「索引里有、盘上无」没进 `missing` 桶（实得 %r）" % (_mm,))
        if _unm:
            fails.append("「索引里有、盘上无」被算成「读不出」⇒ 假红（rc 会被抬到 2）：%r" % (_unm,))
        if _sm != 1:
            fails.append("missing 场景的实扫数应为 1（keep.py），实得 %r" % (_sm,))
        _bm = io.StringIO()
        with contextlib.redirect_stdout(_bm):
            _rcm = main(["--root", _rm])
        _om = _bm.getvalue()
        if _rcm != 0:
            fails.append("有 missing 时 rc=%r（应 0：该桶不计 rc）：%s" % (_rcm, _om))
        if "索引里有、盘上无" not in _om:
            fails.append("有 missing 时没打「索引里有、盘上无」那句 note：%s" % _om)
        # `W3`：原因串只留 OS 原文 ⇒ 这句话整条输出里**只应出现一次**（外层 note 里）。
        if _om.count("索引里有、盘上无") != 1:
            fails.append("missing 的 note 把结论念了两遍（原因串该只留 OS 原文，W3）：%s" % _om)

        # 第四格补测：**有正常文件可读、也有读不出、且无命中** ⇒ 仍须 2。
        #   原来只锚了 `scanned==0` 那个端点 ⇒ `if unreadable and scanned == 0:` 这种把缺陷
        #   伪装成通过的实现能全绿（实测：混合仓库上打 `未完成 1 个` 之后紧跟 `ALL OK`、rc=0）。
        _r3b = _mk_repo("mixed_nohits", [("bad.txt", _bad), ("clean.py", b"x = 1\n")])
        _f3b, _e3b = _collect_files(_r3b)
        _h3b, _s3b, _sk3b, _un3b, _m3b = _scan_files(_r3b, _f3b or [], [])
        if _s3b != 1 or len(_un3b) != 1:
            fails.append("混合格夹具不对：scanned=%r（应 1）、unreadable=%r（应 1）" % (_s3b, _un3b))
        _b3b = io.StringIO()
        with contextlib.redirect_stdout(_b3b):
            _rc3b = main(["--root", _r3b])
        _o3b = _b3b.getvalue()
        if _rc3b != 2:
            fails.append("「有读不出、无命中、有正常文件」时 rc=%r（应 2）：%s" % (_rc3b, _o3b))
        if "=== privacy_scan ALL OK" in _o3b:
            fails.append("混合格（无命中＋有读不出）竟报 `ALL OK`：%s" % _o3b)
        if "实扫 1 个" not in _o3b:
            fails.append("混合格没明示「实扫 1 个」：%s" % _o3b)

        # 命中 ＋ 失败并存：rc=1，命中行与未完成行**同时**出现。
        _r4 = _mk_repo("both", [("bad.txt", _bad),
                                ("hit.py", ("v = " + repr(_mail) + "\n").encode("utf-8"))])
        _b4 = io.StringIO()
        with contextlib.redirect_stdout(_b4):
            _rc4 = main(["--root", _r4])
        _o4 = _b4.getvalue()
        if _rc4 != 1:
            fails.append("命中＋读失败并存时 rc=%r（应 1）：%s" % (_rc4, _o4))
        if "命中邮箱" not in _o4:
            fails.append("命中＋读失败并存时没列命中行：%s" % _o4)
        if "未完成" not in _o4 and "读不出" not in _o4:
            fails.append("命中＋读失败并存时没列未完成行（未读文件被当成干净）：%s" % _o4)

        # 子模块（gitlink／目录项）：`git ls-files` 会把它列出来，但它**不是文本文件**
        #   ⇒ 必须进"跳过"、⛔ 不许算"读不出"（否则子模块仓一律 rc=2，是新增假红）。
        _rg = _mk_repo("gitlink", [("a.py", b"x = 1\n")])
        _gl = subprocess.run(["git", "-C", _rg, "update-index", "--add", "--cacheinfo",
                              "160000,1234567890123456789012345678901234567890,fakesub"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if _gl.returncode == 0:
            # 造出**工作副本目录**（真实子模块检出的形态）。⚠️ "索引里有、盘上无"属于另一类
            #   （tracked-but-deleted），口径未定，本段不测、也不改它的行为。
            os.makedirs(os.path.join(_rg, "fakesub"), exist_ok=True)
            _fg, _eg = _collect_files(_rg)
            _hg, _sg, _skg, _ung, _mg = _scan_files(_rg, _fg or [], [])
            if "fakesub" not in (_fg or []):
                fails.append("gitlink 夹具没生效（清单里没有 fakesub）：实得 %r" % (_fg,))
            if _ung:
                fails.append("子模块目录项被算成「读不出」（应进跳过桶）：%r" % (_ung,))
            if "fakesub" not in _skg:
                fails.append("子模块目录项没进跳过桶（实得 skipped=%r）" % (_skg,))
            _bg = io.StringIO()
            with contextlib.redirect_stdout(_bg):
                _rcg = main(["--root", _rg])
            if _rcg != 0:
                fails.append("含子模块目录项的仓库 rc=%r（应 0）：%s" % (_rcg, _bg.getvalue()))
        else:
            fails.append("子模块夹具没造出来（`git update-index` rc=%d）：%s"
                         % (_gl.returncode, (_gl.stderr or b"").decode("utf-8", "replace")))

        # 全二进制 ⇒ 0（**与"全读失败"是两回事**，⛔ 不许合并成一格）。
        _r6 = _mk_repo("binary", [("pic.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)])
        _f6, _e6 = _collect_files(_r6)
        _h6, _s6, _sk6, _un6, _m6 = _scan_files(_r6, _f6 or [], [])
        if _un6:
            fails.append("二进制被记成了读不出（%r）—— 那是「有意排除」，不是未完成" % (_un6,))
        if "pic.png" not in _sk6:
            fails.append("二进制没进跳过桶（实得 skipped=%r）" % (_sk6,))
        _b6 = io.StringIO()
        with contextlib.redirect_stdout(_b6):
            _rc6 = main(["--root", _r6])
        if _rc6 != 0:
            fails.append("全二进制仓库 rc=%r（应 0）：%s" % (_rc6, _b6.getvalue()))

        # 阳性对照：正常仓库、无坏文件 ⇒ rc=0 ＋ 末行 ALL OK ＋ 读不出为空。
        _r7 = _mk_repo("clean", [("ok.py", b"x = 1\n")])
        _f7, _e7 = _collect_files(_r7)
        _h7, _s7, _sk7, _un7, _m7 = _scan_files(_r7, _f7 or [], [])
        if _un7:
            fails.append("干净仓库竟有读不出的文件（%r）" % (_un7,))
        _b7 = io.StringIO()
        with contextlib.redirect_stdout(_b7):
            _rc7 = main(["--root", _r7])
        _o7 = _b7.getvalue()
        if _rc7 != 0:
            fails.append("干净仓库 rc=%r（应 0）：%s" % (_rc7, _o7))
        if _o7.strip().splitlines()[-1:] != ["=== privacy_scan ALL OK"]:
            fails.append("干净仓库末行不是 `=== privacy_scan ALL OK`：%s" % _o7)

        # 零可扫文件（`files == []`）：`rc` 仍 0，但末行必须与"扫了 N 个都干净"区分开。
        #   ⚠️ 定稿裁定**替换**末行而不是新增：仓内多处按"末行唯一"读，新增一行会让它们读到不同结果。
        _r8 = _mk_repo("empty", [])
        _f8, _e8 = _collect_files(_r8)
        if _f8:
            fails.append("空仓夹具不空（实得 %r）" % (_f8,))
        _b8 = io.StringIO()
        with contextlib.redirect_stdout(_b8):
            _rc8 = main(["--root", _r8])
        _o8 = _b8.getvalue()
        if _rc8 != 0:
            fails.append("零可扫文件时 rc=%r（应 0：没有漏扫对象）：%s" % (_rc8, _o8))
        if _o8.strip().splitlines()[-1:] != ["=== privacy_scan OK（未发现可扫描文件）"]:
            fails.append("零可扫文件时末行不是 `=== privacy_scan OK（未发现可扫描文件）`：%s" % _o8)
        if "=== privacy_scan ALL OK" in _o8:
            fails.append("零可扫文件时仍出现 `ALL OK`（与「扫了 N 个都干净」不可区分）：%s" % _o8)
        if "--root" not in _o8:
            fails.append("零可扫文件时没提示「`--root` 是否指错」：%s" % _o8)
        # 措辞钉死（`W2`）：⛔ 不许用「清单为空」——那是 `--patterns` 空清单的报错文案，撞词会误导。
        if "未发现可跟踪文件" not in _o8:
            fails.append("零可扫文件时的 note 文案不对（应含「未发现可跟踪文件」）：%s" % _o8)
        if "清单为空" in _o8:
            fails.append("零可扫文件时用了「清单为空」——与 `--patterns` 的报错撞词（W2）：%s" % _o8)
    finally:
        _rmtree_tmp(_g2)

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
    print("[ok]  边界断言：`git` 子进程的 timeout／显式 env／错误三档、清单元素类型先验、"
          "NUL 拆名与读失败分桶（四格退出码）、占位豁免按**路径段**判（段内 `<` 不算占位）")
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

    files, err = _collect_files(root)
    if files is None:
        # ⚠️ 三处消费点一律取 `err["msg"]`（⛔ 不把 dict 直接交给 `%s`，那会把 `{'kind': …}` 打进输出）。
        _kind = (err or {}).get("kind")
        _msg = (err or {}).get("msg") or err
        if _kind == "no_git":
            if args.allow_nogit:
                print("[note] privacy_scan：取不到 git 清单 ⇒ 本次**没扫**"
                      "（`--allow-nogit` 降级：不算通过也不算失败）：%s" % _msg)
                print("=== privacy_scan ALL OK")
                return 0
            print("[FAIL] privacy_scan：取不到 git 清单 ⇒ 本次**没扫**（默认判红 —— 静默绿是病根）。"
                  "确无 `.git`（如 zip 分发解包后）需降级时，显式加 `--allow-nogit`。原因：%s" % _msg)
            print("=== privacy_scan FAIL（1 项）")
            return 1
        # timeout ／ io：**有 git 但没跑成** ⇒ 一律 2，且 `--allow-nogit` **不生效**
        #   （它不是"确无 .git"，把这档降级成绿＝让真故障冒充通过）。
        #   ⚠️ `kind` 是**内部枚举**，⛔ 不打进用户可见文案（'io' 对"`--root` 不存在""git 没装"
        #   这两种真实成因都是误导，用 `_msg` 里的实际原因即可）。
        print("[FAIL] privacy_scan：取不到 git 清单 ⇒ 本次**没扫**。"
              "⚠️ 这一档**不受** `--allow-nogit` 降级 —— 降级只用于「确无 `.git`」这一种形态；"
              "超时／git 起不来／除「不是仓库」之外的失败，都属「有 git 却没用成」。原因：%s" % _msg)
        print("=== privacy_scan FAIL（1 项）")
        return 2

    if not files:
        # `files == []`（仓里零可跟踪的文本文件）：`rc` 仍 0（**没有漏扫对象**，判红是假红），
        #   但末行**必须**与"扫了 N 个都干净"区分开 —— 用**替换**而不是新增一行：
        #   仓内三处按"末行"读的断言（见 `main` 的 `ALL OK` 判据与自检）都依赖"末行唯一"。
        #   ⚠️ 措辞别写「清单为空」：那句是 `--patterns` 给空清单时的报错文案，撞词会让人去查清单
        #   而不是查 `--root`（`W2`）。
        print("[note] 未发现可跟踪文件：本次没有可扫描对象 —— `--root` 是否指错？"
              "（也可能是本仓只有二进制，或文件全被 `.gitignore` 排除）")
        print("=== privacy_scan OK（未发现可扫描文件）")
        return 0

    hits, scanned, skipped, unreadable, missing = _scan_files(root, files, patterns)
    list_tag = "／外置业务标识" if patterns else ""
    if skipped:
        shown = "，".join(skipped[:8])
        more = "，另有 %d 个未列" % (len(skipped) - 8) if len(skipped) > 8 else ""
        print("[note] 跳过 %d 个非文本的文件：%s%s" % (len(skipped), shown, more))
    if missing:
        # 「索引里有、盘上无」只提示、**不计 rc**：文件不在盘上 ⇒ 没有内容可泄露，
        #   扫描面并未残缺；判 2 会把 staged 删除／sparse-checkout 变成假红。
        _m_shown = "，".join("%s（%s）" % (r, why) for r, why in missing[:8])
        _m_more = "，另有 %d 个未列" % (len(missing) - 8) if len(missing) > 8 else ""
        print("[note] 索引里有、盘上无 %d 个（不计入「未完成」，不影响退出码）：%s%s"
              % (len(missing), _m_shown, _m_more))
    if unreadable:
        _u_shown = "，".join("%s（%s）" % (r, why) for r, why in unreadable[:8])
        _u_more = "，另有 %d 个未列" % (len(unreadable) - 8) if len(unreadable) > 8 else ""
        # 「未完成」**必须**单列并点名"实扫了几个"：全读失败时 `scanned=0` 要被看见，
        #   ⛔ 不许出现"0 个文件 0 命中 ⇒ ALL OK"这种假绿。
        print("[note] 未完成 %d 个文件（应扫文本**读不出** ⇒ ⛔ 不算通过；本次实扫 %d 个、"
              "跳过非文本 %d 个）：%s%s"
              % (len(unreadable), scanned, len(skipped), _u_shown, _u_more))
    if hits:
        for rel, ln, klass, tok in hits[:40]:
            print("[FAIL] privacy_scan：%s:%d 命中%s「%s」" % (rel, ln, klass, _clip(tok)))
        if len(hits) > 40:
            print("[note] 另有 %d 条命中未逐条列出" % (len(hits) - 40))
        if unreadable:
            print("[FAIL] privacy_scan：另有 %d 个应扫文本**读不出**（见上）—— 命中与未完成同时存在，"
                  "⛔ 未读文件不算干净" % len(unreadable))
        print("=== privacy_scan FAIL（%d 项）" % (len(hits) + len(unreadable)))
        return 1
    if unreadable:
        # 四格矩阵的「无命中 ＋ 有读不出」格：rc=2（**对外契约变更**：读不出从 0 变成 2）。
        print("[FAIL] privacy_scan：%d 个应扫文本**读不出**（实扫 %d 个、命中 0）⇒ 本次**没扫全**，"
              "读失败**不算通过**（⛔ 不报 ALL OK）" % (len(unreadable), scanned))
        print("=== privacy_scan FAIL（%d 项）" % len(unreadable))
        return 2
    print("[ok]  privacy_scan：扫 %d 个文件（跳过 %d 个非文本）—— "
          "本机路径（.py）/ 邮箱 / 手机号 / 疑似 token / uid 形状%s 均 0 命中"
          % (scanned, len(skipped), list_tag))
    print("=== privacy_scan ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
