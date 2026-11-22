"""Общие помощники скриптов наполнения базы (фаза филиала / фаза ГО).

Содержит разбор параметров диапазонов, годовые счётчики документов,
поиск каталога базы/хранилища и прикрепление файлов-вложений.
"""

import argparse
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from internal_correspondence.core.constants import (  # noqa: E402
    FILES_DIR,
    MATERIAL_FILES_DIR,
    TELEGRAM_FILES_DIR,
)
from internal_correspondence.core.settings import AppSettings, SettingsManager  # noqa: E402
from internal_correspondence.orm.base import Base  # noqa: E402
from internal_correspondence.orm.models import FileRecord  # noqa: E402

# Период генерации по умолчанию: последние 30 дней включительно
DEFAULT_PERIOD_DAYS = 30


def parse_range(value: str) -> Tuple[int, int]:
    """Разбирает диапазон вида «N-M» в пару (min, max)."""
    parts = value.split("-", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Ожидался диапазон вида «N-M»: {value!r}")
    try:
        low, high = int(parts[0]), int(parts[1])
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Границы диапазона должны быть целыми: {value!r}"
        ) from error
    if low < 0 or high < low:
        raise argparse.ArgumentTypeError(
            f"Некорректный диапазон (нужно 0 <= N <= M): {value!r}"
        )
    return low, high


def default_period(today: date) -> Tuple[date, date]:
    """Возвращает период генерации по умолчанию: последние 30 дней."""
    return today - timedelta(days=DEFAULT_PERIOD_DAYS - 1), today


def parse_date(value: str) -> date:
    """Разбирает дату формата ГГГГ-ММ-ДД."""
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Дата должна быть в формате ГГГГ-ММ-ДД: {value!r}"
        ) from error


class YearlyCounter:
    """Годовой счётчик документов: цифры по порядку в течение года.

    Счётчик сбрасывается 1 января (каждый год ведёт свою последовательность).
    Номер уникален в пределах своей последовательности и монотонно
    возрастает в порядке выдачи.
    """

    def __init__(self, prefix: str, width: int = 5) -> None:
        self.prefix = prefix
        self.width = width
        self._next_by_year: dict[int, int] = {}

    def next(self, doc_date: date) -> str:
        """Возвращает следующий номер для даты (определяет год счётчика)."""
        year = doc_date.year
        number = self._next_by_year.get(year, 1)
        self._next_by_year[year] = number + 1
        return f"{self.prefix}-{number:0{self.width}d}"

    def basis(self, year: int, next_number: int) -> None:
        """Устанавливает стартовое значение счётчика для года (если больше текущего)."""
        current = self._next_by_year.get(year, 1)
        if next_number > current:
            self._next_by_year[year] = next_number


def resolve_targets(
    args: argparse.Namespace,
) -> Tuple[str, Path, AppSettings]:
    """Определяет URL базы данных, каталог хранилища и настройки приложения."""
    settings_manager = SettingsManager(PROJECT_ROOT)
    settings: AppSettings = (
        settings_manager.load() if settings_manager.exists else AppSettings()
    )

    db_url = args.db_url or settings.db_url
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", "", 1))
        if not db_path.is_absolute():
            db_url = f"sqlite:///{(PROJECT_ROOT / db_path).as_posix()}"

    storage = Path(args.storage) if args.storage else None
    if storage is None:
        storage = (
            Path(settings.storage_path)
            if settings.storage_path
            else PROJECT_ROOT / "Файловое хранилище"
        )

    return db_url, storage, settings


def clear_database(session: Session) -> None:
    """Удаляет все записи из всех таблиц базы данных."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()


def attach_file(
    session: Session,
    storage_root: Path,
    document,
    subdirectory: str,
) -> FileRecord:
    """Создаёт файл в хранилище и регистрирует его как вложение документа."""
    date_str = (
        document.outgoing_date.isoformat() if document.outgoing_date else "unknown"
    )
    relative_dir = (
        Path(FILES_DIR)
        / subdirectory
        / date_str
        / (document.outgoing_number or str(document.id))
    )
    target_dir = storage_root / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    name = f"Приложение-{random.randint(1, 999):03d}"
    target_path = target_dir / f"{name}.txt"
    target_path.write_text(
        f"{document.name}\n\nСгенерировано для тестирования.\n",
        encoding="utf-8",
    )

    record = FileRecord(name=name, extension="txt", path=relative_dir.as_posix())
    session.add(record)
    document.files.append(record)
    return record


def document_files_subdirectory(document) -> str:
    """Возвращает подкаталог хранилища для вложений документа."""
    from internal_correspondence.orm.models import ScientificMaterial

    return (
        MATERIAL_FILES_DIR
        if isinstance(document, ScientificMaterial)
        else TELEGRAM_FILES_DIR
    )


def random_dates(start: date, end: date) -> List[date]:
    """Возвращает список дат от start до end включительно по возрастанию."""
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def new_uuid() -> uuid.UUID:
    """Возвращает новый UUID (обёртка для читаемости вызовов в генераторах)."""
    return uuid.uuid4()


__all__ = [
    "DEFAULT_PERIOD_DAYS",
    "PROJECT_ROOT",
    "YearlyCounter",
    "attach_file",
    "clear_database",
    "default_period",
    "document_files_subdirectory",
    "new_uuid",
    "parse_date",
    "parse_range",
    "random_dates",
    "resolve_targets",
]
