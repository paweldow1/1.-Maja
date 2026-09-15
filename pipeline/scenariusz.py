"""Extract a timed scenario of the day from the Berlin rocznik corpus.

The corpus below the YAML is 84% of the German roczniki and the pipeline
never read it. It holds what the maps do not: district events copied from
the press, each with an address, a district and an hour.

This produces candidates with the source line kept alongside, not finished
rows -- deciding what counts as an event is a reading, not a regex.

Usage: python3 scenariusz.py
"""
import csv
import json
import re
from pathlib import Path

from common import write_csv
from config.layers import ACTOR_KEYWORDS_DE

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
ROCZNIK = BASE / "input/DE_1990-2019.md"
GRANICE = BASE / "input/berlin/umap_backup_1-mai-berlin_aktualna16.umap"

NAGLOWEK_ROKU = re.compile(r"^#\s+(\d{4})_(?:PL|DE)\.md\s*$")
NAGLOWEK = re.compile(r"^(#{1,4})\s+(.+?)\s*$")

# A time is either written with a colon, or spelled out with "Uhr". Bare
# dotted pairs are dates -- "2.05" is the second of May, not five past two.
ZAKRES = re.compile(r"\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?[-\s]*Uhr\b")
GODZINA = re.compile(r"\b(\d{1,2}):(\d{2})\b|\b(\d{1,2})(?:[.:](\d{2}))?[-\s]*Uhr\b")


def dzielnice_berlina():
    dane = json.loads(GRANICE.read_text(encoding="utf-8"))
    nazwy = set()
    for warstwa in dane["layers"]:
        if warstwa.get("properties", {}).get("name") == "Stadteile":
            for f in warstwa["features"]:
                for pole in ("OTEIL", "BEZIRK"):
                    if f["properties"].get(pole):
                        nazwy.add(f["properties"][pole])
    # The press writes "Treptow" where the register says "Alt-Treptow".
    for nazwa in list(nazwy):
        rdzen = re.sub(r"^(?:Alt|Neu)-", "", nazwa)
        if rdzen != nazwa and len(rdzen) > 4:
            nazwy.add(rdzen)
    return sorted(nazwy, key=len, reverse=True)


def minuty(godz, minut):
    g, m = int(godz), int(minut or 0)
    return g * 60 + m if 0 <= g <= 23 and 0 <= m <= 59 else None


def czasy(tekst):
    """-> (od, do) as HH:MM, reading a range first so it is not split."""
    m = ZAKRES.search(tekst)
    if m:
        od = minuty(m.group(1), m.group(2))
        do = minuty(m.group(3), m.group(4))
        if od is not None and do is not None:
            return f"{od // 60:02d}:{od % 60:02d}", f"{do // 60:02d}:{do % 60:02d}"
    m = GODZINA.search(tekst)
    if m:
        godz = m.group(1) or m.group(3)
        minut = m.group(2) or m.group(4)
        od = minuty(godz, minut)
        if od is not None:
            return f"{od // 60:02d}:{od % 60:02d}", ""
    return "", ""


def sekcje_roku(linie):
    """Yield (rok, nr_linii, tekst, sciezka_naglowkow) for the body text."""
    glowy = [i for i, l in enumerate(linie) if NAGLOWEK_ROKU.match(l)]
    for n, start in enumerate(glowy):
        koniec = glowy[n + 1] if n + 1 < len(glowy) else len(linie)
        rok = int(NAGLOWEK_ROKU.match(linie[start]).group(1))
        cialo = linie[start + 1:koniec]
        pierwsza = next((i for i, l in enumerate(cialo) if l.strip()), 0)
        sep = [i for i, l in enumerate(cialo) if l.strip() == "---" and i > pierwsza]
        poczatek = (sep[0] + 1) if sep else pierwsza
        sciezka = []
        for offset, linia in enumerate(cialo[poczatek:], start=poczatek):
            naglowek = NAGLOWEK.match(linia)
            if naglowek:
                poziom = len(naglowek.group(1))
                sciezka = sciezka[:poziom - 1] + [naglowek.group(2)]
                continue
            if linia.strip():
                yield rok, start + 1 + offset, linia.strip(), " / ".join(sciezka)


def main():
    linie = ROCZNIK.read_text(encoding="utf-8").split("\n")
    dzielnice = dzielnice_berlina()
    wiersze = []

    for rok, nr, tekst, sciezka in sekcje_roku(linie):
        od, do = czasy(tekst)
        if not od:
            continue
        czysty = re.sub(r"[*_`#>\[\]]", "", tekst)
        trafione = [d for d in dzielnice if re.search(r"\b%s\b" % re.escape(d), czysty)]
        aktorzy = [a for a in ACTOR_KEYWORDS_DE
                   if re.search(r"\b%s\b" % re.escape(a), czysty)]
        wiersze.append({
            "rok": rok,
            "godzina_od": od,
            "godzina_do": do,
            "dzielnica": trafione[0] if trafione else "",
            "dzielnice_wszystkie": ";".join(trafione),
            "aktor_zgadniety": ";".join(aktorzy),
            "sekcja": sciezka,
            "tekst": czysty[:400],
            "wiersz_zrodlowy": nr,
        })

    # The same line can be quoted twice in a year's notes.
    widziane, unikalne = set(), []
    for w in wiersze:
        klucz = (w["rok"], w["godzina_od"], w["tekst"])
        if klucz not in widziane:
            widziane.add(klucz)
            unikalne.append(w)
    wiersze = unikalne
    wiersze.sort(key=lambda w: (w["rok"], w["godzina_od"]))
    write_csv(OUT_DIR / "scenariusz_berlin.csv", wiersze, [
        "rok", "godzina_od", "godzina_do", "dzielnica", "dzielnice_wszystkie",
        "aktor_zgadniety", "sekcja", "tekst", "wiersz_zrodlowy"])

    lata = sorted({w["rok"] for w in wiersze})
    z_dzielnica = [w for w in wiersze if w["dzielnica"]]
    print(f"scenariusz_berlin.csv: {len(wiersze)} wpisow z godzina, {len(lata)} lat "
          f"({lata[0]}-{lata[-1]})")
    print(f"  z rozpoznana dzielnica: {len(z_dzielnica)}")
    print(f"  z rozpoznanym aktorem:  {sum(1 for w in wiersze if w['aktor_zgadniety'])}")
    braki = [r for r in range(lata[0], lata[-1] + 1) if r not in lata]
    if braki:
        print(f"  lata bez wpisow: {braki}")


if __name__ == "__main__":
    main()
