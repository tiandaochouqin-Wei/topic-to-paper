# 方法轨道（`project.paper_type: method`）

**这份文件是给 Claude 的执行指令。** 用户说"我想做一篇方法论文 / 提出新方法并在公认基准上赢强基线"时，走这条轨道；其余项目照 SKILL.md 的分析轨道走，行为不变，三道新关口在状态板上不出现。

## 0. 为什么有这条轨道

分析轨道的流水线是「先找问题 → 方法一次性设计 → 预注册锁定 → 跑一次 → 失败就转向备选 claim」。用它做出来的论文全是诊断 / 测量论文：方法只有一次机会，失败了只能把失败写成发现。一个真正的方法需要几十轮开发迭代，需要在动手设计之前就知道瞄准的瓶颈有没有提升空间，需要一块没被调参碰过的验证集。方法轨道保留本 skill 的诚实（不在测试集上调参、强基线、不挑结果），加上三样东西：**设计之前的提升空间检验（G1c）→ 免费但全程登记的开发循环（G2m）→ 冻结后在没碰过的数据上确认一次（G4m）**。

## 1. 什么时候选方法轨道（P0/P1 就要定）

三条**都**满足才选，缺一条就走分析轨道：

1. 有**公认基准 + 公认指标 + 官方划分与评测脚本**（论文表里大家都在这个基准上报同一个指标）。
2. 有**最强的、带代码的已发表方法**可以复现到论文数字。没有代码、只能自己重写的，不选。
3. **一轮 dev 实验的代价是小时，不是天**（budget.iter_hours × max_iters 在你的算力内）。一轮要训几天的，几十轮迭代做不起，选分析轨道。

选定后：`t2p.py init --project <dir> --venue "<刊>" --field <领域> --paper-type method`（已有项目：把 `state.project.paper_type` 改成 `method`），再把验证集文件填进 `state.method.splits.confirm.files`（和 dev 的 files、min_effect 等），然后 `method_track.py init --project <dir>`（建 `method/` 四个文件并写 confirm 的 sha256；confirm.files 为空时它会 FAIL）。选不准时问用户一次（这是"两种读法会导致实质不同的工作"）。

不变的东西：P0 选刊、G1 文献、G1b 创新点来源（gap_map / transfer_scan 照写，方法轨道里 gap 写成"强基线在基准上的最大误差来源"，prereg 仍标 `来源: gap#X`）、G3/G3b 审计与仪器校准、G5–G8 全部照旧。

## 2. 状态块与 run 标记约定

`research-state.yaml` 末尾的 `method:` 块（模板里已有，字段含义见模板注释）：主指标、`min_effect` 与依据、基准出处、最强基线（含论文里的已发表数）、`splits.dev / confirm`、`headroom`（oracle、cheap_fixes、k_sd）、`budget`、`components`、`mechanism`、`freeze`、`confirm`、`outcome`。**`freeze` 由 `method_track.py freeze` 写，`confirm.looks` 由 `confirm-check` 登记，不手工改；`outcome` 在 G4m 看完数字后手工填。**

**每个 run 目录**（`results.runs_dir` 下）的 `args.json` 必须带：

```json
{"eval_split": "dev|confirm", "role": "baseline|oracle|cheap_fix|ours|ablation|tuning",
 "method": "<名字>", "seed": 0, "iteration": "I07", "code_sha256": "<当前代码哈希>"}
```

`iteration` 只在 ours / ablation 上写；`code_sha256` 在 confirm 的 run 上必须写（值 = `method_track.py` 对 `audits.code_dirs` 下所有 .py 算出的哈希，训练脚本启动时调用 `method_track.py code-sha` 或它的 `code_sha(root, st)` 记下来，不要手填）。指标一律从 `eval.json` 经 `results.metric_map` 或 `key`（点路径）读，和 G4 同一套。**`eval_split` 是自报的**：脚本只能核对你写下的标记，所以写 launcher 时把它做成命令行参数而不是手敲。

## 3. 顺序（每一步做完才进下一步）

### M0 复现最强基线
在 dev 划分上用 ≥ 3 个 seed 跑最强基线（`role: baseline`），对账论文数字：填 `baseline.published.value / source / tol`（tol 空则取 2×sd）。对不上的先查实现（G3b 仪器校准、`results.reproductions`），**不要在对不上的基线上继续**——之后所有提升都会算在你的实现错误头上。

### M1 误差分解找瓶颈
对基线的逐样本预测跑 `failure_slice.py`（或同等的误差分解），找出占基线误差最大份额、且可以被"一个机制"针对的部分。写 `method/bottleneck.md`（模板在 `templates/method/`）：**瞄准的瓶颈、证据文件路径、它占基线误差的比例、"理想地解决它"的上界怎么测、为什么便宜做法不够**。四项缺一项 G1c 就 FAIL。

