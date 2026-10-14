# -*- coding: utf-8 -*-
"""tests for the G5 figure/table count floor (validation round 16)."""
from conftest import edit, read, run, write
import io, re


def _set_target(research, **kv):
    """rewrite target.<k> via yaml so quoted/empty values round-trip exactly"""
    import yaml
    p = research / "research-state.yaml"; st = yaml.safe_load(io.open(p, encoding="utf-8")) or {}
    st.setdefault("target", {}).update(kv)
    io.open(p, "w", encoding="utf-8").write(yaml.safe_dump(st, allow_unicode=True, sort_keys=False))


def _n_caps(research, kind):
    t = io.open(research / "paper" / "manuscript.md", encoding="utf-8").read()
    return len(re.findall(rf"^\**\s*{kind}\s*\d+[\.\:\*]", t, re.M | re.I))


def test_g5_count_warns_when_below_venue_floor(research):
    """fixture has one figure caption; NeurIPS papers have >= 4 figures at the lower quartile -> WARN names both counts"""
    _set_target(research, venue="NeurIPS", family="cs_conf")
    r = run("gate_check.py", "dpi", cwd=research)
    assert "四分之三的论文有的" in r.out and "venue NeurIPS" in r.out, r.out
    assert r.fails == 0 or "四分之三" not in "".join(l for l in r.out.splitlines() if l.startswith("[FAIL]")), "count floor must WARN, not FAIL"


def test_g5_count_waiver_downgrades_to_info(research):
    _set_target(research, venue="NeurIPS", family="cs_conf", figure_count_waiver="short paper, two-page limit")
    r = run("gate_check.py", "dpi", cwd=research)
    assert "已豁免" in r.out and "short paper" in r.out, r.out
    assert not any("四分之三" in l and l.startswith("[WARN]") for l in r.out.splitlines()), r.out


def test_g5_count_passes_with_enough_captions(research):
    _set_target(research, venue="MICCAI", family="cs_conf")   # MICCAI floor: 2 figures, 1 table
    m = research / "paper" / "manuscript.md"
    write(m, read(m) + "\n\n**Fig. 2.** Second figure.\n\n**Table 1.** A table.\n\n**Table 2.** Another table.\n")
    r = run("gate_check.py", "dpi", cwd=research)
    assert "不低于" in r.out and "MICCAI" in r.out, r.out


def test_g5_count_falls_back_to_family_for_unknown_venue(research):
    _set_target(research, venue="SomeNewVenue", family="cs_conf")
    r = run("gate_check.py", "dpi", cwd=research)
    assert "family cs_conf" in r.out, r.out


def test_g5_count_silent_without_venue_or_family(research):
    _set_target(research, venue="", family="")
    r = run("gate_check.py", "dpi", cwd=research)
    assert "四分之三" not in r.out and "不低于" not in r.out, r.out
