# -*- coding: utf-8 -*-
"""Which way is better for a metric column. Shared by every script that picks a best / strongest / second-best value.

  direction(metric, results)  -> "lower" | "higher" | None (unknown; the caller picks its own default)

Order: research-state.yaml results.metric_direction[<col>]  >  results.primary_direction (primary_metric only)
       >  LOWER_BETTER name regex  >  HIGHER_BETTER name regex  >  None.
A name regex is a guess: delta_rel_Ta (a cross-protocol relative drop) matched neither list, fell through to higher-is-better
and draft_plan named the WORST method the strongest baseline (cvpr2027_medical, 2026-10-15). Set the direction explicitly.
"""
import re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

LOWER_BETTER = re.compile(r"rmse|mae|mse|mape|error|loss|nll|ece|fid|risk|fnr|fpr|far\b|miscoverage|brier|crps|width|size|latency|wer|cer"
                          r"|drop|delta|shift|gap|degrad|declin|asr", re.I)
HIGHER_BETTER = re.compile(r"csi|auc|acc|f1|iou|dice|\bmap\b|\bap\d*\b|psnr|ssim|recall|precision|pod|r2\b|corr|bleu|rouge|hss|ets|fss|top\d|hit", re.I)
_WORDS = {"lower": "lower", "low": "lower", "min": "lower", "minimize": "lower", "lower_is_better": "lower", "down": "lower", "↓": "lower",
          "higher": "higher", "high": "higher", "max": "higher", "maximize": "higher", "higher_is_better": "higher", "up": "higher", "↑": "higher"}

def norm(v, where="direction"):
    d = _WORDS.get(str(v).strip().lower())
    if d is None: raise ValueError(f"{where} = {v!r}: use lower or higher")
    return d

def direction(metric, results=None):
    res = results or {}
    md = res.get("metric_direction") or {}
    if metric in md and str(md[metric]).strip(): return norm(md[metric], f"results.metric_direction.{metric}")
    if metric and metric == res.get("primary_metric") and str(res.get("primary_direction") or "").strip():
        return norm(res["primary_direction"], "results.primary_direction")
    if LOWER_BETTER.search(metric or ""): return "lower"
    if HIGHER_BETTER.search(metric or ""): return "higher"
    return None

def lower_is_better(metric, results=None, default=False):
    d = direction(metric, results)
    return default if d is None else d == "lower"
