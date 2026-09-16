#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Put a Kwerenda icon on the desktop.

    python install_desktop_icon.py

Prepares a private virtual environment (so nothing is installed system-wide),
draws the icon, and creates the shortcut in the way each system expects:

* Linux   — ``~/Desktop/Kwerenda.desktop`` plus an entry in the applications menu
* macOS   — a small ``Kwerenda.app`` bundle on the Desktop
* Windows — ``Kwerenda.lnk`` on the Desktop, pointing at pythonw (no console window)

Run it again after moving the folder; it simply overwrites the shortcut.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

KATALOG = Path(__file__).resolve().parent
NAZWA = "Kwerenda"
OPIS = "Search websites, export citations to Zotero"


def pulpit() -> Path:
    """The desktop directory, honouring XDG on Linux and localisation elsewhere."""
    dom = Path.home()
    konfig = dom / ".config" / "user-dirs.dirs"
    if konfig.is_file():
        for linia in konfig.read_text(encoding="utf-8", errors="ignore").splitlines():
            if linia.startswith("XDG_DESKTOP_DIR"):
                wartosc = linia.split("=", 1)[1].strip().strip('"')
                sciezka = Path(os.path.expandvars(wartosc.replace("$HOME", str(dom))))
                if sciezka.is_dir():
                    return sciezka
    for nazwa in ("Desktop", "Pulpit", "Schreibtisch", "Bureau", "Escritorio",
                  "Рабочий стол", "Робочий стіл"):
        if (dom / nazwa).is_dir():
            return dom / nazwa
    return dom


def przygotuj_srodowisko(uzyj_venv: bool = True) -> Path:
    """Return the Python that the shortcut should run."""
    if not uzyj_venv:
        return Path(sys.executable)

    venv = KATALOG / ".venv"
    windows = platform.system() == "Windows"
    python = venv / ("Scripts/python.exe" if windows else "bin/python")
    if not python.exists():
        print("Preparing a private environment (this happens once)…")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    print("Installing dependencies…")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                   check=False)
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "-r",
                    str(KATALOG / "requirements.txt")], check=True)
    if windows:
        bez_konsoli = venv / "Scripts/pythonw.exe"
        if bez_konsoli.exists():
            return bez_konsoli
    return python


def zbuduj_ikone() -> Path:
    sys.path.insert(0, str(KATALOG))
    from zasoby.ikona import zbuduj                     # noqa: E402
    wynik = zbuduj(KATALOG / "zasoby")
    return wynik["ico" if platform.system() == "Windows" else "png"]


# --------------------------------------------------------------------------
def skrot_linux(python: Path, ikona: Path) -> Path:
    tresc = f"""[Desktop Entry]
Type=Application
Version=1.0
Name={NAZWA}
Comment={OPIS}
Exec={python} -m kwerenda gui
Path={KATALOG}
Icon={ikona}
Terminal=false
Categories=Education;Science;Utility;
Keywords=research;zotero;scraping;bibliography;
"""
    cele = [pulpit() / f"{NAZWA}.desktop",
            Path.home() / ".local/share/applications" / f"{NAZWA.lower()}.desktop"]
    for cel in cele:
        cel.parent.mkdir(parents=True, exist_ok=True)
        cel.write_text(tresc, encoding="utf-8")
        cel.chmod(0o755)
    # GNOME wants shortcuts to be explicitly trusted before it will run them
    subprocess.run(["gio", "set", str(cele[0]), "metadata::trusted", "true"],
                   check=False, capture_output=True)
    return cele[0]


