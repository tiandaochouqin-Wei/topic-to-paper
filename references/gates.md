# 关口细则

每个关口写三样：判据、为什么是这个判据而不是更直觉的那个、过去怎么漏的。

## G0 目标与硬规则
判据：`submission/guide.txt` 存在；state.target 含 page_limit、keyword_max、columns、min_dpi、ref_max、blind（bool）。
为什么：硬规则决定写作阶段的字数预算与参考文献加一删一策略，事后砍比事前控代价高十倍。
漏法：EAAI 关键词上限 6、单栏硬性、首投就要源文件，三条都是定稿后才发现。

## G1 文献入库即解析
判据：gap_map 每个候选主张附 `lit_scout trend` 逐年计数；corpus.csv 每行有 doi/pmid/arxiv 之一；`gate_check.py refs` 对 corpus 跑一次全绿。
为什么：字符串看着对但 DOI 指向另一篇，人工校对抓不到，只有解析回标题再比对才行。
漏法：引用 key 用"首词+年份"让三组不同论文共用一条参考文献，静默合并。key 取三词并断言一 key 一标识符。

## G1b 创新点来源可追溯（`scripts/transfer_scan.py check`，机械）
判据：literature/problem_table.csv 存在、≥8 行、tag/question/finding 齐、已读行 ≥60% 填齐 hidden_assumption+failure_scene+missing_experiment、≥1 条缺口被 ≥2 篇共享（`problem_table.py check`，由 transfer_scan check 调用）；gap_map `## 判定` 在 go 时五行（重要性/新颖性/可验证性/可解释性/可推广性）都答且弱项 <3；gap_map.md 有 `## 评测盲区`、`## 邻域默认假设`（可写"未知：查过…"但小节必须在）和 `## 判定`（verdict go|no-go、claim_source gap#X|transfer#Tn、reason）；transfer_scan.md ≥5 个候选、七列齐、域内计数已填（`count` 子命令写入，格式 openalex+local）；verdict go 时至少 1 个候选过三道判定（计数 ≤2 + 对应物非空 + 失效点非空），且 claim_source 指向的行必须过三道判定；verdict no-go 直接 PASS，不进 P2。prereg §1 必须写 `来源: gap#X|transfer#Tn`（规则前锁定的 prereg 降 WARN）。
为什么：创新点有五个来源（前人明文假设、邻域方法的失效点、评测口径漏洞、自己实验的反常、两领域常识矛盾），原流程只机械化了第一个；遥感项目的主张其实来自第二个（DOFA 的波长条件化），但那是读文献时碰巧带出来的，不是流程强制的。另外原 G1 只要求 gap_map 有 3 个候选，不允许回答"这个方向不值得做"。
测试：模板原样 3 FAIL；填 5 行（2 过、3 淘汰）ALL PASS；claim_source 指向淘汰行 FAIL；改 no-go 后 PASS。
第②③道判定的机械部分（2026-10-11）：对应物与失效点两格按**形状**判，词表 = transfer_scan 的领域词行 + problem_table.csv 全部文本格 + gap_map + prereg，减去架构通用词（transformer/attention/encoder/backbone…）。对应物：含 ≥1 个领域词、不全是架构词、不是问题结构列的复述。失效点：≥4 个内容词、含领域词、含失效谓词（not/fails/assumes/leaves/depends/因为/失效…）、不是"还没人用过"（那是第①道）、不是对应物的复述。作者写 淘汰 的行不判（作者的否决优先）；写 候选/选定 而形状不成立的行 FAIL；claim_source 指向的行必须过形状判定。校准：验证轮 5 的 RS_nowcast 行——DOFA 两格过，OmniRSCLIP 无对应物、SMARTIES 失效点无领域词、"both use ViT / not yet applied" 两格全败，与当时的人工判定一致。
漏法：形状对不等于失效点为真（"DOFA 假设相邻波段信息互补"写得出来但可以是错的）；判定只能保证写了一句"目标领域的 X 让它在 Y 上坏掉"这种形状的话。候选里 arXiv 未录用的标 INFO 不拦。
2026-10-08 二次扩充（来源：用户给的《人工智能科研论文创新点寻找方法》，采纳了其中可机械化的四条：问题表 + 反复缺口计数、失败案例分析、"值不值得做"五维、§0 现象先于方法；未采纳的是纯写作模板与阅读清单——写进 SKILL.md 原则行即可，不设关口）。

