# -*- coding: utf-8 -*-
"""Survey-branch gates (S0–S5). Run by Claude, never by the user.

  python survey_check.py scope    [--state research-state.yaml] [--project .]   G-S0: scope_in/scope_out/axis/thesis + guide
  python survey_check.py search   [--state ...] [--project .]                   G-S1: search_log.json, candidates.csv, prior_surveys.csv
  python survey_check.py protocol [--protocol protocol.md] [--codebook coding/codebook.md] [--state research-state.yaml]   G-S2
  python survey_check.py coding   [--state research-state.yaml] [--project .]   G-S3
  python survey_check.py tables   [--state ...] [--project .]                   G-S4: *summary*.py --verify, coverage.csv sums, figures.csv
  python survey_check.py claims   [--state research-state.yaml] [--project .]   G-S5 (claims + writing)
  python survey_check.py writing  [--state ...] [--project .]                   G-S5 writing part only: tensions ledger, catalogue
                                                                                paragraphs, bounded novelty, included studies cited,
                                                                                reporting checklist

state.survey:
  scope_in: ""              scope_out: ""          axis: ""              thesis: ""
  screening_sheet: coding/screening_sheet.csv     # decision, reason, screen_pass, + an identifier column (doi|pmid|arxiv_id)
  coded: coding/coded.csv                          # one row per included study; columns ⊆ codebook fields
  codebook: coding/codebook.md                     # markdown table: | column | values | rule |
  prisma: literature/prisma_flow.json              # {identified, deduplicated, screened_title, screened_abstract, included}
  kappa: coding/kappa_results.json                 # optional {field: kappa}; min_kappa below
  min_kappa: 0.6
  tables_dir: tables                               # every csv here must be re-derivable from coded.csv (script with --verify)
  coverage: coding/coverage.csv                    # axis × facet counts; row/col totals must equal included count
  prior_surveys: literature/prior_surveys.csv      # title, year, venue, doi, how_this_differs
  claims: paper/claims.csv                         # claim_id, statement, evidence_file, evidence_key, scope_words, verified
  review_type: narrative                           # narrative | scoping | systematic — systematic/scoping make the QC sample and the PRISMA checklist mandatory
  seed_studies: literature/seed_studies.csv        # gold set the search must retrieve (doi|pmid|arxiv_id|title); recall ≥ min_seed_recall
  min_seed_recall: 1.0
  saturation_rounds: 2                             # the last N snowball rounds in search_log.json must have new_included = 0
  qc_sample: coding/qc_exclusion_sample.csv        # survey_tables.py qc-sample: random + near-miss exclusions re-screened blind
  tables_spec: coding/tables.yaml                  # survey_tables.py summary spec (alternative to a hand-written coding/*summary*.py)
  skew_dims: []                                    # coded columns where one value ≥ 70 % of known values is reported (advisory)
  tensions: coding/tensions.csv                    # cross-study tension ledger (see check_tensions)
  manuscript: paper/manuscript.md
  reporting_checklist: paper/prisma_checklist.csv  # item, topic, location — every item located (systematic / scoping)
Exit 1 on any FAIL."""
import argparse, csv, io, json, os, re, sys, collections
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, g, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {g}: {msg}")

def load_state(p):
    import yaml
    return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}

def section(md, name):
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return ""
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

def md_table(txt):
    rows = [l for l in txt.splitlines() if l.strip().startswith("|")]
    out = []
    for l in rows[2:]:
        # a `|` inside backticks is content, not a column separator
        prot = re.sub(r"`([^`]*)`", lambda m: "`" + m.group(1).replace("|", "\x00") + "`", l)
        cells = [c.strip().replace("\x00", "|") for c in prot.strip().strip("|").split("|")]
        if cells and cells[0] and not set(cells[0]) <= set("-: "): out.append(cells)
    return out

def parse_codebook(p):
    """-> {column: (values_set or None, joined_subset: bool)}; None = free text / numeric."""
    if not os.path.exists(p): return None
    fields = {}
    for cells in md_table(io.open(p, encoding="utf-8").read()):
        col = cells[0].strip("` "); vals = cells[1] if len(cells) > 1 else ""
        if re.search(r"free text|\bfloat\b|\bint\b|\bnumber\b|token\b|任意|自由|数值", vals, re.I) and "{" not in vals:
            fields[col] = (None, False); continue
        joined = bool(re.search(r"joined|subset|连接|子集|multi", vals, re.I))
        inner = re.search(r"\{([^}]*)\}", vals)
        src = inner.group(1) if inner else re.sub(r"\(.*?\)", "", vals)
        vs = {v.strip("` ") for v in re.split(r",|/|\|", src) if v.strip("` ")}
        vs = {v for v in vs if not re.search(r"\s", v) or len(v) < 12}
        fields[col] = (vs if vs else None, joined)
    return fields

# ------------------------------------------------------------------ protocol (S2)
DECIDABLE = re.compile(r"(≥|>=|<=|≤|\bat least\b|\bno more than\b|\d{4}|\d+\s*(?:篇|个|years?|年|%)|\bboth\b|\bmust\b|命中|含|includes?|reports?|\bbefore\b|\bafter\b|\bbetween\b|\bto\b.*\bdate\b|\bpeer[- ]reviewed\b|English|英文|such as|e\.g\.|如|例如|covered by|由.*覆盖|\[\d+\])", re.I)

