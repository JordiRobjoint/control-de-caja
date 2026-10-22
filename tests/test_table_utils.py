"""Relleno rápido de tablas (ui/table_utils.py)."""

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ui.table_utils import bulk_fill, fills  # noqa: E402

ROWS, COLUMNS = 300, 12


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_table():
    table = QTableWidget(0, COLUMNS)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    for column in range(4, COLUMNS):
        header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
    return table


def fill(table):
    table.setRowCount(ROWS)
    for row in range(ROWS):
        for column in range(COLUMNS):
            table.setItem(row, column, QTableWidgetItem(f"{row * column:,.2f} €"))


def test_rellena_rapido_y_deja_las_columnas_como_estaban(app):
    table = make_table()
    start = time.perf_counter()
    with bulk_fill(table):
        fill(table)
    assert time.perf_counter() - start < 2.0

    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.Stretch
    assert all(
        header.sectionResizeMode(c) == QHeaderView.ResizeToContents
        for c in range(4, COLUMNS)
    )
    assert table.updatesEnabled()
    # La columna se ha medido con el texto más largo.
    widest = max(
        table.fontMetrics().horizontalAdvance(table.item(r, 11).text())
        for r in range(ROWS)
    )
    assert header.sectionSize(11) >= widest


def test_decorador_con_atributo_o_argumento_y_tras_un_error(app):
    class Page(QWidget):
        def __init__(self):
            super().__init__()
            self.table = make_table()

        @fills("table")
        def load(self):
            fill(self.table)
            return "ok"

        @fills("table")
        def fill_other(self, table):
            assert not table.updatesEnabled()
            fill(table)

        @fills("table")
        def broken(self):
            raise ValueError("fallo")

    page = Page()
    assert page.load() == "ok"
    assert page.table.rowCount() == ROWS

    other = make_table()
    page.fill_other(other)
    assert other.rowCount() == ROWS and other.updatesEnabled()

    with pytest.raises(ValueError):
        page.broken()
    # Aunque falle, la tabla no se queda congelada.
    assert page.table.updatesEnabled()
    assert page.table.horizontalHeader().sectionResizeMode(11) == QHeaderView.ResizeToContents
