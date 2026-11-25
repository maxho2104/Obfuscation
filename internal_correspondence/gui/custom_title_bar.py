"""Кастомные безрамочные шапки окон приложения."""

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable, Optional, Set, Tuple

if sys.platform == "win32":
    from ctypes import wintypes

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QCursor, QIcon, QPainter, QPalette, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QSizePolicy,
    QToolButton,
    QWidget,
    QWizard,
)


ICONS_DIR = Path(__file__).resolve().parent / "icons"
TITLE_BAR_CONTENT_GAP_PROPERTY = "customTitleBarContentGap"
WIZARD_CUSTOM_TITLE_BAR_PROPERTY = "customTitleBarWizardReady"


@dataclass(frozen=True)
class WindowControlLabels:
    """Локализуемые подсказки кнопок управления окном."""

    minimize: str
    maximize: str
    restore: str
    close: str


class WindowTitle(QLabel):
    """Заголовок и безопасная область перетаскивания окна."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("windowTitle")
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.setFixedHeight(44)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)


class WindowContextTitle(QLabel):
    """Контекст текущего подразделения по центру главной шапки."""

    HEIGHT = 44
    MINIMUM_WIDTH = 160
    MAXIMUM_WIDTH = 420

    def __init__(self, text: str, parent: QMenuBar) -> None:
        super().__init__(text, parent)
        self.setObjectName("windowContextTitle")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setToolTip(text)
        parent.installEventFilter(self)
        self._sync_geometry()

    def set_context(self, text: str) -> None:
        """Обновляет подпись подразделения и её положение."""
        self.setText(text)
        self.setToolTip(text)
        self._sync_geometry()

    def _sync_geometry(self) -> None:
        """Удерживает подпись по центру всей ширины шапки."""
        menu_bar = self.parentWidget()
        if menu_bar is None:
            return
        available_width = max(0, menu_bar.width())
        preferred_width = max(
            self.MINIMUM_WIDTH,
            self.sizeHint().width() + 24,
        )
        width = min(preferred_width, self.MAXIMUM_WIDTH, available_width)
        self.setGeometry(
            max(0, (available_width - width) // 2),
            0,
            width,
            self.HEIGHT,
        )
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() in (
            QEvent.Resize,
            QEvent.Show,
            QEvent.LayoutRequest,
            QEvent.StyleChange,
            QEvent.FontChange,
        ):
            self._sync_geometry()
        return False


class WindowControls(QWidget):
    """Кнопки сворачивания, разворачивания и закрытия главного окна."""

    def __init__(
        self,
        window: QWidget,
        labels: WindowControlLabels,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._window = window
        self._labels = labels
        self.setObjectName("windowControls")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.minimize_button = self._make_button(
            "windowMinimizeButton",
            labels.minimize,
            window.showMinimized,
        )
        self.maximize_button = self._make_button(
            "windowMaximizeButton",
            labels.maximize,
            lambda: _toggle_maximize(window),
        )
        self.close_button = self._make_button(
            "windowCloseButton",
            labels.close,
            window.close,
        )

        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)
        self.refresh_icons()

    @property
    def buttons(self) -> Tuple[QToolButton, QToolButton, QToolButton]:
        """Возвращает кнопки в порядке их отображения."""
        return (
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        )

    def _make_button(
        self,
        object_name: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedSize(46, 44)
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _icon(icon_name: str, tint: Optional[QColor] = None) -> QIcon:
        pixmap = QPixmap(str(ICONS_DIR / icon_name))
        if tint is not None and not pixmap.isNull():
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), tint)
            painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _set_icon(
        button: QToolButton,
        icon: QIcon,
        fallback_text: str,
    ) -> None:
        if icon.isNull():
            button.setIcon(QIcon())
            button.setText(fallback_text)
            return
        button.setText("")
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))

    def refresh_icons(self) -> None:
        """Обновляет иконки, учитывая текущую палитру темы."""
        text_color = self.palette().color(QPalette.ButtonText)
        self._set_icon(
            self.minimize_button,
            self._icon("window-minimize.png"),
            "—",
        )
        self._set_icon(
            self.maximize_button,
            self._icon("window-maximize.png", text_color),
            "□",
        )
        self._set_icon(
            self.close_button,
            self._icon("window-close.png"),
            "×",
        )

    def update_maximize_state(self, maximized: bool) -> None:
        """Меняет подсказку кнопки в зависимости от состояния окна."""
        tooltip = self._labels.restore if maximized else self._labels.maximize
        self.maximize_button.setToolTip(tooltip)
        self.maximize_button.setAccessibleName(tooltip)


class WindowDragHandler(QObject):
    """Перетаскивает окно только за выделенную область заголовка."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._drag_position: Optional[QPoint] = None
        self._drag_widget: Optional[QWidget] = None
        self._system_move_attempted = False
        self._targets: Set[QWidget] = set()

    def watch(self, *widgets: QWidget) -> None:
        """Подключает обработчик к безопасным областям шапки."""
        for widget in widgets:
            self._targets.add(widget)
            widget.installEventFilter(self)

    def _is_free_area(self, widget: QWidget, position: QPoint) -> bool:
        """Не перехватывает пункты меню и кнопки управления окном."""
        if isinstance(widget, QMenuBar) and widget.actionAt(position) is not None:
            return False
        child = widget.childAt(position)
        return child is None or child in self._targets

    def _finish_drag(self) -> None:
        widget = self._drag_widget
        self._drag_widget = None
        if widget is not None:
            try:
                if QWidget.mouseGrabber() is widget:
                    widget.releaseMouse()
            except RuntimeError:
                pass
        self._drag_position = None
        self._system_move_attempted = False

    def _start_drag(self, widget: QWidget, global_position: QPoint) -> bool:
        """Запоминает начало перетаскивания и захватывает мышь."""
        self._drag_position = (
            global_position - self._window.frameGeometry().topLeft()
        )
        self._drag_widget = widget
        self._system_move_attempted = False
        widget.grabMouse()
        return True

    def _try_system_move(self) -> bool:
        """Передаёт начавшееся перемещение оконной системе, если возможно."""
        if self._system_move_attempted or self._window.isMaximized():
            return False
        self._system_move_attempted = True
        handle = self._window.windowHandle()
        if handle is None or not hasattr(handle, "startSystemMove"):
            return False

        widget = self._drag_widget
        if widget is not None and QWidget.mouseGrabber() is widget:
            widget.releaseMouse()
        try:
            if handle.startSystemMove():
                self._drag_widget = None
                self._drag_position = None
                return True
        except RuntimeError:
            pass
        if widget is not None:
            widget.grabMouse()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched not in self._targets:
            return super().eventFilter(watched, event)

        if (
            event.type()
            in (
                QEvent.MouseButtonDblClick,
                QEvent.MouseButtonPress,
            )
            and not self._is_free_area(watched, event.pos())
        ):
            return False

        if (
            event.type() == QEvent.MouseButtonDblClick
            and event.button() == Qt.LeftButton
        ):
            self._finish_drag()
            _toggle_maximize(self._window)
            return True

        if (
            event.type() == QEvent.MouseButtonPress
            and event.button() == Qt.LeftButton
        ):
            return self._start_drag(watched, event.globalPos())

        if (
            event.type() == QEvent.MouseMove
            and self._drag_position is not None
            and event.buttons() & Qt.LeftButton
        ):
            if self._try_system_move():
                return True
            if self._window.isMaximized():
                title_width = max(1, watched.width())
                horizontal_ratio = event.pos().x() / title_width
                normal_width = max(1, self._window.normalGeometry().width())
                self._window.showNormal()
                self._drag_position = QPoint(
                    int(normal_width * min(1.0, max(0.0, horizontal_ratio))),
                    22,
                )
            self._window.move(event.globalPos() - self._drag_position)
            return True

        if event.type() == QEvent.MouseButtonRelease:
            self._finish_drag()
            return True

        return super().eventFilter(watched, event)


