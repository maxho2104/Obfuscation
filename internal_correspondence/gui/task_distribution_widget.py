"""Вкладка распределения научных задач по иерархии организации."""

from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTableView,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.importexport.task_export import (
    TaskExportError,
    default_region_filename,
    export_regions,
    write_region_file,
)
from internal_correspondence.importexport.task_import import import_scientific_tasks
from internal_correspondence.orm.models import ScientificTask, TerritorialUnit
from internal_correspondence.services.reference_service import (
    ScientificTaskError,
    ScientificTaskService,
)
from internal_correspondence.services.task_distribution_service import (
    NODE_ORGANIZATION,
    NODE_REGION,
    DistributionNode,
    FinancialPeriod,
    NodeKey,
    TaskDistributionError,
    TaskDistributionService,
)
from internal_correspondence.gui.task_dialog import ScientificTaskDialog
from internal_correspondence.gui.task_table_model import (
    TASK_MIME_TYPE,
    TaskTableModel,
)
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("task_distribution_widget")

KEY_ROLE = Qt.UserRole
ASSIGNABLE_ROLE = Qt.UserRole + 1
INACTIVE_COLOR = QColor("#808080")


class _TaskTableView(QTableView):
    """Таблица задач, принимающая перетаскивание из другой таблицы."""

    dropped = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)

    def _accepts_drag(self, event) -> bool:
        """Проверяет, что перетаскивание пришло из соседней таблицы задач."""
        source = event.source()
        if source is None or source is self:
            return False
        return event.mimeData().hasFormat(TASK_MIME_TYPE)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._accepts_drag(event):
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._accepts_drag(event):
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if not self._accepts_drag(event):
            event.ignore()
            return
        source = event.source()
        model = source.model()
        selection = source.selectionModel()
        if selection is None or not hasattr(model, "tasks_at"):
            event.ignore()
            return
        rows = sorted({index.row() for index in selection.selectedRows()})
        tasks = model.tasks_at(rows)
        if not tasks:
            event.ignore()
            return
        self.dropped.emit(tasks)
        event.setDropAction(Qt.MoveAction)
        event.accept()


