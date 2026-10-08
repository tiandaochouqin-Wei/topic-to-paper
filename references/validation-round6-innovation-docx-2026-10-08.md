# 验证轮 6：创新点方法二次扩充（2026-10-08）

来源：用户提供的《计算机与人工智能科研论文创新点寻找方法》（docx，12 节）。逐节判断能否机械化，采纳 5 条，不采纳 3 条。

## 采纳并实现

| 文档条目 | 判断 | 实现 | 关口 |
|---|---|---|---|
| §八 创新点文献表（十字段）+ §五.4 反复出现的缺口 | 靠谱且可机械：缺口短语跨行统一写法后可以计数 | `templates/problem_table.csv`（14 列：question / hidden_assumption / failure_scene / missing_experiment / contradicts / followup_question / potential_innovation / read_depth …）；`problem_table.py recurring` 数 ≥2 篇共享的缺口，`check` 查 ≥8 行、已读行 ≥60% 填齐三个缺口列、≥1 条共享缺口 | G1b（transfer_scan check 调用） |
| §二.2 失败案例分析 + §二.5 评价指标不充分 | 靠谱且可机械：有逐样本预测就能切片 | `failure_slice.py`：按 id / 目标量级 / 不确定度 / 任意协变量切片；输出最差切片倍数、最差 10% 样本的平方误差占比、sig 对 top-10% 误差的 Spearman 与 AUROC（"模型知不知道"）、协变量扫描按最差/最好 bin 比值排序给候选原因假设 | P1 有基线代码时跑；P4 对本文方法缺则 G4 WARN |
| §六 值不值得做五维 | 靠谱，但只能做成强制作答 | gap_map `## 判定` 五行（重要性/新颖性/可验证性/可解释性/可推广性），答不出写"弱"，≥3 弱 FAIL | G1b |
| §五.5–7 先原因假设、最小对照实验、再设计方法 | 靠谱，核心原则 | prereg 新增 `## 0. phenomenon`（现象 / 原因假设 / 最小对照实验三行）；缺 WARN、三行不齐 FAIL、对照未做 WARN；§1 hypothesis 无原因词 WARN | G2 |
| §三 跨领域迁移三层次 + §二.8 | 靠谱，与已有三道判定一致 | 写进 SKILL.md P1 ③：直接迁移（弱）/ 领域适配（中）/ 用新范式重定义问题（强）；失效点写不出的是第一层 | 已有 G1b |
| §二.4 论文间矛盾 → 找成立条件 | 靠谱 | problem_table 的 `contradicts` 列；gap_map 候选来源列表第 4 条 | problem_table check 不强制该列非空 |

## 不采纳
- §九 写作模板（"现有研究普遍认为 A… 我们发现 C 条件下… D 才是关键…"）：是 §0 phenomenon 的散文版，不另设关口；P6 写作时参考即可。
- §十 阅读清单 14 问：与 problem_table 列重复，不单列。
- §二.7 新数据/新场景：只在"有实际价值且需新技术"时算创新，无法机械判定，写进 gap_map 候选来源第 6 条作提醒。

## 验证
**failure_slice 真实数据**（EAAI 力估计 E5 平台迁移，逐样本 npz）：
| run | 最差切片 | 集中度（最差 10% 占比） | AUROC(sig→top-10% err) |
|---|---|---|---|
| abl_no_dom（本文方法无域项） | \|F\| 最高五分位，2.17× 总体，占 94% 平方误差 | 80% | 0.867 失败可预测 |
| vs_hetero | clip=11，1.20× | 19% | 0.842 |
| vs_baseline | 1.18× | 18% | 0.547 对失败无感 |
三行就是一段正文失败分析：本文方法把误差压进大力区间且知道自己在那里不准，基线误差均匀却无感。
**failure_slice 合成夹具**：植入 device=C 三倍噪声、size<5 两倍噪声，协变量扫描排序 device 3.08× > size 2.40×，正确。CSV 列自动作协变量；逐样本 id 不再切片。
**problem_table**（RS_nowcast 13 行，7 全文 6 摘要）：11 条缺口被 ≥2 篇共享，最高 "held-out sensor evaluation" 6×（GeoCenter/Global MetNet/MetNet-3/Oya/TUPANN/WeatherNext 3），其次 "static land EO only" 4×、"narrow IR unseen-sensor test" 3×。这与 gap_map 手写的判断一致，但现在是数出来的。
**prereg §0 夹具**：三行齐且对照已做 PASS；对照"未做"WARN；删掉原因行 FAIL。RS_nowcast 的锁定 prereg 缺 §0 → WARN（2 WARN，ALL PASS 不变）。
**gap_map 五行**：RS_nowcast 填后 1 弱（可推广性：主实验只有 ABI→AHI 一对）；G1b PASS。
**夹具空表**：模板原样 3 FAIL（缺行、未填齐、无共享缺口）。

## 坑
- 空 CSV 的 DictReader 取不到表头，列检查误报"缺全部列"；改读 csv.reader 首行。
- failure_slice 对逐样本 id 切片会生成 n 个切片；改为 id 种类 ≤ max(50, n/min_n) 才按 id 切。
- 预测文件里的值是标准化后的单位，RMSE 绝对值不可直接进正文，倍数与排名可以；报告头部加了说明。
