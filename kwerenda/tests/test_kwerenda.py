# -*- coding: utf-8 -*-
"""Testy: fleksja, parser zapytań, ekstrakcja, źródła, silnik, eksport."""

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
from kwerenda.fleksja import FlexOptions, czy_pasuje, przykladowe_formy
from kwerenda.konfiguracja import Konfiguracja
from kwerenda.magazyn import Magazyn
from kwerenda.silnik import Silnik
from kwerenda.zapytania import BladZapytania, Dokument, cytaty, parsuj
from kwerenda.zrodla import Zrodlo, _okna_dat
from tests.atrapa_wordpressa import AtrapaWordPressa


class TestFleksja(unittest.TestCase):
    def test_odmiana_rzeczownikow(self):
        for baza, forma in [("Żoliborz", "Żoliborzu"), ("Żoliborz", "Żoliborza"),
                            ("święto", "święcie"), ("święto", "świąt"),
                            ("praca", "pracy"), ("praca", "pracach"),
                            ("Gdańsk", "Gdańsku"), ("pochód", "pochodu"),
                            ("Solidarność", "Solidarności"), ("msza", "mszy"),
                            ("robotnik", "robotników"), ("sztandar", "sztandarami")]:
            with self.subTest(baza=baza, forma=forma):
                self.assertTrue(czy_pasuje(forma, baza), f"{baza} nie złapało {forma}")

    def test_nie_lapie_przypadkowych_slow(self):
        for baza, obce in [("praca", "prawo"), ("msza", "maszyna"), ("maj", "majątek"),
                           ("Gdańsk", "gdakanie"), ("pochód", "pochwała")]:
            with self.subTest(baza=baza, obce=obce):
                self.assertFalse(czy_pasuje(obce, baza), f"{baza} złapało {obce}")

    def test_tryb_dokladny(self):
        opcje = FlexOptions(mode="dokladnie")
        self.assertTrue(czy_pasuje("Solidarność", "Solidarność", opcje))
        self.assertFalse(czy_pasuje("Solidarności", "Solidarność", opcje))

    def test_tryb_rdzenia_lapie_derywaty(self):
        opcje = FlexOptions(mode="rdzen")
        self.assertTrue(czy_pasuje("pracownik", "praca", opcje))
        self.assertTrue(czy_pasuje("pracował", "praca", opcje))

    def test_bez_ogonkow(self):
        opcje = FlexOptions(fold_diacritics=True)
        self.assertTrue(czy_pasuje("Zoliborzu", "Żoliborz", opcje))
        self.assertTrue(czy_pasuje("swieto pracy", "święto", opcje))

    def test_liczebnik_z_koncowka(self):
        self.assertTrue(czy_pasuje("1-go maja", "1 maja"))
        self.assertTrue(czy_pasuje("1 Maja", "1 maja"))
        self.assertFalse(czy_pasuje("3 maja", "1 maja"))

    def test_wildcard(self):
        self.assertTrue(czy_pasuje("pierwszomajowy", "pierwszomaj*"))

    def test_podglad_form(self):
        formy = przykladowe_formy("Żoliborz")
        self.assertIn("żoliborza", [f.lower() for f in formy])
        self.assertGreater(len(formy), 10)

    def test_wykluczanie_formy(self):
        opcje = FlexOptions(wyklucz=("mają",))
        self.assertFalse(czy_pasuje("mają", "maj", opcje))
        self.assertTrue(czy_pasuje("maja", "maj", opcje))


