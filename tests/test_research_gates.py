# -*- coding: utf-8 -*-
"""Research-branch gates on tests/fixtures/research_min: the untouched copy PASSes, each named mutation FAILs the gate that owns it."""
import json

from conftest import edit, lock, read, run, touch, write


# ------------------------------------------------------------------ G1b  gap_map / transfer_scan / problem_table
def test_g1b_pass(research):
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails == 0 and "P1 判定 go" in r.out, r.out


def test_g1b_go_without_claim_source(research):
    edit(research / "literature" / "gap_map.md", "claim_source: gap#A", "claim_source:")
    assert run("transfer_scan.py", "check", cwd=research).fails >= 1


def test_g1b_problem_table_too_short(research):
    p = research / "literature" / "problem_table.csv"
    write(p, "\n".join(read(p).splitlines()[:6]) + "\n")          # header + 5 rows < 8
    assert run("transfer_scan.py", "check", cwd=research).fails >= 1


def test_g1b_domain_count_not_reached(research):
    edit(research / "literature" / "transfer_scan.md", "oa:1+local:0", "oa:?+local:0")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "重跑" in r.out


def test_g1b_three_weak_dimensions_is_nogo(research):
    g = research / "literature" / "gap_map.md"
    for k in ("- 新颖性: ", "- 可验证性: ", "- 可推广性: "):
        edit(g, k, k + "弱：")
    assert run("transfer_scan.py", "check", cwd=research).fails >= 1


# ------------------------------------------------------------------ G2  preregistration
def test_g2_pass(research):
    r = run("prereg_check.py", cwd=research)
    assert r.fails == 0, r.out


def test_g2_missing_statistical_rule(research):
    edit(research / "prereg.md", "with 3 seeds per method, the same seed set for every method, and a paired t-test at alpha 0.05 on the per-seed values", "on all runs")
    lock(research, "prereg.md", "prereg_sha256")
    r = run("prereg_check.py", cwd=research)
    assert r.fails >= 1 and "统计判据" in r.out


def test_g2_edited_after_lock(research):
    write(research / "prereg.md", read(research / "prereg.md") + "\nA line added after locking.\n")
    r = run("prereg_check.py", cwd=research)
    assert r.fails >= 1 and "锁没更新" in r.out


def test_g2_no_fallback_claim(research):
    edit(research / "prereg.md", "fallback claim: the sensor offset is dataset-specific and we instead report a calibration study of the offset rather than a method claim.", "we stop.")
    lock(research, "prereg.md", "prereg_sha256")
    r = run("prereg_check.py", cwd=research)
    assert r.fails >= 1 and "备选" in r.out


def test_g2_claim_source_missing_is_flagged(research):
    edit(research / "prereg.md", "来源: gap#A\n", "")
    lock(research, "prereg.md", "prereg_sha256")
    assert "未写主张来源" in run("prereg_check.py", cwd=research).out


# ------------------------------------------------------------------ G3  build audit
def test_g3_pass(research):
    r = run("audit_check.py", cwd=research)
    assert r.fails == 0, r.out


def _args(research, run_name):
    return research / "runs" / run_name / "args.json"


def test_g3_leak_flag_on(research):
    edit(_args(research, "ours_s0"), '"use_target_labels": 0', '"use_target_labels": 1')
    r = run("audit_check.py", cwd=research)
    assert r.fails >= 1 and "leakage" in r.out


def test_g3_unfinished_run(research):
    p = research / "runs" / "ours_s1" / "log.json"
    write(p, json.dumps(json.loads(read(p))[:1]))
    r = run("audit_check.py", cwd=research)
    assert r.fails >= 1 and "未训完" in r.out


def test_g3_hyperparameter_not_effective(research):
    p = research / "runs" / "ours_s2" / "log.json"
    log = json.loads(read(p))
    for e in log: e["train_dom"] = 0.0
    write(p, json.dumps(log))
    r = run("audit_check.py", cwd=research)
    assert r.fails >= 1 and "effective-config" in r.out


