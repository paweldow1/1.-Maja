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
├── data/                     # raw sources, observations, series map (see pipeline below)
├── scripts/                  # extract → compare → build decisions page
├── tools/                    # decisions page template
├── berlin-violence/
│   ├── index.html             # Berlin RDI (violence) dashboard
│   ├── data.csv                # canonical yearly data: einsatz, injured, arrests, turnout
│   └── README.md               # methodology, anomalies, structural periods
└── maps/
    ├── warsaw.umap             # uMap backup: Warsaw routes/events by faction (OPZZ, PPS, anarchist, right-wing, ...)
    ├── berlin.umap              # uMap backup: Berlin routes/events (DGB, Revolutionäre 1. Mai, MyFest, ...)
    └── kyiv.umap                # uMap backup: Kyiv routes/events
```

## Attendance data pipeline

There is no single source of truth yet; the pipeline collects every number from every
source, flags conflicts, and records the decisions taken on them.

```
data/raw/FrekwencjaDGB17.xlsx            Berlin: one row per report (press / organisers / police)
data/raw/dgb_berlin_brandenburgia__lata.csv   DGB Berlin/Brandenburg sheet (Google Drive snapshot)
maps/*.umap                              per-feature numbers (Lata + Frekwencja/Attendance)
index.html                               numbers currently on the chart
        │  scripts/extract.py   (series assignment: data/series.csv)
        ▼
data/observations.csv                    one row per number found, nothing averaged
        │  scripts/compare.py
        ▼
data/cells.json                          city × series × year: proposal + flags
        │  scripts/build_decisions_page.py
        ▼
tools/decyzje.html                       decisions page (published as a claude.ai artifact)
```

- **Proposal per cell**: mean of the xlsx reports (this reproduces the current Berlin
  chart exactly), else the DGB sheet value, else the largest map feature. Map features are
  overlapping parts of one event (march, rally, feeder march), so they are not summed.
- **Flags**: chart differs from sources (`rozjazd`), sources disagree ≥2× (`rozrzut`),
  number only on the map (`tylko_mapa`), number missing from the chart (`poza_wykresem`),
  chart number with no source (`tylko_wykres`).
- **Decisions** are stored in the decisions artifact's database (per-series rule + per-cell
  overrides: exact value, range, order of magnitude, "happened, attendance unknown",
  excluded, and which segment the number refers to). Next step: export them to
  `data/decisions.json` and generate the chart data from observations + decisions.

To rebuild: `pip install -r requirements.txt`, then run the three scripts in order.

The working copy of the attendance spreadsheet lives in Google Drive as
`1maja_frekwencje_MASTER` (created so the Drive connector can read it).
