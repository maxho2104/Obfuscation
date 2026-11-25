"""Управление аватарками элементов ОШС.

Аватарка хранится в директории ``Аватарки`` файлового хранилища
(ключ ``avatars`` пакета предметной области) под детерминированным именем,
однозначно определяемым данными элемента:
``<тип узла>_<наименование>_<первые 8 символов id>.jpg``.
Запись в базе данных не ведётся: файл находится по соглашению об именовании.
При добавлении изображение переносится (move) из указанного места в
хранилище и приводится к фиксированному размеру 150x200
(обрезка с сохранением пропорций).
"""

import re
from pathlib import Path
from typing import Optional, Tuple, Type

from PIL import Image

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

# Длина хвоста id в имени файла (однозначность при совпадении наименований)
_ID_TAIL_LENGTH = 8

_FILE_NAME_FORBIDDEN = re.compile(r"[^\w\-]+", re.UNICODE)


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


def _sanitize_label(label: str) -> str:
    """Приводит человекочитаемую часть имени к допустимой в имени файла."""
    cleaned = _FILE_NAME_FORBIDDEN.sub("_", label).strip("_")
    return cleaned or "element"


def avatar_label(entity, node_type: str) -> str:
    """Возвращает человекочитаемую часть имени аватарки по данным элемента."""
    if node_type == "employee":
        return entity.display_name()
    if node_type == "branch":
        return entity.short_name or entity.id
    return entity.name


def avatar_file_name(entity, node_type: str) -> str:
    """Формирует однозначно интерпретируемое имя файла аватарки.

    ``<тип узла>_<наименование>_<хвост id>.jpg`` — по имени файла видно,
    аватарка какого элемента перед нами; хвост id устраняет коллизии
    одноимённых элементов.
    """
    label = _sanitize_label(avatar_label(entity, node_type))
    id_tail = str(entity.id).replace("-", "")[:_ID_TAIL_LENGTH]
    return f"{node_type}_{label}_{id_tail}.jpg"


def avatar_path(storage_root: Path, entity, node_type: str) -> Path:
    """Возвращает полный путь файла аватарки в хранилище."""
    return _avatar_dir(storage_root) / avatar_file_name(entity, node_type)


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


def save_avatar(entity, node_type: str, storage_root: Path, source_path: Path) -> Path:
    """Переносит изображение в хранилище как аватарку элемента.

    Исходный файл удаляется (перенос). Возвращает путь сохранённого файла.
    """
    if node_type not in avatar_models_map():
        raise AvatarError(f"Аватарки не поддерживаются для узла '{node_type}'")
    extension = source_path.suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        raise AvatarError(f"Неподдерживаемый формат изображения: {extension}")

    target_dir = _avatar_dir(storage_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = avatar_path(storage_root, entity, node_type)
    source_resolved = source_path.resolve()
    target_resolved = target.resolve()
    _resize_cover(source_path, target)
    if source_resolved != target_resolved:
        source_path.unlink(missing_ok=True)
    return target


def remove_avatar(entity, node_type: str, storage_root: Path) -> None:
    """Удаляет файл аватарки элемента из хранилища."""
    avatar_path(storage_root, entity, node_type).unlink(missing_ok=True)


def resolve_avatar(
    storage_root: Path, entity, node_type: str
) -> Optional[Path]:
    """Возвращает путь файла аватарки или None (выводится заглушка)."""
    path = avatar_path(storage_root, entity, node_type)
    return path if path.is_file() else None
