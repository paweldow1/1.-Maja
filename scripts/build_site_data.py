#!/usr/bin/env python3
"""Build data/site_data.json for the redesigned site from data/cells.json + index.html history.

Value per cell (provisional, until decisions are exported): the number currently on the
chart if there is one, otherwise the proposal from compare.py.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# Counter-demonstrations (anti-Nazi blockades) are radical-left mobilisation; folded in to keep
# the field to six camps.
CAMP_FOLD = {"counter": "radical_left"}


def js_array(text, name):
    body = re.search(rf"const {name} = \[(.*?)\];", text, re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    return [None if t.strip() == "null" else float(t) for t in body.split(",") if t.strip()]


def main():
    cells = json.loads((DATA / "cells.json").read_text(encoding="utf-8"))
    cities = {}
    for key, meta in cells["series"].items():
        city, series = key.split("__")
        cities.setdefault(city, {})[series] = {
            "key": series, "label": meta["label"],
            "camp": CAMP_FOLD.get(meta["camp"], meta["camp"]), "values": {}}
    for c in cells["cells"]:
        v = c["chart"] if c["chart"] is not None else c["proposal"]
        if v is not None:
            cities[c["city"]][c["series"]]["values"][str(c["year"])] = round(v)
    out = {"cities": {city: [s for s in ss.values() if s["values"]] for city, ss in cities.items()}}

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    east = js_array(html, "eastBerlin")
    west = js_array(html, "westRucht")
    warsaw_hist = js_array(html, "warsawHistoric")
    out["long"] = {
        "east_berlin": {str(1950 + i): v for i, v in enumerate(east) if v},
        "west_berlin": {str(1950 + i): v for i, v in enumerate(west) if v},
        "warsaw": {str(1945 + i): v for i, v in enumerate(warsaw_hist) if v},
    }
    (DATA / "site_data.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n = sum(len(s["values"]) for ss in out["cities"].values() for s in ss)
    print(f"data/site_data.json: {n} wartości, {sum(len(v) for v in out['long'].values())} lat historii")


if __name__ == "__main__":
    main()
