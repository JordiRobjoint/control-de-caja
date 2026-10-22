from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QInputDialog,
)
from services.cashflow import date_text, money, order_overrun
from database.database import get_session
from database.models import Collection, Order, Project
from ui.pages.dialogs.collection_dialog import CollectionDialog
from ui.pages.dialogs.invoice_dialog import block_if_invoiced, generate_invoice
from ui.table_filters import ColumnFilters
from ui.table_utils import fills


class CollectionsPage(QWidget):
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
        title = QLabel("Cobros")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Seguimiento global de cobros previstos, facturados y realizados.")
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
            ("🧾  Factura", self.invoice, "secondaryButton"),
            ("Editar", self.edit, "secondaryButton"),
            ("Eliminar", self.delete, "dangerButton"),
            ("+  Nuevo cobro", self.new, "primaryButton"),
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
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Proyecto", "Pedido", "Concepto", "%", "Importe (base)",
            "Fecha prevista", "Estado", "Nº factura", "Fecha factura", "Fecha cobro",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for column in (3, 4, 5, 6, 7, 8, 9):
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
        for project_id, name in projects:
            self.project_filter.addItem(name, project_id)
        index = self.project_filter.findData(current)
        self.project_filter.setCurrentIndex(index if index >= 0 else 0)
        self.project_filter.blockSignals(False)
        self.load_rows()

    @fills("table")
    def load_rows(self):
        project_id = self.project_filter.currentData()
        session = get_session()
        try:
            query = (
                session.query(Collection, Order, Project)
                .join(Order, Collection.order_id == Order.id)
                .join(Project, Order.project_id == Project.id)
            )
            if project_id is not None:
                query = query.filter(Project.id == project_id)
            results = query.order_by(Collection.expected_date.asc(), Collection.id.asc()).all()
            self.rows = [
                dict(
                    id=c.id,
                    project_id=p.id,
                    project=p.name,
                    order=o.order_number,
                    concept=c.concept,
                    percentage=c.percentage,
                    amount=c.amount or 0,
                    expected=c.expected_date,
                    status=c.status,
                    invoice=c.invoice_number or "—",
                    invoice_date=c.invoice_date,
                    collected=c.collection_date,
                )
                for c, o, p in results
            ]
        finally:
            session.close()

        self.table.setRowCount(len(self.rows))
        for row, data in enumerate(self.rows):
            percentage = f"{data['percentage']:.2f} %" if data["percentage"] is not None else "—"
            values = [
                data["project"], data["order"], data["concept"], percentage,
                money(data["amount"]), date_text(data["expected"]), data["status"],
                data["invoice"], date_text(data["invoice_date"]), date_text(data["collected"]),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, item)
        self.filters.apply()

    def selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            QMessageBox.warning(self, "Selecciona un cobro", "Selecciona primero un cobro.")
            return None
        return self.rows[row]

    def choose_project(self):
        project_id = self.project_filter.currentData()
        if project_id is not None:
            return project_id

        session = get_session()
        try:
            projects = [(p.id, p.name) for p in session.query(Project).order_by(Project.name).all()]
        finally:
            session.close()

        if not projects:
            QMessageBox.warning(self, "No hay proyectos", "Crea primero un proyecto.")
            return None
        names = [name for _, name in projects]
        name, ok = QInputDialog.getItem(self, "Seleccionar proyecto", "Proyecto:", names, 0, False)
        return {n: i for i, n in projects}.get(name) if ok else None

    def project_orders(self, project_id, session):
        return (
            session.query(Order)
            .filter(Order.project_id == project_id)
            .order_by(Order.order_date, Order.id)
            .all()
        )

    def validate_total(self, session, order_id, amount, status, collection=None):
        overrun = order_overrun(session, order_id, amount, status, collection)
        if overrun is None:
            return True
        QMessageBox.warning(
            self,
            "Importe superior al pedido",
            "Los cobros superarían el importe del pedido.\n\n"
            f"Pedido: {money(overrun['order'])}\n"
            f"Total resultante: {money(overrun['total'])}",
        )
        return False

    def new(self):
        project_id = self.choose_project()
        if project_id is None:
            return
        session = get_session()
        try:
            orders = self.project_orders(project_id, session)
            if not orders:
                QMessageBox.warning(self, "No hay pedidos", "Este proyecto no tiene pedidos.")
                return
            dialog = CollectionDialog(self, orders=orders)
            if dialog.exec() != QDialog.Accepted:
                return
            data = dialog.get_data()
            if not self.validate_total(session, data["order_id"], data["amount"], data["status"]):
                return
            session.add(Collection(**data))
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
            collection = session.get(Collection, selected["id"])
            orders = self.project_orders(selected["project_id"], session)
            dialog = CollectionDialog(self, orders=orders, collection=collection)
            if dialog.exec() != QDialog.Accepted:
                return
            data = dialog.get_data()
            if not self.validate_total(
                session, data["order_id"], data["amount"], data["status"], collection
            ):
                return
            for key, value in data.items():
                setattr(collection, key, value)
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", str(error))
        finally:
            session.close()
        self.refresh()

    def invoice(self):
        selected = self.selected()
        if not selected:
            return
        if generate_invoice(self, selected["id"]):
            self.refresh()

    def delete(self):
        selected = self.selected()
        if not selected:
            return
        if block_if_invoiced(self, "este cobro", collection_id=selected["id"]):
            return
        answer = QMessageBox.question(
            self,
            "Eliminar cobro",
            f"¿Eliminar '{selected['concept']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        session = get_session()
        try:
            collection = session.get(Collection, selected["id"])
            if collection:
                session.delete(collection)
                session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", str(error))
        finally:
            session.close()
        self.refresh()