def check_protocol(prot_p, cb_p, state_p):
    if not os.path.exists(prot_p): say("FAIL", "protocol", f"{prot_p} 不存在"); return
    md = io.open(prot_p, encoding="utf-8").read()
    for name in ("inclusion", "exclusion", "codebook", "claims", "prediction"):
        if not section(md, name).strip() and not section(md, {"inclusion": "纳入", "exclusion": "排除", "codebook": "编码", "claims": "主张", "prediction": "预测"}[name]).strip():
            say("FAIL", "protocol", f"缺少小节: {name}")
    rules = [l for l in (section(md, "inclusion") + section(md, "纳入") + section(md, "exclusion") + section(md, "排除")).splitlines() if re.match(r"^\s*(?:[-*]|\d+[.)]|\|)", l)]
    vague = [r.strip()[:70] for r in rules if not DECIDABLE.search(r) and len(r.split()) > 3 and not r.strip().startswith("|--")]
    if not rules: say("FAIL", "protocol", "纳入/排除规则为空（要列表或表格，每条可机械判定）")
    elif vague: say("FAIL", "protocol", f"{len(vague)} 条纳入/排除规则无可判定词（阈值/数量/必须含/年份）: {vague[:3]}")
    else: say("PASS", "protocol", f"{len(rules)} 条纳入/排除规则均含可判定词")
    fields = parse_codebook(cb_p)
    if fields is None: say("FAIL", "protocol", f"codebook {cb_p} 不存在")
    else:
        bad = [c for c, (v, _) in fields.items() if v is None and not re.search(r"note|free|text|n_|float|year|title|doi|id$|disease|P_|delta|which", c, re.I)]
        say("FAIL" if bad else "PASS", "protocol", f"codebook {len(fields)} 个字段" + (f"，{len(bad)} 个既无取值集合也不是自由文本/数值: {bad[:5]}" if bad else "，每个字段有取值集合或标明自由文本"))
    claims = md_table(section(md, "claims") + section(md, "主张"))
    if not claims: say("FAIL", "protocol", "主张清单为空（表格：claim | 判据 | 事前预测）")
    else:
        nocrit = [c[0][:40] for c in claims if len(c) < 2 or not re.search(r"[<>≥≤=]|median|中位|占比|fraction|if\b|若|then", " ".join(c[1:]), re.I)]
        say("FAIL" if nocrit else "PASS", "protocol", f"{len(claims)} 条主张" + (f"，{len(nocrit)} 条无判据: {nocrit[:3]}" if nocrit else "，每条有判据"))
    kp = section(md, "kappa") + section(md, "κ") + section(md, "second coder") + section(md, "第二编码")
    say("PASS" if kp.strip() else "WARN", "protocol", "κ 验证计划" + ("已写" if kp.strip() else "未写：单人筛选的综述审稿人必问编码可靠性"))
    import hashlib
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    locked = None
    if os.path.exists(state_p):
        st = io.open(state_p, encoding="utf-8").read(); m = re.search(r"protocol_sha256:\s*\"?([0-9a-f]{64})", st); locked = m.group(1) if m else None
        if locked and locked != sha: say("FAIL", "protocol", f"protocol.md 改过但锁未更新（锁 {locked[:8]}… 现 {sha[:8]}…）；改口径要在 convention_changes 留记录再重锁")
    if not locked: say("INFO", "protocol", f"sha256 = {sha} → 写入 state gates.G-S2.protocol_sha256 即锁定")

