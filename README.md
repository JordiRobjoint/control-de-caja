# Control de Caja

Aplicación de escritorio para Windows que lleva la tesorería de una
empresa que trabaja por proyectos: clientes, proyectos, pedidos, cobros,
pagos, gastos fijos y préstamos. Con todo ello calcula el saldo actual y
la previsión de caja a 12 meses (con el IVA trimestral) y genera las
facturas en PDF.

> **Versión beta (0.9.0).** Gracias por probarla. Puede tener errores:
> revisa las cifras y las facturas antes de usarlas y haz copias de
> seguridad (ver más abajo). Novedades en [CHANGELOG.md](CHANGELOG.md).

---

## Para quien prueba la beta

### Instalar

1. Descarga `ControlDeCaja-0.9.0-Setup.exe` (sección **Releases** de esta
   página, o el enlace que te hayan enviado).
2. Ábrelo. Windows mostrará **«Windows protegió su PC»** porque el
   programa todavía no está firmado digitalmente: pulsa **Más
   información → Ejecutar de todas formas**.
3. Sigue el asistente. No hace falta ser administrador.

Requisitos: Windows 10 u 11 de 64 bits.

### Primeros pasos

Abre **Configuración**, rellena los datos fiscales de tu empresa (y el
logo, si quieres) y pulsa **Guardar configuración**. Después crea tus
clientes y proyectos. El botón **Manual de usuario**, al final del menú,
abre el manual completo en PDF.

### Actualizar a una versión nueva

Instala el nuevo `Setup.exe` encima: tus datos se conservan.
Desinstalar el programa tampoco borra los datos.

### Copias de seguridad

Cada día que abres la aplicación se guarda una copia de la base de
datos (se conservan las 30 últimas). Como están en el mismo disco, elige
en **Configuración → Copias de seguridad** una carpeta externa (OneDrive,
un NAS o un USB): allí se guardará también una copia diaria.

### Privacidad

- Todos tus datos se guardan **solo en tu ordenador**. El programa no
  envía datos a ningún servidor propio ni recoge estadísticas de uso.
- **Lectura de tickets (opcional):** si pones una clave de API de
  Anthropic en Configuración, el ticket o la factura que elijas se envía
  a Anthropic para leerlo. Cada lectura cuesta alrededor de un céntimo y
  la paga el titular de la clave. Sin clave, esta función no se usa y
  nada sale del ordenador.
- **Foto desde el móvil:** el móvil envía la foto directamente al
  ordenador por tu wifi, sin pasar por internet.

### Errores y sugerencias

Nos ayuda mucho que nos cuentes lo que falla o lo que echas en falta.
Si tienes cuenta de GitHub, abre una **incidencia** en la pestaña **Issues**; si
no, escribe a quien te envió la beta. Indica qué estabas haciendo, qué
esperabas y qué ha pasado, y adjunta una captura si puedes. **No envíes
la base de datos ni datos reales de tus clientes.**

### Dónde están los datos

