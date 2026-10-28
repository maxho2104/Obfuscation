"""Настройка логирования приложения."""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from internal_correspondence.core.constants import LOGS_DIR


def configure_logging(
    app_dir: Path,
    level: int = logging.DEBUG,
    log_to_stderr: bool = True,
) -> logging.Logger:
    """Настраивает логирование в файл с ежедневной ротацией и опционально в stderr.

    Args:
        app_dir: Корневой каталог приложения.
        level: Уровень логирования.
        log_to_stderr: Выводить ли логи также в stderr.

    Returns:
        Корневой логгер приложения.
    """
    logs_dir = app_dir / LOGS_DIR
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / "app.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger("internal_correspondence")
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # Файловый обработчик с ежедневной ротацией и хранением 30 дней
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if log_to_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(level)
        stderr_handler.setFormatter(formatter)
        root_logger.addHandler(stderr_handler)

    return root_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Возвращает именованный логгер приложения."""
    full_name = "internal_correspondence"
    if name:
        full_name = f"{full_name}.{name}"
    return logging.getLogger(full_name)
