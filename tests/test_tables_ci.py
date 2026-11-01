# -*- coding: utf-8 -*-
"""make_comparison.py tables: uncertainty in cells (_lo/_hi/_sd), significance marks (sig_<metric>), Delta row, width fitting (--fit),
and latex_check.py's Overfull \\hbox check for tables (G6d). The script only renders what the csv says; nothing here tests significance."""
import csv

from conftest import read, run, touch, write

HEAD = "method,family,AP50,AP50_lo,AP50_hi,AP50_sd,sig_AP50,Params\n"
ROWS = ("A,CNN,0.612,0.600,0.624,0.010,1,10\n"
        "B,CNN,0.640,0.630,0.650,0.008,0.01,12\n"
        "Ours,X,0.700,0.690,0.710,0.007,,9\n")


def _csv(tmp_path, text=HEAD + ROWS, name="m.csv"):
    write(tmp_path / name, text)
    return tmp_path / name


def _sota(tmp_path, *extra, text=HEAD + ROWS, metrics="AP50"):
    return run("make_comparison.py", "sota", "--csv", _csv(tmp_path, text), "--out", tmp_path / "t.tex", "--md", "--metrics", metrics, "--higher", metrics,
               "--ours", "Ours", *extra, cwd=tmp_path)


# ------------------------------------------------------------------ uncertainty
def test_ci_bracket_in_tex_and_md(tmp_path):
    r = _sota(tmp_path)
    assert r.returncode == 0, r.out
    tex, md = read(tmp_path / "t.tex"), read(tmp_path / "t.md")
    assert r"0.612$^\dagger$\,{\scriptsize[0.600, 0.624]}" in tex            # the dagger sits on the point estimate, the interval follows
    assert r"\textbf{\textcolor{red}{0.700}}\,{\scriptsize[0.690, 0.710]}" in tex   # best colouring stays on the point estimate
    assert "| 0.612† [0.600, 0.624] |" in md and "**0.700** [0.690, 0.710]" in md


def test_sd_column_prints_pm(tmp_path):
    text = "method,AP50,AP50_sd\nA,0.612,0.010\nOurs,0.700,0.007\n"
    r = _sota(tmp_path, text=text)
    assert r.returncode == 0, r.out
    assert r"\textcolor{blue}{0.612}\,{\scriptsize$\pm$0.010}" in read(tmp_path / "t.tex") and "| _0.612_ ± 0.010 |" in read(tmp_path / "t.md")


def test_ci_style_pm_turns_bounds_into_half_width_and_none_switches_off(tmp_path):
    text = "method,AP50,AP50_lo,AP50_hi\nA,0.612,0.600,0.624\nOurs,0.700,0.690,0.710\n"
    r = _sota(tmp_path, "--ci-style", "pm", text=text)
    assert r.returncode == 0, r.out
    assert r"{0.612}\,{\scriptsize$\pm$0.012}" in read(tmp_path / "t.tex")
    r = _sota(tmp_path, "--ci-style", "none", text=text)
    assert r.returncode == 0, r.out
    tex = read(tmp_path / "t.tex")
    assert "scriptsize" not in tex and "0.612" in tex


def test_no_uncertainty_columns_leave_the_table_unchanged(tmp_path):
    r = _sota(tmp_path, text="method,AP50\nA,0.612\nOurs,0.700\n")
    assert r.returncode == 0, r.out
    assert "scriptsize" not in read(tmp_path / "t.tex") and "dagger" not in read(tmp_path / "t.tex")


def test_ci_bounds_registered_as_numbers(tmp_path):
    r = _sota(tmp_path, "--numbers")
    assert r.returncode == 0, r.out
    rows = list(csv.DictReader(open(tmp_path / "numbers.csv", encoding="utf-8")))
    by = {x["key"]: x for x in rows}
    lo = by["dataset=|method=A|metric=AP50_lo,value"]; hi = by["dataset=|method=A|metric=AP50_hi,value"]
    assert lo["value"] == "0.600" and hi["value"] == "0.624" and lo["file"] == "t.source.csv"
    src = {(x["method"], x["metric"]): x["value"] for x in csv.DictReader(open(tmp_path / "t.source.csv", encoding="utf-8"))}
    assert src[("A", "AP50_lo")] == "0.600"       # numbers.csv points at a real source cell
    assert "dataset=|method=Ours|metric=AP50_hi,value" in by


