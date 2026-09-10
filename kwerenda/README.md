# Kwerenda

Narzędzie do przeszukiwania stron internetowych pod kątem treści i przenoszenia
trafień prosto do **Zotero** — od razu z przypisem bibliograficznym, tagami
i notatką zawierającą cytat z kontekstem.

Powstało pod konkretny warsztat: badanie obchodów 1 maja po 1989 r. na stronach
regionalnych struktur NSZZ „Solidarność” (WordPress, każdy region inny motyw),
ale nie jest zaszyte pod te strony — działa na dowolnym serwisie.

```
python -m kwerenda gui           # interfejs graficzny w przeglądarce
```

---

## Co potrafi

**Wyszukiwanie**
- Zapytania boolowskie: `I` / `LUB` / `NIE`, nawiasy, `"frazy w cudzysłowie"`.
- Sąsiedztwo: `Wałęsa BLISKO/10 msza` (albo `Wałęsa ~10 msza`).
- Pola: `tytuł:pochód`, `tekst:`, `autor:`, `url:`, `tagi:`. Bez przedrostka
  szukamy w **treści** (tytuł + tekst + autor) — sam tag WordPressa czy słowo
  w adresie nie robi jeszcze trafienia; po nie trzeba poprosić wprost
  (`tagi:"1 maja"`, `url:2015`) albo użyć `wszystko:`.
- **Fleksja** — `Żoliborz` łapie *Żoliborza, Żoliborzu, żoliborski*; `święto`
  łapie *święta, świąt, święcie*; `1 maja` łapie *1-go maja*, *1. maja*.
  Trzy tryby: `dokładnie` / `fleksja` (domyślny) / `rdzeń` (łapie też derywaty:
  `praca` → *pracownik*, *pracował*).
- Modyfikatory pojedynczych terminów: `=Solidarność` (bez odmiany),
  `~msza` (wymuś odmianę), `^prac` (rdzeń), `solidarn*` (wildcard).
- Opcjonalne ignorowanie polskich znaków: `Zoliborz` = `Żoliborz`.
- **Podgląd przed startem**: interfejs pokazuje, jakie formy złapie każdy termin,
  i pozwala kliknięciem wykluczyć te, które są dla Ciebie szumem. Można też
  wkleić próbkę tekstu i sprawdzić, czy zapytanie ją przepuszcza.

**Zbieranie materiału**
- Tryb `auto` sam wykrywa, jak dostać się do treści serwisu:
  **REST API WordPressa → mapa strony (sitemap) → kanał RSS → wyszukiwarka HTML → przejście po linkach**.
  Gdy jedna droga zawodzi, schodzi piętro niżej.
- **Wyniki wyszukiwarki serwisu to tylko lista kandydatów.** Każde trafienie jest
  potwierdzane na pełnym tekście artykułu, własnym zapytaniem — bo wbudowane
  wyszukiwarki WP bywają niewiarygodne (na `solidarnosc.mazowsze.pl` samo `?s=`
  losowo przekierowuje, poprawne wyniki dają dopiero jawne `&paged=N`).
- `pelne_przemiatanie: true` całkiem pomija wyszukiwarkę serwisu i przegląda
  całe archiwum — wolniej, ale bez zdawania się na cudzą indeksację.
- **Okna dat**: `okno_dat: "04-25:05-10"` z zakresem lat pobiera tylko to, co
  ukazało się w okolicach 1 maja każdego roku. Przy badaniu jednego święta to
  różnica między setką a dziesiątkami tysięcy stron.

**Metadane i przypis**
- Autor, data, nazwa serwisu, język, wydawca — z JSON-LD (schema.org), OpenGraph,
  `<meta>`, Dublin Core i heurystyk HTML, kaskadowo.
- Daty rozpoznawane po polsku, niemiecku, ukraińsku i angielsku
  (`2 maja 2015`, `1. Mai 2019`, `9 травня 2020`, `May 3, 2001`).
- Klucz cytowania w stylu Better BibTeX: `nowak2015obchody` (z odsuwaniem kolizji).
- Tagi budowane automatycznie z: trafionych terminów, roku publikacji, domeny,
  kategorii i tagów WordPressa oraz Twoich własnych.
- Cytat z kontekstem (KWIC) wokół każdego trafienia, z zaznaczoną formą.

**Eksport**
- **Prosto do otwartego Zotero** (lokalny konektor, port 23119) — rekord ląduje
  w bibliotece z przypisem, tagami i notatką.
- **Zotero Web API** — klucz + numer użytkownika, z wyborem kolekcji.
- **RIS** (najpewniejszy import do Zotero: `KW` → tagi, `N1` → notatka),
  **CSL-JSON**, **BibTeX/Better BibTeX**, **CSV**, **Zotero JSON**.
- **Notatki do Obsidiana** (.zip) z frontmatterem i linkiem `[[@citekey]]`,
  zgodnie z tym, jak działa Better BibTeX.

**Uprzejmość wobec serwerów**
- Odstęp między żądaniami do jednego hosta (z losowym rozrzutem), retry z
  backoffem przy 429/5xx z uwzględnieniem `Retry-After`, respektowanie
  `robots.txt`, `User-Agent` z Twoim kontaktem.
