# -*- coding: utf-8 -*-
"""Algorithm blocks (pseudocode): skeleton from the code, the seven checks (inside G6d), the Markdown mirror (tex_to_md), G6 floats, readability / numbers blindness, G6c norms, G6b item, calibrate."""
import csv
import io
import re
import sys

from conftest import SCRIPTS, edit, read, run, touch, write

sys.path.insert(0, str(SCRIPTS))
import make_algorithm as ma  # noqa: E402

TEX = ("paper", "latex", "alg_train.tex")
MAIN = ("paper", "latex", "main.tex")


def _p(project, parts):
    return project.joinpath(*parts)


def chk(project):
    return run("make_algorithm.py", "check", cwd=project)


def _state_rows(project, extra):
    """append algorithm rows to research-state.yaml (the file ends with the algorithms: block)"""
    p = project / "research-state.yaml"
    write(p, read(p).rstrip("\n") + "\n" + extra)


# ------------------------------------------------------------------ pass
def test_algorithm_check_pass(research):
    r = chk(research)
    assert r.fails == 0 and not r.crashed, r.out
    assert "[PASS] algorithm: alg:train" in r.out and "3 个 \\Require 数值与 ref run 一致" in r.out and "ALL PASS" in r.out


def test_g6d_folds_in_the_algorithm_lines(research):
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails == 0 and "[PASS] algorithm: alg:train" in r.out, r.out
    edit(_p(research, MAIN), "Algorithm~\\ref{alg:train} summarises the training procedure.", "")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "正文没有 \\ref" in r.out and "[FAIL] algorithm:" in r.out, r.out


def test_board_is_green_with_the_fixture_algorithm(research):
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    r = run("t2p.py", "check", "--project", ".", cwd=research)
    assert "[PASS] G6d:" in r.out and "[FAIL]" not in r.out and r.returncode == 0, r.out


def test_no_algorithm_no_algorithm_lines(research):
    s = read(research / "research-state.yaml")
    write(research / "research-state.yaml", s[:s.index("\nalgorithms:")] + "\n")
    edit(_p(research, MAIN), "\\input{alg_train}", "")
    edit(_p(research, MAIN), "Algorithm~\\ref{alg:train} summarises the training procedure.", "")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails == 0 and "algorithm:" not in r.out, r.out


# ------------------------------------------------------------------ skeleton
def _skel(project, aid="train", *extra):
    return run("make_algorithm.py", "skeleton", "--id", aid, *extra, cwd=project)


def test_skeleton_algpseudocode_dialect(research):
    _p(research, TEX).unlink()
    r = _skel(research)
    assert r.returncode == 0, r.out
    t = read(_p(research, TEX))
    assert "\\begin{algorithm}[t]" in t and "\\label{alg:train}" in t and "\\begin{algorithmic}[1]" in t
    assert "\\For{$\\ldots$} % code: for epoch in range(epochs)" in t and t.count("\\If{") == 2 and "\\State \\Return $\\ldots$ % code: return history" in t
    assert "% code: loss = model.regression_loss(loader)" in t and "% args: model, loader, beta, alpha, epochs" in t
    assert "\\beta -> beta" in t and "K -> epochs" in t and "\\EndFor" in t
    assert "\\usepackage" not in r.out and "\\input" not in r.out            # main.tex already has the packages and the \input
    w = chk(research)
    assert w.fails == 0 and "skeleton 占位" in w.out, w.out                    # a skeleton passes but warns until the comments are rewritten


def test_skeleton_prints_the_lines_main_tex_is_missing(research):
    _p(research, TEX).unlink()
    edit(_p(research, MAIN), "\\usepackage{algorithm}\n\\usepackage{algpseudocode}\n", "")
    edit(_p(research, MAIN), "\\input{alg_train}", "")
    r = _skel(research)
    assert "\\usepackage{algorithm}" in r.out and "\\usepackage{algpseudocode}" in r.out and "\\input{alg_train}" in r.out, r.out


