# -*- coding: utf-8 -*-
"""P7 / S6 — freeze the manuscript into a review packet for independent (fresh-context subagent) reviewers, and prepare the re-review prompts. Run by Claude.

  python review_packet.py make     [--project .] [--round N] [--pdf paper/latex/main.pdf | --manuscript paper/manuscript.md] [--force]
  python review_packet.py rereview [--project .] --round N --items R0-1,R2-3 [--pdf … | --manuscript …] [--allow-same]

make      -> paper/review_packet/round<N>/ : the PDF (or manuscript + figures/), form.md (references/review-forms/<family>.md, family as shape_check.infer_family),
             manifest.json {round, created, kind, source, sha256, sha8, venue, family, branch, seats}, prompts/<seat>.md (the templates of references/review-seats.md,
             filled). One fresh-context subagent per prompt file; the prompt goes in whole and nothing else (no prereg.md, claims.csv, gap_map, conversation, notes).
rereview  -> round<N>/rereview/ : the REVISED PDF, manifest.json (its sha256 is the packet sha8 the log must cite), prompts/<item>.md = the original item text
             + the author's disposition copied from paper/review_log.md + the revised manuscript. The same seat judges `closed` / `OPEN` in a new subagent.

Why: with self-review the author's session wrote every seat, 4 of 6 majors in cvpr2027_med2 were closed by narrowing the wording, and an input-orientation bug in
cvpr2027_medical passed 10 review rounds (references/lessons.md). review_check.py (G7) requires that the log cites these packet hashes.
The sha8 is the first 8 hex digits of the manuscript's sha256; a paper that changes after `make` needs a new round.
"""
import argparse, datetime, hashlib, io, json, os, re, shutil, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
if HERE not in sys.path: sys.path.insert(0, HERE)
from shape_check import infer_family
from review_check import HEAD_IND, HEADING, SEV, seats_of

SEATS_MD = os.path.join(SKILL, "references", "review-seats.md"); FORMS = os.path.join(SKILL, "references", "review-forms")
# (seat label in the log heading, template name, rows of the seat table whose questions it gets)
PLAN = {"research": [("R0", "R0", ["R0"]), ("R1+R3", "R1R3", ["R1", "R3"]), ("R2", "R2", ["R2"]), ("DA", "DA", ["DA"])],
        "survey": [("R1+R4", "SR1R4", ["R1", "R4"]), ("R2+R3", "SR2R3", ["R2", "R3"]), ("DA", "DA", ["DA"])]}
FIG_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".svg")
PLACEHOLDER = re.compile(r"\{(\w+)\}")

def say(st, msg): print(f"[{st}] packet: {msg}")
def die(msg): say("FAIL", msg); sys.exit(1)

def load_state(root):
    p = os.path.join(root, "research-state.yaml")
    if not os.path.exists(p): return {}
    try:
        import yaml; return yaml.safe_load(io.open(p, encoding="utf-8")) or {}
    except Exception as ex: die(f"research-state.yaml 读取失败: {ex}")

def sha256_of(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def templates():
    txt = io.open(SEATS_MD, encoding="utf-8").read()
    out = {m.group(1): m.group(2) for m in re.finditer(r"<!--\s*template:\s*([\w+-]+)\s*-->\s*```[^\n]*\n(.*?)\n```", txt, re.S)}
    for need in ("common", "R0", "R1R3", "R2", "DA", "rereview"):
        if need not in out: die(f"references/review-seats.md 缺少模板 <!-- template: {need} -->")
    return out

def seat_questions(branch):
    """{seat id -> questions cell} from the research or survey seat table of review-seats.md"""
    sect = None; out = {}
    for ln in io.open(SEATS_MD, encoding="utf-8").read().splitlines():
        if ln.startswith("## "):
            sect = "research" if "研究稿席位" in ln else "survey" if "综述稿席位" in ln else None
            continue
        if sect != branch or not ln.startswith("|"): continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if sect == "research" and len(cells) >= 2:
            m = re.match(r"(R\d|DA)\b", cells[0])
            if m: out[m.group(1)] = (cells[0], cells[1])
        elif sect == "survey" and len(cells) >= 3:
            m = re.match(r"(R\d|DA)$", cells[1])
            if m: out[m.group(1)] = (cells[0], cells[2])
    return out

def fill(tpl, tpls, mapping):
    """expand {common}, then substitute placeholders in ONE pass so that free text (items, questions) is never re-expanded"""
    tpl = tpl.replace("{common}", tpls["common"])
    left = [m for m in PLACEHOLDER.findall(tpl) if m not in mapping]
    if left: die(f"模板里有未知占位符 {sorted(set(left))}")
    return PLACEHOLDER.sub(lambda m: mapping[m.group(1)], tpl)

def pick_source(root, a):
    """-> (kind, abs path). --manuscript wins when given; else --pdf / paper/latex/main.pdf when it exists; else paper/manuscript.md"""
    if a.manuscript: p = os.path.join(root, a.manuscript); kind = "manuscript"
    elif a.pdf: p = os.path.join(root, a.pdf); kind = "pdf"
    else:
        pdf = os.path.join(root, "paper", "latex", "main.pdf")
        if os.path.exists(pdf): p, kind = pdf, "pdf"
        else: p, kind = os.path.join(root, "paper", "manuscript.md"), "manuscript"
    if not os.path.isfile(p): die(f"稿件不存在: {p}（先编译 PDF，或用 --manuscript）")
    return kind, p

def stage_source(root, kind, src, dest):
    """copy the PDF (or manuscript + figures) into `dest`; -> (path the reviewer opens, description for the prompt)"""
    os.makedirs(dest, exist_ok=True)
    name = os.path.basename(src) if kind == "pdf" else "manuscript.md"
    shutil.copy2(src, os.path.join(dest, name)); shown = os.path.join(dest, name)
    if kind == "manuscript":
        figs = os.path.join(root, "figures"); n = 0
        if os.path.isdir(figs):
            os.makedirs(os.path.join(dest, "figures"), exist_ok=True)
            for f in sorted(os.listdir(figs)):
                if f.lower().endswith(FIG_EXT) and os.path.isfile(os.path.join(figs, f)): shutil.copy2(os.path.join(figs, f), os.path.join(dest, "figures", f)); n += 1
        shown += f"  (the figures are in {os.path.join(dest, 'figures')}; {n} files)"
    return shown

def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)

