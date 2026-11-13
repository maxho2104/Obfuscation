"""Тесты элементов редактирования и базового диалога сущности."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import MaterialType, Role
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.document_dialogs import (
    MaterialEditDialog,
    TelegramEditDialog,
)
from internal_correspondence.gui.edit_elements import (
    NumberDateEditElement,
    ReportAddressesEditElement,
    create_element,
)
from internal_correspondence.gui.entity_edit_dialog import EntityEditDialog
from internal_correspondence.orm.labels import field_unique
from internal_correspondence.orm.models import (
    Branch,
    Leader,
    ReportAddress,
    ScientificMaterial,
    Telegram,
    TerritorialUnit,
)
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'edit_dialogs.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="function")
def base_data(db_manager):
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
        session.add(Leader(id="L1", active=True))
        session.add(Leader(id="L2", active=True))
        session.commit()
    return db_manager


# ---------------------------------------------------------------------------
# Метаданные: уникальность
# ---------------------------------------------------------------------------


def test_unique_fields_from_constraint() -> None:
    """Уникальность определяется из составного UniqueConstraint модели."""
    assert field_unique(ScientificMaterial, "outgoing_number")
    assert field_unique(ScientificMaterial, "outgoing_date")
    assert not field_unique(ScientificMaterial, "name")


# ---------------------------------------------------------------------------
# Простые элементы и пары «номер и дата»
# ---------------------------------------------------------------------------


def test_create_element_by_column_type(qapp, db_manager) -> None:
    """Фабрика выбирает элемент по типу колонки."""
    element = create_element(ScientificMaterial.name, db_manager.get_session())
    assert element.field_name == "name"

    element = create_element(
        ScientificMaterial.outgoing_date, db_manager.get_session()
    )
    assert element.field_name == "outgoing_date"


def test_number_date_required_validation(qapp, db_manager) -> None:
    """Обязательная пара требует оба значения; необязательная — оба или ни одного."""
    required = NumberDateEditElement(
        ScientificMaterial.outgoing_number, ScientificMaterial.outgoing_date, required=True
    )
    assert required.validate() is not None
    required.number_edit.setText("1")
    assert required.validate() is not None
    required.date_edit.setDate(date(2026, 1, 10))
    assert required.validate() is None

    optional = NumberDateEditElement(
        ScientificMaterial.incoming_number, ScientificMaterial.incoming_date
    )
    assert optional.validate() is None
    optional.number_edit.setText("2")
    assert optional.validate() is not None
    optional.date_edit.setDate(date(2026, 2, 10))
    assert optional.validate() is None


def test_number_date_collects_both_columns(qapp, db_manager) -> None:
    """Пара «номер и дата» отдаёт обе колонки в данные диалога."""
    pair = NumberDateEditElement(
        ScientificMaterial.outgoing_number, ScientificMaterial.outgoing_date, required=True
    )
    pair.number_edit.setText("5")
    pair.date_edit.setDate(date(2026, 3, 1))
    target = {}
    pair.collect_data(target)
    assert target == {"outgoing_number": "5", "outgoing_date": date(2026, 3, 1)}


# ---------------------------------------------------------------------------
# Адресация доклада (расширенная таблица связности)
# ---------------------------------------------------------------------------


def test_report_addresses_element(base_data) -> None:
    """Элемент адресации сохраняет существующие записи и создаёт новые."""
    with base_data.get_session() as session:
        element = ReportAddressesEditElement(Telegram.report_addresses, session)
        existing = ReportAddress(leader_id="L1", report_date=date(2026, 3, 5))
        element.set_value([existing])

        target = {}
        element.collect_data(target)
        assert target["report_addresses"] == [existing]

        # Новая строка с пустой датой («ещё не доложено»)
        element._append_row("L2", None)
        target = {}
        element.collect_data(target)
        addresses = {address.leader_id: address for address in target["report_addresses"]}
        assert addresses["L1"] is existing
        assert addresses["L1"].report_date == date(2026, 3, 5)
        assert addresses["L2"].report_date is None

        # Метка руководителя получает «+» при заполненной дате
        leader_item = element.table.item(0, 0)
        assert leader_item.text().endswith("+")
        leader_item = element.table.item(1, 0)
        assert not leader_item.text().endswith("+")


def test_format_report_addresses() -> None:
    """Формат отображения адресации: «ИД+» через запятую."""
    from internal_correspondence.gui.edit_elements import format_report_addresses

    first = ReportAddress(leader_id="L2", report_date=date(2026, 3, 5))
    second = ReportAddress(leader_id="L1", report_date=None)
    assert format_report_addresses([first, second]) == "L1, L2+"


# ---------------------------------------------------------------------------
# Базовый диалог справочника
# ---------------------------------------------------------------------------


def test_reference_dialog_defaults_and_data(qapp, base_data) -> None:
    """Диалог справочника строит поля по умолчанию и отдаёт введённые данные."""
    with base_data.get_session() as session:
        dialog = EntityEditDialog(session, TerritorialUnit)
        assert dialog.element("id") is not None
        assert dialog.element("name") is not None
        # Автозаполняемые и служебные поля не отображаются
        assert dialog.element("change_id") is None

        dialog.element("id").line_edit.setText("MSK")
        dialog.element("name").line_edit.setText("Москва")
        data = dialog.get_data()
        assert data == {"id": "MSK", "name": "Москва"}


def test_reference_dialog_fk_combo(qapp, base_data) -> None:
    """FK-колонка отображается комбобоксом связанной сущности."""
    with base_data.get_session() as session:
        dialog = EntityEditDialog(session, Branch, role=Role.BRANCH.value, fixed_branch_id=None)
        element = dialog.element("territorial_unit_id")
        assert element is not None
        # Филиал в диалоге справочника не показывается: branch_id нет у Branch,
        # territorial_unit_id — обязателен, нулевой элемент отсутствует
        assert element.combo.itemData(0) is not None


def test_required_validation_message(qapp, base_data) -> None:
    """Обязательное незаполненное поле даёт сообщение с его меткой."""
    with base_data.get_session() as session:
        element = create_element(TerritorialUnit.name, session)
        message = element.validate()
        assert message == STRINGS.msg_required_field.format(label="Наименование")


def test_duplicate_found_by_unique_constraint(qapp, base_data) -> None:
    """Дубль пары «номер + дата» определяется до записи в БД."""
    with base_data.get_session() as session:
        session.add(
            ScientificMaterial(
                type=MaterialType.MESSAGE,
                outgoing_number="М-1",
                outgoing_date=date(2026, 1, 1),
                name="Материал",
                branch_id="F1",
            )
        )
        session.commit()

        dialog = MaterialEditDialog(
            session, branch_id="F1", role=Role.BRANCH.value
        )
        dialog.element("outgoing_number").number_edit.setText("М-1")
        dialog.element("outgoing_number").date_edit.setDate(date(2026, 1, 1))
        dialog.element("type").set_value(int(MaterialType.MESSAGE))
        dialog.element("name").set_value("Другой")
        result = dialog._find_duplicate()
        assert result is not None
        message, element = result
        assert element is dialog.element("outgoing_number")
        assert "Исходящий номер" in message


# ---------------------------------------------------------------------------
# Диалоги документов: роли и условная видимость
# ---------------------------------------------------------------------------


def test_material_dialog_branch_visibility(qapp, base_data) -> None:
    """Поля материала показываются/скрываются по типу (роль «филиал»)."""
    with base_data.get_session() as session:
        dialog = MaterialEditDialog(
            session, branch_id="F1", role=Role.BRANCH.value
        )
        type_element = dialog.element("type")
        serial = dialog.element("serial_number")
        cost = dialog.element("cost")

        type_element.set_value(int(MaterialType.MESSAGE))
        assert serial.isHidden()
        assert cost.isHidden()

        type_element.set_value(int(MaterialType.TECHNICAL_DOCUMENT))
        assert not serial.isHidden()
        assert cost.isHidden()

        type_element.set_value(int(MaterialType.PRODUCT_SAMPLE))
        assert not serial.isHidden()
        assert not cost.isHidden()

        # Исходящий номер и дата — обязательные
        outgoing = dialog.element("outgoing_number")
        assert outgoing.is_required()
        assert dialog.element("name").is_required()
        # Филиал фиксирован и не отображается
        assert dialog.element("branch_id") is None
        data = dialog.get_data()
        assert data["branch_id"] == "F1"


def test_material_dialog_head_office_fields(qapp, base_data) -> None:
    """Для головного офиса основные поля — потребитель, входящие, комментарий."""
    with base_data.get_session() as session:
        dialog = MaterialEditDialog(
            session, branch_id=None, role=Role.HEAD_OFFICE.value
        )
        # Редактор филиала отображается для ручного ввода
        branch_element = dialog.element("branch_id")
        assert branch_element is not None

        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-9",
            outgoing_date=date(2026, 5, 1),
            name="Материал",
            branch_id="F1",
        )
        session.add(material)
        session.commit()

        edit_dialog = MaterialEditDialog(
            session, material=material, role=Role.HEAD_OFFICE.value
        )
        data = edit_dialog.get_data()
        assert data["branch_id"] == "F1"
        assert data["outgoing_number"] == "М-9"


def test_telegram_dialog_branch_role(qapp, base_data) -> None:
    """Диалог телеграммы (роль «филиал»): обязательные исходящие, адресация."""
    with base_data.get_session() as session:
        dialog = TelegramEditDialog(session, branch_id="F1", role=Role.BRANCH.value)
        assert dialog.element("outgoing_number").is_required()
        assert dialog.element("report_addresses") is not None
        assert dialog.element("employees") is not None
        assert dialog.element("branch_id") is None


def test_extra_fields_toggle(qapp, base_data) -> None:
    """Кнопка «Больше» раскрывает дополнительные поля."""
    with base_data.get_session() as session:
        dialog = MaterialEditDialog(session, branch_id="F1", role=Role.BRANCH.value)
        incoming = dialog.element("incoming_number")
        assert incoming is not None
        assert dialog.more_button is not None
        # Доп. поле скрыто, пока не нажата «Больше»
        assert incoming.isHidden()
        dialog.more_button.click()
        assert not incoming.isHidden()
