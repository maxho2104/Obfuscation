"""Диалог организационно-штатной структуры (ОШС).

Форма строится от элемента, от которого открыто приложение: для филиала —
от его собственного узла, для головного офиса — от узла «Головной офис»
со всеми филиалами внутри (режим просмотра). Два дерева одно под другим:
штатная структура (отделы и сотрудники) и рабочие группы с их составом.
По двойному щелчку на элементе справа выдвигается панель с его данными
и назначенными задачами (для сотрудника).
Реализованы множественный выбор, кнопки «+»/«−», контекстное меню,
drag&drop переподчинение сотрудников и подсветка неактивных элементов.
"""

from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from PyQt5.QtCore import QDate, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.oshm_details_panel import ElementDetailsPanel
from internal_correspondence.orm.labels import (
    entity_label,
    field_form_label,
    field_label,
)
from internal_correspondence.orm.models import Branch, Department, Employee, WorkingGroup
from internal_correspondence.services.reference_service import (
    DepartmentService,
    EmployeeService,
    WorkingGroupService,
)
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("oshm_dialog")

# Цвет неактивных (скрытых) элементов дерева
INACTIVE_COLOR = QColor(150, 150, 150)

# Полезная нагрузка узла дерева: (тип узла, строковый идентификатор)
NodeRef = Tuple[str, str]

# Тип корневого узла головного офиса
NODE_HEAD_OFFICE = "head_office"


class OSHMTreeWidget(QTreeWidget):
    """Дерево ОШС с drag&drop переподчинением сотрудников.

    Стандартное перемещение узлов отключено: перенос обрабатывается
    диалогом через сигнал ``nodes_dropped`` (перетаскиваемые узлы и цель).
    """

    nodes_dropped = pyqtSignal(list, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.IgnoreAction)
        self.setHeaderLabels([STRINGS.oshm_col_element])

    def dropEvent(self, event) -> None:
        """Перехватывает перенос: передаёт узлы и цель диалогу."""
        target_item = self.itemAt(event.pos())
        payloads = [item.data(0, Qt.UserRole) for item in self.selectedItems()]
        target = target_item.data(0, Qt.UserRole) if target_item is not None else None
        if payloads:
            self.nodes_dropped.emit(payloads, target)
        event.ignore()


