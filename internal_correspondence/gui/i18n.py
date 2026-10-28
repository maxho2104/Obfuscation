"""Установка русскоязычных подписей стандартных элементов Qt."""

import sys
from pathlib import Path
from typing import List

import PyQt5
from PyQt5.QtCore import QLibraryInfo, QTranslator
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.logging_config import get_logger

logger = get_logger("i18n")

_installed_translators: List[QTranslator] = []


def _translation_dirs() -> List[Path]:
    """Возвращает каталоги, в которых может находиться файл перевода Qt."""
    dirs: List[Path] = [Path(QLibraryInfo.location(QLibraryInfo.TranslationsPath))]
    dirs.append(Path(PyQt5.__file__).resolve().parent / "Qt5" / "translations")

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        dirs.append(Path(bundle_dir) / "translations")
        dirs.append(Path(bundle_dir) / "PyQt5" / "Qt5" / "translations")

    app_dir = Path(__file__).resolve().parent.parent.parent
    dirs.append(app_dir / "translations")

    return dirs


def install_translations(app: QApplication, language: str = "ru") -> bool:
    """Загружает перевод стандартных элементов Qt для указанного языка.

    Args:
        app: Экземпляр приложения Qt.
        language: Код языка перевода (например, "ru").

    Returns:
        True, если файл перевода найден и установлен.
    """
    file_name = f"qtbase_{language}"
    for directory in _translation_dirs():
        if not (directory / f"{file_name}.qm").is_file():
            continue
        translator = QTranslator(app)
        if translator.load(file_name, str(directory)):
            app.installTranslator(translator)
            _installed_translators.append(translator)
            logger.info("Загружен перевод Qt %s из %s", language, directory)
            return True

    logger.warning(
        "Не найден файл перевода %s.qm: подписи стандартных кнопок останутся на английском",
        file_name,
    )
    return False