def skrot_macos(python: Path, ikona: Path) -> Path:
    aplikacja = pulpit() / f"{NAZWA}.app"
    (aplikacja / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
    (aplikacja / "Contents/Resources").mkdir(parents=True, exist_ok=True)

    (aplikacja / "Contents/Info.plist").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>{NAZWA}</string>
  <key>CFBundleDisplayName</key><string>{NAZWA}</string>
  <key>CFBundleExecutable</key><string>{NAZWA}</string>
  <key>CFBundleIdentifier</key><string>pl.kwerenda.app</string>
  <key>CFBundleIconFile</key><string>kwerenda</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
</dict></plist>
""", encoding="utf-8")

    uruchamiacz = aplikacja / "Contents/MacOS" / NAZWA
    uruchamiacz.write_text(_skrypt_macos(python), encoding="utf-8")
    uruchamiacz.chmod(0o755)
    _icns(ikona, aplikacja / "Contents/Resources/kwerenda.icns")
    return aplikacja


#: Launcher for the macOS bundle. Double-clicking an app that dies leaves macOS
#: saying only "the application is not open anymore", with the reason gone — so
#: this keeps a log and puts the failure on screen.
_SZABLON_MACOS = r"""#!/bin/bash
PROGRAM="@PROGRAM@"
PYTHON="@PYTHON@"
LOG="${KWERENDA_HOME:-$HOME/Kwerenda}/launch.log"
mkdir -p "$(dirname "$LOG")" 2>/dev/null

powiedz() {
  printf '%s\n' "$1" >> "$LOG"
  ODPOWIEDZ=$(osascript -e "display dialog \"$1\" buttons {\"Open the log\", \"OK\"} default button \"Open the log\" with title \"Kwerenda\" with icon caution" 2>/dev/null)
  case "$ODPOWIEDZ" in *"Open the log"*) open "$LOG" ;; esac
  exit 1
}

printf '\n--- %s ---\n' "$(date)" >> "$LOG"

if [ ! -d "$PROGRAM" ]; then
  powiedz "The Kwerenda folder is no longer where it was installed from: $PROGRAM. Move it back, or run install_desktop_icon.py again in its new place."
fi
if [ ! -x "$PYTHON" ]; then
  powiedz "Kwerenda's Python environment is missing: $PYTHON. Run install_desktop_icon.py again in $PROGRAM."
fi

cd "$PROGRAM" || powiedz "Cannot enter $PROGRAM."
"$PYTHON" -m kwerenda gui >> "$LOG" 2>&1
KOD=$?
if [ "$KOD" -ne 0 ]; then
  powiedz "Kwerenda stopped with error $KOD. The last lines of the log say what happened."
fi
"""


def _skrypt_macos(python: Path) -> str:
    return (_SZABLON_MACOS.replace("@PROGRAM@", str(KATALOG))
                          .replace("@PYTHON@", str(python)))


def _icns(png: Path, cel: Path) -> None:
    """Build an .icns with the tools macOS ships; skip quietly if unavailable."""
    zestaw = cel.parent / "kwerenda.iconset"
    try:
        zestaw.mkdir(parents=True, exist_ok=True)
        for rozmiar in (16, 32, 64, 128, 256, 512):
            subprocess.run(["sips", "-z", str(rozmiar), str(rozmiar), str(png),
                            "--out", str(zestaw / f"icon_{rozmiar}x{rozmiar}.png")],
                           check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(zestaw), "-o", str(cel)],
                       check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        print("  (no custom icon — sips/iconutil not available)")
    finally:
        for plik in zestaw.glob("*.png"):
            plik.unlink(missing_ok=True)
        if zestaw.is_dir():
            zestaw.rmdir()


def skrot_windows(python: Path, ikona: Path) -> Path:
    cel = pulpit() / f"{NAZWA}.lnk"
    polecenie = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{cel}');"
        f"$s.TargetPath = '{python}';"
        f"$s.Arguments = '-m kwerenda gui';"
        f"$s.WorkingDirectory = '{KATALOG}';"
        f"$s.IconLocation = '{ikona}';"
        f"$s.Description = '{OPIS}';"
        f"$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", polecenie],
                   check=True)
    return cel


# --------------------------------------------------------------------------
def main() -> int:
    uzyj_venv = "--no-venv" not in sys.argv
    python = przygotuj_srodowisko(uzyj_venv)
    ikona = zbuduj_ikone()

    system = platform.system()
    if system == "Linux":
        skrot = skrot_linux(python, ikona)
    elif system == "Darwin":
        skrot = skrot_macos(python, ikona)
    elif system == "Windows":
        skrot = skrot_windows(python, ikona)
    else:
        print(f"Unknown system ({system}). Start it by hand: "
              f"{python} -m kwerenda gui", file=sys.stderr)
        return 1

    print(f"\nDone. Double-click {skrot}")
    print("It opens the interface at http://127.0.0.1:8765 in your browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
