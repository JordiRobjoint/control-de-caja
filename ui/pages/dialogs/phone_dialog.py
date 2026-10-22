import io

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from services.phone_upload import PhoneUploadServer


class _Bridge(QObject):
    """Pasa el archivo del hilo del servidor al de la interfaz."""
    received = Signal(str, object)


class PhoneUploadDialog(QDialog):
    """
    Muestra un QR para enviar la foto del ticket desde el móvil.
    Se cierra solo al recibirla; la ruta queda en `self.path` y el
    recorte marcado en el móvil en `self.corners` (None si es un PDF).
    """

    def __init__(self, parent=None, server_factory=PhoneUploadServer):
        super().__init__(parent)

        self.path = None
        self.corners = None
        self.server = None

        self.bridge = _Bridge()
        self.bridge.received.connect(self.file_received)

        self.setWindowTitle("Ticket desde el móvil")
        self.setup_ui()

        try:
            self.server = server_factory(
                lambda path, corners: self.bridge.received.emit(str(path), corners)
            )
            self.server.start()
        except OSError as error:
            self.server = None
            self.status.setText(
                f"⚠ No se ha podido preparar la conexión con el móvil.\n{error}"
            )
            return

        self.show_qr(self.server.url)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(14)

        title = QLabel("Ticket desde el móvil")
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            "Apunta la cámara del móvil a este código, abre el enlace "
            "y haz la foto del ticket."
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)

        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setMinimumSize(280, 280)

        self.url = QLabel()
        self.url.setAlignment(Qt.AlignCenter)
        self.url.setObjectName("cardDescription")
        self.url.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.status = QLabel("Esperando la foto…")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-weight: 600;")

        help_text = QLabel(
            "El móvil tiene que estar en la misma wifi que el ordenador. "
            "Si la página no carga, revisa que Windows haya permitido el "
            "acceso a la aplicación en redes privadas (aviso del firewall "
            "la primera vez)."
        )
        help_text.setObjectName("cardDescription")
        help_text.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.rejected.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.qr)
        layout.addWidget(self.url)
        layout.addWidget(self.status)
        layout.addWidget(help_text)
        layout.addWidget(buttons)

        self.setMinimumWidth(440)

    def show_qr(self, url):
        import segno

        buffer = io.BytesIO()
        segno.make(url, error="m").save(buffer, kind="png", scale=7, border=2)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        self.qr.setPixmap(pixmap)
        self.url.setText(url)

    def file_received(self, path, corners=None):
        if self.path is not None:
            return
        self.path = path
        self.corners = corners
        self.accept()

    def done(self, result):
        if self.server is not None:
            self.server.stop()
            self.server = None
        super().done(result)


def receive_from_phone(parent):
    """
    Abre el diálogo y devuelve (ruta, recorte) del documento recibido, o
    None si se cancela.
    """
    dialog = PhoneUploadDialog(parent)
    if dialog.exec() != QDialog.Accepted:
        return None
    if not dialog.path:
        QMessageBox.warning(parent, "Móvil", "No ha llegado ningún archivo.")
        return None
    return dialog.path, dialog.corners