class _QtResizeHandler(QObject):
    """Показывает курсор границы и изменяет размер безрамочного окна."""

    def __init__(self, window: QWidget, border: int) -> None:
        super().__init__(window)
        self._window = window
        self._border = border
        self._cursor_widget: Optional[QWidget] = None
        self._cursor_was_set = False
        self._previous_cursor = QCursor()
        self._manual_edges = Qt.Edges()
        self._drag_start_position: Optional[QPoint] = None
        self._drag_start_geometry: Optional[QRect] = None
        self._manual_mouse_widget: Optional[QWidget] = None
        self._watch_widget(window)

    def _watch_widget(self, widget: QWidget) -> None:
        """Следит за наведением на окно и его дочерние виджеты."""
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.setMouseTracking(True)
            child.installEventFilter(self)

    def _resize_edges(self, global_position: QPoint) -> Qt.Edges:
        rect = self._window.frameGeometry()
        edges = Qt.Edges()
        if rect.left() <= global_position.x() <= rect.left() + self._border:
            edges |= Qt.LeftEdge
        if rect.right() - self._border <= global_position.x() <= rect.right():
            edges |= Qt.RightEdge
        if rect.top() <= global_position.y() <= rect.top() + self._border:
            edges |= Qt.TopEdge
        if rect.bottom() - self._border <= global_position.y() <= rect.bottom():
            edges |= Qt.BottomEdge
        return edges

    @staticmethod
    def _event_global_position(widget: QWidget, event: QEvent) -> QPoint:
        """Получает позицию мыши без ошибок координат безрамочного окна."""
        if hasattr(event, "pos"):
            return widget.mapToGlobal(event.pos())
        return QCursor.pos()

    @staticmethod
    def _cursor_shape(edges: Qt.Edges) -> Optional[Qt.CursorShape]:
        """Возвращает стандартную форму курсора для выбранных границ."""
        if edges in (
            Qt.LeftEdge | Qt.TopEdge,
            Qt.RightEdge | Qt.BottomEdge,
        ):
            return Qt.SizeFDiagCursor
        if edges in (
            Qt.RightEdge | Qt.TopEdge,
            Qt.LeftEdge | Qt.BottomEdge,
        ):
            return Qt.SizeBDiagCursor
        if edges & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if edges & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return None

    def _restore_cursor(self) -> None:
        widget = self._cursor_widget
        self._cursor_widget = None
        if widget is None:
            return
        try:
            if self._cursor_was_set:
                widget.setCursor(self._previous_cursor)
            else:
                widget.unsetCursor()
        except RuntimeError:
            # Виджет мог быть удалён вместе с закрытым диалогом.
            pass

    def _update_cursor(self, widget: QWidget, edges: Qt.Edges) -> None:
        shape = self._cursor_shape(edges)
        if shape is None:
            self._restore_cursor()
            return
        if (
            self._cursor_widget is widget
            and widget.cursor().shape() == shape
        ):
            return

        self._restore_cursor()
        self._cursor_widget = widget
        self._cursor_was_set = widget.testAttribute(Qt.WA_SetCursor)
        self._previous_cursor = widget.cursor()
        widget.setCursor(shape)

    @staticmethod
    def _bounded(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(value, maximum))

    def _resize_manually(self, global_position: QPoint) -> None:
        """Меняет геометрию, если оконная система не поддержала resize Qt."""
        start_position = self._drag_start_position
        start_geometry = self._drag_start_geometry
        if start_position is None or start_geometry is None:
            return

        delta = global_position - start_position
        left = start_geometry.x()
        top = start_geometry.y()
        width = start_geometry.width()
        height = start_geometry.height()
        right = left + width
        bottom = top + height

        if self._manual_edges & Qt.LeftEdge:
            width = self._bounded(
                width - delta.x(),
                self._window.minimumWidth(),
                self._window.maximumWidth(),
            )
            left = right - width
        elif self._manual_edges & Qt.RightEdge:
            width = self._bounded(
                width + delta.x(),
                self._window.minimumWidth(),
                self._window.maximumWidth(),
            )

        if self._manual_edges & Qt.TopEdge:
            height = self._bounded(
                height - delta.y(),
                self._window.minimumHeight(),
                self._window.maximumHeight(),
            )
            top = bottom - height
        elif self._manual_edges & Qt.BottomEdge:
            height = self._bounded(
                height + delta.y(),
                self._window.minimumHeight(),
                self._window.maximumHeight(),
            )

        self._window.setGeometry(left, top, width, height)

    def _start_resize(
        self,
        widget: QWidget,
        edges: Qt.Edges,
        position: QPoint,
    ) -> bool:
        handle = self._window.windowHandle()
        if handle is not None and hasattr(handle, "startSystemResize"):
            try:
                if handle.startSystemResize(edges):
                    return True
            except RuntimeError:
                # Оконный дескриптор мог быть пересоздан сменой флагов окна.
                pass

        self._manual_edges = edges
        self._drag_start_position = position
        self._drag_start_geometry = self._window.geometry()
        self._manual_mouse_widget = widget
        widget.grabMouse()
        return True

    def _finish_resize(self) -> None:
        widget = self._manual_mouse_widget
        self._manual_mouse_widget = None
        if widget is not None:
            try:
                if QWidget.mouseGrabber() is widget:
                    widget.releaseMouse()
            except RuntimeError:
                pass
        self._manual_edges = Qt.Edges()
        self._drag_start_position = None
        self._drag_start_geometry = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not isinstance(watched, QWidget):
            return False

        if event.type() == QEvent.ChildAdded:
            child = event.child()
            if (
                isinstance(child, QWidget)
                and watched.window() is self._window
            ):
                self._watch_widget(child)
            return False

        if watched.window() is not self._window:
            return False

        if event.type() in (QEvent.Hide, QEvent.Close):
            self._restore_cursor()
            self._finish_resize()
            return False

        if self._window.isMaximized():
            self._restore_cursor()
            self._finish_resize()
            return False

        if event.type() in (QEvent.Enter, QEvent.MouseMove):
            position = self._event_global_position(watched, event)
            if (
                self._manual_edges
                and event.type() == QEvent.MouseMove
                and event.buttons() & Qt.LeftButton
            ):
                self._resize_manually(position)
                return True
            self._update_cursor(watched, self._resize_edges(position))
            return False

        if event.type() == QEvent.Leave:
            if not self._window.frameGeometry().contains(QCursor.pos()):
                self._restore_cursor()
            return False

        if (
            event.type() == QEvent.MouseButtonPress
            and event.button() == Qt.LeftButton
        ):
            position = self._event_global_position(watched, event)
            edges = self._resize_edges(position)
            if edges:
                return self._start_resize(watched, edges, position)

        if event.type() == QEvent.MouseButtonRelease:
            self._finish_resize()
        return False


