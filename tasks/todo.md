# 当前主工作区剪辑创作 Plugin 实施任务清单

> 设计：`D:\project\video_create\docs\架构\剪辑创作插件架构设计.md`
> 起始 HEAD：`cbe62875b933ec455f719bbb5f125c2ac174a179`
> 开发基础：当前工作区全部源码、测试和文档改动
> 实现仓库：`D:\project\video_create`

## Phase 0：受控起点

## Task 1: 固定当前工作区主基线

**Description:** 直接盘点当前工作区，将现有关键帧、滤镜、转场、Web UI、测试和设计文档
作为新实现起点；区分源码与本地 output 证据，并把当前分支原地统一为 `main`。

**Acceptance criteria:**
- [x] 当前源码、测试、文档和 output 产物完成分类清单。
- [x] 当前开发分支为 `main`，工作目录仍为 `D:\project\video_create`。
- [x] 当前 238 项测试、Ruff、mypy 和 JavaScript 语法检查保持通过。
- [x] 当前源码、测试和设计文档形成可审查的主基线提交。

**Verification:**
- [x] `git branch --show-current` 返回 `main`。
- [x] `git status --short --branch` 仅保留明确排除的本地 output 证据。
- [x] `uv run pytest -q`、`uv run ruff check .`、`uv run mypy`。
- [x] 全部 Web JavaScript 执行 `node --check`。

**Dependencies:** None

**Files likely touched:**
- `D:\project\video_create\docs\实施\当前主基线.md`
- `D:\project\video_create\.gitignore`

**Estimated scope:** Small

## Task 2: 建立最小 Plugin 身份、包和启动入口

**Description:** 只创建可安装、可启动、可完成 MCP initialize 的最小 Plugin，不提前加入
业务工具、知识和分析模块。

**Acceptance criteria:**
- [x] `.codex-plugin`、`.claude-plugin` 和 `.mcp.json` 使用同一身份。
- [x] `video-create-mcp` 可启动并完成 initialize。
- [x] wheel 包含启动所需 manifest。

**Verification:**
- [x] `uv build`。
- [x] 在临时环境安装 wheel。
- [x] MCP initialize 冒烟通过。

**Dependencies:** Task 1

**Files likely touched:**
- `D:\project\video_create\pyproject.toml`
- `D:\project\video_create\.mcp.json`
- `D:\project\video_create\.codex-plugin\plugin.json`
- `D:\project\video_create\.claude-plugin\plugin.json`
- `D:\project\video_create\video_create_plugin\mcp\server.py`

**Estimated scope:** Medium

## Task 3: 建立依赖方向架构测试

**Description:** 在新增业务模块前固定 package 依赖方向，防止 MCP、application、
repository 和 components 互相反向依赖。

**Acceptance criteria:**
- [x] 禁止 components import Plugin、MCP、rules 或 skills。
- [x] 禁止 repository import MCP adapter。
- [x] 架构违规测试提供具体 import 路径。

**Verification:**
- [x] `uv run pytest tests/test_architecture_boundaries.py -q`。
- [x] 人工注入一条反向 import 时测试失败，移除后通过。

**Dependencies:** Task 2

**Files likely touched:**
- `D:\project\video_create\tests\test_architecture_boundaries.py`
- `D:\project\video_create\video_create_plugin\application\__init__.py`
- `D:\project\video_create\video_create_plugin\mcp\__init__.py`
- `D:\project\video_create\video_create_plugin\repository\__init__.py`

**Estimated scope:** Small

## Task 4: 建立公共错误、ID、时间、哈希和值对象

**Description:** 定义所有后续模块共用的最小值对象和稳定错误响应，避免各模块重复字符串、
时间单位和哈希逻辑。

**Acceptance criteria:**
- [x] 内部时间统一使用整数微秒。
- [x] `FileRef` 只包含受控路径、SHA-256 和可选 Schema 版本，不包含任务、阶段或 revision。
- [x] MCP 成功和错误响应结构固定。

**Verification:**
- [x] 值对象边界测试通过。
- [x] `FileRef` JSON round-trip 和哈希稳定性测试通过。

