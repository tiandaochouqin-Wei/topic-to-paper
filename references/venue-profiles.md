# 三类稿件的写法画像（数据来自 275 篇已发表论文，2026-10-09）

来源：`scripts/venue_shape.py` + `scripts/venue_norms.py` 对 `Z:\LDCT\papers` 分层抽样的 11 个 venue × 25 篇（种子 20261005）提取；逐篇原始值 `venue-shape-per-paper.csv`、`venue-norms-per-paper.csv`。数值为中位数或占比。三个家族：**cs_conf**（CVPR/NeurIPS/ICML/MICCAI，n=100）、**cs_journal**（TPAMI/TIP/IJCV，n=75；EAAI/TGRS 等 Elsevier/IEEE 期刊归此类）、**nature**（Nat Commun/Med/BME/MI，n=98；Science 系同）。

## 三个家族的硬差异

| 特征 | cs_conf | cs_journal | nature | 对写作的含义 |
|---|---|---|---|---|
| 页数 / 正文词 | 12 页 / 3 600 词 | 16 页 / 4 650 词 | 19 页 / 5 000 词（含 Methods） | 会议是"一个主张一组实验"，期刊可以展开，Nature 正文 ≤ 5 000 含 Methods 但 Methods 放后面不占阅读主线 |
| 章节顺序 | Intro → Related → Method → Experiments → Conclusion（75% 有 Related Work） | 同上，Related 53%，更多 Problem/Preliminaries 节 | **Results → Discussion → Methods**（96% Methods 在 Results 之后），无 Related Work（5%）、无 Conclusion（11%） | Nature 稿不写 Related Work 和 Conclusion；相关工作融进引言 3–4 段，结论融进 Discussion 末段 |
| 引言 | 占正文 20%；44% 有贡献条目列表（3–4 条）；34% 首页有 teaser 图 | 占 17%；29% 有贡献列表；36% 首页 teaser | 占 12%（约 600 词）；**0% 贡献列表**；0% teaser | Nature 引言不列 "our contributions are"，最后一段用一句话说"Here we show …" |
| 方法 | 占 40%；公式中位 6 | 占 38%；公式 14（TPAMI 22） | 占 31% 但放最后；**公式 0** | Nature 正文不放公式（放 Methods 或 SI）；CS 期刊审稿人期待推导 |
| 结果 | 占 17%；小标题是名词短语（"4.2 Ablation Study"） | 占 12% | 占 44%；**小标题是完整句子**（中位 4 个，如 "SRF conditioning transfers zero-shot to an unseen sensor"） | Nature 的 Results 小标题就是主张，读小标题等于读摘要 |
| 讨论 | 17% 有，占 4% | 13% 有 | **83% 有，占 18%**；局限写在 Discussion 里（18% 有独立 Limitations） | Nature 的 Discussion 是第二长的节，必须有"与前人结论的关系 + 机制解释 + 局限 + 推广边界" |
| 消融 | 63% 有消融（19% 独立节） | 78% 有 | **10%** | Nature 稿的"消融"写成 "control experiments" 或在 SI；正文不出现 ablation 一词也正常 |
| 统计 | std 41%，seeds 3%，CI 3%，p 5% | std 41%，CI 1%，p 4% | std 74%，**CI 30%，p 63%**，seeds 2% | Nature 每个比较给 n、检验名、p 或 CI；CS 给 mean±std 和 seeds |
| 补充材料 | 73%（附录） | 27% | 88%（Supplementary Information / Extended Data） | Nature 的 SI 是正文的一部分，Methods 细节、全部消融、额外图都放那 |
| "state-of-the-art" | 73% | 78% | **20%** | Nature 稿用这个词是信号错位（scope 关口单列） |
| "we" 每千词 | 17 | 19（TIP 44） | **9**（Nat Med 5） | Nature 多用被动与 "Here we …" 开头的少数几句 |
| 参考文献 | 38 | 68 | 44（上限常 70） | CS 期刊引用最多；Nature 近三年文献占 41%，CS 会议 56% |
| 代码链接 | 55% | 68% | 45% | — |

## 各 venue 原始行（中位数 / 占比）

| venue | 页 | 正文词 | 摘要词 | 引言占比 | 方法占比 | 结果占比 | 讨论节 | 讨论占比 | Methods 在后 | 贡献列表 | 结果句式小标题 | 公式 | we/千词 | SOTA |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CVPR | 10 | 3942 | 180 | 18% | 34% | 15% | 8% | 4% | 39%* | 44% | 2 | 7 | 17 | 88% |
| NeurIPS | 24 | 4261 | 176 | 17% | 25% | 18% | 32% | 2% | 39%* | 48% | 1 | 8 | 18 | 68% |
| ICML | 19 | 4410 | 175 | 22% | 42% | 17% | 20% | 6% | 19% | 44% | 1 | 6 | 15 | 68% |
| MICCAI | 11 | 2194 | 162 | 25% | 44% | 17% | 8% | 15% | 8% | 40% | 1 | 5 | 17 | 80% |
| TPAMI | 16 | 4970 | 308 | 18% | 33% | 10% | 8% | 4% | 20% | 32% | 0 | 22 | 19 | 92% |
| TIP | 14 | 2303 | 242 | 16% | 100%† | 13% | 4% | — | 0% | 12% | 0 | 15 | 44 | 76% |
| IJCV | 18 | 6990 | 234 | 16% | 38% | 16% | 28% | 7% | 50%* | 44% | 3 | 8 | 15 | 72% |
| Nat Commun | 15 | 6556 | 159 | 22% | 35% | 41% | 100% | 17% | 100% | 0% | 5 | 0 | 8 | 4% |
| Nat Med | 23 | 2724 | — | — | — | 40% | 76% | 51% | 100% | 0% | 1 | 0 | 5 | 8% |
| Nat BME | 29 | 7748 | 178 | 8% | 36% | 48% | 88% | 16% | 100% | 0% | 6 | 0 | 10 | 25% |
| Nat MI | 15 | 4688 | 280 | 25% | 32% | 56% | 67% | 14% | 81% | 0% | 3 | 1 | 15 | 54% |

