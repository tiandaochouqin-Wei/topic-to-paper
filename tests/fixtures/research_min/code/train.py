# -*- coding: utf-8 -*-
"""Fixture training script. Never executed by the tests: audit_check.py scans it statically for
leak flags, gated hyper-parameters and silent fallbacks, so its shape matters, not its numbers."""
import argparse, json, os, random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--exp", required=True)
    ap.add_argument("--model", default="ours")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--beta", type=float, default=0.1, help="weight of the domain-adversarial term")
    ap.add_argument("--alpha", type=float, default=0.5, help="weight of the temporal consistency term")
    ap.add_argument("--use_target_labels", type=int, default=0, help="leak flag: must stay 0 for every main-table run")
    a = ap.parse_args()
    random.seed(a.seed)
    if not os.path.isdir(os.path.join(a.data, "frames")):
        raise FileNotFoundError("frames/ missing under " + a.data)
    index = json.load(open(os.path.join(a.data, "frames", "index.json"), encoding="utf-8"))
    log = []
    for epoch in range(a.epochs):
        loss = 1.0 / (epoch + 1)
        train_dom = a.beta * loss if a.beta > 0 else 0.0
        train_cons = a.alpha * loss if a.alpha > 0 else 0.0
        log.append({"epoch": epoch, "loss": loss, "train_dom": train_dom, "train_cons": train_cons, "hardware": "A2000", "n": len(index)})
    out = os.path.join("runs", a.exp)
    os.makedirs(out, exist_ok=True)
    json.dump(dict(vars(a), hardware="A2000"), open(os.path.join(out, "args.json"), "w", encoding="utf-8"), indent=1)
    json.dump(log, open(os.path.join(out, "log.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
