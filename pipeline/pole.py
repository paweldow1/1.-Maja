"""Step 6: the POLE aggregate -- one row per year.

Writes a table per city (pole_warszawa.csv, pole_berlin.csv), because the
two do not have the same columns: only Berlin has the police series, and
each city has its own event series. pole.csv is the two of them prefixed
and joined on the year, for the side-by-side view.

Attendance is read from the averaged series, not recomputed: the figures
the analysis quotes were averaged from the spreadsheet once, in the repo's
chart page, and parse_srednie.py lifts them into a table.

Usage: python3 pole.py
"""
import csv
import html
import re
from collections import defaultdict
from pathlib import Path

from common import write_csv
from config.layers import WARSTWY_PRAWICOWE, WARSTWY_REWOLUCYJNE

# The Violence_Berlin data splits arrests three ways -- May 1st,
# Walpurgisnacht, NPD and counter-protests -- because the three have
# different political origins and should not be added up uncritically.
# Attendance is split the same way here so the two can be read side by side.
STRUMIEN_AKTOR = {"NPD": "npd_kontra", "Antifa": "npd_kontra"}


def strumien(warstwa, charakter):
    if warstwa == "Walpurgisnacht":
        return "walpurgis"
    if warstwa in WARSTWY_PRAWICOWE or charakter == "kontra":
        return "npd_kontra"
    return "maj1"

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
# Police deployment, injuries and arrests, from the Violence_Berlin repo.
# Berlin only: Warsaw has no equivalent series.
PRZEMOC = BASE / "input/przemoc_berlin.csv"
# Warsaw's rally place, given by hand. Derived from the roczniki it was
# simply wrong: the prose names several places per route and the first one
# is the assembly point, not where the rally was held.
MIEJSCA_WIECU_PL = BASE / "input/miejsca_wiecu_warszawa.tsv"
# The averaged attendance, one figure per year per event series, lifted from
# the repo's chart page by parse_srednie.py. These are the numbers the
# analysis quotes, so POLE reports them rather than averaging afresh.
SREDNIE = BASE / "input/frekwencja_srednie.tsv"
# Which of the three streams each series belongs to, so attendance lines up
# with the way the Violence_Berlin data splits arrests. Anything unlisted is
# the May 1st stream.
SERIA_STRUMIEN = {"antinazi": "npd_kontra", "nazi": "npd_kontra",
                  "prawica": "npd_kontra"}

# One order, used by the city tables and by the combined one (prefixed).
KOLUMNY_MIASTA = [
    "liczba_wydarzen", "typy", "liczba_demonstracji", "liczba_upamietnien",
    "liczba_festynow", "czy_kontra", "demonstracje_piesze", "korso",
    "liczba_rewolucyjnych", "marsz_gwiazdzisty", "liczba_zwiazkowych",
    "liczba_prawicowych", "liczba_kontra", "liczba_wiecow",
    "liczba_happeningow", "liczba_spotkan", "liczba_koncertow",
    "liczba_poza_centrum", "liczba_dzielnicowych",
    "serie_dzielnicowe_czynne", "dzielnicowe_kronika",
    "frekwencja_suma", "frekwencja_maj1", "frekwencja_walpurgis",
    "frekwencja_npd_kontra", "frekwencja_zwiazkowa", "udzial_zwiazkowy",
    "liczba_aktorow", "aktorzy_nowi", "aktorzy_znikajacy", "wydarzenia_nowe",
    "wydarzenia_znikajace", "miejsce_wiecu", "miejsce_wiecu_zmienione",
    "trasa_glowna_zmieniona", "notatka",
]
KOLUMNY_DE = ["frekwencja_repo", "policja_sily", "ranni_policjanci",
              "zatrzymania_1maja", "zatrzymania_walpurgis", "zatrzymania_kontra"]
PLIKI_MIAST = {"PL": "pole_warszawa.csv", "DE": "pole_berlin.csv"}
MIASTA = ["PL", "DE"]
# Declared scope per city (instrukcja_v2.md sec. 0). The attendance
# spreadsheet runs to 2026, well past the maps, so without this the table
# grows years that have a headcount and no events to attach it to.
ZAKRES = {"PL": (1989, 2019), "DE": (1987, 2019)}
# Actors whose events count as union events. Taken from the map layers'
# `charakter`, plus the unions that appear only in the roczniki.
ZWIAZKI_DODATKOWE = {"DGB", "DGB Berlin-Brandenburg", "OPZZ", "IG Metall",
                     "ÖTV", "FDGB", "DAG", "Solidarność"}


