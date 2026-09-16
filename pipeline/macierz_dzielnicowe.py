"""Macierz dzielnicowek PDS/Die Linke: lata w wierszach, cykle w kolumnach.

Komorka mowi jedno z trzech: co sie odbylo i o ktorej, albo ze cykl w tym
roku trwal, ale tej edycji nikt nie opisal, albo nic -- bo cyklu jeszcze
(lub juz) nie bylo. Te trzy stany to trzy rozne rzeczy i strona ma je
rozrozniac na pierwszy rzut oka.

Usage: python3 macierz_dzielnicowe.py
"""
import csv
import html
from collections import defaultdict
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output"
OD, DO = 1990, 2019


def e(t):
    return html.escape(str(t or ""))


def main():
    with (OUT_DIR / "wydarzenia.csv").open(encoding="utf-8") as f:
        wyd = [x for x in csv.DictReader(f)
               if x["warstwa"] == "Dzielnicowe" and OD <= int(x["rok"]) <= DO]
    with (OUT_DIR / "dzielnicowe_serie.csv").open(encoding="utf-8") as f:
        meta = {s["seria"]: s for s in csv.DictReader(f)}

    # Kolumna to cykl, a nie aktor: Maifest am Obersee w 1994 prowadzi
    # ponadpartyjne Aktionsbündnis, a w pozostalych latach PDS -- to nadal
    # ten sam cykl i ten sam rok trzeba w nim widziec. Do macierzy trafiaja
    # cykle, ktore w wiekszosci edycji prowadzi linia PDS/Die Linke; kto
    # prowadzil dana edycje, mowi sama komorka.
    wg_serii, luzne = defaultdict(dict), defaultdict(list)
    for x in wyd:
        if x["seria"]:
            wg_serii[x["seria"]][int(x["rok"])] = x
        elif x["aktor_linia"] == "PDS/Die Linke":
            luzne[int(x["rok"])].append(x)
    wg_serii = {s: v for s, v in wg_serii.items()
                if sum(1 for x in v.values() if x["aktor_linia"] == "PDS/Die Linke")
                > len(v) / 2}

    def rozpietosc(seria):
        m = meta.get(seria, {})
        od = int(m["od_roku"]) if m.get("od_roku", "").isdigit() else None
        do = int(m["do_roku"]) if m.get("do_roku", "").isdigit() else None
        return od, do

    kolumny = sorted(wg_serii, key=lambda s: (rozpietosc(s)[0] or 9999, s))
    lata = list(range(OD, DO + 1))

    opisane = sum(len(v) for v in wg_serii.values())
    w_cyklu = sum(1 for s in kolumny for r in lata
                  if (rozpietosc(s)[0] or 9999) <= r <= (rozpietosc(s)[1] or -1))
    obcy = sum(1 for s in kolumny for x in wg_serii[s].values()
               if x["aktor_linia"] != "PDS/Die Linke")
    czesci = [SZABLON_GORA.format(
        opisane=opisane, niepotw=w_cyklu - opisane, cykli=len(kolumny),
        luznych=sum(len(v) for v in luzne.values()), obcy=obcy,
        razem=opisane + sum(len(v) for v in luzne.values()))]

    # naglowek
    czesci.append('<div class="ramka"><table class="macierz"><thead><tr>'
                  '<th class="rok-h" scope="col">rok</th>')
    for s in kolumny:
        od, do = rozpietosc(s)
        m = meta.get(s, {})
        czesci.append(
            f'<th scope="col"><span class="seria">{e(s)}</span>'
            f'<span class="dz">{e(m.get("dzielnica"))}</span>'
            f'<span class="span">{od or "?"}–{do or "?"}</span></th>')
    czesci.append("</tr></thead><tbody>")

    for rok in lata:
        czesci.append(f'<tr><th class="rok" scope="row">{rok}</th>')
        for s in kolumny:
            od, do = rozpietosc(s)
            x = wg_serii[s].get(rok)
            if x:
                czas = e(x["godzina"]) + (f'–{e(x["godzina_do"])}' if x["godzina_do"] else "")
                bity = []
                if czas:
                    bity.append(f'<span class="czas">{czas}</span>')
                else:
                    bity.append('<span class="czas brak">godzina nieznana</span>')
                if x["data"] and x["data"] != "01.05":
                    bity.append(f'<span class="wigilia">{e(x["data"])}</span>')
                bity.append(f'<span class="nazwa">{e(x["nazwa"])}</span>')
                if x["miejsce"]:
                    bity.append(f'<span class="miejsce">{e(x["miejsce"])}</span>')
                if x["osoby"]:
                    bity.append(f'<span class="osoby">{e(x["osoby"])}</span>')
                if x["aktor_linia"] != "PDS/Die Linke":
                    bity.append(f'<span class="obcy">organizuje: {e(x["aktor"])}</span>')
                if x["edycja"]:
                    bity.append(f'<span class="edycja">edycja {e(x["edycja"])}</span>')
                if x.get("cytat"):
                    bity.append('<details class="dowod"><summary>'
                                + e(x.get("zrodlo") or "źródło") + "</summary>"
                                f'<q>{e(x["cytat"])}</q></details>')
                czesci.append(f'<td class="jest">{"".join(bity)}</td>')
            elif od is not None and do is not None and od <= rok <= do:
                czesci.append('<td class="brak"><span class="etykieta">'
                              'niepotwierdzone</span></td>')
            else:
                czesci.append('<td class="poza"></td>')
        czesci.append("</tr>")
    czesci.append("</tbody></table></div>")

    # poza cyklami
    czesci.append('<h2 id="poza">Poza cyklami</h2>'
                  '<p class="wstep">Wydarzenia, ktore pojawiaja sie w zrodlach raz '
                  'i nie daje sie ich przypisac do zadnego powtarzajacego sie cyklu.</p>'
                  '<div class="luzne">')
    for rok in sorted(luzne):
        czesci.append(f'<section class="luzny-rok"><h3>{rok}</h3><ul>')
        for x in sorted(luzne[rok], key=lambda y: (y["data"], y["godzina"])):
            czas = e(x["godzina"]) + (f'–{e(x["godzina_do"])}' if x["godzina_do"] else "")
            czesci.append(
                f'<li><span class="czas">{czas or "—"}</span>'
                + (f'<span class="wigilia">{e(x["data"])}</span>'
                   if x["data"] and x["data"] != "01.05" else "")
                + f'<span class="nazwa">{e(x["nazwa"])}</span>'
                f'<span class="dz-inline">{e(x["dzielnica_start"])}</span>'
                + (f'<span class="miejsce">{e(x["miejsce"])}</span>' if x["miejsce"] else "")
                + (f'<span class="osoby">{e(x["osoby"])}</span>' if x["osoby"] else "")
                + "</li>")
        czesci.append("</ul></section>")
    czesci.append("</div>")

    # dowody rozpietosci
    czesci.append('<h2 id="dowody">Skad rozpietosci cykli</h2><dl class="dowody">')
    for s in kolumny:
        od, do = rozpietosc(s)
        czesci.append(f'<dt>{e(s)} <span class="span">{od or "?"}–{do or "?"}</span></dt>'
                      f'<dd>{e(meta.get(s, {}).get("dowod"))}</dd>')
    czesci.append("</dl>")
    czesci.append(STOPKA)

    sciezka = OUT_DIR / "macierz_dzielnicowe.html"
    sciezka.write_text("".join(czesci), encoding="utf-8")
    print(f"macierz_dzielnicowe.html: {sciezka.stat().st_size // 1024} KB")
    print(f"  cykli {len(kolumny)}, opisanych edycji {opisane}, "
          f"niepotwierdzonych {w_cyklu - opisane}, poza cyklami "
          f"{sum(len(v) for v in luzne.values())}")


