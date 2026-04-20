"""知识缺口驱动的研究假设生成引擎。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from src.core.module_base import BaseModule
from src.infra.llm_service import prepare_planned_llm_call
from src.infra.prompt_registry import (
	call_registered_prompt,
	parse_registered_output,
	render_prompt,
)
from src.research.compute_tier_router import ComputeTierRouter, TierDecision
from src.research.learning_strategy import (
	has_learning_strategy,
	resolve_learning_strategy,
	resolve_numeric_learning_parameter,
)
from src.storage.graph_interface import IKnowledgeGraph, KnowledgeGap
from src.storage.neo4j_driver import create_knowledge_graph

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
	"""单条研究假设。"""

	hypothesis_id: str
	title: str
	statement: str
	rationale: str
	novelty: float
	feasibility: float
	evidence_support: float
	confidence: float
	source_gap_type: str
	source_entities: List[str] = field(default_factory=list)
	validation_plan: str = ""
	keywords: List[str] = field(default_factory=list)
	generation_mode: str = "rule"
	domain: str = "integrative_research"
	status: str = "draft"
	supporting_signals: List[str] = field(default_factory=list)
	contradiction_signals: List[str] = field(default_factory=list)
	final_score: float = 0.0
	scores: Dict[str, float] = field(default_factory=dict)

	def to_dict(self) -> Dict[str, Any]:
		return {
			"hypothesis_id": self.hypothesis_id,
			"title": self.title,
			"statement": self.statement,
			"rationale": self.rationale,
			"novelty": self.novelty,
			"feasibility": self.feasibility,
			"evidence_support": self.evidence_support,
			"confidence": self.confidence,
			"source_gap_type": self.source_gap_type,
			"source_entities": self.source_entities,
			"validation_plan": self.validation_plan,
			"keywords": self.keywords,
			"generation_mode": self.generation_mode,
			"domain": self.domain,
			"status": self.status,
			"supporting_signals": self.supporting_signals,
			"contradiction_signals": self.contradiction_signals,
			"final_score": self.final_score,
			"scores": self.scores,
		}


class HypothesisEngine(BaseModule):
	"""基于知识图谱缺口与 LLM 的假设生成引擎。"""

	DEFAULT_SYSTEM_PROMPT = (
		"你是中医科研假设生成专家。"
		"请基于知识图谱缺口、文献线索和上下文，提出可验证、具备创新性的科研假设。"
		"禁止编造不存在的证据，输出必须聚焦中医药研究场景。"
	)

	DEFAULT_HYPOTHESIS_PROMPT = """请围绕以下知识缺口生成 3 条中医科研假设。

知识缺口类型：{gap_type}
核心实体：{entities}
缺口描述：{description}
上下文摘要：{context_summary}

输出 JSON 数组，每个元素必须包含：
- title
- statement
- rationale
- novelty
- feasibility
- evidence_support
- validation_plan
- keywords

评分要求：novelty、feasibility、evidence_support 使用 0 到 1 的浮点数。
"""

	KG_ENHANCED_PROMPT = """你是中医科研假设生成专家。请基于以下知识图谱缺口分析生成高质量研究假设。

## 知识图谱缺口分析

共发现 {gap_count} 个知识缺口：
{gap_details}

## 图谱结构摘要

{kg_structure_summary}

## 研究上下文

{context_summary}

## 要求

请基于上述图谱缺口和结构信息，生成 {num_hypotheses} 条可验证的中医科研假设。
每条假设应：
1. 直接回应一个或多个知识缺口
2. 利用图谱中已有的结构线索
3. 提出可检验的机制解释

