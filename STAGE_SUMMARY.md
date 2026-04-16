# 阶段性推进摘要

<!-- markdownlint-configure-file {"MD022": false, "MD024": false, "MD032": false, "MD060": false} -->

## 阶段性收口（2026-04-16，续）

同步说明（2026-04-16）：

- 本节取代下方同日早段条目，成为当前总续接入口；如果后续只能读一节，优先读本节。
- shared runtime、默认学习闭环、目录学底座与 `catalog_summary` 基础键空间，仍沿用下方同日条目作为实现基线；本节只补这轮新增的 Observe 辑佚候选、文献学校核工作台、artifact 抽查结论与训诂义项权威源补强。
- 当前文献学校核已经进入“可生成候选、可在控制台和项目详情页审核、可写回 repository snapshot / review artifact”的首轮闭环，但还不等于完成权威训诂库或全自动定稿链路。

### 本轮收口目标

- 让 Observe 不再只输出术语标准表和校勘条目，而是真正产出可审核的辑佚候选、疑似佚文补线索和引文来源候选。
- 把 generic philology review 从控制台 dashboard 扩到项目详情面板，并打通 writeback，让目录谱系、术语、校勘、辑佚候选和 claim 都能原地审核。
- 抽查 production-local backfill 新建的 philology artifact，确认字段和 review workbench 预期一致，并收口 `catalog_summary` 训诂义项的定义来源优先级，降低 fallback 推导占比。

### 当前已落地成果

#### 1. Observe 已真实产出辑佚候选资产

- `src/analysis/philology_service.py` 已新增 `fragment_reconstruction` 主链，按版本对勘结果生成 `fragment_candidates`、`lost_text_candidates`、`citation_source_candidates`，并输出稳定 `fragment_candidate_id`、`match_score`、`source_refs`、`reconstruction_basis`、`review_reasons`。
- `src/research/phases/observe_phase.py` 已把上述三类候选纳入 aggregate、annotation report 和 philology assets；Observe 汇总结果现在会显式记录 `fragment_candidate_count`、`lost_text_candidate_count`、`citation_source_candidate_count`。
- `src/research/observe_philology.py` 已把 fragment candidate 系列资产纳入标准 normalization / filter contract / dashboard payload 共享键空间，不再作为 document 局部附属字段悬挂在单个 Observe 文档里。

#### 2. 文献学校核工作台与 writeback 已形成首轮闭环

- 新增 `src/research/review_workbench.py`，统一定义 generic philology review decision 的 normalize / merge / upsert 逻辑，对外稳定产出 `observe_philology_review_workbench` artifact。
- `src/infrastructure/research_session_repo.py` 已新增 `upsert_observe_catalog_review()` 与 `upsert_observe_workbench_review()`，能把目录学校核和 generic philology review 分别写回 `observe_philology_catalog_review` / `observe_philology_review_workbench` artifact，并把更新后的状态重新汇总进 snapshot。
- `src/api/routes/research.py`、`src/api/dependencies.py`、`src/api/schemas.py` 已新增 `/api/research/jobs/{job_id}/catalog-review` 与 `/api/research/jobs/{job_id}/philology-review`，控制台 dashboard 可以直接写回 review 决策。
- `src/web/routes/dashboard.py`、`src/web/ops/research_session_service.py`、`src/web/ops/job_manager.py` 已把同一套 writeback 接到项目详情页和抽屉面板；项目详情页现在不仅能看 catalog baseline，也能直接审核术语、校勘、辑佚候选和 claim。
- `web_console/static/index.html` 已新增 review board UI、catalog filter 复用、原地写回和刷新逻辑；控制台 dashboard 与项目详情页现在共享同一套 Observe philology / review contract，而不是各自拼 DTO。

#### 3. production-local artifact 抽查已得出可续接结论

- 实际抽查结果证明：本轮 backfill 新建的 4 个 philology artifact，并不是单个 cycle 的“四件套”，而是两个 cycle 各自新增了 `annotation_report` + `catalog_summary`。
- 最新 production-local 样本中的 `catalog_summary.summary.exegesis_entry_count == 0`，根因不是 writeback 丢字段，而是这些 cycle 只有版本元数据，没有 terminology row，因此当前本来就不应生成训诂义项。
- 这意味着后续如果再看到“catalog_summary 存在但 exegesis_entries 为空”，要先判定输入形状是否缺术语资产，而不是直接怀疑 repository writeback 或 review workbench 消费链路。
- 上述结论已同步到 repo memory，后续继续查 backfill / artifact 对齐时应直接沿用这个判断基线。

#### 4. `catalog_summary` 训诂义项已补首轮权威源优先级

- `src/research/observe_philology.py` 现已把训诂定义来源优先级固定为：`config_terminology_standard` > `structured_tcm_knowledge` > `terminology_note` > `canonical_fallback`。
- 结构化权威源当前直接复用 `src/semantic_modeling/tcm_relationships.py` 中的 `TCMRelationshipDefinitions.HERB_EFFICACY_MAP`、`TCMRelationshipDefinitions.HERB_PROPERTIES`、`TCMRelationshipDefinitions.FORMULA_COMPOSITIONS`，不再优先依赖机器风格术语 note。
- 训诂义项现在会额外输出 `source_refs`，合并逻辑也会按来源强度保留更强定义来源；`review_reasons` 已区分 `exegesis_authority_resolved`、`exegesis_note_sourced` 与 `definition_source:canonical_fallback`，方便 workbench 继续做人工筛查。
- 这一步的目标是先降低 fallback 占比并暴露来源证据，不是一次性引入新的大型外部权威词典库；后续若继续深化，应在现有优先级链上追加更高质量词条源，而不是推翻当前 contract。

#### 5. 项目详情页回归与消费者链路已经重新压实

- `tests/unit/test_dashboard_copy.py` 已修复因详情页新增文献学校核卡片导致的旧分页断言误报，改为按 section 粒度校验术语分页与校勘分页。
- `tests/test_research_session_repo.py`、`tests/test_web_console_api.py`、`tests/test_research_utils.py` 已补 catalog review / workbench review 写回、dashboard payload 消费、项目详情页回显和 exegesis authority source 断言。
- `tests/test_research_pipeline_observe.py`、`tests/unit/test_philology_service.py` 已补 fragment candidate 生成、annotation report 计数和 catalog summary 训诂义项来源覆盖，避免 Observe 只在 UI 层“看起来支持”辑佚候选。

### 关键验证记录

- 目录详情页分页回归修复后，`tests/unit/test_dashboard_copy.py` 已通过 28 passed。
- 本轮训诂权威源补强后的 focused regression：`tests/test_research_pipeline_observe.py` + `tests/test_research_utils.py`，共 50 passed。
- 本轮 consumer-path regression：`tests/test_research_session_repo.py` + `tests/test_web_console_api.py` + `tests/unit/test_dashboard_copy.py`，共 210 passed。
- production-local 验证已完成：preflight 确认 PostgreSQL / Neo4j active；full backfill 完成 PostgreSQL / Neo4j 初始化，Neo4j 写入 208 nodes / 284 relationships，`observe_version_metadata_writeback` 扫描 13、updated 0、skipped 13，`observe_philology_artifact_writeback` 扫描 14 phases、updated 2、created 4 artifacts、skipped 12。

### 当前续接锚点

- `src/research/observe_philology.py` 现在同时承接 fragment candidate normalization、catalog summary exegesis enrich、catalog review 决策应用和 workbench decision 汇总；后续继续推进时，应继续把它当成单一共享 contract，而不是把 fragment / exegesis / review 各拆一份旁路 DTO。
- 当前 production-local 样本里“catalog_summary 有目录学元数据但没有 exegesis_entries”是输入形状结论，不是 bug；后续再查库时要先看 terminology row 是否存在。
- 目录学校核与 generic philology review 已具备首轮 writeback 闭环，下一步若继续深化，最自然的方向是完善 reviewer audit trail、批量审核与 review artifact 运维查询，而不是重新发明另一套 UI contract。
- 目前唯一明确暴露但尚未修补的外围风险，是 `.vscode/production-local-backfill.ps1` 在 preflight 中仍会打印敏感配置 / 凭据；这属于真实安全问题，不应在后续阶段摘要里被误写成“仅日志噪声”。

### 提交边界说明

- 本次提交应覆盖 Observe 辑佚候选生成、review workbench / writeback 闭环、项目详情页接线、artifact 抽查结论沉淀、训诂义项权威源优先级补强，以及对应测试与阶段摘要同步。
- `.vscode/production-local-backfill.ps1` 的敏感信息泄露问题已被记录，但本次提交不包含修补；后续若单独治理，建议作为安全修复提交独立处理。

## 阶段性收口（2026-04-16）

同步说明（2026-04-16）：

- 本节取代 2026-04-14 条目，成为当前总续接入口；如果后续只够读一节，优先读本节。
- 本轮推进已经把 2026-04-14 的 shared runtime / Observe 文献学主线，继续推进到“默认学习闭环首轮接线 + 多阶段策略消费 + 目录学底座进入 dashboard/API 查询契约”。
- 涉及 PostgreSQL / Neo4j、回填工具、结构化存储健康态的现态判读，仍统一沿用 README 的结构化存储状态词汇表：双写完成、仅 PG 模式、待回填、schema drift 待治理。
- 当前文献学语义里新增的训诂义项、时代语义和 review 状态属于“可展示、可筛选、待人工校核”的首轮落地，不应被误读为已具备权威词典级释义库。

