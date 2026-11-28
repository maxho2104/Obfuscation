"""Сервисы для работы со справочниками и ОШС."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional

from internal_correspondence.core.constants import ScientificTaskType
from internal_correspondence.core.domain_pack import enum_code_of, enum_label
from internal_correspondence.orm.models import (
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Department,
    Employee,
    Leader,
    ScientificTask,
    Source,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.services.base_service import BaseService
from internal_correspondence.utils.string_resources import STRINGS

# Маркер «поле не передано» (отличие от явного None)
_UNSET = object()


class ScientificTaskError(ValueError):
    """Ошибка проверки данных научной задачи."""


class TerritorialUnitService(BaseService[TerritorialUnit]):
    """Сервис территориальных единиц."""

    def __init__(self, session) -> None:
        super().__init__(session, TerritorialUnit)


class BranchService(BaseService[Branch]):
    """Сервис филиалов."""

    def __init__(self, session) -> None:
        super().__init__(session, Branch)


class CountryService(BaseService[Country]):
    """Сервис стран."""

    def __init__(self, session) -> None:
        super().__init__(session, Country)


class AcademicTitleService(BaseService[AcademicTitle]):
    """Сервис научных званий."""

    def __init__(self, session) -> None:
        super().__init__(session, AcademicTitle)


class ScientificTaskService(BaseService[ScientificTask]):
    """Сервис научных задач с проверкой бизнес-правил."""

    def __init__(self, session) -> None:
        super().__init__(session, ScientificTask)

    def create_task(self, data: Dict[str, Any]) -> ScientificTask:
        """Создаёт задачу после проверки обязательных полей и кода."""
        values = self._validated(data)
        if self.session.get(ScientificTask, values["id"]) is not None:
            raise ScientificTaskError(
                f"Задача с кодом «{values['id']}» уже существует."
            )
        return self.create(values)

    def update_task(
        self, task: ScientificTask, data: Dict[str, Any]
    ) -> ScientificTask:
        """Обновляет задачу; код задачи не меняется."""
        values = self._validated(data, task)
        values.pop("id", None)
        return self.update(task, values)

    def delete_task(self, task: ScientificTask) -> None:
        """Удаляет задачу, если она не используется в документах."""
        if task.materials or task.telegrams:
            raise ScientificTaskError(
                "Задача используется в документах и не может быть удалена."
            )
        self.delete(task)

    def _validated(
        self, data: Dict[str, Any], instance: Optional[ScientificTask] = None
    ) -> Dict[str, Any]:
        task_id = str(
            data.get("id") or (instance.id if instance is not None else "")
        ).strip()
        if not task_id:
            raise ScientificTaskError("Не указан код задачи.")
        if len(task_id) > 50:
            raise ScientificTaskError("Код задачи длиннее 50 символов.")

        name = str(data.get("name") or "").strip()
        if not name:
            raise ScientificTaskError("Не указано наименование задачи.")

        task_type = self._as_task_type(data.get("type"))

        start = self._as_date(data.get("start_date"), STRINGS.text_nachala)
        if start is None:
            raise ScientificTaskError("Не указана дата начала задачи.")
        end = self._as_date(data.get("end_date"), STRINGS.text_okonchaniya)
        if end is not None and end < start:
            raise ScientificTaskError(
                "Дата окончания не может быть раньше даты начала."
            )

        partial = self._as_number(data.get("partial_threshold"), STRINGS.text_chastichnogo_resheniya)
        full = self._as_number(data.get("full_threshold"), STRINGS.text_polnogo_resheniya)
        for value, label in ((partial, STRINGS.text_chastichnogo), (full, STRINGS.text_polnogo)):
            if value is not None and value < 0:
                raise ScientificTaskError(
                    f"Порог {label} решения не может быть отрицательным."
                )
        if (
            partial is not None
            and full is not None
            and partial > full
        ):
            raise ScientificTaskError(
                "Порог частичного решения не может быть больше полного."
            )

        return {
            "id": task_id,
            "name": name,
            "type": task_type,
            "start_date": start,
            "end_date": end,
            "comment": (str(data.get("comment") or "").strip() or None),
            "partial_threshold": partial,
            "full_threshold": full,
        }

    @staticmethod
    def _as_task_type(value: Any) -> ScientificTaskType:
        """Приводит тип задачи к перечислению.

        Принимает член перечисления, числовое значение, код пакета
        (например, «ОЗ») или его русскую метку.
        """
        if isinstance(value, ScientificTaskType):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            try:
                return ScientificTaskType(value)
            except ValueError as error:
                raise ScientificTaskError(
                    f"Неизвестный тип задачи «{value}»."
                ) from error

        text = str(value or "").strip()
        for member in ScientificTaskType:
            key = member.name.lower()
            try:
                code = enum_code_of("scientific_task_type", key)
            except ValueError:
                code = ""
            label = enum_label("scientific_task_type", code) if code else ""
            if text in {code, label, member.name, str(member.value)}:
                return member

        raise ScientificTaskError(f"Неизвестный тип задачи «{text}».")

    @staticmethod
    def _as_date(value: Any, label: str) -> Optional[date]:
        if value in (None, "", 0):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        raise ScientificTaskError(f"Некорректная дата {label} задачи.")

    @staticmethod
    def _as_number(value: Any, label: str) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise ScientificTaskError(
                f"Некорректное значение порога {label} решения."
            ) from error


class ConsumerService(BaseService[Consumer]):
    """Сервис потребителей."""

    def __init__(self, session) -> None:
        super().__init__(session, Consumer)


class LeaderService(BaseService[Leader]):
    """Сервис руководителей."""

    def __init__(self, session) -> None:
        super().__init__(session, Leader)


class SourceService(BaseService[Source]):
    """Сервис источников."""

    def __init__(self, session) -> None:
        super().__init__(session, Source)


class DepartmentService(BaseService[Department]):
    """Сервис отделов."""

    def __init__(self, session) -> None:
        super().__init__(session, Department)


class WorkingGroupService(BaseService[WorkingGroup]):
    """Сервис рабочих групп."""

    def __init__(self, session) -> None:
        super().__init__(session, WorkingGroup)


class EmployeeService(BaseService[Employee]):
    """Сервис сотрудников."""

    def __init__(self, session) -> None:
        super().__init__(session, Employee)

    def create(self, data: Dict[str, Any]) -> Employee:
        """Создаёт сотрудника; поля рабочей группы открывают первое участие."""
        wg_id, wg_start, wg_end = self._pop_workgroup_fields(data)
        instance = super().create(data)
        if wg_id is not _UNSET and wg_id is not None:
            self._open_membership(instance, wg_id, wg_start, wg_end)
        return instance

    def update(self, instance: Employee, data: Dict[str, Any]) -> Employee:
        """Обновляет сотрудника; смена группы закрывает старое участие и открывает новое."""
        wg_id, wg_start, wg_end = self._pop_workgroup_fields(data)
        super().update(instance, data)
        if wg_id is _UNSET:
            return instance
        current = instance.current_membership
        if wg_id is None:
            # Исключение из группы: активное участие закрывается
            if current is not None and current.end_date is None:
                self._validate_period(current.start_date, wg_end or wg_start)
                current.end_date = wg_end or wg_start or date.today()
        elif current is not None and current.working_group_id == wg_id:
            # Та же группа: обновляем даты активного участия
            self._validate_period(wg_start, wg_end)
            current.start_date = wg_start
            current.end_date = wg_end
        else:
            self._open_membership(instance, wg_id, wg_start, wg_end)
        self.session.flush()
        return instance

    @staticmethod
    def _validate_period(
        start_date: Optional[date], end_date: Optional[date]
    ) -> None:
        """Проверяет, что дата окончания участия не раньше даты начала."""
        if (
            start_date is not None
            and end_date is not None
            and end_date < start_date
        ):
            raise ValueError(
                "Дата окончания участия не может быть раньше даты начала."
            )

    def _open_membership(
        self,
        instance: Employee,
        wg_id: uuid.UUID,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> None:
        """Открывает новое участие в группе (прежнее закрывается моделью)."""
        workgroup = self.session.get(WorkingGroup, wg_id)
        if workgroup is None:
            raise ValueError(f"Рабочая группа не найдена: {wg_id}")
        self._validate_period(start_date, end_date)
        membership = instance.assign_working_group(workgroup, start_date=start_date)
        if membership is not None and membership.end_date is None and end_date is not None:
            membership.end_date = end_date
        self.session.flush()

    @staticmethod
    def _pop_workgroup_fields(data: Dict[str, Any]):
        """Извлекает из словаря поля участия в рабочей группе."""
        wg_id = data.pop("working_group_id", _UNSET)
        wg_start = data.pop("workgroup_start_date", None)
        wg_end = data.pop("workgroup_end_date", None)
        return wg_id, wg_start, wg_end
