"""Gráficas del Dashboard: evolución de caja y distribución de gastos."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from services.cashflow import money


# Texto que sustituye a los importes mientras están ocultos.
HIDDEN_MONEY = "••••• €"


def compact_money(value):
    """Importe abreviado para ejes y totales: 1,2 M€ · 47,5 k€ · 950 €."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        text = f"{value / 1_000_000:.1f} M€"
    elif value >= 100_000:
        text = f"{value / 1_000:.0f} k€"
    elif value >= 1_000:
        text = f"{value / 1_000:.1f} k€"
    else:
        text = f"{value:.0f} €"
    return sign + text.replace(".0 ", " ").replace(".", ",")


def whole_money(value):
    """Importe sin céntimos: 112.978 €."""
    return f"{round(value):,} €".replace(",", ".")


def nice_step(span, target_lines=4):
    """Paso «redondo» (1, 2, 2,5, 5 × 10ⁿ) para las líneas del eje."""
    raw = span / target_lines
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if factor * magnitude >= raw:
            return factor * magnitude
    return 10 * magnitude


class CashFlowChart(QWidget):
    """Gráfica responsive de evolución acumulada prevista de caja."""

    LINE = "#E31822"
    NEGATIVE = "#FF4D57"
    GRID = "#26262A"
    ZERO = "#8F171D"
    AXIS_TEXT = "#8A8A93"
    BACKGROUND = "#101012"

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.months = []
        self._points = []
        self._step_x = 0.0
        self._hover = None
        self.hidden = False

    def set_hidden(self, hidden):
        self.hidden = hidden
        self.update()

    def set_data(self, months):
        self.months = months
        self._hover = None
        self.update()

    # ----------------------------------------------------------
    # Ratón: importe exacto del mes bajo el cursor
    # ----------------------------------------------------------

    def mouseMoveEvent(self, event):
        if not self._points:
            return
        x = event.position().x()
        index = min(range(len(self._points)), key=lambda i: abs(self._points[i][0] - x))
        if abs(self._points[index][0] - x) > max(self._step_x / 2, 12):
            self.leaveEvent(event)
            return
        if index != self._hover:
            self._hover = index
            self.update()
        _, _, value, label = self._points[index]
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"{label}\nSaldo previsto: {HIDDEN_MONEY if self.hidden else money(value)}",
            self,
        )

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover = None
            self.update()
        QToolTip.hideText()

    # ----------------------------------------------------------
    # Dibujo
    # ----------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        if not self.months:
            self._points = []
            painter.setPen(QColor("#71717A"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, "Sin movimientos previstos")
            return

        values = [item["balance"] for item in self.months]
        data_min = min(values + [0.0])
        data_max = max(values + [0.0])
        span = data_max - data_min
        if span <= 0:
            span = max(abs(data_max), 1.0)

        # Eje vertical con valores redondos que siempre incluye el 0.
        step = nice_step(span)
        y_min = math.floor(data_min / step) * step
        y_max = math.ceil(data_max / step) * step
        if y_max <= y_min:
            y_max = y_min + step
        ticks = []
        tick = y_min
        while tick <= y_max + step / 1000:
            ticks.append(tick)
            tick += step

        axis_font = QFont("Segoe UI", 8)
        axis_metrics = QFontMetrics(axis_font)
        axis_text = (lambda t: "•••") if self.hidden else compact_money
        left = max(axis_metrics.horizontalAdvance(axis_text(t)) for t in ticks) + 14
        right = 18
        top = 28
        bottom = 30
        chart_w = max(1, w - left - right)
        chart_h = max(1, h - top - bottom)

        def y_for(value):
            return top + (y_max - value) / (y_max - y_min) * chart_h

        painter.setFont(axis_font)
        for tick in ticks:
            y = y_for(tick)
            is_zero = abs(tick) < step / 1000
            painter.setPen(QPen(QColor(self.ZERO if is_zero else self.GRID), 1))
            painter.drawLine(QPointF(left, y), QPointF(w - right, y))
            painter.setPen(QColor(self.AXIS_TEXT))
            painter.drawText(
                QRectF(0, y - 9, left - 8, 18),
                Qt.AlignRight | Qt.AlignVCenter,
                axis_text(tick),
            )

        # Puntos
        count = len(self.months)
        self._step_x = chart_w / max(1, count - 1)
        points = []
        for index, item in enumerate(self.months):
            x = left + chart_w / 2 if count == 1 else left + self._step_x * index
            points.append((x, y_for(item["balance"]), item["balance"], item["label"]))
        self._points = points

        # Guía vertical del mes bajo el ratón
        if self._hover is not None and self._hover < count:
            painter.setPen(QPen(QColor("#3F3F46"), 1, Qt.DashLine))
            hx = points[self._hover][0]
            painter.drawLine(QPointF(hx, top), QPointF(hx, top + chart_h))

        # Línea: en rojo claro los tramos que terminan bajo cero
        for index in range(1, count):
            x1, y1, _, _ = points[index - 1]
            x2, y2, value2, _ = points[index]
            color = self.NEGATIVE if value2 < 0 else self.LINE
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Meses: tantos como quepan sin pisarse
        painter.setFont(axis_font)
        painter.setPen(QColor(self.AXIS_TEXT))
        label_w = max(axis_metrics.horizontalAdvance(p[3]) for p in points) + 12
        every = 1 if count == 1 else max(1, math.ceil(label_w / self._step_x))
        for index in range(0, count, every):
            x = points[index][0]
            rect_x = min(max(x - label_w / 2, left - label_w / 2), w - label_w)
            painter.drawText(
                QRectF(max(0, rect_x), h - bottom + 8, label_w, 18),
                Qt.AlignCenter,
                points[index][3],
            )

        # Importes: solo los puntos clave (hoy, final, máximo y mínimo),
        # sin que se solapen. El resto se ve pasando el ratón.
        key_points = []
        for index in (
            0,
            count - 1,
            max(range(count), key=lambda i: values[i]),
            min(range(count), key=lambda i: values[i]),
        ):
            if index not in key_points:
                key_points.append(index)

        value_font = QFont("Segoe UI", 8, QFont.Bold)
        value_metrics = QFontMetrics(value_font)
        painter.setFont(value_font)
        placed = []
        for index in key_points:
            x, y, value, _ = points[index]
            text = HIDDEN_MONEY if self.hidden else whole_money(value)
            box_w = value_metrics.horizontalAdvance(text) + 10
            box_h = 17
            box_x = min(max(x - box_w / 2, 0), w - box_w)
            above = y - box_h - 7
            below = y + 7
            box_y = below if (value < 0 or above < 2) else above
            box = QRectF(box_x, box_y, box_w, box_h)
            if any(box.intersects(other) for other in placed):
                alternative = QRectF(box_x, below if box_y == above else above, box_w, box_h)
                if alternative.top() < 2 or any(alternative.intersects(o) for o in placed):
                    continue
                box = alternative
            placed.append(box)

            color = QColor(self.NEGATIVE if value < 0 else self.LINE)
            background = QColor(self.BACKGROUND)
            background.setAlpha(220)
            painter.setPen(Qt.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(color)
            painter.drawText(box, Qt.AlignCenter, text)

        # Puntos (los clave y el del ratón, más grandes)
        for index, (x, y, value, _) in enumerate(points):
            color = QColor(self.NEGATIVE if value < 0 else self.LINE)
            radius = 4 if (index in key_points or index == self._hover) else 2.5
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), radius, radius)

    @staticmethod
    def money(value):
        return money(value)


