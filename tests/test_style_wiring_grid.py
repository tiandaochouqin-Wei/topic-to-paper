# -*- coding: utf-8 -*-
"""The figure style registry (figure_style.py) wired into make_comparison.py grid (column labels, role colours, cell counts, display gamma, cmap, meta + caption files, source.csv
style columns), the select_samples.py -> grid hand-over, and the style / caption part of the G5 line of t2p.py. Synthetic 64x48 images and a few boxes; the photos are one raster
inside the PDF, so colour checks probe the 400 dpi png."""
import csv
import io
import json
import re

import numpy as np
from PIL import Image

from conftest import edit, read, run, write

STYLE = """figures:
  style:
    ours: [relroute_l]
    methods:
      relroute_l: {label: "RelRoute (ours)", color: "#c94a5e", line: "-", marker: "o"}
      smm: {label: "SMM", color: "#4a4a4a", line: "--", marker: "s"}
    roles: {gt: "#ffd23f", tp: "#2e9b57", fp: "#e08a00", fn: "#d9d9d9", ours_frame: "#1f1f1f", baseline_line: "#8a8a8a"}
    font_pt: 7
"""
YELLOW = np.array([0xff, 0xd2, 0x3f]); GREEN = np.array([0x2e, 0x9b, 0x57]); ORANGE = np.array([0xe0, 0x8a, 0x00]); LGREY = np.array([0xd9, 0xd9, 0xd9]); OURS = np.array([0xc9, 0x4a, 0x5e])


def _world(tmp_path, methods=("GT", "smm", "relroute_l"), samples=("s1",), grey=(90, 120, 150)):
    for m in methods:
        for s in samples:
            p = tmp_path / "imgs" / m / f"{s}.png"; p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 48), grey).save(p)


def _grid(tmp_path, *extra, methods="GT,smm,relroute_l", samples="s1", out="figures/g.png", width=100):
    return run("make_comparison.py", "grid", "--root", "imgs", "--methods", methods, "--samples", samples, "--out", out, "--width-mm", width, "--project", ".", *extra, cwd=tmp_path)


def _rows(p): return list(csv.DictReader(io.open(p, encoding="utf-8")))
def _json(p): return json.loads(io.open(p, encoding="utf-8").read())
def _near(png, rgb, tol=40): return np.abs(np.asarray(Image.open(png).convert("RGB")).astype(int) - rgb).sum(-1) <= tol


def _text(pdf):
    import fitz
    return "".join(pg.get_text() for pg in fitz.open(pdf))


def _boxes(tmp_path):
    """GT: two boxes; smm: one TP + one FP, the second ground-truth box is missed"""
    write(tmp_path / "lab" / "GT" / "s1.txt", "0 0.30 0.40 0.20 0.30\n0 0.75 0.60 0.20 0.30\n")
    write(tmp_path / "lab" / "smm" / "s1.txt", "0 0.30 0.40 0.20 0.30 0.9\n0 0.60 0.20 0.10 0.10 0.8\n")
    write(tmp_path / "lab" / "relroute_l" / "s1.txt", "0 0.30 0.40 0.20 0.30 0.9\n0 0.75 0.60 0.20 0.30 0.9\n")


