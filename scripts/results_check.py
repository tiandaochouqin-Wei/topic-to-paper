# -*- coding: utf-8 -*-
"""G4 — mechanical check that the main table is traceable, on-convention, seeded and complete.

  python results_check.py [--state research-state.yaml] [--prereg prereg.md] [--project .]

state.results:
  main_table: results/main.csv        # columns: run_id, method, seed, <metric columns...>; optional: convention
  ablation_table: results/ablation.csv # columns: ablation (prereg §6 item), run_id, seed, <metrics>
  eval_file: eval.json                 # per-run metrics file under runs/<run_id>/
  runs_dir: runs
  metric_map:                          # main.csv column -> dotted path inside eval_file (list index allowed)
    rmse_E1: E1_in_domain.rmse_contact
  primary_metric: rmse_E1              # must be a main.csv column AND named in prereg §2
  primary_direction: lower             # lower|higher; unset = guessed from the name (WARN when the guess fails)
  metric_direction: {}                 # optional per-column override, e.g. {delta_rel_Ta: lower}
  min_seeds: 3
  seed_waiver: ""                      # non-empty = reason accepted instead of ≥ min_seeds
  group_key: method                    # rows sharing this value are one method; seeds counted within
  freshness_ref: log.json              # eval_file must be newer than this (eval before training finished = stale)
  predictions:                         # optional pre-stated sign checks: expected sign of (b - a) on metric
    - {a: ours, b: no_dom, metric: rmse_E5, sign: "+"}

Checks: (1) every main/ablation row's run dir + eval_file exist, every mapped metric matches the file after rounding to the
CSV's precision; eval newer than freshness_ref; no `_tainted`; (2) primary metric column present and named in prereg;
convention string from prereg §4 appears in the table header/note; (3) seeds ≥ min_seeds per method, else waiver; the same seed
set across methods; (4) ablation rows ⊇ prereg §6 items, baselines ⊇ prereg §5 items (fuzzy token match); (5) sign of each
pre-stated prediction; (6) `reproductions` empty while the main table has a baseline -> WARN; (7) findings.md: a block (`## F#`) that closes an
anomaly (`cause: real|impl|data|convention|leak`, `<step>: excluded|排除`) needs an `evidence:` line naming >=1 existing file (command output, not prose),
and `cause: real` needs a `control:` line. Exit 1 on any FAIL."""
import argparse, csv, io, json, os, re, sys, collections, statistics
from decimal import Decimal, InvalidOperation
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import metric_direction as mdir

FAILS = 0
def say(st, g, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {g}: {msg}")

def load_yaml(p):
    import yaml
    return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}

def get_path(o, path):
    for part in path.split("."):
        if isinstance(o, list): o = o[int(part)]
        else: o = o[part]
    return o

def norm(s):
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", str(s).lower())
    return {w for w in s.split() if w not in {"no", "without", "w", "o", "the", "a", "of", "and", "remove", "removed", "ablation"}}
def flat(s): return re.sub(r"[^a-z0-9一-鿿]", "", str(s).lower())

def fuzzy_in(item, pool):
    a = norm(item)
    if not a: return False
    return any(len(a & norm(p)) >= max(1, len(a) - 1) or a <= norm(p) or norm(p) <= a for p in pool)

def section(md, name):
    """body of the heading whose title starts with `name`, up to the next heading of EQUAL OR SHALLOWER depth (sub-headings stay inside)."""
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return ""
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

def table_first_col(txt):
    rows = [l for l in txt.splitlines() if l.strip().startswith("|")]
    out = []
    for l in rows[2:]:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if cells and cells[0] and not set(cells[0]) <= set("-: "): out.append(cells[0])
    return out

VERDICT = re.compile(r"(?mi)^[ \t]*(?:-[ \t]*)?(?:cause[ \t]*:[ \t]*(?:real|impl|data|convention|leak)\b|(?:convention|data|leak|impl)[ \t]*:[ \t]*(?:excluded|排除))")

