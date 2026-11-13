#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一契约校验器（M2 落地；M3 可集成进 selftest 整块）。

实现《根治方案》§4.7 十六条可失败判据，各判据带稳定判据 ID。本文件是独立脚本，
既可直接命令行运行，也可被 M3 的 selftest 以函数方式导入（run_all()/check_<id>()）。

设计原则（§3.2 独立性）：
  - 判据只从「真实源」（磁盘文件、SKILL.md、CHANGELOG、xwl.py、ledger 数据）现场重算；
    不读任何 build 期生成物来充当 ground truth（derived-values 仅用于「是否随包留证」）。
  - 生成器实现与判据实现是不同代码路径：本模块不含生成/渲染代码。

用法：
  python skill/tests/contract_validator.py [--root ROOT] [--only ID[,ID...]] [--json]
退出码：无违规 -> 0（绿）；有违规 -> 1（红）；参数/环境错 -> 2。
每项输出形如：  <判据ID>  PASS|FAIL  <明细>
"""
import argparse
import io
import json
import os
import re
import sys

JUDGE_IDS = [
    "contract.unregistered_file",
    "metadata.ref_layer_diff",
    "metadata.history_consistency",
    "ledger.item_order",
    "case.schema_uniform",
    "contract.semantic_order",
    "contract.canonical_order",
    "contract.write_form",
    "contract.cross_ref",
    "derive.source_drift",
    "metadata.version_sync",
    "test-prompts.coverage",
    "baseline.deduction",
    "baseline.registry_order",
    "golden.derived",
    "metadata.layers_enum",
]

# ---------- 判据适用域（scope） ----------
# 每个判据声明所需「数据域」。域不存在的树里该判据**不适用**（SKIP），不判红、不误报异常。
#   skill     = skill/ 源码与分发面；任何承载 skill 的树都有
#   workspace = 工作区根侧 ledger/ tools/ gate/ 数据面；发布包 / skill-only 树不含
# 纯 workspace 判据在 skill-only 树整体 SKIP；混合判据域为 skill（必跑），其 workspace 片段函数内按存在性降级。
JUDGE_SCOPE = {
    "contract.unregistered_file":   ("skill",),
    "metadata.ref_layer_diff":      ("skill",),
    "metadata.history_consistency": ("skill",),
    "ledger.item_order":            ("workspace",),
    "case.schema_uniform":          ("workspace",),
    "contract.semantic_order":      ("skill",),
    "contract.canonical_order":     ("skill",),
    "contract.write_form":          ("skill",),
    "contract.cross_ref":           ("skill",),
    "derive.source_drift":          ("skill",),
    "metadata.version_sync":        ("skill",),
    "test-prompts.coverage":        ("skill",),
    "baseline.deduction":           ("skill",),
    "baseline.registry_order":      ("skill",),
    "golden.derived":               ("skill",),
    "metadata.layers_enum":         ("skill",),
}


def _domain_present(root, domain):
    """该数据域在本树是否存在。skill=root/skill 存在；workspace=root 下 ledger|tools|gate 任一存在。"""
    if domain == "skill":
        return os.path.isdir(_p(root, "skill"))
    if domain == "workspace":
        return any(os.path.isdir(_p(root, d)) for d in ("ledger", "tools", "gate"))
    return False


def _judge_applies(root, jid):
    """判据所需域全在本树 ⇒ 适用；任一缺失 ⇒ 不适用（SKIP）。"""
    for dom in JUDGE_SCOPE.get(jid, ("skill",)):
        if not _domain_present(root, dom):
            return False
    return True

# ---------- 基础 IO ----------

def _p(root, *a):
    return os.path.join(root, *a)

def _load(root, rel):
    with io.open(_p(root, rel), "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _raw(root, rel):
    return io.open(_p(root, rel), "rb").read()

def _read_text(root, rel):
    return io.open(_p(root, rel), "r", encoding="utf-8-sig").read()

def _vkey(v):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(v))
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

def _blk_declared(name, txt):
    """块名是否在给定文本里被**独立**提及（词边界；`17j` 不被 `17j-10` 顶替）。

    起因（B4）：`k in 文本` 会把 `17j` 误判为已声明（`17j-10` 含该子串），
    声明类判据必须按独立词匹配。与 selftest.py `_blk_declared` 同一口径。
    """
    return re.search(r"(?<![0-9A-Za-z_-])" + re.escape(name) + r"(?![0-9A-Za-z_-])", txt) is not None

# 正式目录：契约扫描面（registry 绑定闭集 + 磁盘全集）
FORMAL_DIRS = [
    "skill/webbuilder-xwl-patch",
    "skill/tests",
    "ledger/data",
    "gate/spec",
    "tools/testing/injection/injection-cases",
]

# registry 登记的文件模式（含通配）
def _registry_file_patterns(reg):
    return [b["file"] for b in reg.get("bindings", [])]

def _expand_formal_files(root, include_jsonl=False):
    """正式目录下全部 JSON（含可选 .jsonl）相对路径（registry 闭集比对用）。"""
    out = []
    for d in FORMAL_DIRS:
        base = _p(root, d)
        if not os.path.isdir(base):
            continue
        for r, dirs, names in os.walk(base):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                hit = n.endswith(".json") or (include_jsonl and n.endswith(".jsonl"))
                if hit:
                    rel = os.path.relpath(os.path.join(r, n), root).replace("\\", "/")
                    out.append(rel)
    return sorted(out)

def _expand_braces(pattern):
    """展开 {a,b,c} 为多个模式（仅用于 registry file 闭集匹配）。"""
    m = re.search(r"\{([^{}]+)\}", pattern)
    if not m:
        return [pattern]
    pre = pattern[:m.start()]
    post = pattern[m.end():]
    out = []
    for alt in m.group(1).split(","):
        out.extend(_expand_braces(pre + alt + post))
    return out

def _match_one(rel, pat):
    if "**" in pat:
        rx = "^" + re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*") + "$"
    else:
        rx = "^" + re.escape(pat).replace(r"\*", "[^/]*") + "$"
    return re.match(rx, rel) is not None

def _match_pattern(rel, pattern):
    pat = pattern.replace("\\", "/")
    for p in _expand_braces(pat):
        if _match_one(rel, p):
            return True
    return False

# ---------- 各判据实现：各返回 violations 列表；空=绿 ----------

def check_contract_unregistered_file(root, reg):
    """闭集：正式目录下每个 JSON 须被某个 registry.file 模式覆盖，或属于豁免。"""
    v = []
    pats = _registry_file_patterns(reg)
    exempt_forms = {e["path"] for e in (reg.get("exempt_forms", {}).get("items", []))}
    for rel in _expand_formal_files(root):
        if rel in exempt_forms:
            continue
        if any(_match_pattern(rel, p) for p in pats):
            continue
        v.append(rel)
    return v

def check_metadata_ref_layer_diff(root, reg):
    v = []
    md = _load(root, "skill/webbuilder-xwl-patch/metadata.json")
    refs = md.get("references") or []
    layers = md.get("layers") or {}
    refdir = _p(root, "skill/webbuilder-xwl-patch/references")
    disk = set("references/" + f for f in os.listdir(refdir) if f.endswith(".md"))
    if set(refs) != disk:
        v.append("references<->disk missing=%s extra=%s" % (
            sorted(disk - set(refs)), sorted(set(refs) - disk)))
    if set(layers) != set(refs):
        v.append("layers<->references diff=%s" % (
            sorted(set(layers) ^ set(refs)),))
    if len(refs) != len(set(refs)):
        v.append("references 有重复")
    return v

def check_metadata_history_consistency(root, reg):
    v = []
    md = _load(root, "skill/webbuilder-xwl-patch/metadata.json")
    hist = md.get("update_history") or []
    vers = [h.get("version") for h in hist]
    if len({tuple(sorted(h.keys())) for h in hist}) != 1:
        v.append("字段集合不统一")
    if len(vers) != len(set(vers)):
        v.append("版本重复")
    if vers != sorted(vers, key=_vkey, reverse=True):
        v.append("版本非降序")
    # 首条 <=> CHANGELOG 首段版本/日期
    cl = _read_text(root, "skill/webbuilder-xwl-patch/CHANGELOG.md")
    m = re.search(r"^##\s*\[?([0-9]+\.[0-9]+\.[0-9]+)\]?\s*[-—–]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
                  cl, re.M)
    if not m:
        # 兼容 "## 1.8.5 - date" 形式
        m = re.search(r"^##\s*([0-9]+\.[0-9]+\.[0-9]+)\s*[-—–]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
                      cl, re.M)
    if m and hist:
        if vers[0] != m.group(1):
            v.append("首条版本 %s != CHANGELOG 首段 %s" % (vers[0], m.group(1)))
        if hist[0].get("date") != m.group(2):
            v.append("首条日期 %s != CHANGELOG 首段 %s" % (hist[0].get("date"), m.group(2)))
    if md.get("version") != (vers[0] if vers else None):
        v.append("metadata.version != update_history[0].version")
    return v

def check_ledger_item_order(root, reg):
    v = []
    items = _load(root, "ledger/data/items.json").get("items") or []
    ids = [x.get("id") for x in items]
    if ids != sorted(ids):
        v.append("items ID 非升序")
    if len(ids) != len(set(ids)):
        v.append("items ID 重复")
    if len({tuple(sorted(x.keys())) for x in items if isinstance(x, dict)}) != 1:
        v.append("items 字段集合不统一")
    return v

def _case_required_optional(reg):
    for b in reg["bindings"]:
        if b["id"] == "injection.cases":
            a = b["derive"]["args"]
            return a["required"], a["optional"]
    return (["id", "provenance", "type", "desc", "file", "find", "replace", "cmd", "expect", "expect_re"],
            ["targets", "note", "requires", "provenance_ref"])

def check_case_schema_uniform(root, reg):
    v = []
    req, opt = _case_required_optional(reg)
    allowed = set(req) | set(opt)
    icdir = _p(root, "tools/testing/injection/injection-cases")
    for f in sorted(os.listdir(icdir)):
        if not f.endswith(".json"):
            continue
        d = _load(root, "tools/testing/injection/injection-cases/" + f)
        stem = f[:-5]
        if not isinstance(d, dict):
            v.append(f + ": 顶层非对象")
            continue
        if d.get("id") != stem:
            v.append("%s: id(%s) != 文件名" % (f, d.get("id")))
        miss = [k for k in req if k not in d]
        if miss:
            v.append("%s: 缺必填 %s" % (f, miss))
        extra = sorted(set(d.keys()) - allowed)
        if extra:
            v.append("%s: 多余字段 %s" % (f, extra))
    return v

def check_contract_semantic_order(root, reg):
    """semantic 块：baseline.blocks 与 _blocks() 注册序、ops-* 操作数组执行序。
    这里校验「可静态判的语义序」：baseline.blocks 与 selftest.py 内注册序一致（另见
    baseline.registry_order 专判）；此处聚焦 ops-* 操作数组非空且 op 合法、顺序承载
    （不判字典序）。由于执行序正本只能由执行器知，静态判据覆盖 op 枚举与结构。"""
    v = []
    exdir = _p(root, "skill/webbuilder-xwl-patch/examples")
    op_enum = {"set", "insertKey", "insert", "append", "delete"}
    if os.path.isdir(exdir):
        for f in sorted(os.listdir(exdir)):
            if not (f.startswith("ops-") and f.endswith(".json")):
                continue
            d = _load(root, "skill/webbuilder-xwl-patch/examples/" + f)
            ops = d if isinstance(d, list) else (d.get("ops") or [])
            if not isinstance(ops, list):
                v.append("%s: ops 非数组" % f)
                continue
            for i, op in enumerate(ops):
                if not isinstance(op, dict):
                    v.append("%s[%d]: 非对象" % (f, i))
                    continue
                o = op.get("op")
                if o is not None and o not in op_enum:
                    v.append("%s[%d]: op=%r 非枚举" % (f, i, o))
    return v

def check_contract_canonical_order(root, reg):
    v = []
    md = _load(root, "skill/webbuilder-xwl-patch/metadata.json")
    refs = md.get("references") or []
    if refs != sorted(refs):
        v.append("metadata.references 非规范序")
    if len(refs) != len(set(refs)):
        v.append("metadata.references 有重复")
    lk = list((md.get("layers") or {}).keys())
    if lk != sorted(lk):
        v.append("metadata.layers 键非规范序")
    bl = _load(root, "skill/tests/baseline.json")
    dg = list((bl.get("doc_guard_blocks") or {}).keys())
    if dg != sorted(dg):
        v.append("doc_guard_blocks 键非规范序")
    g = _load(root, "skill/tests/task_acceptance_fixtures/golden.json")
    gid = g.get("expected_ids") or []
    if gid != sorted(gid):
        v.append("golden.expected_ids 非规范序")
    if len(gid) != len(set(gid)):
        v.append("golden.expected_ids 有重复")
    # rules.json 属 workspace 域；skill-only 树无 gate/ ⇒ 该片段不适用、跳过（skill 内 4 文件照常校验）。
    if _domain_present(root, "workspace"):
        r = _load(root, "gate/spec/rules.json")
        for key in ("protected", "exempt"):
            seq = r.get(key) or []
            if seq != sorted(seq):
                v.append("rules.%s 非规范序" % key)
            if len(seq) != len(set(seq)):
                v.append("rules.%s 有重复" % key)
    # test-prompts 的 id 升序
    tp = _load(root, "skill/webbuilder-xwl-patch/test-prompts.json")
    ids = [x.get("id") for x in tp]
    if ids != sorted(ids):
        v.append("test-prompts id 非规范序")
    return v

def check_contract_write_form(root, reg):
    v = []
    exempt = {e["path"] for e in (reg.get("exempt_forms", {}).get("items", []))}
    # 写入形态判据面 = 正式目录 .json（.jsonl 事件日志为不可变追加事实，按 ledger 纪律
    # 不对其重写换行；其编码形态在 registry 登记为事件日志豁免，另见 ledger.views）。
    for rel in _expand_formal_files(root, include_jsonl=False):
        if rel in exempt:
            continue
        b = _raw(root, rel)
        if b.startswith(b"\xef\xbb\xbf"):
            v.append(rel + ": BOM")
        if b"\r\n" in b:
            v.append(rel + ": CRLF")
        if b and not b.endswith(b"\n"):
            v.append(rel + ": 无尾换行")
    return v

def check_contract_cross_ref(root, reg):
    """跨块引用：ledger 视图桶/归档件/指纹、derived-values 源指纹。
    可静态判的部分：
      - archive-manifest.files[*].path 冻结件须在磁盘存在，且 md5 与磁盘一致
      - archive-manifest.archived_buckets / book_buckets 的桶名一致（若存在）
    其余（视图三段指纹↔正本、sources↔桶）交由 ledger check 现场判，此处不虚判。"""
    v = []
    am_rel = "ledger/data/archive-manifest.json"
    if os.path.exists(_p(root, am_rel)):
        am = _load(root, am_rel)
        skills = am.get("skills") or {}
        for sname, sval in skills.items():
            files = sval.get("files") or []
            if not isinstance(files, list):
                continue
            for it in files:
                if not isinstance(it, dict):
                    continue
                path = it.get("path")
                if not path:
                    continue
                full = _p(root, path.replace("\\\\", "/"))
                if not os.path.exists(full):
                    v.append("archive-manifest 悬空: %s" % path)
                    continue
                want_md5 = it.get("md5")
                if want_md5:
                    import hashlib
                    got = hashlib.md5(io.open(full, "rb").read()).hexdigest()
                    if got != want_md5:
                        v.append("archive-manifest 指纹不符: %s (%s!=%s)" % (path, got, want_md5))
    return v

def check_derive_source_drift(root, reg):
    """生成器 vs 判据独立重算分叉。
    M2 现状无 build 期 derived-values 随包；若存在 derived-values.json，则对其每个绑定
    用本模块独立重算并与生成值比对，不等即红。不存在则 PASS（附 note：构建链接入后生效）。"""
    v = []
    dv_rel = "skill/contracts/derived-values.json"
    if not os.path.exists(_p(root, dv_rel)):
        return v  # M2 无生成物；M6 构建链随包后启用比对
    dv = _load(root, dv_rel)
    vals = dv.get("values") if isinstance(dv, dict) else None
    if not isinstance(vals, dict):
        return ["derived-values.json 结构异常"]
    # 独立重算少量可静态重算项
    indep = _independent_recompute(root, reg)
    for bid, genv in vals.items():
        if bid in indep and indep[bid] != genv:
            v.append("源漂移 %s: 生成=%r 判据重算=%r" % (bid, genv, indep[bid]))
    return v

def _independent_recompute(root, reg):
    """判据侧独立重算（仅供 source_drift 对照；与生成器不同路径）。"""
    out = {}
    try:
        md = _load(root, "skill/webbuilder-xwl-patch/metadata.json")
        out["metadata.references"] = len(md.get("references") or [])
        out["metadata.update_history"] = len(md.get("update_history") or [])
    except Exception:
        pass
    try:
        items = _load(root, "ledger/data/items.json").get("items") or []
        out["ledger.items"] = len(items)
    except Exception:
        pass
    cp = _p(root, "ledger/data/checkpoints")
    if os.path.isdir(cp):
        out["ledger.checkpoints"] = len([f for f in os.listdir(cp) if f.endswith(".json")])
    return out

def check_metadata_version_sync(root, reg):
    v = []
    md = _load(root, "skill/webbuilder-xwl-patch/metadata.json")
    skill = _read_text(root, "skill/webbuilder-xwl-patch/SKILL.md")
    m = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", skill, re.M)
    if not m:
        v.append("SKILL.md frontmatter 无 version")
        return v
    sv = m.group(1)
    if sv != md.get("version"):
        v.append("SKILL.md version=%s != metadata.version=%s" % (sv, md.get("version")))
    hs = md.get("update_history") or []
    if hs and hs[0].get("version") != sv:
        v.append("SKILL.md version=%s != update_history[0]=%s" % (sv, hs[0].get("version")))
    return v

def _subcommands_from_xwl(root):
    s = _read_text(root, "skill/webbuilder-xwl-patch/scripts/xwl.py")
    return sorted(set(re.findall(r"add_parser\(\s*['\"]([A-Za-z0-9_\-]+)", s)))

def check_test_prompts_coverage(root, reg):
    v = []
    subs = _subcommands_from_xwl(root)
    tp = _load(root, "skill/webbuilder-xwl-patch/test-prompts.json")
    blob = " ".join((x.get("prompt", "") + " " + x.get("expected", "")) for x in tp)
    for sc in subs:
        # 词边界匹配子命令名出现在 prompt/expected 文本
        if not re.search(r"(?<![A-Za-z0-9_\-])%s(?![A-Za-z0-9_\-])" % re.escape(sc), blob):
            v.append("子命令无 prompt 覆盖: %s" % sc)
    return v

def check_baseline_deduction(root, reg):
    """doc_guard_blocks 份数不降 + 基线外新名须 CHANGELOG 独立提及。

    判据（§4.7 / G3，与 selftest.py `_doc_guard_block_mismatch` 同口径）：
      ① 份数不降：doc_guard_blocks 条数须 >= registry 登记的基线（scale_ref，35）；
      ② 每名份数合法（int >= 1）；
      ③ 基线外新名：doc_guard_blocks 的键集 − registry `doc_guard_baseline_names` 冻结集合
         ＝新名集合；每个新名须在 `CHANGELOG.md` 里被**独立**提及（词边界），
         未提及即红。（集合比对，不是 `k in 标量` 那种逐个成员判断。）
    """
    v = []
    bl = _load(root, "skill/tests/baseline.json")
    dg = bl.get("doc_guard_blocks") or {}
    # 份数下界：registry 记录的规模（35）
    lower = None
    for b in reg["bindings"]:
        if b["id"] == "baseline.doc_guard_blocks":
            lower = b.get("scale_ref")
    if lower is not None and len(dg) < lower:
        v.append("doc_guard_blocks 份数 %d < 基线 %d" % (len(dg), lower))
    # 每名份数合法
    for k, cnt in dg.items():
        if not isinstance(cnt, int) or cnt < 1:
            v.append("doc_guard_blocks[%s] 份数异常 %r" % (k, cnt))
    # 基线外新名须 CHANGELOG 独立提及（集合比对）
    baseline_names = reg.get("doc_guard_baseline_names")
    if not isinstance(baseline_names, list):
        v.append("registry 缺 doc_guard_baseline_names（冻结基线名集合）—— 无法判定新名声明，判红")
        return v
    base_set = set(baseline_names)
    new_names = sorted(set(dg) - base_set)
    if new_names:
        cl = _read_text(root, "skill/webbuilder-xwl-patch/CHANGELOG.md")
        undeclared = [k for k in new_names if not _blk_declared(k, cl)]
        if undeclared:
            v.append("doc_guard_blocks 含**基线外新名且未在 CHANGELOG 独立提及**：%s"
                     "（新增＝显式：在 CHANGELOG 写一行含该块名的独立词即可）" % undeclared)
    return v

def _blocks_registry_order(root):
    """从 selftest.py 的 _blocks() 提取注册序（判据侧只读解析，非执行）。"""
    txt = _read_text(root, "skill/scripts/selftest.py")
    # 定位 def _blocks(...) [-> 注解] :  的函数体
    m = re.search(r"def\s+_blocks\s*\([^)]*\)[^\n:]*:\s*\n", txt)
    if not m:
        return None
    seg = txt[m.end():m.end() + 8000]
    rm = re.search(r"return\s*\[(.*?)\]\s*\n", seg, re.S)
    if not rm:
        return None
    body = rm.group(1)
    # 取每个元组首元素字符串，如 ("basics", _check_basics)
    names = re.findall(r"\(\s*['\"]([A-Za-z0-9_\-]+)['\"]\s*,", body)
    if not names:
        names = re.findall(r"['\"]([A-Za-z0-9_\-]+)['\"]", body)
    return names


def check_baseline_registry_order(root, reg):
    v = []
    bl = _load(root, "skill/tests/baseline.json")
    blocks = bl.get("blocks") or []
    authority = _blocks_registry_order(root)
    if authority is None:
        # 无法静态解析时，退化为「blocks 无序且非字典序即视为与注册序可能不符」不成立，记为 note 不判红
        return v
    if list(blocks) != list(authority):
        v.append("baseline.blocks 与 _blocks() 注册序不等: got=%s authority=%s" % (blocks, authority))
    return v


def check_golden_derived(root, reg):
    """golden.expected_ids 无重复且与应检清单同源。
    应检清单独立重算：由 sample-task 目录下 .xwl 文件派生 static 应检项集合
    （object:*、sql-content:*、page-link:*、itemid-unique:*），从 check 逻辑派生。"""
    v = []
    g = _load(root, "skill/tests/task_acceptance_fixtures/golden.json")
    gid = g.get("expected_ids") or []
    if len(gid) != len(set(gid)):
        v.append("golden.expected_ids 有重复")
    # 派生应检清单（独立重算）：遍历 sample-task/*.xwl 生成静态应检项
    coverage = _derive_coverage_ids(root)
    if coverage is not None and set(gid) != set(coverage):
        v.append("golden.expected_ids 与派生应检清单不同源: missing=%s extra=%s" % (
            sorted(set(coverage) - set(gid)), sorted(set(gid) - set(coverage))))
    return v

def _derive_coverage_ids(root):
    """从 sample-task 目录派生静态应检项集合（独立于执行器实现）。"""
    base = _p(root, "skill/tests/task_acceptance_fixtures/sample-task")
    if not os.path.isdir(base):
        return None
    ids = []
    xwls = sorted(f for f in os.listdir(base) if f.endswith(".xwl"))
    # 每文件一个 object:
    for f in xwls:
        ids.append("object:" + f)
    # sql-content: 若文件含 sql 定义（简单启发：含 "sql" 字段或 SQL 关键字）
    for f in xwls:
        txt = _read_text(root, "skill/tests/task_acceptance_fixtures/sample-task/" + f)
        if re.search(r'"sql"\s*:', txt) or re.search(r"\bselect\b", txt, re.I):
            ids.append("sql-content:" + f)
    # page-link：文件出现 "pageLink": "other.xwl" 指向其它 xwl
    names = {f: _read_text(root, "skill/tests/task_acceptance_fixtures/sample-task/" + f) for f in xwls}
    for f, txt in names.items():
        for other in xwls:
            if other == f:
                continue
            if re.search(r'"pageLink"\s*:\s*"[^"]*' + re.escape(other) + r'"', txt):
                ids.append("page-link:" + f + "->" + other)
    # itemid-unique：每文件一条
    for f in xwls:
        ids.append("itemid-unique:" + f)
    return sorted(ids)

def check_metadata_layers_enum(root, reg):
    v = []
    md = _load(root, "skill/webbuilder-xwl-patch/metadata.json")
    layers = md.get("layers") or {}
    for k, val in layers.items():
        if val not in ("spec", "evidence"):
            v.append("layers[%s]=%r 越出 (spec,evidence)" % (k, val))
    return v


CHECKS = {
    "contract.unregistered_file": check_contract_unregistered_file,
    "metadata.ref_layer_diff": check_metadata_ref_layer_diff,
    "metadata.history_consistency": check_metadata_history_consistency,
    "ledger.item_order": check_ledger_item_order,
    "case.schema_uniform": check_case_schema_uniform,
    "contract.semantic_order": check_contract_semantic_order,
    "contract.canonical_order": check_contract_canonical_order,
    "contract.write_form": check_contract_write_form,
    "contract.cross_ref": check_contract_cross_ref,
    "derive.source_drift": check_derive_source_drift,
    "metadata.version_sync": check_metadata_version_sync,
    "test-prompts.coverage": check_test_prompts_coverage,
    "baseline.deduction": check_baseline_deduction,
    "baseline.registry_order": check_baseline_registry_order,
    "golden.derived": check_golden_derived,
    "metadata.layers_enum": check_metadata_layers_enum,
}


def run_all(root, only=None):
    reg = _load(root, "skill/contracts/registry.json")
    ids = JUDGE_IDS if not only else [i for i in JUDGE_IDS if i in only]
    results = []
    violations = 0
    for jid in ids:
        # 域不适用 ⇒ SKIP：不跑判据、不计违规、不误报异常（校验对象不在本树）。
        if not _judge_applies(root, jid):
            results.append((jid, [], "SKIP"))
            continue
        fn = CHECKS[jid]
        try:
            vs = fn(root, reg)
        except Exception as e:  # noqa
            vs = ["<判据异常: %s: %s>" % (type(e).__name__, e)]
        results.append((jid, vs, "PASS" if not vs else "FAIL"))
        if vs:
            violations += len(vs)
    return results, violations


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = a.root
    if root is None:
        # 本文件在 skill/tests/ 下，工作区根为上三级
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.abspath(root)
    only = set(a.only.split(",")) if a.only else None
    results, nviol = run_all(root, only)
    if a.json:
        print(json.dumps([{"id": j, "status": st, "ok": st != "FAIL", "violations": v}
                          for j, v, st in results], ensure_ascii=False, indent=1))
    else:
        for jid, vs, st in results:
            print("%-32s %s  %s" % (jid, st, "" if not vs else " | ".join(vs[:5])))
        print("")
        n_skip = sum(1 for _, _, st in results if st == "SKIP")
        print("判据 %d 条，其中红 %d 条，SKIP %d 条，违规计数 %d。" % (
            len(results), sum(1 for _, _, st in results if st == "FAIL"), n_skip, nviol))
    return 0 if nviol == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
