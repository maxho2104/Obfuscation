"""Единое поведение выпадающих списков приложения."""

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import QApplication, QComboBox, QStyle


_POPUP_SCREEN_MARGIN = 16
_POPUP_CONTENT_PADDING = 16


class ComboBoxPopupInstaller(QObject):
    """Настраивает раскрывающуюся часть каждого ``QComboBox``."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Обновляет размеры списка после наполнения и перед раскрытием."""
        if isinstance(watched, QComboBox) and event.type() in (
            QEvent.Polish,
            QEvent.Show,
            QEvent.MouseButtonPress,
            QEvent.KeyPress,
        ):
            self.prepare(watched)
        return False

    @staticmethod
    def prepare(combo_box: QComboBox) -> None:
        """Показывает все доступные строки и не обрезает их подписи по ширине."""
        item_count = combo_box.count()
        combo_box.setMaxVisibleItems(max(1, item_count))

        view = combo_box.view()
        view.ensurePolished()
        view.setTextElideMode(Qt.ElideNone)
        content_width = max(0, view.sizeHintForColumn(0))
        scrollbar_width = combo_box.style().pixelMetric(
            QStyle.PM_ScrollBarExtent,
            None,
            view,
        )
        popup_width = max(
            combo_box.width(),
            content_width
            + scrollbar_width
            + 2 * view.frameWidth()
            + _POPUP_CONTENT_PADDING,
        )

        screen = QApplication.screenAt(
            combo_box.mapToGlobal(combo_box.rect().center())
        )
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            available_geometry = screen.availableGeometry()
            popup_width = min(
                popup_width,
                max(1, available_geometry.width() - _POPUP_SCREEN_MARGIN),
            )
        view.setMinimumWidth(popup_width)

        content_height = sum(
            max(0, view.sizeHintForRow(row)) for row in range(item_count)
        )
        viewport_chrome = max(
            2 * view.frameWidth(),
            view.height() - view.viewport().height(),
        )
        popup_height = content_height + viewport_chrome
        if screen is not None:
            popup_height = min(
                popup_height,
                max(1, available_geometry.height() - 2 * _POPUP_SCREEN_MARGIN),
            )
        view.setMinimumHeight(max(1, popup_height))


def install_combo_box_popup_behavior(
    app: QApplication,
) -> ComboBoxPopupInstaller:
    """Подключает общую настройку списков к приложению один раз."""
    installer = getattr(app, "_combo_box_popup_installer", None)
    if installer is None:
        installer = ComboBoxPopupInstaller(app)
        app.installEventFilter(installer)
        app._combo_box_popup_installer = installer
    return installer
