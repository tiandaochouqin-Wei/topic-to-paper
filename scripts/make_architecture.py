# -*- coding: utf-8 -*-
"""P5 — method-overview (architecture) figure traced from the model that produced the results, plus a check that keeps it honest. Run by Claude.

The Fig-3 kind of figure (stages left to right, modules as boxes, glue ops, repeated blocks, tensor shapes) is normally drawn by
hand and drifts away from the code. Here the graph is TRACED: forward hooks on every named module plus a TorchFunctionMode
that records the functional glue (add / cat / mul / interpolate / sigmoid / softmax / matmul / flatten / permute / chunk / pooling),
joined by tensor identity. The author may move or merge nodes in the .tex, but never invent one; `check` re-traces and compares.

  python make_architecture.py trace  --model code/model.py:DualYOLO [--init "nc=6,fusion='smm'"] --input "rgb:1x3x640x640,ir:1x3x640x640"
                                     [--depth 2] [--device cpu] [--sample rgb=figures/src/rgb.png,ir=...] [--stages "Backbone=^backbone,Neck=^neck"]
                                     [--label-names] [--dump-activations fuse.p4,neck.c2] --out figures/arch/model.yaml [--project .]
      --model file.py:Class (relative to the project; state.audits.code_dirs and the file's folder go on sys.path) or pkg.module:callable
      (torchvision.models:resnet18). --input name:shape[:dtype] items (dtype float32 default; ids:1x16:long). The model runs in eval(), no_grad,
      on zeros (or --sample images). --depth d: a module is a node when it is called at call-stack depth d, or shallower and a leaf (ModuleList
      containers that are never called do not count as a level); everything inside a node is collapsed, so a residual add inside a collapsed block is
      hidden while an add in the model's own forward is glue and drawn. Same class + same shapes in a chain -> one node "x n" (repeat).
      stage = first part of the dotted name (or --stages "Stage=regex,..." / bare "name" = prefix). Writes the yaml (meta, nodes, edges, activations).
      --dump-activations: channel-mean of those modules' output as figures/arch/act_<module>.png (viridis, square pixels) — insets for the
      make_motivation.py schematic / a Fig-1 "existing vs ours" composite (this script does not touch make_motivation.py).

  python make_architecture.py render --spec figures/arch/model.yaml --out figures/fig_arch.pdf [--engine tikz|dot] [--rankdir LR]
                                     [--hide BatchNorm2d,ReLU,Identity,Dropout,output:out1.feats_0] [--merge "backbone.*=Backbone"] [--images "input:rgb=figures/src/rgb.png,output:out0=figures/src/det.png"]
                                     [--width-mm 178] [--font-pt 7] [--show-params] [--shapes edge|node|none] [--project .]
      Layout = graphviz dot (clusters per stage, LR). --engine tikz (default when pdflatex is on PATH): dot -Tplain coordinates -> a standalone .tex
      (kept next to the .pdf for hand polishing: move / merge, never add) compiled with pdflatex; --engine dot: dot -Tpdf scaled to --width-mm.
      --hide removes node classes (or exact node ids) and re-routes their edges; --merge "regex=Label" (repeatable, or ';' separated) collapses a whole subtree into one box;
      edges carry the shape (C x H x W, batch dropped) only where it changes (--shapes node puts it under the node label instead: about 40 % narrower; none drops it); ops are circles with glyphs (+ x . cat up down).
      Writes <out>, <out>.source.csv (one row per drawn node), <out>.png (200 dpi preview), <out>.render.json (what `check` compares), the .tex (tikz),
      and registers the PDF in figures.csv (print width = measured page width, inspected=no -> look at it, then yes). The page is built at
      --font-pt and scaled down only if the graph is wider than --width-mm; the printed font size is reported (G5 FAILs below target.min_font_pt).

  python make_architecture.py check  [--project .] [--spec figures/arch/model.yaml] [--figure figures/fig_arch.pdf] [--tex figures/fig_arch.tex] [--allow "Detect Head,FPN"]
      (1) re-trace with the stored meta: code unchanged -> PASS; else the node multiset (class + shapes + repeat) must be identical, otherwise FAIL (drawn from an old
      model); (2) every word in the PDF / .tex is a node label, class, stage, shape, op glyph, repeat, number or --allow entry, else WARN (hand-added module?);
      (3) the params total printed with --show-params equals meta.params_total (FAIL if not); (4) every stage name of the figure appears in the Method section of
      paper/manuscript.md (WARN); (5) the input resolution equals the reference run's img_size/input_size (WARN).
      Exit = number of [FAIL] lines. G5 of t2p.py runs this for every figures/arch/*.yaml.

Why: 82 % of CVPR and 89 % of CS-journal papers carry a method-overview figure (references/figure-norms.md); the three real drafts of this skill had none, and the one
concept figure (cvpr2027_medical Fig 1 b/c) was a cartoon not derived from the model. A figure traced from the model cannot show a module that does not exist."""
import argparse, ast, collections, contextlib, csv, datetime, glob, hashlib, importlib, importlib.util, io, json, os, re, shlex, shutil, subprocess, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

# palette: hex values copied from make_motivation.COLORS (not imported, so this script does not need matplotlib)
COLORS = {"rgb": "#e8833a", "x": "#2f6eb5", "shared": "#9aa0a6", "ours": "#d1495b", "good": "#2e9b57", "bad": "#c0392b",
          "neutral": "#4a4a4a", "light": "#f2f2f2"}
STAGE_KEYS = ["x", "good", "shared", "rgb"]   # never the red accent: it means "ours" elsewhere in the skill figures
FAILS = 0


