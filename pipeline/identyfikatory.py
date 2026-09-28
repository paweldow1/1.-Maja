"""Final, unique ids -- and an honest list of what still collides.

Two events can legitimately share a year, a city, a type and an actor: the
NPD held two rallies in 2015, in Marzahn and in Hohenschoenhausen. An `_a`
suffix hides that, so the id takes the distinguishing fact instead -- the
district first, then the geometry (a rally pinned to a point is not the
march drawn as a line) -- and falls back to a letter only when nothing
tells the two apart.

Whatever still needs a letter is either a real duplicate on the map or a
pair the data cannot separate, and that is exactly what duplikaty_id.csv
lists. It is rebuilt here, from the finished table: the parsers' own
duplicate lists are taken before decisions and before the ceremony split,
so they described collisions that no longer exist.

Runs last among the steps that touch wydarzenia.csv.

Usage: python3 identyfikatory.py
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

from common import slugify_actor, write_csv
from config.layers import WARSTWY_ID_Z_NAZWY

OUT_DIR = Path(__file__).parent / "output"

DUP_COLUMNS = ["id_bazowy", "id", "rok", "miasto", "warstwa", "typ", "aktor",
               "nazwa", "dzielnica", "punkt_start", "geom_typ",
               "identyczna_geometria", "rozroznienie", "klucz_zrodlowy"]


def baza_id(w):
    slug = slugify_actor(w["aktor"]) or "NIEZNANY"
    if w["warstwa"] in WARSTWY_ID_Z_NAZWY or w.get("ceremonia"):
        z_nazwy = slugify_actor(re.sub(r"(?:19|20)\d{2}", "", w["nazwa"] or ""))[:40]
        if z_nazwy:
            slug = f"{slug}-{z_nazwy}" if w["aktor"] else z_nazwy
    return f"{w['rok']}_{w['miasto']}_{w['typ']}_{slug}"


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wydarzenia = list(csv.DictReader(f))
    kolumny = list(wydarzenia[0].keys())
    if "rozroznienie" not in kolumny:
        kolumny.append("rozroznienie")

    grupy = defaultdict(list)
    for w in wydarzenia:
        grupy[baza_id(w)].append(w)

    duplikaty, na_litery = [], 0
    for baza, grupa in sorted(grupy.items()):
        if len(grupa) == 1:
            grupa[0]["id"] = baza
            grupa[0]["rozroznienie"] = ""
            continue

        # A ceremony already knows its own ordinal; it is not a collision.
        if all(w.get("ceremonia") for w in grupa):
            for w in grupa:
                w["id"] = f"{baza}-c{w['ceremonia']}"
                w["rozroznienie"] = "ceremonia"
            continue

        # Ordered by how much the fact explains: two rallies in different
        # boroughs are told apart by the borough; a march and a rally by
        # their geometry; everything else by whatever the object is called.
        for pole, etykieta, dlugosc in (("dzielnica_start", "dzielnica", 24),
                                        ("geom_typ", "geometria", 24),
                                        ("nazwa", "nazwa", 40)):
            wartosci = [(w.get(pole) or "").strip() for w in grupa]
            slugi = [slugify_actor(re.sub(r"(?:19|20)\d{2}", "", v))[:dlugosc].lower()
                     for v in wartosci]
            if all(slugi) and len(set(slugi)) == len(grupa):
                for w, slug in zip(grupa, slugi):
                    w["id"] = f"{baza}-{slug}"
                    w["rozroznienie"] = etykieta
                break
        else:
            # Nothing separates them. Keep the letters, but say so, and say
            # whether the geometry is identical -- that is the difference
            # between one object drawn twice and two events at one spot.
            ta_sama = len({w["punkt_start"] for w in grupa}) == 1
            for n, w in enumerate(grupa):
                w["id"] = baza if n == 0 else f"{baza}_{chr(ord('a') + n - 1)}"
                w["rozroznienie"] = ("nierozroznione, ta sama geometria" if ta_sama
                                     else "nierozroznione")
            na_litery += 1
            for w in grupa:
                duplikaty.append({
                    "id_bazowy": baza, "id": w["id"], "rok": w["rok"],
                    "miasto": w["miasto"], "warstwa": w["warstwa"], "typ": w["typ"],
                    "aktor": w["aktor"], "nazwa": (w["nazwa"] or "")[:80],
                    "dzielnica": w.get("dzielnica_start", ""),
                    "punkt_start": w["punkt_start"], "geom_typ": w["geom_typ"],
                    "identyczna_geometria": "TRUE" if ta_sama else "FALSE",
                    "rozroznienie": w["rozroznienie"],
                    "klucz_zrodlowy": w["klucz_zrodlowy"],
                })

    write_csv(OUT_DIR / "wydarzenia.csv", wydarzenia, kolumny)
    write_csv(OUT_DIR / "duplikaty_id.csv", duplikaty, DUP_COLUMNS)

    identyczne = len({d["id_bazowy"] for d in duplikaty
                      if d["identyczna_geometria"] == "TRUE"})
    ids = [w["id"] for w in wydarzenia]
    print(f"id: {len(set(ids))} unikalnych z {len(ids)} wierszy")
    rozr = defaultdict(int)
    for w in wydarzenia:
        if w["rozroznienie"]:
            rozr[w["rozroznienie"]] += 1
    for k, n in sorted(rozr.items()):
        print(f"  rozroznione przez {k}: {n}")
    print(f"duplikaty_id.csv: {na_litery} grup nie do rozroznienia "
          f"({identyczne} z identyczna geometria -- to pewnie ten sam obiekt)")


if __name__ == "__main__":
    main()
