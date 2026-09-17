# -*- coding: utf-8 -*-
"""Tests: morphology, query parser, extraction, sources, engine, export."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

from kwerenda.cytowania import (Rekord, do_bibtex, do_csl, do_csv, do_markdown,
                                do_ris, do_zotero, nadaj_citekeys)
from kwerenda.ekstrakcja import normalizuj_date, wyciagnij_metadane, wyciagnij_tekst
from kwerenda.konfiguracja import Konfiguracja
from kwerenda.magazyn import Magazyn
from kwerenda.morfologia import (TRYB_DOKLADNY, TRYB_ODMIANA, TRYB_RDZEN, Opcje,
                                 czy_pasuje, formy_wg_jezykow, wykryj_jezyk_tekstu)
from kwerenda.silnik import Silnik
from kwerenda.zapytania import BladZapytania, Dokument, cytaty, parsuj
from kwerenda.zrodla import Zrodlo, _okna_dat, _parsuj_sitemap, _wyglada_na_artykul
from tests.atrapa_wordpressa import AtrapaWordPressa


class TestMorfologiaPolska(unittest.TestCase):
    OPCJE = Opcje(jezyki=("pl",))

    def test_odmiana(self):
        for baza, forma in [("Żoliborz", "Żoliborzu"), ("Żoliborz", "Żoliborza"),
                            ("święto", "święcie"), ("święto", "świąt"),
                            ("praca", "pracy"), ("praca", "pracach"),
                            ("Gdańsk", "Gdańsku"), ("pochód", "pochodu"),
                            ("Solidarność", "Solidarności"), ("msza", "mszy"),
                            ("robotnik", "robotników"), ("sztandar", "sztandarami")]:
            with self.subTest(baza=baza, forma=forma):
                self.assertTrue(czy_pasuje(forma, baza, self.OPCJE, TRYB_ODMIANA))

    def test_nie_lapie_obcych_slow(self):
        for baza, obce in [("praca", "prawo"), ("msza", "maszyna"), ("maj", "majątek"),
                           ("Gdańsk", "gdakanie"), ("pochód", "pochwała")]:
            with self.subTest(baza=baza, obce=obce):
                self.assertFalse(czy_pasuje(obce, baza, self.OPCJE, TRYB_ODMIANA))

    def test_bez_ogonkow(self):
        opcje = Opcje(jezyki=("pl",), bez_ogonkow=True)
        self.assertTrue(czy_pasuje("Zoliborzu", "Żoliborz", opcje, TRYB_ODMIANA))
        self.assertTrue(czy_pasuje("swieto pracy", "święto", opcje, TRYB_ODMIANA))

    def test_wykluczanie_formy(self):
        opcje = Opcje(jezyki=("pl",), wyklucz=("mają",))
        self.assertFalse(czy_pasuje("mają", "maj", opcje, TRYB_ODMIANA))
        self.assertTrue(czy_pasuje("maja", "maj", opcje, TRYB_ODMIANA))


class TestMorfologiaWieloJezyczna(unittest.TestCase):
    def _pasuje(self, forma, baza, kody):
        return czy_pasuje(forma, baza, Opcje(jezyki=tuple(kody)), TRYB_ODMIANA)

    def test_angielski(self):
        for baza, forma in [("strike", "strikes"), ("strike", "striking"),
                            ("demonstration", "demonstrations"), ("city", "cities"),
                            ("stop", "stopped"), ("worker", "workers")]:
            with self.subTest(baza=baza, forma=forma):
                self.assertTrue(self._pasuje(forma, baza, ["en"]))
        self.assertFalse(self._pasuje("strict", "strike", ["en"]))

    def test_niemiecki_z_przeglosem(self):
        for baza, forma in [("Mann", "Männer"), ("Buch", "Bücher"),
                            ("Streik", "Streiks"), ("Gewerkschaft", "Gewerkschaften"),
                            ("Arbeiter", "Arbeitern")]:
            with self.subTest(baza=baza, forma=forma):
                self.assertTrue(self._pasuje(forma, baza, ["de"]))

    def test_rosyjski(self):
        for baza, forma in [("забастовка", "забастовки"), ("забастовка", "забастовках"),
                            ("праздник", "празднике"), ("рабочий", "рабочих")]:
            with self.subTest(baza=baza, forma=forma):
                self.assertTrue(self._pasuje(forma, baza, ["ru"]))

    def test_ukrainski(self):
        for baza, forma in [("страйк", "страйку"), ("свято", "свята"),
                            ("робітник", "робітники")]:
            with self.subTest(baza=baza, forma=forma):
                self.assertTrue(self._pasuje(forma, baza, ["uk"]))

    def test_pismo_wybiera_jezyki(self):
        """A Cyrillic term must never be expanded with Latin-script endings."""
        formy = formy_wg_jezykow("страйк", Opcje(), TRYB_ODMIANA)
        self.assertEqual(set(formy), {"ru", "uk"})
        formy = formy_wg_jezykow("Streik", Opcje(), TRYB_ODMIANA)
        self.assertEqual(set(formy), {"pl", "en", "de"})

    def test_wykrywanie_jezyka_tekstu(self):
        próbki = {
            "pl": "Robotnicy i związkowcy nie byli na pochodzie w Warszawie",
            "en": "The workers of the world were marching on the first of May",
            "de": "Die Arbeiter und der Gewerkschaftsbund haben in Berlin demonstriert",
            "ru": "Рабочие и профсоюзы в Москве не были на празднике",
            "uk": "Робітники і профспілки в Києві не були на святі",
        }
        for oczekiwany, tekst in próbki.items():
            with self.subTest(jezyk=oczekiwany):
                self.assertEqual(wykryj_jezyk_tekstu(tekst), oczekiwany)


class TestGwiazdka(unittest.TestCase):
    """The asterisk is the standard truncation mark; a bare term is exact."""

    def setUp(self):
        self.dok = Dokument(tytul="Streiks und Demonstrationen",
                            tekst="Die Gewerkschaft rief zum Streik auf. Arbeiter kamen.")

    def _ocen(self, zapytanie, **kw):
        return parsuj(zapytanie, Opcje(**kw)).ocen(self.dok)[0]

    def test_bez_gwiazdki_dokladnie(self):
        self.assertTrue(self._ocen("Streik"))
        self.assertFalse(self._ocen("Demonstration"))

    def test_gwiazdka_odmienia(self):
        self.assertTrue(self._ocen("Demonstration*"))
        self.assertTrue(self._ocen("Arbeiter*"))

    def test_dwie_gwiazdki_ucinaja(self):
        self.assertTrue(self._ocen("Demonstr**"))
        self.assertFalse(self._ocen("Demonstr*"))
        # a German derivational ending is part of the inflection table, so a
        # single star already reaches Gewerkschaft from Gewerk
        self.assertTrue(self._ocen("Gewerk*"))

    def test_rozszerzaj_wszystko(self):
        self.assertTrue(self._ocen("Demonstration", rozszerzaj_wszystko=True))

    def test_fraza_z_gwiazdka(self):
        dok = Dokument(tekst="W kościele św. Józefa Robotnika odprawiono mszę.")
        self.assertTrue(parsuj('"Józef Robotnik"*').ocen(dok)[0])
        self.assertFalse(parsuj('"Józef Robotnik"').ocen(dok)[0])


class TestZapytania(unittest.TestCase):
    def setUp(self):
        self.dok = Dokument(
            tytul="Obchody 1 Maja na Żoliborzu",
            tekst="W kościele św. Józefa Robotnika odprawiono mszę. Pochód przeszedł "
                  "ulicami. Sztandary Solidarności powiewały.",
            url="https://przyklad.pl/2015/05/obchody", autor="Anna Nowak", tagi=["Mazowsze"])

    def _ocen(self, zapytanie):
        return parsuj(zapytanie).ocen(self.dok)[0]

    def test_operatory_angielskie(self):
        self.assertTrue(self._ocen('"1 Maja" AND Żoliborzu'))
        self.assertTrue(self._ocen('Żoliborzu OR Katowice'))
        self.assertFalse(self._ocen('Katowice OR Wrocław'))
        self.assertFalse(self._ocen('mszę NOT Sztandary'))
        self.assertTrue(self._ocen('mszę NOT Katowice'))
        self.assertFalse(self._ocen('mszę -Sztandary'))

    def test_operatory_polskie_nadal_dzialaja(self):
        self.assertTrue(self._ocen('"1 Maja" I Żoliborzu'))
        self.assertTrue(self._ocen('Żoliborzu LUB Katowice'))
        self.assertTrue(self._ocen('mszę NIE Katowice'))

    def test_domyslny_operator_to_koniunkcja(self):
        self.assertTrue(self._ocen('mszę Pochód'))
        self.assertFalse(self._ocen('mszę Katowice'))

    def test_nawiasy(self):
        self.assertTrue(self._ocen('"1 Maja" AND (Katowice OR Żoliborzu)'))
        self.assertFalse(self._ocen('"1 Maja" AND (Katowice OR Wrocław)'))

    def test_pola(self):
        self.assertTrue(self._ocen('title:Żoliborzu'))
        self.assertFalse(self._ocen('title:Sztandary'))
        self.assertTrue(self._ocen('text:Sztandary'))
        self.assertTrue(self._ocen('author:Nowak'))
        self.assertTrue(self._ocen('url:2015'))
        self.assertTrue(self._ocen('tags:Mazowsze'))
        # by default we search the content, so a bare tag or address is not a hit
        self.assertFalse(self._ocen('Mazowsze'))
        self.assertTrue(self._ocen('all:Mazowsze'))
        self.assertTrue(self._ocen('title:"1 Maja"'))
        self.assertFalse(self._ocen('title:"Sztandary Solidarności"'))

    def test_sasiedztwo(self):
        self.assertTrue(self._ocen('kościele NEAR/3 Józefa'))
        self.assertFalse(self._ocen('kościele NEAR/2 Solidarności'))
        self.assertTrue(self._ocen('kościele ~30 Solidarności'))
        self.assertTrue(self._ocen('kościele BLISKO/3 Józefa'))

    def test_modyfikatory_prefiksowe(self):
        self.assertTrue(self._ocen('=Sztandary'))
        self.assertFalse(self._ocen('=Sztandar'))
        self.assertTrue(self._ocen('~Sztandar'))
        self.assertTrue(self._ocen('^Sztandar'))

    def test_bledy_skladni(self):
        with self.assertRaises(BladZapytania):
            parsuj('(msza AND')
        with self.assertRaises(BladZapytania):
            parsuj('msza)')

    def test_puste_zapytanie_lapie_wszystko(self):
        self.assertTrue(parsuj("").ocen(self.dok)[0])

    def test_cytaty_z_kontekstem(self):
        ok, trafienia = parsuj('"Józef Robotnik"*').ocen(self.dok)
        fragmenty = cytaty(self.dok, trafienia, okno=40)
        self.assertTrue(ok)
        self.assertIn("Józefa Robotnika", fragmenty[0]["fragment"])
        self.assertEqual(fragmenty[0]["pole"], "text")


class TestEkstrakcja(unittest.TestCase):
    HTML = """<html lang="pl"><head><title>Tytuł | Serwis</title>
      <meta property="og:site_name" content="Serwis">
      <meta name="author" content="Jan Kowalski">
      <meta property="article:published_time" content="2015-05-02T10:00:00+02:00">
      </head><body><nav>menu</nav>
      <article><div class="entry-content"><p>Treść artykułu o pochodzie.</p></div></article>
      <div id="comments">komentarz</div></body></html>"""

    def test_metadane(self):
        meta = wyciagnij_metadane(self.HTML, "https://serwis.pl/a")
        self.assertEqual(meta.tytul, "Tytuł")
        self.assertEqual(meta.autorzy, ["Jan Kowalski"])
        self.assertEqual(meta.data, "2015-05-02")
        self.assertEqual(meta.nazwa_serwisu, "Serwis")
        self.assertEqual(meta.jezyk, "pl")

    def test_tresc_bez_menu_i_komentarzy(self):
        tekst = wyciagnij_tekst(self.HTML)
        self.assertIn("pochodzie", tekst)
        self.assertNotIn("menu", tekst)
        self.assertNotIn("komentarz", tekst)

    def test_daty_pieciu_jezykow(self):
        self.assertEqual(normalizuj_date("2 maja 2015"), "2015-05-02")
        self.assertEqual(normalizuj_date("1. Mai 2019"), "2019-05-01")
        self.assertEqual(normalizuj_date("9 травня 2020"), "2020-05-09")
        self.assertEqual(normalizuj_date("9 мая 2020"), "2020-05-09")
        self.assertEqual(normalizuj_date("May 1, 2001"), "2001-05-01")
        self.assertEqual(normalizuj_date("12.05.1998"), "1998-05-12")
        self.assertEqual(normalizuj_date("no date here"), "")

    def test_data_z_adresu(self):
        meta = wyciagnij_metadane("<html><body><h1>X</h1></body></html>",
                                  "https://a.pl/2016/05/tekst")
        self.assertEqual(meta.data, "2016-05")


class TestZrodlaPomocnicze(unittest.TestCase):
    def test_cykliczne_okno_majowe(self):
        okna = _okna_dat(Zrodlo(url="a.pl", od_roku=2014, do_roku=2016, okno_dat="04-25:05-05"))
        self.assertEqual(len(okna), 3)
        self.assertTrue(okna[0][0].startswith("2014-04-25"))
        self.assertTrue(okna[2][1].startswith("2016-05-05"))

    def test_sitemap(self):
        mapy, adresy = _parsuj_sitemap(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://a.pl/x</loc><lastmod>2015-05-02</lastmod></url></urlset>')
        self.assertEqual(adresy, [("https://a.pl/x", "2015-05-02")])
        mapy, adresy = _parsuj_sitemap(
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<sitemap><loc>https://a.pl/s1.xml</loc></sitemap></sitemapindex>')
        self.assertEqual(mapy, ["https://a.pl/s1.xml"])

    def test_rozpoznawanie_adresow_artykulow(self):
        self.assertTrue(_wyglada_na_artykul("https://a.pl/2015/05/obchody-1-maja"))
        self.assertTrue(_wyglada_na_artykul("https://a.pl/kraj/artykul-o-pochodzie,123456"))
        self.assertFalse(_wyglada_na_artykul("https://a.pl/tag/1-maja"))
        self.assertFalse(_wyglada_na_artykul("https://a.pl/logo.png"))

    def test_klucze_angielskie_i_polskie(self):
        angielskie = Zrodlo.z_dict({"url": "https://a.pl", "max_pages": 7,
                                    "search_url": "https://a.pl/s?q={q}", "full_sweep": True})
        self.assertEqual(angielskie.max_stron, 7)
        self.assertEqual(angielskie.szablon_szukania, "https://a.pl/s?q={q}")
        self.assertTrue(angielskie.pelne_przemiatanie)
        self.assertEqual(angielskie.jako_dict()["max_pages"], 7)
        polskie = Zrodlo.z_dict({"url": "https://a.pl", "max_stron": 9, "tryb": "szukajka"})
        self.assertEqual(polskie.max_stron, 9)
        self.assertEqual(polskie.tryb, "search")


class TestSilnikNaAtrapie(unittest.TestCase):
    def _konfig(self, baza, **kw):
        konfig = Konfiguracja(
            nazwa="test",
            zapytanie=kw.pop("zapytanie", '"1 maja"* AND (Żoliborz* OR "Józef Robotnik"*)'),
            kontakt="test@example.org", opoznienie=0.0, watki=1,
            jezyki=kw.pop("jezyki", ["pl"]),
            uzyj_cache=kw.pop("uzyj_cache", True),
            zrodla=[Zrodlo(url=baza, nazwa="Fixture", tryb=kw.pop("tryb", "auto"),
                           **kw.pop("zrodlo", {}))])
        for klucz, wartosc in kw.items():
            setattr(konfig, klucz, wartosc)
        return konfig

    def _uruchom(self, konfig, magazyn=None):
        magazyn = magazyn or Magazyn(":memory:")
        silnik = Silnik(konfig, magazyn)
        przebieg = silnik.uruchom()
        return silnik, magazyn, magazyn.trafienia(przebieg)

    def test_rest_api_i_weryfikacja_tresci(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza))
        adresy = {t["url"] for t in trafienia}
        self.assertEqual(len(trafienia), 1, [t["tytul"] for t in trafienia])
        self.assertTrue(any("zoliborz" in a for a in adresy))
        self.assertFalse(any("komunikat" in a for a in adresy))

    def test_metadane_i_tagi(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza))
        wpis = [t for t in trafienia if "zoliborz" in t["url"]][0]
        self.assertEqual(wpis["tytul"], "Obchody 1 Maja na Żoliborzu")
        self.assertEqual(wpis["autorzy"], ["Anna Nowak"])
        self.assertEqual(wpis["data"], "2015-05-02")
        self.assertIn("Wydarzenia", wpis["tagi"])      # CMS category
        self.assertIn("1 maja", wpis["tagi"])
        self.assertIn("2015", wpis["tagi"])            # year
        self.assertIn("Polish", wpis["tagi"])          # detected language
        self.assertEqual(wpis["jezyk"], "pl")
        self.assertTrue(wpis["citekey"].startswith("nowak2015"))
        self.assertTrue(wpis["cytaty"][0]["fragment"])

    def test_fallback_na_html_gdy_api_wylaczone(self):
        with AtrapaWordPressa(wylacz_api=True) as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza))
        self.assertGreaterEqual(len(trafienia), 1)
        self.assertTrue(all(t["tytul"] for t in trafienia))

    def test_tryb_sitemap(self):
        with AtrapaWordPressa(wylacz_api=True) as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza, tryb="sitemap"))
        # the sitemap lists everything, so the 2017 piece that merely mentions
        # "1 maja" and "Żoliborzu" is a legitimate hit as well
        self.assertEqual(len(trafienia), 2)

    def test_szablon_wyszukiwarki(self):
        """A supplied search template works where auto-detection would flounder."""
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(
                baza, zapytanie="pochód*", tryb="search",
                zrodlo={"szablon_szukania": baza + "/?s={q}&paged={page}"}))
        self.assertGreaterEqual(len(trafienia), 1)

    def test_szablon_listy_omija_wyszukiwarke(self):
        """listing_url walks the archive and ignores the site's search entirely."""
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(
                baza, zapytanie="sztandar*", tryb="listing",
                zrodlo={"szablon_listy": baza + "/archiwum/{page}"}))
        self.assertEqual(len(trafienia), 2)

    def test_pelne_przemiatanie_znajduje_to_czego_szukajka_nie_widzi(self):
        """The fixture, like many real ones, only searches titles."""
        with AtrapaWordPressa() as baza:
            _, _, bez = self._uruchom(self._konfig(baza, zapytanie="sztandar*",
                                                   tryb="wordpress"))
            _, _, z_przemiataniem = self._uruchom(self._konfig(
                baza, zapytanie="sztandar*", tryb="wordpress",
                zrodlo={"pelne_przemiatanie": True}))
        self.assertEqual(bez, [])
        self.assertEqual(len(z_przemiataniem), 2)
        formy = {f for t in z_przemiataniem for c in t["cytaty"] for f in c["formy"]}
        self.assertEqual(formy, {"sztandarami", "sztandary"})

    def test_auto_schodzi_nizej_gdy_api_nic_nie_zwraca(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza, zapytanie="sztandar*"))
        self.assertEqual(len(trafienia), 2)
        self.assertEqual({t["meta"]["skad"] for t in trafienia}, {"sitemap"})

    def test_okno_dat(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(
                baza, zapytanie="pochód*",
                zrodlo={"od_roku": 2015, "do_roku": 2016, "okno_dat": "04-25:05-05",
                        "pelne_przemiatanie": True}))
        self.assertEqual(sorted(t["data"] for t in trafienia),
                         ["2015-05-02", "2016-05-01"])

    def test_korpus_dziala_bez_sieci(self):
        magazyn = Magazyn(":memory:")
        with AtrapaWordPressa() as baza:
            self._uruchom(self._konfig(baza, zapytanie="",
                                       zrodlo={"pelne_przemiatanie": True}), magazyn)
        konfig = Konfiguracja(nazwa="corpus", zapytanie="sztandar*", opoznienie=0.0,
                              jezyki=["pl"], zrodla=[Zrodlo(url="", tryb="corpus")])
        przebieg = Silnik(konfig, magazyn).uruchom()
        self.assertGreaterEqual(len(magazyn.trafienia(przebieg)), 1)

    def test_przerwanie(self):
        with AtrapaWordPressa() as baza:
            magazyn = Magazyn(":memory:")
            silnik = Silnik(self._konfig(baza, zapytanie=""), magazyn)
            silnik.przerwij()
            przebieg = silnik.uruchom()
        self.assertEqual(magazyn.przebieg(przebieg)["status"], "stopped")

    def test_robots_txt_jest_respektowany(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(
                baza, tryb="urls", zrodlo={"lista_url": [f"{baza}/wp-admin/tajne"]}))
        self.assertEqual(trafienia, [])

    def test_wlasne_ciasteczka_trafiaja_do_zadania(self):
        """Content behind your own login: the cookie has to reach the server."""
        with AtrapaWordPressa(wymagaj_ciasteczka="sid=tajne") as baza:
            _, _, bez = self._uruchom(self._konfig(
                baza, zapytanie="prenumerata*", tryb="urls",
                zrodlo={"lista_url": [f"{baza}/2020/05/tylko-dla-prenumeratorow"]}))
            _, _, z_ciasteczkiem = self._uruchom(self._konfig(
                baza, zapytanie="prenumerata*", tryb="urls",
                zrodlo={"lista_url": [f"{baza}/2020/05/tylko-dla-prenumeratorow"],
                        "ciasteczka": "sid=tajne"}))
        self.assertEqual(bez, [])
        self.assertEqual(len(z_ciasteczkiem), 1)

    def test_tagi_bez_gwiazdek(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(
                baza, zapytanie="pierwszomaj*", zrodlo={"pelne_przemiatanie": True}))
        tagi = {t for wpis in trafienia for t in wpis["tagi"]}
        self.assertIn("pierwszomaj", tagi)
        self.assertNotIn("pierwszomaj*", tagi)


