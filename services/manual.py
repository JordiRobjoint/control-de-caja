"""
Manual de usuario en PDF.

Se genera con reportlab al pulsar «Manual de usuario» en el menú, así que
siempre corresponde a la versión instalada. El texto vive aquí: si cambia
una pantalla, se actualiza su sección.
"""

from __future__ import annotations

from pathlib import Path


TITLE = "Control de Caja · Manual de usuario"


# ============================================================
# CONTENIDO
# ============================================================
# Cada sección: (título, [bloques]). Bloques:
#   ("p", texto)            párrafo
#   ("h", texto)            subtítulo
#   ("ul", [textos])        lista
#   ("tip", texto)          recuadro de nota
#   ("table", [filas])      tabla; la primera fila es la cabecera
# Admite <b> e <i>. Solo caracteres de la fuente Helvetica (sin flechas
# ni emojis).

SECTIONS = [
    ("1. Qué es Control de Caja", [
        ("p", "Control de Caja es una aplicación de escritorio para llevar la "
              "tesorería de una empresa que trabaja por proyectos: los pedidos "
              "de cada cliente, lo que se va a cobrar y lo que se va a pagar, "
              "los gastos fijos, los préstamos y el IVA. Con todo ello calcula "
              "el <b>saldo actual</b> y la <b>previsión de caja</b> de los "
              "próximos 12 meses, y genera las <b>facturas en PDF</b>."),
        ("p", "Los datos se guardan solo en tu ordenador, en una base de datos "
              "local. No hace falta internet salvo para la lectura automática "
              "de tickets."),
        ("h", "Cómo se organiza la información"),
        ("ul", [
            "<b>Cliente</b>: la empresa a la que facturas, con sus datos fiscales.",
            "<b>Proyecto</b>: un trabajo para un cliente.",
            "<b>Pedido</b>: lo que el cliente te ha encargado dentro de un proyecto, con su importe sin IVA.",
            "<b>Cobro</b>: cada hito de cobro de un pedido (anticipo, pago final...). Es lo que se factura.",
            "<b>Gasto o pago</b>: lo que paga la empresa, de un proyecto o general.",
            "<b>Financiación</b>: préstamos recibidos y sus cuotas.",
        ]),
        ("tip", "Orden recomendado para empezar: 1) Configuración, 2) Clientes, "
                "3) Proyectos, 4) Pedidos y cobros de cada proyecto, 5) Gastos "
                "generales y financiación."),
    ]),

    ("2. Primeros pasos", [
        ("h", "La ventana principal"),
        ("p", "A la izquierda está el menú con todas las pantallas. Al final del "
              "menú, el botón <b>Manual de usuario</b> abre este documento."),
        ("h", "Configuración inicial"),
        ("ul", [
            "En <b>Configuración</b> pon el <b>capital inicial</b>: el dinero con el que arrancó la empresa.",
            "Rellena los <b>datos fiscales de la empresa</b>. Razón social, CIF, dirección y población son obligatorios para facturar. Si quieres, elige también el <b>logo</b>: sale en el menú y en las facturas.",
            "En <b>Usuario</b> puedes poner tu nombre y cargo para la cabecera del Dashboard.",
            "Revisa la <b>numeración de facturas</b>: si ya tienes facturas emitidas, pon en «Siguiente número» el que toca.",
            "Pulsa <b>Guardar configuración</b>.",
        ]),
        ("h", "Trabajar con las tablas"),
        ("ul", [
            "Haz <b>doble clic</b> en una fila para editarla (o para abrir la ficha, en Proyectos).",
            "Para editar o eliminar con los botones, selecciona antes la fila.",
            "En Pedidos, Cobros y Pagos, pulsa la cabecera de una columna para <b>filtrar u ordenar</b> como en Excel: marca los valores que quieres ver, busca por texto u ordena de A a Z. <b>Quitar filtros</b> deja la tabla completa.",
            "Los campos marcados con * son obligatorios.",
        ]),
    ]),

    ("3. Dashboard", [
        ("p", "Resumen general de la empresa, o de un proyecto si lo eliges en "
              "el desplegable <b>Proyecto</b>."),
        ("tip", "Al abrir la aplicación los importes salen ocultos (•••••). Pulsa "
                "<b>Mostrar importes</b> para verlos y <b>Ocultar importes</b> "
                "para volver a taparlos, por ejemplo si hay alguien delante."),
        ("ul", [
            "<b>Saldo actual</b>: capital inicial + todo lo cobrado - todo lo pagado.",
            "<b>Cobros pendientes</b> y <b>Pagos pendientes</b>: lo que falta por cobrar y por pagar, incluidos los vencidos.",
            "<b>Proyectos activos</b>: proyectos «En curso».",
            "<b>Resultado del ejercicio</b> (sin IVA) del año elegido: el real (facturado - gastos ya imputados) y el previsto al cierre del año, con sus ingresos y gastos previstos.",
            "<b>Evolución prevista de caja</b>: el saldo mes a mes. Pasa el ratón por la línea para ver el importe exacto de cada mes.",
            "<b>Distribución de gastos</b> por categoría en el año elegido.",
            "<b>Próximos cobros</b> y <b>próximos pagos</b>: los cinco siguientes.",
        ]),
        ("p", "En la vista de un proyecto la previsión parte de 0 € y no lleva "
              "IVA, para ver solo lo que aporta el proyecto. Si el proyecto tiene "
              "fecha límite de cálculo, la gráfica cubre todo su periodo."),
    ]),

    ("4. Clientes", [
        ("p", "Ficha fiscal de cada cliente. Se usa automáticamente al facturar."),
        ("ul", [
            "<b>Nombre</b>: nombre corto con el que lo eliges en los proyectos.",
            "<b>Razón social</b>, si es distinta del nombre. Es lo que sale en la factura.",
            "<b>CIF / NIF</b>, <b>dirección</b>, <b>CP y población</b> y <b>país</b>.",
            "<b>Email</b> y <b>teléfono</b> de facturación.",
            "<b>Vencimiento facturas</b>: días de pago de este cliente. Si se deja «Por defecto», se usan los de Configuración.",
        ]),
        ("p", "La columna <b>Datos fiscales</b> avisa de lo que falta para "
              "facturar. Un cliente con proyectos no se puede eliminar: cambia "
              "antes el cliente de esos proyectos. Si al crear un proyecto "
              "escribes un cliente nuevo, se crea su ficha y luego la completas aquí."),
    ]),

    ("5. Proyectos", [
        ("p", "Lista de proyectos con buscador (por proyecto, cliente o "
              "referencia) y filtro por estado. <b>+ Nuevo proyecto</b> abre el "
              "formulario y el <b>doble clic</b> abre la ficha del proyecto."),
        ("h", "Datos del proyecto"),
        ("ul", [
            "<b>Nombre</b> y <b>cliente</b> (obligatorios), y una <b>referencia</b> interna o del cliente.",
            "<b>Fecha inicio</b> y <b>fecha fin</b>.",
            "<b>Fecha límite de cálculo</b>: hasta cuándo se cuentan los gastos mensuales del proyecto. «Sin límite» los cuenta hasta el final de la previsión.",
            "<b>Estado</b>: Planificado, En curso, Finalizado o Cancelado.",
            "<b>Valor estimado</b> y notas.",
        ]),
        ("h", "Ficha del proyecto"),
        ("p", "Arriba muestra lo contratado (suma de pedidos), lo cobrado, los "
              "gastos y el margen (contratado - gastos). Tiene cuatro pestañas: "
              "<b>Resumen</b>, <b>Pedidos</b>, <b>Cobros</b> y <b>Gastos</b>, que "
              "funcionan igual que las pantallas generales pero solo con este "
              "proyecto. <b>Volver</b> regresa a la lista."),
        ("tip", "Un proyecto, pedido o cobro con facturas emitidas no se puede "
                "eliminar, para que la factura no se quede sin registro."),
    ]),

    ("6. Pedidos", [
        ("p", "Vista de los pedidos de todos los proyectos, con filtro por "
              "proyecto. Al crear uno desde aquí, la aplicación pregunta a qué "
              "proyecto pertenece."),
        ("ul", [
            "<b>Nº pedido</b> (obligatorio), descripción y fecha.",
            "<b>Importe base sin IVA</b> (obligatorio).",
            "<b>Estado</b>: Pendiente, Aceptado, En curso, Finalizado o Cancelado.",
        ]),
        ("p", "Eliminar un pedido elimina también sus cobros. Si cancelas un "
              "pedido, sus cobros dejan de contar en la previsión, salvo los que "
              "ya estaban facturados o cobrados."),
    ]),

    ("7. Cobros y facturación", [
        ("p", "Cada cobro es un hito de un pedido. Antes de crear un cobro el "
              "proyecto necesita al menos un pedido."),
        ("h", "Datos del cobro"),
        ("ul", [
            "<b>Pedido</b> y <b>concepto</b> (por ejemplo, Anticipo o Pago final).",
            "<b>Tipo de cálculo</b>: <i>Porcentaje</i> del pedido o <i>Importe fijo</i>. El importe es siempre sin IVA.",
            "<b>Fecha prevista</b>: cuándo esperas cobrarlo. Es la fecha que usa la previsión.",
            "<b>Estado</b>: Previsto, Facturado, Cobrado o Cancelado.",
            "<b>Nº factura</b> y <b>fecha factura</b>.",
            "<b>Fecha real de cobro</b>: solo se activa con el estado Cobrado.",
        ]),
        ("p", "Si los cobros de un pedido superan su importe, la aplicación "
              "avisa antes de guardar. El dinero solo entra en el saldo cuando "
              "el cobro está <b>Cobrado</b>."),
        ("h", "Generar una factura"),
        ("ul", [
            "Selecciona el cobro y pulsa <b>Factura</b>.",
            "Revisa número, fecha, vencimiento, IVA y los datos fiscales del cliente. Lo que cambies aquí se guarda en la ficha del cliente.",
            "Pulsa <b>Generar PDF</b>. La factura se guarda en la carpeta de facturas, por año, y el cobro pasa a <b>Facturado</b>.",
            "Si el cobro ya tiene factura, puedes <b>abrir el PDF</b> o <b>regenerarlo</b> con el mismo número, fecha, importe e IVA.",
        ]),
        ("tip", "Con la factura emitida, el pedido, el concepto, el importe y "
                "los datos de la factura quedan bloqueados. Para anularla, marca "
                "el cobro como Cancelado y pide a la gestoría la factura "
                "rectificativa. Los números de factura no se pueden repetir."),
    ]),

    ("8. Pagos y gastos", [
        ("p", "Todos los gastos de los proyectos y las facturas sueltas de la "
              "empresa. Al pulsar <b>+ Nuevo gasto</b> eliges el proyecto o "
              "«General (sin proyecto)»."),
        ("h", "Datos del gasto"),
        ("ul", [
            "<b>Categoría</b>, <b>concepto</b> y <b>proveedor</b>.",
            "<b>Tipo de pago</b>: <i>Único</i> (una fecha) o <i>Mensual</i> (desde / hasta; solo en gastos de proyecto).",
            "<b>Base imponible</b>, <b>IVA</b> y <b>total</b>: se calculan entre sí.",
            "<b>Estado</b>: Previsto, Pendiente, Pagado o Cancelado, con su fecha de pago.",
            "<b>Factura / referencia</b> y notas.",
        ]),
        ("p", "Un gasto único solo sale del saldo cuando está <b>Pagado</b>. En "
              "un gasto mensual, cada mensualidad se da por pagada al llegar su "
              "fecha. Las columnas Nº meses, Base periodo y Total periodo suman "
              "todas las mensualidades."),
        ("h", "Adjuntar y leer el ticket o la factura"),
        ("ul", [
            "<b>Leer ticket o factura...</b>: elige un PDF o una foto, o arrástralo a la ventana.",
            "<b>Escanear...</b>: lo toma del escáner conectado al ordenador.",
            "<b>Desde el móvil...</b>: aparece un código QR. Ábrelo con la cámara del móvil, haz la foto y ajusta las cuatro esquinas del recorte. El móvil tiene que estar en la misma wifi que el ordenador; la primera vez, permite el acceso en el aviso del firewall de Windows (redes privadas).",
            "<b>Ver documento</b>, <b>Quitar</b> y <b>Usar foto original</b> (guarda la foto sin recortar ni mejorar).",
        ]),
        ("p", "Si hay clave de API configurada, el documento se lee "
              "automáticamente y se rellenan proveedor, fecha, base, IVA, total, "
              "número y categoría. <b>Revisa siempre los datos antes de "
              "guardar.</b> Al guardar, el documento se archiva en la carpeta de "
              "tickets por año y mes, con un nombre como 2026_10_04_Peaje.pdf."),
    ]),

    ("9. Gastos generales", [
        ("p", "Costes fijos mensuales de la empresa que no son de ningún "
              "proyecto: nóminas, Seguridad Social, gestoría, alquiler, "
              "software, seguros..."),
        ("ul", [
            "<b>Base mensual</b> e <b>IVA</b>: la aplicación calcula el IVA y el total mensual.",
            "<b>Activo desde (1er cargo)</b>: el día de esa fecha se repite cada mes.",
            "<b>Tiene fecha de fin</b>: márcalo si el gasto termina; si no, sigue indefinidamente.",
            "<b>Estado</b>: Activo o Inactivo. Un gasto inactivo deja de contar.",
        ]),
        ("p", "Las tarjetas de arriba muestran el gasto fijo mensual sin IVA, el "
              "IVA mensual, la salida bancaria mensual y la estimación anual "
              "(mensual × 12). Cada mensualidad se da por pagada al llegar su fecha."),
    ]),

    ("10. Financiación", [
        ("p", "Préstamos bancarios y su efecto en la caja."),
        ("ul", [
            "<b>Nombre</b>, <b>banco</b>, <b>importe recibido</b> y <b>fecha de ingreso</b>: el dinero entra en el saldo ese día.",
            "<b>Plazo (meses)</b>, <b>cuota mensual</b> y <b>primera cuota</b>. La cuota se introduce a mano: no se calcula con el tipo de interés.",
            "<b>Cuotas pagadas por adelantado</b>: solo si has amortizado cuotas antes de su fecha.",
            "<b>Estado</b>: Activo, Finalizado o Cancelado.",
        ]),
        ("p", "Las cuotas se consideran domiciliadas: cada una se da por pagada "
              "al llegar su fecha. La financiación solo aparece en la vista "
              "global de la empresa, no en la de un proyecto."),
    ]),

    ("11. Tesorería", [
        ("p", "Control real y previsión de entradas y salidas, para toda la "
              "empresa o para un proyecto. <b>Actualizar</b> recalcula las cifras."),
        ("ul", [
            "<b>Saldo actual</b>, <b>cobros pendientes</b>, <b>pagos pendientes</b> y <b>saldo proyectado</b> (saldo actual + pendientes).",
            "<b>Previsión mensual</b>: entradas, salidas, flujo neto y saldo acumulado de cada mes. Lo vencido y no cobrado o pagado se suma al mes actual.",
            "<b>Movimientos</b>: cada cobro, pago, cuota y liquidación de IVA con su fecha y estado.",
            "<b>IVA (modelo 303)</b>: el IVA repercutido y soportado de cada trimestre.",
        ]),
        ("h", "IVA trimestral"),
        ("p", "La aplicación estima cada trimestre con las facturas emitidas y "
              "los gastos registrados, y prevé el pago el día 20 del mes "
              "siguiente (el 30 de enero para el cuarto trimestre). Un resultado "
              "negativo se compensa en los trimestres siguientes."),
        ("p", "Cuando la gestoría presente el 303, pulsa <b>+ Registrar "
              "liquidación</b> e introduce el resultado real y la fecha de pago: "
              "la tesorería usará ese importe en lugar de la estimación. "
              "<b>Eliminar registro</b> vuelve a la estimación."),
        ("tip", "La vista global incluye IVA y financiación. La de un proyecto "
                "parte de 0 € y va sin IVA, porque el IVA no es dinero del "
                "proyecto: se liquida con Hacienda."),
    ]),

    ("12. Configuración", [
        ("ul", [
            "<b>Tesorería</b>: capital inicial.",
            "<b>Datos fiscales de la empresa</b>: aparecen en todas las facturas. <b>Logo</b> (PNG o JPG): sale en el menú lateral y en las facturas.",
            "<b>Usuario</b>: nombre y cargo de la cabecera del Dashboard (opcionales).",
            "<b>Facturación</b>: prefijo (admite {año}, por ejemplo F{año}- genera F2026-0001), dígitos, siguiente número, vencimiento por defecto, carpeta de facturas, texto al pie y un <b>sello</b> opcional (una imagen, por ejemplo la del seguro de crédito) que sale junto a los totales.",
            "<b>Lectura de tickets</b>: clave de API de Anthropic y carpeta de tickets.",
            "<b>Copias de seguridad</b>: carpeta de copias y copia externa.",
        ]),
        ("h", "Lectura de tickets"),
        ("p", "La lectura automática la hace Claude, de Anthropic: el documento "
              "se envía a su servicio y cada lectura cuesta alrededor de un "
              "céntimo. La clave se crea en console.anthropic.com y se guarda en "
              "el Administrador de credenciales de Windows, no en la base de "
              "datos. Sin clave, el documento se adjunta igual y los datos se "
              "rellenan a mano."),
        ("p", "Recuerda pulsar <b>Guardar configuración</b> después de cualquier cambio."),
    ]),

    ("13. Copias de seguridad y datos", [
        ("p", "Cada día que abres la aplicación se guarda una copia de la base "
              "de datos y se conservan las últimas 30. Como esas copias están en "
              "el mismo disco, elige en Configuración una <b>carpeta externa</b> "
              "(OneDrive, un NAS o un USB): allí se guardará también una copia "
              "diaria. <b>Copiar ahora</b> hace una copia en el momento."),
        ("table", [
            ["Qué", "Dónde"],
            ["Base de datos", "%LOCALAPPDATA%\\ControlDeCaja\\control_de_caja.db"],
            ["Copias automáticas", "%LOCALAPPDATA%\\ControlDeCaja\\copias_seguridad"],
            ["Copia externa", "La carpeta elegida en Configuración"],
            ["Facturas PDF", "Carpeta de facturas (por defecto, en Documentos), por año"],
            ["Tickets y facturas de gasto", "Carpeta de tickets (por defecto, en Documentos), por año y mes"],
            ["Clave de API", "Administrador de credenciales de Windows"],
        ]),
        ("tip", "Para recuperar una copia, cierra la aplicación y sustituye "
                "control_de_caja.db por la copia que quieras, cambiándole el "
                "nombre a control_de_caja.db. Guarda antes el archivo actual por "
                "si acaso."),
    ]),

    ("14. Cómo calcula las cifras", [
        ("p", "Todas las pantallas usan las mismas reglas, así que las cifras "
              "coinciden siempre:"),
        ("ul", [
            "<b>Saldo real</b> = capital inicial + todo lo cobrado - todo lo pagado.",
            "Un <b>cobro</b> cuenta con su IVA (21 % salvo que se indique otro) y es real cuando está Cobrado.",
            "Un <b>gasto único</b> es real cuando está Pagado; si no, es pendiente.",
            "Los <b>gastos mensuales</b> y las <b>cuotas de préstamo</b> se dan por pagados al llegar cada fecha.",
            "Lo pendiente con fecha pasada es <b>vencido</b>: no desaparece, se suma al mes actual de la previsión.",
            "La previsión abarca <b>12 meses</b> desde el mes actual.",
            "Lo cancelado (y lo inactivo) no cuenta.",
        ]),
    ]),

    ("15. Preguntas frecuentes", [
        ("h", "No me deja crear un cobro"),
        ("p", "El proyecto necesita al menos un pedido."),
        ("h", "No me deja facturar"),
        ("p", "Faltan datos de la empresa en Configuración, el proyecto no tiene "
              "cliente o el cobro está cancelado. La aplicación indica qué falta."),
        ("h", "El saldo no cuadra con el banco"),
        ("p", "Revisa que los cobros recibidos estén en Cobrado y los gastos "
              "únicos pagados en Pagado, con su fecha real, y que el capital "
              "inicial sea correcto. Mira la pestaña Movimientos de Tesorería."),
        ("h", "El código QR del móvil no carga"),
        ("p", "El móvil y el ordenador deben estar en la misma wifi, y Windows "
              "debe permitir la aplicación en redes privadas."),
        ("h", "No se puede guardar el PDF de la factura"),
        ("p", "Probablemente está abierto en otro programa. Ciérralo y vuelve a intentarlo."),
    ]),
]


