# -*- coding: utf-8 -*-
"""Batch C: entry points (init --entry, N/A gates), the board written back into state.gates, template detection by
comparison with templates/, and the post-hoc preregistration marker."""
import re

import yaml

from conftest import FIXTURES, SKILL, edit, lock, read, run, write


def _state(project):
    return yaml.safe_load(read(project / "research-state.yaml"))


# ------------------------------------------------------------------ init --entry / N/A
def test_init_have_draft_marks_early_gates_na(tmp_path):
    proj = tmp_path / "draft"
    r = run("t2p.py", "init", "--project", str(proj), "--venue", "TPAMI", "--field", "cv", "--entry", "have_draft", cwd=tmp_path)
    assert r.returncode == 0, r.out
    st = _state(proj)
    assert st["project"]["entry"] == "have_draft" and st["phase"]["current"] == "P6"
    assert "G1b" in st["gates"] and "G6b" in st["gates"] and "G6c" in st["gates"] and "G6e" in st["gates"]     # template lists every reported gate
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    for g in ("G1b", "G2", "G3", "G4", "G5"):
        assert f"[N/A] {g}:" in c.out and f"[PENDING] {g}:" not in c.out, c.out
    assert "[PENDING] G0:" in c.out                       # guide.txt is still required
    assert "下一步：修 G0" in c.out                       # not G1b
    assert c.returncode == 0                              # N/A and PENDING are not failures


def test_na_gate_runs_normally_once_its_input_exists(tmp_path):
    proj = tmp_path / "draft"
    run("t2p.py", "init", "--project", str(proj), "--venue", "TPAMI", "--entry", "have_draft", cwd=tmp_path)
    write(proj / "prereg.md", read(FIXTURES / "research_min" / "prereg.md"))      # a real prereg appears
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    assert "[N/A] G2:" not in c.out and re.search(r"\[(PASS|FAIL)\] G2:", c.out), c.out


def test_init_topic_only_has_no_na(tmp_path):
    proj = tmp_path / "topic"
    run("t2p.py", "init", "--project", str(proj), "--venue", "CVPR", cwd=tmp_path)
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    assert "[N/A]" not in c.out and "[PENDING] G2:" in c.out and "下一步：修 G0" in c.out


def test_init_survey_lists_survey_gates(tmp_path):
    proj = tmp_path / "sv"
    run("t2p.py", "init", "--project", str(proj), "--venue", "Information Fusion", "--branch", "survey", cwd=tmp_path)
    st = _state(proj)
    assert st["branch"] == "survey"
    assert "G-S2" in st["gates"] and "protocol_sha256" in st["gates"]["G-S2"]
    assert "G2" not in st["gates"] and "G8" not in st["gates"]
    assert "G0" in st["gates"] and "G1" in st["gates"]


# ------------------------------------------------------------------ template detection
def test_fresh_templates_are_pending_not_failing(tmp_path):
    proj = tmp_path / "fresh"
    run("t2p.py", "init", "--project", str(proj), "--venue", "CVPR", cwd=tmp_path)
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    assert "[PENDING] G2:" in c.out and "[PENDING] G5:" in c.out and "[FAIL]" not in c.out, c.out


def test_header_only_figures_csv_is_pending(research):
    write(research / "figures.csv", "file,print_width_mm,source_data,inspected,issues\n")
    c = run("t2p.py", "check", "--project", ".", cwd=research)
    assert "[PENDING] G5:" in c.out and "[PASS] G5:" not in c.out, c.out


def test_edited_template_is_checked(tmp_path):
    proj = tmp_path / "fresh"
    run("t2p.py", "init", "--project", str(proj), "--venue", "CVPR", cwd=tmp_path)
    edit(proj / "prereg.md", "一句可证伪的话", "Our hypothesis is that nothing works.")   # the old magic substring is gone, file differs from template
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    assert "[FAIL] G2:" in c.out, c.out       # a half-filled prereg must be checked, not treated as a template


