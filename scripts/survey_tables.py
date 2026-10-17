# -*- coding: utf-8 -*-
"""S4 — survey tables computed from coding/coded.csv, so no project has to hand-write its own audit_summary.py. Run by Claude.

  python survey_tables.py summary  [--project .] [--spec coding/tables.yaml] [--verify]
      every table in the spec -> tables/<name>.csv; --verify re-derives each one and compares cell by cell (G-S4 runs this)
  python survey_tables.py crosstab --rows <col> --cols <col> [--out coding/coverage.csv] [--project .]
      coverage matrix (row value × column value → number of included studies); single-valued columns only, so that every
      study is counted exactly once (the G-S4 rule); zero cells are the gaps the roadmap section has to address
  python survey_tables.py kappa    --a coding/coded.csv --b coding/coded_second.csv --fields pair,level,M [--key doi]
                                   [--out coding/kappa_results.json] [--project .]
      Cohen's κ, raw agreement and PABAK per field between two independent coders (or two screeners: --fields decision);
      multi-valued fields compare as sets. Writes {field: κ, ..., "_detail": {field: {n, agree, kappa, pabak, categories}}}
  python survey_tables.py characteristics --cols year,task,metric,n_test [--cite-col bibkey] [--sort year]
                                   [--out tables/characteristics.tex] [--project .]
      one row per included study (the "characteristics of included studies" table), as LaTeX longtable + .md twin
  python survey_tables.py prior    [--cols year,venue,n_studies] [--covers-prefix covers_] [--out tables/prior_surveys.tex]
      the "adjacent surveys and how this one differs" table from literature/prior_surveys.csv; covers_* columns → ✓ / –,
      and a last row for this survey (values from state.survey.this_survey, or "this work"). The tick mark needs amssymb; the long table needs the longtable package.

  python survey_tables.py qc-sample [--n 100] [--seed 20261018] [--near-miss "fusion|multimodal;baseline|unimodal"]
      blind re-screen sample of excluded records: every exclude matching >=1 term of each keyword group (near miss) plus a
      seeded random sample of the rest -> coding/qc_exclusion_sample.csv WITHOUT the first decision; fill qc_decision/qc_reason
      near-miss rows are capped at --max-near-miss (default = --n, sampled by seed) so the blind re-screen stays doable

Spec (coding/tables.yaml):
  tables:
    summary:                         # -> tables/summary.csv
      group_by: M                    # one row per value of this column (omit for a single "all" row)
      groups: ["1", "3"]             # optional: subset and order of group values
      label: "M{}"                   # optional: how the group value is written in the first column
      all: true                      # append a row over every study
      where: "L=0"                   # optional filter, col=val[|val] joined by ";" (all must hold)
      stats:                         # column -> statistic, evaluated per group
        n: count
        median_delta: median(delta_rep)
        share_delta_ci: share(delta_ci=yes)
      digits: 3
  Statistics: count | count(c) (studies with a known value) | median(c) | mean(c) | q1(c) | q3(c) | iqr(c) | min(c) | max(c) | sum(c) | count(c=v[|v]) | share(c=v[|v])
  Numeric statistics skip empty and "?" cells and report n_used in the source line; share() divides by the group size.
"""
import argparse, csv, io, json, os, re, statistics, sys, collections
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] tables: {msg}")

def rows_of(p):
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))

def load_state(root):
    p = os.path.join(root, "research-state.yaml")
    if not os.path.exists(p): return {}
    import yaml
    return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}

def codebook_joined(root, cfg):
    """columns the codebook marks as multi-valued (`|`-joined); crosstab and timeline refuse them."""
    p = os.path.join(root, cfg.get("codebook", "coding/codebook.md"))
    if not os.path.exists(p): return set()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import survey_check
    return {c for c, (_, j) in (survey_check.parse_codebook(p) or {}).items() if j}

# ------------------------------------------------------------------ summary
STAT = re.compile(r"^\s*(count|median|mean|q1|q3|iqr|min|max|sum|share)\s*(?:\(\s*([^)=]+?)\s*(?:=\s*([^)]*))?\))?\s*$", re.I)

