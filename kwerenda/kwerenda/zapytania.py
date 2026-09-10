# -*- coding: utf-8 -*-
"""Query language: boolean operators, phrases, fields, proximity, truncation.

Syntax (English operators are canonical; Polish ones work as aliases)::

    "1 May" AND (Żoliborz* OR "Józef Robotnik"*)
    title:strike* AND text:banner*
    Wałęsa NEAR/10 mass
    Streik* NOT Warnstreik
    solidarn**                  – truncation: stem plus anything

Term forms:

===============  =========================================================
``strike``       exact word
``strike*``      inflected forms in every enabled language
``strike**``     truncation (stem + anything, catches derivatives)
``"..."``        phrase; put the star after the closing quote to inflect it
===============  =========================================================
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .morfologia import (TRYB_DOKLADNY, TRYB_ODMIANA, TRYB_RDZEN, Opcje,
                         formy_wg_jezykow, kompiluj, wzorzec_terminu)

#: Concatenation order. The first three make up "content" — what we search by
#: default. Tags and the address are reachable only on request (``tags:``,
#: ``url:``), so that a bare WordPress tag is not mistaken for a real hit.
POLA = ("tytul", "tekst", "autor", "tagi", "url")
POLA_TRESCI = ("tytul", "tekst", "autor")

_ALIASY_POL = {
    # English
    "title": "tytul", "headline": "tytul", "t": "tytul",
    "text": "tekst", "body": "tekst", "content": "tekst", "full": "tekst",
    "author": "autor", "by": "autor", "creator": "autor",
    "url": "url", "link": "url", "address": "url",
    "tag": "tagi", "tags": "tagi", "category": "tagi", "keyword": "tagi",
    "all": "wszystko", "any": "wszystko", "everything": "wszystko",
    # Polish
    "tytuł": "tytul", "tytul": "tytul",
    "tekst": "tekst", "treść": "tekst", "tresc": "tekst",
    "autor": "autor", "adres": "url", "tagi": "tagi", "kategoria": "tagi",
    "wszystko": "wszystko",
}

_SLOWO_RE = re.compile(r"[^\W_]+", re.UNICODE)


class Dokument:
    """A page split into fields, with the word index that NEAR needs."""

    def __init__(self, tytul: str = "", tekst: str = "", url: str = "",
                 autor: str = "", tagi: Sequence[str] = (), jezyk: str = ""):
        self.jezyk = jezyk
        self.pola: Dict[str, str] = {
            "tytul": tytul or "", "tekst": tekst or "", "url": url or "",
            "autor": autor or "", "tagi": " ".join(tagi or ()),
        }
        self._sklejka_pola: List[Tuple[str, int]] = []
        kawalki, pozycja = [], 0
        for nazwa in POLA:
            wartosc = self.pola[nazwa]
            self._sklejka_pola.append((nazwa, pozycja))
            kawalki.append(wartosc)
            pozycja += len(wartosc) + 2
        self.pola["wszystko"] = "\n\n".join(kawalki)
        self.pola["tresc"] = self.pola["wszystko"][
            :len("\n\n".join(kawalki[:len(POLA_TRESCI)]))]

        self._poczatki_slow = [m.start() for m in _SLOWO_RE.finditer(self.pola["wszystko"])]

    def indeks_slowa(self, offset: int) -> int:
        return bisect.bisect_right(self._poczatki_slow, offset) - 1

    def offset_pola(self, nazwa: str) -> int:
        for pole, poz in self._sklejka_pola:
            if pole == nazwa:
                return poz
        return 0

    def nazwa_pola(self, offset: int) -> str:
        wynik = self._sklejka_pola[0][0]
        for nazwa, poczatek in self._sklejka_pola:
            if poczatek > offset:
                break
            wynik = nazwa
        return wynik

    def granice_pola(self, offset: int) -> Tuple[int, int]:
        """Start and end of the field containing this character.

        Keeps a quotation from bleeding into the metadata concatenated after it
        (author, tags, address) — that would look terrible in a citation.
        """
        poprzednie = 0
        for _, poczatek in self._sklejka_pola:
            if poczatek > offset:
                return poprzednie, poczatek - 2
            poprzednie = poczatek
        return poprzednie, len(self.pola["wszystko"])


@dataclass
class Trafienie:
    termin: str
    forma: str
    start: int
    koniec: int
    pole: str = "tresc"

    def jako_dict(self) -> dict:
        return {"term": self.termin, "form": self.forma, "start": self.start,
                "end": self.koniec, "field": self.pole}


# --------------------------------------------------------------------------
# Query tree
# --------------------------------------------------------------------------

class Wezel:
    def ocen(self, dok: Dokument) -> Tuple[bool, List[Trafienie]]:
        raise NotImplementedError

    def terminy(self) -> List["Termin"]:
        return []

    def opis(self) -> str:
        return ""


@dataclass
class Termin(Wezel):
    tekst: str
    pole: str = "tresc"
    tryb: str = TRYB_DOKLADNY
    opcje: Opcje = field(default_factory=Opcje)
    _regex: Optional["re.Pattern[str]"] = None

    def regex(self) -> "re.Pattern[str]":
        if self._regex is None:
            self._regex = kompiluj(self.tekst, self.opcje, self.tryb)
        return self._regex

    def wzorzec(self) -> str:
        return wzorzec_terminu(self.tekst, self.opcje, self.tryb)

    def formy(self, limit: int = 28) -> Dict[str, List[str]]:
        return formy_wg_jezykow(self.tekst, self.opcje, self.tryb, limit)

    def ocen(self, dok: Dokument) -> Tuple[bool, List[Trafienie]]:
        haystack = dok.pola.get(self.pole, "")
        przesuniecie = 0 if self.pole in ("wszystko", "tresc") else dok.offset_pola(self.pole)
        trafienia = [
            Trafienie(self.tekst, m.group(0), m.start() + przesuniecie,
                      m.end() + przesuniecie, self.pole)
            for m in self.regex().finditer(haystack)
        ]
        wykluczone = {w.lower() for w in self.opcje.wyklucz}
        if wykluczone:
            trafienia = [t for t in trafienia if t.forma.lower() not in wykluczone]
        return bool(trafienia), trafienia

    def terminy(self) -> List["Termin"]:
        return [self]

    def opis(self) -> str:
        prefiks = f"{_nazwa_pola_en(self.pole)}:" if self.pole not in ("wszystko", "tresc") else ""
        gwiazdki = {TRYB_ODMIANA: "*", TRYB_RDZEN: "**"}.get(self.tryb, "")
        return f"{prefiks}“{self.tekst}”{gwiazdki}"


def _nazwa_pola_en(pole: str) -> str:
    return {"tytul": "title", "tekst": "text", "autor": "author",
            "tagi": "tags", "url": "url"}.get(pole, pole)


@dataclass
class Oraz(Wezel):
    dzieci: List[Wezel]

    def ocen(self, dok):
        wszystkie: List[Trafienie] = []
        for dziecko in self.dzieci:
            ok, trafienia = dziecko.ocen(dok)
            if not ok:
                return False, []
            wszystkie.extend(trafienia)
        return True, wszystkie

    def terminy(self):
        return [t for d in self.dzieci for t in d.terminy()]

    def opis(self):
        return "(" + " AND ".join(d.opis() for d in self.dzieci) + ")"


@dataclass
class Lub(Wezel):
    dzieci: List[Wezel]

    def ocen(self, dok):
        wszystkie, ok_any = [], False
        for dziecko in self.dzieci:
            ok, trafienia = dziecko.ocen(dok)
            if ok:
                ok_any = True
                wszystkie.extend(trafienia)
        return ok_any, wszystkie

    def terminy(self):
        return [t for d in self.dzieci for t in d.terminy()]

    def opis(self):
        return "(" + " OR ".join(d.opis() for d in self.dzieci) + ")"


@dataclass
class Nie(Wezel):
    dziecko: Wezel

    def ocen(self, dok):
        ok, _ = self.dziecko.ocen(dok)
        return (not ok), []

    def terminy(self):
        return []          # excluded terms must not become tags

    def opis(self):
        return "NOT " + self.dziecko.opis()


@dataclass
class Blisko(Wezel):
    lewy: Wezel
    prawy: Wezel
    dystans: int = 10

    def ocen(self, dok):
        ok_l, traf_l = self.lewy.ocen(dok)
        ok_p, traf_p = self.prawy.ocen(dok)
        if not (ok_l and ok_p):
            return False, []
        pary: List[Trafienie] = []
        for a in traf_l:
            ia = dok.indeks_slowa(a.start)
            for b in traf_p:
                if abs(ia - dok.indeks_slowa(b.start)) <= self.dystans:
                    pary.extend([a, b])
        return bool(pary), pary

    def terminy(self):
        return self.lewy.terminy() + self.prawy.terminy()

    def opis(self):
        return f"({self.lewy.opis()} NEAR/{self.dystans} {self.prawy.opis()})"


@dataclass
class Zawsze(Wezel):
    """Empty query — everything matches (corpus-sweep mode)."""

    def ocen(self, dok):
        return True, []

    def opis(self):
        return "(everything)"


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class BladZapytania(ValueError):
    pass


_OP_ORAZ = {"and", "&&", "&", "i", "oraz"}
_OP_LUB = {"or", "||", "|", "lub", "albo"}
_OP_NIE = {"not", "!", "nie", "bez"}

_TOKEN_RE = re.compile(
    r"""
    (?P<spacja>\s+)
  | (?P<nawias_o>\()
  | (?P<nawias_z>\))
  | (?P<blisko>(?:NEAR|BLISKO|W)\s*/\s*\d+|~\d+)
  | (?P<pole_fraza>[^\W\d_]+:(?:"[^"]*"|„[^”]*”|'[^']*')\*{0,2})
  | (?P<fraza>(?:"[^"]*"|„[^”]*”|'[^']*')\*{0,2})
  | (?P<symbol>&&|\|\||&|\||!)
  | (?P<slowo>[^\s()"„”']+)
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass
class _Token:
    typ: str
    wartosc: str


def _tokenizuj(tekst: str) -> List[_Token]:
    tokeny: List[_Token] = []
    pozycja = 0
    while pozycja < len(tekst):
        dopasowanie = _TOKEN_RE.match(tekst, pozycja)
        if not dopasowanie:
            raise BladZapytania(
                f"Cannot parse the query from character {pozycja}: "
                f"{tekst[pozycja:pozycja + 20]!r}")
        pozycja = dopasowanie.end()
        if dopasowanie.lastgroup == "spacja":
            continue
        tokeny.append(_Token(dopasowanie.lastgroup or "slowo", dopasowanie.group(0)))
    return tokeny


class _Parser:
    def __init__(self, tokeny: List[_Token], opcje: Opcje, domyslny_operator: str = "AND"):
        self.tokeny = tokeny
        self.i = 0
        self.opcje = opcje
        self.domyslny = domyslny_operator.upper()

    def podglad(self) -> Optional[_Token]:
        return self.tokeny[self.i] if self.i < len(self.tokeny) else None

    def zjedz(self) -> _Token:
        token = self.tokeny[self.i]
        self.i += 1
        return token

    @staticmethod
    def _to_operator(token: Optional[_Token], zbior: set) -> bool:
        return bool(token) and token.typ in ("slowo", "symbol") \
            and token.wartosc.lower() in zbior

    # --- grammar ---
    def parsuj(self) -> Wezel:
        if not self.tokeny:
            return Zawsze()
        wezel = self.wyrazenie_lub()
        if self.i < len(self.tokeny):
            raise BladZapytania(
                f"Unbalanced parenthesis or stray token: {self.tokeny[self.i].wartosc!r}")
        return wezel

    def wyrazenie_lub(self) -> Wezel:
        dzieci = [self.wyrazenie_oraz()]
        while self._to_operator(self.podglad(), _OP_LUB):
            self.zjedz()
            dzieci.append(self.wyrazenie_oraz())
        return dzieci[0] if len(dzieci) == 1 else Lub(dzieci)

    def wyrazenie_oraz(self) -> Wezel:
        dzieci = [self.wyrazenie_blisko()]
        while True:
            token = self.podglad()
            if token is None or token.typ == "nawias_z" or self._to_operator(token, _OP_LUB):
                break
            if self._to_operator(token, _OP_ORAZ):
                self.zjedz()
                dzieci.append(self.wyrazenie_blisko())
                continue
            if self.domyslny == "OR":
                break
            dzieci.append(self.wyrazenie_blisko())     # adjacency = default operator
        return dzieci[0] if len(dzieci) == 1 else Oraz(dzieci)

    def wyrazenie_blisko(self) -> Wezel:
        lewy = self.zaprzeczenie()
        while True:
            token = self.podglad()
            if token is None or token.typ != "blisko":
                break
            self.zjedz()
            dystans = int(re.search(r"\d+", token.wartosc).group(0))
            lewy = Blisko(lewy, self.zaprzeczenie(), dystans)
        return lewy

    def zaprzeczenie(self) -> Wezel:
        token = self.podglad()
        if self._to_operator(token, _OP_NIE):
            self.zjedz()
            return Nie(self.zaprzeczenie())
        if token and token.typ == "slowo" and token.wartosc.startswith("-") \
                and len(token.wartosc) > 1:
            token.wartosc = token.wartosc[1:]
            return Nie(self.zaprzeczenie())
        return self.podstawowe()

    def podstawowe(self) -> Wezel:
        token = self.podglad()
        if token is None:
            raise BladZapytania("Query ends unexpectedly — a term is missing.")
        if token.typ == "nawias_o":
            self.zjedz()
            wezel = self.wyrazenie_lub()
            if not self.podglad() or self.podglad().typ != "nawias_z":
                raise BladZapytania("Missing closing parenthesis.")
            self.zjedz()
            return wezel
        if token.typ == "nawias_z":
            raise BladZapytania("Unexpected closing parenthesis.")
        self.zjedz()
        return self._termin(token)

    # --- one term ---
    def _termin(self, token: _Token) -> Termin:
        surowy = token.wartosc
        pole = "tresc"
        tryb: Optional[str] = None

        if token.typ == "pole_fraza":
            nazwa, _, reszta = surowy.partition(":")
            if nazwa.lower() in _ALIASY_POL:
                pole = _ALIASY_POL[nazwa.lower()]
                surowy = reszta
        elif token.typ == "slowo":
            dopasowanie = re.match(r"^([^\W\d_]+):(?!//)(.*)$", surowy)
            if dopasowanie and dopasowanie.group(1).lower() in _ALIASY_POL \
                    and dopasowanie.group(2):
                pole = _ALIASY_POL[dopasowanie.group(1).lower()]
                surowy = dopasowanie.group(2)

        # trailing stars decide the matching mode
        if surowy.endswith("**"):
            tryb, surowy = TRYB_RDZEN, surowy[:-2]
        elif surowy.endswith("*"):
            tryb, surowy = TRYB_ODMIANA, surowy[:-1]

        if surowy[:1] in ('"', "„", "'"):
            surowy = surowy.strip("\"„”'")

        # explicit prefixes still work, and win over the stars
        if surowy.startswith("="):
            tryb, surowy = TRYB_DOKLADNY, surowy[1:]
        elif surowy.startswith("~"):
            tryb, surowy = TRYB_ODMIANA, surowy[1:]
        elif surowy.startswith("^"):
            tryb, surowy = TRYB_RDZEN, surowy[1:]

        tekst = surowy.strip().strip("\"„”'").strip()
        if not tekst:
            raise BladZapytania(f"Empty term in the query ({token.wartosc!r}).")

        if tryb is None:
            tryb = TRYB_ODMIANA if self.opcje.rozszerzaj_wszystko else TRYB_DOKLADNY
        return Termin(tekst, pole=pole, tryb=tryb, opcje=self.opcje)


def parsuj(zapytanie: str, opcje: Optional[Opcje] = None,
           domyslny_operator: str = "AND") -> Wezel:
    """Turn query text into an evaluable tree."""
    return _Parser(_tokenizuj(zapytanie or ""), opcje or Opcje(),
                   domyslny_operator).parsuj()


# --------------------------------------------------------------------------
# Keyword in context
# --------------------------------------------------------------------------

def cytaty(dok: Dokument, trafienia: Sequence[Trafienie], okno: int = 220,
           maks: int = 5) -> List[dict]:
    """Snippets around the matches, merged where they overlap."""
    tekst = dok.pola["wszystko"]
    zakresy: List[Tuple[int, int, List[Trafienie]]] = []
    for trafienie in sorted(trafienia, key=lambda x: x.start):
        lewa, prawa = dok.granice_pola(trafienie.start)
        od = max(lewa, trafienie.start - okno)
        do = min(prawa, trafienie.koniec + okno)
        if zakresy and od <= zakresy[-1][1]:
            poczatek, koniec, lista = zakresy[-1]
            zakresy[-1] = (poczatek, max(koniec, do), lista + [trafienie])
        else:
            zakresy.append((od, do, [trafienie]))
        if len(zakresy) > maks * 3:
            break

    wynik = []
    for od, do, lista in zakresy[:maks]:
        lewa, prawa = dok.granice_pola(od)
        fragment = tekst[od:do].strip()
        if od > lewa:
            fragment = "…" + fragment
        if do < prawa:
            fragment = fragment + "…"
        wynik.append({
            "fragment": re.sub(r"\s+", " ", fragment),
            "formy": sorted({t.forma for t in lista}),
            "terminy": sorted({t.termin for t in lista}),
            "pole": _nazwa_pola_en(dok.nazwa_pola(od)),
        })
    waga = {"text": 0, "title": 1, "author": 2, "tags": 3, "url": 4}
    wynik.sort(key=lambda c: waga.get(c.get("pole", ""), 5))
    return wynik
