# -*- coding: utf-8 -*-
"""G6f — readability of the manuscript against what published papers of the target family look like. Run by Claude.

  python readability_check.py [check] [--project .] [--manuscript paper/manuscript.md] [--state research-state.yaml] [--family cs_conf|cs_journal|nature] [--norms references/readability-norms.csv] [--min-words 1500]
  python readability_check.py calibrate --corpus Z:/LDCT/papers --work <scratch dir> [--n 40] [--seed 20261023] [--min-year 2023] [--out references/readability-norms.csv]

Why: drafts that pass every other gate still read like a lab notebook — 58–80 numbers per 1k words, contribution bullets with 4–12 numbers, "preregistered/registered" 20×
in the main text, Related Work as a citation list. No editor or reviewer reads past that. This gate measures it and compares with the published corpus.

Text scope: Introduction .. last main section. Excluded: references, figure/table/algorithm captions (`**Fig. N.**`, `**Table N.**`, `**Algorithm N.**`; the pseudocode itself is a fenced code block), markdown tables, math, code, `>` notes, appendix / supplement /
Protocol / Preregistration sections, and lines that are not prose (< 6 words or mostly numbers: table and figure-axis debris of PDF conversions).
A number = digits with optional decimal / % / ± part; "0.79–3.09", "52–86%" and "0.20 ± 0.03" count once; citation brackets, Fig./Table/Section numbers, years, "ResNet-50"-style names do not.
Metrics (higher = worse; verdict from references/readability-norms.csv: > p90 WARN, > p95 WARN, >= 3 metrics > p95 at once FAIL; > 2 numbers in a contribution bullet FAIL):
  abstract_numbers / abstract_acronyms (distinct ALL-CAPS ≥2 letters, minus state.acronym_ok) / abstract_words
  contrib_numbers_max / contrib_words_max   items of the first list in the Introduction (cs families; skipped when no list is found)
  intro_* and body_*: numbers_per1k, semicolons_per1k, sent_len_mean (words), long_sent_share (sentences > 40 words)
Fixed rules (no norms): process vocabulary in the main text — preregist*, registered <ablation|prediction|…>, refuted, falsified, addendum, amendment, "convention change", locked, "post hoc",
  "measured afterwards", findings.md, "finding F<n>", gate names G<n><letter> (G6c), > 3 hits FAIL (first 5 listed), 1–3 WARN: protocol bookkeeping belongs in a Protocol appendix.
  Catalogue paragraphs in Introduction / Related Work (≥4 citations and ≥3 semicolons, or ≥5 sentences opening on "Name [n]"): each WARN with its line, ≥3 FAIL.
If the family has no rows in the norms file the built-in PROVISIONAL thresholds are used and a WARN says so. Exit = #FAIL.

calibrate: samples ~n recent papers per family from the corpus (fixed seed), converts them with pdf_to_md.py into --work (never into the corpus), measures them with the same code
and writes the percentiles to --out (header comment: seed, n, date). Families: cs_conf = CVPR ICCV ECCV NeurIPS MICCAI WACV AAAI; cs_journal = TMI MedIA TIP TPAMI IJCV;
nature = nature/<Journal>/<year>/W*.pdf (research articles only, via nature/metadata/journals.csv)."""
import argparse, csv, datetime, io, os, random, re, statistics, subprocess, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import shape_check as sc                          # headings / canon / infer_family: same section parsing as G6c
from gate_check import strip_code_math            # same math / code / note stripping as the number and acronym gates
import survey_check as sv                         # CITE: citation-group pattern shared with the survey catalogue detector
NORMS_CSV = os.path.join(SKILL, "references", "readability-norms.csv")

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] readability: {msg}")

# built-in thresholds (p90, p95) used only when the norms file has no rows for the family; rough published-paper values, replaced by `calibrate`
PROVISIONAL = {"abstract_numbers": (8, 12), "abstract_acronyms": (5, 7), "abstract_words": (230, 280), "contrib_numbers_max": (3, 5), "contrib_words_max": (60, 80),
               "intro_numbers_per1k": (25, 35), "intro_semicolons_per1k": (6, 9), "intro_sent_len_mean": (28, 32), "intro_long_sent_share": (0.12, 0.2),
               "body_numbers_per1k": (45, 60), "body_semicolons_per1k": (7, 10), "body_sent_len_mean": (27, 31), "body_long_sent_share": (0.1, 0.16)}
