from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from database.database import Base
from services.cashflow import round_money


class Money(TypeDecorator):
    """
    Importe en euros. Se guarda como REAL (igual que antes, sin migración)
    pero siempre redondeado al céntimo al escribir y al leer.
    """
    impl = Float
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return round_money(value)

    def process_result_value(self, value, dialect):
        return round_money(value)


class Client(Base):
    """Ficha de cliente con sus datos fiscales (se usan en las facturas)."""
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="client_record"
    )

    @property
    def invoice_name(self) -> str:
        return self.legal_name or self.name


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    client: Mapped[str] = mapped_column(String(150), nullable=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    calculation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    client_tax_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    client_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="Planificado")
    estimated_value: Mapped[float] = mapped_column(Money, default=0.0)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    client_record: Mapped["Client | None"] = relationship(
        "Client", back_populates="projects"
    )
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="project", cascade="all, delete-orphan"
    )
    expenses: Mapped[list["Expense"]] = relationship(
        "Expense", back_populates="project", cascade="all, delete-orphan"
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    order_number: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="Pendiente")
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="orders")
    collections: Mapped[list["Collection"]] = relationship(
        "Collection", back_populates="order", cascade="all, delete-orphan"
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    concept: Mapped[str] = mapped_column(String(200), nullable=False)
    calculation_type: Mapped[str] = mapped_column(
        String(50), default="Porcentaje", nullable=False
    )
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="Previsto", nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    collection_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # IVA aplicado en la factura (None = 21 %) y ruta del PDF generado.
    vat_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoice_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="collections")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    concept: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)

    payment_type: Mapped[str] = mapped_column(
        String(50), default="Único", nullable=False
    )
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recurrence_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    recurrence_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    base_amount: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    vat_rate: Mapped[float] = mapped_column(Float, default=21.0, nullable=False)
    vat_amount: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)

    status: Mapped[str] = mapped_column(String(50), default="Pendiente", nullable=False)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Ticket o factura escaneada (ruta del archivo archivado)
    document_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    project: Mapped["Project | None"] = relationship("Project", back_populates="expenses")


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    bank: Mapped[str | None] = mapped_column(String(150), nullable=True)
    principal: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_interest_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    monthly_payment: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    first_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_installments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="Activo", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class VatSettlement(Base):
    """
    Liquidación real del IVA (modelo 303) de un trimestre, tal como la
    presenta la gestoría. Sustituye a la estimación de la app.
    amount > 0: importe pagado · amount <= 0: resultado a compensar.
    """
    __tablename__ = "vat_settlements"
    __table_args__ = (UniqueConstraint("year", "quarter", name="uq_vat_settlement_quarter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Money, default=0.0, nullable=False)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
