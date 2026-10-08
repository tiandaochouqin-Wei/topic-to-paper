# 路由表

本 skill 只编排。下面每一行是"本阶段的某个动作 → 调哪个本地 skill 或工具"。全部在当前会话内调用，不开子代理。

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
| 主结果图 / 消融 Δ 图 / seed 图（从 results 表生成，登记 figures.csv） | `scripts/make_figure.py main \| ablation \| seeds` |
| 数据图 | skill `nature-figure`（先问 Python/R）或 `cs-experiment-figure-studio` |
| 定性对比网格（检测/分割结果，Origin+各方法×样本，inset 放大） | `scripts/make_comparison.py grid`；行数 = 样本数，`--cols` 决定每行几个方法（TGRS 常见 12），超出自动换行并在每组下标方法名 |
| 示意图/架构图 | skill `scientific-schematics`、`academic-plotting` |
| 配色与可读性 | skill `dataviz` |
| 图 → 可编辑 PPT | skill `image2pptx` |

## P6 WRITE
| 动作 | 工具 |
|---|---|
| 按稿件家族取写作骨架（P0 定 target.family） | `templates/skeleton-cs_conf.md` / `skeleton-cs_journal.md` / `skeleton-nature.md`；规则与数据 `references/venue-profiles.md` |
| 稿件形状 vs 家族画像 = G6c | `scripts/shape_check.py`（章节顺序、摘要长度、贡献列表/Here-we-show、句式小标题、公式位置、禁用词、Discussion 占比、统计句占比） |
| 各节必写清单（生成 / 核对 = G6b） | `scripts/draft_plan.py plan \| check` |
| LaTeX 稿进关口 | `scripts/tex_to_md.py main.tex <dir> --bib refs.bib`，再 `t2p.py check --project <dir>` |
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
| 模拟审稿 | skill `academic-paper-reviewer` full → re-review |
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
| 系统检索（PubMed 按年切片 / arXiv / OpenAlex）与去重 | 项目内 `lit/search_literature.py`（InfoFusion 模板），写 search_log.json + candidates.csv |
| 滚雪球 | Semantic Scholar 正反向一层，`lit/snowball.py` |
| 规则预筛 / 去重 / DOI 修复 | `lit/triage.py`、`lit/fix_pubmed_dois.py`（efetch 限定 PubmedData） |
| 标题级与摘要级筛选 | Claude 本会话内按批做，写回 screening_sheet.csv |
| 编码 | Claude 按 codebook 本会话内按批做，写 coded.csv；κ 样本盲编 |
| 汇总表 | 项目内 `coding/audit_summary.py --verify` → tables/*.csv |
| G-S2 / G-S3 / G-S5 | `scripts/survey_check.py protocol | coding | claims` |
| 写作 | 论点段 `nature-writing`，对比表与覆盖矩阵 `nature-figure`，润色 `nature-polishing` |
| 审稿 | `academic-paper-reviewer` full，席位换成领域编辑/方法学/领域专家/读者/魔鬼代言人 |
| 投稿包 | 同 P8 |