**Dependencies:** Task 3

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\contracts.py`
- `D:\project\video_create\video_create_plugin\errors.py`
- `D:\project\video_create\tests\test_plugin_contracts.py`
- `D:\project\video_create\schemas\common.schema.json`

**Estimated scope:** Medium

## Task 5: 打通 Context Catalog 最小闭环

**Description:** 只实现 catalog、单个 main rule 和 schema Resource 的发现与读取，验证
渐进式上下文加载边界；任务类型判断直接由 main rule 约束。

**Acceptance criteria:**
- [x] catalog 列出内容 ID、版本、类型和 URI。
- [x] Resource 读取只返回请求内容。
- [x] rule、skill 和 schema 校验失败具有稳定错误码。

**Verification:**
- [x] `resources/list` 和 `resources/read` 冒烟通过。
- [x] catalog 与文件内容版本测试通过。

**Dependencies:** Task 4

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\context\catalog.py`
- `D:\project\video_create\rules\main-agent.md`
- `D:\project\video_create\schemas\catalog.schema.json`
- `D:\project\video_create\tests\test_context_catalog.py`

**Estimated scope:** Medium

## Checkpoint A: Plugin 可安装、可启动、边界稳定

- [x] 当前主工作区和 `main` 分支保持唯一开发入口。
- [x] 现有剪辑器能力保持通过。
- [x] wheel 安装与 MCP initialize 通过。
- [x] catalog Resource 可读取。
- [x] 架构边界测试、pytest、Ruff、mypy 通过。
- [ ] 人工确认后进入 Phase 1。

## Phase 1：参考学习纵向闭环

## Task 6: 实现参考来源解析、media probe 和源文件固化

**Description:** 接收本地路径、URL 或分享文本，复用下载组件并生成媒体哈希与 ffprobe
元数据。

**Acceptance criteria:**
- [x] 本地文件和下载结果进入同一 SourceMedia 合同。
- [x] 源文件哈希、时长、流和 time base 固化。
- [x] 下载逻辑仍归现有组件所有。

**Verification:**
- [x] 本地媒体和 fake download 测试通过。
- [x] 真实 ffprobe 冒烟通过。

**Dependencies:** Task 4

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\analysis\source.py`
- `D:\project\video_create\video_create_plugin\analysis\models.py`
- `D:\project\video_create\tests\test_reference_source.py`

**Estimated scope:** Small

## Task 7: 实现确定性视频分析证据

**Description:** 使用真实 PTS 生成候选切点、帧、联系表和区间细化证据，不输出语义创作
结论。

**Acceptance criteria:**
- [x] 帧引用包含 PTS、时间戳、路径和 SHA-256。
- [x] 快切区间支持不大于 0.1 秒最大采样间隔。
- [x] 自动候选与 Agent 确认镜头明确区分。

**Verification:**
- [x] 合成视频切点和 PTS 测试通过。
- [x] 真实短视频生成可查看联系表。

**Dependencies:** Task 6

**Files likely touched:**
- `D:\project\video_create\components\video_analysis\service.py`
- `D:\project\video_create\components\video_analysis\models.py`
- `D:\project\video_create\tests\test_video_analysis.py`
- `D:\project\video_create\docs\组件\视频分析组件.md`

**Estimated scope:**  Medium

## Task 8: 实现确定性音频分析证据

**Description:** 提取波形、能量、瞬态、节拍候选和声音事件候选，明确混合节目音轨与独立
BGM 的证据边界。

**Acceptance criteria:**
- [x] 音频结果记录采样率、声道、时间范围和 SHA-256。
- [x] tempo 和 beat 只作为带置信度候选。
- [x] Agent 语义判断不进入组件。

**Verification:**
- [x] 合成节拍和静音音频测试通过。
- [x] 真实音轨生成波形和候选事件。

**Dependencies:** Task 6

**Files likely touched:**
- `D:\project\video_create\components\audio_analysis\service.py`
- `D:\project\video_create\components\audio_analysis\models.py`
- `D:\project\video_create\tests\test_audio_analysis.py`
- `D:\project\video_create\docs\组件\音频分析组件.md`

**Estimated scope:** Medium

## Task 9: 实现可恢复的分析 Job

**Description:** 将视频和音频分析编排为持久 Job，支持进度、错误、重启恢复和指定区间细化。

**Acceptance criteria:**
- [x] queued、running、succeeded、failed 状态持久化。
- [x] 重启后 queued 继续，旧 running 标记 interrupted。
- [x] 已完成内容哈希步骤可复用。

**Verification:**
- [x] 重启、失败和细化测试通过。
- [x] Job 输出只引用组件证据文件和分析目录。

**Dependencies:** Tasks 7, 8

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\analysis\jobs.py`
- `D:\project\video_create\video_create_plugin\analysis\service.py`
- `D:\project\video_create\video_create_plugin\repository\jobs.py`
- `D:\project\video_create\tests\test_analysis_jobs.py`

