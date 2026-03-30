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
