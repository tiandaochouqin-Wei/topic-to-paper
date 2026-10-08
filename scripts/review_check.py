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
"""
import argparse, io, os, re, sys

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] review: {msg}")

SEV = re.compile(r"\[(major|minor)(?:→[^\]]*)?\]", re.I)
DISPO = re.compile(r"复核通过|accept|已改|fixed|rebut|驳回|partial|部分采纳|自证|closed|关闭|已修|已补|已加|已删|无需改|不改", re.I)
RE_REVIEW = re.compile(r"^#{1,3}\s*.*(re-review|第二轮|round\s*2|复审|re-?review)", re.I | re.M)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", default="."); ap.add_argument("--log", default="paper/review_log.md"); ap.add_argument("--manuscript", default="paper/manuscript.md"); ap.add_argument("--state", default="research-state.yaml")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    lp = os.path.join(root, a.log)
    if not os.path.exists(lp): say("FAIL", f"{a.log} 不存在"); sys.exit(1)
    txt = io.open(lp, encoding="utf-8").read(); lines = txt.splitlines()
    rr = RE_REVIEW.search(txt); first_round = txt[:rr.start()] if rr else txt; re_review = txt[rr.start():] if rr else ""
    items = []; cur_seat = ""
    synth = ""
    ms = re.search(r"^#{1,3}\s*.*(Phase 2|编辑综合|处置|disposition|synthesis)[^\n]*$", txt, re.I | re.M)
    if ms:
        rest = txt[ms.end():]; nx = re.search(r"^#{1,2}\s", rest, re.M); synth = rest[:nx.start()] if nx else rest
    for i, ln in enumerate(lines):
        hm = re.match(r"^#{2,4}\s*([A-Z]{1,3}\d?)\b", ln)          # ### R1 方法 / ### EIC / ### DA
        if hm: cur_seat = hm.group(1)
        m = SEV.search(ln)
        if not m: continue
        ordinal = re.match(r"^\s*(\d+)\.", ln); item_id = f"{cur_seat}-{ordinal.group(1)}" if cur_seat and ordinal else ""
        ctx = " ".join(lines[i:i + 3]); sev = m.group(1).lower(); inline_closed = bool(re.search(r"→\s*(已自证|closed|已改|fixed)", ln, re.I))
        in_synth = bool(item_id and re.search(r"(?<![A-Za-z0-9-])" + re.escape(item_id) + r"(?![0-9])", synth))   # listed in the editor's synthesis table = dispositioned
        items.append({"line": i + 1, "id": item_id, "sev": sev, "text": ln.strip()[:100], "dispo": bool(DISPO.search(ctx)) or inline_closed or in_synth, "closed_inline": inline_closed, "in_rereview": rr is not None and i + 1 > txt[:rr.start()].count("\n")})
    majors = [it for it in items if it["sev"] == "major" and not it["in_rereview"]]; minors = [it for it in items if it["sev"] == "minor" and not it["in_rereview"]]
    open_major = []
    CLOSED = r".{0,160}?(closed|关闭|已改|fixed|resolved|通过|accept|已补|已加)"
    for it in majors:
        if it["closed_inline"]: continue
        key = re.sub(r"^\s*\d+\.\s*|\[.*?\]|\*", "", it["text"]).strip()[:12]      # text without ordinal/tags
        hit = False
        if re_review:
            if it["id"] and re.search(r"(?<![A-Za-z0-9-])" + re.escape(it["id"]) + r"(?![0-9])" + CLOSED, re_review, re.I | re.S): hit = True
            elif key and re.search(re.escape(key) + CLOSED, re_review, re.I | re.S): hit = True
        if hit: it["dispo"] = True
        else: open_major.append(it)
    nod = [it for it in items if not it["dispo"]]
    if nod: say("FAIL", f"{len(nod)} 条意见无处置（同行/后两行写 复核通过|已改|rebut|partial，或在编辑综合表里按编号 R1-3 列出）: " + "; ".join(f"L{it['line']} {it['id'] or ''} {it['text'][:50]}" for it in nod[:4]))
    else: say("PASS", f"{len(items)} 条意见全部有处置（major {len(majors)} / minor {len(minors)}）")
    if majors and not re_review and open_major: say("FAIL", f"有 {len(majors)} 条 major 但 review_log 无 Re-review/第二轮 小节：修完必须复审，每条 major 在复审节里标 closed")
    elif open_major: say("FAIL", f"{len(open_major)} 条 major 未在复审节关闭: " + "; ".join(f"L{it['line']} {it['text'][:50]}" for it in open_major[:4]))
    elif majors: say("PASS", f"{len(majors)} 条 major 全部关闭（inline 自证 {sum(1 for it in majors if it['closed_inline'])} / 复审节 {len(majors)-sum(1 for it in majors if it['closed_inline'])}）")
    else: say("PASS", "无 major")
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
