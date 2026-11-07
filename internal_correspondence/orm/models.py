"""ORM-модели сущностей системы внутренней корреспонденции."""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from internal_correspondence.orm.base import Base, TimestampMixin, VersionedMixin


# -----------------------------------------------------------------------------
# Вспомогательные функции и ассоциативные таблицы
# -----------------------------------------------------------------------------

def _uuid_pk() -> Mapped[uuid.UUID]:
    """Возвращает mapped_column для UUID-первичного ключа."""
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


# Связь "Научный материал - Отдел" (N-N)
material_department_association = Table(
    "material_departments",
    Base.metadata,
    Column("material_id", PGUUID(as_uuid=True), ForeignKey("scientific_materials.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", PGUUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Научный материал - Сотрудник" (N-N)
material_employee_association = Table(
    "material_employees",
    Base.metadata,
    Column("material_id", PGUUID(as_uuid=True), ForeignKey("scientific_materials.id", ondelete="CASCADE"), primary_key=True),
    Column("employee_id", PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Научный материал - Рабочая группа" (N-N)
material_workgroup_association = Table(
    "material_workgroups",
    Base.metadata,
    Column("material_id", PGUUID(as_uuid=True), ForeignKey("scientific_materials.id", ondelete="CASCADE"), primary_key=True),
    Column("workgroup_id", PGUUID(as_uuid=True), ForeignKey("working_groups.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Научный материал - Источник" (N-N)
material_source_association = Table(
    "material_sources",
    Base.metadata,
    Column("material_id", PGUUID(as_uuid=True), ForeignKey("scientific_materials.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", String(50), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Научный материал - Файл" (N-N)
material_file_association = Table(
    "material_files",
    Base.metadata,
    Column("material_id", PGUUID(as_uuid=True), ForeignKey("scientific_materials.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", PGUUID(as_uuid=True), ForeignKey("file_records.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Телеграмма - Отдел" (N-N)
telegram_department_association = Table(
    "telegram_departments",
    Base.metadata,
    Column("telegram_id", PGUUID(as_uuid=True), ForeignKey("telegrams.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", PGUUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Телеграмма - Сотрудник" (N-N)
telegram_employee_association = Table(
    "telegram_employees",
    Base.metadata,
    Column("telegram_id", PGUUID(as_uuid=True), ForeignKey("telegrams.id", ondelete="CASCADE"), primary_key=True),
    Column("employee_id", PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Телеграмма - Рабочая группа" (N-N)
telegram_workgroup_association = Table(
    "telegram_workgroups",
    Base.metadata,
    Column("telegram_id", PGUUID(as_uuid=True), ForeignKey("telegrams.id", ondelete="CASCADE"), primary_key=True),
    Column("workgroup_id", PGUUID(as_uuid=True), ForeignKey("working_groups.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Телеграмма - Источник" (N-N)
telegram_source_association = Table(
    "telegram_sources",
    Base.metadata,
    Column("telegram_id", PGUUID(as_uuid=True), ForeignKey("telegrams.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", String(50), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Телеграмма - Файл" (N-N)
telegram_file_association = Table(
    "telegram_files",
    Base.metadata,
    Column("telegram_id", PGUUID(as_uuid=True), ForeignKey("telegrams.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", PGUUID(as_uuid=True), ForeignKey("file_records.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Научная задача - Сотрудник" (N-N)
task_employee_association = Table(
    "task_employees",
    Base.metadata,
    Column("task_id", String(50), ForeignKey("scientific_tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("employee_id", PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Оценка - Научный материал" (N-N)
evaluation_material_association = Table(
    "evaluation_materials",
    Base.metadata,
    Column("evaluation_id", PGUUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", PGUUID(as_uuid=True), ForeignKey("scientific_materials.id", ondelete="CASCADE"), primary_key=True),
)

# Связь "Оценка - Телеграмма" (N-N)
evaluation_telegram_association = Table(
    "evaluation_telegrams",
    Base.metadata,
    Column("evaluation_id", PGUUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), primary_key=True),
    Column("telegram_id", PGUUID(as_uuid=True), ForeignKey("telegrams.id", ondelete="CASCADE"), primary_key=True),
)


# -----------------------------------------------------------------------------
# Изменение (Change)
# -----------------------------------------------------------------------------

class Change(Base, TimestampMixin):
    """Запись об изменении сущности для механизма delta-tracking."""
    __entity_label__ = "Изменение"
    __entity_label_plural__ = "Изменения"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "changes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True, info={"label": "Сущность"})
    entity_pk: Mapped[str] = mapped_column(String(255), nullable=False, index=True, info={"label": "Ключ сущности"})
    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        info={"label": "Дата и время изменения"},
    )
    changed_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list, info={"label": "Изменённые переменные"})

    def __repr__(self) -> str:
        return f"<Change {self.entity_name} pk={self.entity_pk} fields={self.changed_fields}>"


class ChangeTrackedMixin:
    """Миксин ссылки на запись Change для механизма delta-tracking.

    Каждая редактируемая сущность хранит ссылку на запись ``Change``,
    описывающую последние неэкспортированные изменения объекта.
    """

    change_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("changes.id", ondelete="SET NULL"),
        nullable=True,
    )

    @declared_attr
    def change(cls) -> Mapped[Optional["Change"]]:
        return relationship("Change")


# -----------------------------------------------------------------------------
# Справочники
# -----------------------------------------------------------------------------

class TerritorialUnit(Base, ChangeTrackedMixin, VersionedMixin):
    """Территориальная единица (область, край, город и т.д.)."""
    __entity_label__ = "Территориальная единица"
    __entity_label_plural__ = "Территориальные единицы"


    __tablename__ = "territorial_units"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Сокращенное наименование"})
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})

    branches: Mapped[List["Branch"]] = relationship(
        "Branch",
        back_populates="territorial_unit",
        cascade="all, delete-orphan",
    )


class Branch(Base, ChangeTrackedMixin, VersionedMixin):
    """Филиал научной организации."""
    __entity_label__ = "Филиал"
    __entity_label_plural__ = "Филиалы"


    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Индекс"})
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})
    short_name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Сокращенное наименование", "short": "Сокращение"})

    territorial_unit_id: Mapped[str] = mapped_column(
        ForeignKey("territorial_units.id", ondelete="RESTRICT"),
        nullable=False,
        info={"label": "Территориальная единица"},
    )
    territorial_unit: Mapped["TerritorialUnit"] = relationship(
        "TerritorialUnit",
        back_populates="branches",
        info={"label": "Территориальная единица"},
    )

    departments: Mapped[List["Department"]] = relationship(
        "Department",
        back_populates="branch",
        cascade="all, delete-orphan",
    )
    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        back_populates="branch",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        back_populates="branch",
    )


class Country(Base, ChangeTrackedMixin, VersionedMixin):
    """Страна происхождения данных."""
    __entity_label__ = "Страна"
    __entity_label_plural__ = "Страны"


    __tablename__ = "countries"

    id: Mapped[str] = mapped_column(String(10), primary_key=True, info={"label": "Сокращенное наименование"})
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        back_populates="country",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        back_populates="country",
    )


class AcademicTitle(Base, ChangeTrackedMixin, VersionedMixin):
    """Научное звание сотрудника."""
    __entity_label__ = "Научное звание"
    __entity_label_plural__ = "Научные звания"


    __tablename__ = "academic_titles"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Сокращенное наименование"})
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})
    genitive: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Род. падеж"})
    dative: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Дат. падеж"})
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Порядок"})

    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        back_populates="academic_title",
    )


class Consumer(Base, ChangeTrackedMixin, VersionedMixin):
    """Подразделение головного офиса или сторонняя организация, выставляющая оценки."""
    __entity_label__ = "Потребитель"
    __entity_label_plural__ = "Потребители"


    __tablename__ = "consumers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Индекс"})
    short_name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Сокращенное наименование", "short": "Сокращение"})
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        back_populates="consumer",
    )


class Source(Base, ChangeTrackedMixin, VersionedMixin):
    """Источник данных, положенных в основу научного материала."""
    __entity_label__ = "Источник"
    __entity_label_plural__ = "Источники"


    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Индекс"})
    type: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Тип"})
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Комментарий"})

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        secondary=material_source_association,
        back_populates="sources",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        secondary=telegram_source_association,
        back_populates="sources",
    )


class Leader(Base, ChangeTrackedMixin, VersionedMixin):
    """Должность руководителя, которому докладываются телеграммы."""
    __entity_label__ = "Руководитель"
    __entity_label_plural__ = "Руководители"


    __tablename__ = "leaders"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Сокращенное наименование"})
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Действительный"})

    report_addresses: Mapped[List["ReportAddress"]] = relationship(
        "ReportAddress",
        back_populates="leader",
        cascade="all, delete-orphan",
    )


# -----------------------------------------------------------------------------
# Организационно-штатная структура (ОШС)
# -----------------------------------------------------------------------------

class Department(Base, ChangeTrackedMixin, VersionedMixin):
    """Отдел филиала."""
    __entity_label__ = "Отдел"
    __entity_label_plural__ = "Отделы"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})
    short_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Сокращенное наименование", "short": "Сокращение"})
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Действительный"})

    branch_id: Mapped[str] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        info={"label": "Филиал"},
    )
    branch: Mapped["Branch"] = relationship("Branch", back_populates="departments")

    workgroups: Mapped[List["WorkingGroup"]] = relationship(
        "WorkingGroup",
        back_populates="department",
        cascade="all, delete-orphan",
    )
    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        back_populates="department",
        cascade="all, delete-orphan",
    )

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        secondary=material_department_association,
        back_populates="departments",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        secondary=telegram_department_association,
        back_populates="departments",
    )


class WorkingGroup(Base, ChangeTrackedMixin, VersionedMixin):
    """Рабочая группа, к работе в которой привлекаются сотрудники."""
    __entity_label__ = "Рабочая группа"
    __entity_label_plural__ = "Рабочие группы"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "working_groups"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Наименование"})
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Комментарий"})
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Действительная"})

    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        info={"label": "Отдел"},
    )
    department: Mapped["Department"] = relationship(
        "Department",
        back_populates="workgroups",
    )

    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        back_populates="working_group",
    )

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        secondary=material_workgroup_association,
        back_populates="workgroups",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        secondary=telegram_workgroup_association,
        back_populates="workgroups",
    )


class Employee(Base, ChangeTrackedMixin, VersionedMixin):
    """Сотрудник филиала."""
    __entity_label__ = "Сотрудник"
    __entity_label_plural__ = "Сотрудники"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = _uuid_pk()
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Фамилия"})
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Имя"})
    middle_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Отчество"})
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Должность"})
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Действительный"})

    academic_title_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("academic_titles.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Научное звание"},
    )
    academic_title: Mapped[Optional["AcademicTitle"]] = relationship(
        "AcademicTitle",
        back_populates="employees",
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        info={"label": "Отдел"},
    )
    department: Mapped["Department"] = relationship(
        "Department",
        back_populates="employees",
    )

    working_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("working_groups.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Рабочая группа"},
    )
    working_group: Mapped[Optional["WorkingGroup"]] = relationship(
        "WorkingGroup",
        back_populates="employees",
    )

    workgroup_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Начало работы в рабочей группе", "short": "Начало в группе"})
    workgroup_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Конец работы в рабочей группе", "short": "Конец в группе"})

    tasks: Mapped[List["ScientificTask"]] = relationship(
        "ScientificTask",
        secondary=task_employee_association,
        back_populates="employees",
    )
    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        secondary=material_employee_association,
        back_populates="employees",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        secondary=telegram_employee_association,
        back_populates="employees",
    )


    def display_name(self) -> str:
        """Возвращает сокращённое ФИО сотрудника."""
        initials = f"{self.first_name[0]}." if self.first_name else ""
        if self.middle_name:
            initials += f"{self.middle_name[0]}."
        title = f"{self.academic_title_id} " if self.academic_title_id else ""
        return f"{title}{self.last_name} {initials}".strip()

    def worked_in_workgroup_on(self, value: date) -> bool:
        """Проверяет, работал ли сотрудник в рабочей группе на указанную дату."""
        if self.working_group_id is None:
            return False
        if self.workgroup_start_date is not None and value < self.workgroup_start_date:
            return False
        if self.workgroup_end_date is not None and value > self.workgroup_end_date:
            return False
        return True


# -----------------------------------------------------------------------------
# Научная задача
# -----------------------------------------------------------------------------

class ScientificTask(Base, ChangeTrackedMixin, VersionedMixin):
    """Научная задача, формулируемая руководством."""
    __entity_label__ = "Научная задача"
    __entity_label_plural__ = "Научные задачи"


    __tablename__ = "scientific_tasks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, info={"label": "Код"})
    name: Mapped[str] = mapped_column(String(500), nullable=False, info={"label": "Наименование"})
    type: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Тип"})
    start_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Начало действия", "short": "Начало"})
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Конец действия", "short": "Окончание"})
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Комментарий"})
    partial_threshold: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, info={"label": "Частичное решение"})
    full_threshold: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, info={"label": "Полное решение"})

    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        secondary=task_employee_association,
        back_populates="tasks",
    )
    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        back_populates="task",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        back_populates="task",
    )


# -----------------------------------------------------------------------------
# Файл
# -----------------------------------------------------------------------------

class FileRecord(Base, ChangeTrackedMixin, VersionedMixin):
    """Прикреплённый файл."""
    __entity_label__ = "Файл"
    __entity_label_plural__ = "Файлы"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "file_records"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Имя"})
    extension: Mapped[str] = mapped_column(String(20), nullable=False, info={"label": "Расширение"})
    path: Mapped[str] = mapped_column(String(500), nullable=False, info={"label": "Путь"})

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        secondary=material_file_association,
        back_populates="files",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        secondary=telegram_file_association,
        back_populates="files",
    )


# -----------------------------------------------------------------------------
# Участники документа
# -----------------------------------------------------------------------------

class ParticipantMixin:
    """Вычисляемые участники документа: сотрудники, отделы и рабочие группы."""

    @property
    def document_date(self) -> Optional[date]:
        """Дата документа для расчёта участия сотрудников в рабочих группах."""
        return self.outgoing_date or self.incoming_date

    @property
    def participating_employees(self) -> List["Employee"]:
        """Сотрудники, причастные к документу, в порядке ФИО."""
        return sorted(
            self.employees,
            key=lambda employee: (
                employee.last_name,
                employee.first_name,
                employee.middle_name or "",
            ),
        )

    @property
    def participating_departments(self) -> List["Department"]:
        """Отделы, к которым фактически относятся причастные сотрудники."""
        departments = {}
        for employee in self.employees:
            department = employee.department
            if department is not None:
                departments[department.id] = department
        return sorted(departments.values(), key=lambda department: department.name)

    @property
    def participating_workgroups(self) -> List["WorkingGroup"]:
        """Рабочие группы, в которых сотрудники работали на дату документа."""
        workgroups = {}
        document_date = self.document_date
        for employee in self.employees:
            workgroup = employee.working_group
            if workgroup is None:
                continue
            if document_date is not None and not employee.worked_in_workgroup_on(document_date):
                continue
            workgroups[workgroup.id] = workgroup
        return sorted(workgroups.values(), key=lambda workgroup: workgroup.name)


class EvaluationMixin:
    """Вычисляемая оценка документа для отображения в списках."""

    @property
    def latest_evaluation(self) -> Optional["Evaluation"]:
        """Возвращает последнюю оценку документа по дате списка оценок."""
        evaluations = [
            evaluation
            for evaluation in self.evaluations
            if evaluation.evaluation_list is not None
        ]
        if not evaluations:
            return None
        return max(
            evaluations,
            key=lambda evaluation: (
                evaluation.evaluation_list.date,
                evaluation.evaluation_list.number or "",
                str(evaluation.id),
            ),
        )

    @property
    def evaluation_share(self) -> Optional[float]:
        """Доля оценки, приходящаяся на один документ в совокупности."""
        evaluation = self.latest_evaluation
        if evaluation is None:
            return None
        documents_count = len(evaluation.materials) + len(evaluation.telegrams)
        if documents_count <= 0:
            return None
        return 1.0 / documents_count

    @property
    def evaluation_display(self) -> str:
        """Строка оценки с учётом распределения по совокупности документов."""
        evaluation = self.latest_evaluation
        if evaluation is None:
            return ""
        documents_count = len(evaluation.materials) + len(evaluation.telegrams)
        if documents_count <= 0:
            return ""
        if documents_count == 1:
            return evaluation.value
        share = 1.0 / documents_count
        return f"{share:.2f}".replace(".", ",") + f" {evaluation.value}"


# -----------------------------------------------------------------------------
# Научный материал
# -----------------------------------------------------------------------------

class ScientificMaterial(Base, ChangeTrackedMixin, VersionedMixin, ParticipantMixin, EvaluationMixin):
    """Передаваемый/принимаемый научный материал."""
    __entity_label__ = "Научный материал"
    __entity_label_plural__ = "Научные материалы"
    __entity_label_prepositional__ = "научном материале"
    __entity_label_prepositional_plural__ = "научных материалах"
    __field_labels__ = {"id": "Идентификатор", "participating_employees": "Сотрудники", "participating_departments": "Отделы", "participating_workgroups": "Рабочие группы", "evaluation_display": "Оценка"}


    __tablename__ = "scientific_materials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    type: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Тип"})
    outgoing_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Исходящий номер", "short": "Исх. номер", "required": True})
    outgoing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Дата исходящего номера", "short": "Дата исх.", "required": True})
    name: Mapped[str] = mapped_column(String(500), nullable=False, info={"label": "Наименование"})
    incoming_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Входящий номер", "short": "Вх. номер"})
    incoming_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Дата входящего номера", "short": "Дата вх."})
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Серийный номер"})
    release_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"label": "Год выпуска"})
    permit_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Номер разрешительного документа"})
    cost: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True, info={"label": "Стоимость"})
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Комментарий"})

    country_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Страна"},
    )
    country: Mapped[Optional["Country"]] = relationship(
        "Country",
        back_populates="materials",
    )

    consumer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("consumers.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Потребитель"},
    )
    consumer: Mapped[Optional["Consumer"]] = relationship(
        "Consumer",
        back_populates="materials",
        info={"label": "Потребитель"},
    )

    branch_id: Mapped[str] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        info={"label": "Филиал"},
    )
    branch: Mapped["Branch"] = relationship("Branch", back_populates="materials", info={"label": "Филиал"})

    task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("scientific_tasks.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Задача"},
    )
    task: Mapped[Optional["ScientificTask"]] = relationship(
        "ScientificTask",
        back_populates="materials",
    )

    departments: Mapped[List["Department"]] = relationship(
        "Department",
        secondary=material_department_association,
        back_populates="materials",
    )
    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        secondary=material_employee_association,
        back_populates="materials",
    )
    workgroups: Mapped[List["WorkingGroup"]] = relationship(
        "WorkingGroup",
        secondary=material_workgroup_association,
        back_populates="materials",
    )
    sources: Mapped[List["Source"]] = relationship(
        "Source",
        secondary=material_source_association,
        back_populates="materials",
    )
    files: Mapped[List["FileRecord"]] = relationship(
        "FileRecord",
        secondary=material_file_association,
        back_populates="materials",
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation",
        secondary=evaluation_material_association,
        back_populates="materials",
    )


    __table_args__ = (
        UniqueConstraint("outgoing_number", "outgoing_date", name="uix_material_outgoing"),
    )


