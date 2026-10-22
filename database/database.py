import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# BASE DE DATOS PERSISTENTE
# ============================================================

APP_NAME = "ControlDeCaja"

local_app_data = os.getenv("LOCALAPPDATA")

if local_app_data:
    DATA_DIR = Path(local_app_data) / APP_NAME
else:
    DATA_DIR = Path.home() / "AppData" / "Local" / APP_NAME

DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "control_de_caja.db"


# ============================================================
# SQLALCHEMY
# ============================================================

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


def migrate_database():
    inspector = inspect(engine)

    if "expenses" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("expenses")
    }

    if "payment_type" not in columns:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE expenses
                ADD COLUMN payment_type VARCHAR(50)
                NOT NULL DEFAULT 'Único'
            """))

    if "recurrence_start" not in columns:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE expenses
                ADD COLUMN recurrence_start DATE
            """))

    if "recurrence_end" not in columns:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE expenses
                ADD COLUMN recurrence_end DATE
            """))


def migrate_expenses_project_nullable():
    """
    SQLite no permite cambiar directamente NOT NULL -> NULL.
    Si project_id sigue siendo obligatorio, reconstruimos solo la tabla
    expenses conservando todos los datos existentes.
    """
    inspector = inspect(engine)

    if "expenses" not in inspector.get_table_names():
        return

    project_column = next(
        (
            column
            for column in inspector.get_columns("expenses")
            if column["name"] == "project_id"
        ),
        None,
    )

    if project_column is None or project_column.get("nullable", False):
        return

    raw = engine.raw_connection()

    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")

        cursor.execute("""
            CREATE TABLE expenses_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NULL,
                category VARCHAR(100) NOT NULL,
                concept VARCHAR(200) NOT NULL,
                supplier VARCHAR(200),
                payment_type VARCHAR(50) NOT NULL DEFAULT 'Único',
                expense_date DATE,
                recurrence_start DATE,
                recurrence_end DATE,
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
        """)

        cursor.execute("""
            INSERT INTO expenses_new (
                id,
                project_id,
                category,
                concept,
                supplier,
                payment_type,
                expense_date,
                recurrence_start,
                recurrence_end,
                base_amount,
                vat_rate,
                vat_amount,
                total_amount,
                status,
                payment_date,
                invoice_reference,
                notes
            )
            SELECT
                id,
                project_id,
                category,
                concept,
                supplier,
                COALESCE(payment_type, 'Único'),
                expense_date,
                recurrence_start,
                recurrence_end,
                base_amount,
                vat_rate,
                vat_amount,
                total_amount,
                status,
                payment_date,
                invoice_reference,
                notes
            FROM expenses
        """)

        cursor.execute("DROP TABLE expenses")
        cursor.execute("ALTER TABLE expenses_new RENAME TO expenses")
        cursor.execute("PRAGMA foreign_keys=ON")
        raw.commit()

    except Exception:
        raw.rollback()
        raise

    finally:
        raw.close()


def add_column_if_missing(table, column, definition):
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns(table)}
    if column not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            ))


def migrate_new_columns():
    # Proyectos
    add_column_if_missing("projects", "calculation_end_date", "DATE")
    add_column_if_missing("projects", "client_tax_id", "VARCHAR(30)")
    add_column_if_missing("projects", "client_address", "VARCHAR(500)")
    add_column_if_missing("projects", "client_id", "INTEGER REFERENCES clients(id)")

    # Cobros: IVA aplicado y PDF de la factura
    add_column_if_missing("collections", "vat_rate", "FLOAT")
    add_column_if_missing("collections", "invoice_file", "VARCHAR(500)")

    # Gastos: ticket o factura escaneada
    add_column_if_missing("expenses", "document_file", "VARCHAR(500)")


def migrate_clients():
    """
    Crea una ficha de cliente por cada nombre de cliente usado en los
    proyectos que aún no estén enlazados, copiando los datos fiscales que
    se hubieran guardado en el proyecto.
    """
    with engine.begin() as connection:
        rows = connection.execute(text("""
            SELECT id, TRIM(client), client_tax_id, client_address
            FROM projects
            WHERE client_id IS NULL AND TRIM(COALESCE(client, '')) <> ''
        """)).fetchall()

        for project_id, name, tax_id, address in rows:
            client_id = connection.execute(
                text("SELECT id FROM clients WHERE LOWER(name) = LOWER(:n)"),
                {"n": name},
            ).scalar()

            if client_id is None:
                connection.execute(
                    text("""
                        INSERT INTO clients (name, tax_id, address)
                        VALUES (:n, :t, :a)
                    """),
                    {"n": name, "t": tax_id, "a": address},
                )
                client_id = connection.execute(
                    text("SELECT id FROM clients WHERE name = :n"), {"n": name}
                ).scalar()
            else:
                # Completar datos vacíos con lo que tuviera el proyecto.
                connection.execute(
                    text("""
                        UPDATE clients
                        SET tax_id = COALESCE(tax_id, :t),
                            address = COALESCE(address, :a)
                        WHERE id = :id
                    """),
                    {"t": tax_id, "a": address, "id": client_id},
                )

            connection.execute(
                text("UPDATE projects SET client_id = :c WHERE id = :p"),
                {"c": client_id, "p": project_id},
            )


def migrate_general_expenses_start():
    """
    Los gastos generales ahora tienen fecha "Activo desde". A los que no
    la tienen se les asigna el día 1 del mes actual (una sola vez), para
    que las mensualidades ya pasadas cuenten como pagadas a partir de ahí.
    """
    from datetime import date

    first_day = date.today().replace(day=1).isoformat()
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE expenses
            SET recurrence_start = :start
            WHERE project_id IS NULL AND recurrence_start IS NULL
        """), {"start": first_day})


