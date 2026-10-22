"""
Prueba de humo de la interfaz: abre la ventana principal (sin mostrarla,
QT_QPA_PLATFORM=offscreen) sobre una base temporal con datos de ejemplo
y recorre todas las páginas. Detecta errores de importación y de carga.
"""

from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from database.database import create_database, get_session  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def project_id(app):
    from database.models import Collection, Expense, Loan, Order, Project

    create_database()
    session = get_session()
    try:
        project = Project(name="Obra demo", client="Acme", start_date=date(2026, 1, 1))
        session.add(project)
        session.flush()
        order = Order(project_id=project.id, order_number="P-1", amount=10000)
        session.add(order)
        session.flush()
        session.add_all([
            Collection(order_id=order.id, concept="Anticipo", percentage=30, amount=3000,
                       status="Cobrado", expected_date=date(2026, 2, 1),
                       collection_date=date(2026, 2, 3), invoice_number="0001"),
            Collection(order_id=order.id, concept="Final", amount=7000,
                       expected_date=date(2026, 12, 1)),
            Expense(project_id=project.id, category="Hotel", concept="Hotel", status="Pagado",
                    payment_date=date(2026, 3, 1), base_amount=100, vat_amount=21,
                    total_amount=121),
            Expense(project_id=project.id, category="Otros", concept="Alquiler grúa",
                    payment_type="Mensual", recurrence_start=date(2026, 1, 1),
                    base_amount=500, vat_amount=105, total_amount=605),
            Expense(project_id=None, category="Oficina", concept="Alquiler oficina",
                    payment_type="Mensual", recurrence_start=date(2026, 1, 1),
                    status="Activo", base_amount=800, vat_amount=168, total_amount=968),
            Loan(name="ICO", principal=20000, received_date=date(2026, 1, 1),
                 term_months=24, monthly_payment=900, first_payment_date=date(2026, 2, 1)),
        ])
        session.commit()
        return project.id
    finally:
        session.close()


def test_main_window_recorre_todas_las_paginas(app, project_id):
    from ui.main_window import MainWindow

    window = MainWindow()
    try:
        window.resize(1500, 900)
        window.show()  # plataforma offscreen: no aparece en pantalla
        for index in range(window.pages.count()):
            window.change_page(index)
            assert window.pages.currentIndex() == index
            # Pinta la página, gráficas incluidas. Un error en paintEvent
            # termina el proceso, así que la ejecución de pytest fallaría.
            app.processEvents()
            assert not window.grab().isNull()

        window.open_project(project_id)
        assert window.pages.currentWidget() is window.project_detail_page
        page = window.project_detail_page
        assert page.orders_table.rowCount() == 1
        assert page.collections_table.rowCount() == 2
        assert page.expenses_table.rowCount() == 2
        for tab in range(page.tabs.count()):
            page.tabs.setCurrentIndex(tab)
            app.processEvents()
            assert not window.grab().isNull()

        assert window.collections_page.table.rowCount() == 2
        assert window.payments_page.table.rowCount() == 2
        assert window.orders_page.table.rowCount() == 1
    finally:
        window.close()
        window.deleteLater()


def test_formulario_de_cobro_rechaza_numero_de_factura_repetido(app, project_id, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from database.models import Collection, Order
    from ui.pages.dialogs.collection_dialog import CollectionDialog

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1]))

    session = get_session()
    try:
        orders = session.query(Order).filter(Order.project_id == project_id).all()
        existing = session.query(Collection).filter(Collection.invoice_number == "0001").one()

        dialog = CollectionDialog(orders=orders)
        dialog.calculation_type.setCurrentText("Importe fijo")
        dialog.concept.setText("Otro hito")
        dialog.amount.setValue(100)
        dialog.invoice_number.setText("0001")
        dialog.validate()
        assert warnings == ["Número de factura repetido"]
        assert dialog.result() != dialog.DialogCode.Accepted

        # Al editar el propio cobro, su número no cuenta como repetido.
        dialog = CollectionDialog(orders=orders, collection=existing)
        dialog.validate()
        assert warnings == ["Número de factura repetido"]
    finally:
        session.close()


# ============================================================
# FACTURAS EMITIDAS
# ============================================================

def _invoiced_collection(session):
    from database.models import Collection
    return session.query(Collection).filter(Collection.invoice_number == "0001").one()


