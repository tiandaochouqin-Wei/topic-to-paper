# -*- coding: utf-8 -*-
"""G6c — manuscript shape vs. the target family's writing profile (references/venue-profiles.md). Run by Claude.

  python shape_check.py [--project .] [--manuscript paper/manuscript.md] [--state research-state.yaml] [--family cs_conf|cs_journal|nature]

Family comes from state.target.family, else inferred from state.target.venue (Nature/Science/npj/Sci Adv -> nature; CVPR/NeurIPS/ICML/ICLR/AAAI/MICCAI/ECCV/ICCV -> cs_conf; else cs_journal).
Checks are the five-to-eight mechanical signatures that separate the families in 275 published papers:
  nature   : order Results > Discussion > Methods; no Related Work / Conclusion headings; no contribution list; abstract ≤150 words one paragraph no citations;
             Results subheadings are sentences (≥3 with a verb); no numbered equations in Intro/Results/Discussion; no "state-of-the-art"; no "ablation" word in main text
             (WARN); Discussion ≥ 12 % of body; every comparison paragraph in Results carries a statistic (p / CI / n=) — WARN if < 50 %; "we" ≤ 12 per 1k words (WARN)
  cs_conf  : order Intro > (Related) > Method > Experiments > Conclusion; contribution list 3–5 items in Intro; Experiments has an Ablation subsection; ≥3 numbered
             equations in Method; abstract 120–220 words; intro ≤ 25 % of body; Conclusion present
  cs_journal: as cs_conf plus Related Work section present (WARN if absent), abstract ≤ 250 words, Discussion/Limitations subsection present (WARN), ≥5 equations (WARN)
Common: body-word count vs. family median ±60 % (WARN); reference count vs. state.target.ref_max.
Exit = #FAIL.
"""
import argparse, io, os, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] shape: {msg}")

NATURE_RE = re.compile(r"nature|science|npj|sci\.?\s*adv|cell\b|lancet|nejm|jama|bmj", re.I)
CONF_RE = re.compile(r"cvpr|neurips|nips|icml|iclr|aaai|ijcai|miccai|eccv|iccv|acl\b|emnlp|kdd|www\b|sigir|interspeech|ismir|corl|icra|iros|rss\b", re.I)
MEDIAN_BODY = {"cs_conf": 3600, "cs_journal": 4650, "nature": 5000}

def infer_family(st):
    t = (st.get("target") or {}); f = (t.get("family") or "").strip().lower()
    if f in MEDIAN_BODY: return f, "state.target.family"
    v = t.get("venue") or ""
    if NATURE_RE.search(v): return "nature", f"venue '{v}'"
    if CONF_RE.search(v): return "cs_conf", f"venue '{v}'"
    return "cs_journal", f"venue '{v}' (default)"

def headings(md):
    """[(level, title, start, end)] for #/##/### headings, body up to References."""
    body = md.split("\n## References")[0]
    # IEEE two-column PDFs: "Abstract—…" sits inline on page 1, often AFTER the intro heading line was pulled up; move it in front.
    m_ab = re.search(r"^Abstract\s*[—–-]\s*(.+?)(?=\n\s*\n)", body, re.M | re.S)
    if m_ab and not re.search(r"^## Abstract", body, re.M):
        body = body[:m_ab.start()] + body[m_ab.end():]
        first_h = re.search(r"^(?:#{1,3}\s+|\d{1,2}\.?\s+|[IVX]{1,4}\.\s+)?(Introduction|INTRODUCTION)\s*$", body, re.M)
        ins = first_h.start() if first_h else 0
        body = body[:ins] + "## Abstract\n\n" + m_ab.group(1).strip() + "\n\n" + body[ins:]
    hs = [(len(m.group(1)), m.group(2).strip(), m.start()) for m in re.finditer(r"^(#{1,3})\s+(.+?)\s*$", body, re.M)]
    # PDF-converted manuscripts keep headings as bare lines: "1. Introduction", "3.1. Shape …", "II. RELATED WORK", or just "Introduction"
    for m in re.finditer(r"^(?:(\d{1,2})\.?|([IVX]{1,4})\.)\s+([A-Z][^\n]{2,70}?)\s*$", body, re.M):
        t = m.group(3)
        if re.search(r"[.;,]$", t) or len(t.split()) > 10: continue
        hs.append((2, t, m.start()))
    for m in re.finditer(r"^(\d{1,2}\.\d{1,2})\.?\s+([A-Z][^\n]{2,70}?)\s*$", body, re.M):
        if len(m.group(2).split()) <= 12: hs.append((3, m.group(2), m.start()))
    for m in re.finditer(r"^(Introduction|Related Work|Background|Methods?|Methodology|Approach|Experiments?|Results?|Discussion|Limitations?|Conclusions?|Ablation Stud(?:y|ies))\s*$", body, re.M | re.I):
        hs.append((2, m.group(1), m.start()))
    hs.sort(key=lambda x: x[2])
    out = []
    for i, (lv, t, s) in enumerate(hs):
        e = next((hs[j][2] for j in range(i + 1, len(hs)) if hs[j][0] <= lv), len(body))
        out.append((lv, t, s, e))
    return body, out

