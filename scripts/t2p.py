# -*- coding: utf-8 -*-
"""topic-to-paper front door. One command, reads research-state.yaml, runs every gate that applies, prints a status board.

  python t2p.py status  [--project .]          where am I: last check time, every gate's status, what to do next (reads state.gates)
  python t2p.py check   [--project .] [--net] [--no-write]
                                               run every gate whose inputs exist and WRITE the board back into state.gates
                                               (--net also resolves DOIs via CrossRef; --no-write for a dry run)
  python t2p.py init    [--project .] [--venue V] [--field F] [--branch research|survey]
                        [--entry topic_only|topic_plus_data|have_results|have_draft|have_reviews]
                                               create the workspace from templates; --entry says where the project starts
  python t2p.py lock    [--project .]          hash prereg.md (research) / protocol.md (survey) into gates.G2.prereg_sha256
                                               / gates.G-S2.protocol_sha256 — do not edit that field by hand
  python t2p.py doctor  [--skills]             verify python deps and the scripts themselves

Entry points: a project that starts from an existing draft (have_draft) or from reviews (have_reviews) has no P1–P5
artefacts, so G1b/G2/G3/G4/G5 are shown as N/A instead of PENDING while their inputs are absent and never become the
"next step"; the moment the inputs appear (prereg.md, runs/, results/, figures.csv) the gate runs normally. have_results
only waives G1b. A template that was copied by init and never edited counts as absent (compared with templates/, not by
magic substrings).

Gate → script mapping (inputs decide whether a gate runs):
  G0  state.target.guide_file exists                       (no script; file check)
  G1  literature/corpus.csv or refs.bib                    gate_check.py refs --no-net (unless --net)
  G2  prereg.md                                            prereg_check.py
  G3  state.audits.runs_dir exists                         audit_check.py
  G3b state.audits.code_dirs holds .py files (research)    instrument_check.py: every pretrained model / harness / train loop has a known-answer check + a broken-input control
  G4  results/main.csv                                     results_check.py + ablation_plan.py resolve
  G5  figures.csv                                          gate_check.py dpi (+ make_architecture.py check when figures/arch/*.yaml exist; + figure_plan.py check: planned figures drawn, figures / claims in the plan)
  G6  paper/manuscript.md                                  gate_check.py floats acronyms scope numbers limits (+refs with --net)
  G6d paper/latex/main.tex (LaTeX projects only)           latex_check.py check: class matches venue, all figures PDF, panels via subfigure, algorithm blocks (make_algorithm.py check)
  G6e paper/claims.csv with rows                           claims_check.py: headline sentences ↔ claims rows, each row computed from results, strong scope ↔ scope_words
  G6f paper/manuscript.md (research)                      readability_check.py: numbers / semicolons / sentence length vs published norms, contribution bullets, protocol vocabulary, catalogue paragraphs
  G7  paper/review_log.md                                  review_check.py
  G8  submission/ with cover_letter.md|title_page.md|…     gate_check.py submission
A gate whose script crashes (traceback, or non-zero exit without a [FAIL] line) is reported as CRASH and counted as a
FAIL: a gate that did not run must never read as PASS.
Exit code = number of gates that FAILed or CRASHed."""
import argparse, glob, io, os, re, shutil, subprocess, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PY = sys.executable

def load_state(p):
    if not os.path.exists(p): return None
    try:
        import yaml
        return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}
    except ImportError:
        print("需要 pyyaml: pip install pyyaml"); sys.exit(2)

CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}   # gate scripts print ✓ ⊆ −; a GBK console must not kill them
GBK_ENV = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "gbk"}      # doctor: the hostile default of a Chinese Windows console
_CRASH_NOTES = []

def run(args, cwd):
    """Run one gate script -> (returncode, fails, warns, out). A script that crashed (traceback on stderr, or non-zero exit
    with no [FAIL] line) gets a leading [CRASH] line in `out`, so verdict() reports CRASH and never PASS."""
    r = subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=CHILD_ENV)
    out = r.stdout + r.stderr
    fails = len(re.findall(r"^\[FAIL\]", out, re.M)); warns = len(re.findall(r"^\[WARN\]", out, re.M))
    if "Traceback (most recent call last)" in r.stderr or (r.returncode != 0 and fails == 0):
        last = next((l for l in reversed(out.strip().splitlines()) if l.strip()), "")
        note = f"[CRASH] {os.path.basename(args[0])} exit {r.returncode}: {last[:160]}"
        _CRASH_NOTES.append(note); out = note + "\n" + out
    return r.returncode, fails, warns, out

