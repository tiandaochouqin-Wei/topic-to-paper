# -*- coding: utf-8 -*-
"""G6g — argument-first writing (argument_check.py, templates/argument.md) and the draft_plan changes that go with it (2026-10-28).

Evidence (three real CVPR drafts, 2026-10-23): checklist-driven intros of 1000+ words that name every prior paper, contribution bullets with 4-14 numbers,
and nothing that asked for ONE claim sentence shared by title, abstract, end of the Introduction and Conclusion. Mutations act on the research_min fixture,
whose paper/argument.md is satisfied by its manuscript."""
import json
import re

import pytest

from conftest import SKILL, edit, read, run, write

ABS_SENT = r"On the held-out platform the proposed model lowers.*?single-run precision\."
INTRO_P2 = r"We observe the phenomenon directly:.*?strongest baseline\.(?=\n\n)"
CONCL = r"(## 5\. Conclusion\n).*?(?=\n\n## References)"
UNRELATED = "The weather in March was mild and the committee met on Tuesday to discuss the budget for the library extension."


def _ms(p): return p / "paper" / "manuscript.md"
def _arg(p): return p / "paper" / "argument.md"


def _sub(path, pat, repl, flags=re.S | re.M):
    s = read(path); s2, n = re.subn(pat, repl, s, count=1, flags=flags)
    assert n == 1, f"{pat!r} not found in {path}"
    write(path, s2)


def _set(p, key, value):
    """replace a one-line `key: …` field of argument.md"""
    _sub(_arg(p), r"^" + re.escape(key) + r":.*$", lambda m: f"{key}: {value}", re.M)


def _chk(p, *args):
    return run("argument_check.py", *args, cwd=p)


def _fail(r, needle):
    assert r.fails >= 1 and needle in r.out, r.out


def _warn(r, needle):
    assert r.fails == 0 and re.search(r"\[WARN\] argument: [^\n]*" + re.escape(needle), r.out), r.out


# ------------------------------------------------------------------ pass / argument.md itself
def test_g6g_pass(research):
    r = _chk(research)
    assert r.fails == 0 and "ALL PASS" in r.out and "[WARN]" not in r.out and not r.crashed, r.out
    for needle in ("主张在摘要里出现", "引言末段", "Conclusion 前两句", "headline.claim_id C1", "reader_question", "引言段落按提纲的顺序走"):
        assert needle in r.out, needle


def test_g6g_missing_argument_md_fails(research):
    _arg(research).unlink()
    r = _chk(research)
    _fail(r, "先写论点再写稿"); assert "templates/argument.md" in r.out


def test_g6g_template_copy_fails_per_field(research):
    write(_arg(research), read(SKILL / "templates" / "argument.md"))
    r = _chk(research)
    for key in ("claim", "reader_question", "why_not_obvious", "strongest_objection", "headline", "outline"):
        assert re.search(r"\[FAIL\] argument: " + key + r"\b", r.out), (key, r.out)
    assert r.fails >= 6


@pytest.mark.parametrize("key,empty", [("claim", '""'), ("reader_question", '""'), ("why_not_obvious", '"<what the field assumes>"'), ("strongest_objection", '""'),
                                       ("headline", "{claim_id: C1, number: \"\"}")])
def test_g6g_each_required_field(research, key, empty):
    _set(research, key, empty)
    _fail(_chk(research), f"[FAIL] argument: {key}" if key != "headline" else "[FAIL] argument: headline")


def test_g6g_empty_outline(research):
    edit(_arg(research), 'outline:\n  - "context:', 'outline: []\nold_outline:\n  - "context:')
    _fail(_chk(research), "[FAIL] argument: outline")


def test_g6g_unquoted_outline_entries_still_parse(research):
    """`- context: why …` without quotes is a YAML one-key mapping; the loader folds it back into "context: why …"."""
    s = read(_arg(research)); s = re.sub(r'^  - "(\w+: )(.*)"$', r"  - \1\2", s, flags=re.M); write(_arg(research), s)
    r = _chk(research)
    assert r.fails == 0 and "引言段落按提纲的顺序走" in r.out, r.out


def test_g6g_broken_yaml_fails_cleanly(research):
    write(_arg(research), "---\nclaim: [unterminated\n---\n")
    r = _chk(research)
    _fail(r, "YAML"); assert not r.crashed


# ------------------------------------------------------------------ claim shape
def _has_warn(r, needle):
    assert re.search(r"\[WARN\] argument: [^\n]*" + re.escape(needle), r.out), r.out


