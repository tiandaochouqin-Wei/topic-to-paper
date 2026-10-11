# -*- coding: utf-8 -*-
"""实验包的路径约定：entry/eval/post/env 相对 code_dir，远程路径里的 ~ 要在服务器上展开。

2026-10-11 真项目 P3 实测：state.bundle 写成 `entry: "python code/train.py …"`，而 run_one.sh 先 cd 进 code/，
于是命令变成 `python code/code/train.py`，README 也写出 `pip install -r code/code/requirements.txt`，
而 check_env.py 拿着字面 "~/rs_calib/data/potsdam" 去 os.path.isdir()，数据在也永远报 MISS。
"""
import re

import yaml

from conftest import SKILL, edit, read, run, write


def _set_bundle(project, **kw):
    """只改 bundle: 块里的键。注意 project: 块里也有 entry:，整文件 count=1 会打中它。"""
    p = project / "research-state.yaml"
    s = read(p)
    m = re.search(r"(?ms)^bundle:.*?(?=^[a-zA-Z_])", s)
    assert m, "fixture 缺 bundle: 段"
    blk = m.group(0)
    for k, v in kw.items():
        blk2, n = re.subn(rf'(?m)^(  {k}:).*$', lambda mm: f"{mm.group(1)} {v}", blk, count=1)
        assert n == 1, k
        blk = blk2
    write(p, s[:m.start()] + blk + s[m.end():])


def test_entry_with_code_prefix_fails(research):
    _set_bundle(research, entry='"python code/train.py --exp {run} {args}"')
    r = run("bundle.py", "check", cwd=research)
    assert r.fails >= 1 and "code/code" in r.out, r.out


def test_env_with_code_prefix_fails(research):
    _set_bundle(research, env="code/requirements.txt")
    r = run("bundle.py", "check", cwd=research)
    assert r.fails >= 1 and "env" in r.out, r.out


def test_clean_relative_paths_pass(research):
    r = run("bundle.py", "check", cwd=research)
    assert "paths" not in r.out or r.fails == 0, r.out


def test_entry_must_name_the_run(research):
    _set_bundle(research, entry='"python train.py --exp fixed {args}"')
    r = run("bundle.py", "check", cwd=research)
    assert r.fails >= 1 and "{run}" in r.out


def test_check_env_expands_tilde_and_vars(research, tmp_path):
    """生成的 check_env.py 必须在服务器上展开 ~ 与 $VAR，否则数据存在也报 MISS。"""
    p = research / "research-state.yaml"
    s = read(p)
    s = re.sub(r"(?m)^(    - \{name: E1, remote:)[^,]*", r"\1 ~/nonexistent_home_dir_xyz", s)
    write(p, s)
    assert run("bundle.py", "make", "--out", "bundle", cwd=research).returncode == 0
    chk = read(research / "bundle" / "check_env.py")
    assert "expanduser" in chk and "expandvars" in chk, chk[:400]
    out = run("bundle.py", "make", "--out", "bundle2", cwd=research)
    r1 = read(research / "bundle2" / "run_one.sh")
    assert "${HOME}/nonexistent_home_dir_xyz" in r1 and '"~/' not in r1, r1[:600]


def test_readme_does_not_double_the_code_dir(research):
    assert run("bundle.py", "make", "--out", "bundle", cwd=research).returncode == 0
    rd = read(research / "bundle" / "README.md")
    assert "code/code/" not in rd, rd[:600]


def test_ref_must_set_every_critical_param_explicitly(research):
    """2026-10-11 全新项目端到端：ref 只写 --model ours，train.py 的 --beta 默认 0，本文方法按基线配置跑完了全部 seeds，G3 放行。"""
    _set_bundle_matrix(research, 'ref: {name: ours, args: "--model ours"}')
    r = run("bundle.py", "check", cwd=research)
    assert r.fails >= 1 and "beta" in r.out and "显式" in r.out, r.out


def test_ref_critical_param_zero_fails(research):
    _set_bundle_matrix(research, 'ref: {name: ours, args: "--model ours --beta 0 --alpha 0.5"}')
    r = run("bundle.py", "check", cwd=research)
    assert r.fails >= 1 and "为 0" in r.out, r.out


def test_ablation_relying_on_default_fails(research):
    _set_bundle_matrix(research, 'ablations: {no_dom: "--model ours --alpha 0.5", no_cons: "--model ours --beta 0.1 --alpha 0"}')
    r = run("bundle.py", "check", cwd=research)
    assert r.fails >= 1 and "no_dom" in r.out and "beta" in r.out, r.out


def _set_bundle_matrix(project, line):
    """replace the matrix line that starts with the same key (ref: / ablations: / baselines:)"""
    p = project / "research-state.yaml"; s = read(p)
    key = line.split(":", 1)[0]
    s2, n = re.subn(rf"(?m)^    {key}: .*$", "    " + line, s, count=1)
    assert n == 1, key
    write(p, s2)