### M2 oracle 提升空间
把瞄准的瓶颈**理想地解决**（GT 路由、oracle 选择、域内上界……），在 dev 上跑 ≥ 3 个 seed（`role: oracle`），登记到 `headroom.oracle.run_glob / key`。提升空间 H = oracle − 基线（方向由指标方向决定）。H 必须 ≥ max(`min_effect`, `k_sd` × 基线 seed s.d.)；oracle 比基线还差 = 瓶颈判断错了。

### M3 便宜做法
至少登记 2 个"不需要新方法"的替代做法（数据增强、更长训练、换个现成损失、调超参……），各在 dev 上跑 ≥ 3 个 seed（`role: cheap_fix`），登记到 `headroom.cheap_fixes`。便宜做法拿走大部分 H、剩下的 R 不到 max(min_effect, k_sd×sd) → 方法没有立足点。

### G1c 关口（设计方法之前的 GO / NO-GO）
真实回放的例子（cvpr2027_fusion，M3FD，指标 SMG_rgb，scratch 项目 E:/t2p_trial_method/fusion_replay）：干净训练的基线 −8.01 ± 0.98（3 seed），oracle 门控 −15.97（2 seed），只做数据增强 +8.88、特征丢弃 +10.10（均相对基线）。关口打印「瞄准的瓶颈判断错了：理想地解决它反而更差」→ NO-GO，与该项目事后的结论一致：设计门控之前就能知道这条路走不通。
```
python <skill>/scripts/method_track.py headroom --project <dir>
```
读最后一行 `G1c: GO (...)` 或 `NO-GO`，以及每条 FAIL 的原因。**NO-GO 之前不许设计方法。** FAIL 的两种修法：补缺的项（数字不够 seed、字段空），或承认瓶颈没有提升空间（换瓶颈回 M1，或走出口 A，见 §4）。同时确认三件事：基线复现与论文数字对上、dev 与 confirm 文件无交集且 confirm 的 sha256 没变、没有任何 `eval_split: confirm` 的 run。

### M4 想法清单
`method/ideas.csv`：id, type (data|objective|architecture|inference|training|other), mechanism, predicted_effect, cheapest_test, kill_result, status。≥ 5 个想法、≥ 3 种类型，每行写清**机制**、**最便宜的检验**、**什么结果就杀掉它**。`method_track.py ideas-check` 只给 WARN（想法是帮助不是证明）。动手前先把这一轮要试的想法的 `predicted_effect` 写下来。

### M5 dev 迭代循环（G2m，每一轮都登记）
对每一轮尝试：

1. **先写假设**：在 ideas.csv 把这一行的 status 改成 running，写下 predicted_effect 与 kill_result（跑之前）。
2. 在 dev 上跑 ≥ `results.min_seeds` 个 seed（`role: ours`，`iteration: I07`）。
3. **立刻登记**，数字由脚本从 run 目录算，不手填：
```
python <skill>/scripts/method_track.py log add --project <dir> --id I07 --hypothesis "…" --change "…" --runs "runs/i07_s*" --decision keep|drop|revise --note "…"
```
4. 没登记的 dev 实验 `dev-check` 一律 FAIL（"每次尝试都要记，否则挑出来的最好结果没有分母"）；跑完不满意也要登记 `--decision drop`，**不许删 run 目录**。

迭代预算：`budget.max_iters`（默认 30）；超出 WARN，超出 1.5 倍 FAIL（要延长就在 `budget.extension` 写理由）；连续 `stall` 轮最好成绩没有超过噪声 → 停下来换假设或收手，这是出口 A 的信号。随时 `method_track.py status` 看一屏概况，`t2p.py check` 的 G2m 行是同一份检查。

### M6 冻结前的三项检查
都在 `method_track.py dev-check` 里：

- **组件必要性**：prereg §6 / `method.components` 里的每个组件，去掉它的 dev 消融（`role: ablation`）必须掉点超过 2×se。去掉不掉点的组件**删掉再冻结**，方法越简单越好。
- **机制检验**：`method.mechanism` 写"提升是因为 X"的可观测预测（某个中间量的符号 / 阈值）。缺 → WARN；被数据反驳 → FAIL（"提升不是因为你说的原因"）。
- **基线同等调参**：`method/baseline_tuning.csv` 里最强基线至少有 min(K, 10) 次调参尝试（或一行 `published_config` 加 ≥ 5 次）。**全篇使用的基线数字 = 它最好的 dev 配置**，不是论文默认配置。
- 另外 dev-check 会算**赢家诅咒线**：从 K 次尝试里挑最好的，期望偏差 = se_gain × sqrt(2 ln K)；扣掉后的 `gain_adj` 要 ≥ `min_effect`。0 < gain_adj < min_effect 是 WARN（加 dev seeds 或继续迭代）；≤ 0 是 FAIL（dev 提升不超过挑选噪声）。它假设各次尝试近似独立，同一思路的微调连试 20 次会把 K 夸大成保守的线，但不会反过来放水——这是有意的偏向。

