"""Диалог-заглушка авторизации перед открытием главного окна."""

from typing import Optional

from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.utils.string_resources import STRINGS


def _password_visibility_icon(color: QColor, crossed_out: bool) -> QIcon:
    """Рисует тематическую иконку показа или скрытия пароля."""
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color)
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)

    eye = QPainterPath()
    eye.moveTo(2.0, 10.0)
    eye.cubicTo(4.5, 6.0, 7.0, 4.5, 10.0, 4.5)
    eye.cubicTo(13.0, 4.5, 15.5, 6.0, 18.0, 10.0)
    eye.cubicTo(15.5, 14.0, 13.0, 15.5, 10.0, 15.5)
    eye.cubicTo(7.0, 15.5, 4.5, 14.0, 2.0, 10.0)
    painter.drawPath(eye)
    painter.drawEllipse(QPointF(10.0, 10.0), 2.5, 2.5)
    if crossed_out:
        painter.drawLine(QPointF(3.0, 3.0), QPointF(17.0, 17.0))
    painter.end()
    return QIcon(pixmap)


class AuthorizationDialog(QDialog):
    """Принимает любые непустые имя пользователя и пароль."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_authorization_title)
        self.setModal(True)
        self.setMinimumWidth(380)
        self.resize(380, 390)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.username_edit = QLineEdit()
        self.username_edit.setObjectName("authorizationUsernameEdit")
        form.addRow(STRINGS.label_user, self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("authorizationPasswordEdit")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_visibility_action: QAction = self.password_edit.addAction(
            QIcon(),
            QLineEdit.TrailingPosition,
        )
        self.password_visibility_action.setCheckable(True)
        self.password_visibility_action.toggled.connect(
            self._set_password_visible
        )
        self._refresh_password_visibility_action()
        form.addRow(STRINGS.label_password, self.password_edit)
        layout.addLayout(form)
        layout.addStretch(1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.ok_button: QPushButton = self.button_box.button(
            QDialogButtonBox.Ok
        )
        self.ok_button.setText(STRINGS.button_ok)
        self.ok_button.setEnabled(False)
        self.button_box.button(QDialogButtonBox.Cancel).setText(
            STRINGS.button_cancel
        )
        layout.addWidget(self.button_box)

        self.username_edit.textChanged.connect(self._update_ok_button)
        self.password_edit.textChanged.connect(self._update_ok_button)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.username_edit.setFocus()

    def _set_password_visible(self, visible: bool) -> None:
        """Переключает отображение введённого пароля."""
        self.password_edit.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )
        self._refresh_password_visibility_action()

    def _refresh_password_visibility_action(self) -> None:
        """Обновляет иконку и подсказку с учётом темы и режима поля."""
        visible = self.password_visibility_action.isChecked()
        color = self.password_edit.palette().color(QPalette.Text)
        self.password_visibility_action.setIcon(
            _password_visibility_icon(color, crossed_out=visible)
        )
        self.password_visibility_action.setToolTip(
            STRINGS.hide_password if visible else STRINGS.show_password
        )

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Перерисовывает глаз при смене палитры приложения."""
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            if hasattr(self, "password_visibility_action"):
                self._refresh_password_visibility_action()

    def _update_ok_button(self) -> None:
        """Разрешает вход после заполнения обоих полей любыми значениями."""
        self.ok_button.setEnabled(
            bool(self.username_edit.text().strip())
            and bool(self.password_edit.text())
        )


def run_authorization_dialog(parent: Optional[QWidget] = None) -> bool:
    """Показывает заглушку и возвращает ``True`` после нажатия «ОК»."""
    dialog = AuthorizationDialog(parent)
    return dialog.exec_() == QDialog.Accepted