class TestZapytania(unittest.TestCase):
    def setUp(self):
        self.dok = Dokument(
            tytul="Obchody 1 Maja na Żoliborzu",
            tekst="W kościele św. Józefa Robotnika odprawiono mszę. Pochód przeszedł "
                  "ulicami. Sztandary Solidarności powiewały.",
            url="https://przyklad.pl/2015/05/obchody", autor="Anna Nowak", tagi=["Mazowsze"])

    def _ocen(self, zapytanie):
        return parsuj(zapytanie).ocen(self.dok)[0]

    def test_operatory_podstawowe(self):
        self.assertTrue(self._ocen('"1 maja" I Żoliborz'))
        self.assertTrue(self._ocen('"1 maja" AND Żoliborz'))
        self.assertTrue(self._ocen('Żoliborz LUB Katowice'))
        self.assertFalse(self._ocen('Katowice LUB Wrocław'))
        self.assertFalse(self._ocen('msza NIE sztandar'))
        self.assertTrue(self._ocen('msza NIE Katowice'))
        self.assertFalse(self._ocen('msza -sztandar'))

    def test_domyslny_operator_to_koniunkcja(self):
        self.assertTrue(self._ocen('msza pochód'))
        self.assertFalse(self._ocen('msza Katowice'))

    def test_nawiasy_i_priorytety(self):
        self.assertTrue(self._ocen('"1 maja" I (Katowice LUB Żoliborz)'))
        self.assertFalse(self._ocen('"1 maja" I (Katowice LUB Wrocław)'))

    def test_pola(self):
        self.assertTrue(self._ocen('tytuł:Żoliborz'))
        self.assertFalse(self._ocen('tytuł:sztandar'))
        self.assertTrue(self._ocen('tekst:sztandar'))
        self.assertTrue(self._ocen('autor:Nowak'))
        self.assertTrue(self._ocen('url:2015'))
        self.assertTrue(self._ocen('tagi:Mazowsze'))
        # domyślnie szukamy w treści, więc sam tag ani adres nie robią trafienia
        self.assertFalse(self._ocen('Mazowsze'))
        self.assertTrue(self._ocen('wszystko:Mazowsze'))
        # pole z frazą w cudzysłowie to jeden termin, nie dwa
        self.assertTrue(self._ocen('tytuł:"1 Maja"'))
        self.assertFalse(self._ocen('tytuł:"sztandary Solidarności"'))

    def test_sasiedztwo(self):
        self.assertTrue(self._ocen('kościele BLISKO/3 Józefa'))
        self.assertFalse(self._ocen('kościele BLISKO/2 Solidarności'))
        self.assertTrue(self._ocen('kościele ~30 Solidarności'))

    def test_modyfikatory_terminu(self):
        self.assertTrue(self._ocen('=Sztandary'))
        self.assertFalse(self._ocen('=Sztandar'))
        self.assertTrue(self._ocen('~Sztandar'))

    def test_bledy_skladni(self):
        with self.assertRaises(BladZapytania):
            parsuj('(msza I')
        with self.assertRaises(BladZapytania):
            parsuj('msza)')

    def test_puste_zapytanie_lapie_wszystko(self):
        self.assertTrue(parsuj("").ocen(self.dok)[0])

    def test_cytaty_z_kontekstem(self):
        ok, trafienia = parsuj('"Józef Robotnik"').ocen(self.dok)
        fragmenty = cytaty(self.dok, trafienia, okno=40)
        self.assertTrue(ok)
        self.assertIn("Józefa Robotnika", fragmenty[0]["fragment"])
        self.assertEqual(fragmenty[0]["formy"], ["Józefa Robotnika"])


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

    def test_daty_wielojezyczne(self):
        self.assertEqual(normalizuj_date("2 maja 2015"), "2015-05-02")
        self.assertEqual(normalizuj_date("1. Mai 2019"), "2019-05-01")
        self.assertEqual(normalizuj_date("9 травня 2020"), "2020-05-09")
        self.assertEqual(normalizuj_date("12.05.1998"), "1998-05-12")
        self.assertEqual(normalizuj_date("bez daty"), "")

    def test_data_z_adresu(self):
        meta = wyciagnij_metadane("<html><body><h1>X</h1></body></html>",
                                  "https://a.pl/2016/05/tekst")
        self.assertEqual(meta.data, "2016-05")


class TestOknaDat(unittest.TestCase):
    def test_cykliczne_okno_majowe(self):
        okna = _okna_dat(Zrodlo(url="a.pl", od_roku=2014, do_roku=2016, okno_dat="04-25:05-05"))
        self.assertEqual(len(okna), 3)
        self.assertTrue(okna[0][0].startswith("2014-04-25"))
        self.assertTrue(okna[2][1].startswith("2016-05-05"))


