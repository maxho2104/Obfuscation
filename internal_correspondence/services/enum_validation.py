"""Проверка кодов перечислений в БД на соответствие активному пакету.

Внешний пакет предметной области может не содержать значения, уже
сохранённые в базе данных (например, пакет сменили, а старые записи
остались). Такие значения не сломают работу (отображаются как есть),
но о них стоит предупредить оператора.
"""

from typing import List, Tuple, Type

from sqlalchemy.orm import Session

from internal_correspondence.core.domain_pack import DomainPackError, get_domain_pack
from internal_correspondence.core.enum_registry import pack_enum_key
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import (
    Evaluation,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
)

logger = get_logger("enum_validation")

# Колонки с кодами перечислений: (модель, имя колонки, имя перечисления в пакете)
ENUM_COLUMNS: List[Tuple[Type[Base], str, str]] = [
    (ScientificMaterial, "type", "material_type"),
    (Telegram, "type", "telegram_type"),
    (Telegram, "report_type", "telegram_report_type"),
    (ScientificTask, "type", "scientific_task_type"),
    (Source, "type", "source_type"),
    (Evaluation, "value", "evaluation_value"),
]


def validate_enum_codes(session: Session) -> List[str]:
    """Возвращает предупреждения о значениях БД, отсутствующих в активном пакете.

    В БД хранятся целые числа; проверка выполняется по семантическим
    ключам пакета (имена членов IntEnum в нижнем регистре).
    """
    pack = get_domain_pack()
    warnings: List[str] = []
    for model, column_name, enum_name in ENUM_COLUMNS:
        try:
            enum_def = pack.enum(enum_name)
        except DomainPackError:
            warnings.append(
                f"В пакете '{pack.id}' нет перечисления '{enum_name}' — "
                f"значения колонки {model.__name__}.{column_name} не проверялись"
            )
            continue
        # Известны все ключи, включая устаревшие (deprecated)
        known_keys = {value.key for value in enum_def.values}
        stored_values = {
            row[0]
            for row in session.query(getattr(model, column_name)).distinct()
            if row[0] is not None
        }
        unknown = sorted(
            int(value)
            for value in stored_values
            if pack_enum_key(enum_name, int(value)) not in known_keys
        )
        if unknown:
            warning = (
                f"{model.__name__}.{column_name}: значения {unknown} "
                f"отсутствуют в пакете '{pack.id}' v{pack.version}"
            )
            logger.warning(warning)
            warnings.append(warning)
    return warnings