def finding_blocks(txt):
    """[(id, block text)] for `## F#` / `### F#` headings; fenced ``` examples (the template's format block) are not findings."""
    txt = re.sub(r"(?s)```.*?```", "", txt)
    ms = list(re.finditer(r"(?m)^#{2,3}[ \t]*(F\d+)\b.*$", txt))
    out = []
    for i, m in enumerate(ms):
        nxt = re.search(r"(?m)^#{1,3}[ \t]", txt[m.end():])
        end = m.end() + nxt.start() if nxt else len(txt)
        out.append((m.group(1), txt[m.end():end]))
    return out

def evidence_paths(block, root):
    """existing project paths named on `evidence:` lines (space/comma separated; `path:line` and `path#anchor` accepted)"""
    ok = []
    for line in re.findall(r"(?mi)^[ \t]*(?:-[ \t]*)?evidence[ \t]*:(.*)$", block):
        for tok in re.split(r"[\s,;，；]+", line):
            tok = re.sub(r"(:\d+)?(#.*)?$", "", tok.strip("`'\"()[]<>"))
            if tok and os.path.exists(os.path.join(root, tok)): ok.append(tok)
    return ok

def read_csv(p):
    if not os.path.exists(p): return None, []
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    return rows, (list(rows[0].keys()) if rows else [])

def cell_matches(s, v):
    """True when CSV cell s is v printed to s's own precision. Precision comes from the Decimal exponent,
    so scientific notation ("9.07e-05", "1.2E+3") counts its digits correctly; ties at half a last digit pass."""
    try: d = Decimal(s)
    except InvalidOperation: return False
    if not d.is_finite(): return d.is_nan() and v != v or (d.is_infinite() and float(d) == v)
    if float(d) == v: return True                                  # shortest repr / full-precision dump
    return abs(Decimal(v) - d) <= Decimal(5).scaleb(d.as_tuple().exponent - 1)   # half a unit in the last printed digit, exact arithmetic

