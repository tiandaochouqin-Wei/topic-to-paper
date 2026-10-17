# -*- coding: utf-8 -*-
"""make_motivation.py: motivation figures in the form the evidence takes (condition curve, paired change, trade-off,
schematic, dataset strip, radar), one PDF per panel, registered in figures.csv; latex_check.py figure takes one width per panel."""
import csv
import io
import shutil

import numpy as np

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
    r = run("make_motivation.py", "radar", "--csv", "results/bench.csv", "--ours", "ours", "--groups", "RGB-only (avg. 2)=rgb_a+rgb_b", "--out", out, cwd=research)
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
    r = run("make_motivation.py", "radar", "--csv", "results/bench.csv", "--ours", "ours", "--out", "figures/fig_r.png", cwd=research)
    assert r.returncode == 0 and "best on 5/6 axes" in r.out and "must not call it an envelope" in r.out, r.out


def test_radar_needs_three_axes(research):
    r = run("make_motivation.py", "radar", "--out", "figures/fig_r.png", cwd=research)        # fixture main table has two metrics
    assert r.returncode == 1 and not r.crashed and "至少要 3 根轴" in r.out, r.out


def test_radar_unknown_group_member_fails_cleanly(research):
    _bench(research)
    r = run("make_motivation.py", "radar", "--csv", "results/bench.csv", "--groups", "X=nope+rgb_a", "--out", "figures/fig_r.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "nope" in r.out, r.out


# ------------------------------------------------------------------ schematic
def test_schematic_template_renders(research):
    _images(research)
    shutil.copy(SKILL / "templates" / "motivation_scheme.yaml", research / "figures" / "motivation_scheme.yaml")
    out = "figures/fig_teaser_scheme.png"
    r = run("make_motivation.py", "schematic", "--spec", "figures/motivation_scheme.yaml", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "[WARN] schematic" not in r.out and "layout audit clean" in r.out, r.out     # the shipped template has no overlaps
    _outputs_exist(research, out)
    assert "illustrations, not measured feature maps" in read(research / "figures.csv")  # tiles flagged for the caption
    _register_pdf(research, out, 100)
    g = run("gate_check.py", "dpi", cwd=research)
    assert not [l for l in g.out.splitlines() if l.startswith("[FAIL]") and "fig_teaser_scheme.pdf" in l], g.out


def test_schematic_bad_edge_and_missing_image_fail_cleanly(research):
    _images(research)
    spec = read(SKILL / "templates" / "motivation_scheme.yaml")
    write(research / "figures" / "s1.yaml", spec.replace("{from: cat, to: bb}", "{from: cat, to: nowhere}"))
    r = run("make_motivation.py", "schematic", "--spec", "figures/s1.yaml", "--out", "figures/s1.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "nowhere" in r.out, r.out
    write(research / "figures" / "s2.yaml", spec.replace("figures/src/det_ours.png", "figures/src/missing.png"))
    r = run("make_motivation.py", "schematic", "--spec", "figures/s2.yaml", "--out", "figures/s2.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "missing.png" in r.out, r.out


def test_schematic_overlap_warns(research):
    _images(research)
    spec = read(SKILL / "templates" / "motivation_scheme.yaml").replace("xy: [43, 51], wh: [14, 11]", "xy: [31, 51], wh: [14, 11]")
    write(research / "figures" / "s3.yaml", spec)
    r = run("make_motivation.py", "schematic", "--spec", "figures/s3.yaml", "--out", "figures/s3.png", cwd=research)
    assert r.returncode == 0 and "[WARN] schematic: 节点 cat 与 bb 重叠" in r.out, r.out


# ------------------------------------------------------------------ strip
def test_strip(research):
    _images(research)
    out = "figures/fig_teaser_data.png"
    r = run("make_motivation.py", "strip", "--item", "M3FD RGB/IR|figures/src/rgb.png|figures/src/x.png",
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


# ------------------------------------------------------------------ condition
def _pilot(project, gap_rgb_ir=12.0, noise=0.5, seeds=3):
    """RGB rises with brightness, IR is flat: the leader changes from IR to RGB near the middle"""
    rng = np.random.default_rng(0); rows = [["method", "scale", "seed", "AP"]]
    for sd in range(seeds):
        for x in (0.1, 0.25, 0.5, 0.75, 1.0):
            rows += [["rgb", x, sd, 30 + 2 * gap_rgb_ir * (x - 0.55) + rng.normal(0, noise)], ["ir", x, sd, 30 + rng.normal(0, noise)],
                     ["ours", x, sd, 40 + 5 * x + rng.normal(0, noise)]]
    with io.open(project / "results" / "pilot.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_condition_marks_a_resolved_leader_change_and_gap(research):
    _pilot(research)
    out = "figures/fig_mot_cond.png"
    r = run("make_motivation.py", "condition", "--csv", "results/pilot.csv", "--x", "scale", "--y", "AP", "--series", "method",
            "--ours", "ours", "--gap", "ours,ir@0.1", "--regions", "dark:0:0.3", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "leader change: ir -> rgb" in r.out and "(outside seed noise)" in r.out, r.out      # ours is excluded from the lead by default
    assert "gap: ours − ir = +10" in r.out, r.out
    _outputs_exist(research, out)
    _register_pdf(research, out, 88)
    g = run("gate_check.py", "dpi", cwd=research)
    assert not [l for l in g.out.splitlines() if l.startswith("[FAIL]") and "fig_mot_cond.pdf" in l], g.out


def test_condition_leader_change_inside_noise_is_flagged_not_drawn(research):
    _pilot(research, gap_rgb_ir=0.4, noise=2.0)
    r = run("make_motivation.py", "condition", "--csv", "results/pilot.csv", "--x", "scale", "--y", "AP", "--series", "method",
            "--ours", "ours", "--out", "figures/fig_c.png", cwd=research)
    assert r.returncode == 0 and "[WARN] condition:" in r.out and "inside seed noise (not drawn)" in r.out, r.out


def test_condition_single_run_is_unverified(research):
    _pilot(research, seeds=1)
    r = run("make_motivation.py", "condition", "--csv", "results/pilot.csv", "--x", "scale", "--y", "AP", "--series", "method",
            "--ours", "ours", "--out", "figures/fig_c.png", cwd=research)
    assert r.returncode == 0 and "single run, unverified" in r.out, r.out


# ------------------------------------------------------------------ paired
def _table1(project, n_det=7):
    rows = [["detector", "dataset", "RGB", "IR", "Naive"]]
    for i in range(n_det):
        for j, d in enumerate(["M3FD", "LLVIP", "Drone"]):
            rgb, ir = 40 + i + j, 35 + i
            rows.append([f"det{i}", d, rgb, ir, rgb - 5 - j if (i + j) % 4 else rgb + 2])      # most cells fall below the better single
    with io.open(project / "results" / "table1.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return rows[1:]


def test_paired_counts_items_that_get_worse(research):
    rows = _table1(research)
    worse = sum(1 for r in rows if r[4] < max(r[2], r[3]))
    out = "figures/fig_mot_paired.png"
    r = run("make_motivation.py", "paired", "--csv", "results/table1.csv", "--item", "detector,dataset", "--from", "RGB,IR", "--to", "Naive",
            "--from-label", "better single", "--to-label", "naive", "--value", "AP", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    assert f"{worse}/{len(rows)} worse" in r.out, r.out                    # 21 items -> sorted Δ bars
    assert "(sorted Δ)" in read(research / "figures.csv")
    _outputs_exist(research, out)


def test_paired_slope_averages_rows_per_item(research):
    _table1(research)
    r = run("make_motivation.py", "paired", "--csv", "results/table1.csv", "--item", "dataset", "--from", "RGB,IR", "--to", "Naive",
            "--out", "figures/fig_p.png", cwd=research)
    assert r.returncode == 0 and "/3 worse" in r.out, r.out                # 3 datasets, 7 detectors averaged into each
    assert "(slope chart)" in read(research / "figures.csv")


def test_paired_missing_column_fails_cleanly(research):
    _table1(research)
    r = run("make_motivation.py", "paired", "--csv", "results/table1.csv", "--item", "detector", "--from", "Depth", "--to", "Naive", "--out", "figures/fig_p.png", cwd=research)
    assert r.returncode == 1 and not r.crashed and "Depth" in r.out, r.out


# ------------------------------------------------------------------ tradeoff
def _eff(project, ours_ap):
    rows = [["method", "params", "AP"], ["tiny", 2.6, 30.0], ["small", 9.4, 33.0], ["big", 120, 36.0], ["mid", 45, 35.2], ["ours", 6.2, ours_ap]]
    with io.open(project / "results" / "eff.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_tradeoff_ours_on_front(research):
    _eff(research, 35.6)
    out = "figures/fig_mot_tradeoff.png"
    r = run("make_motivation.py", "tradeoff", "--csv", "results/eff.csv", "--x", "params", "--y", "AP", "--ours", "ours", "--logx", "--out", out, cwd=research)
    assert r.returncode == 0 and not r.crashed and "ours (ours) is on the Pareto front" in r.out, r.out
    _outputs_exist(research, out)


def test_tradeoff_dominated_ours_warns(research):
    _eff(research, 29.0)                                                    # tiny (2.6 M, 30.0) dominates ours (6.2 M, 29.0)
    r = run("make_motivation.py", "tradeoff", "--csv", "results/eff.csv", "--x", "params", "--y", "AP", "--ours", "ours", "--out", "figures/fig_t.png", cwd=research)
    assert "[WARN] tradeoff:" in r.out and "tiny" in r.out, r.out


def test_out_must_be_png(research):
    _eff(research, 35.6)
    r = run("make_motivation.py", "tradeoff", "--csv", "results/eff.csv", "--x", "params", "--y", "AP", "--out", "figures/fig_t.pdf", cwd=research)
    assert r.returncode == 1 and not r.crashed and ".png" in r.out, r.out