METRICS = list(PROVISIONAL)
MAX_OVER = 3   # calibrated 2026-10-23: >= 3 metrics above p95 at once in 2/40 published papers per family, 9–13 in the three real drafts
FLOOR = {"contrib_numbers_max": (1, 2)}    # published contribution bullets almost never carry a number (p95 = 0–1), but one headline number is fine; > 2 per bullet is the P6 rule

# ------------------------------------------------------------------ text
WORD = re.compile(r"[A-Za-z]+(?:[-'’][A-Za-z]+)*|\d+(?:[.,]\d+)*")
CITE_STRIP = re.compile(r"\[\s*\d+(?:\s*[,–—-]\s*\d+)*\s*\]|\(\s*(?:[A-Z][\w\-]+(?: et al\.?| and [A-Z][\w\-]+)?,?\s+(?:19|20)\d\d[a-z]?(?:[;,]\s*)?)+\)")
REF_STRIP = re.compile(r"\b(?:Figs?\.?|Figures?|Tables?|Sec(?:tion)?s?\.?|Eqs?\.?|Equations?|Appendix|Appendices|Algorithms?|Steps?|Stages?|Panels?|Extended Data Figs?\.?)\s*\(?[A-Z]?\d+(?:\.\d+)*[a-z]?\)?(?:\s*(?:[,–-]|and)\s*\(?[A-Z]?\d+[a-z]?\)?)*|§\s*\d+(?:\.\d+)*|https?://\S+|\b10\.\d{4,}/\S+")
NUM = re.compile(r"(?<![\w.])(?<![A-Za-z][-–−])[−+±-]?\d+(?:[.,]\d+)*(?:\s*(?:[–—-]|to)\s*\d+(?:[.,]\d+)*)?(?:\s*±\s*\d+(?:\.\d+)*)?\s*%?(?!\w)")
ACRO = re.compile(r"\b[A-Z]{2,}[A-Z0-9]*(?:-[A-Z0-9]+)*s?\b")
ROMAN = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}
ABBR = re.compile(r"\b(?:et al|e\.g|i\.e|Fig|Figs|Eq|Eqs|Sec|Tab|vs|cf|No|Ref|Refs|approx|resp|etc|Dr|Prof)\.")
LISTRE = re.compile(r"^\s*(?:[-*•▪–·]|\d+[.)]|\(\d\)|\(?[ivx]+\))\s+")
CAPTION = re.compile(r"^\s*\*\*(?:Fig(?:ure|\.)?|Table|Tab\.|Algorithm|Extended Data Fig\.?)\s*\S+?\*\*", re.I)
APPENDIX = re.compile(r"\b(appendi(?:x|ces)|supplement\w*)\b|附录|^\W*(?:\d+\.?\s*)?(?:protocol|pre-?registration)\b", re.I)

def nwords(s): return len(WORD.findall(s))

def clean(text):
    """line-preserving: code/math/notes/tags stripped, captions + tables + headings blanked."""
    t = re.sub(r"`[^`\n]*`", " ", strip_code_math(text)); out, cap = [], False
    for l in t.split("\n"):
        s = l.strip()
        if CAPTION.match(s): cap = True
        elif not s: cap = False
        out.append("" if (cap or s.startswith("|") or s.startswith("#") or (s and set(s) <= set("-|: "))) else l)
    return "\n".join(out)

def prose_lines(text):
    """lines that are prose: >= 6 words and not mostly numbers (PDF conversions leave table cells / axis labels as short or numeric lines)."""
    keep = []
    for l in text.split("\n"):
        w = WORD.findall(l)
        if len(w) >= 6 and sum(1 for x in w if x[0].isdigit()) / len(w) <= 0.4:
            s = l.strip(); item = bool(LISTRE.match(s)); s = LISTRE.sub("", s, count=1)
            keep.append(s + "." if (item and s[-1] not in ".!?;") or s[-1] == ":" else s)     # a bullet without a full stop, or a "are:" lead-in, is a sentence of its own
    return " ".join(keep)

def sentences(p):
    p = ABBR.sub(lambda m: m.group(0).replace(".", "∯"), p); p = re.sub(r"(?<=\d)\.(?=\d)", "∯", p)
    return [s.replace("∯", ".") for s in re.split(r"(?<=[.!?])\s+(?=[\"“(\[A-Z0-9])", p) if s.strip()]

