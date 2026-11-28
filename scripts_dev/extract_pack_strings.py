"""Извлечение русских строк из кода в пакет предметной области.

Модуль не входит в состав приложения и предназначен для обслуживания кода:
он проходит по каталогу ``internal_correspondence``, находит строковые
литералы с русскими буквами и переносит их в секцию ``strings`` пакета
``core/domain_pack.default.json``. В коде литерал заменяется обращением к
``STRINGS.<ключ>`` из ``utils/string_resources.py``, поэтому исходный текст
подставляется обратно через активный пакет предметной области
(``core/domain_pack.py``) и может быть переопределён без правки кода.

Что считается «строкой интерфейса»

* обычные строковые литералы в теле функций и методов;
* текстовые части f-строк: каждая часть заменяется на ``{STRINGS.ключ}``,
  сама f-строка сохраняется, поэтому порядок слов и подстановки не меняются;
* строки, собранные неявной конкатенацией, — заменяется литерал целиком.

Что пропускается

Комментарии не рассматриваются вовсе: их нет в AST.

По умолчанию не переносятся (каждую группу можно включить отдельным флагом):

* ``docstring`` — докстринги модулей, классов и функций: это документация
  кода, замена сломала бы ``__doc__``;
* ``statement`` — строка-оператор без присваивания;
* ``short`` — литерал не длиннее двух символов (``"Б"``, ``"ОЗ"``, ``"да"``):
  это, как правило, коды перечислений и ключи словарей, они сравниваются
  в коде и не должны зависеть от пакета;
* ``compare`` — операнд сравнения или проверки вхождения (``value in
  ("true", "да")``): это разбор входных данных, а не текст интерфейса;
* ``mapping_key`` — ключ словаря или аргумент ``.get("…")``: договорённость
  о формате данных (заголовки листов Excel, ключи конфигурации);
* ``log`` — сообщения журналирования: в них ``%s``-подстановки, несовместимые
  с шаблонами пакета ``{name}``;
* ``exception`` — тексты исключений: их проверяют тесты;
* ``import_time`` — строки, вычисляемые при импорте (значения по умолчанию
  аргументов, тела классов, константы уровня модуля): ``STRINGS``
  перезаписывается при смене пакета, поэтому такие значения «застыли» бы на
  момент импорта;
* ``orm_label`` — ``info={"label": ...}``: метки моделей ведутся через секцию
  ``entities`` пакета (см. ``orm/labels.py``).

Запуск (по умолчанию только отчёт, файлы не меняются)::

    .venv/Scripts/python.exe scripts_dev/extract_pack_strings.py

Показать все пропущенные вхождения с причиной::

    .venv/Scripts/python.exe scripts_dev/extract_pack_strings.py --show-skipped

Применить изменения::

    .venv/Scripts/python.exe scripts_dev/extract_pack_strings.py --apply

Проверить, что русских строк в коде не осталось (код возврата 1, если есть)::

    .venv/Scripts/python.exe scripts_dev/extract_pack_strings.py --check

Модуль использует только стандартную библиотеку и разбирает исходники через
``ast``, поэтому ему не нужны ни PyQt5, ни SQLAlchemy.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PACK_PATH = Path("internal_correspondence/core/domain_pack.default.json")
STRINGS_PATH = Path("internal_correspondence/utils/string_resources.py")
PACKAGE_DIR = Path("internal_correspondence")

#: Файлы, которые нельзя переписывать: сам механизм подстановки строк и пакет.
ALWAYS_SKIP = {
    "internal_correspondence/core/domain_pack.py",
    "internal_correspondence/core/domain_pack.default.json",
    "internal_correspondence/utils/string_resources.py",
    # string_resources импортирует logging_config — обратный импорт дал бы цикл
    "internal_correspondence/core/logging_config.py",
}

STRINGS_IMPORT = "from internal_correspondence.utils.string_resources import STRINGS"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHORT_TEXT_LENGTH = 2

#: Слова-значения: используются и для показа, и для разбора входных данных
#: (``value.lower() in ("true", "1", "да")``). Переносить их поодиночке нельзя:
#: пара «Да»/«Нет» распалась бы, потому что короткое слово пропускается, а
#: длинное переносится. Поэтому оба считаются данными, а не текстом.
VALUE_WORDS = {"да", "нет", "истина", "ложь"}

#: Предлоги и союзы: сами по себе не дают осмысленного имени ключа.
FUNCTION_WORDS = {
    "в", "во", "на", "от", "до", "из", "за", "по", "к", "ко", "с", "со",
    "о", "об", "обо", "при", "для", "без", "через", "над", "под", "про",
    "и", "а", "но", "или", "либо", "то", "же", "не", "ни",
}

#: Расширения файлов: литерал с ними — часть имени файла, а не текст интерфейса.
FILE_EXTENSIONS = (
    "xlsx", "xls", "docx", "doc", "json", "csv", "txt", "zip", "pdf",
    "png", "jpg", "jpeg", "ini", "log", "bak", "rtf", "odt",
)
FILE_EXTENSION_RE = re.compile(
    r"\.(" + "|".join(FILE_EXTENSIONS) + r")$", re.IGNORECASE
)
#: Функции, аргументы которых — имена листов книги Excel.
SHEET_FUNCTION_HINTS = ("sheet", "read_sheet", "worksheet")

LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "fatal",
    "log",
    "print",
}

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

KEY_PREFIX = "text_"
KEY_MAX_LENGTH = 56

#: Категории, которые по умолчанию не переносятся, и флаги их включения.
SKIP_FLAGS = {
    "docstring": None,
    "statement": None,
    "short": None,
    "compare": "include_data_keys",
    "mapping_key": "include_data_keys",
    "fstring": None,
    "filename": None,
    "path_part": None,
    "sheet_name": None,
    "log": "include_logs",
    "exception": "include_exceptions",
    "import_time": "include_import_time",
    "orm_label": "include_orm_labels",
}

CATEGORY_TITLES = {
    "text": "текст интерфейса",
    "docstring": "докстринг",
    "statement": "строка-оператор",
    "short": "короткий код или слово",
    "compare": "операнд сравнения",
    "mapping_key": "ключ словаря или .get()",
    "fstring": "f-строка со сложными выражениями",
    "filename": "часть имени файла",
    "path_part": "часть пути",
    "sheet_name": "имя листа Excel",
    "log": "сообщение журнала",
    "exception": "текст исключения",
    "import_time": "вычисляется при импорте",
    "orm_label": "метка модели info={'label'}",
}


# ---------------------------------------------------------------------------
# Ключи и транслитерация
# ---------------------------------------------------------------------------


def transliterate(text: str) -> str:
    """Переводит русский текст в латиницу для имени ключа пакета."""
    chunks: List[str] = []
    for char in text:
        lower = char.lower()
        if lower in TRANSLIT:
            chunks.append(TRANSLIT[lower])
        elif char.isascii() and (char.isalnum() or char == "_"):
            chunks.append(char.lower())
        else:
            chunks.append("_")
    result = "".join(chunks)
    result = re.sub(r"_+", "_", result).strip("_")
    return result


class KeyRegistry:
    """Выдаёт стабильные ключи пакета и знает уже существующие строки."""

    def __init__(self, existing: Dict[str, str], reuse: bool = True) -> None:
        self._existing = dict(existing)
        self._reuse = reuse
        self._by_value: Dict[str, str] = {}
        if reuse:
            counts: Dict[str, List[str]] = {}
            for key, value in self._existing.items():
                counts.setdefault(value, []).append(key)
            # переиспользуем только однозначные совпадения, чтобы не связать
            # несвязанные места кода общим ключом
            for value, keys in counts.items():
                if len(keys) == 1:
                    self._by_value[value] = keys[0]
        self._new: Dict[str, str] = {}
        self.reused: Dict[str, str] = {}

    @property
    def new_keys(self) -> Dict[str, str]:
        """Добавленные ключи в порядке появления (ключ -> текст)."""
        return dict(self._new)

    def key_for(self, value: str, hint: str = "") -> str:
        """Возвращает ключ пакета для текста, создавая его при необходимости."""
        if value in self._by_value:
            key = self._by_value[value]
            if key in self._existing:
                self.reused[value] = key
            return key
        if value in self._new.values():
            for key, created in self._new.items():
                if created == value:
                    return key
        base = KEY_PREFIX + (transliterate(hint or value) or "string")
        base = base[:KEY_MAX_LENGTH].strip("_") or KEY_PREFIX + "string"
        if not IDENTIFIER_RE.match(base):
            base = KEY_PREFIX + "string"
        key = base
        counter = 2
        while key in self._existing or key in self._new:
            key = f"{base}_{counter}"
            counter += 1
        self._new[key] = value
        return key


# ---------------------------------------------------------------------------
# Разбор исходников
# ---------------------------------------------------------------------------


@dataclass
class Site:
    """Одно найденное вхождение русского текста."""

    path: str
    lineno: int
    end_lineno: int
    col: int
    end_col: int
    value: str
    category: str
    snippet: str
    function: str = ""
    in_fstring: bool = False
    arguments: List[str] = field(default_factory=list)
    key: str = ""
    replacement: str = ""

    @property
    def skipped(self) -> bool:
        """Вхождение оставлено без замены."""
        return not self.replacement


@dataclass
class FileReport:
    """Итоги разбора одного файла."""

    path: str
    sites: List[Site] = field(default_factory=list)

    @property
    def applied(self) -> List[Site]:
        """Вхождения, которые будут заменены."""
        return [site for site in self.sites if site.replacement]

    @property
    def skipped(self) -> List[Site]:
        """Вхождения, оставленные без изменений."""
        return [site for site in self.sites if not site.replacement]


def _owner_of_string(node: ast.AST, parents: Sequence[ast.AST]) -> Optional[ast.AST]:
    """Возвращает ближайший родительский оператор или модуль."""
    for parent in reversed(parents[:-1]):
        if isinstance(parent, (ast.stmt, ast.Module)):
            return parent
    return None


def _is_docstring(node: ast.AST, parents: Sequence[ast.AST]) -> bool:
    """Проверяет, что узел — докстринг модуля, класса или функции."""
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for parent in reversed(parents[:-1]):
        if not isinstance(parent, owners):
            continue
        body = getattr(parent, "body", [])
        if not body:
            return False
        first = body[0]
        return isinstance(first, ast.Expr) and first.value is node
    return False


def _is_statement_string(node: ast.AST, parents: Sequence[ast.AST]) -> bool:
    """Строка — самостоятельный оператор, а не значение выражения."""
    if not parents:
        return False
    parent = parents[-2] if len(parents) >= 2 else None
    return isinstance(parent, ast.Expr)


def _call_name(node: ast.Call) -> str:
    """Имя вызываемой функции (для методов — только имя метода)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_exception_call(node: ast.Call) -> bool:
    """Похоже ли вызываемое на исключение (``SomeError(...)``)."""
    name = _call_name(node)
    return name.endswith(("Error", "Exception", "Warning"))


