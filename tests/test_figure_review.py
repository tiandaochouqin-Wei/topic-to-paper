# -*- coding: utf-8 -*-
"""figure_review.py (P5 independent visual review): make / rereview / check, and the review part of the G5 line of t2p.py.

Synthetic project = a research_min copy with three matplotlib figure PDFs registered in figures.csv, a compiled multi-page PDF built with PyMuPDF
(page 1 mentions "Figure 2" in running text; the captions "Figure 1/2/3" sit under the figures on pages 2-3), a figure_plan.csv with thumbnails and
exemplar_figures.csv rows. Every check below breaks exactly one rule. Numbering tests rewrite paper/latex/main.tex (_tex) and the compiled PDF (_compile(order=...))
so that the printed order differs from the plan's item numbers; the consistency tests cover the paper-level pass (prompts/consistency.md, check rule 6, rereview --consistency).
"""
import csv, io, json, os, re, struct

import pytest

from conftest import SKILL, edit, read, run, write

FIGS = {1: "figures/f_one.pdf", 2: "figures/f_two.pdf", 3: "figures/f_three.pdf"}
SCORES_OK = "scores: message=4 hierarchy=4 density=4 encoding=4 typography=4 consistency=4 venue=4"
LOG = "paper/figure_review.md"


def _draw(path, height_mm=55, bars=(1, 2, 3, 1), title="method"):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["pdf.fonttype"] = 42
    fig, ax = plt.subplots(figsize=(88 / 25.4, height_mm / 25.4)); ax.bar(range(len(bars)), bars); ax.set_xlabel(title); ax.set_ylabel("score"); fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def _compile(project, extra_pages=0, order=(1, 2, 3)):
    """paper/latex/main.pdf: p1 running text, p2 printed Figure 1 + 2, p3 printed Figure 3 (all 88 mm wide, caption below); `order` = the figure files
    (keys of FIGS) in print order, the caption of the file n reads "Caption number n compares four bars."; the default is the plan order"""
    import fitz
    doc = fitz.open(); p = doc.new_page(width=595, height=842); p.insert_text((72, 100), "Introduction. As Figure 2 shows, the bars differ.", fontsize=10)
    for _ in range(extra_pages): doc.new_page(width=595, height=842)
    pages = {}
    for pos, n in enumerate(order, 1):
        ypos, pk = ((100, "a"), (400, "a"), (100, "b"))[pos - 1]
        if pk not in pages: pages[pk] = doc.new_page(width=595, height=842)
        pg = pages[pk]; r = fitz.Rect(72, ypos, 72 + 88 / 25.4 * 72, ypos + 55 / 25.4 * 72)
        pg.show_pdf_page(r, fitz.open(str(project / FIGS[n])), 0); pg.insert_text((72, r.y1 + 14), f"Figure {pos}: Caption number {n} compares four bars.", fontsize=9)
    out = project / "paper" / "latex" / "main.pdf"; doc.save(str(out)); doc.close()


def _tex(project, order=(3, 1, 2)):
    """paper/latex/main.tex whose figure environments (with captions) come in `order`; the PDF of _compile(order=...) is what it prints"""
    body = "".join(f"\\begin{{figure}}\n\\includegraphics{{../../{FIGS[n][:-4]}}}\n\\caption{{Caption number {n} compares four bars.}}\n\\end{{figure}}\n" for n in order)
    write(project / "paper" / "latex" / "main.tex", "\\documentclass{article}\\begin{document}\n" + body + "\\end{document}\n")


def _thumb(project, name):
    import fitz
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False); pm.clear_with(200)
    p = project / "literature" / "exemplars" / "thumbs" / name; p.parent.mkdir(parents=True, exist_ok=True); pm.save(str(p)); return f"literature/exemplars/thumbs/{name}"


def _csv(path, rows):
    cols = list(rows[0]); buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(rows); write(path, buf.getvalue())


@pytest.fixture
def proj(research):
    for n, f in FIGS.items(): _draw(research / f, bars=(n, 2, 3, 1))
    write(research / "figures.csv", "file,print_width_mm,source_data,inspected,issues\n" + "".join(f"{f},88,results/summary.csv,yes,\n" for f in FIGS.values()))
    _compile(research)
    t1, t2, t3 = _thumb(research, "ex1_fig2.png"), _thumb(research, "ex2_fig5.png"), _thumb(research, "ex3_fig6.png")
    _csv(research / "paper" / "figure_plan.csv", [
        {"item": "Fig 1", "kind": "figure", "role": "main_result", "claim_ids": "C1", "files": "figures/f_one", "status": "planned", "thumb": t1, "exemplar": "modelled on P1 Fig 2"},
        {"item": "Fig 2", "kind": "figure", "role": "ablation", "claim_ids": "C2", "files": "figures/f_two", "status": "planned", "thumb": "", "exemplar": ""},
        {"item": "Fig 3", "kind": "figure", "role": "qualitative", "claim_ids": "C3", "files": "figures/f_three", "status": "planned", "thumb": "", "exemplar": ""}])
    _csv(research / "literature" / "exemplars" / "exemplar_figures.csv", [
        {"paper_id": "P1", "kind": "fig", "n": "2", "page": "5", "role": "main_result", "caption_first": "Quantitative comparison.", "thumb": t1},
        {"paper_id": "P2", "kind": "fig", "n": "5", "page": "6", "role": "main_result", "caption_first": "Comparison on the second benchmark.", "thumb": t2},
        {"paper_id": "P3", "kind": "fig", "n": "6", "page": "7", "role": "main_result", "caption_first": "Another comparison.", "thumb": t3},
        {"paper_id": "P3", "kind": "fig", "n": "7", "page": "8", "role": "main_result", "caption_first": "A fourth one.", "thumb": _thumb(research, "ex4_fig7.png")}])
    _csv(research / "literature" / "exemplars" / "exemplars.csv", [{"paper_id": "P1", "venue": "CVPR", "year": "2025"}, {"paper_id": "P2", "venue": "ICCV", "year": "2025"}, {"paper_id": "P3", "venue": "ECCV", "year": "2024"}])
    return research


