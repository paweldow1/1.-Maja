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
    kronika_dzielnicowe = defaultdict(int)
    for k in wczytaj("brakujace_na_mapie.csv"):
        if k["dzielnicowe"]:
            kronika_dzielnicowe[(int(k["rok"]), k["miasto"])] += 1
    miejsca_pl = wczytaj_miejsca_wiecu_pl()

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
    for rok in lata:
        wiersz = {"rok": rok}
        for miasto in MIASTA:
            p = miasto.lower()
            od, do = ZAKRES[miasto]
            if not (od <= rok <= do):
                # Outside this city's scope: blank, so an empty cell reads as
                # "not covered" rather than as a measured zero.
                for k in ("typy", "liczba_demonstracji", "liczba_upamietnien", "liczba_festynow",
                          "czy_kontra", "demonstracje_piesze", "korso",
                          "liczba_rewolucyjnych", "marsz_gwiazdzisty",
                          "liczba_wydarzen", "liczba_zwiazkowych", "frekwencja_suma",
                          "frekwencja_zwiazkowa", "udzial_zwiazkowy", "liczba_aktorow",
                          "aktorzy_nowi", "aktorzy_znikajacy", "wydarzenia_nowe",
                          "wydarzenia_znikajace", "liczba_prawicowych", "liczba_kontra",
                          "miejsce_wiecu", "miejsce_wiecu_zmienione",
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

            # The maps carry headcounts for events the dedicated sheets do not
            # cover -- in Warsaw that is everything except the unions, without
            # which the union share is 1.0 by construction. Only actors the
            # sheets miss are added, and identical readings within one
            # actor+type are counted once: several map objects can describe
            # the same event and repeat its figure.
            pokryci = {f["aktor"] for f in grupy if f["frekwencja_sr"]}
            z_mapy = set()
            for e in zdarzenia:
                if e["aktor"] in pokryci or not e["frekwencja_mapa_num"]:
                    continue
                z_mapy.add((e["typ"], e["aktor"], int(e["frekwencja_mapa_num"])))
            suma += sum(n for _, _, n in z_mapy)
            suma_zw += sum(n for _, aktor, n in z_mapy if aktor in zwiazkowi)

            # Same figures, split into the three streams.
            strumienie = defaultdict(int)
            for f in grupy:
                if f["frekwencja_sr"]:
                    strumienie[STRUMIEN_AKTOR.get(f["aktor"], "maj1")] += int(f["frekwencja_sr"])
            widziane = set()
            for e in zdarzenia:
                if e["aktor"] in pokryci or not e["frekwencja_mapa_num"]:
                    continue
                klucz_e = (e["typ"], e["aktor"], int(e["frekwencja_mapa_num"]))
                if klucz_e in widziane:
                    continue
                widziane.add(klucz_e)
                strumienie[strumien(e["warstwa"], e["charakter"])] += int(e["frekwencja_mapa_num"])
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

            wiersz.update({
                f"{p}_liczba_wydarzen": len(zdarzenia),
                f"{p}_typy": ";".join(f"{t}:{n}" for t, n in sorted(typy.items())),
                f"{p}_liczba_demonstracji": typy.get("demonstracja", 0),
                f"{p}_liczba_upamietnien": typy.get("upamiętnienie", 0) + typy.get("kwiaty", 0),
                f"{p}_liczba_festynow": typy.get("festyn", 0),
                f"{p}_czy_kontra": "TRUE" if typy.get("kontra") else "FALSE",
                f"{p}_demonstracje_piesze": piesze,
                f"{p}_korso": typy.get("korso", 0),
                f"{p}_liczba_rewolucyjnych": rewolucyjne,
                f"{p}_marsz_gwiazdzisty": gwiazdzisty,
                f"{p}_liczba_zwiazkowych": sum(1 for w in zdarzenia
                                               if w["charakter"] == "zwiazkowe"),
                f"{p}_liczba_prawicowych": sum(1 for w in zdarzenia
                                               if w["warstwa"] in WARSTWY_PRAWICOWE),
                f"{p}_liczba_kontra": sum(1 for w in zdarzenia
                                          if w["charakter"] == "kontra"),
                # The remaining types, so every event in the year is counted
                # under some column and not only inside the _typy string.
                f"{p}_liczba_wiecow": typy.get("wiec", 0),
                f"{p}_liczba_happeningow": typy.get("happening", 0),
                f"{p}_liczba_spotkan": typy.get("spotkanie", 0),
                f"{p}_liczba_koncertow": typy.get("koncert", 0),
                f"{p}_liczba_poza_centrum": sum(1 for w in zdarzenia
                                                if w.get("poza_centrum") == "TRUE"),
                f"{p}_liczba_dzielnicowych": sum(1 for w in zdarzenia
                                                 if w.get("dzielnicowe") == "TRUE"),
                f"{p}_dzielnicowe_kronika": kronika_dzielnicowe.get((rok, miasto), 0),
                f"{p}_frekwencja_maj1": strumienie.get("maj1", "") or "",
                f"{p}_frekwencja_walpurgis": strumienie.get("walpurgis", "") or "",
                f"{p}_frekwencja_npd_kontra": strumienie.get("npd_kontra", "") or "",
                f"{p}_frekwencja_suma": suma or "",
                f"{p}_frekwencja_zwiazkowa": suma_zw or "",
                f"{p}_udzial_zwiazkowy": round(suma_zw / suma, 3) if suma else "",
                f"{p}_liczba_aktorow": len(teraz),
                f"{p}_aktorzy_nowi": ";".join(sorted(teraz - wczoraj)) if wczoraj else "",
                f"{p}_aktorzy_znikajacy": ";".join(sorted(wczoraj - teraz)) if wczoraj else "",
                f"{p}_wydarzenia_nowe": ";".join(sorted(
                    i for s, i in serie_teraz.items() if s not in serie_wczoraj)) if serie_wczoraj else "",
                f"{p}_wydarzenia_znikajace": ";".join(sorted(
                    i for s, i in serie_wczoraj.items() if s not in serie_teraz)) if serie_wczoraj else "",
                f"{p}_miejsce_wiecu": miejsce,
                f"{p}_miejsce_wiecu_zmienione": zmiana_miejsca,
                f"{p}_trasa_glowna_zmieniona": zmiana,
                f"{p}_notatka": f"obsidian://open?vault=Wszystko&file={rok}_{miasto}",
            })
            if miasto == "DE":
                pr = przemoc.get(rok, {})
                wiersz.update({
                    "de_policja_sily": liczba(pr.get("einsatz")),
                    "de_ranni_policjanci": liczba(pr.get("injured_officers")),
                    "de_zatrzymania_1maja": liczba(pr.get("arrests_may1")),
                    "de_zatrzymania_walpurgis": liczba(pr.get("arrests_walpurgisnacht")),
                    "de_zatrzymania_kontra": liczba(pr.get("arrests_npd_kontra")),
                    # The repo's single turnout figure, kept next to our own
                    # sum rather than merged into it: it counts the main
                    # demonstration, while de_frekwencja_suma adds up every
                    # event of the year, so the two are not the same measure
                    # and reconciling them is a decision, not arithmetic.
                    "de_frekwencja_repo": liczba(pr.get("turnout")),
                })
        if any(wiersz[f"{m.lower()}_liczba_wydarzen"] != "" for m in MIASTA):
            wiersze.append(wiersz)

    kolumny = ["rok"]
    for miasto in MIASTA:
        p = miasto.lower()
        kolumny += [f"{p}_liczba_wydarzen", f"{p}_typy",
                    f"{p}_liczba_demonstracji", f"{p}_liczba_upamietnien",
                    f"{p}_liczba_festynow", f"{p}_czy_kontra",
                    f"{p}_demonstracje_piesze", f"{p}_korso",
                    f"{p}_liczba_rewolucyjnych", f"{p}_marsz_gwiazdzisty",
                    f"{p}_liczba_zwiazkowych",
                    f"{p}_liczba_prawicowych", f"{p}_liczba_kontra",
                    f"{p}_liczba_wiecow", f"{p}_liczba_happeningow",
                    f"{p}_liczba_spotkan", f"{p}_liczba_koncertow",
                    f"{p}_liczba_poza_centrum", f"{p}_liczba_dzielnicowych",
                    f"{p}_dzielnicowe_kronika",
                    f"{p}_frekwencja_suma", f"{p}_frekwencja_maj1",
                    f"{p}_frekwencja_walpurgis", f"{p}_frekwencja_npd_kontra",
                    f"{p}_frekwencja_zwiazkowa",
                    f"{p}_udzial_zwiazkowy", f"{p}_liczba_aktorow",
                    f"{p}_aktorzy_nowi", f"{p}_aktorzy_znikajacy",
                    f"{p}_wydarzenia_nowe", f"{p}_wydarzenia_znikajace",
                    f"{p}_miejsce_wiecu", f"{p}_miejsce_wiecu_zmienione",
                    f"{p}_trasa_glowna_zmieniona", f"{p}_notatka"]
        if miasto == "DE":
            kolumny += ["de_frekwencja_repo",
                        "de_policja_sily", "de_ranni_policjanci",
                        "de_zatrzymania_1maja", "de_zatrzymania_walpurgis",
                        "de_zatrzymania_kontra"]
    write_csv(OUT_DIR / "pole.csv", wiersze, kolumny)
    zapisz_html(wiersze, OUT_DIR / "pole.html")
    poza = [w for w in wydarzenia
            if not (ZAKRES[w["miasto"]][0] <= int(w["rok"]) <= ZAKRES[w["miasto"]][1])]
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
<p class="sub">Frekwencja sumowana po odczytach aktor/wydarzenie, nie po wierszach wydarze&#324;;
gdzie arkusze nie si&#281;gaj&#261;, uzupe&#322;niona z pola Frekwencja na mapie.
Kolumny <i>nowe id</i> i <i>znikaj&#261;ce id</i> &mdash; naje&#380;d&#378; kursorem, by zobaczy&#263; pe&#322;n&#261; list&#281;.</p>
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
