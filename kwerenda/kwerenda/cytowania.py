# -*- coding: utf-8 -*-
"""Przypis bibliograficzny: rekord → Zotero / RIS / CSL-JSON / BibTeX / CSV / Obsidian.

Jeden wspólny rekord (:class:`Rekord`) jest tłumaczony na wszystkie formaty, żeby
przypis, tagi i notatka z cytatem były wszędzie takie same.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .ekstrakcja import dzis_iso, rok_z_daty

# Typy Zotero, które mają sens dla stron WWW.
TYPY_ZOTERO = {
    "webpage": {"pojemnik": "websiteTitle", "ris": "ELEC", "csl": "webpage", "bib": "online"},
    "blogPost": {"pojemnik": "blogTitle", "ris": "BLOG", "csl": "post-weblog", "bib": "online"},
    "newspaperArticle": {"pojemnik": "publicationTitle", "ris": "NEWS", "csl": "article-newspaper", "bib": "article"},
    "magazineArticle": {"pojemnik": "publicationTitle", "ris": "MGZN", "csl": "article-magazine", "bib": "article"},
    "document": {"pojemnik": "publisher", "ris": "GEN", "csl": "document", "bib": "misc"},
    "report": {"pojemnik": "institution", "ris": "RPRT", "csl": "report", "bib": "techreport"},
}

_SLOWA_POMIJANE = {
    "the", "a", "an", "der", "die", "das", "ein", "eine", "le", "la", "les",
    "w", "we", "i", "oraz", "na", "do", "o", "z", "ze", "po", "od", "przy",
    "dla", "pod", "nad", "przed", "jak", "to", "się", "nie", "był", "była",
}


@dataclass
class Rekord:
    """Znormalizowany rekord bibliograficzny + ślad kwerendy."""

    url: str = ""
    tytul: str = ""
    autorzy: List[str] = field(default_factory=list)
    data: str = ""
    serwis: str = ""
    wydawca: str = ""
    jezyk: str = ""
    typ: str = "webpage"
    opis: str = ""
    tagi: List[str] = field(default_factory=list)
    terminy: List[str] = field(default_factory=list)
    cytaty: List[dict] = field(default_factory=list)
    notatka: str = ""
    citekey: str = ""
    data_dostepu: str = field(default_factory=dzis_iso)

    @classmethod
    def z_trafienia(cls, trafienie: dict) -> "Rekord":
        meta = trafienie.get("meta") or {}
        return cls(
            url=trafienie.get("url", ""),
            tytul=trafienie.get("tytul", "") or trafienie.get("url", ""),
            autorzy=list(trafienie.get("autorzy") or []),
            data=trafienie.get("data", "") or "",
            serwis=trafienie.get("serwis", "") or "",
            wydawca=trafienie.get("wydawca", "") or trafienie.get("serwis", "") or "",
            jezyk=trafienie.get("jezyk", "") or "",
            typ=trafienie.get("typ") or "webpage",
            opis=meta.get("opis", "") or "",
            tagi=list(trafienie.get("tagi") or []),
            terminy=list(trafienie.get("terminy") or []),
            cytaty=list(trafienie.get("cytaty") or []),
            notatka=trafienie.get("notatka", "") or "",
            citekey=trafienie.get("citekey", "") or "",
            data_dostepu=meta.get("data_dostepu") or dzis_iso(),
        )


# --------------------------------------------------------------------------
# Klucze cytowań (styl Better BibTeX: nazwiskoRokPierwszeSlowo)
# --------------------------------------------------------------------------

def ascii_slug(tekst: str) -> str:
    tekst = (tekst or "").replace("ł", "l").replace("Ł", "L")
    tekst = unicodedata.normalize("NFD", tekst)
    tekst = "".join(c for c in tekst if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "", tekst)


def nazwisko(autor: str) -> str:
    autor = (autor or "").strip()
    if not autor:
        return ""
    if "," in autor:
        return autor.split(",")[0].strip()
    czesci = [c for c in autor.split() if c]
    return czesci[-1] if czesci else ""


def zbuduj_citekey(rekord: Rekord, zajete: Optional[set] = None) -> str:
    baza_autor = nazwisko(rekord.autorzy[0]) if rekord.autorzy else ""
    if not baza_autor:
        baza_autor = re.sub(r"^www\.", "", rekord.serwis or "").split(".")[0]
    baza_autor = ascii_slug(baza_autor).lower()[:18] or "anon"

    rok = rok_z_daty(rekord.data) or "bd"

    slowa = [w for w in re.findall(r"[^\W\d_]+", rekord.tytul or "", re.UNICODE)
             if w.lower() not in _SLOWA_POMIJANE and len(w) > 2]
    tytul_slowo = ascii_slug(slowa[0]).lower() if slowa else ""

    klucz = f"{baza_autor}{rok}{tytul_slowo}"[:40] or "zrodlo"
    if zajete is None:
        return klucz
    kandydat, sufiks = klucz, ord("a")
    while kandydat in zajete:
        kandydat = f"{klucz}{chr(sufiks)}"
        sufiks += 1
    zajete.add(kandydat)
    return kandydat


def nadaj_citekeys(rekordy: Sequence[Rekord]) -> List[Rekord]:
    zajete: set = set()
    for rekord in rekordy:
        if rekord.citekey:
            zajete.add(rekord.citekey)
    for rekord in rekordy:
        if not rekord.citekey:
            rekord.citekey = zbuduj_citekey(rekord, zajete)
    return list(rekordy)


# --------------------------------------------------------------------------
# Wspólne kawałki
# --------------------------------------------------------------------------

def _twórcy_zotero(autorzy: Sequence[str]) -> List[dict]:
    wynik = []
    for autor in autorzy:
        autor = (autor or "").strip()
        if not autor:
            continue
        if "," in autor:
            nazw, _, imie = autor.partition(",")
            wynik.append({"creatorType": "author", "lastName": nazw.strip(),
                          "firstName": imie.strip()})
            continue
        czesci = autor.split()
        if len(czesci) == 1:
            wynik.append({"creatorType": "author", "name": czesci[0], "fieldMode": 1})
        else:
            wynik.append({"creatorType": "author", "firstName": " ".join(czesci[:-1]),
                          "lastName": czesci[-1]})
    return wynik


def notatka_html(rekord: Rekord) -> str:
    """Notatka do Zotero: cytaty z kontekstem + ślad kwerendy."""
    czesci = ["<h2>Kwerenda — dopasowane fragmenty</h2>"]
    if rekord.terminy:
        czesci.append("<p><b>Trafione terminy:</b> " + ", ".join(
            _escape(t) for t in rekord.terminy) + "</p>")
    for cytat in rekord.cytaty:
        formy = ", ".join(cytat.get("formy", []))
        czesci.append(f"<blockquote><p>{_escape(cytat.get('fragment', ''))}</p>"
                      f"<p><i>formy: {_escape(formy)}</i></p></blockquote>")
    if rekord.notatka:
        czesci.append(f"<p><b>Notatka własna:</b> {_escape(rekord.notatka)}</p>")
    czesci.append(f'<p><a href="{_escape(rekord.url)}">{_escape(rekord.url)}</a> '
                  f"(dostęp: {rekord.data_dostepu})</p>")
    return "\n".join(czesci)


def _escape(tekst: str) -> str:
    return (str(tekst or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _abstrakt(rekord: Rekord) -> str:
    if rekord.opis:
        return rekord.opis
    for cytat in rekord.cytaty:
        if cytat.get("pole") in ("tekst", "tytul", None):
            return cytat.get("fragment", "")
    if rekord.cytaty:
        return rekord.cytaty[0].get("fragment", "")
    return ""


# --------------------------------------------------------------------------
# Zotero (format API/konektora)
# --------------------------------------------------------------------------

def do_zotero(rekord: Rekord, z_notatka: bool = True,
              kolekcje: Optional[List[str]] = None) -> dict:
    profil = TYPY_ZOTERO.get(rekord.typ, TYPY_ZOTERO["webpage"])
    element = {
        "itemType": rekord.typ if rekord.typ in TYPY_ZOTERO else "webpage",
        "title": rekord.tytul or rekord.url,
        "creators": _twórcy_zotero(rekord.autorzy),
        "url": rekord.url,
        "date": rekord.data,
        "accessDate": rekord.data_dostepu,
        "language": rekord.jezyk,
        "abstractNote": _abstrakt(rekord),
        "tags": [{"tag": t} for t in dict.fromkeys(rekord.tagi) if t],
        "extra": _extra(rekord),
    }
    pojemnik = profil["pojemnik"]
    element[pojemnik] = rekord.serwis or rekord.wydawca
    if rekord.typ in ("newspaperArticle", "magazineArticle"):
        element["publicationTitle"] = rekord.serwis or rekord.wydawca
    if z_notatka and (rekord.cytaty or rekord.notatka):
        element["notes"] = [{"itemType": "note", "note": notatka_html(rekord)}]
    if kolekcje:
        element["collections"] = list(kolekcje)
    return {k: v for k, v in element.items() if v not in ("", [], None)}


def _extra(rekord: Rekord) -> str:
    linie = []
    if rekord.citekey:
        linie.append(f"Citation Key: {rekord.citekey}")
    if rekord.terminy:
        linie.append("Kwerenda: " + ", ".join(rekord.terminy))
    return "\n".join(linie)


# --------------------------------------------------------------------------
# RIS – najpewniejsza droga do Zotero przez plik (KW → tagi, N1 → notatka)
# --------------------------------------------------------------------------

def do_ris(rekordy: Sequence[Rekord]) -> str:
    linie: List[str] = []
    for rekord in rekordy:
        profil = TYPY_ZOTERO.get(rekord.typ, TYPY_ZOTERO["webpage"])
        linie.append(f"TY  - {profil['ris']}")
        linie.append(f"TI  - {_jedna_linia(rekord.tytul)}")
        for autor in rekord.autorzy:
            linie.append(f"AU  - {_ris_autor(autor)}")
        rok = rok_z_daty(rekord.data)
        if rok:
            linie.append(f"PY  - {rok}")
        if rekord.data:
            linie.append("DA  - " + rekord.data.replace("-", "/"))
        if rekord.serwis:
            linie.append(f"T2  - {_jedna_linia(rekord.serwis)}")
        if rekord.wydawca:
            linie.append(f"PB  - {_jedna_linia(rekord.wydawca)}")
        if rekord.jezyk:
            linie.append(f"LA  - {rekord.jezyk}")
        abstrakt = _abstrakt(rekord)
        if abstrakt:
            linie.append(f"AB  - {_jedna_linia(abstrakt)}")
        for tag in dict.fromkeys(rekord.tagi):
            if tag:
                linie.append(f"KW  - {_jedna_linia(tag)}")
        if rekord.url:
            linie.append(f"UR  - {rekord.url}")
        linie.append(f"Y2  - {rekord.data_dostepu.replace('-', '/')}")
        notatka = _notatka_plaska(rekord)
        if notatka:
            linie.append(f"N1  - {notatka}")
        if rekord.citekey:
            linie.append(f"ID  - {rekord.citekey}")
        linie.append("ER  - ")
        linie.append("")
    return "\r\n".join(linie)


def _ris_autor(autor: str) -> str:
    autor = (autor or "").strip()
    if "," in autor or " " not in autor:
        return autor
    czesci = autor.split()
    return f"{czesci[-1]}, {' '.join(czesci[:-1])}"


def _jedna_linia(tekst: str) -> str:
    return re.sub(r"\s+", " ", str(tekst or "")).strip()


def _notatka_plaska(rekord: Rekord) -> str:
    czesci = []
    if rekord.terminy:
        czesci.append("Trafione terminy: " + ", ".join(rekord.terminy))
    for cytat in rekord.cytaty:
        czesci.append("„" + _jedna_linia(cytat.get("fragment", "")) + "”")
    if rekord.notatka:
        czesci.append("Notatka: " + _jedna_linia(rekord.notatka))
    return " | ".join(czesci)


# --------------------------------------------------------------------------
# CSL-JSON
# --------------------------------------------------------------------------

def _czesci_daty(data: str) -> Optional[List[List[int]]]:
    if not data:
        return None
    kawalki = [int(k) for k in re.findall(r"\d+", data)[:3]]
    return [kawalki] if kawalki else None


def do_csl(rekordy: Sequence[Rekord]) -> List[dict]:
    wynik = []
    for rekord in rekordy:
        profil = TYPY_ZOTERO.get(rekord.typ, TYPY_ZOTERO["webpage"])
        wpis: Dict[str, object] = {
            "id": rekord.citekey or rekord.url,
            "type": profil["csl"],
            "title": rekord.tytul,
            "URL": rekord.url,
            "container-title": rekord.serwis,
            "publisher": rekord.wydawca,
            "language": rekord.jezyk,
            "abstract": _abstrakt(rekord),
            "note": _notatka_plaska(rekord),
            "keyword": ", ".join(dict.fromkeys(rekord.tagi)),
            "accessed": {"date-parts": _czesci_daty(rekord.data_dostepu)},
        }
        czesci = _czesci_daty(rekord.data)
        if czesci:
            wpis["issued"] = {"date-parts": czesci}
        autorzy = []
        for autor in rekord.autorzy:
            if "," in autor:
                nazw, _, imie = autor.partition(",")
                autorzy.append({"family": nazw.strip(), "given": imie.strip()})
            else:
                czesci_imienia = autor.split()
                if len(czesci_imienia) > 1:
                    autorzy.append({"family": czesci_imienia[-1],
                                    "given": " ".join(czesci_imienia[:-1])})
                elif czesci_imienia:
                    autorzy.append({"literal": autor})
        if autorzy:
            wpis["author"] = autorzy
        wynik.append({k: v for k, v in wpis.items() if v not in ("", [], None, {})})
    return wynik


# --------------------------------------------------------------------------
# BibTeX (Better BibTeX: pole keywords → tagi w Zotero)
# --------------------------------------------------------------------------

_BIB_ZNAKI = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
              "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _bib_escape(tekst: str) -> str:
    return "".join(_BIB_ZNAKI.get(z, z) for z in str(tekst or ""))


def do_bibtex(rekordy: Sequence[Rekord]) -> str:
    bloki = []
    for rekord in rekordy:
        profil = TYPY_ZOTERO.get(rekord.typ, TYPY_ZOTERO["webpage"])
        pola = [
            ("author", " and ".join(_ris_autor(a) for a in rekord.autorzy)),
            ("title", rekord.tytul),
            ("organization", rekord.serwis),
            ("year", rok_z_daty(rekord.data)),
            ("date", rekord.data),
            ("url", rekord.url),
            ("urldate", rekord.data_dostepu),
            ("language", rekord.jezyk),
            ("abstract", _abstrakt(rekord)),
            ("keywords", ", ".join(dict.fromkeys(rekord.tagi))),
            ("note", _notatka_plaska(rekord)),
        ]
        tresc = ",\n".join(f"  {nazwa} = {{{_bib_escape(_jedna_linia(wartosc))}}}"
                           for nazwa, wartosc in pola if wartosc)
        bloki.append(f"@{profil['bib']}{{{rekord.citekey or 'zrodlo'},\n{tresc}\n}}")
    return "\n\n".join(bloki) + "\n"


# --------------------------------------------------------------------------
# CSV i Markdown (Obsidian)
# --------------------------------------------------------------------------

KOLUMNY_CSV = ["citekey", "tytul", "autorzy", "data", "serwis", "url", "typ", "jezyk",
               "tagi", "terminy", "cytat", "data_dostepu", "notatka"]


def do_csv(rekordy: Sequence[Rekord]) -> str:
    bufor = io.StringIO()
    zapis = csv.DictWriter(bufor, fieldnames=KOLUMNY_CSV, extrasaction="ignore")
    zapis.writeheader()
    for rekord in rekordy:
        zapis.writerow({
            "citekey": rekord.citekey,
            "tytul": rekord.tytul,
            "autorzy": "; ".join(rekord.autorzy),
            "data": rekord.data,
            "serwis": rekord.serwis,
            "url": rekord.url,
            "typ": rekord.typ,
            "jezyk": rekord.jezyk,
            "tagi": "; ".join(rekord.tagi),
            "terminy": "; ".join(rekord.terminy),
            "cytat": " || ".join(_jedna_linia(c.get("fragment", "")) for c in rekord.cytaty),
            "data_dostepu": rekord.data_dostepu,
            "notatka": rekord.notatka,
        })
    return bufor.getvalue()


def do_markdown(rekord: Rekord) -> str:
    """Notatka źródłowa do Obsidiana, z linkiem [[@citekey]] jak w Better BibTeX."""
    tagi_yaml = "\n".join(f"  - {t}" for t in dict.fromkeys(rekord.tagi) if t)
    linie = [
        "---",
        f'title: "{rekord.tytul.replace(chr(34), chr(39))}"',
        f"citekey: {rekord.citekey}",
        f"url: {rekord.url}",
        f"data: {rekord.data}",
        f"serwis: {rekord.serwis}",
        f"autorzy: [{', '.join(rekord.autorzy)}]",
        f"dostep: {rekord.data_dostepu}",
        "tags:" if tagi_yaml else "tags: []",
    ]
    if tagi_yaml:
        linie.append(tagi_yaml)
    linie += ["---", "", f"# {rekord.tytul}", "", f"Źródło: [[@{rekord.citekey}]] — <{rekord.url}>", ""]
    if rekord.terminy:
        linie += [f"**Trafione terminy:** {', '.join(rekord.terminy)}", ""]
    for cytat in rekord.cytaty:
        linie += ["> " + _jedna_linia(cytat.get("fragment", "")), ""]
    if rekord.notatka:
        linie += ["## Notatka", "", rekord.notatka, ""]
    return "\n".join(linie)


def nazwa_pliku(rekord: Rekord) -> str:
    baza = rekord.citekey or ascii_slug(rekord.tytul)[:40] or "zrodlo"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", baza)
