"""
Escaneo con el servicio WIA de Windows (Windows Image Acquisition).

Abre el diálogo estándar de Windows para elegir escáner y ajustes y
guarda el resultado como JPEG en una carpeta temporal. Funciona con
cualquier escáner o multifunción que Windows reconozca.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path


WIA_DEVICE_SCANNER = 1
WIA_INTENT_COLOR = 1
WIA_FORMAT_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"

# Códigos HRESULT de WIA que merecen un mensaje propio.
WIA_ERRORS = {
    0x80210015: "No se ha encontrado ningún escáner conectado.",
    0x80210006: "El escáner está ocupado. Espera a que termine y repite.",
    0x80210003: "El escáner no tiene papel.",
    0x80210002: "Hay un atasco de papel en el escáner.",
    0x80210005: "El escáner está apagado o desconectado.",
}


class ScannerError(Exception):
    pass


def scan_to_file() -> Path | None:
    """
    Escanea una página y devuelve la ruta del JPEG, o None si el usuario
    cancela. Debe llamarse desde el hilo de la interfaz.
    """
    try:
        import pythoncom
        import win32com.client
        from pywintypes import com_error
    except ImportError:
        raise ScannerError("El escaneo solo está disponible en Windows.")

    pythoncom.CoInitialize()
    try:
        dialog = win32com.client.Dispatch("WIA.CommonDialog")
        image = dialog.ShowAcquireImage(
            WIA_DEVICE_SCANNER,
            WIA_INTENT_COLOR,
            0,                  # Bias: equilibrio calidad/tamaño
            WIA_FORMAT_JPEG,
            False,              # No pedir dispositivo si solo hay uno
            True,               # Mostrar el diálogo de ajustes
            False,              # Cancelar devuelve None, no error
        )
    except com_error as error:
        code = (error.excepinfo[5] if error.excepinfo else error.hresult) & 0xFFFFFFFF
        raise ScannerError(WIA_ERRORS.get(code, f"Error del escáner (0x{code:08X})."))

    if image is None:
        return None

    folder = Path(tempfile.gettempdir()) / "ControlDeCaja" / "escaneos"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"escaneo {datetime.now():%Y-%m-%d %H%M%S}.jpg"
    image.SaveFile(str(path))
    return path
