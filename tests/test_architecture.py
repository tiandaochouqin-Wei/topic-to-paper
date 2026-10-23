# -*- coding: utf-8 -*-
"""make_architecture.py: trace / render / check on a tiny two-branch model written to code/toy.py.

The toy has two conv stems (rgb, x), a fuse made of add + 1x1 conv gate (sigmoid, mul), a down-conv + interpolate + cat, a neck of two
identical blocks (residual add inside each), and a Linear head after adaptive pool + flatten, so that every kind of node the tracer
knows (module, glue op, repeat, input, output) occurs. One shared project is traced/rendered once per module (torch import is the slow part);
tests that mutate something copy it first."""
import csv, hashlib, io, json, shutil

import pytest
import yaml

from conftest import GBK_ENV, run, read, write, edit, SKILL

torch = pytest.importorskip("torch")

TOY = '''import torch, torch.nn as nn, torch.nn.functional as F


def stem(c_in, c):
    return nn.Sequential(nn.Conv2d(c_in, c, 3, padding=1), nn.BatchNorm2d(c), nn.ReLU())


class Block(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.conv = nn.Conv2d(c, c, 3, padding=1)

    def forward(self, x):
        return x + self.conv(x)


class Toy(nn.Module):
    def __init__(self, c=8, nc=4):
        super().__init__()
        self.stem_rgb = stem(3, c)
        self.stem_x = stem(1, c)
        self.gate = nn.Conv2d(c, c, 1)
        self.down = nn.Conv2d(c, 2 * c, 3, stride=2, padding=1)
        self.neck = nn.Sequential(Block(3 * c), Block(3 * c))
        self.head = nn.Linear(3 * c, nc)

    def forward(self, rgb, x):
        a = self.stem_rgb(rgb)
        b = self.stem_x(x)
        s = a + b
        g = torch.sigmoid(self.gate(s))
        f = s * g
        d = F.interpolate(self.down(f), size=f.shape[-2:])
        c = torch.cat([f, d], dim=1)
        n = self.neck(c)
        return self.head(F.adaptive_avg_pool2d(n, 1).flatten(1))
'''
TRACE = ["trace", "--model", "code/toy.py:Toy", "--init", "c=8,nc=4", "--input", "rgb:1x3x32x32,x:1x1x32x32"]
HAVE_LATEX = shutil.which("pdflatex") is not None
HAVE_DOT = shutil.which("dot") is not None
needs_dot = pytest.mark.skipif(not HAVE_DOT, reason="graphviz dot not on PATH")
needs_tex = pytest.mark.skipif(not (HAVE_DOT and HAVE_LATEX), reason="dot + pdflatex needed")


def arch(proj, *args, **kw):
    return run("make_architecture.py", *args, cwd=proj, **kw)


def spec(proj, name):
    return yaml.safe_load(io.open(proj / "figures" / "arch" / name, encoding="utf-8"))


def ops(sp, cls):
    return [n for n in sp["nodes"] if n["kind"] == "op" and n["cls"] == cls]


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    d = tmp_path_factory.mktemp("arch")
    write(d / "code" / "toy.py", TOY)
    for depth in (1, 2, 3):
        r = arch(d, *TRACE, "--depth", depth, "--out", f"figures/arch/toy{depth}.yaml")
        assert r.returncode == 0 and not r.crashed, r.out
    return d


@pytest.fixture
def work(proj, tmp_path):
    dst = tmp_path / "p"
    shutil.copytree(proj, dst)
    return dst


def figrows(p):
    return list(csv.DictReader(io.open(p / "figures.csv", encoding="utf-8-sig")))