def canon(title):
    t = re.sub(r"^\d+(\.\d+)*\.?\s*", "", title).lower()
    for pat, name in [(r"^abstract", "abstract"), (r"introduction", "intro"), (r"related work|background|prior work", "related"), (r"^(method|methods|methodology|approach|proposed)", "method"),
                      (r"experiment|^results?\b|evaluation", "results"), (r"^discussion", "discussion"), (r"limitation", "limitations"), (r"^conclusion|concluding", "conclusion"), (r"ablation", "ablation"),
                      (r"highlights", "highlights"), (r"data availability|code availability|acknowledg|author contribution|competing|credit|declaration|funding", "backmatter")]:
        if re.search(pat, t): return name
    return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", default="."); ap.add_argument("--manuscript", default="paper/manuscript.md"); ap.add_argument("--state", default="research-state.yaml"); ap.add_argument("--family", default="")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    import yaml
    sp = os.path.join(root, a.state); st = yaml.safe_load(io.open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    fam, why = (a.family, "--family") if a.family else infer_family(st or {})
    mp = os.path.join(root, a.manuscript)
    if not os.path.exists(mp): say("FAIL", f"{a.manuscript} 不存在"); sys.exit(1)
    md = io.open(mp, encoding="utf-8").read(); md = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith(">"))
    body, hs = headings(md)
    top = [(canon(t), t, s, e) for lv, t, s, e in hs if lv <= 2]
    seq = [c for c, *_ in top if c and c not in ("abstract", "highlights", "backmatter")]
    def sec(name):
        """longest body among headings that canonicalise to `name` (PDF conversions leave spurious short duplicates, e.g. a running header)."""
        cands = [body[s:e] for c, t, s, e in top if c == name] + [body[s:e] for lv, t, s, e in hs if canon(t) == name]
        return max(cands, key=len) if cands else ""
    words = lambda s: len(re.findall(r"\b[A-Za-z][A-Za-z\-']+\b", s))
    prose = body[(top[0][2] if top else 0):]; bw = max(1, words(prose) - words(sec("abstract")))
    print(f"family = {fam}（来源 {why}）；章节序列 {seq}；正文 ≈ {bw} 词")
    ab = sec("abstract"); ab_paras = [p for p in re.split(r"\n\s*\n", re.sub(r"^#.*$", "", ab, flags=re.M).strip()) if p.strip() and not re.match(r"^(subject terms|keywords?|index terms)", p.strip(), re.I)]
    ab = ab_paras[0] if ab_paras else ""; abw = words(ab)    # first paragraph only: JATS appends "Subject terms" and the editor summary
    we_per_1k = 1000 * len(re.findall(r"\bwe\b", prose, re.I)) / bw
    n_eq_intro_res = len(re.findall(r"\(\s*\d{1,2}\s*\)\s*$", sec("intro") + sec("results") + sec("discussion"), re.M)) + len(re.findall(r"^\$\$|\\begin\{equation\}", sec("intro") + sec("results") + sec("discussion"), re.M))
    n_eq_method = len(re.findall(r"\(\s*\d{1,2}\s*\)\s*$|^\$\$|\\begin\{equation\}|\\tag\{", sec("method"), re.M))
    sota = len(re.findall(r"state[- ]of[- ]the[- ]art", prose, re.I)); abl_word = len(re.findall(r"\bablat", prose, re.I))
    contrib = re.search(r"contributions?\s+(of this (paper|work)\s+)?(are|can be|is|include|lie)|contributions?\s+(are|can be)\s+(summari[sz]ed|categori[sz]ed|listed|threefold|twofold|fourfold)|(three|four|two)[- ]?fold", sec("intro"), re.I)
    contrib_n = len(re.findall(r"^\s*(?:\d+[.)]|[-*•▪–]|\(\d\)|\(?[ivx]+\))\s+", sec("intro")[contrib.end():contrib.end() + 3500], re.M)) if contrib else 0
    if contrib and contrib_n == 0:   # PDF conversion dropped bullets: count "We propose/develop/…" sentence starts after the cue instead
        contrib_n = len(re.findall(r"(?:^|\.\s+)(?:We|Our)\s+(?:propose|present|develop|introduce|design|extend|show|demonstrate|provide|derive|conduct|establish)", sec("intro")[contrib.end():contrib.end() + 3500]))
    res = sec("results"); res_subs = [t for lv, t, s, e in hs if lv == 3 and s >= (next((s2 for c, t2, s2, e2 in top if c == "results"), -1)) and s < (next((e2 for c, t2, s2, e2 in top if c == "results"), -1))]
    claim_subs = [t for t in res_subs if len(t.split()) >= 5 and re.search(r"\b(is|are|does|do|improves?|reduces?|predicts?|reveals?|enables?|outperforms?|generali[sz]es?|captures?|shows?|requires?|depends?|fails?|transfers?|identifies|recovers?|has|have|holds?|collapses?|needs?|cannot|remains?)\b", t, re.I)]
    stat_paras = [p for p in re.split(r"\n\s*\n", res) if words(p) > 40 and re.search(r"\d", p)]
    with_stat = [p for p in stat_paras if re.search(r"\bp\s*[<=>]\s*0?\.\d|95\s*%\s*CI|confidence interval|\bn\s*=\s*\d|±|\bs\.d\.|\bs\.e\.m|seeds?\b", p, re.I)]
    disc = sec("discussion"); disc_share = words(disc) / bw if disc else 0.0
    intro_share = words(sec("intro")) / bw if sec("intro") else 0.0
    if fam == "nature":
        order_ok = "results" in seq and "discussion" in seq and "method" in seq and seq.index("results") < seq.index("discussion") < seq.index("method")
        say("PASS" if order_ok else "FAIL", f"章节顺序 Results → Discussion → Methods：{seq}")
        for bad in ("related", "conclusion"):
            if bad in seq: say("FAIL", f"Nature 稿不设 {bad} 节（相关工作融进引言，结论融进 Discussion 末段）")
        if contrib: say("FAIL", "引言有 contributions 列表：Nature 稿末段用一句 'Here we show …' 代替")
        if not re.search(r"\bHere,?\s+we\s+(show|report|present|demonstrate|develop|introduce|propose|describe|find|establish)", sec("intro") or prose[:6000], re.I): say("WARN", "引言末段没有 'Here we show/report …' 句")
        ab_lim = ((st or {}).get("target") or {}).get("abstract_word_limit") or 150
        if abw > ab_lim * 1.6: say("FAIL", f"摘要 {abw} 词 > {ab_lim}×1.6（已发表 Nature 系摘要中位 150–230，超 1.6 倍必被退改）")
        elif abw > ab_lim * 1.03: say("WARN", f"摘要 {abw} 词 > 投稿限 {ab_lim}（已发表稿常超，投稿时按 guide 压）")
        if ab and re.search(r"\[\d+\]|\\cite", ab): say("FAIL", "摘要不含引用")
        if len([p for p in ab_paras if words(p) > 40]) > 1: say("WARN", f"摘要节有 {len(ab_paras)} 段：Nature 摘要一段（JATS 的编辑摘要已剔除后仍多段则改）")
        say("PASS" if len(claim_subs) >= 2 else "WARN", f"Results 句式小标题 {len(claim_subs)}/{len(res_subs)}（Nat Commun/BME 中位 5，Nat Med 用名词短语；≥2 为佳，小标题 = 主张句）")
        if n_eq_intro_res: say("FAIL", f"引言/结果/讨论里有 {n_eq_intro_res} 个编号公式：Nature 正文不放公式，移到 Methods 或 SI")
        if sota: say("WARN", f"'state-of-the-art' 出现 {sota} 次（Nature 系 20% 用；每处回表确认作用域，scope 关口照查）")
        if abl_word: say("WARN", f"'ablation' 出现 {abl_word} 次（Nature 系 10%；写成 control experiments）")
        say("PASS" if disc_share >= 0.12 else ("WARN" if disc_share >= 0.06 else "FAIL"), f"Discussion 占正文 {disc_share:.0%}（Nature 中位 18%；<6% FAIL，<12% WARN）")
        if stat_paras: say("PASS" if len(with_stat) / len(stat_paras) >= 0.5 else "WARN", f"Results 含数字段落中带统计（p/CI/n=/±）的 {len(with_stat)}/{len(stat_paras)}")
        if we_per_1k > 12: say("WARN", f"'we' {we_per_1k:.0f}/千词（Nature 中位 9；多用 'Here we' 与被动）")
        if "limitations" not in seq and not re.search(r"limitation", disc, re.I): say("WARN", "Discussion 里没有 limitation 字样")
    else:
        need = ["intro", "method", "results", "conclusion"]
        miss = [n for n in need if n not in seq]
        hard = [n for n in miss if n in ("intro", "results")]; soft = [n for n in miss if n not in hard]
        if hard: say("FAIL", f"缺章节 {hard}（CS 稿：Intro → Related → Method → Experiments → Conclusion）")
        if soft: say("WARN", f"缺章节 {soft}（理论稿可按内容命名方法节，但 Conclusion 87% 有）")
        idx = {n: seq.index(n) for n in need if n in seq}
        if len(idx) == 4 and not (idx["intro"] < idx["method"] < idx["results"] < idx["conclusion"]): say("FAIL", f"章节顺序异常 {seq}")
        elif not miss: say("PASS", f"章节顺序 {seq}")
        if contrib and contrib_n == 0: say("WARN", "引言有 contributions 句但未识别到条目（PDF 转换会丢项目符；作者稿须 3–5 条）")
        else: say("PASS" if 3 <= contrib_n <= 5 else "FAIL", f"引言贡献条目 {contrib_n}（CS 稿 3–5 条，每条对应 claims.csv 一行）")
        has_abl_head = "ablation" in [canon(t) for lv, t, s, e in hs] or bool(re.search(r"^#{2,4}\s*\d*\.?\d*\s*.*ablation", body, re.I | re.M))
        has_abl_prose = bool(re.search(r"ablation stud", res + sec("results"), re.I))
        say("PASS" if has_abl_head else ("WARN" if has_abl_prose else "FAIL"), "实验节有 Ablation 小节" if has_abl_head else ("实验节正文有 ablation study 但无独立小节" if has_abl_prose else "实验节无 Ablation（CS 期刊 78%、会议 63% 有）"))
        say("PASS" if n_eq_method >= 3 else "WARN", f"方法节编号公式 {n_eq_method}（会议中位 6、期刊 14；PDF 转换可能丢编号）")
        lim = ((st or {}).get("target") or {}).get("abstract_word_limit") or (250 if fam == "cs_journal" else 220)
        say("PASS" if 120 <= abw <= lim * 1.03 else "FAIL", f"摘要 {abw} 词（{fam} 120–{lim}，+3% 分词容差）")
        say("PASS" if intro_share <= 0.25 else "WARN", f"引言占正文 {intro_share:.0%}（≤25%）")
        if fam == "cs_journal":
            if "related" not in seq: say("WARN", "期刊稿缺 Related Work 节（53% 有，审稿人常要求）")
            if not (sec("limitations") or "discussion" in seq or re.search(r"limitation", sec("results") + sec("conclusion"), re.I)): say("WARN", "无 Discussion/Limitations 子节")
        if fam == "cs_conf" and not re.search(r"limitation", prose, re.I): say("WARN", "无 Limitations 段（NeurIPS 72% 有，checklist 要求）")
    med = MEDIAN_BODY[fam]
    if not (0.4 * med <= bw <= 1.8 * med): say("WARN", f"正文 {bw} 词，{fam} 中位 {med}（±60% 以外）")
    ref_max = ((st or {}).get("target") or {}).get("ref_max")
    nrefs = len(re.findall(r"^\s*\[?\d+\]?[.)]?\s+\S", md.split("\n## References")[-1], re.M)) if "\n## References" in md else None
    if ref_max and nrefs and nrefs > ref_max: say("FAIL", f"参考文献 {nrefs} > ref_max {ref_max}")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