def _toggle_maximize(window: QWidget) -> None:
    """Переключает развёрнутое и обычное состояния произвольного окна."""
    if window.isMaximized():
        window.showNormal()
    else:
        window.showMaximized()


class DialogTitleBar(QWidget):
    """Шапка вторичного окна с заголовком и кнопками управления."""

    HEIGHT = 44

    def __init__(
        self,
        window: QDialog,
        labels: WindowControlLabels,
    ) -> None:
        super().__init__(window)
        self.setObjectName("dialogTitleBar")
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(0)

        self.title_label = QLabel(window.windowTitle(), self)
        self.title_label.setObjectName("dialogWindowTitle")
        self.title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title_label.setFixedHeight(self.HEIGHT)

        self.window_controls = WindowControls(window, labels, self)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.window_controls)


class DialogTitleBarController(QObject):
    """Встраивает шапку поверх содержимого одного ``QDialog``."""

    RESIZE_BORDER = 8

    def __init__(
        self,
        dialog: QDialog,
        labels: WindowControlLabels,
    ) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._space_reserved = False
        self._height_adjusted = False

        dialog.setWindowFlags(dialog.windowFlags() | Qt.FramelessWindowHint)
        self.title_bar = DialogTitleBar(dialog, labels)
        self.window_controls = self.title_bar.window_controls

        self._drag_handler = WindowDragHandler(dialog)
        self._drag_handler.watch(self.title_bar, self.title_bar.title_label)

        self._resize_handler = _QtResizeHandler(dialog, self.RESIZE_BORDER)

        dialog.installEventFilter(self)
        self._reserve_title_bar_space()
        self._sync_title_bar()

    def _reserve_title_bar_space(self) -> None:
        if self._space_reserved:
            return

        reserved_height = DialogTitleBar.HEIGHT + self._content_gap()
        left, top, right, bottom = self._dialog.getContentsMargins()
        self._dialog.setContentsMargins(
            left,
            top + reserved_height,
            right,
            bottom,
        )
        self._space_reserved = True

        if not self._height_adjusted:
            current_height = self._dialog.height()
            maximum_height = self._dialog.maximumHeight()
            if maximum_height < 16_777_215:
                self._dialog.setMaximumHeight(
                    maximum_height + reserved_height
                )
            minimum_height = self._dialog.minimumHeight()
            if minimum_height > 0:
                self._dialog.setMinimumHeight(
                    minimum_height + reserved_height
                )
            self._dialog.resize(
                self._dialog.width(),
                current_height + reserved_height,
            )
            self._height_adjusted = True

    def _content_gap(self) -> int:
        """Возвращает дополнительный отступ содержимого под шапкой окна."""
        value = self._dialog.property(TITLE_BAR_CONTENT_GAP_PROPERTY)
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _sync_title_bar(self) -> None:
        self.title_bar.setGeometry(
            0,
            0,
            self._dialog.width(),
            DialogTitleBar.HEIGHT,
        )
        self.title_bar.title_label.setText(self._dialog.windowTitle())
        self.window_controls.update_maximize_state(
            self._dialog.isMaximized()
        )
        self.title_bar.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._dialog:
            return False

        if event.type() in (QEvent.Show, QEvent.LayoutRequest):
            self._reserve_title_bar_space()
        if event.type() in (
            QEvent.Show,
            QEvent.Resize,
            QEvent.WindowTitleChange,
            QEvent.WindowStateChange,
        ):
            self._sync_title_bar()
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self.window_controls.refresh_icons()
        return False