### 本轮收口目标

- 把 reflect -> 下一轮 runtime context 的默认学习闭环真正打通，不再停留在“可以注入学习器，但默认运行不生效”的状态。
- 让 `learning_strategy` 从 pipeline config / 反思快照进入 Observe、Hypothesis、Analyze、Experiment、ExperimentExecution、Publish 的真实阈值和行为分支。
- 先把目录学这一块做成文献学公共底座，并贯通 Observe artifact、repository snapshot / backfill、dashboard JSON 和 HTML 详情面板。
- 把作品、版本谱系、见证本筛选真正接入 dashboard/API 查询参数，并与旧的文献标题筛选收敛成同一套共享契约。
- 在现有 `catalog_summary` 键空间上补训诂义项、时代语义和人工待核状态，让后续训诂、辑佚、考据不必重新发明摘要结构。

### 当前已落地成果

#### 1. 默认学习闭环已完成首轮主链接线

- `src/research/research_pipeline.py` 现在会按 `self_learning.enabled` 默认装配并初始化 `SelfLearningEngine`，并在 pipeline 启动与 reflect 后刷新学习策略快照；默认运行不再依赖调用方手工注入学习器。
- `src/learning/self_learning_engine.py` 已支持持久化 / 恢复 `tuned_parameters`，并新增 `get_learning_strategy()`、`build_previous_iteration_feedback()`、`has_learning_state()` 等接口，能把调参结果和上一轮反馈显式暴露给 runtime。
- `src/orchestration/research_runtime_service.py` 会自动把 `learning_strategy` 与 `previous_iteration_feedback` 注入每个 phase context；`src/research/phases/reflect_phase.py` 在反思完成后会刷新 pipeline 内部的学习运行时反馈。
- `src/research/learning_strategy.py` 已新增统一解析 helper，避免每个 phase 各自手工拆 `learning_strategy` / `tuned_parameters` / `previous_iteration_feedback`。

#### 2. 主研究链多阶段已开始消费真实学习策略

- Observe 现在会按学习策略调节 literature retrieval 规模、ingestion 最大文本数、实体置信度过滤、reasoning / output generation 开关，并把 `learning_strategy_applied` 和实际阈值写入 metadata。
- Hypothesis 现在会按学习策略调整候选上限、score weights、最小证据支持、最小置信度和 validated / active 阈值，也支持按策略关闭 LLM 生成。
- Analyze 现在会按学习策略调整显著性阈值、最小样本量、低置信度关系过滤，以及 reasoning / evidence grading 开关。
- Experiment 现在会按学习策略调节 protocol LLM 开关、sample size、duration、methodology；ExperimentExecution 会按学习策略控制 document fallback import、relationship confidence 过滤和 records / relationships / sampling_events 限流。
- Publish 现在会按学习策略控制 paper / report / structured output / evidence grade 开关，以及 citation fallback 和本地 citation 记录上限。

#### 3. 目录学基线已接入 Observe 文献学主线

- `src/research/observe_philology.py` 已新增 `observe_philology_catalog_summary` artifact，并把 `catalog_summary` 统一定义为 `summary + documents + version_lineages` 三段结构。
- Observe 文献学资产现在不仅输出术语标准表、校勘条目和 annotation report，也会从文档 `version_metadata` 中提取 `catalog_id`、`work_title`、`fragment_title`、`work_fragment_key`、`version_lineage_key`、`witness_key`、`dynasty`、`author`、`edition` 等目录学字段，形成可复用的目录学事实层。
- `src/research/observe_philology.py` 已支持从 artifacts、aggregate、observe documents 三个来源归并目录学数据，并在 normalization 过程中统一 enrich terminology / collation / document report 的目录学元数据。
- `tests/test_research_pipeline_observe.py` 与 `tests/test_research_session_repo.py` 已补 catalog_summary artifact、snapshot 回填与 repo writeback 覆盖，确保目录学基线不是只存在于单点 DTO。

#### 4. Dashboard / API 现已共享目录学过滤契约

- `src/api/routes/research.py` 的 `/api/research/jobs/{job_id}/dashboard` 现在接受 `document_title`、`work_title`、`version_lineage_key`、`witness_key` 四个查询参数；本轮改动前存在用户或格式化器更新，当前文件已按现态重新核对，无需回退。
- `src/api/research_utils.py` 现在在 dashboard payload 中同时输出 `active_catalog_filters` 与 `catalog_filter_options`，并在 payload 构建时通过共享 helper 过滤 Observe 文献学资产。
- `src/web/routes/dashboard.py` 已把详情面板、分页和 HTMX URL 统一到相同的 catalog filter contract；HTML 详情页不再只支持 `document_title`，而是支持作品、版本谱系、见证本、文献标题四类同步筛选。
- 这意味着 JSON dashboard 与 HTML detail panel 现在共享一份过滤语义，后续不能再把筛选逻辑写回路由局部 helper。

#### 5. `catalog_summary` 已补首轮训诂 / 时代语义 / review 元数据

- `src/research/observe_philology.py` 现已在 `catalog_summary` 下补入 `temporal_semantics`、`exegesis_entries`、`review_status`、`needs_manual_review`、`review_reasons` 等字段，并按 document / lineage / witness 三层归并。
- summary 层现已补齐 `exegesis_entry_count`、`temporal_semantic_count`、`dynasty_counts`、`review_status_counts`、`pending_review_count`、`needs_manual_review_count` 等指标，方便 dashboard 与 API 直接消费。
- 当前训诂义项与时代语义仍以术语标准表、dynasty / author / edition 元数据和校勘上下文的 fallback 推导为主；因此默认 review 状态偏向 `pending` / `needs_manual_review`，避免把机器归纳结果直接包装成确定事实。
- `src/web/routes/dashboard.py` 已增加目录学基线卡片、review badge、时代语义提示和训诂义项预览，dashboard 现在能把 catalog_summary 当作可读主视图，而不是埋在 artifact JSON 内部。

#### 6. 审计文档与部署示例口径已同步到当前现态

- `ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md` 已同步更新默认学习闭环、主研究链策略消费和文献学推进现态，不再把 reflect 继续描述成“默认未学习”，也不再把文献学简单描述成“尚无入口”。
- `deploy/k8s/tcmautoresearch-deployment.example.yaml` 与 `deploy/k8s/tcmautoresearch-migrate-job.example.yaml` 已补结构化存储状态口径注释，明确 readiness / Job 成功不自动等同于“双写完成”。
- 这些文档同步的作用不是重复架构设计，而是防止部署验收和架构审计继续使用旧口径误判当前状态。

### 关键验证记录

- 2026-04-16 已定向复跑默认学习闭环与阶段级策略消费相关测试：`tests/unit/test_default_self_learning_loop.py`、`tests/unit/test_research_runtime_service.py`、`tests/test_hypothesis_engine.py`、`tests/unit/test_analyze_phase.py`、`tests/test_research_pipeline_experiment.py`、`tests/unit/test_experiment_execution_phase.py`、`tests/unit/test_publish_phase.py`，共 172 passed。
- 2026-04-16 已定向复跑目录学基线、repo snapshot / backfill、dashboard payload 与 HTML / API 筛选相关测试：`tests/test_research_pipeline_observe.py`、`tests/test_research_session_repo.py`、`tests/test_research_utils.py`、`tests/unit/test_dashboard_copy.py`、`tests/test_web_console_api.py`，共 240 passed。
- 默认学习闭环与 runtime 注入相关回归已补到 `tests/unit/test_default_self_learning_loop.py` 与 `tests/unit/test_research_runtime_service.py`。
- 多阶段策略消费相关覆盖已补到 `tests/test_hypothesis_engine.py`、`tests/unit/test_analyze_phase.py`、`tests/test_research_pipeline_experiment.py`、`tests/unit/test_experiment_execution_phase.py`、`tests/unit/test_publish_phase.py`。
- 目录学基线、repo snapshot / backfill、dashboard payload 和 HTML / API 筛选覆盖已补到 `tests/test_research_pipeline_observe.py`、`tests/test_research_session_repo.py`、`tests/test_research_utils.py`、`tests/unit/test_dashboard_copy.py`、`tests/test_web_console_api.py`。
- 若未来从任意日期继续接手，优先复跑这批测试，而不是只看 UI 表面效果。

### 当前续接锚点

- 默认学习闭环这条线，当前瓶颈已经从“是否默认启用”转为“策略可观测性、跨阶段一致性、反馈资产治理是否继续收口”。
- 文献学这条线，`src/research/observe_philology.py` 现已成为目录学摘要、筛选契约、语义 enrich 和 review 元数据的共享入口；后续不要再在 route 层各自拼一份过滤逻辑。
- `catalog_summary` 当前已经可以承载目录学、训诂义项、时代语义和 review 状态，但 review 仍是只读展示语义；下一步最自然的落点，是把 review decision 写回 repository snapshot 或显式 review artifact。
- 训诂义项与时代语义当前仍是 fallback / machine-derived 结果，后续若继续深化，应优先补权威词条源与人工审核 writeback，而不是直接提高展示复杂度。

