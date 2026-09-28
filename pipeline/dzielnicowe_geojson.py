"""Warstwa »Festyny dzielnicowe PDS« na mape berlinska.

Dzielnicowki nie maja wspolrzednych -- zrodla podaja adres slowami, a w
tabeli ten sam plac zapisany jest na kilkanascie sposobow ("Schloßplatz
Köpenick", "Frauentog, Altstadt Köpenick", "Schlosshof Köpenick").
input/miejsca_dzielnicowe.tsv sprowadza je do jednego punktu na miejsce;
tutaj laczy sie to z wydarzeniami i sklada w geojson.

Punkt bez wspolrzednych nie trafia do warstwy i nie dostaje zadnego
zastepczego polozenia: festyn postawiony w srodku dzielnicy wyglada na
mapie tak samo jak postawiony pod wlasciwym adresem, a nie jest tym samym.
Brakujace miejsca ida do osobnego pliku, do uzupelnienia.

Usage: python3 dzielnicowe_geojson.py
"""
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from common import write_csv
from dzielnice import WARSTWY, wczytaj_obszary, znajdz

# Ortsteil kontra Bezirk: "Treptow" w tabeli znaczy tez Johannisthal czy
# Alt-Treptow. Kontrola ma wylapywac punkty w zlej dzielnicy, a nie rozne
# poziomy podzialu tej samej.
ALIASY = {
    "hohenschonhausen": {"alt-hohenschonhausen", "neu-hohenschonhausen", "lichtenberg"},
    "treptow": {"alt-treptow", "johannisthal", "plankow", "treptow-kopenick",
                "baumschulenweg", "niederschoneweide"},
    "kopenick": {"treptow-kopenick", "altstadt kopenick"},
    "prenzlauer berg": {"pankow"},
    "hellersdorf": {"marzahn-hellersdorf", "kaulsdorf"},
    "marzahn": {"marzahn-hellersdorf"},
    "buch": {"pankow"},
    "weissensee": {"pankow"},
    "wedding": {"mitte"},
    "kreuzberg": {"friedrichshain-kreuzberg"},
    "friedrichshain": {"friedrichshain-kreuzberg"},
    "lichtenberg": {"lichtenberg"},
    "neukolln": {"neukolln", "gropiusstadt", "britz", "buckow"},
    "spandau": {"spandau"},
    "pankow": {"pankow"},
    "mitte": {"mitte"},
}

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
GAZETER = BASE / "input/miejsca_dzielnicowe.tsv"