def _num(v):
    v = (v or "").strip()
    if v in ("", "?"): return None
    try: return float(v)
    except ValueError: return None

def _match(r, col, vals):
    have = {x.strip() for x in (r.get(col) or "").split("|")}
    return bool(have & {v.strip() for v in vals.split("|")})

def _where(rows, expr):
    for cond in [c for c in (expr or "").split(";") if c.strip()]:
        col, vals = cond.split("=", 1); rows = [r for r in rows if _match(r, col.strip(), vals)]
    return rows

def stat(expr, sel, digits):
    m = STAT.match(str(expr))
    if not m: raise ValueError(f"无法解析的统计量 {expr!r}（count | median(c) | share(c=v) …）")
    fn, col, val = m.group(1).lower(), m.group(2), m.group(3)
    if fn == "count" and not col: return str(len(sel))
    if fn == "count" and col and val is None: return str(sum(1 for r in sel if (r.get(col) or "").strip() not in ("", "?")))   # studies with a known value
    if fn in ("count", "share"):
        if not col or val is None: raise ValueError(f"{expr!r}: {fn} 需要 列=值（count(列) 数该列有已知值的篇数）")
        k = sum(1 for r in sel if _match(r, col, val))
        return str(k) if fn == "count" else (f"{k / len(sel):.{digits}f}" if sel else "")
    xs = [x for x in (_num(r.get(col)) for r in sel) if x is not None]
    if not xs: return ""
    if fn == "median": x = statistics.median(xs)
    elif fn == "mean": x = statistics.fmean(xs)
    elif fn == "min": x = min(xs)
    elif fn == "max": x = max(xs)
    elif fn == "sum": x = sum(xs)
    else:
        q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) > 1 else [xs[0]] * 3
        x = {"q1": q[0], "q3": q[2], "iqr": q[2] - q[0]}[fn]
    return f"{x:.{digits}f}"

def derive(spec, coded):
    gb = spec.get("group_by"); digits = int(spec.get("digits", 3)); label = spec.get("label", "{}")
    base = _where(coded, spec.get("where"))
    groups = []
    if gb:
        vals = [str(v) for v in spec["groups"]] if spec.get("groups") else sorted({(r.get(gb) or "").strip() for r in base} - {"", "?"}, key=lambda s: (_num(s) is None, _num(s) or 0, s))
        groups = [(label.format(v), [r for r in base if (r.get(gb) or "").strip() == v]) for v in vals]
        if not spec.get("groups"):          # unknown / empty values get their own row, otherwise the group rows silently stop adding up to "all"
            unk = [r for r in base if (r.get(gb) or "").strip() in ("", "?")]
            if unk: groups.append((label.format("?"), unk))
    if spec.get("all", not gb): groups.append(("all", base))
    first = spec.get("group_col", "group")
    out = []
    for name, sel in groups:
        row = {first: name}
        for col, expr in (spec.get("stats") or {"n": "count"}).items(): row[col] = stat(expr, sel, digits)
        out.append(row)
    return out

