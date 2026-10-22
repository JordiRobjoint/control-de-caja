"""
Genera el ejecutable y el instalador:

    python build.py

1. PyInstaller -> dist/Control de Caja/
2. Inno Setup  -> dist/ControlDeCaja-<versión>-Setup.exe

La versión sale de app_info.py.
"""

import os
import subprocess
import sys
from pathlib import Path

from app_info import APP_VERSION

ROOT = Path(__file__).resolve().parent

ISCC_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def main():
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "Control de Caja.spec"],
        cwd=ROOT, check=True,
    )

    iscc = next((path for path in ISCC_CANDIDATES if path.exists()), None)
    if iscc is None:
        sys.exit("No se encuentra Inno Setup 6 (ISCC.exe). Instálalo desde jrsoftware.org.")
    subprocess.run(
        [str(iscc), f"/DAppVersion={APP_VERSION}", str(ROOT / "installer" / "ControlDeCaja.iss")],
        cwd=ROOT, check=True,
    )
    print(f"\nInstalador: dist/ControlDeCaja-{APP_VERSION}-Setup.exe")


if __name__ == "__main__":
    main()
