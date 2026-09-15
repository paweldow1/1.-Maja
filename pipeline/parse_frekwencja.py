"""Step 4b: import the dedicated attendance sources.

These supersede the headcounts scraped out of the rocznik prose: they are
one reading per row, with the counting party (prasa / policja /
organizatorzy) recorded separately, which the prose never stated reliably.

  Berlin    FrekwencjaDGB15.xlsx, one `Dane*` sheet per actor
  Warszawa  frekwencja_warszawa_zwiazki.tsv (unions only; other Warsaw
            events carry their headcount in the map data)

Usage: python3 parse_frekwencja.py <input_dir>
"""
import csv
import statistics
import sys
from pathlib import Path

import openpyxl

from common import write_csv

OUT_DIR = Path(__file__).parent / "output"

# sheet -> (aktor, wydarzenie). Several sheets are the same actor at a
# different event, so the actor alone would silently merge them: R1M's
# 13:00 march and its evening demo are different events, as is the joint
# march they ran until 1995.
ARKUSZE = {
    "Dane": ("DGB", "demonstracja"),
    "Dane_Revo": ("R1M", "demonstracja wieczorna"),
    "Dane_Revo13": ("R1M", "demonstracja 13:00"),
    "Dane_Revo_joint": ("R1M", "demonstracja wspolna"),
    "Dane_Antinazi": ("Antifa", "kontrdemonstracja"),
    "Dane_Nazi": ("NPD", "demonstracja"),
    "Dane_MyFest": ("MyFest", "festyn"),
    "Dane_Mariannenplatz": ("Mariannenplatz", "festyn"),
    "Dane_Ost_PDS": ("PDS", "demonstracja"),
    "Euro MayDay": ("EuroMayDay", "demonstracja"),
    "Dane_MyGruni": ("MyGruni", "festyn"),
}
KATEGORIE = {"prasa", "policja", "organizatorzy"}


def wczytaj_xlsx(path, odrzucone):
    wiersze = []
    wb = openpyxl.load_workbook(path, data_only=True)
    plik = Path(path).name
    for arkusz, (aktor, wydarzenie) in ARKUSZE.items():
        for nr, r in enumerate(wb[arkusz].iter_rows(values_only=True), start=1):
            if nr == 1 or not r or r[0] is None:
                continue
            rok, licz = r[0], r[1] if len(r) > 1 else None
            zrodlo = r[2] if len(r) > 2 else None
            kategoria = r[3] if len(r) > 3 else None
            if not isinstance(rok, (int, float)):
                odrzucone.append({"plik": plik, "arkusz": arkusz, "wiersz": nr,
                                  "powod": "rok nieliczbowy", "wartosc": repr(rok)})
                continue
            if not isinstance(licz, (int, float)):
                odrzucone.append({"plik": plik, "arkusz": arkusz, "wiersz": nr,
                                  "powod": "brak liczby", "wartosc": repr(licz)})
                continue
            kat = str(kategoria).strip() if kategoria is not None else ""
            if kat and kat not in KATEGORIE:
                odrzucone.append({"plik": plik, "arkusz": arkusz, "wiersz": nr,
                                  "powod": "nieznana kategoria", "wartosc": kat})
            wiersze.append({
                "rok": int(rok), "miasto": "DE", "aktor": aktor,
                "wydarzenie": wydarzenie, "liczba": int(licz),
                "zrodlo": str(zrodlo).strip() if zrodlo else "",
                "kategoria": kat if kat in KATEGORIE else "",
                "plik_zrodlowy": f"{plik}#{arkusz}",
            })
    return wiersze


def wczytaj_tsv(path, odrzucone):
    wiersze = []
    plik = Path(path).name
    with open(path, encoding="utf-8") as f:
        for nr, row in enumerate(csv.DictReader(f, delimiter="\t"), start=2):
            surowa = (row.get("Liczba uczestników") or "").strip()
            rok = (row.get("Rok") or "").strip()
            if not rok.isdigit() or not surowa.replace(" ", "").isdigit():
                odrzucone.append({"plik": plik, "arkusz": "", "wiersz": nr,
                                  "powod": "rok lub liczba nieliczbowa",
                                  "wartosc": f"{rok!r}/{surowa!r}"})
                continue
            wiersze.append({
                "rok": int(rok), "miasto": "PL", "aktor": "OPZZ",
                "wydarzenie": "demonstracja",
                "liczba": int(surowa.replace(" ", "")),
                "zrodlo": (row.get("Źródło") or "").strip(),
                # The Warsaw table has no counting-party column; leaving it
                # blank rather than guessing which sources are press.
                "kategoria": "",
                "plik_zrodlowy": plik,
            })
    return wiersze


