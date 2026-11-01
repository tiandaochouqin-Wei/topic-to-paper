# -*- coding: utf-8 -*-
"""Project-wide figure style registry (P5): ONE place that decides what a method is called, which colour / line / marker it gets and which one is "ours".

Round-3 independent figure review (a real fusion paper): every generator chose names, colours and "ours" on its own and fell back to code names and default
palettes: ours was named four ways, the same method changed colour between Fig 6 and Fig 7, blue meant a dataset in one figure and a method in the next,
red meant both "ours" and false-positive boxes, labels were "chgate", "recv", "IRraw", "out0", "value". The registry lives in research-state.yaml:

  figures:
    style:
      ours: [relroute_l]                    # method keys that are "ours" (accent, heaviest line, first in legends)
      methods:                              # key = the name used in result files / run dirs / column names
        relroute_l: {label: "RelRoute (ours)", color: "#c94a5e", line: "-",  marker: "o"}
        smm:        {label: "SMM", color: "#4a4a4a", line: "--", marker: "s"}
        rgb:        {label: "RGB-only", color: "#7fa7c9", line: "(0, (1, 1))", marker: "v"}   # a dash tuple is written as a QUOTED string
      aliases: {"F6R +aug +L_rel": relroute_l, "ours": relroute_l}   # other spellings found in files -> key
      datasets: {m3fd: {label: "M3FD", marker: "o", fill: "full"}}   # datasets get marker / fill / panel, NEVER a hue
      roles: {gt: "#ffd23f", tp: "#2e9b57", fp: "#e08a00", fn: "#d9d9d9", ours_frame: "#1f1f1f", baseline_line: "#8a8a8a"}
      cmap: viridis                         # activation / heat maps (jet refused unless roles.allow_jet: true)
      stages: {fuse: "RelRoute fusion"}     # architecture figure stage names
      font_pt: 7                            # one size for all figure text roles

Python API (generators import it; pure, no matplotlib):
  import figure_style as fs
  st = fs.load(root)                        # Style; empty (no registry) when the file / section is missing, never raises
  st.key(name) -> str|None                  # exact key, alias, or case / space / underscore / hyphen-insensitive match of a key, alias or label
  st.label(name, strict=False) -> str       # registry label; unknown -> fs.humanise(name); strict=True: unknown or code-like -> StyleError
  st.color(name, i=None) / st.line(name, i=None) / st.marker(name, i=None) / st.linewidth(name)
                                            # registry value, else a deterministic fallback (i = position of the series when the caller has one, else a hash of
                                            # the name) from a colour-blind-safe palette that never equals the ours colour, a roles colour or a registered colour
  st.is_ours(name); st.ours_color; st.order(names); st.role("gt"|"tp"|"fp"|"fn"|"ours_frame"|"baseline_line"); st.cmap; st.allow_jet
  st.stage(raw); st.dataset(name) -> {label, marker, fill}; st.font_pt; st.columns(name, i=None) -> {label, color, line, marker} (the source.csv style columns)
  fs.looks_like_code(label) -> bool; fs.humanise(name); fs.colour_name(hex); fs.delta_e(h1, h2); fs.simulate(hex, "deut"|"prot"|"trit")

CLI (run by Claude):
  python figure_style.py init  [--project .]   scan results/*.csv, figures/*.source.csv, figures.csv and write a DRAFT figures.style block into
                                               research-state.yaml (only when absent; otherwise print the names not yet registered). Labels are humanised and
                                               marked `# TODO: author name`; colours come from a colour-blind-safe palette (deuteranopia / protanopia / tritanopia
                                               simulation, Machado 2009, CIELAB dE), ours = accent.
  python figure_style.py check [--project .] [--allow w1,w2]   FAIL: (i) a series / column / row label in figures/*.source.csv (label column) or a word in a figure
                                               PDF's text layer is code-like; (ii) one method has two colours or two labels across the source CSVs; (iii) a registry
                                               colour equals the ours colour for a non-ours method, or a roles colour gt / tp / fp / fn equals it; (iv) a dataset entry
                                               has a hue; (v) cmap jet without allow_jet. WARN: a source.csv without style columns (drawn before the registry),
                                               unconfirmed `TODO: author name` labels, near-identical colours. Exit code = number of FAIL lines.
  python figure_style.py show  [--project .]   the resolved table
"""
import argparse, ast, collections, csv, glob, io, json, math, os, re, sys, zlib
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

