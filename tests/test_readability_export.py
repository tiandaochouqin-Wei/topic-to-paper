# -*- coding: utf-8 -*-
"""G6f readability + export bugs (2026-10-23): tex_to_md \\paragraph -> "agraph{", leftover markers, raw bibkeys in the reference list, ablation-resolve in captions."""
import re

from conftest import edit, read, run, touch, write


def touch_ms(project):
    """keep paper/manuscript.md newer than the .tex sources after a test edits them (G6d freshness rule)"""
    touch(project / "paper" / "manuscript.md", +5)


# ------------------------------------------------------------------ tex_to_md
def _convert(tmp_path, tex, bib=None):
    write(tmp_path / "main.tex", "\\documentclass{article}\n\\begin{document}\n" + tex + "\n\\end{document}\n")
    args = ["main.tex", "out"] + (["--bib", "refs.bib"] if bib else [])
    if bib: write(tmp_path / "refs.bib", bib)
    r = run("tex_to_md.py", *args, cwd=tmp_path)
    assert not r.crashed, r.out
    return read(tmp_path / "out" / "paper" / "manuscript.md")


def test_paragraph_is_run_in_head_not_agraph(tmp_path):
    md = _convert(tmp_path, "\\section{Intro}\n\\paragraph{Setup.} Text here.\n\\subparagraph{Detail} More text.")
    assert "agraph{" not in md and "ubagraph" not in md, md
    assert "**Setup.** Text here." in md and "**Detail** More text." in md, md


def test_par_parbox_partial_keep_their_text(tmp_path):
    md = _convert(tmp_path, "\\section{A}\nFirst.\\par Second \\parbox{3cm}{boxed words} and $\\partial x$ and \\parskip.")
    assert "boxed words" in md and "\\partial x" in md, md          # \partial inside math is not "\par" + "tial"
    assert "tial x" not in md.replace("\\partial x", "") and "box{" not in md, md
    assert re.search(r"First\.\s*\n\s*\n\s*Second", md), md           # \par became a paragraph break


def test_section_title_with_nested_macro(tmp_path):
    md = _convert(tmp_path, "\\section{Learning \\textbf{fast}}\nBody.\n\\subsection*{Sub \\emph{x}}\nMore.")
    assert "## Learning fast" in md and "### Sub x" in md and "}" not in md.split("## References")[0].replace("{", ""), md


def test_single_line_bib_entry_gets_its_title_not_the_key(tmp_path):
    bib = "@inproceedings{llvip21, title={LLVIP: A Visible-infrared Paired Dataset}, url={http://x.org/1}, year={2021}}\n"
    md = _convert(tmp_path, "\\section{Intro}\nSee \\cite{llvip21}.", bib)
    assert "[1] LLVIP: A Visible-infrared Paired Dataset (bibkey llvip21)" in md, md


# ------------------------------------------------------------------ leftover markers: G6d (LaTeX sources) and G6 / G8 (text)
def _main(project):
    return project / "paper" / "latex" / "main.tex"


def _ms(project):
    return project / "paper" / "manuscript.md"


def test_latex_pass_has_no_marker_fail(research):
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails == 0 and "没有残留" in r.out, r.out


def test_todo_command_in_source_fails(research):
    edit(_main(research), "\\section{Introduction}\n", "\\section{Introduction}\n\\todo{cite Smith here}\n")
    touch_ms(research)
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "批注命令" in r.out, r.out


def test_commented_out_todo_is_fine(research):
    edit(_main(research), "\\section{Introduction}\n", "\\section{Introduction}\n% \\todo{cite Smith here}\n")
    touch_ms(research)
    assert run("latex_check.py", "check", cwd=research).fails == 0


def test_todonotes_without_disable_fails(research):
    edit(_main(research), "\\usepackage{booktabs}\n", "\\usepackage{booktabs}\n\\usepackage{todonotes}\n")
    touch_ms(research)
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "todonotes" in r.out, r.out
    edit(_main(research), "\\usepackage{todonotes}", "\\usepackage[disable]{todonotes}")
    touch_ms(research)
    assert run("latex_check.py", "check", cwd=research).fails == 0


def test_blg_missing_database_entry_fails(research):
    write(research / "paper" / "latex" / "main.blg", "Warning--I didn't find a database entry for \"llvip21\"\n")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "llvip21" in r.out and "main.blg" in r.out, r.out


def test_log_undefined_citation_fails(research):
    write(research / "paper" / "latex" / "main.log", "Package natbib Warning: Citation `tardal22' on page 2 undefined on input line 5.\n")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "tardal22" in r.out, r.out