# ------------------------------------------------------------------ coding (S3)
def check_coding(cfg, root):
    sp = os.path.join(root, cfg.get("screening_sheet", "coding/screening_sheet.csv"))
    cp = os.path.join(root, cfg.get("coded", "coding/coded.csv"))
    cb = parse_codebook(os.path.join(root, cfg.get("codebook", "coding/codebook.md")))
    if not os.path.exists(sp): say("FAIL", "coding", f"{sp} 不存在"); return
    rows = list(csv.DictReader(open(sp, encoding="utf-8-sig")))
    dec = collections.Counter((r.get("decision") or "").strip().lower() for r in rows)
    bad_dec = sum(1 for r in rows if (r.get("decision") or "").strip().lower() not in ("include", "maybe", "exclude", "pending", ""))
    if dec["pending"]:
        # a failed or unfinished screening call stays pending; it is never silently an exclude, and no final count is reported meanwhile
        say("FAIL", "coding", f"{dec['pending']} 行 decision=pending（调用失败或待复核）：pending 清零前 PRISMA 计数与方法节数字都不是终值")
    no_reason = sum(1 for r in rows if (r.get("decision") or "").strip() and not (r.get("reason") or "").strip())
    no_id = sum(1 for r in rows if (r.get("decision") or "").strip() and not any((r.get(k) or "").strip() for k in ("doi", "pmid", "arxiv_id", "openalex_id")))
    say("FAIL" if (bad_dec or no_reason) else "PASS", "coding", f"screening {len(rows)} 行: include {dec['include']} maybe {dec['maybe']} exclude {dec['exclude']} 未决 {dec['']}；非法 decision {bad_dec}；有决定无理由 {no_reason}")
    if no_id: say("FAIL", "coding", f"screening {no_id} 行已有决定但无任何标识符（doi/pmid/arxiv_id/openalex_id）")
    if dec["maybe"]: say("WARN", "coding", f"{dec['maybe']} 行仍是 maybe，摘要级筛选未完成")
    if not os.path.exists(cp): say("FAIL", "coding", f"{cp} 不存在"); return
    coded = list(csv.DictReader(open(cp, encoding="utf-8-sig")))
    if cb:
        unknown_cols = [c for c in coded[0].keys() if c not in cb and not c.startswith("_") and c not in ("idx", "title", "year", "doi", "pmid", "arxiv_id", "source", "notes")] if coded else []
        if unknown_cols: say("WARN", "coding", f"coded.csv 有 codebook 未定义的列: {unknown_cols[:6]}")
        bad_vals = collections.defaultdict(collections.Counter)
        for r in coded:
            for c, (allowed, joined) in cb.items():
                if not allowed or c not in r: continue
                v = (r[c] or "").strip()
                if not v or v == "?": continue
                parts = [x.strip() for x in v.split("|")] if joined else [v]
                for x in parts:
                    if x not in allowed: bad_vals[c][x] += 1
        if bad_vals:
            for c, cnt in bad_vals.items():
                say("FAIL", "coding", f"coded.csv 列 {c} 有 {sum(cnt.values())} 个值不在 codebook 集合 {sorted(cb[c][0])[:8]}: {dict(cnt.most_common(6))} —— 要么改 codebook 加取值，要么重编")
        else: say("PASS", "coding", f"coded.csv {len(coded)} 行全部字段取值 ∈ codebook")
    inc_ids = {(r.get("doi") or r.get("pmid") or r.get("arxiv_id") or "").strip() for r in rows if (r.get("decision") or "").lower() == "include"}
    cod_ids = {(r.get("doi") or r.get("pmid") or r.get("arxiv_id") or "").strip() for r in coded}
    if inc_ids and cod_ids:
        miss = inc_ids - cod_ids - {""}
        if miss: say("WARN", "coding", f"{len(miss)} 篇 include 未进 coded.csv（审计子集可以小于纳入集，但要在正文说明）")
    pp = os.path.join(root, cfg.get("prisma", "literature/prisma_flow.json"))
    if os.path.exists(pp):
        pr = json.load(open(pp, encoding="utf-8"))
        keys = ["identified", "deduplicated", "screened_title", "screened_abstract", "included"]
        # tolerate the InfoFusion naming: candidates → identified/deduplicated, P1+P2 → screened_title, include → included
        alias = {"identified": ("identified", "candidates", "n_raw"), "deduplicated": ("deduplicated", "candidates", "n_dedup"), "screened_title": ("screened_title", "title_screened"), "screened_abstract": ("screened_abstract", "abstract_screened"), "included": ("included", "include")}
        got = {}
        for k, names in alias.items():
            for n in names:
                if n in pr and isinstance(pr[n], (int, float)): got[k] = int(pr[n]); break
        if "screened_title" not in got and all(t in pr for t in ("P1", "P2")): got["screened_title"] = int(pr["P1"]) + int(pr["P2"])
        if "screened_abstract" not in got:
            # abstract-level screening count = title-level includes + maybes that were then read at abstract level; fall back to title count
            ta = pr.get("by_tier") or {}
            got["screened_abstract"] = sum(int(t.get("include", 0)) + int(t.get("maybe", 0)) for t in ta.values()) if ta else got.get("screened_title", 0)
        missing = [k for k in keys if k not in got]
        if missing: say("FAIL", "coding", f"prisma_flow.json 缺计数: {missing}（现有键 {list(pr)[:8]}）")
        else:
            ok = got["identified"] >= got["deduplicated"] >= got["screened_title"] >= got["screened_abstract"] >= got["included"]
            hint = ""
            if not ok and got["included"] > got["screened_abstract"]:
                hint = f"；included {got['included']} > screened_abstract {got['screened_abstract']} 说明 included 记的是标题级纳入数，摘要级筛选尚未完成（maybe 仍有 {got['screened_abstract']}）——完成后再更新 prisma_flow.json"
            say("PASS" if ok else "FAIL", "coding", "PRISMA " + " ≥ ".join(f"{k} {got[k]}" for k in keys) + ("" if ok else " —— 单调性不成立" + hint))
            if ok and dec["include"] and got["included"] != dec["include"]: say("FAIL", "coding", f"PRISMA included {got['included']} ≠ screening include {dec['include']}")
    else: say("WARN", "coding", "无 prisma_flow.json")
    kp = os.path.join(root, cfg.get("kappa", "coding/kappa_results.json")); mk = float(cfg.get("min_kappa", 0.6))
    if os.path.exists(kp):
        k = json.load(open(kp, encoding="utf-8")); low = {f: v for f, v in k.items() if isinstance(v, (int, float)) and v < mk}
        det = k.get("_detail") or {}
        # prevalence paradox: 97.8 % raw agreement can give κ≈0.47 when one category dominates; PABAK ≥ 0.8 shows the coders agree
        paradox = {f for f in low if isinstance(det.get(f), dict) and (det[f].get("pabak") or 0) >= 0.8}
        hard = {f: v for f, v in low.items() if f not in paradox}
        say("FAIL" if hard else "PASS", "coding", f"κ: " + ", ".join(f"{f}={v:.2f}" for f, v in k.items() if isinstance(v, (int, float))) + (f" —— {list(hard)} < {mk}，该字段的 codebook 规则要改或正文明写" if hard else ""))
        if paradox: say("WARN", "coding", f"{sorted(paradox)} κ < {mk} 但 PABAK ≥ 0.8（一个类别占绝大多数时 κ 被压低）：正文同时报一致率、κ 与 PABAK")
    else: say("WARN", "coding", "无 kappa_results.json：单人编码未验证（survey_tables.py kappa 从两份编码算）")
    check_qc(cfg, root, rows)

def _ident(r):
    for k in ("doi", "pmid", "arxiv_id", "openalex_id"):
        v = (r.get(k) or "").strip().lower()
        if v: return f"{k}:{v}"
    return ""

def check_qc(cfg, root, screening):
    """joint-exclusion audit: a random sample of excludes plus near-miss excludes, re-screened by a reviewer who does not see
    the first decision. Two runs of the same model share misreadings, so agreement alone does not show the excludes are right."""
    qp = os.path.join(root, cfg.get("qc_sample", "coding/qc_exclusion_sample.csv"))
    strict = str(cfg.get("review_type", "narrative")).lower() in ("systematic", "scoping")
    if not os.path.exists(qp):
        say("FAIL" if strict else "WARN", "coding", f"无 {os.path.relpath(qp, root)}：排除记录没有抽样复核（survey_tables.py qc-sample 生成，复核者看不到原决定）" + ("；系统/范围综述必做" if strict else ""))
        return
    qc = list(csv.DictReader(open(qp, encoding="utf-8-sig")))
    undone = [q for q in qc if (q.get("qc_decision") or "").strip().lower() not in ("include", "exclude")]
    if undone: say("FAIL", "coding", f"QC 抽样 {len(undone)}/{len(qc)} 行未复核（qc_decision ∈ include | exclude）")
    cur = {_ident(r): (r.get("decision") or "").strip().lower() for r in screening}
    flips = [q for q in qc if (q.get("qc_decision") or "").strip().lower() == "include"]
    stale = [_ident(q) for q in flips if cur.get(_ident(q)) == "exclude"]
    if stale: say("FAIL", "coding", f"QC 复核判 include 的 {len(stale)} 篇在 screening_sheet 里仍是 exclude: {stale[:4]} —— 改成 include/maybe 并重算 PRISMA")
    if qc and not undone:
        by = collections.Counter((q.get("sample_type") or "random").strip() for q in qc); fl = collections.Counter((q.get("sample_type") or "random").strip() for q in flips)
        rate = {t: f"{fl[t]}/{n}" for t, n in by.items()}
        say("WARN" if flips else "PASS", "coding", f"排除复核 {len(qc)} 篇，误排 {len(flips)}（{rate}）" + ("：误排 > 0 说明排除规则有漏，相近记录要整层重看，正文报误排率" if flips else ""))