def say(st, gate, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {gate}: {msg}")


def die(gate, msg):
    say("FAIL", gate, msg); sys.exit(1)


def rel(p, root): return os.path.relpath(p, root).replace("\\", "/")


def load_state(root):
    p = os.path.join(root, "research-state.yaml")
    if not os.path.exists(p): return {}
    try:
        import yaml
        return yaml.safe_load(io.open(p, encoding="utf-8")) or {}
    except Exception:
        return {}


# ============================================================================================ tracing
# glue ops that are drawn when they happen outside every node: python names (underscores stripped) -> (op, glyph)
_OPS = {}
for _names, _op, _g in [
    (("add", "iadd", "radd"), "add", "⊕"), (("sub", "isub", "rsub"), "sub", "⊖"), (("mul", "imul", "rmul"), "mul", "⊗"),
    (("div", "truediv", "itruediv", "rtruediv", "true_divide"), "div", "⊘"),
    (("cat", "concat", "concatenate"), "cat", "cat"), (("stack",), "stack", "stack"),
    (("interpolate", "upsample"), "interpolate", "↑"), (("sigmoid",), "sigmoid", "⊙"), (("softmax",), "softmax", "softmax"),
    (("matmul", "bmm", "mm", "einsum"), "matmul", "matmul"), (("flatten",), "flatten", "flatten"),
    (("permute", "transpose"), "permute", "permute"), (("chunk", "split", "tensor_split"), "chunk", "chunk"),
    (("max_pool1d", "max_pool2d", "max_pool3d", "avg_pool1d", "avg_pool2d", "avg_pool3d", "adaptive_avg_pool1d", "adaptive_avg_pool2d",
      "adaptive_avg_pool3d", "adaptive_max_pool2d"), "pool", "↓")]:
    for _n in _names: _OPS[_n] = (_op, _g)
ARITH = {"add", "sub", "mul", "div"}   # a binary op needs two tensor operands that come from the graph, else it is scalar scaling (not drawn)
DOTGLYPH = {"⊕": "+", "⊖": "−", "⊗": "×", "⊘": "÷", "⊙": "σ"}   # Times has no circled operators; the circle around the node supplies the ⊕ look in the dot engine
GLYPH = {"add": "⊕", "sub": "⊖", "mul": "⊗", "div": "⊘", "cat": "cat", "stack": "stack", "interpolate": "↑", "sigmoid": "⊙", "softmax": "softmax",
         "matmul": "matmul", "flatten": "flatten", "permute": "permute", "chunk": "chunk", "pool": "↓"}
TEXGLYPH = {"⊕": r"$\oplus$", "⊖": r"$\ominus$", "⊗": r"$\otimes$", "⊘": r"$\oslash$", "⊙": r"$\odot$", "↑": r"$\uparrow$", "↓": r"$\downarrow$"}


def parse_init(s):
    if not s: return {}
    try:
        call = ast.parse(f"_({s})", mode="eval").body
        return {k.arg: ast.literal_eval(k.value) for k in call.keywords}
    except Exception as e:
        die("trace", f"--init 解析失败（写成 \"a=1,b='x'\"）: {e}")


def parse_inputs(s):
    out = []
    for i, it in enumerate([x for x in s.split(",") if x.strip()]):
        parts = it.strip().split(":")
        if len(parts) == 1 or re.fullmatch(r"\d+(x\d+)*", parts[0]):
            name, shp, dt = ("input" if i == 0 else f"input{i}"), parts[0], (parts[1] if len(parts) > 1 else "float32")
        else:
            name, shp, dt = parts[0], parts[1], (parts[2] if len(parts) > 2 else "float32")
        try: shape = [int(v) for v in shp.split("x")]
        except ValueError: die("trace", f"--input 形状 {shp!r} 解析失败（写成 1x3x640x640）")
        out.append({"name": name, "shape": shape, "dtype": dt})
    if not out: die("trace", "--input 不能为空")
    return out


def sha_file(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_model(spec, init, root, state):
    """-> (model, code_sha256). file.py:Class (relative to project) or pkg.module:callable"""
    left, _, right = spec.rpartition(":")
    if not left or not right: die("trace", f"--model {spec!r}: 写成 code/model.py:Class 或 pkg.module:callable")
    fpath = left if os.path.isabs(left) else os.path.join(root, left)
    if left.endswith(".py") or os.path.isfile(fpath):
        if not os.path.isfile(fpath): die("trace", f"{left} 不存在")
        fdir = os.path.dirname(os.path.abspath(fpath))
        extra = [os.path.join(root, d) for d in ((state.get("audits") or {}).get("code_dirs") or [])]
        for d in reversed([fdir, root] + extra):
            if d not in sys.path: sys.path.insert(0, d)
        name = "_t2p_arch_" + re.sub(r"\W", "_", os.path.splitext(os.path.basename(fpath))[0])
        sp = importlib.util.spec_from_file_location(name, fpath)
        mod = importlib.util.module_from_spec(sp); sys.modules[name] = mod
        try: sp.loader.exec_module(mod)
        except Exception as e: die("trace", f"导入 {left} 失败: {type(e).__name__}: {e}")
        sha = sha_file(fpath)
    else:
        try: mod = importlib.import_module(left)
        except Exception as e: die("trace", f"导入 {left} 失败: {type(e).__name__}: {e}")
        top = importlib.import_module(left.split(".")[0])
        sha = f"pkg:{left.split('.')[0]}=={getattr(top, '__version__', '?')}"
    fn = getattr(mod, right, None)
    if fn is None: die("trace", f"{left} 里没有 {right}")
    import torch
    torch.manual_seed(0)
    try: model = fn(**init)
    except Exception as e: die("trace", f"构造 {right}(**{init}) 失败: {type(e).__name__}: {e}")
    if not isinstance(model, torch.nn.Module): die("trace", f"{right}(...) 返回的不是 nn.Module: {type(model).__name__}")
    return model, sha


class Rec:
    def __init__(self):
        self.events = []; self.stack = []; self.live = {}; self.paused = 0; self.n = 0; self.nuid = 0; self.keep = []; self.calls = collections.Counter(); self.acts = {}

    def uid(self, t):
        u = getattr(t, "_t2p_uid", None)
        if u is None:
            self.nuid += 1; u = self.nuid
            try: t._t2p_uid = u
            except Exception: u = -id(t); self.keep.append(t)
        return u


def tensors_of(o, path="", depth=0):
    import torch
    if isinstance(o, torch.Tensor): yield path, o
    elif depth < 5 and isinstance(o, (list, tuple)):
        for i, v in enumerate(o): yield from tensors_of(v, f"{path}{i}" if not path else f"{path}_{i}", depth + 1)
    elif depth < 5 and isinstance(o, dict):
        for k, v in o.items(): yield from tensors_of(v, f"{path}.{k}" if path else str(k), depth + 1)


def run_traced(model, inputs, dump, device):
    """one eval forward pass with hooks -> (Rec, output_leaves[(name, uid, shape)], input uids)"""
    import torch
    from torch.overrides import TorchFunctionMode
    rec = Rec()

    class Mode(TorchFunctionMode):
        def __torch_function__(self, func, types, args=(), kwargs=None):
            kwargs = kwargs or {}
            out = func(*args, **kwargs)
            if rec.paused: return out
            outs = list(tensors_of(out))
            if not outs: return out
            ins = [t for _, t in tensors_of(list(args))] + [t for _, t in tensors_of(list(kwargs.values()))]
            nm = getattr(func, "__name__", "") or ""
            rec.n += 1
            rec.events.append({"kind": "op", "start": rec.n, "end": rec.n, "fn": nm.strip("_"), "stack": tuple(rec.stack),
                               "in": [rec.uid(t) for t in ins], "in_shapes": [tuple(t.shape) for t in ins],
                               "out": [rec.uid(t) for _, t in outs], "out_shapes": [tuple(t.shape) for _, t in outs]})
            return out

    dumps = set(dump or [])

    def pre(name):
        def h(mod, args, kwargs):
            rec.paused += 1
            try:
                ins = [t for _, t in tensors_of(list(args))] + [t for _, t in tensors_of(list(kwargs.values()))]
                rec.n += 1
                k = rec.calls[name]; rec.calls[name] += 1
                ev = {"kind": "module", "id": rec.n, "name": name, "cls": type(mod).__name__, "k": k, "start": rec.n, "depth": len(rec.stack),
                      "parent": rec.stack[-1] if rec.stack else None, "stack": tuple(rec.stack),
                      "in": [rec.uid(t) for t in ins], "in_shapes": [tuple(t.shape) for t in ins],
                      "params": sum(p.numel() for p in mod.parameters())}
                rec.events.append(ev); rec.live[ev["id"]] = ev; rec.stack.append(ev["id"])
            finally: rec.paused -= 1
        return h

    def post(name):
        def h(mod, args, kwargs, output):
            rec.paused += 1
            try:
                ev = rec.live[rec.stack[-1]]
                outs = list(tensors_of(output))
                ev["out"] = [rec.uid(t) for _, t in outs]; ev["out_shapes"] = [tuple(t.shape) for _, t in outs]
                rec.n += 1; ev["end"] = rec.n; rec.stack.pop()
                if name in dumps and name not in rec.acts and outs:
                    rec.acts[name] = outs[0][1].detach().float().cpu().clone()
            finally: rec.paused -= 1
        return h

    handles = []
    for name, m in model.named_modules():
        handles.append(m.register_forward_pre_hook(pre(name), with_kwargs=True))
        handles.append(m.register_forward_hook(post(name), with_kwargs=True))
    in_uids = []
    try:
        with torch.no_grad(), Mode():
            rec.paused += 1
            for t in inputs: in_uids.append(rec.uid(t))
            rec.paused -= 1
            result = model(*inputs)
        rec.paused += 1
        leaves = [(p or "out", rec.uid(t), tuple(t.shape)) for p, t in tensors_of(result)]
        rec.paused -= 1
    finally:
        for h in handles: h.remove()
    if not isinstance(result, dict): leaves = [("out" + p if p != "out" else p, u, s) for p, u, s in leaves]
    return rec, leaves, in_uids


def fmt_shape(s, drop_batch=True):
    s = list(s)
    if drop_batch and len(s) >= 2: s = s[1:]
    return "×".join(str(v) for v in s)


def stage_of(name, rules):
    if rules:
        for st, rx in rules:
            if re.search(rx, name): return st
    return name.split(".")[0] if name else ""


def parse_stages(s):
    out = []
    for it in [x for x in (s or "").split(",") if x.strip()]:
        if "=" in it: st, rx = it.split("=", 1)
        else: st, rx = it, "^" + re.escape(it)
        out.append((st.strip(), rx.strip()))
    return out


def build_graph(rec, leaves, in_uids, inputs, depth, rules, label_names, model_cls):
    mods = {e["id"]: e for e in rec.events if e["kind"] == "module"}
    nch = collections.Counter(e["parent"] for e in mods.values() if e["parent"] is not None)
    node_cache = {}

    def is_node(e):
        i = e["id"]
        if i not in node_cache:
            d = e["depth"]
            node_cache[i] = (d == depth or (d < depth and nch[i] == 0)) if d >= 1 else nch[i] == 0
        return node_cache[i]

    def inside_node(e): return any(is_node(mods[a]) for a in e["stack"])

    nodes = []; edges = []; prod = {}; opn = collections.Counter()
    for spec_in, u in zip(inputs, in_uids):
        nid = f"input:{spec_in['name']}"
        nodes.append({"id": nid, "label": spec_in["name"], "kind": "input", "cls": "input", "shape_in": [], "shape_out": [spec_in["shape"]],
                      "params": 0, "stage": "", "order": -1})
        prod[u] = nid
    seen = set()

    def link(e, nid, uids, shapes):
        for u, sh in zip(uids, shapes):
            src = prod.get(u)
            if src is None or src == nid or (src, nid, u) in seen: continue
            seen.add((src, nid, u)); edges.append({"from": src, "to": nid, "shape": list(sh), "label": ""})

    for e in sorted(rec.events, key=lambda e: e["end"]):
        if e["kind"] == "module":
            if not is_node(e) or inside_node(e): continue
            nm = e["name"]
            nid = (nm or model_cls) if e["k"] == 0 else f"{nm}#{e['k']}"
            n = {"id": nid, "label": (nm or model_cls) if label_names else e["cls"], "kind": "module", "cls": e["cls"],
                 "shape_in": [list(s) for s in e["in_shapes"]], "shape_out": [list(s) for s in e["out_shapes"]],
                 "params": e["params"], "stage": stage_of(nm, rules), "order": e["start"], "_parent": e["parent"]}
            nodes.append(n); link(e, nid, e["in"], e["in_shapes"])
            for u in e["out"]: prod[u] = nid
        else:
            if inside_node(e): continue
            op = _OPS.get(e["fn"])
            if op is not None:
                if op[0] in ARITH and len({u for u in e["in"] if prod.get(u) is not None}) < 2: op = None
            if op is None:   # transparent: the result inherits the producer of the first tensor operand that has one
                src = next((prod[u] for u in e["in"] if prod.get(u) is not None), None)
                for u in e["out"]:
                    if src is not None: prod[u] = src
                    elif u in prod and u not in e["in"]: del prod[u]
                continue
            scope = mods[e["stack"][-1]]["name"] if e["stack"] else ""
            k = opn[(scope, op[0])]; opn[(scope, op[0])] += 1
            nid = f"{scope}/{op[0]}#{k}"
            nodes.append({"id": nid, "label": op[0], "kind": "op", "cls": op[0], "shape_in": [list(s) for s in e["in_shapes"]],
                          "shape_out": [list(s) for s in e["out_shapes"]], "params": 0, "stage": stage_of(scope, rules) if scope else "",
                          "order": e["start"]})
            link(e, nid, e["in"], e["in_shapes"])
            for u in e["out"]: prod[u] = nid
    for i, (nm, u, sh) in enumerate(leaves):
        nid = f"output:{nm}"
        nodes.append({"id": nid, "label": nm, "kind": "output", "cls": "output", "shape_in": [list(sh)], "shape_out": [], "params": 0, "stage": "", "order": 10 ** 9 + i})
        src = prod.get(u)
        if src is not None: edges.append({"from": src, "to": nid, "shape": list(sh), "label": ""})
    nodes, edges = collapse_repeats(nodes, edges)
    for n in nodes: n.pop("_parent", None)
    label_edges(nodes, edges)
    nodes.sort(key=lambda n: n["order"])
    return nodes, edges


def collapse_repeats(nodes, edges):
    """consecutive sibling modules (same parent call, class, shapes) chained one after the other -> one node with repeat n"""
    byid = {n["id"]: n for n in nodes}
    outs = collections.defaultdict(list); ins = collections.defaultdict(list)
    for e in edges: outs[e["from"]].append(e); ins[e["to"]].append(e)
    sig = lambda n: (n["kind"], n["cls"], json.dumps(n["shape_in"]), json.dumps(n["shape_out"]), n.get("_parent"))

    def nxt(n):
        if n["kind"] != "module" or not outs[n["id"]]: return None
        tgt = {e["to"] for e in outs[n["id"]]}
        if len(tgt) != 1: return None
        b = byid[next(iter(tgt))]
        if b["kind"] != "module" or sig(b) != sig(n) or {e["from"] for e in ins[b["id"]]} != {n["id"]}: return None
        return b
    removed = set(); order = sorted([n for n in nodes if n["kind"] == "module"], key=lambda n: n["order"])
    for a in order:
        if a["id"] in removed or any(e["to"] == a["id"] and nxt(byid[e["from"]]) is a for e in ins[a["id"]]): continue   # only chain heads
        run = [a]
        while True:
            b = nxt(run[-1])
            if b is None or b["id"] in removed: break
            run.append(b)
        if len(run) < 2: continue
        a["repeat"] = len(run); a["params"] = sum(r["params"] for r in run)
        for r in run[1:]: removed.add(r["id"])
        last = run[-1]
        for e in outs[last["id"]]: e["from"] = a["id"]
    keep_e = [e for e in edges if e["from"] not in removed and e["to"] not in removed]
    return [n for n in nodes if n["id"] not in removed], keep_e


def label_edges(nodes, edges):
    """edge label = the shape, only where it changes: the producer has no input, or its first input has another shape"""
    first_in = {}
    for e in edges: first_in.setdefault(e["to"], e["shape"])
    kind = {n["id"]: n["kind"] for n in nodes}
    for e in edges:
        p = e["from"]
        e["label"] = fmt_shape(e["shape"]) if (kind.get(p) == "input" or p not in first_in or first_in[p] != e["shape"]) else ""


def load_image(path, shape, device):
    import numpy as np, torch
    from PIL import Image
    c, h, w = shape[-3], shape[-2], shape[-1]
    im = Image.open(path).convert("L" if c == 1 else "RGB").resize((w, h))
    a = np.asarray(im, dtype="float32") / 255.0
    a = a[None] if c == 1 else a.transpose(2, 0, 1)
    if c not in (1, 3): a = np.repeat(a[:1], c, 0)
    t = torch.from_numpy(a.copy())[None].repeat(shape[0], 1, 1, 1)
    return t.to(device)


def do_trace(model_spec, init_s, input_s, depth, device, sample_s, stages_s, label_names, root, state, dump=None):
    import torch
    init = parse_init(init_s); ins = parse_inputs(input_s)
    model, sha = load_model(model_spec, init, root, state)
    model.eval().to(device)
    samples = dict(kv.split("=", 1) for kv in (sample_s or "").split(",") if "=" in kv)
    tens = []
    for it in ins:
        if it["name"] in samples and len(it["shape"]) == 4:
            tens.append(load_image(os.path.join(root, samples[it["name"]]), it["shape"], device))
        else:
            dt = getattr(torch, it["dtype"], None)
            if dt is None: die("trace", f"未知 dtype {it['dtype']}")
            tens.append(torch.zeros(*it["shape"], dtype=dt, device=device))
    try: rec, leaves, in_uids = run_traced(model, tens, dump, device)
    except SystemExit: raise
    except Exception as e: die("trace", f"前向失败: {type(e).__name__}: {e}")
    for d in (dump or []):
        if d not in rec.acts: die("trace", f"--dump-activations {d}: 该模块不存在或前向里没被调用（可用的名字例：{', '.join(n for n, _ in list(model.named_modules())[1:6])}）")
    nodes, edges = build_graph(rec, leaves, in_uids, ins, depth, parse_stages(stages_s), label_names, type(model).__name__)
    spec = {"meta": {"model": model_spec, "init": init_s or "", "input": input_s, "depth": depth, "device": device, "torch": str(torch.__version__),
                     "date": datetime.date.today().isoformat(), "code_sha256": sha, "params_total": sum(p.numel() for p in model.parameters()),
                     "label_names": bool(label_names), "stages": stages_s or "", "sample": sample_s or ""},
            "nodes": nodes, "edges": edges}
    return spec, rec.acts


def write_yaml(spec, path):
    import yaml
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        "# traced by make_architecture.py trace — regenerate, do not hand-edit (edit the .tex after render instead)\n" +
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, default_flow_style=None, width=140))


