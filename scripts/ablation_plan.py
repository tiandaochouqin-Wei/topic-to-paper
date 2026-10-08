# -*- coding: utf-8 -*-
"""P2/P4 — ablation planner and resolution check.

  plan      python ablation_plan.py plan  <train.py> [--model-file model.py] [--out ablation_plan.md]
  resolve   python ablation_plan.py resolve --state research-state.yaml [--prereg prereg.md] [--project .]

plan:   reads argparse switches and class/module names, proposes a one-factor-at-a-time ablation matrix with the
        standard design rules (reference = full model; one component removed per row; "component present but
        non-functional" controls for every learned module; interaction pairs only for components the prereg says
        interact; a matched-capacity control when a component adds parameters). Writes a table ready to paste into
        prereg §6, each row with: switch, how to disable, expected sign, interacts_with.

resolve: for every ablation row in results/ablation.csv, compute Δ = ablation − reference on the primary metric and
        compare to the seed spread of the reference (from main.csv rows with the same group_key as the reference and
        ≥2 seeds). Reports Δ/σ√2 per cell; cells below 2 are "not resolvable at single-run precision" and the number
        of such cells is compared with the binomial expectation under the null (EAAI §5.10 practice). Cells with
        resolvable Δ whose sign disagrees with prereg §6's expected sign are flagged. Exit 1 if any ablation row of
        prereg has no run, or any resolvable cell contradicts its expected sign without a convention_changes entry."""
import argparse, ast, csv, io, os, re, sys, statistics, math, collections

# ------------------------------------------------------------------ plan
def argparse_switches(path):
    src = io.open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"add_argument\(\s*['\"]--([A-Za-z_][\w\-]*)['\"]([^)]*)\)", src):
        name, rest = m.group(1), m.group(2)
        typ = (re.search(r"type\s*=\s*(\w+)", rest) or [None, "flag"])[1]
        default = (re.search(r"default\s*=\s*([^,)]+)", rest) or [None, ""])[1].strip()
        helptxt = (re.search(r"help\s*=\s*['\"]([^'\"]*)['\"]", rest) or [None, ""])[1]
        action = (re.search(r"action\s*=\s*['\"]([^'\"]*)['\"]", rest) or [None, ""])[1]
        out.append(dict(name=name, type=typ if not action else "flag", default=default, help=helptxt, action=action))
    return out

INFRA = re.compile(r"^(data|data_\w+|exp|out|output|seed|workers|num_workers|amp|resume|bs|batch|batch_size|epochs|lr|wd|weight_decay|device|gpu|log|save|ckpt|checkpoint|eval|test|verbose|debug|port|dist|local_rank)$")
LEAK = re.compile(r"(target|_B|B_|unlabel|adapt|finetune|test)", re.I)

def classify(sw):
    n = sw["name"].lower()
    if INFRA.match(n): return "infra"
    if LEAK.search(n) and sw["type"] in ("int", "flag", "bool"): return "leak-flag"
    if sw["type"] in ("flag", "bool") or (sw["type"] == "int" and sw["default"] in ("0", "1")): return "component"
    if sw["type"] == "float": return "coefficient"
    if sw["type"] == "str" and sw["default"]: return "choice"
    return "other"

def class_names(model_file):
    if not model_file or not os.path.exists(model_file): return []
    try: tree = ast.parse(io.open(model_file, encoding="utf-8").read())
    except SyntaxError: return []
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

