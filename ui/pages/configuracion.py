from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from database.database import (
    BACKUP_DIR,
    EXTERNAL_BACKUP_KEY,
    backup_to_external,
    get_session,
    latest_backup,
)
from database.models import AppSetting
from services import invoices, receipts
from services.cashflow import get_setting


class SettingsPage(QWidget):

    INITIAL_BALANCE_KEY = "initial_cash_balance"

    # Tras guardar: la ventana actualiza el logo y el nombre del menú.
    saved = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.company_inputs = {}
        # Imagen elegida y aún sin guardar, por clave de ajuste:
        # ruta del archivo nuevo, o "" para quitarla.
        self.pending_images = {}
        self.setup_ui()
        self.refresh()

    # ==========================================================
    # INTERFAZ
    # ==========================================================

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(22)

        title = QLabel("Configuración")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Parámetros de tesorería, datos fiscales de la empresa y facturación."
        )
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # ---------------- Tesorería ----------------
        panel, panel_layout = self.create_panel(
            "Tesorería",
            "El capital inicial es el dinero con el que arrancó la empresa. "
            "El saldo actual se calcula como capital inicial + todo lo cobrado "
            "- todo lo pagado, así que no hace falta actualizarlo a mano.",
        )
        form = QFormLayout()
        form.setSpacing(12)

        self.initial_balance = QDoubleSpinBox()
        self.initial_balance.setRange(-999_999_999.99, 999_999_999.99)
        self.initial_balance.setDecimals(2)
        self.initial_balance.setSuffix(" €")
        self.initial_balance.setGroupSeparatorShown(True)
        self.initial_balance.setMinimumWidth(230)
        form.addRow("Capital inicial", self.initial_balance)
        panel_layout.addLayout(form)

        note = QLabel(
            "En la vista de un proyecto individual la previsión parte de 0 € "
            "y se calcula sin IVA, para mostrar solo el impacto del proyecto."
        )
        note.setWordWrap(True)
        note.setObjectName("cardDescription")
        panel_layout.addWidget(note)
        layout.addWidget(panel)

        # ---------------- Empresa ----------------
        panel, panel_layout = self.create_panel(
            "Datos fiscales de la empresa",
            "Aparecen en todas las facturas. Razón social, CIF, dirección y "
            "población son obligatorios.",
        )
        form = QFormLayout()
        form.setSpacing(10)
        for key, label, _default in invoices.COMPANY_FIELDS:
            line = QLineEdit()
            line.setMinimumWidth(380)
            self.company_inputs[key] = line
            form.addRow(label, line)
        self.logo_status = QLabel()
        form.addRow("Logo", self.image_row("company_logo", self.logo_status))
        panel_layout.addLayout(form)

        note = QLabel(
            "El logo sale en el menú lateral y en las facturas (PNG o JPG)."
        )
        note.setWordWrap(True)
        note.setObjectName("cardDescription")
        panel_layout.addWidget(note)
        layout.addWidget(panel)

        # ---------------- Usuario ----------------
        panel, panel_layout = self.create_panel(
            "Usuario",
            "Nombre y cargo que aparecen en la cabecera del Dashboard. "
            "Opcionales.",
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.user_name = QLineEdit()
        self.user_name.setPlaceholderText("Ej. Ana García")
        self.user_role = QLineEdit()
        self.user_role.setPlaceholderText("Ej. Administración")
        form.addRow("Nombre", self.user_name)
        form.addRow("Cargo", self.user_role)
        panel_layout.addLayout(form)
        layout.addWidget(panel)

        # ---------------- Facturación ----------------
        panel, panel_layout = self.create_panel(
            "Facturación",
            "Los números son correlativos. Si ya tienes facturas emitidas, "
            "pon en 'Siguiente número' el número que toca. En el prefijo "
            "puedes usar {año}; por ejemplo 'F{año}-' genera F2026-0001.",
        )
        form = QFormLayout()
        form.setSpacing(10)

        self.invoice_prefix = QLineEdit()
        self.invoice_prefix.setPlaceholderText("Vacío = solo número (0060)")
        self.invoice_prefix.textChanged.connect(self.update_preview)

        self.invoice_digits = QSpinBox()
        self.invoice_digits.setRange(1, 8)
        self.invoice_digits.setValue(4)
        self.invoice_digits.valueChanged.connect(self.update_preview)

        self.invoice_next = QSpinBox()
        self.invoice_next.setRange(1, 99_999_999)
        self.invoice_next.valueChanged.connect(self.update_preview)

        self.invoice_preview = QLabel()
        self.invoice_preview.setStyleSheet("font-weight: 700;")

        self.invoice_days = QSpinBox()
        self.invoice_days.setRange(0, 365)
        self.invoice_days.setValue(30)
        self.invoice_days.setSuffix(" días")

        folder_row = QHBoxLayout()
        self.invoice_folder = QLineEdit()
        self.invoice_folder.setPlaceholderText(str(invoices.default_invoice_folder()))
        browse = QPushButton("Elegir…")
        browse.setObjectName("secondaryButton")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.invoice_folder, 1)
        folder_row.addWidget(browse)

        self.invoice_footer = QLineEdit()
        self.invoice_footer.setPlaceholderText("Ej. Gracias por su confianza")

        form.addRow("Prefijo", self.invoice_prefix)
        form.addRow("Dígitos", self.invoice_digits)
        form.addRow("Siguiente número", self.invoice_next)
        form.addRow("Próxima factura", self.invoice_preview)
        form.addRow("Vencimiento por defecto", self.invoice_days)
        form.addRow("Carpeta de facturas", folder_row)
        form.addRow("Texto al pie", self.invoice_footer)

        # Por ejemplo, el sello del seguro de crédito.
        self.stamp_status = QLabel()
        form.addRow("Sello (opcional)", self.image_row("invoice_stamp", self.stamp_status))
        panel_layout.addLayout(form)
        layout.addWidget(panel)

        # ---------------- Lectura de tickets ----------------
        panel, panel_layout = self.create_panel(
            "Lectura de tickets",
            "Al añadir un gasto puedes elegir, arrastrar o escanear el ticket "
            "o la factura y se rellenan los datos solos. La lectura la hace "
            "Claude (Anthropic): el documento se envía a su servicio y cada "
            "lectura cuesta alrededor de un céntimo. La clave se crea en "
            "console.anthropic.com y se guarda en el Administrador de "
            "credenciales de Windows, no en la base de datos. Los documentos "
            "se guardan en la carpeta de tickets, por año y mes "
            "(2026\\10.OCTUBRE), con nombres como 2026_10_04_Peaje.pdf.",
        )
        form = QFormLayout()
        form.setSpacing(10)

        key_row = QHBoxLayout()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setMinimumWidth(320)
        clear_key = QPushButton("Borrar clave")
        clear_key.setObjectName("secondaryButton")
        clear_key.setCursor(Qt.PointingHandCursor)
        clear_key.clicked.connect(self.clear_api_key)
        key_row.addWidget(self.api_key, 1)
        key_row.addWidget(clear_key)

        expense_folder_row = QHBoxLayout()
        self.expense_folder = QLineEdit()
        self.expense_folder.setPlaceholderText(str(receipts.default_expense_folder()))
        browse_expenses = QPushButton("Elegir…")
        browse_expenses.setObjectName("secondaryButton")
        browse_expenses.setCursor(Qt.PointingHandCursor)
        browse_expenses.clicked.connect(self.choose_expense_folder)
        expense_folder_row.addWidget(self.expense_folder, 1)
        expense_folder_row.addWidget(browse_expenses)

        form.addRow("Clave de API", key_row)
        form.addRow("Carpeta de tickets", expense_folder_row)
        panel_layout.addLayout(form)
        layout.addWidget(panel)

        # ---------------- Copias ----------------
        panel, panel_layout = self.create_panel(
            "Copias de seguridad",
            "Cada día que abres la aplicación se guarda una copia de la base "
            "de datos. Se conservan las últimas 30.",
        )
        backup_row = QHBoxLayout()
        backup_label = QLabel(str(BACKUP_DIR))
        backup_label.setObjectName("cardDescription")
        backup_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_backups = QPushButton("Abrir carpeta")
        open_backups.setObjectName("secondaryButton")
        open_backups.setCursor(Qt.PointingHandCursor)
        open_backups.clicked.connect(self.open_backup_folder)
        backup_row.addWidget(backup_label, 1)
        backup_row.addWidget(open_backups)
        panel_layout.addLayout(backup_row)

        external_note = QLabel(
            "Esas copias están en el mismo disco que los datos. Elige además "
            "una carpeta externa (OneDrive, un NAS o un USB) y se guardará "
            "allí también una copia diaria al abrir la aplicación."
        )
        external_note.setWordWrap(True)
        external_note.setObjectName("cardDescription")
        panel_layout.addWidget(external_note)

        external_row = QHBoxLayout()
        self.external_folder = QLineEdit()
        self.external_folder.setPlaceholderText("Sin carpeta externa")
        self.external_folder.textChanged.connect(self.update_external_status)
        choose_external = QPushButton("Elegir…")
        choose_external.setObjectName("secondaryButton")
        choose_external.setCursor(Qt.PointingHandCursor)
        choose_external.clicked.connect(self.choose_external_folder)
        copy_now = QPushButton("Copiar ahora")
        copy_now.setObjectName("secondaryButton")
        copy_now.setCursor(Qt.PointingHandCursor)
        copy_now.clicked.connect(self.copy_now)
        external_row.addWidget(self.external_folder, 1)
        external_row.addWidget(choose_external)
        external_row.addWidget(copy_now)
        panel_layout.addLayout(external_row)

        self.external_status = QLabel()
        self.external_status.setObjectName("cardDescription")
        panel_layout.addWidget(self.external_status)
        layout.addWidget(panel)

        save_button = QPushButton("Guardar configuración")
        save_button.setObjectName("primaryButton")
        save_button.setCursor(Qt.PointingHandCursor)
        save_button.clicked.connect(self.save)
        layout.addWidget(save_button, 0, Qt.AlignLeft)
        layout.addStretch()

    def image_row(self, key, status_label):
        status_label.setObjectName("cardDescription")
        row = QHBoxLayout()
        choose = QPushButton("Elegir imagen…")
        choose.setObjectName("secondaryButton")
        choose.setCursor(Qt.PointingHandCursor)
        choose.clicked.connect(lambda: self.choose_image(key))
        remove = QPushButton("Quitar")
        remove.setObjectName("secondaryButton")
        remove.setCursor(Qt.PointingHandCursor)
        remove.clicked.connect(lambda: self.set_pending_image(key, ""))
        row.addWidget(status_label, 1)
        row.addWidget(choose)
        row.addWidget(remove)
        return row

    def create_panel(self, title_text, description_text):
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setMaximumWidth(820)
        # Alto fijo al que pide su contenido: si no, la página reparte menos
        # alto del necesario y las casillas quedan con el texto cortado.
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 22, 24, 22)
        panel_layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("panelTitle")
        panel_layout.addWidget(title)

        description = QLabel(description_text)
        description.setWordWrap(True)
        description.setObjectName("panelDescription")
        panel_layout.addWidget(description)
        return panel, panel_layout

    # ==========================================================
    # ACCIONES
    # ==========================================================

    def update_preview(self):
        from datetime import date
        self.invoice_preview.setText(invoices.format_number(
            self.invoice_prefix.text(),
            self.invoice_digits.value(),
            self.invoice_next.value(),
            date.today().year,
        ))

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta de facturas",
            self.invoice_folder.text() or str(invoices.default_invoice_folder()),
        )
        if folder:
            self.invoice_folder.setText(folder)

    def choose_image(self, key):
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir imagen", str(Path.home()),
            "Imágenes (*.png *.jpg *.jpeg)",
        )
        if path:
            self.set_pending_image(key, path)

    def set_pending_image(self, key, path):
        self.pending_images[key] = path
        self.update_image_status(key, path)

    def update_image_status(self, key, path):
        label = self.logo_status if key == "company_logo" else self.stamp_status
        label.setText(Path(path).name if path else "Sin imagen")

    def choose_expense_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta de tickets y facturas de gasto",
            self.expense_folder.text() or str(receipts.default_expense_folder()),
        )
        if folder:
            self.expense_folder.setText(folder)

    def update_api_key_placeholder(self):
        self.api_key.clear()
        self.api_key.setPlaceholderText(
            "Clave guardada (escribe otra para cambiarla)"
            if receipts.has_api_key()
            else "sk-ant-…"
        )

    def clear_api_key(self):
        try:
            receipts.set_api_key("")
        except Exception as error:
            QMessageBox.critical(self, "Clave de API", f"No se ha podido borrar.\n\n{error}")
        self.update_api_key_placeholder()

    def choose_external_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta para la copia externa",
            self.external_folder.text() or str(Path.home()),
        )
        if folder:
            self.external_folder.setText(folder)

    def update_external_status(self):
        text = self.external_folder.text().strip()
        if not text:
            self.external_status.setText("Copia externa desactivada.")
            return
        folder = Path(text)
        if not folder.is_dir():
            self.external_status.setText("⚠ La carpeta no existe o no está conectada.")
            return
        latest = latest_backup(folder)
        if latest is None:
            self.external_status.setText("Todavía no hay copias en esta carpeta.")
        else:
            modified = datetime.fromtimestamp(latest.stat().st_mtime)
            self.external_status.setText(
                f"Última copia externa: {modified.strftime('%d/%m/%Y %H:%M')} ({latest.name})"
            )

    def copy_now(self):
        text = self.external_folder.text().strip()
        if not text:
            QMessageBox.warning(self, "Copia externa", "Elige primero una carpeta.")
            return
        try:
            target = backup_to_external(Path(text), force=True)
        except OSError as error:
            QMessageBox.critical(
                self,
                "Copia externa",
                f"No se ha podido hacer la copia.\n\n{error}",
            )
            return
        finally:
            self.update_external_status()
        QMessageBox.information(self, "Copia externa", f"Copia guardada en:\n{target}")

    def open_backup_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BACKUP_DIR)))

    def refresh(self):
        session = get_session()
        try:
            setting = session.get(AppSetting, self.INITIAL_BALANCE_KEY)
            value = 0.0
            if setting is not None:
                try:
                    value = float(setting.value)
                except (TypeError, ValueError):
                    value = 0.0
            self.initial_balance.setValue(value)

            company = invoices.get_company(session)
            for key, line in self.company_inputs.items():
                line.setText(company.get(key, ""))

            settings = invoices.get_invoice_settings(session)
            self.invoice_prefix.setText(settings["invoice_prefix"])
            try:
                self.invoice_digits.setValue(int(settings["invoice_digits"] or 4))
            except ValueError:
                self.invoice_digits.setValue(4)
            try:
                self.invoice_days.setValue(int(settings["invoice_payment_days"] or 30))
            except ValueError:
                self.invoice_days.setValue(30)
            self.invoice_folder.setText(settings["invoice_folder"])
            self.invoice_footer.setText(settings["invoice_footer"])
            self.pending_images = {}
            for key in ("company_logo", "invoice_stamp"):
                self.update_image_status(key, settings[key])
            self.user_name.setText(get_setting(session, "user_name"))
            self.user_role.setText(get_setting(session, "user_role"))
            self.external_folder.setText(get_setting(session, EXTERNAL_BACKUP_KEY))
            self.expense_folder.setText(get_setting(session, receipts.EXPENSE_FOLDER_KEY))

            # Siguiente número: configurado o, si no, deducido de las
            # facturas ya registradas en los cobros.
            suggested = invoices.suggest_invoice_number(session)
            number = invoices._trailing_number(suggested) or 1
            self.invoice_next.setValue(number)
        finally:
            session.close()
        self.update_preview()
        self.update_external_status()
        self.update_api_key_placeholder()

    def save(self):
        session = get_session()
        try:
            values = {
                self.INITIAL_BALANCE_KEY: self.initial_balance.value(),
                "invoice_prefix": self.invoice_prefix.text().strip(),
                "invoice_digits": self.invoice_digits.value(),
                "invoice_next_number": self.invoice_next.value(),
                "invoice_payment_days": self.invoice_days.value(),
                "invoice_folder": self.invoice_folder.text().strip(),
                "invoice_footer": self.invoice_footer.text().strip(),
                "user_name": self.user_name.text().strip(),
                "user_role": self.user_role.text().strip(),
                EXTERNAL_BACKUP_KEY: self.external_folder.text().strip(),
                receipts.EXPENSE_FOLDER_KEY: self.expense_folder.text().strip(),
            }
            for key, line in self.company_inputs.items():
                values[key] = line.text().strip()
            for key, path in self.pending_images.items():
                values[key] = str(invoices.store_image(path, key)) if path else ""
            invoices.save_settings(session, values)
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Error",
                f"No se ha podido guardar la configuración.\n\n{error}",
            )
            return
        finally:
            session.close()

        # Solo se cambia la clave si se ha escrito una nueva.
        if self.api_key.text().strip():
            try:
                receipts.set_api_key(self.api_key.text())
            except Exception as error:
                QMessageBox.critical(
                    self,
                    "Clave de API",
                    f"No se ha podido guardar la clave de API.\n\n{error}",
                )
                return
            finally:
                self.update_api_key_placeholder()

        self.pending_images = {}
        self.saved.emit()
        QMessageBox.information(
            self,
            "Configuración guardada",
            "La configuración se ha guardado correctamente.",
        )