def uprosc(t):
    t = (t or "").lower().replace("ß", "ss").replace("ö", "oe") \
        .replace("ä", "ae").replace("ü", "ue")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def wczytaj_gazeter():
    if not GAZETER.exists():
        return []
    linie = [l for l in GAZETER.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    return list(csv.DictReader(linie, delimiter="\t"))


def dopasuj(w, gazeter):
    """-> wpis gazetera albo None. Szuka po miejscu, potem po nazwie."""
    tekst = uprosc(f"{w['miejsce']} {w['nazwa']}")
    for g in gazeter:
        if g["dzielnica"] and uprosc(g["dzielnica"]) != uprosc(w["dzielnica_start"]):
            continue
        if any(re.search(wz.strip(), tekst) for wz in g["wzorzec"].split("|") if wz.strip()):
            return g
    return None


def _dodaj(g, wydarzenia, kosz, braki):
    """Jeden punkt: wszystkie edycje w tym miejscu, lata w opisie."""
    wsp = (g["wspolrzedne"] or "").strip()
    lata = sorted({w["rok"] for w in wydarzenia})
    if not wsp:
        if braki is not None:
            braki.append({
                "klucz": g["klucz"], "dzielnica": g["dzielnica"],
                "wydarzen": len(wydarzenia), "lata": ";".join(lata),
                "przyklad_miejsca": wydarzenia[0]["miejsce"] or wydarzenia[0]["nazwa"],
            })
        return
    try:
        lat, lon = (float(x) for x in wsp.split(","))
    except ValueError:
        if braki is not None:
            braki.append({"klucz": g["klucz"], "dzielnica": g["dzielnica"],
                          "wydarzen": len(wydarzenia), "lata": ";".join(lata),
                          "przyklad_miejsca": f"zle wspolrzedne: {wsp!r}"})
        return

    opis = []
    for w in sorted(wydarzenia, key=lambda x: x["rok"]):
        czas = w["godzina"] + (f"\u2013{w['godzina_do']}" if w["godzina_do"] else "")
        wiersz = f"{w['rok']}"
        if w["data"] and w["data"] != "01.05":
            wiersz += f" ({w['data']})"
        wiersz += f": {w['nazwa']}"
        if czas:
            wiersz += f", {czas}"
        if w["osoby"]:
            wiersz += f" \u2014 {w['osoby']}"
        if w.get("_z_cyklu"):
            wiersz += " [adres z innych edycji cyklu]"
        # Zrodlo i cytat pod kazdym rokiem: klikniety punkt ma pokazywac,
        # skad wiadomo, ze ta edycja sie odbyla.
        if w.get("zrodlo"):
            wiersz += f"\n   \u017ar\u00f3d\u0142o: {w['zrodlo']}"
        if w.get("cytat"):
            wiersz += f"\n   \u201e{w['cytat']}\u201d"
        opis.append(wiersz)
    aktorzy = sorted({w["aktor"] for w in wydarzenia})
    serie = sorted({w["seria"] for w in wydarzenia if w["seria"]})
    kosz.append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "name": (serie[0] if serie else wydarzenia[0]["nazwa"]),
            "Lata": ";".join(lata),
            "description": "\n\n".join(opis),
            "Aktor": ";".join(aktorzy),
            "Dzielnica": g["dzielnica"],
            "Edycji opisanych": len(wydarzenia),
            "Zrodla": "; ".join(sorted({w["zrodlo"] for w in wydarzenia if w.get("zrodlo")})),
            "Precyzja": g["precyzja"] or "adres",
            "Zrodlo punktu": g["zrodlo"],
        },
    })


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wyd = [x for x in csv.DictReader(f) if x["warstwa"] == "Dzielnicowe"]
    gazeter = wczytaj_gazeter()

    wg_miejsca, nierozpoznane = defaultdict(list), []
    dopasowania = {}
    for w in wyd:
        g = dopasuj(w, gazeter)
        dopasowania[id(w)] = g
        if g:
            wg_miejsca[g["klucz"]].append(w)

    # Cykl ma jedno miejsce; edycja, ktorej zrodlo nie podalo adresu, dostaje
    # punkt swojego cyklu. To nie jest zgadywanie -- to ta sama impreza.
    cykl_do_miejsca = {}
    for w in wyd:
        g = dopasowania[id(w)]
        if w["seria"] and g:
            cykl_do_miejsca.setdefault(w["seria"], {}).setdefault(g["klucz"], 0)
            cykl_do_miejsca[w["seria"]][g["klucz"]] += 1
    for w in wyd:
        if dopasowania[id(w)]:
            continue
        kandydaci = cykl_do_miejsca.get(w["seria"], {})
        if kandydaci:
            klucz = max(kandydaci, key=kandydaci.get)
            wg_miejsca[klucz].append(w)
            w["_z_cyklu"] = "TRUE"
        else:
            nierozpoznane.append(w)

    # Dwie warstwy, nie jedna: ten sam plac bywa miejscem imprezy PDS i SPD
    # (Schlossplatz w Köpenick 1994), a wrzucone razem daja jeden punkt z
    # trzema aktorami, ktory nie jest juz cyklem PDS.
    cechy, cechy_inne, braki = [], [], []
    for g in gazeter:
        wszystkie = wg_miejsca.get(g["klucz"], [])
        if not wszystkie:
            continue
        for linia, kosz in (("PDS/Die Linke", cechy), ("inne", cechy_inne)):
            wydarzenia = [w for w in wszystkie
                          if (w["aktor_linia"] == "PDS/Die Linke") == (linia == "PDS/Die Linke")]
            if not wydarzenia:
                continue
            _dodaj(g, wydarzenia, kosz, braki if linia == "PDS/Die Linke" else None)
    _ = None
    if False:
        wydarzenia = []
    # Kazdy punkt musi wpasc w wielokat swojej dzielnicy. To jedyna kontrola,
    # jaka mam na wspolrzedne rozpoznane z nazwy miejsca, i wylapala trzy
    # bledy przy pierwszym przebiegu.
    ALIASY_N = {uprosc(k): v for k, v in ALIASY.items()}
    obszary = wczytaj_obszary(*WARSTWY["DE"])
    niezgodne = []
    for c in cechy + cechy_inne:
        lon, lat = c["geometry"]["coordinates"]
        dekl = uprosc(c["properties"]["Dzielnica"])
        ot, bez = znajdz(lon, lat, obszary)
        trafione = {uprosc(ot), uprosc(bez)}
        if not ot:
            niezgodne.append((c["properties"]["name"], dekl, "poza wielokatami"))
        # Alt-/Neu- i Ortsteil wewnatrz Bezirku to ta sama dzielnica, wiec
        # zawieranie sie nazw liczy sie jako zgodnosc; ALIASY pokrywaja
        # przypadki, gdzie nazwy nie maja ze soba nic wspolnego (Johannisthal
        # w Treptow, Gropiusstadt w Neukölln).
        elif not (any(dekl in t or t in dekl for t in trafione if t)
                  or trafione & {uprosc(a) for a in ALIASY_N.get(dekl, set())}):
            niezgodne.append((c["properties"]["name"], dekl, f"{ot} / {bez}"))

    for nazwa_w, zbior, plik in (
            ("Festyny dzielnicowe PDS", cechy, "dzielnicowe.geojson"),
            ("Festyny dzielnicowe -- inni i nieustaleni organizatorzy", cechy_inne,
             "dzielnicowe_inne.geojson")):
        (OUT_DIR / plik).write_text(json.dumps(
            {"type": "FeatureCollection", "name": nazwa_w,
             "features": sorted(zbior, key=lambda c: c["properties"]["name"])},
            ensure_ascii=False, indent=1), encoding="utf-8")

    write_csv(OUT_DIR / "dzielnicowe_bez_wspolrzednych.csv", braki,
              ["klucz", "dzielnica", "wydarzen", "lata", "przyklad_miejsca"])

    z_punktem = sum(c["properties"]["Edycji opisanych"] for c in cechy)
    print(f"dzielnicowe.geojson: {len(cechy)} punktow PDS/Linke, {z_punktem} edycji")
    print(f"dzielnicowe_inne.geojson: {len(cechy_inne)} punktow "
          f"({sum(c['properties']['Edycji opisanych'] for c in cechy_inne)} edycji "
          f"-- SPD i inni)")
    print(f"  kontrola dzielnica: {len(cechy) + len(cechy_inne) - len(niezgodne)}"
          f"/{len(cechy) + len(cechy_inne)} punktow "
          f"w swojej dzielnicy")
    for nazwa, dekl, gdzie in niezgodne:
        print(f"    BLAD: {nazwa[:44]} deklarowana {dekl} -> lezy w {gdzie}")
    print(f"  bez wspolrzednych: {len(braki)} miejsc, "
          f"{sum(b['wydarzen'] for b in braki)} edycji")
    if nierozpoznane:
        print(f"  bez adresu i bez cyklu: {len(nierozpoznane)}")
        for w in nierozpoznane[:8]:
            print(f"    {w['rok']} {w['dzielnica_start']}: "
                  f"{(w['miejsce'] or w['nazwa'])[:60]}")


if __name__ == "__main__":
    main()
