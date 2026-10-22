from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.database import get_session
from services import docscan, receipts, scanner
from services.cashflow import add_money, get_setting, money, round_money
from ui.pages.dialogs.phone_dialog import receive_from_phone
from ui.pages.gastos_generales import GENERAL_CATEGORIES


PROJECT_CATEGORIES = [
    "Hotel",
    "Vuelo",
    "Coche de alquiler",
    "Combustible",
    "Peajes",
    "Dietas",
    "Material",
    "Subcontratación",
    "Otros",
]


class ReceiptReader(QThread):
    """Lee el ticket en segundo plano para no congelar la ventana."""

    succeeded = Signal(dict)
    failed = Signal(str)

    # Mantiene vivos los hilos aunque el diálogo se cierre antes de
    # que terminen (destruir un QThread en marcha cierra la aplicación).
    running = set()

    def __init__(self, path, categories, company):
        super().__init__()
        self.path = path
        self.categories = categories
        self.company = company
        ReceiptReader.running.add(self)
        self.finished.connect(lambda: ReceiptReader.running.discard(self))

    def run(self):
        try:
            data = receipts.read_receipt(
                self.path, self.categories, company=self.company
            )
        except receipts.ReceiptError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"Error inesperado al leer el documento:\n{error}")
        else:
            self.succeeded.emit(data)


