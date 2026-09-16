"""Read the ND articles and pull out the district events.

The press write-ups follow one shape closely enough to parse:

    11 bis 17 Uhr: Familienfest »Bunte Platte« in Hohenschoenhausen,
    Falkenberger Chaussee/..., u.a. mit Michael Grunst und Gesine Loetzsch

-- an hour span, a name, a district, an address, and who spoke. What the
parser cannot settle (which year, which borough when the address alone
says it) it leaves blank and says so, rather than guessing.

Output is a candidate table in exactly the shape of input/dzielnicowe.tsv,
so reviewing means reading it and moving the good rows across. It never
writes that file itself: what enters the event table stays a decision.

Put the articles in input/nd/ as .txt or .md, one file per article, with
the year in the filename ("nd_2018.txt", "nd_1994-04-29.md") or in the
first lines of the text.

Usage: python3 parse_nd.py [katalog]
"""
import re
import sys
from pathlib import Path

from common import write_csv

BASE = Path(__file__).parent
KATALOG = BASE / "input/nd"
WYJSCIE = BASE / "output/dzielnicowe_kandydaci.tsv"

# Berlin's boroughs and the Ortsteile that turn up in these write-ups.
DZIELNICE = [
    "Friedrichshain-Kreuzberg", "Treptow-Köpenick", "Marzahn-Hellersdorf",
    "Charlottenburg-Wilmersdorf", "Tempelhof-Schöneberg", "Steglitz-Zehlendorf",
    "Neu-Hohenschönhausen", "Alt-Hohenschönhausen", "Hohenschönhausen",
    "Prenzlauer Berg", "Friedrichshain", "Charlottenburg", "Reinickendorf",
    "Wilmersdorf", "Lichtenberg", "Schöneberg", "Weißensee", "Weissensee",
    "Hellersdorf", "Kreuzberg", "Neukölln", "Neukoelln", "Köpenick", "Koepenick",
    "Spandau", "Steglitz", "Tempelhof", "Treptow", "Zehlendorf", "Marzahn",
    "Pankow", "Wedding", "Mitte", "Tiergarten", "Buch", "Karlshorst",
    "Biesdorf", "Grunewald", "Dahlem", "Gatow", "Müggelheim",
]
PARTIE = [
    ("Die Linke", ["die linke", "linkspartei", "pds/linke"]),
    ("PDS", ["pds"]),
    ("SPD", ["spd", "jusos", "falken"]),
    ("Grüne", ["grüne", "gruene", "bündnis 90"]),
    ("DKP", ["dkp"]),
    ("DGB", ["dgb", "ver.di", "ig metall"]),
]
# "13 bis 18.30 Uhr:", "ab 13 Uhr:", "11 Uhr -"
GODZINY = re.compile(
    r"(?:^|\s)(?:ab\s+)?(\d{1,2})(?:[.:](\d{2}))?\s*"
    r"(?:bis|–|-|—)\s*(\d{1,2})(?:[.:](\d{2}))?\s*Uhr"
    r"|(?:^|\s)(?:ab\s+)?(\d{1,2})(?:[.:](\d{2}))?\s*Uhr", re.I)


def godzina(h, m):
    return f"{int(h):02d}:{m or '00'}" if h else ""


def czas(linia):
    """-> (od, do). Pierwsze wystapienie w linii; pozniejsze to godziny mowcow."""
    m = GODZINY.search(linia)
    if not m:
        return "", ""
    if m.group(1):
        return godzina(m.group(1), m.group(2)), godzina(m.group(3), m.group(4))
    return godzina(m.group(5), m.group(6)), ""


def rok_z_pliku(sciezka, tekst):
    m = re.search(r"(?:19|20)\d{2}", sciezka.name)
    if m:
        return m.group(0)
    m = re.search(r"(?:19|20)\d{2}", "\n".join(tekst.splitlines()[:5]))
    return m.group(0) if m else ""


