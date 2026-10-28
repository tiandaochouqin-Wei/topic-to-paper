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
### 随机性（`audits.stochastic_keys`）
判据：`stochastic_keys: [aug_seed, aug_hash]` 列出日志里每 epoch 写入的增强种子/哈希键，每个键在一个 run 的 epoch 之间必须出现 ≥2 个不同值，全程同一值 → FAIL「全程同一值 —— 随机增强/采样每 epoch 相同」，日志里没有这个键 → FAIL（同有效配置的「无证据列」）；没登记 stochastic_keys 而代码里有 `persistent_workers=True` 或 `worker_init_fn` → WARN。
漏法：cvpr2027_fusion 的 persistent dataloader worker 永远没拿到 `ds.epoch`，增强每 epoch 相同，比 Ultralytics 参考实现低 2.8 AP，靠人工对账才发现。
### 审计集收窄
判据：`main_table_runs` 非空且排除了 runs_dir 下 ≥1 个 run → WARN 并列出被排除的数量；`experiments.convention_changes` 里有条目提到 `main_table_runs` 则改为 PASS 并引用它。
漏法：cvpr2027_med2 把 146 个 FAIL 通过收窄审计集变成了 PASS，而头条数字来自审计集之外的 run。
### 完成度
判据：log 条数 ≥ args[epochs_key]，否则 FAIL；`hardware_key` 未记录 WARN、主表混用 FAIL。
漏法：train.py 不删 ckpt，abl_no_missing 只跑了 6/20 epoch 但 last.pt 在。
回归：22 个 run 全部审计 26 FAIL（6 泄漏 + 16 基线参数未生效 + 2 静默降级 + 1 未训完 + 1 split 未导出），限定到 11 个清洁 run 后只剩 6 条基线 beta/alpha 报警，这是正确的：基线 args 里写了 0.1/0.5 但从未生效，论文方法节不得照 args 抄。

## G3b 仪器校准（`scripts/instrument_check.py`，全部机械；仅研究分支）
配置在 state 的 `instruments:`（schema 与示例见 templates/research-state.yaml）与 `instruments_waiver:`。
判据：① 静态扫描 `audits.code_dirs` 与项目内其它 .py（runs/results/data/literature/paper/figures/bundle 除外；cvpr2028_gcv 的实验代码在 ma_p3/、killtest_*/，只扫 code/ 会静默通过）的加载点（优化器/scaler/scheduler/EMA 的 load_state_dict 不算）（`from_pretrained(`、`load_state_dict(`、`torch.hub.load(`、`timm.create_model(`、`open_clip.create_model`、`create_model_and_transforms(`、`AutoModel*.`、`YOLO(`、带 ckpt/checkpoint/.pt/.pth/weights 的 `torch.load(`、`safetensors`、`hf_hub_download(`、`snapshot_download(`；跳过 tests/、venv、site-packages、`_` 开头的文件、注释行）：每个命中必须被某条 instrument 的 `match`（正则，对文件路径或行文本）或某条 waiver 覆盖，否则 FAIL「未校准的仪器 file:line」；waiver 命中降 WARN 并打印理由（自己的 checkpoint：`{match: "resume|runs/", reason: "own checkpoint"}`）。② 每条 instrument：`check.output` 存在（否则「未跑校准」）；输出不得早于它覆盖的代码（「代码改过、校准未重跑」）；`key` 的读数落在 `expected±tol` 或 `[min,max]` 内，否则 FAIL「仪器读数 v vs 已知 e±t」，缺已知答案也 FAIL；`broken`（同一校验、故意破坏输入）必须存在，且读数在容许带**外**，落在带内 = FAIL「校验区分不了正确与破坏的输入」；输出 json 的 `applied_contract` 与登记的 `contract` 逐键相等（列表逐元素，字符串忽略大小写和空白），缺 applied_contract 或 contract 缺 source 降 WARN；各 run 的 args.json 若记了 `contracts: {name: {...}}` 也同样核对，没有任何 run 记 → WARN 一次；contract 含 axcodes/channels 时 `dump` 必须存在且 `inspected: yes`。③ `kind: train_loop` 没有已知数字，改要 `reference:{output,key,expected,tol,source}`（参考实现在同一划分上的结果），值规则同上，`broken` 可缺（WARN）。
为什么：仪器出错时，所有下游关口（泄漏、溯源、消融分辨率、审稿）检查的都是「这个数是不是由这份代码算出来的」，不是「这份代码算的是不是它声称的东西」。
漏法：cvpr2027_medical 给 SuPreM/VoCo/VISTA3D/SAM-Med3D 喂的是 SPL（LPS 系）数组，官方布局是 RAS；跑了 7 天、过了 10 轮审稿和全部关口，最后是 SuPreM 自带的分割头在 RAS 下胰腺 Dice 0.76、在 SPL 下 0.00 才暴露。更早那个「方向测试」得到 0.562（错）vs 0.581（对），根本不可能失败——所以 `broken` 必须落在带外。cvpr2027_fusion 的自写训练循环比 Ultralytics 参考实现低 2.8 AP（29.5 vs 32.3），靠人工对账发现。