def test_g3_split_overlap(research):
    write(research / "splits" / "test.txt", read(research / "splits" / "test.txt") + "S01\n")
    r = run("audit_check.py", cwd=research)
    assert r.fails >= 1 and "共享" in r.out


def test_g3_silent_fallback_in_code(research):
    edit(research / "code" / "train.py", 'raise FileNotFoundError("frames/ missing under " + a.data)', 'print("frames/ missing, continuing without vision")')
    r = run("audit_check.py", cwd=research)
    assert r.fails >= 1 and "silent-fallback" in r.out


def test_g3_mixed_hardware(research):
    edit(_args(research, "baseB_s0"), '"hardware": "A2000"', '"hardware": "RTX4090"')
    r = run("audit_check.py", cwd=research)
    assert r.fails >= 1 and "硬件" in r.out


# ------------------------------------------------------------------ G4  results traceability + ablation resolution
def test_g4_pass(research):
    r = run("results_check.py", cwd=research); assert r.fails == 0, r.out
    a = run("ablation_plan.py", "resolve", cwd=research); assert a.fails == 0 and "可解读格 2/4" in a.out, a.out


def test_g4_table_number_drift(research):
    edit(research / "results" / "main.csv", "ours_s2,ours,2,A2000,0.204,0.306", "ours_s2,ours,2,A2000,0.214,0.306")
    r = run("results_check.py", cwd=research)
    assert r.fails >= 1 and "trace" in r.out


def test_g4_missing_seed(research):
    p = research / "results" / "main.csv"
    write(p, read(p).replace("ours_s2,ours,2,A2000,0.204,0.306\n", ""))
    r = run("results_check.py", cwd=research)
    assert r.fails >= 1 and "seed" in r.out


def test_g4_stale_evaluation(research):
    touch(research / "runs" / "ours_s0" / "log.json", +60)       # training log newer than its eval
    r = run("results_check.py", cwd=research)
    assert r.fails >= 1 and "陈旧" in r.out


def test_g4_tainted_eval(research):
    p = research / "runs" / "baseA_s0" / "eval.json"
    ev = json.loads(read(p)); ev["_tainted"] = True; write(p, json.dumps(ev))
    r = run("results_check.py", cwd=research)
    assert r.fails >= 1 and "_tainted" in r.out


def test_g4_sign_flip_needs_findings_entry(research):
    edit(research / "results" / "ablation.csv", "no_dom,abl_no_dom,0,A2000,0.250,0.355", "no_dom,abl_no_dom,0,A2000,0.150,0.355")
    p = research / "runs" / "abl_no_dom" / "eval.json"
    ev = json.loads(read(p)); ev["E1"]["rmse"] = 0.150; write(p, json.dumps(ev)); touch(p, +2)
    r = run("results_check.py", cwd=research)
    assert "[FAIL] predictions" in r.out, r.out
    write(research / "findings.md", "## F1 2026-10-10 no_dom rmse_E1\nwhat: no_dom beats ours on rmse_E1, opposite to the preregistered sign\ncause: open\n")
    r2 = run("results_check.py", cwd=research)
    assert "[FAIL] predictions" not in r2.out and "[WARN] predictions" in r2.out, r2.out


def test_g4_ablation_row_missing(research):
    p = research / "results" / "ablation.csv"
    write(p, read(p).replace("no_cons,abl_no_cons,0,A2000,0.203,0.304\n", ""))
    assert run("results_check.py", cwd=research).fails >= 1
    assert run("ablation_plan.py", "resolve", cwd=research).fails >= 1


# ------------------------------------------------------------------ G5  figures
def test_g5_pass(research):
    r = run("gate_check.py", "dpi", cwd=research); assert r.fails == 0, r.out


def test_g5_low_dpi(research):
    from PIL import Image
    Image.new("RGB", (600, 400), "white").save(research / "figures" / "fig_main.png")
    r = run("gate_check.py", "dpi", cwd=research)
    assert r.fails >= 1 and "dpi" in r.out


