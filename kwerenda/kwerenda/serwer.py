# -*- coding: utf-8 -*-
"""Lokalny serwer interfejsu graficznego (biblioteka standardowa, bez Flaska).

Uruchamiany na 127.0.0.1 – nic nie wystawia na zewnątrz. Interfejs to jeden
plik HTML, komunikujący się z tym API JSON-em.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from . import __wersja__
from .cytowania import (Rekord, do_bibtex, do_csl, do_csv, do_markdown, do_ris,
                        do_zotero, nadaj_citekeys, nazwa_pliku)
from .fleksja import FlexOptions, czy_pasuje, przykladowe_formy
from .konfiguracja import Konfiguracja
from .magazyn import Magazyn
from .silnik import Silnik
from .zapytania import BladZapytania, parsuj
from .zotero import kolekcje as zotero_kolekcje
from .zotero import konektor_dziala, wyslij_do_konektora, wyslij_przez_api

KATALOG_WEB = Path(__file__).parent / "web"


class Stan:
    """Wspólny stan serwera: baza, bieżący przebieg, katalog eksportu."""

    def __init__(self, magazyn: Magazyn, katalog_eksportu: Path):
        self.magazyn = magazyn
        self.katalog_eksportu = katalog_eksportu
        self.katalog_eksportu.mkdir(parents=True, exist_ok=True)
        self.silnik: Optional[Silnik] = None
        self.watek: Optional[threading.Thread] = None
        self.ostatni_przebieg: Optional[int] = None

    @property
    def trwa(self) -> bool:
        return bool(self.watek and self.watek.is_alive())


def _rekordy(stan: Stan, dane: dict) -> List[Rekord]:
    identyfikatory = dane.get("ids") or None
    przebieg = dane.get("przebieg")
    trafienia = stan.magazyn.trafienia(
        przebieg_id=int(przebieg) if przebieg else None,
        tylko_wybrane=bool(dane.get("tylko_wybrane")),
        identyfikatory=[int(i) for i in identyfikatory] if identyfikatory else None)
    rekordy = [Rekord.z_trafienia(t) for t in trafienia]
    if dane.get("typ_zotero"):
        for rekord in rekordy:
            rekord.typ = dane["typ_zotero"]
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
        sciezka = rozbior.path
        pytania = parse_qs(rozbior.query)
        try:
            if sciezka in ("/", "/index.html"):
                plik = KATALOG_WEB / "index.html"
                return self._wyslij(plik.read_bytes(), "text/html; charset=utf-8")
            if sciezka.startswith("/api/"):
                return self._api_get(sciezka[5:], pytania)
            return self._wyslij(b"nie znaleziono", "text/plain; charset=utf-8", 404)
        except Exception:
            traceback.print_exc()
            return self._json({"blad": traceback.format_exc(limit=3)}, 500)

    def do_POST(self):
        sciezka = urlparse(self.path).path
        try:
            if sciezka.startswith("/api/"):
                return self._api_post(sciezka[5:], self._cialo())
            return self._wyslij(b"nie znaleziono", "text/plain; charset=utf-8", 404)
        except Exception:
            traceback.print_exc()
            return self._json({"blad": traceback.format_exc(limit=3)}, 500)

    # ------------------------------------------------------------------
    def _api_get(self, zasob: str, pytania: Dict[str, List[str]]):
        stan = self.stan
        if zasob == "stan":
            dziala, komunikat = konektor_dziala()
            return self._json({
                "wersja": __wersja__,
                "trwa": stan.trwa,
                "zotero": {"konektor": dziala, "komunikat": komunikat},
                "korpus": stan.magazyn.statystyki_korpusu(),
                "presety": stan.magazyn.presety(),
                "przebiegi": stan.magazyn.przebiegi(30),
                "ostatni_przebieg": stan.ostatni_przebieg,
                "ustawienia": stan.magazyn.ustawienie("interfejs", {}),
                "katalog_eksportu": str(stan.katalog_eksportu),
            })

        if zasob == "postep":
            silnik = stan.silnik
            if not silnik:
                return self._json({"trwa": False, "postep": {}, "dziennik": []})
            od = int((pytania.get("od") or ["0"])[0])
            return self._json({
                "trwa": stan.trwa,
                "przebieg": silnik.przebieg_id,
                "postep": silnik.postep.jako_dict(),
                "dziennik": silnik.dziennik[od:],
                "razem_dziennik": len(silnik.dziennik),
            })

        if zasob == "trafienia":
            przebieg = (pytania.get("przebieg") or [""])[0]
            return self._json({"trafienia": stan.magazyn.trafienia(
                int(przebieg) if przebieg else None)})

        if zasob == "zotero/kolekcje":
            klucz = (pytania.get("klucz") or [""])[0]
            uzytkownik = (pytania.get("uzytkownik") or [""])[0]
            try:
                return self._json({"kolekcje": zotero_kolekcje(klucz, uzytkownik)})
            except Exception as exc:
                return self._json({"blad": str(exc)}, 400)

        if zasob == "plik":
            nazwa = unquote((pytania.get("nazwa") or [""])[0])
            plik = (self.stan.katalog_eksportu / nazwa).resolve()
            if not str(plik).startswith(str(self.stan.katalog_eksportu.resolve())) \
                    or not plik.is_file():
                return self._wyslij(b"nie znaleziono", "text/plain; charset=utf-8", 404)
            return self._wyslij(
                plik.read_bytes(), "application/octet-stream",
                naglowki={"Content-Disposition": f'attachment; filename="{plik.name}"'})

        return self._json({"blad": "nieznany zasób"}, 404)

    # ------------------------------------------------------------------
    def _api_post(self, zasob: str, dane: dict):
        stan = self.stan

        if zasob == "podglad":
            return self._podglad(dane)

        if zasob == "start":
            if stan.trwa:
                return self._json({"blad": "Kwerenda już trwa – zatrzymaj ją najpierw."}, 409)
            konfig = Konfiguracja.z_dict(dane.get("konfig") or {})
            try:
                parsuj(konfig.zapytanie, konfig.opcje_fleksji(), konfig.domyslny_operator)
            except BladZapytania as exc:
                return self._json({"blad": str(exc)}, 400)
            stan.magazyn.ustaw("interfejs", dane.get("konfig") or {})
            silnik = Silnik(konfig, stan.magazyn)
            stan.silnik = silnik
            przebieg = stan.magazyn.nowy_przebieg(konfig.nazwa, konfig.zapytanie,
                                                  konfig.jako_dict())
            stan.ostatni_przebieg = przebieg
            stan.watek = threading.Thread(target=silnik.uruchom, args=(przebieg,), daemon=True)
            stan.watek.start()
            return self._json({"przebieg": przebieg, "uwagi": konfig.sprawdz()})

        if zasob == "stop":
            if stan.silnik:
                stan.silnik.przerwij()
            return self._json({"ok": True})

        if zasob == "trafienie":
            stan.magazyn.zmien_trafienie(int(dane.pop("id")), **dane)
            return self._json({"ok": True})

        if zasob == "usun-trafienia":
            stan.magazyn.usun_trafienia([int(i) for i in dane.get("ids") or []])
            return self._json({"ok": True})

        if zasob == "usun-przebieg":
            stan.magazyn.usun_przebieg(int(dane["przebieg"]))
            return self._json({"ok": True})

        if zasob == "eksport":
            return self._eksport(dane)

        if zasob == "zotero":
            rekordy = _rekordy(stan, dane)
            if not rekordy:
                return self._json({"ok": False, "komunikat": "Nie wybrano żadnych rekordów."})
            if dane.get("tryb") == "api":
                wynik = wyslij_przez_api(rekordy, dane.get("klucz", ""),
                                         dane.get("uzytkownik", ""), dane.get("kolekcja", ""))
            else:
                wynik = wyslij_do_konektora(rekordy)
            return self._json(wynik)

        if zasob == "preset":
            stan.magazyn.zapisz_preset(dane["nazwa"], dane.get("konfig") or {})
            return self._json({"ok": True, "presety": stan.magazyn.presety()})

        if zasob == "preset/usun":
            stan.magazyn.usun_preset(dane["nazwa"])
            return self._json({"ok": True, "presety": stan.magazyn.presety()})

        if zasob == "korpus/wyczysc":
            ile = stan.magazyn.wyczysc_korpus(dane.get("host", ""))
            return self._json({"ok": True, "usuniete": ile})

        return self._json({"blad": "nieznany zasób"}, 404)

    # ------------------------------------------------------------------
    def _podglad(self, dane: dict):
        opcje = FlexOptions(mode=dane.get("tryb_fleksji", "fleksja"),
                            fold_diacritics=bool(dane.get("bez_ogonkow")),
                            wyklucz=tuple(dane.get("wykluczone_formy") or []))
        try:
            drzewo = parsuj(dane.get("zapytanie", ""), opcje,
                            dane.get("domyslny_operator", "I"))
        except BladZapytania as exc:
            return self._json({"blad": str(exc)})

        terminy = []
        for termin in drzewo.terminy():
            terminy.append({
                "tekst": termin.tekst,
                "pole": termin.pole,
                "tryb": termin.opcje_efektywne().mode,
                "wzorzec": termin.wzorzec(),
                "formy": termin.formy(48),
            })
        wynik = {"opis": drzewo.opis(), "terminy": terminy}

        probka = (dane.get("probka") or "").strip()
        if probka:
            from .zapytania import Dokument, cytaty
            dokument = Dokument(tytul="", tekst=probka)
            pasuje, trafienia = drzewo.ocen(dokument)
            wynik["probka"] = {
                "pasuje": pasuje,
                "formy": sorted({t.forma for t in trafienia}),
                "cytaty": cytaty(dokument, trafienia, 90, 3),
            }
        slowo = (dane.get("slowo") or "").strip()
        if slowo:
            wynik["slowo"] = {
                t["tekst"]: czy_pasuje(slowo, t["tekst"], opcje) for t in terminy}
        return self._json(wynik)

    # ------------------------------------------------------------------
    def _eksport(self, dane: dict):
        rekordy = _rekordy(self.stan, dane)
        if not rekordy:
            return self._json({"ok": False, "komunikat": "Nie wybrano żadnych rekordów."})
        format_ = (dane.get("format") or "ris").lower()
        znacznik = time.strftime("%Y%m%d-%H%M%S")
        katalog = self.stan.katalog_eksportu

        if format_ == "ris":
            nazwa = f"kwerenda-{znacznik}.ris"
            (katalog / nazwa).write_text(do_ris(rekordy), encoding="utf-8")
        elif format_ in ("csl", "csl-json", "json"):
            nazwa = f"kwerenda-{znacznik}.csl.json"
            (katalog / nazwa).write_text(
                json.dumps(do_csl(rekordy), ensure_ascii=False, indent=2), encoding="utf-8")
        elif format_ in ("bib", "bibtex"):
            nazwa = f"kwerenda-{znacznik}.bib"
            (katalog / nazwa).write_text(do_bibtex(rekordy), encoding="utf-8")
        elif format_ == "csv":
            nazwa = f"kwerenda-{znacznik}.csv"
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
            return self._json({"ok": False, "komunikat": f"Nieznany format: {format_}"}, 400)

        return self._json({"ok": True, "nazwa": nazwa, "ile": len(rekordy),
                           "sciezka": str(katalog / nazwa),
                           "komunikat": f"Zapisano {len(rekordy)} rekordów do {nazwa}."})


def uruchom_serwer(magazyn: Magazyn, katalog_eksportu: Path, port: int = 8765,
                   host: str = "127.0.0.1", otworz: bool = True) -> None:
    klasa = type("ObslugaZeStanem", (Obsluga,),
                 {"stan": Stan(magazyn, katalog_eksportu)})
    serwer = ThreadingHTTPServer((host, port), klasa)
    adres = f"http://{host}:{serwer.server_address[1]}"
    print(f"Kwerenda {__wersja__} — interfejs pod adresem {adres}")
    print("Zatrzymanie: Ctrl+C")
    if otworz:
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(adres)).start()
        except Exception:
            pass
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        print("\nKończę.")
    finally:
        serwer.shutdown()
        serwer.server_close()
