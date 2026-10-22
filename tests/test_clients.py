"""Tests de fichas de cliente (services/clients.py)."""

from types import SimpleNamespace

from services import clients


def test_get_or_create_client_ignora_mayusculas_y_espacios(session):
    created = clients.get_or_create_client(session, "  Acme  ")
    assert created.name == "Acme"
    assert clients.get_or_create_client(session, "ACME").id == created.id
    assert clients.client_names(session) == ["Acme"]


def test_find_client_nombre_vacio(session):
    assert clients.find_client(session, "") is None
    assert clients.find_client(session, None) is None


def test_link_project_normaliza_el_nombre(session):
    from database.models import Project

    clients.get_or_create_client(session, "Acme")
    project = Project(name="Obra", client="acme")
    session.add(project)
    session.flush()

    client = clients.link_project(session, project, "acme")
    assert project.client_id == client.id
    assert project.client == "Acme"


def test_client_for_project(session):
    from database.models import Project

    project = Project(name="Obra", client="Nuevo")
    session.add(project)
    session.flush()

    client = clients.client_for_project(session, project)
    assert client.name == "Nuevo"
    assert project.client_id == client.id
    assert clients.client_for_project(session, project).id == client.id

    without_client = Project(name="Vacío", client="")
    assert clients.client_for_project(session, without_client) is None


def test_missing_fiscal_data():
    client = SimpleNamespace(tax_id=" ", address=None, city="Madrid")
    assert clients.missing_fiscal_data(client) == ["CIF", "Dirección"]


def test_invoice_address_omite_espana():
    client = SimpleNamespace(address="Calle 1 ", city="28001 Madrid", country="España")
    assert clients.invoice_address(client) == "Calle 1\n28001 Madrid"
    client.country = "Francia"
    assert clients.invoice_address(client) == "Calle 1\n28001 Madrid\nFrancia"
    client.address = None
    assert clients.invoice_address(client) == "28001 Madrid\nFrancia"