def test_formulario_bloquea_un_cobro_facturado(app, project_id):
    from types import SimpleNamespace

    from ui.pages.dialogs.collection_dialog import CollectionDialog

    session = get_session()
    try:
        collection = _invoiced_collection(session)
        # El pedido ha cambiado de importe después de facturar: el cobro
        # (30 %) NO debe recalcularse.
        order = SimpleNamespace(id=collection.order_id, order_number="P-1", amount=20000)
        dialog = CollectionDialog(orders=[order], collection=collection)

        assert dialog.amount.value() == 3000
        for widget in (dialog.order_combo, dialog.concept, dialog.calculation_type,
                       dialog.percentage, dialog.amount, dialog.invoice_number,
                       dialog.invoice_date):
            assert not widget.isEnabled()
        assert dialog.status.isEnabled() and dialog.notes.isEnabled()
        assert dialog.get_data()["amount"] == 3000
    finally:
        session.close()


def test_regenerar_factura_no_deja_cambiar_numero_fecha_ni_iva(app, project_id):
    from types import SimpleNamespace

    from ui.pages.dialogs.invoice_dialog import InvoiceDialog

    session = get_session()
    try:
        collection = _invoiced_collection(session)
        client = SimpleNamespace(invoice_name="Acme", tax_id="B1", address="", city="")
        dialog = InvoiceDialog(None, collection, collection.order, collection.order.project,
                               client, collection.invoice_number)
        assert dialog.number.isReadOnly()
        assert not dialog.invoice_date.isEnabled()
        assert not dialog.vat_rate.isEnabled()
    finally:
        session.close()


def test_no_se_borran_cobros_pedidos_ni_proyectos_facturados(app, project_id, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from ui.pages.dialogs.invoice_dialog import block_if_invoiced

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1]))

    session = get_session()
    try:
        collection = _invoiced_collection(session)
        assert block_if_invoiced(None, "este cobro", collection_id=collection.id)
        assert block_if_invoiced(None, "este pedido", order_id=collection.order_id)
        assert block_if_invoiced(None, "este proyecto", project_id=project_id)
        assert warnings == ["Tiene facturas emitidas"] * 3
        assert not block_if_invoiced(None, "este proyecto", project_id=-1)
    finally:
        session.close()


# ============================================================
# COPIA EXTERNA DESDE CONFIGURACIÓN
# ============================================================

def test_configuracion_copia_externa(app, project_id, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from database.database import EXTERNAL_BACKUP_KEY
    from services.cashflow import get_setting
    from ui.pages.configuracion import SettingsPage

    messages = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, lambda *args, k=kind: messages.append((k, args[1])))

    page = SettingsPage()
    assert page.external_status.text() == "Copia externa desactivada."

    page.external_folder.setText(str(tmp_path / "no existe"))
    assert "no existe" in page.external_status.text()
    page.copy_now()
    assert messages[-1] == ("critical", "Copia externa")

    page.external_folder.setText(str(tmp_path))
    assert page.external_status.text() == "Todavía no hay copias en esta carpeta."
    page.copy_now()
    assert messages[-1] == ("information", "Copia externa")
    assert len(list(tmp_path.glob("control_de_caja_*.db"))) == 1
    assert page.external_status.text().startswith("Última copia externa:")

    page.save()
    session = get_session()
    try:
        assert get_setting(session, EXTERNAL_BACKUP_KEY) == str(tmp_path)
    finally:
        session.close()
    page.refresh()
    assert page.external_folder.text() == str(tmp_path)