## G2 预注册八项
判据：`scripts/prereg_check.py` 全绿。§0 phenomenon：缺则 WARN，有则必须含 现象/原因/对照 三行（缺 FAIL），最小对照未做 WARN；§1 无原因词（因为/because/机制）WARN；§1 须写 `来源: gap#X|transfer#Tn`（规则前锁定的降 WARN）。八个小节齐全且非空；denominator 与 inclusion_window 写明"跨数据集相同"或列出差异；baselines/ablations 表 ≥1 行；success 含最小改进量（数字+指标）与统计判据（≥3 seeds / CI / 检验）；failure 含备选 claim；事前预测带符号；sha256 与 state 锁一致；state 已有 run 而未锁 → 事后注册 FAIL。脚本同时打印目标刊的 venue-norms 行供对标。测试：在一份合格 prereg 上去掉一致性声明与统计判据并伪造 3 个 run，6/6 抓到。
为什么：分母与窗口两项最常被事后改动。症状是"换一个实现数字就动"，根因是归一化分母在不同数据集里含义不同。
漏法：同一项目犯过两次分母不一致；接触窗口 |F|≥0.1 N 的口径未写死时，全量口径得出三类相反结论。

## G3 三项审计 + 完成度（`scripts/audit_check.py`，全部机械）
远程实验包（`scripts/bundle.py`，用户上传跑的工作流）：runs/ 为空时 G3 由 `bundle.py check` 顶上——矩阵 ⊇ prereg §5 基线与 §6 消融、seeds ≥ min_seeds 且参照方法多 seed、矩阵里无 run 打开 leak_flags、每个数据源有 remote 路径与 inputs、eval 命令已配。`make` 生成的 check_env.py 在服务器上逐 clip 核对 inputs（clip_glob 限定用到的子目录），任何 MISS 退出非零；run_one.sh 先写 hardware.json 与 manifest.json 再训练；`tables` 回表时拒绝 manifest 与包不一致的 run。本地验证：EAAI 项目 15 run 矩阵 check 全绿，check_env 第一次把 data_B 的 12 个未用 clip（Free/Palpation/Traction 无 frames）报成 MISS——这是对的，加 clip_glob 后 ENV OK；smoke.sh 在 A2000 上跑通一 epoch + eval。
配置在 state 的 `audits:` 段。判据与漏法：
### 泄漏
判据：主表 run 的 `leak_flags` 全 0；split_files 的 train/test 分组 id 交集为空；`train_test_split(...)` 无 `groups=` → WARN；`compute_stats|fit(|Scaler` 一行里出现 test/target/concat/tr_sets → WARN（标签相关统计量只能来自源域训练集）；`min_group_size` 以下分组必须丢弃。
漏法：`use_B_train=1` 的 run 主表全部作废；`compute_stats(tr_sets)` 把目标域力标签的一二阶矩带进反归一化（train.py:128 现已拆开）；G5 退化分组溢出。
### 有效配置
判据：`critical_params` 每项，args 为真 ⇒ 日志证据列存在且非零，否则 FAIL；args 为 0 却证据非零也 FAIL；静态点名 `flag and a.param` 门控。
漏法：args.beta=0.1 但 `lam = a.beta*... if (is_ours and a.beta>0) else 0`，五个基线从未生效（train.py:173）。关口在 22 个 run 上把 8 个基线 run 全部报出。
### 静默降级
判据：AST 扫描 `exists()/isfile()/isdir()` 的 If / IfExp / 列表推导，两个分支都不含 raise/assert/exit → 报警；判断里的字符串字面量命中 `inputs` → FAIL；同文件内"存在性判断查的字面量"与"open/np.load 读的字面量"不是同一输入 → FAIL。ckpt/log/cache/输出类路径降 INFO。`--smoke`：复制 smoke_data、删掉一个 inputs、跑 smoke_cmd，退出码 0 → FAIL。
漏法：datasets.py:125 判 `frames/` 存在，:88 读 `frames_256.npy`，集群 12 个 run 全程无视觉。
### 完成度
判据：log 条数 ≥ args[epochs_key]，否则 FAIL；`hardware_key` 未记录 WARN、主表混用 FAIL。
漏法：train.py 不删 ckpt，abl_no_missing 只跑了 6/20 epoch 但 last.pt 在。
回归：22 个 run 全部审计 26 FAIL（6 泄漏 + 16 基线参数未生效 + 2 静默降级 + 1 未训完 + 1 split 未导出），限定到 11 个清洁 run 后只剩 6 条基线 beta/alpha 报警，这是正确的：基线 args 里写了 0.1/0.5 但从未生效，论文方法节不得照 args 抄。