class TestSilnikNaAtrapie(unittest.TestCase):
    def _konfig(self, baza, **kw):
        konfig = Konfiguracja(
            nazwa="test", zapytanie=kw.pop("zapytanie", '"1 maja" I (Żoliborz LUB "Józef Robotnik")'),
            kontakt="test@example.org", opoznienie=0.0, uzyj_cache=kw.pop("uzyj_cache", True),
            watki=1, zrodla=[Zrodlo(url=baza, nazwa="Atrapa", tryb=kw.pop("tryb", "auto"),
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
            silnik, magazyn, trafienia = self._uruchom(self._konfig(baza))
        adresy = {t["url"] for t in trafienia}
        self.assertEqual(len(trafienia), 1, [t["tytul"] for t in trafienia])
        self.assertTrue(any("zoliborz" in a for a in adresy))
        # Post „Komunikat organizacyjny” nie zawiera fraz – nie może się znaleźć,
        # mimo że wyszukiwarka serwisu podała go jako kandydata.
        self.assertFalse(any("komunikat" in a for a in adresy))

    def test_pelne_przemiatanie_znajduje_to_czego_szukajka_nie_widzi(self):
        """Atrapa (jak niejedna realna wyszukiwarka WP) przeszukuje tylko tytuły.
        Słowo „sztandar” występuje wyłącznie w treści – bez przemiecenia archiwum
        przepada, z przemieceniem znajdujemy oba artykuły, w dwóch różnych formach."""
        with AtrapaWordPressa() as baza:
            _, _, bez_przemiatania = self._uruchom(
                self._konfig(baza, zapytanie="sztandar", tryb="wordpress"))
            _, _, z_przemiataniem = self._uruchom(
                self._konfig(baza, zapytanie="sztandar", tryb="wordpress",
                             zrodlo={"pelne_przemiatanie": True}))
        self.assertEqual(bez_przemiatania, [])
        self.assertEqual(len(z_przemiataniem), 2)
        formy = {f for t in z_przemiataniem for c in t["cytaty"] for f in c["formy"]}
        self.assertEqual(formy, {"sztandarami", "sztandary"})

    def test_metadane_i_tagi_z_wordpressa(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza))
        wpis = [t for t in trafienia if "zoliborz" in t["url"]][0]
        self.assertEqual(wpis["tytul"], "Obchody 1 Maja na Żoliborzu")
        self.assertEqual(wpis["autorzy"], ["Anna Nowak"])
        self.assertEqual(wpis["data"], "2015-05-02")
        self.assertIn("Wydarzenia", wpis["tagi"])      # kategoria z WP
        self.assertIn("1 maja", wpis["tagi"])          # tag z WP i z terminów
        self.assertIn("2015", wpis["tagi"])            # rok
        self.assertTrue(wpis["citekey"].startswith("nowak2015"))
        self.assertTrue(wpis["cytaty"][0]["fragment"])

    def test_fallback_na_html_gdy_api_wylaczone(self):
        with AtrapaWordPressa(wylacz_api=True) as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza))
        self.assertGreaterEqual(len(trafienia), 2)
        self.assertTrue(all(t["tytul"] for t in trafienia))

    def test_auto_schodzi_na_sitemap_gdy_szukajka_nic_nie_zwraca(self):
        """Tryb „auto”: API odpowiada, ale na dane hasło nic nie zwraca –
        wtedy zamiast poprzestać, silnik schodzi piętro niżej, na mapę strony."""
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza, zapytanie="sztandar"))
        self.assertEqual(len(trafienia), 2)
        self.assertEqual({t["meta"]["skad"] for t in trafienia}, {"sitemap"})

    def test_tagi_bez_ozdobnikow_zapytania(self):
        with AtrapaWordPressa() as baza:
            _, _, trafienia = self._uruchom(self._konfig(
                baza, zapytanie="pierwszomaj*", zrodlo={"pelne_przemiatanie": True}))
        tagi = {t for wpis in trafienia for t in wpis["tagi"]}
        self.assertIn("pierwszomaj", tagi)
        self.assertNotIn("pierwszomaj*", tagi)

    def test_tryb_sitemap(self):
        with AtrapaWordPressa(wylacz_api=True) as baza:
            _, _, trafienia = self._uruchom(self._konfig(baza, tryb="sitemap"))
        self.assertEqual(len(trafienia), 2)

    def test_okno_dat_zawezenie(self):
        with AtrapaWordPressa() as baza:
            konfig = self._konfig(baza, zapytanie="pochód",
                                  zrodlo={"od_roku": 2015, "do_roku": 2016,
                                          "okno_dat": "04-25:05-05",
                                          "pelne_przemiatanie": True})
            _, _, trafienia = self._uruchom(konfig)
        daty = sorted(t["data"] for t in trafienia)
        self.assertEqual(daty, ["2015-05-02", "2016-05-01"])   # 1998 poza zakresem lat

    def test_korpus_dziala_bez_sieci(self):
        magazyn = Magazyn(":memory:")
        with AtrapaWordPressa() as baza:
            self._uruchom(self._konfig(baza, zapytanie="", zrodlo={"pelne_przemiatanie": True}),
                          magazyn)
        # serwer już nie działa – szukamy w tym, co zostało pobrane
        konfig = Konfiguracja(nazwa="korpus", zapytanie="sztandar", opoznienie=0.0,
                              zrodla=[Zrodlo(url="", tryb="korpus")])
        silnik = Silnik(konfig, magazyn)
        przebieg = silnik.uruchom()
        self.assertGreaterEqual(len(magazyn.trafienia(przebieg)), 1)

    def test_przerwanie_konczy_przebieg(self):
        with AtrapaWordPressa() as baza:
            konfig = self._konfig(baza, zapytanie="")
            magazyn = Magazyn(":memory:")
            silnik = Silnik(konfig, magazyn)
            silnik.przerwij()
            przebieg = silnik.uruchom()
        self.assertEqual(magazyn.przebieg(przebieg)["status"], "przerwane")

    def test_robots_txt_jest_respektowany(self):
        with AtrapaWordPressa() as baza:
            konfig = self._konfig(baza, tryb="lista",
                                  zrodlo={"lista_url": [f"{baza}/wp-admin/tajne"]})
            _, _, trafienia = self._uruchom(konfig)
        self.assertEqual(trafienia, [])


