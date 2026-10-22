"""Tests del motor de tesorería (services/cashflow.py)."""

from datetime import date
from types import SimpleNamespace

import pytest

from services import cashflow as cf
from services.cashflow import Movement


TODAY = date(2026, 10, 13)


def make_collection(**kw):
    data = dict(
        amount=1000.0, vat_rate=None, status="Previsto", concept="Hito",
        expected_date=None, invoice_date=None, collection_date=None,
    )
    data.update(kw)
    return SimpleNamespace(**data)


def make_expense(**kw):
    data = dict(
        project_id=1, payment_type="Único", status="Pendiente", concept="Gasto",
        category="Otros", payment_date=None, expense_date=None,
        recurrence_start=None, recurrence_end=None,
        base_amount=100.0, vat_amount=21.0, total_amount=121.0,
    )
    data.update(kw)
    return SimpleNamespace(**data)


def make_project(**kw):
    data = dict(id=1, name="Proyecto A", calculation_end_date=None)
    data.update(kw)
    return SimpleNamespace(**data)


def make_loan(**kw):
    data = dict(
        name="ICO", principal=300.0, received_date=None,
        first_payment_date=date(2026, 1, 10), term_months=3,
        monthly_payment=100.0, paid_installments=0, status="Activo",
    )
    data.update(kw)
    return SimpleNamespace(**data)


# ============================================================
# FORMATO
# ============================================================

@pytest.mark.parametrize("value, expected", [
    (49000, "49.000,00 €"),
    (1234567.891, "1.234.567,89 €"),
    (-1234.5, "-1.234,50 €"),
    (0, "0,00 €"),
    (None, "0,00 €"),
])
def test_money_formato_espanol(value, expected):
    assert cf.money(value) == expected


def test_date_text():
    assert cf.date_text(date(2026, 3, 5)) == "05/03/2026"
    assert cf.date_text(None) == "—"


# ============================================================
# FECHAS
# ============================================================

@pytest.mark.parametrize("start, months, expected", [
    (date(2026, 1, 31), 1, date(2026, 2, 28)),
    (date(2028, 1, 31), 1, date(2028, 2, 29)),   # bisiesto
    (date(2026, 11, 15), 3, date(2027, 2, 15)),  # cambio de año
    (date(2026, 1, 15), -1, date(2025, 12, 15)),
    (date(2026, 5, 31), 0, date(2026, 5, 31)),
])
def test_add_months(start, months, expected):
    assert cf.add_months(start, months) == expected


def test_monthly_dates_conserva_el_dia_de_inicio():
    # Tras febrero vuelve al día 31: siempre se calcula desde `start`.
    assert cf.monthly_dates(date(2026, 1, 31), date(2026, 4, 1)) == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30),
    ]


def test_monthly_dates_casos_vacios():
    assert cf.monthly_dates(date(2026, 5, 1), date(2026, 4, 1)) == []
    assert cf.monthly_dates(None, date(2026, 4, 1)) == []
    assert cf.monthly_dates(date(2026, 4, 1), None) == []


def test_forecast_horizon_end_son_12_meses():
    assert cf.forecast_horizon_end(TODAY) == date(2027, 9, 30)


# ============================================================
# GASTOS
# ============================================================

def test_is_recurring():
    assert cf.is_recurring(make_expense(project_id=None, payment_type="Único"))
    assert cf.is_recurring(make_expense(payment_type="Mensual"))
    assert not cf.is_recurring(make_expense(payment_type="Único"))
    assert not cf.is_recurring(make_expense(payment_type=None))


def test_gasto_unico_usa_fecha_de_pago_antes_que_fecha_de_gasto():
    expense = make_expense(payment_date=date(2026, 3, 1), expense_date=date(2026, 2, 1))
    assert cf.expense_dates(expense, today=TODAY) == [date(2026, 3, 1)]
    expense = make_expense(expense_date=date(2026, 2, 1))
    assert cf.expense_dates(expense, today=TODAY) == [date(2026, 2, 1)]
    assert cf.expense_dates(make_expense(), today=TODAY) == []