**Estimated scope:** Medium

## Task 10: 收拢 EvidenceBundle 与稳定数据根

**Description:** EvidenceBundle 只由已完成 Analysis Job 和真实组件结果确定性构造；
分析模块逐文件核对受控路径与 SHA-256。默认持久数据根固定为 `~/.video-create/`。

**Acceptance criteria:**
- [x] EvidenceEntry、EvidenceBundle 和构造逻辑归入 analysis 模块。
- [x] 分析结果文件与嵌套证据文件均核对真实 SHA-256。
- [x] Context Catalog、安装包和运行时中移除报告 Schema、Manifest 与生成链。

**Verification:**
- [x] 确定性构造、结果篡改和证据篡改测试通过。
- [x] 两个安装目录使用同一默认数据根合同。

**Dependencies:** Task 9

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\analysis\models.py`
- `D:\project\video_create\video_create_plugin\analysis\evidence.py`
- `D:\project\video_create\video_create_plugin\application\reference_runtime.py`
- `D:\project\video_create\tests\test_analysis_evidence.py`

**Estimated scope:** Medium

## Task 11: 实现 LanceDB 单库原子知识发布

**Description:** 用户确认后，Agent 一次提交 `analysis_id + units`。服务验证证据归属，
在共享写锁内创建新知识或显式合并，并用一次 LanceDB `merge_insert` 提交整批最终行。

**Acceptance criteria:**
- [x] 一条知识只有一个阶段、一个知识类型、多个动态视频类型和一份正文向量。
- [x] 任一输入无效时整批零写入。
- [x] 显式合并保留规范正文和向量，只追加视频类型、证据与来源分析。
- [x] 并发合并同一知识时保留双方新增内容。

**Verification:**
- [x] 新建、批次失败、证据越界、幂等合并和并发合并测试通过。
- [x] Server 重启后从同一 `knowledge.lancedb/` 读取相同知识。

**Dependencies:** Task 10

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\knowledge\models.py`
- `D:\project\video_create\video_create_plugin\knowledge\store.py`
- `D:\project\video_create\video_create_plugin\application\knowledge.py`
- `D:\project\video_create\tests\test_knowledge_publication.py`

**Estimated scope:** Medium

## Task 12: 实现实时类型汇总与离线中文语义检索

**Description:** 类型直接从 active 知识实时汇总；搜索先在 LanceDB 预过滤阶段、视频类型和
知识类型，再使用随 Plugin 分发的固定中文模型对正文执行余弦排序。

**Acceptance criteria:**
- [x] `knowledge_list_stage_types` 不依赖类型注册表。
- [x] 多个视频类型使用 ANY 语义，archived 和其他阶段不进入结果。
- [x] FastEmbed 模型从 Plugin 资产离线加载，发布和查询共用 512 维空间。

**Verification:**
- [x] 类型计数、ANY 过滤、预过滤、归档排除和 SQL 字面量测试通过。
- [x] 模型资产哈希、离线加载、中文语义排序和 wheel 文件测试通过。