def count_numbers(s):
    s = re.sub(r"\(\s*\d{1,2}\s*\)", " ", REF_STRIP.sub(" ", CITE_STRIP.sub(" ", s)))
    return sum(1 for m in NUM.finditer(s) if not re.fullmatch(r"(?:19|20)\d\d", m.group(0).strip()))

def text_stats(prose, prefix, out):
    w = max(1, nwords(prose)); ss = sentences(prose); L = [nwords(x) for x in ss] or [0]
    out[prefix + "numbers_per1k"] = 1000 * count_numbers(prose) / w; out[prefix + "semicolons_per1k"] = 1000 * prose.count(";") / w
    out[prefix + "sent_len_mean"] = sum(L) / len(L); out[prefix + "long_sent_share"] = sum(1 for x in L if x > 40) / len(L); out[prefix + "words"] = w

def first_list(text):
    """items of the first bullet / numbered list with >= 2 items of >= 5 words (continuation lines folded in; a blank line followed by a non-item ends a list)."""
    runs, items, gap = [], [], False
    for l in text.split("\n"):
        if not l.strip():
            gap = bool(items); continue
        if LISTRE.match(l): items.append(LISTRE.sub("", l, count=1).strip()); gap = False
        elif items:
            if gap: runs.append(items); items, gap = [], False
            else: items[-1] += " " + l.strip()
    runs.append(items)
    for run in runs:
        run = [i for i in run if nwords(i) >= 5]
        if len(run) >= 2: return run
    return []

PROCESS = [(r"pre-?regist\w*", "preregistration"), (r"\bregistered\s+(?:ablations?|predictions?|hypothes[ie]s|analys[ie]s|claims?|protocols?|thresholds?|primary|tests?|comparisons?|metrics?|baselines?|decisions?|outcomes?|criteri\w+|checks?|gates?)\b", "registered X"),
           (r"\brefuted\b", "refuted"), (r"\bfalsified\b", "falsified"), (r"\baddend(?:um|a)\b", "addendum"), (r"\bamendments?\b", "amendment"), (r"\bconvention[- ]change\w*", "convention change"),
           (r"\blocked\s+(?:before|prior|in advance|thresholds?|protocol|prereg\w*|criteri\w+|decision rules?|analysis plan|hypothes\w+)\b|\b(?:thresholds?|protocol|criteri\w+|hypothes[ie]s|rules?|plan)\s+(?:was|were|is|are)\s+locked\b", "locked"),
           (r"\bpost[- ]hoc\b", "post hoc"), (r"\bmeasured afterwards?\b", "measured afterwards"), (r"findings\.md", "findings.md"), (r"\bfindings? F\d+\b", "finding F#"),
           (r"\bG\d[a-z]\b|\bgates? G\d\b|\bG\d gate\b", "gate name")]    # bare G1 / F12 / F486 are cell-cycle phases, factors, mutations in published text: only suffixed gate names and "finding F<n>" count
STATS_POSTHOC = re.compile(r"Tukey|Dunn|Bonferroni|ANOVA|[SŠ]id[aá]k|Holm|Fisher|multiple[- ]comparison|t-?tests?|pairwise|Games|Scheff|post[- ]hoc\s+(?:\w+\s+){0,2}(?:tests?|analys|comparison|correction|contrast)", re.I)    # "post hoc" in the statistics sense is normal prose

def process_hits(cleaned, lo, hi):
    """[(line, label, text)] in lines lo..hi (1-based, inclusive) of the line-preserving cleaned text."""
    hits = []
    for i, l in enumerate(cleaned.split("\n"), 1):
        if i < lo or i > hi: continue
        for pat, name in PROCESS:
            if name == "post hoc" and STATS_POSTHOC.search(l): continue
            for m in re.finditer(pat, l, 0 if name == "gate name" else re.I): hits.append((i, name, m.group(0)))
    return hits