def test_gasto_general_sin_inicio_empieza_en_el_mes_actual():
    expense = make_expense(project_id=None)
    dates = cf.expense_dates(expense, today=TODAY)
    assert dates[0] == date(2026, 10, 1)
    assert dates[-1] == date(2027, 9, 1)
    assert len(dates) == 12


def test_gasto_general_con_fecha_fin():
    expense = make_expense(
        project_id=None, recurrence_start=date(2026, 9, 5), recurrence_end=date(2026, 11, 20)
    )
    assert cf.expense_dates(expense, today=TODAY) == [
        date(2026, 9, 5), date(2026, 10, 5), date(2026, 11, 5),
    ]


def test_gasto_mensual_de_proyecto():
    project = make_project(calculation_end_date=date(2026, 3, 31))
    expense = make_expense(payment_type="Mensual", recurrence_start=date(2026, 1, 15))
    assert cf.expense_dates(expense, project, today=TODAY) == [
        date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15),
    ]
    # Sin fecha de inicio no genera pagos.
    assert cf.expense_dates(make_expense(payment_type="Mensual"), project, today=TODAY) == []


def test_expense_month_count():
    assert cf.expense_month_count(make_expense()) == 1
    expense = make_expense(
        payment_type="Mensual",
        recurrence_start=date(2026, 1, 1),
        recurrence_end=date(2026, 6, 30),
    )
    assert cf.expense_month_count(expense, make_project()) == 6


# ============================================================
# PRÉSTAMOS
# ============================================================

def test_loan_schedule_cuotas_pagadas_al_llegar_su_fecha():
    rows = cf.loan_schedule(make_loan(), today=date(2026, 2, 10))
    assert [r["date"] for r in rows] == [date(2026, 1, 10), date(2026, 2, 10), date(2026, 3, 10)]
    assert [r["paid"] for r in rows] == [True, True, False]
    assert [r["balance"] for r in rows] == [200.0, 100.0, 0.0]
    assert cf.paid_installments(make_loan(), today=date(2026, 2, 10)) == 2


def test_loan_schedule_contador_manual_y_finalizado():
    rows = cf.loan_schedule(make_loan(paid_installments=3), today=date(2025, 1, 1))
    assert all(r["paid"] for r in rows)
    rows = cf.loan_schedule(make_loan(status="Finalizado"), today=date(2025, 1, 1))
    assert all(r["paid"] for r in rows)


def test_loan_schedule_datos_incompletos():
    assert cf.loan_schedule(make_loan(first_payment_date=None)) == []
    assert cf.loan_schedule(make_loan(term_months=0)) == []
    assert cf.loan_schedule(make_loan(monthly_payment=0)) == []


# ============================================================
# IVA DE COBROS
# ============================================================

def test_iva_del_cobro():
    assert cf.collection_vat(make_collection()) == 210.0
    assert cf.collection_total(make_collection()) == 1210.0
    assert cf.collection_vat(make_collection(vat_rate=10)) == 100.0
    assert cf.collection_total(make_collection(vat_rate=0)) == 1000.0
    assert cf.collection_total(make_collection(amount=None)) == 0.0


# ============================================================
# MOVIMIENTOS
# ============================================================

def _build(collections=(), expenses=(), loans=(), **kw):
    kw.setdefault("today", TODAY)
    return cf.build_movements(collections, expenses, loans, **kw)


def test_cobro_cobrado_es_real_con_iva():
    collection = make_collection(
        status="Cobrado", collection_date=date(2026, 9, 1), expected_date=date(2026, 8, 1)
    )
    (movement,) = _build([(collection, None, make_project())], vat_settlement=False)
    assert movement.kind == "Cobro"
    assert movement.date == date(2026, 9, 1)
    assert movement.amount_in == 1210.0
    assert movement.realized
    assert movement.project == "Proyecto A"


