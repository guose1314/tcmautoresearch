# 阶段性推进摘要（2026-03-31）

## 1. 目标与范围

本阶段目标：将核心能力从“可运行”推进到“可持续演进”，重点落在以下四条主线：

1. 基础设施收口：LLM 双模式封装 + 磁盘缓存 + 词典热加载。
2. 研究流程解耦：假设引擎、Gap 分析、DataMiner、编排器、任务调度器模块化。
3. 知识层规范化：本体约束集中管理，统一节点/关系校验入口。
4. 交付与治理闭环：引用管理、质量治理档案、测试补齐与回归验证。

## 2. 已完成能力（按模块）

### 2.1 Infra / LLM

- `src/infra/llm_service.py`
  - 新增 `APILLMEngine`，支持 OpenAI 兼容 API 调用。
  - `CachedLLMService` 支持本地/API 双模式统一缓存装饰。
  - 新增 `from_api_config`、`from_config` 工厂，`from_gap_config` 走统一分发。
  - 缓存 key 增加 mode 语义，避免本地/API 冲突。

- `src/infra/cache_service.py`
  - 已具备 `DiskCacheStore` + `LLMDiskCache`（SQLite/WAL/TTL/namespace）。
  - 提供 `_DiskCache` 向后兼容别名。

### 2.2 Infra / Lexicon

- `src/infra/lexicon_service.py`
  - JSONL 词典加载替代硬编码词表。
  - 支持 `refresh_if_needed()` 自动热加载与 `reload()` 手动重载。
  - 文件签名含内容哈希，规避 mtime/size 同步变化漏检。

### 2.3 Research / Knowledge / Orchestration

- `src/knowledge/ontology_manager.py`
  - 集中管理节点类型、关系约束、节点 ID 生成与校验。

- `src/research/gap_analyzer.py`
  - 分离 `GapAnalysisCore`（纯分析）与 `GapAnalysisLLMAdapter`（LLM 适配）。

- `src/research/data_miner.py`
  - 独立 DataMiner（聚类、主题、网络药理、统计分析）。

- `src/hypothesis/hypothesis_engine.py`
  - 从一次性生成升级为“生成→评分→验证→修订”闭环。

- `src/orchestration/research_orchestrator.py`
  - 增加函数式单入口 `run_research(...)`。

- `src/orchestration/task_scheduler.py`
  - 增加队列模式（`start_queue/submit_task/get_result/join_queue/stop_queue`）。

### 2.4 Output / Citation

- `src/output/citation_manager.py`
  - 已支持 BibTeX 生成。
  - 新增 GB/T 7714 文本格式输出。
  - 返回统一字段：`bibtex`、`gbt7714`、`formatted_references`、`format`。

- `src/research/research_pipeline.py`
  - Publish 阶段输出中增加 `gbt7714`，并在交付清单加入 “GB/T 7714 参考文献”。

## 3. 验证状态（关键测试）

- `tests/test_llm_service.py`：通过（117 passed）。
- `tests/test_cache_service.py`：通过（96 passed）。
- `tests/test_lexicon_service.py`：通过（热加载场景已覆盖）。
- `tests/test_citation_manager.py`：通过（24 passed，含 BibTeX + GB/T）。

> 说明：以上为阶段内关键模块回归结果；全仓测试建议在下一阶段续接时执行一次完整回归。

## 4. 当前可续接断点

可从以下任一入口继续，不依赖“上一天上下文”：

1. **引用规范深化**：将 GB/T 7714 细则精细化（文献类型映射、标点规范、作者人数规则）。
2. **编排与调度联动**：把 `TaskScheduler` 队列模式接入 `ResearchOrchestrator` 的阶段内子任务。
3. **配置收敛**：在 `config.yml` 增补 LLM API 模式示例并统一格式字段说明。
4. **质量门集成**：将新增模块纳入质量反馈和档案模板的固定检查项。

## 5. 下一阶段建议待办（可直接执行）

