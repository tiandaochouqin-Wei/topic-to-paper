# -*- coding: utf-8 -*-
"""P5 — decide WHAT to draw: learn the figure set from same-topic high-quality papers, then plan it claim by claim. Run by Claude.

  python figure_plan.py exemplars --project . [--query "..."] [--k 8] [--min-year 2023] [--venues CVPR,ICCV,...] [--papers Z:/LDCT/papers]
                                  [--index literature/lit_index.sqlite] [--pdf extra.pdf ...] [--net] [--from-dir <replay>]
  python figure_plan.py plan      --project . [--force]
  python figure_plan.py check     --project .                       (G5 of t2p.py runs it; exit = #FAIL)

exemplars: BM25 over the local corpus (lit_scout.py index, built when missing) with the query = project topic + prereg §1 sentence + claim statements,
        reduced to content terms. Venue filter = target venue + the top list of the family (cs_conf CVPR ICCV ECCV NeurIPS ICML ICLR; cs_journal TPAMI IJCV
        TIP TMI MedIA InfoFusion TMM TKDE; nature = Nature family), year >= --min-year, a readable local PDF (local_path, else <--papers>/<venue>/<year>/<basename>).
        --net adds the quality half: citations (index cited_by when present, else OpenAlex by title; --from-dir <dir>/openalex_cited.json replays {title: count})
        of the top 3k candidates, keep >= the median of the same venue-year (papers of the current year are exempt, marked fresh). Final pick: top --k by BM25,
        at most 3 per venue. --pdf papers are always included (source=user) and do not count against --k.
        Per exemplar (PyMuPDF): every figure caption -> number, page, types (figure_norms rules), panels, width single|double (the image/drawing cluster just above
        the caption vs the page text width, > 0.6 = double), role motivation|method|main_result|ablation|qualitative|analysis; table captions -> main_result|ablation|
        efficiency|other; a 110 dpi thumbnail per figure (open them with the Read tool). Writes literature/exemplars/{exemplars.csv,exemplar_figures.csv,exemplars.md,thumbs/}.
plan:   paper/figure_plan.csv + .md from paper/claims.csv, prereg §0, the exemplars and figures.csv. Claim first: a figure enters the plan through a claim, the
        prereg §0 phenomenon or the method overview. A role the exemplars have but no claim supports is reported (INFO), not planned. Per row: figure vs table
        (>= 3 methods x >= 2 metrics or >= 2 datasets of exact numbers -> table; trend / trade-off / per-item gains -> figure), generator command, the best-matching
        exemplar figure of the same role ("modelled on <paper> Fig N"). `files` = figures.csv paths (extension dropped; `x_a`, `x_b` panels are covered by `x`) that
        carry the row: check matches figures.csv by it (or by an optional figures.csv column plan_item). The plan is a draft you edit; --force overwrites it.
check:  no plan WARN; < 3 exemplars WARN; planned figure not in figures.csv FAIL; dropped without note FAIL; figures.csv figure no row covers WARN;
        numeric claim no row carries WARN; claim_ids naming a claim that no longer exists FAIL."""
import argparse, collections, csv, datetime, io, json, os, re, statistics, sys, urllib.parse
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import lit_scout, figure_norms as fn

csv.field_size_limit(10**9)
FAILS = 0
TOP_VENUES = {"cs_conf": ["CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "ICLR"],
              "cs_journal": ["TPAMI", "IJCV", "TIP", "TMI", "MedIA", "InfoFusion", "TMM", "TKDE"], "nature": ["Nature"]}
ROLES = ["motivation", "method", "main_result", "ablation", "qualitative", "analysis"]
TABLE_ROLES = ["main_result", "ablation", "efficiency", "other"]
PAGE_HINT = {"motivation": "p1–2", "method": "p3–4", "main_result": "p6–7", "ablation": "p7–8", "qualitative": "p6–8", "analysis": "p7–8"}
DEFAULT_WIDTH = {"motivation": "double", "method": "double", "qualitative": "double"}
ROLE_TYPES = {"motivation": {"concept"}, "method": {"overview"}, "main_result": {"comparison", "bars", "curves"}, "ablation": {"ablation"},
              "qualitative": {"qualitative"}, "analysis": {"heatmap", "embedding", "curves", "failure"}}
PLAN_COLS = ["item", "kind", "role", "claim_ids", "form_reason", "generator", "files", "width", "panels", "page_hint", "exemplar", "exemplar_caption", "thumb", "status", "note"]
EX_COLS = ["paper_id", "title", "venue", "year", "cited", "fresh", "bm25", "source", "pdf"]
FIG_COLS = ["paper_id", "kind", "n", "page", "width", "role", "types", "panels", "caption_first", "caption", "thumb"]
LOCAL_STOP = {"ours", "our", "relative", "strongest", "baseline", "baselines", "removing", "removes", "removed", "raises", "lowers", "less", "than", "more", "within", "seed",
              "seeds", "standard", "deviation", "deviations", "held", "out", "reported", "rather", "interpreted", "cells", "single", "run", "each", "term", "gain", "comes"}


def say(st, msg):
    global FAILS
    FAILS += st == "FAIL"
    print(f"[{st}] figure_plan: {msg}")


def read(p): return io.open(p, encoding="utf-8-sig", errors="replace").read()


def write(p, text):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)


def read_csv(p):
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig", newline=""))) if os.path.exists(p) else []


def write_csv(p, cols, rows):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def load_state(root):
    p = os.path.join(root, "research-state.yaml")
    if not os.path.exists(p): return {}
    import yaml
    return yaml.safe_load(read(p)) or {}


def norm(t): return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def med(xs): return statistics.median(xs) if xs else 0


def target_family(st):
    t = st.get("target") or {}
    return t.get("family") or fn.FAMILY.get(t.get("venue") or "", "")


# ------------------------------------------------------------------ prereg / claims
def prereg_parts(root):
    """(§0 phenomenon sentence or '', §1 hypothesis sentence or '') — template placeholders and '跳过' count as absent"""
    p = os.path.join(root, "prereg.md")
    if not os.path.exists(p): return "", ""
    t = read(p); secs = {m.group(1): m.group(2) for m in re.finditer(r"(?ms)^## (\d+)\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)", t)}
    m = re.search(r"(?m)^[-*]\s*(?:现象|phenomenon)\s*[:：]\s*(.+)$", secs.get("0", ""), re.I)
    ph = m.group(1).strip() if m else ""
    if not ph or ph.startswith("<") or ph.startswith("跳过"): ph = ""
    hyp = ""
    for l in secs.get("1", "").splitlines():
        l = l.strip()
        if l and not l.startswith(("来源", "一句")): hyp = l; break
    return ph, hyp


