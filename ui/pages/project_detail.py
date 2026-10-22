from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.cashflow import money as _money
from database.database import get_session
from database.models import Project

from ui.pages.project_detail_collections import CollectionsTabMixin
from ui.pages.project_detail_expenses import ExpensesTabMixin
from ui.pages.project_detail_orders import OrdersTabMixin


# ==============================================================
# FICHA DEL PROYECTO
# ==============================================================

class ProjectDetailPage(OrdersTabMixin, CollectionsTabMixin, ExpensesTabMixin, QWidget):

    back_requested = Signal()

    def __init__(self):
        super().__init__()

        self.project_id = None
        self.orders = []
        self.collections = []
        self.expenses = []

        self.setup_ui()

    # ==========================================================
    # INTERFAZ
    # ==========================================================

    def setup_ui(self):

        self.setObjectName("page")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 30, 40, 35)
        main_layout.setSpacing(22)

        # ======================================================
        # VOLVER
        # ======================================================

        self.back_button = QPushButton(
            "←  Volver a proyectos"
        )

        self.back_button.setObjectName(
            "backButton"
        )

        self.back_button.setCursor(
            Qt.PointingHandCursor
        )

        self.back_button.clicked.connect(
            self.back_requested.emit
        )

        main_layout.addWidget(
            self.back_button,
            alignment=Qt.AlignLeft,
        )

        # ======================================================
        # CABECERA
        # ======================================================

        header = QHBoxLayout()

        project_info = QVBoxLayout()

        self.project_name = QLabel(
            "Proyecto"
        )

        self.project_name.setObjectName(
            "projectDetailTitle"
        )

        self.project_meta = QLabel("")

        self.project_meta.setObjectName(
            "projectMeta"
        )

        project_info.addWidget(
            self.project_name
        )

        project_info.addWidget(
            self.project_meta
        )

        header.addLayout(
            project_info
        )

        header.addStretch()

        self.status_label = QLabel("")

        self.status_label.setObjectName(
            "statusBadge"
        )

        header.addWidget(
            self.status_label,
            alignment=Qt.AlignTop,
        )

        main_layout.addLayout(header)

        # ======================================================
        # TARJETAS
        # ======================================================

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        self.contracted_value = QLabel(
            "0,00 €"
        )

        self.collected_value = QLabel(
            "0,00 €"
        )

        self.expenses_value = QLabel(
            "0,00 €"
        )

        self.margin_value = QLabel(
            "0,00 €"
        )

        cards_layout.addWidget(
            self.create_card(
                "Contratado",
                self.contracted_value,
                "Importe total de pedidos",
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "Cobrado",
                self.collected_value,
                "Cobros realizados",
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "Gastos",
                self.expenses_value,
                "Costes del proyecto",
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "Margen",
                self.margin_value,
                "Contratado - gastos",
            )
        )

        main_layout.addLayout(
            cards_layout
        )

        # ======================================================
        # PESTAÑAS
        # ======================================================

        self.tabs = QTabWidget()

        self.tabs.setObjectName(
            "projectTabs"
        )

        self.tabs.addTab(
            self.create_summary_tab(),
            "Resumen",
        )

        self.tabs.addTab(
            self.create_orders_tab(),
            "Pedidos",
        )

        self.tabs.addTab(
            self.create_collections_tab(),
            "Cobros"
        )

        self.tabs.addTab(
            self.create_expenses_tab(),
            "Gastos",
        )

        main_layout.addWidget(
            self.tabs,
            1,
        )

    # ==========================================================
    # TARJETA
    # ==========================================================

    def create_card(
        self,
        title_text,
        value_label,
        description_text,
    ):

        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(125)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            20,
            16,
            20,
            16,
        )

        title = QLabel(title_text)
        title.setObjectName("cardTitle")

        value_label.setObjectName(
            "cardValue"
        )

        description = QLabel(
            description_text
        )

        description.setObjectName(
            "cardDescription"
        )

        layout.addWidget(title)
        layout.addWidget(value_label)
        layout.addStretch()
        layout.addWidget(description)

        return card

    # ==========================================================
    # RESUMEN
    # ==========================================================

    def create_summary_tab(self):

        widget = QWidget()

        layout = QVBoxLayout(widget)

        layout.setContentsMargins(
            25,
            25,
            25,
            25,
        )

        layout.setSpacing(18)

        title = QLabel(
            "Información del proyecto"
        )

        title.setObjectName(
            "panelTitle"
        )

        layout.addWidget(title)

        info_panel = QFrame()
        info_panel.setObjectName("panel")

        info_layout = QVBoxLayout(
            info_panel
        )

        info_layout.setContentsMargins(
            25,
            22,
            25,
            22,
        )

        info_layout.setSpacing(14)

        self.client_label = QLabel()
        self.reference_label = QLabel()
        self.dates_label = QLabel()
        self.estimated_label = QLabel()
        self.notes_label = QLabel()

        for label in [
            self.client_label,
            self.reference_label,
            self.dates_label,
            self.estimated_label,
            self.notes_label,
        ]:

            label.setObjectName(
                "projectInfo"
            )

            label.setWordWrap(True)

            info_layout.addWidget(
                label
            )

        layout.addWidget(info_panel)
        layout.addStretch()

        return widget

    # ==========================================================
    # CARGAR PROYECTO
    # ==========================================================

    def load_project(
        self,
        project_id,
    ):

        self.project_id = project_id

        session = get_session()

        try:

            project = session.get(
                Project,
                project_id,
            )

            if project is None:
                return

            # Cabecera

            self.project_name.setText(
                project.name
            )

            start = (
                project.start_date.strftime(
                    "%d/%m/%Y"
                )
                if project.start_date
                else "Sin fecha"
            )

            end = (
                project.end_date.strftime(
                    "%d/%m/%Y"
                )
                if project.end_date
                else "Sin fecha"
            )

            self.project_meta.setText(
                f"{project.client}   ·   "
                f"{start} → {end}"
            )

            self.status_label.setText(
                project.status.upper()
            )

            # Resumen

            self.client_label.setText(
                f"Cliente:  {project.client}"
            )

            self.reference_label.setText(
                "Referencia:  "
                f"{project.reference or '—'}"
            )

            self.dates_label.setText(
                f"Duración:  {start} → {end} | Límite de cálculo: "
                f"{project.calculation_end_date.strftime('%d/%m/%Y') if project.calculation_end_date else 'Sin límite'}"
            )

            self.estimated_label.setText(
                f"Valor estimado:  {_money(project.estimated_value)}"
            )

            self.notes_label.setText(
                "Notas:  "
                f"{project.notes or 'Sin observaciones'}"
            )

        finally:
            session.close()

        # Pedidos, cobros y gastos
        self.load_orders()
        self.load_collections()
        self.load_expenses()