def test_stale_log_is_not_trusted(research):
    p = research / "paper" / "latex" / "main.log"
    write(p, "LaTeX Warning: Citation `old' on page 1 undefined on input line 4.\n")
    touch(p, -3600)
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails == 0 and "比 .tex 源旧" in r.out, r.out


def test_bbl_item_that_is_only_the_key_fails(research):
    write(research / "paper" / "latex" / "main.bbl", "\\begin{thebibliography}{2}\n\\bibitem[A(2020)]{good20}\nA. Author.\n\\newblock A real title.\n\n\\bibitem{llvip21}\nllvip21\n\n\\end{thebibliography}\n")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "llvip21" in r.out and "good20" not in r.out.split("main.bbl")[-1], r.out


def test_markers_pass_on_fixture(research):
    r = run("gate_check.py", "limits", "--no-net", cwd=research)
    assert r.fails == 0, r.out


def test_todo_text_in_manuscript_fails(research):
    for bad in ("TODO: cite", "FIXME", "XXX", "[待补充]", "[TBD]", "see Fig. ??", "\\todo{x}"):
        p = _ms(research); s0 = read(p)
        write(p, s0.replace("## 5. Conclusion\n", "## 5. Conclusion\n" + bad + "\n"))
        r = run("gate_check.py", "limits", cwd=research)
        assert r.fails >= 1 and "markers" in r.out, (bad, r.out)
        write(p, s0)


def test_marker_inside_math_or_code_is_ignored(research):
    p = _ms(research); write(p, read(p).replace("## 5. Conclusion\n", "## 5. Conclusion\n$a\\to ??$ and `TODO`\n\n```\nTODO\n```\n"))
    assert run("gate_check.py", "limits", cwd=research).fails == 0


def test_raw_bibkey_reference_line_fails(research):
    edit(_ms(research), "[1] K. He, X. Zhang, S. Ren, J. Sun, Deep residual learning for image recognition, CVPR 2016.", "[1] he2016resnet (bibkey he2016resnet)")
    r = run("gate_check.py", "limits", cwd=research)
    assert r.fails >= 1 and "参考文献条目只有键" in r.out, r.out


def test_resolved_bibkey_line_is_fine(research):
    edit(_ms(research), "[1] K. He, X. Zhang, S. Ren, J. Sun, Deep residual learning for image recognition, CVPR 2016.", "[1] Deep residual learning for image recognition (bibkey he2016resnet)")
    assert run("gate_check.py", "limits", cwd=research).fails == 0


def test_submission_files_are_scanned_for_markers(research):
    r0 = run("gate_check.py", "submission", cwd=research)
    assert r0.fails == 0, r0.out
    for name in ("cover_letter.md", "blind.md"):
        p = research / "submission" / name; s0 = read(p)
        write(p, s0 + "\n[TBD]\n")
        r = run("gate_check.py", "submission", cwd=research)
        assert r.fails >= 1 and name in r.out and "markers" in r.out, (name, r.out)
        write(p, s0)


# ------------------------------------------------------------------ G6b: ablation-resolve statement may sit in a caption / table footnote
SENT = "Two of the four cells are therefore not resolvable within seed noise and we do not interpret them."
SENT2 = "The consistency term is not resolvable at the present seed budget, so we make no claim about it."     # Discussion/limitations, inside the same top-level section as the ablation


def _plan(research):
    assert run("draft_plan.py", "plan", "--project", ".", cwd=research).returncode == 0


def test_resolve_statement_in_caption_satisfies_g6b(research):
    _plan(research)
    edit(_ms(research), SENT, "We do not interpret the other two cells."); edit(_ms(research), SENT2, "We make no claim about it.")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails >= 1 and "不可解读" in r.out, r.out            # nowhere in Results / captions: still a FAIL
    edit(_ms(research), "the reference row is the mean of the 3 seeds in Table 1.", "the reference row is the mean of the 3 seeds in Table 1; grey cells are not resolvable within seed noise.")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails == 0, r.out


def test_resolve_statement_in_table_footnote_satisfies_g6b(research):
    _plan(research)
    edit(_ms(research), SENT, "We do not interpret the other two cells."); edit(_ms(research), SENT2, "We make no claim about it.")
    edit(_ms(research), "| no_cons | 0.203 | 0.304 |\n", "| no_cons | 0.203 | 0.304 |\nCells within seed noise are not resolvable and are greyed.\n")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)
    assert r.fails == 0, r.out