def wczytaj(nazwa):
    with (OUT_DIR / nazwa).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def wczytaj_srednie():
    """-> {(rok, miasto): {seria: (etykieta, grupa, srednia)}}, plus serie per miasto."""
    if not SREDNIE.exists():
        return {}, {}
    dane, serie_miasta = defaultdict(dict), defaultdict(list)
    for linia in SREDNIE.read_text(encoding="utf-8").splitlines():
        if not linia.strip() or linia.startswith("#") or linia.startswith("rok\t"):
            continue
        rok, miasto, seria, etykieta, grupa, srednia = (linia.split("\t") + [""] * 6)[:6]
        if not rok.strip().isdigit():
            continue
        dane[(int(rok), miasto)][seria] = (etykieta, grupa, int(srednia))
        if seria not in serie_miasta[miasto]:
            serie_miasta[miasto].append(seria)
    return dane, {m: sorted(v) for m, v in serie_miasta.items()}


def wczytaj_miejsca_wiecu_pl():
    """rok -> miejsce. Rok obecny z pusta wartoscia znaczy: wiecu nie bylo."""
    if not MIEJSCA_WIECU_PL.exists():
        return {}
    out = {}
    for linia in MIEJSCA_WIECU_PL.read_text(encoding="utf-8").splitlines():
        if not linia.strip() or linia.startswith("#") or linia.startswith("rok\t"):
            continue
        czesci = linia.split("\t")
        if czesci[0].strip().isdigit():
            out[int(czesci[0])] = czesci[1].strip() if len(czesci) > 1 else ""
    return out


def wczytaj_przemoc():
    """rok -> {kolumna: wartosc}, pusty slownik gdy pliku brak."""
    if not PRZEMOC.exists():
        return {}
    with PRZEMOC.open(encoding="utf-8") as f:
        return {int(r["year"]): r for r in csv.DictReader(f) if r.get("year", "").isdigit()}


def liczba(tekst):
    tekst = (tekst or "").strip()
    return int(tekst) if tekst.lstrip("-").isdigit() else ""


def normalizuj_trase(tekst):
    if not tekst:
        return ""
    return re.sub(r"[^a-zà-ż]+", " ", tekst.lower()).strip()


