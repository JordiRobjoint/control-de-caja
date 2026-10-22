"""
Envío de tickets desde el móvil: servidor local y diálogo del QR.
Las pruebas usan 127.0.0.1, así que no abren nada a la red.
"""

import io
import json
import threading
import urllib.error
import urllib.request

import pytest

from services.phone_upload import MAX_UPLOAD_BYTES, PhoneUploadServer


def jpeg_bytes(size=(600, 800)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 200, 200)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def server():
    received = []
    server = PhoneUploadServer(lambda path, corners: received.append((path, corners)),
                               host="127.0.0.1")
    server.received = received
    server.start()
    try:
        yield server
    finally:
        server.stop()


def request(url, data=None, content_type="image/jpeg", headers=None):
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", content_type)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def crop(server, photo_id, corners):
    body = json.dumps({"id": photo_id, "corners": corners}).encode()
    return request(server.url + "/recortar", body, "application/json")


def test_la_pagina_solo_responde_con_la_clave(server):
    status, body = request(server.url)
    assert status == 200
    assert 'capture="environment"' in body
    assert "Recortar y enviar" in body

    base = server.url.rsplit("/", 1)[0]
    assert request(base + "/otra-clave")[0] == 404
    assert request(base + "/")[0] == 404
    assert request(base + "/otra-clave/subir", b"x")[0] == 404
    assert request(base + "/otra-clave/recortar", b"{}", "application/json")[0] == 404
    assert server.received == []


def test_foto_propone_recorte_y_se_entrega_al_confirmar(server):
    status, body = request(server.url + "/subir", jpeg_bytes())
    assert status == 200
    answer = json.loads(body)
    assert len(answer["corners"]) == 4
    assert all(0 <= v <= 1 for point in answer["corners"] for v in point)
    # Aún no se entrega: falta confirmar el recorte en el móvil.
    assert server.received == []

    corners = [[0.1, 0.1], [0.9, 0.12], [0.88, 0.9], [0.12, 0.88]]
    assert crop(server, answer["id"], corners)[0] == 200
    [(path, received)] = server.received
    assert path.suffix == ".jpg" and path.exists()
    assert received == corners

    # La misma foto no se puede confirmar dos veces.
    assert crop(server, answer["id"], corners)[0] == 400


def test_pdf_se_entrega_sin_recorte(server):
    status, body = request(server.url + "/subir", b"%PDF-1.4", content_type="application/pdf")
    assert status == 200 and json.loads(body) == {"done": True}
    [(path, corners)] = server.received
    assert path.suffix == ".pdf" and corners is None


@pytest.mark.parametrize("corners", [
    [[0, 0], [1, 0], [1, 1]],                        # tres esquinas
    [[0, 0], [2, 0], [1, 1], [0, 1]],                # fuera de la foto
    [[0.5, 0.5], [0.5, 0.5], [0.5, 0.5], [0.5, 0.5]],  # sin área
    "no",
])
def test_rechaza_recortes_no_validos(server, corners):
    answer = json.loads(request(server.url + "/subir", jpeg_bytes())[1])
    assert crop(server, answer["id"], corners)[0] == 400
    assert server.received == []


def test_rechaza_formatos_tamanos_y_fotos_rotas(server):
    assert request(server.url + "/subir", b"x", content_type="text/html")[0] == 415
    assert request(server.url + "/subir", b"")[0] == 400
    assert request(server.url + "/subir", b"\xff\xd8 no es una foto")[0] == 400
    # Se rechaza por la cabecera, sin leer el cuerpo.
    status = request(
        server.url + "/subir", b"x",
        headers={"Content-Length": str(MAX_UPLOAD_BYTES + 1)},
    )[0]
    assert status == 413
    assert crop(server, "no-existe", [[0, 0], [1, 0], [1, 1], [0, 1]])[0] == 400
    assert server.received == []


def test_dialogo_del_qr_recibe_la_foto_y_cierra_el_servidor(tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    from ui.pages.dialogs.phone_dialog import PhoneUploadDialog

    app = QApplication.instance() or QApplication([])

    dialog = PhoneUploadDialog(
        server_factory=lambda on_file: PhoneUploadServer(on_file, host="127.0.0.1")
    )
    url = dialog.server.url
    server = dialog.server
    assert dialog.url.text() == url
    assert not dialog.qr.pixmap().isNull()

    corners = [[0.05, 0.05], [0.95, 0.05], [0.95, 0.95], [0.05, 0.95]]

    def phone():
        answer = json.loads(request(url + "/subir", jpeg_bytes())[1])
        crop(server, answer["id"], corners)

    threading.Thread(target=phone).start()

    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    dialog.open()
    loop.exec()

    assert dialog.result() == QDialog.Accepted
    assert dialog.path.endswith(".jpg")
    assert dialog.corners == corners
    assert dialog.server is None
    assert server._server is None
    app.processEvents()