def test_resolve_statement_elsewhere_in_prose_does_not_count(research):
    _plan(research)
    edit(_ms(research), SENT, "We do not interpret the other two cells."); edit(_ms(research), SENT2, "We make no claim about it.")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)      # abstract / contribution / limitations still say "not resolvable"
    assert r.fails >= 1 and "不可解读" in r.out, r.out


# ------------------------------------------------------------------ G6f readability_check.py
import io
import os
import sys

sys.path.insert(0, str(__import__("conftest").SCRIPTS))
import readability_check as rc          # noqa: E402

NORMS_HDR = "family,metric,p50,p90,p95,n\n"


def _norms(path, family="cs_conf", **over):
    """a norms file where every metric is unreachable (p90/p95 = 1e6/2e6) unless overridden as name=(p90, p95)"""
    rows = "".join(f"{family},{m},1,{over.get(m, (1e6, 2e6))[0]},{over.get(m, (1e6, 2e6))[1]},40\n" for m in rc.METRICS)
    write(path, "# test norms\n" + NORMS_HDR + rows)
    return path


def _lax(path, family="cs_conf"):
    return _norms(path, family, **{m: (1e6, 2e6) for m in rc.METRICS})


FILLER = ("The sensor model maps a raw reading to a calibrated estimate and the estimate feeds a controller that was tuned on the bench. "
          "Earlier work treated the offset as noise and averaged it away, which hides the dependence on the platform. "
          "We instead model the offset explicitly and show that it transfers across platforms without retraining the controller.")


def _paper(tmp_path, abstract=None, contribs=None, intro=None, results=None, appendix="", related=None):
    ab = abstract or "We study sensor offsets in force estimation and propose a regularizer that removes them across two platforms with a clear gain on the held-out platform."
    cs = contribs or ["A regularizer that removes the offset from the shared representation of the encoder.", "A protocol that compares every method under one contact convention.", "An analysis that shows where the gain comes from and where it does not."]
    md = (f"# Title\n\n## Abstract\n\n{ab}\n\n## 1. Introduction\n\n{intro or FILLER}\n\nThe contributions of this paper are:\n\n" + "\n".join(f"- {c}" for c in cs) + "\n\n"
          f"## 2. Related Work\n\n{related or FILLER}\n\n## 3. Method\n\n{FILLER}\n\n## 4. Experiments\n\n{results or FILLER}\n\n## 5. Conclusion\n\n{FILLER}\n\n{appendix}\n## References\n\n[1] A. Author, A title, 2020.\n")
    write(tmp_path / "paper" / "manuscript.md", md)
    write(tmp_path / "research-state.yaml", "target:\n  family: cs_conf\n  venue: CVPR\nacronym_ok: []\n")
    return tmp_path


def _rc(tmp_path, norms, *extra):
    return run("readability_check.py", "--project", ".", "--norms", norms, "--min-words", "0", *extra, cwd=tmp_path)


def test_readability_clean_paper_passes(tmp_path):
    _paper(tmp_path); r = _rc(tmp_path, _norms(tmp_path / "n.csv"))
    assert r.fails == 0 and not r.crashed, r.out
    assert "[PASS] readability: 正文没有流程簿记词" in r.out and "contrib_numbers_max" in r.out, r.out


def test_count_numbers_rules():
    c = rc.count_numbers
    assert c("accuracy rose from 0.79–3.09 and 52–86% and 0.20 ± 0.03 and 12.5%") == 4         # a range or a +- pair is one number
    assert c("see Fig. 3 and Table 2 and Section 4.2 and Eq. (3) [12] [1, 2, 5-7] (Smith et al., 2020) in 2021") == 0
    assert c("ResNet-50 and COVID-19 and GPT-4") == 0
    assert c("we used 3 seeds and 1,000 images") == 2


def test_contribution_numbers_over_p95_fails(tmp_path):
    cs = ["A regularizer cuts RMSE by 19.2% on E1, 11.0% on E2, 4.1 N to 3.3 N and 0.30 to 0.22 across 3 seeds and 11 runs.", "A protocol that compares every method under one contact convention.", "An analysis of where the gain comes from."]
    _paper(tmp_path, contribs=cs); r = _rc(tmp_path, _norms(tmp_path / "n.csv", contrib_numbers_max=(2, 4)))
    assert r.fails >= 1 and "[FAIL] readability: contrib_numbers_max" in r.out, r.out
    r = _rc(tmp_path, _norms(tmp_path / "n.csv", contrib_numbers_max=(2, 40)))
    assert r.fails == 0 and "[WARN] readability: contrib_numbers_max" in r.out, r.out            # between p90 and p95: WARN only


