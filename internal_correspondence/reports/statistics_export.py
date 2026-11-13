"""Выгрузка результатов статистических подсчётов в Excel (xlsx)."""

from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlsxImage
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from internal_correspondence.reports.statistics_service import StatisticsResult
from internal_correspondence.utils.string_resources import STRINGS

# Столбец, с которого выводится изображение графика (правее таблицы)
_CHART_ANCHOR_COLUMN = 2


def export_statistics(
    result: StatisticsResult,
    first_column_header: str,
    path: Path,
    chart_image_path: Optional[Path] = None,
) -> Path:
    """Сохраняет результат подсчёта в файл Excel.

    Лист содержит заголовок, период, сводку (средний балл), таблицу
    с итогами; при наличии — изображение графика под таблицей.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = STRINGS.tab_statistics

    bold = Font(bold=True)

    sheet.cell(row=1, column=1, value=result.title).font = bold
    sheet.cell(row=2, column=1, value=STRINGS.stats_period_prefix.format(label=result.period_label))
    if result.summary:
        sheet.cell(row=3, column=1, value=result.summary).font = bold

    header_row = 5
    headers = [first_column_header] + result.columns + [STRINGS.header_total]
    for column_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=header_row, column=column_index, value=header)
        cell.font = bold
        cell.alignment = Alignment(horizontal="center")

    row_index = header_row + 1
    for row in result.rows:
        label_cell = sheet.cell(row=row_index, column=1, value=row.label)
        if row.is_group:
            label_cell.font = bold
        else:
            label_cell.alignment = Alignment(indent=1)
        for column_index, value in enumerate(row.values, start=2):
            cell = sheet.cell(row=row_index, column=column_index, value=value)
            cell.alignment = Alignment(horizontal="center")
            if row.is_group:
                cell.font = bold
        total_cell = sheet.cell(
            row=row_index, column=len(headers), value=row.total
        )
        total_cell.font = bold
        total_cell.alignment = Alignment(horizontal="center")
        row_index += 1

    # Строка общего итога
    total_label = sheet.cell(row=row_index, column=1, value=STRINGS.row_grand_total)
    total_label.font = bold
    for column_index, value in enumerate(result.totals, start=2):
        cell = sheet.cell(row=row_index, column=column_index, value=value)
        cell.font = bold
        cell.alignment = Alignment(horizontal="center")
    grand_cell = sheet.cell(row=row_index, column=len(headers), value=result.grand_total)
    grand_cell.font = bold
    grand_cell.alignment = Alignment(horizontal="center")

    # Ширины колонок
    sheet.column_dimensions[get_column_letter(1)].width = max(
        30, max((len(row.label) for row in result.rows), default=0) + 4
    )
    for column_index in range(2, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(column_index)].width = 12

    # График под таблицей
    if chart_image_path is not None and chart_image_path.exists():
        image = XlsxImage(str(chart_image_path))
        anchor_row = row_index + 2
        image.anchor = f"{get_column_letter(_CHART_ANCHOR_COLUMN)}{anchor_row}"
        sheet.add_image(image)

    workbook.save(path)
    return path
