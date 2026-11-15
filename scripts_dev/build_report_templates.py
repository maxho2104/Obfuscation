"""Собирает DOCX-шаблоны строго на основе предоставленных образцов.

Скрипт начинает с копии исходного Word-файла и заменяет только текстовые
слоты и строки данных. Геометрия страниц, стили, колонтитулы, таблицы и
рисунок абзацев наследуются от образца.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "scripts_dev" / "report_template_sources"
OUTPUT_DIR = PROJECT_ROOT / "internal_correspondence" / "reports" / "templates"
MONTH_SOURCE = SOURCE_DIR / "monthly_source.docx"
HALFYEAR_SOURCE = SOURCE_DIR / "halfyear_source.docx"
FONT_NAME = "Times New Roman"


def _clear_paragraph(paragraph) -> None:
    """Удаляет содержимое абзаца, сохраняя его свойства и стиль."""
    properties = paragraph._p.pPr
    for child in list(paragraph._p):
        if child is not properties:
            paragraph._p.remove(child)


def _write_paragraph(
    paragraph,
    parts: str | Sequence[tuple[str, bool, bool]],
    *,
    alignment: WD_ALIGN_PARAGRAPH | None = None,
    size: float = 12,
) -> None:
    """Записывает текст в существующий абзац без изменения его геометрии."""
    _clear_paragraph(paragraph)
    if alignment is not None:
        paragraph.alignment = alignment
    normalized: Iterable[tuple[str, bool, bool]]
    if isinstance(parts, str):
        normalized = ((parts, False, False),)
    else:
        normalized = parts
    for text, bold, italic in normalized:
        run = paragraph.add_run(text)
        run.font.name = FONT_NAME
        run.font.size = Pt(size)
        run.bold = bold
        run.italic = italic
        fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn("w:ascii"), FONT_NAME)
        fonts.set(qn("w:hAnsi"), FONT_NAME)
        fonts.set(qn("w:eastAsia"), FONT_NAME)


def _write_cell(
    cell, text: str, *, bold: bool = False, size: float = 12
) -> None:
    """Меняет текст ячейки, сохраняя свойства ячейки и первого абзаца."""
    paragraph = cell.paragraphs[0]
    _write_paragraph(paragraph, ((text, bold, False),), size=size)
    for extra in list(cell.paragraphs[1:]):
        cell._tc.remove(extra._p)


def _strip_vertical_merge(cell) -> None:
    """Убирает с шаблонной строки продолжение вертикального объединения."""
    properties = cell._tc.tcPr
    if properties is None:
        return
    merge = properties.find(qn("w:vMerge"))
    if merge is not None:
        properties.remove(merge)


def _remove_rows(table, indexes: Sequence[int]) -> None:
    for index in sorted(indexes, reverse=True):
        table._tbl.remove(table.rows[index]._tr)


def _keep_row_together(row) -> None:
    """Запрещает разрывать одну строку таблицы между страницами."""
    properties = row._tr.get_or_add_trPr()
    if properties.find(qn("w:cantSplit")) is None:
        properties.append(OxmlElement("w:cantSplit"))


def _prepare_month_table(document: Document) -> None:
    table = document.tables[0]
    _write_cell(table.cell(0, 0), "{%tr for row in task_rows %}")
    _write_cell(table.cell(0, 1), "")
    _write_cell(table.cell(1, 0), "{{ row.label }}")
    _write_cell(
        table.cell(1, 1),
        "– {{ row.current }} ({{ row.previous }})"
        "{% if loop.last %}.{% else %};{% endif %}",
    )
    _write_cell(table.cell(2, 0), "{%tr endfor %}")
    _write_cell(table.cell(2, 1), "")
    _remove_rows(table, (3, 4, 5, 6))


def build_monthly_template() -> Path:
    """Создаёт месячный шаблон с единственной таблицей из образца."""
    output = OUTPUT_DIR / "monthly_analysis.docx"
    shutil.copy2(MONTH_SOURCE, output)
    document = Document(output)
    paragraphs = document.paragraphs

    _write_paragraph(
        paragraphs[0],
        "{{ draft.recipient or 'Директору научной организации' }}",
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )
    _write_paragraph(
        paragraphs[3],
        "В {{ month_name }} {{ year }} года из {{ branch.name }} филиала "
        "({{ branch.territorial_unit }}) представлено {{ materials_total.current }} "
        "(в {{ month_name }} {{ previous_year }} года – {{ materials_total.previous }}) "
        "научных материалов: {% for row in material_types %}{{ row.label|lower }} – "
        "{{ row.current }} ({{ row.previous }}){% if not loop.last %}, {% else %}. "
        "{% endif %}{% endfor %}В ходе практической работы создано "
        "{{ monthly.technical_documents.current }} "
        "({{ monthly.technical_documents.previous }}) технических документов.",
    )
    _write_paragraph(
        paragraphs[4],
        "По основным научным задачам (ОЗ) выполнено "
        "{{ monthly.main_materials.current }} ({{ monthly.main_materials.previous }}) "
        "научных работ, в том числе:",
    )
    _prepare_month_table(document)
    _write_paragraph(
        paragraphs[5],
        "По другим научным задачам проведено {{ monthly.other_materials.current }} "
        "({{ monthly.other_materials.previous }}) работ.",
    )
    _write_paragraph(
        paragraphs[6],
        "Всего получено {{ evaluated_materials.current }} "
        "({{ evaluated_materials.previous }}) оценок, из них по основным научным "
        "задачам – {{ evaluated_main_materials.current }} "
        "({{ evaluated_main_materials.previous }}), в том числе:",
    )
    for index, paragraph_index in enumerate((7, 8, 9)):
        suffix = "." if index == 2 else ";"
        _write_paragraph(
            paragraphs[paragraph_index],
            "«{{ monthly.evaluation_rows["
            + str(index)
            + "].label }}» – {{ monthly.evaluation_rows["
            + str(index)
            + "].current }} ({{ monthly.evaluation_rows["
            + str(index)
            + "].previous }}), из них по ОЗ – {{ monthly.evaluation_rows["
            + str(index)
            + "].main_current }} ({{ monthly.evaluation_rows["
            + str(index)
            + "].main_previous }}): исх. №№ {{ monthly.evaluation_rows["
            + str(index)
            + "].details }}"
            + suffix,
        )
    _write_paragraph(
        paragraphs[10],
        "Анализ представленных в {{ month_name }} {{ year }} года научных "
        "материалов по сравнению с аналогичным периодом прошлого года в целом "
        "свидетельствует о {{ monthly.materials_trend }} количественных "
        "показателей работы.",
    )
    _write_paragraph(
        paragraphs[11],
        "При этом количество представленных технических документов и образцов "
        "продукции свидетельствует о {{ monthly.technical_products_trend }}, "
        "разработанных по ОЗ – о {{ monthly.main_materials_trend }}. Разница по "
        "материалам, полученным с помощью экспериментального оборудования, "
        "составила {{ monthly.experimental_difference }}.",
    )
    _write_paragraph(
        paragraphs[12],
        "Общее количество полученных оценок свидетельствует о "
        "{{ monthly.evaluations_trend }}.",
    )
    _write_paragraph(
        paragraphs[13],
        "В {{ month_name }} {{ year }} года поступило {{ telegrams_total.current }} "
        "(в {{ month_name }} {{ previous_year }} года – {{ telegrams_total.previous }}) "
        "телеграмм. Оценено – {{ reported_telegrams.current }} "
        "({{ reported_telegrams.previous }}), из них были доложены:",
    )
    for index, paragraph_index in enumerate((14, 15)):
        _write_paragraph(
            paragraphs[paragraph_index],
            "«{{ monthly.telegram_report_rows["
            + str(index)
            + "].label }}» – {{ monthly.telegram_report_rows["
            + str(index)
            + "].current }} ({{ monthly.telegram_report_rows["
            + str(index)
            + "].previous }}): исх. №№ {{ monthly.telegram_report_rows["
            + str(index)
            + "].details }}"
            + (";" if index == 0 else "."),
        )
    _write_paragraph(
        paragraphs[16],
        "Общий процент доложенных – {{ reported_percent }}% "
        "({{ monthly.reported_percent_previous }}%).",
    )
    _write_paragraph(
        paragraphs[17],
        "Анализ представленных в {{ month_name }} {{ year }} года телеграмм по "
        "сравнению с аналогичным периодом прошлого года в целом свидетельствует "
        "о {{ monthly.telegrams_trend }} количественных показателей. Количество "
        "доложенных телеграмм свидетельствует о {{ monthly.reported_trend }}.",
    )
    _write_paragraph(
        paragraphs[18],
        "{{ draft.significant_results or 'Значимые результаты не указаны.' }}",
    )
    _write_paragraph(
        paragraphs[19],
        "{{ draft.plan_execution or 'Сведения о выполнении плана не указаны.' }}",
    )
    _write_paragraph(paragraphs[20], "Если есть недостатки по научным работам и телеграммам:")
    _write_paragraph(paragraphs[21], "К наиболее проблемным следует отнести следующие материалы:")
    _write_paragraph(paragraphs[22], "{{ draft.shortcomings or 'Недостатки не указаны.' }}")
    for index in (23, 24):
        _write_paragraph(paragraphs[index], "")
    _write_paragraph(paragraphs[25], "Или:")
    _write_paragraph(paragraphs[26], "{{ draft.conclusion or 'Итоговый вывод не указан.' }}")
    _write_paragraph(
        paragraphs[27],
        "{{ draft.plan_execution or 'Задачи на следующий период не указаны.' }}",
    )
    _write_paragraph(paragraphs[28], "Или:")
    _write_paragraph(paragraphs[29], "{{ draft.proposals or 'Предложения не указаны.' }}")
    _write_paragraph(
        paragraphs[33],
        "{{ draft.signatory_position or 'Заместитель директора по научной работе профессор' }}"
        "                      {{ draft.signatory_name or 'И.Фамилия' }}",
    )
    _write_paragraph(paragraphs[36], "«      » {{ month_name }} {{ year }} г.")
    document.save(output)
    return output


def _prepare_halfyear_telegram_table(document: Document) -> None:
    table = document.tables[0]
    for column, cell in enumerate(table.rows[2].cells):
        _write_cell(
            cell,
            "{%tr for row in halfyear.telegram_table_rows %}"
            if column == 1
            else "",
            size=10,
        )
    values = (
        "{{ row.department }}",
        "{{ row.workgroup }}",
        "{{ row.group_urgent }}",
        "{{ row.department_urgent }}",
        "{{ row.group_reported }}",
        "{{ row.department_reported }}",
        "{{ row.group_total }}",
        "{{ row.department_total }}",
    )
    for cell, value in zip(table.rows[4].cells, values):
        _strip_vertical_merge(cell)
        _write_cell(cell, value, size=10)
    _keep_row_together(table.rows[4])
    _write_cell(table.cell(5, 0), "{%tr endfor %}", size=10)
    for cell in table.rows[5].cells[1:]:
        _write_cell(cell, "", size=10)
    total_values = (
        "Итого",
        "Итого",
        "{{ halfyear.telegram_table_total.urgent }}",
        "{{ halfyear.telegram_table_total.urgent }}",
        "{{ halfyear.telegram_table_total.reported }}",
        "{{ halfyear.telegram_table_total.reported }}",
        "{{ halfyear.telegram_table_total.total }}",
        "{{ halfyear.telegram_table_total.total }}",
    )
    for cell, value in zip(table.rows[7].cells, total_values):
        _strip_vertical_merge(cell)
        _write_cell(cell, value, bold=True, size=10)
    _keep_row_together(table.rows[7])
    _remove_rows(table, (3, 6))


def _prepare_halfyear_material_table(document: Document) -> None:
    table = document.tables[1]
    _write_cell(table.cell(1, 0), "{%tr for row in halfyear.material_table_rows %}")
    for cell in table.rows[1].cells[1:]:
        _write_cell(cell, "")
    material_order = (2, 5, 0, 1, 3, 4)
    values = ["{{ row.label }}"] + [
        "{{ row.type_values[" + str(index) + "] }}" for index in material_order
    ] + ["{{ row.total }}"]
    for cell, value in zip(table.rows[2].cells, values):
        _write_cell(cell, value)
    _write_cell(table.cell(3, 0), "{%tr endfor %}")
    for cell in table.rows[3].cells[1:]:
        _write_cell(cell, "")
    total_values = ["Всего"] + [
        "{{ halfyear.material_table_total.type_values[" + str(index) + "] }}"
        for index in material_order
    ] + ["{{ halfyear.material_table_total.total }}"]
    for cell, value in zip(table.rows[4].cells, total_values):
        _write_cell(cell, value, bold=True)
    _remove_rows(table, (5, 6))


def _prepare_halfyear_evaluation_table(document: Document) -> None:
    table = document.tables[2]
    half = "{{ 'I' if period_number == 1 else 'II' }}"
    for column in (1, 3, 5):
        _write_cell(
            table.cell(1, column),
            half + " полугодие {{ year }} г.",
        )
    for column in (2, 4, 6):
        _write_cell(
            table.cell(1, column),
            half + " полугодие {{ previous_year }} г.",
        )
    _write_cell(table.cell(2, 0), "{%tr for row in halfyear.evaluation_table_rows %}")
    for cell in table.rows[2].cells[1:]:
        _write_cell(cell, "")
    values = ["{{ row.label }}"]
    for index in range(3):
        values.extend(
            (
                "{{ row.categories[" + str(index) + "].current }}",
                "{{ row.categories[" + str(index) + "].previous }}",
            )
        )
    for cell, value in zip(table.rows[3].cells, values):
        _write_cell(cell, value)
    _write_cell(table.cell(4, 0), "{%tr endfor %}")
    for cell in table.rows[4].cells[1:]:
        _write_cell(cell, "")
    total_values = ["Всего"]
    for index in range(3):
        total_values.extend(
            (
                "{{ halfyear.evaluation_table_total.categories["
                + str(index)
                + "].current }}",
                "{{ halfyear.evaluation_table_total.categories["
                + str(index)
                + "].previous }}",
            )
        )
    for cell, value in zip(table.rows[5].cells, total_values):
        _write_cell(cell, value, bold=True)
    _remove_rows(table, (6, 7))


def build_halfyear_template() -> Path:
    """Создаёт полугодовой шаблон с тремя таблицами из образца."""
    output = OUTPUT_DIR / "halfyear_analysis.docx"
    shutil.copy2(HALFYEAR_SOURCE, output)
    document = Document(output)
    paragraphs = document.paragraphs

    _write_paragraph(paragraphs[0], (("Анализ", True, False),), alignment=WD_ALIGN_PARAGRAPH.CENTER)
    _write_paragraph(paragraphs[1], (("научной деятельности", True, False),), alignment=WD_ALIGN_PARAGRAPH.CENTER)
    _write_paragraph(paragraphs[2], "{{ branch.short_name or branch.name }} филиала", alignment=WD_ALIGN_PARAGRAPH.CENTER)
    _write_paragraph(paragraphs[3], "за {{ period_label }} года", alignment=WD_ALIGN_PARAGRAPH.CENTER)
    _write_paragraph(paragraphs[5], (("1. Отработка телеграмм", True, False),), alignment=WD_ALIGN_PARAGRAPH.CENTER)
    _write_paragraph(
        paragraphs[7],
        "1.1 В {{ 'I' if period_number == 1 else 'II' }} полугодии {{ year }} года "
        "филиал направил {{ telegrams_total.current }} (в {{ 'I' if period_number == 1 "
        "else 'II' }} полугодии {{ previous_year }} года – {{ telegrams_total.previous }}, "
        "{{ halfyear.telegrams_trend }}) телеграмм, из которых:",
    )
    _write_paragraph(paragraphs[8], "тематические – {{ telegram_types[0].display }};")
    _write_paragraph(paragraphs[9], "«о достигнутых результатах» – {{ telegram_types[2].display }};")
    _write_paragraph(paragraphs[10], "«о ходе работ» – {{ telegram_types[1].display }}.")
    _write_paragraph(
        paragraphs[11],
        "Оценку «СДР» получили {{ halfyear.telegram_table_total.urgent }}, "
        "«ДР» – {{ halfyear.telegram_table_total.reported }}. Оцениваемость составила "
        "{{ reported_percent }}% ({{ halfyear.reported_percent_previous }}%).",
    )
    _prepare_halfyear_telegram_table(document)
    _write_paragraph(
        paragraphs[14],
        "Из общего количества оцененных телеграмм – {{ reported_telegrams.current }} "
        "({{ reported_telegrams.previous }}):",
    )
    _write_paragraph(paragraphs[15], "{%p for row in halfyear.department_report_rows %}")
    _write_paragraph(
        paragraphs[16],
        "{{ row.label }} направил {{ row.current }} ({{ row.previous }}) штук – "
        "{{ row.percent }}% ({{ row.percent_previous }}%);",
    )
    _write_paragraph(paragraphs[17], "{%p endfor %}")
    _write_paragraph(
        paragraphs[19],
        "Из представленных {{ halfyear.thematic.current }} "
        "({{ halfyear.thematic.previous }}) тематических телеграмм оценку «СДР» "
        "получили {{ halfyear.thematic_urgent.current }} "
        "({{ halfyear.thematic_urgent.previous }}), «ДР» – "
        "{{ halfyear.thematic_reported.current }} "
        "({{ halfyear.thematic_reported.previous }}). Оцениваемость – "
        "{{ halfyear.thematic_percent }}% ({{ halfyear.thematic_percent_previous }}%).",
    )
    _write_paragraph(paragraphs[20], "По количеству оцененных тематических телеграмм:")
    _write_paragraph(paragraphs[21], "{%p for row in halfyear.department_thematic_rows %}")
    _write_paragraph(
        paragraphs[22],
        "{{ row.label }} представил {{ row.current }} ({{ row.previous }}) штук – "
        "{{ row.percent }}% ({{ row.percent_previous }}%);",
    )
    _write_paragraph(paragraphs[23], "{%p endfor %}")
    _write_paragraph(
        paragraphs[24],
        "Из тематических телеграмм доложено и срочно доложено руководителю "
        "{{ halfyear.thematic_percent }}% ({{ halfyear.thematic_percent_previous }}%).",
    )
    _write_paragraph(paragraphs[25], "{%p for row in halfyear.department_report_rows %}")
    _write_paragraph(
        paragraphs[26],
        "{{ row.label }} – {{ row.percent }}% ({{ row.percent_previous }}%);",
    )
    _write_paragraph(paragraphs[27], "{%p endfor %}")
    _write_paragraph(paragraphs[28], "Среди рабочих групп: {{ halfyear.workgroup_thematic_text }}.")
    _write_paragraph(
        paragraphs[29],
        "В целом изменение процента докладываемости соответствует фактическим "
        "показателям отделов и групп.",
    )
    _write_paragraph(
        paragraphs[30],
        "Доложенные телеграммы и адресаты: {% for row in halfyear.telegram_details %}"
        "№ {{ row.number }} от {{ row.date }} ({{ row.leaders }})"
        "{% if not loop.last %}; {% else %}.{% endif %}{% endfor %}",
    )
    _write_paragraph(
        paragraphs[31],
        "Вместе с тем основными недостатками при разработке тематических "
        "документов остаются:",
    )
    _write_paragraph(paragraphs[32], "{{ draft.shortcomings or 'Недостатки не указаны.' }}")
    for index in range(33, 39):
        _write_paragraph(paragraphs[index], "")
    _write_paragraph(paragraphs[39], "{{ draft.conclusion or 'Итоговый вывод по телеграммам не указан.' }}")
    _write_paragraph(
        paragraphs[41],
        "1.2 Работа по предоставлению информации о достигнутых результатах "
        "ведется всеми группами. Всего направлено "
        "{{ halfyear.results_telegrams.current }} "
        "({{ halfyear.results_telegrams.previous }}) телеграмм.",
    )
    _write_paragraph(paragraphs[42], "{{ draft.plan_execution or 'Сведения о выполнении плана не указаны.' }}")
    _write_paragraph(
        paragraphs[43],
        ((
            "По совокупности количественно-качественных показателей места между "
            "рабочими группами по результатам отработки телеграмм распределились "
            "следующим образом:",
            True,
            True,
        ),),
    )
    _write_paragraph(paragraphs[44], "{%p for row in halfyear.workgroup_ranking_rows %}")
    _write_paragraph(paragraphs[45], "{{ row.place }} место – «{{ row.label }}»;")
    _write_paragraph(paragraphs[46], "{%p endfor %}")
    _write_paragraph(paragraphs[47], "")
    _write_paragraph(paragraphs[48], "{%p for row in halfyear.department_ranking_rows %}")
    _write_paragraph(paragraphs[49], "{{ row.place }} место – {{ row.label }};")
    _write_paragraph(paragraphs[50], "{%p endfor %}")
    _write_paragraph(
        paragraphs[53],
        ((
            "2. Отработка научных материалов (сообщений, документов, справок, "
            "образцов продукции и технических документов)",
            True,
            False,
        ),),
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )
    _write_paragraph(
        paragraphs[55],
        "Несмотря на большие объемы поступающей информации, количество научных "
        "материалов, направленных в Головной офис, определяется фактическими "
        "данными. Всего в {{ 'I' if period_number == 1 else 'II' }} полугодии "
        "{{ year }} года исполнено {{ materials_total.current }} "
        "({{ materials_total.previous }}, {{ halfyear.materials_trend }}) документов, "
        "из них сообщений {{ halfyear.message_materials.current }} "
        "({{ halfyear.message_materials.previous }}).",
    )
    _prepare_halfyear_material_table(document)
    _write_paragraph(
        paragraphs[58],
        "Больше всего документов среди отделов представили "
        "{{ halfyear.top_material_departments }}.",
    )
    _write_paragraph(paragraphs[59], "В отчетном периоде получены следующие оценки:")
    _prepare_halfyear_evaluation_table(document)
    _write_paragraph(
        paragraphs[62],
        "В целом количество оценок свидетельствует о "
        "{{ halfyear.evaluations_trend }}.",
    )
    _write_paragraph(
        paragraphs[63],
        "Условная стоимость по образцам продукции составила "
        "{{ material_cost.current }} рублей (в {{ previous_period_label }} – "
        "{{ material_cost.previous }} рублей).",
    )
    _write_paragraph(
        paragraphs[65],
        ((
            "По совокупности отработки научных материалов и ведения научной "
            "работы в филиале места между отделами распределились следующим образом:",
            True,
            True,
        ),),
    )
    _write_paragraph(paragraphs[66], "{%p for row in halfyear.department_ranking_rows %}")
    _write_paragraph(paragraphs[67], "{{ row.place }} место – {{ row.label }};")
    _write_paragraph(paragraphs[68], "{%p endfor %}")
    _write_paragraph(
        paragraphs[70],
        (("Наиболее значимые результаты организации и ведения научной работы:", True, False),),
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )
    _write_paragraph(paragraphs[71], "{{ draft.significant_results or 'Значимые результаты не указаны.' }}")
    _write_paragraph(
        paragraphs[72],
        (("Предложения по улучшению научной работы:", True, False),),
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )
    _write_paragraph(paragraphs[73], "{{ draft.proposals or 'Предложения не указаны.' }}")
    _write_paragraph(paragraphs[74], "{{ draft.signatory_position or 'Доктор наук' }}")
    _write_paragraph(
        paragraphs[75],
        "{{ draft.signatory_name or 'Х.ххххххх' }}",
        alignment=WD_ALIGN_PARAGRAPH.RIGHT,
    )
    _write_paragraph(paragraphs[76], "«      » __________ {{ year }} г.")
    document.save(output)
    return output


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (build_monthly_template(), build_halfyear_template()):
        print(path)


if __name__ == "__main__":
    main()
