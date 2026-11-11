"""Диалоги редактирования справочников."""

from typing import Any, Dict

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
)

from internal_correspondence.core.domain_pack import enum_labels
from internal_correspondence.orm.labels import (
    entity_label,
    field_form_label,
    field_label,
)
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


class BaseReferenceDialog(QDialog):
    """Базовый диалог справочника.

    Подписи полей форм и заголовок окна берутся из метаданных
    ORM-модели (см. ``orm/labels.py``).
    """

    model_class = None

    def __init__(self, session, item=None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        model = type(item) if item is not None else self.model_class
        if model is not None:
            self.setWindowTitle(entity_label(model))
        self._setup_ui()
        if item:
            self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_save(self) -> None:
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        raise NotImplementedError


class TerritorialUnitDialog(BaseReferenceDialog):
    """Диалог территориальной единицы."""

    model_class = TerritorialUnit

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.name_edit = QLineEdit()
        self.form.addRow(field_form_label(TerritorialUnit, "id"), self.id_edit)
        self.form.addRow(field_form_label(TerritorialUnit, "name"), self.name_edit)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.name_edit.setText(self.item.name)

    def get_data(self) -> Dict[str, Any]:
        return {"id": self.id_edit.text().strip(), "name": self.name_edit.text().strip()}


class BranchDialog(BaseReferenceDialog):
    """Диалог филиала."""

    model_class = Branch

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.name_edit = QLineEdit()
        self.short_name_edit = QLineEdit()
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("—", None)
        for unit in self.session.query(TerritorialUnit).order_by(TerritorialUnit.name).all():
            self.unit_combo.addItem(unit.name, unit.id)
        self.form.addRow(field_form_label(Branch, "id"), self.id_edit)
        self.form.addRow(field_form_label(Branch, "name"), self.name_edit)
        self.form.addRow(field_form_label(Branch, "short_name"), self.short_name_edit)
        self.form.addRow(field_form_label(Branch, "territorial_unit_id"), self.unit_combo)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.name_edit.setText(self.item.name)
        self.short_name_edit.setText(self.item.short_name or "")
        idx = self.unit_combo.findData(self.item.territorial_unit_id)
        if idx >= 0:
            self.unit_combo.setCurrentIndex(idx)

    def get_data(self) -> Dict[str, Any]:
        return {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "short_name": self.short_name_edit.text().strip(),
            "territorial_unit_id": self.unit_combo.currentData(),
        }


class CountryDialog(BaseReferenceDialog):
    """Диалог страны."""

    model_class = Country

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.name_edit = QLineEdit()
        self.form.addRow(field_form_label(Country, "id"), self.id_edit)
        self.form.addRow(field_form_label(Country, "name"), self.name_edit)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.name_edit.setText(self.item.name)

    def get_data(self) -> Dict[str, Any]:
        return {"id": self.id_edit.text().strip(), "name": self.name_edit.text().strip()}


class AcademicTitleDialog(BaseReferenceDialog):
    """Диалог научного звания."""

    model_class = AcademicTitle

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.name_edit = QLineEdit()
        self.genitive_edit = QLineEdit()
        self.dative_edit = QLineEdit()
        self.order_spin = QSpinBox()
        self.order_spin.setMinimum(0)
        self.order_spin.setMaximum(9999)
        self.form.addRow(field_form_label(AcademicTitle, "id"), self.id_edit)
        self.form.addRow(field_form_label(AcademicTitle, "name"), self.name_edit)
        self.form.addRow(field_form_label(AcademicTitle, "genitive"), self.genitive_edit)
        self.form.addRow(field_form_label(AcademicTitle, "dative"), self.dative_edit)
        self.form.addRow(field_form_label(AcademicTitle, "sort_order"), self.order_spin)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.name_edit.setText(self.item.name)
        self.genitive_edit.setText(self.item.genitive or "")
        self.dative_edit.setText(self.item.dative or "")
        self.order_spin.setValue(self.item.sort_order or 0)

    def get_data(self) -> Dict[str, Any]:
        return {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "genitive": self.genitive_edit.text().strip() or None,
            "dative": self.dative_edit.text().strip() or None,
            "sort_order": self.order_spin.value(),
        }


class ScientificTaskDialog(BaseReferenceDialog):
    """Диалог научной задачи."""

    model_class = ScientificTask

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        for key, label in enum_labels("scientific_task_type").items():
            self.type_combo.addItem(f"{label} ({key})", key)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setSpecialValueText("")
        self.partial_edit = QLineEdit()
        self.full_edit = QLineEdit()
        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setMaximumHeight(80)
        self.form.addRow(field_form_label(ScientificTask, "id"), self.id_edit)
        self.form.addRow(field_form_label(ScientificTask, "name"), self.name_edit)
        self.form.addRow(field_form_label(ScientificTask, "type"), self.type_combo)
        self.form.addRow(field_form_label(ScientificTask, "start_date"), self.start_date)
        self.form.addRow(field_form_label(ScientificTask, "end_date"), self.end_date)
        self.form.addRow(field_form_label(ScientificTask, "partial_threshold"), self.partial_edit)
        self.form.addRow(field_form_label(ScientificTask, "full_threshold"), self.full_edit)
        self.form.addRow(field_form_label(ScientificTask, "comment"), self.comment_edit)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.name_edit.setText(self.item.name)
        idx = self.type_combo.findData(self.item.type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        if self.item.start_date:
            self.start_date.setDate(self.item.start_date)
        if self.item.end_date:
            self.end_date.setDate(self.item.end_date)
        self.partial_edit.setText(str(self.item.partial_threshold) if self.item.partial_threshold else "")
        self.full_edit.setText(str(self.item.full_threshold) if self.item.full_threshold else "")
        self.comment_edit.setPlainText(self.item.comment or "")

    def get_data(self) -> Dict[str, Any]:
        return {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "type": self.type_combo.currentData(),
            "start_date": self.start_date.date().toPyDate(),
            "end_date": self.end_date.date().toPyDate(),
            "partial_threshold": float(self.partial_edit.text()) if self.partial_edit.text().strip() else None,
            "full_threshold": float(self.full_edit.text()) if self.full_edit.text().strip() else None,
            "comment": self.comment_edit.toPlainText().strip() or None,
        }


class ConsumerDialog(BaseReferenceDialog):
    """Диалог потребителя."""

    model_class = Consumer

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.short_name_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.form.addRow(field_form_label(Consumer, "id"), self.id_edit)
        self.form.addRow(field_form_label(Consumer, "short_name"), self.short_name_edit)
        self.form.addRow(field_form_label(Consumer, "name"), self.name_edit)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.short_name_edit.setText(self.item.short_name)
        self.name_edit.setText(self.item.name)

    def get_data(self) -> Dict[str, Any]:
        return {
            "id": self.id_edit.text().strip(),
            "short_name": self.short_name_edit.text().strip(),
            "name": self.name_edit.text().strip(),
        }


class LeaderDialog(BaseReferenceDialog):
    """Диалог руководителя."""

    model_class = Leader

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.active_check = QCheckBox(field_label(Leader, "active"))
        self.active_check.setChecked(True)
        self.form.addRow(field_form_label(Leader, "id"), self.id_edit)
        self.form.addRow("", self.active_check)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        self.active_check.setChecked(self.item.active)

    def get_data(self) -> Dict[str, Any]:
        return {"id": self.id_edit.text().strip(), "active": self.active_check.isChecked()}


class SourceDialog(BaseReferenceDialog):
    """Диалог источника."""

    model_class = Source

    def _setup_ui(self) -> None:
        super()._setup_ui()
        self.id_edit = QLineEdit()
        self.id_edit.setEnabled(self.item is None)
        self.type_combo = QComboBox()
        for key, label in enum_labels("source_type").items():
            self.type_combo.addItem(f"{label} ({key})", key)
        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setMaximumHeight(80)
        self.form.addRow(field_form_label(Source, "id"), self.id_edit)
        self.form.addRow(field_form_label(Source, "type"), self.type_combo)
        self.form.addRow(field_form_label(Source, "comment"), self.comment_edit)

    def _load_data(self) -> None:
        self.id_edit.setText(self.item.id)
        idx = self.type_combo.findData(self.item.type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.comment_edit.setPlainText(self.item.comment or "")

    def get_data(self) -> Dict[str, Any]:
        return {
            "id": self.id_edit.text().strip(),
            "type": self.type_combo.currentData(),
            "comment": self.comment_edit.toPlainText().strip() or None,
        }


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