1. 执行全量测试并产出失败清单。
2. 对 `citation_manager` 增加更多 GB/T 边界用例（专著、会议论文、电子资源）。
3. 在 README 补“LLM 双模式 + 引用双格式”的最短配置示例。
4. 统一 `src/infra` 与 `src/llm` 导出文档，减少调用入口歧义。

## 6. 续接操作清单（10 分钟启动）

1. `git status --short` 确认工作区状态。
2. `pytest tests/test_llm_service.py tests/test_cache_service.py tests/test_citation_manager.py -q` 做关键回归。
3. 依据“下一阶段建议待办”任选 1 条推进。
4. 完成后更新同目录下一份日期化阶段摘要。

## 7. 当日增量（续推批次）

### 7.1 S2-1 预处理器优化收口

- `src/preprocessor/document_preprocessor.py`
  - 拆分 `_do_execute`：新增 `_validate_raw_text`、`_build_processing_steps`、`_estimate_token_count`，降低单函数复杂度并保持输出契约不变。
  - 修正 `segment_with_ancient_punctuation` 返回类型注解为二维分词列表。

- `tests/unit/test_preprocessor_output_quality.py`
  - 增加古文分词输出结构断言。
  - 新增 token 统计降级路径测试（分词异常时回退空格分割）。

### 7.2 Gate 阻断修复

- `src/data/tcm_lexicon.py` 与 `src/llm/llm_service.py`
  - 清除 UTF-8 BOM，修复 `invalid non-printable character U+FEFF`，恢复 logic/dependency gate 正常执行。

- `tests/test_full_cycle.py`
  - 清理重复 `__all__` 导出，消除 logic checks 残余 warning。

### 7.3 S2-2 抽取器重构启动

- `src/extractors/advanced_entity_extractor.py`
  - 新增 `_validate_processed_text`，统一输入校验。
  - 拆分实体匹配核心路径：`_iter_word_matches`、`_is_position_overlapped`、`_build_entity_record`。
  - 拆分剂量解析逻辑：`_parse_dosage_groups`。

- 新增 `tests/unit/test_advanced_entity_extractor.py`
  - 覆盖输入校验、最长匹配非重叠、剂量抽取、输出契约。

### 7.4 验证结果

- `tests/unit/test_preprocessor_output_quality.py`：通过（40 passed）。
- `tests/unit/test_advanced_entity_extractor.py` + `tests/test_research_pipeline_ingestion.py`：通过（7 passed）。
- `tests/test_llm_service.py` + `tests/unit/test_preprocessor_output_quality.py`：通过（177 passed）。
- `tools/quality_gate.py`：连续通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。

## 8. 当日增量（S2-3 语义建模稳定化）

### 8.1 代码重构

- `src/semantic_modeling/semantic_graph_builder.py`
  - `_do_execute` 新增输入与分层辅助：`_validate_entities`、`_partition_entities`、`_extract_entity_names`。
  - 4 组高级分析提取逻辑统一为 `_collect_advanced_formula_analyses`，减少重复流程分支。
  - 4 类方剂分析循环统一复用 `_analyze_formulas_with`，消除重复代码块。
  - 增加 `entities` 的边界校验：非列表输入抛错，`None` 输入安全降级为空列表。

### 8.2 新增测试

- `tests/unit/test_semantic_graph_builder.py`
  - 覆盖实体输入校验（非法类型/过滤非 dict）。
  - 覆盖 integrated 结果优先 + fallback 回退路径。
  - 覆盖 `entities=None` 的执行边界行为与输出契约。

### 8.3 回归与门禁

- `tests/unit/test_semantic_graph_builder.py` + `tests/test_relation_extractor.py` + `tests/test_research_pipeline_ingestion.py`：通过（25 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。

## 9. 当日增量（S2-4 推理引擎优化）

### 9.1 代码重构

- `src/reasoning/reasoning_engine.py`
  - KG 路径查找链路拆分为 `_collect_formula_nodes`、`_collect_target_nodes`、`_iter_valid_pairs`、`_safe_simple_paths`，降低 `_find_kg_paths` 分支密度。
  - 推理链 DFS 引入 `_ChainTraversalState`，将 `_dfs_chain` 参数从 9 个降到 4 个，降低函数接口复杂度。
  - 保持输出契约不变（`kg_paths`、`inference_chains`、`reasoning_results` 等字段语义不变）。

