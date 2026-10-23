# -*- coding: utf-8 -*-
"""G3b — instrument calibration: every pretrained model / external harness / training loop must reproduce a known answer through the SAME input path the experiments use.

  python instrument_check.py [--state research-state.yaml] [--project .]

Reads research-state.yaml: `instruments:` (list), `instruments_waiver:` (list of {match, reason}), `audits.code_dirs`, `audits.runs_dir`.

  instruments:
    - name: suprem                     # free id (run args.json may log `contracts: {suprem: {...}}` under it)
      kind: pretrained                 # pretrained | harness | train_loop
      match: "SuPreM|suprem"           # regex; covers every loader line whose file path OR line text matches
      contract:                        # the input convention the OFFICIAL code uses; source = the official repo line, not memory
        axcodes: RAS
        spacing: [1.5, 1.5, 1.5]
        intensity: "HU clip [-175, 250] -> [0, 1]"
        channels: 1
        source: "https://github.com/.../transforms.py#L40"
      check:                           # known-answer test through the same input path as the experiments
        cmd: "python code/calib_suprem.py --out results/instruments/suprem.json"
        output: results/instruments/suprem.json   # may carry `applied_contract: {...}` = what the script really fed the model
        key: dice.liver                # dotted path into the json
        expected: 0.95                 # published / official number
        tol: 0.05                      # or min: / max: instead of expected+tol
        source: "SuPreM paper Table 3"
      broken:                          # same check with a deliberately broken input (axes reversed ...); MUST land outside the band
        output: results/instruments/suprem_broken.json
        key: dice.liver                # default: check.key
        how: "axes reversed (LPS)"
      dump: figures/instruments/suprem_first_batch.png   # first tensor the model sees, axis labels on; required when contract has axcodes or channels
      inspected: yes
    - name: own_loop
      kind: train_loop                 # no known number: needs `reference: {output, key, expected, tol, source}` = a reference implementation on the same split
  instruments_waiver:                  # loader lines that are not an instrument, e.g. the project's own checkpoint
    - {match: "resume|runs/", reason: "own checkpoint"}

Checks: (1) static loader scan over audits.code_dirs plus every other project .py outside artefact dirs (from_pretrained / load_state_dict / torch.hub.load / timm / open_clip / YOLO / hf_hub_download ...):
every hit must be covered by an instrument `match` or a waiver (waiver = WARN with its reason); (2) per instrument: output exists, not older than the
code it covers, reading inside the known band, broken-input reading OUTSIDE the band (a test that cannot fail is not a test), applied_contract (json) and the
runs' logged contracts equal the registered contract, first-batch dump exists and is marked inspected. Every FAIL names the instrument or file:line. Exit 1 on any FAIL.
Why: cvpr2027_medical fed four pretrained 3D encoders an SPL array where the official layout is RAS; 7 days, 10 review rounds and every other gate missed it,
and the first 'orientation test' scored 0.562 (wrong) vs 0.581 (right) — it could not fail."""
import argparse, glob, io, json, os, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, gate, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {gate}: {msg}")

def load_state(p):
    try:
        import yaml
        return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}
    except ImportError:
        say("FAIL", "instrument", "需要 pyyaml 读取 research-state.yaml"); sys.exit(1)

LOADER = re.compile(r"from_pretrained\(|load_state_dict\(|torch\.hub\.load\(|timm\.create_model\(|open_clip\.create_model|create_model_and_transforms\(|AutoModel\w*\.|\bYOLO\(|torch\.load\(.*(ckpt|checkpoint|\.pt|\.pth|weights)|safetensors|hf_hub_download\(|snapshot_download\(")
# optimizer / scaler / scheduler / EMA state restores are resume bookkeeping, not an instrument
NOT_INSTRUMENT = re.compile(r"\b(opt\w*|scaler|sched\w*|lr_sched\w*|ema(\.ema)?)\.load_state_dict\(")
SKIP_DIRS = {"tests", "venv", ".venv", "site-packages", "__pycache__", ".git", "node_modules",
             "runs", "results", "data", "literature", "paper", "submission", "figures", "bundle"}   # project dirs that hold artefacts, not experiment code
