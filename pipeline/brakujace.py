"""District events that exist in the chronicles but never made it onto a map.

The scenario file mixes two kinds of row: events already mapped, whose
description happens to carry a time, and events that survive only as a line
of text. Only the second kind is a gap in the map.

A corpus entry counts as already mapped when some map event that year shares
its district and either its actor or a distinctive word from its text. What
is left is a candidate to add.

Usage: python3 brakujace.py
"""
import csv
import re
from pathlib import Path

from common import write_csv

OUT_DIR = Path(__file__).parent / "output"
# Words too common to tie an entry to a particular event.
POSPOLITE = {
    "mai", "maifest", "fest", "demo", "demonstration", "kundgebung", "uhr",
    "berlin", "platz", "strasse", "straße", "stadt", "gegen", "und", "der",
    "die", "das", "des", "den", "dem", "ein", "eine", "für", "mit", "von",
    "vom", "beim", "zum", "zur", "auf", "aus", "ab", "bis", "wird", "werden",
    "findet", "statt", "sich", "nach", "wie", "auch", "nicht", "sind", "ist",
    "przez", "oraz", "pod", "przy", "jest", "sie", "les", "the", "and", "for",
}


def wczytaj(nazwa):
    with (OUT_DIR / nazwa).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def slowa(tekst):
    return {w for w in re.findall(r"[\wÀ-ɏ-]{5,}", (tekst or "").lower())
            if w not in POSPOLITE and not w.isdigit()}


def main():
    scenariusz = wczytaj("scenariusz.csv")
    wydarzenia = wczytaj("wydarzenia.csv")

    mapa = {}
    for w in wydarzenia:
        mapa.setdefault((w["rok"], w["miasto"]), []).append(w)

    kandydaci = []
    for s in scenariusz:
        # Rows sourced from the map are by definition already on it.
        if s["zrodlo"] != "korpus" or not s["dzielnica"]:
            continue
        tekst_slowa = slowa(s["tekst"])
        aktorzy = {a.strip() for a in (s["aktor"] or "").split(";") if a.strip()}
        dopasowanie = None
        for w in mapa.get((s["rok"], s["miasto"]), []):
            ta_sama_dzielnica = (
                w["dzielnica_start"] == s["dzielnica"]
                or s["dzielnica"] in (w["dzielnice_wszystkie"] if "dzielnice_wszystkie" in w else "")
            )
            if not ta_sama_dzielnica:
                continue
            if aktorzy and w["aktor"] in aktorzy:
                dopasowanie = w
                break
            wspolne = tekst_slowa & slowa((w["nazwa"] or "") + " " + (w["opis"] or ""))
            if wspolne:
                dopasowanie = w
                break
        if dopasowanie is None:
            kandydaci.append({
                "rok": s["rok"],
                "miasto": s["miasto"],
                "godzina_od": s["godzina_od"],
                "godzina_do": s["godzina_do"],
                "dzielnica": s["dzielnica"],
                "aktor": s["aktor"],
                "sekcja": s["sekcja"],
                "tekst": s["tekst"],
                "odniesienie": s["odniesienie"],
            })

    # The same event is often written up twice in one year's notes. Group
    # rather than drop: two things can genuinely share an hour and a district.
    kandydaci.sort(key=lambda k: (k["miasto"], int(k["rok"]), k["godzina_od"]))
    grupy = {}
    for k in kandydaci:
        klucz = (k["rok"], k["miasto"], k["dzielnica"], k["godzina_od"])
        rodzenstwo = grupy.setdefault(klucz, [])
        moje = slowa(k["tekst"])
        numer = None
        for idx, (slowa_grupy, _) in enumerate(rodzenstwo):
            if len(moje & slowa_grupy) >= 2:
                numer = idx
                break
        if numer is None:
            rodzenstwo.append((moje, len(rodzenstwo)))
            numer = len(rodzenstwo) - 1
        k["grupa"] = f"{k['rok']}-{k['dzielnica']}-{k['godzina_od']}-{numer}"
    licznik = {}
    for k in kandydaci:
        licznik[k["grupa"]] = licznik.get(k["grupa"], 0) + 1
    for k in kandydaci:
        k["mozliwy_duplikat"] = "TRUE" if licznik[k["grupa"]] > 1 else "FALSE"
    write_csv(OUT_DIR / "brakujace_na_mapie.csv", kandydaci, [
        "rok", "miasto", "godzina_od", "godzina_do", "dzielnica", "aktor",
        "sekcja", "tekst", "grupa", "mozliwy_duplikat", "odniesienie"])

    for miasto in ("DE", "PL"):
        sel = [k for k in kandydaci if k["miasto"] == miasto]
        if not sel:
            continue
        lata = sorted({k["rok"] for k in sel})
        dzielnice = sorted({k["dzielnica"] for k in sel})
        print(f"{miasto}: {len(sel)} wydarzen bez odpowiednika na mapie, "
              f"{len(lata)} lat, {len(dzielnice)} dzielnic")
        unikalne = len({k["grupa"] for k in sel})
        print(f"    po scaleniu duplikatow: {unikalne} odrebnych wydarzen")
        print(f"    dzielnice: {', '.join(dzielnice[:14])}"
              + (" ..." if len(dzielnice) > 14 else ""))


if __name__ == "__main__":
    main()
