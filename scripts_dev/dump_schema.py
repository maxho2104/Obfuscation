"""Генерация DOCX-описания схемы БД и диаграмм.

Запуск из корня проекта:
    .venv\\Scripts\\python.exe scripts_dev\\dump_schema.py --output docs\\database.docx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for path in (str(PROJECT_ROOT), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from schema_docs.diagrams import render_all  # noqa: E402
from schema_docs.docx_builder import build  # noqa: E402
from schema_docs.model import collect_schema  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Собрать описание схемы БД в DOCX")
    parser.add_argument(
        "--output",
        default="docs/database.docx",
        help="путь к итоговому DOCX (по умолчанию docs/database.docx)",
    )
    parser.add_argument(
        "--diagrams-dir",
        default="docs",
        help="каталог для PNG-диаграмм (по умолчанию docs)",
    )
    parser.add_argument(
        "--no-diagrams",
        action="store_true",
        help="не перерисовывать диаграммы, использовать существующие PNG",
    )
    args = parser.parse_args(argv)

    output = Path(args.output).resolve()
    diagrams_dir = Path(args.diagrams_dir).resolve()
    schema = collect_schema()
    print(f"Таблиц в схеме: {len(schema)}")

    if not args.no_diagrams:
        paths = render_all(schema, diagrams_dir)
        for path in paths:
            print(f"Диаграмма: {path}")

    result = build(schema, output, diagrams_dir)
    print(f"Документ: {result} ({result.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