KINDS = ("pretrained", "harness", "train_loop")

def rel(f, root): return os.path.relpath(f, root).replace("\\", "/")

def py_files(codes, root):
    """code_dirs plus every other .py in the project: experiment code outside code_dirs (ma_p3/, killtest_*/) is still experiment code."""
    out = []
    for d in list(codes) + ["."]:
        out += glob.glob(os.path.join(root, d, "**", "*.py"), recursive=True)
    keep = []
    for f in sorted(set(os.path.normpath(f) for f in out)):
        parts = set(rel(f, root).split("/")[:-1])
        if parts & SKIP_DIRS or any(p.startswith("venv") for p in parts) or os.path.basename(f).startswith("_"): continue
        keep.append(f)
    return keep

def scan_loaders(files, root):
    hits = []   # (file, lineno, text)
    for f in files:
        for i, line in enumerate(io.open(f, encoding="utf-8", errors="replace").read().splitlines(), 1):
            if line.lstrip().startswith("#"): continue
            if LOADER.search(NOT_INSTRUMENT.sub("", line)): hits.append((f, i, line.strip()))
    return hits

def rx(pat):
    try: return re.compile(str(pat))
    except re.error: return None

def covers(pat, f, text, root):
    r = rx(pat)
    return bool(r and (r.search(rel(f, root)) or r.search(text)))

def get_path(o, path):
    for part in str(path).split("."):
        o = o[int(part)] if isinstance(o, list) else o[part]
    return o

def read_value(root, spec, key=None):
    """-> (value, error). spec = {output, key}; key overrides spec['key']."""
    p = os.path.join(root, spec.get("output") or "")
    if not spec.get("output") or not os.path.exists(p): return None, "missing"
    try:
        d = json.load(open(p, encoding="utf-8"))
        return float(get_path(d, key or spec.get("key"))), None
    except Exception as e:
        return None, f"unreadable: {e}"

def band(spec):
    """(lo, hi) from expected±tol or min/max; None when the known answer is not stated."""
    try:
        if spec.get("expected") is not None and spec.get("tol") is not None:
            e, t = float(spec["expected"]), abs(float(spec["tol"])); return (e - t, e + t)
        lo = float(spec["min"]) if spec.get("min") is not None else float("-inf")
        hi = float(spec["max"]) if spec.get("max") is not None else float("inf")
    except (TypeError, ValueError): return None
    return None if (lo, hi) == (float("-inf"), float("inf")) else (lo, hi)

def describe(spec):
    if spec.get("expected") is not None and spec.get("tol") is not None: return f"{spec['expected']}±{spec['tol']}"
    return f"[{spec.get('min', '-inf')}, {spec.get('max', 'inf')}]"

def same(a, b):
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if not (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple))) or len(a) != len(b): return False
        return all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool): return a == b
    try: return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError): return str(a).strip().lower() == str(b).strip().lower()

def diff_contract(declared, applied):
    return [k for k, v in declared.items() if k != "source" and (k not in applied or not same(v, applied[k]))]

def truthy_yes(v): return v is True or str(v).strip().lower() in ("yes", "true", "y", "1")

def check_value(name, label, spec, root, kind):
    """3c: reading inside the band. Returns the value (or None)."""
    b = band(spec)
    if b is None:
        say("FAIL", "instrument", f"{name}: {label} 无已知答案（缺 expected+tol 或 min/max）—— 没有已知答案就不是校准"); return None
    v, err = read_value(root, spec)
    if err:
        say("FAIL", "instrument", f"{name}: {label} 读数不可用（{spec.get('output')}#{spec.get('key')}：{err}）"); return None
    if b[0] <= v <= b[1]:
        say("PASS", "instrument", f"{name}: {label} 读数 {v:g} 在已知答案 {describe(spec)} 内（{spec.get('source', '无 source')}）")
    else:
        say("FAIL", "instrument", f"{name}: 仪器读数 {v:g} vs 已知 {describe(spec)}（{spec.get('source', '无 source')}）—— 输入约定/预处理/权重有问题，修好前任何用到它的结果都不能进表")
    return v