def cmd_summary(a):
    root = os.path.abspath(a.project); st = load_state(root); cfg = st.get("survey") or {}
    sp = os.path.join(root, a.spec or cfg.get("tables_spec", "coding/tables.yaml"))
    if not os.path.exists(sp): say("FAIL", f"{os.path.relpath(sp, root)} 不存在（汇总表的定义：哪一列分组、每列算什么）"); return
    import yaml
    spec = yaml.safe_load(io.open(sp, encoding="utf-8").read()) or {}
    coded = rows_of(os.path.join(root, cfg.get("coded", "coding/coded.csv")))
    td = os.path.join(root, cfg.get("tables_dir", "tables")); os.makedirs(td, exist_ok=True)
    for name, t in (spec.get("tables") or {}).items():
        try: fresh = derive(t, coded)
        except (ValueError, KeyError) as ex: say("FAIL", f"{name}: {ex}"); continue
        out = os.path.join(td, name + ".csv"); hdr = list(fresh[0].keys()) if fresh else []
        if a.verify:
            if not os.path.exists(out): say("FAIL", f"{os.path.relpath(out, root)} 不存在：先跑 summary（不带 --verify）"); continue
            have = rows_of(out); diff = []
            if len(have) != len(fresh): diff.append(f"行数 {len(have)} ≠ 重算 {len(fresh)}")
            for i, (h, f) in enumerate(zip(have, fresh)):
                for k in hdr:
                    if (h.get(k) or "") != f[k]: diff.append(f"行 {i + 2} {k}: 表里 {h.get(k)!r} 重算 {f[k]!r}")
            if diff: say("FAIL", f"{name}.csv 与 coded.csv 重算不一致（{len(diff)} 处）: {diff[:4]} —— coded.csv 改过就重跑 summary，不要手改表")
            else: say("PASS", f"{name}.csv {len(have)} 行可从 coded.csv 逐格重算")
        else:
            with io.open(out, "w", encoding="utf-8", newline="") as f: w = csv.DictWriter(f, fieldnames=hdr); w.writeheader(); w.writerows(fresh)
            say("INFO", f"{name}: {len(fresh)} 行 -> {os.path.relpath(out, root)}")

# ------------------------------------------------------------------ crosstab
def cmd_crosstab(a):
    root = os.path.abspath(a.project); cfg = load_state(root).get("survey") or {}
    coded = rows_of(os.path.join(root, cfg.get("coded", "coding/coded.csv")))
    joined = codebook_joined(root, cfg) & {a.rows, a.cols}
    multi = [c for c in (a.rows, a.cols) if any("|" in (r.get(c) or "") for r in coded)]
    if joined or multi:
        say("FAIL", f"{sorted(set(joined) | set(multi))} 是多值列：一篇文献会被计多次，覆盖矩阵合计就不等于纳入篇数。改用单值的主值列（如 primary_pair）"); return
    rv = sorted({(r.get(a.rows) or "?").strip() or "?" for r in coded}); cv = sorted({(r.get(a.cols) or "?").strip() or "?" for r in coded})
    if a.row_order: rv = [v for v in a.row_order.split(",")] + [v for v in rv if v not in a.row_order.split(",")]
    if a.col_order: cv = [v for v in a.col_order.split(",")] + [v for v in cv if v not in a.col_order.split(",")]
    cnt = collections.Counter(((r.get(a.rows) or "?").strip() or "?", (r.get(a.cols) or "?").strip() or "?") for r in coded)
    out = os.path.join(root, a.out); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow([a.rows] + cv)
        for x in rv: w.writerow([x] + [cnt[(x, y)] for y in cv])
    gaps = [(x, y) for x in rv for y in cv if cnt[(x, y)] == 0]
    say("INFO", f"{len(rv)} × {len(cv)} 覆盖矩阵 -> {os.path.relpath(out, root)}；合计 {sum(cnt.values())} = coded 行数 {len(coded)}；空白格 {len(gaps)}: {gaps[:8]}")

# ------------------------------------------------------------------ kappa
def _cohen(pairs):
    """pairs [(a, b)] -> (po, pe, kappa or None, pabak, k)"""
    n = len(pairs); cats = sorted({x for p in pairs for x in p}); k = max(len(cats), 2)
    po = sum(1 for x, y in pairs if x == y) / n
    ca = collections.Counter(x for x, _ in pairs); cb = collections.Counter(y for _, y in pairs)
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    kappa = None if pe >= 1 else (po - pe) / (1 - pe)
    return po, pe, kappa, (k * po - 1) / (k - 1), cats