## G4 结果可回溯（`scripts/results_check.py` + `scripts/ablation_plan.py resolve`，全部机械）
消融分辨率：Δ/(σ_ref·√2) < 2 的格不可解读；可解读格数 ≤ 1.5 × 零假设期望（0.0455 × 格数）→ 整体在分辨率极限；可解读且反号 → FAIL。参照来自 main.csv 同硬件 ≥2 seeds，单 seed 参照直接 FAIL。
配置在 state 的 `results:` 段。
判据：main.csv/ablation.csv 每行 run_id 的 `eval_file` 存在、`metric_map` 每列与文件按 CSV 小数位相等、eval 的 mtime ≥ `freshness_ref`、无 `_tainted`；`primary_metric` 是表列且在 prereg §2 出现；prereg §3/§4 的口径记号（如 `|F|≥0.1 N`、`contact-window`）出现在表头或同名 .md 注释；每个 `group_key` 的 seed 数 ≥ `min_seeds` 或 `seed_waiver` 非空，seed 集合跨方法一致；ablation 项 ⊇ prereg §6、方法 ⊇ prereg §5（词元模糊匹配，容忍 "no_dom" vs "no_dom (domain adversarial)"）；`predictions` 的 (b−a) 符号与事前一致。
失败分析：results/failure_slices.md（`failure_slice.py` 对本文方法的输出）缺则 WARN。最差切片是总体几倍、最差 10% 样本占多少平方误差、sig 对 top-10% 误差的 AUROC，三者进正文。真实数据：EAAI 力估计 E5 平台迁移，本文方法（无域项）94% 的平方误差落在 |F| 最高五分位、AUROC 0.867（失败可预测），VS 基线 AUROC 0.547（对失败无感）——这本身就是一段可写的失败分析。
反常触发器：`results.predictions` 符号反转、或 `results.reproductions` 的基线复现 |Δ| > tol（默认 2×reported_std）时，findings.md 里必须已有含该方法名与指标名的条目，否则 FAIL（有则 WARN，正文必须解释）。为什么：多数人把基线复现偏差和反号当 bug 修掉，实际上一半的时候它是论文；先记录再动配置，才留得下证据。
附加规则（仍写在 SKILL.md，脚本不查）：训完看 log 条数（已在 G3）；参数量用加载真实 ckpt 的函数；不同 GPU 进 repro.csv；零结果先查分层变量量程；对照实验分解后才可写进论文。
漏法：评估早于训练结束（_stale_preds 目录里 2212 N 的成因）；eval.json 带 _tainted 仍被 make_tables 读入；S/V/VS 基线单 seed 却与三 seed 的本文方法同表配对比较。
## G5 图
判据：`dpi = pixel_width / (print_width_mm / 25.4) ≥ 300`；295.5–300 容差带、<40 mm 宽或 <15 mm 高的小图降 WARN（275 篇校准：Nature 印刷版 90/130 张落在 295–300，是版面缩放舍入；ICML 46 张 <150 dpi 全是公式与 logo）；figures.csv 每行有 source 列；state.figure_inspect 每张图一条目测记录。
为什么：matplotlib 的 figure.dpi 是屏幕值，九张图曾全低于 300 而屏幕上看不出来。
漏法：字号达标的图照样有版面缺陷，无自检的图每张至少一个：图例穿线、图例溢出、刻度粘连。

