# -*- coding: utf-8 -*-
"""Regressions from bmemat_motion P6 (2026-10-31).

1. draft_plan plan: every baseline had worst_coverage 0.0 (higher is better), so `(rv - best) / best` raised ZeroDivisionError.
   The plan now asks for the absolute difference when the strongest baseline is 0, and a tie among baselines is broken by
   results.strongest_baseline, then by the other main.csv columns, then by name -- never by the row order of main.csv.
2. draft_plan check: `regex` items were searched without re.M; a section body starts with "\\n", so the Nature RES probe
   `^###\\s+…` (Results subheadings are claim sentences) and the CS ablation probe `^#{2,4}…ablation` never matched a heading.
3. ms_section: the alias "Experiments" matched anywhere in a heading, so `### Passive particles … of experiments` was taken as
   the whole Results section. An alias now has to start the heading text, and the section level (## under a # title) wins."""
import json, sys

import pytest

from conftest import SCRIPTS, read, run, write

sys.path.insert(0, str(SCRIPTS))
import draft_plan as dp

# bmemat_motion results/main.csv: the reference has 3 seeds, the baselines one; every baseline is 0.0 on the primary metric.
# B1 comes first on purpose: row order used to decide the "strongest" baseline.
MAIN = ("run_id,method,seed,worst_coverage,mean_coverage,coverage_nid,coverage_id,max_fpr\n"
        "b1,B1_pathlength,20261028,0.0,0.0075,0.0,0.0126,1.0\n"
        "b2,B2_quadmsd,20261028,0.0,0.2111,0.1987,0.2193,0.427\n"
        "b3,B3_bailey,20261028,0.0,0.7171,0.7897,0.6688,0.043\n"
        "g0,gated,20261028,0.912,0.9556,0.9817,0.9382,0.062\n"
        "g1,gated,21261031,0.908,0.955,0.9812,0.9375,0.053\n"
        "g2,gated,22261034,0.912,0.9561,0.9808,0.9396,0.054\n")
STATE = ("target:\n  venue: BMEMat\n  family: nature\n"
         "results:\n  main_table: results/main.csv\n  primary_metric: worst_coverage\n  primary_direction: higher\n"
         "  metric_direction:\n    max_fpr: lower\n  group_key: method\n  reference_method: gated\n")