def test_g6g_claim_too_long_warns(research):
    _set(research, "claim", '"' + " ".join(["Cross-platform degradation of vision-based force estimation is dominated by a label-side sensor offset"] * 4) + '"')
    _has_warn(_chk(research), "上限 35 词")


def test_g6g_claim_with_three_numbers_warns(research):
    _set(research, "claim", '"Cross-platform degradation of force estimation is dominated by a sensor offset; the regularizer lowers held-out RMSE by 19.2% on 2 platforms over 3 seeds."')
    _has_warn(_chk(research), "3 个数字")


def test_g6g_claim_without_a_falsifiable_verb_warns(research):
    _set(research, "claim", '"Cross-platform vision-based force estimation, the label-side sensor offset, and the domain-adversarial regularizer: held-out RMSE 19.2% against the strongest baseline."')
    _warn(_chk(research), "没有可证伪的动词")


# ------------------------------------------------------------------ the claim recurs in title / abstract / Introduction / Conclusion
def test_g6g_claim_missing_in_abstract(research):
    _sub(_ms(research), ABS_SENT, "Results are reported on two platforms.")
    _sub(_ms(research), r"(We propose a domain-adversarial regularizer).*?(?=Results are reported)", r"We propose a method and evaluate it. ")
    _fail(_chk(research), "主张没有在摘要里出现")


def test_g6g_claim_missing_in_last_intro_paragraph(research):
    _sub(_ms(research), INTRO_P2, UNRELATED)
    _fail(_chk(research), "主张没有在引言最后一段")


def test_g6g_claim_missing_in_conclusion(research):
    _sub(_ms(research), CONCL, r"\1Several questions remain open for the community. The code is released with the paper.")
    _fail(_chk(research), "主张没有在Conclusion 前两句出现")


def test_g6g_claim_recurs_through_its_numbers_only_with_some_shared_words(research):
    """every number of the claim in a sentence is enough only when the sentence also shares >= 25 % of the claim's words: a stray 19.2 does not count"""
    _sub(_ms(research), CONCL, r"\1The audit log lists 19.2 entries. The code is released with the paper.")
    _fail(_chk(research), "主张没有在Conclusion 前两句出现")


def test_g6g_title_far_from_the_claim_warns(research):
    edit(_ms(research), "# Domain-robust vision-based force estimation by removing the platform sensor offset", "# A study of robots")
    _warn(_chk(research), "标题与 claim 共享")


def test_g6g_nature_wants_a_here_we_show_sentence(research):
    r = _chk(research, "--family", "nature")
    _fail(r, "没有 'Here we show")
    edit(_ms(research), "strongest baseline.\n\nThe contributions", "strongest baseline. Here we show that cross-platform degradation of vision-based force estimation is dominated by a label-side sensor offset, and that removing it with a domain-adversarial regularizer lowers held-out RMSE by 19.2% against the strongest baseline.\n\nThe contributions")
    r = _chk(research, "--family", "nature")
    assert "主张在 'Here we show' 句里出现" in r.out, r.out


# ------------------------------------------------------------------ headline
def test_g6g_headline_claim_id_not_in_claims_csv(research):
    _set(research, "headline", '{claim_id: C9, number: "19.2%"}')
    _fail(_chk(research), "不在 paper/claims.csv")


def test_g6g_headline_number_not_in_abstract(research):
    _set(research, "headline", '{claim_id: C1, number: "19.5%"}')
    _fail(_chk(research), "不在摘要里")


def test_g6g_headline_number_missing_in_introduction_warns(research):
    edit(_ms(research), "19.2% against the strongest baseline.", "against the strongest baseline.")
    edit(_ms(research), "by 19.2% relative to the strongest baseline (baseA)", "relative to the strongest baseline (baseA)")
    _warn(_chk(research), "不在引言里")


def test_g6g_rounding_drift_between_abstract_and_introduction_warns(research):
    """6.95 in one place and 7.0 in another (here 19.2 vs 19.0)"""
    edit(_ms(research), "lowers the held-out RMSE by 19.2% against", "lowers the held-out RMSE by 19.0% against")
    edit(_ms(research), "platform by 19.2% relative to the strongest baseline (baseA)", "platform by 19.0% relative to the strongest baseline (baseA)")
    _warn(_chk(research), "取整不一致")


