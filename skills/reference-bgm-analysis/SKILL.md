---
name: reference-bgm-analysis
description: 基于波形、能量、瞬态和节拍候选解释参考片声音与音乐结构
metadata:
  resource_version: 1.0.0
---

# 参考 BGM 分析

先确认 `audio_scope` 是混合节目音轨还是独立 BGM，再读取波形、能量、静音、瞬态、
tempo 和 beat 候选。

- tempo 和 beat 保持候选身份。
- 鼓、贝斯、旋律、人声和 SFX 属于 Agent 解释。
- 识别引入、蓄力、推进、高潮、缓冲和收尾段落。
- 每个声音层或段落判断附时间范围、置信度和证据引用。
