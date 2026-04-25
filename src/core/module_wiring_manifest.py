"""模块接线状态清单 — Module Wiring Manifest.

为系统中每个主要模块声明静态接线层级 (active / optional / dormant)，
降低"看起来有，但默认没接上"的认知成本。

层级定义:
  active   — 默认管线始终接入，无需任何配置即可运行
  optional — 功能完整，但需要配置标志或外部依赖才激活
  dormant  — 代码存在但未接入任何活跃管线路径（demo / deprecated / placeholder）

使用方式::

    from src.core.module_wiring_manifest import MODULE_MANIFEST, get_manifest_summary

    # 查询单个模块
    entry = MODULE_MANIFEST["self_learning_engine"]
    assert entry["tier"] == "optional"

    # 获取汇总
    summary = get_manifest_summary()
    print(summary["counts"])  # {"active": N, "optional": N, "dormant": N}
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# 接线层级常量
# ---------------------------------------------------------------------------
TIER_ACTIVE = "active"
TIER_OPTIONAL = "optional"
TIER_DORMANT = "dormant"

VALID_TIERS = frozenset({TIER_ACTIVE, TIER_OPTIONAL, TIER_DORMANT})

# ---------------------------------------------------------------------------
# 权威清单 — 每条记录包含 module_key, tier, path, description, activation
# ---------------------------------------------------------------------------

MODULE_MANIFEST: Dict[str, Dict[str, Any]] = {
    # ━━━ ACTIVE: 核心管线始终接入 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "research_pipeline": {
        "tier": TIER_ACTIVE,
        "path": "src/research/research_pipeline.py",
        "description": "研究管线主体，管理循环生命周期与模块组装",
        "activation": "always — ResearchRuntimeService 每次请求实例化",
    },
    "phase_orchestrator": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phase_orchestrator.py",
        "description": "阶段执行调度、事件分发与持久化",
        "activation": "always — _bootstrap_research_services()",
    },
    "pipeline_orchestrator": {
        "tier": TIER_ACTIVE,
        "path": "src/research/pipeline_orchestrator.py",
        "description": "循环级编排（create/start/complete/suspend/resume）",
        "activation": "always — self.orchestrator in ResearchPipeline",
    },
    "research_runtime_service": {
        "tier": TIER_ACTIVE,
        "path": "src/orchestration/research_runtime_service.py",
        "description": "CLI / Web 统一研究入口",
        "activation": "always — 所有研究请求的唯一入口",
    },
    "study_session_manager": {
        "tier": TIER_ACTIVE,
        "path": "src/research/study_session_manager.py",
        "description": "ResearchPhase / ResearchCycle / ResearchCycleStatus 定义",
        "activation": "always — 数据结构定义",
    },
    "event_bus": {
        "tier": TIER_ACTIVE,
        "path": "src/core/event_bus.py",
        "description": "进程内事件发布-订阅总线",
        "activation": "always — ResearchPipeline.__init__",
    },
    "module_factory": {
        "tier": TIER_ACTIVE,
        "path": "src/core/module_factory.py",
        "description": "轻量依赖注入容器",
        "activation": "always — ResearchPipeline.__init__",
    },
    "quality_assessor": {
        "tier": TIER_ACTIVE,
        "path": "src/quality/quality_assessor.py",
        "description": "阶段质量评估（QualityScore / ComplianceReport）",
        "activation": "always — ResearchPipeline._bootstrap_quality",
    },
    "hypothesis_engine": {
        "tier": TIER_ACTIVE,
        "path": "src/research/hypothesis_engine.py",
        "description": "假说引擎",
        "activation": "always — hypothesis phase",
    },
    "gap_analyzer": {
        "tier": TIER_ACTIVE,
        "path": "src/research/gap_analyzer.py",
        "description": "研究空白分析",
        "activation": "always — analyze phase",
    },
    "audit_history": {
        "tier": TIER_ACTIVE,
        "path": "src/research/audit_history.py",
        "description": "审计轨迹记录",
        "activation": "always — 事件总线订阅",
    },
    "learning_strategy": {
        "tier": TIER_ACTIVE,
        "path": "src/research/learning_strategy.py",
        "description": "学习策略解析与追踪（StrategyApplicationTracker）",
        "activation": "always — 每个阶段的 context 注入",
    },
    "learning_loop_orchestrator": {
        "tier": TIER_ACTIVE,
        "path": "src/research/learning_loop_orchestrator.py",
        "description": "学习闭环编排器",
        "activation": "always — ResearchRuntimeService.orchestrate()",
    },
    "evidence_contract": {
        "tier": TIER_ACTIVE,
        "path": "src/research/evidence_contract.py",
        "description": "统一证据对象（EvidenceEnvelope / EvidenceRecord / EvidenceClaim）",
        "activation": "always — analyze phase 产出 evidence_protocol",
    },
    "evidence_chain_contract": {
        "tier": TIER_ACTIVE,
        "path": "src/research/evidence_chain_contract.py",
        "description": "考据证据链合同（文献学 claim 三分类）",
        "activation": "always — textual_evidence_chain 消费",
    },
    "learning_feedback_contract": {
        "tier": TIER_ACTIVE,
        "path": "src/research/learning_feedback_contract.py",
        "description": "学习反馈库合同",
        "activation": "always — reflect phase 产出",
    },
    "dossier_builder": {
        "tier": TIER_ACTIVE,
        "path": "src/research/dossier_builder.py",
        "description": "研究 dossier 构建（长上下文压缩）",
        "activation": "always — complete_research_cycle",
    },
    "phase_result": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phase_result.py",
        "description": "阶段结果标准化构建器",
        "activation": "always — 所有阶段返回值构建",
    },
    # ── 7 个阶段处理器 ──
    "phase_observe": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/observe_phase.py",
        "description": "观察阶段 — 语料采集与文献检索",
        "activation": "always — 默认阶段序列",
    },
    "phase_hypothesis": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/hypothesis_phase.py",
        "description": "假说阶段 — 从观察生成研究假说",
        "activation": "always — 默认阶段序列",
    },
    "phase_experiment": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/experiment_phase.py",
        "description": "实验设计阶段",
        "activation": "always — 默认阶段序列",
    },
    "phase_experiment_execution": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/experiment_execution_phase.py",
        "description": "实验执行阶段",
        "activation": "always — 默认阶段序列",
    },
    "phase_analyze": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/analyze_phase.py",
        "description": "分析阶段 — 统计/证据/推理",
        "activation": "always — 默认阶段序列",
    },
    "phase_publish": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/publish_phase.py",
        "description": "发表阶段 — 报告/论文/引用",
        "activation": "always — 默认阶段序列",
    },
    "phase_reflect": {
        "tier": TIER_ACTIVE,
        "path": "src/research/phases/reflect_phase.py",
        "description": "反思阶段 — 质量评估与学习反馈",
        "activation": "always — 默认阶段序列",
    },
    # ── 存储层 ──
    "storage_backend_factory": {
        "tier": TIER_ACTIVE,
        "path": "src/storage/__init__.py",
        "description": "存储后端工厂（PostgreSQL / SQLite 自动选择）",
        "activation": "always — ResearchRuntimeService._initialize_storage_factory",
    },
    "database_schema": {
        "tier": TIER_ACTIVE,
        "path": "src/storage/database_schema.py",
        "description": "ORM schema 定义与迁移",
        "activation": "always — StorageBackendFactory 初始化",
    },
    "transaction": {
        "tier": TIER_ACTIVE,
        "path": "src/storage/transaction.py",
        "description": "PG/Neo4j 双写事务协调",
        "activation": "always — phase_orchestrator persist 路径",
    },
    # ── Web 层 ──
    "web_app": {
        "tier": TIER_ACTIVE,
        "path": "src/web/app.py",
        "description": "FastAPI Web 应用",
        "activation": "always — uvicorn 启动",
    },
    "web_routes_research": {
        "tier": TIER_ACTIVE,
        "path": "src/web/routes/research.py",
        "description": "研究 API 路由",
        "activation": "always — app.include_router",
    },
    "web_routes_dashboard": {
        "tier": TIER_ACTIVE,
        "path": "src/web/routes/dashboard.py",
        "description": "Dashboard 看板路由",
        "activation": "always — app.include_router",
    },

    # ━━━ OPTIONAL: 需要配置标志或外部依赖 ━━━━━━━━━━━━━━━━━━━━━━━━━
    "self_learning_engine": {
        "tier": TIER_OPTIONAL,
        "path": "src/learning/self_learning_engine.py",
        "description": "自学习引擎（模式识别 + 自适应调参）",
        "activation": "config: self_learning.enabled = true",
    },
    "pattern_recognizer": {
        "tier": TIER_OPTIONAL,
        "path": "src/learning/pattern_recognizer.py",
        "description": "学习模式识别器",
        "activation": "随 self_learning_engine 激活",
    },
    "adaptive_tuner": {
        "tier": TIER_OPTIONAL,
        "path": "src/learning/adaptive_tuner.py",
        "description": "自适应参数调优器",
        "activation": "随 self_learning_engine 激活",
    },
    "llm_engine": {
        "tier": TIER_OPTIONAL,
        "path": "src/llm/llm_engine.py",
        "description": "本地 LLM 推理引擎（llama-cpp）",
        "activation": "_try_import — 若依赖不可用则跳过",
    },
    "cached_llm_service": {
        "tier": TIER_OPTIONAL,
        "path": "src/infra/llm_service.py",
        "description": "LLM 缓存服务（get_llm_service 入口）",
        "activation": "_try_import — 懒加载单例",
    },
    "citation_manager": {
        "tier": TIER_OPTIONAL,
        "path": "src/generation/citation_manager.py",
        "description": "引用管理（BibTeX / GB/T 7714）",
        "activation": "publish phase: generate_paper flag",
    },
    "paper_writer": {
        "tier": TIER_OPTIONAL,
        "path": "src/generation/paper_writer.py",
        "description": "论文生成器",
        "activation": "publish phase: generate_paper flag",
    },
    "output_generator": {
        "tier": TIER_OPTIONAL,
        "path": "src/generation/output_formatter.py",
        "description": "输出格式化器",
        "activation": "_try_import — publish phase",
    },
    "report_generator": {
        "tier": TIER_OPTIONAL,
        "path": "src/generation/report_generator.py",
        "description": "报告生成器",
        "activation": "_try_import — publish phase: generate_reports flag",
    },
    "llm_context_adapter": {
        "tier": TIER_OPTIONAL,
        "path": "src/generation/llm_context_adapter.py",
        "description": "LLM 上下文适配器",
        "activation": "随 paper_writer 激活",
    },
    "neo4j_driver": {
        "tier": TIER_OPTIONAL,
        "path": "src/storage/neo4j_driver.py",
        "description": "Neo4j 图数据库驱动",
        "activation": "config: neo4j.enabled = true",
    },
    "philology_service": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/philology_service.py",
        "description": "文献学服务（校勘/辑佚/训诂）",
        "activation": "_try_import — observe phase 条件调用",
    },
    "entity_extractor": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/entity_extractor.py",
        "description": "高级实体抽取器",
        "activation": "_try_import — observe/analyze phase",
    },
    "document_preprocessor": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/preprocessor.py",
        "description": "文档预处理器",
        "activation": "_try_import — observe phase",
    },
    "semantic_graph_builder": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/semantic_graph.py",
        "description": "语义图构建器",
        "activation": "_try_import + fallback stub — observe phase: run_ingestion",
    },
    "reasoning_engine": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/reasoning_engine.py",
        "description": "推理引擎",
        "activation": "_try_import + fallback stub — analyze phase",
    },
    "evidence_grader": {
        "tier": TIER_OPTIONAL,
        "path": "src/quality/evidence_grader.py",
        "description": "GRADE 证据评级",
        "activation": "try/except — analyze phase",
    },
    "textual_evidence_chain": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/textual_evidence_chain.py",
        "description": "考据证据链构建",
        "activation": "analyze phase 条件调用",
    },
    "tcm_knowledge_graph": {
        "tier": TIER_OPTIONAL,
        "path": "src/knowledge/tcm_knowledge_graph.py",
        "description": "中医知识图谱",
        "activation": "依赖 Neo4j — config: neo4j.enabled",
    },
    "kg_query_engine": {
        "tier": TIER_OPTIONAL,
        "path": "src/knowledge/kg_query_engine.py",
        "description": "知识图谱查询引擎",
        "activation": "依赖 Neo4j",
    },
    "embedding_service": {
        "tier": TIER_OPTIONAL,
        "path": "src/knowledge/embedding_service.py",
        "description": "向量嵌入服务（FAISS）",
        "activation": "依赖 sentence-transformers",
    },
    "local_collector": {
        "tier": TIER_OPTIONAL,
        "path": "src/collector/local_collector.py",
        "description": "本地语料采集器",
        "activation": "observe phase: collect_local flag",
    },
    "ctext_corpus_collector": {
        "tier": TIER_OPTIONAL,
        "path": "src/collector/ctext_corpus_collector.py",
        "description": "CText 在线语料采集器",
        "activation": "observe phase: collect_ctext flag",
    },
    "literature_retriever": {
        "tier": TIER_OPTIONAL,
        "path": "src/collector/literature_retriever.py",
        "description": "学术文献检索（PubMed / arXiv / Semantic Scholar 等）",
        "activation": "observe phase: run_literature_retrieval flag",
    },
    "format_converter": {
        "tier": TIER_OPTIONAL,
        "path": "src/collector/format_converter.py",
        "description": "格式转换（PDF / EPUB / HTML → Markdown）",
        "activation": "observe phase 按需调用",
    },

    # ━━━ DORMANT: 未接入活跃管线 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "cycle_research_session": {
        "tier": TIER_DORMANT,
        "path": "src/cycle/cycle_research_session.py",
        "description": "Demo 研究会话包装（薄包装层）",
        "activation": "none — demo entry point only",
    },
    "cycle_cli": {
        "tier": TIER_DORMANT,
        "path": "src/cycle/cycle_cli.py",
        "description": "CLI Demo 工具",
        "activation": "none — demo only",
    },
    "research_orchestrator_deprecated": {
        "tier": TIER_DORMANT,
        "path": "src/orchestration/research_orchestrator.py",
        "description": "已弃用编排器（发出 DeprecationWarning）",
        "activation": "none — deprecated, 仅为兼容导入保留",
    },
    "api_app_standalone": {
        "tier": TIER_DORMANT,
        "path": "src/api/app.py",
        "description": "独立 REST API 应用（与 Web Console 分离）",
        "activation": "none — 当前 Web Console 使用 src/web/app.py",
    },
    "graph_renderer": {
        "tier": TIER_DORMANT,
        "path": "src/visualization/graph_renderer.py",
        "description": "图渲染可视化",
        "activation": "none — 独立工具，未接入管线",
    },
    "network_pharmacology": {
        "tier": TIER_DORMANT,
        "path": "src/analysis/network_pharmacology.py",
        "description": "网络药理学分析",
        "activation": "none — 模块存在但未被任何阶段调用",
    },
    "supramolecular": {
        "tier": TIER_DORMANT,
        "path": "src/analysis/supramolecular.py",
        "description": "超分子结构分析",
        "activation": "none — 模块存在但未被任何阶段调用",
    },
    "complexity_dynamics": {
        "tier": TIER_DORMANT,
        "path": "src/analysis/complexity_dynamics.py",
        "description": "复杂性动力学分析",
        "activation": "none — 模块存在但未被任何阶段调用",
    },
    "knowledge_archaeology": {
        "tier": TIER_OPTIONAL,
        "path": "src/analysis/knowledge_archaeology.py",
        "description": "知识考古分析",
        "activation": "analyze phase 条件调用 — 依赖上下文标志",
    },
}

# ---------------------------------------------------------------------------
# 查询 API
# ---------------------------------------------------------------------------


def get_modules_by_tier(tier: str) -> List[Dict[str, Any]]:
    """返回指定层级的所有模块条目。"""
    if tier not in VALID_TIERS:
        raise ValueError(f"无效层级: {tier}，有效值: {VALID_TIERS}")
    return [
        {"module_key": key, **entry}
        for key, entry in MODULE_MANIFEST.items()
        if entry["tier"] == tier
    ]


def get_manifest_summary() -> Dict[str, Any]:
    """返回清单汇总统计。"""
    counts: Dict[str, int] = {t: 0 for t in VALID_TIERS}
    for entry in MODULE_MANIFEST.values():
        tier = entry.get("tier", "")
        if tier in counts:
            counts[tier] += 1
    return {
        "total": len(MODULE_MANIFEST),
        "counts": counts,
        "tiers": sorted(VALID_TIERS),
    }


def validate_manifest_paths(workspace_root: str = ".") -> List[Dict[str, Any]]:
    """验证清单中所有模块路径是否存在。返回不存在的条目列表。"""
    import os

    missing: List[Dict[str, Any]] = []
    for key, entry in MODULE_MANIFEST.items():
        full_path = os.path.join(workspace_root, entry["path"])
        if not os.path.isfile(full_path):
            missing.append({"module_key": key, "path": entry["path"], "tier": entry["tier"]})
    return missing