class TestZalaczniki(unittest.TestCase):
    """PDFs hanging off a page are the source, not an asset to be skipped."""

    ZAPYTANIE = '"1. Mai"* AND (Familienfest OR Maifest)'

    def setUp(self):
        from kwerenda.pliki import dostepne_silniki
        if not dostepne_silniki():
            self.skipTest("no PDF backend available (pip install pypdf)")

    def _uruchom(self, baza, **kw):
        zrodlo = {"lista_url": [f"{baza}/partei/info-links"]}
        zrodlo.update(kw.pop("zrodlo", {}))
        konfig = Konfiguracja(
            nazwa="pdf", zapytanie=kw.pop("zapytanie", self.ZAPYTANIE),
            jezyki=["de"], opoznienie=0.0, watki=1, kontakt="test@example.org",
            zrodla=[Zrodlo(url=baza, nazwa="DIE LINKE Lichtenberg", tryb="urls", **zrodlo)])
        for klucz, wartosc in kw.items():
            setattr(konfig, klucz, wartosc)
        magazyn = Magazyn(":memory:")
        silnik = Silnik(konfig, magazyn)
        przebieg = silnik.uruchom()
        return silnik, magazyn.trafienia(przebieg)

    def test_znajduje_tresc_w_pdf_ie_podlinkowanym_ze_strony(self):
        with AtrapaWordPressa() as baza:
            silnik, trafienia = self._uruchom(baza)
        self.assertEqual(len(trafienia), 1, [t["tytul"] for t in trafienia])
        wpis = trafienia[0]
        self.assertTrue(wpis["url"].endswith("info-links-05-2019.pdf"))
        self.assertEqual(wpis["tytul"], "Info-Links Mai 2019")
        self.assertEqual(wpis["autorzy"], ["DIE LINKE Lichtenberg"])
        self.assertIn("Familienfest", wpis["cytaty"][0]["fragment"])
        self.assertEqual(silnik.postep.zalacznikow, 3)     # all three were read

    def test_data_bierze_sie_z_nazwy_pliku(self):
        """A newsletter's file name carries the issue date; the PDF's own
        creation date (here 15 April) is when the file was made."""
        with AtrapaWordPressa() as baza:
            _, trafienia = self._uruchom(baza)
        self.assertEqual(trafienia[0]["data"], "2019-05")
        self.assertIn("2019", trafienia[0]["tagi"])

    def test_pdf_dostaje_typ_dokumentu_i_slad_strony(self):
        with AtrapaWordPressa() as baza:
            _, trafienia = self._uruchom(baza, typ_zotero="blogPost")
        self.assertEqual(trafienia[0]["typ"], "document")
        self.assertTrue(trafienia[0]["meta"]["strona_zrodlowa"].endswith("/partei/info-links"))
        self.assertEqual(trafienia[0]["meta"]["plik"], ".pdf")

    def test_skan_jest_zglaszany_a_nie_przemilczany(self):
        """An empty text layer means "nobody ran OCR", not "no match here"."""
        with AtrapaWordPressa() as baza:
            silnik, trafienia = self._uruchom(baza)
        dziennik = "\n".join(silnik.dziennik)
        self.assertIn("no text layer", dziennik)
        self.assertIn("info-links-05-2021.pdf", dziennik)
        self.assertNotIn("2021", [t["data"] for t in trafienia])

    def test_wylaczone_zalaczniki_pomijaja_pdfy(self):
        with AtrapaWordPressa() as baza:
            silnik, trafienia = self._uruchom(baza, zrodlo={"zalaczniki": False})
        self.assertEqual(trafienia, [])
        self.assertEqual(silnik.postep.zalacznikow, 0)

    def test_zotero_dostaje_sam_plik_w_zalaczniku(self):
        from kwerenda.cytowania import Rekord, do_zotero, nadaj_citekeys
        with AtrapaWordPressa() as baza:
            _, trafienia = self._uruchom(baza)
        rekord = nadaj_citekeys([Rekord.z_trafienia(trafienia[0])])[0]
        element = do_zotero(rekord, z_zalacznikiem=True)
        self.assertEqual(element["attachments"][0]["mimeType"], "application/pdf")
        self.assertTrue(element["attachments"][0]["url"].endswith(".pdf"))
        self.assertIn("Found on:", element["extra"])
        # the Web API rejects unknown fields, so that path must not carry them
        self.assertNotIn("attachments", do_zotero(rekord, z_zalacznikiem=False))

    def test_korpus_zapamietuje_tekst_pdf_a(self):
        """Once read, a PDF is searchable offline like any other page."""
        magazyn = Magazyn(":memory:")
        konfig = Konfiguracja(nazwa="pdf", zapytanie=self.ZAPYTANIE, jezyki=["de"],
                              opoznienie=0.0, watki=1,
                              zrodla=[Zrodlo(url="", tryb="urls", lista_url=[])])
        with AtrapaWordPressa() as baza:
            konfig.zrodla = [Zrodlo(url=baza, tryb="urls",
                                    lista_url=[f"{baza}/partei/info-links"])]
            Silnik(konfig, magazyn).uruchom()
        # the fixture is gone now — search what was kept
        konfig_korpus = Konfiguracja(nazwa="corpus", zapytanie="Familienfest",
                                     jezyki=["de"], opoznienie=0.0,
                                     zrodla=[Zrodlo(url="", tryb="corpus")])
        przebieg = Silnik(konfig_korpus, magazyn).uruchom()
        trafienia = magazyn.trafienia(przebieg)
        self.assertTrue(any(t["url"].endswith(".pdf") for t in trafienia))