def main(katalog=None):
    katalog = Path(katalog or KATALOG)
    pliki = sorted(p for p in katalog.glob("*")
                   if p.suffix.lower() in (".txt", ".md")) if katalog.exists() else []
    if not pliki:
        print(f"brak plikow w {katalog} -- wrzuc artykuly jako .txt lub .md")
        return

    kandydaci, bez_roku = [], set()
    for sciezka in pliki:
        tekst = sciezka.read_text(encoding="utf-8", errors="replace")
        rok = rok_z_pliku(sciezka, tekst)
        # These lists sit under one heading ("Die Linke laedt ein ..."), so
        # most lines never name the party. If the article as a whole points
        # at exactly one, that is the organiser -- flagged as such, because
        # it comes from the heading and not from the line.
        w_pliku = [n for n, slowa in PARTIE
                   if any(re.search(r"\b" + re.escape(x) + r"\b", tekst, re.I)
                          for x in slowa)]
        aktor_pliku = w_pliku[0] if len(w_pliku) == 1 else ""
        if not rok:
            bez_roku.add(sciezka.name)
        for nr, linia in enumerate(tekst.splitlines(), start=1):
            linia = linia.strip()
            if len(linia) < 20 or not re.search(r"\bUhr\b", linia, re.I):
                continue
            od, do = czas(linia)
            if not od:
                continue

            # Everything after the first "Uhr:" (or "Uhr -") is the event.
            reszta = re.split(r"Uhr\s*[:\-–]\s*", linia, maxsplit=1, flags=re.I)
            reszta = reszta[1] if len(reszta) > 1 else linia
            osoby_m = re.search(r"\b(?:u\.\s*a\.\s*)?mit\s+(.*)$", reszta, re.I)
            osoby = ""
            if osoby_m:
                osoby = re.sub(r"\s*\([^)]*\)", "", osoby_m.group(1))
                osoby = re.sub(r"\s+und\s+|\s*,\s*", "; ", osoby).strip(" ;")
                reszta = reszta[:osoby_m.start()].rstrip(" ,")

            dzielnica = next((d for d in DZIELNICE if d.lower() in linia.lower()), "")
            # Whole words only: "Falkenberger Chaussee" is a street, and a
            # substring test read it as the Falken and filed the festival
            # under the SPD.
            aktor = next((nazwa for nazwa, slowa in PARTIE
                          if any(re.search(r"\b" + re.escape(s) + r"\b", linia, re.I)
                                 for s in slowa)), "")

            # The name is what comes before the address; "in <Bezirk>" is a
            # location, not part of the name.
            nazwa = re.split(r"\s*,\s*", reszta, maxsplit=1)[0]
            nazwa = re.sub(r"\s+in\s+(?:" + "|".join(re.escape(d) for d in DZIELNICE)
                           + r")\b", "", nazwa, flags=re.I).strip(" .,")
            miejsce = reszta[len(re.split(r"\s*,\s*", reszta, maxsplit=1)[0]):].strip(" ,")

            z_naglowka = False
            if not aktor and aktor_pliku:
                aktor, z_naglowka = aktor_pliku, True
            braki = [p for p, v in (("rok", rok), ("dzielnica", dzielnica),
                                    ("aktor", aktor)) if not v]
            if z_naglowka and not braki:
                braki = ["aktor z naglowka, nie z linii"]
            kandydaci.append({
                "rok": rok, "miasto": "DE", "dzielnica": dzielnica, "aktor": aktor,
                "nazwa": nazwa, "godzina_od": od, "godzina_do": do,
                "miejsce": miejsce, "osoby": osoby, "seria": "",
                "pewnosc": "pewna" if not braki else "do uzupelnienia: " + ", ".join(braki),
                "zrodlo": "ND", "odniesienie": f"{sciezka.name}:{nr}",
            })

    kolumny = ["rok", "miasto", "dzielnica", "aktor", "nazwa", "godzina_od",
               "godzina_do", "miejsce", "osoby", "seria", "pewnosc", "zrodlo",
               "odniesienie"]
    WYJSCIE.parent.mkdir(parents=True, exist_ok=True)
    with WYJSCIE.open("w", encoding="utf-8") as f:
        f.write("# Kandydaci wyciagnieci z artykulow w input/nd/. Przejrzyj,\n"
                "# uzupelnij kolumne pewnosc i przenies dobre wiersze do\n"
                "# input/dzielnicowe.tsv (kolumny sie zgadzaja, bez odniesienia).\n")
        f.write("\t".join(kolumny) + "\n")
        for k in kandydaci:
            f.write("\t".join(str(k[c]) for c in kolumny) + "\n")

    pelne = sum(1 for k in kandydaci if k["pewnosc"] == "pewna")
    print(f"pliki: {len(pliki)}  -> kandydatow: {len(kandydaci)} "
          f"({pelne} kompletnych, {len(kandydaci) - pelne} do uzupelnienia)")
    for nazwa in sorted(bez_roku):
        print(f"  UWAGA: {nazwa} -- nie znalazlem roku ani w nazwie pliku, ani w tekscie")
    print(f"{WYJSCIE.relative_to(BASE)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