def test_skeleton_algorithm2e_dialect(research):
    _p(research, TEX).unlink()
    edit(_p(research, MAIN), "\\usepackage{algorithm}\n\\usepackage{algpseudocode}\n", "\\usepackage[ruled]{algorithm2e}\n")
    r = _skel(research)
    assert r.returncode == 0, r.out
    t = read(_p(research, TEX))
    assert "\\KwIn{$\\ldots$}" in t and "\\KwOut{" in t and "\\For{$\\ldots$}{" in t and "\\If{$\\ldots$}{" in t and "\\Return $\\ldots$\\;" in t
    assert "\\EndFor" not in t and "\\begin{algorithmic}" not in t and "\\State" not in t
    assert "algorithm2e" not in r.out                                           # package already loaded


def test_skeleton_algorithmic_package_uses_upper_case_commands(research):
    _p(research, TEX).unlink()
    edit(_p(research, MAIN), "\\usepackage{algpseudocode}", "\\usepackage{algorithmic}")
    _skel(research)
    t = read(_p(research, TEX))
    assert "\\STATE" in t and "\\FOR{" in t and "\\ENDFOR" in t and "\\RETURN" in t and "\\State" not in t


DEEP = '''def f(a, b):
    """doc"""
    x = 0
    for i in range(3):
        with torch.no_grad():
            for j in range(2):
                y = i + j
                if y > 1:
                    x += y
        if i == 1:
            continue
        elif i == 2:
            x = 3
        else:
            x = 4
    while x < 10:
        x += 1
    return x
'''


def test_skeleton_nesting_is_capped_at_depth_three(research):
    # SAM's first_step nests `for group / for p / e_w = ...`: at depth 2 the update line was hidden, so the cap is 3 and deeper bodies keep every statement as a comment
    write(research / "code" / "deep.py", DEEP)
    _state_rows(research, "  - id: deep\n    source: code/deep.py:f\n    tex: paper/latex/alg_deep.tex\n")
    r = _skel(research, "deep")
    assert r.returncode == 0, r.out
    t = read(research / "paper" / "latex" / "alg_deep.tex")
    assert t.count("\For{") == 2 and t.count("\While{") == 1 and t.count("\If{") == 2      # i-loop, j-loop (depth 2, expanded), `if y > 1` at depth 3 expanded as a header
    assert "% code: y = i + j" in t and "\If{$\ldots$} % code: if y > 1:" in t and "% code: x += y" in t       # depth-3 body: collapsed to one \State + comment, not lost
    assert "\ElsIf{" in t and "\Else" in t and "% code: with torch.no_grad()" in t and "doc" not in t


DEEPER = """def g(a):
    for i in range(2):
        for j in range(2):
            for k in range(2):
                p = i * j
                q = p + k
                if q > 1: a = q
    return a
"""


def test_skeleton_collapsed_body_lists_every_statement(research):
    write(research / "code" / "deeper.py", DEEPER)
    _state_rows(research, "  - id: deeper\n    source: code/deeper.py:g\n    tex: paper/latex/alg_deeper.tex\n")
    assert _skel(research, "deeper").returncode == 0
    t = read(research / "paper" / "latex" / "alg_deeper.tex")
    assert t.count("\For{") == 3                                                      # depth 1–3 expanded
    assert "% code: 3 statements:" in t and "%   p = i * j" in t and "%   q = p + k" in t and "%   if q > 1: a = q" in t     # depth-4 body: one placeholder, all lines kept


ONE_LINE = """def h(w, zero_grad=False):
    if zero_grad: w.zero_()
    for p in w:
        if p is None: continue
    return w
"""


