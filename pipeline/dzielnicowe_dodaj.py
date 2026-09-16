"""Add the district events, which no map ever carried.

The dzielnicowki -- the SPD's and PDS/Linke's local-branch festivals out in
the boroughs -- were never put on the maps, so there is nothing to parse.
They come in as prose from the press and the chronicles, are typed into
input/dzielnicowe.tsv, and are appended here as ordinary event rows, with
the hours the prose gives.

input/dzielnicowe_serie.tsv records which of them are annual series, so the
continuity of a cycle can be counted even where a single edition has no
write-up. It adds no rows: an edition nobody described is not invented.

Runs after rozbij_upamietnienia.py and before identyfikatory.py, so the new
rows get ids on the same terms as everything else.

Usage: python3 dzielnicowe_dodaj.py
"""
import csv
from pathlib import Path

from common import write_csv

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
TABELA = BASE / "input/dzielnicowe.tsv"
SERIE = BASE / "input/dzielnicowe_serie.tsv"


def wczytaj_tsv(sciezka):
    if not sciezka.exists():
        return []
    linie = [l for l in sciezka.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    return list(csv.DictReader(linie, delimiter="\t"))


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wydarzenia = list(csv.DictReader(f))
    kolumny = list(wydarzenia[0].keys())
    for k in ("godzina_do", "miejsce", "osoby", "seria"):
        if k not in kolumny:
            kolumny.append(k)

    wpisy = wczytaj_tsv(TABELA)
    istniejace = {w["klucz_zrodlowy"] for w in wydarzenia}
    dodane = 0
    for n, d in enumerate(wpisy):
        klucz = f"dzielnicowe.tsv#{d['miasto']}#{d['rok']}#{n}"
        if klucz in istniejace:
            continue
        wiersz = {k: "" for k in kolumny}
        wiersz.update({
            "rok": d["rok"], "rok_zrodlo": "dzielnicowe.tsv", "miasto": d["miasto"],
            "warstwa": "Dzielnicowe", "typ": "festyn", "typ_zrodlo": "dzielnicowe.tsv",
            "aktor": d["aktor"], "aktor_zgadniety": "False",
            "aktor_zrodlo": "dzielnicowe.tsv", "charakter": "niezwiazkowe",
            "nazwa": d["nazwa"], "opis": d.get("zrodlo", ""),
            "godzina": d.get("godzina_od", ""), "godzina_do": d.get("godzina_do", ""),
            "miejsce": d.get("miejsce", ""), "osoby": d.get("osoby", ""),
            "seria": d.get("seria", ""),
            "dzielnica_start": d.get("dzielnica", ""),
            "bezirk_start": d.get("dzielnica", ""),
            # By definition: non-central, run by a local branch. That is what
            # put it in this file.
            "centralne": "FALSE", "poza_centrum": "TRUE", "dzielnicowe": "TRUE",
            "organizator_lokalny": f"{d['aktor']} {d.get('dzielnica', '')}".strip(),
            "plik_zrodlowy": "dzielnicowe.tsv", "klucz_zrodlowy": klucz,
            "zrodlo_zlaczenia": "dzielnicowe",
            "wymaga_weryfikacji": "False",
            "decyzja_notatka": d.get("pewnosc", ""),
        })
        wydarzenia.append(wiersz)
        dodane += 1

    write_csv(OUT_DIR / "wydarzenia.csv", wydarzenia, kolumny)

    serie = wczytaj_tsv(SERIE)
    write_csv(OUT_DIR / "dzielnicowe_serie.csv", serie,
              ["seria", "dzielnica", "aktor", "od_roku", "do_roku", "dowod"])

    opisane = {(w["seria"], w["rok"]) for w in wydarzenia if w.get("seria")}
    luki = []
    for s in serie:
        if not (s["od_roku"].isdigit() and s["do_roku"].isdigit()):
            continue
        brak = [r for r in range(int(s["od_roku"]), int(s["do_roku"]) + 1)
                if (s["seria"], str(r)) not in opisane]
        if brak:
            luki.append((s["seria"], brak))

    print(f"dzielnicowe: +{dodane} wydarzen, {len(wydarzenia)} wierszy razem")
    print(f"dzielnicowe_serie.csv: {len(serie)} cykli")
    for seria, brak in luki:
        print(f"  {seria}: bez opisu {len(brak)} edycji "
              f"({brak[0]}-{brak[-1]})")


if __name__ == "__main__":
    main()