ACCENT = "#d1495b"                       # the ours colour when nothing is registered (= make_figure.ACCENT)
DEFAULT_ROLES = {"gt": "#ffd23f", "tp": "#2e9b57", "fp": "#e08a00", "fn": "#d9d9d9", "ours_frame": "#1f1f1f", "baseline_line": "#8a8a8a"}
ROLE_WORDS = {"gt": "ground truth", "tp": "true positive", "fp": "false positive", "fn": "missed ground truth", "ours_frame": "frame around our method", "baseline_line": "baseline"}
DEFAULT_CMAP = "viridis"
MARKS = ["o", "s", "^", "v", "D", "P", "X", "h"]
LINES = ["-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1))]
# colour-blind-safe categorical fallback (Okabe-Ito / Tol hues without red, orange, yellow and green, which the default roles and the accent use)
FALLBACK_POOL = ["#6a3d9a", "#003f5c", "#88CCEE", "#a0522d", "#AA4499", "#332288", "#555555", "#56B4E9", "#CC79A7", "#0072B2"]   # greedy max-min order under normal / deut / prot / trit vision, away from the accent and the default roles
METHOD_COLS = ("series", "method", "group", "model", "baseline", "variant", "item", "name", "key")
DATASET_COLS = ("dataset", "benchmark", "data")
SKIP_NAMES = {"gt", "groundtruth", "ground truth", "input", "image", "chance", "reference"}
TODO = "TODO: author name"


class StyleError(ValueError):
    pass


# ------------------------------------------------------------------ colour maths
def _hex(c):
    c = str(c).strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", c): c = "#" + "".join(ch * 2 for ch in c[1:])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", c): raise StyleError(f"not a hex colour: {c!r}")
    return c.lower()

def _rgb(h):
    h = _hex(h); return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

def _lin(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def _gam(c):
    c = min(1.0, max(0.0, c)); return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

_SIM = {   # Machado, Oliveira, Fernandes 2009, severity 1.0, applied to linear RGB
    "deut": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "prot": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "trit": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]}

def simulate(h, kind):
    """hex colour as seen with deuteranopia (deut), protanopia (prot) or tritanopia (trit); kind None = unchanged"""
    if kind is None: return _hex(h)
    lin = [_lin(c) for c in _rgb(h)]; M = _SIM[kind]
    out = [_gam(sum(M[r][c] * lin[c] for c in range(3))) for r in range(3)]
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in out)

def _lab(h):
    r, g, b = (_lin(c) for c in _rgb(h))
    X = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047; Y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b; Z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(X), f(Y), f(Z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)

def delta_e(h1, h2):
    """CIELAB colour difference (dE76); ~2.3 is a just-noticeable difference, >= 20 reads as clearly different"""
    a, b = _lab(h1), _lab(h2); return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

def min_separation(colors):
    """smallest pairwise dE over normal vision and the three simulated deficiencies -> (value, (kind, c1, c2))"""
    best = (1e9, None)
    for kind in (None, "deut", "prot", "trit"):
        sim = [simulate(c, kind) for c in colors]
        for i in range(len(sim)):
            for j in range(i + 1, len(sim)):
                d = delta_e(sim[i], sim[j])
                if d < best[0]: best = (d, (kind or "normal", colors[i], colors[j]))
    return best

def colour_name(h):
    """a plain English colour word for a hex colour (red, orange, yellow, green, teal, blue, purple, pink, brown, grey, light grey, dark grey, black, white)"""
    import colorsys
    r, g, b = _rgb(h); hh, s, v = colorsys.rgb_to_hsv(r, g, b); hd = hh * 360
    if v < 0.18: return "black"
    if s < 0.16: return "white" if v > 0.95 else ("light grey" if v > 0.78 else ("grey" if v > 0.4 else "dark grey"))
    if hd < 14 or hd >= 346: return "red" if v >= 0.45 else "dark red"
    if hd < 42: return "brown" if v < 0.62 else "orange"
    if hd < 68: return "yellow" if v >= 0.6 else "olive"
    if hd < 165: return "green"
    if hd < 200: return "teal"
    if hd < 262: return "blue"
    if hd < 300: return "purple"
    return "pink"

def line_word(ls):
    """matplotlib linestyle -> solid / dashed / dash-dotted / dotted"""
    if isinstance(ls, (tuple, list)):
        pat = ls[1] if len(ls) == 2 and isinstance(ls[1], (tuple, list)) else ls
        pat = [float(x) for x in pat] or [1.0]
        return "dotted" if max(pat) <= 2 else ("dash-dotted" if len(pat) >= 4 else "dashed")
    return {"-": "solid", "solid": "solid", "--": "dashed", "dashed": "dashed", "-.": "dash-dotted", "dashdot": "dash-dotted", ":": "dotted", "dotted": "dotted"}.get(str(ls), str(ls))

def _parse_line(v):
    if v is None or v == "": return None
    if isinstance(v, (list, tuple)): return (v[0], tuple(v[1])) if len(v) == 2 and isinstance(v[1], (list, tuple)) else tuple(v)
    s = str(v).strip()
    if s.startswith("("):
        try: return _parse_line(ast.literal_eval(s))
        except Exception: raise StyleError(f"line {v!r} is not a matplotlib dash tuple like (0, (1, 1))")
    return s

def line_text(ls):
    """linestyle as a source.csv / yaml cell"""
    return str(ls) if isinstance(ls, str) else str(tuple(ls))


