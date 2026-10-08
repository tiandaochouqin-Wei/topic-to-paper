# 验证轮 7：远程实验包（2026-10-08）

起因：用户的实验方式是"我写好脚本，用户上传到服务器跑，跑完传回来"。P3/P4 原本假定 runs/ 在本地，没有"上传包"的概念，每个来回都要用户动手，所以必须把来回压到最少并让每一步可机械核对。

## 加了什么：`scripts/bundle.py`，配置在 state.bundle

| 子命令 | 做什么 | 关口 |
|---|---|---|
| `check` | 矩阵 ⊇ prereg §5 基线与 §6 消融；seeds ≥ min_seeds 且参照方法多 seed；矩阵里无 run 打开 leak_flags；每个数据源有 remote 与 inputs；eval 命令已配；run_id 不重复 | runs/ 为空时顶替 G3（t2p.py check 自动切换） |
| `make` | 生成自包含实验包：README（按顺序五步）、check_env.py、run_one.sh、smoke.sh、run_all.sh（bash 顺序可中断重跑 / slurm 数组）、collect.sh、matrix.csv、manifest.json、代码副本（不含 runs/ckpt/缓存） | — |
| `tables` | 结果回来后按 state.results.metric_map 从 eval.json 生成 main.csv / ablation.csv；硬件取 hardware.json；manifest 与包不一致、_tainted、缺指标的 run 跳过并列出 | 之后走 G4 |

包内各文件的职责：
- **check_env.py**：Python 版本、import、CUDA、每块 GPU 显存 ≥ 阈值、磁盘、每个数据源目录存在、按 clip_glob 逐 clip 核对 inputs 文件、包文件齐。任何 MISS 退出非零。这是 G3 静默降级关口的远程版（frames/ 缺失曾让 12 个 run 全程无视觉）。
- **run_one.sh**：先写 hardware.json（torch 设备名、驱动、CUDA 版本、主机名、时间）和 manifest.json 副本，再训练、eval、post；全部 tee 到 train.log/eval.log。
- **smoke.sh**：check_env → 参照配置跑 `--epochs 1` → eval → 汇总每个产物是否存在、log 条数 → smoke_report.txt。
- **collect.sh**：只打包 args/log/eval/hardware/manifest/stats/train.log/eval.log/preds，不含 checkpoint。

来回预期三次：烟测报告 → 全量结果包 → 反常补跑（反常触发器规则下，补充对照尽量提前放进第一批）。

## 验证（EAAI 力估计项目，本机 A2000 模拟服务器）
1. state.bundle 按已有 22 个 run 的 args.json 反推矩阵：ref ours × 3 seeds、5 基线（RCNN × 3 seeds）、5 消融 → 15 run。`bundle.py check` ALL PASS，与 prereg §5/§6 逐项对上。
2. `make` 出 53 个文件（38 个代码文件进 manifest）。
3. `check_env.py` 第一次报 MISS：data_B 39 个 clip 里 12 个没有 frames——Free/Palpation/Traction 是本项目不用的子集，只用 C?_* 的 Teleop 切分。这是真实的漏洞提醒而不是误报：若远程数据少拷了子目录，训练会静默退化。加 `clip_glob: "C?_*"` 后 ENV OK。
4. `smoke.sh` 跑通：1 epoch 368 s，val RMSE 0.286，hardware.json 记录 "NVIDIA RTX A2000 12GB / torch 2.11.0+cu128 / CUDA 12.8 / 驱动 582.16"。eval 阶段跑了 >40 分钟仍在跑：eval.py 对每个条件做 5 种缺模态评估 + E5 两种归一化，共 ~26 次全量评估，A2000 上满载 92 °C。
5. 全程 GPU 92–93 °C，正好在记忆里的驱动热复位阈值上；本机不适合跑全量，这也是用户要用服务器的原因。

## 发现的坑
- bundle 内代码目录名要用 code_dir 的 basename（state 里是 `../code`），否则 run_one 的 `cd` 指到包外。
- smoke 的参照行要取 seeds[0]，`{name: row}` 字典会留下最后一个 seed。
- 烟测的 eval 不该跑全量评估矩阵；但 eval.py 是项目代码，包生成器不改项目代码。处理：state.bundle.smoke 可给 `eval` 覆盖（如只评 E1），未给则沿用正式 eval 命令，README 里标出烟测 eval 可能很长。
- Windows 本机 bash 跑 `tee` 正常；Slurm 分支只生成了 sbatch 没有集群可验，标为未验证。

## 未验证
Slurm 数组脚本（无集群）；`tables` 子命令只在本地已有的 runs 上验证了读表逻辑，没走过"传回 tar → 解包 → tables"的完整回收。
