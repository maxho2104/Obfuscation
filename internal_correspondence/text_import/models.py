"""Модели данных импортёра (не ORM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class DocumentMeta:
    """Метаданные импортируемого документа."""

    doc_no: str
    doc_date: date

    def __post_init__(self) -> None:
        if not self.doc_no.strip():
            raise ValueError("doc_no must not be empty")


@dataclass
class FieldSpec:
    """Описание поля схемы разметки."""

    name: str
    type: str = "string"
    start: Optional[int] = None
    length: Optional[int] = None
    required: bool = False
    date_format: Optional[str] = None
    regex: Optional[str] = None
    normalize_regex: Optional[str] = None
    default: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
        }
        if self.start is not None:
            result["start"] = self.start
        if self.length is not None:
            result["length"] = self.length
        if self.date_format:
            result["date_format"] = self.date_format
        if self.regex:
            result["regex"] = self.regex
        if self.normalize_regex:
            result["normalize_regex"] = self.normalize_regex
        if self.default is not None:
            result["default"] = self.default
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldSpec":
        return cls(
            name=str(data.get("name", "")),
            type=str(data.get("type", "string")),
            start=data.get("start"),
            length=data.get("length"),
            required=bool(data.get("required", False)),
            date_format=data.get("date_format"),
            regex=data.get("regex"),
            normalize_regex=data.get("normalize_regex"),
            default=data.get("default"),
        )


@dataclass
class LayoutScheme:
    """Схема разметки строк фиксированной ширины или разделителем."""

    name: str
    mode: str = "fixed"
    delimiter: str = ";"
    header_mode: str = "skip"
    fields: List[FieldSpec] = field(default_factory=list)
    description: str = ""
    record_length: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "version": 1,
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "delimiter": self.delimiter,
            "header_mode": self.header_mode,
            "fields": [item.to_dict() for item in self.fields],
        }
        if self.record_length is not None:
            result["line_length"] = self.record_length
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoutScheme":
        fields = [FieldSpec.from_dict(item) for item in data.get("fields", [])]
        return cls(
            name=str(data.get("name", "")),
            mode=str(data.get("mode", "fixed")),
            delimiter=str(data.get("delimiter", ";")),
            header_mode=str(data.get("header_mode", "skip")),
            fields=fields,
            description=str(data.get("description", "")),
            record_length=data.get("line_length"),
        )

    def validate(self) -> List[str]:
        """Возвращает список технических кодов ошибок схемы."""
        errors: List[str] = []
        if not self.name.strip():
            errors.append("scheme_name_empty")
        if self.mode not in ("fixed", "delimited"):
            errors.append("scheme_mode_invalid")
        if self.mode == "delimited" and not self.delimiter:
            errors.append("scheme_delimiter_empty")
        if self.header_mode not in ("none", "skip", "names"):
            errors.append("scheme_header_mode_invalid")
        if not self.fields:
            errors.append("scheme_fields_empty")
        names = [item.name.strip() for item in self.fields]
        if any(not name for name in names):
            errors.append("field_name_empty")
        if len(set(names)) != len(names):
            errors.append("field_name_duplicate")
        for item in self.fields:
            if item.type not in ("string", "integer", "number", "date"):
                errors.append(f"field_type_invalid:{item.name}")
            if item.type == "date":
                if item.date_format not in (None, "DD.MM.YYYY", "YYYYMM"):
                    errors.append(f"field_date_format_invalid:{item.name}")
            if item.regex:
                try:
                    import re

                    re.compile(item.regex)
                except re.error:
                    errors.append(f"field_regex_invalid:{item.name}")
            if item.normalize_regex:
                try:
                    import re

                    re.compile(item.normalize_regex)
                except re.error:
                    errors.append(f"field_normalize_regex_invalid:{item.name}")
        if self.mode == "fixed":
            errors.extend(self._validate_fixed())
        return errors

    def _validate_fixed(self) -> List[str]:
        errors: List[str] = []
        intervals: List[tuple[int, int, str]] = []
        for index, item in enumerate(self.fields):
            if item.start is None or item.start < 1:
                errors.append(f"field_start_invalid:{item.name}")
                continue
            if item.length is None:
                if index != len(self.fields) - 1:
                    errors.append(f"field_variable_not_last:{item.name}")
                continue
            if item.length < 1:
                errors.append(f"field_length_invalid:{item.name}")
                continue
            intervals.append((item.start, item.start + item.length - 1, item.name))
        intervals.sort()
        for left, right in zip(intervals, intervals[1:]):
            if right[0] <= left[1]:
                errors.append(f"field_overlap:{left[2]}:{right[2]}")
        if self.record_length is not None:
            if self.record_length < 1:
                errors.append("scheme_line_length_invalid")
            elif intervals and intervals[-1][1] > self.record_length:
                errors.append("scheme_line_length_too_small")
        return errors

    @property
    def line_length(self) -> Optional[int]:
        """Длина записи для fixed-схемы (None, если последнее поле до конца)."""
        if self.mode != "fixed":
            return None
        lengths = [
            item.start - 1 + item.length
            for item in self.fields
            if item.start is not None and item.length is not None
        ]
        computed = max(lengths) if lengths else None
        if self.record_length is not None:
            return self.record_length
        return computed

    @property
    def is_valid(self) -> bool:
        return not self.validate()


@dataclass
class SchemeMatch:
    scheme: LayoutScheme
    matched: bool
    reason: str = ""


@dataclass
class ProblemRow:
    row_no: int
    raw: str
    code: str
    message: str = ""


@dataclass
class ParsedRow:
    row_no: int
    raw: str
    data: Dict[str, Any] = field(default_factory=dict)
    problem: Optional[ProblemRow] = None

    @property
    def is_valid(self) -> bool:
        return self.problem is None


@dataclass
class ValidationReport:
    rows: List[ParsedRow] = field(default_factory=list)
    total_lines: int = 0

    @property
    def problems(self) -> List[ProblemRow]:
        return [row.problem for row in self.rows if row.problem is not None]

    @property
    def valid_rows(self) -> List[ParsedRow]:
        return [row for row in self.rows if row.is_valid]

    @property
    def valid_count(self) -> int:
        return len(self.valid_rows)

    @property
    def problem_count(self) -> int:
        return len(self.problems)

    def problem_at(self, row_no: int) -> Optional[ProblemRow]:
        for problem in self.problems:
            if problem.row_no == row_no:
                return problem
        return None


@dataclass
class MatchRule:
    name: str
    entity: str
    composite_keys: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    match: List[str] = field(default_factory=list)
    target: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchRuleSet:
    rules: List[MatchRule] = field(default_factory=list)

    def by_name(self, name: str) -> Optional[MatchRule]:
        for rule in self.rules:
            if rule.name == name:
                return rule
        return None

    @property
    def names(self) -> List[str]:
        return [rule.name for rule in self.rules]


@dataclass
class MatchResult:
    row: ParsedRow
    matched: bool
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    reason: str = ""
    branch_code: str = ""
    outgoing_no: str = ""
    year_month: str = ""
    value_code: Optional[str] = None
    evaluation_date: Optional[date] = None
    effect: Optional[float] = None
    duplicate: bool = False


@dataclass
class MatchPreview:
    results: List[MatchResult] = field(default_factory=list)
    total: int = 0

    @property
    def matched_count(self) -> int:
        return sum(1 for item in self.results if item.matched)

    @property
    def unmatched_count(self) -> int:
        return sum(1 for item in self.results if not item.matched)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for item in self.results if item.duplicate)


@dataclass
class FileInfo:
    path: Path
    encoding: str
    text: str
    lines: List[str]
    file_hash: str
    size: int

    @property
    def line_count(self) -> int:
        return len(self.lines)


@dataclass
class DuplicateInfo:
    import_id: int
    year: int
    file_name: str
    stored_path: Optional[str]
    started_at: Any
    status: str


@dataclass
class ImportCounts:
    imported: int = 0
    matched: int = 0
    unmatched: int = 0
    skipped: int = 0
    rejected: int = 0
    error: int = 0
    evaluations_received: int = 0
    by_value: Dict[str, int] = field(default_factory=dict)
    documents_reupdated: int = 0
    materials_reupdated: int = 0
    telegrams_reupdated: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "imported": self.imported,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "skipped": self.skipped,
            "rejected": self.rejected,
            "error": self.error,
            "evaluations_received": self.evaluations_received,
            "by_value": dict(self.by_value),
            "documents_reupdated": self.documents_reupdated,
            "materials_reupdated": self.materials_reupdated,
            "telegrams_reupdated": self.telegrams_reupdated,
        }


@dataclass
class ImportResult:
    log_id: int
    year: int
    counts: ImportCounts
    stored_path: Optional[Path] = None
    dry_run: bool = False
    duplicate_file: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class StorageCopyResult:
    path: Path
    renamed: bool = False