def _make(p, *args):
    r = run("figure_review.py", "make", *args, cwd=p); assert r.returncode == 0 and not r.crashed, r.out; return r


def _man(p, rnd=1, sub=""):
    return json.loads(read(p / "paper" / "figure_review" / f"round{rnd}" / sub / "manifest.json"))


def _png_size(path):
    b = path.read_bytes(); assert b[:8] == b"\x89PNG\r\n\x1a\n"; return struct.unpack(">II", b[16:24])


def _check(p): return run("figure_review.py", "check", cwd=p)


def _log(p, blocks, sha, head="Figure review"):
    """paper/figure_review.md with one section; blocks = {fig number: (scores line, verdict, [items])}"""
    s = f"## {head} (independent, packet {sha})\n"
    for n, (sc, v, items) in blocks.items(): s += f"### Fig {n}\n{sc}\nverdict: {v}\n" + "".join(f"- {i}\n" for i in items)
    return s


def _cons(sha, verdict="accept", items=("[minor] panel letters bold in Fig 2, regular in Fig 3 → bold in all",), head="Figure consistency"):
    """a consistency section (no scores)"""
    return f"\n## {head} (independent, packet {sha})\nverdict: {verdict}\n" + "".join(f"- {i}\n" for i in items)


def _accept_all(p, sha, cons=True):
    write(p / LOG, _log(p, {n: (SCORES_OK, "accept", ["[minor] raise tick labels to 6.5 pt → 6.5 pt"]) for n in FIGS}, sha) + (_cons(sha) if cons else ""))


# ------------------------------------------------------------------ make
def test_make_manifest_pages_and_sources(proj):
    r = _make(proj); m = _man(proj)
    assert m["kind"] == "figure_review" and m["round"] == 1 and m["venue"] and m["family"] and m["pdf"] == "paper/latex/main.pdf" and len(m["sha8"]) == 8, m
    assert [f["number"] for f in m["figures"]] == [1, 2, 3] and all(f["mode"] == "printed" for f in m["figures"])
    assert [f["pages"] for f in m["figures"]] == [[2], [2], [3]], "page found by the caption 'Figure N', not by the running-text mention on page 1"
    import hashlib
    for f in m["figures"]:
        assert [s["path"] for s in f["sources"]] == [FIGS[f["number"]]]
        assert f["sources"][0]["sha256"] == hashlib.sha256((proj / FIGS[f["number"]]).read_bytes()).hexdigest()
        assert f["number_source"] == "plan" and (proj / f["dir"] / "crop.png").exists() and (proj / f["dir"] / f"page{f['pages'][0]}.png").exists()
    assert m["pdf_sha256"] == hashlib.sha256((proj / "paper/latex/main.pdf").read_bytes()).hexdigest()
    assert m["sha8"] in r.out and "fig1.md" in r.out and "子代理" in r.out


def test_crop_is_cut_at_true_print_size(proj):
    _make(proj); f = _man(proj)["figures"][0]; w, h = _png_size(proj / f["dir"] / "crop.png")
    assert abs(w - f["crop_pt"][0] * 300 / 72) <= 2 and abs(h - f["crop_pt"][1] * 300 / 72) <= 2, (w, h, f["crop_pt"])
    assert 0.9 * 88 / 25.4 * 300 <= w <= 88 / 25.4 * 300 + 10 * 300 / 72, f"88 mm at 300 dpi is {88 / 25.4 * 300:.0f} px, got {w}"
    pw, _ = _png_size(proj / f["dir"] / "page2.png"); assert abs(pw - 595 * 150 / 72) <= 1                                # the full page at 150 dpi


def test_prompts_have_the_images_the_rubric_and_no_author_material(proj):
    _make(proj); d = proj / "paper" / "figure_review" / "round1" / "prompts"; m = _man(proj)
    claims = read(proj / "paper" / "claims.csv"); rubric = read(SKILL / "references" / "figure-rubric.md").lower()
    words = {w for row in csv.DictReader(io.StringIO(claims)) for w in re.findall(r"[A-Za-z]{7,}", row.get("statement", "")) if w.lower() not in rubric}
    assert words, "the fixture claims must contribute words that are not in the rubric"
    for n in (1, 2, 3):
        t = read(d / f"fig{n}.md")
        assert "## Figure review (independent, packet " + m["sha8"] + ")" in t and f"### Fig {n}" in t and "Read tool" in t
        assert "hierarchy" in t and "venue fit" in t and "[major]" in t and "scores: message=N" in t
        paths = re.findall(r"(\S+\.png)", t)
        assert len(paths) >= 2 and all(os.path.exists(p) for p in paths), paths
        for banned in ("results/summary.csv", "prereg", "claims.csv", "research-state", "gap_map", "figures/f_", "source_data", "C1", "C2"): assert banned not in t, (n, banned)
        for w in list(words)[:20]: assert w not in t, (n, w)