def verdict(fails, *outs):
    """PASS / FAIL / CRASH for one gate, from its fail count and the raw output(s) of the script(s) it ran."""
    if any(o.startswith("[CRASH]") for o in outs): return "CRASH"
    return "FAIL" if fails else "PASS"

def exists(root, *parts):
    return os.path.exists(os.path.join(root, *parts))

ENTRIES = ("topic_only", "topic_plus_data", "have_results", "have_draft", "have_reviews")
# gates whose inputs an entry point legitimately lacks: N/A (not PENDING) while the inputs are absent; run normally once they exist
SKIP_BY_ENTRY = {"have_results": {"G1b"}, "have_draft": {"G1b", "G2", "G3", "G3b", "G4", "G5"}, "have_reviews": {"G1b", "G2", "G3", "G3b", "G4", "G5"}}
ENTRY_PHASE = {"topic_only": "P0", "topic_plus_data": "P0", "have_results": "P4", "have_draft": "P6", "have_reviews": "P7"}
GATE_ORDER = ["G0", "G1", "G1b", "G2", "G3", "G3b", "G4", "G5", "G6", "G6b", "G6c", "G6d", "G6e", "G6f", "G7", "G8", "G-S0", "G-S1", "G-S2", "G-S3", "G-S4", "G-S5", "G-S6"]
SURVEY_GATES = ["G0", "G1", "G-S0", "G-S1", "G-S2", "G-S3", "G-S4", "G-S5", "G-S6"]

def gate_key(g):
    return (GATE_ORDER.index(g) if g in GATE_ORDER else len(GATE_ORDER), g)

def _norm(s):
    return "\n".join(l.rstrip() for l in s.replace("\r\n", "\n").split("\n")).strip()

def templated(root, rel, tpl):
    """True when <root>/<rel> is still a verbatim copy of templates/<tpl> (line endings and trailing blanks ignored)."""
    fp, tp = os.path.join(root, rel), os.path.join(SKILL, "templates", tpl)
    if not (os.path.exists(fp) and os.path.exists(tp)): return False
    return _norm(io.open(fp, encoding="utf-8").read()) == _norm(io.open(tp, encoding="utf-8").read())

def n_runs(root, runs_dir):
    """真正的 run 目录数，与 audit_check.collect_runs 同一判据（_ 与 . 开头的不算）。
    不能用 os.listdir 非空来判断：`t2p.py init` 自己往 runs/ 放了 _run_card_template.md，
    否则新项目的 runs/ 永远"非空"，G3 的远程实验包分支一辈子触发不到。"""
    d = os.path.join(root, runs_dir)
    if not os.path.isdir(d): return 0
    return sum(1 for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)) and not x.startswith(("_", ".")))


def data_rows(root, rel):
    """number of non-empty lines after the header of a csv; 0 when the file is missing"""
    p = os.path.join(root, rel)
    if not os.path.exists(p): return 0
    return max(len([l for l in io.open(p, encoding="utf-8-sig").read().splitlines() if l.strip()]) - 1, 0)

def dump_inline(d):
    import yaml
    return yaml.safe_dump(d, default_flow_style=True, allow_unicode=True, width=10**6, sort_keys=False).strip()

GATE_PAT = re.compile(r"^(\s+)(G[\w-]+):\s*(\{.*\})\s*(#.*)?$")

def set_gate_key(sp, gate, key, value):
    """Set one key inside the inline dict of `gate` in the gates: block, whatever the current quoting is, keeping the
    other keys, the comments and the line ending. Returns True when the gate line was found."""
    import yaml
    txt = io.open(sp, encoding="utf-8").read(); eol = "\r\n" if "\r\n" in txt else "\n"
    lines = txt.replace("\r\n", "\n").split("\n")
    for i, ln in enumerate(lines):
        m = GATE_PAT.match(ln)
        if not m or m.group(2) != gate: continue
        d = yaml.safe_load(m.group(3)) or {}
        d[key] = value
        lines[i] = f"{m.group(1)}{gate}: {dump_inline(d)}" + (f"  {m.group(4)}" if m.group(4) else "")
        io.open(sp, "w", encoding="utf-8", newline="").write(eol.join(lines))
        return True
    return False

