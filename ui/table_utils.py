import functools
import inspect
from contextlib import ExitStack, contextmanager

from PySide6.QtWidgets import QHeaderView


@contextmanager
def bulk_fill(table):
    """
    Rellena una tabla sin que Qt recalcule nada en cada celda.

    Con columnas "ajustar al contenido", Qt vuelve a medir la columna
    entera cada vez que se pone una celda: con 100 filas x 12 columnas
    son más de mil mediciones y la página tarda segundos en abrir. Aquí
    se miden una sola vez, al terminar.
    """
    header = table.horizontalHeader()
    auto = [
        column
        for column in range(table.columnCount())
        if header.sectionResizeMode(column) == QHeaderView.ResizeToContents
    ]
    sorting = table.isSortingEnabled()

    table.setUpdatesEnabled(False)
    table.setSortingEnabled(False)
    for column in auto:
        header.setSectionResizeMode(column, QHeaderView.Interactive)
    try:
        yield
    finally:
        for column in auto:
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        table.setSortingEnabled(sorting)
        table.setUpdatesEnabled(True)


def fills(*tables):
    """
    Decorador para los métodos que rellenan tablas: aplica `bulk_fill`
    a cada tabla nombrada, que puede ser un atributo de la página
    (`self.table`) o un argumento del método (`table`).
    """
    def decorator(method):
        signature = inspect.signature(method)

        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            arguments = signature.bind(self, *args, **kwargs).arguments
            with ExitStack() as stack:
                for name in tables:
                    table = arguments.get(name) or getattr(self, name)
                    stack.enter_context(bulk_fill(table))
                return method(self, *args, **kwargs)

        return wrapper

    return decorator
