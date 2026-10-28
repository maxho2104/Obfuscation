"""Подключение к базе данных и управление сессиями SQLAlchemy."""

from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base

logger = get_logger("database")


class DatabaseManager:
    """Управляет подключением к БД и жизненным циклом сессий."""

    def __init__(self, db_url: str, app_dir: Optional[Path] = None) -> None:
        self.db_url = db_url
        self.app_dir = app_dir or Path.cwd()
        self.engine = create_engine(
            db_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            future=True,
        )
        self._configure_sqlite()

    def _configure_sqlite(self) -> None:
        """Дополнительная настройка для SQLite: включение внешних ключей."""
        if self.db_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    def create_tables(self) -> None:
        """Создаёт все таблицы, описанные в метаданных ORM."""
        logger.info("Создание таблиц БД при необходимости...")
        Base.metadata.create_all(bind=self.engine)
        logger.info("Таблицы БД готовы")

    def get_session(self) -> Session:
        """Возвращает новую сессию SQLAlchemy."""
        return self.SessionLocal()

    def close(self) -> None:
        """Закрывает пул соединений."""
        self.engine.dispose()
