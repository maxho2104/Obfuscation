"""Обновляет секцию strings пакета предметной области по умолчанию."""

import json
from dataclasses import fields
from pathlib import Path

from internal_correspondence.utils.string_resources import AppStrings

PACK_PATH = Path("internal_correspondence/core/domain_pack.default.json")


def main() -> None:
    data = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    strings = AppStrings()
    data["strings"] = {fld.name: getattr(strings, fld.name) for fld in fields(strings)}
    PACK_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Обновлено ключей strings: {len(data['strings'])}")


if __name__ == "__main__":
    main()
