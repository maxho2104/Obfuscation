"""Декларативные правила сопоставления строк с документами."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select

from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.text_import.errors import MatcherError
from internal_correspondence.text_import.models import (
    LayoutScheme,
    MatchResult,
    MatchRule,
    MatchRuleSet,
    ParsedRow,
)

ENTITY_MODELS = {
    "material": ScientificMaterial,
    "telegram": Telegram,
}
ENTITY_TABLES = {
    "material": ScientificMaterial.__tablename__,
    "telegram": Telegram.__tablename__,
}


def load_rules(path: Path) -> MatchRuleSet:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MatcherError("rule_not_found", f"rules file not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MatcherError("rule_invalid", f"cannot read rules {path}: {exc}") from exc
    return rules_from_dict(data)


def rules_from_dict(data: Any) -> MatchRuleSet:
    if not isinstance(data, dict):
        raise MatcherError("rule_invalid", "rules root must be an object")
    items = data.get("rules")
    if not isinstance(items, list) or not items:
        raise MatcherError("rule_invalid", "rules list is empty")
    rules: List[MatchRule] = []
    for item in items:
        if not isinstance(item, dict):
            raise MatcherError("rule_invalid", "rule must be an object")
        rule = MatchRule(
            name=str(item.get("name", "")),
            entity=str(item.get("entity", "")),
            composite_keys=list(item.get("composite_keys", [])),
            conditions=list(item.get("conditions", [])),
            match=list(item.get("match", [])),
            target=dict(item.get("target", {})),
            raw=item,
        )
        if not rule.name:
            raise MatcherError("rule_invalid", "rule name is empty")
        if rule.entity not in ENTITY_MODELS:
            raise MatcherError("rule_invalid", f"unknown entity: {rule.entity}")
        if not rule.composite_keys:
            raise MatcherError("rule_invalid", f"rule {rule.name} has no composite_keys")
        if "year_month_equal" not in rule.conditions:
            raise MatcherError("rule_invalid", f"rule {rule.name} requires year_month_equal")
        if "branch_id" not in rule.match or "outgoing_number" not in rule.match:
            raise MatcherError(
                "rule_invalid",
                f"rule {rule.name} must match branch_id and outgoing_number",
            )
        rules.append(rule)
    return MatchRuleSet(rules=rules)


def validate_rule_for_scheme(rule: MatchRule, scheme: LayoutScheme) -> None:
    names = {item.name for item in scheme.fields}
    missing = [name for name in rule.composite_keys if name not in names]
    if missing:
        raise MatcherError(
            "rule_field_missing",
            f"rule {rule.name} references unknown fields: {', '.join(missing)}",
            fields=missing,
        )
    lookup = rule.raw.get("lookup") or {}
    table = lookup.get("table")
    if table and table != ENTITY_TABLES[rule.entity]:
        raise MatcherError(
            "rule_table_mismatch",
            f"rule {rule.name}: table {table} does not match entity {rule.entity}",
        )


def _lookup_field(rule: MatchRule, role: str, default: str) -> str:
    lookup = rule.raw.get("lookup") or {}
    value = lookup.get(role)
    return str(value) if value else default


def _row_branch_code(rule: MatchRule, row: ParsedRow) -> str:
    explicit = _lookup_field(rule, "branch_code", "")
    if explicit:
        return str(row.data.get(explicit) or "").strip()
    parts = [str(row.data.get(key) or "").strip() for key in rule.composite_keys]
    if any(not part for part in parts):
        return ""
    return "-".join(parts)


def _parse_year_month(value: str) -> Optional[Tuple[int, int]]:
    """Разбирает ГГГГММ и ММГГГГ, возвращая (год, месяц)."""
    if len(value) != 6 or not value.isdigit():
        return None
    year, month = int(value[:4]), int(value[4:])
    if 1 <= month <= 12:
        return year, month
    month, year = int(value[:2]), int(value[2:])
    if 1 <= month <= 12:
        return year, month
    return None


class Matcher:
    """Сопоставляет разобранные строки с существующими документами."""

    def __init__(self, session) -> None:
        self.session = session

    def match(
        self,
        rows: Iterable[ParsedRow],
        rule: MatchRule,
        scheme: LayoutScheme,
    ) -> List[MatchResult]:
        validate_rule_for_scheme(rule, scheme)
        model = ENTITY_MODELS[rule.entity]
        valid_rows = [row for row in rows if row.is_valid]
        branch_codes = {
            _row_branch_code(rule, row)
            for row in valid_rows
            if _row_branch_code(rule, row)
        }
        outgoing_field = _lookup_field(rule, "outgoing_no", "outgoing_no")
        numbers = {
            str(row.data.get(outgoing_field) or "").strip()
            for row in valid_rows
            if str(row.data.get(outgoing_field) or "").strip()
        }
        branches = sorted(branch_codes)
        numbers = sorted(numbers)
        candidates: Dict[Tuple[str, str], List[Tuple[str, date]]] = {}
        if branches and numbers:
            statement = select(
                model.id,
                model.branch_id,
                model.outgoing_number,
                model.outgoing_date,
            ).where(
                model.branch_id.in_(branches),
                model.outgoing_number.in_(numbers),
            )
            for entity_id, branch_id, number, document_date in self.session.execute(statement):
                if document_date is None:
                    continue
                key = (str(branch_id), str(number))
                candidates.setdefault(key, []).append((str(entity_id), document_date))

        results: List[MatchResult] = []
        year_month_field = _lookup_field(rule, "year_month", "year_month")
        value_field = _lookup_field(rule, "value", "value")
        date_field = _lookup_field(rule, "evaluation_date", "evaluation_date")
        for row in valid_rows:
            branch_code = _row_branch_code(rule, row)
            outgoing_no = str(row.data.get(outgoing_field) or "").strip()
            year_month = str(row.data.get(year_month_field) or "").strip()
            value_code = row.data.get(value_field)
            value_code = str(value_code).strip() if value_code is not None else None
            evaluation_date = row.data.get(date_field)
            if evaluation_date is not None and not isinstance(evaluation_date, date):
                evaluation_date = None
            base = MatchResult(
                row=row,
                matched=False,
                branch_code=branch_code,
                outgoing_no=outgoing_no,
                year_month=year_month,
                value_code=value_code or None,
                evaluation_date=evaluation_date,
            )
            if not branch_code or not outgoing_no:
                base.reason = "key_empty"
                results.append(base)
                continue
            parsed_year_month = _parse_year_month(year_month)
            if parsed_year_month is None:
                base.reason = "year_month_invalid"
                results.append(base)
                continue
            year, month = parsed_year_month
            found = [
                item
                for item in candidates.get((branch_code, outgoing_no), [])
                if item[1].year == year and item[1].month == month
            ]
            if not found:
                base.reason = "document_not_found"
                results.append(base)
                continue
            if len(found) > 1:
                base.reason = "document_ambiguous"
                results.append(base)
                continue
            base.matched = True
            base.entity_type = rule.entity
            base.entity_id = found[0][0]
            results.append(base)
        return results
