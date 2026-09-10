# -*- coding: utf-8 -*-
"""Atrapa serwisu na WordPressie – do testów bez ruszania cudzych serwerów.

Udostępnia to, co realne strony regionów „Solidarności”: REST API z paginacją
i nagłówkiem X-WP-TotalPages, wyszukiwarkę HTML (?s=…&paged=N), mapę strony,
robots.txt oraz strony artykułów z JSON-LD.
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
    {"id": 5, "slug": "pochod-pierwszomajowy-1998", "date": "1998-05-01T11:00:00",
     "title": "Pochód pierwszomajowy w Warszawie",
     "content": "<p>Pierwszomajowy pochód ruszył sprzed kościoła świętego Józefa Robotnika. "
                "Uczestnicy nieśli sztandary. Msza rozpoczęła się o dziesiątej.</p>",
     "author": "Redakcja", "categories": [1], "tags": [10, 11]},
]

KATEGORIE = {1: "Wydarzenia", 2: "Komunikaty"}
TAGI = {10: "1 maja", 11: "Święto Pracy"}


def _sciezka(post: dict) -> str:
    return f"/{post['date'][:4]}/{post['date'][5:7]}/{post['slug']}"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    baza = ""
    wylacz_api = False

    def log_message(self, *args):  # cisza w testach
        pass

    # ---------------- pomocnicze ----------------
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
                f"<lastmod>{p['date'][:10]}</lastmod></url>" for p in POSTY)
            return self._odpowiedz(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{wpisy}</urlset>", "application/xml")

        if sciezka == "/feed":
            wpisy = "".join(
                f"<item><title>{p['title']}</title><link>{self.baza}{_sciezka(p)}</link>"
                f"<pubDate>{p['date']}</pubDate></item>" for p in POSTY[:3])
            return self._odpowiedz(f"<rss version='2.0'><channel>{wpisy}</channel></rss>",
                                   "application/xml")

        if sciezka == "/" and "s" in zapytanie:
            return self._szukajka(zapytanie)

        for post in POSTY:
            if sciezka == _sciezka(post):
                return self._odpowiedz(self._html_posta(post))

        if sciezka == "/":
            linki = "".join(f'<a href="{_sciezka(p)}">{p["title"]}</a>' for p in POSTY)
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

        wybrane = list(POSTY)
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
        pasujace = [p for p in POSTY if szukane in (p["title"] + p["content"]).lower()]
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

    def __init__(self, wylacz_api: bool = False):
        self.wylacz_api = wylacz_api
        self.serwer = None
        self.watek = None
        self.baza = ""

    def __enter__(self) -> str:
        klasa = type("H", (_Handler,), {"wylacz_api": self.wylacz_api})
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