## G4 结果可回溯（`scripts/results_check.py` + `scripts/ablation_plan.py resolve`，全部机械）
消融分辨率：Δ/(σ_ref·√2) < 2 的格不可解读；可解读格数 ≤ 1.5 × 零假设期望（0.0455 × 格数）→ 整体在分辨率极限；可解读且反号 → FAIL。参照来自 main.csv 同硬件 ≥2 seeds，单 seed 参照直接 FAIL。
配置在 state 的 `results:` 段。
判据：main.csv/ablation.csv 每行 run_id 的 `eval_file` 存在、`metric_map` 每列与文件按 CSV 打印精度相等（精度取自单元格的 Decimal 指数，科学计数 `9.07e-05` 也按有效位比；完全相等或差 ≤ 末位半个单位即过）、eval 的 mtime ≥ `freshness_ref`、无 `_tainted`；`primary_metric` 是表列且在 prereg §2 出现；`primary_direction` / `metric_direction` 的值只能是 lower|higher（否则 FAIL），未设且列名正则猜不出方向时 WARN（下游按 higher-is-better）；prereg §3/§4 的口径记号（如 `|F|≥0.1 N`、`contact-window`）出现在表头或同名 .md 注释；每个 `group_key` 的 seed 数 ≥ `min_seeds` 或 `seed_waiver` 非空，seed 集合跨方法一致；ablation 项 ⊇ prereg §6、方法 ⊇ prereg §5（词元模糊匹配，容忍 "no_dom" vs "no_dom (domain adversarial)"）；`predictions` 的 (b−a) 符号与事前一致。
失败分析：results/failure_slices.md（`failure_slice.py` 对本文方法的输出）缺则 WARN。最差切片是总体几倍、最差 10% 样本占多少平方误差、sig 对 top-10% 误差的 AUROC，三者进正文。真实数据：EAAI 力估计 E5 平台迁移，本文方法（无域项）94% 的平方误差落在 |F| 最高五分位、AUROC 0.867（失败可预测），VS 基线 AUROC 0.547（对失败无感）——这本身就是一段可写的失败分析。
反常触发器：`results.predictions` 符号反转、或 `results.reproductions` 的基线复现 |Δ| > tol（默认 2×reported_std）时，findings.md 里必须已有含该方法名与指标名的条目，否则 FAIL（有则 WARN，正文必须解释）。为什么：多数人把基线复现偏差和反号当 bug 修掉，实际上一半的时候它是论文；先记录再动配置，才留得下证据。
基线复现为空：`reproductions` 为空而主表有 reference_method 之外的方法 → WARN「至少把一个基线复现到其论文数字」（所有真实项目里它都是 `[]`；复现不到论文数字时，数字差是你的实现、不是方法；仪器校准见 G3b）。
分诊自证：findings.md 里标题为 `## F#`/`### F#` 的块，只要写了结案结论（`cause: real|impl|data|convention|leak`，或某步 `excluded`/`排除`）就必须有 `evidence:` 行指向项目里至少一个存在的文件，否则 FAIL「分诊结论没有证据文件（命令输出）」；`cause: real` 另需 `control:` 行，缺则 WARN。围栏代码里的示例不算。为什么：自由文本「impl: 排除」是自己给自己结案，没有任何东西可以复核。
口径混用（v2.13）：对主表每个对照集（`results.dataset_key` 列，默认 `dataset`，无此列即整表一个集），读每个 run 的 `results.protocol_keys`（默认 `input_size / split / checkpoint_rule / class_map / evaluator`，取自 args.json，缺则 eval.json / protocol.json）；一个键在集内出现 ≥ 2 个不同取值 → FAIL「混用了不同口径：<键> = {A: [runs], B: [runs]}」，`results.protocol_waiver: {键: 理由}` 把它降为 WARN 并要求正文说明（理由为空不算豁免；`reproductions` 里的复现基线不自动豁免）；键在所有 run 里都没有 → INFO「未登记，无法核对」，只在部分 run 里有 → WARN 列出缺的 run。为什么：医学稿把「模拟配对」与「自有配对」放进同一张表，差距里混着噪声水平的差；融合稿的表里 input_size 640 与 1280 的行并排，逐行都「各自合理」，合起来不是公平对照。漏法：只查 run 真正登记了的键——没写进 args.json 的口径差异看不见（所以未登记给 INFO 而不是 PASS）；取值字符串写法不同（`640` vs `[640, 640]`）会被当成不同值，宁可误报；也不判断不同值是否「实质」不同。
附加规则（仍写在 SKILL.md，脚本不查）：训完看 log 条数（已在 G3）；参数量用加载真实 ckpt 的函数；不同 GPU 进 repro.csv；零结果先查分层变量量程；对照实验分解后才可写进论文。
漏法：评估早于训练结束（_stale_preds 目录里 2212 N 的成因）；eval.json 带 _tainted 仍被 make_tables 读入；S/V/VS 基线单 seed 却与三 seed 的本文方法同表配对比较。
**消融分辨率口径（验证轮 20 新增）**：`ablation_plan.py resolve` 与 `make_figure.py ablation` 识别消融行代表几个 seed——同名消融多行 = 逐 seed 记录（取均值，n = 行数），否则读 `n_seeds` 列，都没有 = 单 run。单 run 仍判 |Δ| ≥ 2σ_ref√2；n 个 seed 的均值判 |Δ| ≥ 2σ_ref√(1/n + 1/n_ref)。为什么：med-world-model 把 10 seed 均值当单 run 喂进去，配对检验 p=0.003 的效应被画成「不可分辨」。