### 任意日期继续接手建议

1. 先读本节，再回看 2026-04-14 条目和 README 的结构化存储状态词汇表，先把当前 runtime / learning / philology 的三条主线口径锁住。
2. 如果要接默认学习闭环，优先从 `src/research/research_pipeline.py`、`src/learning/self_learning_engine.py`、`src/orchestration/research_runtime_service.py`、`src/research/learning_strategy.py` 建立上下文。
3. 如果要接文献学和目录学，优先从 `src/research/observe_philology.py`、`src/research/phases/observe_phase.py`、`src/api/research_utils.py`、`src/web/routes/dashboard.py` 建立上下文。
4. 如果要继续 dashboard/API 这条线，优先守住“共享 filter contract + catalog_summary 单一键空间”两条约束，不要再把筛选和摘要拆成两份并行 DTO。
5. 如果要继续做 review workflow，建议先把最小 writeback 路径补到 repository snapshot / review artifact，再谈更复杂的工作台交互。

### 提交边界说明

- 本次提交应覆盖默认学习闭环首轮接线、主研究链阶段级策略消费、目录学基线 artifact / snapshot / dashboard / API 连通、catalog_summary 语义 enrich / review 元数据、以及对应架构审计与部署注释同步。
- 这批改动已经超出“局部修补”范围，应视为一组完整阶段推进结果统一提交，而不是拆成零散 feature fix。

## 阶段性收口（2026-04-14）

同步说明（2026-04-14）：

- 本节是当前总续接入口；如需从任意一天继续接手，优先读本节，再回看更早日期条目。
- 涉及 PostgreSQL / Neo4j、回填工具、监控摘要与 drift 治理的现态判读，统一沿用 README 的结构化存储状态词汇表：双写完成、仅 PG 模式、待回填、schema drift 待治理。
- 下文提到的历史设计、历史治理或历史 checkpoint，只代表对应日期的观察基线；当前实现真相以最新源码、测试、架构审计和本节为准。

### 本轮收口目标

- 把 shared runtime / entrypoint / Web session contract 继续收口，避免 API、Web、Web Console 与 demo/cycle 再各自维护一套局部入口语义。
- 把 Observe 文献学能力从 collect、pipeline、structured persist、graph、dashboard 到文档口径全部打通，而不是只停留在某一层的局部 DTO。
- 把结构化存储当前状态统一压成一套稳定词汇，并同步到 README、审计、部署、Helm、阶段摘要与历史架构文档，防止运维和架构文档继续分叉。
- 形成一份可直接提交、可从任意日期续接的阶段摘要，让后续接手者不用再从更旧的六阶段或“已连接即已双写完成”旧口径重新判题。

### 当前已落地成果

#### 1. shared runtime 与入口装配继续收口

- `src/infrastructure/runtime_config_assembler.py` 已显式固化 entrypoint -> runtime_profile 映射：`web` 对应 `web_research`，`demo` 对应 `demo_research`；未知 entrypoint 不再隐式注入 profile。
- `src/api/app.py`、`src/web/app.py`、`web_console/app.py` 现在都会把 `runtime_assembly` 挂到 `app.state`，并统一走 assembly 产出的 orchestrator config，而不是在各入口重复拼接本地默认值。
- `src/cycle/cycle_runtime_config.py` 新增 `build_cycle_runtime_assembly()` 与 `build_cycle_orchestrator_config()`；`src/cycle/cycle_research_handler.py`、`src/cycle/cycle_research_session.py` 现已改成 shared runtime 的薄包装，不再本地声明 demo 入口默认阶段、cycle_name、scope 或 JSON 导出逻辑。
- `src/orchestration/research_runtime_service.py` 已进一步内建 shared runtime profile 默认值、publish report policy 合并逻辑与 `session_result` 契约输出；`run_cycle_demo`、Web 异步 job 和 REST 入口都复用同一条主链。

#### 2. Legacy Web 兼容壳已经删掉，session contract 改走 repository-backed 主线

- `src/web/ops/legacy_research_runtime.py` 已删除；不再通过内存态 legacy store 对 Web 路由做兼容包装。
- 新增 `src/web/ops/research_job_runner.py`、`src/web/ops/research_session_contract.py`、`src/web/ops/research_session_service.py`，分别承接 shared runtime 执行、Web-facing session contract 归一和 repository-backed session 读写。
- `src/web/routes/research.py`、`src/web/routes/analysis.py`、`src/web/routes/dashboard.py` 已改为直接消费新的 session service / contract，不再回落到 legacy runtime store。
- 兼容契约测试也已迁移：`tests/unit/test_legacy_research_runtime.py` 已删除，对应覆盖改由 `tests/unit/test_research_route_contract.py` 与 `tests/unit/test_research_session_service.py` 承接。

#### 3. Observe 文献学主链已经打通到 collect -> pipeline -> persist -> graph -> UI

- 新增 `src/analysis/philology_service.py`，并在 `config.yml`、`src/core/ports.py`、`src/core/adapters.py`、`src/research/research_pipeline.py` 中接入 `philology_service`，使 Observe 子流程可以在预处理前后输出术语标准化、异写识别、版本对勘与文献学资产。
- `src/research/phases/observe_phase.py` 现已支持文献学处理、版本 witness 选择、术语标准表聚合、校勘条目聚合与 annotation report 产出；`src/research/observe_philology.py` 负责统一 observe 文献学资产的归并、artifact DTO 与多来源解析。
- `src/collector/corpus_bundle.py`、`src/collector/ctext_corpus_collector.py`、`src/collector/ctext_whitelist.py`、`src/collector/local_collector.py`、`src/collector/multi_source_corpus.py` 已补齐显式 `version_metadata` 生成逻辑，包括 `work_title`、`fragment_title`、`catalog_id`、`work_fragment_key`、`version_lineage_key`、`witness_key` 等字段。
- `src/orchestration/research_orchestrator.py`、`src/orchestration/research_runtime_service.py`、`src/api/schemas.py`、`src/api/research_utils.py`、`web_console/static/index.html` 都已把 `observe_philology` 纳入标准结果、dashboard payload 和 Web Console 观察面板。

#### 4. Observe 文献学资产已经落到结构化存储与图回填层

- `src/infrastructure/persistence.py` 的 `Document` 表已新增文献版本谱系相关列：`document_urn`、`document_title`、`source_type`、`catalog_id`、`work_title`、`fragment_title`、`work_fragment_key`、`version_lineage_key`、`witness_key`、`dynasty`、`author`、`edition`、`version_metadata_json`；对应迁移已新增到 `alembic/versions/e4c6d2b7a9f1_add_document_version_lineage_fields.py`。
- `src/infrastructure/research_session_repo.py` 现在不仅能持久化 observe 文档图，还能回填 legacy 行的 `version_metadata`、列出 `observe version lineages`、补写 observe 文献学 artifact，并把 `observe_philology` 聚合回完整 snapshot。
- `src/research/research_session_graph_backfill.py` 与 `src/research/phase_orchestrator.py` 已扩展 Neo4j 图投影：Observe 文档除实体图外，还会生成 `VersionLineage` / `VersionWitness` 节点和 `OBSERVED_WITNESS` / `BELONGS_TO_LINEAGE` 边。
- `tools/backfill_research_session_nodes.py` 已增加 PG writeback 开关，可在 Neo4j 图回填前选择是否先回补 observe 版本元数据与文献学 artifact；这些工具当前应明确理解为“待回填”治理链，而不是默认主写路径的一部分。

#### 5. Dashboard / 项目页已经可以展开查看文献学明细

- `src/web/routes/dashboard.py` 已支持项目详情面板、侧边抽屉、分页查看术语标准表、分页查看校勘条目、按文献标题筛选，以及 base / witness 上下文跳转到原始文档片段预览。
- `src/web/templates/dashboard.html` 已增加 session detail drawer 与 fragment preview modal，并补齐对应前端交互函数。
- `tests/unit/test_dashboard_copy.py` 已补针对结构化 session detail、分页、筛选、fragment preview 和模板挂载点的覆盖，确保 dashboard 扩展不是只在模板里“看起来存在”。

#### 6. 文档治理与结构化存储状态口径统一完成一轮 sweep

- `ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md` 的 P1 存储事务边界问题已按当前事实重写：主路径已存在事务协调，真实剩余问题集中在仅 PG 模式、待回填、schema drift 待治理与观测治理，而不是“主链仍未接线”。
- `README.md` 已新增“结构化存储状态词汇表”，把“双写完成 / 仅 PG 模式 / 待回填 / schema drift 待治理”固定为仓库统一术语。
- `STORAGE_ARCHITECTURE.md`、`STORAGE_DELIVERY.md`、`STORAGE_PLAN_SUMMARY.md`、`STORAGE_FINAL_REPORT.md`、`STORAGE_TEST_SUMMARY.md`、`STORAGE_PERFORMANCE_REPORT.md`、`STORAGE_QUERIES.md`、`STORAGE_INTEGRATION.md`、`STORAGE_DEPLOYMENT.md`、`DOCKER_DEPLOYMENT.md` 均已同步到同一状态口径。
- 更早文档也已补同步说明：`ARCHITECTURE_AUDIT_2026_04_06.md`、`ARCHITECTURE_REDESIGN_2026_04_08.md`、`docs/architecture/architecture-design.md`、`deploy/helm/tcmautoresearch/README.md`、以及本文件 `STAGE_SUMMARY.md` 都已注明历史基线与当前现态的边界。
- `STAGE_SUMMARY.md` 当前继续采用文件级 `markdownlint-configure-file` 局部关闭重复标题结构规则，这是对“按日期聚合 checkpoint”文档更合适的治理方式，不再尝试为消除告警而重写历史结构。

