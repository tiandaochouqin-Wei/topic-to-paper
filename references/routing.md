# 路由表

本 skill 只编排。下面每一行是"本阶段的某个动作 → 调哪个本地 skill 或工具"。全部在当前会话内调用，不开子代理。

## 外部 skill：必需 / 可选 / 缺失时怎么办

**全部关口只依赖 `scripts/` 和三个 Python 包（pyyaml、pymupdf、pillow）；没有任何外部 skill 是必需的。** 下面各表路由到的外部 skill 都是"有则用，无则 Claude 在本会话内自己做同样的事，产物格式不变"。`t2p.py doctor --skills` 列出本机哪些可见。缺 skill 不是停下来问用户的理由（可问的四种情形见 SKILL.md）。

| 缺失的 skill | Claude 自己怎么做 |
|---|---|
| `academic-paper-reviewer`、`rigor-reviewer` | 本 skill 内置同等流程（2.9.0 起）：[review-seats.md](review-seats.md) 的盲读 + 五席 + 魔鬼代言人 + 复审，口径 [review-rubrics.md](review-rubrics.md)，写 review_log.md 的固定格式；`review_check.py` 照常 |
| `nature-writing`、`academic-intro-writing`、`nature-polishing` | 直接写：骨架 `templates/skeleton-<family>.md`，画像 [venue-profiles.md](venue-profiles.md)，必写清单 `draft_plan.py plan`；G6 / G6b / G6c 照常 |
| `scipilot-figure-skill`、`nature-figure`、`dataviz` | 主结果 / 消融 / seed / 曲线 / 茎叶 / 箱线 / 横条图已由 `make_figure.py` 生成，方法总览图由 `make_architecture.py` 生成；其它数据图先走 `scipilot-figure-skill`（先剖析数据再推荐图型，拦小样本均值柱 / 双 Y 轴 / 截断轴，Nature / IEEE / 中文核心期刊版式，CJK 字体自动配）；输出仍按本 skill 规则：PDF、印刷宽度、同时写 .source.csv，登记 figures.csv |
| `scientific-schematics`、`image2pptx` | 动机图里的「现有做法 vs 本文」框图用 `make_motivation.py schematic`（YAML 规格，毫米坐标，矢量；模板 templates/motivation_scheme.yaml）；完整架构图仍可先用文字框图占位，不阻塞 G5 |
| `nature-response` | 逐条回复表：意见 / 回应 / 改在哪，一条一行，与 review_log.md 的处置对齐 |
| `nature-data` | 数据可用性声明三句：数据在哪（仓库 / 访问条件）、代码在哪、结果文件在哪 |
| `nature-citation`、`citation-management`、`nature-academic-search`、`bgpt-paper-search`、MCP `academic-search` | CrossRef / OpenAlex / arXiv / PubMed 原生 API（`transfer_scan.py`、`lit_scout.py` 已封装常用调用）；`gate_check.py refs` 核 DOI |
| `deep-research`、`scientific-brainstorming`、`hypothesis-generation`、`scientific-critical-thinking` | 不用；P1 的 problem_table / gap_map / transfer_scan 流程本身就是替代 |
| `experimental-design`、`statistical-power`、`statistical-analysis`、`exploratory-data-analysis` | 统计判据按 [venue-norms.md](venue-norms.md)；检验用 scipy / statsmodels 直接写 |
| `arbor`、`0-autoresearch-skill`、`mlflow`、`weights-and-biases`、`swanlab` | 不用也不影响任何关口；run_card + runs/*/log.json 就是实验跟踪 |
| `venue-templates`、`academic-paper`、`docx` | LaTeX / DOCX 排版放到投稿前；关口只看 paper/manuscript.md |
| `nature-paper2ppt` | 投稿后才用，无需替代 |

## P1 SCOUT
| 动作 | 工具 |
|---|---|
| 邻域论文的基线/消融/数据集/指标频次 | `scripts/baseline_miner.py`（输入 literature/pdf/） |
| 问题导向文献表与反复缺口计数（P1 第一产物） | `scripts/problem_table.py recurring\|check`，表模板 templates/problem_table.csv |
| 失败切片：最差切片/集中度/模型知不知道/协变量扫描（P1 有基线代码时、P4 对本文方法） | `scripts/failure_slice.py --pred runs/<run>/preds/<f>.npz` 或 CSV，`--covariates` 接外部协变量 |
| 饱和检查、候选主张逐年计数、本地 PDF 定位 | `scripts/lit_scout.py`（本地 PDF 库的 FTS5 索引，零 token，先于一切联网检索；无本地库则跳过） |
| 领域外近 18 月方法扫描（P1 第二产物） | `scripts/transfer_scan.py recent --query "<问题结构词>"` → transfer_hits.csv；读候选后填 transfer_scan.md；`count --domain` 填域内计数；`check` = G1b |
| 多源检索 | MCP `academic-search.search_papers`（CrossRef/PubMed/arXiv） |
| 解析标识符、取引用 | MCP `academic-search.get_paper_by_id` / `get_citation` |
| MeSH 检索策略 | MCP `academic-search.lookup_mesh`，skill `nature-academic-search` |
| 结构化抽取实验细节 | skill `bgpt-paper-search` |
| 深度综述 | skill `deep-research` lit-review 模式（重，仅在 corpus >100 篇时用） |
| 选题头脑风暴 | skill `scientific-brainstorming` / `hypothesis-generation` |

## P2 FRAME
| 动作 | 工具 |
|---|---|
| 对标目标刊规范 | `references/venue-norms.csv` |
| 消融矩阵草案 | `scripts/ablation_plan.py plan`（读 train.py 开关） |
| G2 机械关口 | `scripts/prereg_check.py` |
| 实验设计与功效 | skill `experimental-design`、`statistical-power` |
| 批判性检查前提 | skill `scientific-critical-thinking` |

## P3–P4 BUILD / EXPERIMENT
| 动作 | 工具 |
|---|---|
| 远程实验包（用户上传跑）：矩阵核对 / 生成包 / 结果回表 | `scripts/bundle.py check \| make \| tables`，配置在 state.bundle |
| 消融分辨率与符号核对 | `scripts/ablation_plan.py resolve` |
| 反常分诊（口径→数据→泄漏→实现→真发现） | `references/anomaly-triage.md`，记录格式 `templates/findings.md` |
| 领域库 | 按领域：`pydicom` `scanpy` `transformers` `pytorch-lightning` 等 |
| 自主优化循环 | skill `arbor`（HTR）或 `0-autoresearch-skill` 内循环；只在用户要求长时自治时用 |
| 实验跟踪 | skill `mlflow` / `weights-and-biases` / `swanlab` |
| 统计检验 | skill `statistical-analysis`、`statsmodels` |
| 探索性分析 | skill `exploratory-data-analysis` |

## P5 FIGURES
| 动作 | 工具 |
|---|---|
| 主结果图 / 消融 Δ 图 / seed 图（从 results 表生成，登记 figures.csv） | `scripts/make_figure.py main \| ablation \| seeds \| curves \| stems \| box \| hbar` |
| 数据图 | 先试 `make_figure.py main\|ablation\|seeds\|curves\|stems\|box\|hbar`、`make_comparison.py grid`（框/热图/掩码叠加）、`make_architecture.py`（方法总览图）；不够再用 `scipilot-figure-skill`（Python，含中文期刊版式）；要 R 或 Nature 系 QA 清单时用 `nature-figure`（先问 Python/R） |
| 定性对比网格（检测/分割结果，Origin+各方法×样本，inset 放大） | `scripts/make_comparison.py grid`；行数 = 样本数，`--cols` 决定每行几个方法（TGRS 常见 12），超出自动换行并在每组下标方法名 |
| 动机图 | 按证据选形式（[motivation-figures.md](motivation-figures.md)）：`make_motivation.py condition / paired / tradeoff / schematic / strip / radar`，失败案例 `make_comparison.py grid` |
| 示意图/架构图 | skill `scientific-schematics`、`academic-plotting` |
| 配色与可读性 | skill `dataviz` |
| 图 → 可编辑 PPT | skill `image2pptx` |
| 组合图：每面板一个 PDF，生成 subfigure/subfloat 块 | `scripts/latex_check.py figure --panels a.pdf,b.pdf --labels ... --caption ... --label fig:x` → paper/latex/figs/fig_x.tex |
| 目标刊 / 家族 / 主题通常放哪些图（选图单依据） | `references/figure-norms.md`（`scripts/figure_norms.py` 对本地论文库抽样、按题注归类）；重算：`figure_norms.py sample --papers <库>` 再 `figure_norms.py report` |

## P6 WRITE
| 动作 | 工具 |
|---|---|
| 按稿件家族取写作骨架（P0 定 target.family） | `templates/skeleton-cs_conf.md` / `skeleton-cs_journal.md` / `skeleton-nature.md`；规则与数据 `references/venue-profiles.md` |
| 稿件形状 vs 家族画像 = G6c | `scripts/shape_check.py`（章节顺序、摘要长度、贡献列表/Here-we-show、句式小标题、公式位置、禁用词、Discussion 占比、统计句占比） |
| 各节必写清单（生成 / 核对 = G6b） | `scripts/draft_plan.py plan \| check` |
| LaTeX 稿进关口 | `scripts/tex_to_md.py paper/latex/main.tex . --bib paper/refs.bib`（展开 \input，合并 figures.csv），再 `t2p.py check` |
| 期刊 LaTeX 模板骨架 / 版心实测 / 投稿形态关口 = G6d | `scripts/latex_check.py skeleton --venue "<刊>"`、`widths --tex paper/latex/main.tex`、`check`；模板知识表 `references/latex-templates.csv` |
| SOTA 对比表（单数据集，分 CNN/Transformer 组，Params/FLOPs，红最优/蓝次优，ours 加粗） | `scripts/make_comparison.py sota --csv results/main.csv --group-col family --extra Params,FLOPs --ours X --cite-col ref --numbers` |
| 多数据集并排对比表 | `scripts/make_comparison.py multi --datasets A,B,C --dataset-col dataset ...` |
| 消融表（✓/× 组件列，Group 编号，全 ✓ 行加粗） | `scripts/make_comparison.py ablation --components C1,C2,C3 --ablation-plain` |
| Seed 稳定性表（逐 seed + Mean±Std） | `scripts/make_comparison.py seeds --csv results/seeds.csv --metrics AP50 --decimals 4` |
| 表格数字进 G6 | 以上均加 `--numbers`，每格写进 paper/numbers.csv 指向 `<out>.source.csv` |
| 引言 | skill `academic-intro-writing` |
| 各节起草 | skill `nature-writing` |
| 润色 | skill `nature-polishing` |
| 引用管理 | skill `nature-citation`、`citation-management` |
| 期刊模板 | skill `venue-templates` |
| LaTeX/DOCX 输出 | skill `academic-paper` format-convert；DOCX 用 `docx` |

## P7 REVIEW
| 动作 | 工具 |
|---|---|
| 审稿闭环核对 = G7 | `scripts/review_check.py` |
| 模拟审稿 | 内置流程 [review-seats.md](review-seats.md)（装有 `academic-paper-reviewer` 时可用其 full → re-review） |
| 严谨性审查 | skill `rigor-reviewer` |
| 审稿回复 | skill `nature-response` |

## P8 SUBMIT
| 动作 | 工具 |
|---|---|
| 数据可用性声明 | skill `nature-data` |
| 投稿关口 | `scripts/gate_check.py submission` |
| 论文转 PPT | skill `nature-paper2ppt`（投稿后） |

## 不用的
- `academic-pipeline`：功能重叠，且每阶段要用户确认，不适合自治运行。
- `autonomous-research-lab-complete-personalized-skill`：目标是 CCF-A 格式包，脚本与本 skill 的 gate 互相冲突。
- Agent / Workflow 工具：默认不开。token 审计显示子代理工作流是支出主因之一。

## 综述分支 S0–S6
| 动作 | 工具 |
|---|---|
| 已有综述检索 | `scripts/lit_scout.py scout '<主题> survey OR review'` + OpenAlex |
| 系统检索（PubMed 按年切片 / arXiv / OpenAlex）与三源去重，写 search_log.json + candidates.csv | `scripts/survey_search.py search --query "<q>" [--pubmed-query/--arxiv-query/--openalex-query] --since 2015 [--abstracts]`（原项目内 lit/search_literature.py 的通用版） |
| 滚雪球 | `scripts/survey_search.py snowball --dois <种子 DOI> [--direction both\|references\|citations]`（Semantic Scholar 一层） |
| 规则预筛 / PRISMA 计数 / DOI 修复 | `scripts/survey_search.py triage --include-any ... --exclude ... --since ...`（写 screening_sheet.csv，不覆盖 Claude 已决的行，更新 prisma_flow.json）；`fix-dois`（efetch 只取 PubmedData 的 DOI） |
| 检索验证 | `literature/seed_studies.csv` 金标准种子集（G-S1 算召回）；滚雪球每轮在 search_log 记 new_included（饱和判定） |
| 标题级与摘要级筛选 | Claude 本会话内按批做，写回 screening_sheet.csv；拿不准或调用失败写 pending，不默认 exclude |
| 排除复核 | `scripts/survey_tables.py qc-sample --n 100 --near-miss "<词|词>;<词|词>"`（无原决定的盲复核样本） |
| 编码 | Claude 按 codebook 本会话内按批做，写 coded.csv；κ 样本盲编，`scripts/survey_tables.py kappa --b <第二份>` 算 κ / PABAK |
| 汇总表 / 覆盖矩阵 / 特征表 / 已有综述对比表 | `scripts/survey_tables.py summary`（coding/tables.yaml）、`crosstab`、`characteristics`、`prior` |
| PRISMA 流程图 / 时间线 / 覆盖热图 / 证据气泡图 / 偏倚风险图 | `scripts/survey_figure.py prisma | timeline | coverage | bubble | rob` |
| 跨研究张力清单 | Claude 写 coding/tensions.csv（模板 templates/tensions.csv） |
| G-S0 … G-S5 | `scripts/survey_check.py scope | search | protocol | coding | tables | claims`（claims 含 writing） |
| 写作 | 论点段 `nature-writing`，分类树与概念图 `nature-figure`，润色 `nature-polishing` |
| 审稿 | `academic-paper-reviewer` full，席位换成领域编辑/方法学/领域专家/读者/魔鬼代言人 |
| 投稿包 | 同 P8 |
