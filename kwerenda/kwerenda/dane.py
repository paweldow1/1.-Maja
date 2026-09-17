# -*- coding: utf-8 -*-
"""Where your work lives, as opposed to where the program lives.

The corpus, your saved searches and everything exported are yours and outlive
any version of Kwerenda. They are kept in a plain, findable folder — ``~/Kwerenda``
— so that updating means replacing the program folder and nothing else.

Set ``KWERENDA_HOME`` to put that folder somewhere else (a synced drive, the
dissertation directory, an external disk).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, List, Optional

NAZWA_BAZY = "kwerenda.sqlite3"

#: Preset files shipped with the program. Anything else found in its presets
#: folder was put there by the user and is theirs to keep.
PRZYKLADY = frozenset({
    "may-day-solidarnosc.yaml",
    "may-day-three-countries.yaml",
    "newspaper-archive.yaml",
    "offline-corpus.yaml",
    "pdf-newsletters.yaml",
})


def katalog_danych() -> Path:
    """The user's data folder, created on first use."""
    wskazany = os.environ.get("KWERENDA_HOME", "").strip()
    katalog = Path(wskazany).expanduser() if wskazany else Path.home() / "Kwerenda"
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def katalog_programu() -> Path:
    """The folder holding the code — read-only as far as your work is concerned."""
    return Path(__file__).resolve().parent.parent


def katalog_przykladow() -> Path:
    """Presets shipped with the program. They travel with updates."""
    return katalog_programu() / "presets"


def sciezka_bazy() -> Path:
    return katalog_danych() / NAZWA_BAZY


def katalog_eksportu() -> Path:
    return katalog_danych() / "exports"


def katalog_presetow() -> Path:
    return katalog_danych() / "presets"


# --------------------------------------------------------------------------

NAZWA_WSKAZNIKA = "WHERE-IS-THE-PROGRAM.txt"


def zapisz_wskaznik_programu(program: Optional[Path] = None) -> None:
    """Leave a note in the data folder pointing back at the program folder.

    ``~/Kwerenda`` (the data folder) and the folder holding the code look alike
    enough that opening a terminal "in Kwerenda" easily lands in the wrong one —
    and every CLI command then fails with a bare "No module named kwerenda",
    which explains nothing. This file is refreshed on every run, so whichever
    folder somebody is confused inside, the answer is one `cat` away.
    """
    program = Path(program) if program else katalog_programu()
    dane = katalog_danych()
    if program.resolve() == dane.resolve():
        return                                   # nothing to point at from itself

    python = program / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        import sys
        python = Path(sys.executable)

    tresc = (
        "This folder holds your data — the corpus, your presets, your exports.\n"
        "It is NOT the program. If a command like `python -m kwerenda ...` said\n"
        '"No module named kwerenda", you are probably standing here instead of\n'
        "in the program folder.\n\n"
        f"The program lives here:\n  {program}\n\n"
        "Run commands like this instead (works from anywhere):\n"
        f'  cd "{program}" && "{python}" -m kwerenda doctor\n'
        f'  cd "{program}" && "{python}" -m kwerenda update\n'
        f'  cd "{program}" && "{python}" -m kwerenda gui\n'
    )
    try:
        (dane / NAZWA_WSKAZNIKA).write_text(tresc, encoding="utf-8")
    except OSError:
        pass                                      # never let this get in the way


def przenies_stare_dane(log: Callable[[str], None] = print,
                        program: Path | None = None) -> List[str]:
    """Move work left inside the program folder by earlier versions.

    Version 2.0 and before kept the database and saved presets next to the code,
    where replacing the folder on update would have destroyed them. Anything
    found there is moved out once, and said out loud.
    """
    komunikaty: List[str] = []
    # During an update the folder being rescued is the one being replaced, which
    # is not necessarily the one this code is running from.
    program = Path(program) if program else katalog_programu()
    dane = katalog_danych()
    if program.resolve() == dane.resolve():
        return komunikaty

    stara_baza = program / NAZWA_BAZY
    if stara_baza.is_file() and not sciezka_bazy().exists():
        try:
            shutil.move(str(stara_baza), str(sciezka_bazy()))
            for przyrostek in ("-wal", "-shm"):
                towarzysz = program / (NAZWA_BAZY + przyrostek)
                if towarzysz.is_file():
                    shutil.move(str(towarzysz), str(sciezka_bazy()) + przyrostek)
            komunikaty.append(f"Moved your corpus to {sciezka_bazy()}")
        except OSError as exc:
            komunikaty.append(f"Could not move the old corpus ({exc}) — still using it in place")

    stare_presety = program / "presets"
    if stare_presety.is_dir():
        docelowy = katalog_presetow()
        docelowy.mkdir(parents=True, exist_ok=True)
        przeniesione = 0
        for plik in sorted(stare_presety.glob("*.yaml")) + sorted(stare_presety.glob("*.yml")) \
                + sorted(stare_presety.glob("*.json")):
            cel = docelowy / plik.name
            if cel.exists():
                continue
            # The examples shipped with the program stay with the program; only
            # work that is actually the user's is moved out. Comparing contents
            # is no use here — this *is* the shipped folder, so every file would
            # match itself — so the shipped names are the criterion.
            if plik.name in PRZYKLADY:
                continue
            try:
                shutil.copy2(str(plik), str(cel))
                przeniesione += 1
            except OSError:
                continue
        if przeniesione:
            komunikaty.append(f"Copied {przeniesione} of your presets to {docelowy}")

    for komunikat in komunikaty:
        log(komunikat)
    return komunikaty

