# -*- coding: utf-8 -*-
"""A well-mannered HTTP client: per-host throttling, backoff, robots.txt, cache.

What this module guarantees:

* one request per host at a time, no more often than ``opoznienie`` seconds
  (plus jitter);
* a User-Agent carrying the researcher's contact details — basic courtesy;
* robots.txt is respected (it can be switched off deliberately, e.g. for a site
  you run yourself);
* 429/503 → wait as long as Retry-After says, then back off, up to N attempts;
* **no circumvention of anything.** A 401/403 ends in a clear message and the
  page is skipped.

A source may carry *your own* credentials — a cookie header, a ``cookies.txt``
exported from your browser, or HTTP basic auth. That is how you reach material
your own subscription covers. It is not a way past a paywall you have no right
to, and nothing here tries to disguise the client or defeat bot detection.
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
    """HTTP headers must be latin-1, and names often are not.

    "Paweł Downarowicz" → "Pawel Downarowicz"; anything else outside latin-1 is
    dropped instead of blowing up the whole request with UnicodeEncodeError.
    """
    from .morfologia import bez_ogonkow
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
    dane: bytes = b""            # raw body, kept for attachments (PDF, .docx)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.blad


class BlokadaRobots(Exception):
    pass


def ciasteczka_z_naglowka(naglowek: str) -> Dict[str, str]:
    """Parse a raw ``Cookie:`` header copied from the browser's dev tools."""
    wynik: Dict[str, str] = {}
    for kawalek in (naglowek or "").split(";"):
        nazwa, _, wartosc = kawalek.strip().partition("=")
        if nazwa and wartosc:
            wynik[nazwa.strip()] = wartosc.strip()
    return wynik


def ciasteczka_z_pliku(sciezka: str) -> Dict[str, str]:
    """Read a Netscape-format cookies.txt exported from a browser."""
    import http.cookiejar
    sloik = http.cookiejar.MozillaCookieJar()
    try:
        sloik.load(sciezka, ignore_discard=True, ignore_expires=True)
    except Exception as exc:
        raise ValueError(f"cannot read cookies file {sciezka}: {exc}") from exc
    return {c.name: c.value for c in sloik if c.value}


def ciasteczka_z_przegladarki(nazwa: str, domena: str = "") -> Dict[str, str]:
    """Read cookies straight from a local browser profile (needs browser_cookie3)."""
    try:
        import browser_cookie3  # type: ignore
    except ImportError as exc:
        raise ValueError("reading cookies from the browser needs the optional package "
                         "browser_cookie3 (pip install browser-cookie3)") from exc
    funkcja = getattr(browser_cookie3, (nazwa or "firefox").lower(), None)
    if funkcja is None:
        raise ValueError(f"unknown browser: {nazwa}")
    sloik = funkcja(domain_name=domena or "")
    return {c.name: c.value for c in sloik if c.value}