class ExpenseDonutChart(QWidget):
    """Gráfico circular de distribución de gastos por categoría."""

    PALETTE = [
        "#D71920",
        "#FF5A5F",
        "#A7171C",
        "#7F1D1D",
        "#71717A",
        "#52525B",
        "#3F3F46",
        "#A1A1AA",
        "#27272A",
    ]

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(155)
        self.categories = []
        self.hidden = False

    def set_hidden(self, hidden):
        self.hidden = hidden
        self.update()

    def set_data(self, categories):
        self.categories = sorted(
            categories.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        total = sum(value for _, value in self.categories)

        if total <= 0:
            painter.setPen(QColor("#71717A"))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Sin gastos registrados",
            )
            return

        w = self.width()
        h = self.height()

        diameter = min(h - 20, w * 0.43)
        diameter = max(90, diameter)

        x = 10
        y = (h - diameter) / 2
        rect = QRectF(x, y, diameter, diameter)

        start_angle = 90 * 16

        for index, (_, value) in enumerate(self.categories):
            span = -360 * 16 * value / total
            painter.setPen(Qt.NoPen)
            painter.setBrush(
                QColor(self.PALETTE[index % len(self.PALETTE)])
            )
            painter.drawPie(
                rect,
                int(start_angle),
                int(span),
            )
            start_angle += span

        # Agujero central, con el total ajustado a su tamaño
        inner = rect.adjusted(
            diameter * 0.24,
            diameter * 0.24,
            -diameter * 0.24,
            -diameter * 0.24,
        )
        painter.setBrush(QColor("#101012"))
        painter.drawEllipse(inner)

        text = HIDDEN_MONEY if self.hidden else self.compact_money(total)
        available = inner.width() * 0.78
        size = 12
        font = QFont("Segoe UI", size, QFont.Bold)
        while size > 7 and QFontMetrics(font).horizontalAdvance(text) > available:
            size -= 1
            font.setPointSize(size)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(font)
        painter.drawText(inner, Qt.AlignCenter, text)

        # Leyenda: tantas categorías como quepan (máximo 6)
        row_h = 24
        rows = max(1, min(len(self.categories), 6, int((h - 8) // row_h)))
        legend_x = x + diameter + 22
        legend_y = max(4, (h - rows * row_h) / 2)

        painter.setFont(QFont("Segoe UI", 9))

        for index, (category, value) in enumerate(self.categories[:rows]):
            color = QColor(self.PALETTE[index % len(self.PALETTE)])
            top = legend_y + index * row_h

            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(legend_x, top + 4, 10, 10), 2, 2)

            percentage = value / total * 100
            painter.setPen(QColor("#D4D4D8"))
            painter.drawText(
                QRectF(legend_x + 17, top, max(1, w - legend_x - 17), 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{category} · {percentage:.0f}%",
            )

    @staticmethod
    def compact_money(value):
        return compact_money(value)
