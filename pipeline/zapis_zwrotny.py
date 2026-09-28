"""Step 7: write the ids back into the maps and the roczniki.

This is the only step that touches the sources, so it works on the copies
under input/, takes a .bak of every file it opens, and refuses to run when
id_geo does not point at the object it claims. Nothing is written unless
every file passes that check.

The .umap files are compacted JSON; re-dumping them pretty-printed roughly
triples their size, so they go back out with the same separators. The
roczniki get one line inserted into the frontmatter textually rather than a
YAML re-dump, which would reformat every block scalar in the file.

Usage: python3 zapis_zwrotny.py [--wykonaj]     (dry run without the flag)
"""
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
WEJSCIE = BASE / "input"
NAGLOWEK_ROKU = re.compile(r"^#\s+(\d{4})_(PL|DE)\.md\s*$")


def wczytaj(nazwa):
    with (OUT_DIR / nazwa).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def znajdz_plik(nazwa):
    trafienia = [p for p in WEJSCIE.rglob(nazwa) if p.is_file()]
    return trafienia[0] if trafienia else None


def zaladuj_features(sciezka, warstwa):
    """-> (dane, lista_features) for a geojson file or one layer of a .umap."""
    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    if "layers" in dane:
        for l in dane["layers"]:
            if l.get("properties", {}).get("name") == warstwa:
                return dane, l.get("features", [])
        return dane, None
    return dane, dane.get("features", [])