def cmd_kappa(a):
    root = os.path.abspath(a.project); cfg = load_state(root).get("survey") or {}
    A = rows_of(os.path.join(root, a.a)); B = rows_of(os.path.join(root, a.b))
    key = a.key
    ka = {(r.get(key) or "").strip().lower(): r for r in A if (r.get(key) or "").strip()}
    kb = {(r.get(key) or "").strip().lower(): r for r in B if (r.get(key) or "").strip()}
    both = sorted(set(ka) & set(kb))
    if not both: say("FAIL", f"两份编码按 {key} 没有共同的文献"); return
    if len(both) < len(kb): say("WARN", f"第二编码员的 {len(kb) - len(both)} 篇不在第一份里（按 {key} 对不上），未计入")
    joined = codebook_joined(root, cfg)
    res, detail = {}, {}
    for fld in [f.strip() for f in a.fields.split(",") if f.strip()]:
        def val(r):
            v = (r.get(fld) or "").strip()
            return "|".join(sorted(x.strip() for x in v.split("|") if x.strip())) if (fld in joined or "|" in v) else v
        pairs = [(val(ka[i]), val(kb[i])) for i in both if fld in ka[i] and fld in kb[i]]
        pairs = [p for p in pairs if p[0] not in ("", "?") and p[1] not in ("", "?")]
        if len(pairs) < 2: say("WARN", f"{fld}: 可比的文献不足 2 篇"); continue
        po, pe, kap, pabak, cats = _cohen(pairs)
        res[fld] = round(kap, 3) if kap is not None else round(pabak, 3)
        detail[fld] = {"n": len(pairs), "agree": round(po, 3), "expected": round(pe, 3), "kappa": None if kap is None else round(kap, 3), "pabak": round(pabak, 3), "categories": len(cats)}
        dis = collections.Counter(p for p in pairs if p[0] != p[1]).most_common(3)
        say("INFO", f"{fld}: n={len(pairs)} 一致率 {po:.2f} κ={'—' if kap is None else f'{kap:.2f}'} PABAK={pabak:.2f}" + (f"；最常见分歧 {dis}" if dis else ""))
    res["_detail"] = detail
    out = os.path.join(root, a.out); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(res, io.open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    say("INFO", f"-> {os.path.relpath(out, root)}（G-S3 读数值项；κ 低但 PABAK ≥ 0.8 的字段是患病率悖论，降 WARN，正文两个都报）")

# ------------------------------------------------------------------ LaTeX tables
TEX_ESC = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}"}
def tex(s): return "".join(TEX_ESC.get(c, c) for c in str(s))

def write_table(out, hdr, body, caption, label, longtable=False, wide_last=False):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    spec = "l" * (len(hdr) - 1) + (r"p{0.42\linewidth}" if wide_last else "l")   # free-text last column wraps instead of running off the page
    head = " & ".join(rf"\textbf{{{tex(h)}}}" for h in hdr) + r" \\"
    lines = [" & ".join(c if c.startswith("\\") else tex(c) for c in r) + r" \\" for r in body]
    if longtable:
        t = [rf"\begin{{longtable}}{{{spec}}}", rf"\caption{{{caption}}}\label{{{label}}}\\", r"\hline", head, r"\hline", r"\endfirsthead",
             r"\hline", head, r"\hline", r"\endhead", *lines, r"\hline", r"\end{longtable}"]
    else:
        t = [r"\begin{table}[t]", r"\centering", rf"\caption{{{caption}}}\label{{{label}}}", r"\small", rf"\begin{{tabular}}{{{spec}}}", r"\hline", head, r"\hline", *lines, r"\hline", r"\end{tabular}", r"\end{table}"]
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(t) + "\n")
    md = os.path.splitext(out)[0] + ".md"
    plain = lambda c: re.sub(r"\\cite\{([^}]*)\}", r"[@\1]", c).replace(r"\checkmark", "✓")
    io.open(md, "w", encoding="utf-8", newline="\n").write("| " + " | ".join(hdr) + " |\n|" + "---|" * len(hdr) + "\n" + "".join("| " + " | ".join(plain(c) for c in r) + " |\n" for r in body))
    return md

