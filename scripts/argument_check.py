# -*- coding: utf-8 -*-
"""G6g — does the paper tell ONE story: paper/argument.md (written before the draft) versus the manuscript. Run by Claude.

  python argument_check.py [--project .] [--manuscript paper/manuscript.md] [--argument paper/argument.md] [--state research-state.yaml]

Why (diagnosis of three real CVPR drafts, 2026-10-23, references/lessons.md): writing was checklist-driven, not argument-driven. draft_plan turned every gap_map row into
"name <paper> and its failure point" in the Introduction (name-drop catalogue intros of 1000+ words) and forced every claim's numbers into the contribution bullets (4-14 numbers
per bullet). Nothing asked for ONE claim sentence that the title, abstract, end of the Introduction and the Conclusion share, nor for the reader's question the paper answers.
templates/argument.md is that sentence plus its supports; this gate checks that the manuscript follows it. It checks that the paper is CONSISTENT, not that the argument is GOOD:
token overlap cannot tell a weak claim from a strong one (the review seats do that, G7).

argument.md fields (YAML front matter): claim, reader_question, headline {claim_id, number}, why_not_obvious, strongest_objection, where_answered, not_claimed, outline, sections.
  1 FAIL  argument.md missing, or claim / reader_question / headline / why_not_obvious / strongest_objection / outline empty or still the template <placeholder>
  2 WARN  claim > 35 words or > 2 numbers; no comparative / causal verb (nothing that could be false)
  3 FAIL  the claim does not recur (content-word overlap >= 50 %, or every number of the claim in a sentence that shares >= 25 % of its words) in: the abstract (any sentence); the last
          Introduction paragraph before the contribution list (cs) / the "Here we show" sentence (nature); the first two sentences of the Conclusion (cs) / the first Discussion paragraph (nature).
          WARN if the title shares < 2 content words with the claim
  4 FAIL  headline.claim_id is not a row of paper/claims.csv, or a number of headline.number is not in the abstract
  5 WARN  < 40 % of the reader_question's words in the first two Introduction paragraphs
  6 WARN  < 30 % of the why_not_obvious words in the Introduction
  7 WARN  where_answered names no § / Table / Fig that exists, or < 30 % of the strongest_objection words in that place or in Limitations / Discussion
  8 WARN  Introduction paragraph count differs from the outline by more than 1; paragraph i (or i+-1) shares < 35 % of the outline move's words; the moves come in another order
  9 WARN  a not_claimed entry (>= 50 % of its words) does not appear in Limitations / Discussion / Conclusion
 10 WARN  headline.number missing in the Introduction, or a number within 8 % of it that is written differently in the abstract / Introduction (6.95 vs 7.0)
Family (cs_conf | cs_journal | nature) comes from state.target like shape_check.py. Exit = #FAIL."""
import argparse, csv, io, os, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import draft_plan as dp                 # content words, overlap, argument.md loader, paragraph / contribution-block split
import shape_check as sc                # headings / canon / infer_family: the same section parsing as G6c

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] argument: {msg}")

CLAIM_MAX_WORDS, CLAIM_MAX_NUMBERS = 35, 2
VERB = re.compile(r"\b(?:shows?|showed|reduc\w+|improv\w+|fails?|failed|exceed\w*|predict\w*|outperform\w*|remains?|remained|drops?|dropped|collaps\w+|lower\w*|rais\w+|increas\w+|decreas\w+|"
                  r"caus\w+|dominat\w+|explains?|explained|determin\w+|degrad\w+|depends?|dependent|limits?|limited|recover\w*|beats?|exceeds?|cannot|cuts?|halves|doubles|"
                  r"outweigh\w*|underestimat\w+|overestimat\w+|break\w*|hurts?|worsen\w*|erases?|inflates?|biases|accounts?\s+for|driven|explain\w*)\b|降低|提高|导致|失败|优于|下降|恶化|消除|主导", re.I)
HERE_WE = re.compile(r"\bHere,?\s+we\s+(?:show|report|present|demonstrate|develop|introduce|find|establish|propose|describe)\b", re.I)
CONTRIB_ENTRY = re.compile(r"^\s*contributions?\b", re.I)
NUM = re.compile(r"\d+(?:\.\d+)?")