#### 7. 默认学习闭环已完成首轮接线

- `src/research/research_pipeline.py` 现在会按 `self_learning.enabled` 默认装配并初始化 `SelfLearningEngine`，不再要求调用方手工注入 `self_learning_engine` 才能让 reflect 把质量评估喂给学习模块。
- `src/learning/self_learning_engine.py` 已开始持久化 / 恢复 `tuned_parameters`，`src/orchestration/research_runtime_service.py` 会把 `learning_strategy` 与 `previous_iteration_feedback` 自动回写到下一轮 phase context，默认学习闭环已经从“只总结”推进到“默认下一轮可带策略”。
- 对应回归覆盖已补到 `tests/unit/test_default_self_learning_loop.py` 与 `tests/unit/test_research_runtime_service.py`；后续若继续推进，这条线的重点不再是“是否默认启用”，而是各阶段对 `learning_strategy` 的细粒度消费深度。
- 截至本阶段，`src/research/phases/observe_phase.py`、`src/research/hypothesis_engine.py`、`src/research/phases/analyze_phase.py`、`src/research/phases/experiment_phase.py`、`src/research/phases/experiment_execution_phase.py`、`src/research/phases/publish_phase.py` 已开始消费 `learning_strategy` 的真实阈值与行为分支：Observe 会调整 ingestion / literature 规模并按 `confidence_threshold` 过滤实体关系，Hypothesis 会收紧候选数量与证据/置信度门槛，Analyze 会动态解析显著性阈值、最小样本量，并支持推理 / 证据分级分支控制，Experiment 会调节 protocol 的 sample_size / duration / methodology / LLM 开关，ExperimentExecution 会控制 document fallback import、关系置信度过滤以及 execution records / relationships / sampling_events 的导入规模，Publish 会控制 citation fallback、本地 citation 规模以及 paper / report / evidence-grade 分支。

### 关键验证记录

- shared runtime / runtime profile / cycle 入口相关测试已补到 `tests/test_config_loader.py`、`tests/unit/test_cycle_command_executor.py`、`tests/unit/test_cycle_research_handler.py`、`tests/unit/test_cycle_demo_contract.py`、`tests/unit/test_research_runtime_service.py`。
- Observe 文献学与版本谱系相关测试已补到 `tests/unit/test_philology_service.py`、`tests/test_research_pipeline_observe.py`、`tests/test_corpus_bundle.py`、`tests/test_ctext_corpus_collector.py`、`tests/test_ctext_whitelist.py`、`tests/test_multi_source_corpus.py`。
- structured persist / graph / repo writeback 相关覆盖已补到 `tests/test_research_pipeline_persist.py`、`tests/test_research_session_graph_backfill.py`、`tests/test_research_session_repo.py`。
- Web contract 与 dashboard 扩展覆盖已补到 `tests/unit/test_research_route_contract.py`、`tests/unit/test_research_session_service.py`、`tests/unit/test_dashboard_copy.py`、`tests/test_research_utils.py`、`tests/test_rest_api.py`、`tests/test_web_console_api.py`。
- 文档面最近一次诊断已确认 `STAGE_SUMMARY.md`、`docs/architecture/architecture-design.md`、`deploy/helm/tcmautoresearch/README.md` 返回 `No errors found`；`STORAGE_DEPLOYMENT.md` 的主要内容与风格问题已收口到只剩末尾样式尾项。

### 当前续接锚点

- 入口治理这条线当前已经不该回到“每个 wrapper 单独拼默认 runtime_profile / phase / cycle_name”的旧模式；后续若继续收口，应优先扫剩余 direct pipeline shortcut 或旁路 orchestrator 的地方。
- Observe 文献学主链已经不是单纯的局部实验能力，而是 collect、observe、session DTO、structured persist、Neo4j、dashboard、Web Console 和回填工具共同消费的主链资产；后续新增字段必须按这条全链思维推进。
- 结构化存储主路径已存在，后续重点不是再证明“有没有接线”，而是继续治理仅 PG 模式、待回填与 schema drift 待治理，并把观测/验收口径持续压到 README 词汇表上。
- 文档治理方面，新的风险不在“缺少一份审计报告”，而在于历史文档继续用 present tense 描述旧事实；后续再改文档时，优先追加同步说明而不是把历史观察硬改成当前事实。

### 任意日期继续接手建议

1. 先读本节“阶段性收口（2026-04-14）”，再读 `README.md` 的结构化存储状态词汇表，先把 runtime / storage / observe_philology 的当前口径锁住。
2. 如果要接代码主链，优先从 `src/infrastructure/runtime_config_assembler.py`、`src/orchestration/research_runtime_service.py`、`src/research/phases/observe_phase.py`、`src/infrastructure/research_session_repo.py` 四个点建立上下文。
3. 如果要接 Web 与运维面，优先看 `src/web/ops/research_session_service.py`、`src/web/routes/dashboard.py`、`src/web/templates/dashboard.html`、`deploy/helm/tcmautoresearch/README.md`。
4. 如果要继续做结构化存储治理，先区分当前目标属于“双写完成”“仅 PG 模式”“待回填”还是“schema drift 待治理”，不要再用“已连接”“已 ready”“hook 成功”代替运行态结论。
5. 如果要继续扫文档，优先检查剩余历史架构文档、部署示例注释和 `STORAGE_DEPLOYMENT.md` 末尾样式尾项，而不是重开新的口径体系。

### 提交边界说明

- 本次提交应覆盖 shared runtime / entrypoint 收口、Legacy Web 兼容层删除、Observe 文献学主链接入、版本谱系结构化持久化与图回填、dashboard 文献学详情扩展、以及结构化存储状态词汇表同步与历史文档收口。
- Alembic 迁移、repo/writeback/backfill 工具、Web contract 迁移、dashboard 扩展、README/审计/部署文档同步和相关测试均属于正式交付面，不再视作临时脚手架或实验补丁。

## 阶段性收口（2026-04-13）

同步说明（2026-04-14）：

- 涉及 PostgreSQL / Neo4j、监控摘要、schema drift 与回填工具链的现态判读，统一沿用 README 的结构化存储状态词汇表：双写完成、仅 PG 模式、待回填、schema drift 待治理。
- 下文提到的 backfill / writeback 工具，应理解为“待回填”治理资产，而不是默认依赖的隐式主路径。

### 本轮收口目标

- 把 CLI、独立 API、Legacy Web、Web Console 与 cycle/demo 入口统一到同一套 runtime assembler 与 shared runtime service。
- 把七阶段科研主链中的 experiment / experiment_execution 语义边界真正落到 orchestrator、pipeline、持久化、报告、Web 展示与测试基线。
- 让 PostgreSQL / Neo4j 结构化持久化成为研究会话主链默认路径，并补齐 observe 文档图谱、回填工具、迁移与部署支撑。
- 把这轮代码与文档推进结果压成可续接 checkpoint，避免后续再从六阶段旧口径或 legacy 入口重新判题。

### 当前已落地成果

#### 1. 统一运行时与入口装配已经成形

- 新增 src/infrastructure/runtime_config_assembler.py，统一产出 settings、runtime_config 与 orchestrator_config。
- 新增 src/orchestration/research_runtime_service.py，作为 CLI、Web、Legacy Web 共享的研究运行时控制面，统一 cycle 生命周期、phase emit 与 orchestration 汇总。
- 新增 src/cycle/cycle_runtime_config.py、src/api/main.py，并让 src/web/main.py、web_console/main.py、run_cycle_demo.py 相关分支都支持 config/environment 显式注入。
- src/web/app.py、web_console/app.py、src/web/ops/job_manager.py 已改为复用 runtime assembly，而不是各自拼接一套局部配置。
- 截至 2026-04-13，Legacy Web 已不再直接绑定 in-memory ResearchPipeline 单例；当时仍由 src/web/ops/legacy_research_runtime.py 提供兼容 store，dashboard / analysis / research 路由改走统一 runtime + session store。该文件已在 2026-04-14 删除，现由 src/web/ops/research_session_service.py 直接承接 repository-backed 读写。

#### 2. 七阶段主链与实验语义拆分已经落到实现面

