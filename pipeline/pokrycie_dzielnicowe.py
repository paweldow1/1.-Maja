"""Co juz mam o dzielnicowkach, rok po roku -- zeby nie zbierac dwa razy.

Dla kazdego roku pokazuje trzy rzeczy osobno, bo znacza co innego:

  wpisane   -- wydarzenia z input/dzielnicowe.tsv, kompletne, z godzinami
  z kroniki -- wpisy kronikarskie poza centrum bez obiektu na mapie, czyli
               kandydaci: cos wiem, ale nie wiem kto organizowal
  na mapie  -- obiekty poza centrum, dla porzadku; dzielnicowek tam nie ma

Rok, w ktorym wszystkie trzy sa niskie, to rok do poszukania w prasie.

Usage: python3 pokrycie_dzielnicowe.py
"""
import csv
from collections import defaultdict
from pathlib import Path

from common import write_csv

OUT_DIR = Path(__file__).parent / "output"
ZAKRES = range(1987, 2020)


def wczytaj(nazwa):
    sciezka = OUT_DIR / nazwa
    if not sciezka.exists():
        return []
    with sciezka.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    wydarzenia = [w for w in wczytaj("wydarzenia.csv") if w["miasto"] == "DE"]
    brakujace = [b for b in wczytaj("brakujace_na_mapie.csv") if b["miasto"] == "DE"]

    wpisane, kronika, mapa = defaultdict(list), defaultdict(list), defaultdict(int)
    for w in wydarzenia:
        rok = int(w["rok"])
        if w["warstwa"] == "Dzielnicowe":
            wpisane[rok].append(w)
        elif w.get("poza_centrum") == "TRUE":
            mapa[rok] += 1
    for b in brakujace:
        if b["dzielnicowe"]:
            kronika[int(b["rok"])].append(b)

    wiersze = []
    for rok in ZAKRES:
        k = kronika[rok]
        w = wpisane[rok]
        dzielnice = sorted({x["dzielnica"] for x in k if x["dzielnica"]}
                           | {x["dzielnica_start"] for x in w if x["dzielnica_start"]})
        z_godzina = sum(1 for x in k if x["godzina_od"]) + sum(1 for x in w if x["godzina"])
        razem = len(w) + len(k)
        wiersze.append({
            "rok": rok,
            "wpisane": len(w),
            "z_kroniki": len(k),
            "na_mapie_poza_centrum": mapa[rok],
            "z_godzina": z_godzina,
            "dzielnice": ";".join(dzielnice),
            "ocena": "pusto" if razem == 0 else ("cienko" if razem <= 3 else "jest"),
        })

    write_csv(OUT_DIR / "pokrycie_dzielnicowe.csv", wiersze,
              ["rok", "wpisane", "z_kroniki", "na_mapie_poza_centrum",
               "z_godzina", "dzielnice", "ocena"])

    print(f"{'rok':>5} {'wpis':>5} {'kron':>5} {'godz':>5}  {'ocena':8} dzielnice")
    for w in wiersze:
        print(f"{w['rok']:>5} {w['wpisane']:>5} {w['z_kroniki']:>5} {w['z_godzina']:>5}  "
              f"{w['ocena']:8} {w['dzielnice'][:70]}")
    puste = [str(w["rok"]) for w in wiersze if w["ocena"] == "pusto"]
    cienkie = [str(w["rok"]) for w in wiersze if w["ocena"] == "cienko"]
    print(f"\npusto  ({len(puste):2d}): {', '.join(puste)}")
    print(f"cienko ({len(cienkie):2d}): {', '.join(cienkie)}")


if __name__ == "__main__":
    main()
