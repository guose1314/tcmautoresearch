"""Encoding governance for local corpus text files."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:  # pragma: no cover - exercised by integration environments with chardet
    import chardet  # type: ignore
except Exception:  # pragma: no cover
    chardet = None  # type: ignore


ENCODING_CONTRACT_VERSION = "corpus-encoding-v1"
DOCUMENT_KEY_VERSION = "canonical-document-v1"

_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

_KNOWN_DYNASTIES = {
    "先秦",
    "秦",
    "汉",
    "东汉",
    "西汉",
    "晋",
    "南朝",
    "北朝",
    "隋",
    "唐",
    "五代",
    "宋",
    "金",
    "元",
    "明",
    "清",
    "民国",
}

_MOJIBAKE_MARKERS = (
    "�",
    "锟斤拷",
    "Ã",
    "Â",
    "Ð",
    "Ñ",
    "æ",
    "ç",
    "è",
    "é",
    "瀹",
    "紶",
    "獙",
)


@dataclass(frozen=True)
class CorpusEncodingReport:
    """Encoding report for one corpus file."""

    contract_version: str
    path: str
    original_filename: str
    suggested_filename: Optional[str]
    filename_repair_strategy: Optional[str]
    filename_suspect: bool
    source_size_bytes: int
    detected_encoding: str
    decoder_encoding: str
    confidence: float
    anomalous_character_ratio: float
    newline_style: str
    normalized_newlines: bool
    text_sha256: str
    source_file_hash: str
    empty: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalDocumentIdentity:
    """Stable document identity derived before persistence."""

    document_key_version: str
    canonical_document_key: str
    canonical_title: str
    normalized_title: str
    source_file_hash: str
    text_sha256: str
    dynasty: Optional[str]
    author: Optional[str]
    edition_hint: Optional[str]
    source_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StandardizedCorpusText:
    """Decoded UTF-8 text plus governance metadata."""

    text: str
    encoding_report: CorpusEncodingReport
    canonical_identity: CanonicalDocumentIdentity


class CorpusEncodingService:
    """Decode corpus files without mutating the source files."""

    def __init__(self, *, sample_size: int = 131_072) -> None:
        self.sample_size = int(sample_size)

    def iter_txt_files(self, data_dir: Path | str) -> Iterable[Path]:
        root = Path(data_dir)
        return sorted(root.glob("*.txt"), key=lambda path: path.name)

    def standardize_file(self, path: Path | str) -> StandardizedCorpusText:
        file_path = Path(path)
        raw = file_path.read_bytes()
        decoded_text, detected_encoding, decoder_encoding, confidence = (
            self.decode_bytes(raw)
        )
        normalized_text, newline_style, normalized_newlines = self._normalize_text(
            decoded_text
        )
        suggested_filename, repair_strategy = self.suggest_filename_repair(
            file_path.name
        )
        filename_suspect = suggested_filename is not None or self._looks_like_mojibake(
            file_path.name
        )
        source_hash = hashlib.sha256(raw).hexdigest()
        text_hash = hashlib.sha256(
            normalized_text.encode("utf-8", errors="replace")
        ).hexdigest()
        report = CorpusEncodingReport(
            contract_version=ENCODING_CONTRACT_VERSION,
            path=str(file_path),
            original_filename=file_path.name,
            suggested_filename=suggested_filename,
            filename_repair_strategy=repair_strategy,
            filename_suspect=filename_suspect,
            source_size_bytes=len(raw),
            detected_encoding=detected_encoding,
            decoder_encoding=decoder_encoding,
            confidence=round(float(confidence), 4),
            anomalous_character_ratio=self._anomalous_character_ratio(normalized_text),
            newline_style=newline_style,
            normalized_newlines=normalized_newlines,
            text_sha256=text_hash,
            source_file_hash=source_hash,
            empty=len(raw) == 0 or len(normalized_text) == 0,
        )
        source_file = suggested_filename or file_path.name
        identity = self.build_canonical_identity(
            source_file=source_file,
            source_file_hash=source_hash,
            text_sha256=text_hash,
        )
        return StandardizedCorpusText(
            text=normalized_text,
            encoding_report=report,
            canonical_identity=identity,
        )

    def decode_bytes(self, raw: bytes) -> tuple[str, str, str, float]:
        if not raw:
            return "", "empty", "utf-8", 1.0

        for bom, encoding in _BOMS:
            if raw.startswith(bom):
                text = raw.decode(encoding, errors="replace")
                return text, encoding, encoding, 1.0

        try:
            return raw.decode("utf-8"), "utf-8", "utf-8", 1.0
        except UnicodeDecodeError:
            pass

        detected_encoding = "unknown"
        detected_confidence = 0.0
        if chardet is not None:
            detected = chardet.detect(raw[: self.sample_size]) or {}
            detected_encoding = str(detected.get("encoding") or "unknown")
            detected_confidence = float(detected.get("confidence") or 0.0)

        preferred = self._normalize_encoding_label(detected_encoding)
        candidates = self._candidate_encodings(preferred)
        scored: list[tuple[float, str, str]] = []
        for encoding in candidates:
            try:
                text = raw.decode(encoding, errors="replace")
            except LookupError:
                continue
            score = self._decode_quality_score(text)
            if encoding == preferred and detected_confidence > 0:
                score -= min(0.15, detected_confidence / 10.0)
            scored.append((score, encoding, text))

        if not scored:
            text = raw.decode("gb18030", errors="replace")
            return text, detected_encoding, "gb18030", 0.2

        scored.sort(key=lambda item: item[0])
        best_score, best_encoding, best_text = scored[0]
        confidence = self._confidence_from_score(best_score, detected_confidence)
        return best_text, detected_encoding, best_encoding, confidence

    def build_canonical_identity(
        self,
        *,
        source_file: str,
        source_file_hash: str,
        text_sha256: str,
    ) -> CanonicalDocumentIdentity:
        canonical_title, dynasty, author, edition_hint = self._parse_title_metadata(
            source_file
        )
        normalized_title = self.normalize_title(canonical_title)
        key_material = f"{DOCUMENT_KEY_VERSION}\0{text_sha256}"
        canonical_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        return CanonicalDocumentIdentity(
            document_key_version=DOCUMENT_KEY_VERSION,
            canonical_document_key=canonical_key,
            canonical_title=canonical_title,
            normalized_title=normalized_title,
            source_file_hash=source_file_hash,
            text_sha256=text_sha256,
            dynasty=dynasty,
            author=author,
            edition_hint=edition_hint,
            source_file=source_file,
        )

    def normalize_title(self, value: str) -> str:
        title = unicodedata.normalize("NFKC", str(value or ""))
        title = re.sub(r"^[0-9０-９]+[-_\s]+", "", title)
        title = title.replace("《", "").replace("》", "")
        title = re.sub(r"[\s·．.]+", "", title)
        title = re.sub(r"[-_]+", "-", title).strip("-")
        return title.lower()

    def suggest_filename_repair(
        self, filename: str
    ) -> tuple[Optional[str], Optional[str]]:
        original = str(filename or "")
        if not original:
            return None, None
        candidates: list[tuple[float, str, str]] = []
        transforms = (
            ("gb18030->utf-8", "gb18030", "utf-8"),
            ("gbk->utf-8", "gbk", "utf-8"),
            ("latin1->utf-8", "latin1", "utf-8"),
            ("cp1252->utf-8", "cp1252", "utf-8"),
        )
        original_score = self._filename_quality_score(original)
        for strategy, source_encoding, target_encoding in transforms:
            try:
                repaired = original.encode(source_encoding).decode(target_encoding)
            except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
                continue
            if repaired == original:
                continue
            candidates.append(
                (self._filename_quality_score(repaired), strategy, repaired)
            )
        if not candidates:
            return None, None
        candidates.sort(key=lambda item: item[0])
        best_score, strategy, repaired = candidates[0]
        if best_score + 0.05 < original_score:
            return repaired, strategy
        return None, None

    def _normalize_text(self, text: str) -> tuple[str, str, bool]:
        if not text:
            return "", "none", False
        text = text.replace("\ufeff", "")
        if "\r\n" in text:
            newline_style = "crlf"
        elif "\r" in text:
            newline_style = "cr"
        elif "\n" in text:
            newline_style = "lf"
        else:
            newline_style = "none"
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\x00", "")
        return normalized, newline_style, normalized != text

    def _normalize_encoding_label(self, value: str) -> str:
        label = str(value or "").strip().lower().replace("_", "-")
        if label in {"gb2312", "gbk", "gb-2312", "windows-936", "cp936"}:
            return "gb18030"
        if label in {"big5", "big5-hkscs", "cp950"}:
            return "big5"
        if label in {"utf-8", "utf8", "ascii", "us-ascii"}:
            return "utf-8"
        if label.startswith("utf-16"):
            return label
        return label or "gb18030"

    def _candidate_encodings(self, preferred: str) -> list[str]:
        candidates = [preferred, "gb18030", "gbk", "big5", "utf-8", "utf-16"]
        unique: list[str] = []
        for encoding in candidates:
            if encoding and encoding not in unique:
                unique.append(encoding)
        return unique

    def _decode_quality_score(self, text: str) -> float:
        ratio = self._anomalous_character_ratio(text)
        cjk_ratio = self._cjk_ratio(text)
        mojibake_penalty = 0.15 if self._looks_like_mojibake(text[:4000]) else 0.0
        return ratio + mojibake_penalty - min(0.1, cjk_ratio / 10.0)

    def _confidence_from_score(self, score: float, detected_confidence: float) -> float:
        heuristic = max(0.2, min(0.98, 1.0 - max(0.0, score) * 3.0))
        if detected_confidence > 0:
            return max(0.2, min(0.99, (heuristic + detected_confidence) / 2.0))
        return heuristic

    def _anomalous_character_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        bad = 0
        for char in text:
            codepoint = ord(char)
            if char == "\ufffd" or char == "\x00":
                bad += 1
            elif codepoint < 32 and char not in {"\n", "\t"}:
                bad += 1
            elif 0xE000 <= codepoint <= 0xF8FF:
                bad += 1
        return round(bad / max(1, len(text)), 6)

    def _cjk_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        return cjk / max(1, len(text))

    def _looks_like_mojibake(self, value: str) -> bool:
        if any(marker in value for marker in _MOJIBAKE_MARKERS):
            return True
        private_use = sum(1 for char in value if 0xE000 <= ord(char) <= 0xF8FF)
        return private_use >= 1

    def _filename_quality_score(self, filename: str) -> float:
        text = str(filename or "")
        if not text:
            return 1.0
        score = self._anomalous_character_ratio(text)
        if self._looks_like_mojibake(text):
            score += 0.4
        cjk_ratio = self._cjk_ratio(text)
        score -= min(0.2, cjk_ratio / 4.0)
        if Path(text).suffix.lower() == ".txt":
            score -= 0.03
        return score

    def _parse_title_metadata(
        self, source_file: str
    ) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
        stem = Path(source_file).stem.strip()
        stem = re.sub(r"^[0-9０-９]+[-_\s]+", "", stem)
        parts = [part.strip() for part in re.split(r"-+", stem) if part.strip()]
        if not parts:
            return stem or source_file, None, None, None

        title = parts[0]
        dynasty: Optional[str] = None
        author: Optional[str] = None
        edition_hint: Optional[str] = None

        remaining = parts[1:]
        if remaining and remaining[0] in _KNOWN_DYNASTIES:
            dynasty = remaining.pop(0)
        if remaining:
            author = remaining.pop(0)
        if remaining:
            edition_hint = "-".join(remaining)
        return title, dynasty, author, edition_hint
