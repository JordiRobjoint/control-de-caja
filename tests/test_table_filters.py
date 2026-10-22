"""Filtros por columna como en Excel (ui/table_filters.py)."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QWidget  # noqa: E402

from ui.table_filters import EMPTY, ColumnFilters, FilterPopup, sort_key  # noqa: E402

ROWS = [
    {"id": 1, "cells": ["Talleres Norte", "Dietas", "15,00 €", "02/09/2026"]},
    {"id": 2, "cells": ["Talleres Norte", "Vuelo", "1.380,01 €", "20/09/2026"]},
    {"id": 3, "cells": ["General", "Software", "54,99 €", "—"]},
    {"id": 4, "cells": ["Talleres Norte", "Dietas", "30,00 €", "14/08/2026"]},
    {"id": 5, "cells": ["General", "Seguros", "1.271,71 €", "06/10/2026"]},
]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Page(QWidget):
    def __init__(self):
        super().__init__()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Proyecto", "Categoría", "Total", "Fecha"])
        self.filters = ColumnFilters(self.table, self)
        self.status = self.filters.status_widget()
        self.load()

    def load(self, rows=ROWS):
        self.rows = [dict(r) for r in rows]
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, text in enumerate(row["cells"]):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.filters.apply()

    def visible_ids(self):
        return [self.rows[r]["id"] for r in range(self.table.rowCount())
                if not self.table.isRowHidden(r)]

    def table_matches_rows(self):
        return all(
            self.table.item(r, 2).text() == self.rows[r]["cells"][2]
            for r in range(self.table.rowCount())
        )


def test_claves_de_orden():
    assert sort_key("1.380,01 €") > sort_key("54,99 €") > sort_key("-3,00 €")
    assert sort_key("21,00 %") < sort_key("100,00 %")
    assert sort_key("02/09/2026") > sort_key("14/08/2026")
    assert sort_key("01/09/2026 - 30/09/2026") > sort_key("14/08/2026")
    assert sort_key("hotel") < sort_key("Vuelo")
    assert sort_key("") > sort_key("zzz")          # vacías al final


def test_filtrar_combinando_columnas(app):
    page = Page()
    assert page.filters.labels[1] == "Categoría"
    assert page.table.horizontalHeaderItem(1).text() == "▾ Categoría"
    assert not page.status.isVisibleTo(page)

    page.filters.set_filter(0, {"Talleres Norte"})
    assert page.visible_ids() == [1, 2, 4]
    page.filters.set_filter(1, {"Dietas"})
    assert page.visible_ids() == [1, 4]
    assert page.table.horizontalHeaderItem(1).text() == "▼ Categoría"
    assert page.status.isVisibleTo(page)
    assert page.filters.status_label.text() == "Mostrando 2 de 5"

    # Los valores ofrecidos en una columna respetan los filtros de las otras.
    assert page.filters.values(1) == ["Dietas", "Vuelo"]

    page.filters.clear()
    assert page.visible_ids() == [1, 2, 3, 4, 5]
    assert not page.status.isVisibleTo(page)


def test_ordenar_mantiene_tabla_y_datos_alineados(app):
    page = Page()
    page.filters.set_sort(2, descending=True)          # Total, Z -> A
    assert [r["id"] for r in page.rows] == [2, 5, 3, 4, 1]
    assert page.table_matches_rows()
    assert page.table.horizontalHeaderItem(2).text() == "▾ ↓ Total"

    page.filters.set_sort(3, descending=False)         # Fecha, A -> Z; vacía al final
    assert [r["id"] for r in page.rows] == [4, 1, 2, 5, 3]
    page.filters.set_sort(3, descending=True)
    assert [r["id"] for r in page.rows] == [5, 2, 1, 4, 3]
    assert page.table_matches_rows()


def test_filtro_y_orden_se_conservan_al_recargar(app):
    page = Page()
    page.filters.set_filter(0, {"General"})
    page.filters.set_sort(2, descending=False)
    page.table.setCurrentCell(1, 0)

    page.load(ROWS + [{"id": 6, "cells": ["General", "Marketing", "10,00 €", "01/10/2026"]}])
    assert page.visible_ids() == [6, 3, 5]
    assert page.table_matches_rows()
    # Ninguna fila queda seleccionada tras recargar (Editar no actúa a ciegas).
    assert page.table.currentRow() == -1


def test_vacias(app):
    page = Page()
    assert EMPTY in page.filters.values(3)
    page.filters.set_filter(3, {EMPTY})
    assert page.visible_ids() == [3]


def test_ventanita(app):
    page = Page()
    popup = FilterPopup(page.filters, 1)
    texts = [item.text() for item in popup.value_items]
    assert texts == ["Dietas", "Seguros", "Software", "Vuelo"]
    assert popup.all_item.checkState() == Qt.Checked

    # Desmarcar "Vuelo" y aceptar.
    popup.value_items[3].setCheckState(Qt.Unchecked)
    assert popup.all_item.checkState() == Qt.PartiallyChecked
    popup.accept()
    assert page.visible_ids() == [1, 3, 4, 5]

    # Al reabrir, "Vuelo" sigue desmarcada; buscar deja marcadas solo las que coinciden.
    popup = FilterPopup(page.filters, 1)
    assert [i.checkState() == Qt.Checked for i in popup.value_items] == [True, True, True, False]
    popup.search.setText("s")
    assert [i.text() for i in popup.shown_items()] == ["Dietas", "Seguros", "Software"]
    popup.search.setText("seg")
    popup.accept()
    assert page.visible_ids() == [5]

    # Seleccionar todo + aceptar = sin filtro en esa columna.
    popup = FilterPopup(page.filters, 1)
    popup.all_item.setCheckState(Qt.Checked)
    popup.accept()
    assert 1 not in page.filters.allowed
    assert page.visible_ids() == [1, 2, 3, 4, 5]

    # Ordenar desde la ventanita.
    FilterPopup(page.filters, 2).sort(False)
    assert [r["id"] for r in page.rows] == [1, 4, 3, 5, 2]
