"""Базовый CRUD-сервис для работы с ORM-моделями."""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import asc, desc, func, inspect
from sqlalchemy.orm import Session

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base

T = TypeVar("T", bound=Base)

logger = get_logger("base_service")


class BaseService(Generic[T]):
    """Универсальный сервис для создания, чтения, обновления и удаления записей."""

    def __init__(self, session: Session, model_class: Type[T]) -> None:
        self.session = session
        self.model_class = model_class

    def get_by_id(self, pk: Any) -> Optional[T]:
        """Возвращает объект по первичному ключу."""
        return self.session.get(self.model_class, pk)

    def get_all(
        self,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """Возвращает список объектов с опциональной сортировкой и пагинацией."""
        query = self.session.query(self.model_class)
        if order_by and hasattr(self.model_class, order_by):
            column = getattr(self.model_class, order_by)
            query = query.order_by(desc(column) if order_desc else asc(column))
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)
        return query.all()

    def get_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        order_by: Optional[str] = None,
        order_desc: bool = False,
    ) -> Dict[str, Any]:
        """Возвращает страницу объектов и общее количество."""
        total = self.count()
        offset = (page - 1) * page_size
        items = self.get_all(
            order_by=order_by,
            order_desc=order_desc,
            limit=page_size,
            offset=offset,
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if page_size else 1,
        }

    def count(self) -> int:
        """Возвращает общее количество записей."""
        pk_column = inspect(self.model_class).primary_key[0]
        return self.session.query(func.count(pk_column)).scalar() or 0

    def create(self, data: Dict[str, Any]) -> T:
        """Создаёт новую запись."""
        instance = self.model_class(**data)
        self.session.add(instance)
        self.session.flush()
        logger.debug("Создан %s pk=%s", self.model_class.__name__, self._pk_value(instance))
        return instance

    def update(self, instance: T, data: Dict[str, Any]) -> T:
        """Обновляет существующую запись."""
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        self.session.flush()
        logger.debug("Обновлён %s pk=%s", self.model_class.__name__, self._pk_value(instance))
        return instance

    def delete(self, instance: T) -> None:
        """Удаляет запись."""
        pk = self._pk_value(instance)
        self.session.delete(instance)
        self.session.flush()
        logger.debug("Удалён %s pk=%s", self.model_class.__name__, pk)

    def _pk_value(self, instance: T) -> Any:
        """Возвращает строковое представление первичного ключа объекта."""
        pk = inspect(instance).identity
        if pk is None:
            return None
        return "_".join(str(v) for v in pk)

    def exists(self, pk: Any) -> bool:
        """Проверяет существование записи по первичному ключу."""
        return self.get_by_id(pk) is not None
