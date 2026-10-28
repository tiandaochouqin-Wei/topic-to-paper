# -*- coding: utf-8 -*-
"""Independent review (P7 / S6): review_packet.py (make / rereview) and the G7 rules of review_check.py that require fresh-context reviewers,
registered packet hashes, a category on every major, and an independent re-review (same seat, new packet sha) for evidence / validity / novelty / value majors.

The research_min fixture carries an independent log: R0 + R1+R3 + R2 under packet 1a2b3c4d, re-reviews under packet 9f8e7d6c, both registered in
paper/review_packet/round1/ (manifest.json, rereview/manifest.json). Every test below breaks exactly one rule.
"""
import hashlib, json, re, shutil

import pytest
import yaml

from conftest import SKILL, edit, read, run, touch, write

LOG = "paper/review_log.md"
OLD_LOG = """# Review log — round 1 (old style, author-only)

### R1 Methods reviewer
1. [major] The ablation table reports single-run differences; state which cells are within seed noise. → 已改: Section 4.4 now marks two of four cells as not resolvable (Table 2).
2. [minor] Define RMSE at first use. → 已改: expanded in the abstract.

### R2 Domain reviewer
1. [major] Clarify the contact-window convention used for every table. → 已改: Section 4.1 states the window; Table 1 carries it in the caption.
2. [minor] Give reproduction details for baseB. → rebut: the official code is unavailable; the re-implementation is described in Section 4.2.

## Re-review (round 1)
- R1-1 closed: Table 2 and Section 4.4 updated.
- R2-1 closed: convention stated in Section 4.1 and in the Table 1 caption.
"""


def _g6(research):
    assert run("gate_check.py", "all", "--no-net", cwd=research).fails == 0


def _check(research):
    return run("review_check.py", cwd=research)


def _ok(research):
    _g6(research)
    return research


def _state_edit(research, old, new):
    edit(research / "research-state.yaml", old, new)


# ------------------------------------------------------------------ G7: independence
def test_independent_log_passes(research):
    r = _check(_ok(research))
    assert r.fails == 0, r.out
    assert "独立审稿 3 节" in r.out and "都在 manifest.json 里登记" in r.out and "独立审稿评分均值 4.0" in r.out, r.out


def test_no_independent_section_fails(research):
    _ok(research); write(research / LOG, OLD_LOG)
    r = _check(research)
    assert r.fails >= 1 and "没有独立审稿" in r.out, r.out


def test_waiver_turns_missing_independence_into_warn(research):
    _ok(research); write(research / LOG, OLD_LOG)
    _state_edit(research, "open_major: []", 'open_major: []\n  independent_waiver: "no subagent tool in this environment"')
    r = _check(research)
    assert r.fails == 0, r.out
    assert re.search(r"\[WARN\] review: 没有独立审稿节.*no subagent tool in this environment", r.out), r.out


def test_survey_branch_missing_independence_is_only_a_warn(research):
    _ok(research); write(research / LOG, OLD_LOG)
    _state_edit(research, "branch: research", "branch: survey")
    r = _check(research)
    assert r.fails == 0 and "综述分支默认只 WARN" in r.out, r.out


def test_real_reviews_entry_needs_no_independent_section(research):
    _ok(research); write(research / LOG, OLD_LOG)
    _state_edit(research, "entry: topic_only", "entry: have_reviews")
    r = _check(research)
    assert r.fails == 0 and "[INFO] review: entry=have_reviews" in r.out, r.out


def test_missing_r0_fails(research):
    _ok(research)
    s = read(research / LOG); a = s.index("## Reviewer R0"); b = s.index("## Reviewer R1+R3")
    write(research / LOG, s[:a] + s[b:])
    r = _check(research)
    assert r.fails >= 1 and "没有独立的 R0" in r.out, r.out


def test_r0_without_rating_warns(research):
    _ok(research); edit(research / LOG, "rating: 4\n", "")
    r = _check(research)
    assert r.fails == 0 and "独立 R0 节没有 `rating:`" in r.out, r.out


@pytest.mark.parametrize("family,rating,low", [("cs_journal", "2", True), ("cs_journal", "reject", True), ("cs_journal", "major revision", True),
                                               ("cs_journal", "minor revision", False), ("cs_conf", "3", True), ("cs_conf", "4", False),
                                               ("nature", "reject", True), ("nature", "major revision", False)])
def test_low_independent_rating_warns(research, family, rating, low):
    _ok(research)
    _state_edit(research, "family: cs_journal", f"family: {family}")
    edit(research / LOG, "rating: 4\n", f"rating: {rating}\n")
    r = _check(research)
    assert r.fails == 0, r.out
    assert ("独立审稿评分偏低" in r.out) == low, r.out


