# -*- coding: utf-8 -*-
"""Pulling the article text and the bibliographic metadata out of HTML.

Metadata is collected in a cascade, from the most to the least reliable source:
JSON-LD (schema.org) → OpenGraph → <meta name=…> → Dublin Core → HTML heuristics.
That is what lets a Zotero citation appear complete without hand-filling.

Dates are recognised in Polish, English, German, Russian and Ukrainian.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

MIESIACE_PL = {
    "stycznia": 1, "styczeń": 1, "lutego": 2, "luty": 2, "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4, "maja": 5, "maj": 5, "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7, "sierpnia": 8, "sierpień": 8, "września": 9, "wrzesień": 9,
    "października": 10, "październik": 10, "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12,
}
MIESIACE_DE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}
MIESIACE_RU = {
    "января": 1, "январь": 1, "февраля": 2, "февраль": 2, "марта": 3, "март": 3,
    "апреля": 4, "апрель": 4, "мая": 5, "май": 5, "июня": 6, "июнь": 6,
    "июля": 7, "июль": 7, "августа": 8, "август": 8, "сентября": 9, "сентябрь": 9,
    "октября": 10, "октябрь": 10, "ноября": 11, "ноябрь": 11, "декабря": 12, "декабрь": 12,
}
MIESIACE_UA = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}
MIESIACE_EN = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MIESIACE = {**MIESIACE_PL, **MIESIACE_DE, **MIESIACE_UA, **MIESIACE_RU, **MIESIACE_EN}

_SMIECI = ("script", "style", "noscript", "nav", "footer", "header", "aside",
           "form", "iframe", "svg", "button", "template")

_SELEKTORY_TRESCI = (
    "div.entry-content", "div.post-content", "div.article-content", "div.td-post-content",
    "div.single-content", "div.content-area article", "[itemprop='articleBody']",
    "article .content", "article", "main", "#content", ".post", ".entry")

_SELEKTORY_SMIECI = (
    ".comments-area", "#comments", ".comment-respond", ".sharedaddy", ".share",
    ".related-posts", ".wp-block-latest-posts", ".sidebar", "#sidebar",
    ".breadcrumbs", ".breadcrumb", ".cookie", ".menu", ".nav-links", ".post-navigation")


@dataclass
class Metadane:
    tytul: str = ""
    autorzy: List[str] = field(default_factory=list)
    data: str = ""              # ISO: RRRR-MM-DD lub RRRR-MM lub RRRR
    data_modyfikacji: str = ""
    nazwa_serwisu: str = ""
    wydawca: str = ""
    jezyk: str = ""
    opis: str = ""
    slowa_kluczowe: List[str] = field(default_factory=list)
    rubryka: str = ""
    typ: str = ""               # article / blogPost / webpage
    url_kanoniczny: str = ""

    def jako_dict(self) -> dict:
        return dict(self.__dict__)


# --------------------------------------------------------------------------
# Daty
# --------------------------------------------------------------------------

def normalizuj_date(surowa: Optional[str]) -> str:
    """Reduce assorted date spellings to ISO. Returns '' when nothing fits."""
    if not surowa:
        return ""
    s = str(surowa).strip()
    if not s:
        return ""

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"

    m = re.search(r"\b(\d{1,2})\.?\s+([^\W\d_]+)\s+(\d{4})\b", s, re.UNICODE)
    if m:
        miesiac = _MIESIACE.get(m.group(2).lower())
        if miesiac:
            return f"{int(m.group(3)):04d}-{miesiac:02d}-{int(m.group(1)):02d}"

    m = re.search(r"\b([^\W\d_]+)\s+(\d{1,2}),?\s+(\d{4})\b", s, re.UNICODE)
    if m:
        miesiac = _MIESIACE.get(m.group(1).lower())
        if miesiac:
            return f"{int(m.group(3)):04d}-{miesiac:02d}-{int(m.group(2)):02d}"

    m = re.search(r"\b(19|20)\d{2}\b", s)
    if m:
        return m.group(0)
    return ""


def rok_z_daty(data: str) -> str:
    m = re.match(r"(\d{4})", data or "")
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# Treść
# --------------------------------------------------------------------------

def _wyczysc(soup: BeautifulSoup) -> None:
    for tag in soup(list(_SMIECI)):
        tag.decompose()
    for selektor in _SELEKTORY_SMIECI:
        for tag in soup.select(selektor):
            tag.decompose()


def _gestosc(element) -> int:
    if element is None:
        return 0
    akapity = element.find_all(["p", "li", "blockquote"])
    if akapity:
        return sum(len(a.get_text(" ", strip=True)) for a in akapity)
    return len(element.get_text(" ", strip=True)) // 3


def wyciagnij_tekst(html: str, zupa: Optional[BeautifulSoup] = None) -> str:
    """Article text: prefer the usual content containers, fall back to density."""
    zupa = zupa or BeautifulSoup(html or "", "html.parser")
    kopia = BeautifulSoup(str(zupa), "html.parser")
    _wyczysc(kopia)

    najlepszy, najlepszy_wynik = None, 0
    for selektor in _SELEKTORY_TRESCI:
        for kandydat in kopia.select(selektor):
            wynik = _gestosc(kandydat)
            if wynik > najlepszy_wynik:
                najlepszy, najlepszy_wynik = kandydat, wynik

    if najlepszy is None or najlepszy_wynik < 120:
        body = kopia.body or kopia
        if _gestosc(body) > najlepszy_wynik:
            najlepszy = body

    tekst = (najlepszy or kopia).get_text("\n", strip=True)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    tekst = re.sub(r"[ \t ]{2,}", " ", tekst)
    return tekst.strip()


def html_na_tekst(html: str) -> str:
    """Flat text out of an HTML fragment (e.g. a REST API field)."""
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)).strip()


# --------------------------------------------------------------------------
# Metadane
# --------------------------------------------------------------------------

def _json_ld(zupa: BeautifulSoup) -> List[dict]:
    obiekty: List[dict] = []
    for tag in zupa.find_all("script", type=lambda v: v and "ld+json" in v):
        surowe = tag.string or tag.get_text() or ""
        try:
            dane = json.loads(surowe)
        except ValueError:
            surowe = re.sub(r",\s*([}\]])", r"\1", surowe)
            try:
                dane = json.loads(surowe)
            except ValueError:
                continue
        kolejka = dane if isinstance(dane, list) else [dane]
        while kolejka:
            element = kolejka.pop(0)
            if not isinstance(element, dict):
                continue
            if "@graph" in element and isinstance(element["@graph"], list):
                kolejka.extend(element["@graph"])
            obiekty.append(element)
    return obiekty


def _nazwy(wartosc) -> List[str]:
    wynik: List[str] = []
    if isinstance(wartosc, str):
        wynik = [wartosc]
    elif isinstance(wartosc, dict):
        if wartosc.get("name"):
            wynik = [str(wartosc["name"])]
    elif isinstance(wartosc, list):
        for element in wartosc:
            wynik.extend(_nazwy(element))
    return [w.strip() for w in wynik if w and w.strip()]


def _meta(zupa: BeautifulSoup, attrs: Optional[dict] = None, **kryteria) -> str:
    """Zawartość <meta …>. Można podać atrybuty jako słownik albo jako kwargi."""
    szukane = dict(attrs or {})
    szukane.update(kryteria)
    tag = zupa.find("meta", attrs=szukane)
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return ""


def wyciagnij_metadane(html: str, url: str = "") -> Metadane:
    zupa = BeautifulSoup(html or "", "html.parser")
    meta = Metadane()

    # --- JSON-LD ---
    for obiekt in _json_ld(zupa):
        typ = obiekt.get("@type") or ""
        typy = typ if isinstance(typ, list) else [typ]
        typy = [str(t) for t in typy]
        if any(t in ("Article", "NewsArticle", "BlogPosting", "Report", "WebPage") for t in typy):
            meta.tytul = meta.tytul or str(obiekt.get("headline") or obiekt.get("name") or "").strip()
            meta.autorzy = meta.autorzy or _nazwy(obiekt.get("author"))
            meta.data = meta.data or normalizuj_date(obiekt.get("datePublished") or obiekt.get("dateCreated"))
            meta.data_modyfikacji = meta.data_modyfikacji or normalizuj_date(obiekt.get("dateModified"))
            meta.opis = meta.opis or str(obiekt.get("description") or "").strip()
            wydawcy = _nazwy(obiekt.get("publisher"))
            meta.wydawca = meta.wydawca or (wydawcy[0] if wydawcy else "")
            slowa = obiekt.get("keywords")
            if slowa and not meta.slowa_kluczowe:
                if isinstance(slowa, str):
                    meta.slowa_kluczowe = [s.strip() for s in slowa.split(",") if s.strip()]
                elif isinstance(slowa, list):
                    meta.slowa_kluczowe = [str(s).strip() for s in slowa if str(s).strip()]
            meta.rubryka = meta.rubryka or str(obiekt.get("articleSection") or "").strip()
            if not meta.typ and any(t in ("BlogPosting", "NewsArticle", "Article") for t in typy):
                meta.typ = "blogPost" if "BlogPosting" in typy else "article"
        if "WebSite" in typy and not meta.nazwa_serwisu:
            meta.nazwa_serwisu = str(obiekt.get("name") or "").strip()
        if "Organization" in typy and not meta.wydawca:
            meta.wydawca = str(obiekt.get("name") or "").strip()

    # --- OpenGraph / meta ---
    meta.tytul = meta.tytul or _meta(zupa, property="og:title") or _meta(zupa, attrs={"name": "twitter:title"})
    meta.nazwa_serwisu = meta.nazwa_serwisu or _meta(zupa, property="og:site_name")
    meta.opis = meta.opis or _meta(zupa, property="og:description") or _meta(zupa, attrs={"name": "description"})
    meta.data = meta.data or normalizuj_date(
        _meta(zupa, property="article:published_time")
        or _meta(zupa, attrs={"name": "article:published_time"})
        or _meta(zupa, attrs={"itemprop": "datePublished"})
        or _meta(zupa, attrs={"name": "date"})
        or _meta(zupa, attrs={"name": "DC.date"})
        or _meta(zupa, attrs={"name": "dcterms.date"})
        or _meta(zupa, attrs={"name": "pubdate"}))
    meta.data_modyfikacji = meta.data_modyfikacji or normalizuj_date(
        _meta(zupa, property="article:modified_time"))
    if not meta.autorzy:
        kandydaci = [
            _meta(zupa, attrs={"name": "author"}),
            _meta(zupa, property="article:author"),
            _meta(zupa, attrs={"name": "DC.creator"}),
            _meta(zupa, attrs={"name": "dcterms.creator"}),
        ]
        meta.autorzy = [k for k in kandydaci if k and not k.startswith("http")]
    if not meta.autorzy:
        for selektor in (".author .fn", ".author-name", "a[rel='author']", ".entry-author",
                         "[itemprop='author']", ".byline"):
            tag = zupa.select_one(selektor)
            if tag:
                tekst = tag.get_text(" ", strip=True)
                tekst = re.sub(r"^(autor|napisał[ay]?|by|von)[:\s]+", "", tekst, flags=re.I)
                if 2 < len(tekst) < 80:
                    meta.autorzy = [tekst]
                    break

    if not meta.slowa_kluczowe:
        surowe = _meta(zupa, attrs={"name": "keywords"})
        if surowe:
            meta.slowa_kluczowe = [s.strip() for s in surowe.split(",") if s.strip()]
    if not meta.rubryka:
        meta.rubryka = _meta(zupa, property="article:section")

    # --- tytuł i data z HTML ---
    if not meta.tytul:
        h1 = zupa.find("h1")
        if h1:
            meta.tytul = h1.get_text(" ", strip=True)
    if not meta.tytul and zupa.title:
        meta.tytul = zupa.title.get_text(strip=True)
    if not meta.data:
        czas = zupa.find("time")
        if czas:
            meta.data = normalizuj_date(czas.get("datetime") or czas.get_text(" ", strip=True))
    if not meta.data:
        for selektor in (".entry-date", ".post-date", ".published", ".date"):
            tag = zupa.select_one(selektor)
            if tag:
                meta.data = normalizuj_date(tag.get_text(" ", strip=True))
                if meta.data:
                    break
    if not meta.data and url:
        m = re.search(r"/((?:19|20)\d{2})/(\d{2})(?:/(\d{2}))?/", url)
        if m:
            meta.data = "-".join(filter(None, [m.group(1), m.group(2), m.group(3)]))

    # --- język, kanoniczny URL, serwis ---
    html_tag = zupa.find("html")
    if html_tag and html_tag.get("lang"):
        meta.jezyk = html_tag["lang"].strip()[:5]
    kanoniczny = zupa.find("link", rel=lambda v: v and "canonical" in v)
    if kanoniczny and kanoniczny.get("href"):
        meta.url_kanoniczny = kanoniczny["href"].strip()
    if not meta.nazwa_serwisu and url:
        meta.nazwa_serwisu = urlparse(url).netloc.replace("www.", "")
    meta.wydawca = meta.wydawca or meta.nazwa_serwisu
    meta.typ = meta.typ or "webpage"

    # tytuł bywa sklejony z nazwą serwisu („Tytuł - Serwis”)
    if meta.tytul and meta.nazwa_serwisu:
        wzor = re.compile(r"\s*[|\-–—»]\s*" + re.escape(meta.nazwa_serwisu) + r"\s*$", re.I)
        meta.tytul = wzor.sub("", meta.tytul).strip() or meta.tytul

    meta.tytul = re.sub(r"\s+", " ", meta.tytul or "").strip()
    return meta


def dzis_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")
