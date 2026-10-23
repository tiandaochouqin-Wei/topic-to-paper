# -*- coding: utf-8 -*-
"""Algorithm blocks (pseudocode) in a LaTeX manuscript: anchored to the code that ran, checked like every other float. Part of G6d (latex_check.py calls `check`) and G6 floats.

  python make_algorithm.py skeleton  --id train [--project .] [--force]
  python make_algorithm.py check     [--project .] [--tex paper/latex/main.tex] [--state research-state.yaml]
  python make_algorithm.py calibrate [--papers Z:/LDCT/papers] [--out references/algorithm-norms.csv] [--per-venue 40] [--seed 20261023] [--workers 8] [--per-paper csv]

research-state.yaml (templates/research-state.yaml):
  algorithms:
    - id: train                          # \\label{alg:train}
      source: code/train.py:train_one_epoch   # file:function the block describes (parsed with ast; Class.method allowed)
      tex: paper/latex/alg_train.tex     # written by `skeleton`, \\input from main.tex
      params: {"\\\\eta": lr, "\\\\lambda": beta, K: epochs}   # symbol in the block -> args.json key

skeleton: one line per top-level statement of the function (for/while -> \\For, if -> \\If, return -> \\State \\Return, anything else -> \\State with the source line as a `% code:` comment
  that Claude rewrites into the mathematical statement); nesting is kept to depth 2, deeper bodies collapse to one line. Dialect from the preamble of main.tex: algorithm2e -> \\KwIn/\\For{}{};
  `algorithmic` (old package, \\STATE) -> upper-case commands; otherwise `algorithm` + `algpseudocode` (the `algorithmic` environment with \\State/\\Require/\\For). Prints the missing \\usepackage / \\input lines.

check (exit = #FAIL), over every algorithm environment of the \\input-expanded .tex:
  1 packages and command family consistent (algorithm/algorithm2e loaded; \\State needs algpseudocode, \\STATE needs algorithmic, \\KwIn needs algorithm2e; algorithm2e + algorithmic conflict)       FAIL
  2 every block has \\caption and \\label{alg:..}; every label is \\ref/\\cref/\\autoref'd in the text                                                                                      FAIL
  3 label without a state.algorithms row (WARN); row whose source file or function does not exist (FAIL)
  4 code-like tokens in the block (\\texttt{..}, text with _ or digits, Greek macros nobody defines) that are not a params key / an identifier of the source function (WARN)
  5 `\\Require` lines `\\lambda = 0.5` with the symbol in params: the number must equal the reference run's value (bundle.matrix.ref.args `--beta 0.1`, else runs/<ref>*/args.json) (FAIL)
  6 shape: fewer \\For/\\While than the function has loops in its top two nesting levels, no \\If against >= 3 ifs, > 30 numbered lines (WARN); + skeleton placeholders left (empty \\State, \\For{$\\ldots$}) (WARN)
  7 a number with >= 3 significant digits inside \\State text: pseudocode does not carry result numbers (WARN)
Why: pseudocode written from memory describes the intended method, not the one that ran. Same logic as G3b: anchor it to the function and to the reference run's arguments.

calibrate: how common pseudocode is at each venue, from the published-paper corpus (PyMuPDF text of the first 14 pages: caption lines `Algorithm N:` / `Algorithm N Title`, distinct numbers per paper;
n_method_papers = papers with a Method/Approach/Framework heading; share_with_algorithm = among those; p50/p90/max counts are among papers that have >= 1 algorithm).
Rows per venue plus one `ALL` row per family (cs_conf / cs_journal / nature, as shape_check infers it); shape_check.py reads the ALL rows."""
import argparse, ast, csv, datetime, glob, io, json, math, os, random, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
NORMS_CSV = os.path.join(SKILL, "references", "algorithm-norms.csv")
FAILS = WARNS = 0
def say(st, msg):
    global FAILS, WARNS
    FAILS += st == "FAIL"; WARNS += st == "WARN"
    print(f"[{st}] algorithm: {msg}")

def read(p): return io.open(p, encoding="utf-8", errors="replace").read()
def norm(s): return re.sub(r"[\s{}]", "", s)                      # `\lambda_{1}` == `\lambda_1`
def idn(s): return s.lower().replace("_", "")                      # train_loss == trainLoss == TrainLoss (case/underscore blind)

# ------------------------------------------------------------------ source function (ast)
def split_source(src):
    s = str(src or "").strip(); i = s.rfind(":")
    return (s[:i], s[i + 1:]) if i > 0 and re.fullmatch(r"[A-Za-z_][\w.]*", s[i + 1:]) else (None, None)