## G6 正文六项
### refs
bib 解析支持嵌套花括号与无尾逗号；DOI 从 doi/url 字段抽，arXiv 编号从 note/url/journal 字段抽（很多 bib 把 arXiv 写在 note 里）。CrossRef `works/{doi}` 取 title，与 bib title 做序列比率，<0.85 判 FAIL。PubMed 走 efetch 时限定 `PubmedData` 下的 ArticleId，否则会取到该文参考文献的 DOI。
没有任何标识符的条目（NeurIPS/ICML/JMLR 老文常见）报 FAIL，处理是补 DOI 或 arXiv 号，不是加白名单。
### floats
题注标签本身不算引用，但题注正文里引用别的图算；"Tab. 7 of the supplementary" 这类前后 40 字符含 supplement/appendix 的引用降为 WARN。在 7 篇已发表顶会论文上验证：三篇 NeurIPS 共 11 张图（首页 teaser、附录画廊）正文零引用，两篇 IEEE 全部被引用，判据与 IEEE 制作编辑一致。
编号带字母后缀（9a/9b/9c）折叠到父编号 9；S 前缀是独立命名空间，补充材料题注用 `--supplement supp.md` 登记，否则正文引用 Table S3 只给 WARN 不给 FAIL。
正则抓题注 `^(Fig\.|Figure|Table)\s*(\d+)` 得到存在集合；正文抓引用 `(Figs?\.|Figures?|Tables?)\s*[\d,\s–\-and]+` 并展开成组；题注行本身排除；存在集 − 引用集 = 孤立浮动体，引用集 − 存在集 = 悬空引用，两者皆 FAIL。
### acronyms
state 的 `target.field` 填 cv/ml/medimg/nature 时自动加载 `references/acronym-norms.csv`（275 篇校准：同领域 ≥70% 已发表论文从不展开的词）；摘要内未展开单独 FAIL。先剥 URL 再抓；NA/TBD 内置白名单。七篇已发表论文上每篇报 30–66 条、真阳性 0–4 个，第二次确认无白名单不可用。
**综述类稿件假阳性极高**（InfoFusion 稿 191 报 7 真）：数据集名、方法名、期刊名、Table 的 venue 列全是大写串。先在 state 的 `acronym_ok` 登记项目专名，再跑；对"摘要内缩略语"单独看一眼，Elsevier 的 Guide 把"摘要内未定义的非标准缩略语"列为硬规则。
先截掉参考文献表（从 `^## References` 或 `^\[1\]` 起）；缩略语 = ≥2 个大写字母的连续串且前后非数字；展开 = 括号内出现该串或括号前的词首字母序列匹配；判据展开 offset ≤ 首现 offset。
漏法：RMSE 作为主指标出现 28 次从未展开；NLL 在 5.2 节才展开，比首现晚 26k 字符，整篇出现检查会放过它。
### scope
两级：`SCOPE_STRONG` 搭配打 CLAIM 行，其余 `SCOPE_WORDS` 只计数。275 篇校准见 calibration-275-papers.md。原词表：best, first, novel, all, always, never, consistently, outperforms, state-of-the-art, significantly, robust, general。只报行号，由人逐条回表：主张的数据集、口径、表号是否与 claims.csv 一致。核对结果写入 state.scope_audit。
### numbers
溯源模式：`paper/numbers.csv` 每行 `value,file,key[,transform]`。csv 的 key 写 `col=val,col` 选唯一行，json 的 key 写点路径；transform=pct 表示结果是比例、正文是百分数。脚本取值 → 四舍五入到正文小数位 → 必须完全相等。表格里任何带小数的数字不在 numbers.csv 即 FAIL。
为什么不用"正文数字是否出现在结果文件集合里"：在 EAAI 真实稿上实测，结果池 3109 个值时把三个数各改一个最小单位，集合匹配 0/3 抓到。密集的结果池让任何数字都能找到邻居。只有逐格溯源才有区分度。
四种错法已验证可抓：正文改了结果没改、结果重跑了正文没跟、映射指错行、新增数字未登记。
### limits
字数、摘要字数、关键词数、参考文献数、图表数与 state.target 比对。