## G5 图
判据：`dpi = pixel_width / (print_width_mm / 25.4) ≥ 300`；295.5–300 容差带、<40 mm 宽或 <15 mm 高的小图降 WARN（275 篇校准：Nature 印刷版 90/130 张落在 295–300，是版面缩放舍入；ICML 46 张 <150 dpi 全是公式与 logo）；figures.csv 每行有 source 列；state.figure_inspect 每张图一条目测记录。
为什么：matplotlib 的 figure.dpi 是屏幕值，九张图曾全低于 300 而屏幕上看不出来。
漏法：字号达标的图照样有版面缺陷，无自检的图每张至少一个：图例穿线、图例溢出、刻度粘连。

**印刷字号（验证轮 15 新增）**：矢量图用 PyMuPDF 读文本层，字号 × (print_width_mm / 原图宽) = 印刷字号；最小值 < `target.min_font_pt`（默认 5）FAIL，< 下限 + 1 WARN，无文本层 INFO。为什么：一张 83 mm 画的图排到半栏 44 mm，字号 3.5 pt，屏幕预览看不出来；G5 以前只查 dpi 和"已目测"，目测看的是放大的 PNG。
**双纵轴**：同一页左右两侧都有纵向轴标签 → WARN（dataviz 规则：两种量纲各画一个面板）。
**图类型覆盖**：按 `target.family` 取 references/figure-norms.md 里 ≥70% 已发表论文含有的图类型（cs_journal：overview / qualitative / comparison / ablation；cs_conf：前三），每种至少命中一条题注（`figure_norms.FIGURE_TYPES` 的关键词规则），否则要在 figures.csv 的 issues 列写 `no <type>: <为什么不需要>`；缺且未豁免 → WARN（题注关键词是启发式，不 FAIL）。为什么：tpami_medimg 关口全绿时没有总览图也没有定性图，同类期刊 89% / 81% 的论文都有。

**字体嵌入（验证轮 18 新增）**：登记的 PDF 用 pypdf 读字体表，含 Type 3 → FAIL，未嵌入 → WARN。为什么：matplotlib 默认 `pdf.fonttype=3`，本 skill 出的每张图都是 Type 3，IEEE / Elsevier 制作部拒收，G5 从没查过。`make_figure.py` 已改默认 42。
**版面自检 + 灰度预览（验证轮 18 新增）**：`make_figure.py` 存图前在内存里渲染一次：缺字 FAIL（退出 1）、文字压到别的面板 / 刻度标签重叠 WARN，结果写进 figures.csv 的 issues；同时出 `_gray.png`，G5 对没有灰度预览的图 INFO。来源：scipilot-figure-skill 的 visual_qa / export_figure。

**图表数量（验证轮 16 新增）**：正文图数、表数各与 `references/figure-norms-per-paper.csv` 里目标 venue（没有则按 family）已发表论文的下四分位比，低于 → WARN；`target.figure_count_waiver` 写明理由即豁免。为什么：med-world-model 稿第一版 1 图 6 表时 G5 全绿，NeurIPS 四分之三的论文 ≥4 图；类型覆盖查的是"有没有"，不查"够不够"。