def main():
    wydarzenia = wczytaj("wydarzenia.csv")
    frekwencja = wczytaj("frekwencja_agg.csv")
    roczniki = wczytaj("roczniki_wydarzenia.csv")
    przemoc = wczytaj_przemoc()
    # Chronicle entries with no object on the map: where the district events
    # actually are, since they were never put on the maps.
    # Cykle dzielnicowe: rok mieszczacy sie w rozpietosci cyklu liczy sie
    # jako rok, w ktorym impreza sie odbyla, nawet bez opisu tej edycji.
    # To inna wiedza niz udokumentowany wiersz i stoi w osobnej kolumnie.
    serie_dzielnicowe = []
    for sr in wczytaj("dzielnicowe_serie.csv"):
        if sr.get("od_roku", "").isdigit() and sr.get("do_roku", "").isdigit():
            serie_dzielnicowe.append((int(sr["od_roku"]), int(sr["do_roku"])))

    kronika_dzielnicowe = defaultdict(int)
    for k in wczytaj("brakujace_na_mapie.csv"):
        if k["dzielnicowe"]:
            kronika_dzielnicowe[(int(k["rok"]), k["miasto"])] += 1
    miejsca_pl = wczytaj_miejsca_wiecu_pl()
    srednie, serie_miast = wczytaj_srednie()

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

    # Event series per year/city, carrying the id of the event that stands for
    # the series that year. Every id contains its own year, so comparing ids
    # directly would make every event new every year; the series (type+actor)
    # is what recurs, and the id is how it is shown.
    serie = {}
    for w in wydarzenia:
        if w["aktor"]:
            serie.setdefault((int(w["rok"]), w["miasto"]), {}).setdefault(
                (w["typ"], w["aktor"]), w["id"])

    # main route and rally venue per year/city, from the union's rocznik entry
    trasy, miejsca_wiecu = {}, {}
    for r in roczniki:
        if r["aktor"] not in zwiazkowi:
            continue
        if r["trasa"]:
            trasy.setdefault((int(r["rok"]), r["miasto"]), r["trasa"])
        if r["miejsce_wiecu"]:
            miejsca_wiecu.setdefault((int(r["rok"]), r["miasto"]), r["miejsce_wiecu"])

    wiersze = []
    wiersze_miast = {m: [] for m in MIASTA}
    for rok in lata:
        wiersz = {"rok": rok}
        for miasto in MIASTA:
            p = miasto.lower()
            od, do = ZAKRES[miasto]
            if not (od <= rok <= do):
                # Outside this city's scope: blank, so an empty cell reads as
                # "not covered" rather than as a measured zero. The city's own
                # table gets no row at all for such a year.
                for k in KOLUMNY_MIASTA + [f"frekwencja_{x}"
                                           for x in serie_miast.get(miasto, [])]:
                    wiersz[f"{p}_{k}"] = ""
                continue
            zdarzenia = [w for w in wydarzenia
                         if int(w["rok"]) == rok and w["miasto"] == miasto]
            grupy = [f for f in frekwencja
                     if int(f["rok"]) == rok and f["miasto"] == miasto]
            # Attendance comes from the averaged series, not from a mean
            # recomputed here: two averaging methods over one spreadsheet
            # would disagree quietly and nobody would know which figure the
            # paper was quoting.
            odczyty = srednie.get((rok, miasto), {})
            suma = sum(v for _, _, v in odczyty.values())
            suma_zw = sum(v for _, grupa, v in odczyty.values() if grupa == "union")
            strumienie = defaultdict(int)
            for seria, (_, _, v) in odczyty.items():
                strumienie[SERIA_STRUMIEN.get(seria, "maj1")] += v

            teraz = aktorzy.get((rok, miasto), set())
            wczoraj = aktorzy.get((rok - 1, miasto), set())
            serie_teraz = serie.get((rok, miasto), {})
            serie_wczoraj = serie.get((rok - 1, miasto), {})
            # Only Warsaw's route field is a chain of stops that can be
            # compared year to year. Berlin's is press prose, reworded every
            # year by whoever wrote it, so comparing the strings would report
            # a changed route almost every year and mean nothing.
            if miasto == "PL":
                trasa = normalizuj_trase(trasy.get((rok, miasto), ""))
                poprzednia = normalizuj_trase(trasy.get((rok - 1, miasto), ""))
                zmiana = ("TRUE" if trasa != poprzednia else "FALSE") if trasa and poprzednia else ""
            else:
                zmiana = ""

            if miasto == "PL" and miejsca_pl:
                # The table governs Warsaw outright. A year it does not list
                # is unknown, not a licence to fall back on the derivation
                # that was wrong in the first place -- 2019 came out as
                # "Brama Stracen", which is a wreath-laying, not the rally.
                miejsce = miejsca_pl.get(rok, "")
                miejsce_wczoraj = miejsca_pl.get(rok - 1, "")
            else:
                miejsce = miejsca_wiecu.get((rok, miasto), "")
                miejsce_wczoraj = miejsca_wiecu.get((rok - 1, miasto), "")
            if miejsce and miejsce_wczoraj:
                zmiana_miejsca = ("TRUE" if normalizuj_trase(miejsce) !=
                                  normalizuj_trase(miejsce_wczoraj) else "FALSE")
            else:
                zmiana_miejsca = ""

            typy = {}
            for e in zdarzenia:
                typy[e["typ"]] = typy.get(e["typ"], 0) + 1
            # Walking marches against the wheeled and static forms: the shift
            # from one column on foot to a korso is a change in the field, not
            # just in the count.
            piesze = sum(1 for e in zdarzenia if e["typ"] == "demonstracja"
                         and e["geom_typ"] in ("LineString", "MultiLineString"))
            rewolucyjne = sum(1 for e in zdarzenia
                              if e["warstwa"] in WARSTWY_REWOLUCYJNE or e["aktor"] == "R1M")
            trasa_tekst = (trasy.get((rok, miasto), "") or "").lower()
            gwiazdzisty = "TRUE" if "sternmarsch" in trasa_tekst else (
                "FALSE" if trasa_tekst else "")

            pola = {
                "liczba_wydarzen": len(zdarzenia),
                "typy": ";".join(f"{t}:{n}" for t, n in sorted(typy.items())),
                "liczba_demonstracji": typy.get("demonstracja", 0),
                "liczba_upamietnien": typy.get("upamiętnienie", 0) + typy.get("kwiaty", 0),
                "liczba_festynow": typy.get("festyn", 0),
                "czy_kontra": "TRUE" if typy.get("kontra") else "FALSE",
                "demonstracje_piesze": piesze,
                "korso": typy.get("korso", 0),
                "liczba_rewolucyjnych": rewolucyjne,
                "marsz_gwiazdzisty": gwiazdzisty,
                "liczba_zwiazkowych": sum(1 for w in zdarzenia
                                               if w["charakter"] == "zwiazkowe"),
                "liczba_prawicowych": sum(1 for w in zdarzenia
                                               if w["warstwa"] in WARSTWY_PRAWICOWE),
                "liczba_kontra": sum(1 for w in zdarzenia
                                          if w["charakter"] == "kontra"),
                # The remaining types, so every event in the year is counted
                # under some column and not only inside the _typy string.
                "liczba_wiecow": typy.get("wiec", 0),
                "liczba_happeningow": typy.get("happening", 0),
                "liczba_spotkan": typy.get("spotkanie", 0),
                "liczba_koncertow": typy.get("koncert", 0),
                "liczba_poza_centrum": sum(1 for w in zdarzenia
                                                if w.get("poza_centrum") == "TRUE"),
                "liczba_dzielnicowych": sum(1 for w in zdarzenia
                                                 if w.get("dzielnicowe") == "TRUE"),
                # Ile cykli dzielnicowych bylo w tym roku czynnych. Rok w
                # rozpietosci cyklu liczy sie nawet bez opisu tej edycji --
                # to wiedza innego rodzaju niz udokumentowany wiersz, wiec
                # stoi w osobnej kolumnie, nie dodaje sie do tamtej.
                "serie_dzielnicowe_czynne": (
                    sum(1 for od_s, do_s in serie_dzielnicowe if od_s <= rok <= do_s)
                    if miasto == "DE" else ""),
                "dzielnicowe_kronika": kronika_dzielnicowe.get((rok, miasto), 0),
                "frekwencja_maj1": strumienie.get("maj1", "") or "",
                "frekwencja_walpurgis": strumienie.get("walpurgis", "") or "",
                "frekwencja_npd_kontra": strumienie.get("npd_kontra", "") or "",
                "frekwencja_suma": suma or "",
                "frekwencja_zwiazkowa": suma_zw or "",
                "udzial_zwiazkowy": round(suma_zw / suma, 3) if suma else "",
                "liczba_aktorow": len(teraz),
                "aktorzy_nowi": ";".join(sorted(teraz - wczoraj)) if wczoraj else "",
                "aktorzy_znikajacy": ";".join(sorted(wczoraj - teraz)) if wczoraj else "",
                "wydarzenia_nowe": ";".join(sorted(
                    i for s, i in serie_teraz.items() if s not in serie_wczoraj)) if serie_wczoraj else "",
                "wydarzenia_znikajace": ";".join(sorted(
                    i for s, i in serie_wczoraj.items() if s not in serie_teraz)) if serie_wczoraj else "",
                "miejsce_wiecu": miejsce,
                "miejsce_wiecu_zmienione": zmiana_miejsca,
                "trasa_glowna_zmieniona": zmiana,
                "notatka": f"obsidian://open?vault=Wszystko&file={rok}_{miasto}",
            }
            # Every series as its own column: this is the split by event type
            # with its attendance, in the city's own table.
            for seria in serie_miast.get(miasto, []):
                wpis = odczyty.get(seria)
                pola[f"frekwencja_{seria}"] = wpis[2] if wpis else ""
            if miasto == "DE":
                pr = przemoc.get(rok, {})
                pola.update({
                    "policja_sily": liczba(pr.get("einsatz")),
                    "ranni_policjanci": liczba(pr.get("injured_officers")),
                    "zatrzymania_1maja": liczba(pr.get("arrests_may1")),
                    "zatrzymania_walpurgis": liczba(pr.get("arrests_walpurgisnacht")),
                    "zatrzymania_kontra": liczba(pr.get("arrests_npd_kontra")),
                    # The repo's single turnout figure, kept next to our own
                    # sum rather than merged into it: it counts the main
                    # demonstration, while frekwencja_suma adds up every event
                    # of the year, so the two are not the same measure and
                    # reconciling them is a decision, not arithmetic.
                    "frekwencja_repo": liczba(pr.get("turnout")),
                })
            wiersze_miast[miasto].append({"rok": rok, **pola})
            wiersz.update({f"{p}_{k}": v for k, v in pola.items()})
        if any(wiersz[f"{m.lower()}_liczba_wydarzen"] != "" for m in MIASTA):
            wiersze.append(wiersz)

    # Two tables, one per city: they have different columns (Berlin alone
    # has the police series) and different year ranges, and reading one city
    # meant skipping every other column in the wide table.
    for miasto, nazwa in PLIKI_MIAST.items():
        kol = (["rok"] + KOLUMNY_MIASTA
               + [f"frekwencja_{x}" for x in serie_miast.get(miasto, [])]
               + (KOLUMNY_DE if miasto == "DE" else []))
        write_csv(OUT_DIR / nazwa, wiersze_miast[miasto], kol)

    # The wide table stays as the side-by-side view the HTML and the
    # kartoteka read; it is the two above, prefixed and joined on the year.
    kolumny = ["rok"]
    for miasto in MIASTA:
        p = miasto.lower()
        kolumny += [f"{p}_{k}" for k in KOLUMNY_MIASTA]
        kolumny += [f"{p}_frekwencja_{x}" for x in serie_miast.get(miasto, [])]
        if miasto == "DE":
            kolumny += [f"de_{k}" for k in KOLUMNY_DE]
    write_csv(OUT_DIR / "pole.csv", wiersze, kolumny)
    zapisz_html(wiersze, OUT_DIR / "pole.html")
    poza = [w for w in wydarzenia
            if not (ZAKRES[w["miasto"]][0] <= int(w["rok"]) <= ZAKRES[w["miasto"]][1])]
    for miasto, nazwa in PLIKI_MIAST.items():
        w = wiersze_miast[miasto]
        print(f"{nazwa}: {len(w)} lat ({w[0]['rok']}-{w[-1]['rok']})")
    print(f"pole.csv:  {len(wiersze)} lat ({wiersze[0]['rok']}-{wiersze[-1]['rok']})")
    if poza:
        lata_poza = sorted({w["rok"] for w in poza})
        print(f"  poza zakresem, nie liczone: {len(poza)} wydarzen ({', '.join(lata_poza)})")
    braki = [str(r) for r in range(ZAKRES["PL"][0], ZAKRES["PL"][1] + 1) if r not in miejsca_pl]
    if braki:
        print(f"  miejsce wiecu PL nieustalone dla: {', '.join(braki)}")
    print(f"pole.html: {(OUT_DIR / 'pole.html').stat().st_size // 1024} KB")


