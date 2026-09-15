# 1. Maja

Data visualisations of May Day (1 May) demonstrations in Berlin, Warsaw and Kyiv: attendance,
routes/events, and (for Berlin) a riot/violence index.

## Pages

- **[index.html](index.html)** — Attendance comparison, Berlin (DGB) vs Warsaw (OPZZ), 1990–2019,
  with historical context back to 1950 (weather, holidays, correlation, trend analysis).
- **[berlin-violence/index.html](berlin-violence/index.html)** — Berlin May Day violence, 1987–2026:
  Riot Disturbance Index (RDI), arrests, injured officers, turnout. Imported from the standalone
  [`Violence_Berlin_May1st_1990_2026`](https://github.com/paweldow1/violence_berlin_may1st_1990_2026)
  repo; see [berlin-violence/README.md](berlin-violence/README.md) for methodology.

## Structure

```
.
├── index.html                # Berlin vs Warsaw attendance dashboard
├── berlin-violence/
│   ├── index.html             # Berlin RDI (violence) dashboard
│   ├── data.csv                # canonical yearly data: einsatz, injured, arrests, turnout
│   └── README.md               # methodology, anomalies, structural periods
└── maps/
    ├── warsaw.umap             # uMap backup: Warsaw routes/events by faction (OPZZ, PPS, anarchist, right-wing, ...)
    ├── berlin.umap              # uMap backup: Berlin routes/events (DGB, Revolutionäre 1. Mai, MyFest, ...)
    └── kyiv.umap                # uMap backup: Kyiv routes/events
```

## Data sources & known duplication

The `maps/*.umap` files carry per-event data (`Lata` = year, `Frekwencja`/`Attendance`, and often
`Hasło` = slogan) on individual features. The yearly totals shown in `index.html` are currently
**hand-copied** from those maps into hardcoded JS arrays (`warsaw`, `berlin`, `warsawSeries`, ...).
This is a known source of drift: editing a map does not update the chart, and vice versa.

Planned fix (not yet implemented): extract a canonical `data/*.csv` per city, generated from the
`.umap` files by a script, and have `index.html` load it instead of hardcoding it — see project
discussion for the proposed `scripts/umap_to_data.py` approach.