**方法总览图（2.12 新增，`make_architecture.py check`；`figures/arch/*.yaml` 存在才跑）**：
判据：① 用 spec 里记的 model / init / input / depth 重新 trace，代码 sha 没变 → PASS；变了则节点多重集（类 + 输入输出形状 + 重复数 + 参数量）必须一致，否则 FAIL「图是从旧模型画的」；模型已加载不了也 FAIL。② PDF（与 .tex）里每个词必须是节点标签、类名、阶段名、形状、运算符、×n、数字或 `--allow` 登记的词，否则 WARN「trace 里没有的文字」。③ 图里印了参数量（`render --show-params`）则必须等于 trace 的 params_total，否则 FAIL。④ 图里的阶段名（含 `--merge` 的新名）在 manuscript 的 Method 节里都要出现，缺的 WARN。⑤ spec 的输入分辨率与 ref run 的 img_size / input_size（`runs/<ref>/args.json` 或 state.bundle.matrix.ref.args）一致，不一致 WARN。
为什么：唯一一张概念图（cvpr2027_medical Fig 1 b/c）是不从模型派生的卡通；手画的总览图在代码改动后不会跟着变，与 G3b 的仪器校准、伪代码的 source anchor 是同一个逻辑——图和跑出结果的东西之间要有一条机器可查的线。
漏法：它只能判图有没有说谎，判不了图有没有把方法讲明白（阶段取得对不对、合并得合不合理、该突出的门控有没有突出）；形状和参数量一致不代表数据流画对了，tensor 身份追踪会把不可追的运算（`.item()`、numpy 往返）断开；Fig 1「现有 vs 本文」这类对比示意仍由 make_motivation.py schematic 画，不在本检查范围；印刷字号仍由上面的字号检查判（总览图太宽缩到 5 pt 以下会 FAIL）。

**图表计划（2.13 新增，`figure_plan.py check`；`paper/figure_plan.csv` 不存在 → 一条 WARN，旧项目不受影响）**：
判据：① 没有计划 WARN；范文 `literature/exemplars/exemplars.csv` < 3 篇 WARN；② 计划里 `kind=figure` 且未 dropped 的每一行，`files` 列要在 figures.csv 里有对应行（同名，或 `x_a`/`x_b` 面板对应 `x`；figures.csv 另有可选列 `plan_item` 写 `Fig N` 也行），否则 FAIL「计划里的 Fig N 还没画」；`status=dropped` 的行 `note` 为空 FAIL；③ figures.csv 里没有任何计划行覆盖的图 WARN「它支撑哪条主张」；④ 带数字的主张（evidence_key 非空或 expected 含数字）没有计划行承载（claim_ids，或 claims.table_or_figure 指向该行的 Fig/Table）WARN；⑤ 计划行引用的 claim_id 在 claims.csv 里已不存在 FAIL。
为什么：P5 以前只按刊物平均数选图（『82% 的 CVPR 论文有总览图』），既不知道同主题论文怎么开场、怎么排版，也没有任何东西把图表和主张连起来——有主张没图承载，或有图不服务任何主张，都是靠人眼发现的。
漏法：判不了图有没有把它的主张讲清楚；范文由标题上的 BM25 选，可能漏掉最接近的那几篇，用 `--pdf` 补；角色按题注关键词判定，题注写得含糊的图会落进 analysis；图的单/双栏宽按图像与矢量元素的外框估算，纯文字图或整页背景图会判不出。

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
判据：paper/draft_plan.json 的每一项在指定章节里有对应（name 项精确词边界匹配；numbers 项数字逐个在；number_pm1 项允许 ±1 取整，负值写 `-4%`/`−4%` 或绝对值加同句方向词（`4% worse`、lower-is-better 指标的 `4% higher`），正值的 `4%` 不能嵌在 `-4%` 里，`3-4%` 这种区间的连字符不算负号；regex 项按措辞；tokens 项内容词重合 ≥60%）。章节按标题别名定位（Introduction/Method/Experiments|Results/Discussion|Limitation），找不到的退化为全文搜索并 WARN。≤2 字符的名字匹配不可靠，降 WARN 要人工确认。正文里 `>` 开头的编辑日志行先剔除。"ours 相对最强基线"一项按所有方法共有的 seed 求均值（先按 seed 平均，只在部分方法出现的 seed 不计，清单行写明用了哪些 seed）；最强基线 = 主指标上最好的非 ours 方法，方向依次取 `results.metric_direction[<列>]` > `results.primary_direction` > 列名正则（`scripts/metric_direction.py`：rmse/mae/error/loss/…/drop/delta/shift/gap/degradation/decline/asr → lower，其余 higher）；正则猜错会把最差方法当成最强基线（cvpr2027_medical 的 delta_rel_Ta，2026-10-15），所以 delta/drop 类主指标要在 state 里写明方向。
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