def test_pm_half_width_registered_with_its_formula(tmp_path):
    text = "method,AP50,AP50_lo,AP50_hi\nA,0.612,0.600,0.624\nOurs,0.700,0.690,0.710\n"
    r = _sota(tmp_path, "--ci-style", "pm", "--numbers", text=text)
    assert r.returncode == 0, r.out
    rows = {x["key"]: x for x in csv.DictReader(open(tmp_path / "numbers.csv", encoding="utf-8"))}
    hw = rows["dataset=|method=A|metric=AP50_halfwidth,value"]
    assert hw["value"] == "0.012" and "AP50_hi" in hw["transform"]


def test_ablation_takes_the_same_uncertainty_and_dagger(tmp_path):
    write(tmp_path / "a.csv", "SGA,CFE,AP50,AP50_lo,AP50_hi,sig_AP50\n0,0,0.60,0.59,0.61,1\n1,1,0.70,0.69,0.71,\n")
    r = run("make_comparison.py", "ablation", "--csv", tmp_path / "a.csv", "--out", tmp_path / "t.tex", "--md", "--metrics", "AP50", "--higher", "AP50",
            "--components", "SGA,CFE", "--decimals", "2", "--sig-test", "paired t-test", cwd=tmp_path)
    assert r.returncode == 0, r.out
    tex = read(tmp_path / "t.tex")
    assert r"$^\dagger$\,{\scriptsize[0.59, 0.61]}" in tex and "paired t-test" in tex


# ------------------------------------------------------------------ significance
def test_dagger_and_footnote_from_flag_and_p_value(tmp_path):
    r = _sota(tmp_path, "--sig-test", "paired bootstrap, 10k resamples", "--alpha", "0.05")
    assert r.returncode == 0, r.out
    tex, md = read(tmp_path / "t.tex"), read(tmp_path / "t.md")
    assert tex.count(r"$^\dagger$") == 3                                    # 2 cells (A: flag 1, B: p = 0.01) + the footnote mark
    assert r"significantly different from Ours (paired bootstrap, 10k resamples, $\alpha = 0.05$)" in tex
    assert tex.index("significantly different") > tex.index(r"\end{tabular}") and tex.index("significantly different") < tex.index(r"\end{table}")
    assert md.count("†") == 3 and "† significantly different from Ours (paired bootstrap, 10k resamples, α = 0.05)." in md
    assert "[WARN]" not in r.out


def test_p_value_above_alpha_is_not_marked(tmp_path):
    text = "method,AP50,sig_AP50\nA,0.612,0.20\nB,0.640,0.049\nOurs,0.700,\n"
    r = _sota(tmp_path, "--sig-test", "Wilcoxon", text=text)
    assert r.returncode == 0, r.out
    md = read(tmp_path / "t.md")
    assert "0.640_†" in md                                                 # p = 0.049 < 0.05 (B is second best, hence the underscores)
    assert "0.612†" not in md and md.count("†") == 2                       # one cell + the footnote
    r = _sota(tmp_path, "--sig-test", "Wilcoxon", "--alpha", "0.01", text=text)
    assert "†" not in read(tmp_path / "t.md")                              # nothing significant at 0.01: no mark, no footnote
    assert "significantly" not in read(tmp_path / "t.tex")


def test_sig_columns_without_sig_test_warn(tmp_path):
    r = _sota(tmp_path)
    assert r.returncode == 0, r.out
    assert "[WARN] sig_<metric> columns present but no --sig-test" in r.out
    assert "never tests anything" in r.out


