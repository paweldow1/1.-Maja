# -*- coding: utf-8 -*-
"""Source adapters: where the list of candidate pages comes from.

In ``auto`` mode the engine walks down this ladder until something works:

    WordPress REST API → Drupal JSON:API → sitemap → RSS feed
    → the site's own search page → plain link crawl

None of these is treated as proof of a hit: they only produce candidates, whose
full text is then verified locally against the query. Site search engines are
frequently unreliable — the archive search of a large newspaper may miss half of
what it holds — so the two escape hatches that matter are:

* ``search_url`` — a template for the site's own search, e.g.
  ``https://example.com/search?q={q}&page={page}``;
* ``listing_url`` — a template for a paginated archive/index,
  e.g. ``https://example.com/archive/{year}/page/{page}``,
  which sidesteps the site's search entirely.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from .ekstrakcja import html_na_tekst, normalizuj_date
from .siec import KlientHTTP, host_z_url, korzen, normalizuj_url

TRYBY = ("auto", "wordpress", "drupal", "sitemap", "rss", "search", "listing",
         "crawl", "urls", "corpus")

#: External (English) key -> internal attribute.
KLUCZE: Dict[str, str] = {
    "url": "url", "name": "nazwa", "mode": "tryb",
    "max_pages": "max_stron", "max_urls": "max_url", "tags": "tagi",
    "url_pattern": "wzorzec_url", "url_exclude": "pomin_url",
    "full_sweep": "pelne_przemiatanie", "wp_types": "typy_wp",
    "year_from": "od_roku", "year_to": "do_roku", "date_window": "okno_dat",
    "depth": "glebokosc", "urls": "lista_url",
    "search_url": "szablon_szukania", "listing_url": "szablon_listy",
    "link_selector": "selektor_linkow", "next_selector": "selektor_dalej",
    "first_page": "pierwsza_strona", "language": "jezyk",
    "cookies": "ciasteczka", "cookies_file": "plik_ciasteczek",
    "browser_cookies": "ciasteczka_z_przegladarki",
    "basic_auth": "basic_auth", "headers": "naglowki",
}
_ODWROTNE = {v: k for k, v in KLUCZE.items()}


@dataclass
class Zrodlo:
    url: str = ""
    nazwa: str = ""
    tryb: str = "auto"
    max_stron: int = 30                 # pagination limit
    max_url: int = 1500                 # hard cap on candidates from one source
    tagi: List[str] = field(default_factory=list)
    wzorzec_url: str = ""               # regex — only addresses that match
    pomin_url: str = ""                 # regex — addresses to skip
    pelne_przemiatanie: bool = False    # sweep the archive instead of trusting search
    typy_wp: List[str] = field(default_factory=lambda: ["posts"])
    od_roku: Optional[int] = None
    do_roku: Optional[int] = None
    okno_dat: str = ""                  # "MM-DD:MM-DD", repeated every year
    glebokosc: int = 2                  # crawl depth
    lista_url: List[str] = field(default_factory=list)
    jezyk: str = ""                     # language hint for this source

    # universal templates
    szablon_szukania: str = ""          # ".../search?q={q}&page={page}"
    szablon_listy: str = ""             # ".../archive/{year}/page/{page}"
    selektor_linkow: str = ""           # CSS for result links
    selektor_dalej: str = ""            # CSS for the "next page" link
    pierwsza_strona: int = 1

    # access with your own credentials (never a paywall bypass)
    ciasteczka: str = ""                # raw Cookie header
    plik_ciasteczek: str = ""           # Netscape cookies.txt exported from a browser
    ciasteczka_z_przegladarki: str = "" # "firefox" / "chrome" (needs browser_cookie3)
    basic_auth: str = ""                # "user:password"
    naglowki: Dict[str, str] = field(default_factory=dict)

    @property
    def etykieta(self) -> str:
        return self.nazwa or host_z_url(self.url) or self.url or "source"

    def ma_dane_logowania(self) -> bool:
        return bool(self.ciasteczka or self.plik_ciasteczek
                    or self.ciasteczka_z_przegladarki or self.basic_auth)

    def jako_dict(self) -> dict:
        return {_ODWROTNE.get(k, k): v for k, v in asdict(self).items()}

    @classmethod
    def z_dict(cls, dane: dict) -> "Zrodlo":
        znane = set(cls.__dataclass_fields__)       # type: ignore[attr-defined]
        czyste = {}
        for klucz, wartosc in (dane or {}).items():
            nazwa = KLUCZE.get(klucz, klucz)
            if nazwa in znane:
                czyste[nazwa] = wartosc
        czyste["tryb"] = _NORMALIZUJ_TRYB.get(str(czyste.get("tryb", "auto")).lower(),
                                              str(czyste.get("tryb", "auto")).lower())
        return cls(**czyste)


_NORMALIZUJ_TRYB = {
    "auto": "auto", "wordpress": "wordpress", "wp": "wordpress", "drupal": "drupal",
    "sitemap": "sitemap", "mapa": "sitemap", "rss": "rss", "feed": "rss",
    "search": "search", "szukajka": "search", "listing": "listing", "lista": "urls",
    "crawl": "crawl", "urls": "urls", "corpus": "corpus", "korpus": "corpus",
}


@dataclass
class Kandydat:
    url: str
    tytul: str = ""
    data: str = ""
    autorzy: List[str] = field(default_factory=list)
    tresc_html: str = ""                # when the source already gave us full text
    zajawka: str = ""
    tagi_zrodla: List[str] = field(default_factory=list)
    skad: str = ""                      # api / sitemap / rss / search / listing / crawl
    zrodlo: str = ""


Log = Callable[[str], None]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _okna_dat(zrodlo: Zrodlo) -> List[Tuple[str, str]]:
    """Turn "date_window" plus a year range into (after, before) ISO pairs."""
    if not (zrodlo.od_roku or zrodlo.do_roku):
        return []
    od = zrodlo.od_roku or 1996
    do = zrodlo.do_roku or 2100
    dopasowanie = re.match(r"^\s*(\d{2})-(\d{2})\s*:\s*(\d{2})-(\d{2})\s*$",
                           zrodlo.okno_dat or "")
    if not dopasowanie:
        return [(f"{od}-01-01T00:00:00", f"{do}-12-31T23:59:59")]
    okna = []
    for rok in range(od, do + 1):
        start = f"{rok}-{dopasowanie.group(1)}-{dopasowanie.group(2)}T00:00:00"
        koniec_rok = rok if (dopasowanie.group(3), dopasowanie.group(4)) >= \
            (dopasowanie.group(1), dopasowanie.group(2)) else rok + 1
        okna.append((start, f"{koniec_rok}-{dopasowanie.group(3)}-{dopasowanie.group(4)}T23:59:59"))
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

_SCIEZKI_SLUZBOWE = re.compile(
    r"/(?:tag|tags|kategoria|category|categories|rubryka|thema|themen|tema|"
    r"author|autor|avtor|page|strona|seite|search|szukaj|suche|poisk|poshuk|"
    r"login|signin|register|subscribe|prenumerata|abo|cart|koszyk|wp-admin|"
    r"wp-login|wp-content|feed|rss|amp)(?:/|$)", re.I)


def _wyglada_na_tresc(url: str) -> bool:
    """Rough filter: is this an article rather than an index or an asset?"""
    if _NIE_TRESC.search(url):
        return False
    sciezka = urlparse(url).path.lower()
    if not sciezka or sciezka == "/":
        return False
    if _SCIEZKI_SLUZBOWE.search(sciezka):
        return False
    return True


def _wyglada_na_artykul(url: str) -> bool:
    """Stronger heuristic used when we have to guess without any selector."""
    if not _wyglada_na_tresc(url):
        return False
    sciezka = urlparse(url).path
    if re.search(r"/(?:19|20)\d{2}[/-]\d{1,2}", sciezka):       # /2015/05/...
        return True
    if re.search(r"[/-]\d{5,}", sciezka):                       # id in the address
        return True
    ostatni = sciezka.rstrip("/").rsplit("/", 1)[-1]
    if ostatni.count("-") >= 2 and len(ostatni) > 12:           # slug-with-words
        return True
    return len([c for c in sciezka.split("/") if c]) >= 3


def _link_absolutny(baza: str, href: str) -> str:
    return normalizuj_url(urljoin(baza, (href or "").strip()))


# --------------------------------------------------------------------------
# CMS detection
# --------------------------------------------------------------------------

def wykryj_cms(klient: KlientHTTP, baza: str, log: Log = lambda *_: None) -> str:
    """Best-effort guess. Only affects which adapter is tried first."""
    baza = korzen(baza)
    dane, odp = klient.pobierz_json(f"{baza}/wp-json/wp/v2/posts", params={"per_page": 1})
    if isinstance(dane, list) and odp.ok:
        return "wordpress"
    dane, odp = klient.pobierz_json(f"{baza}/jsonapi")
    if isinstance(dane, dict) and odp.ok and "data" in {*dane.keys(), "data"}:
        return "drupal"

    odp = klient.pobierz(baza)
    if odp.ok:
        tekst = odp.tekst[:200000].lower()
        naglowek = " ".join(f"{k}:{v}" for k, v in (odp.naglowki or {}).items()).lower()
        for nazwa, slady in (
            ("wordpress", ("wp-content", "wp-includes", "wp-json")),
            ("drupal", ("drupal-settings-json", "/sites/default/files", "x-generator: drupal")),
            ("joomla", ("/media/jui/", "joomla", "com_content")),
            ("ghost", ("ghost-sdk", "/ghost/api/")),
            ("typo3", ("typo3temp", "typo3conf")),
            ("blogger", ("blogger.com", "blogspot")),
        ):
            if any(slad in tekst or slad in naglowek for slad in slady):
                return nazwa
    return "unknown"


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
            dane, _ = klient.pobierz_json(f"{korzen(baza)}/wp-json/wp/v2/{taksonomia}",
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
        log(f"    WordPress taxonomies: {len(mapy['categories'])}+{len(mapy['tags'])} names")
    return mapy


def _post_na_kandydata(post: dict, mapy: Dict[str, Dict[int, str]], zrodlo: Zrodlo) -> Kandydat:
    tagi = list(zrodlo.tagi)
    for pole in ("categories", "tags"):
        for ident in post.get(pole) or []:
            nazwa = mapy.get(pole, {}).get(int(ident))
            if nazwa:
                tagi.append(nazwa)
    autorzy = [html_na_tekst(str(a["name"]))
               for a in ((post.get("_embedded") or {}).get("author") or [])
               if isinstance(a, dict) and a.get("name")]
    return Kandydat(
        url=normalizuj_url(post.get("link") or ""),
        tytul=html_na_tekst((post.get("title") or {}).get("rendered", "")),
        data=normalizuj_date(post.get("date_gmt") or post.get("date") or ""),
        autorzy=autorzy,
        tresc_html=(post.get("content") or {}).get("rendered", ""),
        zajawka=html_na_tekst((post.get("excerpt") or {}).get("rendered", "")),
        tagi_zrodla=tagi, skad="api", zrodlo=zrodlo.etykieta)


def z_wordpress(klient: KlientHTTP, zrodlo: Zrodlo, hasla: Sequence[str],
                log: Log, przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    mapy = _taksonomie_wp(klient, baza, log)
    okna = _okna_dat(zrodlo)
    wydane, widziane = 0, set()

    def zapytania() -> Iterator[dict]:
        podstawa = [{}] if (zrodlo.pelne_przemiatanie or not hasla) \
            else [{"search": h} for h in hasla]
        for typ in zrodlo.typy_wp or ["posts"]:
            for parametry in podstawa:
                if okna:
                    for po, przed in okna:
                        yield {"_typ": typ, "after": po, "before": przed, **parametry}
                else:
                    yield {"_typ": typ, **parametry}

    for parametry in zapytania():
        if przerwij() or wydane >= zrodlo.max_url:
            return
        typ = parametry.pop("_typ", "posts")
        etykieta = parametry.get("search") or parametry.get("after", "")[:7] or "everything"
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
                    log(f"    [api] {typ}/{etykieta}: no answer ({odp.status}) — skipping")
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
            naglowek = odp.naglowki.get("X-WP-TotalPages") \
                or odp.naglowki.get("x-wp-totalpages") or "1"
            try:
                stron_ogolem = int(naglowek)
            except ValueError:
                stron_ogolem = 1
            log(f"    [api] {typ}/{etykieta}: page {strona}/{stron_ogolem}, +{nowe} new")
            # Only X-WP-TotalPages ends the pagination: some sites cap per_page
            # below what we asked for, so a short page is not the last one.
            if strona >= stron_ogolem:
                break
            strona += 1


# --------------------------------------------------------------------------
# Drupal JSON:API
# --------------------------------------------------------------------------

def z_drupala(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
              przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    adres = f"{baza}/jsonapi/node/article"
    wydane, offset = 0, 0
    while wydane < zrodlo.max_url and offset < zrodlo.max_stron * 50:
        if przerwij():
            return
        dane, odp = klient.pobierz_json(adres, params={
            "page[limit]": 50, "page[offset]": offset, "sort": "-created"})
        if not isinstance(dane, dict) or not isinstance(dane.get("data"), list):
            if offset == 0:
                log(f"    [drupal] JSON:API unavailable ({odp.status})")
            return
        wpisy = dane["data"]
        if not wpisy:
            return
        nowe = 0
        for wpis in wpisy:
            atrybuty = wpis.get("attributes") or {}
            alias = ((atrybuty.get("path") or {}) or {}).get("alias") or ""
            url = normalizuj_url(baza + alias) if alias else ""
            if not url or not _pasuje_url(zrodlo, url):
                continue
            tresc = (atrybuty.get("body") or {}).get("processed") or ""
            nowe += 1
            wydane += 1
            yield Kandydat(url=url, tytul=html_na_tekst(atrybuty.get("title", "")),
                           data=normalizuj_date(atrybuty.get("created", "")),
                           tresc_html=tresc, tagi_zrodla=list(zrodlo.tagi),
                           skad="drupal", zrodlo=zrodlo.etykieta)
        log(f"    [drupal] offset {offset}: +{nowe} new")
        offset += 50


# --------------------------------------------------------------------------
# Sitemap
# --------------------------------------------------------------------------

def _tag_bez_ns(element) -> str:
    return element.tag.split("}")[-1].lower()


def _parsuj_sitemap(xml: str) -> Tuple[List[str], List[Tuple[str, str]]]:
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
        (mapy if nazwa == "sitemap" else adresy).append(
            loc if nazwa == "sitemap" else (loc, lastmod))
    return mapy, adresy


def z_sitemap(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
              przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    kandydaci_map = list(klient.mapy_z_robots(baza)) + [
        f"{baza}/wp-sitemap.xml", f"{baza}/sitemap_index.xml", f"{baza}/sitemap.xml",
        f"{baza}/sitemap-index.xml", f"{baza}/sitemap/sitemap-index.xml",
        f"{baza}/sitemap.xml.gz", f"{baza}/news-sitemap.xml",
    ]
    do_odwiedzenia = list(dict.fromkeys(kandydaci_map))
    odwiedzone, wydane = set(), 0
    lata = range(zrodlo.od_roku or 1990, (zrodlo.do_roku or 2100) + 1) \
        if (zrodlo.od_roku or zrodlo.do_roku) else None

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
            log(f"    [sitemap] {adres} → {len(mapy)} nested maps")
            do_odwiedzenia.extend(m for m in mapy if m not in odwiedzone)
        if adresy:
            log(f"    [sitemap] {adres} → {len(adresy)} addresses")
        for url, lastmod in adresy:
            url = normalizuj_url(url)
            if host_z_url(url) != host_z_url(baza):
                continue
            if not (_pasuje_url(zrodlo, url) and _wyglada_na_tresc(url)):
                continue
            data = normalizuj_date(lastmod)
            if lata and data[:4].isdigit() and int(data[:4]) not in lata:
                # the year in the address is often more reliable than lastmod
                rok_z_url = re.search(r"/((?:19|20)\d{2})/", url)
                if not (rok_z_url and int(rok_z_url.group(1)) in lata):
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
    kanaly = [f"{baza}/feed", f"{baza}/?feed=rss2", f"{baza}/rss", f"{baza}/rss.xml",
              f"{baza}/atom.xml", f"{baza}/feed/atom", f"{baza}/index.xml"]
    odp = klient.pobierz(baza)
    if odp.ok:
        zupa = BeautifulSoup(odp.tekst, "html.parser")
        for link in zupa.find_all("link", type=re.compile(r"rss|atom", re.I)):
            if link.get("href"):
                kanaly.insert(0, _link_absolutny(baza, link["href"]))

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
        log(f"    [rss] {kanal} → {len(wpisy)} entries")
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
# Result-link extraction (used by search and listing adapters)
# --------------------------------------------------------------------------

_SELEKTORY_WYNIKOW = (
    "article a[rel='bookmark']", "h2.entry-title a", "h3.entry-title a", "h1.entry-title a",
    "h2.post-title a", ".entry-title a", ".post-title a", ".search-result a[href]",
    "article h2 a", "article h3 a", "li.result a[href]", ".teaser a[href]",
    "main article a[href]", "[class*='result'] a[href]", "[class*='teaser'] h2 a")


def _linki_wynikow(zupa: BeautifulSoup, baza: str, selektor: str = "") -> List:
    """Article links from a results/listing page, from the most to the least specific."""
    if selektor:
        znalezione = zupa.select(selektor)
        if znalezione:
            return znalezione
    for kandydat in _SELEKTORY_WYNIKOW:
        znalezione = zupa.select(kandydat)
        if znalezione:
            return znalezione
    znalezione = [a for a in zupa.find_all("a", href=re.compile(r"[?&]p=\d+"))]
    if znalezione:
        return znalezione
    for artykul in zupa.find_all("article"):
        link = artykul.find("a", href=True)
        if link:
            znalezione.append(link)
    if znalezione:
        return znalezione
    # last resort: everything that looks like an article address
    return [a for a in zupa.find_all("a", href=True)
            if _wyglada_na_artykul(_link_absolutny(baza, a["href"]))]


def _wypelnij(szablon: str, haslo: str, strona: int, rok: Optional[int] = None) -> str:
    return (szablon.replace("{q}", quote_plus(haslo))
                   .replace("{query}", quote_plus(haslo))
                   .replace("{page}", str(strona))
                   .replace("{year}", str(rok or "")))


def _zbierz_ze_strony(klient: KlientHTTP, zrodlo: Zrodlo, adres: str, baza: str,
                      widziane: set, skad: str) -> Tuple[List[Kandydat], bool, str]:
    """Fetch one results page. Returns (candidates, has-next-page, message)."""
    odp = klient.pobierz(adres, uzyj_cache=False, zrodlo=zrodlo)
    if not odp.ok:
        return [], False, f"HTTP {odp.status} {odp.blad}".strip()
    zupa = BeautifulSoup(odp.tekst, "html.parser")
    kandydaci: List[Kandydat] = []
    for link in _linki_wynikow(zupa, baza, zrodlo.selektor_linkow):
        url = _link_absolutny(baza, link.get("href") or "")
        if not url or url in widziane or host_z_url(url) != host_z_url(baza):
            continue
        if not (_pasuje_url(zrodlo, url) and _wyglada_na_tresc(url)):
            continue
        widziane.add(url)
        kandydaci.append(Kandydat(url=url, tytul=link.get_text(" ", strip=True),
                                  tagi_zrodla=list(zrodlo.tagi), skad=skad,
                                  zrodlo=zrodlo.etykieta))
    if zrodlo.selektor_dalej:
        ma_dalej = bool(zupa.select_one(zrodlo.selektor_dalej))
    else:
        ma_dalej = bool(zupa.select_one(
            "a[rel='next'], a.next, .next a, .pagination a.next, .nav-previous a,"
            "[class*='pager'] a[class*='next']"))
    return kandydaci, ma_dalej, ""


#: Search-page templates tried when the user has not supplied one.
SZABLONY_SZUKANIA = (
    "{baza}/?s={q}&paged={page}",          # WordPress
    "{baza}/search?q={q}&page={page}",
    "{baza}/search/?q={q}&page={page}",
    "{baza}/szukaj?q={q}&page={page}",
    "{baza}/suche?q={q}&seite={page}",
    "{baza}/search?query={q}&page={page}",
    "{baza}/?s={q}",
)


def z_szukajki(klient: KlientHTTP, zrodlo: Zrodlo, hasla: Sequence[str], log: Log,
               przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    """The site's own search — via a supplied template or a discovered one."""
    baza = korzen(zrodlo.url)
    szablony = [zrodlo.szablon_szukania] if zrodlo.szablon_szukania else \
        [s.replace("{baza}", baza) for s in SZABLONY_SZUKANIA]

    dzialajacy = ""
    widziane, wydane = set(), 0
    for haslo in hasla or [""]:
        if przerwij() or wydane >= zrodlo.max_url:
            return
        szablony_do_proby = [dzialajacy] if dzialajacy else szablony
        for szablon in szablony_do_proby:
            strona = zrodlo.pierwsza_strona
            znalezione_dla_szablonu = 0
            while strona < zrodlo.pierwsza_strona + zrodlo.max_stron:
                if przerwij() or wydane >= zrodlo.max_url:
                    return
                adres = _wypelnij(szablon, haslo, strona)
                kandydaci, ma_dalej, blad = _zbierz_ze_strony(
                    klient, zrodlo, adres, baza, widziane, "search")
                if blad:
                    log(f"    [search] {adres}: {blad}")
                    break
                for kandydat in kandydaci:
                    wydane += 1
                    znalezione_dla_szablonu += 1
                    yield kandydat
                log(f"    [search] '{haslo}' page {strona}: +{len(kandydaci)}")
                if not kandydaci or not ma_dalej or "{page}" not in szablon:
                    break
                strona += 1
            if znalezione_dla_szablonu:
                if not dzialajacy:
                    dzialajacy = szablon
                    log(f"    [search] using template {szablon}")
                break


