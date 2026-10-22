"""
Ventana "Generar factura" y flujo completo de facturación de un cobro.

Uso desde cualquier página:

    from ui.pages.dialogs.invoice_dialog import generate_invoice
    if generate_invoice(self, collection_id):
        self.refresh()
"""

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from database.database import get_session
from database.models import Collection
from services import clients, invoices
from services.clients import client_for_project
from services.cashflow import DEFAULT_VAT_RATE, add_money, money, round_money


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


class InvoiceDialog(QDialog):

    def __init__(self, parent, collection, order, project, client, number,
                 payment_days=30):
        super().__init__(parent)
        self.collection = collection
        self.base = collection.amount or 0.0

        # Si ya está facturado solo se regenera el PDF: número, fecha e IVA
        # forman parte de la factura emitida y no se pueden cambiar.
        self.regenerating = invoices.is_invoiced(collection)

        self.setWindowTitle("Regenerar factura" if self.regenerating else "Generar factura")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        summary = QLabel(
            f"<b>{client.invoice_name}</b> · {project.name}<br>"
            f"{collection.concept} · pedido {order.order_number}"
        )
        summary.setObjectName("pageSubtitle")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        form = QFormLayout()
        form.setSpacing(10)

        self.number = QLineEdit(number)

        invoice_date = collection.invoice_date or date.today()
        self.invoice_date = QDateEdit(_qdate(invoice_date))
        self.invoice_date.setCalendarPopup(True)
        self.invoice_date.setDisplayFormat("dd/MM/yyyy")

        due = invoices.default_due_date(collection, invoice_date, payment_days)
        self.due_date = QDateEdit(_qdate(due))
        self.due_date.setCalendarPopup(True)
        self.due_date.setDisplayFormat("dd/MM/yyyy")

        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0.0, 100.0)
        self.vat_rate.setDecimals(2)
        self.vat_rate.setSuffix(" %")
        self.vat_rate.setValue(
            DEFAULT_VAT_RATE if collection.vat_rate is None else collection.vat_rate
        )
        self.vat_rate.valueChanged.connect(self.update_totals)

        self.base_label = QLabel(money(self.base))
        self.vat_label = QLabel()
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-weight: 700;")

        self.client_tax_id = QLineEdit(client.tax_id or "")
        self.client_tax_id.setPlaceholderText("CIF del cliente")
        self.client_address = QLineEdit(client.address or "")
        self.client_address.setPlaceholderText("Calle, número, polígono…")
        self.client_city = QLineEdit(client.city or "")
        self.client_city.setPlaceholderText("CP y población")

        if self.regenerating:
            self.number.setReadOnly(True)
            self.invoice_date.setEnabled(False)
            self.vat_rate.setEnabled(False)

        form.addRow("Nº factura", self.number)
        form.addRow("Fecha factura", self.invoice_date)
        form.addRow("Vencimiento", self.due_date)
        form.addRow("Base imponible", self.base_label)
        form.addRow("IVA", self.vat_rate)
        form.addRow("Cuota IVA", self.vat_label)
        form.addRow("Total factura", self.total_label)
        form.addRow("CIF cliente", self.client_tax_id)
        form.addRow("Dirección cliente", self.client_address)
        form.addRow("CP y población", self.client_city)
        layout.addLayout(form)

        hint = QLabel(
            "Los datos fiscales vienen de la ficha del cliente; si los "
            "cambias aquí, se actualiza la ficha para las próximas facturas. El cobro pasará a 'Facturado' y su fecha "
            "prevista de cobro será la de vencimiento."
        )
        hint.setObjectName("cardDescription")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        generate = QPushButton("Generar PDF")
        generate.setObjectName("primaryButton")
        generate.setCursor(Qt.PointingHandCursor)
        generate.setDefault(True)
        buttons.addButton(generate, QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.update_totals()

    def update_totals(self):
        vat = round_money(self.base * self.vat_rate.value() / 100.0)
        self.vat_label.setText(money(vat))
        self.total_label.setText(money(add_money(self.base, vat)))

    def validate(self):
        if not self.number.text().strip():
            QMessageBox.warning(self, "Número obligatorio",
                                "Introduce el número de factura.")
            return
        if not self.client_tax_id.text().strip():
            answer = QMessageBox.question(
                self,
                "Falta el CIF del cliente",
                "Una factura completa debe incluir el CIF del cliente.\n\n"
                "¿Generarla igualmente?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if self.due_date.date() < self.invoice_date.date():
            QMessageBox.warning(self, "Fechas incorrectas",
                                "El vencimiento no puede ser anterior a la fecha de factura.")
            return
        self.accept()

    def get_data(self):
        return {
            "number": self.number.text().strip(),
            "invoice_date": self.invoice_date.date().toPython(),
            "due_date": self.due_date.date().toPython(),
            "vat_rate": self.vat_rate.value(),
            "client_tax_id": self.client_tax_id.text().strip(),
            "client_address": self.client_address.text().strip(),
            "client_city": self.client_city.text().strip(),
        }


def open_file(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def block_if_invoiced(parent, what, **filters) -> bool:
    """
    Si hay facturas emitidas (para un cobro, pedido o proyecto), avisa y
    devuelve True para que no se borre: la factura desaparecería.
    """
    session = get_session()
    try:
        numbers = invoices.invoiced_numbers(session, **filters)
    finally:
        session.close()
    if not numbers:
        return False
    QMessageBox.warning(
        parent,
        "Tiene facturas emitidas",
        f"No se puede eliminar {what} porque tiene facturas emitidas:\n\n"
        + ", ".join(numbers)
        + "\n\nSi una factura no es válida, marca el cobro como «Cancelado» "
        "y pide a la gestoría la factura rectificativa.",
    )
    return True


def generate_invoice(parent, collection_id) -> bool:
    """
    Flujo completo: comprobaciones, ventana, PDF y guardado.
    Devuelve True si se ha generado una factura (para refrescar la vista).
    """
    session = get_session()
    pdf_path = None
    try:
        collection = session.get(Collection, collection_id)
        if collection is None:
            return False
        order = collection.order
        project = order.project
        client = client_for_project(session, project)
        if client is None:
            QMessageBox.warning(parent, "Proyecto sin cliente",
                                "Asigna primero un cliente al proyecto.")
            return False

        if collection.status == "Cancelado":
            QMessageBox.warning(parent, "Cobro cancelado",
                                "No se puede facturar un cobro cancelado.")
            return False

        company = invoices.get_company(session)
        missing = invoices.missing_company_fields(company)
        if missing:
            QMessageBox.warning(
                parent,
                "Faltan datos de la empresa",
                "Antes de facturar, completa en Configuración:\n\n• "
                + "\n• ".join(missing),
            )
            return False

        # Ya facturado: abrir o regenerar. (Un número escrito a mano en un
        # cobro previsto se usa como número de la factura nueva.)
        if invoices.is_invoiced(collection):
            box = QMessageBox(parent)
            box.setWindowTitle("Cobro ya facturado")
            box.setText(
                f"Este cobro ya tiene la factura {collection.invoice_number}."
            )
            box.setInformativeText(
                "Regenerar crea de nuevo el PDF con el mismo número, "
                "fecha, importe e IVA."
            )
            open_button = None
            if collection.invoice_file and Path(collection.invoice_file).exists():
                open_button = box.addButton("Abrir PDF", QMessageBox.AcceptRole)
            regen_button = box.addButton("Regenerar PDF", QMessageBox.ActionRole)
            box.addButton("Cancelar", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if open_button is not None and clicked == open_button:
                open_file(collection.invoice_file)
                return False
            if clicked != regen_button:
                return False

        settings = invoices.get_invoice_settings(session)
        try:
            payment_days = int(settings["invoice_payment_days"] or 30)
        except ValueError:
            payment_days = 30
        if client.payment_days:
            payment_days = client.payment_days

        number = collection.invoice_number or invoices.suggest_invoice_number(session)
        dialog = InvoiceDialog(parent, collection, order, project, client, number, payment_days)
        if dialog.exec() != QDialog.Accepted:
            return False
        data = dialog.get_data()

        if invoices.invoice_number_in_use(session, data["number"], collection.id):
            QMessageBox.warning(
                parent,
                "Número duplicado",
                f"Ya existe otro cobro con la factura {data['number']}.\n"
                "Los números de factura deben ser únicos y correlativos.",
            )
            return False

        # Guardar en la ficha del cliente los datos usados.
        client.tax_id = data["client_tax_id"].upper() or None
        client.address = data["client_address"] or None
        client.city = data["client_city"] or None

        invoice = invoices.build_invoice(
            collection, order, project, company,
            number=data["number"],
            invoice_date=data["invoice_date"],
            due_date=data["due_date"],
            vat_rate=data["vat_rate"],
            client_tax_id=data["client_tax_id"],
            client_address=clients.invoice_address(client),
            client_name=client.invoice_name,
            footer=settings["invoice_footer"],
            logo=settings["company_logo"],
            stamp=settings["invoice_stamp"],
        )
        pdf_path = invoices.invoice_path(invoice, settings["invoice_folder"] or None)

        # Primero el PDF: si falla, no se consume el número.
        invoices.render_invoice_pdf(invoice, pdf_path)

        collection.invoice_number = data["number"]
        collection.invoice_date = data["invoice_date"]
        collection.vat_rate = data["vat_rate"]
        collection.invoice_file = str(pdf_path)
        if collection.status == "Previsto":
            collection.status = "Facturado"
        if collection.status != "Cobrado":
            collection.expected_date = data["due_date"]


        invoices.register_used_number(session, data["number"])
        session.commit()

    except ImportError as error:
        session.rollback()
        import sys
        if getattr(sys, "frozen", False):
            how = (
                "Estás usando el .exe: instala reportlab en tu Python y "
                "vuelve a generar el ejecutable con PyInstaller."
            )
        else:
            how = (
                "Instálala en ESTE Python con:\n\n"
                f'"{sys.executable}" -m pip install reportlab'
            )
        QMessageBox.critical(
            parent,
            "Falta un componente",
            "Para generar PDF hace falta la librería 'reportlab'.\n\n"
            f"{how}\n\nDetalle: {error}",
        )
        return False
    except PermissionError:
        session.rollback()
        QMessageBox.critical(
            parent,
            "No se puede guardar",
            f"No se puede escribir el PDF:\n{pdf_path}\n\n"
            "¿Está abierto en otro programa? Ciérralo y vuelve a intentarlo.",
        )
        return False
    except Exception as error:
        session.rollback()
        QMessageBox.critical(parent, "Error",
                             f"No se ha podido generar la factura.\n\n{error}")
        return False
    finally:
        session.close()

    open_file(pdf_path)
    return True
