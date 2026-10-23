# -*- coding: utf-8 -*-
"""LaTeX manuscript -> topic-to-paper inputs, so .tex projects can enter the gates without a Markdown mirror.

  python tex_to_md.py main.tex out_dir [--bib refs.bib] [--textwidth-mm 178]

Writes out_dir/paper/manuscript.md with:
  - \\section/\\subsection -> ## / ###; \\paragraph{X} \\subparagraph{X} -> run-in **X**; \\par -> paragraph break; \\parbox{w}{t} -> t
  - every figure/table environment -> "**Fig. N.** caption" / "**Table N.** caption", numbered in document order
    (starred and sub-float-free; \\label{...} recorded so \\ref/\\autoref/\\cref/\\Cref resolve to the SAME numbers)
  - tabular rows -> markdown rows (cells split on &, \\\\ ends a row; \\multicolumn collapsed to its text)
  - \\cite{a,b} -> [n] numbered by first appearance; bib keys mapped and written to out_dir/paper/refs.bib (copied/trimmed from --bib)
  - \\includegraphics width -> figures.csv print_width_mm (fraction × --textwidth-mm; \\columnwidth taken as textwidth/2 for two-column classes)
  - comments, \\begin{document} preamble, bibliography block stripped; math left inline between $...$
It is a text-level converter: it does not run LaTeX, so macros defined in the preamble are not expanded."""
import argparse, io, os, re, csv, shutil
import sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

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

HEAD_RE = re.compile(r"\\(subsubsection|subsection|section|subparagraph|paragraph)\*?\s*(?:\[[^\]]*\])?\s*\{")

def headings(body):
    """\\section/\\subsection/\\subsubsection{T} -> ## / ### / ####; \\paragraph{T} / \\subparagraph{T} -> **T** run-in head. Brace-matched, so titles may nest macros;
    built by concatenation, never as a re.sub replacement string (user text in a replacement string has its backslashes interpreted)."""
    out, i = [], 0
    while True:
        m = HEAD_RE.search(body, i)
        if not m: out.append(body[i:]); return "".join(out)
        out.append(body[i:m.start()]); title, i = balanced(body, m.end() - 1); t = re.sub(r"\\label\{[^}]*\}", "", unbrace(title)).strip()
        run_in = m.group(1).endswith("paragraph")
        out.append({"section": "\n\n## ", "subsection": "\n\n### ", "subsubsection": "\n\n#### "}.get(m.group(1), "\n\n**") + t + ("**" if run_in else "\n\n"))

def parbox(body):
    """\\parbox[pos]{width}{text} -> text (the box is layout, the text is prose); brace-matched."""
    out, i = [], 0
    pat = re.compile(r"\\parbox\s*(?:\[[^\]]*\]\s*)*\{")
    while True:
        m = pat.search(body, i)
        if not m: out.append(body[i:]); return "".join(out)
        out.append(body[i:m.start()]); _, j = balanced(body, m.end() - 1)
        while j < len(body) and body[j] in " \t\n": j += 1
        if j < len(body) and body[j] == "{": txt, i = balanced(body, j); out.append(txt)
        else: i = j

def bib_field(entry, name):
    """value of `name = {...}` / "..." / bare token in a bib entry (brace-matched; single-line Crossref/Zotero entries included), else ''."""
    m = re.search(r"[\s,]" + name + r"\s*=\s*", entry, re.I)
    if not m: return ""
    i = m.end()
    if i < len(entry) and entry[i] == "{": return balanced(entry, i)[0]
    if i < len(entry) and entry[i] == '"':
        j = entry.find('"', i + 1); return entry[i + 1:j if j > 0 else len(entry)]
    t = re.match(r"[^,}\s]+", entry[i:]); return t.group(0) if t else ""

def grab_cmd(s, cmd):
    m = re.search(r"\\" + cmd + r"\s*(?:\[[^\]]*\])?\s*\{", s)
    if not m: return ""
    body, _ = balanced(s, m.end() - 1)
    return body

def tabular_body(inner):
    """body of the first tabular/tabular* in inner, with the (possibly nested, e.g. p{0.62\\columnwidth} or @{}) preamble consumed by brace matching."""
    m = re.search(r"\\begin\{tabular\*?\}", inner)
    if not m: return None
    i = m.end()
    while i < len(inner) and inner[i] in " \t\n": i += 1
    if i < len(inner) and inner[i] == "{":           # tabular*: first group is the width, second the preamble
        _, i = balanced(inner, i)
        j = i
        while j < len(inner) and inner[j] in " \t\n": j += 1
        if j < len(inner) and inner[j] == "{": _, i = balanced(inner, j)
    e = re.search(r"\\end\{tabular\*?\}", inner[i:])
    return inner[i:i + e.start()] if e else inner[i:]

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