# ------------------------------------------------------------------ reader question, prior belief, objection
def test_g6g_reader_question_not_posed_in_first_two_paragraphs(research):
    _set(research, "reader_question", '"How should hospitals schedule night shifts for nursing staff?"')
    _warn(_chk(research), "引言前两段没有提出读者的问题")


def test_g6g_prior_belief_not_in_introduction(research):
    _set(research, "why_not_obvious", '"Everyone believes that larger language models always write better poetry."')
    _warn(_chk(research), "引言没有讲清读者为什么本来不会信")


def test_g6g_where_answered_points_nowhere(research):
    _set(research, "where_answered", '"§9.9 and Table 7"')
    _warn(_chk(research), "不存在的位置")


def test_g6g_where_answered_names_no_location(research):
    _set(research, "where_answered", '"somewhere in the paper"')
    _warn(_chk(research), "没有写出 § / Table / Fig 编号")


def test_g6g_objection_not_answered_warns(research):
    _set(research, "strongest_objection", '"The proprietary vendor firmware may silently rewrite timestamps during export of telemetry."')
    _warn(_chk(research), "没有回应论点自己写下的最强反对意见")


# ------------------------------------------------------------------ outline vs Introduction
def test_g6g_outline_paragraph_count_differs_by_more_than_one(research):
    edit(_arg(research), '  - "contributions"', '  - "belief: methods assume a shared sensor calibration"\n  - "this paper: we remove the offset"\n  - "contributions"')
    _warn(_chk(research), "段数差 > 1")


def test_g6g_introduction_does_not_follow_the_outline(research):
    edit(_arg(research), '  - "gap: GeoNet and ForceFormer inherit the platform offset, and visual domain adaptation never tested the label-side assumption"',
         '  - "gap: quantum annealers amplify thermal fluctuations in cryogenic superconducting circuits"')
    _warn(_chk(research), "引言第 2 段没有按提纲走：gap")


def test_g6g_outline_order_inverted(research):
    s = read(_arg(research))
    ctx = re.search(r'^  - "context:.*$', s, re.M).group(0); fin = re.search(r'^  - "finding:.*$', s, re.M).group(0)
    write(_arg(research), s.replace(ctx, "@@C").replace(fin, ctx).replace("@@C", fin))
    _warn(_chk(research), "顺序与提纲不一致")


def test_g6g_not_claimed_missing_from_limitations_warns(research):
    edit(_arg(research), '  - "a third platform remains future validation"', '  - "no claim about quantum annealers in cryogenic superconducting circuits"')
    _warn(_chk(research), "not_claimed 有 1 条没有在")


# ------------------------------------------------------------------ the board
def test_g6g_on_the_board(research):
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[PASS] G6g:" in r.out, r.out
    assert "[FAIL]" not in r.out and "[CRASH]" not in r.out, r.out


def test_g6g_manuscript_without_argument_md_fails_on_the_board(research):
    _arg(research).unlink()
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[FAIL] G6g:" in r.out, r.out


def test_g6g_pending_before_the_manuscript_exists(research):
    _arg(research).unlink(); _ms(research).unlink()
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[PENDING] G6g:" in r.out and "argument.md" in r.out, r.out


def test_g6g_not_on_the_survey_board(survey):
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=survey)
    assert "G6g" not in r.out, r.out


def test_g6g_in_gate_order_after_g6f():
    s = read(SKILL / "scripts" / "t2p.py")
    order = re.search(r"GATE_ORDER = \[(.*?)\]", s).group(1)
    assert '"G6f", "G6g", "G7"' in order


def test_argument_template_parses_and_is_all_placeholders():
    import sys
    sys.path.insert(0, str(SKILL / "scripts"))
    import draft_plan as dp
    d = dp.load_argument(str(SKILL / "templates" / "argument.md"))
    for key in ("claim", "reader_question", "why_not_obvious", "strongest_objection", "headline", "outline", "where_answered", "not_claimed", "sections"):
        assert key in d and dp.is_placeholder(d[key]), key
    assert any(x.startswith("contributions") for x in d["outline"])


# ------------------------------------------------------------------ draft_plan: relaxed prior-work items, headline-only number, argument items
def _plan(p):
    assert run("draft_plan.py", "plan", "--project", ".", cwd=p).returncode == 0


def _items(p):
    return json.loads(read(p / "paper" / "draft_plan.json"))


