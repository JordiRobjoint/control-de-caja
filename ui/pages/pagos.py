from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QInputDialog,
)
from services.cashflow import date_text, expense_month_count, is_recurring, money
from database.database import get_session
from database.models import Expense, Project
from ui.pages.dialogs.expense_dialog import ExpenseDialog
from ui.table_filters import ColumnFilters
from ui.table_utils import bulk_fill


# Filtro y opción para los gastos sin proyecto (facturas sueltas).
GENERAL = "general"
GENERAL_LABEL = "General (sin proyecto)"


class PaymentsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(22)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Pagos")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Gastos de los proyectos y facturas sueltas de la empresa."
        )
        subtitle.setObjectName("pageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()

        self.project_filter = QComboBox()
        self.project_filter.setObjectName("filterCombo")
        self.project_filter.currentIndexChanged.connect(self.load_rows)
        header.addWidget(self.project_filter)

        buttons = [
            ("Editar", self.edit, "secondaryButton"),
            ("Eliminar", self.delete, "dangerButton"),
            ("+  Nuevo gasto", self.new, "primaryButton"),
        ]
        for text, slot, object_name in buttons:
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            header.addWidget(button)
        layout.addLayout(header)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "Proyecto", "Categoría", "Concepto", "Proveedor", "Tipo", "Fecha / periodo",
            "Estado", "Base mensual", "Total mensual", "Nº meses", "Base periodo", "Total periodo",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for column in (4, 5, 6, 7, 8, 9, 10, 11):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self.edit)

        self.filters = ColumnFilters(self.table, self)
        panel_layout.addWidget(self.filters.status_widget())
        panel_layout.addWidget(self.table)
        layout.addWidget(panel, 1)

    def refresh(self):
        current = self.project_filter.currentData() if self.project_filter.count() else None
        session = get_session()
        try:
            projects = [(p.id, p.name) for p in session.query(Project).order_by(Project.name).all()]
        finally:
            session.close()

        self.project_filter.blockSignals(True)
        self.project_filter.clear()
        self.project_filter.addItem("Todos los proyectos", None)
        self.project_filter.addItem(GENERAL_LABEL, GENERAL)
        for project_id, name in projects:
            self.project_filter.addItem(name, project_id)
        index = self.project_filter.findData(current)
        self.project_filter.setCurrentIndex(index if index >= 0 else 0)
        self.project_filter.blockSignals(False)
        self.load_rows()

    def load_rows(self):
        project_id = self.project_filter.currentData()
        session = get_session()
        try:
            query = (
                session.query(Expense, Project)
                .outerjoin(Project, Expense.project_id == Project.id)
            )
            if project_id == GENERAL:
                query = query.filter(Expense.project_id.is_(None))
            elif project_id is not None:
                query = query.filter(Project.id == project_id)
            results = [
                (expense, project)
                for expense, project in query.order_by(
                    Expense.expense_date.desc(), Expense.id.desc()
                ).all()
                # Los generales mensuales están en Gastos generales.
                if project is not None or not is_recurring(expense)
            ]

            self.rows = []
            for expense, project in results:
                payment_type = expense.payment_type or "Único"
                if payment_type == "Mensual":
                    period = f"{date_text(expense.recurrence_start)} - {date_text(expense.recurrence_end)}"
                else:
                    period = date_text(expense.expense_date)
                self.rows.append(dict(
                    id=expense.id,
                    project_id=project.id if project else None,
                    project=project.name if project else "General",
                    category=expense.category,
                    concept=expense.concept,
                    supplier=expense.supplier or "—",
                    type=payment_type,
                    period=period,
                    status=expense.status,
                    base=expense.base_amount or 0,
                    total=expense.total_amount or 0,
                    months=expense_month_count(expense, project),
                ))
        finally:
            session.close()

        with bulk_fill(self.table):
            self.table.setRowCount(len(self.rows))
            for row, data in enumerate(self.rows):
                values = [
                    data["project"], data["category"], data["concept"], data["supplier"],
                    data["type"], data["period"], data["status"],
                    money(data["base"]), money(data["total"]), str(data["months"]),
                    money(data["base"] * data["months"]), money(data["total"] * data["months"]),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column >= 7:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(row, column, item)
        self.filters.apply()

    def selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            QMessageBox.warning(self, "Selecciona un gasto", "Selecciona primero un gasto.")
            return None
        return self.rows[row]

    def choose_project(self):
        """(True, id de proyecto o None si es general) o (False, None)."""
        project_id = self.project_filter.currentData()
        if project_id == GENERAL:
            return True, None
        if project_id is not None:
            return True, project_id

        session = get_session()
        try:
            projects = [(p.id, p.name) for p in session.query(Project).order_by(Project.name).all()]
        finally:
            session.close()

        names = [GENERAL_LABEL] + [name for _, name in projects]
        name, ok = QInputDialog.getItem(
            self, "Seleccionar proyecto", "Proyecto:", names, 0, False
        )
        if not ok:
            return False, None
        return True, {n: i for i, n in projects}.get(name)

    def new(self):
        ok, project_id = self.choose_project()
        if not ok:
            return
        dialog = ExpenseDialog(self, general=project_id is None)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.get_data()
        session = get_session()
        try:
            session.add(Expense(project_id=project_id, **data))
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", str(error))
        finally:
            session.close()
        self.refresh()

    def edit(self):
        selected = self.selected()
        if not selected:
            return
        session = get_session()
        try:
            expense = session.get(Expense, selected["id"])
            dialog = ExpenseDialog(self, expense=expense)
            if dialog.exec() != QDialog.Accepted:
                return
            for key, value in dialog.get_data().items():
                setattr(expense, key, value)
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", str(error))
        finally:
            session.close()
        self.refresh()

    def delete(self):
        selected = self.selected()
        if not selected:
            return
        answer = QMessageBox.question(
            self,
            "Eliminar gasto",
            f"¿Eliminar '{selected['concept']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        session = get_session()
        try:
            expense = session.get(Expense, selected["id"])
            if expense:
                session.delete(expense)
                session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", str(error))
        finally:
            session.close()
        self.refresh()