def test_cobro_pendiente_usa_fecha_prevista_y_sin_iva_en_vista_de_proyecto():
    collection = make_collection(expected_date=date(2026, 12, 1))
    (movement,) = _build([(collection, None, make_project())], with_vat=False)
    assert movement.date == date(2026, 12, 1)
    assert movement.amount_in == 1000.0
    assert not movement.realized


def test_cobro_cancelado_se_ignora():
    collection = make_collection(status="Cancelado", expected_date=date(2026, 12, 1))
    assert _build([(collection, None, make_project())]) == []


def test_gasto_unico():
    project = make_project()
    paid = make_expense(status="Pagado", payment_date=date(2026, 5, 1))
    pending = make_expense(status="Pendiente", expense_date=date(2026, 11, 1))
    undated = make_expense(status="Pendiente")
    cancelled = make_expense(status="Cancelado", expense_date=date(2026, 11, 1))

    movements = _build(
        expenses=[(paid, project), (pending, project), (undated, project), (cancelled, project)],
        vat_settlement=False,
    )
    assert [(m.date, m.status, m.realized, m.amount_out) for m in movements] == [
        (date(2026, 5, 1), "Pagado", True, 121.0),
        (date(2026, 11, 1), "Pendiente", False, 121.0),
        (None, "Pendiente", False, 121.0),
    ]


def test_gasto_general_mensual_se_paga_al_llegar_la_fecha():
    expense = make_expense(project_id=None, recurrence_start=date(2026, 8, 1))
    movements = _build(expenses=[(expense, None)], with_vat=False)

    assert len(movements) == 14  # agosto 2026 → septiembre 2027
    realized = [m for m in movements if m.realized]
    assert [m.date for m in realized] == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]
    assert {m.status for m in realized} == {"Pagado"}
    assert {m.status for m in movements if not m.realized} == {"Previsto"}
    assert {m.amount_out for m in movements} == {100.0}
    assert movements[0].project == "General / Empresa"


def test_gasto_mensual_marcado_pagado_es_todo_real():
    expense = make_expense(
        payment_type="Mensual", status="Pagado",
        recurrence_start=date(2026, 9, 1), recurrence_end=date(2026, 12, 31),
    )
    movements = _build(expenses=[(expense, make_project())], vat_settlement=False)
    assert len(movements) == 4
    assert all(m.realized and m.status == "Pagado" for m in movements)


def test_gasto_inactivo_se_ignora():
    expense = make_expense(project_id=None, status="Inactivo")
    assert _build(expenses=[(expense, None)]) == []


def test_prestamo_capital_y_cuotas():
    loan = make_loan(
        principal=10000.0, received_date=date(2026, 1, 1),
        first_payment_date=date(2026, 2, 1), term_months=12, monthly_payment=900.0,
    )
    movements = _build(loans=[loan], vat_settlement=False)

    capital = movements[0]
    assert capital.kind == "Financiación"
    assert capital.amount_in == 10000.0 and capital.realized

    installments = movements[1:]
    assert len(installments) == 12
    assert sum(1 for m in installments if m.realized) == 9  # feb → oct
    assert installments[0].concept == "ICO · cuota 1"


def test_prestamo_cancelado_se_ignora():
    assert _build(loans=[make_loan(status="Cancelado")]) == []


# ============================================================
# IVA (303)
# ============================================================

def _vat_movements(movements):
    return [m for m in movements if m.kind == "IVA (303)"]


def test_liquidacion_trimestral_del_iva():
    collection = make_collection(
        status="Facturado", invoice_date=date(2026, 2, 10), expected_date=date(2026, 3, 1)
    )
    expense = make_expense(
        status="Pagado", payment_date=date(2026, 2, 15),
        base_amount=200.0, vat_amount=42.0, total_amount=242.0,
    )
    movements = _build([(collection, None, make_project())], [(expense, make_project())])

    (vat,) = _vat_movements(movements)
    assert vat.date == date(2026, 4, 20)
    assert vat.amount_out == 168.0  # 210 repercutido - 42 soportado
    assert vat.concept == "Liquidación IVA 1T 2026"
    assert vat.realized and vat.status == "Pagado"


