"""Step 4: parse the Obsidian rocznik frontmatter into joinable CSVs.

Usage: python3 parse_roczniki.py <PL_file.md> <DE_file.md>

The roczniki are one concatenated file per city, each year a
`# {rok}_{PL|DE}.md` heading followed by a YAML frontmatter block.

Three outputs, because the frontmatter mixes three kinds of thing (see
config/roczniki.py): actor-attributable records that can join with the
maps, year-level context, and prose kept for manual case coding.
"""
import re
import sys
from pathlib import Path

import yaml

from common import write_csv
from config.roczniki import (
    AKTORZY_KANONICZNI, AKTORZY_ZNANI, AKTOR_KEYS, AKTOR_NIEJASNY, DROP_KEYS,
    KEY_ALIASES, KONTEKST, PROZA, ZRODLA_SKROTY,
)

OUT_DIR = Path(__file__).parent / "output"
CITY_CODE = {"warszawa": "PL", "berlin": "DE"}
HEADING = re.compile(r"^#\s+(\d{4})_(PL|DE)\.md\s*$")
# Mojibake markers: Baltic letters that never occur in Polish or German, and
# the classic UTF-8-read-as-latin1 sequences.
MOJIBAKE = re.compile("[ŅņĢģĶķĻļŖŗ]"
                      "|Ã[-¿]|â€")
ALIAS_LOOKUP = {a: kanon for kanon, aliasy in AKTORZY_KANONICZNI.items() for a in aliasy}


def split_sections(path):
    """Yield (rok, frontmatter_dict, raw_block) per year section."""
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    heads = [i for i, l in enumerate(lines) if HEADING.match(l)]
    for n, start in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        body = lines[start + 1:end]
        rok = int(HEADING.match(lines[start]).group(1))
        first = next((i for i, l in enumerate(body) if l.strip()), None)
        if first is None or body[first].strip() != "---":
            yield rok, None, "\n".join(body)
            continue
        # The frontmatter ends at the first '---' where the block above it
        # parses as a mapping. Verified unambiguous across both files: no
        # later separator ever yields more keys.
        for sep in [i for i, l in enumerate(body) if l.strip() == "---" and i > first]:
            block = "\n".join(body[first + 1:sep])
            try:
                data = yaml.safe_load(block)
            except yaml.YAMLError:
                continue
            if isinstance(data, dict):
                yield rok, data, block
                break
        else:
            yield rok, None, "\n".join(body)


def split_outside_parens(text):
    """Split into alternating (outside_text, paren_content) pairs.

    Digits inside parentheses are dates and archive signatures, never
    headcounts, so the caller must never read numbers out of them.
    """
    parts, depth, buf, paren = [], 0, [], []
    for ch in text:
        if ch == "(":
            if depth == 0:
                parts.append(("out", "".join(buf)))
                buf = []
            else:
                paren.append(ch)
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
            if depth == 0:
                parts.append(("par", "".join(paren)))
                paren = []
            else:
                paren.append(ch)
        elif depth > 0:
            paren.append(ch)
        else:
            buf.append(ch)
    if buf:
        parts.append(("out", "".join(buf)))
    if paren:
        parts.append(("par", "".join(paren)))
    return parts


def skrot_zrodla(src):
    src = src.strip()
    if not src:
        return ""
    low = src.lower()
    trafienia = []
    for nazwa, tag in ZRODLA_SKROTY.items():
        nazwa = nazwa.strip().lower()
        if nazwa.endswith("*"):
            wzor = r"\b" + re.escape(nazwa[:-1])          # stem, any ending
        else:
            wzor = r"\b" + re.escape(nazwa) + r"\b"       # whole word: DGB not FDGB
        m = re.search(wzor, low)
        if m:
            trafienia.append((m.start(), tag))
    if trafienia:
        # Earliest mention wins: that is who produced the figure, not who
        # reprinted it ("ND, za dokumenty ..." -> ND).
        return min(trafienia)[1]
    akronim = re.search(r"\b([A-ZÄÖÜŹŻ]{2,5}\d*)\b", src)
    if akronim:
        return akronim.group(1)
    return re.sub(r"\s+", "-", src.split(",")[0].strip())[:20]


