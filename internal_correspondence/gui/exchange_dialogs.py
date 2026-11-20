"""Диалоги и потоковый воркер экспорта/импорта дельт.

- ``ExportBranchesDialog`` — выбор филиалов-получателей экспорта
  (головной офис): список с флажками и общий флажок «Все»;
- ``ExportWorker`` — формирование архивов в отдельном потоке с сигналами
  прогресса; сессия БД создаётся внутри потока;
- ``ImportWorker`` — применение импортируемого архива в отдельном потоке
  с сигналами прогресса; анализ архива и выбор записей выполняются
  в GUI-потоке до запуска воркера (``ImportPreviewDialog``);
- ``ImportPreviewDialog`` — анализ импортируемых изменений с цветовой
  маркировкой применимости: зелёный — применится сразу, жёлтый — не
  применится, но стоит обратить внимание, красный — отклонено.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import Role
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import Branch
from internal_correspondence.utils.string_resources import STRINGS

# Цвета маркировки применимости записей импорта
COLOR_OK = QColor("#2e7d32")
COLOR_WARNING = QColor("#f9a825")
COLOR_ERROR = QColor("#c62828")

_STATUS_COLORS = {
    "ok": COLOR_OK,
    "warning": COLOR_WARNING,
    "error": COLOR_ERROR,
}

_STATUS_TEXT = {
    "ok": STRINGS.status_ok,
    "warning": STRINGS.status_warning,
    "error": STRINGS.status_error,
}


class ExportBranchesDialog(QDialog):
    """Диалог выбора филиалов для экспорта (головной офис)."""

    def __init__(self, branches: Sequence[Branch], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_export_branches_title)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        hint = QLabel(STRINGS.column_branch)
        layout.addWidget(hint)

        self._list = QListWidget()
        for branch in branches:
            item = QListWidgetItem(branch.short_name or branch.name)
            item.setData(Qt.UserRole, branch.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self._list.addItem(item)
        layout.addWidget(self._list, 1)

        self._all_checkbox = QCheckBox(STRINGS.label_all_branches)
        self._all_checkbox.setChecked(True)
        self._all_checkbox.toggled.connect(self._toggle_all)
        self._list.itemChanged.connect(self._sync_all_state)
        layout.addWidget(self._all_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(STRINGS.button_apply)
        buttons.button(QDialogButtonBox.Cancel).setText(STRINGS.button_cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_all(self, checked: bool) -> None:
        """Отмечает/снимает флажки всех филиалов."""
        state = Qt.Checked if checked else Qt.Unchecked
        for index in range(self._list.count()):
            self._list.item(index).setCheckState(state)

    def _sync_all_state(self, _item: QListWidgetItem) -> None:
        """Синхронизирует общий флажок «Все» с состоянием списка."""
        checked = all(
            self._list.item(index).checkState() == Qt.Checked
            for index in range(self._list.count())
        )
        self._all_checkbox.blockSignals(True)
        self._all_checkbox.setChecked(checked)
        self._all_checkbox.blockSignals(False)

    def selected_branch_ids(self) -> List[str]:
        """Возвращает идентификаторы выбранных филиалов."""
        result = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result


class ExportWorker(QObject):
    """Формирует экспортные архивы в отдельном потоке.

    Сессия БД создаётся внутри потока: объект сессии SQLAlchemy нельзя
    использовать из потока, отличного от породившего.
    """

    progressed = pyqtSignal(int, int, str)  # готово, всего, пояснение
    succeeded = pyqtSignal(list)            # пути к сформированным архивам
    failed = pyqtSignal(str)                # текст ошибки

    def __init__(
        self,
        db_manager: DatabaseManager,
        storage_root: Path,
        retention_days: int,
        role: str,
        branch_id: Optional[str],
        branch_ids: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__()
        self._db_manager = db_manager
        self._storage_root = storage_root
        self._retention_days = retention_days
        self._role = role
        self._branch_id = branch_id
        self._branch_ids = list(branch_ids or ())

    @pyqtSlot()
    def run(self) -> None:
        """Выполняет экспорт и публикует результат сигналами."""
        session = self._db_manager.get_session()
        try:
            service = ExportService(
                session,
                self._storage_root,
                retention_days=self._retention_days,
                role=self._role,
                branch_id=self._branch_id,
                progress_cb=lambda cur, total, msg: self.progressed.emit(
                    cur, total, STRINGS.progress_export_entity.format(entity=msg)
                ),
            )
            if self._role == Role.HEAD_OFFICE.value:
                outputs = service.export_for_branches(self._branch_ids)
            else:
                outputs = [service.export_branch()]
            session.commit()
            self.succeeded.emit([str(path) for path in outputs])
        except Exception as exc:  # pylint: disable=broad-except
            session.rollback()
            self.failed.emit(str(exc))
        finally:
            session.close()


class ImportWorker(QObject):
    """Применяет импортируемый архив в отдельном потоке.

    Сессия БД создаётся внутри потока: объект сессии SQLAlchemy нельзя
    использовать из потока, отличного от породившего. Анализ архива и
    подтверждение записей выполняются в GUI-потоке до запуска воркера.
    """

    progressed = pyqtSignal(int, int, str)  # готово, всего, пояснение
    succeeded = pyqtSignal(object)          # {"result": ..., "recorded": int}
    failed = pyqtSignal(str)                # текст ошибки

    def __init__(
        self,
        db_manager: DatabaseManager,
        storage_root: Path,
        role: str,
        branch_id: Optional[str],
        archive_path: Path,
        exclude: Set[Tuple[str, str]],
        rejected_entries: Sequence[Dict[str, Any]],
    ) -> None:
        super().__init__()
        self._db_manager = db_manager
        self._storage_root = storage_root
        self._role = role
        self._branch_id = branch_id
        self._archive_path = archive_path
        self._exclude = set(exclude)
        self._rejected_entries = list(rejected_entries)

    @pyqtSlot()
    def run(self) -> None:
        """Выполняет импорт и публикует результат сигналами."""
        session = self._db_manager.get_session()
        try:
            service = ImportService(
                session,
                self._storage_root,
                self._role,
                self._branch_id,
                progress_cb=lambda current, total, entity: self.progressed.emit(
                    current,
                    total,
                    STRINGS.progress_import_entry.format(
                        current=current, total=total, entity=entity
                    ),
                ),
            )
            result = service.import_archive(self._archive_path, exclude=self._exclude)
            recorded = service.record_missing_requests(self._rejected_entries)
            session.commit()
            self.succeeded.emit({"result": result, "recorded": recorded})
        except Exception as exc:  # pylint: disable=broad-except
            session.rollback()
            self.failed.emit(str(exc))
        finally:
            session.close()


class ImportPreviewDialog(QDialog):
    """Предварительный анализ импортируемых изменений.

    Строки таблицы маркируются цветом: зелёный — применится сразу,
    жёлтый — не применится, но стоит обратить внимание, красный —
    отклонено. Кнопка «Применить» запускает импорт только «зелёных»
    записей; жёлтые и красные пропускаются.
    """

    def __init__(
        self, entries: Sequence[Dict[str, Any]], parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_import_preview_title)
        self.setMinimumSize(760, 480)

        layout = QVBoxLayout(self)
        counts = {"ok": 0, "warning": 0, "error": 0}
        for entry in entries:
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        summary = QLabel(
            STRINGS.label_import_summary.format(
                total=len(entries),
                ok=counts["ok"],
                warning=counts["warning"],
                error=counts["error"],
            )
        )
        layout.addWidget(summary)

        self._table = QTableWidget(len(entries), 5)
        self._table.setHorizontalHeaderLabels(
            [
                STRINGS.column_entity,
                STRINGS.column_key,
                STRINGS.column_operation,
                STRINGS.column_status,
                STRINGS.column_reason,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        operation_text = {
            "create": STRINGS.op_create,
            "update": STRINGS.op_update,
            "delete": STRINGS.op_delete,
        }
        for row, entry in enumerate(entries):
            color = _STATUS_COLORS.get(entry["status"], COLOR_OK)
            brush = QBrush(color)
            values = [
                entry["entity_label"],
                entry["pk"],
                operation_text.get(entry["operation"] or "", ""),
                _STATUS_TEXT[entry["status"]],
                entry["reason"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 3 or entry["status"] != "ok":
                    item.setForeground(brush)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
        self._table.setColumnWidth(4, 320)
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(STRINGS.button_apply)
        buttons.button(QDialogButtonBox.Cancel).setText(STRINGS.button_cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def excluded_keys(self, entries: Sequence[Dict[str, Any]]) -> Set[Tuple[str, str]]:
        """Возвращает ключи записей, которые не будут применены."""
        return {
            (entry["entity_name"], entry["pk"])
            for entry in entries
            if entry["status"] in ("warning", "error")
        }