def zapisz_html(wiersze, sciezka):
    naglowki = ["wydarzenia", "zwiazk.", "prawic.", "kontra", "frekwencja",
                "fr. zwiazkowa", "udzial", "aktorzy", "nowe id", "znikajace id",
                "miejsce wiecu", "wiec inny", "trasa inna"]
    kol = ["liczba_wydarzen", "liczba_zwiazkowych", "liczba_prawicowych",
           "liczba_kontra", "frekwencja_suma", "frekwencja_zwiazkowa",
           "udzial_zwiazkowy", "liczba_aktorow", "wydarzenia_nowe",
           "wydarzenia_znikajace", "miejsce_wiecu", "miejsce_wiecu_zmienione",
           "trasa_glowna_zmieniona"]
    czesci = ["""<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">
<title>POLE</title><style>
body{font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#1a1714;background:#faf8f5}
h1{font-size:18px;margin:0 0 4px}p.sub{color:#6b6459;margin:0 0 18px;font-size:12px}
table{border-collapse:collapse;font-size:12px}
th,td{border:1px solid #d8d2c8;padding:3px 7px;text-align:right;white-space:nowrap}
th{background:#ede9e2;font-weight:600}
td.akt{text-align:left;max-width:280px;overflow:hidden;text-overflow:ellipsis;font-size:11px;color:#5a534a}
td.rok{text-align:left;font-weight:600;background:#f3f0eb}
.pl{background:#eef4f9}.de{background:#fceeec}
tr:hover td{background:#fff8e6}
</style></head><body><h1>POLE &mdash; przekr&oacute;j rok &times; miasto</h1>
<p class="sub">Frekwencja: &#347;rednie z <code>index.html</code> (liczone z arkusza),
sumowane po seriach wydarze&#324;. Pe&#322;ny rozbi&oacute;r na serie &mdash; i dane policyjne dla Berlina &mdash;
w <code>pole_warszawa.csv</code> i <code>pole_berlin.csv</code>.</p>
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
                v = str(w[f"{p}_{k}"])
                if "aktorzy" in k or "wydarzenia_" in k:
                    # Ids are long and there can be several; the cell is
                    # clipped, so carry the full list in the tooltip.
                    tytul = f' title="{html.escape(v.replace(";", chr(10)))}"' if v else ""
                    czesci.append(f'<td class="akt"{tytul}>{html.escape(v)}</td>')
                else:
                    czesci.append(f"<td>{html.escape(v)}</td>")
        czesci.append("</tr>")
    czesci.append("</tbody></table></body></html>")
    sciezka.write_text("".join(czesci), encoding="utf-8")


if __name__ == "__main__":
    main()
