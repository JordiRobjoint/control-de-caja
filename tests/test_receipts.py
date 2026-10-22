"""
Lectura de tickets: nunca se llama a la API real; se usa un cliente falso
que devuelve la respuesta que daría Claude.
"""

import base64
import io
import json
from datetime import date
from types import SimpleNamespace

import pytest

from services import receipts

CATEGORIES = ["Hotel", "Combustible", "Dietas", "Otros"]


def raw(**overrides):
    data = {
        "is_expense_document": True,
        "supplier": "Hotel Bahía",
        "supplier_tax_id": "B12345678",
        "concept": "Hotel 2 noches Vigo",
        "category": "Hotel",
        "date": "2026-10-03",
        "invoice_reference": "FS-0042",
        "vat_lines": [{"rate": 10, "base": 180.0, "vat": 18.0}],
        "total": 198.0,
        "paid": True,
        "notes": "",
    }
    data.update(overrides)
    return data


class FakeClient:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload = payload
        self.stop_reason = stop_reason
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=text)],
        )


def png_file(path, size=(40, 60)):
    from PIL import Image
    Image.new("RGB", size, "white").save(path)
    return path


# ------------------------------------------------------------
# Normalización
# ------------------------------------------------------------

def test_nombre_corto_para_el_archivo():
    assert receipts.file_label("media markt") == "MediaMarkt"
    assert receipts.file_label("Quirón") == "Quiron"
    assert receipts.file_label("") == ""
    assert receipts.normalize(raw(file_label="Peaje"), CATEGORIES)["file_label"] == "Peaje"


def test_carpeta_del_mes():
    from pathlib import Path

    assert receipts.month_folder(Path("F"), date(2026, 1, 9)) == Path("F/2026/01.ENERO")
    assert receipts.month_folder(Path("F"), date(2026, 12, 1)) == Path("F/2026/12.DICIEMBRE")


def test_un_solo_tipo_de_iva():
    data = receipts.normalize(raw(), CATEGORIES)
    assert data["date"] == date(2026, 10, 3)
    assert (data["base_amount"], data["vat_rate"], data["vat_amount"], data["total_amount"]) == (
        180.0, 10.0, 18.0, 198.0
    )
    assert data["notes"] == ""


def test_varios_tipos_de_iva_usan_el_tipo_medio_y_avisan():
    data = receipts.normalize(raw(vat_lines=[
        {"rate": 10, "base": 100.0, "vat": 10.0},
        {"rate": 21, "base": 50.0, "vat": 10.5},
    ], total=170.5), CATEGORIES)
    assert (data["base_amount"], data["vat_amount"]) == (150.0, 20.5)
    assert data["vat_rate"] == 13.67
    assert "Varios tipos de IVA" in data["notes"]


def test_sin_desglose_toma_el_total_como_base():
    data = receipts.normalize(raw(vat_lines=[], total=12.4), CATEGORIES)
    assert (data["base_amount"], data["vat_rate"], data["total_amount"]) == (12.4, 0.0, 12.4)


def test_categoria_desconocida_y_fecha_invalida():
    data = receipts.normalize(raw(category="Peluquería", date="03/10/2026"), CATEGORIES)
    assert data["category"] == "Otros"
    assert data["date"] is None


# ------------------------------------------------------------
# Documento
# ------------------------------------------------------------

def test_formato_no_admitido(tmp_path):
    path = tmp_path / "ticket.heic"
    path.write_bytes(b"x")
    with pytest.raises(receipts.ReceiptError, match="Formato no admitido"):
        receipts.document_block(path)


def test_pdf_se_envia_como_documento(tmp_path):
    path = tmp_path / "factura.pdf"
    path.write_bytes(b"%PDF-1.4 demo")
    block = receipts.document_block(path)
    assert block["type"] == "document"
    assert base64.b64decode(block["source"]["data"]) == b"%PDF-1.4 demo"


def test_imagen_grande_o_de_escaner_se_reduce_a_jpeg(tmp_path):
    from PIL import Image

    small = receipts.document_block(png_file(tmp_path / "small.png"))
    assert small["source"]["media_type"] == "image/png"

    big = png_file(tmp_path / "big.png", size=(4000, 3000))
    block = receipts.document_block(big)
    assert block["source"]["media_type"] == "image/jpeg"
    image = Image.open(io.BytesIO(base64.b64decode(block["source"]["data"])))
    assert max(image.size) == receipts.MAX_IMAGE_SIDE

    bmp = tmp_path / "scan.bmp"
    Image.new("RGB", (30, 30)).save(bmp)
    assert receipts.document_block(bmp)["source"]["media_type"] == "image/jpeg"


# ------------------------------------------------------------
# Lectura
# ------------------------------------------------------------

def test_lee_el_ticket(tmp_path):
    client = FakeClient(raw())
    data = receipts.read_receipt(
        png_file(tmp_path / "t.png"), CATEGORIES, company="Empresa", client=client
    )
    assert data["supplier"] == "Hotel Bahía"
    assert data["total_amount"] == 198.0

    call = client.calls[0]
    assert call["model"] == receipts.MODEL
    assert call["output_config"]["format"]["schema"] == receipts.SCHEMA
    assert "Empresa" in call["messages"][0]["content"][1]["text"]
    assert "Combustible" in call["messages"][0]["content"][1]["text"]


@pytest.mark.parametrize("payload, stop_reason, message", [
    (raw(), "refusal", "no ha querido"),
    (raw(), "max_tokens", "se ha cortado"),
    ("no es json", "end_turn", "interpretar"),
])
def test_errores_de_respuesta(tmp_path, payload, stop_reason, message):
    with pytest.raises(receipts.ReceiptError, match=message):
        receipts.read_receipt(
            png_file(tmp_path / "t.png"), CATEGORIES,
            client=FakeClient(payload, stop_reason),
        )


def test_sin_clave_de_api(tmp_path):
    with pytest.raises(receipts.ReceiptError, match="Falta la clave"):
        receipts.read_receipt(png_file(tmp_path / "t.png"), CATEGORIES)


# ------------------------------------------------------------
# Archivo
# ------------------------------------------------------------

def test_archiva_sin_sobrescribir(tmp_path):
    source = png_file(tmp_path / "IMG_0001.png")
    folder = tmp_path / "gastos"

    def archive(label):
        return receipts.archive_document(
            source, expense_date=date(2026, 10, 4), label=label, folder=folder
        )

    month = folder / "2026" / "10.OCTUBRE"
    assert archive("Peaje") == month / "2026_10_04_Peaje.png"
    assert archive("Peaje") == month / "2026_10_04_Peaje1.png"
    assert archive("Peaje") == month / "2026_10_04_Peaje2.png"
    assert archive('Quirón "Salud" S/L') == month / "2026_10_04_QuironSaludSL.png"
    assert archive("") == month / "2026_10_04.png"
    assert source.exists()

    first = month / "2026_10_04_Peaje.png"

    # Un documento que ya está archivado no se vuelve a copiar.
    assert receipts.archive_document(first, folder=folder) == first


def test_clave_sin_espacio_de_trabajo_da_un_mensaje_claro(tmp_path):
    import anthropic
    import httpx2

    class WorkspaceClient(FakeClient):
        def create(self, **kwargs):
            request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError(
                "This API key is not scoped to a workspace, so this request must "
                "include the anthropic-workspace-id header",
                response=httpx2.Response(400, request=request),
                body=None,
            )

    with pytest.raises(receipts.ReceiptError, match="espacio de trabajo"):
        receipts.read_receipt(
            png_file(tmp_path / "t.png"), CATEGORIES, client=WorkspaceClient(raw())
        )
