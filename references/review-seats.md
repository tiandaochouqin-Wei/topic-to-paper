# 审稿（P7 / S6）：独立审稿流程、席位与子代理提示

**审稿是本 skill 里唯一允许开子代理的地方**（用户 2026-10-28 批准；其余阶段仍是单会话）。原因：自审时同一个模型带着作者的全部上下文写五个席位，诊断见 [lessons.md](lessons.md)「审稿」一节——cvpr2027_med2 六条 major 里四条靠收窄措辞关闭，cvpr2027_medical 的输入朝向错误扛过 10 轮自审，cvpr2027_fusion 根本没审。独立的是**上下文**（审稿人没见过 prereg、claims、对话、作者笔记），不是判断力：子代理仍是同一模型家族，所以汇报时如实写"同一模型家族的独立上下文审稿，不等于真实审稿"，最终审稿人仍是用户。

评分口径见 [review-rubrics.md](review-rubrics.md)，各刊审稿表见 `review-forms/`（`cs_conf.md` / `cs_journal.md` / `nature.md`）。本机若装有 `academic-paper-reviewer`，可用来做主会话里的 R4 / R5 综合；独立席位仍必须走子代理，产物格式相同，`review_check.py` 照常核对。

目标不是写一份"像审稿意见"的文字，而是找出审稿人真会抓的、能让稿子被拒或降档的问题，并改到关闭。只有赞美和泛泛建议的审稿是失败的审稿。

## 流程

1. **冻结稿件**：编译好 PDF（无 PDF 时用 `paper/manuscript.md` + figures/），G6 全绿后 `python review_packet.py make`。它把 PDF（或稿 + 图）、该刊审稿表、`manifest.json`（sha256、venue、family、席位）和每席一个填好的提示 `prompts/<席位>.md` 放进 `paper/review_packet/round<N>/`。
2. **独立审**：**每个提示文件启动一个全新上下文的子代理**（Agent 工具，general-purpose），提示原文整段交给它，**不加任何东西**。席位：R0（区域主席 / 价值）、R1+R3（方法学与泄漏，一个子代理两个席）、R2（新颖性）、DA（魔鬼代言人）。子代理**拿不到** prereg.md、claims.csv、gap_map、对话和作者笔记；例外只有两条：R1+R3 在写完盲读之后可以打开 `results/` 与 `runs/` 核对证据，R2 可以检索文献（lit_scout 索引、网络）去找最接近的三篇。综述分支见下表，同样每个提示一个子代理。
3. **登记**：把每个子代理返回的审稿**原文**贴进 `paper/review_log.md`，标题行 `## Reviewer <席位> (independent, packet <sha8>)` 不改；不删条、不改严重度、不改类别（不同意写 `rebut`，别改原文）。
4. **主会话里的席位**：R4 写作与形状、R5 编辑综合可以留在主会话（它们要读 gate 输出与作者材料）。R5 是一张表 `编号 | 严重度 | 类别 | 席位 | 一句话 | 处置计划 | 工作量 | 投稿前必须做`，再给建议档位（[review-rubrics.md](review-rubrics.md)）+ 置信度 + 一句话理由 + 投稿前最该做的三件事，区分"不做必被拒""做了明显加分""可留给 rebuttal"。R0 的评分低（cs_conf ≤ 3）时 R5 的第一件事是回证据或选题，不是改写。
5. **先核实"缺失"类意见**：子代理写"没比较 X / 没报告 Y"，作者先在正文、附录、补充材料里搜一遍；搜到的在处置里写"已在 §…"（`复核通过`），冤枉作者是最常见的假阳性。搜不到才改。
6. **处置与改稿**（用户让改才改）：处置词表见下。每条意见回结果文件复核后再处置，改数字回到结果文件与 numbers 登记。
7. **复审**：改稿 → 重新编译 → G6 重跑 → `python review_packet.py rereview --round N --items R0-1,R2-3`（每条 major 一份提示，含原意见 + 作者处置 + 改后 PDF 的 sha）→ 每条一个新子代理，**由同一席位**在改后版本上判 `closed` / `OPEN` → 贴进 `## Re-review <席位> (independent, packet <sha8>)`。`state.review.round` 加 1。
8. **`review_check.py`**（G7）。