## G6e 主张层（`scripts/claims_check.py`，机械；2026-10-11）
判据：paper/claims.csv 每行 = 一条主张；有 evidence_key 的行机械算值并按 expected 判（`rel:<metric>:<a>:<b>` 相对变化 %、`delta:` 差、`z:<metric>:<a>` 消融分辨率 |Δ|/(σ_ref√2)、`mean:`、numbers.csv 式单格、json 点路径；expected 取 `<x <=x >x >=x ==x x±t + −`）；无 evidence_key 的定性行 WARN 永不 PASS（审稿席位人工回看）；主张里的数字必须在正文出现；有 table_or_figure 的主张必须在该题注所在节被陈述（词元重合 ≥50% 或共享数字）；nature 稿的 "Here we show" 句必须对应一行（FAIL）、句式小标题各对应一行（WARN）；CS 稿每条贡献条目必须对应一行（FAIL）、摘要与某行共享数字（WARN）；正文每句本文自述的强作用域主张（gate_check 的 SCOPE_STRONG，且句里有 we/our/proposed）必须对应 scope_words 非空的一行（FAIL）；`rel:` 主张低于 prereg §7 最小改进量 WARN（§8 备选生效，正文须说明）。
为什么：G6c 只能查"有没有一句 Here we show / 有没有贡献列表"，查不了"这句话说的事是不是数出来的"；lessons 里"审稿人第一击是'你说最好，哪个表'"原来靠 scope 关口列出行号后人工回表，现在回表本身是关口：强作用域句 ↔ claims 行 ↔ 表 ↔ 结果文件四段连通才 PASS。
测试：夹具 5 行（3 量化 PASS、2 定性 WARN）ALL PASS；expected 改成与结果相反 FAIL；不可分辨格写成有效 FAIL；有 key 无 expected FAIL；主张数字与正文不同步 FAIL；贡献条目无对应行 FAIL；加一句 "outperforms all existing" 无 claims 行 FAIL、登记 scope_words 后 PASS；table_or_figure 指错节 FAIL；nature 的 Here-we-show 句无对应行 FAIL；prereg §7 改 25% 后 WARN。
漏法：定性主张（§0 对照实验、协议类主张）仍是人判；词元重合 50% 对改写过的句子可能漏；`z:` 用的是单 run 消融 vs 参照 seeds 的分辨率，多 seed 消融应改用 delta: + 检验。

## G6d LaTeX 投稿形态（`scripts/latex_check.py check`，机械；只对 paper/latex/main.tex 存在的项目）
判据：documentclass / style 与 references/latex-templates.csv 里目标刊的模板一致（WARN；state.target.latex_class 填了且不符 FAIL）；每个 \includegraphics 解析到存在的文件（FAIL）且扩展名 ∈ state.target.figure_ext（默认 pdf，FAIL）；含 ≥2 张图的 figure 必须用 subfigure / \subfloat（FAIL）且 subcaption 或 subfig 已加载（FAIL）；题注带面板字母 (a)(b) 而只引用一个文件 = 预合成组合图（FAIL）；\ref 全部有 label（FAIL）；float 无 \label（WARN）；图未登记 figures.csv 或印刷宽度与 LaTeX 宽度差 >5%（WARN）；\bibliography 的 .bib 存在（FAIL）；paper/manuscript.md 比任一 .tex 源旧（FAIL，关口会检查过时正文）。
为什么：出版社要的是矢量图与可编辑源文件；预合成的组合图一改一个面板就要整图重出，且子题注字号与正文脱节；figure 里塞两张图不用 subfigure 则无法被 \ref 到面板。版心宽度从模板实测（`latex_check.py widths --tex`），figures.csv 的印刷宽度才是真的，G5 的 dpi 才算得对。
漏法：以前 LaTeX 稿只能靠 tex_to_md 转 md 后过文字关口，图的格式、组合方式、class 是否对刊无人查；manuscript.md 过时了也照常 PASS。
G6d 的伪代码块检查（`scripts/make_algorithm.py check`，paper/latex 里有 algorithm 环境或 state.algorithms 有行时由 latex_check.py 调用，FAIL/WARN 并入 G6d）：
判据：① 包与命令族一致：有 algorithm 环境就要 `\usepackage{algorithm}`（或 algorithm2e）；algorithmic 环境要 algpseudocode / algorithmic；`\State` 属于 algpseudocode、`\STATE` 属于 algorithmic、`\KwIn` 属于 algorithm2e，错配或 algorithm2e 与 algorithmic 同时加载 = FAIL。② 每块有 `\caption` 和 `\label{alg:..}`（FAIL），label 在正文被 `\ref/\cref/\autoref` 引用（FAIL，同无人引用的图）；manuscript.md 侧 `**Algorithm N.**` 同样要被 "Algorithm N" 引用（gate_check floats，FAIL；引用本稿没有的编号只 WARN，可能在引别人论文里的算法）。③ label 在 state.algorithms 里没有行 = WARN "没有 source 锚点"；行的 source 文件或函数不存在 / 解析失败 = FAIL。④ 符号：块里的 `\texttt{..}`、含 `_` 或数字的文字记号、没有在块内定义的 Greek 符号，必须是 params 键或 source 函数的标识符（名字 / 参数 / 属性 / 调用），否则 WARN。⑤ `\Require` 里 `符号 = 数值`（或 `\gets`）且符号在 params：数值必须等于 ref run 的值（bundle.matrix.ref.args 的 `--key value`，没有则 runs/<ref>*/args.json），不等 FAIL，ref run 里没有这个键 WARN。⑥ 形状：函数前两层的循环数多于块里的 `\For/\While` = WARN；≥3 个 if 而块里没有 `\If` = WARN；> 30 个编号行 = WARN；skeleton 占位（空 `\State`、`\For{$\ldots$}`）没改 = WARN。⑦ `\State` 等语句行里出现 ≥3 位有效数字的数 = WARN（伪代码不写结果数字）。
为什么：凭记忆写的伪代码描述的是想要的方法，不是跑出结果的那个——超参改过、循环被删过、顺序换过，正文和代码就各说各的。把块锚到函数（ast）和 ref run 的参数，同 G3b 的逻辑：不让文字自己为自己作证。
漏法：只比对符号与数值和循环数，不比对语义（把两句话写反不会被发现）；`params` 没登记的超参不对账；Python 以外的代码（C++/CUDA）无法 ast，source 只能指到 Python 入口；块里的 Greek 符号若在块内用 `\gets` 定义过就视为已定义，不再追溯。语料校准（`make_algorithm.py calibrate`，PyMuPDF 取前 14 页的 "Algorithm N" 题注行，每 venue ≤40 篇、2023+、seed 20261023）给出各家族有伪代码的比例，供 G6c shape_check 参考。

