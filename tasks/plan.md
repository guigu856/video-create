# Implementation Plan: 在当前主工作区逐步实现剪辑创作 Plugin

## 1. 目标

以 `D:\project\video_create` 当前工作区的完整状态作为唯一开发基础，按照
`docs/架构/剪辑创作插件架构设计.md` 分阶段实现剪辑创作 Plugin。当前工作区包含
`cbe62875b933ec455f719bbb5f125c2ac174a179` 之后尚未提交的关键帧、滤镜、转场、Web UI、
测试和验证产物；其中源码、测试与设计文档属于实现起点。

每次只交付一个可运行、可测试、可审查的小闭环。上一个检查点通过并确认后，才进入下一个
阶段。

`D:\project\video_create-plugin` 不属于本次实现依赖：

- 不复制其源码。
- 不继承其目录组织和内部抽象。
- 不为其接口增加兼容路径。
- 只在需要构造反例或核对外部行为时作为非权威参考。

## 2. 当前主工作区

### 唯一开发基础

```text
repository: D:\project\video_create
branch: main
starting_head: cbe62875b933ec455f719bbb5f125c2ac174a179
working_tree: 当前全部源码、测试和文档改动
schema_version: 2.0
```

当前工作区已有三类组件：

- `components/video_download`
- `components/material_acquisition`
- `components/video_editor`

当前实现保留以下稳定边界：

- 组件 Python API、CLI 与 HTTP 接口。
- `VideoEditorService.apply` 作为工程写入口。
- `expected_revision` 并发合同。
- 不可变渲染快照。
- FFmpeg 输出与 ffprobe 校验。

### 开发方式

- 直接在 `D:\project\video_create` 开发。
- 当前工作区是唯一主开发区。
- 当前分支在首个任务中原地统一为 `main`。
- 现有关键帧、滤镜、转场和 Web UI 代码全部保留，并作为当前编辑器能力。
- `output/` 下的成片、联系表和实验文件保留为本地验证证据，不纳入公共源码合同。
- 每个任务完成后形成可审查提交，再继续下一个任务。

## 3. 实施原则

### 3.1 垂直切片

每个任务交付一条从领域合同到测试的完整小路径，不先铺满全部目录、模型和 Handler。

### 3.2 依赖单向

```text
host manifests / rules / skills
                ↓
MCP adapters
                ↓
application services
                ↓
domain services / repositories / deterministic components
```

反向 import 由架构测试拦截。

### 3.3 冻结合同

每个阶段先冻结输入输出、错误码和版本，再实现行为。下游只消费已冻结合同，不反向修改上游
产物。

### 3.4 最小模块

- 一个模块只承担一个领域职责。
- MCP adapter 不持有业务状态。
- repository 不做工作流决策。
- component 不依赖 MCP、rules、skills 或宿主。
- 不提前抽象尚未出现的第二种实现。
- 不一次创建所有未来模块的空壳。

### 3.5 验证分层

以下证据分别记录：

- 单元测试。
- schema、lint、类型检查。
- MCP 协议握手。
- 真实组件运行。
- 真实浏览器操作。
- 真实 FFmpeg 渲染。
- 预览帧与导出帧视觉比较。
- Codex/Claude Code 宿主冒烟。

结构检查不替代真实运行证据。

## 4. 非目标

- 不实现管理后台。
- 多用户和远程服务不在本次范围内。
- 不实现分布式任务调度。
- 不一次性实现三类创作任务和全部引擎能力。
- 不把 Agent 推理写入组件或 MCP Server。
- 不把 rules、skills 和全部历史知识一次性加载。
- 不把运行输出、数据库或大媒体作为普通源码提交。
- 不顺带重构现有三个稳定组件。

## 5. 依赖图

