"""Формирование аналитических отчётов из встроенных DOCX-шаблонов."""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Dict

from docxtpl import DocxTemplate

from internal_correspondence.core.constants import ReportType
from internal_correspondence.core.domain_pack import dir_name
from internal_correspondence.utils.string_resources import STRINGS


TEMPLATE_NAMES = {
    ReportType.MONTH: "monthly_analysis.docx",
    ReportType.HALF_YEAR: "halfyear_analysis.docx",
}

# Эти контрольные суммы принадлежат только прежним встроенным шаблонам,
# которые не повторяли структуру предоставленных пользователем образцов.
# Пользовательские шаблоны с любым другим содержимым не перезаписываются.
_OBSOLETE_TEMPLATE_HASHES = {
    "monthly_analysis.docx": {
        "49a5dc56e603b3ba42d48a120cdd878fb990d51b2fcae4274e47933ef0d389fd",
    },
    "halfyear_analysis.docx": {
        "d9b7e10eada41842345b890c0c064abb19c57a096c1160d63e332960bb3232d1",
    },
}


class ReportTemplateError(RuntimeError):
    """Ошибка чтения или заполнения шаблона отчёта."""


def ensure_user_templates(storage_root: Path) -> Path:
    """Копирует новые шаблоны и безопасно обновляет известные старые версии."""
    target_dir = storage_root / dir_name("templates")
    target_dir.mkdir(parents=True, exist_ok=True)
    resource_dir = files("internal_correspondence.reports").joinpath("templates")
    for name in TEMPLATE_NAMES.values():
        target = target_dir / name
        if target.exists() and _file_sha256(target) not in _OBSOLETE_TEMPLATE_HASHES.get(
            name, set()
        ):
            continue
        resource = resource_dir.joinpath(name)
        with as_file(resource) as source:
            shutil.copy2(source, target)
    return target_dir


def _file_sha256(path: Path) -> str:
    """Возвращает SHA-256 файла, не загружая его целиком в память."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_report(
    report_type: ReportType,
    context: Dict[str, Any],
    storage_root: Path,
    output_path: Path,
) -> Path:
    """Заполняет шаблон и сохраняет итоговый DOCX, не изменяя оригинал."""
    template_dir = ensure_user_templates(storage_root)
    template_path = template_dir / TEMPLATE_NAMES[report_type]
    if not template_path.exists():
        raise ReportTemplateError(
            STRINGS.report_error_template_missing.format(path=template_path)
        )

    output_path = output_path.with_suffix(".docx")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        document = DocxTemplate(str(template_path))
        document.render(context, autoescape=True)
        document.save(str(output_path))
    except Exception as exc:  # pragma: no cover - конкретная ошибка зависит от DOCX
        raise ReportTemplateError(
            STRINGS.report_error_template_render.format(
                template=template_path.name,
                error=exc,
            )
        ) from exc

    _validate_rendered_document(output_path)
    return output_path


def _validate_rendered_document(path: Path) -> None:
    """Проверяет, что в итоговом документе не остались маркеры шаблона."""
    try:
        with zipfile.ZipFile(path, "r") as archive:
            xml_parts = [
                archive.read(name).decode("utf-8", errors="ignore")
                for name in archive.namelist()
                if name.startswith("word/") and name.endswith(".xml")
            ]
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReportTemplateError(
            STRINGS.report_error_damaged_docx.format(path=path)
        ) from exc
    xml = "\n".join(xml_parts)
    if "{{" in xml or "{%" in xml or "{#" in xml:
        raise ReportTemplateError(STRINGS.report_error_unresolved_fields)