### M7 冻结
```
python <skill>/scripts/method_track.py freeze --project <dir> --iteration I12
```
dev-check 前四项 FAIL 时拒绝冻结。成功后 `state.method.freeze` 写入 date、iteration、code_sha256、dev_gain、se_gain、k_iters、bias、gain_adj，并打印要粘进 prereg 的行。**冻结之后任何 .py 改动都会让 dev-check 报"冻结后代码改过"**：要改就重新登记一轮迭代并重新 freeze。

### M8 预注册锁定
把 freeze 打印的行写进 `prereg.md`（模板末尾有"方法轨道补充"：§1 写冻结后的方法与 `freeze: <sha8>`；§5 基线 = dev 上同等预算调参后的配置；§7 成功判据**只在 confirm 划分上评测一次**），然后：

```
python <skill>/scripts/prereg_check.py
python <skill>/scripts/t2p.py lock --project <dir>
```
`prereg_check.py` 在方法轨道里：没有 `freeze: <sha8>` 给 WARN；`state.method.freeze` 为空却已锁定给 FAIL（"方法轨道先 freeze 再锁预注册"）。方法轨道里 dev 的 run 早于锁定是正常的，不触发"事后注册"。

### M9 验证集，一次
在 `splits.confirm` 的文件上评测冻结后的方法（`role: ours`）和最强基线的**那一个**调参后配置（`role: baseline`），每个 ≥ `results.min_seeds` 个 seed，`eval_split: confirm`，args.json 带 `code_sha256`。不许看一眼再调。

```
python <skill>/scripts/method_track.py confirm-check --project <dir>
```
G4m 检查：prereg 已锁且含 freeze 的 sha8、锁定日期不早于冻结；每个 confirm run 晚于冻结且代码哈希等于冻结哈希；验证集上评测过的 ours 变体个数 ≤ `confirm.registered_looks`（默认 1）；确认提升 ≥ `min_effect` 且超过 2×se → `confirmed`，否则 `not_confirmed`。**两种结果都是合法的，把对应值填进 `state.method.outcome`，G4m 才通过**；outcome 为空或与数字矛盾就 FAIL。最后打印 dev 提升到 confirm 提升的收缩量（INFO），写进论文局限。

之后 P5 图、P6 写作、P7 审稿、P8 投稿包照旧。

## 4. 两个诚实出口

**出口 A：G1c NO-GO，或 M5 里连续 stall 轮没有超过噪声。** 这不是失败，是分析论文的素材：基线复现、误差分解、oracle 上界、便宜做法吃掉了多少提升空间，本身就是一篇"这个瓶颈为什么做不出方法"的分析（cvpr2027_fusion 就是这样：oracle 路由没有补上差距，普通数据增强反而补上了）。把 `project.paper_type` 改成 `analysis`，把 `method/` 下的日志与 headroom 数字当作分析论文的证据，回 P2 重写 prereg（旧 prereg 的锁要在 `state.experiments.convention_changes` 留记录）。

**出口 B：G4m `not_confirmed`。** 验证集已经烧掉。两条路二选一：(1) 同出口 A，转分析论文，dev 日志 + 确认结果就是素材；(2) 拿到**新的**验证集（新的留出划分或另一个公认基准）回 M5 继续迭代，`method_track.py init --force` 重新写 confirm 哈希，`confirm.looks` 重新计数，**旧验证集上的数字只能当作 dev**。不许在同一块验证集上"再看一次"。

遇到这两个出口时，选哪条是**用户的决定**（课题方向），先报告数字再问，不替他选。

## 5. 论文里要写什么

方法轨道的论文必须交代它的搜索量，否则读者无法判断 dev 提升有多少是挑出来的：

- **迭代次数 K** 与每轮的登记表（放补充材料，来自 `method/iterations.csv`）；哪些想法被杀掉（`ideas.csv`）。
- **dev → confirm 的收缩**：dev 提升、扣除赢家诅咒后的 gain_adj、confirm 提升三个数并排，局限里解释差距。
- **验证集被看了几次**（正常是 1），基线怎么调的参（预算与最好配置）。
- 提升空间分析：基线、oracle 上界、便宜做法各自拿走多少（G1c 的数字）——这是方法的动机证据，不是附录。
- `outcome: not_confirmed` 的方法论文不能写成"提出方法并验证有效"，只能写成它实际是的东西。

## 6. 常见错误

- 在 G1c 之前就开始写方法（NO-GO 之后白做）。
- 跑完觉得不好就不登记（dev-check 会抓到未登记的 run 目录；删目录属于造假）。
- 把验证集当第二个 dev 用：只要看过一次再改方法，这块验证集就不再是验证集。
- 基线用论文默认配置、自己的方法调了 30 轮。
- `eval_split` 标错或不标：脚本无法发现一个把 confirm 数据标成 dev 的 run，这一条靠 launcher 里把它做成参数、以及 confirm 文件 sha256 不变来兜底。
