# -*- coding: utf-8 -*-
"""The local server behind the graphical interface (standard library only).

Bound to 127.0.0.1 — nothing is exposed to the outside world. The interface is
a single HTML file talking to this JSON API.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from . import __wersja__
from .cytowania import (Rekord, do_bibtex, do_csl, do_csv, do_markdown, do_ris,
                        do_zotero, nadaj_citekeys, nazwa_pliku)
from .konfiguracja import Konfiguracja
from .magazyn import Magazyn
from .morfologia import (JEZYKI, TRYB_DOKLADNY, TRYB_ODMIANA, Opcje, czy_pasuje,
                         wykryj_jezyk_tekstu)
from .pliki import dostepne_silniki
from .silnik import Silnik
from .zapytania import BladZapytania, parsuj
from .zotero import kolekcje as zotero_kolekcje
from .zotero import konektor_dziala, wyslij_do_konektora, wyslij_przez_api

KATALOG_WEB = Path(__file__).parent / "web"


class Stan:
    """Shared server state: database, current run, export and preset directories."""

    def __init__(self, magazyn: Magazyn, katalog_eksportu: Path,
                 katalog_presetow: Optional[Path] = None,
                 katalog_przykladow: Optional[Path] = None):
        self.magazyn = magazyn
        self.katalog_eksportu = katalog_eksportu
        self.katalog_eksportu.mkdir(parents=True, exist_ok=True)
        self.katalog_presetow = Path(katalog_presetow or "presets")
        self.katalog_presetow.mkdir(parents=True, exist_ok=True)
        self.katalog_przykladow = Path(katalog_przykladow) if katalog_przykladow else None
        self.silnik: Optional[Silnik] = None
        self.watek: Optional[threading.Thread] = None
        self.ostatni_przebieg: Optional[int] = None

    @property
    def trwa(self) -> bool:
        return bool(self.watek and self.watek.is_alive())


def _trafienie_en(wiersz: dict) -> dict:
    """Database row (Polish column names) → the English shape the interface uses."""
    return {
        "id": wiersz.get("id"),
        "run": wiersz.get("przebieg_id"),
        "url": wiersz.get("url", ""),
        "host": wiersz.get("host", ""),
        "title": wiersz.get("tytul", ""),
        "authors": wiersz.get("autorzy", []),
        "date": wiersz.get("data", ""),
        "site": wiersz.get("serwis", ""),
        "publisher": wiersz.get("wydawca", ""),
        "language": wiersz.get("jezyk", ""),
        "type": wiersz.get("typ", ""),
        "citekey": wiersz.get("citekey", ""),
        "terms": wiersz.get("terminy", []),
        "tags": wiersz.get("tagi", []),
        "quotes": [{"text": c.get("fragment", ""), "forms": c.get("formy", []),
                    "field": c.get("pole", "")} for c in wiersz.get("cytaty", [])],
        "note": wiersz.get("notatka", ""),
        "selected": bool(wiersz.get("wybrane", 1)),
        "meta": wiersz.get("meta", {}),
    }


_POLA_EDYCJI = {"title": "tytul", "date": "data", "site": "serwis", "publisher": "wydawca",
                "language": "jezyk", "type": "typ", "citekey": "citekey", "note": "notatka",
                "selected": "wybrane", "tags": "tagi", "authors": "autorzy"}


def _przebieg_en(wiersz: dict) -> dict:
    return {"id": wiersz.get("id"), "name": wiersz.get("nazwa", ""),
            "query": wiersz.get("zapytanie", ""), "status": wiersz.get("status", ""),
            "hits": wiersz.get("trafien", 0), "started": wiersz.get("start")}


def _slug(nazwa: str) -> str:
    from .cytowania import ascii_slug
    czesci = [ascii_slug(k).lower() for k in re.split(r"[\s_]+", nazwa or "") if k.strip()]
    return "-".join(c for c in czesci if c)[:60] or "preset"


def presety_z_plikow(katalog: Path) -> List[dict]:
    """Every configuration file in the presets directory.

    A preset is a file, not a hidden row in a database: you can read it, put it
    in version control, mail it to somebody, and run it from the command line.
    """
    wynik = []
    for wzorzec in ("*.yaml", "*.yml", "*.json"):
        for plik in sorted(katalog.glob(wzorzec)):
            try:
                konfig = Konfiguracja.wczytaj(plik)
            except Exception as exc:
                wynik.append({"name": plik.stem, "file": plik.name, "source": "file",
                              "error": str(exc)[:200], "config": {}})
                continue
            wynik.append({"name": konfig.nazwa or plik.stem, "file": plik.name,
                          "source": "file", "config": konfig.jako_dict()})
    return wynik


def lista_presetow(stan: Stan) -> List[dict]:
    """Your own presets first, then the examples shipped with the program.

    Yours live in your data folder and survive an update; the examples travel
    with the code. A file of yours with the same name hides the example.
    """
    moje = presety_z_plikow(stan.katalog_presetow)
    pliki = {p["file"] for p in moje}
    nazwy = {p["name"] for p in moje}

    przyklady = []
    if stan.katalog_przykladow and stan.katalog_przykladow.is_dir() \
            and stan.katalog_przykladow.resolve() != stan.katalog_presetow.resolve():
        for preset in presety_z_plikow(stan.katalog_przykladow):
            if preset["file"] in pliki or preset["name"] in nazwy:
                continue
            preset["source"] = "example"
            przyklady.append(preset)
            nazwy.add(preset["name"])

    z_bazy = [{"name": p["nazwa"], "config": p["konfig"], "source": "database"}
              for p in stan.magazyn.presety() if p["nazwa"] not in nazwy]
    return moje + przyklady + z_bazy


def zapisz_preset_do_pliku(stan: Stan, nazwa: str, konfig: dict) -> Path:
    konfiguracja = Konfiguracja.z_dict(konfig)
    konfiguracja.nazwa = nazwa or konfiguracja.nazwa
    rozszerzenie = ".yaml"
    try:
        import yaml  # noqa: F401
    except ImportError:
        rozszerzenie = ".json"
    sciezka = stan.katalog_presetow / f"{_slug(konfiguracja.nazwa)}{rozszerzenie}"
    konfiguracja.zapisz(sciezka)
    return sciezka


def _rekordy(stan: Stan, dane: dict) -> List[Rekord]:
    identyfikatory = dane.get("ids") or None
    przebieg = dane.get("run")
    trafienia = stan.magazyn.trafienia(
        przebieg_id=int(przebieg) if przebieg else None,
        tylko_wybrane=bool(dane.get("selected_only")),
        identyfikatory=[int(i) for i in identyfikatory] if identyfikatory else None)
    rekordy = [Rekord.z_trafienia(t) for t in trafienia]
    if dane.get("zotero_type"):
        for rekord in rekordy:
            rekord.typ = dane["zotero_type"]
    return nadaj_citekeys(rekordy)


class Obsluga(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    stan: Stan = None                       # type: ignore[assignment]
    cichy: bool = True

    def log_message(self, format, *args):   # noqa: A002
        if not self.cichy:
            super().log_message(format, *args)

    # ------------------------------------------------------------------
    def _wyslij(self, tresc: bytes, typ: str = "application/json; charset=utf-8",
                status: int = 200, naglowki: Optional[dict] = None):
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(tresc)))
        self.send_header("Cache-Control", "no-store")
        for klucz, wartosc in (naglowki or {}).items():
            self.send_header(klucz, wartosc)
        self.end_headers()
        try:
            self.wfile.write(tresc)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, dane: Any, status: int = 200):
        self._wyslij(json.dumps(dane, ensure_ascii=False, default=str).encode("utf-8"),
                     status=status)

    def _cialo(self) -> dict:
        dlugosc = int(self.headers.get("Content-Length") or 0)
        if not dlugosc:
            return {}
        try:
            return json.loads(self.rfile.read(dlugosc).decode("utf-8"))
        except ValueError:
            return {}

    # ------------------------------------------------------------------
    def do_GET(self):
        rozbior = urlparse(self.path)
        try:
            if rozbior.path in ("/", "/index.html"):
                return self._wyslij((KATALOG_WEB / "index.html").read_bytes(),
                                    "text/html; charset=utf-8")
            if rozbior.path.startswith("/api/"):
                return self._api_get(rozbior.path[5:], parse_qs(rozbior.query))
            return self._wyslij(b"not found", "text/plain; charset=utf-8", 404)
        except Exception:
            traceback.print_exc()
            return self._json({"error": traceback.format_exc(limit=3)}, 500)

    def do_POST(self):
        sciezka = urlparse(self.path).path
        try:
            if sciezka.startswith("/api/"):
                return self._api_post(sciezka[5:], self._cialo())
            return self._wyslij(b"not found", "text/plain; charset=utf-8", 404)
        except Exception:
            traceback.print_exc()
            return self._json({"error": traceback.format_exc(limit=3)}, 500)

    # ------------------------------------------------------------------
    def _api_get(self, zasob: str, pytania: Dict[str, List[str]]):
        stan = self.stan

        if zasob == "state":
            dziala, komunikat = konektor_dziala()
            return self._json({
                "version": __wersja__,
                "running": stan.trwa,
                "zotero": {"connector": dziala, "message": komunikat},
                "languages": [{"code": j.kod, "name": j.nazwa, "script": j.pismo}
                              for j in JEZYKI.values()],
                "pdf_engines": dostepne_silniki(),
                "corpus": [{"host": k["host"], "pages": k["ile"], "last": k["ostatnio"]}
                           for k in stan.magazyn.statystyki_korpusu()],
                "presets": lista_presetow(stan),
                "presets_dir": str(stan.katalog_presetow.resolve()),
                "data_dir": str(stan.katalog_presetow.resolve().parent),
                "runs": [_przebieg_en(p) for p in stan.magazyn.przebiegi(30)],
                "last_run": stan.ostatni_przebieg,
                "settings": stan.magazyn.ustawienie("interface", {}),
                "export_dir": str(stan.katalog_eksportu),
            })

        if zasob == "progress":
            silnik = stan.silnik
            if not silnik:
                return self._json({"running": False, "progress": {}, "log": []})
            od = int((pytania.get("from") or ["0"])[0])
            postep = silnik.postep.jako_dict()
            return self._json({
                "running": stan.trwa,
                "run": silnik.przebieg_id,
                "progress": {
                    "status": postep.get("status"), "source": postep.get("zrodlo"),
                    "candidates": postep.get("kandydatow"), "checked": postep.get("sprawdzonych"),
                    "hits": postep.get("trafien"), "fetched": postep.get("pobran"),
                    "from_corpus": postep.get("z_cache"), "errors": postep.get("bledow"),
                    "seconds": postep.get("sekundy"),
                },
                "log": silnik.dziennik[od:],
                "log_total": len(silnik.dziennik),
            })

        if zasob == "hits":
            przebieg = (pytania.get("run") or [""])[0]
            return self._json({"hits": [_trafienie_en(t) for t in stan.magazyn.trafienia(
                int(przebieg) if przebieg else None)]})

        if zasob == "zotero/collections":
            try:
                return self._json({"collections": zotero_kolekcje(
                    (pytania.get("key") or [""])[0], (pytania.get("user") or [""])[0])})
            except Exception as exc:
                return self._json({"error": str(exc)}, 400)

        if zasob == "file":
            nazwa = unquote((pytania.get("name") or [""])[0])
            plik = (stan.katalog_eksportu / nazwa).resolve()
            if not str(plik).startswith(str(stan.katalog_eksportu.resolve())) \
                    or not plik.is_file():
                return self._wyslij(b"not found", "text/plain; charset=utf-8", 404)
            return self._wyslij(
                plik.read_bytes(), "application/octet-stream",
                naglowki={"Content-Disposition": f'attachment; filename="{plik.name}"'})

        return self._json({"error": "unknown resource"}, 404)

    # ------------------------------------------------------------------
    def _api_post(self, zasob: str, dane: dict):
        stan = self.stan

        if zasob == "preview":
            return self._podglad(dane)

        if zasob == "start":
            if stan.trwa:
                return self._json({"error": "A search is already running — stop it first."}, 409)
            konfig = Konfiguracja.z_dict(dane.get("config") or {})
            try:
                parsuj(konfig.zapytanie, konfig.opcje_morfologii(), konfig.domyslny_operator)
            except BladZapytania as exc:
                return self._json({"error": str(exc)}, 400)
            stan.magazyn.ustaw("interface", dane.get("config") or {})
            silnik = Silnik(konfig, stan.magazyn)
            stan.silnik = silnik
            przebieg = stan.magazyn.nowy_przebieg(konfig.nazwa, konfig.zapytanie,
                                                  konfig.jako_dict())
            stan.ostatni_przebieg = przebieg
            stan.watek = threading.Thread(target=silnik.uruchom, args=(przebieg,), daemon=True)
            stan.watek.start()
            return self._json({"run": przebieg, "warnings": konfig.sprawdz()})

        if zasob == "stop":
            if stan.silnik:
                stan.silnik.przerwij()
            return self._json({"ok": True})

        if zasob == "hit":
            trafienie_id = int(dane.pop("id"))
            pola = {_POLA_EDYCJI[k]: v for k, v in dane.items() if k in _POLA_EDYCJI}
            if "wybrane" in pola:
                pola["wybrane"] = 1 if pola["wybrane"] else 0
            stan.magazyn.zmien_trafienie(trafienie_id, **pola)
            return self._json({"ok": True})

        if zasob == "delete-hits":
            stan.magazyn.usun_trafienia([int(i) for i in dane.get("ids") or []])
            return self._json({"ok": True})

        if zasob == "delete-run":
            stan.magazyn.usun_przebieg(int(dane["run"]))
            return self._json({"ok": True})

        if zasob == "export":
            return self._eksport(dane)

        if zasob == "zotero":
            rekordy = _rekordy(stan, dane)
            if not rekordy:
                return self._json({"ok": False, "message": "No records selected."})
            if dane.get("mode") == "api":
                wynik = wyslij_przez_api(rekordy, dane.get("key", ""), dane.get("user", ""),
                                         dane.get("collection", ""))
            else:
                wynik = wyslij_do_konektora(rekordy)
            return self._json({"ok": wynik.get("ok"), "sent": wynik.get("wyslane"),
                               "errors": wynik.get("bledy", []),
                               "message": wynik.get("komunikat", "")})

        if zasob == "preset":
            sciezka = zapisz_preset_do_pliku(stan, dane.get("name", ""),
                                             dane.get("config") or {})
            return self._json({"ok": True, "file": sciezka.name,
                               "message": f"Saved as {sciezka}"})

        if zasob == "preset/delete":
            plik = dane.get("file")
            if plik:
                cel = (stan.katalog_presetow / plik).resolve()
                if str(cel).startswith(str(stan.katalog_presetow.resolve())) and cel.is_file():
                    cel.unlink()
                    return self._json({"ok": True})
                return self._json({"error": "no such preset file"}, 404)
            stan.magazyn.usun_preset(dane.get("name", ""))
            return self._json({"ok": True})

        if zasob == "corpus/clear":
            ile = stan.magazyn.wyczysc_korpus(dane.get("host", ""))
            return self._json({"ok": True, "removed": ile})

        return self._json({"error": "unknown resource"}, 404)

    # ------------------------------------------------------------------
    def _podglad(self, dane: dict):
        opcje = Opcje(
            jezyki=tuple(k for k in (dane.get("languages") or JEZYKI.keys()) if k in JEZYKI),
            rozszerzaj_wszystko=bool(dane.get("expand_all")),
            bez_ogonkow=bool(dane.get("ignore_diacritics")),
            wyklucz=tuple(dane.get("excluded_forms") or []))
        try:
            drzewo = parsuj(dane.get("query", ""), opcje,
                            dane.get("default_operator", "AND"))
        except BladZapytania as exc:
            return self._json({"error": str(exc)})

        terminy = []
        for termin in drzewo.terminy():
            terminy.append({
                "text": termin.tekst,
                "field": {"tresc": "content", "wszystko": "all", "tytul": "title",
                          "tekst": "text", "autor": "author", "tagi": "tags",
                          "url": "url"}.get(termin.pole, termin.pole),
                "mode": termin.tryb,
                "pattern": termin.wzorzec(),
                "forms": termin.formy(24),
            })
        wynik: Dict[str, Any] = {"description": drzewo.opis(), "terms": terminy}

        probka = (dane.get("sample") or "").strip()
        if probka:
            from .zapytania import Dokument, cytaty
            dokument = Dokument(tekst=probka)
            pasuje, trafienia = drzewo.ocen(dokument)
            wynik["sample"] = {
                "matches": pasuje,
                "forms": sorted({t.forma for t in trafienia}),
                "language": wykryj_jezyk_tekstu(probka),
                "quotes": [{"text": c["fragment"], "forms": c["formy"]}
                           for c in cytaty(dokument, trafienia, 90, 3)],
            }
        slowo = (dane.get("word") or "").strip()
        if slowo:
            wynik["word"] = {t["text"]: czy_pasuje(slowo, t["text"], opcje,
                                                   t["mode"] or TRYB_DOKLADNY)
                             for t in terminy}
        return self._json(wynik)

    # ------------------------------------------------------------------
    def _eksport(self, dane: dict):
        rekordy = _rekordy(self.stan, dane)
        if not rekordy:
            return self._json({"ok": False, "message": "No records selected."})
        format_ = (dane.get("format") or "ris").lower()
        znacznik = time.strftime("%Y%m%d-%H%M%S")
        katalog = self.stan.katalog_eksportu

        if format_ == "ris":
            nazwa = f"search-{znacznik}.ris"
            (katalog / nazwa).write_text(do_ris(rekordy), encoding="utf-8")
        elif format_ in ("csl", "csl-json", "json"):
            nazwa = f"search-{znacznik}.csl.json"
            (katalog / nazwa).write_text(
                json.dumps(do_csl(rekordy), ensure_ascii=False, indent=2), encoding="utf-8")
        elif format_ in ("bib", "bibtex"):
            nazwa = f"search-{znacznik}.bib"
            (katalog / nazwa).write_text(do_bibtex(rekordy), encoding="utf-8")
        elif format_ == "csv":
            nazwa = f"search-{znacznik}.csv"
            (katalog / nazwa).write_text(do_csv(rekordy), encoding="utf-8-sig")
        elif format_ in ("md", "markdown", "obsidian"):
            nazwa = f"obsidian-{znacznik}.zip"
            with zipfile.ZipFile(katalog / nazwa, "w", zipfile.ZIP_DEFLATED) as archiwum:
                for rekord in rekordy:
                    archiwum.writestr(f"{nazwa_pliku(rekord)}.md", do_markdown(rekord))
        elif format_ == "zotero-json":
            nazwa = f"zotero-{znacznik}.json"
            (katalog / nazwa).write_text(
                json.dumps([do_zotero(r) for r in rekordy], ensure_ascii=False, indent=2),
                encoding="utf-8")
        else:
            return self._json({"ok": False, "message": f"Unknown format: {format_}"}, 400)

        return self._json({"ok": True, "name": nazwa, "count": len(rekordy),
                           "path": str(katalog / nazwa),
                           "message": f"Saved {len(rekordy)} records to {nazwa}."})


def zwiaz_serwer(klasa, host: str, port: int, ile_prob: int = 12) -> ThreadingHTTPServer:
    """Bind the first free port at or after `port`.

    The port may well be taken — by a second copy of Kwerenda, or by anything
    else on the machine. Sliding to the next one beats greeting somebody who
    just double-clicked an icon with a stack trace.
    """
    for kandydat in range(port, port + ile_prob):
        try:
            return ThreadingHTTPServer((host, kandydat), klasa)
        except OSError:
            continue
    print(f"Ports {port}–{port + ile_prob - 1} are all busy. Close whatever is using "
          f"them, or start on a different one:  python -m kwerenda gui --port 9000",
          file=sys.stderr)
    raise SystemExit(1)


def uruchom_serwer(magazyn: Magazyn, katalog_eksportu: Path, port: int = 8765,
                   host: str = "127.0.0.1", otworz: bool = True,
                   katalog_presetow: Optional[Path] = None,
                   katalog_przykladow: Optional[Path] = None) -> None:
    klasa = type("ObslugaZeStanem", (Obsluga,),
                 {"stan": Stan(magazyn, katalog_eksportu, katalog_presetow,
                               katalog_przykladow)})

    serwer = zwiaz_serwer(klasa, host, port)
    if serwer.server_address[1] != port:
        print(f"Port {port} was busy — using {serwer.server_address[1]} instead.")

    adres = f"http://{host}:{serwer.server_address[1]}"
    print(f"Kwerenda {__wersja__} — interface at {adres}")
    print("Stop with Ctrl+C")
    if otworz:
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(adres)).start()
        except Exception:
            pass
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        serwer.shutdown()
        serwer.server_close()
