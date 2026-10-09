---
name: topic-to-paper
description: "User says one sentence — a topic, a draft path, or 'resume' — and Claude drives it to a submission package: research papers via nine machine-checked gates (leakage, effective-config, denominator, claim scope, DOI resolution, orphan floats, acronyms, dpi at print size, submission-doc consistency), surveys via a parallel branch (search log, screening sheet, codebook, coverage matrix, claim-to-row traceability). All scripts run by Claude, never by the user. Single session, no subagents by default, resumable from research-state.yaml. Triggers: topic to paper, 从选题到论文, 自动化科研, 端到端论文, 帮我做综述, 写一篇综述, survey, review paper, research pipeline, 选题, 投稿包, resume."
version: 2.5.0
author: Wei Zhang (KI) + Claude
license: MIT
---

# topic-to-paper

**这份文件是给 Claude 的执行指令，不是给用户的手册。** 用户只说一句话；下面所有命令都由 Claude 自己跑，用户永远不需要碰脚本。

## 用户会说什么，Claude 做什么

| 用户的话 | Claude 的动作 |
|---|---|
| "帮我做一篇 X 的综述" / "write a survey on X" | 走 **综述分支** S0→S6（下文），从 S0 开始 |
| "用 topic-to-paper 开始 X 方向" / "我想做 X 的方法论文" | 走 **研究分支** P0→P8，从 P0 开始 |
| "这是我的稿子 <路径>，帮我过一遍" | 判断是综述还是研究稿 → 跑对应分支的写作关口（G6 或 S5）→ 报告 |
| "收到审稿意见了" | P7/S6 修订分支，用 `nature-response` |
| "resume X" / "继续 X 项目" | 读 `<项目>/research-state.yaml` → `t2p.py status` → 从第一道未过关口继续 |
| "现在到哪了" | `t2p.py status`，三行回答 |

**回来问用户的时机只有四种**：① 需要凭据或账号（Earthdata、SUPR、NSMC、期刊系统）；② 两种读法会导致实质不同的工作（如"综述范围是影像还是全模态"）；③ 要改已锁定的预注册；④ 关口 FAIL 且修法需要用户的领域判断（如"这条引用到底是哪篇"）。其它一切自己决定、自己做、做完汇报。

**汇报格式**：先结论（过了几道关口、停在哪、为什么），再表格列每道关口的结果，最后一段"需要你做的事"。不展示命令，不展示脚本输出。

## 三条纪律（两条分支共用）

1. **单会话、不开子代理。** 每阶段末更新 `research-state.yaml`；上下文满了告诉用户"说 resume 继续"。
2. **每个数字有出处。** 研究稿的数字回溯到 `results/` 文件；综述的数字回溯到编码表的行。写作时登记到 `paper/numbers.csv`，不登记过不了关口。
3. **先注册再动手。** 研究稿锁 `prereg.md`；综述锁 `protocol.md`（检索式、纳入/排除规则、编码表字段、主张清单）。事后改口径必须在 state 的 `convention_changes` 留记录。

## 工作区（两条分支共用骨架）

```
{project}/
├── research-state.yaml      # 唯一状态源；branch: research | survey
├── prereg.md | protocol.md  # 研究 / 综述 的预注册
├── literature/              # corpus.csv  gap_map.md  mined/  pdf/  lit_index.sqlite
├── runs/ results/           # 研究分支
├── coding/ tables/          # 综述分支：screening_sheet.csv  coded.csv  codebook.md  coverage.csv
├── figures/ figures.csv
├── paper/                   # manuscript.md  claims.csv  numbers.csv  refs.bib  review_log.md
└── submission/              # guide.txt  cover_letter.md  title_page.md  highlights.md  blind.md
```

Claude 的第一步永远是 `python <skill>/scripts/t2p.py init --project <dir> --venue "<刊>" --field <cv|ml|medimg|nature>`（已存在则跳过），最后一步永远是 `t2p.py check --project <dir> --net` 并把状态板翻译成汇报。

---

# 研究分支 P0–P8

每站：做什么 → 产物 → 出口关口（脚本，Claude 跑）。细则与历史漏法在 [references/gates.md](references/gates.md)。

