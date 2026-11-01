# -*- coding: utf-8 -*-
"""P5 — choose the frames that show the difference, by a stated rule, instead of the first four files or a hand-picked favourite.

Round-3 figure review: in the qualitative grids every method looked the same on the chosen frames, so the caption's claim was invisible. Two modes:

  python select_samples.py det --gt-dir G --pred-dir P --methods m1,m2,...,ours --ours ours --label-fmt yolo|coco|voc|xyxy
                               [--iou 0.5] [--min-score 0.25] [--k 4] [--group-csv frames.csv --group-col condition] [--typical 1]
                               [--gt-name GT] [--image-dir IMG | --img-size W,H] --out samples.csv
      Per image and method: TP, FP, FN at IoU >= --iou (the matcher of make_comparison.py --box-status, so the numbers equal the drawn box colours: one-to-one,
      class-aware, best IoU first). Discrimination score of an image =
          (TP_ours - TP_b) + 0.5 * (FP_b - FP_ours) + (FN_b - FN_ours)   for the baseline b that is strongest on THAT image (the smallest score over the baselines).
      The k highest scores are chosen, at most ceil(k / n_groups) per group (--group-csv: a table with an `image`/`sample` column and --group-col, e.g. 2 day + 2
      night), ties broken by more ground-truth objects, then by image id; --typical n adds n images whose score is closest to the median (honest context).
      Images where ours is WORSE than the strongest baseline by at least the same margin are the counter-examples (printed, written to <out>_counter.csv).
  python select_samples.py cam --overlay-dir O --gt-dir G --methods ... --ours ours [--label-fmt yolo] [--k 4] [--group-csv ...] [--typical n] --out samples.csv
      Per image and method the share of the (min-max normalised, as drawn) activation mass inside the union of the ground-truth boxes ("in-box share");
      score = share_ours - max(share of the baselines); same selection and counter-examples. Images without ground-truth boxes are skipped.

Layouts (as make_comparison.py grid): predictions / overlays at <dir>/<method>/<sample>.<ext> (.txt .json .xml for labels, .npy .png for overlays); ground truth at
<gt-dir>/<sample>.<ext> or <gt-dir>/<gt-name>/<sample>.<ext> (gt-name default GT).

Writes
  <out>                 image, group, score, then tp_<m>, fp_<m>, fn_<m> per method (det) or inbox_<m> (cam), kind (win | typical): the --cell-counts input of the grid
  <out stem>_counter.csv  the counter-examples (same columns)
  <out stem>.all.csv      every image with its score (nothing is hidden)
  <out stem>.meta.json    the rule, parameters, global win / loss / tie counts over ALL images, selected / typical / counter-example ids, per-method totals:
                          caption_draft.py states them ("ours is worse than the best baseline on L of N frames"), no silent cherry-picking
Exit code = number of [FAIL] lines.
"""
import argparse, csv, glob, io, json, math, os, re, statistics, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import make_comparison as mc

FAILS = 0
BIG = 1.0e6              # image size when none is known: pixel boxes are scaled by it, IoU is invariant to a common scale and nothing is clipped at 1.0
IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")

def say(sev, msg):
    global FAILS
    if sev == "FAIL": FAILS += 1
    print(f"[{sev}] {msg}")

def die(msg):
    say("FAIL", msg); sys.exit(1)


# ------------------------------------------------------------------ inputs
def _stem(name): return os.path.splitext(os.path.basename(str(name).strip()))[0]

def gt_ids(gt_dir, gt_name, exts):
    out = {}
    for d in (os.path.join(gt_dir, gt_name), gt_dir):
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p) and f.lower().endswith(exts): out.setdefault(_stem(f), p)
    return out

def read_groups(path, col):
    rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig", newline="")))
    if not rows: die(f"{path}: empty")
    if col not in rows[0]: die(f"{path}: no column {col!r} (columns: {list(rows[0])})")
    key = next((c for c in ("image", "sample", "frame", "id", "name", "file", "filename") if c in rows[0]), list(rows[0])[0])
    return {_stem(r[key]): (r[col] or "").strip() for r in rows if r.get(key)}

def image_size(a, sample):
    if a.image_dir:
        for d in (a.image_dir, os.path.join(a.image_dir, a.gt_name)):
            for e in IMG_EXTS:
                p = os.path.join(d, sample + e)
                if os.path.isfile(p):
                    from PIL import Image
                    with Image.open(p) as im: return float(im.size[0]), float(im.size[1])
    if a.img_size: return a.img_size
    return BIG, BIG

def pred_path(P, m, sample, exts):
    for e in exts:
        p = os.path.join(P, m, sample + e)
        if os.path.isfile(p): return p
    return None


