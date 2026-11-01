# -*- coding: utf-8 -*-
"""P5 — independent visual review of the figures: render every figure as it is PRINTED, hand it with same-role exemplar thumbnails and a rubric
to a fresh-context subagent, and check the pasted reviews. Run by Claude (make / rereview) and by G5 of t2p.py (check).

  python figure_review.py make     [--project .] [--round N] [--pdf paper/latex/main.pdf] [--force]
  python figure_review.py rereview [--project .] --round N --figs 2,4 [--consistency] [--pdf …] [--allow-same]
  python figure_review.py check    [--project .]                     (G5 of t2p.py runs it; exit = #FAIL)

Figure numbers = the PRINTED numbers: with paper/latex/main.tex the order of the figure environments (\\input expanded, each mapped to figures.csv by its
\\includegraphics stems, only environments with a \\caption count), checked against the compiled PDF (caption text of "Figure N", page where the
source raster is drawn). paper/figure_plan.csv item numbers / figures.csv plan_item are only the fallback; a disagreement prints a WARN with the
mapping and the LaTeX order wins. Exemplar thumbnails follow the ROLE of the plan row that lists the file (never the number).

make      -> paper/figure_review/round<N>/ : per top-level figure of figures.csv (panels x_a, x_b are grouped into x) a folder fig<N>/ with
             page<P>.png (the printed page where "Figure N" is captioned in the compiled PDF, 150 dpi), crop.png (the figure region cut out of that
             page at TRUE print size, 300 dpi) — or, when there is no compiled PDF / no caption "Figure N" is found, true_scale.png (the figure
             file drawn at its registered print_width_mm on a white page, 300 dpi; the manifest says so) — and ex<k>.png (up to 3 exemplar
             thumbnails of the same role: paper/figure_plan.csv `thumb`, then literature/exemplars/exemplar_figures.csv rows of that role).
             manifest.json {round, created, kind, venue, family, pdf, pdf_sha256, sha256, sha8, figures: [{number, number_source, id, sources
             [{path, sha256}], sha256, render_sha256, mode, pages, print_width_mm, exemplars, ...}]}; prompts/fig<N>.md = the filled prompt
             (references/figure-rubric.md): the reviewer sees ONLY the renders, the exemplars and the rubric — no claims, prereg, code, data paths
             or conversation. One fresh subagent per prompt (Agent tool, general-purpose); its answer goes whole into paper/figure_review.md under
             `## Figure review (independent, packet <sha8>)` with one `### Fig N` block per figure (scores / verdict / items; format in the rubric).
             With >= 2 figures, prompts/consistency.md too: ONE fresh reviewer gets all crops (true print size) + captions and answers only
             cross-figure questions (same method = same colour / marker / line style / name; one font family; panel letters, axis conventions;
             plain-word labels, no code names). Its answer goes under `## Figure consistency (independent, packet <sha8>)` (items only, no scores).
rereview  -> round<N>/rereview[K]/ : fresh renders of the revised figures, manifest.json (its sha8 is what the re-review heading must cite) and
             prompts/fig<N>.md = the previous items of the figure's latest block + the author's dispositions (`## Figure dispositions` / `### Fig N`
             in paper/figure_review.md) + the revised renders. Figures whose sources and renders did not change are refused unless --allow-same.
             --consistency: re-renders ALL figures and writes prompts/consistency.md = the previous consistency items + dispositions
             (`### Consistency`) + the new crops; its answer goes under `## Figure consistency re-review (independent, packet <sha8>)`.
check     -> 1. figures.csv has >= 1 figure but paper/figure_review.md has no `## Figure review (independent, packet <sha8>)` section: FAIL when
                paper/figure_plan.csv exists (a new-style project), else WARN;
             2. every section's packet sha8 is registered in a manifest under paper/figure_review/ (else FAIL);
             3. per figure, its LATEST block (review or re-review): `scores:` with the 7 criteria (else WARN); any score <= 2 FAIL "Fig N: <criterion> = 2";
                mean < 3.5 WARN; verdict revise / a [major] item / an OPEN line FAIL unless a LATER `## Figure re-review (independent, packet …)` block
                of that figure, on a different packet (and a changed figure), has verdict accept, no score <= 2, no [major] and no OPEN;
             4. a figure whose current source sha differs from the sha in the packet of its latest review: WARN "Fig N 改过、未复审";
             5. a figure in a packet that has no block in the log: WARN;
             6. >= 2 figures and a per-figure review exists but no `## Figure consistency (independent, packet <sha8>)` section: FAIL when
                paper/figure_plan.csv exists, else WARN; open [major] items / verdict revise / OPEN lines in it FAIL until a LATER
                `## Figure consistency re-review (independent, packet …)` on a different packet (and changed figures) says `verdict: accept`
                with no [major] and no OPEN; figures changed after the consistency packet: WARN.
The thresholds (<= 2 FAIL, mean 3.5 WARN) are provisional: nobody has yet calibrated them against what a user calls ugly. The rubric is one model's taste;
the user is the last reviewer of figures (references/lessons.md: cvpr2027_med2 went through four redesigns).
Why: G5 checks form (font >= 5 pt, dpi, fonts, grayscale, counts, types), not whether a figure is good, and the session that drew a figure also judged it.
Same mechanism as the G7 independent review (review_packet.py / review_check.py): packet sha8 registered in a manifest, fresh-context reviewer, re-review on a changed object.
"""
import argparse, datetime, difflib, hashlib, io, json, os, re, shutil, sys, unicodedata
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
if HERE not in sys.path: sys.path.insert(0, HERE)
import figure_plan as fp
import tex_to_md as t2m
from review_packet import fill, sha256_of, write_text, load_state
from review_check import sections
from shape_check import infer_family

RUBRIC = os.path.join(SKILL, "references", "figure-rubric.md")
CRITERIA = ["message", "hierarchy", "density", "encoding", "typography", "consistency", "venue"]
LOW_SCORE = 2; MEAN_WARN = 3.5                                   # provisional thresholds
RASTER = (".png", ".jpg", ".jpeg"); EXTS = (".pdf",) + RASTER
HEAD_FR = re.compile(r"^#{1,3}\s*Figure\s+review\s*\(\s*(?:independent|独立)[^)\n]*?packet\s+(?P<sha>[0-9a-f]{8})\b[^)\n]*\)", re.I)
HEAD_RR = re.compile(r"^#{1,3}\s*Figure\s+re-?review\s*\(\s*(?:independent|独立)[^)\n]*?packet\s+(?P<sha>[0-9a-f]{8})\b[^)\n]*\)", re.I)
HEAD_CONS = re.compile(r"^#{1,3}\s*Figure\s+consistency\s*\(\s*(?:independent|独立)[^)\n]*?packet\s+(?P<sha>[0-9a-f]{8})\b[^)\n]*\)", re.I)
HEAD_CONS_RR = re.compile(r"^#{1,3}\s*Figure\s+consistency\s+re-?review\s*\(\s*(?:independent|独立)[^)\n]*?packet\s+(?P<sha>[0-9a-f]{8})\b[^)\n]*\)", re.I)
HEAD_DISPO = re.compile(r"^#{1,3}\s*Figure\s+dispositions?\b", re.I)
FIG_SUB = re.compile(r"^#{3,4}\s*Fig(?:ure|\.)?\s*(\d+)\b", re.I)
DISPO_SUB = re.compile(r"^#{3,4}\s*(?:Fig(?:ure|\.)?\s*(\d+)\b|(Consistency)\b)", re.I)
FAILS = 0


