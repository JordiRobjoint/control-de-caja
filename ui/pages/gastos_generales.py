from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.database import get_session
from database.models import Expense
from services.cashflow import add_money, add_months, is_recurring, round_money
from ui.table_utils import fills


GENERAL_CATEGORIES = [
    "Nóminas",
    "Seguridad Social / Autónomos",
    "Seguros",
    "Gestoría / Asesoría",
    "Software / Licencias",
    "Telefonía / Internet",
    "Alquiler / Oficina",
    "Bancos / Comisiones",
    "Vehículos",
    "Marketing",
    "Formación",
    "Impuestos / Tasas",
    "Material de oficina",
    "Otros",
]


class GeneralExpenseDialog(QDialog):
    """Formulario específico para costes fijos mensuales e indefinidos."""

    def __init__(self, parent=None, expense=None):
        super().__init__(parent)
        self.expense = expense
        self.setWindowTitle(
            "Editar gasto general" if expense else "Nuevo gasto general"
        )
        self.setMinimumWidth(560)
        self.setup_ui()

        if expense is not None:
            self.load_expense(expense)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        info = QLabel(
            "Gasto fijo mensual. Cada mensualidad se da por pagada "
            "automáticamente al llegar su fecha y las futuras se incluyen "
            "en la previsión de caja."
        )
        info.setObjectName("pageSubtitle")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(12)

        self.category = QComboBox()
        self.category.addItems(GENERAL_CATEGORIES)

        self.concept = QLineEdit()
        self.concept.setPlaceholderText("Ej. Nóminas equipo")

        self.supplier = QLineEdit()
        self.supplier.setPlaceholderText("Ej. Empleados / aseguradora / gestoría")

        self.base_amount = QDoubleSpinBox()
        self.base_amount.setRange(0.0, 999999999.99)
        self.base_amount.setDecimals(2)
        self.base_amount.setSuffix(" €")
        self.base_amount.valueChanged.connect(self.update_totals)

        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0.0, 100.0)
        self.vat_rate.setDecimals(2)
        self.vat_rate.setValue(21.0)
        self.vat_rate.setSuffix(" %")
        self.vat_rate.valueChanged.connect(self.update_totals)

        self.vat_value = QLabel("0,00 €")
        self.total_value = QLabel("0,00 €")

        self.status = QComboBox()
        self.status.addItems(["Activo", "Inactivo"])

        today = QDate.currentDate()
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd/MM/yyyy")
        self.start_date.setDate(QDate(today.year(), today.month(), 1))
        self.start_date.setToolTip(
            "Fecha del primer cargo. El día se repite cada mes."
        )

        self.has_end = QCheckBox("Tiene fecha de fin")
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd/MM/yyyy")
        self.end_date.setDate(today.addYears(1))
        self.end_date.setEnabled(False)
        self.has_end.toggled.connect(self.end_date.setEnabled)
        end_row = QHBoxLayout()
        end_row.addWidget(self.has_end)
        end_row.addWidget(self.end_date, 1)

        self.notes = QTextEdit()
        self.notes.setMaximumHeight(90)
        self.notes.setPlaceholderText("Observaciones opcionales")

        form.addRow("Categoría", self.category)
        form.addRow("Concepto", self.concept)
        form.addRow("Proveedor", self.supplier)
        form.addRow("Base mensual", self.base_amount)
        form.addRow("IVA", self.vat_rate)
        form.addRow("IVA mensual", self.vat_value)
        form.addRow("Total mensual", self.total_value)
        form.addRow("Activo desde (1er cargo)", self.start_date)
        form.addRow("Hasta", end_row)
        form.addRow("Estado", self.status)
        form.addRow("Notas", self.notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.update_totals()

    def load_expense(self, expense):
        index = self.category.findText(expense.category)
        if index < 0:
            self.category.addItem(expense.category)
            index = self.category.findText(expense.category)
        self.category.setCurrentIndex(index)

        self.concept.setText(expense.concept or "")
        self.supplier.setText(expense.supplier or "")
        self.base_amount.setValue(expense.base_amount or 0.0)
        self.vat_rate.setValue(expense.vat_rate or 0.0)

        # Compatibilidad con los estados antiguos.
        self.status.setCurrentText(
            "Inactivo"
            if expense.status in ("Cancelado", "Inactivo")
            else "Activo"
        )
        if expense.recurrence_start:
            d = expense.recurrence_start
            self.start_date.setDate(QDate(d.year, d.month, d.day))
        if expense.recurrence_end:
            d = expense.recurrence_end
            self.has_end.setChecked(True)
            self.end_date.setDate(QDate(d.year, d.month, d.day))
        self.notes.setPlainText(expense.notes or "")
        self.update_totals()

    def update_totals(self):
        base = self.base_amount.value()
        vat_rate = self.vat_rate.value()
        vat = round_money(base * vat_rate / 100.0)
        total = round_money(add_money(base, vat))

        self.vat_value.setText(self.money(vat))
        self.total_value.setText(self.money(total))

    def validate_and_accept(self):
        if not self.concept.text().strip():
            QMessageBox.warning(
                self,
                "Concepto obligatorio",
                "Introduce un concepto para el gasto general.",
            )
            return

        if (
            self.has_end.isChecked()
            and self.end_date.date() < self.start_date.date()
        ):
            QMessageBox.warning(
                self,
                "Fechas incorrectas",
                "La fecha de fin no puede ser anterior a la de inicio.",
            )
            return

        self.accept()

    def get_data(self):
        base = self.base_amount.value()
        vat_rate = self.vat_rate.value()
        vat = round_money(base * vat_rate / 100.0)
        total = round_money(add_money(base, vat))

        return {
            "category": self.category.currentText(),
            "concept": self.concept.text().strip(),
            "supplier": self.supplier.text().strip() or None,
            "payment_type": "Mensual",
            "expense_date": None,
            "recurrence_start": self.start_date.date().toPython(),
            "recurrence_end": (
                self.end_date.date().toPython()
                if self.has_end.isChecked() else None
            ),
            "base_amount": base,
            "vat_rate": vat_rate,
            "vat_amount": vat,
            "total_amount": total,
            "status": self.status.currentText(),
            "payment_date": None,
            "invoice_reference": None,
            "notes": self.notes.toPlainText().strip() or None,
        }

    @staticmethod
    def money(value):
        text = f"{value:,.2f}"
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{text} €"


class GeneralExpensesPage(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.expenses = []
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(22)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("Gastos generales")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Costes fijos mensuales de empresa no asociados a proyectos."
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        new_button = QPushButton("+  Nuevo gasto")
        new_button.setObjectName("primaryButton")
        new_button.setCursor(Qt.PointingHandCursor)
        new_button.clicked.connect(self.new_expense)
        header.addWidget(new_button)

        edit_button = QPushButton("Editar")
        edit_button.setObjectName("secondaryButton")
        edit_button.setCursor(Qt.PointingHandCursor)
        edit_button.clicked.connect(self.edit_expense)
        header.addWidget(edit_button)

        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("secondaryButton")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self.delete_expense)
        header.addWidget(delete_button)

        layout.addLayout(header)

        cards = QHBoxLayout()
        cards.setSpacing(15)

        self.base_monthly_value = QLabel("0,00 €")
        self.vat_monthly_value = QLabel("0,00 €")
        self.total_monthly_value = QLabel("0,00 €")
        self.annual_value = QLabel("0,00 €")

        cards.addWidget(self.create_card(
            "Base mensual",
            self.base_monthly_value,
            "Gastos activos sin IVA",
        ))
        cards.addWidget(self.create_card(
            "IVA mensual",
            self.vat_monthly_value,
            "IVA mensual estimado",
        ))
        cards.addWidget(self.create_card(
            "Gasto fijo mensual",
            self.total_monthly_value,
            "Salida bancaria mensual",
        ))
        cards.addWidget(self.create_card(
            "Gasto fijo anual",
            self.annual_value,
            "Estimación mensual × 12",
        ))

        layout.addLayout(cards)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(15)

        panel_title = QLabel("Estructura mensual")
        panel_title.setObjectName("panelTitle")
        panel_layout.addWidget(panel_title)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Categoría",
            "Concepto",
            "Proveedor",
            "Estado",
            "Base mensual",
            "IVA",
            "IVA mensual",
            "Total mensual",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.edit_expense)

        panel_layout.addWidget(self.table)
        layout.addWidget(panel, 1)

    def create_card(self, title_text, value_label, description_text):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(120)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        value_label.setObjectName("cardValue")
        description = QLabel(description_text)
        description.setObjectName("cardDescription")

        card_layout.addWidget(title)
        card_layout.addWidget(value_label)
        card_layout.addStretch()
        card_layout.addWidget(description)
        return card

    def refresh(self):
        session = get_session()
        try:
            # Solo los mensuales: las facturas sueltas sin proyecto están
            # en Pagos.
            expenses = [
                expense
                for expense in (
                    session.query(Expense)
                    .filter(Expense.project_id.is_(None))
                    .order_by(Expense.category.asc(), Expense.concept.asc())
                    .all()
                )
                if is_recurring(expense)
            ]

            # Copiamos los valores necesarios antes de cerrar la sesión.
            self.expenses = [
                {
                    "id": e.id,
                    "category": e.category,
                    "concept": e.concept,
                    "supplier": e.supplier,
                    "base_amount": e.base_amount or 0.0,
                    "vat_rate": e.vat_rate or 0.0,
                    "vat_amount": e.vat_amount or 0.0,
                    "total_amount": e.total_amount or 0.0,
                    "status": e.status,
                    "start": e.recurrence_start,
                    "end": e.recurrence_end,
                }
                for e in expenses
            ]
        finally:
            session.close()

        self.fill_table()

    @fills("table")
    def fill_table(self):
        self.table.setRowCount(len(self.expenses))

        base_monthly = 0.0
        vat_monthly = 0.0
        total_monthly = 0.0

        for row, expense in enumerate(self.expenses):
            status_text = self.status_text(expense)
            # El coste mensual solo suma los gastos vigentes este mes.
            active = status_text == "Activo"

            if active:
                base_monthly = add_money(base_monthly, expense["base_amount"])
                vat_monthly = add_money(vat_monthly, expense["vat_amount"])
                total_monthly = add_money(total_monthly, expense["total_amount"])

            values = [
                expense["category"],
                expense["concept"],
                expense["supplier"] or "—",
                status_text,
                self.money(expense["base_amount"]),
                f'{expense["vat_rate"]:.2f} %',
                self.money(expense["vat_amount"]),
                self.money(expense["total_amount"]),
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column >= 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, item)

        self.base_monthly_value.setText(self.money(base_monthly))
        self.vat_monthly_value.setText(self.money(vat_monthly))
        self.total_monthly_value.setText(self.money(total_monthly))
        self.annual_value.setText(self.money(total_monthly * 12))
        self.table.clearSelection()

    @staticmethod
    def status_text(expense, today=None):
        today = today or date.today()
        if expense["status"] in ("Inactivo", "Cancelado"):
            return "Inactivo"
        first_day = today.replace(day=1)
        if expense["end"] is not None and expense["end"] < first_day:
            return "Finalizado"
        if expense["start"] is not None and expense["start"] > add_months(first_day, 1) - timedelta(days=1):
            return f"Desde {expense['start'].strftime('%d/%m/%Y')}"
        return "Activo"

    def new_expense(self):
        dialog = GeneralExpenseDialog(self)

        if dialog.exec() != QDialog.Accepted:
            return

        session = get_session()
        try:
            expense = Expense(
                project_id=None,
                **dialog.get_data(),
            )
            session.add(expense)
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido guardar el gasto general.\n\n{error}",
            )
            return
        finally:
            session.close()

        self.refresh()

    def edit_expense(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.expenses):
            QMessageBox.warning(
                self,
                "Selecciona un gasto",
                "Selecciona primero el gasto general que quieres editar.",
            )
            return

        expense_id = self.expenses[row]["id"]
        session = get_session()

        try:
            expense = session.get(Expense, expense_id)

            if expense is None or expense.project_id is not None:
                return

            dialog = GeneralExpenseDialog(self, expense)

            if dialog.exec() != QDialog.Accepted:
                return

            for key, value in dialog.get_data().items():
                setattr(expense, key, value)

            expense.project_id = None
            session.commit()

        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido actualizar el gasto general.\n\n{error}",
            )
            return
        finally:
            session.close()

        self.refresh()

    def delete_expense(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.expenses):
            QMessageBox.warning(
                self,
                "Selecciona un gasto",
                "Selecciona primero el gasto general que quieres eliminar.",
            )
            return

        selected = self.expenses[row]

        answer = QMessageBox.question(
            self,
            "Eliminar gasto general",
            f'¿Quieres eliminar "{selected["concept"]}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        session = get_session()

        try:
            expense = session.get(Expense, selected["id"])
            if expense is not None and expense.project_id is None:
                session.delete(expense)
                session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido eliminar el gasto general.\n\n{error}",
            )
            return
        finally:
            session.close()

        self.refresh()

    @staticmethod
    def money(value):
        text = f"{value:,.2f}"
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{text} €"
