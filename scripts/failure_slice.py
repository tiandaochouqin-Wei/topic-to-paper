# -*- coding: utf-8 -*-
"""P1/P4 — failure-case slicing: where does a method fail, and does it know? Run by Claude.

  python failure_slice.py --pred runs/<run>/preds/<file>.npz [--y y --mu mu --sig sig --id clip] \
                          [--covariates results/covariates.csv --key clip] [--bins 5] [--out results/failure_slices.md]
  python failure_slice.py --pred results/preds.csv --y target --mu pred [--sig conf] --id sample_id ...

Input: per-sample predictions (npz arrays or CSV columns): target y, prediction mu, optional predictive uncertainty sig,
and an id column. Optional covariates CSV joined on --key gives extra slicing variables (size, device, centre, quality, ...).
Built-in slices even without covariates: by id (clip / subject), by |y| quantile (target magnitude), by sig quantile.

Outputs (markdown + csv next to --out):
  1. per-slice error table (RMSE or MAE, n, share of total squared error)
  2. worst-slice ratio = worst slice error / overall error; >= 2 flagged: errors concentrate -> the paper's question becomes
     "why does it fail THERE", not "raise the mean"
  3. error concentration: share of total squared error in the worst 10 % of samples (0.1 = uniform; >0.5 = a few samples dominate)
  4. does the model know? Spearman(sig, |err|) and AUROC of sig for top-10 % errors (0.5 = blind; >0.7 = failure is predictable
     -> failure prediction / risk estimation is a paper on its own)
  5. covariate scan: for each covariate, worst bin vs best bin ratio, sorted; the top one is the candidate cause hypothesis
     to verify with a minimal controlled experiment (prereg §0 phenomenon) BEFORE designing a method.

Why: averages hide failures. Three past projects found their actual paper in a slice (contact window vs full window; kNN readout
vs learned readout; small-lesion Dice). Doing this mechanically at P1 (baseline code) and P4 (own runs) makes it routine.
"""
import argparse, csv, io, os, sys, math
import numpy as np

def load(a):
    if a.pred.endswith(".npz") or a.pred.endswith(".npy"):
        d = np.load(a.pred, allow_pickle=True)
        y, mu = np.asarray(d[a.y], float), np.asarray(d[a.mu], float)
        sig = np.asarray(d[a.sig], float) if a.sig and a.sig in d.files else None
        ids = np.asarray(d[a.id]) if a.id and a.id in d.files else np.arange(len(y))
        extra = {k: np.asarray(d[k]) for k in d.files if k not in (a.y, a.mu, a.sig, a.id) and d[k].ndim == 1 and len(d[k]) == len(y)}
    else:
        rows = list(csv.DictReader(open(a.pred, encoding="utf-8-sig")))
        y = np.array([float(r[a.y]) for r in rows]); mu = np.array([float(r[a.mu]) for r in rows])
        sig = np.array([float(r[a.sig]) for r in rows]) if a.sig and a.sig in rows[0] else None
        ids = np.array([r[a.id] for r in rows]) if a.id and a.id in rows[0] else np.arange(len(y))
        extra = {}
        for c in rows[0].keys():                      # every other column is a slicing covariate
            if c in (a.y, a.mu, a.sig, a.id): continue
            vals = [r[c] for r in rows]
            try: extra[c] = np.array([float(v) if v != "" else np.nan for v in vals])
            except ValueError: extra[c] = np.array(vals, dtype=object)
    if y.ndim > 1: err = np.sqrt(((y - mu) ** 2).sum(1)); ymag = np.sqrt((y ** 2).sum(1)); s = np.sqrt((sig ** 2).sum(1)) if sig is not None else None
    else: err = np.abs(y - mu); ymag = np.abs(y); s = sig
    return err, ymag, s, ids, extra

def covariates(a, ids):
    cov = {}
    if a.covariates and os.path.exists(a.covariates):
        rows = list(csv.DictReader(open(a.covariates, encoding="utf-8-sig")))
        key = a.key or a.id; by = {r[key]: r for r in rows}
        for c in rows[0].keys():
            if c == key: continue
            vals = [by.get(str(i), {}).get(c, "") for i in ids]
            try: cov[c] = np.array([float(v) if v != "" else np.nan for v in vals])
            except ValueError: cov[c] = np.array(vals, dtype=object)
    return cov

def slice_table(err, groups, name):
    out = []; tot = (err ** 2).sum(); overall = math.sqrt((err ** 2).mean())
    for g in sorted(set(groups.tolist()), key=lambda x: str(x)):
        m = groups == g; e = err[m]
        out.append({"slice": f"{name}={g}", "n": int(m.sum()), "rmse": math.sqrt((e ** 2).mean()), "share_sq_err": (e ** 2).sum() / tot if tot else 0, "ratio_vs_overall": math.sqrt((e ** 2).mean()) / overall if overall else 0})
    return out

def qbins(x, k):
    x = np.asarray(x, float); ok = ~np.isnan(x)
    qs = np.quantile(x[ok], np.linspace(0, 1, k + 1)); qs[-1] += 1e-9
    b = np.full(len(x), "nan", dtype=object)
    idx = np.clip(np.searchsorted(qs, x[ok], side="right") - 1, 0, k - 1)
    b[ok] = [f"q{i+1}/{k}[{qs[i]:.3g},{qs[i+1]:.3g})" for i in idx]
    return b

def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b)); return float(np.corrcoef(ra, rb)[0, 1])