def check_rows(cfg, root, rows, label):
    rd, ef, fr = cfg.get("runs_dir", "runs"), cfg.get("eval_file", "eval.json"), cfg.get("freshness_ref", "log.json")
    mm = cfg.get("metric_map") or {}
    bad = 0
    for i, r in enumerate(rows, 1):
        rid = r.get("run_id", "").strip()
        if not rid:
            bad += 1; say("FAIL", "trace", f"{label} 第 {i} 行无 run_id"); continue
        d = os.path.join(root, rd, rid); p = os.path.join(d, ef)
        if not os.path.exists(p):
            bad += 1; say("FAIL", "trace", f"{label} {rid}: {rd}/{rid}/{ef} 不存在"); continue
        try: ev = json.load(open(p, encoding="utf-8"))
        except Exception as ex:
            bad += 1; say("FAIL", "trace", f"{label} {rid}: {ef} 不可解析 {ex}"); continue
        if isinstance(ev, dict) and ev.get("_tainted"):
            bad += 1; say("FAIL", "trace", f"{label} {rid}: {ef} 标记 _tainted —— 评估于修复前，不得进表")
        ref = os.path.join(d, fr)
        if os.path.exists(ref) and os.path.getmtime(p) < os.path.getmtime(ref) - 1:
            bad += 1; say("FAIL", "trace", f"{label} {rid}: {ef} 早于 {fr} —— 评估发生在训练结束前（陈旧评估）")
        for col, path in mm.items():
            if col not in r or r[col] in ("", None): continue
            try: v = float(get_path(ev, path))
            except Exception:
                bad += 1; say("FAIL", "trace", f"{label} {rid}: {ef} 里没有 {path}"); continue
            s = r[col].strip()
            if not cell_matches(s, v):
                bad += 1; say("FAIL", "trace", f"{label} {rid}.{col} = {s}，但 {ef}#{path} = {v!r}（按 {s} 的打印精度不一致）")
    if bad == 0: say("PASS", "trace", f"{label} {len(rows)} 行全部回溯到 {ef} 且数值一致、评估不陈旧")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="research-state.yaml"); ap.add_argument("--prereg", default="prereg.md"); ap.add_argument("--project", default=".")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    st = load_yaml(os.path.join(root, a.state)); cfg = st.get("results") or {}
    if not cfg: say("FAIL", "results", "state 无 results: 段"); sys.exit(1)
    md = io.open(os.path.join(root, a.prereg), encoding="utf-8").read() if os.path.exists(os.path.join(root, a.prereg)) else ""
    if not md: say("WARN", "results", "无 prereg.md，跳过覆盖率与口径核对")
    main_p = os.path.join(root, cfg.get("main_table", "results/main.csv")); abl_p = os.path.join(root, cfg.get("ablation_table", "results/ablation.csv"))
    main_rows, main_cols = read_csv(main_p); abl_rows, abl_cols = read_csv(abl_p)
    if main_rows is None: say("FAIL", "trace", f"{cfg.get('main_table')} 不存在"); sys.exit(1)
    print("== trace =="); check_rows(cfg, root, main_rows, "main")
    if abl_rows is not None: check_rows(cfg, root, abl_rows, "ablation")
    # ---- convention
    print("\n== convention ==")
    pm = cfg.get("primary_metric", "")
    if not pm or pm not in main_cols:
        say("FAIL", "convention", f"primary_metric '{pm}' 不是 main.csv 的列（现有列 {main_cols}）")
    elif md:
        sec = section(md, "primary_metric")
        key = re.sub(r"_.*", "", pm).lower()
        if key not in sec.lower() and pm.lower() not in sec.lower():
            conv = (st.get("experiments") or {}).get("convention_changes") or []
            logged_conv = any(pm.lower() in str(c).lower() for c in conv)   # str(), not json.dumps: yaml gives date objects
            if logged_conv: say("WARN", "convention", f"主指标 '{pm}' 不在 prereg §2，但 state.experiments.convention_changes 登记了它（代理口径）—— 投稿主表必须换回预注册指标")
            else: say("FAIL", "convention", f"prereg §2 没有提到主指标 '{pm}'（主表的主指标必须是预注册的那个；代理口径要在 state.experiments.convention_changes 登记）")
        else: say("PASS", "convention", f"主指标 {pm} 与 prereg §2 一致")
    # direction of the primary metric: draft_plan picks the strongest baseline by it (min or max); a guessed-wrong direction names the worst one
    try:
        for c in (cfg.get("metric_direction") or {}): mdir.direction(c, cfg)
        if pm and mdir.direction(pm, cfg) is None:
            say("WARN", "convention", f"主指标 '{pm}' 的方向从名字猜不出（下游按 higher-is-better 选最强基线）—— 在 results.primary_direction 写 lower 或 higher")
    except ValueError as e: say("FAIL", "convention", f"research-state.yaml {e}")
    if md:
        win = section(md, "inclusion_window"); den = section(md, "denominator")
        hdr = io.open(main_p, encoding="utf-8-sig").read().splitlines()[0] + " " + " ".join(main_cols) + " " + (open(main_p, encoding="utf-8-sig").read()[:400])
        note_p = os.path.splitext(main_p)[0] + ".md"
        note = io.open(note_p, encoding="utf-8").read() if os.path.exists(note_p) else ""
        tokens = re.findall(r"(\|?F\|?\s*[≥>=]+\s*[\d.]+\s*N?|\d+(?:\.\d+)?\s*%|contact[- ]window|full[- ]window|≥\s*\d+%|[A-Za-z_]+_window|per[- ]pixel|per[- ]subject)", win + " " + den, re.I)
        if tokens and not any(t.lower() in (hdr + note).lower() for t in tokens):
            say("FAIL", "convention", f"prereg 的口径标记 {sorted(set(tokens))[:4]} 没有出现在 main.csv 表头/注释（{os.path.basename(note_p)}）—— 每张表必须标口径")
        elif tokens: say("PASS", "convention", "main.csv 表头/注释带 prereg 的口径标记")
    # ---- seeds
    print("\n== seeds ==")
    gk, ms = cfg.get("group_key", "method"), int(cfg.get("min_seeds", 3))
    seeds = collections.defaultdict(set)
    for r in main_rows: seeds[r.get(gk, "")].add(r.get("seed", "").strip())
    short = {g: s for g, s in seeds.items() if len({x for x in s if x}) < ms}
    if short and not cfg.get("seed_waiver"):
        for g, s in short.items(): say("FAIL", "seeds", f"{gk}={g}: 只有 {len({x for x in s if x})} 个 seed（要求 ≥{ms}），无 seed_waiver")
    elif short: say("WARN", "seeds", f"{len(short)} 个方法 seed <{ms}，已有 waiver: {cfg['seed_waiver'][:80]}")
    else: say("PASS", "seeds", f"所有 {len(seeds)} 个方法 ≥{ms} seeds")
    sets = {frozenset(x for x in s if x) for s in seeds.values()}
    if len(sets) > 1: say("WARN", "seeds", f"各方法的 seed 集合不一致: {[sorted(s) for s in sets][:4]} —— 配对比较要求同 seed")
    if md:
        # ---- coverage
        print("\n== coverage ==")
        pre_abl = table_first_col(section(md, "ablations")); pre_base = table_first_col(section(md, "baselines"))
        have_methods = sorted({r.get(gk, "") for r in main_rows})
        ref_m = cfg.get("reference_method", "ours")
        # a §6 row can be a multi-seed method in the main table (RS_nowcast: the DOFA-style scalar conditioning is both a baseline and ablation row 1)
        have_abl = [r.get("ablation") or r.get(gk, "") for r in (abl_rows or [])] + [m for m in have_methods if m != ref_m]
        aliases = cfg.get("aliases") or {}; waiver = cfg.get("coverage_waiver") or {}
        _n = flat
        def _covered(x, pool): return fuzzy_in(x, pool) or any(n in pool and _n(sub) and _n(sub) in _n(x) for n, sub in aliases.items())
        def _waived(x): return any(_n(k) and _n(k) in _n(x) for k in waiver)
        wv = [x for x in pre_abl + pre_base if _waived(x)]
        if wv: say("WARN", "coverage", f"{len(wv)} 项 prereg 基线/消融按 results.coverage_waiver 豁免: {wv[:3]} —— 投稿主表不得带豁免")
        pre_abl = [x for x in pre_abl if not _waived(x)]; pre_base = [x for x in pre_base if not _waived(x)]
        fuzzy_in_ = fuzzy_in
        miss = [x for x in pre_abl if not _covered(x, have_abl)]
        if pre_abl and abl_rows is None: say("FAIL", "coverage", f"prereg 列了 {len(pre_abl)} 项消融但 {cfg.get('ablation_table')} 不存在")
        elif miss: say("FAIL", "coverage", f"prereg §6 的消融未出现在 ablation.csv: {miss}")
        elif pre_abl: say("PASS", "coverage", f"prereg §6 的 {len(pre_abl)} 项消融全部有行")
        extra = [x for x in set(have_abl) if x and not fuzzy_in(x, pre_abl) and not any(_n(aliases.get(x, "")) and _n(aliases[x]) in _n(p) for p in pre_abl)]
        if extra: say("WARN", "coverage", f"ablation.csv 有 prereg 未登记的消融 {extra} —— 事后增补要在 state.convention_changes 留记录")
        missb = [x for x in pre_base if not _covered(x, have_methods)]
        if missb: say("FAIL", "coverage", f"prereg §5 的基线未出现在 main.csv: {missb}")
        elif pre_base: say("PASS", "coverage", f"prereg §5 的 {len(pre_base)} 个基线全部在主表")
    # ---- predictions (sign flip = anomaly: must be in findings.md before training continues)
    find_p = os.path.join(root, cfg.get("findings", "findings.md"))
    findings = io.open(find_p, encoding="utf-8").read().lower() if os.path.exists(find_p) else ""
    def logged(*names): return bool(findings) and all(str(n).lower() in findings for n in names if n)
    preds = cfg.get("predictions") or []
    if preds:
        print("\n== predictions ==")
        def mean_of(name, metric):
            xs = [float(r[metric]) for r in main_rows + (abl_rows or []) if (r.get(gk) == name or r.get("ablation") == name or r.get("run_id") == name) and r.get(metric, "") != ""]
            return statistics.mean(xs) if xs else None
        for p in preds:
            va, vb = mean_of(p["a"], p["metric"]), mean_of(p["b"], p["metric"])
            if va is None or vb is None: say("WARN", "predictions", f"{p}: 找不到 a/b 的 {p['metric']}"); continue
            d = vb - va; sign = "+" if d > 0 else "-" if d < 0 else "0"
            if sign != p["sign"]:
                if logged(p["b"], p["metric"]): say("WARN", "predictions", f"{p['b']} − {p['a']} on {p['metric']} = {d:+.4f} 与预测 {p['sign']} 反号，findings.md 已记录 —— 正文必须解释")
                else: say("FAIL", "predictions", f"{p['b']} − {p['a']} on {p['metric']} = {d:+.4f} 与预测 {p['sign']} 反号，findings.md 无记录 —— 反常先当发现写进 findings.md（含 {p['b']} 与 {p['metric']}）再继续训练，不许直接改配置")
            else: say("PASS", "predictions", f"{p['b']} − {p['a']} on {p['metric']} = {d:+.4f}，与预测 {p['sign']} 一致")
    # ---- reproductions: baseline re-run vs the number its paper reported; |Δ| > tol (default 2× reported std) = anomaly
    reps = cfg.get("reproductions") or []
    if reps:
        print("\n== reproductions ==")
        for q in reps:
            name, met = q["method"], q["metric"]
            xs = [float(r[met]) for r in main_rows if r.get(gk) == name and r.get(met, "") != ""]
            if not xs: say("WARN", "reproductions", f"{name}.{met}: 主表无该方法"); continue
            m = statistics.mean(xs); rep = float(q["reported"]); tol = float(q.get("tol", 2 * float(q.get("reported_std", 0)) or 0))
            if tol <= 0: say("WARN", "reproductions", f"{name}.{met}: 无 tol/reported_std，无法判定（复现 {m:.4f} vs 报告 {rep}）"); continue
            if abs(m - rep) > tol:
                if logged(name, met): say("WARN", "reproductions", f"{name}.{met}: 复现 {m:.4f} vs 报告 {rep}（|Δ| {abs(m-rep):.4f} > tol {tol}），findings.md 已记录")
                else: say("FAIL", "reproductions", f"{name}.{met}: 复现 {m:.4f} vs 报告 {rep}（|Δ| {abs(m-rep):.4f} > tol {tol}），findings.md 无记录 —— 基线复现偏差先写 findings.md（可能是口径/数据/泄漏，也可能就是论文）再继续")
            else: say("PASS", "reproductions", f"{name}.{met}: 复现 {m:.4f} vs 报告 {rep}，|Δ| ≤ {tol}")
    if not reps and main_rows:
        others = sorted({r.get(gk, "") for r in main_rows} - {cfg.get("reference_method", "ours"), ""})
        if others: say("WARN", "reproductions", f"reproductions 为空：至少把一个基线复现到其论文数字（主表有 {len(others)} 个基线 {others[:3]}）；仪器校准见 G3b —— 复现不到论文数字时，数字差是你的实现、不是方法")
    # ---- findings.md: a closing verdict needs evidence, not free text (med2: 'impl: excluded' with nothing behind it)
    blocks = finding_blocks(io.open(find_p, encoding="utf-8").read()) if os.path.exists(find_p) else []
    closed = [(fid, b) for fid, b in blocks if VERDICT.search(b)]
    if closed:
        print("\n== findings ==")
        n_bad = 0
        for fid, b in closed:
            if not evidence_paths(b, root):
                n_bad += 1; say("FAIL", "findings", f"{fid}: 分诊结论没有证据文件（命令输出）——自由文本不算排查；写 `evidence: <runs/…/x.txt results/…>` 指向存在的文件")
            if re.search(r"(?mi)^[ \t]*(?:-[ \t]*)?cause[ \t]*:[ \t]*real\b", b) and not re.search(r"(?mi)^[ \t]*(?:-[ \t]*)?control[ \t]*:[ \t]*\S", b):
                say("WARN", "findings", f"{fid}: cause: real 没有 control: 行（阳性或阴性对照：同一管线下已知答案的输入应得到已知结果）")
        if not n_bad: say("PASS", "findings", f"{len(closed)} 条已结案的 finding 都带存在的证据文件")
    # ---- failure analysis: averages hide failures; the slice report for the reference method must exist
    fs = os.path.join(root, cfg.get("failure_slices", "results/failure_slices.md"))
    if os.path.exists(fs): say("PASS", "failure", f"{os.path.relpath(fs, root)} 存在（failure_slice.py 输出）")
    else: say("WARN", "failure", f"无 {os.path.relpath(fs, root)}：对本文方法跑 `failure_slice.py --pred runs/<ref>/preds/...`，最差切片、集中度、模型知不知道要进正文失败分析")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
