# -*- coding: utf-8 -*-
"""Per-venue manuscript SHAPE (what sections, in what order, how long) from published PDFs — the data behind venue-profiles.md.
   python venue_shape.py <corpus_dir> <out_csv>       corpus_dir/<venue>/*.pdf  (same layout as venue_norms.py)
Per paper: top-level section sequence (normalised), words in abstract / intro / methods / results / discussion / conclusion,
           share of body words per section, methods-after-results (Nature order), intro has subsections, results subheads are
           sentences (claim-style, Nature), contribution bullets, related-work section, limitation section, teaser figure on p1,
           display items (Fig+Table captions), supplementary / extended-data mentions, first-person 'we' density, equation count.
Aggregates by venue -> markdown table + csv next to out_csv. Text layer only; Nature two-column PDFs are parsed per page."""
import sys, os, re, glob, csv, io, statistics, collections
import fitz

CANON = [  # (regex on heading line, canonical name)
    (r"^abstract\b", "abstract"), (r"^(\d+\.?\s*)?introduction\b", "intro"), (r"^(\d+\.?\s*)?(related work|background|prior work|preliminar)", "related"),
    (r"^(\d+\.?\s*)?(method|methods|methodology|approach|proposed|our (method|approach|framework)|model|the .{0,30}(framework|method|model|architecture))\b", "method"),
    (r"^(\d+\.?\s*)?(problem (formulation|statement|setup|definition)|preliminaries|notation)", "problem"),
    (r"^(\d+\.?\s*)?(experiment|experimental|results|evaluation|empirical)", "results"),
    (r"^(\d+\.?\s*)?(discussion)", "discussion"), (r"^(\d+\.?\s*)?(limitation)", "limitations"), (r"^(\d+\.?\s*)?(conclusion|concluding|summary)", "conclusion"),
    (r"^(\d+\.?\s*)?(broader impact|societal|ethic|impact statement)", "impact"), (r"^(\d+\.?\s*)?(acknowledg)", "ack"), (r"^(\d+\.?\s*)?(references|bibliography)", "refs"),
    (r"^(data availability|code availability|availability)", "availability"), (r"^(author contributions|competing interests|additional information|online content|reporting summary|extended data)", "backmatter"),
    (r"^(\d+\.?\s*)?(ablation)", "ablation"), (r"^(supplementary|appendix)", "supp"),
]

def heading_lines(pages):
    """candidate top-level headings: short lines, Title-case or ALLCAPS or numbered, from the page text layer."""
    out = []
    for pi, txt in enumerate(pages):
        for ln in txt.splitlines():
            s = ln.strip()
            if not (2 <= len(s) <= 70): continue
            if re.search(r"[.;:,]$", s) and not re.match(r"^\d+(\.\d+)*\.?\s", s): continue
            if re.match(r"^(\d{1,2}\.?\s+[A-Z][A-Za-z\- ]{2,60}|[A-Z][A-Za-z\- ]{2,40}|[A-Z][A-Z \-]{3,40})$", s):
                out.append((pi, s))
    return out

def canon(h):
    hl = h.lower().strip()
    for pat, name in CANON:
        if re.search(pat, hl): return name
    return None

