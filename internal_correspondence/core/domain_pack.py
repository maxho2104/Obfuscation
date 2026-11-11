"""Пакет предметной области: коды, метки и веса перечислений.

Бизнес-логика оперирует семантическими ключами и кодами перечислений,
а их отображаемые значения (метки, веса оценок) определяются внешним
JSON-пакетом. Это позволяет менять предметную терминологию приложения
без изменения кода: достаточно подключить другой файл пакета.

Правила совместимости:
- ``code`` — неизменяемый идентификатор значения, хранится в БД и в
  экспортных файлах; менять коды нельзя, устаревшие значения помечаются
  ``deprecated`` и скрываются из выбора, но остаются читаемыми;
- у пакета есть ``id`` и ``version`` для контроля совместимости при
  обмене между филиалом и головным офисом.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from internal_correspondence.core.logging_config import get_logger

logger = get_logger("domain_pack")

# Путь к встроенному пакету по умолчанию (фолбэк при отсутствии внешнего)
DEFAULT_PACK_PATH = Path(__file__).with_name("domain_pack.default.json")


class DomainPackError(ValueError):
    """Ошибка структуры или содержимого пакета предметной области."""


@dataclass(frozen=True)
class EnumValue:
    """Значение перечисления: семантический ключ, код в БД, метка."""

    key: str
    code: str
    label: str
    weight: Optional[int] = None
    deprecated: bool = False


@dataclass
class EnumDef:
    """Описание одного перечисления предметной области."""
    name: str
    label: str
    values: List[EnumValue] = field(default_factory=list)

    def active(self) -> List[EnumValue]:
        """Возвращает действующие (не устаревшие) значения."""
        return [value for value in self.values if not value.deprecated]

    def labels(self) -> Dict[str, str]:
        """Возвращает отображение {код: метка} действующих значений."""
        return {value.code: value.label for value in self.active()}

    def codes(self) -> List[str]:
        """Возвращает коды действующих значений в порядке объявления."""
        return [value.code for value in self.active()]

    def label_of(self, code: str) -> str:
        """Возвращает метку кода; неизвестный код отображается как есть."""
        for value in self.values:
            if value.code == code:
                return value.label
        return code

    def weight_of(self, code: str) -> Optional[int]:
        """Возвращает весовой коэффициент кода (если задан)."""
        for value in self.values:
            if value.code == code:
                return value.weight
        return None

    def code_of(self, key: str) -> str:
        """Возвращает код по семантическому ключу."""
        for value in self.values:
            if value.key == key:
                return value.code
        raise DomainPackError(
            f"В перечислении '{self.name}' нет значения с ключом '{key}'"
        )

    def to_dict(self) -> dict:
        """Сериализует перечисление в структуру файла пакета."""
        values = []
        for value in self.values:
            item: Dict[str, Any] = {
                "key": value.key,
                "code": value.code,
                "label": value.label,
            }
            if value.weight is not None:
                item["weight"] = value.weight
            if value.deprecated:
                item["deprecated"] = True
            values.append(item)
        return {"label": self.label, "values": values}


@dataclass
class EntityDef:
    """Метки сущности и её полей, переопределяющие встроенные."""

    name: str
    label: Optional[str] = None
    label_plural: Optional[str] = None
    label_prepositional: Optional[str] = None
    label_prepositional_plural: Optional[str] = None
    fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def field_info(self, field_name: str) -> Dict[str, Any]:
        """Возвращает переопределённые метаданные поля или пустой словарь."""
        return dict(self.fields.get(field_name, {}))

    def to_dict(self) -> dict:
        """Сериализует метки сущности в структуру файла пакета."""
        data: Dict[str, Any] = {}
        for attr in (
            "label",
            "label_plural",
            "label_prepositional",
            "label_prepositional_plural",
        ):
            value = getattr(self, attr)
            if value is not None:
                data[attr] = value
        if self.fields:
            data["fields"] = {name: dict(info) for name, info in self.fields.items()}
        return data


# Имена служебных директорий по умолчанию (ключ -> имя каталога)
DEFAULT_DIRECTORIES: Dict[str, str] = {
    "files": "Файлы",
    "templates": "Шаблоны",
    "export": "Экспорт",
    "material_files": "Научные материалы",
    "telegram_files": "Телеграммы",
}


class DomainPack:
    """Пакет предметной области: именованный набор перечислений."""

    def __init__(
        self,
        pack_id: str,
        version: str,
        enums: Dict[str, EnumDef],
        entities: Optional[Dict[str, EntityDef]] = None,
        directories: Optional[Dict[str, str]] = None,
        strings: Optional[Dict[str, str]] = None,
    ) -> None:
        self.id = pack_id
        self.version = version
        self._enums = enums
        self._entities = entities or {}
        self._directories = directories or {}
        self._strings = strings or {}

    @property
    def enum_names(self) -> List[str]:
        """Возвращает имена перечислений пакета."""
        return list(self._enums)

    @property
    def entity_names(self) -> List[str]:
        """Возвращает имена сущностей, описанных в пакете."""
        return list(self._entities)

    def enum(self, name: str) -> EnumDef:
        """Возвращает перечисление по имени или выбрасывает ошибку."""
        try:
            return self._enums[name]
        except KeyError:
            raise DomainPackError(
                f"В пакете '{self.id}' нет перечисления '{name}'"
            ) from None

    def labels(self, name: str) -> Dict[str, str]:
        """Отображение {код: метка} для перечисления."""
        return self.enum(name).labels()

    def label(self, name: str, code: str) -> str:
        """Метка кода перечисления с фолбэком на сам код."""
        return self.enum(name).label_of(code)

    def codes(self, name: str) -> List[str]:
        """Коды действующих значений перечисления."""
        return self.enum(name).codes()

    def weight(self, name: str, code: str) -> Optional[int]:
        """Весовой коэффициент кода перечисления."""
        return self.enum(name).weight_of(code)

    def code_of(self, name: str, key: str) -> str:
        """Код значения по семантическому ключу."""
        return self.enum(name).code_of(key)

    # ------------------------------------------------------------------
    # Метки сущностей и полей
    # ------------------------------------------------------------------

    def entity(self, name: str) -> Optional[EntityDef]:
        """Возвращает описание сущности или None, если её нет в пакете."""
        return self._entities.get(name)

    def entity_label(self, name: str, plural: bool = False) -> Optional[str]:
        """Метка сущности из пакета (None — нет переопределения)."""
        entity = self._entities.get(name)
        if entity is None:
            return None
        if plural:
            return entity.label_plural or entity.label
        return entity.label

    def entity_label_prepositional(
        self, name: str, plural: bool = False
    ) -> Optional[str]:
        """Предложная форма метки сущности (None — нет переопределения)."""
        entity = self._entities.get(name)
        if entity is None:
            return None
        if plural:
            return entity.label_prepositional_plural or entity.label_prepositional
        return entity.label_prepositional

    def entity_field_info(self, entity_name: str, field_name: str) -> Dict[str, Any]:
        """Переопределённые метаданные поля сущности ({} — нет)."""
        entity = self._entities.get(entity_name)
        if entity is None:
            return {}
        return entity.field_info(field_name)

    # ------------------------------------------------------------------
    # Директории и строки интерфейса
    # ------------------------------------------------------------------

    def directory(self, key: str) -> str:
        """Имя служебной директории с фолбэком на встроенное."""
        return self._directories.get(key, DEFAULT_DIRECTORIES.get(key, key))

    def strings(self) -> Dict[str, str]:
        """Переопределённые строки интерфейса (ключ -> текст)."""
        return dict(self._strings)

    def to_dict(self) -> dict:
        """Сериализует пакет в структуру JSON-файла."""
        data: Dict[str, Any] = {
            "id": self.id,
            "version": self.version,
            "enums": {name: enum.to_dict() for name, enum in self._enums.items()},
        }
        if self._entities:
            data["entities"] = {
                name: entity.to_dict() for name, entity in self._entities.items()
            }
        if self._directories:
            data["directories"] = dict(self._directories)
        if self._strings:
            data["strings"] = dict(self._strings)
        return data

    @classmethod
    def from_dict(cls, data: dict, source: str = "<данные>") -> "DomainPack":
        """Строит пакет из словаря с валидацией структуры."""
        if not isinstance(data, dict):
            raise DomainPackError(f"{source}: корень пакета должен быть объектом")

        pack_id = data.get("id")
        version = data.get("version")
        enums_data = data.get("enums")
        if not pack_id or not isinstance(pack_id, str):
            raise DomainPackError(f"{source}: отсутствует строковое поле 'id'")
        if not version or not isinstance(version, str):
            raise DomainPackError(f"{source}: отсутствует строковое поле 'version'")
        if not isinstance(enums_data, dict) or not enums_data:
            raise DomainPackError(f"{source}: отсутствует непустой объект 'enums'")

        enums: Dict[str, EnumDef] = {}
        for enum_name, enum_data in enums_data.items():
            enums[enum_name] = cls._parse_enum(enum_name, enum_data, source)

        entities_data = data.get("entities", {})
        if not isinstance(entities_data, dict):
            raise DomainPackError(f"{source}: поле 'entities' должно быть объектом")
        entities: Dict[str, EntityDef] = {}
        for entity_name, entity_data in entities_data.items():
            entities[entity_name] = cls._parse_entity(entity_name, entity_data, source)

        directories = cls._parse_str_dict(data, "directories", source)
        strings = cls._parse_str_dict(data, "strings", source)
        return cls(pack_id, version, enums, entities, directories, strings)

    @staticmethod
    def _parse_str_dict(data: dict, key: str, source: str) -> Dict[str, str]:
        """Разбирает опциональную секцию словаря строк."""
        section = data.get(key, {})
        if not isinstance(section, dict):
            raise DomainPackError(f"{source}: поле '{key}' должно быть объектом")
        result: Dict[str, str] = {}
        for entry_key, value in section.items():
            if not isinstance(value, str):
                raise DomainPackError(
                    f"{source}: '{key}.{entry_key}' должно быть строкой"
                )
            result[str(entry_key)] = value
        return result

    @staticmethod
    def _parse_entity(entity_name: str, entity_data: dict, source: str) -> EntityDef:
        """Разбирает и валидирует описание сущности пакета."""
        where = f"{source}: сущность '{entity_name}'"
        if not isinstance(entity_data, dict):
            raise DomainPackError(f"{where}: описание должно быть объектом")

        def optional_str(key: str) -> Optional[str]:
            value = entity_data.get(key)
            if value is not None and not isinstance(value, str):
                raise DomainPackError(f"{where}: поле '{key}' должно быть строкой")
            return value

        fields_data = entity_data.get("fields", {})
        if not isinstance(fields_data, dict):
            raise DomainPackError(f"{where}: поле 'fields' должно быть объектом")
        fields: Dict[str, Dict[str, Any]] = {}
        for field_name, field_meta in fields_data.items():
            entry = f"{where}, поле '{field_name}'"
            if not isinstance(field_meta, dict):
                raise DomainPackError(f"{entry}: метаданные должны быть объектом")
            for key in ("label", "short"):
                if key in field_meta and not isinstance(field_meta[key], str):
                    raise DomainPackError(f"{entry}: '{key}' должно быть строкой")
            if "required" in field_meta and not isinstance(field_meta["required"], bool):
                raise DomainPackError(f"{entry}: 'required' должно быть логическим")
            fields[field_name] = dict(field_meta)

        return EntityDef(
            name=entity_name,
            label=optional_str("label"),
            label_plural=optional_str("label_plural"),
            label_prepositional=optional_str("label_prepositional"),
            label_prepositional_plural=optional_str("label_prepositional_plural"),
            fields=fields,
        )

    @staticmethod
    def _parse_enum(enum_name: str, enum_data: dict, source: str) -> EnumDef:
        """Разбирает и валидирует одно перечисление пакета."""
        where = f"{source}: перечисление '{enum_name}'"
        if not isinstance(enum_data, dict):
            raise DomainPackError(f"{where}: описание должно быть объектом")
        values_data = enum_data.get("values")
        if not isinstance(values_data, list) or not values_data:
            raise DomainPackError(f"{where}: отсутствует непустой список 'values'")

        values: List[EnumValue] = []
        seen_keys = set()
        seen_codes = set()
        for index, item in enumerate(values_data):
            entry = f"{where}, значение #{index + 1}"
            if not isinstance(item, dict):
                raise DomainPackError(f"{entry}: значение должно быть объектом")
            key, code, label = item.get("key"), item.get("code"), item.get("label")
            if not key or not isinstance(key, str):
                raise DomainPackError(f"{entry}: отсутствует строковое поле 'key'")
            if not code or not isinstance(code, str):
                raise DomainPackError(f"{entry}: отсутствует строковое поле 'code'")
            if not label or not isinstance(label, str):
                raise DomainPackError(f"{entry}: отсутствует строковое поле 'label'")
            weight = item.get("weight")
            if weight is not None and not isinstance(weight, int):
                raise DomainPackError(f"{entry}: поле 'weight' должно быть целым")
            if key in seen_keys:
                raise DomainPackError(f"{entry}: дублируется ключ '{key}'")
            if code in seen_codes:
                raise DomainPackError(f"{entry}: дублируется код '{code}'")
            seen_keys.add(key)
            seen_codes.add(code)
            values.append(
                EnumValue(
                    key=key,
                    code=code,
                    label=label,
                    weight=weight,
                    deprecated=bool(item.get("deprecated", False)),
                )
            )

        return EnumDef(
            name=enum_name,
            label=str(enum_data.get("label", enum_name)),
            values=values,
        )


def load_domain_pack(path: Path) -> DomainPack:
    """Загружает пакет предметной области из JSON-файла."""
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise DomainPackError(f"Файл пакета не найден: {path}") from None
    except json.JSONDecodeError as exc:
        raise DomainPackError(f"Файл пакета {path} не является JSON: {exc}") from None
    return DomainPack.from_dict(data, source=str(path))


def default_domain_pack() -> DomainPack:
    """Возвращает встроенный пакет по умолчанию."""
    return load_domain_pack(DEFAULT_PACK_PATH)


def save_domain_pack(pack: DomainPack, path: Path) -> Path:
    """Сохраняет пакет предметной области в JSON-файл."""
    path = Path(path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(pack.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    logger.info("Пакет предметной области сохранён: %s", path)
    return path


# -----------------------------------------------------------------------------
# Глобальный реестр активного пакета
# -----------------------------------------------------------------------------

_current_pack: Optional[DomainPack] = None


def get_domain_pack() -> DomainPack:
    """Возвращает активный пакет, лениво инициализируя дефолтный."""
    global _current_pack
    if _current_pack is None:
        _current_pack = default_domain_pack()
        logger.info(
            "Загружен пакет предметной области по умолчанию: %s v%s",
            _current_pack.id,
            _current_pack.version,
        )
    return _current_pack


def set_domain_pack(pack: Optional[DomainPack]) -> None:
    """Устанавливает активный пакет (None — сброс на дефолтный)."""
    global _current_pack
    _current_pack = pack


def init_domain_pack(path: Optional[Path] = None) -> DomainPack:
    """Инициализирует активный пакет из внешнего файла или дефолтного."""
    global _current_pack
    if path:
        _current_pack = load_domain_pack(Path(path))
        logger.info(
            "Загружен внешний пакет предметной области: %s v%s (%s)",
            _current_pack.id,
            _current_pack.version,
            path,
        )
    else:
        _current_pack = default_domain_pack()
        logger.info(
            "Загружен пакет предметной области по умолчанию: %s v%s",
            _current_pack.id,
            _current_pack.version,
        )
    return _current_pack


# -----------------------------------------------------------------------------
# Удобные функции доступа к активному пакету
# -----------------------------------------------------------------------------

def enum_labels(name: str) -> Dict[str, str]:
    """Отображение {код: метка} действующих значений перечисления."""
    return get_domain_pack().labels(name)


def enum_label(name: str, code: str) -> str:
    """Метка кода перечисления с фолбэком на сам код."""
    return get_domain_pack().label(name, code)


def enum_codes(name: str) -> List[str]:
    """Коды действующих значений перечисления."""
    return get_domain_pack().codes(name)


def enum_weight(name: str, code: str) -> Optional[int]:
    """Весовой коэффициент кода перечисления."""
    return get_domain_pack().weight(name, code)


def enum_code_of(name: str, key: str) -> str:
    """Код значения по семантическому ключу."""
    return get_domain_pack().code_of(name, key)


def dir_name(key: str) -> str:
    """Имя служебной директории с учётом активного пакета."""
    return get_domain_pack().directory(key)
