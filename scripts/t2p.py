# -*- coding: utf-8 -*-
"""topic-to-paper front door. One command, reads research-state.yaml, runs every gate that applies, prints a status board.

  python t2p.py status  [--project .]          where am I: phase, gates passed/failed/pending, what to do next
  python t2p.py check   [--project .] [--net]  run every gate whose inputs exist; --net also resolves DOIs via CrossRef
  python t2p.py init    [--project .] [--venue V] [--field F]   create the workspace from templates
  python t2p.py doctor                         verify python deps and the scripts themselves

Gate → script mapping (inputs decide whether a gate runs):
  G0  state.target.guide_file exists                       (no script; file check)
  G1  literature/corpus.csv or refs.bib                    gate_check.py refs --no-net (unless --net)
  G2  prereg.md                                            prereg_check.py
  G3  state.audits.runs_dir exists                         audit_check.py
  G4  results/main.csv                                     results_check.py + ablation_plan.py resolve
  G5  figures.csv                                          gate_check.py dpi
  G6  paper/manuscript.md                                  gate_check.py floats acronyms scope numbers limits (+refs with --net)
  G7  paper/review_log.md                                  (no script; file check + G6 rerun)
  G8  submission/ with cover_letter.md|title_page.md|…     gate_check.py submission
Exit code = number of gates that FAILed."""
import argparse, io, os, re, shutil, subprocess, sys

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

def run(args, cwd):
    r = subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    fails = len(re.findall(r"^\[FAIL\]", out, re.M)); warns = len(re.findall(r"^\[WARN\]", out, re.M))
    return r.returncode, fails, warns, out

def exists(root, *parts):
    return os.path.exists(os.path.join(root, *parts))