def lock(root):
    """Hash the preregistration (research) or protocol (survey) and write it into its gate entry. Doing this by hand with
    a regex breaks as soon as `check` has rewritten the gates block with different quoting, so it is a command."""
    sp = os.path.join(root, "research-state.yaml")
    st = load_state(sp)
    if st is None: print("[FAIL] research-state.yaml 不存在：先 `t2p.py init`"); return 1
    survey = (st.get("branch") == "survey")
    doc, gate, key = ("protocol.md", "G-S2", "protocol_sha256") if survey else ("prereg.md", "G2", "prereg_sha256")
    dp = os.path.join(root, doc)
    if not os.path.exists(dp): print(f"[FAIL] {doc} 不存在"); return 1
    if templated(root, doc, doc): print(f"[FAIL] {doc} 仍是 templates/{doc} 的原样副本，没有内容可锁"); return 1
    import hashlib
    sha = hashlib.sha256(io.open(dp, encoding="utf-8").read().encode("utf-8")).hexdigest()
    old = ((st.get("gates") or {}).get(gate) or {}).get(key) or ""
    if not set_gate_key(sp, gate, key, sha):
        print(f"[FAIL] gates 块里没有 {gate} 行：先跑一次 `t2p.py check`"); return 1
    if old and old != sha:
        print(f"[WARN] {doc} 的锁被更新（旧 {old[:12]}… → 新 {sha[:12]}…）：改口径要同时在 state.experiments.convention_changes 留记录")
    print(f"[PASS] {doc} 已锁定 → gates.{gate}.{key} = {sha}")
    return 0

def write_gates(sp, board):
    """Write the board into the `gates:` block of research-state.yaml in place, one inline dict per gate. Every comment
    and every extra key (prereg_sha256, protocol_sha256, ...) is kept; gates not yet listed are appended to the block."""
    import yaml, datetime
    txt = io.open(sp, encoding="utf-8").read(); eol = "\r\n" if "\r\n" in txt else "\n"
    lines = txt.replace("\r\n", "\n").split("\n")
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    gi = next((i for i, l in enumerate(lines) if re.match(r"^gates:\s*(#.*)?$", l)), None)
    if gi is None:
        while lines and lines[-1] == "": lines.pop()
        lines += ["", "gates:"]; gi = len(lines) - 1
    pat = GATE_PAT
    at = {}; indent = "  "; last = gi; j = gi + 1
    while j < len(lines) and (lines[j].strip() == "" or lines[j][:1] in (" ", "\t")):
        m = pat.match(lines[j])
        if m: at[m.group(2)] = j; indent = m.group(1); last = j
        j += 1
    for g, status, detail in board:
        new = {"status": status.lower(), "evidence": detail[:140], "checked": stamp}
        if g in at:
            m = pat.match(lines[at[g]]); old = yaml.safe_load(m.group(3)) or {}
            for k, v in old.items():
                if k not in new: new[k] = v
            lines[at[g]] = f"{indent}{g}: {dump_inline(new)}" + (f"  {m.group(4)}" if m.group(4) else "")
        else:
            last += 1; lines.insert(last, f"{indent}{g}: {dump_inline(new)}"); at[g] = last
    io.open(sp, "w", encoding="utf-8", newline="").write(eol.join(lines))