# ------------------------------------------------------------------ Delta row
def test_delta_row_higher_is_better_and_registered(tmp_path):
    r = _sota(tmp_path, "--delta", "best", "--numbers")
    assert r.returncode == 0, r.out
    tex, md = read(tmp_path / "t.tex"), read(tmp_path / "t.md")
    assert r"$\Delta$ vs best baseline" in tex and "+0.060" in tex and "| Δ vs best baseline |" in md and "+0.060" in md   # 0.700 - 0.640 (B is the strongest)
    lines = tex.splitlines(); k = next(i for i, l in enumerate(lines) if l.startswith(r"$\Delta$"))
    assert lines[k - 1] == r"\midrule" and lines[k + 1] == r"\bottomrule"      # a separate final row
    row = {x["key"]: x for x in csv.DictReader(open(tmp_path / "numbers.csv", encoding="utf-8"))}["dataset=|method=delta_vs_best|metric=AP50_delta,value"]
    assert row["value"] == "0.060" and row["transform"] == "AP50[Ours] - AP50[B]"
    src = {(x["method"], x["metric"]): x["value"] for x in csv.DictReader(open(tmp_path / "t.source.csv", encoding="utf-8"))}
    assert src[("delta_vs_best", "AP50_delta")] == "0.060"


def test_delta_row_lower_is_better_uses_the_lowest_baseline(tmp_path):
    text = "method,RMSE\nA,0.30\nB,0.25\nOurs,0.20\n"
    r = run("make_comparison.py", "sota", "--csv", _csv(tmp_path, text), "--out", tmp_path / "t.tex", "--md", "--metrics", "RMSE", "--lower", "RMSE", "--ours", "Ours",
            "--delta", "best", "--decimals", "2", cwd=tmp_path)
    assert r.returncode == 0, r.out
    tex, md = read(tmp_path / "t.tex"), read(tmp_path / "t.md")
    assert "$-0.05$" in tex and "| -0.05 |" in md       # 0.20 - 0.25: B is the strongest (lowest) baseline; md keeps an ASCII minus for the numbers gate


def test_delta_vs_named_method_and_missing_ours(tmp_path):
    r = _sota(tmp_path, "--delta", "A")
    assert r.returncode == 0, r.out
    assert "+0.088" in read(tmp_path / "t.tex") and r"vs A" in read(tmp_path / "t.tex")
    r = run("make_comparison.py", "sota", "--csv", _csv(tmp_path), "--out", tmp_path / "t2.tex", "--metrics", "AP50", "--delta", "best", cwd=tmp_path)
    assert "[WARN] --delta needs an --ours row" in r.out and "Delta" not in read(tmp_path / "t2.tex")


def test_delta_row_per_dataset_in_multi(tmp_path):
    write(tmp_path / "m.csv", "method,task,AP\nA,d1,0.5\nOurs,d1,0.6\nA,d2,0.7\nOurs,d2,0.65\n")
    r = run("make_comparison.py", "multi", "--csv", tmp_path / "m.csv", "--out", tmp_path / "t.tex", "--md", "--metrics", "AP", "--higher", "AP", "--ours", "Ours",
            "--datasets", "d1,d2", "--dataset-col", "task", "--delta", "best", "--decimals", "2", cwd=tmp_path)
    assert r.returncode == 0, r.out
    tex = read(tmp_path / "t.tex")
    assert r"+0.10 & $-0.05$" in tex


# ------------------------------------------------------------------ width fitting
WIDE_HEAD = "method," + ",".join(f"M{i}" for i in range(8)) + "\n"
WIDE_ROWS = "".join(f"A_long_method_name_{k}," + ",".join("0.123" for _ in range(8)) + "\n" for k in range(3))


def _wide(tmp_path, *extra, **kw):
    metrics = ",".join(f"M{i}" for i in range(8))
    return run("make_comparison.py", "sota", "--csv", _csv(tmp_path, WIDE_HEAD + WIDE_ROWS, "w.csv"), "--out", tmp_path / "w.tex", "--metrics", metrics, "--higher", metrics, *extra, **{"cwd": tmp_path})


def test_fit_narrow_table_gets_no_resizebox(tmp_path):
    r = _sota(tmp_path, "--width-mm", "88", "--ci-style", "none")
    assert r.returncode == 0, r.out
    assert "resizebox" not in read(tmp_path / "t.tex") and "[PASS] table width" in r.out and "fits 88 mm" in r.out