SZABLON_GORA = """<title>Dzielnicówki PDS</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root{{
    --ground:#f6f2ef; --surface:#fffdfb; --ink:#1c1917; --muted:#7c716a;
    --line:#e4dcd5; --line-mocna:#cdc1b8; --accent:#9b2226; --ghost:#b9aca3;
    --ghost-tlo:#efe9e4;
    --ui:"Archivo",system-ui,sans-serif;
    --tekst:"Newsreader",Georgia,serif;
    --mono:"IBM Plex Mono",ui-monospace,monospace;
  }}
  @media (prefers-color-scheme:dark){{
    :root:not([data-theme="light"]){{
      --ground:#161413; --surface:#1f1c1a; --ink:#ece6e1; --muted:#9b8f88;
      --line:#312b28; --line-mocna:#463e39; --accent:#e0645c; --ghost:#6a5f59;
      --ghost-tlo:#221f1d;
    }}
  }}
  :root[data-theme="dark"]{{
    --ground:#161413; --surface:#1f1c1a; --ink:#ece6e1; --muted:#9b8f88;
    --line:#312b28; --line-mocna:#463e39; --accent:#e0645c; --ghost:#6a5f59;
    --ghost-tlo:#221f1d;
  }}
  body{{background:var(--ground);color:var(--ink);font-family:var(--tekst);
    margin:0;padding-block:32px 64px;padding-left:16px;padding-right:16px;
    font-size:15px;line-height:1.5;}}
  .szpalta{{max-width:62ch;}}
  h1{{font-family:var(--ui);font-size:26px;font-weight:700;letter-spacing:-.015em;
    margin:0 0 6px;text-wrap:balance;}}
  .podtytul{{font-size:15px;color:var(--muted);margin:0 0 22px;}}
  h2{{font-family:var(--ui);font-size:17px;font-weight:600;letter-spacing:.01em;
    margin:44px 0 6px;padding-top:18px;border-top:1px solid var(--line);}}
  .wstep{{color:var(--muted);margin:0 0 16px;max-width:62ch;font-size:14px;}}

  .liczby{{display:flex;flex-wrap:wrap;gap:22px;margin:0 0 18px;
    font-family:var(--ui);}}
  .liczby div{{display:flex;flex-direction:column;}}
  .liczby b{{font-family:var(--mono);font-size:22px;font-weight:500;
    font-variant-numeric:tabular-nums;line-height:1.1;}}
  .liczby span{{font-size:11px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--muted);margin-top:3px;}}

  .zakres{{max-width:62ch;color:var(--muted);font-size:13px;margin:0 0 16px;}}
  .zakres b{{color:var(--ink);font-weight:500;}}
  .legenda{{display:flex;flex-wrap:wrap;gap:16px;margin:0 0 18px;
    font-family:var(--ui);font-size:12px;color:var(--muted);align-items:center;}}
  .legenda i{{display:inline-block;width:14px;height:14px;vertical-align:-2px;
    margin-right:6px;border:1px solid var(--line-mocna);}}
  .l-jest{{background:var(--surface);border-left:3px solid var(--accent)!important;}}
  .l-brak{{background:var(--ghost-tlo);background-image:repeating-linear-gradient(
    -45deg,transparent 0 4px,var(--line) 4px 5px);}}
  .l-poza{{background:transparent;}}

  .ramka{{overflow-x:auto;border:1px solid var(--line);background:var(--surface);}}
  table.macierz{{border-collapse:collapse;font-size:12px;}}
  .macierz th,.macierz td{{border:1px solid var(--line);vertical-align:top;
    text-align:left;}}
  .macierz thead th{{background:var(--ground);padding:8px 9px;width:186px;
    min-width:186px;font-family:var(--ui);font-weight:600;position:sticky;
    top:env(safe-area-inset-top,0px);z-index:2;}}
  .macierz thead th.rok-h{{width:52px;min-width:52px;left:0;z-index:3;
    font-family:var(--mono);font-weight:500;text-transform:uppercase;
    font-size:10px;letter-spacing:.08em;color:var(--muted);}}
  .seria{{display:block;line-height:1.25;}}
  .dz{{display:block;color:var(--muted);font-weight:500;font-size:11px;margin-top:2px;}}
  .span{{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);
    margin-top:3px;}}
  th.rok{{position:sticky;left:0;background:var(--ground);font-family:var(--mono);
    font-weight:500;font-size:12px;font-variant-numeric:tabular-nums;
    padding:8px 9px;z-index:1;color:var(--muted);}}
  .macierz td{{padding:7px 9px;}}
  td.jest{{background:var(--surface);border-left:3px solid var(--accent);}}
  td.jest span{{display:block;}}
  .czas{{font-family:var(--mono);font-size:12px;font-weight:500;color:var(--accent);
    font-variant-numeric:tabular-nums;}}
  .czas.brak{{color:var(--muted);font-size:10px;font-weight:400;}}
  .wigilia{{font-family:var(--ui);font-size:10px;font-weight:600;color:var(--muted);
    letter-spacing:.05em;}}
  .nazwa{{font-family:var(--tekst);font-size:13px;margin-top:2px;line-height:1.3;}}
  .miejsce{{color:var(--muted);font-size:11px;margin-top:3px;line-height:1.35;}}
  .osoby{{color:var(--muted);font-size:11px;font-style:italic;margin-top:3px;
    line-height:1.35;}}
  .edycja{{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:4px;}}
  .dowod{{margin-top:6px;font-family:var(--ui);font-size:10px;}}
  .dowod summary{{color:var(--muted);cursor:pointer;list-style:none;
    text-decoration:underline dotted;text-underline-offset:2px;}}
  .dowod summary::-webkit-details-marker{{display:none}}
  .dowod summary:hover{{color:var(--accent);}}
  .dowod q{{display:block;margin-top:5px;padding-left:7px;
    border-left:2px solid var(--line-mocna);font-family:var(--tekst);
    font-size:11px;line-height:1.4;color:var(--ink);quotes:"„" "”";}}
  .obcy{{font-family:var(--ui);font-size:10px;font-weight:600;color:var(--accent);
    margin-top:4px;letter-spacing:.01em;}}
  td.brak{{background:var(--ghost-tlo);
    background-image:repeating-linear-gradient(
      -45deg,transparent 0 5px,var(--line) 5px 6px);}}
  td.brak .etykieta{{font-family:var(--ui);font-size:9px;letter-spacing:.04em;
    color:var(--ghost);text-transform:lowercase;font-variant:small-caps;}}
  td.poza{{background:transparent;}}

  .luzne{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
    gap:20px;}}
  .luzny-rok h3{{font-family:var(--mono);font-size:13px;font-weight:500;
    margin:0 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line-mocna);
    color:var(--accent);}}
  .luzny-rok ul{{list-style:none;margin:0;padding:0;display:flex;
    flex-direction:column;gap:11px;}}
  .luzny-rok li span{{display:block;}}
  .dz-inline{{font-family:var(--ui);font-size:10px;text-transform:uppercase;
    letter-spacing:.06em;color:var(--muted);margin-top:2px;}}

  .dowody{{margin:0;max-width:74ch;}}
  .dowody dt{{font-family:var(--ui);font-size:13px;font-weight:600;margin-top:14px;}}
  .dowody dt .span{{display:inline;font-family:var(--mono);font-size:11px;
    color:var(--muted);margin-left:6px;}}
  .dowody dd{{margin:3px 0 0;color:var(--muted);font-size:13px;}}

  footer{{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);
    color:var(--muted);font-size:12px;font-family:var(--ui);max-width:74ch;}}
</style>
<div class="szpalta">
<h1>Dzielnicówki PDS i Die Linke</h1>
<p class="podtytul">Berlin, 1990–2019. Cykliczne festyny pierwszomajowe
organizowane przez dzielnicowe struktury partii — jedna linia, mimo zmiany
nazwy w 2007 roku.</p>
<div class="liczby">
  <div><b>{cykli}</b><span>cykli</span></div>
  <div><b>{opisane}</b><span>opisanych edycji</span></div>
  <div><b>{niepotw}</b><span>niepotwierdzonych</span></div>
  <div><b>{luznych}</b><span>poza cyklami</span></div>
</div>
</div>
<p class="zakres">Kolumna to <b>cykl</b>, nie organizator: {razem} edycji w tabeli,
z czego {obcy} prowadzil w danym roku ktos inny niz PDS lub Die Linke &mdash; komórka
mówi wtedy, kto. Festyny dzielnicowe SPD i pozostałych, które nie należą do żadnego
z tych cykli, są poza tą tabelą.</p>
<div class="legenda">
  <span><i class="l-jest"></i>edycja opisana w źródle</span>
  <span><i class="l-brak"></i>cykl trwał, tej edycji nikt nie opisał</span>
  <span><i class="l-poza"></i>cyklu jeszcze lub już nie było</span>
  <span>&middot; kliknij źródło pod wpisem, żeby zobaczyć cytat</span>
</div>
"""

STOPKA = """<footer>
Źródła: archiwum nd-aktuell (1992–2000), strony i newslettery Die Linke Berlin,
Berliner Zeitung, Berliner Morgenpost, PDS Berlin. Godziny podane tak, jak
stoją w źródle. „30.04” oznacza wydarzenie wieczoru poprzedzającego, nie
1 maja. Numer edycji liczony od roku początkowego cyklu, nie od najstarszego
zachowanego opisu.
</footer>"""


if __name__ == "__main__":
    main()