**Dependencies:** Task 11

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\knowledge\embedding.py`
- `D:\project\video_create\video_create_plugin\knowledge\store.py`
- `D:\project\video_create\video_create_plugin\mcp\reference.py`
- `D:\project\video_create\tests\test_knowledge_search.py`
- `D:\project\video_create\tests\test_knowledge_embedding.py`

**Estimated scope:** Medium

## Task 13: 完成 Codex reference_study 真实闭环

**Description:** 使用真实参考视频，经 MCP、按需上下文加载、分析、六章上下文文档、
用户确认和一次知识发布完成完整任务。

**Acceptance criteria:**
- [ ] 从 source resolve 到知识发布的证据和来源可追溯。
- [ ] 六章上下文文档包含画面、BGM、音画关系和可迁移剪辑语法。
- [ ] 用户确认前不调用知识发布工具。

**Verification:**
- [ ] Codex 宿主真实执行。
- [ ] MCP Inspector 完整握手。
- [ ] 证据和知识来源哈希检查通过。

**Dependencies:** Tasks 5, 12

**Files likely touched:**
- `D:\project\video_create\tests\test_reference_study_e2e.py`
- `D:\project\video_create\docs\命令速查.md`

**Estimated scope:** Medium

## Checkpoint B: 参考学习可真实使用

- [ ] 默认测试与真实媒体验证分别通过。
- [ ] 真实 PTS、证据引用和知识发布通过。
- [ ] Codex 参考学习六章上下文文档可查看。
- [ ] 人工确认后进入 Phase 2。

## Phase 2：创作与执行闭环

## Task 14: 定义三阶段创作产物与边界校验

**Description:** 定义 CreativeDirection、PreparationPackageManifest 和
EditingSpecification 的阶段合同及禁止字段。

**Acceptance criteria:**
- [ ] 阶段一排除素材、秒点和执行参数。
- [ ] 阶段二排除最终时间线。
- [ ] 阶段三只接受用户确认且实际存在的素材和 BGM 文件。

**Verification:**
- [ ] 三阶段正反例、缺失文件和哈希不符测试通过。

**Dependencies:** Task 13

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\creation\models.py`
- `D:\project\video_create\video_create_plugin\creation\validator.py`
- `D:\project\video_create\schemas\creation.schema.json`
- `D:\project\video_create\tests\test_creation_contracts.py`

**Estimated scope:** Medium

## Task 15: 实现图片/视频素材获取和预处理纵向切片

**Description:** 复用现有视频素材服务，新增一个图片来源和声明式预处理，并统一 provenance
合同。

**Acceptance criteria:**
- [ ] 搜索、获取、哈希、授权和派生关系完整。
- [ ] 预处理输出引用原始素材并记录参数。
- [ ] 当前切片只支持一个明确图片来源和最小预处理集合。

**Verification:**
- [ ] fake source、真实下载和预处理测试通过。

**Dependencies:** Task 14

**Files likely touched:**
- `D:\project\video_create\components\image_acquisition\service.py`
- `D:\project\video_create\components\media_preprocessing\service.py`
- `D:\project\video_create\video_create_plugin\application\materials.py`
- `D:\project\video_create\tests\test_material_preparation.py`
- `D:\project\video_create\schemas\material-package.schema.json`

**Estimated scope:** Medium

## Task 16: 实现 BGM 获取、分析和 BgmPackage

**Description:** 实现一个 BGM 来源、下载授权记录、片段选择和音频分析包，不与普通视频
素材服务混合。

**Acceptance criteria:**
- [ ] 原始音乐与选用片段分开保存和追溯。
- [ ] BgmPackage 包含来源、授权、段落、节拍候选和能量。
- [ ] 音频分析复用 Task 8 组件。

**Verification:**
- [ ] fake source、真实音频和越界片段测试通过。

**Dependencies:** Tasks 8, 14

**Files likely touched:**
- `D:\project\video_create\components\bgm_acquisition\service.py`
- `D:\project\video_create\video_create_plugin\application\bgm.py`
- `D:\project\video_create\schemas\bgm-package.schema.json`
- `D:\project\video_create\tests\test_bgm_preparation.py`

**Estimated scope:** Medium

## Task 17: 实现 PreparationPackageManifest

**Description:** 汇总可并行产生的 MaterialPackage、BgmPackage 和 provenance 文件，
供 Agent 展示并在用户确认后交给阶段三。

**Acceptance criteria:**
- [ ] manifest 列出所有素材、BGM 和 provenance 文件的相对路径与哈希。
- [ ] 任一文件缺失或哈希不符时校验失败。
- [ ] 阶段三只读取 Agent 传入的确认版 manifest。

**Verification:**
- [ ] 并行结果汇总、缺失 parent 和篡改测试通过。

