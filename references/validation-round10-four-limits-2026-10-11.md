# 验证轮 10：补 README 自述的四条缺口（2026-10-11）

起因：README「Limits」里写了四条"还没做到"的事。用户要求四条都补。四条全部有回归测试，`python -m pytest tests -q` 252 项全绿（含 6 项真跑脚本的端到端测试，约 3 分钟）。

## 1. P4 在全新项目上端到端（原文：not yet end-to-end on a fresh project）

`tests/test_e2e_fresh_project.py`：`t2p.py init` 起一个空项目 → 锁 prereg → `bundle.py check`（G3 走实验包分支）→ `bundle.py make` → **真的跑**生成的 `check_env.py` / `smoke.sh` / `run_all.sh` / `collect.sh`（夹具训练器 `tests/fixtures/e2e_code/train.py`+`eval.py`，CPU 几秒，数字是 (model, β, α, seed) 的确定函数）→ `bundle.py ingest` → `bundle.py tables` → G3 审计分支 + G4（results_check + resolve）→ `make_figure.py main|ablation` → G5 → 状态板"下一步：修 G6"。

一条全新的链路抓到 5 个真 bug，全部已修：

| 症状 | 根因 | 处理 |
|---|---|---|
| check_env.py 一行都没跑就 NameError | `json.dumps(bool)` 生成的是 `false` 不是 Python 的 `False` | 用 Python 字面量 |
| ingest 后 12 个 run，不是 11 | `_smoke_ours` 被当成正式 run 收进 runs/ | `_`/`.` 开头的 run 进 `bundle/returned_<stamp>/runs/` |
| **本文方法全部 seeds 按基线配置跑完，G3 放行** | ref 行只写 `--model ours`，train.py 的 `--beta` 默认 0；G3 有效配置审计看到 args=0、日志=0 自洽 | `bundle.py check` 新规则：ref 与消融行必须显式写每个 critical_params，ref 的值必须非零，否则 FAIL（3 个突变测试）|
| 新项目 G5 对一张不存在的图 FAIL | init 复制的 figures.csv 模板带占位行 `figures/fig1.png` | make_figure 写 figures.csv 时丢掉"文件不存在且从未目测"的行 |
| results_check 口径关口无东西可读 | tables 只写 csv，不写 main.md | tables 从 prereg §3/§4 原文写 `results/main.md` |

另外三个顺手补的：`bundle.py ingest`（解包 collect.sh 的 tar，拒绝 `..` 越界路径，manifest 比对）；collect.sh 只打包存在的文件；`$PYTHON` 环境变量让没有 `python` 命令的服务器可用。

第三条值得单独说：它正是 lessons 里"基线与提出方法差距稳定但解释不了 → args 里的超参没走到生效分支"的镜像——这次是**本文方法**没走到生效分支，而已有的 G3 审计设计上抓不到，因为它查的是 args 与日志是否一致，一致地等于 0 它就放行。只有在矩阵层面要求"本文方法的关键超参必须显式非零"才堵得住。

## 2. Slurm 分支（原文：the Slurm branch of the bundle is untested）

重写 `jobs.sbatch`：读 matrix.csv 从 `cut`/`sed`（带引号的 args 会断）改成 `csv.DictReader`；每个 array task 先查 eval.json 存在即退出（重提交只补缺的）；task 内先跑完整 check_env.py 再训练；失败追加 failed.txt。`run_all.sh` 在登录节点用 `check_env.py --no-gpu` 预检（登录节点无 GPU），再 `${SBATCH:-sbatch} jobs.sbatch`。

本机没有 Slurm。生成 `sbatch_local.sh`：串行模拟 array job，设置 `SLURM_SUBMIT_DIR` / `SLURM_ARRAY_TASK_ID` / `SLURM_ARRAY_JOB_ID`，写 `slurm_<job>_<task>.out`。端到端测试对 `scheduler: slurm` 跑同一矩阵：11 个 `.out` 全部 `== done`，无 failed.txt，重跑 11 个全 skip。模拟器不是 Slurm（没有分区、没有 GPU 分配、没有时限），它验证的是 jobs.sbatch 的逻辑和 matrix.csv 的回读；真集群上的差异只剩调度器本身。

