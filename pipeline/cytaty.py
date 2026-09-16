"""Dopisz do kazdej dzielnicowki fragment zrodla, z ktorego ja znam.

Tabela dzielnicowe.tsv niesie rozpisane pola -- rok, godzine, miejsce -- ale
nie zdanie, na ktorym to stoi. Na mapie i w kartotece to jest roznica miedzy
"tak zapisalem" a "tak stoi w gazecie".

Skrypt szuka w dokumencie zrodlowym fragmentu, ktory najlepiej pasuje do
wiersza (miejsce + godzina + nazwa), i proponuje go jako cytat. Nie wpisuje
go sam do dzielnicowe.tsv: dopasowanie bywa chybione, a cytat przypisany do
niewlasciwego wydarzenia jest gorszy niz jego brak. Wynik idzie do
output/cytaty_kandydaci.tsv do przejrzenia.

Usage: python3 cytaty.py
"""
import csv
import re
import unicodedata
from pathlib import Path

from common import write_csv

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
TABELA = BASE / "input/dzielnicowe.tsv"

# fragment kolumny `zrodlo` -> plik, w ktorym szukac
DOKUMENTY = [
    ("blättchen", "input/zrodla/blaettchen_treptow_koepenick.md"),
    ("info links", "input/zrodla/info_links_lichtenberg.md"),
    ("Berliner Zeitung", "input/zrodla/bunte_platte_2010_2012.txt"),
    ("Berliner Morgenpost", "input/zrodla/bunte_platte_2010_2012.txt"),
    ("rocznik DE", "input/DE_1990-2019.md"),
    ("BZ ", "input/DE_1990-2019.md"),
    ("Newsletter Die Linke", "input/nd/artykuly_nd.txt"),
    ("strona wydarzenia", "input/nd/artykuly_nd.txt"),
    ("PDS Berlin, Termine", "input/nd/artykuly_nd.txt"),
    ("Facebook", "input/nd/artykuly_nd.txt"),
    ("ND", "input/nd/artykuly_nd.txt"),
    ("nd ", "input/nd/artykuly_nd.txt"),
]
OKNO = 260

# Numer pisma z kolumny `zrodlo`: "blättchen 211, kwiecien 2015" -> 211,
# "info links 03/2007" -> 03/2007. Bez tego szuka sie po calym roczniku i
# cytat trafia w inny numer sprzed dziesieciu lat.
NUMER = re.compile(r"blättchen\s+(\d+)|info links\s+(\d{2})/(\d{4})", re.I)


# Tekst wyciagniety z PDF-a niesie rozpakowane obrazki: dlugie ciagi bez
# spacji i bez slow. Cytat z takiego miejsca jest smieciem.
SMIEC = re.compile(r"[^\sA-Za-zÀ-ÿ0-9.,;:!?()„”»«\-–/]{6,}")


def smieciowy(t):
    if SMIEC.search(t):
        return True
    litery = sum(c.isalpha() or c.isspace() for c in t)
    return litery < 0.7 * max(len(t), 1)


def uprosc(t):
    t = (t or "").lower().replace("ß", "ss").replace("ö", "oe") \
        .replace("ä", "ae").replace("ü", "ue")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t)


def bloki_dokumentu(p):
    """Dokument -> lista (naglowek, tekst). Kazdy numer pisma osobno."""
    tekst = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix != ".md" or "\n# " not in tekst:
        return [("", tekst)]
    czesci = re.split(r"^# ", tekst, flags=re.M)
    out = []
    for c in czesci[1:]:
        u = re.search(r"<(https?://[^>]+)>", c)
        out.append((u.group(1) if u else "", c))
    return out


