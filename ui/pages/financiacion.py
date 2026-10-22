from calendar import monthrange
from datetime import date

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from database.database import get_session
from database.models import Loan


# Las cuotas se calculan en el motor central de tesorería.
# Al estar domiciliadas, cada cuota cuenta como pagada al llegar su fecha.
from services.cashflow import add_months, loan_schedule  # noqa: E402,F401
from ui.table_utils import fills


class LoanDialog(QDialog):
    def __init__(self, parent=None, loan=None):
        super().__init__(parent)
        self.loan = loan
        self.setWindowTitle("Editar financiación" if loan else "Nueva financiación")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit()
        self.bank = QLineEdit()

        self.principal = QDoubleSpinBox()
        self.principal.setRange(0, 100_000_000)
        self.principal.setDecimals(2)
        self.principal.setSuffix(" €")

        self.received_date = QDateEdit()
        self.received_date.setCalendarPopup(True)
        self.received_date.setDisplayFormat("dd/MM/yyyy")
        self.received_date.setDate(QDate.currentDate())


        self.term = QSpinBox()
        self.term.setRange(1, 600)
        self.term.setValue(60)

        self.monthly_payment = QDoubleSpinBox()
        self.monthly_payment.setRange(0, 10_000_000)
        self.monthly_payment.setDecimals(2)
        self.monthly_payment.setSuffix(" €")

        self.first_payment = QDateEdit()
        self.first_payment.setCalendarPopup(True)
        self.first_payment.setDisplayFormat("dd/MM/yyyy")
        self.first_payment.setDate(QDate.currentDate().addMonths(1))

        self.paid_installments = QSpinBox()
        self.paid_installments.setRange(0, 600)

        self.status = QComboBox()
        self.status.addItems(["Activo", "Finalizado", "Cancelado"])

        self.notes = QTextEdit()
        self.notes.setMaximumHeight(90)

        form.addRow("Nombre *", self.name)
        form.addRow("Banco", self.bank)
        form.addRow("Importe recibido *", self.principal)
        form.addRow("Fecha de ingreso *", self.received_date)
        form.addRow("Plazo (meses)", self.term)
        form.addRow("Cuota mensual", self.monthly_payment)
        form.addRow("Primera cuota", self.first_payment)
        form.addRow("Cuotas pagadas por adelantado", self.paid_installments)
        form.addRow("Estado", self.status)
        form.addRow("Notas", self.notes)
        layout.addLayout(form)

        hint = QLabel(
            "La cuota mensual se introduce manualmente. No se calcula con TIN. "
            "Las cuotas están domiciliadas: cada cuota se da por pagada "
            "automáticamente al llegar su fecha. Usa 'Cuotas pagadas por "
            "adelantado' solo si has amortizado cuotas antes de su fecha."
        )
        hint.setWordWrap(True)
        hint.setObjectName("cardDescription")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if loan:
            self.load_loan()

    def load_loan(self):
        l = self.loan
        self.name.setText(l.name or "")
        self.bank.setText(l.bank or "")
        self.principal.setValue(l.principal or 0.0)
        if l.received_date:
            self.received_date.setDate(QDate(l.received_date.year, l.received_date.month, l.received_date.day))
        self.term.setValue(l.term_months or 1)
        self.monthly_payment.setValue(l.monthly_payment or 0.0)
        if l.first_payment_date:
            self.first_payment.setDate(QDate(l.first_payment_date.year, l.first_payment_date.month, l.first_payment_date.day))
        self.paid_installments.setMaximum(max(600, l.term_months or 1))
        self.paid_installments.setValue(l.paid_installments or 0)
        idx = self.status.findText(l.status or "Activo")
        self.status.setCurrentIndex(max(0, idx))
        self.notes.setPlainText(l.notes or "")

    def validate(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Datos incompletos", "Indica un nombre para la financiación.")
            return
        if self.principal.value() <= 0:
            QMessageBox.warning(self, "Datos incompletos", "El importe recibido debe ser mayor que 0.")
            return
        if self.monthly_payment.value() <= 0:
            QMessageBox.warning(self, "Datos incompletos", "Introduce manualmente la cuota mensual.")
            return
        if self.paid_installments.value() > self.term.value():
            QMessageBox.warning(self, "Dato incorrecto", "Las cuotas pagadas no pueden superar el plazo.")
            return
        self.accept()

    def data(self):
        return {
            "name": self.name.text().strip(),
            "bank": self.bank.text().strip() or None,
            "principal": self.principal.value(),
            "received_date": self.received_date.date().toPython(),
            "annual_interest_rate": 0.0,
            "term_months": self.term.value(),
            "monthly_payment": self.monthly_payment.value(),
            "first_payment_date": self.first_payment.date().toPython(),
            "paid_installments": self.paid_installments.value(),
            "status": self.status.currentText(),
            "notes": self.notes.toPlainText().strip() or None,
        }


class FinancingPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Financiación")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Préstamos bancarios y su impacto en la tesorería.")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        new_btn = QPushButton("+  Nueva financiación")
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(self.new_loan)
        header.addWidget(new_btn)
        layout.addLayout(header)

        cards = QHBoxLayout()
        self.received_value = QLabel("0,00 €")
        self.pending_value = QLabel("0,00 €")
        self.monthly_value = QLabel("0,00 €")
        self.remaining_payments_value = QLabel("0,00 €")
        cards.addWidget(self.card("Financiación recibida", self.received_value, "Capital recibido"))
        cards.addWidget(self.card("Cuotas pendientes", self.pending_value, "Pagos futuros previstos"))
        cards.addWidget(self.card("Cuotas mensuales", self.monthly_value, "Préstamos activos"))
        cards.addWidget(self.card("Pagos pendientes", self.remaining_payments_value, "Sin separar capital e intereses"))
        layout.addLayout(cards)

        panel = QFrame()
        panel.setObjectName("panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(20, 18, 20, 18)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Nombre", "Banco", "Importe", "Ingreso", "Plazo",
            "Cuota", "Pagadas", "Pagos pendientes", "Estado"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.edit_loan)
        pl.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.addStretch()
        edit_btn = QPushButton("Editar")
        edit_btn.setObjectName("secondaryButton")
        edit_btn.clicked.connect(self.edit_loan)
        delete_btn = QPushButton("Eliminar")
        delete_btn.setObjectName("secondaryButton")
        delete_btn.clicked.connect(self.delete_loan)
        buttons.addWidget(edit_btn)
        buttons.addWidget(delete_btn)
        pl.addLayout(buttons)
        layout.addWidget(panel, 1)

    def card(self, title_text, value, desc):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(110)
        l = QVBoxLayout(card)
        l.setContentsMargins(20, 14, 20, 14)
        t = QLabel(title_text); t.setObjectName("cardTitle")
        value.setObjectName("cardValue")
        d = QLabel(desc); d.setObjectName("cardDescription")
        l.addWidget(t); l.addWidget(value); l.addStretch(); l.addWidget(d)
        return card

    def selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def new_loan(self):
        dialog = LoanDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        session = get_session()
        try:
            session.add(Loan(**dialog.data()))
            session.commit()
        finally:
            session.close()
        self.refresh()

    def edit_loan(self, *_):
        loan_id = self.selected_id()
        if not loan_id:
            return
        session = get_session()
        try:
            loan = session.get(Loan, loan_id)
            if not loan:
                return
            dialog = LoanDialog(self, loan)
            if dialog.exec() != QDialog.Accepted:
                return
            for key, value in dialog.data().items():
                setattr(loan, key, value)
            session.commit()
        finally:
            session.close()
        self.refresh()

    def delete_loan(self):
        loan_id = self.selected_id()
        if not loan_id:
            return
        if QMessageBox.question(
            self, "Eliminar financiación",
            "¿Quieres eliminar esta financiación y su previsión?"
        ) != QMessageBox.Yes:
            return
        session = get_session()
        try:
            loan = session.get(Loan, loan_id)
            if loan:
                session.delete(loan)
                session.commit()
        finally:
            session.close()
        self.refresh()

    @fills("table")
    def refresh(self):
        session = get_session()
        try:
            loans = session.query(Loan).order_by(Loan.received_date.desc()).all()
            rows = []
            total_received = total_pending = total_monthly = 0.0

            for loan in loans:
                schedule = loan_schedule(loan)
                paid = sum(1 for row in schedule if row["paid"])
                pending_schedule = [row for row in schedule if not row["paid"]]
                pending_payments = sum(x["payment"] for x in pending_schedule)
                payment = float(loan.monthly_payment or 0.0)

                if loan.status != "Cancelado":
                    total_received += loan.principal or 0.0
                    total_pending += pending_payments
                    if loan.status == "Activo" and pending_schedule:
                        total_monthly += payment

                rows.append((loan, pending_payments, payment, paid))

            self.table.setRowCount(len(rows))
            for row, (loan, pending_payments, payment, paid) in enumerate(rows):
                values = [
                    loan.name,
                    loan.bank or "—",
                    self.money(loan.principal),
                    loan.received_date.strftime("%d/%m/%Y") if loan.received_date else "—",
                    f"{loan.term_months} meses",
                    self.money(payment),
                    f"{paid}/{loan.term_months}",
                    self.money(pending_payments),
                    loan.status,
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if col == 0:
                        item.setData(Qt.UserRole, loan.id)
                    if col in (2, 5, 7):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(row, col, item)

            self.received_value.setText(self.money(total_received))
            self.pending_value.setText(self.money(total_pending))
            self.monthly_value.setText(self.money(total_monthly))
            self.remaining_payments_value.setText(self.money(total_pending))
        finally:
            session.close()

    @staticmethod
    def money(value):
        text = f"{float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{text} €"
