"""BibTeX 自动引用格式化管理器。"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from src.core.module_base import BaseModule


@dataclass
class CitationEntry:
    citation_key: str
    entry_type: str
    title: str
    authors: List[str] = field(default_factory=list)
    year: str = ""
    journal: str = ""
    booktitle: str = ""
    publisher: str = ""
    volume: str = ""
    number: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    note: str = ""
    source: str = ""
    source_type: str = ""
    source_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CitationLibrary:
    entries: List[CitationEntry] = field(default_factory=list)
    format: str = "bibtex"
    generated_at: str = ""
    duplicates_merged: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "format": self.format,
            "generated_at": self.generated_at,
            "duplicates_merged": self.duplicates_merged,
            "stats": self.stats,
        }


class CitationManager(BaseModule):
    """将文献元数据规整为 BibTeX 与 GB/T 7714 引用格式。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("citation_manager", config)
        self.default_entry_type = str((config or {}).get("default_entry_type", "article"))
        self.include_abstract = bool((config or {}).get("include_abstract", False))
        self.output_format = str((config or {}).get("format", "bibtex")).strip() or "bibtex"
        self.merge_duplicates = bool((config or {}).get("merge_duplicates", True))
        self.export_outputs = bool((config or {}).get("export_outputs", False))
        self.default_output_dir = str((config or {}).get("output_dir", "")).strip()
        self._inline_citation_registry: Dict[str, int] = {}
        self._inline_citation_next_index = 1

    def _do_initialize(self) -> bool:
        self.logger.info("CitationManager 初始化完成")
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raw_records = self._resolve_record_inputs(context)
        entries = self.build_entries(raw_records)
        duplicates_merged = 0
        if self.merge_duplicates and entries:
            entries, duplicates_merged = self._merge_duplicate_entries(entries)
        bibtex = self.render_bibtex(entries)
        gbt7714 = self.render_gbt7714(self._sort_entries_for_bibliography(entries))
        selected_format = self._normalize_output_format(context.get("format") or self.output_format)
        formatted_references = gbt7714 if selected_format.lower().startswith("gb") else bibtex
        library = self.build_library(entries, selected_format, duplicates_merged)
        output_files = self._maybe_export_outputs(context, library, bibtex, gbt7714)
        return {
            "citation_count": len(entries),
            "entries": [entry.to_dict() for entry in entries],
            "bibtex": bibtex,
            "gbt7714": gbt7714,
            "formatted_references": formatted_references,
            "format": selected_format,
            "duplicates_merged": duplicates_merged,
            "library": library.to_dict(),
            "output_files": output_files,
        }

    def build_entries(self, records: Iterable[Any]) -> List[CitationEntry]:
        entries: List[CitationEntry] = []
        used_keys: Dict[str, int] = {}
        for index, record in enumerate(records, start=1):
            entry = self._normalize_record(self._coerce_record_dict(record), index=index)
            entry.citation_key = self._ensure_unique_key(entry.citation_key, used_keys)
            entries.append(entry)
        return entries

    def render_bibtex(self, entries: Iterable[CitationEntry]) -> str:
        rendered = [self.format_entry(entry) for entry in entries]
        return "\n\n".join(item for item in rendered if item)

    def render_gbt7714(self, entries: Iterable[CitationEntry]) -> str:
        lines = []
        for index, entry in enumerate(entries, start=1):
            line = self.format_gbt_entry(entry)
            if line:
                lines.append(f"[{index}] {line}")
        return "\n".join(lines)

    def format_citation(self, record: Any) -> str:
        """将单条记录格式化为 GB/T 7714 引用字符串。"""
        entry = self._normalize_record(self._coerce_record_dict(record), index=1)
        return self.format_gbt_entry(entry)

    def generate_bibliography(self, records: Iterable[Any]) -> str:
        """生成自动去重、排序、编号后的参考文献列表。"""
        entries = self.build_entries(records)
        if self.merge_duplicates and entries:
            entries, _ = self._merge_duplicate_entries(entries)
        return self.render_gbt7714(self._sort_entries_for_bibliography(entries))

    def insert_inline_citation(self, text: str, record: Any) -> str:
        """在文本中插入数字型行内引用标记。"""
        base_text = str(text or "")
        entry = self._normalize_record(self._coerce_record_dict(record), index=1)
        dedupe_key = self._dedupe_key(entry)
        citation_index = self._inline_citation_registry.get(dedupe_key)
        if citation_index is None:
            citation_index = self._inline_citation_next_index
            self._inline_citation_registry[dedupe_key] = citation_index
            self._inline_citation_next_index += 1

        marker = f"[{citation_index}]"
        if marker in base_text:
            return base_text

        stripped = base_text.rstrip()
        if not stripped:
            return marker
        if stripped[-1] in "。；;，,！!？?）)】]":
            return stripped[:-1] + marker + stripped[-1]
        return stripped + marker

    def format_gbt_entry(self, entry: CitationEntry) -> str:
        authors = self._format_authors_gbt(entry.authors)
        title = entry.title.strip() or "Untitled"

        if entry.entry_type == "article":
            journal = entry.journal or "未知刊名"
            suffix = self._join_with_sep(
                [
                    self._join_volume_issue(entry.volume, entry.number),
                    self._normalize_pages(entry.pages),
                ],
                sep=": ",
            )
            parts = [
                f"{authors}. {title}[J]",
                f"{journal}, {entry.year}" if entry.year else journal,
                suffix,
            ]
            extra = self._build_extra_note(entry)
            return self._append_extra(self._join_sentence(parts), extra)

        if entry.entry_type == "book":
            publisher = entry.publisher or "未知出版社"
            parts = [
                f"{authors}. {title}[M]",
                f"{publisher}, {entry.year}" if entry.year else publisher,
            ]
            extra = self._build_extra_note(entry)
            return self._append_extra(self._join_sentence(parts), extra)

        if entry.entry_type in {"thesis", "phdthesis", "mastersthesis", "dissertation"}:
            publisher = entry.publisher or "未知授予单位"
            parts = [
                f"{authors}. {title}[D]",
                f"{publisher}, {entry.year}" if entry.year else publisher,
            ]
            extra = self._build_extra_note(entry)
            return self._append_extra(self._join_sentence(parts), extra)

        if entry.entry_type == "inproceedings":
            booktitle = entry.booktitle or "未知会议"
            parts = [
                f"{authors}. {title}[C]//{booktitle}",
                entry.year,
            ]
            extra = self._build_extra_note(entry)
            return self._append_extra(self._join_sentence(parts), extra)

        # misc / fallback
        parts = [
            f"{authors}. {title}[EB/OL]",
            entry.year,
        ]
        extra = self._build_extra_note(entry)
        return self._append_extra(self._join_sentence(parts), extra)

    def format_entry(self, entry: CitationEntry) -> str:
        fields = self._collect_bibtex_fields(entry)

        lines = [f"@{entry.entry_type}{{{entry.citation_key},"]
        for field_name, field_value in fields:
            if not field_value:
                continue
            lines.append(f"  {field_name} = {{{field_value}}},")
        if len(lines) > 1:
            lines[-1] = lines[-1].rstrip(",")
        lines.append("}")
        return "\n".join(lines)

    def _collect_bibtex_fields(self, entry: CitationEntry) -> List[tuple[str, str]]:
        """收集 BibTeX 字段并完成转义。"""
        fields: List[tuple[str, str]] = []
        author_text = self._format_authors(entry.authors)
        if author_text:
            fields.append(("author", author_text))
        fields.append(("title", self._bibtex_escape(entry.title, wrap_braces=True)))

        optional_fields = [
            ("journal", entry.journal),
            ("booktitle", entry.booktitle),
            ("publisher", entry.publisher),
            ("year", entry.year),
            ("volume", entry.volume),
            ("number", entry.number),
            ("pages", entry.pages),
            ("doi", entry.doi),
            ("url", entry.url),
            ("note", entry.note),
            ("source", entry.source),
            ("source_type", entry.source_type),
            ("source_ref", entry.source_ref),
        ]
        for field_name, raw_value in optional_fields:
            if raw_value:
                fields.append((field_name, self._bibtex_escape(raw_value)))

        if self.include_abstract and entry.abstract:
            fields.append(("abstract", self._bibtex_escape(entry.abstract)))

        return fields

    def generate_bibtex(self, records: Iterable[Any]) -> str:
        return self.render_bibtex(self.build_entries(records))

    def build_library(
        self,
        entries: Iterable[CitationEntry],
        selected_format: str,
        duplicates_merged: int = 0,
    ) -> CitationLibrary:
        entry_list = list(entries)
        by_type: Dict[str, int] = {}
        by_year: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        for entry in entry_list:
            by_type[entry.entry_type] = by_type.get(entry.entry_type, 0) + 1
            if entry.year:
                by_year[entry.year] = by_year.get(entry.year, 0) + 1
            if entry.source:
                by_source[entry.source] = by_source.get(entry.source, 0) + 1

        stats = {
            "entry_count": len(entry_list),
            "by_type": by_type,
            "by_year": dict(sorted(by_year.items(), key=lambda item: item[0])),
            "by_source": dict(sorted(by_source.items(), key=lambda item: item[0])),
        }
        return CitationLibrary(
            entries=entry_list,
            format=selected_format,
            generated_at=datetime.now().isoformat(),
            duplicates_merged=duplicates_merged,
            stats=stats,
        )

    def _normalize_record(self, record: Dict[str, Any], index: int) -> CitationEntry:
        normalized = dict(record)
        title = self._read_first_text(normalized, ["title", "paper_title", "name"])
        if not title:
            title = f"Untitled Reference {index}"

        authors = self._parse_authors(
            normalized.get("authors") or normalized.get("author") or normalized.get("authors_venue") or ""
        )
        year = self._extract_year(normalized.get("year") or normalized.get("publish_date") or normalized.get("published") or "")

        text_fields = self._collect_record_text_fields(normalized)
        journal = text_fields["journal"]
        booktitle = text_fields["booktitle"]
        publisher = text_fields["publisher"]
        doi = text_fields["doi"]
        url = text_fields["url"]
        pages = text_fields["pages"]
        volume = text_fields["volume"]
        number = text_fields["number"]
        abstract = text_fields["abstract"]
        note = text_fields["note"]
        source = text_fields["source"]
        source_type = text_fields["source_type"]
        source_ref = text_fields["source_ref"]

        entry_type = str(normalized.get("entry_type") or self._infer_entry_type(normalized, journal, booktitle, publisher, url)).strip()
        citation_key = str(normalized.get("citation_key") or "").strip() or self._build_citation_key(authors, year, title, index)

        return CitationEntry(
            citation_key=citation_key,
            entry_type=entry_type,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            booktitle=booktitle,
            publisher=publisher,
            volume=volume,
            number=number,
            pages=pages,
            doi=doi,
            url=url,
            abstract=abstract,
            note=note,
            source=source,
            source_type=source_type,
            source_ref=source_ref,
        )

    def _resolve_record_inputs(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_inputs = (
            context.get("records")
            or context.get("references")
            or context.get("literature_records")
            or context.get("citations")
            or context.get("reference_records")
            or []
        )

        if not raw_inputs and isinstance(context.get("reference_library"), dict):
            library = context.get("reference_library") or {}
            raw_inputs = library.get("entries") or library.get("records") or []

        return self._ensure_record_list(raw_inputs)

    def _merge_duplicate_entries(self, entries: List[CitationEntry]) -> tuple[List[CitationEntry], int]:
        merged: Dict[str, CitationEntry] = {}
        duplicates_merged = 0
        for entry in entries:
            key = self._dedupe_key(entry)
            if key not in merged:
                merged[key] = entry
                continue
            duplicates_merged += 1
            merged[key] = self._merge_entry_fields(merged[key], entry)
        return list(merged.values()), duplicates_merged

    def _dedupe_key(self, entry: CitationEntry) -> str:
        author_key = "|".join(author.strip().lower() for author in entry.authors if author.strip())
        title_key = re.sub(r"\s+", " ", entry.title.strip().lower())
        return f"{title_key}|{entry.year}|{author_key}"

    def _merge_entry_fields(self, left: CitationEntry, right: CitationEntry) -> CitationEntry:
        merged = CitationEntry(**left.to_dict())
        for field_name in (
            "journal",
            "booktitle",
            "publisher",
            "volume",
            "number",
            "pages",
            "doi",
            "url",
            "abstract",
            "note",
            "source",
            "source_type",
            "source_ref",
        ):
            current_value = getattr(merged, field_name)
            if current_value:
                continue
            incoming = getattr(right, field_name)
            if incoming:
                setattr(merged, field_name, incoming)

        for author in right.authors:
            if author not in merged.authors:
                merged.authors.append(author)

        if not merged.year and right.year:
            merged.year = right.year
        if not merged.entry_type and right.entry_type:
            merged.entry_type = right.entry_type
        return merged

    def _collect_record_text_fields(self, record: Dict[str, Any]) -> Dict[str, str]:
        """统一提取 record 中的文本字段，减少归一化分支复杂度。"""
        note = self._read_first_text(record, ["note", "status"])
        source = self._read_first_text(record, ["source"])
        source_type = self._read_first_text(record, ["source_type"])
        source_ref = self._read_first_text(record, ["source_ref", "urn"])

        if note and (not source_type or not source_ref):
            note_mapping = self._parse_note_mapping(note)
            if not source_ref:
                source_ref = note_mapping.get("source_ref", "")
            if not source_type:
                source_type = note_mapping.get("source_type", "")

        if not source_type and source:
            source_type = self._infer_source_type_from_source(source)

        return {
            "journal": self._read_first_text(record, ["journal", "venue", "source"]),
            "booktitle": self._read_first_text(record, ["booktitle", "conference"]),
            "publisher": self._read_first_text(record, ["publisher"]),
            "doi": self._read_first_text(record, ["doi"]),
            "url": self._read_first_text(record, ["url", "link"]),
            "pages": self._read_first_text(record, ["pages", "page"]),
            "volume": self._read_first_text(record, ["volume"]),
            "number": self._read_first_text(record, ["number", "issue"]),
            "abstract": self._read_first_text(record, ["abstract", "snippet"]),
            "note": note,
            "source": source,
            "source_type": source_type,
            "source_ref": source_ref,
        }

    def _parse_note_mapping(self, note: str) -> Dict[str, str]:
        """从 `k=v; k2=v2` 形式的 note 中抽取键值对。"""
        mapping: Dict[str, str] = {}
        for segment in str(note or "").split(";"):
            part = segment.strip()
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip().lower()
            if not key:
                continue
            mapping[key] = value.strip()
        return mapping

    def _infer_source_type_from_source(self, source: str) -> str:
        normalized = str(source or "").strip().lower()
        if not normalized:
            return ""
        if normalized.endswith("_corpus"):
            return normalized.removesuffix("_corpus")
        if normalized in {"local", "ctext", "pdf", "web", "pipeline", "literature", "corpus"}:
            return normalized
        return ""

    def _read_first_text(self, record: Dict[str, Any], keys: List[str]) -> str:
        """按候选键顺序读取首个非空文本。"""
        for key in keys:
            value = record.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _infer_entry_type(
        self,
        record: Dict[str, Any],
        journal: str,
        booktitle: str,
        publisher: str,
        url: str,
    ) -> str:
        explicit_type = str(
            record.get("entry_type")
            or record.get("document_type")
            or record.get("publication_type")
            or record.get("type")
            or ""
        ).lower()
        source = str(record.get("source") or "").lower()
        if explicit_type in {"thesis", "dissertation", "phdthesis", "mastersthesis", "degree"}:
            return "thesis"
        if explicit_type in {"book", "monograph"}:
            return "book"
        if explicit_type in {"electronic", "online", "web", "webpage", "misc"}:
            return "misc"
        if publisher and not journal and not booktitle:
            return "book"
        if any(token in source for token in ("dissertation", "thesis", "degree")):
            return "thesis"
        if booktitle:
            return "inproceedings"
        if "arxiv" in source or "arxiv" in url.lower():
            return "misc"
        if journal or source:
            return "article"
        return self.default_entry_type

    def _build_citation_key(self, authors: List[str], year: str, title: str, index: int) -> str:
        first_author = authors[0] if authors else "ref"
        surname = self._slug_token(self._extract_primary_author(first_author)) or f"ref{index}"
        year_token = year or "nd"
        title_token = self._slug_token(self._extract_title_token(title)) or str(index)
        return f"{surname}{year_token}{title_token}"

    def _ensure_unique_key(self, base_key: str, used_keys: Dict[str, int]) -> str:
        current_count = used_keys.get(base_key, 0)
        used_keys[base_key] = current_count + 1
        if current_count == 0:
            return base_key
        return f"{base_key}{chr(ord('a') + current_count)}"

    def _format_authors(self, authors: List[str]) -> str:
        normalized = [self._normalize_author_name(author) for author in authors if str(author).strip()]
        return " and ".join(item for item in normalized if item)

    def _format_authors_gbt(self, authors: List[str]) -> str:
        if not authors:
            return "佚名"
        rendered: List[str] = []
        for author in authors[:3]:
            text = str(author).strip()
            if not text:
                continue
            if self._contains_cjk(text):
                rendered.append(text)
                continue
            parts = [part for part in re.split(r"\s+", text) if part]
            if len(parts) >= 2:
                rendered.append(f"{parts[-1]} {' '.join(parts[:-1])}")
            else:
                rendered.append(text)
        if not rendered:
            return "佚名"
        if len(authors) > 3:
            rendered.append("等")
        return ", ".join(rendered)

    def _normalize_author_name(self, author: str) -> str:
        text = str(author).strip()
        if not text:
            return ""
        if "," in text:
            return self._bibtex_escape(text)
        if self._contains_cjk(text):
            return self._bibtex_escape(text)
        parts = [part for part in re.split(r"\s+", text) if part]
        if len(parts) >= 2:
            return self._bibtex_escape(f"{parts[-1]}, {' '.join(parts[:-1])}")
        return self._bibtex_escape(text)

    def _parse_authors(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

        text = str(value or "").strip()
        if not text:
            return []
        author_segment = text.split(" - ", 1)[0].strip()
        separators = [" and ", ";", "，", ","]
        parts = [author_segment]
        for separator in separators:
            if separator in author_segment:
                parts = [item.strip() for item in author_segment.split(separator)]
                break
        return [part for part in parts if part]

    def _ensure_record_list(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in value:
            record = self._coerce_record_dict(item)
            if record:
                normalized.append(record)
        return normalized

    def _coerce_record_dict(self, record: Any) -> Dict[str, Any]:
        if isinstance(record, CitationEntry):
            return record.to_dict()
        if isinstance(record, dict):
            return dict(record)
        if is_dataclass(record):
            payload = asdict(record)
            return payload if isinstance(payload, dict) else {}
        if hasattr(record, "__dict__"):
            return {key: value for key, value in vars(record).items() if not key.startswith("_")}
        return {}

    def _sort_entries_for_bibliography(self, entries: List[CitationEntry]) -> List[CitationEntry]:
        return sorted(
            entries,
            key=lambda entry: (
                re.sub(r"\s+", " ", entry.title.strip().lower()),
                entry.year or "9999",
                self._extract_primary_author(entry.authors[0]) if entry.authors else "zzz",
            ),
        )

    def _maybe_export_outputs(
        self,
        context: Dict[str, Any],
        library: CitationLibrary,
        bibtex: str,
        gbt7714: str,
    ) -> Dict[str, str]:
        should_export = bool(context.get("export_outputs", self.export_outputs))
        output_dir = str(context.get("output_dir") or self.default_output_dir).strip()
        if not should_export or not output_dir:
            return {}

        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        file_stem = str(context.get("file_stem") or context.get("base_name") or "citations").strip() or "citations"

        json_path = os.path.join(output_dir, f"{file_stem}.json")
        bib_path = os.path.join(output_dir, f"{file_stem}.bib")
        gbt_path = os.path.join(output_dir, f"{file_stem}_gbt7714.txt")

        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(library.to_dict(), handle, ensure_ascii=False, indent=2)
        with open(bib_path, "w", encoding="utf-8") as handle:
            handle.write(bibtex)
        with open(gbt_path, "w", encoding="utf-8") as handle:
            handle.write(gbt7714)

        return {
            "library_json": json_path,
            "bibtex": bib_path,
            "gbt7714": gbt_path,
        }

    def _extract_year(self, value: Any) -> str:
        text = str(value or "")
        match = re.search(r"\b(19|20)\d{2}\b", text)
        return match.group(0) if match else ""

    def _normalize_output_format(self, value: str) -> str:
        text = str(value or "bibtex").strip().lower()
        if text in {"gbt", "gb", "gb/t", "gb/t 7714", "gb/t 7714-2015", "gbt7714"}:
            return "GB/T 7714-2015"
        return "bibtex"

    def _join_volume_issue(self, volume: str, number: str) -> str:
        v = str(volume or "").strip()
        n = str(number or "").strip()
        if v and n:
            return f"{v}({n})"
        return v or n

    def _normalize_pages(self, pages: str) -> str:
        return str(pages or "").strip().replace("--", "-")

    def _build_extra_note(self, entry: CitationEntry) -> str:
        extras = []
        if entry.doi:
            extras.append(f"DOI: {entry.doi}")
        if entry.url:
            extras.append(entry.url)
        structured_note = self._build_structured_provenance_note(entry)
        if structured_note:
            extras.append(structured_note)
        return " ".join(item for item in extras if item)

    def _build_structured_provenance_note(self, entry: CitationEntry) -> str:
        fields: List[str] = []
        if entry.source:
            fields.append(f"source={entry.source}")
        if entry.source_type:
            fields.append(f"source_type={entry.source_type}")
        if entry.source_ref:
            fields.append(f"source_ref={entry.source_ref}")
        if not fields:
            return ""
        return f"【结构化附注】{'; '.join(fields)}"

    def _join_with_sep(self, values: List[str], sep: str) -> str:
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return sep.join(cleaned)

    def _join_sentence(self, values: List[str]) -> str:
        cleaned = [str(item).strip().rstrip(".") for item in values if str(item).strip()]
        if not cleaned:
            return ""
        return ". ".join(cleaned) + "."

    def _append_extra(self, base: str, extra: str) -> str:
        if not extra:
            return base
        return f"{base} {extra}".strip()

    def _extract_primary_author(self, author: str) -> str:
        tokens = [token for token in re.split(r"\s+", author.strip()) if token]
        if not tokens:
            return "ref"
        if self._contains_cjk(author):
            return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", author) or "ref"
        return re.sub(r"[^A-Za-z0-9]", "", tokens[-1]) or "ref"

    def _extract_title_token(self, title: str) -> str:
        for token in re.split(r"[^\w\u4e00-\u9fff]+", title):
            if len(token) >= 2:
                return token
        return "ref"

    def _slug_token(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = "".join(ch for ch in normalized if ch.isascii())
        compact = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", ascii_only or value)
        return compact[:32]

    def _contains_cjk(self, value: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in value)

    def _bibtex_escape(self, value: str, wrap_braces: bool = False) -> str:
        escaped = (
            str(value)
            .replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("&", "\\&")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        if wrap_braces:
            return escaped
        return escaped

    def _do_cleanup(self) -> bool:
        self._inline_citation_registry.clear()
        self._inline_citation_next_index = 1
        self.logger.info("CitationManager 资源清理完成")
        return True