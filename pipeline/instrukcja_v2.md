# Tabela wydarzeń + widok POLE — instrukcja wdrożenia (v2)

Wersja poprawiona po obejrzeniu realnych plików map. Zastępuje v1.

Cel: zbudować `wydarzenia.csv` i `miejsca.csv` przez złączenie danych z map uMap
i roczników (Obsidian, YAML frontmatter), a następnie policzyć agregat POLE
(przekrój rok × miasto).

Zakres: Warszawa 1989–2024, Berlin 1987–2019. Ukraina poza tą iteracją.

---

## 0. Czego ta instrukcja NIE obejmuje

Cechy performansu (Międzynarodówka, orkiestra, goździki, mówcy, epizody),
ruchy aktorów, ramy — osobne tabele, kodowane ręcznie przy pisaniu kejsów.
Tu budujemy warstwę morfologiczną i ilościową.

---

## 1. Pliki źródłowe

### Warszawa
`umap_backup_1-maja_warszawa_9_.umap` — **kompletny**, zawiera wszystkie
warstwy z danymi. Jedyne źródło dla Warszawy.

### Berlin — dwa źródła, bo backup jest niekompletny
Backup `umap_backup_1-mai-berlin_aktualna_19_.umap` zawiera pięć warstw
oznaczonych `group: true` (Revolutionäre 1. Mai, DGB, Neo-Nazi May Day,
East German Left, Walpurgisnacht) — to nagłówki folderów, **bez danych**.
Ich zawartość jest w osobnych eksportach:

| plik | warstwa | obiekty |
|---|---|---|
| `1__mai_berlin_aktualna_11_.geojson` | Walpurgisnacht | 43 |
| `1__mai_berlin_aktualna_12_.geojson` | East German Left | 24 |
| `1__mai_berlin_aktualna_13_.geojson` | Neo-Nazi May Day | 44 |
| `1__mai_berlin_aktualna_14_.geojson` | DGB | 125 |
| `1__mai_berlin_aktualna_15_.geojson` | Revolutionäre 1. Mai | 80 |

Warstwę przypisuje **nazwa pliku** (mapping powyżej, na sztywno w konfiguracji).
Pliki te nie mają pola warstwy w properties.

`1__mai_berlin_aktualna_10_.geojson` to konkatenacja powyższych pięciu (316) —
**nie używać**, duplikuje dane.

Z backupu Berlina brać warstwy: `Other events` (24), `Points of Interest` (14),
`Euro May Day` (5), `DAG (1990-1997)` (3), `MyGruni` (4).

### Warstwy do zignorowania
Berlin: `Stadteile` (96), `Berlin Wall` (281)
Warszawa: `Obszary MSI` (144), `Pomniki i tablice upamiętniające` (0)

Lista ignorowanych w pliku konfiguracyjnym, nie na sztywno w kodzie.

---

## 2. Warstwy Warszawy (z backupu)

| warstwa | obiekty | przeznaczenie |
|---|---|---|
| OPZZ | 30 | wydarzenia |
| Lewica radykalna | 20 | wydarzenia |
| Prawicowe kontry i blokady | 18 | wydarzenia |
| PPS | 12 | wydarzenia |
| Festyny | 12 | wydarzenia |
| Right-wing May Day | 10 | wydarzenia |
| Anarchistyczny 1. Maja | 10 | wydarzenia |
| Inne wydarzenia | 5 | wydarzenia |
| Parada Równości | 3 | wydarzenia |
| European Union accession anniversary | 3 | wydarzenia |
| Solidarność | 2 | wydarzenia |
| Punkty na trasie | 10 | **miejsca** |
| Upamiętnienia | 8 | **miejsca** |

---

## 3. Podział: WYDARZENIA vs MIEJSCA

**Kluczowa reguła.** Warstwy punktów stałych nie są wydarzeniami i nie wolno
rozbijać ich po latach — Brama Straceń nie jest osobnym wydarzeniem w każdym
z 12 lat. Rozbijanie produkuje tam śmieci (8 obiektów → 86 wierszy).

Do `miejsca.csv`: `Upamiętnienia`, `Punkty na trasie` (W),
`Points of Interest`, `MyGruni` (B).
Schemat: `id_miejsca` · `nazwa` · `miasto` · `wspolrzedne` · `lata_uzycia`
(lista) · `opis` · `zrodlo`.

Do `wydarzenia.csv`: wszystkie pozostałe warstwy, z rozbiciem po latach.

