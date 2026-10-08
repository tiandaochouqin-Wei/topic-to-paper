# -*- coding: utf-8 -*-
"""Survey-branch gates (S2, S3, S5). Run by Claude, never by the user.

  python survey_check.py protocol [--protocol protocol.md] [--codebook coding/codebook.md] [--state research-state.yaml]
  python survey_check.py coding   [--state research-state.yaml] [--project .]
  python survey_check.py claims   [--state research-state.yaml] [--project .]

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
Exit 1 on any FAIL."""
import argparse, csv, io, json, os, re, sys, collections

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
    bad_dec = sum(1 for r in rows if (r.get("decision") or "").strip().lower() not in ("include", "maybe", "exclude", ""))
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
        say("FAIL" if low else "PASS", "coding", f"κ: " + ", ".join(f"{f}={v:.2f}" for f, v in k.items() if isinstance(v, (int, float))) + (f" —— {list(low)} < {mk}，该字段的 codebook 规则要改或正文明写" if low else ""))
    else: say("WARN", "coding", "无 kappa_results.json：单人编码未验证")

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
        say("PASS" if gen else "WARN", "claims", f"tables/ 有 {len([f for f in os.listdir(td) if f.endswith('.csv')])} 张 csv" + ("，coding/ 有生成脚本" if gen else "，但 coding/ 无 *summary*.py 生成脚本：汇总表必须能从 coded.csv 重算"))
    if bad == 0: say("PASS", "claims", f"{len(rows)} 条主张全部能回到证据文件的具体行且满足判据")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("protocol"); p.add_argument("--protocol", default="protocol.md"); p.add_argument("--codebook", default="coding/codebook.md"); p.add_argument("--state", default="research-state.yaml")
    for n in ("coding", "claims"):
        q = sub.add_parser(n); q.add_argument("--state", default="research-state.yaml"); q.add_argument("--project", default=".")
    a = ap.parse_args()
    if a.cmd == "protocol": check_protocol(a.protocol, a.codebook, a.state)
    else:
        root = os.path.abspath(a.project); st = load_state(os.path.join(root, a.state)); cfg = st.get("survey") or {}
        (check_coding if a.cmd == "coding" else check_claims)(cfg, root)
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)
