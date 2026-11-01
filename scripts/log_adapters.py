# -*- coding: utf-8 -*-
"""Training logs -> one epoch-level long CSV that `make_figure.py curves --x epoch --y value --series method` reads.

  python log_adapters.py --adapter ultralytics|mmengine|lightning|csv|json|tensorboard --input <path>
        --metric-col <name> [--epoch-col <name>] --method M --dataset D --units fraction|percent|none
        --out results/curves_x.csv [--seed 0] [--append] [--extra key=value ...] [--header-comment] [--step-is-epoch]

Output (percent is the output unit; with --units none the values stay unchanged and units_out is none):
  epoch,value,method,dataset,seed,metric,units_in,units_out,source_file,source_sha256,adapter,epoch_base[,<extra keys>]

Rules (never guess):
  * --units is MANDATORY. fraction -> value*100 (recorded in units_in); percent -> unchanged; none -> unchanged, for quantities that are not
    percentages at all (training loss, learning rate, counts): no conversion, no percent plausibility check, units_in = units_out = none.
    fraction with any value > 1.5 = FAIL; percent with >= 5 values all <= 1.0 = WARN (probably a fraction).
  * duplicate epochs: keep the last + WARN; gaps between min and max epoch: WARN listing them; NaN/inf rows: dropped, counted in a WARN.
  * ultralytics: results.csv, header cells are space-padded (stripped); epoch column `epoch` (0- or 1-based is kept, epoch_base records the first).
    mmengine: JSON-lines (*.log.json); only lines with mode == val carry the metric; lines without the metric / epoch are skipped and counted.
    lightning: metrics.csv; only rows where the metric is non-empty (train and val rows interleave); epoch repeats are collapsed (last wins).
    csv: any CSV with an epoch column and a metric column.
    json: the log.json training scripts write: a list with one dict per epoch ([{"epoch": 0, "loss": 1.2, "val_AP": 30.1}, ...]; records
    without the metric, e.g. validation every 10 epochs, are skipped) or a dict of equal-length lists ({"epoch": [...], "loss": [...]}; without
    an "epoch" key the list index is the epoch). Not for JSON-lines (that is mmengine).
    epoch_base = smallest epoch in the whole log, even when the metric is logged only every k epochs.
    tensorboard: scalar tag --metric-col from an event file/dir. The step is an ITERATION counter in most setups, so it is accepted as epoch only
    with --step-is-epoch. Needs `pip install tensorboard`.
  * --append merges into an existing --out (rows with the same method/dataset/seed/metric are replaced); other methods are kept.
  * --header-comment writes a first line `# adapter=..., input=..., units_in=...` (provenance travels with the file; the per-row columns carry it
    anyway). Readers that do not skip `#` lines (make_figure.py's CSV loader) need it OFF, which is the default.
Exit code = number of [FAIL] lines."""
import argparse, csv, hashlib, io, json, math, os, sys
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, g, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {g}: {msg}")

class Fail(Exception): pass

BASE_COLS = ["epoch", "value", "method", "dataset", "seed", "metric", "units_in", "units_out", "source_file", "source_sha256", "adapter", "epoch_base"]
DEFAULT_EPOCH = {"ultralytics": "epoch", "mmengine": "epoch", "lightning": "epoch", "csv": "epoch", "json": "epoch"}


def sha256_of(path):
    h = hashlib.sha256()
    files = [path] if os.path.isfile(path) else sorted(os.path.join(dp, f) for dp, _, fs in os.walk(path) for f in fs if "tfevents" in f)
    for f in files:
        h.update(os.path.basename(f).encode("utf-8"))
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def _num(x):
    """float or None (empty / non-numeric)"""
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    s = str(x).strip()
    if not s: return None
    try: return float(s)
    except ValueError: return None


def _find_col(header, name, what):
    stripped = {h.strip(): h for h in header}
    if name in stripped: return stripped[name]
    low = {h.strip().lower(): h for h in header}
    if name.strip().lower() in low: return low[name.strip().lower()]
    raise Fail(f"{what} 列 '{name}' 不在输入里；现有列: {[h.strip() for h in header][:30]}")


def _looks_json(path):
    """True when the file is ONE JSON document starting with [ or { (JSON-lines does not parse as one document)"""
    try:
        with open(path, encoding="utf-8-sig") as f: txt = f.read()
    except (OSError, UnicodeDecodeError): return False
    if txt.lstrip()[:1] not in ("[", "{"): return False
    try: json.loads(txt)
    except ValueError: return False
    return True


