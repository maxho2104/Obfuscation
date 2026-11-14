"""Диалоги редактирования справочников на базовом диалоге сущности.

Каждый диалог — тонкая настройка ``EntityEditDialog``: элементы
редактирования выбираются автоматически по типам колонок и связей
(см. ``gui/edit_elements.py``), метки — из метаданных модели и пакета
предметной области.
"""

from typing import Optional

from PyQt5.QtWidgets import QWidget
from sqlalchemy.orm import Session

from internal_correspondence.gui.entity_edit_dialog import EntityEditDialog, FieldSpec
from internal_correspondence.orm.models import (
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Leader,
    ScientificTask,
    Source,
    TerritorialUnit,
)


class _ReferenceDialog(EntityEditDialog):
    """Базовая обёртка диалога справочника с совместимым вызовом."""

    model_class = None
    main_fields: Optional[list] = None
    extra_fields: Optional[list] = None

    def __init__(
        self, session: Session, item=None, parent: Optional[QWidget] = None
    ) -> None:
        if self.model_class is None:
            raise TypeError("Диалог справочника не задаёт model_class")
        super().__init__(
            session,
            self.model_class,
            entity=item,
            main_fields=self.main_fields,
            extra_fields=self.extra_fields,
            parent=parent,
        )


class TerritorialUnitDialog(_ReferenceDialog):
    """Диалог территориальной единицы."""

    model_class = TerritorialUnit


class BranchDialog(_ReferenceDialog):
    """Диалог филиала."""

    model_class = Branch


class CountryDialog(_ReferenceDialog):
    """Диалог страны."""

    model_class = Country


class AcademicTitleDialog(_ReferenceDialog):
    """Диалог научного звания."""

    model_class = AcademicTitle


class ScientificTaskDialog(_ReferenceDialog):
    """Диалог научной задачи."""

    model_class = ScientificTask


class ConsumerDialog(_ReferenceDialog):
    """Диалог потребителя."""

    model_class = Consumer


class LeaderDialog(_ReferenceDialog):
    """Диалог руководителя."""

    model_class = Leader


class SourceDialog(_ReferenceDialog):
    """Диалог источника."""

    model_class = Source


__all__ = [
    "AcademicTitleDialog",
    "BranchDialog",
    "ConsumerDialog",
    "CountryDialog",
    "LeaderDialog",
    "ScientificTaskDialog",
    "SourceDialog",
    "TerritorialUnitDialog",
]
