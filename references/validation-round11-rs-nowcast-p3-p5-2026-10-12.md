# 验证轮 11：RS_nowcast 真项目 P1b→P5 实战（2026-10-12）

起因：用户要求实战测试 skill。选了唯一的活研究分支项目 RS_nowcast（Nature Communications，P2 锁定于 10-06，停在 P3 等数据）。本机 RTX 4000 Ada 20 GB，SEVIR 2019 上半年 storm 子集（7.4 GB，AWS 公开桶 4 MB/s）。

## 走了什么

| 站 | 做了什么 | 关口结果 |
|---|---|---|
| 补 P1b | 项目早于 v2.5 的 G1b，缺 problem_table / transfer_scan / gap_map 三小节。按验证轮 5 的记录回填：9 篇问题表（"no held-out sensor" 6×）、10 个迁移候选（5 过三道判定，T1 DOFA 选定）、评测盲区 / 邻域默认假设 / 判定五行 | G1b 5 FAIL → PASS |
| P3 | 写 code/（srf.py 读 NOAA/JMA 的 SRF 表、data_sevir.py、UNet+FiLM、train/eval/metrics、make_smoke.py），填 state.audits/results/bundle，`bundle.py check/make`，check_env ENV OK，smoke.sh 通 | G3 bundle check PASS |
| P4 | `run_all.sh` 13 run（约 2 min/run，GPU 54 °C 72 W）→ collect → ingest → tables → audit_check **6 FAIL** → 修代码全重跑（旧 run 因 manifest 不一致被 tables 拒绝）→ 全绿；failure_slice 对 ours_s0 的 282 窗 | G3 audit PASS；G4 PASS（5 WARN 全是已登记的代理口径与豁免） |
| P5 | make_figure main / ablation，两张裁图目测 | G5 PASS |

状态板：G0–G5 全 PASS，下一步 G6。原型数字按 prereg §9 不进主表，F1 写明 `ahi_zs` 列只是条件向量敏感度探针，不是迁移。

## 关口抓到的真问题（项目侧）

1. **G3 有效配置审计抓到 cwl 基线的一致项从未生效**：args.rt_loss=0.1，日志 train_rt 全程 0。原因是 cond_tensor 只对 srf 做扰动，cwl 的两份条件完全相同，L1 恒 0。这正是 lessons 里"基线 args 写了 0.1 但从未生效"的镜像。修法：cwl 也做 ±aug µm 标量平移，使 prereg §6 第 1 行成为单因素消融。13 个 run 全重跑，没有手改任何 args。
2. 第一遍 audit 还报 nominal 的 cond=none 为"args 为真但证据列为 0"——这是 skill 的 bug（见下），不是项目的。
3. failure_slice：误差 65% 集中在真值雨区最大的五分位，模型把 VIL 79 预测成 10，CSI@74/133 恒 0——6 epoch + L1 对重尾目标的已知行为，记 F3，正式阶段换损失与 epoch。

## skill 侧修掉的（4 个提交，257 测试全绿）

| 症状 | 根因 | 修 |
|---|---|---|
| `--cond none` 被 bundle check 判"关键超参为 0"，被 audit_check 判"args 为真" | 两处只认数值；truthy 把任何非空字符串当真 | nz/anyv 正则接受词值，off = 0/none/false/off/no；truthy 对字符串按同一表 |
| prereg §5/§6 行是中文散文，矩阵名是短英文；bundle check 报 5 基线 3 消融"不在矩阵"；norm 去掉所有非 ASCII 后空串匹配一切 | 没有别名机制；norm 不保 CJK；空键命中全池 | `state.results.aliases`（矩阵名 → prereg 行子串）、`coverage_waiver`（本阶段不跑的行 → 理由，WARN 不 FAIL）；三处 norm 保 CJK；空键不匹配 |
| resolve 把 no_srf_aug 匹配到"SRF 条件化 → 中心波长"行 | row_matches 只要一个共享词元 | 短名的全部词元都要在行里，或别名子串 |
| cwl 既是 §5 基线又是 §6 消融第 1 行，在主表多 seed，results_check 与 resolve 报"§6 消融没有 run" | 消融覆盖只看 ablation.csv | 主表非参照方法也算消融覆盖 |
| 原型代理指标 csi16_abi 不在 prereg §2，G4 FAIL 无出路 | 没有"已登记的代理口径"概念 | convention_changes 登记过的主指标 → WARN；json.dumps 遇 yaml 日期崩溃 → str() |
| manifest.json / hardware.json 触发静默降级 WARN | OPTIONAL 列表没有它们 | 加入 OPTIONAL |
| resolve 对 CSI 按误差指标判符号 | prereg "worse" = +Δ 只对误差指标成立 | 按指标名翻转（CSI/AUC/F1/… 高好；RMSE/loss/… 低好） |

另：`collect.sh` 现在也打包 split_* 与 stats.json（G3 split 证据）。

## 仍不机械的 / 留给正式阶段
- 原型的 `ahi_zs` 不是迁移（SEVIR 无 AHI 帧）；prereg §10 的全部符号检验留到 Arrhenius。
- 需要用户：SUPR 申请、Earthdata 账号、NSMC 账号。
- 正式阶段切换清单写在项目 README 末行。

## 坑
- heredoc 里的中文 + `\c` 转义又炸了两次（README 补丁）；Write 工具落文件是唯一稳的办法。
- Git Bash 的 `/tmp` 在 Python 里是 `C:\Users\...\Temp`，但 `os.path.isdir("/tmp/x/data")` 在 Windows 上看的是 `C:\tmp`；临时数据放项目目录内。
- 第一次 `rm -rf runs/* bundle` 被安全检查拦下（通配符删除）；改成 `mv` 留旧包反而更对——旧矩阵是 F2 的证据。
