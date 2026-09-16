# -*- coding: utf-8 -*-
"""Command line: graphical interface, batch searches, match preview, export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from . import __wersja__
from .cytowania import (Rekord, do_bibtex, do_csl, do_csv, do_markdown, do_ris,
                        nadaj_citekeys, nazwa_pliku)
from .dane import (katalog_danych, katalog_eksportu, katalog_presetow,
                   katalog_przykladow, przenies_stare_dane, sciezka_bazy)
from .konfiguracja import Konfiguracja
from .magazyn import Magazyn
from .morfologia import (DOMYSLNE, JEZYKI, TRYB_DOKLADNY, TRYB_ODMIANA, Opcje,
                         wykryj_jezyk_tekstu)
from .silnik import Silnik
from .zapytania import BladZapytania, parsuj


def _magazyn(args) -> Magazyn:
    przenies_stare_dane(lambda w: print(w, file=sys.stderr))
    return Magazyn(args.database or sciezka_bazy())


def _katalog_eksportu(args) -> Path:
    katalog = Path(args.exports) if args.exports else katalog_eksportu()
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def _katalog_presetow(args) -> Path:
    wskazany = getattr(args, "presets", None)
    katalog = Path(wskazany) if wskazany else katalog_presetow()
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def _znajdz_preset(args, wskazanie: str) -> Path:
    """Accept either a path to a configuration file or the name of a preset.

    ``run presets/may-day.yaml`` and ``run may-day`` both work, so nobody has to
    remember where the folder lives.
    """
    sciezka = Path(wskazanie)
    if sciezka.is_file():
        return sciezka
    katalog = _katalog_presetow(args)
    for kandydat in (wskazanie, f"{wskazanie}.yaml", f"{wskazanie}.yml", f"{wskazanie}.json"):
        if (katalog / kandydat).is_file():
            return katalog / kandydat
    dostepne = sorted(p.stem for wzorzec in ("*.yaml", "*.yml", "*.json")
                      for p in katalog.glob(wzorzec))
    raise SystemExit(f"No such preset or file: {wskazanie}\n"
                     f"Available in {katalog}/: {', '.join(dostepne) or '(none)'}")


# --------------------------------------------------------------------------
def polecenie_gui(args) -> int:
    from .serwer import uruchom_serwer
    uruchom_serwer(_magazyn(args), _katalog_eksportu(args), port=args.port,
                   otworz=not args.no_browser, katalog_presetow=_katalog_presetow(args),
                   katalog_przykladow=katalog_przykladow())
    return 0


def polecenie_run(args) -> int:
    konfig = Konfiguracja.wczytaj(_znajdz_preset(args, args.config))
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


def polecenie_presets(args) -> int:
    from .serwer import presety_z_plikow
    katalog = _katalog_presetow(args)
    presety = presety_z_plikow(katalog)
    nazwy = {p["file"] for p in presety}
    presety += [p for p in presety_z_plikow(katalog_przykladow())
                if p["file"] not in nazwy]
    if not presety:
        print(f"No presets in {katalog}/. Save one from the interface, or copy "
              f"an example from the presets/ folder of the repository.")
        return 0
    print(f"Presets in {katalog}/:\n")
    for preset in presety:
        if preset.get("error"):
            print(f"  {preset['file']:<34} ! cannot be read: {preset['error']}")
            continue
        konfig = Konfiguracja.z_dict(preset["config"])
        zrodla = ", ".join(z.etykieta for z in konfig.zrodla) or "—"
        print(f"  {Path(preset['file']).stem:<28} {preset['name']}")
        print(f"  {'':<28} query:   {konfig.zapytanie.strip()[:80]}")
        print(f"  {'':<28} sources: {zrodla[:80]}\n")
    print(f"Run one with:  python -m kwerenda run {Path(presety[0]['file']).stem}")
    return 0


def polecenie_where(args) -> int:
    przenies_stare_dane(lambda w: print(w))
    print(f"Your work      {katalog_danych()}")
    print(f"  corpus       {args.database or sciezka_bazy()}")
    print(f"  your presets {_katalog_presetow(args)}")
    print(f"  exports      {_katalog_eksportu(args)}")
    print(f"\nThe program    {katalog_przykladow().parent}")
    print(f"  examples     {katalog_przykladow()}")
    print("\nUpdating means replacing the program folder only. "
          "Set KWERENDA_HOME to keep your work somewhere else.")
    return 0


def polecenie_doctor(args) -> int:
    """Check everything the interface needs, and say what is wrong in plain words."""
    import socket

    klopoty: List[str] = []

    def zdaj(etykieta: str, ok: bool, szczegol: str = "", rada: str = "",
             konieczna: bool = True) -> None:
        # Something optional that is broken is not "ok" — saying so would hide
        # exactly the kind of half-installed library that is worth knowing about.
        znacznik = "ok  " if ok else ("FAIL" if konieczna else "warn")
        print(f"  {znacznik}  {etykieta:<22} {szczegol}")
        if not ok and rada:
            klopoty.append(rada)

    print(f"Kwerenda {__wersja__}\n")
    print("Python")
    wersja = sys.version_info
    zdaj("version", wersja >= (3, 9), f"{wersja.major}.{wersja.minor}.{wersja.micro}",
         "Python 3.9 or newer is needed — install it from python.org.")
    zdaj("interpreter", True, sys.executable)

    print("\nLibraries")
    for nazwa, konieczna, rada in (
            ("requests", True, "pip install -r requirements.txt"),
            ("bs4", True, "pip install -r requirements.txt"),
            ("pypdf", False, "pip install pypdf — without it PDF attachments are skipped"),
            ("yaml", False, "pip install pyyaml — without it presets must be JSON")):
        try:
            modul = __import__(nazwa)
            zdaj(nazwa, True, getattr(modul, "__version__", ""))
        except BaseException as exc:
            zdaj(nazwa, False, f"{type(exc).__name__}: {str(exc)[:60]}", rada,
                 konieczna=konieczna)

    print("\nPDF readers")
    from .pliki import dostepne_silniki
    silniki = dostepne_silniki()
    zdaj("available", bool(silniki), ", ".join(silniki) or "none",
         "No PDF reader: run pip install pypdf, otherwise PDFs will be skipped.")

    print("\nYour work")
    katalog = katalog_danych()
    proba = katalog / ".zapis-probny"
    try:
        proba.write_text("x", encoding="utf-8")
        proba.unlink()
        zapisywalny = True
    except OSError as exc:
        zapisywalny = False
        print(f"        ({exc})")
    zdaj("folder", zapisywalny, str(katalog),
         f"Cannot write to {katalog} — set KWERENDA_HOME to a folder you can write to.")
    zdaj("corpus", True, str(args.database or sciezka_bazy()))

    print("\nThe interface")
    port = 8765
    gniazdo = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        gniazdo.bind(("127.0.0.1", port))
        wolny = True
    except OSError:
        wolny = False
    finally:
        gniazdo.close()
    zdaj(f"port {port}", True, "free" if wolny
         else "busy — Kwerenda will use the next one")

    from .zotero import konektor_dziala
    dziala, komunikat = konektor_dziala()
    zdaj("Zotero", True, komunikat if dziala else "not running (that is fine — export a RIS file)")

    if klopoty:
        print("\nWhat to do:")
        for rada in klopoty:
            print(f"  • {rada}")
        return 1
    print("\nEverything the interface needs is in place. Start it with: "
          "python -m kwerenda gui")
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
    parser.add_argument("--database", default=None,
                        help=f"database file (default {sciezka_bazy()})")
    parser.add_argument("--exports", default=None,
                        help="directory for exported files")
    parser.add_argument("--presets", default=None,
                        help="directory holding your preset files")
    pod = parser.add_subparsers(dest="command")

    p = pod.add_parser("gui", help="open the graphical interface in a browser")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(funkcja=polecenie_gui)

    p = pod.add_parser("run", help="run a search from a preset or a configuration file")
    p.add_argument("config", help="a preset name (see: kwerenda presets) or a path to a file")
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

    p = pod.add_parser("presets", help="list the saved presets")
    p.set_defaults(funkcja=polecenie_presets)

    p = pod.add_parser("doctor", help="check that everything needed is in place")
    p.set_defaults(funkcja=polecenie_doctor)

    p = pod.add_parser("where", help="show where your work is kept")
    p.set_defaults(funkcja=polecenie_where)

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