# ------------------------------------------------------------------ labels that look like code
_MATH = re.compile(r"\$[^$]*\$")
_PLACEHOLDER = {"value", "values", "val", "y", "x"}
_FAMILY_LETTER = re.compile(r"\bF\d+[A-Z]\b")                                              # F6R
_FAMILY_WORD = re.compile(r"\bF\d+\b(?=\s+(?!(?:score|scores|measure|measures)\b)[A-Za-z+])")   # "F1 Add", "F2 Concat" (not "F1 score", "F1 (%)", "F1@0.5")
_OUT = re.compile(r"\bout\d+\b|\b(?:in|feat|layer|blk|fc|conv)\d+\b", re.I)
_PATH = re.compile(r"^[A-Za-z]:[\\/]|[\\/][\w.\- ]+[\\/]|\b[\w\-]+[\\/][\w\-]+[\\/][\w\-]+|\.(?:png|jpe?g|csv|json|pdf|npy|txt|ya?ml|pth?|ckpt|py|tex)\b", re.I)
_CAMEL_UP = re.compile(r"\b[A-Z]{2,}[a-z]{3,}\b")                                           # IRraw
_CAMEL_LOW = re.compile(r"\b[a-z]{3,}[A-Z][a-z]+")                                         # clsLoss
_LEGIT3 = {"str", "spr", "spl", "scr", "thr", "shr", "sch", "chr", "phr", "ght", "tch", "nch", "rch", "lch", "rth", "nth", "lth", "rst", "nst", "lst", "mpt", "mpl", "mpr",
           "nds", "ndr", "ndl", "lph", "thm", "ntr", "ntl", "ctr", "ngl", "ngr", "ngth", "mbl", "mbr", "xpl", "xpr", "xtr", "rtl", "rgl", "rld", "rnt", "nct", "nsf", "nsp", "nsm", "bst",
           "dst", "ndw", "dth", "pth", "xth", "ghth", "rtn", "rch", "rnl", "ntf", "ngt", "nks", "lms", "rms", "rts", "rds", "rns", "lls", "tls", "rst", "mps", "sts", "nsc"}
_BAD_V = re.compile(r"v[^aeiouy]|[bcdfghjkmnpqstwxz]v|j[^aeiouy]|q(?!u)")

def _odd_lower(t):
    """a lowercase token of 3-6 letters that cannot be an English word: no vowel, an unpronounceable consonant run (chg, ttn), or v next to a consonant (cv)"""
    w = t[:-1] if t.endswith("s") and len(t) > 3 else t
    if not re.search(r"[aeiouy]", w): return True
    for m in re.finditer(r"[^aeiouy]+", w):
        if len(m.group()) >= 3 and m.group() not in _LEGIT3: return True
    return bool(_BAD_V.search(w))

def looks_like_code(label, placeholders=True):
    """True when a figure label reads like a code name rather than something an author wrote: underscores (math excluded), family codes (F6R, "F1 Add"),
    out0 / feat3, path-like strings, camel / glued names (IRraw, clsLoss), lowercase abbreviations without a pronounceable shape (chgate, xattn, recv, rgb) and,
    when `placeholders` (an axis / series label, not a word of running text), a bare value / val / y / x. Legit labels pass: RGB-only, IR-only, SMM, Concat, AP (%),
    DINOv2, ResNet-50, F1 score, L$_\\mathrm{rel}$."""
    s = _MATH.sub(" ", str(label or "")).strip()
    if not s: return False
    if placeholders and s.lower() in _PLACEHOLDER: return True
    if "_" in s: return True
    if _FAMILY_LETTER.search(s) or _FAMILY_WORD.search(s) or _OUT.search(s) or _PATH.search(s) or _CAMEL_UP.search(s) or _CAMEL_LOW.search(s): return True
    return any(re.fullmatch(r"[a-z]{3,6}", t) and _odd_lower(t) for t in re.findall(r"[A-Za-z0-9]+", s))

_ACR = {"rgb": "RGB", "ir": "IR", "nir": "NIR", "fir": "FIR", "cnn": "CNN", "gan": "GAN", "mlp": "MLP", "nms": "NMS", "roc": "ROC", "auc": "AUC", "ap": "AP", "map": "mAP",
        "iou": "IoU", "psnr": "PSNR", "ssim": "SSIM", "fid": "FID", "ct": "CT", "mri": "MRI", "pet": "PET", "gt": "GT", "gpu": "GPU", "fps": "FPS", "ema": "EMA",
        "cam": "CAM", "tp": "TP", "fp": "FP", "fn": "FN", "gflops": "GFLOPs", "flops": "FLOPs", "hu": "HU", "snr": "SNR", "sd": "s.d.", "ci": "CI"}

def humanise(name):
    """a readable draft of a code name: snake_case -> words, known acronyms upper-cased, trailing unit suffix in parentheses (params_M -> Params (M)).
    It is a DRAFT: the author still has to confirm it (a humanised 'recv' is still not a name)."""
    s = str(name if name is not None else "").strip()
    if not s: return s
    m = re.fullmatch(r"(.+?)_([MKGB]|ms|s|pct|percent)", s)
    unit = ""
    if m and "_" not in m.group(1): s, unit = m.group(1), " (%s)" % ("%" if m.group(2) in ("pct", "percent") else m.group(2))
    s = re.sub(r"\s+", " ", s.replace("_", " ")).strip(); words = []
    for k, w in enumerate(s.split(" ")):
        lw = w.lower()
        if w == lw and lw in _ACR: words.append(_ACR[lw])
        elif w == lw and k == 0: words.append(w[:1].upper() + w[1:])
        else: words.append(w)
    return " ".join(words) + unit


# ------------------------------------------------------------------ the registry
def _norm(s): return re.sub(r"[\s_\-]+", "", str(s).lower())