# -----------------------------------------------------------------------------
# Телеграмма
# -----------------------------------------------------------------------------

class Telegram(Base, ChangeTrackedMixin, VersionedMixin, ParticipantMixin, EvaluationMixin):
    """Передаваемая/принимаемая телеграмма."""
    __entity_label__ = "Телеграмма"
    __entity_label_plural__ = "Телеграммы"
    __entity_label_prepositional__ = "телеграмме"
    __entity_label_prepositional_plural__ = "телеграммах"
    __field_labels__ = {"id": "Идентификатор", "participating_employees": "Сотрудники", "participating_departments": "Отделы", "participating_workgroups": "Рабочие группы", "evaluation_display": "Оценка"}


    __tablename__ = "telegrams"

    id: Mapped[uuid.UUID] = _uuid_pk()
    type: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Тип"})
    outgoing_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Исходящий номер", "short": "Исх. номер", "required": True})
    outgoing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Дата исходящего номера", "short": "Дата исх.", "required": True})
    name: Mapped[str] = mapped_column(String(500), nullable=False, info={"label": "Наименование (тема)", "short": "Наименование"})
    incoming_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Входящий номер", "short": "Вх. номер"})
    incoming_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Дата входящего номера", "short": "Дата вх."})
    report_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Тип доклада"})
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Комментарий"})

    country_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Страна"},
    )
    country: Mapped[Optional["Country"]] = relationship(
        "Country",
        back_populates="telegrams",
    )

    branch_id: Mapped[str] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        info={"label": "Филиал"},
    )
    branch: Mapped["Branch"] = relationship(
        "Branch", back_populates="telegrams", info={"label": "Филиал"}
    )

    task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("scientific_tasks.id", ondelete="SET NULL"),
        nullable=True,
        info={"label": "Задача"},
    )
    task: Mapped[Optional["ScientificTask"]] = relationship(
        "ScientificTask",
        back_populates="telegrams",
    )

    departments: Mapped[List["Department"]] = relationship(
        "Department",
        secondary=telegram_department_association,
        back_populates="telegrams",
    )
    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        secondary=telegram_employee_association,
        back_populates="telegrams",
    )
    workgroups: Mapped[List["WorkingGroup"]] = relationship(
        "WorkingGroup",
        secondary=telegram_workgroup_association,
        back_populates="telegrams",
    )
    sources: Mapped[List["Source"]] = relationship(
        "Source",
        secondary=telegram_source_association,
        back_populates="telegrams",
    )
    files: Mapped[List["FileRecord"]] = relationship(
        "FileRecord",
        secondary=telegram_file_association,
        back_populates="telegrams",
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation",
        secondary=evaluation_telegram_association,
        back_populates="telegrams",
    )


    __table_args__ = (
        UniqueConstraint("outgoing_number", "outgoing_date", name="uix_telegram_outgoing"),
    )


