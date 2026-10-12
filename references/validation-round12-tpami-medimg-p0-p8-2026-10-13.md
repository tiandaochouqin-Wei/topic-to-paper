# 验证轮 12：tpami_medimg 真项目 P0→P8 全程（2026-10-12 → 10-13）

起因：用户要求"用这个 skill 做一篇医学图像处理论文，投 TPAMI"，选了全新选题从 P0 起。两天内走完 P0→P8，G0–G8 全 PASS。这是 skill 第一次在一个从零开始的研究项目上跑通全部九站（验证轮 11 是 P1b→P5）。

## 走了什么

| 站 | 做了什么 | 关口结果 |
|---|---|---|
| P0 | TPAMI 规则（IEEE CS 指南；CSDL 专页渲染为空，记入待办）；IEEEtran 骨架 | G0 PASS |
| P1 | 本地索引 + OpenAlex/arXiv 315 条命中；16 篇问题表；gap_map 三候选（A 选定，B 是作者另一条线，C 不可及）；transfer_scan 8 候选 T1 选定；refs.bib 26 条全解析 | G1 G1b PASS |
| P2 | §0 对照先做（固定共形集只换校准标注者：prostate 留出者 0.129 vs 同标注者 0.061）；prereg 八节 + 三条失败分支；锁 | G2 PASS |
| P3 | code/rec（MedSAM 冻结预测器、9 种校准、整掩膜伪标注者）、audits 两个泄漏开关 + 三个关键超参证据列 | G3 PASS |
| P4 | 62 run（4 任务 × 9 方法 + 5 消融 + 3 种子 + 5 δ + 9 LIDC）；findings F1–F5；三条预注册失败分支中两条适用 | G4 PASS |
| P5 | 6 个面板 PDF + source.csv，目测登记 | G5 PASS |
| P6 | IEEEtran 稿 9 页、4 表 5 图、numbers.csv 159 条、claims C1–C10 | G6 G6b G6c G6d G6e PASS |
| P7 | 五席 16 条（5 major），全部回结果文件复核；Re-review 关闭 | G7 PASS |
| P8 | title_page / cover_letter / highlights / blind（单盲 n/a）/ supplementary / checklist | G8 PASS |

## 关口抓到的真问题（项目侧）

1. **G4 results_check + findings 纪律抓到"方法 = 基线"**：rec_quantile 在 K ≤ 6 时与 mondrian_max 逐格相同，是 Proposition 的数学事实不是 bug（F3）。prereg §8 第二分支预写了这种情形，论文按分支写成"理论 + 不可能性 + 审计"，没有事后改判据。
2. **G6 numbers 抓到两处不可溯源的句子**（P7 R1 席复核）："r3 在 93% 的划分中被漏盖"写进了 MedSAM 主结果段，但 eval.json 只存 per_split_worst，93% 来自 §0 平滑掩膜对照；"三个种子最多变动 0.003"与 seeds.csv 的 0.006 极差不符。两处都改成可溯源的句子。
3. **F5：LIDC-IDRI 的"四位放射科医生"不是持久身份**。pylidc 根本不存 radiologist 字段；下载 TCIA 的 XML 核对 servicingRadiologistID：563 次扫描中 437 次四列全为 anon，其余数值 ID 逐扫描唯一。prereg §4 按"四位医生"写的第二模态复现不成立；按理论它变成对照（可交换列 → 单标注者保证直接转移，实测差距 0.009 vs prostate 0.068）。登记 convention_changes 第 5 条，不改锁。**教训**：多标注者数据集的"标注者列"在进 prereg 前要核一次身份是否跨样本一致。

## skill 侧修掉的（本轮 1 个提交，257 + 3 测试全绿）

| 症状 | 根因 | 修 |
|---|---|---|
| G6 numbers 报 "Table 2 的 0.62 未登记" | tex_to_md 的 tabular 正则 `(?:\{[^}]*\})+` 遇到 `p{0.62\columnwidth}` 的嵌套花括号，把列规格剩下的 `0.62\columnwidth}cc@{}}` 当成表体第一行 | `tabular_body()` 用 balanced() 消费 preamble（tabular* 两个组） |
| G6b RES61 要 "-37%" 但正文 `$-37$\%` 不可见 | numbers 关口剥掉 `$...$`；纯数字的 inline math 是排版习惯不是公式 | tex_to_md 把 `$-37$` 解包成 `-37` 再写 manuscript.md |
| RES61 的"约 -37%"本身算错：seed-0 是 -35% | draft_plan 对 main.csv 全表按方法取均值，而主表里只有三种方法有 seed 1/2 行，均值被种子行拉偏；同时 rec_mean 的平凡集风险 0.0 若进了候选会成为"最强基线" | 只取第一个 seed 切片；lower-is-better 指标恒为 0 的方法不算最强基线 |

验证：三个新测试（嵌套 preamble + 纯数字 math；种子切片；零风险基线）；全套 260 通过。

## 没解决、要记住的

- `gate_check.py numbers` 对 `$-35$\%` 这类写法仍依赖 tex_to_md 解包；直接写 markdown 稿的人若把数字放进 `$...$` 还是会隐身——写作细则（P6.md）已有"数字写在数学模式外"的规则，本轮不再加关口。
- 多标注者数据集的标注者身份核对没有脚本化（本轮是项目内 `code/lidc_xml_ids.py`）；是否值得进 P2 细则作为一条检查项，等第二个多标注者项目再定。
- TPAMI 专页仍未能抓到（CSDL 动态渲染），guide.txt 来自 IEEE CS 通用指南；P0 细则里的 curl 对这类站点无效，用户投稿前要手工核。
