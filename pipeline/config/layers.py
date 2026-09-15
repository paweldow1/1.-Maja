"""Layer classification config for the wydarzenia/miejsca pipeline.

Nothing here is hardcoded into the parser scripts themselves — the parsers
read these tables. Keep this file as the single place to adjust mappings.
"""

FROM_NAME = "__FROM_NAME__"

LAYERS_IGNORE = {
    "warszawa": {"Obszary MSI", "Pomniki i tablice upamiętniające"},
    "berlin": {"Stadteile", "Berlin Wall"},
}

LAYERS_MIEJSCA = {
    "warszawa": {"Punkty na trasie", "Upamiętnienia"},
    "berlin": {"Points of Interest", "MyGruni"},
}

# warstwa -> (typ domyślny, aktor, charakter)
# aktor / typ == FROM_NAME means: derive from `name` via regex, flag
# aktor_zgadniety=True, wymaga_weryfikacji=True.
LAYER_META = {
    "warszawa": {
        "OPZZ": ("demonstracja", "OPZZ", "zwiazkowe"),
        "PPS": ("demonstracja", "PPS", "niezwiazkowe"),
        "Solidarność": ("demonstracja", "Solidarność", "zwiazkowe"),
        "Anarchistyczny 1. Maja": ("demonstracja", "Anarchiści", "niezwiazkowe"),
        "Lewica radykalna": ("demonstracja", FROM_NAME, "niezwiazkowe"),
        "Prawicowe kontry i blokady": ("kontra", FROM_NAME, "kontra"),
        "Right-wing May Day": ("demonstracja", FROM_NAME, "niezwiazkowe"),
        "Festyny": ("festyn", FROM_NAME, "niezwiazkowe"),
        "Parada Równości": ("demonstracja", "Parada Równości", "niezwiazkowe"),
        "European Union accession anniversary": ("festyn", "", "niezwiazkowe"),
        "Inne wydarzenia": (FROM_NAME, FROM_NAME, "niezwiazkowe"),
    },
    "berlin": {
        "DGB": (FROM_NAME, "DGB", "zwiazkowe"),
        "Revolutionäre 1. Mai": ("demonstracja", "R1M", "niezwiazkowe"),
        "Walpurgisnacht": (FROM_NAME, "Walpurgisnacht", "niezwiazkowe"),
        "Neo-Nazi May Day": ("demonstracja", FROM_NAME, "kontra"),
        "East German Left": (FROM_NAME, "PDS", "niezwiazkowe"),
        "Euro May Day": ("demonstracja", "EuroMayDay", "niezwiazkowe"),
        "DAG (1990-1997)": ("demonstracja", "DAG", "zwiazkowe"),
        "Other events": (FROM_NAME, FROM_NAME, "niezwiazkowe"),
    },
}

# Berlin backup contains group:true layer headers with no data; the real
# features live in per-layer geojson exports, matched by filename.
BERLIN_LAYER_FILES = {
    "1__mai_berlin_aktualna_11_.geojson": "Walpurgisnacht",
    "1__mai_berlin_aktualna_12_.geojson": "East German Left",
    "1__mai_berlin_aktualna_13_.geojson": "Neo-Nazi May Day",
    "1__mai_berlin_aktualna_14_.geojson": "DGB",
    "1__mai_berlin_aktualna_15_.geojson": "Revolutionäre 1. Mai",
}
# Never parse this one -- it's a concatenation duplicating the five above.
BERLIN_LAYER_FILES_IGNORE = {"1__mai_berlin_aktualna_10_.geojson"}

FIELD_MAP = {
    "warszawa": {"frekwencja": "Frekwencja", "haslo": "Hasło"},
    "berlin": {"frekwencja": "Attendance", "haslo": "Slogan"},
}

CITY_CODE = {"warszawa": "PL", "berlin": "DE"}

DROP_FIELDS = {
    "osm_type", "osm_id", "osm_key", "osm_value", "type", "countrycode",
    "country", "city", "district", "postcode", "locality", "street",
    "housenumber", "state", "extent", "_umap_options", "styleUrl",
    "label-scale", "markerColor", "tooltip", "imgurl",
}
DROP_FIELD_PREFIXES = ("stroke", "icon", "fill")

