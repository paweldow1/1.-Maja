# -*- coding: utf-8 -*-
"""Konfiguracja kwerendy – jeden obiekt opisujący całe zadanie.

Da się go zapisać/wczytać jako YAML albo JSON, więc to samo zadanie można
uruchomić z interfejsu graficznego i z wiersza poleceń.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fleksja import FlexOptions
from .zrodla import Zrodlo


@dataclass
class Konfiguracja:
    nazwa: str = "Kwerenda"
    zapytanie: str = ""
    domyslny_operator: str = "I"          # I albo LUB między sąsiednimi terminami

    # fleksja
    tryb_fleksji: str = "fleksja"          # dokladnie | fleksja | rdzen
    bez_ogonkow: bool = False              # „Zoliborz” ma trafiać w „Żoliborz”
    warianty_reczne: Dict[str, List[str]] = field(default_factory=dict)
    wykluczone_formy: List[str] = field(default_factory=list)

    # źródła
    zrodla: List[Zrodlo] = field(default_factory=list)

    # sieć i grzeczność
    kontakt: str = ""
    opoznienie: float = 0.4
    proby: int = 3
    respektuj_robots: bool = True
    watki: int = 2
    uzyj_cache: bool = True
    maks_wiek_cache_dni: float = 30.0

    # limity
    limit_kandydatow: int = 4000
    limit_trafien: int = 1000

    # wynik
    okno_cytatu: int = 220
    maks_cytatow: int = 4
    typ_zotero: str = "blogPost"
    tagi_dodatkowe: List[str] = field(default_factory=list)
    tag_z_domeny: bool = True
    tag_z_roku: bool = True
    tag_z_terminow: bool = True
    tagi_z_wp: bool = True
    od_roku: Optional[int] = None
    do_roku: Optional[int] = None

    # ---------------------------------------------------------------
    def opcje_fleksji(self) -> FlexOptions:
        return FlexOptions(mode=self.tryb_fleksji, fold_diacritics=self.bez_ogonkow,
                           wyklucz=tuple(self.wykluczone_formy))

    def jako_dict(self) -> dict:
        dane = asdict(self)
        dane["zrodla"] = [asdict(z) if not isinstance(z, dict) else z for z in self.zrodla]
        return dane

    @classmethod
    def z_dict(cls, dane: dict) -> "Konfiguracja":
        dane = dict(dane or {})
        zrodla = [Zrodlo.z_dict(z) if isinstance(z, dict) else z
                  for z in dane.pop("zrodla", []) or []]
        znane = {p for p in cls.__dataclass_fields__}       # type: ignore[attr-defined]
        czyste = {k: v for k, v in dane.items() if k in znane}
        konfig = cls(**czyste)
        konfig.zrodla = zrodla
        return konfig

    # ---------------------------------------------------------------
    @classmethod
    def wczytaj(cls, sciezka: str | Path) -> "Konfiguracja":
        tekst = Path(sciezka).read_text(encoding="utf-8")
        if str(sciezka).lower().endswith((".yaml", ".yml")):
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise SystemExit("Do plików YAML potrzebny jest pakiet PyYAML "
                                 "(pip install pyyaml) albo użyj formatu JSON.") from exc
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
            sciezka.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------------
    def sprawdz(self) -> List[str]:
        """Zwraca listę zastrzeżeń do pokazania użytkownikowi przed startem."""
        uwagi: List[str] = []
        if not self.zrodla:
            uwagi.append("Nie podano żadnego źródła (adresu strony).")
        if not self.zapytanie.strip():
            uwagi.append("Puste zapytanie – zbiorę wszystko, co znajdę (to może być dużo).")
        if not self.kontakt:
            uwagi.append("Brak adresu kontaktowego w User-Agent — wypada się przedstawiać "
                         "administratorom przeszukiwanych serwisów.")
        if self.opoznienie < 0.2:
            uwagi.append("Odstęp między zapytaniami poniżej 0,2 s bywa uznawany za nieuprzejmy.")
        if not self.respektuj_robots:
            uwagi.append("Wyłączono respektowanie robots.txt — rób tak tylko dla stron, "
                         "co do których masz pewność, że wolno.")
        return uwagi