def test_skeleton_one_line_if_is_not_duplicated(research):
    # `if zero_grad: self.zero_grad()` used to emit the whole line as the \If header AND again as its \State
    write(research / "code" / "one.py", ONE_LINE)
    _state_rows(research, "  - id: one\n    source: code/one.py:h\n    tex: paper/latex/alg_one.tex\n")
    assert _skel(research, "one").returncode == 0
    t = read(research / "paper" / "latex" / "alg_one.tex")
    assert "\If{$\ldots$} % code: if zero_grad:\n  \State $\ldots$ % code: w.zero_()" in t, t
    assert t.count("w.zero_()") == 1 and "% code: if p is None:\n" in t and "% code: continue" in t


def test_skeleton_refuses_overwrite_unknown_id_and_missing_function(research):
    r = _skel(research)
    assert r.returncode == 1 and "已存在" in r.out
    assert _skel(research, "train", "--force").returncode == 0
    r = _skel(research, "nope")
    assert r.returncode == 1 and "没有 id=nope" in r.out
    edit(research / "research-state.yaml", "train_one_epoch", "train_nothing")
    r = _skel(research, "train", "--force")
    assert r.returncode == 1 and "没有函数 train_nothing" in r.out


# ------------------------------------------------------------------ check 1: packages
def test_missing_algorithm_package_fails(research):
    edit(_p(research, MAIN), "\\usepackage{algorithm}\n", "")
    r = chk(research)
    assert r.fails >= 1 and "没有 \\usepackage{algorithm}" in r.out, r.out


def test_math_thick_space_is_not_an_algorithm2e_marker(research):
    """found on a real project (a \\STATE line ending in `;\\;`): `\\;` is also the math space, so it must not read as algorithm2e's line end"""
    edit(_p(research, TEX), "\\State $h \\gets \\emptyset$", "\\State $h \\gets \\emptyset$;\\; $g \\gets h$")
    r = chk(research)
    assert r.fails == 0 and "algorithm2e" not in r.out, r.out


def test_missing_algorithmic_package_fails(research):
    edit(_p(research, MAIN), "\\usepackage{algpseudocode}\n", "")
    r = chk(research)
    assert r.fails >= 1 and "algorithmic 环境但没有" in r.out, r.out


def test_algorithm2e_with_algpseudocode_conflicts(research):
    edit(_p(research, MAIN), "\\usepackage{algpseudocode}", "\\usepackage{algpseudocode}\n\\usepackage{algorithm2e}")
    r = chk(research)
    assert r.fails >= 1 and "同时加载" in r.out, r.out


def test_command_family_must_match_the_package(research):
    edit(_p(research, MAIN), "\\usepackage{algpseudocode}", "\\usepackage{algorithmic}")      # \State is algpseudocode; algorithmic wants \STATE
    r = chk(research)
    assert r.fails >= 1 and "algpseudocode 的命令" in r.out, r.out
    edit(_p(research, MAIN), "\\usepackage{algorithmic}", "\\usepackage{algpseudocode}")
    edit(_p(research, TEX), "\\Require", "\\REQUIRE"), edit(_p(research, TEX), "\\Ensure", "\\ENSURE")
    r = chk(research)
    assert r.fails >= 1 and "algorithmic 的命令" in r.out, r.out


def test_algorithm2e_commands_need_algorithm2e(research):
    edit(_p(research, TEX), "\\Ensure", "\\KwOut{x} \\Ensure")
    r = chk(research)
    assert r.fails >= 1 and "algorithm2e 的命令" in r.out, r.out


# ------------------------------------------------------------------ check 2: caption / label / ref
def test_missing_caption_fails(research):
    edit(_p(research, TEX), "\\caption{Training with the domain-adversarial and the consistency term.}\n", "")
    r = chk(research)
    assert r.fails >= 1 and "没有 \\caption" in r.out, r.out


def test_missing_label_fails(research):
    edit(_p(research, TEX), "\\label{alg:train}\n", "")
    edit(_p(research, MAIN), "Algorithm~\\ref{alg:train} summarises the training procedure.", "")
    r = chk(research)
    assert r.fails >= 1 and "没有 \\label{alg:...}" in r.out, r.out


