#!/usr/bin/env python3
"""Collect every attendance observation from all sources into data/observations.csv.

Sources:
  maps/*.umap                              uMap backups (features with Lata + Frekwencja/Attendance)
  data/raw/FrekwencjaDGB17.xlsx            Berlin per-source observations (Dane_* sheets)
  data/raw/dgb_berlin_brandenburgia__lata.csv   DGB Berlin/Brandenburg yearly sheet
  index.html                               numbers currently shown on the chart (derived, not evidence)

Nothing is averaged or dropped here: one row per number found in a source.
Series assignment comes from data/series.csv (edit that file, not this script).
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
CITIES = ["berlin", "warsaw", "kyiv"]
YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d)\b")

# Features filed in a generic layer but belonging to a named series.
NAME_OVERRIDES = [
    ("berlin", re.compile(r"myfest", re.I), "myfest"),
    ("berlin", re.compile(r"mariannenplatz", re.I), "marian"),
]

FIELDS = ["city", "year", "series", "value", "source_type", "source", "source_category",
          "event_name", "note", "ref"]


def load_series():
    by_layer, by_sheet, by_index = {}, {}, {}
    with open(DATA / "series.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c, s = row["city"], row["series"]
            for layer in filter(None, row["map_layers"].split("|")):
                by_layer[(c, layer)] = s
            for sheet in filter(None, row["xlsx_sheets"].split("|")):
                by_sheet[(c, sheet)] = s
            for key in filter(None, row["index_keys"].split("|")):
                by_index[(c, key)] = s
    return by_layer, by_sheet, by_index


def to_number(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    digits = re.sub(r"[^\d]", "", str(v))
    return float(digits) if digits else None


# ── uMap ──────────────────────────────────────────────────────────────────────

def extract_maps(by_layer, unmapped):
    rows = []
    for city in CITIES:
        path = ROOT / "maps" / f"{city}.umap"
        umap = json.loads(path.read_text(encoding="utf-8"))

        def walk(layers, prefix=""):
            for layer in layers:
                name = layer["properties"].get("name") or ""
                full = prefix + name
                for i, feat in enumerate(layer.get("features", [])):
                    rows.extend(map_feature(city, full, i, feat["properties"], by_layer, unmapped))
                walk(layer.get("layers", []), full + " / ")

        walk(umap["layers"])
    return rows


def map_feature(city, layer, idx, props, by_layer, unmapped):
    raw = props.get("Frekwencja", props.get("Attendance"))
    if raw in (None, ""):
        return []
    name = str(props.get("name") or "").strip()
    series = by_layer.get((city, layer))
    for c, pattern, s in NAME_OVERRIDES:
        if c == city and pattern.search(name):
            series = s
    if series is None:
        unmapped.add((city, "map", layer))
        series = "?"
    years = [int(y) for y in YEAR_RE.findall(str(props.get("Lata") or ""))]
    if not years:
        years = [int(y) for y in YEAR_RE.findall(name)][:1]
    base = dict(city=city, series=series, source_type="mapa", source=f"mapa {city}",
                source_category="mapa", event_name=name, ref=f"{layer} #{idx}")

    # "2003: 20000\n2004: 30000" → one value per year
    per_year = re.findall(r"(\d{4})\s*:\s*([\d .]+)", str(raw))
    if per_year:
        return [dict(base, year=int(y), value=to_number(v), note="") for y, v in per_year]

    value = to_number(raw)
    if value is None or not years:
        return [dict(base, year=years[0] if years else "", value="", note=f"nieczytelne: {raw!r}")]
    note = f"jedna liczba dla lat {', '.join(map(str, years))}" if len(years) > 1 else ""
    return [dict(base, year=y, value=value, note=note) for y in years]


# ── Berlin xlsx ───────────────────────────────────────────────────────────────

def extract_xlsx(by_sheet, unmapped):
    path = RAW / "FrekwencjaDGB17.xlsx"
    if not path.exists():
        print(f"pomijam {path.name} (brak pliku)", file=sys.stderr)
        return []
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = []
    for ws in wb.worksheets:
        series = by_sheet.get(("berlin", ws.title))
        if series is None:
            if ws.title.startswith("Dane"):
                unmapped.add(("berlin", "xlsx", ws.title))
            continue
        for r, (year, value, source, category, *_) in enumerate(
                ws.iter_rows(min_row=2, max_col=4, values_only=True), start=2):
            if year is None or to_number(value) is None:
                continue
            rows.append(dict(city="berlin", year=int(year), series=series, value=to_number(value),
                             source_type="xlsx", source=str(source or "").strip(),
                             source_category=str(category or "").strip() or "?",
                             event_name="", note="", ref=f"{path.name}:{ws.title}!R{r}"))
    return rows


# ── DGB Berlin/Brandenburg sheet ──────────────────────────────────────────────

def extract_dgb_sheet():
    path = RAW / "dgb_berlin_brandenburgia__lata.csv"
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for col, cat in (("berlin", "arkusz DGB – główna"), ("berlin_alt", "arkusz DGB – alternatywna")):
                v = to_number(r[col])
                if v is not None:
                    rows.append(dict(city="berlin", year=int(r["rok"]), series="dgb", value=v,
                                     source_type="arkusz_dgb", source=r["zrodlo_berlin"],
                                     source_category=cat, event_name="", note=r["uwagi"],
                                     ref=f"{path.name}:{r['rok']}:{col}"))
    return rows


# ── index.html (current chart values) ─────────────────────────────────────────

def js_array(text, name):
    m = re.search(rf"\b{name}\s*[:=]\s*\[([^\]]*)\]", text)
    if not m:
        return None
    return [None if t.strip() in ("null", "") else float(t) for t in m.group(1).split(",")]


def extract_index_html(by_index):
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    years = [int(v) for v in js_array(text, "years")]
    sources = {"berlin": js_array(text, "berlin"), "warsaw": js_array(text, "warsaw")}
    rows = []
    blocks = {"berlin": "berlinSeries", "warsaw": "warsawSeries"}
    for city, block in blocks.items():
        body = re.search(rf"const {block} = \{{(.*?)\n\}};", text, re.S).group(1)
        for key in re.findall(r"^\s*(\w+)\s*:", body, re.M):
            arr = js_array(body, key)
            if arr is None:  # bound to the canonical array (dgb: berlin, opzz: warsaw)
                arr = sources[city]
            series = by_index.get((city, key))
            if series is None:
                continue
            for y, v in zip(years, arr):  # zip truncates over-long arrays (pds_a has 36 slots)
                if v is not None:
                    rows.append(dict(city=city, year=y, series=series, value=v, source_type="index_html",
                                     source="index.html", source_category="wykres (obecny)",
                                     event_name=key, note="", ref=f"index.html:{block}.{key}"))
    return rows


def main():
    by_layer, by_sheet, by_index = load_series()
    unmapped = set()
    rows = (extract_maps(by_layer, unmapped) + extract_xlsx(by_sheet, unmapped)
            + extract_dgb_sheet() + extract_index_html(by_index))
    rows.sort(key=lambda r: (r["city"], r["series"], str(r["year"]), r["source_type"]))
    out = DATA / "observations.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            r["value"] = "" if r["value"] in (None, "") else int(r["value"])
            w.writerow(r)
    print(f"{len(rows)} obserwacji → {out.relative_to(ROOT)}")
    for u in sorted(unmapped):
        print("  bez serii:", " | ".join(u), file=sys.stderr)


if __name__ == "__main__":
    main()
