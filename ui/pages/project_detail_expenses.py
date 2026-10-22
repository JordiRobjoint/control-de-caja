"""Pestaña Gastos de la ficha de proyecto."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.cashflow import money as _money
from database.database import get_session
from database.models import Expense
from ui.pages.dialogs.expense_dialog import ExpenseDialog
from ui.table_utils import fills


class ExpensesTabMixin:
    """Pestaña Gastos de la ficha de proyecto (se mezcla en ProjectDetailPage)."""

    # ==========================================================
    # GASTOS
    # ==========================================================

    def create_expenses_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Gastos")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        edit_button = QPushButton("Editar")
        edit_button.setObjectName("secondaryButton")
        edit_button.setCursor(Qt.PointingHandCursor)
        edit_button.clicked.connect(self.edit_expense)

        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self.delete_expense)

        new_button = QPushButton("+  Nuevo gasto")
        new_button.setObjectName("primaryButton")
        new_button.setCursor(Qt.PointingHandCursor)
        new_button.clicked.connect(self.new_expense)

        header.addWidget(edit_button)
        header.addWidget(delete_button)
        header.addWidget(new_button)
        layout.addLayout(header)

        self.expenses_table = QTableWidget()
        self.expenses_table.setColumnCount(11)
        self.expenses_table.setHorizontalHeaderLabels([
            "Categoría",
            "Concepto",
            "Proveedor",
            "Tipo",
            "Fecha / periodo",
            "Estado",
            "Base mensual",
            "Total mensual",
            "Nº meses",
            "Base periodo",
            "Total periodo",
        ])
        self.expenses_table.verticalHeader().setVisible(False)
        self.expenses_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.expenses_table.setSelectionMode(QTableWidget.SingleSelection)
        self.expenses_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.expenses_table.setShowGrid(False)
        self.expenses_table.setAlternatingRowColors(True)
        self.expenses_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        for column in (3, 4, 5, 6, 7, 8, 9, 10):
            self.expenses_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeToContents,
            )
        self.expenses_table.doubleClicked.connect(self.edit_expense)

        layout.addWidget(self.expenses_table)
        return widget

    # ==========================================================
    # CARGAR GASTOS
    # ==========================================================

    @fills("expenses_table")
    def load_expenses(self):
        if self.project_id is None:
            return

        session = get_session()

        try:
            expenses = (
                session.query(Expense)
                .filter(Expense.project_id == self.project_id)
                .order_by(Expense.id.desc())
                .all()
            )

            self.expenses = expenses
            self.expenses_table.setRowCount(len(expenses))

            # Para rentabilidad usamos base sin IVA.
            # En un gasto mensual, base_amount representa UNA mensualidad.
            total_expenses_base = 0.0

            for row, expense in enumerate(expenses):

                payment_type = expense.payment_type or "Único"
                months = self.expense_month_count(expense, expense.project)

                if expense.status != "Cancelado":
                    total_expenses_base += (
                        (expense.base_amount or 0.0) * months
                    )

                if payment_type == "Mensual":
                    start_text = (
                        expense.recurrence_start.strftime("%d/%m/%Y")
                        if expense.recurrence_start else "—"
                    )
                    end_text = (
                        expense.recurrence_end.strftime("%d/%m/%Y")
                        if expense.recurrence_end else "—"
                    )
                    date_text = f"{start_text} → {end_text}"
                    type_text = f"Mensual · {months} mes"
                    if months != 1:
                        type_text += "es"
                else:
                    date_text = (
                        expense.expense_date.strftime("%d/%m/%Y")
                        if expense.expense_date else "—"
                    )
                    type_text = "Único"

                base_monthly = expense.base_amount or 0.0
                total_monthly = expense.total_amount or 0.0

                base_period = base_monthly * months
                total_period = total_monthly * months

                values = [
                    expense.category,
                    expense.concept,
                    expense.supplier or "—",
                    type_text,
                    date_text,
                    expense.status,
                    _money(base_monthly),
                    _money(total_monthly),
                    str(months),
                    _money(base_period),
                    _money(total_period),
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))

                    if column in (6, 7, 8, 9, 10):
                        item.setTextAlignment(
                            Qt.AlignRight | Qt.AlignVCenter
                        )

                    self.expenses_table.setItem(
                        row,
                        column,
                        item,
                    )

            self.expenses_table.clearSelection()

            self.expenses_value.setText(
                _money(total_expenses_base)
            )

            total_contracted = getattr(
                self,
                "total_contracted",
                0.0,
            )

            margin = (
                total_contracted
                - total_expenses_base
            )

            self.margin_value.setText(
                _money(margin)
            )

        finally:
            session.close()

    # ==========================================================
    # NÚMERO DE MENSUALIDADES
    # ==========================================================

    @staticmethod
    def expense_month_count(expense, project=None):
        """Número de mensualidades (cálculo central de tesorería)."""
        from services.cashflow import expense_month_count
        return expense_month_count(expense, project)

    # ==========================================================
    # NUEVO GASTO
    # ==========================================================

    def new_expense(self):
        if self.project_id is None:
            return

        dialog = ExpenseDialog(self)

        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        session = get_session()

        try:
            expense = Expense(
                project_id=self.project_id,
                category=data["category"],
                concept=data["concept"],
                supplier=data["supplier"],
                payment_type=data["payment_type"],
                expense_date=data["expense_date"],
                recurrence_start=data["recurrence_start"],
                recurrence_end=data["recurrence_end"],
                base_amount=data["base_amount"],
                vat_rate=data["vat_rate"],
                vat_amount=data["vat_amount"],
                total_amount=data["total_amount"],
                status=data["status"],
                payment_date=data["payment_date"],
                invoice_reference=data["invoice_reference"],
                notes=data["notes"],
                document_file=data["document_file"],
            )

            session.add(expense)
            session.commit()

        except Exception as error:
            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido guardar el gasto.\n\n{error}",
            )

            return

        finally:
            session.close()

        self.load_expenses()

    # ==========================================================
    # EDITAR GASTO
    # ==========================================================

    def edit_expense(self):
        row = self.expenses_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Selecciona un gasto",
                "Selecciona primero el gasto que quieres editar.",
            )
            return

        if row >= len(self.expenses):
            return

        selected = self.expenses[row]
        session = get_session()

        try:
            expense = session.get(
                Expense,
                selected.id,
            )

            if expense is None:
                return

            dialog = ExpenseDialog(
                self,
                expense=expense,
            )

            if dialog.exec() != QDialog.Accepted:
                return

            data = dialog.get_data()

            expense.category = data["category"]
            expense.concept = data["concept"]
            expense.supplier = data["supplier"]

            expense.payment_type = data[
                "payment_type"
            ]

            expense.expense_date = data[
                "expense_date"
            ]

            expense.recurrence_start = data[
                "recurrence_start"
            ]

            expense.recurrence_end = data[
                "recurrence_end"
            ]

            expense.base_amount = data[
                "base_amount"
            ]

            expense.vat_rate = data[
                "vat_rate"
            ]

            expense.vat_amount = data[
                "vat_amount"
            ]

            expense.total_amount = data[
                "total_amount"
            ]

            expense.status = data[
                "status"
            ]

            expense.payment_date = data[
                "payment_date"
            ]

            expense.invoice_reference = data[
                "invoice_reference"
            ]

            expense.notes = data["notes"]
            expense.document_file = data["document_file"]

            session.commit()

        except Exception as error:
            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido modificar el gasto.\n\n{error}",
            )

            return

        finally:
            session.close()

        self.load_expenses()

    # ==========================================================
    # ELIMINAR GASTO
    # ==========================================================

    def delete_expense(self):
        row = self.expenses_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Selecciona un gasto",
                "Selecciona el gasto que quieres eliminar.",
            )
            return

        if row >= len(self.expenses):
            return

        selected = self.expenses[row]

        answer = QMessageBox.question(
            self,
            "Eliminar gasto",
            (
                f"¿Seguro que quieres eliminar '{selected.concept}'?\n\n"
                "Esta acción no se puede deshacer."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        session = get_session()

        try:
            expense = session.get(
                Expense,
                selected.id,
            )

            if expense is None:
                return

            session.delete(expense)
            session.commit()

        except Exception as error:
            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido eliminar el gasto.\n\n{error}",
            )

            return

        finally:
            session.close()

        self.load_expenses()