# ------------------------------------------------------------------ trace
def test_trace_depth1(proj):
    sp = spec(proj, "toy1.yaml"); ids = {n["id"]: n for n in sp["nodes"]}
    mods = [n["id"] for n in sorted(sp["nodes"], key=lambda n: n["order"]) if n["kind"] == "module"]
    assert mods == ["stem_rgb", "stem_x", "gate", "down", "neck", "head"]
    assert {"input:rgb", "input:x", "output:out"} <= set(ids)
    for k in ("add", "sigmoid", "mul", "interpolate", "cat", "pool", "flatten"):
        assert len(ops(sp, k)) == 1, k                      # glue in the model's own forward is drawn
    assert ids["neck"]["cls"] == "Sequential" and ids["neck"].get("repeat", 1) == 1
    for e in sp["edges"]:
        assert e["from"] in ids and e["to"] in ids, e       # no dangling endpoint
    for n in sp["nodes"]:
        if n["kind"] != "input": assert any(e["to"] == n["id"] for e in sp["edges"]), f"{n['id']} has no producer"
    into = lambda i: sorted(e["from"] for e in sp["edges"] if e["to"] == i)
    assert into("/add#0") == ["stem_rgb", "stem_x"]
    assert into("/mul#0") == ["/add#0", "/sigmoid#0"]       # tensor identity: the gate multiplies the sum it was computed from
    assert into("/cat#0") == ["/interpolate#0", "/mul#0"]
    assert into("output:out") == ["head"]
    assert sp["meta"]["depth"] == 1 and sp["meta"]["code_sha256"] == hashlib.sha256((proj / "code" / "toy.py").read_bytes()).hexdigest()


def test_trace_stages_in_forward_order(proj):
    r = arch(proj, *TRACE, "--depth", 1, "--out", "figures/arch/_o.yaml")
    assert r.returncode == 0
    assert "stages: stem_rgb → stem_x → gate → down → neck → head" in r.out and "[PASS] trace" in r.out


def test_trace_depth2_collapses_and_repeats(proj):
    sp = spec(proj, "toy2.yaml"); ids = {n["id"]: n for n in sp["nodes"]}
    assert {"stem_rgb.0", "stem_rgb.1", "stem_rgb.2", "stem_x.0"} <= set(ids)
    assert ids["stem_rgb.1"]["cls"] == "BatchNorm2d" and ids["stem_rgb.1"]["stage"] == "stem_rgb"
    blk = ids["neck.0"]
    assert blk["cls"] == "Block" and blk["repeat"] == 2 and "neck.1" not in ids     # two identical blocks -> one node "x 2"
    assert len(ops(sp, "add")) == 1                          # the residual add inside each collapsed Block is hidden
    assert blk["params"] == 2 * (24 * 24 * 9 + 24)
    for e in sp["edges"]: assert e["from"] in ids and e["to"] in ids
    assert [e["from"] for e in sp["edges"] if e["to"] == "/pool#0"] == ["neck.0"]


def test_trace_depth3_opens_the_blocks(proj):
    sp = spec(proj, "toy3.yaml"); ids = {n["id"] for n in sp["nodes"]}
    assert len(ops(sp, "add")) == 3                          # root add + the residual add of each Block, now glue between visible nodes
    assert {"neck.0.conv", "neck.1.conv"} <= ids and "neck.0" not in ids
    assert all(n.get("repeat", 1) == 1 for n in sp["nodes"])  # the two convs are separated by an add: not a chain


