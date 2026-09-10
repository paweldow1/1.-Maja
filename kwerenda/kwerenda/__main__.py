# -*- coding: utf-8 -*-
"""Wiersz poleceń: interfejs graficzny, kwerenda wsadowa, podgląd fleksji, eksport."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __wersja__
from .cytowania import (do_bibtex, do_csl, do_csv, do_markdown, do_ris, nadaj_citekeys,
                        nazwa_pliku, Rekord)
from .fleksja import FlexOptions, przykladowe_formy
from .konfiguracja import Konfiguracja
from .magazyn import Magazyn
from .silnik import Silnik
from .zapytania import BladZapytania, parsuj


def _magazyn(args) -> Magazyn:
    return Magazyn(args.baza)


def _katalog_eksportu(args) -> Path:
    katalog = Path(args.eksport)
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


# --------------------------------------------------------------------------
def polecenie_gui(args) -> int:
    from .serwer import uruchom_serwer
    uruchom_serwer(_magazyn(args), _katalog_eksportu(args), port=args.port,
                   otworz=not args.bez_przegladarki)
    return 0


def polecenie_uruchom(args) -> int:
    konfig = Konfiguracja.wczytaj(args.konfig)
    if args.zapytanie:
        konfig.zapytanie = args.zapytanie
    for uwaga in konfig.sprawdz():
        print(f"⚠ {uwaga}", file=sys.stderr)

    magazyn = _magazyn(args)
    silnik = Silnik(konfig, magazyn, log=lambda w: print(w, flush=True))
    przebieg = silnik.uruchom()

    trafienia = magazyn.trafienia(przebieg)
    print(f"\nTrafień: {len(trafienia)} (przebieg #{przebieg})")
    if args.format:
        sciezka = _zapisz(trafienia, args.format, _katalog_eksportu(args),
                          f"{nazwa_pliku(Rekord(tytul=konfig.nazwa))}-{przebieg}")
        print(f"Zapisano: {sciezka}")
    return 0


def polecenie_eksport(args) -> int:
    magazyn = _magazyn(args)
    trafienia = magazyn.trafienia(args.przebieg, tylko_wybrane=not args.wszystkie)
    if not trafienia:
        print("Brak trafień do wyeksportowania.", file=sys.stderr)
        return 1
    sciezka = _zapisz(trafienia, args.format, _katalog_eksportu(args),
                      f"kwerenda-{args.przebieg or 'wszystko'}")
    print(f"Zapisano {len(trafienia)} rekordów: {sciezka}")
    return 0


def polecenie_zotero(args) -> int:
    from .zotero import wyslij_do_konektora, wyslij_przez_api
    magazyn = _magazyn(args)
    trafienia = magazyn.trafienia(args.przebieg, tylko_wybrane=not args.wszystkie)
    rekordy = nadaj_citekeys([Rekord.z_trafienia(t) for t in trafienia])
    if args.klucz and args.uzytkownik:
        wynik = wyslij_przez_api(rekordy, args.klucz, args.uzytkownik, args.kolekcja or "")
    else:
        wynik = wyslij_do_konektora(rekordy)
    print(wynik["komunikat"])
    for blad in wynik.get("bledy", [])[:10]:
        print("  ! " + blad, file=sys.stderr)
    return 0 if wynik.get("ok") else 1


def polecenie_podglad(args) -> int:
    opcje = FlexOptions(mode=args.tryb, fold_diacritics=args.bez_ogonkow)
    try:
        drzewo = parsuj(args.zapytanie, opcje, args.operator)
    except BladZapytania as exc:
        print(f"Błąd zapytania: {exc}", file=sys.stderr)
        return 1
    print("Zrozumiane jako:", drzewo.opis())
    for termin in drzewo.terminy():
        formy = termin.formy(args.ile)
        print(f"\n• {termin.tekst}  [pole: {termin.pole}, tryb: {termin.opcje_efektywne().mode}]")
        print("  formy:", ", ".join(formy))
        if args.wzorce:
            print("  wzorzec:", termin.wzorzec())
    if args.probka:
        from .zapytania import Dokument, cytaty
        dokument = Dokument(tekst=args.probka)
        pasuje, trafienia = drzewo.ocen(dokument)
        print("\nPróbka:", "PASUJE" if pasuje else "nie pasuje")
        for cytat in cytaty(dokument, trafienia, 80, 3):
            print("  …" + cytat["fragment"])
    return 0


def polecenie_przebiegi(args) -> int:
    for przebieg in _magazyn(args).przebiegi(args.ile):
        print(f"#{przebieg['id']:>4}  {przebieg['status']:<10} {przebieg['trafien']:>4} traf.  "
              f"{przebieg['nazwa']}  |  {przebieg['zapytanie']}")
    return 0


def polecenie_korpus(args) -> int:
    magazyn = _magazyn(args)
    if args.wyczysc:
        ile = magazyn.wyczysc_korpus(args.host or "")
        print(f"Usunięto {ile} stron z korpusu.")
        return 0
    for wpis in magazyn.statystyki_korpusu():
        print(f"{wpis['host']:<44} {wpis['ile']:>6} stron")
    return 0


# --------------------------------------------------------------------------
def _zapisz(trafienia, format_: str, katalog: Path, rdzen_nazwy: str) -> Path:
    rekordy = nadaj_citekeys([Rekord.z_trafienia(t) for t in trafienia])
    format_ = format_.lower()
    if format_ == "ris":
        sciezka = katalog / f"{rdzen_nazwy}.ris"
        sciezka.write_text(do_ris(rekordy), encoding="utf-8")
    elif format_ in ("csl", "csl-json", "json"):
        sciezka = katalog / f"{rdzen_nazwy}.csl.json"
        sciezka.write_text(json.dumps(do_csl(rekordy), ensure_ascii=False, indent=2),
                           encoding="utf-8")
    elif format_ in ("bib", "bibtex"):
        sciezka = katalog / f"{rdzen_nazwy}.bib"
        sciezka.write_text(do_bibtex(rekordy), encoding="utf-8")
    elif format_ == "csv":
        sciezka = katalog / f"{rdzen_nazwy}.csv"
        sciezka.write_text(do_csv(rekordy), encoding="utf-8-sig")
    elif format_ in ("md", "markdown", "obsidian"):
        sciezka = katalog / rdzen_nazwy
        sciezka.mkdir(parents=True, exist_ok=True)
        for rekord in rekordy:
            (sciezka / f"{nazwa_pliku(rekord)}.md").write_text(do_markdown(rekord),
                                                               encoding="utf-8")
    else:
        raise SystemExit(f"Nieznany format: {format_}")
    return sciezka


def zbuduj_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwerenda",
        description="Kwerenda — przeszukiwanie stron WWW i eksport do Zotero.")
    parser.add_argument("--wersja", action="version", version=f"Kwerenda {__wersja__}")
    parser.add_argument("--baza", default="kwerenda.sqlite3", help="plik bazy (domyślnie ./kwerenda.sqlite3)")
    parser.add_argument("--eksport", default="eksport", help="katalog na pliki eksportu")
    pod = parser.add_subparsers(dest="polecenie")

    p = pod.add_parser("gui", help="uruchom interfejs graficzny w przeglądarce")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--bez-przegladarki", action="store_true")
    p.set_defaults(funkcja=polecenie_gui)

    p = pod.add_parser("uruchom", help="wykonaj kwerendę z pliku konfiguracyjnego")
    p.add_argument("konfig")
    p.add_argument("--zapytanie", help="nadpisz zapytanie z pliku")
    p.add_argument("--format", help="od razu zapisz wynik: ris|csl|bibtex|csv|md")
    p.set_defaults(funkcja=polecenie_uruchom)

    p = pod.add_parser("eksport", help="wyeksportuj trafienia z bazy")
    p.add_argument("--przebieg", type=int)
    p.add_argument("--format", default="ris")
    p.add_argument("--wszystkie", action="store_true", help="także odznaczone")
    p.set_defaults(funkcja=polecenie_eksport)

    p = pod.add_parser("zotero", help="wyślij trafienia do Zotero")
    p.add_argument("--przebieg", type=int)
    p.add_argument("--wszystkie", action="store_true")
    p.add_argument("--klucz", help="klucz Web API (bez tego – lokalny konektor)")
    p.add_argument("--uzytkownik", help="numer użytkownika Zotero")
    p.add_argument("--kolekcja")
    p.set_defaults(funkcja=polecenie_zotero)

    p = pod.add_parser("podglad", help="sprawdź, jakie formy złapie zapytanie")
    p.add_argument("zapytanie")
    p.add_argument("--tryb", default="fleksja", choices=["dokladnie", "fleksja", "rdzen"])
    p.add_argument("--operator", default="I", choices=["I", "LUB"])
    p.add_argument("--bez-ogonkow", action="store_true")
    p.add_argument("--ile", type=int, default=40)
    p.add_argument("--wzorce", action="store_true")
    p.add_argument("--probka", help="tekst do sprawdzenia")
    p.set_defaults(funkcja=polecenie_podglad)

    p = pod.add_parser("przebiegi", help="lista dotychczasowych przebiegów")
    p.add_argument("--ile", type=int, default=30)
    p.set_defaults(funkcja=polecenie_przebiegi)

    p = pod.add_parser("korpus", help="statystyki pobranego korpusu")
    p.add_argument("--wyczysc", action="store_true")
    p.add_argument("--host")
    p.set_defaults(funkcja=polecenie_korpus)
    return parser


def main(argv=None) -> int:
    parser = zbuduj_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "funkcja", None):
        args = parser.parse_args((argv or []) + ["gui"])
    return args.funkcja(args)


if __name__ == "__main__":
    raise SystemExit(main())