def test_unreferenced_algorithm_fails(research):
    edit(_p(research, MAIN), "Algorithm~\\ref{alg:train} summarises the training procedure.", "")
    r = chk(research)
    assert r.fails == 1 and "正文没有 \\ref / \\cref / \\autoref" in r.out, r.out


def test_cref_counts_as_a_reference(research):
    edit(_p(research, MAIN), "Algorithm~\\ref{alg:train}", "\\cref{alg:train}")
    assert chk(research).fails == 0


# ------------------------------------------------------------------ check 3: anchor
def test_block_without_a_state_row_warns(research):
    s = read(research / "research-state.yaml")
    write(research / "research-state.yaml", s[:s.index("\nalgorithms:")] + "\n")
    r = chk(research)
    assert r.fails == 0 and "[WARN] algorithm:" in r.out and "没有 source 锚点" in r.out, r.out


def test_row_without_a_block_warns(research):
    _state_rows(research, "  - id: other\n    source: code/train.py:train_one_epoch\n")
    r = chk(research)
    assert r.fails == 0 and "algorithms.other 登记了但" in r.out, r.out


def test_missing_source_function_fails(research):
    edit(research / "research-state.yaml", "train.py:train_one_epoch", "train.py:train_nothing")
    r = chk(research)
    assert r.fails >= 1 and "没有函数 train_nothing" in r.out, r.out


def test_missing_source_file_fails(research):
    edit(research / "research-state.yaml", "code/train.py:train_one_epoch", "code/gone.py:train_one_epoch")
    r = chk(research)
    assert r.fails >= 1 and "gone.py 不存在" in r.out, r.out


def test_class_method_source_is_found(research):
    write(research / "code" / "trainer.py", "class T:\n    def fit(self, loader):\n        for b in loader:\n            self.step(b)\n")
    node, lines, err = ma.load_func(str(research), "code/trainer.py:T.fit")
    assert err is None and node.name == "fit"
    assert ma.load_func(str(research), "code/trainer.py:fit")[0].name == "fit"          # unique bare name is found too
    assert "没有函数" in ma.load_func(str(research), "code/trainer.py:T.nope")[2]


# ------------------------------------------------------------------ check 4: symbols
def test_unknown_code_identifier_warns(research):
    edit(_p(research, TEX), "\\State $h \\gets \\emptyset$", "\\State $h \\gets \\emptyset$ using \\texttt{warmup\\_steps}")
    r = chk(research)
    assert r.fails == 0 and "伪代码里的 warmup_steps 在 source 函数里找不到" in r.out, r.out


def test_known_identifiers_do_not_warn(research):
    edit(_p(research, TEX), "\\State $h \\gets \\emptyset$", "\\State $h \\gets \\emptyset$ using \\texttt{regression\\_loss}, \\texttt{loader}, \\texttt{epochs}")
    r = chk(research)
    assert r.fails == 0 and "[WARN]" not in r.out, r.out


def test_undefined_greek_symbol_warns_but_defined_ones_do_not(research):
    edit(_p(research, TEX), "\\beta\\, L_{dom}", "\\gamma\\, L_{dom}")
    r = chk(research)
    assert "伪代码里的 \\gamma 在 source 函数里找不到" in r.out, r.out
    edit(_p(research, TEX), "\\State $h \\gets \\emptyset$", "\\State $\\gamma \\gets 0$\n\\State $h \\gets \\emptyset$")     # assigned in the block: defined
    assert "伪代码里的 \\gamma" not in chk(research).out


# ------------------------------------------------------------------ check 5: values vs the reference run
def test_require_value_mismatch_fails(research):
    edit(_p(research, TEX), "$\\beta = 0.1$", "$\\beta = 0.5$")
    r = chk(research)
    assert r.fails == 1 and "伪代码里 \\beta = 0.5 但 ref run 的 beta = 0.1" in r.out, r.out