def check(root, net):
    st = load_state(os.path.join(root, "research-state.yaml"))
    if st is None:
        print("[FAIL] research-state.yaml 不存在：先 `t2p.py init`"); return 1
    S = lambda n: os.path.join(HERE, n)
    tgt = st.get("target") or {}; aud = st.get("audits") or {}; res = st.get("results") or {}
    manuscript = "paper/manuscript.md"
    survey = (st.get("branch") == "survey")
    board = []   # (gate, status, detail)
    def rec(g, status, detail):
        if survey and g in ("G2", "G3", "G4"): return      # research-only gates are meaningless for a survey
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
        if net: rec("G1", "FAIL" if f else "PASS", f"{bib}: {f} FAIL / {w} WARN" + ("" if f else "，DOI 全部解析"))
        else: rec("G1", "SKIP", f"{bib} 存在；加 --net 才解析 DOI")
    else: rec("G1", "PENDING", "无 literature/refs.bib 或 paper/refs.bib")
    # G1b: gap_map 判定 + transfer_scan（研究分支的 P1 第二产物）
    if not survey and (exists(root, "literature/gap_map.md") or exists(root, "literature/transfer_scan.md")):
        rc, f, w, out = run([S("transfer_scan.py"), "check"], root)
        mv = re.search(r"P1 判定 (no-go|go)", out)
        rec("G1b", "FAIL" if f else "PASS", f"gap_map/transfer_scan {f} FAIL" + (f"，判定 {mv.group(1)}" if mv else "") + ("；no-go 是合法出口，不进 P2" if mv and mv.group(1) == "no-go" else ""))
    elif not survey: rec("G1b", "PENDING", "无 literature/gap_map.md 与 transfer_scan.md（P1 两个必产物）")
    # G2
    pr = os.path.join(root, "prereg.md")
    if exists(root, "prereg.md") and "一句可证伪的话" not in io.open(pr, encoding="utf-8").read():
        rc, f, w, out = run([S("prereg_check.py")], root); rec("G2", "FAIL" if f else "PASS", f"prereg_check {f} FAIL / {w} WARN")
    else: rec("G2", "PENDING", "prereg.md 不存在或仍是模板")
    # G3
    rd = aud.get("runs_dir", "runs") if aud else "runs"
    if aud and (aud.get("leak_flags") or aud.get("critical_params") or aud.get("inputs")) and exists(root, rd) and os.listdir(os.path.join(root, rd)):
        rc, f, w, out = run([S("audit_check.py")], root); rec("G3", "FAIL" if f else "PASS", f"audit_check {f} FAIL / {w} WARN")
    elif st.get("bundle") and (st["bundle"].get("matrix") or {}).get("ref") and (st["bundle"].get("matrix") or {}).get("baselines"):   # template ref alone is not a configured matrix
        rc, f, w, out = run([S("bundle.py"), "check"], root); m = re.search(r"\[INFO\] matrix: (\d+ runs[^\n]*)", out)
        rec("G3", "FAIL" if f else "PASS", f"bundle check {f} FAIL（远程实验包，runs/ 尚空）" + (f"；{m.group(1)}" if m else "") + "；结果回来后 audit_check 再跑")
    else: rec("G3", "PENDING", "state.audits 的 leak_flags/critical_params/inputs 未填，或 runs/ 为空（远程跑则填 state.bundle.matrix）")
    # G4
    if exists(root, res.get("main_table", "results/main.csv")):
        rc, f, w, out = run([S("results_check.py")], root); f2 = w2 = 0
        if exists(root, res.get("ablation_table", "results/ablation.csv")):
            rc2, f2, w2, out2 = run([S("ablation_plan.py"), "resolve"], root)
        rec("G4", "FAIL" if (f or f2) else "PASS", f"results_check {f} FAIL / {w} WARN；ablation resolve {f2} FAIL")
    else: rec("G4", "PENDING", f"无 {res.get('main_table', 'results/main.csv')}")
    # G5
    fc = os.path.join(root, "figures.csv")
    if exists(root, "figures.csv") and len(io.open(fc, encoding="utf-8").read().strip().splitlines()) > 1 and "figures/fig1.png,90,results/main.csv,no" not in io.open(fc, encoding="utf-8").read():
        rc, f, w, out = run([S("gate_check.py"), "dpi", "--manuscript", manuscript if exists(root, manuscript) else "figures.csv"], root)
        rec("G5", "FAIL" if f else "PASS", f"dpi {f} FAIL / {w} WARN")
    else: rec("G5", "PENDING", "figures.csv 为空或仍是模板")
    # G6
    if exists(root, manuscript):
        subs = ["floats", "acronyms", "scope", "numbers", "limits"] + (["refs"] if net and exists(root, "paper/refs.bib") else [])
        tot_f = 0; parts = []
        for g in subs:
            rc, f, w, out = run([S("gate_check.py"), g, "--manuscript", manuscript, "--bib", "paper/refs.bib"] + (["--supplement", "paper/supplement.md"] if exists(root, "paper/supplement.md") else []), root)
            tot_f += f; parts.append(f"{g}:{f}F/{w}W")
        rec("G6", "FAIL" if tot_f else "PASS", "  ".join(parts) + ("" if net else "  (refs 需 --net)"))
        # G6b: must-write checklist from P1–P4 artefacts
        if exists(root, "paper/draft_plan.json"):
            rc, f, w, out = run([S("draft_plan.py"), "check"], root); m = re.search(r"(\d+)/(\d+) 项已写", out)
            rec("G6b", "FAIL" if f else "PASS", f"draft_plan {f} FAIL / {w} WARN" + (f"，{m.group(0)}" if m else ""))
        else: rec("G6b", "PENDING", "无 paper/draft_plan.json：写作前先 `draft_plan.py plan` 生成各节必写清单")
        # G6c: manuscript shape vs. target family (cs_conf | cs_journal | nature)
        rc, f, w, out = run([S("shape_check.py")], root); m = re.search(r"family = (\w+)", out)
        rec("G6c", "FAIL" if f else "PASS", f"shape {f} FAIL / {w} WARN" + (f"，family={m.group(1)}" if m else ""))
    else: rec("G6", "PENDING", f"无 {manuscript}")
    # G7
    if exists(root, "paper/review_log.md"):
        rc, f, w, out = run([S("review_check.py")], root)
        rec("G7", "FAIL" if f else "PASS", f"review_check {f} FAIL / {w} WARN")
    else: rec("G7", "PENDING", "无 paper/review_log.md")
    # G8
    if any(exists(root, "submission", x) for x in ("cover_letter.md", "title_page.md", "highlights.md", "blind.md")):
        rc, f, w, out = run([S("gate_check.py"), "submission", "--manuscript", manuscript], root); rec("G8", "FAIL" if f else "PASS", f"submission {f} FAIL / {w} WARN")
    else: rec("G8", "PENDING", "submission/ 无 cover_letter.md / title_page.md / highlights.md / blind.md")
    # survey branch gates (only when state.branch == survey or state.survey is filled)
    sv = st.get("survey") or {}
    sv_filled = any(sv.get(k) for k in ("scope_in", "scope_out", "axis", "thesis"))   # path/threshold keys are template defaults; only content keys make it a survey
    if (st.get("branch") == "survey") or sv_filled:
        if exists(root, "protocol.md") and "锁定日期：\n" not in io.open(os.path.join(root, "protocol.md"), encoding="utf-8").read()[:200]:
            rc, f, w, out = run([S("survey_check.py"), "protocol", "--codebook", sv.get("codebook", "coding/codebook.md")], root); rec("G-S2", "FAIL" if f else "PASS", f"protocol {f} FAIL / {w} WARN")
        else: rec("G-S2", "PENDING", "protocol.md 不存在或仍是模板")
        if exists(root, sv.get("screening_sheet", "coding/screening_sheet.csv")):
            rc, f, w, out = run([S("survey_check.py"), "coding"], root); rec("G-S3", "FAIL" if f else "PASS", f"coding {f} FAIL / {w} WARN")
        else: rec("G-S3", "PENDING", f"无 {sv.get('screening_sheet', 'coding/screening_sheet.csv')}")
        if exists(root, sv.get("claims", "paper/claims.csv")) and "C1,\"\"" not in io.open(os.path.join(root, sv.get("claims", "paper/claims.csv")), encoding="utf-8").read():
            rc, f, w, out = run([S("survey_check.py"), "claims"], root); rec("G-S5", "FAIL" if f else "PASS", f"claims {f} FAIL / {w} WARN")
        else: rec("G-S5", "PENDING", "paper/claims.csv 为空或仍是模板")
    nf = sum(1 for _, s, _ in board if s == "FAIL")
    first_bad = next((g for g, s, _ in board if s in ("FAIL", "PENDING")), None)
    print(f"\n== {nf} 道关口 FAIL；phase.current = {(st.get('phase') or {}).get('current', '?')}；下一步：{'修 ' + first_bad if first_bad else '全部通过，可投稿'} ==")
    print("逐条明细：对应脚本加 --project 单独跑；gate_report.md 保存最近一次 gate_check 输出")
    return nf

