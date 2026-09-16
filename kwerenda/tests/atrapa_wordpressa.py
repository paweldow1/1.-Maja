# -*- coding: utf-8 -*-
"""A fake WordPress site — so tests never touch anybody else's server.

It serves what real sites do: a REST API with pagination and X-WP-TotalPages,
an HTML search (?s=…&paged=N) that — like many real ones — only looks at titles,
a paginated archive listing, a sitemap, an RSS feed, robots.txt, and article
pages carrying JSON-LD. One article sits behind a subscriber cookie, so the
"sign in with your own account" path can be tested too.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

POSTY = [
    {"id": 1, "slug": "obchody-1-maja-zoliborz", "date": "2015-05-02T10:00:00",
     "title": "Obchody 1 Maja na Żoliborzu",
     "content": "<p>W kościele św. Józefa Robotnika odprawiono mszę w intencji ludzi pracy. "
                "Następnie pochód przeszedł ulicami Żoliborza pod sztandarami Solidarności.</p>",
     "author": "Anna Nowak", "categories": [1], "tags": [10]},
    {"id": 2, "slug": "swieto-pracy-w-regionie", "date": "2016-05-01T09:00:00",
     "title": "Święto Pracy w regionie",
     "content": "<p>Uroczystości Święta Pracy odbyły się przed pomnikiem. "
                "Nie było w tym roku pochodu ani mszy.</p>",
     "author": "Jan Kowalski", "categories": [1], "tags": [11]},
    {"id": 3, "slug": "rocznica-porozumien", "date": "2017-08-31T12:00:00",
     "title": "Rocznica porozumień sierpniowych",
     "content": "<p>Delegacja złożyła kwiaty. O 1 maja nie było mowy, ale wspomniano "
                "o ludziach pracy i o Żoliborzu jako dzielnicy robotniczej.</p>",
     "author": "Anna Nowak", "categories": [2], "tags": [10]},
    {"id": 4, "slug": "komunikat-organizacyjny", "date": "2018-03-05T08:00:00",
     "title": "Komunikat organizacyjny",
     "content": "<p>Zebranie zarządu regionu. Sprawy składek i szkoleń.</p>",
     "author": "", "categories": [2], "tags": []},
    {"id": 6, "slug": "tylko-dla-prenumeratorow", "date": "2020-05-01T07:00:00",
     "title": "Relacja z pochodu — tylko dla prenumeratorów",
     "content": "<p>Pełna relacja dostępna w prenumeracie. Pochód, sztandary, msza.</p>",
     "author": "Redakcja", "categories": [1], "tags": [10], "prenumerata": True},
    {"id": 5, "slug": "pochod-pierwszomajowy-1998", "date": "1998-05-01T11:00:00",
     "title": "Pochód pierwszomajowy w Warszawie",
     "content": "<p>Pierwszomajowy pochód ruszył sprzed kościoła świętego Józefa Robotnika. "
                "Uczestnicy nieśli sztandary. Msza rozpoczęła się o dziesiątej.</p>",
     "author": "Redakcja", "categories": [1], "tags": [10, 11]},
]

#: Newsletters published only as PDFs, the way local party branches do it.
ZALACZNIKI = {
    "info-links-05-2019.pdf": {
        "tytul": "Info-Links Mai 2019",
        "autor": "DIE LINKE Lichtenberg",
        "data": "20190415",
        "linie": ["Info-Links Mai 2019", "",
                  "Am 1. Mai laedt die Partei zum Familienfest",
                  "in den Stadtpark ein. Alle sind herzlich eingeladen."],
    },
    "info-links-11-2019.pdf": {
        "tytul": "Info-Links November 2019",
        "autor": "DIE LINKE Lichtenberg",
        "data": "20191105",
        "linie": ["Info-Links November 2019", "",
                  "Bericht von der Mitgliederversammlung.",
                  "Termine im Dezember."],
    },
    "info-links-05-2021.pdf": {"skan": True, "tytul": "Info-Links Mai 2021"},
}

KATEGORIE = {1: "Wydarzenia", 2: "Komunikaty"}
TAGI = {10: "1 maja", 11: "Święto Pracy"}


def _sciezka(post: dict) -> str:
    return f"/{post['date'][:4]}/{post['date'][5:7]}/{post['slug']}"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    baza = ""
    wylacz_api = False
    wymagaj_ciasteczka = ""      # e.g. "sid=secret" — guards the subscriber article

    @classmethod
    def posty(cls):
        """The subscriber-only article exists only when the guard is switched on,
        so the other tests keep working against a stable set of five posts."""
        return [p for p in POSTY if not p.get("prenumerata") or cls.wymagaj_ciasteczka]

    def log_message(self, *args):  # cisza w testach
        pass

    # ---------------- pomocnicze ----------------
    def _bajty(self, dane: bytes, typ: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(dane)))
        self.end_headers()
        self.wfile.write(dane)

    def _odpowiedz(self, tresc: str, typ: str = "text/html; charset=utf-8",
                   status: int = 200, naglowki: dict | None = None):
        dane = tresc.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(dane)))
        for klucz, wartosc in (naglowki or {}).items():
            self.send_header(klucz, wartosc)
        self.end_headers()
        self.wfile.write(dane)

    # ---------------- routing ----------------
    def do_GET(self):
        rozbior = urlparse(self.path)
        sciezka, zapytanie = rozbior.path, parse_qs(rozbior.query)

        if sciezka == "/robots.txt":
            return self._odpowiedz(f"User-agent: *\nDisallow: /wp-admin/\n"
                                   f"Sitemap: {self.baza}/wp-sitemap.xml\n", "text/plain")

        if sciezka.startswith("/wp-json/wp/v2/"):
            if self.wylacz_api:
                return self._odpowiedz('{"code":"rest_no_route"}', "application/json", 404)
            return self._api(sciezka.rsplit("/", 1)[-1], zapytanie)

        if sciezka == "/wp-sitemap.xml":
            wpisy = "".join(
                f"<url><loc>{self.baza}{_sciezka(p)}</loc>"
                f"<lastmod>{p['date'][:10]}</lastmod></url>" for p in self.posty())
            return self._odpowiedz(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{wpisy}</urlset>", "application/xml")

        if sciezka == "/feed":
            wpisy = "".join(
                f"<item><title>{p['title']}</title><link>{self.baza}{_sciezka(p)}</link>"
                f"<pubDate>{p['date']}</pubDate></item>" for p in self.posty()[:3])
            return self._odpowiedz(f"<rss version='2.0'><channel>{wpisy}</channel></rss>",
                                   "application/xml")

        if sciezka == "/" and "s" in zapytanie:
            return self._szukajka(zapytanie)

        if sciezka.startswith("/archiwum"):
            return self._archiwum(sciezka)

        if sciezka == "/partei/info-links":
            return self._odpowiedz(self._strona_z_pdfami())

        if sciezka.startswith("/media/"):
            return self._plik(sciezka.rsplit("/", 1)[-1])

        for post in self.posty():
            if sciezka == _sciezka(post):
                if post.get("prenumerata") and self.wymagaj_ciasteczka:
                    if self.wymagaj_ciasteczka not in (self.headers.get("Cookie") or ""):
                        return self._odpowiedz("<html><body>Zaloguj się</body></html>",
                                               status=403)
                return self._odpowiedz(self._html_posta(post))

        if sciezka == "/":
            linki = "".join(f'<a href="{_sciezka(p)}">{p["title"]}</a>' for p in self.posty())
            return self._odpowiedz(f"<html><body><h1>Strona główna</h1>{linki}</body></html>")

        return self._odpowiedz("<html><body>404</body></html>", status=404)

    # ---------------- REST API ----------------
    def _api(self, zasob: str, zapytanie: dict):
        if zasob == "categories":
            dane = [{"id": i, "name": n} for i, n in KATEGORIE.items()]
            return self._odpowiedz(json.dumps(dane), "application/json")
        if zasob == "tags":
            dane = [{"id": i, "name": n} for i, n in TAGI.items()]
            return self._odpowiedz(json.dumps(dane), "application/json")
        if zasob not in ("posts", "pages"):
            return self._odpowiedz('{"code":"rest_no_route"}', "application/json", 404)
        if zasob == "pages":
            return self._odpowiedz("[]", "application/json", 200,
                                   {"X-WP-TotalPages": "1"})

        wybrane = list(self.posty())
        szukane = (zapytanie.get("search") or [""])[0].lower()
        if szukane:
            # celowo „niedoskonała” wyszukiwarka: tylko tytuł, bez odmiany
            wybrane = [p for p in wybrane if szukane in p["title"].lower()]
        po = (zapytanie.get("after") or [""])[0]
        przed = (zapytanie.get("before") or [""])[0]
        if po:
            wybrane = [p for p in wybrane if p["date"] >= po]
        if przed:
            wybrane = [p for p in wybrane if p["date"] <= przed]

        na_strone = int((zapytanie.get("per_page") or ["10"])[0])
        strona = int((zapytanie.get("page") or ["1"])[0])
        # sztucznie mała paginacja, żeby przetestować przechodzenie stron
        na_strone = min(na_strone, 2)
        stron = max(1, (len(wybrane) + na_strone - 1) // na_strone)
        kawalek = wybrane[(strona - 1) * na_strone: strona * na_strone]

        dane = [{
            "id": p["id"],
            "date": p["date"],
            "date_gmt": p["date"],
            "link": f"{self.baza}{_sciezka(p)}",
            "title": {"rendered": p["title"]},
            "content": {"rendered": p["content"]},
            "excerpt": {"rendered": p["content"][:60]},
            "categories": p["categories"],
            "tags": p["tags"],
            "_embedded": {"author": [{"name": p["author"]}]} if p["author"] else {},
        } for p in kawalek]
        return self._odpowiedz(json.dumps(dane), "application/json", 200,
                               {"X-WP-TotalPages": str(stron)})

    # ---------------- wyszukiwarka HTML ----------------
    def _szukajka(self, zapytanie: dict):
        szukane = (zapytanie.get("s") or [""])[0].lower()
        strona = int((zapytanie.get("paged") or ["1"])[0])
        # like many real site searches, this one only looks at titles
        pasujace = [p for p in self.posty() if szukane in p["title"].lower()]
        na_strone = 2
        kawalek = pasujace[(strona - 1) * na_strone: strona * na_strone]
        wyniki = "".join(
            f'<article><h2 class="entry-title">'
            f'<a rel="bookmark" href="{_sciezka(p)}">{p["title"]}</a></h2></article>'
            for p in kawalek)
        dalej = ""
        if strona * na_strone < len(pasujace):
            dalej = f'<a href="/?s={szukane}&paged={strona + 1}">»</a>'
        return self._odpowiedz(f"<html><body>{wyniki}{dalej}</body></html>")

    # ---------------- strona z załącznikami ----------------
    def _strona_z_pdfami(self):
        """A thin page whose whole content is a list of PDF links."""
        linki = "".join(
            f'<li><a href="/media/{nazwa}">{opis.get("tytul", nazwa)}</a></li>'
            for nazwa, opis in ZALACZNIKI.items())
        return (f'<html lang="de"><head><title>Info-Links | DIE LINKE</title>'
                f'<meta property="og:site_name" content="DIE LINKE Lichtenberg">'
                f'</head><body><article><h1>Info-Links</h1>'
                f"<p>Unsere Mitgliederzeitung zum Herunterladen.</p>"
                f"<ul>{linki}</ul></article></body></html>")

    def _plik(self, nazwa: str):
        from tests.pdf_testowy import zbuduj_pdf, zbuduj_skan
        opis = ZALACZNIKI.get(nazwa)
        if opis is None:
            return self._odpowiedz("<html><body>404</body></html>", status=404)
        if opis.get("skan"):
            return self._bajty(zbuduj_skan(opis.get("tytul", "")), "application/pdf")
        return self._bajty(zbuduj_pdf(opis["linie"], opis.get("tytul", ""),
                                      opis.get("autor", ""), opis.get("data", "")),
                           "application/pdf")

    # ---------------- archiwum z paginacją ----------------
    def _archiwum(self, sciezka: str):
        """A paginated index — the way past a hopeless site search."""
        czesci = [c for c in sciezka.split("/") if c]
        strona = int(czesci[1]) if len(czesci) > 1 and czesci[1].isdigit() else 1
        na_strone = 2
        wszystkie = self.posty()
        kawalek = wszystkie[(strona - 1) * na_strone: strona * na_strone]
        wpisy = "".join(
            f'<article><h2 class="entry-title">'
            f'<a rel="bookmark" href="{_sciezka(p)}">{p["title"]}</a></h2></article>'
            for p in kawalek)
        dalej = f'<a class="next" href="/archiwum/{strona + 1}">next</a>' \
            if strona * na_strone < len(wszystkie) else ""
        return self._odpowiedz(f"<html><body>{wpisy}{dalej}</body></html>")

    # ---------------- strona artykułu ----------------
    def _html_posta(self, post: dict) -> str:
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": post["title"],
            "author": {"@type": "Person", "name": post["author"]} if post["author"] else None,
            "datePublished": post["date"],
            "keywords": [TAGI[t] for t in post["tags"]],
        })
        return (
            f'<html lang="pl"><head><title>{post["title"]} | Atrapa Solidarności</title>'
            f'<meta property="og:site_name" content="Atrapa Solidarności">'
            f'<script type="application/ld+json">{ld}</script></head>'
            f'<body><nav>menu nawigacja</nav><article><h1 class="entry-title">{post["title"]}</h1>'
            f'<div class="entry-content">{post["content"]}</div></article>'
            f'<div id="comments">spam w komentarzach: 1 maja 1 maja</div></body></html>')


class AtrapaWordPressa:
    """Kontekstowy serwer testowy: ``with AtrapaWordPressa() as baza: …``"""

    def __init__(self, wylacz_api: bool = False, wymagaj_ciasteczka: str = ""):
        self.wylacz_api = wylacz_api
        self.wymagaj_ciasteczka = wymagaj_ciasteczka
        self.serwer = None
        self.watek = None
        self.baza = ""

    def __enter__(self) -> str:
        klasa = type("H", (_Handler,), {"wylacz_api": self.wylacz_api,
                                        "wymagaj_ciasteczka": self.wymagaj_ciasteczka})
        self.serwer = ThreadingHTTPServer(("127.0.0.1", 0), klasa)
        port = self.serwer.server_address[1]
        self.baza = f"http://127.0.0.1:{port}"
        klasa.baza = self.baza
        self.watek = threading.Thread(target=self.serwer.serve_forever, daemon=True)
        self.watek.start()
        return self.baza

    def __exit__(self, *args):
        if self.serwer:
            self.serwer.shutdown()
            self.serwer.server_close()