- src/research/study_session_manager.py、src/orchestration/research_orchestrator.py、src/research/pipeline_orchestrator.py、src/research/phase_orchestrator.py 已把默认研究链扩为 observe → hypothesis → experiment → experiment_execution → analyze → publish → reflect。
- src/research/phases/experiment_phase.py 已明确 experiment=实验方案阶段，只负责 protocol design，并显式输出 not_executed / not_started 边界元数据。
- 新增 src/research/phases/experiment_execution_phase.py 与 src/research/phase_handlers/experiment_execution_handler.py，承接外部实验执行、采样与结果导入；无输入时为 skipped，有输入时为 completed。
- src/research/phases/analyze_phase.py、src/research/phases/publish_phase.py、src/research/real_observe_smoke.py 已能消费 experiment_execution 的导入记录、关系和状态，而不是继续把 experiment 混写成真实实验执行。
- Web 与展示口径也已同步：web_console/static/index.html、src/web/routes/dashboard.py、src/api/research_utils.py 等位置统一把 experiment 显示为“实验方案阶段”，experiment_execution 显示为“实验执行阶段”。

#### 3. PostgreSQL / Neo4j 结构化持久化主链已经接上

- src/research/phase_orchestrator.py 已新增 structured persistence 主路径：ResearchSession / PhaseExecution / Artifact 写入 PostgreSQL，Neo4j 图投影与 legacy sqlite fallback 清晰分层。
- src/infrastructure/research_session_repo.py 现已支持外部事务 session 复用，并新增 observe 文档、实体、关系的结构化落库与快照回读。
- 新增 src/research/research_session_graph_backfill.py、tools/backfill_research_session_nodes.py、tools/backfill_research_graph_nodes.py，补齐历史研究会话到 Neo4j 的节点/边回填工具；这些工具当前应按“待回填”治理资产理解，而不是默认主写路径的一部分。
- src/storage/transaction.py、src/storage/neo4j_driver.py 已继续收口查询与写入规范：split MATCH、scoped CALL、可选关系读取去噪，避免把旧的 Neo4j 通知模式重新带回主链。
- src/infrastructure/monitoring.py 与相关测试已把 schema drift / structured storage 暴露到健康检查与监控摘要中；运维判读应统一落到双写完成、仅 PG 模式、待回填、schema drift 待治理这四类状态上。

#### 4. 配置、迁移、部署与密钥解析已经补齐配套

- 新增 src/infrastructure/alembic_runtime.py，统一 Alembic 从 environment / config / explicit url 解析目标数据库，不再依赖手工改 alembic.ini。
- 新增两条 Alembic 迁移：7fbe6f4d7a2c_migrate_legacy_postgres_enum_columns_to_varchar_contract.py 与 d6c8f52a1b2e_migrate_postgres_string_list_columns_to_varchar_array_contract.py，用于收敛 PostgreSQL 历史 enum / string-list 契约漂移。
- 新增 src/infrastructure/secret_resolution.py，并让 src/storage/backend_factory.py、src/storage/neo4j_driver.py 优先采用显式 password，再回退 password_env，减少配置与环境变量打架。
- Docker / Helm / K8s 部署面已同步：deploy/helm/tcmautoresearch/templates/migration-job.yaml、deploy/k8s/tcmautoresearch-migrate-job.example.yaml、Dockerfile、docker-compose.yml、DOCKER_DEPLOYMENT.md、deploy/helm/tcmautoresearch/README.md 等均已纳入统一启动与迁移口径。

#### 5. 文档真相同步与历史文档收口已经完成一轮

- 新增 ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md，作为当前阶段最接近“运行时真相”的架构审计基线。
- README.md、docs/architecture/architecture-design.md、docs/module_contracts.md、docs/real_observe_smoke.md 与根目录历史 ARCHITECTURE / STAGE / PHASE_RESULT 文档已统一到七阶段当前边界。
- 历史报告中的 Mermaid 图、ASCII 架构块与清单块已补“历史基线”说明，避免读者把旧设计图直接当成当前主链实现。
- STORAGE_ARCHITECTURE.md、STORAGE_DELIVERY.md、STORAGE_PLAN_SUMMARY.md、STORAGE_FINAL_REPORT.md、STORAGE_TEST_SUMMARY.md 已完成 markdownlint 风格收口，并在最终 sweep 中清掉 MD047 / MD034 尾项。

### 关键验证记录

- 当时定向回归已通过：tests/unit/test_research_runtime_service.py、tests/unit/test_legacy_research_runtime.py、tests/test_research_pipeline_experiment.py、tests/test_research_pipeline_persist.py、tests/test_config_loader.py、tests/test_alembic_runtime.py、tests/test_research_session_graph_backfill.py、tests/unit/test_backend_factory.py、tests/test_research_session_repo.py、tests/unit/test_neo4j_driver.py，共 264 passed。后续这组 legacy Web 兼容覆盖已迁到 tests/unit/test_research_route_contract.py 与 tests/unit/test_research_session_service.py。
- 真实持久化回归：integration_tests/test_experiment_execution_persistence_e2e.py 已在开发 PostgreSQL + Neo4j 上通过，结果为 2 passed in 22.36s。
- 真实语义锁定：该回归已明确断言 experiment_execution 无输入时持久化为 skipped，有输入时持久化为 completed。
- 文档最终收口：上述 5 份 STORAGE 历史文档最后一轮 diagnostics 已全部返回 No errors found。

### 当前续接锚点

- 运行时统一这条线当前已不该再回到“每个入口各装配一遍配置”的旧模式；后续若继续收口，应优先找剩余 direct pipeline shortcut 与 legacy 壳。
- experiment / experiment_execution 的语义边界已经在代码、测试、文档、Web 文案和持久化层同时落地；后续不要再把 experiment 写回“真实实验执行”。
- 结构化持久化已经接入主研究链，下一阶段重点不是“是否接线”，而是事务边界、仅 PG 模式 / 待回填 / schema drift 待治理与可观测性继续收敛。
- 文档治理已完成一轮大收口；若后续继续扫尾，优先检查历史根文档是否还有六阶段旧表述、历史图示未标注，或 markdownlint 残留的 MD047 / MD034。

### 任意日期继续接手建议

1. 先读本节“阶段性收口（2026-04-13）”，再读 ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md，不要再从更老的六阶段审计结论重新判断当前主链。
2. 再看 README.md 与 docs/architecture/architecture-design.md，确认用户可见口径仍保持 experiment=实验方案阶段、experiment_execution=实验执行阶段。
3. 代码续接时优先从 src/orchestration/research_runtime_service.py、src/infrastructure/runtime_config_assembler.py、src/research/phase_orchestrator.py、src/infrastructure/research_session_repo.py 四个点建立上下文。
4. 如需验证主链真相，先跑 integration_tests/test_experiment_execution_persistence_e2e.py；如只做文档收口，先查历史文档里的旧图示/旧术语和 markdownlint 尾项。
5. 后续真正的 P0 不再是阶段命名，而是文献学能力、默认 learning loop、事务边界/fallback 继续治理，以及剩余 legacy 入口的收敛。

### 提交边界说明

- 本次 checkpoint 应覆盖当前工作树中的运行时统一、七阶段实验语义拆分、结构化持久化与图回填、Alembic/部署支撑、以及架构/历史文档同步收口。
- 新增审计文档、集成回归、迁移脚本、部署模板和历史文档清理均属于正式交付面，不再视作临时产物。

## 阶段性收口（2026-04-12）

### 本轮收口目标
- 完成 PhaseResult 统一契约从 producer 到 secondary consumer 的一轮收口，并清掉 publish 根级旧镜像字段。
- 删除已不在生产路径中的 legacy cycle 迭代子系统，缩小 `src/cycle/` 到当前运行时入口。
- 修复 quality consumer inventory 与真实 smoke/质量门联动，让全仓在当前契约下重新回到绿色基线。
- 为后续断点续接补齐阶段摘要、只读盘点结论和诊断工具入口。

### 当前已落地成果

#### 1. PhaseResult 主契约已经成为研究主链基线
- 新增 `src/research/phase_result.py`，统一提供 `PhaseResult` dataclass、`build_phase_result()`、`normalize_phase_result()`、`get_phase_value()`、`get_phase_results()`、`get_phase_artifact_map()`。
- 六个研究阶段的返回值已统一到 `phase/status/results/artifacts/metadata/error`，并由 `src/research/pipeline_orchestrator.py` 在 event 路径、handler 路径和失败路径统一做 `normalize_phase_result()` 兜底。
- `src/quality/quality_assessor.py` 已接受 `degraded`、`blocked` 为合法状态；`analyze` 记录为空时会显式落成 degraded，而不是只在 metadata 中隐含表达。

#### 2. publish 根级旧镜像字段删除序列已经收完
- `PHASE_RESULT_LEGACY_FIELD_REMOVAL_2026_04_08.md` 已记录完整删除轨迹；publish 根级的 `paper_draft`、`imrd_reports`、`paper_language`、`report_output_files`、`report_session_result`、`report_generation_errors`、`analysis_results`、`research_artifact` 等旧镜像已全部从根结果移除。
- publish 对外标准承载位已收敛到 `results.*` 与 `artifacts`；`report_session_result` 内部命名也收敛为 `report_session_payload`，明确其只属于 ReportGenerator 输入，而不是对外 DTO。
- 根 `phase_results` 的 `metadata.deprecated_field_fallbacks` 已清零，不再依赖旧顶层兼容回退。

