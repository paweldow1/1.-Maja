"""Everything the pipeline knows about one year, for checking against the
hand-written scenarios.

Usage: python3 rok.py 1997 [PL|DE]
"""
import csv
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output"


def wczytaj(nazwa):
    sciezka = OUT_DIR / nazwa
    if not sciezka.exists():
        return []
    with sciezka.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def naglowek(tytul):
    print(f"\n{tytul}\n{'-' * len(tytul)}")


def raport(rok, miasto):
    rok_s = str(rok)
    print(f"\n{'=' * 72}\n{miasto} {rok_s}\n{'=' * 72}")

    kontekst = [k for k in wczytaj("roczniki_kontekst.csv")
                if k["rok"] == rok_s and k["miasto"] == miasto]
    if kontekst:
        k = kontekst[0]
        naglowek("kontekst roczny")
        for pole in ("Związek", "Temat", "Główna demonstracja",
                     "Centralne_BB", "frekwencja_niemcy", "Źródła"):
            if k.get(pole):
                print(f"  {pole}: {k[pole][:150]}")

    rocz = [r for r in wczytaj("roczniki_wydarzenia.csv")
            if r["rok"] == rok_s and r["miasto"] == miasto]
    if rocz:
        naglowek("z rocznika (per aktor)")
        for r in rocz:
            print(f"  {r['aktor'] or '(nieokreslony)'}")
            if r["miejsce_wiecu"]:
                print(f"      wiec:      {r['miejsce_wiecu']}  [{r['miejsce_wiecu_zrodlo']}]")
            if r["trasa"]:
                print(f"      trasa:     {r['trasa'][:120]}")
            if r["haslo"]:
                print(f"      haslo:     {r['haslo'][:120]}")
            if r["frekwencja_lista"]:
                print(f"      frekwencja: {r['frekwencja_lista']}  (sr {r['frekwencja_sr']})")

    scen = [s for s in wczytaj("scenariusz.csv")
            if s["rok"] == rok_s and s["miasto"] == miasto]
    if scen:
        naglowek(f"scenariusz godzinowy ({len(scen)} wpisow)")
        for s in scen:
            czas = s["godzina_od"] + (f"-{s['godzina_do']}" if s["godzina_do"] else "")
            dz = f"[{s['dzielnica']}]" if s["dzielnica"] else ""
            skala = s.get("skala") or ""
            print(f"  {czas:12s} {dz:20s} {skala:12s} {s['tekst'][:78]}")

    wyd = [w for w in wczytaj("wydarzenia.csv")
           if w["rok"] == rok_s and w["miasto"] == miasto]
    if wyd:
        naglowek(f"wydarzenia z mapy ({len(wyd)})")
        for w in sorted(wyd, key=lambda x: (x["typ"], x["aktor"])):
            frek = w["frekwencja_zrodlo"] or w["frekwencja_mapa_num"] or ""
            print(f"  {w['typ']:14s} {(w['aktor'] or '?'):16s} {(w['dzielnica_start'] or '?'):20s}"
                  f" {('~' + frek) if frek else '':>8s}  {(w['nazwa'] or '')[:40]}")

    proza = [p for p in wczytaj("roczniki_proza.csv")
             if p["rok"] == rok_s and p["miasto"] == miasto]
    if proza:
        naglowek(f"pola prozy w roczniku ({len(proza)})")
        for p in proza:
            print(f"  {p['pole']:22s} {len(p['tekst']):6d} znakow  {p['tekst'][:70]}...")


def main():
    rok = sys.argv[1] if len(sys.argv) > 1 else "1997"
    miasta = [sys.argv[2]] if len(sys.argv) > 2 else ["PL", "DE"]
    for miasto in miasta:
        raport(rok, miasto)


if __name__ == "__main__":
    main()