def plan(train_py, model_file, out):
    sw = argparse_switches(train_py); cls = class_names(model_file)
    comps = [s for s in sw if classify(s) == "component"]
    coefs = [s for s in sw if classify(s) == "coefficient"]
    choices = [s for s in sw if classify(s) == "choice"]
    leaks = [s for s in sw if classify(s) == "leak-flag"]
    L = [f"# 消融矩阵草案（由 {os.path.basename(train_py)} 的开关自动生成；每行改一个因素，参考 = 全模型）", "",
         "规则：① 参考行 = 全部组件开启、β 等系数取正文值；② 每行只动一个开关；③ 每个**可学习**模块除\"去掉\"外再加一行\"保留但失效\"（随机初始化冻结 / 恒等替换），区分\"模块有用\"与\"多了参数有用\"；④ 加参数的组件配一行等参数量对照；⑤ 只对 prereg 写明\"相互作用\"的组件对做两因素行；⑥ 每行写事前预测符号；⑦ 分辨率：单 run 消融的 |Δ| 必须 > 2·σ_ref·√2 才可解读，σ_ref 来自参考模型的 ≥3 seeds（`ablation_plan.py resolve` 自动判）。", "",
         "## A. 组件开关（去掉 / 保留但失效）", "", "| 行 | 开关 | 怎么关 | 事前预测符号 | 与谁相互作用 | 备注 |", "|---|---|---|---|---|---|",
         "| ref | — | 全模型 | — | — | 主表同一 run |"]
    i = 1
    for s in comps:
        off = f"--{s['name']}" if s["type"] == "flag" else f"--{s['name']} {'0' if s['default'] != '0' else '1'}"
        L.append(f"| A{i} | {s['name']} | `{off}` | ? | ? | {s['help'][:40]} |"); i += 1
        if re.search(r"token|head|attn|attention|encoder|decoder|branch|module|net|fusion|distil", s["name"], re.I):
            L.append(f"| A{i} | {s['name']} (保留但失效) | 同结构，冻结随机初始化或恒等替换 | 0 或与 A{i-1} 同号但更小 | A{i-1} | 区分参数量效应 |"); i += 1
    L += ["", "## B. 系数置零 / 扫描（损失项、正则）", "", "| 行 | 系数 | 置零 | 扫描网格 | 事前预测符号 |", "|---|---|---|---|---|"]
    for s in coefs:
        L.append(f"| B{i} | {s['name']} (default {s['default']}) | `--{s['name']} 0` | 默认 ×{{0.1, 0.5, 2, 10}} | ? |"); i += 1
    if choices:
        L += ["", "## C. 离散选择（骨干 / 融合方式）", "", "| 行 | 开关 | 可选值 | 事前预测 |", "|---|---|---|---|"]
        for s in choices:
            L.append(f"| C{i} | {s['name']} (default {s['default']}) | 列出全部可选 | ? |"); i += 1
    L += ["", "## D. 必须恒为 0 的开关（不是消融，是泄漏护栏 → state.audits.leak_flags）", "", ", ".join(f"`{s['name']}`" for s in leaks) or "（未检测到）"]
    if cls:
        L += ["", "## E. 模型文件里的类（检查每个可学习模块是否都有 A 行）", "", ", ".join(cls)]
    L += ["", "## F. 覆盖率自检（填 prereg §6 前打勾）", "", "- [ ] 方法节提到的每个组件在 A 表有行", "- [ ] 每个损失项在 B 表有置零行", "- [ ] 参考行与主表的 run 是同一个（run_id 一致）", "- [ ] 参考模型 ≥3 seeds，否则所有消融格不可解读", "- [ ] 事前预测符号全部填写（不允许 ?）"]
    io.open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:40])); print(f"\n-> {out}  ({len(comps)} components, {len(coefs)} coefficients, {len(choices)} choices, {len(leaks)} leak flags)")

# ------------------------------------------------------------------ resolve
def load_yaml(p):
    import yaml
    return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}

def section(md, name):
    """body of the heading whose title starts with `name`, up to the next heading of EQUAL OR SHALLOWER depth (sub-headings stay inside)."""
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return ""
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

def expected_signs(prereg):
    """prereg §6 rows: first col = component, any col with 'drop/worse/+/增/下降/−' -> sign of (ablation − reference) on an error metric."""
    out = {}
    for l in section(prereg, "ablations").splitlines():
        if not l.strip().startswith("|"): continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower() in ("去掉/替换什么", "remove", "去掉/替换"): continue
        txt = " ".join(cells[1:]).lower()
        if re.search(r"worse|drop|degrad|increase|rise|larger|higher|up|\+|下降|变差|上升|变大|large|medium|small|moderate", txt): s = "+"
        elif re.search(r"better|improve|decrease|lower|smaller|−|-|改善|变好|变小", txt): s = "-"
        elif re.search(r"no change|unchanged|≈|~0|none|无", txt): s = "0"
        else: s = "?"
        out[cells[0]] = s
    return out

def norm_tok(s):
    return {w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if w not in {"no", "without", "w", "o", "the", "a", "of", "and", "remove", "removed", "ablation"}}