def cmd_characteristics(a):
    root = os.path.abspath(a.project); cfg = load_state(root).get("survey") or {}
    coded = rows_of(os.path.join(root, cfg.get("coded", "coding/coded.csv")))
    cols = [c.strip() for c in a.cols.split(",") if c.strip()]
    miss = [c for c in cols if coded and c not in coded[0]]
    if miss: say("FAIL", f"coded.csv 没有列 {miss}"); return
    if a.cite_col and coded and a.cite_col not in coded[0]:
        say("WARN", f"coded.csv 没有 {a.cite_col} 列：Study 列写标识符；要引用就给 coded.csv 加 {a.cite_col} 列（.bib 的键）"); a.cite_col = ""
    if a.sort: coded.sort(key=lambda r: (_num(r.get(a.sort)) is None, _num(r.get(a.sort)) or 0, r.get(a.sort) or ""))
    hdr = ["Study"] + cols
    ident = lambda r: (r.get("doi") or r.get("pmid") or r.get("arxiv_id") or "?").strip()
    body = [[(rf"\cite{{{r[a.cite_col].strip()}}}" if a.cite_col and (r.get(a.cite_col) or "").strip() else ident(r))] + [(r.get(c) or "").replace("|", ", ") for c in cols] for r in coded]
    nocite = sum(1 for r in coded if a.cite_col and not (r.get(a.cite_col) or "").strip())
    md = write_table(os.path.join(root, a.out), hdr, body, a.caption or "Characteristics of the included studies.", a.label, longtable=True)
    say("WARN" if nocite else "INFO", f"{len(body)} 篇 -> {a.out} + {os.path.relpath(md, root)}" + (f"；{nocite} 篇无 {a.cite_col}（写了标识符代替，正文要能引到）" if nocite else ""))

def cmd_prior(a):
    root = os.path.abspath(a.project); st = load_state(root); cfg = st.get("survey") or {}
    ps = rows_of(os.path.join(root, cfg.get("prior_surveys", "literature/prior_surveys.csv")))
    if not ps: say("FAIL", "prior_surveys.csv 为空"); return
    covers = [c for c in ps[0] if c.startswith(a.covers_prefix)]
    cols = [c.strip() for c in a.cols.split(",") if c.strip() and c.strip() in ps[0]]
    hdr = ["Survey"] + cols + [c[len(a.covers_prefix):].replace("_", " ") for c in covers] + (["How this survey differs"] if not covers else [])
    mark = lambda v: r"\checkmark" if (v or "").strip().lower() in ("y", "yes", "1", "true", "✓") else "–"
    cite = lambda r: rf"\cite{{{r['bibkey'].strip()}}}" if (r.get("bibkey") or "").strip() else (r.get("title") or "").strip()
    body = [[cite(r)] + [r.get(c) or "" for c in cols] + [mark(r.get(c)) for c in covers] + ([r.get("how_this_differs") or ""] if not covers else []) for r in ps]
    if covers:
        mine = (cfg.get("this_survey") or {})
        body.append(["This survey"] + [str(mine.get(c, "")) for c in cols] + [mark(mine.get(c, "yes")) for c in covers])
        uniq = [c for c in covers if all(mark(r.get(c)) == "–" for r in ps)]
        say("INFO", f"本文独有的覆盖维度: {[c[len(a.covers_prefix):] for c in uniq] or '无 —— 差异只能靠深度/方法，正文要说清'}")
    md = write_table(os.path.join(root, a.out), hdr, body, a.caption or "Comparison with existing surveys on the topic.", a.label, wide_last=not covers)
    say("INFO", f"{len(ps)} 篇已有综述 -> {a.out} + {os.path.relpath(md, root)}")

