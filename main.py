import sys
import os
import ctypes
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app_info import APP_TITLE, APP_VERSION
from database.database import (
    backup_to_external,
    create_database,
    duplicate_invoice_numbers,
    external_backup_folder,
)
from ui.main_window import MainWindow


def resource_path(relative_path):
    """
    Devuelve la ruta correcta tanto ejecutando desde Python
    como desde el EXE generado con PyInstaller.
    """
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path


if __name__ == "__main__":

    # Identificador propio de la aplicación para Windows.
    # Ayuda a que Windows utilice nuestro icono en la barra de tareas.
    if sys.platform == "win32":
        app_id = "ControlDeCaja.App"

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                app_id
            )
        except Exception:
            pass

    # Crear / actualizar base de datos
    create_database()

    app = QApplication(sys.argv)

    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)

    # Icono de la aplicación
    icon_path = resource_path(
        os.path.join("assets", "app.ico")
    )

    app_icon = QIcon(str(icon_path))

    app.setWindowIcon(app_icon)

    window = MainWindow()
    window.setWindowIcon(app_icon)

    window.show()

    # La base no admite números de factura repetidos; si ya los hay
    # (datos antiguos), se avisa en cada arranque hasta corregirlos.
    duplicates = duplicate_invoice_numbers()
    if duplicates:
        lines = "\n".join(
            f"  · Factura {number}: {count} cobros" for number, count in duplicates
        )
        QMessageBox.warning(
            window,
            "Números de factura repetidos",
            "Hay números de factura asignados a más de un cobro:\n\n"
            f"{lines}\n\n"
            "Corrígelos en Cobros (cada factura debe tener un número distinto).",
        )

    # Copia diaria en la carpeta externa (si está configurada).
    try:
        backup_to_external()
    except OSError as error:
        QMessageBox.warning(
            window,
            "Copia de seguridad externa",
            "No se ha podido hacer la copia en la carpeta externa:\n"
            f"{external_backup_folder()}\n\n{error}\n\n"
            "Comprueba que la unidad está conectada. La aplicación funciona "
            "con normalidad; se volverá a intentar en el próximo arranque o "
            "con «Copiar ahora» en Configuración.",
        )

    sys.exit(app.exec())