def load_func(root, src):
    """-> (FunctionDef node, source lines, None) or (None, None, error). `Class.method` walks the class body; a bare name falls back to the unique def of that name anywhere."""
    f, fn = split_source(src)
    if not f: return None, None, f"source {src!r} 不是 file:function"
    p = os.path.join(root, f)
    if not os.path.isfile(p): return None, None, f"文件 {f} 不存在"
    try: text = read(p); tree = ast.parse(text)
    except SyntaxError as ex: return None, None, f"{f} 解析失败: {ex.msg} (行 {ex.lineno})"
    scope, node = tree.body, None
    for part in fn.split("."):
        node = next((n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part), None)
        if node is None: break
        scope = node.body
    if node is None and "." not in fn:
        hits = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn]
        node = hits[0] if len(hits) == 1 else None
    if node is None or isinstance(node, ast.ClassDef): return None, None, f"{f} 里没有函数 {fn}"
    return node, text.splitlines(), None

def func_idents(node):
    """normalised identifiers of a function: its name, arguments, every Name / attribute / keyword / called function."""
    out = {idn(node.name)}
    for n in ast.walk(node):
        if isinstance(n, ast.arg): out.add(idn(n.arg))
        elif isinstance(n, ast.Name): out.add(idn(n.id))
        elif isinstance(n, ast.Attribute): out.add(idn(n.attr))
        elif isinstance(n, ast.keyword) and n.arg: out.add(idn(n.arg))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): out.add(idn(n.name))
    return out

LOOPS = (ast.For, ast.AsyncFor, ast.While)
def count_top(stmts, kinds, depth=1):
    """statements of `kinds` in the first two nesting levels (with/try are transparent, like in the skeleton)."""
    n = 0
    for s in stmts:
        n += isinstance(s, kinds)
        if isinstance(s, (ast.With, ast.AsyncWith, ast.Try)): n += count_top(s.body, kinds, depth)
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.While, ast.If)) and depth < 2: n += count_top(s.body + s.orelse, kinds, depth + 1)
    return n

# ------------------------------------------------------------------ skeleton
DIALECT = {   # algpseudocode (\State) | algorithmic (\STATE) | algorithm2e
    "camel": dict(req="\\Require", ens="\\Ensure", state="\\State", ret="\\State \\Return", For="\\For{%s}", endfor="\\EndFor", While="\\While{%s}", endwhile="\\EndWhile", If="\\If{%s}", elsif="\\ElsIf{%s}", Else="\\Else", endif="\\EndIf"),
    "upper": dict(req="\\REQUIRE", ens="\\ENSURE", state="\\STATE", ret="\\RETURN", For="\\FOR{%s}", endfor="\\ENDFOR", While="\\WHILE{%s}", endwhile="\\ENDWHILE", If="\\IF{%s}", elsif="\\ELSIF{%s}", Else="\\ELSE", endif="\\ENDIF"),
}
PH = "$\\ldots$"            # the placeholder a skeleton leaves; check warns while any is left

def pick_dialect(preamble):
    pk = {p.strip() for g in re.findall(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", preamble) for p in g.split(",")}
    if "algorithm2e" in pk: return "a2e", pk
    if "algorithmic" in pk and not pk & {"algpseudocode", "algpseudocodex", "algorithmicx"}: return "upper", pk
    return "camel", pk

def src_line(lines, s, extra=""):
    t = lines[s.lineno - 1].strip(); n = (getattr(s, "end_lineno", s.lineno) or s.lineno) - s.lineno + 1
    return re.sub(r"\s+", " ", t)[:100] + (f" … ({n} lines)" if n > 1 else "") + extra

def body_stmts(stmts):
    return [s for s in stmts if not (isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant) and isinstance(s.value.value, str)))]

