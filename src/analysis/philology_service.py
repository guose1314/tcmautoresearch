"""文献学服务 - 术语标准化、校勘条目与版本对勘资产。"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Mapping, Sequence

from src.collector.normalizer import Normalizer
from src.core.module_base import BaseModule
from src.data.tcm_lexicon import get_lexicon

_MULTI_SPACE_RE = re.compile(r"\s+")
_CATEGORY_LABELS = {
    "herb": "本草药名",
    "formula": "方剂名",
    "syndrome": "证候术语",
    "theory": "理论术语",
    "efficacy": "功效术语",
    "common": "通用术语",
    None: "术语",
}
_DEFAULT_COLLATION_JUDGEMENTS = {
    "replace": ("异文替换", "出现异文替换，建议结合底本与异本复核。"),
    "delete": ("疑似脱文", "当前文本相较对校见缺字或缺词，建议核对传抄链。"),
    "insert": ("疑似衍文", "当前文本相较对校见增字或增词，建议核对版本来源。"),
}


class PhilologyService(BaseModule):
    """为 Observe 主链补充可配置的文献学结构化输出。"""

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__("philology_service", config)
        cfg = config or {}
        normalizer_config = dict(cfg.get("normalizer_config") or {})
        if "convert_mode" in cfg and "convert_mode" not in normalizer_config:
            normalizer_config["convert_mode"] = cfg.get("convert_mode")

        artifact_output = dict(cfg.get("artifact_output") or {})
        self.normalizer = Normalizer(normalizer_config)
        self.lexicon = get_lexicon()
        self.max_recognized_terms = max(1, int(cfg.get("max_recognized_terms", 12) or 12))
        self.max_collation_diffs = max(1, int(cfg.get("max_collation_diffs", 8) or 8))
        self.max_witnesses = max(1, int(cfg.get("max_witnesses", 3) or 3))
        self.collation_context_window = max(0, int(cfg.get("collation_context_window", 12) or 12))
        self.enable_glossary = bool(cfg.get("enable_glossary", True))
        self.enable_version_collation = bool(cfg.get("enable_version_collation", True))
        self.asset_output_enabled = bool(artifact_output.get("enabled", True))
        self.include_terminology_asset = bool(artifact_output.get("include_terminology_standard_table", True))
        self.include_collation_asset = bool(artifact_output.get("include_collation_entries", True))
        self.include_annotation_report = bool(artifact_output.get("include_annotation_report", True))
        self.terminology_standards = self._normalize_terminology_standards(cfg.get("terminology_standards"))
        self.collation_entry_rules = self._normalize_collation_entry_rules(cfg.get("collation_entry_rules"))

    def _do_initialize(self) -> bool:
        return self.normalizer.initialize()

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raw_text = self._validate_raw_text(context)
        input_metadata = self._extract_input_metadata(context)
        normalization_result = self.normalizer.normalize_text_payload(
            {
                "raw_text": raw_text,
                "metadata": input_metadata,
            }
        )
        normalized_text = str(normalization_result.normalized_text or raw_text)

        term_standardization = self._build_term_standardization(
            raw_text,
            normalized_text,
            normalization_result.term_mappings,
        )
        version_collation = self._build_version_collation(raw_text, context, input_metadata)
        philology_notes = self._build_philology_notes(term_standardization, version_collation)
        philology_assets = self._build_philology_assets(
            input_metadata,
            term_standardization,
            version_collation,
            philology_notes,
        )

        philology_summary = {
            "normalized_text_preview": normalized_text[:160],
            "normalized_text_size": len(normalized_text),
            "normalization_steps": list(normalization_result.normalization_steps),
            "term_standardization": term_standardization,
            "version_collation": version_collation,
            "philology_assets": philology_assets,
            "statistics": {
                "mapping_count": int(term_standardization.get("mapping_count") or 0),
                "orthographic_variant_count": int(term_standardization.get("orthographic_variant_count") or 0),
                "recognized_term_count": int(term_standardization.get("recognized_term_count") or 0),
                "terminology_standard_table_count": int(term_standardization.get("terminology_standard_table_count") or 0),
                "collation_difference_count": int(version_collation.get("difference_count") or 0),
                "collation_entry_count": int(version_collation.get("collation_entry_count") or 0),
                "collation_witness_count": int(version_collation.get("witness_count") or 0),
                "asset_count": int(philology_assets.get("asset_count") or 0),
            },
            "philology_notes": philology_notes,
        }

        merged_metadata = {
            **input_metadata,
            **normalization_result.metadata,
            "philology": {
                "mapping_count": int(term_standardization.get("mapping_count") or 0),
                "orthographic_variant_count": int(term_standardization.get("orthographic_variant_count") or 0),
                "recognized_term_count": int(term_standardization.get("recognized_term_count") or 0),
                "terminology_standard_table_count": int(term_standardization.get("terminology_standard_table_count") or 0),
                "collation_difference_count": int(version_collation.get("difference_count") or 0),
                "collation_entry_count": int(version_collation.get("collation_entry_count") or 0),
                "collation_witness_count": int(version_collation.get("witness_count") or 0),
                "asset_count": int(philology_assets.get("asset_count") or 0),
                "notes": list(philology_notes),
            },
        }

        return {
            "raw_text": normalized_text,
            "metadata": merged_metadata,
            "philology": philology_summary,
            "philology_notes": philology_notes,
            "philology_assets": philology_assets,
        }

    def _do_cleanup(self) -> bool:
        return self.normalizer.cleanup()

    def _validate_raw_text(self, context: Dict[str, Any]) -> str:
        raw_text = context.get("raw_text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("PhilologyService 需要 raw_text 字符串输入")
        return raw_text

    def _extract_input_metadata(self, context: Dict[str, Any]) -> Dict[str, Any]:
        metadata = context.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    def _build_term_standardization(
        self,
        raw_text: str,
        normalized_text: str,
        term_mappings: Dict[str, str],
    ) -> Dict[str, Any]:
        applied_mappings = self._build_applied_mappings(raw_text, normalized_text, term_mappings)
        orthographic_variants = self._build_orthographic_variants(raw_text, normalized_text)
        glossary_notes = self._build_glossary_notes(normalized_text, applied_mappings)
        terminology_standard_table = self._build_terminology_standard_table(
            raw_text,
            normalized_text,
            applied_mappings,
            orthographic_variants,
            glossary_notes,
        )

        return {
            "applied_mappings": applied_mappings,
            "mapping_count": len(applied_mappings),
            "orthographic_variants": orthographic_variants,
            "orthographic_variant_count": len(orthographic_variants),
            "glossary_notes": glossary_notes,
            "recognized_term_count": len(glossary_notes),
            "terminology_standard_table": terminology_standard_table,
            "terminology_standard_table_count": len(terminology_standard_table),
        }

    def _build_applied_mappings(
        self,
        raw_text: str,
        normalized_text: str,
        term_mappings: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        mappings: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for original, canonical in term_mappings.items():
            original_text = str(original or "").strip()
            canonical_text = str(canonical or "").strip()
            if not original_text or not canonical_text:
                continue
            if original_text not in raw_text and canonical_text not in normalized_text:
                continue

            canonical_term, category = self.lexicon.resolve_synonym(canonical_text)
            canonical_value = str(canonical_term or canonical_text)
            mapping_key = (original_text, canonical_value)
            if mapping_key in seen:
                continue
            seen.add(mapping_key)

            mappings.append(
                {
                    "original": original_text,
                    "canonical": canonical_value,
                    "category": category,
                    "label": self._label_for_category(category),
                    "source": "normalizer_term_mapping",
                    "note": f"{original_text} 统一为 {canonical_value}（{self._label_for_category(category)}）",
                }
            )

        return mappings

    def _build_orthographic_variants(self, raw_text: str, normalized_text: str) -> List[Dict[str, Any]]:
        if raw_text == normalized_text:
            return []

        variants: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for diff in self._extract_diff_segments(raw_text, normalized_text, limit=self.max_collation_diffs):
            original_text = str(diff.get("base_text") or "").strip()
            canonical_text = str(diff.get("witness_text") or "").strip()
            if not original_text or not canonical_text:
                continue
            key = (original_text, canonical_text, str(diff.get("difference_type") or ""))
            if key in seen:
                continue
            seen.add(key)
            variants.append(
                {
                    "original": original_text,
                    "canonical": canonical_text,
                    "difference_type": diff.get("difference_type"),
                    "source": "normalized_text",
                    "note": f"检测到异写 {original_text} -> {canonical_text}",
                }
            )
        return variants

    def _build_glossary_notes(
        self,
        normalized_text: str,
        applied_mappings: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not self.enable_glossary:
            return []

        glossary_notes: List[Dict[str, Any]] = []
        seen_terms: set[str] = set()

        for mapping in applied_mappings:
            canonical = str(mapping.get("canonical") or "").strip()
            if canonical:
                self._append_glossary_note(glossary_notes, seen_terms, canonical, original=mapping.get("original"))

        if len(glossary_notes) >= self.max_recognized_terms:
            return glossary_notes[: self.max_recognized_terms]

        for word in sorted(self.lexicon.get_all_words(), key=len, reverse=True):
            candidate = str(word or "").strip()
            if len(candidate) < 2 or candidate in seen_terms:
                continue
            if candidate not in normalized_text:
                continue
            canonical, category = self.lexicon.resolve_synonym(candidate)
            if category == "common" and candidate not in normalized_text[:80]:
                continue
            self._append_glossary_note(glossary_notes, seen_terms, canonical or candidate, original=candidate)
            if len(glossary_notes) >= self.max_recognized_terms:
                break

        return glossary_notes

    def _append_glossary_note(
        self,
        glossary_notes: List[Dict[str, Any]],
        seen_terms: set[str],
        term: str,
        *,
        original: Any = None,
    ) -> None:
        canonical, category = self.lexicon.resolve_synonym(str(term))
        canonical_term = str(canonical or term).strip()
        if not canonical_term or canonical_term in seen_terms:
            return

        seen_terms.add(canonical_term)
        original_text = str(original or canonical_term).strip()
        label = self._label_for_category(category)
        note = f"{canonical_term} 识别为{label}"
        if original_text and original_text != canonical_term:
            note = f"{original_text} 统一为 {canonical_term}，识别为{label}"

        glossary_notes.append(
            {
                "term": canonical_term,
                "original": original_text,
                "category": category,
                "label": label,
                "note": note,
            }
        )

    def _build_terminology_standard_table(
        self,
        raw_text: str,
        normalized_text: str,
        applied_mappings: Sequence[Mapping[str, Any]],
        orthographic_variants: Sequence[Mapping[str, Any]],
        glossary_notes: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        table_index: Dict[str, Dict[str, Any]] = {}

        def _ensure_row(canonical: str, category: str | None = None, *, label: str = "") -> Dict[str, Any]:
            canonical_term = str(canonical or "").strip()
            if not canonical_term:
                canonical_term = "未命名术语"
            row = table_index.get(canonical_term)
            if row is None:
                row = {
                    "canonical": canonical_term,
                    "category": category,
                    "label": label or self._label_for_category(category),
                    "observed_forms": [],
                    "configured_variants": [],
                    "sources": [],
                    "notes": [],
                    "status": "recognized",
                }
                table_index[canonical_term] = row
            else:
                if category and not row.get("category"):
                    row["category"] = category
                if label and not row.get("label"):
                    row["label"] = label
            if not row.get("label"):
                row["label"] = self._label_for_category(row.get("category"))
            return row

        for mapping in applied_mappings:
            row = _ensure_row(
                str(mapping.get("canonical") or "").strip(),
                mapping.get("category"),
                label=str(mapping.get("label") or "").strip(),
            )
            self._append_unique(row["observed_forms"], str(mapping.get("original") or "").strip())
            self._append_unique(row["sources"], str(mapping.get("source") or "normalizer_term_mapping").strip())
            self._append_unique(row["notes"], str(mapping.get("note") or "").strip())
            row["status"] = "standardized"

        for variant in orthographic_variants:
            row = _ensure_row(str(variant.get("canonical") or "").strip())
            self._append_unique(row["observed_forms"], str(variant.get("original") or "").strip())
            self._append_unique(row["sources"], str(variant.get("source") or "normalized_text").strip())
            self._append_unique(row["notes"], str(variant.get("note") or "").strip())
            row["status"] = "standardized"

        for glossary in glossary_notes:
            row = _ensure_row(
                str(glossary.get("term") or "").strip(),
                glossary.get("category"),
                label=str(glossary.get("label") or "").strip(),
            )
            self._append_unique(row["observed_forms"], str(glossary.get("original") or "").strip())
            self._append_unique(row["sources"], "lexicon_glossary")
            self._append_unique(row["notes"], str(glossary.get("note") or "").strip())

        for standard in self.terminology_standards:
            canonical = str(standard.get("canonical") or "").strip()
            if not canonical:
                continue
            matched_forms = [
                token
                for token in [canonical, *(standard.get("variants") or [])]
                if self._text_contains_token(raw_text, token) or self._text_contains_token(normalized_text, token)
            ]
            if not matched_forms and canonical not in table_index:
                continue

            row = _ensure_row(canonical, standard.get("category"), label=str(standard.get("label") or "").strip())
            for matched in matched_forms:
                self._append_unique(row["observed_forms"], str(matched or "").strip())
            for variant in standard.get("variants") or []:
                self._append_unique(row["configured_variants"], str(variant or "").strip())
            self._append_unique(row["sources"], str(standard.get("source") or "config_terminology_standard").strip())
            self._append_unique(row["notes"], str(standard.get("note") or "").strip())
            if matched_forms:
                row["status"] = "standardized"
            elif row.get("status") != "standardized":
                row["status"] = "configured"

        rows: List[Dict[str, Any]] = []
        for canonical in sorted(table_index):
            row = dict(table_index[canonical])
            row["category"] = row.get("category") or None
            row["observed_forms"] = sorted(
                [str(item) for item in row.get("observed_forms") or [] if str(item).strip()]
            )
            row["observed_form_count"] = len(row["observed_forms"])
            row["configured_variants"] = sorted(
                [str(item) for item in row.get("configured_variants") or [] if str(item).strip()]
            )
            row["sources"] = sorted(
                [str(item) for item in row.get("sources") or [] if str(item).strip()]
            )
            row["notes"] = [str(item) for item in row.get("notes") or [] if str(item).strip()]
            rows.append(row)
        return rows

    def _build_version_collation(
        self,
        raw_text: str,
        context: Dict[str, Any],
        input_metadata: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if not self.enable_version_collation:
            return {
                "enabled": False,
                "witness_count": 0,
                "difference_count": 0,
                "witnesses": [],
                "summary": [],
                "collation_entries": [],
                "collation_entry_count": 0,
            }

        witnesses = self._extract_parallel_versions(context)
        witness_reports: List[Dict[str, Any]] = []
        all_collation_entries: List[Dict[str, Any]] = []
        total_differences = 0
        base_text = self._normalize_collation_text(raw_text)

        for witness in witnesses[: self.max_witnesses]:
            witness_text = self._normalize_collation_text(witness.get("text", ""))
            if not witness_text or witness_text == base_text:
                continue

            differences = self._extract_diff_segments(base_text, witness_text, limit=self.max_collation_diffs)
            if not differences:
                continue

            collation_entries = [
                self._build_collation_entry(diff, witness, input_metadata)
                for diff in differences
            ]
            collation_entries = [entry for entry in collation_entries if entry]
            if not collation_entries:
                continue

            report = {
                "witness_title": str(witness.get("title") or ""),
                "witness_urn": str(witness.get("urn") or ""),
                "selection_strategy": str(witness.get("selection_strategy") or ""),
                "version_metadata": dict(witness.get("version_metadata") or {}),
                "difference_count": len(differences),
                "differences": differences,
                "collation_entries": collation_entries,
            }
            witness_reports.append(report)
            all_collation_entries.extend(collation_entries)
            total_differences += len(differences)

        summary = []
        for report in witness_reports:
            witness_label = self._build_version_witness_label(report)
            summary.append(f"与 {witness_label} 存在 {report['difference_count']} 处异文")

        return {
            "enabled": True,
            "witness_count": len(witness_reports),
            "difference_count": total_differences,
            "witnesses": witness_reports,
            "summary": summary,
            "collation_entries": all_collation_entries,
            "collation_entry_count": len(all_collation_entries),
        }

    def _build_collation_entry(
        self,
        difference: Mapping[str, Any],
        witness: Mapping[str, Any],
        input_metadata: Mapping[str, Any],
    ) -> Dict[str, Any]:
        base_text = str(difference.get("base_text") or "").strip()
        witness_text = str(difference.get("witness_text") or "").strip()
        if not base_text and not witness_text:
            return {}

        matched_rule = self._match_collation_entry_rule(difference, witness, input_metadata)
        judgement, default_note = self._resolve_collation_judgement(
            str(difference.get("difference_type") or "").strip(),
            base_text,
            witness_text,
        )
        note = str((matched_rule or {}).get("note") or default_note).strip()

        payload = {
            "difference_type": str(difference.get("difference_type") or "").strip(),
            "base_text": base_text,
            "witness_text": witness_text,
            "base_context": str(difference.get("base_context") or "").strip(),
            "witness_context": str(difference.get("witness_context") or "").strip(),
            "base_span": [
                int(difference.get("base_start") or 0),
                int(difference.get("base_end") or 0),
            ],
            "witness_span": [
                int(difference.get("witness_start") or 0),
                int(difference.get("witness_end") or 0),
            ],
            "witness_title": str(witness.get("title") or "").strip(),
            "witness_urn": str(witness.get("urn") or "").strip(),
            "selection_strategy": str(witness.get("selection_strategy") or "").strip(),
            "version_metadata": dict(witness.get("version_metadata") or {}),
            "judgement": str((matched_rule or {}).get("judgement") or judgement).strip(),
            "severity": str((matched_rule or {}).get("severity") or "info").strip(),
            "note": note,
            "source": str((matched_rule or {}).get("source") or "auto_version_collation").strip(),
        }
        matched_rule_name = str((matched_rule or {}).get("name") or "").strip()
        if matched_rule_name:
            payload["matched_rule"] = matched_rule_name
        canonical_reading = str((matched_rule or {}).get("canonical_reading") or "").strip()
        if canonical_reading:
            payload["canonical_reading"] = canonical_reading
        return payload

    def _extract_parallel_versions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        versions = context.get("parallel_versions") or context.get("version_witnesses") or []
        if not isinstance(versions, list):
            return []

        normalized_versions: List[Dict[str, Any]] = []
        for item in versions:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    normalized_versions.append(item)
            elif isinstance(item, str) and item.strip():
                normalized_versions.append({"text": item, "title": "", "urn": ""})
        return normalized_versions

    def _build_version_witness_label(self, witness_report: Dict[str, Any]) -> str:
        version_metadata = witness_report.get("version_metadata") or {}
        edition = str(version_metadata.get("edition") or "").strip()
        dynasty = str(version_metadata.get("dynasty") or "").strip()
        author = str(version_metadata.get("author") or "").strip()
        title = str(witness_report.get("witness_title") or "").strip()

        label_parts = [part for part in [title, edition, dynasty, author] if part]
        if label_parts:
            return " / ".join(label_parts)
        return str(witness_report.get("witness_urn") or "平行版本")

    def _normalize_collation_text(self, text: Any) -> str:
        normalized = _MULTI_SPACE_RE.sub(" ", str(text or "").replace("\r\n", "\n").replace("\r", "\n"))
        return normalized.strip()

    def _extract_diff_segments(self, base_document_text: str, witness_document_text: str, *, limit: int) -> List[Dict[str, Any]]:
        matcher = difflib.SequenceMatcher(a=base_document_text, b=witness_document_text)
        differences: List[Dict[str, Any]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            base_segment = base_document_text[i1:i2].strip()
            witness_segment = witness_document_text[j1:j2].strip()
            if not base_segment and not witness_segment:
                continue
            if len(base_segment) > 24 or len(witness_segment) > 24:
                continue
            if not self._looks_like_textual_difference(base_segment, witness_segment):
                continue

            differences.append(
                {
                    "difference_type": tag,
                    "base_text": base_segment,
                    "witness_text": witness_segment,
                    "base_start": i1,
                    "base_end": i2,
                    "witness_start": j1,
                    "witness_end": j2,
                    "base_context": self._extract_context_window(base_document_text, i1, i2),
                    "witness_context": self._extract_context_window(witness_document_text, j1, j2),
                }
            )
            if len(differences) >= limit:
                break
        return differences

    def _extract_context_window(self, text: str, start: int, end: int) -> str:
        left = max(int(start or 0) - self.collation_context_window, 0)
        right = min(int(end or 0) + self.collation_context_window, len(text))
        return str(text[left:right] or "").strip()

    def _looks_like_textual_difference(self, base_segment: str, witness_segment: str) -> bool:
        sample = f"{base_segment}{witness_segment}".strip()
        if not sample:
            return False
        return any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in sample)

    def _build_philology_assets(
        self,
        input_metadata: Mapping[str, Any],
        term_standardization: Mapping[str, Any],
        version_collation: Mapping[str, Any],
        philology_notes: Sequence[str],
    ) -> Dict[str, Any]:
        terminology_standard_table = list(term_standardization.get("terminology_standard_table") or [])
        collation_entries = list(version_collation.get("collation_entries") or [])
        annotation_report = self._build_annotation_report(
            input_metadata,
            term_standardization,
            version_collation,
            philology_notes,
        )

        assets = {
            "terminology_standard_table": terminology_standard_table if self.asset_output_enabled and self.include_terminology_asset else [],
            "collation_entries": collation_entries if self.asset_output_enabled and self.include_collation_asset else [],
            "annotation_report": annotation_report if self.asset_output_enabled and self.include_annotation_report else {},
        }
        assets["asset_count"] = sum(
            1
            for payload in (
                assets.get("terminology_standard_table"),
                assets.get("collation_entries"),
                assets.get("annotation_report"),
            )
            if payload not in (None, "", [], {})
        )
        return assets

    def _build_annotation_report(
        self,
        input_metadata: Mapping[str, Any],
        term_standardization: Mapping[str, Any],
        version_collation: Mapping[str, Any],
        philology_notes: Sequence[str],
    ) -> Dict[str, Any]:
        version_metadata = input_metadata.get("version_metadata") if isinstance(input_metadata.get("version_metadata"), dict) else {}
        return {
            "title": self._resolve_title(input_metadata),
            "source_type": str(input_metadata.get("source_type") or input_metadata.get("source") or "").strip(),
            "source_file": str(input_metadata.get("source_file") or "").strip(),
            "work_title": str(version_metadata.get("work_title") or input_metadata.get("work_title") or "").strip(),
            "fragment_title": str(version_metadata.get("fragment_title") or input_metadata.get("fragment_title") or "").strip(),
            "mapping_count": int(term_standardization.get("mapping_count") or 0),
            "recognized_term_count": int(term_standardization.get("recognized_term_count") or 0),
            "terminology_standard_table_count": int(term_standardization.get("terminology_standard_table_count") or 0),
            "collation_difference_count": int(version_collation.get("difference_count") or 0),
            "collation_entry_count": int(version_collation.get("collation_entry_count") or 0),
            "collation_witness_count": int(version_collation.get("witness_count") or 0),
            "notes": [str(note) for note in philology_notes if str(note).strip()],
        }

    def _build_philology_notes(
        self,
        term_standardization: Dict[str, Any],
        version_collation: Dict[str, Any],
    ) -> List[str]:
        notes: List[str] = []
        mapping_count = int(term_standardization.get("mapping_count") or 0)
        orthographic_variant_count = int(term_standardization.get("orthographic_variant_count") or 0)
        recognized_term_count = int(term_standardization.get("recognized_term_count") or 0)
        terminology_standard_table_count = int(term_standardization.get("terminology_standard_table_count") or 0)
        difference_count = int(version_collation.get("difference_count") or 0)
        collation_entry_count = int(version_collation.get("collation_entry_count") or 0)

        if mapping_count:
            notes.append(f"术语标准化完成 {mapping_count} 处映射")
        if orthographic_variant_count:
            notes.append(f"识别 {orthographic_variant_count} 处异体或异写")
        if recognized_term_count:
            notes.append(f"生成 {recognized_term_count} 条术语训诂注记")
        if terminology_standard_table_count:
            notes.append(f"整理 {terminology_standard_table_count} 条术语标准表记录")
        if difference_count:
            notes.append(f"版本对勘发现 {difference_count} 处异文，建议人工复核")
        if collation_entry_count:
            notes.append(f"输出 {collation_entry_count} 条可复用校勘条目")
        return notes

    def _resolve_collation_judgement(
        self,
        difference_type: str,
        base_text: str,
        witness_text: str,
    ) -> tuple[str, str]:
        base_canonical, base_category = self.lexicon.resolve_synonym(base_text)
        witness_canonical, witness_category = self.lexicon.resolve_synonym(witness_text)
        normalized_base = str(base_canonical or base_text).strip()
        normalized_witness = str(witness_canonical or witness_text).strip()
        if normalized_base and normalized_base == normalized_witness:
            label = self._label_for_category(base_category or witness_category)
            return (
                "术语异写",
                f"{base_text} 与 {witness_text} 归并为同一{label} {normalized_base}，可视为异写。",
            )
        return _DEFAULT_COLLATION_JUDGEMENTS.get(
            difference_type,
            ("异文", "检测到版本异文，建议结合版本谱系与上下文复核。"),
        )

    def _match_collation_entry_rule(
        self,
        difference: Mapping[str, Any],
        witness: Mapping[str, Any],
        input_metadata: Mapping[str, Any],
    ) -> Dict[str, Any] | None:
        searchable_text = " ".join(
            part
            for part in (
                str(difference.get("base_text") or "").strip(),
                str(difference.get("witness_text") or "").strip(),
                str(difference.get("base_context") or "").strip(),
                str(difference.get("witness_context") or "").strip(),
            )
            if part
        )
        title_parts = " ".join(
            part
            for part in (
                self._resolve_title(input_metadata),
                str((input_metadata.get("version_metadata") or {}).get("work_title") or "").strip() if isinstance(input_metadata.get("version_metadata"), dict) else "",
                str((input_metadata.get("version_metadata") or {}).get("fragment_title") or "").strip() if isinstance(input_metadata.get("version_metadata"), dict) else "",
                str(witness.get("title") or "").strip(),
            )
            if part
        )

        for rule in self.collation_entry_rules:
            match_terms = [str(item) for item in rule.get("match_terms") or [] if str(item).strip()]
            title_terms = [str(item) for item in rule.get("applies_to_titles") or [] if str(item).strip()]
            if match_terms and not any(self._text_contains_token(searchable_text, term) for term in match_terms):
                continue
            if title_terms and not any(self._text_contains_token(title_parts, term) for term in title_terms):
                continue
            return dict(rule)
        return None

    def _normalize_terminology_standards(self, payload: Any) -> List[Dict[str, Any]]:
        standards: List[Dict[str, Any]] = []
        if not isinstance(payload, list):
            return standards
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            canonical = str(item.get("canonical") or item.get("term") or "").strip()
            if not canonical:
                continue
            variants = self._normalize_string_list(item.get("variants") or item.get("observed_forms") or [])
            category = str(item.get("category") or "").strip() or None
            standards.append(
                {
                    "canonical": canonical,
                    "variants": variants,
                    "category": category,
                    "label": str(item.get("label") or self._label_for_category(category)).strip(),
                    "source": str(item.get("source") or "config_terminology_standard").strip(),
                    "note": str(item.get("note") or "").strip(),
                }
            )
        return standards

    def _normalize_collation_entry_rules(self, payload: Any) -> List[Dict[str, Any]]:
        rules: List[Dict[str, Any]] = []
        if not isinstance(payload, list):
            return rules
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            match_terms = self._normalize_string_list(item.get("match_terms") or item.get("variants") or [])
            applies_to_titles = self._normalize_string_list(item.get("applies_to_titles") or item.get("titles") or [])
            judgement = str(item.get("judgement") or "").strip()
            note = str(item.get("note") or "").strip()
            canonical_reading = str(item.get("canonical_reading") or item.get("preferred_reading") or "").strip()
            if not match_terms and not applies_to_titles and not judgement and not note and not canonical_reading:
                continue
            rules.append(
                {
                    "name": str(item.get("name") or judgement or "collation_rule").strip(),
                    "match_terms": match_terms,
                    "applies_to_titles": applies_to_titles,
                    "judgement": judgement,
                    "note": note,
                    "canonical_reading": canonical_reading,
                    "severity": str(item.get("severity") or "info").strip(),
                    "source": str(item.get("source") or "config_collation_rule").strip(),
                }
            )
        return rules

    def _normalize_string_list(self, payload: Any) -> List[str]:
        if isinstance(payload, str):
            payload = [payload]
        if not isinstance(payload, list):
            return []
        return [str(item).strip() for item in payload if str(item).strip()]

    def _resolve_title(self, metadata: Mapping[str, Any]) -> str:
        version_metadata = metadata.get("version_metadata") if isinstance(metadata.get("version_metadata"), dict) else {}
        return str(
            metadata.get("title")
            or metadata.get("fragment_title")
            or version_metadata.get("fragment_title")
            or version_metadata.get("work_title")
            or metadata.get("source_file")
            or ""
        ).strip()

    @staticmethod
    def _append_unique(container: List[str], value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in container:
            container.append(normalized)

    @staticmethod
    def _text_contains_token(text: str, token: str) -> bool:
        normalized_text = str(text or "").strip()
        normalized_token = str(token or "").strip()
        if not normalized_text or not normalized_token:
            return False
        return normalized_token in normalized_text

    def _label_for_category(self, category: str | None) -> str:
        return _CATEGORY_LABELS.get(category, _CATEGORY_LABELS[None])