class TestGrzecznosc(unittest.TestCase):
    def test_user_agent_znosi_znaki_spoza_latin1(self):
        from kwerenda.siec import KlientHTTP, naglowek_ascii
        self.assertEqual(naglowek_ascii("Paweł Żółć"), "Pawel Zolc")
        KlientHTTP(kontakt="Paweł Downarowicz").user_agent.encode("latin-1")

    def test_blad_zrodla_nie_przerywa_kwerendy(self):
        magazyn = Magazyn(":memory:")
        konfig = Konfiguracja(nazwa="t", zapytanie="msza*", opoznienie=0.0, proby=1,
                              zrodla=[Zrodlo(url="https://nie-istnieje.invalid",
                                             tryb="wordpress"),
                                      Zrodlo(url="", tryb="corpus")])
        przebieg = Silnik(konfig, magazyn).uruchom()
        self.assertEqual(magazyn.przebieg(przebieg)["status"], "done")

    def test_ostrzezenie_o_danych_logowania(self):
        konfig = Konfiguracja(zapytanie="x", kontakt="a@b.c",
                              zrodla=[Zrodlo(url="https://a.pl", ciasteczka="sid=1")])
        self.assertTrue(any("credentials" in u for u in konfig.sprawdz()))


class TestPresety(unittest.TestCase):
    """A preset is a file: readable, editable, shareable, runnable from the CLI."""

    def test_czyta_pliki_i_zapisuje_z_powrotem(self):
        from kwerenda.serwer import Stan, lista_presetow, zapisz_preset_do_pliku

        with tempfile.TemporaryDirectory() as katalog:
            katalog = Path(katalog)
            (katalog / "eksport").mkdir()
            stan = Stan(Magazyn(":memory:"), katalog / "eksport", katalog / "presets")

            konfig = Konfiguracja(nazwa="May Day — Mazowsze", zapytanie='"1 maja"*',
                                  jezyki=["pl"], zrodla=[Zrodlo(url="https://a.pl")])
            sciezka = zapisz_preset_do_pliku(stan, konfig.nazwa, konfig.jako_dict())
            self.assertEqual(sciezka.name, "may-day-mazowsze.yaml")

            presety = lista_presetow(stan)
            self.assertEqual(len(presety), 1)
            self.assertEqual(presety[0]["name"], "May Day — Mazowsze")
            self.assertEqual(presety[0]["source"], "file")
            wczytany = Konfiguracja.z_dict(presety[0]["config"])
            self.assertEqual(wczytany.zapytanie, '"1 maja"*')
            self.assertEqual(wczytany.zrodla[0].url, "https://a.pl")

    def test_zepsuty_plik_nie_wywala_listy(self):
        from kwerenda.serwer import presety_z_plikow

        with tempfile.TemporaryDirectory() as katalog:
            katalog = Path(katalog)
            (katalog / "dobry.json").write_text('{"name": "Fine", "query": "x"}',
                                                encoding="utf-8")
            (katalog / "zepsuty.json").write_text("{ this is not json", encoding="utf-8")
            presety = {p["name"]: p for p in presety_z_plikow(katalog)}
        self.assertEqual(presety["Fine"]["config"]["query"], "x")
        self.assertIn("error", presety["zepsuty"])

    def test_cli_znajduje_preset_po_nazwie(self):
        from kwerenda.__main__ import _znajdz_preset

        class Args:
            pass

        with tempfile.TemporaryDirectory() as katalog:
            katalog = Path(katalog)
            (katalog / "moja-kwerenda.yaml").write_text("name: Mine\nquery: x\n",
                                                        encoding="utf-8")
            args = Args()
            args.presets = str(katalog)
            self.assertEqual(_znajdz_preset(args, "moja-kwerenda").name,
                             "moja-kwerenda.yaml")
            self.assertEqual(_znajdz_preset(args, str(katalog / "moja-kwerenda.yaml")).name,
                             "moja-kwerenda.yaml")
            with self.assertRaises(SystemExit):
                _znajdz_preset(args, "nie-ma-takiego")


