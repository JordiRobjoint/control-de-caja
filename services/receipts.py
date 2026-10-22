"""
Lectura de tickets y facturas de gasto con Claude (OCR + extracción).

* El documento (foto, escaneo o PDF) se envía a la API de Anthropic, que
  devuelve proveedor, fecha, importes e IVA ya separados.
* La clave de API se guarda en el Administrador de credenciales de
  Windows (keyring), no en la base de datos: la base se copia a carpetas
  externas y la clave no debe viajar con ella.
* El documento se archiva en `<carpeta>\\<año>\\<MM>.<MES>` con nombres
  como `2026_10_04_Peaje.pdf` (carpeta elegida en Configuración) y el
  gasto guarda su ruta.

Sin Qt: la interfaz llama a `read_receipt()` desde un hilo aparte.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from services.cashflow import add_money, round_money


MODEL = "claude-opus-5-5"

KEYRING_SERVICE = "ControlDeCaja"
KEYRING_USER = "anthropic_api_key"

EXPENSE_FOLDER_KEY = "expense_folder"

PDF_EXTENSIONS = {".pdf"}
# Formatos que la API acepta tal cual.
API_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
# Formatos que se convierten a JPEG antes de enviarlos (escáner).
CONVERTIBLE_IMAGES = {".bmp", ".tif", ".tiff"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | set(API_IMAGE_TYPES) | CONVERTIBLE_IMAGES

FILE_FILTER = (
    "Tickets y facturas (*.pdf *.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff)"
)

# La API admite imágenes de hasta 5 MB; por encima de este lado largo
# no se gana precisión y solo se paga más.
MAX_IMAGE_SIDE = 2400
MAX_IMAGE_BYTES = 4_500_000
MAX_PDF_BYTES = 30_000_000


class ReceiptError(Exception):
    """Error con un mensaje apto para enseñar al usuario."""


# ============================================================
# CLAVE DE API
# ============================================================

def get_api_key() -> str:
    try:
        import keyring
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        key = None
    return key or os.environ.get("ANTHROPIC_API_KEY", "")


def set_api_key(key: str):
    import keyring
    key = key.strip()
    if key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except keyring.errors.PasswordDeleteError:
        pass


def has_api_key() -> bool:
    return bool(get_api_key())


# ============================================================
# PREPARAR EL DOCUMENTO
# ============================================================

def _encode(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _image_to_jpeg(path: Path) -> bytes:
    """Gira según EXIF, reduce si hace falta y devuelve un JPEG."""
    from PIL import Image, ImageOps

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        for quality in (88, 80, 70, 60):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            if buffer.tell() <= MAX_IMAGE_BYTES:
                return buffer.getvalue()
    raise ReceiptError("La imagen es demasiado grande incluso comprimida.")


def document_block(path: str | Path) -> dict:
    """Bloque de contenido de la API para el archivo."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ReceiptError(
            f"Formato no admitido ({suffix or 'sin extensión'}). "
            "Usa PDF, JPG, PNG, WEBP, GIF, BMP o TIFF."
        )
    if not path.is_file():
        raise ReceiptError(f"No se encuentra el archivo:\n{path}")

    if suffix in PDF_EXTENSIONS:
        data = path.read_bytes()
        if len(data) > MAX_PDF_BYTES:
            raise ReceiptError("El PDF supera los 30 MB.")
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": _encode(data)},
        }

    data = path.read_bytes()
    media_type = API_IMAGE_TYPES.get(suffix)
    small = len(data) <= MAX_IMAGE_BYTES
    if media_type is None or not small or _too_large(path):
        data, media_type = _image_to_jpeg(path), "image/jpeg"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": _encode(data)},
    }


def _too_large(path: Path) -> bool:
    from PIL import Image
    try:
        with Image.open(path) as image:
            return max(image.size) > MAX_IMAGE_SIDE
    except OSError:
        return False


# ============================================================
# EXTRACCIÓN
# ============================================================

SCHEMA = {
    "type": "object",
    "properties": {
        "is_expense_document": {"type": "boolean"},
        "supplier": {"type": "string"},
        "supplier_tax_id": {"type": "string"},
        "file_label": {"type": "string"},
        "concept": {"type": "string"},
        "category": {"type": "string"},
        "date": {"type": "string"},
        "invoice_reference": {"type": "string"},
        "vat_lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rate": {"type": "number"},
                    "base": {"type": "number"},
                    "vat": {"type": "number"},
                },
                "required": ["rate", "base", "vat"],
                "additionalProperties": False,
            },
        },
        "total": {"type": "number"},
        "paid": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": [
        "is_expense_document", "supplier", "supplier_tax_id", "file_label", "concept",
        "category", "date", "invoice_reference", "vat_lines", "total",
        "paid", "notes",
    ],
    "additionalProperties": False,
}

