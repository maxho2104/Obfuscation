"""Константы и перечисления приложения."""

from enum import Enum


class Role(str, Enum):
    """Роль приложения в сети организаций."""

    HEAD_OFFICE = "head_office"
    BRANCH = "branch"


class MaterialType(str, Enum):
    """Тип научного материала."""

    MESSAGE = "С"
    DOCUMENT = "ДОК"
    REFERENCE = "СПР"
    PRODUCT_SAMPLE = "ОП"
    TECHNICAL_DOCUMENT = "ТДОК"
    REPORT = "Д"


class ResearchType(str, Enum):
    """Тип научного изыскания."""

    EXPERIMENTAL = "Э"
    ANALYTICAL = "А"


class EvaluationValue(str, Enum):
    """Значение оценки научного материала с весовым коэффициентом."""

    USELESS = "Б"
    INTERESTING = "И"
    USEFUL = "П"
    IMPORTANT = "В"


class ScientificTaskType(str, Enum):
    """Тип научной задачи."""

    MAIN = "ОЗ"
    ADDITIONAL = "ДЗ"


class TelegramType(str, Enum):
    """Тип телеграммы."""

    THEMATIC = "Т"
    PROGRESS_REPORT = "ОХР"
    RESULTS_REPORT = "ОДР"


class TelegramReportType(str, Enum):
    """Тип доклада телеграммы."""

    REPORTED = "ДР"
    URGENTLY_REPORTED = "СДР"


class SourceType(str, Enum):
    """Тип источника научного материала."""

    EXPERIMENTAL_EQUIPMENT = "ЭО"
    SCIENTIFIC_WORK = "НТ"


# Специальный маркер удаления в поле changed_fields таблицы changes
DELETION_MARKER = "__DELETED__"

# Имя INI-файла настроек
CONFIG_FILE_NAME = "settings.ini"

# Директории приложения
LOGS_DIR = "Logs"
BACKUPS_DIR = "Backups"

# Поддиректории файлового хранилища
FILES_DIR = "Файлы"
TEMPLATES_DIR = "Шаблоны"
EXPORT_DIR = "Экспорт"

# Поддиректории прикреплённых файлов
MATERIAL_FILES_DIR = "Научные материалы"
TELEGRAM_FILES_DIR = "Телеграммы"

# Локализация
DEFAULT_LANGUAGE = "ru"

# Пагинация
DEFAULT_PAGE_SIZE = 50