\* CS 稿的 "Methods 在后" 是检测器把附录里的 "Implementation details" 当成第二个 Method 节；真实值 ≈0。† TIP 双栏 PDF 的文本层把全文并进一个节，占比不可用。Nat Med 25 篇里 Perspective/Review 混入，摘要与引言词数失真。章节序列检测对 Nature 稿 21/25 命中 results>discussion>method，对 CS 稿命中率 30–50%（双栏标题被拆行），所以**占比用家族中位数，不用单 venue**。

## 写作规则（draft_plan 按家族加载，`profile` 块）

### cs_conf（CVPR / NeurIPS / ICML / ICLR / AAAI / MICCAI）
- 章节：Abstract, 1 Introduction, 2 Related Work, 3 Method（或 Preliminaries + Method）, 4 Experiments（含 4.x Ablation）, 5 Conclusion；NeurIPS/ICML 加 Limitations（72%/36%）与 Broader Impact 段。
- 引言 ≤ 20% 正文，末尾贡献条目 3–4 条，每条对应 claims.csv 一行且含数字；首页 teaser 图（CVPR 76%）。
- 方法节有公式（≥ 3 个编号式），每个有消融的组件一个小节。
- 实验：数据集/指标/实现细节/与 SOTA 比较/消融/分析 五段；mean±std 或 seeds；"state-of-the-art" 可用但 scope 关口照查作用域。
- 篇幅：主文 8–10 页（CVPR）/ 9 页 + 附录（NeurIPS），附录放完整表与超参。

### cs_journal（TPAMI / TIP / IJCV / EAAI / TGRS / Information Fusion / Pattern Recognition）
- 章节：同 cs_conf，但 Related Work 可展开成 2.1–2.4，方法节可有 Problem Formulation 独立节，实验节 10 个以上小节常见（EAAI 稿 5.1–5.11）；Discussion / Limitations 子节（36%）；Conclusion 必有。
- 摘要 200–250 词（Elsevier 常限 250），结构化不强制；Highlights（Elsevier）3–5 条 ≤ 85 字符另文件。
- 公式多（中位 14），推导放正文不放附录；参考文献 60–80 条，经典与近三年并重。
- 篇幅：14–18 页双栏或 25–40 页单栏 preprint；补充材料少（27%），所有消融进正文。

### nature（Nature / Science 及子刊：Nat Commun / Nat Med / Nat BME / Nat MI / Sci Adv）
- 章节顺序固定：Abstract（≤150 词，一段，无小标题，无引用）→ Introduction（无标题，3–5 段，≤ 600 词，最后一段 "Here we show/report …"）→ **Results**（小标题是完整句子主张，中位 4–6 个）→ **Discussion**（与前人结论的关系、机制、局限、推广边界、下一步）→ **Methods**（放最后，可 ≥ 1 500 词，不计入主文字数上限时按刊）→ Data availability / Code availability / References / Acknowledgements / Author contributions / Competing interests。
- **不写** Related Work、Conclusion、贡献条目列表、"state-of-the-art"、正文公式（放 Methods 或 SI）、"ablation" 一词（写 control experiments）。
- 每个比较句给统计：n、检验、p 值或 95% CI，效应量带单位；图例（legend）自成一体，说明 n、误差棒含义、检验。
- 显示项 ≤ 6–8（图 + 表），其余 Extended Data / Supplementary Information；主文引用 SI 用 "Supplementary Fig. 1"。
- 参考文献 ≤ 70（Nat Commun 常 ≤ 70，Nature 主刊 ≤ 50），近三年 ~40%，经典必引。
- "we" 每千词 ≤ 10；多用 "Here we"、被动与名词化；标题是陈述句或名词短语不带冒号的方法名。

## 三类之间迁移时最常犯的错（供 G6c 检查）
1. CS 稿投 Nature：保留 Related Work / Conclusion / 贡献列表 / 公式 / "state-of-the-art" / 名词短语小标题。五项都是机械可查的。
2. Nature 稿投 CS：没有消融、没有 mean±std/seeds、Methods 在最后、无 Related Work。
3. 会议稿扩期刊：引言和方法原样、只加实验；期刊审稿人要看到 Related Work 展开、Problem Formulation、Discussion/Limitations。