def test_exemplars_of_the_same_role_up_to_three(proj):
    _make(proj); m = _man(proj); f1, f2 = m["figures"][0], m["figures"][1]
    assert [e["thumb"] for e in f1["exemplars"]][0] == "literature/exemplars/thumbs/ex1_fig2.png", "the plan row's own thumb comes first"
    assert len(f1["exemplars"]) == 3, "plan thumb + other main_result exemplars, capped at 3 (a fourth exists)"
    assert f1["exemplars"][0]["venue_year"] == "CVPR 2025" and all((proj / f1["dir"] / f"ex{i}.png").exists() for i in (1, 2, 3))
    assert f2["exemplars"] == [] and "no exemplar" in f2["exemplar_note"]
    t1 = read(proj / "paper/figure_review/round1/prompts/fig1.md"); t2 = read(proj / "paper/figure_review/round1/prompts/fig2.md")
    assert "Exemplar 1 (CVPR 2025)" in t1 and "None supplied for this figure" in t2


def test_no_plan_no_exemplars_is_noted(proj):
    (proj / "paper" / "figure_plan.csv").unlink(); _make(proj)
    m = _man(proj); assert all(f["exemplars"] == [] and f["exemplar_note"] for f in m["figures"])
    assert [f["number_source"] for f in m["figures"]] == ["guess (figures.csv order)"] * 3


def test_no_compiled_pdf_renders_true_scale_and_says_so(proj):
    (proj / "paper" / "latex" / "main.pdf").unlink(); r = _make(proj); m = _man(proj)
    assert m["pdf"] == "" and all(f["mode"] == "true_scale" and f["pages"] == [] for f in m["figures"]), m
    assert "true_scale" in r.out and "[WARN] figure_review: Fig 1" in r.out
    f = m["figures"][0]; w, _ = _png_size(proj / f["dir"] / "true_scale.png"); assert abs(w - 88 / 25.4 * 300) <= 1, w
    assert "drawn at its print width" in read(proj / "paper/figure_review/round1/prompts/fig1.md")


def test_caption_missing_in_the_pdf_falls_back_for_that_figure_only(proj):
    import fitz
    d = fitz.open(str(proj / "paper/latex/main.pdf")); pg = d[2]
    for b in pg.get_text("blocks"):
        if b[4].startswith("Figure 3"): pg.add_redact_annot(fitz.Rect(b[:4])); pg.apply_redactions()
    d.save(str(proj / "paper/latex/main2.pdf")); d.close()
    r = _make(proj, "--pdf", "paper/latex/main2.pdf"); m = _man(proj)
    assert [f["mode"] for f in m["figures"]] == ["printed", "printed", "true_scale"] and "no caption 'Figure 3'" in r.out


def test_panels_are_one_figure_and_tex_order_gives_the_number(proj):
    (proj / "paper" / "figure_plan.csv").unlink()
    for s in ("a", "b"): _draw(proj / "figures" / f"f_two_{s}.pdf", bars=(2, 2))
    (proj / "figures" / "f_two.pdf").unlink(); (proj / "paper" / "latex" / "main.pdf").unlink()
    write(proj / "figures.csv", "file,print_width_mm,source_data,inspected,issues\nfigures/f_one.pdf,88,r.csv,yes,\nfigures/f_two_a.pdf,44,r.csv,yes,\nfigures/f_two_b.pdf,44,r.csv,yes,\nfigures/f_three.pdf,88,r.csv,yes,\n")
    write(proj / "paper" / "latex" / "main.tex", "\\documentclass{article}\\begin{document}\n% \\begin{figure}\\includegraphics{figures/f_one}\\end{figure}\n"
          "\\begin{figure}\\includegraphics{figures/f_three.pdf}\\caption{x}\\end{figure}\n\\input{figs/two}\n\\end{document}\n")
    write(proj / "paper" / "latex" / "figs" / "two.tex", "\\begin{figure*}\\subfloat{\\includegraphics{../figures/f_two_a}}\\subfloat{\\includegraphics{../figures/f_two_b}}\\caption{two}\\end{figure*}\n"
          "\\begin{figure}\\includegraphics{figures/f_one}\\caption{one}\\end{figure}\n")
    _make(proj); m = _man(proj)
    by = {f["id"]: f for f in m["figures"]}
    assert len(m["figures"]) == 3 and set(by) == {"figures/f_one", "figures/f_two", "figures/f_three"}
    assert by["figures/f_three"]["number"] == 1 and by["figures/f_two"]["number"] == 2 and by["figures/f_one"]["number"] == 3, {k: v["number"] for k, v in by.items()}
    assert {s["path"] for s in by["figures/f_two"]["sources"]} == {"figures/f_two_a.pdf", "figures/f_two_b.pdf"} and by["figures/f_two"]["number_source"] == "tex order"
    w, h = _png_size(proj / by["figures/f_two"]["dir"] / "true_scale.png"); assert abs(w - (44 * 2 + 2) / 25.4 * 300) <= 2, "two 44 mm panels side by side with a 2 mm gap"