def check(root, net, write=True):
    st = load_state(os.path.join(root, "research-state.yaml"))
    if st is None:
        print("[FAIL] research-state.yaml 不存在：先 `t2p.py init`"); return 1
    S = lambda n: os.path.join(HERE, n)
    tgt = st.get("target") or {}; aud = st.get("audits") or {}; res = st.get("results") or {}
    manuscript = "paper/manuscript.md"
    survey = (st.get("branch") == "survey")
    entry = (st.get("project") or {}).get("entry") or "topic_only"
    na = SKIP_BY_ENTRY.get(entry, set())
    board = []   # (gate, status, detail)
    def rec(g, status, detail):
        if survey and g in ("G2", "G3", "G3b", "G4", "G6e", "G6f"): return      # research-only gates are meaningless for a survey (G-S5 is the survey claim gate)
        if status == "PENDING" and g in na: status, detail = "N/A", f"entry={entry}：无此阶段产物，不要求（文件出现即照常检查）；" + detail
        if status == "CRASH": detail += "；" + "；".join(_CRASH_NOTES); _CRASH_NOTES.clear()
        board.append((g, status, detail)); print(f"[{status}] {g}: {detail}")
    # G0
    gf = tgt.get("guide_file") or "submission/guide.txt"
    if exists(root, gf) and tgt.get("venue"): rec("G0", "PASS", f"{gf} 存在，venue={tgt['venue']}")
    else: rec("G0", "PENDING", f"缺 {gf} 或 target.venue")
    # G1
    bib = next((b for b in ("literature/refs.bib", "paper/refs.bib") if exists(root, b)), None)
    if bib:
        stub = os.path.join(root, "_t2p_stub.md"); io.open(stub, "w", encoding="utf-8").write("# stub\n\n## References\n")
        rc, f, w, out = run([S("gate_check.py"), "refs", "--manuscript", "_t2p_stub.md", "--bib", bib] + ([] if net else ["--no-net"]), root)
        os.remove(stub)
        if net: rec("G1", verdict(f, out), f"{bib}: {f} FAIL / {w} WARN" + ("" if f else "，DOI 全部解析"))
        else: rec("G1", "SKIP", f"{bib} 存在；加 --net 才解析 DOI")
    else: rec("G1", "PENDING", "无 literature/refs.bib 或 paper/refs.bib")
    # G1b: gap_map 判定 + transfer_scan（研究分支的 P1 第二产物）
    if not survey and (exists(root, "literature/gap_map.md") or exists(root, "literature/transfer_scan.md")):
        rc, f, w, out = run([S("transfer_scan.py"), "check"], root)
        mv = re.search(r"P1 判定 (no-go|go)", out)
        rec("G1b", verdict(f, out), f"gap_map/transfer_scan {f} FAIL" + (f"，判定 {mv.group(1)}" if mv else "") + ("；no-go 是合法出口，不进 P2" if mv and mv.group(1) == "no-go" else ""))
    elif not survey: rec("G1b", "PENDING", "无 literature/gap_map.md 与 transfer_scan.md（P1 两个必产物）")
    # G2
    if exists(root, "prereg.md") and not templated(root, "prereg.md", "prereg.md"):
        rc, f, w, out = run([S("prereg_check.py")], root); rec("G2", verdict(f, out), f"prereg_check {f} FAIL / {w} WARN")
    else: rec("G2", "PENDING", "prereg.md 不存在或仍是模板")
    # G3
    rd = aud.get("runs_dir", "runs") if aud else "runs"
    if aud and (aud.get("leak_flags") or aud.get("critical_params") or aud.get("inputs")) and n_runs(root, rd):
        rc, f, w, out = run([S("audit_check.py")], root); rec("G3", verdict(f, out), f"audit_check {f} FAIL / {w} WARN")
    elif st.get("bundle") and (st["bundle"].get("matrix") or {}).get("ref") and (st["bundle"].get("matrix") or {}).get("baselines"):   # template ref alone is not a configured matrix
        rc, f, w, out = run([S("bundle.py"), "check"], root); m = re.search(r"\[INFO\] matrix: (\d+ runs[^\n]*)", out)
        rec("G3", verdict(f, out), f"bundle check {f} FAIL（远程实验包，runs/ 尚空）" + (f"；{m.group(1)}" if m else "") + "；结果回来后 audit_check 再跑")
    else: rec("G3", "PENDING", "state.audits 的 leak_flags/critical_params/inputs 未填，或 runs/ 为空（远程跑则填 state.bundle.matrix）")
    # G3b: instrument calibration — known-answer check + broken-input control for every pretrained model / external harness / train loop
    sys.path.insert(0, HERE); from instrument_check import py_files   # same file set the gate scans: code_dirs plus any other experiment .py in the project
    if py_files(aud.get("code_dirs") or [], root):
        rc, f, w, out = run([S("instrument_check.py")], root); rec("G3b", verdict(f, out), f"instrument {f} FAIL / {w} WARN")
    else: rec("G3b", "PENDING", "项目里还没有实验代码（.py）：登记 state.instruments（预训练组件/外部框架/自写训练循环的已知答案 + 破坏对照）")
    # G4
    if exists(root, res.get("main_table", "results/main.csv")):
        rc, f, w, out = run([S("results_check.py")], root); f2 = w2 = 0; out2 = ""
        if exists(root, res.get("ablation_table", "results/ablation.csv")):
            rc2, f2, w2, out2 = run([S("ablation_plan.py"), "resolve"], root)
        rec("G4", verdict(f + f2, out, out2), f"results_check {f} FAIL / {w} WARN；ablation resolve {f2} FAIL")
    else: rec("G4", "PENDING", f"无 {res.get('main_table', 'results/main.csv')}")
    # G5
    if data_rows(root, "figures.csv") >= 1 and not templated(root, "figures.csv", "figures.csv"):
        rc, f, w, out = run([S("gate_check.py"), "dpi", "--manuscript", manuscript if exists(root, manuscript) else "figures.csv"], root)
        detail = f"dpi {f} FAIL / {w} WARN"; outs = [out]; f_all = f
        if glob.glob(os.path.join(root, "figures", "arch", "*.yaml")):   # traced method-overview figures: re-trace the model and compare (make_architecture.py check)
            rc2, f2, w2, out2 = run([S("make_architecture.py"), "check"], root)
            detail += f"；architecture {f2} FAIL / {w2} WARN"; outs.append(out2); f_all += f2
        rc3, f3, w3, out3 = run([S("figure_plan.py"), "check"], root)   # every planned figure drawn, every figure / numeric claim in the plan (paper/figure_plan.csv; no plan = WARN)
        detail += f"；plan {f3} FAIL / {w3} WARN"; outs.append(out3); f_all += f3
        rec("G5", verdict(f_all, *outs), detail)
    else: rec("G5", "PENDING", "figures.csv 不存在、无数据行或仍是模板")
    # G6
    if exists(root, manuscript):
        subs = ["floats", "acronyms", "scope", "numbers", "limits"] + (["refs"] if net and exists(root, "paper/refs.bib") else [])
        tot_f = 0; parts = []; outs = []
        for g in subs:
            rc, f, w, out = run([S("gate_check.py"), g, "--manuscript", manuscript, "--bib", "paper/refs.bib"] + (["--supplement", "paper/supplement.md"] if exists(root, "paper/supplement.md") else []), root)
            tot_f += f; parts.append(f"{g}:{f}F/{w}W"); outs.append(out)
        rec("G6", verdict(tot_f, *outs), "  ".join(parts) + ("" if net else "  (refs 需 --net)"))
        # G6b: must-write checklist from P1–P4 artefacts
        if exists(root, "paper/draft_plan.json"):
            rc, f, w, out = run([S("draft_plan.py"), "check"], root); m = re.search(r"(\d+)/(\d+) 项已写", out)
            rec("G6b", verdict(f, out), f"draft_plan {f} FAIL / {w} WARN" + (f"，{m.group(0)}" if m else ""))
        else: rec("G6b", "PENDING", "无 paper/draft_plan.json：写作前先 `draft_plan.py plan` 生成各节必写清单")
        # G6c: manuscript shape vs. target family (cs_conf | cs_journal | nature)
        rc, f, w, out = run([S("shape_check.py")], root); m = re.search(r"family = (\w+)", out)
        rec("G6c", verdict(f, out), f"shape {f} FAIL / {w} WARN" + (f"，family={m.group(1)}" if m else ""))
        # G6e: claim layer — every headline sentence is a claims.csv row and every row is computed from the result files
        if data_rows(root, "paper/claims.csv") >= 1 and not templated(root, "paper/claims.csv", "claims.csv"):
            rc, f, w, out = run([S("claims_check.py")], root); m = re.search(r"(\d+)/(\d+)", out)
            rec("G6e", verdict(f, out), f"claims {f} FAIL / {w} WARN")
        else: rec("G6e", "PENDING", "paper/claims.csv 无主张行或仍是模板：每条主张一行（evidence_key + expected 让它可机械核验）")
        # G6f: readability — numbers per 1k words, contribution bullets, protocol vocabulary, catalogue paragraphs vs references/readability-norms.csv
        rc, f, w, out = run([S("readability_check.py")], root); m = re.search(r"family = (\w+)", out)
        rec("G6f", verdict(f, out), f"readability {f} FAIL / {w} WARN" + (f"，family={m.group(1)}" if m else ""))
    else: rec("G6", "PENDING", f"无 {manuscript}")
    # G6d: LaTeX submission form, only for projects that write in the venue template
    if exists(root, tgt.get("latex_dir") or "paper/latex", "main.tex"):
        rc, f, w, out = run([S("latex_check.py"), "check"], root); rec("G6d", verdict(f, out), f"latex {f} FAIL / {w} WARN")
    # G7
    if exists(root, "paper/review_log.md"):
        rc, f, w, out = run([S("review_check.py")], root)
        rec("G7", verdict(f, out), f"review_check {f} FAIL / {w} WARN")
    else: rec("G7", "PENDING", "无 paper/review_log.md")
    # G8
    if any(exists(root, "submission", x) for x in ("cover_letter.md", "title_page.md", "highlights.md", "blind.md")):
        rc, f, w, out = run([S("gate_check.py"), "submission", "--manuscript", manuscript], root); rec("G8", verdict(f, out), f"submission {f} FAIL / {w} WARN")
    else: rec("G8", "PENDING", "submission/ 无 cover_letter.md / title_page.md / highlights.md / blind.md")
    # survey branch gates (only when state.branch == survey or state.survey is filled)
    sv = st.get("survey") or {}
    sv_filled = any(sv.get(k) for k in ("scope_in", "scope_out", "axis", "thesis"))   # path/threshold keys are template defaults; only content keys make it a survey
    if (st.get("branch") == "survey") or sv_filled:
        rc, f, w, out = run([S("survey_check.py"), "scope"], root); rec("G-S0", verdict(f, out), f"scope {f} FAIL / {w} WARN")
        if exists(root, sv.get("search_log", "literature/search_log.json")) or exists(root, sv.get("candidates", "literature/candidates.csv")):
            rc, f, w, out = run([S("survey_check.py"), "search"], root); rec("G-S1", verdict(f, out), f"search {f} FAIL / {w} WARN")
        else: rec("G-S1", "PENDING", "无 literature/search_log.json 与 candidates.csv（S1 产物：每源检索式+日期+计数，候选表带标识符）")
        if exists(root, "protocol.md") and not templated(root, "protocol.md", "protocol.md"):
            rc, f, w, out = run([S("survey_check.py"), "protocol", "--codebook", sv.get("codebook", "coding/codebook.md")], root); rec("G-S2", verdict(f, out), f"protocol {f} FAIL / {w} WARN")
        else: rec("G-S2", "PENDING", "protocol.md 不存在或仍是模板")
        if exists(root, sv.get("screening_sheet", "coding/screening_sheet.csv")):
            rc, f, w, out = run([S("survey_check.py"), "coding"], root); rec("G-S3", verdict(f, out), f"coding {f} FAIL / {w} WARN")
        else: rec("G-S3", "PENDING", f"无 {sv.get('screening_sheet', 'coding/screening_sheet.csv')}")
        td = os.path.join(root, sv.get("tables_dir", "tables"))
        if os.path.isdir(td) and any(x.endswith(".csv") for x in os.listdir(td)):
            rc, f, w, out = run([S("survey_check.py"), "tables"], root); rec("G-S4", verdict(f, out), f"tables {f} FAIL / {w} WARN")
        else: rec("G-S4", "PENDING", f"{sv.get('tables_dir', 'tables')}/ 无 csv（S4 产物：汇总表落盘 + coding/*summary*.py --verify + coverage.csv）")
        cl = sv.get("claims", "paper/claims.csv")
        if data_rows(root, cl) >= 1 and not templated(root, cl, "claims.csv"):
            rc, f, w, out = run([S("survey_check.py"), "claims"], root); rec("G-S5", verdict(f, out), f"claims {f} FAIL / {w} WARN")
        else: rec("G-S5", "PENDING", f"{cl} 不存在、无数据行或仍是模板")
    nf = sum(1 for _, s, _ in board if s in ("FAIL", "CRASH"))
    first_bad = next((g for g, s, _ in board if s in ("FAIL", "CRASH", "PENDING")), None)
    print(f"\n== {nf} 道关口 FAIL/CRASH；entry={entry}；phase.current = {(st.get('phase') or {}).get('current', '?')}；下一步：{'修 ' + first_bad if first_bad else '全部通过，可投稿'} ==")
    if write:
        write_gates(os.path.join(root, "research-state.yaml"), board)
        print("状态板已写回 research-state.yaml 的 gates:（`t2p.py status` 读它；--no-write 可跳过）")
    print("逐条明细：对应脚本加 --project 单独跑；gate_report.md 保存最近一次 gate_check 输出")
    return nf