## G6b 各节必写清单（`scripts/draft_plan.py check`，机械）
判据：paper/draft_plan.json 的每一项在指定章节里有对应（name 项精确词边界匹配；numbers 项数字逐个在；number_pm1 项允许 ±1 取整；regex 项按措辞；tokens 项内容词重合 ≥60%）。章节按标题别名定位（Introduction/Method/Experiments|Results/Discussion|Limitation），找不到的退化为全文搜索并 WARN。≤2 字符的名字匹配不可靠，降 WARN 要人工确认。正文里 `>` 开头的编辑日志行先剔除。
为什么：G6 查的是"写了的数字对不对"，不查"该写的有没有写"。清单来自 P1–P4 已有产物，所以"引言必须点名 GeoCenter 的失效点"这类要求不是凭空定的。
测试：EAAI 稿 20 项 17 过（3 项是单字母基线名 S/V/VS 降 WARN）；删掉消融节的分辨率措辞后 RES18 FAIL。RS_nowcast 无正文时 plan 出 38 项，可作写作提纲。
漏法：只能查"有没有提"，不能查"提得对不对"；tokens 重合 60% 对长句偏松。

## G6c 稿件形状 vs 家族画像（`scripts/shape_check.py`，机械）
family 来自 state.target.family，否则按 venue 名推断（Nature/Science/npj/Sci Adv → nature；CVPR/NeurIPS/ICML/ICLR/AAAI/MICCAI/ECCV/ICCV → cs_conf；其余 cs_journal）。画像数据 `references/venue-profiles.md`（`scripts/venue_shape.py` 对 275 篇提取，逐篇 `venue-shape-per-paper.csv`）。
判据 nature：顺序 Results → Discussion → Methods（FAIL）；无 Related Work / Conclusion 节（FAIL）；无贡献列表（FAIL）、有 "Here we show"（WARN）；摘要 > 限×1.6 FAIL、> 限 WARN、含引用 FAIL；Results 句式小标题 ≥2（WARN）；引言/结果/讨论无编号公式（FAIL）；"state-of-the-art" / "ablation" WARN；Discussion 占正文 <6% FAIL、<12% WARN；含数字段落带统计 ≥50%（WARN）；"we" ≤12/千词（WARN）。
判据 cs_conf / cs_journal：缺 Intro/Experiments FAIL、缺 Method/Conclusion WARN；顺序 Intro < Method < Experiments < Conclusion；贡献条目 3–5（有 contributions 句但 PDF 丢项目符 → WARN）；Ablation 小节（有正文 ablation study 无小节 → WARN）；方法节公式 ≥3（WARN）；摘要 120–220/250（+3%）；引言 ≤25%；cs_journal 缺 Related Work / Discussion 子节 WARN；cs_conf 无 Limitations 段 WARN。
共同：正文词数在家族中位 ±60% 外 WARN；参考文献 > ref_max FAIL。
为什么：同一份内容投三类刊要三种写法；CS 稿投 Nature 最常犯的五项（Related Work、Conclusion、贡献列表、公式、SOTA 词）全部机械可查。原来只有 limits 关口查字数，没有查"形状"。
测试：6 篇 Nature 系 OA 论文（JATS 转换，Nat Commun ×4、Nat MI ×1、Nat Med ×1）5 篇 ALL PASS，1 篇 FAIL 是它真的有 Conclusion 节（Nat MI 允许）；3 篇 CS（CVPR/NeurIPS/TPAMI PDF 转换）顺序与摘要全过，贡献条目与消融小节因 PDF 丢项目符/小标题报 FAIL——对作者 markdown 稿不存在这个问题，EAAI 稿 ALL PASS；EAAI 稿按 nature 判 8 FAIL，全部正确。
校准过程改掉的阈值：Nature 已发表摘要中位 150–230（投稿限 150 但出版后常超），改为 >1.6× 才 FAIL；Nat Med 的 Results 小标题是名词短语，句式小标题从 ≥3 FAIL 降为 ≥2 WARN；"state-of-the-art" 在 Nature 系 20% 出现，降 WARN；Discussion 占比 6–12% 之间降 WARN。
漏法：查的是形状不是内容；"Here we show" 可以写了但主张不对；JATS 的 Nat Med 稿 Results 用名词短语不违规。