NAMED_OPEN = re.compile(r"^\s*(?:[A-Z][\w\-]*(?: et al\.?| and [A-Z][\w\-]+)?\s*\[\d|\[\d+(?:[,–-]\s*\d+)*\]\s+\w+s\b)")
def catalogue_paragraphs(cleaned, spans):
    """line numbers of catalogue paragraphs inside the given (lo, hi) line spans: citation-dense and semicolon-chained, or a run of 'Name [n] verbs …' sentences."""
    out = []
    for ln, p in sv._paragraphs(cleaned):
        if not any(lo <= ln <= hi for lo, hi in spans): continue
        cites = len(sv.CITE.findall(p)); semis = p.count(";"); named = sum(1 for s in sentences(p) if NAMED_OPEN.match(s))
        if (cites >= 4 and semis >= 3) or named >= 5: out.append(ln)
    return out

# ------------------------------------------------------------------ analysis
def analyze(md, acronym_ok=(), family="cs_conf"):
    """metrics dict for one manuscript (markdown text); keys absent when the part does not exist. Also 'process' hits and 'catalogue' line numbers."""
    md = "\n".join("" if l.lstrip().startswith(">") else l for l in md.splitlines())
    body, hs = sc.headings(md); top = [(sc.canon(t), t, s, e) for lv, t, s, e in hs if lv <= 2]
    cl_lines = clean(body).split("\n"); NL = len(cl_lines)
    ln = lambda pos: min(NL, body.count("\n", 0, max(0, pos)) + 1)            # 1-based line of a char offset in body (== line in the line-preserving cleaned text)
    seg = lambda p0, p1: "\n".join(cl_lines[ln(p0) - 1:ln(p1) - 1 if p1 < len(body) else NL])
    def sec(name):
        c = [(s, e) for cn, t, s, e in top if cn == name] + [(s, e) for lv, t, s, e in hs if sc.canon(t) == name]
        return max(c, key=lambda x: x[1] - x[0]) if c else None
    res = {}
    ab_span = sec("abstract"); ab = ""
    if ab_span:    # abstract = first paragraph of the Abstract section
        ps = [p for p in re.split(r"\n\s*\n", re.sub(r"^#.*$", "", strip_code_math(body[ab_span[0]:ab_span[1]]), flags=re.M).strip()) if p.strip() and not re.match(r"^(subject terms|keywords?|index terms)", p.strip(), re.I)]
        ab = " ".join(ps[0].split()) if ps else ""
    elif family == "nature":    # Nature-style PDFs carry no 'Abstract' heading: the first paragraph of 120–400 words before the first recognised section is the abstract
        first = min([s for cn, t, s, e in top if cn in ("intro", "results", "method", "discussion")] or [len(body)])
        for m in re.finditer(r"\S[^\n]*(?:\n(?!\s*\n)[^\n]*)*", body[:first]):
            if 120 <= nwords(m.group(0)) <= 400: ab_span = (m.start(), m.end()); ab = " ".join(m.group(0).split()); break
    if ab:
        res["abstract_words"] = nwords(ab); res["abstract_numbers"] = count_numbers(ab)
        res["abstract_acronyms"] = len({x for x in ACRO.findall(ab) if x not in ROMAN and x not in set(acronym_ok)})
    # main-text span: Introduction (else first results / method / discussion heading, else after the abstract) .. first appendix-like heading
    starts = [s for cn, t, s, e in top if cn == "intro"] or [s for cn, t, s, e in top if cn in ("results", "method", "discussion")]
    ab_end = ab_span[1] if ab_span else 0
    s0 = min(starts) if starts else ab_end
    cut = next((s for lv, t, s, e in hs if lv <= 2 and s > s0 and APPENDIX.search(t)), len(body))
    for cn, t, s, e in top:       # acknowledgements / data availability / author contributions are not argument
        if cn == "backmatter":
            for i in range(ln(s) - 1, min(NL, ln(e) - 1 if e < len(body) else NL)): cl_lines[i] = ""
    res["has_intro"] = any(cn == "intro" for cn, *_ in top); text_stats(prose_lines(seg(s0, cut)), "body_", res)
    it = sec("intro")
    if it and it[0] < cut:
        intro_c = seg(it[0], min(it[1], cut))
        if nwords(prose_lines(intro_c)) < 250:    # PDF conversions turn figure-axis debris into headings that cut the Introduction short: run on to the next recognised section instead
            nxt = [s for cn, t, s, e in top if cn not in (None, "intro", "abstract", "backmatter") and s > it[0]]
            intro_c = seg(it[0], min(min(nxt) if nxt else it[1], it[0] + 20000, cut))
        text_stats(prose_lines(intro_c), "intro_", res)
        items = first_list(intro_c)
        if items:
            res["contrib_n"] = len(items); res["contrib_numbers_max"] = max(count_numbers(x) for x in items); res["contrib_words_max"] = max(nwords(x) for x in items)
    elif family == "nature" and starts and s0 > ab_end:     # Nature has no Introduction heading: the unlabelled text between the abstract and the first section is the introduction
        intro_c = seg(ab_end, s0)
        if nwords(prose_lines(intro_c)) >= 200: text_stats(prose_lines(intro_c), "intro_", res)
    lo = ln(min(s0, ab_span[0]) if ab_span else s0); hi = ln(cut) if cut < len(body) else NL
    cleaned = "\n".join(cl_lines)
    res["process"] = process_hits(cleaned, lo, hi)
    spans = [(ln(s), ln(e)) for lv, t, s, e in hs if sc.canon(t) in ("intro", "related") and s < cut]
    res["catalogue"] = catalogue_paragraphs(cleaned, spans)
    return res

