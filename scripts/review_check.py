# -*- coding: utf-8 -*-
"""P7 — review-loop check: every reviewer item has a disposition, majors are closed by a re-review, and G6 was re-run after the last edit.

  python review_check.py [--project .] [--log paper/review_log.md] [--manuscript paper/manuscript.md] [--state research-state.yaml]

Expected review_log.md structure (free text otherwise):
  items   : lines containing [major] / [minor] / [major→已自证] / **[复核通过]** … ; an item is any line with a bracketed severity or disposition tag
  dispo   : one of 复核通过 | accept | 已改 | fixed | rebut | 驳回 | partial | 部分 | 自证 | closed | 关闭 — on the same line or the next 2 lines
  round N : a heading matching  ## .*(Re-review|第二轮|Round 2|复审)  ; inside it each earlier major must appear as closed (its id/first 12 chars + closed word)
Checks:
  1. every [major]/[minor] item has a disposition                             -> FAIL
  2. every major is closed in a re-review section (or marked 自证/closed inline) -> FAIL
  3. state.review.round ≥ 1 and open_major is empty                            -> FAIL
  4. gate_report.md is newer than manuscript.md (G6 re-run after last edit)    -> FAIL
  5. edits named in dispositions ("§5.6", "Table 8", "L123") exist in manuscript -> WARN
Independent review (2026-10-28; references/review-seats.md, scripts/review_packet.py). Why: in three real drafts the author's own session wrote the
seats, 4 of 6 majors in cvpr2027_med2 were closed by narrowing the wording, and an input-orientation bug in cvpr2027_medical passed 10 self-review
rounds. Reviewers now run as fresh-context subagents on a registered packet; the log carries their output under
  ## Reviewer <seat> (independent, packet <sha8>)            sha8 = first 8 hex of manifest.json sha256 in paper/review_packet/round*/
  ## Re-review <seat> (independent, packet <sha8>)           sha8 of the REVISED manuscript (paper/review_packet/round*/rereview/manifest.json)
  6. research branch: ≥1 independent Reviewer section                           -> FAIL (state.review.independent_waiver: "<reason>" -> WARN; survey branch: WARN;
                                                                                    state.project.entry have_reviews = real reviews, INFO)
  7. an independent R0 section exists and carries `rating:` / `score:` / `recommendation:` ; mean independent rating at the reject boundary
     (cs_conf <= 3 of 6; cs_journal reject or major; nature reject)                -> missing R0 FAIL, missing rating WARN, low rating WARN
  8. every independent section's packet sha8 matches a manifest.json             -> FAIL
  9. every [major] carries `category:` (evidence|validity|novelty|value|clarity|format) on its line or the next 2 -> WARN (FAIL would turn every old log red)
 10. a major of category evidence|validity|novelty|value that the author closed (inline arrow, or in a non-independent Re-review text) instead of
     an independent Re-review section of the same seat on a different packet sha8     -> FAIL (narrowing words 收窄|narrow|reword|措辞|scope|限定|弱化|soften
     in the closing line: "收窄措辞不是关闭"); with a waiver and no independent re-review at all this is WARN
 11. a validity major's closing line or disposition names an existing file under the project (the check output that fails on a deliberately broken variant) -> FAIL
Mean rating scale: numbers are the 1-6 scale; words map reject 2 / major 3 / minor 4.5 / accept 5.5 (nature: major revision 3.5); low = mean <= 3.
"""
import argparse, io, os, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] review: {msg}")

SEV = re.compile(r"\[(major|minor)(?:→[^\]]*)?\]", re.I)
DISPO = re.compile(r"复核通过|accept|已改|fixed|rebut|驳回|partial|部分采纳|自证|closed|关闭|已修|已补|已加|已删|无需改|不改|需新实验|待补实验", re.I)
NEG_I = re.compile(r"\b(?:not|isn't|never)\s+(?:yet\s+)?(?:closed|resolved|fixed|accepted)|\bstill\s+open|未(?:关闭|解决|通过|修|改|补|闭)|尚未|没有(?:关闭|解决)|仍(?:未|然未|然开放)", re.I)   # a negated closing word is not a closing
NEG_CASE = re.compile(r"\bOPEN\b")                                                                                                    # the log format marks an unclosed major "OPEN: …"
def negated(span): return bool(NEG_I.search(span) or NEG_CASE.search(span))