# ------------------------------------------------------------------ claims (S5)
def lookup(root, file, key):
    p = os.path.join(root, file)
    if file.endswith(".json"):
        o = json.load(open(p, encoding="utf-8"))
        for part in key.split("."): o = o[int(part)] if isinstance(o, list) else o[part]
        return o
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    if "=" in key:
        sel, col = key.rsplit(",", 1); conds = [kv.split("=", 1) for kv in sel.split("|")]
        hit = [r for r in rows if all(r.get(k) == v for k, v in conds)]
        if len(hit) != 1: raise KeyError(f"{sel} 命中 {len(hit)} 行")
        return hit[0][col]
    i, col = key.split(",", 1); return rows[int(i)][col]

def check_claims(cfg, root):
    cp = os.path.join(root, cfg.get("claims", "paper/claims.csv"))
    if not os.path.exists(cp): say("FAIL", "claims", f"{cp} 不存在"); return
    rows = list(csv.DictReader(open(cp, encoding="utf-8-sig")))
    bad = 0
    for r in rows:
        f, k = (r.get("evidence_file") or "").strip(), (r.get("evidence_key") or "").strip()
        if not f or not k: bad += 1; say("FAIL", "claims", f"{r.get('claim_id')}: evidence_file/evidence_key 为空"); continue
        if not os.path.exists(os.path.join(root, f)): bad += 1; say("FAIL", "claims", f"{r.get('claim_id')}: {f} 不存在"); continue
        try: v = lookup(root, f, k)
        except Exception as ex: bad += 1; say("FAIL", "claims", f"{r.get('claim_id')}: {f}#{k} 取不到 ({ex})"); continue
        if (r.get("expected") or "").strip():
            e = r["expected"].strip(); m = re.match(r"([<>≥≤=]+)\s*([\d.]+)", e)
            if m:
                op, thr = m.group(1), float(m.group(2))
                try: x = float(v)
                except Exception: bad += 1; say("FAIL", "claims", f"{r.get('claim_id')}: 证据值 {v!r} 非数值"); continue
                ok = {"<": x < thr, "<=": x <= thr, "≤": x <= thr, ">": x > thr, ">=": x >= thr, "≥": x >= thr, "=": abs(x - thr) < 1e-9}.get(op, True)
                if not ok: bad += 1; say("FAIL", "claims", f"{r.get('claim_id')}: {f}#{k} = {x} 不满足判据 {e}")
    tp = os.path.join(root, cfg.get("prior_surveys", "literature/prior_surveys.csv"))
    strong = [r for r in rows if re.search(r"\b(first|only|no (?:prior|existing)|唯一|首个|首次)\b", (r.get("statement") or "") + " " + (r.get("scope_words") or ""), re.I)]
    if strong:
        if not os.path.exists(tp): bad += 1; say("FAIL", "claims", f"{len(strong)} 条 first/only 类主张，但无 {tp} 可对照")
        else:
            ps = list(csv.DictReader(open(tp, encoding="utf-8-sig"))); nodiff = [p.get("title", "")[:40] for p in ps if not (p.get("how_this_differs") or "").strip()]
            say("FAIL" if nodiff else "PASS", "claims", f"{len(strong)} 条 first/only 主张；已有综述表 {len(ps)} 行" + (f"，{len(nodiff)} 行未写本文差异: {nodiff[:3]}" if nodiff else "，每行有差异说明"))
    # tables re-derivable
    td = os.path.join(root, cfg.get("tables_dir", "tables"))
    if os.path.isdir(td):
        gen = [f for f in os.listdir(os.path.join(root, "coding")) if f.endswith(".py") and "summary" in f] if os.path.isdir(os.path.join(root, "coding")) else []
        if os.path.exists(os.path.join(root, cfg.get("tables_spec", "coding/tables.yaml"))): gen.append("tables.yaml")
        say("PASS" if gen else "WARN", "claims", f"tables/ 有 {len([f for f in os.listdir(td) if f.endswith('.csv')])} 张 csv" + ("，有生成定义" if gen else "，但无 *summary*.py 或 tables.yaml：汇总表必须能从 coded.csv 重算"))
    if bad == 0: say("PASS", "claims", f"{len(rows)} 条主张全部能回到证据文件的具体行且满足判据")
    check_writing(cfg, root)

# ------------------------------------------------------------------ writing (S5): synthesis, not catalogue
TENSION_A = {"contradiction", "conditional_difference", "no_material_conflict", "insufficient_overlap"}
TENSION_R = {"resolved_in_synthesis", "flagged_unresolved", "not_applicable"}
SYNTH = re.compile(r"\b(however|whereas|while|in contrast|by contrast|unlike|conversely|similarly|likewise|both|all|most|few|none of|across|together|common(?:ly)?|consistent(?:ly)?|inconsistent|conflict\w*|contradict\w*|disagree\w*|agree\w*|compared?|comparison|differ\w*|trade-?off|only when|depends? on|regardless|pattern|trend|majority|minority|in general|overall|taken together)\b|然而|相比|不同于|一致|矛盾|多数|少数|共同|总体|取决于", re.I)
CITE = re.compile(r"\[@[^\]]+\]|\\cite[pt]?\{[^}]+\}|\[\d+(?:[,–-]\s*\d+)*\]|\(\w[\w-]+ et al\.,? \d{4}\)|\b\w[\w-]+ et al\. \(\d{4}\)")
OPENER = re.compile(r"^\s*(?:\[@[^\]]+\]|\\cite[pt]?\{[^}]+\}|\[\d+\]|[A-Z][\w-]+ et al\.|[A-Z][\w-]+ and [A-Z][\w-]+|In \[\d+\]|In \\cite|The authors of|They\b)", re.M)
UNBOUNDED = re.compile(r"\b(no (?:prior|previous|existing) (?:study|work|survey|review)|no study has|has never been|all (?:contradictions|conflicts|inconsistencies) (?:are|were|have been) (?:resolved|addressed)|first (?:survey|review) (?:to|that))\b", re.I)
BOUND = re.compile(r"\b(within|among|in) (?:the |our )?(?:searched|included|retrieved|reviewed) (?:sources|studies|literature|corpus|records)|\bto (?:the best of )?our knowledge|date range|as of \d{4}|检索范围内|纳入的研究中", re.I)

