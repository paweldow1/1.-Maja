# -*- coding: utf-8 -*-
"""Język zapytań: operatory boolowskie, frazy, pola, sąsiedztwo (NEAR).

Składnia (polska i angielska działają wymiennie)::

    "1 maja" I (Żoliborz LUB "Józef Robotnik") NIE "1 maja 1982"
    tytuł:pochód ORAZ tekst:sztandar
    Wałęsa BLISKO/10 msza
    =Solidarność            – dosłownie, bez odmiany
    ~msza                   – wymuś odmianę (domyślne)
    ^prac                   – tryb rdzenia: prac|pracownik|pracować…
    solidarn*               – wildcard użytkownika

Domyślny operator między sąsiednimi terminami to I (AND); można zmienić na LUB.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .fleksja import FlexOptions, kompiluj, przykladowe_formy, wzorzec_terminu

# --------------------------------------------------------------------------
# Dokument
# --------------------------------------------------------------------------

#: Kolejność sklejania pól. Pierwsze trzy tworzą „treść” – to, co domyślnie
#: przeszukujemy. Tagi i adres są dostępne, ale tylko na wyraźne życzenie
#: (``tagi:``, ``url:``), żeby trafieniem nie okazał się sam tag WordPressa.
POLA = ("tytul", "tekst", "autor", "tagi", "url")
POLA_TRESCI = ("tytul", "tekst", "autor")

_ALIASY_POL = {
    "tytuł": "tytul", "tytul": "tytul", "title": "tytul", "t": "tytul",
    "tekst": "tekst", "text": "tekst", "treść": "tekst", "tresc": "tekst",
    "url": "url", "link": "url", "adres": "url",
    "autor": "autor", "author": "autor",
    "tag": "tagi", "tagi": "tagi", "tags": "tagi", "kategoria": "tagi",
    "treść": "tresc", "tresc": "tresc",
    "wszystko": "wszystko", "any": "wszystko", "all": "wszystko",
}

_SLOWO_RE = re.compile(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+")


class Dokument:
    """Tekst strony rozbity na pola, z indeksem słów potrzebnym dla NEAR."""

    def __init__(self, tytul: str = "", tekst: str = "", url: str = "",
                 autor: str = "", tagi: Sequence[str] = ()):
        self.pola: Dict[str, str] = {
            "tytul": tytul or "",
            "tekst": tekst or "",
            "url": url or "",
            "autor": autor or "",
            "tagi": " ".join(tagi or ()),
        }
        # „wszystko” to konkatenacja – offsety liczymy względem niej,
        # dzięki czemu NEAR działa też między polami.
        self._sklejka_pola: List[Tuple[str, int]] = []
        kawalki = []
        pozycja = 0
        for nazwa in POLA:
            wartosc = self.pola[nazwa]
            self._sklejka_pola.append((nazwa, pozycja))
            kawalki.append(wartosc)
            pozycja += len(wartosc) + 2
        self.pola["wszystko"] = "\n\n".join(kawalki)
        koniec_tresci = len("\n\n".join(kawalki[:len(POLA_TRESCI)]))
        self.pola["tresc"] = self.pola["wszystko"][:koniec_tresci]

        self._poczatki_slow: List[int] = []
        for m in _SLOWO_RE.finditer(self.pola["wszystko"]):
            self._poczatki_slow.append(m.start())

    def indeks_slowa(self, offset: int) -> int:
        return bisect.bisect_right(self._poczatki_slow, offset) - 1

    def offset_pola(self, nazwa: str) -> int:
        for pole, poz in self._sklejka_pola:
            if pole == nazwa:
                return poz
        return 0

    def nazwa_pola(self, offset: int) -> str:
        """Nazwa pola, w którym leży dany znak (tytul / tekst / autor / tagi / url)."""
        wynik = self._sklejka_pola[0][0]
        for nazwa, poczatek in self._sklejka_pola:
            if poczatek > offset:
                break
            wynik = nazwa
        return wynik

    def granice_pola(self, offset: int) -> Tuple[int, int]:
        """Początek i koniec pola, w którym leży dany znak.

        Dzięki temu cytat wokół trafienia nie przecieka do sklejonych dalej
        metadanych (autor, tagi, adres) — w przypisie wyglądałoby to fatalnie.
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
    pole: str = "wszystko"

    def jako_dict(self) -> dict:
        return {"termin": self.termin, "forma": self.forma,
                "start": self.start, "koniec": self.koniec, "pole": self.pole}


