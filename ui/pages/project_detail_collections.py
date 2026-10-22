"""Pestaña Cobros de la ficha de proyecto."""

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

from services.cashflow import money as _money, order_overrun
from database.database import get_session
from database.models import Collection, Order
from ui.pages.dialogs.collection_dialog import CollectionDialog
from ui.pages.dialogs.invoice_dialog import block_if_invoiced, generate_invoice
from ui.table_utils import fills


class CollectionsTabMixin:
    """Pestaña Cobros de la ficha de proyecto (se mezcla en ProjectDetailPage)."""

    # ==========================================================
    # COBROS
    # ==========================================================

    def create_collections_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Cobros")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        edit_button = QPushButton("Editar")
        edit_button.setObjectName("secondaryButton")
        edit_button.setCursor(Qt.PointingHandCursor)
        edit_button.clicked.connect(self.edit_collection)

        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self.delete_collection)

        new_button = QPushButton("+  Nuevo cobro")
        new_button.setObjectName("primaryButton")
        new_button.setCursor(Qt.PointingHandCursor)
        new_button.clicked.connect(self.new_collection)

        invoice_button = QPushButton("🧾  Factura")
        invoice_button.setObjectName("secondaryButton")
        invoice_button.setCursor(Qt.PointingHandCursor)
        invoice_button.setToolTip("Generar o abrir la factura del cobro seleccionado")
        invoice_button.clicked.connect(self.invoice_collection)

        header.addWidget(invoice_button)
        header.addWidget(edit_button)
        header.addWidget(delete_button)
        header.addWidget(new_button)
        layout.addLayout(header)

        self.collections_table = QTableWidget()
        self.collections_table.setColumnCount(8)
        self.collections_table.setHorizontalHeaderLabels([
            "Pedido", "Concepto", "%", "Importe (base)",
            "Fecha prevista", "Estado", "Nº factura", "Fecha cobro",
        ])
        self.collections_table.verticalHeader().setVisible(False)
        self.collections_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.collections_table.setSelectionMode(QTableWidget.SingleSelection)
        self.collections_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.collections_table.setShowGrid(False)
        self.collections_table.setAlternatingRowColors(True)
        self.collections_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.collections_table.doubleClicked.connect(self.edit_collection)

        layout.addWidget(self.collections_table)
        return widget

    # ==========================================================
    # CARGAR COBROS
    # ==========================================================

    @fills("collections_table")
    def load_collections(self):
        if self.project_id is None:
            return

        session = get_session()
        try:
            collections = (
                session.query(Collection)
                .join(Order)
                .filter(Order.project_id == self.project_id)
                .order_by(
                    Collection.expected_date.asc(),
                    Collection.id.asc(),
                )
                .all()
            )

            self.collections = collections
            self.collections_table.setRowCount(len(collections))
            total_collected = 0.0

            for row, collection in enumerate(collections):
                if collection.status == "Cobrado":
                    total_collected += collection.amount or 0

                expected_date = (
                    collection.expected_date.strftime("%d/%m/%Y")
                    if collection.expected_date else "—"
                )
                collection_date = (
                    collection.collection_date.strftime("%d/%m/%Y")
                    if collection.collection_date else "—"
                )
                percentage = (
                    f"{collection.percentage:.2f} %"
                    if collection.percentage is not None else "—"
                )

                values = [
                    collection.order.order_number,
                    collection.concept,
                    percentage,
                    _money(collection.amount),
                    expected_date,
                    collection.status,
                    collection.invoice_number or "—",
                    collection_date,
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 3:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.collections_table.setItem(row, column, item)

            self.collections_table.clearSelection()
            self.collected_value.setText(_money(total_collected))

        finally:
            session.close()

    # ==========================================================
    # NUEVO COBRO
    # ==========================================================

    def new_collection(self):
        if self.project_id is None:
            return

        if not self.orders:
            QMessageBox.warning(
                self,
                "No hay pedidos",
                "Antes de crear un cobro debes crear al menos un pedido.",
            )
            return

        dialog = CollectionDialog(self, orders=self.orders)

        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()

        if not self.validate_collection_total(
            data["order_id"],
            data["amount"],
            new_status=data["status"],
        ):
            return

        session = get_session()
        try:
            collection = Collection(
                order_id=data["order_id"],
                concept=data["concept"],
                calculation_type=data["calculation_type"],
                percentage=data["percentage"],
                amount=data["amount"],
                expected_date=data["expected_date"],
                status=data["status"],
                invoice_number=data["invoice_number"],
                invoice_date=data["invoice_date"],
                collection_date=data["collection_date"],
                notes=data["notes"],
            )
            session.add(collection)
            session.commit()

        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido guardar el cobro.\n\n{error}",
            )
            return

        finally:
            session.close()

        self.load_collections()

    # ==========================================================
    # EDITAR COBRO
    # ==========================================================

    def edit_collection(self):
        row = self.collections_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Selecciona un cobro",
                "Selecciona primero el cobro que quieres editar.",
            )
            return

        if row >= len(self.collections):
            return

        selected = self.collections[row]
        session = get_session()

        try:
            collection = session.get(Collection, selected.id)

            if collection is None:
                return

            dialog = CollectionDialog(
                self,
                orders=self.orders,
                collection=collection,
            )

            if dialog.exec() != QDialog.Accepted:
                return

            data = dialog.get_data()

            if not self.validate_collection_total(
                data["order_id"],
                data["amount"],
                collection=collection,
                new_status=data["status"],
            ):
                return

            collection.order_id = data["order_id"]
            collection.concept = data["concept"]
            collection.calculation_type = data["calculation_type"]
            collection.percentage = data["percentage"]
            collection.amount = data["amount"]
            collection.expected_date = data["expected_date"]
            collection.status = data["status"]
            collection.invoice_number = data["invoice_number"]
            collection.invoice_date = data["invoice_date"]
            collection.collection_date = data["collection_date"]
            collection.notes = data["notes"]

            session.commit()

        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido modificar el cobro.\n\n{error}",
            )
            return

        finally:
            session.close()

        self.load_collections()

    # ==========================================================
    # FACTURA
    # ==========================================================

    def invoice_collection(self):
        row = self.collections_table.currentRow()

        if row < 0 or row >= len(self.collections):
            QMessageBox.warning(
                self,
                "Selecciona un cobro",
                "Selecciona primero el cobro que quieres facturar.",
            )
            return

        if generate_invoice(self, self.collections[row].id):
            self.load_collections()

    # ==========================================================
    # ELIMINAR COBRO
    # ==========================================================

    def delete_collection(self):
        row = self.collections_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Selecciona un cobro",
                "Selecciona el cobro que quieres eliminar.",
            )
            return

        if row >= len(self.collections):
            return

        selected = self.collections[row]

        if block_if_invoiced(self, "este cobro", collection_id=selected.id):
            return

        answer = QMessageBox.question(
            self,
            "Eliminar cobro",
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
            collection = session.get(Collection, selected.id)

            if collection is None:
                return

            session.delete(collection)
            session.commit()

        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido eliminar el cobro.\n\n{error}",
            )
            return

        finally:
            session.close()

        self.load_collections()

    # ==========================================================
    # VALIDAR TOTAL DEL PEDIDO
    # ==========================================================

    def validate_collection_total(
        self,
        order_id,
        new_amount,
        collection=None,
        new_status="Previsto",
    ):
        session = get_session()
        try:
            overrun = order_overrun(
                session, order_id, new_amount, new_status, collection
            )
        finally:
            session.close()

        if overrun is None:
            return True

        QMessageBox.warning(
            self,
            "Importe superior al pedido",
            (
                "Los cobros asociados a este pedido superarían "
                "su importe.\n\n"
                f"Importe pedido: {_money(overrun['order'])}\n"
                f"Cobros existentes: {_money(overrun['others'])}\n"
                f"Nuevo cobro: {_money(new_amount)}\n"
                f"Total resultante: {_money(overrun['total'])}"
            ),
        )
        return False