## G6f 可读性（`scripts/readability_check.py`，机械；2026-10-23）
判据：正文（Introduction 起，不含参考文献、图表题注、表格、公式、代码、Appendix/Supplement/Protocol/Preregistration 节）的指标对照 references/readability-norms.csv（已发表 CVPR/ICCV/ECCV/NeurIPS/MICCAI/WACV/AAAI、TMI/MedIA/TIP/TPAMI/IJCV、Nature 系各 40 篇，seed 20261023）：摘要数字/缩写/词数、贡献条目数字与字数、引言与全文的数字每千词、分号每千词、平均句长、>40 词句占比。单项 > p90 或 > p95 只 WARN（已发表论文 40 篇里 7–12 篇恰好有一项超 p95）；**≥3 项同时超 p95 FAIL**（已发表样本 2/40）；贡献条目 > 2 个数字 FAIL（P6 规则）。固定规则：流程簿记词（preregist*、registered ablation/prediction…、refuted、falsified、addendum、amendment、convention change、protocol 意义上的 locked、post hoc（非统计意义）、findings.md、G6c 式关口名）> 3 处 FAIL、1–3 处 WARN；引言/相关工作的目录式段落（≥4 引用且 ≥3 分号，或 ≥5 句 "Name [n] …"）每个 WARN、≥3 个 FAIL。正文 < 1500 词时比率指标只 WARN；家族无校准行用 PROVISIONAL 阈值并 WARN。
为什么：三个真实草稿（med2、medical、fusion）每千词 31–52 个数字（已发表 p95 24）、贡献条目 6–14 个数字、流程簿记词 8–17 处，同时超 p95 的指标 7–11 项，而其它关口全过。
漏法：只量表面统计，不判断写得好不好、论点是否成立（那是 P7 审稿的事）；PDF 转换会丢项目符，贡献条目指标在已发表样本里 n 只有 23–25；协议记账换个说法（"frozen before running"）抓不到。

## G6g 论点一致（`scripts/argument_check.py`，机械；2026-10-28；tests/test_argument.py）
判据：`paper/argument.md`（`templates/argument.md`，写稿之前由 claims.csv + prereg 填）对照稿子。① 文件缺失 FAIL「先写论点再写稿」；claim / reader_question / headline / why_not_obvious / strongest_objection / outline 为空或仍是模板 `<…>` 各 FAIL；② claim > 35 词或 > 2 个数字、没有可证伪的动词 WARN；③ claim 须在摘要（任一句）、引言贡献列表之前的末段（Nature 为 "Here we show" 句）、Conclusion 前两句（Nature 为 Discussion 第一段）复现——实词重合 ≥ 50 %，或 claim 的全部数字都在且该处与 claim 共享 ≥ 25 % 实词——缺哪处 FAIL 哪处，标题与 claim 共享 < 2 个实词 WARN；④ headline.claim_id 不在 claims.csv、headline.number 的数字不在摘要里 FAIL；⑤ 引言前两段含 reader_question ≥ 40 % 实词、引言含 why_not_obvious ≥ 30 % 实词（缺 WARN）；⑥ where_answered 指向的 § / Table / Fig 存在，strongest_objection ≥ 30 % 实词出现在那里或 Limitations / Discussion（缺 WARN）；⑦ 提纲项数与引言段数差 ≤ 1，第 i 项（去掉 "move:" 前缀）与引言第 i±1 段重合 ≥ 35 %，顺序不倒（缺 WARN）；⑧ not_claimed 每条在 Limitations / Discussion / Conclusion 出现，headline 数字在引言里出现且与摘要同样取整（6.95 vs 7.0 WARN）。同步改动 draft_plan（G6b）：失效点点名改为 Related Work 或引言均可且 WARN，引言一段引 > 6 篇 WARN，只有 headline 主张的数字强制进贡献条目，argument.md 的 claim / reader_question 进必写清单。
为什么：三个真实 CVPR 草稿（2026-10-23）写作是清单驱动——gap_map 每行变成引言里一句人名，每条主张的数字塞进贡献条目——没有人要求一句话的主张、标题 / 摘要 / 引言 / 结论共用它，也没有人要求写下读者的问题和最强反对意见；读者读完引言说不出这篇论文到底主张什么。
漏法：词元重合只能证明论文前后讲的是同一个故事，不能证明这个论点好、新、对（那是 P7 独立审稿的 R0 席位的事）；同义改写可能把重合压到阈值下（误报 FAIL，改 argument.md 的措辞即可）；一句话里塞对词但逻辑相反（"does not lower"）抓不到；argument.md 与 claims.csv 的主张是否同义不核，只核 headline.claim_id 存在与数字出现；用户自己写的 argument.md 空话（"we propose a better method"）能过 ②。