# --------------------------------------------------------------------------
# Drzewo zapytania
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
    tryb: Optional[str] = None          # nadpisanie trybu fleksji
    opcje: FlexOptions = field(default_factory=FlexOptions)
    _regex: Optional["re.Pattern[str]"] = None

    def opcje_efektywne(self) -> FlexOptions:
        return self.opcje.replace(mode=self.tryb) if self.tryb else self.opcje

    def regex(self) -> "re.Pattern[str]":
        if self._regex is None:
            self._regex = kompiluj(self.tekst, self.opcje_efektywne())
        return self._regex

    def wzorzec(self) -> str:
        return wzorzec_terminu(self.tekst, self.opcje_efektywne())

    def formy(self, limit: int = 60) -> List[str]:
        return przykladowe_formy(self.tekst, self.opcje_efektywne(), limit)

    def ocen(self, dok: Dokument) -> Tuple[bool, List[Trafienie]]:
        haystack = dok.pola.get(self.pole, "")
        przesuniecie = 0 if self.pole in ("wszystko", "tresc") else dok.offset_pola(self.pole)
        trafienia = [
            Trafienie(self.tekst, m.group(0), m.start() + przesuniecie,
                      m.end() + przesuniecie, self.pole)
            for m in self.regex().finditer(haystack)
        ]
        wykluczone = {w.lower() for w in self.opcje_efektywne().wyklucz}
        if wykluczone:
            trafienia = [t for t in trafienia if t.forma.lower() not in wykluczone]
        return bool(trafienia), trafienia

    def terminy(self) -> List["Termin"]:
        return [self]

    def opis(self) -> str:
        prefiks = f"{self.pole}:" if self.pole not in ("wszystko", "tresc") else ""
        return f"{prefiks}„{self.tekst}”"


@dataclass
class Oraz(Wezel):
    dzieci: List[Wezel]

    def ocen(self, dok):
        wszystkie: List[Trafienie] = []
        for d in self.dzieci:
            ok, traf = d.ocen(dok)
            if not ok:
                return False, []
            wszystkie.extend(traf)
        return True, wszystkie

    def terminy(self):
        return [t for d in self.dzieci for t in d.terminy()]

    def opis(self):
        return "(" + " I ".join(d.opis() for d in self.dzieci) + ")"


@dataclass
class Lub(Wezel):
    dzieci: List[Wezel]

    def ocen(self, dok):
        wszystkie: List[Trafienie] = []
        ok_any = False
        for d in self.dzieci:
            ok, traf = d.ocen(dok)
            if ok:
                ok_any = True
                wszystkie.extend(traf)
        return ok_any, wszystkie

    def terminy(self):
        return [t for d in self.dzieci for t in d.terminy()]

    def opis(self):
        return "(" + " LUB ".join(d.opis() for d in self.dzieci) + ")"


@dataclass
class Nie(Wezel):
    dziecko: Wezel

    def ocen(self, dok):
        ok, _ = self.dziecko.ocen(dok)
        return (not ok), []

    def terminy(self):
        return []          # terminy wykluczające nie trafiają do tagów

    def opis(self):
        return "NIE " + self.dziecko.opis()


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
                ib = dok.indeks_slowa(b.start)
                if abs(ia - ib) <= self.dystans:
                    pary.extend([a, b])
        return bool(pary), pary

    def terminy(self):
        return self.lewy.terminy() + self.prawy.terminy()

    def opis(self):
        return f"({self.lewy.opis()} BLISKO/{self.dystans} {self.prawy.opis()})"