def expand_inputs(path, seen=None):
    """\\input{x} / \\include{x} -> contents of x(.tex) next to the including file, recursively; comments stripped first."""
    seen = seen if seen is not None else set(); path = os.path.abspath(path); seen.add(path)
    text = strip_comments(io.open(path, encoding="utf-8", errors="replace").read()); base = os.path.dirname(path)
    def sub(m):
        name = m.group(1).strip(); p = next((c for c in (os.path.join(base, name), os.path.join(base, name + ".tex")) if os.path.isfile(c)), None)
        if p is None or os.path.abspath(p) in seen: return "" if p else m.group(0)
        return "\n" + expand_inputs(p, seen) + "\n"
    return re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", sub, text)

def class_widths(src):
    """(textwidth_mm, two_column) from references/latex-templates.csv for the documentclass / style file, else None."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "latex-templates.csv")
    if not os.path.exists(p): return None
    m = re.search(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", src); cls = m.group(2).strip() if m else ""; opts = (m.group(1) or "") if m else ""
    pkgs = [x.strip() for g in re.findall(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", src) for x in g.split(",")]
    for r in csv.DictReader(io.open(p, encoding="utf-8-sig")):
        sty = [s for s in r.get("sty", "").split("|") if s]
        if cls in r["documentclass"].split("|") and (not sty or any(x.startswith(s) for s in sty for x in pkgs)):
            return float(r["full_width_mm"]), (r["twocolumn"].lower() == "yes" or "twocolumn" in opts)
    return None

def convert(tex_path, out_dir, bib_path, tw_mm):
    src = expand_inputs(tex_path)
    cw = class_widths(src)
    if tw_mm is None:
        tw_mm = cw[0] if cw else 178.0
        print(f"textwidth {tw_mm} mm" + (" (references/latex-templates.csv)" if cw else " (default; pass --textwidth-mm or add the class to latex-templates.csv)"))
    two_col = (cw[1] if cw else False) or bool(re.search(r"\\documentclass\[[^\]]*(?:journal|twocolumn|conference)[^\]]*\]", src)) or "IEEEtran" in src
    body = src.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    body = re.sub(r"\\(?:maketitle|tableofcontents|newpage|clearpage|IEEEpeerreviewmaketitle|IEEEdisplaynontitleabstractindextext)(?![A-Za-z@])", "", body)
    body = re.sub(r"\\(?:begin|end)\{frontmatter\}", "", body)
    body = re.sub(r"\\(?:author|affiliation|address|cortext|ead|fntext|tnotetext|title|IEEEauthorblockN|IEEEauthorblockA|thanks)\s*(?:\[[^\]]*\])?\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", body)
    body = re.sub(r"\\begin\{keyword\}(.*?)\\end\{keyword\}", lambda m: "\n\nKeywords: " + re.sub(r"\s*\\sep\b\s*", "; ", m.group(1)).strip() + "\n\n", body, flags=re.S)
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
        caps = []
        for cm in re.finditer(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", inner):
            caps.append(unbrace(balanced(inner, cm.end() - 1)[0]).strip())
        subcaps = [unbrace(x).strip() for x in re.findall(r"\\subfloat\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]", inner)]
        if len(caps) > 1: subcaps = caps[:-1]
        cap = (caps[-1] if caps else "") + ("".join(f" ({chr(97 + i)}) {re.sub(chr(92) + chr(92) + "label\\{[^}]*\\}", "", c).strip()}" for i, c in enumerate(subcaps)) if subcaps else "")
        for lm in re.finditer(r"\\label\{([^}]+)\}", inner): labels[lm.group(1)] = f"{tag} {n}"
        out = f"\n\n**{tag} {n}.** {cap}\n\n"
        if is_tab:
            tb = tabular_body(inner)
            if tb is not None: out += tabular_to_md(tb) + "\n\n"
        # a graphic inside \begin{subfigure}{0.48\textwidth} is 0.48 of the base, whatever its own width= says relative to \linewidth
        sub_scale = {}
        for sm in re.finditer(r"\\begin\{subfigure\}(?:\[[^\]]*\])?\{\s*([\d.]*)\s*\\(textwidth|linewidth|columnwidth)\s*\}(.*?)\\end\{subfigure\}", inner, re.S):
            sfrac = float(sm.group(1)) if sm.group(1) else 1.0; sbase = tw_mm / 2 if (sm.group(2) == "columnwidth" and two_col) else tw_mm
            for g in re.finditer(r"\\includegraphics", sm.group(3)): sub_scale[sm.start(3) + g.start()] = sfrac * sbase
        for gm in re.finditer(r"\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", inner):
            opt, fn = gm.group(1) or "", gm.group(2)
            wm = re.search(r"width\s*=\s*([\d.]*)\s*\\(textwidth|linewidth|columnwidth)", opt)
            frac = float(wm.group(1)) if wm and wm.group(1) else 1.0
            if gm.start() in sub_scale:
                wmm = frac * sub_scale[gm.start()] if wm else sub_scale[gm.start()]
            else:
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
    body = headings(body)   # \section.. -> ##.. ; \paragraph{X} -> run-in **X**
    body = re.sub(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", lambda m: "\n\n## Abstract\n\n" + m.group(1).strip() + "\n\n", body, flags=re.S)
    kw = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}|\\keywords\{([^}]*)\}", body, re.S)
    if kw: body = body.replace(kw.group(0), "\n\nKeywords: " + (kw.group(1) or kw.group(2)).strip() + "\n\n")
    body = re.sub(r"\\bibliography\{[^}]*\}|\\bibliographystyle\{[^}]*\}|\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "", body, flags=re.S)
    body = re.sub(r"\\begin\{(itemize|enumerate)\}(.*?)\\end\{\1\}", lambda m: re.sub(r"\\item\s*", "\n- ", m.group(2)), body, flags=re.S)
    body = parbox(body); body = re.sub(r"\\par(?![A-Za-z@])", "\n\n", body)   # \par = paragraph break; the lookahead keeps \paragraph / \parskip / \partial from being eaten as "\par" + text ("agraph{Setup.}")
    body = re.sub(r"\\(?:vspace|hspace|setlength|footnotesize|small|centering|noindent|renewcommand|newcommand)(?![A-Za-z@])\*?(?:\{[^}]*\})*(?:\[[^\]]*\])?", "", body)
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
            t = re.sub(r"\s+", " ", bib_field(e, "title")).replace("{", "").replace("}", "").strip()   # the old regex needed a newline after title=: single-line Crossref/Zotero entries fell back to the bare key
            md_refs.append(f"[{i}] {t or k} (bibkey {k})")
        else:
            md_refs.append(f"[{i}] (bib key not found: {k})"); bib_out.append(f"@misc{{r{i},\n  title = {{{k}}},\n}}")
    os.makedirs(os.path.join(out_dir, "paper"), exist_ok=True)
    body = re.sub(r"\$\s*([+\-\u2212]?\d+(?:\.\d+)?)\s*\$", r"\1", body)   # $-37$ is a number, not a formula: keep it visible to the numbers gate
    md = f"# {title}\n\n{body.strip()}\n\n## References\n\n" + "\n".join(md_refs) + "\n"
    io.open(os.path.join(out_dir, "paper", "manuscript.md"), "w", encoding="utf-8").write(md)
    out_bib = os.path.join(out_dir, "paper", "refs.bib")
    if bib_path and os.path.exists(bib_path) and os.path.abspath(bib_path) == os.path.abspath(out_bib):
        print(f"refs.bib: {bib_path} is the project bib, left untouched (keys keep their names)")
    else:
        io.open(out_bib, "w", encoding="utf-8").write("\n\n".join(bib_out) + "\n")
    texdir = os.path.dirname(os.path.abspath(tex_path))
    gp = re.search(r"\\graphicspath\s*\{((?:\s*\{[^}]*\}\s*)+)\}", src); gpaths = re.findall(r"\{([^}]*)\}", gp.group(1)) if gp else []
    fcsv = os.path.join(out_dir, "figures.csv"); hdr = ["file", "print_width_mm", "source_data", "inspected", "issues"]
    old = {}
    if os.path.exists(fcsv):
        for r in csv.DictReader(io.open(fcsv, encoding="utf-8-sig")): old[os.path.normpath(r["file"])] = r
    new_rows = []
    for fn, wmm, n in fig_rows:
        cands = [os.path.join(b, fn + e) for b in [texdir] + [os.path.join(texdir, g) for g in gpaths] for e in ("", ".pdf", ".png")]
        p = next((c for c in cands if os.path.isfile(c)), os.path.join(texdir, fn))
        rel = os.path.relpath(p, out_dir).replace("\\", "/")
        prev = old.get(os.path.normpath(rel), {})
        new_rows.append({"file": rel, "print_width_mm": wmm, "source_data": prev.get("source_data", ""), "inspected": prev.get("inspected", "no"), "issues": prev.get("issues") or f"Fig. {n}"})
    seen = {os.path.normpath(r["file"]) for r in new_rows}
    keep = [r for k, r in old.items() if k not in seen]      # figures registered earlier but not (yet) in the tex stay registered
    with open(fcsv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr); w.writeheader()
        for r in new_rows + keep: w.writerow({k: r.get(k, "") for k in hdr})
    missing = sum(1 for r in md_refs if "not found" in r)
    print(f"{os.path.basename(tex_path)}: {fig_n} figures, {tab_n} tables, {len(order)} cited keys ({missing} missing from bib), {len(labels)} labels -> {out_dir}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tex"); ap.add_argument("out_dir"); ap.add_argument("--bib", default=""); ap.add_argument("--textwidth-mm", type=float, default=None, help="default: from references/latex-templates.csv for the documentclass, else 178")
    a = ap.parse_args(); convert(a.tex, a.out_dir, a.bib, a.textwidth_mm)
