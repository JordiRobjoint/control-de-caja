"""Pestaña Pedidos de la ficha de proyecto."""

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
from database.models import Order
from ui.pages.dialogs.invoice_dialog import block_if_invoiced
from ui.pages.dialogs.order_dialog import OrderDialog
from ui.table_utils import fills


class OrdersTabMixin:
    """Pestaña Pedidos de la ficha de proyecto (se mezcla en ProjectDetailPage)."""

    # ==========================================================
    # PEDIDOS
    # ==========================================================

    def create_orders_tab(self):

        widget = QWidget()

        layout = QVBoxLayout(widget)

        layout.setContentsMargins(
            25,
            25,
            25,
            25,
        )

        layout.setSpacing(18)

        # Cabecera

        header = QHBoxLayout()

        title = QLabel("Pedidos")
        title.setObjectName("panelTitle")

        header.addWidget(title)
        header.addStretch()

        edit_button = QPushButton(
            "Editar"
        )

        edit_button.setObjectName(
            "secondaryButton"
        )

        edit_button.setCursor(
            Qt.PointingHandCursor
        )

        edit_button.clicked.connect(
            self.edit_order
        )

        delete_button = QPushButton(
            "Eliminar"
        )

        delete_button.setObjectName(
            "dangerButton"
        )

        delete_button.setCursor(
            Qt.PointingHandCursor
        )

        delete_button.clicked.connect(
            self.delete_order
        )

        new_button = QPushButton(
            "+  Nuevo pedido"
        )

        new_button.setObjectName(
            "primaryButton"
        )

        new_button.setCursor(
            Qt.PointingHandCursor
        )

        new_button.clicked.connect(
            self.new_order
        )

        header.addWidget(edit_button)
        header.addWidget(delete_button)
        header.addWidget(new_button)

        layout.addLayout(header)

        # Tabla

        self.orders_table = QTableWidget()

        self.orders_table.setColumnCount(5)

        self.orders_table.setHorizontalHeaderLabels([
            "Nº pedido",
            "Descripción",
            "Fecha",
            "Estado",
            "Importe",
        ])

        self.orders_table.verticalHeader().setVisible(
            False
        )

        self.orders_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )

        self.orders_table.setSelectionMode(
            QTableWidget.SingleSelection
        )

        self.orders_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.orders_table.setShowGrid(False)

        self.orders_table.setAlternatingRowColors(
            True
        )

        self.orders_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        self.orders_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )

        self.orders_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,
        )

        self.orders_table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents,
        )

        self.orders_table.horizontalHeader().setSectionResizeMode(
            4,
            QHeaderView.ResizeToContents,
        )

        self.orders_table.doubleClicked.connect(
            self.edit_order
        )

        layout.addWidget(
            self.orders_table
        )

        return widget

    # ==========================================================
    # CARGAR PEDIDOS
    # ==========================================================

    @fills("orders_table")
    def load_orders(self):

        if self.project_id is None:
            return

        session = get_session()

        try:

            orders = (
                session.query(Order)
                .filter(
                    Order.project_id
                    == self.project_id
                )
                .order_by(
                    Order.order_date.desc(),
                    Order.id.desc(),
                )
                .all()
            )

            self.orders = orders

            self.orders_table.setRowCount(
                len(orders)
            )

            total_contracted = 0.0

            for row, order in enumerate(
                orders
            ):

                # Un pedido cancelado no cuenta como contratado.
                if order.status != "Cancelado":
                    total_contracted += (
                        order.amount or 0
                    )

                date_text = (
                    order.order_date.strftime(
                        "%d/%m/%Y"
                    )
                    if order.order_date
                    else "—"
                )

                values = [
                    order.order_number,
                    order.description or "—",
                    date_text,
                    order.status,
                    _money(order.amount),
                ]

                for column, value in enumerate(
                    values
                ):

                    item = QTableWidgetItem(
                        str(value)
                    )

                    if column == 4:

                        item.setTextAlignment(
                            Qt.AlignRight
                            | Qt.AlignVCenter
                        )

                    self.orders_table.setItem(
                        row,
                        column,
                        item,
                    )

            self.orders_table.clearSelection()

            # ----------------------------------------------
            # TARJETAS
            # ----------------------------------------------

            self.total_contracted = total_contracted

            self.contracted_value.setText(
                _money(total_contracted)
            )


        finally:
            session.close()

    # ==========================================================
    # NUEVO PEDIDO
    # ==========================================================

    def new_order(self):

        if self.project_id is None:
            return

        dialog = OrderDialog(self)

        if (
            dialog.exec()
            != QDialog.Accepted
        ):
            return

        data = dialog.get_data()

        session = get_session()

        try:

            order = Order(
                project_id=self.project_id,
                order_number=data[
                    "order_number"
                ],
                description=data[
                    "description"
                ],
                order_date=data[
                    "order_date"
                ],
                amount=data["amount"],
                status=data["status"],
                notes=data["notes"],
            )

            session.add(order)
            session.commit()

        except Exception as error:

            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                (
                    "No se ha podido guardar "
                    "el pedido."
                    f"\n\n{error}"
                ),
            )

            return

        finally:
            session.close()

        self.load_orders()

    # ==========================================================
    # EDITAR PEDIDO
    # ==========================================================

    def edit_order(self):

        row = (
            self.orders_table.currentRow()
        )

        if row < 0:

            QMessageBox.warning(
                self,
                "Selecciona un pedido",
                (
                    "Selecciona primero el pedido "
                    "que quieres editar."
                ),
            )

            return

        if row >= len(self.orders):
            return

        selected_order = self.orders[row]

        session = get_session()

        try:

            order = session.get(
                Order,
                selected_order.id,
            )

            if order is None:
                return

            dialog = OrderDialog(
                self,
                order=order,
            )

            if (
                dialog.exec()
                != QDialog.Accepted
            ):
                return

            data = dialog.get_data()

            order.order_number = data[
                "order_number"
            ]

            order.description = data[
                "description"
            ]

            order.order_date = data[
                "order_date"
            ]

            order.amount = data[
                "amount"
            ]

            order.status = data[
                "status"
            ]

            order.notes = data[
                "notes"
            ]

            session.commit()

        except Exception as error:

            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                (
                    "No se ha podido modificar "
                    "el pedido."
                    f"\n\n{error}"
                ),
            )

            return

        finally:
            session.close()

        self.load_orders()

    # ==========================================================
    # ELIMINAR PEDIDO
    # ==========================================================

    def delete_order(self):

        row = (
            self.orders_table.currentRow()
        )

        if row < 0:

            QMessageBox.warning(
                self,
                "Selecciona un pedido",
                (
                    "Selecciona primero el pedido "
                    "que quieres eliminar."
                ),
            )

            return

        if row >= len(self.orders):
            return

        selected_order = self.orders[row]

        if block_if_invoiced(self, "este pedido", order_id=selected_order.id):
            return

        answer = QMessageBox.question(
            self,
            "Eliminar pedido",
            (
                "¿Seguro que quieres eliminar "
                f"el pedido "
                f"'{selected_order.order_number}'?"
                "\n\n"
                "Esta acción no se puede deshacer."
            ),
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        session = get_session()

        try:

            order = session.get(
                Order,
                selected_order.id,
            )

            if order is None:
                return

            session.delete(order)
            session.commit()

        except Exception as error:

            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                (
                    "No se ha podido eliminar "
                    "el pedido."
                    f"\n\n{error}"
                ),
            )

            return

        finally:
            session.close()

        self.load_orders()