def _paragraphs(md):
    """body paragraphs with their first line number; headings, tables, lists, figure/table captions, and the reference list dropped."""
    md = re.split(r"(?m)^#{1,3}\s*(?:References|Bibliography|参考文献)\b", md)[0]
    out, buf, start = [], [], 0
    for i, l in enumerate(md.splitlines() + [""], 1):
        if l.strip() and not re.match(r"\s*(#|\||[-*+]\s|\d+[.)]\s|!\[|>|<!--|(?:Table|Figure|Fig\.)\s*\d)", l): buf.append(l); start = start or i; continue
        if buf: out.append((start, " ".join(buf))); buf, start = [], 0
    return out

def check_writing(cfg, root):
    mp = os.path.join(root, cfg.get("manuscript", "paper/manuscript.md"))
    md = io.open(mp, encoding="utf-8").read() if os.path.exists(mp) else ""
    check_tensions(cfg, root, md)
    if not md: say("WARN", "writing", f"无 {os.path.relpath(mp, root)}：目录式段落、引用覆盖与报告清单未查"); return
    # 1. catalogue paragraphs: ≥3 sentences, most of them open on a single citation, and no comparative or synthesising word
    cat, cited = [], 0
    for ln, p in _paragraphs(md):
        sents = [s for s in re.split(r"(?<=[.!?。])\s+", p) if len(s.split()) >= 4]
        if not CITE.search(p): continue
        cited += 1
        if len(sents) < 3: continue
        led = sum(1 for s in sents if OPENER.match(s) or (len(CITE.findall(s)) == 1 and CITE.search(s).start() < 40))
        if led / len(sents) >= 0.6 and not SYNTH.search(p): cat.append(ln)
    if cited:
        share = len(cat) / cited
        say("WARN" if cat else "PASS", "writing", f"{len(cat)}/{cited} 个带引用段落是逐篇罗列（多数句以单篇引用开头、无比较/归纳词）" + (f"，行 {cat[:8]}：改成 主题句 → 3–5 篇证据 → 对比/冲突 → 判断（编辑退稿理由「这是目录不是综述」）" if cat else ""))
        if share > 0.3: say("FAIL", "writing", f"逐篇罗列段占带引用段落 {share:.0%} > 30%：整篇读起来是目录")
    # 2. bounded novelty / completeness statements
    unb = [i for i, l in enumerate(md.splitlines(), 1) if UNBOUNDED.search(l) and not BOUND.search(l)]
    if unb: say("WARN", "writing", f"行 {unb[:6]} 有无边界的「首个 / 无人研究 / 矛盾已全部解决」说法：改成「在检索的数据库与日期范围内」并指向 prior_surveys / tensions")
    # 3. every included study is cited somewhere (body or characteristics table)
    cp = os.path.join(root, cfg.get("coded", "coding/coded.csv"))
    if os.path.exists(cp):
        coded = list(csv.DictReader(open(cp, encoding="utf-8-sig")))
        if coded and "bibkey" in coded[0]:
            pool = md
            for f in ("tables/characteristics.tex", "tables/characteristics.md"):
                if os.path.exists(os.path.join(root, f)): pool += io.open(os.path.join(root, f), encoding="utf-8").read()
            keys = [(r.get("bibkey") or "").strip() for r in coded]
            miss = [k for k in keys if k and not re.search(r"(?<![\w:-])" + re.escape(k) + r"(?![\w:-])", pool)]
            nokey = sum(1 for k in keys if not k)
            say("WARN" if (miss or nokey) else "PASS", "writing", f"纳入 {len(keys)} 篇" + (f"，{len(miss)} 篇正文与特征表都没引: {miss[:5]}" if miss else "，每篇在正文或特征表被引") + (f"；{nokey} 篇 bibkey 为空" if nokey else ""))
    # 4. reporting checklist (PRISMA 2020 / PRISMA-ScR): every item has a location
    strict = str(cfg.get("review_type", "narrative")).lower() in ("systematic", "scoping")
    rp = os.path.join(root, cfg.get("reporting_checklist", "paper/prisma_checklist.csv"))
    if os.path.exists(rp):
        items = list(csv.DictReader(open(rp, encoding="utf-8-sig")))
        nl = [r.get("item") for r in items if not (r.get("location") or "").strip() or (r.get("location") or "").strip().lower() in ("todo", "tbd", "?")]
        na = [r.get("item") for r in items if (r.get("location") or "").strip().lower() in ("n/a", "na", "not applicable")]
        say("FAIL" if (nl and strict) else ("WARN" if nl else "PASS"), "writing", f"报告清单 {len(items)} 项，{len(items) - len(nl)} 项已定位" + (f"，未定位: {nl[:8]}" if nl else "") + (f"；{len(na)} 项标 N/A（审稿人会看理由）" if na else ""))
    elif strict: say("FAIL", "writing", f"review_type={cfg.get('review_type')} 但无 {os.path.relpath(rp, root)}（templates/prisma2020_checklist.csv 拷过去逐项填 location）")

def check_tensions(cfg, root, md):
    """cross-study tension ledger. Two orthogonal axes: is it a real conflict (pair_assessment), and did the review deal with it
    (resolution_status). A real contradiction cannot be not_applicable; a resolved one must point at the place in the manuscript."""
    tp = os.path.join(root, cfg.get("tensions", "coding/tensions.csv"))
    if not os.path.exists(tp):
        say("WARN", "writing", f"无 {os.path.relpath(tp, root)}：没有逐对记录研究间的冲突（study_a, study_b, topic, pair_assessment, resolution_status, resolution_pointer）"); return
    rows = list(csv.DictReader(open(tp, encoding="utf-8-sig"))); bad = []
    for i, r in enumerate(rows, 2):
        a = (r.get("pair_assessment") or "").strip(); s = (r.get("resolution_status") or "").strip(); ptr = (r.get("resolution_pointer") or "").strip()
        if a not in TENSION_A: bad.append(f"行 {i} pair_assessment={a!r} ∉ {sorted(TENSION_A)}"); continue
        if s not in TENSION_R: bad.append(f"行 {i} resolution_status={s!r} ∉ {sorted(TENSION_R)}"); continue
        if a in ("contradiction", "conditional_difference") and s == "not_applicable": bad.append(f"行 {i} 真冲突不能标 not_applicable")
        if a in ("no_material_conflict", "insufficient_overlap") and s != "not_applicable": bad.append(f"行 {i} {a} 只能配 not_applicable")
        if s == "resolved_in_synthesis":
            if not ptr: bad.append(f"行 {i} resolved_in_synthesis 缺 resolution_pointer（正文哪一节/哪句话处理了它）")
            elif md and ptr.lower() not in md.lower(): bad.append(f"行 {i} resolution_pointer {ptr[:30]!r} 在正文里找不到")
    for b in bad: say("FAIL", "writing", "tensions: " + b)
    real = [r for r in rows if (r.get("pair_assessment") or "").strip() in ("contradiction", "conditional_difference")]
    unres = [r for r in real if (r.get("resolution_status") or "").strip() == "flagged_unresolved"]
    if unres and md and not re.search(r"unresolved|open question|remain(?:s)? unclear|inconsistent|conflicting|未解决|尚无定论|结论不一", md, re.I):
        say("FAIL", "writing", f"{len(unres)} 对冲突标 flagged_unresolved，但正文没有任何「未解决 / 结论不一」的表述")
    if not bad: say("PASS" if real else "WARN", "writing", f"tensions {len(rows)} 对，真冲突 {len(real)}（已在综合中处理 {len(real) - len(unres)}，标未解决 {len(unres)}）" + ("" if real else "：没有记录到任何真冲突——综述没有找到分歧通常是没去找"))