class TestGrzecznosc(unittest.TestCase):
    def test_user_agent_znosi_polskie_znaki(self):
        from kwerenda.siec import KlientHTTP, naglowek_ascii
        self.assertEqual(naglowek_ascii("Paweł Żółć"), "Pawel Zolc")
        klient = KlientHTTP(kontakt="Paweł Downarowicz")
        klient.user_agent.encode("latin-1")     # nagłówki HTTP są latin-1

    def test_blad_zrodla_nie_przerywa_kwerendy(self):
        magazyn = Magazyn(":memory:")
        konfig = Konfiguracja(nazwa="t", zapytanie="msza", opoznienie=0.0, proby=1, zrodla=[
            Zrodlo(url="https://na-pewno-nie-istnieje.invalid", tryb="wordpress"),
            Zrodlo(url="", tryb="korpus")])
        silnik = Silnik(konfig, magazyn)
        przebieg = silnik.uruchom()
        self.assertEqual(magazyn.przebieg(przebieg)["status"], "gotowe")


class TestEksport(unittest.TestCase):
    def setUp(self):
        self.rekord = Rekord(
            url="https://serwis.pl/2015/05/obchody", tytul="Obchody 1 Maja na Żoliborzu",
            autorzy=["Anna Nowak"], data="2015-05-02", serwis="Serwis", jezyk="pl",
            typ="blogPost", tagi=["1 maja", "Żoliborz"], terminy=["1 maja"],
            cytaty=[{"fragment": "msza w kościele", "formy": ["msza"]}])
        nadaj_citekeys([self.rekord])

    def test_citekey_w_stylu_better_bibtex(self):
        self.assertEqual(self.rekord.citekey, "nowak2015obchody")

    def test_unikalne_citekeys(self):
        drugi = Rekord(url="https://serwis.pl/x", tytul="Obchody inne", autorzy=["Anna Nowak"],
                       data="2015-06-01")
        nadaj_citekeys([self.rekord, drugi])
        self.assertNotEqual(self.rekord.citekey, drugi.citekey)

    def test_ris_ma_tagi_i_notatke(self):
        ris = do_ris([self.rekord])
        self.assertIn("TY  - BLOG", ris)
        self.assertIn("AU  - Nowak, Anna", ris)
        self.assertIn("KW  - Żoliborz", ris)
        self.assertIn("UR  - https://serwis.pl/2015/05/obchody", ris)
        self.assertIn("N1  - ", ris)
        self.assertIn("ER  - ", ris)

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

    def test_markdown_dla_obsidiana(self):
        md = do_markdown(self.rekord)
        self.assertIn("[[@nowak2015obchody]]", md)
        self.assertIn("> msza w kościele", md)

    def test_csv(self):
        csv_tekst = do_csv([self.rekord])
        self.assertIn("citekey,tytul", csv_tekst)
        self.assertIn("nowak2015obchody", csv_tekst)


class TestKonfiguracja(unittest.TestCase):
    def test_zapis_i_odczyt_json(self):
        konfig = Konfiguracja(nazwa="x", zapytanie="msza", zrodla=[Zrodlo(url="https://a.pl")])
        with tempfile.TemporaryDirectory() as katalog:
            sciezka = Path(katalog) / "k.json"
            konfig.zapisz(sciezka)
            wczytana = Konfiguracja.wczytaj(sciezka)
        self.assertEqual(wczytana.zapytanie, "msza")
        self.assertEqual(wczytana.zrodla[0].url, "https://a.pl")

    def test_ostrzezenia(self):
        uwagi = Konfiguracja().sprawdz()
        self.assertTrue(any("źródła" in u for u in uwagi))


if __name__ == "__main__":
    unittest.main(verbosity=2)