def auroc(score, pos):
    s = np.asarray(score, float); p = np.asarray(pos, bool)
    if p.sum() == 0 or (~p).sum() == 0: return float("nan")
    r = np.argsort(np.argsort(s)) + 1
    return float((r[p].sum() - p.sum() * (p.sum() + 1) / 2) / (p.sum() * (~p).sum()))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", required=True); ap.add_argument("--y", default="y"); ap.add_argument("--mu", default="mu"); ap.add_argument("--sig", default="sig"); ap.add_argument("--id", default="clip")
    ap.add_argument("--covariates", default=""); ap.add_argument("--key", default=""); ap.add_argument("--bins", type=int, default=5); ap.add_argument("--out", default="results/failure_slices.md")
    ap.add_argument("--min-n", type=int, default=20, help="slices smaller than this are reported but not ranked")
    a = ap.parse_args()
    if not os.path.exists(a.pred): print(f"[FAIL] {a.pred} 不存在（该 run 没存逐样本预测？训练脚本要落 preds/）"); sys.exit(1)
    err, ymag, sig, ids, extra = load(a); cov = covariates(a, ids); cov.update({k: v for k, v in extra.items() if k not in cov})
    n = len(err); overall = math.sqrt((err ** 2).mean())
    L = [f"# Failure slices — {a.pred}", "", f"n = {n}, overall RMSE = {overall:.4f}（单位 = 预测文件里存的单位，可能是标准化后的；比值与排名不受影响）", ""]
    rows = []
    # 1 by id — only when ids are groups (clips/subjects), not one per sample
    if len(set(ids.tolist())) <= max(50, n // a.min_n): rows += slice_table(err, ids.astype(str), a.id or "id")
    # 2 by target magnitude
    if len(np.unique(ymag)) >= a.bins: rows += slice_table(err, qbins(ymag, a.bins), "|y|")
    # 3 by sig
    if sig is not None: rows += slice_table(err, qbins(sig, a.bins), "sig")
    # 4 covariates
    cov_rank = []
    for c, v in cov.items():
        if v.dtype == object: g = v.astype(str)
        else:
            if len(np.unique(v[~np.isnan(v)])) <= a.bins: g = np.array([f"{x:g}" if not np.isnan(x) else "nan" for x in v], dtype=object)
            else: g = qbins(v, a.bins)
        t = slice_table(err, g, c); rows += t
        big = [r for r in t if r["n"] >= a.min_n and r["slice"].split("=", 1)[1] != "nan"]
        if len(big) >= 2:
            w, b = max(big, key=lambda r: r["rmse"]), min(big, key=lambda r: r["rmse"])
            cov_rank.append((w["rmse"] / b["rmse"] if b["rmse"] else float("inf"), c, w["slice"], w["rmse"], b["slice"], b["rmse"]))
    # 2' worst slice ratio over slices with n >= min_n (excluding sig bins: those are the model's own ranking)
    ranked = [r for r in rows if r["n"] >= a.min_n and not r["slice"].startswith("sig=")]
    worst = max(ranked, key=lambda r: r["ratio_vs_overall"]) if ranked else None
    # 3' concentration
    e2 = np.sort(err ** 2)[::-1]; top = max(1, int(round(0.1 * n))); conc = e2[:top].sum() / e2.sum() if e2.sum() else 0
    # 4' does it know
    know = ""
    if sig is not None:
        rho = spearman(sig, err); au = auroc(sig, err >= np.quantile(err, 0.9))
        know = f"Spearman(sig, |err|) = {rho:+.3f}; AUROC(sig → top-10% error) = {au:.3f} " + ("→ **失败可预测**（可做失败预测/风险估计）" if au >= 0.7 else "→ 模型对自己的失败基本无感" if au < 0.6 else "→ 弱信号")
    L += ["## 信号", "", f"- 最差切片：{worst['slice']}（n={worst['n']}，RMSE {worst['rmse']:.4f}，是总体的 {worst['ratio_vs_overall']:.2f}×，占总平方误差 {worst['share_sq_err']:.0%}）" + ("  **← 误差集中，问题应改为\"为什么在这里失败\"**" if worst['ratio_vs_overall'] >= 2 else "") if worst else "- 无 n≥min_n 的切片",
          f"- 误差集中度：最差 10% 样本占总平方误差 {conc:.0%}（均匀 = 10%）" + ("  **← 少数样本主导**" if conc >= 0.5 else ""),
          f"- 模型知不知道：{know}" if know else "- 模型知不知道：无 sig 列，跳过", ""]
    if cov_rank:
        cov_rank.sort(reverse=True)
        L += ["## 协变量扫描（最差 bin / 最好 bin，候选原因假设按此排序）", "", "| 协变量 | 比值 | 最差 bin (RMSE) | 最好 bin (RMSE) |", "|---|---|---|---|"]
        L += [f"| {c} | {r:.2f} | {ws} ({wr:.4f}) | {bs} ({br:.4f}) |" for r, c, ws, wr, bs, br in cov_rank]
        L += ["", f"候选原因假设：**{cov_rank[0][1]}**（比值 {cov_rank[0][0]:.2f}）。下一步不是设计方法，是做一个只改这个变量的最小对照实验（prereg §0 现象验证）。", ""]
    L += ["## 全部切片", "", "| slice | n | RMSE | ×overall | share |", "|---|---|---|---|---|"]
    L += [f"| {r['slice']} | {r['n']} | {r['rmse']:.4f} | {r['ratio_vs_overall']:.2f} | {r['share_sq_err']:.1%} |" for r in rows]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    io.open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    with open(os.path.splitext(a.out)[0] + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["slice", "n", "rmse", "ratio_vs_overall", "share_sq_err"]); w.writeheader(); w.writerows(rows)
    print("\n".join(L[:len(L) - len(rows) - 4]))
    print(f"-> {a.out} (+ .csv, {len(rows)} slices)")

if __name__ == "__main__":
    main()
