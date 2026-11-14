"""Тесты импорта оценок из текстовых файлов."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import EvaluationValue, MaterialType
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import (
    Branch,
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    TerritorialUnit,
)
from internal_correspondence.text_import import Importer, ImporterConfig
from internal_correspondence.text_import.matcher import _parse_year_month
from internal_correspondence.text_import.models import FieldSpec, LayoutScheme
from internal_correspondence.text_import.scheme import detect_schemes


def _scheme() -> LayoutScheme:
    return LayoutScheme(
        name="fixed",
        mode="fixed",
        header_mode="skip",
        fields=[
            FieldSpec("branch_part_1", "string", 1, 2, True),
            FieldSpec("branch_part_2", "string", 4, 1, True),
            FieldSpec("branch_part_3", "string", 6, 2, True),
            FieldSpec("outgoing_no", "string", 8, 10, True),
            FieldSpec("year_month", "string", 18, 6, True),
            FieldSpec("value", "string", 24, 1, False),
            FieldSpec("evaluation_date", "date", 25, 10, False, "DD.MM.YYYY"),
        ],
    )


def _line(value: str = "П", out: str = "1234567890") -> str:
    return f"01 1 01{out}202603{value}05.03.2026"


def _config(tmp_path: Path) -> ImporterConfig:
    storage = tmp_path / "storage"
    storage.mkdir()
    schemes = tmp_path / "schemes"
    schemes.mkdir()
    rules = tmp_path / "rules.json"
    rules.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "material",
                        "entity": "material",
                        "composite_keys": ["branch_part_1", "branch_part_2", "branch_part_3"],
                        "conditions": ["year_month_equal"],
                        "lookup": {
                            "table": "scientific_materials",
                            "outgoing_no": "outgoing_no",
                            "year_month": "year_month",
                            "value": "value",
                            "evaluation_date": "evaluation_date",
                        },
                        "match": ["branch_id", "outgoing_number"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ImporterConfig(storage, schemes, rules, storage_subdir="Импорт")


def _engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        unit = TerritorialUnit(id="TU1", name="Регион")
        branch = Branch(
            id="01-1-01",
            name="Филиал",
            short_name="Ф1",
            territorial_unit_id=unit.id,
        )
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="1234567890",
            outgoing_date=date(2026, 3, 5),
            name="Материал",
            branch_id=branch.id,
        )
        session.add_all([unit, branch, material])
        session.commit()
    return engine


def test_import_creates_list_and_evaluation(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    source = tmp_path / "data.txt"
    source.write_text("header\n" + _line() + "\n", encoding="utf-8")
    config = _config(tmp_path)
    importer = Importer(config, engine)
    importer.load_file(source)
    importer.load_rules()
    importer.set_scheme(_scheme())
    importer.set_rule_by_name("material")
    importer.set_document("DOC-1", date(2026, 3, 10))
    report = importer.validate()
    assert report.valid_count == 1
    preview = importer.preview_matches()
    assert preview.matched_count == 1
    result = importer.import_to_db()
    assert result.counts.matched == 1
    assert result.counts.imported == 1
    assert result.log_id > 0
    importer.close()

    with Session(engine) as session:
        lists = list(session.scalars(select(EvaluationList)))
        assert len(lists) == 1
        assert lists[0].number == "DOC-1"
        assert lists[0].date == date(2026, 3, 10)
        evaluation = session.scalars(select(Evaluation)).one()
        assert evaluation.value == EvaluationValue.USEFUL
        assert evaluation.date == date(2026, 3, 5)
        material = session.scalars(select(ScientificMaterial)).one()
        assert evaluation in material.evaluations


def test_duplicate_evaluation_update_does_not_create_second(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    source = tmp_path / "data.txt"
    source.write_text("header\n" + _line("П") + "\n", encoding="utf-8")
    config = _config(tmp_path)
    first = Importer(config, engine)
    first.load_file(source)
    first.load_rules()
    first.set_scheme(_scheme())
    first.set_rule_by_name("material")
    first.set_document("DOC-1", date(2026, 3, 10))
    first.import_to_db()
    first.close()

    source.write_text("header\n" + _line("В") + "\n", encoding="utf-8")
    second = Importer(config, engine)
    second.load_file(source)
    second.load_rules()
    second.set_scheme(_scheme())
    second.set_rule_by_name("material")
    second.set_document("DOC-1", date(2026, 3, 10))
    second.validate()
    preview = second.preview_matches()
    assert preview.duplicate_count == 1
    result = second.import_to_db(
        duplicate_actions={preview.results[0].row.row_no: "update"},
        force_duplicate=True,
    )
    assert result.counts.skipped == 0
    second.close()
    with Session(engine) as session:
        evaluation = session.scalars(select(Evaluation)).one()
        assert evaluation.value == EvaluationValue.IMPORTANT


def test_unmatched_row_is_logged(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    source = tmp_path / "data.txt"
    source.write_text("header\n" + _line(out="0000000000") + "\n", encoding="utf-8")
    config = _config(tmp_path)
    importer = Importer(config, engine)
    importer.load_file(source)
    importer.load_rules()
    importer.set_scheme(_scheme())
    importer.set_rule_by_name("material")
    importer.set_document("DOC-1", date(2026, 3, 10))
    importer.validate()
    preview = importer.preview_matches()
    assert preview.unmatched_count == 1
    result = importer.import_to_db()
    assert result.counts.unmatched == 1
    assert result.counts.matched == 0
    importer.close()
    with Session(engine) as session:
        assert session.scalars(select(Evaluation)).first() is None


def test_delimited_scheme_detection_and_cp1251(tmp_path: Path) -> None:
    scheme = LayoutScheme(
        name="delimited",
        mode="delimited",
        delimiter=";",
        header_mode="skip",
        fields=[
            FieldSpec("branch_part_1", "string", required=True),
            FieldSpec("branch_part_2", "string", required=True),
            FieldSpec("branch_part_3", "string", required=True),
            FieldSpec("outgoing_no", "string", required=True),
            FieldSpec("year_month", "string", required=True),
        ],
    )
    lines = ["Филиал;Часть;Код;Номер;Период", "01;1;01;1234567890;202603"]
    matches = detect_schemes(lines, [scheme])
    assert matches[0].matched

    source = tmp_path / "data.csv"
    source.write_text("\n".join(lines) + "\n", encoding="cp1251")
    importer = Importer(_config(tmp_path), _engine(tmp_path))
    info = importer.load_file(source)
    assert info.encoding.lower() in {"cp1251", "windows-1251"}
    importer.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("202603", (2026, 3)),
        ("032026", (2026, 3)),
        ("112025", (2025, 11)),
        ("202511", (2025, 11)),
        ("132025", None),
        ("202513", None),
        ("2026", None),
        ("abcdef", None),
    ],
)
def test_year_month_accepts_year_first_and_month_first(value: str, expected) -> None:
    """Период в файле может быть как ГГГГММ, так и ММГГГГ."""
    assert _parse_year_month(value) == expected
