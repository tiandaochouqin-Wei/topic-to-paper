# -*- coding: utf-8 -*-
"""2.11 survey upgrade: survey_tables.py, survey_figure.py and the new G-S0/G-S1/G-S3/G-S4/G-S5 rules, each with a mutation
that must FAIL (or WARN where the rule is advisory) on tests/fixtures/survey_min."""
import csv, io, json

from conftest import edit, read, run, write

SPEC = """tables:
  summary:
    group_by: M
    groups: ["1", "3"]
    label: "M{}"
    all: true
    stats:
      n: count
      median_delta: median(delta_rep)
      share_delta_ci: share(delta_ci=yes)
    digits: 3
"""


def state_add(project, text):
    """append keys under the survey: block of research-state.yaml"""
    edit(project / "research-state.yaml", "  claims: paper/claims.csv\n", "  claims: paper/claims.csv\n" + text)


def set_rows(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def rows_of(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


# ------------------------------------------------------------------ survey_tables.py summary + G-S4
def test_summary_spec_reproduces_fixture_table(survey):
    write(survey / "coding" / "tables.yaml", SPEC)
    r = run("survey_tables.py", "summary", "--verify", cwd=survey); assert r.fails == 0, r.out
    (survey / "coding" / "audit_summary.py").unlink()            # spec alone must satisfy G-S4
    r = run("survey_check.py", "tables", cwd=survey); assert r.fails == 0, r.out
    assert "tables.yaml" in r.out


def test_summary_spec_detects_hand_edit(survey):
    write(survey / "coding" / "tables.yaml", SPEC)
    (survey / "coding" / "audit_summary.py").unlink()
    edit(survey / "tables" / "summary.csv", "M3,2,0.015", "M3,2,0.012")
    r = run("survey_check.py", "tables", cwd=survey)
    assert r.fails >= 1 and "重算不一致" in r.out


def test_summary_quantiles_and_where(survey):
    write(survey / "coding" / "tables.yaml", "tables:\n  q:\n    where: \"L=0\"\n    stats:\n      n: count\n      q1: q1(delta_rep)\n      q3: q3(delta_rep)\n      k: count(ablation=yes)\n")
    r = run("survey_tables.py", "summary", cwd=survey); assert r.fails == 0, r.out
    row = rows_of(survey / "tables" / "q.csv")[0]
    assert row["group"] == "all" and row["n"] == "3" and row["k"] == "3"     # L=0 rows: a, c, d
    assert float(row["q1"]) <= float(row["q3"])


def test_crosstab_refuses_multivalued_column(survey):
    r = run("survey_tables.py", "crosstab", "--rows", "pair", "--cols", "task", cwd=survey)
    assert r.fails == 1 and "多值列" in r.out


def test_crosstab_matches_fixture_coverage(survey):
    r = run("survey_tables.py", "crosstab", "--rows", "mechanism", "--cols", "task", "--row-order", "concat,attn,graph", cwd=survey)
    assert r.fails == 0, r.out
    assert read(survey / "coding" / "coverage.csv").splitlines() == ["mechanism,dx,prog", "concat,1,0", "attn,1,1", "graph,0,1"]


def test_characteristics_and_prior_tables(survey):
    r = run("survey_tables.py", "characteristics", "--cols", "year,task,metric", cwd=survey)
    assert r.fails == 0 and "bibkey" in r.out                    # no bibkey column: identifiers instead, with a WARN
    assert "longtable" in read(survey / "tables" / "characteristics.tex")
    ps = rows_of(survey / "literature" / "prior_surveys.csv")
    for p, c in zip(ps, ("yes", "no")): p["covers_baseline_audit"] = "no"; p["covers_architectures"] = c
    set_rows(survey / "literature" / "prior_surveys.csv", ps)
    r = run("survey_tables.py", "prior", cwd=survey); assert r.fails == 0, r.out
    assert "baseline_audit" in r.out and r"\checkmark" in read(survey / "tables" / "prior_surveys.tex")


# ------------------------------------------------------------------ κ / PABAK + G-S3
def _second_coder(survey, change):
    rows = rows_of(survey / "coding" / "coded.csv")
    change(rows); set_rows(survey / "coding" / "coded2.csv", rows)


def test_kappa_disagreement_fails_gate(survey):
    _second_coder(survey, lambda rows: rows[0].update(M="3"))
    r = run("survey_tables.py", "kappa", "--b", "coding/coded2.csv", "--fields", "M,level", cwd=survey); assert r.fails == 0, r.out
    k = json.load(io.open(survey / "coding" / "kappa_results.json", encoding="utf-8"))
    assert k["M"] == 0.5 and k["level"] == 1.0 and k["_detail"]["M"]["agree"] == 0.75
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "['M']" in r.out


def test_kappa_prevalence_paradox_is_warn(survey):
    write(survey / "coding" / "kappa_results.json", json.dumps({"ablation": 0.47, "_detail": {"ablation": {"n": 90, "agree": 0.978, "kappa": 0.47, "pabak": 0.96}}}))
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails == 0, r.out
    assert "PABAK" in r.out and "[WARN]" in r.out


# ------------------------------------------------------------------ pending + exclusion QC (G-S3)
def test_pending_decision_fails(survey):
    edit(survey / "coding" / "screening_sheet.csv", "fix.f,Study F: a perspective on fusion,exclude,no quantitative results", "fix.f,Study F: a perspective on fusion,pending,api call failed")
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "pending" in r.out


def test_qc_sample_is_blind_and_must_be_filled(survey):
    r = run("survey_tables.py", "qc-sample", "--n", "5", "--near-miss", "fusion", cwd=survey); assert r.fails == 0, r.out
    qc = rows_of(survey / "coding" / "qc_exclusion_sample.csv")
    assert len(qc) == 2 and "decision" not in qc[0] and "reason" not in qc[0]
    assert {q["sample_type"] for q in qc} == {"near_miss"}             # both excludes mention fusion
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "未复核" in r.out


def test_qc_flip_not_applied_fails_then_passes(survey):
    run("survey_tables.py", "qc-sample", "--n", "5", cwd=survey)
    qc = rows_of(survey / "coding" / "qc_exclusion_sample.csv")
    for q in qc: q["qc_decision"] = "include" if q["doi"].endswith(".f") else "exclude"; q["qc_reason"] = "checked"
    set_rows(survey / "coding" / "qc_exclusion_sample.csv", qc)
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "仍是 exclude" in r.out
    for q in qc: q["qc_decision"] = "exclude"
    set_rows(survey / "coding" / "qc_exclusion_sample.csv", qc)
    r = run("survey_check.py", "coding", cwd=survey); assert r.fails == 0, r.out
    assert "排除复核 2 篇，误排 0" in r.out


def test_qc_missing_is_fail_for_systematic_review(survey):
    r = run("survey_check.py", "coding", cwd=survey); assert r.fails == 0, r.out       # narrative: WARN only
    state_add(survey, "  review_type: systematic\n")
    r = run("survey_check.py", "coding", cwd=survey)
    assert r.fails >= 1 and "qc_exclusion_sample" in r.out


# ------------------------------------------------------------------ seeds + saturation (G-S1)
def test_seed_recall(survey):
    write(survey / "literature" / "seed_studies.csv", "doi,pmid,arxiv_id,title,seed_source\n10.1000/FIX.A,,,,anchor refs\n,,,Study B: records plus imaging for prognosis,anchor refs\n")
    r = run("survey_check.py", "search", cwd=survey); assert r.fails == 0, r.out
    assert "种子召回 2/2" in r.out
    write(survey / "literature" / "seed_studies.csv", "doi,title\n10.1000/fix.a,\n10.1000/never.found,A study the search missed\n")
    r = run("survey_check.py", "search", cwd=survey)
    assert r.fails == 1 and "never.found" in r.out


def test_saturation_rule(survey):
    lp = survey / "literature" / "search_log.json"
    log = json.load(io.open(lp, encoding="utf-8"))
    base = list(log["sources"])
    log["sources"] = base + [{"source": "snowball:s2", "query": "seeds", "date": "2026-09-21", "count": 12, "new_included": n} for n in (3, 0, 0)]
    write(lp, json.dumps(log))
    r = run("survey_check.py", "search", cwd=survey); assert "已饱和" in r.out, r.out
    log["sources"] = base + [{"source": "snowball:s2", "query": "seeds", "date": "2026-09-21", "count": 12, "new_included": n} for n in (0, 2)]
    write(lp, json.dumps(log))
    r = run("survey_check.py", "search", cwd=survey)
    assert r.fails == 0 and "继续滚" in r.out


# ------------------------------------------------------------------ review type (G-S0)
def test_systematic_title_needs_systematic_review_type(survey):
    edit(survey / "research-state.yaml", 'title: "Fixture: multimodal fusion gain survey"', 'title: "A systematic review of multimodal fusion gain"')
    r = run("survey_check.py", "scope", cwd=survey)
    assert r.fails == 1 and "systematic" in r.out
    state_add(survey, "  review_type: systematic\n")
    r = run("survey_check.py", "scope", cwd=survey); assert r.fails == 0, r.out


# ------------------------------------------------------------------ writing (G-S5)
CATALOGUE = """# Fusion methods

Smith et al. proposed a concatenation model for diagnosis [1]. Lee et al. used attention over report tokens [2]. Wang et al. built a graph of records and signals [3]. Chen et al. added a gating layer to the image branch [4].

Patel et al. trained a transformer on notes [5]. Kim et al. fused genomics with slides [6]. Garcia et al. reported a stacking ensemble [7].
"""
SYNTHESIS = """# Fusion methods

Most reported gains shrink once the unimodal baseline is matched: the concatenation [1] and attention [2] models gain 0.06 and 0.04 over weak baselines, whereas the matched comparisons [3, 4] gain 0.02 or less. In contrast to these, graph fusion [3] reports no matched baseline at all.
"""


def test_catalogue_paragraphs_fail_and_synthesis_passes(survey):
    write(survey / "paper" / "manuscript.md", CATALOGUE)
    r = run("survey_check.py", "writing", cwd=survey)
    assert r.fails >= 1 and "逐篇罗列" in r.out
    write(survey / "paper" / "manuscript.md", SYNTHESIS)
    r = run("survey_check.py", "writing", cwd=survey)
    assert r.fails == 0 and "0/1 个带引用段落" in r.out, r.out


def test_unbounded_novelty_warns(survey):
    write(survey / "paper" / "manuscript.md", SYNTHESIS + "\nNo prior survey has audited baseline matching.\n")
    r = run("survey_check.py", "writing", cwd=survey); assert "无边界" in r.out
    write(survey / "paper" / "manuscript.md", SYNTHESIS + "\nWithin the searched sources, no prior survey has audited baseline matching.\n")
    r = run("survey_check.py", "writing", cwd=survey); assert "无边界" not in r.out


def test_tension_ledger_rules(survey):
    write(survey / "paper" / "manuscript.md", SYNTHESIS)
    tp = survey / "coding" / "tensions.csv"
    hdr = "study_a,study_b,topic,pair_assessment,resolution_status,resolution_pointer,note\n"
    write(tp, hdr + "fix.a,fix.c,gain size,contradiction,not_applicable,,\n")
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails >= 1 and "not_applicable" in r.out
    write(tp, hdr + "fix.a,fix.c,gain size,contradiction,resolved_in_synthesis,a sentence that is not there,\n")
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails >= 1 and "找不到" in r.out
    write(tp, hdr + "fix.a,fix.c,gain size,contradiction,flagged_unresolved,,\n")
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails >= 1 and "未解决" in r.out
    write(tp, hdr + "fix.a,fix.c,gain size,conditional_difference,resolved_in_synthesis,whereas the matched comparisons,\nfix.b,fix.d,metric,insufficient_overlap,not_applicable,,\n")
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails == 0, r.out
    assert "真冲突 1" in r.out


def test_included_studies_cited(survey):
    rows = rows_of(survey / "coding" / "coded.csv")
    for r_, k in zip(rows, ("smith21", "lee22", "wang23", "chen24")): r_["bibkey"] = k
    set_rows(survey / "coding" / "coded.csv", rows)
    write(survey / "paper" / "manuscript.md", SYNTHESIS.replace("[1]", "[@smith21]").replace("[2]", "[@lee22]").replace("[3, 4]", "[@wang23]"))
    r = run("survey_check.py", "writing", cwd=survey)
    assert "chen24" in r.out
    run("survey_tables.py", "characteristics", "--cols", "year,task", cwd=survey)
    r = run("survey_check.py", "writing", cwd=survey)
    assert "每篇在正文或特征表被引" in r.out, r.out


def test_reporting_checklist(survey):
    write(survey / "paper" / "manuscript.md", SYNTHESIS)
    state_add(survey, "  review_type: systematic\n")
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails >= 1 and "prisma_checklist" in r.out
    tpl = read(__import__("conftest").SKILL / "templates" / "prisma2020_checklist.csv")
    write(survey / "paper" / "prisma_checklist.csv", tpl)
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails >= 1 and "未定位" in r.out
    rows = rows_of(survey / "paper" / "prisma_checklist.csv")
    for x in rows: x["location"] = "§2"
    set_rows(survey / "paper" / "prisma_checklist.csv", rows)
    r = run("survey_check.py", "writing", cwd=survey); assert r.fails == 0, r.out


# ------------------------------------------------------------------ survey_figure.py
def test_figures_render_and_register(survey):
    for args in (("prisma", "--out", "figures/fig_prisma.png"), ("timeline", "--out", "figures/fig_tl.png", "--by", "task"),
                 ("coverage", "--out", "figures/fig_cov.png"), ("bubble", "--out", "figures/fig_ev.png", "--x", "mechanism", "--y", "task", "--colour", "ext_val=yes")):
        r = run("survey_figure.py", *args, cwd=survey)
        assert r.returncode == 0 and not r.crashed, r.out
        assert "caption numbers" in r.out
        assert (survey / args[2].replace(".png", ".pdf")).exists()
    files = [x["file"] for x in rows_of(survey / "figures.csv")]
    assert {"figures/fig_prisma.png", "figures/fig_tl.png", "figures/fig_cov.png", "figures/fig_ev.png"} <= set(files)
    src = rows_of(survey / "figures" / "fig_prisma.source.csv")
    assert {"count": "included", "n": "4"} in src


def test_prisma_reasons_must_add_up(survey):
    # 8 assessed − 4 included = 4 excluded at abstract level, but only one abstract-level exclusion is in the sheet
    edit(survey / "coding" / "screening_sheet.csv", "fix.f,Study F: a perspective on fusion,exclude,no quantitative results,title", "fix.f,Study F: a perspective on fusion,exclude,no quantitative results,abstract")
    r = run("survey_figure.py", "prisma", "--out", "figures/fig_prisma.png", cwd=survey)
    assert r.returncode == 1 and "排除理由合计 1" in r.out


def test_figure_refuses_multivalued_and_bad_levels(survey):
    r = run("survey_figure.py", "timeline", "--out", "figures/t.png", "--by", "pair", cwd=survey)
    assert r.returncode == 1 and "多值列" in r.out
    r = run("survey_figure.py", "rob", "--out", "figures/r.png", "--domains", "ablation", "--levels", "low,high", cwd=survey)
    assert r.returncode == 1 and "--levels" in r.out
    r = run("survey_figure.py", "rob", "--out", "figures/r.png", "--domains", "ablation,missing_test", "--levels", "yes,no", "--labels", "ablation=Ablation", cwd=survey)
    assert r.returncode == 0, r.out