# ------------------------------------------------------------------ scope (S0)
AXES = {"method-level", "method", "task", "data", "time", "方法层级", "任务", "数据", "时间"}
NOT_A_THESIS = re.compile(r"^\s*(we (review|survey|summari[sz]e)|this (survey|review)|a (survey|review) of|an overview of|我们综述|本文综述|本综述|综述了)", re.I)

def check_scope(cfg, root, st):
    """G-S0: state.survey has the four scoping answers and the guide file is in place."""
    for k in ("scope_in", "scope_out", "axis", "thesis"):
        v = str(cfg.get(k) or "").strip()
        if len(v) < 8: say("FAIL", "scope", f"state.survey.{k} 为空或太短（{v!r}）：范围边界/组织轴/论点在 S0 就要写出来")
    axis = str(cfg.get("axis") or "").strip().lower()
    if axis and axis not in AXES: say("FAIL", "scope", f"state.survey.axis={axis!r} 不是 method-level | task | data | time 之一（只选一个主轴）")
    thesis = str(cfg.get("thesis") or "")
    if thesis and NOT_A_THESIS.match(thesis): say("FAIL", "scope", f"state.survey.thesis 是目录句不是论点：{thesis[:60]!r}（要一句可证伪的话，如\"报告的融合增益随基线匹配严格度缩小\"）")
    rt = str(cfg.get("review_type") or "narrative").strip().lower()
    if rt not in ("narrative", "scoping", "systematic"): say("FAIL", "scope", f"state.survey.review_type={rt!r} 不是 narrative | scoping | systematic")
    title = str((st.get("project") or {}).get("title") or "")
    if rt != "systematic" and re.search(r"systematic|系统综述|系统性综述", title + " " + thesis, re.I):
        say("FAIL", "scope", f"标题/论点自称 systematic，但 review_type={rt}：没有锁定协议、可复现检索、双人筛选与 PRISMA 清单就不能叫系统综述")
    gf = ((st.get("target") or {}).get("guide_file")) or "submission/guide.txt"
    if not os.path.exists(os.path.join(root, gf)): say("FAIL", "scope", f"{gf} 不存在（S0 同 P0：先下载 Guide for Authors）")
    if FAILS == 0: say("PASS", "scope", f"scope_in / scope_out / axis={axis} / thesis 四项齐，论点是可证伪句，guide 在")

# ------------------------------------------------------------------ search (S1)
ID_COLS = ("doi", "pmid", "arxiv_id", "openalex_id", "s2_id")

def _sources(log):
    """search_log.json: {"sources": [{source, query, date, count}, ...]} or {source: {query, date, count}}; keys may be Chinese."""
    if isinstance(log, dict) and isinstance(log.get("sources"), list): items = [(s.get("source") or s.get("name") or f"#{i}", s) for i, s in enumerate(log["sources"])]
    elif isinstance(log, list): items = [(s.get("source") or s.get("name") or f"#{i}", s) for i, s in enumerate(log)]
    elif isinstance(log, dict): items = [(k, v) for k, v in log.items() if isinstance(v, dict) and k not in ("dedup_total", "meta")]
    else: items = []
    norm = []
    for name, s in items:
        q = s.get("query") or s.get("检索式") or s.get("q") or ""
        d = s.get("date") or s.get("日期") or s.get("run_at") or ""
        n = s.get("count") if s.get("count") is not None else (s.get("n") if s.get("n") is not None else s.get("hits", s.get("命中数")))
        norm.append((str(name), str(q).strip(), str(d).strip(), n))
    return norm