def read_yaml(path):
    import yaml
    return yaml.safe_load(io.open(path, encoding="utf-8")) or {}


def stages_in_order(nodes):
    seen = []
    for n in sorted(nodes, key=lambda n: n["order"]):
        if n["stage"] and n["stage"] not in seen: seen.append(n["stage"])
    return seen


def save_act(t, path):
    import numpy as np
    a = t[0] if t.ndim >= 3 else t
    a = a.mean(0) if a.ndim == 3 else a
    if a.ndim != 2: return False
    a = a.numpy(); lo, hi = float(a.min()), float(a.max())
    a = (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)
    import matplotlib; matplotlib.use("Agg")
    from matplotlib import colormaps
    from PIL import Image
    rgb = (colormaps["viridis"](a)[..., :3] * 255).astype("uint8")
    f = max(1, int(round(128 / max(1, min(rgb.shape[:2])))))
    im = Image.fromarray(rgb)
    if f > 1: im = im.resize((rgb.shape[1] * f, rgb.shape[0] * f), Image.NEAREST)
    im.save(path)
    return True


def cmd_trace(a):
    root = os.path.abspath(a.project); state = load_state(root)
    try: import torch
    except ImportError: die("trace", "需要 torch（pip install torch）")
    dump = [x for x in a.dump_activations.split(",") if x.strip()] if a.dump_activations else []
    spec, acts = do_trace(a.model, a.init, a.input, a.depth, a.device, a.sample, a.stages, a.label_names, root, state, dump)
    out = os.path.join(root, a.out)
    if dump:
        spec["activations"] = []
        for d in dump:
            f = os.path.join(os.path.dirname(out), f"act_{d}.png")
            if save_act(acts[d], f): spec["activations"].append({"module": d, "file": rel(f, root), "shape": list(acts[d].shape)})
            else: say("WARN", "trace", f"{d} 的输出不是空间特征图（{tuple(acts[d].shape)}），没有激活图")
    write_yaml(spec, out)
    n, e = spec["nodes"], spec["edges"]; st = stages_in_order(n); mods = [x for x in n if x["kind"] == "module"]
    say("PASS", "trace", f"{len(n)} 节点（{len(mods)} 模块 / {sum(1 for x in n if x['kind'] == 'op')} 运算 / {sum(1 for x in n if x['kind'] in ('input', 'output'))} 输入输出）、{len(e)} 边、{len(st)} 阶段、{spec['meta']['params_total']:,} 参数 → {rel(out, root)}")
    print("stages: " + (" → ".join(st) if st else "（无）"))
    if len(mods) <= 1 and a.depth == 1: say("WARN", "trace", "深度 1 只有一个模块节点（模型把整个前向交给了子模块）：加大 --depth")
    for x in n:
        if x["kind"] == "input" and not any(y["from"] == x["id"] for y in e): say("WARN", "trace", f"输入 {x['label']} 没有任何消费者（前向里没用到，或被不可追踪的运算吞掉）")
    for x in n:
        if x["kind"] == "output" and not any(y["to"] == x["id"] for y in e): say("WARN", "trace", f"输出 {x['label']} 找不到来源节点")
    sys.exit(FAILS)