class Style:
    def __init__(self, data=None, source=""):
        d = data if isinstance(data, dict) else {}
        self.raw = d; self.source = source; self.error = ""
        o = d.get("ours"); self.ours = [str(x) for x in (o if isinstance(o, (list, tuple)) else ([o] if o else []))]
        self.methods = collections.OrderedDict((str(k), (v if isinstance(v, dict) else {})) for k, v in (d.get("methods") or {}).items()) if isinstance(d.get("methods"), dict) else collections.OrderedDict()
        self.aliases = {str(k): str(v) for k, v in (d.get("aliases") or {}).items()} if isinstance(d.get("aliases"), dict) else {}
        self.datasets = collections.OrderedDict((str(k), (v if isinstance(v, dict) else {})) for k, v in (d.get("datasets") or {}).items()) if isinstance(d.get("datasets"), dict) else collections.OrderedDict()
        r = d.get("roles") if isinstance(d.get("roles"), dict) else {}
        self.allow_jet = bool(r.get("allow_jet") or d.get("allow_jet"))
        self._roles = {k: (r.get(k) or v) for k, v in DEFAULT_ROLES.items()}
        self.cmap = str(d.get("cmap") or DEFAULT_CMAP)
        self.stages = {str(k): str(v) for k, v in (d.get("stages") or {}).items()} if isinstance(d.get("stages"), dict) else {}
        try: self.font_pt = float(d.get("font_pt") or 7.0)
        except (TypeError, ValueError): self.font_pt = 7.0
        self._index = {}; self._pool = None
        for k in self.methods: self._index.setdefault(("exact", k), k)
        for a_, k in self.aliases.items(): self._index.setdefault(("exact", a_), k)
        for k in self.methods: self._index.setdefault(("norm", _norm(k)), k)
        for a_, k in self.aliases.items(): self._index.setdefault(("norm", _norm(a_)), k)
        for k, v in self.methods.items():
            if v.get("label"): self._index.setdefault(("norm", _norm(v["label"])), k)

    # ---- state
    def empty(self): return not (self.methods or self.ours or self.datasets)

    def key(self, name):
        if name is None: return None
        k = self._index.get(("exact", str(name))) or self._index.get(("norm", _norm(name)))
        return k if k in self.methods else None

    def is_ours(self, name):
        k = self.key(name)
        return bool(k is not None and k in self.ours) or (k is None and str(name) in self.ours)

    def _hash(self, name): return zlib.crc32(_norm(name).encode("utf-8"))

    # ---- colours
    @property
    def ours_color(self):
        for k in self.ours:
            c = self.methods.get(k, {}).get("color")
            if c: return _hex(c)
        return ACCENT

    def role(self, name):
        if name not in DEFAULT_ROLES: raise StyleError(f"unknown role {name!r}: use one of {sorted(DEFAULT_ROLES)}")
        return _hex(self._roles[name])

    def _fallback_pool(self):
        if self._pool is None:
            avoid = [self.ours_color] + [self.role(k) for k in DEFAULT_ROLES] + [_hex(v["color"]) for v in self.methods.values() if v.get("color")]
            pool = [c.lower() for c in FALLBACK_POOL if all(delta_e(c, a_) >= 14 for a_ in avoid)]
            self._pool = pool or [c.lower() for c in FALLBACK_POOL if c.lower() not in avoid] or [c.lower() for c in FALLBACK_POOL]
        return self._pool

    def _slot(self, name, i, n): return (i if i is not None else self._hash(name)) % n

    def color(self, name, i=None):
        k = self.key(name)
        if k is not None and self.methods[k].get("color"): return _hex(self.methods[k]["color"])
        if self.is_ours(name): return self.ours_color
        pool = self._fallback_pool(); return pool[self._slot(name, i, len(pool))]

    def line(self, name, i=None):
        k = self.key(name)
        if k is not None and _parse_line(self.methods[k].get("line")) is not None: return _parse_line(self.methods[k].get("line"))
        if self.is_ours(name): return "-"
        return LINES[self._slot(name, i, len(LINES) - 1) + 1]          # "-" stays reserved for ours

    def marker(self, name, i=None):
        k = self.key(name)
        if k is not None and self.methods[k].get("marker"): return str(self.methods[k]["marker"])
        if self.is_ours(name): return "o"
        return MARKS[1 + self._slot(name, i, len(MARKS) - 1)]

    def linewidth(self, name): return 1.8 if self.is_ours(name) else 1.0

    def columns(self, name, i=None):
        """the style columns every source.csv carries per series"""
        return {"label": self.label(name), "color": self.color(name, i), "line": line_text(self.line(name, i)), "marker": self.marker(name, i)}

    # ---- names
    def label(self, name, strict=False):
        k = self.key(name)
        if k is not None and self.methods[k].get("label"):
            lab = str(self.methods[k]["label"])
            if strict and looks_like_code(lab): raise StyleError(f"registered label {lab!r} of {name!r} looks like code: rename it in figures.style.methods.{k}.label")
            return lab
        if strict:
            raise StyleError(f"{name!r} is not registered" + (" and looks like code" if looks_like_code(name) else "") + ": register it with figure_style.py init (figures.style.methods)")
        return humanise(name)

    def order(self, names):
        names = list(names); rank = {k: n for n, k in enumerate(self.methods)}
        def sk(item):
            pos, nm = item; k = self.key(nm)
            if self.is_ours(nm): return (0, self.ours.index(k) if k in self.ours else 0, pos)
            if k in rank: return (1, rank[k], pos)
            return (2, 0, pos)
        return [nm for _, nm in sorted(enumerate(names), key=sk)]

    def stage(self, raw):
        if raw in self.stages: return self.stages[raw]
        for k, v in self.stages.items():
            if _norm(k) == _norm(raw): return v
        return humanise(raw)

    def dataset(self, name):
        key = next((k for k in self.datasets if k == name or _norm(k) == _norm(name) or _norm(self.datasets[k].get("label", "")) == _norm(name)), None)
        d = self.datasets.get(key, {}) if key is not None else {}
        n = list(self.datasets).index(key) if key is not None else self._hash(name)
        return {"label": str(d.get("label") or humanise(name)), "marker": str(d.get("marker") or MARKS[n % len(MARKS)]), "fill": str(d.get("fill") or ("full" if n % 2 == 0 else "none"))}

    # ---- validation (figure_style.py check)
    def validate(self):
        """[(severity, message)] for the registry itself"""
        out = []
        oc = self.ours_color
        for k, v in self.methods.items():
            c = v.get("color")
            if not c: continue
            try: c = _hex(c)
            except StyleError as e: out.append(("FAIL", f"methods.{k}.color: {e}")); continue
            if k not in self.ours and self.ours:
                if c == oc: out.append(("FAIL", f"methods.{k} has the ours colour {oc}: a baseline must not look like ours"))
                elif delta_e(c, oc) < 10: out.append(("WARN", f"methods.{k} colour {c} is nearly the ours colour {oc} (dE {delta_e(c, oc):.1f})"))
            for rk in ("gt", "tp", "fp", "fn"):
                if c == self.role(rk) and k not in self.ours: out.append(("WARN", f"methods.{k} colour {c} is also the {rk} role colour: the same colour must not mean a method and a box status"))
            lab = v.get("label")
            if lab and looks_like_code(lab): out.append(("FAIL", f"methods.{k}.label {lab!r} looks like a code name"))
            if not lab: out.append(("WARN", f"methods.{k} has no label: figures would show {humanise(k)!r}"))
        for k in self.ours:
            if k not in self.methods: out.append(("WARN", f"ours key {k!r} is not in methods"))
        for a_, k in self.aliases.items():
            if k not in self.methods: out.append(("WARN", f"alias {a_!r} points to {k!r}, which is not in methods"))
        for rk in ("gt", "fp", "fn", "tp"):
            try:
                if self.role(rk) == oc and self.ours: out.append(("FAIL", f"roles.{rk} equals the ours colour {oc}: red meant both 'ours' and false-positive boxes in the round-3 review"))
            except StyleError as e: out.append(("FAIL", f"roles.{rk}: {e}"))
        for k, v in self.datasets.items():
            bad = [h for h in ("color", "colour", "hue", "fill_color") if v.get(h)]
            if bad: out.append(("FAIL", f"datasets.{k} carries a hue ({bad[0]}={v[bad[0]]}): datasets are encoded by marker / fill / panel, never by colour (the hue belongs to methods)"))
            if v.get("label") and looks_like_code(v["label"]): out.append(("FAIL", f"datasets.{k}.label {v['label']!r} looks like a code name"))
        for k, v in self.stages.items():
            if looks_like_code(v): out.append(("FAIL", f"stages.{k} = {v!r} looks like a code name"))
        if self.cmap.lower().startswith(("jet", "rainbow", "gist_rainbow", "hsv")) and not self.allow_jet:
            out.append(("FAIL", f"cmap {self.cmap!r} is a rainbow map (not perceptually uniform, unreadable in grayscale): use viridis, or set roles.allow_jet: true with a reason"))
        labs = collections.defaultdict(list)
        for k, v in self.methods.items():
            if v.get("label"): labs[_norm(v["label"])].append(k)
        for lab, ks in labs.items():
            if len(ks) > 1: out.append(("WARN", f"methods {ks} share the label {lab!r}"))
        return out


