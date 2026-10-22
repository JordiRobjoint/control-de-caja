from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QColor, QFont

from database.database import get_session
from database.models import Project
from services import cashflow
from services.cashflow import money, sort_movements
from ui.table_utils import fills


class TreasuryPage(QWidget):

    def refresh(self):
        self.load_projects()
        self.load_data()

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 35, 40, 35)
        main_layout.setSpacing(22)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("Tesorería")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Control real y previsión de entradas y salidas de caja."
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        self.project_filter = QComboBox()
        self.project_filter.setMinimumWidth(260)
        self.project_filter.currentIndexChanged.connect(self.load_data)
        header.addWidget(self.project_filter)

        refresh_button = QPushButton("↻  Actualizar")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.setCursor(Qt.PointingHandCursor)
        refresh_button.clicked.connect(self.load_data)
        header.addWidget(refresh_button)

        main_layout.addLayout(header)

        cards = QHBoxLayout()
        cards.setSpacing(15)

        self.current_balance_value = QLabel("0,00 €")
        self.pending_collections_value = QLabel("0,00 €")
        self.pending_payments_value = QLabel("0,00 €")
        self.projected_balance_value = QLabel("0,00 €")

        self.current_balance_card = self.create_card(
            "Saldo actual",
            self.current_balance_value,
            "Capital inicial + cobrado - pagado",
        )
        cards.addWidget(self.current_balance_card)
        cards.addWidget(self.create_card(
            "Cobros pendientes",
            self.pending_collections_value,
            "Incluye vencidos sin cobrar",
        ))
        cards.addWidget(self.create_card(
            "Pagos pendientes",
            self.pending_payments_value,
            "Incluye vencidos sin pagar",
        ))
        cards.addWidget(self.create_card(
            "Saldo proyectado",
            self.projected_balance_value,
            "Saldo actual + pendientes",
        ))

        main_layout.addLayout(cards)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(15)

        panel_header = QHBoxLayout()
        panel_title = QLabel("Previsión mensual")
        panel_title.setObjectName("panelTitle")
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("panelDescription")
        self.summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        panel_header.addWidget(panel_title)
        panel_header.addStretch()
        panel_header.addWidget(self.summary_label)
        panel_layout.addLayout(panel_header)

        self.month_table = QTableWidget()
        self.month_table.setColumnCount(5)
        self.month_table.setHorizontalHeaderLabels([
            "Mes",
            "Entradas",
            "Salidas",
            "Flujo neto",
            "Saldo acumulado",
        ])
        self.prepare_table(self.month_table)
        panel_layout.addWidget(self.month_table)

        main_layout.addWidget(panel, 1)

        movements_panel = QFrame()
        movements_panel.setObjectName("panel")
        movements_layout = QVBoxLayout(movements_panel)
        movements_layout.setContentsMargins(22, 20, 22, 20)
        movements_layout.setSpacing(15)

        self.tabs = QTabWidget()
        movements_layout.addWidget(self.tabs)

        movements_tab = QWidget()
        movements_tab_layout = QVBoxLayout(movements_tab)
        movements_tab_layout.setContentsMargins(0, 12, 0, 0)
        self.tabs.addTab(movements_tab, "Movimientos")

        self.movements_table = QTableWidget()
        self.movements_table.setColumnCount(7)
        self.movements_table.setHorizontalHeaderLabels([
            "Fecha",
            "Tipo",
            "Proyecto",
            "Concepto",
            "Estado",
            "Entrada",
            "Salida",
        ])
        self.prepare_table(self.movements_table)
        movements_tab_layout.addWidget(self.movements_table)

        self.tabs.addTab(self.create_vat_tab(), "IVA (modelo 303)")

        main_layout.addWidget(movements_panel, 1)

        self.load_projects()
        self.load_data()

    # ==========================================================
    # IVA (MODELO 303)
    # ==========================================================

    def create_vat_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        note = QLabel(
            "La app estima cada trimestre con las facturas emitidas y los "
            "gastos registrados. Cuando la gestoría presente el 303, registra "
            "el resultado real: la tesorería usará ese importe y esa fecha."
        )
        note.setWordWrap(True)
        note.setObjectName("cardDescription")
        header.addWidget(note, 1)

        delete_button = QPushButton("Eliminar registro")
        delete_button.setObjectName("dangerButton")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self.delete_vat_settlement)
        header.addWidget(delete_button)

        register_button = QPushButton("+  Registrar liquidación")
        register_button.setObjectName("primaryButton")
        register_button.setCursor(Qt.PointingHandCursor)
        register_button.clicked.connect(self.register_vat_settlement)
        header.addWidget(register_button)
        layout.addLayout(header)

        self.vat_table = QTableWidget()
        self.vat_table.setColumnCount(7)
        self.vat_table.setHorizontalHeaderLabels([
            "Trimestre",
            "IVA repercutido",
            "IVA soportado",
            "Estimado app",
            "Real (gestoría)",
            "Fecha de pago",
            "Estado",
        ])
        self.prepare_table(self.vat_table)
        self.vat_table.doubleClicked.connect(self.register_vat_settlement)
        layout.addWidget(self.vat_table)

        self.vat_rows = []
        return tab

    @fills("vat_table")
    def fill_vat(self, rows, today):
        # Más recientes primero, sin trimestres vacíos (p. ej. meses de la
        # previsión con gastos sin IVA, como las nóminas).
        self.vat_rows = [
            row for row in reversed(rows)
            if row["registered"]
            or any(abs(row[key]) > 0.005 for key in ("output", "input", "estimated", "carry_in"))
        ]
        self.vat_table.setRowCount(len(self.vat_rows))

        for row_index, row in enumerate(self.vat_rows):
            quarter_end = cashflow.add_months(date(row["year"], row["quarter"] * 3 - 2, 1), 3)
            pending_register = not row["registered"] and quarter_end <= today

            if row["registered"]:
                real = money(row["result"])
                if row["result"] <= 0.005:
                    status = "A compensar" if row["result"] < -0.005 else "Sin ingreso"
                    payment = "—"
                else:
                    status = "Pagado" if row["realized"] else "Pendiente de pago"
                    payment = row["payment_date"].strftime("%d/%m/%Y")
            else:
                real = "—"
                payment = f"{row['due_date'].strftime('%d/%m/%Y')} (plazo)" if row["to_pay"] else "—"
                status = "Sin registrar" if pending_register else "Previsión"

            values = [
                row["label"],
                money(row["output"]),
                money(row["input"]),
                money(row["estimated"]),
                real,
                payment,
                status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (1, 2, 3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if pending_register and column == 6:
                    item.setForeground(QColor("#E0A030"))
                    item.setToolTip(
                        "Trimestre cerrado sin el resultado real de la gestoría: "
                        "la tesorería está usando la estimación."
                    )
                self.vat_table.setItem(row_index, column, item)

        self.vat_table.clearSelection()

    def selected_vat_row(self):
        row = self.vat_table.currentRow()
        if 0 <= row < len(self.vat_rows):
            return self.vat_rows[row]
        return None

    def register_vat_settlement(self):
        from database.models import VatSettlement
        from ui.pages.dialogs.vat_dialog import VatSettlementDialog

        if not self.vat_rows:
            QMessageBox.information(
                self, "IVA", "Todavía no hay trimestres con IVA."
            )
            return

        selected = self.selected_vat_row()
        if selected is None:
            # Por defecto, el último trimestre ya cerrado.
            today = date.today()
            closed = [
                r for r in self.vat_rows
                if cashflow.add_months(date(r["year"], r["quarter"] * 3 - 2, 1), 3) <= today
            ]
            selected = (closed or self.vat_rows)[0]
        key = (selected["year"], selected["quarter"])

        session = get_session()
        try:
            existing = (
                session.query(VatSettlement)
                .filter_by(year=key[0], quarter=key[1])
                .first()
            )
            dialog = VatSettlementDialog(
                self, list(reversed(self.vat_rows)), selected=key, existing=existing
            )
            if dialog.exec() != QDialog.Accepted:
                return
            data = dialog.get_data()

            record = existing or (
                session.query(VatSettlement)
                .filter_by(year=data["year"], quarter=data["quarter"])
                .first()
            )
            if record is None:
                record = VatSettlement(year=data["year"], quarter=data["quarter"])
                session.add(record)
            record.amount = data["amount"]
            record.payment_date = data["payment_date"]
            record.notes = data["notes"]
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self, "Error", f"No se ha podido guardar la liquidación.\n\n{error}"
            )
            return
        finally:
            session.close()

        self.load_data()

    def delete_vat_settlement(self):
        from database.models import VatSettlement

        selected = self.selected_vat_row()
        if selected is None or not selected["registered"]:
            QMessageBox.warning(
                self,
                "Eliminar registro",
                "Selecciona un trimestre con una liquidación registrada.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Eliminar registro",
            f"¿Eliminar la liquidación registrada del {selected['label']}?\n\n"
            "La tesorería volverá a usar la estimación de la app.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        session = get_session()
        try:
            session.query(VatSettlement).filter_by(
                year=selected["year"], quarter=selected["quarter"]
            ).delete()
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Error", str(error))
            return
        finally:
            session.close()

        self.load_data()

    def create_card(self, title_text, value_label, description_text):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(120)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        value_label.setObjectName("cardValue")
        description = QLabel(description_text)
        description.setObjectName("cardDescription")

        layout.addWidget(title)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(description)

        return card

    def prepare_table(self, table):
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def load_projects(self):
        current_id = self.project_filter.currentData()

        session = get_session()
        try:
            projects = (
                session.query(Project)
                .order_by(Project.name.asc())
                .all()
            )

            self.project_filter.blockSignals(True)
            self.project_filter.clear()
            self.project_filter.addItem("Todos los proyectos", None)

            for project in projects:
                self.project_filter.addItem(
                    f"{project.name} · {project.client}",
                    project.id,
                )

            if current_id is not None:
                index = self.project_filter.findData(current_id)
                if index >= 0:
                    self.project_filter.setCurrentIndex(index)

            self.project_filter.blockSignals(False)

        finally:
            session.close()

    def load_data(self):
        if not hasattr(self, "project_filter"):
            return

        project_id = self.project_filter.currentData()
        today = date.today()

        session = get_session()
        try:
            movements, summary = cashflow.load_cashflow(
                session, project_id, today
            )
            vat_rows = cashflow.load_vat_quarters(session, today)
        finally:
            session.close()

        description = self.current_balance_card.findChild(
            QLabel, "cardDescription"
        )
        if description is not None:
            description.setText(
                "Capital inicial + cobrado - pagado (con IVA)"
                if project_id is None
                else "Cobrado - pagado del proyecto (sin IVA)"
            )

        self.current_balance_value.setText(money(summary.real_balance))
        self.pending_collections_value.setText(money(summary.pending_in))
        self.pending_payments_value.setText(money(summary.pending_out))
        self.projected_balance_value.setText(
            money(summary.projected_balance)
        )

        self.fill_movements(movements)
        self.fill_months(summary, today)
        self.fill_vat(vat_rows, today)

        overdue = len(summary.overdue)
        text = f"{len(movements)} movimientos"
        if overdue:
            text += f" · {overdue} vencidos pendientes"
        self.summary_label.setText(text)

    @fills("movements_table")
    def fill_movements(self, movements):
        movements = sort_movements(movements)
        today = date.today()

        self.movements_table.setRowCount(len(movements))

        for row, movement in enumerate(movements):
            date_text = (
                movement.date.strftime("%d/%m/%Y")
                if movement.date else "Sin fecha"
            )
            overdue = (
                not movement.realized
                and (movement.date is None or movement.date < today)
            )
            status = movement.status + (" · vencido" if overdue else "")

            values = [
                date_text,
                movement.kind,
                movement.project,
                movement.concept,
                status,
                money(movement.amount_in) if movement.amount_in else "—",
                money(movement.amount_out) if movement.amount_out else "—",
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (5, 6):
                    item.setTextAlignment(
                        Qt.AlignRight | Qt.AlignVCenter
                    )
                if overdue:
                    item.setForeground(QColor("#C0392B"))
                self.movements_table.setItem(row, column, item)

        self.movements_table.clearSelection()

    @fills("month_table")
    def fill_months(self, summary, today=None):
        rows = summary.forecast_rows(today)
        self.month_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["label"] + ("  *" if row["beyond_horizon"] else ""),
                money(row["in"]),
                money(row["out"]),
                money(row["net"]),
                money(row["balance"]),
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignRight | Qt.AlignVCenter
                    )
                if row["key"] is None:
                    item.setForeground(QColor("#C0392B"))
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                if column == 4 and row["balance"] < 0:
                    item.setForeground(QColor("#C0392B"))
                if row["beyond_horizon"]:
                    item.setForeground(QColor("#71717A"))
                    item.setToolTip(
                        "Fuera del horizonte de previsión (12 meses): incluye "
                        "cobros y cuotas con fecha, pero no los gastos mensuales "
                        "sin fecha de fin (nóminas, alquileres…)."
                    )
                self.month_table.setItem(row_index, column, item)

        self.month_table.clearSelection()

    @staticmethod
    def money(value):
        return money(value)