def test_iva_negativo_se_compensa_en_el_trimestre_siguiente():
    expense = make_expense(
        status="Pagado", payment_date=date(2026, 1, 10),
        base_amount=476.19, vat_amount=100.0, total_amount=576.19,
    )
    collection = make_collection(invoice_date=date(2026, 5, 1), expected_date=date(2026, 6, 1))
    movements = _build([(collection, None, make_project())], [(expense, make_project())])

    (vat,) = _vat_movements(movements)
    assert vat.date == date(2026, 7, 20)
    assert vat.amount_out == 110.0


def test_iva_del_cuarto_trimestre_se_paga_el_30_de_enero():
    collection = make_collection(invoice_date=date(2026, 11, 5), expected_date=date(2026, 12, 5))
    (vat,) = _vat_movements(_build([(collection, None, make_project())]))
    assert vat.date == date(2027, 1, 30)
    assert not vat.realized and vat.status == "Previsto"


def test_iva_de_cobro_sin_fechas_de_factura_ni_prevista_usa_la_de_cobro():
    collection = make_collection(status="Cobrado", collection_date=date(2026, 5, 3))
    (vat,) = _vat_movements(_build([(collection, None, make_project())]))
    assert vat.date == date(2026, 7, 20)
    assert vat.amount_out == 210.0


def test_vista_sin_iva_no_genera_liquidaciones():
    collection = make_collection(invoice_date=date(2026, 2, 10), expected_date=date(2026, 3, 1))
    assert _vat_movements(_build([(collection, None, make_project())], with_vat=False)) == []


def test_vat_due_date():
    assert cf.vat_due_date(2026, 1) == date(2026, 4, 20)
    assert cf.vat_due_date(2026, 2) == date(2026, 7, 20)
    assert cf.vat_due_date(2026, 3) == date(2026, 10, 20)
    assert cf.vat_due_date(2026, 4) == date(2027, 1, 30)


# ============================================================
# RESUMEN Y PREVISIÓN
# ============================================================

def _movements_for_summary():
    return [
        Movement(date(2026, 9, 1), "Cobro", "A", "c1", "Cobrado", amount_in=500, realized=True),
        Movement(date(2026, 9, 2), "Pago", "A", "p1", "Pagado", amount_out=200, realized=True),
        Movement(date(2026, 12, 5), "Cobro", "A", "c2", "Previsto", amount_in=300),
        Movement(date(2026, 9, 30), "Pago", "A", "p2", "Pendiente", amount_out=100),
        Movement(None, "Cobro", "A", "c3", "Previsto", amount_in=50),
    ]


def test_summarize_saldos():
    summary = cf.summarize(_movements_for_summary(), opening_balance=1000, today=TODAY)

    assert summary.real_balance == 1300
    assert summary.pending_in == 350
    assert summary.pending_out == 100
    assert summary.projected_balance == 1550
    assert (summary.overdue_in, summary.overdue_out) == (50, 100)
    assert [m.concept for m in summary.overdue] == ["p2", "c3"]
    assert summary.monthly == {(2026, 12): {"in": 300, "out": 0.0}}
    assert summary.all_monthly[(2026, 9)] == {"in": 500, "out": 300}


def test_forecast_rows():
    summary = cf.summarize(_movements_for_summary(), opening_balance=1000, today=TODAY)
    rows = summary.forecast_rows(today=TODAY)

    assert len(rows) == 13
    assert rows[0]["label"] == "Vencido / sin fecha"
    assert rows[0]["net"] == -50
    assert rows[0]["balance"] == 1250
    assert rows[1]["label"] == "Octubre 2026"
    assert rows[1]["balance"] == 1250
    assert rows[3]["label"] == "Diciembre 2026"
    assert rows[3]["balance"] == 1550
    assert rows[-1]["label"] == "Septiembre 2027"
    assert rows[-1]["balance"] == summary.projected_balance


