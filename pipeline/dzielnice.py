"""Assign each event a district, from the map's own boundary layers.

Those layers are ignored as event sources (instrukcja_v2.md sec. 1) but they
are a usable spatial reference: Berlin's Stadteile carry OTEIL and BEZIRK,
Warsaw's Obszary MSI carry the neighbourhood name.

A route crosses districts, so a line records where it started, where it
ended and how many it passed through -- a demonstration that stays in one
district is a different thing from one that crosses the city.

Usage: python3 dzielnice.py
"""
import csv
import json
from pathlib import Path

from common import organizator_lokalny, write_csv

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
# The central districts. "Dzielnicowe" means held away from the centre --
# a neighbourhood event rather than the central one -- which is the
# distinction the roczniki already draw with Glowna demonstracja and
# Centralne_BB. Comparing start to end instead would call every point event
# local, since a rally in one spot trivially begins and ends in one place.
CENTRUM = {
    "PL": {"Śródmieście Północne", "Śródmieście Południowe",
           "Nowe Miasto", "Stare Miasto", "Mirów", "Muranów"},
    "DE": {"Mitte"},   # matched against BEZIRK, so Tiergarten and Wedding count too
}

WARSTWY = {
    "PL": (BASE / "input/warszawa/umap_backup_1-maja_warszawa9.umap",
           "Obszary MSI", ("name",)),
    "DE": (BASE / "input/berlin/umap_backup_1-mai-berlin_aktualna16.umap",
           "Stadteile", ("OTEIL", "BEZIRK")),
}


def wczytaj_obszary(sciezka, nazwa_warstwy, pola):
    """-> [(nazwa, nadrzedna, [pierscien, ...])] with bounding boxes."""
    dane = json.loads(Path(sciezka).read_text(encoding="utf-8"))
    obszary = []
    for warstwa in dane["layers"]:
        if warstwa.get("properties", {}).get("name") != nazwa_warstwy:
            continue
        for f in warstwa["features"]:
            props = f.get("properties", {})
            nazwa = props.get(pola[0]) or props.get("name") or ""
            nadrzedna = props.get(pola[1]) if len(pola) > 1 else ""
            geom = f.get("geometry", {})
            if geom.get("type") == "Polygon":
                pierscienie = [geom["coordinates"][0]]
            elif geom.get("type") == "MultiPolygon":
                pierscienie = [wielokat[0] for wielokat in geom["coordinates"]]
            else:
                continue
            for p in pierscienie:
                xs = [pt[0] for pt in p]
                ys = [pt[1] for pt in p]
                obszary.append((nazwa, nadrzedna or "", p,
                                (min(xs), min(ys), max(xs), max(ys))))
    return obszary


def w_wielokacie(x, y, pierscien):
    """Ray casting; the boundary case does not matter at this scale."""
    w_srodku = False
    n = len(pierscien)
    for i in range(n):
        x1, y1 = pierscien[i][0], pierscien[i][1]
        x2, y2 = pierscien[(i + 1) % n][0], pierscien[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            przeciecie = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < przeciecie:
                w_srodku = not w_srodku
    return w_srodku


def znajdz(x, y, obszary):
    for nazwa, nadrzedna, pierscien, (minx, miny, maxx, maxy) in obszary:
        if minx <= x <= maxx and miny <= y <= maxy and w_wielokacie(x, y, pierscien):
            return nazwa, nadrzedna
    return "", ""


def punkty_wiersza(w):
    """Start and end of the event, as (lon, lat). Stored as 'lat,lon'."""
    out = []
    for kolumna in ("punkt_start", "punkt_koniec"):
        surowy = (w.get(kolumna) or "").strip()
        if not surowy or "," not in surowy:
            continue
        lat, lon = surowy.split(",", 1)
        try:
            out.append((float(lon), float(lat)))
        except ValueError:
            continue
    return out


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wydarzenia = list(csv.DictReader(f))

    obszary = {m: wczytaj_obszary(*WARSTWY[m]) for m in WARSTWY}
    print("obszary odniesienia: " + ", ".join(
        f"{m} {len(obszary[m])}" for m in obszary))

    # District names a party name can sit against ("PDS Marzahn"), taken
    # from the same reference layers, so the list never drifts from them.
    nazwy_dzielnic = {m: {o[0] for o in obszary[m] if o[0]} | {o[1] for o in obszary[m] if o[1]}
                      for m in obszary}

    trafione = 0
    for w in wydarzenia:
        punkty = punkty_wiersza(w)
        siatka = obszary.get(w["miasto"], [])
        nazwy = [znajdz(x, y, siatka) for x, y in punkty]
        nazwy = [n for n in nazwy if n[0]]
        w["dzielnica_start"] = nazwy[0][0] if nazwy else ""
        w["dzielnica_koniec"] = nazwy[-1][0] if nazwy else ""
        w["bezirk_start"] = nazwy[0][1] if nazwy else ""
        if nazwy:
            trafione += 1
            # Berlin is judged on the borough, Warsaw on the MSI area itself.
            klucz = nazwy[0][1] if w["miasto"] == "DE" else nazwy[0][0]
            w["centralne"] = "TRUE" if klucz in CENTRUM[w["miasto"]] else "FALSE"
            # NOT the same thing as a "dzielnicowka": this only says the
            # event sits outside the central area. A district festival that
            # never made it onto a map is a different question entirely, and
            # lives in brakujace_na_mapie.csv.
            w["poza_centrum"] = "FALSE" if w["centralne"] == "TRUE" else "TRUE"
            w["przecina_dzielnice"] = "TRUE" if len({n[0] for n in nazwy}) > 1 else "FALSE"
        else:
            w["centralne"] = w["poza_centrum"] = w["przecina_dzielnice"] = ""

        # A dzielnicowka in Pawel's sense: non-central AND run by a local
        # branch. On the maps this is almost empty by design -- he put the
        # district events in the chronicles, not on the maps -- so an empty
        # column here is the expected answer, not a failure to detect.
        lokalny, dowod = organizator_lokalny(
            " ".join(filter(None, [w.get("nazwa"), w.get("opis"), w.get("aktor")])),
            nazwy_dzielnic.get(w["miasto"], set()))
        w["organizator_lokalny"] = dowod
        w["dzielnicowe"] = "TRUE" if (lokalny and w["poza_centrum"] == "TRUE") else (
            "FALSE" if w["poza_centrum"] else "")

    kolumny = list(wydarzenia[0].keys())
    write_csv(OUT_DIR / "wydarzenia.csv", wydarzenia, kolumny)

    for miasto in ("PL", "DE"):
        sel = [w for w in wydarzenia if w["miasto"] == miasto and w["dzielnica_start"]]
        licznik = {}
        for w in sel:
            licznik[w["dzielnica_start"]] = licznik.get(w["dzielnica_start"], 0) + 1
        top = sorted(licznik.items(), key=lambda kv: -kv[1])[:6]
        print(f"{miasto}: {len(sel)} wydarzen z dzielnica; najczestsze: "
              + ", ".join(f"{k} ({v})" for k, v in top))
    print(f"razem przypisanych: {trafione} z {len(wydarzenia)}")


if __name__ == "__main__":
    main()
