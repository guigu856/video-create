---
name: reference-visual-analysis
description: 使用真实 PTS、证据帧和候选边界形成参考片逐镜画面分析
metadata:
  resource_version: 1.0.0
---

# 参考画面分析

读取 `frame_index`、`boundary_candidates`、联系表及候选前后证据帧。

- 自动边界只作为复核候选。
- 主画面真实更换才建立新主镜头。
- 记录主画面、可见图层、空间关系、运动、动画与效果作用域。
- 快切或复杂叠层区间使用不大于 0.1 秒的密集取证。
- 所有镜头使用真实 PTS 对应的整数微秒边界，并连续覆盖全片。
