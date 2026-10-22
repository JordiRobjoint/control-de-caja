from PySide6.QtCore import QDate
from services.cashflow import money as _money
from services import invoices
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


class CollectionDialog(QDialog):

    def __init__(
        self,
        parent=None,
        orders=None,
        collection=None,
    ):
        super().__init__(parent)

        self.orders = orders or []
        self.collection = collection

        self.setWindowTitle(
            "Nuevo cobro"
            if collection is None
            else "Editar cobro"
        )

        self.setMinimumWidth(550)

        self.setup_ui()

        if self.collection is not None:
            self.load_collection_data()

    # ==========================================================
    # INTERFAZ
    # ==========================================================

    def setup_ui(self):

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(20)

        title = QLabel(
            "Nuevo cobro"
            if self.collection is None
            else "Editar cobro"
        )
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            "Define el hito de cobro asociado a un pedido."
        )
        subtitle.setObjectName("dialogSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(25)

        # Pedido
        self.order_combo = QComboBox()

        for order in self.orders:
            self.order_combo.addItem(
                f"{order.order_number}  ·  {_money(order.amount)}",
                order.id,
            )

        self.order_combo.currentIndexChanged.connect(
            self.update_amount
        )

        form.addRow(
            "Pedido *",
            self.order_combo,
        )

        # Concepto
        self.concept = QLineEdit()
        self.concept.setPlaceholderText(
            "Ej. Anticipo / Pago final"
        )

        form.addRow(
            "Concepto *",
            self.concept,
        )

        # Tipo
        self.calculation_type = QComboBox()

        self.calculation_type.addItems([
            "Porcentaje",
            "Importe fijo",
        ])

        self.calculation_type.currentTextChanged.connect(
            self.calculation_type_changed
        )

        form.addRow(
            "Tipo de cálculo",
            self.calculation_type,
        )

        # Porcentaje
        self.percentage = QDoubleSpinBox()
        self.percentage.setRange(0, 100)
        self.percentage.setDecimals(2)
        self.percentage.setSuffix(" %")

        self.percentage.valueChanged.connect(
            self.update_amount
        )

        form.addRow(
            "Porcentaje",
            self.percentage,
        )

        # Importe
        self.amount = QDoubleSpinBox()
        self.amount.setMaximum(999_999_999)
        self.amount.setDecimals(2)
        self.amount.setSuffix(" €")
        self.amount.setGroupSeparatorShown(True)

        form.addRow(
            "Importe *",
            self.amount,
        )

        # Fecha prevista
        self.expected_date = QDateEdit()
        self.expected_date.setCalendarPopup(True)
        self.expected_date.setDisplayFormat(
            "dd/MM/yyyy"
        )
        self.expected_date.setDate(
            QDate.currentDate()
        )

        form.addRow(
            "Fecha prevista",
            self.expected_date,
        )

        # Estado
        self.status = QComboBox()

        self.status.addItems([
            "Previsto",
            "Facturado",
            "Cobrado",
            "Cancelado",
        ])

        self.status.currentTextChanged.connect(
            self.status_changed
        )

        form.addRow(
            "Estado",
            self.status,
        )

        # Factura
        self.invoice_number = QLineEdit()

        self.invoice_number.setPlaceholderText(
            "Ej. FV-2026-001"
        )

        form.addRow(
            "Nº factura",
            self.invoice_number,
        )

        # Fecha factura
        self.invoice_date = QDateEdit()
        self.invoice_date.setCalendarPopup(True)
        self.invoice_date.setDisplayFormat(
            "dd/MM/yyyy"
        )
        self.invoice_date.setDate(
            QDate.currentDate()
        )

        form.addRow(
            "Fecha factura",
            self.invoice_date,
        )

        # Fecha cobro
        self.collection_date = QDateEdit()
        self.collection_date.setCalendarPopup(True)
        self.collection_date.setDisplayFormat(
            "dd/MM/yyyy"
        )
        self.collection_date.setDate(
            QDate.currentDate()
        )

        form.addRow(
            "Fecha real de cobro",
            self.collection_date,
        )

        # Notas
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(90)

        self.notes.setPlaceholderText(
            "Observaciones..."
        )

        form.addRow(
            "Notas",
            self.notes,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save
            | QDialogButtonBox.Cancel
        )

        buttons.button(
            QDialogButtonBox.Save
        ).setText("Guardar cobro")

        buttons.button(
            QDialogButtonBox.Cancel
        ).setText("Cancelar")

        buttons.accepted.connect(
            self.validate
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

        self.calculation_type_changed(
            self.calculation_type.currentText()
        )

        self.status_changed(
            self.status.currentText()
        )

    # ==========================================================
    # TIPO DE CÁLCULO
    # ==========================================================

    def calculation_type_changed(
        self,
        calculation_type,
    ):

        is_percentage = (
            calculation_type == "Porcentaje"
        )

        self.percentage.setEnabled(
            is_percentage
        )

        self.amount.setReadOnly(
            is_percentage
        )

        if is_percentage:
            self.update_amount()

    # ==========================================================
    # CALCULAR IMPORTE
    # ==========================================================

    def update_amount(self):

        if (
            self.calculation_type.currentText()
            != "Porcentaje"
        ):
            return

        index = self.order_combo.currentIndex()

        if index < 0:
            self.amount.setValue(0)
            return

        order_id = self.order_combo.currentData()

        order = next(
            (
                order
                for order in self.orders
                if order.id == order_id
            ),
            None,
        )

        if order is None:
            self.amount.setValue(0)
            return

        calculated_amount = (
            order.amount
            * self.percentage.value()
            / 100
        )

        self.amount.setValue(
            calculated_amount
        )

    # ==========================================================
    # ESTADO
    # ==========================================================

    def status_changed(self, status):

        # Solo tiene sentido introducir fecha real
        # cuando el dinero ya se ha cobrado.
        self.collection_date.setEnabled(
            status == "Cobrado"
        )

    # ==========================================================
    # CARGAR DATOS
    # ==========================================================

    def load_collection_data(self):

        collection = self.collection

        index = self.order_combo.findData(
            collection.order_id
        )

        if index >= 0:
            self.order_combo.setCurrentIndex(
                index
            )

        self.concept.setText(
            collection.concept or ""
        )

        type_index = (
            self.calculation_type.findText(
                collection.calculation_type
            )
        )

        if type_index >= 0:
            self.calculation_type.setCurrentIndex(
                type_index
            )

        self.percentage.setValue(
            collection.percentage or 0
        )

        self.amount.setValue(
            collection.amount or 0
        )

        if collection.expected_date:
            self.expected_date.setDate(
                QDate(
                    collection.expected_date.year,
                    collection.expected_date.month,
                    collection.expected_date.day,
                )
            )

        status_index = self.status.findText(
            collection.status
        )

        if status_index >= 0:
            self.status.setCurrentIndex(
                status_index
            )

        self.invoice_number.setText(
            collection.invoice_number or ""
        )

        if collection.invoice_date:
            self.invoice_date.setDate(
                QDate(
                    collection.invoice_date.year,
                    collection.invoice_date.month,
                    collection.invoice_date.day,
                )
            )

        if collection.collection_date:
            self.collection_date.setDate(
                QDate(
                    collection.collection_date.year,
                    collection.collection_date.month,
                    collection.collection_date.day,
                )
            )

        self.notes.setPlainText(
            collection.notes or ""
        )

        self.calculation_type_changed(
            self.calculation_type.currentText()
        )

        self.status_changed(
            self.status.currentText()
        )

        if invoices.is_invoiced(collection):
            self.lock_invoiced_fields()

    # ==========================================================
    # COBRO FACTURADO
    # ==========================================================

    def lock_invoiced_fields(self):
        """
        Con la factura emitida, lo que figura en ella no se puede cambiar.
        Se puede seguir actualizando el estado, las fechas de previsión y
        cobro y las notas.
        """
        # Al cargar, un cobro por porcentaje recalcula el importe con el
        # pedido actual: se restaura el importe facturado.
        self.amount.setValue(self.collection.amount or 0)

        locked = [
            self.order_combo,
            self.concept,
            self.calculation_type,
            self.percentage,
            self.amount,
        ]
        number = self.collection.invoice_number.strip()
        if self.invoice_number_taken(number):
            # Número repetido (datos antiguos): se deja corregir el número
            # y la fecha de factura; lo demás queda bloqueado.
            text = (
                f"La factura {number} está repetida en otro cobro: corrige aquí "
                "el número (y la fecha si hace falta). El pedido, el concepto y "
                "el importe no se pueden modificar."
            )
        else:
            locked += [self.invoice_number, self.invoice_date]
            text = (
                f"Factura {number} emitida: el pedido, el concepto, el importe "
                "y los datos de la factura no se pueden modificar. Para anularla, "
                "marca el cobro como «Cancelado» y pide a la gestoría la factura "
                "rectificativa."
            )
        for widget in locked:
            widget.setEnabled(False)

        # Volver a "Previsto" la desbloquearía: no se ofrece.
        previsto = self.status.findText("Previsto")
        if previsto >= 0 and self.status.currentText() != "Previsto":
            self.status.removeItem(previsto)

        notice = QLabel(text)
        notice.setObjectName("dialogSubtitle")
        notice.setWordWrap(True)
        self.layout().insertWidget(2, notice)

    # ==========================================================
    # VALIDAR
    # ==========================================================

    def validate(self):

        if self.order_combo.currentIndex() < 0:
            QMessageBox.warning(
                self,
                "Pedido necesario",
                "Selecciona un pedido.",
            )
            return

        if not self.concept.text().strip():
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Introduce el concepto del cobro.",
            )
            return

        if (
            self.calculation_type.currentText()
            == "Porcentaje"
            and self.percentage.value() <= 0
        ):
            QMessageBox.warning(
                self,
                "Porcentaje incorrecto",
                "El porcentaje debe ser superior a 0.",
            )
            return

        if self.amount.value() <= 0:
            QMessageBox.warning(
                self,
                "Importe incorrecto",
                "El importe debe ser superior a 0 €.",
            )
            return

        number = self.invoice_number.text().strip()
        if number and self.invoice_number_taken(number):
            QMessageBox.warning(
                self,
                "Número de factura repetido",
                f"La factura {number} ya está asignada a otro cobro.\n\n"
                "Cada factura debe tener un número distinto.",
            )
            return

        self.accept()

    def invoice_number_taken(self, number):
        from database.database import get_session
        from services.invoices import invoice_number_in_use

        exclude = self.collection.id if self.collection is not None else None
        session = get_session()
        try:
            return invoice_number_in_use(session, number, exclude)
        finally:
            session.close()

    # ==========================================================
    # OBTENER DATOS
    # ==========================================================

    def get_data(self):

        is_collected = (
            self.status.currentText()
            == "Cobrado"
        )

        return {
            "order_id":
                self.order_combo.currentData(),

            "concept":
                self.concept.text().strip(),

            "calculation_type":
                self.calculation_type.currentText(),

            "percentage":
                (
                    self.percentage.value()
                    if self.calculation_type.currentText()
                    == "Porcentaje"
                    else None
                ),

            "amount":
                self.amount.value(),

            "expected_date":
                self.expected_date.date().toPython(),

            "status":
                self.status.currentText(),

            "invoice_number":
                self.invoice_number.text().strip()
                or None,

            "invoice_date":
                self.invoice_date.date().toPython()
                if self.invoice_number.text().strip()
                else None,

            "collection_date":
                self.collection_date.date().toPython()
                if is_collected
                else None,

            "notes":
                self.notes.toPlainText().strip()
                or None,
        }