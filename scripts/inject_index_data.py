#!/usr/bin/env python3
"""Write data/ and berlin-violence/ data into index.html's generated blocks.

1. extra-series: the series that index.html does not hard-code yet.

Takes every series from data/series.csv that has no index.html key (Berlin/Warsaw extras
from the uMap backups, all of Kyiv), with yearly values from data/cells.json, and replaces
the block between `// <generated:extra-series>` and `// </generated:extra-series>`.
These values are preliminary (mostly the largest map feature per year), so the page marks
them ◦ and, for Berlin and Warsaw, leaves them unchecked by default.

2. violence: berlin-violence/data.csv (police figures) for the Violence (Berlin) tab.
3. map-events: every feature of an event layer in maps/*.umap (name, years, slogan,
   attendance, description, centre point, and per year the time/day/type/place parsed by
   scripts/scenario.py) for the Scenario tab, with a link back to uMap.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YEARS = range(1990, 2020)

# English labels for the page (series.csv labels are Polish working names).
LABELS = {
    "berlin": {"dgb": "DGB Berlin", "revo_j": "Revo joint (1987–95)", "revo18": "Revolutionäre 18",
               "revo13": "Revolutionäre 13", "pds": "PDS/Linke (East)", "euro": "EuroMayDay",
               "antinazi": "Antinazi blockades", "nazi": "Nazi demo", "myfest": "MyFest Kreuzberg",
               "marian": "Mariannenplatzfest","dgb_maifest": "DGB Maifest", "dgb_korso": "DGB Korso / run", "dag": "DAG",
               "revo_spont": "Spontaneous demos", "revo_inne": "Revolutionäre (other)",
               "bkg": "Kritische Gewerkschafter", "ost_radical": "East Berlin radical left",
               "mygruni": "MyGruni", "walpurgis_demo": "Walpurgisnacht demo",
               "walpurgis_ttbn": "Take back the night", "walpurgis_tanz": "Tanz in den Mai",
               "inne": "Other events"},
    "warsaw": {"opzz": "OPZZ", "pps": "PPS", "lew_alt": "Left alt.", "anarchi": "Anarchists",
               "prawica_mayday": "Right/Nationalists", "parada": "Equality Parade",
               "fest_eu": "European Festival", "solidarnosc": "Solidarność", "prawica_kontra": "Right counter-protests",
               "festyny": "Festivals (other)", "inne": "Other events"},
    "kyiv": {"kpu": "Communist Party (KPU)", "pspu": "PSPU", "spu": "Socialist Party (SPU)",
             "rukh": "Narodnyi Rukh", "sotsrukh": "Sotsialnyi Rukh", "monstracja": "Monstratsiya",
             "anarchi": "Anarchists", "nacjonal": "Nationalists", "fpu": "FPU (trade unions)",
             "zwiazki_inne": "Other trade unions", "inne": "Other events"},
}
# Page groups per city (must match each city's groupColors in index.html).
GROUP = {
    "berlin": {"union": "union", "fest": "fest"},                       # everything else → alt
    "warsaw": {"union": "union", "radical_left": "left", "left_party": "left",
               "right": "right", "fest": "fest", "counter": "left"},     # else → other
    "kyiv": {"union": "union", "radical_left": "left", "left_party": "left",
             "right": "right", "fest": "other"},                         # else → other
}
DEFAULT_GROUP = {"berlin": "alt", "warsaw": "other", "kyiv": "other"}
# Muted swatches per page group, used in order for each new series.
SWATCH = {
    "union": ["#b5483a", "#d17a5c", "#8a3a2e", "#e09a7a"],
    "alt":   ["#6d5a8f", "#a07cb8", "#4f6f7f", "#7f9a6a", "#b08a5a", "#5f5f78", "#9a6a7a", "#6a8a9a"],
    "left":  ["#4a4a4a", "#7a7a7a", "#2f2f2f", "#5f6f7f", "#8a6a5a"],
    "right": ["#8b5e3c", "#b08060", "#6b4a30"],
    "fest":  ["#3d8a5a", "#5aaa7a", "#2f6f8a"],
    "other": ["#9a6aa0", "#7a8aa0", "#a08a5a"],
}


# Kyiv's left camp has five parties side by side: mid-tone hues that read on light and dark.
SWATCH_CITY = {("kyiv", "left"): ["#b03a3a", "#d0743c", "#7a5aa0", "#3f8a9a", "#a08a3a"],
               ("kyiv", "union"): ["#3a6fb0", "#6a9ad0"]}


def rgba(hex_, a):
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def replace_block(html, name, payload):
    block = (f"// <generated:{name}> written by scripts/inject_index_data.py from data/; do not edit by hand\n"
             f"{payload}\n// </generated:{name}>")
    pattern = re.compile(rf"// <generated:{name}>.*?// </generated:{name}>", re.S)
    if not pattern.search(html):
        raise SystemExit(f"index.html has no <generated:{name}> block")
    return pattern.sub(lambda _: block, html)


def violence_payload():
    cols = {}
    with open(ROOT / "berlin-violence" / "data.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k, v in r.items():
                cols.setdefault(k, []).append(int(v) if v.strip() else None)
    return f"const VIOLENCE = {json.dumps(cols, separators=(',', ':'))};"


def centre(geom):
    """Rough centre of a GeoJSON geometry: mean of its vertices (good enough to aim a map link)."""
    pts = []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    if not pts:
        return None
    return round(sum(p[1] for p in pts) / len(pts), 5), round(sum(p[0] for p in pts) / len(pts), 5)


def map_events_payload():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from extract import load_series, NAME_OVERRIDES, YEAR_RE  # same layer → series mapping as the pipeline
    from scenario import scenario_fields
    by_layer, _, _ = load_series()
    labels = {}
    with open(ROOT / "data" / "series.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            labels.setdefault(r["city"], {})[r["series"]] = [LABELS[r["city"]].get(r["series"], r["label"]), r["camp"]]
    out = {}
    for city in ("berlin", "warsaw", "kyiv"):
        umap = json.loads((ROOT / "maps" / f"{city}.umap").read_text(encoding="utf-8"))
        rows = []

        def walk(layers, prefix=""):
            for layer in layers:
                full = prefix + (layer["properties"].get("name") or "")
                for feat in layer.get("features", []):
                    p = feat["properties"]
                    name = str(p.get("name") or "").strip()
                    series = by_layer.get((city, full))
                    for c, pat, s_ in NAME_OVERRIDES:
                        if c == city and pat.search(name):
                            series = s_
                    if series is None:
                        continue  # reference layers: districts, Berlin Wall, MSI areas, monuments
                    years = sorted({int(y) for y in YEAR_RE.findall(str(p.get("Lata") or ""))}
                                   or {int(y) for y in YEAR_RE.findall(name)[:1]})
                    if not years:
                        continue
                    desc = re.sub(r"\s+", " ", str(p.get("description") or "")).strip()
                    c = centre(feat["geometry"]) if feat.get("geometry") else None
                    geom = {"Point": "point", "LineString": "route", "MultiLineString": "route"}.get(
                        feat["geometry"]["type"], "area") if feat.get("geometry") else ""
                    att = str(p.get("Frekwencja", p.get("Attendance")) or "").strip()
                    rows.append({"s": series, "y": years, "n": name, "a": att[:80],
                                 "h": str(p.get("Hasło") or "").strip(),
                                 "d": desc[:320] + ("…" if len(desc) > 320 else ""),
                                 "g": geom, "c": c,
                                 **scenario_fields(city, series, name, desc, geom, years, att)})
                walk(layer.get("layers", []), full + " / ")
        walk(umap["layers"])
        out[city] = {"uri": umap.get("uri", "").replace("http://", "https://"), "labels": labels[city], "events": rows}
    return f"const MAP_EVENTS = {json.dumps(out, ensure_ascii=False, separators=(',', ':'))};"


def main():
    cells = json.loads((ROOT / "data" / "cells.json").read_text(encoding="utf-8"))
    values = {}
    for c in cells["cells"]:
        v = c["chart"] if c["chart"] is not None else c["proposal"]
        values[(c["city"], c["series"], c["year"])] = v

    extra = {}
    used = {}
    with open(ROOT / "data" / "series.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            city, key = row["city"], row["series"]
            if row["index_keys"]:
                continue  # already hand-coded in index.html
            arr = [values.get((city, key, y)) for y in YEARS]
            if not any(v for v in arr):
                continue
            group = GROUP[city].get(row["camp"], DEFAULT_GROUP[city])
            n = used.setdefault((city, group), 0)
            used[(city, group)] = n + 1
            palette = SWATCH_CITY.get((city, group), SWATCH[group])
            sw = palette[n % len(palette)]
            entry = extra.setdefault(city, {"meta": [], "series": {}})
            entry["meta"].append({"key": key, "label": LABELS[city].get(key, row["label"]), "group": group,
                                  "stub": False, "prelim": True, "off": city != "kyiv",
                                  "color": rgba(sw, 0.75), "border": sw})
            entry["series"][key] = [None if v is None else round(v) for v in arr]

    path = ROOT / "index.html"
    html = path.read_text(encoding="utf-8")
    html = replace_block(html, "extra-series",
                         f"const EXTRA = {json.dumps(extra, ensure_ascii=False, separators=(',', ':'))};")
    html = replace_block(html, "violence", violence_payload())
    html = replace_block(html, "map-events", map_events_payload())
    path.write_text(html, encoding="utf-8")
    for city, e in extra.items():
        print(f"{city}: {len(e['meta'])} serii → index.html")
    print("violence: berlin-violence/data.csv → index.html")
    print("map-events: maps/*.umap → index.html")


if __name__ == "__main__":
    main()