# ------------------------------------------------------------------ QC sample of exclusions
def cmd_qc_sample(a):
    """random + near-miss sample of excluded records for a blind second look. The output deliberately omits the first decision
    and its reason; survey_check.py coding joins it back to screening_sheet.csv by identifier."""
    import random
    root = os.path.abspath(a.project); cfg = load_state(root).get("survey") or {}
    sp = os.path.join(root, cfg.get("screening_sheet", "coding/screening_sheet.csv"))
    rows = rows_of(sp); idc = [c for c in ("doi", "pmid", "arxiv_id", "openalex_id") if rows and c in rows[0]]
    excl = [r for r in rows if (r.get("decision") or "").strip().lower() == "exclude" and any((r.get(c) or "").strip() for c in idc)]
    if not excl: say("FAIL", "screening_sheet 没有带标识符的 exclude 行"); return
    text = lambda r: " ".join((r.get(c) or "") for c in ("title", "abstract")).lower()
    groups = [[p.strip().lower() for p in g.split("|") if p.strip()] for g in a.near_miss.split(";") if g.strip()]
    near_all = [r for r in excl if groups and all(any(p in text(r) for p in g) for g in groups)]
    rng = random.Random(a.seed); cap = a.max_near_miss or a.n
    near = near_all if len(near_all) <= cap else rng.sample(near_all, cap)     # a near-miss set of 1 000+ rows will never be re-screened blind
    if len(near_all) > cap: say("WARN", f"near-miss 命中 {len(near_all)} 篇 > 上限 {cap}：按 seed 抽 {cap} 篇（--max-near-miss 调上限；关键词组太宽时先收窄）")
    taken = {id(r) for r in near_all}; pool = [r for r in excl if id(r) not in taken]
    rand = rng.sample(pool, min(a.n, len(pool)))
    out = os.path.join(root, cfg.get("qc_sample", a.out)); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    cols = idc + ["title", "abstract", "sample_type", "qc_decision", "qc_reason"]
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for t, sel in (("near_miss", near), ("random", rand)):
            for r in sel: w.writerow({**{c: r.get(c, "") for c in idc + ["title", "abstract"]}, "sample_type": t, "qc_decision": "", "qc_reason": ""})
    say("INFO", f"排除 {len(excl)} 篇中抽 near_miss {len(near)}（命中 {len(near_all)}）+ random {len(rand)}（seed {a.seed}）-> {os.path.relpath(out, root)}；"
                "复核时只看标题/摘要与协议，不看原决定，逐行填 qc_decision ∈ include | exclude 与 qc_reason")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    qs = sub.add_parser("qc-sample"); qs.add_argument("--n", type=int, default=100); qs.add_argument("--seed", type=int, default=20261018)
    qs.add_argument("--near-miss", default="", help='keyword groups "a|b;c|d": an exclude matching >=1 term of EVERY group is a near miss (one group per core criterion)')
    qs.add_argument("--max-near-miss", type=int, default=0, help="cap on near-miss rows (0 = same as --n)")
    qs.add_argument("--out", default="coding/qc_exclusion_sample.csv"); qs.add_argument("--project", default=".")
    s = sub.add_parser("summary"); s.add_argument("--spec", default=""); s.add_argument("--verify", action="store_true")
    c = sub.add_parser("crosstab"); c.add_argument("--rows", required=True); c.add_argument("--cols", required=True); c.add_argument("--out", default="coding/coverage.csv")
    c.add_argument("--row-order", default=""); c.add_argument("--col-order", default="")
    k = sub.add_parser("kappa"); k.add_argument("--a", default="coding/coded.csv"); k.add_argument("--b", required=True); k.add_argument("--fields", required=True)
    k.add_argument("--key", default="doi"); k.add_argument("--out", default="coding/kappa_results.json")
    h = sub.add_parser("characteristics"); h.add_argument("--cols", required=True); h.add_argument("--cite-col", default="bibkey"); h.add_argument("--sort", default="year")
    h.add_argument("--out", default="tables/characteristics.tex"); h.add_argument("--caption", default=""); h.add_argument("--label", default="tab:characteristics")
    p = sub.add_parser("prior"); p.add_argument("--cols", default="year,venue"); p.add_argument("--covers-prefix", default="covers_")
    p.add_argument("--out", default="tables/prior_surveys.tex"); p.add_argument("--caption", default=""); p.add_argument("--label", default="tab:prior")
    for q in (s, c, k, h, p): q.add_argument("--project", default=".")
    a = ap.parse_args()
    {"summary": cmd_summary, "crosstab": cmd_crosstab, "kappa": cmd_kappa, "characteristics": cmd_characteristics, "prior": cmd_prior, "qc-sample": cmd_qc_sample}[a.cmd](a)
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