def test_g5_not_inspected(research):
    edit(research / "figures.csv", ",yes,", ",no,")
    assert run("gate_check.py", "dpi", cwd=research).fails >= 1


# ------------------------------------------------------------------ G6  manuscript gates
def test_g6_all_pass(research):
    r = run("gate_check.py", "all", "--no-net", cwd=research)
    assert r.fails == 0 and "ALL PASS" in r.out, r.out


def test_g6_orphan_figure(research):
    edit(research / "paper" / "manuscript.md", "## References", "**Fig. 2.** An orphan figure that nothing in the text cites.\n\n## References")
    r = run("gate_check.py", "floats", cwd=research)
    assert r.fails >= 1 and "无人引用" in r.out


def test_g6_dangling_citation(research):
    edit(research / "paper" / "manuscript.md", "Table 1 reports the main comparison", "Table 3 reports the main comparison")
    r = run("gate_check.py", "floats", cwd=research)
    assert r.fails >= 1 and "不存在的编号" in r.out


def test_g6_acronym_undefined_in_abstract(research):
    edit(research / "paper" / "manuscript.md", "Vision-based force estimation lets", "Vision-based force estimation with DA lets")
    r = run("gate_check.py", "acronyms", cwd=research)
    assert r.fails >= 1 and "摘要内" in r.out


def test_g6_table_number_changed(research):
    edit(research / "paper" / "manuscript.md", "| ours | 0.202 ± 0.002 |", "| ours | 0.212 ± 0.002 |")
    r = run("gate_check.py", "numbers", cwd=research)
    assert r.fails >= 1 and "numbers" in r.out


def test_g6_unregistered_table_number(research):
    edit(research / "paper" / "manuscript.md", "| no_cons | 0.203 | 0.304 |", "| no_cons | 0.203 | 0.304 |\n| extra | 0.999 | 0.888 |")
    r = run("gate_check.py", "numbers", cwd=research)
    assert r.fails >= 1 and "未登记" in r.out


def test_g6_reference_limit(research):
    edit(research / "research-state.yaml", "ref_max: 80", "ref_max: 2")
    r = run("gate_check.py", "limits", cwd=research)
    assert r.fails >= 1 and "ref_max" in r.out


# ------------------------------------------------------------------ G6b  must-write checklist
def _plan(research):
    assert run("draft_plan.py", "plan", "--project", ".", cwd=research).returncode == 0


def test_g6b_pass(research):
    _plan(research)
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails == 0, r.out


def test_g6b_resolution_statement_missing(research):
    _plan(research)
    m = research / "paper" / "manuscript.md"
    edit(m, "not resolvable", "uncertain"); edit(m, "within seed noise", "within error")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails >= 1 and "不可解读" in r.out


def test_g6b_contribution_list_missing(research):
    _plan(research)
    edit(research / "paper" / "manuscript.md", "The contributions of this paper are:", "In short:")
    assert run("draft_plan.py", "check", "--project", ".", cwd=research).fails >= 1


def test_g6b_baseline_not_named_in_results(research):
    _plan(research)
    edit(research / "paper" / "manuscript.md", "baseB", "baseC")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails >= 1 and "baseB" in r.out


# ------------------------------------------------------------------ G6c  manuscript shape
def test_g6c_pass(research):
    r = run("shape_check.py", cwd=research)
    assert r.fails == 0 and "family = cs_journal" in r.out, r.out


def test_g6c_cs_draft_judged_as_nature_fails(research):
    r = run("shape_check.py", "--family", "nature", cwd=research)
    assert r.fails >= 1 and "Nature" in r.out


def test_g6c_abstract_over_limit(research):
    edit(research / "research-state.yaml", "abstract_word_limit: 250", "abstract_word_limit: 100")
    r = run("shape_check.py", cwd=research)
    assert r.fails >= 1 and "摘要" in r.out


# ------------------------------------------------------------------ G7  review loop
def _g6(research):
    assert run("gate_check.py", "all", "--no-net", cwd=research).fails == 0      # writes gate_report.md after the manuscript