def read_json(path, metric, epoch):
    """(pairs, info) from a JSON log: list of per-epoch dicts, or dict of equal-length lists. Records without the metric are skipped (counted in
    info['no_metric']); info['epoch_min'] = smallest epoch over ALL records = the numbering base even when the metric is logged every k epochs."""
    try:
        with open(path, encoding="utf-8-sig") as f: obj = json.load(f)
    except ValueError as ex:
        raise Fail(f"{path} 不是单个 JSON 文档（{ex}）；若是每行一个 JSON 的日志，用 --adapter mmengine")
    if isinstance(obj, dict) and obj and not all(isinstance(v, list) and v and not isinstance(v[0], dict) for v in obj.values()):
        inner = [v for v in obj.values() if isinstance(v, (list, dict))]
        if len(inner) == 1: obj = inner[0]                                          # {"history": [...]} / {"log": {...}}
    if isinstance(obj, dict):
        if not obj or not all(isinstance(v, list) for v in obj.values()) or len({len(v) for v in obj.values()}) != 1:
            raise Fail("JSON 是 dict，但不是等长 list 的 dict（{'epoch': [...], 'loss': [...]}），也不是 list of dict")
        n = len(next(iter(obj.values()))); recs = [{k: v[i] for k, v in obj.items()} for i in range(n)]
        if epoch not in obj:
            for i, r in enumerate(recs): r[epoch] = i
    elif isinstance(obj, list):
        recs = [r for r in obj if isinstance(r, dict)]
        if not recs: raise Fail("JSON 是 list，但里面没有 dict 记录（需要每 epoch 一条 dict）")
    else:
        raise Fail("JSON 顶层既不是 list of dict 也不是 dict of list")
    keys = {}
    for r in recs:
        for k in r: keys.setdefault(str(k).strip().lower(), k)
    mk, ek = keys.get(metric.strip().lower()), keys.get(epoch.strip().lower())
    if mk is None: raise Fail(f"metric 键 '{metric}' 不在 JSON 记录里；现有键: {sorted(map(str, keys.values()))[:30]}")
    if ek is None: raise Fail(f"epoch 键 '{epoch}' 不在 JSON 记录里；现有键: {sorted(map(str, keys.values()))[:30]}（用 --epoch-col 指定，或用 dict of list，下标就是 epoch）")
    pairs, skipped, no_metric, eps = [], 0, 0, []
    for r in recs:
        e = _num(r.get(ek))
        if e is None: skipped += 1; continue
        eps.append(e)
        if r.get(mk) is None: no_metric += 1; continue
        m = _num(r[mk]); pairs.append((e, m if m is not None else float("nan")))
    return pairs, {"skipped": skipped, "no_metric": no_metric, "epoch_min": min(eps) if eps else None}


def read_table(path, metric, epoch, require_nonempty=False):
    """(pairs, info) from a CSV: pairs = [(epoch, raw value)] in file order; unparseable / empty cells are counted in info['skipped']."""
    if _looks_json(path): raise Fail(f"{os.path.basename(path)} 是 JSON 文件，不是 CSV：用 --adapter json")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f); header = next(rd, None)
        if not header: raise Fail(f"{path} 是空文件")
        mc, ec = _find_col(header, metric, "metric"), _find_col(header, epoch, "epoch")
        mi, ei = header.index(mc), header.index(ec)
        pairs, skipped = [], 0
        for row in rd:
            if not row or not any(c.strip() for c in row): continue
            m = _num(row[mi]) if mi < len(row) else None; e = _num(row[ei]) if ei < len(row) else None
            if m is None and (mi >= len(row) or not row[mi].strip()) and require_nonempty: continue   # lightning: train/val rows interleave
            if e is None: skipped += 1; continue
            pairs.append((e, m if m is not None else float("nan")))
    return pairs, {"skipped": skipped}


