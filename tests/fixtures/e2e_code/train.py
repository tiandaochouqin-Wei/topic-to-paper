# -*- coding: utf-8 -*-
"""End-to-end fixture trainer (CPU, seconds). The regression suite really runs this one through bundle.py's generated
scripts: run_one.sh -> train.py -> eval.py, so args.json / log.json / eval.json / hardware.json come from the pipeline,
not from hand-written files. Numbers are deterministic functions of (model, beta, alpha, seed) so every gate's
expectation (sign of the ablation, seed spread, coverage) can be asserted.

Data layout expected (what bundle.check_env.py verifies): $E1_PATH/<clip>/frames/index.json"""
import argparse, json, os, random, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--data", default=os.environ.get("E1_PATH", ""), help="defaults to $E1_PATH exported by run_one.sh")
    ap.add_argument("--model", default="ours")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--beta", type=float, default=0.0, help="weight of the domain-adversarial term (ours only)")
    ap.add_argument("--alpha", type=float, default=0.0, help="weight of the temporal consistency term (ours only)")
    ap.add_argument("--use_target_labels", type=int, default=0, help="leak flag: must stay 0 for every main-table run")
    a = ap.parse_args()
    if not a.data:
        raise SystemExit("no --data and no $E1_PATH")
    clips = [os.path.join(a.data, c) for c in sorted(os.listdir(a.data)) if os.path.isdir(os.path.join(a.data, c))]
    n = 0
    for c in clips:
        idx = os.path.join(c, "frames", "index.json")
        if not os.path.isfile(idx):
            raise FileNotFoundError("frames/index.json missing under " + c)   # never continue without vision
        n += len(json.load(open(idx, encoding="utf-8")))
    random.seed(a.seed)
    log = []
    for epoch in range(a.epochs):
        loss = 1.0 / (epoch + 1)
        train_dom = a.beta * loss if (a.model == "ours" and a.beta > 0) else 0.0
        train_cons = a.alpha * loss if (a.model == "ours" and a.alpha > 0) else 0.0
        log.append({"epoch": epoch, "loss": round(loss, 4), "train_dom": round(train_dom, 4), "train_cons": round(train_cons, 4), "n": n})
        sys.stdout.write(f"epoch {epoch} loss {loss:.3f} dom {train_dom:.3f} cons {train_cons:.3f}\n")
    out = os.path.join("runs", a.exp)
    os.makedirs(out, exist_ok=True)
    json.dump(vars(a), open(os.path.join(out, "args.json"), "w", encoding="utf-8"), indent=1)
    json.dump(log, open(os.path.join(out, "log.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