def test_round_is_not_overwritten_and_the_next_round_increments(proj):
    _make(proj, "--round", 2); r = run("figure_review.py", "make", "--round", 2, cwd=proj)
    assert r.returncode != 0 and "已存在" in r.out, r.out
    assert run("figure_review.py", "make", "--round", 2, "--force", cwd=proj).returncode == 0
    _make(proj); assert (proj / "paper/figure_review/round3/manifest.json").exists()


def test_no_figures_registered_fails_cleanly(proj):
    write(proj / "figures.csv", "file,print_width_mm,source_data,inspected,issues\nfigures/missing.pdf,88,r.csv,yes,\n")
    r = run("figure_review.py", "make", cwd=proj)
    assert r.returncode != 0 and "没有可审的图" in r.out and not r.crashed, r.out


# ------------------------------------------------------------------ check
def test_check_passes_on_an_accepted_registered_review(proj):
    sha = _make(proj) and _man(proj)["sha8"]; _accept_all(proj, sha)
    r = _check(proj); assert r.fails == 0 and r.returncode == 0 and "ALL PASS" in r.out and "[PASS] figure_review: 3 张图" in r.out, r.out


def test_check_without_a_review_fails_for_a_planned_project_and_warns_for_an_old_one(proj):
    r = _check(proj); assert r.fails == 1 and "还没有独立视觉审稿" in r.out, r.out
    (proj / "paper" / "figure_plan.csv").unlink(); r = _check(proj)
    assert r.fails == 0 and "[WARN] figure_review: 3 张图还没有独立视觉审稿" in r.out and "旧项目" in r.out, r.out


def test_check_ignores_projects_without_figures(proj):
    write(proj / "figures.csv", "file,print_width_mm,source_data,inspected,issues\n"); r = _check(proj)
    assert r.fails == 0 and "没有可审的图" in r.out


def test_unregistered_packet_fails(proj):
    _make(proj); _accept_all(proj, "deadbeef"); r = _check(proj)
    assert r.fails >= 1 and "deadbeef" in r.out and "不在 paper/figure_review/round*/manifest.json" in r.out, r.out


def test_a_heading_without_packet_does_not_count(proj):
    _make(proj); write(proj / LOG, "## Figure review\n### Fig 1\n" + SCORES_OK + "\nverdict: accept\n"); r = _check(proj)
    assert r.fails == 1 and "还没有独立视觉审稿" in r.out


def test_missing_criterion_warns(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); edit(proj / LOG, "### Fig 2\nscores: message=4 hierarchy=4 density=4 encoding=4 typography=4 consistency=4 venue=4",
                                                                            "### Fig 2\nscores: message=4 hierarchy=4 density=4 encoding=4 typography=4 consistency=4")
    r = _check(proj); assert r.fails == 0 and "[WARN] figure_review: Fig 2: `scores:` 缺 venue" in r.out, r.out


def test_a_score_of_two_fails_naming_the_criterion(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); edit(proj / LOG, "### Fig 2\nscores: message=4 hierarchy=4", "### Fig 2\nscores: message=4 hierarchy=2")
    r = _check(proj); assert r.fails == 1 and "Fig 2: hierarchy = 2" in r.out and "Fig 1:" not in r.out.replace("3 张图", ""), r.out