# ============================================================
# PDF
# ============================================================

def render_manual_pdf(path: str | Path, version: str = "") -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
        Spacer, Table, TableStyle,
    )

    RED = colors.HexColor("#D71920")
    INK = colors.HexColor("#202024")
    MUTED = colors.HexColor("#71717A")
    LINE = colors.HexColor("#E4E4E7")
    SOFT = colors.HexColor("#F4F4F5")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def style(name, **kw):
        base = dict(fontName="Helvetica", fontSize=10, leading=14.5, textColor=INK)
        base.update(kw)
        return ParagraphStyle(name, **base)

    s_text = style("text", spaceAfter=6)
    s_item = style("item")
    s_h1 = style("h1", fontName="Helvetica-Bold", fontSize=17, leading=22,
                 spaceBefore=4, spaceAfter=10, textColor=RED)
    s_h2 = style("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                 spaceBefore=8, spaceAfter=4)
    s_tip = style("tip", fontSize=9.5, leading=13.5)
    s_cell = style("cell", fontSize=9, leading=12)
    s_cover = style("cover", fontName="Helvetica-Bold", fontSize=30, leading=36)
    s_cover_sub = style("coversub", fontSize=13, leading=18, textColor=MUTED)
    s_toc = style("toc", fontSize=11, leading=19)

    width = A4[0] - 40 * mm
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title=TITLE,
    )

    # ---------- Portada e índice ----------
    story = [
        Spacer(1, 55 * mm),
        Paragraph("Control de Caja", s_cover),
        Spacer(1, 4 * mm),
        Paragraph("Manual de usuario y funcionamiento", s_cover_sub),
    ]
    if version:
        story.append(Paragraph(f"Versión {version}", s_cover_sub))
    story += [Spacer(1, 25 * mm), Paragraph("Contenido", s_h2)]
    story += [Paragraph(title, s_toc) for title, _ in SECTIONS]

    # ---------- Secciones ----------
    for title, blocks in SECTIONS:
        story += [PageBreak(), Paragraph(title, s_h1)]
        for kind, content in blocks:
            if kind == "p":
                story.append(Paragraph(content, s_text))
            elif kind == "h":
                story.append(Paragraph(content, s_h2))
            elif kind == "ul":
                story.append(ListFlowable(
                    [ListItem(Paragraph(text, s_item), leftIndent=14) for text in content],
                    bulletType="bullet", start="•", bulletColor=RED, bulletFontSize=11,
                    leftIndent=14, spaceAfter=6,
                ))
            elif kind == "tip":
                box = Table([[Paragraph(content, s_tip)]], colWidths=[width])
                box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, RED),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]))
                story += [Spacer(1, 3 * mm), box, Spacer(1, 4 * mm)]
            elif kind == "table":
                rows = [[Paragraph(cell, s_cell) for cell in row] for row in content]
                table = Table(rows, colWidths=[width * 0.32, width * 0.68], repeatRows=1)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story += [Spacer(1, 2 * mm), table, Spacer(1, 4 * mm)]

    def on_page(canvas, document):
        if document.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 10 * mm, TITLE)
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Pág. {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return path
