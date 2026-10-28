---
name: topic-to-paper
description: "Gated topic-to-submission pipeline. One sentence from the user (a topic, a draft path, or 'resume <project>') and Claude runs every script to a submission package: research branch P0–P8 and survey branch S0–S6, each stage closed by a machine-checked gate (preregistration lock, leakage/effective-config audit, number traceability, ablation resolution, figure dpi, manuscript shape, review loop, submission consistency). Single session, no subagents, state in research-state.yaml. Triggers: 用 topic-to-paper, 从选题到论文, 投稿包, 端到端论文, 自动化科研, 帮我做一篇综述, 写一篇综述, write a survey on X, 这是我的稿子帮我过一遍关口, check my draft against the gates, resume/继续 <项目>. Not for a single writing, citation or figure task (nature-writing, nature-citation, nature-figure do those)."
version: 2.12.0
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
| "这是我的稿子 <路径>，帮我过一遍" | `t2p.py init --entry have_draft`（已有项目则把 state.project.entry 改成 have_draft）→ 稿子转 paper/manuscript.md → 判断是综述还是研究稿 → 跑对应分支的写作关口（G6 或 S5）→ 报告。G1b–G5 显示 N/A 是正常的 |
| "收到审稿意见了" | entry 改 have_reviews（新项目 `init --entry have_reviews`）→ 意见逐条进 paper/review_log.md → P7/S6 修订分支，用 `nature-response` |
| "resume X" / "继续 X 项目" | `t2p.py status`（显示上次 check 写回的状态板）→ 从第一道未过关口继续；状态可疑就重跑 `t2p.py check` |
| "现在到哪了" | `t2p.py status`，三行回答 |

**回来问用户的时机只有四种**：① 需要凭据或账号（Earthdata、SUPR、NSMC、期刊系统）；② 两种读法会导致实质不同的工作；③ 要改已锁定的预注册；④ 关口 FAIL 且修法需要用户的领域判断。其它一切自己决定、自己做、做完汇报。

**汇报格式**：先结论（过了几道关口、停在哪、为什么），再表格列每道关口的结果，最后一段"需要你做的事"。不展示命令，不展示脚本输出。

## 三条纪律（两条分支共用）

1. **单会话、不开子代理。** 每阶段末更新 `research-state.yaml`；上下文满了告诉用户"说 resume 继续"。
2. **每个数字有出处。** 研究稿的数字回溯到 `results/` 文件；综述的数字回溯到编码表的行。写作时登记到 `paper/numbers.csv`，不登记过不了关口。
3. **先注册再动手。** 研究稿锁 `prereg.md`；综述锁 `protocol.md`（检索式、纳入/排除规则、编码表字段、主张清单）。事后改口径必须在 state 的 `convention_changes` 留记录。
4. **外部 skill 缺则自己做。** 路由到的任何外部 skill 不在本机时，按 [references/routing.md](references/routing.md) 开头的替代做法在本会话内做同样的事，产物格式不变，不为此停下来问用户（`t2p.py doctor --skills` 可查哪些在）。关口只依赖 `scripts/`。

## 工作区（两条分支共用骨架）

```
{project}/
├── research-state.yaml      # 唯一状态源；branch: research | survey
├── prereg.md | protocol.md  # 研究 / 综述 的预注册
├── literature/              # corpus.csv  gap_map.md  pdf/
├── runs/ results/           # 研究分支
├── coding/ tables/          # 综述分支：screening_sheet.csv  coded.csv
├── figures/ figures.csv
├── paper/                   # manuscript.md  claims.csv  numbers.csv  refs.bib
└── submission/              # guide.txt  cover_letter.md  blind.md …
```

Claude 的第一步永远是 `python <skill>/scripts/t2p.py init --project <dir> --venue "<刊>" --field <cv|ml|medimg|nature> --entry <topic_only|topic_plus_data|have_results|have_draft|have_reviews>`（已存在则跳过），最后一步永远是 `t2p.py check --project <dir> --net` 并把状态板翻译成汇报。`check` 会把每道关口的 status/evidence/checked 写回 state.gates，`status` 读它；**state.gates 一律不手工改**，预注册/协议的 sha256 用 `t2p.py lock` 写。

---

# 研究分支 P0–P8

每站四件事：做什么 → 产物 → 命令 → 出口关口。**进入某站之前先读 `references/phases/P<n>.md`（该站全部细则），照做，不凭记忆补细节。** 关口的判据与为什么在 [references/gates.md](references/gates.md)。下表是索引，不是全文。

