"""Heuristics that turn a uMap feature into a row of the day's scenario (Scenario tab).

The map descriptions are free text in German, Polish, English, Ukrainian and Russian,
often covering several years in one feature. Everything here is best-effort: a row
without a recognisable time is still shown, under "time not given".
"""
import re

YEAR = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")
_HM = r"(?:[01]?\d|2[0-3])[:.][0-5]\d"
_H = r"(?:[01]?\d|2[0-3])"
# "10:00–12:00", "з 10.00 до 12.00", "9.00 bis 13.00", "from 10:00 to 12:00"
RANGE = re.compile(rf"(?<![\d.])({_HM})(?![\d])\s*(?:–|-|—|до|to|bis|do)\s*({_HM})(?![\d.])")
CLOCK = re.compile(rf"(?<![\d.])({_HM})(?![\d]|\.\d)")
# "10 Uhr", "godz. 9", "o godzinie 10", "18h"
HOUR_WORD = re.compile(rf"(?<![\d.])({_H})\s*(?:Uhr|h\b)|(?:godz(?:\.|iny|inie)?|o)\s+({_H})(?![\d:.])", re.I)

# Series whose name already fixes the hour, used when the text gives none.
DEFAULT_TIME = {("berlin", "revo18"): "18:00", ("berlin", "revo13"): "13:00"}
EVE_SERIES = {("berlin", "walpurgis_demo"), ("berlin", "walpurgis_ttbn"), ("berlin", "walpurgis_tanz")}
# Matched against the feature name only: descriptions cite sources like "(taz 30.04.1990)".
EVE_WORDS = re.compile(r"Walpurgis|Vorabend|Tanz in den Mai|Take back the night|Frauendemo", re.I)
# Place names, strict on purpose: better no place than a fragment of a sentence.
_UP_DE, _LO_DE = "A-ZÄÖÜ", "a-zäöüß"
_UP_PL, _LO_PL = "A-ZŁŚŻŹĆÓ", "a-ząćęłńóśźż"
_UP_UA, _LO_UA = "А-ЯІЇЄҐ", "а-яіїєґ"
PLACE = re.compile("|".join([
    # Alexanderplatz, Keithstraße, Karl-Marx-Allee, Mauerpark, Oranienstr.
    rf"\b[{_UP_DE}][{_LO_DE}\-]*(?:straße|strasse|str\.|platz|park|allee|damm|ufer|brücke|markt|garten|tor)\b",
    # Görlitzer Park, Brandenburger Tor, Rotes Rathaus
    rf"\b[{_UP_DE}][{_LO_DE}]+(?:er|es) (?:Park|Platz|Tor|Rathaus|Straße|Strasse)\b",
    # Platz der Republik, Platz des 18. März
    rf"\b(?:Platz|Park) (?:der|des|am) [{_UP_DE}0-9][{_LO_DE}0-9.]*(?: [{_UP_DE}][{_LO_DE}]+)?",
    # plac Zamkowy, rondo de Gaulle'a, ul. Smolna, pomnik Kopernika
    rf"\b(?:plac|pl\.|placu|rondo|ronda|rondzie|ul\.|ulica|ulicy|al\.|aleja|alei|skwer|pomnik\w*)\s+(?:de |im\. )?[{_UP_PL}][{_LO_PL}'’\-]+(?:\s+[{_UP_PL}][{_LO_PL}'’\-]+)?",
    # площа Слави, вулиця Хрещатик, Європейська площа, Майдан Незалежності
    rf"(?:площ\w*|вулиц\w*|вул\.|майдан\w*|бульвар\w*|сквер\w*)\s+[{_UP_UA}][{_LO_UA}'’\-]+",
    rf"\b[{_UP_UA}][{_LO_UA}'’\-]+\s+(?:площ\w*|майдан\w*)",
    rf"\bМайдан\w*(?:\s+Незалежності)?|\bХрещатик\w*",
]))

