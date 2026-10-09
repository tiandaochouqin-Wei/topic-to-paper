# -*- coding: utf-8 -*-
"""Recompute tables/summary.csv from coding/coded.csv (fixture of the S4 'every table is re-derivable' rule).

  python coding/audit_summary.py            rewrite tables/summary.csv
  python coding/audit_summary.py --verify   re-derive and compare with the committed table; exit 1 on any difference
"""
import argparse, csv, io, os, statistics, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")


def derive(coded):
    rows = list(csv.DictReader(io.open(coded, encoding="utf-8-sig")))
    out = []
    for group, sel in (("M1", [r for r in rows if r["M"] == "1"]), ("M3", [r for r in rows if r["M"] == "3"]), ("all", rows)):
        deltas = [float(r["delta_rep"]) for r in sel if r["delta_rep"]]
        with_ci = sum(1 for r in sel if r["delta_ci"] == "yes")
        out.append({"group": group, "n": str(len(sel)), "median_delta": f"{statistics.median(deltas):.3f}", "share_delta_ci": f"{with_ci / len(sel):.3f}"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coded", default="coding/coded.csv")
    ap.add_argument("--out", default="tables/summary.csv")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    fresh = derive(a.coded)
    if a.verify:
        if not os.path.exists(a.out):
            print(f"[FAIL] {a.out} missing"); sys.exit(1)
        have = list(csv.DictReader(io.open(a.out, encoding="utf-8-sig")))
        bad = [(h, f) for h, f in zip(have, fresh) if dict(h) != f] + ([("length", len(have), len(fresh))] if len(have) != len(fresh) else [])
        for b in bad: print("[FAIL] summary differs:", b)
        print("ALL PASS" if not bad else f"{len(bad)} FAIL"); sys.exit(0 if not bad else 1)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group", "n", "median_delta", "share_delta_ci"]); w.writeheader(); w.writerows(fresh)
    print(f"{len(fresh)} rows -> {a.out}")


if __name__ == "__main__":
    main()
