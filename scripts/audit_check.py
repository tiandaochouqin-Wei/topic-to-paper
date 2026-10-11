# -*- coding: utf-8 -*-
"""G3 — mechanical audit of leakage, effective configuration, silent fallback, run completeness.

  python audit_check.py [--state research-state.yaml] [--project .] [--smoke]

Configuration lives in research-state.yaml under `audits:` (see templates/research-state.yaml):

  audits:
    runs_dir: runs                      # each run = a folder with args_file + log_file
    args_file: args.json
    log_file: log.json                  # list of per-epoch dicts, or dict of lists
    epochs_key: epochs                  # args key that says how many log entries a finished run has
    main_table_runs: []                 # run names that feed the main table; empty = every run
    leak_flags: [use_B_train, B_labels] # any truthy value in a main-table run = target-domain information in training
    split_key: clip                     # group field that train/test must not share
    split_files: {train: "", test: ""}  # optional: csv/json/txt listing group ids per split -> overlap must be empty
    min_group_size: 5                   # groups below this must be dropped, not merged (degenerate-group overflow)
    critical_params:                    # args key -> evidence column in log (null = search a column containing the key name)
      beta: train_dom
      alpha: train_cons
    code_dirs: [code]                   # python files to scan for existence-checks that fall back instead of raising
    inputs: [frames, frames_256.npy]    # input names whose absence must raise; used by the static and the smoke check
    smoke_cmd: ""                       # e.g. "python code/train.py --data_A {data} --epochs 1 --exp _smoke"; {data} = temp copy with one input removed
    smoke_data: ""                      # small data root to copy for the smoke check
    hardware_key: hardware              # args/log key recording GPU model; missing -> WARN, mixed in one table -> FAIL

Every FAIL carries the run name or file:line. Exit 1 on any FAIL. Checks were calibrated on the project where all three
incidents happened (use_B_train leak, beta gated by is_ours, frames/ vs frames_256.npy): the gate must rediscover all three."""
import argparse, ast, csv, glob, io, json, os, re, shutil, subprocess, sys, tempfile, collections
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, gate, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {gate}: {msg}")

def load_state(p):
    txt = io.open(p, encoding="utf-8").read()
    try:
        import yaml
        return yaml.safe_load(txt) or {}
    except ImportError:
        say("FAIL", "audit", "需要 pyyaml 读取 research-state.yaml"); sys.exit(1)

def load_log(p):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    if isinstance(d, list):
        return d
    if isinstance(d, dict) and d and all(isinstance(v, list) for v in d.values()):
        n = max(len(v) for v in d.values())
        return [{k: (v[i] if i < len(v) else None) for k, v in d.items()} for i in range(n)]
    return None

def truthy(v):
    """args value counts as ON. Strings: '0', 'false', 'none', 'null', 'off', 'no' are OFF (RS_nowcast: --cond none was read as on)."""
    if isinstance(v, str): return v.strip().lower() not in ("", "0", "0.0", "false", "none", "null", "off", "no")
    return v not in (0, 0.0, False, None, [], {})

# ------------------------------------------------------------------ runs
def collect_runs(cfg, root):
    rd = os.path.join(root, cfg.get("runs_dir", "runs"))
    runs = {}
    for d in sorted(glob.glob(os.path.join(rd, "*"))):
        if not os.path.isdir(d) or os.path.basename(d).startswith(("_", ".")):
            continue
        ap = os.path.join(d, cfg.get("args_file", "args.json"))
        if not os.path.exists(ap):
            continue
        try:
            args = json.load(open(ap, encoding="utf-8"))
        except Exception:
            say("WARN", "runs", f"{os.path.basename(d)}: args.json 不可解析"); continue
        runs[os.path.basename(d)] = {"dir": d, "args": args, "log": load_log(os.path.join(d, cfg.get("log_file", "log.json")))}
    sel = cfg.get("main_table_runs") or []
    if sel:
        missing = [s for s in sel if s not in runs]
        if missing: say("FAIL", "runs", f"main_table_runs 里有 run 不存在: {missing}")
        runs = {k: v for k, v in runs.items() if k in sel}
    say("INFO", "runs", f"{len(runs)} 个 run 进入审计" + ("（main_table_runs 限定）" if sel else "（未指定 main_table_runs，审计全部）"))
    return runs

