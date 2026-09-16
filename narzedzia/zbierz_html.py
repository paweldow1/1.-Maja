"""Zetnij zapisane strony HTML do jednego malego pliku tekstowego.

Strona zapisana z przegladarki wazy megabajty, bo niesie CSS, skrypty i
obrazki w base64. Sam tekst artykulu to zwykle kilka kilobajtow. Ten skrypt
przechodzi katalog (razem z podkatalogami), wyciaga z kazdego .html sam
tekst i sklada wszystko w jeden plik -- zachowujac sciezke kazdego pliku,
bo rok czesto stoi wlasnie w nazwie folderu.

Nie wymaga niczego poza Pythonem 3. Nie rusza plikow zrodlowych.

    python3 zbierz_html.py <katalog_z_artykulami> [plik_wyjsciowy]

Domyslnie zapisuje do artykuly.txt obok skryptu. Jesli wynik wyjdzie duzy,
dodaj --skrot: zostana tylko fragmenty mowiace o godzinach i festynach,
z linijka kontekstu z obu stron.
"""
import html as html_mod
import json
import re
import sys
from pathlib import Path

ISTOTNE = re.compile(r"\bUhr\b|\w*[Ff]est\b|Kundgebung|Demonstration|Markt am|"
                     r"\b1\.\s*Mai\b|Maifeier|Aufzug|Umzug", re.I)


# Strony takie jak Facebook nie maja tresci w HTML-u -- maja szkielet, a
# posty siedza w blokach <script type="application/json">. Wyciecie skryptow
# razem z nimi zostawia sama nawigacje.
SKRYPT_JSON = re.compile(
    r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', re.S | re.I)
# Daty przepuszczamy bez wzgledu na dlugosc i w kolejnosci wystapienia:
# w zrzucie wyszukiwarki kazdy post ma wlasny rok, a data stoi zaraz obok
# tresci. Odcieta data zostawilaby posty z roznych lat bez rozroznienia.
DATA = re.compile(r"\b\d{1,2}[ .]\s*(?:sty|lut|mar|kwi|maj|cze|lip|sie|wrz|paź|paz|lis|gru|"
                  r"Jan|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)"
                  r"[a-zA-ZäöüÄÖÜżźćńółęąś]*\s+((?:19|20)\d{2})\b"
                  r"|\b\d{1,2}\.\d{1,2}\.((?:19|20)\d{2})\b")
# Co uznajemy za zdanie, a nie za identyfikator albo kawalek kodu.
ZDANIE = re.compile(r"[A-Za-zÄÖÜäöüßĄĆĘŁŃÓŚŹŻąćęłńóśźż]{3}.*\s.*"
                    r"[A-Za-zÄÖÜäöüßĄĆĘŁŃÓŚŹŻąćęłńóśźż]")


def _zbierz_napisy(obiekt, out):
    """Rekurencyjnie: wszystkie napisy z rozpakowanego JSON-a."""
    if isinstance(obiekt, str):
        out.append(obiekt)
    elif isinstance(obiekt, dict):
        for v in obiekt.values():
            _zbierz_napisy(v, out)
    elif isinstance(obiekt, list):
        for v in obiekt:
            _zbierz_napisy(v, out)


def tekst_z_json(surowy):
    """Zdania z blokow <script type="application/json">, bez powtorzen."""
    widziane, wynik = set(), []
    for blok in SKRYPT_JSON.findall(surowy):
        try:
            dane = json.loads(blok)
        except (ValueError, RecursionError):
            continue
        napisy = []
        try:
            _zbierz_napisy(dane, napisy)
        except RecursionError:
            continue
        for n in napisy:
            n = html_mod.unescape(n).strip()
            # Za krotkie to etykiety, za dlugie to zrzuty konfiguracji;
            # bez spacji i bez liter to identyfikatory.
            if n in widziane or len(n) > 1200:
                continue
            if n.startswith(("http", "{", "[", "<")) or "/" in n[:12]:
                continue
            if not DATA.search(n) and (len(n) < 25 or not ZDANIE.match(n)):
                continue
            widziane.add(n)
            wynik.append(n)
    return wynik


def tekst_z_html(surowy):
    z_json = tekst_z_json(surowy)
    surowy = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", surowy)
    surowy = re.sub(r"(?s)<!--.*?-->", " ", surowy)
    surowy = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h[1-6]|/section|/article)\b[^>]*>",
                    "\n", surowy)
    surowy = re.sub(r"<[^>]+>", " ", surowy)
    surowy = html_mod.unescape(surowy)
    surowy = re.sub(r"[ \t\xa0]+", " ", surowy)
    linie = [l.strip() for l in surowy.splitlines()]
    widoczne = [l for l in linie if l]
    if z_json:
        widoczne += ["--- tresc z blokow JSON ---"] + z_json
    return "\n".join(widoczne)


def skroc(tekst):
    """Zostaw tylko to, co mowi o wydarzeniach, z linijka kontekstu."""
    linie = tekst.splitlines()
    trzymaj = set()
    for i, l in enumerate(linie):
        if ISTOTNE.search(l):
            trzymaj.update(range(max(0, i - 1), min(len(linie), i + 2)))
    return "\n".join(linie[i] for i in sorted(trzymaj))


def main(argv):
    argv = [a for a in argv if a != "--skrot"]
    tylko_istotne = len(argv) != len(sys.argv[1:])
    if not argv:
        print(__doc__)
        return 1

    katalog = Path(argv[0]).expanduser()
    if not katalog.is_dir():
        print(f"nie ma takiego katalogu: {katalog}")
        return 1
    wyjscie = Path(argv[1]).expanduser() if len(argv) > 1 else Path("artykuly.txt")

    pliki = sorted(p for p in katalog.rglob("*")
                   if p.is_file() and p.suffix.lower() in (".html", ".htm", ".mhtml"))
    if not pliki:
        print(f"nie znalazlem zadnego .html w {katalog}")
        return 1

    czesci, puste, wejscie_bajtow = [], [], 0
    for p in pliki:
        wejscie_bajtow += p.stat().st_size
        try:
            surowy = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            puste.append(f"{p} ({e})")
            continue
        tekst = tekst_z_html(surowy)
        if tylko_istotne:
            tekst = skroc(tekst)
        if not tekst.strip():
            puste.append(str(p.relative_to(katalog)))
            continue
        # Sciezka wzgledna, zeby po drugiej stronie dalo sie odczytac rok
        # z nazwy folderu.
        czesci.append(f"=== PLIK: {p.relative_to(katalog).as_posix()} ===\n{tekst}")

    wyjscie.parent.mkdir(parents=True, exist_ok=True)
    wyjscie.write_text("\n\n".join(czesci), encoding="utf-8")
    rozmiar = wyjscie.stat().st_size

    def mb(n):
        return f"{n / 1048576:.1f} MB"

    print(f"plikow HTML: {len(pliki)}  ({mb(wejscie_bajtow)})")
    print(f"zapisane do: {wyjscie.resolve()}  ({mb(rozmiar)})")
    if puste:
        print(f"bez tekstu ({len(puste)}):")
        for s in puste[:10]:
            print(f"  {s}")
        if len(puste) > 10:
            print(f"  ... i jeszcze {len(puste) - 10}")
    if rozmiar > 5 * 1048576 and not tylko_istotne:
        print("\nDuzo tego. Uruchom jeszcze raz z --skrot, zostana same")
        print("fragmenty o godzinach i festynach.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
