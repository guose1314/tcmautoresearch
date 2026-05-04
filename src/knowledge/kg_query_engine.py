# -*- coding: utf-8 -*-
"""KGQueryEngine：自然语言 → Cypher 转换引擎。

将用户的中医药自然语言问题映射为安全的 Cypher 查询，降低知识图谱查询门槛。

设计：
- 基于意图识别 + 实体抽取 + 模板匹配（确定性，无 LLM 依赖）
- 可选 LLM 辅助模式：将模板无法匹配的查询交由 LLM 生成 Cypher，
  但会经过安全校验（只允许 MATCH / RETURN / WITH / WHERE / OPTIONAL MATCH）
- 所有查询只读（禁止 CREATE / DELETE / SET / MERGE / REMOVE / DROP）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from src.llm.llm_gateway import generate_with_gateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 安全：禁止的 Cypher 关键字（写操作）
# ---------------------------------------------------------------------------

_WRITE_KEYWORDS: Set[str] = {
    "CREATE",
    "DELETE",
    "DETACH",
    "SET",
    "MERGE",
    "REMOVE",
    "DROP",
    "CALL",
    "FOREACH",
    "LOAD",
}

_WRITE_PATTERN = re.compile(
    r"\b(" + "|".join(_WRITE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _is_safe_cypher(cypher: str) -> bool:
    """检查 Cypher 是否只含只读操作。"""
    # 去除字符串字面量后再检查
    cleaned = re.sub(r"'[^']*'", "", cypher)
    cleaned = re.sub(r'"[^"]*"', "", cleaned)
    return _WRITE_PATTERN.search(cleaned) is None


# ---------------------------------------------------------------------------
# 查询意图
# ---------------------------------------------------------------------------

INTENT_COMPOSITION = "composition"  # 方剂组成
INTENT_EFFICACY = "efficacy"  # 中药功效
INTENT_TREATING = "treating"  # 治疗某证候的方剂
INTENT_SIMILAR = "similar"  # 类似方剂
INTENT_PATH = "path"  # 两实体间路径
INTENT_HERB_FORMULAS = "herb_formulas"  # 含某药的方剂
INTENT_STATISTICS = "statistics"  # 统计
INTENT_UNKNOWN = "unknown"

_INTENT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        INTENT_COMPOSITION,
        re.compile(
            r"(组成|君臣佐使|配伍|组方|由.{0,6}组成|包含.{0,6}药)", re.IGNORECASE
        ),
    ),
    (
        INTENT_EFFICACY,
        re.compile(r"(功效|作用|主治|功能|效果|药效|有什么用)", re.IGNORECASE),
    ),
    (
        INTENT_TREATING,
        re.compile(r"(治疗|治|主治|用于|可治|哪些方.{0,4}治)", re.IGNORECASE),
    ),
    (
        INTENT_SIMILAR,
        re.compile(r"(类似|相似|近似|替代|同类|像.{0,4}方)", re.IGNORECASE),
    ),
    (INTENT_PATH, re.compile(r"(关系|路径|关联|相关|联系|之间)", re.IGNORECASE)),
    (
        INTENT_HERB_FORMULAS,
        re.compile(r"(含有|用了|使用了|哪些方.{0,4}含|哪些方.{0,4}用)", re.IGNORECASE),
    ),
    (INTENT_STATISTICS, re.compile(r"(统计|多少|数量|总共|总计|有几)", re.IGNORECASE)),
]

# ---------------------------------------------------------------------------
# 实体抽取（复用 kg_rag 的词典）
# ---------------------------------------------------------------------------

_KNOWN_FORMULAS: Optional[Set[str]] = None
_KNOWN_HERBS: Optional[Set[str]] = None


def _load_entity_dicts() -> None:
    global _KNOWN_FORMULAS, _KNOWN_HERBS
    if _KNOWN_FORMULAS is not None:
        return
    try:
        from src.semantic_modeling.tcm_relationships import (
            TCMRelationshipDefinitions as Defs,
        )

        _KNOWN_FORMULAS = set(Defs.FORMULA_COMPOSITIONS.keys())
        _KNOWN_HERBS = set(Defs.HERB_EFFICACY_MAP.keys())
    except ImportError:
        _KNOWN_FORMULAS = set()
        _KNOWN_HERBS = set()


def _extract_entities(query: str) -> Dict[str, List[str]]:
    """从查询中提取方剂名和中药名。"""
    _load_entity_dicts()
    assert _KNOWN_FORMULAS is not None and _KNOWN_HERBS is not None
    result: Dict[str, List[str]] = {"formula": [], "herb": []}
    seen: Set[str] = set()
    for name in _KNOWN_FORMULAS:
        if name in query and name not in seen:
            result["formula"].append(name)
            seen.add(name)
    for name in _KNOWN_HERBS:
        if name in query and name not in seen:
            result["herb"].append(name)
            seen.add(name)
    return result


# ---------------------------------------------------------------------------
# 查询结果
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """单次图谱查询的结果。"""

    success: bool
    intent: str
    cypher: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    records: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Cypher 模板
# ---------------------------------------------------------------------------

_CYPHER_TEMPLATES: Dict[str, str] = {
    INTENT_COMPOSITION: (
        "MATCH (f:Formula {name: $formula_name})-[r]->(h:Herb) "
        "RETURN h.name AS herb, type(r) AS role ORDER BY role"
    ),
    INTENT_EFFICACY: (
        "MATCH (h:Herb {name: $herb_name})-[:HAS_EFFICACY]->(e:Efficacy) "
        "RETURN e.name AS efficacy"
    ),
    INTENT_TREATING: (
        "MATCH (f:Formula)-[:TREATS]->(s:Syndrome {name: $syndrome_name}) "
        "RETURN f.name AS formula"
    ),
    INTENT_SIMILAR: (
        "MATCH (f1:Formula {name: $formula_name})-[:SIMILAR_TO]-(f2:Formula) "
        "RETURN f2.name AS similar_formula LIMIT 10"
    ),
    INTENT_PATH: (
        "MATCH p = allShortestPaths((a {name: $src})-[*..6]-(b {name: $dst})) "
        "RETURN [n IN nodes(p) | n.name] AS path, "
        "[r IN relationships(p) | type(r)] AS rels LIMIT 10"
    ),
    INTENT_HERB_FORMULAS: (
        "MATCH (f:Formula)-[r]->(h:Herb {name: $herb_name}) "
        "WHERE type(r) IN ['SOVEREIGN','MINISTER','ASSISTANT','ENVOY'] "
        "RETURN f.name AS formula, type(r) AS role"
    ),
    INTENT_STATISTICS: (
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"
    ),
}


# ---------------------------------------------------------------------------
# KGQueryEngine
# ---------------------------------------------------------------------------


class KGQueryEngine:
    """自然语言 → Cypher 查询引擎。

    Parameters
    ----------
    neo4j_driver : Neo4jDriver | None
        Neo4j 驱动实例（已连接）。为 None 时仅做翻译不执行。
    llm_service : LLMService | None
        可选 LLM 服务，用于模板无法覆盖时的 Cypher 生成。
    """

    def __init__(
        self,
        neo4j_driver: Optional[Any] = None,
        llm_service: Optional[Any] = None,
    ) -> None:
        self._driver = neo4j_driver
        self._llm = llm_service

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def query(self, natural_language: str) -> QueryResult:
        """将自然语言查询翻译为 Cypher 并执行。

        Parameters
        ----------
        natural_language : str
            用户输入的自然语言问题。

        Returns
        -------
        QueryResult
        """
        if not natural_language or not natural_language.strip():
            return QueryResult(
                success=False,
                intent=INTENT_UNKNOWN,
                cypher="",
                error="查询不能为空",
            )

        intent = self.detect_intent(natural_language)
        entities = _extract_entities(natural_language)

        # 尝试模板匹配
        cypher, params = self._resolve_template(intent, natural_language, entities)

        # 模板未命中 → 尝试 LLM 辅助
        if cypher is None and self._llm is not None:
            cypher, params = self._llm_generate_cypher(natural_language)

        if cypher is None:
            return QueryResult(
                success=False,
                intent=intent,
                cypher="",
                error="无法将该查询转换为图谱查询，请尝试更具体的提问",
            )

        # 安全校验
        if not _is_safe_cypher(cypher):
            logger.warning("拒绝不安全的 Cypher: %s", cypher[:200])
            return QueryResult(
                success=False,
                intent=intent,
                cypher=cypher,
                error="安全校验未通过：仅允许只读查询",
            )

        # 执行
        if self._driver is None:
            return QueryResult(
                success=True,
                intent=intent,
                cypher=cypher,
                parameters=params,
                summary="（翻译成功，未连接数据库，仅返回 Cypher）",
            )

        return self._execute(cypher, params, intent)

    def translate(self, natural_language: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """仅翻译，不执行。返回 ``(cypher, params)``。"""
        if not natural_language or not natural_language.strip():
            return None, {}
        intent = self.detect_intent(natural_language)
        entities = _extract_entities(natural_language)
        cypher, params = self._resolve_template(intent, natural_language, entities)
        if cypher is None and self._llm is not None:
            cypher, params = self._llm_generate_cypher(natural_language)
        if cypher is not None and not _is_safe_cypher(cypher):
            return None, {}
        return cypher, params

    # ------------------------------------------------------------------
    # 意图识别
    # ------------------------------------------------------------------

    def detect_intent(self, query: str) -> str:
        """根据关键词模式匹配查询意图。"""
        entities = _extract_entities(query)
        scores: Dict[str, int] = {}
        for intent, pattern in _INTENT_PATTERNS:
            matches = pattern.findall(query)
            scores[intent] = len(matches)

        # 语义修正：有方剂名 + 组成关键词 → COMPOSITION
        # 有中药名 + 功效关键词 → EFFICACY
        best = max(scores, key=scores.get) if scores else INTENT_UNKNOWN  # type: ignore[arg-type]
        if scores.get(best, 0) == 0:
            # 无关键词命中，按实体类型猜测
            if entities["formula"]:
                return INTENT_COMPOSITION
            if entities["herb"]:
                return INTENT_EFFICACY
            return INTENT_UNKNOWN
        return best

    # ------------------------------------------------------------------
    # 模板解析
    # ------------------------------------------------------------------

    def _resolve_template(
        self,
        intent: str,
        query: str,
        entities: Dict[str, List[str]],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """尝试用预定义模板生成 Cypher + 参数。"""
        template = _CYPHER_TEMPLATES.get(intent)
        if template is None:
            return None, {}

        params: Dict[str, Any] = {}

        if intent == INTENT_COMPOSITION:
            name = self._pick_entity(entities, "formula", query)
            if name is None:
                return None, {}
            params["formula_name"] = name

        elif intent == INTENT_EFFICACY:
            name = self._pick_entity(entities, "herb", query)
            if name is None:
                return None, {}
            params["herb_name"] = name

        elif intent == INTENT_TREATING:
            # 证候名通常不在词典中，尝试启发式抽取
            syndrome = self._extract_syndrome(query)
            if syndrome is None:
                return None, {}
            params["syndrome_name"] = syndrome

        elif intent == INTENT_SIMILAR:
            name = self._pick_entity(entities, "formula", query)
            if name is None:
                return None, {}
            params["formula_name"] = name

        elif intent == INTENT_PATH:
            all_names = entities["formula"] + entities["herb"]
            if len(all_names) < 2:
                return None, {}
            params["src"] = all_names[0]
            params["dst"] = all_names[1]

        elif intent == INTENT_HERB_FORMULAS:
            name = self._pick_entity(entities, "herb", query)
            if name is None:
                return None, {}
            params["herb_name"] = name

        elif intent == INTENT_STATISTICS:
            pass  # 无参数

        return template, params

    # ------------------------------------------------------------------
    # LLM 辅助 Cypher 生成
    # ------------------------------------------------------------------

    _CYPHER_SYSTEM_PROMPT = (
        "你是一个 Neo4j Cypher 查询专家。中医知识图谱包含以下节点标签："
        "Formula(方剂), Herb(中药), Syndrome(证候), Efficacy(功效), "
        "Target(靶点), Pathway(通路)。"
        "关系类型：SOVEREIGN(君药), MINISTER(臣药), ASSISTANT(佐药), ENVOY(使药), "
        "TREATS(治疗), HAS_EFFICACY(有功效), SIMILAR_TO(类似), ENTERS(归经)。\n"
        "请仅返回一条只读 Cypher 查询语句（MATCH ... RETURN ...），不要包含任何解释文字。"
        "禁止使用 CREATE、DELETE、SET、MERGE、REMOVE、DROP 等写操作。"
    )

    def _llm_generate_cypher(
        self, natural_language: str
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """使用 LLM 将自然语言翻译为 Cypher（带安全校验）。"""
        try:
            gateway_result = generate_with_gateway(
                self._llm,
                natural_language,
                self._CYPHER_SYSTEM_PROMPT,
                prompt_version="kg_query_engine.cypher_generation@v1",
                phase="query",
                purpose="kg_cypher_generation",
                task_type="cypher_generation",
                metadata={
                    "prompt_name": "kg_query_engine.cypher_generation",
                    "response_format": "cypher",
                },
            )
            raw = gateway_result.text
            cypher = self._extract_cypher_from_llm(raw)
            if cypher and _is_safe_cypher(cypher):
                return cypher, {"llm_gateway": dict(gateway_result.metadata or {})}
            return None, {}
        except Exception as exc:
            logger.debug("LLM Cypher 生成失败: %s", exc)
            return None, {}

    @staticmethod
    def _extract_cypher_from_llm(raw: str) -> Optional[str]:
        """从 LLM 输出中提取 Cypher 语句。"""
        if not raw:
            return None
        # 尝试提取代码块
        m = re.search(r"```(?:cypher)?\s*\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # 否则取第一个 MATCH 开头的行到末尾
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("MATCH"):
                return stripped
        # 最后尝试返回全文（单行）
        cleaned = raw.strip()
        if cleaned.upper().startswith("MATCH"):
            return cleaned
        return None

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def _execute(self, cypher: str, params: Dict[str, Any], intent: str) -> QueryResult:
        """在 Neo4j 上执行 Cypher 并包装结果。"""
        try:
            with self._driver.driver.session(database=self._driver.database) as session:
                raw_records = session.execute_read(
                    lambda tx: list(tx.run(cypher, **params))
                )
            records = [dict(r) for r in raw_records]
            summary = self._summarize(intent, records)
            return QueryResult(
                success=True,
                intent=intent,
                cypher=cypher,
                parameters=params,
                records=records,
                summary=summary,
            )
        except Exception as exc:
            logger.warning("Cypher 执行失败: %s", exc)
            return QueryResult(
                success=False,
                intent=intent,
                cypher=cypher,
                parameters=params,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # 辅助工具
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_entity(
        entities: Dict[str, List[str]], etype: str, query: str
    ) -> Optional[str]:
        """从抽取结果中选取首个指定类型的实体。"""
        names = entities.get(etype, [])
        return names[0] if names else None

    @staticmethod
    def _extract_syndrome(query: str) -> Optional[str]:
        """启发式提取证候名（"治疗 X"中的 X）。"""
        patterns = [
            re.compile(r"治疗[「「\"]?(.{2,10}?)[」」\"]?(?:的|用|$)"),
            re.compile(r"治[「「\"]?(.{2,10}?)[」」\"]?(?:的|用|怎|如何|$)"),
            re.compile(r"主治[「「\"]?(.{2,10}?)[」」\"]?(?:的|$)"),
            re.compile(r"用于[「「\"]?(.{2,10}?)[」」\"]?(?:的|$)"),
        ]
        for p in patterns:
            m = p.search(query)
            if m:
                candidate = m.group(1).strip()
                if candidate:
                    return candidate
        return None

    @staticmethod
    def _summarize(intent: str, records: List[Dict[str, Any]]) -> str:
        """为查询结果生成简洁的中文摘要。"""
        if not records:
            return "未找到匹配结果"

        n = len(records)

        if intent == INTENT_COMPOSITION:
            herbs = [r.get("herb", "") for r in records if r.get("herb")]
            roles = {r.get("role", "") for r in records if r.get("role")}
            return f"该方剂包含 {len(herbs)} 味药材：{', '.join(herbs)}（角色：{', '.join(roles)}）"

        if intent == INTENT_EFFICACY:
            effs = [r.get("efficacy", "") for r in records]
            return f"功效：{', '.join(effs)}"

        if intent == INTENT_TREATING:
            formulas = [r.get("formula", "") for r in records]
            return f"共 {len(formulas)} 个方剂可治疗：{', '.join(formulas[:10])}"

        if intent == INTENT_SIMILAR:
            names = [r.get("similar_formula", "") for r in records]
            return f"类似方剂：{', '.join(names)}"

        if intent == INTENT_PATH:
            return f"找到 {n} 条路径"

        if intent == INTENT_HERB_FORMULAS:
            formulas = [r.get("formula", "") for r in records]
            return f"含该药材的方剂：{', '.join(formulas[:10])}"

        if intent == INTENT_STATISTICS:
            parts = [f"{r.get('label', '?')}: {r.get('count', 0)}" for r in records]
            return "图谱统计 — " + ", ".join(parts)

        return f"返回 {n} 条记录"
