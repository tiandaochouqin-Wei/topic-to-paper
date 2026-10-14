# 验证轮 16：G5 图表数量下限（2026-10-16，来自 med-world-model）

## 触发

med-world-model 稿（NeurIPS 2027 目标）第一版用 ml-paper-writing 写成 1 图 6 表，用户两次反馈「图太少表太少」。
把该项目接到 topic-to-paper 的 results/、figures.csv、research-state.yaml 上跑 G5：**ALL PASS**——
矢量、印刷字号、cs_conf 三类图类型覆盖全过。关口查的是「有没有某类图」和「图印出来清不清楚」，
从没查过「够不够」，而 figure-norms.md 里早已统计了每个刊的图/篇、表/篇。

## 改动

| 位置 | 内容 |
|---|---|
| `scripts/gate_check.py` | `_norm_floor(venue, family, col)`：从 `references/figure-norms-per-paper.csv` 取目标 venue（样本 <10 篇或没有则退到 family）的 n_fig / n_tab 下四分位；`_dpi_count(a)`：正文（非 S 编号）图、表题注数低于下四分位 → WARN；`target.figure_count_waiver` 非空 → INFO；venue 和 family 都不在规范表里 → 静默。挂在 `gate_dpi` 末尾，`_dpi_coverage` 之后 |
| `templates/research-state.yaml` | `target.figure_count_waiver: ""` |
| `references/gates.md` | G5 新增「图表数量」一段 |
| `references/phases/P5.md` | 「图表够不够」一段：下四分位底线示例（NeurIPS 4 图 2 表、CVPR 4/3、TPAMI 6 图、NatCommun 6 图），第一版就配足 |
| `references/lessons.md` | 一行：关口全绿但只有 1 图 6 表 |
| `tests/test_g5_count.py` | 5 个测试：低于下限 WARN 不 FAIL、豁免降 INFO、够数 PASS、未知 venue 退到 family、无 venue/family 静默 |

下四分位而不是中位数：中位数会把一半已发表论文判成不够；下四分位是「四分之三的同刊论文都至少有这么多」，WARN 的措辞也这么写。

## 在真项目上

med-world-model v0.5（12 图 12 表）：`[PASS] 正文 12 图 12 表，不低于 NeurIPS 已发表论文的下四分位`。
把 manuscript.md 回退到第一版的题注数（1 图 6 表）：`[WARN] 图 1 张 < venue NeurIPS 四分之三的论文有的 4 张（40 篇样本）`。

## 教训

- 测试里改 research-state.yaml 的值要走 yaml 往返，不要正则替换：`venue: ""` 用正则写回去变成带引号的字符串 `'""'`，yaml 读出来是两个双引号而非空。
- 规范表里有数据但关口不用，等于没有。figure-norms.md 的「图/篇」列从验证轮 7 就在，到验证轮 16 才进关口。

270 tests pass（6 e2e deselected）。未 push。
