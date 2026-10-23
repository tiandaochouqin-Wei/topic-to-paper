# -*- coding: utf-8 -*-
"""G6d — LaTeX submission form. The manuscript is written in the venue's LaTeX template, every figure is a PDF referenced by
\\includegraphics, and a multi-panel figure is composed in LaTeX from one PDF per panel (subcaption / subfig), never pre-composited.

  python latex_check.py check    [--project .] [--tex paper/latex/main.tex] [--state research-state.yaml] [--figures figures.csv]
  python latex_check.py skeleton --venue "<journal>" [--family cs_conf|cs_journal|nature] [--out paper/latex] [--title T] [--force] [--project .]
  python latex_check.py figure   --panels figures/a.pdf,figures/b.pdf [--labels "A","B"] [--caption "..."] [--label fig:x] [--width 0.48]
                                 [--style auto|subcaption|subfig] [--env figure|figure*] [--tex-dir paper/latex] [--out figs/fig_x.tex] [--project .]
  python latex_check.py widths   [--tex paper/latex/main.tex | --class elsarticle --options preprint,12pt] [--project .]

Template knowledge (class, where to get it, column widths) lives in references/latex-templates.csv. `widths` measures the real
\\textwidth / \\columnwidth with pdflatex when it is installed, otherwise reports the table values (marked approx).

check:  documentclass / style file matches the venue's template (WARN; FAIL when state.target.latex_class disagrees);
        every \\includegraphics resolves to an existing file (FAIL) with the allowed extension, default pdf (FAIL);
        a figure with >= 2 graphics uses subfigure / subfloat (FAIL) and the package is loaded (FAIL);
        a caption with panel letters (a)(b) over a single graphic = pre-composited panels (FAIL);
        dangling \\ref (FAIL); float without \\label (WARN); graphic not in figures.csv or with another print width (WARN);
        bibliography file present (FAIL); paper/manuscript.md older than the .tex sources = gates ran on stale text (FAIL);
        leftover \\todo / \\fixme / \\hl in any \\input-ed source, or todonotes loaded without [disable] (FAIL);
        raw keys in the reference list: main.blg "didn't find a database entry", main.log "Citation .. undefined", a main.bbl \\bibitem whose body is just the key (FAIL; logs older than the sources are WARN, not trusted).
Exit = number of FAIL lines."""
import argparse, csv, io, os, re, shutil, subprocess, sys, tempfile
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
TEMPLATES_CSV = os.path.join(SKILL, "references", "latex-templates.csv")
PT_MM = 25.4 / 72.27
FAILS = 0


def _relpath(path, start=None):
    """os.path.relpath that falls back to the absolute path when the two are on different Windows drives (ValueError)"""
    try: return os.path.relpath(path) if start is None else os.path.relpath(path, start)
    except ValueError: return os.path.abspath(path)

def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] latex: {msg}")


