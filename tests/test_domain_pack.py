"""Тесты пакета предметной области (domain_pack)."""

import json

import pytest

from internal_correspondence.core.domain_pack import (
    DomainPack,
    DomainPackError,
    default_domain_pack,
    enum_code_of,
    enum_codes,
    enum_label,
    enum_labels,
    enum_weight,
    get_domain_pack,
    load_domain_pack,
    set_domain_pack,
)

EXPECTED_ENUMS = {
    "material_type",
    "research_type",
    "evaluation_value",
    "scientific_task_type",
    "telegram_type",
    "telegram_report_type",
    "source_type",
}


@pytest.fixture(autouse=True)
def reset_pack():
    """Сбрасывает активный пакет на дефолтный до и после каждого теста."""
    set_domain_pack(None)
    yield
    set_domain_pack(None)


def _write_pack(tmp_path, data) -> str:
    """Записывает словарь пакета во временный JSON-файл."""
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _minimal_pack(values=None) -> dict:
    """Возвращает минимально валидную структуру пакета."""
    return {
        "id": "test-pack",
        "version": "0.1",
        "enums": {
            "material_type": {
                "label": "Тип",
                "values": values
                or [{"key": "document", "code": "ДОК", "label": "Документ"}],
            }
        },
    }


class TestDefaultPack:
    """Встроенный пакет по умолчанию."""

    def test_loads_and_contains_all_enums(self):
        pack = default_domain_pack()
        assert pack.id == "scientific-network"
        assert pack.version
        assert set(pack.enum_names) == EXPECTED_ENUMS

    def test_labels_match_domain(self):
        pack = default_domain_pack()
        assert pack.label("material_type", "ДОК") == "Документ"
        assert pack.label("telegram_type", "ОХР") == "О ходе работ"
        assert pack.label("source_type", "НТ") == "Научный труд"
        assert pack.label("scientific_task_type", "ОЗ") == "Основная задача"
        assert pack.label("telegram_report_type", "СДР") == "Срочно доложено руководителю"

    def test_unknown_code_falls_back_to_code(self):
        assert default_domain_pack().label("material_type", "НЕТ") == "НЕТ"

    def test_evaluation_weights(self):
        pack = default_domain_pack()
        assert pack.weight("evaluation_value", "Б") == 0
        assert pack.weight("evaluation_value", "И") == 1
        assert pack.weight("evaluation_value", "П") == 2
        assert pack.weight("evaluation_value", "В") == 3

    def test_code_lookup_by_semantic_key(self):
        pack = default_domain_pack()
        assert pack.code_of("material_type", "message") == "С"
        assert pack.code_of("evaluation_value", "important") == "В"