## G7 审稿闭环（`scripts/review_check.py`，机械）
判据：review_log.md 每条 [major]/[minor] 有处置（同行或后两行的 复核通过|已改|rebut|partial|自证，或在 Phase 2 编辑综合表里按 R1-3 编号出现）；每条 major 在 `## Re-review` 小节里按编号或前 12 字 + closed/已改 关闭（inline "→已自证" 也算；2.9.0 起带否定的句子 `NOT closed` / `未关闭` / `OPEN:` 不算关闭，只靠行内箭头关闭而复审节没提到该编号 → WARN；处置词表加「需新实验 / 待补实验」）；state.review.round ≥1 且 open_major 空；gate_report.md 新于 manuscript.md；处置里的 §x.y / Table n 在正文存在（缺 WARN）。
测试：EAAI 真实 review_log 7 条全绿；追加一条无处置 major → 2 FAIL；加 Re-review 关闭后 ALL PASS。
为什么：修订会引入新的数字与新的引用，第一次过关不代表第二次过。

**独立审稿（2026-10-28 新增，`scripts/review_packet.py` + `review_check.py`；tests/test_review_independent.py）**
判据：① 研究分支至少一节 `## Reviewer <席位> (independent, packet <sha8>)`，否则 FAIL（`state.review.independent_waiver: "<原因>"` 降为 WARN；综述分支默认 WARN；`entry: have_reviews` 的日志是真实审稿，不查）；② 必须有独立的 R0（区域主席 / 价值），带 `rating:`（缺 WARN）；评分均值在拒稿线上（cs_conf ≤ 3/6；期刊 reject 或 major；nature reject）→ WARN「先回证据或选题」；③ 每节的 packet sha8 要在 `paper/review_packet/round*/**/manifest.json` 登记，否则 FAIL（审稿不是在登记的稿件版本上做的）；④ 每条 `[major]` 带 `category:`（缺 WARN）；⑤ evidence / validity / novelty / value 类 major 只能由同一席位的 `## Re-review <席位> (independent, packet <sha8>)` 关闭，且复审 sha8 与原审稿不同（在改后版本上做的）；作者自己写 closed、行内箭头、别的席位关闭、同一 packet 复审都 FAIL，作者段落里带收窄词（收窄|narrow|reword|措辞|scope|限定|弱化|soften）的 FAIL「收窄措辞不是关闭」；有 waiver 且没有任何独立复审节时降为 WARN；⑥ validity 类 major 的关闭行或处置要引用一个存在的文件（故意弄坏的版本上会失败的检查输出），否则 FAIL。
为什么：自审时同一会话带着作者上下文写全部席位——cvpr2027_med2 六条 major 里四条靠收窄措辞关闭，cvpr2027_medical 的输入朝向错误（SuPreM 等四个编码器喂 SPL 而非 RAS）扛过 10 轮自审，cvpr2027_fusion 根本没审；谁也没问过「这个发现是不是已经有人知道、值不值得占一个会议名额」，所以 R0 是必选席位。
漏法：子代理仍是同一模型家族——独立的是上下文，不是判断力，共同的盲点照样共同；sha8 只证明审稿读的是登记过的版本，不证明子代理没有越权打开别的文件（提示里写了禁止，靠自觉）；validity 的「文件存在」不证明它在破坏版上真的会失败（那要 G3b 的 broken 对照或变异测试来保证）；category 是审稿人自己标的，标成 clarity 就绕开 ⑤，所以 R5 综合时要核一遍类别；最终审稿人仍是用户。

