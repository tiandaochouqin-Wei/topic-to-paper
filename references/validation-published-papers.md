# topic-to-paper 关口在七篇已发表顶会顶刊论文上的验证

日期：2026-10-05。目的：已发表论文经过编辑与排版，关口理论上应全绿；每个 FAIL 要么是关口假阳性，要么是真漏网。两种都要分清。
输入：官方 PDF（CVF Open Access、NeurIPS proceedings、IEEE Xplore 开放获取、UCL 机构库接收稿），用 `scripts/pdf_to_md.py` 转为 skill 格式。每条 FAIL 都回到 PDF 原始文本层复核过，不以转换结果为准。

| 论文 | 来源 | 页 | 参考文献 |
|---|---|---|---|
| Depth Anything (Yang et al.) | CVPR 2024 | 11 | 89 |
| DUSt3R (Wang et al.) | CVPR 2024 | 13 | 140 |
| VAR, Visual Autoregressive Modeling (Tian et al.) | NeurIPS 2024 best paper | 27 | 75 |
| CRATE-α, Scaling White-Box Transformers (Yang et al.) | NeurIPS 2024 | 25 | 51 |
| Stormer, weather forecasting (Nguyen et al.) | NeurIPS 2024 | 32 | 50 |
| DeGCN (Myung et al.) | IEEE TIP 2024 | 14 | 61 |
| End-to-End Autonomous Driving (Chen et al.) | IEEE TPAMI 2024 | 20 | 279 |

## 结果

| 关口 | 7 篇汇总 | 判定 |
|---|---|---|
| refs | 有 DOI/arXiv 的 121 条全部解析回标题并匹配；0 条指错 | 全绿。CVF/NeurIPS 参考文献本就极少带 DOI（DUSt3R 140 条只有 4 条），关口在这类稿上覆盖率低是输入问题不是关口问题 |
| floats | 4 篇 PASS；3 篇共 11 张图正文零引用 | **真漏网**，见下 |
| acronyms | 每篇 30–66 条报告，核实后真阳性每篇 0–4 个 | 假阳性率 ≈ 95%，与 InfoFusion 一致 |
| scope | 每篇 24–109 处词命中，其中真正的"首个/最先"主张每篇 0–5 句 | 按设计只列不判 |
| dpi | 5 篇各有 1–2 张图低于 300 dpi | **真漏网**，见下 |
| limits / submission / numbers | 未跑：已发表稿无投稿硬规则、无投稿文件、无结果文件 | 不适用 |

## floats：三篇 NeurIPS 论文共 11 张图从未被正文引用

| 论文 | 图 | 内容 |
|---|---|---|
| VAR | Fig. 1 | 首页 teaser，生成样本 |
| VAR | Fig. 10, 11 | 附录中的样本画廊 |
| CRATE-α | Fig. 2 | 模型单层架构图 |
| Stormer | Fig. 1 | 首页 teaser，5 天预报示例 |
| Stormer | Fig. 14–19 | 附录 C 的逐 lead-time 预报误差图 |

全部在 PDF 原文中用 `Fig(ure|s?\.)\s*(\d+)` 含成组展开复核，题注各一处、引用零处。两篇 CVPR 和两篇 IEEE 论文全部被引用。NeurIPS 没有制作编辑，首页 teaser 图和附录画廊不引用是该社区的常态；Elsevier/IEEE 的制作流程会退回。对本 skill 的目标期刊（Nature 系、Elsevier、IEEE）这条关口照常开。

## dpi：五篇各有一张主图印刷分辨率不足

| 论文 | 图 | 像素宽 | 印刷宽 | dpi |
|---|---|---|---|---|
| Depth Anything | Fig. 4，与 MiDaS 对比 | 1412 | 136 mm | 265 |
| DUSt3R | Fig. 2，网络架构 | 640 | 72 mm | 226 |
| VAR | Fig. 7，缩放律 | 1428 | 140 mm | 260 |
| CRATE-α | Fig. 7，注意力图 | 915 | 138 mm | 168 |
| Stormer | Fig. 11, 12 | 1571 / 1400 | 138 / 126 mm | 289 / 283 |