def say(st, msg):
    global FAILS
    FAILS += st == "FAIL"
    print(f"[{st}] figure_review: {msg}")


def die(msg): say("FAIL", msg); print(f"\n{FAILS} FAIL"); sys.exit(1)


def rel(root, p): return os.path.relpath(p, root).replace("\\", "/")


def fwd(p): return os.path.abspath(p).replace("\\", "/")


def float_or(x, default=0.0):
    try: return float(str(x).strip())
    except Exception: return default


# ------------------------------------------------------------------ figures.csv -> top-level figures
def load_groups(root):
    """[{id, stems: {stem: {files, width}}, plan_item, missing}] in figures.csv order; panels x_a / x_b are one figure x; _gray previews and instrument figures are skipped"""
    groups = {}
    for r in fp.read_csv(os.path.join(root, "figures.csv")):
        f = re.sub(r"^\./", "", (r.get("file") or "").strip().replace("\\", "/"))
        if not f: continue
        stem, ext = os.path.splitext(f)
        if "/instruments/" in "/" + stem or stem.endswith("_gray"): continue
        gid = re.sub(r"_[a-h]$", "", stem)
        g = groups.setdefault(gid, {"id": gid, "stems": {}, "plan_item": "", "missing": []})
        st = g["stems"].setdefault(stem, {"files": [], "width": 0.0})
        st["width"] = max(st["width"], float_or(r.get("print_width_mm")))
        g["plan_item"] = g["plan_item"] or (r.get("plan_item") or "").strip()
        if ext.lower() in EXTS and os.path.isfile(os.path.join(root, f)): st["files"].append(f)
        else: g["missing"].append(f)
    return [g for g in groups.values() if any(s["files"] for s in g["stems"].values())], [g for g in groups.values() if not any(s["files"] for s in g["stems"].values())]


def sources_of(g): return sorted({f for s in g["stems"].values() for f in s["files"]})


def sha_of_sources(root, paths):
    """one sha over [(path, file sha256)] — a missing file gives '' so that it never equals a recorded sha"""
    items = []
    for p in sorted(paths):
        fp_ = os.path.join(root, p)
        if not os.path.isfile(fp_): return ""
        items.append(f"{p}:{sha256_of(fp_)}")
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()


def group_width(g): return max([s["width"] for s in g["stems"].values()] + [0.0])


# ------------------------------------------------------------------ figure numbers
def tex_figures(root):
    """[{k, stems: {basenames of the \\includegraphics files}, caption}] per figure environment that gets a number, in source order = the LaTeX figure
    number (\\input / \\include expanded, comments stripped). A float without \\caption (subfigure captions do not count) gets no number; when no
    float has a \\caption at all, every float is counted. [] when there is no paper/latex/main.tex."""
    main = os.path.join(root, "paper", "latex", "main.tex")
    if not os.path.isfile(main): return []
    try: text = t2m.expand_inputs(main)
    except Exception: return []
    envs = []
    for m in re.finditer(r"\\begin\{((?:sideways)?figure\*?)\}(.*?)\\end\{\1\}", text, re.S):
        body = m.group(2)
        stems = {os.path.splitext(os.path.basename(x.strip().replace("\\", "/")))[0] for x in re.findall(r"\\includegraphics\*?(?:\[[^\]]*\])?\s*\{([^}]+)\}", body)}
        top = re.sub(r"\\begin\{subfigure\}.*?\\end\{subfigure\}", "", body, flags=re.S)
        cm = re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", top); cap = None
        if cm: cap = t2m.balanced(top, cm.end() - 1)[0]
        envs.append({"stems": stems, "caption": cap})
    counted = [e for e in envs if e["caption"] is not None] or envs
    for k, e in enumerate(counted, 1): e["k"] = k; e["caption"] = e["caption"] or ""
    return counted