#### 3. secondary consumer 迁移已覆盖主要生成/摘要层
- `src/api/research_utils.py` 已优先从 `phase_results.publish` 的标准 `analysis_results/research_artifact/artifacts` 读取 dashboard 高亮与报告产物。
- `src/generation/paper_writer.py` 已改为 helper-based 解析 `output_data`、`research_artifact`、`quality_metrics`、`recommendations`、`llm_analysis_context`、图谱证据等，不再靠散落的 `context.get()`。
- `src/generation/report_generator.py` 已改为 results-first 路径，Methods/Results/Discussion 中对 `study_protocol`、`analysis_results`、`comparison_with_literature`、`limitations`、`future directions` 的读取都已收敛。
- `src/generation/llm_context_adapter.py` 已迁到 PhaseResult-aware 读取：当前 payload、`session_result.phase_results.publish/analyze`、`output_data`、`analysis_results`、`research_artifact` 都会走 helper 解析，同时保留对 wrapped generator 所需的顶层 `analysis_results/analysis_modules` 兼容输出。
- 只读扫尾已经确认：生成层里没有新的真实 PhaseResult consumer 债务；`src/generation/output_formatter.py` 当前仍保留少量顶层读取，但这是 publish 通用生成上下文契约，不计入本轮统一契约阻塞项。

#### 4. legacy cycle 子系统已经移出当前基线
- 已删除 `src/cycle/fixing_stage.py`、`src/cycle/iteration_cycle.py`、`src/cycle/module_iteration.py`、`src/cycle/system_iteration.py`、`src/cycle/test_driven_iteration.py`。
- `src/cycle/__init__.py` 现在只保留当前运行时入口：`build_cycle_demo_arg_parser`、`execute_cycle_demo_command`、`execute_real_module_pipeline`、`run_full_cycle_demo`、`run_research_session`。
- 相关过时测试与文档引用已同步清理，`tests/unit/test_architecture_cycle_quality.py` 已改为验证当前 cycle 包导出与 core/architecture 契约，而不是继续锚定旧 iteration 子系统。

#### 5. 质量门、inventory 和真实诊断基线已重新稳定
- `run_cycle_demo.py` 已补显式 export contract 描述，满足 `quality_consumer_inventory` 对 root script 的契约识别。
- `tools/quality_consumer_inventory.py` 已把 sqlite/DB 快速检查脚本归类为 `non_governance_domain_script`，不再作为未分类脚本打红质量门。
- `src/research/real_observe_smoke.py` 与 `tools/diagnostics/real_observe_smoke_profile.json` 已对齐新契约，不再把 publish 旧 alias 字段当作强制要求。
- `src/knowledge/embedding_service.py` 已对“查询文本与已索引条目完全相同”的情况复用缓存向量，避免离线 smoke/词典对比时重新触发 SentenceTransformer 初始化与 Hugging Face 重试。

#### 6. 词典与真实运行诊断工具已补齐
- 新增 `tools/diagnostics/rebuild_tcm_lexicon.py`，支持默认构建、`--audit-dir` 逐类别审计和可选 `--include-micang-clinical-terms`。
- 新增 `tools/diagnostics/compare_real_cycle_lexicon_modes.py` 与 `tools/diagnostics/real_observe_available_workspace_profile.json`，可以在同一可用语料上对比“无词典/重建词典”两条真实运行链。
- 当前词典审计基线已记录在 repo memory：默认构建不再把 `秘藏膏丹丸散方剂` 的高噪声临床条目直接混入 syndrome/efficacy，真实运行对比已证明重建词典显著提升实体、关系、记录数与 KG 路径数。

### 关键验证记录
- `tests/test_research_utils.py` + `tests/test_paper_writer.py`：47 passed。
- `tests/unit/test_publish_phase.py`：34 passed（secondary consumer 迁移后回归）。
- `tests/test_report_generator.py` + `tests/test_output_generator.py`：31 passed。
- `tests/test_llm_context_adapter.py` + `tests/test_citation_manager.py` 相关选定用例：4 passed。
- cycle legacy 删除后的定向回归：`tests/unit/test_architecture_cycle_quality.py`、`tests/unit/test_iteration_feedback_loop.py`、`tests/unit/test_cycle_demo_contract.py`、`tests/test_research_pipeline_quality.py` 已通过。
- 全仓质量门：`tools/quality_gate.py --report output/quality-gate.json` 返回 `overall_success=True`，当前基线为 `overall_score=95.0`、`grade=A`、`quality_consumer_inventory.missing_contract_count=0`、`uncategorized_root_script_count=0`。

### 当前续接锚点
- 如果继续沿统一契约这条线推进，真正剩下的只是一类“风格一致性优化”：把 `src/generation/output_formatter.py` 的少量 reader 也改成 helper-based 解析；这不是当前阻塞项。
- publish 根级兼容镜像删除已经结束，后续不要再恢复 `paper_draft`、`report_session_result`、`report_output_files` 这类根字段；对外读取应继续通过 `results.*`、`artifacts` 或 orchestrator/web DTO。
- `src/cycle/` 已经完成一次硬收缩，后续不应再围绕被删除的 iteration/fixing/test-driven 子系统追加修复；下一步若继续清理，应只审视当前 runtime/demo 封装是否还能再合并。
- 词典/真实运行诊断现已具备独立工具链，后续可以单独沿 `tools/diagnostics/rebuild_tcm_lexicon.py` 和 `compare_real_cycle_lexicon_modes.py` 继续演进，不必重新从主链编排里埋临时脚本。

### 任意日期继续接手建议
1. 先读本节“阶段性收口（2026-04-12）”，再读 `PHASE_RESULT_LEGACY_FIELD_REMOVAL_2026_04_08.md`，不要直接从更老的 Roadmap 重新判断当前完成度。
2. 运行 `python tools/quality_gate.py --report output/quality-gate.json`，确认基线仍是 `overall_success=True`。
3. 如果继续统一契约线，先决定是否做 `output_formatter.py` 的风格一致性 cleanup；如果不做，这条线可以视为阶段性完成。
4. 如果继续真实研究质量线，优先从 real observe / 词典工具链切入，而不是回头改已稳定的 publish 根契约。
5. 如果继续架构收口，优先审视当前 `src/cycle/` 和 web 入口的剩余边界，而不是恢复已删除的 legacy module。

### 提交边界说明
- 本次 checkpoint 提交覆盖当前工作树中的正式代码、测试、文档和诊断脚本变更。
- 质量归档文档、架构审计文档、PhaseResult 删除清单、词典/真实运行对比工具均属于这轮推进的正式交付面，不再视作临时产物。

## 阶段性收口（2026-04-08）

### 本轮收口目标
- 对齐架构审计 Roadmap 的当前实现面，补齐当时科研主链与 `run_cycle_demo` 的边界拆分；当前主链已在此基础上继续演进为七阶段。
- 落地 Neo4j/Cypher 注入防护、跨存储事务原子性和质量门扫描接入。
- 收尾 Web 登录与 Dashboard 数据显示问题，保证当前版本能以统一登录页进入并正确读取 ORM 数据。

### 当前已落地成果

#### 1. 历史科研主链与 `run_cycle_demo` 收口（当前主链已演进为七阶段）
- `run_cycle_demo.py` 大幅瘦身，主文件从“大而全脚本”拆到 `src/cycle/` 下的桥接/插件/研究会话/存储持久化/子进程模块。
- 新增 `src/cycle/cycle_pipeline_bridge.py`，让 `cycle_runner` 默认通过真实 `ResearchPipeline` 执行当时主链迭代，而不是继续堆积在 CLI 文件内；后续主链已在 `experiment` 与 `analyze` 之间补入 `experiment_execution`。
- 2026-04-08 时新增 `src/cycle/cycle_research_session.py`，把当时 research mode 的 session 生命周期、结果序列化、报告导出从入口脚本中抽离；截至 2026-04-14，该入口已继续收口为消费 `entrypoint=demo` 装配结果后的 shared runtime 参数透传，不再本地持有 demo profile 默认值。
- 新增 `src/cycle/cycle_plugin_workflows.py`、`src/cycle/cycle_storage_persist.py`、`src/cycle/cycle_subprocess.py`，把插件工作流、双库存档、subprocess 安全包装单独封装。

#### 2. Pipeline/Phase 显式化与降级路径补齐
- `src/research/research_pipeline.py` 去掉隐式 `__getattr__` 桥接，改为显式暴露 phase/runtime 相关方法，减少动态委托带来的不可追踪行为。
- `src/research/phase_orchestrator.py` 去掉大量阶段 passthrough 私有桥，统一通过 `get_handler()` 直接拿显式 handler 执行。
- `src/research/phases/observe_phase.py` 改为调用 `execute_real_module_pipeline()` 执行观察阶段子流程，支持可选模块失败时继续链路。
- `src/research/phases/analyze_phase.py` 增加 Hypothesis fallback：当 Observe 没有 ingest 产物时，可从假设阶段合成最小分析记录与关系，避免 Analyze 空转。
- `src/research/pipeline_orchestrator.py` 为 analyze 阶段补充 degraded 标记：`record_count == 0` 时显式把阶段和循环状态打成 degraded。
- `src/research/phases/publish_phase.py` 从 `PaperWriter` 真实产出动态构建 publications，不再使用纯占位假数据。
- `src/research/phases/reflect_phase.py` 与 `src/learning/self_learning_engine.py` 打通 LLM 诊断、模式提取和 AdaptiveTuner 调参闭环。

