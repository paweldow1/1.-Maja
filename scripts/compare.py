#!/usr/bin/env python3
"""Group data/observations.csv into cells (city × series × year) and flag what needs a decision.

Writes data/cells.json (input for the decisions page) and prints a summary.

Proposal per cell: mean of the reports in the xlsx (press/organisers/police — the method
behind the current Berlin chart), else the DGB sheet's chosen value, else the largest map
feature for that year (map features are overlapping parts of one event: march, rally, ...).

Flags:
  rozjazd        the chart (index.html) shows a value >10% off the proposal
  tylko_wykres   the chart shows a value no source backs up
  poza_wykresem  sources have a number the chart does not show (Berlin/Warsaw only)
  tylko_mapa     the only evidence is a number on the map and the chart does not show it
                 (map numbers are often already the output of the averaging method)
  rozrzut        reports disagree by a factor of 2 or more
"""
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHART_CITIES = {"berlin", "warsaw"}


def main():
    series = {}
    with open(DATA / "series.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            series[(r["city"], r["series"])] = {"label": r["label"], "camp": r["camp"]}

    cells = defaultdict(list)
    with open(DATA / "observations.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["year"] and r["value"]:
                cells[(r["city"], r["series"], int(r["year"]))].append(r)

    out = []
    for (city, s, year), obs in sorted(cells.items()):
        evid = [o for o in obs if o["source_type"] != "index_html"]
        chart = [float(o["value"]) for o in obs if o["source_type"] == "index_html"]
        # Reports (press/organisers/police) are alternative estimates of one crowd → averaged.
        # Map features are parts of the event (march, rally, feeder march). The same people
        # walk the march and stand at the rally, so parts overlap: take the largest, not the sum.
        reports = [float(o["value"]) for o in evid if o["source_type"] == "xlsx"]
        sheet = [float(o["value"]) for o in evid if o["source_category"] == "arkusz DGB – główna"]
        parts = [float(o["value"]) for o in evid if o["source_type"] == "mapa"]
        if reports:
            proposal, basis = mean(reports), "średnia relacji (xlsx)"
        elif sheet:
            proposal, basis = sheet[0], "arkusz DGB"
        elif parts:
            proposal, basis = max(parts), "największy obiekt z mapy" if len(parts) > 1 else "mapa"
        else:
            proposal, basis = None, ""
        estimates = reports + [float(o["value"]) for o in evid if o["source_type"] == "arkusz_dgb"]
        flags = []
        if chart and proposal is None:
            flags.append("tylko_wykres")
        if proposal is not None and not chart and city in CHART_CITIES:
            flags.append("poza_wykresem")
        if chart and proposal is not None and abs(chart[0] - proposal) > 0.1 * max(proposal, 1):
            flags.append("rozjazd")
        if parts and not estimates and not chart:
            flags.append("tylko_mapa")
        if len(estimates) > 1 and min(estimates) > 0 and max(estimates) / min(estimates) >= 2:
            flags.append("rozrzut")
        out.append({
            "id": f"{city}__{s}__{year}",
            "city": city, "series": s, "year": year,
            "chart": chart[0] if chart else None,
            "proposal": round(proposal) if proposal is not None else None,
            "basis": basis,
            "min": min(estimates or parts) if (estimates or parts) else None,
            "max": max(estimates or parts) if (estimates or parts) else None,
            "flags": flags,
            "obs": [{k: o[k] for k in ("value", "source_type", "source", "source_category", "event_name", "note")}
                    for o in evid],
        })

    meta = {f"{c}__{s}": v for (c, s), v in series.items()}
    (DATA / "cells.json").write_text(
        json.dumps({"series": meta, "cells": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    counts = defaultdict(int)
    for c in out:
        for fl in c["flags"]:
            counts[(c["city"], fl)] += 1
    print(f"{len(out)} komórek → data/cells.json")
    for (city, fl), n in sorted(counts.items()):
        print(f"  {city:7} {fl:14} {n}")


if __name__ == "__main__":
    main()