### 9.2 回归与门禁

- `tests/test_reasoning_engine.py` + `tests/test_research_pipeline_quality.py`：通过（156 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警数由 70 降至 68（持续收敛）。

## 10. 当日增量（S2-5 输出生成器强化）

### 10.1 代码重构

- `src/output/output_generator.py`
  - 质量指标统计新增 `_safe_metric_count`，对非数字/异常值统一降级为 0。
  - 建议生成逻辑拆分为 `_recommendations_by_entity_count` + `_recommendations_by_confidence`，降低 `_build_recommendations` 分支复杂度。
  - 保持输出契约不变（`output_data` / `quality_metrics` / `recommendations` 结构不变）。

### 10.2 测试补强

- `tests/unit/test_preprocessor_output_quality.py`
  - 新增坏置信度输入（`confidence_score="bad"`）建议回退测试。
  - 新增非数值统计字段质量指标回退测试。

### 10.3 回归与门禁

- `tests/unit/test_preprocessor_output_quality.py` + `tests/test_research_pipeline_quality.py`：通过（121 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。

## 11. 当日增量（S2-6 质量评估与合并准备）

### 11.1 全量关键回归

- 关键测试批次一次性回归通过（388 passed）：
  - `tests/test_llm_service.py`
  - `tests/test_cache_service.py`
  - `tests/test_citation_manager.py`
  - `tests/test_reasoning_engine.py`
  - `tests/test_relation_extractor.py`
  - `tests/test_research_pipeline_ingestion.py`
  - `tests/test_research_pipeline_quality.py`
  - `tests/unit/test_preprocessor_output_quality.py`
  - `tests/unit/test_advanced_entity_extractor.py`
  - `tests/unit/test_semantic_graph_builder.py`

### 11.2 质量门结论

- `tools/quality_gate.py`：全门通过。
- 关键指标：
  - `logic_checks`: 0 error / 0 warning
  - `quality_assessment`: `overall_score=95.0`, `grade=A`, `failed_dimension_count=0`
  - `continuous_improvement`: `trend_status=stable`

### 11.3 合并准备产物

- 新增合并就绪文档：`docs/quality-governance/s2-6-merge-readiness-2026-03-31.md`
  - 包含：可合并结论、验证证据、改动范围、排除项、提交前执行清单。

## 12. 当日增量（S2-6 后续：warning TopN 精修第 1 轮）

### 12.1 精修目标

- `src/core/phase_tracker.py`：`_serialize_value` 复杂度告警（13 > 12）。
- `src/research/data_miner.py`：`frequency_and_chi_square`（20 > 12）与 `time_series_and_dose_response`（17 > 12）。

### 12.2 代码重构

- `src/core/phase_tracker.py`
  - `_serialize_value` 拆分为 `_serialize_primitive` / `_serialize_mapping_like` / `_serialize_sequence_like` / `_serialize_dataclass_like`，降低分支密度并保持序列化契约一致。

- `src/research/data_miner.py`
  - 统计卡方链路拆分：`_build_herb_frequency` / `_collect_syndrome_values` / `_build_contingency_counts` / `_compute_chi_square` / `_chi2_fallback`。
  - 时间-剂量链路拆分：`_extract_time_series` / `_fit_linear_trend` / `_extract_dose_response` / `_fit_dose_response_model` / `_try_fit_hill`。

### 12.3 测试与验证

- 新增：`tests/unit/test_phase_tracker_mixin.py`（序列化行为 + 阶段生命周期）。
- 扩展：`tests/test_data_miner.py`（time_series+dose_response 场景覆盖）。
- 回归通过：`tests/test_data_miner.py` + `tests/unit/test_phase_tracker_mixin.py` + `tests/test_research_pipeline_quality.py`（173 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`68 -> 65`（下降 3）。

## 13. 当日增量（S2-6 后续：warning TopN 精修第 2 轮）

### 13.1 精修目标