@dataclass
class Zawsze(Wezel):
    """Puste zapytanie – wszystko pasuje (tryb „zbierz cały korpus”)."""

    def ocen(self, dok):
        return True, []

    def opis(self):
        return "(wszystko)"


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class BladZapytania(ValueError):
    pass


_OP_ORAZ = {"and", "i", "oraz", "&&", "&"}
_OP_LUB = {"or", "lub", "albo", "||", "|"}
_OP_NIE = {"not", "nie", "bez", "!"}

_TOKEN_RE = re.compile(
    r"""
    (?P<spacja>\s+)
  | (?P<nawias_o>\()
  | (?P<nawias_z>\))
  | (?P<pole_fraza>[\wĄĆĘŁŃÓŚŹŻąćęłńóśźż]+:(?:"[^"]*"|„[^”]*”|'[^']*'))
  | (?P<fraza>"[^"]*"|„[^”]*”|'[^']*')
  | (?P<blisko>(?:NEAR|BLISKO)\s*/\s*\d+|~\d+)
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
        m = _TOKEN_RE.match(tekst, pozycja)
        if not m:
            raise BladZapytania(f"Nie rozumiem zapytania od znaku {pozycja}: {tekst[pozycja:pozycja+20]!r}")
        pozycja = m.end()
        rodzaj = m.lastgroup
        wartosc = m.group(0)
        if rodzaj == "spacja":
            continue
        tokeny.append(_Token(rodzaj or "slowo", wartosc))
    return tokeny


class _Parser:
    def __init__(self, tokeny: List[_Token], opcje: FlexOptions, domyslny_operator: str = "I"):
        self.tokeny = tokeny
        self.i = 0
        self.opcje = opcje
        self.domyslny = domyslny_operator.upper()

    # --- pomocnicze ---
    def podglad(self) -> Optional[_Token]:
        return self.tokeny[self.i] if self.i < len(self.tokeny) else None

    def zjedz(self) -> _Token:
        tok = self.tokeny[self.i]
        self.i += 1
        return tok

    def _to_operator(self, tok: Optional[_Token], zbior: set) -> bool:
        return bool(tok) and tok.typ in ("slowo", "symbol") and tok.wartosc.lower() in zbior

    # --- gramatyka ---
    def parsuj(self) -> Wezel:
        if not self.tokeny:
            return Zawsze()
        wezel = self.wyrazenie_lub()
        if self.i < len(self.tokeny):
            raise BladZapytania(f"Niedomknięty nawias albo nadmiarowy token: {self.tokeny[self.i].wartosc!r}")
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
            tok = self.podglad()
            if tok is None or tok.typ == "nawias_z":
                break
            if self._to_operator(tok, _OP_LUB):
                break
            if self._to_operator(tok, _OP_ORAZ):
                self.zjedz()
                dzieci.append(self.wyrazenie_blisko())
                continue
            # sąsiedztwo bez operatora → operator domyślny
            if self.domyslny == "LUB":
                break
            dzieci.append(self.wyrazenie_blisko())
        if len(dzieci) == 1:
            return dzieci[0]
        return Oraz(dzieci)

    def wyrazenie_blisko(self) -> Wezel:
        lewy = self.zaprzeczenie()
        while True:
            tok = self.podglad()
            if tok is None or tok.typ != "blisko":
                break
            self.zjedz()
            dystans = int(re.search(r"\d+", tok.wartosc).group(0))
            prawy = self.zaprzeczenie()
            lewy = Blisko(lewy, prawy, dystans)
        return lewy

    def zaprzeczenie(self) -> Wezel:
        tok = self.podglad()
        if self._to_operator(tok, _OP_NIE):
            self.zjedz()
            return Nie(self.zaprzeczenie())
        if tok and tok.typ == "slowo" and tok.wartosc.startswith("-") and len(tok.wartosc) > 1:
            tok.wartosc = tok.wartosc[1:]
            return Nie(self.zaprzeczenie())
        return self.podstawowe()

    def podstawowe(self) -> Wezel:
        tok = self.podglad()
        if tok is None:
            raise BladZapytania("Zapytanie urwane – brakuje terminu.")
        if tok.typ == "nawias_o":
            self.zjedz()
            wezel = self.wyrazenie_lub()
            if not self.podglad() or self.podglad().typ != "nawias_z":
                raise BladZapytania("Brak zamykającego nawiasu.")
            self.zjedz()
            return wezel
        if tok.typ == "nawias_z":
            raise BladZapytania("Nieoczekiwany nawias zamykający.")
        self.zjedz()
        return self._termin(tok)

    def _termin(self, tok: _Token) -> Termin:
        surowy = tok.wartosc
        pole = "tresc"
        tryb: Optional[str] = None

        if tok.typ == "pole_fraza":
            nazwa, _, reszta = surowy.partition(":")
            if nazwa.lower() in _ALIASY_POL:
                pole = _ALIASY_POL[nazwa.lower()]
                tekst = reszta[1:-1]
            else:
                tekst = surowy
        elif tok.typ == "fraza":
            tekst = surowy[1:-1]
        else:
            # pole:reszta (dwukropek nie może być częścią http://)
            m = re.match(r"^([\wĄĆĘŁŃÓŚŹŻąćęłńóśźż]+):(?!//)(.*)$", surowy)
            if m and m.group(1).lower() in _ALIASY_POL and m.group(2):
                pole = _ALIASY_POL[m.group(1).lower()]
                surowy = m.group(2)
                if surowy.startswith(('"', "„", "'")):
                    surowy = surowy.strip("\"„”'")
            tekst = surowy

        if tekst.startswith("="):
            tryb, tekst = "dokladnie", tekst[1:]
        elif tekst.startswith("~"):
            tryb, tekst = "fleksja", tekst[1:]
        elif tekst.startswith("^"):
            tryb, tekst = "rdzen", tekst[1:]

        if not tekst.strip():
            raise BladZapytania(f"Pusty termin w zapytaniu ({tok.wartosc!r}).")
        return Termin(tekst.strip(), pole=pole, tryb=tryb, opcje=self.opcje)


def parsuj(zapytanie: str, opcje: FlexOptions | None = None,
           domyslny_operator: str = "I") -> Wezel:
    """Zamienia tekst zapytania na drzewo do oceniania."""
    return _Parser(_tokenizuj(zapytanie or ""), opcje or FlexOptions(),
                   domyslny_operator).parsuj()


# --------------------------------------------------------------------------
# Cytaty z kontekstem (KWIC)
# --------------------------------------------------------------------------

def cytaty(dok: Dokument, trafienia: Sequence[Trafienie], okno: int = 220,
           maks: int = 5) -> List[dict]:
    """Fragmenty tekstu wokół trafień, scalone gdy na siebie zachodzą."""
    tekst = dok.pola["wszystko"]
    zakresy: List[Tuple[int, int, List[Trafienie]]] = []
    for t in sorted(trafienia, key=lambda x: x.start):
        lewa, prawa = dok.granice_pola(t.start)
        od, do = max(lewa, t.start - okno), min(prawa, t.koniec + okno)
        if zakresy and od <= zakresy[-1][1]:
            p, k, lista = zakresy[-1]
            zakresy[-1] = (p, max(k, do), lista + [t])
        else:
            zakresy.append((od, do, [t]))
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
            "pole": dok.nazwa_pola(od),
        })
    # Fragmenty z treści i tytułu są dla przypisu cenniejsze niż z adresu czy tagów.
    waga = {"tekst": 0, "tytul": 1, "autor": 2, "tagi": 3, "url": 4}
    wynik.sort(key=lambda c: waga.get(c.get("pole", ""), 5))
    return wynik
