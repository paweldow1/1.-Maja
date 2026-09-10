# -*- coding: utf-8 -*-
"""Magazyn SQLite: korpus pobranych stron, przebiegi kwerend, trafienia, ustawienia.

Korpus jest celowo trwały: raz pobrane strony można potem przeszukiwać
w kółko nowymi zapytaniami, bez ruszania cudzych serwerów.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS strony (
    url         TEXT PRIMARY KEY,
    host        TEXT,
    status      INTEGER,
    url_koncowy TEXT,
    html        TEXT,
    tekst       TEXT,
    meta_json   TEXT,
    pobrano     REAL
);
CREATE INDEX IF NOT EXISTS idx_strony_host ON strony(host);

CREATE TABLE IF NOT EXISTS przebiegi (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nazwa         TEXT,
    zapytanie     TEXT,
    konfig_json   TEXT,
    status        TEXT,
    start         REAL,
    koniec        REAL,
    statystyki    TEXT,
    dziennik      TEXT
);

CREATE TABLE IF NOT EXISTS trafienia (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    przebieg_id  INTEGER,
    url          TEXT,
    host         TEXT,
    tytul        TEXT,
    autorzy      TEXT,
    data         TEXT,
    serwis       TEXT,
    wydawca      TEXT,
    jezyk        TEXT,
    typ          TEXT,
    citekey      TEXT,
    terminy      TEXT,
    tagi         TEXT,
    cytaty       TEXT,
    meta_json    TEXT,
    notatka      TEXT DEFAULT '',
    wybrane      INTEGER DEFAULT 1,
    dodano       REAL,
    UNIQUE(przebieg_id, url)
);
CREATE INDEX IF NOT EXISTS idx_trafienia_przebieg ON trafienia(przebieg_id);

CREATE TABLE IF NOT EXISTS ustawienia (
    klucz    TEXT PRIMARY KEY,
    wartosc  TEXT
);

CREATE TABLE IF NOT EXISTS presety (
    nazwa       TEXT PRIMARY KEY,
    konfig_json TEXT,
    zmieniono   REAL
);
"""


def _teraz() -> float:
    return time.time()