**Dependencies:** Tasks 15, 16

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\creation\preparation.py`
- `D:\project\video_create\video_create_plugin\application\preparation.py`
- `D:\project\video_create\tests\test_preparation_manifest.py`

**Estimated scope:** Small

## Task 18: 实现 EditingSpecification 与严格 ActionSpec

**Description:** 定义人类表格与机器 ActionSpec 的同源合同，包括 shot/action 稳定 ID、
时间范围、素材引用、作用域和能力要求。

**Acceptance criteria:**
- [ ] shot 和 action 双向引用完整。
- [ ] 主镜头时间线无空洞。
- [ ] 所有素材引用属于输入的 PreparationPackageManifest。

**Verification:**
- [ ] schema、时间线、引用和内容哈希测试通过。

**Dependencies:** Task 17

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\editing\models.py`
- `D:\project\video_create\video_create_plugin\editing\validator.py`
- `D:\project\video_create\schemas\editing-specification.schema.json`
- `D:\project\video_create\tests\test_editing_specification.py`

**Estimated scope:** Medium

## Task 19: 实现版本化 Capability Registry 与 Preflight

**Description:** 根据当前基线编辑器真实能力建立版本化 Registry，逐 action 输出支持或缺口
结论。

**Acceptance criteria:**
- [ ] Registry 首版只登记基线实际能力。
- [ ] 每个 action 都有独立 capability check。
- [ ] 存在缺口时生成 CapabilityGapReport 并停止编译。

**Verification:**
- [ ] 支持、缺口和 Registry 版本测试通过。

**Dependencies:** Task 18

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\editing\capabilities.py`
- `D:\project\video_create\video_create_plugin\editing\preflight.py`
- `D:\project\video_create\schemas\capability-assessment.schema.json`
- `D:\project\video_create\tests\test_capability_preflight.py`

**Estimated scope:** Medium

## Task 20: 实现 EditorProject 与 SpecTraceMap 确定性编译

**Description:** 只消费严格 ActionSpec，把受支持动作映射为 EditorProject，并输出逐 action
的稳定工程路径。

**Acceptance criteria:**
- [ ] 编译不解析自由文本。
- [ ] 每个受支持 action_id 都有 TraceMap。
- [ ] 输入哈希、schema 和 Registry 版本写入编译结果。

**Verification:**
- [ ] 相同输入重复编译字节稳定。
- [ ] EditorProject Pydantic 和领域校验通过。

**Dependencies:** Task 19

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\video_create_plugin\editing\trace.py`
- `D:\project\video_create\schemas\execution-project.schema.json`
- `D:\project\video_create\tests\test_execution_compiler.py`

**Estimated scope:** Medium

## Task 21: 实现 Editor 与 Render MCP 薄映射

**Description:** 把现有编辑器 Python 服务和渲染队列映射到 MCP，不通过 shell 回调项目
自身 CLI。

**Acceptance criteria:**
- [ ] import、apply、validate、submit render 和 get render 走现有服务。
- [ ] MCP 与 Python API 保持同一 revision 和错误语义。
- [ ] 渲染使用不可变工程快照。

**Verification:**
- [ ] Python/MCP 同输入结果比较通过。
- [ ] revision 冲突和渲染失败测试通过。

**Dependencies:** Task 20

**Files likely touched:**
- `D:\project\video_create\video_create_plugin\application\editor.py`
- `D:\project\video_create\video_create_plugin\mcp\editor.py`
- `D:\project\video_create\video_create_plugin\mcp\server.py`
- `D:\project\video_create\tests\test_editor_mcp.py`

**Estimated scope:** Medium

## Task 22: 实现 RenderInspection 与 ExecutionManifest

**Description:** 从确认后的规格和 SpecTraceMap 派生检查预期，验证技术质量、规划覆盖和最终执行
绑定。

**Acceptance criteria:**
- [ ] 检查报告绑定规格、工程、RenderJob、成片和 TraceMap 哈希。
- [ ] 黑帧、时长、音频、越界和规格覆盖分别报告。
- [ ] ExecutionManifest 只接受成功渲染和通过的检查报告。

**Verification:**
- [ ] 真实 MP4、篡改成片和缺失 action 覆盖测试通过。

**Dependencies:** Task 21

