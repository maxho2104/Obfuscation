"""Связка пакетных перечислений с IntEnum-константами.

БД и экспортные файлы хранят целочисленные значения перечислений;
краткий текст («С», «ДОК», «Б»…) и метки определяются пакетом
предметной области. Имена членов IntEnum совпадают с ключами пакета.
"""

from enum import IntEnum
from typing import Dict, List, Optional, Tuple, Type

from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    ScientificTaskType,
    SourceType,
    TelegramReportType,
    TelegramType,
)
from internal_correspondence.core.domain_pack import (
    DomainPackError,
    enum_code_of,
    enum_label,
    get_domain_pack,
)

# Имя перечисления в пакете -> класс IntEnum
PACK_ENUMS: Dict[str, Type[IntEnum]] = {
    "material_type": MaterialType,
    "evaluation_value": EvaluationValue,
    "scientific_task_type": ScientificTaskType,
    "telegram_type": TelegramType,
    "telegram_report_type": TelegramReportType,
    "source_type": SourceType,
}


def pack_enum_key(enum_name: str, value: int) -> str:
    """Возвращает семантический ключ пакета для целочисленного значения.

    Неизвестное число возвращается как строковое представление.
    """
    enum_class = PACK_ENUMS.get(enum_name)
    if enum_class is None:
        return str(value)
    try:
        return enum_class(int(value)).name.lower()
    except ValueError:
        return str(value)


def pack_enum_display(enum_name: str, value: Optional[int]) -> str:
    """Возвращает краткий текст (код пакета) для целочисленного значения.

    Пустое значение -> пустая строка; неизвестное число -> его строковое
    представление; ключ, отсутствующий в пакете, -> сам ключ.
    """
    if value is None:
        return ""
    key = pack_enum_key(enum_name, value)
    if key == str(value):
        return key  # значение вне диапазона перечисления
    try:
        return enum_code_of(enum_name, key)
    except DomainPackError:
        return key


def pack_enum_choices(enum_name: str) -> List[Tuple[int, str]]:
    """Возвращает пары (значение, 'метка (код)') для наполнения комбобоксов.

    Члены, помеченные в пакете как deprecated (или отсутствующие в пакете),
    в выбор не попадают.
    """
    enum_class = PACK_ENUMS[enum_name]
    pack = get_domain_pack()
    try:
        active_keys = {value.key for value in pack.enum(enum_name).active()}
    except DomainPackError:
        active_keys = None
    choices: List[Tuple[int, str]] = []
    for member in enum_class:
        if active_keys is not None and member.name.lower() not in active_keys:
            continue
        code = pack_enum_display(enum_name, int(member))
        label = enum_label(enum_name, code)
        choices.append((int(member), f"{label} ({code})"))
    return choices
