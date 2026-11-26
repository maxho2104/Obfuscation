"""Тесты общего поведения выпадающих списков."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QComboBox

from internal_correspondence.gui.combo_box_behavior import (
    install_combo_box_popup_behavior,
)
from internal_correspondence.gui.theme import apply_theme


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    """Возвращает приложение с общим обработчиком выпадающих списков."""
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_theme(app, "light")
    install_combo_box_popup_behavior(app)
    return app


def test_popup_shows_all_items_that_fit_screen(qt_app: QApplication) -> None:
    """Список из двенадцати строк раскрывается полностью, без прокрутки."""
    combo_box = QComboBox()
    combo_box.addItems([f"Item {index}" for index in range(12)])
    combo_box.resize(140, combo_box.sizeHint().height())
    combo_box.show()
    qt_app.processEvents()

    combo_box.showPopup()
    qt_app.processEvents()

    view = combo_box.view()
    last_index = combo_box.model().index(combo_box.count() - 1, 0)
    assert combo_box.maxVisibleItems() == combo_box.count()
    assert not view.verticalScrollBar().isVisible()
    assert view.visualRect(last_index).bottom() <= view.viewport().rect().bottom()

    combo_box.hidePopup()
    combo_box.close()


def test_popup_width_fits_longest_item(qt_app: QApplication) -> None:
    """Раскрытая часть расширяется под длинную подпись и не ставит многоточие."""
    combo_box = QComboBox()
    longest_text = "A long combo-box item that must remain completely visible"
    combo_box.addItems(["Short", longest_text])
    combo_box.resize(100, combo_box.sizeHint().height())
    combo_box.show()
    qt_app.processEvents()

    view = combo_box.view()
    assert view.textElideMode() == Qt.ElideNone
    assert view.minimumWidth() >= view.sizeHintForColumn(0)

    combo_box.close()


def test_installer_is_idempotent(qt_app: QApplication) -> None:
    """Повторное подключение не создаёт ещё один обработчик."""
    first = install_combo_box_popup_behavior(qt_app)
    second = install_combo_box_popup_behavior(qt_app)
    assert first is second
