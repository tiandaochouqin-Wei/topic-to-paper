# 验证轮 15：G5 关口补印刷字号、图类型覆盖、双纵轴（2026-10-15）

起因：tpami_medimg 在 14 道关口全 PASS 的状态下，用户看了一眼就说"图表质量差，不像能发好期刊"。量了成稿：Fig. 4 两个面板缩到半栏后字号 3.5–4 pt，Fig. 3 双纵轴四条线，Fig. 5 十九个点里十八个压在零线上，没有总览图和定性图（cs_journal 样本里 89% / 81% 的论文有）。G5 以前只查 dpi、source_data 和 inspected=yes，而"已目测"看的是放大的 PNG。

## 改了什么

| 项 | 实现 | 判据 |
|---|---|---|
| 印刷字号 | PyMuPDF 读每个 PDF 的文本层，span 字号 × (print_width_mm / 原图宽) | 最小 < `target.min_font_pt`（默认 5）FAIL；< 下限 +1 WARN；无文本层 INFO |
| 双纵轴 | 同一页左右两侧（<15% 与 >85% 页宽）都有旋转 90° 的文字 | WARN |
| 图类型覆盖 | `target.family` → `FAMILY_MUST_TYPES`（cs_journal：overview/qualitative/comparison/ablation；cs_conf 前三；nature 不查）；题注按 `figure_norms.FIGURE_TYPES` 分类；figures.csv issues 列 `no <type>: <理由>` 可豁免 | 缺且未豁免 WARN |

模板 `target.min_font_pt: 5`。测试 5 个（test_g5_print.py）：缩放后 1.75 pt FAIL、原宽 7 pt PASS、双纵轴 WARN、覆盖缺失 WARN 与豁免清零、题注命中清零。

## 在 tpami_medimg 上的实际效果

重画后再跑：Fig. 3 的两个逐标注者面板按 0.33 版心排，字号 4.8 pt → FAIL，按真实宽度重画后 PASS；定性图 26 mm 宽的标签 5.1 pt → WARN，改 7 pt。图类型覆盖报 qualitative / comparison / ablation 未命中——定性图与对比图其实都有，是题注没用规则认得的词（"Which rater the guarantee covers"、"Worst held-out-rater risk ..."）；处理是题注加关键词 + figures.csv 写明消融在 Table II。这说明覆盖检查是启发式，只能 WARN。

## 没解决

- 关口量得出字号，量不出"图好不好看"：图例压数据、点全压在零线、信息密度，仍靠目测。目测的正确做法已写进 P5.md：渲染排版后的页面，不看放大 PNG。
- 配色验证用的是 dataviz 技能的 `validate_palette.js`，没有集成进 G5（需要 node）。
- cs_journal 的 must 列表来自 118 篇样本；Nature 系按主题差异太大，没有 must 列表。
