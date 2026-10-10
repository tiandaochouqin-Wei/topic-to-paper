# -*- coding: utf-8 -*-
"""Survey-branch gates on tests/fixtures/survey_min: protocol (G-S2), coding (G-S3), claims (G-S5) and the re-derivable summary table."""
import subprocess

from conftest import ENV, PY, edit, read, run, write


# ------------------------------------------------------------------ G-S2  protocol
def test_protocol_pass(survey):
    r = run("survey_check.py", "protocol", cwd=survey); assert r.fails == 0, r.out


def test_protocol_vague_rule(survey):
    edit(survey / "protocol.md", "- Full text not available in English.", "- Papers that look relevant to the topic.")
    r = run("survey_check.py", "protocol", cwd=survey)
    assert r.fails >= 1 and "可判定词" in r.out


def test_protocol_edited_after_lock(survey):
    write(survey / "protocol.md", read(survey / "protocol.md") + "\nA rule added after locking.\n")
    r = run("survey_check.py", "protocol", cwd=survey)
    assert r.fails >= 1 and "锁未更新" in r.out


def test_protocol_claim_without_criterion(survey):
    edit(survey / "protocol.md", "| fraction of delta_ci = yes < 0.5 |", "| most of them |")
    r = run("survey_check.py", "protocol", cwd=survey)
    assert r.fails >= 1 and "无判据" in r.out


# ------------------------------------------------------------------ G-S3  coding
def test_coding_pass(survey):
    r = run("survey_check.py", "coding", cwd=survey); assert r.fails == 0, r.out


def test_coding_value_outside_codebook(survey):
    edit(survey / "coding" / "coded.csv", ",concat,", ",stacking,")
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "codebook" in r.out


def test_coding_prisma_count_mismatch(survey):
    edit(survey / "literature" / "prisma_flow.json", '"included": 4', '"included": 5')
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "PRISMA" in r.out


def test_coding_low_kappa(survey):
    edit(survey / "coding" / "kappa_results.json", '"M": 0.66', '"M": 0.40')
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "κ" in r.out


def test_coding_decision_without_reason(survey):
    edit(survey / "coding" / "screening_sheet.csv", "exclude,single data-source family,title", "exclude,,title")
    assert run("survey_check.py", "coding", cwd=survey).fails >= 1


# ------------------------------------------------------------------ G-S5  claims
def test_claims_pass(survey):
    r = run("survey_check.py", "claims", cwd=survey); assert r.fails == 0, r.out


def test_claims_criterion_violated(survey):
    edit(survey / "tables" / "summary.csv", "M3,2,0.015,0.500", "M3,2,0.050,0.500")
    r = run("survey_check.py", "claims", cwd=survey)
    assert r.fails >= 1 and "不满足判据" in r.out


def test_claims_first_claim_without_prior_survey_diff(survey):
    p = survey / "literature" / "prior_surveys.csv"
    write(p, "title,year,venue,doi,how_this_differs\nA survey of multimodal fusion in medical imaging,2022,Medical Image Analysis,10.1000/prior.1,\n")
    r = run("survey_check.py", "claims", cwd=survey)
    assert r.fails >= 1 and "差异" in r.out


def test_claims_evidence_cell_missing(survey):
    edit(survey / "paper" / "claims.csv", '"group=M3,median_delta"', '"group=M9,median_delta"')
    r = run("survey_check.py", "claims", cwd=survey)
    assert r.fails >= 1 and "取不到" in r.out


# ------------------------------------------------------------------ G-S0  scope
def test_scope_pass(survey):
    r = run("survey_check.py", "scope", cwd=survey); assert r.fails == 0, r.out


def test_scope_thesis_is_a_table_of_contents(survey):
    edit(survey / "research-state.yaml", 'thesis: "the reported fusion gain shrinks as the baseline matching level gets stricter"', 'thesis: "we review multimodal fusion in clinical models"')
    r = run("survey_check.py", "scope", cwd=survey)
    assert r.fails >= 1 and "论点" in r.out


def test_scope_invalid_axis(survey):
    edit(survey / "research-state.yaml", "axis: method-level", "axis: everything")
    assert run("survey_check.py", "scope", cwd=survey).fails >= 1


def test_scope_missing_scope_out(survey):
    edit(survey / "research-state.yaml", 'scope_out: "fusion within one family (for example multi-sequence MRI), covered by the prior survey [1]"', 'scope_out: ""')
    r = run("survey_check.py", "scope", cwd=survey)
    assert r.fails >= 1 and "scope_out" in r.out


# ------------------------------------------------------------------ G-S1  search
def test_search_pass(survey):
    r = run("survey_check.py", "search", cwd=survey); assert r.fails == 0, r.out


def test_search_source_without_date(survey):
    edit(survey / "literature" / "search_log.json", '"date": "2026-09-20", "count": 9', '"count": 9')
    r = run("survey_check.py", "search", cwd=survey)
    assert r.fails >= 1 and "arxiv" in r.out


def test_search_candidate_without_identifier(survey):
    edit(survey / "literature" / "candidates.csv", "arxiv,,,2401.00001,", "arxiv,,,,")
    r = run("survey_check.py", "search", cwd=survey)
    assert r.fails >= 1 and "标识符" in r.out


def test_search_duplicate_doi(survey):
    p = survey / "literature" / "candidates.csv"
    write(p, read(p) + "pubmed,10.1000/fix.a,30000099,,Study A again,2021,Medical Image Analysis\n")
    r = run("survey_check.py", "search", cwd=survey)
    assert r.fails >= 1 and "重复" in r.out


def test_search_prior_surveys_missing(survey):
    (survey / "literature" / "prior_surveys.csv").unlink()
    r = run("survey_check.py", "search", cwd=survey)
    assert r.fails >= 1 and "prior_surveys" in r.out


# ------------------------------------------------------------------ G-S4  tables
def test_tables_pass(survey):
    r = run("survey_check.py", "tables", cwd=survey)
    assert r.fails == 0 and "格子合计" in r.out, r.out


def test_tables_coverage_sum_mismatch(survey):
    edit(survey / "coding" / "coverage.csv", "graph,0,1", "graph,0,2")
    r = run("survey_check.py", "tables", cwd=survey)
    assert r.fails >= 1 and "纳入篇数" in r.out


def test_tables_summary_not_rederivable(survey):
    edit(survey / "tables" / "summary.csv", "M1,2,0.050,0.000", "M1,2,0.060,0.000")
    r = run("survey_check.py", "tables", cwd=survey)
    assert r.fails >= 1 and "--verify" in r.out


def test_tables_no_generator_script(survey):
    (survey / "coding" / "audit_summary.py").unlink()
    r = run("survey_check.py", "tables", cwd=survey)
    assert r.fails >= 1 and "summary" in r.out


# ------------------------------------------------------------------ S4  summary table re-derivable from coded.csv
def test_summary_table_verifies(survey):
    r = subprocess.run([PY, "coding/audit_summary.py", "--verify"], cwd=str(survey), capture_output=True, text=True, encoding="utf-8", env=ENV)
    assert r.returncode == 0, r.stdout + r.stderr
    edit(survey / "tables" / "summary.csv", "all,4,0.030,0.250", "all,4,0.040,0.250")
    r = subprocess.run([PY, "coding/audit_summary.py", "--verify"], cwd=str(survey), capture_output=True, text=True, encoding="utf-8", env=ENV)
    assert r.returncode == 1
