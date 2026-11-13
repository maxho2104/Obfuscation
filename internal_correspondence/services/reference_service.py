"""Сервисы для работы со справочниками и ОШС."""

import uuid
from datetime import date
from typing import Any, Dict, Optional

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

# Маркер «поле не передано» (отличие от явного None)
_UNSET = object()


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
    """Сервис научных задач."""

    def __init__(self, session) -> None:
        super().__init__(session, ScientificTask)


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
        if wg_id is not None:
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
                current.end_date = wg_end or wg_start or date.today()
        elif current is not None and current.working_group_id == wg_id:
            # Та же группа: обновляем даты активного участия
            current.start_date = wg_start
            current.end_date = wg_end
        else:
            self._open_membership(instance, wg_id, wg_start, wg_end)
        self.session.flush()
        return instance

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