## 3. 创新性第②③道判定机械化（原文：written by Claude after reading a paper, not computed）

诚实的边界：机器读不懂论文，判不了失效点是否为真。能判的是**形状**——这格写的是不是"目标领域的 X 让它在 Y 上坏掉"这种话，还是"都用 Transformer"/"还没人在本领域用过"这种话。后两种正是 Round 5 验证时人工淘汰候选的理由，所以机械化它们有价值。

`transfer_scan.py check` 从项目自己的文件建领域词表（transfer_scan 的领域词行 + problem_table.csv 全部文本格 + gap_map + prereg，减去 transformer/attention/encoder/backbone 等架构通用词；夹具 307 个词），对每个未淘汰候选判：

- 对应物：有领域名词；去掉架构词后非空；不是问题结构列复述。
- 失效点：≥4 内容词；有领域名词；有失效谓词（not/fails/assumes/leaves/depends/因为/失效…）；不是"not yet applied"（那是第①道）；不是对应物复述。

作者写 淘汰 的行不判（否决优先）；写 候选/选定 而形状不成立 FAIL；claim_source 指向的行必须过。

校准：按 Round 5 记录重建 RS_nowcast 的 5 种行——DOFA（两格过）、OmniRSCLIP（无对应）、RAMEN（过，当时人工淘汰是因为"重采样后问题消失"，这属于失效点为真但不够格，机器判不了）、SMARTIES（失效点无领域词）、"both use ViT / not yet applied"（两格全败）。与当时人工判定的分歧只有 RAMEN 一行，且是机器偏松的方向。7 个突变测试。

## 4. 形状关口查主张（原文：Shape checks verify form, not whether the claim is right）

新关口 **G6e `claims_check.py`**。思路：G6c 查"有没有 Here we show 句"，G6e 查"这句话对应 claims.csv 的哪一行，那一行的数是不是从结果文件算出来的"。

claims.csv 加两列：`evidence_key`（`rel:<metric>:<a>:<b>` 相对变化 %、`delta:`、`z:<metric>:<a>` 消融分辨率、`mean:`、numbers.csv 式单格、json 点路径）与 `expected`（`-19.2±0.2`、`>=2`、`<2`、`+`）。关口自己算值自己判。查五件事：每行证据成立；主张里的数字在正文；有 table_or_figure 的主张在该题注所在节被陈述；headline 句（nature：Here we show、句式小标题；CS：贡献条目、摘要数字）各对应一行；正文每句本文自述的强作用域句（SCOPE_STRONG + we/our/proposed）对应 scope_words 非空的一行——"outperforms all"必须有一行写明 all = 谁、哪个表。`rel:` 低于 prereg §7 最小改进量 WARN。

定性主张（§0 对照实验、协议类）留空 evidence_key，WARN 永不 PASS，审稿席位人工看。这是诚实的边界：关口只能把"写了但没数支撑"的 headline 抓出来，判不了一句有数支撑的话是否解读正确。

夹具 5 行（3 量化 PASS、2 定性 WARN）；10 个突变测试覆盖：expected 与结果相反、不可分辨格写成有效、有 key 无 expected、主张数字与正文不同步、贡献条目无对应行、"outperforms all existing" 无行 → 登记 scope_words 后过、table_or_figure 指错节、nature 的 Here-we-show 无对应行、prereg §7 抬高后 WARN、状态板出现 G6e。

## 坑
- heredoc 写含 `\n` / `\s` / 嵌套引号的 Python 补丁三次失败（lessons 已记，这次又犯）：改用 Write 工具落文件再 `python -I` 跑。
- 强作用域判定起初按**段**匹配 claims 行，段里别的数字让任何行都能匹配上；改成按句。
- `json.dumps(True)` 生成到 Python 源码里是 `true`，不是 `True`。

## 仍不机械的
- 失效点为真与否；定性主张；RAMEN 式"写得出失效点但问题在预处理后消失"的判断。
- `z:` 用单 run 消融 vs 参照 seeds 的分辨率，多 seed 消融应改用 `delta:` + 检验。
- Slurm 真集群未跑过；模拟器覆盖的是脚本逻辑不是调度器。
