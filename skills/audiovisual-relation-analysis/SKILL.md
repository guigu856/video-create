---
name: audiovisual-relation-analysis
description: 对齐视觉事件与音频事件并解释同步、蓄力、释放、延音和非节拍关系
metadata:
  resource_version: 1.0.0
---

# 音画关系分析

将视觉边界、运动和图层事件与瞬态、静音、能量和节拍候选对齐。

关系类型只使用：

- `sync`
- `anticipation`
- `post_beat_release`
- `sustain`
- `non_beat_binding`

报告实际时间差和证据。接近不等于同步；无稳定节拍时使用非节拍关系。