# -----------------------------------------------------------------------------
# Адресация доклада телеграмм
# -----------------------------------------------------------------------------

class ReportAddress(Base, ChangeTrackedMixin, VersionedMixin):
    """Промежуточная таблица между телеграммой и адресатом доклада с датой доклада."""
    __entity_label__ = "Адресация доклада"
    __entity_label_plural__ = "Адресации доклада"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "report_addresses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    report_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Дата доклада"})

    telegram_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("telegrams.id", ondelete="CASCADE"),
        nullable=False,
        info={"label": "Телеграмма"},
    )
    telegram: Mapped["Telegram"] = relationship("Telegram")

    leader_id: Mapped[str] = mapped_column(
        ForeignKey("leaders.id", ondelete="RESTRICT"),
        nullable=False,
        info={"label": "Руководитель"},
    )
    leader: Mapped["Leader"] = relationship("Leader", back_populates="report_addresses")


# -----------------------------------------------------------------------------
# Список оценок и оценка
# -----------------------------------------------------------------------------

class EvaluationList(Base, ChangeTrackedMixin, VersionedMixin):
    """Документ, определяющий выставление оценок материалам/телеграммам."""
    __entity_label__ = "Список оценок"
    __entity_label_plural__ = "Списки оценок"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "evaluation_lists"

    id: Mapped[uuid.UUID] = _uuid_pk()
    number: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Номер"})
    date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Дата"})

    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation",
        back_populates="evaluation_list",
        cascade="all, delete-orphan",
    )


class Evaluation(Base, ChangeTrackedMixin, VersionedMixin):
    """Оценка материалов/телеграмм потребителем."""
    __entity_label__ = "Оценка"
    __entity_label_plural__ = "Оценки"
    __field_labels__ = {"id": "Идентификатор"}


    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    value: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Значение оценки"})

    evaluation_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_lists.id", ondelete="CASCADE"),
        nullable=False,
        info={"label": "Список оценок"},
    )
    evaluation_list: Mapped["EvaluationList"] = relationship(
        "EvaluationList",
        back_populates="evaluations",
    )

    materials: Mapped[List["ScientificMaterial"]] = relationship(
        "ScientificMaterial",
        secondary=evaluation_material_association,
        back_populates="evaluations",
    )
    telegrams: Mapped[List["Telegram"]] = relationship(
        "Telegram",
        secondary=evaluation_telegram_association,
        back_populates="evaluations",
    )
