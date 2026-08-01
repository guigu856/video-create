---
name: reference-study
description: 参考视频学习的唯一主入口；读取真实音画证据，调用专业分析方法，在宿主上下文中生成并展示六章 DOCX，并在用户确认后一次发布选中的可迁移知识
metadata:
  resource_version: 1.1.0
---

# 参考学习

## 职责

在同一宿主上下文中完成证据获取、语义分析、六章 DOCX 组装与展示、候选知识确认和确认后发布。
`reference-visual-analysis`、`reference-bgm-analysis`、
`audiovisual-relation-analysis` 与 `editing-grammar-synthesis` 只提供分析方法，
最终产物统一由本 Skill 组织。

## 执行流程

1. 输入尚未形成 `SourceMedia` 时调用 `reference_resolve_source`，保留完整来源身份。
2. 调用 `analysis_start`。任务处于运行状态时调用 `analysis_get_job`，直到获得完成状态与 `analysis_id`。
3. 按 `video-create://analysis/{analysis_id}/{evidence_id}` 读取联系表、帧、波形、候选边界和音频事件。存在明确证据缺口时调用 `analysis_refine_intervals`，再读取新增证据。
4. 应用四个专业 Skill 的方法，在同一分析中建立独立 BGM 时间线、三层画面结构、音画绑定与剪辑句式。
5. 分类候选知识前，按候选涉及的阶段调用 `knowledge_list_stage_types(stage)`。语义相符时复用已有视频类型名称；现有名称均不贴合时使用简洁的新名称。
6. 以候选知识的阶段、视频类型、知识类型和正文调用 `knowledge_search`。发现同义机制时填写命中的 `existing_knowledge_id`；其他候选保持新建状态。
7. 调用宿主文档能力，在当前上下文直接生成并展示完整六章 DOCX，并停留在候选知识确认环节。DOCX 由宿主上下文承载，Plugin MCP 只负责证据与确认后的知识发布。
8. 用户明确确认全部候选，或明确排除部分 `local_id` 后，只将最终选中的条目组成一次 `knowledge_publish` 调用。发布输入仅包含 `analysis_id` 与 `units`。

## 证据与判断

关键分析单元分别表达：

```text
可观察事实
分析判断
声音依据
画面依据
置信度
```

使用 `RU-01`、`MS-01`、`IE-01`、`AE-01` 等报告内编号建立交叉引用。
原始时间、帧、波形、瞬态和候选边界属于证据；剪辑动机、观看作用、声音层解释和可迁移机制属于分析判断。重要结论引用真实 Evidence Resource。低置信度判断可保留在分析章节，候选知识只采用 `medium` 或 `high`。

## 六章 DOCX 上下文文档

始终按以下顺序交付一份连续可读的文档。参考片中缺少某种手法时，以实际证据组织该章内容，避免用空字段填充。

### 一、参考视频总体概括

说明视频类型与核心机制、整体制作方法、视觉语言、节奏与声音使用、转场与镜头连接、素材与音乐性质，以及预期观看体验。

### 二、BGM 结构分析

建立独立音乐时间线，分析实际存在的：

- `MusicSection`：引入、蓄力、推进、高潮、缓冲、收尾及其他段落；
- `MusicLayer`：鼓、贝斯、旋律、人声、音效及其他可辨识声音层；
- `RhythmPattern`：连续节拍组、重拍组合、切分和重复节奏型；
- `AudioEvent`：重音、空拍、停顿、新音色、能量释放和结构转折；
- `EnergyCurve`：能量的上升、下降、维持、停顿和释放。

tempo、beat 与瞬态保持候选身份，分析重点放在具有剪辑意义的节奏型和结构变化。

### 三、参考片逐镜效果分析

使用 `RhythmUnit → MainShot → InShotEvent` 三层结构。`MainShot` 只在主画面或叙事承载画面真实变化时建立；画中画、辅助图层、字幕、遮罩、缩放、位移、旋转、透明度及局部或整体效果作为 `InShotEvent`。

逐镜表至少包含：时间范围、节奏单元、主镜头、镜内事件与图层、对应音乐事件、音画关系、效果作用范围、组合关系、观看作用、可迁移规律、证据引用与置信度。时间边界使用真实 PTS 对应的整数微秒，并连续覆盖全片。

### 四、音画关系与剪辑语法

将视觉事件与音频事件组织为 `AudioVisualBinding`，写明关系类型、实际时间差和视觉作用。再将连续 `RhythmUnit` 归纳为 `EditingSentence`，解释镜头密度、图层组合、动作衔接、提前进入、延迟退出、跨镜延续、快切与缓冲等规律。

### 五、整体总结与重新创作原则

总结核心观看目标、BGM 利用方式、视觉密度、冲击结构和情绪节奏。重新创作迁移节奏密度、动作组合、音画关系和观看体验机制；参考片专属画面、素材身份、绝对时间点、坐标和效果参数只作为分析证据。

### 六、待沉淀知识

按“阶段 → 视频类型 → 知识类型”展示候选知识。每条候选采用以下结构：

```text
local_id: K001
stage: stage1 | stage2 | stage3
video_types: [一个或多个动态视频类型]
knowledge_type: 所属阶段的知识类型
content: 适用条件 → 剪辑动作或组合机制 → 预期视觉与观看作用
evidence_refs: [一个或多个 Evidence Resource，可附 start_ms 与 end_ms]
confidence: medium | high
existing_knowledge_id: 仅在检索确认同义机制时填写
```

`local_id` 从 `K001` 起连续编号，只承担当前上下文中的选择标识。一条知识可关联多个视频类型，正文展示一次。用户可按 `local_id` 排除任意候选。

## 知识分类

每条知识只有一个阶段、一个知识类型和一份正文，可关联一个或多个动态视频类型。一个观察机制服务多个阶段时，分别编写符合各阶段用途的原子知识。

| 阶段 | knowledge_type |
| :-- | :-- |
| `stage1` | `core_mechanism`、`production_method`、`visual_language`、`rhythm_method`、`transition_principle`、`asset_music_traits`、`viewing_experience` |
| `stage2` | `asset_selection_traits`、`shot_composition_traits`、`action_direction_traits`、`preprocess_need`、`bgm_mood`、`music_sections`、`energy_curve`、`rhythm_events` |
| `stage3` | `editing_sentence`、`shot_switch_logic`、`layer_composition_pattern`、`motion_pattern`、`effect_scope`、`audio_visual_binding`、`cross_shot_continuity`、`density_pattern`、`transition_pattern` |

候选知识满足以下准入条件：

- 可迁移到其他素材或项目；
- 一条只表达一个规律；
- 至少引用一个关键分析单元或真实 Evidence Resource；
- 正文聚焦通用机制，参考片专属素材名称、绝对时间点、坐标和效果参数留在分析证据中；
- 置信度为 `medium` 或 `high`。