def status(root):
    st = load_state(os.path.join(root, "research-state.yaml"))
    if st is None: print("无 research-state.yaml"); return 1
    ph = st.get("phase") or {}; g = {k: (v or {}) for k, v in (st.get("gates") or {}).items()}; pj = st.get("project") or {}
    print(f"项目: {pj.get('title', '?')}  分支: {st.get('branch') or 'research'}  入口: {pj.get('entry') or 'topic_only'}")
    print(f"目标刊: {(st.get('target') or {}).get('venue', '?')}\n阶段: {ph.get('current', '?')}  历史: {ph.get('history', [])}")
    checked = [str(v.get("checked")) for v in g.values() if isinstance(v, dict) and v.get("checked")]
    print("上次 check: " + (max(checked) if checked else "从未 —— 下面的状态是手工填的，先跑 `t2p.py check`"))
    order = sorted(g, key=gate_key)
    for k in order: print(f"  {k:5s} {str(g[k].get('status', '?')):8s} {str(g[k].get('evidence', ''))[:100]}")
    nxt = next((k for k in order if str(g[k].get("status", "")).lower() not in ("pass", "n/a", "skip")), None)
    print(f"下一道未过关口: {nxt or '无'}")
    for doc, gt, key in (("prereg.md", "G2", "prereg_sha256"), ("protocol.md", "G-S2", "protocol_sha256")):
        if os.path.exists(os.path.join(root, doc)) and not (g.get(gt) or {}).get(key):
            print(f"{doc} 未锁定: 跑 `t2p.py lock` 把 sha256 写进 gates.{gt}.{key}")
    return 0

