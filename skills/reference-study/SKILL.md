---
name: reference-study
description: 编排参考来源、确定性证据、语义分析、报告生成和确认后知识发布
metadata:
  resource_version: 1.0.0
---

# 参考学习

1. 调用 `reference_resolve_source`，保存完整 `SourceMedia`。
2. 调用 `analysis_start`，通过 `analysis_get_job` 确认分析成功。
3. 按 `video-create://analysis/{analysis_id}/{evidence_id}` 读取联系表、帧、波形和候选事件；复杂区间调用 `analysis_refine_intervals`。
4. 分别执行画面、BGM、音画关系和剪辑语法分析。
5. 按 `schema_reference_study` 生成报告，调用 `analysis_validate_artifact`。
6. 调用 `report_generate`，向用户展示报告路径和待发布知识。
7. 调用 `knowledge_preview_publication`。
8. 用户明确确认后调用 `knowledge_publish`。