SYSTEM = """\
Lees tickets y facturas de gasto de una empresa española y devuelves sus \
datos para registrarlos en contabilidad. Copia los datos tal como aparecen \
en el documento; si un dato no aparece, déjalo vacío ("") en lugar de \
inventarlo.

- supplier: nombre comercial o razón social de quien emite el documento \
(el vendedor), nunca la empresa compradora.
- supplier_tax_id: NIF/CIF del emisor.
- file_label: una o dos palabras para nombrar el archivo, como se \
nombraría a mano: el nombre corto y conocido del proveedor si es una \
empresa reconocible (Renfe, Ikea, Leroy Merlin, MediaMarkt, Repsol) o lo \
comprado si es un ticket genérico (Peaje, Gasolina, Parking, Comida).
- concept: descripción breve (máx. 60 caracteres) de lo comprado, útil para \
reconocer el gasto en un listado. Ej. "Hotel 2 noches Vigo", "Gasoil", \
"Comida equipo".
- category: exactamente una de las categorías dadas; si ninguna encaja, "Otros".
- date: fecha de emisión en formato AAAA-MM-DD.
- invoice_reference: número de factura, factura simplificada o ticket.
- vat_lines: una línea por tipo de IVA del desglose, con base, tipo (%) y \
cuota. Si el ticket solo dice "IVA incluido" con el total, calcula base y \
cuota a partir del tipo indicado (o del habitual para ese producto en \
España). Si el documento no lleva IVA (exento, extranjero, tasas), una \
línea con tipo 0 y base igual al total.
- total: importe total a pagar del documento.
- paid: true si el documento indica que ya está pagado (ticket de caja, \
tarjeta, "pagado"); false si es una factura pendiente de pago.
- notes: avisos breves para quien revisa (texto ilegible, varios IVA, \
moneda distinta del euro...). Vacío si no hay nada que señalar.
- is_expense_document: false si la imagen no es un ticket o factura.\
"""


