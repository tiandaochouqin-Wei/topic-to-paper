# -*- coding: utf-8 -*-
"""P1/P2 — mine what neighbouring papers compare against, and what they ablate.

  python baseline_miner.py <pdf_dir> <out_dir> [--min-papers 2]

For every PDF: find result tables (blocks after "Table N" captions containing ≥3 numeric cells), take the first cell of each
row as a method name, and collect the ablation rows ("w/o X", "without X", "− X", "no X", "- X"). Also scans prose for
"compared with/against X", "baselines include X". Names are normalised (case, punctuation, citation marks) and clustered by
token overlap so "ConvLSTM [12]" and "ConvLSTM" merge.

Outputs:
  baselines.csv   name, n_papers, papers, example_row     — methods ≥ min_papers neighbours compare against
  ablations.csv   component, n_papers, papers, example    — components neighbours ablate
  datasets.csv    dataset, n_papers                        — datasets named in table captions / prose
  metrics.csv     metric, n_papers
  baseline_report.md                                       — human-readable summary ranked by frequency

Use: the prereg §5 baseline table must cover every method in baselines.csv with n_papers ≥ 2, or state why not.
Calibrated on 13 nowcasting papers (2026-10-07): precision of the baselines list ≈ 0.8 after the stop-list; names that are
metrics/datasets/column headers are filtered by METRIC/DATASET/STOP tables below."""
import sys, os, re, io, csv, glob, collections, argparse
import fitz

METRIC = {"mse", "mae", "rmse", "csi", "pod", "far", "hss", "ets", "fss", "psnr", "ssim", "lpips", "fvd", "fid", "crps", "bias", "acc", "accuracy", "auc", "auroc", "f1", "dice", "iou", "miou", "map", "bleu", "nll", "ece", "brier", "mape", "r2", "corr", "spearman", "pearson", "precision", "recall", "top-1", "top-5", "flops", "params", "latency", "time", "memory", "throughput", "fps", "mean", "avg", "average", "std", "total", "overall"}
DATASET_HINT = re.compile(r"\b(SEVIR|HKO-?7|MeteoNet|Shanghai|MRMS|ERA5|WeatherBench|IMERG|CORRA|GPM|KITTI|COCO|ImageNet|CIFAR|MNIST|Moving ?MNIST|N-body|TaxiBJ|BAIR|KTH|Human3\.6M|UCF|Kinetics|nuScenes|Waymo|ADNI|BraTS|MIMIC|ChestX|TCGA|MICCAI|LIDC|OASIS|HCP|SST|OPERA|RRQPE|JMA|KNMI|DWD|NEXRAD|FY-?4|GOES|Himawari|Meteosat|ABI|AHI|AGRI|SEVIRI|FCI)\b", re.I)
STOP = {"method", "methods", "model", "models", "approach", "baseline", "baselines", "ours", "our", "proposed", "setting", "settings", "config", "configuration", "variant", "variants", "ablation", "component", "components", "dataset", "datasets", "metric", "metrics", "lead", "time", "step", "steps", "frame", "frames", "horizon", "threshold", "all", "none", "full", "default", "reference", "input", "output", "train", "test", "val", "validation", "n/a", "na", "-", "—", "–", "total", "and", "or", "the", "a", "of", "with", "w", "wo", "w/o", "without", "no", "not", "yes"}
ABL = re.compile(r"^\s*(?:w/o|w\.o\.|without|no|−|-|–|—|minus|remove[d]?|replace[d]?|only|\+|w/|with)\s+(.{2,60})$", re.I)
CITE = re.compile(r"\s*(?:\[\d+(?:[,–-]\s*\d+)*\]|\(\d{4}[a-z]?\)|\(\w[^)]{0,40}\d{4}\)|†|‡|\*|\^\d)")

def norm(s):
    s = CITE.sub("", s); s = re.sub(r"\s+", " ", s).strip(" .:;,|")
    return s

def key(s):
    k = re.sub(r"[^a-z0-9]+", "", s.lower())
    return k

def is_name(s):
    if not s or len(s) < 2 or len(s) > 60: return False
    low = s.lower()
    if low in STOP or low in METRIC: return False
    if re.fullmatch(r"[\d.,%±+\-−–— ]+", s): return False     # numeric
    if sum(c.isalpha() for c in s) < 2: return False
    if re.fullmatch(r"(?:\d+\s*(?:min|h|km|mm|dBZ|%)?)", s, re.I): return False
    return True

def text_of(pdf):
    d = fitz.open(pdf)
    return "\n".join(p.get_text() for p in d), d.page_count

def result_tables(text):
    """yield (caption, rows) for blocks after 'Table N' with ≥3 rows containing ≥2 numbers."""
    out = []
    for m in re.finditer(r"(?:^|\n)\s*(?:Table|TABLE)\s*(\d+)[.:|]?\s*([^\n]{0,200})", text):
        cap = m.group(2); seg = text[m.end():m.end() + 6000]
        lines = [l.strip() for l in seg.splitlines() if l.strip()]
        rows = []; cur = []
        for l in lines[:140]:
            if re.search(r"(?:^|\n)\s*(?:Table|Figure|Fig\.)\s*\d", l): break
            cur.append(l)
            if len(re.findall(r"-?\d+\.\d+", " ".join(cur))) >= 2 and len(cur) >= 2:
                rows.append(cur); cur = []
        if len(rows) >= 3: out.append((cap, rows))
    return out