- Strona wymagająca logowania albo blokująca dostęp (401/403) jest **pomijana**
  z jasnym komunikatem. Narzędzie nie omija żadnych zabezpieczeń ani CAPTCH.

**Korpus**
- Każda pobrana strona ląduje w lokalnej bazie SQLite. Kolejne kwerendy można
  puszczać w trybie `korpus` — **bez ani jednego zapytania do cudzego serwera**.
  Materiał zbierasz raz, hipotezy testujesz dowolnie długo.

---

## Instalacja

```bash
pip install -r requirements.txt
```

Albo bez myślenia: `./start.sh` (macOS/Linux) lub dwuklik w `start.bat` (Windows)
— same zbudują środowisko i otworzą interfejs.

## Użycie

### Interfejs graficzny
```bash
python -m kwerenda gui              # otwiera http://127.0.0.1:8765
```
Serwer słucha wyłącznie na `127.0.0.1` — nic nie wychodzi na zewnątrz.

Zakładki: **Kwerenda** (co i gdzie szukać, podgląd fleksji, dziennik na żywo) →
**Wyniki** (tabela z cytatami, edycja przypisu i tagów, zaznaczanie) →
**Eksport** (Zotero i pliki) → **Korpus i przebiegi** → **Ściąga** ze składnią.

### Wiersz poleceń
```bash
# sprawdź, co złapie zapytanie, zanim ruszysz w sieć
python -m kwerenda podglad '"1 maja" I (Żoliborz LUB "Józef Robotnik")' \
       --probka "Na Żoliborzu 1-go maja odprawiono mszę."

# wykonaj kwerendę z pliku i od razu zapisz RIS
python -m kwerenda uruchom presety/solidarnosc-1-maja.yaml --format ris

# wyślij trafienia do otwartego Zotero
python -m kwerenda zotero --przebieg 3

# eksporty i przeglądanie
python -m kwerenda eksport --przebieg 3 --format bibtex
python -m kwerenda przebiegi
python -m kwerenda korpus
```

## Konfiguracja

Zadanie da się zapisać jako YAML/JSON i uruchamiać wsadowo — patrz
`presety/solidarnosc-1-maja.yaml` (opisany komentarzami) i
`presety/korpus-offline.yaml`. W interfejsie te same zadania zapisują się jako
presety w bazie.

## Jak działa fleksja

Nie ma tu słownika ani zewnętrznego analizatora. Ze słowa wyznaczany jest rdzeń
(odcięcie znanej końcówki), a potem budowane wyrażenie regularne:
rdzeń **z obocznościami** (`t`→`ć/ci`, `k`→`c/cz`, `r`→`rz`, `ó`↔`o`, `ą`↔`ę`,
e ruchome) + **zamknięta lista końcówek** fleksyjnych.

Dzięki temu `Gdańsk` łapie *Gdańsku* i *Gdańska*, ale nie *gdakanie*;
`praca` łapie *pracy* i *pracach*, ale nie *prawo*.

Cena: wzorzec bywa nadmiarowy (`maj` przepuści też czasownik *mają*). Dlatego
podgląd w interfejsie pokazuje wszystkie formy, a kliknięcie w formę wyklucza ją
z dopasowania. Jeśli masz zainstalowany `morfeusz2`, funkcja `fleksja.lematyzuj`
z niego skorzysta, ale nie jest do niczego wymagany.

## Czego narzędzie nie robi

- Nie omija zabezpieczeń, CAPTCH ani logowania — publiczne strony, i tyle.
- Nie zakłada, że wszystkie serwisy mają ten sam motyw czy strukturę HTML.
- Nie ufa wynikom cudzej wyszukiwarki bez sprawdzenia treści.

## Testy

```bash
python -m unittest discover -s tests -t .
```

45 testów: fleksja, parser zapytań, ekstrakcja metadanych, adaptery źródeł,
silnik i eksport. Silnik testowany jest end-to-end na **lokalnej atrapie
WordPressa** (`tests/atrapa_wordpressa.py`) — z REST API, paginacją,
wyszukiwarką HTML, sitemapą, RSS i `robots.txt` — więc testy nie wysyłają
żadnego żądania do cudzych serwerów.

## Układ kodu

| plik | rola |
|---|---|
| `fleksja.py` | odmiana polska → wyrażenia regularne |
| `zapytania.py` | parser operatorów, ocena dokumentu, cytaty KWIC |
| `siec.py` | grzeczny klient HTTP (throttling, retry, robots.txt) |
| `ekstrakcja.py` | treść artykułu i metadane bibliograficzne z HTML |
| `zrodla.py` | adaptery: WordPress REST, sitemap, RSS, wyszukiwarka, crawl |
| `silnik.py` | orkiestracja: kandydaci → weryfikacja → trafienia |
| `cytowania.py` | rekord → RIS / CSL-JSON / BibTeX / CSV / Markdown / Zotero |
| `zotero.py` | lokalny konektor i Web API |
| `magazyn.py` | SQLite: korpus, przebiegi, trafienia, presety |
| `serwer.py` + `web/index.html` | interfejs graficzny |