**Files likely touched:**
- `D:\project\video_create\components\render_inspection\service.py`
- `D:\project\video_create\video_create_plugin\application\execution.py`
- `D:\project\video_create\schemas\execution-manifest.schema.json`
- `D:\project\video_create\tests\test_render_inspection.py`

**Estimated scope:** Medium

## Task 23: 完成 original_creation 真实闭环

**Description:** 使用真实素材和 BGM，经过三次确认、编译、渲染和检查生成原创成片。

**Acceptance criteria:**
- [ ] 三阶段边界和项目文件引用有效。
- [ ] 最终 ActionSpec、EditorProject 和 TraceMap 完整。
- [ ] 成片和 ExecutionManifest 可审计。

**Verification:**
- [ ] Codex 真实执行。
- [ ] ffprobe、指定帧和检查报告通过。

**Dependencies:** Task 22

**Files likely touched:**
- `D:\project\video_create\validation\creation\original.json`
- `D:\project\video_create\validation\creation\runner.py`
- `D:\project\video_create\tests\test_original_creation_e2e.py`
- `D:\project\video_create\docs\命令速查.md`

**Estimated scope:** Medium

## Task 24: 完成 reference_guided_creation 真实闭环

**Description:** 使用用户确认发布的参考知识和全新素材生成具有相似剪辑规律的成片，不复制参考片
具体素材与时间线。

**Acceptance criteria:**
- [ ] 三阶段分别读取对应知识投影。
- [ ] ActionSpec 不包含参考片绝对时间点。
- [ ] 最终执行可追溯到参考分析证据、知识记录和项目输入文件。

**Verification:**
- [ ] Codex 真实执行。
- [ ] 检索审计、素材隔离和成片检查通过。

**Dependencies:** Tasks 13, 23

**Files likely touched:**
- `D:\project\video_create\validation\creation\reference_guided.json`
- `D:\project\video_create\validation\creation\runner.py`
- `D:\project\video_create\tests\test_reference_guided_creation_e2e.py`

**Estimated scope:** Medium

## Task 25: 完成 Claude Code 第二宿主冒烟

**Description:** 验证第二宿主使用同一 manifests 内容根、rules、skills 和 MCP，不建立宿主
专属业务实现。

**Acceptance criteria:**
- [ ] Claude Code 按需读取 rules、skills 和项目输入文件并调用 MCP 工具。
- [ ] 两个宿主读取的内容版本一致。
- [ ] 宿主差异只存在于 manifest 适配层。

**Verification:**
- [ ] Claude Code 安装与 MCP 握手通过。
- [ ] 内容版本快照比较通过。

**Dependencies:** Tasks 23, 24

**Files likely touched:**
- `D:\project\video_create\.claude-plugin\plugin.json`
- `D:\project\video_create\tests\test_host_manifests.py`
- `D:\project\video_create\docs\安装.md`

**Estimated scope:** Small

## Checkpoint C: 三类任务形成完整闭环

- [ ] reference_study、original_creation、reference_guided_creation 真实执行通过。
- [ ] Codex 与 Claude Code 冒烟通过。
- [ ] 项目文件、知识、编译和执行结果闭合。
- [ ] 人工确认后进入 Phase 3。

## Phase 3：引擎能力逐项扩展

## Task 26: 收口现有关键帧与缓动领域合同

**Description:** 审查并收口当前工作区已有的 clip 本地时间关键帧、属性表达式和最小缓动
语义，使模型、命令、schema 与测试形成最终合同。

**Acceptance criteria:**
- [ ] 关键帧有序、在 clip 范围内且至少修改一个属性。
- [ ] `clip.update` 保持唯一写入口。
- [ ] schema_version 按确认后的策略更新。

**Verification:**
- [ ] 模型、命令、CLI 和 HTTP round-trip 测试通过。

**Dependencies:** Task 25，且 Checkpoint C 已确认

**Files likely touched:**
- `D:\project\video_create\components\video_editor\models.py`
- `D:\project\video_create\components\video_editor\commands.py`
- `D:\project\video_create\components\video_editor\expressions.py`
- `D:\project\video_create\tests\test_video_editor_keyframes.py`
- `D:\project\video_create\schemas\editor-project.schema.json`

**Estimated scope:** Medium

## Task 27: 补齐关键帧预览、FFmpeg 和 ActionSpec 闭环

