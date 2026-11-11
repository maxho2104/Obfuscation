"""Делегат отображения оценки с цветовым выделением."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.gui.table_model import EVALUATION_VALUE_ROLE


class EvaluationItemDelegate(QStyledItemDelegate):
    """Рисует оценку в отдельной ячейке с цветом, соответствующим значению."""

    COLORS = {
        EvaluationValue.USELESS: ("#b71c1c", "#ffcdd2"),
        EvaluationValue.INTERESTING: ("#8d6e00", "#fff9c4"),
        EvaluationValue.USEFUL: ("#1b5e20", "#c8e6c9"),
        EvaluationValue.IMPORTANT: ("#0d47a1", "#bbdefb"),
    }

    def __init__(self, evaluation_column: int, parent=None) -> None:
        super().__init__(parent)
        self.evaluation_column = evaluation_column

    def paint(self, painter: QPainter, option, index) -> None:
        if index.column() != self.evaluation_column:
            super().paint(painter, option, index)
            return

        value = index.data(EVALUATION_VALUE_ROLE)
        text = index.data(Qt.DisplayRole)
        colors = self.COLORS.get(value)
        if not text or colors is None:
            super().paint(painter, option, index)
            return

        text_color = QColor(colors[0])
        background_color = QColor(colors[1])

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(2, 2, -2, -2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(background_color)
        painter.drawRoundedRect(rect, 4, 4)

        if option.state & QStyle.State_Selected:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(option.palette.highlight().color())
            painter.drawRoundedRect(rect, 4, 4)

        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, str(text))
        painter.restore()