def read_mmengine(path, metric, epoch):
    pairs, skipped, bad = [], 0, 0
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: o = json.loads(line)
            except ValueError: bad += 1; continue
            if not isinstance(o, dict) or o.get("mode") != "val": continue
            if metric not in o: continue
            e = _num(o.get(epoch))
            if e is None: skipped += 1; continue
            pairs.append((e, _num(o[metric]) if _num(o[metric]) is not None else float("nan")))
    if not pairs and not skipped:
        raise Fail(f"{path} 里没有 mode=val 且含 '{metric}' 的行（mmengine JSON-lines；检查 --metric-col 的写法，如 coco/bbox_mAP）")
    return pairs, {"skipped": skipped, "bad_lines": bad}


def read_tensorboard(path, metric, step_is_epoch):
    if not step_is_epoch:
        raise Fail("TensorBoard 的 step 常是 iteration，不是 epoch；确认 step 就是 epoch（每 epoch 记一次）后加 --step-is-epoch")
    try:
        from tensorboard.backend.event_processing import event_accumulator as ea
    except ImportError:
        raise Fail("读 tensorboard 日志需要 tensorboard 包：pip install tensorboard")
    acc = ea.EventAccumulator(path, size_guidance={ea.SCALARS: 0}); acc.Reload()
    tags = acc.Tags().get("scalars", [])
    if metric not in tags: raise Fail(f"标量 '{metric}' 不在 {path}；现有标量: {tags[:20]}")
    return [(float(e.step), float(e.value)) for e in acc.Scalars(metric)], {"skipped": 0}


def clean(pairs, info, notes):
    """drop NaN/inf, collapse duplicate epochs (last wins), list gaps; returns sorted [(epoch, value)]"""
    bad = [p for p in pairs if not math.isfinite(p[1])]
    if bad: notes.append(f"{len(bad)} 行 NaN/inf 已丢弃（epoch {sorted({p[0] for p in bad})[:8]}）")
    pairs = [p for p in pairs if math.isfinite(p[1])]
    last, dup = {}, set()
    for e, v in pairs:
        if e in last: dup.add(e)
        last[e] = v
    if dup: notes.append(f"{len(dup)} 个 epoch 重复（{sorted(dup)[:8]}），保留最后一条")
    if info.get("skipped"): notes.append(f"{info['skipped']} 行没有 epoch，已跳过并计数")
    if info.get("no_metric"): notes.append(f"{info['no_metric']} 条记录不含该指标（例如隔若干 epoch 才验证一次），已跳过")
    if info.get("bad_lines"): notes.append(f"{info['bad_lines']} 行不是合法 JSON，已跳过")
    es = sorted(last)
    if es and all(float(e).is_integer() for e in es):
        have = {int(e) for e in es}; miss = [e for e in range(min(have), max(have) + 1) if e not in have]
        if miss: notes.append(f"epoch 有缺口 {miss[:20]}{'…' if len(miss) > 20 else ''}（共缺 {len(miss)} 个）")
    return [(e, last[e]) for e in es]


def _fmt_epoch(e): return str(int(e)) if float(e).is_integer() else repr(e)


def adapt(a):
    if not a.units: raise Fail("单位必须显式给出：--units fraction（0–1 小数，会 ×100）、--units percent（已是百分数）或 --units none（loss / 计数等不是百分数的量，原样保留）；不替你猜")
    if not a.input or not os.path.exists(a.input): raise Fail(f"--input {a.input!r} 不存在")
    if not a.metric_col: raise Fail("--metric-col 必须给出（日志里的指标列名 / 标量标签）")
    ec = a.epoch_col or DEFAULT_EPOCH.get(a.adapter, "epoch")
    if a.adapter == "ultralytics" or a.adapter == "csv": pairs, info = read_table(a.input, a.metric_col, ec)
    elif a.adapter == "lightning": pairs, info = read_table(a.input, a.metric_col, ec, require_nonempty=True)
    elif a.adapter == "mmengine": pairs, info = read_mmengine(a.input, a.metric_col, ec)
    elif a.adapter == "json": pairs, info = read_json(a.input, a.metric_col, ec)
    else: pairs, info = read_tensorboard(a.input, a.metric_col, a.step_is_epoch)
    raw_eps = [p[0] for p in pairs] + ([info["epoch_min"]] if info.get("epoch_min") is not None else [])
    notes = []; ser = clean(pairs, info, notes)
    if not ser: raise Fail("没有读到任何有效 (epoch, 指标) 行")
    vals = [v for _, v in ser]
    if a.units == "fraction" and max(vals) > 1.5:
        raise Fail(f"声明 fraction 但最大值 {max(vals):g} > 1.5 —— 这像是百分数；确认单位后改 --units percent")
    if a.units == "percent" and len(vals) >= 5 and max(vals) <= 1.0:
        notes.append("全部 ≤ 1 但声明为 percent，确认不是小数")
    scale = 100.0 if a.units == "fraction" else 1.0
    base = _fmt_epoch(min(raw_eps))          # numbering base = smallest epoch in the log, not the first epoch that carries the metric
    sha = sha256_of(a.input); src = os.path.basename(a.input.rstrip("/\\")) if a.adapter != "tensorboard" else os.path.basename(a.input.rstrip("/\\"))
    extra = {}
    for kv in a.extra or []:
        if "=" not in kv or not kv.split("=", 1)[0].strip(): raise Fail(f"--extra 要 key=value，收到 {kv!r}")
        k, v = kv.split("=", 1); extra[k.strip()] = v
        if k.strip() in BASE_COLS: raise Fail(f"--extra 的 key '{k.strip()}' 与固定列重名")
    rows = [{"epoch": _fmt_epoch(e), "value": f"{round(v * scale, 10):g}", "method": a.method, "dataset": a.dataset, "seed": a.seed, "metric": a.metric_col,
             "units_in": a.units, "units_out": "none" if a.units == "none" else "percent", "source_file": src, "source_sha256": sha, "adapter": a.adapter, "epoch_base": base, **extra} for e, v in ser]
    return rows, notes, list(extra)


