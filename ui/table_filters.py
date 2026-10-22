"""
Filtros por columna como en Excel para las tablas de Pedidos, Cobros y
Pagos.

Cada cabecera lleva un ▾; al pulsarla se abre una ventanita con Ordenar
A→Z / Z→A, un buscador y la lista de valores de la columna con casillas.
Las columnas filtradas se marcan en rojo con ▼.

Las páginas guardan sus datos en una lista (`page.rows`) y "Editar" usa
el número de fila seleccionada. Por eso los filtros ocultan filas sin
quitarlas, y al ordenar se reordenan a la vez la tabla y esa lista.
"""

from __future__ import annotations

import re
from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

EMPTY = "(vacías)"
# La flecha va delante del nombre: si la columna es estrecha se recorta el
# final del nombre, nunca la flecha.
ARROW = "▾ "
ACTIVE_ARROW = "▼ "
ACTIVE_COLOR = QColor("#D71920")

_MONEY = re.compile(r"^-?[\d.]+(,\d+)?\s*[€%]?$")
_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def cell_text(table, row, column) -> str:
    item = table.item(row, column)
    text = item.text().strip() if item is not None else ""
    return "" if text in ("—", "-") else text


def sort_key(text: str):
    """
    Clave para ordenar como espera una persona: importes y porcentajes
    como números, fechas como fechas y el resto como texto. Las vacías,
    al final.
    """
    if not text:
        return (3, 0)
    plain = text.replace(" ", " ").strip()
    if _MONEY.match(plain.replace(" ", "")):
        number = plain.replace("€", "").replace("%", "").replace(" ", "")
        number = number.replace(".", "").replace(",", ".")
        try:
            return (0, float(number))
        except ValueError:
            pass
    match = _DATE.search(plain)
    if match:
        day, month, year = (int(x) for x in match.groups())
        try:
            return (1, date(year, month, day).toordinal())
        except ValueError:
            pass
    return (2, plain.casefold())