def analyze(pdf):
    try: d = fitz.open(pdf)
    except Exception: return None
    pages = [p.get_text() for p in d]; full = "\n".join(pages)
    if len(full) < 3000: return None
    r = {"paper": os.path.splitext(os.path.basename(pdf))[0][:50], "pages": len(d)}
    # section sequence with char offsets
    seq = []; pos = 0; offs = []
    for pi, h in heading_lines(pages):
        c = canon(h)
        if c and (not seq or seq[-1] != c):
            # offset of this heading in full text
            k = full.find(h, pos)
            if k < 0: continue
            seq.append(c); offs.append(k); pos = k + len(h)
    # cut at refs
    if "refs" in seq:
        i = seq.index("refs"); body_end = offs[i]
    else: body_end = len(full)
    r["sequence"] = ">".join(s for s in seq if s not in ("ack", "refs", "backmatter", "availability", "supp"))
    # words per section (first occurrence of each canonical, up to next canonical)
    words = {}
    for i, (s, o) in enumerate(zip(seq, offs)):
        if s in words: continue
        e = offs[i + 1] if i + 1 < len(offs) else body_end
        words[s] = len(re.findall(r"\b[A-Za-z][A-Za-z\-']+\b", full[o:min(e, body_end)]))
    body_words = max(1, sum(v for k, v in words.items() if k not in ("abstract", "ack", "refs", "backmatter", "availability", "supp")))
    for s in ("abstract", "intro", "related", "method", "results", "discussion", "conclusion", "limitations"):
        r[f"w_{s}"] = words.get(s, "")
        r[f"share_{s}"] = round(words[s] / body_words, 2) if s in words and s != "abstract" else ""
    r["body_words"] = body_words
    # order features
    if "method" in seq and "results" in seq: r["methods_after_results"] = int(seq.index("method") > seq.index("results"))
    else: r["methods_after_results"] = ""
    r["has_related"] = int("related" in seq); r["has_discussion"] = int("discussion" in seq); r["has_limitations"] = int("limitations" in seq or bool(re.search(r"\n\s*(\d+(\.\d+)*\s+)?limitations?\b", full[:body_end], re.I)))
    r["has_conclusion"] = int("conclusion" in seq); r["has_problem_section"] = int("problem" in seq); r["has_impact"] = int("impact" in seq)
    r["has_ablation_section"] = int("ablation" in seq or bool(re.search(r"\n\s*\d+(\.\d+)*\s+ablation", full[:body_end], re.I)))
    # intro: numbered subsections? contribution bullets?
    intro_txt = ""
    if "intro" in seq:
        i = seq.index("intro"); intro_txt = full[offs[i]:(offs[i + 1] if i + 1 < len(offs) else body_end)]
    r["intro_paragraphs"] = len([p for p in re.split(r"\n\s*\n", intro_txt) if len(p.split()) > 25]) if intro_txt else ""
    cm = re.search(r"contributions?\s+(of this (paper|work)\s+)?(are|can be|is|include)[^\n]{0,80}", intro_txt, re.I)
    r["contrib_bullets"] = len(re.findall(r"(?:^|\n)\s*(?:•|–|-|\*|\(\d\)|\d\)|\(?[ivx]+\)|\d\.)\s", intro_txt[cm.end():cm.end() + 2500])) if cm else 0
    r["intro_has_contrib_list"] = int(bool(cm))
    # results subheads claim-style (Nature): sentence-like subheads with a verb, ≥6 words
    res_txt = ""
    if "results" in seq:
        i = seq.index("results"); res_txt = full[offs[i]:(offs[i + 1] if i + 1 < len(offs) else body_end)]
    subs = [ln.strip() for ln in res_txt.splitlines() if 6 <= len(ln.split()) <= 18 and not ln.strip().endswith((".", ",", ";")) and re.match(r"^[A-Z]", ln.strip()) and not re.search(r"\d\.\d", ln)]
    claim_like = [s for s in subs if re.search(r"\b(is|are|does|do|improves?|reduces?|predicts?|reveals?|enables?|outperforms?|generali[sz]es?|captures?|shows?|requires?|depends?|fails?|transfers?|identifies|recovers?)\b", s)]
    r["results_claim_subheads"] = len(claim_like)
    # display items & supplementary
    r["fig_captions"] = len(set(re.findall(r"(?:^|\n)\s*(?:Fig\.|Figure)\s*(\d+)\s*[|.:]", full[:body_end])))
    r["table_captions"] = len(set(re.findall(r"(?:^|\n)\s*(?:Table|TABLE)\s*(\d+)\s*[|.:]", full[:body_end])))
    r["mentions_supp"] = int(bool(re.search(r"supplementary (fig|table|note|information|material)|extended data|appendix", full, re.I)))
    r["teaser_fig_p1"] = int(bool(re.search(r"(Fig\.|Figure)\s*1\s*[|.:]", pages[0]))) if pages else 0
    r["equations"] = len(re.findall(r"\(\s*\d{1,2}\s*\)\s*$", full[:body_end], re.M))
    r["we_per_1k"] = round(1000 * len(re.findall(r"\bwe\b", full[:body_end], re.I)) / body_words, 1)
    r["sota_word"] = int("state-of-the-art" in full.lower() or "state of the art" in full.lower())
    return r