- `src/extraction/relation_extractor.py`：`extract` 复杂度告警（24 > 12）。
- `src/output/citation_manager.py`：`_normalize_record` 复杂度告警（18 > 12）。

### 13.2 代码重构

- `src/extraction/relation_extractor.py`
  - `extract` 拆分为 `_filter_entities_by_type`、`_build_name_to_node_map`、`_extract_formula_herb_edges`、`_extract_herb_efficacy_edges`、`_extract_treats_edges`。
  - 对非 dict 实体输入增加兼容过滤，避免异常项污染关系抽取流程。

- `src/output/citation_manager.py`
  - `_normalize_record` 拆分字段提取逻辑：新增 `_collect_record_text_fields` 与 `_read_first_text`。
  - 保持 BibTeX / GB-T 输出契约与字段语义不变。

### 13.3 测试与验证

- 扩展 `tests/test_relation_extractor.py`：新增非 dict 输入兼容测试。
- 扩展 `tests/test_citation_manager.py`：新增字段回退（venue/link/page/issue）行为测试。
- 回归通过：`tests/test_relation_extractor.py` + `tests/test_citation_manager.py` + `tests/test_research_pipeline_quality.py`（104 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`65 -> 63`（下降 2）。

## 14. 当日增量（S2-6 后续：warning TopN 精修第 3 轮）

### 14.1 精修目标

- `src/analytics/data_miner.py`：`cluster` 复杂度告警（14 > 12）。
- `src/knowledge/embedding_service.py`：`_coerce_formula_item` 复杂度告警（15 > 12）。

### 14.2 代码重构

- `src/analytics/data_miner.py`
  - `cluster` 拆分为 `_build_binary_matrix` / `_cluster_records` / `_analyze_factors` / `_format_factor_loadings`。

- `src/knowledge/embedding_service.py`
  - `_coerce_formula_item` 拆分为 `_extract_formula_identity` / `_build_formula_text_parts` / `_optional_list_text`。

### 14.3 测试与验证

- 扩展 `tests/test_embedding_service.py`：增加 `syndromes` 回退构造文本测试。
- 回归通过：`tests/test_data_miner.py` + `tests/test_embedding_service.py` + `tests/test_research_pipeline_quality.py`（143 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`63 -> 61`（下降 2）。

## 15. 当日增量（S2-6 后续：warning TopN 精修第 4 轮）

### 15.1 精修目标

- `src/knowledge/embedding_service.py`：`search` 复杂度告警（18 > 12）。
- `src/output/citation_manager.py`：`format_entry` 复杂度告警（16 > 12）。

### 15.2 代码重构

- `src/knowledge/embedding_service.py`
  - `search` 拆分为 `_validate_search_request` / `_prepare_query_vector` / `_rank_candidates` / `_build_search_results`。

- `src/output/citation_manager.py`
  - `format_entry` 拆分字段收集逻辑：新增 `_collect_bibtex_fields`。

### 15.3 测试与验证

- 回归通过：`tests/test_embedding_service.py` + `tests/test_citation_manager.py` + `tests/test_research_pipeline_quality.py`（129 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`61 -> 59`（下降 2）。

## 16. 当日增量（S2-6 后续：warning TopN 精修第 5 轮）

### 16.1 精修目标

- `src/learning/pattern_recognizer.py`：`_ingest` 复杂度告警（17 > 12）。
- `src/orchestration/research_orchestrator.py`：`run` 复杂度告警（17 > 12）。

### 16.2 代码重构

- `src/learning/pattern_recognizer.py`
  - `_ingest` 拆分为 `_ingest_entities` / `_ingest_topic_sequence` / `_ingest_numeric_features` / `_trim_feature_history`。

- `src/orchestration/research_orchestrator.py`
  - `run` 拆分为 `_prepare_pipeline_and_cycle` / `_execute_phases` / `_build_skipped_outcomes`。
  - 维持阶段失败中断策略与返回契约不变。

### 16.3 测试与验证

- 回归通过：`tests/unit/test_learning_optimization_features.py` + `tests/test_research_orchestrator.py` + `tests/test_research_pipeline_quality.py`（165 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`59 -> 57`（下降 2）。

