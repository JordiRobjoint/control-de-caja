from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from services.cashflow import date_text, money
from database.database import get_session
from database.models import Order, Project
from ui.pages.dialogs.invoice_dialog import block_if_invoiced
from ui.pages.dialogs.order_dialog import OrderDialog
from ui.table_filters import ColumnFilters
from ui.table_utils import fills


class OrdersPage(QWidget):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(22)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Pedidos"); title.setObjectName("pageTitle")
        subtitle = QLabel("Vista global de los pedidos de todos los proyectos.")
        subtitle.setObjectName("pageSubtitle")
        titles.addWidget(title); titles.addWidget(subtitle)
        header.addLayout(titles); header.addStretch()

        self.project_filter = QComboBox()
        self.project_filter.setObjectName("filterCombo")
        self.project_filter.currentIndexChanged.connect(self.load_orders)
        header.addWidget(self.project_filter)

        for text, slot, obj in [
            ("Editar", self.edit_order, "secondaryButton"),
            ("Eliminar", self.delete_order, "dangerButton"),
            ("+  Nuevo pedido", self.new_order, "primaryButton"),
        ]:
            b = QPushButton(text); b.setObjectName(obj)
            b.setCursor(Qt.PointingHandCursor); b.clicked.connect(slot)
            header.addWidget(b)
        layout.addLayout(header)

        panel = QFrame(); panel.setObjectName("panel")
        pl = QVBoxLayout(panel); pl.setContentsMargins(22,20,22,20)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Proyecto", "Cliente", "Nº pedido", "Descripción",
            "Fecha", "Estado", "Importe"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for c in (4,5,6):
            self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self.edit_order)
        self.filters = ColumnFilters(self.table, self)
        pl.addWidget(self.filters.status_widget())
        pl.addWidget(self.table); layout.addWidget(panel, 1)

    def refresh(self):
        current = self.project_filter.currentData() if self.project_filter.count() else None
        s = get_session()
        try:
            projects = s.query(Project).order_by(Project.name).all()
            data = [(p.id, p.name) for p in projects]
        finally:
            s.close()
        self.project_filter.blockSignals(True)
        self.project_filter.clear(); self.project_filter.addItem("Todos los proyectos", None)
        for pid, name in data: self.project_filter.addItem(name, pid)
        idx = self.project_filter.findData(current)
        self.project_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.project_filter.blockSignals(False)
        self.load_orders()

    @fills("table")
    def load_orders(self):
        pid = self.project_filter.currentData()
        s = get_session()
        try:
            q = s.query(Order, Project).join(Project, Order.project_id == Project.id)
            if pid is not None: q = q.filter(Project.id == pid)
            results = q.order_by(Order.order_date.desc(), Order.id.desc()).all()
            self.rows = [{
                "id": o.id, "project_id": p.id, "project": p.name, "client": p.client,
                "number": o.order_number, "description": o.description or "",
                "date": o.order_date, "status": o.status, "amount": o.amount or 0,
            } for o,p in results]
        finally:
            s.close()
        self.table.setRowCount(len(self.rows))
        for r,x in enumerate(self.rows):
            vals=[x["project"],x["client"],x["number"],x["description"],date_text(x["date"]),x["status"],money(x["amount"])]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(str(v))
                if c==6: item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                self.table.setItem(r,c,item)
        self.filters.apply()

    def selected(self):
        r=self.table.currentRow()
        if r < 0 or r >= len(self.rows):
            QMessageBox.warning(self,"Selecciona un pedido","Selecciona primero un pedido.")
            return None
        return self.rows[r]

    def choose_project(self):
        pid = self.project_filter.currentData()
        if pid is not None: return pid
        s=get_session()
        try: projects=[(p.id,p.name) for p in s.query(Project).order_by(Project.name).all()]
        finally: s.close()
        if not projects:
            QMessageBox.warning(self,"No hay proyectos","Crea primero un proyecto.")
            return None
        from PySide6.QtWidgets import QInputDialog
        names=[n for _,n in projects]
        name,ok=QInputDialog.getItem(self,"Seleccionar proyecto","Proyecto:",names,0,False)
        if not ok: return None
        return dict((n,i) for i,n in projects)[name]

    def new_order(self):
        pid=self.choose_project()
        if pid is None: return
        d=OrderDialog(self)
        if d.exec()!=QDialog.Accepted: return
        data=d.get_data(); s=get_session()
        try:
            s.add(Order(project_id=pid, **data)); s.commit()
        except Exception as e:
            s.rollback(); QMessageBox.critical(self,"Error",f"No se ha podido guardar el pedido.\n\n{e}")
        finally: s.close()
        self.refresh()

    def edit_order(self):
        x=self.selected()
        if not x: return
        s=get_session()
        try:
            o=s.get(Order,x["id"]); d=OrderDialog(self,order=o)
            if d.exec()!=QDialog.Accepted: return
            for k,v in d.get_data().items(): setattr(o,k,v)
            s.commit()
        except Exception as e:
            s.rollback(); QMessageBox.critical(self,"Error",f"No se ha podido modificar el pedido.\n\n{e}")
        finally: s.close()
        self.refresh()

    def delete_order(self):
        x=self.selected()
        if not x: return
        if block_if_invoiced(self, "este pedido", order_id=x["id"]): return
        if QMessageBox.question(self,"Eliminar pedido",f"¿Eliminar el pedido '{x['number']}'?\n\nTambién se eliminarán sus cobros asociados.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        s=get_session()
        try:
            o=s.get(Order,x["id"])
            if o: s.delete(o); s.commit()
        except Exception as e:
            s.rollback(); QMessageBox.critical(self,"Error",str(e))
        finally: s.close()
        self.refresh()