def normalizuj_url(url: str) -> str:
    """Drop the #fragment and tidy the address so that de-duplication works."""
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
                 user_agent: str = "", cache=None, log=None, maks_plik_mb: float = 40.0):
        self.opoznienie = max(0.0, float(opoznienie))
        self.timeout = timeout
        self.proby = max(1, int(proby))
        self.respektuj_robots = respektuj_robots
        self.maks_plik_mb = maks_plik_mb
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
        self._konteksty: Dict[int, dict] = {}
        self.licznik_zadan = 0

    # ---------------- credentials of a single source ----------------
    def kontekst_zrodla(self, zrodlo) -> dict:
        """Cookies / auth / extra headers of one source, built once and cached."""
        if zrodlo is None:
            return {}
        klucz = id(zrodlo)
        if klucz in self._konteksty:
            return self._konteksty[klucz]

        kontekst: dict = {"cookies": {}, "headers": {}, "auth": None}
        try:
            if getattr(zrodlo, "ciasteczka", ""):
                kontekst["cookies"].update(ciasteczka_z_naglowka(zrodlo.ciasteczka))
            if getattr(zrodlo, "plik_ciasteczek", ""):
                kontekst["cookies"].update(ciasteczka_z_pliku(zrodlo.plik_ciasteczek))
            if getattr(zrodlo, "ciasteczka_z_przegladarki", ""):
                kontekst["cookies"].update(ciasteczka_z_przegladarki(
                    zrodlo.ciasteczka_z_przegladarki, host_z_url(zrodlo.url)))
        except ValueError as exc:
            self.log(f"credentials for {getattr(zrodlo, 'url', '?')}: {exc}")
        if getattr(zrodlo, "naglowki", None):
            kontekst["headers"].update({str(k): str(v) for k, v in zrodlo.naglowki.items()})
        if getattr(zrodlo, "basic_auth", ""):
            uzytkownik, _, haslo = zrodlo.basic_auth.partition(":")
            kontekst["auth"] = (uzytkownik, haslo)
        if kontekst["cookies"] or kontekst["auth"]:
            self.log(f"using your own credentials for {host_z_url(getattr(zrodlo, 'url', ''))} "
                     f"({len(kontekst['cookies'])} cookies)")
        self._konteksty[klucz] = kontekst
        return kontekst

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
                naglowki: Optional[dict] = None, zrodlo=None) -> Odpowiedz:
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
            self.log(f"robots.txt disallows: {url}")
            return Odpowiedz(url, 999, blad="robots.txt disallows fetching this address")

        host = host_z_url(url)
        opoznienie_kary = 0.0
        with self._zamek(host):
            for proba in range(1, self.proby + 1):
                self._poczekaj(host)
                if opoznienie_kary:
                    time.sleep(opoznienie_kary)
                kontekst = self.kontekst_zrodla(zrodlo)
                laczne_naglowki = dict(kontekst.get("headers") or {})
                laczne_naglowki.update(naglowki or {})
                try:
                    r = self.sesja.get(url, timeout=self.timeout,
                                       headers=laczne_naglowki,
                                       cookies=kontekst.get("cookies") or None,
                                       auth=kontekst.get("auth"),
                                       allow_redirects=True)
                    self.licznik_zadan += 1
                except requests.RequestException as exc:
                    if proba == self.proby:
                        return Odpowiedz(url, 0, blad=f"network error: {exc}")
                    opoznienie_kary = 2.0 * proba
                    continue

                if r.status_code in (429, 500, 502, 503, 504) and proba < self.proby:
                    retry_after = r.headers.get("Retry-After")
                    czekaj = 2.0 * proba
                    if retry_after and retry_after.strip().isdigit():
                        czekaj = min(60.0, float(retry_after.strip()))
                    self.log(f"HTTP {r.status_code} at {url} — waiting {czekaj:.0f}s and retrying")
                    opoznienie_kary = czekaj
                    continue

                if r.status_code in (401, 403):
                    return Odpowiedz(r.url, r.status_code,
                                     blad="the page requires signing in or refuses access "
                                          "— skipping")

                tekst, dane = "", b""
                typ = r.headers.get("Content-Type", "")
                if r.status_code < 400 and ("html" in typ or "xml" in typ or "json" in typ
                                            or "text" in typ or not typ):
                    tekst = r.text
                if r.status_code < 400:
                    from .pliki import czy_zalacznik
                    if czy_zalacznik(url, typ):
                        # An attachment is bytes, not text: keep the body, unless it
                        # is so large that holding it in memory would be reckless.
                        if len(r.content) <= self.maks_plik_mb * 1024 * 1024:
                            dane = r.content
                        else:
                            return Odpowiedz(r.url, r.status_code, naglowki=dict(r.headers),
                                             blad=f"file larger than {self.maks_plik_mb:.0f} MB "
                                                  f"— skipping")
                odp = Odpowiedz(r.url, r.status_code, tekst, dict(r.headers), dane=dane)
                if odp.ok and self.cache is not None and tekst:
                    self.cache.zapisz_strone(url, r.status_code, tekst, r.url)
                return odp
        return Odpowiedz(url, 0, blad="all attempts exhausted")

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