def test_require_value_falls_back_to_the_reference_runs_args_json(research):
    edit(_p(research, TEX), "$K = 3$", "$K = 5$")              # epochs is not in bundle.matrix.ref.args: runs/ours*/args.json says 3
    r = chk(research)
    assert r.fails == 1 and "ref run 的 epochs = 3" in r.out and "runs/ours_s0/args.json" in r.out, r.out


def test_require_value_in_scientific_notation_and_unknown_key(research):
    edit(research / "research-state.yaml", "K: epochs}", 'K: epochs, "\\\\eta": lr}')
    edit(_p(research, TEX), "$K = 3$", "$K = 3$, $\\eta = 10^{-4}$")
    r = chk(research)
    assert r.fails == 0 and "ref run 里没有可比的 lr" in r.out, r.out                # lr is not in the reference run: cannot compare, says so
    assert ma.parse_num("10^{-4}") == 1e-4 and ma.parse_num("5 \\times 10^{-4}") == 5e-4 and ma.parse_num("1e-4") == 1e-4 and ma.parse_num(".5") == 0.5


# ------------------------------------------------------------------ checks 6 and 7: shape, result numbers
def test_fewer_loops_than_the_function_warns(research):
    edit(_p(research, TEX), "\\For{$k = 1, \\ldots, K$}", "\\State repeat $K$ times")
    edit(_p(research, TEX), "\\EndFor\n", "")
    r = chk(research)
    assert r.fails == 0 and "前两层有 1 个循环，伪代码只有 0 个" in r.out, r.out


def test_more_than_30_lines_warns(research):
    edit(_p(research, TEX), "\\State \\Return $h$", "\\State \\Return $h$\n" + "\\State $h \\gets h$\n" * 25)
    r = chk(research)
    assert r.fails == 0 and "> 30" in r.out, r.out


def test_result_numbers_in_a_state_line_warn(research):
    edit(_p(research, TEX), "\\State \\Return $h$", "\\State report RMSE $0.202$ and the 19.2\\% gain\n\\State \\Return $h$")
    r = chk(research)
    assert r.fails == 0 and "结果数字 ['0.202', '19.2']" in r.out, r.out
    assert ma.sig_digits("0.202") == 3 and ma.sig_digits("1000") == 1 and ma.sig_digits("0.05") == 1 and ma.sig_digits("1024") == 4


def test_hyperparameter_numbers_are_not_result_numbers(research):
    edit(_p(research, TEX), "\\State \\Return $h$", "\\State $\\epsilon \\gets 10^{-8}$, batch $64$, $\\beta_1 = 0.9$\n\\State \\Return $h$")
    assert "结果数字" not in chk(research).out


def test_many_ifs_but_no_if_in_the_block_warns(research):
    write(research / "code" / "ifs.py", "def g(a, b, c):\n    for i in range(3):\n        if a:\n            pass\n        if b:\n            pass\n        if c:\n            pass\n")
    edit(research / "research-state.yaml", "train.py:train_one_epoch", "ifs.py:g")
    t = read(_p(research, TEX))
    write(_p(research, TEX), re.sub(r"\\If\{.*?\\EndIf\n", "", t, flags=re.S))
    r = chk(research)
    assert "前两层有 3 个 if，伪代码一个 \\If 都没有" in r.out, r.out


def test_unparsable_source_fails(research):
    write(research / "code" / "bad.py", "def (:\n")
    edit(research / "research-state.yaml", "train.py:train_one_epoch", "bad.py:g")
    r = chk(research)
    assert r.fails >= 1 and "解析失败" in r.out, r.out


def test_label_without_alg_prefix_warns(research):
    edit(_p(research, TEX), "\\label{alg:train}", "\\label{train}")
    edit(_p(research, MAIN), "\\ref{alg:train}", "\\ref{train}")
    r = chk(research)
    assert r.fails == 0 and "label 惯例写成 alg:xxx" in r.out, r.out


