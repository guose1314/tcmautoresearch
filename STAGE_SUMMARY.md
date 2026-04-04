# 阶段性推进摘要

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
