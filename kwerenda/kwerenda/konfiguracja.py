# -*- coding: utf-8 -*-
"""One object describing a whole search job.

Saved and loaded as YAML or JSON with **English keys**, so the same job runs
from the graphical interface and from the command line. Keys from earlier
Polish-language configurations are still accepted.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .morfologia import DOMYSLNE, JEZYKI, Opcje
from .zrodla import Zrodlo

#: External (English) key  ->  internal attribute name.
KLUCZE: Dict[str, str] = {
    "name": "nazwa",
    "query": "zapytanie",
    "default_operator": "domyslny_operator",
    "languages": "jezyki",
    "expand_all": "rozszerzaj_wszystko",
    "ignore_diacritics": "bez_ogonkow",
    "excluded_forms": "wykluczone_formy",
    "sources": "zrodla",
    "contact": "kontakt",
    "delay": "opoznienie",
    "retries": "proby",
    "respect_robots": "respektuj_robots",
    "threads": "watki",
    "use_cache": "uzyj_cache",
    "cache_max_age_days": "maks_wiek_cache_dni",
    "max_candidates": "limit_kandydatow",
    "max_hits": "limit_trafien",
    "snippet_window": "okno_cytatu",
    "max_snippets": "maks_cytatow",
    "zotero_type": "typ_zotero",
    "extra_tags": "tagi_dodatkowe",
    "tag_from_domain": "tag_z_domeny",
    "tag_from_year": "tag_z_roku",
    "tag_from_terms": "tag_z_terminow",
    "tag_from_cms": "tagi_z_wp",
    "tag_from_language": "tag_z_jezyka",
    "year_from": "od_roku",
    "year_to": "do_roku",
    "detect_language": "wykrywaj_jezyk",
}
_ODWROTNE = {v: k for k, v in KLUCZE.items()}


@dataclass
class Konfiguracja:
    nazwa: str = "Search"
    zapytanie: str = ""
    domyslny_operator: str = "AND"          # AND or OR between adjacent terms

    # morphology
    jezyki: List[str] = field(default_factory=lambda: list(DOMYSLNE))
    rozszerzaj_wszystko: bool = False       # treat every term as if it ended with *
    bez_ogonkow: bool = False               # "Zoliborz" matches "Żoliborz"
    wykluczone_formy: List[str] = field(default_factory=list)

    # where to look
    zrodla: List[Zrodlo] = field(default_factory=list)

    # network manners
    kontakt: str = ""
    opoznienie: float = 0.4
    proby: int = 3
    respektuj_robots: bool = True
    watki: int = 2
    uzyj_cache: bool = True
    maks_wiek_cache_dni: float = 30.0

    # limits
    limit_kandydatow: int = 4000
    limit_trafien: int = 1000

    # output
    okno_cytatu: int = 220
    maks_cytatow: int = 4
    typ_zotero: str = "blogPost"
    tagi_dodatkowe: List[str] = field(default_factory=list)
    tag_z_domeny: bool = True
    tag_z_roku: bool = True
    tag_z_terminow: bool = True
    tagi_z_wp: bool = True
    tag_z_jezyka: bool = True
    wykrywaj_jezyk: bool = True
    od_roku: Optional[int] = None
    do_roku: Optional[int] = None

    # ---------------------------------------------------------------
    def opcje_morfologii(self) -> Opcje:
        jezyki = tuple(k for k in (self.jezyki or DOMYSLNE) if k in JEZYKI)
        return Opcje(jezyki=jezyki or tuple(DOMYSLNE),
                     rozszerzaj_wszystko=self.rozszerzaj_wszystko,
                     bez_ogonkow=self.bez_ogonkow,
                     wyklucz=tuple(self.wykluczone_formy))

    # ---------------------------------------------------------------
    def jako_dict(self) -> dict:
        surowe = asdict(self)
        wynik = {_ODWROTNE.get(k, k): v for k, v in surowe.items() if k != "zrodla"}
        wynik["sources"] = [z.jako_dict() if isinstance(z, Zrodlo) else z
                            for z in self.zrodla]
        return wynik

    @classmethod
    def z_dict(cls, dane: dict) -> "Konfiguracja":
        dane = dict(dane or {})
        zrodla_surowe = dane.pop("sources", None)
        if zrodla_surowe is None:
            zrodla_surowe = dane.pop("zrodla", []) or []
        zrodla = [Zrodlo.z_dict(z) if isinstance(z, dict) else z for z in zrodla_surowe]

        znane = set(cls.__dataclass_fields__)          # type: ignore[attr-defined]
        czyste: Dict[str, Any] = {}
        for klucz, wartosc in dane.items():
            nazwa = KLUCZE.get(klucz, klucz)
            if nazwa in znane:
                czyste[nazwa] = wartosc

        konfig = cls(**czyste)
        konfig.zrodla = zrodla
        if isinstance(konfig.jezyki, str):
            konfig.jezyki = [k.strip() for k in konfig.jezyki.split(",") if k.strip()]
        konfig.domyslny_operator = {"I": "AND", "LUB": "OR"}.get(
            (konfig.domyslny_operator or "AND").upper(), (konfig.domyslny_operator or "AND").upper())
        return konfig

    # ---------------------------------------------------------------
    @classmethod
    def wczytaj(cls, sciezka: str | Path) -> "Konfiguracja":
        tekst = Path(sciezka).read_text(encoding="utf-8")
        if str(sciezka).lower().endswith((".yaml", ".yml")):
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise SystemExit("YAML files need PyYAML (pip install pyyaml); "
                                 "or use JSON instead.") from exc
            dane = yaml.safe_load(tekst) or {}
        else:
            dane = json.loads(tekst)
        return cls.z_dict(dane)

    def zapisz(self, sciezka: str | Path) -> None:
        sciezka = Path(sciezka)
        dane = self.jako_dict()
        if str(sciezka).lower().endswith((".yaml", ".yml")):
            import yaml  # type: ignore
            sciezka.write_text(yaml.safe_dump(dane, allow_unicode=True, sort_keys=False),
                               encoding="utf-8")
        else:
            sciezka.write_text(json.dumps(dane, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    # ---------------------------------------------------------------
    def sprawdz(self) -> List[str]:
        """Warnings shown to the user before the run starts."""
        uwagi: List[str] = []
        if not self.zrodla:
            uwagi.append("No source given — add at least one website address.")
        if not self.zapytanie.strip():
            uwagi.append("Empty query: everything found will be collected. "
                         "That can be a lot.")
        if not self.kontakt:
            uwagi.append("No contact address in the User-Agent. It is good manners to "
                         "let site administrators know who is crawling them.")
        if self.opoznienie < 0.2:
            uwagi.append("A delay below 0.2 s between requests is widely considered rude.")
        if not self.respektuj_robots:
            uwagi.append("robots.txt is being ignored — only do this for sites where "
                         "you know you are allowed to.")
        if any(z.ma_dane_logowania() for z in self.zrodla):
            uwagi.append("Some sources use your own credentials. Only access content "
                         "your subscription actually covers, and keep to the site's terms.")
        return uwagi
