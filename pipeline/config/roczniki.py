"""Key classification for the Obsidian rocznik frontmatter.

Three buckets, because the frontmatter mixes three different kinds of thing:

  KONTEKST  year-level facts (one value per year, not an event)
  AKTOR     structured, attributable to an actor -> joinable with the maps
  PROZA     narrative descriptions -> kept verbatim for manual case coding

Anything not listed here lands in klucze_nieznane.csv rather than being
dropped silently.
"""

# Typos in the source material -> canonical key (instrukcja_v2.md sec. 8).
KEY_ALIASES = {
    "Hasl_DGBBB": "Haslo_DGBBB",
    "Hasł_DGBBB": "Hasło_DGBBB",
    "rok": "Rok",
    "Trasa_OTV": "Trasa_ÖTV",
    "Vorabendveranstlatung": "Vorabendveranstaltung",
}

# Obsidian bookkeeping, not data. id_wydarzen is written back by step 7, so
# it is ours rather than the source's and must not be reported as unknown.
DROP_KEYS = {"cssclasses", "aliases", "locations", "id_wydarzen"}

KONTEKST = {
    "warszawa": {"Temat", "Związek", "Rok", "Źródła", "Źródło", "Kontekst"},
    "berlin": {"Rok", "Główna demonstracja", "Centralne_BB", "FrekwencjaNiemcy"},
}

# key -> (aktor, pole). aktor None means "the year's main union" (PL, where the
# organiser sits in the *value* of Zwiazek, not in the key name).
AKTOR_KEYS = {
    "warszawa": {
        "Trasa": (None, "trasa"),
        "Trasa_alt": (None, "trasa_alt"),
        "Frekwencja": (None, "frekwencja"),
        "Hasło": (None, "haslo"),
        "Hasła": (None, "haslo"),
        "Hasła_OPZZ": ("OPZZ", "haslo"),
        "Hasła_PPS": ("PPS", "haslo"),
        "Hasła_SLD": ("SLD", "haslo"),
        "Hasła_Razem": ("Razem", "haslo"),
        "Hasła_radykalne": (None, "haslo_radykalne"),
        "Hasła_kontra": (None, "haslo_kontra"),
    },
    # Berlin: the organiser is in the KEY NAME suffix (instrukcja sec. 8).
    "berlin": {
        "TrasaDGB": ("DGB", "trasa"),
        "FrekwencjaDGB": ("DGB", "frekwencja"),
        "FrekwencjaMainDGB": ("DGB", "frekwencja"),
        "Hasło_DGB": ("DGB", "haslo"),
        "Hasła_DGB": ("DGB", "haslo"),
        "Apel_DGB": ("DGB", "apel"),
        "MuzykaDGB": ("DGB", "muzyka"),
        "Hasło_DGBBB": ("DGB Berlin-Brandenburg", "haslo"),
        "Apel_DGB_BB": ("DGB Berlin-Brandenburg", "apel"),
        "Trasa_revo": ("R1M", "trasa"),
        "TrasaRevo": ("R1M", "trasa"),
        "TrasaOstRevo": ("R1M", "trasa_ost"),
        "FrekwencjaRevo": ("R1M", "frekwencja"),
        "Hasło_revo": ("R1M", "haslo"),
        "Uczestnicy_revo": ("R1M", "uczestnicy"),
        "Apel_radical_left": ("R1M", "apel"),
        "TrasaIGM": ("IG Metall", "trasa"),
        "Trasa_ÖTV": ("ÖTV", "trasa"),
        "Apel_FDGB": ("FDGB", "apel"),
        "Hasła_BKG": ("BKG", "haslo"),
        "Hasła_FDJ": ("FDJ", "haslo"),
        # In Berlin `wiec` is the venue of the central DGB rally ("Lustgarten",
        # "Rotes Rathaus"), not narration -- unlike the Polish key of the same
        # name, which is prose about who spoke.
        "wiec": ("DGB", "miejsce_wiecu"),
    },
}

# Structured but the actor cannot be read off the key -> parsed, flagged.
AKTOR_NIEJASNY = {
    "berlin": {
        "Trasa": "trasa",
        "Trasa_Ost": "trasa",
        "Trasa_zachod": "trasa",
        "Frekwencja": "frekwencja",
        "Hasło_D": "haslo",
    },
}