输出 JSON 数组，每个元素必须包含：
- title: 假设标题
- statement: 假设声明
- rationale: 论据（须引用图谱证据）
- novelty: 创新性评分 (0-1)
- feasibility: 可行性评分 (0-1)
- evidence_support: 证据支持评分 (0-1)
- validation_plan: 验证方案
- keywords: 关键词列表
- source_gap_type: 对应的缺口类型
- source_entities: 涉及的实体列表
"""

	DEFAULT_SCORE_WEIGHTS = {
		"novelty": 0.35,
		"feasibility": 0.25,
		"evidence_support": 0.25,
		"mechanism_completeness": 0.15,
	}

	def __init__(
		self,
		config: Optional[Dict[str, Any]] = None,
		llm_engine: Any = None,
		knowledge_graph: Optional[IKnowledgeGraph] = None,
	) -> None:
		super().__init__("research_hypothesis_engine", config)
		self.llm_engine = llm_engine
		self.knowledge_graph = knowledge_graph or create_knowledge_graph(
			self.config, preload_formulas=False
		)
		self.base_max_hypotheses = int(self.config.get("max_hypotheses", 5))
		self.max_hypotheses = self.base_max_hypotheses
		self.score_weights = {
			**self.DEFAULT_SCORE_WEIGHTS,
			**(self.config.get("score_weights") or {}),
		}
		self.minimum_confidence = float(self.config.get("minimum_confidence", 0.0))
		self.minimum_evidence_support = float(self.config.get("minimum_evidence_support", 0.0))
		self.active_confidence_threshold = float(self.config.get("active_confidence_threshold", 0.65))
		self.validation_confidence_threshold = float(self.config.get("validation_confidence_threshold", 0.8))
		self.system_prompt = str(self.config.get("system_prompt") or self.DEFAULT_SYSTEM_PROMPT)
		self.prompt_template = str(
			self.config.get("hypothesis_prompt_template") or self.DEFAULT_HYPOTHESIS_PROMPT
		)

	def _do_initialize(self) -> bool:
		self.logger.info("HypothesisEngine 初始化完成")
		return True

	def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		self._last_small_model_plan = None
		self._last_llm_cost_report = None
		self._last_fallback_path = None
		knowledge_gap = context.get("knowledge_gap")
		runtime_graph = context.get("knowledge_graph")
		previous_graph = self.knowledge_graph
		if isinstance(runtime_graph, IKnowledgeGraph):
			self.knowledge_graph = runtime_graph

		try:
			hypotheses = self.generate_hypotheses(knowledge_gap=knowledge_gap, context=context)
			ranked = self._enrich_hypotheses(self.rank_hypotheses(hypotheses, context), context)
		finally:
			self.knowledge_graph = previous_graph

		top_hypothesis = ranked[0] if ranked else None
		used_llm_generation = any(item.generation_mode in ("llm", "kg_enhanced") for item in ranked)
		used_kg_enhanced = any(item.generation_mode == "kg_enhanced" for item in ranked)
		return {
			"phase": "hypothesis",
			"hypotheses": [item.to_dict() for item in ranked],
			"validation_iterations": [],
			"domain": str(context.get("research_domain") or "integrative_research"),
			"metadata": {
				"hypothesis_count": len(ranked),
				"generation_mode": ranked[0].generation_mode if ranked else "rule",
				"has_llm": self.llm_engine is not None,
				"validation_iteration_count": 0,
				"selected_hypothesis_id": top_hypothesis.hypothesis_id if top_hypothesis else "",
				"used_llm_generation": used_llm_generation,
				"used_kg_enhanced": used_kg_enhanced,
				"used_llm_closed_loop": False,
				"llm_iteration_count": 0,
				"research_direction": top_hypothesis.title if top_hypothesis else str(context.get("research_objective") or ""),
				"small_model_plan": self._last_small_model_plan,
				"llm_cost_report": self._last_llm_cost_report,
				"fallback_path": self._last_fallback_path,
			},
		}

	def _do_cleanup(self) -> bool:
		self.logger.info("HypothesisEngine 清理完成")
		return True

	def generate_hypotheses(
		self,
		knowledge_gap: Any,
		context: Optional[Dict[str, Any]] = None,
	) -> List[Hypothesis]:
		prepared_context = context or {}
		gap = self._normalize_gap(knowledge_gap, prepared_context)
		active_llm_engine = self._resolve_llm_engine(prepared_context)

		# --- 动态算力分配：评估是否需要 LLM ---
		tier_decision = self._evaluate_compute_tier(prepared_context, gap)
		if not tier_decision.should_use_llm:
			self.logger.info(
				"算力路由: 跳过 LLM (tier=%s, reason=%s)",
				tier_decision.tier.name, tier_decision.reason,
			)
			return self._enrich_hypotheses(
				self.rank_hypotheses(self._generate_with_rules(gap, prepared_context), prepared_context),
				prepared_context,
			)

		# --- P3.2 KG 增强路径 ---
		if active_llm_engine is not None:
			kg_gaps = self.extract_kg_gaps(prepared_context)
			if kg_gaps:
				kg_hypotheses = self._generate_kg_enhanced(
					kg_gaps, gap, prepared_context, active_llm_engine,
				)
				if kg_hypotheses:
					return self._enrich_hypotheses(
						self.rank_hypotheses(kg_hypotheses, prepared_context), prepared_context,
					)

		# --- 原有 LLM 路径 ---
		if active_llm_engine is not None:
			llm_hypotheses = self._generate_with_llm(gap, prepared_context, active_llm_engine)
			if llm_hypotheses:
				return self._enrich_hypotheses(self.rank_hypotheses(llm_hypotheses, prepared_context), prepared_context)
		return self._enrich_hypotheses(
			self.rank_hypotheses(self._generate_with_rules(gap, prepared_context), prepared_context),
			prepared_context,
		)

	def rank_hypotheses(
		self,
		hypotheses: List[Hypothesis],
		context: Optional[Dict[str, Any]] = None,
	) -> List[Hypothesis]:
		ranked = list(hypotheses)
		score_weights = self._resolve_hypothesis_score_weights(context or {})
		for item in ranked:
			mechanism_completeness = item.scores.get("mechanism_completeness", 0.0)
			item.confidence = round(
				item.novelty * score_weights["novelty"]
				+ item.feasibility * score_weights["feasibility"]
				+ item.evidence_support * score_weights["evidence_support"]
				+ mechanism_completeness * score_weights["mechanism_completeness"],
				4,
			)
		ranked.sort(key=lambda item: item.confidence, reverse=True)
		return ranked[: self._resolve_hypothesis_max_hypotheses(context or {})]

	def _resolve_hypothesis_score_weights(self, context: Dict[str, Any]) -> Dict[str, float]:
		weights = dict(self.score_weights)
		strategy = resolve_learning_strategy(context, self.config)
		strategy_weights = strategy.get("score_weights") or {}
		if isinstance(strategy_weights, dict):
			for key, value in strategy_weights.items():
				if key not in weights:
					continue
				try:
					weights[key] = max(0.0, float(value))
				except (TypeError, ValueError):
					continue

		total_weight = sum(weights.values())
		if total_weight <= 0:
			return dict(self.DEFAULT_SCORE_WEIGHTS)
		return {
			key: round(value / total_weight, 6)
			for key, value in weights.items()
		}

	def _resolve_hypothesis_max_hypotheses(self, context: Dict[str, Any]) -> int:
		explicit_max_hypotheses = context.get("max_hypotheses")
		if explicit_max_hypotheses is not None:
			try:
				return max(1, min(int(explicit_max_hypotheses), 10))
			except (TypeError, ValueError):
				pass

		if not has_learning_strategy(context, self.config):
			return self.base_max_hypotheses

		quality_threshold = resolve_numeric_learning_parameter(
			"quality_threshold",
			0.7,
			context,
			self.config,
			min_value=0.3,
			max_value=0.95,
		)
		if quality_threshold >= 0.82:
			return max(2, self.base_max_hypotheses - 1)
		if quality_threshold <= 0.55:
			return min(8, self.base_max_hypotheses + 1)
		return self.base_max_hypotheses

	def _resolve_minimum_hypothesis_confidence(self, context: Dict[str, Any]) -> float:
		base_value = max(0.0, min(1.0, self.minimum_confidence))
		if not has_learning_strategy(context, self.config):
			return base_value

		confidence_threshold = resolve_numeric_learning_parameter(
			"confidence_threshold",
			0.7,
			context,
			self.config,
			min_value=0.0,
			max_value=1.0,
		)
		return round(max(base_value, confidence_threshold - 0.05), 4)

	def _resolve_minimum_evidence_support(self, context: Dict[str, Any]) -> float:
		base_value = max(0.0, min(1.0, self.minimum_evidence_support))
		if not has_learning_strategy(context, self.config):
			return base_value

		quality_threshold = resolve_numeric_learning_parameter(
			"quality_threshold",
			0.7,
			context,
			self.config,
			min_value=0.3,
			max_value=0.95,
		)
		return round(max(base_value, min(0.85, 0.2 + quality_threshold * 0.45)), 4)

	def _resolve_status_thresholds(self, context: Dict[str, Any]) -> tuple[float, float]:
		validated_threshold = self.validation_confidence_threshold
		active_threshold = self.active_confidence_threshold
		if not has_learning_strategy(context, self.config):
			return validated_threshold, active_threshold

		confidence_threshold = resolve_numeric_learning_parameter(
			"confidence_threshold",
			0.7,
			context,
			self.config,
			min_value=0.0,
			max_value=1.0,
		)
		active_threshold = round(max(active_threshold, min(0.85, confidence_threshold)), 4)
		validated_threshold = round(max(validated_threshold, min(0.95, active_threshold + 0.1)), 4)
		return validated_threshold, active_threshold

	def _generate_with_llm(
		self,
		gap: Dict[str, Any],
		context: Dict[str, Any],
		llm_engine: Any,
	) -> List[Hypothesis]:
		if not hasattr(llm_engine, "generate"):
			return []

		planned_call = prepare_planned_llm_call(
			phase="hypothesis",
			task_type="hypothesis_generation",
			purpose="hypothesis",
			dossier_sections=self._build_hypothesis_dossier_sections(gap, context),
			llm_engine=llm_engine,
			template_preferences=self._extract_template_preferences(context),
		)
		self._record_planned_call(planned_call)
		if not planned_call.should_call_llm:
			return []

		template_override = None
		if self.prompt_template != self.DEFAULT_HYPOTHESIS_PROMPT:
			template_override = self.prompt_template

		rendered = render_prompt(
			"hypothesis_engine.default_hypothesis",
			system_prompt_override=self.system_prompt,
			user_template_override=template_override,
			gap_type=gap["gap_type"],
			entities="、".join(gap["entities"]) or gap["entity"],
			description=gap["description"],
			context_summary=self._build_context_summary(context),
		)
		try:
			raw = call_registered_prompt(
				planned_call.create_proxy(),
				"hypothesis_engine.default_hypothesis",
				rendered=rendered,
			)
		except Exception as exc:
			self.logger.warning("LLM 假设生成失败，回退规则引擎: %s", exc)
			return []
		return self._parse_llm_response(
			raw,
			gap,
			prompt_name="hypothesis_engine.default_hypothesis",
			generation_mode="llm",
		)

	def _parse_llm_response(
		self,
		raw: Any,
		gap: Dict[str, Any],
		*,
		prompt_name: str = "hypothesis_engine.default_hypothesis",
		generation_mode: str = "llm",
		allowed_gap_types: Optional[set[str]] = None,
	) -> List[Hypothesis]:
		validation = parse_registered_output(prompt_name, raw)
		if isinstance(validation.parsed, list):
			payload = validation.parsed
		elif isinstance(raw, list):
			payload = raw
		elif isinstance(raw, dict):
			payload = raw.get("hypotheses") or raw.get("items") or [raw]
		else:
			text = str(raw or "").strip()
			if not text:
				return []
			if text.startswith("```"):
				lines = text.splitlines()
				if len(lines) >= 3:
					text = "\n".join(lines[1:-1]).strip()
			try:
				payload = json.loads(text)
			except Exception:
				return []

		hypotheses: List[Hypothesis] = []
		for item in payload:
			if not isinstance(item, dict):
				continue
			statement = str(item.get("statement") or "").strip()
			if not statement:
				continue
			title = str(item.get("title") or statement[:30]).strip()
			novelty = self._normalize_score(item.get("novelty"), default=0.75)
			feasibility = self._normalize_score(item.get("feasibility"), default=0.7)
			evidence_support = self._normalize_score(item.get("evidence_support"), default=0.65)
			validation_plan = str(
				item.get("validation_plan")
				or "通过知识图谱补边、文献回溯和专家复核验证该假设。"
			).strip()
			keywords = self._ensure_text_list(item.get("keywords"))
			returned_gap_type = str(item.get("source_gap_type") or "").strip()
			if returned_gap_type and (allowed_gap_types is None or returned_gap_type in allowed_gap_types):
				source_gap_type = returned_gap_type
			else:
				source_gap_type = gap["gap_type"]
			source_entities = self._ensure_text_list(item.get("source_entities")) or gap["entities"]
			hypotheses.append(
				self._build_hypothesis(
					title=title,
					statement=statement,
					rationale=str(item.get("rationale") or gap["description"]).strip(),
					source_gap_type=source_gap_type,
					source_entities=source_entities,
					validation_plan=validation_plan,
					keywords=keywords or self._extract_keywords([title, statement]),
					novelty=novelty,
					feasibility=feasibility,
					evidence_support=evidence_support,
					generation_mode=generation_mode,
				)
			)
		return hypotheses

	# ------------------------------------------------------------------ #
	# P3.2  KG 增强假设生成
	# ------------------------------------------------------------------ #

	def extract_kg_gaps(self, context: Dict[str, Any]) -> List[KnowledgeGap]:
		"""从知识图谱提取知识缺口列表。

		优先使用 context 中的运行时 KG，回退到 self.knowledge_graph。
		"""
		graph = context.get("knowledge_graph") or self.knowledge_graph
		try:
			gaps = graph.find_gaps()
		except Exception as exc:
			self.logger.warning("KG 缺口提取失败: %s", exc)
			return []
		if not gaps:
			return []
		# 按严重度排序：high > medium > low
		severity_order = {"high": 0, "medium": 1, "low": 2}
		gaps.sort(key=lambda g: severity_order.get(g.severity, 3))
		return gaps

	def _generate_kg_enhanced(
		self,
		kg_gaps: List[KnowledgeGap],
		fallback_gap: Dict[str, Any],
		context: Dict[str, Any],
		llm_engine: Any,
	) -> List[Hypothesis]:
		"""用 KG 缺口 + 图谱结构组装增强 prompt，调用 LLM 生成假设。"""
		if not hasattr(llm_engine, "generate"):
			return []

		gap_details = self._format_kg_gaps(kg_gaps)
		kg_summary = self._build_kg_structure_summary(kg_gaps, context)
		context_summary = self._build_context_summary(context)
		planned_call = prepare_planned_llm_call(
			phase="hypothesis",
			task_type="hypothesis_generation",
			purpose="hypothesis",
			dossier_sections={
				"objective": str(context.get("research_objective") or "").strip(),
				"kg_gap_details": gap_details,
				"kg_structure_summary": kg_summary,
				"context_summary": context_summary,
			},
			llm_engine=llm_engine,
			template_preferences=self._extract_template_preferences(context),
		)
		self._record_planned_call(planned_call)
		if not planned_call.should_call_llm:
			return []

		rendered = render_prompt(
			"hypothesis_engine.kg_enhanced",
			system_prompt_override=self.system_prompt,
			gap_count=len(kg_gaps),
			gap_details=gap_details,
			kg_structure_summary=kg_summary,
			context_summary=context_summary,
			num_hypotheses=min(self.max_hypotheses, max(3, len(kg_gaps))),
		)

		try:
			raw = call_registered_prompt(
				planned_call.create_proxy(),
				"hypothesis_engine.kg_enhanced",
				rendered=rendered,
			)
		except Exception as exc:
			self.logger.warning("KG 增强 LLM 生成失败，回退: %s", exc)
			return []

		return self._parse_kg_enhanced_response(raw, kg_gaps, fallback_gap)

	def _format_kg_gaps(self, gaps: List[KnowledgeGap]) -> str:
		"""将知识缺口列表格式化为 prompt 文本。"""
		lines: List[str] = []
		for i, gap in enumerate(gaps[:10], 1):  # 最多 10 个避免 prompt 过长
			lines.append(
				f"{i}. [{gap.severity.upper()}] {gap.gap_type}: "
				f"{gap.entity} ({gap.entity_type}) — {gap.description}"
			)
		return "\n".join(lines)

	def _build_kg_structure_summary(
		self,
		gaps: List[KnowledgeGap],
		context: Dict[str, Any],
	) -> str:
		"""围绕缺口实体构建图谱结构摘要。"""
		graph = context.get("knowledge_graph") or self.knowledge_graph
		parts: List[str] = []

		# 实体统计
		try:
			if hasattr(graph, "entity_count"):
				parts.append(f"图谱节点数: {graph.entity_count}，边数: {graph.relation_count}")
		except Exception:
			pass

		# 缺口实体的邻域信息
		seen_entities: set[str] = set()
		for gap in gaps[:5]:
			if gap.entity in seen_entities:
				continue
			seen_entities.add(gap.entity)
			try:
				subgraph = graph.get_subgraph(gap.entity, depth=1)
				neighbor_count = max(0, subgraph.number_of_nodes() - 1)
				if neighbor_count > 0:
					neighbor_names = [
						str(n) for n in subgraph.nodes
						if str(n) != gap.entity
					][:5]
					parts.append(
						f"「{gap.entity}」邻域: {neighbor_count} 个邻居 "
						f"({', '.join(neighbor_names)})"
					)
				else:
					parts.append(f"「{gap.entity}」无直接邻居")
			except Exception:
				pass

		# 缺口实体间的路径
		gap_entities = list({g.entity for g in gaps[:6]})
		for i in range(min(len(gap_entities), 3)):
			for j in range(i + 1, min(len(gap_entities), 4)):
				try:
					paths = graph.query_path(gap_entities[i], gap_entities[j])
					if paths:
						parts.append(
							f"路径: {gap_entities[i]} → {' → '.join(paths[0])} → {gap_entities[j]}"
						)
				except Exception:
					pass

		return "\n".join(parts) if parts else "图谱结构信息不足。"

	def _parse_kg_enhanced_response(
		self,
		raw: Any,
		kg_gaps: List[KnowledgeGap],
		fallback_gap: Dict[str, Any],
	) -> List[Hypothesis]:
		"""解析 KG 增强 prompt 的 LLM 响应。"""

		return self._parse_llm_response(
			raw,
			fallback_gap,
			prompt_name="hypothesis_engine.kg_enhanced",
			generation_mode="kg_enhanced",
			allowed_gap_types={g.gap_type for g in kg_gaps},
		)

	def _generate_with_rules(self, gap: Dict[str, Any], context: Dict[str, Any]) -> List[Hypothesis]:
		hypotheses: List[Hypothesis] = []
		hypotheses.extend(self._hypotheses_from_gap_type(gap, context))
		hypotheses.extend(self._hypotheses_from_graph_structure(gap, context))
		hypotheses.extend(self._hypotheses_from_context(gap, context))

		deduplicated: List[Hypothesis] = []
		seen: set[str] = set()
		for item in hypotheses:
			if item.statement in seen:
				continue
			seen.add(item.statement)
			deduplicated.append(item)
		while len(deduplicated) < min(self.max_hypotheses, 3):
			deduplicated.append(self._build_backfill_hypothesis(gap, context, len(deduplicated) + 1))
		return deduplicated[: max(self.max_hypotheses, 3)]

	def _hypotheses_from_gap_type(self, gap: Dict[str, Any], context: Dict[str, Any]) -> List[Hypothesis]:
		entity = gap["entity"]
		entities = gap["entities"] or [entity]
		gap_type = gap["gap_type"]
		entity_type = gap["entity_type"]
		context_keywords = self._extract_keywords(self._context_strings(context))

		if gap_type == "missing_direct_relation":
			return [
				self._build_hypothesis(
					title=f"{entities[0]} 与 {entities[-1]} 存在潜在直接关系",
					statement=(
						f"假设 {entities[0]} 与 {entities[-1]} 之间存在尚未显式建模的直接关系，"
						"该关系可能解释当前知识图谱中间接路径频繁出现的现象。"
					),
					rationale="图中已存在稳定间接路径但缺少直接边，适合优先提出关联补边假设。",
					source_gap_type=gap_type,
					source_entities=entities,
					validation_plan="检索相关文献与病例证据，验证两实体是否存在直接作用或共现关系。",
					keywords=entities + context_keywords[:2],
					novelty=0.84,
					feasibility=0.73,
					evidence_support=self._estimate_evidence_support(gap, context, bonus=0.08),
				),
				self._build_hypothesis(
					title=f"{entities[0]} 通过中介机制影响 {entities[-1]}",
					statement=(
						f"假设 {entities[0]} 对 {entities[-1]} 的影响依赖于尚未识别的中介机制或隐含实体，"
						"因此在知识图谱中表现为多跳路径而非直接连接。"
					),
					rationale="多跳路径通常提示存在中介节点或潜在机制层未被显式编码。",
					source_gap_type=gap_type,
					source_entities=entities,
					validation_plan="在现有路径节点基础上补充靶点、通路和功效证据，验证中介机制。",
					keywords=entities + ["中介机制"],
					novelty=0.81,
					feasibility=0.68,
					evidence_support=self._estimate_evidence_support(gap, context, bonus=0.05),
				),
			]

		if gap_type == "missing_downstream":
			return [
				self._build_hypothesis(
					title=f"{entity} 存在未识别的下游{self._next_level_name(entity_type)}关系",
					statement=(
						f"假设 {entity} 对应的 {self._next_level_name(entity_type)} 层实体尚未被系统抽取，"
						"补充该层关系后可显著提升机制解释完整性。"
					),
					rationale="层级断裂通常意味着证据存在但未被结构化编码。",
					source_gap_type=gap_type,
					source_entities=entities,
					validation_plan="围绕该实体定向抽取下游靶点、通路或证候证据，比较补边前后的路径覆盖率。",
					keywords=[entity, self._next_level_name(entity_type)],
					novelty=0.72,
					feasibility=0.86,
					evidence_support=self._estimate_evidence_support(gap, context, bonus=0.1),
				)
			]

		if gap_type == "orphan_entity":
			return [
				self._build_hypothesis(
					title=f"孤立实体 {entity} 具备可连接研究价值",
					statement=f"假设孤立实体 {entity} 并非真实孤立，而是由于文献抽取或关系标准化不足导致未接入现有图谱。",
					rationale="孤立节点往往是信息缺失而非真实无关，适合作为新知识发现入口。",
					source_gap_type=gap_type,
					source_entities=entities,
					validation_plan="回溯该实体在文献和知识库中的上下游关系，建立最可能的候选连接。",
					keywords=[entity, "关系补全"],
					novelty=0.78,
					feasibility=0.74,
					evidence_support=self._estimate_evidence_support(gap, context, bonus=0.04),
				)
			]

		if gap_type == "incomplete_composition":
			return [
				self._build_hypothesis(
					title=f"{entity} 的配伍角色存在遗漏",
					statement=f"假设方剂 {entity} 在君臣佐使角色中仍存在未标注药物，该遗漏会影响配伍机制与功效解释。",
					rationale="方剂组成缺口直接影响理论解释与实验设计的完整性。",
					source_gap_type=gap_type,
					source_entities=entities,
					validation_plan="结合古籍原文与现代方解资料，补充并验证缺失角色药物。",
					keywords=[entity, "君臣佐使", "配伍"],
					novelty=0.69,
					feasibility=0.88,
					evidence_support=self._estimate_evidence_support(gap, context, bonus=0.12),
				)
			]

		return [
			self._build_hypothesis(
				title=f"围绕 {entity} 的缺口驱动假设",
				statement=f"假设实体 {entity} 所对应的知识缺口可通过新增结构化证据获得机制性解释。",
				rationale=gap["description"],
				source_gap_type=gap_type,
				source_entities=entities,
				validation_plan="补充关系抽取和文献证据后重新评估假设。",
				keywords=[entity] + context_keywords[:2],
				novelty=0.66,
				feasibility=0.72,
				evidence_support=self._estimate_evidence_support(gap, context),
			)
		]

	def _hypotheses_from_graph_structure(self, gap: Dict[str, Any], context: Dict[str, Any]) -> List[Hypothesis]:
		entities = gap["entities"] or [gap["entity"]]
		if len(entities) >= 2:
			source, target = entities[0], entities[-1]
			paths = self.knowledge_graph.query_path(source, target)
			if paths:
				path = paths[0]
				return [
					self._build_hypothesis(
						title=f"{source} 到 {target} 的路径可压缩为关键机制",
						statement=f"假设 {source} 到 {target} 的现有路径中存在关键瓶颈节点，该节点决定了大部分作用机制与证据收敛方向。",
						rationale=f"当前图结构中已观察到路径 {' -> '.join(path)}，可进一步聚焦关键中介。",
						source_gap_type=gap["gap_type"],
						source_entities=entities,
						validation_plan="对路径中的中介节点做消融式证据检索，识别关键机制节点。",
						keywords=self._extract_keywords(path),
						novelty=0.77,
						feasibility=0.69,
						evidence_support=self._estimate_evidence_support(gap, context, bonus=0.06),
					)
				]

		subgraph = self.knowledge_graph.get_subgraph(gap["entity"], depth=2)
		if subgraph.number_of_nodes() >= 3:
			neighbor_names = [str(node) for node in subgraph.nodes if str(node) != gap["entity"]][:3]
			return [
				self._build_hypothesis(
					title=f"{gap['entity']} 周边子图存在未收敛机制",
					statement=f"假设 {gap['entity']} 周边子图中的实体 {', '.join(neighbor_names)} 共同指向同一潜在机制，但当前图谱尚未形成明确机制闭环。",
					rationale="局部子图已聚集多个相关节点，适合提出机制整合型假设。",
					source_gap_type=gap["gap_type"],
					source_entities=[gap["entity"]] + neighbor_names,
					validation_plan="联合分析局部子图关系类型与文献证据，验证是否存在统一机制主题。",
					keywords=[gap["entity"]] + neighbor_names,
					novelty=0.74,
					feasibility=0.71,
					evidence_support=self._estimate_evidence_support(gap, context, bonus=0.07),
				)
			]
		return []

	def _hypotheses_from_context(self, gap: Dict[str, Any], context: Dict[str, Any]) -> List[Hypothesis]:
		evidence = (
			self._ensure_text_list(context.get("observations"))
			+ self._ensure_text_list(context.get("findings"))
			+ self._ensure_text_list(context.get("literature_titles"))
		)
		if not evidence:
			return []

		summary_terms = self._extract_keywords(evidence)[:4]
		if not summary_terms:
			return []

		return [
			self._build_hypothesis(
				title=f"{gap['entity']} 与上下文证据的整合假设",
				statement=f"假设围绕 {gap['entity']} 的知识缺口与上下文中的 {', '.join(summary_terms[:2])} 线索具有一致的证据指向，可形成可检验的综合研究命题。",
				rationale="知识缺口需要与文献和观察线索合并，才能形成高价值研究假设。",
				source_gap_type=gap["gap_type"],
				source_entities=[gap["entity"]],
				validation_plan="按上下文证据类别分层验证，并比较不同来源证据的一致性。",
				keywords=[gap["entity"]] + summary_terms,
				novelty=0.71,
				feasibility=0.79,
				evidence_support=self._estimate_evidence_support(gap, context, bonus=0.09),
			)
		]

	def _normalize_gap(self, knowledge_gap: Any, context: Dict[str, Any]) -> Dict[str, Any]:
		if isinstance(knowledge_gap, KnowledgeGap):
			return {
				"gap_type": knowledge_gap.gap_type,
				"entity": knowledge_gap.entity,
				"entity_type": knowledge_gap.entity_type,
				"description": knowledge_gap.description,
				"severity": knowledge_gap.severity,
				"entities": [knowledge_gap.entity],
			}

		if isinstance(knowledge_gap, dict):
			entity = str(knowledge_gap.get("entity") or knowledge_gap.get("source") or "未知实体")
			entities = knowledge_gap.get("entities")
			if not isinstance(entities, list) or not entities:
				related = [knowledge_gap.get("source"), knowledge_gap.get("target"), entity]
				entities = [str(item) for item in related if item]
			return {
				"gap_type": str(knowledge_gap.get("gap_type") or "custom_gap"),
				"entity": entity,
				"entity_type": str(knowledge_gap.get("entity_type") or "generic"),
				"description": str(knowledge_gap.get("description") or "未命名知识缺口"),
				"severity": str(knowledge_gap.get("severity") or "medium"),
				"entities": [str(item) for item in entities if str(item).strip()],
			}

		gaps = self.knowledge_graph.find_gaps()
		if gaps:
			first_gap = gaps[0]
			return {
				"gap_type": first_gap.gap_type,
				"entity": first_gap.entity,
				"entity_type": first_gap.entity_type,
				"description": first_gap.description,
				"severity": first_gap.severity,
				"entities": [first_gap.entity],
			}

		fallback_entity = self._fallback_entity_from_context(context)
		return {
			"gap_type": "insufficient_graph_relation",
			"entity": fallback_entity,
			"entity_type": "generic",
			"description": f"围绕 {fallback_entity} 缺少足够图谱关系，需生成探索性假设。",
			"severity": "medium",
			"entities": [fallback_entity],
		}

	def _fallback_entity_from_context(self, context: Dict[str, Any]) -> str:
		entities = context.get("entities")
		if isinstance(entities, list):
			for item in entities:
				if isinstance(item, dict) and item.get("name"):
					return str(item["name"])
				if item:
					return str(item)
		objective = str(context.get("research_objective") or "研究对象")
		return objective[:20] if objective else "研究对象"

	def _evaluate_compute_tier(self, context: Dict[str, Any], gap: Dict[str, Any]) -> TierDecision:
		"""使用 ComputeTierRouter 评估当前假设生成是否需要 LLM。"""
		router = ComputeTierRouter(self.config)

		# 收集现有证据指标
		entities = context.get("entities") or []
		relationships = context.get("relationships") or []
		kg = context.get("knowledge_graph") or self.knowledge_graph
		kg_entity_count = 0
		if kg is not None and hasattr(kg, "entity_count"):
			try:
				kg_entity_count = kg.entity_count
			except Exception:
				pass

		evidence = {
			"entity_count": len(entities) + kg_entity_count,
			"relationship_count": len(relationships),
			"rule_confidence": float(context.get("inference_confidence") or 0.0),
			"retrieval_hits": len(context.get("literature_titles") or []),
			"evidence_items": len(context.get("observations") or []) + len(context.get("findings") or []),
			"has_rule_result": bool(context.get("reasoning_summary")),
		}

		return router.decide(
			task_type="hypothesis",
			evidence=evidence,
			force_tier=context.get("force_compute_tier"),
		)

	def _resolve_llm_engine(self, context: Dict[str, Any]) -> Any:
		if "use_llm_generation" in context and not context.get("use_llm_generation"):
			return None
		strategy = resolve_learning_strategy(context, self.config)
		if "use_llm_generation" not in context:
			if "hypothesis_use_llm_generation" in strategy and not strategy.get("hypothesis_use_llm_generation"):
				return None
			if "use_llm_generation" in strategy and not strategy.get("use_llm_generation"):
				return None
		return context.get("llm_service") or context.get("llm_engine") or self.llm_engine

	def _record_planned_call(self, planned_call: Any) -> None:
		if planned_call is None:
			return
		self._last_small_model_plan = planned_call.to_metadata()
		self._last_llm_cost_report = planned_call.get_cost_report()
		self._last_fallback_path = planned_call.fallback_path

	def _extract_template_preferences(self, context: Dict[str, Any]) -> Dict[str, float]:
		strategy = resolve_learning_strategy(context, self.config)
		preferences = strategy.get("template_preferences")
		return dict(preferences) if isinstance(preferences, dict) else {}

	def _build_hypothesis_dossier_sections(
		self,
		gap: Dict[str, Any],
		context: Dict[str, Any],
	) -> Dict[str, str]:
		entities = gap.get("entities") or []
		entity_names: List[str] = []
		for item in entities:
			if isinstance(item, dict):
				name = str(item.get("name") or "").strip()
			else:
				name = str(item or "").strip()
			if name:
				entity_names.append(name)
		observations = [str(item).strip() for item in (context.get("observations") or []) if str(item).strip()]
		findings = [str(item).strip() for item in (context.get("findings") or []) if str(item).strip()]
		literature_titles = [str(item).strip() for item in (context.get("literature_titles") or []) if str(item).strip()]
		reasoning_summary = context.get("reasoning_summary") or {}
		return {
			"objective": str(context.get("research_objective") or "").strip(),
			"knowledge_gap": str(gap.get("description") or "").strip(),
			"entities": "、".join(entity_names),
			"observations": "\n".join(observations[:8]),
			"findings": "\n".join(findings[:8]),
			"literature_titles": "\n".join(literature_titles[:10]),
			"reasoning_summary": json.dumps(reasoning_summary, ensure_ascii=False),
		}

	def _estimate_evidence_support(
		self,
		gap: Dict[str, Any],
		context: Dict[str, Any],
		bonus: float = 0.0,
	) -> float:
		evidence_count = len(self._context_strings(context))
		severity_bonus = {"high": 0.04, "medium": 0.02, "low": 0.0}.get(gap["severity"], 0.01)
		score = 0.48 + min(0.24, evidence_count * 0.03) + severity_bonus + bonus
		return round(min(0.95, score), 4)

	def _build_context_summary(self, context: Dict[str, Any]) -> str:
		parts: List[str] = []
		for key in ["research_objective", "research_scope"]:
			value = context.get(key)
			if value:
				parts.append(str(value))
		parts.extend(self._ensure_text_list(context.get("observations"))[:2])
		parts.extend(self._ensure_text_list(context.get("findings"))[:2])
		parts.extend(self._ensure_text_list(context.get("literature_titles"))[:2])
		# 推理框架指导（Self-Discover）
		reasoning_guidance = context.get("reasoning_guidance")
		if reasoning_guidance:
			parts.append(f"\n【推理框架指导】{reasoning_guidance}")
		if not parts:
			return "暂无额外上下文。"
		return "；".join(parts)

	def _context_strings(self, context: Dict[str, Any]) -> List[str]:
		strings: List[str] = []
		strings.extend(self._ensure_text_list(context.get("observations")))
		strings.extend(self._ensure_text_list(context.get("findings")))
		strings.extend(self._ensure_text_list(context.get("literature_titles")))
		if context.get("research_objective"):
			strings.append(str(context.get("research_objective")))
		if context.get("research_scope"):
			strings.append(str(context.get("research_scope")))
		return strings

	def _build_hypothesis(
		self,
		title: str,
		statement: str,
		rationale: str,
		source_gap_type: str,
		source_entities: List[str],
		validation_plan: str,
		keywords: List[str],
		novelty: float,
		feasibility: float,
		evidence_support: float,
		generation_mode: str = "rule",
	) -> Hypothesis:
		stable_text = "|".join([title, statement, source_gap_type, ",".join(source_entities), generation_mode])
		hypothesis_id = hashlib.md5(stable_text.encode("utf-8")).hexdigest()[:12]
		confidence = round(
			novelty * self.score_weights["novelty"]
			+ feasibility * self.score_weights["feasibility"]
			+ evidence_support * self.score_weights["evidence_support"],
			4,
		)
		return Hypothesis(
			hypothesis_id=hypothesis_id,
			title=title,
			statement=statement,
			rationale=rationale,
			novelty=round(novelty, 4),
			feasibility=round(feasibility, 4),
			evidence_support=round(evidence_support, 4),
			confidence=confidence,
			source_gap_type=source_gap_type,
			source_entities=source_entities,
			validation_plan=validation_plan,
			keywords=keywords,
			generation_mode=generation_mode,
			final_score=confidence,
			scores={
				"novelty": round(novelty, 4),
				"feasibility": round(feasibility, 4),
				"evidence_support": round(evidence_support, 4),
			},
		)

	def _build_backfill_hypothesis(
		self,
		gap: Dict[str, Any],
		context: Dict[str, Any],
		index: int,
	) -> Hypothesis:
		entity = gap["entity"]
		return self._build_hypothesis(
			title=f"{entity} 探索性补充假设 {index}",
			statement=f"假设围绕 {entity} 的知识缺口可通过补充文献与图谱关系形成新的可验证解释。",
			rationale="当图结构信号不足时，使用研究目标与上下文证据生成保守补充假设。",
			source_gap_type=gap["gap_type"],
			source_entities=gap["entities"],
			validation_plan="补充关系抽取、文献共现分析和专家复核后再次评估。",
			keywords=[entity] + self._extract_keywords(self._context_strings(context))[:2],
			novelty=0.63,
			feasibility=0.7,
			evidence_support=self._estimate_evidence_support(gap, context),
		)

	def _enrich_hypotheses(
		self,
		hypotheses: List[Hypothesis],
		context: Dict[str, Any],
	) -> List[Hypothesis]:
		domain = str(context.get("research_domain") or "integrative_research")
		supporting_signals = self._context_strings(context)[:3]
		contradiction_signals = self._ensure_text_list(context.get("contradictions"))[:3]
		score_weights = self._resolve_hypothesis_score_weights(context)
		minimum_confidence = self._resolve_minimum_hypothesis_confidence(context)
		minimum_evidence_support = self._resolve_minimum_evidence_support(context)
		validated_threshold, active_threshold = self._resolve_status_thresholds(context)
		enriched: List[Hypothesis] = []
		for item in hypotheses:
			mechanism_completeness = self._estimate_mechanism_completeness(item, context)
			item.domain = item.domain or domain
			item.supporting_signals = item.supporting_signals or supporting_signals
			item.contradiction_signals = item.contradiction_signals or contradiction_signals
			item.scores = {
				**item.scores,
				"testability": self._estimate_testability(item.validation_plan),
				"relevance": self._estimate_relevance(item, context),
				"mechanism_completeness": mechanism_completeness,
			}
			item.confidence = round(
				item.novelty * score_weights["novelty"]
				+ item.feasibility * score_weights["feasibility"]
				+ item.evidence_support * score_weights["evidence_support"]
				+ mechanism_completeness * score_weights["mechanism_completeness"],
				4,
			)
			item.final_score = round(item.confidence, 4)
			if item.evidence_support < minimum_evidence_support or item.confidence < minimum_confidence:
				item.status = "rejected"
				continue
			if item.confidence >= validated_threshold:
				item.status = "validated"
			elif item.confidence >= active_threshold:
				item.status = "active"
			else:
				item.status = "draft"
			enriched.append(item)
		return enriched[: self._resolve_hypothesis_max_hypotheses(context)]

	def _estimate_testability(self, validation_plan: str) -> float:
		measurable_terms = ["验证", "比较", "抽取", "回顾", "分析", "检索", "复核"]
		hit_count = sum(1 for term in measurable_terms if term in validation_plan)
		return round(min(1.0, 0.45 + hit_count * 0.08), 4)

	def _estimate_relevance(self, hypothesis: Hypothesis, context: Dict[str, Any]) -> float:
		objective_terms = self._extract_keywords(
			[
				str(context.get("research_objective") or ""),
				str(context.get("research_scope") or ""),
			]
		)
		overlap = sum(1 for keyword in hypothesis.keywords if keyword in objective_terms)
		return round(min(1.0, 0.5 + overlap * 0.12), 4)

	def _estimate_mechanism_completeness(self, hypothesis: Hypothesis, context: Dict[str, Any]) -> float:
		reasoning_summary = context.get("reasoning_summary") or {}
		knowledge_patterns = context.get("knowledge_patterns") or reasoning_summary.get("knowledge_patterns") or {}
		inference_confidence = float(context.get("inference_confidence") or reasoning_summary.get("inference_confidence") or 0.0)
		common_entities = [str(item) for item in (knowledge_patterns.get("common_entities") or []) if str(item).strip()]
		shared_efficacies = [str(item) for item in (knowledge_patterns.get("most_shared_efficacies") or []) if str(item).strip()]
		grouped_entities = knowledge_patterns.get("entity_groups") or {}

		keyword_hits = sum(1 for keyword in hypothesis.keywords if keyword in common_entities or keyword in shared_efficacies)
		entity_hits = sum(
			1
			for entity in hypothesis.source_entities
			if entity in common_entities or any(entity in values for values in grouped_entities.values())
		)
		path_bonus = 0.0
		if len(hypothesis.source_entities) >= 2:
			paths = self.knowledge_graph.query_path(hypothesis.source_entities[0], hypothesis.source_entities[-1])
			if paths:
				path_bonus = min(0.2, 0.05 * len(paths[0]))

		score = 0.35 + min(0.2, keyword_hits * 0.08) + min(0.15, entity_hits * 0.08)
		score += min(0.25, inference_confidence * 0.25) + path_bonus
		return round(min(1.0, score), 4)

	def _extract_keywords(self, texts: Iterable[str]) -> List[str]:
		keywords: List[str] = []
		for text in texts:
			normalized = str(text).replace("，", " ").replace("。", " ").replace("、", " ")
			for token in normalized.split():
				cleaned = token.strip()
				if len(cleaned) >= 2 and cleaned not in keywords:
					keywords.append(cleaned)
		return keywords[:8]

	def _normalize_score(self, value: Any, default: float) -> float:
		try:
			score = float(value)
		except (TypeError, ValueError):
			return default
		return max(0.0, min(1.0, score))

	def _ensure_text_list(self, value: Any) -> List[str]:
		if isinstance(value, list):
			return [str(item) for item in value if str(item).strip()]
		if isinstance(value, str) and value.strip():
			return [value.strip()]
		return []

	def _next_level_name(self, entity_type: str) -> str:
		mapping = {
			"formula": "证候",
			"syndrome": "靶点",
			"target": "通路",
		}
		return mapping.get(entity_type, "下游实体")


__all__ = ["Hypothesis", "HypothesisEngine"]