class TestRozdzielenieDanych(unittest.TestCase):
    """Your work must not live inside the folder that gets replaced on update."""

    def test_katalog_danych_slucha_zmiennej(self):
        from kwerenda import dane
        with tempfile.TemporaryDirectory() as katalog:
            stare = os.environ.get("KWERENDA_HOME")
            os.environ["KWERENDA_HOME"] = katalog
            try:
                self.assertEqual(dane.katalog_danych(), Path(katalog))
                self.assertEqual(dane.sciezka_bazy().parent, Path(katalog))
                self.assertEqual(dane.katalog_presetow(), Path(katalog) / "presets")
            finally:
                if stare is None:
                    os.environ.pop("KWERENDA_HOME", None)
                else:
                    os.environ["KWERENDA_HOME"] = stare

    def test_przenosi_stara_baze_i_moje_presety_ale_nie_przyklady(self):
        from kwerenda import dane
        with tempfile.TemporaryDirectory() as katalog:
            katalog = Path(katalog)
            program = dane.katalog_programu()
            stara_baza = program / dane.NAZWA_BAZY
            moj_preset = dane.katalog_przykladow() / "moja-wlasna-kwerenda.yaml"
            przyklad = dane.katalog_przykladow() / sorted(dane.PRZYKLADY)[0]

            stare = os.environ.get("KWERENDA_HOME")
            os.environ["KWERENDA_HOME"] = str(katalog)
            posprzataj = []
            try:
                if not stara_baza.exists():
                    stara_baza.write_bytes(b"SQLite format 3\x00")
                    posprzataj.append(stara_baza)
                moj_preset.write_text("name: Mine\nquery: x\n", encoding="utf-8")
                posprzataj.append(moj_preset)

                dane.przenies_stare_dane(log=lambda *_: None)

                self.assertTrue((katalog / dane.NAZWA_BAZY).is_file())
                self.assertFalse(stara_baza.exists())         # moved, not copied
                self.assertTrue((katalog / "presets" / moj_preset.name).is_file())
                # an untouched example belongs to the program, not to the user
                self.assertFalse((katalog / "presets" / przyklad.name).exists())
            finally:
                for plik in posprzataj:
                    plik.unlink(missing_ok=True)
                if stare is None:
                    os.environ.pop("KWERENDA_HOME", None)
                else:
                    os.environ["KWERENDA_HOME"] = stare

    def test_manifest_przykladow_nadaza_za_folderem(self):
        """Adding an example without listing it would make the migration treat
        it as the user's work and copy it into their folder."""
        from kwerenda.dane import PRZYKLADY, katalog_przykladow
        na_dysku = {p.name for p in katalog_przykladow().glob("*.yaml")}
        self.assertEqual(na_dysku, set(PRZYKLADY))

    def test_lista_laczy_moje_presety_z_przykladami(self):
        from kwerenda.dane import katalog_przykladow
        from kwerenda.serwer import Stan, lista_presetow

        with tempfile.TemporaryDirectory() as katalog:
            katalog = Path(katalog)
            moje = katalog / "presets"
            moje.mkdir()
            (moje / "wlasna.yaml").write_text("name: Wlasna\nquery: x\n", encoding="utf-8")
            stan = Stan(Magazyn(":memory:"), katalog / "exports", moje, katalog_przykladow())
            presety = lista_presetow(stan)

        zrodla = {p["name"]: p["source"] for p in presety}
        self.assertEqual(zrodla.get("Wlasna"), "file")
        self.assertIn("example", zrodla.values())
        self.assertEqual(len(presety), len({p["name"] for p in presety}))   # no duplicates