PROZA = {
    "warszawa": {
        "wiec", "kontra", "kontra_lewica", "Pikniki", "Wydarzenia_alt",
        "Wydarzenia_inne", "Anarchiści", "TVP", "Apel", "Apel_PPS",
        "Apel_SLD", "Apel_alt", "Muzyka", "Organizacje",
        "Komitet organizacyjny", "Aktorzy", "Goście", "Uczestnicy",
        "Miejsca_pamięci", "Brama Straceń", "Siedziba Robotnika",
        "Plac Grzybowski", "Plac Piłsudskiego", "Odwołania_historyczne",
        "Transformacja", "Dziedzictwo_PRL", "Frame_MayDay", "Conflict_MayDay",
        "Przemówienia", "Bieżące_sprawy", "Ważne", "Opis fasady",
        "Znaczenie", "Wspolnie_OPZZ_PPS",
    },
    "berlin": {
        "Festyn", "Wydarzenia", "Wydarzenia_alt", "Upamiętnienia",
        "Organizacje_trad", "Plan_main", "Vorabendveranstaltung", "Nazi",
    },
}

# Known sources -> the short tags used in frekwencja_lista. Matching is by
# earliest occurrence in the parenthetical, so "40000 (ND, za dokumenty
# Kritische Gewerkschaften)" attributes to ND (who counted) rather than to
# the publication that reprinted it. Longer names first so "Berliner Zeitung"
# is not shadowed by "Berliner Kurier" style prefixes.
ZRODLA_SKROTY = {
    "Gazeta Wyborcza": "GW",
    "Życie Warszawy": "ŻW",
    "Dziennik Trybuna": "DT",
    "Neues Deutschland": "ND",
    "Berliner Morgenpost": "BM",
    "Berliner Zeitung": "BZ",
    "Berliner Kurier": "BK",
    "Junge Welt": "JW",
    "Tagesspiegel": "TSG",
    "TagesSpiegel": "TSG",
    "Rzeczpospolita": "RP",
    "Umbruch": "Umbruch",
    "Glückspilz": "Gluckspilz",
    "Gluckspilz": "Gluckspilz",
    "stressfaktor": "stressfaktor",
    "Lewica.pl": "Lewica.pl",
    "Wprost": "Wprost",
    "wp.pl": "wp.pl",
    "RMF": "RMF",
    "PAP": "PAP",
    "taz": "TAZ",
    "TPZ": "TPZ",
    "rbb": "rbb",
    # Trailing '*' = match the stem, for Polish inflection (policja/policja/policji)
    # and for organizatorami/organizatorow.
    "policj*": "policja",
    "Polizei*": "policja",
    "organizator*": "organizatorzy",
    "organiser*": "organizatorzy",
    "DGB": "DGB",
    "ND": "ND",
    "BZ": "BZ",
    "BM": "BM",
    "JW": "JW",
    "GW": "GW",
    "RP": "RP",
    "DT": "DT",
    "TsG": "TSG",
    "Tsg": "TSG",
}

# Canonical actor -> aliases (instrukcja sec. 9).
AKTORZY_KANONICZNI = {
    "IG Metall": ["IGM"],
    "ÖTV": ["OTV"],
    "Die Linke": ["Linkspartei"],
    "Razem": ["Lewica Razem"],
    "DGB Jugend": ["Gewerkschaftsjugend"],
}

AKTORZY_ZNANI = {
    "warszawa": [
        "OPZZ", "Solidarność", "Sierpień 80", "ZZ Kontra", "ZNP",
        "Budowlani", "WZZ", "SLD", "PPS", "SdRP", "UP", "Razem", "ZSMP", "PSL",
        "Zieloni", "PLD", "KRPEiR", "ZKP Proletariat", "Stronnictwo Demokratyczne",
        "Liga Republikańska", "NZS", "KPN", "UPR", "Samoobrona",
        "Młodzież Wszechpolska", "Federacja Anarchistyczna", "Komitet M1",
        "Nurt Lewicy Rewolucyjnej", "Krytyka Polityczna",
    ],
    "berlin": [
        "DGB", "DGB Berlin-Brandenburg", "DGB Jugend", "IG Metall", "ÖTV",
        "HBV", "ver.di", "GEW", "NGG", "IG BAU", "IG BCE", "TRANSNET", "FDGB",
        "DAG", "PDS", "SPD", "Grüne", "Die Linke", "DKP", "MLPD", "Jusos",
        "Falken", "FDJ", "Naturfreunde", "BKG", "R1M", "Antifa", "EuroMayDay",
        "NPD", "FAP", "Junge Nationaldemokraten", "AfD", "Bärgida", "MyFest",
        "MyGruni", "GBBO",
    ],
}