def test_low_mean_warns(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; low = "scores: message=3 hierarchy=3 density=3 encoding=3 typography=3 consistency=3 venue=4"
    write(proj / LOG, _log(proj, {1: (low, "accept", []), 2: (SCORES_OK, "accept", []), 3: (SCORES_OK, "accept", [])}, sha) + _cons(sha)); r = _check(proj)
    assert r.fails == 0 and "[WARN] figure_review: Fig 1: 七项均分 3.1 < 3.5" in r.out and "Fig 2: 七项均分" not in r.out, r.out


def test_verdict_revise_fails(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); edit(proj / LOG, "### Fig 3\n" + SCORES_OK + "\nverdict: accept", "### Fig 3\n" + SCORES_OK + "\nverdict: revise")
    r = _check(proj); assert r.fails == 1 and "Fig 3: 审稿结论 revise" in r.out, r.out


def test_a_major_item_fails_even_when_the_verdict_says_accept(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); edit(proj / LOG, "- [minor] raise tick labels to 6.5 pt → 6.5 pt\n### Fig 3", "- [major] drop panel (c), it repeats Table 2 → drop panel (c)\n### Fig 3")
    r = _check(proj); assert r.fails == 1 and "Fig 2: 审稿结论 revise / 仍有 [major]" in r.out, r.out


def _revise_then_fix(proj):
    """round 1 asks for changes to Fig 2; the author redraws it and recompiles; rereview registers the new packet -> returns (sha1, sha2)"""
    m = _man(proj); sha1 = m["sha8"]
    write(proj / LOG, _log(proj, {1: (SCORES_OK, "accept", []), 2: ("scores: message=4 hierarchy=3 density=4 encoding=4 typography=4 consistency=4 venue=4", "revise",
                                  ["[major] the bars have equal weight → ours red, others grey"]), 3: (SCORES_OK, "accept", [])}, sha1)
          + _cons(sha1) + "\n## Figure dispositions\n### Fig 2\nrecoloured: ours is now the only red bar.\n")
    _draw(proj / FIGS[2], bars=(5, 1, 1, 1), title="method (ours = red)"); _compile(proj)
    r = run("figure_review.py", "rereview", "--round", 1, "--figs", "2", cwd=proj); assert r.returncode == 0 and not r.crashed, r.out
    return sha1, _man(proj, 1, "rereview")["sha8"], r


def test_rereview_prompt_carries_items_dispositions_and_new_renders(proj):
    _make(proj); sha1, sha2, r = _revise_then_fix(proj)
    assert sha1 != sha2 and _man(proj, 1, "rereview")["original_sha8"] == sha1 and [f["number"] for f in _man(proj, 1, "rereview")["figures"]] == [2]
    t = read(proj / "paper/figure_review/round1/rereview/prompts/fig2.md")
    assert "ours red, others grey" in t and "recoloured: ours is now the only red bar." in t and "## Figure re-review (independent, packet " + sha2 + ")" in t and "OPEN" in t
    assert (proj / "paper/figure_review/round1/rereview/fig2/crop.png").exists() and not (proj / "paper/figure_review/round1/rereview/prompts/fig1.md").exists()


def test_rereview_refuses_an_unchanged_figure_unless_allowed(proj):
    _make(proj); write(proj / LOG, _log(proj, {2: (SCORES_OK, "revise", ["[major] x → y"])}, _man(proj)["sha8"]))
    r = run("figure_review.py", "rereview", "--round", 1, "--figs", "2", cwd=proj)
    assert r.returncode != 0 and "相同" in r.out and not (proj / "paper/figure_review/round1/rereview").exists(), r.out
    r = run("figure_review.py", "rereview", "--round", 1, "--figs", "2", "--allow-same", cwd=proj); assert r.returncode == 0 and "没有变化" in r.out
    assert run("figure_review.py", "rereview", "--round", 1, "--figs", "2", "--allow-same", cwd=proj).returncode == 0 and (proj / "paper/figure_review/round1/rereview2/manifest.json").exists()


def test_rereview_warns_without_a_disposition(proj):
    _make(proj); sha1 = _man(proj)["sha8"]; write(proj / LOG, _log(proj, {2: (SCORES_OK, "revise", ["[major] x → y"])}, sha1))
    _draw(proj / FIGS[2], bars=(9, 1, 1, 1)); _compile(proj); r = run("figure_review.py", "rereview", "--round", 1, "--figs", "2", cwd=proj)
    assert r.returncode == 0 and "Fig 2: 没有处置" in r.out and "(no disposition recorded)" in read(proj / "paper/figure_review/round1/rereview/prompts/fig2.md")


def test_rereview_unknown_figure_fails_cleanly(proj):
    _make(proj); write(proj / LOG, _log(proj, {2: (SCORES_OK, "revise", ["[major] x → y"])}, _man(proj)["sha8"]))
    r = run("figure_review.py", "rereview", "--round", 1, "--figs", "9", cwd=proj)
    assert r.returncode != 0 and "没有 Fig 9" in r.out and not r.crashed


def test_a_later_independent_rereview_on_a_new_packet_closes_the_major(proj):
    _make(proj); sha1, sha2, _ = _revise_then_fix(proj)
    s = read(proj / LOG) + "\n" + _log(proj, {2: (SCORES_OK, "accept", ["closed: ours red, others grey"])}, sha2, head="Figure re-review")
    write(proj / LOG, s); r = _check(proj)
    assert r.fails == 0 and "Fig 2: 审稿结论" not in r.out and "改过、未复审" not in r.out, r.out


def test_rereview_on_the_same_packet_does_not_close(proj):
    _make(proj); sha1, sha2, _ = _revise_then_fix(proj)
    write(proj / LOG, read(proj / LOG) + "\n" + _log(proj, {2: (SCORES_OK, "accept", [])}, sha1, head="Figure re-review"))
    r = _check(proj); assert r.fails == 1 and "Fig 2: 复审与原审稿是同一份 packet" in r.out, r.out


def test_rereview_still_revise_or_open_fails(proj):
    _make(proj); sha1, sha2, _ = _revise_then_fix(proj)
    base = read(proj / LOG)
    write(proj / LOG, base + "\n" + _log(proj, {2: (SCORES_OK, "revise", ["[minor] z → w"])}, sha2, head="Figure re-review"))
    r = _check(proj); assert r.fails == 1 and "Fig 2: 复审后仍 revise" in r.out, r.out
    write(proj / LOG, base + "\n" + _log(proj, {2: (SCORES_OK, "accept", ["OPEN: ours red, others grey → still the same weight"])}, sha2, head="Figure re-review"))
    r = _check(proj); assert r.fails == 1 and "Fig 2: 复审后仍 revise" in r.out, r.out


def test_rereview_with_a_score_of_two_does_not_close(proj):
    _make(proj); sha1, sha2, _ = _revise_then_fix(proj)
    write(proj / LOG, read(proj / LOG) + "\n" + _log(proj, {2: ("scores: message=4 hierarchy=4 density=2 encoding=4 typography=4 consistency=4 venue=4", "accept", [])}, sha2, head="Figure re-review"))
    r = _check(proj); assert r.fails == 1 and "Fig 2: density = 2" in r.out, r.out


def test_a_figure_changed_after_its_review_warns(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); _draw(proj / FIGS[3], bars=(7, 7, 7, 7))
    r = _check(proj); assert r.fails == 0 and "[WARN] figure_review: Fig 3 改过、未复审" in r.out and "Fig 1 改过" not in r.out, r.out


def test_a_figure_in_the_packet_without_a_block_warns(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]
    write(proj / LOG, _log(proj, {1: (SCORES_OK, "accept", []), 2: (SCORES_OK, "accept", [])}, sha) + _cons(sha)); r = _check(proj)
    assert r.fails == 0 and "[WARN] figure_review: Fig 3 在 packet 里，但" in r.out, r.out


# ------------------------------------------------------------------ G5 line of t2p.py check
def _g5(p):
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=p); return [l for l in r.out.splitlines() if "G5" in l and l.startswith("[")][0], r


