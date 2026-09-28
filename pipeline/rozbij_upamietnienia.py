"""Split a commemoration row into one row per ceremony.

One place in one year is often several separate acts: Unia Pracy laying
wreaths alone at 11, an SLD and OPZZ delegation at the same gate at 12.
Stored as a single row they collapse into one compound actor ("UP_OPZZ_SdRP")
and the hours are lost -- so input/upamietnienia_ceremonie.tsv, read off the
verification notes, says which years split and into what.

The table also carries the hour, which is where Warsaw gets its first
`godzina` values.

Runs after zastosuj_decyzje.py: the decision applies to the object, then the
table replaces it with its ceremonies, so the table wins where they disagree.

Usage: python3 rozbij_upamietnienia.py
"""
import csv
from pathlib import Path

from common import write_csv

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
TABELA = BASE / "input/upamietnienia_ceremonie.tsv"

NOWE_KOLUMNY = ["godzina", "ceremonia", "ceremonii_lacznie", "pewnosc_ceremonii",
                "zrodlo_ceremonii", "uwaga_ceremonii"]


def wczytaj_ceremonie():
    if not TABELA.exists():
        return {}
    wiersze = [w for w in TABELA.read_text(encoding="utf-8").splitlines()
               if w.strip() and not w.startswith("#")]
    czytnik = csv.DictReader(wiersze, delimiter="\t")
    wg_klucza = {}
    for c in czytnik:
        wg_klucza.setdefault(c["klucz_zrodlowy"], []).append(c)
    for lista in wg_klucza.values():
        lista.sort(key=lambda c: int(c["ceremonia"]))
    return wg_klucza


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wydarzenia = list(csv.DictReader(f))
    kolumny = list(wydarzenia[0].keys())
    for k in NOWE_KOLUMNY:
        if k not in kolumny:
            kolumny.append(k)

    ceremonie = wczytaj_ceremonie()
    # The split replaces rows, so running it twice over the same file would
    # find nothing to split and report every key as missing. wydarzenia.csv
    # has to come from a fresh parse -- see uruchom.sh.
    if any("#c" in w["klucz_zrodlowy"] for w in wydarzenia):
        print("wydarzenia.csv jest juz rozbite -- uruchom caly potok "
              "(sh uruchom.sh), nie sam ten krok")
        return
    nieuzyte = set(ceremonie)
    out, rozbitych, dodanych, z_godzina = [], 0, 0, 0

    for w in wydarzenia:
        for k in NOWE_KOLUMNY:
            w.setdefault(k, "")
        lista = ceremonie.get(w["klucz_zrodlowy"])
        if not lista:
            # ids are regenerated for everyone so the suffixes stay consistent
            # once the split adds rows in the same year.
            out.append(w)
            continue
        nieuzyte.discard(w["klucz_zrodlowy"])
        rozbitych += 1
        dodanych += len(lista) - 1
        for c in lista:
            nowy = dict(w)
            nowy["aktor"] = c["aktor"]
            nowy["aktor_zrodlo"] = "ceremonie"
            nowy["aktor_zgadniety"] = "False"
            nowy["godzina"] = c.get("godzina", "")
            nowy["ceremonia"] = c["ceremonia"]
            nowy["ceremonii_lacznie"] = len(lista)
            nowy["pewnosc_ceremonii"] = c.get("pewnosc", "")
            nowy["zrodlo_ceremonii"] = c.get("zrodlo", "")
            nowy["uwaga_ceremonii"] = (c.get("uwaga") or "").strip()
            nowy["klucz_zrodlowy"] = f"{w['klucz_zrodlowy']}#c{c['ceremonia']}"
            nowy["wymaga_weryfikacji"] = "False"
            # The ceremony table governs these rows, not the kartoteka, so
            # they leave its queue: carrying the object's decision forward
            # would put every ceremony back up for a judgement already made,
            # under a key the page's store does not have.
            nowy["decyzja"] = ""
            if nowy["godzina"]:
                z_godzina += 1
            out.append(nowy)

    write_csv(OUT_DIR / "wydarzenia.csv", out, kolumny)

    print(f"rozbite upamietnienia: {rozbitych} obiektow -> "
          f"{rozbitych + dodanych} ceremonii (+{dodanych} wierszy)")
    print(f"  z godzina: {z_godzina}")
    print(f"  wydarzenia.csv: {len(out)} wierszy")
    if nieuzyte:
        print("  UWAGA, klucze z tabeli bez wiersza w wydarzenia.csv:")
        for k in sorted(nieuzyte):
            print("   ", k)


if __name__ == "__main__":
    main()
