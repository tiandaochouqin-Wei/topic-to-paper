# -*- coding: utf-8 -*-
"""G6e — the claim layer (claims_check.py, 2026-10-11): every headline sentence is a claims.csv row and every row is computed
from the result files. On the untouched fixture: 3 quantitative rows PASS, 2 qualitative rows WARN, ALL PASS."""
from conftest import edit, lock, read, run, write


def _claims(research):
    return research / "paper" / "claims.csv"


def test_g6e_pass(research):
    r = run("claims_check.py", cwd=research)
    assert r.fails == 0 and "rel:rmse_E1:ours:baseA" in r.out and "z:rmse_E1:no_dom" in r.out, r.out


def test_g6e_claim_contradicted_by_results(research):
    """statement says 19.2 % but results say less: expected no longer holds"""
    edit(_claims(research), "-19.2±0.15", "-25±0.15")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "C1" in r.out and "不成立" in r.out, r.out


def test_g6e_unresolvable_cell_claimed_as_effect(research):
    edit(_claims(research), "z:rmse_E1:no_cons,<2", "z:rmse_E1:no_cons,>=2")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "C3" in r.out and "不成立" in r.out, r.out


def test_g6e_evidence_key_without_expected(research):
    edit(_claims(research), "rel:rmse_E1:ours:baseA,-19.2±0.15", "rel:rmse_E1:ours:baseA,")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "无 expected" in r.out, r.out


def test_g6e_number_in_claim_not_in_manuscript(research):
    edit(_claims(research), "by 19.2% relative", "by 19.4% relative")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "19.4" in r.out and "不在正文" in r.out, r.out


def test_g6e_contribution_bullet_without_claim_row(research):
    edit(research / "paper" / "manuscript.md", "- An ablation protocol with explicit seed-noise resolution",
         "- A new benchmark of surgical clips released with the paper, and an ablation protocol with explicit seed-noise resolution")
    p = _claims(research); write(p, "\n".join(l for l in read(p).splitlines() if not l.startswith("C4,")) + "\n")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "贡献条目 3" in r.out and "没有对应行" in r.out, r.out


def test_g6e_strong_scope_sentence_needs_scope_words(research):
    m = research / "paper" / "manuscript.md"
    edit(m, "the ordering is the same on both platforms and the seed standard deviations do not overlap.",
         "the ordering is the same on both platforms and the seed standard deviations do not overlap. Our model outperforms all existing force regressors on the held-out platform.")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "outperforms all" in r.out and ("没有 claims 行" in r.out or "scope_words 为空" in r.out), r.out
    # register it with scope words -> PASS
    write(_claims(research), read(_claims(research)) + 'C5,"ours outperforms all existing force regressors (baseA, baseB) on the held-out platform E1",E1,contact-window,results/main.csv,rel:rmse_E1:ours:baseA,<0,Table 1,"all existing = the two preregistered baselines on E1 contact-window; Table 1",yes\n')
    r = run("claims_check.py", cwd=research)
    assert r.fails == 0 and "C5" in r.out and "scope_words" in r.out, r.out


def test_g6e_claim_stated_in_wrong_section(research):
    edit(_claims(research), "z:rmse_E1:no_dom,>=2,Table 2", "z:rmse_E1:no_dom,>=2,Table 1")
    r = run("claims_check.py", cwd=research)
    assert r.fails >= 1 and "C2" in r.out and "所在节没有陈述" in r.out, r.out


def test_g6e_nature_here_we_show_must_be_a_claim(research):
    m = research / "paper" / "manuscript.md"
    edit(m, "The remainder of the paper reviews related work", "Here we show that a wavelength-conditioned encoder transfers to unseen satellites. The remainder of the paper reviews related work")
    r = run("claims_check.py", "--family", "nature", cwd=research)
    assert r.fails >= 1 and "Here we show" in r.out and "没有对应行" in r.out, r.out


def test_g6e_below_prereg_minimum_warns(research):
    edit(research / "prereg.md", "at least 5 % relative to the strongest baseline", "at least 25 % relative to the strongest baseline")
    lock(research, "prereg.md", "prereg_sha256")
    r = run("claims_check.py", cwd=research)
    assert r.fails == 0 and "低于 prereg §7" in r.out, r.out


def test_g6e_on_the_board(research):
    assert run("draft_plan.py", "plan", "--project", ".", cwd=research).returncode == 0
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[PASS] G6e:" in r.out, r.out