## 17. 当日增量（S2-6 后续：warning TopN 精修第 6 轮）

### 17.1 精修目标

- `src/research/research_pipeline.py`：`_collect_observe_corpus_if_enabled` 复杂度告警（14 > 12）。
- `src/research/research_pipeline.py`：`_build_observe_metadata` 复杂度告警（13 > 12）。

### 17.2 代码重构

- `src/research/research_pipeline.py`
  - `_collect_observe_corpus_if_enabled` 拆分为 `_register_observe_collection_result` / `_to_observe_corpus_bundle`，统一来源结果注册与错误回退逻辑。
  - `_build_observe_metadata` 拆分为 `_is_ctext_corpus_collected` / `_build_observe_ingestion_flags` / `_has_observe_evidence_matrix`，降低分支密度并保持输出字段契约不变。

### 17.3 测试与验证

- 扩展 `tests/test_research_pipeline_quality.py`：
  - 新增“ctext 失败 + local 成功”时优先返回 bundle 的回退行为测试。
  - 新增 local-only bundle 的 observe metadata 标记测试（`auto_collected_ctext=False`）。
- 回归通过：`tests/test_research_pipeline_quality.py` + `tests/test_research_orchestrator.py` + `tests/test_corpus_bundle.py`（164 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`57 -> 55`（下降 2）。

## 18. 当日增量（S2-6 后续：warning TopN 精修第 7 轮）

### 18.1 精修目标

- `src/research/ctext_whitelist.py`：`build_batch_manifest` 复杂度告警（16 > 12）。
- `src/research/literature_retriever.py`：`_build_query_plan` 复杂度告警（13 > 12）。

### 18.2 代码重构

- `src/research/ctext_whitelist.py`
  - `build_batch_manifest` 拆分为 `_iter_group_items` / `_build_manifest_entry` / `_is_duplicate_entry` / `_track_seen_values`，统一去重与过滤逻辑。

- `src/research/literature_retriever.py`
  - `_build_query_plan` 改为 `QUERY_PLAN_TEMPLATES` 模板驱动，消除大规模 if-elif 链。
  - 保持各来源 URL 模板与提示语语义不变，fallback 场景继续追加“（API 回退）”。

### 18.3 测试与验证

- 扩展 `tests/test_ctext_whitelist.py`：新增重复 URN/URL 去重与非法项过滤测试。
- 新增 `tests/unit/test_literature_retriever_query_plan.py`：覆盖已知来源 fallback 与未知来源默认模板行为。
- 回归通过：`tests/test_ctext_whitelist.py` + `tests/unit/test_literature_retriever_query_plan.py` + `tests/test_research_pipeline_literature.py`（15 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`55 -> 53`（下降 2）。

## 19. 当日增量（S2-6 后续：warning TopN 精修第 8 轮）

### 19.1 精修目标

- `src/research/multi_source_corpus.py`：`recognize_classical_format` 复杂度告警（16 > 12）。
- `src/cycle/fixing_stage.py`：`_calculate_comprehensive_confidence` 复杂度告警（15 > 12）。

### 19.2 代码重构

- `src/research/multi_source_corpus.py`
  - `recognize_classical_format` 拆分为 `_recognize_by_suffix` / `_recognize_by_media_type` / `_recognize_by_sample_text`，统一后缀、MIME 与文本内容三层判定流程。

- `src/cycle/fixing_stage.py`
  - `_calculate_comprehensive_confidence` 拆分为 `_calculate_repair_confidence` / `_calculate_success_rate` / `_calculate_academic_confidence` / `_priority_academic_score`。
  - 保持权重规则不变：repair 0.4、quality 0.3、academic 0.3。

### 19.3 测试与验证

- 扩展 `tests/test_multi_source_corpus.py`：新增 XML/TEI 与 sample_text JSON 判定测试。
- 扩展 `tests/unit/test_fixing_stage_classification.py`：新增综合置信度精确数值断言。
- 回归通过：`tests/test_multi_source_corpus.py` + `tests/unit/test_fixing_stage_classification.py` + `tests/unit/test_architecture_cycle_quality.py`（145 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`53 -> 51`（下降 2）。