# ------------------------------------------------------------------ scoring
def det_counts(gt, pred, iou):
    status, missed = mc.match_boxes(gt, pred, iou)
    return {"tp": status.count("tp"), "fp": status.count("fp"), "fn": len(missed)}

def det_score(c, ours, baselines):
    """smallest pairwise discrimination score over the baselines = the score against the baseline that is strongest on this image"""
    best = None
    for b in baselines:
        s = (c[ours]["tp"] - c[b]["tp"]) + 0.5 * (c[b]["fp"] - c[ours]["fp"]) + (c[b]["fn"] - c[ours]["fn"])
        best = s if best is None else min(best, s)
    return float(best if best is not None else 0.0)

def inbox_share(mask_boxes, path):
    import numpy as np
    from PIL import Image
    if path.lower().endswith(".npy"): m = np.nan_to_num(np.squeeze(np.load(path)).astype(np.float64))
    else: m = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
    if m.ndim != 2: raise ValueError(f"{path}: expected a 2-D map, got shape {m.shape}")
    lo, hi = float(m.min()), float(m.max()); H, W = m.shape
    inside = np.zeros((H, W), bool)
    for (_c, x0, y0, x1, y1) in mask_boxes: inside[int(math.floor(y0 * H)):int(math.ceil(y1 * H)), int(math.floor(x0 * W)):int(math.ceil(x1 * W))] = True
    if hi <= lo: return float(inside.mean())                      # a flat map carries no information: uniform mass, share = box area fraction
    m = (m - lo) / (hi - lo)                                    # the same min-max normalisation the grid draws
    return float(m[inside].sum() / m.sum())


# ------------------------------------------------------------------ selection
def select(items, k, groups, typical, default_margin):
    """items: [{image, group, score, n_gt}] -> (selected, typical_items, counter_examples, margin). Ties: more ground-truth objects, then image id."""
    order = sorted(items, key=lambda r: (-r["score"], -r["n_gt"], r["image"]))
    gnames = sorted({r["group"] for r in items} - {""})
    quota = math.ceil(k / len(gnames)) if gnames else k
    cnt = {}; sel = []
    for r in order:
        if len(sel) >= k: break
        g = r["group"] if gnames else ""
        if cnt.get(g, 0) >= quota: continue
        cnt[g] = cnt.get(g, 0) + 1; sel.append(r)
    wins = [r for r in sel if r["score"] > 1e-9]
    margin = min([r["score"] for r in wins]) if wins else default_margin
    counter = sorted([r for r in items if r["score"] <= -margin + 1e-12], key=lambda r: (r["score"], r["image"]))
    typ = []
    if typical > 0 and items:
        med = statistics.median(r["score"] for r in items); chosen = {r["image"] for r in sel}
        typ = sorted([r for r in items if r["image"] not in chosen], key=lambda r: (abs(r["score"] - med), -r["n_gt"], r["image"]))[:typical]
    return sel, typ, counter, margin, quota, gnames


def common(a, mode):
    methods = [m for m in a.methods.split(",") if m]
    if a.ours not in methods: die(f"--ours {a.ours!r} is not among --methods {methods}")
    baselines = [m for m in methods if m != a.ours]
    if not baselines: die("--methods needs at least one baseline besides --ours")
    if not os.path.isdir(a.gt_dir): die(f"--gt-dir {a.gt_dir} is not a directory")
    exts = mc.LABEL_EXT[a.label_fmt]
    ids = gt_ids(a.gt_dir, a.gt_name, exts)
    if not ids: die(f"no ground-truth files {exts} in {a.gt_dir} (or {a.gt_dir}/{a.gt_name})")
    grp = read_groups(a.group_csv, a.group_col) if a.group_csv else {}
    if a.group_csv:
        missing = sorted(set(ids) - set(grp))
        if missing: say("WARN", f"{len(missing)} image(s) have no row in {a.group_csv}: they get group '' ({missing[:3]}…)")
    if a.k < 1: die("--k must be >= 1")
    return methods, baselines, exts, ids, grp