def test_fit_wide_table_is_wrapped_and_reports_the_printed_size(tmp_path):
    r = _wide(tmp_path, "--width-mm", "120")
    assert r.returncode == 0, r.out
    tex = read(tmp_path / "w.tex")
    assert "\\resizebox{\\linewidth}{!}{%\n\\begin{tabular}" in tex and "\\end{tabular}}" in tex
    assert "effective printed font size" in r.out and "pt" in r.out and "[PASS] table width" in r.out


def test_fit_between_5_and_6_pt_warns(tmp_path):
    r = _wide(tmp_path, "--width-mm", "80")
    assert r.returncode == 0, r.out
    assert "\\resizebox" in read(tmp_path / "w.tex") and "[WARN] table width" in r.out and "< 6 pt" in r.out


def test_fit_extreme_table_fails_and_emits_no_resizebox(tmp_path):
    r = _wide(tmp_path, "--width-mm", "40")
    assert r.returncode == 1 and r.fails == 1, r.out
    assert "split the table" in r.out and "(< 5 pt)" in r.out
    assert "resizebox" not in read(tmp_path / "w.tex")           # the file is still written, but without the unreadable scaling


def test_fit_none_never_wraps_and_forced_modes_always_do(tmp_path):
    r = _wide(tmp_path, "--width-mm", "170", "--fit", "none")
    assert "resizebox" not in read(tmp_path / "w.tex") and "--fit none" not in r.out       # it fits: no warning
    r = _wide(tmp_path, "--width-mm", "100", "--fit", "none")
    assert "resizebox" not in read(tmp_path / "w.tex") and "[WARN] table width" in r.out and "--fit none" in r.out
    r = _wide(tmp_path, "--width-mm", "300", "--fit", "columnwidth")
    assert "\\resizebox{\\columnwidth}{!}" in read(tmp_path / "w.tex") and "scaled UP" in r.out


def test_fit_target_comes_from_the_venue_template(tmp_path):
    write(tmp_path / "research-state.yaml", "target:\n  venue: CVPR\n  family: cs_conf\n")
    r = _wide(tmp_path, "--project", ".")
    assert "cvpr template, single column" in r.out and "\\resizebox" in read(tmp_path / "w.tex"), r.out
    write(tmp_path / "w3.csv", "method,dataset,M0\nA,d1,0.1\nA,d2,0.2\n")
    r = run("make_comparison.py", "multi", "--csv", tmp_path / "w3.csv", "--out", tmp_path / "w3.tex", "--metrics", "M0", "--datasets", "d1,d2", "--project", ".", cwd=tmp_path)
    assert "full text width" in r.out                              # table* spans both columns


def test_fit_without_project_defaults_to_170_mm(tmp_path):
    r = _wide(tmp_path)
    assert "170 mm" in r.out and "default 170 mm" in r.out


def test_resizebox_without_graphicx_warns(tmp_path):
    write(tmp_path / "paper" / "latex" / "main.tex", "\\documentclass{article}\n\\begin{document}\n\\end{document}\n")
    r = run("make_comparison.py", "sota", "--csv", _csv(tmp_path, WIDE_HEAD + WIDE_ROWS, "w.csv"), "--out", tmp_path / "paper" / "w.tex",
            "--metrics", ",".join(f"M{i}" for i in range(8)), "--width-mm", "120", "--project", ".", cwd=tmp_path)
    assert "[WARN] \\resizebox needs graphicx" in r.out, r.out
    write(tmp_path / "paper" / "latex" / "main.tex", "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\end{document}\n")
    r = run("make_comparison.py", "sota", "--csv", tmp_path / "w.csv", "--out", tmp_path / "paper" / "w.tex",
            "--metrics", ",".join(f"M{i}" for i in range(8)), "--width-mm", "120", "--project", ".", cwd=tmp_path)
    assert "graphicx" not in r.out


def test_seeds_table_is_fitted_too(tmp_path):
    write(tmp_path / "s.csv", "setting,seed,nll\n" + "".join(f"a_rather_long_setting_name_{k},{s},0.5\n" for k in range(2) for s in range(1, 9)))
    r = run("make_comparison.py", "seeds", "--csv", tmp_path / "s.csv", "--out", tmp_path / "t.tex", "--metrics", "nll", "--lower", "nll", "--width-mm", "70", cwd=tmp_path)
    assert "\\resizebox" in read(tmp_path / "t.tex") or r.fails == 1, r.out