def check_leak_flags(cfg, runs):
    flags = cfg.get("leak_flags") or []
    if not flags:
        say("WARN", "leakage", "audits.leak_flags 为空：请列出所有\"目标域标签/数据进训练\"类开关"); return
    bad = []
    for name, r in runs.items():
        on = [f for f in flags if truthy(r["args"].get(f))]
        if on: bad.append((name, on))
    for name, on in bad:
        say("FAIL", "leakage", f"{name}: {on} 为真 —— 目标域信息进入训练，主表不得使用")
    if not bad:
        say("PASS", "leakage", f"{len(runs)} 个 run 的 {flags} 全部为 0")

def read_ids(p):
    if not p or os.path.isdir(p) or not os.path.exists(p): return None
    txt = io.open(p, encoding="utf-8").read()
    if p.endswith(".json"):
        d = json.loads(txt)
        if isinstance(d, dict):
            vals = []
            for v in d.values(): vals += v if isinstance(v, list) else [v]
            return set(map(str, vals))
        return set(map(str, d))
    if p.endswith(".csv"):
        rows = list(csv.reader(io.StringIO(txt)))
        return {r[0] for r in rows[1:] if r}
    return {l.strip() for l in txt.splitlines() if l.strip()}

def check_split(cfg, root):
    key = cfg.get("split_key")
    sf = cfg.get("split_files") or {}
    tr, te = read_ids(os.path.join(root, sf.get("train") or "")), read_ids(os.path.join(root, sf.get("test") or ""))
    if tr is not None and te is not None:
        ov = tr & te
        if ov: say("FAIL", "leakage", f"split_files: train/test 共享 {len(ov)} 个 {key}: {sorted(ov)[:8]}")
        else: say("PASS", "leakage", f"split_files: train {len(tr)} / test {len(te)} 个 {key}，无重叠")
    elif key:
        # 「配了路径但文件还不在」与「根本没配」是两件事：前者多半是数据还没准备好，后者是漏填
        miss = [f"{k}={sf[k]}" for k in ("train", "test") if (sf.get(k) or "").strip() and not os.path.exists(os.path.join(root, sf[k]))]
        if miss:
            say("WARN", "leakage", f"split_key={key}，split_files 已配但文件不存在: {miss} —— 先跑数据准备脚本导出 {key} 列表，再重跑本关口")
        else:
            say("WARN", "leakage", f"split_key={key} 但未提供 split_files，无法机械核对划分重叠；请导出 train/test 的 {key} 列表")
    # static: sample-level splits in code
    for f in py_files(cfg, root):
        src = io.open(f, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"train_test_split\s*\((.*?)\)", src, re.S):
            if "groups" not in m.group(1) and "stratify" not in m.group(1):
                say("WARN", "leakage", f"{rel(f, root)}:{src.count(chr(10), 0, m.start())+1} train_test_split 无 groups=，若样本来自同一受试者/片段即泄漏")
        for m in re.finditer(r"(random\.shuffle|np\.random\.(?:shuffle|permutation)|\.sample\(frac)", src):
            say("INFO", "leakage", f"{rel(f, root)}:{src.count(chr(10), 0, m.start())+1} 样本级打乱 {m.group(1)}：确认打乱的是 {key or '分组'} 不是样本")
    mg = cfg.get("min_group_size")
    if mg:
        say("INFO", "leakage", f"min_group_size={mg}：评估代码里样本数 <{mg} 的分组必须丢弃而不是并入邻组；grep 'degenerate|merge|fallback' 见下")
        for f in py_files(cfg, root):
            src = io.open(f, encoding="utf-8", errors="replace").read()
            for m in re.finditer(r"\b(degenerate|merge[sd]?\s+into|fall\s*back\s+to|collapse)\b", src, re.I):
                say("INFO", "leakage", f"{rel(f, root)}:{src.count(chr(10), 0, m.start())+1} '{m.group(1)}'")

def check_stats_leak(cfg, root):
    """normalisation statistics fitted on anything but the labelled source/train set."""
    pat = re.compile(r"(compute_stats|StandardScaler|MinMaxScaler|\.fit\(|normali[sz]e_stats|mean\(\)|std\(\))")
    tgt = re.compile(r"\b(test|target|B_train|trB|val|eval|all_sets|tr_sets|concat)\b", re.I)
    for f in py_files(cfg, root):
        src = io.open(f, encoding="utf-8", errors="replace").read()
        for i, line in enumerate(src.splitlines(), 1):
            if pat.search(line) and tgt.search(line):
                say("WARN", "leakage", f"{rel(f, root)}:{i} 统计量/归一化拟合的输入含 {tgt.search(line).group(1)}：确认标签相关统计量只来自源域训练集 | {line.strip()[:90]}")