| 站 | 做什么 | 产物 | 命令（Claude 跑） | 出口关口 |
|---|---|---|---|---|
| **P0 选刊** [细则](references/phases/P0.md) | 下载 Guide for Authors；硬规则与 `target.family`（cs_conf / cs_journal / nature）抄进 state.target；有 LaTeX 模板的刊：class 进 paper/latex/ | submission/guide.txt；state.target；paper/latex/main.tex | curl（nature.com 带浏览器 UA）；`latex_check.py skeleton --venue "<刊>"`、`widths --tex` | G0 = 文件在、venue 填了 |
| **P1 文献与饱和** [细则](references/phases/P1.md) | 先找问题不找模型：本地索引 → 联网 API；每篇核心论文记"哪里不够"；领域外方法扫描；有基线代码就切失败片 | literature/problem_table.csv、gap_map.md（`## 判定` go/no-go）、transfer_scan.md；refs.bib | `lit_scout.py` `baseline_miner.py` `problem_table.py` `transfer_scan.py recent\|count\|check` `failure_slice.py` | G1 = `gate_check.py refs`；G1b = `transfer_scan.py check`。**no-go 是合法出口** |
| **P2 预注册** [细则](references/phases/P2.md) | §0 现象 → 原因 → 最小对照 先于方法；§1 写"在 <条件> 下 <失败>，因为 <原因>"并标 `来源: gap#A` 或 `transfer#Tn`；八节齐、口径写死 | prereg.md（sha256 锁进 state.gates.G2） | `ablation_plan.py plan code/train.py` → `prereg_check.py` | G2 = `prereg_check.py` 全绿 |
| **P3 搭建** [细则](references/phases/P3.md) | 填 state.audits（泄漏开关、关键超参证据列、必需输入、烟测）；**仪器校准**见细则（G3b）；实验在服务器跑时填 state.bundle 出实验包 | runs/ 结构；bundle/ | `audit_check.py --smoke`；`bundle.py check\|make\|tables` | G3 = `audit_check.py` 全绿（runs 空时 `bundle.py check` 顶上）；G3b = `instrument_check.py`（已知答案 + 破坏对照） |
| **P4 实验** [细则](references/phases/P4.md) | 每 run 写 run_card；反常先记 findings.md 再动配置（分诊 [anomaly-triage](references/anomaly-triage.md)）；对本文方法切失败片 | results/main.csv、ablation.csv、runs/*/eval.json、findings.md、results/failure_slices.md | `failure_slice.py`；`results_check.py`；`ablation_plan.py resolve` | G4 = 两脚本全绿 |
| **P5 图** [细则](references/phases/P5.md) | 数据图、定性网格、方法总览图由脚本生成；**全部 PDF，组合图每面板一个 PDF**；每张裁图目测后 inspected=yes；**按印刷宽度画**（印刷字号 ≥ 5 pt） | figures/*.pdf+ .source.csv；figures.csv | `make_figure.py`；`make_comparison.py grid`；`make_motivation.py`；`make_architecture.py`；`figure_plan.py`（范文→计划） | G5 = `gate_check.py dpi` + `figure_plan.py check` |
| **P6 写作** [细则](references/phases/P6.md) | 按 family 取骨架 → 填 claims.csv → 生成必写清单 → 写 → 表格由脚本生成并登记数字；LaTeX 稿写 paper/latex/main.tex，`tex_to_md.py` 派生 manuscript.md 再过关口 | paper/manuscript.md、claims.csv、numbers.csv、draft_plan.md | `draft_plan.py plan\|check`；`make_comparison.py sota\|multi\|ablation\|seeds --numbers`；`make_algorithm.py skeleton\|check`；`gate_check.py all`；`shape_check.py`；`readability_check.py` | G6 = `gate_check.py all`；G6b = `draft_plan.py check`；G6c = `shape_check.py`；G6d = `latex_check.py check`（LaTeX 稿）；G6e = `claims_check.py`（主张 ↔ 结果文件）；G6f = `readability_check.py`（数字密度、贡献条目、流程簿记词，对照已发表论文） |
| **P7 审稿** [细则](references/phases/P7.md) | 五席审稿在本会话内做；每条先回结果文件复核再写 review_log.md；修完 `## Re-review` 逐条关闭 major，G6 重跑 | paper/review_log.md；state.review.round + 1 | `review_check.py` | G7 = `review_check.py` 全绿 |
| **P8 投稿包** [细则](references/phases/P8.md) | 标题页、cover letter、highlights、盲稿、数据声明 | submission/* | `gate_check.py submission` | G8 |


---

# 综述分支 S0–S6

来自两篇 Information Fusion 综述的真实流程（InfoFusion_review 纵向稿、InfoFusion_multimodal 融合增益稿）。综述的"实验"是文献本身，所以关口查的是**检索可复现、筛选可追溯、每个主张能回到编码表的一行**。

每站同研究分支：**进入某站之前先读 `references/phases/S<n>.md`**，照做。

| 站 | 做什么 | 产物 | 命令（Claude 跑） | 出口关口 |
|---|---|---|---|---|
| **S0 选刊与范围** [细则](references/phases/S0.md) | 同 P0，外加 state.survey 的范围边界 / 组织轴 / 论点（一篇综述要有一个可证伪的论点，不是目录） | submission/guide.txt；state.survey 的 scope_in、scope_out、axis、thesis | curl | G-S0 = guide 在、四项非空 |
| **S1 检索与饱和** [细则](references/phases/S1.md) | 先查已有综述（≥3 篇要在 thesis 里写差异）；PubMed 按年切片 / arXiv / OpenAlex 三源去重；Semantic Scholar 正反向滚雪球 | literature/search_log.json、candidates.csv、prior_surveys.csv | `lit_scout.py scout` + 项目内检索脚本 | G-S1 = 每源有检索式、日期、计数；每行有标识符；已有综述表每行写差异 |
| **S2 协议** [细则](references/phases/S2.md) | protocol.md：纳入/排除规则可机械判定、编码表每字段有取值集合、主张清单每条有判据、事前预测、κ 计划 | protocol.md（sha256 锁进 state.gates.G-S2）、coding/codebook.md | `survey_check.py protocol` | G-S2 全绿 |
| **S3 筛选与编码** [细则](references/phases/S3.md) | 标题级 → 摘要级；零 token 的部分交脚本，要判断的部分本会话按批做；生成 PRISMA 计数 | coding/screening_sheet.csv、coded.csv、literature/prisma_flow.json、coding/kappa_results.json | `survey_check.py coding` | G-S3 全绿（κ ≥ 0.6） |
| **S4 汇总表与图** [细则](references/phases/S4.md) | 汇总表由脚本从 coded.csv 算出并落盘（自带 --verify）；覆盖矩阵找空白格 | tables/*.csv、coding/coverage.csv、figures.csv | `survey_tables.py`、`survey_figure.py` | G-S4 = 每个数可重算；行列合计 = 纳入篇数 |
| **S5 写作** [细则](references/phases/S5.md) | 论点段 → 已有综述对比表 → 分类法 → 审计/汇总 → 空白与路线图 → 自身局限；每个数字登记 numbers.csv | paper/manuscript.md、claims.csv、numbers.csv | `gate_check.py all`；`survey_check.py claims` | G-S5 全绿（first/only 主张逐行对照已有综述） |
| **S6 审稿、修订、投稿包** [细则](references/phases/S6.md) | 同 P7/P8；席位换成领域编辑 / 方法学 / 领域专家 / 读者 / 魔鬼代言人 | paper/review_log.md、submission/* | `review_check.py`；`gate_check.py submission` | G7 / G8 |


---

## 脚本（全部由 Claude 跑）

入口 `t2p.py`（init / check / status / doctor）；`check` 对综述分支额外跑 `survey_check.py`。
研究分支：`lit_scout.py` `baseline_miner.py` `prereg_check.py` `ablation_plan.py` `audit_check.py` `instrument_check.py` `bundle.py` `results_check.py` `gate_check.py` `claims_check.py`。
综述分支：`survey_check.py`（scope…writing）、`survey_tables.py`、`survey_figure.py` + `gate_check.py`。
输入转换：`tex_to_md.py`（LaTeX）、`pdf_to_md.py`（已发表 PDF）、`jats_to_md.py`（Europe PMC XML）。
校准：`calibrate.py` `venue_norms.py`（在已发表语料上重算关口阈值与刊物规范）。
模板在 `templates/`（研究：prereg.md run-card.md；综述：protocol.md codebook.md）。改任何脚本后先跑 `python -m pytest tests -q`（tests/README.md），全绿才算改完。每站细则在 `references/phases/P0.md`–`P8.md` 与 `S0.md`–`S6.md`（进站前读）。验证记录在 `references/validation-*.md`，失败模式总表 [references/lessons.md](references/lessons.md)，路由 [references/routing.md](references/routing.md)。