def test_g5_line_carries_the_review_counts(proj):
    line, _ = _g5(proj)
    assert line.startswith("[FAIL] G5") and "review 1 FAIL / 0 WARN" in line, line                        # planned project, no review yet
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha)
    line, _ = _g5(proj); assert "review 0 FAIL / 0 WARN" in line and "plan 0 FAIL" in line, line
    edit(proj / LOG, "### Fig 1\n" + SCORES_OK, "### Fig 1\nscores: message=4 hierarchy=4 density=2 encoding=4 typography=4 consistency=4 venue=4")
    line, _ = _g5(proj); assert line.startswith("[FAIL] G5") and "review 1 FAIL" in line, line


def test_g5_review_of_an_old_project_is_only_a_warn(proj):
    (proj / "paper" / "figure_plan.csv").unlink(); line, _ = _g5(proj)
    assert "review 0 FAIL / 1 WARN" in line and not line.startswith("[FAIL] G5"), line


# ------------------------------------------------------------------ numbering = what is printed
def test_latex_order_beats_the_plan_numbering_and_exemplars_follow_the_file_role(proj):
    """the plan numbers f_one/f_two/f_three 1/2/3, the .tex (and the compiled PDF) print f_three/f_one/f_two"""
    _tex(proj, (3, 1, 2)); _compile(proj, order=(3, 1, 2)); r = _make(proj); m = _man(proj); by = {f["id"]: f for f in m["figures"]}
    assert [f["id"] for f in m["figures"]] == ["figures/f_three", "figures/f_one", "figures/f_two"], "sorted by the printed number"
    assert [f["number"] for f in m["figures"]] == [1, 2, 3] and all(f["number_source"] == "tex order" and f["verified"].startswith("caption") for f in m["figures"]), m
    assert [by[k]["plan_number"] for k in ("figures/f_one", "figures/f_two", "figures/f_three")] == [1, 2, 3]
    assert "[WARN] figure_review: 图表计划的序号与 LaTeX 的出图顺序不一致" in r.out and "figures/f_one: plan Fig 1 → LaTeX Figure 2" in r.out and "figures/f_three: plan Fig 3 → LaTeX Figure 1" in r.out, r.out
    assert len(m["numbering"]["mismatches"]) == 3 and m["numbering"]["source"] == "tex order"
    assert "Caption number 3" in by["figures/f_three"]["caption"] and by["figures/f_three"]["pages"] == [2] and by["figures/f_two"]["pages"] == [3], "printed Figure 1 sits on page 2, Figure 3 on page 3"
    # exemplars: the role of the plan row that lists the FILE, whatever number the figure has now
    assert by["figures/f_one"]["role"] == "main_result" and len(by["figures/f_one"]["exemplars"]) == 3 and by["figures/f_one"]["exemplars"][0]["venue_year"] == "CVPR 2025"
    assert by["figures/f_three"]["role"] == "qualitative" and by["figures/f_three"]["exemplars"] == [] and by["figures/f_two"]["role"] == "ablation"
    d = proj / "paper/figure_review/round1/prompts"
    assert "None supplied for this figure" in read(d / "fig1.md") and "Exemplar 1 (CVPR 2025)" in read(d / "fig2.md")


def test_plan_numbering_is_kept_when_it_agrees_with_the_latex_order(proj):
    _tex(proj, (1, 2, 3)); _compile(proj, order=(1, 2, 3)); r = _make(proj); m = _man(proj)
    assert [f["id"] for f in m["figures"]] == ["figures/f_one", "figures/f_two", "figures/f_three"] and all(f["number_source"] == "tex order" for f in m["figures"])
    assert "不一致" not in r.out and m["numbering"]["mismatches"] == []


def test_a_stale_pdf_is_warned_about(proj):
    _tex(proj, (3, 1, 2)); _compile(proj, order=(1, 2, 3))                 # the .tex was reordered after the last compile
    r = _make(proj); m = _man(proj)
    assert "caption mismatch" in {f["verified"] for f in m["figures"]} and "[WARN] figure_review: Fig 1 (figures/f_three)" in r.out and "不是最新编译" in r.out, r.out