def test_one_metric_over_p95_is_only_a_warning(tmp_path):
    # 7–12 of 40 published papers per family exceed p95 on exactly one metric; one alone is not a FAIL
    ab = "RMSE falls from 0.31 to 0.22 on E1 (19.2%), from 0.40 to 0.30 on E2 (25%), by 4.1 N, 3.3 N and 2.2 N across 3 seeds, 11 runs and 5 splits."
    _paper(tmp_path, abstract=ab); r = _rc(tmp_path, _norms(tmp_path / "n.csv", abstract_numbers=(5, 8)))
    assert r.fails == 0 and "[WARN] readability: abstract_numbers" in r.out and "超过已发表论文 95 分位" in r.out, r.out


def test_number_density_in_body_over_p95_warns(tmp_path):
    dense = " ".join(f"The error is {i}.{i} N at {i + 3}.{i} mm for {i + 7} of {i + 40} runs in split {i + 1}." for i in range(1, 25))
    _paper(tmp_path, results=dense); r = _rc(tmp_path, _norms(tmp_path / "n.csv", body_numbers_per1k=(30, 50)))
    assert "[WARN] readability: body_numbers_per1k" in r.out and "超过已发表论文 95 分位" in r.out, r.out


def test_numbers_in_captions_tables_math_appendix_are_not_counted(tmp_path):
    junk = ("**Table 1.** Errors 1.1 2.2 3.3 4.4 5.5 6.6 7.7 8.8 9.9 in 10 11 12 13 14 15 16 runs\n\n| a | b |\n|---|---|\n| 1.1 | 2.2 |\n\n"
            "$$x = 1.1 + 2.2 + 3.3 + 4.4 + 5.5 + 6.6 + 7.7 + 8.8 + 9.9$$\n\n")
    _paper(tmp_path, results=FILLER + "\n\n" + junk, appendix="## Appendix A\n\n" + " ".join(f"Run {i} gave {i}.{i} and {i}.{i + 1} and {i}.{i + 2} N." for i in range(1, 60)) + "\n\n")
    r = _rc(tmp_path, _norms(tmp_path / "n.csv", body_numbers_per1k=(8, 12)))
    assert r.fails == 0 and "[PASS] readability: body_numbers_per1k" in r.out, r.out


def test_process_vocabulary_fails_above_three_warns_below(tmp_path):
    one = FILLER + " The thresholds were preregistered before any run."
    _paper(tmp_path, results=one); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 0 and "[WARN] readability: 正文出现 1 处流程簿记词" in r.out, r.out
    many = FILLER + " The thresholds were preregistered. The registered ablation was refuted by the addendum. Gate G6c locked the number; see findings.md."
    _paper(tmp_path, results=many); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 1 and "[FAIL] readability: 正文出现" in r.out and "Protocol" in r.out, r.out


def test_process_vocabulary_in_protocol_appendix_is_allowed(tmp_path):
    many = "The thresholds were preregistered. The registered ablation was refuted by the addendum. Gate G6c locked the number; see findings.md. Finding F29 was amended post hoc."
    _paper(tmp_path, appendix="## Appendix B. Protocol and preregistration\n\n" + many + "\n\n"); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 0 and "没有流程簿记词" in r.out, r.out
    _paper(tmp_path, appendix="## Protocol\n\n" + many + "\n\n"); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 0 and "没有流程簿记词" in r.out, r.out


def test_f1_and_model_names_are_not_finding_ids(tmp_path):
    _paper(tmp_path, results=FILLER + " The F1 score of bridge F4 and F6 is 0.8 for registered images and image registration."); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 0 and "没有流程簿记词" in r.out, r.out


CAT = ("Prior work studied offsets with filters [1, 2]; others used adaptive observers [3]; some relied on learned models [4, 5]; yet others combined sensors [6, 7]; "
       "and a recent line used transformers [8].")
NAMED = " ".join(f"Author{i} et al. [{i}] proposed a method{i} for sensing." for i in range(1, 7))


def test_catalogue_paragraph_warns_three_fail(tmp_path):
    _paper(tmp_path, related=FILLER + "\n\n" + CAT); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 0 and "[WARN] readability: 引言 / 相关工作有 1 个目录式段落" in r.out, r.out
    _paper(tmp_path, related=CAT + "\n\n" + NAMED, intro=CAT); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 1 and "[FAIL] readability: 引言 / 相关工作有 3 个目录式段落" in r.out, r.out


def test_catalogue_outside_intro_and_related_is_ignored(tmp_path):
    _paper(tmp_path, results=CAT + "\n\n" + NAMED); r = _rc(tmp_path, _lax(tmp_path / "n.csv"))
    assert r.fails == 0 and "没有目录式段落" in r.out, r.out


