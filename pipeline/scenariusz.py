"""Build a timed scenario of the day, for both cities.

Two sources, because neither covers the other's ground:

  korpus  the text below the YAML in the roczniki -- 84% of the German
          material, where the district events copied from the press live
  mapa    the description of each map object, which carries times the
          roczniki do not, and is the only timed source for Warsaw

A multi-year object has one description covering every year it ran, so a
time taken from it is only pinned to a year when the description is split
by year; otherwise the row says the time is shared.

Usage: python3 scenariusz.py
"""
import csv
import json
import re
from pathlib import Path

from common import write_csv
from config.layers import ACTOR_KEYWORDS_DE, ACTOR_KEYWORDS_PL

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
ROCZNIKI = {"DE": BASE / "input/DE_1990-2019.md", "PL": BASE / "input/PL_1990-2019.md"}
GRANICE = {
    "DE": (BASE / "input/berlin/umap_backup_1-mai-berlin_aktualna16.umap", "Stadteile",
           ("OTEIL", "BEZIRK")),
    "PL": (BASE / "input/warszawa/umap_backup_1-maja_warszawa9.umap", "Obszary MSI",
           ("name",)),
}

NAGLOWEK_ROKU = re.compile(r"^#\s+(\d{4})_(?:PL|DE)\.md\s*$")
NAGLOWEK = re.compile(r"^(#{1,4})\s+(.+?)\s*$")

# A time carries a colon, the word Uhr, or Polish "godz". A bare dotted pair
# is a date: "2.05" is the second of May, not five past two.
ZAKRES = re.compile(r"\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?[-\s]*(?:Uhr)\b")
GODZINA = re.compile(
    r"\b(\d{1,2}):(\d{2})\b"
    r"|\b(\d{1,2})(?:[.:](\d{2}))?[-\s]*Uhr\b"
    r"|godz\w*\.?\s*(\d{1,2})(?:[.:](\d{2}))?")
ROK_SEGMENT = re.compile(r"(?:^|\n)\s*#{0,4}\s*((?:19|20)\d{2})\s*[:–.-]")


def dzielnice(miasto):
    sciezka, warstwa, pola = GRANICE[miasto]
    dane = json.loads(Path(sciezka).read_text(encoding="utf-8"))
    nazwy = set()
    for l in dane["layers"]:
        if l.get("properties", {}).get("name") != warstwa:
            continue
        for f in l["features"]:
            for pole in pola:
                if f["properties"].get(pole):
                    nazwy.add(f["properties"][pole])
            if not pola[0] in f["properties"] and f["properties"].get("name"):
                nazwy.add(f["properties"]["name"])
    for nazwa in list(nazwy):
        rdzen = re.sub(r"^(?:Alt|Neu)-", "", nazwa)
        if rdzen != nazwa and len(rdzen) > 4:
            nazwy.add(rdzen)
    return nazwy


def minuty(godz, minut):
    g, m = int(godz), int(minut or 0)
    return g * 60 + m if 0 <= g <= 23 and 0 <= m <= 59 else None


def hhmm(wartosc):
    return f"{wartosc // 60:02d}:{wartosc % 60:02d}"


def wpisy_z_tekstu(tekst):
    """Yield (od, do, fragment) for every time in the text, not just the first.

    One description can enumerate a whole afternoon of district festivals --
    "Kreuzberg, 15-21 Uhr, Mariannenplatz, Prenzlauer Berg, 10-18 Uhr,
    Humannplatz, Treptow, 14-18 Uhr, ..." -- and taking one time per
    description collapses seven events into one.
    """
    znalezione = []
    zajete = []
    for m in ZAKRES.finditer(tekst):
        od, do = minuty(m.group(1), m.group(2)), minuty(m.group(3), m.group(4))
        if od is not None and do is not None:
            znalezione.append((m.start(), m.end(), hhmm(od), hhmm(do)))
            zajete.append((m.start(), m.end()))
    for m in GODZINA.finditer(tekst):
        if any(p <= m.start() < k for p, k in zajete):
            continue
        godz = m.group(1) or m.group(3) or m.group(5)
        minut = m.group(2) or m.group(4) or m.group(6)
        od = minuty(godz, minut)
        if od is None:
            continue
        if m.group(1) is not None and int(godz) < 5:
            continue
        znalezione.append((m.start(), m.end(), hhmm(od), ""))
    znalezione.sort()

    for i, (start, koniec, od, do) in enumerate(znalezione):
        # The place is usually named just before its hour and the detail just
        # after, so the window reaches back to the previous entry and forward
        # to the next.
        lewo = znalezione[i - 1][1] if i else 0
        prawo = znalezione[i + 1][0] if i + 1 < len(znalezione) else len(tekst)
        fragment = tekst[max(lewo, start - 110):min(prawo + 40, koniec + 150)]
        yield od, do, fragment