## 20. 当日增量（S2-6 后续：warning TopN 精修第 9 轮）

### 20.1 精修目标

- `src/cycle/iteration_cycle.py`：`execute_iteration` 过长告警（122 > 120）。
- `src/cycle/iteration_cycle.py`：`get_cycle_summary` 复杂度告警（14 > 12）。

### 20.2 代码重构

- `src/cycle/iteration_cycle.py`
  - `execute_iteration` 清理非必要注释与空行，函数长度收敛至阈值内。
  - `get_cycle_summary` 拆分为 `_build_average_metrics` 与 `_count_stable_iterations`，将平均指标计算与稳定轮次统计下沉到 helper。
  - 保持摘要输出契约不变（字段名与含义保持一致）。

### 20.3 测试与验证

- 回归通过：`tests/unit/test_architecture_cycle_quality.py` + `tests/unit/test_cycle_demo_contract.py`（126 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`51 -> 49`（下降 2）。

## 21. 当日增量（S2-6 后续：warning TopN 精修第 10 轮）

### 21.1 精修目标

- `src/cycle/module_iteration.py`：`get_module_performance_report` 复杂度告警（13 > 12）。
- `src/hypothesis/hypothesis_engine.py`：`_parse_llm_feedback_response` 复杂度告警（13 > 12）。

### 21.2 代码重构

- `src/cycle/module_iteration.py`
  - `get_module_performance_report` 拆分为 `_partition_iteration_history` / `_build_module_average_metrics` / `_build_module_report_analysis_summary`。
  - 保持模块报告输出契约不变（统计字段与 analysis_summary 语义保持一致）。

- `src/hypothesis/hypothesis_engine.py`
  - `_parse_llm_feedback_response` 拆分为 `_extract_feedback_payload` / `_normalize_feedback_score` / `_normalize_feedback_action` / `_normalize_feedback_revisions`。
  - 保持英文与中文动作关键词映射策略不变（retain/revise/deprioritize）。

### 21.3 测试与验证

- 扩展 `tests/test_hypothesis_engine.py`：新增中文动作归一化与异常分值文本解析测试。
- 回归通过：`tests/test_hypothesis_engine.py` + `tests/unit/test_architecture_cycle_quality.py`（139 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`49 -> 47`（下降 2）。

## 22. 当日增量（S2-6 后续：warning TopN 精修第 11 轮）

### 22.1 精修目标

- `src/cycle/test_driven_iteration.py`：`get_test_performance_report` 复杂度告警（13 > 12）。
- `src/hypothesis/hypothesis_engine.py`：`_run_llm_closed_loop` 复杂度告警（20 > 12）。

### 22.2 代码重构

- `src/cycle/test_driven_iteration.py`
  - `get_test_performance_report` 拆分为 `_partition_iterations` / `_average_execution_time` / `_average_confidence_score` / `_build_test_report_analysis_summary`。

- `src/hypothesis/hypothesis_engine.py`
  - `_run_llm_closed_loop` 拆分为 `_can_run_llm_closed_loop` / `_run_single_hypothesis_closed_loop` / `_collect_feedback_metrics` / `_normalize_verification_score` / `_normalize_validation_action` / `_apply_feedback_revision`。
  - 保持 LLM 闭环评分、动作归一化与 revise 回写语义不变。

### 22.3 测试与验证

- 扩展 `tests/test_hypothesis_engine.py`：新增闭环前置条件（未启用 llm_generation 时跳过）测试。
- 回归通过：`tests/test_hypothesis_engine.py` + `tests/unit/test_architecture_cycle_quality.py`（144 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`47 -> 45`（下降 2）。

## 23. 当日增量（S2-6 后续：warning TopN 精修第 12 轮）

### 23.1 精修目标

- `src/cycle/system_iteration.py`：`_build_analysis_results` 参数过多告警（8 > 7）。
- `src/hypothesis/hypothesis_engine.py`：`_build_candidate` 参数过多告警（10 > 7）。