class TestSprawdzaniaLogowania(unittest.TestCase):
    """Copying a Cookie header is the fiddliest step; a wrong one must not fail
    silently by quietly collecting login pages."""

    def _sprawdz(self, baza, ciasteczka=""):
        from kwerenda.serwer import Obsluga, Stan

        odpowiedzi = []
        obsluga = Obsluga.__new__(Obsluga)
        obsluga.stan = Stan(Magazyn(":memory:"), Path(tempfile.mkdtemp()))
        obsluga._json = lambda dane, status=200: odpowiedzi.append(dane)
        obsluga._sprawdz_logowanie({
            "source": {"url": baza, "cookies": ciasteczka},
            "url": f"{baza}/2020/05/tylko-dla-prenumeratorow"})
        return odpowiedzi[0]

    def test_rozpoznaje_brak_zle_i_dobre_ciasteczka(self):
        with AtrapaWordPressa(wymagaj_ciasteczka="sid=tajne") as baza:
            bez = self._sprawdz(baza)
            zle = self._sprawdz(baza, "sid=nieprawidlowe")
            dobre = self._sprawdz(baza, "sid=tajne")

        self.assertFalse(bez["ok"])
        self.assertEqual(bez["cookies"], 0)
        self.assertIn("Nothing was sent to identify you", bez["message"])

        self.assertFalse(zle["ok"])
        self.assertEqual(zle["cookies"], 1)
        self.assertIn("stale", zle["message"])

        self.assertTrue(dobre["ok"])
        self.assertIn("Looks signed in", dobre["message"])
        self.assertIn("prenumerat", dobre["title"])

    def test_rozpoznaje_strone_logowania(self):
        from kwerenda.serwer import _wyglada_na_logowanie
        self.assertTrue(_wyglada_na_logowanie('<form><input type="password"></form>'))
        self.assertTrue(_wyglada_na_logowanie("<title>Anmelden | Zeitung</title>"))
        self.assertFalse(_wyglada_na_logowanie("<title>1. Mai in Lichtenberg</title>"))


