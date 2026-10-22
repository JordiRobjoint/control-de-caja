from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func

from database.database import get_session
from database.models import Client, Project
from services.clients import missing_fiscal_data
from ui.table_utils import fills


# ==============================================================
# FORMULARIO DE CLIENTE
# ==============================================================

class ClientDialog(QDialog):

    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.setWindowTitle("Editar cliente" if client else "Nuevo cliente")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        info = QLabel(
            "Los datos fiscales se usan automáticamente al generar las "
            "facturas de los proyectos de este cliente."
        )
        info.setObjectName("pageSubtitle")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Nombre corto, ej. Talleres Norte")
        self.legal_name = QLineEdit()
        self.legal_name.setPlaceholderText("Ej. Talleres Norte, S.L. (si es distinta)")
        self.tax_id = QLineEdit()
        self.tax_id.setPlaceholderText("Ej. A12345678")
        self.address = QLineEdit()
        self.address.setPlaceholderText("Calle, número, polígono…")
        self.city = QLineEdit()
        self.city.setPlaceholderText("Ej. 36315 Vigo (Pontevedra)")
        self.country = QLineEdit()
        self.country.setPlaceholderText("España")
        self.email = QLineEdit()
        self.email.setPlaceholderText("Email de facturación")
        self.phone = QLineEdit()

        self.payment_days = QSpinBox()
        self.payment_days.setRange(0, 365)
        self.payment_days.setSuffix(" días")
        self.payment_days.setSpecialValueText("Por defecto (Configuración)")

        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)

        form.addRow("Nombre *", self.name)
        form.addRow("Razón social", self.legal_name)
        form.addRow("CIF / NIF", self.tax_id)
        form.addRow("Dirección", self.address)
        form.addRow("CP y población", self.city)
        form.addRow("País", self.country)
        form.addRow("Email", self.email)
        form.addRow("Teléfono", self.phone)
        form.addRow("Vencimiento facturas", self.payment_days)
        form.addRow("Notas", self.notes)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if client is not None:
            self.name.setText(client.name or "")
            self.legal_name.setText(client.legal_name or "")
            self.tax_id.setText(client.tax_id or "")
            self.address.setText(client.address or "")
            self.city.setText(client.city or "")
            self.country.setText(client.country or "")
            self.email.setText(client.email or "")
            self.phone.setText(client.phone or "")
            self.payment_days.setValue(client.payment_days or 0)
            self.notes.setPlainText(client.notes or "")

    def validate(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Datos incompletos", "Introduce el nombre del cliente.")
            return
        self.accept()

    def get_data(self):
        def value(line):
            return line.text().strip() or None

        return {
            "name": self.name.text().strip(),
            "legal_name": value(self.legal_name),
            "tax_id": (self.tax_id.text().strip().upper() or None),
            "address": value(self.address),
            "city": value(self.city),
            "country": value(self.country),
            "email": value(self.email),
            "phone": value(self.phone),
            "payment_days": self.payment_days.value() or None,
            "notes": self.notes.toPlainText().strip() or None,
        }


def name_taken(session, name, exclude_id=None):
    query = session.query(Client).filter(func.lower(Client.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(Client.id != exclude_id)
    return query.first() is not None


# ==============================================================
# PÁGINA DE CLIENTES
# ==============================================================

class ClientsPage(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.rows = []
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(22)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Clientes")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Datos fiscales de cada cliente para la facturación.")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre, CIF o población…")
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(self.fill_table)
        header.addWidget(self.search)

        for text, slot, name in [
            ("Editar", self.edit_client, "secondaryButton"),
            ("Eliminar", self.delete_client, "dangerButton"),
            ("+  Nuevo cliente", self.new_client, "primaryButton"),
        ]:
            button = QPushButton(text)
            button.setObjectName(name)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            header.addWidget(button)

        layout.addLayout(header)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)

        self.summary = QLabel("")
        self.summary.setObjectName("panelDescription")
        panel_layout.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Cliente", "Razón social", "CIF / NIF", "Población",
            "Email", "Proyectos", "Datos fiscales",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for column in (2, 5, 6):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.table.doubleClicked.connect(self.edit_client)
        panel_layout.addWidget(self.table)
        layout.addWidget(panel, 1)

    # ----------------------------------------------------------

    def refresh(self):
        session = get_session()
        try:
            counts = dict(
                session.query(Project.client_id, func.count(Project.id))
                .group_by(Project.client_id)
                .all()
            )
            self.rows = []
            for client in session.query(Client).order_by(Client.name).all():
                missing = missing_fiscal_data(client)
                self.rows.append({
                    "id": client.id,
                    "name": client.name,
                    "legal_name": client.legal_name or "—",
                    "tax_id": client.tax_id or "—",
                    "city": client.city or "—",
                    "email": client.email or "—",
                    "projects": counts.get(client.id, 0),
                    "missing": missing,
                })
        finally:
            session.close()
        self.fill_table()

    def visible_rows(self):
        text = self.search.text().strip().lower()
        if not text:
            return self.rows
        return [
            row for row in self.rows
            if text in f"{row['name']} {row['legal_name']} {row['tax_id']} {row['city']}".lower()
        ]

    @fills("table")
    def fill_table(self):
        rows = self.visible_rows()
        self.table.setRowCount(len(rows))
        incomplete = 0
        for index, row in enumerate(rows):
            status = "Completos" if not row["missing"] else "Falta: " + ", ".join(row["missing"])
            incomplete += bool(row["missing"])
            values = [
                row["name"], row["legal_name"], row["tax_id"], row["city"],
                row["email"], str(row["projects"]), status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, row["id"])
                if column == 5:
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 6 and row["missing"]:
                    item.setForeground(QColor("#C0392B"))
                self.table.setItem(index, column, item)
        self.table.clearSelection()

        text = f"{len(self.rows)} clientes"
        if incomplete:
            text += f" · {incomplete} con datos fiscales incompletos"
        self.summary.setText(text)

    def selected_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.warning(self, "Selecciona un cliente", "Selecciona primero un cliente.")
            return None
        return item.data(Qt.UserRole)

    # ----------------------------------------------------------

    def new_client(self):
        dialog = ClientDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.get_data()
        session = get_session()
        try:
            if name_taken(session, data["name"]):
                QMessageBox.warning(self, "Cliente duplicado",
                                    f"Ya existe un cliente llamado '{data['name']}'.")
                return
            session.add(Client(**data))
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", f"No se ha podido guardar el cliente.\n\n{error}")
            return
        finally:
            session.close()
        self.refresh()

    def edit_client(self, *_):
        client_id = self.selected_id()
        if client_id is None:
            return
        session = get_session()
        try:
            client = session.get(Client, client_id)
            if client is None:
                return
            dialog = ClientDialog(self, client)
            if dialog.exec() != QDialog.Accepted:
                return
            data = dialog.get_data()
            if name_taken(session, data["name"], client.id):
                QMessageBox.warning(self, "Cliente duplicado",
                                    f"Ya existe un cliente llamado '{data['name']}'.")
                return
            for key, value in data.items():
                setattr(client, key, value)
            # Mantener el nombre visible en sus proyectos.
            for project in client.projects:
                project.client = client.name
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", f"No se ha podido guardar el cliente.\n\n{error}")
            return
        finally:
            session.close()
        self.refresh()

    def delete_client(self):
        client_id = self.selected_id()
        if client_id is None:
            return
        session = get_session()
        try:
            client = session.get(Client, client_id)
            if client is None:
                return
            if client.projects:
                QMessageBox.warning(
                    self,
                    "Cliente con proyectos",
                    f"'{client.name}' tiene {len(client.projects)} proyecto(s). "
                    "Cambia antes el cliente de esos proyectos.",
                )
                return
            answer = QMessageBox.question(
                self, "Eliminar cliente", f"¿Eliminar el cliente '{client.name}'?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            session.delete(client)
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", f"No se ha podido eliminar.\n\n{error}")
            return
        finally:
            session.close()
        self.refresh()