# ------------------------------------------------------------------ effective config
def check_effective_config(cfg, runs, root):
    crit = cfg.get("critical_params") or {}
    if not crit:
        say("WARN", "effective-config", "audits.critical_params 为空：列出每个关键超参及其在日志中的证据列"); return
    for name, r in runs.items():
        log = r["log"]
        if not log:
            say("FAIL", "effective-config", f"{name}: 无 log，无法核对任何参数是否生效"); continue
        cols = set().union(*[set(e.keys()) for e in log])
        for p, col in crit.items():
            if p not in r["args"]:
                say("WARN", "effective-config", f"{name}: args 无 {p}"); continue
            v = r["args"][p]
            cands = [col] if col else [c for c in cols if p.lower() in c.lower()]
            present = [c for c in cands if c in cols]
            nonzero = any(any(truthy(e.get(c)) for e in log) for c in present)
            if truthy(v) and not present:
                say("FAIL", "effective-config", f"{name}: args.{p}={v} 但日志无证据列 {cands or '(按名搜索)'} —— 参数未生效（如被 is_ours 之类分支挡住）")
            elif truthy(v) and present and not nonzero:
                say("FAIL", "effective-config", f"{name}: args.{p}={v}，证据列 {present} 存在但全程为 0")
            elif not truthy(v) and nonzero:
                say("FAIL", "effective-config", f"{name}: args.{p}={v} 却在日志里看到 {present} 非零 —— 配置与行为相反")
    # static: gating conditions on critical params — "x if (flag and a.beta > 0) else 0" / "if flag and a.beta"
    for f in py_files(cfg, root):
        src = io.open(f, encoding="utf-8", errors="replace").read()
        for p in crit:
            for m in re.finditer(r"\b(\w+)\s+and\s+[^\n]{0,40}\b(?:a|args|cfg|opt)\.%s\b" % re.escape(p), src):
                g = m.group(1)
                if g in ("and", "or", "not"): continue
                say("INFO", "effective-config", f"{rel(f, root)}:{src.count(chr(10), 0, m.start())+1} {p} 被 '{g}' 门控：{g} 为假时 args.{p} 写什么都不生效")
    say("INFO", "effective-config", f"核对了 {len(runs)} 个 run × {list(crit)}")

# ------------------------------------------------------------------ silent fallback (static)
def py_files(cfg, root):
    out = []
    for d in cfg.get("code_dirs") or ["."]:
        out += glob.glob(os.path.join(root, d, "**", "*.py"), recursive=True)
    return [f for f in out if "__pycache__" not in f and not os.path.basename(f).startswith("_")]

def rel(f, root):
    return os.path.relpath(f, root).replace("\\", "/")

EXIST = re.compile(r"\.(exists|is_file|is_dir)\(\)|os\.path\.(exists|isfile|isdir)\(")

def _raises(node):
    for n in ast.walk(node):
        if isinstance(n, (ast.Raise, ast.Assert)): return True
        if isinstance(n, ast.Call) and getattr(getattr(n.func, "attr", None), "lower", lambda: "")() == "exit": return True
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("exit", "quit"): return True
    return False

RE_FUNCS = {"search", "match", "fullmatch", "compile", "sub", "subn", "findall", "finditer", "split"}

def _regex_literals(node):
    """字符串字面量里其实是**正则**的（re.search(r"(a|b)", …)）：不是路径，不能算进"检查过的文件"。"""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(getattr(n, "func", None), ast.Attribute) and n.func.attr in RE_FUNCS:
            if getattr(n.func.value, "id", "") in ("re", "regex") or n.func.attr in ("search", "findall", "finditer"):
                for arg in n.args[:1]:
                    out |= {x.value for x in ast.walk(arg) if isinstance(x, ast.Constant) and isinstance(x.value, str)}
    return out

def _str_literals(node, drop_regex=True):
    lits = {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and 1 < len(n.value) < 60}
    return (lits - _regex_literals(node)) if drop_regex else lits

