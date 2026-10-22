"""
Motor de tesorería de Control de Caja.

TODAS las pantallas (Dashboard, Tesorería, Proyectos, Pagos) calculan
fechas, importes y saldos a través de este módulo, para que las cifras
coincidan siempre.

Reglas:

* Saldo real   = capital inicial + todo lo cobrado - todo lo pagado.
* Cobros       = importe (base) + IVA del cobro (21 % por defecto).
                 Real si su estado es "Cobrado".
* Gastos únicos  real si su estado es "Pagado"; si no, pendiente.
* Gastos mensuales (de proyecto y generales): cada mensualidad cuya
  fecha ya ha llegado se considera pagada automáticamente; las futuras
  quedan pendientes. Si el gasto está marcado "Pagado", todo es real.
* Préstamos (domiciliados): el capital entra en su fecha de ingreso y
  cada cuota se considera pagada automáticamente al llegar su fecha.
* IVA (modelo 303): en la vista global se prevé la liquidación de cada
  trimestre (IVA repercutido - IVA soportado) el día 20 del mes
  siguiente (30 de enero para el 4T). Un resultado negativo se compensa
  en los trimestres siguientes.
* Vista de un proyecto: parte de 0 € y trabaja SIN IVA (el IVA no es
  dinero del proyecto, se liquida con Hacienda).
* Lo pendiente con fecha anterior a hoy (o sin fecha) es "Vencido":
  no desaparece de la previsión, se muestra aparte.

Este módulo no depende de Qt, para poder probarlo de forma aislada.
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


DEFAULT_VAT_RATE = 21.0
FORECAST_MONTHS = 12

MONTH_NAMES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MONTH_SHORT = [
    "", "ene", "feb", "mar", "abr", "may", "jun", "jul",
    "ago", "sep", "oct", "nov", "dic",
]


# ============================================================
# IMPORTES
# ============================================================

_CENT = Decimal("0.01")


def round_money(value):
    """
    Redondeo comercial al céntimo (0,005 -> 0,01).

    `round()` de Python trabaja sobre el binario del float y redondea
    1,005 a 1,00; aquí se parte del texto del número para evitarlo.
    """
    if value is None:
        return None
    return float(Decimal(repr(float(value))).quantize(_CENT, rounding=ROUND_HALF_UP))


def add_money(*values) -> float:
    """Suma importes sin arrastrar errores de coma flotante."""
    return float(sum((Decimal(repr(float(v or 0.0))) for v in values), Decimal(0)))


# ============================================================
# FORMATO
# ============================================================

def money(value) -> str:
    """Formato español: 49.000,00 €"""
    text = f"{(value or 0.0):,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def date_text(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


# ============================================================
# FECHAS
# ============================================================

def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def first_of_month(value: date) -> date:
    return date(value.year, value.month, 1)


def monthly_dates(start: date, end: date) -> list[date]:
    """Una fecha por mes, conservando el día de `start`."""
    if start is None or end is None or end < start:
        return []
    dates = []
    index = 0
    while True:
        current = add_months(start, index)
        if _ym(current) > _ym(end):
            return dates
        dates.append(current)
        index += 1


def _ym(value: date):
    return value.year, value.month


def forecast_horizon_end(today: date) -> date:
    """Último día del último mes del horizonte de previsión."""
    last_month = add_months(first_of_month(today), FORECAST_MONTHS - 1)
    return date(last_month.year, last_month.month, monthrange(*_ym(last_month))[1])


def is_recurring(expense) -> bool:
    payment_type = getattr(expense, "payment_type", None) or "Único"
    if getattr(expense, "project_id", None) is None:
        # Los gastos generales son mensuales (nóminas, cuotas…) salvo las
        # facturas sueltas: "Único" y con fecha. Los antiguos, sin fecha,
        # siguen siendo mensuales.
        return not (
            payment_type == "Único"
            and getattr(expense, "expense_date", None) is not None
        )
    return payment_type == "Mensual"


def expense_dates(expense, project=None, today: date | None = None,
                  until: date | None = None) -> list[date]:
    """
    Fechas de cada pago de un gasto.

    * Único: fecha de pago si existe; si no, fecha del gasto.
    * Mensual de proyecto: de inicio a fin, limitado por la fecha fin de
      cálculo del proyecto. Sin fecha fin -> hasta el horizonte.
    * General (sin proyecto): desde "Activo desde" (o el mes actual si
      no se ha indicado) hasta su fecha fin o el horizonte.
    """
    today = today or date.today()
    horizon_end = until or forecast_horizon_end(today)

    if not is_recurring(expense):
        single = getattr(expense, "payment_date", None) or getattr(expense, "expense_date", None)
        return [single] if single else []

    start = getattr(expense, "recurrence_start", None)
    end = getattr(expense, "recurrence_end", None)

    if getattr(expense, "project_id", None) is None:
        if start is None:
            start = first_of_month(today)
        end = min(end, horizon_end) if end else horizon_end
    else:
        if start is None:
            return []
        limit = getattr(project, "calculation_end_date", None)
        if end is None:
            end = horizon_end
        if limit is not None:
            end = min(end, limit)

    return monthly_dates(start, end)


def expense_month_count(expense, project=None) -> int:
    """Número de mensualidades (1 para gastos únicos)."""
    if not is_recurring(expense):
        return 1
    return len(expense_dates(expense, project))


# ============================================================
# PRÉSTAMOS
# ============================================================

def loan_schedule(loan, today: date | None = None) -> list[dict]:
    """
    Cuotas de un préstamo usando la cuota mensual introducida.
    Como están domiciliadas, una cuota se considera pagada cuando llega
    su fecha (o si el contador manual de cuotas pagadas la incluye).
    """
    today = today or date.today()
    first = getattr(loan, "first_payment_date", None)
    months = int(getattr(loan, "term_months", 0) or 0)
    payment = float(getattr(loan, "monthly_payment", 0.0) or 0.0)
    principal = float(getattr(loan, "principal", 0.0) or 0.0)
    manual_paid = int(getattr(loan, "paid_installments", 0) or 0)
    finished = getattr(loan, "status", "") == "Finalizado"

    if not first or months <= 0 or payment <= 0:
        return []

    rows = []
    total_paid = 0.0
    for index in range(months):
        due = add_months(first, index)
        total_paid = add_money(total_paid, payment)
        rows.append({
            "index": index + 1,
            "date": due,
            "payment": payment,
            "principal": 0.0,
            "interest": 0.0,
            "balance": max(0.0, add_money(principal, -total_paid)),
            "paid": finished or due <= today or index < manual_paid,
        })
    return rows


def paid_installments(loan, today: date | None = None) -> int:
    return sum(1 for row in loan_schedule(loan, today) if row["paid"])


# ============================================================
# MOVIMIENTOS
# ============================================================

@dataclass
class Movement:
    date: date | None
    kind: str            # Cobro, Pago, Financiación, Cuota préstamo, IVA (303)
    project: str
    concept: str
    status: str
    amount_in: float = 0.0
    amount_out: float = 0.0
    realized: bool = False
    category: str | None = None
    project_id: int | None = None

    @property
    def net(self) -> float:
        return self.amount_in - self.amount_out


def collection_counts(collection, order=None) -> bool:
    """
    Si un cobro cuenta en tesorería, IVA y resultados: no si está cancelado,
    ni si su pedido está cancelado y el cobro no llegó a facturarse ni a
    cobrarse (lo facturado o cobrado sí es real y se mantiene).
    """
    if collection.status == "Cancelado":
        return False
    if getattr(order, "status", None) == "Cancelado":
        invoiced = bool((getattr(collection, "invoice_number", None) or "").strip())
        return collection.status == "Cobrado" or invoiced
    return True


def collection_vat_rate(collection) -> float:
    rate = getattr(collection, "vat_rate", None)
    return DEFAULT_VAT_RATE if rate is None else float(rate)


def collection_vat(collection) -> float:
    return round_money((collection.amount or 0.0) * collection_vat_rate(collection) / 100.0)


def collection_total(collection) -> float:
    return round_money(add_money(collection.amount, collection_vat(collection)))


def _expense_vat(expense) -> float:
    vat = getattr(expense, "vat_amount", None)
    if vat is not None:
        return float(vat)
    return add_money(expense.total_amount, -float(expense.base_amount or 0.0))


def build_movements(collections, expenses, loans=(), *, with_vat=True,
                    vat_settlement=True, vat_registered=None,
                    today: date | None = None) -> list[Movement]:
    """
    collections:    iterable de (Collection, Order, Project)
    expenses:       iterable de (Expense, Project | None)
    loans:          iterable de Loan
    vat_registered: {(año, trimestre): liquidación real} (ver vat_quarters)
    """
    today = today or date.today()
    collections = list(collections)
    expenses = list(expenses)
    movements: list[Movement] = []

    # ---------------- COBROS ----------------
    for collection, order, project in collections:
        if not collection_counts(collection, order):
            continue

        amount = collection_total(collection) if with_vat else (collection.amount or 0.0)

        if collection.status == "Cobrado":
            movement_date = (
                collection.collection_date
                or collection.expected_date
                or collection.invoice_date
            )
            realized = True
        else:
            movement_date = collection.expected_date
            realized = False

        movements.append(Movement(
            date=movement_date,
            kind="Cobro",
            project=project.name if project else "—",
            project_id=project.id if project else None,
            concept=collection.concept,
            status=collection.status,
            amount_in=amount,
            realized=realized,
        ))

    # ---------------- GASTOS ----------------
    for expense, project in expenses:
        if expense.status in ("Cancelado", "Inactivo"):
            continue

        amount = (expense.total_amount or 0.0) if with_vat else (expense.base_amount or 0.0)
        recurring = is_recurring(expense)
        paid_flag = expense.status == "Pagado"
        project_name = project.name if project is not None else "General / Empresa"

        dates = expense_dates(expense, project, today=today)
        if not dates and not recurring:
            # Gasto único sin fecha: queda como pendiente "sin fecha".
            dates = [None]

        for movement_date in dates:
            if paid_flag:
                realized = True
            elif recurring:
                realized = movement_date is not None and movement_date <= today
            else:
                realized = False

            if paid_flag or (recurring and realized):
                status = "Pagado"
            elif recurring:
                status = "Previsto"
            else:
                status = expense.status

            movements.append(Movement(
                date=movement_date,
                kind="Pago",
                project=project_name,
                project_id=getattr(project, "id", None),
                concept=expense.concept,
                status=status,
                amount_out=amount,
                realized=realized,
                category=expense.category,
            ))

    # ---------------- PRÉSTAMOS ----------------
    for loan in loans:
        if loan.status == "Cancelado":
            continue

        if loan.received_date:
            received = loan.received_date <= today
            movements.append(Movement(
                date=loan.received_date,
                kind="Financiación",
                project="Empresa",
                concept=f"{loan.name} · capital recibido",
                status="Cobrado" if received else "Previsto",
                amount_in=loan.principal or 0.0,
                realized=received,
            ))

        for row in loan_schedule(loan, today):
            movements.append(Movement(
                date=row["date"],
                kind="Cuota préstamo",
                project="Empresa",
                concept=f"{loan.name} · cuota {row['index']}",
                status="Pagado" if row["paid"] else "Previsto",
                amount_out=row["payment"],
                realized=row["paid"],
            ))

    # ---------------- IVA (303) ----------------
    if with_vat and vat_settlement:
        rows = vat_quarters(collections, expenses, vat_registered, today=today)
        movements.extend(_vat_settlements(rows))

    return movements


def _quarter(value: date):
    return value.year, (value.month - 1) // 3 + 1


def vat_due_date(year: int, quarter: int) -> date:
    if quarter == 4:
        return date(year + 1, 1, 30)
    return date(year, quarter * 3 + 1, 20)


def vat_by_quarter(collections, expenses, today: date | None = None):
    """
    IVA repercutido y soportado por trimestre: ({(año, t): cuota}, {...}).

    * Repercutido: devengo en la fecha de factura; si no hay, la prevista
      y, en último caso, la de cobro (ningún cobro queda fuera del 303).
    * Soportado: en la fecha de cada pago del gasto.
    """
    today = today or date.today()
    vat_output = defaultdict(float)
    vat_input = defaultdict(float)

    for collection, order, _project in collections:
        if not collection_counts(collection, order):
            continue
        accrual_date = (
            collection.invoice_date
            or collection.expected_date
            or collection.collection_date
        )
        if accrual_date:
            key = _quarter(accrual_date)
            vat_output[key] = add_money(vat_output[key], collection_vat(collection))

    for expense, project in expenses:
        if expense.status in ("Cancelado", "Inactivo"):
            continue
        for payment_date in expense_dates(expense, project, today=today):
            key = _quarter(payment_date)
            vat_input[key] = add_money(vat_input[key], _expense_vat(expense))

    return vat_output, vat_input


def vat_quarters(collections, expenses, registered=None, today: date | None = None) -> list[dict]:
    """
    Una fila por trimestre (consecutivos) con la estimación de la app y,
    si existe, la liquidación real que ha presentado la gestoría.

    registered: {(año, trimestre): objeto con .amount y .payment_date}.
      amount > 0  -> importe pagado (sustituye a la estimación).
      amount <= 0 -> resultado a compensar en los trimestres siguientes.

    Un resultado negativo (estimado o real) se compensa en los siguientes.
    """
    today = today or date.today()
    registered = registered or {}
    vat_output, vat_input = vat_by_quarter(collections, expenses, today)

    quarters = sorted(set(vat_output) | set(vat_input) | set(registered))
    if not quarters:
        return []

    rows = []
    carry = 0.0
    year, quarter = quarters[0]
    last = quarters[-1]
    while (year, quarter) <= last:
        key = (year, quarter)
        output = vat_output.get(key, 0.0)
        input_ = vat_input.get(key, 0.0)
        estimated = add_money(output, -input_, carry)
        due = vat_due_date(year, quarter)
        real = registered.get(key)

        if real is not None:
            result = round_money(real.amount or 0.0)
            payment_date = getattr(real, "payment_date", None) or due
        else:
            result = round_money(estimated)
            payment_date = due

        to_pay = result if result > 0.005 else 0.0
        realized = to_pay > 0 and payment_date <= today
        rows.append({
            "year": year,
            "quarter": quarter,
            "label": f"{quarter}T {year}",
            "output": output,
            "input": input_,
            "carry_in": carry,
            "estimated": round_money(estimated),
            "registered": real is not None,
            "result": result,
            "to_pay": to_pay,
            "due_date": due,
            "payment_date": payment_date,
            "realized": realized,
        })

        carry = 0.0 if result > 0.005 else result  # a compensar
        quarter += 1
        if quarter == 5:
            quarter = 1
            year += 1
    return rows


def _vat_settlements(rows):
    result = []
    for row in rows:
        if row["to_pay"] <= 0:
            continue
        result.append(Movement(
            date=row["payment_date"],
            kind="IVA (303)",
            project="Hacienda",
            concept=f"Liquidación IVA {row['label']}"
            + (" (gestoría)" if row["registered"] else ""),
            status="Pagado" if row["realized"] else "Previsto",
            amount_out=row["to_pay"],
            realized=row["realized"],
        ))
    return result


# ============================================================
# RESUMEN
# ============================================================

@dataclass
class CashSummary:
    opening_balance: float
    realized_in: float = 0.0
    realized_out: float = 0.0
    overdue_in: float = 0.0
    overdue_out: float = 0.0
    pending_in: float = 0.0       # incluye vencidos
    pending_out: float = 0.0      # incluye vencidos
    monthly: dict = field(default_factory=dict)       # pendientes futuros por (año, mes)
    all_monthly: dict = field(default_factory=dict)   # todo (real + pendiente) por (año, mes)
    overdue: list = field(default_factory=list)

    @property
    def real_balance(self) -> float:
        return add_money(self.opening_balance, self.realized_in, -self.realized_out)

    @property
    def projected_balance(self) -> float:
        return add_money(self.real_balance, self.pending_in, -self.pending_out)

    def forecast_rows(self, today: date | None = None, minimum_months: int = FORECAST_MONTHS):
        """
        Filas de previsión: primero "Vencido / sin fecha" (si hay) y luego
        cada mes desde el actual. Devuelve dicts con label, in, out, net,
        balance y beyond_horizon (meses posteriores al horizonte: solo
        llevan cobros y cuotas con fecha, no los gastos mensuales sin fin).
        """
        today = today or date.today()
        rows = []
        running = self.real_balance

        if self.overdue_in or self.overdue_out:
            running = add_money(running, self.overdue_in, -self.overdue_out)
            rows.append({
                "key": None,
                "label": "Vencido / sin fecha",
                "in": self.overdue_in,
                "out": self.overdue_out,
                "net": add_money(self.overdue_in, -self.overdue_out),
                "balance": running,
                "beyond_horizon": False,
            })

        keys = []
        current = first_of_month(today)
        for _ in range(minimum_months):
            keys.append(_ym(current))
            current = add_months(current, 1)
        for key in self.monthly:
            if key not in keys:
                keys.append(key)
        keys.sort()

        for year, month in keys:
            values = self.monthly.get((year, month), {"in": 0.0, "out": 0.0})
            running = add_money(running, values["in"], -values["out"])
            rows.append({
                "key": (year, month),
                "label": f"{MONTH_NAMES[month]} {year}",
                "in": values["in"],
                "out": values["out"],
                "net": add_money(values["in"], -values["out"]),
                "balance": running,
                "beyond_horizon": (year, month) > _ym(forecast_horizon_end(today)),
            })
        return rows


def summarize(movements, opening_balance=0.0, today: date | None = None) -> CashSummary:
    today = today or date.today()
    summary = CashSummary(opening_balance=opening_balance)
    monthly = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    all_monthly = defaultdict(lambda: {"in": 0.0, "out": 0.0})

    for movement in movements:
        if movement.date is not None:
            key = _ym(movement.date)
            all_monthly[key]["in"] = add_money(all_monthly[key]["in"], movement.amount_in)
            all_monthly[key]["out"] = add_money(all_monthly[key]["out"], movement.amount_out)

        if movement.realized:
            summary.realized_in = add_money(summary.realized_in, movement.amount_in)
            summary.realized_out = add_money(summary.realized_out, movement.amount_out)
            continue

        summary.pending_in = add_money(summary.pending_in, movement.amount_in)
        summary.pending_out = add_money(summary.pending_out, movement.amount_out)

        if movement.date is None or movement.date < today:
            summary.overdue_in = add_money(summary.overdue_in, movement.amount_in)
            summary.overdue_out = add_money(summary.overdue_out, movement.amount_out)
            summary.overdue.append(movement)
        else:
            key = _ym(movement.date)
            monthly[key]["in"] = add_money(monthly[key]["in"], movement.amount_in)
            monthly[key]["out"] = add_money(monthly[key]["out"], movement.amount_out)

    summary.monthly = dict(monthly)
    summary.all_monthly = dict(all_monthly)
    return summary


def sort_movements(movements):
    return sorted(movements, key=lambda m: (m.date is None, m.date or date.max, m.kind))


# ============================================================
# CARGA DESDE BASE DE DATOS
# ============================================================

def order_overrun(session, order_id, amount, status, collection=None):
    """
    Comprueba que los cobros de un pedido no pasen de su importe.

    Devuelve None si el cobro se puede guardar, o un dict con el importe
    del pedido, lo de los otros cobros y el total resultante si no.

    Un cobro que ya existía se puede guardar aunque el pedido ya esté
    superado (pedido rebajado después, datos antiguos) mientras el cambio
    no aumente lo cobrado: así se puede marcar como cobrado, cambiar
    fechas o notas de un cobro facturado, cuyo importe no se puede tocar.
    """
    from database.models import Collection, Order

    if status == "Cancelado":
        return None
    order = session.get(Order, order_id)
    if order is None:
        return None

    others = add_money(*(
        c.amount or 0.0
        for c in session.query(Collection).filter(
            Collection.order_id == order_id,
            Collection.status != "Cancelado",
        )
        if collection is None or c.id != collection.id
    ))
    total = add_money(others, amount)
    if total <= (order.amount or 0.0) + 0.01:
        return None

    if collection is not None:
        counted = collection.order_id == order_id and collection.status != "Cancelado"
        previous = (collection.amount or 0.0) if counted else 0.0
        if amount <= previous + 0.005:
            return None

    return {"order": order.amount or 0.0, "others": others, "total": total}


def get_setting(session, key, default=""):
    from database.models import AppSetting
    setting = session.get(AppSetting, key)
    return setting.value if setting is not None and setting.value is not None else default


def get_float_setting(session, key, default=0.0) -> float:
    try:
        return float(get_setting(session, key, default))
    except (TypeError, ValueError):
        return default


def load_vat_registered(session) -> dict:
    """Liquidaciones reales de IVA registradas: {(año, trimestre): fila}."""
    from database.models import VatSettlement
    return {(v.year, v.quarter): v for v in session.query(VatSettlement).all()}


def load_vat_quarters(session, today: date | None = None) -> list[dict]:
    """Tabla de trimestres de IVA (estimado y real) para la vista global."""
    from database.models import Collection, Expense, Order, Project

    collections = (
        session.query(Collection, Order, Project)
        .join(Order, Collection.order_id == Order.id)
        .join(Project, Order.project_id == Project.id)
        .all()
    )
    expenses = (
        session.query(Expense, Project)
        .outerjoin(Project, Expense.project_id == Project.id)
        .all()
    )
    return vat_quarters(collections, expenses, load_vat_registered(session), today=today)


def load_cashflow(session, project_id=None, today: date | None = None):
    """
    Carga datos y devuelve (movements, summary) para la vista global
    (project_id=None) o para un proyecto concreto.
    """
    from database.models import Collection, Expense, Loan, Order, Project

    today = today or date.today()

    collection_query = (
        session.query(Collection, Order, Project)
        .join(Order, Collection.order_id == Order.id)
        .join(Project, Order.project_id == Project.id)
    )
    expense_query = (
        session.query(Expense, Project)
        .outerjoin(Project, Expense.project_id == Project.id)
    )
    if project_id is not None:
        collection_query = collection_query.filter(Project.id == project_id)
        expense_query = expense_query.filter(Expense.project_id == project_id)

    global_view = project_id is None
    loans = session.query(Loan).all() if global_view else []

    movements = build_movements(
        collection_query.all(),
        expense_query.all(),
        loans,
        with_vat=global_view,
        vat_settlement=global_view,
        vat_registered=load_vat_registered(session) if global_view else None,
        today=today,
    )
    opening = get_float_setting(session, "initial_cash_balance") if global_view else 0.0
    return movements, summarize(movements, opening, today)