# ------------------------------------------------------------------ latex_check: Overfull \hbox inside tables (G6d)
LOG_HEAD = "This is pdfTeX, Version 3.14159265-2.6-1.40.21\n(./main.tex\nLaTeX2e <2020-10-01>\n(/usr/share/texlive/article.cls (Font) shape)\n"


def _overfull(research, log_body, extra_tex=None):
    lt = research / "paper" / "latex"
    if extra_tex:
        write(lt / "tab_wide.tex", extra_tex)
        s = read(lt / "main.tex").replace("\\section{Conclusion}", "\\input{tab_wide}\n\\section{Conclusion}", 1)
        write(lt / "main.tex", s)
    write(lt / "main.log", LOG_HEAD + log_body)
    touch(lt / "main.log", 5); touch(research / "paper" / "manuscript.md", 3)
    return run("latex_check.py", "check", cwd=research)


def test_overfull_over_10pt_in_a_table_fails_with_the_label(research):
    r = _overfull(research, "Overfull \\hbox (14.2pt too wide) in alignment at lines 46--53\n[]\\OT1/cmr/m/n/10 x\n)\n")
    assert "[FAIL] latex: 表 tab:main 超出版心 14.2 pt" in r.out, r.out


def test_overfull_between_2_and_10pt_warns(research):
    r = _overfull(research, "Overfull \\hbox (4.5pt too wide) in alignment at lines 46--53\n)\n")
    assert "[WARN] latex: 表 tab:main 超出版心 4.5 pt" in r.out and "超出版心" not in "".join(x for x in r.out.splitlines() if x.startswith("[FAIL]")), r.out


def test_overfull_under_2pt_or_outside_tables_passes(research):
    r = _overfull(research, "Overfull \\hbox (1.5pt too wide) in alignment at lines 46--53\nOverfull \\hbox (30.0pt too wide) in paragraph at lines 25--25\n)\n")
    assert "[PASS] latex: main.log: 表格没有 > 2 pt 的 Overfull" in r.out and "超出版心" not in r.out, r.out     # line 25 is the Introduction, not a table


def test_overfull_detected_at_line_form_is_matched(research):
    r = _overfull(research, "Overfull \\hbox (12.0pt too wide) detected at line 50\n)\n")
    assert "[FAIL] latex: 表 tab:main 超出版心 12.0 pt" in r.out, r.out


def test_overfull_is_attributed_to_the_input_file_via_the_log_stack(research):
    tab = "\\begin{table}[t]\n\\centering\n\\caption{Wide.}\n\\label{tab:wide}\n\\begin{tabular}{lcc}\na & b & c \\\\\n\\end{tabular}\n\\end{table}\n"
    # lines 5--7 are the tabular of tab_wide.tex; in main.tex the same lines are the preamble (not a table)
    r = _overfull(research, "(./tab_wide.tex\nOverfull \\hbox (20.0pt too wide) in alignment at lines 5--7\n)\n", extra_tex=tab)
    assert "[FAIL] latex: 表 tab:wide 超出版心 20.0 pt" in r.out and "tab:main 超出版心" not in r.out, r.out
    r = _overfull(research, "Overfull \\hbox (20.0pt too wide) in alignment at lines 5--7\n)\n")      # log says main.tex: lines 5--7 are not in a table of main.tex
    assert "超出版心" not in r.out, r.out


def test_overfull_stale_log_is_not_trusted(research):
    lt = research / "paper" / "latex"
    write(lt / "main.log", LOG_HEAD + "Overfull \\hbox (30pt too wide) in alignment at lines 46--53\n)\n")
    touch(lt / "main.log", -3600)
    r = run("latex_check.py", "check", cwd=research)
    assert "main.log 比 .tex 源旧" in r.out and "超出版心" not in r.out, r.out


def test_no_log_means_no_overfull_line(research):
    r = run("latex_check.py", "check", cwd=research)
    assert "Overfull" not in r.out and r.fails == 0, r.out
