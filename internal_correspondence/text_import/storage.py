"""Копирование исходного файла в файловое хранилище после commit."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from internal_correspondence.text_import.config import ImporterConfig
from internal_correspondence.text_import.errors import StorageError
from internal_correspondence.text_import.models import StorageCopyResult


def _target_name(source: Path) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{source.name}"


def copy_to_storage(
    source: Path,
    config: ImporterConfig,
    overwrite: bool = False,
    target_name: Optional[str] = None,
) -> StorageCopyResult:
    source = Path(source)
    if not source.exists():
        raise StorageError("source_not_found", f"source file not found: {source}")
    target_dir = config.import_dir
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError("storage_mkdir_failed", str(exc)) from exc
    name = target_name or _target_name(source)
    target = target_dir / name
    renamed = False
    if target.exists() and not overwrite:
        stem, suffix = target.stem, target.suffix
        counter = 1
        while target.exists():
            target = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        renamed = True
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise StorageError("copy_failed", str(exc), target=str(target)) from exc
    return StorageCopyResult(path=target, renamed=renamed)