def _simple_expression(node: ast.AST) -> Optional[str]:
    """Текст выражения f-строки без подстановки, если он безопасен.

    Возвращает исходное выражение (``count``, ``item.name``, ``value``) для
    случаев, когда его можно передать аргументом ``str.format``. Спецификаторы
    формата (``:.2f``), преобразования (``!r``) и вычисления (``len(a)``)
    вернут ``None``: шаблон пакета их не воспроизведёт.
    """
    if isinstance(node, ast.Constant):
        return str(node.value) if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _simple_expression(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _placeholder_name(index: int) -> str:
    """Имя плейсхолдера по порядковому номеру подстановки: ``name_1``."""
    return f"name_{index}"


def build_fstring_template(node: ast.JoinedStr) -> Optional[Tuple[str, List[str]]]:
    """Превращает f-строку в шаблон пакета и список аргументов ``format``.

    ``f"ОЗ — {count} шт."`` даёт
    ``("ОЗ — {name_1} шт.", ["name_1=count"])``.

    Имена позиционные (``name_1``, ``name_2``), а не выведенные из выражения:
    ``f"ОЗ — {x}"`` и ``f"ОЗ — {y}"`` должны дать один и тот же шаблон и один
    ключ пакета, иначе одинаковый текст пришлось бы переводить дважды.
    Порядок при этом сохраняется: переводчик может переставить плейсхолдеры,
    не ломая подстановку.

    ``None`` означает, что строку нельзя вынести в пакет без искажения
    подстановок (спецификатор формата, ``!r`` или сложное выражение).
    """
    chunks: List[str] = []
    arguments: List[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            if isinstance(value.value, str):
                chunks.append(value.value)
            continue
        if isinstance(value, ast.FormattedValue):
            if value.conversion not in (-1, None) or value.format_spec is not None:
                return None
            expression = _simple_expression(value.value)
            if expression is None:
                return None
            name = _placeholder_name(len(arguments) + 1)
            chunks.append("{" + name + "}")
            arguments.append(f"{name}={expression}")
            continue
        return None
    text = "".join(chunks)
    if not CYRILLIC_RE.search(text):
        return None
    return text, arguments


class Collector(ast.NodeVisitor):
    """Обходит дерево и собирает русские литералы с контекстом."""

    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.source = source
        self.sites: List[Site] = []
        self._parents: List[ast.AST] = []
        self._runtime = False
        self._function: List[str] = []

    # -- обход ---------------------------------------------------------

    def visit(self, node: ast.AST) -> None:  # type: ignore[override]
        self._parents.append(node)
        try:
            super().visit(node)
        finally:
            self._parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.AST) -> None:
        # декораторы, аннотации и значения по умолчанию вычисляются при импорте
        previous = self._runtime
        for child in node.decorator_list:  # type: ignore[attr-defined]
            self.visit(child)
        self._visit_arguments(node.args)  # type: ignore[attr-defined]
        self._runtime = True
        self._function.append(node.name)  # type: ignore[attr-defined]
        try:
            for statement in node.body:  # type: ignore[attr-defined]
                self.visit(statement)
        finally:
            self._function.pop()
        self._runtime = previous

    def _visit_arguments(self, arguments: ast.arguments) -> None:
        for default in list(arguments.defaults) + list(arguments.kw_defaults):
            if default is not None:
                self.visit(default)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        previous = self._runtime
        self._visit_arguments(node.args)
        self._runtime = True
        self._function.append("<lambda>")
        try:
            self.visit(node.body)
        finally:
            self._function.pop()
        self._runtime = previous

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # тело класса исполняется при импорте, режим не меняется
        for child in node.decorator_list + node.bases + [kw.value for kw in node.keywords]:
            self.visit(child)
        for statement in node.body:
            self.visit(statement)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        """f-строка заменяется целиком, если её можно превратить в шаблон.

        Замена отдельных текстовых частей запрещена: она меняет порядок слов
        и теряет подстановки (``f"ОЗ — {n} шт."`` распадалось на куски).
        Целиком f-строку можно заменить, только если все выражения — простые
        имена (или к ним сводимые) без спецификаторов формата и без ``!r``;
        иначе вхождение пропускается с причиной ``fstring``.
        """
        template = build_fstring_template(node)
        if template is None:
            self._add_fstring_parts(node)
            return
        text, arguments = template
        self.sites.append(
            Site(
                path=self.path,
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                col=node.col_offset,
                end_col=getattr(node, "end_col_offset", node.col_offset)
                or node.col_offset,
                value=text,
                category=self._fstring_category(node, text),
                snippet=self._snippet(node.lineno),
                function=self._current_function(),
                in_fstring=True,
                arguments=arguments,
            )
        )

    def _add_fstring_parts(self, node: ast.JoinedStr) -> None:
        """Запоминает f-строку как пропущенную, с указанием длины текста."""
        text = "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
        if not CYRILLIC_RE.search(text) or not text.strip():
            return
        self.sites.append(
            Site(
                path=self.path,
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                col=node.col_offset,
                end_col=getattr(node, "end_col_offset", node.col_offset)
                or node.col_offset,
                value=text.strip(),
                category="fstring",
                snippet=self._snippet(node.lineno),
                function=self._current_function(),
                in_fstring=True,
            )
        )

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or not CYRILLIC_RE.search(node.value):
            return
        if not node.value.strip():
            return
        self.sites.append(
            Site(
                path=self.path,
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno) or node.lineno,
                col=node.col_offset,
                end_col=getattr(node, "end_col_offset", node.col_offset)
                or node.col_offset,
                value=node.value,
                category=self._category(node),
                snippet=self._snippet(node.lineno),
                function=self._current_function(),
            )
        )

    # -- вспомогательное ------------------------------------------------

    def _current_function(self) -> str:
        """Имя функции, внутри которой строка (пусто на уровне модуля)."""
        return self._function[-1] if self._function else ""

    def _snippet(self, lineno: int) -> str:
        lines = self.source.splitlines()
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()[:160]
        return ""

    def _category(self, node: ast.AST, text: Optional[str] = None) -> str:
        """Определяет категорию вхождения по окружению."""
        value = text if text is not None else getattr(node, "value", "")
        if _is_docstring(node, self._parents):
            return "docstring"
        if _is_statement_string(node, self._parents):
            return "statement"
        if len(value.strip()) <= SHORT_TEXT_LENGTH:
            return "short"
        if value.strip().lower() in VALUE_WORDS:
            return "compare"
        if self._in_compare(node):
            return "compare"
        if self._is_mapping_key(node):
            return "mapping_key"
        if self._is_filename(value):
            return "filename"
        if self._is_sheet_name(node):
            return "sheet_name"
        if self._is_path_part(node):
            return "path_part"
        call = self._enclosing_call()
        if call is not None:
            name = _call_name(call)
            if name in LOG_METHODS:
                return "log"
            if _is_exception_call(call):
                return "exception"
            if any(keyword.arg == "info" for keyword in call.keywords):
                return "orm_label"
        if not self._runtime:
            return "import_time"
        return "text"

    @staticmethod
    def _is_filename(value: str) -> bool:
        """Литерал — имя файла: заканчивается известным расширением."""
        return bool(FILE_EXTENSION_RE.search(value.strip()))

    def _is_sheet_name(self, node: ast.AST) -> bool:
        """Литерал — имя листа книги Excel: аргумент функции с ``sheet``."""
        for index in range(len(self._parents) - 1, 0, -1):
            parent = self._parents[index]
            child = self._parents[index + 1] if index + 1 < len(self._parents) else node
            if isinstance(parent, ast.Call):
                name = _call_name(parent).lower()
                if any(hint in name for hint in SHEET_FUNCTION_HINTS):
                    return any(argument is child for argument in parent.args)
                return False
            if isinstance(parent, (ast.stmt, ast.Module)):
                return False
        return False

    def _is_path_part(self, node: ast.AST) -> bool:
        """Литерал — сегмент пути: слагаемое ``/`` рядом со строкой.

        Строку нельзя разделить на строку или число арифметически (это
        ``TypeError``), поэтому строковый литерал в роли операнда ``/`` —
        это соединение пути через ``pathlib``: ``storage / "Импорт"``.
        """
        for index in range(len(self._parents) - 1, 0, -1):
            parent = self._parents[index]
            if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
                return True
            if isinstance(parent, (ast.Call, ast.stmt, ast.Module)):
                return False
        return False

    def _enclosing_call(self) -> Optional[ast.Call]:
        """Ближайший вызов, внутри которого находится строка."""
        for ancestor in reversed(self._parents[:-1]):
            if isinstance(ancestor, ast.Call):
                return ancestor
        return None

    def _in_compare(self, node: ast.Constant) -> bool:
        """Строка участвует в сравнении или проверке вхождения."""
        for index in range(len(self._parents) - 1, 0, -1):
            parent = self._parents[index]
            child = self._parents[index + 1] if index + 1 < len(self._parents) else node
            if isinstance(parent, ast.Compare):
                operands = [parent.left, *parent.comparators]
                return any(child is operand or _contains(operand, node)
                           for operand in operands)
            if isinstance(parent, (ast.Tuple, ast.Set, ast.List)):
                continue
            if isinstance(parent, (ast.Call, ast.stmt, ast.Module)):
                return False
        return False

    def _is_mapping_key(self, node: ast.Constant) -> bool:
        """Строка — ключ словаря или аргумент ``dict.get("…")``."""
        for index in range(len(self._parents) - 1, 0, -1):
            parent = self._parents[index]
            child = self._parents[index + 1] if index + 1 < len(self._parents) else node
            if isinstance(parent, ast.Dict):
                return any(key is child for key in parent.keys)
            if isinstance(parent, ast.Subscript) and child is not parent.slice:
                return True
            if isinstance(parent, ast.Call) and _call_name(parent) == "get":
                if parent.args and parent.args[0] is child:
                    return True
            if isinstance(parent, (ast.Call, ast.stmt, ast.Module)):
                return False
        return False

    def _fstring_category(self, node: ast.JoinedStr, text: str) -> str:
        """Категория f-строки с учётом контекста и имени файла."""
        self._parents.append(node)
        try:
            category = self._category(node, text)
        finally:
            self._parents.pop()
        return category