## 红线

- 类别为 `evidence | validity | novelty | value` 的 major，**只能由同一席位在改后版本的 PDF 上、用新上下文子代理复审后写 `R0-1 closed: …` 才算关闭**。作者在自己的段落里写 closed 不算；行内 `→ 已改` 不算。
- **收窄主张是合法的修法，但只有独立复审接受它才算关闭**；"收窄措辞"本身不是关闭（满足它的复审必须读到收窄后的稿子，并判断收窄后仍有被该刊接受的贡献）。
- `validity` 类 major 的处置必须引用一个存在的检查输出文件，且这个检查在**故意弄坏的版本上会失败**（G3b 的 `results/instruments/*_broken.json`、或一条变异测试）。"我们查过了没问题"不是关闭。
- 不编造实验结果、数字、引用；不用改措辞去"关闭"一条本来需要证据的 major；改数字回到结果文件和 numbers 登记，不在稿子里手改。
- 子代理的返回不得被主会话改写后再贴；要质疑就在处置里写 `rebut: <引用结果文件>`。

## 意见格式（每条五点 + 类别，否则不写）

- **定位**：§x.y / Table n / Fig n / 行号。
- **被攻击的主张**：引用或转述正文原话，不是笼统的"实验不够"。
- **后果**：一句话，说为什么审稿人在意。
- **怎样才算解决**：具体动作与预期读数（"加 X 对照，预期读数 Y"）。给不出的就是泛泛之谈，删。
- **严重度**：`[major]` = 不解决会使结论不成立、结果不可信或稿子被拒；`[minor]` = 清晰度、措辞、格式。major 一般 3–8 条，超过 10 条是在凑数，合并或降级。
- **类别** `category:`（行内或下一行）：
  - `evidence`：主张缺支持 / 缺实验；
  - `validity`：测量可能是错的——泄漏、bug、协议、输入约定；
  - `novelty`：已有工作；
  - `value`：重要性 / 与该刊的匹配；
  - `clarity`、`format`：表达与版式。

## 研究稿席位

下表的"只问这些问题"就是子代理提示里的 `{seat_questions}`，所以只写稿子本身能回答的问题（不引用 prereg / claims）。"盲读后才可打开"一列只对标注的席位开放。R0 / R1+R3 / R2 / DA 各是一个独立子代理；R4、R5 留在主会话。

