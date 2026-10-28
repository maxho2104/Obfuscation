#!/usr/bin/env python3
"""Точка входа в приложение "Внутренняя корреспонденция"."""

import sys

from internal_correspondence.gui.application import run_application


def main() -> int:
    """Запускает главный цикл приложения."""
    return run_application(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