def test_forecast_rows_incluye_meses_fuera_del_horizonte():
    movements = [Movement(date(2028, 3, 1), "Cobro", "A", "c", "Previsto", amount_in=10)]
    rows = cf.summarize(movements, today=TODAY).forecast_rows(today=TODAY)
    assert rows[-1]["key"] == (2028, 3)
    assert rows[-1]["balance"] == 10


def test_sort_movements_deja_los_sin_fecha_al_final():
    movements = [
        Movement(None, "Pago", "A", "x", "Pendiente"),
        Movement(date(2026, 5, 1), "Pago", "A", "y", "Pendiente"),
        Movement(date(2026, 5, 1), "Cobro", "A", "z", "Previsto"),
    ]
    assert [m.concept for m in cf.sort_movements(movements)] == ["z", "y", "x"]


# ============================================================
# CARGA DESDE BASE DE DATOS
# ============================================================

def test_load_cashflow_global_y_por_proyecto(session):
    from database.models import AppSetting, Collection, Expense, Order, Project

    project = Project(name="Obra", client="Cliente")
    other = Project(name="Otra", client="Cliente")
    session.add_all([project, other, AppSetting(key="initial_cash_balance", value="5000")])
    session.flush()
    order = Order(project_id=project.id, order_number="P1", amount=2000)
    session.add(order)
    session.flush()
    session.add_all([
        Collection(order_id=order.id, concept="Anticipo", amount=1000, status="Cobrado",
                   collection_date=date(2026, 9, 1)),
        Expense(project_id=project.id, category="Otros", concept="Hotel", status="Pagado",
                payment_date=date(2026, 9, 2), base_amount=100, vat_amount=21, total_amount=121),
        Expense(project_id=other.id, category="Otros", concept="Vuelo", status="Pagado",
                payment_date=date(2026, 9, 2), base_amount=50, vat_amount=10.5, total_amount=60.5),
    ])
    session.commit()

    movements, summary = cf.load_cashflow(session, today=TODAY)
    assert summary.opening_balance == 5000
    # El cobro no tiene fecha de factura ni prevista: su IVA se devenga en
    # la fecha de cobro (3T 2026) y se liquida el 20 de octubre.
    (vat,) = _vat_movements(movements)
    assert vat.date == date(2026, 10, 20)
    assert vat.amount_out == 210 - 21 - 10.5
    assert summary.real_balance == 5000 + 1210 - 121 - 60.5
    assert summary.pending_out == 178.5

    movements, summary = cf.load_cashflow(session, project_id=project.id, today=TODAY)
    assert summary.opening_balance == 0
    assert summary.real_balance == 1000 - 100
    assert not _vat_movements(movements)


def test_get_float_setting(session):
    from database.models import AppSetting

    assert cf.get_float_setting(session, "nada", 3.5) == 3.5
    session.add(AppSetting(key="malo", value="abc"))
    session.flush()
    assert cf.get_float_setting(session, "malo", 1.0) == 1.0


# ============================================================
# IMPORTES EXACTOS AL CÉNTIMO
# ============================================================

@pytest.mark.parametrize("value, expected", [
    (1.005, 1.01),      # round() de Python daría 1.0
    (2.675, 2.68),      # round() de Python daría 2.67
    (0.105, 0.11),
    (-1.005, -1.01),
    (1234.5678, 1234.57),
    (10, 10.0),
    (None, None),
])
def test_round_money_redondeo_comercial(value, expected):
    assert cf.round_money(value) == expected


