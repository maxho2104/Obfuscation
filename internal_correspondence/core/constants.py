"""Константы и перечисления приложения."""

from enum import Enum, IntEnum


class Role(str, Enum):
    """Роль приложения в сети организаций."""

    HEAD_OFFICE = "head_office"
    BRANCH = "branch"


class ChangeOperation(IntEnum):
    """Тип операции над сущностью, фиксируемый в записи Change.

    Внутреннее техническое перечисление: хранится в БД и экспортных
    файлах как целое число (0 — создание, 1 — изменение, 2 — удаление).
    """

    CREATE = 0
    UPDATE = 1
    DELETE = 2


class MaterialType(IntEnum):
    """Тип научного материала.

    Имена членов совпадают с ключами пакетного перечисления
    ``material_type``; значения хранятся в БД как целые числа,
    краткий текст («С», «ДОК»…) определяется пакетом предметной области.
    """

    MESSAGE = 0
    DOCUMENT = 1
    REFERENCE = 2
    PRODUCT_SAMPLE = 3
    TECHNICAL_DOCUMENT = 4
    REPORT = 5


class EvaluationValue(IntEnum):
    """Значение оценки научного материала (вес — в пакете предметной области)."""

    USELESS = 0
    INTERESTING = 1
    USEFUL = 2
    IMPORTANT = 3


class ScientificTaskType(IntEnum):
    """Тип научной задачи."""

    MAIN = 0
    ADDITIONAL = 1


class TelegramType(IntEnum):
    """Тип телеграммы."""

    THEMATIC = 0
    PROGRESS_REPORT = 1
    RESULTS_REPORT = 2


class TelegramReportType(IntEnum):
    """Тип доклада телеграммы."""

    REPORTED = 0
    URGENTLY_REPORTED = 1


class SourceType(IntEnum):
    """Тип источника научного материала."""

    EXPERIMENTAL_EQUIPMENT = 0
    SCIENTIFIC_WORK = 1


# Имя INI-файла настроек
CONFIG_FILE_NAME = "settings.ini"

# Срок хранения записей Change (в днях) по умолчанию; <= 0 — бессрочно
DEFAULT_CHANGES_RETENTION_DAYS = 30

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