def test_unregistered_packet_sha_fails(research):
    _ok(research); edit(research / LOG, "## Reviewer R2 (independent, packet 1a2b3c4d)", "## Reviewer R2 (independent, packet deadbeef)")
    r = _check(research)
    assert r.fails >= 1 and "不是在登记的稿件版本上做的" in r.out and "deadbeef" in r.out, r.out


def test_unregistered_rereview_packet_fails(research):
    _ok(research); (research / "paper" / "review_packet" / "round1" / "rereview" / "manifest.json").unlink()
    r = _check(research)
    assert r.fails >= 1 and "不是在登记的稿件版本上做的" in r.out and "9f8e7d6c" in r.out, r.out


# ------------------------------------------------------------------ G7: categories and closure
def test_major_without_category_warns(research):
    _ok(research); edit(research / LOG, "   category: evidence\n", "")
    r = _check(research)
    assert r.fails == 0 and "[WARN] review: 1 条 major 没有 category" in r.out and "R1-1" in r.out, r.out


def test_evidence_major_closed_by_the_author_fails(research):
    """the independent Re-review section is replaced by the author's own: closed in session = not closed"""
    _ok(research); edit(research / LOG, "## Re-review R1+R3 (independent, packet 9f8e7d6c)", "## Re-review (author, round 1)")
    r = _check(research)
    assert r.fails >= 1 and "作者不能自己关闭 evidence 类 major（R1-1）" in r.out, r.out


def test_evidence_major_closed_by_an_inline_arrow_only_fails(research):
    _ok(research); edit(research / LOG, "- R1-1 closed: Table 2 and Section 4.4 updated.\n", "")
    r = _check(research)
    assert r.fails >= 1 and "作者不能自己关闭 evidence 类 major（R1-1）" in r.out, r.out


def test_narrowing_words_are_not_a_closing(research):
    _ok(research)
    edit(research / LOG, "## Re-review R1+R3 (independent, packet 9f8e7d6c)", "## Re-review (author, round 1)")
    edit(research / LOG, "- R1-1 closed: Table 2 and Section 4.4 updated.", "- R1-1 closed: narrowed the claim in Section 3 to the tested scope.")
    r = _check(research)
    assert r.fails >= 1 and "收窄措辞不是关闭" in r.out and "R1-1" in r.out, r.out


def test_independent_rereview_that_accepts_a_narrowing_closes_the_major(research):
    """narrowing is a legitimate fix when the independent re-review, on the revised packet, accepts it"""
    _ok(research)
    edit(research / LOG, "- R1-1 closed: Table 2 and Section 4.4 updated.", "- R1-1 closed: the claim is narrowed to the tested platforms in Section 4.4 and the narrowed paper still reports a usable result.")
    r = _check(research)
    assert r.fails == 0, r.out


def test_rereview_on_the_original_packet_fails(research):
    _ok(research); edit(research / LOG, "## Re-review R1+R3 (independent, packet 9f8e7d6c)", "## Re-review R1+R3 (independent, packet 1a2b3c4d)")
    r = _check(research)
    assert r.fails >= 1 and "同一份 packet" in r.out and "R1-1" in r.out, r.out


def test_rereview_by_another_seat_fails(research):
    _ok(research)
    edit(research / LOG, "## Re-review R1+R3 (independent, packet 9f8e7d6c)", "## Re-review R2 (independent, packet 9f8e7d6c)")
    r = _check(research)
    assert r.fails >= 1 and "R1-1（evidence）被别的席位的复审关闭" in r.out, r.out


def test_clarity_major_may_be_closed_by_the_author(research):
    _ok(research); edit(research / LOG, "- R2-1 closed: convention stated in Section 4.1 and in the Table 1 caption.\n", "")
    r = _check(research)
    assert r.fails == 0, r.out                                           # R2-1 is a clarity major: the arrow closes it (WARN: the re-review never looked at it)
    assert "R2-1" in r.out and "[WARN]" in r.out


@pytest.mark.parametrize("cat", ["validity", "novelty", "value"])
def test_other_strict_categories_need_the_independent_rereview(research, cat):
    _ok(research)
    edit(research / LOG, "   category: evidence", f"   category: {cat}")
    edit(research / LOG, "## Re-review R1+R3 (independent, packet 9f8e7d6c)\n- R1-1 closed: Table 2 and Section 4.4 updated.",
         "## Re-review (author, round 1)\n- R1-1 closed: Table 2 and Section 4.4 updated; results/instruments/backbone_broken.json.")
    r = _check(research)
    assert r.fails >= 1 and f"作者不能自己关闭 {cat} 类 major（R1-1）" in r.out, r.out


