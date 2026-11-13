"""Сервисы для работы со справочниками и ОШС."""

from datetime import date, datetime
from typing import Any, Dict, Optional

from internal_correspondence.core.domain_pack import enum_codes
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

        task_type = str(data.get("type") or "").strip()
        if task_type not in enum_codes("scientific_task_type"):
            raise ScientificTaskError(
                f"Неизвестный тип задачи «{task_type}»."
            )

        start = self._as_date(data.get("start_date"), "начала")
        if start is None:
            raise ScientificTaskError("Не указана дата начала задачи.")
        end = self._as_date(data.get("end_date"), "окончания")
        if end is not None and end < start:
            raise ScientificTaskError(
                "Дата окончания не может быть раньше даты начала."
            )

        partial = self._as_number(data.get("partial_threshold"), "частичного решения")
        full = self._as_number(data.get("full_threshold"), "полного решения")
        for value, label in ((partial, "частичного"), (full, "полного")):
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