def render(stmts, lines, d, depth, ind, out):
    """append skeleton lines for `stmts`; depth 1 = top level of the function body. Compound statements below depth 2 collapse to one `\\State % code: … (n lines)`."""
    a2e = d is None
    for s in body_stmts(stmts):
        pad = "  " * ind; cm = lambda t: f" % code: {t}"
        if isinstance(s, (ast.With, ast.AsyncWith, ast.Try)):
            out.append(f"{pad}% code: {src_line(lines, s)}"); render(s.body, lines, d, depth, ind, out)
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.While, ast.If)):
            loop = not isinstance(s, ast.If); kind = ("While" if isinstance(s, ast.While) else "For") if loop else "If"
            def sub(body, ind2):
                if depth >= 2:
                    n = max(getattr(b, "end_lineno", b.lineno) for b in body) - body[0].lineno + 1; first = re.sub(r"\s+", " ", lines[body[0].lineno - 1].strip())[:100]
                    out.append("  " * ind2 + (f"{d['state']} {PH}" if not a2e else f"{PH}\\;") + cm(first if n == 1 else f"{first} … ({n} lines)"))
                else: render(body, lines, d, depth + 1, ind2, out)
            if a2e:
                out.append(f"{pad}\\{kind}{{{PH}}}{{" + cm(src_line(lines, s, "")))
                sub(s.body, ind + 1)
                orelse = s.orelse
                while orelse and not loop:
                    if len(orelse) == 1 and isinstance(orelse[0], ast.If): out.append(f"{pad}}}\\ElseIf{{{PH}}}{{" + cm(src_line(lines, orelse[0]))); sub(orelse[0].body, ind + 1); orelse = orelse[0].orelse
                    else: out.append(f"{pad}}}\\Else{{"); sub(orelse, ind + 1); orelse = []
                out.append(f"{pad}}}")
            else:
                out.append(f"{pad}{d[kind] % PH}" + cm(src_line(lines, s)))
                sub(s.body, ind + 1)
                orelse = s.orelse
                while orelse and not loop:
                    if len(orelse) == 1 and isinstance(orelse[0], ast.If): out.append(f"{pad}{d['elsif'] % PH}" + cm(src_line(lines, orelse[0]))); sub(orelse[0].body, ind + 1); orelse = orelse[0].orelse
                    else: out.append(f"{pad}{d['Else']}"); sub(orelse, ind + 1); orelse = []
                out.append(f"{pad}{d['endwhile'] if kind == 'While' else d['endfor'] if loop else d['endif']}")
        elif isinstance(s, ast.Return):
            out.append(f"{pad}" + (f"\\Return {PH}\\;" if a2e else (f"{d['ret']} {PH}" if s.value is not None else d["ret"])) + cm(src_line(lines, s)))
        else:
            out.append(f"{pad}" + (f"{PH}\\;" if a2e else f"{d['state']} {PH}") + cm(src_line(lines, s)))

def skeleton_text(aid, node, lines, dialect, params):
    args = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs if a.arg not in ("self", "cls")]
    body = []; d = None if dialect == "a2e" else DIALECT[dialect]
    render(node.body, lines, d, 1, 0, body)
    ph = f"% params (symbol -> args.json key): {', '.join(f'{k} -> {v}' for k, v in params.items())}; state values in \\Require as `symbol = number`, the check compares them with the reference run" if params else "% no params declared in state.algorithms: add {symbol: args key} to let `check` compare numbers"
    head = ["\\begin{algorithm}[t]", f"\\caption{{{aid} (fill in)}}", f"\\label{{alg:{aid}}}"]
    if dialect == "a2e":
        head += ["\\SetAlgoLined", f"\\KwIn{{{PH}}} % args: {', '.join(args)}", f"\\KwOut{{{PH}}} % what the function returns / writes", ph]
        return "\n".join(head + body + ["\\end{algorithm}", ""])
    head += ["\\begin{algorithmic}[1]", f"{d['req']} {PH} % args: {', '.join(args)}", ph, f"{d['ens']} {PH} % what the function returns / writes"]
    return "\n".join(head + body + ["\\end{algorithmic}", "\\end{algorithm}", ""])

def load_state(root, name="research-state.yaml"):
    p = os.path.join(root, name)
    if not os.path.exists(p): return {}
    try:
        import yaml; return yaml.safe_load(read(p)) or {}
    except Exception as ex: say("WARN", f"state 读取失败 {ex}"); return {}

def skeleton(a):
    root = os.path.abspath(a.project); st = load_state(root)
    row = next((r for r in (st.get("algorithms") or []) if isinstance(r, dict) and str(r.get("id")) == a.id), None)
    if not row: say("FAIL", f"research-state.yaml 的 algorithms 里没有 id={a.id}（先登记 {{id, source: file:function, tex, params}}）"); sys.exit(1)
    node, lines, err = load_func(root, row.get("source"))
    if err: say("FAIL", f"algorithms.{a.id}.source: {err}"); sys.exit(1)
    latex_dir = ((st.get("target") or {}).get("latex_dir")) or "paper/latex"; main = os.path.join(root, latex_dir, "main.tex")
    pre = read(main).split("\\begin{document}", 1)[0] if os.path.exists(main) else ""
    dialect, pk = pick_dialect(pre)
    out = os.path.join(root, row.get("tex") or f"{latex_dir}/alg_{a.id}.tex")
    if os.path.exists(out) and not a.force: say("FAIL", f"{os.path.relpath(out, root)} 已存在（--force 覆盖）"); sys.exit(1)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(skeleton_text(a.id, node, lines, dialect, row.get("params") or {}))
    nl = sum(1 for _ in io.open(out, encoding="utf-8")); rel = os.path.relpath(out, root).replace("\\", "/")
    print(f"-> {rel}  ({dialect}，函数 {row['source']}，{nl} 行)；把每个 `% code:` 注释改写成数学语句，符号在正文里定义，不写结果数字，然后 `make_algorithm.py check`")
    need = ([] if "algorithm" in pk or "algorithm2e" in pk else (["\\usepackage{algorithm2e}"] if dialect == "a2e" else ["\\usepackage{algorithm}"]))
    if dialect == "camel" and not pk & {"algpseudocode", "algpseudocodex", "algorithmicx"}: need.append("\\usepackage{algpseudocode}")
    if dialect == "upper" and "algorithmic" not in pk: need.append("\\usepackage{algorithmic}")
    inp = os.path.splitext(os.path.relpath(out, os.path.dirname(main)))[0].replace("\\", "/")
    if not os.path.exists(main): print(f"main.tex 不存在：以后在导言区加 {need or '（包已就绪）'}，在方法节加 \\input{{{inp}}}")
    else:
        if need: print("main.tex 导言区还缺: " + "  ".join(need))
        if not re.search(r"\\(?:input|include)\{" + re.escape(inp) + r"(?:\.tex)?\}", read(main)): print(f"main.tex 方法节还缺: \\input{{{inp}}}，并在正文写 Algorithm~\\ref{{alg:{a.id}}}")

