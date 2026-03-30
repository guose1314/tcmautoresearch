"""假设引擎模块 - 假设生成、评分与迭代验证。"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


@dataclass
class HypothesisCandidate:
    """单条研究假设候选。"""

    hypothesis_id: str
    title: str
    statement: str
    domain: str
    rationale: str
    validation_plan: str
    keywords: List[str] = field(default_factory=list)
    supporting_signals: List[str] = field(default_factory=list)
    contradiction_signals: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    validation_score: float = 0.0
    final_score: float = 0.0
    iteration_count: int = 0
    status: str = "draft"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "statement": self.statement,
            "domain": self.domain,
            "rationale": self.rationale,
            "validation_plan": self.validation_plan,
            "keywords": self.keywords,
            "supporting_signals": self.supporting_signals,
            "contradiction_signals": self.contradiction_signals,
            "scores": self.scores,
            "confidence": self.confidence,
            "validation_score": self.validation_score,
            "final_score": self.final_score,
            "iteration_count": self.iteration_count,
            "status": self.status,
        }


@dataclass
class ValidationIteration:
    """单轮假设验证记录。"""

    hypothesis_id: str
    iteration_index: int
    support_count: int
    contradiction_count: int
    evidence_coverage: float
    verification_score: float
    action: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "iteration_index": self.iteration_index,
            "support_count": self.support_count,
            "contradiction_count": self.contradiction_count,
            "evidence_coverage": self.evidence_coverage,
            "verification_score": self.verification_score,
            "action": self.action,
            "notes": self.notes,
        }


class HypothesisEngine(BaseModule):
    """研究假设引擎，负责生成、评分与多轮验证。"""

    _DEFAULT_WEIGHTS = {
        "evidence": 0.25,
        "testability": 0.2,
        "novelty": 0.15,
        "feasibility": 0.15,
        "relevance": 0.15,
        "clarity": 0.1,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, llm_service: Any = None):
        super().__init__("hypothesis_engine", config)
        self.llm_service = llm_service
        self.max_hypotheses = int(self.config.get("max_hypotheses", 3))
        self.max_validation_iterations = int(self.config.get("max_validation_iterations", 2))
        self.closed_loop_iterations = int(
            self.config.get("closed_loop_iterations", self.max_validation_iterations)
        )
        self.validation_threshold = float(self.config.get("validation_threshold", 0.68))
        self.weights = {
            **self._DEFAULT_WEIGHTS,
            **(self.config.get("score_weights") or {}),
        }

    def _do_initialize(self) -> bool:
        self.logger.info("HypothesisEngine 初始化完成")
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prepared = self._prepare_context(context)
        hypotheses = self._generate_hypotheses(prepared)
        scored_hypotheses = [self._score_hypothesis(item, prepared) for item in hypotheses]
        scored_hypotheses.sort(key=lambda item: item.final_score, reverse=True)
        scored_hypotheses = scored_hypotheses[: self.max_hypotheses]

        llm_iterations = self._run_llm_closed_loop(scored_hypotheses, prepared)
        validation_iterations = llm_iterations + self._run_validation_iterations(scored_hypotheses, prepared)
        scored_hypotheses.sort(key=lambda item: item.final_score, reverse=True)

        top_hypothesis = scored_hypotheses[0] if scored_hypotheses else None
        research_direction = top_hypothesis.title if top_hypothesis else prepared["research_objective"]

        return {
            "phase": "hypothesis",
            "hypotheses": [item.to_dict() for item in scored_hypotheses],
            "validation_iterations": [item.to_dict() for item in validation_iterations],
            "metadata": {
                "hypothesis_count": len(scored_hypotheses),
                "validation_iteration_count": len(validation_iterations),
                "research_direction": research_direction,
                "selected_hypothesis_id": top_hypothesis.hypothesis_id if top_hypothesis else "",
                "used_llm_generation": prepared["used_llm_generation"],
                "used_llm_closed_loop": prepared["used_llm_closed_loop"],
                "llm_iteration_count": len(llm_iterations),
            },
        }

    def _do_cleanup(self) -> bool:
        self.logger.info("HypothesisEngine 资源清理完成")
        return True

    def _prepare_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        observations = self._ensure_text_list(context.get("observations"))
        findings = self._ensure_text_list(context.get("findings"))
        contradictions = self._ensure_text_list(context.get("contradictions"))
        literature_titles = self._extract_literature_titles(context)
        entities = self._ensure_entity_list(context.get("entities"))
        evidence_pool = observations + findings + literature_titles
        objective = str(context.get("research_objective") or "从中医古籍中提炼可验证的研究问题")
        scope = str(context.get("research_scope") or "")
        domain = str(context.get("research_domain") or self._infer_domain(scope, objective, entities))
        existing_hypotheses = self._extract_existing_hypothesis_texts(context.get("existing_hypotheses"))
        generated_at = datetime.now().isoformat()

        return {
            "observations": observations,
            "findings": findings,
            "contradictions": contradictions,
            "literature_titles": literature_titles,
            "entities": entities,
            "evidence_pool": evidence_pool,
            "research_objective": objective,
            "research_scope": scope,
            "research_domain": domain,
            "existing_hypotheses": existing_hypotheses,
            "generated_at": generated_at,
            "used_llm_generation": False,
            "used_llm_closed_loop": False,
            "context": context,
        }

    def _resolve_llm_service(self, prepared: Dict[str, Any]) -> Any:
        return prepared["context"].get("llm_service") or self.llm_service

    def _run_llm_closed_loop(
        self,
        hypotheses: List[HypothesisCandidate],
        prepared: Dict[str, Any],
    ) -> List[ValidationIteration]:
        if not hypotheses:
            return []
        if not prepared["context"].get("use_llm_generation"):
            return []

        llm_service = self._resolve_llm_service(prepared)
        if llm_service is None:
            return []
        if not (hasattr(llm_service, "generate") or hasattr(llm_service, "evaluate_hypothesis")):
            return []

        iterations: List[ValidationIteration] = []
        max_rounds = max(0, self.closed_loop_iterations)
        for hypothesis in hypotheses:
            running_score = hypothesis.final_score
            for iteration_index in range(1, max_rounds + 1):
                feedback = self._request_llm_feedback(llm_service, hypothesis, prepared, iteration_index)
                if not feedback:
                    continue

                support_count = self._count_keyword_hits(hypothesis.keywords, prepared["evidence_pool"])
                contradiction_count = self._count_keyword_hits(hypothesis.keywords, prepared["contradictions"])
                evidence_coverage = min(
                    1.0,
                    (support_count + len(hypothesis.supporting_signals) + iteration_index)
                    / max(1, len(hypothesis.keywords) + 2),
                )

                verification_score = float(feedback.get("verification_score", running_score))
                verification_score = max(0.0, min(1.0, verification_score))
                action = str(feedback.get("action") or self._choose_validation_action(verification_score, contradiction_count)).lower()
                if action not in {"retain", "revise", "deprioritize"}:
                    action = self._choose_validation_action(verification_score, contradiction_count)

                revised_statement = str(feedback.get("revised_statement") or "").strip()
                revised_plan = str(feedback.get("revised_plan") or "").strip()
                if action == "revise" and revised_statement:
                    hypothesis.statement = revised_statement
                    hypothesis.title = revised_statement[:36] if len(revised_statement) > 36 else revised_statement
                    hypothesis.keywords = self._extract_keywords([revised_statement]) or hypothesis.keywords
                    if revised_plan:
                        hypothesis.validation_plan = revised_plan
                    hypothesis = self._score_hypothesis(hypothesis, prepared)

                running_score = round((running_score + verification_score) / 2.0, 4)
                hypothesis.validation_score = round(verification_score, 4)
                hypothesis.final_score = running_score
                hypothesis.iteration_count = max(hypothesis.iteration_count, iteration_index)
                hypothesis.status = self._status_from_score(running_score, action)

                notes = self._build_iteration_notes(
                    support_count,
                    contradiction_count,
                    evidence_coverage,
                    action,
                )
                llm_note = str(feedback.get("note") or "").strip()
                if llm_note:
                    notes.append(f"LLM评审: {llm_note}")

                iterations.append(
                    ValidationIteration(
                        hypothesis_id=hypothesis.hypothesis_id,
                        iteration_index=iteration_index,
                        support_count=support_count,
                        contradiction_count=contradiction_count,
                        evidence_coverage=round(evidence_coverage, 4),
                        verification_score=round(verification_score, 4),
                        action=action,
                        notes=notes,
                    )
                )

        if iterations:
            prepared["used_llm_closed_loop"] = True
        return iterations

    def _request_llm_feedback(
        self,
        llm_service: Any,
        hypothesis: HypothesisCandidate,
        prepared: Dict[str, Any],
        iteration_index: int,
    ) -> Dict[str, Any]:
        try:
            if hasattr(llm_service, "evaluate_hypothesis"):
                response = llm_service.evaluate_hypothesis(
                    hypothesis.statement,
                    self._summarize_evidence_pool(prepared["evidence_pool"]),
                    "\n".join(prepared["contradictions"][:5]),
                    prepared["research_objective"],
                )
            else:
                response = llm_service.generate(
                    self._build_llm_feedback_prompt(hypothesis, prepared, iteration_index),
                    system_prompt=(
                        "你是中医科研方法学评审专家。"
                        "请输出可执行的评审结论，格式为 key: value，每行一个字段。"
                    ),
                )
        except Exception as exc:
            self.logger.warning("LLM 闭环评审失败，跳过该轮: %s", exc)
            return {}

        if isinstance(response, dict):
            return response
        return self._parse_llm_feedback_response(str(response or ""))

    def _build_llm_feedback_prompt(
        self,
        hypothesis: HypothesisCandidate,
        prepared: Dict[str, Any],
        iteration_index: int,
    ) -> str:
        return (
            f"第 {iteration_index} 轮假设评审\n"
            f"研究目标: {prepared['research_objective']}\n"
            f"研究领域: {prepared['research_domain']}\n"
            f"假设陈述: {hypothesis.statement}\n"
            f"验证计划: {hypothesis.validation_plan}\n"
            f"证据摘要:\n{self._summarize_evidence_pool(prepared['evidence_pool'])}\n"
            f"冲突线索:\n{self._summarize_evidence_pool(prepared['contradictions'])}\n\n"
            "请输出：\n"
            "verification_score: 0-1 浮点数\n"
            "action: retain/revise/deprioritize\n"
            "note: 评语\n"
            "revised_statement: 若 action=revise，给出修订后的假设陈述，否则留空\n"
            "revised_plan: 若 action=revise，给出修订后的验证计划，否则留空\n"
        )

    def _parse_llm_feedback_response(self, text: str) -> Dict[str, Any]:
        payload = self._extract_feedback_payload(text)
        self._normalize_feedback_score(payload)
        self._normalize_feedback_action(payload)
        self._normalize_feedback_revisions(payload)
        return payload

    def _extract_feedback_payload(self, text: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            payload[key.strip().lower()] = value.strip()
        return payload

    def _normalize_feedback_score(self, payload: Dict[str, Any]) -> None:
        score_text = str(payload.get("verification_score", "")).strip()
        if not score_text:
            return
        match = re.search(r"[-+]?\d*\.?\d+", score_text)
        if not match:
            return
        try:
            payload["verification_score"] = float(match.group(0))
        except ValueError:
            return

    def _normalize_feedback_action(self, payload: Dict[str, Any]) -> None:
        action_text = str(payload.get("action", "")).lower()
        if not action_text:
            return
        if "retain" in action_text or "保留" in action_text:
            payload["action"] = "retain"
            return
        if "deprioritize" in action_text or "降级" in action_text or "降低" in action_text:
            payload["action"] = "deprioritize"
            return
        payload["action"] = "revise"

    def _normalize_feedback_revisions(self, payload: Dict[str, Any]) -> None:
        if "revised_statement" in payload:
            payload["revised_statement"] = str(payload["revised_statement"]).strip()
        if "revised_plan" in payload:
            payload["revised_plan"] = str(payload["revised_plan"]).strip()

    def _generate_hypotheses(self, prepared: Dict[str, Any]) -> List[HypothesisCandidate]:
        llm_candidates = self._generate_hypotheses_with_llm(prepared)
        if llm_candidates:
            prepared["used_llm_generation"] = True
            return llm_candidates
        return self._generate_heuristic_hypotheses(prepared)

    def _generate_hypotheses_with_llm(self, prepared: Dict[str, Any]) -> List[HypothesisCandidate]:
        if not prepared["context"].get("use_llm_generation"):
            return []

        llm_service = prepared["context"].get("llm_service") or self.llm_service
        if llm_service is None or not hasattr(llm_service, "generate_research_hypothesis"):
            return []

        try:
            response = llm_service.generate_research_hypothesis(
                prepared["research_domain"],
                self._summarize_evidence_pool(prepared["evidence_pool"]),
                "\n".join(prepared["existing_hypotheses"]),
            )
        except Exception as exc:
            self.logger.warning("LLM 假设生成失败，回退启发式生成: %s", exc)
            return []

        items = [line.strip("- 0123456789.、") for line in response.splitlines() if line.strip()]
        candidates: List[HypothesisCandidate] = []
        for idx, item in enumerate(items[: self.max_hypotheses]):
            title = item[:36] if len(item) > 36 else item
            candidates.append(
                self._build_candidate(
                    title=title or f"研究假设 {idx + 1}",
                    statement=item,
                    domain=prepared["research_domain"],
                    rationale="基于 LLM 对观察结果、研究目标和既有研究的综合生成。",
                    validation_plan="通过古籍证据比对、结构化抽取结果复核与文献回溯验证。",
                    keywords=self._extract_keywords([item]),
                    supporting_signals=prepared["evidence_pool"][:3],
                    contradiction_signals=prepared["contradictions"][:2],
                    generated_at=prepared["generated_at"],
                )
            )
        return candidates

    def _generate_heuristic_hypotheses(self, prepared: Dict[str, Any]) -> List[HypothesisCandidate]:
        formulas = self._entity_names_by_type(prepared["entities"], "formula")
        herbs = self._entity_names_by_type(prepared["entities"], "herb")
        syndromes = self._entity_names_by_type(prepared["entities"], "syndrome")
        efficacies = self._entity_names_by_type(prepared["entities"], "efficacy")
        candidates: List[HypothesisCandidate] = []

        primary_formula = formulas[0] if formulas else "方剂配伍"
        primary_herb = herbs[0] if herbs else "核心药物"
        primary_syndrome = syndromes[0] if syndromes else "目标证候"
        primary_efficacy = efficacies[0] if efficacies else "关键功效"

        candidates.append(
            self._build_candidate(
                title=f"{primary_formula} 与 {primary_syndrome} 的配伍效应假设",
                statement=(
                    f"假设 {primary_formula} 的核心配伍结构与 {primary_syndrome} 的治疗效果存在稳定对应关系，"
                    f"且这种关系可通过 {primary_efficacy} 等语义线索重复验证。"
                ),
                domain=prepared["research_domain"],
                rationale="观察结果显示方剂、证候和功效线索具有可复用的关联模式。",
                validation_plan="对古籍文本中的方剂-证候-功效三元组进行抽取、统计和交叉验证。",
                keywords=[primary_formula, primary_syndrome, primary_efficacy],
                supporting_signals=self._select_supporting_signals(prepared, [primary_formula, primary_syndrome, primary_efficacy]),
                contradiction_signals=prepared["contradictions"][:2],
                generated_at=prepared["generated_at"],
            )
        )

        candidates.append(
            self._build_candidate(
                title=f"{primary_herb} 的功效机制可迁移假设",
                statement=(
                    f"假设 {primary_herb} 在不同方剂中的角色变化会改变其 {primary_efficacy} 相关功效表达，"
                    "这种变化可通过知识图谱路径与文献证据联合验证。"
                ),
                domain=prepared["research_domain"],
                rationale="实体与观察结果同时指向药物角色和功效表达之间的耦合关系。",
                validation_plan="比较同一药物在多方剂中的角色分布、关联功效和证候覆盖度。",
                keywords=[primary_herb, primary_efficacy] + formulas[:1],
                supporting_signals=self._select_supporting_signals(prepared, [primary_herb, primary_efficacy]),
                contradiction_signals=prepared["contradictions"][:2],
                generated_at=prepared["generated_at"],
            )
        )

        if self._looks_historical(prepared):
            candidates.append(
                self._build_candidate(
                    title="古籍剂量与证候表述演变假设",
                    statement="假设古籍中剂量、功效与证候表述存在可量化的历史演变轨迹，并影响后续配伍决策。",
                    domain=prepared["research_domain"],
                    rationale="研究范围和观察结果包含明显的历史比较与文本演化线索。",
                    validation_plan="按时代切分语料，对剂量词、证候词和配伍词进行时间序列比较。",
                    keywords=["剂量", "证候", "演变"],
                    supporting_signals=self._select_supporting_signals(prepared, ["历史", "演变", "朝代", "剂量"]),
                    contradiction_signals=prepared["contradictions"][:2],
                    generated_at=prepared["generated_at"],
                )
            )

        while len(candidates) < self.max_hypotheses:
            seed_index = len(candidates) + 1
            candidates.append(
                self._build_candidate(
                    title=f"研究目标驱动假设 {seed_index}",
                    statement=f"假设围绕“{prepared['research_objective']}”可以形成可重复检验的结构化证据链。",
                    domain=prepared["research_domain"],
                    rationale="在观测线索不足时，以研究目标为中心生成保守假设。",
                    validation_plan="补充抽取结果与文献背景后，对假设进行再次评分与收敛。",
                    keywords=self._extract_keywords([prepared["research_objective"]]),
                    supporting_signals=prepared["evidence_pool"][:2],
                    contradiction_signals=prepared["contradictions"][:2],
                    generated_at=prepared["generated_at"],
                )
            )

        return candidates[: self.max_hypotheses]

    def _score_hypothesis(self, candidate: HypothesisCandidate, prepared: Dict[str, Any]) -> HypothesisCandidate:
        evidence_hits = self._count_keyword_hits(candidate.keywords, prepared["evidence_pool"])
        objective_hits = self._count_keyword_hits(candidate.keywords, [prepared["research_objective"], prepared["research_scope"]])
        contradiction_hits = self._count_keyword_hits(candidate.keywords, prepared["contradictions"])
        existing_overlap = self._count_keyword_hits(candidate.keywords, prepared["existing_hypotheses"])

        evidence_score = min(1.0, 0.3 + evidence_hits * 0.12 + len(candidate.supporting_signals) * 0.08)
        testability_score = min(1.0, 0.45 + self._count_measurable_terms(candidate.validation_plan) * 0.1)
        novelty_score = max(0.15, 0.9 - existing_overlap * 0.15)
        feasibility_score = min(1.0, 0.35 + len(prepared["entities"]) * 0.03 + len(prepared["evidence_pool"]) * 0.04)
        relevance_score = min(1.0, 0.4 + objective_hits * 0.15 + self._domain_bonus(prepared["research_domain"], candidate.keywords))
        clarity_score = min(1.0, 0.55 + (0.1 if len(candidate.statement) >= 24 else 0.0) + (0.1 if candidate.validation_plan else 0.0))

        composite = (
            evidence_score * self.weights["evidence"]
            + testability_score * self.weights["testability"]
            + novelty_score * self.weights["novelty"]
            + feasibility_score * self.weights["feasibility"]
            + relevance_score * self.weights["relevance"]
            + clarity_score * self.weights["clarity"]
        )
        composite = max(0.0, min(1.0, composite - contradiction_hits * 0.05))

        candidate.scores = {
            "evidence": round(evidence_score, 4),
            "testability": round(testability_score, 4),
            "novelty": round(novelty_score, 4),
            "feasibility": round(feasibility_score, 4),
            "relevance": round(relevance_score, 4),
            "clarity": round(clarity_score, 4),
        }
        candidate.confidence = round(composite, 4)
        candidate.validation_score = round(composite, 4)
        candidate.final_score = round(composite, 4)
        candidate.status = "active" if composite >= self.validation_threshold else "draft"
        return candidate

    def _run_validation_iterations(
        self,
        hypotheses: List[HypothesisCandidate],
        prepared: Dict[str, Any],
    ) -> List[ValidationIteration]:
        iterations: List[ValidationIteration] = []

        for hypothesis in hypotheses:
            running_score = hypothesis.final_score
            for iteration_index in range(1, self.max_validation_iterations + 1):
                support_count = self._count_keyword_hits(hypothesis.keywords, prepared["evidence_pool"])
                contradiction_count = self._count_keyword_hits(hypothesis.keywords, prepared["contradictions"])
                evidence_coverage = min(
                    1.0,
                    (support_count + len(hypothesis.supporting_signals) + iteration_index)
                    / max(1, len(hypothesis.keywords) + 2),
                )
                verification_score = max(
                    0.0,
                    min(
                        1.0,
                        running_score * 0.55 + evidence_coverage * 0.4 - contradiction_count * 0.06,
                    ),
                )
                action = self._choose_validation_action(verification_score, contradiction_count)
                notes = self._build_iteration_notes(
                    support_count,
                    contradiction_count,
                    evidence_coverage,
                    action,
                )

                iteration = ValidationIteration(
                    hypothesis_id=hypothesis.hypothesis_id,
                    iteration_index=iteration_index,
                    support_count=support_count,
                    contradiction_count=contradiction_count,
                    evidence_coverage=round(evidence_coverage, 4),
                    verification_score=round(verification_score, 4),
                    action=action,
                    notes=notes,
                )
                iterations.append(iteration)

                running_score = round((running_score + verification_score) / 2.0, 4)
                hypothesis.validation_score = round(verification_score, 4)
                hypothesis.final_score = running_score
                hypothesis.iteration_count = iteration_index
                hypothesis.status = self._status_from_score(running_score, action)

        return iterations

    def _build_candidate(
        self,
        title: str,
        statement: str,
        domain: str,
        rationale: str,
        validation_plan: str,
        keywords: List[str],
        supporting_signals: List[str],
        contradiction_signals: List[str],
        generated_at: str,
    ) -> HypothesisCandidate:
        stable_text = f"{title}|{statement}|{domain}|{generated_at}"
        hypothesis_id = hashlib.md5(stable_text.encode("utf-8")).hexdigest()[:12]
        return HypothesisCandidate(
            hypothesis_id=hypothesis_id,
            title=title,
            statement=statement,
            domain=domain,
            rationale=rationale,
            validation_plan=validation_plan,
            keywords=[item for item in keywords if item],
            supporting_signals=supporting_signals,
            contradiction_signals=contradiction_signals,
        )

    def _extract_existing_hypothesis_texts(self, hypotheses: Any) -> List[str]:
        if not isinstance(hypotheses, list):
            return []
        results: List[str] = []
        for item in hypotheses:
            if isinstance(item, dict):
                text = item.get("statement") or item.get("description") or item.get("title") or ""
                if text:
                    results.append(str(text))
            elif item:
                results.append(str(item))
        return results

    def _extract_literature_titles(self, context: Dict[str, Any]) -> List[str]:
        titles: List[str] = []
        direct_titles = context.get("literature_titles")
        if isinstance(direct_titles, list):
            titles.extend(str(item) for item in direct_titles if item)

        literature_pipeline = context.get("literature_pipeline")
        if isinstance(literature_pipeline, dict):
            for key in ["records", "articles", "results", "related_works"]:
                values = literature_pipeline.get(key)
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, dict):
                            title = item.get("title") or item.get("paper_title") or item.get("name")
                            if title:
                                titles.append(str(title))
                        elif item:
                            titles.append(str(item))
        return titles

    def _ensure_text_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if value:
            return [str(value)]
        return []

    def _ensure_entity_list(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _entity_names_by_type(self, entities: List[Dict[str, Any]], entity_type: str) -> List[str]:
        return [
            str(item.get("name"))
            for item in entities
            if str(item.get("type", "")).lower() == entity_type and item.get("name")
        ]

    def _infer_domain(self, scope: str, objective: str, entities: List[Dict[str, Any]]) -> str:
        combined = f"{scope} {objective}".lower()
        if "history" in combined or "historical" in combined or "朝代" in combined or "古籍" in combined:
            return "historical_research"
        if any(str(item.get("type", "")).lower() == "formula" for item in entities):
            return "formula_research"
        if any(str(item.get("type", "")).lower() == "herb" for item in entities):
            return "herb_research"
        return "integrative_research"

    def _looks_historical(self, prepared: Dict[str, Any]) -> bool:
        text_blob = " ".join(prepared["observations"] + prepared["findings"] + [prepared["research_scope"], prepared["research_objective"]])
        return any(token in text_blob for token in ["朝代", "历史", "演变", "古籍", "时期"])

    def _select_supporting_signals(self, prepared: Dict[str, Any], keywords: List[str]) -> List[str]:
        signals: List[str] = []
        for entry in prepared["evidence_pool"]:
            if any(keyword and keyword in entry for keyword in keywords):
                signals.append(entry)
            if len(signals) >= 3:
                break
        if signals:
            return signals
        return prepared["evidence_pool"][:3]

    def _extract_keywords(self, texts: List[str]) -> List[str]:
        keywords: List[str] = []
        for text in texts:
            for token in str(text).replace("，", " ").replace("。", " ").replace("、", " ").split():
                cleaned = token.strip()
                if len(cleaned) >= 2 and cleaned not in keywords:
                    keywords.append(cleaned)
        return keywords[:6]

    def _count_keyword_hits(self, keywords: List[str], texts: List[str]) -> int:
        hits = 0
        for text in texts:
            if any(keyword and keyword in text for keyword in keywords):
                hits += 1
        return hits

    def _count_measurable_terms(self, text: str) -> int:
        terms = ["统计", "验证", "比较", "抽取", "实验", "评分", "时间序列", "交叉验证"]
        return sum(1 for item in terms if item in text)

    def _domain_bonus(self, domain: str, keywords: List[str]) -> float:
        bonus_map = {
            "formula_research": ["方剂", "配伍", "功效"],
            "herb_research": ["药物", "药材", "功效"],
            "historical_research": ["历史", "古籍", "演变"],
            "integrative_research": ["证据", "关联", "结构"],
        }
        bonus_keywords = bonus_map.get(domain, [])
        if any(item in keywords for item in bonus_keywords):
            return 0.15
        return 0.05

    def _choose_validation_action(self, verification_score: float, contradiction_count: int) -> str:
        if contradiction_count >= 2 and verification_score < self.validation_threshold:
            return "deprioritize"
        if verification_score >= self.validation_threshold:
            return "retain"
        return "revise"

    def _build_iteration_notes(
        self,
        support_count: int,
        contradiction_count: int,
        evidence_coverage: float,
        action: str,
    ) -> List[str]:
        notes = [f"支持证据命中 {support_count} 条", f"证据覆盖率 {evidence_coverage:.2f}"]
        if contradiction_count:
            notes.append(f"发现 {contradiction_count} 条潜在冲突线索")
        if action == "retain":
            notes.append("当前假设可进入下一阶段实验设计")
        elif action == "revise":
            notes.append("建议补充观察证据或缩小研究范围后再次评分")
        else:
            notes.append("建议降低优先级，等待新增证据")
        return notes

    def _status_from_score(self, score: float, action: str) -> str:
        if action == "deprioritize":
            return "deprioritized"
        if score >= 0.8:
            return "validated"
        if score >= self.validation_threshold:
            return "active"
        return "draft"

    def _summarize_evidence_pool(self, evidence_pool: List[str]) -> str:
        if not evidence_pool:
            return "暂无结构化观察结果。"
        return "\n".join(evidence_pool[:6])


__all__ = ["HypothesisEngine", "HypothesisCandidate", "ValidationIteration"]