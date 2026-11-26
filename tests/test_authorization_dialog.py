"""Тесты окна-заглушки авторизации и его места в запуске приложения."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit

from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui import application as application_module
from internal_correspondence.gui.authorization_dialog import AuthorizationDialog
from internal_correspondence.gui.custom_title_bar import (
    WindowControlLabels,
    install_dialog_title_bars,
)
from internal_correspondence.gui.theme import apply_theme


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    """Создаёт приложение с темой и общей кастомной шапкой диалогов."""
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_theme(app, "light")
    install_dialog_title_bars(
        app,
        lambda: WindowControlLabels("Minimize", "Maximize", "Restore", "Close"),
    )
    return app


def test_any_non_empty_credentials_are_accepted(qt_app: QApplication) -> None:
    """Заглушка принимает произвольные непустые имя и пароль."""
    dialog = AuthorizationDialog()
    dialog.show()
    qt_app.processEvents()

    assert dialog.height() >= 430
    assert dialog.password_edit.echoMode() == QLineEdit.Password
    assert not dialog.ok_button.isEnabled()
    dialog.username_edit.setText("any user")
    dialog.password_edit.setText("any password")
    assert dialog.password_edit.displayText() != "any password"
    assert dialog.ok_button.isEnabled()

    QTest.mouseClick(dialog.ok_button, Qt.LeftButton)
    assert dialog.result() == QDialog.Accepted


def test_password_visibility_action_toggles_mask(
    qt_app: QApplication,
) -> None:
    """Глаз внутри поля временно показывает пароль и снова скрывает его."""
    dialog = AuthorizationDialog()
    dialog.password_edit.setText("secret")

    action = dialog.password_visibility_action
    assert not action.icon().isNull()
    assert not action.isChecked()
    assert dialog.password_edit.echoMode() == QLineEdit.Password

    action.trigger()
    assert action.isChecked()
    assert dialog.password_edit.echoMode() == QLineEdit.Normal
    assert dialog.password_edit.displayText() == "secret"

    action.trigger()
    assert not action.isChecked()
    assert dialog.password_edit.echoMode() == QLineEdit.Password
    assert dialog.password_edit.displayText() != "secret"


def test_cancel_and_title_bar_close_reject_dialog(
    qt_app: QApplication,
) -> None:
    """Кнопка отмены и крестик кастомной шапки отменяют вход."""
    cancel_dialog = AuthorizationDialog()
    cancel_dialog.show()
    qt_app.processEvents()
    cancel_button = cancel_dialog.button_box.button(QDialogButtonBox.Cancel)
    QTest.mouseClick(cancel_button, Qt.LeftButton)
    assert cancel_dialog.result() == QDialog.Rejected

    close_dialog = AuthorizationDialog()
    close_dialog.show()
    qt_app.processEvents()
    controller = close_dialog._custom_title_bar_controller
    controller.window_controls.close_button.click()
    qt_app.processEvents()
    assert close_dialog.result() == QDialog.Rejected


@pytest.mark.parametrize("accepted", [True, False])
def test_authorization_controls_first_run_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    accepted: bool,
) -> None:
    """Успешный вход сохраняет настройки, отмена возвращает первый запуск."""
    manager = SettingsManager(tmp_path)
    manager.save(AppSettings())
    monkeypatch.setattr(
        application_module,
        "run_authorization_dialog",
        lambda: accepted,
    )

    assert application_module._authorize_or_reset_settings(tmp_path) is accepted
    assert manager.exists is accepted