def load(root=".", state_file="research-state.yaml"):
    """Style from <root>/research-state.yaml figures.style; `root` may also be a yaml path or an already-loaded dict. Empty Style when the file or the section is missing."""
    try:
        if isinstance(root, dict): d = root
        else:
            p = root if str(root).lower().endswith((".yaml", ".yml")) else os.path.join(str(root), state_file)
            if not os.path.isfile(p): return Style(None, "")
            import yaml
            d = yaml.safe_load(io.open(p, encoding="utf-8-sig")) or {}
        sec = (d.get("figures") or {}).get("style") if isinstance(d.get("figures"), dict) else None
        if sec is None and "figures" not in d and any(k in d for k in ("methods", "ours", "datasets", "roles")): sec = d       # a bare style dict
        return Style(sec if isinstance(sec, dict) else None, "" if isinstance(root, dict) else str(root))
    except Exception as e:                                                                  # never raises: a broken yaml is the gates' job to report
        st = Style(None, str(root)); st.error = str(e); return st


# ------------------------------------------------------------------ CLI helpers
FAILS = 0; WARNS = 0

def say(sev, msg):
    global FAILS, WARNS
    if sev == "FAIL": FAILS += 1
    elif sev == "WARN": WARNS += 1
    print(f"[{sev}] {msg}")

def _read_csv(p):
    try:
        with io.open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
    except Exception: return []

def _slug(s):
    s = re.sub(r"[^0-9a-z]+", "_", str(s).lower()).strip("_")
    return s or "m"

def _is_number(s):
    try: float(s); return True
    except Exception: return False

