"""Apply the verification decisions over the parser's guesses.

The decisions are made on the kartoteka page and exported from its store to
input/decyzje/. They are authoritative: where a decision names an actor or a
type, it replaces what the parser inferred, and the row stops being flagged.

Runs after join.py and dzielnice.py, rewriting wydarzenia.csv in place, so a
fresh parse never loses a judgement already made.

Runs twice. First over the per-city files, before join.py: the join matches
a rocznik entry to a map object by actor, so a correction that lands only
afterwards leaves the entry looking like it has no object at all -- which is
why fifteen `tylko_rocznik` rows came back annotated "jest na mapie". Then
over the joined table, which is where the audit trail and the flags belong.

Usage: python3 zastosuj_decyzje.py            (the joined table)
       python3 zastosuj_decyzje.py --miasta   (the per-city files, aktor/typ only)
"""
import csv
import json
import sys
from pathlib import Path

from common import write_csv

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
DECYZJE = BASE / "input/decyzje"


def wczytaj_decyzje(nazwa):
    sciezka = DECYZJE / f"{nazwa}.json"
    if not sciezka.exists():
        return {}
    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    # the export wraps the document body one level deep
    if isinstance(dane, dict) and "content" in dane and isinstance(dane["content"], dict):
        dane = dane["content"]
    return {k: v for k, v in dane.items() if isinstance(v, dict)}


def przed_zlaczeniem():
    """Only aktor and typ, only in the per-city files."""
    aktorzy = wczytaj_decyzje("aktorzy")
    for nazwa in ("wydarzenia_warszawa.csv", "wydarzenia_berlin.csv"):
        sciezka = OUT_DIR / nazwa
        if not sciezka.exists():
            continue
        with sciezka.open(encoding="utf-8") as f:
            wiersze = list(csv.DictReader(f))
        n = 0
        for w in wiersze:
            d = aktorzy.get(w["klucz_zrodlowy"])
            if not d:
                continue
            if d.get("aktor") and d["aktor"] != w["aktor"]:
                w["aktor"], w["aktor_zgadniety"] = d["aktor"], "False"
                n += 1
            if d.get("typ") and d["typ"] != w["typ"]:
                w["typ"], w["typ_zrodlo"] = d["typ"], "weryfikacja"
                n += 1
        write_csv(sciezka, wiersze, list(wiersze[0].keys()))
        print(f"{nazwa}: {n} poprawek przed zlaczeniem")


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wydarzenia = list(csv.DictReader(f))
    kolumny = list(wydarzenia[0].keys())
    for nowa in ("aktor_zrodlo", "decyzja", "decyzja_notatka"):
        if nowa not in kolumny:
            kolumny.append(nowa)

    aktorzy = wczytaj_decyzje("aktorzy")
    duplikaty = wczytaj_decyzje("duplikaty")
    bez_lat = wczytaj_decyzje("bez_lat")

    # a renamed duplicate: {"nazwa__<id>": "<new name>"}
    nazwy_wariantow = {}
    for d in duplikaty.values():
        for pole, wartosc in d.items():
            if pole.startswith("nazwa__") and str(wartosc).strip():
                nazwy_wariantow[pole[len("nazwa__"):]] = str(wartosc).strip()

    zmiany = {"aktor": 0, "typ": 0, "potwierdzone": 0, "odlozone": 0, "nazwa": 0}
    slad = []

    for w in wydarzenia:
        w.setdefault("aktor_zrodlo", "parser")
        d = aktorzy.get(w["klucz_zrodlowy"])
        if d:
            if d.get("aktor") and d["aktor"] != w["aktor"]:
                slad.append({"id": w["id"], "pole": "aktor", "przed": w["aktor"],
                             "po": d["aktor"], "notatka": d.get("notatka", "")})
                w["aktor"] = d["aktor"]
                w["aktor_zrodlo"] = "weryfikacja"
                w["aktor_zgadniety"] = "False"
                zmiany["aktor"] += 1
            if d.get("typ") and d["typ"] != w["typ"]:
                slad.append({"id": w["id"], "pole": "typ", "przed": w["typ"],
                             "po": d["typ"], "notatka": d.get("notatka", "")})
                w["typ"] = d["typ"]
                w["typ_zrodlo"] = "weryfikacja"
                zmiany["typ"] += 1
            w["decyzja"] = d.get("akcja", "")
            w["decyzja_notatka"] = d.get("notatka", "")
            if d.get("akcja") == "potwierdzam":
                w["wymaga_weryfikacji"] = "False"
                zmiany["potwierdzone"] += 1
            elif d.get("akcja"):
                zmiany["odlozone"] += 1
        else:
            w.setdefault("decyzja", "")
            w.setdefault("decyzja_notatka", "")

        if w["id"] in nazwy_wariantow:
            nowa = nazwy_wariantow[w["id"]]
            slad.append({"id": w["id"], "pole": "nazwa_wariantu", "przed": w["nazwa"],
                         "po": nowa, "notatka": ""})
            w["nazwa"] = nowa
            zmiany["nazwa"] += 1

    write_csv(OUT_DIR / "wydarzenia.csv", wydarzenia, kolumny)
    write_csv(OUT_DIR / "weryfikacja_slad.csv", slad,
              ["id", "pole", "przed", "po", "notatka"])

    # decisions that do not change a row but say what to do next
    zadania = []
    for nazwa, opis in (("brakujace", "dopisac na mape"), ("tylko_rocznik", "z rocznika"),
                        ("bez_lat", "brak lat")):
        for klucz, d in wczytaj_decyzje(nazwa).items():
            if d.get("akcja") or d.get("notatka") or d.get("lata"):
                zadania.append({"kolejka": nazwa, "klucz": klucz,
                                "akcja": d.get("akcja", ""), "lata": d.get("lata", ""),
                                "notatka": d.get("notatka", "")})
    write_csv(OUT_DIR / "weryfikacja_zadania.csv", zadania,
              ["kolejka", "klucz", "akcja", "lata", "notatka"])

    nadal = sum(1 for w in wydarzenia if w["wymaga_weryfikacji"] == "True")
    print(f"decyzje zastosowane: aktor {zmiany['aktor']}, typ {zmiany['typ']}, "
          f"nazwa {zmiany['nazwa']}")
    print(f"  potwierdzone: {zmiany['potwierdzone']}, odlozone: {zmiany['odlozone']}")
    print(f"  wymaga_weryfikacji nadal: {nadal} z {len(wydarzenia)}")
    print(f"  weryfikacja_slad.csv: {len(slad)} zmian")
    print(f"  weryfikacja_zadania.csv: {len(zadania)} pozycji")


if __name__ == "__main__":
    if "--miasta" in sys.argv:
        przed_zlaczeniem()
    else:
        main()