**Description:** 让位置、尺寸、旋转和透明度关键帧贯通预览、导出、Registry、Preflight 和
SpecTraceMap。

**Acceptance criteria:**
- [ ] 预览与 FFmpeg 使用同一时间和插值语义。
- [ ] Registry 在真实渲染通过后登记能力。
- [ ] 每个关键帧 action_id 有 TraceMap。

**Verification:**
- [ ] 真实 FFmpeg 和指定帧比较通过。

**Dependencies:** Task 26

**Files likely touched:**
- `D:\project\video_create\components\video_editor\render.py`
- `D:\project\video_create\components\video_editor\web\preview.js`
- `D:\project\video_create\video_create_plugin\editing\capabilities.py`
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\tests\test_keyframe_execution.py`

**Estimated scope:** Medium

## Task 28: 收口现有转场与效果作用域领域合同

**Description:** 审查并收口当前工作区已有转场、滤镜、重叠校验和
clip/track/transition 效果作用域。

**Acceptance criteria:**
- [ ] 转场只绑定合法相邻片段。
- [ ] 作用域使用稳定枚举。
- [ ] 非法重叠和首片段转场被拒绝。

**Verification:**
- [ ] 模型、命令和 ActionSpec 测试通过。

**Dependencies:** Task 27

**Files likely touched:**
- `D:\project\video_create\components\video_editor\models.py`
- `D:\project\video_create\components\video_editor\commands.py`
- `D:\project\video_create\video_create_plugin\editing\models.py`
- `D:\project\video_create\tests\test_transition_contract.py`

**Estimated scope:** Medium

## Task 29: 补齐转场预览、FFmpeg 和 ActionSpec 闭环

**Description:** 实现首批明确转场的 Web 操作、FFmpeg 链、Registry 和 TraceMap。

**Acceptance criteria:**
- [ ] Web 一次手势只提交一次命令。
- [ ] 视频和音频转场时长一致。
- [ ] 视觉轨层级语义保持不变。

**Verification:**
- [ ] Web、filtergraph、真实 MP4 和指定帧测试通过。

**Dependencies:** Task 28

**Files likely touched:**
- `D:\project\video_create\components\video_editor\web\app.js`
- `D:\project\video_create\components\video_editor\web\index.html`
- `D:\project\video_create\components\video_editor\render.py`
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\tests\test_transition_execution.py`

**Estimated scope:** Medium

## Task 30: 速度变化领域合同

**Description:** 定义连续速度段、源时间映射和输出时长合同。

**Acceptance criteria:**
- [ ] 速度段无重叠和空洞。
- [ ] 输出时长可精确派生。
- [ ] 非法速度和源区间被拒绝。

**Verification:**
- [ ] 模型、命令和 Preflight 测试通过。

**Dependencies:** Task 29

**Files likely touched:**
- `D:\project\video_create\components\video_editor\models.py`
- `D:\project\video_create\components\video_editor\commands.py`
- `D:\project\video_create\video_create_plugin\editing\models.py`
- `D:\project\video_create\tests\test_speed_contract.py`

**Estimated scope:** Medium

## Task 31: 速度预览、音频和 FFmpeg 闭环

**Description:** 实现浏览器源时间映射、视频 setpts、音频 atempo 和 TraceMap。

**Acceptance criteria:**
- [ ] playhead 与源媒体时间一致。
- [ ] 视频和音频目标时长误差不超过一帧。
- [ ] Registry 只登记已验证速度范围。

**Verification:**
- [ ] 浏览器时间映射、真实 MP4 和 ffprobe 测试通过。

**Dependencies:** Task 30

