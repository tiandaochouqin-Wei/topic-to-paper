# -*- coding: utf-8 -*-
"""G2 section-length rule must work for a Chinese preregistration.

Found 2026-10-11 on a real remote-sensing project: §1 hypothesis and §4 inclusion_window were each several hundred
Chinese characters long, but the check was `len(t.split()) < 15` — Chinese prose has almost no spaces, so both
sections were reported as 缺少或过短 on a complete prereg. The templates shipped with the skill are Chinese, so this
hit the first Chinese-language prereg written with the skill.
"""
import importlib.util

from conftest import SCRIPTS, edit, lock, read, run, write


def _pc():
    spec = importlib.util.spec_from_file_location("prereg_check", SCRIPTS / "prereg_check.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_long_chinese_section_is_not_too_short():
    m = _pc()
    zh = ("纳入统计的像元是有效类别标签且非 ignore 的全部像元，不按置信度筛选，不按边界距离筛选，也不按类别频次筛选，"
          "跨数据集相同；可交换性单元是瓦片而不是像元，校准集与测试集按地理区块划分以避免空间自相关泄漏。")
    assert len(zh.split()) < 15                      # whitespace splitting alone still sees "a few words"
    assert not m.too_short(zh)


def test_short_chinese_stub_is_still_too_short():
    m = _pc()
    assert m.too_short("名称、公式、实现文件与函数名。")
    assert m.too_short("")


def test_english_rule_unchanged():
    m = _pc()
    assert m.too_short("Too short to count as a section.")
    assert not m.too_short("This section states the metric, the denominator, the implementation file and the function "
                           "name, and lists the secondary metrics that do not enter the success criterion at all.")


def test_table_still_counts_as_content():
    m = _pc()
    assert not m.too_short("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |")


def test_chinese_prereg_passes_the_gate(research):
    """A minimal Chinese prereg built on the fixture's own state must pass G2 (it used to FAIL on two sections)."""
    zh = read(SCRIPTS.parent / "templates" / "prereg.md")
    p = research / "prereg.md"
    body = read(p)
    # translate the two sections the bug hit into Chinese prose of the same meaning, keep everything else
    edit(p, "contact-window: only samples with |F| ≥ 0.1 N enter the statistics; the window is the same across datasets, "
            "and every table header carries the contact-window label so the convention is visible.",
         "contact-window：只有 |F| ≥ 0.1 N 的样本进入统计，这个窗口跨数据集相同，并且每张表的表头都标注 contact-window 口径，"
         "以便读者看到纳入窗口；不按置信度筛选，不按时间段筛选，也不做任何逐数据集的重新定义。")
    lock(research, "prereg.md", "prereg_sha256")
    r = run("prereg_check.py", cwd=research)
    assert "inclusion_window" not in r.out.replace("inclusion_window 未", ""), r.out
    assert r.fails == 0, r.out
    assert zh  # the shipped template is Chinese, which is why this path matters
