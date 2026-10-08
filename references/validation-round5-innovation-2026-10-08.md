# 验证轮 5：创新点来源（2026-10-08）

起因：用户问"找创新点不应该也参考最近新出的模型/论文能不能用到目标领域吗"。承认原 P1 只机械化了"领域内空白"（前人明文假设），遥感项目的主张其实来自"邻域方法的失效点"（DOFA 的波长条件化），但那是读文献时碰巧带出来的。

## 加了什么

| 项 | 实现 | 关口 |
|---|---|---|
| P1 第二产物 transfer_scan.md | `scripts/transfer_scan.py recent`（本地顶会近 2 年 + arXiv 近 18 月标未录用 + OpenAlex）→ transfer_hits.csv；Claude 读候选后填七列表；`count --domain` 机械填域内计数（OpenAlex → Semantic Scholar bulk → arXiv 三级回退，格式 `s2:0+local:0`）；三道判定：计数 ≤2、对应物、失效点 | G1b = `transfer_scan.py check` |
| gap_map 两个固定问题 | `## 评测盲区`、`## 邻域默认假设`，答不出写"未知：查过…"但小节必须在 | G1b |
| P1 允许"不做" | `## 判定` verdict go\|no-go + claim_source + reason；no-go 是合法出口，不进 P2 | G1b |
| 主张来源可追溯 | prereg §1 必须写 `来源: gap#A` 或 `来源: transfer#T2`；指向的行必须过三道判定；规则前锁定的 prereg 降 WARN | G2 `prereg_check.py` |
| P4 反常触发器 | `results.predictions` 反号、或 `results.reproductions` 基线复现 \|Δ\| > tol（默认 2×reported_std）时，findings.md 必须已有含方法名+指标名的条目，否则 FAIL（有则 WARN） | G4 `results_check.py` |
| 模板 | templates/gap_map.md、templates/transfer_scan.md；state 模板加 reproductions / findings | — |

## 验证

**夹具**（/tmp/t2p_fx）：模板原样 3 FAIL；填 5 行（2 过、3 淘汰）ALL PASS；claim_source 指向淘汰行 FAIL；改 no-go 后 PASS（no-go 下不再查 claim_source）。
**EAAI 项目**：加一条 `reproductions: {RCNN, rmse_E1_in_domain, reported 0.90, std 0.02}`，无 findings.md → FAIL；写一条含 "RCNN" 与指标名的 findings → WARN。prereg 规则前锁定 → 来源缺失降 WARN，ALL PASS 不变。
**RS_nowcast 补跑**：`recent` 本地顶会 0 命中、arXiv 9 条全预印本；读了 9 条摘要 + corpus 里已有的 5 个 any-sensor FM，填 10 行：6 过三道判定、1 无对应（OmniRSCLIP）、1 无失效点（RAMEN 处理的是空间分辨率，本文重采样后问题消失）、2 已有人做（SMARTIES/STARS 与 DOFA 同思路）。两个固定问题答出（评测盲区：单传感器时间切分看不见传感器系统偏差与 lead-time 误差放大；邻域默认假设：陆地 FM 默认中心波长足够、本领域默认每星单训，IR 窄带的中间地带两边都没验）。判定 go，claim_source gap#A，方法来源 transfer#T1。G1b PASS，状态板 G0/G1b/G2 绿。

## 发现的坑
- OpenAlex 免费额度按天计（Retry-After 13250 s），`count` 10 行就打爆；加了 Semantic Scholar bulk 和 arXiv 回退。arXiv API 对无 UA 的 http 请求 301 到 https。
- `count` 的查询把方法名里的 "(2403.15356)" 带进去，命中为 0 是查询污染不是真零；去掉括号内容。
- 判定列写"淘汰"的行即使三道判定数据齐也不算过——作者的淘汰优先于机械判定。
- 变量名 `m` 在循环里既是方法名又被 re.search 复用，静默覆盖后格式化报错。

## 仍不机械的
第 2、3 道判定（对应物、失效点）是我读论文后写的。来源 3（评测口径漏洞）和 5（两领域常识矛盾）只做成固定提问，答不出允许留空。