def tex_plain(s):
    """a TeX caption as plain words: commands dropped (their arguments kept), math delimiters and braces removed"""
    s = t2m.unbrace(s or ""); s = re.sub(r"\\label\{[^}]*\}", "", s); s = re.sub(r"\\[A-Za-z]+\*?", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[{}$~\\]", " ", s)).strip()


def alnum(s): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", s or "").lower())


def caption_body(txt):
    """printed caption text without its 'Figure N:' label, ligatures resolved, whitespace collapsed"""
    s = unicodedata.normalize("NFKC", txt or "")
    return re.sub(r"\s+", " ", re.sub(r"^\s*(?:Fig\.|Figure|FIGURE)\s*\d+\s*[.:|]?\s*", "", s)).strip()


def caps_match(tex_cap, pdf_txt):
    """does the printed caption start like the TeX caption (commands dropped, ligatures and hyphenation tolerated)?  None when there is nothing to compare"""
    a = alnum(tex_plain(tex_cap))[:40]; b = alnum(caption_body(pdf_txt))[:40]
    if not a or not b: return None
    n = min(len(a), len(b), 24)
    if a[:n] == b[:n]: return True
    # tolerate a few glyph differences (math, citations, hyphenation) but never a different number
    return re.findall(r"\d+", a) == re.findall(r"\d+", b) and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def plan_row_for(g, plan):
    """(plan row, how well) whose `files` column lists one of the group's file stems: 3 = the same stem, 2 = a panel / prefix of it; (None, 0) when no row does.
    Matching is by FILE, never by the row's item number."""
    best, score = None, 0
    for r in plan:
        if r.get("kind") != "figure" or (r.get("status") or "planned") == "dropped": continue
        for e in fp.plan_files(r):
            ent = os.path.splitext(e.replace("\\", "/").lstrip("./"))[0].lower()
            for stem in list(g["stems"]) + [g["id"]]:
                sc = 3 if stem.lower() == ent else 2 if fp.covers(e, stem) else 0
                if sc > score: best, score = r, sc
    return best, score


def num_of(item):
    m = re.search(r"(\d+)", item or ""); return int(m.group(1)) if m else 0


def merge_groups(groups):
    """figure groups that sit in the same LaTeX environment are ONE printed figure: stems and sources are unioned, ids joined with '+'"""
    out = {}
    for g in groups:
        k = g.get("tex_number")
        if not k or k not in out:
            out[k or id(g)] = g; continue
        t = out[k]; t["id"] += "+" + g["id"]; t["stems"].update(g["stems"]); t["missing"] += g["missing"]; t["plan_item"] = t["plan_item"] or g["plan_item"]
        t["plan_number"] = t.get("plan_number") or g.get("plan_number", 0); t["plan_how"] = t.get("plan_how") or g.get("plan_how", "")
    return list(out.values())


def assign_numbers(root, groups, quiet=False):
    """-> (groups sorted by number, info). Number = the printed number: the order of the figure environments in main.tex (a group is mapped by its
    \\includegraphics stems; groups of one environment are merged); without main.tex / without a match the plan row that lists the file (item "Fig N"),
    then figures.csv plan_item, then free numbers in figures.csv order. A plan number that disagrees with the LaTeX order prints one WARN with the mapping."""
    plan = [r for r in fp.read_csv(os.path.join(root, "paper", "figure_plan.csv")) if r.get("kind") == "figure" and (r.get("status") or "planned") != "dropped"]
    texfigs = tex_figures(root); info = {"tex_figures": len(texfigs), "source": "", "mismatches": []}
    for g in groups:
        r, _ = plan_row_for(g, plan); g["plan_number"] = num_of(r.get("item")) if r else 0; g["plan_how"] = "plan" if g["plan_number"] else ""
        if not g["plan_number"] and num_of(g["plan_item"]): g["plan_number"] = num_of(g["plan_item"]); g["plan_how"] = "figures.csv plan_item"
        names = {os.path.basename(s) for s in g["stems"]} | {os.path.basename(g["id"])}
        g["tex_number"] = next((t["k"] for t in texfigs if t["stems"] & names), 0)
    use_tex = any(g["tex_number"] for g in groups)
    if use_tex: groups = merge_groups(groups)
    used = set()
    def take(g, n, how):
        if n and n not in used: g["number"] = n; g["number_source"] = how; used.add(n)
    if use_tex:
        info["source"] = "tex order"
        for g in groups:
            if g["tex_number"]:
                take(g, g["tex_number"], "tex order"); g["tex_caption"] = tex_plain(next(t["caption"] for t in texfigs if t["k"] == g["tex_number"]))
                if g.get("plan_number") and g["plan_number"] != g["number"]:
                    info["mismatches"].append({"id": g["id"], "plan": g["plan_number"], "tex": g["number"]})
        nxt = len(texfigs) + 1
        for g in groups:
            if g.get("number"): continue
            while nxt in used: nxt += 1
            take(g, nxt, "guess (not in main.tex)")
            if not quiet: say("WARN", f"{g['id']} 不在 paper/latex/main.tex 的任何 figure 环境里（按 \\includegraphics 的文件名匹配）：编号 {g['number']} 是猜的，渲染会退回 true_scale")
        if info["mismatches"] and not quiet:
            say("WARN", "图表计划的序号与 LaTeX 的出图顺序不一致，按 LaTeX 顺序编号（印刷出来的是它）：" + "; ".join(f"{m['id']}: plan Fig {m['plan']} → LaTeX Figure {m['tex']}" for m in info["mismatches"])
                + "（paper/figure_plan.csv 的 item 号请改成 LaTeX 顺序）")
    else:
        if texfigs and not quiet: say("WARN", "paper/latex/main.tex 有 figure 环境，但没有一个的 \\includegraphics 文件名与 figures.csv 的图对得上：序号退回 plan / figures.csv 顺序")
        info["source"] = "plan"
        for g in groups: take(g, g.get("plan_number", 0), g.get("plan_how") or "plan")
        nxt = 1
        for g in groups:
            if g.get("number"): continue
            while nxt in used: nxt += 1
            take(g, nxt, "guess (figures.csv order)")
    return sorted(groups, key=lambda g: g["number"]), info


def pdf_caption(doc, n):
    """(page index, caption text without its label) of 'Figure n' in the compiled PDF, or None"""
    found = locate(doc, n)
    if not found: return None
    return found[0], caption_body(doc[found[0]].get_text("text", clip=found[1]))


def raster_pages(doc, root, g):
    """1-based pages of the PDF on which one of the group's raster source files is drawn (matched by pixel size); empty when unknown (vector sources)"""
    import fitz
    dims = set()
    for f in sources_of(g):
        if f.lower().endswith(RASTER):
            try: pm = fitz.Pixmap(os.path.join(root, f)); dims.add((pm.width, pm.height))
            except Exception: pass
    out = set()
    for pno, page in enumerate(doc):
        try: infos = page.get_image_info()
        except Exception: infos = []
        if any((im.get("width"), im.get("height")) in dims for im in infos): out.add(pno + 1)
    return out


def verify_numbers(root, doc, groups, texfigs):
    """check the LaTeX-order numbers against the compiled PDF: the caption printed as 'Figure N' must start like the TeX caption of the N-th environment, and
    the page that draws the figure's raster must be the caption's page. Sets g['verified'] and WARNs on a mismatch (a stale main.pdf is the usual cause)."""
    cache = {}
    def pcap(n):
        if n not in cache: cache[n] = pdf_caption(doc, n)
        return cache[n]
    for g in groups:
        g["verified"] = "not checked"
        if doc is None: g["verified"] = "no PDF"; continue
        tf = next((t for t in texfigs if t["k"] == g["number"]), None) if g.get("number_source") == "tex order" else None
        if tf is None: continue
        pc = pcap(g["number"])
        if pc is None: g["verified"] = "no caption in PDF"; continue
        ok = caps_match(tf["caption"], pc[1]); pages = raster_pages(doc, root, g)
        if ok is False:
            other = [n for n in range(1, len(texfigs) + 4) if n != g["number"] and pcap(n) and caps_match(tf["caption"], pcap(n)[1])]
            g["verified"] = "caption mismatch"
            say("WARN", f"Fig {g['number']} ({g['id']}): LaTeX 的第 {g['number']} 个 figure 环境，但 PDF 里印的 'Figure {g['number']}' 图注是「{pc[1][:50]}」" +
                (f"；这个图注在 PDF 里是 Figure {other[0]}" if other else "") + " → main.pdf 可能不是最新编译，重新编译后再 make")
        elif pages and pc[0] + 1 not in pages:
            g["verified"] = "image page mismatch"
            say("WARN", f"Fig {g['number']} ({g['id']}): 图注在第 {pc[0] + 1} 页，但这张图的位图画在第 {', '.join(map(str, sorted(pages)))} 页 → 核对 main.pdf 是否最新")
        else: g["verified"] = ("caption" if ok else "caption (nothing to compare)") + ("+image page" if pages else "")
    return groups


# ------------------------------------------------------------------ rendering
def locate(doc, n):
    """(page index, caption rect, figure region or None) of the caption `Figure n` — the first page where a figure region sits above it, else the first caption"""
    fallback = None
    for pno, page in enumerate(doc):
        for b in page.get_text("blocks"):
            if b[6] != 0: continue
            m = fp.fn.CAP_RE.search(b[4])
            if not m or b[4][:m.start()].strip() or int(m.group(1)) != n: continue
            import fitz
            cap = fitz.Rect(b[:4]); reg = fp.figure_region(page, cap)
            if reg is not None: return pno, cap, reg
            fallback = fallback or (pno, cap, None)
    return fallback


def render_printed(doc, found, outdir):
    import fitz
    pno, cap, reg = found; page = doc[pno]; H = page.rect.height
    pp = os.path.join(outdir, f"page{pno + 1}.png"); page.get_pixmap(dpi=150, alpha=False).save(pp)
    clip = fitz.Rect(reg.x0 - 4, reg.y0 - 4, reg.x1 + 4, reg.y1 + 4) if reg is not None else fitz.Rect(cap.x0, max(0, cap.y0 - 0.3 * H), cap.x1, cap.y0)
    clip &= page.rect
    cp = os.path.join(outdir, "crop.png"); page.get_pixmap(dpi=300, clip=clip, alpha=False).save(cp)
    return {"page": pp, "crop": cp, "pages": [pno + 1], "region_detected": reg is not None, "crop_pt": [round(clip.width, 1), round(clip.height, 1)]}


def render_true_scale(root, g, outdir):
    """the figure file(s) drawn at the registered print width on a white page, 300 dpi; panels flow left to right, wrapping at 183 mm"""
    import fitz
    gap = 2 * 72 / 25.4; maxw = 183 * 72 / 25.4; pan = []
    for stem in sorted(g["stems"]):
        s = g["stems"][stem]; files = sorted(s["files"], key=lambda f: (not f.lower().endswith(".pdf"), f))
        if not files: continue
        src = os.path.join(root, files[0]); wmm = s["width"] or group_width(g) or 88.0
        if src.lower().endswith(".pdf"):
            d = fitz.open(src); w0, h0 = d[0].rect.width, d[0].rect.height
        else:
            pm = fitz.Pixmap(src); w0, h0 = pm.width, pm.height; d = None
        wpt = wmm * 72 / 25.4; pan.append({"src": src, "doc": d, "w": wpt, "h": h0 / w0 * wpt})
    x = y = rowh = W = 0.0
    for p in pan:
        if x > 0 and x + p["w"] > maxw + 0.5: x, y, rowh = 0.0, y + rowh + gap, 0.0
        p["x"], p["y"] = x, y; x += p["w"] + gap; rowh = max(rowh, p["h"]); W = max(W, p["x"] + p["w"])
    H = y + rowh; out = fitz.open(); page = out.new_page(width=W, height=H)
    for p in pan:
        r = fitz.Rect(p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"])
        if p["doc"] is not None: page.show_pdf_page(r, p["doc"], 0)
        else: page.insert_image(r, filename=p["src"])
    cp = os.path.join(outdir, "true_scale.png"); page.get_pixmap(dpi=300, alpha=False).save(cp)
    return {"page": "", "crop": cp, "pages": [], "region_detected": False, "crop_pt": [round(W, 1), round(H, 1)]}


def exemplars_for(root, g, plan_rows, fig_rows, ex_rows, k=3):
    """[{thumb, paper_id, venue_year, caption_first}] — the plan row's own thumb first, then other exemplar figures of the same role (existing files, <= k)"""
    role = ""; thumbs = []
    r, _ = plan_row_for(g, plan_rows)            # the row that lists this FILE (plan `files` column); the printed number plays no part
    if r is not None:
        role = r.get("role") or ""
        if r.get("thumb"): thumbs.append(r["thumb"])
    if role:
        thumbs += [r["thumb"] for r in fig_rows if r.get("kind") == "fig" and r.get("role") == role and r.get("thumb")]
    out = []; seen = set(); by_id = {e.get("paper_id"): e for e in ex_rows}; by_thumb = {r.get("thumb"): r for r in fig_rows}
    for t in thumbs:
        if t in seen or not os.path.isfile(os.path.join(root, t)): continue
        seen.add(t); fr = by_thumb.get(t) or {}; e = by_id.get(fr.get("paper_id")) or {}
        out.append({"thumb": t, "paper_id": fr.get("paper_id", ""), "venue_year": " ".join(x for x in (e.get("venue", ""), e.get("year", "")) if x), "caption_first": (fr.get("caption_first") or "")[:120]})
        if len(out) >= k: break
    return out, role


def build_figure(root, g, doc, outdir, plan_rows, fig_rows, ex_rows):
    """render one figure into outdir -> manifest entry (with absolute image paths under key '_abs' for the prompt)"""
    os.makedirs(outdir, exist_ok=True)
    found = locate(doc, g["number"]) if doc is not None else None
    if found:
        info = render_printed(doc, found, outdir); mode = "printed"
    else:
        info = render_true_scale(root, g, outdir); mode = "true_scale"
        why = "no compiled PDF" if doc is None else f"no caption 'Figure {g['number']}' in the compiled PDF"
        say("WARN", f"Fig {g['number']}: {why} → rendered at the registered print width on a white page (true_scale), not as placed in the paper")
    exs, role = exemplars_for(root, g, plan_rows, fig_rows, ex_rows); ex_abs = []
    for i, e in enumerate(exs, 1):
        dst = os.path.join(outdir, f"ex{i}{os.path.splitext(e['thumb'])[1] or '.png'}"); shutil.copy2(os.path.join(root, e["thumb"]), dst); ex_abs.append(dst)
    srcs = sources_of(g)
    cap = ""
    if found: cap = caption_body(doc[found[0]].get_text("text", clip=found[1]))
    cap = (cap or g.get("tex_caption") or "")[:700]
    entry = {"number": g["number"], "number_source": g["number_source"], "verified": g.get("verified", "not checked"), "plan_number": g.get("plan_number", 0),
             "id": g["id"], "role": role, "caption": cap,
             "sources": [{"path": p, "sha256": sha256_of(os.path.join(root, p))} for p in srcs], "sha256": sha_of_sources(root, srcs),
             "render_sha256": sha256_of(info["crop"]), "mode": mode, "pages": info["pages"], "region_detected": info["region_detected"],
             "crop_pt": info["crop_pt"], "print_width_mm": group_width(g), "exemplars": exs,
             "exemplar_note": "" if exs else ("no exemplar of this role (no paper/figure_plan.csv row or no thumbnail)" if not role else f"no exemplar thumbnail for role '{role}'"),
             "dir": rel(root, outdir)}
    entry["_abs"] = {"page": info["page"], "crop": info["crop"], "exemplars": ex_abs}
    return entry


def fig_prompt_parts(e):
    ab = e["_abs"]; w = e["print_width_mm"]
    width_note = f"{w:g} mm wide" if w else "print width not registered"
    if e["mode"] == "printed":
        mode_note = f"from the compiled paper, page {e['pages'][0]}"
        imgs = f"- The printed page, 150 dpi: {fwd(ab['page'])}\n- The figure region cut out at true print size, 300 dpi: {fwd(ab['crop'])}"
    else:
        mode_note = "drawn at its print width on a white page; it is not yet placed in a page, so judge the figure itself"
        imgs = f"- The figure at true print size, 300 dpi: {fwd(ab['crop'])}"
    if ab["exemplars"]:
        exs = "\n".join(f"- Exemplar {i}{' (' + x['venue_year'] + ')' if x['venue_year'] else ''}: {fwd(p)}" for i, (x, p) in enumerate(zip(e["exemplars"], ab["exemplars"]), 1))
    else:
        exs = "- None supplied for this figure. Judge the venue-fit criterion from your general knowledge of the venue and say so in one line."
    return width_note, mode_note, imgs, exs


def templates():
    txt = io.open(RUBRIC, encoding="utf-8").read()
    out = {m.group(1): m.group(2) for m in re.finditer(r"<!--\s*template:\s*([\w+-]+)\s*-->\s*```[^\n]*\n(.*?)\n```", txt, re.S)}
    for need in ("rubric", "figure", "rereview", "consistency", "consistency_rereview"):
        if need not in out: die(f"references/figure-rubric.md 缺少模板 <!-- template: {need} -->")
    return out


def consistency_prompt(tpl, venue, entries, sha8, items="", dispositions=""):
    """the paper-level prompt: every figure's crop (true print size) + its caption, cross-figure questions only. `tpl` is the consistency or the
    consistency_rereview template (the latter also takes the earlier items and the author's dispositions)."""
    blocks = []
    for e in sorted(entries, key=lambda x: x["number"]):
        w = f"{e['print_width_mm']:g} mm wide" if e.get("print_width_mm") else "print width not registered"
        blocks.append(f"Figure {e['number']} ({w})\n- Crop at true print size, 300 dpi: {fwd(e['_abs']['crop'])}\n- Caption as printed: {e.get('caption') or '(not available)'}")
    m = {"venue": venue or "the target venue", "n_figs": str(len(entries)), "fig_blocks": "\n\n".join(blocks), "packet_sha": sha8, "items": items, "dispositions": dispositions}
    keep = set(re.findall(r"\{(\w+)\}", tpl)) | {"common"}
    return fill(tpl, {"common": ""}, {k: v for k, v in m.items() if k in keep})


def packet_sha(pdf_sha, entries):
    blob = json.dumps({"pdf": pdf_sha, "figures": {str(e["number"]): [e["sha256"], e["render_sha256"]] for e in entries}}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def clean(e): return {k: v for k, v in e.items() if not k.startswith("_")}


def open_pdf(root, a):
    """-> (doc or None, relative path or '', sha256 or '')"""
    if a.pdf: p = os.path.join(root, a.pdf)
    else: p = os.path.join(root, "paper", "latex", "main.pdf")
    if not os.path.isfile(p):
        if a.pdf: die(f"PDF 不存在: {a.pdf}（先编译，或不给 --pdf 走 true_scale 渲染）")
        say("INFO", "没有编译好的 paper/latex/main.pdf：按登记的印刷宽度渲染图文件（true_scale），图排进页面后要再 rereview 一次")
        return None, "", ""
    import fitz
    return fitz.open(p), rel(root, p), sha256_of(p)


def context(root):
    ex = os.path.join(root, "literature", "exemplars")
    return (fp.read_csv(os.path.join(root, "paper", "figure_plan.csv")), fp.read_csv(os.path.join(ex, "exemplar_figures.csv")), fp.read_csv(os.path.join(ex, "exemplars.csv")))


# ------------------------------------------------------------------ make
def cmd_make(a):
    root = os.path.abspath(a.project); st = load_state(root)
    family, how = infer_family(st); venue = (st.get("target") or {}).get("venue") or ""
    groups, empty = load_groups(root)
    for g in empty: say("WARN", f"figures.csv 的 {g['id']} 没有可读的源文件（{', '.join(g['missing'])}）：不审")
    if not groups: die("figures.csv 里没有可审的图（pdf / png / jpg 源文件存在的行）")
    groups, ninfo = assign_numbers(root, groups)
    base = os.path.join(root, "paper", "figure_review")
    existing = [int(m.group(1)) for d in (os.listdir(base) if os.path.isdir(base) else []) for m in [re.match(r"round(\d+)$", d)] if m]
    rnd = a.round if a.round else (max(existing) + 1 if existing else 1); out = os.path.join(base, f"round{rnd}")
    if os.path.exists(out) and not a.force: die(f"{rel(root, out)} 已存在：已登记的版本不能覆盖（改图后用 rereview；整轮重审用新的 --round；确要覆盖加 --force）")
    if os.path.exists(out): shutil.rmtree(out)
    doc, pdf_rel, pdf_sha = open_pdf(root, a); plan_rows, fig_rows, ex_rows = context(root); tpls = templates()
    verify_numbers(root, doc, groups, tex_figures(root))
    entries = [build_figure(root, g, doc, os.path.join(out, f"fig{g['number']}"), plan_rows, fig_rows, ex_rows) for g in groups]
    sha = packet_sha(pdf_sha, entries); sha8 = sha[:8]
    for e in entries:
        width_note, mode_note, imgs, exs = fig_prompt_parts(e)
        text = fill(tpls["figure"], {"common": tpls["rubric"]}, {"venue": venue or "the target venue", "number": str(e["number"]), "width_note": width_note, "mode_note": mode_note,
                    "fig_images": imgs, "exemplar_images": exs, "packet_sha": sha8})
        write_text(os.path.join(out, "prompts", f"fig{e['number']}.md"), text)
    cons = len(entries) >= 2
    if cons: write_text(os.path.join(out, "prompts", "consistency.md"), consistency_prompt(tpls["consistency"], venue, entries, sha8))
    manifest = {"round": rnd, "created": datetime.datetime.now().isoformat(timespec="seconds"), "kind": "figure_review", "venue": venue, "family": family,
                "pdf": pdf_rel, "pdf_sha256": pdf_sha, "sha256": sha, "sha8": sha8, "numbering": ninfo, "consistency_prompt": "prompts/consistency.md" if cons else "",
                "figures": [clean(e) for e in entries]}
    write_text(os.path.join(out, "manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    say("INFO", f"round {rnd}  {len(entries)} 张图  PDF {pdf_rel or '(无，true_scale)'}  packet sha8 {sha8}  venue '{venue}'  family {family} ({how})  -> {rel(root, out)}/")
    for e in entries:
        say("INFO", f"Fig {e['number']:<2d} {e['id']}  [{e['mode']}, 序号来自 {e['number_source']}（{e['verified']}）, {len(e['exemplars'])} 张范文]  -> {rel(root, os.path.join(out, 'prompts', 'fig' + str(e['number']) + '.md'))}")
    print(f"\n每个提示文件启动一个全新上下文的子代理（Agent 工具，general-purpose），提示原文整段交给它，不加任何东西；"
          f"把每个子代理返回的审稿原文贴在 paper/figure_review.md 的 `## Figure review (independent, packet {sha8})` 之下（每张图一个 `### Fig N` 块）。"
          f"图在审稿期间不能改（改了 sha 就对不上）。")
    if cons:
        print(f"\n另有一个跨图一致性提示 {rel(root, os.path.join(out, 'prompts', 'consistency.md'))}：同样一个全新子代理，返回的原文贴在同一文件的 "
              f"`## Figure consistency (independent, packet {sha8})` 之下（只有条目，没有评分）；有 [major] 时要改图后 `rereview --consistency` 复审。")


# ------------------------------------------------------------------ log parsing
def log_blocks(text):
    """[{kind: review|rereview, sha, num, text, start}] for every `### Fig N` block inside an independent (re-)review section, in file order"""
    lines = text.splitlines(); blocks = []
    for kind, rx in (("review", HEAD_FR), ("rereview", HEAD_RR)):
        for s in sections(lines, rx):
            body = s["text"].splitlines(); idx = [(i, int(m.group(1))) for i, l in enumerate(body) for m in [FIG_SUB.match(l)] if m]
            for j, (i, num) in enumerate(idx):
                end = idx[j + 1][0] if j + 1 < len(idx) else len(body)
                blocks.append({"kind": kind, "sha": s["sha"], "num": num, "text": "\n".join(body[i:end]), "start": s["start"] + i})
    return sorted(blocks, key=lambda b: b["start"])


def parse_block(text):
    scores = {}
    for ln in text.splitlines():
        m = re.match(r"^\s*[-*]?\s*scores\s*[:：]\s*(.*)$", ln, re.I)
        if m: scores.update({k.lower(): int(v) for k, v in re.findall(r"([A-Za-z_]+)\s*=\s*(\d)\b", m.group(1))})
    v = re.search(r"^\s*[-*]?\s*verdict\s*[:：]\s*[*_`]*\s*(accept|revise)", text, re.I | re.M)
    return {"scores": scores, "verdict": v.group(1).lower() if v else "", "majors": len(re.findall(r"\[major\]", text, re.I)),
            "opens": len(re.findall(r"^\s*[-*]\s*[*_`]*OPEN\b", text, re.M)), "items": [l for l in text.splitlines() if re.match(r"^\s*[-*]\s*\[(?:major|minor)\]", l, re.I)]}


def dispositions(text):
    """{figure number -> text} from the `## Figure dispositions` sections"""
    lines = text.splitlines(); out = {}
    for i, ln in enumerate(lines):
        if not HEAD_DISPO.match(ln): continue
        lvl = len(re.match(r"#+", ln).group(0)); end = len(lines)
        for j in range(i + 1, len(lines)):
            m = re.match(r"^(#+)\s", lines[j])
            if m and len(m.group(1)) <= lvl: end = j; break
        body = lines[i + 1:end]; idx = [(k, int(m.group(1)) if m.group(1) else "consistency") for k, l in enumerate(body) for m in [DISPO_SUB.match(l)] if m]
        for j, (k, num) in enumerate(idx):
            e = idx[j + 1][0] if j + 1 < len(idx) else len(body)
            out[num] = "\n".join(body[k + 1:e]).strip()
    return out


def parse_cons(text):
    """a consistency (re-)review section: verdict, open [major] item lines (only lines that ARE items), OPEN lines, all item lines"""
    items = [l for l in text.splitlines() if re.match(r"^\s*[-*]\s*[*_`]*\[(?:major|minor)\]", l, re.I)]
    v = re.search(r"^\s*[-*]?\s*verdict\s*[:：]\s*[*_`]*\s*(accept|revise)", text, re.I | re.M)
    return {"verdict": v.group(1).lower() if v else "", "majors": sum(bool(re.match(r"^\s*[-*]\s*[*_`]*\[major\]", l, re.I)) for l in items),
            "opens": len(re.findall(r"^\s*[-*]\s*[*_`]*OPEN\b", text, re.M)), "items": items}


def cons_unresolved(P): return P["verdict"] == "revise" or bool(P["majors"]) or bool(P["opens"])


def latest_cons_items(text):
    """the item lines of the latest consistency (re-)review section in the log, or ''"""
    lines = text.splitlines(); secs = sections(lines, HEAD_CONS) + sections(lines, HEAD_CONS_RR)
    if not secs: return ""
    t = max(secs, key=lambda s: s["start"])["text"]
    return "\n".join(parse_cons(t)["items"] + [l for l in t.splitlines() if re.match(r"^\s*[-*]\s*[*_`]*OPEN\b", l)])


def load_manifests(root):
    """{sha8: manifest dict} over paper/figure_review/round*/manifest.json and the rereview*/manifest.json below them"""
    out = {}
    for dp, _dn, fn_ in os.walk(os.path.join(root, "paper", "figure_review")):
        if "manifest.json" not in fn_: continue
        try: d = json.load(io.open(os.path.join(dp, "manifest.json"), encoding="utf-8"))
        except Exception: continue
        s = str(d.get("sha256") or d.get("sha8") or "").lower()
        if re.match(r"^[0-9a-f]{8}", s): out[s[:8]] = d
    return out


def entry_of(manifest, num):
    return next((e for e in (manifest or {}).get("figures", []) if e.get("number") == num), None)


# ------------------------------------------------------------------ rereview
def cmd_rereview(a):
    root = os.path.abspath(a.project); st = load_state(root)
    if not a.round: die("--round N 必填（原审稿的那一轮）")
    base = os.path.join(root, "paper", "figure_review", f"round{a.round}"); mp = os.path.join(base, "manifest.json")
    if not os.path.exists(mp): die(f"没有 {rel(root, mp)}：先 make")
    orig = json.load(io.open(mp, encoding="utf-8"))
    try: nums = [int(x) for x in re.split(r"[,\s]+", a.figs.strip()) if x]
    except ValueError: nums = []
    cons = bool(a.consistency)
    if not nums and not cons: die("--figs 2,4 必填（图号，与 make 打印的一致），或加 --consistency 复审跨图一致性")
    lp = os.path.join(root, "paper", "figure_review.md")
    if not os.path.exists(lp): die("paper/figure_review.md 不存在：先把独立审稿贴进日志并写处置")
    log = io.open(lp, encoding="utf-8").read(); blocks = log_blocks(log); dispo = dispositions(log)
    groups, _ = load_groups(root); groups, _ = assign_numbers(root, groups, quiet=True); gmap = {g["id"]: g for g in groups}; todo = []
    build_nums = [e["number"] for e in sorted(orig.get("figures", []), key=lambda x: x["number"])] if cons else nums
    if cons and len(build_nums) < 2: die(f"round{a.round} 只有 {len(build_nums)} 张图：没有跨图一致性可审")
    for n in build_nums:
        oe = entry_of(orig, n)
        if not oe: die(f"round{a.round} 的 manifest 里没有 Fig {n}")
        if oe["id"] not in gmap: die(f"figures.csv 里已没有 {oe['id']}（Fig {n}）")
        g = gmap[oe["id"]]; g["number"] = n; g["number_source"] = oe["number_source"]; todo.append((g, oe))
    doc, pdf_rel, pdf_sha = open_pdf(root, a); plan_rows, fig_rows, ex_rows = context(root); tpls = templates(); venue = orig.get("venue") or (st.get("target") or {}).get("venue") or ""
    k = 1
    while os.path.exists(os.path.join(base, "rereview" if k == 1 else f"rereview{k}")): k += 1
    out = os.path.join(base, "rereview" if k == 1 else f"rereview{k}"); entries = []; same = []
    for g, oe in todo:
        e = build_figure(root, g, doc, os.path.join(out, f"fig{g['number']}"), plan_rows, fig_rows, ex_rows); entries.append(e)
        if e["sha256"] == oe["sha256"] and e["render_sha256"] == oe["render_sha256"]: same.append(g["number"])
    refuse = (len(same) == len(todo)) if cons else bool(same)
    if refuse and not a.allow_same:
        shutil.rmtree(out, ignore_errors=True)
        die((f"没有一张图的源文件和渲染与 round{a.round} 的 packet 不同" if cons else f"Fig {', '.join(map(str, same))} 的源文件和渲染都与 round{a.round} 的 packet 相同") + "：复审要在改后的图上做（确要照样复审加 --allow-same）")
    for n in same: say("WARN", f"Fig {n} 没有变化" + ("（--allow-same）" if refuse else ""))
    sha = packet_sha(pdf_sha, entries); sha8 = sha[:8]
    if cons:
        items = latest_cons_items(log)
        if not items: say("WARN", "paper/figure_review.md 里没有一致性审稿的意见条目"); items = "(none recorded)"
        d = dispo.get("consistency", "")
        if not d.strip(): say("WARN", "没有一致性处置（`## Figure dispositions` / `### Consistency`）：先写处置再复审"); d = "(no disposition recorded)"
        write_text(os.path.join(out, "prompts", "consistency.md"), consistency_prompt(tpls["consistency_rereview"], venue, entries, sha8, items, d))
    for e in entries:
        n = e["number"]
        if n not in nums: continue
        prev = [b for b in blocks if b["num"] == n]
        items = "\n".join(parse_block(prev[-1]["text"])["items"]) if prev else ""
        if not items: say("WARN", f"Fig {n}: paper/figure_review.md 里没有原审稿的意见条目"); items = "(none recorded)"
        d = dispo.get(n, "")
        if not d.strip(): say("WARN", f"Fig {n}: 没有处置（`## Figure dispositions` / `### Fig {n}`）：先写处置再复审"); d = "(no disposition recorded)"
        width_note, mode_note, imgs, exs = fig_prompt_parts(e)
        text = fill(tpls["rereview"], {"common": tpls["rubric"]}, {"venue": venue or "the target venue", "number": str(n), "width_note": width_note, "mode_note": mode_note, "fig_images": imgs,
                    "exemplar_images": exs, "items": items, "dispositions": d, "packet_sha": sha8})
        write_text(os.path.join(out, "prompts", f"fig{n}.md"), text)
    write_text(os.path.join(out, "manifest.json"), json.dumps({"round": a.round, "created": datetime.datetime.now().isoformat(timespec="seconds"), "kind": "figure_rereview", "venue": venue,
               "family": orig.get("family", ""), "pdf": pdf_rel, "pdf_sha256": pdf_sha, "sha256": sha, "sha8": sha8, "original_sha8": orig.get("sha8", ""), "consistency": cons, "reviewed_figs": nums,
               "figures": [clean(e) for e in entries]}, ensure_ascii=False, indent=2) + "\n")
    say("INFO", f"round {a.round} rereview  Fig {', '.join(str(e['number']) for e in entries)}{'（一致性：全部图）' if cons else ''}  packet sha8 {sha8}（原 {orig.get('sha8', '')}）  -> {rel(root, out)}/")
    for n in nums: say("INFO", f"Fig {n:<2d} -> {rel(root, os.path.join(out, 'prompts', 'fig' + str(n) + '.md'))}")
    if nums: print(f"\n每张图一个全新上下文的子代理，提示原文整段交给它；返回的复审贴在 paper/figure_review.md 的 `## Figure re-review (independent, packet {sha8})` 之下（每张图一个 `### Fig N` 块）。")
    if cons:
        say("INFO", f"一致性 -> {rel(root, os.path.join(out, 'prompts', 'consistency.md'))}")
        print(f"\n一致性复审：一个全新子代理，返回的复审贴在 `## Figure consistency re-review (independent, packet {sha8})` 之下（verdict + 逐条 closed / OPEN + 新条目）。")


# ------------------------------------------------------------------ check
def cmd_check(a):
    root = os.path.abspath(a.project); groups, _ = load_groups(root)
    if not groups: say("INFO", "figures.csv 里没有可审的图（源文件存在的行）：不查图的视觉审稿"); return finish()
    new_style = os.path.exists(os.path.join(root, "paper", "figure_plan.csv"))
    lp = os.path.join(root, "paper", "figure_review.md"); text = io.open(lp, encoding="utf-8").read() if os.path.exists(lp) else ""
    lines = text.splitlines(); ind = sections(lines, HEAD_FR); ind_rr = sections(lines, HEAD_RR); manifests = load_manifests(root)
    cons = sections(lines, HEAD_CONS); cons_rr = sections(lines, HEAD_CONS_RR)
    # 1. an independent review exists
    if not ind:
        say("FAIL" if new_style else "WARN", f"{len(groups)} 张图还没有独立视觉审稿（P5：figure_review.py make → 每张图一个新上下文子代理 → 返回的审稿贴成 "
            f"`## Figure review (independent, packet <sha8>)`，写进 paper/figure_review.md）" + ("" if new_style else "；旧项目（无 paper/figure_plan.csv）只 WARN"))
    else: say("PASS", f"独立视觉审稿 {len(ind)} 节：" + ", ".join(s["sha"] for s in ind[:6]))
    # 2. packet sha8 registered
    if ind or ind_rr or cons or cons_rr:
        bad = sorted({s["sha"] for s in ind + ind_rr + cons + cons_rr} - set(manifests))
        if bad: say("FAIL", f"图的审稿不是在登记的版本上做的：packet {', '.join(bad)} 不在 paper/figure_review/round*/manifest.json（figure_review.py make / rereview 先登记）")
        else: say("PASS", "图审稿节的 packet sha8 都在 manifest.json 里登记")
    # 3/4. per figure: the latest block
    blocks = log_blocks(text); per = {}
    for b in blocks: per.setdefault(b["num"], []).append(b)
    flagged = 0
    for num in sorted(per):
        bl = per[num]; latest = bl[-1]; P = parse_block(latest["text"]); lab = f"Fig {num}"; sc = P["scores"]; before = FAILS
        miss = [c for c in CRITERIA if c not in sc]
        if miss: flagged += 1; say("WARN", f"{lab}: `scores:` 缺 {', '.join(miss)}（七项都要打分）")
        for c in CRITERIA:
            if c in sc and sc[c] <= LOW_SCORE: say("FAIL", f"{lab}: {c} = {sc[c]}（≤ {LOW_SCORE}：这一项没有达到可以排版的程度）")
        if not miss:
            mean = sum(sc[c] for c in CRITERIA) / len(CRITERIA)
            if mean < MEAN_WARN: flagged += 1; say("WARN", f"{lab}: 七项均分 {mean:.1f} < {MEAN_WARN}")
        if not P["verdict"]: flagged += 1; say("WARN", f"{lab}: 没有 `verdict: accept|revise`")
        unresolved = P["verdict"] == "revise" or P["majors"] or P["opens"]
        if latest["kind"] == "review":
            if unresolved: say("FAIL", f"{lab}: 审稿结论 revise / 仍有 [major]（{P['majors']} 条）：改图后 figure_review.py rereview，复审块 accept 才算关闭")
        else:
            prev = bl[-2] if len(bl) >= 2 else None; pm = manifests.get(prev["sha"]) if prev else None; lm = manifests.get(latest["sha"])
            pe, le = entry_of(pm, num), entry_of(lm, num)
            if prev is None: flagged += 1; say("WARN", f"{lab}: 复审块前面没有原审稿块")
            elif prev["sha"] == latest["sha"] or (pe and le and pe.get("sha256") == le.get("sha256") and pe.get("render_sha256") == le.get("render_sha256")):
                say("FAIL", f"{lab}: 复审与原审稿是同一份 packet / 同一张图（packet {latest['sha']}）：复审必须在改后的图上做（figure_review.py rereview）")
            elif unresolved: say("FAIL", f"{lab}: 复审后仍 revise / 有 [major] / OPEN：继续改，再 rereview")
        flagged += FAILS > before
        m = manifests.get(latest["sha"]); e = entry_of(m, num)
        if e and e.get("sources") is not None:
            if sha_of_sources(root, [s["path"] for s in e["sources"]]) != e.get("sha256"):
                flagged += 1; say("WARN", f"{lab} 改过、未复审：源文件现在的 sha 与最近一次审稿的 packet {latest['sha']} 不同（figure_review.py rereview --round N --figs {num}）")
    # 5. figures in the packets without a block
    reg = {}
    for m in manifests.values():
        for e in m.get("figures", []): reg.setdefault(e["number"], e)
    for num in sorted(set(reg) - set(per)):
        if ind or ind_rr: flagged += 1; say("WARN", f"Fig {num} 在 packet 里，但 paper/figure_review.md 没有它的审稿块（### Fig {num}）")
    # 6. paper-level consistency pass (one reviewer, all figures): needed once there are >= 2 figures and the per-figure reviews exist
    if len(groups) >= 2 and ind:
        if not cons: flagged += 1; say("FAIL" if new_style else "WARN", f"{len(groups)} 张图还没有跨图一致性审稿（figure_review.py make 写的 prompts/consistency.md → 一个新上下文子代理 → "
                                       f"返回的审稿贴成 `## Figure consistency (independent, packet <sha8>)`）" + ("" if new_style else "；旧项目只 WARN"))
        else:
            base_ = max(cons, key=lambda s: s["start"]); P = parse_cons(base_["text"]); latest_ = base_
            if not cons_unresolved(P): say("PASS", f"跨图一致性审稿（packet {base_['sha']}）：无 [major]，无 OPEN")
            else:
                rrs = [s for s in cons_rr if s["start"] > base_["start"]]
                if not rrs: flagged += 1; say("FAIL", f"跨图一致性：审稿结论 revise / 仍有 [major]（{P['majors']} 条）：改图后 figure_review.py rereview --consistency，复审块 accept 才算关闭")
                else:
                    latest_ = rrs[-1]; P2 = parse_cons(latest_["text"]); bm = manifests.get(base_["sha"]); lm = manifests.get(latest_["sha"])
                    def sig(m): return {e.get("number"): (e.get("sha256"), e.get("render_sha256")) for e in (m or {}).get("figures", [])}
                    if latest_["sha"] == base_["sha"] or (bm and lm and sig(bm) == sig(lm)):
                        flagged += 1; say("FAIL", f"跨图一致性：复审与原审稿是同一份 packet / 同一批图（packet {latest_['sha']}）：复审必须在改后的图上做（figure_review.py rereview --consistency）")
                    elif cons_unresolved(P2): flagged += 1; say("FAIL", "跨图一致性：复审后仍 revise / 有 [major] / OPEN：继续改，再 rereview --consistency")
                    else: say("PASS", f"跨图一致性：原审稿的 [major] 已被复审（packet {latest_['sha']}）关闭")
            lm = manifests.get(latest_["sha"]); stale = [e["number"] for e in (lm or {}).get("figures", []) if e.get("sources") is not None and sha_of_sources(root, [s["path"] for s in e["sources"]]) != e.get("sha256")]
            if stale: flagged += 1; say("WARN", f"跨图一致性审稿（packet {latest_['sha']}）之后 Fig {', '.join(map(str, stale))} 又改了：figure_review.py rereview --round N --consistency")
    if per and not flagged and FAILS == 0: say("PASS", f"{len(per)} 张图的最近一次审稿均 accept，七项都 ≥ {LOW_SCORE + 1}，均分 ≥ {MEAN_WARN}")
    return finish()


def finish():
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(FAILS)


def main():
    ap = argparse.ArgumentParser(description="independent visual review of the figures: render as printed, hand to a fresh subagent with a rubric, check the pasted reviews")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn_ in (("make", cmd_make), ("rereview", cmd_rereview), ("check", cmd_check)):
        p = sub.add_parser(name); p.set_defaults(fn=fn_); p.add_argument("--project", default=".")
        if name != "check": p.add_argument("--round", type=int, default=0); p.add_argument("--pdf", default="")
        if name == "make": p.add_argument("--force", action="store_true")
        if name == "rereview": p.add_argument("--figs", default=""); p.add_argument("--allow-same", action="store_true"); p.add_argument("--consistency", action="store_true")
    a = ap.parse_args(); a.fn(a)
    if a.cmd != "check": sys.exit(0 if FAILS == 0 else 1)


if __name__ == "__main__":
    main()