class DialogTitleBarInstaller(QObject):
    """Автоматически подключает кастомную шапку ко всем диалогам."""

    def __init__(
        self,
        app: QApplication,
        labels_provider: Callable[[], WindowControlLabels],
    ) -> None:
        super().__init__(app)
        self._labels_provider = labels_provider

    def set_labels_provider(
        self,
        labels_provider: Callable[[], WindowControlLabels],
    ) -> None:
        """Обновляет источник локализуемых подписей."""
        self._labels_provider = labels_provider

    @staticmethod
    def _should_install(
        dialog: QDialog,
        platform_name: Optional[str] = None,
    ) -> bool:
        """Проверяет поддержку диалога текущим платформенным плагином."""
        app = QApplication.instance()
        if app is None and platform_name is None:
            return False
        # Прогресс должен сохранять обычную системную рамку, а файловый диалог
        # открывается нативным средством ОС и не оформляется приложением.
        if isinstance(dialog, (QProgressDialog, QFileDialog)):
            return False
        # QWizard игнорирует contents margins, поэтому кастомная шапка
        # разрешена только мастерам, которые сами подготовили отступ внутри
        # заголовков страниц (см. FirstRunWizard).
        if (
            isinstance(dialog, QWizard)
            and not dialog.property(WIZARD_CUSTOM_TITLE_BAR_PROPERTY)
        ):
            return False
        # Плагин offscreen аварийно завершается при безрамочном QMessageBox.
        # В обычном Windows/X11-сеансе ограничение отсутствует.
        unsupported_offscreen = (QMessageBox,)
        return not (
            (platform_name or app.platformName()) == "offscreen"
            and isinstance(dialog, unsupported_offscreen)
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            event.type() in (QEvent.Polish, QEvent.Show)
            and isinstance(watched, QDialog)
            and getattr(watched, "_custom_title_bar_controller", None) is None
            and not watched.property("skipCustomTitleBar")
            and self._should_install(watched)
        ):
            controller = DialogTitleBarController(
                watched,
                self._labels_provider(),
            )
            watched._custom_title_bar_controller = controller
        return False


