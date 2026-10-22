"""Fichas de cliente: búsqueda, alta automática y enlace con proyectos."""

from sqlalchemy import func

from database.models import Client, Project


def client_names(session) -> list[str]:
    return [name for (name,) in session.query(Client.name).order_by(Client.name).all()]


def find_client(session, name: str):
    name = (name or "").strip()
    if not name:
        return None
    return (
        session.query(Client)
        .filter(func.lower(Client.name) == name.lower())
        .first()
    )


def get_or_create_client(session, name: str) -> Client:
    """Devuelve la ficha con ese nombre o la crea vacía si no existe."""
    client = find_client(session, name)
    if client is None:
        client = Client(name=name.strip())
        session.add(client)
        session.flush()
    return client


def link_project(session, project: Project, name: str):
    """Enlaza el proyecto con su cliente (creándolo si hace falta)."""
    client = get_or_create_client(session, name)
    project.client_id = client.id
    project.client = client.name
    return client


def client_for_project(session, project: Project):
    if project.client_id is not None:
        client = session.get(Client, project.client_id)
        if client is not None:
            return client
    return link_project(session, project, project.client) if project.client else None


def missing_fiscal_data(client) -> list[str]:
    missing = []
    if not (client.tax_id or "").strip():
        missing.append("CIF")
    if not (client.address or "").strip():
        missing.append("Dirección")
    if not (client.city or "").strip():
        missing.append("CP y población")
    return missing


def invoice_address(client) -> str:
    lines = [client.address, client.city]
    if client.country and client.country.strip().lower() not in ("españa", "spain", "es"):
        lines.append(client.country)
    return "\n".join(line.strip() for line in lines if line and line.strip())
