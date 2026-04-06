"""数据挖掘服务 — 关联规则、聚类分析、频繁项集、预测建模。"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from src.core.module_base import BaseModule
from src.research.data_miner import DataMiner as _ResearchDataMiner
from src.research.data_miner import StatisticalDataMiner

logger = logging.getLogger(__name__)

_METHOD_EXECUTION_ORDER = (
    "frequent_itemsets",
    "association_rules",
    "clustering",
    "latent_topics",
    "frequency_chi_square",
    "predictive_modeling",
)


class DataMiningService(BaseModule):
    """3.0 分析域数据挖掘服务。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("data_mining_service", config)
        self._base_miner = _ResearchDataMiner
        self.min_support = float(self.config.get("min_support", 0.3))
        self.min_confidence = float(self.config.get("min_confidence", 0.6))
        self.min_lift = float(self.config.get("min_lift", 1.0))
        self.max_itemset_size = int(self.config.get("max_itemset_size", 3))
        self.max_rules = int(self.config.get("max_rules", 20))
        self.default_methods = self._normalize_methods(
            self.config.get("default_methods")
            or ["association_rules", "clustering", "frequent_itemsets"]
        )

    def _do_initialize(self) -> bool:
        logger.info(
            "DataMiningService 初始化完成: min_support=%.2f, min_confidence=%.2f",
            self.min_support,
            self.min_confidence,
        )
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        methods = self._resolve_methods(context)
        records, transactions = self._resolve_execution_inputs(context)
        items = self._resolve_items(context, records, transactions)
        result = self._build_base_result(records, transactions, items)
        pattern_payload = self._prepare_pattern_mining_payload(context, methods, transactions)
        self._apply_method_results(result, methods, records, items, context, pattern_payload)
        result["summary"] = self._build_summary(result)
        return result

    def _do_cleanup(self) -> bool:
        return True

    def _resolve_execution_inputs(
        self,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
        records = self._resolve_records(context)
        transactions = self._resolve_transactions(context, records)

        if not records and transactions:
            records = self._build_records_from_transactions(transactions)
        if not transactions and records:
            transactions = self._derive_transactions_from_records(records)
        if not records and not transactions:
            raise ValueError("DataMiningService 需要 records 或 transactions 输入")

        return records, transactions

    def _build_base_result(
        self,
        records: Sequence[Dict[str, Any]],
        transactions: Sequence[Sequence[str]],
        items: Sequence[str],
    ) -> Dict[str, Any]:
        return {
            "record_count": len(records),
            "transaction_count": len(transactions),
            "item_count": len(items),
            "items": list(items),
            "methods_executed": [],
        }

    def _prepare_pattern_mining_payload(
        self,
        context: Dict[str, Any],
        methods: Sequence[str],
        transactions: Sequence[Sequence[str]],
    ) -> Dict[str, Any]:
        transaction_sets = [frozenset(tx) for tx in transactions if tx]
        support_map: Dict[FrozenSet[str], float] = {}
        count_map: Dict[FrozenSet[str], int] = {}
        frequent_payload: Optional[Dict[str, Any]] = None

        if self._requires_pattern_mining(methods):
            support_map, count_map = self._mine_frequent_itemsets(
                transaction_sets,
                float(context.get("min_support", self.min_support)),
                int(context.get("max_itemset_size", self.max_itemset_size)),
            )
            frequent_payload = self._format_frequent_itemsets(
                support_map,
                count_map,
                len(transaction_sets),
            )

        return {
            "transaction_sets": transaction_sets,
            "support_map": support_map,
            "count_map": count_map,
            "frequent_payload": frequent_payload,
        }

    def _requires_pattern_mining(self, methods: Sequence[str]) -> bool:
        return "frequent_itemsets" in methods or "association_rules" in methods

    def _apply_method_results(
        self,
        result: Dict[str, Any],
        methods: Sequence[str],
        records: Sequence[Dict[str, Any]],
        items: Sequence[str],
        context: Dict[str, Any],
        pattern_payload: Dict[str, Any],
    ) -> None:
        for method in _METHOD_EXECUTION_ORDER:
            if method not in methods:
                continue

            payload = self._build_method_payload(
                method,
                records,
                items,
                context,
                pattern_payload,
            )
            if payload is None:
                continue

            result[method] = payload
            result["methods_executed"].append(method)

    def _build_method_payload(
        self,
        method: str,
        records: Sequence[Dict[str, Any]],
        items: Sequence[str],
        context: Dict[str, Any],
        pattern_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        transaction_count = len(pattern_payload["transaction_sets"])
        if method == "frequent_itemsets":
            return pattern_payload["frequent_payload"] or self._build_empty_frequent_itemsets_payload(
                transaction_count
            )
        if method == "association_rules":
            return self._build_association_rules(
                pattern_payload["support_map"],
                transaction_count,
                float(context.get("min_confidence", self.min_confidence)),
                float(context.get("min_lift", self.min_lift)),
                int(context.get("max_rules", self.max_rules)),
            )
        if method == "clustering":
            return self._run_clustering(records, items)
        if method == "latent_topics":
            return self._base_miner.latent_topics(records, items)
        if method == "frequency_chi_square":
            return StatisticalDataMiner.frequency_and_chi_square(list(records), list(items))
        if method == "predictive_modeling":
            return self._run_predictive_modeling(records, context)
        return None

    def _build_empty_frequent_itemsets_payload(self, transaction_count: int) -> Dict[str, Any]:
        return {
            "itemsets": [],
            "transaction_count": transaction_count,
            "max_itemset_size": 0,
        }

    def _resolve_methods(self, context: Dict[str, Any]) -> List[str]:
        if "methods" not in context:
            return list(self.default_methods)
        return self._normalize_methods(context.get("methods"))

    def _normalize_methods(self, raw_methods: Any) -> List[str]:
        aliases = {
            "association": "association_rules",
            "rules": "association_rules",
            "frequent": "frequent_itemsets",
            "itemsets": "frequent_itemsets",
            "cluster": "clustering",
            "clustering_factor": "clustering",
            "latent": "latent_topics",
            "topics": "latent_topics",
            "predict": "predictive_modeling",
            "prediction": "predictive_modeling",
            "stats": "frequency_chi_square",
        }
        if isinstance(raw_methods, str):
            candidates = [raw_methods]
        else:
            candidates = list(raw_methods or [])
        normalized: List[str] = []
        seen = set()
        for method in candidates:
            value = str(method or "").strip().lower()
            if not value:
                continue
            canonical = aliases.get(value, value)
            if canonical in seen:
                continue
            seen.add(canonical)
            normalized.append(canonical)
        return normalized

    def _resolve_records(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_records = (
            context.get("records")
            or context.get("formula_records")
            or context.get("mining_records")
            or []
        )
        records: List[Dict[str, Any]] = []
        for record in raw_records:
            if isinstance(record, dict):
                normalized = dict(record)
                items = self._extract_record_items(normalized)
                if "herbs" not in normalized:
                    normalized["herbs"] = items
                if "formula" not in normalized:
                    normalized["formula"] = normalized.get("name") or normalized.get("title") or f"record_{len(records) + 1}"
                records.append(normalized)
        return records

    def _resolve_transactions(
        self,
        context: Dict[str, Any],
        records: Sequence[Dict[str, Any]],
    ) -> List[List[str]]:
        raw_transactions = context.get("transactions")
        if raw_transactions:
            return [self._normalize_transaction(tx) for tx in raw_transactions if self._normalize_transaction(tx)]
        return self._derive_transactions_from_records(records)

    def _derive_transactions_from_records(self, records: Sequence[Dict[str, Any]]) -> List[List[str]]:
        transactions: List[List[str]] = []
        for record in records:
            items = self._extract_record_items(record)
            if items:
                transactions.append(items)
        return transactions

    def _build_records_from_transactions(self, transactions: Sequence[Sequence[str]]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for index, tx in enumerate(transactions, start=1):
            normalized = self._normalize_transaction(tx)
            if not normalized:
                continue
            records.append(
                {
                    "formula": f"record_{index}",
                    "herbs": normalized,
                }
            )
        return records

    def _resolve_items(
        self,
        context: Dict[str, Any],
        records: Sequence[Dict[str, Any]],
        transactions: Sequence[Sequence[str]],
    ) -> List[str]:
        explicit = context.get("herbs") or context.get("items") or context.get("features") or []
        if explicit:
            return sorted({str(item).strip() for item in explicit if str(item).strip()})

        items = set()
        for tx in transactions:
            items.update(tx)
        if not items:
            for record in records:
                items.update(self._extract_record_items(record))
        return sorted(items)

    def _extract_record_items(self, record: Dict[str, Any]) -> List[str]:
        for key in ("herbs", "items", "ingredients", "entities", "tokens"):
            value = record.get(key)
            if value:
                return self._normalize_transaction(value)
        return []

    def _normalize_transaction(self, transaction: Any) -> List[str]:
        items: List[str] = []
        if isinstance(transaction, dict):
            for key in ("herbs", "items", "ingredients", "entities", "tokens"):
                if key in transaction:
                    return self._normalize_transaction(transaction.get(key))
            return []

        iterable: Iterable[Any]
        if isinstance(transaction, (list, tuple, set)):
            iterable = transaction
        else:
            iterable = [transaction]

        for item in iterable:
            if isinstance(item, dict):
                name = item.get("name") or item.get("text") or item.get("herb") or item.get("value")
            else:
                name = item
            text = str(name or "").strip()
            if text and text not in items:
                items.append(text)
        return sorted(items)

    def _mine_frequent_itemsets(
        self,
        transaction_sets: Sequence[FrozenSet[str]],
        min_support: float,
        max_itemset_size: int,
    ) -> Tuple[Dict[FrozenSet[str], float], Dict[FrozenSet[str], int]]:
        support_map: Dict[FrozenSet[str], float] = {}
        count_map: Dict[FrozenSet[str], int] = {}
        transaction_count = len(transaction_sets)
        if transaction_count == 0:
            return support_map, count_map

        item_counter = Counter()
        for tx in transaction_sets:
            for item in tx:
                item_counter[frozenset([item])] += 1

        current_level = {
            itemset: count
            for itemset, count in item_counter.items()
            if count / transaction_count >= min_support
        }
        for itemset, count in current_level.items():
            support_map[itemset] = count / transaction_count
            count_map[itemset] = count

        level = 2
        previous_level = set(current_level.keys())
        while previous_level and level <= max_itemset_size:
            candidates = self._generate_candidates(previous_level, level)
            if not candidates:
                break

            next_level: Dict[FrozenSet[str], int] = {}
            for candidate in candidates:
                count = sum(1 for tx in transaction_sets if candidate.issubset(tx))
                support = count / transaction_count
                if support >= min_support:
                    next_level[candidate] = count
                    support_map[candidate] = support
                    count_map[candidate] = count

            previous_level = set(next_level.keys())
            level += 1

        return support_map, count_map

    def _generate_candidates(
        self,
        previous_level: Iterable[FrozenSet[str]],
        target_size: int,
    ) -> List[FrozenSet[str]]:
        candidates = set()
        previous_items = list(previous_level)
        previous_lookup = set(previous_items)
        previous_list = sorted(previous_items, key=lambda itemset: sorted(itemset))
        for left_index, left in enumerate(previous_list):
            for right in previous_list[left_index + 1:]:
                candidate = left.union(right)
                if len(candidate) != target_size:
                    continue
                all_subsets_frequent = all(
                    frozenset(subset) in previous_lookup
                    for subset in combinations(candidate, target_size - 1)
                )
                if all_subsets_frequent:
                    candidates.add(frozenset(candidate))
        return sorted(candidates, key=lambda itemset: (len(itemset), sorted(itemset)))

    def _format_frequent_itemsets(
        self,
        support_map: Dict[FrozenSet[str], float],
        count_map: Dict[FrozenSet[str], int],
        transaction_count: int,
    ) -> Dict[str, Any]:
        itemsets = [
            {
                "items": sorted(itemset),
                "size": len(itemset),
                "support": round(float(support_map[itemset]), 4),
                "count": int(count_map[itemset]),
            }
            for itemset in support_map
        ]
        itemsets.sort(key=lambda entry: (entry["size"], entry["support"], entry["count"]), reverse=True)
        return {
            "itemsets": itemsets,
            "transaction_count": transaction_count,
            "max_itemset_size": max((entry["size"] for entry in itemsets), default=0),
        }

    def _iter_association_rule_partitions(
        self,
        itemset: FrozenSet[str],
    ) -> Iterable[Tuple[FrozenSet[str], FrozenSet[str]]]:
        ordered_items = sorted(itemset)
        for subset_size in range(1, len(ordered_items)):
            for antecedent_tuple in combinations(ordered_items, subset_size):
                antecedent = frozenset(antecedent_tuple)
                consequent = frozenset(itemset.difference(antecedent))
                yield antecedent, consequent

    def _build_association_rule_entry(
        self,
        antecedent: FrozenSet[str],
        consequent: FrozenSet[str],
        support: float,
        support_map: Dict[FrozenSet[str], float],
        min_confidence: float,
        min_lift: float,
    ) -> Optional[Dict[str, Any]]:
        antecedent_support = support_map.get(antecedent)
        consequent_support = support_map.get(consequent)
        if not antecedent_support or not consequent_support:
            return None

        confidence = support / antecedent_support
        if confidence < min_confidence:
            return None

        lift = self._resolve_rule_lift(confidence, consequent_support)
        if lift < min_lift:
            return None

        leverage = support - antecedent_support * consequent_support
        conviction = self._resolve_rule_conviction(confidence, consequent_support)
        return {
            "antecedent": sorted(antecedent),
            "consequent": sorted(consequent),
            "support": round(float(support), 4),
            "confidence": round(float(confidence), 4),
            "lift": round(float(lift), 4),
            "leverage": round(float(leverage), 4),
            "conviction": round(float(conviction), 4) if conviction is not None else None,
        }

    def _resolve_rule_lift(self, confidence: float, consequent_support: float) -> float:
        if consequent_support <= 0:
            return 0.0
        return confidence / consequent_support

    def _resolve_rule_conviction(
        self,
        confidence: float,
        consequent_support: float,
    ) -> Optional[float]:
        if confidence >= 1.0:
            return None
        denominator = 1.0 - confidence
        if denominator <= 0:
            return None
        return (1.0 - consequent_support) / denominator

    def _collect_association_rules_for_itemset(
        self,
        itemset: FrozenSet[str],
        support: float,
        support_map: Dict[FrozenSet[str], float],
        min_confidence: float,
        min_lift: float,
    ) -> List[Dict[str, Any]]:
        if len(itemset) < 2:
            return []

        rules: List[Dict[str, Any]] = []
        for antecedent, consequent in self._iter_association_rule_partitions(itemset):
            rule = self._build_association_rule_entry(
                antecedent,
                consequent,
                support,
                support_map,
                min_confidence,
                min_lift,
            )
            if rule is not None:
                rules.append(rule)
        return rules

    def _sort_and_limit_association_rules(
        self,
        rules: List[Dict[str, Any]],
        max_rules: int,
    ) -> Dict[str, Any]:
        rules.sort(
            key=lambda entry: (
                entry["lift"],
                entry["confidence"],
                entry["support"],
                len(entry["antecedent"]),
            ),
            reverse=True,
        )
        limited_rules = rules[:max_rules]
        return {"rules": limited_rules, "rule_count": len(limited_rules)}

    def _build_association_rules(
        self,
        support_map: Dict[FrozenSet[str], float],
        transaction_count: int,
        min_confidence: float,
        min_lift: float,
        max_rules: int,
    ) -> Dict[str, Any]:
        if transaction_count == 0:
            return {"rules": [], "rule_count": 0}

        rules: List[Dict[str, Any]] = []
        for itemset, support in support_map.items():
            rules.extend(
                self._collect_association_rules_for_itemset(
                    itemset,
                    support,
                    support_map,
                    min_confidence,
                    min_lift,
                )
            )
        return self._sort_and_limit_association_rules(rules, max_rules)

    def _run_clustering(
        self,
        records: Sequence[Dict[str, Any]],
        items: Sequence[str],
    ) -> Dict[str, Any]:
        if not records or not items:
            return {"clusters": [], "factors": [], "cluster_summary": []}

        payload = self._base_miner.cluster(list(records), list(items))
        payload["cluster_summary"] = self._summarize_clusters(records, payload.get("clusters") or [])
        return payload

    def _summarize_clusters(
        self,
        records: Sequence[Dict[str, Any]],
        cluster_rows: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        grouped_formulas: Dict[int, List[str]] = defaultdict(list)
        grouped_items: Dict[int, Counter[str]] = defaultdict(Counter)
        record_by_formula = {
            str(record.get("formula") or record.get("name") or record.get("title") or f"record_{index + 1}"): record
            for index, record in enumerate(records)
        }

        for row in cluster_rows:
            cluster_id = int(row.get("cluster", 0))
            formula = str(row.get("formula") or "")
            grouped_formulas[cluster_id].append(formula)
            record = record_by_formula.get(formula)
            if record:
                grouped_items[cluster_id].update(self._extract_record_items(record))

        summary: List[Dict[str, Any]] = []
        for cluster_id in sorted(grouped_formulas):
            top_items = [
                {"item": item, "count": count}
                for item, count in grouped_items[cluster_id].most_common(5)
            ]
            summary.append(
                {
                    "cluster": cluster_id,
                    "size": len(grouped_formulas[cluster_id]),
                    "formulas": grouped_formulas[cluster_id],
                    "top_items": top_items,
                }
            )
        return summary

    def _run_predictive_modeling(
        self,
        records: Sequence[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        if context.get("time_series_data") or context.get("dose_response_data"):
            return StatisticalDataMiner.time_series_and_dose_response(list(records), context)

        numeric_pairs = []
        for record in records:
            if record.get("dose_total") is None or record.get("response") is None:
                continue
            numeric_pairs.append((float(record["dose_total"]), float(record["response"])))

        if len(numeric_pairs) < 2:
            return {"model": "insufficient_data"}

        doses = np.array([pair[0] for pair in numeric_pairs], dtype=float)
        responses = np.array([pair[1] for pair in numeric_pairs], dtype=float)
        slope, intercept = np.polyfit(doses, responses, deg=1)
        predicted = slope * doses + intercept
        ss_res = float(np.sum((responses - predicted) ** 2))
        ss_tot = float(np.sum((responses - np.mean(responses)) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return {
            "model": "linear_regression",
            "slope": round(float(slope), 4),
            "intercept": round(float(intercept), 4),
            "r_squared": round(float(r_squared), 4),
        }

    def _build_summary(self, result: Dict[str, Any]) -> Dict[str, Any]:
        summary = {
            "record_count": result.get("record_count", 0),
            "transaction_count": result.get("transaction_count", 0),
            "item_count": result.get("item_count", 0),
            "method_count": len(result.get("methods_executed") or []),
        }
        frequent_itemsets = result.get("frequent_itemsets", {})
        association_rules = result.get("association_rules", {})
        clustering = result.get("clustering", {})
        summary["frequent_itemset_count"] = len(frequent_itemsets.get("itemsets") or [])
        summary["association_rule_count"] = len(association_rules.get("rules") or [])
        summary["cluster_count"] = len(clustering.get("cluster_summary") or [])
        return summary