def install_dialog_title_bars(
    app: QApplication,
    labels_provider: Callable[[], WindowControlLabels],
) -> DialogTitleBarInstaller:
    """Включает автоматические кастомные шапки для всех ``QDialog``."""
    installer = getattr(app, "_dialog_title_bar_installer", None)
    if installer is None:
        installer = DialogTitleBarInstaller(app, labels_provider)
        app.installEventFilter(installer)
        app._dialog_title_bar_installer = installer
    else:
        installer.set_labels_provider(labels_provider)
    return installer


class FramelessWindowMixin:
    """Добавляет ``QMainWindow`` кастомную шапку и изменение размера."""

    RESIZE_BORDER = 8

    WM_NCHITTEST = 0x0084
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17

    def setup_custom_title_bar(
        self,
        menu_bar: QMenuBar,
        title: str,
        labels: WindowControlLabels,
        context_title: str = "",
    ) -> None:
        """Настраивает безрамочное окно и виджеты его шапки."""
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        menu_bar.setObjectName("mainMenuBar")
        menu_bar.setNativeMenuBar(False)
        menu_bar.setFixedHeight(46)

        self.window_title = WindowTitle(title, menu_bar)
        menu_bar.setCornerWidget(self.window_title, Qt.TopLeftCorner)

        self.window_context_title = WindowContextTitle(
            context_title,
            menu_bar,
        )

        self.window_controls = WindowControls(self, labels, menu_bar)
        menu_bar.setCornerWidget(self.window_controls, Qt.TopRightCorner)
        self.window_context_title._sync_geometry()

        self._window_drag_handler = WindowDragHandler(self)
        # Свободная часть menuBar перемещает окно, а пункты меню не
        # перехватываются благодаря проверке actionAt в обработчике.
        self._window_drag_handler.watch(self.window_title, menu_bar)

        self._qt_resize_handler = None
        app = QApplication.instance()
        if app is not None:
            self._qt_resize_handler = _QtResizeHandler(
                self,
                self.RESIZE_BORDER,
            )

    def _resize_hit_test(self, global_position: QPoint) -> Optional[int]:
        rect = self.frameGeometry()
        border = self.RESIZE_BORDER

        on_left = rect.left() <= global_position.x() <= rect.left() + border
        on_right = rect.right() - border <= global_position.x() <= rect.right()
        on_top = rect.top() <= global_position.y() <= rect.top() + border
        on_bottom = rect.bottom() - border <= global_position.y() <= rect.bottom()

        if on_top and on_left:
            return self.HTTOPLEFT
        if on_top and on_right:
            return self.HTTOPRIGHT
        if on_bottom and on_left:
            return self.HTBOTTOMLEFT
        if on_bottom and on_right:
            return self.HTBOTTOMRIGHT
        if on_left:
            return self.HTLEFT
        if on_right:
            return self.HTRIGHT
        if on_top:
            return self.HTTOP
        if on_bottom:
            return self.HTBOTTOM
        return None

    def nativeEvent(  # noqa: N802
        self,
        event_type: Any,
        message: Any,
    ) -> Tuple[bool, int]:
        """Возвращает Windows коды границ для нативного изменения размера."""
        if (
            sys.platform == "win32"
            and not self.isMaximized()
            and getattr(self, "_qt_resize_handler", None) is None
        ):
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == self.WM_NCHITTEST:
                hit_result = self._resize_hit_test(QCursor.pos())
                if hit_result is not None:
                    return True, hit_result
        return super().nativeEvent(event_type, message)

    def toggle_maximize(self) -> None:
        """Переключает развёрнутое и обычное состояния окна."""
        _toggle_maximize(self)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Синхронизирует подсказку кнопки с состоянием окна."""
        if event.type() == QEvent.WindowStateChange:
            controls = getattr(self, "window_controls", None)
            if controls is not None:
                controls.update_maximize_state(self.isMaximized())
        super().changeEvent(event)