INVOICE_NUMBER_INDEX = "ux_collections_invoice_number"


def duplicate_invoice_numbers():
    """Números de factura repetidos en cobros: lista de (número, veces)."""
    inspector = inspect(engine)
    if "collections" not in inspector.get_table_names():
        return []
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT invoice_number, COUNT(*)
            FROM collections
            WHERE invoice_number IS NOT NULL
            GROUP BY invoice_number
            HAVING COUNT(*) > 1
            ORDER BY invoice_number
        """)).fetchall()
    return [(number, count) for number, count in rows]


def ensure_unique_invoice_numbers():
    """
    Impide en la propia base que dos cobros compartan número de factura.
    Si ya hay duplicados, no se crea el índice (la app debe seguir
    abriendo); se avisa al usuario y se creará cuando los corrija.
    """
    if duplicate_invoice_numbers():
        return False
    with engine.begin() as connection:
        connection.execute(text(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {INVOICE_NUMBER_INDEX}
            ON collections (invoice_number)
            WHERE invoice_number IS NOT NULL
        """))
    return True


# Un cobro con factura emitida no se puede borrar (tampoco al borrar su
# pedido o proyecto) ni cambiar en lo que figura en la factura. Emitida =
# número y, además, PDF generado o estado posterior a "Previsto" (misma
# regla que services.invoices.is_invoiced): un número escrito a mano en un
# cobro previsto aún no es una factura. Si su número está repetido con otro
# cobro (datos antiguos) se permite corregirlo.
_INVOICED = """
    OLD.invoice_number IS NOT NULL
    AND TRIM(OLD.invoice_number) <> ''
    AND (
        (OLD.invoice_file IS NOT NULL AND TRIM(OLD.invoice_file) <> '')
        OR COALESCE(OLD.status, 'Previsto') <> 'Previsto'
    )
    AND (SELECT COUNT(*) FROM collections d
         WHERE d.invoice_number = OLD.invoice_number) = 1
"""

INVOICE_PROTECTION_TRIGGERS = {
    "trg_collections_invoiced_no_delete": f"""
        CREATE TRIGGER IF NOT EXISTS trg_collections_invoiced_no_delete
        BEFORE DELETE ON collections
        WHEN {_INVOICED}
        BEGIN
            SELECT RAISE(ABORT, 'No se puede eliminar un cobro con factura emitida');
        END
    """,
    "trg_collections_invoiced_no_update": f"""
        CREATE TRIGGER IF NOT EXISTS trg_collections_invoiced_no_update
        BEFORE UPDATE OF order_id, concept, amount, invoice_number, invoice_date,
            vat_rate, status
        ON collections
        WHEN {_INVOICED}
            AND (
                -- Volver a "Previsto" la desbloquearía.
                (COALESCE(NEW.status, 'Previsto') = 'Previsto'
                 AND COALESCE(OLD.status, 'Previsto') <> 'Previsto')
                OR NEW.order_id IS NOT OLD.order_id
                OR NEW.concept IS NOT OLD.concept
                OR NEW.amount IS NOT OLD.amount
                OR NEW.invoice_number IS NOT OLD.invoice_number
                OR NEW.invoice_date IS NOT OLD.invoice_date
                OR COALESCE(NEW.vat_rate, 21.0) IS NOT COALESCE(OLD.vat_rate, 21.0)
            )
        BEGIN
            SELECT RAISE(ABORT, 'No se puede modificar un cobro con factura emitida');
        END
    """,
}