# ------------------------------------------------------------------ tex_to_md
def test_tex_to_md_converts_the_block_and_the_reference(research):
    edit(_p(research, MAIN), "\\section{Conclusion}", "See also \\autoref{alg:train} and Alg.~\\ref{alg:train}.\n\n\\section{Conclusion}")
    r = run("tex_to_md.py", "paper/latex/main.tex", ".", "--bib", "paper/refs.bib", cwd=research)
    assert r.returncode == 0 and "1 algorithms" in r.out, r.out
    md = read(research / "paper" / "manuscript.md")
    assert "**Algorithm 1.** Training with the domain-adversarial and the consistency term." in md
    assert "```latex\n\\Require encoder" in md and "\\State \\Return $h$\n```" in md and "\\begin{algorithmic}" not in md and "@@ALG" not in md
    assert "Algorithm 1 summarises the training procedure." in md and "See also Algorithm 1 and Algorithm 1." in md and "\\ref{alg:train}" not in md
    assert md.index("**Algorithm 1.**") < md.index("```latex") < md.index("**Fig. 1.**")
    f = run("gate_check.py", "floats", "--project", ".", "--manuscript", "paper/manuscript.md", cwd=research)
    assert "algorithms ['1']" in f.out and f.fails == 0, f.out


def test_tex_to_md_numbers_algorithms_in_document_order(research):
    write(research / "paper" / "latex" / "alg_two.tex", "\\begin{algorithm*}[t]\n\\caption{Second.}\n\\label{alg:two}\n\\begin{algorithmic}\n\\State $x \\gets 1$\n\\end{algorithmic}\n\\end{algorithm*}\n")
    edit(_p(research, MAIN), "\\input{alg_train}", "\\input{alg_train}\n\\input{alg_two}\nAlgorithm~\\ref{alg:two} is the second.")
    run("tex_to_md.py", "paper/latex/main.tex", ".", "--bib", "paper/refs.bib", cwd=research)
    md = read(research / "paper" / "manuscript.md")
    assert "**Algorithm 2.** Second." in md and "Algorithm 2 is the second." in md and md.index("**Algorithm 1.**") < md.index("**Algorithm 2.**")


# ------------------------------------------------------------------ readability / numbers do not see the block
def _without_algorithm(md):
    md = re.sub(r"\*\*Algorithm 1\.\*\*[^\n]*\n\s*```latex.*?```\n", "", md, flags=re.S)
    return md.replace(" Algorithm 1 summarises the training procedure; the two regularizers enter only when their weights are positive.", "")


def test_readability_ignores_algorithm_caption_and_block(research):
    import readability_check as rc
    md = read(research / "paper" / "manuscript.md").replace("\r\n", "\n")
    noisy = md.replace("```latex\n", "```latex\n\\State report RMSE $0.202$ ; 0.303 ; 19.2 ; 7 ; 8 ; 9 ; 10 ; 11 ; 12 ; 13 ; 14 ; 15 words words words words words\n", 1)
    noisy = noisy.replace("**Algorithm 1.** Training with the domain-adversarial and the consistency term.", "**Algorithm 1.** Training with 1.1 and 2.2 and 3.3 and 4.4 and 5.5 and 6.6 over 77 steps, 88 steps, 99 steps; yes; yes; yes.")
    a, b = rc.analyze(md, [], "cs_journal"), rc.analyze(noisy, [], "cs_journal")
    for k in ("body_words", "body_numbers_per1k", "body_semicolons_per1k", "body_sent_len_mean", "body_long_sent_share"):
        assert a[k] == b[k], (k, a[k], b[k])


def test_numbers_gate_strips_the_fenced_block(research):
    import gate_check as gc
    md = read(research / "paper" / "manuscript.md")
    s = gc.strip_code_math(md)
    assert "\\Require" not in s and "\\For" not in s
    r = run("gate_check.py", "numbers", "--project", ".", "--manuscript", "paper/manuscript.md", cwd=research)
    assert r.fails == 0, r.out