TYPES = [  # first match wins; the name is checked before the description
    ("mass", re.compile(r"\bMsza|Gottesdienst|nabożeń|liturg|богослуж", re.I)),
    ("blockade", re.compile(r"blo[ck]k?ad|Sitzblock|kontrmanif|counter|Gegen(?:demo|protest)|\bkontra\b", re.I)),
    ("march", re.compile(r"Demo\b|Demonstr|pochód|pochod|marsz|march|\bZug\b|Sponti|Spontan|Korso|Lauf\b|Spaziergang|ход\b|похід|колон|шеств|марш", re.I)),
    ("festival", re.compile(r"fest\b|festyn|festival|Maifest|MyFest|Tanz in den Mai|Party|Rave|piknik|kiermasz|концерт|фестив", re.I)),
    ("rally", re.compile(r"Kundgebung|wiec|rally|mityng|мітинг|митинг|zgromadzen|pikiet|picket|happening", re.I)),
]
GEOM_TYPE = {"route": "march", "point": "gathering", "area": "gathering"}


def _valid(hm):
    h = int(re.split(r"[:.]", hm)[0])
    return 6 <= h <= 23  # 1.05 / 2.05 / 3.05 are dates, not times


def _norm(hm):
    h, m = re.split(r"[:.]", hm)
    return f"{int(h):02d}:{m}"


def year_segment(text, year, years):
    """The part of a multi-year description that talks about `year`."""
    if len(years) <= 1 or not text:
        return text
    marks = [(m.start(), int(m.group(1))) for m in YEAR.finditer(text) if int(m.group(1)) in years]
    starts = [i for i, (pos, y) in enumerate(marks) if y == year]
    if not starts:
        return ""
    pos = marks[starts[0]][0]
    nxt = next((p for p, y in marks[starts[0] + 1:] if y != year), len(text))
    return text[pos:nxt]


def find_time(text):
    """'HH:MM' or 'HH:MM–HH:MM' from free text, or ''."""
    if not text:
        return ""
    for m in RANGE.finditer(text):
        if _valid(m.group(1)) and _valid(m.group(2)):
            return f"{_norm(m.group(1))}–{_norm(m.group(2))}"
    for m in CLOCK.finditer(text):
        if _valid(m.group(1)):
            return _norm(m.group(1))
    for m in HOUR_WORD.finditer(text):
        h = m.group(1) or m.group(2)
        if h and 6 <= int(h) <= 23:
            return f"{int(h):02d}:00"
    return ""


def event_type(name, text, geom):
    for blob in (name, text[:300]):
        for label, pat in TYPES:
            if blob and pat.search(blob):
                return label
    return GEOM_TYPE.get(geom, "")


def place(name, text, geom):
    """Short 'where': route start → end, a named spot, or the feature name if it is a place."""
    if name and not re.search(r"\d", name) and len(name) <= 45 and geom != "route":
        return name
    found = []
    for m in PLACE.finditer(text[:700]):
        f = m.group(0).strip(" .,")
        if f not in found:
            found.append(f)
    if geom == "route" and len(found) >= 2:
        return f"{found[0]} → {found[-1]}"
    return found[0] if found else ""


def attendance_for_year(raw, year):
    """'2003: 20000\\n2004: 30000' → the value for `year`; a plain number → itself."""
    per_year = dict(re.findall(r"(\d{4})\s*:\s*([\d .]+)", raw or ""))
    if per_year:
        v = per_year.get(str(year), "")
        return re.sub(r"[^\d]", "", v)
    return (raw or "").strip()


def scenario_fields(city, series, name, desc, geom, years, raw_attendance):
    """Per-year time/day/attendance plus year-independent type and place."""
    times, days, att = {}, {}, {}
    for y in years:
        seg = year_segment(desc, y, years) if len(years) > 1 else desc
        t = find_time(f"{name} {seg}") or DEFAULT_TIME.get((city, series), "")
        if t:
            times[y] = t
        if (city, series) in EVE_SERIES or EVE_WORDS.search(name):
            days[y] = "30.04"
        a = attendance_for_year(raw_attendance, y)
        if a and a != raw_attendance:
            att[y] = a
    return {"t": times, "dy": days, "ay": att,
            "k": event_type(name, desc, geom), "p": place(name, desc, geom)}