# Name evidence for the event type, checked in order: the specific kinds
# first, so "DGB Maifest" reads as a festyn rather than falling through to
# the generic demonstration/rally match. The layer only says who, not what,
# so a clear signal in the name overrides the layer's default type (which
# instrukcja_v2.md sec. 6 calls a "typ domyslny").
TYP_SLOWA = [
    ("kwiaty", ["kwiat", "wieńc", "wieniec", "wieńce", "złożenie kwiat",
                "kranz", "kranzniederlegung", "gedenk", "denkmal", "mahnmal",
                "ehrung", "upamiętnien"]),
    ("korso", ["korso", "motorrad", "skater", "fahrrad", "rowerow"]),
    ("koncert", ["konzert", "koncert", "concert"]),
    ("festyn", ["maifest", "strassenfest", "straßenfest", "kulturfest",
                "stadtteilfest", "bürgerfest", "sommerfest", "myfest",
                "mygruni", "festyn", "piknik", "picnic", "festival",
                "tanz in den mai", "street party", "strassenparty", "-fest",
                " fest", "fest\""]),
    ("spotkanie", ["spotkanie", "treffen", "tag der offenen tür", "diskussion",
                   "gespräch"]),
    ("wiec", ["kundgebung", "wiec", "rally", "versammlung", "auftakt"]),
    ("kontra", ["gegendemo", "gegenkundgebung", "counterdemo", "counter-demo",
                "counterdemonstration", "kontra", "blockade", "blokada",
                "gegenprotest"]),
    ("demonstracja", ["demonstracja", "demonstration", "aufmarsch", "aufzug",
                      "marsch", "pochód", "marsz", "manifest", "demo",
                      "sponti", "spontandemo"]),
]

# Commemoration layers hold acts, not pins: a delegation laying wreaths at
# the Brama Stracen or the Robotnik plaque did so year after year. The place
# stays a single row in miejsca.csv -- it is not twelve places -- while each
# year of use also becomes an upamietnienie event.
WARSTWY_UPAMIETNIENIA = {"Upamiętnienia"}

# Fixed objects sitting inside event layers. Their `Lata` list is the years
# the place was used, so splitting them per year invents an event for every
# year a building stood there. Buildings and venues belong in miejsca.csv;
# things that genuinely recurred (the president's picnic, the Humannplatz
# Maifest, the counter-demo at the basilica) stay events.
OBIEKTY_MIEJSCA = {
    "warszawa": {
        "OPZZ Headquarters",
        "Sejm RP",
        "Siedziba SdRP/SLD",
        "Brama Uniwersytetu Warszawskiego",
        "Park im. Edwarda Rydza-Śmigłego",
    },
    "berlin": {
        "IG Metall HQ",
        "DGB-Haus",
        "DGB Main headquarters (1999-2019)",
        "Haus des Deutschen Verkehrsbunds",
        "ÖTV trade union headquarters",
        "Wallstrasse 61-65 (former HQ of Berlin FDGB and pre-war ADGB)",
        "Mariannenplatz",
        "Viktoriapark",
        "Oranienplatz",
        "Kollwitzplatz",
        "Lausitzer Platz",
        "Lustgarten",
        "Brandenburger Tor",
        "Bergmannstraße",
        "Mauerpark Walpurgisplatz",
    },
}

# Layers where the layer name carries no distinguishing information, so the
# id discriminator is taken from the object's own name instead. Walpurgisnacht
# is the case: the layer is one label over parties, women's marches and riots
# in a dozen different parks, and only the name tells them apart.
WARSTWY_ID_Z_NAZWY = {"Walpurgisnacht", "Other events", "Inne wydarzenia",
                      "Upamiętnienia"}

# Right-wing layers, counted as their own column in POLE. `charakter` alone
# will not do: it marks the Warsaw right-wing march as niezwiazkowe, which
# is true but hides it among everything else that is not a union.
WARSTWY_PRAWICOWE = {"Prawicowe kontry i blokady", "Right-wing May Day",
                     "Neo-Nazi May Day"}

# Known actor keywords for best-effort FROM_NAME guessing (section 9).
ACTOR_KEYWORDS_PL = [
    "OPZZ", "Solidarność", "Sierpień 80", "ZZ Kontra", "ZNP", "Budowlani",
    "WZZ", "SLD", "PPS", "SdRP", "UP", "Razem", "ZSMP", "PSL", "Zieloni",
    "PLD", "KRPEiR", "ZKP Proletariat", "Stronnictwo Demokratyczne",
    "Liga Republikańska", "NZS", "KPN", "UPR", "Samoobrona",
    "Młodzież Wszechpolska", "Federacja Anarchistyczna", "Komitet M1",
    "Nurt Lewicy Rewolucyjnej", "Krytyka Polityczna",
]
ACTOR_KEYWORDS_DE = [
    "DGB", "IG Metall", "IGM", "ÖTV", "OTV", "HBV", "ver.di", "GEW", "NGG",
    "IG BAU", "IG BCE", "TRANSNET", "FDGB", "DAG", "PDS", "SPD", "Grüne",
    "Die Linke", "Linkspartei", "DKP", "MLPD", "Jusos", "Falken", "FDJ",
    "Naturfreunde", "BKG", "Revolutionäre 1. Mai", "Antifa", "EuroMayDay",
    "NPD", "FAP", "Junge Nationaldemokraten", "AfD", "Bärgida", "MyFest",
    "MyGruni", "GBBO",
]

# Layers whose events are the revolutionary May Day, counted separately in
# POLE: the 13:00 march, the evening demonstration and the joint march they
# ran until 1995 are all R1M, whatever the layer they sit in.
WARSTWY_REWOLUCYJNE = {"Revolutionäre 1. Mai"}