def wybierz_bloki(bloki, zrodlo, rok):
    """Numery pisma pasujace do zrodla wiersza; gdy nie ma -- wszystkie."""
    m = NUMER.search(zrodlo or "")
    if m and m.group(1):
        pasujace = [b for b in bloki if re.search(rf"_{m.group(1)}[_.]", b[0])]
        if pasujace:
            return pasujace
    if m and m.group(2):
        mm, rr = m.group(2), m.group(3)
        pasujace = [b for b in bloki
                    if re.search(rf"info{mm}{rr[2:]}\.pdf|/{rr}/info{mm}", b[0])]
        if pasujace:
            return pasujace
    # inaczej: numery, ktore w ogole mowia o tym roku
    po_roku = [b for b in bloki if rok in b[1]]
    return po_roku or bloki


def dokumenty_dla(zrodlo):
    """Wszystkie pasujace dokumenty, nie pierwszy lepszy.

    "nd 27.04.1994" pasuje i do zbioru artykulow ND, i do rocznika -- a tekst
    z 1994 jest tylko w tym drugim. Lepiej przeszukac oba i wybrac lepsze
    dopasowanie, niz zgadywac po nazwie zrodla.
    """
    out = []
    for fragment, sciezka in DOKUMENTY:
        if fragment.lower() in (zrodlo or "").lower():
            p = BASE / sciezka
            if p.exists() and sciezka not in [o[0] for o in out]:
                out.append((sciezka, p))
    return out


_cache = {}


def wczytaj(p):
    if p not in _cache:
        _cache[p] = [(n, t, uprosc(t)) for n, t in bloki_dokumentu(p)]
    return _cache[p]


def tokeny(w):
    """Slowa, ktore maja wskazac wlasciwy fragment: miejsce i nazwa."""
    sur = f"{w['miejsce']} {w['nazwa']}"
    slowa = [s for s in uprosc(sur).split() if len(s) >= 4]
    # numery i skroty tez licza sie, jesli sa charakterystyczne
    slowa += [s for s in re.findall(r"\d{1,3}", sur) if len(s) >= 2]
    return list(dict.fromkeys(slowa))


def godziny(w):
    out = []
    for pole in ("godzina_od", "godzina_do"):
        g = (w.get(pole) or "").strip()
        if g:
            h = g.split(":")[0].lstrip("0") or "0"
            out.append(h)
    return out


# Wpis w takim wykazie zaczyna sie od godziny albo od punktora. Cytat uciety
# w polowie poprzedniego wpisu wyglada, jakby dotyczyl czegos innego.
# Poczatek wpisu: godzina albo poczatek zakresu godzin. Wazne, zeby zlapac
# "13 - 18 Uhr" od trzynastej, a nie od osiemnastej -- inaczej cytat zaczyna
# sie w polowie wlasnej godziny.
POCZATEK = re.compile(
    r"(?:^|[•●■▪>|\n])\s*"
    r"|\b(?:ab|von|um)\s+\d{1,2}(?:[.:]\d{2})?\s*(?:bis|–|-|—|\s*uhr)"
    r"|\b\d{1,2}(?:[.:]\d{2})?\s*(?:bis|–|-|—)\s*\d{1,2}(?:[.:]\d{2})?\s*uhr"
    r"|\b\d{1,2}(?:[.:]\d{2})?\s*uhr", re.I)
# Koniec: nastepny wpis albo granica dokumentu w sklejce.
KONIEC = re.compile(r"\n?---\s*\ntitle:|=== PLIK:|\n#{1,2}\s")


def poczatek_wpisu(prosty, a, kotwica):
    """Przesun poczatek cytatu do poczatku wpisu, w ktorym stoi kotwica."""
    ostatni = a
    for m in POCZATEK.finditer(prosty, a, kotwica + 1):
        ostatni = m.start()
    return ostatni


