# -*- coding: utf-8 -*-
"""Grzeczny klient HTTP: throttling per host, retry z backoffem, robots.txt, cache.

Zasady, których pilnuje ten moduł:
* jeden request na hosta naraz nie częściej niż co ``opoznienie`` sekund (+ jitter),
* nagłówek User-Agent z kontaktem do badacza (wymóg dobrych obyczajów),
* respektowanie robots.txt (można wyłączyć świadomie, np. dla własnego serwisu),
* 429/503 → czekamy tyle, ile każe Retry-After, potem backoff 2·, maks. N prób,
* żadnego omijania zabezpieczeń: 401/403 kończy się jasnym komunikatem i pominięciem.
"""

from __future__ import annotations

import gzip
import random
import re
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests

DOMYSLNY_UA = (
    "Kwerenda/1.0 (badawczy skrypt naukowy; +kontakt: {kontakt})"
)


def naglowek_ascii(tekst: str) -> str:
    """Nagłówki HTTP muszą być latin-1, a nazwiska bywają z ogonkami.

    „Paweł Downarowicz” → „Pawel Downarowicz”; reszta znaków spoza latin-1 znika,
    zamiast wywalać całe żądanie wyjątkiem UnicodeEncodeError.
    """
    from .fleksja import bez_ogonkow
    tekst = bez_ogonkow(str(tekst or ""))
    return tekst.encode("ascii", "ignore").decode("ascii").strip()


@dataclass
class Odpowiedz:
    url: str
    status: int
    tekst: str = ""
    naglowki: Dict[str, str] = field(default_factory=dict)
    z_cache: bool = False
    blad: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.blad


class BlokadaRobots(Exception):
    pass


def normalizuj_url(url: str) -> str:
    """Ucina fragment (#...) i porządkuje adres, żeby deduplikacja działała."""
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    czesci = urlparse(url)
    sciezka = re.sub(r"/{2,}", "/", czesci.path) or "/"
    if sciezka != "/" and sciezka.endswith("/"):
        sciezka = sciezka.rstrip("/")
    return urlunparse((czesci.scheme.lower(), czesci.netloc.lower(), sciezka,
                       "", czesci.query, ""))


def host_z_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def korzen(url: str) -> str:
    c = urlparse(normalizuj_url(url))
    return f"{c.scheme}://{c.netloc}"