def test_uncalibrated_family_uses_provisional_with_warning(tmp_path):
    _paper(tmp_path); r = _rc(tmp_path, _norms(tmp_path / "n.csv", family="nature"))
    assert r.fails == 0 and "未校准" in r.out and "PROVISIONAL" in r.out, r.out


def test_sentence_length_metrics(tmp_path):
    long_s = "Word " + " ".join(["word"] * 54) + "."
    _paper(tmp_path, intro=(long_s + " ") * 8); r = _rc(tmp_path, _norms(tmp_path / "n.csv", intro_sent_len_mean=(30, 38), intro_long_sent_share=(0.3, 0.5)))
    assert r.fails == 0 and "[WARN] readability: intro_sent_len_mean" in r.out and "[WARN] readability: intro_long_sent_share" in r.out, r.out
    assert "2 项指标超过 95 分位" in r.out, r.out


def test_three_metrics_over_p95_at_once_fail(tmp_path):
    # >= 3 metrics above p95 together: 2/40 published papers per family, 7–11 in the three real drafts
    long_s = "Word " + " ".join(["word"] * 54) + "."
    ab = "RMSE falls from 0.31 to 0.22 on E1 (19.2%), from 0.40 to 0.30 on E2 (25%), by 4.1 N, 3.3 N and 2.2 N across 3 seeds, 11 runs and 5 splits."
    _paper(tmp_path, abstract=ab, intro=(long_s + " ") * 8)
    r = _rc(tmp_path, _norms(tmp_path / "n.csv", abstract_numbers=(5, 8), intro_sent_len_mean=(30, 38), intro_long_sent_share=(0.3, 0.5)))
    assert r.fails == 1 and "[FAIL] readability: 3 项指标同时超过已发表论文 95 分位" in r.out, r.out


def test_missing_manuscript_fails(tmp_path):
    write(tmp_path / "research-state.yaml", "target:\n  family: cs_conf\n")
    assert _rc(tmp_path, _lax(tmp_path / "n.csv")).fails == 1


def test_shipped_norms_file_is_complete():
    norms = rc.load_norms()
    for fam in ("cs_conf", "cs_journal", "nature"):
        have = {m for (f, m) in norms if f == fam}
        assert {"abstract_numbers", "abstract_words", "intro_numbers_per1k", "body_numbers_per1k", "body_sent_len_mean"} <= have, (fam, sorted(have))
    for (f, m), (p50, p90, p95, n) in norms.items():
        assert m in rc.METRICS and p50 <= p90 <= p95 and n >= 8, (f, m, p50, p90, p95, n)
    head = io.open(rc.NORMS_CSV, encoding="utf-8").read().splitlines()[0]
    assert head.startswith("#") and "seed 20261023" in head, head


def test_calibrate_candidates_and_percentiles(tmp_path):
    for rel in ("CVPR/2022/a.pdf", "CVPR/2024/b.pdf", "TMI/2025/c.pdf", "nature/NatCommun/2024/W1.pdf", "nature/NatCommun/2024/W2.pdf", "nature/NatCommun/2020/W3.pdf"):
        write(tmp_path / "corpus" / rel, "x")
    write(tmp_path / "corpus" / "nature" / "metadata" / "journals.csv", "journal,year,type,field,openalex_id\nNatCommun,2024,article,Biology,W1\nNatCommun,2024,review,Biology,W2\n")
    c = lambda fam: sorted(os.path.basename(p) for p, v, f in rc.list_candidates(str(tmp_path / "corpus"), fam, 2023))
    assert c("cs_conf") == ["b.pdf"] and c("cs_journal") == ["c.pdf"] and c("nature") == ["W1.pdf"]       # >= 2023 only; reviews excluded
    assert rc.pct([1, 2, 3, 4, 5], 0.5) == 3 and abs(rc.pct(list(range(1, 101)), 0.95) - 95.05) < 1e-9


def test_short_text_rates_only_warn(tmp_path):
    long_s = "Word " + " ".join(["word"] * 54) + "."
    _paper(tmp_path, intro=(long_s + " ") * 8); n = _norms(tmp_path / "n.csv", intro_long_sent_share=(0.3, 0.5))
    r = run("readability_check.py", "--project", ".", "--norms", n, cwd=tmp_path)                      # default --min-words 1500: ~700-word stub
    assert r.fails == 0 and "[WARN] readability: intro_long_sent_share" in r.out and "比率不稳" in r.out, r.out


def test_research_fixture_has_no_readability_fail(research):
    r = run("readability_check.py", "--project", ".", cwd=research)
    assert r.fails == 0 and not r.crashed, r.out