# ------------------------------------------------------------------ norms
def load_norms(path=NORMS_CSV):
    rows = []
    if os.path.exists(path):
        txt = "\n".join(l for l in io.open(path, encoding="utf-8-sig").read().splitlines() if not l.startswith("#"))
        rows = list(csv.DictReader(io.StringIO(txt)))
    return {(r["family"], r["metric"]): (float(r["p50"]), float(r["p90"]), float(r["p95"]), int(float(r["n"]))) for r in rows}

def check(a):
    import yaml
    root = os.path.abspath(a.project); sp = os.path.join(root, a.state)
    st = yaml.safe_load(io.open(sp, encoding="utf-8")) if os.path.exists(sp) else {}; st = st or {}
    fam, why = (a.family, "--family") if a.family else sc.infer_family(st)
    mp = os.path.join(root, a.manuscript)
    if not os.path.exists(mp): say("FAIL", f"{a.manuscript} 不存在"); return
    res = analyze(io.open(mp, encoding="utf-8").read(), st.get("acronym_ok") or [], fam)
    norms = load_norms(a.norms); fam_norms = {m: norms[(fam, m)] for m in METRICS if (fam, m) in norms}
    calibrated = bool(fam_norms)
    if not calibrated: say("WARN", f"未校准：{a.norms} 没有 {fam} 的行，用内置 PROVISIONAL 阈值（跑 `readability_check.py calibrate` 生成）")
    print(f"family = {fam}（来源 {why}）；正文 ≈ {res.get('body_words', 0)} 词；引言 {'有' if res.get('has_intro') else '无'}")
    if not res.get("has_intro"): say("WARN", "找不到 Introduction 节：正文区间退化为摘要之后，引言与贡献列表指标跳过")
    over = []   # metrics above p95: one alone is normal (24–28 of 40 published papers per family exceed none, 7–12 exceed one), ≥ MAX_OVER together is not (2/40)
    for m in METRICS:
        if m not in res: continue
        v = res[m]
        if m in fam_norms: p50, p90, p95, n = fam_norms[m]; p90, p95 = max(p90, FLOOR.get(m, (0, 0))[0]), max(p95, FLOOR.get(m, (0, 0))[1]); ref = f"p50 {p50:.3g} / p90 {p90:.3g} / p95 {p95:.3g}，{fam} 已发表 n={n}"
        else: p90, p95 = PROVISIONAL[m]; ref = f"p90 {p90} / p95 {p95}（PROVISIONAL）"
        st_ = "FAIL" if v > p95 else ("WARN" if v > p90 else "PASS")
        hint = {"FAIL": "超过已发表论文 95 分位", "WARN": "超过 90 分位", "PASS": ""}[st_]
        if st_ == "FAIL" and m.startswith(("body_", "intro_")) and res.get("body_words", 0) < a.min_words: st_ = "WARN"; hint += f"（正文仅 {res.get('body_words', 0)} 词 < {a.min_words}，比率不稳，只警告）"
        if st_ == "FAIL" and m != "contrib_numbers_max": over.append(m); st_ = "WARN"   # > 2 numbers per contribution bullet stays a hard rule (P6)
        say(st_, f"{m} = {v:.3g}（{ref}）{hint}")
    if len(over) >= MAX_OVER: say("FAIL", f"{len(over)} 项指标同时超过已发表论文 95 分位（{', '.join(over)}）—— 已发表样本里同时超 ≥{MAX_OVER} 项的只有 2/40")
    elif over: say("PASS", f"{len(over)} 项指标超过 95 分位（单项超标在已发表论文里常见，≥{MAX_OVER} 项才判 FAIL）")
    if "contrib_numbers_max" not in res and res.get("has_intro") and fam != "nature":
        say("WARN", "引言里没找到贡献列表（≥2 条项目符号 / 编号），贡献条目的数字与字数没有检查")
    ph = res["process"]
    if len(ph) > 3: say("FAIL", f"正文出现 {len(ph)} 处流程簿记词（preregistered / registered X / refuted / addendum / locked / G6c / F29 …），前 5 处: " + "; ".join(f"L{l} {n}「{t}」" for l, n, t in ph[:5]) + " —— 协议记账移到 Protocol / Preregistration 附录，正文只陈述结果")
    elif ph: say("WARN", f"正文出现 {len(ph)} 处流程簿记词: " + "; ".join(f"L{l} {n}「{t}」" for l, n, t in ph) + " —— 移到 Protocol / Preregistration 附录")
    else: say("PASS", "正文没有流程簿记词")
    cat = res["catalogue"]
    if len(cat) >= 3: say("FAIL", f"引言 / 相关工作有 {len(cat)} 个目录式段落（引用密集 + 分号串联，或连续 'Name [n] 做了…'），行 {cat[:8]} —— 改成 主题句 → 证据 → 对比 → 判断")
    elif cat: say("WARN", f"引言 / 相关工作有 {len(cat)} 个目录式段落，行 {cat} —— 改成 主题句 → 证据 → 对比 → 判断")
    else: say("PASS", "引言 / 相关工作没有目录式段落")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); return FAILS