def read(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


# ------------------------------------------------------------------ templates
def load_templates():
    return list(csv.DictReader(io.open(TEMPLATES_CSV, encoding="utf-8-sig"))) if os.path.exists(TEMPLATES_CSV) else []


def pick_template(venue, family, rows=None):
    """Row of latex-templates.csv for a venue name (word match on the venues column), else a family default."""
    rows = rows if rows is not None else load_templates()
    v = (venue or "").lower()
    for r in rows:
        for tok in r["venues"].split("|"):
            t = tok.strip().lower()
            if t and re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", v): return r
    fam = (family or "").lower()
    if fam == "nature": return next((r for r in rows if r["key"] == "nature"), None)
    if fam == "cs_journal" and re.search(r"ieee|transactions", v): return next((r for r in rows if r["key"] == "ieee"), None)
    return None


def two_column(row, opts, cls):
    if row and row.get("twocolumn", "").lower() == "yes": return True
    return "twocolumn" in (opts or "") or cls in ("IEEEtran", "acmart")


# ------------------------------------------------------------------ tex parsing
def strip_comments(s):
    return re.sub(r"(?<!\\)%[^\n]*", "", s)


def expand_inputs(path, seen=None, files=None):
    """Return (text with \\input/\\include expanded recursively, list of source files). Missing inputs are reported and left in place."""
    seen = seen if seen is not None else set(); files = files if files is not None else []
    path = os.path.abspath(path); seen.add(path); files.append(path)
    text = strip_comments(read(path)); base = os.path.dirname(path)
    def sub(m):
        name = m.group(1).strip()
        cand = [os.path.join(base, name), os.path.join(base, name + ".tex")]
        p = next((c for c in cand if os.path.isfile(c)), None)
        if p is None: say("FAIL", f"\\input{{{name}}} 找不到文件（相对 {_relpath(base)}）"); return m.group(0)
        if os.path.abspath(p) in seen: return ""
        inner, _ = expand_inputs(p, seen, files)
        return "\n" + inner + "\n"
    text = re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", sub, text)
    return text, files


def balanced(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{": depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0: return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def captions(inner):
    """all \\caption{...} bodies in order (balanced braces, optional short form skipped)"""
    out = []
    for m in re.finditer(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", inner):
        body, _ = balanced(inner, m.end() - 1); out.append(body)
    return out


def graphicspath(text):
    m = re.search(r"\\graphicspath\s*\{((?:\s*\{[^}]*\}\s*)+)\}", text)
    return re.findall(r"\{([^}]*)\}", m.group(1)) if m else []


EXTS = ("pdf", "png", "jpg", "jpeg", "eps", "tif", "tiff", "svg")


def resolve_graphic(fn, texdir, gpaths):
    """-> (absolute path or None, extension found or given)"""
    fn = fn.strip()
    bases = [texdir] + [os.path.join(texdir, g) for g in gpaths]
    has_ext = re.search(r"\.([A-Za-z]{2,4})$", fn)
    for b in bases:
        if has_ext:
            p = os.path.join(b, fn)
            if os.path.isfile(p): return p, has_ext.group(1).lower()
        else:
            for e in EXTS:
                p = os.path.join(b, fn + "." + e)
                if os.path.isfile(p): return p, e
    return None, (has_ext.group(1).lower() if has_ext else None)


def width_mm(opt, base_full, base_col, scale=1.0):
    """print width in mm from an includegraphics option string; None when no width= is given"""
    m = re.search(r"width\s*=\s*([\d.]*)\s*\\(textwidth|linewidth|columnwidth)", opt or "")
    if not m: return None
    frac = float(m.group(1)) if m.group(1) else 1.0
    base = base_col if m.group(2) == "columnwidth" else base_full
    return frac * base * scale


# ------------------------------------------------------------------ check
MARKER_CMD = re.compile(r"\\(todo|TODO|fixme|FIXME|missingfigure|hl)(?![A-Za-z@])")

def leftover_markers(text, pkgs_raw):
    """\\todo / \\fixme / \\hl left in an \\input-ed source (comments are already stripped), or todonotes loaded without `disable`."""
    hits = [(m.group(0), re.sub(r"\s+", " ", text[m.start():m.start() + 60])) for m in MARKER_CMD.finditer(text)]
    if hits: say("FAIL", f"{len(hits)} 处未清的批注命令（\\todo/\\fixme/\\hl 会把批注印进 PDF 或留在源里）：{[h[1] for h in hits[:4]]} —— 删掉或注释掉")
    bad = [o for o, names in pkgs_raw if "todonotes" in [n.strip() for n in names.split(",")] and "disable" not in o]
    if bad: say("FAIL", "加载了 todonotes 但没有 [disable] —— 提交前 \\usepackage[disable]{todonotes} 或直接去掉，否则批注会印进 PDF")
    elif not hits: say("PASS", "没有残留的 \\todo/\\fixme/\\hl，todonotes 未启用")

def bib_artifacts(tex, files):
    """Reference list built from keys instead of entries: bibtex `didn't find a database entry` (.blg), `Citation .. undefined` (.log), or a .bbl \\bibitem whose body is just the key.
    Only looks at artefacts that exist next to the main .tex; a build log older than the sources is reported as stale, not trusted."""
    stem = os.path.splitext(tex)[0]; newest = max(os.path.getmtime(f) for f in files); n_checked = n_bad = 0
    for ext, rx in ((".blg", r"I didn't find a database entry for \"([^\"]+)\""), (".log", r"Citation `([^']+)' (?:on page \d+ )?undefined")):
        p = stem + ext
        if not os.path.exists(p): continue
        n_checked += 1
        if os.path.getmtime(p) + 1 < newest: say("WARN", f"{os.path.basename(p)} 比 .tex 源旧，没有据此检查引用键：重编译一遍（pdflatex → bibtex → pdflatex ×2）"); continue
        keys = sorted(set(re.findall(rx, read(p))))
        if keys: n_bad += 1; say("FAIL", f"{os.path.basename(p)}: {len(keys)} 个引用键在 .bib 里找不到 / 编译后仍是未定义，参考文献表里会印出原始键: {keys[:8]}")
    p = stem + ".bbl"
    if os.path.exists(p):
        n_checked += 1; raw = []
        for m in re.finditer(r"\\bibitem\s*(?:\[[^\]]*(?:\[[^\]]*\][^\]]*)*\])?\s*\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})", read(p), re.S):
            key, body = m.group(1).strip(), re.sub(r"\\newblock|\\(?:em|emph|textit)\b|[{}\s]", "", m.group(2))
            if not body or body.lower() == key.lower().replace("_", "") or body.lower() == key.lower(): raw.append(key)
        if raw: n_bad += 1; say("FAIL", f"{os.path.basename(p)}: {len(raw)} 条 \\bibitem 正文只有键本身: {raw[:8]}")
    if n_checked and not n_bad: say("PASS", "编译产物（.blg/.log/.bbl）里没有未解析的引用键")

def check(a):
    root = os.path.abspath(a.project)
    st = {}
    sp = os.path.join(root, a.state)
    if os.path.exists(sp):
        try:
            import yaml; st = yaml.safe_load(read(sp)) or {}
        except Exception as ex: say("WARN", f"state 读取失败 {ex}")
    tgt = st.get("target") or {}
    latex_dir = tgt.get("latex_dir") or "paper/latex"
    tex = os.path.join(root, a.tex or os.path.join(latex_dir, "main.tex"))
    if not os.path.exists(tex): say("FAIL", f"{_relpath(tex, root)} 不存在"); return
    texdir = os.path.dirname(os.path.abspath(tex))
    text, files = expand_inputs(tex)
    rows = load_templates(); venue = tgt.get("venue") or ""; family = tgt.get("family") or ""
    tpl = pick_template(venue, family, rows)
    # --- class / style file
    m = re.match(r"", "")
    m = re.search(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", text)
    cls, opts = (m.group(2).strip(), m.group(1) or "") if m else ("", "")
    pkgs = [p.strip() for grp in re.findall(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", text) for p in grp.split(",")]
    if not cls: say("FAIL", "没有 \\documentclass")
    if tgt.get("latex_class") and cls and cls != tgt["latex_class"]:
        say("FAIL", f"documentclass {cls} ≠ state.target.latex_class {tgt['latex_class']}")
    if tpl:
        want_cls = tpl["documentclass"].split("|"); want_sty = [s for s in tpl.get("sty", "").split("|") if s]
        cls_ok = cls in want_cls
        sty_ok = (not want_sty) or any(p.startswith(s) for s in want_sty for p in pkgs)
        if cls_ok and sty_ok: say("PASS", f"documentclass {cls}" + (f" + {[p for p in pkgs if any(p.startswith(s) for s in want_sty)]}" if want_sty else "") + f" 与 {venue or tpl['key']} 的模板一致")
        else: say("WARN", f"documentclass {cls} / packages 不像 {venue or family} 的模板（期望 {want_cls}" + (f" + \\usepackage{{{want_sty}…}}" if want_sty else "") + f"；来源 {tpl['sty_source']}）")
    else: say("INFO", f"references/latex-templates.csv 没有 {venue!r} 的模板行；class={cls}（只查通用规则）")
    base_full = float(tpl["full_width_mm"]) if tpl else 170.0
    base_col = float(tpl["single_col_mm"]) if tpl else 85.0
    twocol = two_column(tpl, opts, cls)
    if not twocol: base_col = base_full   # \columnwidth == \textwidth in a one-column class
    # --- every graphic: exists, allowed extension
    allowed = [e.strip().lower() for e in str(tgt.get("figure_ext") or "pdf").split(",")]
    gpaths = graphicspath(text)
    incs = list(re.finditer(r"\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", text))
    resolved = []
    for g in incs:
        p, ext = resolve_graphic(g.group(2), texdir, gpaths)
        if p is None: say("FAIL", f"\\includegraphics{{{g.group(2)}}} 找不到文件（graphicspath {gpaths or ['.']}）"); continue
        if ext not in allowed: say("FAIL", f"{g.group(2)} 是 .{ext}，图一律 {allowed}（栅格内容也封成 PDF；make_figure.py / make_comparison.py grid 都出 .pdf）")
        resolved.append((g, p, ext))
    if incs and len(resolved) == len(incs) and all(e in allowed for _, _, e in resolved):
        say("PASS", f"{len(incs)} 张图全部存在且为 {allowed}")
    if not incs: say("WARN", "正文没有任何 \\includegraphics")
    # --- figure environments: composition rules
    n_fig = n_multi = 0; uses_sub = False
    for fm in re.finditer(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", text, re.S):
        inner = fm.group(2); n_fig += 1
        n_inc = len(re.findall(r"\\includegraphics", inner))
        n_sub = len(re.findall(r"\\begin\{subfigure\}|\\subfloat\b|\\subcaptionbox\b", inner))
        if n_sub: uses_sub = True
        caps = captions(inner); main_cap = caps[-1] if caps else ""
        label = re.search(r"\\label\{([^}]+)\}", inner)
        tag = label.group(1) if label else f"figure #{n_fig}"
        if n_inc >= 2:
            n_multi += 1
            if n_sub == 0: say("FAIL", f"{tag}: figure 含 {n_inc} 张图但没有 subfigure/subfloat —— 组合图要逐子图引用，每个子图自己的 PDF 与子题注（`latex_check.py figure` 生成）")
            elif n_sub < n_inc: say("WARN", f"{tag}: {n_inc} 张图只有 {n_sub} 个子图容器")
        if n_inc == 1 and re.search(r"\(\s*(?:\\textbf\{)?[a-hA-H]\}?\s*\)|\\textbf\{\(?[a-h]\)?\}", main_cap):
            say("FAIL", f"{tag}: 题注带面板字母 (a)(b) 但只引用一个文件 —— 这是预合成的组合图；拆成单个子图 PDF，用 subfigure 拼（`latex_check.py figure`）")
        if not label: say("WARN", f"figure #{n_fig} 没有 \\label")
    if uses_sub and not any(p in ("subcaption", "subfig") for p in pkgs):
        say("FAIL", "用了 subfigure/subfloat 但没有 \\usepackage{subcaption}（IEEEtran 用 \\usepackage[caption=false,font=footnotesize]{subfig}）")
    for tm in re.finditer(r"\\begin\{(table\*?)\}(.*?)\\end\{\1\}", text, re.S):
        if not re.search(r"\\label\{", tm.group(2)): say("WARN", "有 table 没有 \\label")
    # --- references
    labels = set(re.findall(r"\\label\{([^}]+)\}", text))
    refs = [r.strip() for grp in re.findall(r"\\(?:ref|autoref|cref|Cref|eqref|pageref)\{([^}]+)\}", text) for r in grp.split(",")]
    dangling = sorted({r for r in refs if r and r not in labels})
    if dangling: say("FAIL", f"\\ref 指向不存在的 label: {dangling[:8]}")
    elif refs: say("PASS", f"{len(refs)} 处 \\ref 全部有 label")
    # --- bibliography
    bm = re.search(r"\\bibliography\{([^}]+)\}", text); am = re.findall(r"\\addbibresource\{([^}]+)\}", text)
    bibs = ([b.strip() for b in bm.group(1).split(",")] if bm else []) + am
    if bibs:
        for b in bibs:
            p = next((c for c in (os.path.join(texdir, b), os.path.join(texdir, b + ".bib")) if os.path.isfile(c)), None)
            if p is None: say("FAIL", f"\\bibliography{{{b}}} 的 .bib 不存在（相对 {_relpath(texdir, root)}）")
        else: say("PASS", f"bib 文件在: {bibs}")
    elif re.search(r"\\begin\{thebibliography\}", text): say("PASS", "内嵌 thebibliography")
    else: say("WARN", "没有 \\bibliography / \\addbibresource / thebibliography")
    # --- leftover markers + bibliography build artefacts (raw keys in the reference list)
    leftover_markers(text, pkgs_raw=re.findall(r"\\usepackage\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", text))
    bib_artifacts(tex, files)
    # --- figures.csv cross-check (registration + print width)
    fp = os.path.join(root, a.figures)
    reg = {}
    if os.path.exists(fp):
        for r in csv.DictReader(io.open(fp, encoding="utf-8-sig")):
            try: reg[os.path.normpath(os.path.join(root, r["file"]))] = float(r.get("print_width_mm") or 0)
            except Exception: pass
    # subfigure scale: includegraphics inside \begin{subfigure}{0.48\textwidth} is 0.48 of the base
    sub_scale = {}
    for sm in re.finditer(r"\\begin\{subfigure\}(?:\[[^\]]*\])?\{\s*([\d.]*)\s*\\(textwidth|linewidth|columnwidth)\s*\}(.*?)\\end\{subfigure\}", text, re.S):
        frac = float(sm.group(1)) if sm.group(1) else 1.0; base = base_col if sm.group(2) == "columnwidth" else base_full
        for g in re.finditer(r"\\includegraphics", sm.group(3)): sub_scale[sm.start(3) + g.start()] = (frac, base)
    unreg = []; off = []
    for g, p, ext in resolved:
        key = os.path.normpath(p)
        if key not in reg: unreg.append(_relpath(p, root).replace("\\", "/")); continue
        if g.start() in sub_scale:
            frac, base = sub_scale[g.start()]; inner = width_mm(g.group(1), 1.0, 1.0)   # fraction of the subfigure's linewidth
            mm = frac * base * (inner if inner is not None else 1.0)
        else: mm = width_mm(g.group(1), base_full, base_col)
        if mm is not None and reg[key] and abs(mm - reg[key]) / reg[key] > 0.05:
            off.append(f"{os.path.basename(p)}: LaTeX {mm:.0f} mm vs figures.csv {reg[key]:.0f} mm")
    if unreg: say("WARN", f"{len(unreg)} 张图未登记 figures.csv（G5 不会查它们）: {unreg[:5]}")
    if off: say("WARN", f"印刷宽度不一致（版心按 {tpl['key'] if tpl else '默认'} {base_full:.0f}/{base_col:.0f} mm 估算，`widths --tex` 可实测）: {off[:4]}")
    if resolved and not unreg and not off: say("PASS", f"{len(resolved)} 张图都在 figures.csv 且印刷宽度一致")
    # --- derived manuscript freshness
    md = os.path.join(root, "paper", "manuscript.md")
    newest = max(os.path.getmtime(f) for f in files)
    if not os.path.exists(md): say("WARN", f"无 paper/manuscript.md：关口要它，跑 `tex_to_md.py {_relpath(tex, root)} . --bib <bib>` 生成")
    elif os.path.getmtime(md) + 1 < newest: say("FAIL", f"paper/manuscript.md 比 LaTeX 源旧 —— 关口检查的是旧正文；改完 .tex 先 `tex_to_md.py {_relpath(tex, root).replace(os.sep, '/')} . --bib <bib>` 再 `t2p.py check`")
    else: say("PASS", "paper/manuscript.md 新于全部 .tex 源（派生正文是最新的）")
    if FAILS == 0: say("PASS", f"LaTeX 投稿形态：{n_fig} 个 figure（{n_multi} 个组合图逐子图引用），{len(files)} 个 .tex 源文件")


# ------------------------------------------------------------------ figure block
def figure_block(panels, labels, caption, label, width, style, env, texdir, twocol):
    base = "\\columnwidth" if (twocol and not env.endswith("*")) else "\\textwidth"
    rel = [_relpath(os.path.abspath(p), texdir).replace("\\", "/") for p in panels]
    L = [f"\\begin{{{env}}}[t]", "  \\centering"]
    widths = [w.strip() for w in str(width).split(",") if w.strip()]
    widths = widths * len(rel) if len(widths) == 1 else widths     # one share for all panels, or one per panel (teaser: 0.15,0.33,0.50)
    for i, (p, lab) in enumerate(zip(rel, labels)):
        sub = f"{label}-{chr(97 + i)}"; width = widths[i]
        if style == "subfig":
            L.append(f"  \\subfloat[{lab}\\label{{{sub}}}]{{\\includegraphics[width={width}{base}]{{{p}}}}}" + ("\\hfill" if i < len(rel) - 1 else ""))
        else:
            L += [f"  \\begin{{subfigure}}[t]{{{width}{base}}}", f"    \\centering\\includegraphics[width=\\linewidth]{{{p}}}", f"    \\caption{{{lab}}}\\label{{{sub}}}", "  \\end{subfigure}" + ("\\hfill" if i < len(rel) - 1 else "")]
    L += [f"  \\caption{{{caption}}}", f"  \\label{{{label}}}", f"\\end{{{env}}}"]
    return "\n".join(L) + "\n"


def detect_style(texdir):
    main = os.path.join(texdir, "main.tex")
    if os.path.exists(main):
        t = read(main)
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{subfig\}", t): return "subfig"
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{subcaption\}", t): return "subcaption"
        if "IEEEtran" in t: return "subfig"
    return "subcaption"


def figure(a):
    root = os.path.abspath(a.project); texdir = os.path.join(root, a.tex_dir)
    panels = [p.strip() for p in a.panels.split(",") if p.strip()]
    labels = [l.strip() for l in a.labels.split(",")] if a.labels else [f"Panel {chr(65 + i)}" for i in range(len(panels))]
    if len(labels) != len(panels): say("FAIL", f"{len(panels)} 个面板但 {len(labels)} 个标签"); sys.exit(1)
    nw = len([w for w in a.width.split(",") if w.strip()])
    if nw not in (1, len(panels)): say("FAIL", f"--width 给了 {nw} 个份额，要么 1 个（全部面板同宽）要么每个面板一个（{len(panels)} 个）"); sys.exit(1)
    for p in panels:
        ap = p if os.path.isabs(p) else os.path.join(root, p)
        if not os.path.isfile(ap): say("FAIL", f"面板 {p} 不存在"); sys.exit(1)
        if not ap.lower().endswith(".pdf"): say("FAIL", f"面板 {p} 不是 PDF：每个子图单独出一个 PDF（matplotlib savefig('.pdf')；栅格图用 PIL 存 PDF）"); sys.exit(1)
    style = detect_style(texdir) if a.style == "auto" else a.style
    main = os.path.join(texdir, "main.tex"); twocol = False
    if os.path.exists(main):
        t = read(main); m = re.search(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", t)
        twocol = two_column(None, m.group(1) if m else "", m.group(2) if m else "") if m else False
    label = a.label or "fig:" + re.sub(r"\W+", "-", os.path.splitext(os.path.basename(panels[0]))[0])
    block = figure_block([os.path.join(root, p) if not os.path.isabs(p) else p for p in panels], labels, a.caption, label, a.width, style, a.env, texdir, twocol)
    out = os.path.join(texdir, a.out or os.path.join("figs", re.sub(r"\W+", "_", label.split(":", 1)[-1]) + ".tex"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(block)
    inp = os.path.splitext(_relpath(out, texdir))[0].replace("\\", "/")
    print(block); print(f"-> {_relpath(out, root)}  ({style}, {len(panels)} 个子图)；正文里写 \\input{{{inp}}}；每个面板登记 figures.csv，印刷宽度 = {a.width} × 版心")


# ------------------------------------------------------------------ skeleton
BACKMATTER = ("credit", "declaration", "data availability", "acknowledg", "references", "highlights", "keywords", "abstract")


def sections_from_skeleton(family):
    p = os.path.join(SKILL, "templates", f"skeleton-{family}.md")
    if not os.path.exists(p): return []
    out = []
    for ln in read(p).splitlines():
        m = re.match(r"^(#{2,3})\s+(?:\d+(?:\.\d+)*\.?\s+)?(.+?)\s*$", ln)
        if not m: continue
        title = m.group(2)
        title = re.sub(r"\([^)]*\)", "", title)                       # drop remarks such as "(✓/× table; …)"
        title = re.sub(r"<([^>]*)>", r"\1", title)                     # "<Component A>" -> "Component A"
        title = re.sub(r"[^\x20-\x7e]", "", title)                     # LaTeX source stays ASCII; headings are English anyway
        title = re.sub(r"\s+", " ", title).strip(" :;,-")
        if not title or any(k in title.lower() for k in BACKMATTER): continue
        out.append((len(m.group(1)), title))
    return out


def skeleton(a):
    root = os.path.abspath(a.project)
    rows = load_templates(); tpl = pick_template(a.venue, a.family, rows)
    family = (a.family or (tpl["family"] if tpl else "") or "cs_journal").lower()
    cls = tpl["documentclass"].split("|")[0] if tpl else "article"
    opts = (tpl["class_options"] if tpl else "")
    sty = [s for s in (tpl.get("sty", "") if tpl else "").split("|") if s]
    style = (tpl["subfig_style"] if tpl else "subcaption")
    bibstyle = tpl["bibstyle"] if tpl else "plainnat"
    out_dir = os.path.join(root, a.out); os.makedirs(out_dir, exist_ok=True)
    main = os.path.join(out_dir, "main.tex")
    if os.path.exists(main) and not a.force: say("FAIL", f"{_relpath(main, root)} 已存在（--force 覆盖）"); sys.exit(1)
    figrel = _relpath(os.path.join(root, "figures"), out_dir).replace("\\", "/") + "/"
    bibrel = _relpath(os.path.join(root, "paper", "refs"), out_dir).replace("\\", "/")
    title = a.title or "<Title>"
    L = [f"\\documentclass[{opts}]{{{cls}}}" if opts else f"\\documentclass{{{cls}}}"]
    if tpl: L.append(f"% template: {tpl['key']} — put the class/style file(s) in this folder; source: {tpl['sty_source']}")
    for s in sty: L.append(f"\\usepackage{{{s.rstrip('_')}<year>}}  % rename to the file you downloaded")
    L += ["\\usepackage{graphicx}", "\\usepackage{amsmath,amssymb}", "\\usepackage{booktabs}"]
    L.append("\\usepackage[caption=false,font=footnotesize]{subfig}" if style == "subfig" else "\\usepackage{subcaption}")
    L += [f"\\graphicspath{{{{{figrel}}}}}", "% every figure is a PDF; a multi-panel figure is one PDF per panel composed below (latex_check.py figure)", ""]
    if cls == "elsarticle":
        L += ["\\begin{document}", "\\begin{frontmatter}", f"\\title{{{title}}}", "\\author[1]{Author}", "\\affiliation[1]{organization={Institution}, city={City}, country={Country}}",
              "\\begin{abstract}", "<abstract>", "\\end{abstract}", "\\begin{keyword}", "keyword one \\sep keyword two", "\\end{keyword}", "\\end{frontmatter}", ""]
    elif cls == "IEEEtran":
        L += [f"\\title{{{title}}}", "\\author{Author}", "\\begin{document}", "\\maketitle", "\\begin{abstract}", "<abstract>", "\\end{abstract}", "\\begin{IEEEkeywords}", "keyword one, keyword two", "\\end{IEEEkeywords}", ""]
    else:
        L += [f"\\title{{{title}}}", "\\author{Author}", "\\begin{document}", "\\maketitle", "\\begin{abstract}", "<abstract>", "\\end{abstract}", ""]
    secs = sections_from_skeleton(family) or [(2, "Introduction"), (2, "Method"), (2, "Experiments"), (2, "Conclusion")]
    star = "*" if family == "nature" else ""
    for lv, t in secs:
        L.append(("\\section" if lv == 2 else "\\subsection") + star + f"{{{t}}}")
    # The two figure examples stay COMMENTED OUT: at P0 no figure exists yet, and a live \includegraphics of a file that
    # P5 has not produced would make G6d FAIL on a freshly generated skeleton. Uncomment at P6, one block per real figure.
    base = "\\columnwidth" if two_column(tpl, opts, cls) else "\\textwidth"
    example = (["% ---- 图示例（P5 出图后取消注释，每张图一块；正文里用 Fig.~\\ref{fig:main} 引用）----",
                "\\begin{figure}[t]", "  \\centering", f"  \\includegraphics[width=0.95{base}]{{fig_main.pdf}}", "  \\caption{<caption>}", "  \\label{fig:main}", "\\end{figure}", "",
                "% ---- 组合图示例：每个面板一个 PDF，由 `latex_check.py figure --panels a.pdf,b.pdf …` 生成 ----"]
               + figure_block([os.path.join(root, "figures", "fig_a.pdf"), os.path.join(root, "figures", "fig_b.pdf")],
                              ["<panel a>", "<panel b>"], "<caption>", "fig:panels", "0.48", style, "figure", out_dir,
                              two_column(tpl, opts, cls)).rstrip("\n").split("\n"))
    L += [""] + [ln if ln.startswith("%") else "% " + ln for ln in example]
    L += ["", f"\\bibliographystyle{{{bibstyle}}}", f"\\bibliography{{{bibrel}}}", "\\end{document}", ""]
    io.open(main, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print(f"-> {_relpath(main, root)}  class {cls}{'[' + opts + ']' if opts else ''}，family {family}，{len(secs)} 个节，子图风格 {style}")
    if tpl: print(f"模板文件来源: {tpl['sty_source']}\n版心（{tpl['measured']}）: 单栏 {tpl['single_col_mm']} mm / 全宽 {tpl['full_width_mm']} mm；`latex_check.py widths --tex {_relpath(main, root).replace(os.sep, '/')}` 可实测")
    else: print("latex-templates.csv 没有这个刊的行：用了 article；把目标刊的 class 放进来后改 \\documentclass")
    print(f"写作流程：改 main.tex → `tex_to_md.py {_relpath(main, root).replace(os.sep, '/')} . --bib paper/refs.bib` 派生 paper/manuscript.md → `t2p.py check`（G6d = latex_check.py check）")


# ------------------------------------------------------------------ widths
def widths(a):
    root = os.path.abspath(a.project)
    rows = load_templates()
    if a.tex:
        tex = os.path.join(root, a.tex); texdir = os.path.dirname(os.path.abspath(tex))
        if not os.path.exists(tex): say("FAIL", f"{a.tex} 不存在"); sys.exit(1)
        pre = read(tex).split("\\begin{document}", 1)[0]
        m = re.search(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", pre); cls = m.group(2) if m else "?"; opts = (m.group(1) or "") if m else ""
    else:
        if not a.cls: say("FAIL", "给 --tex 或 --class"); sys.exit(1)
        cls, opts = a.cls, a.options; texdir = root
        pre = f"\\documentclass[{opts}]{{{cls}}}\n" if opts else f"\\documentclass{{{cls}}}\n"
    tpl = next((r for r in rows if cls in r["documentclass"].split("|")), None)
    pdflatex = shutil.which("pdflatex")
    if pdflatex:
        doc = pre + "\n\\begin{document}\n\\typeout{T2P-TW=\\the\\textwidth}\\typeout{T2P-CW=\\the\\columnwidth}\n\\end{document}\n"
        name = "_t2p_widths"
        io.open(os.path.join(texdir, name + ".tex"), "w", encoding="utf-8").write(doc)
        try:
            r = subprocess.run([pdflatex, "-interaction=nonstopmode", "-halt-on-error", "-draftmode", name + ".tex"], cwd=texdir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            out = r.stdout + r.stderr
        except Exception as ex: out = f"pdflatex failed: {ex}"
        finally:
            for e in (".tex", ".aux", ".log", ".pdf", ".out"):
                try: os.remove(os.path.join(texdir, name + e))
                except OSError: pass
        tw = re.search(r"T2P-TW=([\d.]+)pt", out); cw = re.search(r"T2P-CW=([\d.]+)pt", out)
        if tw and cw:
            twm, cwm = float(tw.group(1)) * PT_MM, float(cw.group(1)) * PT_MM
            print(f"measured with pdflatex: class {cls}[{opts}]  textwidth = {twm:.1f} mm ({float(tw.group(1)):.1f} pt)  columnwidth = {cwm:.1f} mm ({float(cw.group(1)):.1f} pt)")
            print("用法：figures.csv 的 print_width_mm = width 份额 × 上面的值；make_figure.py --width-mm 取同一数")
            return
        miss = re.search(r"! LaTeX Error: File `([^']+)' not found", out)
        say("WARN", f"pdflatex 未能编译（{'缺 ' + miss.group(1) if miss else '见日志'}）：class/style 文件要放在 {_relpath(texdir, root) or '.'}；下面是表值")
    else: say("INFO", "本机没有 pdflatex；下面是 references/latex-templates.csv 的表值")
    if tpl: print(f"table ({tpl['measured']}): class {cls}  textwidth ≈ {tpl['full_width_mm']} mm  columnwidth ≈ {tpl['single_col_mm'] if tpl['twocolumn'] == 'yes' else tpl['full_width_mm']} mm  (two-column: {tpl['twocolumn']})")
    else: print(f"table: no row for class {cls}; typical defaults textwidth 170 mm, two-column column 85 mm")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--project", default="."); c.add_argument("--tex", default=""); c.add_argument("--state", default="research-state.yaml"); c.add_argument("--figures", default="figures.csv")
    s = sub.add_parser("skeleton"); s.add_argument("--venue", required=True); s.add_argument("--family", default=""); s.add_argument("--out", default="paper/latex"); s.add_argument("--title", default=""); s.add_argument("--force", action="store_true"); s.add_argument("--project", default=".")
    f = sub.add_parser("figure"); f.add_argument("--panels", required=True); f.add_argument("--labels", default=""); f.add_argument("--caption", default="<caption>"); f.add_argument("--label", default="")
    f.add_argument("--width", default="0.48"); f.add_argument("--style", choices=["auto", "subcaption", "subfig"], default="auto"); f.add_argument("--env", choices=["figure", "figure*"], default="figure"); f.add_argument("--tex-dir", default="paper/latex"); f.add_argument("--out", default=""); f.add_argument("--project", default=".")
    w = sub.add_parser("widths"); w.add_argument("--tex", default=""); w.add_argument("--class", dest="cls", default=""); w.add_argument("--options", default=""); w.add_argument("--project", default=".")
    a = ap.parse_args()
    {"check": check, "skeleton": skeleton, "figure": figure, "widths": widths}[a.cmd](a)
    if a.cmd == "check":
        print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)
    sys.exit(0 if FAILS == 0 else 1)