def _is_write(seg):
    """open(..., "w"/"a"/"x")、to_csv、savez 之类是**写**：生产输入文件的脚本不该因为"写了却没先检查存在"被判成判一个读一个。"""
    if re.search(r"\b(savez|savez_compressed|to_csv|imwrite|DictWriter|writer)\s*\(", seg): return True
    # open(...) 的 mode 实参可能被 os.path.join(...) 隔开，所以不能用 [^)]*：直接在整段里找写模式字面量
    return bool(re.search(r"\bopen\s*\(", seg) and re.search(r"""["'][wax][btx+]*["']""", seg))

OPTIONAL = re.compile(r"(log|ckpt|checkpoint|best\.pt|last\.pt|\.pt\b|\.pth\b|resume|cache|\bout\b|output|eval\.json|args\.json|meta\.json|manifest\.json|hardware\.json|results?\.json|\.png|\.pdf|\.csv)", re.I)

def check_silent_fallback(cfg, root):
    inputs = set(cfg.get("inputs") or [])
    n_warn = 0
    seen = set()
    for f in py_files(cfg, root):
        src = io.open(f, encoding="utf-8", errors="replace").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        # (a) existence checks whose outcome does not raise
        for node in ast.walk(tree):
            tests = []
            if isinstance(node, ast.If): tests = [(node.test, node.body + node.orelse, node)]
            elif isinstance(node, ast.IfExp): tests = [(node.test, [node.body, node.orelse], node)]
            elif isinstance(node, ast.ListComp):
                tests = [(node.elt.test, [node.elt.body, node.elt.orelse], node)] if isinstance(node.elt, ast.IfExp) else []
            for test, branches, parent in tests:
                seg = ast.get_source_segment(src, test) or ""
                if not EXIST.search(seg): continue
                lits = _str_literals(test)
                hit_inputs = {l for l in lits for i in inputs if i in l}
                if any(_raises(b) if isinstance(b, ast.AST) else False for b in branches):
                    continue
                key = (f, node.lineno, seg)
                if key in seen: continue
                seen.add(key)
                if hit_inputs:
                    tag = "FAIL"
                elif OPTIONAL.search(seg) and not any(i in seg for i in inputs):
                    tag = "INFO"      # checkpoints / logs / caches / outputs are allowed to be absent
                else:
                    tag = "WARN"
                if tag != "INFO": n_warn += 1
                say(tag, "silent-fallback", f"{rel(f, root)}:{node.lineno} 存在性判断 `{seg[:70]}` 的两个分支都不 raise —— 输入缺失时静默降级" + (f"（涉及声明输入 {sorted(hit_inputs)}）" if hit_inputs else ""))
        # (b) checked literal != read literal: the frames/ vs frames_256.npy incident
        checked, read = set(), set()
        for node in ast.walk(tree):
            seg = ast.get_source_segment(src, node) if isinstance(node, (ast.Call, ast.Compare, ast.BoolOp)) else None
            if not seg: continue
            if EXIST.search(seg): checked |= _str_literals(node)
            if re.search(r"\b(open|np\.load|load|Image\.open|read_csv|imread|loadtxt|h5py\.File|torch\.load)\s*\(", seg) and not _is_write(seg):
                read |= _str_literals(node)          # 只算读；写出同名文件的生产脚本不该被判成"判一个读一个"
        for i in inputs:
            c = {l for l in checked if i in l}; r_ = {l for l in read if i in l}
            others_checked = {l for l in checked if any(j in l for j in inputs) and i not in l}
            if r_ and not c and others_checked:
                say("FAIL", "silent-fallback", f"{rel(f, root)}: 读取 '{i}'（{sorted(r_)[:2]}）但存在性判断只查了 {sorted(others_checked)[:2]} —— 判一个文件、读另一个文件")
    if n_warn == 0:
        say("PASS", "silent-fallback", "静态扫描：所有输入存在性判断的失败分支都 raise/exit")