def test_validity_closure_without_a_check_file_fails_and_with_one_passes(research):
    _ok(research); edit(research / LOG, "   category: evidence", "   category: validity")
    r = _check(research)
    assert r.fails >= 1 and "validity 类 major 关闭要引用一个在破坏版上会失败的检查输出（R1-1）" in r.out, r.out
    edit(research / LOG, "- R1-1 closed: Table 2 and Section 4.4 updated.", "- R1-1 closed: Table 2 and Section 4.4 updated; the check in results/instruments/backbone_broken.json fails on the broken variant.")
    r = _check(research)
    assert r.fails == 0, r.out


def test_validity_closure_citing_a_file_that_does_not_exist_fails(research):
    _ok(research); edit(research / LOG, "   category: evidence", "   category: validity")
    edit(research / LOG, "- R1-1 closed: Table 2 and Section 4.4 updated.", "- R1-1 closed: see results/instruments/no_such_check.json")
    r = _check(research)
    assert r.fails >= 1 and "validity 类 major" in r.out, r.out


def test_validity_disposition_may_name_the_check_file(research):
    _ok(research); edit(research / LOG, "   category: evidence", "   category: validity")
    edit(research / LOG, "→ 已改: Section 4.4 now marks", "处置: 已改 (broken-variant output results/instruments/backbone_broken.json): Section 4.4 now marks")
    r = _check(research)
    assert r.fails == 0, r.out


def test_waiver_without_any_independent_rereview_degrades_strict_closure_to_warn(research):
    """the author-only flow stays usable when the project cannot run subagents (and says so in state)"""
    _ok(research)
    s = read(research / LOG)
    write(research / LOG, re.sub(r" \(independent, packet [0-9a-f]{8}\)", "", s))
    _state_edit(research, "open_major: []", 'open_major: []\n  independent_waiver: "no subagent tool"')
    r = _check(research)
    assert r.fails == 0, r.out
    assert "[WARN] review: 没有独立审稿节" in r.out and "作者不能自己关闭 evidence 类 major（R1-1）" in r.out, r.out


# ------------------------------------------------------------------ review_packet.py
def _fake_pdf(project, text="%PDF-1.4 fake\n", keep=False):
    """write paper/latex/main.pdf; drops the fixture's registered packets (round1) unless keep=True so `make` starts from round 1"""
    if not keep: shutil.rmtree(project / "paper" / "review_packet", ignore_errors=True)
    p = project / "paper" / "latex" / "main.pdf"; p.write_bytes(text.encode("ascii")); return p


def _manifest(project, rnd=1, sub=""):
    d = project / "paper" / "review_packet" / f"round{rnd}"
    return json.loads(read((d / sub / "manifest.json") if sub else (d / "manifest.json")))


def test_templates_and_forms_exist():
    seats = read(SKILL / "references" / "review-seats.md")
    for name in ("common", "R0", "R1R3", "R2", "DA", "SR1R4", "SR2R3", "rereview"):
        assert re.search(rf"<!-- template: {name} -->\s*```", seats), name
    for fam in ("cs_conf", "cs_journal", "nature"):
        assert (SKILL / "references" / "review-forms" / f"{fam}.md").exists()