def test_plan_prior_work_items_are_warn_and_accept_related_work(research):
    _plan(research)
    it = [i for i in _items(research) if i["source"] == "gap_map 失效点：GeoNet"][0]
    assert it["level"] == "WARN" and it["kind"] == "name" and it["probe"] == "GeoNet" and "related" in it["also"], it
    edit(_ms(research), "GeoNet", "Alpha")                                           # named nowhere
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert re.search(r"\[WARN\] INT\d+ intro: 缺 —— 相关工作（按主题成段）或引言里点名 GeoNet", r.out), r.out
    edit(_ms(research), "Early systems regress force from geometric cues", "GeoNet and early systems regress force from geometric cues")      # named in Related Work instead
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert re.search(r"\[PASS\] INT\d+ intro: 相关工作（按主题成段）或引言里点名 GeoNet", r.out), r.out


def test_plan_intro_paragraph_with_more_than_six_references_warns(research):
    _plan(research)
    edit(_ms(research), "in the operating room [2].", "in the operating room [2][3][4][5][6][7][8].")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert re.search(r"\[WARN\] INT\d+ intro: 缺 —— 引言每段至多引 6 篇", r.out), r.out
    edit(_ms(research), "[2][3][4][5][6][7][8]", "[2][3][4][5][6][7]")                 # 6 distinct references are fine
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert any(l.startswith("[PASS]") and "引言每段至多引 6 篇" in l for l in r.out.splitlines()), r.out


def test_plan_citation_ranges_and_author_year_count_as_distinct_references():
    import sys
    sys.path.insert(0, str(SKILL / "scripts"))
    import draft_plan as dp
    assert len(dp.distinct_refs("see [1-4] and [6, 9] and (Smith et al., 2020) and Lee 2021 and \\cite{a,b}")) == 4 + 2 + 1 + 1 + 2


def test_plan_contribution_number_item_only_for_the_headline_claim(research):
    _plan(research)
    intro_claims = [i["source"] for i in _items(research) if i["section"] == "intro" and i["source"].startswith("claims ")]
    assert "claims C1" in intro_claims and not {"claims C2", "claims C3", "claims C4"} & set(intro_claims), intro_claims
    c1 = [i for i in _items(research) if i["source"] == "claims C1"][0]
    assert c1["kind"] == "numbers" and c1["probe"] == "19.2" and c1["level"] == "FAIL"
    assert any(i["source"].startswith("claims C2 @") for i in _items(research))       # the same claim's number is still demanded in Results


def test_plan_headline_follows_argument_md(research):
    _set(research, "headline", '{claim_id: C2, number: "two seed standard deviations"}')
    _plan(research)
    intro_claims = [i["source"] for i in _items(research) if i["section"] == "intro" and i["source"].startswith("claims ")]
    assert "claims C2" in intro_claims and "claims C1" not in intro_claims, intro_claims


def test_plan_headline_without_argument_md_is_the_first_claim_with_a_number(research):
    _arg(research).unlink()
    _plan(research)
    intro_claims = [i["source"] for i in _items(research) if i["section"] == "intro" and i["source"].startswith("claims ")]
    assert "claims C1" in intro_claims and "claims C2" not in intro_claims, intro_claims
    assert not any(i["source"].startswith("argument.md") for i in _items(research))


def test_plan_claim_without_table_or_figure_is_a_warn_in_the_introduction(research):
    _plan(research)
    c0 = [i for i in _items(research) if i["source"] == "claims C0"][0]
    assert c0["section"] == "intro" and c0["level"] == "WARN", c0


def test_plan_argument_items_and_their_check(research):
    _plan(research)
    items = {i["source"]: i for i in _items(research)}
    assert items["argument.md claim"]["kind"] == "para_last" and items["argument.md claim"]["level"] == "FAIL"
    assert items["argument.md reader_question"]["kind"] == "para_first2" and items["argument.md reader_question"]["level"] == "WARN"
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails == 0 and "论点句" in r.out, r.out
    _sub(_ms(research), INTRO_P2, UNRELATED)
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert re.search(r"\[FAIL\] INT\d+ intro: 缺 —— 引言最后一段（贡献列表之前）要出现论点句", r.out), r.out
    assert re.search(r"\[WARN\] INT\d+ intro: 缺 —— 引言前两段要提出读者的问题", r.out) or "读者的问题" in r.out


def test_plan_has_no_argument_items_while_argument_md_is_still_the_template(research):
    write(_arg(research), read(SKILL / "templates" / "argument.md"))
    _plan(research)
    assert not any(i["source"].startswith("argument.md") for i in _items(research))