def load_claims(root):
    return [r for r in read_csv(os.path.join(root, "paper", "claims.csv")) if (r.get("statement") or "").strip()]


def is_numeric_claim(c):
    return bool((c.get("evidence_key") or "").strip()) or bool(re.search(r"\d", c.get("expected") or ""))


QUAL_RE = re.compile(r"qualitative|\bvisuali[sz]\w*|\bvisual\b|attention map|\bCAM\b|grad-?cam|routing map|saliency|heat ?map|failure case", re.I)
ABL_RE = re.compile(r"ablat|\bremov(?:e|es|ed|ing|al)\b|\bwithout\b|\bw/o\b|\bno_\w+", re.I)
COND_RE = re.compile(r"\b(?:as|when)\b[^.;]{0,50}\b(?:increas|decreas|grow|shrink|vary|varies|rise|fall|drop)\w*|across (?:illumination|dose|noise|occlusion|levels|conditions|settings|resolutions)"
                     r"|\bunder (?:low|high|varying|different|extreme|degraded|heavy|noisy|reduced)|degrad\w+ (?:with|as|under)|as a function of", re.I)
PHEN_RE = re.compile(r"\bexisting\b|\bprior\b|\bprevious\b|(?:methods?|baselines?|detectors?) (?:fail|degrade|collapse)", re.I)
MAIN_RE = re.compile(r"outperform|state-of-the-art|\bsota\b|\bvs\.?\b|versus|better than|relative to|lower than|higher than|improv", re.I)


def claim_role(c):
    """claim -> figure role ('' = a statement with neither numbers nor a figure cue, not planned)"""
    s = c.get("statement") or ""; key = (c.get("evidence_key") or "").strip(); num = is_numeric_claim(c)
    if "prereg" in (c.get("evidence_file") or "").lower() or re.search(r"prereg|§\s*0|phenomen", s, re.I): return "motivation"
    if key.startswith("z:") or ABL_RE.search(s): return "ablation"
    if QUAL_RE.search(s): return "analysis" if key else "qualitative"
    if COND_RE.search(s): return "motivation" if PHEN_RE.search(s) else "analysis"
    if key.startswith("rel:") or MAIN_RE.search(s) or key.startswith("mean:"): return "main_result"
    return "analysis" if num else ""


# ------------------------------------------------------------------ exemplars: corpus search
def default_venues(st, override):
    if override: return {v.strip().lower() for v in override.split(",") if v.strip()}, ""
    fam = target_family(st); vs = {v.lower() for v in TOP_VENUES.get(fam, TOP_VENUES["cs_conf"])}
    return vs, norm((st.get("target") or {}).get("venue"))


def venue_ok(venue, allowed, target_norm, nature):
    v = (venue or "").lower()
    if v in allowed: return True
    if nature and re.match(r"nat", v): return True
    vn = norm(venue)
    return bool(target_norm and len(vn) >= 3 and (vn in target_norm or target_norm in vn))


def resolve_pdf(local_path, venue, year, papers):
    """local_path if it exists, else <papers>/<venue>/<year>/<basename> (also under nature/); '' = not on this machine"""
    if not local_path: return ""
    if os.path.exists(local_path): return local_path
    base = os.path.basename(local_path.replace("\\", "/"))
    for sub in ((venue, year), ("nature", venue, year)):
        c = os.path.join(papers or "", *sub, base)
        if papers and os.path.exists(c): return c
    return ""


def build_query(a, st, root):
    """topic + title only: claims and the hypothesis describe this paper's FINDINGS ('gated', 'augmentation', 'all six'),
    and on cvpr2027_fusion they pulled 'Robot-Gated Imitation Learning' and 'Quantum-Gated Distillation' in as exemplars"""
    if a.query: return a.query
    p = st.get("project") or {}; seen = []
    for t in (p.get("topic") or "", p.get("title") or ""):
        for w in lit_scout.terms(t)[1]:
            if w not in seen and w not in LOCAL_STOP: seen.append(w)
    return " ".join(seen[:25])


