# -*- coding: utf-8 -*-
"""make_comparison.py grid: boxes (yolo / xyxy / coco / voc), GT green vs accent, CAM overlay + shared colorbar, class masks + palette,
highlight frame, marks, label position, print-width / dpi audit. Synthetic 64x64 images; the photos are one raster inside the PDF, so
the PDF check is "one image of the expected pixel size + a text layer", not "no /Image"."""
import csv
import io
import json
import os
import sys

import numpy as np
from PIL import Image

from conftest import SCRIPTS, run, write

GT_GREEN = np.array([0x2c, 0xa2, 0x5f]); ACCENT_RED = np.array([0xd1, 0x49, 0x5b])
sys.path.insert(0, str(SCRIPTS))


def _scene(tmp_path, methods=("GT", "M1"), samples=("a", "b"), grey=128):
    for m in methods:
        for s in samples:
            p = tmp_path / "img" / m / f"{s}.png"; p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 64), (grey, grey, grey)).save(p)


def _grid(tmp_path, *extra, methods="GT,M1", samples="a,b", out="figures/g.png", width=90):
    return run("make_comparison.py", "grid", "--root", tmp_path / "img", "--methods", methods, "--samples", samples, "--out", out,
               "--project", tmp_path, "--width-mm", width, *extra, cwd=tmp_path)


def _rows(path): return list(csv.DictReader(io.open(path, encoding="utf-8")))


def _near(png, rgb, tol=28):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    return (np.abs(a - rgb).sum(-1) <= tol)


def _pdf_text(pdf):
    import fitz
    return "".join(pg.get_text() for pg in fitz.open(pdf))


def _pdf_images(pdf):
    from pypdf import PdfReader
    pg = PdfReader(pdf).pages[0]
    return [im.image.size for im in pg.images], float(pg.mediabox.width) / 72 * 25.4


def test_plain_grid_files_audit_and_pdf(tmp_path):
    _scene(tmp_path)
    r = _grid(tmp_path)
    assert r.returncode == 0, r.out
    for ext in (".png", ".pdf", ".source.csv", "_gray.png"): assert (tmp_path / "figures" / f"g{ext}").exists(), ext
    rows = _rows(tmp_path / "figures" / "g.source.csv")
    assert len(rows) == 4 and {(x["sample"], x["method"]) for x in rows} == {(s, m) for s in "ab" for m in ("GT", "M1")}
    assert all(x["n_boxes"] == "0" and x["highlight"] == "no" and x["image"] for x in rows)
    fig = _rows(tmp_path / "figures.csv"); row = next(x for x in fig if x["file"] == "figures/g.png")
    assert float(row["print_width_mm"]) == 90 and row["source_data"] == "figures/g.source.csv"
    w = Image.open(tmp_path / "figures" / "g.png").size[0]
    assert abs(w / (90 / 25.4) - 400) < 2, w                       # page = --width-mm exactly (no tight-bbox padding), 400 dpi
    imgs, page_mm = _pdf_images(tmp_path / "figures" / "g.pdf")
    assert len(imgs) == 1 and abs(page_mm - 90) < 0.5               # one embedded raster over the printed width
    assert imgs[0][0] / (page_mm / 25.4) >= 395, (imgs, page_mm)    # embedded raster dpi at print size >= 395
    txt = _pdf_text(tmp_path / "figures" / "g.pdf"); assert "GT" in txt and "M1" in txt and "a" in txt   # col + row labels are text, not pixels
    assert "400 dpi" in r.out


