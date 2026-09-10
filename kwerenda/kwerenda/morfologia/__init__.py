# -*- coding: utf-8 -*-
"""Morphological matching across languages.

A search term can be written three ways:

===============  ==========================================================
``strike``       exact word (case- and, optionally, diacritic-insensitive)
``strike*``      inflected forms — *Streiks*, *страйку*, *strajkujących*
``strike**``     truncation: the stem plus anything at all, however long
===============  ==========================================================

For each term the engine picks the languages whose script matches the term
(Cyrillic terms are never expanded with German endings) and builds one regular
expression covering all of them:

    (word boundary) STEM+alternations ENDING (word boundary)

Supported out of the box: Polish, English, German, Russian, Ukrainian.
Adding a language means adding a table in :mod:`kwerenda.morfologia.jezyki` —
no code changes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .jezyki import DOMYSLNE, JEZYKI, Jezyk

TRYB_DOKLADNY = "exact"
TRYB_ODMIANA = "morph"
TRYB_RDZEN = "stem"
TRYBY = (TRYB_DOKLADNY, TRYB_ODMIANA, TRYB_RDZEN)

_CYRYLICA = re.compile(r"[Ѐ-ӿ]")
_LITERA = r"[^\W\d_]"

GRANICA_L = r"(?<![^\W_])"
GRANICA_P = r"(?![^\W_])"

# Separator inside a phrase: spaces, non-breaking space, hyphen, comma, dot, slash.
_SEP = r"[\s ]*[-–—,./]?[\s ]*"


@dataclass
class Opcje:
    """Matching options shared by every term of one query."""

    jezyki: Tuple[str, ...] = tuple(DOMYSLNE)
    rozszerzaj_wszystko: bool = False   # treat every term as if it ended with *
    bez_ogonkow: bool = False           # "Zoliborz" matches "Żoliborz", "Munchen" → "München"
    luz: int = 6                        # how many endings the ** preview shows
    wyklucz: Tuple[str, ...] = ()       # surface forms to reject

    def replace(self, **kw) -> "Opcje":
        dane = dict(self.__dict__)
        dane.update(kw)
        return Opcje(**dane)

    def lista_jezykow(self) -> List[Jezyk]:
        wybrane = [JEZYKI[k] for k in self.jezyki if k in JEZYKI]
        return wybrane or [JEZYKI[k] for k in DOMYSLNE]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def bez_ogonkow(tekst: str) -> str:
    """Strip diacritics: ł→l, ż→z, ä→a, ї→i."""
    tekst = tekst.replace("ł", "l").replace("Ł", "L").replace("ß", "ss")
    rozlozone = unicodedata.normalize("NFD", tekst)
    return "".join(c for c in rozlozone if unicodedata.category(c) != "Mn")


def pismo_slowa(slowo: str) -> str:
    return "cyrillic" if _CYRYLICA.search(slowo or "") else "latin"


def jezyki_dla(slowo: str, opcje: Opcje) -> List[Jezyk]:
    """Languages worth trying for this word — script decides."""
    pismo = pismo_slowa(slowo)
    pasujace = [j for j in opcje.lista_jezykow() if j.pismo == pismo]
    if pasujace:
        return pasujace
    return [j for j in JEZYKI.values() if j.pismo == pismo] or list(JEZYKI.values())


def _klasa_znaku(znak: str, jezyk: Jezyk, fold: bool) -> str:
    warianty = set()
    if fold and znak in jezyk.fold:
        warianty |= set(jezyk.fold[znak])
    if znak in jezyk.samogloski:
        warianty |= set(jezyk.samogloski[znak])
    if not warianty:
        return re.escape(znak)
    warianty.add(znak)
    return "[" + "".join(sorted(warianty)) + "]"


def _rdzen(slowo: str, jezyk: Jezyk) -> str:
    """Shortest sensible stem: strip the longest known ending."""
    for koncowka in sorted(jezyk.odcinane, key=len, reverse=True):
        if not koncowka or not slowo.endswith(koncowka):
            continue
        reszta = slowo[: len(slowo) - len(koncowka)]
        if len(reszta) >= jezyk.min_rdzen and len(koncowka) <= jezyk.maks_odciecie:
            return reszta
    return slowo


def _warianty_rdzenia(rdzen: str, jezyk: Jezyk) -> List[str]:
    """Stem plus its consonant/umlaut alternations and fleeting-vowel variant."""
    wyniki = [rdzen]
    for dlugosc in (3, 2, 1):
        koncowka = rdzen[-dlugosc:]
        if len(rdzen) > dlugosc and koncowka in jezyk.oboczności:
            baza = rdzen[:-dlugosc]
            wyniki = [baza + alt for alt in jezyk.oboczności[koncowka]]
            break

    # Umlaut/vowel alternation inside the stem (German Mann → Männer).
    if jezyk.kod == "de":
        dodatkowe = []
        for wariant in wyniki:
            for prosta, przeglos in (("a", "ä"), ("o", "ö"), ("u", "ü"), ("au", "äu")):
                if prosta in wariant:
                    dodatkowe.append(wariant.replace(prosta, przeglos, 1))
        wyniki += dodatkowe

    if jezyk.podwajanie and len(rdzen) >= 3 and rdzen[-1] not in "aeiouy":
        wyniki.append(rdzen + rdzen[-1])          # stop → stopped
    if jezyk.e_ruchome and len(rdzen) >= 3 and rdzen[-2] in "eо" \
            and rdzen[-1] not in "aąeęioóuyаеиоуыэюя":
        wyniki.append(rdzen[:-2] + rdzen[-1])     # pies → psa, сон → сна

    widziane, out = set(), []
    for wariant in wyniki:
        if wariant and wariant not in widziane:
            widziane.add(wariant)
            out.append(wariant)
    return out


def _rdzenie(slowo: str, jezyk: Jezyk) -> List[str]:
    """Stem candidates: the stripped stem *and* the word itself.

    Keeping the full word matters where stripping cuts too deep — German
    ``Mann`` would otherwise become ``Man`` and never reach ``Männer``.
    """
    return list(dict.fromkeys([_rdzen(slowo, jezyk), slowo]))


def _regex_rdzenia(slowo: str, jezyk: Jezyk, opcje: Opcje) -> str:
    warianty: List[str] = []
    for rdzen in _rdzenie(slowo, jezyk):
        for wariant in _warianty_rdzenia(rdzen, jezyk):
            if wariant not in warianty:
                warianty.append(wariant)
    galezie = ["".join(_klasa_znaku(z, jezyk, opcje.bez_ogonkow) for z in wariant)
               for wariant in warianty]
    return galezie[0] if len(galezie) == 1 else "(?:" + "|".join(galezie) + ")"


def _regex_koncowek(jezyk: Jezyk, opcje: Opcje) -> str:
    czesci = []
    for koncowka in jezyk.posortowane_koncowki():
        if not koncowka:
            continue
        if opcje.bez_ogonkow:
            czesci.append("".join(_klasa_znaku(z, jezyk, True) for z in koncowka))
        else:
            czesci.append(re.escape(koncowka))
    return "(?:" + "|".join(czesci) + ")?"


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

def wzorzec_slowa(slowo: str, opcje: Optional[Opcje] = None,
                  tryb: str = TRYB_DOKLADNY) -> str:
    """Regular expression for one word (no word boundaries)."""
    opcje = opcje or Opcje()
    slowo = (slowo or "").strip().lower()
    if not slowo:
        return ""

    # A number matches its ordinal forms too: 1 → 1st, 1-go, 1., 1er
    if slowo.isdigit():
        return re.escape(slowo) + \
            r"(?:\s*[-–—.]?\s*(?:go|szy|wszy|ego|st|nd|rd|th|er|te|ten|го|й|е))?"

    if tryb == TRYB_DOKLADNY:
        jezyk = jezyki_dla(slowo, opcje)[0]
        return "".join(_klasa_znaku(z, jezyk, opcje.bez_ogonkow) for z in slowo)

    galezie = []
    for jezyk in jezyki_dla(slowo, opcje):
        trzon = _regex_rdzenia(slowo, jezyk, opcje)
        if tryb == TRYB_RDZEN:
            # ** is plain truncation, the way library catalogues use it:
            # the stem plus anything at all, however long.
            galezie.append(trzon + _LITERA + "*")
        else:
            galezie.append(trzon + _regex_koncowek(jezyk, opcje))
    galezie = list(dict.fromkeys(galezie))
    return galezie[0] if len(galezie) == 1 else "(?:" + "|".join(galezie) + ")"


def wzorzec_terminu(termin: str, opcje: Optional[Opcje] = None,
                    tryb: str = TRYB_DOKLADNY) -> str:
    """Full regular expression, word boundaries included."""
    opcje = opcje or Opcje()
    slowa = [s for s in re.split(r"[\s ]+", (termin or "").strip()) if s]
    if not slowa:
        return ""
    czesci = [wzorzec_slowa(s, opcje, tryb) for s in slowa]
    return GRANICA_L + _SEP.join(c for c in czesci if c) + GRANICA_P


def kompiluj(termin: str, opcje: Optional[Opcje] = None,
             tryb: str = TRYB_DOKLADNY) -> "re.Pattern[str]":
    return re.compile(wzorzec_terminu(termin, opcje, tryb), re.IGNORECASE | re.UNICODE)


def czy_pasuje(tekst: str, termin: str, opcje: Optional[Opcje] = None,
               tryb: str = TRYB_DOKLADNY) -> bool:
    opcje = opcje or Opcje()
    wykluczone = {w.lower() for w in opcje.wyklucz}
    for dopasowanie in kompiluj(termin, opcje, tryb).finditer(tekst or ""):
        if dopasowanie.group(0).lower() not in wykluczone:
            return True
    return False


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------

def _formy_slowa(slowo: str, jezyk: Jezyk, koncowki: Sequence[str]) -> List[str]:
    if slowo.isdigit():
        return [slowo] * len(koncowki)
    rdzen = _rdzen(slowo.lower(), jezyk)
    return [rdzen + koncowka for koncowka in koncowki]


def formy_wg_jezykow(termin: str, opcje: Optional[Opcje] = None,
                     tryb: str = TRYB_ODMIANA,
                     limit: int = 28) -> Dict[str, List[str]]:
    """Sample surface forms per language — what the user sees before running.

    A phrase is inflected as a whole and in agreement ("Józef Robotnik" →
    "Józefa Robotnika"), because that is exactly how matching works.
    """
    opcje = opcje or Opcje()
    slowa = [s for s in re.split(r"\s+", (termin or "").strip()) if s]
    if not slowa:
        return {}
    if tryb == TRYB_DOKLADNY:
        return {"—": [termin.strip()]}

    wynik: Dict[str, List[str]] = {}
    for jezyk in jezyki_dla(slowa[-1], opcje):
        koncowki = (jezyk.podglad or jezyk.posortowane_koncowki())[:limit]
        if tryb == TRYB_RDZEN:
            koncowki = koncowki[:8]
        kolumny = [_formy_slowa(s, jezyk, koncowki) for s in slowa]
        formy, widziane = [], set()
        for indeks in range(len(koncowki)):
            czesci = []
            for slowo, kolumna in zip(slowa, kolumny):
                forma = kolumna[indeks]
                if slowo[:1].isupper():
                    forma = forma[:1].upper() + forma[1:]
                czesci.append(forma)
            fraza = " ".join(czesci)
            if fraza not in widziane:
                widziane.add(fraza)
                formy.append(fraza)
        if tryb == TRYB_RDZEN:
            formy.append(" ".join(slowa[:-1] + [_rdzen(slowa[-1].lower(), jezyk) + "…"]))
        wynik[jezyk.kod] = formy
    return wynik


def przykladowe_formy(termin: str, opcje: Optional[Opcje] = None,
                      tryb: str = TRYB_ODMIANA, limit: int = 60) -> List[str]:
    """Flat list of sample forms (used by the CLI)."""
    wszystkie: List[str] = []
    for formy in formy_wg_jezykow(termin, opcje, tryb).values():
        for forma in formy:
            if forma not in wszystkie:
                wszystkie.append(forma)
            if len(wszystkie) >= limit:
                return wszystkie
    return wszystkie


# --------------------------------------------------------------------------
# Language of a document
# --------------------------------------------------------------------------

_STOPWORDY = {
    "pl": "i w na z nie że się do jest oraz przez dla przy który została były",
    "en": "the and of to in is that for with was were this from have been",
    "de": "der die das und in von zu mit den dem ist auf für nicht wurde",
    "ru": "и в не на что с по как это для был была были от но",
    "uk": "і в на що з не для як це був була були від але",
}
_STOPWORDY = {kod: set(slowa.split()) for kod, slowa in _STOPWORDY.items()}


def wykryj_jezyk_tekstu(tekst: str, domyslny: str = "") -> str:
    """Cheap language guess from stop words — good enough for tagging."""
    slowa = re.findall(r"[^\W\d_]+", (tekst or "").lower())[:400]
    if not slowa:
        return domyslny
    zbior = set(slowa)
    punkty = {kod: len(zbior & stop) for kod, stop in _STOPWORDY.items()}
    najlepszy = max(punkty, key=lambda k: punkty[k])
    if punkty[najlepszy] < 2:
        return domyslny or ("ru" if _CYRYLICA.search(tekst or "") else "")
    return najlepszy


__all__ = [
    "Opcje", "JEZYKI", "Jezyk", "DOMYSLNE",
    "TRYB_DOKLADNY", "TRYB_ODMIANA", "TRYB_RDZEN", "TRYBY",
    "bez_ogonkow", "pismo_slowa", "jezyki_dla", "wzorzec_slowa", "wzorzec_terminu",
    "kompiluj", "czy_pasuje", "formy_wg_jezykow", "przykladowe_formy",
    "wykryj_jezyk_tekstu",
]