def mine(pdf_dir, out_dir, min_papers):
    os.makedirs(out_dir, exist_ok=True)
    base = collections.defaultdict(set); base_ex = {}
    abl = collections.defaultdict(set); abl_ex = {}
    ds = collections.defaultdict(set); met = collections.defaultdict(set)
    canon = {}
    def add(d, ex, name, paper, example):
        k = key(name)
        if not k: return
        # cluster: longest common prefix ≥ 5 chars with an existing key
        for ck in list(canon):
            if k == ck or (len(k) >= 5 and (k.startswith(ck) or ck.startswith(k)) and abs(len(k) - len(ck)) <= 3):
                k = ck; break
        canon.setdefault(k, name)
        d[k].add(paper); ex.setdefault(k, example)
    for pdf in sorted(glob.glob(os.path.join(pdf_dir, "*.pdf"))):
        paper = os.path.splitext(os.path.basename(pdf))[0]
        try: text, n = text_of(pdf)
        except Exception: continue
        flat = re.sub(r"\s+", " ", text)
        for dm in DATASET_HINT.finditer(flat): ds[dm.group(1).upper()].add(paper)
        for mm in re.finditer(r"\b([A-Z]{2,6}(?:@\d+)?|PSNR|SSIM|LPIPS|CRPS)\b", flat):
            if mm.group(1).lower().rstrip("@0123456789") in METRIC: met[mm.group(1).upper()].add(paper)
        for cap, rows in result_tables(text):
            is_abl_table = bool(re.search(r"ablation|component|variant|w/o|without|effect of|impact of|importance of", cap, re.I))
            for r in rows:
                first = norm(r[0])
                am = ABL.match(first)
                if am or (is_abl_table and re.match(r"^\s*(?:w/o|without|−|-|no)", first, re.I)):
                    comp = norm(am.group(1)) if am else norm(re.sub(r"^\s*(?:w/o|without|−|-|no)\s*", "", first, flags=re.I))
                    if is_name(comp): add(abl, abl_ex, comp, paper, first)
                elif is_name(first) and not is_abl_table:
                    add(base, base_ex, first, paper, first)
        # PDF text layers emit one table cell per line: scan every short line for ablation-row syntax, independent of row grouping
        for l in text.splitlines():
            l = norm(l)
            if len(l) > 60: continue
            am = ABL.match(l)
            if am and re.match(r"^\s*(?:w/o|w\.o\.|without|−|–|—)", l, re.I):
                comp = norm(am.group(1))
                if is_name(comp) and len(comp.split()) <= 5: add(abl, abl_ex, comp, paper, l)
            # "Model w/o X" and "Model (no X)" inline variants
            for im in re.finditer(r"(?:w/o|without)\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})", l):
                comp = norm(im.group(1))
                if is_name(comp): add(abl, abl_ex, comp, paper, l)
        for pm in re.finditer(r"(?:compared? (?:with|against|to)|baselines? (?:include|are|:)|competitors? (?:include|are|:))\s+([A-Z][^.;]{3,160})", flat):
            for cand in re.split(r",|\band\b|;", pm.group(1)):
                c = norm(cand.strip())
                if is_name(c) and len(c.split()) <= 4 and c[0].isupper(): add(base, base_ex, c, paper, "prose: " + pm.group(0)[:80])
    def dump(fn, d, ex, label):
        rows = sorted(((canon[k], len(v), ";".join(sorted(v)), ex.get(k, "")) for k, v in d.items()), key=lambda r: (-r[1], r[0]))
        with open(os.path.join(out_dir, fn), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow([label, "n_papers", "papers", "example"]); w.writerows(rows)
        return rows
    b = dump("baselines.csv", base, base_ex, "name"); a = dump("ablations.csv", abl, abl_ex, "component")
    with open(os.path.join(out_dir, "datasets.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["dataset", "n_papers", "papers"]); w.writerows(sorted(((k, len(v), ";".join(sorted(v))) for k, v in ds.items()), key=lambda r: -r[1]))
    with open(os.path.join(out_dir, "metrics.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["metric", "n_papers", "papers"]); w.writerows(sorted(((k, len(v), ";".join(sorted(v))) for k, v in met.items()), key=lambda r: -r[1]))
    npap = len(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    L = [f"# 邻域论文的基线与消融（{npap} 篇，{os.path.basename(pdf_dir)}）", "",
         f"## 被 ≥{min_papers} 篇对比的方法（prereg §5 必须覆盖或说明为何不比）", "", "| 方法 | 篇数 | 论文 |", "|---|---|---|"]
    L += [f"| {r[0]} | {r[1]} | {r[2]} |" for r in b if r[1] >= min_papers]
    L += ["", "## 被 ≥1 篇消融的组件（设计 prereg §6 时对照）", "", "| 组件 | 篇数 | 写法示例 |", "|---|---|---|"]
    L += [f"| {r[0]} | {r[1]} | {r[3][:50]} |" for r in a[:40]]
    L += ["", "## 数据集 / 指标出现频次", "", "数据集: " + ", ".join(f"{k}({len(v)})" for k, v in sorted(ds.items(), key=lambda kv: -len(kv[1]))[:15]),
          "", "指标: " + ", ".join(f"{k}({len(v)})" for k, v in sorted(met.items(), key=lambda kv: -len(kv[1]))[:15])]
    io.open(os.path.join(out_dir, "baseline_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:60]))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("pdf_dir"); ap.add_argument("out_dir"); ap.add_argument("--min-papers", type=int, default=2)
    a = ap.parse_args(); mine(a.pdf_dir, a.out_dir, a.min_papers)