def resolve(state_p, prereg_p, project):
    root = os.path.abspath(project); st = load_yaml(os.path.join(root, state_p)); cfg = st.get("results") or {}
    main_p = os.path.join(root, cfg.get("main_table", "results/main.csv")); abl_p = os.path.join(root, cfg.get("ablation_table", "results/ablation.csv"))
    if not (os.path.exists(main_p) and os.path.exists(abl_p)):
        print("[FAIL] resolve: main/ablation csv 缺失"); sys.exit(1)
    main = list(csv.DictReader(open(main_p, encoding="utf-8-sig"))); abl = list(csv.DictReader(open(abl_p, encoding="utf-8-sig")))
    gk = cfg.get("group_key", "method"); ref = cfg.get("reference_method", "ours")
    metrics = [c for c in abl[0].keys() if c not in ("ablation", "run_id", "seed", "hardware", "table", gk) and re.match(r"^-?\d", (abl[0][c] or "x"))]
    # reference seeds from main.csv (same hardware as ablation rows if a hardware column exists)
    hw_abl = {r.get("hardware") for r in abl if r.get("hardware")}
    ref_rows = [r for r in main if r.get(gk) == ref and (not r.get("hardware") or not hw_abl or r.get("hardware") in hw_abl)]
    seeds = {r.get("seed") for r in ref_rows}
    fails = 0
    if len(seeds) < 2:
        print(f"[FAIL] resolve: 参考方法 '{ref}' 在 main.csv 只有 {len(seeds)} 个 seed（同硬件），无法给消融分辨率；所有消融格不可解读"); fails += 1
    sig = {m: (statistics.stdev([float(r[m]) for r in ref_rows]) if len(ref_rows) >= 2 else float("nan")) for m in metrics}
    mean = {m: statistics.mean([float(r[m]) for r in ref_rows]) for m in metrics} if ref_rows else {}
    exp = expected_signs(io.open(os.path.join(root, prereg_p), encoding="utf-8").read()) if os.path.exists(os.path.join(root, prereg_p)) else {}
    print(f"参考 '{ref}': {len(ref_rows)} 行 / seeds {sorted(seeds)}；σ_ref: " + ", ".join(f"{m}={sig[m]:.4f}" for m in metrics))
    print(f"\n{'ablation':22s} " + " ".join(f"{m[:14]:>16s}" for m in metrics) + "   resolvable/total  sign-check")
    tot = res = contra = 0
    for r in abl:
        name = r["ablation"]; es = next((v for k, v in exp.items() if norm_tok(k) & norm_tok(name) or norm_tok(name) <= norm_tok(k)), "?")
        cells = []; nres = 0; bad = []
        for m in metrics:
            if r.get(m, "") == "" or not ref_rows: cells.append(f"{'':>16s}"); continue
            d = float(r[m]) - mean[m]; z = abs(d) / (sig[m] * math.sqrt(2)) if sig[m] and sig[m] > 0 else float("inf")
            tot += 1; ok = z >= 2
            if ok: res += 1; nres += 1
            mark = "" if ok else "~"
            cells.append(f"{d:+.3f}({z:.1f}σ){mark}".rjust(16))
            if ok and es in ("+", "-") and (("+" if d > 0 else "-") != es): bad.append(m)
        if bad:
            contra += 1
            print(f"{name:22s} " + " ".join(cells) + f"   {nres}/{len(metrics)}   CONTRADICTS prereg sign {es} on {bad}")
        else:
            print(f"{name:22s} " + " ".join(cells) + f"   {nres}/{len(metrics)}   {'ok' if es != '?' else 'no prereg sign'}")
    null_expect = tot * 0.0455   # P(|z| ≥ 2) under H0 for a single-run difference vs seed sd (two-sided, σ√2)
    print(f"\n可解读格 {res}/{tot}（|Δ| ≥ 2·σ_ref·√2）；零假设下期望约 {null_expect:.1f} 格。" + ("**整体在单 run 分辨率极限，不逐格解读**" if res <= null_expect * 1.5 else "整体高于零假设，可逐格解读"))
    missing = [k for k in exp if not any(norm_tok(k) & norm_tok(r["ablation"]) or norm_tok(r["ablation"]) <= norm_tok(k) for r in abl)]
    if missing: print(f"[FAIL] resolve: prereg §6 有 {len(missing)} 项消融没有 run: {missing}"); fails += 1
    if contra:
        conv = (st.get("experiments") or {}).get("convention_changes") or []
        if not conv: print(f"[FAIL] resolve: {contra} 行与事前预测符号相反且 state.experiments.convention_changes 无记录"); fails += 1
        else: print(f"[WARN] resolve: {contra} 行与事前预测相反，convention_changes 有 {len(conv)} 条记录，需在正文解释")
    print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAIL")); sys.exit(0 if fails == 0 else 1)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("train_py"); p.add_argument("--model-file", default=""); p.add_argument("--out", default="ablation_plan.md")
    r = sub.add_parser("resolve"); r.add_argument("--state", default="research-state.yaml"); r.add_argument("--prereg", default="prereg.md"); r.add_argument("--project", default=".")
    a = ap.parse_args()
    if a.cmd == "plan": plan(a.train_py, a.model_file, a.out)
    else: resolve(a.state, a.prereg, a.project)
