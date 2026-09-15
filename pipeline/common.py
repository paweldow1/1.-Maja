import csv
import math
import re
import unicodedata
from pathlib import Path

from config.layers import (
    ACTOR_KEYWORDS_DE, ACTOR_KEYWORDS_PL, CITY_CODE, DROP_FIELD_PREFIXES,
    DROP_FIELDS, FIELD_MAP, FROM_NAME, LAYER_META, LAYERS_IGNORE,
    LAYERS_MIEJSCA, OBIEKTY_MIEJSCA, TYP_SLOWA, WARSTWY_ID_Z_NAZWY,
)

YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def parse_years(text):
    """Extract, dedupe, sort 4-digit years from a string. Empty list if none."""
    if not text:
        return []
    years = {int(y) for y in YEAR_RE.findall(str(text))}
    return sorted(years)


def slugify_actor(name):
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^A-Za-z0-9]+", "-", n).strip("-")
    return n


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def line_length_m(coords):
    total = 0.0
    for (lon1, lat1, *_), (lon2, lat2, *_) in zip(coords, coords[1:]):
        total += haversine_m(lon1, lat1, lon2, lat2)
    return total


def guess_actor(name, city):
    keywords = ACTOR_KEYWORDS_PL if city == "warszawa" else ACTOR_KEYWORDS_DE
    if not name:
        return ""
    for kw in keywords:
        if kw.lower() in name.lower():
            return kw
    return ""


def typ_z_nazwy(name):
    """Type read off the object's name, or '' when the name says nothing."""
    if not name:
        return ""
    low = name.lower()
    for typ, slowa in TYP_SLOWA:
        if any(s in low for s in slowa):
            return typ
    return ""


def typ_z_geometrii(geom_type):
    return "demonstracja" if geom_type in ("LineString", "MultiLineString") else "wiec"


def start_end_points(geometry):
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point":
        return tuple(coords[:2]), tuple(coords[:2])
    if gtype in ("LineString",):
        return tuple(coords[0][:2]), tuple(coords[-1][:2])
    if gtype == "MultiLineString":
        flat = [pt for seg in coords for pt in seg]
        return tuple(flat[0][:2]), tuple(flat[-1][:2])
    return (None, None), (None, None)


def route_length(geometry):
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "LineString":
        return line_length_m(coords)
    if gtype == "MultiLineString":
        return sum(line_length_m(seg) for seg in coords)
    return None


WYDARZENIA_COLUMNS = [
    "id", "rok", "rok_zrodlo", "miasto", "warstwa", "typ", "typ_zrodlo", "aktor",
    "aktor_zgadniety", "charakter", "nazwa", "opis", "haslo",
    "frekwencja_mapa", "geom_typ", "dlugosc_trasy_m", "punkt_start",
    "punkt_koniec", "id_geo", "plik_zrodlowy", "postcovid",
    "wymaga_weryfikacji",
]

MIEJSCA_COLUMNS = [
    "id_miejsca", "nazwa", "miasto", "wspolrzedne", "lata_uzycia", "opis",
    "zrodlo",
]