def check_broken(name, spec, ref_spec, root, kind):
    br = spec.get("broken")
    need = kind != "train_loop"
    if not br:
        say("FAIL" if need else "WARN", "instrument", f"{name}: 没有破坏对照：一个不会失败的校验等于没校验（broken: 同一校验、故意破坏输入，读数必须落到容许带外）"); return
    vb, err = read_value(root, br, br.get("key") or ref_spec.get("key"))
    if err:
        say("FAIL", "instrument", f"{name}: 破坏对照 {br.get('output')} {err} —— 破坏版没跑"); return
    b = band(ref_spec); v, _ = read_value(root, ref_spec)
    if b is None or v is None: return
    if b[0] <= vb <= b[1]:
        say("FAIL", "instrument", f"{name}: 校验区分不了正确与破坏的输入（{br.get('how', '?')}: {vb:g} vs {v:g}）—— 这个测试无效")
    else:
        say("PASS", "instrument", f"{name}: 破坏对照（{br.get('how', '?')}）读数 {vb:g} 落在容许带 {describe(ref_spec)} 外，校验能失败")

def check_contract(name, ins, root, cfg_runs, run_contracts):
    c = ins.get("contract") or {}
    if not c: return
    if not c.get("source"): say("WARN", "instrument", f"{name}: contract 没有 source（官方仓库的那一行，不是记忆）")
    out = (ins.get("check") or ins.get("reference") or {}).get("output")
    p = os.path.join(root, out) if out else None
    if p and os.path.exists(p):
        try: ap = json.load(open(p, encoding="utf-8")).get("applied_contract")
        except Exception: ap = None
        if isinstance(ap, dict):
            bad = diff_contract(c, ap)
            if bad: say("FAIL", "instrument", f"{name}: 校准脚本实际用的输入约定与登记不符 {[(k, c[k], ap.get(k)) for k in bad]}（{out}#applied_contract）")
            else: say("PASS", "instrument", f"{name}: applied_contract 与登记的 contract 一致")
        else: say("WARN", "instrument", f"{name}: 校准脚本没写 applied_contract，无法核对输入约定（{out}）")
    for run, cs in run_contracts.items():
        if isinstance(cs.get(name), dict):
            bad = diff_contract(c, cs[name])
            if bad: say("FAIL", "instrument", f"run {run} 实际用的约定与登记不符 {name}: {[(k, c[k], cs[name].get(k)) for k in bad]}")
            else: say("PASS", "instrument", f"{name}: run {run} 记录的 contracts 与登记一致")
    if c.get("axcodes") is not None or c.get("channels") is not None:
        d = ins.get("dump")
        if not d or not os.path.exists(os.path.join(root, d)):
            say("FAIL", "instrument", f"{name}: 缺首批输入图 dump（{d or '未登记'}）—— contract 含 axcodes/channels 时必须把模型看到的第一个张量画出来（标轴向）")
        elif not truthy_yes(ins.get("inspected")):
            say("FAIL", "instrument", f"{name}: 首批输入图未目测（{d}）—— 看过图后写 inspected: yes")
        else: say("PASS", "instrument", f"{name}: 首批输入图 {d} 已目测")