# ------------------------------------------------------------------ state write-back
def test_check_writes_board_into_state_gates(research):
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    sha_before = _state(research)["gates"]["G2"]["prereg_sha256"]
    c = run("t2p.py", "check", "--project", ".", cwd=research); assert c.returncode == 0, c.out
    st = _state(research)
    for g in ("G0", "G1b", "G2", "G3", "G4", "G5", "G6", "G6b", "G6c", "G7", "G8"):
        assert st["gates"][g]["status"] == "pass", (g, st["gates"][g])
        assert st["gates"][g]["checked"]
    assert st["gates"]["G1"]["status"] == "skip"
    assert st["gates"]["G2"]["prereg_sha256"] == sha_before                  # extra keys survive the rewrite
    text = read(research / "research-state.yaml")
    assert text.count("  G6b:") == 1 and text.count("  G2:") == 1            # rewritten in place, not duplicated
    assert "# 由 `t2p.py check` 写回" in text or "gates:" in text            # comments elsewhere untouched
    assert "acronym_ok: [EAAI]" in text and "blind_terms: [Zhang, Karolinska]" in text


def test_status_reads_what_check_wrote(research):
    before = run("t2p.py", "status", "--project", ".", cwd=research)
    assert "从未" in before.out
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    edit(research / "submission" / "cover_letter.md", "19.2%", "21.5%")          # break G8 on purpose
    c = run("t2p.py", "check", "--project", ".", cwd=research); assert c.returncode == 1
    after = run("t2p.py", "status", "--project", ".", cwd=research)
    assert "上次 check: 20" in after.out
    assert re.search(r"G8\s+fail", after.out) and re.search(r"G2\s+pass", after.out), after.out
    assert "下一道未过关口: G8" in after.out


def test_check_twice_is_idempotent(research):
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    run("t2p.py", "check", "--project", ".", cwd=research)
    first = read(research / "research-state.yaml")
    run("t2p.py", "check", "--project", ".", cwd=research)
    second = read(research / "research-state.yaml")
    strip = lambda s: re.sub(r"checked: '[^']*'", "checked: X", s)
    assert strip(first) == strip(second)


def test_no_write_leaves_state_alone(research):
    before = read(research / "research-state.yaml")
    run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert read(research / "research-state.yaml") == before


def test_survey_write_back_keeps_protocol_lock(survey):
    sha = _state(survey)["gates"]["G-S2"]["protocol_sha256"]
    c = run("t2p.py", "check", "--project", ".", cwd=survey); assert c.returncode == 0, c.out
    st = _state(survey)
    assert st["gates"]["G-S2"]["status"] == "pass" and st["gates"]["G-S2"]["protocol_sha256"] == sha
    assert st["gates"]["G-S3"]["status"] == "pass" and st["gates"]["G-S5"]["status"] == "pass"


def test_write_back_creates_gates_block_when_missing(research):
    p = research / "research-state.yaml"
    write(p, re.sub(r"(?ms)^gates:.*?(?=^\w)", "", read(p)))     # drop the whole block
    assert "gates:" not in read(p)
    run("t2p.py", "check", "--project", ".", cwd=research)
    st = _state(research)
    assert st["gates"]["G0"]["status"] == "pass" and st["gates"]["G7"]["status"] == "pass"


# ------------------------------------------------------------------ post-hoc preregistration
def test_posthoc_prereg_marker_downgrades_to_warn(research):
    edit(research / "research-state.yaml", 'prereg_sha256: "', 'prereg_sha256: "x')   # break the lock -> "never locked"
    s = read(research / "research-state.yaml"); write(research / "research-state.yaml", re.sub(r'prereg_sha256: "[^"]*"', 'prereg_sha256: ""', s))
    r = run("prereg_check.py", cwd=research)
    assert "[FAIL]" in r.out and "事后注册" in r.out, r.out
    write(research / "prereg.md", "post-hoc: written after the 11 runs in state; see Methods.\n" + read(research / "prereg.md"))
    r2 = run("prereg_check.py", cwd=research)
    assert "[WARN]" in r2.out and "事后注册" in r2.out and r2.fails == 0, r2.out