# ============================================================================================ render
def tint(hexc, f):
    h = hexc.lstrip("#"); c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(int(round(255 - (255 - v) * f)) for v in c)


def apply_hide(nodes, edges, hide):
    hide = {h.strip().lower() for h in hide if h.strip()}
    if not hide: return nodes, edges
    gone = {n["id"] for n in nodes if n["cls"].lower() in hide or n["label"].lower() in hide or n["id"].lower() in hide}   # class, label or exact node id (output:out1.feats_0)
    cur = [dict(e) for e in edges]
    for g in gone:
        ins = [e for e in cur if e["to"] == g]; outs = [e for e in cur if e["from"] == g]
        cur = [e for e in cur if e["to"] != g and e["from"] != g]
        have = {(e["from"], e["to"]) for e in cur}
        for i in ins:
            for o in outs:
                if i["from"] != o["to"] and (i["from"], o["to"]) not in have:
                    cur.append({"from": i["from"], "to": o["to"], "shape": o["shape"], "label": ""}); have.add((i["from"], o["to"]))
    keep = [n for n in nodes if n["id"] not in gone]
    label_edges(keep, cur)
    return keep, cur


def apply_merge(nodes, edges, rules):
    labels = []
    for rx, lab in rules:
        try: r = re.compile(rx)
        except re.error as ex: die("render", f"--merge 正则 {rx!r} 无效: {ex}")
        grp = [n for n in nodes if n["kind"] in ("module", "op") and r.match(n["id"])]
        if not grp: say("WARN", "render", f"--merge {rx!r} 没有匹配任何节点"); continue
        ids = {n["id"] for n in grp}; first = min(grp, key=lambda n: n["order"]); nid = f"merged:{lab}"
        ein = [e for e in edges if e["to"] in ids and e["from"] not in ids]; eout = [e for e in edges if e["from"] in ids and e["to"] not in ids]
        shp = lambda es: [s for i, s in enumerate([e["shape"] for e in es]) if s not in [e["shape"] for e in es][:i]]
        m = {"id": nid, "label": lab, "kind": "module", "cls": "(merged)", "shape_in": shp(ein), "shape_out": shp(eout), "params": sum(n["params"] for n in grp),
             "stage": first["stage"], "order": first["order"]}
        edges = [e for e in edges if e["to"] not in ids and e["from"] not in ids]
        seen = set()
        for e in ein:
            if (e["from"], nid) not in seen: seen.add((e["from"], nid)); edges.append({"from": e["from"], "to": nid, "shape": e["shape"], "label": ""})
        for e in eout:
            if (nid, e["to"]) not in seen: seen.add((nid, e["to"])); edges.append({"from": nid, "to": e["to"], "shape": e["shape"], "label": ""})
        nodes = [n for n in nodes if n["id"] not in ids] + [m]; labels.append(lab)
    label_edges(nodes, edges)
    return nodes, edges, labels


def human(n):
    for u, d in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= d: return f"{n / d:.1f}{u}"
    return str(n)


class Style:
    def __init__(self, font): self.font = font; self.cw = 0.5 * font; self.pad = 5.0; self.show_params = False; self.shapes = "edge"


def node_text(n, st):
    if n["kind"] == "op": return [GLYPH.get(n["cls"], n["label"])]
    l1 = n["label"] + (f" ×{n['repeat']}" if n.get("repeat", 1) > 1 else "")
    out = [l1]
    if st.shapes == "node" and n["kind"] in ("module", "input") and n["shape_out"]:
        out.append(fmt_shape(n["shape_out"][0]) + (" …" if len(n["shape_out"]) > 1 else ""))
    if st.show_params and n["kind"] == "module" and n["params"]: out.append(human(n["params"]))
    return out


def node_dims(n, st, img):
    f = st.font
    if n["kind"] == "op":
        g = GLYPH.get(n["cls"], n["label"])
        if len(g) <= 3: d = max(1.9 * f, st.cw * len(g) + 0.9 * f); return d, d
        return st.cw * len(g) + 1.2 * f, 1.7 * f
    lines = node_text(n, st)
    w = max(st.cw * len(l) for l in lines) + 2 * 3.2; h = len(lines) * f * 1.22 + 2 * 2.6
    if img: iw, ih = img["w"], img["h"]; return max(w, iw + 2), h + ih + 2
    return w, h


_TEXESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
           "^": r"\textasciicircum{}", "×": r"\texttimes{}"}


def esc_tex(s):
    return re.sub(r"[\\&%$#_{}~^×]", lambda m: _TEXESC[m.group(0)], s)


def dot_cmd():
    return shutil.which("dot")


