---
name: audiovisual-relation-analysis
description: 为参考学习提供视觉事件与音频事件的对齐方法，识别同步、蓄力、释放、延音和非节拍关系
metadata:
  resource_version: 1.1.0
---

# 音画关系分析方法

将 `MainShot` 边界、`InShotEvent`、运动和图层变化与 `AudioEvent`、`RhythmPattern`、静音、能量变化和 beat 候选对齐。

## 关系类型

- `sync`：视觉事件与目标声音事件在证据精度内同步发生；
- `anticipation`：视觉元素提前进入或动作提前展开，为后续声音事件蓄力；
- `post_beat_release`：视觉动作在声音事件后完成释放；
- `sustain`：视觉状态沿延音、持续能量或段落延续；
- `non_beat_binding`：视觉变化响应旋律、歌词、音色、叙事信息或其他非拍点因素。

## 判断原则

- 每个 `AudioVisualBinding` 写明视觉事件、声音事件、关系类型、实际时间差、作用解释、证据和置信度。
- 时间接近只构成同步候选；结合取证精度、连续节奏和前后事件确认关系。
- 分析画面响应的具体声音层，区分重拍、连续节拍组、旋律、人声、音色变化、留白和能量转折。
- 识别单素材、局部图层和整体合成画面是否响应不同声音事件。
- 将单次对齐放回前后 `RhythmUnit`，判断其在蓄力、推进、爆发或缓冲中的作用。
