"""
Escaneo de fotos (recorte, enderezado y mejora). Las fotos son
sintéticas: un ticket con texto colocado en perspectiva sobre un fondo.
"""

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from services import docscan  # noqa: E402

TICKET_W, TICKET_H = 600, 1100


def ticket(with_table=False):
    paper = np.full((TICKET_H, TICKET_W, 3), 245, np.uint8)
    cv2.putText(paper, "MERCADONA S.A.", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)
    y = 60
    for i in range(22):
        y += 42
        cv2.putText(paper, f"ARTICULO {i:02d}   {i * 1.37:6.2f}", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 40), 2)
    if with_table:
        # Recuadro interior: no debe confundirse con el borde del papel.
        cv2.rectangle(paper, (25, 380), (575, 760), (30, 30, 30), 3)
    return paper


def photo(background, quad, paper):
    h, w = paper.shape[:2]
    matrix = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(quad)
    )
    height, width = background.shape[:2]
    warped = cv2.warpPerspective(paper, matrix, (width, height))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), matrix, (width, height))
    result = background.copy()
    result[mask > 0] = warped[mask > 0]
    noise = np.random.default_rng(1).normal(0, 4, result.shape)
    return np.clip(result + noise, 0, 255).astype(np.uint8)


QUAD = [[420, 350], [1380, 450], [1450, 2050], [330, 2000]]


def dark():
    return np.full((2400, 1800, 3), 50, np.uint8)


def wood():
    stripes = (np.sin(np.arange(1800) / 9.0) * 25 + 120).astype(np.uint8)
    image = np.zeros((2400, 1800, 3), np.uint8)
    image[:] = np.stack([stripes * 0.55, stripes * 0.8, stripes], axis=-1).astype(np.uint8)
    return image


def save(tmp_path, image, name="foto.jpg"):
    path = tmp_path / name
    cv2.imwrite(str(path), image)
    return path


@pytest.mark.parametrize("background", [dark, wood])
def test_recorta_y_endereza_el_ticket(tmp_path, background):
    image = photo(background(), QUAD, ticket())
    corners = docscan.find_document(image)
    assert corners is not None
    # Esquinas a menos de 2 % del tamaño de la foto de las reales.
    assert np.abs(corners - np.float32(QUAD)).max() < 0.02 * 2400

    # El resultado es un rectángulo con los lados más largos del ticket
    # tal como se ve en la foto.
    tl, tr, br, bl = np.float32(QUAD)
    expected = (
        max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))
        / max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))
    )
    warped = docscan._warp(image, corners)
    assert warped.shape[0] / warped.shape[1] == pytest.approx(expected, rel=0.05)


def test_una_tabla_dentro_del_ticket_no_engana(tmp_path):
    image = photo(dark(), QUAD, ticket(with_table=True))
    corners = docscan.find_document(image)
    assert corners is not None
    assert np.abs(corners - np.float32(QUAD)).max() < 0.02 * 2400


def test_si_la_hoja_no_cabe_entera_no_recorta(tmp_path):
    # La hoja se sale de la foto por abajo: no hay cuatro esquinas.
    quad = [[200, 150], [1600, 200], [1700, 2600], [100, 2550]]
    image = photo(dark(), quad, ticket(with_table=True))
    assert docscan.find_document(image) is None


def test_scan_photo_crea_un_pdf(tmp_path):
    source = save(tmp_path, photo(dark(), QUAD, ticket()))
    result = docscan.scan_photo(source)
    assert result.cropped
    assert result.pdf == source.with_suffix(".pdf")
    assert result.pdf.read_bytes().startswith(b"%PDF")

    blank = save(tmp_path, np.full((800, 600, 3), 200, np.uint8), "blanco.jpg")
    result = docscan.scan_photo(blank, tmp_path / "otro.pdf")
    assert not result.cropped
    assert (tmp_path / "otro.pdf").exists()


def test_la_mejora_deja_el_fondo_blanco_y_el_texto_oscuro():
    paper = ticket()
    # Sombra fuerte de izquierda a derecha.
    shade = np.tile(np.linspace(0.45, 1.0, TICKET_W, dtype=np.float32), (TICKET_H, 1))[..., None]
    shaded = (paper * shade).astype(np.uint8)
    result = docscan.enhance(shaded)
    background = result[TICKET_H - 80:, :]
    assert background[:, :100].mean() > 230
    assert background[:, -100:].mean() > 230
    assert result[40:70, 40:300].min() < 60


def test_recorte_marcado_en_el_movil(tmp_path):
    image = photo(dark(), QUAD, ticket())
    source = save(tmp_path, image)
    h, w = image.shape[:2]
    fractions = [[x / (w - 1), y / (h - 1)] for x, y in QUAD]

    result = docscan.scan_photo(source, corners=fractions)
    assert result.cropped
    # El recorte es el marcado: la foto enderezada es el ticket y nada más.
    corners = docscan.from_fractions(fractions, image.shape)
    assert np.abs(corners - np.float32(QUAD)).max() < 1.0
    warped = docscan.enhance(docscan._warp(image, corners))
    border = np.concatenate([warped[:8].ravel(), warped[-8:].ravel()])
    assert border.mean() > 200          # papel, no el fondo oscuro


def test_esquinas_validas():
    assert docscan.valid_fractions([[0, 0], [1, 0], [1, 1], [0, 1]])
    assert not docscan.valid_fractions([[0, 0], [1, 0], [1, 1]])
    assert not docscan.valid_fractions([[0, 0], [1.5, 0], [1, 1], [0, 1]])
    assert not docscan.valid_fractions([[0.5, 0.5]] * 4)
    assert not docscan.valid_fractions("no")


def test_propuesta_cuando_la_hoja_no_cabe_entera():
    # La hoja se sale por abajo: no hay documento entero, pero se propone
    # quitar el fondo de los lados sin cortar el papel.
    quad = [[300, 150], [1500, 200], [1600, 2600], [200, 2550]]
    image = photo(dark(), quad, ticket(with_table=True))
    corners, how = docscan.suggest_corners(image)
    assert how == "papel"
    xs, ys = corners[:, 0], corners[:, 1]
    assert xs.min() <= 200 + 30 and xs.max() >= 1600 - 30   # no corta papel
    assert ys.min() <= 150 + 30
    assert xs.min() > 50 or xs.max() < 1750                  # quita fondo


def test_sin_papel_propone_la_foto_entera():
    image = np.full((800, 600, 3), 40, np.uint8)
    corners, how = docscan.suggest_corners(image)
    assert how == "foto"
    assert docscan.to_fractions(corners, image.shape) == [[0, 0], [1, 0], [1, 1], [0, 1]]