def write_outputs(a, mode, rows, cols, sel, typ, counter, margin, quota, gnames, meta_extra, methods):
    out = os.path.abspath(a.out); stem = os.path.splitext(out)[0]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    header = ["image", "group", "score"] + cols + ["kind"]
    def line(r, kind): return [r["image"], r["group"], f"{r['score']:g}"] + [r["cells"][c] for c in cols] + [kind]
    def dump(p, rs, kind):
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(header); [w.writerow(line(r, kind(r))) for r in rs]
    dump(out, sel + typ, lambda r: "typical" if r in typ else "win")
    dump(stem + "_counter.csv", counter, lambda r: "counter")
    dump(stem + ".all.csv", sorted(rows, key=lambda r: (-r["score"], r["image"])), lambda r: "")
    wins = sum(1 for r in rows if r["score"] > 1e-9); losses = sum(1 for r in rows if r["score"] < -1e-9); ties = len(rows) - wins - losses
    if mode == "det":
        rule = (f"for each frame, ours versus the baseline that is strongest on that frame: (TP gain) + 0.5 × (FP reduction) + (FN reduction) at IoU ≥ {a.iou:g}"
                f"; the {a.k} frames with the largest advantage" + (f", at most {quota} per {a.group_col}" if gnames else "") + (f", plus {a.typical} median-score frame(s)" if typ else ""))
    else:
        rule = (f"for each frame, the share of the normalised activation mass inside the ground-truth boxes, ours minus the best baseline; the {a.k} frames with the largest advantage"
                + (f", at most {quota} per {a.group_col}" if gnames else "") + (f", plus {a.typical} median-score frame(s)" if typ else ""))
    meta = {"mode": mode, "rule": rule, "ours": a.ours, "methods": methods, "k": a.k, "typical_requested": a.typical, "label_fmt": a.label_fmt, "n_images": len(rows), "wins": wins, "losses": losses, "ties": ties,
            "counter_margin": margin, "n_counter": len(counter), "counter_examples": [r["image"] for r in counter], "selected": [r["image"] for r in sel], "typical": [r["image"] for r in typ],
            "group_col": a.group_col if gnames else "", "group_quota": quota if gnames else None, "groups": {g: sum(1 for r in rows if r["group"] == g) for g in gnames},
            "scores": {r["image"]: r["score"] for r in rows}}
    meta.update(meta_extra)
    with io.open(stem + ".meta.json", "w", encoding="utf-8", newline="\n") as f: json.dump(meta, f, ensure_ascii=False, indent=1)
    say("INFO", f"{len(rows)} images scored: ours better than the strongest baseline on {wins}, worse on {losses}, tied on {ties}")
    if any(r["score"] <= 1e-9 for r in sel): say("WARN", f"only {sum(1 for r in sel if r['score'] > 1e-9)} of {len(sel)} chosen frame(s) show ours ahead: the difference is not visible on every chosen frame; say so in the caption or lower --k")
    if len(sel) < a.k: say("WARN", f"only {len(sel)} of --k {a.k} frames selected" + (f" (quota {quota} per group)" if gnames else ""))
    for r in sel: print(f"  chosen   {r['image']:<24} group={r['group'] or '-':<10} score={r['score']:g}")
    for r in typ: print(f"  typical  {r['image']:<24} group={r['group'] or '-':<10} score={r['score']:g}")
    if counter:
        say("INFO", f"counter-examples (ours worse by >= {margin:g}): {len(counter)} of {len(rows)} frames -> {os.path.basename(stem)}_counter.csv")
        for r in counter[:8]: print(f"  counter  {r['image']:<24} group={r['group'] or '-':<10} score={r['score']:g}")
    else: say("INFO", "no counter-examples at the selection margin")
    say("PASS", f"wrote {os.path.basename(out)} ({len(sel) + len(typ)} rows), {os.path.basename(stem)}_counter.csv, {os.path.basename(stem)}.all.csv, {os.path.basename(stem)}.meta.json")


def cmd_det(a):
    methods, baselines, exts, ids, grp = common(a, "det")
    if not os.path.isdir(a.pred_dir): die(f"--pred-dir {a.pred_dir} is not a directory")
    cols = [f"{k}_{m}" for m in methods for k in ("tp", "fp", "fn")]
    rows = []; missing = {m: 0 for m in methods}; tot = {m: {"tp": 0, "fp": 0, "fn": 0} for m in methods}
    for sample, gpath in sorted(ids.items()):
        iw, ih = image_size(a, sample)
        gt = mc.read_boxes(gpath, a.label_fmt, iw, ih)
        c = {}
        for m in methods:
            pp = pred_path(a.pred_dir, m, sample, exts)
            if pp is None: missing[m] += 1
            pred = mc.read_boxes(pp, a.label_fmt, iw, ih, a.min_score or None) if pp else []
            c[m] = det_counts(gt, pred, a.iou)
            for k in tot[m]: tot[m][k] += c[m][k]
        rows.append({"image": sample, "group": grp.get(sample, ""), "score": det_score(c, a.ours, baselines), "n_gt": len(gt),
                     "cells": {f"{k}_{m}": str(c[m][k]) for m in methods for k in ("tp", "fp", "fn")}})
    for m, n in missing.items():
        if n: say("WARN", f"method {m!r}: no prediction file for {n} of {len(rows)} images (counted as no detections)")
    if not a.image_dir and not a.img_size: say("INFO", "image size unknown: pixel boxes are compared in pixel units (IoU is scale-invariant); give --image-dir or --img-size when GT and predictions use different coordinate systems")
    sel, typ, counter, margin, quota, gnames = select(rows, a.k, grp, a.typical, 0.5)
    write_outputs(a, "det", rows, cols, sel, typ, counter, margin, quota, gnames, {"iou": a.iou, "min_score": a.min_score, "per_method_totals": tot, "missing_predictions": missing,
                                                                              "matcher": "make_comparison.match_boxes (one-to-one, class-aware, best IoU first)"}, methods)
    return FAILS