def czasy(tekst):
    m = ZAKRES.search(tekst)
    if m:
        od, do = minuty(m.group(1), m.group(2)), minuty(m.group(3), m.group(4))
        if od is not None and do is not None:
            return hhmm(od), hhmm(do)
    for m in GODZINA.finditer(tekst):
        godz = m.group(1) or m.group(3) or m.group(5)
        minut = m.group(2) or m.group(4) or m.group(6)
        od = minuty(godz, minut)
        if od is None:
            continue
        # A bare "0:19" is a timestamp in a cited recording, not an hour of
        # the day -- the descriptions quote rbb footage that way. Anything
        # before 5am has to say Uhr or godz to count.
        if m.group(1) is not None and int(godz) < 5:
            continue
        return hhmm(od), ""
    return "", ""


def segment_roku(opis, rok):
    """-> (fragment, przypisany_do_roku). A description split by year gives
    that year's part; otherwise the whole text, shared across its years."""
    znaczniki = list(ROK_SEGMENT.finditer(opis))
    if len(znaczniki) < 2:
        return opis, False
    for i, m in enumerate(znaczniki):
        if m.group(1) == str(rok):
            koniec = znaczniki[i + 1].start() if i + 1 < len(znaczniki) else len(opis)
            return opis[m.start():koniec], True
    return "", True


def oczysc(tekst):
    return re.sub(r"\s+", " ", re.sub(r"[*_`#>\[\]]", "", tekst)).strip()


def dopasuj(tekst, slownik):
    """Names in the order they appear: the venue is named before the organiser."""
    pozycje = []
    for nazwa in slownik:
        m = re.search(r"\b%s\b" % re.escape(nazwa), tekst)
        if m:
            pozycje.append((m.start(), -len(nazwa), nazwa))
    return [n for _, _, n in sorted(pozycje)]


def z_korpusu(miasto, slownik_dzielnic, slownik_aktorow):
    sciezka = ROCZNIKI[miasto]
    if not sciezka.exists():
        return []
    linie = sciezka.read_text(encoding="utf-8").split("\n")
    glowy = [i for i, l in enumerate(linie) if NAGLOWEK_ROKU.match(l)]
    wiersze = []
    for n, start in enumerate(glowy):
        koniec = glowy[n + 1] if n + 1 < len(glowy) else len(linie)
        rok = int(NAGLOWEK_ROKU.match(linie[start]).group(1))
        cialo = linie[start + 1:koniec]
        pierwsza = next((i for i, l in enumerate(cialo) if l.strip()), 0)
        sep = [i for i, l in enumerate(cialo) if l.strip() == "---" and i > pierwsza]
        sciezka_naglowkow = []
        for offset, linia in enumerate(cialo[(sep[0] + 1) if sep else pierwsza:],
                                       start=(sep[0] + 1) if sep else pierwsza):
            naglowek = NAGLOWEK.match(linia)
            if naglowek:
                poziom = len(naglowek.group(1))
                sciezka_naglowkow = sciezka_naglowkow[:poziom - 1] + [naglowek.group(2)]
                continue
            if not linia.strip():
                continue
            for od, do, fragment in wpisy_z_tekstu(linia):
                czysty = oczysc(fragment)
                trafione = dopasuj(czysty, slownik_dzielnic)
                wiersze.append({
                    "rok": rok, "miasto": miasto, "godzina_od": od, "godzina_do": do,
                    "dzielnica": trafione[0] if trafione else "",
                    "dzielnice_wszystkie": ";".join(trafione),
                    "aktor": ";".join(dopasuj(czysty, slownik_aktorow)),
                    # only says the entry names a Bezirk, not that the event
                    # was a district one -- see the note in dzielnice.py
                    "skala": "nazwana dzielnica" if trafione else "",
                    "zrodlo": "korpus",
                    "sekcja": " / ".join(sciezka_naglowkow),
                    "id_wydarzenia": "",
                    "tekst": czysty[:400],
                    "odniesienie": f"{sciezka.name}:{start + 1 + offset}",
                })
    return wiersze


ROK_ZRODLA = re.compile(r"(?:19|20)\d{2}")
DATA_ZRODLA = re.compile(r"\d{1,2}\.\d{2}\.((?:19|20)\d{2})")