def test_params_total_and_node_params(proj):
    sp = spec(proj, "toy1.yaml")
    import importlib.util
    s = importlib.util.spec_from_file_location("toy_t", proj / "code" / "toy.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    assert sp["meta"]["params_total"] == sum(p.numel() for p in m.Toy(8, 4).parameters())
    assert sum(n["params"] for n in sp["nodes"] if n["kind"] == "module") == sp["meta"]["params_total"]


def test_edge_labels_only_where_shape_changes(proj):
    sp = spec(proj, "toy2.yaml"); lab = {(e["from"], e["to"]): e["label"] for e in sp["edges"]}
    assert lab[("input:rgb", "stem_rgb.0")] == "3×32×32"     # batch dropped, first edge always labelled
    assert lab[("stem_rgb.0", "stem_rgb.1")] == "8×32×32"
    assert lab[("stem_rgb.1", "stem_rgb.2")] == ""           # BatchNorm keeps the shape: no label
    assert lab[("down", "/interpolate#0")] == "16×16×16" and lab[("/interpolate#0", "/cat#0")] == "16×32×32"


def test_stages_option_and_label_names(proj):
    r = arch(proj, *TRACE, "--depth", 2, "--stages", "RGB=^stem_rgb,Neck=^neck", "--label-names", "--out", "figures/arch/_s.yaml")
    assert r.returncode == 0, r.out
    sp = spec(proj, "_s.yaml"); ids = {n["id"]: n for n in sp["nodes"]}
    assert ids["stem_rgb.0"]["stage"] == "RGB" and ids["neck.0"]["stage"] == "Neck" and ids["stem_x.0"]["stage"] == "stem_x"
    assert ids["stem_rgb.0"]["label"] == "stem_rgb.0"


def test_trace_resnet18_from_package(tmp_path):
    pytest.importorskip("torchvision")
    r = arch(tmp_path, "trace", "--model", "torchvision.models:resnet18", "--input", "1x3x224x224", "--depth", 1, "--out", "figures/arch/r18.yaml")
    assert r.returncode == 0 and not r.crashed, r.out
    sp = spec(tmp_path, "r18.yaml")
    mods = [n for n in sp["nodes"] if n["kind"] == "module"]
    assert len(mods) == 10 and [n["id"] for n in ops(sp, "flatten")] == ["/flatten#0"]
    assert {"input:input", "output:out"} <= {n["id"] for n in sp["nodes"]}
    assert sp["meta"]["params_total"] == 11689512 and sp["meta"]["code_sha256"].startswith("pkg:torchvision==")
    assert arch(tmp_path, "trace", "--model", "torchvision.models:resnet18", "--input", "1x3x224x224", "--depth", 2, "--out", "figures/arch/r18b.yaml").returncode == 0
    n2 = yaml.safe_load(io.open(tmp_path / "figures/arch/r18b.yaml", encoding="utf-8"))["nodes"]
    assert next(n for n in n2 if n["id"] == "layer1.0")["repeat"] == 2 and not [n for n in n2 if n["kind"] == "op" and n["cls"] == "add"]


def test_dump_activations(work):
    r = arch(work, *TRACE, "--depth", 2, "--dump-activations", "stem_rgb.2,neck", "--out", "figures/arch/a.yaml")
    assert r.returncode == 0, r.out
    sp = spec(work, "a.yaml")
    assert [a["module"] for a in sp["activations"]] == ["stem_rgb.2", "neck"]
    from PIL import Image
    for a in sp["activations"]:
        f = work / a["file"]; assert f.exists()
        w, h = Image.open(f).size; assert w == h and w >= 32     # square pixels, square map
    bad = arch(work, *TRACE, "--depth", 2, "--dump-activations", "nope", "--out", "figures/arch/b.yaml")
    assert bad.fails == 1 and "nope" in bad.out


def test_bad_inputs_fail_cleanly(work):
    r = arch(work, "trace", "--model", "code/toy.py:Nope", "--input", "1x3x8x8", "--out", "figures/arch/c.yaml")
    assert r.fails == 1 and not r.crashed
    r = arch(work, "trace", "--model", "code/toy.py:Toy", "--input", "rgb:1x3x32x32", "--out", "figures/arch/c.yaml")   # forward needs two inputs
    assert r.fails == 1 and not r.crashed and "前向失败" in r.out


# ------------------------------------------------------------------ render
@needs_dot
def test_render_dot_vector_and_registered(work):
    r = arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_arch.pdf", "--engine", "dot")
    assert r.returncode == 0 and not r.crashed, r.out
    import fitz
    d = fitz.open(work / "figures" / "fig_arch.pdf")
    assert d[0].get_images() == [] and b"/Subtype /Image" not in (work / "figures" / "fig_arch.pdf").read_bytes()    # vector
    text = d[0].get_text()
    assert "Conv2d" in text and "Block" in text and "×2" in text and "stem_rgb" in text
    assert (work / "figures" / "fig_arch.png").exists() and (work / "figures" / "fig_arch.dot").exists()
    nodes = spec(work, "toy2.yaml")["nodes"]
    rows = list(csv.DictReader(io.open(work / "figures" / "fig_arch.source.csv", encoding="utf-8")))
    assert len(rows) == len(nodes) and {r_["id"] for r_ in rows} == {n["id"] for n in nodes}
    fr = [x for x in figrows(work) if x["file"] == "figures/fig_arch.pdf"]
    assert len(fr) == 1 and fr[0]["inspected"] == "no" and fr[0]["source_data"] == "figures/fig_arch.source.csv"
    assert abs(float(fr[0]["print_width_mm"]) - d[0].rect.width / 72 * 25.4) < 0.2        # registered width = measured page width
    rj = json.load(io.open(work / "figures" / "fig_arch.render.json", encoding="utf-8"))
    assert rj["nodes"] == len(nodes) and rj["edges"] == len(spec(work, "toy2.yaml")["edges"]) and rj["engine"] == "dot"


@needs_tex
def test_render_tikz_compiles_and_keeps_tex(work):
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_arch.pdf", "--engine", "tikz", "--width-mm", 178)
    assert r.returncode == 0 and not r.crashed, r.out
    tex = read(work / "figures" / "fig_arch.tex")
    assert "\\documentclass[tikz,border=1pt]{standalone}" in tex and "rounded corners" in tex and "spec_sha256=" in tex and "Sequential" in tex
    assert not (work / "figures" / "fig_arch.aux").exists() and not (work / "figures" / "fig_arch.log").exists()
    import fitz
    d = fitz.open(work / "figures" / "fig_arch.pdf")
    assert d[0].get_images() == [] and "Sequential" in d[0].get_text() and d[0].rect.width / 72 * 25.4 <= 178.5
    rj = json.load(io.open(work / "figures" / "fig_arch.render.json", encoding="utf-8"))
    assert rj["engine"] == "tikz" and rj["tex"] == "figures/fig_arch.tex" and rj["min_font_pt"] > 3


@needs_tex
def test_render_tikz_labels_are_escaped_not_executed(work):
    spec_p = work / "figures" / "arch" / "toy1.yaml"
    sp = yaml.safe_load(io.open(spec_p, encoding="utf-8")); sp["nodes"][2]["label"] = "\\undefinedmacro_50%"
    io.open(spec_p, "w", encoding="utf-8").write(yaml.safe_dump(sp, allow_unicode=True))
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_esc.pdf", "--engine", "tikz")
    assert r.returncode == 0, r.out
    assert "\\textbackslash{}undefinedmacro\\_50\\%" in read(work / "figures" / "fig_esc.tex")


@needs_tex
def test_render_tikz_compile_failure_is_a_fail_with_the_first_bang_line(work):
    spec_p = work / "figures" / "arch" / "toy1.yaml"
    sp = yaml.safe_load(io.open(spec_p, encoding="utf-8")); sp["nodes"][2]["label"] = "骨干"      # not typesettable with pdflatex
    io.open(spec_p, "w", encoding="utf-8").write(yaml.safe_dump(sp, allow_unicode=True))
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_cjk.pdf", "--engine", "tikz")
    assert r.fails == 1 and r.returncode == 1 and not r.crashed and "pdflatex 编译失败: !" in r.out
    assert (work / "figures" / "fig_cjk.tex").exists()                      # the .tex stays for inspection


@needs_dot
def test_hide_reroutes_edges(work):
    base = spec(work, "toy2.yaml")
    r = arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_h.pdf", "--engine", "dot", "--hide", "BatchNorm2d")
    assert r.returncode == 0, r.out
    rj = json.load(io.open(work / "figures" / "fig_h.render.json", encoding="utf-8"))
    assert rj["nodes"] == len(base["nodes"]) - 2 and rj["edges"] == len(base["edges"]) - 2      # each BN had one in and one out edge
    rows = list(csv.DictReader(io.open(work / "figures" / "fig_h.source.csv", encoding="utf-8")))
    assert not [x for x in rows if x["cls"] == "BatchNorm2d"]
    import fitz
    assert "BatchNorm2d" not in fitz.open(work / "figures" / "fig_h.pdf")[0].get_text()


@needs_dot
def test_merge_collapses_subtree(work):
    base = spec(work, "toy2.yaml")
    r = arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_m.pdf", "--engine", "dot", "--merge", "stem_rgb.*=RGB branch")
    assert r.returncode == 0, r.out
    rj = json.load(io.open(work / "figures" / "fig_m.render.json", encoding="utf-8"))
    assert rj["nodes"] == len(base["nodes"]) - 2 and rj["edges"] == len(base["edges"]) - 2 and rj["merge_labels"] == ["RGB branch"]
    rows = list(csv.DictReader(io.open(work / "figures" / "fig_m.source.csv", encoding="utf-8")))
    m = [x for x in rows if x["label"] == "RGB branch"]
    assert len(m) == 1 and int(m[0]["params"]) == 224 + 16 + 0 and m[0]["shape_out"] == "1x8x32x32"
    import fitz
    t = fitz.open(work / "figures" / "fig_m.pdf")[0].get_text()
    assert "RGB branch" in t and "stem_rgb" not in t


def _png(p, size=(40, 30)):
    from PIL import Image
    im = Image.new("RGB", size, (200, 120, 40)); im.putpixel((3, 3), (0, 0, 0)); im.save(p)


@needs_dot
def test_images_embedded_dot(work):
    _png(work / "rgb.png")
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_i.pdf", "--engine", "dot", "--images", "input:rgb=rgb.png,output:out=rgb.png")
    assert r.returncode == 0, r.out
    import fitz
    assert len(fitz.open(work / "figures" / "fig_i.pdf")[0].get_images()) >= 1
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_i2.pdf", "--engine", "dot", "--images", "input:nope=rgb.png")
    assert "[WARN] render" in r.out and "nope" in r.out


@needs_tex
def test_images_embedded_tikz(work):
    _png(work / "rgb.png")
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_i.pdf", "--engine", "tikz", "--images", "input:rgb=rgb.png")
    assert r.returncode == 0, r.out
    import fitz
    assert len(fitz.open(work / "figures" / "fig_i.pdf")[0].get_images()) >= 1
    assert "includegraphics" in read(work / "figures" / "fig_i.tex") and (work / "figures" / "fig_i_assets" / "input_rgb.png").exists()


@needs_tex
def test_print_font_passes_g5_when_the_graph_fits(work):
    """merge the stems and the neck so the page is built at 7 pt: the registered width equals the page width and G5's font audit passes"""
    r = arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_arch.pdf", "--engine", "tikz",
             "--merge", "stem_.*=Stems", "--rankdir", "TB")
    assert r.returncode == 0, r.out
    g = run("gate_check.py", "dpi", "--manuscript", "figures.csv", cwd=work)
    assert "[FAIL] dpi: figures/fig_arch.pdf 印刷最小字号" not in g.out and "无 Type 3" in g.out and not g.crashed, g.out