**P0 选刊**：下载 Guide for Authors 到 `submission/guide.txt`（nature.com 用 curl 带浏览器 UA，官方 PDF 比网页可靠），硬规则抄进 state.target。**同时定 `target.family`**：cs_conf（CVPR/NeurIPS/ICML/ICLR/MICCAI…）| cs_journal（TPAMI/TIP/IJCV/EAAI/TGRS/Information Fusion…）| nature（Nature/Science 及子刊、npj、Sci Adv）；三类的章节顺序、篇幅、禁用词、统计写法在 [references/venue-profiles.md](references/venue-profiles.md)（275 篇实测），写作骨架 `templates/skeleton-<family>.md` 在 P6 复制为 manuscript.md 起点。G0 = 文件在、venue 填了。
**P1 文献与饱和**：先 `lit_scout.py build/trend/scout`（本地 PDF 库索引，零 token；没有本地库就跳过，直接走联网 API），再 CrossRef/arXiv/OpenAlex 原生 API。命中 PDF 放 `literature/pdf/`，跑 `baseline_miner.py` 得邻域论文比了谁、消了什么。**原则：先找问题，不找模型；先解释为什么失败，再决定怎么改。** 三个必产物：
① `problem_table.csv`（模板 templates/problem_table.csv）：每篇核心论文一行，记的是"哪里不够"不是"做了什么"：question、hidden_assumption、failure_scene、missing_experiment、contradicts（与哪篇结论相反）、followup_question。缺口短语跨行用同一句话（"no held-out sensor"），`problem_table.py recurring` 数出 ≥2 篇共享的缺口，这比任何单篇的 future work 都硬。≥8 行，已读行 ≥60% 填齐三个缺口列。
② `gap_map.md`（模板 templates/gap_map.md）：≥3 候选主张，来源按产出概率：problem_table 反复缺口 / failure_slice 的失败切片 / 论文明文假设与 future work / 两篇矛盾→找成立条件 / transfer_scan 失效点 / 新场景；每个同时查邻域大题（要热）和具体主张（要冷）的逐年计数，至少 1 个判定为"饱和/不可及，只引用"的对照。关键论文逐篇"做法 / 失效点（原句）"。两个固定问题 `## 评测盲区`、`## 邻域默认假设`，答不出写"未知：查过 X"。`## 判定`：verdict go|no-go + claim_source + reason + 值不值得做五行（重要性/新颖性/可验证性/可解释性/可推广性，答不出写"弱"，≥3 弱应 no-go）。**no-go 是合法出口。**
③ `transfer_scan.md`（模板 templates/transfer_scan.md）：领域外近 18 个月方法扫描，`transfer_scan.py recent --query "<问题结构词，不含领域词>"` 拉本地顶会近 2 年 + arXiv 近 18 月（标未录用）+ OpenAlex；≥5 候选，三道判定：域内计数 ≤2（`count --domain "<领域词>"` 机械填）、结构对应物、目标领域让它失效的那一点。迁移分三层：直接迁移（弱）/ 领域适配（中）/ 用新范式重定义领域问题（强）；失效点写不出的是第一层，不作主张。
有基线代码且能出逐样本预测时，P1 就跑 `failure_slice.py --pred <preds>`：最差切片是总体几倍、误差集中度、模型知不知道（AUROC），协变量扫描给出候选原因假设。平均指标掩盖失败，三个项目的真正论文都在切片里。G1 = `gate_check.py refs` 全绿；G1b = `transfer_scan.py check` 全绿（含 problem_table check、判定五行）。
**P2 预注册**：从 gap_map 或 transfer_scan 选一个主张写 `prereg.md`。**§0 phenomenon 先于一切**：现象（现有方法在 C 条件下失败，来源 failure_slice/problem_table/原句）、原因假设（D 才是关键）、最小对照实验（只改 D；未做则 P3 第一件事做它，G2 WARN）。§1 hypothesis 写成"现有方法在 <条件> 下 <失败>，因为 <原因>；<方法> 修这一点，预期 <量级>"，没有原因词 WARN；必须写 `来源: gap#A` 或 `来源: transfer#T2`（prereg_check 查，指向的行必须过三道判定）；基线表以 `mined/baselines.csv` 为底（≥2 篇比过的必须进表或写明不比）；消融表用 `ablation_plan.py plan code/train.py` 生成后填预测符号；统计判据按 [references/venue-norms.md](references/venue-norms.md)（Nature 系 CI+p，CS 顶会 seeds+消融）。G2 = `prereg_check.py` 全绿，sha256 锁进 state。
**P3 搭建**：填 state.audits（划分键、泄漏开关、关键超参与日志证据列、必需输入、烟测命令），G3 = `audit_check.py --smoke` 全绿。**实验在服务器上跑时**（用户上传、跑完传回的工作流）：填 state.bundle（入口命令、eval 命令、数据远程路径与 inputs、调度器 bash|slurm、matrix = ref/baselines/ablations 各自的参数串与 seeds），`bundle.py check` 核对矩阵覆盖 prereg §5/§6、seeds ≥ min_seeds、无 run 打开泄漏开关；`bundle.py make` 生成自包含实验包（README、check_env.py 逐项核对 CUDA/显存/磁盘/每个 clip 的输入、smoke.sh 一 epoch 烟测、run_all.sh 整矩阵可中断重跑、collect.sh 只打包关口要的文件、manifest.json 记代码 sha256）。来回三次：烟测报告 → 全量结果包 → 反常补跑。结果回来后 `bundle.py tables` 按 metric_map 从 eval.json 生成 main.csv/ablation.csv（硬件取自 hardware.json，manifest 不一致的 run 不进表），再走 G4。
**P4 实验**：每 run 写 run_card；训完看 log 条数；主表只收一种硬件；每 5–10 run 回看 findings.md；对本文方法跑 `failure_slice.py` 出 results/failure_slices.md（最差切片、集中度、模型知不知道，进正文失败分析；缺则 G4 WARN）。**反常触发器**（results_check 查，分诊顺序见 [references/anomaly-triage.md](references/anomaly-triage.md)：口径→数据→泄漏→实现→真发现，findings.md 用 templates/findings.md 的块格式记 checked/cause/action，open 状态不得进正文）：基线复现与原论文报告值差超过 `reproductions` 的 tol（默认 2×报告 std），或任一 `predictions` 符号与预注册相反，必须先在 findings.md 写一条（含方法名与指标名）再继续训练，不许直接改配置——一半的时候反常本身就是论文（ESM-2 序列不预测共表达、kNN 读数低估嵌入都是这么来的）。G4 = `results_check.py` + `ablation_plan.py resolve` 全绿（溯源、口径、seeds、覆盖、预测符号、消融分辨率）。
**P5 图**：**主结果图、消融图、seed 图不手画**：`make_figure.py main|ablation|seeds --project . --out figures/fig_x.png --labels 'col=显示名'`（读 state.results 的表；main = 分组柱 + 多 seed 的 mean±s.d. 与逐 seed 点，ours 红色；ablation = Δ vs 参照 + 灰色 ±2σ√2 噪声带，带内的格灰色；seeds = 指定方法的 mean±s.d.），每张出 .png/.pdf/.source.csv 并登记 figures.csv（inspected=no，裁图目测后改 yes）。其它数据图走 `nature-figure`/`cs-experiment-figure-studio`，示意图走 `scientific-schematics`；**定性对比网格图**（Origin + 各方法 × 样本，带放大 inset，方法名在列下，CV/遥感稿必备）用 `make_comparison.py grid --root figures/det --methods Origin,A,B,Ours --samples s1,s2 --inset x,y,w,h --cols 12`（默认 400 dpi@183 mm，自动算格子尺寸；每个方法一个子目录放同名样本图）。每张进 figures.csv 带印刷宽度与来源。G5 = `gate_check.py dpi`。
**P6 写作**：**先按 family 取骨架** `templates/skeleton-{cs_conf|cs_journal|nature}.md` 作 manuscript.md 起点（nature：Abstract ≤150 词一段 → 无标题引言 ≤600 词末句 "Here we show" → Results 小标题是主张句 → Discussion ≥12% → Methods 在最后；不写 Related Work / Conclusion / 贡献列表 / 正文公式 / "state-of-the-art"，消融写 control experiments，每个比较给 n、检验、p 或 CI。cs_conf：Intro 末尾贡献 3–5 条 → Related → Method 带公式 → Experiments 含 Ablation 小节 → Conclusion，主文 8–10 页附录放全表。cs_journal：同 cs_conf 但 Related 展开 2.1–2.3、Problem Formulation、实验 8–11 小节、Discussion/Limitations 子节、摘要 ≤250、Highlights 另文件）。顺序固定：① 填 claims.csv（每条主张：陈述、数据集、口径、证据文件、表/图、作用域词）；② `draft_plan.py plan` 从 gap_map / prereg / claims / results 自动生成**各节必写清单** paper/draft_plan.md（引言：重要性行、每篇关键论文的失效点、§0 现象、§1 主张一句话、贡献条目含数字；方法：§0 原因假设作动机段、每个有消融的组件、借来方法的失效点与修法；结果：每个预注册基线与消融的名字、ours 相对最强基线的相对变化、不可分辨的消融格必须写"not resolvable / within seed noise"、失败切片与"模型知不知道"；局限：预注册失败分支、五维弱项）；③ 按清单写各节，引言用 `academic-intro-writing`、各节 `nature-writing`、润色 `nature-polishing` 作可选辅助；④ `draft_plan.py check` 逐项核对（词元重合或精确数字，章节对才算），缺的 FAIL = G6b。清单抓的是"该说的没说、说错了章节"，说错了数字由 G6 numbers/scope 抓。**对比/消融表不要手写**：`make_comparison.py sota|multi|ablation|seeds --csv results/x.csv --out paper/tab_x.tex --md --numbers`（sota=单数据集 SOTA 表，按 --group-col 分 CNN/Transformer 组、--extra Params,FLOPs、最优红/次优蓝、--ours 加粗置底；multi=多数据集并排；ablation=✓/× 组件表、全 ✓ 行加粗；seeds=逐 seed + Mean±Std；--labels 'AP50=AP$_{50}$' 换表头）。`--numbers` 把每格登记进 paper/numbers.csv，G6 直接溯源到 `<out>.source.csv`。G6 = `gate_check.py all`（refs/floats/acronyms/scope/numbers/limits）。
**P7 审稿**：`academic-paper-reviewer` full，五席在本会话内执行，每条意见先回结果文件复核再写入 review_log.md，每条标 [major]/[minor] 并给处置（复核通过 / 已改 / rebut / partial，或在 Phase 2 编辑综合表按 R1-3 编号列出）；修完**必须有 `## Re-review` 小节**逐条关闭 major，state.review.round 加 1，G6 重跑。G7 = `review_check.py` 全绿（每条有处置、major 全关闭、round ≥1、gate_report 新于正文、处置里提到的位置在正文里存在）。
**P8 投稿包**：标题页、cover letter、highlights、盲稿、数据声明（`nature-data`）。G8 = `gate_check.py submission`。

