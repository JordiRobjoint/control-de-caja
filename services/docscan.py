"""
Escaneo de documentos a partir de una foto (como CamScanner).

1. Busca los cuatro bordes del ticket o factura en la foto.
2. Lo recorta y endereza (corrige la perspectiva).
3. Lo mejora: fondo blanco, sin sombras y texto negro nítido.
4. Lo guarda como PDF.

Si no encuentra los bordes con seguridad, no recorta nada: solo mejora
la foto entera, para no cortar nunca parte del ticket.

Funciona sin internet (OpenCV). Sin Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Lado largo con el que se buscan los bordes (rápido y suficiente).
DETECT_SIDE = 1000
# El documento debe ocupar al menos esta parte de la foto.
MIN_AREA_RATIO = 0.15
# Resolución del PDF: 200 ppp es la de un escáner normal de oficina.
PDF_DPI = 200
# Lado largo máximo de la imagen final.
MAX_SIDE = 3000


@dataclass
class ScanResult:
    pdf: Path
    cropped: bool


def _load(path: Path):
    """Foto como matriz BGR, ya girada según el EXIF del móvil."""
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        rgb = np.asarray(image)
    return rgb[:, :, ::-1].copy()


def _order_corners(points):
    """Esquinas en orden: arriba-izq, arriba-dcha, abajo-dcha, abajo-izq."""
    import numpy as np

    points = points.reshape(4, 2).astype("float32")
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).ravel()
    return np.array([
        points[np.argmin(sums)],
        points[np.argmin(diffs)],
        points[np.argmax(sums)],
        points[np.argmax(diffs)],
    ], dtype="float32")


def _quads_from_mask(mask, min_area):
    """Cuadriláteros candidatos, del más grande al más pequeño."""
    import cv2

    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        if cv2.contourArea(contour) < min_area:
            break
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        for epsilon in (0.02, 0.03, 0.04, 0.05):
            approx = cv2.approxPolyDP(hull, epsilon * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                yield _order_corners(approx)
                break


def _angles_ok(corners) -> bool:
    """Esquinas casi rectas: una foto en perspectiva no deforma más."""
    import numpy as np

    for i in range(4):
        a = corners[i - 1] - corners[i]
        b = corners[(i + 1) % 4] - corners[i]
        cos = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        if not 50 <= np.degrees(np.arccos(np.clip(cos, -1, 1))) <= 130:
            return False
    return True


def _nothing_outside(gray, corners) -> bool:
    """
    Fuera del documento solo debe haber fondo. Si fuera queda papel (el
    mismo tono que el ticket) con texto, el recuadro es una tabla de la
    propia hoja o corta una esquina, y recortar por ahí perdería datos.
    Un fondo de otro tono (mesa, madera) puede tener vetas sin problema.
    """
    import cv2
    import numpy as np

    ink = cv2.adaptiveThreshold(
        gray, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15
    )
    inside = np.zeros_like(gray)
    cv2.fillConvexPoly(inside, corners.astype(np.int32), 1)
    margin = max(5, min(gray.shape) // 30)
    near = cv2.dilate(inside, np.ones((margin, margin), np.uint8))
    outside = near == 0

    if outside.mean() < 0.03:
        return True

    # Papel fuera del recuadro: zonas con el tono del papel de dentro,
    # cerradas para incluir las letras que hay sobre ellas.
    paper_tone = float(np.percentile(gray[inside == 1], 75))
    paper = (gray > paper_tone - 40).astype(np.uint8)
    paper = cv2.morphologyEx(
        paper, cv2.MORPH_CLOSE, np.ones((margin * 2, margin * 2), np.uint8)
    )
    paper_outside = (paper == 1) & outside
    if paper_outside.mean() < 0.02:
        return True

    ink_in = ink[inside == 1].mean()
    ink_out = ink[paper_outside].mean()
    return ink_out <= max(0.01, 0.3 * ink_in)


def find_document(image):
    """
    Esquinas del documento en coordenadas de `image`, o None.

    Prueba dos métodos: bordes (Canny), que va bien con fondos de
    cualquier color, y papel claro sobre fondo más oscuro (Otsu).
    """
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = DETECT_SIDE / max(height, width)
    small = cv2.resize(image, (round(width * scale), round(height * scale)),
                       interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    plain = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    image_area = small.shape[0] * small.shape[1]
    min_area = MIN_AREA_RATIO * image_area
    kernel = np.ones((5, 5), np.uint8)

    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    _, paper = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, kernel, iterations=3)

    for mask in (edges, paper):
        for corners in _quads_from_mask(mask, min_area):
            # Las cuatro esquinas tienen que verse: si una toca el borde
            # de la foto, el papel sigue fuera y no se sabe dónde acaba.
            if not _corners_in_frame(corners, small.shape):
                continue
            if _angles_ok(corners) and _nothing_outside(plain, corners):
                return corners / scale
    return None


def find_paper(image):
    """
    Recorte aproximado cuando no se ven las cuatro esquinas: el
    cuadrilátero que envuelve la zona de papel (la región clara más
    grande), aunque toque el borde de la foto. Quita mesa, teclado y
    demás fondo. None si no hay una zona de papel clara.
    """
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = DETECT_SIDE / max(height, width)
    small = cv2.resize(image, (round(width * scale), round(height * scale)),
                       interpolation=cv2.INTER_AREA)

    # Papel: poco colorido y no oscuro. No se usa el brillo de Otsu
    # porque con sol directo la parte en sombra del papel quedaría fuera;
    # una sombra sigue siendo gris, la madera o la mesa tienen color y un
    # teclado es casi negro.
    hsv = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2HSV), (7, 7), 0)
    paper = ((hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 95)).astype(np.uint8) * 255
    kernel = np.ones((9, 9), np.uint8)
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, kernel, iterations=3)
    paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, kernel, iterations=2)

    contours, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    image_area = small.shape[0] * small.shape[1]
    if cv2.contourArea(contour) < 0.25 * image_area:
        return None

    # Rectángulo (girado) que envuelve todo el papel: mejor que sobre un
    # poco de fondo que cortar texto.
    hull = cv2.convexHull(contour)
    quad = cv2.boxPoints(cv2.minAreaRect(hull)).reshape(4, 1, 2)

    corners = _order_corners(quad)
    corners[:, 0] = corners[:, 0].clip(0, small.shape[1] - 1)
    corners[:, 1] = corners[:, 1].clip(0, small.shape[0] - 1)
    # Si ocupa casi toda la foto no hay nada que quitar.
    if cv2.contourArea(corners) > 0.97 * image_area:
        return None
    return corners / scale


def suggest_corners(image):
    """
    Esquinas propuestas para recortar: el documento entero si se ve, si
    no la zona de papel, y si tampoco, la foto completa. También dice
    de dónde salen ("documento", "papel" o "foto").
    """
    import numpy as np

    corners = find_document(image)
    if corners is not None:
        return corners, "documento"
    corners = find_paper(image)
    if corners is not None:
        return corners, "papel"
    height, width = image.shape[:2]
    return np.float32(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
    ), "foto"


def _corners_in_frame(corners, shape) -> bool:
    height, width = shape[:2]
    margin = 0.01 * max(height, width)
    return all(
        margin <= x <= width - 1 - margin and margin <= y <= height - 1 - margin
        for x, y in corners
    )


def _warp(image, corners):
    import cv2
    import numpy as np

    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    target = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(image, matrix, (width, height),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def enhance(image):
    """
    Aspecto de escáner: se divide por el fondo estimado (quita sombras y
    el tono del papel) y se estira el contraste. Gris, no blanco y negro
    puro, para no perder letras finas de tickets térmicos gastados.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    size = max(15, (min(gray.shape) // 25) | 1)
    background = cv2.morphologyEx(
        gray, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)),
    )
    background = cv2.GaussianBlur(background, (0, 0), size / 3)
    flat = cv2.divide(gray, background, scale=255)

    low, high = np.percentile(flat, (1, 99.5))
    if high - low < 10:
        return flat
    stretched = np.clip((flat.astype("float32") - low) * 255.0 / (high - low), 0, 255)
    # Algo de oscurecimiento en los grises para que el texto quede negro.
    return (255.0 * (stretched / 255.0) ** 1.4).astype("uint8")


