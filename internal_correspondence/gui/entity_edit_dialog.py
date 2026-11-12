"""Базовый диалог (виджет) редактирования экземпляра сущности.

Диалог строится из элементов редактирования (см.
``gui/edit_elements.py``): сетка «метка — редактор», кнопки «Сохранить»
и «Отмена» по нижнему краю, кнопка «Больше» раскрывает дополнительные
(по умолчанию скрытые) поля. Обязательные незаполненные поля отображаются
даже среди скрытых.

Проверка вводимых данных выполняется при нажатии «Сохранить»: обход всех
отображаемых элементов сверху вниз; первый непрошедший проверку элемент
получает фокус, пользователю показывается сообщение с просьбой ввести
данные. Повторяется, пока все проверки не пройдут (или «Отмена»).
Дубли составных уникальных ограничений (например «Исходящий номер +
Дата») отлавливаются до записи в БД.

Если модель имеет колонку ``branch_id``, диалог обрабатывает её
автоматически: для роли «филиал» филиал фиксирован (редактор не
отображается), для роли «головной офис» — отображается редактируемый
выпадающий список филиалов (ручной ввод данных при сбое обмена).
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import UniqueConstraint, inspect as sa_inspect
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import Role
from internal_correspondence.gui.edit_elements import EditElement, create_element
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.labels import entity_label, field_label
from internal_correspondence.utils.string_resources import STRINGS

# Описание поля диалога: переменная сущности, готовый элемент
# или пара (метка, элемент)
FieldSpec = Union[Any, EditElement, tuple]


class EntityEditDialog(QDialog):
    """Базовый диалог редактирования экземпляра сущности.

    Args:
        session: Сессия БД.
        model_class: Класс ORM-модели.
        entity: Редактируемый экземпляр (None — создание).
        main_fields: Поля, отображаемые всегда; None — все поля сущности.
        extra_fields: Дополнительные поля, скрытые под кнопкой «Больше».
        role: Роль приложения (Role.BRANCH.value / Role.HEAD_OFFICE.value).
        fixed_branch_id: Филиал, фиксированный для роли «филиал».
        visibility_driver: Имя поля, от значения которого зависят
            правила видимости (обычно «type»).
        visibility_rules: Словарь «имя поля → предикат от значения
            драйвера»; поле отображается, когда предикат истинен.
    """

    def __init__(
        self,
        session: Session,
        model_class: Type[Base],
        entity: Optional[Base] = None,
        main_fields: Optional[Sequence[FieldSpec]] = None,
        extra_fields: Optional[Sequence[FieldSpec]] = None,
        role: Optional[str] = None,
        fixed_branch_id: Optional[str] = None,
        visibility_driver: Optional[str] = None,
        visibility_rules: Optional[Dict[str, Callable[[Any], bool]]] = None,
        parent=None,
        title: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.model_class = model_class
        self.entity = entity
        self.role = role
        self.fixed_branch_id = fixed_branch_id
        self.visibility_driver = visibility_driver
        self.visibility_rules = dict(visibility_rules or {})

        self._elements: List[EditElement] = []
        self._rows: List[Dict[str, Any]] = []
        self._extra_visible = False
        self._branch_element: Optional[EditElement] = None
        self.more_button: Optional[QPushButton] = None
        self._buttons_added = False

        if title is not None:
            window_title = title
        elif entity is not None:
            window_title = entity_label(model_class)
        else:
            window_title = STRINGS.action_add_entity.format(
                entity=entity_label(model_class)
            )
        self.setWindowTitle(window_title)
        self.setMinimumWidth(680)

        specs_main = list(main_fields) if main_fields is not None else self._default_fields()
        specs_extra = list(extra_fields or [])

        self._build_layout()
        self._build_branch_row()
        for spec in specs_main:
            self._add_field(spec, is_extra=False)
        for spec in specs_extra:
            self._add_field(spec, is_extra=True)
        self._setup_visibility_driver()
        self._load_values()
        self._update_more_button()

    # --- построение интерфейса ---

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll, 1)

        container = QWidget()
        self._scroll.setWidget(container)
        self._grid = QGridLayout(container)
        self._grid.setColumnStretch(1, 1)
        self._next_row = 0

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText(STRINGS.button_save)
        self.buttons.button(QDialogButtonBox.Cancel).setText(STRINGS.button_cancel)
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)

    def _default_fields(self) -> List[FieldSpec]:
        """Возвращает все редактируемые поля сущности по умолчанию.

        Автозаполняемые первичные ключи (uuid, автоинкремент) и служебное
        поле change_id не включаются; множественные связи включаются
        элементом списка N→N, скалярные связи пропускаются (их
        отображает колонка внешнего ключа).
        """
        mapper = sa_inspect(self.model_class)
        specs: List[FieldSpec] = []
        for column in mapper.columns:
            if column.name == "change_id":
                continue
            if column.primary_key and (
                column.default is not None or column.autoincrement is True
            ):
                continue
            specs.append(getattr(self.model_class, column.name))
        # Связи в набор по умолчанию не включаются: обратные коллекции
        # (branches, materials...) не редактируют через диалог сущности,
        # а прямые связи отображаются колонками внешних ключей. Явные
        # спецификации полей (main_fields) позволяют задать связи точно.
        return specs

    def _build_branch_row(self) -> None:
        """Добавляет выбор филиала для моделей с branch_id."""
        mapper = sa_inspect(self.model_class)
        if "branch_id" not in mapper.columns:
            return
        if self.role == Role.BRANCH.value:
            # Филиал фиксирован — редактор не отображается
            return
        element = create_element(self.model_class.branch_id, self.session, parent=self)
        element.editor.setMinimumWidth(300)
        self._branch_element = element
        self._add_field(element, is_extra=False)

    def _add_field(self, spec: FieldSpec, is_extra: bool) -> None:
        """Добавляет строку «метка — редактор» в сетку диалога."""
        label_override = None
        if isinstance(spec, tuple):
            label_override, spec = spec
        if isinstance(spec, EditElement):
            element = spec
        else:
            element = create_element(spec, self.session, parent=self)
        if label_override is not None:
            element._label_override = label_override  # pylint: disable=protected-access

        label = element.label_widget()
        row = self._next_row
        self._next_row += 1
        self._grid.addWidget(label, row, 0, alignment=Qt.AlignRight | Qt.AlignTop)
        self._grid.addWidget(element, row, 1)

        self._elements.append(element)
        self._rows.append(
            {"element": element, "label": label, "row": row, "is_extra": is_extra}
        )

    def _setup_visibility_driver(self) -> None:
        """Подключает правила условной видимости к драйверу."""
        if not self.visibility_driver:
            return
        driver = self.element(self.visibility_driver)
        if driver is None:
            return
        driver.valueChanged.connect(self._apply_visibility)
        self._apply_visibility()

    def _update_more_button(self) -> None:
        """Создаёт/обновляет кнопку «Больше» и размещает кнопки диалога."""
        has_extra = any(item["is_extra"] for item in self._rows)
        if has_extra and self.more_button is None:
            self.more_button = QPushButton()
            self.more_button.clicked.connect(self._toggle_extra)
            row = self._next_row
            self._next_row += 1
            self._grid.addWidget(self.more_button, row, 1, alignment=Qt.AlignLeft)
        if not self._buttons_added:
            row = self._next_row
            self._next_row += 1
            self._grid.addWidget(self.buttons, row, 0, 1, 2)
            self._buttons_added = True
        if self.more_button is not None:
            self.more_button.setText(
                STRINGS.button_less if self._extra_visible else STRINGS.button_more
            )
        self._apply_row_visibility()

    def _toggle_extra(self) -> None:
        self._extra_visible = not self._extra_visible
        self._update_more_button()

    def _apply_visibility(self) -> None:
        """Применяет правила видимости полей от значения драйвера."""
        if not self.visibility_driver:
            return
        driver = self.element(self.visibility_driver)
        if driver is None:
            return
        value = driver.value()
        for name, predicate in self.visibility_rules.items():
            element = self.element(name)
            if element is not None:
                element.setVisible(bool(predicate(value)))
                label = self._label_for(element)
                if label is not None:
                    label.setVisible(bool(predicate(value)))
        self._apply_row_visibility()

    def _apply_row_visibility(self) -> None:
        """Вычисляет видимость строк с учётом «Больше» и обязательности."""
        for item in self._rows:
            element = item["element"]
            rule_visible = True
            if element.field_name in self.visibility_rules:
                driver = self.element(self.visibility_driver) if self.visibility_driver else None
                if driver is not None:
                    rule_visible = bool(
                        self.visibility_rules[element.field_name](driver.value())
                    )
            if item["is_extra"] and not self._extra_visible:
                # Скрытые доп. поля показываем, только если обязательны
                # и не заполнены
                extra_visible = element.is_required() and element.is_empty()
            else:
                extra_visible = True
            visible = rule_visible and extra_visible
            element.setVisible(visible)
            item["label"].setVisible(visible)

    # --- доступ к элементам и данным ---

    def element(self, field_name: str) -> Optional[EditElement]:
        """Возвращает элемент редактирования по имени поля."""
        for element in self._elements:
            if element.field_name == field_name:
                return element
        return None

    def _label_for(self, element: EditElement) -> Optional[QLabel]:
        for item in self._rows:
            if item["element"] is element:
                return item["label"]
        return None

    def _load_values(self) -> None:
        """Загружает значения сущности (или умолчания) в элементы."""
        if self.entity is not None:
            for element in self._elements:
                element.load_value(self.entity)
            if self._branch_element is not None:
                self._branch_element.load_value(self.entity)
        self._apply_visibility()
        self._apply_row_visibility()
        # Строковые PK не редактируются при изменении существующей записи
        if self.entity is not None:
            mapper = sa_inspect(self.model_class)
            pk_columns = [column.name for column in mapper.primary_key]
            for name in pk_columns:
                element = self.element(name)
                if element is not None:
                    element.setEnabled(False)

    def get_data(self) -> Dict[str, Any]:
        """Возвращает данные диалога для сервисного слоя."""
        data: Dict[str, Any] = {}
        for element in self._elements:
            element.collect_data(data)
        if self._branch_element is not None:
            self._branch_element.collect_data(data)
        elif (
            sa_inspect(self.model_class).columns.get("branch_id") is not None
        ):
            data["branch_id"] = (
                self.entity.branch_id
                if self.entity is not None
                else self.fixed_branch_id
            )
        return data

    # --- сохранение и проверки ---

    def _on_save(self) -> None:
        """Проверяет все элементы сверху вниз и принимает диалог."""
        for element in self._elements:
            if not element.isVisible():
                continue
            message = element.validate()
            if message:
                QMessageBox.warning(self, STRINGS.title_attention, message)
                self._focus_element(element)
                return
        duplicate = self._find_duplicate()
        if duplicate is not None:
            message, element = duplicate
            QMessageBox.warning(self, STRINGS.title_attention, message)
            self._focus_element(element)
            return
        self.accept()

    def _focus_element(self, element: EditElement) -> None:
        """Передаёт фокус элементу и прокручивает к нему сетку."""
        self._scroll.ensureWidgetVisible(element)
        element.focus_editor()

    def _find_duplicate(self) -> Optional[tuple]:
        """Ищет дубли по уникальным ограничениям; возвращает (сообщение, элемент)."""
        mapper = sa_inspect(self.model_class)
        data = self.get_data()
        pk_names = [column.name for column in mapper.primary_key]
        for constraint in mapper.persist_selectable.constraints:
            if not isinstance(constraint, UniqueConstraint):
                continue
            column_names = [column.name for column in constraint.columns]
            if any(name not in data or data[name] is None for name in column_names):
                continue
            query = self.session.query(self.model_class)
            for name in column_names:
                query = query.filter(getattr(self.model_class, name) == data[name])
            found = query.first()
            if found is None:
                continue
            if self.entity is not None and all(
                getattr(found, name) == getattr(self.entity, name) for name in pk_names
            ):
                continue
            labels = ", ".join(
                field_label(self.model_class, name) for name in column_names
            )
            first_element = self.element(column_names[0])
            return (
                STRINGS.msg_duplicate_fields.format(fields=labels),
                first_element,
            )
        return None
