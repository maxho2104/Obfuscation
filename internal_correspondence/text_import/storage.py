"""Копирование исходного файла в файловое хранилище после commit."""

from __future__ import annotations

import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from internal_correspondence.text_import.config import ImporterConfig
from internal_correspondence.text_import.errors import StorageError
from internal_correspondence.text_import.models import StorageCopyResult


def _safe_part(value: str, fallback: str = "документ") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return cleaned or fallback


def _target_name(source: Path, doc_no: str = "", doc_date: Optional[date] = None) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [stamp]
    if doc_no.strip():
        parts.append(_safe_part(doc_no))
    if doc_date is not None:
        parts.append(doc_date.strftime("%d.%m.%Y"))
    parts.append(source.name)
    return "_".join(parts)


def copy_to_storage(
    source: Path,
    config: ImporterConfig,
    overwrite: bool = False,
    target_name: Optional[str] = None,
    doc_no: str = "",
    doc_date: Optional[date] = None,
) -> StorageCopyResult:
    source = Path(source)
    if not source.exists():
        raise StorageError("source_not_found", f"source file not found: {source}")
    target_dir = config.import_dir
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError("storage_mkdir_failed", str(exc)) from exc
    name = target_name or _target_name(source, doc_no, doc_date)
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
