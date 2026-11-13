"""Ошибки импортёра.

Сообщения намеренно не содержат русских строк: GUI переводит ``code``
в текст через AppStrings, а журнал получает техническое описание.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ImporterError(Exception):
    """Базовая ошибка импортёра с машинным кодом."""

    default_code = "import_error"

    def __init__(
        self,
        code: Optional[str] = None,
        message: str = "",
        **params: Any,
    ) -> None:
        self.code = code or self.default_code
        self.message = message or self.code
        self.params: Dict[str, Any] = dict(params)
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ConfigError(ImporterError):
    default_code = "config_error"


class ReaderError(ImporterError):
    default_code = "reader_error"


class SchemeError(ImporterError):
    default_code = "scheme_error"


class ParsingError(ImporterError):
    default_code = "parsing_error"


class MatcherError(ImporterError):
    default_code = "matcher_error"


class StorageError(ImporterError):
    default_code = "storage_error"


class RepositoryError(ImporterError):
    default_code = "repository_error"


class DuplicateFileError(ImporterError):
    default_code = "duplicate_file"

    def __init__(self, message: str = "", **params: Any) -> None:
        super().__init__(self.default_code, message, **params)


class ValidationFailedError(ImporterError):
    default_code = "validation_failed"

    def __init__(self, message: str = "", **params: Any) -> None:
        super().__init__(self.default_code, message, **params)