def check_search(cfg, root):
    """G-S1: every source has a query, a date and a count; every candidate has an identifier; prior surveys each say how this one differs."""
    lp = os.path.join(root, cfg.get("search_log", "literature/search_log.json"))
    cp = os.path.join(root, cfg.get("candidates", "literature/candidates.csv"))
    if not os.path.exists(lp): say("FAIL", "search", f"{os.path.relpath(lp, root)} 不存在：每个检索源的检索式、日期、命中数要落盘，审稿人会问检索可否复现")
    else:
        try: srcs = _sources(json.load(open(lp, encoding="utf-8")))
        except Exception as ex: srcs = []; say("FAIL", "search", f"search_log.json 不可解析: {ex}")
        if not srcs: say("FAIL", "search", "search_log.json 没有任何检索源记录")
        bad = [(n, [k for k, v in (("query", q), ("date", d), ("count", c)) if v in ("", None)]) for n, q, d, c in srcs]
        bad = [(n, m) for n, m in bad if m]
        for n, m in bad: say("FAIL", "search", f"检索源 {n} 缺 {m}（检索式 / 日期 / 命中数三项都要）")
        nodate = [n for n, q, d, c in srcs if d and not re.match(r"\d{4}-\d{2}(-\d{2})?", d)]
        if nodate: say("WARN", "search", f"检索源 {nodate} 的日期不是 YYYY-MM-DD")
        if srcs and not bad: say("PASS", "search", f"{len(srcs)} 个检索源各有检索式、日期、命中数: " + ", ".join(f"{n}={c}" for n, q, d, c in srcs))
    if not os.path.exists(cp): say("FAIL", "search", f"{os.path.relpath(cp, root)} 不存在")
    else:
        rows = list(csv.DictReader(open(cp, encoding="utf-8-sig")))
        cols = set(rows[0].keys()) if rows else set()
        have_id = [c for c in ID_COLS if c in cols]
        if not rows: say("FAIL", "search", "candidates.csv 为空")
        elif not have_id: say("FAIL", "search", f"candidates.csv 没有标识符列（需 {ID_COLS} 之一）")
        else:
            noid = [i for i, r in enumerate(rows, 2) if not any((r.get(c) or "").strip() for c in have_id)]
            if noid: say("FAIL", "search", f"candidates.csv {len(noid)} 行无任何标识符（行 {noid[:6]}）：没有 DOI/PMID/arXiv 的候选无法去重与核实")
            else: say("PASS", "search", f"candidates.csv {len(rows)} 行全部有标识符")
            dois = [(r.get("doi") or "").strip().lower() for r in rows if (r.get("doi") or "").strip()]
            dup = len(dois) - len(set(dois))
            if dup: say("FAIL", "search", f"candidates.csv 有 {dup} 个重复 DOI：三源去重没做完")
    tp = os.path.join(root, cfg.get("prior_surveys", "literature/prior_surveys.csv"))
    if not os.path.exists(tp): say("FAIL", "search", f"{os.path.relpath(tp, root)} 不存在：S1 先查已有综述，每行写 how_this_differs")
    else:
        ps = list(csv.DictReader(open(tp, encoding="utf-8-sig")))
        nodiff = [p.get("title", "")[:40] for p in ps if not (p.get("how_this_differs") or "").strip()]
        if not ps: say("FAIL", "search", "prior_surveys.csv 为空：查过没有同主题综述也要写一行说明（title 填 none，how_this_differs 写检索式）")
        elif nodiff: say("FAIL", "search", f"prior_surveys.csv {len(nodiff)} 行未写本文差异: {nodiff[:3]}")
        else: say("PASS", "search", f"已有综述 {len(ps)} 篇，每篇写了本文差异")
    check_seeds(cfg, root, cp)
    if os.path.exists(lp): check_saturation(cfg, lp)

def _ntitle(t): return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()

def check_seeds(cfg, root, cand_p):
    """search validation: a gold set of studies that must be in scope (from the anchor papers' reference lists or prior surveys)
    has to be retrieved by the search. A seed missing after dedup is a search problem; a seed excluded later is a rule problem."""
    sp = os.path.join(root, cfg.get("seed_studies", "literature/seed_studies.csv"))
    if not os.path.exists(sp):
        say("WARN", "search", f"无 {os.path.relpath(sp, root)}：检索召回率不可算。从 2–5 篇锚点文献的参考文献表里取 ≥10 篇确定在范围内的研究作金标准"); return
    seeds = [r for r in csv.DictReader(open(sp, encoding="utf-8-sig")) if any((r.get(k) or "").strip() for k in ("doi", "pmid", "arxiv_id", "title"))]
    if not seeds: say("FAIL", "search", "seed_studies.csv 没有可匹配的行（doi / pmid / arxiv_id / title）"); return
    cands = list(csv.DictReader(open(cand_p, encoding="utf-8-sig"))) if os.path.exists(cand_p) else []
    have = {(k, (r.get(k) or "").strip().lower()) for r in cands for k in ("doi", "pmid", "arxiv_id") if (r.get(k) or "").strip()}
    titles = {_ntitle(r.get("title")) for r in cands if (r.get("title") or "").strip()}
    miss = [s for s in seeds if not any((k, (s.get(k) or "").strip().lower()) in have for k in ("doi", "pmid", "arxiv_id") if (s.get(k) or "").strip()) and _ntitle(s.get("title")) not in titles]
    rec = 1 - len(miss) / len(seeds); need = float(cfg.get("min_seed_recall", 1.0))
    lab = lambda s: (s.get("doi") or s.get("title") or s.get("pmid") or "")[:50]
    say("FAIL" if rec < need else "PASS", "search", f"种子召回 {len(seeds) - len(miss)}/{len(seeds)} = {rec:.2f}（要求 ≥ {need:.2f}）" + (f"；漏检 {[lab(s) for s in miss[:4]]}：逐条归因（缺同义词 / 主题词错 / 限定过窄），改检索式并在 search_log 记新版本" if miss else ""))

def check_saturation(cfg, lp):
    """stopping rule: snowball until the last N rounds add no new eligible study. Rounds are search_log entries whose source names
    snowball/citation, in log order, each with new_included (eligible studies first found in that round)."""
    try: log = json.load(open(lp, encoding="utf-8"))
    except Exception: return
    items = log.get("sources") if isinstance(log, dict) and isinstance(log.get("sources"), list) else (log if isinstance(log, list) else [])
    rounds = [s for s in items if isinstance(s, dict) and re.search(r"snowball|citation|chain", str(s.get("source") or s.get("name") or ""), re.I)]
    if not rounds: say("WARN", "search", "search_log 没有滚雪球轮次：停止规则无从判断（每轮记 new_included）"); return
    n = int(cfg.get("saturation_rounds", 2)); ni = [s.get("new_included") for s in rounds]
    if any(v is None for v in ni): say("WARN", "search", f"{sum(v is None for v in ni)}/{len(rounds)} 个滚雪球轮次没记 new_included（该轮首次发现的合格研究数），饱和不可判"); return
    tail = ni[-n:]
    ok = len(tail) == n and all(int(v) == 0 for v in tail)
    say("PASS" if ok else "WARN", "search", f"滚雪球 {len(rounds)} 轮，各轮新增合格 {ni}" + ("：最后 %d 轮无新增，已饱和" % n if ok else f"：最后 {n} 轮仍有新增或不足 {n} 轮，继续滚或在局限节写明停止理由"))