RE_REVIEW = re.compile(r"^#{1,3}\s*.*(re-review|第二轮|round\s*2|复审|re-?review)", re.I | re.M)

HEAD_IND = re.compile(r"^#{1,3}\s*Reviewer\s+(?P<seat>[^(\n]+?)\s*\(\s*(?:independent|独立)[^)\n]*?packet\s+(?P<sha>[0-9a-f]{8})\b[^)\n]*\)", re.I)
HEAD_RR_IND = re.compile(r"^#{1,3}\s*(?P<pre>[^(\n]*?(?:re-?review|复审)[^(\n]*?)\s*\(\s*(?:independent|独立)[^)\n]*?packet\s+(?P<sha>[0-9a-f]{8})\b[^)\n]*\)", re.I)
HEADING = re.compile(r"^(#{1,6})\s")
SEAT_TOKEN = re.compile(r"\b(?:R\d|DA|EIC)\b")
CATEGORY = re.compile(r"category\s*[:：=]\s*[*`_]*\s*(evidence|validity|novelty|value|clarity|format)\b", re.I)
STRICT_CATS = ("evidence", "validity", "novelty", "value")           # only an independent re-review of the same seat can close these
NARROW = re.compile(r"收窄|narrow|re-?word|措辞|scope|限定|弱化|soften", re.I)
RATING = re.compile(r"^[ \t>*_`\-]*(?:rating|score|recommendation|评分|评级)[*_`]*[ \t]*[:：][ \t]*[*_`]*[ \t]*(\d+(?:\.\d+)?|accept|minor revision|major revision|reject|major|minor)\b", re.I | re.M)
WORD_SCORE = {"reject": 2.0, "major": 3.0, "major revision": 3.0, "minor": 4.5, "minor revision": 4.5, "accept": 5.5}
PATH_TOKEN = re.compile(r"[\w./\\-]+\.(?:json|csv|txt|md|py|log|yaml|yml|png|pdf|npy|tex)\b")
LOW_BOUNDARY = 3.0

def rating_value(tok, family):
    t = tok.lower()
    if re.match(r"^\d", t): return float(t)
    if family == "nature" and t == "major revision": return 3.5
    return WORD_SCORE.get(t)

def sections(lines, matcher):
    """[{seat_text, sha, start, end, text}] for every heading accepted by `matcher`; a section ends at the next heading of the same or a higher level."""
    out = []
    for i, ln in enumerate(lines):
        m = matcher.match(ln)
        if not m: continue
        lvl = len(HEADING.match(ln).group(1)); end = len(lines)
        for j in range(i + 1, len(lines)):
            hj = HEADING.match(lines[j])
            if hj and len(hj.group(1)) <= lvl: end = j; break
        gd = m.groupdict(); seat_text = gd.get("seat") or gd.get("pre") or ""
        out.append({"seat_text": seat_text.strip(), "sha": m.group("sha").lower(), "start": i, "end": end, "text": "\n".join(lines[i:end])})
    return out

def seats_of(seat_text):
    """'R1+R3' -> ['R1','R3']; 'Re-review R0' -> ['R0']; '' -> [] (an unnamed section is open to every seat)."""
    return SEAT_TOKEN.findall(seat_text)

def manifest_shas(root):
    shas = set(); base = os.path.join(root, "paper", "review_packet")
    for dp, _dn, fn in os.walk(base):
        for f in fn:
            if f != "manifest.json": continue
            try:
                import json; d = json.load(io.open(os.path.join(dp, f), encoding="utf-8"))
                s = str(d.get("sha256") or d.get("sha8") or "").lower()
                if re.match(r"^[0-9a-f]{8}", s): shas.add(s[:8])
            except Exception: pass
    return shas

