from collections import defaultdict
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QHeaderView,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.database import get_session
from database.models import AppSetting, Collection, Expense, Loan, Order, Project
from services import cashflow
from ui.pages.dashboard_charts import HIDDEN_MONEY, CashFlowChart, ExpenseDonutChart
from ui.table_utils import fills


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.selected_project_id = None
        # Los importes se ocultan al abrir hasta que se pulse el botón.
        self.amounts_visible = False
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        # Si la ventana es pequeña, el contenido se desplaza en vez de
        # aplastarse (las cifras y la gráfica quedarían cortadas).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 14, 30, 14)
        layout.setSpacing(9)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Resumen general de proyectos y flujo de caja"
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        filter_box = QVBoxLayout()

        filter_label = QLabel("Proyecto")
        filter_label.setObjectName("cardDescription")

        self.project_filter = QComboBox()
        self.project_filter.setMinimumWidth(230)
        self.project_filter.currentIndexChanged.connect(
            self.project_filter_changed
        )

        filter_box.addWidget(filter_label)
        filter_box.addWidget(self.project_filter)

        header.addLayout(filter_box)
        header.addSpacing(16)

        self.amounts_button = QPushButton("Mostrar importes")
        self.amounts_button.setCursor(Qt.PointingHandCursor)
        self.amounts_button.clicked.connect(self.toggle_amounts)
        header.addWidget(self.amounts_button, 0, Qt.AlignBottom)
        header.addSpacing(24)

        # Nombre y cargo de Configuración; vacíos, no se muestran.
        user_box = QVBoxLayout()
        self.user_label = QLabel()
        self.user_label.setObjectName("userName")
        self.user_label.setAlignment(Qt.AlignRight)
        self.role_label = QLabel()
        self.role_label.setObjectName("userRole")
        self.role_label.setAlignment(Qt.AlignRight)
        user_box.addWidget(self.user_label)
        user_box.addWidget(self.role_label)
        header.addLayout(user_box)

        layout.addLayout(header)

        cards = QHBoxLayout()
        cards.setSpacing(16)

        self.balance_value = QLabel("0,00 €")
        self.collections_value = QLabel("0,00 €")
        self.payments_value = QLabel("0,00 €")
        self.projects_value = QLabel("0")

        cards.addWidget(self.create_card(
            "Saldo actual",
            self.balance_value,
            "Capital inicial + cobrado - pagado",
        ))
        cards.addWidget(self.create_card(
            "Cobros pendientes",
            self.collections_value,
            "Pendiente de cobro",
        ))
        cards.addWidget(self.create_card(
            "Pagos pendientes",
            self.payments_value,
            "Pendiente de pago",
        ))
        cards.addWidget(self.create_card(
            "Proyectos activos",
            self.projects_value,
            "Actualmente en ejecución",
        ))

        layout.addLayout(cards)
        # ==========================================================
        # RESULTADO DEL EJERCICIO
        # ==========================================================
        result_panel, result_layout = self.create_panel("Resultado del ejercicio")
        result_header = QHBoxLayout()
        result_header.addStretch()
        year_label = QLabel("Ejercicio")
        year_label.setObjectName("cardDescription")
        result_header.addWidget(year_label)
        self.year_filter = QComboBox()
        self.year_filter.setMinimumWidth(110)
        current_year = date.today().year
        for year in range(current_year - 3, current_year + 4):
            self.year_filter.addItem(str(year), year)
        self.year_filter.setCurrentIndex(self.year_filter.findData(current_year))
        self.year_filter.currentIndexChanged.connect(self.result_year_changed)
        result_header.addWidget(self.year_filter)
        result_layout.addLayout(result_header)
        result_cards = QHBoxLayout()
        result_cards.setSpacing(16)
        self.actual_result_value = QLabel("0,00 €")
        self.forecast_result_value = QLabel("0,00 €")
        self.result_income_value = QLabel("0,00 €")
        self.result_expense_value = QLabel("0,00 €")
        result_cards.addWidget(self.create_card(
            "Resultado real", self.actual_result_value,
            "Facturado - gastos imputados",
        ))
        result_cards.addWidget(self.create_card(
            "Resultado previsto", self.forecast_result_value,
            "Previsión al cierre del ejercicio",
        ))
        result_cards.addWidget(self.create_card(
            "Ingresos previstos", self.result_income_value,
            "Facturas emitidas + previstas",
        ))
        result_cards.addWidget(self.create_card(
            "Gastos previstos", self.result_expense_value,
            "Base sin IVA",
        ))
        result_layout.addLayout(result_cards)
        layout.addWidget(result_panel)

        # ==========================================================
        # GRÁFICOS
        # ==========================================================

        middle = QHBoxLayout()
        middle.setSpacing(16)

        cash_panel, cash_layout = self.create_panel(
            "Evolución prevista de caja"
        )

        self.cashflow_chart = CashFlowChart()
        cash_layout.addWidget(self.cashflow_chart)

        middle.addWidget(cash_panel, 2)

        expense_panel, expense_layout = self.create_panel(
            "Distribución de gastos"
        )
        self.expense_chart = ExpenseDonutChart()
        expense_layout.addWidget(self.expense_chart)
        middle.addWidget(expense_panel, 1)

        layout.addLayout(middle, 1)

        # ==========================================================
        # PRÓXIMOS MOVIMIENTOS
        # ==========================================================

        bottom = QHBoxLayout()
        bottom.setSpacing(16)

        collection_panel, collection_layout = self.create_panel(
            "Próximos cobros"
        )
        self.next_collections = QTableWidget()
        self.next_collections.setColumnCount(3)
        self.next_collections.setHorizontalHeaderLabels(
            ["Fecha", "Proyecto", "Importe"]
        )
        self.prepare_table(self.next_collections)
        self.next_collections.setMinimumHeight(155)
        collection_layout.addWidget(self.next_collections)
        bottom.addWidget(collection_panel)

        payment_panel, payment_layout = self.create_panel(
            "Próximos pagos"
        )
        self.next_payments = QTableWidget()
        self.next_payments.setColumnCount(3)
        self.next_payments.setHorizontalHeaderLabels(
            ["Fecha", "Proyecto", "Importe"]
        )
        self.prepare_table(self.next_payments)
        self.next_payments.setMinimumHeight(155)
        payment_layout.addWidget(self.next_payments)
        bottom.addWidget(payment_panel)

        layout.addLayout(bottom, 2)

    def create_card(self, title_text, value_label, description_text):
        card = QFrame()
        card.setObjectName("card")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 8, 16, 8)

        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        value_label.setObjectName("cardValue")
        description = QLabel(description_text)
        description.setObjectName("cardDescription")

        card_layout.addWidget(title)
        card_layout.addWidget(value_label)
        card_layout.addStretch()
        card_layout.addWidget(description)

        return card

    def create_panel(self, title_text):
        panel = QFrame()
        panel.setObjectName("panel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 10, 16, 10)
        panel_layout.setSpacing(5)

        title = QLabel(title_text)
        title.setObjectName("panelTitle")
        panel_layout.addWidget(title)

        return panel, panel_layout

    def prepare_table(self, table):
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)

        # Fecha e importe ocupan lo justo; el proyecto, el resto. Si aun
        # así no cabe, el texto pasa a dos líneas en vez de cortarse.
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.ElideNone)
        table.setStyleSheet("QTableWidget::item { padding: 4px 9px; }")
        # La altura de cada fila se recalcula cuando cambia el ancho de las
        # columnas (una línea si cabe, dos si no).
        header.sectionResized.connect(lambda *_: self.fit_rows(table))

    def refresh(self):
        session = get_session()

        try:
            projects = (
                session.query(Project)
                .order_by(Project.name.asc())
                .all()
            )

            initial_balance_setting = session.get(
                AppSetting,
                "initial_cash_balance",
            )

            try:
                company_initial_balance = (
                    float(initial_balance_setting.value)
                    if initial_balance_setting is not None
                    else 0.0
                )
            except (TypeError, ValueError):
                company_initial_balance = 0.0

            for label, key in (
                (self.user_label, "user_name"),
                (self.role_label, "user_role"),
            ):
                text = cashflow.get_setting(session, key)
                label.setText(text)
                label.setVisible(bool(text))

            current_project_id = self.selected_project_id

            self.project_filter.blockSignals(True)
            self.project_filter.clear()
            self.project_filter.addItem(
                "Todos los proyectos",
                None,
            )

            for project in projects:
                self.project_filter.addItem(
                    project.name,
                    project.id,
                )

            selected_index = self.project_filter.findData(
                current_project_id
            )

            if selected_index < 0:
                selected_index = 0
                self.selected_project_id = None

            self.project_filter.setCurrentIndex(
                selected_index
            )
            self.project_filter.blockSignals(False)
            # Financiación solo pertenece a la vista global de empresa.
            loans = (
                session.query(Loan).all()
                if self.selected_project_id is None
                else []
            )

            collections_query = (
                session.query(Collection, Order, Project)
                .join(
                    Order,
                    Collection.order_id == Order.id,
                )
                .join(
                    Project,
                    Order.project_id == Project.id,
                )
            )

            expenses_query = (
                session.query(Expense, Project)
                .outerjoin(
                    Project,
                    Expense.project_id == Project.id,
                )
            )

            if self.selected_project_id is not None:
                collections_query = collections_query.filter(
                    Project.id == self.selected_project_id
                )
                expenses_query = expenses_query.filter(
                    Expense.project_id == self.selected_project_id
                )

            collections = collections_query.all()
            expenses = expenses_query.all()

            # =====================================================
            # RESULTADO DEL EJERCICIO (sin IVA)
            # =====================================================
            selected_year = self.year_filter.currentData()
            today = date.today()
            year_end = date(selected_year, 12, 31)
            actual_income = 0.0
            forecast_income = 0.0
            for collection, order, project in collections:
                if not cashflow.collection_counts(collection, order):
                    continue
                amount = collection.amount or 0.0
                if collection.invoice_date is not None and collection.invoice_date.year == selected_year:
                    actual_income += amount
                    forecast_income += amount
                elif collection.invoice_date is None and collection.expected_date is not None and collection.expected_date.year == selected_year:
                    forecast_income += amount
            actual_expenses = 0.0
            forecast_expenses = 0.0
            categories = defaultdict(float)
            for expense, project in expenses:
                if expense.status in ("Cancelado", "Inactivo"):
                    continue
                base_amount = expense.base_amount or 0.0
                for movement_date in cashflow.expense_dates(
                    expense, project, today=today, until=year_end
                ):
                    if movement_date.year != selected_year:
                        continue
                    forecast_expenses += base_amount
                    categories[expense.category] += base_amount
                    if movement_date <= today:
                        actual_expenses += base_amount
            actual_result = actual_income - actual_expenses
            forecast_result = forecast_income - forecast_expenses
            # =====================================================
            # TESORERÍA (motor central, igual que la página Tesorería)
            # =====================================================
            global_view = self.selected_project_id is None
            movements = cashflow.build_movements(
                collections,
                expenses,
                loans,
                with_vat=global_view,
                vat_settlement=global_view,
                vat_registered=(
                    cashflow.load_vat_registered(session) if global_view else None
                ),
                today=today,
            )
            summary = cashflow.summarize(
                movements,
                company_initial_balance if global_view else 0.0,
                today,
            )
            collection_rows = [
                (m.date, m.project, m.amount_in)
                for m in movements
                if m.amount_in and not m.realized
            ]
            payment_rows = [
                (
                    m.date,
                    m.project if m.kind == "Pago" else m.kind,
                    m.amount_out,
                )
                for m in movements
                if m.amount_out and not m.realized
            ]
            active_statuses = {
                "En curso",
                "Activo",
                "En ejecución",
            }

            if self.selected_project_id is None:
                active_projects = sum(
                    1
                    for project in projects
                    if project.status in active_statuses
                )
            else:
                active_projects = sum(
                    1
                    for project in projects
                    if (
                        project.id
                        == self.selected_project_id
                        and project.status in active_statuses
                    )
                )

        finally:
            session.close()

        self.actual_result_value.setText(self.money(actual_result))
        self.forecast_result_value.setText(self.money(forecast_result))
        self.result_income_value.setText(self.money(forecast_income))
        self.result_expense_value.setText(self.money(forecast_expenses))
        self.cashflow_chart.set_hidden(not self.amounts_visible)
        self.expense_chart.set_hidden(not self.amounts_visible)
        self.balance_value.setText(
            self.money(summary.real_balance)
        )
        self.collections_value.setText(
            self.money(summary.pending_in)
        )
        self.payments_value.setText(
            self.money(summary.pending_out)
        )
        self.projects_value.setText(
            str(active_projects)
        )

        selected_project = next(
            (p for p in projects if p.id == self.selected_project_id), None
        )
        chart_end_date = (
            getattr(selected_project, "calculation_end_date", None)
            if selected_project is not None else None
        )
        self.fill_cashflow(
            summary,
            chart_end_date,
        )
        self.expense_chart.set_data(
            categories
        )

        self.fill_upcoming(
            self.next_collections,
            collection_rows,
        )

        self.fill_upcoming(
            self.next_payments,
            payment_rows,
        )

    def toggle_amounts(self):
        self.amounts_visible = not self.amounts_visible
        self.amounts_button.setText(
            "Ocultar importes" if self.amounts_visible else "Mostrar importes"
        )
        self.refresh()

    def result_year_changed(self):
        self.refresh()
    def project_filter_changed(self):

        self.selected_project_id = (
            self.project_filter.currentData()
        )

        self.refresh()

    @staticmethod
    def expense_months(expense, project=None):
        """Compatibilidad: usa el cálculo central de mensualidades."""
        return cashflow.expense_dates(expense, project)
    def fill_cashflow(
        self,
        summary,
        end_date=None,
    ):
        """
        Evolución del saldo mes a mes.

        * Vista global o proyecto sin fecha fin: los meses del horizonte
          de previsión (12) desde el mes
          actual, partiendo del saldo actual real. Lo vencido pendiente
          se suma en el mes actual.
        * Proyecto con fecha fin de cálculo: todo el periodo del proyecto
          desde 0 €, con movimientos reales y previstos.
        """
        today = date.today()
        names = cashflow.MONTH_SHORT
        months = []
        if end_date is not None:
            keys = [
                key for key, values in summary.all_monthly.items()
                if values["in"] or values["out"]
            ]
            if keys:
                first = min(keys)
                last = max(max(keys), (end_date.year, end_date.month))
            else:
                first = last = (end_date.year, end_date.month)
            year, month = first
            running_balance = summary.opening_balance
            while (year, month) <= last:
                values = summary.all_monthly.get(
                    (year, month), {"in": 0.0, "out": 0.0}
                )
                running_balance = cashflow.add_money(
                    running_balance, values["in"], -values["out"]
                )
                months.append({
                    "label": f"{names[month]}-{str(year)[2:]}",
                    "in": values["in"],
                    "out": values["out"],
                    "balance": running_balance,
                })
                month += 1
                if month == 13:
                    month = 1
                    year += 1
        else:
            running_balance = summary.real_balance
            year, month = today.year, today.month
            # Solo el horizonte de previsión: más allá no se generan los
            # gastos mensuales sin fecha fin (nóminas…) y el saldo saldría
            # artificialmente alto.
            for index in range(cashflow.FORECAST_MONTHS):
                values = summary.monthly.get(
                    (year, month), {"in": 0.0, "out": 0.0}
                )
                money_in = values["in"]
                money_out = values["out"]
                if index == 0:
                    money_in = cashflow.add_money(money_in, summary.overdue_in)
                    money_out = cashflow.add_money(money_out, summary.overdue_out)
                running_balance = cashflow.add_money(
                    running_balance, money_in, -money_out
                )
                months.append({
                    "label": f"{names[month]}-{str(year)[2:]}",
                    "in": money_in,
                    "out": money_out,
                    "balance": running_balance,
                })
                month += 1
                if month == 13:
                    month = 1
                    year += 1
        self.cashflow_chart.set_data(months)
    @fills("table")
    def fill_upcoming(self, table, rows):
        rows = [
            row for row in rows
            if row[0] is not None
        ]
        rows.sort(key=lambda row: row[0])
        rows = rows[:5]

        table.setRowCount(len(rows))

        for index, (movement_date, project, amount) in enumerate(rows):
            values = [
                movement_date.strftime("%d/%m/%Y"),
                project,
                self.money(amount),
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)

                if column == 2:
                    item.setTextAlignment(
                        Qt.AlignRight | Qt.AlignVCenter
                    )

                table.setItem(index, column, item)

        self.fit_rows(table)

    @staticmethod
    def fit_rows(table):
        # resizeRowsToContents() también aplica la altura de la cabecera de
        # filas (oculta, pero con el relleno del estilo global): se ajusta
        # cada fila a lo que necesita su texto.
        for row in range(table.rowCount()):
            table.setRowHeight(row, table.sizeHintForRow(row))

    def money(self, value):
        if not self.amounts_visible:
            return HIDDEN_MONEY
        return cashflow.money(value)
