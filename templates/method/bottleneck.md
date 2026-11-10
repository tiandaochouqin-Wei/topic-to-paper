# 方法轨道：瓶颈说明（method_track.py headroom 第 7 项读它；HTML 注释和 <尖括号占位> 不算内容）

## 瞄准的瓶颈
<!-- 一句话：最强基线的哪一类错误是你要解决的。写具体的失败，不写"泛化性差"。 -->

## 证据文件
<!-- failure_slice.py 输出 / 误差分解表的项目内路径（必须真实存在），如 results/failure_slices.md -->

## 占基线误差的比例
<!-- 数：这类错误占最强基线总误差（或总损失的指标差）的百分之几，例如 "41%（failure_slices.md 第 3 节）"。小于 min_effect 能覆盖的量就不值得做 -->

## 理想解决后的上界怎么测
<!-- headroom.oracle：GT 路由 / oracle 选择 / 域内上界……在 dev 上跑 ≥3 seeds，run 标 role=oracle -->

## oracle 自检
<!-- headroom.oracle.sanity：用 dev 数据造一个"已知答案"的情形——瓶颈在那里必然是限制因素（例如故意注入这类失败，并告诉 oracle 它在哪），所以一个能用的 oracle 必须在那里赢。
     写三件事：① 这个情形怎么造的（sanity.setting）；② 为什么 oracle 在那里必须赢（sanity.why，一句话）；③ oracle 是 train+test（模型训练时也见过 oracle 信号）还是 test_only（只在推理时注入已训好的基线；这类 oracle 最容易不涨反跌，优先做 train+test）。
     基线和 oracle 各 ≥3 seeds，run 标 eval_split=sanity 与 role=baseline / oracle。oracle 在这里没赢，说明 oracle 本身造错了，上面的提升空间 H 不能读。 -->

## 为什么便宜做法不够
<!-- headroom.cheap_fixes：数据增强 / 更长训练 / 更大骨干 / 调参……各自在 dev 上跑过，拿走了多少提升空间（headroom 的 INFO 行） -->