---

# 综述分支 S0–S6

来自两篇 Information Fusion 综述的真实流程（InfoFusion_review 纵向稿、InfoFusion_multimodal 融合增益稿）。综述的"实验"是文献本身，所以关口查的是**检索可复现、筛选可追溯、每个主张能回到编码表的一行**。

### S0 选刊与范围
同 P0，外加三个综述专属判定写进 state.survey：**范围边界**（哪些算进、哪些明确排除，各给一条判据）、**组织轴**（按方法层级 / 按任务 / 按数据 / 按时间，只选一个主轴）、**综述的主张**（一篇好综述有一个可证伪的论点，如"报告的融合增益随基线匹配严格度缩小"，不是目录）。编辑退稿最常见的理由是"这是目录不是综述"，S0 就要把论点写出来。
G-S0 = guide.txt 在；state.survey 的 scope_in / scope_out / axis / thesis 四项非空。

### S1 检索与饱和
先查**已有综述**：`lit_scout.py scout '<主题> survey OR review'` + OpenAlex；列出近 5 年同主题综述 ≥3 篇就要在 S0 的 thesis 里写明与它们的区别（InfoFusion 的 Table 1 "adjacent surveys by what they cover" 就是这个）。
再做系统检索：PubMed（按年切片，E-utilities 在 retstart 10 000 截断）、arXiv、OpenAlex，三源去重，写 `literature/search_log.json`（每源的检索式、日期、命中数）和 `literature/candidates.csv`。滚雪球用 Semantic Scholar 正反向各一层，种子 = 已核实的锚点文献。
G-S1 = search_log.json 每源有检索式+日期+计数；candidates.csv 每行有 DOI/PMID/arXiv 之一；已有综述表 ≥1 行且每行说明本文差异。

