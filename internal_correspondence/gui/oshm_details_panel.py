"""Панель сведений об элементе ОШС.

Выдвигается справа в диалоге ОШС по двойному щелчку на элементе дерева.
Верхняя часть: аватарка с кнопками (+ добавить, − удалить, «Печать»),
наименование элемента с коэффициентом эффективности и поля данных,
таблица оценок за выбранный период. Ниже — задачи элемента и блок
сравнения периодов: две трёхкольцевые диаграммы (текущий период и
аналогичный период прошлого года). Кнопки: «Скрыть», «Изменить»,
«Статистика» (запрашивает у приложения статистику по элементу).
"""

from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.domain_pack import enum_label
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.oshm_element_charts import (
    ElementDonutWidget,
    PeriodSelectorWidget,
)
from internal_correspondence.orm.labels import field_label, field_short_label
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Department,
    Employee,
    ScientificTask,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.services.avatar_service import (
    AVATAR_HEIGHT,
    AVATAR_WIDTH,
    AvatarError,
    avatar_models_map,
    remove_avatar,
    resolve_avatar,
    save_avatar,
)
from internal_correspondence.services.element_stats_service import (
    ElementStatsService,
    shift_period_year,
)
from internal_correspondence.services.task_distribution_service import (
    NODE_BRANCH,
    NODE_DEPARTMENT,
    NODE_EMPLOYEE,
    NODE_REGION,
    NODE_WORKGROUP,
)
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("oshm_details_panel")

# Полезная нагрузка узла дерева: (тип узла, строковый идентификатор)
NodeRef = Tuple[str, str]

# Отображение пустого значения
EMPTY = "—"


def _date_text(value) -> str:
    """Форматирует дату для показа на панели."""
    return value.strftime("%d.%m.%Y") if value is not None else EMPTY


def _bool_text(value: bool) -> str:
    """Форматирует признак активности для показа на панели."""
    return STRINGS.value_yes if value else STRINGS.value_no