def _plan(tmp_path, main=MAIN, state=STATE):
    write(tmp_path / "results" / "main.csv", main)
    write(tmp_path / "research-state.yaml", state)
    r = run("draft_plan.py", "plan", "--project", ".", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    return json.loads(read(tmp_path / "paper" / "draft_plan.json"))


def _main_items(items):
    return [i for i in items if i["source"] == "main.csv 主指标"]


# ---------------------------------------------------------------- 1. zero baseline + tie-break
def test_zero_baseline_asks_for_absolute_difference(tmp_path):
    items = _main_items(_plan(tmp_path))
    assert [i["kind"] for i in items] == ["number_abs", "name"], items
    assert items[0]["probe"] == "0.91", items[0]          # shared seed 20261028: gated 0.912 - 0
    assert "相对变化无定义" in items[0]["must"]


def test_tie_broken_by_other_metric_not_row_order(tmp_path):
    """all three baselines tie at 0.0; mean_coverage (first other column, direction of the primary) picks B3_bailey"""
    items = _main_items(_plan(tmp_path))
    assert items[1]["probe"] == "B3_bailey", items
    assert "mean_coverage" in items[0]["must"], items[0]["must"]
    rows = MAIN.splitlines(); shuffled = "\n".join([rows[0]] + rows[1:][::-1]) + "\n"
    assert _main_items(_plan(tmp_path, shuffled))[1]["probe"] == "B3_bailey"


def test_tie_broken_by_state_strongest_baseline(tmp_path):
    items = _main_items(_plan(tmp_path, state=STATE + "  strongest_baseline: B2_quadmsd\n"))
    assert items[1]["probe"] == "B2_quadmsd" and "strongest_baseline" in items[0]["must"], items


def test_full_tie_falls_back_to_name(tmp_path):
    main = "run_id,method,seed,acc\no,ours,0,0.5\nz,zeta,0,0.0\na,alpha,0,0.0\n"
    st = "results:\n  main_table: results/main.csv\n  primary_metric: acc\n  group_key: method\n  reference_method: ours\n"
    assert _main_items(_plan(tmp_path, main, st))[1]["probe"] == "alpha"


def test_lower_is_better_all_zero_baselines_do_not_crash(tmp_path):
    main = "run_id,method,seed,rmse\no,ours,0,0.02\na,a,0,0.0\nb,b,0,0.0\n"
    st = "results:\n  main_table: results/main.csv\n  primary_metric: rmse\n  primary_direction: lower\n  group_key: method\n  reference_method: ours\n"
    it = _main_items(_plan(tmp_path, main, st))[0]
    assert it["kind"] == "number_abs" and it["probe"] == "0.020", it


def test_nonzero_ties_keep_the_relative_change(tmp_path):
    """zeta comes first in main.csv; alpha has the higher f1 and is the strongest"""
    main = "run_id,method,seed,acc,f1\no,ours,0,0.55,0.5\nz,zeta,0,0.50,0.2\na,alpha,0,0.50,0.3\n"
    st = "results:\n  main_table: results/main.csv\n  primary_metric: acc\n  group_key: method\n  reference_method: ours\n"
    items = _main_items(_plan(tmp_path, main, st))
    assert items[0]["kind"] == "number_pm1" and items[0]["probe"] == "10" and items[1]["probe"] == "alpha", items


@pytest.mark.parametrize("p,text,ok", [
    ("0.91", "coverage stayed at 0.911 versus 0", True),
    ("0.91", "coverage was 0.92", True),            # +-1 in the last printed digit
    ("0.91", "coverage was 0.89", False),
    ("0.91", "0.0912", False),
    ("12", "a gap of 13 points", True),
])
def test_abs_diff_stated(p, text, ok):
    assert dp.abs_diff_stated(p, text) is ok


def test_zero_baseline_end_to_end(tmp_path):
    items = _plan(tmp_path)
    write(tmp_path / "paper" / "manuscript.md", "# T\n\n## Introduction\n\nx\n\n## Results\n\n"
          "### The gated estimator keeps coverage above 0.90\n\nWorst-case coverage was 0.911 for gated versus 0 for B3_bailey.\n\n"
          "## Discussion\n\nx\n")
    r = run("draft_plan.py", "check", "--project", ".", cwd=tmp_path)
    for it in _main_items(items):
        assert f"[PASS] {it['id']}" in r.out, r.out


# ---------------------------------------------------------------- 2. regex probes on headings
def test_nature_results_subheading_probe_matches(tmp_path):
    items = _plan(tmp_path, state="target:\n  family: nature\n")
    res = next(i for i in items if i["source"] == "venue-profile nature" and i["section"] == "results")
    write(tmp_path / "paper" / "manuscript.md", "# T\n\n## Introduction\n\nHere we show x.\n\n## Results\n\n"
          "### Detection fails for six of nine audited motor speeds\n\nText.\n\n## Discussion\n\nconsistent with earlier work.\n")
    r = run("draft_plan.py", "check", "--project", ".", cwd=tmp_path)
    assert f"[PASS] {res['id']}" in r.out, r.out


def test_cs_ablation_heading_probe_matches(tmp_path):
    items = _plan(tmp_path, state="target:\n  venue: CVPR\n")
    abl = next(i for i in items if i["source"] == "venue-profile cs" and i["section"] == "results")
    write(tmp_path / "paper" / "manuscript.md", "# T\n\n## 1. Introduction\n\nx\n\n## 4. Experiments\n\n### 4.1 Main\n\nx\n\n"
          "### 4.2 Ablation\n\nRemoving the gate costs coverage.\n\n## 5. Conclusion\n\n3 things.\n")
    r = run("draft_plan.py", "check", "--project", ".", cwd=tmp_path)
    assert f"[PASS] {abl['id']}" in r.out, r.out


# ---------------------------------------------------------------- 3. section aliases
MS = ("# Video-Rate Tracking Cannot Identify Speed\n\n## Introduction\n\nintro\n\n## Results\n\n"
      "### Detection fails for six of nine speeds\n\nfirst result\n\n"
      "### Passive particles are flagged as propelled in 6.2% of experiments\n\npassive\n\n"
      "## Discussion\n\ndisc\n\n## Methods\n\n### Simulation grid\n\nmeth\n")


def test_alias_inside_a_subheading_is_not_the_section():
    res = dp.ms_section(MS, "results")
    assert "first result" in res and "passive" in res and "disc" not in res, res


def test_alias_must_start_the_heading():
    assert dp.ms_section("## Intro\n\nx\n\n### Results of experiments\n\ny\n", "results") is not None   # "Results" starts it
    assert dp.ms_section("## Intro\n\nx\n\n## Many experiments\n\ny\n", "results") is None


def test_section_level_preferred_over_title_and_subheadings():
    md = "# Results-aware tracking\n\n## Introduction\n\nx\n\n### Experiments overview\n\nsub\n\n## 4. Experiments\n\nexp\n\n## Conclusion\n\nc\n"
    assert dp.ms_section(md, "results").strip() == "exp"


def test_limitations_may_be_a_subheading_and_numbering_is_skipped():
    md = "# T\n\n## 1. Introduction\n\nx\n\n## 4. Experiments\n\n### 4.1 Main\n\nm\n\n### 4.6 Discussion and limitations\n\nlim\n\n## 5. Conclusion\n\nc\n"
    assert dp.ms_section(md, "limitations").strip() == "lim"
    assert "m" in dp.ms_section(md, "results") and dp.ms_section(md, "conclusion").strip() == "c"
    assert dp.ms_section("# T\n\n## II. **Methods**\n\nmeth\n\n## III. Results\n\nr\n", "method").strip() == "meth"