def test_g7_pass(research):
    _g6(research)
    r = run("review_check.py", cwd=research)
    assert r.fails == 0, r.out


def test_g7_major_without_disposition(research):
    _g6(research)
    edit(research / "paper" / "review_log.md", "## Re-review", "3. [major] Add a third platform.\n\n## Re-review")
    r = run("review_check.py", cwd=research)
    assert r.fails >= 1 and "无处置" in r.out or "未在复审节关闭" in r.out


def test_g7_round_not_recorded(research):
    _g6(research)
    edit(research / "research-state.yaml", "round: 1", "round: 0")
    r = run("review_check.py", cwd=research)
    assert r.fails >= 1 and "round" in r.out


def test_g7_manuscript_edited_after_last_gate_run(research):
    _g6(research)
    touch(research / "paper" / "manuscript.md", +60)
    r = run("review_check.py", cwd=research)
    assert r.fails >= 1 and "没重跑" in r.out


# ------------------------------------------------------------------ G8  submission package
def test_g8_pass(research):
    r = run("gate_check.py", "submission", cwd=research); assert r.fails == 0, r.out


def test_g8_cover_letter_number_drifted(research):
    edit(research / "submission" / "cover_letter.md", "19.2%", "21.5%")
    r = run("gate_check.py", "submission", cwd=research)
    assert r.fails >= 1 and "未在正文出现" in r.out


def test_g8_blind_copy_leaks_identity(research):
    # the leak must sit in the body: the gate deliberately ignores the reference list (cited authors are not a leak)
    edit(research / "submission" / "blind.md", "## References", "This work was funded by grant no 12345 to Zhang at Karolinska.\n\n## References")
    r = run("gate_check.py", "submission", cwd=research)
    assert r.fails >= 1 and "盲稿" in r.out


# ------------------------------------------------------------------ G1b  tests 2 / 3 judged mechanically (2026-10-11)
def _scan(research):
    return research / "literature" / "transfer_scan.md"


def test_g1b_architecture_words_are_not_a_correspondence(research):
    edit(_scan(research), "| platform identity as the nuisance |", "| both use a Transformer encoder with attention |")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "T1" in r.out and "架构词" in r.out and "对应物" in r.out, r.out


def test_g1b_correspondence_without_domain_noun(research):
    edit(_scan(research), "| platform identity as the nuisance |", "| the same idea works here too |")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "T1" in r.out and "领域" in r.out, r.out


def test_g1b_not_yet_applied_is_not_a_failure_point(research):
    edit(_scan(research), "| the nuisance is in the label channel, not the input, so the discriminator must see the prediction head |",
         "| has not yet been applied to surgical force estimation |")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "T1" in r.out and "还没人用过" in r.out, r.out


def test_g1b_failure_point_without_breaking_predicate(research):
    edit(_scan(research), "| the nuisance is in the label channel, not the input, so the discriminator must see the prediction head |",
         "| surgical force sensor offset platform calibration regression |")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "T1" in r.out and "谓词" in r.out, r.out


def test_g1b_failure_point_as_a_label_is_too_short(research):
    edit(_scan(research), "| the nuisance is in the label channel, not the input, so the discriminator must see the prediction head |", "| offset not modelled |")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "T1" in r.out and "太短" in r.out, r.out


def test_g1b_ruled_out_rows_are_not_judged(research):
    """T3 is 淘汰-无失效点 with an empty cell: the author's ruling stands, no FAIL for it."""
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails == 0 and "T3" not in r.out, r.out


def test_g1b_claim_source_pointing_at_a_shape_failure(research):
    edit(research / "literature" / "gap_map.md", "claim_source: gap#A", "claim_source: transfer#T2")
    edit(_scan(research), "| the offset is force-dependent at contact onset, a constant bias model under-corrects |", "| never tried on surgical robots |")
    r = run("transfer_scan.py", "check", cwd=research)
    assert r.fails >= 1 and "transfer#T2" in r.out and "不能作为主张来源" in r.out and "失效点" in r.out, r.out