# ------------------------------------------------------------------ G6 floats
def test_floats_unreferenced_algorithm_fails(research):
    edit(research / "paper" / "manuscript.md", " Algorithm 1 summarises the training procedure; the two regularizers enter only when their weights are positive.", "")
    r = run("gate_check.py", "floats", "--project", ".", cwd=research)
    assert r.fails == 1 and "alg 无人引用: ['1']" in r.out, r.out


def test_floats_passes_and_names_the_algorithm(research):
    r = run("gate_check.py", "floats", "--project", ".", cwd=research)
    assert r.fails == 0 and "algorithms ['1']" in r.out.replace('"', "'"), r.out


def test_floats_reference_to_someone_elses_algorithm_is_a_warning(research):
    edit(research / "paper" / "manuscript.md", "Algorithm 1 summarises", "Algorithm 2 of [1] and Algorithm 1 summarises")
    r = run("gate_check.py", "floats", "--project", ".", cwd=research)
    assert r.fails == 0 and "[WARN] floats: alg 引用了本稿没有的" in r.out, r.out


# ------------------------------------------------------------------ G6c norms
NORMS = "# test norms\nfamily,venue,n,n_method_papers,share_with_algorithm,p50_count,p90_count,max_count\ncs_journal,ALL,100,90,0.6,1,2,4\n"


def _shape(project, norms=NORMS):
    write(project / "norms.csv", norms)
    return run("shape_check.py", "--algorithm-norms", "norms.csv", cwd=project)


def test_shape_warns_when_the_family_has_pseudocode_and_the_paper_does_not(research):
    write(research / "paper" / "manuscript.md", _without_algorithm(read(research / "paper" / "manuscript.md")))
    r = _shape(research)
    assert "[WARN] shape: 该家族 60% 的方法论文有伪代码（n=90），本文没有" in r.out, r.out


def test_shape_info_line_when_the_manuscript_has_one(research):
    r = _shape(research)
    assert "[INFO] shape: Algorithm 块 1 个；cs_journal 方法论文里 60% 有伪代码" in r.out and "该家族" not in r.out, r.out


def test_shape_warns_above_p90(research):
    md = read(research / "paper" / "manuscript.md")
    extra = "".join(f"\n**Algorithm {i}.** Extra {i}.\n\n```latex\n\\State $x \\gets {i}$\n```\n" for i in (2, 3, 4))
    write(research / "paper" / "manuscript.md", md.replace("\n## 4. Experiments", extra + "\n## 4. Experiments", 1))
    assert "4 个 Algorithm 块 > 该家族有伪代码的论文的 p90 (2" in _shape(research).out


def test_shape_is_silent_without_norms_or_when_the_family_rarely_has_pseudocode(research, tmp_path):
    write(research / "paper" / "manuscript.md", _without_algorithm(read(research / "paper" / "manuscript.md")))
    r = run("shape_check.py", "--algorithm-norms", str(tmp_path / "missing.csv"), cwd=research)
    assert "Algorithm" not in r.out and "伪代码" not in r.out
    r = _shape(research, NORMS.replace(",0.6,", ",0.2,"))
    assert "[WARN] shape: 该家族" not in r.out


def test_shape_does_not_count_pseudocode_words_as_prose(research):
    base = run("shape_check.py", "--algorithm-norms", "none.csv", cwd=research).out.split("正文 ≈ ")[1].split(" ")[0]
    md = read(research / "paper" / "manuscript.md")
    write(research / "paper" / "manuscript.md", md.replace("```latex\n", "```latex\n" + "\\State many many words that are not prose at all in the block " * 40 + "\n", 1))
    assert run("shape_check.py", "--algorithm-norms", "none.csv", cwd=research).out.split("正文 ≈ ")[1].split(" ")[0] == base


