"""
Tests de migraciones y copias de seguridad (database/database.py).

Cada test trabaja sobre una base SQLite en una carpeta temporal: se
sustituyen `engine`, `DATABASE_PATH` y `BACKUP_DIR` del módulo.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, inspect, text

import database.database as db


LEGACY_SCHEMA = [
    """
    CREATE TABLE projects (
        id INTEGER NOT NULL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        client VARCHAR(150) NOT NULL,
        reference VARCHAR(100),
        start_date DATE,
        end_date DATE,
        status VARCHAR(50),
        estimated_value FLOAT,
        notes VARCHAR(1000)
    )
    """,
    """
    CREATE TABLE expenses (
        id INTEGER NOT NULL PRIMARY KEY,
        project_id INTEGER NOT NULL,
        category VARCHAR(100) NOT NULL,
        concept VARCHAR(200) NOT NULL,
        supplier VARCHAR(200),
        expense_date DATE,
        base_amount FLOAT NOT NULL DEFAULT 0.0,
        vat_rate FLOAT NOT NULL DEFAULT 21.0,
        vat_amount FLOAT NOT NULL DEFAULT 0.0,
        total_amount FLOAT NOT NULL DEFAULT 0.0,
        status VARCHAR(50) NOT NULL DEFAULT 'Pendiente',
        payment_date DATE,
        invoice_reference VARCHAR(150),
        notes VARCHAR(1000),
        FOREIGN KEY(project_id) REFERENCES projects (id)
    )
    """,
    """
    CREATE TABLE orders (
        id INTEGER NOT NULL PRIMARY KEY,
        project_id INTEGER NOT NULL,
        order_number VARCHAR(100) NOT NULL,
        description VARCHAR(500),
        order_date DATE,
        amount FLOAT NOT NULL,
        status VARCHAR(50),
        notes VARCHAR(1000)
    )
    """,
    """
    CREATE TABLE collections (
        id INTEGER NOT NULL PRIMARY KEY,
        order_id INTEGER NOT NULL,
        concept VARCHAR(200) NOT NULL,
        calculation_type VARCHAR(50) NOT NULL,
        percentage FLOAT,
        amount FLOAT NOT NULL,
        expected_date DATE,
        status VARCHAR(50) NOT NULL,
        invoice_number VARCHAR(100),
        invoice_date DATE,
        collection_date DATE,
        notes VARCHAR(1000)
    )
    """,
]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    path = tmp_path / "control_de_caja.db"
    engine = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATABASE_PATH", path)
    monkeypatch.setattr(db, "BACKUP_DIR", tmp_path / "copias_seguridad")
    yield engine
    engine.dispose()


@pytest.fixture
def legacy_db(temp_db):
    with temp_db.begin() as conn:
        for statement in LEGACY_SCHEMA:
            conn.execute(text(statement))
        conn.execute(text("""
            INSERT INTO projects (id, name, client, status, estimated_value)
            VALUES (1, 'Obra 1', 'Acme', 'Activo', 1000),
                   (2, 'Obra 2', ' acme ', 'Activo', 2000),
                   (3, 'Obra 3', 'Beta', 'Activo', 0),
                   (4, 'Interna', '', 'Activo', 0)
        """))
        conn.execute(text("""
            INSERT INTO expenses (id, project_id, category, concept, expense_date,
                                  base_amount, vat_amount, total_amount, status)
            VALUES (7, 1, 'Hotel', 'Hotel Vigo', '2026-03-01', 100, 21, 121, 'Pagado')
        """))
    return temp_db


def _columns(engine, table):
    return {c["name"]: c for c in inspect(engine).get_columns(table)}


def test_create_database_en_base_nueva(temp_db):
    db.create_database()
    tables = set(inspect(temp_db).get_table_names())
    assert {"clients", "projects", "orders", "collections", "expenses", "loans", "app_settings"} <= tables


def test_migracion_de_base_antigua(legacy_db):
    db.create_database()

    expenses = _columns(legacy_db, "expenses")
    assert expenses["project_id"]["nullable"]
    assert {"payment_type", "recurrence_start", "recurrence_end"} <= set(expenses)
    assert {"calculation_end_date", "client_tax_id", "client_address", "client_id"} <= set(
        _columns(legacy_db, "projects")
    )
    assert {"vat_rate", "invoice_file"} <= set(_columns(legacy_db, "collections"))

    with legacy_db.connect() as conn:
        expense = conn.execute(text(
            "SELECT id, project_id, concept, payment_type, total_amount, status FROM expenses"
        )).one()
        assert tuple(expense) == (7, 1, "Hotel Vigo", "Único", 121.0, "Pagado")

        clients = conn.execute(text("SELECT id, name FROM clients ORDER BY name")).all()
        assert [name for _, name in clients] == ["Acme", "Beta"]

        links = dict(conn.execute(text("SELECT id, client_id FROM projects")).all())
        acme_id = clients[0][0]
        assert links[1] == links[2] == acme_id
        assert links[3] == clients[1][0]
        assert links[4] is None


def test_migraciones_son_idempotentes(legacy_db):
    db.create_database()
    db.create_database()
    with legacy_db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM clients")).scalar() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM expenses")).scalar() == 1


def test_migrate_clients_completa_datos_fiscales_vacios(temp_db):
    db.create_database()
    with temp_db.begin() as conn:
        conn.execute(text("INSERT INTO clients (name) VALUES ('Acme')"))
        conn.execute(text("""
            INSERT INTO projects (name, client, client_tax_id, client_address, status, estimated_value)
            VALUES ('Obra', 'ACME', 'B123', 'Calle 1', 'Activo', 0)
        """))

    db.migrate_clients()

    with temp_db.connect() as conn:
        row = conn.execute(text("SELECT name, tax_id, address FROM clients")).one()
        assert tuple(row) == ("Acme", "B123", "Calle 1")


def test_gastos_generales_sin_inicio_reciben_el_mes_actual(temp_db):
    db.create_database()
    with temp_db.begin() as conn:
        conn.execute(text("""
            INSERT INTO expenses (project_id, category, concept, payment_type,
                                  base_amount, vat_rate, vat_amount, total_amount, status)
            VALUES (NULL, 'Alquiler', 'Oficina', 'Mensual', 500, 21, 105, 605, 'Activo')
        """))

    db.migrate_general_expenses_start()

    with temp_db.connect() as conn:
        start = conn.execute(text("SELECT recurrence_start FROM expenses")).scalar()
    assert start == date.today().replace(day=1).isoformat()


# ============================================================
# COPIAS DE SEGURIDAD
# ============================================================

def test_backup_database_crea_copia_del_dia(temp_db):
    db.create_database()
    target = db.backup_database()
    assert target == db.BACKUP_DIR / f"control_de_caja_{date.today().isoformat()}.db"
    assert target.exists()


def test_backup_database_conserva_las_ultimas_30(temp_db):
    db.create_database()
    db.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    old = [db.BACKUP_DIR / f"control_de_caja_2020-01-{day:02d}.db" for day in range(1, 33 - 1)]
    old += [db.BACKUP_DIR / "control_de_caja_2020-02-01.db", db.BACKUP_DIR / "control_de_caja_2020-02-02.db"]
    for path in old:
        path.write_bytes(b"")

    db.backup_database()

    remaining = sorted(p.name for p in db.BACKUP_DIR.glob("control_de_caja_*.db"))
    assert len(remaining) == db.BACKUPS_TO_KEEP
    assert remaining[-1] == f"control_de_caja_{date.today().isoformat()}.db"
    assert "control_de_caja_2020-01-01.db" not in remaining


def test_backup_database_sin_base_no_hace_nada(temp_db):
    assert db.backup_database() is None


# ============================================================
# NÚMEROS DE FACTURA ÚNICOS
# ============================================================

def _insert_collection(conn, number):
    conn.execute(text("""
        INSERT INTO collections (order_id, concept, calculation_type, amount, status, invoice_number)
        VALUES (1, 'Hito', 'Importe', 100, 'Facturado', :n)
    """), {"n": number})


def test_indice_unico_impide_repetir_numero_de_factura(temp_db):
    from sqlalchemy.exc import IntegrityError

    db.create_database()
    with temp_db.begin() as conn:
        _insert_collection(conn, "0001")
        _insert_collection(conn, None)
        _insert_collection(conn, None)  # sin número se puede repetir

    with pytest.raises(IntegrityError):
        with temp_db.begin() as conn:
            _insert_collection(conn, "0001")


def test_con_duplicados_previos_no_se_crea_el_indice_y_se_informa(temp_db):
    with temp_db.begin() as conn:
        for statement in LEGACY_SCHEMA:
            conn.execute(text(statement))
        _insert_collection(conn, "0057")
        _insert_collection(conn, "0057")
        _insert_collection(conn, "0058")

    db.create_database()  # no debe fallar

    assert db.duplicate_invoice_numbers() == [("0057", 2)]
    indexes = {i["name"] for i in inspect(temp_db).get_indexes("collections")}
    assert db.INVOICE_NUMBER_INDEX not in indexes

    # Una vez corregido, el siguiente arranque crea el índice.
    with temp_db.begin() as conn:
        conn.execute(text(
            "UPDATE collections SET invoice_number = '0059' WHERE id = (SELECT MAX(id) FROM collections WHERE invoice_number = '0057')"
        ))
    db.create_database()
    assert db.duplicate_invoice_numbers() == []
    indexes = {i["name"] for i in inspect(temp_db).get_indexes("collections")}
    assert db.INVOICE_NUMBER_INDEX in indexes


# ============================================================
# IMPORTES (columna Money)
# ============================================================

def test_importes_se_guardan_redondeados_al_centimo(session):
    from database.models import Expense, Loan

    expense = Expense(project_id=None, category="X", concept="X",
                      base_amount=100.005, vat_amount=21.0011, total_amount=121.0061)
    session.add_all([expense, Loan(name="L", principal=1000.555, monthly_payment=0)])
    session.commit()
    session.expire_all()

    stored = session.get(Expense, expense.id)
    assert (stored.base_amount, stored.vat_amount, stored.total_amount) == (100.01, 21.0, 121.01)
    assert stored.vat_rate == 21.0  # los porcentajes no se tocan
    assert session.query(Loan).one().principal == 1000.56


def test_importes_con_mas_decimales_ya_guardados_se_leen_al_centimo(session):
    from database.models import Expense

    session.execute(text("""
        INSERT INTO expenses (category, concept, payment_type, base_amount, vat_rate,
                              vat_amount, total_amount, status)
        VALUES ('X', 'X', 'Único', 10.004, 21, 2.1, 12.104, 'Pendiente')
    """))
    session.commit()
    assert session.query(Expense).one().total_amount == 12.1


# ============================================================
# PROTECCIÓN DE COBROS FACTURADOS (triggers)
# ============================================================

@pytest.fixture
def invoiced_db(temp_db):
    db.create_database()
    with temp_db.begin() as conn:
        conn.execute(text("INSERT INTO projects (id, name, client, status, estimated_value) VALUES (1, 'P', 'C', 'Activo', 0)"))
        conn.execute(text("INSERT INTO orders (id, project_id, order_number, amount, status) VALUES (1, 1, 'O', 1000, 'Pendiente')"))
        conn.execute(text("""
            INSERT INTO collections (id, order_id, concept, calculation_type, amount, status,
                                     invoice_number, invoice_date, vat_rate)
            VALUES (1, 1, 'Facturado', 'Importe fijo', 100, 'Facturado', '0001', '2026-10-01', NULL),
                   (2, 1, 'Sin factura', 'Importe fijo', 200, 'Previsto', NULL, NULL, NULL)
        """))
    return temp_db


def _run(engine, sql):
    with engine.begin() as conn:
        conn.execute(text(sql))


@pytest.mark.parametrize("change", [
    "amount = 150",
    "concept = 'Otro'",
    "invoice_number = '0099'",
    "invoice_date = '2026-10-02'",
    "vat_rate = 10",
    "order_id = 2",
])
def test_no_se_modifica_lo_que_figura_en_la_factura(invoiced_db, change):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError, match="factura emitida"):
        _run(invoiced_db, f"UPDATE collections SET {change} WHERE id = 1")


def test_si_se_actualiza_estado_fechas_notas_y_pdf(invoiced_db):
    _run(invoiced_db, """
        UPDATE collections
        SET status = 'Cobrado', collection_date = '2026-10-20', expected_date = '2026-11-01',
            notes = 'ok', invoice_file = 'C:/f.pdf', percentage = 10,
            vat_rate = 21, invoice_number = '0001'
        WHERE id = 1
    """)  # vat_rate NULL -> 21 es el mismo IVA


def test_no_se_borra_un_cobro_facturado_ni_en_cascada(invoiced_db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError, match="factura emitida"):
        _run(invoiced_db, "DELETE FROM collections WHERE id = 1")
    with pytest.raises(IntegrityError, match="factura emitida"):
        _run(invoiced_db, "DELETE FROM collections WHERE order_id = 1")

    _run(invoiced_db, "DELETE FROM collections WHERE id = 2")  # sin factura: sí


def test_borrar_pedido_con_factura_desde_el_orm_falla(invoiced_db):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from database.models import Order

    with Session(invoiced_db) as session:
        session.delete(session.get(Order, 1))
        with pytest.raises(IntegrityError, match="factura emitida"):
            session.commit()

    with invoiced_db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM collections")).scalar() == 2


def test_numero_escrito_en_un_cobro_previsto_no_bloquea(invoiced_db):
    # Número puesto a mano en un cobro previsto, sin PDF: aún no hay factura.
    _run(invoiced_db, "UPDATE collections SET invoice_number = '0060' WHERE id = 2")
    _run(invoiced_db, "UPDATE collections SET amount = 250, concept = 'Otro' WHERE id = 2")
    _run(invoiced_db, "DELETE FROM collections WHERE id = 2")


def test_con_pdf_generado_queda_protegido_aunque_este_previsto(invoiced_db):
    from sqlalchemy.exc import IntegrityError

    _run(invoiced_db, """
        UPDATE collections SET invoice_number = '0060', invoice_file = 'C:/f.pdf' WHERE id = 2
    """)
    with pytest.raises(IntegrityError, match="factura emitida"):
        _run(invoiced_db, "UPDATE collections SET amount = 250 WHERE id = 2")


def test_un_cobro_facturado_no_vuelve_a_previsto(invoiced_db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError, match="factura emitida"):
        _run(invoiced_db, "UPDATE collections SET status = 'Previsto' WHERE id = 1")
    _run(invoiced_db, "UPDATE collections SET status = 'Cancelado' WHERE id = 1")


def test_la_regla_antigua_se_reemplaza_al_arrancar(invoiced_db):
    # Base con el trigger antiguo (bloqueaba con solo tener número).
    _run(invoiced_db, "DROP TRIGGER trg_collections_invoiced_no_update")
    _run(invoiced_db, """
        CREATE TRIGGER trg_collections_invoiced_no_update
        BEFORE UPDATE OF amount ON collections
        WHEN OLD.invoice_number IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'No se puede modificar un cobro con factura emitida'); END
    """)
    _run(invoiced_db, "UPDATE collections SET invoice_number = '0060' WHERE id = 2")

    db.create_database()
    _run(invoiced_db, "UPDATE collections SET amount = 250 WHERE id = 2")


def test_numero_repetido_se_puede_corregir(temp_db):
    with temp_db.begin() as conn:
        for statement in LEGACY_SCHEMA:
            conn.execute(text(statement))
        _insert_collection(conn, "0057")
        _insert_collection(conn, "0057")
    db.create_database()

    _run(temp_db, "UPDATE collections SET invoice_number = '0060' WHERE id = 2")

    # Una vez corregido, los dos quedan protegidos.
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError, match="factura emitida"):
        _run(temp_db, "UPDATE collections SET invoice_number = '0061' WHERE id = 2")


# ============================================================
# COPIA EXTERNA
# ============================================================

def _set_external(engine, folder):
    with engine.begin() as conn:
        conn.execute(text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:k, :v)"),
                     {"k": db.EXTERNAL_BACKUP_KEY, "v": str(folder)})


def test_copia_externa_sin_configurar_no_hace_nada(temp_db):
    db.create_database()
    assert db.external_backup_folder() is None
    assert db.backup_to_external() is None


def test_copia_externa_crea_una_copia_valida(temp_db, tmp_path):
    import sqlite3
    from contextlib import closing

    db.create_database()
    with temp_db.begin() as conn:
        conn.execute(text("INSERT INTO clients (name) VALUES ('Acme')"))
    external = tmp_path / "OneDrive"
    external.mkdir()
    _set_external(temp_db, external)

    assert db.external_backup_folder() == external
    target = db.backup_to_external()

    assert target == external / f"control_de_caja_{date.today().isoformat()}.db"
    assert not list(external.glob("*.tmp"))
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT name FROM clients").fetchall() == [("Acme",)]
    assert db.latest_backup(external) == target


def test_copia_externa_una_al_dia_salvo_forzada(temp_db, tmp_path):
    import sqlite3
    from contextlib import closing

    db.create_database()
    target = db.backup_to_external(tmp_path)
    with temp_db.begin() as conn:
        conn.execute(text("INSERT INTO clients (name) VALUES ('Nuevo')"))

    db.backup_to_external(tmp_path)  # ya existe la de hoy: no se repite
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 0

    db.backup_to_external(tmp_path, force=True)  # «Copiar ahora»
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 1


def test_copia_externa_conserva_las_ultimas_30(temp_db, tmp_path):
    db.create_database()
    for day in range(1, 32):
        (tmp_path / f"control_de_caja_2020-01-{day:02d}.db").write_bytes(b"")
    db.backup_to_external(tmp_path)
    assert len(list(tmp_path.glob("control_de_caja_*.db"))) == db.BACKUPS_TO_KEEP


def test_copia_externa_con_carpeta_no_disponible(temp_db, tmp_path):
    db.create_database()
    _set_external(temp_db, tmp_path / "USB desconectado")
    with pytest.raises(OSError, match="no está disponible"):
        db.backup_to_external()
    assert db.latest_backup(tmp_path / "USB desconectado") is None


def test_copia_externa_bloqueada_no_deja_temporales(temp_db, tmp_path, monkeypatch):
    db.create_database()

    def locked(*args):
        raise PermissionError("archivo en uso")

    external = tmp_path / "externa"
    external.mkdir()
    monkeypatch.setattr(db.os, "replace", locked)
    with pytest.raises(OSError):
        db.backup_to_external(external, force=True)
    assert list(external.iterdir()) == []