class TestSerwer(unittest.TestCase):
    def test_zajety_port_nie_wywala_programu(self):
        """Double-clicking the icon twice must not end in a stack trace."""
        import socket
        from http.server import BaseHTTPRequestHandler
        from kwerenda.serwer import zwiaz_serwer

        zajety = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        zajety.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        zajety.bind(("127.0.0.1", 0))
        zajety.listen(1)
        port = zajety.getsockname()[1]
        try:
            serwer = zwiaz_serwer(BaseHTTPRequestHandler, "127.0.0.1", port)
            try:
                self.assertNotEqual(serwer.server_address[1], port)
                self.assertLess(serwer.server_address[1], port + 12)
            finally:
                serwer.server_close()
        finally:
            zajety.close()


class TestEksport(unittest.TestCase):
    def setUp(self):
        self.rekord = Rekord(
            url="https://serwis.pl/2015/05/obchody", tytul="Obchody 1 Maja na Żoliborzu",
            autorzy=["Anna Nowak"], data="2015-05-02", serwis="Serwis", jezyk="pl",
            typ="blogPost", tagi=["1 maja", "Żoliborz"], terminy=["1 maja"],
            cytaty=[{"fragment": "msza w kościele", "formy": ["msza"], "pole": "text"}])
        nadaj_citekeys([self.rekord])

    def test_citekey(self):
        self.assertEqual(self.rekord.citekey, "nowak2015obchody")

    def test_unikalne_citekeys(self):
        drugi = Rekord(url="https://serwis.pl/x", tytul="Obchody inne",
                       autorzy=["Anna Nowak"], data="2015-06-01")
        nadaj_citekeys([self.rekord, drugi])
        self.assertNotEqual(self.rekord.citekey, drugi.citekey)

    def test_ris(self):
        ris = do_ris([self.rekord])
        for fragment in ("TY  - BLOG", "AU  - Nowak, Anna", "KW  - Żoliborz",
                         "UR  - https://serwis.pl/2015/05/obchody", "N1  - ", "ER  - "):
            self.assertIn(fragment, ris)

    def test_csl_json(self):
        csl = do_csl([self.rekord])[0]
        self.assertEqual(csl["type"], "post-weblog")
        self.assertEqual(csl["issued"]["date-parts"], [[2015, 5, 2]])
        self.assertEqual(csl["author"][0]["family"], "Nowak")

    def test_bibtex(self):
        bib = do_bibtex([self.rekord])
        self.assertIn("@online{nowak2015obchody,", bib)
        self.assertIn("keywords = {1 maja, Żoliborz}", bib)

    def test_zotero_item(self):
        element = do_zotero(self.rekord)
        self.assertEqual(element["itemType"], "blogPost")
        self.assertEqual(element["blogTitle"], "Serwis")
        self.assertEqual(element["tags"], [{"tag": "1 maja"}, {"tag": "Żoliborz"}])
        self.assertIn("notes", element)
        self.assertIn("Citation Key: nowak2015obchody", element["extra"])

    def test_markdown(self):
        md = do_markdown(self.rekord)
        self.assertIn("[[@nowak2015obchody]]", md)
        self.assertIn("> msza w kościele", md)

    def test_csv_ma_angielskie_naglowki(self):
        csv_tekst = do_csv([self.rekord])
        self.assertIn("citekey,title,authors", csv_tekst)
        self.assertIn("nowak2015obchody", csv_tekst)