印刷宽度直接取 PDF 内嵌图像的 bbox，不是估计值。DUSt3R Fig. 2 的 9 个文字 span 是矢量叠加，栅格只是底图，实际影响小；其余四张图的文字在栅格内。两篇 IEEE 论文 24 张栅格图全部 ≥300 dpi，IEEE 制作流程确实查这一条。

## acronyms：真阳性

| 论文 | 缩略语 | 出现 | 情况 |
|---|---|---|---|
| CRATE-α | CRATE | 196 | 摘要首句即用，§3 才展开 |
| CRATE-α 
| ISTA, MSSA, ODL | 15 / 10 / 7 | 公式里先用，段落标题才展开 |
| VAR | GAN | 7 | §2 先用，§6 才展开 |
| Stormer | RMSE | 11 | Fig. 2 轴标签先用，§4 才展开 |
| TPAMI 综述 | AI | 7 | 从未展开，但属"DNA 级"通用词 |
| Depth Anything | RMSE | 3 | 仅表头出现，从未展开 |

其余报告项全是数据集名（KITTI、NTU、COCO）、方法名（DPT、COLMAP、GPT）和表格单元（NA、GT、RW）。结论与 InfoFusion 一致：这条关口必须配项目级白名单，否则噪声淹没信号。

## scope：真正的"首个"主张

DUSt3R "the first holistic end-to-end 3D reconstruction pipeline"、VAR "this is the first time of a GPT-style autoregressive model surpassing diffusion"、Stormer 五句。关口按设计只列行号供人回表，不判对错。七篇里没有一句明显越界，说明顶会作者对这类词的使用是克制的；关口列出的 24–109 行里 90% 以上是 "first stage"、"all datasets" 这类非主张用法，这是设计局限：词表无法区分主张与叙述。

## 对转换器与关口的修改（本次暴露）

pdf_to_md.py（新建）：
- 双栏阅读顺序按块的列号与 y 排序；页眉页脚（期刊名、页码、"Page x of 14"）按位置和文本模式剔除，否则 IEEE 稿每页的 "IEEE TRANSACTIONS ON IMAGE PROCESSING" 会被当成 14 组缩略语。
- 题注判定在块级别做："Fig. 3." 单独成行且前一块句子未结束，是换行断开的引用，不是题注。TPAMI 稿因此一度误报 Fig. 3 孤立。
- NeurIPS 把附录放在参考文献之后；转换时把最后一条参考文献之后的内容还给正文，否则附录里的图全部"不存在"。
- 参考文献标题从 "[n] 作者. 标题. 刊名" 里取第一个不像作者表的句段；此前取第二段会在 "A. B and C. D. Title" 这种格式上取到作者名，CrossRef 比对就会误报。

gate_check.py：
- 题注标签的排除范围从"整行"缩到"标签本身"：题注正文里引用别的图（"(a) same as Fig. 6"）必须算引用。
- "Tab. 7 of the supplementary / in the Appendix" 这类引用前后 40 字符内有 supplement/appendix 字样时降为 WARN，不算悬空引用。
- 引用形式加 `Tab.`（CVF 习惯）。
- 缩略语关口先剥 URL，再加 NA/N-A/TBD 白名单。
- 一行只有 "Fig. 3." 且后面不足 12 字符的不登记为题注。

全部修改后，EAAI 稿与 InfoFusion 稿的 floats 关口回归仍为 PASS。

## 结论

- **refs、floats、dpi 三条关口在已发表论文上没有假阳性**：每条 FAIL 回到 PDF 原文都成立。它们抓到的是 NeurIPS 制作流程本来就不查的东西（孤立图、图分辨率），而 IEEE 的两篇在这两条上全绿，说明关口的判据与专业制作编辑一致。
- **acronyms 关口没有白名单不可用**，这是第二次确认。
- **scope 关口的价值是列清单不是判断**，词表在顶会论文上 90% 以上是叙述性用法。
- 转换器本身花了本次大部分工夫。PDF 文本层不是 skill 的设计输入，这次的七篇是为了验证才走这条路；真实项目的输入是 Markdown 源，不经过这些启发式。
