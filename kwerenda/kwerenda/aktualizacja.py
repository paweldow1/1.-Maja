# -*- coding: utf-8 -*-
"""Updating the program in place, without another round of download-and-unpack.

Your work lives outside the program folder (see :mod:`kwerenda.dane`), so a new
version only has to overwrite code. That is what this does: fetch the current
archive, check it really is Kwerenda, copy it over the folder we are running
from, and reinstall the dependencies into the existing environment.

Nothing here touches ``.venv``, ``.git``, the corpus or anything of yours that
happens to be sitting in the folder.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import __wersja__
from .dane import katalog_programu

#: The branch this copy was built from.
ZRODLO = ("https://codeload.github.com/paweldow1/1.-Maja/zip/refs/heads/"
          "claude/web-scraper-zotero-export-77tlgl")

#: Files that prove an archive is actually this program.
ZNACZNIKI = ("requirements.txt", "kwerenda/__init__.py", "kwerenda/silnik.py")

#: Never overwritten or removed: your environment, your history, your work.
POMIJANE = {".venv", ".git", "__pycache__", "exports", "eksport", ".DS_Store"}
POMIJANE_WZORCE = (re.compile(r"\.sqlite3(-wal|-shm)?$"), re.compile(r"\.pyc$"))


def _pomijany(sciezka: str) -> bool:
    czesci = Path(sciezka).parts
    if any(czesc in POMIJANE for czesc in czesci):
        return True
    return any(wzorzec.search(sciezka) for wzorzec in POMIJANE_WZORCE)


def _pobierz(url: str, log: Callable[[str], None]) -> bytes:
    import requests
    log(f"Fetching {url}")
    odp = requests.get(url, timeout=120, headers={"User-Agent": f"Kwerenda/{__wersja__}"})
    odp.raise_for_status()
    log(f"  {len(odp.content) / 1024:.0f} kB")
    return odp.content


def _korzen_programu(archiwum: zipfile.ZipFile) -> Optional[str]:
    """Find the folder inside the archive that holds the program itself."""
    nazwy = archiwum.namelist()
    for nazwa in nazwy:
        if not nazwa.endswith("kwerenda/__init__.py"):
            continue
        # .../<program>/kwerenda/__init__.py  →  .../<program>/
        korzen = nazwa[: -len("kwerenda/__init__.py")]
        if all(any(n == korzen + znacznik for n in nazwy) for znacznik in ZNACZNIKI):
            return korzen
    return None


def _wersja_w_archiwum(archiwum: zipfile.ZipFile, korzen: str) -> str:
    try:
        tresc = archiwum.read(korzen + "kwerenda/__init__.py").decode("utf-8", "replace")
    except KeyError:
        return "?"
    dopasowanie = re.search(r'__wersja__\s*=\s*["\']([^"\']+)', tresc)
    return dopasowanie.group(1) if dopasowanie else "?"


def aktualizuj(url: str = "", katalog: Optional[Path] = None,
               log: Callable[[str], None] = print,
               instaluj_zaleznosci: bool = True) -> Tuple[bool, List[str]]:
    """Replace the program files in place. Returns (changed anything, messages)."""
    katalog = Path(katalog or katalog_programu())
    komunikaty: List[str] = []

    # Rescue anything of the user's still sitting in the program folder before a
    # single file is overwritten.
    from .dane import przenies_stare_dane, zapisz_wskaznik_programu
    komunikaty.extend(przenies_stare_dane(log=lambda *_: None, program=katalog))
    zapisz_wskaznik_programu(katalog)

    try:
        dane = _pobierz(url or ZRODLO, log)
    except Exception as exc:
        return False, [f"Could not download the update: {exc}"]

    try:
        archiwum = zipfile.ZipFile(io.BytesIO(dane))
    except zipfile.BadZipFile:
        return False, ["What came back is not a zip archive — try again later."]

    korzen = _korzen_programu(archiwum)
    if korzen is None:
        return False, ["That archive does not look like Kwerenda — nothing was changed."]

    nowa = _wersja_w_archiwum(archiwum, korzen)
    if nowa == __wersja__:
        log(f"Version {nowa} both sides — refreshing the files anyway")
    else:
        log(f"Version {__wersja__} → {nowa}")

    zapisane, dodane = 0, 0
    for wpis in archiwum.infolist():
        if wpis.is_dir() or not wpis.filename.startswith(korzen):
            continue
        wzgledna = wpis.filename[len(korzen):]
        if not wzgledna or _pomijany(wzgledna):
            continue
        cel = (katalog / wzgledna).resolve()
        # Never let an archive write outside the folder it is updating.
        if not str(cel).startswith(str(katalog.resolve())):
            komunikaty.append(f"Refused a suspicious path in the archive: {wzgledna}")
            continue
        nowy_plik = not cel.exists()
        cel.parent.mkdir(parents=True, exist_ok=True)
        with archiwum.open(wpis) as zrodlo, open(cel, "wb") as wyjscie:
            shutil.copyfileobj(zrodlo, wyjscie)
        if wzgledna.endswith((".sh", ".command", ".py")):
            cel.chmod(0o755 if wzgledna.endswith((".sh", ".command")) else 0o644)
        zapisane += 1
        dodane += 1 if nowy_plik else 0

    komunikaty.append(f"Updated {zapisane} files ({dodane} new) in {katalog}")

    if instaluj_zaleznosci:
        komunikaty.extend(_doinstaluj(katalog, log))
    return True, komunikaty


def _doinstaluj(katalog: Path, log: Callable[[str], None]) -> List[str]:
    """Bring the environment up to date with the new requirements.txt."""
    wymagania = katalog / "requirements.txt"
    if not wymagania.is_file():
        return []
    kandydaci = [katalog / ".venv/bin/python", katalog / ".venv/Scripts/python.exe"]
    python = next((k for k in kandydaci if k.exists()), Path(sys.executable))
    log(f"Installing dependencies with {python}")
    try:
        wynik = subprocess.run([str(python), "-m", "pip", "install", "--quiet",
                                "-r", str(wymagania)], capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"Could not install dependencies ({exc}) — run: "
                f'"{python}" -m pip install -r "{wymagania}"']
    if wynik.returncode != 0:
        blad = (wynik.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return ["Installing dependencies failed:"] + [f"  {l}" for l in blad[-4:]] + \
               [f'Run it by hand: "{python}" -m pip install -r "{wymagania}"']
    return ["Dependencies are up to date"]