def test_boxes_in_four_formats_and_source_counts(tmp_path):
    _scene(tmp_path, methods=("GT", "Y", "X", "C", "V"), samples=("s",))
    lab = tmp_path / "lab"
    write(lab / "Y" / "s.txt", "0 0.5 0.5 0.4 0.4\n1 0.2 0.2 0.1 0.1\n")
    write(lab / "X" / "s.txt", "0 6.4 6.4 32 32 0.9\n")                                       # pixels, score ignored
    write(lab / "C" / "s.json", json.dumps([{"bbox": [6.4, 6.4, 25.6, 25.6], "category_id": 1, "score": 0.8}]))
    write(lab / "V" / "s.xml", "<annotation><object><name>car</name><bndbox><xmin>10</xmin><ymin>10</ymin><xmax>40</xmax><ymax>40</ymax></bndbox></object>"
                               "<object><name>car</name><bndbox><xmin>1</xmin><ymin>1</ymin><xmax>5</xmax><ymax>5</ymax></bndbox></object></annotation>")
    for fmt, mth, n in (("yolo", "Y", 2), ("xyxy", "X", 1), ("coco", "C", 1), ("voc", "V", 2)):
        only = tmp_path / f"lab_{fmt}"; (only / mth).mkdir(parents=True)
        for f in (lab / mth).iterdir(): (only / mth / f.name).write_bytes(f.read_bytes())            # a label dir holds one format
        r = _grid(tmp_path, "--labels-dir", only, "--label-fmt", fmt, "--gt-col", "GT", "--class-names", "car,person", methods="GT,Y,X,C,V", samples="s", out=f"figures/b_{fmt}.png")
        assert r.returncode == 0, r.out
        rows = {x["method"]: x for x in _rows(tmp_path / "figures" / f"b_{fmt}.source.csv")}
        assert rows[mth]["n_boxes"] == str(n), (fmt, rows)
        assert all(rows[m]["n_boxes"] == "0" for m in rows if m != mth)


def test_read_boxes_normalises_every_format(tmp_path):
    import make_comparison as mc
    write(tmp_path / "y.txt", "3 0.5 0.5 0.2 0.4\n")
    assert np.allclose(mc.read_boxes(str(tmp_path / "y.txt"), "yolo", 64, 64)[0][1:], (0.4, 0.3, 0.6, 0.7))
    write(tmp_path / "x.txt", "0 16 8 48 40\n")
    assert np.allclose(mc.read_boxes(str(tmp_path / "x.txt"), "xyxy", 64, 32)[0][1:], (0.25, 0.25, 0.75, 1.0))      # pixels / image size, clipped to 1
    write(tmp_path / "n.txt", "0 0.1 0.2 0.3 0.4\n")
    assert np.allclose(mc.read_boxes(str(tmp_path / "n.txt"), "xyxy", 64, 64)[0][1:], (0.1, 0.2, 0.3, 0.4))        # already normalised
    write(tmp_path / "c.json", json.dumps({"annotations": [{"bbox": [16, 16, 32, 16], "category_id": 2}]}))
    assert np.allclose(mc.read_boxes(str(tmp_path / "c.json"), "coco", 64, 64)[0][1:], (0.25, 0.25, 0.75, 0.5))


