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
from typing import Callable, List

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

def przenies_stare_dane(log: Callable[[str], None] = print) -> List[str]:
    """Move work left inside the program folder by earlier versions.

    Version 2.0 and before kept the database and saved presets next to the code,
    where replacing the folder on update would have destroyed them. Anything
    found there is moved out once, and said out loud.
    """
    komunikaty: List[str] = []
    program, dane = katalog_programu(), katalog_danych()
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

