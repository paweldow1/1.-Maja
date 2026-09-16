"""Build the payload for the verification page.

The page ships the rows to review as data and keeps only the decisions in
its store, so a rerun of the pipeline refreshes what is under review
without touching what has already been judged.

Usage: python3 weryfikacja_dane.py
"""
import csv
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output"


def wczytaj(nazwa):
    sciezka = OUT_DIR / nazwa
    if not sciezka.exists():
        return []
    with sciezka.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def skroc(tekst, n=180):
    tekst = (tekst or "").replace("\n", " ").strip()
    return tekst[:n] + ("…" if len(tekst) > n else "")


def main():
    wydarzenia = wczytaj("wydarzenia.csv")
    po_id = {w["id"]: w for w in wydarzenia}

    kolejki = {}

    # 1. rows the parser could not settle on its own
    kolejki["aktorzy"] = [{
        "klucz": w["id"], "rok": w["rok"], "miasto": w["miasto"],
        "warstwa": w["warstwa"], "typ": w["typ"], "typ_zrodlo": w["typ_zrodlo"],
        "aktor": w["aktor"], "zgadniety": w["aktor_zgadniety"] == "True",
        "nazwa": skroc(w["nazwa"], 90), "opis": skroc(w["opis"]),
        "dzielnica": w["dzielnica_start"],
    } for w in wydarzenia if w["wymaga_weryfikacji"] == "True"]

    # 2. ids that collided and got a suffix
    duplikaty = wczytaj("duplikaty_id_warszawa.csv") + wczytaj("duplikaty_id_berlin.csv")
    grupy = {}
    for d in duplikaty:
        grupy.setdefault(d["id_bazowy"], []).append(d["id"])
    kolejki["duplikaty"] = [{
        "klucz": baza,
        "rok": baza.split("_")[0],
        "miasto": baza.split("_")[1] if len(baza.split("_")) > 1 else "",
        "warianty": [{
            "id": i,
            "nazwa": skroc(po_id[i]["nazwa"], 70) if i in po_id else "",
            "warstwa": po_id[i]["warstwa"] if i in po_id else "",
            "dzielnica": po_id[i].get("dzielnica_start", "") if i in po_id else "",
        } for i in sorted(ids)],
    } for baza, ids in sorted(grupy.items()) if len(ids) > 1]

    # 3. the prose figure disagrees with the dedicated source
    kolejki["frekwencja"] = [{
        "klucz": f"{r['rok']}_{r['miasto']}_{r['aktor']}",
        "rok": r["rok"], "miasto": r["miasto"], "aktor": r["aktor"],
        "wydarzenie": r["wydarzenie"],
        "rocznik": r["frekwencja_rocznik"], "arkusz": r["frekwencja_arkusz"],
        "odchylka": r["odchylka_proc"],
        "lista": skroc(r["lista_rocznik"], 120), "zrodla": skroc(r["zrodla_arkusz"], 90),
    } for r in wczytaj("frekwencja_rozbieznosci.csv")]

    # 4. district events in the chronicle that never made it onto a map
    kolejki["brakujace"] = [{
        "klucz": b["grupa"], "rok": b["rok"], "miasto": b["miasto"],
        "godzina": b["godzina_od"] + ("–" + b["godzina_do"] if b["godzina_do"] else ""),
        "dzielnica": b["dzielnica"], "aktor": b["aktor"],
        "duplikat": b["mozliwy_duplikat"] == "TRUE",
        "tekst": skroc(b["tekst"], 200), "odniesienie": b["odniesienie"],
    } for b in wczytaj("brakujace_na_mapie.csv")]

    # 5. the rocznik knows an actor the map does not
    kolejki["tylko_rocznik"] = [{
        "klucz": f"{r['rok']}_{r['miasto']}_{r['aktor'] or 'brak'}",
        "rok": r["rok"], "miasto": r["miasto"], "aktor": r["aktor"],
        "typ": r["typ"], "klucze": r["klucze_zrodlowe"],
        "trasa": skroc(r["trasa"], 140), "haslo": skroc(r["haslo"], 100),
        "frekwencja": r["frekwencja_lista"],
    } for r in wczytaj("tylko_rocznik.csv")]

    # 6. objects with no year at all
    kolejki["bez_lat"] = [{
        "klucz": f"{b['plik_zrodlowy']}#{b['id_geo']}",
        "miasto": b["miasto"], "warstwa": b["warstwa"],
        "nazwa": skroc(b["nazwa"], 90), "plik": b["plik_zrodlowy"], "id_geo": b["id_geo"],
    } for b in wczytaj("bez_lat_warszawa.csv") + wczytaj("bez_lat_berlin.csv")]

    pole = wczytaj("pole.csv")

    dane = {
        "kolejki": kolejki,
        "pole": pole,
        "aktorzy_znani": sorted({w["aktor"] for w in wydarzenia if w["aktor"]}),
        "typy_znane": sorted({w["typ"] for w in wydarzenia if w["typ"]}),
        "podsumowanie": {
            "wydarzen": len(wydarzenia),
            "pl": sum(1 for w in wydarzenia if w["miasto"] == "PL"),
            "de": sum(1 for w in wydarzenia if w["miasto"] == "DE"),
            "z_rocznikiem": sum(1 for w in wydarzenia
                                if w["zrodlo_zlaczenia"] == "mapa+rocznik"),
            "z_frekwencja": sum(1 for w in wydarzenia
                                if w["frekwencja_zrodlo"] or w["frekwencja_mapa_num"]),
            "z_dzielnica": sum(1 for w in wydarzenia if w["dzielnica_start"]),
        },
    }

    sciezka = OUT_DIR / "weryfikacja_dane.json"
    sciezka.write_text(json.dumps(dane, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
    print(f"weryfikacja_dane.json: {sciezka.stat().st_size // 1024} KB")
    for nazwa, wiersze in kolejki.items():
        print(f"  {nazwa:16s} {len(wiersze):5d}")


if __name__ == "__main__":
    main()