def parse_frekwencja(value):
    """-> (lista '6000@GW;10000@TPZ', srednia, uwagi).

    Leading dashes are junk (instrukcja sec. 8). One list item can hold
    several readings, and some hold a source with no number at all.
    """
    wpisy, liczby, uwagi = [], [], []
    for item in iter_scalars(value):
        text = str(item).replace(" ", " ").strip()
        if not text:
            continue
        pending = None
        saw_any = False
        for kind, chunk in split_outside_parens(text):
            if kind == "out":
                for m in re.finditer(r"\d[\d\s]*", chunk):
                    if pending is not None:
                        wpisy.append(str(pending))
                        liczby.append(pending)
                    pending = int(re.sub(r"\s+", "", m.group()))
                    saw_any = True
            else:
                tag = skrot_zrodla(chunk)
                if pending is not None:
                    wpisy.append(f"{pending}@{tag}" if tag else str(pending))
                    liczby.append(pending)
                    pending = None
                    saw_any = True
                elif chunk.strip():
                    # No number in front of it, so this is a note ("pochod sie
                    # nie odbyl"), not an attribution -- keep it verbatim.
                    uwagi.append(f"bez liczby: {chunk.strip()[:80]}")
                    saw_any = True
        if pending is not None:
            wpisy.append(str(pending))
            liczby.append(pending)
        elif not saw_any:
            uwagi.append(text[:80])
    srednia = round(sum(liczby) / len(liczby)) if liczby else ""
    return ";".join(wpisy), srednia, "; ".join(uwagi)


def normalizuj_aktora(aktor, miasto, nieznani, rok):
    if not aktor:
        return "", False
    aktor = ALIAS_LOOKUP.get(aktor.strip(), aktor.strip())
    if aktor in AKTORZY_ZNANI[miasto]:
        return aktor, True
    nieznani.append({"aktor": aktor, "miasto": CITY_CODE[miasto], "rok": rok})
    return aktor, False


def iter_scalars(value):
    """Yield non-empty scalars, flattening nested lists."""
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            yield from iter_scalars(v)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            yield f"{k}: {flatten(v)}"
        return
    yield value


def flatten(value):
    return "\n".join(str(v).strip() for v in iter_scalars(value) if str(v).strip())