class TaskPickerDialog(QDialog):
    """Диалог выбора научных задач для назначения узлу."""

    def __init__(
        self,
        session,
        excluded_ids: Optional[List[str]] = None,
        allowed_ids: Optional[set] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self._excluded_ids = set(excluded_ids or [])
        # Ограничение выбора задачами старшего элемента (None — без ограничения)
        self._allowed_ids = allowed_ids
        self._tasks: List[ScientificTask] = []
        self.setWindowTitle(STRINGS.picker_tasks_title)
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._load_tasks()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_tasks(self) -> None:
        query = self.session.query(ScientificTask).order_by(ScientificTask.name)
        if self._excluded_ids:
            query = query.filter(ScientificTask.id.notin_(list(self._excluded_ids)))
        if self._allowed_ids is not None:
            query = query.filter(ScientificTask.id.in_(list(self._allowed_ids)))
        self._tasks = query.all()
        self.list_widget.clear()
        for task in self._tasks:
            item = QListWidgetItem(f"{task.id} — {task.name}")
            item.setData(Qt.UserRole, task.id)
            self.list_widget.addItem(item)

    def selected_tasks(self) -> List[ScientificTask]:
        """Возвращает задачи, выбранные в списке."""
        selected_ids = {
            item.data(Qt.UserRole) for item in self.list_widget.selectedItems()
        }
        return [task for task in self._tasks if task.id in selected_ids]


class ElementDetailsPanel(QWidget):
    """Панель данных элемента ОШС с задачами сотрудника и кнопками действий."""

    hide_requested = pyqtSignal()
    edit_requested = pyqtSignal(tuple)  # NodeRef
    statistics_requested = pyqtSignal(tuple)  # NodeRef

    def __init__(
        self,
        session,
        storage_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self._storage_root = storage_root
        self._stats_service = ElementStatsService(session)
        self.current_node: Optional[NodeRef] = None
        self._employee: Optional[Employee] = None
        # Узел, для которого показывается таблица задач, и его старший
        # элемент (ограничение назначения: задача должна быть у старшего)
        self._tasks_node: Optional[NodeRef] = None
        self._tasks_parent: Optional[NodeRef] = None
        self.setMinimumWidth(680)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Верхняя строка: аватар | название + коэффициент + поля | оценки
        top_row = QHBoxLayout()

        avatar_column = QVBoxLayout()
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(AVATAR_WIDTH, AVATAR_HEIGHT)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setWordWrap(True)
        self.avatar_label.setStyleSheet("border: 1px solid palette(Mid);")
        avatar_column.addWidget(self.avatar_label)
        avatar_buttons = QHBoxLayout()
        self.avatar_add_btn = QPushButton("+")
        self.avatar_add_btn.setToolTip(STRINGS.oshm_avatar_add)
        self.avatar_add_btn.clicked.connect(self._add_avatar)
        self.avatar_remove_btn = QPushButton("−")
        self.avatar_remove_btn.setToolTip(STRINGS.oshm_avatar_remove)
        self.avatar_remove_btn.clicked.connect(self._remove_avatar)
        self.print_btn = QPushButton(STRINGS.button_print)
        self.print_btn.clicked.connect(self._print_panel)
        avatar_buttons.addWidget(self.avatar_add_btn)
        avatar_buttons.addWidget(self.avatar_remove_btn)
        avatar_buttons.addWidget(self.print_btn)
        avatar_buttons.addStretch()
        avatar_column.addLayout(avatar_buttons)
        top_row.addLayout(avatar_column)

        center_column = QVBoxLayout()
        title_row = QHBoxLayout()
        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        title_row.addWidget(self.title_label, stretch=1)
        # Коэффициент эффективности — просто цифра справа от наименования
        self.coef_value = QLabel()
        coef_font = self.coef_value.font()
        coef_font.setBold(True)
        coef_font.setPointSize(coef_font.pointSize() + 4)
        self.coef_value.setFont(coef_font)
        title_row.addWidget(self.coef_value)
        title_row.addSpacing(8)
        center_column.addLayout(title_row)
        self.fields_layout = QFormLayout()
        center_column.addLayout(self.fields_layout)
        center_column.addStretch()
        top_row.addLayout(center_column, stretch=1)

        self.eval_group = QGroupBox(STRINGS.oshm_eval_table_title)
        eval_layout = QVBoxLayout(self.eval_group)
        self.eval_table = QTableWidget(0, 2)
        self.eval_table.setHorizontalHeaderLabels(
            [STRINGS.oshm_eval_col_value, STRINGS.oshm_eval_col_count]
        )
        self.eval_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.eval_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.eval_table.verticalHeader().setVisible(False)
        eval_layout.addWidget(self.eval_table)
        top_row.addWidget(self.eval_group)

        layout.addLayout(top_row)

        # Задачи сотрудника
        self.tasks_group = QGroupBox(STRINGS.oshm_tasks_section)
        tasks_layout = QVBoxLayout(self.tasks_group)
        self.tasks_table = QTableWidget(0, 4)
        self.tasks_table.setHorizontalHeaderLabels(
            [
                field_short_label(ScientificTask, "id"),
                field_short_label(ScientificTask, "name"),
                field_short_label(ScientificTask, "start_date"),
                field_short_label(ScientificTask, "end_date"),
            ]
        )
        self.tasks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tasks_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tasks_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tasks_table.verticalHeader().setVisible(False)
        tasks_layout.addWidget(self.tasks_table)

        tasks_buttons = QHBoxLayout()
        self.task_add_btn = QPushButton("+")
        self.task_add_btn.setToolTip(STRINGS.button_add)
        self.task_add_btn.clicked.connect(self._add_tasks)
        self.task_remove_btn = QPushButton("−")
        self.task_remove_btn.setToolTip(STRINGS.button_delete)
        self.task_remove_btn.clicked.connect(self._remove_tasks)
        tasks_buttons.addWidget(self.task_add_btn)
        tasks_buttons.addWidget(self.task_remove_btn)
        tasks_buttons.addStretch()
        tasks_layout.addLayout(tasks_buttons)
        layout.addWidget(self.tasks_group)

        # Нижний блок: выбор периода и две диаграммы
        # (текущий период и аналогичный период прошлого года)
        self.period_selector = PeriodSelectorWidget()
        self.period_selector.period_changed.connect(self._refresh_stats)
        layout.addWidget(self.period_selector)
        charts_row = QHBoxLayout()
        self.current_chart = ElementDonutWidget()
        self.previous_chart = ElementDonutWidget()
        charts_row.addWidget(self.current_chart)
        charts_row.addWidget(self.previous_chart)
        layout.addLayout(charts_row, stretch=1)

        # Кнопки действий
        buttons_row = QHBoxLayout()
        self.hide_btn = QPushButton(STRINGS.button_hide)
        self.hide_btn.clicked.connect(self.hide_requested.emit)
        self.edit_btn = QPushButton(STRINGS.button_edit)
        self.edit_btn.clicked.connect(self._edit_clicked)
        self.stats_btn = QPushButton(STRINGS.button_statistics)
        self.stats_btn.clicked.connect(self._show_statistics)
        buttons_row.addWidget(self.hide_btn)
        buttons_row.addWidget(self.edit_btn)
        buttons_row.addWidget(self.stats_btn)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

    # ------------------------------------------------------------------
    # Наполнение данными
    # ------------------------------------------------------------------

    def show_node(self, node: NodeRef, can_edit_people: bool = True) -> bool:
        """Заполняет панель данными узла. False — узел не найден (удалён)."""
        node_type, node_id = node
        loaders = {
            "branch": lambda: self._show_branch(node_id),
            "department": lambda: self._show_department(node_id),
            "workgroup": lambda: self._show_workgroup(node_id),
            "employee": lambda: self._show_employee(node_id),
            "head_office": lambda: self._show_head_office(),
        }
        loader = loaders.get(node_type)
        if loader is None:
            return False
        self._clear_fields()
        self._employee = None
        self._tasks_node = None
        self._tasks_parent = None
        if not loader():
            return False
        self.current_node = node
        # «Изменить»: людей редактирует только филиал; филиал и корень ГО
        # редактируются в справочниках, а не в этом диалоге
        can_edit = node_type in ("department", "workgroup") or (
            node_type == "employee" and can_edit_people
        )
        self.edit_btn.setEnabled(can_edit)
        # Задачи: филиал/отдел/группа — обеим ролям; сотрудник — только филиалу
        can_edit_tasks = node_type in ("branch", "department", "workgroup") or (
            node_type == "employee" and can_edit_people
        )
        self.set_tasks_editable(can_edit_tasks)
        if self._tasks_node is not None:
            self._fill_tasks()
            self.tasks_group.show()
        else:
            self.tasks_group.hide()
        self._update_avatar()
        self._refresh_stats()
        return True

    def _clear_fields(self) -> None:
        while self.fields_layout.rowCount():
            self.fields_layout.removeRow(0)

    def _add_field(self, label: str, value: Optional[str]) -> None:
        value_label = QLabel(value or EMPTY)
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fields_layout.addRow(f"{label}:", value_label)

    # ------------------------------------------------------------------
    # Аватарка
    # ------------------------------------------------------------------

    def _avatar_entity(self):
        """Возвращает сущность текущего узла (для аватарки и подписей)."""
        if self._tasks_node is None:
            return None
        node_type, node_id = self._tasks_node
        model = avatar_models_map().get(node_type)
        if model is None:
            return None
        key = node_id if model is Branch else UUID(node_id)
        return self.session.get(model, key)

    def _update_avatar(self) -> None:
        """Показывает аватарку элемента или заглушку."""
        entity = self._avatar_entity()
        can_edit = entity is not None and self._storage_root is not None
        self.avatar_add_btn.setEnabled(can_edit)
        self.avatar_remove_btn.setEnabled(can_edit)
        self.print_btn.setEnabled(self.current_node is not None)
        path = None
        if entity is not None and self._storage_root is not None:
            path = resolve_avatar(
                self._storage_root, entity, self._tasks_node[0]
            )
        if path is not None:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.avatar_label.setPixmap(
                    pixmap.scaled(
                        AVATAR_WIDTH,
                        AVATAR_HEIGHT,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                return
        self.avatar_label.setPixmap(QPixmap())
        self.avatar_label.setText(STRINGS.oshm_avatar_placeholder)

    def _add_avatar(self) -> None:
        """Переносит выбранное изображение в хранилище как аватарку элемента."""
        if self._tasks_node is None or self._storage_root is None:
            return
        entity = self._avatar_entity()
        if entity is None:
            return
        path, _selected = QFileDialog.getOpenFileName(
            self, STRINGS.dialog_avatar_open, "", STRINGS.file_filter_images
        )
        if not path:
            return
        try:
            save_avatar(entity, self._tasks_node[0], self._storage_root, Path(path))
        except AvatarError as exc:
            QMessageBox.warning(self, STRINGS.oshm_avatar_add, str(exc))
            return
        self._update_avatar()

    def _remove_avatar(self) -> None:
        """Удаляет аватарку элемента из хранилища."""
        if self._tasks_node is None or self._storage_root is None:
            return
        entity = self._avatar_entity()
        if entity is None:
            return
        answer = QMessageBox.question(
            self,
            STRINGS.oshm_avatar_remove,
            STRINGS.msg_avatar_remove_confirm,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        remove_avatar(entity, self._tasks_node[0], self._storage_root)
        self._update_avatar()

    # ------------------------------------------------------------------
    # Статистика элемента за период
    # ------------------------------------------------------------------

    def _refresh_stats(self, *_args) -> None:
        """Обновляет коэффициент, таблицу оценок и обе диаграммы."""
        if self._tasks_node is None:
            self.coef_value.setText(EMPTY)
            self.eval_table.setRowCount(0)
            return
        node_type, node_id = self._tasks_node
        period = self.period_selector.current_period()
        if period is None:
            return
        stats = self._stats_service.period_stats(node_type, node_id, period)
        previous = self._stats_service.period_stats(
            node_type, node_id, shift_period_year(period, -1)
        )
        # Коэффициент эффективности — средняя оценка за период (только цифра)
        self.coef_value.setText(
            f"{stats.avg_weight:.2f}" if stats.avg_weight is not None else EMPTY
        )
        # Таблица оценок за период
        values = sorted(stats.evaluation_counts)
        self.eval_table.setRowCount(len(values))
        for row, value in enumerate(values):
            short = pack_enum_display("evaluation_value", value)
            value_item = QTableWidgetItem(
                enum_label("evaluation_value", short)
            )
            count_item = QTableWidgetItem(str(stats.evaluation_counts[value]))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.eval_table.setItem(row, 0, value_item)
            self.eval_table.setItem(row, 1, count_item)
        # Диаграммы: текущий период и аналогичный период прошлого года
        self.current_chart.set_data(
            period.label,
            stats.material_type_counts,
            stats.telegram_type_counts,
            stats.evaluation_counts,
        )
        self.previous_chart.set_data(
            shift_period_year(period, -1).label,
            previous.material_type_counts,
            previous.telegram_type_counts,
            previous.evaluation_counts,
        )

    # ------------------------------------------------------------------
    # Печать
    # ------------------------------------------------------------------

    def _print_panel(self) -> None:
        """Выводит панель сведений на печать."""
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec_() != QPrintDialog.Accepted:
            return
        pixmap = self.grab()
        painter = QPainter(printer)
        try:
            rect = painter.viewport()
            scaled = pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(
                (rect.width() - scaled.width()) // 2,
                (rect.height() - scaled.height()) // 2,
                scaled,
            )
        finally:
            painter.end()

    def _show_head_office(self) -> bool:
        self.title_label.setText(STRINGS.role_head_office)
        self.tasks_group.hide()
        return True

    def _show_branch(self, node_id: str) -> bool:
        branch = self.session.get(Branch, node_id)
        if branch is None:
            return False
        self.title_label.setText(branch.name)
        self._add_field(field_label(Branch, "id"), branch.id)
        self._add_field(field_label(Branch, "short_name"), branch.short_name)
        if branch.territorial_unit is not None:
            self._add_field(
                field_label(Branch, "territorial_unit_id"),
                branch.territorial_unit.name,
            )
        # Задачи филиала — из пула региона (как во вкладке «Задачи»)
        self._tasks_node = (NODE_BRANCH, str(branch.id))
        if branch.territorial_unit_id:
            self._tasks_parent = (NODE_REGION, str(branch.territorial_unit_id))
        return True

    def _show_department(self, node_id: str) -> bool:
        department = self.session.get(Department, UUID(node_id))
        if department is None:
            return False
        self.title_label.setText(department.name)
        self._add_field(field_label(Department, "short_name"), department.short_name)
        if department.branch is not None:
            self._add_field(
                field_label(Department, "branch_id"), department.branch.name
            )
        self._add_field(
            field_label(Department, "active"), _bool_text(department.active)
        )
        # Задачи отдела — только из назначенных филиалу
        self._tasks_node = (NODE_DEPARTMENT, str(department.id))
        if department.branch_id:
            self._tasks_parent = (NODE_BRANCH, str(department.branch_id))
        return True

    def _show_workgroup(self, node_id: str) -> bool:
        workgroup = self.session.get(WorkingGroup, UUID(node_id))
        if workgroup is None:
            return False
        self.title_label.setText(workgroup.name)
        if workgroup.department is not None:
            self._add_field(
                field_label(WorkingGroup, "department_id"),
                workgroup.department.name,
            )
        self._add_field(field_label(WorkingGroup, "comment"), workgroup.comment)
        self._add_field(
            field_label(WorkingGroup, "active"), _bool_text(workgroup.active)
        )
        # Задачи группы — только из назначенных отделу
        self._tasks_node = (NODE_WORKGROUP, str(workgroup.id))
        if workgroup.department_id:
            self._tasks_parent = (NODE_DEPARTMENT, str(workgroup.department_id))
        return True
        return True

    def _show_employee(self, node_id: str) -> bool:
        employee = self.session.get(Employee, UUID(node_id))
        if employee is None:
            return False
        self._employee = employee
        self.title_label.setText(employee.display_name())
        self._add_field(field_label(Employee, "last_name"), employee.last_name)
        self._add_field(field_label(Employee, "first_name"), employee.first_name)
        self._add_field(field_label(Employee, "middle_name"), employee.middle_name)
        self._add_field(field_label(Employee, "position"), employee.position)
        if employee.academic_title is not None:
            self._add_field(
                field_label(Employee, "academic_title_id"),
                employee.academic_title.name,
            )
        if employee.department is not None:
            self._add_field(
                field_label(Employee, "department_id"), employee.department.name
            )
        membership = employee.current_membership
        if membership is not None and membership.working_group is not None:
            self._add_field(
                field_label(WorkGroupMembership, "working_group_id"),
                membership.working_group.name,
            )
            self._add_field(
                field_label(WorkGroupMembership, "start_date"),
                _date_text(membership.start_date),
            )
            self._add_field(
                field_label(WorkGroupMembership, "end_date"),
                _date_text(membership.end_date),
            )
        # История прежних участий (закрытые записи)
        history = [
            m for m in employee.workgroup_memberships
            if m is not membership and m.working_group is not None
        ]
        for past in history:
            period = f"{_date_text(past.start_date)} — {_date_text(past.end_date)}"
            self._add_field(
                f"{past.working_group.name} ({STRINGS.oshm_membership_history})",
                period,
            )
        self._add_field(field_label(Employee, "active"), _bool_text(employee.active))
        # Задачи сотрудника — только из назначенных его отделу
        self._tasks_node = (NODE_EMPLOYEE, str(employee.id))
        if employee.department_id is not None:
            self._tasks_parent = (
                NODE_DEPARTMENT,
                str(employee.department_id),
            )
        return True

    def _assigned_tasks(self, node_type: str, node_id: str) -> List[AddedTask]:
        """Назначения задач узлу (механизм распределения задач)."""
        return (
            self.session.query(AddedTask)
            .filter(
                AddedTask.node_type == node_type,
                AddedTask.node_id == node_id,
            )
            .all()
        )

    def _fill_tasks(self) -> None:
        """Заполняет таблицу задач, назначенных текущему узлу."""
        if self._tasks_node is None:
            return
        node_type, node_id = self._tasks_node
        assignments = self._assigned_tasks(node_type, node_id)
        tasks = sorted(
            (assignment.task for assignment in assignments),
            key=lambda task: task.name,
        )
        self.tasks_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            cells = [
                task.id,
                task.name,
                _date_text(task.start_date),
                _date_text(task.end_date),
            ]
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(Qt.UserRole, task.id)
                self.tasks_table.setItem(row, column, cell)

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------

    def set_tasks_editable(self, editable: bool) -> None:
        """Включает/отключает кнопки назначения задач (ГО не ведёт людей)."""
        self.task_add_btn.setEnabled(editable)
        self.task_remove_btn.setEnabled(editable)

    def _edit_clicked(self) -> None:
        if self.current_node is not None:
            self.edit_requested.emit(self.current_node)

    def _show_statistics(self) -> None:
        """Запрашивает статистику по текущему элементу (обрабатывает приложение)."""
        if self.current_node is not None:
            self.statistics_requested.emit(self.current_node)

    def _add_tasks(self) -> None:
        """Назначает узлу задачи, выбранные в диалоге выбора.

        Доступны только задачи, назначенные старшему элементу
        (филиалу — из пула региона и т.д.), как во вкладке «Задачи».
        """
        if self._tasks_node is None:
            return
        node_type, node_id = self._tasks_node
        assigned_ids = {a.task_id for a in self._assigned_tasks(node_type, node_id)}
        allowed_ids: Optional[set] = None
        if self._tasks_parent is not None:
            parent_type, parent_id = self._tasks_parent
            allowed_ids = {
                a.task_id for a in self._assigned_tasks(parent_type, parent_id)
            }
        dialog = TaskPickerDialog(
            self.session, excluded_ids=assigned_ids, allowed_ids=allowed_ids,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            for task in dialog.selected_tasks():
                if task.id in assigned_ids:
                    continue
                self.session.add(
                    AddedTask(task_id=task.id, node_type=node_type, node_id=node_id)
                )
            self.session.commit()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка назначения задачи")
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
            self.session.rollback()
            return
        self._fill_tasks()

    def _remove_tasks(self) -> None:
        """Снимает с узла назначения, выбранные в таблице задач."""
        if self._tasks_node is None:
            return
        node_type, node_id = self._tasks_node
        selected_ids = {
            self.tasks_table.item(index.row(), 0).data(Qt.UserRole)
            for index in self.tasks_table.selectionModel().selectedRows()
        }
        if not selected_ids:
            return
        try:
            for assignment in self._assigned_tasks(node_type, node_id):
                if assignment.task_id in selected_ids:
                    self.session.delete(assignment)
            self.session.commit()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка снятия назначения задачи")
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
            self.session.rollback()
            return
        self._fill_tasks()
