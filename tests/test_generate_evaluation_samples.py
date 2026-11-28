"""Тесты генератора тестовых данных для импорта оценок."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import (
    Branch,
    Country,
    MaterialType,
    ScientificMaterial,
    TerritorialUnit,
    Telegram,
    TelegramType,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def generator():
    """Загружает scripts_dev/generate_evaluation_samples.py как модуль."""
    spec = importlib.util.spec_from_file_location(
        "generate_evaluation_samples",
        PROJECT_ROOT / "scripts_dev" / "generate_evaluation_samples.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.bootstrap(PROJECT_ROOT)
    return module


def _make_db(tmp_path: Path, branch_ids=("11-1-12", "11-1-13")):
    """Создаёт временную базу с документами нескольких филиалов."""
    engine = create_engine(f"sqlite:///{tmp_path / 'gen.db'}", future=True)
    Base.metadata.create_all(engine)
    counter = 0
    with Session(engine) as session:
        unit = TerritorialUnit(id="TU1", name="Регион")
        country = Country(id="РФ", name="Россия")
        session.add_all([unit, country])
        session.flush()
        for branch_id in branch_ids:
            branch = Branch(
                id=branch_id,
                name="Филиал",
                short_name="Ф1",
                territorial_unit_id=unit.id,
            )
            session.add(branch)
            session.flush()
            for index in range(10):
                counter += 1
                session.add(
                    ScientificMaterial(
                        type=MaterialType(index % 6),
                        outgoing_number=f"ИСХ-{counter:05d}",
                        outgoing_date=date(2025, index % 12 + 1, 10),
                        name="Материал",
                        branch_id=branch.id,
                        cost=None,
                        countries=[country],
                    )
                )
            for index in range(6):
                counter += 1
                session.add(
                    Telegram(
                        type=TelegramType(index % 3),
                        outgoing_number=f"ТЛГ-{counter:05d}",
                        outgoing_date=date(2025, index % 12 + 1, 12),
                        name="Телеграмма",
                        branch_id=branch.id,
                    )
                )
        session.commit()
    return engine


def test_generator_writes_two_files_and_manifest(generator, tmp_path: Path) -> None:
    """Генератор создаёт оба файла нужной длины и отчёт."""
    engine = _make_db(tmp_path)
    out = tmp_path / "out"
    code = generator.main(
        [
            "--db",
            str(tmp_path / "gen.db"),
            "--project",
            str(PROJECT_ROOT),
            "--out",
            str(out),
            "--quiet",
        ]
    )
    assert code == 0

    evaluation = (out / "evaluation_data_139.txt").read_text(encoding="utf-8")
    effect = (out / "effect_101.txt").read_text(encoding="utf-8")
    evaluation_lines = evaluation.splitlines()
    effect_lines = effect.splitlines()
    assert evaluation_lines and effect_lines
    assert len(evaluation_lines) == len(effect_lines)
    # Одна строка испорчена (3%), остальные — ровно по 139 и 101 символу.
    assert sum(1 for line in evaluation_lines if len(line) == 139) >= len(evaluation_lines) - 1
    assert sum(1 for line in effect_lines if len(line) == 101) >= len(effect_lines) - 1

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["rows_per_file"] == len(evaluation_lines)
    assert manifest["checks"]["evaluation"]["rows"] == len(evaluation_lines)
    assert manifest["checks"]["evaluation"]["mismatches"] == []
    assert manifest["checks"]["effect"]["mismatches"] == []
    with Session(engine) as session:
        total = len(
            list(session.scalars(select(ScientificMaterial)))
        ) + len(list(session.scalars(select(Telegram))))
    assert manifest["rows_per_file"] == round(0.40 * total)


def test_generator_respects_detected_scheme(generator, tmp_path: Path) -> None:
    """Первую строку импортёр распознаёт как нужную схему фиксированной ширины."""
    from internal_correspondence.text_import.scheme import (
        detect_scheme_by_length,
        load_schemes,
    )

    _make_db(tmp_path)
    out = tmp_path / "out"
    generator.main(
        [
            "--db",
            str(tmp_path / "gen.db"),
            "--project",
            str(PROJECT_ROOT),
            "--out",
            str(out),
            "--quiet",
        ]
    )
    schemes = load_schemes(PROJECT_ROOT / "schemes")
    for name, length in (("evaluation_data_139.txt", 139), ("effect_101.txt", 101)):
        lines = (out / name).read_text(encoding="utf-8").splitlines()
        matches = [item for item in detect_scheme_by_length(lines, schemes) if item.matched]
        assert len(matches) == 1, name
        assert matches[0].scheme.line_length == length


def test_generator_matches_about_85_percent(generator, tmp_path: Path) -> None:
    """Доля совпавших строк соответствует параметру --matched-share."""
    _make_db(tmp_path)
    out = tmp_path / "out"
    generator.main(
        [
            "--db",
            str(tmp_path / "gen.db"),
            "--project",
            str(PROJECT_ROOT),
            "--out",
            str(out),
            "--share",
            "1.0",
            "--quiet",
        ]
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    checks = manifest["checks"]["evaluation"]
    assert 0.80 <= checks["matched_share"] <= 0.95
    assert len(checks["problems"]) == 1


def test_generator_maps_branch_ids_to_new_format(generator, tmp_path: Path) -> None:
    """Тестовые идентификаторы филиалов заменяются кодами вида «11-1-12»."""
    _make_db(tmp_path, branch_ids=("BR-001", "BR-002"))
    out = tmp_path / "out"
    generator.main(
        [
            "--db",
            str(tmp_path / "gen.db"),
            "--project",
            str(PROJECT_ROOT),
            "--out",
            str(out),
            "--quiet",
            "--branch-map",
            "BR-001=11-1-12,BR-002=11-1-13",
        ]
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["branch_codes"] == {"BR-001": "11-1-12", "BR-002": "11-1-13"}
    assert manifest["warnings"] == []
    lines = (out / "evaluation_data_139.txt").read_text(encoding="utf-8").splitlines()
    prefixes = {line[:7] for line in lines}
    assert prefixes <= {"11 1 12", "11 1 13"}


def test_generator_warns_about_test_branch_ids(generator, tmp_path: Path) -> None:
    """Без карты кодов генератор пишет в строках синтетические коды и предупреждает."""
    _make_db(tmp_path, branch_ids=("BR-001",))
    out = tmp_path / "out"
    generator.main(
        [
            "--db",
            str(tmp_path / "gen.db"),
            "--project",
            str(PROJECT_ROOT),
            "--out",
            str(out),
            "--quiet",
        ]
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["branch_codes"]["BR-001"] == "11-1-12"
    assert any("BR-001" in item for item in manifest["warnings"])