NEXT_BY_ENTRY = {
    "topic_only": "下载目标刊 Guide for Authors 到 submission/guide.txt，把硬规则抄进 research-state.yaml 的 target，然后 `t2p.py check`",
    "topic_plus_data": "下载目标刊 Guide for Authors 到 submission/guide.txt，把硬规则与数据可得性抄进 research-state.yaml（target / resources.data），然后 `t2p.py check`",
    "have_results": "把 runs/ 与 results/main.csv 放进来，填 state.audits 与 state.results；补一份 prereg.md 并在首行标 `post-hoc`；下载 guide.txt；然后 `t2p.py check`",
    "have_draft": "把稿子转成 paper/manuscript.md（LaTeX 用 tex_to_md.py，PDF 用 pdf_to_md.py），refs.bib 放 paper/；下载 guide.txt 填 target 硬规则；然后 `t2p.py check`（G1b–G5 显示 N/A 是正常的）",
    "have_reviews": "同 have_draft，再把审稿意见逐条整理进 paper/review_log.md（[major]/[minor] + 处置），然后 `t2p.py check`",
}

def init(root, venue, field, branch, entry="topic_only"):
    os.makedirs(root, exist_ok=True)
    for d in (("literature", "runs", "results", "figures", "paper", "submission") if branch == "research" else ("literature", "literature/pdf", "coding", "tables", "figures", "paper", "submission")): os.makedirs(os.path.join(root, d), exist_ok=True)
    tpl = os.path.join(SKILL, "templates")
    for src, dst in (("research-state.yaml", "research-state.yaml"), ("prereg.md", "prereg.md"), ("protocol.md", "protocol.md"), ("codebook.md", "coding/codebook.md"), ("claims.csv", "paper/claims.csv"), ("numbers.csv", "paper/numbers.csv"), ("figures.csv", "figures.csv"), ("run-card.md", "runs/_run_card_template.md"), ("submission-checklist.md", "submission/checklist.md")):
        if branch == "survey" and src in ("prereg.md", "run-card.md"): continue
        if branch == "research" and src in ("protocol.md", "codebook.md"): continue
        os.makedirs(os.path.dirname(os.path.join(root, dst)) or root, exist_ok=True)
        if not exists(root, dst): shutil.copy(os.path.join(tpl, src), os.path.join(root, dst))
    sp = os.path.join(root, "research-state.yaml"); s = io.open(sp, encoding="utf-8").read()
    s = re.sub(r'(?m)^branch:[^\n]*$', f'branch: {branch}', s, count=1) if re.search(r"(?m)^branch:", s) else s.replace("project:\n", f"branch: {branch}            # research | survey\n\nproject:\n", 1)
    if venue: s = re.sub(r'(?m)^(  venue:)[^\n]*$', r'\1 "%s"' % venue, s, count=1)
    if field: s = re.sub(r'(?m)^(  field:)[^\n]*$', r'\1 "%s"' % field, s, count=1)
    s = re.sub(r'(?m)^(  started:)[^\n]*$', r'\1 "%s"' % __import__("datetime").date.today().isoformat(), s, count=1)
    s = re.sub(r'(?m)^(  entry:)[^#\n]*', r'\1 %s ' % entry, s, count=1)
    s = re.sub(r'(?m)^(  current:)[^#\n]*', r'\1 %s ' % ENTRY_PHASE[entry], s, count=1)
    if branch == "survey":   # the template lists the research gates; a survey project tracks G0, G1 and G-S0..G-S6
        s = re.sub(r'(?m)^  G[1-8]\w*:.*\n', '', s)
        rows = "".join(f'  {g}: {{status: pending, evidence: ""' + (', protocol_sha256: ""' if g == "G-S2" else "") + "}\n" for g in SURVEY_GATES[1:])
        s = re.sub(r'(?m)^(  G0:.*\n)', lambda m: m.group(1) + rows, s, count=1)
    io.open(sp, "w", encoding="utf-8").write(s)
    print(f"工作区已建: {root}（branch={branch}, entry={entry}, phase={ENTRY_PHASE[entry]}）\n下一步: {NEXT_BY_ENTRY[entry]}")
    return 0