def layout(nodes, edges, st, rankdir, imgs, mode, size_in=None, pdf_out=None, params_note=None):
    """build the dot source; mode 'plain' -> dict of positions in pt, 'pdf' -> writes pdf_out"""
    idx = {n["id"]: i for i, n in enumerate(nodes)}; ft = st.font
    stages = stages_in_order(nodes)
    members = collections.defaultdict(list)
    for n in nodes:
        if n["stage"] and n["kind"] in ("module", "op"): members[n["stage"]].append(n)
    framed = [s for s in stages if len(members[s]) >= 2]
    colr = {s: COLORS[STAGE_KEYS[i % len(STAGE_KEYS)]] for i, s in enumerate(stages)}
    L = ["digraph G {", f'rankdir={rankdir}; nodesep=0.1; ranksep=0.13; newrank=true; margin=0; pad=0.02;',
         f'node [fontname="Times-Roman", fontsize={ft:g}, color="#444444", penwidth=0.6];',
         f'edge [fontname="Times-Roman", fontsize={ft * 0.85:g}, color="#555555", penwidth=0.6, arrowsize=0.5{", arrowhead=none" if mode == "plain" else ""}];']
    if size_in and mode == "pdf": L.append(f'size="{size_in[0]:.4f},{size_in[1]:.4f}!";')
    if params_note and mode == "pdf": L.append(f'label="{params_note}"; labelloc=b; labeljust=l; fontsize={ft * 0.9:g};')

    def nodedef(n):
        w, h = node_dims(n, st, imgs.get(n["id"])); i = idx[n["id"]]
        base = f'n{i} [fixedsize=true, width={w / 72:.4f}, height={h / 72:.4f}'
        txt = "\\n".join(DOTGLYPH.get(l, l).replace('"', "'") for l in node_text(n, st))
        if n["kind"] == "op":
            circ = len(GLYPH.get(n["cls"], n["label"])) <= 3
            return f'{base}, shape={"circle" if circ else "box"}, label="{txt}", fillcolor="white", style="{"filled" if circ else "rounded,filled"}"];'
        fill = tint(colr.get(n["stage"], COLORS["light"]), 0.16) if n["kind"] == "module" else COLORS["light"]
        im = imgs.get(n["id"])
        if im and mode == "pdf":
            p = im["path"].replace("\\", "/")
            lab = (f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0"><TR><TD FIXEDSIZE="TRUE" WIDTH="{im["w"]:.1f}" HEIGHT="{im["h"]:.1f}">'
                   f'<IMG SRC="{p}" SCALE="TRUE"/></TD></TR><TR><TD>{txt}</TD></TR></TABLE>>')
            return f'{base}, shape=box, margin=0, color="#444444", style="rounded", label={lab}];'
        return f'{base}, shape=box, style="rounded,filled", fillcolor="{fill}", label="{txt}"];'
    done = set()
    for s in framed:
        L.append(f'subgraph cluster_{stages.index(s)} {{ label="{s}"; labeljust=l; labelloc=t; fontsize={ft:g}; fontname="Times-Bold"; style="rounded"; color="{tint(colr[s], 0.6)}"; margin=9; penwidth=0.6;')
        for n in members[s]: L.append("  " + nodedef(n)); done.add(n["id"])
        L.append("}")
    for n in nodes:
        if n["id"] not in done: L.append(nodedef(n))
    for e in edges:
        lab = f' [label="{e["label"]}"]' if e["label"] else ""
        L.append(f'n{idx[e["from"]]} -> n{idx[e["to"]]}{lab};')
    L.append("}")
    src = "\n".join(L)
    dot = dot_cmd()
    if not dot: die("render", "PATH 上没有 graphviz 的 dot（安装 graphviz）")
    if mode == "pdf":
        r = subprocess.run([dot, "-Tpdf", "-o", pdf_out], input=src.encode("utf-8"), capture_output=True)
        if r.returncode != 0: die("render", "dot -Tpdf 失败: " + r.stderr.decode("utf-8", "replace").strip()[:300])
        return None, src
    r = subprocess.run([dot, "-Tplain"], input=src.encode("utf-8"), capture_output=True)
    if r.returncode != 0: die("render", "dot -Tplain 失败: " + r.stderr.decode("utf-8", "replace").strip()[:300])
    pos = {}; epl = []; W = Hh = 0
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        t = shlex.split(line)
        if not t: continue
        if t[0] == "graph": W, Hh = float(t[2]) * 72, float(t[3]) * 72
        elif t[0] == "node": pos[int(t[1][1:])] = (float(t[2]) * 72, float(t[3]) * 72, float(t[4]) * 72, float(t[5]) * 72)
        elif t[0] == "edge":
            k = int(t[3]); pts = [(float(t[4 + 2 * j]) * 72, float(t[5 + 2 * j]) * 72) for j in range(k)]
            rest = t[4 + 2 * k:]; lp = (float(rest[1]) * 72, float(rest[2]) * 72, rest[0]) if len(rest) >= 5 else None
            epl.append((int(t[1][1:]), int(t[2][1:]), pts, lp))
    return {"pos": pos, "edges": epl, "W": W, "H": Hh, "framed": framed, "members": members, "colr": colr, "stages": stages, "src": src}, src