def source_csvs(root):
    paths = {}
    def add(p): paths.setdefault(os.path.normcase(os.path.abspath(p)), os.path.abspath(p))
    for p in glob.glob(os.path.join(root, "figures", "**", "*.source.csv"), recursive=True): add(p)
    for r in _read_csv(os.path.join(root, "figures.csv")):
        for k in ("source_data", "source"):
            v = (r.get(k) or "").strip().replace("\\", "/")
            if v.lower().endswith(".csv") and os.path.isfile(os.path.join(root, v)): add(os.path.join(root, v))
    return sorted(paths.values())

def scan_names(root):
    """-> (methods {name: first file}, datasets {name: first file})"""
    meth, dsets = collections.OrderedDict(), collections.OrderedDict()
    files = sorted(glob.glob(os.path.join(root, "results", "*.csv"))) + source_csvs(root)
    for p in files:
        rows = _read_csv(p); rel = os.path.relpath(p, root).replace("\\", "/")
        if not rows: continue
        hdr = {h.lower(): h for h in rows[0].keys() if h}
        is_src = rel.endswith(".source.csv")
        mcols = [hdr[c] for c in METHOD_COLS if c in hdr] + ([hdr["label"]] if is_src and "label" in hdr and "id" not in hdr else [])
        for c in mcols[:2]:
            for v in dict.fromkeys((r.get(c) or "").strip() for r in rows):
                if v and not _is_number(v) and v.lower() not in SKIP_NAMES and len(v) < 60: meth.setdefault(v, rel)
        for c in [hdr[c] for c in DATASET_COLS if c in hdr][:1]:
            for v in dict.fromkeys((r.get(c) or "").strip() for r in rows):
                if v and not _is_number(v): dsets.setdefault(v, rel)
    return meth, dsets

def _draft_palette(n, ours_color, role_colors):
    """n colours greedily chosen from a candidate pool to maximise the smallest separation under normal vision and deuteranopia / protanopia / tritanopia, away from ours and the roles"""
    cands = [c.lower() for c in FALLBACK_POOL]
    chosen = []; fixed = [ours_color] + list(role_colors)
    def sep(c, others): return min([delta_e(simulate(c, k), simulate(o, k)) for k in (None, "deut", "prot", "trit") for o in others] or [99.0])
    for _ in range(n):
        best, bs = None, -1.0
        for c in cands:
            if c in chosen: continue
            s = sep(c, fixed + chosen)
            if s > bs: best, bs = c, s
        if best is None: break
        chosen.append(best)
    return chosen

def build_block(meth, dsets):
    """the DRAFT `style:` block (text, 4-space indented under figures:)"""
    keys = collections.OrderedDict(); aliases = {}
    for name in meth:
        k = _slug(name)
        if k in keys: aliases[name] = k; continue
        keys[k] = name
    ours = [k for k, nm in keys.items() if re.fullmatch(r"(?:ours?|proposed|our method)", nm.strip().lower()) or "(ours)" in nm.lower() or nm.strip().lower().endswith(" ours")]
    base = [k for k in keys if k not in ours]
    pal = _draft_palette(len(base), ACCENT, DEFAULT_ROLES.values())
    L = ["  style:   # DRAFT written by figure_style.py init: confirm every label (TODO), pick `ours`, then every generator reads it",
         "    ours: [%s]%s" % (", ".join(ours), "" if ours else "   # TODO: author name the method key(s) that are ours"),
         "    methods:"]
    bi = 0
    for k, nm in keys.items():
        if k in ours: col, ln, mk = ACCENT, "-", "o"
        else: col = pal[bi % len(pal)] if pal else "#777777"; ln = LINES[1 + bi % (len(LINES) - 1)]; mk = MARKS[1 + bi % (len(MARKS) - 1)]; bi += 1
        L.append('      %s: {label: "%s", color: "%s", line: "%s", marker: "%s"}   # %s' % (k, humanise(nm).replace('"', "'"), col, line_text(ln), mk, TODO))
    if bi > len(pal) and pal: L.append(f"      # WARN: {bi} baselines but only {len(pal)} distinguishable colours: the rest repeat a colour (lines / markers still differ)")
    L.append("    aliases: {%s}" % ", ".join('"%s": %s' % (a_.replace('"', "'"), k) for a_, k in aliases.items()))
    L.append("    datasets:   # marker / fill / panel, never a hue")
    for n, nm in enumerate(dsets):
        L.append('      %s: {label: "%s", marker: "%s", fill: "%s"}   # %s' % (_slug(nm), humanise(nm), MARKS[n % len(MARKS)], "full" if n % 2 == 0 else "none", TODO))
    L.append("    roles: {%s}" % ", ".join('%s: "%s"' % kv for kv in DEFAULT_ROLES.items()))
    L.append("    cmap: viridis")
    L.append("    stages: {}   # architecture stage names, e.g. {fuse: \"Fusion\"}")
    L.append("    font_pt: 7")
    return "\n".join(L), keys, ours

