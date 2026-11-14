"""Сборка DOCX-описания схемы БД из интроспекции SQLAlchemy."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .model import (
    ASSOCIATIONS,
    DOMAINS,
    TableInfo,
    domain_tables,
)

DARK_BLUE = "1F3864"
HEADER_BLUE = "2E75B6"
LIGHT_BLUE = "DEEBF7"
LIGHT_GRAY = "F2F2F2"
MID_GRAY = "BFBFBF"


def _set_cell_shading(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def _set_cell_margins(cell, top: int = 20, bottom: int = 20, left: int = 90, right: int = 90) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for tag, value in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def _repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def _no_split(row) -> None:
    """Запрещает разрыв строки таблицы между страницами."""
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    cant_split.set(qn("w:val"), "true")
    tr_pr.append(cant_split)


def _set_col_widths(table, widths: Sequence[float]) -> None:
    for row in table.rows:
        for index, width in enumerate(widths):
            if index < len(row.cells):
                row.cells[index].width = Cm(width)


def _add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char)
    run._r.append(instr)
    run._r.append(fld_end)


def _configure_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.15
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "Times New Roman")

    for name, size, color in (
        ("Heading 1", 18, DARK_BLUE),
        ("Heading 2", 14, HEADER_BLUE),
        ("Heading 3", 12, DARK_BLUE),
    ):
        style = document.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True


def _configure_page(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(1.5)
    section.different_first_page_header_footer = True

    footer = section.footer
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run("Описание схемы базы данных · ")
    _add_page_number(paragraph)
    for run in paragraph.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x59, 0x59, 0x59)


def _add_title_page(document: Document) -> None:
    for _ in range(4):
        document.add_paragraph()
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("ВНУТРЕННЯЯ КОРРЕСПОНДЕНЦИЯ")
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = RGBColor.from_string(DARK_BLUE)

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("Описание схемы базы данных")
    run.bold = True
    run.font.size = Pt(30)
    run.font.color.rgb = RGBColor.from_string(DARK_BLUE)

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("Таблицы, поля, связи и диаграммы")
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x59, 0x59, 0x59)

    document.add_paragraph()
    info = document.add_table(rows=4, cols=2)
    info.alignment = WD_TABLE_ALIGNMENT.CENTER
    info.style = "Table Grid"
    values = [
        ("Версия документа", "1.0"),
        ("Дата", date.today().strftime("%d.%m.%Y")),
        ("СУБД", "SQLite (филиал) / PostgreSQL (головной офис)"),
        ("Источник", "SQLAlchemy-модели internal_correspondence"),
    ]
    for row, (key, value) in zip(info.rows, values):
        row.cells[0].text = key
        row.cells[1].text = value
        row.cells[0].paragraphs[0].runs[0].bold = True
        _set_cell_shading(row.cells[0], LIGHT_BLUE)
    _set_col_widths(info, [5.0, 11.5])

    document.add_paragraph()
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(
        "Документ сгенерирован автоматически из метаданных SQLAlchemy.\n"
        "При изменении моделей описание и диаграммы нужно пересобрать."
    )
    run.font.size = Pt(9)
    run.italic = True
    run.font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)
    paragraph.add_run().add_break(WD_BREAK.PAGE)


def _add_contents(document: Document) -> None:
    document.add_heading("Содержание", level=1)
    entries = [
        "1. Общие сведения",
        "2. Обзорная схема",
        "3. Справочники",
        "4. Организационная структура",
        "5. Документы",
        "6. Научные задачи и распределение",
        "7. Оценки",
        "8. Импорт оценок",
        "9. Обмен изменениями",
        "10. Служебные объекты",
        "11. Ассоциативные таблицы",
        "12. Сводка внешних ключей",
        "13. Порядок сопровождения",
    ]
    for entry in entries:
        paragraph = document.add_paragraph(entry)
        paragraph.paragraph_format.space_after = Pt(4)
    document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _add_paragraph(document: Document, text: str, *, bold: bool = False, italic: bool = False, size: int = 11) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return paragraph


def _add_bullet(document: Document, text: str) -> None:
    paragraph = document.add_paragraph(text, style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(1)
    for run in paragraph.runs:
        run.font.size = Pt(10.5)
    for run in paragraph.runs:
        run.font.size = Pt(10.5)


def _start_landscape(document: Document) -> None:
    section = document.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21.0)
    section.top_margin = Cm(1.4)
    section.bottom_margin = Cm(1.4)
    section.left_margin = Cm(1.6)
    section.right_margin = Cm(1.6)


def _start_portrait(document: Document) -> None:
    section = document.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(1.5)


def _add_caption(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x59, 0x59, 0x59)


def _add_image(document: Document, path: Path, caption: str, width: float = 16.5) -> None:
    if not path.exists():
        _add_paragraph(document, f"[Диаграмма не найдена: {path.name}]", italic=True)
        return
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(path), width=Cm(width))
    _add_caption(document, caption)


def _clean_type(type_name: str) -> str:
    text = type_name.upper().replace("VARCHAR", "VARCHAR").replace("NUMERIC", "NUMERIC")
    text = text.replace(", ", ",").replace(" ", "")
    if text.startswith("VARCHAR") or text.startswith("NUMERIC") or text.startswith("STRING"):
        return text
    return {
        "INTEGER": "INTEGER",
        "BIGINTEGER": "BIGINT",
        "BOOLEAN": "BOOLEAN",
        "DATE": "DATE",
        "DATETIME": "DATETIME",
        "TEXT": "TEXT",
        "UUID": "UUID",
        "JSON": "JSON",
        "FLOAT": "REAL",
    }.get(text, text)


def _add_field_table(document: Document, table: TableInfo) -> None:
    rows = len(table.columns) + 1
    doc_table = document.add_table(rows=rows, cols=5)
    doc_table.style = "Table Grid"
    doc_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Поле", "Тип", "NULL", "Ключ", "Описание"]
    for index, header in enumerate(headers):
        cell = doc_table.rows[0].cells[index]
        cell.text = header
        _set_cell_shading(cell, HEADER_BLUE)
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            run.font.size = Pt(10)
        _set_cell_margins(cell)
    _repeat_header(doc_table.rows[0])

    for row_index, column in enumerate(table.columns, start=1):
        cells = doc_table.rows[row_index].cells
        key = ""
        if column.primary_key:
            key = "PK"
        if column.foreign_key:
            key = "FK" if not key else "PK/FK"
        values = [
            f"{column.label}\n({column.name})" if column.label != column.name else column.name,
            _clean_type(column.type_name),
            "да" if column.nullable else "нет",
            key,
            column.description or "—",
        ]
        for cell, value in zip(cells, values):
            cell.text = value
            _set_cell_margins(cell)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
            if column.primary_key:
                _set_cell_shading(cell, LIGHT_BLUE)
        if row_index % 2 == 0:
            for cell in cells:
                _set_cell_shading(cell, LIGHT_GRAY)

    _set_col_widths(doc_table, [4.4, 3.0, 1.3, 1.5, 5.8])
    for row in doc_table.rows:
        _no_split(row)


def _relationships(schema: Dict[str, TableInfo], table: TableInfo) -> List[str]:
    lines: List[str] = []
    for column in table.foreign_keys:
        target = schema.get(column.foreign_key.split(".")[0]) if column.foreign_key else None
        target_label = target.label if target else column.foreign_key
        suffix = f" (ON DELETE {column.ondelete})" if column.ondelete else ""
        lines.append(f"{column.name} → {target_label}.{column.foreign_key.split('.')[-1]}{suffix}")
    for name, (left, right) in ASSOCIATIONS.items():
        if left == table.name:
            other = schema.get(right)
            lines.append(f"M:N с «{other.label if other else right}» через {name}")
        elif right == table.name:
            other = schema.get(left)
            lines.append(f"M:N с «{other.label if other else left}» через {name}")
    return lines


def _add_table_section(document: Document, schema: Dict[str, TableInfo], table: TableInfo, caption_no: int) -> None:
    document.add_heading(f"{table.label} ({table.name})", level=2)
    if table.description:
        _add_paragraph(document, table.description)
    _add_field_table(document, table)
    _add_caption(document, f"Таблица {caption_no}. Поля таблицы {table.name}")

    relations = _relationships(schema, table)
    if relations:
        _add_paragraph(document, "Связи:", bold=True)
        for line in relations:
            _add_bullet(document, line)

    if table.indexes:
        _add_paragraph(document, "Индексы:", bold=True)
        for index in table.indexes:
            unique = " (уникальный)" if index.unique else ""
            _add_bullet(document, f"{index.name}: {', '.join(index.columns)}{unique}")

    if table.unique_constraints:
        _add_paragraph(document, "Уникальные ограничения:", bold=True)
        for name, columns in table.unique_constraints:
            _add_bullet(document, f"{name or 'без имени'}: {', '.join(columns)}")


def _add_domain(
    document: Document,
    schema: Dict[str, TableInfo],
    code: str,
    title: str,
    intro: str,
    diagram: Optional[str],
    docs_dir: Path,
    figure_no: int,
    table_no: int,
) -> Tuple[int, int]:
    if diagram:
        _start_landscape(document)
        document.add_heading(title, level=1)
        _add_paragraph(document, intro)
        clean_title = title.split(". ", 1)[1] if title[:1].isdigit() and ". " in title else title
        _add_image(document, docs_dir / diagram, f"Рисунок {figure_no}. {clean_title}", width=23.0)
        figure_no += 1
        _start_portrait(document)
    else:
        document.add_heading(title, level=1)
        _add_paragraph(document, intro)
    for table in domain_tables(schema, code):
        _add_table_section(document, schema, table, table_no)
        table_no += 1
    return figure_no, table_no


def _add_associations(document: Document, schema: Dict[str, TableInfo], caption_no: int) -> None:
    document.add_heading("11. Ассоциативные таблицы", level=1)
    _add_paragraph(
        document,
        "Связи «многие ко многим» реализованы отдельными таблицами с составным первичным ключом. "
        "В прикладном коде они не являются самостоятельными сущностями и не экспортируются отдельно: "
        "изменение связи фиксируется в change tracking владельца — стороны, чей внешний ключ идёт первой колонкой.",
    )
    doc_table = document.add_table(rows=len(ASSOCIATIONS) + 1, cols=4)
    doc_table.style = "Table Grid"
    doc_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Таблица", "Левая сторона", "Правая сторона", "Смысл"]
    for index, header in enumerate(headers):
        cell = doc_table.rows[0].cells[index]
        cell.text = header
        _set_cell_shading(cell, HEADER_BLUE)
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            run.font.size = Pt(9)
    _repeat_header(doc_table.rows[0])
    for row_index, (name, (left, right)) in enumerate(sorted(ASSOCIATIONS.items()), start=1):
        left_table = schema.get(left)
        right_table = schema.get(right)
        cells = doc_table.rows[row_index].cells
        cells[0].text = name
        cells[1].text = left_table.label if left_table else left
        cells[2].text = right_table.label if right_table else right
        cells[3].text = f"связь: {cells[1].text} ↔ {cells[2].text}"
        for cell in cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8.5)
    _set_col_widths(doc_table, [4.0, 4.0, 4.0, 4.5])
    for row in doc_table.rows:
        _no_split(row)
    _add_caption(document, f"Таблица {caption_no}. Ассоциативные таблицы")


def _add_fk_summary(document: Document, schema: Dict[str, TableInfo], caption_no: int) -> None:
    document.add_heading("12. Сводка внешних ключей", level=1)
    _add_paragraph(
        document,
        "Таблица содержит все явные внешние ключи. Для связей M:N внешние ключи находятся "
        "в ассоциативных таблицах (раздел 11).",
    )
    rows: List[Tuple[str, str, str, str]] = []
    for table in sorted(schema.values(), key=lambda item: item.name):
        for column in table.foreign_keys:
            target_table, _, target_column = (column.foreign_key or "").partition(".")
            target = schema.get(target_table)
            rows.append(
                (
                    table.name,
                    column.name,
                    f"{target.label if target else target_table}.{target_column}",
                    column.ondelete or "—",
                )
            )
    doc_table = document.add_table(rows=len(rows) + 1, cols=4)
    doc_table.style = "Table Grid"
    doc_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, header in enumerate(["Таблица", "Поле", "Ссылается на", "ON DELETE"]):
        cell = doc_table.rows[0].cells[index]
        cell.text = header
        _set_cell_shading(cell, HEADER_BLUE)
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            run.font.size = Pt(8.5)
    _repeat_header(doc_table.rows[0])
    for row_index, values in enumerate(rows, start=1):
        cells = doc_table.rows[row_index].cells
        for cell, value in zip(cells, values):
            cell.text = value
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)
    _set_col_widths(doc_table, [4.5, 4.0, 5.5, 2.5])
    for row in doc_table.rows:
        _no_split(row)
    _add_caption(document, f"Таблица {caption_no}. Внешние ключи")


def _add_service(document: Document) -> None:
    document.add_heading("10. Служебные объекты", level=1)
    _add_paragraph(
        document,
        "Служебные объекты не являются бизнес-сущностями и не участвуют в обмене ZIP-дельты. "
        "Они обеспечивают версионирование схемы и просмотр результатов импорта.",
    )
    for title, text in (
        (
            "alembic_version",
            "Служебная таблица Alembic: одна строка с идентификатором текущей ревизии. "
            "Приложение не читает её напрямую; миграции применяются командой alembic upgrade head.",
        ),
        (
            "import_matches (VIEW)",
            "Представление объединяет import_rows и import_log и показывает, какая строка файла "
            "сопоставлена с каким документом. Используется для отчёта и диагностики; данные не хранит.",
        ),
    ):
        document.add_heading(title, level=2)
        _add_paragraph(document, text)


def _add_maintenance(document: Document) -> None:
    document.add_heading("13. Порядок сопровождения", level=1)
    _add_paragraph(
        document,
        "Документ и диаграммы строятся по метаданным SQLAlchemy, поэтому при изменении моделей "
        "их нужно пересобрать.",
    )
    for step in (
        "Изменить модели в internal_correspondence/orm/models.py (и Core-таблицы импорта при необходимости).",
        "Добавить миграцию Alembic; проверить upgrade и downgrade на SQLite.",
        "Обновить метки и описания в scripts_dev/schema_docs/model.py, если появились новые таблицы или поля.",
        "Выполнить: python scripts_dev/dump_schema.py --output docs/database.docx.",
        "Проверить документ и диаграммы, закоммитить изменения.",
    ):
        _add_bullet(document, step)
    _add_paragraph(
        document,
        "Команда генерации: .venv\\Scripts\\python.exe scripts_dev\\dump_schema.py "
        "--output docs\\database.docx --diagrams-dir docs",
        italic=True,
        size=9,
    )


def build(schema: Dict[str, TableInfo], output: Path, diagrams_dir: Optional[Path] = None) -> Path:
    document = Document()
    _configure_page(document)
    _configure_styles(document)
    _add_title_page(document)
    _add_contents(document)
    docs_dir = diagrams_dir or output.parent

    document.add_heading("1. Общие сведения", level=1)
    _add_paragraph(
        document,
        "Приложение «Внутренняя корреспонденция» автоматизирует учёт научных материалов и телеграмм, "
        "распределение научных задач, оценки и обмен изменениями между филиалами и головным офисом. "
        "Филиал работает с локальной базой SQLite, головной офис — с PostgreSQL; схема должна быть "
        "одинаковой для обеих СУБД.",
    )
    _add_paragraph(
        document,
        f"В документе описаны {len(schema)} таблиц: {len(schema) - len(ASSOCIATIONS) - 2} бизнес-таблиц, "
        f"2 служебные таблицы импорта и {len(ASSOCIATIONS)} ассоциативных таблиц, а также служебное представление import_matches. "
        "Связи M:N в разделах описаны одной строкой, а их физические таблицы перечислены в разделе 11.",
    )
    _add_paragraph(document, "Соглашения:", bold=True)
    for text in (
        "PK — первичный ключ; FK — внешний ключ; NULL — допустимость пустого значения.",
        "Типы приведены в нотации SQL; для SQLite и PostgreSQL используются совместимые типы.",
        "UUID-ключи применяются для ОШС, документов, файлов, адресации, оценок и назначений.",
        "Справочники используют короткие строковые коды; changes.id — целочисленный autoincrement.",
        "Все изменяемые бизнес-сущности имеют change_id и участвуют в обмене дельтами.",
    ):
        _add_bullet(document, text)

    _start_landscape(document)
    document.add_heading("2. Обзорная схема", level=1)
    _add_paragraph(
        document,
        "Домены сгруппированы по назначению. Документы — центральный домен: с ними связаны "
        "справочники, ОШС, задачи, файлы и оценки; импорт читает документы и создаёт оценки.",
    )
    _add_image(document, docs_dir / "schema_overview.png", "Рисунок 1. Обзор доменов базы данных", width=23.0)

    figure_no, table_no = 2, 1
    figure_no, table_no = _add_domain(
        document,
        schema,
        "reference",
        "3. Справочники",
        "Справочники хранят относительно устойчивые значения: регионы, страны, научные звания, "
        "потребителей, источники и руководителей. Коды справочников неизменяемы и используются в экспорте.",
        "schema_reference.png",
        docs_dir,
        figure_no,
        table_no,
    )
    figure_no, table_no = _add_domain(
        document,
        schema,
        "oshm",
        "4. Организационная структура",
        "ОШС образует иерархию «регион → филиал → отдел → сотрудник». Рабочая группа принадлежит отделу, "
        "а участие сотрудника в группе хранится отдельной сущностью с периодом — это позволяет "
        "восстанавливать состав группы на дату документа.",
        None,
        docs_dir,
        figure_no,
        table_no,
    )
    figure_no, table_no = _add_domain(
        document,
        schema,
        "documents",
        "5. Документы",
        "Научный материал и телеграмма имеют собственные исходящие и входящие реквизиты. "
        "Участники, файлы, источники, страны и задачи связаны с документом через ассоциативные таблицы; "
        "адресация доклада относится только к телеграмме.",
        "schema_documents.png",
        docs_dir,
        figure_no,
        table_no,
    )
    figure_no, table_no = _add_domain(
        document,
        schema,
        "tasks",
        "6. Научные задачи и распределение",
        "Задача распределяется по узлам ОШС: региону, филиалу, отделу, рабочей группе или сотруднику. "
        "Назначение хранится в added_tasks; task_entity_links оставлена для совместимости со старыми данными.",
        "schema_tasks.png",
        docs_dir,
        figure_no,
        table_no,
    )
    figure_no, table_no = _add_domain(
        document,
        schema,
        "evaluations",
        "7. Оценки",
        "Оценка хранит код Б/И/П/В, дату выставления и эффект. Один список оценок объединяет оценки "
        "за отчётный период; оценка может относиться к материалу и/или телеграмме.",
        "schema_evaluations.png",
        docs_dir,
        figure_no,
        table_no,
    )
    figure_no, table_no = _add_domain(
        document,
        schema,
        "import",
        "8. Импорт оценок",
        "Импорт принимает текстовый файл фиксированной ширины, определяет схему по длине строки, "
        "ищет документ по филиалу, исходящему номеру и месяцу и создаёт/обновляет оценку. "
        "Журнал и строки импорта — служебные таблицы, они не участвуют в обмене дельтами.",
        None,
        docs_dir,
        figure_no,
        table_no,
    )
    figure_no, table_no = _add_domain(
        document,
        schema,
        "exchange",
        "9. Обмен изменениями",
        "Каждое создание, изменение и удаление tracked-сущности фиксируется в changes. "
        "Экспорт сериализует только changed_fields; после успешного экспорта записи changes удаляются.",
        None,
        docs_dir,
        figure_no,
        table_no,
    )
    _add_service(document)
    _add_associations(document, schema, table_no)
    table_no += 1
    _add_fk_summary(document, schema, table_no)
    _add_maintenance(document)

    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return output