def tex_source(nodes, edges, L, st, s, imgs, img_rel, show_params, total_params, spec_sha, prefer_times):
    f = st.font * s; fe = f * 0.85; idx = {n["id"]: i for i, n in enumerate(nodes)}
    P = lambda v: f"{v * s:.2f}"
    o = [f"% t2p-arch: generated by make_architecture.py render; spec_sha256={spec_sha}",
         "% hand polish: move or merge nodes here, never add a module — `make_architecture.py check` compares the words in this file with the trace.",
         r"\documentclass[tikz,border=1pt]{standalone}", r"\usepackage[T1]{fontenc}"]
    if prefer_times: o.append(r"\usepackage{mathptmx}")
    o += [r"\usepackage{graphicx}", r"\usetikzlibrary{arrows.meta}"]
    for i, stg in enumerate(L["stages"]):
        o.append(f"\\definecolor{{st{i}}}{{HTML}}{{{tint(L['colr'][stg], 0.16)[1:].upper()}}}")
        o.append(f"\\definecolor{{sb{i}}}{{HTML}}{{{tint(L['colr'][stg], 0.6)[1:].upper()}}}")
    o += [f"\\definecolor{{lightgrey}}{{HTML}}{{{COLORS['light'][1:].upper()}}}", r"\definecolor{ink}{HTML}{444444}", r"\definecolor{edgegrey}{HTML}{555555}",
          r"\begin{document}", r"\begin{tikzpicture}[x=1pt,y=1pt,line width=%.2fpt,>={Latex[length=%.2fpt,width=%.2fpt]},"
          % (0.5 * s, 3.2 * s, 2.4 * s)]
    o += [f"  box/.style={{draw=ink,rounded corners={1.8 * s:.2f}pt,inner sep={1.2 * s:.2f}pt,align=center,font=\\fontsize{{{f:.2f}}}{{{f * 1.2:.2f}}}\\selectfont}},",
          f"  opn/.style={{draw=ink,fill=white,circle,inner sep={0.3 * s:.2f}pt,align=center,font=\\fontsize{{{f:.2f}}}{{{f * 1.2:.2f}}}\\selectfont}},",
          f"  opb/.style={{draw=ink,fill=white,rounded corners={1.8 * s:.2f}pt,inner sep={1.0 * s:.2f}pt,align=center,font=\\fontsize{{{f:.2f}}}{{{f * 1.2:.2f}}}\\selectfont}},",
          f"  elab/.style={{inner sep={0.4 * s:.2f}pt,fill=white,fill opacity=0.85,text opacity=1,font=\\fontsize{{{fe:.2f}}}{{{fe * 1.2:.2f}}}\\selectfont}},",
          f"  stt/.style={{anchor=north west,inner sep={1.5 * s:.2f}pt,font=\\fontsize{{{f:.2f}}}{{{f * 1.2:.2f}}}\\bfseries\\selectfont}},",
          f"  edg/.style={{->,draw=edgegrey,line width={0.5 * s:.2f}pt}}]"]
    pos = L["pos"]; pad = 5.0
    for stg in L["framed"]:
        ms = [pos[idx[n["id"]]] for n in L["members"][stg]]
        x0 = min(p[0] - p[2] / 2 for p in ms) - pad; x1 = max(p[0] + p[2] / 2 for p in ms) + pad
        y0 = min(p[1] - p[3] / 2 for p in ms) - pad; y1 = max(p[1] + p[3] / 2 for p in ms) + pad + 1.5 * st.font
        k = L["stages"].index(stg)
        o.append(f"  \\draw[sb{k},rounded corners={3 * s:.2f}pt,line width={0.5 * s:.2f}pt] ({P(x0)},{P(y0)}) rectangle ({P(x1)},{P(y1)});")
        o.append(f"  \\node[stt,text=ink] at ({P(x0)},{P(y1)}) {{{esc_tex(stg)}}};")
    for n in nodes:
        i = idx[n["id"]]; x, y, w, h = pos[i]; lines = node_text(n, st)
        if n["kind"] == "op":
            g = GLYPH.get(n["cls"], n["label"]); txt = TEXGLYPH.get(g, esc_tex(g))
            sty = "opn" if len(g) <= 3 else "opb"
            o.append(f"  \\node[{sty},minimum size={P(min(w, h))}pt] (n{i}) at ({P(x)},{P(y)}) {{{txt}}};"
                     if sty == "opn" else f"  \\node[{sty},minimum width={P(w)}pt,minimum height={P(h)}pt] (n{i}) at ({P(x)},{P(y)}) {{{txt}}};")
            continue
        fill = f"st{L['stages'].index(n['stage'])}" if (n["kind"] == "module" and n["stage"] in L["stages"]) else "lightgrey"
        txt = "\\\\".join(esc_tex(l) for l in lines)
        im = imgs.get(n["id"])
        if im:
            gx = f"\\includegraphics[width={im['w'] * s:.2f}pt]{{{img_rel[n['id']]}}}\\\\[{1 * s:.1f}pt]"
            o.append(f"  \\node[box,minimum width={P(w)}pt,minimum height={P(h)}pt] (n{i}) at ({P(x)},{P(y)}) {{{gx}{txt}}};")
        else:
            o.append(f"  \\node[box,fill={fill},minimum width={P(w)}pt,minimum height={P(h)}pt] (n{i}) at ({P(x)},{P(y)}) {{{txt}}};")
    for (a_, b_, pts, lp) in L["edges"]:
        d = f"({P(pts[0][0])},{P(pts[0][1])})"
        for j in range(1, len(pts) - 2, 3):
            d += f" .. controls ({P(pts[j][0])},{P(pts[j][1])}) and ({P(pts[j + 1][0])},{P(pts[j + 1][1])}) .. ({P(pts[j + 2][0])},{P(pts[j + 2][1])})"
        o.append(f"  \\draw[edg] {d};")
        if lp: o.append(f"  \\node[elab] at ({P(lp[0])},{P(lp[1])}) {{{esc_tex(lp[2])}}};")
    if show_params:
        o.append(f"  \\node[anchor=north west,inner sep=0pt,font=\\fontsize{{{f * 0.9:.2f}}}{{{f * 1.1:.2f}}}\\selectfont] at (0,{-1.5 * s:.2f}) {{params {total_params:,}}};")
    o += [r"\end{tikzpicture}", r"\end{document}", ""]
    return "\n".join(o)


def parse_kv(s, sep=","):
    return dict(kv.split("=", 1) for kv in s.split(sep) if "=" in kv) if s else {}


def register_figure(root, out_pdf, width_mm, src_csv, note):
    """append / update the row in figures.csv, same row format as make_figure.finish"""
    fp = os.path.join(root, "figures.csv"); relf = rel(out_pdf, root)
    rows = list(csv.DictReader(open(fp, encoding="utf-8-sig"))) if os.path.exists(fp) else []
    hdr = list(rows[0].keys()) if rows else ["file", "print_width_mm", "source_data", "inspected", "issues"]
    rows = [r for r in rows if r.get("file") != relf and not (r.get("inspected", "no") != "yes" and not os.path.exists(os.path.join(root, r.get("file", ""))))]
    new = {h: "" for h in hdr}; new.update({"file": relf, "print_width_mm": f"{width_mm:g}", "inspected": "no"})
    for k in ("source_data", "source"):
        if k in hdr: new[k] = rel(src_csv, root)
    if "issues" in hdr: new["issues"] = "auto: " + note
    rows.append(new)
    with open(fp, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=hdr); wr.writeheader(); wr.writerows(rows)