class TestKonfiguracja(unittest.TestCase):
    def test_zapis_i_odczyt(self):
        konfig = Konfiguracja(nazwa="x", zapytanie="msza*", jezyki=["pl", "de"],
                              zrodla=[Zrodlo(url="https://a.pl")])
        with tempfile.TemporaryDirectory() as katalog:
            sciezka = Path(katalog) / "k.json"
            konfig.zapisz(sciezka)
            tekst = sciezka.read_text(encoding="utf-8")
            wczytana = Konfiguracja.wczytaj(sciezka)
        self.assertIn('"query"', tekst)          # English keys on disk
        self.assertIn('"sources"', tekst)
        self.assertEqual(wczytana.zapytanie, "msza*")
        self.assertEqual(wczytana.jezyki, ["pl", "de"])
        self.assertEqual(wczytana.zrodla[0].url, "https://a.pl")

    def test_stare_polskie_klucze_nadal_dzialaja(self):
        konfig = Konfiguracja.z_dict({"nazwa": "stara", "zapytanie": "msza",
                                      "domyslny_operator": "I",
                                      "zrodla": [{"url": "https://a.pl", "tryb": "korpus"}]})
        self.assertEqual(konfig.nazwa, "stara")
        self.assertEqual(konfig.domyslny_operator, "AND")
        self.assertEqual(konfig.zrodla[0].tryb, "corpus")

    def test_ostrzezenia(self):
        self.assertTrue(any("No source" in u for u in Konfiguracja().sprawdz()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
