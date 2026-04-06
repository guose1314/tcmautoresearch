# 阶段性推进摘要

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
