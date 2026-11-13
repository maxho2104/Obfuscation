"""Диалоги редактирования научных материалов и телеграмм.

Диалоги построены на базовом диалоге редактирования сущности
(``gui/entity_edit_dialog.py``); набор отображаемых полей зависит от роли
приложения. Поля «Серийный номер», «Год выпуска», «Стоимость» и
«Номер и дата разрешительного документа» показываются/скрываются
в зависимости от выбранного значения «Типа» (семантические ключи
IntEnum, не коды пакета предметной области).

Прикрепление файлов к документам выполняется док-виджетом файлов
(см. ``gui/application.py``), а не диалогами редактирования.
"""

from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import (
    MaterialType,
    Role,
    TelegramType,
)
from internal_correspondence.gui.edit_elements import (
    ManyToManyEditElement,
    NumberDateEditElement,
    ReportAddressesEditElement,
)
from internal_correspondence.gui.entity_edit_dialog import EntityEditDialog, FieldSpec
from internal_correspondence.orm import models as models_mod
from internal_correspondence.orm.labels import entity_label


def _type_in(*types) -> Callable:
    """Возвращает предикат видимости «значение среди перечисленных типов»."""
    allowed = {int(item) for item in types}
    return lambda value: value in allowed


# Видимость полей научного материала по типу
_SAMPLE_OR_DOC = _type_in(MaterialType.PRODUCT_SAMPLE, MaterialType.TECHNICAL_DOCUMENT)
_SAMPLE_ONLY = _type_in(MaterialType.PRODUCT_SAMPLE)


class MaterialEditDialog(EntityEditDialog):
    """Диалог создания/редактирования научного материала.

    Args:
        session: Сессия БД.
        storage_root: Устарел, сохранён для совместимости вызовов.
        material: Редактируемый материал (None — создание).
        branch_id: Филиал документа (фиксированный для роли «филиал»).
        role: Роль приложения (Role.BRANCH.value / Role.HEAD_OFFICE.value).
    """

    def __init__(
        self,
        session: Session,
        storage_root=None,
        material: Optional[models_mod.ScientificMaterial] = None,
        branch_id: Optional[str] = None,
        role: Optional[str] = None,
        parent=None,
    ) -> None:
        is_branch = role == Role.BRANCH.value
        branch_id = branch_id or (material.branch_id if material else None)
        main_fields, extra_fields = self._field_specs(session, is_branch, branch_id)
        super().__init__(
            session,
            models_mod.ScientificMaterial,
            entity=material,
            main_fields=main_fields,
            extra_fields=extra_fields,
            role=role,
            fixed_branch_id=branch_id,
            visibility_driver="type",
            visibility_rules={
                "serial_number": _SAMPLE_OR_DOC,
                "release_year": _SAMPLE_OR_DOC,
                "cost": _SAMPLE_ONLY,
                "permit_number": _SAMPLE_OR_DOC,
            },
            parent=parent,
        )

    @staticmethod
    def _field_specs(
        session: Session, is_branch: bool, branch_id: Optional[str]
    ):
        """Возвращает наборы основных и дополнительных полей по роли."""
        m = models_mod
        outgoing = NumberDateEditElement(
            m.ScientificMaterial.outgoing_number,
            m.ScientificMaterial.outgoing_date,
            required=True,
        )
        incoming = NumberDateEditElement(
            m.ScientificMaterial.incoming_number,
            m.ScientificMaterial.incoming_date,
        )
        permit = NumberDateEditElement(
            m.ScientificMaterial.permit_number,
            m.ScientificMaterial.permit_date,
            label="Номер и дата разрешительного документа",
        )
        employees = ManyToManyEditElement(
            m.ScientificMaterial.employees,
            session,
            query_factory=_branch_employees_query(branch_id) if is_branch else None,
        )

        branch_main: List[FieldSpec] = [
            outgoing,
            m.ScientificMaterial.type,
            m.ScientificMaterial.serial_number,
            m.ScientificMaterial.release_year,
            m.ScientificMaterial.cost,
            permit,
            m.ScientificMaterial.name,
            m.ScientificMaterial.tasks,
            m.ScientificMaterial.countries,
            m.ScientificMaterial.consumer_id,
            employees,
            m.ScientificMaterial.comment,
        ]
        branch_extra: List[FieldSpec] = [incoming]

        office_main: List[FieldSpec] = [
            m.ScientificMaterial.consumer_id,
            incoming,
            m.ScientificMaterial.comment,
        ]
        office_extra: List[FieldSpec] = [
            outgoing,
            m.ScientificMaterial.type,
            m.ScientificMaterial.serial_number,
            m.ScientificMaterial.release_year,
            m.ScientificMaterial.cost,
            permit,
            m.ScientificMaterial.name,
            m.ScientificMaterial.tasks,
            m.ScientificMaterial.countries,
        ]
        return (
            (branch_main, branch_extra)
            if is_branch
            else (office_main, office_extra)
        )


class TelegramEditDialog(EntityEditDialog):
    """Диалог создания/редактирования телеграммы.

    Состав полей зависит от роли приложения; «Исходящий номер и дата» —
    обязательные к заполнению.
    """

    def __init__(
        self,
        session: Session,
        storage_root=None,
        telegram: Optional[models_mod.Telegram] = None,
        branch_id: Optional[str] = None,
        role: Optional[str] = None,
        parent=None,
    ) -> None:
        m = models_mod
        is_branch = role == Role.BRANCH.value
        outgoing = NumberDateEditElement(
            m.Telegram.outgoing_number,
            m.Telegram.outgoing_date,
            required=True,
        )
        incoming = NumberDateEditElement(
            m.Telegram.incoming_number,
            m.Telegram.incoming_date,
        )
        report_addresses = ReportAddressesEditElement(
            m.Telegram.report_addresses,
            session,
        )
        employees = ManyToManyEditElement(
            m.Telegram.employees,
            session,
            query_factory=_branch_employees_query(branch_id) if is_branch else None,
        )

        branch_main: List[FieldSpec] = [
            outgoing,
            m.Telegram.type,
            m.Telegram.name,
            m.Telegram.tasks,
            m.Telegram.countries,
            report_addresses,
            employees,
            m.Telegram.comment,
        ]
        branch_extra: List[FieldSpec] = [incoming, m.Telegram.report_type]

        office_main: List[FieldSpec] = [
            report_addresses,
            incoming,
            m.Telegram.report_type,
            m.Telegram.comment,
        ]
        office_extra: List[FieldSpec] = [
            outgoing,
            m.Telegram.type,
            m.Telegram.name,
            m.Telegram.tasks,
            m.Telegram.countries,
            m.Telegram.comment,
        ]
        super().__init__(
            session,
            m.Telegram,
            entity=telegram,
            main_fields=branch_main if is_branch else office_main,
            extra_fields=branch_extra if is_branch else office_extra,
            role=role,
            fixed_branch_id=branch_id,
            parent=parent,
        )


def _branch_employees_query(branch_id: Optional[str]) -> Optional[Callable]:
    """Фабрика запроса сотрудников филиала (None — без ограничения)."""
    if not branch_id:
        return None

    def factory(session: Session):
        return (
            session.query(models_mod.Employee)
            .join(models_mod.Department)
            .filter(models_mod.Department.branch_id == branch_id)
        )

    return factory


__all__ = [
    "MaterialEditDialog",
    "TelegramEditDialog",
]