def test_make_packet_contents_and_sha(research):
    pdf = _fake_pdf(research)
    r = run("review_packet.py", "make", "--round", 3, cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    d = research / "paper" / "review_packet" / "round3"
    m = _manifest(research, 3)
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert m["sha256"] == sha and m["sha8"] == sha[:8] and m["round"] == 3 and m["kind"] == "pdf"
    assert m["family"] == "cs_journal" and m["venue"].startswith("Engineering Applications") and m["seats"] == ["R0", "R1+R3", "R2", "DA"]
    assert (d / "main.pdf").read_bytes() == pdf.read_bytes() and (d / "form.md").exists()
    assert sorted(p.name for p in (d / "prompts").iterdir()) == ["DA.md", "R0.md", "R1R3.md", "R2.md"]
    for p in (d / "prompts").iterdir():
        t = read(p)
        assert f"## Reviewer " in t and f"(independent, packet {sha[:8]})" in t, p.name
        assert "{" not in t and "}" not in t, f"unfilled placeholder in {p.name}"
        assert "round3" in t and "main.pdf" in t and "form.md" in t
    assert "{venue}" not in read(d / "form.md") and "Engineering Applications of Artificial Intelligence" in read(d / "form.md")
    assert sha[:8] in r.out and "全新上下文的子代理" in r.out


@pytest.mark.parametrize("family,needle", [("cs_conf", "Strong reject"), ("cs_journal", "major revision"), ("nature", "Key results")])
def test_form_follows_the_family(research, family, needle):
    _fake_pdf(research); _state_edit(research, "family: cs_journal", f"family: {family}")
    assert run("review_packet.py", "make", cwd=research).returncode == 0
    f = read(research / "paper" / "review_packet" / "round1" / "form.md")
    assert needle in f
    assert _manifest(research)["family"] == family


def test_family_inferred_from_the_venue_when_not_set(research):
    _fake_pdf(research); _state_edit(research, "  family: cs_journal\n", ""); _state_edit(research, 'venue: "Engineering Applications of Artificial Intelligence"', 'venue: "CVPR 2027"')
    assert run("review_packet.py", "make", cwd=research).returncode == 0
    assert _manifest(research)["family"] == "cs_conf"


def test_prompts_carry_no_author_material(research):
    """the whole point: no prereg, claims, gap_map or notes text reaches the reviewer"""
    _fake_pdf(research)
    assert run("review_packet.py", "make", cwd=research).returncode == 0
    prompts = "\n".join(read(p) for p in (research / "paper" / "review_packet" / "round1" / "prompts").iterdir())
    secrets = []
    for rel in ("prereg.md", "paper/claims.csv", "literature/gap_map.md"):
        for ln in read(research / rel).splitlines():
            ln = ln.strip().strip("|# ").strip()
            if len(ln) >= 25: secrets.append(ln)
    secrets += ["a domain-adversarial regularizer removes the platform-specific sensor offset", "contact-window: |F| >= 0.1 N"]
    assert secrets, "fixture has no author text to check against"
    leaked = [s for s in secrets if s in prompts]
    assert not leaked, leaked[:3]
    for p in (research / "paper" / "review_packet" / "round1" / "prompts").iterdir():
        t = read(p).lower()
        if p.name == "R1R3.md": assert "prereg.md" in t and "do not open prereg.md, claims.csv" in t      # named only in the prohibition
        else: assert "prereg" not in t and "claims.csv" not in t, p.name


def test_seat_prompts_have_the_seat_specific_parts(research):
    _fake_pdf(research); run("review_packet.py", "make", cwd=research)
    d = research / "paper" / "review_packet" / "round1" / "prompts"
    r0, r2, da, pair = (read(d / f) for f in ("R0.md", "R2.md", "DA.md", "R1R3.md"))
    assert "Engineering Applications of Artificial Intelligence" in r0 and "唯一主张" in r0 and "rating" in r0 and "Single change that would most raise the rating" in r0
    assert "closest three prior works" in r2 and "category novelty" in r2
    assert "1-3 items only" in da and "How to refute me" in da
    assert "blind read" in pair and "/results" in pair and "### R1 methodology" in pair and "### R3 reproducibility" in pair


def test_manuscript_mode_copies_the_manuscript_and_figures(research):
    shutil.rmtree(research / "paper" / "review_packet")
    r = run("review_packet.py", "make", "--manuscript", "paper/manuscript.md", cwd=research)
    assert r.returncode == 0, r.out
    d = research / "paper" / "review_packet" / "round1"; m = _manifest(research)
    assert m["kind"] == "manuscript" and (d / "manuscript.md").exists() and (d / "figures" / "fig_main.pdf").exists()
    assert m["sha256"] == hashlib.sha256((research / "paper" / "manuscript.md").read_bytes()).hexdigest()
    assert "figures" in read(d / "prompts" / "R0.md")


def test_default_source_is_the_pdf_else_the_manuscript(research):
    shutil.rmtree(research / "paper" / "review_packet")
    assert run("review_packet.py", "make", cwd=research).returncode == 0 and _manifest(research)["kind"] == "manuscript"
    _fake_pdf(research, keep=True)
    assert run("review_packet.py", "make", "--round", 2, cwd=research).returncode == 0 and _manifest(research, 2)["kind"] == "pdf"


def test_missing_source_fails_cleanly(research):
    r = run("review_packet.py", "make", "--pdf", "paper/latex/nope.pdf", cwd=research)
    assert r.returncode == 1 and "稿件不存在" in r.out and not r.crashed


def test_registered_round_is_not_overwritten_and_next_round_increments(research):
    _fake_pdf(research); assert run("review_packet.py", "make", "--round", 4, cwd=research).returncode == 0
    r = run("review_packet.py", "make", "--round", 4, cwd=research)
    assert r.returncode == 1 and "已存在" in r.out
    assert run("review_packet.py", "make", "--round", 4, "--force", cwd=research).returncode == 0
    assert run("review_packet.py", "make", cwd=research).returncode == 0
    assert (research / "paper" / "review_packet" / "round5" / "manifest.json").exists()


def test_survey_branch_gets_survey_seats(research):
    _fake_pdf(research); _state_edit(research, "branch: research", "branch: survey")
    r = run("review_packet.py", "make", cwd=research)
    assert r.returncode == 0, r.out
    d = research / "paper" / "review_packet" / "round1"
    assert sorted(p.name for p in (d / "prompts").iterdir()) == ["DA.md", "SR1R4.md", "SR2R3.md"]
    assert "survey" in read(d / "prompts" / "SR1R4.md") and "R4 (读者视角)" in read(d / "prompts" / "SR1R4.md")
    assert _manifest(research)["seats"] == ["R1+R4", "R2+R3", "DA"]


def test_packet_hash_is_what_review_check_registers(research):
    """make -> paste the real sha8 into the log headings -> G7 accepts it (the fixture's own round1 still registers the re-review packet)"""
    _ok(research); _fake_pdf(research, keep=True)
    assert run("review_packet.py", "make", "--round", 9, cwd=research).returncode == 0
    sha8 = _manifest(research, 9)["sha8"]
    write(research / LOG, read(research / LOG).replace("1a2b3c4d", sha8))
    r = _check(research)
    assert r.fails == 0 and "都在 manifest.json 里登记" in r.out, r.out
    write(research / LOG, read(research / LOG).replace(sha8, "0badc0de"))
    assert "不是在登记的稿件版本上做的" in _check(research).out
    assert run("review_packet.py", "rereview", "--round", 9, "--items", "R1-1", cwd=research).returncode == 1       # the PDF is unchanged: nothing to re-review


def test_rereview_prompts_carry_item_and_disposition(research):
    _fake_pdf(research, "%PDF-1.4 v1\n"); assert run("review_packet.py", "make", cwd=research).returncode == 0
    orig = _manifest(research)["sha8"]
    _fake_pdf(research, "%PDF-1.4 v2 revised\n", keep=True)
    r = run("review_packet.py", "rereview", "--round", 1, "--items", "R1-1,R2-1", cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    d = research / "paper" / "review_packet" / "round1" / "rereview"; m = _manifest(research, 1, "rereview")
    assert m["sha8"] != orig and m["original_sha8"] == orig and m["items"] == ["R1-1", "R2-1"]
    assert sorted(p.name for p in (d / "prompts").iterdir()) == ["R1-1.md", "R2-1.md"]
    t = read(d / "prompts" / "R1-1.md")
    assert "The ablation table reports single-run differences" in t                               # the original item
    assert "→ 已改: Section 4.4 now marks two of four cells as not resolvable (Table 2)." in t       # the author's disposition
    assert f"## Re-review R1 (independent, packet {m['sha8']})" in t and "R1-1 OPEN" in t
    assert "{" not in t
    assert "Clarify the contact-window convention" not in t                                      # nothing about the other items
    assert (d / "main.pdf").read_bytes() == b"%PDF-1.4 v2 revised\n"
    assert m["sha8"] in r.out


def test_rereview_with_an_unknown_item_or_missing_round_fails(research):
    _fake_pdf(research, "%PDF-1.4 v1\n"); run("review_packet.py", "make", cwd=research); _fake_pdf(research, "%PDF-1.4 v2\n", keep=True)
    r = run("review_packet.py", "rereview", "--round", 1, "--items", "R9-9", cwd=research)
    assert r.returncode == 1 and "找不到意见" in r.out
    r = run("review_packet.py", "rereview", "--round", 7, "--items", "R1-1", cwd=research)
    assert r.returncode == 1 and "先 make" in r.out
    r = run("review_packet.py", "rereview", "--round", 1, cwd=research)
    assert r.returncode == 1 and "--items" in r.out


def test_rereview_warns_when_the_item_has_no_disposition(research):
    _fake_pdf(research, "%PDF-1.4 v1\n"); run("review_packet.py", "make", cwd=research); _fake_pdf(research, "%PDF-1.4 v2\n", keep=True)
    edit(research / LOG, "→ 已改: Section 4.4 now marks two of four cells as not resolvable (Table 2).", "")
    r = run("review_packet.py", "rereview", "--round", 1, "--items", "R1-1", cwd=research)
    assert r.returncode == 0 and "[WARN] packet: R1-1" in r.out and "no disposition recorded" in read(research / "paper" / "review_packet" / "round1" / "rereview" / "prompts" / "R1-1.md"), r.out