def _parse_date(text: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", text or "")
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def normalize(raw: dict, categories: list[str]) -> dict:
    """
    Convierte la respuesta del modelo en los datos del formulario.

    El formulario tiene un solo tipo de IVA: con varios tipos se usa el
    tipo efectivo (cuota total / base total) y se avisa en las notas.
    """
    lines = [line for line in raw.get("vat_lines") or [] if line.get("base") is not None]
    base = round_money(add_money(*(line["base"] for line in lines))) if lines else 0.0
    vat = round_money(add_money(*(line["vat"] for line in lines))) if lines else 0.0
    total = round_money(raw.get("total") or 0)

    if not lines and total:
        base = total

    rates = sorted({round(float(line["rate"]), 2) for line in lines})
    if len(rates) == 1:
        rate = rates[0]
    elif base:
        rate = round(vat / base * 100, 2)
    else:
        rate = 0.0

    notes = [(raw.get("notes") or "").strip()]
    if len(rates) > 1:
        detail = ", ".join(
            f"{line['rate']:g}% sobre {line['base']:.2f} €" for line in lines
        )
        notes.append(f"Varios tipos de IVA ({detail}); se usa el tipo medio.")

    category = raw.get("category") or ""
    if category not in categories:
        category = "Otros" if "Otros" in categories else (categories[0] if categories else "")

    return {
        "is_expense_document": bool(raw.get("is_expense_document", True)),
        "supplier": (raw.get("supplier") or "").strip(),
        "supplier_tax_id": (raw.get("supplier_tax_id") or "").strip(),
        "file_label": file_label(raw.get("file_label") or ""),
        "concept": (raw.get("concept") or "").strip()[:200],
        "category": category,
        "date": _parse_date(raw.get("date") or ""),
        "invoice_reference": (raw.get("invoice_reference") or "").strip()[:150],
        "base_amount": base,
        "vat_rate": rate,
        "vat_amount": vat,
        "total_amount": total or round_money(add_money(base, vat)),
        "paid": bool(raw.get("paid")),
        "notes": " ".join(note for note in notes if note),
    }


def read_receipt(path: str | Path, categories: list[str], *,
                 company: str = "", client=None) -> dict:
    """
    Lee el ticket o factura y devuelve los datos normalizados (ver
    `normalize`). Lanza ReceiptError con un mensaje legible si falla.
    """
    import anthropic

    block = document_block(path)

    if client is None:
        key = get_api_key()
        if not key:
            raise ReceiptError(
                "Falta la clave de API de Anthropic.\n"
                "Añádela en Configuración → Lectura de tickets."
            )
        client = anthropic.Anthropic(api_key=key, timeout=120.0)

    prompt = (
        f"Categorías posibles: {', '.join(categories)}.\n"
        + (f"La empresa compradora (no es el proveedor) es: {company}.\n" if company else "")
        + "Extrae los datos de este documento."
    )

    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": [block, {"type": "text", "text": prompt}]}],
        )
    except anthropic.AuthenticationError:
        raise ReceiptError("La clave de API de Anthropic no es válida.")
    except anthropic.PermissionDeniedError:
        raise ReceiptError("La clave de API no tiene permiso para usar este modelo.")
    except anthropic.RateLimitError:
        raise ReceiptError("Demasiadas peticiones seguidas. Espera un minuto y repite.")
    except anthropic.BadRequestError as error:
        if "workspace" in str(error.message):
            raise ReceiptError(
                "La clave de API no pertenece a ningún espacio de trabajo.\n"
                "En console.anthropic.com crea una clave nueva dentro de un "
                "workspace (Settings → Workspaces → Default → API keys) y "
                "pégala en Configuración → Lectura de tickets."
            )
        raise ReceiptError(f"La API ha rechazado el documento:\n{error.message}")
    except anthropic.APIStatusError as error:
        raise ReceiptError(f"Error del servicio de Anthropic ({error.status_code}). Prueba más tarde.")
    except anthropic.APIConnectionError:
        raise ReceiptError("No hay conexión con Anthropic. Revisa internet.")

    if response.stop_reason == "refusal":
        raise ReceiptError("El servicio no ha querido procesar este documento.")
    if response.stop_reason == "max_tokens":
        raise ReceiptError("La respuesta se ha cortado. Prueba de nuevo.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raise ReceiptError("No se ha podido interpretar la respuesta. Prueba de nuevo.")

    return normalize(raw, categories)


# ============================================================
# ARCHIVO DEL DOCUMENTO
# ============================================================

def default_expense_folder() -> Path:
    return Path.home() / "Documents" / "Control de Caja" / "Gastos"


MONTHS = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
    "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


def file_label(text: str) -> str:
    """
    Palabra para el nombre del archivo, sin tildes, espacios ni
    símbolos: "Quirón Salud" -> "QuironSalud", "media markt" -> "MediaMarkt".
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = re.findall(r"[A-Za-z0-9]+", text)
    label = "".join(w if w[0].isupper() else w.capitalize() for w in words)
    return label[:30]


def month_folder(base: Path, day: date) -> Path:
    """`<carpeta>/2026/10.OCTUBRE`"""
    return base / str(day.year) / f"{day.month:02d}.{MONTHS[day.month - 1]}"


def archive_target(source: str | Path, *, expense_date: date | None = None,
                   label: str = "", folder: str | Path | None = None) -> Path:
    """
    Ruta con la que se archivará el documento, sin copiar nada:
    `<carpeta>/<año>/<MM>.<MES>/<AAAA_MM_DD>_<Etiqueta>`, sin pisar otro
    archivo (Peaje, Peaje1, Peaje2…). Si ya está dentro de la carpeta de
    gastos, su ruta actual.
    """
    source = Path(source)
    base = Path(folder) if folder else default_expense_folder()
    try:
        source.resolve().relative_to(base.resolve())
        return source
    except ValueError:
        pass

    day = expense_date or date.today()
    target_dir = month_folder(base, day)
    label = file_label(label)
    stem = f"{day:%Y_%m_%d}" + (f"_{label}" if label else "")
    suffix = source.suffix.lower()
    target = target_dir / f"{stem}{suffix}"
    counter = 1
    while target.exists():
        target = target_dir / f"{stem}{counter}{suffix}"
        counter += 1
    return target


def archive_document(source: str | Path, *, expense_date: date | None = None,
                     label: str = "", folder: str | Path | None = None) -> Path:
    """
    Copia el documento a su sitio en la carpeta de gastos (ver
    `archive_target`) y devuelve la ruta nueva.
    """
    source = Path(source)
    target = archive_target(source, expense_date=expense_date, label=label, folder=folder)
    if target == source:
        return source
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target