**Files likely touched:**
- `D:\project\video_create\components\video_editor\web\state.js`
- `D:\project\video_create\components\video_editor\web\preview.js`
- `D:\project\video_create\components\video_editor\render.py`
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\tests\test_speed_execution.py`

**Estimated scope:** Medium

## Task 32: 遮罩与裁切动画领域合同

**Description:** 定义首批遮罩形状、裁切参数、坐标空间和关键帧引用。

**Acceptance criteria:**
- [ ] Transform 与遮罩组合顺序固定。
- [ ] 遮罩只作用于声明范围。
- [ ] 未登记形状返回 CapabilityGap。

**Verification:**
- [ ] 模型、命令和 Preflight 测试通过。

**Dependencies:** Task 31

**Files likely touched:**
- `D:\project\video_create\components\video_editor\models.py`
- `D:\project\video_create\components\video_editor\commands.py`
- `D:\project\video_create\video_create_plugin\editing\models.py`
- `D:\project\video_create\tests\test_mask_contract.py`

**Estimated scope:** Medium

## Task 33: 遮罩预览、FFmpeg 和 ActionSpec 闭环

**Description:** 实现静态及动画遮罩的浏览器与 FFmpeg 同语义执行。

**Acceptance criteria:**
- [ ] 预览和导出的形状、位置和时间范围一致。
- [ ] 透明区域和旋转组合满足容差。
- [ ] TraceMap 覆盖遮罩动作。

**Verification:**
- [ ] Web、真实 FFmpeg 和指定帧差异测试通过。

**Dependencies:** Task 32

**Files likely touched:**
- `D:\project\video_create\components\video_editor\web\preview.js`
- `D:\project\video_create\components\video_editor\web\app.js`
- `D:\project\video_create\components\video_editor\render.py`
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\tests\test_mask_execution.py`

**Estimated scope:** Medium

## Task 34: 音量包络、淡入淡出和 ducking 闭环

**Description:** 以显式音频自动化动作贯通模型、Preflight、编译、FFmpeg 和响度检查。

**Acceptance criteria:**
- [ ] 包络点有序且使用 clip 本地时间。
- [ ] ducking 明确主轨、触发轨和恢复参数。
- [ ] 静态音量项目保持原语义。

**Verification:**
- [ ] 音频自动化、真实渲染和响度区间测试通过。

**Dependencies:** Task 33

**Files likely touched:**
- `D:\project\video_create\components\video_editor\models.py`
- `D:\project\video_create\components\video_editor\render.py`
- `D:\project\video_create\video_create_plugin\editing\models.py`
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\tests\test_audio_automation.py`

**Estimated scope:** Medium

## Task 35: Composition 与跨镜头延续闭环

**Description:** 定义嵌套 Composition、本地时间、依赖图和展开规则，用显式引用表达跨镜头
延续。

**Acceptance criteria:**
- [ ] Composition 依赖图无循环。
- [ ] 展开后所有 action_id 可追溯。
- [ ] 跨镜头延续不修改用户确认的上游规格。

**Verification:**
- [ ] 循环、越界、编译和真实渲染测试通过。

**Dependencies:** Task 34

**Files likely touched:**
- `D:\project\video_create\components\video_editor\models.py`
- `D:\project\video_create\components\video_editor\render.py`
- `D:\project\video_create\video_create_plugin\editing\models.py`
- `D:\project\video_create\video_create_plugin\editing\compiler.py`
- `D:\project\video_create\tests\test_composition_execution.py`

**Estimated scope:** Medium

## Task 36: 统一预览帧与导出帧一致性框架

**Description:** 建立真实浏览器和 FFmpeg 指定帧比较工具，统一验证全部视觉能力。

**Acceptance criteria:**
- [ ] 每次比较绑定工程 revision、时间戳和成片 SHA-256。
- [ ] 输出浏览器截图、导出帧、差异图和容差结论。
- [ ] 结构测试与视觉 E2E 分别报告。

**Verification:**
- [ ] 静态 Transform、旋转、关键帧、转场、速度、遮罩和 Composition 场景通过。

**Dependencies:** Tasks 27, 29, 31, 33, 35

**Files likely touched:**
- `D:\project\video_create\validation\preview_export\runner.py`
- `D:\project\video_create\validation\preview_export\models.py`
- `D:\project\video_create\validation\preview_export\scenarios.json`
- `D:\project\video_create\tests\test_preview_export_parity.py`
- `D:\project\video_create\docs\命令速查.md`

**Estimated scope:** Medium

## Checkpoint D: 引擎能力闭合

- [ ] 每项能力完成独立纵向验证。
- [ ] Registry 与真实执行能力一致。
- [ ] 完整 pytest、Ruff、mypy、MCP、浏览器和 FFmpeg 证据通过。
- [ ] 形成可审查的发布候选。