## G8 投稿文件
判据：标题页、cover letter、highlights 中出现的每个数字在正文中出现；盲稿 grep 作者姓、单位、邮箱、基金号、"our previous"、"we previously" 为空；文件清单与 guide.txt 的 required files 逐项勾选。
为什么：投稿文件是独立文件，裸 [n] 解析不到，正文改了数字它们不会跟着动。
漏法：cover letter 里的性能数字停在上一版；新关口上线时做反向对照（故意制造一处不一致确认能抓到）。

## 综述分支关口（`scripts/survey_check.py`）
### G-S0
state.survey 的 scope_in / scope_out / axis / thesis 非空；guide.txt 在。漏法：5 月 synopsis 四维并列被编辑批为"目录"，根因是没有 thesis。
2.11：review_type ∈ narrative | scoping | systematic；标题或论点自称 systematic 而 review_type 不是 → FAIL。

### G-S1
search_log.json 每源有检索式+日期+计数；candidates.csv 每行有标识符；prior_surveys.csv ≥1 行且每行 how_this_differs 非空。漏法：PubMed E-utilities 在 retstart 10 000 截断，要按年切片。
2.11：金标准种子召回 `literature/seed_studies.csv`（按 doi/pmid/arxiv_id 或归一化标题匹配 candidates）< min_seed_recall（默认 1.0）FAIL，无种子集 WARN；滚雪球轮次（search_log 中 source 含 snowball/citation 的条目，按记录顺序）每轮记 new_included，最后 saturation_rounds 轮不全为 0 → WARN。为什么：没有金标准，检索好坏无从谈起；种子在看结果前定。

### G-S2（protocol）
inclusion/exclusion 每条含可判定词（阈值、数量、年份、"such as"、"covered by [n]"）；codebook 每字段有取值集合或标明 free text/float/int（`{...}` 内为集合，"joined/subset" 表示多值用 `|` 连接）；claims 表每条有可从 coded.csv 算出的判据；κ 计划；sha256 锁。在 InfoFusion_multimodal 真实 codebook 上：22 字段全部解析。
### G-S3（coding）
screening 每行 decision ∈ {include, maybe, exclude} 且有 reason；已决行必有标识符；coded.csv 每字段取值 ∈ codebook（多值字段拆 `|` 后逐个查）；PRISMA 五个计数单调且 included = screening include 数；κ ≥ min_kappa。在 InfoFusion_multimodal 真实数据上：抓到 mechanism 列 68 个值（nomogram/late/LR/stacking/ensemble…）与 metric 列 177 个 AUC 不在 codebook 集合——codebook 写的是 AUROC，编码时全写成 AUC，正文汇总按哪个算就是口径问题。
2.11：decision=pending 允许出现但 FAIL（pending 清零前不出终值；失败调用不得默认 exclude）；排除复核 `coding/qc_exclusion_sample.csv`（survey_tables.py qc-sample，无原决定）每行 qc_decision 已填，判 include 的在 screening 中仍为 exclude → FAIL，误排 > 0 → WARN，文件缺失 systematic/scoping FAIL、narrative WARN；κ < min_kappa 而 kappa_results.json `_detail` 的 PABAK ≥ 0.8 → 降 WARN（患病率悖论）。借自 Imbad0202 sr-screener（joint-exclusion audit、no silent defaults、κ+PABAK）。

### G-S4（tables）
每张 tables/*.csv 可从 coded.csv 逐格重算：coding/tables.yaml 存在时跑 `survey_tables.py summary --verify`，否则跑 coding/*summary*.py --verify（两者都没有 FAIL）；coverage.csv 格子合计 = 纳入篇数；figures.csv 至少一张（WARN）；skew_dims 中某值 ≥ 已知值 70% → WARN（借自 Imbad0202 bibliography_agent 的分布偏斜提示，只提示不阻断）。图由 `survey_figure.py` 生成（PRISMA 排除理由合计与计数不符时脚本自己 FAIL）。
### G-S5（claims）
claims.csv 每条 evidence_file#evidence_key 能取到值且满足 expected 判据；first/only 类主张必须有 prior_surveys.csv 且每行写明差异；tables/ 必须有 *summary*.py 生成脚本。
2.11 写作部分（`survey_check.py writing`，claims 子命令末尾也跑）：tensions.csv 两轴取值合法、真冲突不得 not_applicable、resolved 的 pointer 在正文可找到、有 flagged_unresolved 时正文有"未解决"类表述；逐篇罗列段（≥3 句、≥60% 句子以单篇引用开头、无比较/归纳词）WARN 并给行号，占带引用段落 > 30% FAIL；无边界的"首个 / 无人研究 / 矛盾已全部解决"WARN；coded.csv 有 bibkey 时每篇纳入研究在正文或特征表被引（WARN）；报告清单 paper/prisma_checklist.csv 每项有 location（systematic/scoping FAIL，narrative WARN；无清单时 systematic/scoping FAIL）。漏法：罗列检测只看句首与比较词，换个句式的堆砌能逃过；张力清单只查形式，不查冲突找全了没有——R3/DA 席位人工补。