# ------------------------------------------------------------------ check
GREEK = set("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Sigma Upsilon Phi Psi Omega".split())
ALIAS = {"epsilon": ("eps",), "varepsilon": ("eps", "epsilon"), "lambda": ("lam", "lambd", "lmbda"), "kappa": ("kap",), "sigma": ("sig",), "gamma": ("gam",), "theta": ("params", "weights")}
CAMEL = re.compile(r"\\(?:State|Statex|Require|Ensure|EndFor|EndWhile|EndIf|ElsIf)\b"); UPPER = re.compile(r"\\(?:STATE|REQUIRE|ENSURE|ENDFOR|ENDWHILE|ENDIF|ELSIF)\b"); A2E = re.compile(r"\\(?:KwIn|KwOut|KwData|KwResult|ElseIf|eIf|uIf|nl)\b")     # `\;` is not a marker: it is also the thick math space
REQ = re.compile(r"\\(?:Require|REQUIRE|KwIn|KwData)\b"); STOP = re.compile(r"\\(?:State|STATE|Statex|Ensure|ENSURE|For|FOR|ForAll|FORALL|If|IF|While|WHILE|Repeat|REPEAT|Return|RETURN|KwOut|KwResult|EndFor|EndIf|Require|REQUIRE|KwIn|end)\b")
NUMLINE = re.compile(r"\\(?:State|STATE|If|IF|ElsIf|ELSIF|Else|ELSE|EndIf|ENDIF|For|FOR|ForAll|FORALL|EndFor|ENDFOR|While|WHILE|EndWhile|ENDWHILE|Repeat|REPEAT|Until|UNTIL)\b")
LOOPCMD = re.compile(r"\\(?:For|FOR|ForAll|FORALL|ForEach|While|WHILE|Repeat|REPEAT)\b"); IFCMD = re.compile(r"\\(?:If|IF|eIf|uIf)\b")
NUM = r"[-+]?(?:\d+(?:\.\d+)?\s*(?:\\times|\\cdot|×)\s*10\^\{?-?\d+\}?|10\^\{?-?\d+\}?|\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|\.\d+)"
SYMVAL = re.compile(r"(\\[A-Za-z]+(?:_\{?[A-Za-z0-9]+\}?)?|[A-Za-z](?:_\{?[A-Za-z0-9]+\}?)?|[A-Za-z]{2,})\s*(?:=|:=|\\gets|\\leftarrow|\\coloneqq|\\coloneq)\s*(" + NUM + ")")

def parse_num(s):
    s = s.replace(" ", "").replace("{", "").replace("}", "")
    m = re.fullmatch(r"([-+]?\d*\.?\d+)?(?:\\times|\\cdot|×)?10\^(-?\d+)", s)
    if m: return float(m.group(1) or 1) * 10 ** int(m.group(2))
    try: return float(s)
    except ValueError: return None

def sig_digits(tok):
    d = tok.replace(".", "").lstrip("0")
    return len(d if "." in tok else d.rstrip("0"))

def ref_args(root, st):
    """{key: value} of the reference run: bundle.matrix.ref.args (`--beta 0.1`) first, then runs/<reference_method>*/args.json for keys it does not name."""
    out, src = {}, {}
    ref = ((st.get("bundle") or {}).get("matrix") or {}).get("ref") or {}
    for k, v in re.findall(r"--([\w-]+)[= ]+(\S+)", str(ref.get("args") or "")): out[k.replace("-", "_")] = v; src[k.replace("-", "_")] = "bundle.matrix.ref.args"
    res, aud = st.get("results") or {}, st.get("audits") or {}
    name = res.get("reference_method") or ref.get("name") or "ours"
    rd = os.path.join(root, aud.get("runs_dir") or res.get("runs_dir") or "runs")
    for d in sorted(glob.glob(os.path.join(rd, name + "*", aud.get("args_file", "args.json")))):
        try: ja = json.load(io.open(d, encoding="utf-8"))
        except Exception: continue
        if isinstance(ja, dict):
            for k, v in ja.items():
                if k not in out: out[k] = v; src[k] = os.path.relpath(d, root).replace("\\", "/")
        break
    return out, src

