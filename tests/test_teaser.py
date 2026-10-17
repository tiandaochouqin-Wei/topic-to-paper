# -*- coding: utf-8 -*-
"""make_teaser.py: the parts of a Fig.-1 motivation figure (radar over benchmarks, dataset strip, naive-vs-ours schematic),
one PDF per panel, registered in figures.csv; latex_check.py figure takes one width share per panel."""
import csv
import io
import shutil

from conftest import SKILL, read, run, write


def _images(project):
    from PIL import Image
    src = project / "figures" / "src"; src.mkdir(parents=True, exist_ok=True)
    for name, colour in (("rgb.png", (90, 110, 80)), ("x.png", (30, 30, 30)), ("det_naive.png", (120, 120, 120)), ("det_ours.png", (40, 40, 40))):
        Image.new("RGB", (160, 120), colour).save(src / name)


def _bench(project, ours_best=True):
    rows = [["dataset", "method", "AP"]]
    for i, d in enumerate(["M3FD", "LLVIP", "DroneVehicle", "SUN", "NYU", "UODAC"]):
        rows += [[d, "ours", 60 + i], [d, "rgb_a", 50 + i], [d, "rgb_b", 48 + i], [d, "cat_a", 30 + i], [d, "fusion", 55 + i + (0 if ours_best or i else 9)]]
    with io.open(project / "results" / "bench.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def _register_pdf(project, png, width):
    rows = list(csv.DictReader(io.open(project / "figures.csv", encoding="utf-8-sig")))
    rows.append({"file": png.replace(".png", ".pdf"), "print_width_mm": str(width), "source_data": "x", "inspected": "yes", "issues": ""})
    with io.open(project / "figures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "print_width_mm", "source_data", "inspected", "issues"]); w.writeheader(); w.writerows(rows)


def _outputs_exist(project, out):
    stem = out[:-4]
    for suffix in (".png", ".pdf", "_gray.png", ".source.csv"):
        assert (project / (stem + suffix)).exists(), stem + suffix
    assert out in read(project / "figures.csv")


# ------------------------------------------------------------------ radar
def test_radar_from_long_csv_with_groups(research):
    _bench(research)
    out = "figures/fig_teaser_radar.png"
    r = run("make_teaser.py", "radar", "--csv", "results/bench.csv", "--ours", "ours", "--groups", "RGB-only (avg. 2)=rgb_a+rgb_b", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "best on 6/6 axes" in r.out and "layout audit clean" in r.out, r.out
    _outputs_exist(research, out)
    src = read(research / "figures" / "fig_teaser_radar.source.csv")
    assert "RGB-only (avg. 2)" in src and "rgb_a" not in src            # grouped series replace their members
    _register_pdf(research, out, 62)
    g = run("gate_check.py", "dpi", cwd=research)
    assert not [l for l in g.out.splitlines() if l.startswith("[FAIL]") and "fig_teaser_radar.pdf" in l], g.out   # every label >= 5 pt at the drawn width


def test_radar_says_when_ours_is_not_the_envelope(research):
    _bench(research, ours_best=False)
    r = run("make_teaser.py", "radar", "--csv", "results/bench.csv", "--ours", "ours", "--out", "figures/fig_r.png", cwd=research)
    assert r.returncode == 0 and "best on 5/6 axes" in r.out and "must not call it an envelope" in r.out, r.out


def test_radar_needs_three_axes(research):
    r = run("make_teaser.py", "radar", "--out", "figures/fig_r.png", cwd=research)        # fixture main table has two metrics
    assert r.returncode == 1 and not r.crashed and "至少要 3 根轴" in r.out, r.out


def test_radar_unknown_group_member_fails_cleanly(research):
    _bench(research)
    r = run("make_teaser.py", "radar", "--csv", "results/bench.csv", "--groups", "X=nope+rgb_a", "--out", "figures/fig_r.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "nope" in r.out, r.out


# ------------------------------------------------------------------ schematic
def test_schematic_template_renders(research):
    _images(research)
    shutil.copy(SKILL / "templates" / "teaser_scheme.yaml", research / "figures" / "teaser_scheme.yaml")
    out = "figures/fig_teaser_scheme.png"
    r = run("make_teaser.py", "schematic", "--spec", "figures/teaser_scheme.yaml", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "[WARN] schematic" not in r.out and "layout audit clean" in r.out, r.out     # the shipped template has no overlaps
    _outputs_exist(research, out)
    assert "illustrations, not measured feature maps" in read(research / "figures.csv")  # tiles flagged for the caption
    _register_pdf(research, out, 100)
    g = run("gate_check.py", "dpi", cwd=research)
    assert not [l for l in g.out.splitlines() if l.startswith("[FAIL]") and "fig_teaser_scheme.pdf" in l], g.out


def test_schematic_bad_edge_and_missing_image_fail_cleanly(research):
    _images(research)
    spec = read(SKILL / "templates" / "teaser_scheme.yaml")
    write(research / "figures" / "s1.yaml", spec.replace("{from: cat, to: bb}", "{from: cat, to: nowhere}"))
    r = run("make_teaser.py", "schematic", "--spec", "figures/s1.yaml", "--out", "figures/s1.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "nowhere" in r.out, r.out
    write(research / "figures" / "s2.yaml", spec.replace("figures/src/det_ours.png", "figures/src/missing.png"))
    r = run("make_teaser.py", "schematic", "--spec", "figures/s2.yaml", "--out", "figures/s2.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "missing.png" in r.out, r.out


def test_schematic_overlap_warns(research):
    _images(research)
    spec = read(SKILL / "templates" / "teaser_scheme.yaml").replace("xy: [43, 51], wh: [14, 11]", "xy: [31, 51], wh: [14, 11]")
    write(research / "figures" / "s3.yaml", spec)
    r = run("make_teaser.py", "schematic", "--spec", "figures/s3.yaml", "--out", "figures/s3.png", cwd=research)
    assert r.returncode == 0 and "[WARN] schematic: 节点 cat 与 bb 重叠" in r.out, r.out


# ------------------------------------------------------------------ strip
def test_strip(research):
    _images(research)
    out = "figures/fig_teaser_data.png"
    r = run("make_teaser.py", "strip", "--item", "M3FD RGB/IR|figures/src/rgb.png|figures/src/x.png",
            "--item", "LLVIP RGB/IR|figures/src/rgb.png|figures/src/x.png", "--title", "Datasets", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed and "layout audit clean" in r.out, r.out
    _outputs_exist(research, out)


# ------------------------------------------------------------------ composing the teaser in LaTeX
def test_latex_figure_takes_one_width_per_panel(research):
    r = run("latex_check.py", "figure", "--panels", "figures/fig_abl_a.pdf,figures/fig_abl_b.pdf,figures/fig_main.pdf",
            "--labels", "a,b,c", "--width", "0.15,0.33,0.50", "--env", "figure*", "--label", "fig:teaser", cwd=research)
    assert r.returncode == 0, r.out
    assert "0.15" in r.out and "0.33" in r.out and "0.50" in r.out, r.out
    r = run("latex_check.py", "figure", "--panels", "figures/fig_abl_a.pdf,figures/fig_abl_b.pdf",
            "--labels", "a,b", "--width", "0.15,0.33,0.50", cwd=research)
    assert r.returncode == 1 and "份额" in r.out, r.out
