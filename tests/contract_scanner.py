#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一契约扫描器（M3）：形状白名单 + 绑定解析。

核心（根治方案 §3.4 / §4.6.5 / §4.7）：
  文档中每个**派生值出现**（形状白名单内的 count_unit / semver / explicit_key）都必须
  解析出一个**绑定 ID**（对照 `skill/contracts/registry.json` 的 bindings）。
    - 解析成功 ⇒ 由该绑定的 derive 从真实源现场重算，与文档声明比对；不等 ⇒ 红（漂移）。
    - 解析不出绑定 ⇒ 该命中归“未绑定”。

设计要点：
  - 形状集是**有限闭集**（registry.shape_whitelist.patterns）。
  - 扫描面 = 文档集（默认：SKILL.md + references/*.md + README.md）− 豁免集
    （history 类：CHANGELOG.md，及 registry.exempt_forms）。
  - 本模块只做**扫描与归类**，不改文档、不写被扫文件；可在离线副本上跑负例。
  - 生成器与判据独立性（§3.2）：判据侧一律从真实源现场重算，不读 build 期生成物。

命令行：
  python skill/tests/contract_scanner.py [--root ROOT] [--json] [--strict]
    默认：打印归类报告；未绑定命中数 > 0 时 **rc=1**（--strict 或不 --strict 均如此，
          因 §3.4 要求「未归类命中数＝0」才可升格；本实现对「明确可判的未绑定形状」
          直接判红，对属已知绑定来源但值漂移的给漂移红）。
"""
import argparse
import collections
import io
import json
import os
import re
import sys
import tokenize

# 默认扫描的文档集（相对 root）
DEFAULT_DOCS = ["SKILL.md", "README.md"]
DEFAULT_REF_GLOB = "references"

# 历史类 / 免扫描文档（按语义）
HISTORY_DOCS = {"CHANGELOG.md"}

def _p(root, *a):
    return os.path.join(root, *a)

def _load_registry(root):
    with io.open(_p(root, "skill/contracts/registry.json"), "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _read(root, rel):
    try:
        with io.open(_p(root, rel.replace("/", os.sep)), "r", encoding="utf-8", newline="") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

# -------- 形状白名单（从 registry 读取；关闭集）--------

def _shape_patterns(reg):
    sw = (reg.get("shape_whitelist") or {}).get("patterns") or []
    out = []
    for p in sw:
        sid = p.get("shape_id")
        rx = p.get("regex")
        if not sid or not rx:
            continue
        if sid in ("count_unit", "semver"):
            # registry 里用 PCRE 命名组 (?<name>...)；Python 需 (?P<name>...)
            pyrx = re.sub(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", rx)
            out.append((sid, re.compile(pyrx)))
        # explicit_key 是叙述型（非正则），按结构单独处理
    return out

# -------- 绑定解析（数据驱动，登记即契约）--------
# 形状白名单收敛（§3.4）：count_unit 只在**派生声明锚位**上命中——即「数字+数量单位」出现在
#   一个**已登记的派生声明句式**里（registry.shape_whitelist.count_anchors 的整行正则，含
#   一个捕获数字的命名组 `n`）。锚位命中把该计数绑到一个绑定 ID，由绑定现场重算并比对。
#   没有落在任何锚位的「N 个/条/项…」一律归 `prose`（正文语用 / 实测账本数字，**不是派生值
#   出现**），既不进 unbound、也不判红。
#   ⇒ 未归类命中数＝0（所有命中都被归入 bound_ok / drift / unbound / prose 之一）。
# 判红面（check_scan）＝claims 违规 + 锚位 unbound（锚到绑定却算不出）+ drift（锚位值 != 重算）
#                   + unclassified（加粗声明形状命中但既非锚位、也非已登记 claim —— 待登记即红）。

def _count_anchors(reg):
    """从 registry 读派生声明锚：[(compiled_regex_with_namedgroup_n, binding)]。

    regex 是整行正则，捕获组 `n` 为声明的数量值。
    """
    out = []
    for a in ((reg.get("shape_whitelist") or {}).get("count_anchors") or []):
        rx = a.get("regex")
        binding = a.get("binding")
        if not rx or not binding:
            continue
        pyrx = re.sub(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", rx)
        out.append((re.compile(pyrx), binding))
    return out

def _semver_version(reg):
    """semver 形状的受控值：registry 指定的版本绑定（默认 metadata.version）。"""
    return "metadata.version"

def _recompute(reg, root):
    """判据侧独立重算：binding_id -> 当前真实规模（int/str）或 None。"""
    out = {}
    try:
        md = json.load(io.open(_p(root, "skill/webbuilder-xwl-patch/metadata.json"), encoding="utf-8-sig"))
        out["metadata.references"] = len(md.get("references") or [])
        out["metadata.layers"] = len(md.get("layers") or {})
        out["metadata.update_history"] = len(md.get("update_history") or [])
        out["metadata.version"] = md.get("version")
    except Exception:
        pass
    try:
        bl = json.load(io.open(_p(root, "skill/tests/baseline.json"), encoding="utf-8-sig"))
        out["baseline.blocks"] = len(bl.get("blocks") or [])
        out["baseline.doc_guard_blocks"] = len(bl.get("doc_guard_blocks") or {})
    except Exception:
        pass
    try:
        g = json.load(io.open(_p(root, "skill/tests/task_acceptance_fixtures/golden.json"), encoding="utf-8-sig"))
        out["golden.expected_ids"] = len(g.get("expected_ids") or [])
    except Exception:
        pass
    try:
        tp = json.load(io.open(_p(root, "skill/webbuilder-xwl-patch/test-prompts.json"), encoding="utf-8-sig"))
        out["test_prompts"] = len(tp)
    except Exception:
        pass
    try:
        items = json.load(io.open(_p(root, "ledger/data/items.json"), encoding="utf-8-sig")).get("items") or []
        out["ledger.items"] = len(items)
    except Exception:
        pass
    cpd = _p(root, "ledger/data/checkpoints")
    if os.path.isdir(cpd):
        out["ledger.checkpoints"] = len([f for f in os.listdir(cpd) if f.endswith(".json")])
    icd = _p(root, "tools/testing/injection/injection-cases")
    if os.path.isdir(icd):
        out["injection.cases"] = len([f for f in os.listdir(icd) if f.endswith(".json")])
    try:
        xs = io.open(_p(root, "skill/webbuilder-xwl-patch/scripts/xwl.py"), encoding="utf-8-sig").read()
        out["subcommands"] = len(set(re.findall(r"add_parser\(\s*['\"]([A-Za-z0-9_\-]+)", xs)))
    except Exception:
        pass
    return out

def _doc_surface(root, reg):
    """返回 [(rel, text)] 扫描面：分发包文档集 − history − exempt。"""
    exempt = {e["path"] for e in (reg.get("exempt_forms", {}).get("items", []))}
    dist = _p(root, "skill", "webbuilder-xwl-patch")
    docs = []
    for nm in DEFAULT_DOCS:
        t = _read(root, "skill/webbuilder-xwl-patch/" + nm)
        if t is not None:
            docs.append((nm, t))
    refdir = os.path.join(dist, DEFAULT_REF_GLOB)
    if os.path.isdir(refdir):
        for f in sorted(os.listdir(refdir)):
            if f.endswith(".md"):
                rel = "references/" + f
                t = _read(root, "skill/webbuilder-xwl-patch/" + rel)
                if t is not None:
                    docs.append((rel, t))
    docs = [(rel, t) for rel, t in docs
            if rel not in HISTORY_DOCS and os.path.basename(rel) not in HISTORY_DOCS
            and ("skill/webbuilder-xwl-patch/" + rel) not in exempt]
    return docs

def _dist_path(root, rel):
    return _p(root, "skill", "webbuilder-xwl-patch", rel.replace("/", os.sep))

def _claim_recompute(root, reg):
    """判据侧独立重算：claim_bindings 的 fn -> 现算值（int）或 None。
    与生成器不同代码路径（此处直接按 marker 现场数文档，不读任何 build 生成物）。"""
    cb = (reg.get("derived_claims") or {}).get("claim_bindings") or {}
    out = {}
    for bid, spec in cb.items():
        args = spec.get("args") or {}
        doc = args.get("doc")
        marker = args.get("marker")
        try:
            if doc and marker is not None:
                txt = _read(root, "skill/webbuilder-xwl-patch/" + doc)
                if txt is None:
                    out[bid] = None
                    continue
                out[bid] = len(re.findall(marker, txt, re.M))
            elif spec.get("fn") == "derive.test_prompts_count":
                tp = json.load(io.open(_dist_path(root, "test-prompts.json"), encoding="utf-8-sig"))
                out[bid] = len(tp)
            else:
                out[bid] = None
        except Exception:
            out[bid] = None
    return out

def check_claims(root, reg):
    """登记式派生声明校验：对 registry.derived_claims.claims 逐条判「声明值==重算值」。
    返回 violations 列表；空=绿。声明值解析不到或与重算不等 => 红。"""
    claims = (reg.get("derived_claims") or {}).get("claims") or []
    rec = _claim_recompute(root, reg)
    v = []
    for c in claims:
        doc = c.get("doc"); rx = c.get("regex"); bid = c.get("binding"); label = c.get("label", c.get("id"))
        txt = _read(root, "skill/webbuilder-xwl-patch/" + doc)
        if txt is None:
            continue  # 文档不存在则本声明不适用（README 常缺声明，是惰性，不判红）
        try:
            pyrx = re.sub(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", rx)
            hits = re.findall(pyrx, txt, re.M)
        except re.error as e:
            v.append("claim %s 正则非法: %s" % (c.get("id"), e))
            continue
        rv = rec.get(bid)
        for h in hits:
            claimed = int(h) if not isinstance(h, tuple) else int(h[0])
            if rv is None:
                v.append("claim %s 无法重算 binding=%s（%s）" % (c.get("id"), bid, label))
            elif claimed != rv:
                v.append("自称数字不符 %s：文档写 %d，重算 %d" % (label, claimed, rv))
    return v

# 声明形状（用于「待登记」识别）：加粗 `**N 单位**` **紧跟**一个 claim 关键词
#   （如 `**30 项**清单`、`**25 条**高频问题`）。紧跟＝bold 串后 3 字内含关键词。
#   measured-data 家族文档是**实测账本**（数字的权威在 ledger，不是契约派生）⇒ 整体豁免本启发式。
_DECL_SHAPE = re.compile(r"\*\*(\d+)\s*(条|项|个|把|处)\*\*(.{0,3})")
_CLAIM_KEYWORDS = ("清单", "高频问题", "子命令", "守卫", "规则", "条目", "样例", "示例", "模板")
_SEMVER = re.compile(r"\d+\.\d+\.\d+")

def _is_measured_doc(rel):
    """measured-data 家族文档＝实测账本，其数字权威在 ledger，非契约派生面。"""
    return "measured-data" in rel

def _version_anchors(reg):
    """从 registry 读版本声明锚：[(compiled_regex_with_group_n, binding)]（同 count_anchors 形态）。"""
    out = []
    for a in ((reg.get("shape_whitelist") or {}).get("version_anchors") or []):
        rx = a.get("regex"); binding = a.get("binding")
        if not rx or not binding:
            continue
        pyrx = re.sub(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", rx)
        out.append((re.compile(pyrx), binding))
    return out

def scan(root, reg):
    """扫描并逐条归类每个命中。返回 structure: {
         'recompute', 'hits', 'unbound', 'drift', 'prose', 'unclassified', 'bound_ok'
       }
    status ∈ bound_ok / drift / unbound / prose / unclassified。
    """
    anchors = _count_anchors(reg)
    v_anchors = _version_anchors(reg)
    rec = _recompute(reg, root)
    ver = rec.get(_semver_version(reg))
    hits = []
    claim_anchored_positions = set()
    for c in ((reg.get("derived_claims") or {}).get("claims") or []):
        doc = c.get("doc")
        txt = _read(root, "skill/webbuilder-xwl-patch/" + doc) if doc else None
        if txt is None:
            continue
        try:
            pyrx = re.sub(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", c.get("regex"))
            for ln, line in enumerate(txt.splitlines(), 1):
                if re.search(pyrx, line):
                    claim_anchored_positions.add((doc, ln))
        except re.error:
            pass
    for rel, text in _doc_surface(root, reg):
        measured = _is_measured_doc(rel)
        for ln, line in enumerate(text.splitlines(), 1):
            # ① 锚位声明：整行正则（含命名组 n）命中 → 绑定比对
            anchor_spans = []   # 已由锚位消费的数字起点，避免重复计入 census
            for rx, binding in anchors:
                for am in rx.finditer(line):
                    try:
                        n = int(am.group("n"))
                    except (IndexError, TypeError):
                        continue
                    anchor_spans.append((am.start("n"), am.end("n")))
                    rv = rec.get(binding)
                    if not isinstance(rv, int):
                        status = "unbound"      # 锚到绑定却算不出 → 红
                    elif rv == n:
                        status = "bound_ok"
                    else:
                        status = "drift"
                    hits.append({"doc": rel, "line": ln, "shape": "count_unit",
                                 "text": am.group(0), "count": n, "unit": "?",
                                 "binding": binding, "recomputed": rv,
                                 "status": status})
            # ② 全量普查：其余「N 单位」逐条归类（锚位已消费的除外）
            for m in re.finditer(r"(\d+)\s*(条|项|个|把|处)", line):
                n = int(m.group(1)); unit = m.group(2)
                if any(s <= m.start(1) < e for s, e in anchor_spans):
                    continue    # 已被锚位计入
                is_decl = False
                if not measured:
                    dm = _DECL_SHAPE.search(line)
                    # 加粗声明形状且 bold 串后紧跟 claim 关键词 ⇒ 声明形
                    is_decl = dm is not None and any(kw in dm.group(3) for kw in _CLAIM_KEYWORDS)
                if (rel, ln) in claim_anchored_positions:
                    status = "bound_ok"   # 已被登记的 claim 覆盖并复核（check_claims）
                elif is_decl:
                    status = "unclassified"
                else:
                    status = "prose"
                hits.append({"doc": rel, "line": ln, "shape": "count_unit",
                             "text": m.group(0), "count": n, "unit": unit,
                             "binding": None, "recomputed": None,
                             "status": status})
            # ③ 版本声明锚：仅在版本声明句式里比对（散文里的示例版本号不计）
            for rx, binding in v_anchors:
                for vm in rx.finditer(line):
                    got = vm.group("n") if "n" in rx.groupindex else vm.group(1)
                    rv = rec.get(binding)
                    if rv is None:
                        status = "unbound"
                    elif str(got) == str(rv):
                        status = "bound_ok"
                    else:
                        status = "drift"
                    hits.append({"doc": rel, "line": ln, "shape": "semver",
                                 "text": vm.group(0), "binding": binding,
                                 "recomputed": rv, "status": status})
    def _sel(st):
        return [h for h in hits if h["status"] == st]
    return {"recompute": rec, "hits": hits,
            "unbound": _sel("unbound"), "drift": _sel("drift"),
            "prose": _sel("prose"), "unclassified": _sel("unclassified"),
            "bound_ok": _sel("bound_ok")}

def check_scan(root, reg):
    """统一判定（判红面）：把「未绑定 / 漂移 / 待登记 + claims 违规」并入判定结果。

    返回 violations 列表；空=绿。判据 ID 前缀 `scan.`：
      - scan.claim_*：登记声明的自称数字与现场重算不符（见 check_claims）
      - scan.drift：锚位派生计数 != 现场重算
      - scan.unbound：锚到绑定却算不出（绑定不可重算）
      - scan.unclassified：加粗声明形状命中，却既不在锚位、也不被已登记 claim 覆盖（待登记）
    prose（正文语用计数）不计入判定，属已归类合法面。
    """
    v = []
    s = scan(root, reg)
    for x in check_claims(root, reg):
        v.append("scan.claim: " + x)
    for h in s["drift"]:
        v.append("scan.drift: %s:%d 「%s」绑定=%s 重算=%r"
                 % (h["doc"], h["line"], h["text"], h["binding"], h["recomputed"]))
    for h in s["unbound"]:
        v.append("scan.unbound: %s:%d 「%s」绑定=%s 无法重算"
                 % (h["doc"], h["line"], h["text"], h["binding"]))
    for h in s["unclassified"]:
        v.append("scan.unclassified: %s:%d 「%s」声明形状无登记（待登记）"
                 % (h["doc"], h["line"], h["text"]))
    return v

# ======================================================================================
# B1 迁入：文档守卫 17b / 17l / 17r / 17j-4 的判定逻辑（自 selftest.py 物理迁入）
# ======================================================================================
# 背景：同类判定的实现散落在 selftest.py 各段函数体里，本身不规范。此处统一承接，**语义逐条
#   等价**（旧负例仍红、新写法仍红）。四个调用点由 selftest 的本段函数（`_docs_xfile_consistency`
#   / `_docs_layers_and_distribution` / `_docs_tail_scaffold`）调用，并保留各自 `# 17x` 块头注释。
#   ⚠️ 这些判定原依赖 selftest 的若干模块级常量/助手（`_trows` / `_chron` / `_date_verb` /
#     `_date_re` / `_ver_re` / `_chron_exempt` / `_git_scan_scope` / `_docs_git_arm` / `_b17r_*` /
#     `_mark_sub`）。为保持**单一真源、结果等价**，这里以 **default=None 注入**承接这些依赖：
#     selftest 调用时显式传入其模块级同名对象，迁入代码在传入对象上与旧逻辑逐字一致；缺省时才
#     退到本模块的**独立本地副本**（供独立运行/负例自证）。

# ---- 17b：任意两份文档之间不得有逐字重复的表格行 ----

def _local_trows(ls):
    """`_trows` 的本地副本（仅在被 scan 独立调用、未注入 selftest `_trows` 时用；逐字等价）。"""
    return {l.strip() for l in ls
            if l.strip().startswith("|") and l.strip().endswith("|")
            and not set(l.strip()) <= set("|-: ")}


def guard_dup_table_rows(docs, trows=None):
    """17b：`docs`（{文档名: 行列表}）里**任意两份**之间逐字重复的表格行 ⇒ 违规列表。

    等价于旧 `_docs_xfile_consistency` 的 17b 块：排除 `CHANGELOG.md`，对名称对两两取表格行
    交集，非空即报（文案逐字保留）。`trows` = selftest 的模块级 `_trows`（注入以保单一真源）。
    """
    _tr = trows or _local_trows
    out = []
    _names = [k for k in docs if k != "CHANGELOG.md"]
    for _i in range(len(_names)):
        for _j in range(_i + 1, len(_names)):
            _dup = _tr(docs[_names[_i]]) & _tr(docs[_names[_j]])
            if _dup:
                out.append("%s 与 %s 有 %d 行表格逐字重复（同一张表别写两处）：%s"
                           % (_names[_i], _names[_j], len(_dup), sorted(_dup)[0][:60]))
    return out


# ---- 17l：编年纪律（三条臂）----

# 本地默认副本（仅在被独立调用、未注入 selftest 同名对象时用）。`_chron` 仍按**相邻字面量拼接**，
#   与 selftest 模块级常量保持同一形态（整词直写会让本文件被这三条臂判红）。
_LOCAL_CHRON = ["曾" "经", "原" "先", "早" "先", "此" "前", "一" "度", "当" "年", "旧" "版",
                "旧" "实现", "旧" "判据", "原" "判据", "上" "一轮", "上" "一版", "当" "时", "历史" "上",
                "以" "前"]
_LOCAL_DATE_VERB = ("实测", "真机", "复现", "审查", "修正", "发布", "事故")
_LOCAL_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LOCAL_VER_RE = re.compile(r"\d+\.\d+\.\d+")


def guard_chronology(root, doc_fail, nogit_arms, checks, arm, chron=None,
                     date_verb=None, date_re=None, ver_re=None,
                     chron_exempt=None, git_scan_scope=None, docs_git_arm=None):
    """17l：编年纪律三条臂（事件词 / 施工日期 / 发版号）。

    等价于旧 `_docs_layers_and_distribution` 的 17l 块：
      - 扫描面 = `_git_scan_scope(root)`（`git ls-files ∪ 磁盘新增`；取不到 git 走 `_docs_git_arm`
        判红或降级，两条分支语义不变）；
      - 豁免面 = `_chron_exempt(root)`（结构判据：CHANGELOG/archive/metadata ∪ 依据层文件）；
      - 臂①事件词、臂②施工日期（±25 字内有施工动词）、臂③发版号；`SKILL.md` 的 `version:` 行跳过。
    依赖以注入承接：`chron` / `date_verb` / `date_re` / `ver_re` / `chron_exempt` / `git_scan_scope`
    / `docs_git_arm` = selftest 模块级同名对象；缺省退到本模块本地副本。违规 append 进 `doc_fail`。
    """
    _chron = chron if chron is not None else _LOCAL_CHRON
    _date_verb = date_verb if date_verb is not None else _LOCAL_DATE_VERB
    _date_re = date_re if date_re is not None else _LOCAL_DATE_RE
    _ver_re = ver_re if ver_re is not None else _LOCAL_VER_RE
    _chron_exempt = chron_exempt or _local_chron_exempt
    _git_scan_scope = git_scan_scope or _local_git_scan_scope
    _docs_git_arm = docs_git_arm or _local_docs_git_arm
    _chron_ex = _chron_exempt(root)
    _shipped, _ = _git_scan_scope(root)
    if not _docs_git_arm(arm, _shipped, doc_fail, nogit_arms, checks, "git.chron"):
        return
    for _rel in _shipped:
        if _rel in _chron_ex:
            continue
        try:
            _bl = io.open(_p(root, _rel.replace("/", os.sep)),
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


# ---- 17j-4：篇幅上限（SKILL.md 字符数硬/软、README.md 行数、CHANGELOG 文首行数）----

def guard_length_caps(root, docs, sk_hard=32000, sk_soft=28000, sk_goal=12000,
                      read_chars=None, gate_note=None):
    """17j-4：篇幅上限族。返回 `(violations, notes)` —— `violations` 进 doc_fail（判红），
    `notes` 由调用方走 `_gate_note`（不进 rc）。

    等价于旧 `_docs_layers_and_distribution` 的 17j-4 块：
      - `SKILL.md` 字符数：> 硬上限 ⇒ 一条红；软上限…硬上限之间 ⇒ 一条红；正常 ⇒ 一条 note。
      - `README.md` 行数 > 150 ⇒ 一条红。
      - `CHANGELOG.md` 文首区（首个 `## [` 之前）非空行 > 14 ⇒ 一条红。
    `read_chars` / `gate_note` 用 selftest 的注入对象；缺省退到本地等价实现。
    """
    _read_chars = read_chars or _local_read_chars
    v = []
    notes = []
    _sk_chars, _sk_err = _read_chars(root, "SKILL.md")
    if _sk_chars is None:
        v.append("篇幅上限：读不出 SKILL.md（%s）—— 报错，不算通过" % _sk_err)
    if _sk_chars is not None:
        if _sk_chars > sk_hard:
            v.append("SKILL.md 已 %d 字符，超过硬上限 %d 字符"
                     "（新增内容请考虑下沉到 references/）" % (_sk_chars, sk_hard))
        elif _sk_chars > sk_soft:
            try:
                _rf = sorted(f for f in os.listdir(os.path.join(root, "references")) if f.endswith(".md"))
                _rl = sum(len(io.open(os.path.join(root, "references", f), encoding="utf-8").read().splitlines())
                          for f in _rf)
                _stat = ("`references/` 现有 %d 份、合计 %d 行；`SKILL.md` 里已有 %d 处指针可挂"
                         % (len(_rf), _rl, sum("references/" in _l for _l in docs.get("SKILL.md", []))))
            except (OSError, UnicodeDecodeError):   # UnicodeDecodeError 是 ValueError 子类、非 OSError ⇒ 必须并列
                _stat = "统计不出（references/ 不可读）"
            v.append("SKILL.md %d 字符已超软上限 %d（硬上限 %d）⇒ **新增内容默认走 "
                     "`references/`**（%s）。" % (_sk_chars, sk_soft, sk_hard, _stat))
        notes.append("SKILL.md %d 字符（硬上限 %d／软上限 %d；远期目标 %d，尚差 %d）"
                     % (_sk_chars, sk_hard, sk_soft, sk_goal, max(0, _sk_chars - sk_goal)))
    # `README.md` 按行数
    _rd_n = len(docs.get("README.md", []))
    if _rd_n > 150:
        v.append("README.md 已 %d 行，超过 150 行上限（新增内容请考虑下沉到 references/）"
                 % _rd_n)
    # CHANGELOG.md 文首区（首个 `## [` 之前）非空行 ≤ 14
    _cl_head_lines = docs.get("CHANGELOG.md", [])
    _cl_ne = 0
    for _cl_l in _cl_head_lines:
        if _cl_l.startswith("## ["):
            break
        if _cl_l.strip() != "":
            _cl_ne += 1
    if _cl_ne > 14:
        v.append("CHANGELOG.md 文首区（首个 `## [` 之前）非空行 %d 行 > 上限 14 —— "
                 "发版判据应落在依据层／记忆，文首只留使用者向内容（哪一版改了什么、升了要注意什么）"
                 % _cl_ne)
    return v, notes


# ---- 17r：分发面自包含（扫描面里不得出现指向 skill 包外的引用）----

# 本地默认副本（仅在被独立调用、未注入 selftest 同名对象时用；逐字等价）。
_LOCAL_B17R_DOCS = ("《验收基线》", "《落地清单》", "施工索引", "施工单")
_LOCAL_B17R_CODE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-L]\d{1,2}|[A-Z]{1,3}-\d{1,2}|[A-L]-[a-z])(?![A-Za-z0-9_]|\.\w)"
    r"|(?<![A-Za-z0-9_])SITE\d(?![A-Za-z0-9_])")
_LOCAL_B17R_CODE_OK = re.compile(
    r"^(?:UTF-?8|UTF-?16|UTF-?32|UTF8|UTF16|UTF32|UCS-?[24]|ISO-8859-\d{1,2}"
    r"|GB\d{4}|GBK|GB18030|CP\d{3,5}|KOI8-[RU]|SHIFT_JIS|EUC-[A-Z]{2})$", re.I)
_LOCAL_B17R_SEC = re.compile(r"§\d{1,3}-\d{1,2}")
_LOCAL_B17R_PROC = re.compile(r"\bPRE\d+\b|\b(?:eng|qa|pm|arch|reg|tl)-\d{1,3}\b")


def _local_b17r_mask_strings(_text):
    """`_b17r_mask_strings` 的本地副本（未注入时用；逐字等价）。"""
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


def _local_b17r_history_skip(_rel, _text):
    """`_b17r_history_skip` 的本地副本（未注入时用；逐字等价）。"""
    if not _rel.endswith(".json"):
        return set()
    _k = _text.find('"update_history"')
    if _k < 0:
        return set()
    _j = _text.find("[", _k + len('"update_history"'))
    if _j < 0:
        return set()
    _depth = 0
    _in = False
    _esc = False
    _p = _j
    while _p < len(_text):
        _c = _text[_p]
        if _in:
            if _esc:
                _esc = False
            elif _c == "\\":
                _esc = True
            elif _c == '"':
                _in = False
        else:
            if _c == '"':
                _in = True
            elif _c == "[":
                _depth += 1
            elif _c == "]":
                _depth -= 1
                if _depth == 0:
                    break
        _p += 1
    else:
        return set()
    _start_ln = _text.count("\n", 0, _j) + 1
    _end_ln = _text.count("\n", 0, _p) + 1
    return set(range(_start_ln, _end_ln + 1))


def guard_dist_selfcontained(root, doc_fail, nogit_arms, checks, arm,
                             b17r_docs=None, b17r_code=None, b17r_code_ok=None,
                             b17r_sec=None, b17r_proc=None, mask_strings=None,
                             history_skip=None, git_scan_scope=None, docs_git_arm=None,
                             ok_print=None):
    """17r：分发面自包含。扫描面（`git ls-files ∪ 磁盘新增`）里不得出现指向 skill 包外的引用。

    等价于旧 `_docs_tail_scaffold` 的 17r 块：四类判据（包外文档名 / 施工单条目代号 / §N-M 节号 /
    前置批次号与过程角色编号）；`.py` 只在字符串字面量之外判；`CHANGELOG*.md` 整体与 metadata 的
    `update_history` 段按语义跳过。`doc_fail` 追加违规（截前 12 条）；全绿时调 `ok_print` 打印
    `[ok]`（文案逐字保留）。依赖以注入承接 selftest 模块级同名对象；缺省退到本地副本。
    """
    _docs_w = b17r_docs if b17r_docs is not None else _LOCAL_B17R_DOCS
    _code = b17r_code or _LOCAL_B17R_CODE
    _code_ok = b17r_code_ok or _LOCAL_B17R_CODE_OK
    _sec = b17r_sec or _LOCAL_B17R_SEC
    _proc = b17r_proc or _LOCAL_B17R_PROC
    _mask = mask_strings or _local_b17r_mask_strings
    _hskip = history_skip or _local_b17r_history_skip
    _git_scan_scope = git_scan_scope or _local_git_scan_scope
    _docs_git_arm = docs_git_arm or _local_docs_git_arm
    _files, _ = _git_scan_scope(root)
    if not _docs_git_arm(arm, _files, doc_fail, nogit_arms, checks, "git.dist"):
        return
    _b17r_fail = []
    for _rel17 in _files:
        if not _rel17 or _rel17 in ("CHANGELOG.md", "CHANGELOG-archive.md"):
            continue
        _fp17 = os.path.join(root, _rel17.replace("/", os.sep))
        if not os.path.exists(_fp17):
            continue
        try:
            with io.open(_fp17, "r", encoding="utf-8", newline="") as _fh17:
                _raw17 = _fh17.read()
        except Exception as _exc17:  # noqa: BLE001
            _b17r_fail.append("17r 分发面自包含：读不出 %s（%s）—— 报错，不算「没命中」" % (_rel17, _exc17))
            continue
        if _rel17.endswith(".py"):
            _judge17 = _mask(_raw17)
            if _judge17 is None:
                _b17r_fail.append("17r 分发面自包含：%s 词法解析失败 ⇒ 不敢判（保守报错）" % _rel17)
                continue
        else:
            _judge17 = _raw17
        _skip17 = _hskip(_rel17, _judge17)
        for _i17, _l17 in enumerate(_judge17.split("\n"), 1):
            if _i17 in _skip17:
                continue
            _hit17 = ([_m.group(0) for _m in _code.finditer(_l17)
                       if not _code_ok.match(_m.group(0))]
                      + [_m.group(0) for _m in _sec.finditer(_l17)]
                      + [_m.group(0) for _m in _proc.finditer(_l17)]
                      + [_w for _w in _docs_w if _w in _l17])
            if _hit17:
                _b17r_fail.append("17r 分发面自包含：%s:%d 出现包外引用 %s —— 原文：%s"
                                  % (_rel17, _i17, "/".join(sorted(set(_hit17))), _l17.strip()[:80]))
    if _b17r_fail:
        doc_fail.extend(_b17r_fail[:12])
    else:
        if ok_print is not None:
            ok_print(_files)
        else:
            print("[ok]  17r 分发面自包含：%d 个分发文件里无包外引用"
                  "（无《验收基线》/《落地清单》/施工索引/施工单、无施工单条目代号（**A–L 单字母**-数字 ／ 字母-短横-数字〔任意 1–3 个字母〕／ **A–L 单字母**-短横-小写字母 形态）、"
                  "无 §N-M 形式的节号指针、无前置批次号/过程角色编号；"
                  "`.py` 只判字符串字面量之外；CHANGELOG 整文件 ＋ 历史记录段 ＋ 编码名词形豁免）"
                  % len(_files))


# ---- 缺省兜底：本地等价实现（仅在被独立调用、selftest 未注入时用）----

def _local_read_chars(root, rel):
    """返回 `(chars, None)`；读不出返回 `(None, err_str)`（`err_str` 用于等价旧报错文案）。"""
    try:
        return len(io.open(_p(root, rel.replace("/", os.sep)), encoding="utf-8", newline="").read()), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, exc


def _local_chron_exempt(root):
    """本地等价：{CHANGELOG.md, CHANGELOG-archive.md, metadata.json} ∪ 依据层文件。

    依据层 = `metadata.json` 的 `layers` 里值为 `evidence`、且 stem 落在依据层家族前缀内的 `references/*.md`。
    """
    _ex = {"CHANGELOG.md", "CHANGELOG-archive.md", "metadata.json"}
    try:
        with io.open(_p(root, "metadata.json"), "r", encoding="utf-8") as _f:
            _md = json.load(_f)
        _lay = _md.get("layers") if isinstance(_md, dict) else None
    except (OSError, ValueError):
        _lay = None
    if isinstance(_lay, dict):
        _refdir = os.path.join(root, "references")
        try:
            _nms = sorted(os.listdir(_refdir))
        except OSError:
            _nms = []
        for _n in _nms:
            if not _n.endswith(".md"):
                continue
            _rel = "references/" + _n
            _stem = _n[:-3]
            if _lay.get(_rel) == "evidence" and any(
                    _stem == _s or _stem.startswith(_s + "-")
                    for _s in ("measured-data", "workflow-notes")):
                _ex.add(_rel)
    return _ex


def _local_git_scan_scope(root):
    """本地副本：子进程 `git ls-files ∪ --others --exclude-standard`；取不到 ⇒ `(None, why)`。"""
    import subprocess
    scope, seen = [], set()
    for c in (["ls-files"], ["ls-files", "--others", "--exclude-standard"]):
        try:
            pr = subprocess.run(["git", "-C", root] + c, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120)
        except (OSError, ValueError) as exc:
            return None, "%s: %s" % (type(exc).__name__, exc)
        if pr.returncode != 0:
            return None, "`git %s` 返回 %s" % (" ".join(c), pr.returncode)
        for x in pr.stdout.splitlines():
            x = x.strip()
            if x and x not in seen:
                seen.add(x)
                scope.append(x)
    return scope, None


def _local_docs_git_arm(arm, shipped, doc_fail, nogit_arms, checks, sid):
    """本地兜底：取到清单即 True；取不到则把该臂记入 nogit_arms 并返回 False（不再扫）。

    仅在被独立调用、未注入 selftest `_docs_git_arm` 时用 —— selftest 调用时一律注入其真实现
    （含 `--require-all` / `--allow-nogit` 的完整降级语义）。
    """
    if shipped is not None:
        return True
    doc_fail.append("%s：取不到 `git ls-files` 清单 ⇒ 未扫（独立运行兜底）" % arm)
    nogit_arms.append(arm)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args(argv)
    root = a.root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.abspath(root)
    reg = _load_registry(root)
    s = scan(root, reg)
    v = check_scan(root, reg)
    if a.json:
        print(json.dumps({"violations": v,
                          "census": {"recompute": s["recompute"],
                                     "hits": len(s["hits"]),
                                     "bound_ok": len(s["bound_ok"]),
                                     "unbound": len(s["unbound"]),
                                     "drift": len(s["drift"]),
                                     "prose": len(s["prose"]),
                                     "unclassified": len(s["unclassified"])}},
                         ensure_ascii=False, indent=1))
        return 0 if not v else 1
    print("== 统一契约扫描器（形状白名单 + 绑定解析）==")
    print("重算规模：", json.dumps({k: val for k, val in s["recompute"].items()}, ensure_ascii=False))
    print("形状普查：命中 %d（bound_ok=%d, drift=%d, unbound=%d, prose=%d, unclassified=%d）" % (
        len(s["hits"]), len(s["bound_ok"]), len(s["drift"]), len(s["unbound"]),
        len(s["prose"]), len(s["unclassified"])))
    print("判定（判红面：claim + drift + unbound + unclassified）：违规 %d" % len(v))
    for x in v[:20]:
        print("  [FAIL] " + x)
    if a.report_only:
        return 0
    return 0 if not v else 1


if __name__ == "__main__":
    raise SystemExit(main())