**Spodziewana wielkość po rozbiciu:** Berlin ~458 wierszy wydarzeń,
Warszawa ~228. Razem ~686.

---

## 4. Pole `Lata` — rozbijanie

`Lata` jest **stringiem**, nie liczbą ani listą. Formaty spotykane:
- `"1999"`
- `"2013, 2014, 2015, 2016, 2017, 2018, 2019"`
- zapisy z myślnikiem w `name` (`2017-2018 Motorrad Demo`) — `Lata` bywa wtedy pełne

Parser: regex `(?:19|20)\d{2}`, deduplikacja, sortowanie.
Jeden obiekt o N latach → N wierszy wydarzeń, każdy z własnym `id`.

**Obiekty bez `Lata`** (ok. 10, głównie DGB i East German Left):
nie odrzucać — wypisać do `bez_lat.csv` do ręcznego uzupełnienia.
Uwaga: `Lata` bywa też w `name` (`1990 Walpurgisnacht`) — użyć jako fallback,
ale oznaczyć `rok_zrodlo = name`.

Istnieje też przestarzałe pole `Rok` (Berlin, 15 obiektów) — duplikat `Lata`,
traktować jako fallback, nie jako osobną informację.

---

## 5. Mapowanie pól map

| kolumna docelowa | Warszawa | Berlin |
|---|---|---|
| frekwencja | `Frekwencja` | `Attendance` |
| hasło | `Hasło` | `Slogan` |
| nazwa | `name` | `name` |
| opis | `description` | `description` |
| lata | `Lata` | `Lata`, fallback `Rok` |
| źródło | — | `Zrodlo` (9+2 obiekty) |
| kategoria | — | `Kategoria` (`DGB_Site`, `R1M_Site`) |

Pola do odrzucenia (śmieci z geokodera i styli): `osm_type`, `osm_id`,
`osm_key`, `osm_value`, `type`, `countrycode`, `country`, `city`, `district`,
`postcode`, `locality`, `street`, `housenumber`, `state`, `extent`,
`_umap_options`, `styleUrl`, `stroke*`, `icon*`, `label-scale`, `markerColor`,
`tooltip`, `imgurl`, `fill*`.

Pole `postcovid` (Boolean, Berlin) zachować — może się przydać.

---

## 6. Konwencja `id`

```
{rok}_{miasto}_{typ}_{aktor}
```
Przykłady: `2001_PL_demonstracja_OPZZ`, `1996_DE_demonstracja_R1M`,
`2015_DE_korso_DGB`, `2001_PL_kwiaty_PPS`

**`typ` i `aktor` wyprowadzać z warstwy**, nie z `name` — warstwa jest źródłem
pewnym, nazwa nie. Mapowanie warstwa → (typ, aktor, charakter) w konfiguracji:

| warstwa | typ domyślny | aktor | charakter |
|---|---|---|---|
| OPZZ | demonstracja | OPZZ | zwiazkowe |
| PPS | demonstracja | PPS | niezwiazkowe |
| Solidarność | demonstracja | Solidarność | zwiazkowe |
| Anarchistyczny 1. Maja | demonstracja | Anarchiści | niezwiazkowe |
| Lewica radykalna | demonstracja | — z `name` | niezwiazkowe |
| Prawicowe kontry i blokady | kontra | — z `name` | kontra |
| Right-wing May Day | demonstracja | — z `name` | niezwiazkowe |
| Festyny | festyn | — z `name` | niezwiazkowe |
| Parada Równości | demonstracja | Parada Równości | niezwiazkowe |
| European Union accession anniversary | festyn | — | niezwiazkowe |
| Inne wydarzenia | — z `name` | — z `name` | niezwiazkowe |
| DGB | — z geometrii/`name` | DGB | zwiazkowe |
| Revolutionäre 1. Mai | demonstracja | R1M | niezwiazkowe |
| Walpurgisnacht | — z `name` | — z `name` | niezwiazkowe |
| Neo-Nazi May Day | demonstracja | — z `name` (NPD, FAP, JN) | kontra |
| East German Left | — z `name` | PDS | niezwiazkowe |
| Euro May Day | demonstracja | EuroMayDay | niezwiazkowe |
| DAG (1990-1997) | demonstracja | DAG | zwiazkowe |
| Other events | — z `name` | — z `name` | niezwiazkowe |

Gdzie „— z `name`" — regex, a wynik do kolumny `aktor_zgadniety` + flaga
`wymaga_weryfikacji = TRUE`. Nie zgadywać po cichu.