def n_words(s):
    return len(re.findall(r"[A-Za-z0-9][\w\-.%±]*|[一-鿿]", s))

def sentences(text):
    t = " ".join(text.split())
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(\[0-9])|(?<=[。！？])", t) if x.strip()]

def share_n(need, hay):
    """how many content words of `need` occur in `hay` (stem-aware, as draft_plan.stem_overlap)."""
    h = hay.lower()
    return sum(1 for t in dp.cwords(need) if re.search(r"(?<![a-z0-9])" + re.escape(dp._stem(t)), h))

# ------------------------------------------------------------------ manuscript
class Manuscript:
    def __init__(self, md):
        md = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith(">"))      # editing-log quote lines are not prose
        m = re.search(r"^#\s+(.+?)\s*$", md, re.M); self.title = m.group(1) if m else ""
        self.body, self.hs = sc.headings(md)

    def spans(self, name):
        return [(s, e) for lv, t, s, e in self.hs if sc.canon(t) == name]

    def text(self, name):
        """longest section canonicalising to `name`, heading line removed; "" when absent."""
        c = self.spans(name)
        if not c: return ""
        s, e = max(c, key=lambda x: x[1] - x[0])
        return self.body[s:e].split("\n", 1)[1] if "\n" in self.body[s:e] else ""

    def texts(self, *names):
        return "\n\n".join(self.body[s:e].split("\n", 1)[-1] for n in names for s, e in self.spans(n))

    def abstract(self):
        t = self.text("abstract")
        if t.strip():
            ps = [p for p in dp.paragraphs(t) if not re.match(r"^\W*(keywords?|subject terms|index terms)\b", p, re.I)]
            return " ".join(" ".join(ps).split())
        first = min([s for lv, tt, s, e in self.hs if sc.canon(tt) in ("intro", "results", "method", "discussion", "related")] or [len(self.body)])   # Nature PDFs: no Abstract heading
        for p in dp.paragraphs(self.body[:first]):
            if len(p.split()) >= 80 and not p.startswith("**"): return " ".join(p.split())
        return ""

    def intro(self):
        t = self.text("intro")
        if t.strip(): return t
        starts = [s for lv, tt, s, e in self.hs if sc.canon(tt) in ("results", "method", "discussion", "related")]      # Nature: unlabelled text between the abstract and the first section
        if not starts: return ""
        ab = self.spans("abstract"); a0 = max([e for s, e in ab] or [0])
        return self.body[a0:min(starts)] if min(starts) > a0 else ""

    def section_by_number(self, num):
        for lv, t, s, e in self.hs:
            m = re.match(r"(\d+(?:\.\d+)*)\.?\s", t.strip())
            if m and m.group(1) == num: return self.body[s:e]
        return None

    def numbered(self, num):
        return self.section_by_number(num) is not None

def claim_numbers(s):
    return sorted(set(NUM.findall(s or "")))

# ------------------------------------------------------------------ checks
def recurs(claim, hay):
    return dp.claim_in(claim, hay, 0.5)

def check_fields(arg):
    """check 1: returns the usable values."""
    ok = {}
    for key in ("claim", "reader_question", "why_not_obvious", "strongest_objection"):
        v = dp.arg_text(arg, key)
        if not v: say("FAIL", f"{key} 为空或仍是模板占位（<…>）：先写论点再写稿，templates/argument.md"); continue
        ok[key] = v
    hl = arg.get("headline")
    if not isinstance(hl, dict) or dp.is_placeholder(hl.get("claim_id")) or dp.is_placeholder(hl.get("number")):
        say("FAIL", "headline 缺 claim_id / number 或仍是模板占位：读者应该记住的那一个数字，必须是 claims.csv 里的一行")
    else: ok["headline"] = {"claim_id": str(hl["claim_id"]).strip(), "number": str(hl["number"]).strip()}
    ol = arg.get("outline")
    if not isinstance(ol, list) or not ol: say("FAIL", "outline 为空：引言每段一条（段落的主题句 / 这一段做的那一步）")
    else:
        bad = [i + 1 for i, x in enumerate(ol) if dp.is_placeholder(x)]
        if bad: say("FAIL", f"outline 第 {bad} 项仍是模板占位：引言每段一条（段落的主题句 / 这一段做的那一步）")
        else: ok["outline"] = [str(x) for x in ol]
    for key in ("where_answered",):
        v = dp.arg_text(arg, key)
        if v: ok[key] = v
        else: say("WARN", f"{key} 为空或仍是模板占位")
    ng = arg.get("not_claimed")
    real = [str(x) for x in ng if not dp.is_placeholder(x)] if isinstance(ng, list) else []
    if real: ok["not_claimed"] = real
    else: say("WARN", "not_claimed 为空或仍是模板占位：把论文明说不主张的范围写下来（它们要在 Limitations / Discussion 里出现）")
    return ok

