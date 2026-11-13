"""Оркестратор импорта: чтение, разбор, сопоставление и запись."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from internal_correspondence.services.evaluation_import_writer import (
    EvaluationImportWriter,
    EvaluationWriteError,
)
from internal_correspondence.text_import import repository
from internal_correspondence.text_import.config import ImporterConfig
from internal_correspondence.text_import.errors import (
    ConfigError,
    DuplicateFileError,
    ImporterError,
    MatcherError,
    SchemeError,
    ValidationFailedError,
)
from internal_correspondence.text_import.matcher import Matcher, load_rules, validate_rule_for_scheme
from internal_correspondence.text_import.models import (
    DocumentMeta,
    FileInfo,
    ImportCounts,
    ImportResult,
    LayoutScheme,
    MatchPreview,
    MatchResult,
    MatchRule,
    MatchRuleSet,
    ParsedRow,
    SchemeMatch,
    ValidationReport,
)
from internal_correspondence.text_import.parsing import parse_rows
from internal_correspondence.text_import.reader import read_file
from internal_correspondence.text_import.scheme import detect_schemes, load_schemes
from internal_correspondence.text_import.storage import copy_to_storage

logger = logging.getLogger("internal_correspondence.text_import")


class Importer:
    """Один сеанс импорта одного файла.

    Последовательность: ``load_file`` → ``detect_schemes``/``set_scheme`` →
    ``set_document`` → ``validate`` → ``preview_matches`` → ``import_to_db``.
    """

    def __init__(
        self,
        config: ImporterConfig,
        engine,
        session: Optional[Session] = None,
    ) -> None:
        try:
            config.ensure_dirs()
        except OSError as exc:
            raise ConfigError("config_storage_unavailable", str(exc)) from exc
        self.config = config
        self.engine = engine
        repository.ensure_schema(engine)
        self.session = session or Session(engine)
        self.info: Optional[FileInfo] = None
        self.scheme: Optional[LayoutScheme] = None
        self.rule: Optional[MatchRule] = None
        self.meta: Optional[DocumentMeta] = None
        self.report: Optional[ValidationReport] = None
        self.preview: Optional[MatchPreview] = None
        self.schemes: List[LayoutScheme] = []
        self.rules: MatchRuleSet = MatchRuleSet()
        self._rejected: Set[int] = set()
        self._writer: Optional[EvaluationImportWriter] = None

    # -- загрузка и выбор схемы/правила ------------------------------------
    def load_file(self, path: str | Path, encoding: Optional[str] = None) -> FileInfo:
        self.info = read_file(
            Path(path),
            self.config.allowed_extensions,
            encoding=encoding,
            max_line_length=self.config.max_line_length,
        )
        self.report = None
        self.preview = None
        self._rejected.clear()
        self.schemes = load_schemes(self.config.schemes_dir)
        return self.info

    def detect_schemes(self) -> List[SchemeMatch]:
        if self.info is None:
            raise ImporterError("file_not_loaded", "file is not loaded")
        return detect_schemes(self.info.lines, self.schemes)

    def set_scheme(self, scheme: LayoutScheme) -> None:
        errors = scheme.validate()
        if errors:
            raise SchemeError("scheme_invalid", "; ".join(errors), errors=errors)
        self.scheme = scheme
        self.report = None
        self.preview = None

    def set_document(self, doc_no: str, doc_date: date) -> None:
        self.meta = DocumentMeta(doc_no=doc_no, doc_date=doc_date)

    def load_rules(self) -> MatchRuleSet:
        self.rules = load_rules(self.config.matcher_rules_path)
        return self.rules

    def set_rule(self, rule: MatchRule) -> None:
        if self.scheme is None:
            raise MatcherError("scheme_not_selected", "scheme is not selected")
        validate_rule_for_scheme(rule, self.scheme)
        self.rule = rule
        self.preview = None

    def set_rule_by_name(self, name: str) -> None:
        rule = self.rules.by_name(name)
        if rule is None:
            raise MatcherError("rule_not_found", f"rule not found: {name}")
        self.set_rule(rule)

    # -- проверка и правка строк -------------------------------------------
    def validate(self) -> ValidationReport:
        self._require(self.info, "file_not_loaded")
        self._require(self.scheme, "scheme_not_selected")
        self.report = parse_rows(self.info.lines, self.scheme)
        self.preview = None
        return self.report

    def correct_row(self, row_no: int, raw_line: str) -> ValidationReport:
        self._require(self.info, "file_not_loaded")
        if not 1 <= row_no <= len(self.info.lines):
            raise ImporterError("row_not_found", f"row not found: {row_no}")
        lines = list(self.info.lines)
        lines[row_no - 1] = raw_line.rstrip("\r\n")
        self.info = FileInfo(
            path=self.info.path,
            encoding=self.info.encoding,
            text="\n".join(lines),
            lines=lines,
            file_hash=self.info.file_hash,
            size=self.info.size,
        )
        self._rejected.discard(row_no)
        return self.validate()

    def reject_row(self, row_no: int) -> None:
        self._rejected.add(row_no)
        self.preview = None

    def unreject_row(self, row_no: int) -> None:
        self._rejected.discard(row_no)
        self.preview = None

    def rejected_rows(self) -> Set[int]:
        return set(self._rejected)

    # -- предпросмотр и импорт ---------------------------------------------
    def preview_matches(self) -> MatchPreview:
        self._require(self.report, "validation_required")
        self._require(self.rule, "rule_not_selected")
        self._require(self.meta, "document_not_set")
        rows = [
            row
            for row in self.report.rows
            if row.is_valid and row.row_no not in self._rejected
        ]
        matcher = Matcher(self.session)
        results = matcher.match(rows, self.rule, self.scheme)
        self._writer = EvaluationImportWriter(self.session, self.meta.doc_no, self.meta.doc_date)
        for result in results:
            if result.matched and result.value_code:
                try:
                    result.duplicate = (
                        self._writer.find_existing(result.entity_type or "", result.entity_id or "")
                        is not None
                    )
                except (ValueError, EvaluationWriteError):
                    result.duplicate = False
        self.preview = MatchPreview(results=results, total=len(results))
        return self.preview

    def check_duplicate_file(self) -> Optional[Any]:
        self._require(self.info, "file_not_loaded")
        return repository.find_duplicate(self.session, self.info.file_hash)

    def import_to_db(
        self,
        dry_run: bool = False,
        duplicate_actions: Optional[Dict[int, str]] = None,
        force_duplicate: bool = False,
    ) -> ImportResult:
        self._require(self.info, "file_not_loaded")
        self._require(self.scheme, "scheme_not_selected")
        self._require(self.rule, "rule_not_selected")
        self._require(self.meta, "document_not_set")
        if self.report is None:
            self.validate()
        preview = self.preview_matches()
        actions = dict(duplicate_actions or {})
        duplicate = self.check_duplicate_file()
        if duplicate is not None and not force_duplicate:
            raise DuplicateFileError(
                "file already imported",
                import_id=duplicate.import_id,
                file_name=duplicate.file_name,
                started_at=duplicate.started_at,
            )
        if self.config.require_all_matched and preview.unmatched_count:
            raise ValidationFailedError(
                "not all rows are matched",
                unmatched=preview.unmatched_count,
            )

        counts = self._counts(preview, actions)
        warnings = list(self._writer.warnings) if self._writer else []
        if dry_run:
            return ImportResult(
                log_id=0,
                year=self.meta.doc_date.year,
                counts=counts,
                dry_run=True,
                duplicate_file=duplicate is not None,
                warnings=warnings,
            )

        log_id = repository.create_log(
            self.session,
            {
                "year": self.meta.doc_date.year,
                "doc_no": self.meta.doc_no,
                "doc_date": self.meta.doc_date,
                "file_name": self.info.path.name,
                "file_hash": self.info.file_hash,
                "scheme_name": self.scheme.name,
                "matched_rule": self.rule.name,
                "started_at": datetime.now(),
                "status": "running",
            },
        )
        stored_path: Optional[Path] = None
        try:
            with self.session.begin():
                self._insert_staging_rows(log_id, preview, actions)
                self._write_evaluations(preview, actions)
                repository.update_log(
                    self.session,
                    log_id,
                    commit=False,
                    imported_rows=counts.imported,
                    matched_rows=counts.matched,
                    unmatched_rows=counts.unmatched,
                    skipped_rows=counts.skipped,
                    rejected_rows=counts.rejected,
                    error_rows=counts.error,
                    finished_at=datetime.now(),
                    status="committed",
                )
        except Exception as exc:
            self.session.rollback()
            repository.update_log(
                self.session,
                log_id,
                imported_rows=counts.imported,
                matched_rows=counts.matched,
                unmatched_rows=counts.unmatched,
                skipped_rows=counts.skipped,
                rejected_rows=counts.rejected,
                error_rows=1,
                finished_at=datetime.now(),
                status="rolled_back",
            )
            logger.exception("import failed", exc_info=exc)
            raise
        try:
            copied = copy_to_storage(self.info.path, self.config)
            stored_path = copied.path
            repository.update_log(self.session, log_id, stored_path=str(stored_path))
        except Exception as exc:  # файл уже в БД — не откатываем импорт
            warnings.append(f"file copy failed: {exc}")
            logger.warning("import file copy failed: %s", exc)
        return ImportResult(
            log_id=log_id,
            year=self.meta.doc_date.year,
            counts=counts,
            stored_path=stored_path,
            duplicate_file=duplicate is not None,
            warnings=warnings,
        )

    # -- внутреннее ---------------------------------------------------------
    def _counts(self, preview: MatchPreview, actions: Dict[int, str]) -> ImportCounts:
        counts = ImportCounts()
        counts.rejected = len(self.report.problems) + len(
            [row for row in self.report.valid_rows if row.row_no in self._rejected]
        )
        for result in preview.results:
            if result.matched:
                counts.matched += 1
                if result.duplicate and actions.get(result.row.row_no, "skip") == "skip":
                    counts.skipped += 1
            else:
                counts.unmatched += 1
        counts.imported = counts.matched + counts.unmatched
        return counts

    def _insert_staging_rows(
        self,
        log_id: int,
        preview: MatchPreview,
        actions: Dict[int, str],
    ) -> None:
        by_row = {result.row.row_no: result for result in preview.results}
        payload: List[Dict[str, Any]] = []
        for row in self.report.rows:
            result = by_row.get(row.row_no)
            if row.problem is not None or row.row_no in self._rejected:
                status = "rejected"
                error = row.problem.message if row.problem else "rejected by operator"
            elif result is not None and result.matched:
                status = "matched"
                error = ""
            else:
                status = "unmatched"
                error = result.reason if result is not None else "not matched"
            data = _json_data(row.data)
            payload.append(
                {
                    "year": self.meta.doc_date.year,
                    "import_id": log_id,
                    "source_row_no": row.row_no,
                    "raw_line": row.raw,
                    "data": data,
                    "status": status,
                    "error": error or None,
                    "branch_code": result.branch_code if result else None,
                    "outgoing_no": result.outgoing_no if result else None,
                    "year_month": result.year_month if result else None,
                    "value_code": result.value_code if result else None,
                    "evaluation_date": result.evaluation_date if result else None,
                    "matched_entity_type": result.entity_type if result and result.matched else None,
                    "matched_entity_id": result.entity_id if result and result.matched else None,
                    "created_at": datetime.now(),
                }
            )
        repository.insert_rows(self.session, payload[: self.config.batch_size])
        for start in range(self.config.batch_size, len(payload), self.config.batch_size):
            repository.insert_rows(self.session, payload[start : start + self.config.batch_size])

    def _write_evaluations(self, preview: MatchPreview, actions: Dict[int, str]) -> None:
        if self._writer is None:
            self._writer = EvaluationImportWriter(self.session, self.meta.doc_no, self.meta.doc_date)
        for result in preview.results:
            if not result.matched or not result.value_code:
                continue
            action = actions.get(result.row.row_no, "skip")
            self._writer.write(result, action=action)

    def _require(self, value: Any, code: str) -> None:
        if value is None:
            raise ImporterError(code, code)

    def close(self) -> None:
        self.session.close()


def _json_data(data: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, date):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result
