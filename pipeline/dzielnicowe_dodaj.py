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

# PDS i Die Linke to jedna linia: partia zmienila nazwe w 2007, a Maifest
# w Koepenick czy na Mariannenplatz odbywal sie dalej. Liczac je osobno
# rozcina sie kazdy cykl na pol dokladnie w tym miejscu.
LINIA_LEWICY = {"PDS", "Die Linke", "Linkspartei", "PDS / Die Linke",
                "PDS/Die Linke"}
LINIA = "PDS/Die Linke"

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
    for k in ("godzina_do", "miejsce", "osoby", "seria", "data", "aktor_linia",
              "edycja", "edycja_zrodlo"):
        if k not in kolumny:
            kolumny.append(k)

    serie = wczytaj_tsv(SERIE)
    poczatki = {s["seria"]: int(s["od_roku"]) for s in serie
                if s.get("od_roku", "").isdigit()}

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
            "aktor_linia": LINIA if d["aktor"] in LINIA_LEWICY else d["aktor"],
            "aktor_zrodlo": "dzielnicowe.tsv", "charakter": "niezwiazkowe",
            "nazwa": d["nazwa"], "opis": d.get("zrodlo", ""),
            "godzina": d.get("godzina_od", ""), "godzina_do": d.get("godzina_do", ""),
            "miejsce": d.get("miejsce", ""), "osoby": d.get("osoby", ""),
            "seria": d.get("seria", ""),
            # 30 kwietnia to nie 1 maja: "Tanz in den Mai" to wieczor
            # poprzedzajacy, osobne wydarzenie, i tak ma byc liczone.
            "data": d.get("data", "01.05"),
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
        # Ktora to edycja cyklu. Liczona od roku poczatkowego z tabeli serii,
        # nie od najstarszego opisu, jaki mamy -- brak opisu nie znaczy, ze
        # edycji nie bylo. Zrodlo policzenia idzie obok liczby.
        seria_nazwa = d.get("seria", "")
        if seria_nazwa in poczatki:
            wiersz["edycja"] = int(d["rok"]) - poczatki[seria_nazwa] + 1
            wiersz["edycja_zrodlo"] = f"od {poczatki[seria_nazwa]}"
        wydarzenia.append(wiersz)
        dodane += 1

    write_csv(OUT_DIR / "wydarzenia.csv", wydarzenia, kolumny)

    write_csv(OUT_DIR / "dzielnicowe_serie.csv", serie,
              ["seria", "dzielnica", "aktor", "od_roku", "do_roku", "dowod"])

    opisane = {(w["seria"], w["rok"]) for w in wydarzenia if w.get("seria")}
    from collections import Counter
    wg_daty = Counter(w.get("data") for w in wydarzenia if w["warstwa"] == "Dzielnicowe")
    luki = []
    for s in serie:
        if not (s["od_roku"].isdigit() and s["do_roku"].isdigit()):
            continue
        brak = [r for r in range(int(s["od_roku"]), int(s["do_roku"]) + 1)
                if (s["seria"], str(r)) not in opisane]
        if brak:
            luki.append((s["seria"], brak))

    print(f"dzielnicowe: +{dodane} wydarzen, {len(wydarzenia)} wierszy razem")
    print("  wg daty: " + ", ".join(f"{d or '?'}: {n}" for d, n in sorted(wg_daty.items())))
    w_cyklu = sum(1 for w in wydarzenia
                  if w["warstwa"] == "Dzielnicowe" and w.get("seria"))
    print(f"  w znanym cyklu: {w_cyklu} z {dodane or w_cyklu} "
          f"-- reszta to pojedyncze wydarzenia")
    print(f"dzielnicowe_serie.csv: {len(serie)} cykli")
    for seria, brak in luki:
        print(f"  {seria}: bez opisu {len(brak)} edycji "
              f"({brak[0]}-{brak[-1]})")


if __name__ == "__main__":
    main()