# ------------------------------------------------------------------ tables (S4)
def check_tables(cfg, root):
    """G-S4: every summary table is re-derivable (generator --verify passes), coverage cells sum to the included count, figures registered."""
    import subprocess
    td = os.path.join(root, cfg.get("tables_dir", "tables"))
    csvs = sorted(f for f in os.listdir(td) if f.endswith(".csv")) if os.path.isdir(td) else []
    if not csvs: say("FAIL", "tables", f"{os.path.relpath(td, root)}/ 没有 csv：汇总表必须落盘（正文数字要指向它的行）")
    gens = sorted(f for f in os.listdir(os.path.join(root, "coding")) if f.endswith(".py") and "summary" in f) if os.path.isdir(os.path.join(root, "coding")) else []
    spec = os.path.join(root, cfg.get("tables_spec", "coding/tables.yaml"))
    if os.path.exists(spec):
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "survey_tables.py"), "summary", "--verify", "--project", root, "--spec", os.path.relpath(spec, root)],
                           cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        for l in (r.stdout or "").splitlines():
            if l.startswith("[FAIL]"): say("FAIL", "tables", l.split(":", 1)[1].strip())
        if r.returncode == 0: say("PASS", "tables", f"{os.path.relpath(spec, root)} 定义的表全部可从 coded.csv 逐格重算")
        elif "Traceback" in (r.stderr or ""): say("FAIL", "tables", "survey_tables.py summary --verify 崩溃: " + r.stderr.strip().splitlines()[-1][:120])
    elif not gens: say("FAIL", "tables", "coding/ 无 *summary*.py 生成脚本，也无 coding/tables.yaml：tables/*.csv 必须能从 coded.csv 重算（survey_tables.py summary）")
    for g in gens:
        r = subprocess.run([sys.executable, os.path.join("coding", g), "--verify"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or "Traceback" in (r.stderr or ""):
            say("FAIL", "tables", f"coding/{g} --verify 退出码 {r.returncode}：汇总表与 coded.csv 不一致或脚本不可运行 | " + ((r.stdout + r.stderr).strip().splitlines() or ["(无输出)"])[-1][:120])
        else: say("PASS", "tables", f"coding/{g} --verify 通过：{len(csvs)} 张表可从 coded.csv 重算")
    # included count: PRISMA first, screening sheet second
    inc = None
    pp = os.path.join(root, cfg.get("prisma", "literature/prisma_flow.json"))
    if os.path.exists(pp):
        try: inc = int(json.load(open(pp, encoding="utf-8")).get("included"))
        except Exception: inc = None
    if inc is None:
        sp = os.path.join(root, cfg.get("screening_sheet", "coding/screening_sheet.csv"))
        if os.path.exists(sp): inc = sum(1 for r in csv.DictReader(open(sp, encoding="utf-8-sig")) if (r.get("decision") or "").strip().lower() == "include")
    cv = os.path.join(root, cfg.get("coverage", "coding/coverage.csv"))
    if not os.path.exists(cv): say("FAIL", "tables", f"{os.path.relpath(cv, root)} 不存在：覆盖矩阵（轴 × 任务/数据的篇数）找空白格，也是路线图节的依据")
    else:
        rows = [r for r in csv.reader(open(cv, encoding="utf-8-sig")) if any(c.strip() for c in r)]
        hdr, body = rows[0], rows[1:]
        cells = []
        for r in body:
            if r[0].strip().lower() in ("total", "合计", "sum"): continue
            for j, c in enumerate(r[1:], 1):
                if j < len(hdr) and hdr[j].strip().lower() in ("total", "合计", "sum"): continue
                try: cells.append(int(float(c)))
                except Exception: pass
        tot = sum(cells)
        if inc is None: say("WARN", "tables", f"coverage.csv 格子合计 {tot}，但找不到纳入篇数（prisma_flow.json 的 included 或 screening 的 include 行）来核对")
        elif tot != inc: say("FAIL", "tables", f"coverage.csv 格子合计 {tot} ≠ 纳入篇数 {inc}：每篇纳入文献在矩阵里应恰好计一次")
        else: say("PASS", "tables", f"coverage.csv {len(body)} 行 × {len(hdr)-1} 列，格子合计 = 纳入篇数 {inc}；空白格 {sum(1 for c in cells if c == 0)} 个")
    fp = os.path.join(root, cfg.get("figures", "figures.csv"))
    nfig = max(len([l for l in open(fp, encoding="utf-8-sig").read().splitlines() if l.strip()]) - 1, 0) if os.path.exists(fp) else 0
    say("PASS" if nfig else "WARN", "tables", f"figures.csv {nfig} 张图" + ("" if nfig else "（survey_figure.py prisma / timeline / coverage 还没跑；S4 末至少一张）"))
    check_skew(cfg, root)

def check_skew(cfg, root):
    """advisory only: when one value holds ≥ 70 % of the known values of a dimension, the corpus (not the field) may be skewed —
    the discussion has to say whether that is the field or the search."""
    dims = cfg.get("skew_dims") or []
    cp = os.path.join(root, cfg.get("coded", "coding/coded.csv"))
    if not dims or not os.path.exists(cp): return
    rows = list(csv.DictReader(open(cp, encoding="utf-8-sig")))
    for d in dims:
        vals = [v.strip() for r in rows for v in (r.get(d) or "").split("|") if v.strip() and v.strip() != "?"]
        if not vals: say("WARN", "tables", f"skew_dims 列 {d} 无已知值"); continue
        top, n = collections.Counter(vals).most_common(1)[0]
        if n / len(vals) >= 0.7: say("WARN", "tables", f"分布偏斜：{d}={top} 占已知值 {n}/{len(vals)} = {n / len(vals):.0%}（≥70%）——讨论节说明这是领域本身还是检索造成的")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("protocol"); p.add_argument("--protocol", default="protocol.md"); p.add_argument("--codebook", default="coding/codebook.md"); p.add_argument("--state", default="research-state.yaml")
    for n in ("scope", "search", "coding", "tables", "claims", "writing"):
        q = sub.add_parser(n); q.add_argument("--state", default="research-state.yaml"); q.add_argument("--project", default=".")
    a = ap.parse_args()
    if a.cmd == "protocol": check_protocol(a.protocol, a.codebook, a.state)
    else:
        root = os.path.abspath(a.project); st = load_state(os.path.join(root, a.state)); cfg = st.get("survey") or {}
        if a.cmd == "scope": check_scope(cfg, root, st)
        else: {"search": check_search, "coding": check_coding, "tables": check_tables, "claims": check_claims, "writing": check_writing}[a.cmd](cfg, root)
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)
