# -*- coding: utf-8 -*-
"""Dwie drogi do Zotero: lokalny konektor (Zotero otwarte na tym komputerze)
oraz Web API (klucz + identyfikator użytkownika).

Konektor jest wygodniejszy — rekordy lądują w bibliotece od razu, bez plików.
Web API działa też zdalnie i pozwala wskazać kolekcję.
"""

from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

import requests

from .cytowania import Rekord, do_zotero, notatka_html

KONEKTOR = "http://127.0.0.1:23119"
API = "https://api.zotero.org"
_NAGLOWKI_KONEKTORA = {
    "Content-Type": "application/json",
    "X-Zotero-Connector-API-Version": "2",
    "User-Agent": "Kwerenda/1.0 (Zotero connector client)",
}


# --------------------------------------------------------------------------
# Lokalny konektor
# --------------------------------------------------------------------------

def konektor_dziala(timeout: float = 2.0) -> Tuple[bool, str]:
    try:
        odp = requests.post(f"{KONEKTOR}/connector/ping", data="{}",
                            headers=_NAGLOWKI_KONEKTORA, timeout=timeout,
                            proxies={"http": None, "https": None})
        if odp.status_code < 400:
            return True, "Zotero działa i przyjmie rekordy."
        return False, f"Zotero odpowiada, ale kodem {odp.status_code}."
    except requests.RequestException:
        return False, ("Nie widzę uruchomionego Zotero na tym komputerze "
                       "(port 23119). Uruchom Zotero albo użyj eksportu do pliku RIS.")


def wyslij_do_konektora(rekordy: Sequence[Rekord], timeout: float = 30.0) -> dict:
    """Wysyła rekordy do otwartego Zotero. Zwraca podsumowanie."""
    dziala, komunikat = konektor_dziala()
    if not dziala:
        return {"ok": False, "wyslane": 0, "komunikat": komunikat}

    wyslane, bledy = 0, []
    for rekord in rekordy:
        element = do_zotero(rekord, z_notatka=True)
        ladunek = {
            "items": [element],
            "uri": rekord.url,
            "sessionID": str(uuid.uuid4()),
        }
        try:
            odp = requests.post(f"{KONEKTOR}/connector/saveItems",
                                data=json.dumps(ladunek, ensure_ascii=False).encode("utf-8"),
                                headers=_NAGLOWKI_KONEKTORA, timeout=timeout,
                                proxies={"http": None, "https": None})
            if odp.status_code < 400:
                wyslane += 1
            else:
                bledy.append(f"{rekord.url}: HTTP {odp.status_code}")
        except requests.RequestException as exc:
            bledy.append(f"{rekord.url}: {exc}")

    return {
        "ok": wyslane > 0,
        "wyslane": wyslane,
        "bledy": bledy,
        "komunikat": f"Wysłano do Zotero: {wyslane} z {len(rekordy)}."
                     + (f" Problemy: {len(bledy)}." if bledy else ""),
    }


# --------------------------------------------------------------------------
# Web API
# --------------------------------------------------------------------------

def _naglowki_api(klucz: str) -> Dict[str, str]:
    return {
        "Zotero-API-Key": klucz,
        "Zotero-API-Version": "3",
        "Content-Type": "application/json",
        "User-Agent": "Kwerenda/1.0",
    }


def kolekcje(klucz: str, uzytkownik: str, timeout: float = 20.0) -> List[dict]:
    odp = requests.get(f"{API}/users/{uzytkownik}/collections",
                       headers=_naglowki_api(klucz), params={"limit": 100}, timeout=timeout)
    odp.raise_for_status()
    return [{"klucz": k.get("key"), "nazwa": (k.get("data") or {}).get("name", "")}
            for k in odp.json()]


def wyslij_przez_api(rekordy: Sequence[Rekord], klucz: str, uzytkownik: str,
                     kolekcja: str = "", z_notatkami: bool = True,
                     timeout: float = 40.0) -> dict:
    """Tworzy rekordy przez Web API, a następnie dopina notatki jako elementy potomne."""
    if not (klucz and uzytkownik):
        return {"ok": False, "wyslane": 0,
                "komunikat": "Podaj klucz API i numer użytkownika Zotero."}

    wyslane, bledy, klucze = 0, [], []
    for poczatek in range(0, len(rekordy), 50):
        partia = list(rekordy[poczatek:poczatek + 50])
        elementy = [do_zotero(r, z_notatka=False,
                              kolekcje=[kolekcja] if kolekcja else None) for r in partia]
        try:
            odp = requests.post(f"{API}/users/{uzytkownik}/items",
                                headers=_naglowki_api(klucz),
                                data=json.dumps(elementy, ensure_ascii=False).encode("utf-8"),
                                timeout=timeout)
        except requests.RequestException as exc:
            bledy.append(str(exc))
            continue
        if odp.status_code >= 400:
            bledy.append(f"HTTP {odp.status_code}: {odp.text[:300]}")
            continue
        wynik = odp.json()
        udane = wynik.get("successful", {}) or {}
        for indeks, element in udane.items():
            wyslane += 1
            klucze.append((int(indeks), element.get("key")))
        for indeks, powod in (wynik.get("failed", {}) or {}).items():
            bledy.append(f"pozycja {indeks}: {powod.get('message', powod)}")

        if z_notatkami and klucze:
            notatki = []
            for indeks, klucz_elementu in klucze:
                rekord = partia[indeks] if indeks < len(partia) else None
                if rekord and (rekord.cytaty or rekord.notatka):
                    notatki.append({"itemType": "note", "parentItem": klucz_elementu,
                                    "note": notatka_html(rekord)})
            if notatki:
                try:
                    requests.post(f"{API}/users/{uzytkownik}/items",
                                  headers=_naglowki_api(klucz),
                                  data=json.dumps(notatki, ensure_ascii=False).encode("utf-8"),
                                  timeout=timeout)
                except requests.RequestException as exc:
                    bledy.append(f"notatki: {exc}")
        klucze = []

    return {"ok": wyslane > 0, "wyslane": wyslane, "bledy": bledy,
            "komunikat": f"Web API Zotero: zapisano {wyslane} z {len(rekordy)}."
                         + (f" Problemy: {len(bledy)}." if bledy else "")}