class TestPackValidation:
    """Валидация структуры внешнего пакета."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(DomainPackError, match="не найден"):
            load_domain_pack(tmp_path / "absent.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{не json", encoding="utf-8")
        with pytest.raises(DomainPackError, match="JSON"):
            load_domain_pack(path)

    def test_missing_required_root_fields(self, tmp_path):
        with pytest.raises(DomainPackError, match="'id'"):
            load_domain_pack(_as_path(tmp_path, {"version": "1", "enums": {"x": {}}}))

    def test_duplicate_codes_rejected(self, tmp_path):
        pack = _minimal_pack(
            [
                {"key": "a", "code": "X", "label": "Раз"},
                {"key": "b", "code": "X", "label": "Два"},
            ]
        )
        with pytest.raises(DomainPackError, match="дублируется код"):
            load_domain_pack(_as_path(tmp_path, pack))

    def test_duplicate_keys_rejected(self, tmp_path):
        pack = _minimal_pack(
            [
                {"key": "a", "code": "X", "label": "Раз"},
                {"key": "a", "code": "Y", "label": "Два"},
            ]
        )
        with pytest.raises(DomainPackError, match="дублируется ключ"):
            load_domain_pack(_as_path(tmp_path, pack))

    def test_empty_values_rejected(self, tmp_path):
        pack = {
            "id": "test-pack",
            "version": "0.1",
            "enums": {"material_type": {"label": "Тип", "values": []}},
        }
        with pytest.raises(DomainPackError, match="values"):
            load_domain_pack(_as_path(tmp_path, pack))

    def test_weight_must_be_int(self, tmp_path):
        pack = _minimal_pack(
            [{"key": "a", "code": "X", "label": "Раз", "weight": "много"}]
        )
        with pytest.raises(DomainPackError, match="weight"):
            load_domain_pack(_as_path(tmp_path, pack))


def _as_path(tmp_path, pack: dict):
    """Сохраняет пакет во временный файл и возвращает путь."""
    return _write_pack(tmp_path, pack)


class TestRegistry:
    """Глобальный реестр активного пакета."""

    def test_lazy_default(self):
        assert get_domain_pack().id == "scientific-network"

    def test_module_level_accessors_use_active_pack(self):
        assert enum_label("material_type", "ДОК") == "Документ"
        assert enum_labels("evaluation_value") == {
            "Б": "Бесполезно",
            "И": "Интересно",
            "П": "Полезно",
            "В": "Важно",
        }
        assert enum_codes("source_type") == ["ЭО", "НТ"]
        assert enum_weight("evaluation_value", "П") == 2
        assert enum_code_of("telegram_type", "thematic") == "Т"

    def test_external_pack_replaces_default(self, tmp_path):
        pack = _minimal_pack(
            [{"key": "lecture", "code": "Л", "label": "Лекция"}]
        )
        set_domain_pack(load_domain_pack(_as_path(tmp_path, pack)))
        assert get_domain_pack().id == "test-pack"
        assert enum_label("material_type", "Л") == "Лекция"
        assert enum_codes("material_type") == ["Л"]

    def test_reset_restores_default(self, tmp_path):
        set_domain_pack(load_domain_pack(_as_path(tmp_path, _minimal_pack())))
        set_domain_pack(None)
        assert get_domain_pack().id == "scientific-network"


class TestDeprecatedValues:
    """Устаревшие значения скрыты из выбора, но читаются."""

    def test_deprecated_excluded_from_labels_but_resolved(self, tmp_path):
        pack = _minimal_pack(
            [
                {"key": "new", "code": "Н", "label": "Новый"},
                {"key": "old", "code": "С", "label": "Старый", "deprecated": True},
            ]
        )
        loaded = load_domain_pack(_as_path(tmp_path, pack))
        assert loaded.labels("material_type") == {"Н": "Новый"}
        assert loaded.codes("material_type") == ["Н"]
        # Метка устаревшего кода остаётся доступной для старых записей БД
        assert loaded.label("material_type", "С") == "Старый"


class TestUnknownEnum:
    """Обращение к отсутствующему перечислению."""

    def test_unknown_enum_raises(self):
        with pytest.raises(DomainPackError, match="нет перечисления"):
            get_domain_pack().labels("несуществующее")


class TestEntityLabels:
    """Переопределение меток сущностей и полей пакетом (C2)."""

    @staticmethod
    def _pack_with_entities(tmp_path, entities: dict):
        pack = _minimal_pack()
        pack["entities"] = entities
        return load_domain_pack(_as_path(tmp_path, pack))

    def test_default_pack_mirrors_models(self):
        """Встроенный пакет содержит метки всех сущностей и полей."""
        from internal_correspondence.orm import models

        pack = default_domain_pack()
        assert pack.entity_label("ScientificMaterial") == "Научный материал"
        assert pack.entity_label("Telegram", plural=True) == "Телеграммы"
        assert pack.entity_label_prepositional("Telegram") == "телеграмме"
        info = pack.entity_field_info("ScientificMaterial", "outgoing_number")
        assert info == {"label": "Исходящий номер", "short": "Исх. номер", "required": True}
        assert pack.entity_field_info(models.Branch.__name__, "short_name")["label"]

    def test_pack_overrides_entity_label(self, tmp_path):
        from internal_correspondence.orm.labels import entity_label
        from internal_correspondence.orm.models import ScientificMaterial

        set_domain_pack(
            self._pack_with_entities(
                tmp_path,
                {"ScientificMaterial": {"label": "Курсовая работа",
                                        "label_plural": "Курсовые работы"}},
            )
        )
        assert entity_label(ScientificMaterial) == "Курсовая работа"
        assert entity_label(ScientificMaterial, plural=True) == "Курсовые работы"

    def test_pack_overrides_field_label_and_required(self, tmp_path):
        from internal_correspondence.orm.labels import (
            field_form_label,
            field_label,
            field_required,
        )
        from internal_correspondence.orm.models import ScientificMaterial

        set_domain_pack(
            self._pack_with_entities(
                tmp_path,
                {"ScientificMaterial": {"fields": {
                    "name": {"label": "Тема работы"},
                    "incoming_number": {"label": "Номер зачёта", "required": True},
                }}},
            )
        )
        assert field_label(ScientificMaterial, "name") == "Тема работы"
        assert field_required(ScientificMaterial, "incoming_number") is True
        assert field_form_label(ScientificMaterial, "incoming_number") == "Номер зачёта *:"

    def test_prepositional_override(self, tmp_path):
        from internal_correspondence.orm.labels import entity_label_prepositional
        from internal_correspondence.orm.models import Telegram

        set_domain_pack(
            self._pack_with_entities(
                tmp_path,
                {"Telegram": {"label_prepositional": "рассылке",
                              "label_prepositional_plural": "рассылках"}},
            )
        )
        assert entity_label_prepositional(Telegram) == "рассылке"
        assert entity_label_prepositional(Telegram, plural=True) == "рассылках"

    def test_fallback_to_model_metadata(self, tmp_path):
        """Поля и сущности без переопределения читаются из метаданных моделей."""
        from internal_correspondence.orm.labels import entity_label, field_label
        from internal_correspondence.orm.models import ScientificMaterial

        set_domain_pack(
            self._pack_with_entities(
                tmp_path, {"ScientificMaterial": {"fields": {"name": {"label": "Тема"}}}}
            )
        )
        # Нет переопределения — метка из модели
        assert field_label(ScientificMaterial, "outgoing_number") == "Исходящий номер"
        assert entity_label(ScientificMaterial) == "Научный материал"

    def test_invalid_entity_section_rejected(self, tmp_path):
        pack = _minimal_pack()
        pack["entities"] = {"X": {"label": 42}}
        with pytest.raises(DomainPackError, match="'label'"):
            load_domain_pack(_as_path(tmp_path, pack))