# ------------------------------------------------------------------ calibrate
FAMILIES = {"cs_conf": ["CVPR", "ICCV", "ECCV", "NeurIPS", "MICCAI", "WACV", "AAAI"], "cs_journal": ["TMI", "MedIA", "TIP", "TPAMI", "IJCV"]}

def list_candidates(corpus, fam, min_year):
    out = []
    if fam == "nature":
        meta = {}
        mp = os.path.join(corpus, "nature", "metadata", "journals.csv")
        if os.path.exists(mp):
            for r in csv.DictReader(io.open(mp, encoding="utf-8-sig")): meta[r["openalex_id"]] = (r.get("type", ""), r.get("field", ""))
        base = os.path.join(corpus, "nature")
        for j in sorted(d for d in os.listdir(base) if d != "metadata" and os.path.isdir(os.path.join(base, d))):
            for y in sorted(os.listdir(os.path.join(base, j))):
                if not (y.isdigit() and int(y) >= min_year): continue
                for f in sorted(os.listdir(os.path.join(base, j, y))):
                    wid = os.path.splitext(f)[0]
                    if f.lower().endswith(".pdf") and (not meta or meta.get(wid, ("article", ""))[0] == "article"): out.append((os.path.join(base, j, y, f), j, meta.get(wid, ("", ""))[1]))
    else:
        for v in FAMILIES[fam]:
            vd = os.path.join(corpus, v)
            if not os.path.isdir(vd): continue
            for y in sorted(os.listdir(vd)):
                if not (y.isdigit() and int(y) >= min_year): continue
                out += [(os.path.join(vd, y, f), v, "") for f in sorted(os.listdir(os.path.join(vd, y))) if f.lower().endswith(".pdf")]
    return out

