"""Step 5: join the map events with the roczniki and the attendance sources.

Key per instrukcja_v2.md sec. 10: rok + miasto + typ + aktor.

The three outputs are all results in their own right. tylko_mapa.csv and
tylko_rocznik.csv are not a failure of the join -- they show where each
source knows something the other does not.

Usage: python3 join.py
"""
import csv
from pathlib import Path

from common import MIEJSCA_COLUMNS, WYDARZENIA_COLUMNS, write_csv

OUT_DIR = Path(__file__).parent / "output"


def wczytaj(nazwa):
    sciezka = OUT_DIR / nazwa
    with sciezka.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    mapy = wczytaj("wydarzenia_warszawa.csv") + wczytaj("wydarzenia_berlin.csv")
    roczniki = wczytaj("roczniki_wydarzenia.csv")
    frekwencja = wczytaj("frekwencja_agg.csv")

    # Attendance is keyed on rok+miasto+aktor; an actor can hold several
    # events in a year, so keep them all and let the row pick by type.
    fr_index = {}
    for f in frekwencja:
        fr_index.setdefault((f["rok"], f["miasto"], f["aktor"]), []).append(f)

    rocz_index = {}
    for r in roczniki:
        rocz_index.setdefault((r["rok"], r["miasto"], r["typ"], r["aktor"]), []).append(r)

    # A rocznik row carrying only a slogan has no type to key on -- that is a
    # gap in the source, not an absent event -- so those match on
    # rok+miasto+aktor alone, preferring the demonstration when the actor
    # held several kinds of event that year. The level is recorded.
    luzny_index = {}
    for r in roczniki:
        if not r["typ"]:
            luzny_index.setdefault((r["rok"], r["miasto"], r["aktor"]), []).append(r)

    uzyte_rocz = set()
    polaczone, tylko_mapa = [], []

    for m in mapy:
        klucz = (m["rok"], m["miasto"], m["typ"], m["aktor"])
        trafienia = rocz_index.get(klucz, [])
        poziom = "pelny"
        if not trafienia and m["aktor"]:
            luzny_klucz = (m["rok"], m["miasto"], m["aktor"])
            kandydaci_l = luzny_index.get(luzny_klucz, [])
            if kandydaci_l:
                typy_aktora = {x["typ"] for x in mapy
                               if (x["rok"], x["miasto"], x["aktor"]) == luzny_klucz}
                # Attach to one type only, or the slogan lands on every event
                # the actor held that year.
                docelowy = "demonstracja" if "demonstracja" in typy_aktora else (
                    next(iter(typy_aktora)) if len(typy_aktora) == 1 else None)
                if docelowy == m["typ"]:
                    trafienia = kandydaci_l
                    poziom = "bez typu"
                    uzyte_rocz.add((m["rok"], m["miasto"], "", m["aktor"]))
        wiersz = dict(m)
        if trafienia:
            uzyte_rocz.add(klucz)
            r = trafienia[0]
            wiersz.update({
                "zrodlo_zlaczenia": "mapa+rocznik",
                "poziom_zlaczenia": poziom,
                "trasa_rocznik": r["trasa"],
                "haslo_rocznik": r["haslo"],
                "frekwencja_rocznik": r["frekwencja_sr"],
                "klucze_rocznik": r["klucze_zrodlowe"],
            })
        else:
            wiersz.update({
                "zrodlo_zlaczenia": "tylko mapa", "poziom_zlaczenia": "",
                "trasa_rocznik": "", "haslo_rocznik": "",
                "frekwencja_rocznik": "", "klucze_rocznik": "",
            })

        kandydaci = fr_index.get((m["rok"], m["miasto"], m["aktor"]), [])
        if kandydaci:
            # Prefer a reading whose event label matches this row's type.
            pasujace = [k for k in kandydaci if m["typ"] in k["wydarzenie"]] or kandydaci
            f = pasujace[0]
            wiersz.update({
                "frekwencja_zrodlo": f["frekwencja_sr"],
                "frekwencja_n_odczytow": f["n_odczytow"],
                "frekwencja_wydarzenie": f["wydarzenie"],
            })
        else:
            wiersz.update({"frekwencja_zrodlo": "", "frekwencja_n_odczytow": "",
                           "frekwencja_wydarzenie": ""})

        polaczone.append(wiersz)
        if not trafienia:
            tylko_mapa.append(wiersz)

    tylko_rocznik = [
        r for r in roczniki
        if (r["rok"], r["miasto"], r["typ"], r["aktor"]) not in uzyte_rocz
    ]

    kolumny = WYDARZENIA_COLUMNS + [
        "zrodlo_zlaczenia", "poziom_zlaczenia", "trasa_rocznik", "haslo_rocznik", "frekwencja_rocznik",
        "klucze_rocznik", "frekwencja_zrodlo", "frekwencja_n_odczytow",
        "frekwencja_wydarzenie"]
    write_csv(OUT_DIR / "wydarzenia.csv", polaczone, kolumny)
    write_csv(OUT_DIR / "tylko_mapa.csv", tylko_mapa, kolumny)
    write_csv(OUT_DIR / "tylko_rocznik.csv", tylko_rocznik, list(roczniki[0].keys()))

    miejsca = wczytaj("miejsca_warszawa.csv") + wczytaj("miejsca_berlin.csv")
    write_csv(OUT_DIR / "miejsca.csv", miejsca, MIEJSCA_COLUMNS)

    z_rocznikiem = sum(1 for w in polaczone if w["zrodlo_zlaczenia"] == "mapa+rocznik")
    z_frekwencja = sum(1 for w in polaczone if w["frekwencja_zrodlo"])
    luzne = sum(1 for w in polaczone if w.get("poziom_zlaczenia") == "bez typu")
    print(f"wydarzenia.csv:    {len(polaczone)} wierszy")
    print(f"  z rocznikiem:    {z_rocznikiem}")
    print(f"    w tym bez typu: {luzne}")
    print(f"  z frekwencja:    {z_frekwencja}")
    print(f"tylko_mapa.csv:    {len(tylko_mapa)}")
    print(f"tylko_rocznik.csv: {len(tylko_rocznik)} z {len(roczniki)} wierszy roczników")
    print(f"miejsca.csv:       {len(miejsca)}")


if __name__ == "__main__":
    main()
