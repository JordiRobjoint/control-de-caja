"""Tests de facturación (services/invoices.py)."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import invoices as inv


# ============================================================
# NUMERACIÓN
# ============================================================

@pytest.mark.parametrize("prefix, digits, number, expected", [
    ("", 4, 7, "0007"),
    ("FAC-{año}-", 4, 7, "FAC-2026-0007"),
    ("F{year}/", 3, 12, "F2026/012"),
    ("A", 0, 5, "A5"),           # mínimo un dígito
    (None, 2, 123, "123"),       # no recorta números largos
])
def test_format_number(prefix, digits, number, expected):
    assert inv.format_number(prefix, digits, number, 2026) == expected


@pytest.mark.parametrize("text, expected", [
    ("FAC-2026-0042", 42),
    ("0007 ", 7),
    ("sin número", None),
    ("", None),
    (None, None),
])
def test_trailing_number(text, expected):
    assert inv._trailing_number(text) == expected


def _add_collection(session, number, status=None):
    from database.models import Collection, Order, Project

    project = Project(name=f"P {number}", client="Cliente")
    session.add(project)
    session.flush()
    order = Order(project_id=project.id, order_number="1", amount=1000)
    session.add(order)
    session.flush()
    if status is None:
        status = "Facturado" if number else "Previsto"
    collection = Collection(order_id=order.id, concept="Hito", amount=100,
                            invoice_number=number, status=status)
    session.add(collection)
    session.flush()
    return collection


def test_suggest_invoice_number_sin_configurar_continua_el_mayor(session):
    assert inv.suggest_invoice_number(session, date(2026, 1, 1)) == "0001"
    _add_collection(session, "F-0007")
    _add_collection(session, "F-0012")
    _add_collection(session, None)
    assert inv.suggest_invoice_number(session, date(2026, 1, 1)) == "0013"


def test_suggest_invoice_number_con_configuracion(session):
    inv.save_settings(session, {
        "invoice_prefix": "FAC-{año}-",
        "invoice_digits": "3",
        "invoice_next_number": "5",
    })
    assert inv.suggest_invoice_number(session, date(2026, 6, 1)) == "FAC-2026-005"


def test_register_used_number_solo_avanza(session):
    inv.save_settings(session, {"invoice_next_number": "5"})

    inv.register_used_number(session, "FAC-2026-0009")
    assert inv.get_invoice_settings(session)["invoice_next_number"] == "10"

    inv.register_used_number(session, "FAC-2026-0003")
    assert inv.get_invoice_settings(session)["invoice_next_number"] == "10"

    inv.register_used_number(session, "sin número")
    assert inv.get_invoice_settings(session)["invoice_next_number"] == "10"


def test_invoice_number_in_use(session):
    collection = _add_collection(session, "0001")
    assert inv.invoice_number_in_use(session, "0001")
    assert not inv.invoice_number_in_use(session, "0001", exclude_collection_id=collection.id)
    assert not inv.invoice_number_in_use(session, "0002")


# ============================================================
# CONFIGURACIÓN
# ============================================================

def test_get_company_usa_valores_por_defecto(session):
    company = inv.get_company(session)
    assert company["company_name"] == ""
    assert inv.missing_company_fields(company) == [
        "Razón social", "CIF", "Dirección", "CP y población",
    ]


def test_save_settings_crea_y_actualiza(session):
    inv.save_settings(session, {"company_tax_id": "B123"})
    inv.save_settings(session, {"company_tax_id": "B456"})
    assert inv.get_company(session)["company_tax_id"] == "B456"


# ============================================================
# DATOS DE LA FACTURA
# ============================================================

def test_default_due_date():
    invoice_date = date(2026, 11, 1)
    with_expected = SimpleNamespace(expected_date=date(2026, 12, 1))
    past_expected = SimpleNamespace(expected_date=date(2026, 10, 1))

    assert inv.default_due_date(with_expected, invoice_date) == date(2026, 12, 1)
    assert inv.default_due_date(past_expected, invoice_date, 30) == date(2026, 12, 1)
    assert inv.default_due_date(past_expected, invoice_date, 60) == date(2027, 1, 1)
    assert inv.default_due_date(past_expected, invoice_date, 45) == date(2026, 12, 16)


def _invoice(**kw):
    collection = SimpleNamespace(amount=1234.56, concept="Hito 1", percentage=30)
    order = SimpleNamespace(order_number="123", description="Montaje", amount=10000)
    project = SimpleNamespace(name="Obra", reference="R-1", client="Cliente S.L.")
    args = dict(
        number="0001", invoice_date=date(2026, 10, 13), due_date=date(2026, 11, 13),
        vat_rate=21.0,
    )
    args.update(kw)
    return inv.build_invoice(collection, order, project, {"company_name": "Empresa"}, **args)


def test_build_invoice_importes():
    invoice = _invoice()
    assert invoice["base"] == 1234.56
    assert invoice["vat"] == 259.26
    assert invoice["total"] == 1493.82


def test_build_invoice_detalles_y_cliente():
    invoice = _invoice()
    (line,) = invoice["lines"]
    assert line["description"] == "Hito 1"
    assert line["details"] == [
        "Pedido 123 · Montaje",
        "30 % s/ importe del pedido (10.000,00 €)",
        "Proyecto: Obra (ref. R-1)",
    ]
    assert invoice["client"]["name"] == "Cliente S.L."

    invoice = _invoice(client_name="Razón Social S.A.", client_tax_id="A1")
    assert invoice["client"] == {"name": "Razón Social S.A.", "tax_id": "A1", "address": ""}


def test_build_invoice_no_duplica_la_palabra_pedido():
    collection = SimpleNamespace(amount=100, concept="", percentage=None)
    order = SimpleNamespace(order_number="Pedido 5", description=None, amount=0)
    invoice = inv.build_invoice(
        collection, order, None, {}, number="1", invoice_date=date(2026, 1, 1),
        due_date=None, vat_rate=21,
    )
    assert invoice["lines"][0]["description"] == "Servicios"
    assert invoice["lines"][0]["details"] == ["Pedido 5"]
    assert invoice["client"]["name"] == ""


def test_percent():
    assert inv._percent(30) == "30 %"
    assert inv._percent(12.5) == "12,5 %"
    assert inv._percent(33.333) == "33,33 %"


def test_escape():
    assert inv._escape("A & <B>\nC") == "A &amp; &lt;B&gt;<br/>C"
    assert inv._escape(None) == ""


def test_invoice_filename_y_ruta():
    invoice = _invoice(number="FAC/0001", client_name='Cliente: "X"')
    assert inv.invoice_filename(invoice) == "Factura FAC-0001 - Cliente- -X-.pdf"
    path = inv.invoice_path(invoice, "C:/Facturas")
    assert path == Path("C:/Facturas") / "2026" / "Factura FAC-0001 - Cliente- -X-.pdf"
    assert inv.invoice_path(invoice).parent.parent == inv.default_invoice_folder()


# ============================================================
# PDF
# ============================================================

def test_render_invoice_pdf(tmp_path):
    company = {
        "company_name": "Empresa de Prueba S.L.",
        "company_tax_id": "B00000000",
        "company_address": "Calle Falsa 1",
        "company_city": "08000 Barcelona",
        "company_iban": "ES00 0000 0000 0000 0000 0000",
        "company_registry": "Registro de prueba",
    }
    invoice = _invoice()
    invoice["company"] = company
    invoice["footer"] = "Gracias & <saludos>"

    path = inv.render_invoice_pdf(invoice, tmp_path / "sub" / "factura.pdf")

    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")


def test_render_invoice_pdf_sin_logo(tmp_path):
    path = inv.render_invoice_pdf(_invoice(), tmp_path / "f.pdf", logo=tmp_path / "no.png")
    assert path.read_bytes().startswith(b"%PDF")


def test_build_invoice_redondeo_comercial_del_iva():
    collection = SimpleNamespace(amount=0.5, concept="X", percentage=None)
    invoice = inv.build_invoice(
        collection, None, None, {}, number="1", invoice_date=date(2026, 1, 1),
        due_date=None, vat_rate=21,
    )
    assert (invoice["base"], invoice["vat"], invoice["total"]) == (0.5, 0.11, 0.61)


# ============================================================
# FACTURAS EMITIDAS
# ============================================================

def test_is_invoiced():
    def c(number, status="Facturado", pdf=None):
        return SimpleNamespace(invoice_number=number, status=status, invoice_file=pdf)

    for status in ("Facturado", "Cobrado", "Cancelado"):
        assert inv.is_invoiced(c("0001", status))
    assert inv.is_invoiced(c("0001", "Previsto", pdf="f.pdf"))
    # Número escrito a mano en un cobro previsto: aún no es una factura.
    assert not inv.is_invoiced(c("0001", "Previsto"))
    assert not inv.is_invoiced(c("  "))
    assert not inv.is_invoiced(c(None))


def test_invoiced_numbers_por_cobro_pedido_y_proyecto(session):
    a = _add_collection(session, "0002")
    b = _add_collection(session, None)
    _add_collection(session, "0001")
    draft = _add_collection(session, "0003", status="Previsto")

    assert inv.invoiced_numbers(session) == ["0001", "0002"]
    assert inv.invoiced_numbers(session, collection_id=draft.id) == []
    assert inv.invoiced_numbers(session, collection_id=a.id) == ["0002"]
    assert inv.invoiced_numbers(session, collection_id=b.id) == []
    assert inv.invoiced_numbers(session, order_id=a.order_id) == ["0002"]
    assert inv.invoiced_numbers(session, project_id=a.order.project_id) == ["0002"]
    assert inv.invoiced_numbers(session, project_id=b.order.project_id) == []


def test_logo_y_sello_de_configuracion(tmp_path, session):
    from PIL import Image

    settings = inv.get_invoice_settings(session)
    assert settings["company_logo"] == settings["invoice_stamp"] == ""

    image = tmp_path / "sello.png"
    Image.new("RGB", (290, 141), "white").save(image)
    collection = SimpleNamespace(amount=1000.0, concept="Hito", percentage=None)
    images = {}
    for name, logo, stamp in (("nada", "", ""), ("logo", image, ""), ("ambos", image, image)):
        invoice = inv.build_invoice(
            collection, None, None, {"company_name": "Empresa"},
            number=name, invoice_date=date(2026, 10, 19), due_date=None,
            vat_rate=21, logo=str(logo), stamp=str(stamp),
        )
        pdf = inv.render_invoice_pdf(invoice, tmp_path / f"{name}.pdf")
        images[name] = pdf.read_bytes().count(b"/Subtype /Image")
    assert images["nada"] == 0
    assert images["logo"] == 1
    assert images["ambos"] >= 1  # reportlab reutiliza la misma imagen


def test_store_image_sustituye_la_anterior(tmp_path):
    from PIL import Image

    from database.database import DATA_DIR

    first = tmp_path / "a.png"
    second = tmp_path / "b.jpg"
    Image.new("RGB", (10, 10)).save(first)
    Image.new("RGB", (10, 10)).save(second)
    inv.store_image(first, "company_logo")
    stored = inv.store_image(second, "company_logo")
    assert stored == DATA_DIR / "imagenes" / "company_logo.jpg"
    assert [f.name for f in (DATA_DIR / "imagenes").glob("company_logo.*")] == ["company_logo.jpg"]