def test_add_money_sin_error_de_coma_flotante():
    total = 0.0
    for _ in range(10):
        total += 0.1
    assert total != 1.0  # el problema que se evita (antes el motor sumaba así)
    assert cf.add_money(*([0.1] * 10)) == 1.0
    assert cf.add_money(0.1, 0.2) == 0.3
    assert cf.add_money(None, 5) == 5.0


def test_saldos_exactos_con_muchos_movimientos():
    movements = [
        Movement(date(2026, 9, 1), "Cobro", "A", "c", "Cobrado", amount_in=0.1, realized=True)
        for _ in range(10)
    ] + [
        Movement(date(2026, 9, 1), "Pago", "A", "p", "Pagado", amount_out=0.3, realized=True)
    ]
    summary = cf.summarize(movements, opening_balance=0.2, today=TODAY)
    assert summary.realized_in == 1.0
    assert summary.real_balance == 0.9
    assert summary.forecast_rows(today=TODAY)[-1]["balance"] == 0.9


def test_iva_del_cobro_con_redondeo_comercial():
    # 0,50 € al 21 % = 0,105 € -> 0,11 €
    assert cf.collection_vat(make_collection(amount=0.5)) == 0.11
    assert cf.collection_total(make_collection(amount=0.5)) == 0.61


# ============================================================
# LIQUIDACIONES REALES DE IVA (gestoría)
# ============================================================

def _real(amount, payment_date=None):
    return SimpleNamespace(amount=amount, payment_date=payment_date)


def _q3_2026():
    """El 3T 2026 real de la empresa: 7.268,52 repercutido, 804 soportado."""
    project = make_project()
    collections = [
        (make_collection(amount=24345.0, invoice_date=date(2026, 7, 31)), None, project),
        (make_collection(amount=3060.0, invoice_date=date(2026, 9, 11)), None, project),
        (make_collection(amount=7207.0, invoice_date=date(2026, 7, 31)), None, project),
    ]
    expenses = [(make_expense(
        status="Pagado", payment_date=date(2026, 8, 3),
        base_amount=3828.57, vat_amount=804.0, total_amount=4632.57,
    ), project)]
    return collections, expenses


def test_sin_registro_se_usa_la_estimacion():
    collections, expenses = _q3_2026()
    (row,) = cf.vat_quarters(collections, expenses, today=TODAY)
    assert (row["output"], row["input"], row["estimated"]) == (7268.52, 804.0, 6464.52)
    assert row["to_pay"] == 6464.52 and not row["registered"]
    assert row["payment_date"] == date(2026, 10, 20)


def test_liquidacion_real_sustituye_a_la_estimacion():
    collections, expenses = _q3_2026()
    registered = {(2026, 3): _real(5863.17, date(2026, 10, 10))}

    (row,) = cf.vat_quarters(collections, expenses, registered, today=TODAY)
    assert row["estimated"] == 6464.52      # la estimación se sigue mostrando
    assert row["result"] == 5863.17 and row["registered"]

    (vat,) = _vat_movements(_build(collections, expenses, vat_registered=registered))
    assert vat.amount_out == 5863.17
    assert vat.date == date(2026, 10, 10)
    assert vat.realized and vat.status == "Pagado"
    assert vat.concept == "Liquidación IVA 3T 2026 (gestoría)"


def test_liquidacion_real_con_fecha_futura_queda_prevista():
    collections, expenses = _q3_2026()
    registered = {(2026, 3): _real(5863.17, date(2026, 10, 20))}
    (vat,) = _vat_movements(_build(collections, expenses, vat_registered=registered))
    assert not vat.realized and vat.status == "Previsto"


def test_resultado_real_negativo_se_compensa_despues():
    project = make_project()
    collections = [
        (make_collection(invoice_date=date(2026, 2, 1)), None, project),   # 1T: 210
        (make_collection(invoice_date=date(2026, 5, 1)), None, project),   # 2T: 210
    ]
    registered = {(2026, 1): _real(-100.0)}  # la gestoría deja 100 € a compensar

    movements = _build(collections, [], vat_registered=registered)
    (vat,) = _vat_movements(movements)
    assert vat.concept == "Liquidación IVA 2T 2026"
    assert vat.amount_out == 110.0

    rows = cf.vat_quarters(collections, [], registered, today=TODAY)
    assert [r["carry_in"] for r in rows] == [0.0, -100.0]


