from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.cashflow import money as _money
from database.database import get_session
from database.models import Project
from services.clients import client_names, link_project
from ui.pages.dialogs.invoice_dialog import block_if_invoiced
from ui.table_utils import fills


# ==============================================================
# PÁGINA DE PROYECTOS
# ==============================================================

class ProjectsPage(QWidget):

    # Señal para solicitar a MainWindow que abra un proyecto
    project_open_requested = Signal(int)

    def __init__(self):
        super().__init__()

        self.projects = []
        self.visible_projects = []

        self.setup_ui()
        self.load_projects()

    # ==========================================================
    # INTERFAZ
    # ==========================================================

    def setup_ui(self):

        self.setObjectName("page")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 35, 40, 35)
        main_layout.setSpacing(25)

        # ======================================================
        # CABECERA
        # ======================================================

        header = QHBoxLayout()

        titles = QVBoxLayout()

        title = QLabel("Proyectos")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Gestiona los proyectos y trabajos de la empresa."
        )
        subtitle.setObjectName("pageSubtitle")

        titles.addWidget(title)
        titles.addWidget(subtitle)

        header.addLayout(titles)
        header.addStretch()

        # ======================================================
        # BOTONES DE ACCIÓN
        # ======================================================

        edit_button = QPushButton("Editar")
        edit_button.setObjectName("secondaryButton")
        edit_button.setCursor(Qt.PointingHandCursor)
        edit_button.clicked.connect(self.edit_project)

        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self.delete_project)

        new_button = QPushButton("+  Nuevo proyecto")
        new_button.setObjectName("primaryButton")
        new_button.setCursor(Qt.PointingHandCursor)
        new_button.clicked.connect(self.new_project)

        header.addWidget(edit_button)
        header.addWidget(delete_button)
        header.addWidget(new_button)

        main_layout.addLayout(header)

        # ======================================================
        # BUSCADOR Y FILTRO
        # ======================================================

        search_container = QHBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Buscar por proyecto, cliente o referencia..."
        )
        self.search.setObjectName("searchBox")
        self.search.setClearButtonEnabled(True)

        self.search.textChanged.connect(
            self.filter_projects
        )

        search_container.addWidget(self.search)

        self.status_filter = QComboBox()
        self.status_filter.setObjectName("filterCombo")

        self.status_filter.addItems([
            "Todos los estados",
            "Planificado",
            "En curso",
            "Finalizado",
            "Cancelado",
        ])

        self.status_filter.currentTextChanged.connect(
            self.filter_projects
        )

        search_container.addWidget(
            self.status_filter
        )

        main_layout.addLayout(
            search_container
        )

        # ======================================================
        # TABLA
        # ======================================================

        table_container = QFrame()
        table_container.setObjectName("panel")

        table_layout = QVBoxLayout(
            table_container
        )

        table_layout.setContentsMargins(
            1,
            1,
            1,
            1,
        )

        self.table = QTableWidget()

        self.table.setColumnCount(8)

        self.table.setHorizontalHeaderLabels([
            "Proyecto",
            "Cliente",
            "Referencia",
            "Inicio",
            "Fin",
            "Límite cálculo",
            "Estado",
            "Valor estimado",
        ])

        self.table.verticalHeader().setVisible(
            False
        )

        self.table.setSelectionBehavior(
            QTableWidget.SelectRows
        )

        self.table.setSelectionMode(
            QTableWidget.SingleSelection
        )

        self.table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        # Doble clic = abrir ficha del proyecto
        self.table.doubleClicked.connect(
            self.open_selected_project
        )

        self.table.setShowGrid(False)

        self.table.setAlternatingRowColors(
            True
        )

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )

        table_layout.addWidget(
            self.table
        )

        main_layout.addWidget(
            table_container
        )

    # ==========================================================
    # CARGAR PROYECTOS
    # ==========================================================

    def load_projects(self):

        session = get_session()

        try:

            projects = (
                session.query(Project)
                .order_by(Project.id.desc())
                .all()
            )

            self.projects = projects

            self.show_projects(
                projects
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Error",
                (
                    "No se han podido cargar los proyectos."
                    f"\n\n{error}"
                ),
            )

        finally:
            session.close()

    # ==========================================================
    # MOSTRAR PROYECTOS
    # ==========================================================

    @fills("table")
    def show_projects(self, projects):

        self.visible_projects = list(projects)

        # Crear exactamente las filas necesarias
        self.table.setRowCount(
            len(projects)
        )

        for row, project in enumerate(projects):

            values = [
                project.name,
                project.client,
                project.reference or "—",

                (
                    project.start_date.strftime(
                        "%d/%m/%Y"
                    )
                    if project.start_date
                    else "—"
                ),

                (
                    project.end_date.strftime(
                        "%d/%m/%Y"
                    )
                    if project.end_date
                    else "—"
                ),

                (project.calculation_end_date.strftime("%d/%m/%Y")
                 if project.calculation_end_date else "Sin límite"),
                project.status,

                _money(project.estimated_value),
            ]

            for column, value in enumerate(values):

                item = QTableWidgetItem(
                    str(value)
                )

                if column == 7:

                    item.setTextAlignment(
                        Qt.AlignRight
                        | Qt.AlignVCenter
                    )

                self.table.setItem(
                    row,
                    column,
                    item,
                )

        self.table.clearSelection()

    # ==========================================================
    # FILTRAR PROYECTOS
    # ==========================================================

    def filter_projects(self):

        search_text = (
            self.search
            .text()
            .lower()
            .strip()
        )

        selected_status = (
            self.status_filter.currentText()
        )

        filtered = []

        for project in self.projects:

            searchable = (
                f"{project.name} "
                f"{project.client} "
                f"{project.reference or ''}"
            ).lower()

            matches_search = (
                search_text in searchable
            )

            matches_status = (
                selected_status
                == "Todos los estados"
                or project.status
                == selected_status
            )

            if (
                matches_search
                and matches_status
            ):
                filtered.append(
                    project
                )

        self.show_projects(
            filtered
        )

    # ==========================================================
    # NUEVO PROYECTO
    # ==========================================================

    def new_project(self):

        dialog = ProjectDialog(
            self
        )

        if (
            dialog.exec()
            != QDialog.Accepted
        ):
            return

        data = dialog.get_data()

        session = get_session()

        try:

            project = Project(
                name=data["name"],
                client=data["client"],
                reference=data["reference"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                calculation_end_date=data["calculation_end_date"],
                status=data["status"],
                estimated_value=data[
                    "estimated_value"
                ],
                notes=data["notes"],
            )

            link_project(session, project, data["client"])
            session.add(project)
            session.commit()

        except Exception as error:

            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                (
                    "No se ha podido guardar "
                    "el proyecto."
                    f"\n\n{error}"
                ),
            )

            return

        finally:
            session.close()

        self.load_projects()

    # ==========================================================
    # EDITAR PROYECTO
    # ==========================================================

    def edit_project(self):

        row = self.table.currentRow()

        if row < 0:

            QMessageBox.warning(
                self,
                "Selecciona un proyecto",
                (
                    "Selecciona primero el proyecto "
                    "que quieres editar."
                ),
            )

            return

        if row >= len(
            self.visible_projects
        ):
            return

        selected_project = (
            self.visible_projects[row]
        )

        session = get_session()

        try:

            project = session.get(
                Project,
                selected_project.id,
            )

            if project is None:

                QMessageBox.warning(
                    self,
                    "Proyecto no encontrado",
                    (
                        "El proyecto ya no existe "
                        "en la base de datos."
                    ),
                )

                return

            dialog = ProjectDialog(
                self,
                project=project,
            )

            if (
                dialog.exec()
                != QDialog.Accepted
            ):
                return

            data = dialog.get_data()

            project.name = data["name"]
            link_project(session, project, data["client"])
            project.reference = data[
                "reference"
            ]
            project.start_date = data[
                "start_date"
            ]
            project.end_date = data[
                "end_date"
            ]
            project.calculation_end_date = data["calculation_end_date"]
            project.status = data[
                "status"
            ]
            project.estimated_value = data[
                "estimated_value"
            ]
            project.notes = data[
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
                    "el proyecto."
                    f"\n\n{error}"
                ),
            )

            return

        finally:
            session.close()

        self.load_projects()

    # ==========================================================
    # ELIMINAR PROYECTO
    # ==========================================================

    def delete_project(self):

        row = self.table.currentRow()

        if row < 0:

            QMessageBox.warning(
                self,
                "Selecciona un proyecto",
                (
                    "Selecciona primero el proyecto "
                    "que quieres eliminar."
                ),
            )

            return

        if row >= len(
            self.visible_projects
        ):
            return

        selected_project = (
            self.visible_projects[row]
        )

        if block_if_invoiced(self, "este proyecto", project_id=selected_project.id):
            return

        answer = QMessageBox.question(
            self,
            "Eliminar proyecto",
            (
                "¿Seguro que quieres eliminar "
                f"'{selected_project.name}'?"
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

            project = session.get(
                Project,
                selected_project.id,
            )

            if project is None:

                QMessageBox.warning(
                    self,
                    "Proyecto no encontrado",
                    (
                        "El proyecto ya no existe "
                        "en la base de datos."
                    ),
                )

                return

            session.delete(project)
            session.commit()

        except Exception as error:

            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                (
                    "No se ha podido eliminar "
                    "el proyecto."
                    f"\n\n{error}"
                ),
            )

            return

        finally:
            session.close()

        self.load_projects()

    # ==========================================================
    # ABRIR PROYECTO
    # ==========================================================

    def open_selected_project(self):

        row = self.table.currentRow()

        if row < 0:
            return

        if row >= len(
            self.visible_projects
        ):
            return

        project = (
            self.visible_projects[row]
        )

        self.project_open_requested.emit(
            project.id
        )


# ==============================================================
# FORMULARIO NUEVO / EDITAR PROYECTO
# ==============================================================

class ProjectDialog(QDialog):

    def __init__(
        self,
        parent=None,
        project=None,
    ):

        super().__init__(parent)

        self.project = project

        if project is None:
            self.setWindowTitle(
                "Nuevo proyecto"
            )
        else:
            self.setWindowTitle(
                "Editar proyecto"
            )

        self.setMinimumWidth(520)

        self.setup_ui()

        if self.project is not None:
            self.load_project_data()

    # ==========================================================
    # INTERFAZ DEL FORMULARIO
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

        if self.project is None:
            title_text = "Nuevo proyecto"
        else:
            title_text = "Editar proyecto"

        title = QLabel(
            title_text
        )

        title.setObjectName(
            "dialogTitle"
        )

        subtitle = QLabel(
            "Introduce la información principal "
            "del proyecto."
        )

        subtitle.setObjectName(
            "dialogSubtitle"
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # ======================================================
        # FORMULARIO
        # ======================================================

        form = QFormLayout()

        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(25)

        # Proyecto

        self.name = QLineEdit()

        self.name.setPlaceholderText(
            "Ej. Talleres Norte - Línea de montaje"
        )

        form.addRow(
            "Nombre del proyecto *",
            self.name,
        )

        # Cliente

        # Desplegable con las fichas de cliente. Si se escribe un nombre
        # nuevo, se crea su ficha al guardar el proyecto.
        self.client = QComboBox()
        self.client.setEditable(True)
        self.client.setInsertPolicy(QComboBox.NoInsert)
        self.client.lineEdit().setPlaceholderText(
            "Elige un cliente o escribe uno nuevo"
        )
        session = get_session()
        try:
            self.client.addItems(client_names(session))
        finally:
            session.close()
        self.client.setCurrentIndex(-1)

        form.addRow(
            "Cliente *",
            self.client,
        )

        # Referencia

        self.reference = QLineEdit()

        self.reference.setPlaceholderText(
            "Referencia interna / cliente"
        )

        form.addRow(
            "Referencia",
            self.reference,
        )

        # Fecha inicio

        self.start_date = QDateEdit()

        self.start_date.setCalendarPopup(
            True
        )

        self.start_date.setDisplayFormat(
            "dd/MM/yyyy"
        )

        self.start_date.setDate(
            QDate.currentDate()
        )

        form.addRow(
            "Fecha inicio",
            self.start_date,
        )

        # Fecha fin

        self.end_date = QDateEdit()

        self.end_date.setCalendarPopup(
            True
        )

        self.end_date.setDisplayFormat(
            "dd/MM/yyyy"
        )

        self.end_date.setDate(
            QDate.currentDate()
        )

        form.addRow(
            "Fecha fin",
            self.end_date,
        )

        # Límite de cálculo independiente del fin real.
        self.calculation_end_date = QDateEdit()
        self.calculation_end_date.setCalendarPopup(True)
        self.calculation_end_date.setDisplayFormat("dd/MM/yyyy")
        self.calculation_end_date.setDate(self.end_date.date())
        self.calculation_end_date.setSpecialValueText("Sin límite")
        self.calculation_end_date.setMinimumDate(QDate(2000, 1, 1))
        self.calculation_end_date.setDate(self.calculation_end_date.minimumDate())
        form.addRow("Fecha límite de cálculo", self.calculation_end_date)

        # Estado

        self.status = QComboBox()

        self.status.addItems([
            "Planificado",
            "En curso",
            "Finalizado",
            "Cancelado",
        ])

        form.addRow(
            "Estado",
            self.status,
        )

        # Valor estimado

        self.estimated_value = (
            QDoubleSpinBox()
        )

        self.estimated_value.setMaximum(
            999_999_999
        )

        self.estimated_value.setDecimals(
            2
        )

        self.estimated_value.setSuffix(
            " €"
        )

        self.estimated_value.setGroupSeparatorShown(
            True
        )

        form.addRow(
            "Valor estimado",
            self.estimated_value,
        )

        # Notas

        self.notes = QTextEdit()

        self.notes.setMaximumHeight(
            100
        )

        self.notes.setPlaceholderText(
            "Observaciones del proyecto..."
        )

        form.addRow(
            "Notas",
            self.notes,
        )

        layout.addLayout(form)

        # ======================================================
        # BOTONES
        # ======================================================

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save
            | QDialogButtonBox.Cancel
        )

        buttons.button(
            QDialogButtonBox.Save
        ).setText(
            "Guardar proyecto"
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
    # CARGAR DATOS AL EDITAR
    # ==========================================================

    def load_project_data(self):

        project = self.project

        self.name.setText(
            project.name or ""
        )

        self.client.setCurrentText(
            project.client or ""
        )

        self.reference.setText(
            project.reference or ""
        )

        if project.start_date:

            self.start_date.setDate(
                QDate(
                    project.start_date.year,
                    project.start_date.month,
                    project.start_date.day,
                )
            )

        if project.end_date:

            self.end_date.setDate(
                QDate(
                    project.end_date.year,
                    project.end_date.month,
                    project.end_date.day,
                )
            )

        if getattr(project, "calculation_end_date", None):
            d = project.calculation_end_date
            self.calculation_end_date.setDate(QDate(d.year, d.month, d.day))

        status_index = (
            self.status.findText(
                project.status
            )
        )

        if status_index >= 0:

            self.status.setCurrentIndex(
                status_index
            )

        self.estimated_value.setValue(
            project.estimated_value or 0
        )

        self.notes.setPlainText(
            project.notes or ""
        )

    # ==========================================================
    # VALIDACIÓN
    # ==========================================================

    def validate(self):

        if not self.name.text().strip():

            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Introduce el nombre del proyecto.",
            )

            return

        if not self.client.currentText().strip():

            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Introduce el cliente.",
            )

            return

        if (
            self.end_date.date()
            < self.start_date.date()
        ):

            QMessageBox.warning(
                self,
                "Fechas incorrectas",
                (
                    "La fecha de fin no puede ser "
                    "anterior a la fecha de inicio."
                ),
            )

            return

        self.accept()

    # ==========================================================
    # OBTENER DATOS
    # ==========================================================

    def get_data(self):

        return {
            "name":
                self.name.text().strip(),

            "client":
                self.client.currentText().strip(),

            "reference":
                self.reference.text().strip()
                or None,

            "start_date":
                self.start_date.date().toPython(),

            "end_date":
                self.end_date.date().toPython(),

            "calculation_end_date": (
                None if self.calculation_end_date.date() == self.calculation_end_date.minimumDate()
                else self.calculation_end_date.date().toPython()
            ),
            "status":
                self.status.currentText(),

            "estimated_value":
                self.estimated_value.value(),

            "notes":
                self.notes.toPlainText().strip()
                or None,
        }