"""Тесты инструмента переноса русских строк в пакет предметной области.

Инструмент живёт в ``scripts_dev`` и не входит в приложение, поэтому тесты
проверяют его как обычный модуль: классификацию литералов, построение
шаблонов f-строк, добавление импорта и сквозной прогон по временному
проекту.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def extractor():
    """Загружает scripts_dev/extract_pack_strings.py как модуль."""
    spec = importlib.util.spec_from_file_location(
        "extract_pack_strings",
        PROJECT_ROOT / "scripts_dev" / "extract_pack_strings.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sites(extractor, source: str):
    """Собирает вхождения из исходника."""
    tree = ast.parse(source)
    collector = extractor.Collector("probe.py", source)
    collector.visit(tree)
    return collector.sites


def _categories(extractor, source: str):
    """Соответствие «текст → категория» для исходника."""
    return {site.value: site.category for site in _sites(extractor, source)}


# ---------------------------------------------------------------------------
# Категории
# ---------------------------------------------------------------------------


def test_comments_are_ignored(extractor) -> None:
    """Комментарии не попадают в разбор: их нет в AST."""
    source = "# Это комментарий на русском\nx = 1\n"
    assert _sites(extractor, source) == []


def test_docstring_is_skipped(extractor) -> None:
    """Докстринги не переносятся: замена сломала бы ``__doc__``."""
    source = 'def f():\n    """Документация функции."""\n    return 1\n'
    assert _categories(extractor, source)["Документация функции."] == "docstring"


def test_interface_text_inside_function_is_moved(extractor) -> None:
    """Обычный текст в теле функции — кандидат на перенос."""
    source = 'def f():\n    return "Нет данных"\n'
    assert _categories(extractor, source)["Нет данных"] == "text"


def test_module_level_string_is_not_moved(extractor) -> None:
    """Строка уровня модуля вычисляется при импорте и «застынет».

    ``STRINGS`` перезаписывается ``reload_strings()``, поэтому значение,
    взятое при импорте модуля, не обновится при смене пакета.
    """
    source = 'TITLE = "Заголовок окна"\n'
    assert _categories(extractor, source)["Заголовок окна"] == "import_time"


def test_class_body_string_is_not_moved(extractor) -> None:
    """Тело класса исполняется при импорте — тот же запрет."""
    source = 'class A:\n    TITLE = "Заголовок"\n'
    assert _categories(extractor, source)["Заголовок"] == "import_time"


def test_argument_default_is_not_moved(extractor) -> None:
    """Значение по умолчанию вычисляется при импорте."""
    source = 'def f(title="Заголовок"):\n    return title\n'
    assert _categories(extractor, source)["Заголовок"] == "import_time"


def test_short_code_is_skipped(extractor) -> None:
    """Короткие коды перечислений не переносятся."""
    source = 'def f():\n    return "ОЗ"\n'
    assert _categories(extractor, source)["ОЗ"] == "short"


def test_compare_operand_is_skipped(extractor) -> None:
    """Сравнение — разбор данных, а не текст интерфейса."""
    source = 'def f(kind):\n    return kind in ("true", "1", "да")\n'
    assert _categories(extractor, source)["да"] == "short"


def test_log_message_is_skipped(extractor) -> None:
    """Сообщения журнала используют ``%s``, несовместимые с шаблонами."""
    source = 'def f():\n    logger.warning("Пропущен лист %s", name)\n'
    assert _categories(extractor, source)["Пропущен лист %s"] == "log"


def test_exception_text_is_skipped(extractor) -> None:
    """Тексты исключений проверяют тесты — их переносить нельзя."""
    source = 'def f():\n    raise ValueError("Нет данных")\n'
    assert _categories(extractor, source)["Нет данных"] == "exception"


def test_mapping_key_is_skipped(extractor) -> None:
    """Ключи словаря — договорённость о формате данных."""
    source = 'def f():\n    return {"Страны": 1}\n'
    assert _categories(extractor, source)["Страны"] == "mapping_key"


def test_file_name_is_skipped(extractor) -> None:
    """Имя файла — контракт, а не текст интерфейса."""
    source = 'def f():\n    return "Чек-лист.docx"\n'
    assert _categories(extractor, source)["Чек-лист.docx"] == "filename"


def test_sheet_name_is_skipped(extractor) -> None:
    """Имя листа Excel — контракт формата обмена."""
    source = 'def f(path):\n    return _read_sheet_rows(path, "Страны")\n'
    assert _categories(extractor, source)["Страны"] == "sheet_name"


def test_path_segment_is_skipped(extractor) -> None:
    """Сегмент пути хранилища — не текст интерфейса."""
    source = 'def f(storage):\n    return storage / "Импорт"\n'
    assert _categories(extractor, source)["Импорт"] == "path_part"


# ---------------------------------------------------------------------------
# f-строки
# ---------------------------------------------------------------------------


def test_fstring_becomes_named_template(extractor) -> None:
    """f-строка заменяется целиком, подстановки — именованные."""
    template = extractor.build_fstring_template(ast.parse('f"ОЗ — {count} шт."').body[0].value)
    assert template is not None
    text, arguments = template
    assert text == "ОЗ — {name_1} шт."
    assert arguments == ["name_1=count"]


def test_fstring_keeps_placeholder_order(extractor) -> None:
    """Порядок подстановок сохраняется, текст не теряется."""
    template = extractor.build_fstring_template(
        ast.parse('f"Записей: {n}, из них {m}"').body[0].value
    )
    assert template is not None
    text, arguments = template
    assert text == "Записей: {name_1}, из них {name_2}"
    assert arguments == ["name_1=n", "name_2=m"]


def test_fstring_with_format_spec_is_skipped(extractor) -> None:
    """Спецификатор формата шаблон пакета не воспроизведёт."""
    node = ast.parse('f"Итог: {value:.2f} руб."').body[0].value
    assert extractor.build_fstring_template(node) is None


def test_fstring_with_conversion_is_skipped(extractor) -> None:
    """``!r`` тоже не переносится."""
    node = ast.parse('f"Значение: {value!r}"').body[0].value
    assert extractor.build_fstring_template(node) is None


def test_fstring_with_complex_expression_is_skipped(extractor) -> None:
    """Вычисление внутри подстановки в шаблон не превратить."""
    node = ast.parse('f"ОЦ-{maximum + 1:05d}"').body[0].value
    assert extractor.build_fstring_template(node) is None


def test_fstring_without_cyrillic_is_ignored(extractor) -> None:
    """Без русского текста переносить нечего."""
    node = ast.parse('f"{count} items"').body[0].value
    assert extractor.build_fstring_template(node) is None


def test_same_text_with_different_variables_shares_template(extractor) -> None:
    """``f"ОЗ — {x}"`` и ``f"ОЗ — {y}"`` дают один шаблон."""
    first = extractor.build_fstring_template(ast.parse('f"ОЗ — {x}"').body[0].value)
    second = extractor.build_fstring_template(ast.parse('f"ОЗ — {y}"').body[0].value)
    assert first[0] == second[0] == "ОЗ — {name_1}"


# ---------------------------------------------------------------------------
# Правка исходника
# ---------------------------------------------------------------------------


def _write_project(tmp_path: Path, files: dict) -> Path:
    """Создаёт временный проект с пакетом предметной области."""
    (tmp_path / "internal_correspondence" / "utils").mkdir(parents=True)
    (tmp_path / "internal_correspondence" / "core").mkdir(parents=True)
    (tmp_path / "internal_correspondence" / "__init__.py").write_text("", encoding="utf-8")
    strings = tmp_path / "internal_correspondence" / "utils" / "string_resources.py"
    strings.write_text(
        "class AppStrings:\n    pass\n\n\nSTRINGS = AppStrings()\n", encoding="utf-8"
    )
    pack = tmp_path / "internal_correspondence" / "core" / "domain_pack.default.json"
    pack.write_text(
        json.dumps({"id": "test", "version": "1", "strings": {}, "enums": {},
                    "entities": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_apply_replaces_literal_and_adds_import(extractor, tmp_path, monkeypatch) -> None:
    """Литерал заменяется ссылкой, импорт добавляется после последнего."""
    root = _write_project(
        tmp_path,
        {
            "internal_correspondence/gui/widget.py": (
                "from PyQt5.QtWidgets import QWidget\n"
                "\n"
                "\n"
                "class Panel(QWidget):\n"
                "    def label(self):\n"
                '        return "Нет данных"\n'
            )
        },
    )
    monkeypatch.setattr(extractor, "PROJECT_ROOT", root)
    monkeypatch.setattr(extractor, "PACKAGE_DIR", root / "internal_correspondence")
    options = extractor.parse_args(["--root", str(root / "internal_correspondence"),
                                    "--apply", "--quiet"])
    runner = extractor.Extractor(options)
    runner.collect()
    runner.apply()
    updated = (root / "internal_correspondence" / "gui" / "widget.py").read_text(
        encoding="utf-8"
    )
    assert "from internal_correspondence.utils.string_resources import STRINGS" in updated
    assert "STRINGS.text_net_dannykh" in updated
    assert '"Нет данных"' not in updated
    pack = json.loads(
        (root / "internal_correspondence" / "core" / "domain_pack.default.json").read_text(
            encoding="utf-8"
        )
    )
    assert pack["strings"]["text_net_dannykh"] == "Нет данных"


def test_apply_keeps_existing_import(extractor, tmp_path, monkeypatch) -> None:
    """Повторный импорт не добавляется."""
    root = _write_project(
        tmp_path,
        {
            "internal_correspondence/gui/widget.py": (
                "from internal_correspondence.utils.string_resources import STRINGS\n"
                "\n"
                "\n"
                "def label():\n"
                '    return "Нет данных"\n'
            )
        },
    )
    monkeypatch.setattr(extractor, "PROJECT_ROOT", root)
    options = extractor.parse_args(["--root", str(root / "internal_correspondence"),
                                    "--apply", "--quiet"])
    runner = extractor.Extractor(options)
    runner.collect()
    runner.apply()
    updated = (root / "internal_correspondence" / "gui" / "widget.py").read_text(
        encoding="utf-8"
    )
    assert updated.count("string_resources import STRINGS") == 1


def test_apply_skips_pack_and_strings_module(extractor, tmp_path, monkeypatch) -> None:
    """Механизм подстановки и пакет не переписываются."""
    root = _write_project(
        tmp_path,
        {
            "internal_correspondence/core/domain_pack.py": 'X = "Пакет"\n',
            "internal_correspondence/utils/string_resources.py": (
                'X = "Строка"\n\n\nclass AppStrings:\n    pass\n\n\nSTRINGS = AppStrings()\n'
            ),
        },
    )
    monkeypatch.setattr(extractor, "PROJECT_ROOT", root)
    options = extractor.parse_args(["--root", str(root / "internal_correspondence"),
                                    "--apply", "--quiet"])
    runner = extractor.Extractor(options)
    runner.collect()
    assert all(
        not report.path.endswith(("domain_pack.py", "string_resources.py"))
        for report in runner.reports
        if report.applied
    )


def test_check_mode_reports_leftovers(extractor, tmp_path, monkeypatch, capsys) -> None:
    """``--check`` возвращает 1, пока в коде остаётся русский текст."""
    root = _write_project(
        tmp_path,
        {
            "internal_correspondence/gui/widget.py": (
                "def f():\n" '    return "Есть текст"\n'
            )
        },
    )
    monkeypatch.setattr(extractor, "PROJECT_ROOT", root)
    code = extractor.main(["--root", str(root / "internal_correspondence"), "--check"])
    assert code == 1


def test_fstring_replacement_formats_like_original(extractor) -> None:
    """Замена ``f"ОЗ — {count}"`` на шаблон даёт тот же текст."""
    template, arguments = extractor.build_fstring_template(
        ast.parse('f"ОЗ — {count} шт."').body[0].value
    )
    rendered = template.format(name_1=7)
    assert rendered == f"ОЗ — {7} шт."
    assert arguments == ["name_1=count"]
