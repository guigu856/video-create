---
name: reference-study
description: 参考视频学习的唯一主入口；读取真实画面和声音证据，在宿主上下文生成普通用户能看懂的五章视频拆解与第六章候选知识 DOCX，并在用户确认后一次发布选中的可迁移知识
metadata:
  resource_version: 1.2.0
---

# 参考学习

## 职责

在同一宿主上下文完成来源处理、证据获取、语义分析、六章 DOCX 组装、候选知识确认和确认后发布。

前五章面向没有剪辑和音频工程知识的普通用户。`reference-visual-analysis`、`reference-bgm-analysis`、`audiovisual-relation-analysis` 与 `editing-grammar-synthesis` 提供专业分析方法，最终报告把内部结构翻译成直接、易读的中文。

## 执行流程

1. 输入尚未形成 `SourceMedia` 时调用 `reference_resolve_source`，保留完整来源身份。
2. 调用 `analysis_start`。任务处于运行状态时调用 `analysis_get_job`，直到获得完成状态与 `analysis_id`。
3. 按 `video-create://analysis/{analysis_id}/{evidence_id}` 读取联系表、帧、波形、候选边界和声音变化。明确证据不足时调用 `analysis_refine_intervals`，再读取新增证据。
4. 实际查看画面并听取声音。应用四个专业 Skill 的方法，建立音乐段落、主要画面时间线、声音和画面配合以及可以重复使用的剪法。
5. 分类候选知识前，按候选涉及阶段调用 `knowledge_list_stage_types(stage)`。已有视频类型名称语义相符时复用，否则使用简洁的新名称。
6. 以候选知识的阶段、视频类型、知识类型和正文调用 `knowledge_search`。发现同义机制时填写命中的 `existing_knowledge_id`。
7. 调用宿主文档能力，在当前上下文直接生成并展示完整六章 DOCX，并停在候选知识确认环节。Plugin MCP 只负责证据与确认后的知识发布。
8. 用户确认全部候选或明确排除部分 `local_id` 后，只将最终条目组成一次 `knowledge_publish` 调用。发布输入只包含 `analysis_id` 与 `units`。

## 证据和表达

每个重要结论依次说明：

```text
实际看到或听到了什么
我们的分析判断是什么
画面依据
声音依据
把握程度：高 / 中 / 低
```

原始时间、帧、波形、瞬态和候选边界属于证据；剪辑意图、观看作用、声音解释和可迁移方法属于分析判断。重要结论引用真实 Evidence Resource。证据不足的判断降低把握程度或补充取证。

报告内可使用 `F0001`、`A001` 等证据编号。`RhythmUnit`、`MainShot`、`InShotEvent`、`MusicSection`、`AudioVisualBinding` 和 `EditingSentence` 等内部字段不进入用户可见的前五章正文。

## 六章 DOCX

### 第一章：先用一分钟看懂这条视频

依次说明：

1. 这是一条什么视频；
2. 它最主要的一至三个吸引力；
3. 素材、镜头、音乐、文字和效果大致怎样组织；
4. 观众感受如何从开头发展到结尾；
5. 一句话总结。

本章只保留全片主线，不堆叠逐镜细节。

### 第二章：音乐和声音是怎么带动视频的

说明整体听感、音乐段落、重要声音变化、音乐从弱到强及停顿释放的过程，以及音乐强弱如何影响镜头长度和画面变化数量。

使用：

| 时间 | 音乐发生了什么 | 强弱变化 | 画面如何配合 |
| :-- | :-- | :-- | :-- |

| 时间 | 听到了什么变化 | 画面发生了什么 | 带来的感觉 |
| :-- | :-- | :-- | :-- |

tempo、beat 与瞬态保持候选身份。重点解释确实影响剪辑和观看感受的声音变化，不机械列出全部鼓点。

### 第三章：画面是怎么一段段剪出来的

本章先提供连续覆盖全片的简明时间线：

| 时间 | 主要画面 | 画面里的变化 | 对应声音 | 产生的作用 |
| :-- | :-- | :-- | :-- | :-- |

再详解最值得学习的片段。每个重点片段写明：时间、实际画面、处理动作、声音配合、观看作用、可以学到的方法、画面依据、声音依据和把握程度。

主要画面或叙事承载内容真实改变时才建立新片段；画中画、字幕、遮罩、缩放、位移、旋转、透明度及局部或整体效果写在“画面里的变化”中。

### 第四章：声音和画面是怎么配合的

解释当前视频实际使用的五类关系：

1. 声音和画面同时发生；
2. 画面提前行动；
3. 声音出现后画面再释放；
4. 持续声音连接前后画面；
5. 画面跟随歌词、情绪或音色，而不是机械卡点。

再整理可以重复使用的剪法。每种剪法写明名称、适用场景、操作顺序、观看效果、参考时间、画面依据、声音依据和把握程度。名称直接描述动作，例如“相同方向连接”“先慢后快再停一下”“重拍负责冲击、尾音负责连接”。

### 第五章：如果重新做一条，应该学什么

依次说明：

1. 最值得保留的观看体验；
2. 可以直接复用的方法；
3. 不应照搬的原片人物、素材、绝对时间点、坐标和效果参数；
4. 使用新素材重新创作的步骤；
5. 最终检查表。

重新创作迁移节奏密度、动作关系、声音和画面配合、观看体验及素材选择原则，不复刻原片身份和专属参数。

### 第六章：待沉淀知识

按“阶段 → 视频类型 → 知识类型”展示候选知识。用户可见说明使用中文直述；提交给 MCP 的机器字段保持以下合同：

```text
local_id: K001
stage: stage1 | stage2 | stage3
video_types: [一个或多个动态视频类型]
knowledge_type: 所属阶段的知识类型
content: 适用条件 → 操作或组合方法 → 预期观看作用
evidence_refs: [一个或多个 Evidence Resource，可附 start_ms 与 end_ms]
confidence: medium | high
existing_knowledge_id: 仅在检索确认同义机制时填写
```

`local_id` 从 `K001` 起连续编号，只用于当前上下文选择。一条知识可关联多个视频类型，正文只展示一次。用户可以按 `local_id` 排除候选。

## 知识分类

每条知识只有一个阶段、一个知识类型和一份正文，可以关联多个动态视频类型。一个观察方法服务多个阶段时，分别编写符合各阶段用途的原子知识。

| 阶段 | knowledge_type |
| :-- | :-- |
| `stage1` | `core_mechanism`、`production_method`、`visual_language`、`rhythm_method`、`transition_principle`、`asset_music_traits`、`viewing_experience` |
| `stage2` | `asset_selection_traits`、`shot_composition_traits`、`action_direction_traits`、`preprocess_need`、`bgm_mood`、`music_sections`、`energy_curve`、`rhythm_events` |
| `stage3` | `editing_sentence`、`shot_switch_logic`、`layer_composition_pattern`、`motion_pattern`、`effect_scope`、`audio_visual_binding`、`cross_shot_continuity`、`density_pattern`、`transition_pattern` |

候选知识满足：

- 可以迁移到其他素材或项目；
- 一条只表达一个规律；
- 至少引用一个真实 Evidence Resource；
- 正文聚焦通用方法，原片素材名称、绝对时间点、坐标和效果参数留在证据中；
- 置信度为 `medium` 或 `high`。
