# -*- coding: utf-8 -*-
"""Adaptery źródeł: skąd brać listę kandydatów do sprawdzenia.

Kolejność w trybie ``auto`` (zgodnie z doświadczeniem z solidarnosc.mazowsze.pl,
gdzie wbudowana wyszukiwarka WP bywa niewiarygodna):

    REST API WordPressa → mapa strony (sitemap) → kanał RSS → wyszukiwarka HTML → crawl

Żadne z tych źródeł nie jest traktowane jako dowód trafienia: to tylko lista
kandydatów, których treść i tak weryfikujemy lokalnie zapytaniem.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .ekstrakcja import html_na_tekst, normalizuj_date
from .siec import KlientHTTP, host_z_url, korzen, normalizuj_url

TRYBY = ("auto", "wordpress", "sitemap", "rss", "szukajka", "crawl", "lista", "korpus")


@dataclass
class Zrodlo:
    url: str = ""
    nazwa: str = ""
    tryb: str = "auto"
    max_stron: int = 30              # limit paginacji wyszukiwarki/API
    max_url: int = 1500              # twardy limit kandydatów z jednego źródła
    tagi: List[str] = field(default_factory=list)
    wzorzec_url: str = ""            # regex – tylko pasujące adresy
    pomin_url: str = ""              # regex – adresy do pominięcia
    pelne_przemiatanie: bool = False # pobierz wszystko zamiast ufać wyszukiwarce
    typy_wp: List[str] = field(default_factory=lambda: ["posts"])
    od_roku: Optional[int] = None
    do_roku: Optional[int] = None
    okno_dat: str = ""               # "MM-DD:MM-DD", np. "04-20:05-10" – co roku
    glebokosc: int = 2               # dla trybu crawl
    lista_url: List[str] = field(default_factory=list)

    @property
    def etykieta(self) -> str:
        return self.nazwa or host_z_url(self.url) or self.url

    @classmethod
    def z_dict(cls, dane: dict) -> "Zrodlo":
        znane = {p for p in cls.__dataclass_fields__}          # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (dane or {}).items() if k in znane})


@dataclass
class Kandydat:
    url: str
    tytul: str = ""
    data: str = ""
    autorzy: List[str] = field(default_factory=list)
    tresc_html: str = ""             # gdy źródło dało pełną treść (REST API)
    zajawka: str = ""
    tagi_zrodla: List[str] = field(default_factory=list)
    skad: str = ""                   # api / sitemap / rss / szukajka / crawl / lista
    zrodlo: str = ""


Log = Callable[[str], None]


# --------------------------------------------------------------------------
# Pomocnicze
# --------------------------------------------------------------------------

def _okna_dat(zrodlo: Zrodlo) -> List[Tuple[str, str]]:
    """Zamienia „okno_dat” + zakres lat na listę par (po, przed) w ISO."""
    if not (zrodlo.od_roku or zrodlo.do_roku):
        return []
    od = zrodlo.od_roku or 1996
    do = zrodlo.do_roku or 2100
    if not zrodlo.okno_dat:
        return [(f"{od}-01-01T00:00:00", f"{do}-12-31T23:59:59")]
    m = re.match(r"^\s*(\d{2})-(\d{2})\s*:\s*(\d{2})-(\d{2})\s*$", zrodlo.okno_dat)
    if not m:
        return [(f"{od}-01-01T00:00:00", f"{do}-12-31T23:59:59")]
    okna = []
    for rok in range(od, do + 1):
        start = f"{rok}-{m.group(1)}-{m.group(2)}T00:00:00"
        koniec_rok = rok if (m.group(3), m.group(4)) >= (m.group(1), m.group(2)) else rok + 1
        koniec = f"{koniec_rok}-{m.group(3)}-{m.group(4)}T23:59:59"
        okna.append((start, koniec))
    return okna


def _pasuje_url(zrodlo: Zrodlo, url: str) -> bool:
    if zrodlo.wzorzec_url and not re.search(zrodlo.wzorzec_url, url, re.I):
        return False
    if zrodlo.pomin_url and re.search(zrodlo.pomin_url, url, re.I):
        return False
    return True


_NIE_TRESC = re.compile(
    r"\.(?:jpe?g|png|gif|webp|svg|pdf|docx?|xlsx?|pptx?|zip|rar|mp[34]|avi|mov|css|js)(?:$|\?)",
    re.I)


def _wyglada_na_tresc(url: str) -> bool:
    if _NIE_TRESC.search(url):
        return False
    sciezka = urlparse(url).path.lower()
    if any(sciezka.startswith(p) for p in ("/wp-admin", "/wp-login", "/wp-content", "/feed")):
        return False
    if re.search(r"/(tag|kategoria|category|author|autor|page|strona)/", sciezka):
        return False
    return True


# --------------------------------------------------------------------------
# WordPress REST API
# --------------------------------------------------------------------------

def wykryj_wordpress(klient: KlientHTTP, baza: str) -> bool:
    dane, odp = klient.pobierz_json(f"{korzen(baza)}/wp-json/wp/v2/posts",
                                    params={"per_page": 1})
    return isinstance(dane, list) and odp.ok


def _taksonomie_wp(klient: KlientHTTP, baza: str, log: Log) -> Dict[str, Dict[int, str]]:
    mapy: Dict[str, Dict[int, str]] = {"categories": {}, "tags": {}}
    for taksonomia in ("categories", "tags"):
        strona = 1
        while strona <= 5:
            dane, odp = klient.pobierz_json(f"{korzen(baza)}/wp-json/wp/v2/{taksonomia}",
                                            params={"per_page": 100, "page": strona})
            if not isinstance(dane, list) or not dane:
                break
            for wpis in dane:
                if isinstance(wpis, dict) and wpis.get("id"):
                    mapy[taksonomia][int(wpis["id"])] = html_na_tekst(str(wpis.get("name", "")))
            if len(dane) < 100:
                break
            strona += 1
    if mapy["categories"] or mapy["tags"]:
        log(f"    kategorie/tagi WP: {len(mapy['categories'])}+{len(mapy['tags'])} nazw")
    return mapy


def _post_na_kandydata(post: dict, mapy: Dict[str, Dict[int, str]], zrodlo: Zrodlo) -> Kandydat:
    tagi = list(zrodlo.tagi)
    for pole, taksonomia in (("categories", "categories"), ("tags", "tags")):
        for ident in post.get(pole) or []:
            nazwa = mapy.get(taksonomia, {}).get(int(ident))
            if nazwa:
                tagi.append(nazwa)
    autorzy = []
    osadzone = (post.get("_embedded") or {}).get("author") or []
    for autor in osadzone:
        if isinstance(autor, dict) and autor.get("name"):
            autorzy.append(html_na_tekst(str(autor["name"])))
    return Kandydat(
        url=normalizuj_url(post.get("link") or ""),
        tytul=html_na_tekst((post.get("title") or {}).get("rendered", "")),
        data=normalizuj_date(post.get("date_gmt") or post.get("date") or ""),
        autorzy=autorzy,
        tresc_html=(post.get("content") or {}).get("rendered", ""),
        zajawka=html_na_tekst((post.get("excerpt") or {}).get("rendered", "")),
        tagi_zrodla=tagi,
        skad="api",
        zrodlo=zrodlo.etykieta,
    )


def z_wordpress(klient: KlientHTTP, zrodlo: Zrodlo, hasla: Sequence[str],
                log: Log, przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    mapy = _taksonomie_wp(klient, baza, log)
    okna = _okna_dat(zrodlo)
    wydane = 0

    def zapytania() -> Iterator[dict]:
        podstawa: List[dict] = []
        if zrodlo.pelne_przemiatanie or not hasla:
            podstawa = [{}]
        else:
            podstawa = [{"search": h} for h in hasla]
        for typ in zrodlo.typy_wp or ["posts"]:
            for parametry in podstawa:
                if okna:
                    for po, przed in okna:
                        yield {"_typ": typ, "after": po, "before": przed, **parametry}
                else:
                    yield {"_typ": typ, **parametry}

    widziane = set()
    for parametry in zapytania():
        if przerwij() or wydane >= zrodlo.max_url:
            return
        typ = parametry.pop("_typ", "posts")
        etykieta = parametry.get("search") or parametry.get("after", "")[:7] or "wszystko"
        strona = 1
        while strona <= zrodlo.max_stron:
            if przerwij() or wydane >= zrodlo.max_url:
                return
            dane, odp = klient.pobierz_json(
                f"{baza}/wp-json/wp/v2/{typ}",
                params={"per_page": 100, "page": strona, "orderby": "date",
                        "_embed": "author", **parametry})
            if not isinstance(dane, list):
                if strona == 1:
                    log(f"    [API] {typ}/{etykieta}: brak odpowiedzi ({odp.status}) – pomijam")
                break
            if not dane:
                break
            nowe = 0
            for post in dane:
                if not isinstance(post, dict):
                    continue
                kandydat = _post_na_kandydata(post, mapy, zrodlo)
                if not kandydat.url or kandydat.url in widziane:
                    continue
                if not _pasuje_url(zrodlo, kandydat.url):
                    continue
                widziane.add(kandydat.url)
                nowe += 1
                wydane += 1
                yield kandydat
            wszystkich = odp.naglowki.get("X-WP-TotalPages") or odp.naglowki.get("x-wp-totalpages") or "1"
            try:
                stron_ogolem = int(wszystkich)
            except ValueError:
                stron_ogolem = 1
            log(f"    [API] {typ}/{etykieta}: strona {strona}/{stron_ogolem}, +{nowe} nowych")
            # O końcu paginacji decyduje wyłącznie X-WP-TotalPages: część serwisów
            # przycina per_page poniżej żądanej wartości i krótsza strona nie
            # oznacza wcale, że to ostatnia.
            if strona >= stron_ogolem:
                break
            strona += 1


# --------------------------------------------------------------------------
# Sitemap
# --------------------------------------------------------------------------

def _tag_bez_ns(element) -> str:
    return element.tag.split("}")[-1].lower()


def _parsuj_sitemap(xml: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Zwraca (linki do zagnieżdżonych map, [(url, lastmod)])."""
    try:
        korzen_xml = ET.fromstring(xml.encode("utf-8", "ignore"))
    except ET.ParseError:
        linki = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml or "", re.I)
        return ([l for l in linki if l.endswith(".xml")],
                [(l, "") for l in linki if not l.endswith(".xml")])
    mapy, adresy = [], []
    for dziecko in korzen_xml:
        nazwa = _tag_bez_ns(dziecko)
        loc, lastmod = "", ""
        for wnuk in dziecko:
            if _tag_bez_ns(wnuk) == "loc":
                loc = (wnuk.text or "").strip()
            elif _tag_bez_ns(wnuk) == "lastmod":
                lastmod = (wnuk.text or "").strip()
        if not loc:
            continue
        if nazwa == "sitemap":
            mapy.append(loc)
        else:
            adresy.append((loc, lastmod))
    return mapy, adresy