def cmd_init(a):
    root = os.path.abspath(a.project); sp = os.path.join(root, "research-state.yaml")
    meth, dsets = scan_names(root)
    st = load(root)
    if not st.empty() and not a.force:
        reg = {_norm(k) for k in st.methods} | {_norm(x) for x in st.aliases} | {_norm(v.get("label", "")) for v in st.methods.values()}
        new = [(n, f) for n, f in meth.items() if _norm(n) not in reg and _norm(_slug(n)) not in reg]
        newd = [(n, f) for n, f in dsets.items() if not any(_norm(n) in (_norm(k), _norm(v.get("label", ""))) for k, v in st.datasets.items())]
        say("INFO", f"figures.style exists ({len(st.methods)} methods, {len(st.datasets)} datasets); init writes a block only when it is absent (--force to replace)")
        for n, f in new: say("WARN", f"method name not registered: {n!r} (seen in {f}) -> add methods.{_slug(n)} or an alias")
        for n, f in newd: say("WARN", f"dataset not registered: {n!r} (seen in {f})")
        if not new and not newd: say("PASS", "every method / dataset name found in results/ and figures/ is registered")
        return FAILS
    if not meth and not dsets: say("WARN", "no method / dataset names found in results/*.csv or figures/*.source.csv: the block lists nothing to confirm")
    block, keys, ours = build_block(meth, dsets)
    pal_warn = [ln for ln in block.split("\n") if "# WARN:" in ln]
    if not os.path.isfile(sp):
        say("FAIL", f"{sp} not found: run t2p.py init first, or print the block below and paste it under `figures:`"); print("figures:\n" + block); return FAILS
    raw = io.open(sp, encoding="utf-8-sig", newline="").read(); nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl); out = None
    if a.force and not st.empty():
        say("FAIL", "--force with an existing figures.style would drop comments and other keys: delete the block by hand, then run init"); return FAILS
    for i, ln in enumerate(lines):
        if re.match(r"^figures:\s*(#.*)?$", ln):
            out = nl.join(lines[:i + 1] + block.split("\n") + lines[i + 1:]); break
        if re.match(r"^figures:\s*[^\s#]", ln): out = None; break
    else:
        out = raw.rstrip("\r\n") + nl + nl + "figures:" + nl + block.replace("\n", nl) + nl
    if out is None:
        say("FAIL", "figures: in research-state.yaml is an inline mapping; paste this under it by hand:"); print(block); return FAILS
    io.open(sp, "w", encoding="utf-8", newline="").write(out)
    say("PASS", f"figures.style DRAFT written to research-state.yaml: {len(keys)} methods ({len(ours)} marked ours), {len(dsets)} datasets")
    for ln in pal_warn: say("WARN", ln.strip("# ").replace("WARN: ", ""))
    chk = load(root)
    for s, m in chk.validate():
        if s == "FAIL" and ".label" in m and "code name" in m: say("WARN", m + " (a draft: rename it, check FAILs until you do)")
        elif s == "FAIL": say("FAIL", m)
    d, who = min_separation([chk.color(k) for k in chk.methods]) if len(chk.methods) > 1 else (99.0, None)
    say("INFO" if d >= 10 else "WARN", f"smallest colour separation over normal / deuteranopia / protanopia / tritanopia vision: dE {d:.1f}" + (f" ({who[0]}: {who[1]} vs {who[2]})" if who and d < 10 else ""))
    say("WARN", f"{len(keys)} labels end in `# {TODO}`: confirm or rename them (check keeps warning until the comments are gone), and set `ours`" if not ours else f"{len(keys)} labels end in `# {TODO}`: confirm or rename them")
    return FAILS


def _name_col(hdr):
    for c in METHOD_COLS:
        if c in hdr: return hdr[c]
    return hdr.get("label") if "id" not in hdr else None

def _pdf_words(path):
    try: import fitz
    except Exception: return None, None
    words, lines = [], []
    try:
        with fitz.open(path) as doc:
            for pg in doc:
                words += [w[4] for w in pg.get_text("words")]
                lines += [" ".join(b[4].split()) for b in pg.get_text("blocks") if len(b) > 4 and isinstance(b[4], str)]
    except Exception: return None, None
    return words, lines