| 席位 | 只问这些问题 | 盲读后才可打开 |
|---|---|---|
| R0 区域主席 / 价值 | 这篇稿子 {venue} 会收吗？主要发现是否已被该刊读者知道或显而易见——点名谁已经这么说了？有没有一张对最强已发表方法的主表？只读完第 1 节，你能否用一句话说出这篇稿子的唯一主张？最能提高评分的单一改动是什么？按该刊审稿表的量表给出 rating。 | 无（只看稿子） |
| R1 方法学 / 统计 | 主张的作用域有没有越过数据集与口径？每个"更好"有没有 n、seeds、检验？消融格是否在 seed 噪声内却被解读？消融是否一次只改一个因素、对照是否同等调参？含命题的稿子：每条命题是否独立重推过证明（量词、期望还是概率、比值损失的分母）？正文里的"不可能/任何/从不"是否逐句对到某条命题？置信区间的重采样单位是不是稿中写明的独立单位（患者 / 场景，而不是切片 / 帧）？经验陈述里的"从不/每一对/所有任务"在换一个预测器或缩小测试集后是否仍成立？有无多重比较、事后挑指标、只报最好的 seed？ | results/ 的表与分析脚本的重采样代码（只读） |
| R2 领域专家 / 新颖性 | 问题是否真实、是否已有人系统回答？**最接近的三篇已有工作是哪几篇、差异是否站得住**（实际检索，不凭记忆断言；给出标题与年份）？基线是否漏了该邻域里被比最多的、是否同等设置？贡献点（新方法 / 新发现 / 新数据）与实验对得上吗？稿中声称的"现有方法失效点"有证据吗？ | 文献检索（lit_scout 索引、网络） |
| R3 复现与泄漏 | 划分键、泄漏开关、关键超参是否生效、硬件是否混用？早停与调参是否碰过测试集？预处理统计量（归一化、窗宽窗位）是否只在训练集估计？输入约定（朝向、间距、通道、归一化）是否与所用预训练组件的官方约定一致？数字能否溯源？代码、权重、预算是否可得？ | results/ 与 runs/*/args.json（只读） |
| R4 写作与形状 | 章节顺序与家族画像是否一致？摘要→引言→贡献→实验→结论是否一条线、是否共用同一句主张？引言是否按读者的问题推进（不是点名一串论文）？图是否单看图与图注就能读懂、是否都被正文引用？缩略语？局限节是否诚实？版式、双盲是否合刊要求？（主会话） | shape_check、draft_plan、argument_check、readability_check 的输出 |
| R5 编辑 | 一句话说得清贡献吗？对该刊读者重要吗？局限节是否覆盖预注册的失败分支？有无过度宣称？投稿文件与正文一致吗？综合出档位与三件事。（主会话） | paper/claims.csv、prereg.md §8、submission/ |
| DA 魔鬼代言人 | 构造对这篇稿子**最有力的反驳**：结论能否被更简单的解释取代（数据偏差、弱基线、指标选择、泄漏）？哪个实验做了会推翻主张、作者是否回避？哪篇已有工作或哪组数据能直接反驳核心论点？去掉最亮眼的结果后剩下的够发表吗？只写 1–3 条，每条给出"怎样才能反驳我" | 无（只看稿子） |

## 综述稿席位

综述分支默认 WARN 级（`review_check.py` 对缺少独立节只警告）。仍建议独立审：R1+R4 一个子代理、R2+R3 一个子代理、DA 一个子代理（R3 可检索文献）。

| 席位 | 编号 | 只问这些问题 |
|---|---|---|
| 领域编辑 | R1 | 这是综述还是目录？论点一句话是什么，能被证伪吗？ |
| 方法学 | R2 | 检索式、日期、计数能复现吗？纳入规则可机械判定吗？编码表每字段有取值集合吗？κ 多少？ |
| 领域专家 | R3 | 漏了哪些该纳入的工作（实际检索）？已有综述表是否齐、差异是否成立？ |
| 读者视角 | R4 | 读完能据此选方法吗？覆盖矩阵的空白格有没有变成路线图？ |
| 魔鬼代言人 | DA | 论点能否被某篇已有综述或某组被纳入文献直接反驳？ |

## 处置词表

| 处置 | 含义 | 约束 |
|---|---|---|
| 已改 | 已在稿中改动 | 写改在哪（§ / Table / Fig） |
| 复核通过 | 复核后意见不成立，或稿中已有证据 | 写稿中哪里有证据 |
| rebut | 不采纳 | 引用结果文件或论据，不能只写"不同意" |
| partial | 部分采纳 | 写明采了哪半、没采哪半及原因 |
| 需新实验 | 要补实验才能关 | 未补之前 major 不得写 closed；补完在复审节关闭 |

## 自审的已知失败模式

- **自我欣赏**：写出一堆"总体不错，但可以…"就说明没在审 → 每席先写最强拒稿理由。
- **锚定作者框架** → 独立子代理没有作者框架可锚。
- **严重度通胀 / 凑数** → major 数量约束。
- **假缺失** → 流程第 5 步先搜。
- **只有方法学、没有新颖性与价值** → R2 必须真的去检索最接近的工作；R0 必须回答"这个发现是否已知"。
- **档位偏乐观**：拿不准往低估，并写出"什么证据能升一档"。
- **用收窄措辞关闭 major** → 红线：只有独立复审接受才算。
- **子代理也是同一模型家族**：上下文独立，判断不独立。汇报时如实说明，不等于真实审稿结果；最终审稿人是用户。

## 子代理提示模板

`review_packet.py` 读下面的模板（`<!-- template: 名字 -->` 后的围栏块），替换占位符 `{pdf}` `{form}` `{venue}` `{seat}` `{seat_questions}` `{packet_sha}` `{project_dir}`（复审另有 `{item_id}` `{item_text}` `{disposition}`），写成 `prompts/<席位>.md`。`{common}` 展开为 common 块。改模板时不要在围栏块里写三个反引号。

<!-- template: common -->
```
You are an independent peer reviewer for {venue}. You have never seen this project. You have only the files named below. Do not open any other file of this project, do not look for the authors' notes, and do not ask the authors anything.

Manuscript: {pdf}
Review form: {form}   (read it first; your review follows its questions and its rating scale)
Packet: {packet_sha}

How to review
- Start with one line: "Strongest reason to reject: ..." - the best case you can make for rejecting this paper.
- Every item has five parts, or you do not write it: where (section / table / figure / line); the claim you attack (quote or paraphrase the text); the consequence for a reader; what would resolve it (a concrete action and the reading that would settle it); severity. Add a category.
- Item format, one numbered line per item:
  1. [major] <where>: <claim attacked>. <consequence>. Resolve: <action and expected reading>.
     category: <evidence | validity | novelty | value | clarity | format>
- [major] = the conclusion would not stand, the result would not be trusted or the paper would be rejected if this is not resolved; [minor] = clarity, wording, format. Expect 3-8 majors; more than 10 means you are padding - merge or downgrade.
- categories: evidence = a claim lacks support or an experiment is missing; validity = the measurement may be wrong (leakage, a bug, the protocol, an input convention); novelty = prior work; value = significance or fit to the venue; clarity / format = presentation.
- Before you write "X is missing / not compared / not reported", search the whole manuscript, appendix and supplement for X, and say so in the item ("searched the full text for X: not found").
- No praise padding. Do not suggest a rewrite when the problem is missing evidence.

How to return
- Your final message is the review and nothing else; do not write files.
- Begin it with exactly this heading line: ## Reviewer {seat} (independent, packet {packet_sha})
- Number the items from 1 under that heading (for a pair of seats, use a "### R1 ..." / "### R3 ..." sub-heading per seat and number the items from 1 under each).
- Finish with the rating lines the form asks for: "rating: ..." and "confidence: ...".
```

<!-- template: R0 -->
```
{common}

Your seat: R0, area chair (value). Answer these questions in this order, as numbered items or short paragraphs under your heading:
{seat_questions}

After your items write: "Single change that would most raise the rating: ..." and the rating lines. R0 must give a rating on the form's scale.
```

<!-- template: R1R3 -->
```
{common}

Your seat: R1+R3, methodology / statistics and reproducibility / leakage. Questions for the two seats:
{seat_questions}

Order of work: (1) read the manuscript only and write a three-line blind read: the paper's one-sentence contribution; which claim you would and would not believe after five minutes; whether the abstract's promises are met in the body. (2) Only after writing it, you may open the evidence folders read-only: {project_dir}/results and {project_dir}/runs. Do not open prereg.md, claims.csv, literature/ or the other paper/ files; do not run any code. Items that rest on a file you opened name the file.
Put the blind read directly under your heading, then a "### R1 methodology" and a "### R3 reproducibility" sub-heading with the items.
```

<!-- template: R2 -->
```
{common}

Your seat: R2, domain expert (novelty). Questions:
{seat_questions}

You may search the literature (web search, or any local paper index you can find) to name the closest three prior works; give title, year and what differs. State plainly if you could not find them. A claim of novelty you cannot support from a search is a [major] with category novelty.
```

<!-- template: DA -->
```
{common}

Your seat: DA, devil's advocate. Questions:
{seat_questions}

Write 1-3 items only. Under each, add the line "How to refute me: ..." giving the experiment or argument that would answer you.
```

<!-- template: SR1R4 -->
```
{common}

Your seat: R1+R4 for a survey: domain editor and reader. Questions:
{seat_questions}

Put the items under "### R1 domain editor" and "### R4 reader" sub-headings.
```

<!-- template: SR2R3 -->
```
{common}

Your seat: R2+R3 for a survey: methodology and domain expert. Questions:
{seat_questions}

You may search the literature to find included-worthy works that the survey misses; name them. Put the items under "### R2 methodology" and "### R3 domain expert" sub-headings.
```

<!-- template: rereview -->
```
You are re-reviewing one item that you raised, as seat {seat}, against an earlier version of this manuscript for {venue}. You have only the item below, the authors' response to it and the revised manuscript. Do not open any other file of this project.

Revised manuscript: {pdf}
Review form: {form}
Packet: {packet_sha}

Original item {item_id}:
{item_text}

Authors' disposition:
{disposition}

Decide whether the item is resolved in the revised manuscript as it now reads.
- Find the place the authors name and read it. A change in the response that is not in the manuscript does not count.
- If the authors narrowed or reworded a claim, judge whether the narrowed paper still makes a contribution {venue} would accept. Narrowing that removes the contribution is OPEN.
- For a validity item the authors must cite a check whose output fails on a deliberately broken variant; a statement that "we checked and it is fine" is OPEN.
- Also report problems the revision introduced (new claims without evidence, numbers that changed in one place but not in the abstract or conclusion, dangling references), in the item format of the original review.

Return only this, as your final message, with no files written:
## Re-review {seat} (independent, packet {packet_sha})
{item_id} closed: <where in the revised manuscript and why that settles it>
(or)
{item_id} OPEN: <what is still missing>
Then any new items, numbered, each "[major|minor] <where>: ... category: ...".
```

## 产出格式（paper/review_log.md）

`review_check.py` 认的结构：独立席位标题 `## Reviewer <席位> (independent, packet <sha8>)`（`<sha8>` = `manifest.json` 里稿件 sha256 的前 8 位）；子标题 `### R1 …` / `### R3 …` 给出席位；意见是编号行 `1. [major] …`，编号与席位拼成 `R1-1`；`category:` 在行内或后两行；处置在同行或后两行；独立复审节标题 `## Re-review <席位> (independent, packet <sha8>)`，其中的 sha8 必须来自改后版本的 packet。

```
# Review log — round 1 (<日期>, 口径: <官方表 / 通用口径>)

## Reviewer R0 (independent, packet 1a2b3c4d)
Strongest reason to reject: …
1. [major] <定位>：<被攻击的主张>。<后果>。Resolve: <具体动作>。
   category: value
   处置: 已改 (<改在哪>)
rating: 3
confidence: 4

## Reviewer R1+R3 (independent, packet 1a2b3c4d)
### R1 methodology
1. [minor] … category: clarity → rebut: <理由，引用结果文件>

## R5 编辑综合（主会话）
| 编号 | 严重度 | 类别 | 席位 | 一句话 | 处置计划 | 工作量 | 投稿前必须做 |
建议档位：… （置信度：高/中/低）；理由：…；投稿前最该做的三件事：1) … 2) … 3) …

## Re-review R0 (independent, packet 9f8e7d6c)
- R0-1 closed: <改后位置与依据>
## Re-review R1+R3 (independent, packet 9f8e7d6c)
- R1-2 OPEN: <还差什么>
```

`review_check.py` 的行为（别踩）：
- 没有任何独立节 → FAIL；`state.review.independent_waiver: "<原因>"` 把它降成 WARN（确实无法开子代理的项目；综述分支默认只 WARN）。R0 必须存在且带 `rating:`；评分在拒稿线上（cs_conf ≤ 3 / 期刊 reject 或 major / nature reject）→ WARN。
- 独立节的 packet sha8 必须在 `paper/review_packet/round*/**/manifest.json` 里登记，否则 FAIL。
- 每个 `[major]` 应带 `category:`（缺了 WARN，旧日志不至于全红）。四类（evidence/validity/novelty/value）major 必须由独立复审节关闭（sha8 与原审稿不同、席位对得上），否则 FAIL"作者不能自己关闭"；在作者段落用收窄词关闭 → FAIL"收窄措辞不是关闭"。validity 类还要在关闭行或处置里引用一个存在的文件路径。
- 行内 `→ 已改 / closed / fixed` 把该条直接判为已关闭、不经复审（EAAI 真实日志依赖此行为）。**major 写 `处置: 已改 (…)`，不用箭头**，这样才逼出复审；仍用箭头时脚本给 WARN（复审节没逐条核对）。四类 major 用箭头关闭 = FAIL。
- 复审节里没关的 major 写 `OPEN: …`。含否定的句子（`NOT closed`、`未关闭`、`尚未`）不再算关闭，但 `OPEN:` 一行里仍避免出现 closed / 关闭 / 已改 / 通过 等词，免得歧义。
- `state.project.entry: have_reviews`（日志里是真实审稿人的意见）不要求独立节。