```text
Phase 0 受控起点
  1 固定当前工作区主基线
    → 2 Plugin 身份与启动骨架
      → 3 依赖边界测试
        → 4 公共值对象与错误合同
          → 5 Context Catalog 最小闭环

Phase 1 参考学习纵向闭环
  6 工作流领域模型
    → 7 SQLite + 对象库
      → 8 阶段状态机
        → 9 FreezeRecord 与 stale
          → 10 StageEnvelope 与 access handle
            → 11 Workflow/Context MCP
  12 来源解析与探测
    → 13 视频证据
    → 14 音频证据
      → 15 分析 Job
        → 16 报告合同与校验
          → 17 报告生成与 Artifact 清单
            → 18 知识发布与检索
              → 19 reference_study 真实闭环

Phase 2 创作与执行闭环
  20 三阶段创作合同
    → 21 图片/视频素材准备
    → 22 BGM 准备
      → 23 PreparationPackageManifest
        → 24 EditingSpecification + ActionSpec
          → 25 Capability Registry + Preflight
            → 26 确定性编译 + SpecTraceMap
              → 27 Editor/Render MCP 薄映射
                → 28 RenderInspection + ExecutionManifest
                  → 29 original_creation 真实闭环
                  → 30 reference_guided_creation 真实闭环
                    → 31 第二宿主冒烟

Phase 3 引擎能力逐项扩展
  32-33 关键帧与缓动
    → 34-35 转场与效果作用域
      → 36-37 速度变化
        → 38-39 遮罩与裁切动画
          → 40 音频自动化与 ducking
            → 41 Composition 与跨镜头延续
              → 42 统一预览/导出一致性框架
```

## 6. 阶段任务

### Phase 0：受控起点

- [ ] Task 1：固定当前工作区主基线
- [ ] Task 2：建立最小 Plugin 身份、包和启动入口
- [ ] Task 3：建立依赖方向架构测试
- [ ] Task 4：建立公共错误、ID、时间、哈希和值对象
- [ ] Task 5：打通 Context Catalog 最小闭环

### Checkpoint A：Plugin 可安装、可启动、边界稳定

- [ ] 当前源码、测试、文档和验证证据均已盘点。
- [ ] 当前开发分支为 `main`。
- [ ] 现有关键帧、滤镜和转场测试保持通过。
- [ ] `video-create-mcp` 完成 initialize。
- [ ] `catalog` Resource 可读取。
- [ ] 依赖方向测试、pytest、Ruff、mypy 通过。
- [ ] 人工确认 Phase 0 后进入参考学习。

### Phase 1：参考学习纵向闭环

- [ ] Task 6：定义 TaskRun、StageRun、ArtifactEnvelope
- [ ] Task 7：实现 SQLite repository 与内容寻址对象库
- [ ] Task 8：实现参考学习阶段状态机
- [ ] Task 9：实现批准、冻结闭包和 stale 传播
- [ ] Task 10：实现 StageEnvelope 与 stage access handle
- [ ] Task 11：暴露 Workflow/Context MCP Resources 与 Tools
- [ ] Task 12：实现参考来源解析、media probe 与源文件固化
- [ ] Task 13：实现确定性视频分析证据
- [ ] Task 14：实现确定性音频分析证据
- [ ] Task 15：实现可恢复的分析 Job
- [ ] Task 16：定义参考报告与 EvidenceBundle 合同
- [ ] Task 17：实现报告生成、校验和主 Artifact 清单
- [ ] Task 18：实现批准后知识发布与阶段过滤检索
- [ ] Task 19：完成 Codex `reference_study` 真实闭环

### Checkpoint B：参考学习可真实使用

- [ ] 本地文件和下载视频均可进入分析。
- [ ] 主镜头区间覆盖全片且使用真实 PTS。
- [ ] 所有重要结论引用有效证据。
- [ ] 用户确认前不发布共享知识。
- [ ] 重开上游后旧 access handle 失效，下游标记 stale。
- [ ] Codex 完成一次真实参考学习并生成可打开报告。
- [ ] 人工确认 Phase 1 后进入创作流程。

### Phase 2：创作与执行闭环

