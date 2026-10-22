"""
Generación de facturas en PDF a partir de un cobro.

* Los datos fiscales de la empresa y la numeración se guardan en
  Configuración (tabla app_settings).
* Los datos fiscales del cliente se guardan en el proyecto.
* El importe del cobro es la BASE IMPONIBLE; la factura suma el IVA.

Requiere `reportlab` (pip install reportlab).
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

from services.cashflow import add_money, add_months, date_text, money, round_money


# ============================================================
# CONFIGURACIÓN
# ============================================================

COMPANY_FIELDS = [
    ("company_name", "Razón social", ""),
    ("company_tax_id", "CIF", ""),
    ("company_address", "Dirección", ""),
    ("company_city", "CP y población", ""),
    ("company_email", "Email", ""),
    ("company_phone", "Teléfono", ""),
    ("company_iban", "IBAN para cobros", ""),
    ("company_registry", "Datos registrales (opcional)", ""),
]

INVOICE_FIELDS = [
    ("invoice_prefix", "Prefijo de numeración", ""),
    ("invoice_digits", "Dígitos del número", "4"),
    ("invoice_next_number", "Siguiente número", ""),
    ("invoice_payment_days", "Vencimiento por defecto (días)", "30"),
    ("invoice_folder", "Carpeta de facturas", ""),
    ("invoice_footer", "Texto al pie (opcional)", ""),
    # Imágenes elegidas en Configuración (ruta de la copia guardada en la
    # carpeta de datos). Vacío = sin logo / sin sello.
    ("company_logo", "Logo de la empresa", ""),
    ("invoice_stamp", "Sello en las facturas", ""),
]


def _settings_dict(session, fields):
    from services.cashflow import get_setting
    return {key: get_setting(session, key, default) for key, _, default in fields}


def get_company(session) -> dict:
    return _settings_dict(session, COMPANY_FIELDS)


def get_invoice_settings(session) -> dict:
    return _settings_dict(session, INVOICE_FIELDS)


def save_settings(session, values: dict):
    from database.models import AppSetting
    for key, value in values.items():
        setting = session.get(AppSetting, key)
        if setting is None:
            session.add(AppSetting(key=key, value=str(value)))
        else:
            setting.value = str(value)


def missing_company_fields(company: dict) -> list[str]:
    required = ("company_name", "company_tax_id", "company_address", "company_city")
    labels = {key: label for key, label, _ in COMPANY_FIELDS}
    return [labels[key] for key in required if not (company.get(key) or "").strip()]


def default_invoice_folder() -> Path:
    return Path.home() / "Documents" / "Control de Caja" / "Facturas"


def store_image(source: str | Path, name: str) -> Path:
    """Copia una imagen elegida por el usuario a la carpeta de datos."""
    import shutil

    from database.database import DATA_DIR

    source = Path(source)
    folder = DATA_DIR / "imagenes"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{name}.*"):
        old.unlink()
    target = folder / f"{name}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    return target


# ============================================================
# NUMERACIÓN
# ============================================================

def _trailing_number(text: str | None):
    match = re.search(r"(\d+)\s*$", text or "")
    return int(match.group(1)) if match else None


def format_number(prefix: str, digits: int, number: int, year: int) -> str:
    prefix = (prefix or "").replace("{año}", str(year)).replace("{year}", str(year))
    return f"{prefix}{str(number).zfill(max(1, digits))}"


def suggest_invoice_number(session, invoice_date: date | None = None) -> str:
    """
    Siguiente número correlativo. Si no se ha configurado, continúa a
    partir del número más alto ya registrado en los cobros.
    """
    from database.models import Collection

    invoice_date = invoice_date or date.today()
    settings = get_invoice_settings(session)
    try:
        digits = int(settings["invoice_digits"] or 4)
    except ValueError:
        digits = 4

    try:
        next_number = int(settings["invoice_next_number"])
    except (TypeError, ValueError):
        existing = [
            _trailing_number(number)
            for (number,) in session.query(Collection.invoice_number).all()
        ]
        existing = [n for n in existing if n is not None]
        next_number = (max(existing) + 1) if existing else 1

    return format_number(settings["invoice_prefix"], digits, next_number, invoice_date.year)


def invoice_number_in_use(session, number: str, exclude_collection_id=None) -> bool:
    from database.models import Collection
    query = session.query(Collection).filter(Collection.invoice_number == number)
    if exclude_collection_id is not None:
        query = query.filter(Collection.id != exclude_collection_id)
    return query.first() is not None


def is_invoiced(collection) -> bool:
    """
    El cobro tiene una factura emitida: número y, además, el PDF generado
    por la aplicación o un estado posterior a "Previsto" (Facturado,
    Cobrado, o Cancelado tras facturar). Un número escrito a mano en un
    cobro previsto todavía no es una factura enviada.
    """
    if not (getattr(collection, "invoice_number", None) or "").strip():
        return False
    return bool(getattr(collection, "invoice_file", None)) or (
        (getattr(collection, "status", None) or "Previsto") != "Previsto"
    )


def invoiced_numbers(session, *, collection_id=None, order_id=None, project_id=None) -> list[str]:
    """
    Números de factura emitidos para un cobro, un pedido o un proyecto.
    Se usa para impedir borrados que harían desaparecer facturas.
    """
    from sqlalchemy import or_

    from database.models import Collection, Order

    # Misma regla que is_invoiced().
    query = (
        session.query(Collection.invoice_number)
        .join(Order, Collection.order_id == Order.id)
        .filter(Collection.invoice_number.isnot(None), Collection.invoice_number != "")
        .filter(or_(
            (Collection.invoice_file.isnot(None)) & (Collection.invoice_file != ""),
            Collection.status != "Previsto",
        ))
    )
    if collection_id is not None:
        query = query.filter(Collection.id == collection_id)
    if order_id is not None:
        query = query.filter(Collection.order_id == order_id)
    if project_id is not None:
        query = query.filter(Order.project_id == project_id)
    return [number for (number,) in query.order_by(Collection.invoice_number).all()]


def register_used_number(session, number: str):
    """Avanza el contador si el número usado es igual o mayor que el siguiente."""
    used = _trailing_number(number)
    if used is None:
        return
    settings = get_invoice_settings(session)
    try:
        current_next = int(settings["invoice_next_number"])
    except (TypeError, ValueError):
        current_next = 0
    if used + 1 > current_next:
        save_settings(session, {"invoice_next_number": used + 1})


# ============================================================
# DATOS DE LA FACTURA
# ============================================================

def default_due_date(collection, invoice_date: date, payment_days: int = 30) -> date:
    expected = getattr(collection, "expected_date", None)
    if expected and expected >= invoice_date:
        return expected
    if payment_days % 30 == 0:
        return add_months(invoice_date, payment_days // 30)
    from datetime import timedelta
    return invoice_date + timedelta(days=payment_days)


def build_invoice(collection, order, project, company: dict, *, number: str,
                  invoice_date: date, due_date: date | None, vat_rate: float,
                  client_tax_id: str = "", client_address: str = "",
                  client_name: str = "",
                  footer: str = "",
                  logo: str = "",
                  stamp: str = "") -> dict:
    base = round_money(collection.amount or 0.0)
    vat = round_money(base * vat_rate / 100.0)

    description = collection.concept or "Servicios"
    details = []
    if order is not None:
        order_number = str(order.order_number or "")
        order_text = (
            order_number
            if order_number.lower().startswith("pedido")
            else f"Pedido {order_number}"
        )
        if order.description:
            order_text += f" · {order.description}"
        details.append(order_text)
        if collection.percentage and (order.amount or 0):
            details.append(
                f"{_percent(collection.percentage)} s/ importe del pedido "
                f"({money(order.amount)})"
            )
    if project is not None:
        project_text = f"Proyecto: {project.name}"
        if project.reference:
            project_text += f" (ref. {project.reference})"
        details.append(project_text)

    return {
        "number": number,
        "date": invoice_date,
        "due_date": due_date,
        "company": company,
        "client": {
            "name": client_name or (project.client if project is not None else ""),
            "tax_id": client_tax_id or "",
            "address": client_address or "",
        },
        "lines": [{
            "description": description,
            "details": details,
            "amount": base,
        }],
        "base": base,
        "vat_rate": vat_rate,
        "vat": vat,
        "total": round_money(add_money(base, vat)),
        "footer": footer or "",
        "logo": logo or "",
        "stamp": stamp or "",
    }


def invoice_filename(invoice: dict) -> str:
    client = invoice["client"]["name"] or "cliente"
    raw = f"Factura {invoice['number']} - {client}"
    safe = re.sub(r'[<>:"/\\|?*]+', "-", raw).strip(" .")
    return f"{safe}.pdf"


def invoice_path(invoice: dict, folder: str | Path | None = None) -> Path:
    base = Path(folder) if folder else default_invoice_folder()
    return base / str(invoice["date"].year) / invoice_filename(invoice)


# ============================================================
# PDF
# ============================================================

def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative


def _escape(text) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _percent(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") + " %"


def _scaled_image(path: Path, max_width: float, max_height: float):
    """Imagen de reportlab que cabe en el recuadro sin deformarse."""
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image

    width, height = ImageReader(str(path)).getSize()
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def render_invoice_pdf(invoice: dict, path: str | Path, logo: str | Path | None = None) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    RED = colors.HexColor("#D71920")
    INK = colors.HexColor("#202024")
    MUTED = colors.HexColor("#71717A")
    LINE = colors.HexColor("#E4E4E7")
    SOFT = colors.HexColor("#F4F4F5")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    company = invoice["company"]
    client = invoice["client"]

    def style(name, **kw):
        base = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
        base.update(kw)
        return ParagraphStyle(name, **base)

    s_label = style("label", fontName="Helvetica-Bold", fontSize=7.5, textColor=MUTED, leading=10)
    s_label_right = style("labelr", fontName="Helvetica-Bold", fontSize=7.5,
                          textColor=MUTED, leading=10, alignment=TA_RIGHT)
    s_text = style("text")
    s_bold = style("bold", fontName="Helvetica-Bold")
    s_small = style("small", fontSize=8, textColor=MUTED, leading=10.5)
    s_title = style("title", fontName="Helvetica-Bold", fontSize=22, leading=26,
                    textColor=INK, alignment=TA_RIGHT)
    s_right = style("right", alignment=TA_RIGHT)
    s_right_bold = style("rightbold", fontName="Helvetica-Bold", alignment=TA_RIGHT)
    s_total = style("total", fontName="Helvetica-Bold", fontSize=12, leading=15,
                    alignment=TA_RIGHT, textColor=colors.white)
    s_total_label = style("totallabel", fontName="Helvetica-Bold", fontSize=10,
                          leading=15, textColor=colors.white)

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"Factura {invoice['number']}",
        author=company.get("company_name", ""),
    )
    width = A4[0] - 36 * mm
    story = []

    # ---------- Cabecera ----------
    logo_path = Path(logo or invoice.get("logo") or "")
    if logo_path.is_file():
        logo_flow = _scaled_image(logo_path, 30 * mm, 30 * mm)
        logo_flow.hAlign = "LEFT"
    else:
        logo_flow = Paragraph(_escape(company.get("company_name")), s_bold)

    meta = Table(
        [
            [Paragraph("FACTURA", s_title)],
            [Spacer(1, 3 * mm)],
            [Table(
                [
                    [Paragraph("Nº factura", s_label), Paragraph(_escape(invoice["number"]), s_right_bold)],
                    [Paragraph("Fecha", s_label), Paragraph(date_text(invoice["date"]), s_right)],
                    [Paragraph("Vencimiento", s_label), Paragraph(date_text(invoice["due_date"]), s_right)],
                ],
                colWidths=[28 * mm, 40 * mm],
                style=TableStyle([
                    ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]),
                hAlign="RIGHT",
            )],
        ],
        colWidths=[70 * mm],
        style=TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    header = Table([[logo_flow, meta]], colWidths=[width - 70 * mm, 70 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [header, Spacer(1, 6 * mm)]

    # ---------- Emisor / Cliente ----------
    def party(title, lines):
        content = [Paragraph(title, s_label), Spacer(1, 1.5 * mm)]
        first = True
        for line in lines:
            if line:
                content.append(Paragraph(_escape(line), s_bold if first else s_text))
                first = False
        return content

    issuer = party("EMISOR", [
        company.get("company_name"),
        f"CIF: {company['company_tax_id']}" if company.get("company_tax_id") else "",
        company.get("company_address"),
        company.get("company_city"),
        " · ".join(x for x in (company.get("company_email"), company.get("company_phone")) if x),
    ])
    customer = party("CLIENTE", [
        client.get("name"),
        f"CIF/NIF: {client['tax_id']}" if client.get("tax_id") else "",
        client.get("address"),
    ])
    parties = Table([[issuer, customer]], colWidths=[width / 2 - 3 * mm, width / 2 + 3 * mm])
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, 0), SOFT),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEABOVE", (0, 0), (-1, 0), 2, RED),
    ]))
    story += [parties, Spacer(1, 8 * mm)]

    # ---------- Conceptos ----------
    rows = [[Paragraph("CONCEPTO", s_label), Paragraph("BASE IMPONIBLE", s_label_right)]]
    for line in invoice["lines"]:
        desc = [Paragraph(_escape(line["description"]), s_bold)]
        for detail in line.get("details", []):
            desc.append(Paragraph(_escape(detail), s_small))
        rows.append([desc, Paragraph(money(line["amount"]), s_right)])
    lines_table = Table(rows, colWidths=[width - 40 * mm, 40 * mm])
    lines_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [lines_table, Spacer(1, 6 * mm)]

    # ---------- Totales ----------
    totals = Table(
        [
            [Paragraph("Base imponible", s_text), Paragraph(money(invoice["base"]), s_right)],
            [Paragraph(f"IVA {_percent(invoice['vat_rate'])}", s_text), Paragraph(money(invoice["vat"]), s_right)],
            [Paragraph("TOTAL FACTURA", s_total_label), Paragraph(money(invoice["total"]), s_total)],
        ],
        colWidths=[38 * mm, 34 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINE),
        ("BACKGROUND", (0, 2), (-1, 2), INK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    # Sello del seguro de crédito a la izquierda de los totales.
    stamp_path = Path(invoice.get("stamp") or "")
    if stamp_path.is_file():
        stamp = _scaled_image(stamp_path, 46 * mm, 30 * mm)
        stamp.hAlign = "LEFT"
        totals.hAlign = "RIGHT"
        totals = Table([[stamp, totals]], colWidths=[width - 72 * mm, 72 * mm])
        totals.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    story += [totals, Spacer(1, 10 * mm)]

    # ---------- Forma de pago ----------
    payment = []
    if company.get("company_iban"):
        payment.append(Paragraph("FORMA DE PAGO", s_label))
        payment.append(Spacer(1, 1.5 * mm))
        payment.append(Paragraph(
            f"Transferencia bancaria a <b>{_escape(company['company_iban'])}</b>"
            + (f" antes del {date_text(invoice['due_date'])}" if invoice.get("due_date") else ""),
            s_text,
        ))
        payment.append(Paragraph(f"Indique el nº de factura {_escape(invoice['number'])} en el concepto.", s_small))
    if invoice.get("footer"):
        payment.append(Spacer(1, 4 * mm))
        payment.append(Paragraph(_escape(invoice["footer"]), s_small))
    story += payment

    registry = company.get("company_registry") or ""

    def on_page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        left = company.get("company_name", "")
        if company.get("company_tax_id"):
            left += f" · CIF {company['company_tax_id']}"
        if registry:
            left += f" · {registry}"
        canvas.drawString(18 * mm, 9 * mm, left[:150])
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Factura {invoice['number']} · Pág. {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return path