@needs_dot
def test_show_params_footnote(work):
    r = arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_p.pdf", "--engine", "dot", "--show-params")
    assert r.returncode == 0, r.out
    import fitz
    assert "params 12,092" in fitz.open(work / "figures" / "fig_p.pdf")[0].get_text()


# ------------------------------------------------------------------ check
@needs_dot
def test_check_passes_on_untouched_project(work):
    assert arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_arch.pdf", "--engine", "dot", "--show-params").returncode == 0
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.returncode == 0 and r.fails == 0 and not r.crashed, r.out
    assert "[WARN]" not in r.out and "代码未变" in r.out and "参数量 12,092 与 trace 一致" in r.out


@needs_dot
def test_check_fails_when_the_model_changed(work):
    assert arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_arch.pdf", "--engine", "dot").returncode == 0
    edit(work / "code" / "toy.py", "self.head = nn.Linear(3 * c, nc)", "self.head = nn.Linear(3 * c, nc + 3)")   # a channel count changed
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.fails == 1 and r.returncode == 1 and "图是从旧模型画的" in r.out and "Linear" in r.out


def test_check_sees_changes_that_keep_every_shape(work):
    edit(work / "code" / "toy.py", "self.gate = nn.Conv2d(c, c, 1)", "self.gate = nn.Conv2d(c, c, 3, padding=1)")   # kernel size: shapes identical, params not
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.fails == 1 and "图是从旧模型画的" in r.out