def independent_checks(a, root, st, txt, lines, rr, re_review, majors, synth):
    """Rules 6-11 of the docstring: independent seats, registered packets, categories, closure of the four strict categories."""
    from shape_check import infer_family
    family = infer_family(st)[0]
    rv = st.get("review") or {}; waiver = str(rv.get("independent_waiver") or "").strip()
    branch = str(st.get("branch") or "research").strip().lower()
    entry = str((st.get("project") or {}).get("entry") or "").strip()
    ind = sections(lines, HEAD_IND); ind_rr = sections(lines, HEAD_RR_IND)
    waived_open = bool(waiver) and not ind_rr                        # the author-only flow is explicitly allowed: strict closure degrades to WARN
    # --- 6. independent sections exist
    if entry == "have_reviews":
        say("INFO", "entry=have_reviews：日志里是真实审稿人的意见，不要求独立审稿节")
    elif ind:
        say("PASS", f"独立审稿 {len(ind)} 节：" + ", ".join(f"{s['seat_text']}@{s['sha']}" for s in ind[:6]))
    elif waiver:
        say("WARN", f"没有独立审稿节（P7：每席一个新上下文子代理），已豁免：{waiver}")
    elif branch == "survey":
        say("WARN", "没有独立审稿节（S6：建议每席一个新上下文子代理；综述分支默认只 WARN）")
    else:
        say("FAIL", "没有独立审稿（P7：每席一个新上下文子代理）：review_packet.py make 后每个提示一个子代理，返回的审稿贴成 `## Reviewer <席位> (independent, packet <sha8>)`；确实无法开子代理时在 state.review.independent_waiver 写原因")
    # --- 7. R0 + rating
    if ind and branch != "survey" and entry != "have_reviews":
        r0 = [s for s in ind if "R0" in seats_of(s["seat_text"])]
        if not r0: say("FAIL", "没有独立的 R0（区域主席 / 价值）节：R0 回答「这个发现是否已被该刊读者知道、该刊会不会收」，不能省")
        vals = []; r0_has = False
        for s in ind:
            ms = list(RATING.finditer(s["text"]))
            if not ms: continue
            v = rating_value(ms[-1].group(1), family)
            if v is not None:
                vals.append(v)
                if "R0" in seats_of(s["seat_text"]): r0_has = True
        if r0 and not r0_has: say("WARN", "独立 R0 节没有 `rating:`（按该刊审稿表的量表给分）")
        if vals:
            mean = sum(vals) / len(vals)
            if mean <= LOW_BOUNDARY: say("WARN", f"独立审稿评分偏低（均值 {mean:.1f}，拒稿线 ≤ {LOW_BOUNDARY:g}，{family}）：先回证据或选题，不要只改写")
            else: say("PASS", f"独立审稿评分均值 {mean:.1f}（{len(vals)} 个评分）")
    # --- 8. packet sha8 registered
    if ind or ind_rr:
        known = manifest_shas(root)
        bad = sorted({s["sha"] for s in ind + ind_rr} - known)
        if bad: say("FAIL", f"审稿不是在登记的稿件版本上做的：packet {', '.join(bad)} 不在 paper/review_packet/round*/manifest.json（review_packet.py make / rereview 先登记）")
        else: say("PASS", "独立审稿节的 packet sha8 都在 manifest.json 里登记")
    # --- 9. category present
    nocat = [it for it in majors if not it["category"]]
    if nocat: say("WARN", f"{len(nocat)} 条 major 没有 category:（evidence|validity|novelty|value|clarity|format）: " + ", ".join(it["id"] or f"L{it['line']}" for it in nocat[:8]))
    # --- 10/11. closure of the strict categories
    strict = [it for it in majors if it["category"] in STRICT_CATS]
    if not strict: return
    author_rr = re_review
    for s in sorted(ind_rr, key=lambda s: -s["start"]):
        author_rr = author_rr.replace(s["text"], "")
    def closing(text, it):
        """the first non-negated 'id ... closed' span in `text`, extended to the end of its line (the reason follows the word), else ''"""
        pats = []
        if it["id"]: pats.append(r"(?<![A-Za-z0-9-])" + re.escape(it["id"]) + r"(?![0-9])")
        key = re.sub(r"^\s*\d+\.\s*|\[.*?\]|\*", "", it["text"]).strip()[:12]
        if key: pats.append(re.escape(key))
        for p in pats:
            for mm in re.finditer(p + r".{0,160}?(closed|关闭|已改|fixed|resolved|通过|accept|已补|已加)", text, re.I | re.S):
                if not negated(mm.group(0)):
                    end = text.find("\n", mm.end()); return text[mm.start():len(text) if end < 0 else end]
        return ""
    bad_n = 0
    for it in strict:
        who = it["id"] or f"L{it['line']}"
        named = [s for s in ind_rr if closing(s["text"], it)]
        ok_secs = [s for s in named if not seats_of(s["seat_text"]) or it["seat"] in seats_of(s["seat_text"])]
        good = [s for s in ok_secs if s["sha"] != it["sha"]]
        author_close = closing(author_rr, it) if not good else ""
        closed_by = ""
        if good:
            closed_by = closing(good[0]["text"], it)
        elif ok_secs:
            bad_n += 1; say("FAIL", f"{who}（{it['category']}）的复审与原审稿是同一份 packet {it['sha']}：独立复审必须在改后版本上做（review_packet.py rereview）")
        elif named:
            bad_n += 1; say("FAIL", f"{who}（{it['category']}）被别的席位的复审关闭：同一席位 {it['seat']} 必须自己在改后版本上复审")
        elif author_close or it["closed_inline"]:
            closed_by = author_close or it["block"][0]
            lvl = "WARN" if waived_open else "FAIL"
            bad_n += lvl == "FAIL"
            if NARROW.search(closed_by): say(lvl, f"收窄措辞不是关闭（{who}，{it['category']}）：{closed_by.strip()[:80]!r}；收窄后的稿子要由同一席位在新 packet 上独立复审并接受")
            else: say(lvl, f"作者不能自己关闭 {it['category']} 类 major（{who}）：需要同一席位的 `## Re-review {it['seat'] or '<席位>'} (independent, packet <sha8>)` 在改后版本上写 closed")
        if it["category"] == "validity" and closed_by:
            disp = " ".join(re.sub(r"^.*?(处置|disposition|→)", r"\1", l, flags=re.I) for l in it["block"] if re.search(r"处置|disposition|→", l, re.I))
            rows = " ".join(l for l in synth.splitlines() if it["id"] and re.search(r"(?<![A-Za-z0-9-])" + re.escape(it["id"]) + r"(?![0-9])", l))
            toks = PATH_TOKEN.findall(" ".join([closed_by, disp, rows]))
            if not [t for t in toks if os.path.isfile(os.path.join(root, t.replace("\\", "/")))]:
                bad_n += 1; say("FAIL", f"validity 类 major 关闭要引用一个在破坏版上会失败的检查输出（{who}）：在关闭行或处置里写出存在的文件路径，如 results/instruments/<组件>_broken.json 或变异测试的输出")
    if not bad_n: say("PASS", f"{len(strict)} 条 evidence/validity/novelty/value 类 major 都由独立复审关闭或尚未关闭（未关闭的由上面的复审检查报告）")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", default="."); ap.add_argument("--log", default="paper/review_log.md"); ap.add_argument("--manuscript", default="paper/manuscript.md"); ap.add_argument("--state", default="research-state.yaml")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    lp = os.path.join(root, a.log)
    if not os.path.exists(lp): say("FAIL", f"{a.log} 不存在"); sys.exit(1)
    txt = io.open(lp, encoding="utf-8").read(); lines = txt.splitlines()
    rr = RE_REVIEW.search(txt); first_round = txt[:rr.start()] if rr else txt; re_review = txt[rr.start():] if rr else ""
    st = {}
    sp0 = os.path.join(root, a.state)
    if os.path.exists(sp0):
        try:
            import yaml; st = yaml.safe_load(io.open(sp0, encoding="utf-8")) or {}
        except Exception: st = {}
    items = []; cur_seat = ""; cur_sha = ""
    synth = ""
    ms = re.search(r"^#{1,3}\s*.*(Phase 2|编辑综合|处置|disposition|synthesis)[^\n]*$", txt, re.I | re.M)
    if ms:
        rest = txt[ms.end():]; nx = re.search(r"^#{1,2}\s", rest, re.M); synth = rest[:nx.start()] if nx else rest
    def item_block(i):
        """the item line plus up to 2 continuation lines, stopping before the next item or heading"""
        blk = [lines[i]]
        for j in range(i + 1, min(i + 3, len(lines))):
            l = lines[j]
            if SEV.search(l) or re.match(r"^\s*\d+\.\s", l) or HEADING.match(l): break
            blk.append(l)
        return blk
    for i, ln in enumerate(lines):
        hi = HEAD_IND.match(ln)
        if hi:                                                      # ## Reviewer R1+R3 (independent, packet 1a2b3c4d)
            tk = seats_of(hi.group("seat")); cur_seat = tk[0] if tk else (re.split(r"[\s+,/]+", hi.group("seat").strip()) or [""])[0]; cur_sha = hi.group("sha").lower()
        else:
            if re.match(r"^#{1,2}\s", ln): cur_sha = ""             # a new top-level section that is not an independent review
            hm = re.match(r"^#{2,4}\s*([A-Z]{1,3}\d?)\b", ln)       # ### R1 方法 / ### EIC / ### DA
            if hm: cur_seat = hm.group(1)
        m = SEV.search(ln)
        if not m: continue
        ordinal = re.match(r"^\s*(\d+)\.", ln); item_id = f"{cur_seat}-{ordinal.group(1)}" if cur_seat and ordinal else ""
        ctx = " ".join(lines[i:i + 3]); sev = m.group(1).lower(); inline_closed = bool(re.search(r"→\s*(已自证|closed|已改|fixed)", ln, re.I))
        in_synth = bool(item_id and re.search(r"(?<![A-Za-z0-9-])" + re.escape(item_id) + r"(?![0-9])", synth))   # listed in the editor's synthesis table = dispositioned
        blk = item_block(i); cm = CATEGORY.search(" ".join(blk))
        items.append({"line": i + 1, "id": item_id, "sev": sev, "text": ln.strip()[:100], "dispo": bool(DISPO.search(ctx)) or inline_closed or in_synth, "closed_inline": inline_closed, "in_rereview": rr is not None and i + 1 > txt[:rr.start()].count("\n"),
                      "seat": cur_seat, "sha": cur_sha, "category": cm.group(1).lower() if cm else "", "block": blk})
    majors = [it for it in items if it["sev"] == "major" and not it["in_rereview"]]; minors = [it for it in items if it["sev"] == "minor" and not it["in_rereview"]]
    open_major = []
    CLOSED = r".{0,160}?(closed|关闭|已改|fixed|resolved|通过|accept|已补|已加)"
    for it in majors:
        if it["closed_inline"]: continue
        key = re.sub(r"^\s*\d+\.\s*|\[.*?\]|\*", "", it["text"]).strip()[:12]      # text without ordinal/tags
        hit = False
        def closes(prefix): return any(not negated(mm.group(0)) for mm in re.finditer(prefix + CLOSED, re_review, re.I | re.S))
        if re_review:
            if it["id"] and closes(r"(?<![A-Za-z0-9-])" + re.escape(it["id"]) + r"(?![0-9])"): hit = True
            elif key and closes(re.escape(key)): hit = True
        if hit: it["dispo"] = True
        else: open_major.append(it)
    nod = [it for it in items if not it["dispo"]]
    if nod: say("FAIL", f"{len(nod)} 条意见无处置（同行/后两行写 复核通过|已改|rebut|partial，或在编辑综合表里按编号 R1-3 列出）: " + "; ".join(f"L{it['line']} {it['id'] or ''} {it['text'][:50]}" for it in nod[:4]))
    else: say("PASS", f"{len(items)} 条意见全部有处置（major {len(majors)} / minor {len(minors)}）")
    if majors and not re_review and open_major: say("FAIL", f"有 {len(majors)} 条 major 但 review_log 无 Re-review/第二轮 小节：修完必须复审，每条 major 在复审节里标 closed")
    elif open_major: say("FAIL", f"{len(open_major)} 条 major 未在复审节关闭: " + "; ".join(f"L{it['line']} {it['text'][:50]}" for it in open_major[:4]))
    elif majors and any(it["closed_inline"] and it["id"] and not re.search(r"(?<![A-Za-z0-9-])" + re.escape(it["id"]) + r"(?![0-9])", re_review) for it in majors):
        solo = [it["id"] for it in majors if it["closed_inline"] and it["id"] and not re.search(r"(?<![A-Za-z0-9-])" + re.escape(it["id"]) + r"(?![0-9])", re_review)]
        say("WARN", f"{len(solo)} 条 major 只靠行内 →已改/closed 关闭，复审节没有逐条核对: {', '.join(solo[:6])}（复审的意义是换一遍眼睛看改后的稿子）")
        say("PASS", f"{len(majors)} 条 major 全部关闭（含行内关闭）")
    elif majors: say("PASS", f"{len(majors)} 条 major 全部关闭（inline 自证 {sum(1 for it in majors if it['closed_inline'])} / 复审节 {len(majors)-sum(1 for it in majors if it['closed_inline'])}）")
    else: say("PASS", "无 major")
    independent_checks(a, root, st, txt, lines, rr, re_review, majors, synth)
    # state
    sp = os.path.join(root, a.state)
    if os.path.exists(sp):
        try:
            import yaml; st = yaml.safe_load(io.open(sp, encoding="utf-8")) or {}; rv = st.get("review") or {}
            if int(rv.get("round", 0) or 0) < 1: say("FAIL", "state.review.round < 1：审稿后把 round 记上")
            if rv.get("open_major"): say("FAIL", f"state.review.open_major 非空: {rv['open_major']}")
            if int(rv.get("round", 0) or 0) >= 1 and not rv.get("open_major"): say("PASS", f"state.review.round={rv.get('round')}，open_major 空")
        except Exception as ex: say("WARN", f"state 读取失败 {ex}")
    # G6 rerun after last edit
    mp = os.path.join(root, a.manuscript); gp = os.path.join(root, "gate_report.md")
    if os.path.exists(mp) and os.path.exists(gp):
        if os.path.getmtime(gp) + 1 < os.path.getmtime(mp): say("FAIL", "manuscript.md 比 gate_report.md 新：修订后 G6 没重跑（`gate_check.py all`）")
        else: say("PASS", "gate_report.md 新于 manuscript.md（修订后 G6 已重跑）")
    elif os.path.exists(mp): say("FAIL", "无 gate_report.md：修订后要跑 G6")
    # named edit locations exist
    if os.path.exists(mp):
        md = io.open(mp, encoding="utf-8").read()
        locs = set(re.findall(r"(§\s*\d+(?:\.\d+)*|Table\s*\d+|Fig\.?\s*\d+|Section\s*\d+(?:\.\d+)*)", txt))
        miss = [l for l in locs if not re.search(re.escape(re.sub(r"^§\s*|^Section\s*", "", l)) if l.startswith(("§", "Section")) else re.escape(l), md)]
        if miss: say("WARN", f"处置里提到的位置在正文找不到: {sorted(miss)[:6]}")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
