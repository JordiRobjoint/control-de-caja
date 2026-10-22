"""
Recibir la foto de un ticket desde el móvil por la wifi de la oficina.

La aplicación abre un pequeño servidor web en la red local solo mientras
el diálogo del QR está abierto. El QR lleva una dirección con una clave
aleatoria: sin ella el servidor no responde.

1. El móvil hace la foto, la reduce a JPEG en el propio navegador (así
   también se convierten las fotos HEIC del iPhone) y la envía.
2. El PC propone un recorte (services.docscan) y el móvil lo enseña con
   cuatro esquinas que se pueden arrastrar, como en CamScanner.
3. Al confirmar, el móvil manda las esquinas y el PC recibe la foto con
   el recorte: `on_file(path, corners)`.

Un PDF se recibe directamente, sin recorte: `on_file(path, None)`.

Sin Qt: `on_file` se llama desde el hilo del servidor.
"""

from __future__ import annotations

import json
import secrets
import socket
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

MAX_UPLOAD_BYTES = 30_000_000

# Extensión según el tipo que manda el navegador.
CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def local_ip() -> str:
    """IP del PC en la red local (no envía nada: UDP no conecta)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.168.255.255", 1))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def upload_folder() -> Path:
    folder = Path(tempfile.gettempdir()) / "ControlDeCaja" / "movil"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class PhoneUploadServer:
    """
    Servidor de un solo uso: `start()`, enseñar `url` en un QR y
    `stop()` al cerrar. Cada documento recibido se guarda en una carpeta
    temporal y se pasa a `on_file(path, corners)`.
    """

    def __init__(self, on_file: Callable[[Path, list | None], None], *,
                 host: str | None = None, port: int = 0):
        self.on_file = on_file
        self.token = secrets.token_urlsafe(16)
        self.host = host or local_ip()
        self._bind = (host or "0.0.0.0", port)
        self._server = None
        self._thread = None
        # Fotos esperando a que se confirme el recorte: id -> ruta.
        self._photos: dict[str, Path] = {}
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://{self.host}:{port}/{self.token}"

    def start(self):
        handler = type("Handler", (_Handler,), {"owner": self})
        self._server = ThreadingHTTPServer(self._bind, handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _save(self, data: bytes, content_type: str) -> Path:
        suffix = CONTENT_TYPES[content_type]
        path = upload_folder() / f"movil {datetime.now():%Y-%m-%d %H%M%S%f}{suffix}"
        path.write_bytes(data)
        return path

    def _hold_photo(self, path: Path) -> str:
        photo_id = secrets.token_hex(8)
        with self._lock:
            self._photos[photo_id] = path
        return photo_id

    def _release_photo(self, photo_id: str) -> Path | None:
        with self._lock:
            return self._photos.pop(photo_id, None)


class _Handler(BaseHTTPRequestHandler):
    owner: PhoneUploadServer

    def log_message(self, format, *args):
        pass  # sin consola en el ejecutable

    def _send(self, status: int, body: str, content_type="text/plain; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict):
        self._send(200, json.dumps(payload), "application/json")

    def _token_ok(self, suffix="") -> bool:
        return secrets.compare_digest(self.path, f"/{self.owner.token}{suffix}")

    def _body(self, limit=MAX_UPLOAD_BYTES) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._send(400, "No ha llegado ningún archivo.")
            return None
        if length > limit:
            self._send(413, "El archivo supera los 30 MB.")
            return None
        return self.rfile.read(length)

    def do_GET(self):
        if not self._token_ok():
            self._send(404, "No encontrado")
            return
        self._send(200, PAGE, "text/html; charset=utf-8")

    def do_POST(self):
        if self._token_ok("/subir"):
            self._upload()
        elif self._token_ok("/recortar"):
            self._crop()
        else:
            self._send(404, "No encontrado")

    def _upload(self):
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type not in CONTENT_TYPES:
            self._send(415, "Formato no admitido. Envía una foto o un PDF.")
            return
        data = self._body()
        if data is None:
            return
        path = self.owner._save(data, content_type)

        if content_type == "application/pdf":
            self._json({"done": True})
            self.owner.on_file(path, None)
            return

        from services import docscan
        try:
            corners, how = docscan.suggest_fractions(path)
        except Exception:
            self._send(400, "No se ha podido abrir la foto. Prueba a repetirla.")
            return
        self._json({"id": self.owner._hold_photo(path), "corners": corners, "how": how})

    def _crop(self):
        data = self._body(limit=10_000)
        if data is None:
            return
        try:
            payload = json.loads(data)
            photo_id = str(payload["id"])
            corners = payload["corners"]
        except (ValueError, KeyError, TypeError):
            self._send(400, "Petición no válida.")
            return

        from services import docscan
        if not docscan.valid_fractions(corners):
            self._send(400, "El recorte no es válido. Ajusta las esquinas.")
            return
        path = self.owner._release_photo(photo_id)
        if path is None:
            self._send(400, "La foto ya no está disponible. Hazla de nuevo.")
            return
        self._json({"done": True})
        self.owner.on_file(path, [[float(x), float(y)] for x, y in corners])


PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Control de Caja · Ticket</title>
<style>
  body { margin: 0; font-family: -apple-system, system-ui, sans-serif;
         background: #f4f6f9; color: #1f2937; }
  main { max-width: 480px; margin: 0 auto; padding: 24px 16px; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  p { color: #6b7280; margin: 0 0 20px; line-height: 1.4; }
  label, button { display: block; width: 100%; box-sizing: border-box; text-align: center;
          padding: 16px; margin-bottom: 10px; border-radius: 12px; font-size: 17px;
          font-weight: 600; cursor: pointer; font-family: inherit; }
  .primary { background: #1d4ed8; color: white; border: 0; }
  .secondary { background: white; color: #1d4ed8; border: 1px solid #c7d2fe; }
  input { display: none; }
  #editor { touch-action: none; display: block; margin: 0 auto 14px;
            border-radius: 8px; background: #111; }
  .row { display: flex; gap: 10px; }
  .row > * { flex: 1; }
  #status { text-align: center; font-size: 17px; margin-top: 16px; min-height: 40px; }
  .ok { color: #047857; font-weight: 600; }
  .error { color: #b91c1c; }
</style>
</head>
<body>
<main>
  <section id="start">
    <h1>Enviar ticket</h1>
    <p>Haz una foto del ticket o factura con buena luz. Después podrás
       ajustar el recorte para que quede solo el documento.</p>
    <label class="primary">Hacer foto
      <input id="camera" type="file" accept="image/*" capture="environment"></label>
    <label class="secondary">Elegir foto o PDF
      <input id="file" type="file" accept="image/*,application/pdf"></label>
  </section>

  <section id="crop" hidden>
    <h1>Ajusta el recorte</h1>
    <p id="crop-help">Arrastra las esquinas azules hasta los bordes del
       documento. Se guardará solo lo que quede dentro.</p>
    <canvas id="editor"></canvas>
    <button id="send" class="primary">Recortar y enviar</button>
    <div class="row">
      <button id="whole" class="secondary">Foto entera</button>
      <button id="retry" class="secondary">Repetir foto</button>
    </div>
  </section>

  <div id="status"></div>
</main>
<script>
const MAX_SIDE = 2400;
const HANDLE = 14;
// Margen alrededor de la foto para que las esquinas que caen en el borde
// se vean enteras y se puedan coger con el dedo.
const PAD = HANDLE + 8;
const $ = id => document.getElementById(id);
const statusBox = $("status");
const canvas = $("editor");
const ctx = canvas.getContext("2d");

let photo = null;     // { id, img }
let corners = [];     // fracciones 0..1: [[x, y] x4]
let dragging = -1;
let imgW = 0, imgH = 0;   // tamaño de la foto dibujada (px de pantalla)

function show(text, kind) {
  statusBox.textContent = text;
  statusBox.className = kind || "";
}

function screen(name) {
  $("start").hidden = name !== "start";
  $("crop").hidden = name !== "crop";
}

// Las fotos se reducen y pasan a JPEG en el móvil: sube más rápido y
// así también llegan bien las fotos HEIC del iPhone.
function toJpeg(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const s = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement("canvas");
      c.width = Math.round(img.naturalWidth * s);
      c.height = Math.round(img.naturalHeight * s);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob(blob => blob ? resolve(blob) : reject(new Error("imagen")), "image/jpeg", 0.88);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("imagen")); };
    img.src = url;
  });
}

function loadImage(blob) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("imagen"));
    img.src = URL.createObjectURL(blob);
  });
}

async function post(path, body, type) {
  const response = await fetch(location.pathname + path, {
    method: "POST", headers: { "Content-Type": type }, body,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function done() {
  screen("none");
  show("✓ Recibido. Ya puedes cerrar esta página y revisar el gasto en el ordenador.", "ok");
}

async function send(file) {
  if (!file) return;
  screen("none");
  show("Enviando…");
  try {
    if (file.type === "application/pdf") {
      await post("/subir", file, "application/pdf");
      done();
      return;
    }
    const jpeg = await toJpeg(file);
    const answer = await post("/subir", jpeg, "image/jpeg");
    photo = { id: answer.id, img: await loadImage(jpeg) };
    corners = answer.corners;
    $("crop-help").textContent = answer.how === "documento"
      ? "Revisa el recorte. Si hace falta, arrastra las esquinas azules."
      : "Arrastra las esquinas azules hasta los bordes del documento. " +
        "Se guardará solo lo que quede dentro.";
    show("");
    screen("crop");
    layout();
  } catch (error) {
    screen("start");
    show("No se ha podido enviar: " + (error.message === "imagen"
      ? "el móvil no ha podido abrir la foto." : error.message), "error");
  }
}

// ---------------- Editor de recorte ----------------

function layout() {
  const img = photo.img;
  // Ancho útil real (sin los márgenes de la página).
  const maxW = $("crop").clientWidth - 2 * PAD;
  const maxH = window.innerHeight * 0.62 - 2 * PAD;
  const scale = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight);
  const ratio = window.devicePixelRatio || 1;
  imgW = Math.round(img.naturalWidth * scale);
  imgH = Math.round(img.naturalHeight * scale);
  const w = imgW + 2 * PAD;
  const h = imgH + 2 * PAD;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  canvas.width = Math.round(w * ratio);
  canvas.height = Math.round(h * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}

function px(i) {
  return [PAD + corners[i][0] * imgW, PAD + corners[i][1] * imgH];
}

function draw() {
  const w = imgW + 2 * PAD, h = imgH + 2 * PAD;
  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(photo.img, PAD, PAD, imgW, imgH);

  // Oscurece lo que queda fuera del recorte.
  ctx.beginPath();
  ctx.rect(PAD, PAD, imgW, imgH);
  ctx.moveTo(...px(0));
  for (let i = 3; i >= 1; i--) ctx.lineTo(...px(i));
  ctx.closePath();
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fill("evenodd");

  ctx.beginPath();
  ctx.moveTo(...px(0));
  for (let i = 1; i < 4; i++) ctx.lineTo(...px(i));
  ctx.closePath();
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = "#3b82f6";
  ctx.stroke();

  for (let i = 0; i < 4; i++) {
    ctx.beginPath();
    ctx.arc(...px(i), dragging === i ? HANDLE + 4 : HANDLE, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(59, 130, 246, 0.35)";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();
  }
}

function pointer(event) {
  const rect = canvas.getBoundingClientRect();
  return [event.clientX - rect.left, event.clientY - rect.top];
}

canvas.addEventListener("pointerdown", event => {
  const [x, y] = pointer(event);
  let best = -1, bestDistance = 48;   // radio de toque generoso
  for (let i = 0; i < 4; i++) {
    const [cx, cy] = px(i);
    const d = Math.hypot(cx - x, cy - y);
    if (d < bestDistance) { best = i; bestDistance = d; }
  }
  if (best >= 0) {
    dragging = best;
    canvas.setPointerCapture(event.pointerId);
    draw();
  }
});

canvas.addEventListener("pointermove", event => {
  if (dragging < 0) return;
  const [x, y] = pointer(event);
  corners[dragging] = [
    Math.min(1, Math.max(0, (x - PAD) / imgW)),
    Math.min(1, Math.max(0, (y - PAD) / imgH)),
  ];
  draw();
});

for (const name of ["pointerup", "pointercancel"]) {
  canvas.addEventListener(name, () => { dragging = -1; draw(); });
}

window.addEventListener("resize", () => { if (photo && !$("crop").hidden) layout(); });

$("whole").addEventListener("click", () => {
  corners = [[0, 0], [1, 0], [1, 1], [0, 1]];
  draw();
});

$("retry").addEventListener("click", () => {
  photo = null;
  screen("start");
  show("");
});

$("send").addEventListener("click", async () => {
  screen("none");
  show("Enviando…");
  try {
    await post("/recortar", JSON.stringify({ id: photo.id, corners }), "application/json");
    done();
  } catch (error) {
    screen("crop");
    show("No se ha podido enviar: " + error.message, "error");
  }
});

for (const id of ["camera", "file"]) {
  $(id).addEventListener("change", e => { send(e.target.files[0]); e.target.value = ""; });
}
</script>
</body>
</html>
"""