def test_grafica_muestra_el_importe_exacto_al_pasar_el_raton(app, project_id, monkeypatch):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QToolTip

    from services.cashflow import money
    from ui.pages.dashboard_charts import CashFlowChart

    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda pos, text, *args: shown.append(text))

    chart = CashFlowChart()
    chart.resize(600, 240)
    chart.set_data([
        {"label": "oct-26", "balance": 1000.0},
        {"label": "nov-26", "balance": 2500.55},
        {"label": "dic-26", "balance": -300.0},
    ])
    chart.grab()  # calcula la posición de los puntos

    x, y, _, _ = chart._points[1]
    event = QMouseEvent(QEvent.MouseMove, QPointF(x + 3, 20), QPointF(x + 3, 20),
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    chart.mouseMoveEvent(event)

    assert chart._hover == 1
    assert shown == [f"nov-26\nSaldo previsto: {money(2500.55)}"]
    chart.grab()  # dibuja la guía del ratón sin errores


# ============================================================
# LIQUIDACIONES DE IVA EN TESORERÍA
# ============================================================

def test_tesoreria_registrar_y_eliminar_liquidacion_de_iva(app, project_id, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from database.models import VatSettlement
    from ui.pages.dialogs import vat_dialog
    from ui.pages.tesoreria import TreasuryPage

    page = TreasuryPage()
    assert page.vat_rows, "con los datos de ejemplo hay trimestres con IVA"
    labels = [row["label"] for row in page.vat_rows]
    page.vat_table.setCurrentCell(labels.index("1T 2026"), 0)

    def accept(dialog):
        dialog.amount.setValue(123.45)
        dialog.notes.setPlainText("303 de la gestoría")
        return QDialog.Accepted

    monkeypatch.setattr(vat_dialog.VatSettlementDialog, "exec", accept)
    page.register_vat_settlement()

    session = get_session()
    try:
        record = session.query(VatSettlement).one()
        assert (record.year, record.quarter, record.amount) == (2026, 1, 123.45)
        assert record.notes == "303 de la gestoría"
    finally:
        session.close()

    row = page.vat_rows[labels.index("1T 2026")]
    assert row["registered"] and row["result"] == 123.45
    texts = [page.vat_table.item(labels.index("1T 2026"), c).text() for c in range(7)]
    assert texts[4] == "123,45 €" and texts[6] == "Pagado"

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    page.vat_table.setCurrentCell(labels.index("1T 2026"), 0)
    page.delete_vat_settlement()
    session = get_session()
    try:
        assert session.query(VatSettlement).count() == 0
    finally:
        session.close()


def test_dashboard_y_tesoreria_dan_el_mismo_saldo_con_iva_registrado(app, project_id):
    from datetime import date

    from database.models import VatSettlement
    from services import cashflow
    from ui.pages.dashboard import DashboardPage
    from ui.pages.dashboard_charts import HIDDEN_MONEY
    from ui.pages.tesoreria import TreasuryPage

    session = get_session()
    try:
        session.add(VatSettlement(year=2026, quarter=1, amount=99.99, payment_date=date(2026, 4, 1)))
        session.commit()
        _, summary = cashflow.load_cashflow(session)
    finally:
        session.close()

    try:
        dashboard = DashboardPage()
        assert dashboard.balance_value.text() == HIDDEN_MONEY
        dashboard.toggle_amounts()
        treasury = TreasuryPage()
        expected = cashflow.money(summary.real_balance)
        assert dashboard.balance_value.text() == expected
        assert treasury.current_balance_value.text() == expected
        assert dashboard.payments_value.text() == treasury.pending_payments_value.text()
    finally:
        session = get_session()
        session.query(VatSettlement).delete()
        session.commit()
        session.close()


def test_grafica_del_dashboard_no_pasa_del_horizonte(app, project_id):
    from services import cashflow
    from ui.pages.dashboard import DashboardPage

    page = DashboardPage()
    assert len(page.cashflow_chart.months) == cashflow.FORECAST_MONTHS


def test_gastos_generales_solo_suman_los_vigentes(app, project_id):
    from datetime import date

    from ui.pages.gastos_generales import GeneralExpensesPage

    status = GeneralExpensesPage.status_text
    today = date(2026, 10, 13)
    base = {"status": "Activo", "start": date(2026, 1, 1), "end": None}
    assert status(base, today) == "Activo"
    assert status({**base, "end": date(2026, 9, 30)}, today) == "Finalizado"
    assert status({**base, "end": date(2026, 10, 1)}, today) == "Activo"
    assert status({**base, "start": date(2026, 10, 31)}, today) == "Activo"
    assert status({**base, "start": date(2026, 11, 1)}, today) == "Desde 01/11/2026"
    assert status({**base, "status": "Inactivo"}, today) == "Inactivo"

    page = GeneralExpensesPage()
    page.expenses = [
        {"id": 1, "category": "Oficina", "concept": "Alquiler", "supplier": None,
         "base_amount": 800, "vat_rate": 21, "vat_amount": 168, "total_amount": 968,
         "status": "Activo", "start": date(2020, 1, 1), "end": None},
        {"id": 2, "category": "Oficina", "concept": "Antiguo", "supplier": None,
         "base_amount": 500, "vat_rate": 21, "vat_amount": 105, "total_amount": 605,
         "status": "Activo", "start": date(2020, 1, 1), "end": date(2021, 1, 1)},
    ]
    page.fill_table()
    assert page.total_monthly_value.text() == "968,00 €"
    assert page.table.item(1, 3).text() == "Finalizado"


def test_formularios_de_gasto_redondean_igual_que_las_facturas(app, project_id):
    from ui.pages.dialogs.expense_dialog import ExpenseDialog
    from ui.pages.gastos_generales import GeneralExpenseDialog

    dialog = ExpenseDialog()
    dialog.base_amount.setValue(0.5)
    dialog.vat_rate.setValue(21)
    dialog.calculate_totals()
    assert (dialog.vat_amount.value(), dialog.total_amount.value()) == (0.11, 0.61)

    general = GeneralExpenseDialog()
    general.concept.setText("X")
    general.base_amount.setValue(0.5)
    general.vat_rate.setValue(21)
    data = general.get_data()
    assert (data["vat_amount"], data["total_amount"]) == (0.11, 0.61)


def test_formulario_de_gasto_rellena_desde_ticket_y_archiva(app, project_id, tmp_path, monkeypatch):
    from database.models import AppSetting
    from services import receipts
    from ui.pages.dialogs.expense_dialog import ExpenseDialog

    session = get_session()
    try:
        session.merge(AppSetting(key=receipts.EXPENSE_FOLDER_KEY, value=str(tmp_path / "gastos")))
        session.commit()
    finally:
        session.close()

    ticket = tmp_path / "ticket.pdf"
    ticket.write_bytes(b"%PDF-1.4 demo")

    dialog = ExpenseDialog()
    assert not dialog.open_button.isVisibleTo(dialog)

    # Sin clave de API: se adjunta igual, pero no se lee.
    dialog.read_document(str(ticket))
    assert dialog.reader is None
    assert "falta la clave" in dialog.document_status.text()

    dialog.document_read(receipts.normalize({
        "is_expense_document": True, "supplier": "Repsol", "supplier_tax_id": "A0000000",
        "file_label": "Gasolina",
        "concept": "Gasoil", "category": "Combustible", "date": "2026-09-30",
        "invoice_reference": "T-77", "vat_lines": [{"rate": 21, "base": 50.0, "vat": 10.5}],
        "total": 60.0, "paid": True, "notes": "",
    }, ["Combustible", "Otros"]))

    assert dialog.category.currentText() == "Combustible"
    assert dialog.supplier.text() == "Repsol"
    assert dialog.status.currentText() == "Pagado"
    assert dialog.total_amount.value() == 60.5
    assert "Revisa base e IVA" in dialog.document_status.text()
    assert "NIF proveedor: A0000000" in dialog.notes.toPlainText()

    dialog.validate()
    data = dialog.get_data()
    assert data["expense_date"] == date(2026, 9, 30)
    assert data["payment_date"] == date(2026, 9, 30)
    assert data["document_file"] == str(
        tmp_path / "gastos" / "2026" / "09.SEPTIEMBRE" / "2026_09_30_Gasolina.pdf"
    )
    assert ticket.exists()


def test_formulario_de_gasto_cabe_en_la_pantalla(app, project_id):
    from ui.pages.dialogs.expense_dialog import ExpenseDialog

    dialog = ExpenseDialog()
    available = dialog.screen().availableGeometry().height()
    assert dialog.height() <= available - 50

    dialog.payment_type.setCurrentText("Mensual")
    assert dialog.form.isRowVisible(dialog.recurrence_row)
    assert not dialog.form.isRowVisible(dialog.expense_date)
    assert dialog.base_label.text() == "Base mensual *"

    dialog.payment_type.setCurrentText("Único")
    assert dialog.form.isRowVisible(dialog.expense_date)
    assert not dialog.form.isRowVisible(dialog.recurrence_row)


def test_foto_del_movil_se_escanea_a_pdf(app, project_id, tmp_path):
    from PIL import Image

    from ui.pages.dialogs.expense_dialog import ExpenseDialog

    photo = tmp_path / "movil.jpg"
    Image.new("RGB", (600, 800), (200, 200, 200)).save(photo)

    dialog = ExpenseDialog()
    dialog.read_scanned_photo(str(photo))
    assert dialog.pending_document == str(tmp_path / "movil.pdf")
    assert dialog.original_photo == str(photo)
    assert "Escaneado a PDF" in dialog.document_status.text()
    assert dialog.original_button.isVisibleTo(dialog)

    dialog.use_original_photo()
    assert dialog.pending_document == str(photo)
    assert not dialog.original_button.isVisibleTo(dialog)


def test_facturas_generales_sueltas_van_a_pagos(app, project_id):
    from database.models import Expense
    from ui.pages.dialogs.expense_dialog import ExpenseDialog
    from ui.pages.gastos_generales import GENERAL_CATEGORIES, GeneralExpensesPage
    from ui.pages.pagos import GENERAL, PaymentsPage

    session = get_session()
    try:
        invoice = Expense(project_id=None, category="Software / Licencias",
                          concept="Antivirus", supplier="Kaspersky", payment_type="Único",
                          expense_date=date(2026, 9, 2), status="Pagado",
                          payment_date=date(2026, 9, 2), base_amount=40, vat_amount=8.4,
                          total_amount=48.4)
        session.add(invoice)
        session.commit()
        invoice_id = invoice.id
    finally:
        session.close()

    try:
        general = GeneralExpensesPage()
        assert invoice_id not in [e["id"] for e in general.expenses]
        assert any(e["concept"] == "Alquiler oficina" for e in general.expenses)

        payments = PaymentsPage()
        row = next(r for r in payments.rows if r["id"] == invoice_id)
        assert (row["project"], row["months"]) == ("General", 1)
        assert all(r["concept"] != "Alquiler oficina" for r in payments.rows)

        payments.project_filter.setCurrentIndex(payments.project_filter.findData(GENERAL))
        assert [r["id"] for r in payments.rows] == [invoice_id]

        session = get_session()
        try:
            dialog = ExpenseDialog(expense=session.get(Expense, invoice_id))
        finally:
            session.close()
        assert dialog.general
        assert dialog.category.currentText() == "Software / Licencias"
        assert dialog.category.count() == len(GENERAL_CATEGORIES)
        assert dialog.payment_type.count() == 1
    finally:
        session = get_session()
        try:
            session.delete(session.get(Expense, invoice_id))
            session.commit()
        finally:
            session.close()


def test_formulario_ensena_el_nombre_definitivo_y_la_ficha_lo_enlaza(app, project_id, tmp_path, monkeypatch):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDialog

    from database.models import AppSetting, Expense
    from services import receipts
    from ui.pages.dialogs import expense_dialog
    from ui.pages.project_detail import ProjectDetailPage

    session = get_session()
    try:
        session.merge(AppSetting(key=receipts.EXPENSE_FOLDER_KEY, value=str(tmp_path / "FACTURAS")))
        session.commit()
    finally:
        session.close()

    photo_pdf = tmp_path / "movil 2026-10-19 164852376789.pdf"
    photo_pdf.write_bytes(b"%PDF-1.4 demo")

    dialog = expense_dialog.ExpenseDialog()
    dialog.read_document(str(photo_pdf))      # sin clave de API: no se lee
    dialog.file_label = "Uber"
    dialog.expense_date.setDate(QDate(2026, 10, 15))
    month = tmp_path / "FACTURAS" / "2026" / "10.OCTUBRE"

    def shown():
        return dialog.document_target.text().replace("\u200b", "")

    assert shown().endswith("FACTURAS\\2026\\10.OCTUBRE\\2026_10_15_Uber.pdf")
    assert dialog.document_target.toolTip() == str(month / "2026_10_15_Uber.pdf")
    assert dialog.document_target.isVisibleTo(dialog)
    # El nombre temporal del escaneo no se enseña.
    assert "164852376789" not in dialog.document_status.text()

    dialog.expense_date.setDate(QDate(2026, 11, 2))
    assert shown().endswith("11.NOVIEMBRE\\2026_11_02_Uber.pdf")

    # Guardar desde la ficha del proyecto: el gasto queda enlazado.
    def fake_exec(self):
        self.read_document(str(photo_pdf))
        self.file_label = "Uber"
        self.concept.setText("Trayecto")
        self.base_amount.setValue(10)
        self.expense_date.setDate(QDate(2026, 10, 15))
        self.validate()
        return QDialog.Accepted

    monkeypatch.setattr(expense_dialog.ExpenseDialog, "exec", fake_exec)
    page = ProjectDetailPage()
    page.load_project(project_id)
    page.new_expense()

    session = get_session()
    try:
        expense = session.query(Expense).filter(Expense.concept == "Trayecto").one()
        assert expense.document_file == str(month / "2026_10_15_Uber.pdf")
        assert (month / "2026_10_15_Uber.pdf").exists()
        session.delete(expense)
        session.commit()
    finally:
        session.close()