def main(pl_path, de_path):
    wydarzenia, kontekst_rows, proza_rows = [], [], []
    nieznane_klucze, nieznani_aktorzy, kodowanie = [], [], []

    for path, miasto in ((pl_path, "warszawa"), (de_path, "berlin")):
        kod = CITY_CODE[miasto]
        plik = Path(path).name
        for rok, fm, raw in split_sections(path):
            if fm is None:
                nieznane_klucze.append({
                    "rok": rok, "miasto": kod, "klucz": "(brak frontmatter)",
                    "plik": plik, "probka": raw[:100].replace("\n", " ")})
                continue

            for hit in MOJIBAKE.finditer(raw):
                kodowanie.append({
                    "rok": rok, "miasto": kod, "plik": plik,
                    "kontekst": raw[max(0, hit.start() - 40):hit.start() + 25].replace("\n", " ")})

            # PL keeps the organiser in the *value* of Zwiazek; DE in the key name.
            zwiazek = flatten(fm.get("Związek")) if miasto == "warszawa" else ""
            per_aktor = {}
            kontekst = {"rok": rok, "miasto": kod, "plik": plik}

            for klucz_raw, value in fm.items():
                klucz = KEY_ALIASES.get(str(klucz_raw), str(klucz_raw))
                if klucz in DROP_KEYS:
                    continue
                if klucz in KONTEKST[miasto]:
                    if klucz == "FrekwencjaNiemcy":
                        # National figure -- never Berlin attendance.
                        lista, sr, _ = parse_frekwencja(value)
                        kontekst["frekwencja_niemcy"] = lista
                        kontekst["frekwencja_niemcy_sr"] = sr
                    else:
                        kontekst[klucz] = flatten(value)
                    continue
                if klucz in AKTOR_KEYS[miasto]:
                    aktor, pole = AKTOR_KEYS[miasto][klucz]
                    aktor = aktor if aktor is not None else zwiazek
                    slot = per_aktor.setdefault(aktor, {})
                    # Several source keys feed one field (FrekwencjaDGB and
                    # FrekwencjaMainDGB, Haslo and Hasla, Trasa_revo and
                    # TrasaRevo). Collect them -- assigning would drop all but one.
                    slot.setdefault(pole, []).append(value)
                    slot.setdefault("_klucze", []).append(klucz)
                    continue
                if klucz in AKTOR_NIEJASNY.get(miasto, {}):
                    pole = AKTOR_NIEJASNY[miasto][klucz]
                    slot = per_aktor.setdefault("(nieokreslony)", {})
                    slot.setdefault(pole, []).append(value)
                    slot.setdefault("_klucze", []).append(klucz)
                    continue
                if klucz in PROZA[miasto]:
                    tekst = flatten(value)
                    if tekst:
                        proza_rows.append({
                            "rok": rok, "miasto": kod, "pole": klucz,
                            "tekst": tekst, "plik": plik})
                    continue
                nieznane_klucze.append({
                    "rok": rok, "miasto": kod, "klucz": klucz, "plik": plik,
                    "probka": flatten(value)[:100].replace("\n", " ")})

            kontekst_rows.append(kontekst)

            for aktor, pola in per_aktor.items():
                if aktor == "(nieokreslony)":
                    aktor_norm, znany = "", False
                else:
                    aktor_norm, znany = normalizuj_aktora(aktor, miasto, nieznani_aktorzy, rok)
                lista, srednia, uwagi = parse_frekwencja(pola.get("frekwencja"))
                trasa = flatten(pola.get("trasa")) or flatten(pola.get("trasa_ost"))
                typ = "demonstracja" if trasa else ""
                wydarzenia.append({
                    "rok": rok,
                    "miasto": kod,
                    "aktor": aktor_norm,
                    "aktor_znany": znany,
                    "typ": typ,
                    "trasa": trasa,
                    "trasa_alt": flatten(pola.get("trasa_alt")),
                    "haslo": flatten(pola.get("haslo")),
                    "frekwencja_lista": lista,
                    "frekwencja_sr": srednia,
                    "frekwencja_uwagi": uwagi,
                    "klucze_zrodlowe": ";".join(pola.get("_klucze", [])),
                    "plik_zrodlowy": plik,
                    "wymaga_weryfikacji": (not znany) or (not typ),
                })

    kontekst_cols = sorted({k for row in kontekst_rows for k in row})
    kontekst_cols = ["rok", "miasto"] + [c for c in kontekst_cols if c not in ("rok", "miasto")]

    write_csv(OUT_DIR / "roczniki_wydarzenia.csv", wydarzenia, [
        "rok", "miasto", "aktor", "aktor_znany", "typ", "trasa", "trasa_alt",
        "haslo", "frekwencja_lista", "frekwencja_sr", "frekwencja_uwagi",
        "klucze_zrodlowe", "plik_zrodlowy", "wymaga_weryfikacji"])
    write_csv(OUT_DIR / "roczniki_kontekst.csv", kontekst_rows, kontekst_cols)
    write_csv(OUT_DIR / "roczniki_proza.csv", proza_rows,
              ["rok", "miasto", "pole", "tekst", "plik"])
    write_csv(OUT_DIR / "klucze_nieznane.csv", nieznane_klucze,
              ["rok", "miasto", "klucz", "probka", "plik"])
    write_csv(OUT_DIR / "nieznani_aktorzy.csv", nieznani_aktorzy,
              ["aktor", "miasto", "rok"])
    write_csv(OUT_DIR / "problemy_kodowania.csv", kodowanie,
              ["rok", "miasto", "kontekst", "plik"])

    print(f"roczniki_wydarzenia: {len(wydarzenia)} wierszy")
    print(f"roczniki_kontekst:   {len(kontekst_rows)} lat")
    print(f"roczniki_proza:      {len(proza_rows)} pol prozy")
    print(f"klucze_nieznane:     {len(nieznane_klucze)}")
    print(f"nieznani_aktorzy:    {len(nieznani_aktorzy)}")
    print(f"problemy_kodowania:  {len(kodowanie)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 parse_roczniki.py <PL_file.md> <DE_file.md>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