def _contains(node: ast.AST, target: ast.AST) -> bool:
    """Есть ли ``target`` среди потомков ``node``."""
    for child in ast.walk(node):
        if child is target:
            return True
    return False


def _looks_like_path(node: ast.AST) -> bool:
    """Похоже ли выражение на путь: ``Path(...)`` или имя со словом ``path``."""
    if isinstance(node, ast.Call) and _call_name(node) in ("Path", "PurePath"):
        return True
    if isinstance(node, ast.Attribute) and node.attr in ("parent", "anchor", "stem"):
        return True
    if isinstance(node, ast.Name) and "path" in node.id.lower():
        return True
    if isinstance(node, ast.Attribute) and "path" in node.attr.lower():
        return True
    return False


# ---------------------------------------------------------------------------
# Правка файлов
# ---------------------------------------------------------------------------


class SourceFile:
    """Исходник с пересчётом координат AST в байтовые смещения."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.raw = path.read_bytes()
        self.text = self.raw.decode("utf-8")
        self.newline = "\r\n" if b"\r\n" in self.raw else "\n"
        self._line_bytes: List[int] = [0]
        for index, byte in enumerate(self.raw):
            if byte == 0x0A:
                self._line_bytes.append(index + 1)

    def offset(self, lineno: int, col: int) -> int:
        """Байтовое смещение позиции (lineno, col) из AST."""
        if lineno - 1 >= len(self._line_bytes):
            return len(self.raw)
        return self._line_bytes[lineno - 1] + col

    def insert_offset_for_import(self, tree: ast.Module) -> int:
        """Куда вставить импорт: после последнего импорта модуля."""
        last = 0
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                last = max(
                    last,
                    self.offset(
                        node.end_lineno or node.lineno, node.end_col_offset or 0
                    ),
                )
        if last:
            return last
        if getattr(tree, "body", []):
            first = tree.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                return self.offset(
                    first.end_lineno or first.lineno, first.end_col_offset or 0
                )
        return 0


class Rewriter:
    """Применяет замены литералов и при необходимости добавляет импорт."""

    def __init__(self, strings_module: str = STRINGS_IMPORT) -> None:
        self.strings_module = strings_module

    def apply(self, source: SourceFile, tree: ast.Module, sites: Sequence[Site]) -> str:
        """Возвращает новое содержимое файла."""
        edits: List[Tuple[int, int, bytes]] = []
        for site in sites:
            start = source.offset(site.lineno, site.col)
            end = source.offset(site.end_lineno, site.end_col)
            edits.append((start, end, site.replacement.encode("utf-8")))
        if not edits:
            return source.text
        raw = source.raw
        if not self._has_strings_import(tree):
            position = source.insert_offset_for_import(tree)
            addition = (source.newline + self.strings_module).encode("utf-8")
            if position == 0:
                addition = (self.strings_module + source.newline).encode("utf-8")
            edits.append((position, position, addition))
        for start, end, payload in sorted(
            edits, key=lambda item: item[0], reverse=True
        ):
            raw = raw[:start] + payload + raw[end:]
        return raw.decode("utf-8")

    @staticmethod
    def _has_strings_import(tree: ast.Module) -> bool:
        """Уже импортирован ли ``STRINGS`` в модуле."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "STRINGS" and alias.asname in (None, "STRINGS"):
                        return True
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.endswith("string_resources"):
                        return True
        return False


