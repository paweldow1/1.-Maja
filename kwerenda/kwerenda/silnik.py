# -*- coding: utf-8 -*-
"""Silnik kwerendy: źródła → kandydaci → weryfikacja treści → trafienia w bazie.

Najważniejsza zasada: wyszukiwarka serwisu (WP, RSS, sitemap) jest tylko
listą kandydatów. Dopasowanie zawsze potwierdzamy na pełnym tekście artykułu
własnym zapytaniem — dzięki temu wynik jest powtarzalny i niezależny od tego,
jak dana strona ma skonfigurowane wyszukiwanie.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .cytowania import Rekord, nadaj_citekeys, zbuduj_citekey
from .ekstrakcja import (Metadane, dzis_iso, html_na_tekst, rok_z_daty,
                         wyciagnij_metadane, wyciagnij_tekst)
from .konfiguracja import Konfiguracja
from .magazyn import Magazyn
from .siec import KlientHTTP, host_z_url, normalizuj_url
from .zapytania import Dokument, Wezel, cytaty, parsuj
from .zrodla import Kandydat, Zrodlo, kandydaci


@dataclass
class Postep:
    status: str = "przygotowanie"
    zrodlo: str = ""
    kandydatow: int = 0
    sprawdzonych: int = 0
    trafien: int = 0
    pobran: int = 0
    z_cache: int = 0
    bledow: int = 0
    start: float = field(default_factory=time.time)

    def jako_dict(self) -> dict:
        dane = dict(self.__dict__)
        dane["sekundy"] = round(time.time() - self.start, 1)
        return dane


class Silnik:
    def __init__(self, konfig: Konfiguracja, magazyn: Magazyn,
                 log: Optional[Callable[[str], None]] = None):
        self.konfig = konfig
        self.magazyn = magazyn
        self.postep = Postep()
        self.dziennik: List[str] = []
        self._zewnetrzny_log = log
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.przebieg_id: Optional[int] = None
        self.klient = KlientHTTP(
            kontakt=konfig.kontakt or "badacz",
            opoznienie=konfig.opoznienie,
            proby=konfig.proby,
            respektuj_robots=konfig.respektuj_robots,
            cache=magazyn if konfig.uzyj_cache else None,
            log=self.log,
        )
        self._widziane_url: set = set()
        self._citekeys: set = set()

    # ------------------------------------------------------------------
    def log(self, wiadomosc: str) -> None:
        wpis = time.strftime("%H:%M:%S ") + wiadomosc
        with self._lock:
            self.dziennik.append(wpis)
            if len(self.dziennik) > 4000:
                del self.dziennik[:1000]
        if self._zewnetrzny_log:
            self._zewnetrzny_log(wpis)

    def przerwij(self) -> None:
        self._stop.set()
        self.log("⏹ przerwane przez użytkownika")

    def czy_stop(self) -> bool:
        return self._stop.is_set()

    # ------------------------------------------------------------------
    def hasla_dla_wyszukiwarek(self, drzewo: Wezel) -> List[str]:
        """Słowa, którymi warto zaczepić wyszukiwarkę serwisu (bez NOT-ów)."""
        hasla: List[str] = []
        for termin in drzewo.terminy():
            tekst = termin.tekst.strip().strip("*")
            if tekst and tekst not in hasla:
                hasla.append(tekst)
        return hasla[:12]

    # ------------------------------------------------------------------
    def uruchom(self, przebieg_id: Optional[int] = None) -> int:
        konfig = self.konfig
        drzewo = parsuj(konfig.zapytanie, konfig.opcje_fleksji(), konfig.domyslny_operator)
        hasla = self.hasla_dla_wyszukiwarek(drzewo)

        if przebieg_id is None:
            przebieg_id = self.magazyn.nowy_przebieg(konfig.nazwa, konfig.zapytanie,
                                                     konfig.jako_dict())
        self.przebieg_id = przebieg_id
        self.postep.status = "zbieranie"
        self.log(f"▶ start: {konfig.nazwa}")
        self.log(f"  zapytanie: {drzewo.opis()}")
        if hasla:
            self.log(f"  hasła dla wyszukiwarek serwisów: {', '.join(hasla)}")
        for uwaga in konfig.sprawdz():
            self.log("  ⚠ " + uwaga)

        try:
            for zrodlo in konfig.zrodla:
                if self.czy_stop():
                    break
                try:
                    self._przetworz_zrodlo(zrodlo, drzewo, hasla, przebieg_id)
                except Exception as exc:
                    # Awaria jednego serwisu nie może przerwać całej kwerendy:
                    # zapisujemy ją w dzienniku i idziemy do następnego źródła.
                    self.postep.bledow += 1
                    self.log(f"  ✕ źródło {zrodlo.etykieta} przerwane błędem: "
                             f"{type(exc).__name__}: {exc}")
                    import traceback as _tb
                    self.log("    " + _tb.format_exc(limit=2).replace("\n", " ")[:400])
        finally:
            self.postep.status = "przerwane" if self.czy_stop() else "gotowe"
            self.magazyn.aktualizuj_przebieg(
                przebieg_id, status=self.postep.status, koniec=time.time(),
                statystyki=_json(self.postep.jako_dict()),
                dziennik="\n".join(self.dziennik[-800:]))
            self.log(f"■ koniec: {self.postep.trafien} trafień "
                     f"z {self.postep.sprawdzonych} sprawdzonych stron "
                     f"({self.postep.pobran} pobrań, {self.postep.z_cache} z pamięci podręcznej)")
        return przebieg_id

    # ------------------------------------------------------------------
    def _przetworz_zrodlo(self, zrodlo: Zrodlo, drzewo: Wezel, hasla: Sequence[str],
                          przebieg_id: int) -> None:
        self.postep.zrodlo = zrodlo.etykieta
        self.log(f"► źródło: {zrodlo.etykieta} (tryb: {zrodlo.tryb})")

        if (zrodlo.tryb or "").lower() == "korpus":
            self._z_korpusu(zrodlo, drzewo, przebieg_id)
            return

        paczka: List[Kandydat] = []
        for kandydat in kandydaci(self.klient, zrodlo, hasla, self.log, self.czy_stop):
            if self.czy_stop():
                break
            url = normalizuj_url(kandydat.url)
            if not url or url in self._widziane_url:
                continue
            self._widziane_url.add(url)
            kandydat.url = url
            paczka.append(kandydat)
            self.postep.kandydatow += 1
            if len(paczka) >= 40:
                self._sprawdz_paczke(paczka, drzewo, przebieg_id, zrodlo)
                paczka = []
            if self.postep.kandydatow >= self.konfig.limit_kandydatow:
                self.log("  osiągnięto limit kandydatów – kończę to źródło")
                break
        if paczka and not self.czy_stop():
            self._sprawdz_paczke(paczka, drzewo, przebieg_id, zrodlo)

    def _sprawdz_paczke(self, paczka: List[Kandydat], drzewo: Wezel, przebieg_id: int,
                        zrodlo: Zrodlo) -> None:
        watki = max(1, int(self.konfig.watki))
        if watki == 1:
            for kandydat in paczka:
                self._sprawdz(kandydat, drzewo, przebieg_id, zrodlo)
            return
        with ThreadPoolExecutor(max_workers=watki) as pula:
            list(pula.map(lambda k: self._sprawdz(k, drzewo, przebieg_id, zrodlo), paczka))

    # ------------------------------------------------------------------
    def _sprawdz(self, kandydat: Kandydat, drzewo: Wezel, przebieg_id: int,
                 zrodlo: Zrodlo) -> None:
        if self.czy_stop() or self.postep.trafien >= self.konfig.limit_trafien:
            return
        try:
            tekst, meta = self._tresc_i_meta(kandydat)
        except Exception as exc:                      # nie przerywamy całej kwerendy
            self.postep.bledow += 1
            self.log(f"  ! błąd przy {kandydat.url}: {exc}")
            return
        self.postep.sprawdzonych += 1

        if not tekst:
            return

        rok = rok_z_daty(meta.data or kandydat.data)
        if rok and (self.konfig.od_roku or self.konfig.do_roku):
            wartosc = int(rok)
            if self.konfig.od_roku and wartosc < self.konfig.od_roku:
                return
            if self.konfig.do_roku and wartosc > self.konfig.do_roku:
                return

        tagi_wejsciowe = list(kandydat.tagi_zrodla) if self.konfig.tagi_z_wp else list(zrodlo.tagi)
        dokument = Dokument(
            tytul=meta.tytul or kandydat.tytul,
            tekst=tekst,
            url=kandydat.url,
            autor="; ".join(meta.autorzy or kandydat.autorzy),
            tagi=tagi_wejsciowe,
        )
        pasuje, trafienia = drzewo.ocen(dokument)
        if not pasuje:
            return

        fragmenty = cytaty(dokument, trafienia, self.konfig.okno_cytatu, self.konfig.maks_cytatow)
        rekord = self._zbuduj_rekord(kandydat, meta, trafienia, fragmenty, tagi_wejsciowe, zrodlo)
        with self._lock:
            self.magazyn.dodaj_trafienie(przebieg_id, rekord)
            self.postep.trafien += 1
        formy = ", ".join(sorted({t.forma for t in trafienia})[:6])
        self.log(f"  ✓ {rekord['tytul'][:70]} [{rekord['data'] or 'bez daty'}] — {formy}")

    # ------------------------------------------------------------------
    def _tresc_i_meta(self, kandydat: Kandydat) -> tuple:
        """Tekst artykułu i metadane – z REST API, z pamięci podręcznej albo z sieci."""
        if kandydat.tresc_html:
            tekst = html_na_tekst(kandydat.tresc_html)
            meta = Metadane(tytul=kandydat.tytul, autorzy=list(kandydat.autorzy),
                            data=kandydat.data, opis=kandydat.zajawka)
            if len(tekst) > 200 or not kandydat.url:
                self.postep.z_cache += 1
                return tekst, meta

        zapisane = None
        if self.konfig.uzyj_cache:
            zapisane = self.magazyn.pobierz_strone(kandydat.url, self.konfig.maks_wiek_cache_dni)
        if zapisane and zapisane.get("tekst"):
            self.postep.z_cache += 1
            meta_dict = {}
            try:
                import json as _json
                meta_dict = _json.loads(zapisane.get("meta_json") or "{}")
            except ValueError:
                meta_dict = {}
            meta = Metadane(**{k: v for k, v in meta_dict.items()
                               if k in Metadane.__dataclass_fields__})
            return zapisane["tekst"], meta

        html = ""
        if zapisane and zapisane.get("html"):
            html = zapisane["html"]
            self.postep.z_cache += 1
        else:
            odp = self.klient.pobierz(kandydat.url, uzyj_cache=False)
            self.postep.pobran += 1
            if not odp.ok:
                if odp.blad:
                    self.log(f"  – pomijam {kandydat.url}: {odp.blad}")
                return "", Metadane()
            html = odp.tekst

        tekst = wyciagnij_tekst(html)
        meta = wyciagnij_metadane(html, kandydat.url)
        if self.konfig.uzyj_cache:
            self.magazyn.zapisz_strone(kandydat.url, 200, html, kandydat.url, tekst,
                                       meta.jako_dict())
        return tekst, meta

    # ------------------------------------------------------------------
    def _zbuduj_rekord(self, kandydat: Kandydat, meta: Metadane, trafienia,
                       fragmenty, tagi_wejsciowe: List[str], zrodlo: Zrodlo) -> dict:
        konfig = self.konfig
        data = meta.data or kandydat.data
        # W tagach nie chcemy technicznych ozdobników zapytania („pierwszomaj*”).
        terminy = sorted({t.termin.strip().rstrip("*").strip() for t in trafienia if t.termin.strip()})

        tagi: List[str] = []
        tagi.extend(konfig.tagi_dodatkowe)
        tagi.extend(tagi_wejsciowe)
        if konfig.tagi_z_wp:
            tagi.extend(meta.slowa_kluczowe)
            if meta.rubryka:
                tagi.append(meta.rubryka)
        if konfig.tag_z_terminow:
            tagi.extend(terminy)
        if konfig.tag_z_domeny:
            tagi.append(host_z_url(kandydat.url))
        if konfig.tag_z_roku:
            rok = rok_z_daty(data)
            if rok:
                tagi.append(rok)
        tagi = [t.strip() for t in dict.fromkeys(tagi) if t and t.strip()]

        rekord = Rekord(
            url=kandydat.url,
            tytul=meta.tytul or kandydat.tytul or kandydat.url,
            autorzy=meta.autorzy or kandydat.autorzy,
            data=data,
            serwis=meta.nazwa_serwisu or zrodlo.nazwa or host_z_url(kandydat.url),
            wydawca=meta.wydawca or zrodlo.nazwa or host_z_url(kandydat.url),
            jezyk=meta.jezyk,
            typ=konfig.typ_zotero or meta.typ or "webpage",
            opis=meta.opis,
            tagi=tagi,
            terminy=terminy,
            cytaty=fragmenty,
        )
        with self._lock:
            rekord.citekey = zbuduj_citekey(rekord, self._citekeys)

        return {
            "url": rekord.url, "tytul": rekord.tytul, "autorzy": rekord.autorzy,
            "data": rekord.data, "serwis": rekord.serwis, "wydawca": rekord.wydawca,
            "jezyk": rekord.jezyk, "typ": rekord.typ, "citekey": rekord.citekey,
            "terminy": rekord.terminy, "tagi": rekord.tagi, "cytaty": rekord.cytaty,
            "meta": {**meta.jako_dict(), "skad": kandydat.skad, "zrodlo": zrodlo.etykieta,
                     "data_dostepu": dzis_iso()},
        }

    # ------------------------------------------------------------------
    def _z_korpusu(self, zrodlo: Zrodlo, drzewo: Wezel, przebieg_id: int) -> None:
        """Przeszukuje wyłącznie to, co już mamy w bazie – bez ruchu w sieci."""
        hosty = [host_z_url(zrodlo.url)] if zrodlo.url else None
        strony = self.magazyn.korpus(hosty)
        self.log(f"  korpus lokalny: {len(strony)} stron")
        for strona in strony:
            if self.czy_stop():
                return
            self.postep.kandydatow += 1
            tekst = strona.get("tekst") or wyciagnij_tekst(strona.get("html") or "")
            if not tekst:
                continue
            try:
                import json as _json
                meta_dict = _json.loads(strona.get("meta_json") or "{}")
            except ValueError:
                meta_dict = {}
            meta = Metadane(**{k: v for k, v in meta_dict.items()
                               if k in Metadane.__dataclass_fields__})
            if not meta.tytul:
                meta = wyciagnij_metadane(strona.get("html") or "", strona["url"])
            kandydat = Kandydat(url=strona["url"], tytul=meta.tytul, data=meta.data,
                                tagi_zrodla=list(zrodlo.tagi), skad="korpus",
                                zrodlo=zrodlo.etykieta)
            self.postep.sprawdzonych += 1
            dokument = Dokument(tytul=meta.tytul, tekst=tekst, url=strona["url"],
                                autor="; ".join(meta.autorzy), tagi=zrodlo.tagi)
            pasuje, trafienia = drzewo.ocen(dokument)
            if not pasuje:
                continue
            fragmenty = cytaty(dokument, trafienia, self.konfig.okno_cytatu,
                               self.konfig.maks_cytatow)
            rekord = self._zbuduj_rekord(kandydat, meta, trafienia, fragmenty,
                                         list(zrodlo.tagi), zrodlo)
            self.magazyn.dodaj_trafienie(przebieg_id, rekord)
            self.postep.trafien += 1
            self.log(f"  ✓ {rekord['tytul'][:70]} (korpus)")


def _json(dane) -> str:
    import json
    return json.dumps(dane, ensure_ascii=False)