def check_claim_shape(claim):
    nw, nn = n_words(claim), len(claim_numbers(claim))
    if nw > CLAIM_MAX_WORDS or nn > CLAIM_MAX_NUMBERS: say("WARN", f"claim {nw} 词 / {nn} 个数字（上限 {CLAIM_MAX_WORDS} 词、{CLAIM_MAX_NUMBERS} 个数字）：一句话，读者记不住两句")
    else: say("PASS", f"claim {nw} 词 / {nn} 个数字")
    if not VERB.search(claim): say("WARN", "主张句没有可证伪的动词（shows / reduces / fails / exceeds / predicts / 降低 / 导致 …）：它现在是个话题，不是主张")

def check_recurrence(claim, ms, fam):
    ab = ms.abstract(); intro = ms.intro()
    # abstract
    if not ab: say("FAIL", "找不到摘要：主张要在摘要里出现")
    elif any(recurs(claim, x) for x in sentences(ab)): say("PASS", "主张在摘要里出现")
    else: say("FAIL", "主张没有在摘要里出现（没有一句与 claim 的实词重合 ≥ 50 %，也没有一句同时含它的全部数字）")
    # end of the Introduction
    if fam == "nature":
        m = HERE_WE.search(intro)
        if not m: say("FAIL", "引言里没有 'Here we show …' 句：Nature 稿用它给出主张")
        else:
            para_end = intro.find("\n\n", m.start()); hay = intro[m.start(): para_end if para_end > 0 else len(intro)]
            say("PASS" if recurs(claim, hay) else "FAIL", "主张在 'Here we show' 句里出现" if recurs(claim, hay) else "'Here we show' 句与 claim 对不上（实词重合 < 50 %）")
    else:
        paras, _ = dp.intro_paragraphs(intro)
        if not paras: say("FAIL", "找不到 Introduction 的正文段落：主张要在引言末段（贡献列表之前）出现")
        elif recurs(claim, paras[-1]): say("PASS", "主张在引言末段（贡献列表之前）出现")
        else: say("FAIL", "主张没有在引言最后一段（贡献列表之前）出现：这一段必须把 claim 说出来")
    # end of the paper
    if fam == "nature":
        paras = dp.paragraphs(ms.text("discussion")); hay = paras[0] if paras else ""; where = "Discussion 第一段"
    else:
        hay = " ".join(sentences(ms.text("conclusion"))[:2]); where = "Conclusion 前两句"
        if not hay:
            hay = " ".join(sentences(ms.text("discussion"))[:2]); where = "Discussion 前两句（无 Conclusion 节）"
    if not hay: say("FAIL", f"找不到{where.split(' ')[0]}：主张要在论文结尾复述")
    elif recurs(claim, hay): say("PASS", f"主张在{where}出现")
    else: say("FAIL", f"主张没有在{where}出现")
    # title
    n = share_n(claim, ms.title)
    say("PASS" if n >= 2 else "WARN", f"标题与 claim 共享 {n} 个实词" + ("" if n >= 2 else "（< 2）：标题应该是主张的缩写"))
    return ab, intro

