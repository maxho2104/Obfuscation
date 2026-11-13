"""Импорт структурированных текстовых данных (оценок) в БД.

Пакет не зависит от GUI и предметной модели приложения: снаружи передаются
конфигурация, Engine SQLAlchemy и путь к правилам сопоставления. Запись
оценок выполняет отдельный адаптер приложения.
"""

from internal_correspondence.text_import.config import ImporterConfig
from internal_correspondence.text_import.errors import ImporterError
from internal_correspondence.text_import.models import (
    DocumentMeta,
    FieldSpec,
    FileInfo,
    ImportResult,
    LayoutScheme,
    MatchPreview,
    MatchResult,
    ParsedRow,
    ProblemRow,
    SchemeMatch,
    ValidationReport,
)
from internal_correspondence.text_import.service import Importer

__all__ = [
    "DocumentMeta",
    "FieldSpec",
    "FileInfo",
    "ImportResult",
    "Importer",
    "ImporterConfig",
    "ImporterError",
    "LayoutScheme",
    "MatchPreview",
    "MatchResult",
    "ParsedRow",
    "ProblemRow",
    "SchemeMatch",
    "ValidationReport",
]
