"""Step 4c: the canonical averaged attendance, from index.html.

The repo's chart page already carries one averaged figure per year per
event series, computed from the attendance spreadsheet. Those are the
numbers the analysis uses, so the pipeline reads them rather than
re-deriving its own means: two averaging methods over one source would
disagree quietly and nobody would know which the paper was quoting.

Writes one long table, input/frekwencja_srednie.tsv, which is the unifying
file: rok, miasto, seria, etykieta, grupa, srednia -- no JavaScript, no
index-into-an-array, and a missing year is an absent row rather than a
`null` in the middle of a list.

Usage: python3 parse_srednie.py [sciezka/do/index.html]
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
DOMYSLNY = BASE.parent / "index.html"
WYJSCIE = BASE / "input/frekwencja_srednie.tsv"


def tablica(zrodlo, nazwa):
    """let/const <nazwa> = [ ... ];  ->  list, z null jako None."""
    m = re.search(r"(?:let|const)\s+" + re.escape(nazwa) + r"\s*=\s*(\[.*?\]);",
                  zrodlo, re.S)
    if not m:
        raise SystemExit(f"nie znaleziono tablicy {nazwa}")
    return json.loads(re.sub(r",\s*\]", "]", m.group(1)))


def obiekt_serii(zrodlo, nazwa):
    """const <nazwa> = { klucz: [...], ... };  ->  {klucz: list}."""
    m = re.search(r"const\s+" + re.escape(nazwa) + r"\s*=\s*\{(.*?)\n\};", zrodlo, re.S)
    if not m:
        raise SystemExit(f"nie znaleziono obiektu {nazwa}")
    out = {}
    # A series is either a literal list or a bare name: the chart binds its
    # main series to a separate array by reference ("dgb: berlin,").
    for klucz, tresc in re.findall(r"(\w+)\s*:\s*(\[[^\]]*\]|\w+)", m.group(1)):
        out[klucz] = (json.loads(re.sub(r",\s*\]", "]", tresc))
                      if tresc.startswith("[") else tresc)
    return out


def meta(zrodlo, nazwa):
    """const <nazwa> = [ {key:..., label:..., group:...}, ... ]."""
    m = re.search(r"const\s+" + re.escape(nazwa) + r"\s*=\s*\[(.*?)\n\];", zrodlo, re.S)
    if not m:
        return {}
    out = {}
    for wpis in re.findall(r"\{([^}]*)\}", m.group(1)):
        k = re.search(r"key\s*:\s*'([^']*)'", wpis)
        et = re.search(r"label\s*:\s*'([^']*)'", wpis)
        gr = re.search(r"group\s*:\s*'([^']*)'", wpis)
        if k:
            out[k.group(1)] = (et.group(1) if et else "", gr.group(1) if gr else "")
    return out


def main(sciezka=None):
    zrodlo = Path(sciezka or DOMYSLNY).read_text(encoding="utf-8")
    lata = tablica(zrodlo, "years")

    wiersze, ostrzezenia = [], []
    for miasto, nazwa_serii, nazwa_meta, glowna in (
            ("DE", "berlinSeries", "berlinMeta", "berlin"),
            ("PL", "warsawSeries", "warsawMeta", "warsaw")):
        serie = obiekt_serii(zrodlo, nazwa_serii)
        opisy = meta(zrodlo, nazwa_meta)
        # The chart binds the main series to a separate array by reference,
        # so in the object literal it is just a name, not numbers.
        for klucz, wartosci in list(serie.items()):
            if isinstance(wartosci, str):
                serie[klucz] = tablica(zrodlo, wartosci)
        for klucz, wartosci in serie.items():
            if len(wartosci) != len(lata):
                ostrzezenia.append(
                    f"{miasto} {klucz}: {len(wartosci)} wartosci na {len(lata)} lat "
                    f"-- {'obcinam' if len(wartosci) > len(lata) else 'dopelniam'}")
            etykieta, grupa = opisy.get(klucz, ("", ""))
            for i, rok in enumerate(lata):
                v = wartosci[i] if i < len(wartosci) else None
                if v is None:
                    continue
                wiersze.append({"rok": rok, "miasto": miasto, "seria": klucz,
                                "etykieta": etykieta, "grupa": grupa,
                                "srednia": int(v)})

    wiersze.sort(key=lambda w: (w["miasto"], w["rok"], w["seria"]))
    WYJSCIE.parent.mkdir(parents=True, exist_ok=True)
    with WYJSCIE.open("w", encoding="utf-8") as f:
        f.write("# Srednie frekwencje, wyciagniete z index.html (wykresy w repo).\n"
                "# Zrodlo prawdy dla liczb -- policzone z arkusza, nie liczone tutaj.\n"
                "# Regeneruje: python3 parse_srednie.py\n")
        f.write("rok\tmiasto\tseria\tetykieta\tgrupa\tsrednia\n")
        for w in wiersze:
            f.write(f"{w['rok']}\t{w['miasto']}\t{w['seria']}\t{w['etykieta']}\t"
                    f"{w['grupa']}\t{w['srednia']}\n")

    pl = sum(1 for w in wiersze if w["miasto"] == "PL")
    print(f"frekwencja_srednie.tsv: {len(wiersze)} odczytow "
          f"(PL {pl}, DE {len(wiersze) - pl}), lata {lata[0]}-{lata[-1]}")
    serie_pl = sorted({w["seria"] for w in wiersze if w["miasto"] == "PL"})
    serie_de = sorted({w["seria"] for w in wiersze if w["miasto"] == "DE"})
    print(f"  serie PL ({len(serie_pl)}): {', '.join(serie_pl)}")
    print(f"  serie DE ({len(serie_de)}): {', '.join(serie_de)}")
    for o in ostrzezenia:
        print(f"  UWAGA {o}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