#### 3. 安全与质量治理收口
- `src/storage/neo4j_driver.py` 增加 `_safe_cypher_label()`，所有动态 label/relationship-type 在拼接前做标识符校验，封堵 Cypher 注入入口。
- `src/storage/transaction.py` 改为“PG flush -> Neo4j execute -> PG commit”的原子提交顺序，补上 Neo4j 失败/PG commit 失败时的补偿逻辑。
- 新增 `tools/cypher_injection_scan.py`，并接入 `tools/quality_gate.py` 与 `.github/workflows/quality-control.yml`，把 Cypher 注入扫描纳入质量门和 CI。
- `src/core/event_bus.py` 增加 dead-letter warning，便于排查事件发出但无人消费的链路断裂。
- `src/web/auth.py` 增加 JWT HS256 最小 32 字节密钥长度校验，避免弱密钥配置继续工作。

#### 4. 惰性导出与兼容层清理
- 多个包入口改为 lazy import：`src/ai_assistant`, `src/analytics`, `src/api/routes`, `src/common`, `src/data`, `src/extraction`, `src/infra`, `src/learning`, `src/llm`, `src/orchestration`, `src/quality`, `src/visualization`, `src/research/phase_handlers`, `src/research/phases`, `src/semantic_modeling/methods`。
- 清理旧兼容层与重复包导出：删除 `src/output/*`、`src/reasoning/*`、`src/extractors/*` 等已迁移 shim，推动导入路径向权威实现收敛。
- `src/infrastructure/config_loader.py` 与 `src/infra/config_manager.py` 明确标注 `ConfigManager` 已弃用，后续应统一走 `load_settings()`。

#### 5. Web 登录与 Dashboard 运行面修复
- 登录链路已确认：统一登录页 `/login`、JWT 登录 `/api/auth/login`、用户信息 `/api/auth/me` 可用。
- `src/web/app.py` 新增数据库初始化与 shutdown 清理，`dashboard` 的 ORM 指标不再因 `app.state.db_manager` 缺失而全部显示 0。
- 当前实际验证结果：Dashboard 已能正确显示 SQLite 中的 ORM 数据，至少恢复为 `知识实体(ORM)=6`、`分析文档=5`；`知识关系(ORM)=0` 是数据库当前真实内容而不是显示错误。

### 关键验证记录
- 手动诊断登录配置与密码校验：确认统一登录页可用，账号加载与 JWT 签发正常。
- 手动启动 `src.web.main` 后验证接口：
  - `/api/auth/status` 200
  - `/api/auth/login` 200
  - `/api/auth/me` 200
  - `/api/dashboard/stats` 200
- 定向测试已补充：
  - `tests/test_auth_login_resilience.py`
  - `tests/test_event_bus.py`
  - `tests/test_phase_orchestrator_contract.py`
  - `tests/test_research_pipeline_observe.py`
  - `tests/test_research_pipeline_quality.py`
  - `tests/test_research_pipeline_analyze_degrade.py`
  - `tests/unit/test_analyze_phase.py`
  - `tests/unit/test_publish_phase.py`
  - `tests/unit/test_reflect_phase_extended.py`
  - `tests/unit/test_self_learning_feedback_loop.py`
  - `tests/unit/test_cypher_injection_scan.py`
  - `integration_tests/test_transaction.py`
  - `integration_tests/test_transaction_docker_e2e.py`

### 当前续接锚点

#### 代码入口
- CLI/演示主入口：`run_cycle_demo.py`
- 新 cycle 拆分模块：`src/cycle/`
- 科研主链：`src/research/research_pipeline.py`
- 阶段实现：`src/research/phases/`
- 存储与事务：`src/storage/neo4j_driver.py`, `src/storage/transaction.py`
- 质量门：`tools/quality_gate.py`, `tools/cypher_injection_scan.py`
- Web 入口与登录：`src/web/app.py`, `src/web/auth.py`, `src/web/routes/auth.py`

#### 运行基线
1. 激活环境：`.\venv310\Scripts\activate`
2. 启动 Web：`python -m src.web.main --port 8000`
3. 浏览器检查：`/login` -> `/dashboard`
4. 质量门：`python tools/quality_gate.py --report output/quality-gate.json`
5. 定向事务/阶段测试优先从新增测试文件开始回归。

### 任意日期继续接手建议
1. 先看本文件“阶段性收口（2026-04-08）”和下方历史阶段，确认当下收口位置而不是从旧 Roadmap 重新判题。
2. 若继续推进架构线，优先检查 `run_cycle_demo.py` 与 `src/cycle/` 是否还存在残留 CLI 逻辑可以继续下沉。
3. 若继续推进科研主链，优先围绕 Analyze/Publish/Reflect 的新增 fallback 和 degraded 契约补集成回归。
4. 若继续推进安全线，优先把 Cypher 注入扫描从 `neo4j_driver.py` 扩展到更多存储/图查询调用点，并把事务 docker e2e 纳入条件化 CI。
5. 若继续推进 Web 线，优先解决 `src.web.main` 模式下没有 `/console` 路由的问题；当前 `/dashboard` 正常，`/console` 仍属于 `web_console/app.py` 启动路径。

### 提交边界说明
- 临时诊断脚本 `_diag_login.py`、`_check_*` 类文件不属于正式交付面，按约定不纳入代码基线。
- 本次应提交的正式资产以架构拆分、测试补齐、安全治理、Web 修复和本摘要文档为主。

---

## 架构审计 Roadmap 推进（2026-04-06）

### 本轮目标
按 `ARCHITECTURE_AUDIT_2026_04_06.md` Roadmap，系统性消除 code_quality 复杂度告警，
目标文件按 warning 密度降序逐一击破。

### 量化成果

| 指标 | 改前基线 | 改后 | 变化 |
|---|---|---|---|
| warning_count | 155 | **144** | **−11** |
| tests (unit) | 278 pass | 278 pass | 0 |
| grade / score | A / 95.0 | A / 95.0 | stable |

### 文件级改动明细

#### 1. `src/api/websocket.py`（1 warning → 0）
- `stream_job_events_over_websocket` (complexity 13→~7)
- 提取 `_authenticate_and_get_job()`：认证 + job 查找，3 个 early-return 分支
- 提取 `_drain_pending_events()`：带锁的事件拉取

#### 2. `src/api/dependencies.py`（1 warning → 0）
- `resolve_authenticated_console_principal` (complexity 13→~9)
- 提取 `_try_resolve_jwt_principal(token)`：JWT 解析 + 字段提取（sub/display_name/auth_source）

#### 3. `src/generation/paper_writer.py`（14 warnings → 0，+402 / −273 行）

| 原函数 | 原复杂度 | 提取 helper | 策略 |
|---|---|---|---|
| `_revise_draft` | 41 | `_revise_expand_short_sections`, `_revise_add_missing_sections`, `_revise_abstract`, `_revise_references`, `_revise_keywords`, `_revise_enhance_fallback` | coordinator + 6 子步骤 |
| `_review_draft` | 23 | `_collect_review_issues` | 5 条件对→单函数返回 (issues, suggestions) |
| `_resolve_keywords` | 23 | `_deduplicate_keyword_candidates`, `_derive_keywords_from_entities`, `_derive_keywords_from_mining` | 3 来源回退链 |
| `_export_docx` | 21 | `_write_docx_front_matter`, `_write_docx_figures` | 首页 + 图表嵌入独立 |
| `_build_similar_formula_graph_evidence_section` | 20 | `_format_formula_graph_match` | 单条匹配格式化提取 |
| `_build_analysis_result_note` | 17 | `_format_statistical_metric_bits` | 双语 metric-bits 共享 |
| `_build_evidence_grade_result_note` | 17 | `_format_bias_distribution_bits`, `_assemble_evidence_grade_sentence` | 偏倚分布 + 组句分拆 |
| `_build_quality_discussion_text` | 15 | `_format_quality_metric_bits`, `_assemble_quality_discussion` | 同上模式 |
| `_build_methods` | 15 | `_build_evidence_protocol_text` | 证据协议双语文本 |
| `_export_markdown` | 15 | `_build_markdown_front_matter` | 作者/单位行提取 |
| `_build_results` | 13 | `_build_top_cluster_text`, `_assemble_results_text` | 聚类高亮 + 文本组装 |
| `_resolve_evidence` | 13 | `_iter_evidence_sources` | 生成器链替代嵌套 if |
| `_resolve_section_overrides` | 13 | `_parse_sections_payload` | payload 归一化独立 |
| `_run_iterative_refinement` | 13 | `_make_disabled_refinement_summary` | 禁用路径固定返回 |

### 验证记录
- `from src.generation.paper_writer import PaperWriter` → OK（每批次后 import check）
- `tests/test_paper_writer.py` + `tests/test_generation_coverage.py` → **72 passed**
- `tests/unit/` 全量 → **278 passed**
- `tools/quality_gate.py` → **overall_success=True, A/95.0, 144 warnings**