def test_a_figure_not_in_main_tex_gets_a_free_number_after_the_printed_ones(proj):
    write(proj / "paper" / "latex" / "main.tex", "\\documentclass{article}\\begin{document}\n\\begin{figure}\\includegraphics{../../figures/f_two}\\caption{Caption number 2 compares four bars.}\\end{figure}\n\\end{document}\n")
    r = _make(proj); by = {f["id"]: f for f in _man(proj)["figures"]}
    assert by["figures/f_two"]["number"] == 1 and by["figures/f_two"]["number_source"] == "tex order"
    assert {by["figures/f_one"]["number"], by["figures/f_three"]["number"]} == {2, 3} and by["figures/f_one"]["number_source"] == "guess (not in main.tex)"
    assert "figures/f_one 不在 paper/latex/main.tex" in r.out


def test_two_files_in_one_figure_environment_are_one_figure(proj):
    write(proj / "paper" / "latex" / "main.tex", "\\documentclass{article}\\begin{document}\n\\begin{figure}\\includegraphics{../../figures/f_one}\\includegraphics{../../figures/f_two}"
          "\\caption{Caption number 1 compares four bars.}\\end{figure}\n\\begin{figure}\\includegraphics{../../figures/f_three}\\caption{Caption number 3 compares four bars.}\\end{figure}\n\\end{document}\n")
    (proj / "paper" / "latex" / "main.pdf").unlink(); _make(proj); m = _man(proj)
    assert [(f["number"], f["id"]) for f in m["figures"]] == [(1, "figures/f_one+figures/f_two"), (2, "figures/f_three")]
    assert {s["path"] for s in m["figures"][0]["sources"]} == {"figures/f_one.pdf", "figures/f_two.pdf"}


def test_a_float_without_a_caption_gets_no_number(proj):
    write(proj / "paper" / "latex" / "main.tex", "\\documentclass{article}\\begin{document}\n\\begin{figure}\\includegraphics{../../figures/f_one}\\end{figure}\n"
          "\\begin{figure}\\includegraphics{../../figures/f_two}\\caption{x}\\end{figure}\n\\begin{figure}\\includegraphics{../../figures/f_three}\\caption{y}\\end{figure}\n\\end{document}\n")
    (proj / "paper" / "latex" / "main.pdf").unlink(); _make(proj); by = {f["id"]: f for f in _man(proj)["figures"]}
    assert by["figures/f_two"]["number"] == 1 and by["figures/f_three"]["number"] == 2 and by["figures/f_one"]["number_source"] == "guess (not in main.tex)"


# ------------------------------------------------------------------ cross-figure consistency pass
def test_consistency_prompt_has_all_crops_captions_and_only_cross_figure_questions(proj):
    _tex(proj, (3, 1, 2)); _compile(proj, order=(3, 1, 2)); _make(proj); m = _man(proj); t = read(proj / "paper/figure_review/round1/prompts/consistency.md")
    assert m["consistency_prompt"] == "prompts/consistency.md"
    assert "## Figure consistency (independent, packet " + m["sha8"] + ")" in t and "Read tool" in t and "true print size" in t
    for f in m["figures"]:
        assert f"Figure {f['number']} (88 mm wide)" in t and f"Caption as printed: Caption number" in t and f["caption"] in t
    crops = re.findall(r"(\S+crop\.png)", t); assert len(crops) == 3 and all(os.path.exists(c) for c in crops), crops
    for must in ("same colour", "marker", "line style", "NAME", "font family", "panel letters", "axis label", "L_rel", "F6R", "out0", "params_M", "[major]", "[minor]", "No scores"): assert must in t, must
    for banned in ("scores: message", "hierarchy", "venue fit", "page2.png", "ex1.png", "Exemplar", "results/summary.csv", "prereg", "claims.csv", "research-state", "figures/f_", "source_data"): assert banned not in t, banned
    assert "Caption number 3 compares four bars" in t.split("Figure 1 (")[1].split("Figure 2 (")[0], "the caption belongs to the printed number"


def test_no_consistency_prompt_for_a_single_figure(proj):
    write(proj / "figures.csv", "file,print_width_mm,source_data,inspected,issues\nfigures/f_one.pdf,88,r.csv,yes,\n"); _make(proj)
    assert not (proj / "paper/figure_review/round1/prompts/consistency.md").exists() and _man(proj)["consistency_prompt"] == ""
    sha = _man(proj)["sha8"]; write(proj / LOG, _log(proj, {1: (SCORES_OK, "accept", [])}, sha)); r = _check(proj)
    assert r.fails == 0 and "一致性" not in r.out, r.out


def test_check_without_a_consistency_block_fails_for_a_planned_project_and_warns_for_an_old_one(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha, cons=False); r = _check(proj)
    assert r.fails == 1 and "[FAIL] figure_review: 3 张图还没有跨图一致性审稿" in r.out, r.out
    (proj / "paper" / "figure_plan.csv").unlink(); r = _check(proj)
    assert r.fails == 0 and "[WARN] figure_review: 3 张图还没有跨图一致性审稿" in r.out and "旧项目" in r.out, r.out


def test_consistency_pass_does_not_double_count_a_missing_figure_review(proj):
    _make(proj); r = _check(proj); assert r.fails == 1 and "一致性" not in r.out, r.out


def test_consistency_with_only_minor_items_passes(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); r = _check(proj)
    assert r.fails == 0 and "ALL PASS" in r.out and "跨图一致性审稿" in r.out, r.out