# ---------------------------------------------------------------------------
# Чтение и запись пакета
# ---------------------------------------------------------------------------


def read_app_strings(path: Path) -> List[Tuple[str, str]]:
    """Читает поля ``AppStrings`` (имя, текст) без импорта модуля."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AppStrings":
            result: List[Tuple[str, str]] = []
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    name = statement.target.id
                    value = statement.value
                elif (
                    isinstance(statement, ast.Assign)
                    and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Name)
                ):
                    name = statement.targets[0].id
                    value = statement.value
                else:
                    continue
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    result.append((name, value.value))
            return result
    raise SystemExit(f"{path}: не найден класс AppStrings")


def read_pack_strings(path: Path) -> Dict[str, str]:
    """Читает секцию ``strings`` пакета предметной области."""
    data = json.loads(path.read_text(encoding="utf-8"))
    strings = data.get("strings", {})
    if not isinstance(strings, dict):
        raise SystemExit(f"{path}: секция strings должна быть объектом")
    return {str(key): str(value) for key, value in strings.items()}


def write_new_strings(path: Path, new_values: Dict[str, str]) -> List[str]:
    """Дописывает поля в ``AppStrings`` и возвращает добавленные имена."""
    source = SourceFile(path)
    tree = ast.parse(source.text)
    target: Optional[ast.ClassDef] = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AppStrings":
            target = node
            break
    if target is None:
        raise SystemExit(f"{path}: не найден класс AppStrings")
    last_line = max(
        (statement.end_lineno or statement.lineno) for statement in target.body
    )
    lines = source.text.splitlines(keepends=True)
    addition = []
    for key, value in new_values.items():
        literal = json.dumps(value, ensure_ascii=False)
        addition.append(f"    {key}: str = {literal}{source.newline}")
    lines.insert(last_line, "".join(addition))
    path.write_text("".join(lines), encoding="utf-8", newline="")
    return list(new_values)


def write_pack(path: Path, strings: Dict[str, str]) -> None:
    """Переписывает секцию ``strings`` пакета, сохраняя остальное."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["strings"] = strings
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Основной проход
# ---------------------------------------------------------------------------