### 关键改动文件
- `src/api/websocket.py`
- `src/api/dependencies.py`
- `src/generation/paper_writer.py`

### 任意日期续接指引
1. 切到本提交，激活环境 `.\venv310\Scripts\activate`
2. 运行 `python -m pytest tests/unit/ -x -q --tb=short` → 预期 278 passed
3. 运行 `python tools/quality_gate.py --report output/quality-gate.json` → A/95.0, 144 warnings
4. 剩余 warning 热点按 `quality-gate.json` 中 `code_quality.details` 排序，逐文件击破
5. 每个函数拆分后先做 import check，再跑对应 test 文件，最后全量回归

### 下一接力方向
- **继续降 warning**：剩余 144 条，按文件聚集度选下一个簇（如 `research_utils.py`, `cycle_runner.py`, `data_mining.py` 等）
- **Phase 2 打通**：AnalyzePhase 真实实现、System A/B 融合（见审计报告 §七）
- **Phase 3 新功能**：Meta-Analysis 引擎、Research Compendium 归档（见下方"未开始"章节）

> 分支 `stage2-s2_1-preprocessor-opt` · 基线 `881b5c7` (refactor: decompose run_cycle_demo)
> 截止 2026-04-06 · 测试基线 **278 passed** (unit) · **144 warnings** · **A / 95.0**

---

## 增量收口（2026-04-05）

### 收口范围
- 研究看板 P4.2 收尾：失败阶段高亮、健康度分级、异常阶段一键过滤、阶段详情弹层。
- 研究看板 P4.3 首版：知识关系图谱预览 + 放大弹层，支持节点/边/关键关系摘要展示。
- 登录配置更新：控制台账号改为 `hgk1988`。

### 已落地结果
- 后端 dashboard payload 新增 `knowledge_graph_board`（节点、边、统计、高亮关系）。
- 前端看板新增关系图渲染模块（SVG），并提供“放大展示知识关系”交互。
- 研究看板与阶段看板交互已统一：异常过滤、阶段点击弹层、ESC/遮罩关闭。
- 登录参数已更新到运行配置：`secrets.yml -> security.console_auth.users`。

### 关键改动文件（本轮）
- `src/api/research_utils.py`
- `src/api/schemas.py`
- `web_console/static/index.html`
- `tests/test_web_console_api.py`
- `secrets.yml`

### 验证结论
- 已执行：`tests/test_web_console_api.py`
- 结果：`63 passed, 0 failed`

### 任意日期续接指引
1. 先拉取并切到收口提交后版本，阅读本文件顶部“增量收口（2026-04-05）”与“未开始”章节。
2. 启动服务后访问 `/login`，使用新账号登录，再访问 `/console` 验证看板可用。
3. 创建研究任务后验证三类交互：异常过滤、阶段详情弹层、知识关系放大弹层。
4. 若要继续 P4.3 深化，优先按顺序推进：布局优化（拥挤场景）-> 边筛选（阈值/类型）-> 缩放/拖拽。
5. 提交前至少执行一次定向回归：`python -m pytest tests/test_web_console_api.py -q`。

### 待办建议（下一接力点）
- 增加知识图谱视图的“关系权重阈值”筛选。
- 对节点/边数量较大场景增加性能保护（抽样、分页、懒渲染）。
- 为 `knowledge_graph_board` 增加异常/缺省数据测试样例。

> 分支 `stage2-s2_1-preprocessor-opt` · 基线 `2febb2c` (merge main)
> 截止 2026-04-04 · 测试基线 **38 failed / 1482 passed / 1 skipped**

---

## 已完成阶段

### Phase 0 — 零风险债务清理
- 清理无用 import、死代码、重复定义
- 统一日志格式与 warning 治理

### Phase 1 — 基础设施统一
- `ModuleContext` / `ModuleOutput` 权威位置迁至 `src/core/module_base.py`
- 删除 `src/core/module_interface.py` 中的重复定义，改为 re-export shim
- `BaseModule` 自动注册 `ModuleRegistry`（best-effort, never raises）
- `PhaseTrackerMixin` 统一到 `src/core/phase_tracker.py`
- `EventBus` 合并：`src/infra/event_bus.py` → shim 转发至 `src/core/event_bus.py`
- 所有 `__init__.py` 按架构 3.0 规范整理 re-export

### Phase 2 — 编排层解耦
- **Ports/Adapters 架构引入**
  - 5 个 Port 接口：`CollectionPort`, `AnalysisPort`, `ResearchPort`, `QualityPort`, `OutputPort` → `src/core/ports.py`
  - 默认适配器实现 → `src/core/adapters.py`
  - `ResearchPipeline._bootstrap_research_services()` 集成 Port 注入
- **observe_phase 恢复与迁移**
  - 从 git history 恢复 `src/research/phases/observe_phase.py`
  - 迁移至使用 `analysis_port` 进行文献分析
- **publish_phase 迁移**
  - 迁移至使用 `output_port` 进行成果输出
- **假设引擎合并**
  - 删除 `src/hypothesis/hypothesis_engine.py`（30 行 shim）
  - 保留 `src/research/hypothesis_engine.py` 为权威实现
  - `src/hypothesis/__init__.py` 转发 re-export
- **Web 入口合并**
  - `web_console/{job_manager,job_store,console_auth}.py` 核心逻辑移至 `src/web/ops/`
  - 原文件保留为向后兼容 shim
  - `src/web/routes/auth.py`, `src/web/routes/dashboard.py` 新增路由拆分

---

## 本次变更统计

| 类别 | 文件数 | 说明 |
|------|--------|------|
| Modified | ~35 | 重构 import / re-export / shim 化 |
| Added (new) | ~12 | ports.py, adapters.py, phases/, web/ops/, web/routes/, tools/ |
| Deleted | 1 | src/hypothesis/hypothesis_engine.py |
| Net LOC | -4500+ | 大量重复代码消除 |

---

## 未开始 — Phase 3：科研能力增强（新增功能）

以下 4 个功能模块已完成需求分析和代码上下文调研，尚未编码：

### 3.1 Meta-Analysis 引擎
- **目标文件**: `src/quality/meta_analysis.py`（~1500 行）
- **依赖**: scipy 1.15.3（已验证可用）、现有 `EvidenceGrader` / `StudyRecord`
- **功能规划**:
  - 固定效应模型 (Mantel-Haenszel)
  - 随机效应模型 (DerSimonian-Laird)
  - 异质性检验 (Q-test, I², τ²)
  - Forest plot / Funnel plot 数据生成
  - 发表偏倚检测 (Egger's test, Begg's test)
  - 亚组分析与敏感性分析
- **集成点**: 扩展 `src/quality/__init__.py` 导出

### 3.2 Research Compendium 归档
- **目标文件**: `src/generation/compendium.py`（~800 行）
- **功能规划**:
  - 打包：数据、代码引用、分析结果、环境信息
  - 可重现性元数据 (Python 版本、依赖快照、随机种子)
  - ZIP/目录 两种归档格式
  - 与 `ReportGenerator` / `OutputFormatter` 集成
- **集成点**: 扩展 `src/generation/__init__.py` 导出

### 3.3 实验设计模板增强
- **目标文件**: `src/research/experiment_templates.py`（~1000 行）
- **功能规划**:
  - RCT 模板：随机化方案、盲法、对照组、样本量计算 (power analysis)
  - 队列研究模板：暴露/结局追踪、随访周期设计
  - 病例对照模板：匹配标准、OR 计算
  - TCM 特色：证候分型作为分层因子、方剂组合作为干预
- **集成点**: 供 `ExperimentPhaseMixin` / `TheoreticalFramework.design_experiment()` 调用

### 3.4 术语桥接 TCM ↔ ICD-11
- **目标文件**: `src/knowledge/terminology_bridge.py`
- **功能规划**:
  - TCM 证候 → ICD-11 编码双向映射
  - 中药名 → ATC 分类映射
  - 模糊匹配 + 精确匹配双模式
  - 映射置信度评分
  - 映射表版本管理（长期维护成本）
- **集成点**: 扩展 `src/knowledge/__init__.py` 导出

---

## 已知遗留

- **38 个测试失败** — 均为 Phase 0 之前即存在的历史失败，非本轮引入
- **web 启动问题** — `src.web.main` 部分路由依赖待补全（不影响核心 pipeline）
- **tmp 临时目录** — `tmp03cy5eko/`, `tmp3m8l9_h1/`, `tmpz_g33xpa/` 为 subagent 报告残留，可安全清理

---

## 继续接力指引

1. **环境**: Python 3.10 venv → `.\venv310\Scripts\activate`
2. **测试**: `python -m pytest tests/ -q --tb=no` → 预期 38 failed / 1482 passed
3. **下一步**: 从 Phase 3.1 Meta-Analysis 引擎开始编码
4. **参考上下文**:
   - BaseModule 模式: `src/core/module_base.py`
   - GRADE 体系: `src/quality/evidence_grader.py`
   - StudyRecord 数据类: 同上
   - 实验框架: `src/research/theoretical_framework.py` → `ResearchExperiment`
   - 知识层: `src/knowledge/ontology_manager.py`, `tcm_knowledge_graph.py`