def write_out(a, rows, extra_cols):
    out = a.out; old, comments = [], []
    if a.append and os.path.exists(out):
        with open(out, encoding="utf-8-sig", newline="") as f:
            lines = f.read().splitlines()
        comments = [l for l in lines if l.startswith("#")]
        old = list(csv.DictReader([l for l in lines if not l.startswith("#")]))
    key = lambda r: (r.get("method"), r.get("dataset"), str(r.get("seed")), r.get("metric"))
    new_keys = {key(r) for r in rows}
    kept = [r for r in old if key(r) not in new_keys]
    if len(kept) < len(old): say("INFO", "append", f"{len(old) - len(kept)} 行同 method/dataset/seed/metric 的旧行被替换")
    cols = list(BASE_COLS)
    for r in kept + rows:
        for c in r:
            if c not in cols and c is not None: cols.append(c)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        for c in comments: f.write(c + "\n")
        if a.header_comment: f.write(f"# adapter={a.adapter}, input={a.input}, units_in={a.units}\n")
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader()
        for r in kept + rows: w.writerow({c: r.get(c, "") for c in cols})
    return len(kept) + len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", required=True, choices=["ultralytics", "mmengine", "lightning", "csv", "json", "tensorboard"])
    ap.add_argument("--input", required=True); ap.add_argument("--metric-col", default=""); ap.add_argument("--epoch-col", default="")
    ap.add_argument("--method", required=True); ap.add_argument("--dataset", default="")
    ap.add_argument("--units", default="", choices=["", "fraction", "percent", "none"], help="mandatory; never guessed. none = not a percentage (loss, counts): written unchanged")
    ap.add_argument("--out", required=True); ap.add_argument("--seed", default="0"); ap.add_argument("--append", action="store_true")
    ap.add_argument("--extra", nargs="*", default=[], help="extra constant columns, key=value")
    ap.add_argument("--step-is-epoch", action="store_true", help="tensorboard: accept the event step as the epoch")
    ap.add_argument("--header-comment", action="store_true", help="first line '# adapter=..., input=..., units_in=...' (make_figure.py cannot read it)")
    a = ap.parse_args(argv)
    global FAILS; FAILS = 0
    try:
        rows, notes, extra_cols = adapt(a)
    except Fail as e:
        say("FAIL", "adapt", str(e)); print(f"\n{FAILS} FAIL"); return FAILS
    for n in notes: say("WARN", "adapt", n)
    n = write_out(a, rows, extra_cols)
    say("PASS", "adapt", f"{a.adapter} {os.path.basename(a.input)}: {len(rows)} epoch ({rows[0]['epoch']}..{rows[-1]['epoch']}, epoch_base={rows[0]['epoch_base']}) "
        f"units {a.units} -> {'none' if a.units == 'none' else 'percent'} -> {a.out}（共 {n} 行）")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); return FAILS


if __name__ == "__main__":
    sys.exit(main())