def _limit_size(image):
    import cv2

    height, width = image.shape[:2]
    scale = MAX_SIDE / max(height, width)
    if scale >= 1:
        return image
    return cv2.resize(image, (round(width * scale), round(height * scale)),
                      interpolation=cv2.INTER_AREA)


def save_pdf(gray, path: Path) -> Path:
    from PIL import Image

    Image.fromarray(gray).save(path, "PDF", resolution=PDF_DPI)
    return path


def to_fractions(corners, shape) -> list[list[float]]:
    """Esquinas en píxeles -> fracciones 0..1 del ancho y alto de la foto."""
    height, width = shape[:2]
    return [[round(float(x) / (width - 1), 4), round(float(y) / (height - 1), 4)]
            for x, y in corners]


def from_fractions(fractions, shape):
    """Fracciones 0..1 -> esquinas en píxeles, ordenadas."""
    import numpy as np

    height, width = shape[:2]
    points = np.float32([[x * (width - 1), y * (height - 1)] for x, y in fractions])
    return _order_corners(points)


def valid_fractions(fractions) -> bool:
    """Cuatro esquinas dentro de la foto que encierran algo de área."""
    import cv2
    import numpy as np

    try:
        points = np.float32(fractions)
    except (TypeError, ValueError):
        return False
    if points.shape != (4, 2) or not np.isfinite(points).all():
        return False
    if (points < -0.001).any() or (points > 1.001).any():
        return False
    return cv2.contourArea(_order_corners(points)) > 0.01


def suggest_fractions(photo: str | Path) -> tuple[list[list[float]], str]:
    """Recorte propuesto para una foto, en fracciones (para el móvil)."""
    image = _load(Path(photo))
    corners, how = suggest_corners(image)
    return to_fractions(corners, image.shape), how


def scan_photo(photo: str | Path, pdf: str | Path | None = None,
               corners=None) -> ScanResult:
    """
    Convierte la foto de un documento en un PDF escaneado. Por defecto el
    PDF va junto a la foto, con el mismo nombre.

    `corners`: recorte marcado a mano (fracciones 0..1, p. ej. desde el
    móvil). Sin él, se recorta solo si se ve el documento entero.
    """
    photo = Path(photo)
    pdf = Path(pdf) if pdf else photo.with_suffix(".pdf")

    image = _load(photo)
    if corners is not None:
        points = from_fractions(corners, image.shape)
    else:
        points = find_document(image)
    if points is not None:
        image = _warp(image, points)

    save_pdf(enhance(_limit_size(image)), pdf)
    return ScanResult(pdf=pdf, cropped=points is not None)
