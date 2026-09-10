# -*- coding: utf-8 -*-
"""Language tables driving morphological expansion.

One generic algorithm (see :mod:`kwerenda.morfologia`) is parameterised per
language: a closed list of inflectional endings, a table of stem-final
alternations, vowel alternations and a diacritic-folding map.

These are deliberately rule-based approximations, not dictionaries: they need no
downloads, work offline and degrade gracefully. Where a real analyser is
installed (``morfeusz2`` for Polish, ``pymorphy3`` for Russian/Ukrainian,
``snowballstemmer`` for the rest) the preview can use it, but nothing depends
on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Jezyk:
    kod: str                       # ISO 639-1
    nazwa: str                     # English display name
    pismo: str                     # "latin" | "cyrillic"
    koncowki: List[str]            # closed list of inflectional endings
    odcinane: List[str]            # endings that may be stripped to find a stem
    oboczności: Dict[str, List[str]] = field(default_factory=dict)
    samogloski: Dict[str, str] = field(default_factory=dict)
    fold: Dict[str, str] = field(default_factory=dict)
    podglad: List[str] = field(default_factory=list)   # endings shown in the UI
    min_rdzen: int = 3
    maks_odciecie: int = 4
    podwajanie: bool = False       # stop → stopped (English)
    e_ruchome: bool = True         # pies → psa, Vater → Vatr- (fleeting vowel)

    def posortowane_koncowki(self) -> List[str]:
        return sorted(set(self.koncowki) | {""}, key=lambda e: (-len(e), e))


def _slowa(tekst: str) -> List[str]:
    return [w for w in tekst.split() if w]


# ==========================================================================
# POLSKI
# ==========================================================================

_PL_KONCOWKI = _slowa("""
a ach ami ą e em ę i ie iem mi o om owi owie ów u y
ość ości ością ościach ościami
anie ania aniu aniem aniach anią enie enia eniu eniem eniach enią
cie cia ciu ciem ciach
ego iego emu iemu ym im ych ich ymi imi ej iej
owy owa owe owego owemu owym owych owymi owej owo
ski ska skie skiego skiemu skim skich skimi skiej sku
cki cka ckie ckiego ckim ckich ckiej
ny na ne nego nemu nym nych nymi nej ni
ć esz emy ecie ą isz imy icie ysz ymy ycie
ł ła ło li ły łem łam łeś łaś liśmy liście łyśmy łyście
ał ała ało ali ały ałem ałam ałeś ałaś aliśmy aliście
ił iła iło ili iły ył yła yło yli yły
ono ano iono ąc ący ąca ące ących ącym ącymi
ony ona one onych onym any ana ane anych anym ty ta te tych tym
""")

_PL_ODCINANE = _slowa("""
ami ach owie owi ów om em iem mi ego emu ym im ych ich ymi imi ej iej
ie a e i o u y ą ę
""")

_PL_OBOCZNOSCI = {
    "st": ["st", "ść", "ści", "śc", "szcz"], "sł": ["sł", "śl"], "zł": ["zł", "źl"],
    "zd": ["zd", "źdz", "ździ", "źdź"], "sn": ["sn", "śni", "śn"],
    "ch": ["ch", "sz", "ś", "si"], "sz": ["sz", "ch", "ś", "si"],
    "cz": ["cz", "c", "k"], "dz": ["dz", "g", "dź", "dzi"], "rz": ["rz", "r"],
    "k": ["k", "c", "cz", "ki"], "g": ["g", "dz", "ż", "z", "gi"], "r": ["r", "rz"],
    "ł": ["ł", "l"], "l": ["l", "ł"], "t": ["t", "ć", "ci", "c"],
    "d": ["d", "dź", "dzi", "dz"], "s": ["s", "ś", "si", "sz"], "z": ["z", "ź", "zi", "ż"],
    "n": ["n", "ń", "ni"], "b": ["b", "bi"], "p": ["p", "pi"], "w": ["w", "wi"],
    "m": ["m", "mi"], "f": ["f", "fi"], "ć": ["ć", "t", "ci", "c"],
    "ń": ["ń", "n", "ni"], "ś": ["ś", "s", "si", "sz"], "ź": ["ź", "z", "zi", "ż"],
    "ż": ["ż", "z", "g", "ź"], "c": ["c", "cz", "k", "ć"],
}

_PL_FOLD = {"ą": "aą", "ć": "cć", "ę": "eę", "ł": "lł", "ń": "nń", "ó": "oó",
            "ś": "sś", "ź": "zźż", "ż": "zźż", "a": "aą", "c": "cć", "e": "eę",
            "l": "lł", "n": "nń", "o": "oó", "s": "sś", "z": "zźż"}

POLSKI = Jezyk(
    kod="pl", nazwa="Polish", pismo="latin",
    koncowki=_PL_KONCOWKI, odcinane=_PL_ODCINANE, oboczności=_PL_OBOCZNOSCI,
    samogloski={"o": "oó", "ó": "oó", "ą": "ąę", "ę": "ąę"}, fold=_PL_FOLD,
    podglad=_slowa("a u owi em ie y i ę ą o ów om ami ach owie owy owa owe ego ym ych"),
)

# ==========================================================================
# ENGLISH
# ==========================================================================

_EN_KONCOWKI = _slowa("""
s es ed d ing er est ies ied ying ings ers ment ments
al ally ic ical ism ist ists ation ations sion tion tions ness
""")

ANGIELSKI = Jezyk(
    kod="en", nazwa="English", pismo="latin",
    koncowki=_EN_KONCOWKI,
    odcinane=_slowa("ing ies ied es ed er est s e y"),
    oboczności={"y": ["y", "i", "ie"], "i": ["i", "y", "ie"], "c": ["c", "ck"],
                "f": ["f", "v", "ve"], "v": ["v", "f", "ve"]},
    samogloski={}, fold={},
    podglad=_slowa("s es ed ing er est ies ied ation ism ist ness al ic"),
    min_rdzen=3, maks_odciecie=3, podwajanie=True, e_ruchome=False,
)

# ==========================================================================
# DEUTSCH
# ==========================================================================

_DE_KONCOWKI = _slowa("""
e en er es s n em ern ens
ung ungen heit heiten keit keiten schaft schaften
te ten test tet st t end ende enden er ere eren erer ste sten
in innen
""")

NIEMIECKI = Jezyk(
    kod="de", nazwa="German", pismo="latin",
    koncowki=_DE_KONCOWKI,
    odcinane=_slowa("ungen ern en em es er e n s"),
    # Umlaut is the German equivalent of Slavic stem alternation.
    oboczności={"a": ["a", "ä"], "o": ["o", "ö"], "u": ["u", "ü"],
                "ä": ["ä", "a"], "ö": ["ö", "o"], "ü": ["ü", "u"],
                "ss": ["ss", "ß"], "ß": ["ß", "ss"]},
    samogloski={"a": "aä", "o": "oö", "u": "uü", "ä": "aä", "ö": "oö", "ü": "uü"},
    fold={"ä": "aä", "ö": "oö", "ü": "uü", "ß": "sß", "a": "aä", "o": "oö", "u": "uü"},
    podglad=_slowa("e en er es s n em ung ungen heit keit schaft te ten"),
    min_rdzen=3, maks_odciecie=5,
)

# ==========================================================================
# РУССКИЙ
# ==========================================================================

_RU_KONCOWKI = _slowa("""
а я ы и у ю е ё ой ей ом ем ам ям ах ях ами ями ов ев ёв
ий ый ая яя ое ее ые ие ых их ым им ыми ими ую юю ой ею
ешь ет ем ете ут ют ишь ит им ите ат ят
л ла ло ли ть ться ся сь ся
ние ния нию нием ниях ений ение
ский ская ское ские ского ском ских ским скими
ость ости остью остей
""")

ROSYJSKI = Jezyk(
    kod="ru", nazwa="Russian", pismo="cyrillic",
    koncowki=_RU_KONCOWKI,
    odcinane=_slowa("ами ями ах ях ов ев ый ий ая ое ые ие ых их ым им ой ей ом ем ам ям а я ы и у ю е о ь й"),
    oboczności={
        "к": ["к", "ч", "ц"], "г": ["г", "ж", "з"], "х": ["х", "ш", "с"],
        "ц": ["ц", "ч", "к"], "д": ["д", "ж", "жд"], "т": ["т", "ч", "щ"],
        "с": ["с", "ш"], "з": ["з", "ж"], "ск": ["ск", "щ"], "ст": ["ст", "щ"],
        "б": ["б", "бл"], "п": ["п", "пл"], "в": ["в", "вл"], "м": ["м", "мл"],
        "ф": ["ф", "фл"], "ь": ["ь", ""], "й": ["й", ""],
    },
    samogloski={"о": "оа", "е": "её", "ё": "ёе"},
    fold={"е": "её", "ё": "ёе", "и": "иі", "ъ": "ъь", "ь": "ьъ"},
    podglad=_slowa("а я ы и у е ом ем ов ах ами ый ая ое ые ых ский ость ние"),
)

# ==========================================================================
# УКРАЇНСЬКА
# ==========================================================================

_UK_KONCOWKI = _slowa("""
а я и і ї у ю е є ою ею ом ем ам ям ах ях ами ями ів їв ей
ий ій ого ому их им ими ої ою
еш є емо ете уть ють иш ить имо ите ать ять
в ла ло ли ти тися ся сь
ння ннями ність ності ністю
ський ська ське ські ського ським ських
""")

UKRAINSKI = Jezyk(
    kod="uk", nazwa="Ukrainian", pismo="cyrillic",
    koncowki=_UK_KONCOWKI,
    odcinane=_slowa("ами ями ах ях ів їв ого ому их им ими ої ою ом ем ам ям "
                    "а я и і ї у ю е є о ь й"),
    oboczności={
        "к": ["к", "ц", "ч"], "г": ["г", "з", "ж"], "х": ["х", "с", "ш"],
        "д": ["д", "дж", "ж"], "т": ["т", "ч"], "с": ["с", "ш"], "з": ["з", "ж"],
        "ськ": ["ськ", "зьк", "цьк"], "ь": ["ь", ""], "й": ["й", ""],
    },
    # Typical Ukrainian о/е → і alternation: кіт/кота, ніс/носа.
    samogloski={"о": "оі", "е": "еі", "і": "іоє"},
    fold={"і": "іи", "и": "ии", "ї": "їі", "є": "єе", "ь": "ь"},
    podglad=_slowa("а я и і у ою ом ів ах ами ий ої ського ність ння"),
)


JEZYKI: Dict[str, Jezyk] = {j.kod: j for j in
                            (POLSKI, ANGIELSKI, NIEMIECKI, ROSYJSKI, UKRAINSKI)}

#: Order used when the user has not narrowed the language list.
DOMYSLNE = ["pl", "en", "de", "ru", "uk"]
