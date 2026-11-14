"""Конфигурация импортёра текстовых данных."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple


@dataclass
class ImporterConfig:
    """Параметры, не зависящие от конкретной предметной области."""

    file_storage_dir: Path
    schemes_dir: Path
    matcher_rules_path: Path
    storage_subdir: str = "Импорт"
    allowed_extensions: Tuple[str, ...] = (".txt", ".csv", ".dat")
    preview_lines: int = 50
    batch_size: int = 1000
    require_all_matched: bool = False
    log_year_source: str = "doc_date"
    max_line_length: int = 1_000_000
    encoding_fallbacks: Tuple[str, ...] = ("utf-8", "cp1251")

    def __post_init__(self) -> None:
        self.file_storage_dir = Path(self.file_storage_dir)
        self.schemes_dir = Path(self.schemes_dir)
        self.matcher_rules_path = Path(self.matcher_rules_path)
        self.allowed_extensions = tuple(ext.lower() for ext in self.allowed_extensions)
        if not self.storage_subdir:
            raise ValueError("storage_subdir must not be empty")
        if self.preview_lines < 1:
            raise ValueError("preview_lines must be positive")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")

    @property
    def import_dir(self) -> Path:
        """Каталог, в который копируются исходные файлы после commit."""
        return self.file_storage_dir / self.storage_subdir

    def ensure_dirs(self) -> None:
        """Создаёт каталоги схем и импорта, проверяет хранилище."""
        if not self.file_storage_dir.exists():
            raise FileNotFoundError(f"storage directory not found: {self.file_storage_dir}")
        self.schemes_dir.mkdir(parents=True, exist_ok=True)
        self.import_dir.mkdir(parents=True, exist_ok=True)
