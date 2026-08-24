# May Day Violence in Berlin · 1987–2026

A data visualisation of four decades of May 1st unrest in Berlin, analysed across two independent dimensions: absolute violence intensity (RDI) and social mobilisation (turnout).

**Live site:** https://paweldow1.github.io/Violence_Berlin_May1st_1990_2026

## Data

| Variable | Source | Coverage |
|---|---|---|
| Injured officers | Polizei Berlin press releases | 1987–2026 |
| Total arrests | Polizei Berlin press releases | 1987–2026 |
| Police deployment (Einsatz) | Polizei Berlin press releases | 1987–2026 (1995 imputed) |
| Demonstrator turnout | Organiser & police estimates | 1990–2026 |

Arrests are broken down by event type: **May 1st**, **Walpurgisnacht** (Apr 30 eve), and **NPD/counter-protests** — three streams with distinct political origins that should not be aggregated uncritically.

## Methodology

### Riot Disturbance Index (RDI)

```
RDI = 0.5 × injured_norm + 0.5 × arrests_norm
```

Both variables normalised min-max to [0, 1], then averaged with equal weights. Smoothed with a 3-year centred moving average (MA-3).

The index was tested against a variant incorporating police deployment as a correction factor (`injured/Einsatz` instead of raw injured count). The two versions correlate at r > 0.92 across all weight choices, confirming the index is robust to this methodological decision.

### Turnout

Used as interpretive backdrop, not as a normalisation denominator. Normalising arrests by turnout is methodologically problematic because turnout can be legally constrained (see 2001 anomaly below).

## Anomalies

| Year | Type | Note |
|---|---|---|
| 1987 | Small Einsatz | Only 400 officers deployed; injured/officer ratio is an extreme outlier from the tiny denominator |
| 1989 | Small Einsatz | 1,600 officers, 346 injured |
| 1995 | Missing data | Einsatz figure unavailable; imputed with series median (5,500) |
| 2001 | Endogeneity | Demonstration ban suppressed turnout (~7,750) while generating record arrests (616); ratio-based metrics misleading |
| 2005–2006 | Structural break | Turnout collapses to 500/50 — format reorganisation (emergence of Myfest) |
| 2009 | Violence peak | Absolute peak in injured officers (479)|
| 2020 | COVID-19 | Arrests (350) predominantly for violating containment regulations — a categorically different arrest type |

## Three structural periods

**1987–2004 · High, variable violence**
Classic Berlin model: high and volatile RDI, stable turnout of 10–15k. Kreuzberg SO36 as the primary flashpoint.

**2005–2010 · Turbulence & peak**
Turnout disrupted by format reorganisation then recovering. Violence reaches its absolute peak in 2009. Competing dynamics: Myfest pacification vs. continued autonomous confrontations.

**2011–2026 · The scissors effect**
Turnout grows to record highs. Violence falls to historic lows. Possible explanations: dilution of radical participants in larger crowds; institutionalisation of May Day as a festival.