def check_headline(hl, ab, intro, root):
    rows = []
    cp = os.path.join(root, "paper", "claims.csv")
    if os.path.exists(cp): rows = list(csv.DictReader(io.open(cp, encoding="utf-8-sig")))
    ids = [r.get("claim_id", "").strip() for r in rows]
    if hl["claim_id"] not in ids: say("FAIL", f"headline.claim_id {hl['claim_id']} 不在 paper/claims.csv（{', '.join(i for i in ids if i) or '无主张行'}）")
    else: say("PASS", f"headline.claim_id {hl['claim_id']} 是 claims.csv 的一行")
    nums = claim_numbers(hl["number"])
    if not nums: say("FAIL", f"headline.number 「{hl['number']}」里没有数字：写读者应该记住的那个数")
    else:
        miss = [n for n in nums if not dp.has_number(n, ab)]
        if miss: say("FAIL", f"headline.number {miss} 不在摘要里（摘要必须带这个数字，且写法与 argument.md 一致）")
        else: say("PASS", f"headline.number {nums} 在摘要里")
        miss_i = [n for n in nums if not dp.has_number(n, intro)]
        if miss_i: say("WARN", f"headline.number {miss_i} 不在引言里（引言的发现段 / 贡献条目要出现同一个数）")
        drift = []
        for n in nums:
            x = float(n)
            if x == 0: continue
            for where, txt in (("摘要", ab), ("引言", intro)):
                for y in dict.fromkeys(NUM.findall(re.sub(r"\[[\d,;\s–-]+\]", " ", txt))):
                    if y != n and abs(float(y) - x) / x <= 0.08 and not dp.has_number(n, txt): drift.append(f"{where}写 {y} 而 headline 是 {n}")
        if drift: say("WARN", "同一个数字的取整不一致：" + "；".join(drift[:4]))
        elif not miss_i: say("PASS", "headline.number 在摘要与引言里写法一致")

def check_reader(arg_ok, intro):
    paras, _ = dp.intro_paragraphs(intro); first2 = "\n".join(paras[:2]) or intro
    ov = dp.stem_overlap(arg_ok["reader_question"], first2)
    say("PASS" if ov >= 0.4 else "WARN", f"reader_question 词重合 {ov:.0%}（引言前两段）" + ("" if ov >= 0.4 else "：引言前两段没有提出读者的问题"))
    ov = dp.stem_overlap(arg_ok["why_not_obvious"], intro)
    say("PASS" if ov >= 0.3 else "WARN", f"why_not_obvious 词重合 {ov:.0%}（引言）" + ("" if ov >= 0.3 else "：引言没有讲清读者为什么本来不会信这个主张（前人 / 领域默认怎么认为）"))

def check_where(arg_ok, ms):
    wa = arg_ok.get("where_answered")
    if not wa: return
    body = ms.body; places, bad = [], []
    for m in re.finditer(r"(?:§|\bSec(?:tion)?s?\.?)\s*(\d+(?:\.\d+)*)", wa):
        t = ms.section_by_number(m.group(1))
        (places if t is not None else bad).append(t if t is not None else f"§{m.group(1)}")
    for m in re.finditer(r"\bTables?\s*(S?\d+)", wa, re.I):
        paras = [p for p in dp.paragraphs(body) if re.search(r"\bTables?\.?\s*" + re.escape(m.group(1)) + r"\b", p, re.I)]
        (places if paras else bad).extend(["\n".join(paras)] if paras else [f"Table {m.group(1)}"])
    for m in re.finditer(r"\bFig(?:ure|s|\.)?\s*(S?\d+)", wa, re.I):
        paras = [p for p in dp.paragraphs(body) if re.search(r"\bFig(?:ure|s|\.)?\s*" + re.escape(m.group(1)) + r"\b", p, re.I)]
        (places if paras else bad).extend(["\n".join(paras)] if paras else [f"Fig {m.group(1)}"])
    if not places and not bad: say("WARN", "where_answered 没有写出 § / Table / Fig 编号：读者找不到答案在哪")
    elif bad: say("WARN", f"where_answered 指向稿子里不存在的位置：{bad}")
    else: say("PASS", "where_answered 指向的位置都存在")
    hay = "\n".join(places) + "\n" + ms.texts("limitations", "discussion")
    ov = dp.stem_overlap(arg_ok["strongest_objection"], hay)
    say("PASS" if ov >= 0.3 else "WARN", f"strongest_objection 词重合 {ov:.0%}（答案所在位置 + Limitations / Discussion）" + ("" if ov >= 0.3 else "：稿子里没有回应论点自己写下的最强反对意见"))

