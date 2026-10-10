# -*- coding: utf-8 -*-
"""G3 静态审计的精度：别把正则字面量当路径，别把写文件当读文件，检查点可以不存在，split_files 配了但缺文件要说清。

全部来自 2026-10-11 真项目 P3 的实测：一个**生产** tiles.csv / radio.json 的数据准备脚本被判了两条
"判一个文件、读另一个文件" FAIL，原因是 ① 脚本里 re.search(r"(label|gts|…)") 的正则字面量被当成"检查过的路径"，
② 同名文件是被 csv.DictWriter 写出来的，却算进了"读"。另外 OPTIONAL 正则里混进了字面退格符，`out` 分支一直是死的。
"""
import importlib.util

from conftest import SCRIPTS, read, run, write


def _ac():
    spec = importlib.util.spec_from_file_location("audit_check", SCRIPTS / "audit_check.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_no_literal_control_characters_in_scripts():
    """字面退格符曾让三处正则的 \\b 失效（audit_check 的 OPTIONAL、baseline_miner 的两处消融行识别）。"""
    bad = {}
    for p in sorted(SCRIPTS.glob("*.py")):
        s = read(p)
        ctrl = {c for c in s if ord(c) < 32 and c not in "\n\r\t"}
        if ctrl: bad[p.name] = sorted(hex(ord(c)) for c in ctrl)
    assert not bad, f"脚本里有字面控制字符（正则里的 \\b 很可能被写成了退格符）: {bad}"


def test_optional_pattern_matches_what_it_claims():
    m = _ac()
    for s in ("out/pred.npy", "runs/x/output.json", "ckpt/seg_s0.pt", "w/last.pth", "cache/x", "logs/train.log"):
        assert m.OPTIONAL.search(s), s
    assert not m.OPTIONAL.search("frames_256.npy")


def test_regex_literals_are_not_treated_as_paths(tmp_path):
    m = _ac()
    import ast
    src = 'import re, os\nd = "x"\nok = [d for d in ("a",) if os.path.isdir(d) and re.search(r"(label|gts)", d)]\n'
    tree = ast.parse(src)
    lits = set()
    for node in ast.walk(tree):
        seg = ast.get_source_segment(src, node) if isinstance(node, (ast.Call, ast.Compare, ast.BoolOp)) else None
        if seg and m.EXIST.search(seg): lits |= m._str_literals(node)
    assert "(label|gts)" not in lits, lits


def test_write_is_not_counted_as_read():
    m = _ac()
    assert m._is_write('open(os.path.join(out, "tiles.csv"), "w", newline="")')
    assert m._is_write('np.savez(os.path.join(out, "calib.npz"), **d)')
    assert not m._is_write('open(os.path.join(root, "tiles.csv"), encoding="utf-8")')
    assert not m._is_write('np.load(os.path.join(d, "frames_256.npy"))')


def test_producer_script_is_not_flagged(research):
    """一个写出 tiles.csv 的生产脚本 + 用正则筛目录，不该被判 silent-fallback FAIL。"""
    write(research / "code" / "prepare.py",
          'import csv, io, os, re\n'
          'def find(root):\n'
          '    ds = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and re.search(r"(label|gts)", d)]\n'
          '    if not ds: raise FileNotFoundError("no label dir")\n'
          '    return ds\n'
          'def write_index(out, rows):\n'
          '    with io.open(os.path.join(out, "tiles.csv"), "w", encoding="utf-8", newline="") as f:\n'
          '        w = csv.DictWriter(f, fieldnames=["tile_id"]); w.writeheader(); w.writerows(rows)\n')
    import re as _re
    sp = research / "research-state.yaml"
    s = read(sp).replace("  inputs: []", '  inputs: [tiles.csv, frames]')
    s = _re.sub(r"(?m)^  inputs:.*$", "  inputs: [tiles.csv, frames]", s)
    write(sp, s)
    r = run("audit_check.py", cwd=research)
    assert "判一个文件、读另一个文件" not in r.out, r.out


def test_split_files_configured_but_missing_says_so(research):
    import re as _re
    sp = research / "research-state.yaml"
    write(sp, _re.sub(r"(?m)^  split_files:.*$", "  split_files: {train: splits/nope_train.txt, test: splits/nope_test.txt}", read(sp)))
    r = run("audit_check.py", cwd=research)
    assert "已配但文件不存在" in r.out, r.out
    assert "未提供 split_files" not in r.out