def wpisy(tekst):
    """Tekst wykazu -> pojedyncze wpisy.

    Te wykazy sa ciagiem pozycji zaczynajacych sie od godziny: "13 bis 18
    Uhr: Maifest ...", "ab 11 Uhr ...". Dopasowanie do calego wpisu jest
    sprawdzalne -- wpis albo zawiera to miejsce i te godzine, albo nie --
    w odroznieniu od okna N znakow, ktore zlapie sasiedni wpis i wyglada
    tak samo wiarygodnie.
    """
    granice = [m.start() for m in POCZATEK.finditer(tekst)]
    if not granice:
        return []
    granice.append(len(tekst))
    out = []
    for a, z in zip(granice, granice[1:]):
        frag = tekst[a:min(z, a + 420)]
        kon = KONIEC.search(frag)
        if kon:
            frag = frag[:kon.start()]
        if len(frag.strip()) >= 20:
            out.append(frag)
    return out


def znajdz(w, bloki):
    """Wpis, ktory zawiera i miejsce, i godzine tego wydarzenia."""
    sl = tokeny(w)
    godz = godziny(w)
    if not sl:
        return "", 0, ""
    najlepszy, wynik = None, 0
    for naglowek, tekst, _ in bloki:
        for wpis in wpisy(tekst):
            if smieciowy(wpis):
                continue
            prosty = uprosc(wpis)
            pokrycie = sum(1 for s in sl if s in prosty) / len(sl)
            if pokrycie < 0.5:
                continue
            # Godzina musi stac w tym samym wpisie. Bez tego wpis obok, o
            # innej godzinie i w innej dzielnicy, wyglada rownie dobrze.
            if godz:
                w_wpisie = sum(1 for g in godz if re.search(rf"\b{g}\b", prosty))
                if not w_wpisie:
                    continue
            else:
                w_wpisie = 0
            pkt = round(pokrycie * 10 + w_wpisie * 2, 1)
            if pkt > wynik:
                wynik, najlepszy = pkt, (wpis, naglowek)
    if not najlepszy:
        return "", 0, ""
    return re.sub(r"\s+", " ", najlepszy[0]).strip(), wynik, najlepszy[1]


def main():
    linie = [l for l in TABELA.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    wiersze = list(csv.DictReader(linie, delimiter="\t"))

    out, bez_dokumentu, slabe = [], 0, 0
    for n, w in enumerate(wiersze):
        kandydaci = dokumenty_dla(w["zrodlo"])
        if not kandydaci:
            sciezka, p = "", None
            bez_dokumentu += 1
            out.append({"nr": n, "rok": w["rok"], "dzielnica": w["dzielnica"],
                        "nazwa": w["nazwa"], "zrodlo": w["zrodlo"],
                        "dokument": "(brak w repo)", "trafnosc": "", "cytat": ""})
            continue
        cytat, pkt, skad, sciezka = "", 0, "", ""
        for sc, p in kandydaci:
            bloki = wybierz_bloki(wczytaj(p), w["zrodlo"], w["rok"])
            c, pk, sk = znajdz(w, bloki)
            if pk > pkt:
                cytat, pkt, skad, sciezka = c, pk, sk, sc
        # Prog dobrany tak, zeby przechodzilo dopasowanie z wiekszoscia slow
        # miejsca i trafiona godzina.
        if pkt < 7:
            slabe += 1
            cytat = ""
        out.append({"nr": n, "rok": w["rok"], "dzielnica": w["dzielnica"],
                    "nazwa": w["nazwa"], "zrodlo": w["zrodlo"],
                    "dokument": (skad or sciezka).rsplit("/", 1)[-1],
                    "trafnosc": pkt, "cytat": cytat})

    write_csv(OUT_DIR / "cytaty_kandydaci.tsv", out,
              ["nr", "rok", "dzielnica", "nazwa", "zrodlo", "dokument", "trafnosc", "cytat"])
    znalezione = sum(1 for o in out if o["cytat"])
    print(f"wierszy: {len(wiersze)}")
    print(f"  z cytatem: {znalezione}")
    print(f"  dopasowanie za slabe: {slabe}")
    print(f"  bez dokumentu w repo: {bez_dokumentu}")


if __name__ == "__main__":
    main()