def routed_skills():
    """External skills named in references/routing.md (hyphenated lower-case tokens in backticks, e.g. `nature-figure`)."""
    p = os.path.join(SKILL, "references", "routing.md")
    if not os.path.exists(p): return []
    toks = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`", io.open(p, encoding="utf-8").read()))
    return sorted(t for t in toks if not t.startswith("-") and "." not in t and t not in ("topic-to-paper", "no-net", "topic-to"))

def installed_skills(project):
    """Directories that contain a SKILL.md under the user-level and project-level skill folders Claude Code loads from."""
    import glob
    roots = [os.path.join(os.path.expanduser("~"), ".claude", "skills"), os.path.join(os.path.expanduser("~"), ".claude", "plugins")]
    d = os.path.abspath(project)
    while True:
        roots.append(os.path.join(d, ".claude", "skills"))
        nd = os.path.dirname(d)
        if nd == d: break
        d = nd
    found = {}
    for r in roots:
        if not os.path.isdir(r): continue
        for sk in glob.glob(os.path.join(r, "**", "SKILL.md"), recursive=True):
            found.setdefault(os.path.basename(os.path.dirname(sk)), os.path.dirname(sk))
    return found

def doctor(skills=False, project="."):
    ok = True
    for mod, pipname in (("yaml", "pyyaml"), ("fitz", "pymupdf"), ("PIL", "pillow")):
        try: __import__(mod); print(f"[ok] {mod}")
        except ImportError: ok = False; print(f"[MISSING] {mod}  -> pip install {pipname}")
    import glob
    for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        if os.path.basename(f) == "t2p.py": continue
        r = subprocess.run([PY, f, "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=GBK_ENV)
        print(f"[{'ok' if r.returncode == 0 else 'BROKEN'}] {os.path.basename(f)} --help (GBK console)")
        ok &= r.returncode == 0
    for f in ("acronym-norms.csv", "venue-norms.csv", "gates.md", "lessons.md", "routing.md"):
        print(f"[{'ok' if exists(SKILL, 'references', f) else 'MISSING'}] references/{f}")
    if skills:   # informational: which external skills routing.md points at are installed where this project runs
        have = installed_skills(project); names = routed_skills(); miss = []
        for n in names:
            if n in have: print(f"[skill ok]      {n:32s} {have[n]}")
            else: miss.append(n); print(f"[skill absent]  {n:32s} -> 按 references/routing.md 的替代做法由 Claude 自己做")
        print(f"\n{len(names) - len(miss)}/{len(names)} 个路由到的外部 skill 在本机可见（用户级 ~/.claude/skills、~/.claude/plugins 与项目级 .claude/skills）；缺失不阻塞任何关口")
    return 0 if ok else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "check", "init", "lock"):
        p = sub.add_parser(name); p.add_argument("--project", default=".")
        if name == "check": p.add_argument("--net", action="store_true"); p.add_argument("--no-write", action="store_true", help="不把状态板写回 research-state.yaml")
        if name == "init":
            p.add_argument("--venue", default=""); p.add_argument("--field", default=""); p.add_argument("--branch", choices=["research", "survey"], default="research")
            p.add_argument("--entry", choices=list(ENTRIES), default="topic_only", help="项目从哪里开始：have_draft/have_reviews 时 G1b–G5 显示 N/A 而非 PENDING")
    d = sub.add_parser("doctor"); d.add_argument("--skills", action="store_true", help="也列出 routing.md 路由到的外部 skill 哪些在本机可见"); d.add_argument("--project", default=".")
    a = ap.parse_args()
    if a.cmd == "doctor": sys.exit(doctor(a.skills, a.project))
    root = os.path.abspath(a.project)
    sys.exit({"status": lambda: status(root), "check": lambda: check(root, a.net, not a.no_write),
              "init": lambda: init(root, a.venue, a.field, a.branch, a.entry), "lock": lambda: lock(root)}[a.cmd]())
