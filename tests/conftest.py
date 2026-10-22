"""
Configuración común de los tests.

`database.database` crea la base de datos en %LOCALAPPDATA% al importarse.
Antes de que ningún test lo importe, apuntamos LOCALAPPDATA a una carpeta
temporal con una base vacía, para no tocar NUNCA los datos reales ni
copiar la base antigua de `data/`.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TEST_APPDATA = Path(tempfile.mkdtemp(prefix="control_de_caja_tests_"))
(_TEST_APPDATA / "ControlDeCaja").mkdir()
(_TEST_APPDATA / "ControlDeCaja" / "control_de_caja.db").touch()
os.environ["LOCALAPPDATA"] = str(_TEST_APPDATA)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Ni el almacén de credenciales real de Windows ni una clave de API real.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture
def session():
    """Sesión sobre una base SQLite en memoria con el esquema actual."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.database import Base
    import database.models  # noqa: F401  (registra los modelos)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