## G6d LaTeX 投稿形态（`scripts/latex_check.py check`，机械；只对 paper/latex/main.tex 存在的项目）
判据：documentclass / style 与 references/latex-templates.csv 里目标刊的模板一致（WARN；state.target.latex_class 填了且不符 FAIL）；每个 \includegraphics 解析到存在的文件（FAIL）且扩展名 ∈ state.target.figure_ext（默认 pdf，FAIL）；含 ≥2 张图的 figure 必须用 subfigure / \subfloat（FAIL）且 subcaption 或 subfig 已加载（FAIL）；题注带面板字母 (a)(b) 而只引用一个文件 = 预合成组合图（FAIL）；\ref 全部有 label（FAIL）；float 无 \label（WARN）；图未登记 figures.csv 或印刷宽度与 LaTeX 宽度差 >5%（WARN）；\bibliography 的 .bib 存在（FAIL）；paper/manuscript.md 比任一 .tex 源旧（FAIL，关口会检查过时正文）。
为什么：出版社要的是矢量图与可编辑源文件；预合成的组合图一改一个面板就要整图重出，且子题注字号与正文脱节；figure 里塞两张图不用 subfigure 则无法被 \ref 到面板。版心宽度从模板实测（`latex_check.py widths --tex`），figures.csv 的印刷宽度才是真的，G5 的 dpi 才算得对。
漏法：以前 LaTeX 稿只能靠 tex_to_md 转 md 后过文字关口，图的格式、组合方式、class 是否对刊无人查；manuscript.md 过时了也照常 PASS。

## G7 审稿闭环（`scripts/review_check.py`，机械）
判据：review_log.md 每条 [major]/[minor] 有处置（同行或后两行的 复核通过|已改|rebut|partial|自证，或在 Phase 2 编辑综合表里按 R1-3 编号出现）；每条 major 在 `## Re-review` 小节里按编号或前 12 字 + closed/已改 关闭（inline "→已自证" 也算）；state.review.round ≥1 且 open_major 空；gate_report.md 新于 manuscript.md；处置里的 §x.y / Table n 在正文存在（缺 WARN）。
测试：EAAI 真实 review_log 7 条全绿；追加一条无处置 major → 2 FAIL；加 Re-review 关闭后 ALL PASS。
为什么：修订会引入新的数字与新的引用，第一次过关不代表第二次过。

## G8 投稿文件
判据：标题页、cover letter、highlights 中出现的每个数字在正文中出现；盲稿 grep 作者姓、单位、邮箱、基金号、"our previous"、"we previously" 为空；文件清单与 guide.txt 的 required files 逐项勾选。
为什么：投稿文件是独立文件，裸 [n] 解析不到，正文改了数字它们不会跟着动。
漏法：cover letter 里的性能数字停在上一版；新关口上线时做反向对照（故意制造一处不一致确认能抓到）。

## 综述分支关口（`scripts/survey_check.py`）
### G-S0
state.survey 的 scope_in / scope_out / axis / thesis 非空；guide.txt 在。漏法：5 月 synopsis 四维并列被编辑批为"目录"，根因是没有 thesis。
### G-S1
search_log.json 每源有检索式+日期+计数；candidates.csv 每行有标识符；prior_surveys.csv ≥1 行且每行 how_this_differs 非空。漏法：PubMed E-utilities 在 retstart 10 000 截断，要按年切片。
### G-S2（protocol）
inclusion/exclusion 每条含可判定词（阈值、数量、年份、"such as"、"covered by [n]"）；codebook 每字段有取值集合或标明 free text/float/int（`{...}` 内为集合，"joined/subset" 表示多值用 `|` 连接）；claims 表每条有可从 coded.csv 算出的判据；κ 计划；sha256 锁。在 InfoFusion_multimodal 真实 codebook 上：22 字段全部解析。
### G-S3（coding）
screening 每行 decision ∈ {include, maybe, exclude} 且有 reason；已决行必有标识符；coded.csv 每字段取值 ∈ codebook（多值字段拆 `|` 后逐个查）；PRISMA 五个计数单调且 included = screening include 数；κ ≥ min_kappa。在 InfoFusion_multimodal 真实数据上：抓到 mechanism 列 68 个值（nomogram/late/LR/stacking/ensemble…）与 metric 列 177 个 AUC 不在 codebook 集合——codebook 写的是 AUROC，编码时全写成 AUC，正文汇总按哪个算就是口径问题。
### G-S5（claims）
claims.csv 每条 evidence_file#evidence_key 能取到值且满足 expected 判据；first/only 类主张必须有 prior_surveys.csv 且每行写明差异；tables/ 必须有 *summary*.py 生成脚本。