def pct(xs, q):
    xs = sorted(xs); k = (len(xs) - 1) * q; f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def calibrate(a):
    rng = random.Random(a.seed); work = os.path.abspath(a.work); os.makedirs(work, exist_ok=True)
    allrows, per = [], {}
    for fam in ("cs_conf", "cs_journal", "nature"):
        cands = list_candidates(a.corpus, fam, a.min_year); rng.shuffle(cands); got = 0
        print(f"{fam}: {len(cands)} candidates since {a.min_year}")
        for k, (pdf, venue, field) in enumerate(cands):
            if got >= a.n: break
            d = os.path.join(work, f"{fam}_{k:04d}"); mdp = os.path.join(d, "paper", "manuscript.md")
            if not os.path.exists(mdp):
                try: subprocess.run([sys.executable, os.path.join(HERE, "pdf_to_md.py"), pdf, d], capture_output=True, timeout=180)    # own process: a hung PDF costs 3 minutes, not the run
                except Exception as ex: print(f"  skip {os.path.basename(pdf)[:40]}: {ex!r}"); continue
            if not os.path.exists(mdp): print(f"  skip {os.path.basename(pdf)[:40]}: conversion failed"); continue
            md = io.open(mdp, encoding="utf-8").read(); r = analyze(md, [], fam)
            if "abstract_words" not in r or r.get("body_words", 0) < 1500 or (fam != "nature" and not r["has_intro"]) or (fam != "nature" and "intro_words" not in r): print(f"  skip {os.path.basename(pdf)[:40]}: no Abstract/Introduction/body parsed"); continue
            got += 1; per.setdefault(fam, []).append(r)
            allrows.append({"family": fam, "venue": venue, "field": field, "pdf": os.path.relpath(pdf, a.corpus).replace("\\", "/"), **{m: round(r[m], 4) for m in METRICS if m in r}, "process": len(r["process"]), "catalogue": len(r["catalogue"])})
        print(f"  accepted {got}")
    out_rows = []
    for fam, rs in per.items():
        for m in METRICS:
            xs = [r[m] for r in rs if m in r]
            if len(xs) >= 8: out_rows.append({"family": fam, "metric": m, "p50": round(pct(xs, .5), 4), "p90": round(pct(xs, .9), 4), "p95": round(pct(xs, .95), 4), "n": len(xs)})
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# readability norms: {datetime.date.today().isoformat()}, seed {a.seed}, <= {a.n} papers per family (published {a.min_year}+), converted with pdf_to_md.py; regenerate: readability_check.py calibrate\n")
        f.write("# n per row = papers where the metric exists (contrib_* needs a bullet list that survived PDF conversion; Nature has no Introduction heading)\n")
        w = csv.DictWriter(f, fieldnames=["family", "metric", "p50", "p90", "p95", "n"], lineterminator="\n"); w.writeheader(); w.writerows(out_rows)
    pp = os.path.join(work, "papers.csv")
    with io.open(pp, "w", encoding="utf-8", newline="") as f:
        cols = ["family", "venue", "field", "pdf"] + METRICS + ["process", "catalogue"]; w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(allrows)
    # the corpus judged by its own norms: per-metric FAIL (> p95) and WARN (> p90) rates
    norms = {(r["family"], r["metric"]): r for r in out_rows}; print(f"\nnorms -> {a.out}; per-paper measurements -> {pp}\nfamily metric: FAIL%/WARN% of the sampled papers against their own norms")
    for fam, rs in per.items():
        anyf = sum(1 for r in rs if any(m in r and (fam, m) in norms and r[m] > norms[(fam, m)]["p95"] for m in METRICS)); procf = sum(1 for r in rs if len(r["process"]) > 3); catf = sum(1 for r in rs if len(r["catalogue"]) >= 3)
        print(f"  {fam}: n={len(rs)}; any-metric FAIL {anyf}/{len(rs)}; process-vocab FAIL {procf}/{len(rs)}; catalogue FAIL {catf}/{len(rs)}")
    return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["check", "calibrate"], default="check")
    ap.add_argument("--project", default="."); ap.add_argument("--manuscript", default="paper/manuscript.md"); ap.add_argument("--state", default="research-state.yaml"); ap.add_argument("--family", default="")
    ap.add_argument("--norms", default=NORMS_CSV); ap.add_argument("--min-words", type=int, default=1500, help="below this many body words the per-1k / sentence metrics can only WARN (a stub or fixture has too few sentences for rates)")
    ap.add_argument("--corpus", default="Z:/LDCT/papers"); ap.add_argument("--work", default="readability_corpus"); ap.add_argument("--n", type=int, default=40); ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--min-year", type=int, default=2023); ap.add_argument("--out", default=NORMS_CSV)
    a = ap.parse_args()
    if a.cmd == "calibrate": sys.exit(calibrate(a))
    check(a); sys.exit(1 if FAILS else 0)

if __name__ == "__main__":
    main()