def z_listy(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
            przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    """A paginated archive/index page — bypasses the site's search entirely."""
    baza = korzen(zrodlo.url)
    szablon = zrodlo.szablon_listy
    if not szablon:
        log("    [listing] no listing_url template given")
        return
    lata = list(range(zrodlo.od_roku, zrodlo.do_roku + 1)) \
        if (zrodlo.od_roku and zrodlo.do_roku and "{year}" in szablon) else [None]

    widziane, wydane = set(), 0
    for rok in lata:
        strona = zrodlo.pierwsza_strona
        while strona < zrodlo.pierwsza_strona + zrodlo.max_stron:
            if przerwij() or wydane >= zrodlo.max_url:
                return
            adres = _wypelnij(szablon, "", strona, rok)
            kandydaci, ma_dalej, blad = _zbierz_ze_strony(
                klient, zrodlo, adres, baza, widziane, "listing")
            if blad:
                log(f"    [listing] {adres}: {blad}")
                break
            for kandydat in kandydaci:
                wydane += 1
                yield kandydat
            log(f"    [listing] {rok or ''} page {strona}: +{len(kandydaci)}")
            if not kandydaci or "{page}" not in szablon:
                break
            strona += 1


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------

def z_crawl(klient: KlientHTTP, zrodlo: Zrodlo, log: Log,
            przerwij: Callable[[], bool]) -> Iterator[Kandydat]:
    baza = korzen(zrodlo.url)
    kolejka: List[Tuple[str, int]] = [(normalizuj_url(zrodlo.url), 0)]
    odwiedzone, wydane = set(), 0
    while kolejka and not przerwij() and wydane < zrodlo.max_url:
        url, glebokosc = kolejka.pop(0)
        if url in odwiedzone:
            continue
        odwiedzone.add(url)
        odp = klient.pobierz(url, zrodlo=zrodlo)
        if not odp.ok:
            continue
        if _wyglada_na_tresc(url) and _pasuje_url(zrodlo, url):
            wydane += 1
            yield Kandydat(url=url, tagi_zrodla=list(zrodlo.tagi), skad="crawl",
                           zrodlo=zrodlo.etykieta)
        if glebokosc >= zrodlo.glebokosc:
            continue
        zupa = BeautifulSoup(odp.tekst, "html.parser")
        for link in zupa.find_all("a", href=True):
            nowy = _link_absolutny(url, link["href"])
            if nowy and nowy not in odwiedzone and host_z_url(nowy) == host_z_url(baza) \
                    and not _NIE_TRESC.search(nowy):
                kolejka.append((nowy, glebokosc + 1))
        if len(odwiedzone) % 25 == 0:
            log(f"    [crawl] visited {len(odwiedzone)}, queued {len(kolejka)}")


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

def kandydaci(klient: KlientHTTP, zrodlo: Zrodlo, hasla: Sequence[str], log: Log,
              przerwij: Callable[[], bool] = lambda: False) -> Iterator[Kandydat]:
    tryb = _NORMALIZUJ_TRYB.get((zrodlo.tryb or "auto").lower(), "auto")

    if tryb == "urls" or (tryb == "auto" and zrodlo.lista_url):
        for url in zrodlo.lista_url or [zrodlo.url]:
            url = normalizuj_url(url)
            if url and _pasuje_url(zrodlo, url):
                yield Kandydat(url=url, tagi_zrodla=list(zrodlo.tagi), skad="urls",
                               zrodlo=zrodlo.etykieta)
        return

    proste = {"wordpress": lambda: z_wordpress(klient, zrodlo, hasla, log, przerwij),
              "drupal": lambda: z_drupala(klient, zrodlo, log, przerwij),
              "sitemap": lambda: z_sitemap(klient, zrodlo, log, przerwij),
              "rss": lambda: z_rss(klient, zrodlo, log, przerwij),
              "search": lambda: z_szukajki(klient, zrodlo, hasla, log, przerwij),
              "listing": lambda: z_listy(klient, zrodlo, log, przerwij),
              "crawl": lambda: z_crawl(klient, zrodlo, log, przerwij)}
    if tryb in proste:
        yield from proste[tryb]()
        return

    # ---- auto ----
    if zrodlo.szablon_listy:
        log(f"  {zrodlo.etykieta}: using the supplied listing template")
        yield from z_listy(klient, zrodlo, log, przerwij)
        return

    log(f"  detecting how to reach {zrodlo.etykieta}…")
    cms = wykryj_cms(klient, zrodlo.url, log)
    log(f"    → looks like: {cms}")

    kolejnosc: List[Tuple[str, Callable[[], Iterator[Kandydat]]]] = []
    if cms == "wordpress":
        kolejnosc.append(("WordPress REST API",
                          lambda: z_wordpress(klient, zrodlo, hasla, log, przerwij)))
    elif cms == "drupal":
        kolejnosc.append(("Drupal JSON:API", lambda: z_drupala(klient, zrodlo, log, przerwij)))
    kolejnosc += [
        ("sitemap", lambda: z_sitemap(klient, zrodlo, log, przerwij)),
        ("RSS feed", lambda: z_rss(klient, zrodlo, log, przerwij)),
        ("site search", lambda: z_szukajki(klient, zrodlo, hasla, log, przerwij)),
        ("link crawl", lambda: z_crawl(klient, zrodlo, log, przerwij)),
    ]

    for nazwa, funkcja in kolejnosc:
        cokolwiek = False
        for kandydat in funkcja():
            cokolwiek = True
            yield kandydat
        if cokolwiek:
            log(f"    → {nazwa} was enough")
            return
        log(f"    → {nazwa}: nothing")