def pdf_facts(pdf):
    import fitz
    d = fitz.open(pdf); pg = d[0]
    spans = [sp for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"] if sp["text"].strip()]
    return pg.rect.width / 72 * 25.4, (min(sp["size"] for sp in spans) if spans else None), d


def cmd_render(a):
    root = os.path.abspath(a.project); sp = os.path.join(root, a.spec)
    if not os.path.exists(sp): die("render", f"{a.spec} 不存在：先 trace")
    spec = read_yaml(sp); meta = spec.get("meta") or {}
    nodes = [dict(n) for n in spec.get("nodes") or []]; edges = [dict(e) for e in spec.get("edges") or []]
    if not nodes: die("render", f"{a.spec} 没有节点")
    for n in nodes: n.setdefault("repeat", 1)
    rules = []
    for m in (a.merge or []):
        for part in m.split(";"):
            if "=" in part: rx, lab = part.rsplit("=", 1); rules.append((rx.strip(), lab.strip()))
    nodes, edges, merge_labels = apply_merge(nodes, edges, rules)
    nodes, edges = apply_hide(nodes, edges, a.hide.split(",") if a.hide else [])
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids]
    if a.shapes != "edge":
        for e in edges: e["label"] = ""
    engine = a.engine or ("tikz" if shutil.which("pdflatex") else "dot")
    if engine == "tikz" and not shutil.which("pdflatex"): die("render", "--engine tikz 需要 pdflatex 在 PATH 上（或用 --engine dot）")
    out = os.path.join(root, a.out); odir = os.path.dirname(out); os.makedirs(odir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(out))[0]
    st = Style(a.font_pt); st.show_params = a.show_params; st.shapes = a.shapes
    imgs = {}; img_rel = {}; assets = os.path.join(odir, stem + "_assets")
    for k, p in parse_kv(a.images).items():
        if k not in ids: say("WARN", "render", f"--images {k}: 没有这个节点（可用: {', '.join(sorted(ids)[:6])}…）"); continue
        src = os.path.join(root, p)
        if not os.path.exists(src): die("render", f"图像 {p} 不存在")
        from PIL import Image
        try: iw, ih = Image.open(src).size
        except Exception as ex: die("render", f"图像 {p} 读不了: {ex}")
        w = 6.0 * st.font; h = w * ih / iw
        if h > w * 1.4: h = w * 1.4; w = h * iw / ih
        os.makedirs(assets, exist_ok=True); name = re.sub(r"\W", "_", k) + os.path.splitext(src)[1]; dst = os.path.join(assets, name); shutil.copyfile(src, dst)
        imgs[k] = {"w": w, "h": h, "path": dst}; img_rel[k] = f"{stem}_assets/{name}"
    note = f"params {meta['params_total']:,}" if a.show_params and meta.get("params_total") else None
    L, _ = layout(nodes, edges, st, a.rankdir, imgs, "plain")
    nat_w = L["W"] + 2; target = a.width_mm / 25.4 * 72 - (2 if engine == "tikz" else 0)
    s = min(target / nat_w, 1.5) if nat_w > 0 else 1.0
    if s < 1: say("WARN" if s < 0.8 else "INFO", "render", f"图自然宽 {nat_w / 72 * 25.4:.0f} mm > {a.width_mm:g} mm：整体缩到 {s:.2f}，字号约 {a.font_pt * s * 0.85:.1f} pt。要大字就 --hide 掉 BatchNorm2d,ReLU,Identity、--merge 子树，或 --rankdir TB")
    spec_sha = sha_file(sp)
    if engine == "tikz":
        prefer_times = bool(shutil.which("kpsewhich") and subprocess.run(["kpsewhich", "mathptmx.sty"], capture_output=True, text=True).stdout.strip())
        tex = tex_source(nodes, edges, L, st, s, imgs, img_rel, a.show_params, meta.get("params_total", 0), spec_sha, prefer_times)
        texp = os.path.join(odir, stem + ".tex"); io.open(texp, "w", encoding="utf-8", newline="\n").write(tex)
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", os.path.basename(texp)], cwd=odir, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not os.path.exists(os.path.join(odir, stem + ".pdf")):
            first = next((l for l in (r.stdout + r.stderr).splitlines() if l.startswith("!")), (r.stdout + r.stderr).strip()[-200:])
            die("render", f"pdflatex 编译失败: {first}（{rel(texp, root)}）")
        for ext in (".aux", ".log"):
            try: os.remove(os.path.join(odir, stem + ext))
            except OSError: pass
        pdf = os.path.join(odir, stem + ".pdf")
        if os.path.abspath(pdf) != os.path.abspath(out): shutil.copyfile(pdf, out)
    else:
        W_in = (nat_w - 2) * s / 72 + 0.0; H_in = L["H"] * s / 72
        _, src = layout(nodes, edges, st, a.rankdir, imgs, "pdf", size_in=(W_in, H_in), pdf_out=out, params_note=note)
        io.open(os.path.splitext(out)[0] + ".dot", "w", encoding="utf-8", newline="\n").write(src)
        texp = None
    page_mm, min_pt, doc = pdf_facts(out)
    png = os.path.splitext(out)[0] + ".png"; doc[0].get_pixmap(dpi=200).save(png)
    page_mm = round(page_mm, 1)
    csvp = os.path.splitext(out)[0] + ".source.csv"
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["id", "label", "cls", "shape_in", "shape_out", "params", "stage", "repeat"])
        for n in sorted(nodes, key=lambda n: n["order"]):
            w.writerow([n["id"], n["label"], n["cls"], " | ".join("x".join(map(str, s_)) for s_ in n["shape_in"]), " | ".join("x".join(map(str, s_)) for s_ in n["shape_out"]),
                        n["params"], n["stage"], n.get("repeat", 1)])
    stage_names = [x for x in stages_in_order(nodes) if len(L["members"][x]) >= 2 or any(n["stage"] == x and n["kind"] == "module" for n in nodes)]
    allowed = [lab for lab in merge_labels] + [n["label"] for n in nodes] + [n["cls"] for n in nodes] + stage_names + [k.split(":", 1)[-1] for k in imgs]
    rj = {"spec": rel(sp, root), "spec_sha256": spec_sha, "engine": engine, "width_mm": a.width_mm, "page_mm": page_mm, "font_pt": a.font_pt, "scale": round(s, 3),
          "min_font_pt": round(min_pt, 2) if min_pt else None, "nodes": len(nodes), "edges": len(edges), "hide": a.hide or "", "merge": rules, "merge_labels": merge_labels,
          "show_params": bool(a.show_params), "stage_names": stage_names, "allowed": sorted(set(allowed)), "tex": rel(texp, root) if texp else "", "pdf": rel(out, root)}
    json.dump(rj, io.open(os.path.splitext(out)[0] + ".render.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    register_figure(root, out, page_mm, csvp, f"Architecture traced from {meta.get('model', '?')} (depth {meta.get('depth', '?')}, {len(nodes)} nodes, {len(edges)} edges); shapes C×H×W, batch dropped.")
    say("PASS", "render", f"{rel(out, root)}: {engine}, 页宽 {page_mm:g} mm，节点 {len(nodes)} / 边 {len(edges)}，印刷最小字号 {min_pt:.1f} pt；预览 {rel(png, root)}；figures.csv 已登记（inspected=no → 看图后改 yes）")
    if min_pt is not None and min_pt < 5: say("WARN", "render", f"印刷最小字号 {min_pt:.1f} pt < 5 pt：G5 会 FAIL，按上面的办法减节点")
    sys.exit(FAILS)


# ============================================================================================ check
def word_tokens(text):
    return [t for t in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text) if len(re.findall(r"[A-Za-z]", t)) >= 2]


def tex_texts(tex):
    tex = re.sub(r"(?m)(?<!\\)%.*$", "", tex)
    body = tex.split(r"\begin{document}", 1)[-1]
    out = []
    for m in re.finditer(r"\\node\b[^;]*?\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}\s*;", body, re.S):
        t = m.group(1)
        t = re.sub(r"\\includegraphics\s*(\[[^\]]*\])?\s*\{[^}]*\}", " ", t); t = re.sub(r"\$[^$]*\$", " ", t)
        t = re.sub(r"\\\\(\[[^\]]*\])?", " ", t); t = re.sub(r"\\([_&%#$\{\}])", r"\1", t); t = re.sub(r"\\[A-Za-z]+\*?", " ", t); t = t.replace("\\", " ")
        out.append(t)
    return out


def method_text(md):
    lines = md.splitlines(); best = None
    for i, l in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", l)
        if m and re.search(r"(?i)method|approach|architecture|framework|proposed|model|方法|模型", m.group(2)):
            best = (i, len(m.group(1))); break
    if not best: return None
    i, lv = best; buf = []
    for l in lines[i + 1:]:
        m = re.match(r"^(#{1,6})\s", l)
        if m and len(m.group(1)) <= lv: break
        buf.append(l)
    return "\n".join(buf)


def multiset(nodes):
    return collections.Counter((n["kind"], n["cls"], json.dumps(n["shape_in"]), json.dumps(n["shape_out"]), n.get("repeat", 1), n.get("params", 0)) for n in nodes)


def input_hw(spec):
    out = []
    for it in parse_inputs((spec.get("meta") or {}).get("input", "")):
        if len(it["shape"]) >= 3: out.append((it["name"], tuple(it["shape"][-2:])))
    return out


def ref_resolution(root, state):
    """(hw tuple, where) of the reference run, or None"""
    ref = ((state.get("bundle") or {}).get("matrix") or {}).get("ref") or {}
    name = ref.get("name") if isinstance(ref, dict) else None
    runs = (state.get("audits") or {}).get("runs_dir", "runs")
    cands = []
    if name: cands += sorted(glob.glob(os.path.join(root, runs, name, "args.json"))) + sorted(glob.glob(os.path.join(root, runs, name + "*", "args.json")))
    for c in cands:
        try: d = json.load(io.open(c, encoding="utf-8"))
        except Exception: continue
        for k in ("img_size", "input_size", "imgsz", "img_sz", "image_size"):
            if k in d:
                v = d[k]
                if isinstance(v, (int, float)): return (int(v), int(v)), f"{rel(c, root)}:{k}"
                if isinstance(v, (list, tuple)) and len(v) >= 2: return (int(v[0]), int(v[1])), f"{rel(c, root)}:{k}"
    if isinstance(ref, dict) and ref.get("args"):
        m = re.search(r"--(?:img[-_]?size|imgsz|input[-_]size|image[-_]size)[ =](\d+)(?:[ ,x](\d+))?", str(ref["args"]))
        if m: return (int(m.group(1)), int(m.group(2) or m.group(1))), "state.bundle.matrix.ref.args"
    return None


def check_one(a, root, state, specp):
    spec = read_yaml(specp); meta = spec.get("meta") or {}; nodes = spec.get("nodes") or []; tag = rel(specp, root)
    # (1) re-trace
    try:
        import torch
        have_torch = True
    except ImportError:
        have_torch = False
    if not have_torch: say("WARN", "architecture", f"{tag}: torch 不可用，无法重新 trace（跳过 (1)）")
    else:
        fresh = None
        try:
            fresh, _ = do_trace(meta["model"], meta.get("init", ""), meta["input"], int(meta.get("depth", 1)), meta.get("device", "cpu") if (meta.get("device", "cpu") != "cuda" or torch.cuda.is_available()) else "cpu",
                                "", meta.get("stages", ""), meta.get("label_names", False), root, state)
        except SystemExit:
            say("FAIL", "architecture", f"{tag}: 无法重新 trace（模型加载/前向失败，见上一行）：图是不是从已不存在的代码画的？")
        if fresh:
            fm = fresh["meta"]; same_sha = fm["code_sha256"] == meta.get("code_sha256")
            diff_a = multiset(nodes) - multiset(fresh["nodes"]); diff_b = multiset(fresh["nodes"]) - multiset(nodes)
            n_diff = sum(diff_a.values()) + sum(diff_b.values())
            if n_diff == 0 and same_sha: say("PASS", "architecture", f"{tag}: 代码未变，重新 trace 的 {len(nodes)} 个节点与图一致")
            elif n_diff == 0: say("PASS", "architecture", f"{tag}: 代码文件改过（sha 变了）但重新 trace 的节点与图一致")
            else:
                ex = [f"图里有 {k[1]} {json.loads(k[3])} ×{k[4]}（{k[5]:,} 参数），现在的模型没有" for k in list(diff_a)[:2]] + [f"现在的模型有 {k[1]} {json.loads(k[3])} ×{k[4]}（{k[5]:,} 参数），图里没有" for k in list(diff_b)[:2]]
                say("FAIL", "architecture", f"{tag}: 图是从旧模型画的：{n_diff} 处不同（例：{'；'.join(ex)}）—— 重新 trace/render")
            if n_diff == 0 and fresh["meta"]["params_total"] != meta.get("params_total"): say("WARN", "architecture", f"{tag}: 参数量 {meta.get('params_total'):,} → {fresh['meta']['params_total']:,}（图的 spec 已过期）")
    # locate the rendered figure
    rjs = []
    for f in glob.glob(os.path.join(root, "figures", "**", "*.render.json"), recursive=True):
        try: j = json.load(io.open(f, encoding="utf-8"))
        except Exception: continue
        if j.get("spec") == tag: rjs.append((f, j))
    figs = []
    if a.figure: figs.append((os.path.join(root, a.figure), next((j for f, j in rjs if os.path.join(root, j.get("pdf", "")) == os.path.join(root, a.figure)), {})))
    else: figs += [(os.path.join(root, j["pdf"]), j) for f, j in rjs]
    if not figs: say("INFO", "architecture", f"{tag}: 还没有渲染过的图（render 之后 check 才查文字、参数、阶段名）")
    allow = {t for it in (a.allow or "").split(",") for t in word_tokens(it)}
    for fig, rj in figs:
        ft = rel(fig, root)
        if rj and rj.get("spec_sha256") != sha_file(specp): say("WARN", "architecture", f"{ft}: 图是从旧 spec 渲染的（spec 之后又被重新 trace）：重新 render")
        if not os.path.exists(fig): say("FAIL", "architecture", f"{ft} 不存在"); continue
        okt = set(allow)
        for s_ in (rj.get("allowed") or []) + [n["label"] for n in nodes] + [n["cls"] for n in nodes] + [n["stage"] for n in nodes]: okt |= set(word_tokens(s_))
        for n in nodes:
            if meta.get("label_names"): okt |= set(word_tokens(n["id"]))
        okt |= {"params", "param"}; low = {t.lower() for t in okt}
        def accepted(t):
            tl = t.lower()
            return tl in low or (len(tl) >= 3 and any(x.startswith(tl) or x.endswith(tl) for x in low))
        unknown = []; text = ""
        try:
            import fitz
            d = fitz.open(fig); text = "\n".join(p.get_text() for p in d)
            words = [w[4] for p in d for w in p.get_text("words")]
            for i, w in enumerate(words):
                for t in word_tokens(w):
                    if not accepted(t) and not (i + 1 < len(words) and accepted(t + "".join(word_tokens(words[i + 1])))): unknown.append(t)
        except ImportError: say("WARN", "architecture", "未安装 PyMuPDF，跳过 PDF 文字检查")
        texf = a.tex and os.path.join(root, a.tex) or (os.path.join(root, rj["tex"]) if rj.get("tex") else None)
        if texf and os.path.exists(texf):
            for chunk in tex_texts(io.open(texf, encoding="utf-8").read()):
                for t in word_tokens(chunk):
                    if not accepted(t): unknown.append(t)
        unknown = list(dict.fromkeys(unknown))
        if unknown: say("WARN", "architecture", f"{ft}: 图里出现了 trace 里没有的文字: {', '.join(unknown[:8])}（手工加的模块？加了就在 --allow 里登记，或回到 trace）")
        else: say("PASS", "architecture", f"{ft}: 图中文字都来自 trace（节点 / 类名 / 阶段 / 形状 / 运算符）")
        # (3) params
        m = re.search(r"params\s+([\d,]+)", text)
        if m:
            shown = int(m.group(1).replace(",", ""))
            if shown != meta.get("params_total"): say("FAIL", "architecture", f"{ft}: 图里的参数量 {shown:,} ≠ trace 的 {meta.get('params_total'):,}")
            else: say("PASS", "architecture", f"{ft}: 参数量 {shown:,} 与 trace 一致")
        elif rj.get("show_params"): say("WARN", "architecture", f"{ft}: 渲染时开了 --show-params，但 PDF 里找不到 'params N' 行（被手工删了？）")
        # (4) stage names in the Method section
        names = rj.get("stage_names") or stages_in_order(nodes)
        mp = os.path.join(root, "paper", "manuscript.md")
        if names and os.path.exists(mp):
            mt = method_text(io.open(mp, encoding="utf-8").read())
            if mt is None: say("INFO", "architecture", "manuscript.md 里没找到 Method 节标题，跳过阶段名核对")
            else:
                miss = [s_ for s_ in names if s_.lower() not in mt.lower()]
                for s_ in miss: say("WARN", "architecture", f"{ft}: 阶段名 \"{s_}\" 在 Method 节里没出现：正文要用图里的名字，或在 render 里 --merge 成正文用的名字")
                if not miss: say("PASS", "architecture", f"{ft}: {len(names)} 个阶段名都在 Method 节里出现")
    # (5) input resolution
    rr = ref_resolution(root, state)
    if rr:
        hw, where = rr; bad = [(n, s_) for n, s_ in input_hw(spec) if s_ != hw]
        if bad: say("WARN", "architecture", f"{tag}: 图里的输入分辨率不是跑结果用的：图 {bad[0][1]}（{bad[0][0]}）vs {where} = {hw}")
        else: say("PASS", "architecture", f"{tag}: 输入分辨率 {hw} 与 {where} 一致")


def cmd_check(a):
    root = os.path.abspath(a.project); state = load_state(root)
    specs = [os.path.join(root, a.spec)] if a.spec else sorted(glob.glob(os.path.join(root, "figures", "arch", "*.yaml")))
    if not specs: say("INFO", "architecture", "没有 figures/arch/*.yaml（没有用 trace 画的总览图）"); sys.exit(0)
    for s_ in specs:
        if not os.path.exists(s_): say("FAIL", "architecture", f"{rel(s_, root)} 不存在"); continue
        check_one(a, root, state, s_)
    sys.exit(FAILS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("trace"); p.add_argument("--project", default="."); p.add_argument("--model", required=True); p.add_argument("--init", default="")
    p.add_argument("--input", required=True); p.add_argument("--depth", type=int, default=2); p.add_argument("--device", default="cpu"); p.add_argument("--sample", default="")
    p.add_argument("--stages", default=""); p.add_argument("--label-names", action="store_true"); p.add_argument("--dump-activations", default=""); p.add_argument("--out", required=True)
    p = sub.add_parser("render"); p.add_argument("--project", default="."); p.add_argument("--spec", required=True); p.add_argument("--out", required=True)
    p.add_argument("--engine", choices=["tikz", "dot"], default=""); p.add_argument("--rankdir", default="LR"); p.add_argument("--hide", default="")
    p.add_argument("--merge", action="append", default=[]); p.add_argument("--images", default=""); p.add_argument("--width-mm", type=float, default=178)
    p.add_argument("--font-pt", type=float, default=7); p.add_argument("--show-params", action="store_true")
    p.add_argument("--shapes", choices=["edge", "node", "none"], default="edge", help="where tensor shapes go: on the edges where they change (default), as a second line in each node (about 40 %% narrower), or nowhere")
    p = sub.add_parser("check"); p.add_argument("--project", default="."); p.add_argument("--spec", default=""); p.add_argument("--figure", default="")
    p.add_argument("--tex", default=""); p.add_argument("--allow", default="")
    a = ap.parse_args(); {"trace": cmd_trace, "render": cmd_render, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