def agreguj(wiersze):
    grupy = {}
    for w in wiersze:
        grupy.setdefault((w["rok"], w["miasto"], w["aktor"], w["wydarzenie"]), []).append(w)
    out = []
    for (rok, miasto, aktor, wydarzenie), grupa in sorted(grupy.items()):
        liczby = [g["liczba"] for g in grupa]
        wiersz = {
            "rok": rok, "miasto": miasto, "aktor": aktor, "wydarzenie": wydarzenie,
            "n_odczytow": len(liczby),
            "frekwencja_min": min(liczby),
            "frekwencja_max": max(liczby),
            "frekwencja_sr": round(statistics.mean(liczby)),
            "frekwencja_mediana": round(statistics.median(liczby)),
        }
        for kat in sorted(KATEGORIE):
            wartosci = [g["liczba"] for g in grupa if g["kategoria"] == kat]
            wiersz[f"fr_{kat}"] = round(statistics.mean(wartosci)) if wartosci else ""
        wiersz["zrodla"] = ";".join(sorted({g["zrodlo"] for g in grupa if g["zrodlo"]}))
        out.append(wiersz)
    return out


def porownaj_z_rocznikami(agg):
    """Flag where the prose-derived figure disagrees with the dedicated source.

    Not an error to fix automatically: it catches typos in the roczniki
    (a 60000 that the spreadsheet records as 6000) and cases where the two
    count different things (the march vs the rally).
    """
    sciezka = OUT_DIR / "roczniki_wydarzenia.csv"
    if not sciezka.exists():
        return []
    wg_aktora = {}
    for a in agg:
        wg_aktora.setdefault((a["rok"], a["miasto"], a["aktor"]), []).append(a)

    out = []
    with sciezka.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r["frekwencja_sr"]:
                continue
            klucz = (int(r["rok"]), r["miasto"], r["aktor"])
            kandydaci = wg_aktora.get(klucz)
            if not kandydaci:
                continue
            z_rocznika = int(r["frekwencja_sr"])
            # An actor can have several events in a year; compare against the
            # closest one rather than declaring a mismatch against all of them.
            najblizszy = min(kandydaci, key=lambda a: abs(a["frekwencja_sr"] - z_rocznika))
            z_arkusza = najblizszy["frekwencja_sr"]
            odchylka = abs(z_arkusza - z_rocznika) / max(z_arkusza, z_rocznika, 1)
            if odchylka <= 0.05:
                continue
            out.append({
                "rok": r["rok"], "miasto": r["miasto"], "aktor": r["aktor"],
                "wydarzenie": najblizszy["wydarzenie"],
                "frekwencja_rocznik": z_rocznika,
                "frekwencja_arkusz": z_arkusza,
                "odchylka_proc": round((z_rocznika - z_arkusza) / z_arkusza * 100),
                "lista_rocznik": r["frekwencja_lista"],
                "zrodla_arkusz": najblizszy["zrodla"],
            })
    return out


def main(input_dir):
    input_dir = Path(input_dir)
    odrzucone = []
    wiersze = wczytaj_xlsx(input_dir / "FrekwencjaDGB15.xlsx", odrzucone)
    wiersze += wczytaj_tsv(input_dir / "frekwencja_warszawa_zwiazki.tsv", odrzucone)
    wiersze.sort(key=lambda w: (w["miasto"], w["rok"], w["aktor"], w["wydarzenie"]))

    agg = agreguj(wiersze)
    write_csv(OUT_DIR / "frekwencja.csv", wiersze, [
        "rok", "miasto", "aktor", "wydarzenie", "liczba", "zrodlo", "kategoria",
        "plik_zrodlowy"])
    write_csv(OUT_DIR / "frekwencja_agg.csv", agg, [
        "rok", "miasto", "aktor", "wydarzenie", "n_odczytow", "frekwencja_min",
        "frekwencja_max", "frekwencja_sr", "frekwencja_mediana",
        "fr_organizatorzy", "fr_policja", "fr_prasa", "zrodla"])
    write_csv(OUT_DIR / "frekwencja_odrzucone.csv", odrzucone, [
        "plik", "arkusz", "wiersz", "powod", "wartosc"])

    rozbieznosci = porownaj_z_rocznikami(agg)
    write_csv(OUT_DIR / "frekwencja_rozbieznosci.csv", rozbieznosci, [
        "rok", "miasto", "aktor", "wydarzenie", "frekwencja_rocznik",
        "frekwencja_arkusz", "odchylka_proc", "lista_rocznik", "zrodla_arkusz"])
    print(f"rozbieznosci vs roczniki: {len(rozbieznosci)}")

    pl = [w for w in wiersze if w["miasto"] == "PL"]
    de = [w for w in wiersze if w["miasto"] == "DE"]
    print(f"frekwencja.csv:     {len(wiersze)} odczytow  (PL {len(pl)}, DE {len(de)})")
    print(f"frekwencja_agg.csv: {len(agg)} grup rok/aktor/wydarzenie")
    print(f"odrzucone:          {len(odrzucone)}")
    if de:
        print(f"zakres DE: {min(w['rok'] for w in de)}-{max(w['rok'] for w in de)}")
    if pl:
        print(f"zakres PL: {min(w['rok'] for w in pl)}-{max(w['rok'] for w in pl)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "input")