def z_sitemap(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
              przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    kandydaci_map = list(klient.mapy_z_robots(baza)) + [
        f"{baza}/wp-sitemap.xml", f"{baza}/sitemap_index.xml", f"{baza}/sitemap.xml",
        f"{baza}/sitemap-index.xml", f"{baza}/sitemap.xml.gz",
    ]
    do_odwiedzenia, odwiedzone, wydane = list(dict.fromkeys(kandydaci_map)), set(), 0
    lata = None
    if zrodlo.od_roku or zrodlo.do_roku:
        lata = range(zrodlo.od_roku or 1990, (zrodlo.do_roku or 2100) + 1)

    while do_odwiedzenia and not przerwij() and wydane < zrodlo.max_url:
        adres = do_odwiedzenia.pop(0)
        if adres in odwiedzone:
            continue
        odwiedzone.add(adres)
        xml = klient.pobierz_xml(adres)
        if not xml or "<" not in xml:
            continue
        mapy, adresy = _parsuj_sitemap(xml)
        if mapy:
            log(f"    [sitemap] {adres} → {len(mapy)} podmap")
            do_odwiedzenia.extend(m for m in mapy if m not in odwiedzone)
        if adresy:
            log(f"    [sitemap] {adres} → {len(adresy)} adresów")
        for url, lastmod in adresy:
            url = normalizuj_url(url)
            if host_z_url(url) != host_z_url(baza):
                continue
            if not (_pasuje_url(zrodlo, url) and _wyglada_na_tresc(url)):
                continue
            data = normalizuj_date(lastmod)
            if lata and data[:4].isdigit() and int(data[:4]) not in lata:
                # data z URL-a bywa wiarygodniejsza niż lastmod
                m = re.search(r"/((?:19|20)\d{2})/", url)
                if not (m and int(m.group(1)) in lata):
                    continue
            wydane += 1
            yield Kandydat(url=url, data=data, tagi_zrodla=list(zrodlo.tagi),
                           skad="sitemap", zrodlo=zrodlo.etykieta)
            if wydane >= zrodlo.max_url:
                return


# --------------------------------------------------------------------------
# RSS / Atom
# --------------------------------------------------------------------------

def z_rss(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
          przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    kanaly = [f"{baza}/feed", f"{baza}/?feed=rss2", f"{baza}/rss", f"{baza}/atom.xml",
              f"{baza}/feed/atom"]
    odp = klient.pobierz(baza)
    if odp.ok:
        zupa = BeautifulSoup(odp.tekst, "html.parser")
        for link in zupa.find_all("link", type=re.compile(r"rss|atom", re.I)):
            if link.get("href"):
                kanaly.insert(0, urljoin(baza, link["href"]))

    wydane = 0
    for kanal in dict.fromkeys(kanaly):
        if przerwij() or wydane >= zrodlo.max_url:
            return
        xml = klient.pobierz_xml(kanal)
        if not xml or "<" not in xml:
            continue
        try:
            korzen_xml = ET.fromstring(xml.encode("utf-8", "ignore"))
        except ET.ParseError:
            continue
        wpisy = [e for e in korzen_xml.iter() if _tag_bez_ns(e) in ("item", "entry")]
        if not wpisy:
            continue
        log(f"    [rss] {kanal} → {len(wpisy)} wpisów")
        for wpis in wpisy:
            url, tytul, data, kategorie, autor = "", "", "", [], ""
            for pole in wpis:
                nazwa = _tag_bez_ns(pole)
                if nazwa == "link":
                    url = (pole.get("href") or pole.text or "").strip()
                elif nazwa == "title":
                    tytul = html_na_tekst(pole.text or "")
                elif nazwa in ("pubdate", "published", "updated", "date"):
                    data = data or normalizuj_date(pole.text or "")
                elif nazwa == "category":
                    kategorie.append((pole.get("term") or pole.text or "").strip())
                elif nazwa == "creator":
                    autor = html_na_tekst(pole.text or "")
            url = normalizuj_url(url)
            if not url or not _pasuje_url(zrodlo, url):
                continue
            wydane += 1
            yield Kandydat(url=url, tytul=tytul, data=data,
                           autorzy=[autor] if autor else [],
                           tagi_zrodla=list(zrodlo.tagi) + [k for k in kategorie if k],
                           skad="rss", zrodlo=zrodlo.etykieta)
        if wydane:
            return


# --------------------------------------------------------------------------
# Wyszukiwarka HTML (?s=…&paged=N)
# --------------------------------------------------------------------------

_SELEKTORY_WYNIKOW = (
    "article a[rel='bookmark']", "h2.entry-title a", "h3.entry-title a", "h1.entry-title a",
    "h2.post-title a", ".entry-title a", ".post-title a", "article h2 a", "article h3 a",
    ".search-results a[href]", "main article a[href]")


def z_szukajki(klient: KlientHTTP, zrodlo: Zrodlo, hasla: Sequence[str], log: Log,
               przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    widziane, wydane = set(), 0
    for haslo in hasla or [""]:
        strona = 1
        while strona <= zrodlo.max_stron and not przerwij() and wydane < zrodlo.max_url:
            parametry = {"s": haslo}
            if strona > 1:
                parametry["paged"] = strona
            odp = klient.pobierz(f"{baza}/", params=parametry, uzyj_cache=False)
            if not odp.ok:
                log(f"    [szukajka] '{haslo}' strona {strona}: HTTP {odp.status} {odp.blad}")
                break
            zupa = BeautifulSoup(odp.tekst, "html.parser")

            linki = []
            for selektor in _SELEKTORY_WYNIKOW:
                znalezione = zupa.select(selektor)
                if znalezione:
                    linki = znalezione
                    break
            if not linki:
                linki = [a for a in zupa.find_all("a", href=re.compile(r"[?&]p=\d+"))]
            if not linki:
                for artykul in zupa.find_all("article"):
                    a = artykul.find("a", href=True)
                    if a:
                        linki.append(a)

            nowe = 0
            for a in linki:
                url = normalizuj_url(urljoin(baza, a.get("href") or ""))
                if not url or url in widziane or host_z_url(url) != host_z_url(baza):
                    continue
                if not (_pasuje_url(zrodlo, url) and _wyglada_na_tresc(url)):
                    continue
                widziane.add(url)
                nowe += 1
                wydane += 1
                yield Kandydat(url=url, tytul=a.get_text(" ", strip=True),
                               tagi_zrodla=list(zrodlo.tagi), skad="szukajka",
                               zrodlo=zrodlo.etykieta)
            log(f"    [szukajka] '{haslo}' strona {strona}: +{nowe}")
            ma_dalej = bool(zupa.select_one(f"a[href*='paged={strona + 1}'], a.next, .nav-previous a"))
            if nowe == 0 or not ma_dalej:
                break
            strona += 1


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------

def z_crawl(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
            przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    start = normalizuj_url(zrodlo.url)
    kolejka: List[Tuple[str, int]] = [(start, 0)]
    odwiedzone, wydane = set(), 0
    while kolejka and not przerwij() and wydane < zrodlo.max_url:
        url, glebokosc = kolejka.pop(0)
        if url in odwiedzone:
            continue
        odwiedzone.add(url)
        odp = klient.pobierz(url)
        if not odp.ok:
            continue
        if _wyglada_na_tresc(url) and _pasuje_url(zrodlo, url):
            wydane += 1
            yield Kandydat(url=url, tagi_zrodla=list(zrodlo.tagi), skad="crawl",
                           zrodlo=zrodlo.etykieta)
        if glebokosc >= zrodlo.glebokosc:
            continue
        zupa = BeautifulSoup(odp.tekst, "html.parser")
        for a in zupa.find_all("a", href=True):
            nowy = normalizuj_url(urljoin(url, a["href"]))
            if nowy and nowy not in odwiedzone and host_z_url(nowy) == host_z_url(baza):
                if not _NIE_TRESC.search(nowy):
                    kolejka.append((nowy, glebokosc + 1))
        if len(odwiedzone) % 25 == 0:
            log(f"    [crawl] odwiedzono {len(odwiedzone)}, w kolejce {len(kolejka)}")


# --------------------------------------------------------------------------
# Dyspozytor
# --------------------------------------------------------------------------

def kandydaci(klient: KlientHTTP, zrodlo: Zrodlo, hasla: Sequence[str], log: Log,
              przerwij: Callable[[], bool] = lambda: False) -> Iterator[Kandydat]:
    tryb = (zrodlo.tryb or "auto").lower()

    if tryb == "lista" or (tryb == "auto" and zrodlo.lista_url):
        for url in zrodlo.lista_url or [zrodlo.url]:
            url = normalizuj_url(url)
            if url and _pasuje_url(zrodlo, url):
                yield Kandydat(url=url, tagi_zrodla=list(zrodlo.tagi), skad="lista",
                               zrodlo=zrodlo.etykieta)
        return

    if tryb == "wordpress":
        yield from z_wordpress(klient, zrodlo, hasla, log, przerwij)
        return
    if tryb == "sitemap":
        yield from z_sitemap(klient, zrodlo, log, przerwij)
        return
    if tryb == "rss":
        yield from z_rss(klient, zrodlo, log, przerwij)
        return
    if tryb == "szukajka":
        yield from z_szukajki(klient, zrodlo, hasla, log, przerwij)
        return
    if tryb == "crawl":
        yield from z_crawl(klient, zrodlo, log, przerwij)
        return

    # ---- auto ----
    log(f"  wykrywanie sposobu dostępu dla {zrodlo.etykieta}…")
    if wykryj_wordpress(klient, zrodlo.url):
        log("    → REST API WordPressa działa, używam go")
        cokolwiek = False
        for kandydat in z_wordpress(klient, zrodlo, hasla, log, przerwij):
            cokolwiek = True
            yield kandydat
        if cokolwiek:
            return
        log("    → API nic nie zwróciło, próbuję dalej")
    else:
        log("    → brak REST API (404/wyłączone)")

    for nazwa, funkcja in (("mapa strony", z_sitemap), ("kanał RSS", z_rss)):
        cokolwiek = False
        for kandydat in funkcja(klient, zrodlo, log, przerwij):
            cokolwiek = True
            yield kandydat
        if cokolwiek:
            log(f"    → {nazwa} wystarczył")
            return
        log(f"    → {nazwa}: pusto")

    log("    → zostaje wyszukiwarka HTML")
    cokolwiek = False
    for kandydat in z_szukajki(klient, zrodlo, hasla, log, przerwij):
        cokolwiek = True
        yield kandydat
    if not cokolwiek:
        log("    → wyszukiwarka nic nie dała, przechodzę na crawl")
        yield from z_crawl(klient, zrodlo, log, przerwij)