| Qué | Dónde |
| --- | --- |
| Base de datos | `%LOCALAPPDATA%\ControlDeCaja\control_de_caja.db` |
| Copias automáticas | `%LOCALAPPDATA%\ControlDeCaja\copias_seguridad\` |
| Copia externa (opcional) | La carpeta elegida en Configuración |
| Facturas PDF (por defecto) | `Documentos\Control de Caja\Facturas\<año>\` |
| Tickets y facturas de gasto (por defecto) | `Documentos\Control de Caja\Gastos\<año>\` |
| Logo y sello elegidos en Configuración | `%LOCALAPPDATA%\ControlDeCaja\imagenes\` |
| Clave de API de Anthropic | Administrador de credenciales de Windows (`ControlDeCaja`) |

---

## Desarrollo

Aplicación en Python (PySide6 + SQLite). El nombre y la versión están en
`app_info.py`. Los datos de la empresa (razón social, logo, sello de las
facturas, nombre del usuario) se eligen en Configuración: no hay nada
fijo en el código.

### Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

### Tests

```bash
python -m pytest
```

Los tests usan siempre una base de datos temporal: **nunca** tocan los
datos reales. Cubren el motor de tesorería, la facturación, las fichas
de cliente, las migraciones de la base de datos, las copias de seguridad
y una prueba de humo que abre todas las pantallas sin mostrarlas. Se
ejecutan también en GitHub en cada envío (`.github/workflows/tests.yml`).

### Publicar una versión

1. Sube `APP_VERSION` en `app_info.py` y anota los cambios en `CHANGELOG.md`.
2. Genera el ejecutable y el instalador (hace falta
   [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

   ```bash
   python build.py
   ```

   El instalador queda en `dist/ControlDeCaja-<versión>-Setup.exe`.
3. Crea la Release en GitHub con ese archivo:

   ```bash
   gh release create v<versión> "dist/ControlDeCaja-<versión>-Setup.exe" --prerelease --title "Control de Caja <versión> (beta)" --notes-file CHANGELOG.md
   ```

El instalador actualiza la instalación anterior y no toca los datos del
usuario.

> No cambies `APP_NAME` en `database/database.py` ni el `AppId` de
> `installer/ControlDeCaja.iss`: el primero es la carpeta de datos y el
> segundo identifica la instalación para poder actualizarla.

### Lectura de tickets

En el formulario de gasto se puede elegir, arrastrar o escanear un ticket
o una factura (PDF, JPG, PNG, WEBP, GIF, BMP o TIFF) y se rellenan
proveedor, fecha, base, IVA, total, número y categoría. La lectura la hace
Claude (`claude-opus-5-5`) a través de la API de Anthropic, así que
necesita internet y una clave de API (Configuración → Lectura de tickets).
Los datos leídos se revisan siempre antes de guardar. Sin clave, el
documento se adjunta igual y los datos se rellenan a mano.

Con **Desde el móvil…** el formulario enseña un código QR: se abre con la
cámara del móvil, se hace la foto y llega al formulario. El móvil tiene
que estar en la misma wifi que el PC; la aplicación solo escucha en la
red mientras el QR está abierto y con una dirección de clave aleatoria.
La primera vez Windows pregunta en el firewall: hay que permitir el
acceso en **redes privadas**.

Al hacer la foto con el móvil, la página propone el recorte y lo enseña
con cuatro esquinas que se arrastran con el dedo (como CamScanner); al
pulsar **Recortar y enviar** se guarda solo lo que queda dentro. El PC
endereza el recorte, deja el fondo blanco y el texto negro y lo guarda
como PDF. Las fotos del escáner se recortan solas si se ven las cuatro
esquinas del documento. En el formulario, **Usar foto original** guarda
la foto sin procesar.

### Estructura

```
main.py               Punto de entrada
app_info.py           Nombre y versión
build.py              Ejecutable (PyInstaller) e instalador (Inno Setup)
installer/            Script del instalador
database/             Conexión, modelos SQLAlchemy y migraciones
services/cashflow.py  Motor de tesorería (sin Qt): todas las cifras salen de aquí
services/invoices.py  Numeración y PDF de facturas
services/clients.py   Fichas de cliente
services/receipts.py  Lectura de tickets con Claude y archivo de documentos
services/scanner.py   Escaneo con WIA (escáner de Windows)
services/phone_upload.py  Recepción de fotos desde el móvil (QR + wifi)
services/docscan.py   Escaneo de fotos a PDF (recorte, perspectiva, mejora)
services/manual.py    Manual de usuario en PDF (botón «Manual de usuario» del menú)
ui/                   Ventana principal, páginas y diálogos
tests/                Tests con pytest
```

## Licencia

Todos los derechos reservados. La beta se puede usar gratis para
probarla; consulta las condiciones en [LICENSE](LICENSE).