def collect_run_contracts(acfg, root):
    out, any_logged = {}, False
    rd = os.path.join(root, acfg.get("runs_dir", "runs"))
    for d in sorted(glob.glob(os.path.join(rd, "*"))):
        ap = os.path.join(d, acfg.get("args_file", "args.json"))
        if not os.path.isdir(d) or os.path.basename(d).startswith(("_", ".")) or not os.path.exists(ap): continue
        try: a = json.load(open(ap, encoding="utf-8"))
        except Exception: continue
        if isinstance(a, dict) and isinstance(a.get("contracts"), dict): out[os.path.basename(d)] = a["contracts"]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="research-state.yaml")
    ap.add_argument("--project", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.project)
    st = load_state(os.path.join(root, a.state) if not os.path.isabs(a.state) else a.state)
    acfg = st.get("audits") or {}
    instruments = [i for i in (st.get("instruments") or []) if isinstance(i, dict)]
    waivers = [w for w in (st.get("instruments_waiver") or []) if isinstance(w, dict) and w.get("match")]
    files = py_files(acfg.get("code_dirs") or ["."], root)
    hits = scan_loaders(files, root)
    print("== loader scan ==")
    names = [i.get("name") or f"#{n}" for n, i in enumerate(instruments, 1)]
    for n, i in zip(names, instruments):
        if rx(i.get("match")) is None or not i.get("match"):
            say("FAIL", "instrument", f"{n}: match 缺失或不是合法正则（{i.get('match')!r}）")
        if i.get("kind") not in KINDS: say("FAIL", "instrument", f"{n}: kind 必须是 {'|'.join(KINDS)}（现为 {i.get('kind')!r}）")
    uncovered, waived = [], {}
    for f, ln, text in hits:
        if any(i.get("match") and covers(i["match"], f, text, root) for i in instruments): continue
        w = next((w for w in waivers if covers(w["match"], f, text, root)), None)
        if w: waived.setdefault(w.get("reason") or w["match"], []).append(f"{rel(f, root)}:{ln}")
        else: uncovered.append((f, ln, text))
    by_file = {}   # one FAIL per file: a dozen load_state_dict lines of one encoder are one missing calibration, not twelve
    for f, ln, text in uncovered: by_file.setdefault(rel(f, root), []).append((ln, text))
    for rf, locs in by_file.items():
        say("FAIL", "instrument", f"未校准的仪器 {rf}:{','.join(str(l) for l, _ in locs[:8])}{' …' if len(locs) > 8 else ''} — 加 instruments 条目（已知答案 + 破坏对照）| {locs[0][1][:80]}")
    for reason, locs in waived.items():
        say("WARN", "instrument", f"{len(locs)} 处加载按 instruments_waiver 豁免（{reason}）: {locs[:3]} —— 确认它真的不是外部预训练组件")
    if not instruments and not hits:
        say("PASS", "instrument", "无预训练组件/外部框架（静态扫描项目代码未发现加载点）")
    elif not uncovered:
        say("PASS", "instrument", f"{len(hits)} 个加载点全部被 instruments 或 waiver 覆盖")
    run_contracts = collect_run_contracts(acfg, root) if instruments else {}
    if any((i.get("contract") or {}) for i in instruments) and not run_contracts:
        say("WARN", "instrument", "没有任何 run 的 args.json 记录 contracts: {仪器名: {...}} —— 无法核对实验实际用的输入约定与登记是否一致")
    for n, i in zip(names, instruments):
        print(f"\n== {n} ({i.get('kind')}) ==")
        kind = i.get("kind")
        pat = i.get("match")
        covered_files = [f for f in files if pat and rx(pat) and (rx(pat).search(rel(f, root)) or any(h[0] == f and rx(pat).search(h[2]) for h in hits))]
        if kind == "train_loop":
            spec, label = i.get("reference") or {}, "参考实现"
            if not spec: say("FAIL", "instrument", f"{n}: train_loop 需要 reference:（参考实现在同一划分上的结果，如官方 trainer）—— 自己写的训练循环没有已知数字，只能和参考实现对账")
        else:
            spec, label = i.get("check") or {}, "校准"
        out = spec.get("output") if spec else None
        if spec and not (out and os.path.exists(os.path.join(root, out))):
            say("FAIL", "instrument", f"{n}: 未跑{label}（cmd: {spec.get('cmd', '未登记')}；缺 {out or 'output'}）")
        elif spec:
            op = os.path.join(root, out)
            newer = [f for f in covered_files if os.path.getmtime(f) > os.path.getmtime(op) + 1]
            if newer: say("FAIL", "instrument", f"{n}: 代码改过、校准未重跑 —— {[rel(f, root) for f in newer][:3]} 比 {out} 新")
            check_value(n, label, spec, root, kind)
            check_broken(n, i, spec, root, kind)
        check_contract(n, i, root, acfg, run_contracts)
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL"))
    sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
