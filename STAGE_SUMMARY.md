# 阶段性推进摘要

## 阶段性收口（2026-04-13）

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
- Legacy Web 已不再直接绑定 in-memory ResearchPipeline 单例；src/web/ops/legacy_research_runtime.py 提供兼容 store，dashboard / analysis / research 路由都改为走统一 runtime + session store。

#### 2. 七阶段主链与实验语义拆分已经落到实现面

- src/research/study_session_manager.py、src/orchestration/research_orchestrator.py、src/research/pipeline_orchestrator.py、src/research/phase_orchestrator.py 已把默认研究链扩为 observe → hypothesis → experiment → experiment_execution → analyze → publish → reflect。
- src/research/phases/experiment_phase.py 已明确 experiment=实验方案阶段，只负责 protocol design，并显式输出 not_executed / not_started 边界元数据。
- 新增 src/research/phases/experiment_execution_phase.py 与 src/research/phase_handlers/experiment_execution_handler.py，承接外部实验执行、采样与结果导入；无输入时为 skipped，有输入时为 completed。
- src/research/phases/analyze_phase.py、src/research/phases/publish_phase.py、src/research/real_observe_smoke.py 已能消费 experiment_execution 的导入记录、关系和状态，而不是继续把 experiment 混写成真实实验执行。
- Web 与展示口径也已同步：web_console/static/index.html、src/web/routes/dashboard.py、src/api/research_utils.py 等位置统一把 experiment 显示为“实验方案阶段”，experiment_execution 显示为“实验执行阶段”。

#### 3. PostgreSQL / Neo4j 结构化持久化主链已经接上

- src/research/phase_orchestrator.py 已新增 structured persistence 主路径：ResearchSession / PhaseExecution / Artifact 写入 PostgreSQL，Neo4j 图投影与 legacy sqlite fallback 清晰分层。
- src/infrastructure/research_session_repo.py 现已支持外部事务 session 复用，并新增 observe 文档、实体、关系的结构化落库与快照回读。
- 新增 src/research/research_session_graph_backfill.py、tools/backfill_research_session_nodes.py、tools/backfill_research_graph_nodes.py，补齐历史研究会话到 Neo4j 的节点/边回填工具。
- src/storage/transaction.py、src/storage/neo4j_driver.py 已继续收口查询与写入规范：split MATCH、scoped CALL、可选关系读取去噪，避免把旧的 Neo4j 通知模式重新带回主链。
- src/infrastructure/monitoring.py 与相关测试已把 schema drift / structured storage 暴露到健康检查与监控摘要中。

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

- 定向回归已通过：tests/unit/test_research_runtime_service.py、tests/unit/test_legacy_research_runtime.py、tests/test_research_pipeline_experiment.py、tests/test_research_pipeline_persist.py、tests/test_config_loader.py、tests/test_alembic_runtime.py、tests/test_research_session_graph_backfill.py、tests/unit/test_backend_factory.py、tests/test_research_session_repo.py、tests/unit/test_neo4j_driver.py，共 264 passed。
- 真实持久化回归：integration_tests/test_experiment_execution_persistence_e2e.py 已在开发 PostgreSQL + Neo4j 上通过，结果为 2 passed in 22.36s。
- 真实语义锁定：该回归已明确断言 experiment_execution 无输入时持久化为 skipped，有输入时持久化为 completed。
- 文档最终收口：上述 5 份 STORAGE 历史文档最后一轮 diagnostics 已全部返回 No errors found。

### 当前续接锚点

- 运行时统一这条线当前已不该再回到“每个入口各装配一遍配置”的旧模式；后续若继续收口，应优先找剩余 direct pipeline shortcut 与 legacy 壳。
- experiment / experiment_execution 的语义边界已经在代码、测试、文档、Web 文案和持久化层同时落地；后续不要再把 experiment 写回“真实实验执行”。
- 结构化持久化已经接入主研究链，下一阶段重点不是“是否接线”，而是事务边界、fallback 治理、schema drift 与可观测性继续收敛。
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
- 新增 `src/cycle/cycle_research_session.py`，把 research mode 的 session 生命周期、结果序列化、报告导出从入口脚本中抽离。
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