Typ z geometrii jako pomoc: `LineString`/`MultiLineString` → trasa
(demonstracja/korso), `Point` → zgromadzenie (wiec/festyn/kwiaty).

Slug aktora: bez spacji i diakrytyków, myślnik jako separator (`Revo-Antifa`).

**Duplikaty `id`:** gdy w jednym roku ta sama warstwa ma kilka obiektów
(np. dwie trasy R1M 1996), dodać sufiks `_a`, `_b` i wypisać do
`duplikaty_id.csv` do ręcznego nazwania.

---

## 7. Schemat `wydarzenia.csv`

| kolumna | opis |
|---|---|
| `id` | wg konwencji |
| `rok` | int, po rozbiciu `Lata` |
| `rok_zrodlo` | `Lata` / `Rok` / `name` / `reczne` |
| `miasto` | `PL` / `DE` |
| `warstwa` | nazwa warstwy źródłowej |
| `typ` | `demonstracja` / `wiec` / `kwiaty` / `festyn` / `koncert` / `korso` / `spotkanie` / `kontra` |
| `aktor` | znormalizowany |
| `aktor_zgadniety` | TRUE/FALSE |
| `charakter` | `zwiazkowe` / `niezwiazkowe` / `kontra` |
| `nazwa` | `name` z mapy |
| `opis` | `description` |
| `haslo` | `Hasło` / `Slogan` |
| `frekwencja_mapa` | `Frekwencja` / `Attendance` |
| `geom_typ` | `LineString` / `Point` / … |
| `dlugosc_trasy_m` | Haversine, tylko dla linii |
| `punkt_start` / `punkt_koniec` | współrzędne (pierwsza/ostatnia) |
| `id_geo` | indeks obiektu w pliku źródłowym |
| `plik_zrodlowy` | nazwa pliku |
| `postcovid` | Boolean, tylko Berlin |
| `wymaga_weryfikacji` | TRUE/FALSE |

Geometrii **nie kopiować** — tylko cechy pochodne.

---

## 8. Parser roczników (krok drugi, po mapach)

Pliki `{rok}_PL.md`, `{rok}_DE.md`, dane w YAML frontmatter.
**Mapowanie kluczy różni się między PL i DE.**

### PL
- trasa: `Trasa`, `Trasa_alt`
- frekwencja: `Frekwencja` (lista wielo­źródłowa)
- organizator: `Związek`, `Organizacje`, `Komitet organizacyjny`
- współorganizatorzy: `Organizacje`, `Aktorzy`, `Goście`
- miejsca: `Miejsca_pamięci`, `Brama Straceń`, `Plac Grzybowski`,
  `Siedziba Robotnika`, `Plac Piłsudskiego`
- inne w polu: `Wydarzenia_alt`, `Pikniki`, `kontra`, `Anarchiści`, `kontra_lewica`

### DE
- trasa: `TrasaDGB`, `Trasa_revo`, `TrasaRevo`, `TrasaOstRevo`, `TrasaIGM`,
  `Trasa_OTV`, `Trasa_ÖTV`, `Trasa_Ost`, `Trasa_zachod`, `Trasa`
- frekwencja: `FrekwencjaDGB`, `FrekwencjaRevo`, `FrekwencjaMainDGB`, `Frekwencja`
- **organizator z sufiksu nazwy klucza** (`TrasaIGM` → IG Metall)
- inne w polu: `Wydarzenia_alt`, `Wydarzenia`, `Festyn`, `Nazi`, `Vorabendveranstlatung`
- kontekst: `Główna demonstracja`, `Centralne_BB`

**Główna pułapka:** w PL organizator siedzi w wartości pola, w DE w nazwie klucza.

### Frekwencja w PL — parsowanie
Zapis niespójny, np.:
```
Frekwencja:
  -     - 6000 (Gazeta Wyborcza)
  -    - 10000 (TPZ)
  - 8000 (Kisieliński w DT 2002)
```
Wyciągnąć liczbę i skrót źródła z nawiasu → `6000@GW;10000@TPZ;8000@DT`,
policzyć średnią do `frekwencja_sr`. Wiodące myślniki to śmieci.

### Aliasy kluczy (literówki w materiale)
`Hasł_DGBBB` → `Hasło_DGBBB`, `rok` → `Rok`, `Trasa_OTV` → `Trasa_ÖTV`,
`Vorabendveranstlatung` → `Vorabendveranstaltung`.

---

## 9. Normalizacja aktorów

Pary do scalenia wykryte w materiale:

| kanoniczna | aliasy |
|---|---|
| IG Metall | IGM |
| ÖTV | OTV |
| Die Linke | Linkspartei |
| Razem | Lewica Razem |
| DGB Jugend | Gewerkschaftsjugend |

**PL związkowi:** OPZZ, Solidarność, Sierpień 80, ZZ Kontra, ZNP, Budowlani, WZZ
**PL partyjni:** SLD, PPS, SdRP, UP, Razem, ZSMP, PSL, Zieloni, PLD, KRPEiR,
ZKP Proletariat, Stronnictwo Demokratyczne
**PL kontra:** Liga Republikańska, NZS, KPN, UPR, Samoobrona, Młodzież Wszechpolska
**PL radykalna lewica:** Federacja Anarchistyczna, Komitet M1,
Nurt Lewicy Rewolucyjnej, Krytyka Polityczna
**DE związkowi:** DGB, DGB Berlin-Brandenburg, DGB Jugend, IG Metall, ÖTV, HBV,
ver.di, GEW, NGG, IG BAU, IG BCE, TRANSNET, FDGB, DAG
**DE partyjni:** PDS, SPD, Grüne, Die Linke, DKP, MLPD, Jusos, Falken, FDJ,
Naturfreunde
**DE radykalna lewica:** BKG, Revolutionäre 1. Mai, Antifa, EuroMayDay
**DE prawica:** NPD, FAP, Junge Nationaldemokraten, AfD, Bärgida
**DE inne:** MyFest, MyGruni, GBBO

Nazwy spoza słownika → `nieznani_aktorzy.csv`, nie odrzucać.

---

## 10. Złączenie z rocznikami

Klucz: `rok + miasto + typ + aktor`.

Output — trzy pliki:
1. `wydarzenia.csv` — złączone
2. `tylko_mapa.csv` — jest na mapie, brak w roczniku
3. `tylko_rocznik.csv` — odwrotnie

Pliki 2 i 3 są **wynikiem sam w sobie** — pokazują luki w obu zbiorach.
Nie traktować jako błędu do naprawienia przez skrypt.

---

## 11. Zapis zwrotny `id` (osobny krok, po weryfikacji)

Po ręcznym sprawdzeniu `wydarzenia.csv`:
- dopisać `id` do `properties` obiektów w plikach map
- dopisać `id_wydarzen` do YAML roczników

**Uwaga techniczna:** pliki `.umap` to skompaktowany JSON. Zapisywać przez
`json.dump(..., separators=(',', ':'))`, inaczej rozmiar rośnie ~3×.
**Backup przed uruchomieniem.**

---

## 12. Agregat POLE

Z `wydarzenia.csv`, grupowanie po `rok + miasto`:

`liczba_wydarzen` · `liczba_zwiazkowych` · `frekwencja_suma` ·
`frekwencja_zwiazkowa` · `udzial_zwiazkowy` · `liczba_aktorow` ·
`aktorzy_nowi` (obecni w N, nieobecni w N-1) · `aktorzy_znikajacy` ·
`trasa_glowna_zmieniona`

Format: jeden wiersz na rok, kolumny PL i DE obok siebie. Szeroki i płaski,
do skanowania wzrokiem. Output: `pole.csv` + `pole.html`.

Dodać kolumnę z linkiem `obsidian://open?vault=Wszystko&file={rok}_{miasto}`.

---

## 13. Kolejność realizacji

1. Parser map: Warszawa (backup) + Berlin (backup + 5 plików warstwowych)
   → `wydarzenia_surowe.csv`, `miejsca.csv`, `bez_lat.csv`, `duplikaty_id.csv`
2. **STOP — obejrzeć output.** Sprawdzić: czy liczby zgadzają się z oczekiwanymi
   (~458 DE, ~228 PL), czy rozbicie `Lata` nie wyprodukowało absurdów,
   czy `id` się nie duplikują masowo.
3. Normalizacja aktorów + flagowanie `wymaga_weryfikacji`
4. Parser roczników
5. Złączenie + raport rozbieżności
6. Agregat POLE
7. Zapis zwrotny `id` (po weryfikacji, z backupem)

---

## 14. Wymagania techniczne

- Python, `pandas`, `pyyaml`
- Każdy krok osobnym skryptem, output pośredni na dysk
- Nie nadpisywać map ani roczników bez backupu
- UTF-8; w DE umlauty i ß, w PL diakrytyki
- W niektórych rocznikach PL uszkodzone kodowanie (`wieŅce` zamiast `wieńce`)
  — zgłosić do `problemy_kodowania.csv`, nie naprawiać automatycznie