class OSHMDialog(QDialog):
    """Диалог просмотра и редактирования ОШС.

    Деревья строятся от элемента, от которого открыто приложение:
    филиал видит и редактирует только свою структуру, головной офис
    видит все филиалы и редактирует структуру (отделы, рабочие группы),
    но не записи о сотрудниках.
    """

    def __init__(
        self,
        session,
        branch_id: Optional[str] = None,
        role: str = Role.BRANCH.value,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.role = role
        self.is_head_office = role == Role.HEAD_OFFICE.value
        # Головной офис редактирует структуру (отделы, рабочие группы),
        # но не записи о людях — сотрудников ведёт сам филиал
        self.can_edit_people = not self.is_head_office
        self.branch_id = branch_id
        self._active_tree: Optional[OSHMTreeWidget] = None
        self.setWindowTitle(STRINGS.title_oshm)
        self.setMinimumSize(700, 600)
        self._setup_ui()
        self._load_data()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Два дерева одно под другим
        splitter = QSplitter(Qt.Vertical)

        structure_widget = QWidget()
        structure_layout = QVBoxLayout(structure_widget)
        structure_layout.setContentsMargins(0, 0, 0, 0)
        structure_layout.addWidget(QLabel(STRINGS.oshm_tree_structure))
        self.tree_structure = self._create_tree()
        structure_layout.addWidget(self.tree_structure)
        splitter.addWidget(structure_widget)

        workgroups_widget = QWidget()
        workgroups_layout = QVBoxLayout(workgroups_widget)
        workgroups_layout.setContentsMargins(0, 0, 0, 0)
        workgroups_layout.addWidget(QLabel(STRINGS.oshm_tree_workgroups))
        self.tree_workgroups = self._create_tree()
        workgroups_layout.addWidget(self.tree_workgroups)
        splitter.addWidget(workgroups_widget)

        splitter.setSizes([350, 350])

        # Справа — выдвижная панель сведений об элементе (двойной щелчок)
        self.details_panel = ElementDetailsPanel(self.session, self)
        self.details_panel.hide_requested.connect(self._hide_details)
        self.details_panel.edit_requested.connect(self._edit_node)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(splitter)
        main_splitter.addWidget(self.details_panel)
        main_splitter.setSizes([700, 340])
        layout.addWidget(main_splitter)
        self.details_panel.hide()

        # Кнопки добавления и скрытия
        buttons_row = QHBoxLayout()
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip(STRINGS.button_add)
        self.add_btn.clicked.connect(self._add_clicked)
        self.toggle_btn = QPushButton("−")
        self.toggle_btn.setToolTip(STRINGS.action_toggle_hide)
        self.toggle_btn.clicked.connect(self._toggle_selected)
        buttons_row.addWidget(self.add_btn)
        buttons_row.addWidget(self.toggle_btn)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _create_tree(self) -> OSHMTreeWidget:
        """Создаёт настроенное дерево ОШС."""
        tree = OSHMTreeWidget()
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._show_context_menu)
        tree.itemDoubleClicked.connect(
            lambda item, _column, tree=tree: self._show_details(item, tree)
        )
        tree.itemSelectionChanged.connect(lambda tree=tree: self._activate_tree(tree))
        tree.nodes_dropped.connect(
            lambda payloads, target, tree=tree: self._on_nodes_dropped(
                tree, payloads, target
            )
        )
        return tree

    def _activate_tree(self, tree: OSHMTreeWidget) -> None:
        """Запоминает дерево, с которым работает оператор."""
        self._active_tree = tree

    # ------------------------------------------------------------------
    # Панель сведений об элементе
    # ------------------------------------------------------------------

    def _show_details(self, item: QTreeWidgetItem, tree: OSHMTreeWidget) -> None:
        """Показывает справа панель сведений об элементе (двойной щелчок)."""
        payload = item.data(0, Qt.UserRole)
        if payload is None:
            return
        self._activate_tree(tree)
        tree.setCurrentItem(item)
        if self.details_panel.show_node(payload, can_edit_people=self.can_edit_people):
            self.details_panel.show()

    def _hide_details(self) -> None:
        """Скрывает панель сведений (кнопка «Скрыть»)."""
        self.details_panel.hide()

    def _refresh_details_panel(self) -> None:
        """Обновляет панель после перестройки деревьев.

        Если элемент был удалён, панель скрывается.
        """
        if self.details_panel.isHidden():
            return
        node = self.details_panel.current_node
        if node is None:
            return
        if not self.details_panel.show_node(node, can_edit_people=self.can_edit_people):
            self.details_panel.hide()

    # ------------------------------------------------------------------
    # Загрузка данных
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        """Перестраивает оба дерева от корня текущей роли."""
        self.tree_structure.clear()
        self.tree_workgroups.clear()

        if self.is_head_office:
            root_s = self._add_node(
                self.tree_structure, None, NODE_HEAD_OFFICE, "",
                STRINGS.role_head_office,
            )
            root_w = self._add_node(
                self.tree_workgroups, None, NODE_HEAD_OFFICE, "",
                STRINGS.role_head_office,
            )
            branches = self.session.query(Branch).order_by(Branch.name).all()
            for branch in branches:
                self._add_branch_nodes(root_s, root_w, branch)
        else:
            branch = (
                self.session.get(Branch, self.branch_id) if self.branch_id else None
            )
            if branch is None:
                return
            root_s = self._add_node(
                self.tree_structure, None, "branch", branch.id, branch.name
            )
            root_w = self._add_node(
                self.tree_workgroups, None, "branch", branch.id, branch.name
            )
            self._fill_branch(root_s, root_w, branch.id)
        self._refresh_details_panel()

    def _add_branch_nodes(
        self,
        structure_parent: QTreeWidgetItem,
        workgroups_parent: QTreeWidgetItem,
        branch: Branch,
    ) -> None:
        """Добавляет узел филиала и его структуру в оба дерева."""
        node_s = self._add_node(
            self.tree_structure, structure_parent, "branch", branch.id, branch.name
        )
        node_w = self._add_node(
            self.tree_workgroups, workgroups_parent, "branch", branch.id, branch.name
        )
        self._fill_branch(node_s, node_w, branch.id)

    def _fill_branch(
        self,
        structure_parent: QTreeWidgetItem,
        workgroups_parent: QTreeWidgetItem,
        branch_id: str,
    ) -> None:
        """Заполняет оба дерева содержимым филиала."""
        departments = (
            self.session.query(Department)
            .filter(Department.branch_id == branch_id)
            .order_by(Department.name)
            .all()
        )
        for dept in departments:
            # Дерево штатной структуры: отдел → сотрудники
            dept_item = self._add_node(
                self.tree_structure, structure_parent, "department",
                dept.id, dept.name, active=dept.active,
            )
            employees = (
                self.session.query(Employee)
                .filter(Employee.department_id == dept.id)
                .order_by(Employee.last_name)
                .all()
            )
            for emp in employees:
                self._add_employee_node(dept_item, emp, dept.active)

            # Дерево рабочих групп: отдел → группа → состав группы
            wg_dept_item = self._add_node(
                self.tree_workgroups, workgroups_parent, "department",
                dept.id, dept.name, active=dept.active,
            )
            workgroups = (
                self.session.query(WorkingGroup)
                .filter(WorkingGroup.department_id == dept.id)
                .order_by(WorkingGroup.name)
                .all()
            )
            for wg in workgroups:
                wg_item = self._add_node(
                    self.tree_workgroups, wg_dept_item, "workgroup",
                    wg.id, wg.name, active=wg.active,
                )
                members = (
                    self.session.query(Employee)
                    .filter(Employee.working_group_id == wg.id)
                    .order_by(Employee.last_name)
                    .all()
                )
                for emp in members:
                    self._add_employee_node(wg_item, emp, dept.active)

    def _add_node(
        self,
        tree: OSHMTreeWidget,
        parent_item: Optional[QTreeWidgetItem],
        node_type: str,
        node_id,
        text: str,
        active: bool = True,
    ) -> QTreeWidgetItem:
        """Добавляет узел дерева с полезной нагрузкой и подсветкой неактивных."""
        if parent_item is None:
            item = QTreeWidgetItem(tree, [text])
            item.setExpanded(True)  # корень всегда развёрнут, остальное «выпадает»
        else:
            item = QTreeWidgetItem(parent_item, [text])
        item.setData(0, Qt.UserRole, (node_type, str(node_id)))
        flags = item.flags()
        if node_type == "employee" and self.can_edit_people:
            flags |= Qt.ItemIsDragEnabled
            flags &= ~Qt.ItemIsDropEnabled
        elif node_type in ("department", "workgroup"):
            flags &= ~Qt.ItemIsDragEnabled
            flags |= Qt.ItemIsDropEnabled
        else:
            flags &= ~Qt.ItemIsDragEnabled & ~Qt.ItemIsDropEnabled
        item.setFlags(flags)
        if not active:
            item.setForeground(0, QBrush(INACTIVE_COLOR))
        return item

    def _add_employee_node(
        self, parent_item: QTreeWidgetItem, emp: Employee, dept_active: bool
    ) -> QTreeWidgetItem:
        """Добавляет узел сотрудника; сотрудник сокращённого отдела — неактивен."""
        return self._add_node(
            self._tree_of(parent_item),
            parent_item,
            "employee",
            emp.id,
            emp.display_name(),
            active=emp.active and dept_active,
        )

    @staticmethod
    def _tree_of(item: QTreeWidgetItem) -> OSHMTreeWidget:
        """Возвращает дерево, которому принадлежит узел."""
        return item.treeWidget()

    # ------------------------------------------------------------------
    # Выбор и контекстное меню
    # ------------------------------------------------------------------

    def _selected_nodes(self) -> List[NodeRef]:
        """Возвращает полезную нагрузку выбранных узлов активного дерева."""
        if self._active_tree is None:
            return []
        return [
            item.data(0, Qt.UserRole)
            for item in self._active_tree.selectedItems()
        ]

    def _current_node(self) -> Optional[NodeRef]:
        """Возвращает текущий узел активного дерева."""
        if self._active_tree is None:
            return None
        item = self._active_tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def _show_context_menu(self, position) -> None:
        tree = self._active_tree
        if tree is None:
            return
        item = tree.itemAt(position)
        if item is None:
            return
        tree.setCurrentItem(item)
        selected = tree.selectedItems()
        # Головной офис не редактирует людей
        editable_types = ("department", "workgroup") + (
            ("employee",) if self.can_edit_people else ()
        )

        menu = QMenu()
        if len(selected) > 1:
            # Множественный выбор: групповые операции над редактируемыми узлами
            if not any(
                node.data(0, Qt.UserRole)[0] in editable_types for node in selected
            ):
                return
            toggle = menu.addAction(STRINGS.action_toggle_hide)
            toggle.triggered.connect(self._toggle_selected)
            delete = menu.addAction(STRINGS.button_delete)
            delete.triggered.connect(self._delete_selected)
        else:
            node_type, _node_id = item.data(0, Qt.UserRole)
            if node_type == "branch":
                add_dept = menu.addAction(
                    STRINGS.action_add_entity.format(
                        entity=entity_label(Department).lower()
                    )
                )
                add_dept.triggered.connect(self._add_department)
            elif node_type == "department":
                add_wg = menu.addAction(
                    STRINGS.action_add_entity.format(
                        entity=entity_label(WorkingGroup).lower()
                    )
                )
                add_wg.triggered.connect(self._add_workgroup)
                if self.can_edit_people:
                    add_emp = menu.addAction(
                        STRINGS.action_add_entity.format(
                            entity=entity_label(Employee).lower()
                        )
                    )
                    add_emp.triggered.connect(self._add_employee)
                menu.addSeparator()
                edit = menu.addAction(STRINGS.button_edit)
                edit.triggered.connect(self._edit_item)
            elif node_type in editable_types:
                edit = menu.addAction(STRINGS.button_edit)
                edit.triggered.connect(self._edit_item)
            if node_type in editable_types:
                toggle = menu.addAction(STRINGS.action_toggle_hide)
                toggle.triggered.connect(self._toggle_selected)
                delete = menu.addAction(STRINGS.button_delete)
                delete.triggered.connect(self._delete_selected)
            if menu.isEmpty():
                return
        menu.exec_(tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Добавление
    # ------------------------------------------------------------------

    def _add_clicked(self) -> None:
        """Обрабатывает кнопку «+» с учётом выбранного узла."""
        node = self._current_node()
        if node is None or node[0] in ("branch", NODE_HEAD_OFFICE):
            self._add_department()
            return
        if node[0] == "department":
            menu = QMenu(self)
            add_wg = menu.addAction(
                STRINGS.action_add_entity.format(
                    entity=entity_label(WorkingGroup).lower()
                )
            )
            add_emp = None
            if self.can_edit_people:
                add_emp = menu.addAction(
                    STRINGS.action_add_entity.format(entity=entity_label(Employee).lower())
                )
            action = menu.exec_(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))
            if action is add_wg:
                self._add_workgroup()
            elif add_emp is not None and action is add_emp:
                self._add_employee()

    def _branch_id_for_add(self) -> Optional[str]:
        """Филиал для нового отдела: выбранный узел филиала либо свой (роль филиала)."""
        node = self._current_node()
        if node is not None and node[0] == "branch":
            return node[1]
        if not self.is_head_office:
            return self.branch_id
        return None

    def _add_department(self) -> None:
        branch_id = self._branch_id_for_add()
        if not branch_id:
            QMessageBox.information(
                self, STRINGS.title_oshm, STRINGS.oshm_select_branch_first
            )
            return
        dialog = DepartmentEditDialog(
            self.session, branch_id=branch_id, parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            self._apply(
                lambda: DepartmentService(self.session).create(dialog.get_data()),
                "Ошибка добавления отдела",
            )

    def _add_workgroup(self) -> None:
        node = self._current_node()
        if node is None or node[0] != "department":
            return
        dialog = WorkingGroupEditDialog(
            self.session, department_id=UUID(node[1]), parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            self._apply(
                lambda: WorkingGroupService(self.session).create(dialog.get_data()),
                "Ошибка добавления рабочей группы",
            )

    def _add_employee(self) -> None:
        if not self.can_edit_people:
            return
        node = self._current_node()
        if node is None or node[0] != "department":
            return
        dialog = EmployeeEditDialog(
            self.session, department_id=UUID(node[1]), parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            self._apply(
                lambda: EmployeeService(self.session).create(dialog.get_data()),
                "Ошибка добавления сотрудника",
            )

    # ------------------------------------------------------------------
    # Изменение, скрытие, удаление, drag&drop
    # ------------------------------------------------------------------

    def _edit_item(self) -> None:
        """Открывает редактирование текущего узла активного дерева."""
        node = self._current_node()
        if node is not None:
            self._edit_node(node)

    def _edit_node(self, node: NodeRef) -> None:
        """Открывает диалог редактирования для указанного узла."""
        node_type, node_id = node
        if node_type == "employee" and not self.can_edit_people:
            return
        try:
            if node_type == "department":
                obj = self.session.get(Department, UUID(node_id))
                dialog = DepartmentEditDialog(self.session, item=obj, parent=self)
            elif node_type == "workgroup":
                obj = self.session.get(WorkingGroup, UUID(node_id))
                dialog = WorkingGroupEditDialog(self.session, item=obj, parent=self)
            elif node_type == "employee":
                obj = self.session.get(Employee, UUID(node_id))
                dialog = EmployeeEditDialog(self.session, item=obj, parent=self)
            else:
                return
            if dialog.exec_() != QDialog.Accepted:
                return
            if node_type == "department":
                DepartmentService(self.session).update(obj, dialog.get_data())
            elif node_type == "workgroup":
                WorkingGroupService(self.session).update(obj, dialog.get_data())
            else:
                EmployeeService(self.session).update(obj, dialog.get_data())
            self.session.commit()
            self._load_data()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка редактирования элемента ОШС")
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
            self.session.rollback()

    def _toggle_selected(self) -> None:
        """Переключает признак активности у всех выбранных элементов."""
        models = {
            "department": Department,
            "workgroup": WorkingGroup,
            "employee": Employee,
        }
        changed = False
        for node_type, node_id in self._selected_nodes():
            if node_type == "employee" and not self.can_edit_people:
                continue
            model_class = models.get(node_type)
            if model_class is None:
                continue
            obj = self.session.get(model_class, UUID(node_id))
            if obj is not None:
                obj.active = not obj.active
                changed = True
        if changed:
            self.session.commit()
            self._load_data()

    def _delete_selected(self) -> None:
        """Удаляет выбранные элементы после подтверждения."""
        nodes = [
            node
            for node in self._selected_nodes()
            if node[0] in ("department", "workgroup", "employee")
            and (node[0] != "employee" or self.can_edit_people)
        ]
        if not nodes:
            return
        if len(nodes) == 1:
            text = STRINGS.msg_delete_element_confirm
        else:
            text = STRINGS.msg_delete_elements_confirm.format(count=len(nodes))
        reply = QMessageBox.question(self, STRINGS.title_confirm, text)
        if reply != QMessageBox.Yes:
            return
        services = {
            "department": (Department, DepartmentService),
            "workgroup": (WorkingGroup, WorkingGroupService),
            "employee": (Employee, EmployeeService),
        }

        def do_delete() -> None:
            for node_type, node_id in nodes:
                model_class, service_class = services[node_type]
                obj = self.session.get(model_class, UUID(node_id))
                if obj is not None:
                    service_class(self.session).delete(obj)

        self._apply(do_delete, "Ошибка удаления элемента ОШС")

    def _on_nodes_dropped(
        self,
        tree: OSHMTreeWidget,
        payloads: List[NodeRef],
        target: Optional[NodeRef],
    ) -> None:
        """Обрабатывает drag&drop переподчинение сотрудников."""
        if self.is_head_office or target is None:
            return
        employees = [payload for payload in payloads if payload[0] == "employee"]
        if not employees:
            return

        def do_move() -> None:
            for _node_type, node_id in employees:
                employee = self.session.get(Employee, UUID(node_id))
                if employee is None:
                    continue
                if tree is self.tree_structure and target[0] == "department":
                    # Перевод сотрудника в другой отдел
                    employee.department_id = UUID(target[1])
                elif tree is self.tree_workgroups and target[0] == "workgroup":
                    # Включение сотрудника в рабочую группу
                    employee.working_group_id = UUID(target[1])

        self._apply(do_move, "Ошибка переноса сотрудника")

    def _apply(self, operation, error_message: str) -> None:
        """Выполняет операцию с фиксацией транзакции и обработкой ошибок."""
        try:
            operation()
            self.session.commit()
            self._load_data()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(error_message)
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
            self.session.rollback()


class DepartmentEditDialog(QDialog):
    """Диалог редактирования отдела."""

    def __init__(self, session, item=None, branch_id: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        self.branch_id = branch_id or (item.branch_id if item else None)
        title = entity_label(Department)
        self.setWindowTitle(title if item else STRINGS.oshm_new_m.format(title=title.lower()))
        self._setup_ui()
        if item:
            self.name_edit.setText(item.name)
            self.short_edit.setText(item.short_name or "")
            self.active_check.setChecked(item.active)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.short_edit = QLineEdit()
        self.active_check = QCheckBox(field_label(Department, "active"))
        self.active_check.setChecked(True)
        form.addRow(field_form_label(Department, "name"), self.name_edit)
        form.addRow(field_form_label(Department, "short_name"), self.short_edit)
        form.addRow("", self.active_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "short_name": self.short_edit.text().strip() or None,
            "active": self.active_check.isChecked(),
            "branch_id": self.branch_id,
        }


class WorkingGroupEditDialog(QDialog):
    """Диалог редактирования рабочей группы."""

    def __init__(self, session, item=None, department_id: Optional[UUID] = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        self.department_id = department_id or (item.department_id if item else None)
        title = entity_label(WorkingGroup)
        self.setWindowTitle(title if item else STRINGS.oshm_new_f.format(title=title.lower()))
        self._setup_ui()
        if item:
            self.name_edit.setText(item.name)
            self.comment_edit.setPlainText(item.comment or "")
            self.active_check.setChecked(item.active)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setMaximumHeight(80)
        self.active_check = QCheckBox(field_label(WorkingGroup, "active"))
        self.active_check.setChecked(True)
        form.addRow(field_form_label(WorkingGroup, "name"), self.name_edit)
        form.addRow(field_form_label(WorkingGroup, "comment"), self.comment_edit)
        form.addRow("", self.active_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "comment": self.comment_edit.toPlainText().strip() or None,
            "active": self.active_check.isChecked(),
            "department_id": self.department_id,
        }


class EmployeeEditDialog(QDialog):
    """Диалог редактирования сотрудника."""

    def __init__(self, session, item=None, department_id: Optional[UUID] = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        self.department_id = department_id or (item.department_id if item else None)
        title = entity_label(Employee)
        self.setWindowTitle(title if item else STRINGS.oshm_new_m.format(title=title.lower()))
        self._setup_ui()
        if item:
            self.last_name.setText(item.last_name)
            self.first_name.setText(item.first_name)
            self.middle_name.setText(item.middle_name or "")
            self.position.setText(item.position or "")
            self.active_check.setChecked(item.active)
            if item.academic_title_id:
                idx = self.title_combo.findData(item.academic_title_id)
                if idx >= 0:
                    self.title_combo.setCurrentIndex(idx)
            if item.working_group_id:
                idx = self.workgroup_combo.findData(str(item.working_group_id))
                if idx >= 0:
                    self.workgroup_combo.setCurrentIndex(idx)
            if item.workgroup_start_date:
                self.workgroup_start_date.setDate(item.workgroup_start_date)
            if item.workgroup_end_date:
                self.workgroup_end_date.setDate(item.workgroup_end_date)
        self._update_date_fields_state()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.last_name = QLineEdit()
        self.first_name = QLineEdit()
        self.middle_name = QLineEdit()
        self.position = QLineEdit()
        self.title_combo = QComboBox()
        self.title_combo.addItem("—", None)
        from internal_correspondence.orm.models import AcademicTitle
        for title in self.session.query(AcademicTitle).order_by(AcademicTitle.sort_order).all():
            self.title_combo.addItem(title.name, title.id)
        self.workgroup_combo = QComboBox()
        self.workgroup_combo.addItem("—", None)
        for wg in self.session.query(WorkingGroup).order_by(WorkingGroup.name).all():
            self.workgroup_combo.addItem(wg.name, str(wg.id))
        self.workgroup_combo.currentIndexChanged.connect(self._update_date_fields_state)

        self.workgroup_start_date = self._create_date_edit()
        self.workgroup_end_date = self._create_date_edit()
        self.clear_dates_btn = QPushButton(STRINGS.button_clear_dates)
        self.clear_dates_btn.clicked.connect(self._clear_workgroup_dates)

        self.active_check = QCheckBox(field_label(Employee, "active"))
        self.active_check.setChecked(True)
        form.addRow(field_form_label(Employee, "last_name"), self.last_name)
        form.addRow(field_form_label(Employee, "first_name"), self.first_name)
        form.addRow(field_form_label(Employee, "middle_name"), self.middle_name)
        form.addRow(field_form_label(Employee, "position"), self.position)
        form.addRow(field_form_label(Employee, "academic_title_id"), self.title_combo)
        form.addRow(field_form_label(Employee, "working_group_id"), self.workgroup_combo)
        form.addRow(field_form_label(Employee, "workgroup_start_date"), self.workgroup_start_date)
        form.addRow(field_form_label(Employee, "workgroup_end_date"), self.workgroup_end_date)
        form.addRow("", self.clear_dates_btn)
        form.addRow("", self.active_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_date_edit(self) -> QDateEdit:
        """Создаёт поле даты с пустым значением по умолчанию."""
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setMinimumDate(QDate(1900, 1, 1))
        edit.setSpecialValueText(STRINGS.date_not_set)
        edit.setDate(QDate(1900, 1, 1))
        return edit

    def _update_date_fields_state(self) -> None:
        """Включает поля дат только при выбранной рабочей группе."""
        has_group = self.workgroup_combo.currentData() is not None
        self.workgroup_start_date.setEnabled(has_group)
        self.workgroup_end_date.setEnabled(has_group)
        self.clear_dates_btn.setEnabled(has_group)

    def _clear_workgroup_dates(self) -> None:
        """Сбрасывает даты работы в рабочей группе."""
        self.workgroup_start_date.setDate(QDate(1900, 1, 1))
        self.workgroup_end_date.setDate(QDate(1900, 1, 1))

    def get_data(self) -> dict:
        wg_id = self.workgroup_combo.currentData()
        start_date = self.workgroup_start_date.date()
        end_date = self.workgroup_end_date.date()
        return {
            "last_name": self.last_name.text().strip(),
            "first_name": self.first_name.text().strip(),
            "middle_name": self.middle_name.text().strip() or None,
            "position": self.position.text().strip() or None,
            "academic_title_id": self.title_combo.currentData(),
            "department_id": self.department_id,
            "working_group_id": UUID(wg_id) if wg_id else None,
            "workgroup_start_date": (
                start_date.toPyDate() if wg_id and start_date.year() > 1900 else None
            ),
            "workgroup_end_date": (
                end_date.toPyDate() if wg_id and end_date.year() > 1900 else None
            ),
            "active": self.active_check.isChecked(),
        }
