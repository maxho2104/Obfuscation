"""Управление аватарками элементов ОШС.

Файл аватарки хранится в директории ``Аватарки`` файлового хранилища
(ключ ``avatars`` пакета предметной области) под уникальным именем на
основе идентификатора элемента: ``<тип узла>_<id>.<расширение>``.
Изображение при сохранении приводится к фиксированному размеру 150x200
(обрезка с сохранением пропорций). Путь (имя файла) записывается в колонку
``avatar_file`` соответствующей сущности.
"""

from pathlib import Path
from typing import Optional, Tuple, Type
from uuid import UUID

from PIL import Image
from sqlalchemy.orm import Session

from internal_correspondence.core.domain_pack import dir_name
from internal_correspondence.orm.models import (
    Branch,
    Department,
    Employee,
    WorkingGroup,
)

# Фиксированный размер аватарки, px (ширина x высота)
AVATAR_WIDTH = 150
AVATAR_HEIGHT = 200

# Поддерживаемые форматы исходных изображений
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

# Модели ОШС, для которых доступны аватарки
AVATAR_MODELS: Tuple[Type, ...] = (Branch, Department, WorkingGroup, Employee)


class AvatarError(Exception):
    """Ошибка операции с аватаркой."""

    pass


def avatar_models_map() -> dict:
    """Возвращает отображение «тип узла дерева ОШС -> модель»."""
    return {
        "branch": Branch,
        "department": Department,
        "workgroup": WorkingGroup,
        "employee": Employee,
    }


def _avatar_dir(storage_root: Path) -> Path:
    """Возвращает директорию аватарок хранилища."""
    return storage_root / dir_name("avatars")


def avatar_file_name(node_type: str, node_id: str, extension: str) -> str:
    """Формирует уникальное имя файла аватарки на основе id элемента."""
    ext = extension.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    return f"{node_type}_{node_id}{ext}"


def avatar_path(storage_root: Path, node_type: str, node_id: str, file_name: str) -> Path:
    """Возвращает полный путь файла аватарки в хранилище."""
    return _avatar_dir(storage_root) / file_name


def _resize_cover(source: Path, target: Path) -> None:
    """Приводит изображение к 150x200 обрезкой с сохранением пропорций."""
    try:
        with Image.open(source) as image:
            image = image.convert("RGB")
            src_w, src_h = image.size
            scale = max(AVATAR_WIDTH / src_w, AVATAR_HEIGHT / src_h)
            resized = image.resize(
                (round(src_w * scale), round(src_h * scale)), Image.LANCZOS
            )
            left = (resized.width - AVATAR_WIDTH) // 2
            top = (resized.height - AVATAR_HEIGHT) // 2
            cropped = resized.crop(
                (left, top, left + AVATAR_WIDTH, top + AVATAR_HEIGHT)
            )
            cropped.save(target, format="JPEG", quality=90)
    except AvatarError:
        raise
    except Exception as exc:
        raise AvatarError(f"Не удалось обработать изображение: {exc}") from exc


def _entity_key(model: Type, node_id: str):
    """Приводит строковый id узла к типу первичного ключа модели."""
    if model is Branch:
        return node_id
    return UUID(node_id)


def save_avatar(
    session: Session,
    storage_root: Path,
    node_type: str,
    node_id: str,
    source_path: Path,
) -> str:
    """Сохраняет аватарку элемента из файла. Возвращает имя файла."""
    model = avatar_models_map().get(node_type)
    if model is None:
        raise AvatarError(f"Аватарки не поддерживаются для узла '{node_type}'")
    extension = source_path.suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        raise AvatarError(f"Неподдерживаемый формат изображения: {extension}")

    target_dir = _avatar_dir(storage_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = avatar_file_name(node_type, node_id, extension)
    target = target_dir / file_name
    # Имя фиксировано: перед записью убираем прежний файл с другим расширением
    remove_avatar_file(storage_root, node_type, node_id)
    _resize_cover(source_path, target)

    entity = session.get(model, _entity_key(model, node_id))
    if entity is None:
        target.unlink(missing_ok=True)
        raise AvatarError("Элемент не найден в базе данных")
    entity.avatar_file = file_name
    session.commit()
    return file_name


def remove_avatar_file(storage_root: Path, node_type: str, node_id: str) -> None:
    """Удаляет файл(ы) аватарки элемента из хранилища (без правки БД)."""
    directory = _avatar_dir(storage_root)
    if not directory.exists():
        return
    prefix = f"{node_type}_{node_id}."
    for path in directory.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            path.unlink(missing_ok=True)


def remove_avatar(
    session: Session, storage_root: Path, node_type: str, node_id: str
) -> None:
    """Удаляет аватарку элемента: файл из хранилища и запись в БД."""
    model = avatar_models_map().get(node_type)
    if model is None:
        raise AvatarError(f"Аватарки не поддерживаются для узла '{node_type}'")
    entity = session.get(model, _entity_key(model, node_id))
    if entity is None:
        raise AvatarError("Элемент не найден в базе данных")
    remove_avatar_file(storage_root, node_type, node_id)
    entity.avatar_file = None
    session.commit()


def resolve_avatar(
    storage_root: Path, node_type: str, node_id: str, file_name: Optional[str]
) -> Optional[Path]:
    """Возвращает путь файла аватарки или None (выводится заглушка)."""
    if not file_name:
        return None
    path = _avatar_dir(storage_root) / file_name
    return path if path.is_file() else None