def test_liquidacion_registrada_de_un_trimestre_sin_datos():
    registered = {(2026, 2): _real(300.0, date(2026, 7, 15))}
    (vat,) = _vat_movements(_build([], [], vat_registered=registered))
    assert vat.amount_out == 300.0 and vat.date == date(2026, 7, 15)


def test_load_cashflow_usa_las_liquidaciones_registradas(session):
    from database.models import Collection, Order, Project, VatSettlement

    project = Project(name="Obra", client="Cliente")
    session.add(project)
    session.flush()
    order = Order(project_id=project.id, order_number="P1", amount=10000)
    session.add(order)
    session.flush()
    session.add_all([
        Collection(order_id=order.id, concept="Hito", amount=1000, status="Facturado",
                   invoice_date=date(2026, 8, 1), expected_date=date(2026, 12, 1)),
        VatSettlement(year=2026, quarter=3, amount=150.0, payment_date=date(2026, 10, 5)),
    ])
    session.commit()

    movements, summary = cf.load_cashflow(session, today=TODAY)
    (vat,) = _vat_movements(movements)
    assert vat.amount_out == 150.0 and vat.realized
    assert summary.real_balance == -150.0

    (row,) = cf.load_vat_quarters(session, today=TODAY)
    assert (row["estimated"], row["result"]) == (210.0, 150.0)


# ============================================================
# HORIZONTE DE PREVISIÓN
# ============================================================

def test_meses_fuera_del_horizonte_se_marcan():
    movements = [
        Movement(date(2027, 5, 1), "Cobro", "A", "c", "Previsto", amount_in=10),
        Movement(date(2028, 3, 1), "Cuota préstamo", "E", "q", "Previsto", amount_out=5),
    ]
    rows = cf.summarize(movements, today=TODAY).forecast_rows(today=TODAY)
    beyond = {r["label"] for r in rows if r["beyond_horizon"]}
    assert beyond == {"Marzo 2028"}
    assert not any(r["beyond_horizon"] for r in rows if r["label"] == "Septiembre 2027")


def test_grafica_del_dashboard_cubre_solo_el_horizonte():
    """Los gastos mensuales sin fin solo se generan dentro del horizonte."""
    payroll = make_expense(project_id=None, recurrence_start=date(2026, 1, 1),
                           base_amount=6800, vat_amount=0, total_amount=6800)
    dates = cf.expense_dates(payroll, today=TODAY)
    assert dates[-1] == date(2027, 9, 1)
    assert len([d for d in dates if d >= date(2026, 10, 1)]) == cf.FORECAST_MONTHS


# ============================================================
# PEDIDOS CANCELADOS
# ============================================================

def test_pedido_cancelado_solo_mantiene_lo_facturado_o_cobrado():
    project = make_project()
    cancelled = SimpleNamespace(status="Cancelado")
    pending = make_collection(concept="Pendiente", expected_date=date(2026, 12, 1),
                              invoice_number=None)
    invoiced = make_collection(concept="Facturado", status="Facturado", invoice_number="0001",
                               invoice_date=date(2026, 9, 1), expected_date=date(2026, 12, 1))
    collected = make_collection(concept="Cobrado", status="Cobrado", invoice_number=None,
                                collection_date=date(2026, 9, 5))

    movements = _build([(c, cancelled, project) for c in (pending, invoiced, collected)],
                       vat_settlement=False)
    assert {m.concept for m in movements} == {"Facturado", "Cobrado"}

    # Su IVA tampoco cuenta: solo el de los dos que se mantienen (3T).
    rows = cf.vat_quarters([(c, cancelled, project) for c in (pending, invoiced, collected)], [],
                           today=TODAY)
    assert sum(r["output"] for r in rows) == 420.0


