"""Step 6: the POLE aggregate -- one row per year, PL and DE side by side.

Attendance is summed over distinct actor/event readings, never over event
rows: several map objects can share one headcount (three DGB objects in
1995 all carry the DGB 1995 figure), and summing rows would count it three
times.

Usage: python3 pole.py
"""
import csv
import html
import re
from pathlib import Path

from common import write_csv

OUT_DIR = Path(__file__).parent / "output"
MIASTA = ["PL", "DE"]
# Declared scope per city (instrukcja_v2.md sec. 0). The attendance
# spreadsheet runs to 2026, well past the maps, so without this the table
# grows years that have a headcount and no events to attach it to.
ZAKRES = {"PL": (1989, 2024), "DE": (1987, 2019)}
# Actors whose events count as union events. Taken from the map layers'
# `charakter`, plus the unions that appear only in the roczniki.
ZWIAZKI_DODATKOWE = {"DGB", "DGB Berlin-Brandenburg", "OPZZ", "IG Metall",
                     "ÖTV", "FDGB", "DAG", "Solidarność"}


def wczytaj(nazwa):
    with (OUT_DIR / nazwa).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalizuj_trase(tekst):
    if not tekst:
        return ""
    return re.sub(r"[^a-zà-ż]+", " ", tekst.lower()).strip()


def main():
    wydarzenia = wczytaj("wydarzenia.csv")
    frekwencja = wczytaj("frekwencja_agg.csv")
    roczniki = wczytaj("roczniki_wydarzenia.csv")

    zwiazkowi = set(ZWIAZKI_DODATKOWE)
    for w in wydarzenia:
        if w["charakter"] == "zwiazkowe" and w["aktor"]:
            zwiazkowi.add(w["aktor"])

    lata = sorted({int(w["rok"]) for w in wydarzenia} |
                  {int(r["rok"]) for r in roczniki})

    # actors per year/city, for the new/vanishing comparison
    aktorzy = {}
    for w in wydarzenia:
        if w["aktor"]:
            aktorzy.setdefault((int(w["rok"]), w["miasto"]), set()).add(w["aktor"])

    # main route per year/city, from the union's rocznik entry
    trasy = {}
    for r in roczniki:
        if r["trasa"] and r["aktor"] in zwiazkowi:
            trasy.setdefault((int(r["rok"]), r["miasto"]), r["trasa"])

    wiersze = []
    for rok in lata:
        wiersz = {"rok": rok}
        for miasto in MIASTA:
            p = miasto.lower()
            od, do = ZAKRES[miasto]
            if not (od <= rok <= do):
                # Outside this city's scope: blank, so an empty cell reads as
                # "not covered" rather than as a measured zero.
                for k in ("liczba_wydarzen", "liczba_zwiazkowych", "frekwencja_suma",
                          "frekwencja_zwiazkowa", "udzial_zwiazkowy", "liczba_aktorow",
                          "aktorzy_nowi", "aktorzy_znikajacy",
                          "trasa_glowna_zmieniona", "notatka"):
                    wiersz[f"{p}_{k}"] = ""
                continue
            zdarzenia = [w for w in wydarzenia
                         if int(w["rok"]) == rok and w["miasto"] == miasto]
            grupy = [f for f in frekwencja
                     if int(f["rok"]) == rok and f["miasto"] == miasto]
            suma = sum(int(f["frekwencja_sr"]) for f in grupy if f["frekwencja_sr"])
            suma_zw = sum(int(f["frekwencja_sr"]) for f in grupy
                          if f["frekwencja_sr"] and f["aktor"] in zwiazkowi)
            teraz = aktorzy.get((rok, miasto), set())
            wczoraj = aktorzy.get((rok - 1, miasto), set())
            trasa = normalizuj_trase(trasy.get((rok, miasto), ""))
            trasa_rok_wczesniej = normalizuj_trase(trasy.get((rok - 1, miasto), ""))
            if not trasa or not trasa_rok_wczesniej:
                zmiana = ""
            else:
                zmiana = "TRUE" if trasa != trasa_rok_wczesniej else "FALSE"

            wiersz.update({
                f"{p}_liczba_wydarzen": len(zdarzenia),
                f"{p}_liczba_zwiazkowych": sum(1 for w in zdarzenia
                                               if w["charakter"] == "zwiazkowe"),
                f"{p}_frekwencja_suma": suma or "",
                f"{p}_frekwencja_zwiazkowa": suma_zw or "",
                f"{p}_udzial_zwiazkowy": round(suma_zw / suma, 3) if suma else "",
                f"{p}_liczba_aktorow": len(teraz),
                f"{p}_aktorzy_nowi": ";".join(sorted(teraz - wczoraj)) if wczoraj else "",
                f"{p}_aktorzy_znikajacy": ";".join(sorted(wczoraj - teraz)) if wczoraj else "",
                f"{p}_trasa_glowna_zmieniona": zmiana,
                f"{p}_notatka": f"obsidian://open?vault=Wszystko&file={rok}_{miasto}",
            })
        if any(wiersz[f"{m.lower()}_liczba_wydarzen"] != "" for m in MIASTA):
            wiersze.append(wiersz)

    kolumny = ["rok"]
    for miasto in MIASTA:
        p = miasto.lower()
        kolumny += [f"{p}_liczba_wydarzen", f"{p}_liczba_zwiazkowych",
                    f"{p}_frekwencja_suma", f"{p}_frekwencja_zwiazkowa",
                    f"{p}_udzial_zwiazkowy", f"{p}_liczba_aktorow",
                    f"{p}_aktorzy_nowi", f"{p}_aktorzy_znikajacy",
                    f"{p}_trasa_glowna_zmieniona", f"{p}_notatka"]
    write_csv(OUT_DIR / "pole.csv", wiersze, kolumny)
    zapisz_html(wiersze, OUT_DIR / "pole.html")
    poza = [w for w in wydarzenia
            if not (ZAKRES[w["miasto"]][0] <= int(w["rok"]) <= ZAKRES[w["miasto"]][1])]
    print(f"pole.csv:  {len(wiersze)} lat ({wiersze[0]['rok']}-{wiersze[-1]['rok']})")
    if poza:
        lata_poza = sorted({w["rok"] for w in poza})
        print(f"  poza zakresem, nie liczone: {len(poza)} wydarzen ({', '.join(lata_poza)})")
    print(f"pole.html: {(OUT_DIR / 'pole.html').stat().st_size // 1024} KB")


