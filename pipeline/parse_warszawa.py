"""Step 1 (Warszawa part): parse the uMap backup into wydarzenia/miejsca CSVs.

Usage: python3 parse_warszawa.py <path-to-umap-backup>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from common import (
    MIEJSCA_COLUMNS, WYDARZENIA_COLUMNS, build_event_rows, build_miejsce_rows,
    podziel_obiekty, write_csv, z_indeksami,
)
from config.layers import (
    FROM_NAME, LAYERS_IGNORE, LAYERS_MIEJSCA, LAYER_META, WARSTWY_UPAMIETNIENIA,
)

CITY = "warszawa"
OUT_DIR = Path(__file__).parent / "output"


def main(umap_path):
    with open(umap_path, encoding="utf-8") as f:
        data = json.load(f)

    plik = Path(umap_path).name
    wydarzenia_rows = []
    miejsca_rows = []
    bez_lat_rows = []
    id_counters = {}
    seen_layers = set()

    for layer in data["layers"]:
        name = layer.get("properties", {}).get("name", "")
        features = layer.get("features", [])
        seen_layers.add(name)

        if name in LAYERS_IGNORE[CITY]:
            continue
        if name in LAYERS_MIEJSCA[CITY]:
            miejsca_rows.extend(build_miejsce_rows(name, z_indeksami(features), CITY, plik))
            if name in WARSTWY_UPAMIETNIENIA:
                # The place is one row; the wreath-laying there is an event
                # per year of use.
                wydarzenia_rows.extend(build_event_rows(
                    name, z_indeksami(features), CITY, plik, id_counters, bez_lat_rows,
                    typ_wymuszony="upamiętnienie",
                    meta=("upamiętnienie", FROM_NAME, "niezwiazkowe")))
        elif name in LAYER_META[CITY]:
            zdarzenia, stale = podziel_obiekty(features, CITY)
            miejsca_rows.extend(build_miejsce_rows(name, stale, CITY, plik))
            wydarzenia_rows.extend(
                build_event_rows(name, zdarzenia, CITY, plik, id_counters, bez_lat_rows)
            )
        else:
            print(f"UWAGA: nieznana warstwa bez konfiguracji: {name!r} ({len(features)} obiektow)")

    write_csv(OUT_DIR / "wydarzenia_warszawa.csv", wydarzenia_rows, WYDARZENIA_COLUMNS)
    write_csv(OUT_DIR / "miejsca_warszawa.csv", miejsca_rows, MIEJSCA_COLUMNS)
    write_csv(
        OUT_DIR / "bez_lat_warszawa.csv", bez_lat_rows,
        ["warstwa", "miasto", "nazwa", "id_geo", "plik_zrodlowy"],
    )


    print(f"Warstwy w pliku: {len(seen_layers)}")
    print(f"wydarzenia: {len(wydarzenia_rows)} wierszy (oczekiwano ~228)")
    print(f"miejsca: {len(miejsca_rows)} wierszy")
    print(f"bez_lat: {len(bez_lat_rows)} wierszy")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 parse_warszawa.py <path-to-umap-backup>")
        sys.exit(1)
    main(sys.argv[1])
