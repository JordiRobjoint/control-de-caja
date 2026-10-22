from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_TITLE, APP_VERSION
from database.database import DATA_DIR, get_session
from services import invoices, manual
from ui.pages.proyectos import ProjectsPage
from ui.pages.project_detail import ProjectDetailPage
from ui.pages.dashboard import DashboardPage
from ui.pages.tesoreria import TreasuryPage
from ui.pages.configuracion import SettingsPage
from ui.pages.gastos_generales import GeneralExpensesPage
from ui.pages.pedidos import OrdersPage
from ui.pages.cobros import CollectionsPage
from ui.pages.pagos import PaymentsPage
from ui.pages.financiacion import FinancingPage
from ui.pages.clientes import ClientsPage


# ==============================================================
# VENTANA PRINCIPAL
# ==============================================================

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 900)
        self.setMinimumSize(1200, 720)

        self.setup_ui()
        self.apply_styles()

    # ==========================================================
    # INTERFAZ PRINCIPAL
    # ==========================================================

    def setup_ui(self):

        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")

        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ======================================================
        # SIDEBAR
        # ======================================================

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(265)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 25, 16, 25)
        sidebar_layout.setSpacing(6)

        # ------------------------------------------------------
        # LOGO
        # ------------------------------------------------------

        # Logo de la empresa (Configuración) o, si no hay, el nombre de
        # la aplicación. Se rellena en update_company().
        self.logo_label = QLabel()
        self.logo_label.setObjectName("logo")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setMinimumHeight(60)

        sidebar_layout.addWidget(self.logo_label)
        sidebar_layout.addSpacing(20)

        # ======================================================
        # STACK DE PÁGINAS
        # ======================================================

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")

        # IMPORTANTE:
        # Creamos cada página una única vez.

        self.dashboard_page = DashboardPage()

        self.projects_page = ProjectsPage()

        self.project_detail_page = ProjectDetailPage()

        self.orders_page = OrdersPage()

        self.collections_page = CollectionsPage()

        self.payments_page = PaymentsPage()

        self.general_expenses_page = GeneralExpensesPage()

        self.financing_page = FinancingPage()

        self.treasury_page = TreasuryPage()

        self.settings_page = SettingsPage()
        self.settings_page.saved.connect(self.update_company)
        self.clients_page = ClientsPage()

        # Añadir páginas al QStackedWidget

        self.pages.addWidget(self.dashboard_page)          # 0
        self.pages.addWidget(self.projects_page)           # 1
        self.pages.addWidget(self.orders_page)             # 2
        self.pages.addWidget(self.collections_page)        # 3
        self.pages.addWidget(self.payments_page)           # 4
        self.pages.addWidget(self.general_expenses_page)   # 5
        self.pages.addWidget(self.financing_page)          # 6
        self.pages.addWidget(self.treasury_page)           # 7
        self.pages.addWidget(self.settings_page)           # 8
        self.pages.addWidget(
            self.project_detail_page
        )   
        self.pages.addWidget(self.clients_page)            # 10

        # ======================================================
        # CONEXIONES ENTRE PÁGINAS
        # ======================================================

        self.projects_page.project_open_requested.connect(
            self.open_project
        )

        self.project_detail_page.back_requested.connect(
            lambda: self.change_page(1)
        )

        # ======================================================
        # MENÚ LATERAL
        # ======================================================

        menu_items = [
            ("⌂", "Dashboard", 0),
            ("▣", "Proyectos", 1),
            ("☺", "Clientes", 10),
            ("▤", "Pedidos", 2),
            ("↓", "Cobros", 3),
            ("↑", "Pagos", 4),
            ("◆", "Gastos generales", 5),
            ("€", "Financiación", 6),
            ("▥", "Tesorería", 7),
            ("⚙", "Configuración", 8),
        ]

        self.menu_buttons = []

        for icon, text, page_index in menu_items:

            button = QPushButton(
                f"{icon}     {text}"
            )

            button.setObjectName("menuButton")

            button.setCheckable(True)

            button.setCursor(
                Qt.PointingHandCursor
            )

            # Guardamos el índice directamente.
            button.setProperty(
                "page_index",
                page_index,
            )

            button.clicked.connect(
                self.menu_button_clicked
            )

            sidebar_layout.addWidget(button)

            self.menu_buttons.append(button)

        sidebar_layout.addStretch()

        manual_button = QPushButton("?     Manual de usuario")
        manual_button.setObjectName("menuButton")
        manual_button.setCursor(Qt.PointingHandCursor)
        manual_button.clicked.connect(self.open_manual)
        sidebar_layout.addWidget(manual_button)
        sidebar_layout.addSpacing(10)

        # ======================================================
        # PIE DEL SIDEBAR
        # ======================================================

        separator = QFrame()
        separator.setObjectName("redSeparator")
        separator.setFixedHeight(1)

        sidebar_layout.addWidget(separator)
        sidebar_layout.addSpacing(10)

        self.company_label = QLabel()
        self.company_label.setObjectName("company")
        self.company_label.setWordWrap(True)

        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("version")

        sidebar_layout.addWidget(self.company_label)
        sidebar_layout.addWidget(version)

        # ======================================================
        # LAYOUT GENERAL
        # ======================================================

        main_layout.addWidget(sidebar)

        main_layout.addWidget(
            self.pages,
            1,
        )

        self.update_company()

        # Página inicial
        self.change_page(0)

    # ==========================================================
    # EMPRESA (logo y nombre del menú)
    # ==========================================================

    def update_company(self):
        session = get_session()
        try:
            company = invoices.get_company(session)
            logo = invoices.get_invoice_settings(session)["company_logo"]
        finally:
            session.close()

        pixmap = QPixmap(logo) if logo and Path(logo).is_file() else QPixmap()
        if pixmap.isNull():
            self.logo_label.setPixmap(QPixmap())
            self.logo_label.setText(APP_TITLE)
            self.logo_label.setStyleSheet(
                "color: white; font-size: 22px; font-weight: 800;"
            )
        else:
            self.logo_label.setStyleSheet("")
            self.logo_label.setPixmap(pixmap.scaled(
                210, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation,
            ))
        self.company_label.setText(company["company_name"])
        self.dashboard_page.refresh()

    # ==========================================================
    # CLICK EN MENÚ
    # ==========================================================

    def menu_button_clicked(self):

        button = self.sender()

        if button is None:
            return

        page_index = button.property(
            "page_index"
        )

        self.change_page(
            int(page_index)
        )

    # ==========================================================
    # MANUAL DE USUARIO
    # ==========================================================

    def open_manual(self):
        # Se genera en cada apertura: así siempre es el de esta versión.
        path = DATA_DIR / "Manual de usuario.pdf"
        try:
            manual.render_manual_pdf(path, APP_VERSION)
        except Exception as error:
            # Si el PDF está abierto en otro programa no se puede
            # reescribir, pero el que hay sigue sirviendo.
            if not path.exists():
                QMessageBox.critical(
                    self,
                    "Manual de usuario",
                    f"No se ha podido generar el manual.\n\n{error}",
                )
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ==========================================================
    # ABRIR FICHA DE PROYECTO
    # ==========================================================

    def open_project(self, project_id):

        self.project_detail_page.load_project(
            project_id
        )

        self.pages.setCurrentWidget(
            self.project_detail_page
        )

        # Dejamos Proyectos marcado en el menú
        for i, button in enumerate(
            self.menu_buttons
        ):
            button.blockSignals(True)
            button.setChecked(button.property("page_index") == 1)
            button.blockSignals(False)

    # ==========================================================
    # CAMBIO DE PÁGINA
    # ==========================================================

    def change_page(self, index):

        if index < 0:
            return

        if index >= self.pages.count():
            return

        self.pages.setCurrentIndex(index)

        if index == 0:
            self.dashboard_page.refresh()

        if index == 2:
            self.orders_page.refresh()

        if index == 3:
            self.collections_page.refresh()

        if index == 4:
            self.payments_page.refresh()

        if index == 5:
            self.general_expenses_page.refresh()

        if index == 6:
            self.financing_page.refresh()

        if index == 7:
            self.treasury_page.refresh()

        if index == 8:
            self.settings_page.refresh()

        if index == 10:
            self.clients_page.refresh()

        for i, button in enumerate(
            self.menu_buttons
        ):

            button.blockSignals(True)

            # Los botones no van en el mismo orden que las páginas.
            button.setChecked(
                button.property("page_index") == index
            )

            button.blockSignals(False)

    # ==========================================================
    # ESTILOS
    # ==========================================================

    def apply_styles(self):

        self.setStyleSheet("""

        /* =====================================================
           GENERAL
        ===================================================== */

        QMainWindow {
            background-color: #090909;
        }

        QWidget {
            font-family: "Segoe UI";
            color: #F4F4F5;
        }

        #centralWidget {
            background-color: #090909;
        }

        #page {
            background-color: #0B0B0C;
        }

        #pages {
            background-color: #0B0B0C;
        }


        /* =====================================================
           SIDEBAR
        ===================================================== */

        #sidebar {

            background-color: #050505;

            border-right:
                1px solid #27272A;
        }


        #menuButton {

            background-color:
                transparent;

            color: #B7B7BA;

            border: none;

            border-radius: 8px;

            text-align: left;

            padding: 13px 15px;

            font-size: 14px;

            font-weight: 500;
        }


        #menuButton:hover {

            background-color: #18181B;

            color: white;
        }


        #menuButton:checked {

            background-color: #D71920;

            color: white;

            font-weight: 600;
        }


        #redSeparator {

            background-color: #D71920;
        }


        #company {

            color: #A1A1AA;

            font-size: 12px;
        }


        #version {

            color: #52525B;

            font-size: 11px;
        }


        /* =====================================================
           CABECERA
        ===================================================== */

        #pageTitle {

            color: #FFFFFF;

            font-size: 30px;

            font-weight: 700;
        }


        #pageSubtitle {

            color: #8B8B91;

            font-size: 14px;
        }


        #userName {

            color: white;

            font-size: 14px;

            font-weight: 600;
        }


        #userRole {

            color: #71717A;

            font-size: 12px;
        }


        /* =====================================================
           TARJETAS
        ===================================================== */

        #card {

            background-color: #121214;

            border:
                1px solid #29292D;

            border-radius: 12px;
        }


        #card:hover {

            border:
                1px solid #D71920;
        }


        #cardTitle {

            color: #A1A1AA;

            font-size: 13px;
        }


        #cardValue {

            color: white;

            font-size: 27px;

            font-weight: 700;
        }


        #cardDescription {

            color: #71717A;

            font-size: 12px;
        }


        /* =====================================================
           PANELES
        ===================================================== */

        #panel {

            background-color: #101012;

            border:
                1px solid #29292D;

            border-radius: 12px;
        }


        #panelTitle {

            color: white;

            font-size: 18px;

            font-weight: 600;
        }


        #panelDescription {

            color: #71717A;

            font-size: 13px;
        }


        /* =====================================================
           FORMULARIOS
        ===================================================== */

        QLineEdit,
        QComboBox,
        QDateEdit,
        QDoubleSpinBox,
        QTextEdit {

            background-color: #151517;

            color: #F4F4F5;

            border:
                1px solid #303034;

            border-radius: 7px;

            padding: 9px;

            font-size: 13px;
        }


        QLineEdit:focus,
        QComboBox:focus,
        QDateEdit:focus,
        QDoubleSpinBox:focus,
        QTextEdit:focus {

            border:
                1px solid #D71920;
        }


        #searchBox {

            min-height: 22px;
        }


        #filterCombo {

            min-width: 180px;
        }


        /* =====================================================
           BOTÓN PRINCIPAL
        ===================================================== */

        #primaryButton {

            background-color: #D71920;

            color: white;

            border: none;

            border-radius: 7px;

            padding: 11px 18px;

            font-size: 13px;

            font-weight: 600;
        }


        #primaryButton:hover {

            background-color: #EF252C;
        }


        #primaryButton:pressed {

            background-color: #B51218;
        }


        /* =====================================================
           TABLAS
        ===================================================== */

        QTableWidget {

            background-color: #101012;

            alternate-background-color:
                #131315;

            color: #E4E4E7;

            border: none;

            selection-background-color:
                #351114;

            selection-color: white;

            font-size: 13px;
        }


        QTableWidget::item {

            padding: 9px;

            border-bottom:
                1px solid #202024;
        }


        QHeaderView::section {

            background-color: #18181B;

            color: #A1A1AA;

            border: none;

            border-bottom:
                1px solid #303034;

            padding: 11px;

            font-size: 12px;

            font-weight: 600;
        }


        /* =====================================================
           DIÁLOGOS
        ===================================================== */

        QDialog {

            background-color: #101012;

            color: white;
        }


        #dialogTitle {

            color: white;

            font-size: 22px;

            font-weight: 700;
        }


        #dialogSubtitle {

            color: #8B8B91;

            font-size: 13px;
        }


        QDialogButtonBox QPushButton {

            background-color: #202024;

            color: white;

            border:
                1px solid #343438;

            border-radius: 7px;

            padding: 9px 16px;
        }


        QDialogButtonBox QPushButton:hover {

            border-color: #D71920;
        }

        /* =====================================================
        BOTONES SECUNDARIOS
        ===================================================== */

        #secondaryButton {

            background-color: #202024;
            color: #F4F4F5;

            border: 1px solid #343438;
            border-radius: 7px;

            padding: 11px 18px;

            font-size: 13px;
            font-weight: 600;
        }

        #secondaryButton:hover {

            background-color: #29292D;
            border-color: #71717A;
        }


        /* =====================================================
        BOTÓN ELIMINAR
        ===================================================== */

        #dangerButton {

            background-color: transparent;
            color: #EF4444;

            border: 1px solid #7F1D1D;
            border-radius: 7px;

            padding: 11px 18px;

            font-size: 13px;
            font-weight: 600;
        }

        #dangerButton:hover {

            background-color: #3F1012;
            border-color: #EF4444;
        }

        /* =====================================================
        FICHA PROYECTO
        ===================================================== */

        #backButton {
            background-color: transparent;
            color: #A1A1AA;
            border: none;
            padding: 5px 0px;
            font-size: 13px;
            font-weight: 600;
        }

        #backButton:hover {
            color: #FFFFFF;
        }


        #projectDetailTitle {
            color: #FFFFFF;
            font-size: 28px;
            font-weight: 700;
        }


        #projectMeta {
            color: #8B8B91;
            font-size: 13px;
        }


        #statusBadge {
            background-color: #351114;
            color: #FF646A;
            border: 1px solid #7F1D1D;
            border-radius: 8px;
            padding: 7px 13px;
            font-size: 11px;
            font-weight: 700;
        }


        #projectInfo {
            color: #D4D4D8;
            font-size: 13px;
        }


        /* =====================================================
        PESTAÑAS
        ===================================================== */

        QTabWidget::pane {
            background-color: #101012;
            border: 1px solid #29292D;
            border-radius: 10px;
            top: -1px;
        }


        QTabBar::tab {
            background-color: transparent;
            color: #8B8B91;
            padding: 12px 22px;
            border: none;
            font-size: 13px;
            font-weight: 600;
        }


        QTabBar::tab:hover {
            color: #FFFFFF;
        }


        QTabBar::tab:selected {
            color: #FFFFFF;
            border-bottom: 2px solid #D71920;
        }

        """)