def run_check(root, allow=(), verbose=True):
    """-> (n_fail, n_warn) and prints the PASS / WARN / FAIL lines. `root` = project directory."""
    global FAILS, WARNS
    FAILS = WARNS = 0
    root = os.path.abspath(root); st = load(root)
    allow = {str(x).lower() for x in allow} | {str(x).lower() for x in (st.raw.get("allow_code") or [])}
    srcs = source_csvs(root); pdfs = [p for p in sorted(glob.glob(os.path.join(root, "figures", "**", "*.pdf"), recursive=True))]
    if st.error: say("WARN", f"research-state.yaml could not be read for figures.style: {st.error}")
    if st.empty():
        say("WARN" if (srcs or pdfs) else "INFO", "no figure style registry (figures.style): " + ("figures exist; run figure_style.py init" if (srcs or pdfs) else "no figures yet"))
    else:
        v = st.validate()
        for sev, msg in v: say(sev, msg)
        if not any(s == "FAIL" for s, _ in v): say("PASS", f"registry: {len(st.methods)} methods ({len(st.ours)} ours), {len(st.datasets)} datasets, cmap {st.cmap}")
        try:
            todo = len(re.findall(re.escape(TODO), io.open(os.path.join(root, "research-state.yaml"), encoding="utf-8-sig").read()))
            if todo: say("WARN", f"{todo} registry entries still carry `# {TODO}`: the author has not confirmed the draft labels")
        except OSError: pass
        if not st.ours: say("WARN", "figures.style.ours is empty: every series is drawn with equal weight")
    # ---- source CSVs: (i) code-like labels, (ii) one method one colour / label, WARN without style columns
    seen = collections.defaultdict(lambda: {"label": collections.defaultdict(set), "color": collections.defaultdict(set)})
    n_nostyle = 0; bad_labels = collections.defaultdict(set)
    for p in srcs:
        rows = _read_csv(p); rel = os.path.relpath(p, root).replace("\\", "/")
        if not rows: continue
        hdr = {h.lower(): h for h in rows[0].keys() if h}
        has_style = any(c in hdr for c in ("color", "line", "marker")); nc = _name_col(hdr)
        if not has_style: n_nostyle += 1; say("WARN", f"{rel}: no style columns (label / color / line / marker): drawn before the registry; regenerate it")
        cols = [hdr[c] for c in ("label",) + METHOD_COLS + DATASET_COLS if c in hdr]
        for c in dict.fromkeys(cols):
            for val in dict.fromkeys((r.get(c) or "").strip() for r in rows):
                if not val or _is_number(val) or val.lower() in allow or val.lower() in SKIP_NAMES: continue
                if looks_like_code(val):
                    registered = st.key(val) is not None or any(_norm(val) in (_norm(k), _norm(v.get("label", ""))) for k, v in st.datasets.items())
                    lab_col = c.lower() == "label" and has_style
                    if lab_col or not registered: bad_labels[(rel, lab_col)].add(val)
        if nc and has_style:
            for r in rows:
                nm = (r.get(nc) or "").strip()
                if not nm: continue
                k = st.key(nm) or _norm(nm)
                if "label" in hdr and (r.get(hdr["label"]) or "").strip(): seen[k]["label"][(r.get(hdr["label"]) or "").strip()].add(rel)
                if "color" in hdr and (r.get(hdr["color"]) or "").strip(): seen[k]["color"][(r.get(hdr["color"]) or "").strip().lower()].add(rel)
    for (rel, lab_col), vals in sorted(bad_labels.items()):
        sev = "FAIL" if lab_col else "WARN"
        say(sev, f"{rel}: code-like label(s) {sorted(vals)[:6]}" + ("" if lab_col else " (file has no style columns, so what was drawn is unknown)") + ": name them in figures.style.methods (figure_style.py init) and regenerate")
    for k, d in seen.items():
        for what in ("label", "color"):
            if len(d[what]) > 1:
                say("FAIL", f"method {k!r} has {len(d[what])} different {what}s across the source CSVs: " + "; ".join(f"{v} ({', '.join(sorted(f)[:2])})" for v, f in sorted(d[what].items())) + " -> one method, one " + what)
    if srcs and not n_nostyle and not bad_labels and not any(len(d[w]) > 1 for d in seen.values() for w in ("label", "color")):
        say("PASS", f"{len(srcs)} source CSVs: every series carries style columns, no code-like labels, one label and colour per method")
    # ---- (i) text layer of the figure PDFs
    nfig = 0; bad_pdf = {}
    for p in pdfs:
        if p.endswith("_gray.pdf"): continue
        words, lines = _pdf_words(p)
        if words is None: continue
        nfig += 1
        bad = sorted({w.strip(".,;:()[]") for w in words if w.strip(".,;:()[]").lower() not in allow and looks_like_code(w.strip(".,;:()[]"), placeholders=False)})
        bad += sorted({ln for ln in lines if ln.lower() in _PLACEHOLDER and ln.lower() not in allow})
        if bad: bad_pdf[os.path.relpath(p, root).replace("\\", "/")] = bad
    for rel, bad in bad_pdf.items(): say("FAIL", f"{rel}: code-like text in the figure ({bad[:8]}): the reader sees a variable name, not a label")
    if nfig and not bad_pdf: say("PASS", f"{nfig} figure PDFs: no code-like words in the text layer")
    if verbose: print(f"figure style: {FAILS} FAIL, {WARNS} WARN")
    return FAILS, WARNS

def cmd_show(a):
    st = load(os.path.abspath(a.project))
    if st.empty(): print("[INFO] no figures.style registry"); return 0
    print(f"ours: {st.ours}  ours_color: {st.ours_color}  cmap: {st.cmap}  font_pt: {st.font_pt:g}")
    for k in st.methods: print(f"{k:<16} {st.label(k):<32} {st.color(k)}  {line_text(st.line(k)):<10} {st.marker(k)}" + ("  (ours)" if st.is_ours(k) else ""))
    for k in st.datasets: print(f"dataset {k:<10} {st.dataset(k)}")
    return 0

def main():
    ap = argparse.ArgumentParser(description="project-wide figure style registry: init (draft the figures.style block), check (labels / colours / roles / cmap), show")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="write a DRAFT figures.style block (only when absent; else list names not yet registered)"); i.add_argument("--project", default="."); i.add_argument("--force", action="store_true")
    c = sub.add_parser("check", help="FAIL on code-like labels, inconsistent method styles, colour collisions, hue-coded datasets, jet"); c.add_argument("--project", default="."); c.add_argument("--allow", default="", help="comma-separated words that may look like code")
    s = sub.add_parser("show", help="print the resolved registry"); s.add_argument("--project", default=".")
    a = ap.parse_args()
    if a.cmd == "init": sys.exit(min(cmd_init(a), 255))
    if a.cmd == "show": sys.exit(cmd_show(a))
    f, _w = run_check(a.project, [x for x in a.allow.split(",") if x]); sys.exit(min(f, 255))

if __name__ == "__main__":
    main()
