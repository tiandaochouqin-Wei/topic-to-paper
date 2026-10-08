# -*- coding: utf-8 -*-
"""LaTeX manuscript -> topic-to-paper inputs, so .tex projects can enter the gates without a Markdown mirror.

  python tex_to_md.py main.tex out_dir [--bib refs.bib] [--textwidth-mm 178]

Writes out_dir/paper/manuscript.md with:
  - \\section/\\subsection -> ## / ###
  - every figure/table environment -> "**Fig. N.** caption" / "**Table N.** caption", numbered in document order
    (starred and sub-float-free; \\label{...} recorded so \\ref/\\autoref/\\cref/\\Cref resolve to the SAME numbers)
  - tabular rows -> markdown rows (cells split on &, \\\\ ends a row; \\multicolumn collapsed to its text)
  - \\cite{a,b} -> [n] numbered by first appearance; bib keys mapped and written to out_dir/paper/refs.bib (copied/trimmed from --bib)
  - \\includegraphics width -> figures.csv print_width_mm (fraction × --textwidth-mm; \\columnwidth taken as textwidth/2 for two-column classes)
  - comments, \\begin{document} preamble, bibliography block stripped; math left inline between $...$
It is a text-level converter: it does not run LaTeX, so macros defined in the preamble are not expanded."""
import argparse, io, os, re, csv, shutil

def strip_comments(s):
    return re.sub(r"(?<!\\)%[^\n]*", "", s)

def unbrace(s):
    """\\textbf{x}, \\emph{x}, \\mathrm{x} -> x (one level, repeated)."""
    for _ in range(4):
        s = re.sub(r"\\(?:textbf|textit|emph|textsc|texttt|mathrm|mathbf|underline|mbox|hbox|text)\{([^{}]*)\}", r"\1", s)
    return s