def test_check_comment_only_edit_is_a_pass(work):
    edit(work / "code" / "toy.py", "class Block(nn.Module):", "# a comment\nclass Block(nn.Module):")
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.fails == 0 and "代码文件改过" in r.out and "节点与图一致" in r.out


def test_check_when_the_model_no_longer_loads(work):
    edit(work / "code" / "toy.py", "class Toy(nn.Module):", "class Toy2(nn.Module):")
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.fails >= 1 and not r.crashed and "无法重新 trace" in r.out


@needs_tex
def test_check_warns_on_a_hand_added_label_in_the_tex(work):
    assert arch(work, "render", "--spec", "figures/arch/toy1.yaml", "--out", "figures/fig_arch.pdf", "--engine", "tikz").returncode == 0
    texp = work / "figures" / "fig_arch.tex"
    edit(texp, "\\end{tikzpicture}", "  \\node at (0,0) {FancyModule};\n\\end{tikzpicture}")
    r = arch(work, "check", "--spec", "figures/arch/toy1.yaml")
    assert r.fails == 0 and "[WARN] architecture" in r.out and "FancyModule" in r.out
    ok = arch(work, "check", "--spec", "figures/arch/toy1.yaml", "--allow", "FancyModule")
    assert "FancyModule" not in ok.out and "[WARN]" not in ok.out