def test_an_open_consistency_major_fails_even_when_the_verdict_says_accept(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]
    write(proj / LOG, _log(proj, {n: (SCORES_OK, "accept", []) for n in FIGS}, sha) + _cons(sha, "accept", ["[major] Fig 2, Fig 4: ours red vs blue → ours red everywhere"]))
    r = _check(proj); assert r.fails == 1 and "跨图一致性：审稿结论 revise / 仍有 [major]（1 条）" in r.out, r.out
    write(proj / LOG, _log(proj, {n: (SCORES_OK, "accept", []) for n in FIGS}, sha) + _cons(sha, "revise", ["[minor] z → w"]))
    r = _check(proj); assert r.fails == 1 and "跨图一致性：审稿结论 revise" in r.out, r.out


def test_an_unregistered_consistency_packet_fails(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]
    write(proj / LOG, _log(proj, {n: (SCORES_OK, "accept", []) for n in FIGS}, sha) + _cons("deadbeef")); r = _check(proj)
    assert r.fails >= 1 and "deadbeef" in r.out and "不在 paper/figure_review/round*/manifest.json" in r.out, r.out


def _cons_major_then_fix(proj, redraw=True):
    """round 1: consistency says [major] on colours; the author recolours Fig 2 and recompiles; rereview --consistency -> (sha1, sha2, result)"""
    sha1 = _man(proj)["sha8"]
    write(proj / LOG, _log(proj, {n: (SCORES_OK, "accept", []) for n in FIGS}, sha1) + _cons(sha1, "revise", ["[major] Fig 1, Fig 2: ours is red in Fig 1 and blue in Fig 2 → ours red in both"])
          + "\n## Figure dispositions\n### Consistency\nFig 2 recoloured: ours is red now.\n")
    if redraw: _draw(proj / FIGS[2], bars=(5, 1, 1, 1), title="method (ours = red)"); _compile(proj)
    r = run("figure_review.py", "rereview", "--round", 1, "--consistency", cwd=proj)
    return sha1, (_man(proj, 1, "rereview")["sha8"] if redraw else ""), r


def test_rereview_consistency_prompt_carries_items_dispositions_and_all_new_crops(proj):
    _make(proj); sha1, sha2, r = _cons_major_then_fix(proj); assert r.returncode == 0 and not r.crashed, r.out
    m = _man(proj, 1, "rereview"); t = read(proj / "paper/figure_review/round1/rereview/prompts/consistency.md")
    assert m["consistency"] is True and m["original_sha8"] == sha1 and sha1 != sha2 and [f["number"] for f in m["figures"]] == [1, 2, 3] and m["reviewed_figs"] == []
    assert "ours red in both" in t and "Fig 2 recoloured: ours is red now." in t and "## Figure consistency re-review (independent, packet " + sha2 + ")" in t and "OPEN" in t
    crops = re.findall(r"(\S+crop\.png)", t); assert len(crops) == 3 and all("rereview" in c and os.path.exists(c) for c in crops), crops
    assert not list((proj / "paper/figure_review/round1/rereview/prompts").glob("fig*.md")), "no per-figure prompt unless --figs is given"


def test_rereview_consistency_refuses_unchanged_figures_unless_allowed(proj):
    _make(proj); _, _, r = _cons_major_then_fix(proj, redraw=False)
    assert r.returncode != 0 and "没有一张图" in r.out and not (proj / "paper/figure_review/round1/rereview").exists(), r.out
    assert run("figure_review.py", "rereview", "--round", 1, "--consistency", "--allow-same", cwd=proj).returncode == 0


def test_consistency_rereview_on_a_new_packet_with_accept_closes_the_major(proj):
    _make(proj); sha1, sha2, _ = _cons_major_then_fix(proj)
    write(proj / LOG, read(proj / LOG) + _cons(sha2, "accept", ["closed: Fig 1, Fig 2: ours red in both"], head="Figure consistency re-review"))
    r = _check(proj); assert r.fails == 0 and "原审稿的 [major] 已被复审" in r.out and "又改了" not in r.out, r.out


def test_consistency_rereview_on_the_same_packet_or_with_open_does_not_close(proj):
    _make(proj); sha1, sha2, _ = _cons_major_then_fix(proj); base = read(proj / LOG)
    write(proj / LOG, base + _cons(sha1, "accept", [], head="Figure consistency re-review")); r = _check(proj)
    assert r.fails == 1 and "跨图一致性：复审与原审稿是同一份 packet" in r.out, r.out
    write(proj / LOG, base + _cons(sha2, "accept", ["OPEN: ours red in both → Fig 2 still blue"], head="Figure consistency re-review")); r = _check(proj)
    assert r.fails == 1 and "跨图一致性：复审后仍 revise" in r.out, r.out
    write(proj / LOG, base + _cons(sha2, "revise", ["[minor] z → w"], head="Figure consistency re-review")); r = _check(proj)
    assert r.fails == 1 and "跨图一致性：复审后仍 revise" in r.out, r.out


def test_figures_changed_after_the_consistency_review_warn(proj):
    sha = (_make(proj), _man(proj)["sha8"])[1]; _accept_all(proj, sha); _draw(proj / FIGS[1], bars=(9, 9, 9, 9)); r = _check(proj)
    assert r.fails == 0 and "[WARN] figure_review: 跨图一致性审稿（packet " + sha + "）之后 Fig 1 又改了" in r.out, r.out
