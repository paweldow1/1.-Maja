# -*- coding: utf-8 -*-
"""Fleksja: dopasowywanie polskich form odmienionych bez zewnętrznych słowników.

Idea: z zapytanego słowa wyznaczamy rdzeń (odcinając znaną końcówkę fleksyjną),
a następnie budujemy wyrażenie regularne:

    (granica słowa) RDZEŃ_Z_OBOCZNIKAMI KOŃCÓWKA (granica słowa)

gdzie RDZEŃ_Z_OBOCZNIKAMI uwzględnia polskie oboczności spółgłoskowe
(Żoliborz→Żoliborzu, święto→święcie, Gdańsk→Gdańsku) i samogłoskowe
(ó↔o, ą↔ę, e ruchome), a KOŃCÓWKA to zamknięta lista końcówek fleksyjnych.

Trzy tryby (`FlexOptions.mode`):
  * ``dokladnie`` – dosłownie to, co wpisano (bez odmiany),
  * ``fleksja``   – domyślny, odmiana przez zamkniętą listę końcówek,
  * ``rdzen``     – agresywny: rdzeń + dowolne do 6 liter (łapie też derywaty
                    typu ``praca`` → ``pracownik``), z ryzykiem szumu.

Świadomie nie używamy morfeusz2/spaCy: mają być zerowe zależności i działanie
offline. Jeśli jednak w środowisku jest zainstalowany ``morfeusz2``, funkcja
:func:`lematyzuj` wykorzysta go do podpowiedzi form w podglądzie.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

# --------------------------------------------------------------------------
# Alfabet i znaki diakrytyczne
# --------------------------------------------------------------------------

PL_LETTERS = "aąbcćdeęfghijklłmnńoópqrsśtuvwxyzźż"

_FOLD = {
    "ą": "aą", "ć": "cć", "ę": "eę", "ł": "lł", "ń": "nń",
    "ó": "oó", "ś": "sś", "ź": "zźż", "ż": "zźż",
    "a": "aą", "c": "cć", "e": "eę", "l": "lł", "n": "nń",
    "o": "oó", "s": "sś", "z": "zźż",
}

# Oboczności samogłoskowe działające zawsze (niezależnie od trybu „bez ogonków”).
_VOWEL_ALT = {"o": "oó", "ó": "oó", "ą": "ąę", "ę": "ąę"}

# Oboczności spółgłoskowe na końcu rdzenia. Klucze dwuznakowe mają pierwszeństwo.
_STEM_FINAL_ALT = {
    "st": ["st", "ść", "ści", "śc", "szcz"],
    "sł": ["sł", "śl"],
    "zł": ["zł", "źl"],
    "zd": ["zd", "źdz", "ździ", "źdź"],
    "sn": ["sn", "śni", "śn"],
    "ch": ["ch", "sz", "ś", "si"],
    "sz": ["sz", "ch", "ś", "si"],
    "cz": ["cz", "c", "k"],
    "dz": ["dz", "g", "dź", "dzi"],
    "rz": ["rz", "r"],
    "k":  ["k", "c", "cz", "ki"],
    "g":  ["g", "dz", "ż", "z", "gi"],
    "r":  ["r", "rz"],
    "ł":  ["ł", "l"],
    "l":  ["l", "ł"],
    "t":  ["t", "ć", "ci", "c"],
    "d":  ["d", "dź", "dzi", "dz"],
    "s":  ["s", "ś", "si", "sz"],
    "z":  ["z", "ź", "zi", "ż"],
    "n":  ["n", "ń", "ni"],
    "b":  ["b", "bi"],
    "p":  ["p", "pi"],
    "w":  ["w", "wi"],
    "m":  ["m", "mi"],
    "f":  ["f", "fi"],
    "ć":  ["ć", "t", "ci", "c"],
    "ń":  ["ń", "n", "ni"],
    "ś":  ["ś", "s", "si", "sz"],
    "ź":  ["ź", "z", "zi", "ż"],
    "ż":  ["ż", "z", "g", "ź"],
    "c":  ["c", "cz", "k", "ć"],
}

# --------------------------------------------------------------------------
# Końcówki fleksyjne
# --------------------------------------------------------------------------

_ENDINGS_NOUN = """
a ach ami ą e em ę i ie iem mi o om owi owie ów u y ą
ów om ami ach owie
ość ości ością ościach ościami
anie ania aniu aniem aniach anią
enie enia eniu eniem eniach enią
cie cia ciu ciem ciach
""".split()

_ENDINGS_ADJ = """
y i a e ego iego emu iemu ym im ych ich ymi imi ej iej ą ie
owy owa owe owego owemu owym owych owymi owej owo owi
ski ska skie skiego skiemu skim skich skimi skiej sku
cki cka ckie ckiego ckim ckich ckiej
ny na ne nego nemu nym nych nymi nej ni
""".split()

_ENDINGS_VERB = """
ć ę esz e emy ecie ą isz imy icie ysz ymy ycie
ł ła ło li ły łem łam łeś łaś liśmy liście łyśmy łyście
ał ała ało ali ały ałem ałam ałeś ałaś aliśmy aliście
ił iła iło ili iły ył yła yło yli yły
ono ano iono ąc ący ąca ące ących ącym ącymi
ony ona one onych onym any ana ane anych anym ty ta te tych tym
""".split()

#: Pełna, zamknięta lista końcówek (plus końcówka pusta) używana w trybie „fleksja”.
ENDINGS: List[str] = sorted(
    {""} | set(_ENDINGS_NOUN) | set(_ENDINGS_ADJ) | set(_ENDINGS_VERB),
    key=lambda e: (-len(e), e),
)

#: Skrócona lista do podglądu przykładowych form w interfejsie.
ENDINGS_PODGLAD = [
    "", "a", "u", "owi", "em", "ie", "y", "i", "ę", "ą", "o",
    "ów", "om", "ami", "ach", "owie", "owy", "owa", "owe", "ego", "ym", "ych",
]

# Końcówki, które wolno odciąć przy wyznaczaniu rdzenia. Świadomie węższa niż
# ENDINGS: odcinanie „ość” czy „anie” gubiłoby sens słowa.
_STRIPPABLE = sorted(
    {
        "ami", "ach", "ami", "owie", "owi", "ów", "om", "em", "iem", "mi",
        "ego", "emu", "ym", "im", "ych", "ich", "ymi", "imi", "ej", "iej",
        "ie", "a", "e", "i", "o", "u", "y", "ą", "ę",
    },
    key=len,
    reverse=True,
)


@dataclass
class FlexOptions:
    """Ustawienia dopasowania jednego terminu."""

    mode: str = "fleksja"           # dokladnie | fleksja | rdzen
    fold_diacritics: bool = False   # „Zoliborz” ma trafiać w „Żoliborz”
    max_strip: int = 4              # ile liter wolno odciąć przy szukaniu rdzenia
    min_stem: int = 3               # najkrótszy dopuszczalny rdzeń
    luz: int = 6                    # ile liter dokleja tryb „rdzen”
    warianty: Sequence[str] = field(default_factory=tuple)   # ręczne dopiski
    wyklucz: Sequence[str] = field(default_factory=tuple)    # formy do odrzucenia

    def replace(self, **kw) -> "FlexOptions":
        d = dict(self.__dict__)
        d.update(kw)
        return FlexOptions(**d)


# --------------------------------------------------------------------------
# Budowa wyrażeń
# --------------------------------------------------------------------------

def bez_ogonkow(tekst: str) -> str:
    """Usuwa znaki diakrytyczne (ł → l, ż → z ...)."""
    tekst = tekst.replace("ł", "l").replace("Ł", "L")
    rozlozone = unicodedata.normalize("NFD", tekst)
    return "".join(c for c in rozlozone if unicodedata.category(c) != "Mn")


def _klasa_znaku(ch: str, fold: bool) -> str:
    warianty = set()
    if fold and ch in _FOLD:
        warianty |= set(_FOLD[ch])
    if ch in _VOWEL_ALT:
        warianty |= set(_VOWEL_ALT[ch])
    if not warianty:
        return re.escape(ch)
    warianty.add(ch)
    return "[" + "".join(sorted(warianty)) + "]"


def _rdzen(slowo: str, opts: FlexOptions) -> str:
    """Najkrótszy sensowny rdzeń: odcinamy najdłuższą znaną końcówkę."""
    for koncowka in _STRIPPABLE:
        if not slowo.endswith(koncowka):
            continue
        reszta = slowo[: len(slowo) - len(koncowka)]
        if len(reszta) >= opts.min_stem and len(koncowka) <= opts.max_strip:
            return reszta
    return slowo


def _warianty_rdzenia(rdzen: str) -> List[str]:
    """Rdzeń + jego oboczności spółgłoskowe i wersja z „e” ruchomym."""
    wyniki = [rdzen]
    for dl in (2, 1):
        koniec = rdzen[-dl:]
        if len(rdzen) > dl and koniec in _STEM_FINAL_ALT:
            baza = rdzen[:-dl]
            wyniki = [baza + alt for alt in _STEM_FINAL_ALT[koniec]]
            break
    # e ruchome: pies → ps, wiatr → wietrz nie, ale sen → sn
    if len(rdzen) >= 3 and rdzen[-2] == "e" and rdzen[-1] not in "aąeęioóuy":
        wyniki.append(rdzen[:-2] + rdzen[-1])
    # wypadanie tematycznego -e- z ostatniej sylaby (marzec → marc)
    out, widziane = [], set()
    for w in wyniki:
        if w not in widziane:
            widziane.add(w)
            out.append(w)
    return out


def _regex_rdzenia(rdzen: str, opts: FlexOptions) -> str:
    warianty = _warianty_rdzenia(rdzen)
    galezie = []
    for w in warianty:
        galezie.append("".join(_klasa_znaku(c, opts.fold_diacritics) for c in w))
    if len(galezie) == 1:
        return galezie[0]
    return "(?:" + "|".join(galezie) + ")"


def _regex_koncowek(opts: FlexOptions) -> str:
    if opts.fold_diacritics:
        czesci = []
        for e in ENDINGS:
            if not e:
                continue
            czesci.append("".join(_klasa_znaku(c, True) for c in e))
        return "(?:" + "|".join(czesci) + ")?"
    czesci = [re.escape(e) for e in ENDINGS if e]
    return "(?:" + "|".join(czesci) + ")?"


_ORDINAL_PL = r"(?:\s*[-–—]?\s*(?:go|szy|wszy|ego|maja|majowy))?"


def wzorzec_slowa(slowo: str, opts: FlexOptions | None = None) -> str:
    """Wyrażenie regularne (bez granic słowa) dopasowujące jedno słowo."""
    opts = opts or FlexOptions()
    slowo = slowo.strip().lower()
    if not slowo:
        return ""

    # Liczebniki: „1” ma trafiać także w „1-go”, „1.”
    if slowo.isdigit():
        return re.escape(slowo) + r"(?:\s*[-–—]?\s*(?:go|szy|wszy|ego))?"

    # Jawny wildcard użytkownika: „solidarn*”
    if slowo.endswith("*"):
        baza = slowo[:-1]
        trzon = "".join(_klasa_znaku(c, opts.fold_diacritics) for c in baza)
        return trzon + r"[\w]{0,%d}" % max(opts.luz, 8)

    if opts.mode == "dokladnie":
        return "".join(_klasa_znaku(c, opts.fold_diacritics) for c in slowo)

    rdzen = _rdzen(slowo, opts)
    trzon = _regex_rdzenia(rdzen, opts)

    if opts.mode == "rdzen":
        return trzon + r"[\w]{0,%d}" % opts.luz

    return trzon + _regex_koncowek(opts)


# Separator wewnątrz frazy: spacja, półpauza, przecinek, twarda spacja, nowa linia.
_SEP = r"[\s ]*[-–—,./]?[\s ]*"

GRANICA_L = r"(?<![0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż_])"
GRANICA_P = r"(?![0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż_])"


def wzorzec_terminu(termin: str, opts: FlexOptions | None = None) -> str:
    """Pełne wyrażenie regularne (z granicami słowa) dla terminu lub frazy."""
    opts = opts or FlexOptions()
    slowa = [s for s in re.split(r"[\s ]+", termin.strip()) if s]
    if not slowa:
        return ""
    rdzenie = [wzorzec_slowa(s, opts) for s in slowa]
    trzon = _SEP.join(r for r in rdzenie if r)

    galezie = [trzon]
    for w in opts.warianty:
        galezie.append(wzorzec_terminu_surowy(w, opts))
    if len(galezie) > 1:
        trzon = "(?:" + "|".join(galezie) + ")"

    return GRANICA_L + trzon + GRANICA_P


def wzorzec_terminu_surowy(termin: str, opts: FlexOptions) -> str:
    slowa = [s for s in re.split(r"[\s ]+", termin.strip()) if s]
    return _SEP.join(wzorzec_slowa(s, opts) for s in slowa if s)


def kompiluj(termin: str, opts: FlexOptions | None = None) -> "re.Pattern[str]":
    return re.compile(wzorzec_terminu(termin, opts), re.IGNORECASE | re.UNICODE)


# --------------------------------------------------------------------------
# Podgląd form – żeby badacz widział, co właściwie zostanie dopasowane
# --------------------------------------------------------------------------

def _formy_slowa(slowo: str, opts: FlexOptions, koncowki: List[str]) -> List[str]:
    """Formy jednego słowa, w kolejności odpowiadającej liście końcówek."""
    if slowo.isdigit() or slowo.endswith("*"):
        return [slowo] * len(koncowki)
    rdzen = _rdzen(slowo.lower(), opts)
    return [rdzen + e for e in koncowki]


def przykladowe_formy(termin: str, opts: FlexOptions | None = None, limit: int = 60) -> List[str]:
    """Prawdopodobne formy odmienione – do podglądu w interfejsie.

    Frazę odmieniamy w całości i zgodnie: „Józef Robotnik” → „Józefa Robotnika”,
    „Józefowi Robotnikowi”. Tak samo działa dopasowanie, więc podgląd nie kłamie.
    Lista bywa nadmiarowa (wzorzec przyjmie też formy, których w polszczyźnie nie
    ma) — to nieszkodliwe, bo takich ciągów po prostu nie ma w tekstach.
    """
    opts = opts or FlexOptions()
    slowa = [s for s in re.split(r"\s+", termin.strip()) if s]
    if not slowa:
        return []
    if opts.mode == "dokladnie":
        return [termin.strip()]

    koncowki = ENDINGS_PODGLAD if opts.mode == "fleksja" else ["", "a", "u", "ów", "ownik", "ować"]
    koncowki = koncowki[:limit]
    kolumny = [_formy_slowa(s, opts, koncowki) for s in slowa]

    formy: List[str] = []
    widziane = set()
    for indeks in range(len(koncowki)):
        czesci = []
        for slowo, kolumna in zip(slowa, kolumny):
            forma = kolumna[indeks]
            if slowo[:1].isupper():
                forma = forma[:1].upper() + forma[1:]
            czesci.append(forma)
        forma_frazy = " ".join(czesci)
        if forma_frazy not in widziane:
            widziane.add(forma_frazy)
            formy.append(forma_frazy)

    # dodatkowo pokaż oboczności rdzenia ostatniego słowa (Żoliborz → żoliborsk-)
    if opts.mode == "fleksja" and len(formy) < limit:
        rdzen = _rdzen(slowa[-1].lower(), opts)
        for wariant in _warianty_rdzenia(rdzen)[1:4]:
            for koncowka in ("a", "u", "i", "ie"):
                forma = " ".join(slowa[:-1] + [wariant + koncowka])
                if slowa[-1][:1].isupper():
                    forma = forma[:1].upper() + forma[1:]
                if forma not in widziane and len(formy) < limit:
                    widziane.add(forma)
                    formy.append(forma)
    return formy


def lematyzuj(slowo: str) -> List[str]:
    """Opcjonalne wsparcie morfeusz2, jeśli akurat jest zainstalowany."""
    try:  # pragma: no cover - zależy od środowiska użytkownika
        import morfeusz2  # type: ignore
    except Exception:
        return []
    try:  # pragma: no cover
        morf = morfeusz2.Morfeusz()
        return sorted({analiza[2][1].split(":")[0] for analiza in morf.analyse(slowo)})
    except Exception:
        return []


def czy_pasuje(slowo: str, termin: str, opts: FlexOptions | None = None) -> bool:
    """Wygodne w testach i w oknie „sprawdź słowo” w interfejsie."""
    opts = opts or FlexOptions()
    wykluczone = {w.lower() for w in opts.wyklucz}
    for dopasowanie in kompiluj(termin, opts).finditer(slowo):
        if dopasowanie.group(0).lower() not in wykluczone:
            return True
    return False