def check_outline(outline, intro):
    paras, _ = dp.intro_paragraphs(intro)
    entries = []
    for x in outline:
        if CONTRIB_ENTRY.match(x): continue
        move, _, rest = x.partition(":")
        if rest.strip() and len(move.split()) <= 3: entries.append((move.strip(), rest.strip()))
        else: entries.append((x.strip()[:24], x.strip()))
    nO, nP = len(entries), len(paras)
    if not nP: say("WARN", "引言没有可对照提纲的正文段落"); return
    if abs(nO - nP) > 1: say("WARN", f"引言 {nP} 段（贡献列表之前），提纲 {nO} 项（除 contributions）：段数差 > 1，先改提纲或先改稿")
    else: say("PASS", f"引言 {nP} 段 ↔ 提纲 {nO} 项")
    match, off = [], False
    for i, (move, text) in enumerate(entries):
        cand = sorted(((dp.stem_overlap(text, paras[j]), -abs(j - i), j) for j in (i - 1, i, i + 1) if 0 <= j < nP), reverse=True)
        if not cand or cand[0][0] < 0.35:
            off = True; say("WARN", f"引言第 {i + 1} 段没有按提纲走：{move}（提纲「{text[:50]}」与第 {max(i, 1)} 附近段落的词重合 {cand[0][0] if cand else 0:.0%} < 35 %）"); match.append(None)
        else: match.append(cand[0][2])
    got = [m for m in match if m is not None]
    inv = [i for i in range(1, len(match)) if match[i] is not None and match[i - 1] is not None and match[i] < match[i - 1]]
    if inv: say("WARN", f"引言段落顺序与提纲不一致：提纲第 {inv[0] + 1} 项（{entries[inv[0]][0]}）落在第 {inv[0]} 项之前")
    elif not off and got: say("PASS", "引言段落按提纲的顺序走")

def check_not_claimed(items, ms):
    hay = ms.texts("limitations", "discussion", "conclusion")
    miss = [x for x in items if dp.stem_overlap(x, hay) < 0.5]
    if miss: say("WARN", f"not_claimed 有 {len(miss)} 条没有在 Limitations / Discussion / Conclusion 里明说：" + "；".join(m[:50] for m in miss[:4]))
    else: say("PASS", f"not_claimed {len(items)} 条都在 Limitations / Discussion / Conclusion 里出现")

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="."); ap.add_argument("--manuscript", default="paper/manuscript.md"); ap.add_argument("--argument", default="paper/argument.md")
    ap.add_argument("--state", default="research-state.yaml"); ap.add_argument("--family", default="")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    import yaml
    sp = os.path.join(root, a.state); st = (yaml.safe_load(io.open(sp, encoding="utf-8")) if os.path.exists(sp) else {}) or {}
    fam, why = (a.family, "--family") if a.family else sc.infer_family(st)
    ap_ = os.path.join(root, a.argument)
    try: arg = dp.load_argument(ap_)
    except ValueError as e: say("FAIL", str(e)); return finish()
    if arg is None: say("FAIL", f"{a.argument} 不存在。先写论点再写稿：复制 templates/argument.md 到 {a.argument} 填好（claim / reader_question / headline / outline …），稿子照它写"); return finish()
    print(f"family = {fam}（来源 {why}）")
    ok = check_fields(arg)
    if "claim" in ok: check_claim_shape(ok["claim"])
    mp = os.path.join(root, a.manuscript)
    if not os.path.exists(mp): print(f"[INFO] argument: {a.manuscript} 不存在：只检查了 argument.md 本身"); return finish()
    ms = Manuscript(io.open(mp, encoding="utf-8").read())
    ab = intro = ""
    if "claim" in ok: ab, intro = check_recurrence(ok["claim"], ms, fam)
    else: ab, intro = ms.abstract(), ms.intro()
    if "headline" in ok: check_headline(ok["headline"], ab, intro, root)
    if "reader_question" in ok and "why_not_obvious" in ok: check_reader(ok, intro)
    if "where_answered" in ok and "strongest_objection" in ok: check_where(ok, ms)
    if "outline" in ok: check_outline(ok["outline"], intro)
    if ok.get("not_claimed"): check_not_claimed(ok["not_claimed"], ms)
    return finish()

def finish():
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(1 if FAILS else 0)

if __name__ == "__main__":
    main()