class ColumnFilters:
    """
    Filtros y orden para una QTableWidget.

    `page` y `rows_attr`: la lista de datos de la página que va en el
    mismo orden que las filas de la tabla (se reordena al ordenar).
    Llamar a `apply()` cada vez que la página rellena la tabla.
    """

    def __init__(self, table, page, rows_attr: str = "rows"):
        self.table = table
        self.page = page
        self.rows_attr = rows_attr
        self.allowed: dict[int, set[str]] = {}   # columna -> valores visibles
        self.sort: tuple[int, bool] | None = None  # (columna, descendente)
        self.labels = [
            table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else ""
            for c in range(table.columnCount())
        ]
        self.popup = None
        self.status = None

        header = table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setTextElideMode(Qt.ElideRight)
        header.sectionClicked.connect(self.open_popup)
        self.update_headers()

    # ---------------------------------------------------------- estado

    @property
    def active(self) -> bool:
        return bool(self.allowed)

    def visible_count(self) -> int:
        return sum(not self.table.isRowHidden(r) for r in range(self.table.rowCount()))

    def clear(self):
        self.allowed.clear()
        self.apply()

    def set_filter(self, column: int, values: set[str] | None):
        if values is None:
            self.allowed.pop(column, None)
        else:
            self.allowed[column] = set(values)
        self.apply()

    def set_sort(self, column: int, descending: bool):
        self.sort = (column, descending)
        self.apply()

    # ---------------------------------------------------------- aplicar

    def apply(self):
        """Ordena y filtra lo que haya en la tabla. Llamar tras rellenarla."""
        if self.sort is not None:
            self._sort_rows(*self.sort)
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, not self._passes(row))
        # Que "Editar" no actúe sobre una fila que se acaba de ocultar.
        self.table.setCurrentCell(-1, -1)
        self.table.clearSelection()
        self.update_headers()
        self.update_status()

    def status_widget(self):
        """'Mostrando 12 de 93 · Quitar filtros', solo con filtros puestos."""
        self.status = QWidget()
        layout = QHBoxLayout(self.status)
        layout.setContentsMargins(0, 0, 0, 6)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #D71920; font-weight: 600;")
        clear = QPushButton("Quitar filtros")
        clear.setObjectName("secondaryButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self.clear)
        layout.addWidget(self.status_label)
        layout.addWidget(clear)
        layout.addStretch()
        self.update_status()
        return self.status

    def update_status(self):
        if self.status is None:
            return
        self.status.setVisible(self.active)
        if self.active:
            self.status_label.setText(
                f"Mostrando {self.visible_count()} de {self.table.rowCount()}"
            )

    def _passes(self, row, skip_column=None) -> bool:
        for column, values in self.allowed.items():
            if column == skip_column:
                continue
            if (cell_text(self.table, row, column) or EMPTY) not in values:
                return False
        return True

    def _sort_rows(self, column, descending):
        table = self.table
        count = table.rowCount()
        rows = getattr(self.page, self.rows_attr, None)
        if count < 2 or rows is None or len(rows) != count:
            return
        order = sorted(
            range(count),
            key=lambda r: sort_key(cell_text(table, r, column)),
            reverse=descending,
        )
        if order == list(range(count)):
            return
        # Las vacías siempre al final, también en Z→A.
        if descending:
            empty = [r for r in order if not cell_text(table, r, column)]
            order = [r for r in order if cell_text(table, r, column)] + empty

        items = [
            [table.takeItem(r, c) for c in range(table.columnCount())]
            for r in range(count)
        ]
        for new_row, old_row in enumerate(order):
            for c, item in enumerate(items[old_row]):
                table.setItem(new_row, c, item)
        setattr(self.page, self.rows_attr, [rows[r] for r in order])

    def update_headers(self):
        for column, label in enumerate(self.labels):
            item = self.table.horizontalHeaderItem(column)
            if item is None:
                continue
            filtered = column in self.allowed
            arrow = ACTIVE_ARROW if filtered else ARROW
            if self.sort and self.sort[0] == column:
                arrow += "↓ " if self.sort[1] else "↑ "
            item.setText(arrow + label)
            item.setForeground(ACTIVE_COLOR if filtered else QColor())
            item.setToolTip(
                "Filtrada: pulsa para cambiar el filtro" if filtered
                else "Pulsa para filtrar u ordenar"
            )

    # ------------------------------------------------------- ventanita

    def values(self, column) -> list[str]:
        """Valores de la columna en las filas que pasan los OTROS filtros."""
        found = {
            cell_text(self.table, r, column) or EMPTY
            for r in range(self.table.rowCount())
            if self._passes(r, skip_column=column)
        }
        return sorted(found, key=lambda v: (v == EMPTY, sort_key("" if v == EMPTY else v)))

    def open_popup(self, column):
        if self.popup is not None:
            self.popup.close()
        self.popup = FilterPopup(self, column)
        header = self.table.horizontalHeader()
        x = header.sectionViewportPosition(column)
        point = header.mapToGlobal(QPoint(x, header.height()))
        self.popup.move(point)
        self.popup.show()
        self.popup.search.setFocus()


class FilterPopup(QFrame):
    def __init__(self, filters: ColumnFilters, column: int):
        super().__init__(filters.table, Qt.Popup)
        self.filters = filters
        self.column = column
        self.setObjectName("filterPopup")
        self.setStyleSheet("""
            #filterPopup { background-color: #151517; border: 1px solid #343438;
                           border-radius: 8px; }
            #filterPopup QPushButton { background-color: #202024; color: #F4F4F5;
                           border: 1px solid #343438; border-radius: 6px; padding: 6px 10px; }
            #filterPopup QPushButton:hover { border-color: #D71920; }
            #filterPopup QListWidget { background-color: #101012; border: 1px solid #303034;
                           border-radius: 6px; }
        """)
        self.setMinimumWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel(filters.labels[column])
        title.setStyleSheet("font-weight: 700;")
        layout.addWidget(title)

        sort_row = QHBoxLayout()
        ascending = QPushButton("↑ Ordenar A → Z")
        descending = QPushButton("↓ Ordenar Z → A")
        ascending.clicked.connect(lambda: self.sort(False))
        descending.clicked.connect(lambda: self.sort(True))
        sort_row.addWidget(ascending)
        sort_row.addWidget(descending)
        layout.addLayout(sort_row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar…")
        self.search.textChanged.connect(self.search_changed)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setMinimumHeight(220)
        self.list.itemChanged.connect(self.item_changed)
        layout.addWidget(self.list)

        allowed = filters.allowed.get(column)
        self.all_item = QListWidgetItem("(Seleccionar todo)")
        self.all_item.setFlags(self.all_item.flags() | Qt.ItemIsUserCheckable)
        self.list.addItem(self.all_item)
        self.value_items = []
        for value in filters.values(column):
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if allowed is None or value in allowed else Qt.Unchecked
            )
            self.list.addItem(item)
            self.value_items.append(item)
        self.refresh_all_item()

        buttons = QHBoxLayout()
        accept = QPushButton("Aceptar")
        clear = QPushButton("Borrar filtro")
        accept.clicked.connect(self.accept)
        clear.clicked.connect(self.clear)
        buttons.addWidget(accept)
        buttons.addWidget(clear)
        layout.addLayout(buttons)

        self.search.returnPressed.connect(self.accept)

    # ------------------------------------------------------------ casillas

    def shown_items(self):
        return [item for item in self.value_items if not item.isHidden()]

    def refresh_all_item(self):
        shown = self.shown_items()
        checked = sum(item.checkState() == Qt.Checked for item in shown)
        self.list.blockSignals(True)
        if shown and checked == len(shown):
            self.all_item.setCheckState(Qt.Checked)
        elif checked:
            self.all_item.setCheckState(Qt.PartiallyChecked)
        else:
            self.all_item.setCheckState(Qt.Unchecked)
        self.list.blockSignals(False)

    def item_changed(self, item):
        if item is self.all_item:
            state = Qt.Unchecked if item.checkState() == Qt.Unchecked else Qt.Checked
            self.list.blockSignals(True)
            for value_item in self.shown_items():
                value_item.setCheckState(state)
            self.list.blockSignals(False)
        self.refresh_all_item()

    def search_changed(self, text):
        """Como en Excel: al buscar, quedan marcadas solo las que coinciden."""
        needle = text.strip().casefold()
        self.list.blockSignals(True)
        for item in self.value_items:
            match = needle in item.text().casefold()
            item.setHidden(not match)
            if needle:
                item.setCheckState(Qt.Checked if match else Qt.Unchecked)
        self.list.blockSignals(False)
        self.refresh_all_item()

    # ------------------------------------------------------------- acciones

    def sort(self, descending):
        self.filters.set_sort(self.column, descending)
        self.close()

    def accept(self):
        checked = {item.text() for item in self.value_items if item.checkState() == Qt.Checked}
        everything = {item.text() for item in self.value_items}
        self.filters.set_filter(self.column, None if checked == everything else checked)
        self.close()

    def clear(self):
        self.filters.set_filter(self.column, None)
        self.close()