# ------------------------------------------------------------------ silent fallback (dynamic smoke)
def check_smoke(cfg, root):
    cmd, data = cfg.get("smoke_cmd"), cfg.get("smoke_data")
    inputs = cfg.get("inputs") or []
    if not (cmd and data and inputs):
        say("WARN", "silent-fallback", "未配置 smoke_cmd/smoke_data/inputs，跳过动态烟测（删一个输入后训练命令必须非零退出）"); return
    src = os.path.join(root, data)
    if not os.path.isdir(src):
        say("FAIL", "silent-fallback", f"smoke_data {data} 不存在"); return
    for inp in inputs:
        tmp = tempfile.mkdtemp(prefix="g3smoke_")
        dst = os.path.join(tmp, "data"); shutil.copytree(src, dst)
        removed = 0
        for dp, dns, fns in os.walk(dst):
            for x in list(dns) + list(fns):
                if x == inp or x.startswith(inp):
                    p = os.path.join(dp, x); shutil.rmtree(p) if os.path.isdir(p) else os.remove(p); removed += 1
        if removed == 0:
            say("WARN", "silent-fallback", f"smoke: 在 {data} 里没找到输入 '{inp}'，无法删除"); shutil.rmtree(tmp, ignore_errors=True); continue
        try:
            r = subprocess.run(cmd.format(data=dst), shell=True, cwd=root, capture_output=True, text=True, timeout=900)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -1
        shutil.rmtree(tmp, ignore_errors=True)
        if rc == 0:
            say("FAIL", "silent-fallback", f"smoke: 删除输入 '{inp}'（{removed} 处）后训练命令仍以 0 退出 —— 缺失被静默吞掉")
        else:
            say("PASS", "silent-fallback", f"smoke: 删除 '{inp}' 后命令退出码 {rc}（非零，正确）")

# ------------------------------------------------------------------ completeness & hardware
def check_completeness(cfg, runs):
    ek = cfg.get("epochs_key", "epochs")
    for name, r in runs.items():
        exp = r["args"].get(ek)
        n = len(r["log"]) if r["log"] else 0
        if exp is None:
            say("WARN", "completeness", f"{name}: args 无 {ek}，无法判断是否训完"); continue
        if n < int(exp):
            say("FAIL", "completeness", f"{name}: log {n}/{exp} 条 —— 未训完（ckpt 存在与否不算证据），不得进主表")
    hk = cfg.get("hardware_key", "hardware")
    hw = collections.Counter()
    for name, r in runs.items():
        v = r["args"].get(hk) or (r["log"][0].get(hk) if r["log"] and isinstance(r["log"][0], dict) else None)
        hp = os.path.join(r.get("dir", ""), "hardware.json")                       # bundle.py run_one.sh writes this
        if not v and r.get("dir") and os.path.exists(hp):
            try: v = json.load(open(hp)).get("hardware")
            except Exception: pass
        hw[str(v) if v else "(unrecorded)"] += 1
    if "(unrecorded)" in hw:
        say("WARN", "completeness", f"{hw['(unrecorded)']} 个 run 未记录硬件（args/log 的 '{hk}'）；不同 GPU 的结果不可同表比较，请在 train.py 里写入 torch.cuda.get_device_name()")
    kinds = [k for k in hw if k != "(unrecorded)"]
    if len(kinds) > 1:
        say("FAIL", "completeness", f"主表混有多种硬件: {dict(hw)} —— 另立复现表")
    done = sum(1 for r in runs.values() if r["log"] and r["args"].get(ek) and len(r["log"]) >= int(r["args"][ek]))
    say("INFO", "completeness", f"{done}/{len(runs)} 个 run 训完")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="research-state.yaml")
    ap.add_argument("--project", default=".")
    ap.add_argument("--smoke", action="store_true", help="也跑动态烟测（删输入后训练命令必须非零退出）")
    a = ap.parse_args()
    root = os.path.abspath(a.project)
    st = load_state(os.path.join(root, a.state) if not os.path.isabs(a.state) else a.state)
    cfg = st.get("audits") or {}
    if not cfg:
        say("FAIL", "audit", "research-state.yaml 没有 audits: 段"); sys.exit(1)
    runs = collect_runs(cfg, root)
    print("\n== leakage =="); check_leak_flags(cfg, runs); check_split(cfg, root); check_stats_leak(cfg, root)
    print("\n== effective-config =="); check_effective_config(cfg, runs, root)
    print("\n== silent-fallback =="); check_silent_fallback(cfg, root)
    if a.smoke: check_smoke(cfg, root)
    print("\n== completeness =="); check_completeness(cfg, runs)
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL"))
    sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
