from services import manual


def test_manual_genera_un_pdf_con_todas_las_secciones(tmp_path):
    path = manual.render_manual_pdf(tmp_path / "manual.pdf", "1.0.0")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    # Portada + índice y una página por sección, como mínimo.
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= len(manual.SECTIONS) + 1
