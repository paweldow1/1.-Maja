"""Step 1 (Berlin part): parse the 5 per-layer geojson exports (and,
optionally, the uMap backup for the remaining 5 layers) into
wydarzenia/miejsca CSVs.

Usage: python3 parse_berlin.py <input_dir> [path-to-umap-backup]

<input_dir> must contain the 5 files named per BERLIN_LAYER_FILES in
config/layers.py (the layer-name -> filename mapping is fixed by
filename, since these exports carry no layer field in properties).
"""
import json
import sys
from pathlib import Path

from common import (
    MIEJSCA_COLUMNS, WYDARZENIA_COLUMNS, build_event_rows, build_miejsce_rows,
    podziel_obiekty, write_csv, z_indeksami,
)
from config.layers import (
    BERLIN_LAYER_FILES, LAYERS_IGNORE, LAYERS_MIEJSCA, LAYER_META,
)

CITY = "berlin"
OUT_DIR = Path(__file__).parent / "output"


def main(input_dir, umap_path=None):
    input_dir = Path(input_dir)
    wydarzenia_rows = []
    miejsca_rows = []
    bez_lat_rows = []
    id_counters = {}

    # 1. The 5 per-layer geojson exports (mandatory, filename -> layer).
    for filename, layer_name in BERLIN_LAYER_FILES.items():
        path = input_dir / filename
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        features = data["features"]
        zdarzenia, stale = podziel_obiekty(features, CITY)
        miejsca_rows.extend(build_miejsce_rows(layer_name, stale, CITY, filename))
        wydarzenia_rows.extend(
            build_event_rows(layer_name, zdarzenia, CITY, filename, id_counters, bez_lat_rows)
        )
        print(f"{filename} -> warstwa {layer_name!r}: {len(features)} obiektow")

    # 2. Remaining layers live only in the backup (optional, if supplied).
    if umap_path:
        with open(umap_path, encoding="utf-8") as f:
            backup = json.load(f)
        plik = Path(umap_path).name
        for layer in backup["layers"]:
            name = layer.get("properties", {}).get("name", "")
            features = layer.get("features", [])
            if layer.get("properties", {}).get("group") or name in BERLIN_LAYER_FILES.values():
                continue  # header-only folder layers, or already parsed from geojson exports
            if name in LAYERS_IGNORE[CITY]:
                continue
            if name in LAYERS_MIEJSCA[CITY]:
                miejsca_rows.extend(build_miejsce_rows(name, z_indeksami(features), CITY, plik))
            elif name in LAYER_META[CITY]:
                zdarzenia, stale = podziel_obiekty(features, CITY)
                miejsca_rows.extend(build_miejsce_rows(name, stale, CITY, plik))
                wydarzenia_rows.extend(
                    build_event_rows(name, zdarzenia, CITY, plik, id_counters, bez_lat_rows)
                )
            else:
                print(f"UWAGA: nieznana warstwa bez konfiguracji: {name!r} ({len(features)} obiektow)")
    else:
        print("Brak backupu Berlina -- pomijam: Other events, Points of Interest, "
              "Euro May Day, DAG (1990-1997), MyGruni")

    write_csv(OUT_DIR / "wydarzenia_berlin.csv", wydarzenia_rows, WYDARZENIA_COLUMNS)
    write_csv(OUT_DIR / "miejsca_berlin.csv", miejsca_rows, MIEJSCA_COLUMNS)
    write_csv(
        OUT_DIR / "bez_lat_berlin.csv", bez_lat_rows,
        ["warstwa", "miasto", "nazwa", "id_geo", "plik_zrodlowy"],
    )


    print(f"wydarzenia: {len(wydarzenia_rows)} wierszy (oczekiwano ~458 z pelnym backupem)")
    print(f"miejsca: {len(miejsca_rows)} wierszy")
    print(f"bez_lat: {len(bez_lat_rows)} wierszy")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: python3 parse_berlin.py <input_dir> [path-to-umap-backup]")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
