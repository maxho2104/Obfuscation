"""Тест полноты русскоязычных меток сущностей и полей ORM.

Охранитель: при добавлении сущности или колонки без метки, а также
столбца пресета без метаданных, тест падает.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.orm import models
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.labels import (
    deletion_confirmation_text,
    entity_label,
    entity_label_prepositional,
    field_form_label,
    field_label,
    field_required,
    field_short_label,
    plural_records,
)

# Служебные поля, не отображаемые пользователю
SERVICE_FIELDS = {"change_id", "row_version", "created_at", "updated_at"}

MODEL_CLASSES = [
    obj
    for obj in vars(models).values()
    if isinstance(obj, type) and issubclass(obj, Base) and hasattr(obj, "__tablename__")
]


def test_all_entities_have_labels() -> None:
    """У каждой сущности есть наименование в ед. и мн. числе."""
    assert len(MODEL_CLASSES) >= 17
    for cls in MODEL_CLASSES:
        assert getattr(cls, "__entity_label__", None), cls.__name__
        assert getattr(cls, "__entity_label_plural__", None), cls.__name__
        assert entity_label(cls)
        assert entity_label(cls, plural=True)


def test_all_columns_have_labels() -> None:
    """У каждой не служебной колонки есть русскоязычная метка."""
    for cls in MODEL_CLASSES:
        field_labels = getattr(cls, "__field_labels__", {})
        for column in cls.__table__.columns:
            if column.name in SERVICE_FIELDS:
                continue
            has_label = bool(column.info.get("label")) or column.name in field_labels
            assert has_label, f"{cls.__name__}.{column.name} не имеет метки"


def test_display_fields_have_labels() -> None:
    """Вычислимые поля документов, используемые в таблицах, имеют метки."""
    for cls in (models.ScientificMaterial, models.Telegram):
        for name in (
            "participating_employees",
            "participating_departments",
            "participating_workgroups",
            "evaluation_display",
        ):
            assert field_label(cls, name) != name, f"{cls.__name__}.{name}"


def test_relationship_paths_resolve() -> None:
    """Составные пути столбцов разрешаются в метки связей."""
    assert field_label(models.Branch, "territorial_unit.name") == "Территориальная единица"
    assert field_label(models.ScientificMaterial, "branch.short_name") == "Филиал"
    assert field_label(models.ScientificMaterial, "consumer.short_name") == "Потребитель"


def test_short_labels() -> None:
    """Краткие метки заполнены; при отсутствии краткой — полная."""
    assert field_short_label(models.ScientificMaterial, "outgoing_number") == "Исх. номер"
    assert field_short_label(models.ScientificMaterial, "name") == "Наименование"


def test_required_fields() -> None:
    """Обязательность: явный бизнес-флаг приоритетнее ограничения NOT NULL."""
    assert field_required(models.ScientificMaterial, "outgoing_number")
    assert field_required(models.ScientificMaterial, "name")
    assert not field_required(models.ScientificMaterial, "incoming_number")
    assert field_required(models.Telegram, "outgoing_date")
    assert not field_required(models.ScientificMaterial, "participating_employees")


def test_form_labels() -> None:
    """Метки форм содержат пометку обязательности."""
    assert field_form_label(models.ScientificMaterial, "outgoing_number") == "Исходящий номер *:"
    assert field_form_label(models.ScientificMaterial, "incoming_number") == "Входящий номер:"
    assert field_form_label(models.ScientificTask, "end_date") == "Конец действия:"


def test_column_presets_resolve() -> None:
    """Все столбцы пресетов приложения разрешаются в метаданные моделей."""
    from internal_correspondence.gui import application

    pairs = [
        (application.MATERIAL_COLUMNS, models.ScientificMaterial),
        (application.TELEGRAM_COLUMNS, models.Telegram),
        (application.TERRITORIAL_UNIT_COLUMNS, models.TerritorialUnit),
        (application.BRANCH_COLUMNS, models.Branch),
        (application.COUNTRY_COLUMNS, models.Country),
        (application.ACADEMIC_TITLE_COLUMNS, models.AcademicTitle),
        (application.SCIENTIFIC_TASK_COLUMNS, models.ScientificTask),
        (application.CONSUMER_COLUMNS, models.Consumer),
        (application.LEADER_COLUMNS, models.Leader),
        (application.SOURCE_COLUMNS, models.Source),
    ]
    for columns, model_class in pairs:
        assert columns, model_class.__name__
        for column in columns:
            # Заголовки не заданы явно — подставляются из метаданных
            assert column.header is None, f"{model_class.__name__}.{column.name}"
            resolved = field_short_label(model_class, column.name)
            assert resolved != column.name, f"{model_class.__name__}.{column.name} без метки"


def test_prepositional_labels() -> None:
    """Предложные формы наименований документов для сообщений."""
    assert entity_label_prepositional(models.ScientificMaterial) == "научном материале"
    assert (
        entity_label_prepositional(models.ScientificMaterial, plural=True)
        == "научных материалах"
    )
    assert entity_label_prepositional(models.Telegram) == "телеграмме"
    assert entity_label_prepositional(models.Telegram, plural=True) == "телеграммах"


@pytest.mark.parametrize(
    "count,expected",
    [
        (1, "1 запись"),
        (2, "2 записи"),
        (3, "3 записи"),
        (4, "4 записи"),
        (5, "5 записей"),
        (6, "6 записей"),
        (10, "10 записей"),
        (11, "11 записей"),
        (12, "12 записей"),
        (13, "13 записей"),
        (14, "14 записей"),
        (20, "20 записей"),
        (21, "21 запись"),
        (22, "22 записи"),
        (24, "24 записи"),
        (25, "25 записей"),
        (100, "100 записей"),
        (101, "101 запись"),
        (111, "111 записей"),
        (121, "121 запись"),
    ],
)
def test_plural_records(count: int, expected: str) -> None:
    """Склонение слова «запись» с числительными, включая 11–14."""
    assert plural_records(count) == expected


def test_plural_records_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        plural_records(0)


def test_deletion_confirmation_text() -> None:
    """Текст подтверждения удаления для единственной и множественной форм."""
    assert deletion_confirmation_text(
        models.ScientificMaterial, 1
    ) == "Вы действительно хотите удалить запись о научном материале?"
    assert deletion_confirmation_text(
        models.ScientificMaterial, 3
    ) == "Вы действительно хотите удалить 3 записи о научных материалах?"
    assert deletion_confirmation_text(
        models.Telegram, 1
    ) == "Вы действительно хотите удалить запись о телеграмме?"
    assert deletion_confirmation_text(
        models.Telegram, 11
    ) == "Вы действительно хотите удалить 11 записей о телеграммах?"