def zapisz_html(wiersze, sciezka):
    naglowki = ["wydarzenia", "zwiazkowe", "frekwencja", "fr. zwiazkowa",
                "udzial", "aktorzy", "nowi", "znikajacy", "trasa inna"]
    kol = ["liczba_wydarzen", "liczba_zwiazkowych", "frekwencja_suma",
           "frekwencja_zwiazkowa", "udzial_zwiazkowy", "liczba_aktorow",
           "aktorzy_nowi", "aktorzy_znikajacy", "trasa_glowna_zmieniona"]
    czesci = ["""<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">
<title>POLE</title><style>
body{font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#1a1714;background:#faf8f5}
h1{font-size:18px;margin:0 0 4px}p.sub{color:#6b6459;margin:0 0 18px;font-size:12px}
table{border-collapse:collapse;font-size:12px}
th,td{border:1px solid #d8d2c8;padding:3px 7px;text-align:right;white-space:nowrap}
th{background:#ede9e2;font-weight:600}
td.akt{text-align:left;max-width:190px;overflow:hidden;text-overflow:ellipsis;font-size:11px;color:#5a534a}
td.rok{text-align:left;font-weight:600;background:#f3f0eb}
.pl{background:#eef4f9}.de{background:#fceeec}
tr:hover td{background:#fff8e6}
</style></head><body><h1>POLE &mdash; przekr&oacute;j rok &times; miasto</h1>
<p class="sub">Frekwencja sumowana po odczytach aktor/wydarzenie, nie po wierszach wydarze&#324;.
Puste kom&oacute;rki = rok poza zakresem danych dla tego miasta.</p>
<table><thead><tr><th rowspan="2">rok</th>"""]
    czesci.append(f'<th class="pl" colspan="{len(kol)}">Warszawa</th>')
    czesci.append(f'<th class="de" colspan="{len(kol)}">Berlin</th></tr><tr>')
    for miasto in MIASTA:
        klasa = "pl" if miasto == "PL" else "de"
        for h in naglowki:
            czesci.append(f'<th class="{klasa}">{html.escape(h)}</th>')
    czesci.append("</tr></thead><tbody>")
    for w in wiersze:
        link = w["pl_notatka"]
        czesci.append(f'<tr><td class="rok"><a href="{html.escape(link)}">{w["rok"]}</a></td>')
        for miasto in MIASTA:
            p = miasto.lower()
            for k in kol:
                v = w[f"{p}_{k}"]
                klasa = "akt" if "aktorzy" in k else ""
                czesci.append(f'<td class="{klasa}">{html.escape(str(v))}</td>')
        czesci.append("</tr>")
    czesci.append("</tbody></table></body></html>")
    sciezka.write_text("".join(czesci), encoding="utf-8")


if __name__ == "__main__":
    main()
