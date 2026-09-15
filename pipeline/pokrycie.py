"""Where the district record is thin -- a reading list, not a result.

Counts what is documented per year and district, from the map and from the
chronicle separately. A zero is not evidence that nothing happened there;
it marks a year nobody wrote up, which is exactly where to go looking.

Usage: python3 pokrycie.py [PL|DE]
"""
import csv
import sys
from pathlib import Path

from common import write_csv

OUT_DIR = Path(__file__).parent / "output"


def wczytaj(nazwa):
    with (OUT_DIR / nazwa).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(miasto="DE"):
    wydarzenia = [w for w in wczytaj("wydarzenia.csv") if w["miasto"] == miasto]
    scenariusz = [s for s in wczytaj("scenariusz.csv") if s["miasto"] == miasto]

    na_mapie, w_kronice = {}, {}
    for w in wydarzenia:
        if w["dzielnica_start"]:
            na_mapie[(int(w["rok"]), w["dzielnica_start"])] = \
                na_mapie.get((int(w["rok"]), w["dzielnica_start"]), 0) + 1
    for s in scenariusz:
        if s["dzielnica"] and s["zrodlo"] == "korpus":
            w_kronice[(int(s["rok"]), s["dzielnica"])] = \
                w_kronice.get((int(s["rok"]), s["dzielnica"]), 0) + 1

    lata = sorted({r for r, _ in na_mapie} | {r for r, _ in w_kronice})
    dzielnice = sorted({d for _, d in na_mapie} | {d for _, d in w_kronice})

    wiersze = []
    for rok in lata:
        for dzielnica in dzielnice:
            m = na_mapie.get((rok, dzielnica), 0)
            k = w_kronice.get((rok, dzielnica), 0)
            if m or k:
                wiersze.append({"rok": rok, "miasto": miasto, "dzielnica": dzielnica,
                                "na_mapie": m, "w_kronice": k, "razem": m + k})
    write_csv(OUT_DIR / f"pokrycie_dzielnic_{miasto}.csv", wiersze,
              ["rok", "miasto", "dzielnica", "na_mapie", "w_kronice", "razem"])

    print(f"{miasto}: {len(wiersze)} par rok/dzielnica z jakimkolwiek zapisem, "
          f"{len(dzielnice)} dzielnic, {len(lata)} lat")
    print(f"    siatka pelna mialaby {len(lata) * len(dzielnice)} pol -- "
          f"udokumentowane {100 * len(wiersze) // (len(lata) * len(dzielnice))}%")

    print("\n  rok  dzielnic  na mapie  w kronice   tylko w kronice")
    for rok in lata:
        wiersz = [w for w in wiersze if w["rok"] == rok]
        tylko_kronika = [w for w in wiersz if w["w_kronice"] and not w["na_mapie"]]
        print(f"  {rok}  {len(wiersz):8d}  {sum(w['na_mapie'] for w in wiersz):8d}"
              f"  {sum(w['w_kronice'] for w in wiersz):9d}   "
              + (", ".join(w["dzielnica"] for w in tylko_kronika[:5]) or "-"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "DE")
