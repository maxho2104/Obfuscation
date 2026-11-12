"""Операции с файлами файлового хранилища.

Чистые файловые примитивы (без обращений к БД): поблочное копирование
с возможностью отмены, генерация неперекрывающихся имён вида
``file(1).doc``, удаление пустых директорий вверх по дереву. Используются
сервисом документов (привязка/отвязка файлов) и док-виджетом файлов.
"""

import shutil
from pathlib import Path
from typing import Callable, Optional

# Размер блока поблочного копирования (1 МиБ)
COPY_CHUNK_SIZE = 1024 * 1024


class FileServiceError(Exception):
    """Ошибка файловой операции хранилища."""

    pass


class FileCopyCancelled(FileServiceError):
    """Копирование отменено пользователем."""

    pass


def is_inside_storage(path: Path, storage_root: Path) -> bool:
    """Проверяет, находится ли файл внутри файлового хранилища."""
    try:
        path.resolve().relative_to(storage_root.resolve())
        return True
    except ValueError:
        return False


def unique_target_path(target_dir: Path, file_name: str) -> Path:
    """Возвращает путь, не перекрывающий существующие файлы.

    При совпадении имени к основе добавляется порядковый номер
    в круглых скобках, как в проводнике Windows: ``file(1).doc``.
    """
    candidate = target_dir / file_name
    if not candidate.exists():
        return candidate
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    counter = 1
    while True:
        candidate = target_dir / f"{stem}({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def copy_with_progress(
    source: Path,
    target: Path,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_chunk: Optional[Callable[[int], None]] = None,
    chunk_size: int = COPY_CHUNK_SIZE,
) -> None:
    """Копирует файл поблочно с контролем отмены и обратным вызовом.

    Args:
        source: Путь к исходному файлу.
        target: Путь назначения (перезаписывается при совпадении).
        should_cancel: Функция проверки отмены; истина — прервать.
        on_chunk: Вызывается после записи каждого блока (прочитано байт).
        chunk_size: Размер блока в байтах.

    Raises:
        FileCopyCancelled: Отмена до завершения (частичный файл удаляется).
        FileServiceError: Исходный файл недоступен.
    """
    if not source.exists():
        raise FileServiceError(f"Файл не найден: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    copied = 0
    try:
        with source.open("rb") as src, target.open("wb") as dst:
            while True:
                if should_cancel is not None and should_cancel():
                    raise FileCopyCancelled(str(source))
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                if on_chunk is not None:
                    on_chunk(copied)
            shutil.copystat(source, target, follow_symlinks=True)
    except FileCopyCancelled:
        # Недокопированный файл не должен оставаться в хранилище
        if target.exists():
            target.unlink()
        raise


def cleanup_empty_dirs(start: Path, stop_at: Path) -> None:
    """Удаляет пустые директории от ``start`` вверх, не трогая ``stop_at``.

    После удаления файла из хранилища удаляет ставшую пустой папку
    документа, затем — пустые родительские вплоть до (не включая)
    корневой папки типа документа в хранилище. Выход за пределы дерева
    ``stop_at`` невозможен: подъём прекращается, как только текущая
    папка перестаёт быть потомком ``stop_at``.
    """
    current = start
    stop = stop_at.resolve()
    while current.exists() and current.is_dir():
        resolved = current.resolve()
        if resolved == stop or stop not in resolved.parents:
            break
        try:
            if any(current.iterdir()):
                break
            current.rmdir()
        except OSError:
            break
        current = current.parent
