"""Доступ к русскоязычным меткам сущностей и полей ORM-моделей.

Метки объявляются рядом с описанием сущностей в ``orm/models.py``:
наименование сущности — атрибуты ``__entity_label__`` и
``__entity_label_plural__`` класса; метки полей — словарь ``info`` колонок
и связей, либо словарь ``__field_labels__`` для вычисляемых свойств.

Активный пакет предметной области (``core/domain_pack.py``) может
переопределять любые встроенные метки — это основа white-label
настройки приложения под другую предметную область.
"""

import logging
from typing import Any, Dict

from sqlalchemy import inspect as sa_inspect

from internal_correspondence.core.domain_pack import get_domain_pack
from internal_correspondence.utils.string_resources import STRINGS

logger = logging.getLogger("internal_correspondence.orm.labels")


def entity_label(model_class: type, plural: bool = False) -> str:
    """Возвращает русскоязычное наименование сущности.

    Args:
        model_class: Класс ORM-модели.
        plural: Вернуть наименование множественного числа.
    """
    pack_label = get_domain_pack().entity_label(model_class.__name__, plural=plural)
    if pack_label:
        return pack_label
    label = None
    if plural:
        label = getattr(model_class, "__entity_label_plural__", None)
    label = label or getattr(model_class, "__entity_label__", None)
    if not label:
        logger.warning("Сущность %s не имеет русскоязычной метки", model_class.__name__)
        return model_class.__name__
    return label


def field_info(model_class: type, field_name: str) -> Dict[str, Any]:
    """Возвращает метаданные отображения поля (info) или пустой словарь.

    Порядок поиска: колонка таблицы, связь ORM, словарь __field_labels__;
    поверх результата накладываются переопределения активного пакета
    предметной области.
    """
    info: Dict[str, Any] = {}
    mapper = sa_inspect(model_class)
    column = mapper.columns.get(field_name)
    if column is not None and column.info:
        info = dict(column.info)
    elif field_name in mapper.relationships:
        relationship = mapper.relationships[field_name]
        if relationship.info:
            info = dict(relationship.info)
    else:
        field_labels = getattr(model_class, "__field_labels__", {})
        if field_name in field_labels:
            info = {"label": field_labels[field_name]}
    # Переопределения пакета предметной области имеют приоритет
    info.update(get_domain_pack().entity_field_info(model_class.__name__, field_name))
    return info


def field_label(model_class: type, field_name: str) -> str:
    """Возвращает полную русскоязычную метку поля.

    Для составных путей ("branch.short_name") возвращает метку первого
    компонента — связи.
    """
    head = field_name.split(".", 1)[0]
    label = field_info(model_class, head).get("label")
    if label:
        return label
    logger.warning(
        "Поле %s.%s не имеет русскоязычной метки",
        model_class.__name__,
        field_name,
    )
    return field_name


def field_short_label(model_class: type, field_name: str) -> str:
    """Возвращает краткую метку поля (для шапок таблиц).

    При отсутствии краткой метки возвращает полную.
    """
    info = field_info(model_class, field_name.split(".", 1)[0])
    return info.get("short") or field_label(model_class, field_name)


def field_required(model_class: type, field_name: str) -> bool:
    """Проверяет обязательность заполнения поля.

    Явный флаг ``required`` (в info колонки или в пакете предметной
    области) имеет приоритет; иначе обязательность определяется
    ограничением NOT NULL колонки.
    """
    mapper = sa_inspect(model_class)
    column = mapper.columns.get(field_name)
    if column is None:
        return False
    info = field_info(model_class, field_name)
    if "required" in info:
        return bool(info["required"])
    return not column.nullable


def field_form_label(model_class: type, field_name: str) -> str:
    """Возвращает метку поля для форм с пометкой обязательности."""
    label = field_label(model_class, field_name)
    if field_required(model_class, field_name):
        return f"{label} *:"
    return f"{label}:"


def entity_label_prepositional(model_class: type, plural: bool = False) -> str:
    """Возвращает наименование сущности в предложном падеже.

    Используется в сообщениях вида «запись о научном материале».
    При отсутствии формы в метаданных возвращает наименование в И.п.
    в нижнем регистре.
    """
    pack_label = get_domain_pack().entity_label_prepositional(
        model_class.__name__, plural=plural
    )
    if pack_label:
        return pack_label
    attr = (
        "__entity_label_prepositional_plural__"
        if plural
        else "__entity_label_prepositional__"
    )
    label = getattr(model_class, attr, None)
    if label:
        return label
    logger.warning(
        "Сущность %s не имеет предложной формы наименования",
        model_class.__name__,
    )
    return entity_label(model_class, plural=plural).lower()


def plural_records(count: int) -> str:
    """Склоняет слово «запись» с числительным: 1 запись, 2 записи, 5 записей."""
    if count <= 0:
        raise ValueError(f"count должен быть положительным, получено {count}")
    remainder = count % 10
    hundred = count % 100
    if remainder == 1 and hundred != 11:
        word = "запись"
    elif 2 <= remainder <= 4 and not 12 <= hundred <= 14:
        word = "записи"
    else:
        word = "записей"
    return f"{count} {word}"


def deletion_confirmation_text(model_class: type, count: int) -> str:
    """Формирует текст подтверждения удаления записей сущности.

    Для одной записи: «Вы действительно хотите удалить запись
    о научном материале?»; для нескольких — с числительным и формой
    множественного числа.
    """
    if count == 1:
        return STRINGS.msg_delete_records_one.format(
            entity=entity_label_prepositional(model_class)
        )
    return STRINGS.msg_delete_records_many.format(
        records=plural_records(count),
        entity=entity_label_prepositional(model_class, plural=True),
    )
