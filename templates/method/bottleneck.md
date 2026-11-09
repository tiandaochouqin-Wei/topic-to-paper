# 方法轨道：瓶颈说明（method_track.py headroom 第 7 项读它；HTML 注释和 <尖括号占位> 不算内容）

## 瞄准的瓶颈
<!-- 一句话：最强基线的哪一类错误是你要解决的。写具体的失败，不写"泛化性差"。 -->

## 证据文件
<!-- failure_slice.py 输出 / 误差分解表的项目内路径（必须真实存在），如 results/failure_slices.md -->

## 占基线误差的比例
<!-- 数：这类错误占最强基线总误差（或总损失的指标差）的百分之几，例如 "41%（failure_slices.md 第 3 节）"。小于 min_effect 能覆盖的量就不值得做 -->

## 理想解决后的上界怎么测
<!-- headroom.oracle：GT 路由 / oracle 选择 / 域内上界……在 dev 上跑 ≥3 seeds，run 标 role=oracle -->

## 为什么便宜做法不够
<!-- headroom.cheap_fixes：数据增强 / 更长训练 / 更大骨干 / 调参……各自在 dev 上跑过，拿走了多少提升空间（headroom 的 INFO 行） -->