def build_event_rows(layer_name, features, city, plik_zrodlowy, id_counters,
                     bez_lat_rows, typ_wymuszony=None, meta=None):
    typ_default, aktor_default, charakter = meta or LAYER_META[city][layer_name]
    field_map = FIELD_MAP[city]
    city_code = CITY_CODE[city]
    rows = []

    for id_geo, feat in enumerate(features):
        props = feat.get("properties", {})
        geometry = feat.get("geometry", {})
        name = props.get("name", "")

        lata_raw = props.get("Lata") or props.get("Rok")
        rok_zrodlo = "Lata" if props.get("Lata") else ("Rok" if props.get("Rok") else None)
        years = parse_years(lata_raw)
        if not years:
            years = parse_years(name)
            if years:
                rok_zrodlo = "name"

        if not years:
            bez_lat_rows.append({
                "warstwa": layer_name, "miasto": city_code, "nazwa": name,
                "id_geo": id_geo, "plik_zrodlowy": plik_zrodlowy,
            })
            continue

        aktor_zgadniety = False
        if aktor_default == FROM_NAME:
            aktor = guess_actor(name, city)
            aktor_zgadniety = True
        else:
            aktor = aktor_default

        nazwany_typ = typ_z_nazwy(name)
        if typ_wymuszony:
            typ, typ_zrodlo = typ_wymuszony, "warstwa"
        elif nazwany_typ:
            typ, typ_zrodlo = nazwany_typ, "name"
        elif typ_default != FROM_NAME:
            typ, typ_zrodlo = typ_default, "warstwa"
        else:
            typ, typ_zrodlo = typ_z_geometrii(geometry.get("type")), "geometria"

        wymaga_weryfikacji = aktor_zgadniety or typ_zrodlo == "geometria" or not aktor

        punkt_start, punkt_koniec = start_end_points(geometry)
        dlugosc = route_length(geometry)

        for rok in years:
            slug = slugify_actor(aktor) or "NIEZNANY"
            if layer_name in WARSTWY_ID_Z_NAZWY:
                # The layer groups unlike things, so the name is what
                # distinguishes them -- without it these collapse into one id
                # per year and come out as _a/_b.
                z_nazwy = slugify_actor(re.sub(r"(?:19|20)\d{2}", "", name or ""))
                if z_nazwy:
                    slug = f"{slug}-{z_nazwy[:40]}" if aktor else z_nazwy[:40]
            base_id = f"{rok}_{city_code}_{typ}_{slug}"
            n = id_counters.get(base_id, 0)
            id_counters[base_id] = n + 1
            event_id = base_id if n == 0 else f"{base_id}_{chr(ord('a') + n - 1)}"

            rows.append({
                "id": event_id,
                "rok": rok,
                "rok_zrodlo": rok_zrodlo or "reczne",
                "miasto": city_code,
                "warstwa": layer_name,
                "typ": typ,
                "typ_zrodlo": typ_zrodlo,
                "aktor": aktor,
                "aktor_zgadniety": aktor_zgadniety,
                "charakter": charakter,
                "nazwa": name,
                "opis": props.get("description", ""),
                "haslo": props.get(field_map["haslo"], ""),
                "frekwencja_mapa": props.get(field_map["frekwencja"], ""),
                "geom_typ": geometry.get("type", ""),
                "dlugosc_trasy_m": round(dlugosc, 1) if dlugosc else "",
                "punkt_start": f"{punkt_start[1]},{punkt_start[0]}" if punkt_start[0] is not None else "",
                "punkt_koniec": f"{punkt_koniec[1]},{punkt_koniec[0]}" if punkt_koniec[0] is not None else "",
                "id_geo": id_geo,
                "plik_zrodlowy": plik_zrodlowy,
                "postcovid": props.get("postcovid", ""),
                "wymaga_weryfikacji": wymaga_weryfikacji,
            })

    return rows


def build_miejsce_rows(layer_name, features, city, plik_zrodlowy):
    city_code = CITY_CODE[city]
    rows = []
    for id_geo, feat in enumerate(features):
        props = feat.get("properties", {})
        geometry = feat.get("geometry", {})
        name = props.get("name", "")
        lata_raw = props.get("Lata") or props.get("Rok")
        years = parse_years(lata_raw)
        coords = geometry.get("coordinates")
        if geometry.get("type") == "Point" and coords:
            wsp = f"{coords[1]},{coords[0]}"
        else:
            wsp = ""
        rows.append({
            "id_miejsca": f"{city_code}_{layer_name}_{id_geo}",
            "nazwa": name,
            "miasto": city_code,
            "wspolrzedne": wsp,
            "lata_uzycia": ";".join(str(y) for y in years),
            "opis": props.get("description", ""),
            "zrodlo": plik_zrodlowy,
        })
    return rows


def podziel_obiekty(features, city):
    """-> (wydarzenia, obiekty_stale). Fixed objects are named in config."""
    stale_nazwy = OBIEKTY_MIEJSCA.get(city, set())
    wydarzenia, stale = [], []
    for f in features:
        nazwa = (f.get("properties", {}).get("name") or "").strip()
        (stale if nazwa in stale_nazwy else wydarzenia).append(f)
    return wydarzenia, stale


def write_csv(path, rows, columns):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow(r)