def z_mapy(wydarzenia, slowniki_dzielnic, slowniki_aktorow):
    # Group the year-split rows back into the objects they came from. An
    # object whose description is not split by year has one text covering all
    # of them, so its entries are emitted once rather than repeated for every
    # year -- nine years of one quote would otherwise be nine copies.
    obiekty = {}
    for w in wydarzenia:
        obiekty.setdefault((w.get("plik_zrodlowy"), w.get("id_geo")), []).append(w)

    zadania = []
    for grupa in obiekty.values():
        opis = grupa[0].get("opis") or ""
        if not opis:
            continue
        lata = sorted(int(g["rok"]) for g in grupa)
        po_latach = len(list(ROK_SEGMENT.finditer(opis))) >= 2
        if po_latach:
            for g in grupa:
                fragment, _ = segment_roku(opis, int(g["rok"]))
                if fragment.strip():
                    zadania.append((g, int(g["rok"]), fragment, True, lata))
        else:
            zadania.append((grupa[0], None, opis, len(lata) == 1, lata))

    wiersze = []
    for w, rok_wymuszony, fragment_roku, pinowany, lata in zadania:
        for od, do, fragment in wpisy_z_tekstu(fragment_roku):
            # An undated shared description often cites its own source date
            # ("ND 30.04.1997"); that pins the entry better than the object's
            # first year does.
            if rok_wymuszony is not None:
                rok = rok_wymuszony
            else:
                cytowane = [int(r) for r in ROK_ZRODLA.findall(fragment)
                            if lata[0] <= int(r) <= lata[-1]]
                if not cytowane:
                    # The citation often trails the whole quote ("ND
                    # 30.04.1997"), outside this entry's window. A full date
                    # is unambiguous enough to attribute the passage.
                    cytowane = [int(d) for d in DATA_ZRODLA.findall(fragment_roku)
                                if lata[0] <= int(d) <= lata[-1]]
                rok = cytowane[0] if cytowane else lata[0]
            czysty = oczysc(fragment)
            trafione = dopasuj(czysty, slowniki_dzielnic[w["miasto"]])
            # A district named inside this fragment beats the object's own
            # location: the enumeration is about other places than the pin.
            dzielnica = trafione[0] if trafione else (w.get("dzielnica_start") or "")
            wiersze.append({
                "rok": rok, "miasto": w["miasto"], "godzina_od": od, "godzina_do": do,
                "dzielnica": dzielnica,
                "dzielnice_wszystkie": ";".join(trafione),
                "aktor": w.get("aktor") or ";".join(dopasuj(czysty, slowniki_aktorow[w["miasto"]])),
                "skala": "poza centrum" if w.get("poza_centrum") == "TRUE" else (
                    "centrum" if w.get("centralne") == "TRUE" else ""),
                "zrodlo": "mapa" if pinowany else (
                    f"mapa (opis wspolny {lata[0]}-{lata[-1]})"),
                "sekcja": w.get("warstwa", ""),
                "id_wydarzenia": w.get("id", ""),
                "tekst": (w.get("nazwa") or "")[:50] + " | " + czysty[:340],
                "odniesienie": f"{w.get('plik_zrodlowy', '')}#{w.get('id_geo', '')}",
            })
    return wiersze


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wydarzenia = list(csv.DictReader(f))

    slowniki_dzielnic = {m: dzielnice(m) for m in ("PL", "DE")}
    slowniki_aktorow = {"PL": ACTOR_KEYWORDS_PL, "DE": ACTOR_KEYWORDS_DE}

    wiersze = []
    for miasto in ("PL", "DE"):
        wiersze += z_korpusu(miasto, slowniki_dzielnic[miasto], slowniki_aktorow[miasto])
    wiersze += z_mapy(wydarzenia, slowniki_dzielnic, slowniki_aktorow)

    widziane, unikalne = set(), []
    for w in wiersze:
        klucz = (w["rok"], w["miasto"], w["godzina_od"], w["tekst"][:120])
        if klucz not in widziane:
            widziane.add(klucz)
            unikalne.append(w)
    unikalne.sort(key=lambda w: (w["miasto"], w["rok"], w["godzina_od"]))

    write_csv(OUT_DIR / "scenariusz.csv", unikalne, [
        "rok", "miasto", "godzina_od", "godzina_do", "dzielnica",
        "dzielnice_wszystkie", "aktor", "skala", "zrodlo", "sekcja",
        "id_wydarzenia", "tekst", "odniesienie"])

    for miasto in ("PL", "DE"):
        sel = [w for w in unikalne if w["miasto"] == miasto]
        lata = sorted({w["rok"] for w in sel})
        z_korp = sum(1 for w in sel if w["zrodlo"] == "korpus")
        z_map = len(sel) - z_korp
        dz = sum(1 for w in sel if w["dzielnica"])
        print(f"{miasto}: {len(sel)} wpisow ({z_korp} korpus, {z_map} mapa), "
              f"{len(lata)} lat, {dz} z dzielnica")
        braki = [r for r in range(min(lata), max(lata) + 1) if r not in lata]
        if braki:
            print(f"    lata bez godzin: {braki}")


if __name__ == "__main__":
    main()
