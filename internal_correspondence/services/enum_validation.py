"""Проверка кодов перечислений в БД на соответствие активному пакету.

Внешний пакет предметной области может не содержать коды, уже
сохранённые в базе данных (например, пакет сменили, а старые записи
остались). Такие коды не сломают работу (метки фолбэкаются на сам код),
но о них стоит предупредить оператора.
"""

from typing import List, Tuple, Type

from sqlalchemy.orm import Session

from internal_correspondence.core.domain_pack import DomainPackError, get_domain_pack
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
    """Возвращает предупреждения о кодах БД, отсутствующих в активном пакете."""
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
        # Известны все коды, включая устаревшие (deprecated)
        known_codes = {value.code for value in enum_def.values}
        stored_codes = {
            row[0]
            for row in session.query(getattr(model, column_name)).distinct()
            if row[0] is not None
        }
        unknown = sorted(stored_codes - known_codes)
        if unknown:
            warning = (
                f"{model.__name__}.{column_name}: коды {', '.join(unknown)} "
                f"отсутствуют в пакете '{pack.id}' v{pack.version}"
            )
            logger.warning(warning)
            warnings.append(warning)
    return warnings
