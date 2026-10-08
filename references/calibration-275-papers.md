# 275 篇已发表论文的关口校准

日期：2026-10-05。语料：用户本地库 `Z:\LDCT\papers`（约 10.6 万篇 PDF，按会议/期刊分目录），固定种子 20261005 分层随机抽 11 个 venue × 25 篇 = 275 篇，含 CVPR、ICML、NeurIPS、IJCV、TIP、TPAMI、MICCAI、Nature Medicine、Nature Communications、Nature BME、Nature Machine Intelligence。
工具：`scripts/calibrate.py`（转换 → 四道离线关口 → 每条 floats FAIL 回 PDF 原文复核）。两轮：第一轮用原关口，第二轮用据此修改后的关口。校准脚本可重跑：`python scripts/calibrate.py <corpus_dir> <out_dir>`。

## 第二轮（修改后）各 venue 结果

| venue | n | 有标识符的参考文献 | 孤立图表 报告→复核 | 篇均 ≥5 次缩略语 | 篇均强主张句 | 有强主张的篇 | <300 dpi 图占比 | 有低 dpi 图的篇 |
|---|---|---|---|---|---|---|---|---|
| CVPR | 25 | 15% | 18→18（10 篇） | 4.8 | 1.6 | 17/25 | 4% | 9/25 |
| ICML | 25 | 15% | 16→16（10 篇） | 3.6 | 1.8 | 18/25 | 9% | 14/25 |
| NeurIPS | 25 | 18% | 54→53（6 篇） | 6.9 | 1.8 | 19/25 | 11% | 9/25 |
| IJCV | 25 | 22% | 6→6（4 篇） | 5.4 | 1.5 | 17/25 | 10% | 6/25 |
| TIP | 25 | 13% | 12→11（6 篇） | 9.2 | 2.3 | 20/25 | 8% | 13/25 |
| TPAMI | 24 | 9% | 25→25（7 篇） | 10.3 | 2.7 | 24/24 | 8% | 13/24 |
| MICCAI | 25 | 16% | 12→11（8 篇） | 2.4 | 0.9 | 15/25 | 2% | 4/25 |
| NatMed | 25 | 6% | 1→0（0 篇） | 4.0 | 0.1 | 2/25 | 3% | 5/25 |
| NatCommun | 25 | 5% | 0→0（0 篇） | 9.1 | 0.1 | 1/25 | 1% | 1/25 |
| NatBME | 25 | 9% | 3→2（2 篇） | 7.8 | 0.2 | 5/25 | 1% | 4/25 |
| NatMI | 25 | 17% | 2→2（2 篇） | 3.2 | 1.1 | 11/25 | 13% | 7/25 |

## 四条结论

**1. 孤立图表关口的判据与制作编辑一致。** 复核后 149/149 条报告全部成立（报告→复核几乎无损），而分布极度偏向无制作编辑的 venue：NeurIPS 6 篇 53 张、CVPR 10 篇、ICML 10 篇；Nature 四刊 100 篇只有 4 张（两张在 HAL 接收稿里）。这条关口在 Nature/Elsevier/IEEE 稿上几乎不会误报，报了就是真的。

**2. dpi 关口原判据有两类系统性假阳性，已修。** 第一轮 Nature 四刊 "有低 dpi 图的篇占比" 高达 80–92%，细查发现 NatCommun 130 张栅格里 90 张落在 295–300 dpi：这是 Nature 排版把 300 dpi 原图按版面缩放后的舍入，不是作者问题。第二类是 ICML 46 张、NatMed 5 张 <150 dpi 的"图"，尺寸 <40 mm 宽或 <15 mm 高，是公式、logo、按钮图标。修改：300 的 1.5% 容差带内降 WARN；小图降 WARN。修后 Nature 四刊的低 dpi 篇占比降到 4–28%，剩下的是真的（NatMed 两篇整页 149 dpi 的扫描图、NatMI 一篇 63 dpi 的小面板）。

**3. 作用域词关口改为"强主张"与"叙述词"两级。** 第一轮每篇列 24–109 行，复核样本里 >90% 是 "first stage"、"all datasets"。新 `SCOPE_STRONG` 只匹配 "the first to/work/…"、"first … survey/benchmark"、"new state-of-the-art"、"outperforms all/every"、"all existing/prior"、"no prior work"、"consistently/significantly outperforms" 等搭配，单独打 CLAIM 行；其余只计数，`--verbose` 才展开。校准后篇均强主张句 CVPR 1.6、NeurIPS 1.8、TPAMI 2.7、Nature 系 0.1–0.2，与直觉一致：CS 顶会作者每篇写一两句 SOTA 主张，Nature 系几乎不写。抽样 14 句 CLAIM 全部是真主张（"outperforms all baselines across all evaluation metrics"、"achieving a new state-of-the-art"）。InfoFusion 稿 Highlights 那句 "First cross-disease survey" 现在能被抓到，EAAI 稿 0 句。

**4. 缩略语关口加了领域规范表。** 从 270 篇统计"同领域 ≥5 篇使用且 ≥70% 从不展开"的词，再用大小写变体过滤掉 PDF 大写标题带来的 OF/ON/METHODS，得到 `references/acronym-norms.csv`：cv 领域 RGB/CLIP/SNE/GPT/CIFAR，ml 领域 GPT/CIFAR/AI，nature 领域 RNA/IL/CA/PMC/GPT/COVID/IFN/EDTA/HLA/CRISPR/TNF/SARS，medimg 领域为空（MICCAI 作者全都展开）。在 state 的 `target.field` 填 cv/ml/medimg/nature 即自动加载。另外发现 11% 的报告是"展开晚于首现"（PSNR、SSIM、MSE、MLP 在表格里先出现、正文才展开），这类在 CS 论文里是常态，关口照报但用户可按领域决定；摘要内未展开单独 FAIL（Elsevier/Springer 硬规则）。

## 转换器修改

- 参考文献切分支持三种格式：`[n]`（CVF/IEEE/NeurIPS）、`n.`（Springer/Nature，含 `\t` 与 `\xa0` 分隔）、作者-年份块（ICML/IJCV）。第一轮 ICML、IJCV、MICCAI、Nature 四刊几乎全部 0 条参考文献，第二轮全部恢复。
- 栅格导出支持 CMYK/Lab/Indexed（转 RGB）与带 alpha 的图，第一轮因此失败的 4 篇第二轮通过。
- 剩 1 篇 TPAMI 转换超时（含数百张小栅格），未处理。

## 没改的

- 参考文献关口没动。有标识符的 1 400 多条 DOI 全部解析回标题且 0 条不符；CS 会议参考文献带 DOI 的只有 5–22%，是输入问题。
- 缩略语关口在 CS 稿上每篇仍报 3–10 个 ≥5 次使用的词，其中数据集名（COCO、KITTI、CIFAR）与方法名（CLIP、GPT、SAM）占多数。规范表能吃掉一部分，项目级 `acronym_ok` 仍然需要。
