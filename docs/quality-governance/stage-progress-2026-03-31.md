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