class ExpenseDialog(QDialog):

    def __init__(self, parent=None, expense=None, general=None):
        super().__init__(parent)

        self.expense = expense
        # Gasto general (sin proyecto): factura suelta de la empresa.
        self.general = (
            general if general is not None
            else expense is not None and expense.project_id is None
        )

        # Documento enlazado: archivado (ruta guardada en el gasto) o
        # recién elegido/escaneado, que se archiva al guardar.
        self.document_file = expense.document_file if expense else None
        self.pending_document = None
        # Foto original de un escaneo, por si el recorte no convence.
        self.original_photo = None
        self.scan_note = ""
        # Nombre corto para el archivo propuesto al leer el documento.
        self.file_label = ""
        self.reader = None
        self.expected_total = None

        self.setAcceptDrops(True)

        self.setWindowTitle(
            "Nuevo gasto" if expense is None else "Editar gasto"
        )
        self.setMinimumWidth(620)

        self.setup_ui()

        if self.expense is not None:
            self.load_expense_data()

        self.fit_to_screen()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 20)
        layout.setSpacing(14)

        title = QLabel(
            "Nuevo gasto" if self.expense is None else "Editar gasto"
        )
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            "Factura o ticket de la empresa, sin proyecto. Los gastos "
            "mensuales van en Gastos generales."
            if self.general else
            "Registra un gasto único o un coste recurrente mensual."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("dialogSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Título y botones quedan fijos; el resto se desplaza si la
        # pantalla no es lo bastante alta (portátiles, escalado 125 %).
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content.setObjectName("expenseContent")
        self.content.setStyleSheet(
            "#expenseContent { background: transparent; }"
        )
        self.scroll.setWidget(self.content)
        self.scroll.viewport().setStyleSheet("background: transparent;")

        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)

        content_layout.addWidget(self.create_document_bar())

        self.form = QFormLayout()
        self.form.setVerticalSpacing(11)
        self.form.setHorizontalSpacing(20)
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # =========================================================
        # DATOS GENERALES
        # =========================================================

        self.category = QComboBox()
        self.category.addItems(
            GENERAL_CATEGORIES if self.general else PROJECT_CATEGORIES
        )
        self.form.addRow("Categoría *", self.category)

        self.concept = QLineEdit()
        self.concept.setPlaceholderText("Ej. Hotel proyecto Vigo")
        self.form.addRow("Concepto *", self.concept)

        self.supplier = QLineEdit()
        self.supplier.setPlaceholderText("Ej. Hotel / proveedor")
        self.form.addRow("Proveedor", self.supplier)

        # =========================================================
        # TIPO DE PAGO
        # =========================================================

        self.payment_type = QComboBox()
        self.payment_type.addItems(
            ["Único"] if self.general else ["Único", "Mensual"]
        )
        self.payment_type.currentTextChanged.connect(
            self.payment_type_changed
        )
        self.form.addRow("Tipo de pago *", self.payment_type)

        # =========================================================
        # PAGO ÚNICO
        # =========================================================

        self.expense_date = QDateEdit()
        self.expense_date.setCalendarPopup(True)
        self.expense_date.setDisplayFormat("dd/MM/yyyy")
        self.expense_date.setDate(QDate.currentDate())

        self.expense_date_label = QLabel("Fecha")
        self.form.addRow(
            self.expense_date_label,
            self.expense_date,
        )

        # =========================================================
        # PAGO MENSUAL
        # =========================================================

        self.recurrence_start = QDateEdit()
        self.recurrence_start.setCalendarPopup(True)
        self.recurrence_start.setDisplayFormat("dd/MM/yyyy")
        self.recurrence_start.setDate(QDate.currentDate())

        self.recurrence_start_label = QLabel("Desde")

        self.recurrence_end = QDateEdit()
        self.recurrence_end.setCalendarPopup(True)
        self.recurrence_end.setDisplayFormat("dd/MM/yyyy")
        self.recurrence_end.setDate(
            QDate.currentDate().addMonths(1)
        )

        self.recurrence_end_label = QLabel("Hasta")

        self.recurrence_row = QHBoxLayout()
        self.recurrence_row.setSpacing(12)
        self.recurrence_row.addWidget(self.recurrence_start, 1)
        self.recurrence_row.addWidget(self.recurrence_end_label)
        self.recurrence_row.addWidget(self.recurrence_end, 1)
        self.form.addRow(
            self.recurrence_start_label,
            self.recurrence_row,
        )

        # =========================================================
        # IMPORTES
        # =========================================================

        self.base_amount = QDoubleSpinBox()
        self.base_amount.setMaximum(999_999_999)
        self.base_amount.setDecimals(2)
        self.base_amount.setSuffix(" €")
        self.base_amount.setGroupSeparatorShown(True)
        self.base_amount.valueChanged.connect(
            self.calculate_totals
        )

        self.base_label = QLabel("Base imponible *")

        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0, 100)
        self.vat_rate.setDecimals(2)
        self.vat_rate.setSuffix(" %")
        self.vat_rate.setValue(21.0)
        self.vat_rate.valueChanged.connect(
            self.calculate_totals
        )
        self.vat_rate_label = QLabel("IVA")

        self.vat_amount = QDoubleSpinBox()
        self.vat_amount.setMaximum(999_999_999)
        self.vat_amount.setDecimals(2)
        self.vat_amount.setSuffix(" €")
        self.vat_amount.setReadOnly(True)

        self.vat_label = QLabel("Importe IVA")

        self.total_amount = QDoubleSpinBox()
        self.total_amount.setMaximum(999_999_999)
        self.total_amount.setDecimals(2)
        self.total_amount.setSuffix(" €")
        self.total_amount.setReadOnly(True)

        self.total_label = QLabel("Total")

        amounts = QGridLayout()
        amounts.setHorizontalSpacing(10)
        amounts.setVerticalSpacing(5)
        for column, (label, field) in enumerate((
            (self.base_label, self.base_amount),
            (self.vat_rate_label, self.vat_rate),
            (self.vat_label, self.vat_amount),
            (self.total_label, self.total_amount),
        )):
            field.setButtonSymbols(QDoubleSpinBox.NoButtons)
            field.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amounts.addWidget(label, 0, column)
            amounts.addWidget(field, 1, column)
            amounts.setColumnStretch(column, 1)
        self.form.addRow(amounts)

        # =========================================================
        # ESTADO
        # =========================================================

        self.status = QComboBox()
        self.status.addItems([
            "Previsto",
            "Pendiente",
            "Pagado",
            "Cancelado",
        ])
        self.status.currentTextChanged.connect(
            self.status_changed
        )

        self.payment_date = QDateEdit()
        self.payment_date.setCalendarPopup(True)
        self.payment_date.setDisplayFormat("dd/MM/yyyy")
        self.payment_date.setDate(QDate.currentDate())

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        status_row.addWidget(self.status, 1)
        status_row.addWidget(QLabel("Fecha de pago"))
        status_row.addWidget(self.payment_date, 1)
        self.form.addRow("Estado", status_row)

        self.invoice_reference = QLineEdit()
        self.invoice_reference.setPlaceholderText(
            "Nº factura, ticket o referencia"
        )
        self.form.addRow(
            "Factura / referencia",
            self.invoice_reference,
        )

        self.notes = QTextEdit()
        self.notes.setFixedHeight(80)
        self.notes.setPlaceholderText("Observaciones...")
        self.form.addRow("Notas", self.notes)

        content_layout.addLayout(self.form)
        content_layout.addStretch()
        layout.addWidget(self.scroll, 1)

        # =========================================================
        # BOTONES
        # =========================================================

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save |
            QDialogButtonBox.Cancel
        )

        buttons.button(
            QDialogButtonBox.Save
        ).setText("Guardar gasto")

        buttons.button(
            QDialogButtonBox.Cancel
        ).setText("Cancelar")

        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        self.payment_type_changed(
            self.payment_type.currentText()
        )

        self.status_changed(
            self.status.currentText()
        )

        self.calculate_totals()
        self.update_document_bar()

        for signal in (
            self.expense_date.dateChanged,
            self.recurrence_start.dateChanged,
            self.supplier.textChanged,
            self.payment_type.currentTextChanged,
        ):
            signal.connect(self.update_document_target)

    def fit_to_screen(self):
        """Tamaño justo para el contenido, sin pasar del alto de la pantalla."""
        screen = self.parent().screen() if self.parent() else self.screen()
        available = screen.availableGeometry().height()

        # El área desplazable no transmite el ancho de su contenido.
        margins = self.layout().contentsMargins()
        scrollbar = self.scroll.verticalScrollBar().sizeHint().width()
        self.setMinimumWidth(max(
            620,
            self.content.minimumSizeHint().width()
            + margins.left() + margins.right() + scrollbar,
        ))

        # Alto del contenido con ese ancho (los textos largos ocupan
        # más líneas cuanto más estrecho).
        width = (
            self.minimumWidth() - margins.left() - margins.right() - scrollbar
        )
        content_height = self.content.layout().totalHeightForWidth(width)
        if content_height < 0:
            content_height = self.content.sizeHint().height()

        chrome = self.sizeHint().height() - self.scroll.sizeHint().height()
        wanted = chrome + content_height + 16
        # Margen para la barra de título de Windows.
        self.resize(self.minimumWidth(), min(wanted, available - 50))

    # =============================================================
    # TICKET / FACTURA ESCANEADA
    # =============================================================

    def create_document_bar(self):
        bar = QFrame()
        bar.setObjectName("panel")
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(14, 10, 14, 10)
        bar_layout.setSpacing(6)

        row = QHBoxLayout()
        self.read_button = QPushButton("Leer ticket o factura…")
        self.scan_button = QPushButton("Escanear…")
        self.phone_button = QPushButton("Desde el móvil…")
        self.open_button = QPushButton("Ver documento")
        self.remove_button = QPushButton("Quitar")
        self.original_button = QPushButton("Usar foto original")
        for button in (
            self.read_button,
            self.scan_button,
            self.phone_button,
            self.open_button,
            self.remove_button,
            self.original_button,
        ):
            button.setObjectName("secondaryButton")
            button.setCursor(Qt.PointingHandCursor)
        for button in (
            self.read_button,
            self.scan_button,
            self.phone_button,
        ):
            row.addWidget(button)
        row.addStretch()

        # Ver / quitar van junto al nombre del documento, que es a lo
        # que se refieren, y así la fila de arriba no se ensancha.
        for button in (
            self.open_button,
            self.original_button,
            self.remove_button,
        ):
            button.setStyleSheet("padding: 5px 12px;")
        self.original_button.clicked.connect(self.use_original_photo)

        self.read_button.clicked.connect(self.choose_document)
        self.scan_button.clicked.connect(self.scan_document)
        self.phone_button.clicked.connect(self.phone_document)
        self.open_button.clicked.connect(self.open_document)
        self.remove_button.clicked.connect(self.remove_document)

        self.document_status = QLabel()
        self.document_status.setObjectName("cardDescription")
        self.document_status.setWordWrap(True)
        self.document_status.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        # Dónde y con qué nombre se archivará al guardar el gasto.
        self.document_target = QLabel()
        self.document_target.setObjectName("cardDescription")
        self.document_target.setWordWrap(True)
        self.document_target.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.document_target.setStyleSheet("font-weight: 600;")
        # Que un nombre largo se parta en líneas en vez de ensanchar.
        for label in (self.document_status, self.document_target):
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.open_button)
        actions.addWidget(self.original_button)
        actions.addWidget(self.remove_button)
        actions.addStretch()

        bar_layout.addLayout(row)
        bar_layout.addWidget(self.document_status)
        bar_layout.addWidget(self.document_target)
        bar_layout.addLayout(actions)
        return bar

    def document_name(self):
        """
        Nombre para enseñar: el archivado, o "nuevo" si aún no se ha
        guardado (su nombre temporal no dice nada; el definitivo sale
        en la línea "Al guardar el gasto se archivará como").
        """
        if self.pending_document:
            return "nuevo"
        return Path(self.document_file).name if self.document_file else ""

    def current_document(self):
        return self.pending_document or self.document_file

    def update_document_bar(self, message=None):
        document = self.current_document()
        busy = self.reader is not None

        self.read_button.setEnabled(not busy)
        self.scan_button.setEnabled(not busy)
        self.phone_button.setEnabled(not busy)
        self.open_button.setVisible(bool(document))
        self.remove_button.setVisible(bool(document) and not busy)
        self.original_button.setVisible(
            bool(self.original_photo) and not busy
        )

        if message is None:
            if document and not Path(document).exists():
                message = f"⚠ No se encuentra el documento: {document}"
            elif document:
                message = f"Documento: {self.document_name()}"
            else:
                message = (
                    "Elige o arrastra aquí una foto o PDF del ticket, "
                    "escanéalo o hazle una foto con el móvil, y se "
                    "rellenarán los datos."
                )
        if self.scan_note and self.original_photo:
            message = f"{message}\n{self.scan_note}"
        self.document_status.setText(message)
        self.update_document_target()

    def archive_folder(self):
        if getattr(self, "_archive_folder", None) is None:
            session = get_session()
            try:
                self._archive_folder = get_setting(session, receipts.EXPENSE_FOLDER_KEY)
            finally:
                session.close()
        return self._archive_folder or None

    def archive_date(self):
        return (
            self.expense_date.date().toPython()
            if self.payment_type.currentText() == "Único"
            else self.recurrence_start.date().toPython()
        )

    def update_document_target(self, *_):
        """Enseña el nombre definitivo del documento nuevo."""
        if not hasattr(self, "document_target"):
            return
        if not self.pending_document or self.reader is not None:
            self.document_target.setVisible(False)
            return
        target = receipts.archive_target(
            self.pending_document,
            expense_date=self.archive_date(),
            label=self.file_label or self.supplier.text().strip(),
            folder=self.archive_folder(),
        )
        # Ruta desde la carpeta de gastos (FACTURAS\\2026\\10.OCTUBRE\\…):
        # la completa no cabe y ensancharía el formulario.
        base = Path(self.archive_folder() or receipts.default_expense_folder())
        try:
            shown = Path(base.name) / target.relative_to(base)
        except ValueError:
            shown = target
        # Espacio invisible tras cada "\\" para poder partir la ruta.
        shown = str(shown).replace("\\", "\\\u200b")
        self.document_target.setText(
            f"Al guardar el gasto se archivará como: {shown}"
        )
        self.document_target.setToolTip(str(target))
        self.document_target.setVisible(True)

    def choose_document(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Ticket o factura",
            str(Path.home()),
            receipts.FILE_FILTER,
        )
        if path:
            self.read_document(path)

    def scan_document(self):
        try:
            path = scanner.scan_to_file()
        except scanner.ScannerError as error:
            QMessageBox.warning(self, "Escanear", str(error))
            return
        if path:
            self.read_scanned_photo(path)

    def phone_document(self):
        received = receive_from_phone(self)
        if not received:
            return
        path, corners = received
        if Path(path).suffix.lower() == ".pdf":
            self.read_document(path)
        else:
            self.read_scanned_photo(path, corners)

    def read_scanned_photo(self, photo, corners=None):
        """
        Foto del móvil o del escáner: se recorta, endereza y mejora como
        un escáner y se convierte a PDF antes de leerla. `corners` es el
        recorte marcado en el móvil; sin él se busca el documento solo.
        """
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = docscan.scan_photo(photo, corners=corners)
        except Exception:
            # Si el procesado falla, se usa la foto tal cual.
            result = None
        finally:
            QGuiApplication.restoreOverrideCursor()

        if result is None:
            self.read_document(str(photo))
            return

        self.read_document(
            str(result.pdf),
            original_photo=str(photo),
            scan_note=(
                "Escaneado a PDF: recortado como lo marcaste en el móvil, "
                "enderezado y mejorado."
                if corners is not None else
                "Escaneado a PDF: recortado, enderezado y mejorado."
                if result.cropped else
                "Escaneado a PDF y mejorado. No se ha recortado porque "
                "no se veía el documento entero."
            ),
        )

    def use_original_photo(self):
        if not self.original_photo:
            return
        self.pending_document = self.original_photo
        self.original_photo = None
        self.scan_note = ""
        self.update_document_bar(
            "Documento: nuevo · Se guardará la foto original, sin recortar."
        )

    def dragEnterEvent(self, event):
        if self.reader is None and self._dropped_file(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = self._dropped_file(event)
        if path:
            event.acceptProposedAction()
            self.read_document(path)

    @staticmethod
    def _dropped_file(event):
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = urls[0].toLocalFile()
        if Path(path).suffix.lower() not in receipts.SUPPORTED_EXTENSIONS:
            return None
        return path

    def read_document(self, path, original_photo=None, scan_note=""):
        if self.reader is not None:
            return

        self.pending_document = path
        self.original_photo = original_photo
        self.scan_note = scan_note

        if not receipts.has_api_key():
            self.update_document_bar(
                f"Documento: {self.document_name()} · No se ha leído: falta la "
                "clave de API (Configuración → Lectura de tickets). "
                "Rellena los datos a mano; el documento se guardará igual."
            )
            return

        session = get_session()
        try:
            company = " · ".join(
                part for part in (
                    get_setting(session, "company_name"),
                    get_setting(session, "company_tax_id"),
                ) if part
            )
        finally:
            session.close()

        categories = [
            self.category.itemText(i)
            for i in range(self.category.count())
        ]

        self.reader = ReceiptReader(path, categories, company)
        self.reader.succeeded.connect(self.document_read)
        self.reader.failed.connect(self.document_failed)
        self.reader.start()

        self.update_document_bar(
            "Leyendo el documento… (unos segundos)"
        )

    def document_failed(self, message):
        self.reader = None
        self.update_document_bar()
        QMessageBox.warning(self, "No se ha podido leer", message)

    def document_read(self, data):
        self.reader = None

        if not data["is_expense_document"]:
            self.update_document_bar()
            QMessageBox.warning(
                self,
                "Documento no reconocido",
                "No parece un ticket ni una factura. Revisa el archivo "
                "o rellena los datos a mano.",
            )
            return

        self.fill_from_document(data)

        message = (
            f"Documento: {self.document_name()} · "
            "Datos leídos: revísalos antes de guardar."
        )
        if self.total_mismatch():
            message += (
                f"\n⚠ El total del documento es {money(self.expected_total)} "
                f"y el calculado {money(self.total_amount.value())}. "
                "Revisa base e IVA."
            )
        self.update_document_bar(message)
        self.fit_to_screen()

    def fill_from_document(self, data):
        self.file_label = data.get("file_label", "")
        index = self.category.findText(data["category"])
        if index >= 0:
            self.category.setCurrentIndex(index)
        if data["concept"]:
            self.concept.setText(data["concept"])
        if data["supplier"]:
            self.supplier.setText(data["supplier"])

        self.payment_type.setCurrentText("Único")
        if data["date"]:
            day = QDate(data["date"].year, data["date"].month, data["date"].day)
            self.expense_date.setDate(day)
            self.payment_date.setDate(day)

        self.vat_rate.setValue(data["vat_rate"])
        self.base_amount.setValue(data["base_amount"])

        self.status.setCurrentText("Pagado" if data["paid"] else "Pendiente")

        if data["invoice_reference"]:
            self.invoice_reference.setText(data["invoice_reference"])

        extra = [
            f"NIF proveedor: {data['supplier_tax_id']}"
            if data["supplier_tax_id"] else "",
            data["notes"],
        ]
        extra = "\n".join(line for line in extra if line)
        if extra:
            current = self.notes.toPlainText().strip()
            self.notes.setPlainText(
                f"{current}\n{extra}" if current else extra
            )

        self.expected_total = data["total_amount"]
        self.calculate_totals()

    def total_mismatch(self):
        if not self.expected_total:
            return False
        return abs(self.total_amount.value() - self.expected_total) > 0.015

    def open_document(self):
        document = self.current_document()
        if not document or not Path(document).exists():
            QMessageBox.warning(
                self,
                "Documento",
                f"No se encuentra el documento:\n{document}",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(document))

    def remove_document(self):
        self.pending_document = None
        self.original_photo = None
        self.scan_note = ""
        self.document_file = None
        self.expected_total = None
        self.update_document_bar()

    def archive_pending_document(self):
        """Copia el documento nuevo a la carpeta de gastos. False si falla."""
        if not self.pending_document:
            return True

        try:
            archived = receipts.archive_document(
                self.pending_document,
                expense_date=self.archive_date(),
                label=self.file_label or self.supplier.text().strip(),
                folder=self.archive_folder(),
            )
        except OSError as error:
            QMessageBox.critical(
                self,
                "Documento",
                f"No se ha podido guardar una copia del documento.\n\n{error}",
            )
            return False

        self.document_file = str(archived)
        self.pending_document = None
        return True

    def reject(self):
        # Si se cierra mientras lee, el resultado ya no interesa.
        if self.reader is not None:
            self.reader.succeeded.disconnect(self.document_read)
            self.reader.failed.disconnect(self.document_failed)
            self.reader = None
        super().reject()

    # =============================================================
    # TIPO DE PAGO
    # =============================================================

    def payment_type_changed(self, payment_type):

        monthly = payment_type == "Mensual"

        # Pago único / pago mensual
        self.form.setRowVisible(self.expense_date, not monthly)
        self.form.setRowVisible(self.recurrence_row, monthly)

        # Cambiamos los textos para que quede claro que
        # los importes corresponden a UNA mensualidad.

        if monthly:

            self.base_label.setText(
                "Base mensual *"
            )

            self.vat_label.setText(
                "IVA mensual"
            )

            self.total_label.setText(
                "Total mensual"
            )

        else:

            self.base_label.setText(
                "Base imponible *"
            )

            self.vat_label.setText(
                "Importe IVA"
            )

            self.total_label.setText(
                "Total"
            )

        self.calculate_totals()

    # =============================================================
    # CÁLCULOS
    # =============================================================

    def calculate_totals(self):

        base = self.base_amount.value()
        rate = self.vat_rate.value()

        # Redondeo comercial, igual que en facturas y tesorería.
        vat = round_money(base * rate / 100)
        total = round_money(add_money(base, vat))

        self.vat_amount.setValue(vat)
        self.total_amount.setValue(total)

    # =============================================================
    # ESTADO
    # =============================================================

    def status_changed(self, status):

        self.payment_date.setEnabled(
            status == "Pagado"
        )

    # =============================================================
    # CARGAR GASTO
    # =============================================================

    def load_expense_data(self):

        expense = self.expense

        index = self.category.findText(
            expense.category
        )

        if index >= 0:
            self.category.setCurrentIndex(index)

        self.concept.setText(
            expense.concept or ""
        )

        self.supplier.setText(
            expense.supplier or ""
        )

        # ---------------------------------------------------------
        # TIPO DE PAGO
        # ---------------------------------------------------------

        payment_type = (
            expense.payment_type
            if expense.payment_type
            else "Único"
        )

        payment_index = self.payment_type.findText(
            payment_type
        )

        if payment_index >= 0:
            self.payment_type.setCurrentIndex(
                payment_index
            )

        # ---------------------------------------------------------
        # FECHA ÚNICA
        # ---------------------------------------------------------

        if expense.expense_date:

            self.expense_date.setDate(
                QDate(
                    expense.expense_date.year,
                    expense.expense_date.month,
                    expense.expense_date.day,
                )
            )

        # ---------------------------------------------------------
        # RECURRENCIA
        # ---------------------------------------------------------

        if expense.recurrence_start:

            self.recurrence_start.setDate(
                QDate(
                    expense.recurrence_start.year,
                    expense.recurrence_start.month,
                    expense.recurrence_start.day,
                )
            )

        if expense.recurrence_end:

            self.recurrence_end.setDate(
                QDate(
                    expense.recurrence_end.year,
                    expense.recurrence_end.month,
                    expense.recurrence_end.day,
                )
            )

        # ---------------------------------------------------------
        # IMPORTES
        # ---------------------------------------------------------

        self.base_amount.setValue(
            expense.base_amount or 0
        )

        self.vat_rate.setValue(
            expense.vat_rate or 0
        )

        # ---------------------------------------------------------
        # ESTADO
        # ---------------------------------------------------------

        status_index = self.status.findText(
            expense.status
        )

        if status_index >= 0:
            self.status.setCurrentIndex(
                status_index
            )

        if expense.payment_date:

            self.payment_date.setDate(
                QDate(
                    expense.payment_date.year,
                    expense.payment_date.month,
                    expense.payment_date.day,
                )
            )

        self.invoice_reference.setText(
            expense.invoice_reference or ""
        )

        self.notes.setPlainText(
            expense.notes or ""
        )

        self.payment_type_changed(
            self.payment_type.currentText()
        )

        self.calculate_totals()

        self.status_changed(
            self.status.currentText()
        )

    # =============================================================
    # VALIDACIÓN
    # =============================================================

    def validate(self):

        if not self.concept.text().strip():

            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Introduce el concepto del gasto.",
            )

            return

        if self.base_amount.value() <= 0:

            QMessageBox.warning(
                self,
                "Importe incorrecto",
                "La base imponible debe ser superior a 0 €.",
            )

            return

        # ---------------------------------------------------------
        # VALIDAR RECURRENCIA
        # ---------------------------------------------------------

        if self.payment_type.currentText() == "Mensual":

            start = self.recurrence_start.date()
            end = self.recurrence_end.date()

            if end < start:

                QMessageBox.warning(
                    self,
                    "Fechas incorrectas",
                    "La fecha final no puede ser "
                    "anterior a la fecha inicial.",
                )

                return

        if self.reader is not None:

            QMessageBox.information(
                self,
                "Leyendo documento",
                "Espera a que termine de leer el documento.",
            )

            return

        if not self.archive_pending_document():
            return

        self.accept()

    # =============================================================
    # DEVOLVER DATOS
    # =============================================================

    def get_data(self):

        payment_type = (
            self.payment_type.currentText()
        )

        monthly = payment_type == "Mensual"

        paid = (
            self.status.currentText()
            == "Pagado"
        )

        return {
            "category":
                self.category.currentText(),

            "concept":
                self.concept.text().strip(),

            "supplier":
                self.supplier.text().strip()
                or None,

            "payment_type":
                payment_type,

            # Pago único
            "expense_date": (
                None
                if monthly
                else self.expense_date.date().toPython()
            ),

            # Pago mensual
            "recurrence_start": (
                self.recurrence_start.date().toPython()
                if monthly
                else None
            ),

            "recurrence_end": (
                self.recurrence_end.date().toPython()
                if monthly
                else None
            ),

            # En mensual estos importes representan
            # UNA mensualidad.
            "base_amount":
                self.base_amount.value(),

            "vat_rate":
                self.vat_rate.value(),

            "vat_amount":
                self.vat_amount.value(),

            "total_amount":
                self.total_amount.value(),

            "status":
                self.status.currentText(),

            "payment_date": (
                self.payment_date.date().toPython()
                if paid
                else None
            ),

            "invoice_reference": (
                self.invoice_reference.text().strip()
                or None
            ),

            "notes": (
                self.notes.toPlainText().strip()
                or None
            ),

            "document_file":
                self.document_file,
        }