# ------------------------------------------------------------------ labels, ours, style columns, meta + caption
def test_column_labels_come_from_the_registry_and_ours_is_framed(tmp_path):
    _world(tmp_path); write(tmp_path / "research-state.yaml", STYLE)
    r = _grid(tmp_path, "--row-labels", "none")
    assert r.returncode == 0 and not r.crashed, r.out
    txt = _text(tmp_path / "figures" / "g.pdf")
    assert "SMM" in txt and "RelRoute (ours)" in txt and "relroute_l" not in txt             # registry labels, never the directory (= registry key) names
    rows = {x["method"]: x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows["relroute_l"]["highlight"] == "yes" and rows["smm"]["highlight"] == "no"       # figures.style.ours frames the column without --highlight
    for m, lab, col in (("smm", "SMM", "#4a4a4a"), ("relroute_l", "RelRoute (ours)", "#c94a5e")):
        assert (rows[m]["label"], rows[m]["color"], rows[m]["line"], rows[m]["marker"]) == (lab, col, "--" if m == "smm" else "-", "s" if m == "smm" else "o")   # style columns of the source.csv
    png = tmp_path / "figures" / "g.png"; w = Image.open(png).size[0]
    dark = _near(png, np.array([0x1f, 0x1f, 0x1f]), 12)
    assert dark[:, 2 * w // 3:].sum() > 300 and _near(png, OURS).sum() == 0                  # the frame is the neutral ours_frame role, no red anywhere


def test_meta_and_caption_files_state_what_was_drawn(tmp_path):
    _world(tmp_path); _boxes(tmp_path); write(tmp_path / "research-state.yaml", STYLE)
    r = _grid(tmp_path, "--labels-dir", "lab", "--box-status", "--inset", "0.1,0.1,0.3,0.3", "--display-gamma", "0.5")
    assert r.returncode == 0, r.out
    meta = _json(tmp_path / "figures" / "g.meta.json")
    assert meta["kind"] == "grid" and meta["box_status"] is True and meta["roles_used"][:1] == ["gt"] and {"tp", "fp", "fn"} <= set(meta["roles_used"])
    assert meta["roles"]["fp"] == "#e08a00" and meta["roles"]["gt"] == "#ffd23f" and meta["inset"] == [0.1, 0.1, 0.3, 0.3] and meta["display_gamma"] == 0.5 and meta["min_box_pt"] >= 0.8
    assert meta["styles"]["relroute_l"]["label"] == "RelRoute (ours)"
    cap = read(tmp_path / "figures" / "g.caption.md")
    assert cap.startswith("<takeaway") and "orange dashed = false positive" in cap and "green solid = true positive" in cap and "yellow" in cap and "light grey dotted = missed ground truth" in cap
    assert "Inset" in cap and "brightened for display only" in cap and "RelRoute (ours)" in cap
    assert "[INFO] caption draft" in r.out


# ------------------------------------------------------------------ code-like labels, roles, box status
def test_code_like_directory_name_is_a_fail_unless_allowed(tmp_path):
    _world(tmp_path, methods=("GT", "chgate")); write(tmp_path / "research-state.yaml", STYLE)
    r = _grid(tmp_path, methods="GT,chgate")
    assert r.fails == 1 and r.returncode != 0 and "chgate" in r.out and "--allow-code-labels" in r.out, r.out
    r2 = _grid(tmp_path, "--allow-code-labels", methods="GT,chgate", out="figures/ok.png")
    assert r2.returncode == 0 and "[WARN] method name 'chgate' reads like code" in r2.out, r2.out
    r3 = _grid(tmp_path, "--col-labels", "Ground truth,Channel gate", methods="GT,chgate", out="figures/named.png")      # an explicit readable label clears it
    assert r3.returncode == 0 and r3.fails == 0, r3.out


def test_unregistered_method_is_a_warn_when_a_registry_exists(tmp_path):
    _world(tmp_path, methods=("GT", "Concat")); write(tmp_path / "research-state.yaml", STYLE)
    r = _grid(tmp_path, methods="GT,Concat")
    assert r.returncode == 0 and "[WARN] method name 'Concat' is not registered" in r.out, r.out


def test_box_status_uses_the_role_colours_and_a_four_entry_legend(tmp_path):
    _world(tmp_path); _boxes(tmp_path); write(tmp_path / "research-state.yaml", STYLE)
    r = _grid(tmp_path, "--labels-dir", "lab", "--box-status", "--row-labels", "none")
    assert r.returncode == 0, r.out
    assert "box status (IoU >= 0.5, class-aware; per method TP/FP/FN): smm 1/1/1; relroute_l 2/0/0" in r.out, r.out
    png = tmp_path / "figures" / "g.png"; w = Image.open(png).size[0]; col = lambda a, i: a[:, i * w // 3:(i + 1) * w // 3].sum()
    yel, grn, org, lgr = (_near(png, c) for c in (YELLOW, GREEN, ORANGE, LGREY))
    assert col(yel, 0) > 200 and col(yel, 1) == 0 and col(yel, 2) == 0                       # GT column: the gt role (yellow)
    assert col(grn, 1) > 100 and col(org, 1) > 100 and col(lgr, 1) > 100                     # smm: TP green, FP orange, missed ground truth light grey
    assert col(org, 2) == 0 and col(grn, 2) > 200                                            # relroute_l: two TP, nothing orange
    txt = _text(tmp_path / "figures" / "g.pdf")
    assert "Ground truth" in txt and "TP (IoU >= 0.5)" in txt and "FP" in txt and "FN (missed ground truth)" in txt
    cap = read(tmp_path / "figures.csv")
    assert "green solid = true positive" in cap and "orange dashed = false positive" in cap


def test_prediction_boxes_without_status_use_the_method_colour(tmp_path):
    _world(tmp_path); _boxes(tmp_path); write(tmp_path / "research-state.yaml", STYLE)
    r = _grid(tmp_path, "--labels-dir", "lab", "--row-labels", "none")
    assert r.returncode == 0, r.out
    rows = {x["method"]: x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows["GT"]["box_color"].lower() == "#ffd23f" and rows["relroute_l"]["box_color"].lower() == "#c94a5e" and rows["smm"]["box_color"].lower() == "#4a4a4a"
    assert _json(tmp_path / "figures" / "g.meta.json")["roles_used"] == ["gt", "ours_frame"]


# ------------------------------------------------------------------ cmap, gamma
def test_overlay_default_cmap_is_viridis_and_jet_is_refused(tmp_path):
    _world(tmp_path, methods=("GT",), samples=("a",)); write(tmp_path / "research-state.yaml", STYLE)
    m = np.zeros((16, 16), np.float32); m[4:8, 4:8] = 3.0; m[0, 0] = 5.0
    (tmp_path / "cam" / "smm").mkdir(parents=True); np.save(tmp_path / "cam" / "smm" / "a.npy", m)
    r = _grid(tmp_path, "--overlay-dir", "cam", methods="GT,smm", samples="a", width=90)
    assert r.returncode == 0, r.out
    a = np.asarray(Image.open(tmp_path / "figures" / "g.png").convert("RGB")).astype(int); h, w = a.shape[:2]
    bar = a[:, w - int(w * 4.0 / 90):w - int(w * 2.6 / 90)]; ys = np.where((bar.max(-1) - bar.min(-1) > 60).all(1))[0]       # rows where the bar is coloured (not the black labels)
    top, bot = bar[ys[len(ys) // 20]].mean(0), bar[ys[-len(ys) // 20]].mean(0)
    assert top[0] > 200 and top[1] > 200 and top[2] < 120 and bot[2] > bot[0] and bot[1] < 60, (top, bot)   # viridis: yellow on top (High), dark purple at the bottom (Low)
    meta = _json(tmp_path / "figures" / "g.meta.json"); assert meta["cam"] == {"cmap": "viridis", "norm": "per_image_minmax"}
    assert "min–max normalised per image" in read(tmp_path / "figures" / "g.caption.md")
    j = _grid(tmp_path, "--overlay-dir", "cam", "--cmap", "jet", methods="GT,smm", samples="a", width=90, out="figures/j.png")
    assert j.fails == 1 and j.returncode != 0 and "rainbow map" in j.out and "allow_jet" in j.out, j.out
    assert _json(tmp_path / "figures" / "j.meta.json")["cam"]["cmap"] == "viridis"            # refused: drawn with viridis, the caption does not claim jet


def test_display_gamma_brightens_the_photos_only_for_display(tmp_path):
    _world(tmp_path, methods=("GT", "smm"), grey=(40, 40, 40)); write(tmp_path / "research-state.yaml", STYLE)
    r0 = _grid(tmp_path, "--row-labels", "none", methods="GT,smm", out="figures/g0.png"); r1 = _grid(tmp_path, "--row-labels", "none", "--display-gamma", "0.5", methods="GT,smm", out="figures/g1.png")
    assert r0.returncode == 0 and r1.returncode == 0, r0.out + r1.out
    def mode(n):                                                                               # the photo grey = the most frequent grey that is not the white page
        g = np.asarray(Image.open(tmp_path / "figures" / f"{n}.png").convert("L")).ravel(); c = np.bincount(g, minlength=256); c[255] = 0; return int(c.argmax())
    assert mode("g0") == 40 and abs(mode("g1") - 255 * (40 / 255) ** 0.5) <= 1                # 40 -> 101: out = 255 * (in / 255) ** gamma
    assert _json(tmp_path / "figures" / "g1.meta.json")["display_gamma"] == 0.5 and _json(tmp_path / "figures" / "g0.meta.json")["display_gamma"] is None
    assert "Display gamma 0.5" in read(tmp_path / "figures.csv")


# ------------------------------------------------------------------ cell counts
def _samples_csv(tmp_path, rows, cols):
    write(tmp_path / "samples.csv", "image,group,score," + ",".join(cols) + ",kind\n" + "\n".join(rows) + "\n")


def test_cell_counts_det_print_tp_fp_fn_under_each_cell_and_feed_the_caption(tmp_path):
    _world(tmp_path, samples=("s1", "s2")); write(tmp_path / "research-state.yaml", STYLE)
    _samples_csv(tmp_path, ["s1,day,2,1,1,1,2,0,0,win", "s2,night,1,0,0,2,1,0,1,win"], ["tp_smm", "fp_smm", "fn_smm", "tp_relroute_l", "fp_relroute_l", "fn_relroute_l"])
    sel = {"mode": "det", "rule": "ours versus the strongest baseline on that frame", "n_images": 20, "wins": 12, "losses": 3, "ties": 5, "n_counter": 3, "counter_examples": ["c1", "c2", "c3"], "iou": 0.5}
    write(tmp_path / "samples.meta.json", json.dumps(sel))
    r = _grid(tmp_path, "--cell-counts", "samples.csv", "--row-labels", "none", samples="s1,s2", width=120)
    assert r.returncode == 0, r.out
    txt = _text(tmp_path / "figures" / "g.pdf")
    assert "TP 1 · FP 1 · FN 1" in txt and "TP 2 · FP 0 · FN 0" in txt and "TP 0 · FP 0 · FN 2" in txt and "TP 1 · FP 0 · FN 1" in txt
    rows = {(x["sample"], x["method"]): x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows[("s1", "smm")]["counts"] == "TP 1 · FP 1 · FN 1" and rows[("s1", "GT")]["counts"] == ""
    meta = _json(tmp_path / "figures" / "g.meta.json"); assert meta["cell_counts"] == "det" and meta["selection"]["wins"] == 12 and meta["iou"] == 0.5
    cap = read(tmp_path / "figures" / "g.caption.md")
    assert "Under each image: TP · FP · FN counts." in cap and "Over all 20 frames our method is better than the best baseline on 12, worse on 3 and tied on 5" in cap and "3 counter-example(s)" in cap


def test_cell_counts_cam_print_the_in_box_share(tmp_path):
    _world(tmp_path); write(tmp_path / "research-state.yaml", STYLE)
    _samples_csv(tmp_path, ["s1,,0.2,0.41,0.618,win"], ["inbox_smm", "inbox_relroute_l"])
    r = _grid(tmp_path, "--cell-counts", "samples.csv", "--row-labels", "none")
    assert r.returncode == 0, r.out
    txt = _text(tmp_path / "figures" / "g.pdf"); assert "in-box 41 %" in txt and "in-box 62 %" in txt
    assert _json(tmp_path / "figures" / "g.meta.json")["cell_counts"] == "cam" and "share of the activation mass inside the ground-truth boxes" in read(tmp_path / "figures" / "g.caption.md")


def test_cell_counts_without_matching_columns_or_rows_warn(tmp_path):
    _world(tmp_path, samples=("s1", "s2")); write(tmp_path / "research-state.yaml", STYLE)
    _samples_csv(tmp_path, ["s1,,0.2,1,0,0,win"], ["tp_other", "fp_other", "fn_other"])
    r = _grid(tmp_path, "--cell-counts", "samples.csv", samples="s1,s2")
    assert r.returncode == 0 and "no tp_<method>/fp_/fn_ or inbox_<method> column" in r.out and _json(tmp_path / "figures" / "g.meta.json")["cell_counts"] is None, r.out
    _samples_csv(tmp_path, ["s1,,0.2,1,0,0,2,0,0,win"], ["tp_smm", "fp_smm", "fn_smm", "tp_relroute_l", "fp_relroute_l", "fn_relroute_l"])
    r = _grid(tmp_path, "--cell-counts", "samples.csv", samples="s1,s2", out="figures/h.png")
    assert r.returncode == 0 and "no row for sample(s) ['s2']" in r.out, r.out


def test_select_samples_output_is_the_grid_cell_counts_input(tmp_path):
    """select_samples.py det -> make_comparison.py grid --cell-counts: the numbers under the cells equal the drawn box colours (one matcher)"""
    _world(tmp_path, samples=("s1", "s2")); write(tmp_path / "research-state.yaml", STYLE); _boxes(tmp_path)
    write(tmp_path / "lab" / "GT" / "s2.txt", "0 0.50 0.50 0.40 0.40\n")
    write(tmp_path / "lab" / "smm" / "s2.txt", "0 0.50 0.50 0.40 0.40 0.9\n")
    write(tmp_path / "lab" / "relroute_l" / "s2.txt", "0 0.10 0.10 0.10 0.10 0.9\n")           # ours is WORSE here: a counter-example
    s = run("select_samples.py", "det", "--gt-dir", "lab", "--pred-dir", "lab", "--methods", "smm,relroute_l", "--ours", "relroute_l", "--k", "1", "--out", "samples.csv", cwd=tmp_path)
    assert s.returncode == 0 and not s.crashed, s.out
    sel = _json(tmp_path / "samples.meta.json"); assert sel["wins"] == 1 and sel["losses"] == 1
    r = _grid(tmp_path, "--cell-counts", "samples.csv", "--labels-dir", "lab", "--box-status", "--row-labels", "none", samples="s1")
    assert r.returncode == 0, r.out
    txt = _text(tmp_path / "figures" / "g.pdf")
    assert "TP 1 · FP 1 · FN 1" in txt and "TP 2 · FP 0 · FN 0" in txt                          # smm / relroute_l on s1
    assert "box status (IoU >= 0.5, class-aware; per method TP/FP/FN): smm 1/1/1; relroute_l 2/0/0" in r.out
    assert "worse on 1" in read(tmp_path / "figures" / "g.caption.md")                          # the counter-example count reaches the caption


def test_row_pitch_makes_room_for_the_count_line(tmp_path):
    _world(tmp_path, samples=("s1", "s2")); write(tmp_path / "research-state.yaml", STYLE)
    plain = _grid(tmp_path, "--row-labels", "none", samples="s1,s2", out="figures/p.png")
    _samples_csv(tmp_path, ["s1,,0,1,0,0,1,0,0,win", "s2,,0,1,0,0,1,0,0,win"], ["tp_smm", "fp_smm", "fn_smm", "tp_relroute_l", "fp_relroute_l", "fn_relroute_l"])
    withc = _grid(tmp_path, "--cell-counts", "samples.csv", "--row-labels", "none", samples="s1,s2", out="figures/c.png")
    assert plain.returncode == 0 and withc.returncode == 0
    h = lambda n: Image.open(tmp_path / "figures" / f"{n}.png").size[1]
    assert h("c") > h("p") + 20                                                                # a text line per row is extra height, not an overlap with the next photo
    import fitz
    pg = fitz.open(tmp_path / "figures" / "c.pdf")[0]
    ys = sorted({round(b[1]) for b in pg.get_text("words") if b[4] == "TP"})
    assert len(ys) == 2 and ys[1] - ys[0] > 15


# ------------------------------------------------------------------ G5 line of t2p.py
def _g5(p):
    r = run("t2p.py", "check", "--no-write", cwd=p)
    return next(l for l in r.out.splitlines() if "G5" in l and l.startswith("[") and "style" in l), r


def _register(p):
    s = read(p / "research-state.yaml")
    assert "\nfigures:" in s
    write(p / "research-state.yaml", s.replace("\nfigures:\n", "\nfigures:\n" + "\n".join(STYLE.splitlines()[1:]) + "\n", 1))


def test_g5_line_carries_style_and_caption_counts_and_warns_without_a_registry(research):
    r = run("t2p.py", "check", "--no-write", cwd=research)
    line = next(l for l in r.out.splitlines() if "G5" in l and "style" in l and "captions" in l)
    assert re.search(r"style 0/\d+.captions 0/0", line) and not line.startswith("[FAIL]") and "no figure style registry (figure_style.py init)" in line, line
    _register(research)
    line = next(l for l in run("t2p.py", "check", "--no-write", cwd=research).out.splitlines() if "G5" in l and "captions" in l)
    assert "no figure style registry" not in line, line


def test_g5_folds_a_code_like_label_in_a_source_csv_into_a_fail(research):
    _register(research)
    write(research / "figures" / "fig_x.source.csv", "series,x,y,label,color,line,marker\nrecv,1,2,recv,#4a4a4a,--,s\nsmm,1,3,SMM,#4a4a4a,--,s\n")
    line, r = _g5(research)
    assert line.startswith("[FAIL] G5") and re.search(r"style [1-9]\d*/", line), line


def test_g5_folds_a_caption_that_claims_an_inset_the_figure_does_not_have(research):
    _register(research)
    write(research / "figures" / "fig_main.meta.json", json.dumps({"kind": "bars", "series": ["smm"], "y_label": "AP", "inset": None}))
    edit(research / "paper" / "latex" / "main.tex", "Main comparison on both platforms (fixture).", "Main comparison on both platforms (fixture); the zoomed inset shows the tail.")
    line, r = _g5(research)
    assert line.startswith("[FAIL] G5") and re.search(r"captions [1-9]\d*/", line), line