class Extractor:
    """Ищет русские литералы, присваивает ключи и (опционально) правит код."""

    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.root = Path(options.root).resolve() if options.root else (
            PROJECT_ROOT / PACKAGE_DIR
        ).resolve()
        self.pack_path = (
            Path(options.pack).resolve() if options.pack else PROJECT_ROOT / PACK_PATH
        )
        self.strings_path = (
            Path(options.strings).resolve()
            if options.strings
            else PROJECT_ROOT / STRINGS_PATH
        )
        self.fields: Dict[str, str] = dict(read_app_strings(self.strings_path))
        pack_strings = (
            read_pack_strings(self.pack_path) if self.pack_path.exists() else {}
        )
        combined = dict(pack_strings)
        combined.update(self.fields)
        self.registry = KeyRegistry(combined, reuse=not options.no_reuse)
        self.reports: List[FileReport] = []
        self.scanned = 0

    # -- конфигурация ---------------------------------------------------

    def skip_flag(self, category: str) -> Optional[str]:
        """Флаг, включающий категорию; None — категория не переносится никогда."""
        return SKIP_FLAGS.get(category)

    def is_skipped(self, category: str) -> bool:
        """Пропускается ли категория при текущих флагах."""
        if category == "text":
            return False
        flag = self.skip_flag(category)
        if flag is None:
            return True
        return not getattr(self.options, flag, False)

    # -- сбор -----------------------------------------------------------

    def collect(self) -> List[FileReport]:
        """Проходит по файлам пакета и собирает вхождения."""
        for path in sorted(self.root.rglob("*.py")):
            relative = self._relative(path)
            if relative in ALWAYS_SKIP or path.name in self.options.skip_files:
                continue
            if self.options.only and self.options.only not in relative:
                continue
            self.scanned += 1
            report = self._scan_file(path, relative)
            if report.sites:
                self.reports.append(report)
        return self.reports

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.as_posix()

    def _scan_file(self, path: Path, relative: str) -> FileReport:
        report = FileReport(path=relative)
        try:
            source = SourceFile(path)
            tree = ast.parse(source.text, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as error:
            print(f"пропущен {relative}: {error}", file=sys.stderr)
            return report
        collector = Collector(relative, source.text)
        collector.visit(tree)
        for site in collector.sites:
            if self.is_skipped(site.category):
                report.sites.append(site)
                continue
            site.key = self.registry.key_for(
                site.value, hint=self._hint_for(site, site.function)
            )
            site.replacement = self._replacement(site)
            report.sites.append(site)
        return report

    @staticmethod
    def _hint_for(site: Site, function: str = "") -> str:
        """Подсказка для имени ключа: слова текста, иначе имя функции.

        Плейсхолдеры ``{name_1}`` выброшены: в имени ключа они ничего не
        значат. Если значимых слов не осталось (``"{a} от {b}"`` — только
        предлог), ключ собирается из имени функции и номера строки.
        """
        text = re.sub(r"\{[^{}]*\}", " ", site.value)
        words = [
            word
            for word in re.findall(r"[А-Яа-яЁёA-Za-z0-9]+", text)
            if word.lower() not in FUNCTION_WORDS
        ]
        if words:
            return "_".join(words[:4])
        if function and function != "<lambda>":
            return function
        return f"{Path(site.path).stem}_{site.lineno}"

    @staticmethod
    def _replacement(site: Site) -> str:
        """Текст замены литерала.

        Для f-строки подставляется шаблон пакета с ``.format(...)``: аргументы
        — исходные выражения f-строки, поэтому форматирование и значения
        остаются прежними.
        """
        reference = f"STRINGS.{site.key}"
        if not site.in_fstring:
            return reference
        if not site.arguments:
            return reference
        arguments = ", ".join(site.arguments)
        return f"{reference}.format({arguments})"

    # -- применение -----------------------------------------------------

    def apply(self) -> Tuple[int, int]:
        """Переписывает файлы, добавляет поля и обновляет пакет."""
        rewriter = Rewriter()
        changed_files = 0
        changed_sites = 0
        for report in self.reports:
            applied = report.applied
            if not applied:
                continue
            path = PROJECT_ROOT / report.path
            source = SourceFile(path)
            tree = ast.parse(source.text, filename=str(path))
            updated = rewriter.apply(source, tree, applied)
            if updated != source.text:
                path.write_text(updated, encoding="utf-8", newline="")
                changed_files += 1
                changed_sites += len(applied)
        new_keys = self.registry.new_keys
        if new_keys:
            self.fields.update(new_keys)
            write_new_strings(self.strings_path, new_keys)
            write_pack(self.pack_path, self.fields)
        return changed_files, changed_sites

    # -- отчёт ----------------------------------------------------------

    def report_dict(self) -> dict:
        """Сводка по всем найденным вхождениям."""
        all_sites = [site for report in self.reports for site in report.sites]
        applied = [site for site in all_sites if site.replacement]
        skipped = [site for site in all_sites if not site.replacement]
        by_category: Dict[str, int] = {}
        skipped_by_category: Dict[str, int] = {}
        for site in applied:
            by_category[site.category] = by_category.get(site.category, 0) + 1
        for site in skipped:
            skipped_by_category[site.category] = (
                skipped_by_category.get(site.category, 0) + 1
            )
        by_file: Dict[str, int] = {}
        for report in self.reports:
            if report.applied:
                by_file[report.path] = len(report.applied)
        return {
            "files_scanned": self.scanned,
            "files_to_change": len(by_file),
            "literals_found": len(all_sites),
            "literals_to_replace": len(applied),
            "literals_skipped": len(skipped),
            "new_keys": len(self.registry.new_keys),
            "reused_keys": len(self.registry.reused),
            "by_category": dict(sorted(by_category.items())),
            "skipped_by_category": dict(sorted(skipped_by_category.items())),
            "by_file": dict(sorted(by_file.items(), key=lambda item: -item[1])),
            "samples": [
                {
                    "path": site.path,
                    "line": site.lineno,
                    "key": site.key,
                    "value": site.value,
                    "replacement": site.replacement,
                }
                for site in applied[:40]
            ],
            "skipped_samples": [
                {
                    "path": site.path,
                    "line": site.lineno,
                    "category": site.category,
                    "value": site.value,
                }
                for site in skipped[:40]
            ],
        }

    def print_report(self, summary: dict, show_skipped: bool = False) -> None:
        """Печатает отчёт в человекочитаемом виде."""
        print(f"Файлов просмотрено: {summary['files_scanned']}")
        print(f"Литералов с русским текстом: {summary['literals_found']}")
        print(
            f"К переносу: {summary['literals_to_replace']} "
            f"в {summary['files_to_change']} файлах"
        )
        print(
            f"Пропущено: {summary['literals_skipped']}"
            f" (см. --show-skipped)"
        )
        print(
            f"Ключей: новых {summary['new_keys']}, "
            f"переиспользовано существующих {summary['reused_keys']}"
        )
        if summary["by_file"]:
            print("\nФайлы с наибольшим числом замен:")
            for path, count in list(summary["by_file"].items())[:15]:
                print(f"  {count:4d}  {path}")
        if summary["skipped_by_category"]:
            print("\nПропущено по причинам:")
            for category, count in summary["skipped_by_category"].items():
                title = CATEGORY_TITLES.get(category, category)
                print(f"  {count:4d}  {category:12s} {title}")
        if summary["samples"]:
            print("\nПримеры замен:")
            for sample in summary["samples"][:10]:
                print(f"  {sample['path']}:{sample['line']}")
                print(f"    было:  {sample['value']!r}")
                print(f"    стало: {sample['replacement']}")
        if show_skipped and summary["skipped_samples"]:
            print("\nПримеры пропущенных вхождений:")
            for sample in summary["skipped_samples"][:25]:
                print(f"  [{sample['category']}] {sample['path']}:{sample['line']}")
                print(f"    {sample['value']!r}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Переносит русские строки кода в пакет предметной области",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="переписать файлы, добавить ключи в AppStrings и пакет",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="только проверить: код возврата 1, если остались русские строки",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="показать примеры пропущенных вхождений с причиной",
    )
    parser.add_argument("--root", type=Path, default=None, help="каталог для обхода")
    parser.add_argument("--pack", type=Path, default=None, help="путь к пакету JSON")
    parser.add_argument(
        "--strings", type=Path, default=None, help="путь к string_resources.py"
    )
    parser.add_argument(
        "--report", type=Path, default=None, help="записать отчёт в JSON-файл"
    )
    parser.add_argument(
        "--only", default="", help="обрабатывать только файлы с этим фрагментом пути"
    )
    parser.add_argument(
        "--skip-file",
        dest="skip_files",
        action="append",
        default=[],
        help="имя файла, который нужно пропустить (можно несколько раз)",
    )
    parser.add_argument(
        "--no-reuse",
        action="store_true",
        help="не переиспользовать существующие ключи пакета с тем же текстом",
    )
    parser.add_argument(
        "--include-logs", action="store_true", help="переносить сообщения журналирования"
    )
    parser.add_argument(
        "--include-exceptions", action="store_true", help="переносить тексты исключений"
    )
    parser.add_argument(
        "--include-import-time",
        action="store_true",
        help="переносить строки, вычисляемые при импорте",
    )
    parser.add_argument(
        "--include-orm-labels",
        action="store_true",
        help="переносить info={'label': ...} вместо секции entities",
    )
    parser.add_argument(
        "--include-data-keys",
        action="store_true",
        help="переносить ключи словарей и операнды сравнений",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="не печатать отчёт (нужен для запуска из тестов)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа: сбор, отчёт и (при --apply) правка файлов."""
    options = parse_args(argv)
    extractor = Extractor(options)
    extractor.collect()
    summary = extractor.report_dict()

    if options.report:
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if options.check:
        remaining = summary["literals_to_replace"]
        if remaining:
            print(
                f"Найдено русских строк вне пакета: {remaining}", file=sys.stderr
            )
            if not options.quiet:
                extractor.print_report(summary, options.show_skipped)
            return 1
        if not options.quiet:
            print("Русских строк вне пакета не найдено")
        return 0

    if options.apply:
        files, sites = extractor.apply()
        if not options.quiet:
            print(f"Изменено файлов: {files}, заменено литералов: {sites}")
            print(f"Добавлено ключей: {summary['new_keys']}")
        return 0

    if not options.quiet:
        extractor.print_report(summary, options.show_skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