### S2 协议（综述的预注册）
写 `protocol.md`：① 纳入/排除规则，每条可机械判定（"标题+摘要命中 ≥2 个数据源族且有方法词"）；② **编码表字段**（codebook.md，每字段的取值与判定规则，照 InfoFusion 的 M0–M3 / L0–L2 写法）；③ **主张清单**：综述要下的每个结论及其判据（"若 M3 组的 Δ 中位数 < M1 组，则主张 A 成立"）；④ 事前预测；⑤ 单人筛选时的 κ 验证计划（抽 100 篇让第二编码员盲编）。
G-S2 = `survey_check.py protocol` 全绿：五项齐、每条纳入规则含可判定词、编码表每字段有取值集合、主张清单每条有判据；sha256 锁进 state。

### S3 筛选与编码
分两级：标题级（规则 + 人工）、摘要级（人工）。`coding/screening_sheet.csv` 每行 decision ∈ {include, maybe, exclude} + reason + screen_pass。纳入的进 `coding/coded.csv`，字段 = codebook。生成 PRISMA 计数（`literature/prisma_flow.json`）。
零 token 的部分交脚本：规则预筛、去重、DOI 修复（PubMed efetch 限定 PubmedData）。要判断的部分 Claude 在本会话内按批做，每批写回 csv，不开子代理。
G-S3 = `survey_check.py coding` 全绿：screening 每行 decision+reason；coded 每行每字段的值 ∈ codebook 取值集合；PRISMA 四个数相加对得上；κ 样本已编且 ≥0.6（否则 codebook 要改）。