def test_collection_counts():
    active = SimpleNamespace(status="En curso")
    cancelled = SimpleNamespace(status="Cancelado")
    assert cf.collection_counts(make_collection(), active)
    assert cf.collection_counts(make_collection(), None)
    assert not cf.collection_counts(make_collection(status="Cancelado"), active)
    assert not cf.collection_counts(make_collection(invoice_number=None), cancelled)
    assert cf.collection_counts(make_collection(invoice_number="7"), cancelled)


def test_factura_general_suelta_cuenta_una_sola_vez():
    invoice = make_expense(
        project_id=None, payment_type="Único", status="Pagado",
        expense_date=date(2026, 9, 2), payment_date=date(2026, 9, 2),
    )
    assert not cf.is_recurring(invoice)
    assert cf.expense_dates(invoice, today=TODAY) == [date(2026, 9, 2)]

    movements = cf.build_movements([], [(invoice, None)], [], with_vat=True, today=TODAY)
    paid = [m for m in movements if m.amount_out]
    assert len(paid) == 1 and paid[0].amount_out == 121.0


def test_gastos_generales_sin_fecha_siguen_siendo_mensuales():
    # Las nóminas y los gastos generales antiguos ("Único" sin fecha).
    assert cf.is_recurring(make_expense(project_id=None, payment_type="Mensual"))
    assert cf.is_recurring(make_expense(project_id=None, payment_type="Único"))
    assert cf.is_recurring(make_expense(project_id=None, payment_type=None))


def test_cobros_de_un_pedido_ya_superado_se_pueden_editar(session):
    from database.models import Collection, Order, Project

    project = Project(name="Talleres Norte", client="Talleres Norte", start_date=date(2026, 8, 3))
    session.add(project)
    session.flush()
    order = Order(project_id=project.id, order_number="PED-0001", amount=45691.03)
    other_order = Order(project_id=project.id, order_number="2", amount=50000)
    session.add_all([order, other_order])
    session.flush()
    advance = Collection(order_id=order.id, concept="Anticipo", amount=24345,
                         status="Facturado", invoice_number="0057")
    final = Collection(order_id=order.id, concept="Pago final", amount=24345,
                       status="Facturado", invoice_number="0059")
    session.add_all([advance, final])
    session.flush()

    # Marcar como cobrado sin tocar el importe: se puede.
    assert cf.order_overrun(session, order.id, 24345, "Cobrado", advance) is None
    # Bajar el importe tampoco aumenta el exceso.
    assert cf.order_overrun(session, order.id, 20000, "Facturado", advance) is None

    # Subirlo, o un cobro nuevo, sí lo aumentan.
    overrun = cf.order_overrun(session, order.id, 25000, "Facturado", advance)
    assert overrun == {"order": 45691.03, "others": 24345.0, "total": 49345.0}
    assert cf.order_overrun(session, order.id, 100, "Previsto") is not None

    # Cancelar siempre se puede.
    assert cf.order_overrun(session, order.id, 99999, "Cancelado") is None

    # Un cobro cancelado que se reactiva cuenta como nuevo: solo cabe lo
    # que queda libre del pedido (45.691,03 - 24.345 = 21.346,03).
    advance.status = "Cancelado"
    session.flush()
    assert cf.order_overrun(session, order.id, 21346.03, "Previsto", advance) is None
    assert cf.order_overrun(session, order.id, 24345, "Previsto", advance) is not None
    advance.status = "Facturado"
    session.flush()

    # Moverlo a otro pedido se comprueba contra ese pedido.
    assert cf.order_overrun(session, other_order.id, 24345, "Facturado", advance) is None
    assert cf.order_overrun(session, other_order.id, 60000, "Facturado", advance) is not None