class KlientHTTP:
    def __init__(self, kontakt: str = "badacz@example.org", opoznienie: float = 0.4,
                 timeout: float = 20.0, proby: int = 3, respektuj_robots: bool = True,
                 user_agent: str = "", cache=None, log=None):
        self.opoznienie = max(0.0, float(opoznienie))
        self.timeout = timeout
        self.proby = max(1, int(proby))
        self.respektuj_robots = respektuj_robots
        self.user_agent = naglowek_ascii(
            user_agent or DOMYSLNY_UA.format(kontakt=kontakt or "badacz")) or "Kwerenda/1.0"
        self.cache = cache
        self.log = log or (lambda *a, **k: None)
        self.sesja = requests.Session()
        self.sesja.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Language": "pl,de;q=0.8,uk;q=0.7,en;q=0.5",
        })
        self._ostatni: Dict[str, float] = {}
        self._zamki: Dict[str, threading.Lock] = {}
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._robots_lock = threading.Lock()
        self.licznik_zadan = 0

    # ---------------- throttling ----------------
    def _zamek(self, host: str) -> threading.Lock:
        with self._robots_lock:
            if host not in self._zamki:
                self._zamki[host] = threading.Lock()
            return self._zamki[host]

    def _poczekaj(self, host: str) -> None:
        if self.opoznienie <= 0:
            return
        ostatni = self._ostatni.get(host, 0.0)
        przerwa = self.opoznienie + random.uniform(0, self.opoznienie * 0.35)
        brakuje = ostatni + przerwa - time.monotonic()
        if brakuje > 0:
            time.sleep(brakuje)
        self._ostatni[host] = time.monotonic()

    # ---------------- robots ----------------
    def robots(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        baza = korzen(url)
        with self._robots_lock:
            if baza in self._robots:
                return self._robots[baza]
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(urljoin(baza + "/", "robots.txt"))
        try:
            r = self.sesja.get(urljoin(baza + "/", "robots.txt"), timeout=self.timeout)
            if r.status_code == 200:
                parser.parse(r.text.splitlines())
            else:
                parser.parse([])
        except requests.RequestException:
            parser = None  # brak robots.txt traktujemy jak brak ograniczeń
        with self._robots_lock:
            self._robots[baza] = parser
        return parser

    def wolno(self, url: str) -> bool:
        if not self.respektuj_robots:
            return True
        parser = self.robots(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def mapy_z_robots(self, url: str):
        parser = self.robots(url)
        if parser is None:
            return []
        try:
            return list(parser.site_maps() or [])
        except Exception:
            return []

    # ---------------- pobieranie ----------------
    def pobierz(self, url: str, *, params=None, uzyj_cache: bool = True,
                naglowki: Optional[dict] = None) -> Odpowiedz:
        url = normalizuj_url(url)
        if params:
            from urllib.parse import urlencode
            laczik = "&" if urlparse(url).query else "?"
            url = f"{url}{laczik}{urlencode(params, doseq=True)}"

        if uzyj_cache and self.cache is not None:
            zapisane = self.cache.pobierz_strone(url)
            if zapisane is not None:
                return Odpowiedz(url, zapisane.get("status", 200), zapisane.get("html", ""),
                                 {}, z_cache=True)

        if not self.wolno(url):
            self.log(f"robots.txt zabrania pobrania: {url}")
            return Odpowiedz(url, 999, blad="robots.txt zabrania pobierania tego adresu")

        host = host_z_url(url)
        opoznienie_kary = 0.0
        with self._zamek(host):
            for proba in range(1, self.proby + 1):
                self._poczekaj(host)
                if opoznienie_kary:
                    time.sleep(opoznienie_kary)
                try:
                    r = self.sesja.get(url, timeout=self.timeout, headers=naglowki or {},
                                       allow_redirects=True)
                    self.licznik_zadan += 1
                except requests.RequestException as exc:
                    if proba == self.proby:
                        return Odpowiedz(url, 0, blad=f"błąd sieci: {exc}")
                    opoznienie_kary = 2.0 * proba
                    continue

                if r.status_code in (429, 500, 502, 503, 504) and proba < self.proby:
                    retry_after = r.headers.get("Retry-After")
                    czekaj = 2.0 * proba
                    if retry_after and retry_after.strip().isdigit():
                        czekaj = min(60.0, float(retry_after.strip()))
                    self.log(f"HTTP {r.status_code} przy {url} – czekam {czekaj:.0f}s i ponawiam")
                    opoznienie_kary = czekaj
                    continue

                if r.status_code in (401, 403):
                    return Odpowiedz(r.url, r.status_code,
                                     blad="strona wymaga logowania/blokuje dostęp – pomijam")

                tekst = ""
                typ = r.headers.get("Content-Type", "")
                if r.status_code < 400 and ("html" in typ or "xml" in typ or "json" in typ
                                            or "text" in typ or not typ):
                    tekst = r.text
                odp = Odpowiedz(r.url, r.status_code, tekst, dict(r.headers))
                if odp.ok and self.cache is not None and tekst:
                    self.cache.zapisz_strone(url, r.status_code, tekst, r.url)
                return odp
        return Odpowiedz(url, 0, blad="wyczerpano próby")

    def pobierz_json(self, url: str, *, params=None, uzyj_cache: bool = False):
        odp = self.pobierz(url, params=params, uzyj_cache=uzyj_cache)
        if not odp.ok:
            return None, odp
        import json
        try:
            return json.loads(odp.tekst), odp
        except ValueError:
            return None, odp

    def pobierz_xml(self, url: str) -> Optional[str]:
        odp = self.pobierz(url, uzyj_cache=False)
        if not odp.ok:
            return None
        tekst = odp.tekst
        if not tekst and url.endswith(".gz"):
            try:
                tekst = gzip.decompress(odp.tekst.encode("latin-1")).decode("utf-8")
            except Exception:
                return None
        return tekst
