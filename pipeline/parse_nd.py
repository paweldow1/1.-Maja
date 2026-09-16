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

Put the articles under input/nd/ -- nested folders are fine, the whole
tree is walked. .txt and .md are read directly, .html, .docx and .odt are
unwrapped in-process, and .pdf, .doc and .rtf go through LibreOffice. The
year is taken from the filename ("nd_2018.txt"), and failing that from any
folder on the path, and failing that from the first lines of the text.

Usage: python3 parse_nd.py [katalog]
"""
import html as html_mod
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from pathlib import Path

from common import write_csv

BASE = Path(__file__).parent
KATALOG = BASE / "input/nd"
WYJSCIE = BASE / "output/dzielnicowe_kandydaci.tsv"

PROSTE = {".txt", ".md", ".text"}
ZNACZNIKI = {".html", ".htm", ".xml"}
# Office formats that are really zip archives with one xml inside.
ZIPOWE = {".docx": "word/document.xml", ".odt": "content.xml",
          ".fodt": None, ".epub": None}
PRZEZ_LIBRE = {".pdf", ".doc", ".rtf", ".odf", ".pages"}


def bez_znacznikow(tekst):
    """Tags out, entities decoded, block ends turned into newlines."""
    tekst = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", tekst)
    tekst = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h[1-6]|w:p|/w:p|text:p|/text:p)\b[^>]*>",
                   "\n", tekst)
    tekst = re.sub(r"<[^>]+>", " ", tekst)
    tekst = html_mod.unescape(tekst)
    tekst = re.sub(r"[ \t\xa0]+", " ", tekst)
    return re.sub(r"\n{3,}", "\n\n", tekst)


# Text operators: a literal (string) or a <hex> one, then the operator that
# shows it, plus the ones that move to a new line.
PDF_TEKST = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|"
                       rb"\b(?:TJ|Tj|'|\"|Td|TD|T\*|ET)\b")
PDF_ESCAPE = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
              b"(": b"(", b")": b")", b"\\": b"\\"}


def _pdf_literal(surowy):
    """(...) -> bytes, z odkodowanymi sekwencjami \\n, \\( i \\ooo."""
    out, i, tresc = bytearray(), 0, surowy[1:-1]
    while i < len(tresc):
        z = tresc[i:i + 1]
        if z != b"\\":
            out += z
            i += 1
            continue
        nast = tresc[i + 1:i + 2]
        if nast in PDF_ESCAPE:
            out += PDF_ESCAPE[nast]
            i += 2
        elif nast.isdigit():
            cyfry = tresc[i + 1:i + 4]
            cyfry = cyfry[:len(cyfry) - len(cyfry.lstrip(b"01234567")) or len(cyfry)]
            try:
                out += bytes([int(cyfry, 8) & 0xFF])
            except ValueError:
                pass
            i += 1 + len(cyfry)
        else:
            i += 2
    return bytes(out)


def pdf_tekst(dane):
    """Tekst z PDF-a, stdlib.

    Rozpakowuje strumienie FlateDecode i czyta operatory tekstowe. Dziala na
    PDF-ach z prawdziwym tekstem; skan bez OCR nie ma czego oddac i wyjdzie
    pusty -- o tym parser mowi wprost, zamiast udawac, ze plik byl pusty.
    """
    czesci = []
    for blok in re.findall(rb"stream\r?\n(.*?)endstream", dane, re.S):
        try:
            tresc = zlib.decompress(blok)
        except zlib.error:
            tresc = blok if b"Tj" in blok or b"TJ" in blok else b""
        if not tresc:
            continue
        linia = bytearray()
        for token in PDF_TEKST.findall(tresc):
            if token[:1] == b"(":
                linia += _pdf_literal(token)
            elif token[:1] == b"<":
                hexy = re.sub(rb"\s", b"", token[1:-1])
                if len(hexy) % 2:
                    hexy += b"0"
                try:
                    rozpakowane = bytes.fromhex(hexy.decode("ascii"))
                except ValueError:
                    continue
                # UTF-16BE identity encoding: every other byte is zero.
                if rozpakowane[:2] == b"\xfe\xff" or (
                        len(rozpakowane) > 3 and not any(rozpakowane[0::2])):
                    linia += rozpakowane.decode("utf-16-be", "replace").encode("utf-8")
                else:
                    linia += rozpakowane
            elif token in (b"Td", b"TD", b"T*", b"ET"):
                czesci.append(bytes(linia))
                linia = bytearray()
        czesci.append(bytes(linia))
    tekst = b"\n".join(c for c in czesci if c.strip())
    try:
        return tekst.decode("utf-8")
    except UnicodeDecodeError:
        # Simple fonts are WinAnsi, close enough to latin-1 for the umlauts.
        return tekst.decode("latin-1", "replace")


def przez_libreoffice(sciezka):
    """Last resort for pdf/doc/rtf. Returns '' when it cannot be converted."""
    if not shutil.which("libreoffice"):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "txt:Text",
                 "--outdir", tmp, str(sciezka)],
                capture_output=True, timeout=120, check=False)
        except (subprocess.TimeoutExpired, OSError):
            return ""
        wynik = list(Path(tmp).glob("*.txt"))
        if not wynik:
            return ""
        return wynik[0].read_text(encoding="utf-8", errors="replace")


def tekst_z_pliku(sciezka):
    """-> (tekst, sposob). Pusty tekst znaczy: nie umiem tego przeczytac."""
    rozsz = sciezka.suffix.lower()
    if rozsz in PROSTE:
        return sciezka.read_text(encoding="utf-8", errors="replace"), "tekst"
    if rozsz in ZNACZNIKI:
        return bez_znacznikow(sciezka.read_text(encoding="utf-8", errors="replace")), "html"
    if rozsz in ZIPOWE:
        try:
            with zipfile.ZipFile(sciezka) as z:
                wnetrze = ZIPOWE[rozsz]
                nazwy = [wnetrze] if wnetrze else [
                    n for n in z.namelist() if n.endswith((".xml", ".xhtml", ".html"))]
                czesci = []
                for n in nazwy:
                    try:
                        czesci.append(z.read(n).decode("utf-8", errors="replace"))
                    except KeyError:
                        continue
                if czesci:
                    return bez_znacznikow("\n".join(czesci)), rozsz.lstrip(".")
        except (zipfile.BadZipFile, OSError):
            pass
        return "", ""
    if rozsz == ".pdf":
        tekst = pdf_tekst(sciezka.read_bytes())
        if tekst.strip():
            return tekst, "pdf"
        # LibreOffice is installed but does not run in this sandbox; kept as a
        # fallback for wherever it does.
        return przez_libreoffice(sciezka), "pdf/libreoffice"
    if rozsz in PRZEZ_LIBRE:
        return przez_libreoffice(sciezka), "libreoffice"
    return "", ""

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


def uprosc(tekst):
    """Fold the umlauts away for matching.

    A PDF extracted without its font map gives "Kopenick", and a transcript
    may give "Koepenick"; both have to find Koepenick. Only for comparison --
    what lands in the table is the text as written.
    """
    tekst = (tekst.lower().replace("ß", "ss").replace("ä", "ae")
             .replace("ö", "oe").replace("ü", "ue"))
    tekst = "".join(c for c in unicodedata.normalize("NFKD", tekst)
                    if not unicodedata.combining(c))
    return tekst.replace("oe", "o").replace("ae", "a").replace("ue", "u")


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


def rok_z_pliku(sciezka, tekst, korzen):
    """Nazwa pliku, potem katalogi po drodze, potem pierwsze linie tekstu.

    Katalogi licza sie dlatego, ze archiwum bywa ulozone jako 1994/artykul.pdf
    -- rok stoi wtedy wylacznie w nazwie folderu.
    """
    m = re.search(r"(?:19|20)\d{2}", sciezka.stem)
    if m:
        return m.group(0)
    try:
        czesci = sciezka.relative_to(korzen).parts[:-1]
    except ValueError:
        czesci = ()
    for czesc in reversed(czesci):
        m = re.search(r"(?:19|20)\d{2}", czesc)
        if m:
            return m.group(0)
    m = re.search(r"(?:19|20)\d{2}", "\n".join(tekst.splitlines()[:5]))
    return m.group(0) if m else ""


def main(katalog=None):
    katalog = Path(katalog or KATALOG)
    # The whole tree: the archive is organised one article per folder.
    znane = PROSTE | ZNACZNIKI | set(ZIPOWE) | PRZEZ_LIBRE
    pliki = sorted(p for p in katalog.rglob("*")
                   if p.is_file() and p.suffix.lower() in znane) if katalog.exists() else []
    pominiete = sorted({p.suffix.lower() for p in katalog.rglob("*")
                        if p.is_file() and p.suffix.lower() not in znane}) \
        if katalog.exists() else []
    if not pliki:
        print(f"brak czytelnych plikow w {katalog}")
        if pominiete:
            print(f"  sa za to rozszerzenia, ktorych nie obsluguje: {', '.join(pominiete)}")
        return

    kandydaci, bez_roku, nieczytelne = [], set(), []
    for sciezka in pliki:
        tekst, sposob = tekst_z_pliku(sciezka)
        if not tekst.strip():
            nieczytelne.append(str(sciezka.relative_to(katalog)))
            continue
        rok = rok_z_pliku(sciezka, tekst, katalog)
        # These lists sit under one heading ("Die Linke laedt ein ..."), so
        # most lines never name the party. If the article as a whole points
        # at exactly one, that is the organiser -- flagged as such, because
        # it comes from the heading and not from the line.
        w_pliku = [n for n, slowa in PARTIE
                   if any(re.search(r"\b" + re.escape(x) + r"\b", tekst, re.I)
                          for x in slowa)]
        aktor_pliku = w_pliku[0] if len(w_pliku) == 1 else ""
        if not rok:
            bez_roku.add(str(sciezka.relative_to(katalog)))
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

            linia_prosta = uprosc(linia)
            dzielnica = next((d for d in DZIELNICE
                              if uprosc(d) in linia_prosta), "")
            # Whole words only: "Falkenberger Chaussee" is a street, and a
            # substring test read it as the Falken and filed the festival
            # under the SPD.
            aktor = next((nazwa for nazwa, slowa in PARTIE
                          if any(re.search(r"\b" + re.escape(s) + r"\b", linia, re.I)
                                 for s in slowa)), "")

            # The name is what comes before the address; "in <Bezirk>" is a
            # location, not part of the name.
            nazwa = re.split(r"\s*,\s*", reszta, maxsplit=1)[0]
            # Cut "in <Bezirk>" off the name, matching however it was spelled.
            for d in DZIELNICE:
                m_in = re.search(r"\s+in\s+(\S+)$", nazwa)
                if m_in and uprosc(m_in.group(1).strip(" .,")) == uprosc(d):
                    nazwa = nazwa[:m_in.start()]
                    break
            nazwa = nazwa.strip(" .,")
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
                "zrodlo": "ND",
                "odniesienie": f"{sciezka.relative_to(katalog)}:{nr}",
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
        print(f"  UWAGA: {nazwa} -- brak roku w nazwie, w folderach i w tekscie")
    for nazwa in nieczytelne:
        print(f"  UWAGA: {nazwa} -- nie udalo sie wyciagnac tekstu")
    if pominiete:
        print(f"  rozszerzenia pominiete: {', '.join(pominiete)}")
    print(f"{WYJSCIE.relative_to(BASE)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
