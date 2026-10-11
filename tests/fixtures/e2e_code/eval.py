# -*- coding: utf-8 -*-
"""End-to-end fixture evaluator: runs/<exp>/{args,log}.json -> runs/<exp>/eval.json. Deterministic in (model, beta, alpha, seed):
  ours (beta>0, alpha>0): rmse_E1 = 0.200 + 0.002*seed      no_dom (beta=0): +0.050 (resolvable)   no_cons (alpha=0): +0.001 (inside seed noise)
  baseA: 0.247 + 0.003*seed   baseB: 0.266 + 0.004*seed     rmse_E2 = rmse_E1 + 0.103
An unfinished run (log shorter than epochs) is written with _tainted so the gates refuse it."""
import argparse, json, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="run id, or several joined by ,")
    a = ap.parse_args()
    for exp in a.exp.split(","):
        d = os.path.join("runs", exp)
        args = json.load(open(os.path.join(d, "args.json"), encoding="utf-8"))
        log = json.load(open(os.path.join(d, "log.json"), encoding="utf-8"))
        m, s = args["model"], int(args["seed"])
        if m == "ours":
            e1 = 0.200 + 0.002 * s + (0.050 if args["beta"] <= 0 else 0.0) + (0.001 if args["alpha"] <= 0 else 0.0)
        elif m == "baseA":
            e1 = 0.247 + 0.003 * s
        else:
            e1 = 0.266 + 0.004 * s
        ev = {"E1": {"rmse": round(e1, 4), "n": 1200}, "E2": {"rmse": round(e1 + 0.103, 4), "n": 900}}
        if len(log) < int(args["epochs"]):
            ev["_tainted"] = "evaluated before training finished"
        json.dump(ev, open(os.path.join(d, "eval.json"), "w", encoding="utf-8"), indent=1)
        print(exp, ev["E1"]["rmse"], ev["E2"]["rmse"])


if __name__ == "__main__":
    main()
