# -*- coding: utf-8 -*-
"""Command line: graphical interface, batch searches, match preview, export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __wersja__
from .cytowania import (Rekord, do_bibtex, do_csl, do_csv, do_markdown, do_ris,
                        nadaj_citekeys, nazwa_pliku)
from .konfiguracja import Konfiguracja
from .magazyn import Magazyn
from .morfologia import (DOMYSLNE, JEZYKI, TRYB_DOKLADNY, TRYB_ODMIANA, Opcje,
                         wykryj_jezyk_tekstu)
from .silnik import Silnik
from .zapytania import BladZapytania, parsuj


def _magazyn(args) -> Magazyn:
    return Magazyn(args.database)


def _katalog_eksportu(args) -> Path:
    katalog = Path(args.exports)
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


# --------------------------------------------------------------------------
def polecenie_gui(args) -> int:
    from .serwer import uruchom_serwer
    uruchom_serwer(_magazyn(args), _katalog_eksportu(args), port=args.port,
                   otworz=not args.no_browser)
    return 0


def polecenie_run(args) -> int:
    konfig = Konfiguracja.wczytaj(args.config)
    if args.query:
        konfig.zapytanie = args.query
    if args.languages:
        konfig.jezyki = [k.strip() for k in args.languages.split(",") if k.strip()]
    for uwaga in konfig.sprawdz():
        print(f"⚠ {uwaga}", file=sys.stderr)

    magazyn = _magazyn(args)
    silnik = Silnik(konfig, magazyn, log=lambda w: print(w, flush=True))
    przebieg = silnik.uruchom()

    trafienia = magazyn.trafienia(przebieg)
    print(f"\nHits: {len(trafienia)} (run #{przebieg})")
    if args.format:
        sciezka = _zapisz(trafienia, args.format, _katalog_eksportu(args),
                          f"{nazwa_pliku(Rekord(tytul=konfig.nazwa))}-{przebieg}")
        print(f"Saved: {sciezka}")
    return 0


def polecenie_export(args) -> int:
    magazyn = _magazyn(args)
    trafienia = magazyn.trafienia(args.run, tylko_wybrane=not args.all)
    if not trafienia:
        print("Nothing to export.", file=sys.stderr)
        return 1
    sciezka = _zapisz(trafienia, args.format, _katalog_eksportu(args),
                      f"search-{args.run or 'all'}")
    print(f"Saved {len(trafienia)} records: {sciezka}")
    return 0


def polecenie_zotero(args) -> int:
    from .zotero import wyslij_do_konektora, wyslij_przez_api
    magazyn = _magazyn(args)
    trafienia = magazyn.trafienia(args.run, tylko_wybrane=not args.all)
    rekordy = nadaj_citekeys([Rekord.z_trafienia(t) for t in trafienia])
    if args.key and args.user:
        wynik = wyslij_przez_api(rekordy, args.key, args.user, args.collection or "")
    else:
        wynik = wyslij_do_konektora(rekordy)
    print(wynik["komunikat"])
    for blad in wynik.get("bledy", [])[:10]:
        print("  ! " + blad, file=sys.stderr)
    return 0 if wynik.get("ok") else 1


def polecenie_preview(args) -> int:
    jezyki = tuple(k.strip() for k in (args.languages or ",".join(DOMYSLNE)).split(",")
                   if k.strip() in JEZYKI)
    opcje = Opcje(jezyki=jezyki or tuple(DOMYSLNE),
                  rozszerzaj_wszystko=args.expand_all,
                  bez_ogonkow=args.ignore_diacritics)
    try:
        drzewo = parsuj(args.query, opcje, args.operator)
    except BladZapytania as exc:
        print(f"Query error: {exc}", file=sys.stderr)
        return 1

    print("Read as:", drzewo.opis())
    for termin in drzewo.terminy():
        print(f"\n• {termin.tekst}   [field: {termin.pole}, mode: {termin.tryb}]")
        if termin.tryb == TRYB_DOKLADNY:
            print("  exact match only — add * to inflect it")
        for kod, formy in termin.formy(args.count).items():
            nazwa = JEZYKI[kod].nazwa if kod in JEZYKI else kod
            print(f"  {nazwa:<10} {', '.join(formy)}")
        if args.patterns:
            print("  pattern:", termin.wzorzec())
    if args.sample:
        from .zapytania import Dokument, cytaty
        dokument = Dokument(tekst=args.sample)
        pasuje, trafienia = drzewo.ocen(dokument)
        print("\nSample:", "MATCHES" if pasuje else "does not match",
              f"(language guess: {wykryj_jezyk_tekstu(args.sample) or 'unknown'})")
        for cytat in cytaty(dokument, trafienia, 80, 3):
            print("  …" + cytat["fragment"])
    return 0


def polecenie_runs(args) -> int:
    for przebieg in _magazyn(args).przebiegi(args.count):
        print(f"#{przebieg['id']:>4}  {przebieg['status']:<10} {przebieg['trafien']:>4} hits  "
              f"{przebieg['nazwa']}  |  {przebieg['zapytanie']}")
    return 0


def polecenie_corpus(args) -> int:
    magazyn = _magazyn(args)
    if args.clear:
        print(f"Removed {magazyn.wyczysc_korpus(args.host or '')} pages from the corpus.")
        return 0
    for wpis in magazyn.statystyki_korpusu():
        print(f"{wpis['host']:<44} {wpis['ile']:>6} pages")
    return 0


def polecenie_languages(args) -> int:
    for jezyk in JEZYKI.values():
        print(f"{jezyk.kod}  {jezyk.nazwa:<12} {jezyk.pismo:<9} "
              f"{len(jezyk.koncowki)} endings")
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
        raise SystemExit(f"Unknown format: {format_}")
    return sciezka


def zbuduj_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwerenda",
        description="Kwerenda — search websites for content and export to Zotero.")
    parser.add_argument("--version", action="version", version=f"Kwerenda {__wersja__}")
    parser.add_argument("--database", default="kwerenda.sqlite3",
                        help="database file (default ./kwerenda.sqlite3)")
    parser.add_argument("--exports", default="exports", help="directory for exported files")
    pod = parser.add_subparsers(dest="command")

    p = pod.add_parser("gui", help="open the graphical interface in a browser")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(funkcja=polecenie_gui)

    p = pod.add_parser("run", help="run a search from a configuration file")
    p.add_argument("config")
    p.add_argument("--query", help="override the query from the file")
    p.add_argument("--languages", help="comma-separated language codes, e.g. pl,en,de")
    p.add_argument("--format", help="write the result straight away: ris|csl|bibtex|csv|md")
    p.set_defaults(funkcja=polecenie_run)

    p = pod.add_parser("export", help="export stored hits")
    p.add_argument("--run", type=int)
    p.add_argument("--format", default="ris")
    p.add_argument("--all", action="store_true", help="include unselected hits")
    p.set_defaults(funkcja=polecenie_export)

    p = pod.add_parser("zotero", help="send hits to Zotero")
    p.add_argument("--run", type=int)
    p.add_argument("--all", action="store_true")
    p.add_argument("--key", help="Web API key (without it the local connector is used)")
    p.add_argument("--user", help="Zotero user id")
    p.add_argument("--collection")
    p.set_defaults(funkcja=polecenie_zotero)

    p = pod.add_parser("preview", help="see which forms a query will match")
    p.add_argument("query")
    p.add_argument("--languages", help="comma-separated codes, e.g. pl,de,uk")
    p.add_argument("--operator", default="AND", choices=["AND", "OR"])
    p.add_argument("--expand-all", action="store_true",
                   help="treat every term as if it ended with *")
    p.add_argument("--ignore-diacritics", action="store_true")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--patterns", action="store_true")
    p.add_argument("--sample", help="text to test the query against")
    p.set_defaults(funkcja=polecenie_preview)

    p = pod.add_parser("runs", help="list previous runs")
    p.add_argument("--count", type=int, default=30)
    p.set_defaults(funkcja=polecenie_runs)

    p = pod.add_parser("corpus", help="statistics of the downloaded corpus")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--host")
    p.set_defaults(funkcja=polecenie_corpus)

    p = pod.add_parser("languages", help="list supported languages")
    p.set_defaults(funkcja=polecenie_languages)
    return parser


def main(argv=None) -> int:
    parser = zbuduj_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "funkcja", None):
        args = parser.parse_args((argv or []) + ["gui"])
    return args.funkcja(args)


if __name__ == "__main__":
    raise SystemExit(main())