def test_gt_boxes_green_others_accent_pixel_probe(tmp_path):
    _scene(tmp_path, samples=("s",))
    write(tmp_path / "lab" / "GT" / "s.txt", "0 0.5 0.5 0.5 0.5\n"); write(tmp_path / "lab" / "M1" / "s.txt", "0 0.5 0.5 0.5 0.5\n")
    r = _grid(tmp_path, "--labels-dir", tmp_path / "lab", "--row-labels", "none", samples="s")
    assert r.returncode == 0, r.out
    rows = {x["method"]: x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows["GT"]["box_color"].lower() == "#2ca25f" and rows["M1"]["box_color"].lower() == "#d1495b"
    png = tmp_path / "figures" / "g.png"; w = Image.open(png).size[0]
    green, red = _near(png, GT_GREEN), _near(png, ACCENT_RED)
    assert green[:, :w // 2].sum() > 200 and green[:, w // 2:].sum() == 0        # GT column (left) only green
    assert red[:, w // 2:].sum() > 200 and red[:, :w // 2].sum() == 0            # method column (right) only accent


def test_box_line_width_has_a_printed_floor_and_scales_with_the_cell(tmp_path):
    _scene(tmp_path, methods=("GT", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "M11"), samples=("s",))
    r = _grid(tmp_path, "--box-lw", "0.1", methods="GT,M1,M2,M3,M4,M5,M6,M7,M8,M9,M10,M11", samples="s", out="figures/narrow.png", width=60)
    assert "box line 0.40 pt" in r.out and "0.4 pt printed floor" in r.out, r.out
    r2 = _grid(tmp_path, samples="s", width=180, out="figures/wide.png")
    assert "box line 1.00 pt" in r2.out, r2.out                                  # big cells cap at 1 pt


def test_overlay_colorbar_and_gt_column_as_base(tmp_path):
    _scene(tmp_path, methods=("GT",), samples=("a", "b"))                        # M1 has no photo of its own: its CAM sits on the GT image
    for s in "ab":
        m = np.zeros((16, 16), np.float32); m[4:8, 4:8] = 3.0; m[0, 0] = 5.0         # not 0-1: must be min-max normalised
        (tmp_path / "cam" / "M1").mkdir(parents=True, exist_ok=True); np.save(tmp_path / "cam" / "M1" / f"{s}.npy", m)
    r = _grid(tmp_path, "--overlay-dir", tmp_path / "cam", "--cmap", "jet", "--colorbar", "Low,High", "--overlay-alpha", "0.55")
    assert r.returncode == 0, r.out
    rows = {(x["sample"], x["method"]): x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows[("a", "M1")]["overlay"].endswith("a.npy") and rows[("a", "GT")]["overlay"] == ""
    assert rows[("a", "M1")]["image"].replace("\\", "/").endswith("img/GT/a.png")  # fell back to the GT image
    txt = _pdf_text(tmp_path / "figures" / "g.pdf"); assert "High" in txt and "Low" in txt
    a = np.asarray(Image.open(tmp_path / "figures" / "g.png").convert("RGB")).astype(int); h, w = a.shape[:2]
    bar = a[:, w - int(w * 0.035):w - int(w * 0.012)]                              # the shared bar at the right edge
    ys = np.where((np.abs(bar - 255).sum(-1) > 60).any(1))[0]; assert len(ys) > h * 0.5
    top, bot = bar[ys[len(ys) // 20]].mean(0), bar[ys[-len(ys) // 20]].mean(0)
    assert top[0] > top[2] + 60 and bot[2] > bot[0] + 60, (top, bot)               # jet: dark red on top (High), dark blue at the bottom (Low)
    r2 = _grid(tmp_path, "--overlay-dir", tmp_path / "cam", "--colorbar", "none", out="figures/nobar.png")
    assert "High" not in _pdf_text(tmp_path / "figures" / "nobar.pdf")


def test_overlay_png_used_as_is_and_missing_cells_are_listed(tmp_path):
    _scene(tmp_path, samples=("a", "b"))
    os.remove(tmp_path / "img" / "M1" / "b.png")
    (tmp_path / "ov" / "GT").mkdir(parents=True); Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "ov" / "GT" / "a.png")
    r = _grid(tmp_path, "--overlay-dir", tmp_path / "ov", "--overlay-alpha", "1.0")
    assert r.returncode == 0 and "MISSING 1: ['M1/b']" in r.out, r.out
    rows = {(x["sample"], x["method"]): x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert len(rows) == 4 and rows[("b", "M1")]["image"] == ""                      # one row per cell, even the empty one
    assert _near(tmp_path / "figures" / "g.png", np.array([255, 0, 0]), 6).sum() > 1000    # the png overlay went in unchanged (alpha 1)


def test_highlight_frame_and_label_position(tmp_path):
    import fitz
    _scene(tmp_path, methods=("GT", "Ours"), samples=("s",))
    r = _grid(tmp_path, "--highlight", "Ours", "--label-pos", "top", "--row-labels", "none", methods="GT,Ours", samples="s", out="figures/top.png")
    assert r.returncode == 0, r.out
    rows = {x["method"]: x for x in _rows(tmp_path / "figures" / "top.source.csv")}
    assert rows["Ours"]["highlight"] == "yes" and rows["GT"]["highlight"] == "no"
    png = tmp_path / "figures" / "top.png"; w = Image.open(png).size[0]; red = _near(png, ACCENT_RED)
    assert red[:, w // 2:].sum() > 500 and red[:, :w // 2 - 20].sum() == 0          # frame (and its label) only round the highlighted column
    def ylab(pdf, word):
        pg = fitz.open(pdf)[0]; return next(b[1] for b in pg.get_text("words") if b[4] == word) / pg.rect.height
    assert ylab(tmp_path / "figures" / "top.pdf", "GT") < 0.2                        # label above the photos
    _grid(tmp_path, "--row-labels", "none", methods="GT,Ours", samples="s", out="figures/bot.png")
    assert ylab(tmp_path / "figures" / "bot.pdf", "GT") > 0.8                        # default: under the row group


def test_custom_row_and_col_labels_and_length_check(tmp_path):
    _scene(tmp_path)
    r = _grid(tmp_path, "--row-labels", "Row One,Row Two", "--col-labels", "Ground truth,Method 1")
    assert r.returncode == 0, r.out
    txt = _pdf_text(tmp_path / "figures" / "g.pdf"); assert "Ground truth" in txt and "Row Two" in txt
    r = _grid(tmp_path, "--col-labels", "only one", out="figures/bad.png")
    assert r.returncode != 0 and "--col-labels needs 2" in r.out


def test_marks_draw_accent_ellipses_and_count_in_csv(tmp_path):
    _scene(tmp_path, samples=("s",))
    write(tmp_path / "marks.csv", "sample,method,cx,cy,w,h\ns,M1,0.5,0.5,0.6,0.4\ns,M1,0.2,0.2,0.2,0.2\n")
    r = _grid(tmp_path, "--marks", tmp_path / "marks.csv", "--row-labels", "none", samples="s")
    assert r.returncode == 0, r.out
    rows = {x["method"]: x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows["M1"]["n_marks"] == "2" and rows["GT"]["n_marks"] == "0"
    png = tmp_path / "figures" / "g.png"; w = Image.open(png).size[0]; red = _near(png, ACCENT_RED)
    assert red[:, w // 2:].sum() > 200 and red[:, :w // 2].sum() == 0


def test_masks_use_a_fixed_palette_with_alpha_blend(tmp_path):
    import make_comparison as mc
    _scene(tmp_path, methods=("GT", "M1"), samples=("s",), grey=128)
    ids = np.zeros((64, 64), np.uint8); ids[:, :32] = 1; ids[:, 32:] = 2
    for m in ("GT", "M1"):
        (tmp_path / "mask" / m).mkdir(parents=True, exist_ok=True); Image.fromarray(ids).save(tmp_path / "mask" / m / "s.png")
    r = _grid(tmp_path, "--mask-dir", tmp_path / "mask", "--palette", "3", "--mask-alpha", "0.5", "--row-labels", "none", samples="s")
    assert r.returncode == 0, r.out
    rows = {x["method"]: x for x in _rows(tmp_path / "figures" / "g.source.csv")}
    assert rows["GT"]["mask"].endswith("s.png") and rows["M1"]["mask"].endswith("s.png")
    hexa = lambda h: np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)])
    for cls in (1, 2):
        exp = 0.5 * 128 + 0.5 * hexa(mc.CLASS_COLORS[cls - 1])                       # class k -> palette[k-1], blended over the grey photo
        assert _near(tmp_path / "figures" / "g.png", exp, 6).sum() > 1000, cls


def test_legacy_cli_still_works_with_inset_cols_and_multirow_groups(tmp_path):
    _scene(tmp_path, methods=("Origin", "A", "B", "C"), samples=("s1", "s2"))
    r = run("make_comparison.py", "grid", "--root", tmp_path / "img", "--methods", "Origin,A,B,C", "--samples", "s1,s2", "--out", "figdet/g.png",
            "--inset", "0.1,0.1,0.3,0.3", "--cols", "2", "--width-mm", "88", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert (tmp_path / "figdet" / "g.png").exists() and (tmp_path / "figdet" / "g.pdf").exists()
    assert len(_rows(tmp_path / "figdet" / "g.source.csv")) == 8
    txt = _pdf_text(tmp_path / "figdet" / "g.pdf"); assert "Origin" in txt and "C" in txt


def test_upsampled_source_images_are_reported(tmp_path):
    _scene(tmp_path, methods=tuple(f"M{i}" for i in range(12)), samples=("s",))     # 64 px across a ~14 mm cell = ~115 dpi
    r = _grid(tmp_path, methods=",".join(f"M{i}" for i in range(12)), samples="s", width=183)
    assert r.returncode == 0 and "source images give only" in r.out and "upsampled" in r.out, r.out