def domain_ok(domain, title, abstract, q_words):
    """--domain 'a|b, c|d': every comma group must match (any '|' alternative, word prefix); without --domain at least half
    of the query's content words must be in title + abstract (conference rows have no abstract, so this is a title test)"""
    t = " " + re.sub(r"[^a-z0-9]+", " ", (title + " " + (abstract or "")).lower()) + " "
    if domain:
        return all(any(" " + alt.strip().lower() in t for alt in grp.split("|") if alt.strip()) for grp in domain.split(",") if grp.strip())
    hits = sum(1 for w in q_words if " " + w in t)
    return hits >= max(2, (len(q_words) + 1) // 2)


def openalex_cited(title, year, replay, net):
    """citation count of a work by title: replay file {title: count}, or OpenAlex (title search, the hit with the same normalised title)"""
    if replay is not None:
        for t, n in replay.items():
            if norm(t)[:60] == norm(title)[:60]: return int(n)
        return None
    if not net: return None
    import survey_search
    x = survey_search.http("https://api.openalex.org/works?" + urllib.parse.urlencode({"search": title, "filter": f"publication_year:{year}" if str(year).isdigit() else "type:article", "per-page": 3, "mailto": survey_search.EMAIL}))
    try: res = json.loads(x or "{}").get("results") or []
    except Exception: return None
    for w in res:
        if norm(w.get("display_name") or w.get("title"))[:60] == norm(title)[:60]: return int(w.get("cited_by_count") or 0)
    return None


def pick_exemplars(a, st, root):
    """-> (picked rows [dict], stats dict)"""
    q = build_query(a, st, root); print(f"query: {q}")
    stats = {"query": q, "skipped_nopdf": 0, "cand": 0, "dropped_cit": 0, "unknown_cit": 0}
    allowed, tnorm = default_venues(st, a.venues); nature = target_family(st) == "nature" and not a.venues
    idx = a.index if os.path.isabs(a.index) else os.path.join(root, a.index)
    if not os.path.exists(idx):
        if not a.papers or not os.path.isdir(a.papers):
            say("WARN", f"没有索引 {idx}，也找不到论文库 {a.papers}：只用 --pdf 的范文"); return [], stats
        print(f"building {idx} from {a.papers} (网络盘上要几分钟) ...", flush=True)
        os.makedirs(os.path.dirname(idx), exist_ok=True); lit_scout.build(a.papers, idx, progress=20000)
    replay = None
    if a.from_dir:
        pj = os.path.join(a.from_dir, "openalex_cited.json")
        replay = json.load(io.open(pj, encoding="utf-8")) if os.path.exists(pj) else {}
    net = a.net or replay is not None
    rows = lit_scout.search(idx, q)
    q_words = [w for w in lit_scout.terms(q)[1] if w not in LOCAL_STOP]
    if a.domain: print(f"domain: {a.domain}")
    else: say("WARN", "没给 --domain：同题材只按 query 实词过半判定；给出任务与数据的词组更准，如 --domain \"rgb|infrared|thermal, detection|detector\"")
    stats["off_domain"] = 0
    pool = []; seen = set(); per_venue = collections.Counter(); target = 3 * a.k if net else a.k
    for venue, year, title, _abs, doi, lp, cited, score in rows:
        if not (year.isdigit() and int(year) >= a.min_year) or not venue_ok(venue, allowed, tnorm, nature): continue
        if not domain_ok(a.domain, title, _abs, q_words): stats["off_domain"] += 1; continue
        key = norm(title)[:60]
        if key in seen: continue
        pdf = resolve_pdf(lp, venue, year, a.papers)
        if not pdf: stats["skipped_nopdf"] += 1; continue
        seen.add(key)
        if not net:
            if per_venue[venue] >= 3: continue
            per_venue[venue] += 1
        pool.append({"venue": venue, "year": year, "title": title, "cited": int(cited) if str(cited).strip().isdigit() else None, "bm25": round(-score, 3), "pdf": pdf, "source": "corpus"})
        if len(pool) >= target: break
    stats["cand"] = len(pool); this_year = datetime.date.today().year
    for r in pool: r["fresh"] = int(int(r["year"]) >= this_year)
    if net:
        for i, r in enumerate(pool):
            if r["cited"] is None: r["cited"] = openalex_cited(r["title"], r["year"], replay, a.net)
            if (i + 1) % 10 == 0: print(f"  ... citations {i + 1}/{len(pool)}", flush=True)
        cohort = collections.defaultdict(list)
        for r in pool:
            if r["cited"] is not None: cohort[(r["venue"], r["year"])].append(r["cited"])
        keep = []
        for r in pool:
            if r["cited"] is None: stats["unknown_cit"] += 1; keep.append(r)
            elif r["fresh"] or r["cited"] >= med(cohort[(r["venue"], r["year"])]): keep.append(r)
            else: stats["dropped_cit"] += 1
        pool = keep
    else:
        say("WARN", "未核引用数：范文质量只按刊物和年份过滤")
    out = []; cnt = collections.Counter()
    for r in sorted(pool, key=lambda r: -r["bm25"]):
        if cnt[r["venue"]] >= 3: continue
        out.append(r); cnt[r["venue"]] += 1
        if len(out) >= a.k: break
    return out, stats


# ------------------------------------------------------------------ exemplars: PDF analysis
def first_sentence(cap):
    cap = re.sub(r"\s+", " ", cap).strip()
    m = re.search(r"(?<=[a-z0-9\)\]])\.\s+(?=[A-Z(])", cap[20:])
    s = cap[:20 + m.start() + 1] if m else cap
    return s[:160]


def count_panels(cap):
    idx = []
    for m in re.finditer(r"\(([a-hA-H])\)|(?:^|[.;:]\s*)([a-h])[\s,]+[A-Z]|\b([a-h])\s*[–-]\s*([a-h])\b", cap):
        for g in m.groups():
            if g: idx.append(ord(g.lower()) - 96)
    n = max(idx) if idx else 0
    return n if n >= 2 else (2 if fn.PANEL_RE.search(cap) else 1)


# Role rules, calibrated on the 37 figures of 8 RGB-X / multimodal-detection exemplars (2026-10-28 trial on cvpr2027_fusion):
# early figures that contrast paradigms ("existing pipelines … ours", "global vs local fusion") are motivation, not method;
# "Illustrative diagram of the complete network" (p.4) is method; visualisations across SEVERAL METHODS are qualitative,
# visualisations of the model's own features / gradients are analysis; "Effects of X on M3FD" is ablation.
PROPOSED_OVERVIEW = re.compile(r"overview of (the |our )?(proposed|\w+net\b|[A-Z])|overall (workflow|architecture|framework|pipeline|structure)|schematic overview|we present a unified framework", re.I)
PARADIGM = re.compile(r"comparison (between|of)\b.{0,80}\b(existing|conventional|previous|different|paradigm|global|naive)|existing\b.{0,80}\b(pipelines?|methods|paradigms?)|pipelines of different|\bvs\.?\b.{0,40}\bours\b|advantages? of|motivat|teaser|failure of existing", re.I)
DATASET = re.compile(r"statistics of|examples? (of|from) the\b.{0,40}\bdataset|(proposed|our|synthesi[sz]ed) (dataset|data)\b|dataset (samples|examples|statistics)", re.I)
MULTI_METHOD_VIS = re.compile(r"(visual|qualitative|heat ?map|detection|segmentation|fusion)\b.{0,40}\b(results?|comparisons?|visuali[sz]ation)\b.{0,80}\b(several|different|various|other|existing|competing|sota|state-of-the-art)\b.{0,40}\b(methods|models|approaches|detectors)|(several|different|various|other)\b.{0,30}\b(methods|models|approaches|detectors)\b", re.I)
INTERNAL_VIS = re.compile(r"feature (map )?visuali|visuali[sz]ation of (the )?(features?|task|attention|gradients?|routing|gates?)|attention (map|weight)|activation|conflicting gradients|t-?sne|embedding", re.I)
QUAL = re.compile(r"qualitative|visual (results|comparisons?)|detection results|examples?\b", re.I)
METHOD = re.compile(r"overview|framework|architecture|network|pipeline|schematic|diagram|\bmodules?\b|sub-?modules|workflow|illustration of the proposed", re.I)
MAIN = re.compile(r"state-of-the-art|\bsota\b|accuracy[- ]efficiency|trade-?off|benchmark|outperform|comparison (with|against|to)", re.I)
ABL = re.compile(r"ablat|w/o|without\b|effects? of|impact of|influence of|shapley|importance of each component|configurations?|variants? of|sensitivity", re.I)

def fig_role(n, page, types, cap):
    t = set(types); c = re.sub(r"\s+", " ", cap)[:250]   # extracted captions run on into body text ("Visual results of image fusion on M3FD. 3.4 Gradient Matrix …")
    early = n <= 2 and 0 < page <= 2
    if DATASET.search(c): return "dataset"
    if early and not PROPOSED_OVERVIEW.search(c): return "motivation"
    if MULTI_METHOD_VIS.search(c) and re.search(r"visual|heat ?map|results?|qualitative", c, re.I): return "qualitative"
    if PARADIGM.search(c) and n <= 2: return "motivation"
    if INTERNAL_VIS.search(c): return "analysis"
    if QUAL.search(c): return "qualitative"
    if ABL.search(c): return "ablation"
    if METHOD.search(c) or "overview" in t: return "method"
    if MAIN.search(c) and t & {"comparison", "bars", "curves", "tradeoff"}: return "main_result"
    return "analysis"


def table_role(cap):
    c = re.sub(r"\s+", " ", cap)[:200].lower()   # first sentence decides: "Comparison with state-of-the-art methods. … Params / FLOPs …" is a main-result table
    if re.search(r"ablat|w/o|without|component|variants?\b|effects? of|impact of|influence of|different\b.{0,40}\b(strateg|settings?|configurations?|designs?)", c): return "ablation"
    if re.search(r"state-of-the-art|\bsota\b|quantitative (results|comparisons?)|benchmark|results on|comparisons? (with|on|among)|performance comparison|outperform", c): return "main_result"
    if re.search(r"params|flops|latency|speed|\bfps\b|memory|efficien|runtime|inference time|model size", c): return "efficiency"
    if re.search(r"comparison|performance|accuracy", c): return "main_result"
    return "other"


def figure_region(page, cap):
    """rect of the image/drawing cluster just above the caption block (None when there is none)"""
    import fitz
    W, H = page.rect.width, page.rect.height; items = []
    for im in page.get_images(full=True):
        try: items += [fitz.Rect(r) for r in page.get_image_rects(im[0])]
        except Exception: pass
    try: items += [fitz.Rect(d["rect"]) for d in page.get_drawings()]
    except Exception: pass
    items = [r for r in items if not r.is_empty and r.width * r.height >= 20 and not (r.width > 0.97 * W and r.height > 0.9 * H)
             and r.x1 > cap.x0 - 5 and r.x0 < cap.x1 + 5 and r.y1 <= cap.y0 + 4]
    region = None
    for r in sorted(items, key=lambda r: -r.y1):
        if region is None:
            if cap.y0 - r.y1 > 60: break
            region = fitz.Rect(r)
        elif r.y1 >= region.y0 - 14: region |= r
        else: break
    return region


def analyze_exemplar(pdf, pid, thumbs):
    """-> list of figure/table dicts (FIG_COLS) or None when the PDF cannot be read"""
    import fitz
    try: d = fitz.open(pdf)
    except Exception: return None
    pages_txt = [p.get_text() for p in d]; full = "\n".join(pages_txt)
    rm = re.search(r"\n\s*(references|bibliography)\s*\n", full, re.I)
    body_end = rm.start() if rm and rm.start() > len(full) * 0.4 else len(full)
    out = []; blocks = [p.get_text("blocks") for p in d]
    for n, cap in fn.captions_of(full, body_end):
        sig = re.sub(r"\s+", " ", cap)[:25]; found = fallback = None
        for pi, page in enumerate(d):
            for b in blocks[pi]:
                m = fn.CAP_RE.search(b[4]) if b[6] == 0 else None
                if not m or b[4][:m.start()].strip() or int(m.group(1)) != n: continue
                if sig in re.sub(r"\s+", " ", b[4]): found = (pi, page, fitz.Rect(b[:4])); break
                fallback = fallback or (pi, page, fitz.Rect(b[:4]))
            if found: break
        found = found or fallback
        types = [name for name, rx in fn.FIGURE_TYPES if re.search(rx, cap, re.I)]
        row = {"paper_id": pid, "kind": "fig", "n": n, "page": found[0] + 1 if found else 0, "width": "", "types": "|".join(types), "panels": count_panels(cap),
               "caption_first": first_sentence(cap), "caption": cap, "thumb": ""}
        row["role"] = fig_role(n, row["page"], types, cap)
        if found:
            pi, page, cb = found; reg = figure_region(page, cb)
            body = [fitz.Rect(b[:4]) for b in blocks[pi] if b[6] == 0 and len(b[4]) >= 40]
            tw = (max(r.x1 for r in body) - min(r.x0 for r in body)) if body else page.rect.width * 0.75
            if reg is not None and tw > 0: row["width"] = "double" if reg.width / tw > 0.6 else "single"
            clip = (fitz.Rect(reg) | cb) if reg is not None else fitz.Rect(cb.x0, max(0, cb.y0 - 0.3 * page.rect.height), cb.x1, cb.y1)
            clip = fitz.Rect(clip.x0 - 6, clip.y0 - 6, clip.x1 + 6, clip.y1 + 6) & page.rect
            tp = os.path.join(thumbs, f"{pid}_fig{n}.png")
            try: page.get_pixmap(clip=clip, dpi=110).save(tp); row["thumb"] = tp
            except Exception: pass
        out.append(row)
    seen = set()
    for pi, page in enumerate(d):
        for b in blocks[pi]:
            m = re.match(r"\s*(?:Table|TABLE)\s*(\d{1,2})\s*[.:|]", b[4]) if b[6] == 0 else None
            if not m or int(m.group(1)) in seen: continue
            seen.add(int(m.group(1))); cap = re.sub(r"\s+", " ", b[4]).strip()[:400]
            cap = re.sub(r"^(?:Table|TABLE)\s*\d{1,2}\s*[.:|]\s*", "", cap)
            out.append({"paper_id": pid, "kind": "table", "n": int(m.group(1)), "page": pi + 1, "width": "", "role": table_role(cap), "types": "", "panels": 1,
                        "caption_first": first_sentence(cap), "caption": cap, "thumb": ""})
    return out


def venue_norm(st, col):
    """(median, floor, label, n) of <col> among published papers of the target venue (family when the venue is not in the table)"""
    t = st.get("target") or {}; path = os.path.join(HERE, "..", "references", "figure-norms-per-paper.csv")
    rows = read_csv(path)
    for key, label in ((t.get("venue"), "venue"), (target_family(st), "family")):
        if not key: continue
        vals = sorted(int(r[col]) for r in rows if (r.get(label) or "").lower() == key.lower() and (r.get(col) or "").isdigit())
        if len(vals) >= 10: return med(vals), vals[int(0.25 * (len(vals) - 1))], f"{label} {key}", len(vals)
    return None


def exemplars(a):
    root = os.path.abspath(a.project); st = load_state(root)
    outdir = os.path.join(root, "literature", "exemplars"); thumbs = os.path.join(outdir, "thumbs"); os.makedirs(thumbs, exist_ok=True)
    picked, stats = pick_exemplars(a, st, root)
    for p in a.pdf:
        picked.append({"venue": "", "year": "", "title": os.path.splitext(os.path.basename(p))[0], "cited": None, "bm25": 0.0, "pdf": os.path.abspath(p), "source": "user", "fresh": 0})
    ex_rows = []; fig_rows = []; used = set(); unreadable = 0
    for i, r in enumerate(picked):
        pid = re.sub(r"[^\w.-]+", "_", os.path.splitext(os.path.basename(r["pdf"]))[0])[:60] or f"p{i}"
        while pid in used: pid += "_"
        used.add(pid)
        print(f"  [{i + 1}/{len(picked)}] {pid}", flush=True)
        figs = analyze_exemplar(r["pdf"], pid, thumbs)
        if figs is None: unreadable += 1; say("WARN", f"{r['pdf']} " + ("不存在（微信等临时目录会被清理：把 PDF 复制进 literature/pdf/ 再给 --pdf）" if not os.path.exists(r["pdf"]) else "打不开") + "，跳过"); continue
        ex_rows.append({"paper_id": pid, "title": r["title"], "venue": r["venue"], "year": r["year"], "cited": "" if r["cited"] is None else r["cited"], "fresh": r["fresh"], "bm25": r["bm25"], "source": r["source"], "pdf": r["pdf"]})
        for f in figs:
            if f["thumb"]: f["thumb"] = os.path.relpath(f["thumb"], root).replace("\\", "/")
        fig_rows += figs
    write_csv(os.path.join(outdir, "exemplars.csv"), EX_COLS, ex_rows); write_csv(os.path.join(outdir, "exemplar_figures.csv"), FIG_COLS, fig_rows)
    md, summary = exemplars_md(st, stats, ex_rows, fig_rows); write(os.path.join(outdir, "exemplars.md"), md)
    n = len(ex_rows); nf = sum(r["kind"] == "fig" for r in fig_rows); nt = len(fig_rows) - nf
    print(f"\nexemplars: {n} 篇（用户给的 {sum(r['source'] == 'user' for r in ex_rows)}）, {nf} 图 / {nt} 表 -> {os.path.relpath(outdir, root)}")
    print(f"候选 {stats['cand']}，无本地 PDF 跳过 {stats['skipped_nopdf']}，引用不足淘汰 {stats['dropped_cit']}，引用未知保留 {stats['unknown_cit']}，题材不符淘汰 {stats.get('off_domain', 0)}，PDF 打不开 {unreadable}")
    print(chr(10).join(summary))
    if n < 3: say("WARN", f"范文只有 {n} 篇（< 3）：调 --query / --min-year / --venues，或用 --pdf 补；不足时 figure-norms.md 是刊物层面的退路")
    else: say("PASS", f"{n} 篇范文；先用 Read 工具打开 literature/exemplars/thumbs/ 里的缩略图，再 `figure_plan.py plan`")


def role_stats(fig_rows, ex_ids, kind, roles):
    out = {}
    for role in roles:
        rs = [r for r in fig_rows if r["kind"] == kind and r["role"] == role]; per = collections.Counter(r["paper_id"] for r in rs)
        widths = collections.Counter(r["width"] for r in rs if r["width"])
        sents = []; used = set()
        for r in sorted(rs, key=lambda r: -len(r["caption_first"]) if len(r["caption_first"]) <= 160 else 0):
            if r["paper_id"] in used or len(r["caption_first"]) < 25: continue
            used.add(r["paper_id"]); sents.append(f"{r['paper_id'][:24]} {'Fig' if kind == 'fig' else 'Table'} {r['n']}: {r['caption_first']}")
            if len(sents) == 2: break
        out[role] = {"share": len(per) / len(ex_ids) if ex_ids else 0, "n_papers": len(per), "med_count": med(list(per.values())), "med_panels": f"{med([int(r['panels']) for r in rs]):g}" if kind == "fig" else "",
                     "width": widths.most_common(1)[0][0] if widths else "", "cells": {pid: ",".join(str(r["n"]) for r in rs if r["paper_id"] == pid) for pid in per}, "sents": sents}
    return out


def exemplars_md(st, stats, ex_rows, fig_rows):
    ids = [e["paper_id"] for e in ex_rows]; L = ["# 范文的图表（figure_plan.py exemplars）", "", f"查询：`{stats['query']}`", ""]
    L += ["| # | paper | venue | year | cited | 来源 |", "|---|---|---|---|---|---|"]
    for i, e in enumerate(ex_rows): L.append(f"| E{i + 1} | {e['title'][:70]} | {e['venue']} | {e['year']} | {e['cited']}{' (fresh)' if str(e['fresh']) == '1' else ''} | {e['source']} |")
    L += ["", "## 角色 × 范文（格内是图号 / 表号）", "", "| 角色 | " + " | ".join(f"E{i + 1}" for i in range(len(ids))) + " | 占比 | 中位数量 | 中位面板 | 常见宽度 |", "|---|" + "---|" * (len(ids) + 4)]
    fs = role_stats(fig_rows, ids, "fig", ROLES); ts = role_stats(fig_rows, ids, "table", TABLE_ROLES); summary = []
    for name, stt, kind in [(r, fs[r], "图") for r in ROLES] + [("表:" + r, ts[r], "表") for r in TABLE_ROLES]:
        L.append(f"| {name} | " + " | ".join(stt["cells"].get(p, "") for p in ids) + f" | {stt['n_papers']}/{len(ids)} | {stt['med_count']:g} | {stt['med_panels']} | {stt['width']} |")
        if kind == "图": summary.append(f"- **{name}** {stt['n_papers']}/{len(ids)} 篇有，中位 {stt['med_count']:g} 张，{stt['width'] or '宽度未知'}，{stt['med_panels']} 面板")
    L += ["", "## 各角色最能说明问题的两句题注", ""]
    for r in ROLES:
        if fs[r]["sents"]: L += [f"- **{r}**"] + [f"  - {s}" for s in fs[r]["sents"]]
    nf = [sum(1 for r in fig_rows if r["kind"] == "fig" and r["paper_id"] == p) for p in ids]; nt = [sum(1 for r in fig_rows if r["kind"] == "table" and r["paper_id"] == p) for p in ids]
    L += ["", "## 数量", "", f"- 范文中位：{med(nf):g} 图 / {med(nt):g} 表 每篇"]
    for col, label, xs in (("n_fig", "图", nf), ("n_tab", "表", nt)):
        vn = venue_norm(st, col)
        if vn: L.append(f"- 目标刊物层面（references/figure-norms.md，{vn[2]}，{vn[3]} 篇）：{label}/篇中位 {vn[0]:g}，下四分位 {vn[1]}")
    return "\n".join(L + ["", "## 摘要（每角色一行）", ""] + summary) + "\n", summary


# ------------------------------------------------------------------ plan
def csv_info(root, rel):
    p = os.path.join(root, rel)
    rows = read_csv(p)
    if not rows: return {"exists": False, "cols": [], "num": [], "rows": []}
    cols = list(rows[0].keys()); num = []
    for c in cols:
        if c in ("seed", "run_id", "ablation", "method", "dataset", "hardware"): continue
        try: [float(r[c]) for r in rows[:20] if r[c] != ""]; num.append(c)
        except Exception: pass
    return {"exists": True, "cols": cols, "num": num, "rows": rows}


def exemplar_shares(ex_rows, fig_rows, kind="fig"):
    ids = [e["paper_id"] for e in ex_rows]
    return {r: (len({x["paper_id"] for x in fig_rows if x["kind"] == kind and x["role"] == r}) / len(ids) if ids else 0) for r in ROLES + ["efficiency", "other"]}


def pick_reference(ex_rows, fig_rows, role, kind, st, wanted):
    """best-matching exemplar figure/table of the same role: same types, then target venue, then BM25"""
    meta = {e["paper_id"]: e for e in ex_rows}; tv = norm((st.get("target") or {}).get("venue"))
    cands = [r for r in fig_rows if r["kind"] == ("fig" if kind == "figure" else "table") and r["role"] == role and r["paper_id"] in meta]
    if not cands: return None
    def score(r):
        e = meta[r["paper_id"]]; vn = norm(e["venue"])
        return (len(set(r["types"].split("|")) & wanted), int(bool(tv and vn and (vn in tv or tv in vn))), float(e["bm25"] or 0), -int(r["n"]))
    r = max(cands, key=score); r["_meta"] = meta[r["paper_id"]]
    return r


def plan(a):
    root = os.path.abspath(a.project); st = load_state(root); out = os.path.join(root, "paper", "figure_plan.csv")
    if os.path.exists(out) and not a.force:
        say("FAIL", "paper/figure_plan.csv 已存在（计划是你改过的草稿）：--force 才覆盖"); return
    ex_rows = read_csv(os.path.join(root, "literature", "exemplars", "exemplars.csv")); fig_rows = read_csv(os.path.join(root, "literature", "exemplars", "exemplar_figures.csv"))
    claims = load_claims(root); ph, _ = prereg_parts(root); res = st.get("results") or {}
    main = csv_info(root, res.get("main_table") or "results/main.csv"); abl = csv_info(root, res.get("ablation_table") or "results/ablation.csv")
    main_rel = res.get("main_table") or "results/main.csv"; abl_rel = res.get("ablation_table") or "results/ablation.csv"
    by_role = collections.defaultdict(list)
    for c in claims:
        r = claim_role(c)
        if r: by_role[r].append(c)
        else: print(f"[INFO] figure_plan: 主张 {c.get('claim_id')} 无数字也无图型线索，未入计划")
    shares = exemplar_shares(ex_rows, fig_rows); n_ex = len(ex_rows); pm = res.get("primary_metric") or ""
    metrics = ",".join(main["num"][:6]) or "<metrics>"
    gk = res.get("group_key") or "method"
    n_methods = len({r.get(gk) for r in main["rows"]}) if main["exists"] else 0
    ds_col = "dataset" if "dataset" in main["cols"] else ""
    n_ds = len({r["dataset"] for r in main["rows"]}) if ds_col else len({str(v).split(".")[0] for v in (res.get("metric_map") or {}).values()}) or 1
    seeds = (res.get("min_seeds") or 0) >= 2 or len((st.get("experiments") or {}).get("seeds") or []) >= 2 or len({r.get("seed") for r in main["rows"]}) > 1
    rows = []
    def add(role, kind, claim_ids, reason, gen, files, wanted, note=""):
        ref = pick_reference(ex_rows, fig_rows, role, kind, st, wanted) if ex_rows else None
        d = {"item": "", "kind": kind, "role": role, "claim_ids": ";".join(claim_ids), "form_reason": reason, "generator": gen, "files": files,
             "width": (ref["width"] if ref and ref["width"] else DEFAULT_WIDTH.get(role, "single")), "panels": (ref["panels"] if ref else (2 if role == "ablation" and kind == "figure" else 1)),
             "page_hint": PAGE_HINT[role] if kind == "figure" or role != "method" else "", "exemplar": "", "exemplar_caption": "", "thumb": "", "status": "planned", "note": note}
        if ref:
            e = ref["_meta"]; short = (e["title"] or ref["paper_id"])[:40]
            d["exemplar"] = f"仿 {short} Fig {ref['n']}（p.{ref['page']}，{ref['width'] or '宽度未知'}，{ref['panels']} 面板）" if kind == "figure" else f"仿 {short} Table {ref['n']}（p.{ref['page']}）"
            d["exemplar_caption"] = ref["caption_first"]; d["thumb"] = ref["thumb"]
        elif n_ex: d["note"] = (note + "；" if note else "") + "范文里没有同角色的" + ("图" if kind == "figure" else "表") + "，按 references/figure-norms.md 的刊物常态"
        rows.append(d)
    # motivation
    mot = by_role.get("motivation", [])
    if ph or mot:
        txt = " ".join([c["statement"] for c in mot] + [ph])
        if re.search(r"trade-?off|pareto|flops|latency", txt, re.I): g = f"make_motivation.py tradeoff --csv results/efficiency.csv --x GFLOPs --y {pm or '<metric>'} --label method --ours ours --out figures/fig_motivation.png"
        elif re.search(r"paradigm|existing .{0,40}\bvs\b|different pipeline", txt, re.I): g = "make_motivation.py schematic --spec figures/motivation_scheme.yaml --out figures/fig_motivation.png   # 模板 templates/motivation_scheme.yaml"
        elif re.search(r"\bpaired\b|per[- ](?:dataset|item|backbone)|naive fusion|better single", txt, re.I): g = "make_motivation.py paired --csv results/table1.csv --item dataset --from <A> --to <B> --out figures/fig_motivation.png"
        elif re.search(r"new (?:dataset|modality)|thumbnails?", txt, re.I): g = "make_motivation.py strip --item \"<label>|<a.png>|<b.png>\" --out figures/fig_motivation.png"
        else:
            pil = next((p for p in ("results/pilot.csv", "results/motivation.csv") if os.path.exists(os.path.join(root, p))), "results/pilot.csv")
            g = f"make_motivation.py condition --csv {pil} --x <condition> --y {pm or '<metric>'} --series method --ours ours --out figures/fig_motivation.png"
        add("motivation", "figure", [c["claim_id"] for c in mot], "prereg §0 现象 / 动机主张：一张图一条主张，用来说明为什么要做", g, "figures/fig_motivation", ROLE_TYPES["motivation"],
            "" if mot else "只有 prereg §0 的现象，没有对应 claims 行——想清楚这张图支撑哪条主张")
    # method overview (always)
    code = ((st.get("audits") or {}).get("code_dirs") or ["code"])[0]
    arch = "figures/arch/model.yaml"
    gen = (f"make_architecture.py render --spec {arch} --out figures/fig_arch.pdf" if os.path.exists(os.path.join(root, arch)) else
           f"make_architecture.py trace --model {code}/<file>.py:<Class> --input \"<name>:1x3x<H>x<W>\" --out {arch}  &&  make_architecture.py render --spec {arch} --out figures/fig_arch.pdf")
    add("method", "figure", [], "方法总览：承载方法一节，不需要主张；由模型 trace 出来，不手画", gen, "figures/fig_arch", ROLE_TYPES["method"])
    # main result
    mr = by_role.get("main_result", [])
    if mr:
        ids = [c["claim_id"] for c in mr]; big = n_methods >= 3 and (len(main["num"]) >= 2 or n_ds >= 2)
        sub = f"multi --csv {main_rel} --datasets <A,B> --dataset-col dataset" if n_ds >= 2 and ds_col else f"sota --csv {main_rel}"
        tg = f"make_comparison.py {sub} --out paper/tab_sota.tex --metrics {metrics} --md"
        fg = f"make_figure.py main --project . --out figures/fig_main.png --metrics {metrics}"
        if big:
            add("main_result", "table", ids, f"{n_methods} 个方法 × {len(main['num'])} 个指标 / {n_ds} 个数据集的精确数字 → 表", tg, "paper/tab_sota", ROLE_TYPES["main_result"])
            if shares["main_result"] >= 0.5:
                add("main_result", "figure", ids, f"范文 {round(shares['main_result'] * n_ex)}/{n_ex} 有主结果图：表之外再给一张图（柱 / 逐 seed 点）", fg, "figures/fig_main", ROLE_TYPES["main_result"])
        else:
            add("main_result", "figure", ids, f"只有 {n_methods} 个方法 × {len(main['num'])} 个指标：数字太少不值得一张表 → 图", fg, "figures/fig_main", ROLE_TYPES["main_result"])
    ab = by_role.get("ablation", [])
    if ab:
        ids = [c["claim_id"] for c in ab]; am = ",".join(abl["num"][:6]) or metrics
        add("ablation", "table", ids, "消融是精确数字的逐行对照 → 表", f"make_comparison.py ablation --csv {abl_rel} --components <组件列> --metrics {am} --out paper/tab_ablation.tex", "paper/tab_ablation", ROLE_TYPES["ablation"])
        if seeds:
            add("ablation", "figure", ids, "项目有多 seed：再出一张带噪声带的 Δ 图，看哪些格在种子噪声内", "make_figure.py ablation --project . --out figures/fig_abl.png", "figures/fig_abl", ROLE_TYPES["ablation"])
    q = by_role.get("qualitative", [])
    if q:
        add("qualitative", "figure", [c["claim_id"] for c in q], "定性主张只能用图展示", "make_comparison.py grid --root figures/qual --methods <列> --samples <列> --out figures/fig_qual.png", "figures/fig_qual", ROLE_TYPES["qualitative"])
    for i, c in enumerate(by_role.get("analysis", []), 1):
        s = c["statement"]; cid = c["claim_id"]
        if re.search(r"per[- ](?:item|backbone|dataset)|paired|each (?:backbone|detector|dataset)", s, re.I): g, why = f"make_figure.py stems --csv results/items.csv --item backbone --x baseline_AP --y ours_AP --out figures/fig_analysis_{i}.png", "逐项配对增益 → 图"
        elif re.search(r"distribution|spread|quartile", s, re.I): g, why = f"make_figure.py box --csv results/dist.csv --value <v> --group dataset --out figures/fig_analysis_{i}.png", "分布 → 图"
        elif re.search(r"\bdrop\b|\bgain\b|Δ", s): g, why = f"make_figure.py hbar --csv results/drop.csv --value <v> --group dataset --out figures/fig_analysis_{i}.png", "逐项差值 → 图"
        else: g, why = f"make_figure.py curves --csv results/curves.csv --x <条件> --y {pm or '<metric>'} --series method --out figures/fig_analysis_{i}.png", "随条件 / epoch 变化的趋势或权衡 → 图"
        add("analysis", "figure", [cid], why, g, f"figures/fig_analysis_{i}", ROLE_TYPES["analysis"] | ({"heatmap"} if QUAL_RE.search(s) else set()))
    rows.sort(key=lambda r: (ROLES.index(r["role"]), 0 if r["kind"] == "table" else 1))
    nf = nt = 0
    fstems = [os.path.splitext(r["file"].replace("\\", "/"))[0].lower() for r in read_csv(os.path.join(root, "figures.csv"))]
    for r in rows:
        if r["kind"] == "figure": nf += 1; r["item"] = f"Fig {nf}"
        else: nt += 1; r["item"] = f"Table {nt}"
        if r["kind"] == "figure" and any(covers(r["files"].lower(), s) for s in fstems): r["status"] = "done"
    write_csv(out, PLAN_COLS, rows)
    lines = report(root, st, rows, claims, ex_rows, fig_rows, shares)
    md = ["# 图表计划（figure_plan.py plan）", "", "草稿：先看 `literature/exemplars/thumbs/` 的缩略图，再改 `figure_plan.csv`（claims 先行；范文有而本文没有主张的图不画）。", "",
          "| item | kind | role | claims | 形式理由 | 生成命令 | 宽度 | 面板 | 位置 | 范文 | 状态 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['item']} | {r['kind']} | {r['role']} | {r['claim_ids']} | {r['form_reason']} | `{r['generator']}` | {r['width']} | {r['panels']} | {r['page_hint']} | {r['exemplar']}<br>{r['exemplar_caption']}<br>{r['thumb']} | {r['status']} |")
    write(os.path.join(root, "paper", "figure_plan.md"), "\n".join(md + ["", "## 报告", ""] + [f"- {l}" for l in lines]) + "\n")
    print(f"\nplan: {nf} 图 {nt} 表 -> paper/figure_plan.csv / .md（草稿：改完再画；画完登记 figures.csv，`files` 列对应）")


def covers(entry, fstem):
    """a plan `files` entry (extension dropped) covers a figures.csv stem: the same file, or a panel x_a / x_b of x"""
    entry = os.path.splitext(entry.replace("\\", "/").lstrip("./"))[0].lower(); fstem = fstem.lstrip("./")
    return bool(entry) and (fstem == entry or fstem.startswith(entry + "_") or re.sub(r"_[a-h]$", "", fstem) == entry)


def plan_files(row): return [f.strip() for f in (row.get("files") or "").split(";") if f.strip()]


def uncarried(claims, rows):
    """numeric claims no live plan row carries (claim_ids, or claims.table_or_figure naming the row's item)"""
    live = [r for r in rows if r.get("status") != "dropped"]; out = []
    for c in claims:
        if not is_numeric_claim(c): continue
        tf = re.sub(r"[^a-z0-9]", "", (c.get("table_or_figure") or "").lower().replace("figure", "fig"))
        if any(c["claim_id"] in (r.get("claim_ids") or "").split(";") or (tf and tf == re.sub(r"[^a-z0-9]", "", (r.get("item") or "").lower())) for r in live): continue
        out.append(c)
    return out


def report(root, st, rows, claims, ex_rows, fig_rows, shares):
    lines = []
    def emit(stt, msg): say(stt, msg); lines.append(f"[{stt}] {msg}")
    for c in uncarried(claims, rows): emit("WARN", f"主张 {c['claim_id']} 带数字但没有任何计划行承载（evidence_key={c.get('evidence_key') or '-'}, expected={c.get('expected') or '-'}）：加一行，或在 claims.table_or_figure 指明它在哪张图表里")
    n = len(ex_rows)
    if n < 3: emit("INFO", f"范文只有 {n} 篇（< 3）：跳过「范文有而本文没有」的对照；图表数量只对照刊物常态")
    else:
        have = {r["role"] for r in rows if r["status"] != "dropped"}
        for role in ROLES:
            if role != "method" and shares.get(role, 0) >= 0.5 and role not in have:
                k = round(shares[role] * n); emit("INFO", f"范文 {k}/{n} 有 {role}，本文没有对应主张——要么补主张，要么不画（不要为了像而画）")
    nf = sum(r["kind"] == "figure" and r["status"] != "dropped" for r in rows); nt = sum(r["kind"] == "table" and r["status"] != "dropped" for r in rows)
    exf = [sum(1 for r in fig_rows if r["kind"] == k and r["paper_id"] == e["paper_id"]) for e in ex_rows for k in ("fig",)]
    ext = [sum(1 for r in fig_rows if r["kind"] == "table" and r["paper_id"] == e["paper_id"]) for e in ex_rows]
    parts = [f"计划 {nf} 图 {nt} 表"] + ([f"范文中位 {med(exf):g} 图 {med(ext):g} 表"] if n else [])
    short = []
    for col, k, what in (("n_fig", nf, "图"), ("n_tab", nt, "表")):
        vn = venue_norm(st, col)
        if vn:
            parts.append(f"{vn[2]} {what}/篇中位 {vn[0]:g}，下四分位 {vn[1]}")
            if k < vn[1]: short.append(f"{what} {k} 张 < {vn[2]} 下四分位 {vn[1]}")
    if short: emit("WARN", "；".join(parts) + "。低于刊物底线：补主张和对应图表（G5 也会 WARN）")
    else: emit("INFO", "；".join(parts))
    return lines


# ------------------------------------------------------------------ check
def check(a):
    root = os.path.abspath(a.project); pp = os.path.join(root, "paper", "figure_plan.csv")
    if not os.path.exists(pp): say("WARN", "没有图表计划（figure_plan.py exemplars → plan）"); return
    n_ex = len(read_csv(os.path.join(root, "literature", "exemplars", "exemplars.csv")))
    if n_ex < 3: say("WARN", f"literature/exemplars/exemplars.csv 只有 {n_ex} 篇范文（< 3）：图表只对照了刊物常态，没有同主题高质量论文作参考")
    rows = read_csv(pp); claims = read_csv(os.path.join(root, "paper", "claims.csv")); ids = {c["claim_id"] for c in claims if c.get("claim_id")}
    figs = read_csv(os.path.join(root, "figures.csv")); bad = 0
    fstems = [(os.path.splitext(f["file"].replace("\\", "/"))[0].lower(), (f.get("plan_item") or "").strip().lower()) for f in figs]
    for r in rows:
        item = r.get("item") or "?"; live = (r.get("status") or "planned") != "dropped"
        if not live and not (r.get("note") or "").strip(): bad += 1; say("FAIL", f"{item} 标了 dropped 但 note 为空：写明为什么不画（哪条主张不需要它）")
        for cid in [x for x in (r.get("claim_ids") or "").split(";") if x]:
            if cid not in ids: bad += 1; say("FAIL", f"{item} 的 claim_ids 引用了不存在的主张 {cid}（claims.csv 里已没有）")
        if r.get("kind") == "figure" and live:
            ents = plan_files(r)
            if not any(covers(e, s) for e in ents for s, _ in fstems) and not any(pi == item.lower() for _, pi in fstems):
                bad += 1; say("FAIL", f"计划里的 {item} 还没画（{r.get('role')}；files={r.get('files') or '空'}；生成：{(r.get('generator') or '')[:70]}）")
    live_rows = [r for r in rows if (r.get("status") or "planned") != "dropped"]
    planned_files = [e for r in live_rows if r.get("kind") == "figure" for e in plan_files(r)]
    for s, pi in dict.fromkeys(fstems):
        if "/instruments/" in "/" + s or s.endswith("_gray"): continue
        if any(covers(e, s) for e in planned_files) or any(pi == (r.get("item") or "").lower() for r in live_rows): continue
        bad += 1; say("WARN", f"未计划的图 {s}：它支撑哪条主张？（加一行 figure_plan.csv 并填 files，或不要这张图）")
    for c in uncarried([c for c in claims if (c.get("statement") or "").strip()], rows):
        bad += 1; say("WARN", f"主张 {c['claim_id']} 带数字但没有任何计划行承载：在某行的 claim_ids 里加上它，或在 claims.table_or_figure 指明")
    if not bad: say("PASS", f"{len(rows)} 行计划与 figures.csv、claims.csv 一致（{sum(r.get('kind') == 'figure' for r in live_rows)} 图 {sum(r.get('kind') == 'table' for r in live_rows)} 表）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("exemplars"); e.add_argument("--project", default="."); e.add_argument("--query", default=""); e.add_argument("--domain", default="", help="'a|b, c|d': every comma group must match title+abstract"); e.add_argument("--k", type=int, default=8); e.add_argument("--min-year", type=int, default=2023)
    e.add_argument("--venues", default=""); e.add_argument("--papers", default=os.environ.get("T2P_PAPERS", "Z:/LDCT/papers")); e.add_argument("--index", default="literature/lit_index.sqlite")
    e.add_argument("--pdf", action="append", default=[], help="a paper you want as an exemplar (repeatable)"); e.add_argument("--net", action="store_true", help="OpenAlex citation counts (the quality filter)")
    e.add_argument("--from-dir", default="", help="replay <dir>/openalex_cited.json instead of calling OpenAlex")
    p = sub.add_parser("plan"); p.add_argument("--project", default="."); p.add_argument("--force", action="store_true")
    c = sub.add_parser("check"); c.add_argument("--project", default=".")
    a = ap.parse_args()
    {"exemplars": exemplars, "plan": plan, "check": check}[a.cmd](a)
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(FAILS)


if __name__ == "__main__":
    main()