# ------------------------------------------------------------------ G6b item
def test_draft_plan_has_an_algorithm_item_that_needs_a_reference_in_the_method_text(research):
    r = run("draft_plan.py", "plan", "--project", ".", cwd=research)
    assert "方法节正文要引用 Algorithm 1（train）" in r.out, r.out
    assert run("draft_plan.py", "check", "--project", ".", cwd=research).fails == 0
    edit(research / "paper" / "manuscript.md", " Algorithm 1 summarises the training procedure; the two regularizers enter only when their weights are positive.", "")
    r = run("draft_plan.py", "check", "--project", ".", cwd=research)           # the caption line `**Algorithm 1.**` is still there: it is not a reference
    assert r.fails == 1 and "方法节正文要引用 Algorithm 1" in r.out, r.out


def test_draft_plan_has_no_algorithm_item_without_state_rows(research):
    s = read(research / "research-state.yaml")
    write(research / "research-state.yaml", s[:s.index("\nalgorithms:")] + "\n")
    assert "Algorithm" not in run("draft_plan.py", "plan", "--project", ".", cwd=research).out


# ------------------------------------------------------------------ calibrate
def _pdf(path, lines):
    import fitz
    path.parent.mkdir(parents=True, exist_ok=True)
    d = fitz.open(); pg = d.new_page(); y = 72
    for ln in lines:
        pg.insert_text((72, y), ln, fontsize=11); y += 16
    d.save(str(path)); d.close()


def test_calibrate_counts_algorithm_captions_among_method_papers(tmp_path):
    root = tmp_path / "papers"
    _pdf(root / "CVPR" / "2024" / "a.pdf", ["1. Introduction", "We propose X.", "3. Method", "Algorithm 1: Foo training", "Input: data", "Algorithm 2 Bar inference", "Algorithm 1 shows the loop in detail."])
    _pdf(root / "CVPR" / "2024" / "b.pdf", ["1. Introduction", "Text only.", "3. Method", "We describe the approach. See Algorithm 1 of the appendix."])
    _pdf(root / "CVPR" / "2024" / "c.pdf", ["1. Introduction", "A dataset paper.", "Results", "Table 1"])
    _pdf(root / "CVPR" / "2022" / "old.pdf", ["3. Method", "Algorithm 1: too old to be sampled"])
    out = tmp_path / "norms.csv"
    r = run("make_algorithm.py", "calibrate", "--papers", root, "--out", out, "--per-venue", "10", "--workers", "1", "--per-paper", tmp_path / "pp.csv", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    txt = read(out)
    assert txt.startswith("# algorithm norms:") and "seed 20261023" in txt
    rows = list(csv.DictReader(io.StringIO("\n".join(l for l in txt.splitlines() if not l.startswith("#")))))
    cvpr = next(x for x in rows if x["venue"] == "CVPR")
    assert (cvpr["family"], cvpr["n"], cvpr["n_method_papers"]) == ("cs_conf", "3", "2")        # c.pdf has no Method heading; 2022 is out of range
    assert float(cvpr["share_with_algorithm"]) == 0.5 and float(cvpr["p50_count"]) == 2 and cvpr["max_count"] == "2"     # a.pdf: Algorithm 1 and 2 (the prose "Algorithm 1 shows" is not a caption); b.pdf: none
    allrow = next(x for x in rows if x["venue"] == "ALL")
    assert allrow["family"] == "cs_conf" and allrow["n"] == "3" and not any(x["family"] == "nature" for x in rows)
    pp = list(csv.DictReader(io.open(tmp_path / "pp.csv", encoding="utf-8")))
    assert {x["pdf"].split("/")[-1]: x["algs"] for x in pp} == {"a.pdf": "2", "b.pdf": "0", "c.pdf": "0"}


def test_calibrate_file_is_what_shape_check_reads():
    """the shipped references/algorithm-norms.csv parses and has an ALL row per family"""
    p = ma.NORMS_CSV
    rows = list(csv.DictReader(io.StringIO("\n".join(l for l in io.open(p, encoding="utf-8").read().splitlines() if not l.startswith("#")))))
    assert {x["family"] for x in rows if x["venue"] == "ALL"} == {"cs_conf", "cs_journal", "nature"}
    assert all(0 <= float(x["share_with_algorithm"]) <= 1 for x in rows)