class Magazyn:
    def __init__(self, sciezka: str | Path = "kwerenda.sqlite3"):
        self.sciezka = str(sciezka)
        self._lock = threading.RLock()
        self._polaczenie = sqlite3.connect(self.sciezka, check_same_thread=False)
        self._polaczenie.row_factory = sqlite3.Row
        with self._lock:
            self._polaczenie.executescript(SCHEMA)
            try:
                self._polaczenie.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            self._polaczenie.commit()

    # ------------------------------------------------------------------
    def wykonaj(self, sql: str, parametry: Iterable = ()) -> sqlite3.Cursor:
        with self._lock:
            kursor = self._polaczenie.execute(sql, tuple(parametry))
            self._polaczenie.commit()
            return kursor

    def pobierz_wiersze(self, sql: str, parametry: Iterable = ()) -> List[sqlite3.Row]:
        with self._lock:
            return list(self._polaczenie.execute(sql, tuple(parametry)).fetchall())

    def zamknij(self) -> None:
        with self._lock:
            self._polaczenie.close()

    # ------------------------------------------------------------------
    # Korpus
    # ------------------------------------------------------------------
    def zapisz_strone(self, url: str, status: int, html: str, url_koncowy: str = "",
                      tekst: str = "", meta: Optional[dict] = None) -> None:
        from .siec import host_z_url
        self.wykonaj(
            """INSERT INTO strony(url, host, status, url_koncowy, html, tekst, meta_json, pobrano)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(url) DO UPDATE SET status=excluded.status, html=excluded.html,
                 url_koncowy=excluded.url_koncowy, tekst=COALESCE(NULLIF(excluded.tekst,''), strony.tekst),
                 meta_json=COALESCE(NULLIF(excluded.meta_json,''), strony.meta_json),
                 pobrano=excluded.pobrano""",
            (url, host_z_url(url), status, url_koncowy or url, html, tekst,
             json.dumps(meta or {}, ensure_ascii=False), _teraz()))

    def uzupelnij_strone(self, url: str, tekst: str, meta: dict) -> None:
        self.wykonaj("UPDATE strony SET tekst=?, meta_json=? WHERE url=?",
                     (tekst, json.dumps(meta, ensure_ascii=False), url))

    def pobierz_strone(self, url: str, maks_wiek_dni: float = 30.0) -> Optional[Dict[str, Any]]:
        wiersze = self.pobierz_wiersze("SELECT * FROM strony WHERE url=?", (url,))
        if not wiersze:
            return None
        wiersz = dict(wiersze[0])
        if maks_wiek_dni and wiersz.get("pobrano"):
            if _teraz() - wiersz["pobrano"] > maks_wiek_dni * 86400:
                return None
        return wiersz

    def korpus(self, hosty: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if hosty:
            znaki = ",".join("?" * len(hosty))
            sql = f"SELECT * FROM strony WHERE status<400 AND host IN ({znaki})"
            return [dict(w) for w in self.pobierz_wiersze(sql, hosty)]
        return [dict(w) for w in self.pobierz_wiersze("SELECT * FROM strony WHERE status<400")]

    def statystyki_korpusu(self) -> List[Dict[str, Any]]:
        return [dict(w) for w in self.pobierz_wiersze(
            "SELECT host, COUNT(*) AS ile, MAX(pobrano) AS ostatnio FROM strony "
            "WHERE status<400 GROUP BY host ORDER BY ile DESC")]

    def wyczysc_korpus(self, host: str = "") -> int:
        if host:
            kursor = self.wykonaj("DELETE FROM strony WHERE host=?", (host,))
        else:
            kursor = self.wykonaj("DELETE FROM strony", ())
        return kursor.rowcount

    # ------------------------------------------------------------------
    # Przebiegi
    # ------------------------------------------------------------------
    def nowy_przebieg(self, nazwa: str, zapytanie: str, konfig: dict) -> int:
        kursor = self.wykonaj(
            "INSERT INTO przebiegi(nazwa, zapytanie, konfig_json, status, start, statystyki, dziennik)"
            " VALUES(?,?,?,?,?,?,?)",
            (nazwa, zapytanie, json.dumps(konfig, ensure_ascii=False), "trwa",
             _teraz(), "{}", ""))
        return int(kursor.lastrowid)

    def aktualizuj_przebieg(self, przebieg_id: int, **pola) -> None:
        if not pola:
            return
        ustaw = ", ".join(f"{k}=?" for k in pola)
        self.wykonaj(f"UPDATE przebiegi SET {ustaw} WHERE id=?",
                     list(pola.values()) + [przebieg_id])

    def przebieg(self, przebieg_id: int) -> Optional[dict]:
        wiersze = self.pobierz_wiersze("SELECT * FROM przebiegi WHERE id=?", (przebieg_id,))
        return dict(wiersze[0]) if wiersze else None

    def przebiegi(self, limit: int = 50) -> List[dict]:
        return [dict(w) for w in self.pobierz_wiersze(
            "SELECT p.*, (SELECT COUNT(*) FROM trafienia t WHERE t.przebieg_id=p.id) AS trafien "
            "FROM przebiegi p ORDER BY p.id DESC LIMIT ?", (limit,))]

    def usun_przebieg(self, przebieg_id: int) -> None:
        self.wykonaj("DELETE FROM trafienia WHERE przebieg_id=?", (przebieg_id,))
        self.wykonaj("DELETE FROM przebiegi WHERE id=?", (przebieg_id,))

    # ------------------------------------------------------------------
    # Trafienia
    # ------------------------------------------------------------------
    def dodaj_trafienie(self, przebieg_id: int, rekord: dict) -> int:
        from .siec import host_z_url
        kursor = self.wykonaj(
            """INSERT INTO trafienia(przebieg_id, url, host, tytul, autorzy, data, serwis,
                    wydawca, jezyk, typ, citekey, terminy, tagi, cytaty, meta_json, notatka,
                    wybrane, dodano)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(przebieg_id, url) DO UPDATE SET
                    terminy=excluded.terminy, cytaty=excluded.cytaty, tagi=excluded.tagi""",
            (przebieg_id, rekord["url"], host_z_url(rekord["url"]), rekord.get("tytul", ""),
             json.dumps(rekord.get("autorzy", []), ensure_ascii=False), rekord.get("data", ""),
             rekord.get("serwis", ""), rekord.get("wydawca", ""), rekord.get("jezyk", ""),
             rekord.get("typ", "webpage"), rekord.get("citekey", ""),
             json.dumps(rekord.get("terminy", []), ensure_ascii=False),
             json.dumps(rekord.get("tagi", []), ensure_ascii=False),
             json.dumps(rekord.get("cytaty", []), ensure_ascii=False),
             json.dumps(rekord.get("meta", {}), ensure_ascii=False),
             rekord.get("notatka", ""), 1, _teraz()))
        return int(kursor.lastrowid)

    def trafienia(self, przebieg_id: Optional[int] = None, tylko_wybrane: bool = False,
                  identyfikatory: Optional[List[int]] = None) -> List[dict]:
        warunki, parametry = [], []
        if przebieg_id is not None:
            warunki.append("przebieg_id=?")
            parametry.append(przebieg_id)
        if tylko_wybrane:
            warunki.append("wybrane=1")
        if identyfikatory:
            warunki.append("id IN (" + ",".join("?" * len(identyfikatory)) + ")")
            parametry.extend(identyfikatory)
        sql = "SELECT * FROM trafienia"
        if warunki:
            sql += " WHERE " + " AND ".join(warunki)
        sql += " ORDER BY data DESC, id DESC"
        return [self._rozpakuj(dict(w)) for w in self.pobierz_wiersze(sql, parametry)]

    @staticmethod
    def _rozpakuj(wiersz: dict) -> dict:
        for pole in ("autorzy", "terminy", "tagi", "cytaty"):
            try:
                wiersz[pole] = json.loads(wiersz.get(pole) or "[]")
            except ValueError:
                wiersz[pole] = []
        try:
            wiersz["meta"] = json.loads(wiersz.get("meta_json") or "{}")
        except ValueError:
            wiersz["meta"] = {}
        wiersz.pop("meta_json", None)
        return wiersz

    def zmien_trafienie(self, trafienie_id: int, **pola) -> None:
        dozwolone = {"tytul", "data", "serwis", "wydawca", "jezyk", "typ", "citekey",
                     "notatka", "wybrane"}
        ustawienia, parametry = [], []
        for klucz, wartosc in pola.items():
            if klucz in dozwolone:
                ustawienia.append(f"{klucz}=?")
                parametry.append(wartosc)
            elif klucz in ("tagi", "autorzy", "terminy"):
                ustawienia.append(f"{klucz}=?")
                parametry.append(json.dumps(wartosc, ensure_ascii=False))
        if not ustawienia:
            return
        parametry.append(trafienie_id)
        self.wykonaj(f"UPDATE trafienia SET {', '.join(ustawienia)} WHERE id=?", parametry)

    def usun_trafienia(self, identyfikatory: List[int]) -> None:
        if not identyfikatory:
            return
        self.wykonaj("DELETE FROM trafienia WHERE id IN (" + ",".join("?" * len(identyfikatory)) + ")",
                     identyfikatory)

    # ------------------------------------------------------------------
    # Ustawienia i presety
    # ------------------------------------------------------------------
    def ustaw(self, klucz: str, wartosc: Any) -> None:
        self.wykonaj("INSERT INTO ustawienia(klucz, wartosc) VALUES(?,?) "
                     "ON CONFLICT(klucz) DO UPDATE SET wartosc=excluded.wartosc",
                     (klucz, json.dumps(wartosc, ensure_ascii=False)))

    def ustawienie(self, klucz: str, domyslne: Any = None) -> Any:
        wiersze = self.pobierz_wiersze("SELECT wartosc FROM ustawienia WHERE klucz=?", (klucz,))
        if not wiersze:
            return domyslne
        try:
            return json.loads(wiersze[0]["wartosc"])
        except ValueError:
            return domyslne

    def zapisz_preset(self, nazwa: str, konfig: dict) -> None:
        self.wykonaj("INSERT INTO presety(nazwa, konfig_json, zmieniono) VALUES(?,?,?) "
                     "ON CONFLICT(nazwa) DO UPDATE SET konfig_json=excluded.konfig_json, "
                     "zmieniono=excluded.zmieniono",
                     (nazwa, json.dumps(konfig, ensure_ascii=False), _teraz()))

    def presety(self) -> List[dict]:
        wynik = []
        for wiersz in self.pobierz_wiersze("SELECT * FROM presety ORDER BY nazwa"):
            try:
                konfig = json.loads(wiersz["konfig_json"])
            except ValueError:
                konfig = {}
            wynik.append({"nazwa": wiersz["nazwa"], "konfig": konfig,
                          "zmieniono": wiersz["zmieniono"]})
        return wynik

    def usun_preset(self, nazwa: str) -> None:
        self.wykonaj("DELETE FROM presety WHERE nazwa=?", (nazwa,))