def make_form(family, venue, dest):
    fp = os.path.join(FORMS, f"{family}.md")
    if not os.path.exists(fp): die(f"没有审稿表 references/review-forms/{family}.md")
    out = os.path.join(dest, "form.md"); write_text(out, io.open(fp, encoding="utf-8").read().replace("{venue}", venue or "the target venue")); return out

def cmd_make(a):
    root = os.path.abspath(a.project); st = load_state(root)
    family, how = infer_family(st); venue = (st.get("target") or {}).get("venue") or ""
    branch = "survey" if str(st.get("branch") or "").lower() == "survey" else "research"
    base = os.path.join(root, "paper", "review_packet")
    existing = [int(m.group(1)) for d in (os.listdir(base) if os.path.isdir(base) else []) for m in [re.match(r"round(\d+)$", d)] if m]
    rnd = a.round if a.round else (max(existing) + 1 if existing else 1)
    out = os.path.join(base, f"round{rnd}")
    if os.path.exists(out) and not a.force: die(f"{os.path.relpath(out, root)} 已存在：已登记的稿件版本不能覆盖（改后的版本用 rereview；要整轮重审用新的 --round；确要覆盖加 --force）")
    if os.path.exists(out): shutil.rmtree(out)
    kind, src = pick_source(root, a)
    shown = stage_source(root, kind, src, out); sha = sha256_of(src); sha8 = sha[:8]
    form = make_form(family, venue, out); tpls = templates(); qs = seat_questions(branch)
    plan = PLAN[branch]; files = []
    for label, tname, rows in plan:
        missing = [r for r in rows if r not in qs]
        if missing: die(f"review-seats.md 的 {branch} 席位表里找不到 {missing}")
        quest = "\n".join(f"- {r} ({qs[r][0]}): {qs[r][1]}" if len(rows) > 1 else f"- {qs[r][1]}" for r in rows).replace("{venue}", venue or "the venue")
        text = fill(tpls[tname], tpls, {"pdf": shown, "form": form, "venue": venue or "the target venue", "seat": label, "seat_questions": quest, "packet_sha": sha8, "project_dir": root.replace(os.sep, "/")})
        write_text(os.path.join(out, "prompts", f"{tname}.md"), text); files.append((label, f"prompts/{tname}.md"))
    manifest = {"round": rnd, "created": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, "source": os.path.relpath(src, root).replace("\\", "/"),
                "sha256": sha, "sha8": sha8, "venue": venue, "family": family, "branch": branch, "seats": [l for l, _, _ in plan]}
    write_text(os.path.join(out, "manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    say("INFO", f"round {rnd}  {kind} {os.path.relpath(src, root)}  sha256 {sha8}…  venue '{venue}'  family {family} ({how})  -> {os.path.relpath(out, root)}/")
    for label, f in files: say("INFO", f"seat {label:6s} -> {os.path.relpath(os.path.join(out, f), root)}")
    print(f"\n每个提示文件启动一个全新上下文的子代理（Agent 工具，general-purpose），提示原文整段交给它，不加任何东西；"
          f"把每个子代理返回的审稿原文贴在 paper/review_log.md 的 `## Reviewer <席位> (independent, packet {sha8})` 之下。"
          f"稿子在审稿期间不能改（改了 sha 就对不上）。")

def log_items(root):
    """{item id -> (item text, disposition)} from the first-round part of paper/review_log.md (ids as review_check.py builds them)"""
    lp = os.path.join(root, "paper", "review_log.md")
    if not os.path.exists(lp): die("paper/review_log.md 不存在：先把独立审稿贴进日志并写处置")
    lines = io.open(lp, encoding="utf-8").read().splitlines()
    rr = next((i for i, l in enumerate(lines) if re.match(r"^#{1,3}\s*.*(re-review|第二轮|复审)", l, re.I)), len(lines))
    synth = {}; cur = ""; out = {}
    for i, l in enumerate(lines[:rr]):
        hi = HEAD_IND.match(l)
        if hi: tk = seats_of(hi.group("seat")); cur = tk[0] if tk else ""
        else:
            hm = re.match(r"^#{2,4}\s*([A-Z]{1,3}\d?)\b", l)
            if hm: cur = hm.group(1)
        if l.lstrip().startswith("|"):
            for m in re.finditer(r"\b([A-Z]{1,3}\d?-\d+)\b", l): synth.setdefault(m.group(1), []).append(l.strip())
        m = SEV.search(l); o = re.match(r"^\s*(\d+)\.", l)
        if not (m and o and cur): continue
        blk = [l]
        for j in range(i + 1, min(i + 5, rr)):
            nl = lines[j]
            if not nl.strip() or SEV.search(nl) or re.match(r"^\s*\d+\.\s", nl) or HEADING.match(nl): break
            blk.append(nl)
        out[f"{cur}-{o.group(1)}"] = blk
    res = {}
    for iid, blk in out.items():
        disp = [mm.group(0) for l in blk for mm in [re.search(r"(处置|disposition|→|rebut|partial).*", l, re.I)] if mm]
        item = [re.split(r"\s*(?:→|处置\s*[:：])", l)[0].rstrip() for l in blk]
        if not disp: disp = synth.get(iid, [])
        res[iid] = ("\n".join(item), "\n".join(disp))
    return res

def cmd_rereview(a):
    root = os.path.abspath(a.project)
    if not a.round: die("--round N 必填（原审稿的那一轮）")
    base = os.path.join(root, "paper", "review_packet", f"round{a.round}"); mp = os.path.join(base, "manifest.json")
    if not os.path.exists(mp): die(f"没有 {os.path.relpath(mp, root)}：先 make")
    orig = json.load(io.open(mp, encoding="utf-8")); st = load_state(root)
    ids = [x.strip() for x in (a.items or "").split(",") if x.strip()]
    if not ids: die("--items R0-1,R2-3 必填")
    items = log_items(root); miss = [i for i in ids if i not in items]
    if miss: die(f"review_log.md 里找不到意见 {miss}（编号 = 席位-序号，如 R0-1）")
    kind, src = pick_source(root, a); sha = sha256_of(src)
    if sha == orig.get("sha256") and not a.allow_same: die(f"稿件与 round{a.round} 的 packet 相同（sha {sha[:8]}）：复审要在改后版本上做；先改稿并重新编译（确要照样复审加 --allow-same）")
    out = os.path.join(base, "rereview")
    if os.path.exists(out): shutil.rmtree(out)
    shown = stage_source(root, kind, src, out); venue = orig.get("venue") or (st.get("target") or {}).get("venue") or ""
    form = make_form(orig.get("family") or infer_family(st)[0], venue, out); tpls = templates(); files = []
    for iid in ids:
        text_i, disp = items[iid]
        if not disp.strip():
            say("WARN", f"{iid} 在 review_log.md 里没有处置：先写处置（已改 / rebut / partial …）再复审"); disp = "(no disposition recorded)"
        seat = iid.rsplit("-", 1)[0]
        text = fill(tpls["rereview"], tpls, {"pdf": shown, "form": form, "venue": venue or "the target venue", "seat": seat, "packet_sha": sha[:8], "item_id": iid, "item_text": text_i, "disposition": disp})
        write_text(os.path.join(out, "prompts", f"{iid}.md"), text); files.append(iid)
    write_text(os.path.join(out, "manifest.json"), json.dumps({"round": a.round, "created": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind,
               "source": os.path.relpath(src, root).replace("\\", "/"), "sha256": sha, "sha8": sha[:8], "original_sha8": orig.get("sha8", ""), "items": ids}, ensure_ascii=False, indent=2) + "\n")
    say("INFO", f"round {a.round} rereview  revised {kind} sha256 {sha[:8]}… (original {str(orig.get('sha8', ''))})  items {', '.join(ids)}")
    for iid in files: say("INFO", f"item {iid:8s} -> {os.path.relpath(os.path.join(out, 'prompts', iid + '.md'), root)}")
    print(f"\n每条意见一个全新上下文的子代理，提示原文整段交给它；返回的 closed / OPEN 按席位贴进 paper/review_log.md 的 "
          f"`## Re-review <席位> (independent, packet {sha[:8]})` 之下。")

def main():
    ap = argparse.ArgumentParser(description="freeze the manuscript into a review packet for independent reviewers; prepare re-review prompts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("make", cmd_make), ("rereview", cmd_rereview)):
        p = sub.add_parser(name); p.set_defaults(fn=fn)
        p.add_argument("--project", default="."); p.add_argument("--round", type=int, default=0)
        p.add_argument("--pdf", default=""); p.add_argument("--manuscript", default="")
        if name == "make": p.add_argument("--force", action="store_true")
        else: p.add_argument("--items", default=""); p.add_argument("--allow-same", action="store_true")
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