def mapy(wydarzenia, miejsca, wykonaj):
    # one object can carry several events, so the ids travel as a list
    wg_obiektu = defaultdict(list)
    for w in wydarzenia:
        wg_obiektu[(w["plik_zrodlowy"], w["warstwa"], int(w["id_geo"]))].append(w)
    wg_miejsca = {}
    for m in miejsca:
        if m.get("id_geo"):
            wg_miejsca[(m["plik_zrodlowy"], m["warstwa"], int(m["id_geo"]))] = m

    pliki = defaultdict(list)
    for (plik, warstwa, id_geo), wiersze in wg_obiektu.items():
        pliki[plik].append((warstwa, id_geo, wiersze, None))
    for (plik, warstwa, id_geo), m in wg_miejsca.items():
        pliki[plik].append((warstwa, id_geo, None, m))

    problemy, plan = [], []
    for plik, zadania in sorted(pliki.items()):
        sciezka = znajdz_plik(plik)
        if sciezka is None:
            problemy.append(f"{plik}: nie znaleziono w input/")
            continue
        for warstwa, id_geo, wiersze, miejsce in zadania:
            dane, features = zaladuj_features(sciezka, warstwa)
            if features is None:
                problemy.append(f"{plik}/{warstwa}: brak warstwy")
                continue
            if id_geo >= len(features):
                problemy.append(f"{plik}/{warstwa}#{id_geo}: indeks poza zakresem")
                continue
            oczekiwana = (wiersze[0]["nazwa"] if wiersze else miejsce["nazwa"]) or ""
            w_pliku = features[id_geo].get("properties", {}).get("name") or ""
            if oczekiwana.strip() != w_pliku.strip():
                problemy.append(
                    f"{plik}/{warstwa}#{id_geo}: nazwa nie zgadza sie "
                    f"({w_pliku[:40]!r} vs {oczekiwana[:40]!r})")
                continue
            plan.append((sciezka, warstwa, id_geo, wiersze, miejsce))

    if problemy:
        print(f"PRZERWANO: {len(problemy)} niezgodnosci, nic nie zapisano")
        for p in problemy[:10]:
            print(f"   {p}")
        return False, 0

    if not wykonaj:
        print(f"[proba] mapy: {len(plan)} obiektow dostaloby id")
        return True, len(plan)

    wg_sciezki = defaultdict(list)
    for sciezka, warstwa, id_geo, wiersze, miejsce in plan:
        wg_sciezki[sciezka].append((warstwa, id_geo, wiersze, miejsce))

    zapisane = 0
    for sciezka, zadania in wg_sciezki.items():
        kopia = sciezka.with_suffix(sciezka.suffix + ".bak")
        if not kopia.exists():
            shutil.copy2(sciezka, kopia)
        dane = json.loads(sciezka.read_text(encoding="utf-8"))
        for warstwa, id_geo, wiersze, miejsce in zadania:
            if "layers" in dane:
                features = next(l["features"] for l in dane["layers"]
                                if l.get("properties", {}).get("name") == warstwa)
            else:
                features = dane["features"]
            props = features[id_geo].setdefault("properties", {})
            if wiersze:
                props["id_wydarzen"] = ";".join(w["id"] for w in wiersze)
            if miejsce:
                props["id_miejsca"] = miejsce["id_miejsca"]
            zapisane += 1
        # uMap ships compacted JSON; pretty-printing it roughly triples the file
        sciezka.write_text(
            json.dumps(dane, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
    print(f"mapy: {zapisane} obiektow, {len(wg_sciezki)} plikow (kopie .bak)")
    return True, zapisane


def roczniki(wydarzenia, wykonaj):
    wg_roku = defaultdict(list)
    for w in wydarzenia:
        wg_roku[(w["miasto"], int(w["rok"]))].append(w["id"])

    zmienione = 0
    for miasto, plik in (("PL", "PL_1990-2019.md"), ("DE", "DE_1990-2019.md")):
        sciezka = znajdz_plik(plik)
        if sciezka is None:
            continue
        linie = sciezka.read_text(encoding="utf-8").split("\n")
        glowy = [i for i, l in enumerate(linie) if NAGLOWEK_ROKU.match(l)]
        wstawki = []
        for n, start in enumerate(glowy):
            koniec = glowy[n + 1] if n + 1 < len(glowy) else len(linie)
            rok = int(NAGLOWEK_ROKU.match(linie[start]).group(1))
            ids = wg_roku.get((miasto, rok))
            if not ids:
                continue
            cialo = linie[start + 1:koniec]
            pierwsza = next((i for i, l in enumerate(cialo) if l.strip()), None)
            if pierwsza is None or cialo[pierwsza].strip() != "---":
                continue
            sep = [i for i, l in enumerate(cialo) if l.strip() == "---" and i > pierwsza]
            if not sep:
                continue
            # replace an existing line rather than stacking a second one
            istnieje = next((i for i in range(pierwsza + 1, sep[0])
                             if cialo[i].startswith("id_wydarzen:")), None)
            wpis = "id_wydarzen: " + ";".join(sorted(ids))
            if istnieje is not None:
                wstawki.append(("zamien", start + 1 + istnieje, wpis))
            else:
                wstawki.append(("wstaw", start + 1 + sep[0], wpis))
            zmienione += 1

        if not wykonaj:
            continue
        kopia = sciezka.with_suffix(sciezka.suffix + ".bak")
        if not kopia.exists():
            shutil.copy2(sciezka, kopia)
        for rodzaj, indeks, wpis in sorted(wstawki, key=lambda x: -x[1]):
            if rodzaj == "zamien":
                linie[indeks] = wpis
            else:
                linie.insert(indeks, wpis)
        sciezka.write_text("\n".join(linie), encoding="utf-8")

    print(f"{'roczniki' if wykonaj else '[proba] roczniki'}: "
          f"{zmienione} sekcji rocznych dostaje id_wydarzen")
    return zmienione


def main(wykonaj):
    wydarzenia = wczytaj("wydarzenia.csv")
    miejsca = wczytaj("miejsca.csv")
    ok, _ = mapy(wydarzenia, miejsca, wykonaj)
    if not ok:
        sys.exit(1)
    roczniki(wydarzenia, wykonaj)
    if not wykonaj:
        print("\nto byla proba. uruchom z --wykonaj, zeby zapisac")


if __name__ == "__main__":
    main("--wykonaj" in sys.argv)