def cmd_cam(a):
    methods, baselines, exts, ids, grp = common(a, "cam")
    if not os.path.isdir(a.overlay_dir): die(f"--overlay-dir {a.overlay_dir} is not a directory")
    cols = [f"inbox_{m}" for m in methods]
    rows = []; skipped = {"no GT boxes": 0, "ours has no overlay": 0, "no baseline overlay": 0}; png_used = False
    for sample, gpath in sorted(ids.items()):
        iw, ih = image_size(a, sample)
        gt = mc.read_boxes(gpath, a.label_fmt, iw, ih)
        if not gt: skipped["no GT boxes"] += 1; continue
        sh = {}
        for m in methods:
            p = mc._find(a.overlay_dir, m, sample, (".npy", ".png"))
            if p is None: continue
            png_used = png_used or p.lower().endswith(".png")
            sh[m] = inbox_share(gt, p)
        if a.ours not in sh: skipped["ours has no overlay"] += 1; continue
        base = [sh[b] for b in baselines if b in sh]
        if not base: skipped["no baseline overlay"] += 1; continue
        rows.append({"image": sample, "group": grp.get(sample, ""), "score": sh[a.ours] - max(base), "n_gt": len(gt), "cells": {f"inbox_{m}": (f"{sh[m]:.4f}" if m in sh else "") for m in methods}})
    for why, n in skipped.items():
        if n: say("WARN", f"{n} image(s) skipped: {why}")
    if not rows: die("no image has ground-truth boxes and overlays for ours and at least one baseline")
    if png_used: say("WARN", "some overlays are .png: colour-mapped images carry no activation values, their luminance is used as a proxy (prefer .npy maps)")
    sel, typ, counter, margin, quota, gnames = select(rows, a.k, grp, a.typical, 0.05)
    write_outputs(a, "cam", rows, cols, sel, typ, counter, margin, quota, gnames, {"skipped": skipped, "share": "mass of the min-max normalised map inside the union of the GT boxes / total mass"}, methods)
    return FAILS


def main():
    ap = argparse.ArgumentParser(description="choose the frames for a qualitative grid by a stated rule (det: TP / FP / FN advantage of ours; cam: in-box share of the activation mass)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    def shared(p):
        p.add_argument("--gt-dir", required=True); p.add_argument("--methods", required=True, help="comma-separated method directory names, ours included")
        p.add_argument("--ours", required=True); p.add_argument("--label-fmt", choices=["yolo", "coco", "voc", "xyxy"], default="yolo")
        p.add_argument("--gt-name", default="GT", help="sub-directory of --gt-dir holding the ground-truth files when they are not directly in it")
        p.add_argument("--k", type=int, default=4); p.add_argument("--typical", type=int, default=0, help="also pick this many frames whose score is closest to the median")
        p.add_argument("--group-csv", default=""); p.add_argument("--group-col", default="group")
        p.add_argument("--image-dir", default="", help="images for pixel-coordinate label formats: <dir>/<sample>.png|jpg"); p.add_argument("--img-size", default="", help="W,H when all images share one size")
        p.add_argument("--out", required=True)
    d = sub.add_parser("det", help="detection frames: TP / FP / FN advantage of ours"); shared(d)
    d.add_argument("--pred-dir", required=True, help="<dir>/<method>/<sample>.txt|json|xml"); d.add_argument("--iou", type=float, default=0.5); d.add_argument("--min-score", type=float, default=0.25)
    c = sub.add_parser("cam", help="activation-map frames: in-box share of the activation mass"); shared(c)
    c.add_argument("--overlay-dir", required=True, help="<dir>/<method>/<sample>.npy|png")
    a = ap.parse_args()
    if a.img_size:
        try: a.img_size = tuple(float(x) for x in a.img_size.split(",")); assert len(a.img_size) == 2
        except Exception: die("--img-size needs W,H")
    else: a.img_size = None
    sys.exit(min(cmd_det(a) if a.cmd == "det" else cmd_cam(a), 255))

if __name__ == "__main__":
    main()