def status(root):
    st = load_state(os.path.join(root, "research-state.yaml"))
    if st is None: print("无 research-state.yaml"); return 1
    ph = st.get("phase") or {}; g = st.get("gates") or {}
    print(f"项目: {(st.get('project') or {}).get('title', '?')}\n目标刊: {(st.get('target') or {}).get('venue', '?')}\n阶段: {ph.get('current', '?')}  历史: {ph.get('history', [])}")
    for k in sorted(g): print(f"  {k}: {g[k].get('status', '?'):8s} {str(g[k].get('evidence', ''))[:90]}")
    nxt = next((k for k in sorted(g) if g[k].get("status") != "pass"), None)
    print(f"下一道未过关口: {nxt or '无'}")
    return 0

def init(root, venue, field, branch):
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
    io.open(sp, "w", encoding="utf-8").write(s)
    print(f"工作区已建: {root}\n下一步: 下载目标刊 Guide for Authors 到 submission/guide.txt，把硬规则抄进 research-state.yaml 的 target，然后 `t2p.py check`")
    return 0

def doctor():
    ok = True
    for mod, pipname in (("yaml", "pyyaml"), ("fitz", "pymupdf"), ("PIL", "pillow")):
        try: __import__(mod); print(f"[ok] {mod}")
        except ImportError: ok = False; print(f"[MISSING] {mod}  -> pip install {pipname}")
    import glob
    for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        if os.path.basename(f) == "t2p.py": continue
        r = subprocess.run([PY, f, "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"[{'ok' if r.returncode == 0 else 'BROKEN'}] {os.path.basename(f)} --help")
        ok &= r.returncode == 0
    for f in ("acronym-norms.csv", "venue-norms.csv", "gates.md", "lessons.md"):
        print(f"[{'ok' if exists(SKILL, 'references', f) else 'MISSING'}] references/{f}")
    return 0 if ok else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "check", "init"):
        p = sub.add_parser(name); p.add_argument("--project", default=".")
        if name == "check": p.add_argument("--net", action="store_true")
        if name == "init": p.add_argument("--venue", default=""); p.add_argument("--field", default=""); p.add_argument("--branch", choices=["research", "survey"], default="research")
    sub.add_parser("doctor")
    a = ap.parse_args()
    if a.cmd == "doctor": sys.exit(doctor())
    root = os.path.abspath(a.project)
    sys.exit({"status": lambda: status(root), "check": lambda: check(root, a.net), "init": lambda: init(root, a.venue, a.field, a.branch)}[a.cmd]())
