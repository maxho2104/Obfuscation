"""Отрисовка ER-диаграмм схемы БД в PNG (Pillow, без Graphviz)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from .model import TableInfo


CANVAS = (2400, 1500)
FONT_DIR = Path("C:/Windows/Fonts")
FONT_REGULAR = FONT_DIR / "arial.ttf"
FONT_BOLD = FONT_DIR / "arialbd.ttf"

COLORS = {
    "reference": ("#2E75B6", "#DEEBF7"),
    "oshm": ("#548235", "#E2EFDA"),
    "documents": ("#C55A11", "#FBE5D6"),
    "tasks": ("#7030A0", "#E9DFF3"),
    "evaluations": ("#BF9000", "#FFF2CC"),
    "import": ("#C00000", "#F8D7DA"),
    "exchange": ("#595959", "#E7E6E6"),
    "service": ("#404040", "#EDEDED"),
    "group": ("#7F7F7F", "#F2F2F2"),
}

INK = "#1F1F1F"
MUTED = "#595959"
LINE = "#7F7F7F"
WHITE = "#FFFFFF"


@dataclass
class Box:
    key: str
    x: int
    y: int
    w: int
    h: int
    title: str
    subtitle: str
    fields: List[str]
    color: Tuple[str, str]
    group: bool = False

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    size: int = 21,
    bold: bool = False,
) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    while size > 14:
        font = _font(path, size)
        if _text_width(draw, text, font) <= max_width:
            return font
        size -= 1
    return _font(path, size)


def _truncate(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    suffix = "…"
    while text and _text_width(draw, text + suffix, font) > max_width:
        text = text[:-1]
    return text + suffix


def _box_height(fields: Sequence[str]) -> int:
    return 92 + max(1, len(fields)) * 42 + 18


def _draw_box(draw: ImageDraw.ImageDraw, box: Box) -> None:
    header_color, body_color = box.color
    shadow = (box.x + 6, box.y + 6, box.x + box.w + 6, box.y + box.h + 6)
    draw.rounded_rectangle(shadow, radius=16, fill="#D9D9D9")

    if box.group:
        draw.rounded_rectangle(
            (box.x, box.y, box.x + box.w, box.y + box.h),
            radius=16,
            fill=body_color,
            outline=header_color,
            width=3,
        )
        draw.rounded_rectangle(
            (box.x, box.y, box.x + box.w, box.y + 64),
            radius=16,
            fill=header_color,
        )
        draw.rectangle((box.x, box.y + 44, box.x + box.w, box.y + 64), fill=header_color)
    else:
        draw.rounded_rectangle(
            (box.x, box.y, box.x + box.w, box.y + box.h),
            radius=16,
            fill=body_color,
            outline=header_color,
            width=3,
        )
        draw.rounded_rectangle(
            (box.x, box.y, box.x + box.w, box.y + 72),
            radius=16,
            fill=header_color,
        )
        draw.rectangle((box.x, box.y + 50, box.x + box.w, box.y + 72), fill=header_color)

    title_font = _fit(draw, box.title, box.w - 28, 28, bold=True)
    draw.text(
        (box.x + 14, box.y + 10),
        _truncate(draw, box.title, title_font, box.w - 28),
        font=title_font,
        fill=WHITE,
    )
    if box.subtitle:
        subtitle_font = _font(FONT_REGULAR, 19)
        draw.text(
            (box.x + 14, box.y + 46 if not box.group else box.y + 36),
            _truncate(draw, box.subtitle, subtitle_font, box.w - 28),
            font=subtitle_font,
            fill="#E6E6E6" if not box.group else "#F2F2F2",
        )

    if box.group:
        font = _font(FONT_REGULAR, 22)
        y = box.y + 82
        for line in box.fields:
            if y + 30 > box.y + box.h:
                break
            draw.text((box.x + 18, y), "• " + line, font=font, fill=INK)
            y += 34
        return

    y = box.y + 84
    for field in box.fields:
        if y + 36 > box.y + box.h:
            break
        badge = ""
        if field.startswith("PK "):
            badge, field = "PK", field[3:]
        elif field.startswith("FK "):
            badge, field = "FK", field[3:]
        if badge:
            badge_color = "#BF9000" if badge == "PK" else "#2E75B6"
            draw.rounded_rectangle(
                (box.x + 12, y + 2, box.x + 56, y + 28),
                radius=6,
                fill=badge_color,
            )
            badge_font = _font(FONT_BOLD, 15)
            draw.text(
                (box.x + 19, y + 5),
                badge,
                font=badge_font,
                fill=WHITE,
            )
            text_x = box.x + 66
        else:
            text_x = box.x + 14
        font = _fit(draw, field, box.x + box.w - text_x - 10, 20)
        draw.text(
            (text_x, y + 3),
            _truncate(draw, field, font, box.x + box.w - text_x - 10),
            font=font,
            fill=INK,
        )
        y += 42


def _anchor(box: Box, toward: Tuple[int, int]) -> Tuple[int, int, str]:
    cx, cy = box.center
    tx, ty = toward
    dx, dy = tx - cx, ty - cy
    if abs(dx) >= abs(dy):
        if dx >= 0:
            return box.x + box.w, cy, "right"
        return box.x, cy, "left"
    if dy >= 0:
        return cx, box.y + box.h, "bottom"
    return cx, box.y, "top"


def _arrow(
    draw: ImageDraw.ImageDraw,
    points: List[Tuple[int, int]],
    color: str = LINE,
    dashed: bool = False,
    width: int = 3,
) -> None:
    if dashed:
        for start, end in zip(points, points[1:]):
            _dashed_segment(draw, start, end, color, width)
    else:
        draw.line(points, fill=color, width=width, joint="curve")

    (x1, y1), (x2, y2) = points[-2], points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 15
    tip = (x2, y2)
    left = (x2 - ux * size + px * size * 0.55, y2 - uy * size + py * size * 0.55)
    right = (x2 - ux * size - px * size * 0.55, y2 - uy * size - py * size * 0.55)
    draw.polygon([tip, left, right], fill=color)


def _dashed_segment(
    draw: ImageDraw.ImageDraw,
    start: Tuple[int, int],
    end: Tuple[int, int],
    color: str,
    width: int,
) -> None:
    x1, y1 = start
    x2, y2 = end
    length = max(1.0, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
    dash, gap = 14, 9
    position = 0.0
    while position < length:
        part_end = min(position + dash, length)
        a = (x1 + (x2 - x1) * position / length, y1 + (y2 - y1) * position / length)
        b = (x1 + (x2 - x1) * part_end / length, y1 + (y2 - y1) * part_end / length)
        draw.line([a, b], fill=color, width=width)
        position += dash + gap


def _side_point(box: Box, side: str) -> Tuple[int, int]:
    """Точка на середине указанной стороны рамки."""
    if side == "left":
        return box.x, box.y + box.h // 2
    if side == "right":
        return box.x + box.w, box.y + box.h // 2
    if side == "top":
        return box.x + box.w // 2, box.y
    return box.x + box.w // 2, box.y + box.h


def _draw_edge(
    draw: ImageDraw.ImageDraw,
    boxes: Dict[str, Box],
    source: str,
    target: str,
    label: str = "",
    *,
    dashed: bool = False,
    label_offset: Tuple[int, int] = (0, 0),
    color: str = LINE,
    source_side: Optional[str] = None,
    target_side: Optional[str] = None,
    via: Sequence[Tuple[int, int]] = (),
    label_pos: Optional[Tuple[int, int]] = None,
) -> None:
    src = boxes[source]
    dst = boxes[target]
    if source_side:
        sx, sy = _side_point(src, source_side)
        sside = source_side
    else:
        sx, sy, sside = _anchor(src, dst.center)
    if target_side:
        ex, ey = _side_point(dst, target_side)
        eside = target_side
    else:
        ex, ey, eside = _anchor(dst, src.center)

    if via:
        points = [(sx, sy), *via, (ex, ey)]
    elif sside in ("left", "right") and eside in ("left", "right"):
        midx = (sx + ex) // 2
        points = [(sx, sy), (midx, sy), (midx, ey), (ex, ey)]
    elif sside in ("top", "bottom") and eside in ("top", "bottom"):
        midy = (sy + ey) // 2
        points = [(sx, sy), (sx, midy), (ex, midy), (ex, ey)]
    else:
        points = [(sx, sy), (sx, ey), (ex, ey)]

    # Убираем нулевые сегменты, чтобы стрелка не рисовала точку поверх линии.
    cleaned: List[Tuple[int, int]] = [points[0]]
    for point in points[1:]:
        if point != cleaned[-1]:
            cleaned.append(point)
    points = cleaned

    _arrow(draw, points, color=color, dashed=dashed)
    if label:
        if label_pos is not None:
            lx, ly = label_pos
        else:
            mid = points[len(points) // 2]
            font = _font(FONT_REGULAR, 20)
            text_w = _text_width(draw, label, font)
            lx = mid[0] + label_offset[0] - text_w // 2
            ly = mid[1] + label_offset[1] - 14
        font = _font(FONT_REGULAR, 20)
        text_w = _text_width(draw, label, font)
        draw.rounded_rectangle(
            (lx - 8, ly - 4, lx + text_w + 8, ly + 28),
            radius=5,
            fill=WHITE,
            outline=color,
            width=1,
        )
        draw.text((lx, ly), label, font=font, fill=color)


def _new_canvas(
    title: str,
    subtitle: str = "",
    size: Tuple[int, int] = CANVAS,
) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", size, WHITE)
    draw = ImageDraw.Draw(image)
    draw.text((50, 24), title, font=_font(FONT_BOLD, 40), fill="#1F3864")
    if subtitle:
        draw.text((52, 72), subtitle, font=_font(FONT_REGULAR, 22), fill=MUTED)
    return image, draw


def _legend(draw: ImageDraw.ImageDraw, y: int = 1390) -> None:
    font = _font(FONT_REGULAR, 20)
    x = 60
    draw.rounded_rectangle((x, y, x + 46, y + 26), radius=5, fill="#BF9000")
    draw.text((x + 7, y + 3), "PK", font=_font(FONT_BOLD, 15), fill=WHITE)
    draw.text((x + 56, y), "первичный ключ", font=font, fill=INK)
    x += 230
    draw.rounded_rectangle((x, y, x + 46, y + 26), radius=5, fill="#2E75B6")
    draw.text((x + 7, y + 3), "FK", font=_font(FONT_BOLD, 15), fill=WHITE)
    draw.text((x + 56, y), "внешний ключ", font=font, fill=INK)
    x += 220
    draw.line((x, y + 13, x + 70, y + 13), fill=LINE, width=3)
    draw.polygon([(x + 70, y + 13), (x + 54, y + 4), (x + 54, y + 22)], fill=LINE)
    draw.text((x + 82, y), "1:N / N:1", font=font, fill=INK)
    x += 240
    draw.line((x, y + 13, x + 70, y + 13), fill=LINE, width=3)
    draw.text((x + 82, y), "M:N (свёрнуто)", font=font, fill=INK)
    x += 300
    _dashed_segment(draw, (x, y + 13), (x + 70, y + 13), LINE, 3)
    draw.text((x + 82, y), "логическая/неявная связь", font=font, fill=INK)


def _table_box(
    schema: Dict[str, TableInfo],
    key: str,
    x: int,
    y: int,
    fields: Sequence[str],
    width: int = 500,
) -> Box:
    table = schema[key]
    labels = {column.name: column.label for column in table.columns}
    lines = []
    for field_name in fields:
        prefix = ""
        column = table.column(field_name)
        if column is not None:
            if column.primary_key:
                prefix = "PK "
            elif column.foreign_key:
                prefix = "FK "
        lines.append(f"{prefix}{labels.get(field_name, field_name)} ({field_name})")
    return Box(
        key=key,
        x=x,
        y=y,
        w=width,
        h=_box_height(lines),
        title=table.label,
        subtitle=table.name,
        fields=lines,
        color=COLORS.get(table.domain, COLORS["service"]),
    )


def _group_box(
    key: str,
    x: int,
    y: int,
    title: str,
    subtitle: str,
    lines: Sequence[str],
    width: int = 500,
) -> Box:
    return Box(
        key=key,
        x=x,
        y=y,
        w=width,
        h=_box_height(lines) + 20,
        title=title,
        subtitle=subtitle,
        fields=list(lines),
        color=COLORS["group"],
        group=True,
    )


def _finish(image: Image.Image, draw: ImageDraw.ImageDraw, boxes: Iterable[Box], path: Path) -> None:
    for box in boxes:
        _draw_box(draw, box)
    _legend(draw)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", dpi=(200, 200))


def _overview(schema: Dict[str, TableInfo], out: Path) -> None:
    image, draw = _new_canvas(
        "Схема базы данных: обзор доменов",
        "40 таблиц; ассоциативные таблицы свёрнуты в связи M:N",
        size=(2400, 1080),
    )
    domain_info = {
        "reference": ("Справочники", "6 таблиц", ["Регионы", "Страны", "Научные звания", "Потребители", "Источники", "Руководители"]),
        "oshm": ("Организационная структура", "5 таблиц", ["Филиалы", "Отделы", "Рабочие группы", "Сотрудники", "История участия"]),
        "documents": ("Документы", "4 таблицы", ["Научные материалы", "Телеграммы", "Адресация доклада", "Файлы"]),
        "evaluations": ("Оценки", "2 таблицы", ["Списки оценок", "Оценки документов", "Эффект"]),
        "tasks": ("Научные задачи", "3 таблицы", ["Задачи", "Назначения узлам ОШС"]),
        "import": ("Импорт оценок", "2 таблицы", ["Журнал импорта", "Строки импорта", "Сопоставление"]),
        "exchange": ("Обмен изменениями", "1 таблица", ["changes", "Дельта для ZIP"]),
        "service": ("Служебные объекты", "2 объекта", ["alembic_version", "import_matches (VIEW)"]),
    }
    positions = {
        "reference": (60, 110),
        "oshm": (620, 110),
        "documents": (1180, 110),
        "evaluations": (1740, 110),
        "tasks": (60, 470),
        "import": (620, 470),
        "exchange": (1180, 470),
        "service": (1740, 470),
    }
    boxes = {}
    for key, (title, count, lines) in domain_info.items():
        x, y = positions[key]
        boxes[key] = Box(
            key=key,
            x=x,
            y=y,
            w=500,
            h=290,
            title=title,
            subtitle=count,
            fields=lines,
            color=COLORS[key],
            group=True,
        )
    for box in boxes.values():
        _draw_box(draw, box)

    # Верхний ряд: справочники → ОШС → документы → оценки.
    _draw_edge(draw, boxes, "reference", "oshm", "1:N", label_pos=(555, 245))
    _draw_edge(draw, boxes, "oshm", "documents", "1:N", label_pos=(1115, 245))
    _draw_edge(draw, boxes, "documents", "evaluations", "1:N", label_pos=(1675, 245))
    # Нижний ряд: задачи и импорт связаны с документами/оценками; обмен — со всеми.
    _draw_edge(
        draw,
        boxes,
        "tasks",
        "documents",
        "M:N",
        dashed=True,
        source_side="top",
        target_side="bottom",
        via=[(310, 430), (1430, 430), (1430, 400)],
        label_pos=(760, 405),
    )
    _draw_edge(
        draw,
        boxes,
        "import",
        "evaluations",
        "создаёт",
        dashed=True,
        source_side="top",
        target_side="bottom",
        via=[(870, 430), (1990, 430), (1990, 400)],
        label_pos=(1520, 405),
    )
    _draw_edge(
        draw,
        boxes,
        "exchange",
        "documents",
        "change_id",
        dashed=True,
        source_side="top",
        target_side="bottom",
        via=[(1430, 440), (1430, 400)],
        label_pos=(1340, 410),
    )

    draw.text(
        (60, 800),
        "Документы связаны M:N со справочниками, ОШС, задачами и файлами; "
        "импорт читает документы и создаёт оценки.",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    draw.text(
        (60, 834),
        "Все изменяемые бизнес-сущности ссылаются на changes через change_id; "
        "служебные таблицы импорта в обмене не участвуют.",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    _legend(draw, 900)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", dpi=(200, 200))


def _reference(schema: Dict[str, TableInfo], out: Path) -> None:
    image, draw = _new_canvas(
        "Справочники и организационная структура",
        "Иерархия: регион → филиал → отдел → сотрудник; рабочая группа и история участия",
    )
    boxes = {
        "territorial_units": _table_box(schema, "territorial_units", 60, 110, ["id", "name"]),
        "branches": _table_box(schema, "branches", 620, 110, ["id", "name", "short_name", "territorial_unit_id"]),
        "departments": _table_box(schema, "departments", 1180, 110, ["id", "name", "short_name", "branch_id", "active"]),
        "employees": _table_box(schema, "employees", 1740, 110, ["id", "last_name", "first_name", "department_id", "academic_title_id"]),
        "academic_titles": _table_box(schema, "academic_titles", 60, 470, ["id", "name", "genitive"]),
        "working_groups": _table_box(schema, "working_groups", 1180, 470, ["id", "name", "department_id", "active"]),
        "workgroup_memberships": _table_box(schema, "workgroup_memberships", 1740, 470, ["id", "employee_id", "working_group_id", "start_date", "end_date"]),
        "countries": _table_box(schema, "countries", 60, 830, ["id", "name"]),
        "consumers": _table_box(schema, "consumers", 620, 830, ["id", "short_name", "name"]),
        "sources": _table_box(schema, "sources", 1180, 830, ["id", "type", "comment"]),
        "leaders": _table_box(schema, "leaders", 1740, 830, ["id", "active"]),
    }
    for box in boxes.values():
        _draw_box(draw, box)

    _draw_edge(draw, boxes, "territorial_units", "branches", "1:N")
    _draw_edge(draw, boxes, "branches", "departments", "1:N")
    _draw_edge(draw, boxes, "departments", "employees", "1:N")
    _draw_edge(draw, boxes, "academic_titles", "employees", "1:N", label_offset=(0, 20))
    _draw_edge(draw, boxes, "departments", "working_groups", "1:N")
    _draw_edge(draw, boxes, "employees", "workgroup_memberships", "1:N", label_offset=(0, 10))
    _draw_edge(draw, boxes, "working_groups", "workgroup_memberships", "1:N")
    _legend(draw, 1230)
    draw.text(
        (60, 1180),
        "Страны, потребители, источники и руководители связаны с документами "
        "(см. рисунок «Документы»).",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    image.save(out, "PNG", dpi=(200, 200))


def _documents(schema: Dict[str, TableInfo], out: Path) -> None:
    image, draw = _new_canvas(
        "Документы и участники",
        "N-N-связи документа с отделами, сотрудниками, группами, источниками, странами, задачами и файлами",
    )
    boxes = {
        "scientific_materials": _table_box(schema, "scientific_materials", 60, 110, ["id", "outgoing_number", "outgoing_date", "branch_id", "consumer_id"], 520),
        "branches": _table_box(schema, "branches", 640, 110, ["id", "name", "short_name"], 520),
        "file_records": _table_box(schema, "file_records", 1220, 110, ["id", "name", "extension", "path"], 520),
        "consumers": _table_box(schema, "consumers", 1800, 900, ["id", "short_name", "name"], 520),
        "telegrams": _table_box(schema, "telegrams", 60, 520, ["id", "outgoing_number", "outgoing_date", "branch_id", "report_type"], 520),
        "report_addresses": _table_box(schema, "report_addresses", 1220, 520, ["id", "telegram_id", "leader_id", "report_date"], 520),
        "leaders": _table_box(schema, "leaders", 1800, 520, ["id", "active"], 520),
    }
    boxes["participants"] = _group_box(
        "participants",
        640,
        520,
        "Участники документа",
        "M:N через ассоциативные таблицы",
        [
            "Отделы (departments)",
            "Сотрудники (employees)",
            "Рабочие группы (working_groups)",
            "Источники (sources)",
            "Страны (countries)",
            "Задачи (scientific_tasks)",
        ],
        520,
    )
    for box in boxes.values():
        _draw_box(draw, box)

    # Материал → филиал (FK, 1:N).
    _draw_edge(draw, boxes, "scientific_materials", "branches", "", source_side="right", target_side="left")
    # Материал → файлы: обход сверху, чтобы не пересекать филиал.
    _draw_edge(
        draw,
        boxes,
        "scientific_materials",
        "file_records",
        "",
        source_side="bottom",
        target_side="left",
        via=[(320, 450), (1200, 450), (1200, 250)],
    )
    # Телеграмма → файлы: обход справа от блока участников.
    _draw_edge(
        draw,
        boxes,
        "telegrams",
        "file_records",
        "",
        source_side="right",
        target_side="bottom",
        via=[(1200, 650), (1200, 450), (1480, 450)],
    )
    # Телеграмма → филиал: обход между материалом и телеграммой.
    _draw_edge(
        draw,
        boxes,
        "telegrams",
        "branches",
        "",
        source_side="top",
        target_side="left",
        via=[(320, 480), (600, 480), (600, 300)],
    )
    # Телеграмма → адресация доклада.
    _draw_edge(
        draw,
        boxes,
        "telegrams",
        "report_addresses",
        "",
        source_side="bottom",
        target_side="left",
        via=[(320, 940), (1200, 940), (1200, 650)],
    )
    _draw_edge(draw, boxes, "report_addresses", "leaders", "", source_side="right", target_side="left")
    # Материал → участники (M:N, свёрнуто).
    _draw_edge(
        draw,
        boxes,
        "scientific_materials",
        "participants",
        "",
        source_side="bottom",
        target_side="left",
        via=[(320, 500), (620, 500), (620, 600)],
    )
    # Телеграмма → участники (M:N, свёрнуто).
    _draw_edge(draw, boxes, "telegrams", "participants", "", source_side="right", target_side="left")
    # Материал → потребитель: дальний обход по нижнему полю, вне таблиц.
    consumer_bottom = boxes["consumers"].y + boxes["consumers"].h
    _draw_edge(
        draw,
        boxes,
        "scientific_materials",
        "consumers",
        "",
        source_side="left",
        target_side="left",
        via=[(30, 250), (30, consumer_bottom + 60), (1770, consumer_bottom + 60), (1770, consumer_bottom - 120)],
    )

    draw.text(
        (60, 1240),
        "Оба документа имеют собственные исходящие реквизиты и филиал; связи M:N "
        "вынесены в 14 ассоциативных таблиц и в разделах описания свёрнуты.",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    draw.text(
        (60, 1274),
        "Адресация доклада относится только к телеграмме; файлы и участники — к обоим типам документов.",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    _legend(draw, 1330)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", dpi=(200, 200))


def _evaluations(schema: Dict[str, TableInfo], out: Path) -> None:
    image, draw = _new_canvas(
        "Оценки и импорт",
        "Оценка связывает список оценок с материалами и телеграммами; импорт создаёт оценки",
        size=(2400, 1150),
    )
    boxes = {
        "evaluation_lists": _table_box(schema, "evaluation_lists", 60, 110, ["id", "number", "date"], 520),
        "evaluations": _table_box(schema, "evaluations", 640, 110, ["id", "value", "date", "effect", "evaluation_list_id"], 520),
        "scientific_materials": _table_box(schema, "scientific_materials", 1220, 110, ["id", "outgoing_number", "outgoing_date", "branch_id"], 520),
        "telegrams": _table_box(schema, "telegrams", 1800, 110, ["id", "outgoing_number", "outgoing_date", "branch_id"], 520),
        "import_log": _table_box(schema, "import_log", 60, 520, ["id", "doc_no", "doc_date", "file_name", "status"], 520),
        "import_rows": _table_box(schema, "import_rows", 640, 520, ["id", "import_id", "source_row_no", "status", "matched_entity_id"], 520),
        "changes": _table_box(schema, "changes", 1220, 520, ["id", "entity_name", "entity_pk", "operation_type"], 520),
    }
    for box in boxes.values():
        _draw_box(draw, box)

    _draw_edge(draw, boxes, "evaluation_lists", "evaluations", "1:N", source_side="right", target_side="left", label_pos=(575, 235))
    _draw_edge(draw, boxes, "evaluations", "scientific_materials", "", source_side="right", target_side="left")
    # Оценка → телеграмма: обход над первым рядом.
    _draw_edge(
        draw,
        boxes,
        "evaluations",
        "telegrams",
        "",
        source_side="top",
        target_side="top",
        via=[(900, 104), (2100, 104)],
    )
    _draw_edge(draw, boxes, "import_log", "import_rows", "1:N", source_side="right", target_side="left", label_pos=(575, 645))
    _draw_edge(draw, boxes, "import_rows", "evaluations", "", source_side="top", target_side="bottom", via=[(800, 460), (800, 400)])
    # Импорт → материал: обход справа от строк импорта.
    _draw_edge(
        draw,
        boxes,
        "import_rows",
        "scientific_materials",
        "",
        source_side="right",
        target_side="bottom",
        via=[(1190, 620), (1190, 450), (1480, 450)],
    )
    # Импорт → телеграмма: нижний обход вне таблиц.
    _draw_edge(
        draw,
        boxes,
        "import_rows",
        "telegrams",
        "",
        source_side="bottom",
        target_side="bottom",
        via=[(800, 850), (2100, 850)],
    )
    # changes показана отдельно: сквозная связь change_id описана в тексте.

    draw.text(
        (60, 900),
        "Один список оценок объединяет оценки за отчётный период; импорт ищет документ "
        "по филиалу, исходящему номеру и месяцу и создаёт/обновляет оценку.",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    draw.text(
        (60, 934),
        "Оценка хранит код Б/И/П/В, дату и эффект; для материала эффект дополнительно "
        "записывается в поле «Стоимость».",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    _legend(draw, 1000)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", dpi=(200, 200))


def _tasks(schema: Dict[str, TableInfo], out: Path) -> None:
    image, draw = _new_canvas(
        "Задачи, распределение и обмен",
        "Назначения задачи хранятся в added_tasks и ссылаются на узел ОШС полиморфно",
        size=(2400, 1150),
    )
    boxes = {
        "scientific_tasks": _table_box(schema, "scientific_tasks", 60, 110, ["id", "name", "type", "start_date", "end_date"], 520),
        "added_tasks": _table_box(schema, "added_tasks", 640, 110, ["id", "task_id", "node_type", "node_id"], 520),
        "task_entity_links": _table_box(schema, "task_entity_links", 1220, 110, ["id", "task_id", "entity_name", "entity_pk"], 520),
        "changes": _table_box(schema, "changes", 1800, 110, ["id", "entity_name", "entity_pk", "operation_type"], 520),
        "scientific_materials": _table_box(schema, "scientific_materials", 60, 520, ["id", "outgoing_number", "outgoing_date"], 520),
        "telegrams": _table_box(schema, "telegrams", 640, 520, ["id", "outgoing_number", "outgoing_date"], 520),
    }
    boxes["nodes"] = _group_box(
        "nodes",
        1220,
        520,
        "Узлы распределения",
        "node_type + node_id",
        [
            "region — территориальная единица",
            "branch — филиал",
            "department — отдел",
            "workgroup — рабочая группа",
            "employee — сотрудник",
        ],
        520,
    )
    for box in boxes.values():
        _draw_box(draw, box)

    _draw_edge(draw, boxes, "scientific_tasks", "added_tasks", "1:N", source_side="right", target_side="left", label_pos=(600, 235))
    # Задача → устаревшая связь с сущностями: обход под первым рядом.
    _draw_edge(
        draw,
        boxes,
        "scientific_tasks",
        "task_entity_links",
        "",
        source_side="bottom",
        target_side="left",
        via=[(320, 460), (1200, 460), (1200, 300)],
    )
    _draw_edge(draw, boxes, "scientific_tasks", "scientific_materials", "", source_side="bottom", target_side="top")
    # Задача → телеграмма: обход между назначением и строкой.
    _draw_edge(
        draw,
        boxes,
        "scientific_tasks",
        "telegrams",
        "",
        source_side="right",
        target_side="top",
        via=[(600, 300), (600, 480), (900, 480)],
    )
    # Назначение → узел ОШС: полиморфная связь.
    _draw_edge(
        draw,
        boxes,
        "added_tasks",
        "nodes",
        "",
        source_side="bottom",
        target_side="top",
        via=[(900, 500), (1480, 500)],
        dashed=True,
    )
    # changes: только смысловая связь, чтобы не тянуть линии через всю схему.
    draw.text(
        (1740, 600),
        "change_id",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    draw.text(
        (1740, 632),
        "у задач, назначений\nи старых связей",
        font=_font(FONT_REGULAR, 20),
        fill=MUTED,
        spacing=6,
    )

    draw.text(
        (60, 1000),
        "task_entity_links — устаревшая совместимая связь; новое распределение "
        "выполняется только через added_tasks (регион, филиал, отдел, группа, сотрудник).",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    draw.text(
        (60, 1034),
        "Задачи связаны M:N с материалами и телеграммами; обе связи хранятся в ассоциативных таблицах.",
        font=_font(FONT_REGULAR, 22),
        fill=MUTED,
    )
    _legend(draw, 1090)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", dpi=(200, 200))


def render_all(schema: Dict[str, TableInfo], output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        output_dir / "schema_overview.png",
        output_dir / "schema_reference.png",
        output_dir / "schema_documents.png",
        output_dir / "schema_evaluations.png",
        output_dir / "schema_tasks.png",
    ]
    _overview(schema, paths[0])
    _reference(schema, paths[1])
    _documents(schema, paths[2])
    _evaluations(schema, paths[3])
    _tasks(schema, paths[4])
    return paths


def domain_tables(schema: Dict[str, TableInfo], domain: str) -> List[TableInfo]:
    from .model import domain_tables as _domain_tables

    return _domain_tables(schema, domain)