def ensure_invoice_protection():
    # Se reemplazan siempre: con "IF NOT EXISTS" una base antigua se
    # quedaría con la versión anterior de la regla.
    with engine.begin() as connection:
        for name, statement in INVOICE_PROTECTION_TRIGGERS.items():
            connection.execute(text(f"DROP TRIGGER IF EXISTS {name}"))
            connection.execute(text(statement))


# ============================================================
# COPIAS DE SEGURIDAD AUTOMÁTICAS
# ============================================================

BACKUP_DIR = DATA_DIR / "copias_seguridad"
BACKUPS_TO_KEEP = 30


def backup_database():
    """
    Copia la base de datos una vez al día (al abrir la app) y conserva
    las últimas 30 copias.
    """
    from datetime import date

    if not DATABASE_PATH.exists():
        return None

    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = BACKUP_DIR / f"control_de_caja_{date.today().isoformat()}.db"
        if not target.exists():
            shutil.copy2(DATABASE_PATH, target)

        _rotate_backups(BACKUP_DIR)
        return target
    except OSError:
        # Una copia fallida nunca debe impedir abrir la aplicación.
        return None


def _rotate_backups(folder):
    backups = sorted(Path(folder).glob("control_de_caja_*.db"))
    for old in backups[:-BACKUPS_TO_KEEP]:
        old.unlink(missing_ok=True)


# ------------------------------------------------------------
# Copia externa (OneDrive, NAS, USB…)
# ------------------------------------------------------------

EXTERNAL_BACKUP_KEY = "backup_external_folder"


def external_backup_folder():
    """Carpeta externa configurada en Configuración, o None."""
    inspector = inspect(engine)
    if "app_settings" not in inspector.get_table_names():
        return None
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT value FROM app_settings WHERE key = :k"),
            {"k": EXTERNAL_BACKUP_KEY},
        ).scalar()
    value = (value or "").strip()
    return Path(value) if value else None


def backup_to_external(folder=None, force=False):
    """
    Copia la base en la carpeta externa (una por día, últimas 30).

    Usa la copia nativa de SQLite, coherente aunque la base esté abierta,
    y escribe primero un temporal para no dejar copias a medias.
    Devuelve la ruta de la copia o None si no hay carpeta configurada.
    Lanza OSError si la carpeta no está disponible.
    """
    import sqlite3
    from datetime import date

    folder = Path(folder) if folder else external_backup_folder()
    if folder is None:
        return None
    if not folder.is_dir():
        raise OSError(f"La carpeta no existe o no está disponible: {folder}")

    target = folder / f"control_de_caja_{date.today().isoformat()}.db"
    if target.exists() and not force:
        return target

    temporary = target.with_suffix(".tmp")
    source = sqlite3.connect(DATABASE_PATH)
    try:
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
        finally:
            destination.close()
    except sqlite3.Error as error:
        temporary.unlink(missing_ok=True)
        raise OSError(str(error)) from error
    finally:
        source.close()

    try:
        os.replace(temporary, target)
    except OSError:
        # Copia de hoy bloqueada (sincronización, antivirus…): no dejar restos.
        temporary.unlink(missing_ok=True)
        raise
    _rotate_backups(folder)
    return target


def latest_backup(folder):
    """Copia más reciente de una carpeta, o None."""
    if folder is None or not Path(folder).is_dir():
        return None
    backups = sorted(Path(folder).glob("control_de_caja_*.db"))
    return backups[-1] if backups else None


def create_database():
    from database.models import (
        AppSetting,
        Client,
        Collection,
        Expense,
        Loan,
        Order,
        Project,
        VatSettlement,
    )

    backup_database()
    Base.metadata.create_all(bind=engine)
    migrate_database()
    migrate_expenses_project_nullable()
    migrate_new_columns()
    migrate_clients()
    migrate_general_expenses_start()
    ensure_unique_invoice_numbers()
    ensure_invoice_protection()


def get_session():
    return SessionLocal()
