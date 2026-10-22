from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

# ==============================================================
# FORMULARIO PEDIDO
# ==============================================================

class OrderDialog(QDialog):

    def __init__(
        self,
        parent=None,
        order=None,
    ):

        super().__init__(parent)

        self.order = order

        if order is None:
            self.setWindowTitle(
                "Nuevo pedido"
            )
        else:
            self.setWindowTitle(
                "Editar pedido"
            )

        self.setMinimumWidth(520)

        self.setup_ui()

        if self.order is not None:
            self.load_order_data()

    # ==========================================================
    # INTERFAZ
    # ==========================================================

    def setup_ui(self):

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            25,
            30,
            25,
        )

        layout.setSpacing(20)

        title_text = (
            "Nuevo pedido"
            if self.order is None
            else "Editar pedido"
        )

        title = QLabel(title_text)
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            "Introduce los datos principales "
            "del pedido del cliente."
        )

        subtitle.setObjectName(
            "dialogSubtitle"
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()

        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(25)

        # Número pedido

        self.order_number = QLineEdit()

        self.order_number.setPlaceholderText(
            "Ej. PED-2026-015"
        )

        form.addRow(
            "Nº pedido *",
            self.order_number,
        )

        # Descripción

        self.description = QLineEdit()

        self.description.setPlaceholderText(
            "Ej. Programación robótica"
        )

        form.addRow(
            "Descripción",
            self.description,
        )

        # Fecha

        self.order_date = QDateEdit()

        self.order_date.setCalendarPopup(
            True
        )

        self.order_date.setDisplayFormat(
            "dd/MM/yyyy"
        )

        self.order_date.setDate(
            QDate.currentDate()
        )

        form.addRow(
            "Fecha del pedido",
            self.order_date,
        )

        # Importe

        self.amount = QDoubleSpinBox()

        self.amount.setMaximum(
            999_999_999
        )

        self.amount.setDecimals(2)

        self.amount.setSuffix(" €")

        self.amount.setGroupSeparatorShown(
            True
        )

        form.addRow(
            "Importe base sin IVA *",
            self.amount,
        )

        # Estado

        self.status = QComboBox()

        self.status.addItems([
            "Pendiente",
            "Aceptado",
            "En curso",
            "Finalizado",
            "Cancelado",
        ])

        form.addRow(
            "Estado",
            self.status,
        )

        # Notas

        self.notes = QTextEdit()

        self.notes.setMaximumHeight(100)

        self.notes.setPlaceholderText(
            "Observaciones del pedido..."
        )

        form.addRow(
            "Notas",
            self.notes,
        )

        layout.addLayout(form)

        # Botones

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save
            | QDialogButtonBox.Cancel
        )

        buttons.button(
            QDialogButtonBox.Save
        ).setText(
            "Guardar pedido"
        )

        buttons.button(
            QDialogButtonBox.Cancel
        ).setText(
            "Cancelar"
        )

        buttons.accepted.connect(
            self.validate
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

    # ==========================================================
    # CARGAR PEDIDO
    # ==========================================================

    def load_order_data(self):

        order = self.order

        self.order_number.setText(
            order.order_number or ""
        )

        self.description.setText(
            order.description or ""
        )

        if order.order_date:

            self.order_date.setDate(
                QDate(
                    order.order_date.year,
                    order.order_date.month,
                    order.order_date.day,
                )
            )

        self.amount.setValue(
            order.amount or 0
        )

        status_index = (
            self.status.findText(
                order.status
            )
        )

        if status_index >= 0:

            self.status.setCurrentIndex(
                status_index
            )

        self.notes.setPlainText(
            order.notes or ""
        )

    # ==========================================================
    # VALIDAR
    # ==========================================================

    def validate(self):

        if not (
            self.order_number
            .text()
            .strip()
        ):

            QMessageBox.warning(
                self,
                "Datos incompletos",
                (
                    "Introduce el número "
                    "del pedido."
                ),
            )

            return

        if self.amount.value() <= 0:

            QMessageBox.warning(
                self,
                "Importe incorrecto",
                (
                    "El importe del pedido "
                    "debe ser superior a 0 €."
                ),
            )

            return

        self.accept()

    # ==========================================================
    # DATOS
    # ==========================================================

    def get_data(self):

        return {
            "order_number":
                self.order_number
                .text()
                .strip(),

            "description":
                self.description
                .text()
                .strip()
                or None,

            "order_date":
                self.order_date
                .date()
                .toPython(),

            "amount":
                self.amount.value(),

            "status":
                self.status.currentText(),

            "notes":
                self.notes
                .toPlainText()
                .strip()
                or None,
        }