def main(corpus, out_csv):
    rows = []
    for pdf in sorted(glob.glob(os.path.join(corpus, "*", "*.pdf"))):
        r = analyze(pdf)
        if r: r["venue"] = os.path.basename(os.path.dirname(pdf)); rows.append(r); print(f"{r['venue']:10s} {r['paper'][:34]:34s} {r['sequence'][:70]}")
    keys = ["venue", "paper", "pages", "sequence", "body_words", "w_abstract", "w_intro", "w_related", "w_method", "w_results", "w_discussion", "w_conclusion", "w_limitations",
            "share_intro", "share_related", "share_method", "share_results", "share_discussion", "share_conclusion", "methods_after_results", "has_related", "has_problem_section", "has_discussion",
            "has_limitations", "has_conclusion", "has_impact", "has_ablation_section", "intro_paragraphs", "intro_has_contrib_list", "contrib_bullets", "results_claim_subheads", "fig_captions", "table_captions",
            "mentions_supp", "teaser_fig_p1", "equations", "we_per_1k", "sota_word"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in keys})
    by = collections.defaultdict(list)
    for r in rows: by[r["venue"]].append(r)
    def med(v, k):
        xs = [float(r[k]) for r in v if r.get(k) not in ("", None)]
        return f"{statistics.median(xs):.0f}" if xs else "-"
    def medf(v, k):
        xs = [float(r[k]) for r in v if r.get(k) not in ("", None)]
        return f"{statistics.median(xs):.0%}" if xs else "-"
    def pct(v, k):
        xs = [int(r[k]) for r in v if r.get(k) not in ("", None)]
        return f"{100*sum(xs)/len(xs):.0f}%" if xs else "-"
    def topseq(v):
        c = collections.Counter(r["sequence"] for r in v if r["sequence"]); s, n = c.most_common(1)[0] if c else ("-", 0); return f"{s} ({n}/{len(v)})"
    L = ["| venue | n | 页 | 正文词 | 摘要词 | 引言词 | 引言占比 | 相关工作 | 方法占比 | 结果占比 | 讨论节 | 讨论占比 | 局限节 | 结论节 | 方法在结果后 | 引言有贡献列表 | 贡献条数 | 结果小标题为句子 | 图 | 表 | 公式 | we/千词 | 补充材料 | SOTA 词 |", "|---|" + "---|" * 23]
    for v in sorted(by):
        x = by[v]
        L.append(f"| {v} | {len(x)} | {med(x,'pages')} | {med(x,'body_words')} | {med(x,'w_abstract')} | {med(x,'w_intro')} | {medf(x,'share_intro')} | {pct(x,'has_related')} | {medf(x,'share_method')} | {medf(x,'share_results')} | {pct(x,'has_discussion')} | {medf(x,'share_discussion')} | {pct(x,'has_limitations')} | {pct(x,'has_conclusion')} | {pct(x,'methods_after_results')} | {pct(x,'intro_has_contrib_list')} | {med(x,'contrib_bullets')} | {med(x,'results_claim_subheads')} | {med(x,'fig_captions')} | {med(x,'table_captions')} | {med(x,'equations')} | {med(x,'we_per_1k')} | {pct(x,'mentions_supp')} | {pct(x,'sota_word')} |")
    L += ["", "最常见章节序列：", ""] + [f"- {v}: {topseq(by[v])}" for v in sorted(by)]
    io.open(os.path.splitext(out_csv)[0] + ".md", "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus_dir", help="corpus_dir/<venue>/*.pdf"); ap.add_argument("out_csv")
    a = ap.parse_args(); main(a.corpus_dir, a.out_csv)
