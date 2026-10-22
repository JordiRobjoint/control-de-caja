"""Ventana para registrar la liquidación real del IVA (modelo 303)."""

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from services.cashflow import money


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


class VatSettlementDialog(QDialog):
    """
    rows:     filas de cashflow.vat_quarters (para elegir trimestre y ver
              la estimación de la app).
    selected: (año, trimestre) a mostrar al abrir.
    existing: liquidación ya registrada de ese trimestre (para editar).
    """

    def __init__(self, parent, rows, selected=None, existing=None):
        super().__init__(parent)
        self.rows = {(row["year"], row["quarter"]): row for row in rows}

        self.setWindowTitle("Liquidación de IVA (modelo 303)")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        intro = QLabel(
            "Introduce el resultado del modelo 303 que ha presentado la "
            "gestoría. La tesorería usará este importe y esta fecha en lugar "
            "de la estimación de la app."
        )
        intro.setObjectName("pageSubtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)

        # El dato de cada opción es año*10 + trimestre: PySide convierte las
        # tuplas y findData() dejaría de encontrarlas.
        self.quarter = QComboBox()
        for year, quarter in sorted(self.rows, reverse=True):
            self.quarter.addItem(self.rows[(year, quarter)]["label"], year * 10 + quarter)
        if selected is not None:
            index = self.quarter.findData(selected[0] * 10 + selected[1])
            if index >= 0:
                self.quarter.setCurrentIndex(index)
        self.quarter.setEnabled(existing is None)
        self.quarter.currentIndexChanged.connect(self.update_estimate)

        self.estimate = QLabel()
        self.estimate.setObjectName("cardDescription")

        self.amount = QDoubleSpinBox()
        self.amount.setRange(-99_999_999, 99_999_999)
        self.amount.setDecimals(2)
        self.amount.setSuffix(" €")
        self.amount.setGroupSeparatorShown(True)
        self.amount.valueChanged.connect(self.update_payment_date)

        self.payment_date = QDateEdit(_qdate(date.today()))
        self.payment_date.setCalendarPopup(True)
        self.payment_date.setDisplayFormat("dd/MM/yyyy")

        self.notes = QTextEdit()
        self.notes.setMaximumHeight(70)
        self.notes.setPlaceholderText("Ej. incluye facturas de compras no registradas en la app")

        hint = QLabel("Positivo: importe pagado · Negativo: resultado a compensar")
        hint.setObjectName("cardDescription")

        form.addRow("Trimestre", self.quarter)
        form.addRow("Estimación de la app", self.estimate)
        form.addRow("Resultado del 303", self.amount)
        form.addRow("", hint)
        form.addRow("Fecha de pago", self.payment_date)
        form.addRow("Notas", self.notes)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if existing is not None:
            self.amount.setValue(existing.amount or 0.0)
            if existing.payment_date:
                self.payment_date.setDate(_qdate(existing.payment_date))
            self.notes.setPlainText(existing.notes or "")

        self.update_estimate()
        self.update_payment_date()

    def current_key(self):
        code = self.quarter.currentData()
        return None if code is None else divmod(int(code), 10)

    def current_row(self):
        return self.rows.get(self.current_key())

    def update_estimate(self):
        row = self.current_row()
        if row is None:
            self.estimate.setText("—")
            return
        self.estimate.setText(
            f"{money(row['estimated'])}  (repercutido {money(row['output'])} − "
            f"soportado {money(row['input'])})"
        )

    def update_payment_date(self):
        # Sin importe a pagar no hay fecha de pago.
        self.payment_date.setEnabled(self.amount.value() > 0)

    def validate(self):
        if self.current_key() is None:
            QMessageBox.warning(self, "Trimestre", "Elige el trimestre.")
            return
        self.accept()

    def get_data(self):
        year, quarter = self.current_key()
        amount = self.amount.value()
        return {
            "year": year,
            "quarter": quarter,
            "amount": amount,
            "payment_date": self.payment_date.date().toPython() if amount > 0 else None,
            "notes": self.notes.toPlainText().strip() or None,
        }