- [ ] Task 20：定义三阶段创作产物与边界校验
- [ ] Task 21：实现图片/视频素材获取和预处理纵向切片
- [ ] Task 22：实现 BGM 获取、分析和 BgmPackage
- [ ] Task 23：实现 PreparationPackageManifest 与阶段二冻结
- [ ] Task 24：实现 EditingSpecification 与严格 ActionSpec
- [ ] Task 25：实现版本化 Capability Registry 与 Preflight
- [ ] Task 26：实现 EditorProject 与 SpecTraceMap 确定性编译
- [ ] Task 27：实现 Editor/Render MCP 薄映射
- [ ] Task 28：实现 RenderInspection 与 ExecutionManifest
- [ ] Task 29：完成 `original_creation` 真实闭环
- [ ] Task 30：完成 `reference_guided_creation` 真实闭环
- [ ] Task 31：完成 Claude Code 第二宿主冒烟

### Checkpoint C：三类任务形成完整闭环

- [ ] 阶段一不包含具体素材和执行参数。
- [ ] 阶段二不设计最终时间线。
- [ ] 阶段三只引用已冻结素材和 BGM。
- [ ] 每个 ActionSpec 都有 capability 结论。
- [ ] 能力齐备时每个 action_id 都有 TraceMap。
- [ ] 缺口场景只生成 CapabilityGapReport。
- [ ] 原创和参考驱动任务均生成真实成片。
- [ ] Codex 与 Claude Code 读取同一套 rules、skills 和 MCP。
- [ ] 人工确认 Phase 2 后进入引擎扩展。

### Phase 3：引擎能力逐项扩展

- [ ] Task 32：收口现有关键帧与缓动领域合同
- [ ] Task 33：补齐关键帧预览、FFmpeg 和 ActionSpec 闭环
- [ ] Task 34：收口现有转场与效果作用域合同
- [ ] Task 35：补齐转场预览、FFmpeg 和 ActionSpec 闭环
- [ ] Task 36：速度变化领域合同
- [ ] Task 37：速度预览、音频和 FFmpeg 闭环
- [ ] Task 38：遮罩与裁切动画领域合同
- [ ] Task 39：遮罩预览、FFmpeg 和 ActionSpec 闭环
- [ ] Task 40：音量包络、淡入淡出与 ducking 闭环
- [ ] Task 41：Composition 与跨镜头延续闭环
- [ ] Task 42：统一预览帧与导出帧一致性框架

### Checkpoint D：引擎能力闭合

- [ ] 每项能力分别通过模型、命令、预检、编译、预览和导出测试。
- [ ] Capability Registry 只登记已完成纵向验证的能力。
- [ ] Python、CLI、HTTP、MCP 使用同一 EditorProject 语义。
- [ ] 关键帧、转场、速度、遮罩和 Composition 均有真实渲染证据。
- [ ] 浏览器预览帧和导出帧满足架构文档容差。

## 7. 每个任务的完成定义

每项任务同时满足：

- 只修改该任务直接涉及的最小文件集合。
- 验收测试先失败、实现后通过。
- 受影响模块 focused tests 通过。
- 完整 pytest、Ruff、mypy 保持通过。
- 新增公共合同同步 schema 和文档。
- 没有临时兼容路径、无用抽象和对话痕迹。
- 交接列出文件、原因、验证、风险和下一任务。

## 8. 阶段外风险

| 风险 | 处理 |
| :-- | :-- |
| 当前工作区混合源码与运行产物 | 首任务分类盘点；源码、测试和文档进入主基线，output 保留为本地证据 |
| 再次形成一步到位的大模块 | 每个任务限制为一个合同或一个纵向切片 |
| MCP Handler 堆积业务逻辑 | 架构测试限制 import，Handler 只映射 application service |
| schema 与模型漂移 | 每个公共模型生成/校验 schema，并加入合同测试 |
| 测试依赖历史 output | 测试只使用受控夹具和临时目录 |
| 真实验证被单元测试替代 | 每个 Checkpoint 单列真实媒体、浏览器、FFmpeg 和宿主证据 |
| 旧 Plugin 影响新设计 | 不引用其内部模块，不增加兼容合同 |
| 引擎能力提前扩散到创作层 | Registry 未登记前统一返回 CapabilityGap |

## 9. 执行入口

计划确认后只执行 Task 1。Task 1 在当前工作区原地完成验证和主基线提交，再开始 Task 2；
不批量启动后续任务。
