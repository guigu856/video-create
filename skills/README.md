# Skills

每个阶段 Skill 使用独立子目录和 `SKILL.md`，只承载证据检查、推理步骤、工具调用与产物模板。
任务类型判断由 `rules/main-agent.md` 负责，不建立重复分类规则的路由 Skill。

目录结构：

```text
skills/{skill_id}/SKILL.md
```

`SKILL.md` frontmatter 必须包含资源版本：

```yaml
---
name: editing-specification
description: 生成逐镜表和编辑规格
metadata:
  resource_version: 1.0.0
---
```

Context Catalog 与构建系统从该目录受控发现 Skill；`name` 必须与目录名一致。