def balanced(s, i):
    """return the content of the {...} group starting at s[i] == '{' and the index after it."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{": depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0: return s[i + 1:j], j + 1
    return s[i + 1:], len(s)

def grab_cmd(s, cmd):
    m = re.search(r"\\" + cmd + r"\s*(?:\[[^\]]*\])?\s*\{", s)
    if not m: return ""
    body, _ = balanced(s, m.end() - 1)
    return body

def tabular_to_md(body):
    body = re.sub(r"\\(?:toprule|midrule|bottomrule|hline|cline\{[^}]*\}|cmidrule(?:\([^)]*\))?\{[^}]*\})", "", body)
    body = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", body)
    body = re.sub(r"\\multirow\{\d+\}\{[^}]*\}\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", body)
    rows = [r for r in re.split(r"\\\\(?:\[[^\]]*\])?", body) if r.strip()]
    out = []
    for r in rows:
        cells = [unbrace(c).strip() for c in r.split("&")]
        if any(cells): out.append("| " + " | ".join(cells) + " |")
    if len(out) > 1: out.insert(1, "|" + "---|" * (out[0].count("|") - 1))
    return "\n".join(out)

def convert(tex_path, out_dir, bib_path, tw_mm):
    src = io.open(tex_path, encoding="utf-8", errors="replace").read()
    src = strip_comments(src)
    two_col = bool(re.search(r"\\documentclass\[[^\]]*(?:journal|twocolumn|conference)[^\]]*\]", src)) or "IEEEtran" in src
    body = src.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    body = re.sub(r"\\maketitle|\\tableofcontents|\\newpage|\\clearpage|\\IEEEpeerreviewmaketitle|\\IEEEdisplaynontitleabstractindextext", "", body)
    # --- citations -> [n]
    order = []
    def cite_sub(m):
        keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
        nums = []
        for k in keys:
            if k not in order: order.append(k)
            nums.append(str(order.index(k) + 1))
        return "[" + ",".join(nums) + "]"
    body = re.sub(r"\\(cite[pt]?|citep|citet|citealp|citeauthor)\*?\s*(?:\[[^\]]*\])*\s*\{([^}]+)\}", cite_sub, body)
    # --- floats: number in order, record labels
    labels = {}; fig_n = tab_n = 0; fig_rows = []
    def float_sub(m):
        nonlocal fig_n, tab_n
        env, inner = m.group(1), m.group(2)
        is_tab = env.startswith("table")
        if is_tab: tab_n += 1; n = tab_n; tag = "Table"
        else: fig_n += 1; n = fig_n; tag = "Fig."
        cap = unbrace(grab_cmd(inner, "caption")).strip()
        for lm in re.finditer(r"\\label\{([^}]+)\}", inner): labels[lm.group(1)] = f"{tag} {n}"
        out = f"\n\n**{tag} {n}.** {cap}\n\n"
        if is_tab:
            tm = re.search(r"\\begin\{tabular\*?\}(?:\{[^}]*\})+(.*?)\\end\{tabular\*?\}", inner, re.S)
            if tm: out += tabular_to_md(tm.group(1)) + "\n\n"
        for gm in re.finditer(r"\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", inner):
            opt, fn = gm.group(1) or "", gm.group(2)
            wm = re.search(r"width\s*=\s*([\d.]*)\s*\\(textwidth|linewidth|columnwidth)", opt)
            frac = float(wm.group(1)) if wm and wm.group(1) else 1.0
            base = tw_mm / 2 if (wm and wm.group(2) == "columnwidth" and two_col) else tw_mm
            wmm = frac * base if wm else tw_mm
            fig_rows.append((fn, round(wmm, 1), n))
        return out
    body = re.sub(r"\\begin\{(figure\*?|table\*?)\}(.*?)\\end\{\1\}", float_sub, body, flags=re.S)
    # --- refs to floats
    def ref_sub(m):
        key = m.group(2)
        return labels.get(key, m.group(0))
    body = re.sub(r"\\(ref|autoref|cref|Cref|eqref)\{([^}]+)\}", ref_sub, body)
    body = re.sub(r"(?:Fig\.|Figure|Table|Tab\.)~?\s*(Fig\. \d+|Table \d+)", r"\1", body)   # "Fig.~Fig. 3" -> "Fig. 3"
    # --- sections
    body = re.sub(r"\\section\*?\{([^}]*)\}", lambda m: "\n\n## " + unbrace(m.group(1)) + "\n\n", body)
    body = re.sub(r"\\subsection\*?\{([^}]*)\}", lambda m: "\n\n### " + unbrace(m.group(1)) + "\n\n", body)
    body = re.sub(r"\\subsubsection\*?\{([^}]*)\}", lambda m: "\n\n#### " + unbrace(m.group(1)) + "\n\n", body)
    body = re.sub(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", lambda m: "\n\n## Abstract\n\n" + m.group(1).strip() + "\n\n", body, flags=re.S)
    kw = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}|\\keywords\{([^}]*)\}", body, re.S)
    if kw: body = body.replace(kw.group(0), "\n\nKeywords: " + (kw.group(1) or kw.group(2)).strip() + "\n\n")
    body = re.sub(r"\\bibliography\{[^}]*\}|\\bibliographystyle\{[^}]*\}|\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "", body, flags=re.S)
    body = re.sub(r"\\begin\{(itemize|enumerate)\}(.*?)\\end\{\1\}", lambda m: re.sub(r"\\item\s*", "\n- ", m.group(2)), body, flags=re.S)
    body = re.sub(r"\\(?:vspace|hspace|setlength|footnotesize|small|centering|noindent|par|renewcommand|newcommand)\*?(?:\{[^}]*\})*(?:\[[^\]]*\])?", "", body)
    body = re.sub(r"\\(?:IEEEPARstart)\{([^}]*)\}\{([^}]*)\}", r"\1\2", body)
    body = unbrace(body)
    body = re.sub(r"~", " ", body); body = re.sub(r"\\&", "&", body); body = re.sub(r"\\%", "%", body); body = re.sub(r"\\_", "_", body)
    body = re.sub(r"[ \t]+\n", "\n", body); body = re.sub(r"\n{3,}", "\n\n", body)
    # pasted PDF text layers (figure axes, long runs of bare numbers) are not prose: flag lines that are mostly numbers
    pasted = [i + 1 for i, l in enumerate(body.splitlines()) if len(l) > 80 and len(re.findall(r"-?\d+\.\d+", l)) >= 8 and not l.strip().startswith("|")]
    if pasted:
        print(f"[WARN] {len(pasted)} 行像粘贴进来的 PDF 文本层（≥8 个小数、非表格）: 行 {pasted[:6]} —— 这些会被 scope/numbers/floats 关口当正文扫，应改成真正的 figure 环境或删除")
    title = unbrace(grab_cmd(src, "title")).strip() or os.path.basename(tex_path)
    # --- references list + refs.bib
    md_refs = []; bib_out = []
    entries = {}
    if bib_path and os.path.exists(bib_path):
        bt = io.open(bib_path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", bt, re.S):
            entries[m.group(2)] = m.group(0).strip()
    for i, k in enumerate(order, 1):
        e = entries.get(k)
        if e:
            e2 = re.sub(r"^@(\w+)\s*\{\s*[^,\s]+\s*,", r"@\1{r%d," % i, e, count=1)
            bib_out.append(e2)
            t = re.search(r"title\s*=\s*[{\"](.*?)[}\"]\s*,?\s*\n", e, re.S | re.I)
            md_refs.append(f"[{i}] {re.sub(r'\s+', ' ', t.group(1)).strip('{} ') if t else k} (bibkey {k})")
        else:
            md_refs.append(f"[{i}] (bib key not found: {k})"); bib_out.append(f"@misc{{r{i},\n  title = {{{k}}},\n}}")
    os.makedirs(os.path.join(out_dir, "paper"), exist_ok=True)
    md = f"# {title}\n\n{body.strip()}\n\n## References\n\n" + "\n".join(md_refs) + "\n"
    io.open(os.path.join(out_dir, "paper", "manuscript.md"), "w", encoding="utf-8").write(md)
    io.open(os.path.join(out_dir, "paper", "refs.bib"), "w", encoding="utf-8").write("\n\n".join(bib_out) + "\n")
    texdir = os.path.dirname(os.path.abspath(tex_path))
    with open(os.path.join(out_dir, "figures.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["file", "print_width_mm", "source_data", "inspected", "issues"])
        for fn, wmm, n in fig_rows:
            p = next((c for c in (os.path.join(texdir, fn), os.path.join(texdir, fn + ".pdf"), os.path.join(texdir, fn + ".png")) if os.path.exists(c)), fn)
            w.writerow([os.path.relpath(p, out_dir) if os.path.isabs(p) else p, wmm, "", "no", f"Fig. {n}"])
    missing = sum(1 for r in md_refs if "not found" in r)
    print(f"{os.path.basename(tex_path)}: {fig_n} figures, {tab_n} tables, {len(order)} cited keys ({missing} missing from bib), {len(labels)} labels -> {out_dir}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tex"); ap.add_argument("out_dir"); ap.add_argument("--bib", default=""); ap.add_argument("--textwidth-mm", type=float, default=178.0, help="IEEEtran journal 178; elsarticle 3p 17.5 cm = 175; Nature 180")
    a = ap.parse_args(); convert(a.tex, a.out_dir, a.bib, a.textwidth_mm)