### S4 汇总表与图
`coding/audit_summary.py` 一类脚本从 coded.csv 算出全部汇总表（按分组的中位数、IQR、占比），**写 tables/*.csv 落盘**；覆盖矩阵 `coding/coverage.csv`（轴 × 任务/数据的篇数）找空白格；时间线、覆盖热图走 `nature-figure`。
G-S4 = 每张 tables/*.csv 的每个数能从 coded.csv 重算（脚本自带 `--verify`）；coverage.csv 的行列合计 = 纳入篇数；figures.csv 齐。

### S5 写作
顺序：论点段 → 已有综述对比表 → 分类法节 → 审计/汇总节 → 空白与路线图 → **综述自身的局限节**（单人筛选、检索源、编码员、时间截止）。每个数字登记 numbers.csv 指向 tables/*.csv 或 coded.csv 的行。参考文献上限按刊（Information Fusion 综述 ≤300，加一删一）。
G-S5 = `gate_check.py all` + `survey_check.py claims`：claims.csv 每条主张的 evidence 指向 tables/ 或 coded.csv 的具体行并能重算；"first/only survey" 类主张必须对已有综述表逐行说明。

### S6 审稿、修订、投稿包
同 P7/P8。综述审稿席位换成：领域编辑（是否目录）、方法学（检索与编码可复现）、领域专家（漏了谁）、读者视角（能否据此选方法）、魔鬼代言人（论点能否被已有综述反驳）。

---

## 脚本（全部由 Claude 跑）

入口 `t2p.py`（init / check / status / doctor）；`check` 对综述分支额外跑 `survey_check.py`。
研究分支：`lit_scout.py` `baseline_miner.py` `prereg_check.py` `ablation_plan.py` `audit_check.py` `results_check.py` `gate_check.py`。
综述分支：`survey_check.py`（protocol / coding / claims 三个子命令）+ `gate_check.py`。
输入转换：`tex_to_md.py`（LaTeX）、`pdf_to_md.py`（已发表 PDF）、`jats_to_md.py`（Europe PMC XML）。
校准：`calibrate.py` `venue_norms.py`（在已发表语料上重算关口阈值与刊物规范）。
模板在 `templates/`（研究：prereg.md run-card.md；综述：protocol.md codebook.md）。改任何脚本后先跑 `python -m pytest tests -q`（tests/README.md），全绿才算改完。验证记录在 `references/validation-*.md`，失败模式总表 [references/lessons.md](references/lessons.md)，路由 [references/routing.md](references/routing.md)。