@needs_dot
def test_check_params_in_the_figure_must_match_the_trace(work):
    assert arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_arch.pdf", "--engine", "dot", "--show-params").returncode == 0
    edit(work / "figures" / "arch" / "toy2.yaml", "params_total: 12092", "params_total: 12093")
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.fails == 1 and "参数量 12,092 ≠ trace 的 12,093" in r.out


@needs_dot
def test_check_stale_spec_and_stage_names_in_method(work):
    assert arch(work, "render", "--spec", "figures/arch/toy2.yaml", "--out", "figures/fig_arch.pdf", "--engine", "dot").returncode == 0
    write(work / "paper" / "manuscript.md", "# T\n\n## 1 Introduction\n\nstem_x and gate.\n\n## 3 Method\n\nThe stem_rgb branch feeds the neck and the down path; stem_x too.\n\n### 3.1 Fusion\n\nThe head.\n\n## 4 Experiments\n\ngate.\n")
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    miss = [l for l in r.out.splitlines() if "在 Method 节里没出现" in l]
    assert len(miss) == 1 and "\"gate\"" in miss[0] and r.fails == 0      # gate is only named in other sections
    sp = work / "figures" / "arch" / "toy2.yaml"; sp.write_text(sp.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    assert "图是从旧 spec 渲染的" in arch(work, "check", "--spec", "figures/arch/toy2.yaml").out


def test_check_input_resolution_vs_reference_run(work):
    write(work / "research-state.yaml", "bundle:\n  matrix:\n    ref: {name: ours, args: '--exp ours'}\naudits:\n  runs_dir: runs\n")
    write(work / "runs" / "ours" / "args.json", json.dumps({"img_size": 64, "seed": 0}))
    r = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert r.fails == 0 and "图里的输入分辨率不是跑结果用的" in r.out and "(64, 64)" in r.out
    write(work / "runs" / "ours" / "args.json", json.dumps({"img_size": [32, 32]}))
    ok = arch(work, "check", "--spec", "figures/arch/toy2.yaml")
    assert "输入分辨率 (32, 32)" in ok.out and "[WARN]" not in ok.out


def test_check_without_specs_is_silent_ok(tmp_path):
    r = arch(tmp_path, "check")
    assert r.returncode == 0 and "[FAIL]" not in r.out


def test_trace_survives_a_gbk_console(work):
    r = arch(work, *TRACE, "--depth", 2, "--out", "figures/arch/g.yaml", env=GBK_ENV)
    assert r.returncode == 0 and not r.crashed, r.out
    c = arch(work, "check", "--spec", "figures/arch/g.yaml", env=GBK_ENV)
    assert c.returncode == 0 and not c.crashed, c.out


# ------------------------------------------------------------------ G5 wiring
@pytest.fixture
def research_arch(research):
    write(research / "code" / "toy.py", TOY)
    r = arch(research, *TRACE, "--depth", 1, "--out", "figures/arch/toy.yaml")
    assert r.returncode == 0, r.out
    return research


def _g5(p):
    r = run("t2p.py", "check", "--no-write", cwd=p)
    return next(l for l in r.out.splitlines() if "G5" in l and l.startswith("["))


def test_t2p_g5_reports_architecture_counts(research_arch):
    line = _g5(research_arch)
    assert "architecture 0 FAIL / 0 WARN" in line, line


def test_t2p_g5_folds_an_architecture_fail(research_arch):
    edit(research_arch / "code" / "toy.py", "self.head = nn.Linear(3 * c, nc)", "self.head = nn.Linear(3 * c, nc + 2)")
    line = _g5(research_arch)
    assert line.startswith("[FAIL] G5") and "architecture 1 FAIL" in line, line
