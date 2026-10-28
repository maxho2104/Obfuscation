"""Сервисы для работы со справочниками и ОШС."""

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