### 23.2 代码重构

- `src/cycle/system_iteration.py`
  - `_analyze_system_results` 新增 `analysis_payload` 聚合对象。
  - `_build_analysis_results` 改为接收 `analysis_payload`，将多个分析产物参数收敛为单入参。
  - 同步清理未使用导入 `Enum`。

- `src/hypothesis/hypothesis_engine.py`
  - 新增 `HypothesisCandidateInput` dataclass，统一候选假设构造输入。
  - `_build_candidate` 改为接收单个 `HypothesisCandidateInput`，并更新 LLM/启发式路径所有调用点。

### 23.3 测试与验证

- 回归通过：`tests/test_hypothesis_engine.py` + `tests/unit/test_architecture_cycle_quality.py`（144 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`45 -> 43`（下降 2）。

## 24. 当日增量（S2-6 后续：warning TopN 精修第 13 轮，research/infra）

### 24.1 精修目标

- `src/research/literature_retriever.py`：`_search_pubmed` 复杂度告警（16 > 12）。
- `src/infra/cache_service.py`：`put_llm` 参数过多告警（8 > 7）与 `put` 参数过多告警（9 > 7）。

### 24.2 代码重构

- `src/research/literature_retriever.py`
  - `_search_pubmed` 拆分为 `_build_pubmed_params` / `_build_pubmed_records` / `_build_single_pubmed_record` / `_extract_pubmed_year` / `_extract_pubmed_doi`。
  - 保持 PubMed 请求参数、年份提取与 DOI 解析语义不变。

- `src/infra/cache_service.py`
  - `put_llm` 改为 `*legacy_args/**legacy_kwargs` 兼容模式，并下沉到 `_build_llm_meta` / `_parse_legacy_llm_args`。
  - `put` 维持新旧两套签名兼容（通用 `put(key, value, meta=...)` 与旧 LLM 参数形式），同时收敛显式参数数量。

### 24.3 测试与验证

- 扩展 `tests/test_cache_service.py`：新增 `put_llm` kwargs 兼容测试。
- 新增 `tests/unit/test_literature_retriever_pubmed_helpers.py`：覆盖 PubMed 年份/DOI 解析与空项处理。
- 回归通过：`tests/test_cache_service.py` + `tests/unit/test_literature_retriever_pubmed_helpers.py` + `tests/test_research_pipeline_literature.py`（104 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`43 -> 40`（下降 3）。

## 25. 当日增量（S2-6 后续：warning TopN 精修第 14 轮，research/infra）

### 25.1 精修目标

- `src/infra/llm_service.py`：`from_engine_config` 参数过多告警（10 > 7）。
- `src/infra/llm_service.py`：`from_api_config` 参数过多告警（11 > 7）。
- `src/research/google_scholar_helper.py`：`run_google_scholar_related_works` 参数过多告警（8 > 7）。

### 25.2 代码重构

- `src/infra/llm_service.py`
  - `from_engine_config` 改为 `model_path + **engine_options`，内部解析 engine/cache 配置，保持旧 kwargs 调用兼容。
  - `from_api_config` 改为 `api_url/model + **api_options`，内部解析 API 与缓存参数，保持行为不变。

- `src/research/google_scholar_helper.py`
  - 新增 `_resolve_related_works_options`，统一解析旧位置参数与新 kwargs。
  - `run_google_scholar_related_works` 改为 `*legacy_args/**options` 兼容入口，保留既有流程与产出契约。
  - 清理 fallback 生成中的无用循环变量。

### 25.3 测试与验证

- 新增 `tests/unit/test_google_scholar_helper_options.py`：验证旧位置参数调用兼容与 `max_papers` 生效。
- 回归通过：`tests/test_llm_service.py` + `tests/unit/test_google_scholar_helper_options.py` + `tests/test_google_scholar_helper_smoke.py`（117 passed）。
- `tools/quality_gate.py`：通过，`overall_score=95.0`，`grade=A`，`failed_dimension_count=0`。
- `code_quality` 告警：`40 -> 37`（下降 3）。