class TaskDistributionWidget(QWidget):
    """Дерево организации, задачи родителя и задачи выбранного узла."""

    def __init__(
        self,
        session,
        role: Role | str,
        branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.role = role
        self.branch_id = branch_id
        self.service = TaskDistributionService(session, role, branch_id)
        self.is_head_office = self.service.is_head_office

        self.current_period: Optional[FinancialPeriod] = None
        self.current_node: Optional[DistributionNode] = None
        self.selected_assignable = True

        self._build_ui()
        self._reload_periods()
        self._populate_tree()
        self._reload_all()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        top = QHBoxLayout()
        top.addWidget(QLabel(STRINGS.task_period))
        self.period_combo = QComboBox()
        self.period_combo.setMinimumWidth(180)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        top.addWidget(self.period_combo)
        top.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(240)
        self.tree.setIndentation(16)
        self.tree.currentItemChanged.connect(self._on_tree_current_changed)

        self.middle_label = QLabel(STRINGS.task_middle_title)
        self.middle_search = QLineEdit()
        self.middle_search.setPlaceholderText(STRINGS.task_search)
        self.middle_search.setClearButtonEnabled(True)
        self.middle_model = TaskTableModel(self)
        self.middle_view = _TaskTableView()
        self.middle_view.setModel(self.middle_model)
        self.middle_view.dropped.connect(self._on_middle_drop)
        self.middle_search.textChanged.connect(self.middle_model.set_search)
        self.middle_view.selectionModel().selectionChanged.connect(self._update_buttons)
        self.middle_view.doubleClicked.connect(self._edit_current_middle)
        self.middle_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.middle_view.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.middle_view, pos)
        )
        self._configure_table(self.middle_view)

        middle_panel = QWidget()
        middle_panel.setMinimumWidth(260)
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.addWidget(self.middle_label)
        middle_layout.addWidget(self.middle_search)
        middle_layout.addWidget(self.middle_view, 1)

        self.right_label = QLabel(STRINGS.task_right_title)
        self.right_search = QLineEdit()
        self.right_search.setPlaceholderText(STRINGS.task_search)
        self.right_search.setClearButtonEnabled(True)
        self.right_model = TaskTableModel(self)
        self.right_view = _TaskTableView()
        self.right_view.setModel(self.right_model)
        self.right_view.dropped.connect(self._on_right_drop)
        self.right_search.textChanged.connect(self.right_model.set_search)
        self.right_view.selectionModel().selectionChanged.connect(self._update_buttons)
        self.right_view.doubleClicked.connect(self._edit_current_right)
        self.right_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.right_view.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.right_view, pos)
        )
        self._configure_table(self.right_view)

        right_panel = QWidget()
        right_panel.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.right_label)
        right_layout.addWidget(self.right_search)
        right_layout.addWidget(self.right_view, 1)

        self.assign_button = QToolButton()
        self.assign_button.setText(">>>")
        self.assign_button.setFixedWidth(48)
        self.assign_button.setMinimumHeight(48)
        self.assign_button.setToolTip(STRINGS.task_assign)
        self.assign_button.clicked.connect(self._assign_selected)

        self.unassign_button = QToolButton()
        self.unassign_button.setText("<<<")
        self.unassign_button.setFixedWidth(48)
        self.unassign_button.setMinimumHeight(48)
        self.unassign_button.setToolTip(STRINGS.task_unassign)
        self.unassign_button.clicked.connect(self._unassign_selected)

        buttons = QWidget()
        buttons.setFixedWidth(52)
        buttons.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        buttons_layout = QVBoxLayout(buttons)
        buttons_layout.setContentsMargins(2, 0, 2, 0)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.assign_button)
        buttons_layout.addWidget(self.unassign_button)
        buttons_layout.addStretch(1)
        self.buttons_panel = buttons

        # Средняя таблица и кнопки — единая панель: при изменении ширины
        # средней колонки кнопки остаются прижатыми к правой таблице,
        # а не «отъезжают» от неё.
        center_panel = QWidget()
        center_layout = QHBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)
        center_layout.addWidget(middle_panel, 1)
        center_layout.addWidget(buttons)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(center_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setChildrenCollapsible(False)
        for index in range(self.splitter.count()):
            self.splitter.setCollapsible(index, False)
        self.splitter.setSizes([280, 432, 380])

        self.create_button = QToolButton()
        self.create_button.setText(STRINGS.task_create)
        self.create_button.clicked.connect(self._create_task)

        self.import_button = QToolButton()
        self.import_button.setText(STRINGS.task_import)
        self.import_button.clicked.connect(self._import_tasks)

        bottom = QHBoxLayout()
        bottom.addWidget(self.create_button)
        bottom.addWidget(self.import_button)
        bottom.addStretch(1)

        self.export_button = QToolButton()
        self.export_button.setText(STRINGS.task_export)
        self.export_button.clicked.connect(self._export_tasks)
        self.export_button.setVisible(self.is_head_office)
        bottom.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.splitter, 1)
        layout.addLayout(bottom)

    @staticmethod
    def _configure_table(view: QTableView) -> None:
        header = view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        for column, width in enumerate(
            (90, 260, 110, 100, 100, 120, 120, 200)
        ):
            view.setColumnWidth(column, width)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        view.sortByColumn(0, Qt.AscendingOrder)

    # ------------------------------------------------------------------
    # Дерево и периоды
    # ------------------------------------------------------------------

    def _populate_tree(self) -> None:
        current_key = self.current_key()
        self.tree.blockSignals(True)
        self.tree.clear()
        for root in self.service.build_tree(self.current_period):
            self.tree.addTopLevelItem(self._make_item(root))
        self.tree.blockSignals(False)
        if current_key is not None:
            self._select_key(current_key)
        elif self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
            self.tree.expandToDepth(1)

    def _make_item(self, node: DistributionNode) -> QTreeWidgetItem:
        label = STRINGS.task_organization if node.node_type == NODE_ORGANIZATION else node.label
        item = QTreeWidgetItem([label])
        item.setData(0, KEY_ROLE, node.key)
        item.setData(0, ASSIGNABLE_ROLE, node.assignable)
        item.setToolTip(0, label)
        if not node.active:
            item.setForeground(0, QBrush(INACTIVE_COLOR))
        if not node.assignable:
            item.setToolTip(0, STRINGS.task_group_employee_hint)
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    def _select_key(self, key: NodeKey) -> None:
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, KEY_ROLE) == key:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                return
            iterator += 1

    def current_key(self) -> Optional[NodeKey]:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, KEY_ROLE)

    def _reload_periods(self) -> None:
        previous = self.current_period.year if self.current_period else None
        periods = self.service.available_periods()
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for period in periods:
            self.period_combo.addItem(period.title, period)
        if previous is not None:
            index = self.period_combo.findData(FinancialPeriod(previous))
            if index >= 0:
                self.period_combo.setCurrentIndex(index)
        if self.period_combo.currentIndex() < 0 and periods:
            self.period_combo.setCurrentIndex(0)
        self.period_combo.blockSignals(False)
        self.current_period = self.period_combo.currentData()

    def _on_period_changed(self, _index: int) -> None:
        self.current_period = self.period_combo.currentData()
        # Состав рабочих групп зависит от периода, поэтому дерево
        # перестраивается до обновления таблиц.
        self._populate_tree()
        self._reload_all()

    def _on_tree_current_changed(
        self, current: Optional[QTreeWidgetItem], _previous: Optional[QTreeWidgetItem]
    ) -> None:
        if current is None:
            self.current_node = None
            return
        key = current.data(0, KEY_ROLE)
        self.selected_assignable = bool(current.data(0, ASSIGNABLE_ROLE))
        self.current_node = self.service.node(key)
        self._refresh_tables()

    def _reload_all(self) -> None:
        if self.current_period is None:
            return
        self.service.tasks(self.current_period)
        if self.current_node is None:
            if self.tree.topLevelItemCount():
                self.tree.setCurrentItem(self.tree.topLevelItem(0))
            return
        self._refresh_tables()

    def refresh_all(self) -> None:
        """Полностью перечитывает дерево, периоды и таблицы."""
        self.service = TaskDistributionService(
            self.session, self.role, self.branch_id
        )
        self._reload_periods()
        self._populate_tree()
        self._reload_all()

    def _refresh_after_data_change(self) -> None:
        """Обновляет периоды, дерево и таблицы после правки задач."""
        self._reload_periods()
        self._populate_tree()
        self._reload_all()

    # ------------------------------------------------------------------
    # Таблицы
    # ------------------------------------------------------------------

    def _refresh_tables(self) -> None:
        node = self.current_node
        period = self.current_period
        if node is None or period is None:
            return

        parent_key = self.service.parent_key(node.key)
        if parent_key is None:
            middle_owner = node
            middle_tasks = self.service.tasks_for_node(node, period)
            right_tasks: List[ScientificTask] = []
            self.right_view.setVisible(False)
            self.right_label.setVisible(False)
            self.right_search.setVisible(False)
            self.assign_button.setVisible(False)
            self.unassign_button.setVisible(False)
            self.middle_label.setText(
                f"{STRINGS.task_middle_title} — {self._node_title(node)}"
            )
        else:
            middle_owner = self.service.node(parent_key) or node
            middle_tasks = self.service.tasks_for_parent(node, period)
            right_tasks = self.service.tasks_for_node(node, period)
            self.right_view.setVisible(True)
            self.right_label.setVisible(True)
            self.right_search.setVisible(True)
            self.assign_button.setVisible(True)
            self.unassign_button.setVisible(True)
            self.middle_label.setText(
                f"{STRINGS.task_middle_title} — {self._node_title(middle_owner)}"
            )
            self.right_label.setText(
                f"{STRINGS.task_right_title} — {self._node_title(node)}"
            )

        middle_undistributed = {
            task.id
            for task in middle_tasks
            if self.service.is_undistributed(task, middle_owner)
        }
        right_undistributed = {
            task.id
            for task in right_tasks
            if self.service.is_undistributed(task, node)
        }
        self.middle_model.set_tasks(middle_tasks, middle_undistributed)
        self.right_model.set_tasks(right_tasks, right_undistributed)
        self.middle_view.clearSelection()
        self.right_view.clearSelection()
        self._update_buttons()

    @staticmethod
    def _node_title(node: DistributionNode) -> str:
        if node.node_type == NODE_ORGANIZATION:
            return STRINGS.task_organization
        return node.label

    def _selected_tasks(self, view: QTableView) -> List[ScientificTask]:
        selection = view.selectionModel()
        if selection is None:
            return []
        rows = sorted({index.row() for index in selection.selectedRows()})
        return view.model().tasks_at(rows)

    def _update_buttons(self, *_args) -> None:
        node = self.current_node
        can_assign = False
        can_unassign = False
        if node is not None and self.selected_assignable:
            can_assign = bool(self._selected_tasks(self.middle_view)) and self.service.can_assign(node)[0]
            can_unassign = bool(self._selected_tasks(self.right_view)) and self.service.can_unassign(node)[0]
        self.assign_button.setEnabled(can_assign)
        self.unassign_button.setEnabled(can_unassign)

    # ------------------------------------------------------------------
    # Назначение и снятие
    # ------------------------------------------------------------------

    def _assign_selected(self) -> None:
        self._assign_tasks(self._selected_tasks(self.middle_view))

    def _on_right_drop(self, tasks: list) -> None:
        self._assign_tasks(tasks)

    def _assign_tasks(self, tasks: Sequence[ScientificTask]) -> None:
        node = self.current_node
        if node is None or not tasks:
            return
        try:
            self.service.assign(tasks, node)
            self.session.commit()
        except (TaskDistributionError, Exception) as error:  # noqa: B014
            self.session.rollback()
            QMessageBox.warning(
                self,
                STRINGS.title_error,
                STRINGS.task_assign_error.format(error=error),
            )
            return
        self._reload_all()

    def _unassign_selected(self) -> None:
        self._unassign_tasks(self._selected_tasks(self.right_view))

    def _on_middle_drop(self, tasks: list) -> None:
        self._unassign_tasks(tasks)

    def _unassign_tasks(self, tasks: Sequence[ScientificTask]) -> None:
        node = self.current_node
        if node is None or not tasks:
            return
        if len(tasks) >= 5:
            answer = QMessageBox.question(
                self,
                STRINGS.title_confirm,
                STRINGS.task_unassign_confirm.format(
                    count=len(tasks), node=self._node_title(node)
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        try:
            self.service.unassign(tasks, node)
            self.session.commit()
        except (TaskDistributionError, Exception) as error:  # noqa: B014
            self.session.rollback()
            QMessageBox.warning(
                self,
                STRINGS.title_error,
                STRINGS.task_unassign_error.format(error=error),
            )
            return
        self._reload_all()

    def _assign_chain(self, task: ScientificTask, node: DistributionNode) -> None:
        """Назначает задачу узлу и всем предкам сверху вниз."""
        chain = list(reversed(self.service.ancestors(node.key))) + [node.key]
        for key in chain:
            if key[0] == NODE_ORGANIZATION:
                continue
            if not self.is_head_office and key[0] == NODE_REGION:
                continue
            target = self.service.node(key)
            if target is None or not target.assignable or not target.active:
                continue
            self.service.assign([task], target)

    # ------------------------------------------------------------------
    # Создание, редактирование, удаление
    # ------------------------------------------------------------------

    def _create_task(self) -> None:
        dialog = ScientificTaskDialog(parent=self)
        if dialog.exec_() != dialog.Accepted:
            return
        service = ScientificTaskService(self.session)
        try:
            task = service.create_task(dialog.get_data())
            self.session.commit()
        except ScientificTaskError as error:
            self.session.rollback()
            QMessageBox.warning(self, STRINGS.title_error, str(error))
            return
        node = self.current_node
        if node is not None and node.node_type != NODE_ORGANIZATION:
            try:
                self._assign_chain(task, node)
                self.session.commit()
            except (TaskDistributionError, Exception) as error:  # noqa: B014
                self.session.rollback()
                QMessageBox.warning(
                    self,
                    STRINGS.title_error,
                    STRINGS.task_assign_error.format(error=error),
                )
        self._refresh_after_data_change()

    def _edit_current_middle(self, _index) -> None:
        self._edit_selected(self.middle_view)

    def _edit_current_right(self, _index) -> None:
        self._edit_selected(self.right_view)

    def _edit_selected(self, view: QTableView) -> None:
        tasks = self._selected_tasks(view)
        if not tasks:
            return
        self._edit_task(tasks[0])

    def _edit_task(self, task: ScientificTask) -> None:
        dialog = ScientificTaskDialog(task, self)
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            ScientificTaskService(self.session).update_task(task, dialog.get_data())
            self.session.commit()
        except ScientificTaskError as error:
            self.session.rollback()
            QMessageBox.warning(self, STRINGS.title_error, str(error))
            return
        self._refresh_after_data_change()

    def _delete_task(self, task: ScientificTask) -> None:
        if not self.is_head_office:
            return
        answer = QMessageBox.question(
            self,
            STRINGS.title_confirm,
            STRINGS.task_delete_confirm.format(name=task.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            ScientificTaskService(self.session).delete_task(task)
            self.session.commit()
        except (ScientificTaskError, Exception) as error:  # noqa: B014
            self.session.rollback()
            QMessageBox.warning(self, STRINGS.title_error, str(error))
            return
        self._refresh_after_data_change()

    def _show_context_menu(self, view: QTableView, pos) -> None:
        tasks = self._selected_tasks(view)
        if not tasks:
            return
        task = tasks[0]
        menu = QMenu(self)
        edit_action = menu.addAction(STRINGS.task_edit)
        edit_action.triggered.connect(lambda: self._edit_task(task))
        if self.is_head_office:
            delete_action = menu.addAction(STRINGS.task_delete)
            delete_action.triggered.connect(lambda: self._delete_task(task))
        menu.exec_(view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Импорт и выгрузка
    # ------------------------------------------------------------------

    def _import_tasks(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, STRINGS.task_import_choose_file, "", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            result = import_scientific_tasks(self.session, Path(path))
            self.session.commit()
        except Exception as error:  # pylint: disable=broad-except
            self.session.rollback()
            QMessageBox.warning(self, STRINGS.title_error, str(error))
            return

        tasks = [
            self.session.get(ScientificTask, task_id)
            for task_id in result.task_ids
        ]
        tasks = [task for task in tasks if task is not None]
        try:
            if tasks:
                if self.is_head_office:
                    node = self.current_node
                    if node is not None and node.node_type != NODE_ORGANIZATION:
                        for task in tasks:
                            self._assign_chain(task, node)
                else:
                    self.service.add_region_assignments(tasks)
                self.session.commit()
        except (TaskDistributionError, Exception) as error:  # noqa: B014
            self.session.rollback()
            QMessageBox.warning(
                self,
                STRINGS.title_error,
                STRINGS.task_assign_error.format(error=error),
            )

        message = STRINGS.task_import_done.format(
            created=result.created,
            updated=result.updated,
            skipped=result.skipped,
        )
        if result.errors:
            message += "\n\n" + STRINGS.task_import_errors + "\n" + "\n".join(
                result.errors[:20]
            )
        QMessageBox.information(self, STRINGS.title_import, message)
        self._refresh_after_data_change()

    def _export_tasks(self) -> None:
        regions = list(
            self.session.query(TerritorialUnit)
            .order_by(TerritorialUnit.name)
            .all()
        )
        if not regions:
            QMessageBox.warning(
                self, STRINGS.title_error, STRINGS.task_export_no_regions
            )
            return
        labels = [STRINGS.task_export_all_regions] + [
            f"{region.id} — {region.name}" for region in regions
        ]
        choice, accepted = QInputDialog.getItem(
            self,
            STRINGS.task_export_title,
            STRINGS.task_export_region,
            labels,
            0,
            False,
        )
        if not accepted:
            return

        period = self.current_period
        if period is None:
            return

        if choice == STRINGS.task_export_all_regions:
            directory = QFileDialog.getExistingDirectory(
                self, STRINGS.task_export_choose_dir
            )
            if not directory:
                return
            try:
                written = export_regions(
                    self.session, period, regions, Path(directory)
                )
            except (TaskExportError, Exception) as error:  # noqa: B014
                QMessageBox.warning(
                    self,
                    STRINGS.title_error,
                    STRINGS.task_export_error.format(error=error),
                )
                return
            if not written:
                QMessageBox.warning(
                    self, STRINGS.title_error, STRINGS.task_export_empty
                )
                return
            QMessageBox.information(
                self,
                STRINGS.title_export,
                STRINGS.task_export_done.format(
                    count=len(written), directory=directory
                ),
            )
            return

        index = labels.index(choice) - 1
        region = regions[index]
        default_path = Path.home() / default_region_filename(region, period)
        path, _ = QFileDialog.getSaveFileName(
            self,
            STRINGS.task_export_choose_file,
            str(default_path),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            write_region_file(self.session, region, period, Path(path))
        except (TaskExportError, Exception) as error:  # noqa: B014
            QMessageBox.warning(
                self,
                STRINGS.title_error,
                STRINGS.task_export_error.format(error=error),
            )
            return
        QMessageBox.information(
            self,
            STRINGS.title_export,
            STRINGS.task_export_done.format(count=1, directory=str(Path(path).parent)),
        )

    # ------------------------------------------------------------------
    # Тема
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        """Перерисовывает таблицы после смены темы."""
        self.middle_model.refresh_theme()
        self.right_model.refresh_theme()