def find_blocks(text):
    out = []
    for m in re.finditer(r"\\begin\{(algorithm\*?)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}", text, re.S):
        inner = m.group(2); lab = re.search(r"\\label\{([^}]+)\}", inner)
        import latex_check as lc
        caps = lc.captions(inner)
        out.append({"span": m.span(), "inner": inner, "label": lab.group(1).strip() if lab else None, "caption": caps[-1] if caps else None})
    return out

def block_body(inner):
    """the algorithmic content: caption / label / begin-end lines dropped."""
    import latex_check as lc
    s = inner
    for cm in list(re.finditer(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", s))[::-1]:
        _, j = lc.balanced(s, cm.end() - 1); s = s[:cm.start()] + s[j:]
    return re.sub(r"\\label\{[^}]*\}|\\(?:begin|end)\{algorithmic\}(?:\[[^\]]*\])?|\\SetAlgoLined|\\DontPrintSemicolon", "", s)

def code_tokens(body):
    """(greek macros, identifier-like tokens) of a block: \\texttt{..}/\\mathtt{..} contents, text outside math containing `_` or a digit, Greek macros anywhere."""
    greek = {"\\" + g for g in re.findall(r"\\([A-Za-z]+)", body) if g in GREEK}
    toks = set()
    for m in re.finditer(r"\\(?:texttt|mathtt|code)\{([^{}]*)\}", body): toks |= {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", m.group(1).replace("\\_", "_")) if len(re.findall(r"[A-Za-z]", t)) >= 2}
    plain = re.sub(r"\\(?:texttt|mathtt|code)\{[^{}]*\}", " ", body); plain = re.sub(r"\$[^$]*\$", " ", plain); plain = re.sub(r"\\[A-Za-z]+\*?", " ", plain).replace("\\_", "_")
    for t in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|[A-Za-z]+[0-9]+[A-Za-z0-9]*", plain):
        if len(re.findall(r"[A-Za-z]", t)) >= 2 and not re.fullmatch(r"[A-Za-z]{1,2}\d+|\d+[A-Za-z]{0,2}", t): toks.add(t)
    return greek, toks

def defined_in_block(sym, body):
    """a Greek macro is the block's own variable if it is declared in \\Require/\\Ensure, bound by a loop header, or assigned."""
    e = re.escape(sym) + r"(?![A-Za-z])"
    if re.search(e + r"[^\n\\]{0,30}(?:\\gets|\\leftarrow|:=|\\coloneqq|=)", body): return True
    for m in REQ.finditer(body) :
        seg = body[m.end():]; n = STOP.search(seg); seg = seg[:n.start()] if n else seg
        if re.search(e, seg): return True
    return bool(re.search(r"\\(?:Ensure|ENSURE|KwOut|For|FOR|ForAll|FORALL|ForEach)\b[^\n]*" + e, body))

def check_block(b, aid, row, root, st, ref, ref_src):
    body = block_body(b["inner"]); tag = f"alg:{aid}"
    f0, w0 = FAILS, WARNS
    node = lines = None
    if row:
        node, lines, err = load_func(root, row.get("source"))
        if err: say("FAIL", f"{tag}: algorithms.{aid}.source {err}")
    params = {norm(str(k)): str(v) for k, v in ((row or {}).get("params") or {}).items()}
    if node is not None:
        idents = func_idents(node) | {idn(v) for v in params.values()}
        greek, toks = code_tokens(body)
        unknown = sorted(t for t in toks if idn(t) not in idents and norm(t) not in params)
        for g in sorted(greek):
            name = g[1:]
            if norm(g) in params or idn(name) in idents or any(idn(x) in idents for x in ALIAS.get(name, ())) or defined_in_block(g, body): continue
            unknown.append(g)
        if unknown: say("WARN", f"{tag}: 伪代码里的 {', '.join(unknown[:8])} 在 source 函数里找不到（既不是 params 键，也不是函数的名字 / 参数 / 调用，Greek 符号也没在块里定义）—— 写错符号，还是描述的不是这个函数")
        c_loops, c_ifs = count_top(node.body, LOOPS), count_top(node.body, ast.If)
        b_loops, b_ifs = len(LOOPCMD.findall(body)), len(IFCMD.findall(body))
        if b_loops < c_loops: say("WARN", f"{tag}: 函数 {row['source'].split(':')[-1]} 前两层有 {c_loops} 个循环，伪代码只有 {b_loops} 个 \\For/\\While —— 描述的是同一个方法吗")
        if c_ifs >= 3 and b_ifs == 0: say("WARN", f"{tag}: 函数前两层有 {c_ifs} 个 if，伪代码一个 \\If 都没有 —— 描述的是同一个方法吗")
    # 5: \Require values vs the reference run
    n_ok = 0
    for m in REQ.finditer(body):
        seg = body[m.end():]; n = STOP.search(seg); seg = seg[:n.start()] if n else seg
        for sm in SYMVAL.finditer(seg):
            key = params.get(norm(sm.group(1)))
            if key is None: continue
            val = parse_num(sm.group(2))
            if val is None: continue
            rv = ref.get(key)
            try: rf = float(rv)
            except (TypeError, ValueError): rf = None
            if rf is None: say("WARN", f"{tag}: {sm.group(1)} = {sm.group(2).strip()} 但 ref run 里没有可比的 {key}（bundle.matrix.ref.args 与 runs/<ref>*/args.json 都没有数值）—— 无法核对")
            elif not math.isclose(val, rf, rel_tol=1e-6, abs_tol=1e-12): say("FAIL", f"{tag}: 伪代码里 {sm.group(1)} = {val:g} 但 ref run 的 {key} = {rf:g}（{ref_src.get(key)}）—— 伪代码写的不是跑出结果的那组参数")
            else: n_ok += 1
    # 6: length + skeleton placeholders;  7: result numbers
    nlines = len(NUMLINE.findall(body)) + (len(re.findall(r"\\;", body)) if A2E.search(body) else 0)
    if nlines > 30: say("WARN", f"{tag}: 伪代码 {nlines} 行 > 30 —— 一块伪代码一页放不下，拆成子过程或挪到附录")
    left = len(re.findall(r"\\(?:State|STATE)\s*(?:\$\\ldots\$\s*)?$", body, re.M)) + len(re.findall(r"\{\s*\$\\ldots\$\s*\}", body)) + len(re.findall(r"^\s*\$\\ldots\$\\;\s*$", body, re.M))
    if left: say("WARN", f"{tag}: 还有 {left} 处 skeleton 占位（空 \\State / \\For{{$\\ldots$}}）—— 把 `% code:` 注释改写成数学语句")
    nums = []
    for ln in body.splitlines():
        m = re.match(r"\s*\\(?:State|STATE|Statex|If|IF|ElsIf|ELSIF|For|FOR|ForAll|FORALL|While|WHILE|Until|UNTIL|Return|RETURN)\b(.*)$", ln)
        if not m: continue
        t = re.sub(r"[\^_]\{[^}]*\}|[\^_]\w", "", m.group(1))
        nums += [x for x in re.findall(r"(?<![\w.\\])\d+(?:\.\d+)?", t) if sig_digits(x) >= 3]
    if nums: say("WARN", f"{tag}: \\State 里有结果数字 {nums[:5]} —— 伪代码不写结果数字，数字属于表和正文")
    if FAILS == f0 and WARNS == w0: say("PASS", f"{tag}: {nlines} 行" + (f"，锚点 {row['source']}，符号 / 形状一致" if node is not None else "") + (f"，{n_ok} 个 \\Require 数值与 ref run 一致" if n_ok else ""))

def run_checks(root, st, text, tex):
    """the seven checks over every algorithm environment in the expanded .tex `text`; -> (fails, warns). Prints [PASS|WARN|FAIL] lines."""
    global FAILS, WARNS
    FAILS = WARNS = 0
    rows = [r for r in (st.get("algorithms") or []) if isinstance(r, dict) and r.get("id") is not None]
    blocks = find_blocks(text); by_id = {str(r["id"]): r for r in rows}
    pk = {p.strip() for g in re.findall(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", text) for p in g.split(",")}
    pseudo, old, a2e = bool(pk & {"algpseudocode", "algpseudocodex", "algorithmicx"}), "algorithmic" in pk, "algorithm2e" in pk
    allb = "\n".join(b["inner"] for b in blocks)
    if blocks:
        if not pk & {"algorithm", "algorithm2e"}: say("FAIL", "有 algorithm 环境但没有 \\usepackage{algorithm}（或 algorithm2e）")
        if a2e and (pseudo or old): say("FAIL", "algorithm2e 与 algorithmic / algpseudocode 同时加载：两套互相冲突（Command \\algorithm already defined），只留一套")
        if re.search(r"\\begin\{algorithmic\}", allb) and not (pseudo or old): say("FAIL", "用了 algorithmic 环境但没有 \\usepackage{algpseudocode}（或 algorithmic）")
        if A2E.search(allb) and not a2e: say("FAIL", "用了 algorithm2e 的命令（\\KwIn / \\KwOut）但没有 \\usepackage{algorithm2e}")
        if CAMEL.search(allb) and old and not pseudo: say("FAIL", "块里是 algpseudocode 的命令（\\State / \\Require / \\EndFor）但加载的是 algorithmic 包（它的命令是 \\STATE / \\REQUIRE）—— 换成 \\usepackage{algpseudocode}")
        if UPPER.search(allb) and pseudo and not old: say("FAIL", "块里是 algorithmic 的命令（\\STATE / \\REQUIRE）但加载的是 algpseudocode（它的命令是 \\State / \\Require）—— 统一一套")
    rest = text
    for b in sorted(blocks, key=lambda b: -b["span"][0]): rest = rest[:b["span"][0]] + rest[b["span"][1]:]
    refs = {r.strip() for g in re.findall(r"\\(?:ref|autoref|cref|Cref|pageref|nameref)\{([^}]+)\}", rest) for r in g.split(",")}
    ref, ref_src = ref_args(root, st); seen = set()
    for i, b in enumerate(blocks, 1):
        lab = b["label"]; aid = (lab[4:] if lab and lab.startswith("alg:") else lab) if lab else None; tag = f"algorithm #{i}" + (f" ({lab})" if lab else "")
        if not b["caption"]: say("FAIL", f"{tag} 没有 \\caption")
        if not lab: say("FAIL", f"{tag} 没有 \\label{{alg:...}}（正文无法 \\ref 它）")
        else:
            if not lab.startswith("alg:"): say("WARN", f"{tag}: label 惯例写成 alg:xxx")
            if lab not in refs: say("FAIL", f"{tag}: 正文没有 \\ref / \\cref / \\autoref 引用它（无人引用的算法块与无人引用的图同罪）")
        row = by_id.get(aid) if aid else None
        if aid: seen.add(aid)
        if lab and not row: say("WARN", f"{tag}: 伪代码没有 source 锚点（research-state.yaml 的 algorithms 里没有 id={aid}）—— 登记 {{id, source: file:function, params}}，否则无法核对它描述的是跑出结果的那个函数")
        check_block(b, aid or f"#{i}", row, root, st, ref, ref_src)
    for r in rows:
        if str(r["id"]) not in seen: say("WARN", f"algorithms.{r['id']} 登记了但 {os.path.relpath(tex, root).replace(os.sep, '/')} 里没有 \\label{{alg:{r['id']}}} 的 algorithm 块")
    return FAILS, WARNS

def check(a):
    import latex_check as lc
    root = os.path.abspath(a.project); st = load_state(root, a.state)
    tex = os.path.join(root, a.tex or os.path.join(((st.get("target") or {}).get("latex_dir")) or "paper/latex", "main.tex"))
    if not os.path.exists(tex): say("FAIL", f"{os.path.relpath(tex, root)} 不存在"); print("\n1 FAIL"); sys.exit(1)
    text, files = lc.expand_inputs(tex); f, w = run_checks(root, st, text, tex); f += lc.FAILS
    if not find_blocks(text) and not (st.get("algorithms") or []): print("[INFO] algorithm: 没有 algorithm 环境，也没有 state.algorithms")
    print("\n" + ("ALL PASS" if f == 0 else f"{f} FAIL")); sys.exit(0 if f == 0 else 1)

# ------------------------------------------------------------------ calibrate (published papers)
FAMILIES = {"cs_conf": ["CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "AAAI", "IJCAI", "MICCAI", "WACV", "MM"], "cs_journal": ["TMI", "MedIA", "TIP", "TPAMI", "IJCV", "TKDE", "TMM", "InfoFusion", "Bioinformatics"]}
ALG_CAP = re.compile(r"^\s*(?:Algorithm|ALGORITHM)\s+(\d{1,2})\s*(?:[:.](?!\d)|$|\s+(?=[A-Z(\u201c\"]|\d+[A-Za-z]))")
METHOD_HEAD = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+|[IVX]{1,4}\.\s+)?(?:(?:Proposed |Our )?(?:Methods?|Methodology|Approach|Framework|Model|Algorithm)s?(?: Overview| Description| Details)?|Materials and Methods|Online Methods|Problem (?:Formulation|Statement|Setup)|Preliminaries)\s*$", re.I | re.M)

def analyze_pdf(path, max_pages=14):
    """-> {algs, method, pages} for one PDF (first `max_pages` pages of text); {err} when it cannot be read."""
    try:
        import fitz; fitz.TOOLS.mupdf_display_errors(False)
        d = fitz.open(path); n = min(max_pages, len(d)); algs = set(); method = False
        for i in range(n):
            t = d[i].get_text()
            if METHOD_HEAD.search(t): method = True
            algs |= {int(m.group(1)) for l in t.splitlines() for m in [ALG_CAP.match(l)] if m}
        return {"algs": len(algs), "method": method, "pages": n}
    except Exception as ex: return {"err": repr(ex)[:80]}

def pct(xs, q):
    xs = sorted(xs)
    if not xs: return 0.0
    k = (len(xs) - 1) * q; f = int(k); c = min(f + 1, len(xs) - 1); return xs[f] + (xs[c] - xs[f]) * (k - f)

def candidates(corpus, venue, family, min_year):
    out = []
    if family == "nature":
        meta = {}
        mp = os.path.join(corpus, "nature", "metadata", "journals.csv")
        if os.path.exists(mp):
            csv.field_size_limit(1 << 28)
            for r in csv.DictReader(io.open(mp, encoding="utf-8-sig")): meta[r["openalex_id"]] = r.get("type", "")
        base = os.path.join(corpus, "nature", venue)
        for y in sorted(os.listdir(base)):
            if y.isdigit() and int(y) >= min_year:
                out += [os.path.join(base, y, f) for f in sorted(os.listdir(os.path.join(base, y))) if f.lower().endswith(".pdf") and (not meta or meta.get(os.path.splitext(f)[0], "article") == "article")]
    else:
        base = os.path.join(corpus, venue)
        for y in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            if y.isdigit() and int(y) >= min_year: out += [os.path.join(base, y, f) for f in sorted(os.listdir(os.path.join(base, y))) if f.lower().endswith(".pdf")]
    return out

def summarise(family, venue, rs):
    ok = [r for r in rs if "err" not in r]; mp = [r for r in ok if r["method"]]; wa = [r["algs"] for r in mp if r["algs"] >= 1]
    return {"family": family, "venue": venue, "n": len(ok), "n_method_papers": len(mp), "share_with_algorithm": round(len(wa) / len(mp), 4) if mp else 0.0,
            "p50_count": round(pct(wa, .5), 2), "p90_count": round(pct(wa, .9), 2), "max_count": max(wa) if wa else 0}

def calibrate(a):
    from concurrent.futures import ProcessPoolExecutor
    corpus = os.path.abspath(a.papers); venues = [("cs_conf", v) for v in FAMILIES["cs_conf"]] + [("cs_journal", v) for v in FAMILIES["cs_journal"]]
    nb = os.path.join(corpus, "nature")
    if os.path.isdir(nb): venues += [("nature", j) for j in sorted(os.listdir(nb)) if j != "metadata" and os.path.isdir(os.path.join(nb, j))]
    rows, per, allp = [], {}, []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for fam, v in venues:
            try: c = candidates(corpus, v, fam, a.min_year)
            except OSError as e: print(f"{fam}/{v}: skip ({e})"); continue
            random.Random(f"{a.seed}-{v}").shuffle(c); c = c[:a.per_venue]
            if not c: print(f"{fam}/{v}: no papers since {a.min_year}"); continue
            rs = list(ex.map(analyze_pdf, c, chunksize=2)); per.setdefault(fam, []).extend(r for r in rs if "err" not in r)
            allp += [{"family": fam, "venue": v, "pdf": os.path.relpath(p, corpus).replace("\\", "/"), **r} for p, r in zip(c, rs)]
            s = summarise(fam, v, rs); rows.append(s); print(f"{fam}/{v}: n={s['n']} (of {len(c)} sampled, {sum('err' in r for r in rs)} unreadable) method={s['n_method_papers']} share={s['share_with_algorithm']:.2f} max={s['max_count']}", flush=True)
    fam_rows = [summarise(f, "ALL", rs) for f, rs in per.items()]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cols = ["family", "venue", "n", "n_method_papers", "share_with_algorithm", "p50_count", "p90_count", "max_count"]
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# algorithm norms: {datetime.date.today().isoformat()}, seed {a.seed}, <= {a.per_venue} papers per venue (published {a.min_year}+), n = {sum(r['n'] for r in rows)} papers read (first 14 pages, PyMuPDF text); regenerate: make_algorithm.py calibrate\n")
        f.write("# share_with_algorithm = among papers with a Method/Approach/Framework heading in those pages; p50/p90/max_count = algorithm blocks per paper among papers that have >= 1; nature: Methods usually sit after page 14, counts are a floor\n")
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r["family"], r["venue"]))); w.writerows(fam_rows)
    if a.per_paper:
        with io.open(a.per_paper, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["family", "venue", "pdf", "algs", "method", "pages", "err"], restval=""); w.writeheader(); w.writerows(allp)
    print(f"-> {a.out}")
    for r in fam_rows: print(f"  {r['family']} ALL: n={r['n']} method={r['n_method_papers']} share={r['share_with_algorithm']:.3f} p50={r['p50_count']} p90={r['p90_count']} max={r['max_count']}")
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("skeleton"); s.add_argument("--id", required=True); s.add_argument("--project", default="."); s.add_argument("--force", action="store_true")
    c = sub.add_parser("check"); c.add_argument("--project", default="."); c.add_argument("--tex", default=""); c.add_argument("--state", default="research-state.yaml")
    k = sub.add_parser("calibrate"); k.add_argument("--papers", default="Z:/LDCT/papers"); k.add_argument("--out", default=NORMS_CSV); k.add_argument("--per-venue", type=int, default=40); k.add_argument("--seed", type=int, default=20261023)
    k.add_argument("--min-year", type=int, default=2023); k.add_argument("--workers", type=int, default=8); k.add_argument("--per-paper", default="")
    a = ap.parse_args()
    {"skeleton": skeleton, "check": check, "calibrate": calibrate}[a.cmd](a)
