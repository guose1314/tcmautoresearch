# 阶段性进展摘要 — 2026-04-19

基于 `ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md` 审计建议的落地执行记录。

---

## 已完成阶段

### Phase A — 入口收口（此前 session 完成）
- 3 个入口文件迁移至 `ResearchRuntimeService` 7 阶段管道
- Guard #17 保护入口一致性

### Phase B — 存储治理（本 session 完成）
| 组件 | 文件 | 职责 |
|------|------|------|
| DegradationGovernor | `src/storage/degradation_governor.py` | PG/Neo4j 降级状态感知与策略决策 |
| BackfillLedger | `src/storage/backfill_ledger.py` | 回填任务追踪与优先级队列 |
| StorageObservability | `src/storage/storage_observability.py` | 存储操作指标采集（延迟/吞吐/错误） |
| 接线 | `src/storage/backend_factory.py` | 三组件注入 StorageBackendFactory |

- Guard #31：9 tests 保护强一致基础设施
- 测试文件：`tests/unit/test_storage_governance.py`（36 tests）

### Phase D — 学习闭环（本 session 完成）
| 组件 | 文件 | 职责 |
|------|------|------|
| PolicyAdjuster | `src/learning/policy_adjuster.py` | cycle_score → 证据策略 / 模板偏好 / 阶段阈值自动调整 |
| ImportQualityValidator | `src/research/import_quality_validator.py` | 外部导入数据三级校验（strict/standard/lenient） |
| 接线（Orchestrator） | `src/research/learning_loop_orchestrator.py` | reflect → adjust → next_cycle_strategy |
| 接线（Experiment） | `src/research/phases/experiment_execution_phase.py` | `_validate_import_quality()` |

- Guard #32：10 tests
- 测试文件：`tests/unit/test_learning_loop_phase_d.py`（33 tests）

### Phase E — 小模型成本优化（本 session 完成）
| 组件 | 文件 | 职责 |
|------|------|------|
| ReasoningTemplateSelector | `src/infra/reasoning_template_selector.py` | 5 推理框架按 phase/complexity/preference/budget 动态选择 |
| DynamicInvocationStrategy | `src/infra/dynamic_invocation_strategy.py` | proceed/decompose/skip/retry_simplified 决策 + 3 级降级 |
| DossierLayerCompressor | `src/infra/dossier_layer_compressor.py` | 三层上下文压缩（L0=512t / L1=1536t / L2=3072t） |
| SmallModelOptimizer | `src/infra/small_model_optimizer.py` | 门面层 `prepare_call()` → `CallPlan` |
| 入口单例 | `src/infra/llm_service.py` | `get_small_model_optimizer()` 懒初始化 |

- Guard #33：10 tests
- 测试文件：`tests/unit/test_phase_e_llm_optimization.py`（54 tests）

---

## 测试基线

```
2893 passed / 4 known failures / 2 skipped
```

已知失败（非本次引入）：
1. `tests/test_gap_analyzer.py` × 2 — `IndexError: list index out of range`
2. `tests/test_hypothesis_engine.py::test_llm_failure_falls_back_to_rules` — 规则引擎 fallback 条件
3. `tests/test_web_console_browser_e2e.py` — Selenium 环境 flaky

---

## 未完成阶段（后续 session 继续）

### Phase C — 协议统一：EvidenceContract v2 全量迁移
- 审计建议：将所有 phase 的产出统一为 `EvidenceEnvelope` 格式
- 现状：`EvidenceContract` / `EvidenceEnvelope` 已定义，部分 phase 已接入
- 待做：剩余 phase 迁移 + 端到端 schema 一致性校验

### Phase F — CI/可观测收口
- 审计建议：Prometheus metrics export、结构化日志、CI 覆盖率门禁
- 现状：`StorageObservability` 已埋点，但无 export adapter
- 待做：metrics HTTP endpoint、log formatter、CI config

### Phase G — 知识图谱增强
- 审计建议：Neo4j schema 版本化、图推理管道、假说子图标注
- 待做：全部

---

## 分支与 Guard 索引

- 分支：`stage2-s2_1-preprocessor-opt`
- Guard 总数：#1 — #33
- 关键 Guard 文件：`tests/unit/test_architecture_regression_guard.py`

---

## 接续要点

1. **测试命令**：`venv310\Scripts\python.exe -m pytest tests/ -q --tb=line`
2. **已知 4 failures 不可修**（外部依赖 / 环境问题），回归时排除：`-k "not test_web_console_browser_e2e"`
3. **PolicyAdjuster ↔ ReasoningTemplateSelector 桥接已就绪**：`prepare_next_cycle_strategy()` 输出 `template_preferences` → `SmallModelOptimizer.prepare_call(template_preferences=...)` 直接消费
4. **下一步推荐**：Phase C（协议统一）或 Phase F（CI 收口），两者无依赖可并行
