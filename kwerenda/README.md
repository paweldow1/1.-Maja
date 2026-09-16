# Kwerenda

<img src="zasoby/kwerenda.png" width="96" align="right" alt="">

Search websites for content and move what you find straight into **Zotero** —
with the bibliographic citation, tags and a note holding the quotation in context.

Built for a working historian: sources in several languages, sites on every
imaginable CMS, and site search engines that cannot be trusted. It began as a
scraper for the regional sites of NSZZ „Solidarność"; nothing about it is tied
to them any more.

```
python -m kwerenda gui              # the interface, in your browser
python install_desktop_icon.py      # …or an icon on your desktop
```

---

## What it does

### Finding things

* Boolean queries: `AND` / `OR` / `NOT`, parentheses, `"phrases"`.
* Proximity: `Wałęsa NEAR/10 mass` (or `Wałęsa ~10 mass`).
* Fields: `title:`, `text:`, `author:`, `url:`, `tags:`. With no prefix the
  **content** is searched (title + text + author), so a bare CMS tag or a word in
  the address is not by itself a hit — ask for those explicitly.
* **The asterisk is truncation**, as in any library catalogue:

  | you write | it matches |
  |---|---|
  | `strike` | that word exactly |
  | `strike*` | inflected forms in every enabled language — *strikes, Streiks, страйку, strajkujących* |
  | `strike**` | the stem plus anything at all — also derivatives |
  | `"May Day"*` | the whole phrase inflected, in agreement: *Józefa Robotnika* |

  A checkbox turns inflection on for every term at once, if you would rather not
  type stars. Polish operators (`I`, `LUB`, `NIE`, `BLISKO/10`) still work.
* Optional diacritic-blindness: `Zoliborz` = `Żoliborz`, `Munchen` = `München`.
* **A preview before you touch the network**: the interface lists the forms each
  term will catch, language by language, and one click excludes any of them.
  Paste a sample paragraph to check whether your query passes it.

### Languages

Polish, English, German, Russian and Ukrainian out of the box, with the script of
the term deciding what applies — a Cyrillic word is never expanded with German
endings.

| | catches |
|---|---|
| Polish | *Żoliborz → Żoliborzu, żoliborski*; *święto → świąt, święcie* |
| English | *strike → strikes, striking*; *city → cities*; *stop → stopped* |
| German | *Mann → Männer*; *Buch → Bücher*; *Gewerkschaft → Gewerkschaften* |
| Russian | *забастовка → забастовках*; *праздник → празднике* |
| Ukrainian | *страйк → страйку*; *свято → свята* |

Dates are read in all five: *2 maja 2015*, *1. Mai 2019*, *9 травня 2020*,
*9 мая 2020*, *May 1, 2001*. Each page's language is detected and can become a tag.

Adding a language means adding a table in `kwerenda/morfologia/jezyki.py` — a list
of endings and a table of stem alternations. No code changes.

### Collecting the material

`auto` walks down a ladder until something works:

**WordPress REST API → Drupal JSON:API → sitemap → RSS → the site's own search → link crawl**

Whatever the source, **it only produces candidates**. Every hit is then confirmed
against the full article text with your query, so results are reproducible and do
not depend on how well a site indexes itself.

When a site's own search is hopeless — and newspaper archives often are — do not
fight it:

* `listing_url` — a template for a paginated archive, e.g.
  `https://paper.com/archive/{year}/page/{page}`. Kwerenda walks it and ignores
  the search entirely.
* `search_url` — a template for the site's search, e.g.
  `https://site.com/search?q={q}&page={page}`, when it works but is not one of
  the shapes detected automatically.
* `full_sweep: true` — take the whole archive and match locally.
* `date_window: "04-25:05-10"` with a year range — fetch only what appeared
  around 1 May in each year. Studying one single day, that is the difference
  between a hundred pages and tens of thousands.

CSS selectors (`link_selector`, `next_selector`) are there when the guessing needs
help; leaving them empty is usually fine.

### Signing in as yourself

Some material sits behind your own subscription. A source can carry your
credentials: a `Cookie` header copied from the browser, a `cookies.txt` exported
from it, cookies read straight from a local Firefox/Chrome profile (optional
`browser-cookie3`), or HTTP basic auth.

**This is not a way past a paywall.** Nothing here disguises the client, defeats
bot detection or circumvents any protection — a 401/403 ends with the page being
skipped and a clear message. It reaches what your own account already opens, and
whether automated reading is allowed is between you and the site's terms.

### PDFs and other attachments

Local party newsletters, council minutes and festival programmes are routinely
published as a PDF hanging off an otherwise empty page. Kwerenda follows those
links, reads the text out of the file and treats it as a document in its own
right: it gets its own citation, its own quotation in context, and — when sent
to a running Zotero — **the PDF itself is attached**, not merely linked.

* Works from every adapter: whatever page is fetched, the documents linked from
  it are picked up. Switch it off per source with `attachments: false`.
* Reads `.pdf`, `.docx` and plain text. PDF text comes from `pypdf` (shipped),
  or `pdfminer.six` or poppler's `pdftotext` if you have them.
* The date comes from the file name where there is one — `info-links-05-2019.pdf`
  is the May 2019 issue, whatever date the file was last saved.
* The title comes from the PDF's own metadata, falling back to the link text on
  the page ("Info-Links Mai 2019"), and the citation records which page it was
  found on.
* **A scan is reported as a scan.** A PDF with no text layer yields the message
  *no text layer — the file is almost certainly a scan and would need OCR*,
  rather than silently counting as "no match". Kwerenda does not do OCR.

Once read, a PDF lives in the corpus like any page, so further queries run
against it offline. See `presets/pdf-newsletters.yaml`.

### The citation

* Author, date, site name, language and publisher, taken in a cascade from
  JSON-LD (schema.org) → OpenGraph → `<meta>` → Dublin Core → HTML heuristics.
* Citation keys in Better BibTeX style: `nowak2015obchody`, collisions resolved.
* Tags assembled from the matched terms, the year, the domain, the detected
  language, the CMS's own categories and tags, and whatever you add yourself.
* A keyword-in-context quotation for every hit, with the matched form marked.
  Quotations are clipped to their field, so a citation never bleeds into
  concatenated metadata.

### Getting it out

* **Straight into an open Zotero** through the local connector — citation, tags
  and the quotation note land in the library at once.
* **Zotero Web API** — key plus user id, with a collection picker.
* Files: **RIS** (the safest import: keywords become tags, the note comes across),
  **CSL-JSON**, **BibTeX / Better BibTeX**, **CSV**, **Zotero JSON**.
* **Obsidian notes** (.zip) with YAML front matter and a `[[@citekey]]` link, the
  way Better BibTeX makes them.

### Manners, and the corpus

Per-host throttling with jitter, backoff on 429/5xx honouring `Retry-After`,
`robots.txt` respected, a User-Agent carrying your contact details.

Every page fetched is kept in a local SQLite corpus. Later searches can run in
`corpus` mode — **without a single request to anybody's server**. Collect once,
test hypotheses for as long as you like.

---

## Installing

```bash
pip install -r requirements.txt
```

Or don't think about it: `python install_desktop_icon.py` prepares a private
environment, draws the icon and puts a shortcut on your desktop
(Linux `.desktop`, a macOS `.app`, a Windows `.lnk`). `./start.sh` and
`start.bat` do the same without the icon.

## Using it

### The interface

```bash
python -m kwerenda gui              # http://127.0.0.1:8765
```

It listens on 127.0.0.1 only; nothing is exposed to the outside world.

Tabs: **Search** (what and where, the form preview, a live log) → **Results**
(a table with quotations, editable citations and tags) → **Export** →
**Corpus & runs** → **Syntax**.

### The command line

```bash
# see what a query will catch, before going near the network
python -m kwerenda preview '"1 maja"* AND (Żoliborz* OR "Józef Robotnik"*)' \
       --languages pl --sample "Na Żoliborzu 1-go maja odprawiono mszę."

# run a saved job and write RIS straight away
python -m kwerenda run presets/may-day-solidarnosc.yaml --format ris

# send hits to a running Zotero
python -m kwerenda zotero --run 3

python -m kwerenda export --run 3 --format bibtex
python -m kwerenda runs
python -m kwerenda corpus
python -m kwerenda languages
```

## Presets

**A preset is a file.** Everything in the `presets/` folder — YAML or JSON, with
English keys — shows up in the interface's *load a preset* list and can be run
from the command line. Nothing is hidden in a database, so a query can go into
version control, be mailed to a colleague, or edited in any text editor.

| file | what it shows |
|---|---|
| `may-day-solidarnosc.yaml` | the WordPress case, fully commented |
| `may-day-three-countries.yaml` | one question in Polish, German and Ukrainian |
| `newspaper-archive.yaml` | a bad archive search, walked by a listing template; signing in with your own subscription |
| `pdf-newsletters.yaml` | a branch that publishes only PDFs — following and reading them |
| `offline-corpus.yaml` | new keywords against already-downloaded material |

In the interface: pick one from the dropdown to fill the whole form, or press
**Save as preset** to write the current form back out as a new file.

From the command line, by name or by path:

```bash
python -m kwerenda presets                        # what is available
python -m kwerenda run may-day-solidarnosc        # by name
python -m kwerenda run presets/offline-corpus.yaml --format ris
python -m kwerenda --presets ~/my-queries run whatever
```

Configurations written by earlier Polish-language versions still load.

## How the morphology works

No dictionary, no external analyser, nothing to download. A stem is found by
stripping a known ending, and a regular expression is built from
**the stem with its alternations** (`t→ć/ci`, `k→c/cz`, `r→rz`, `ó↔o`, `ą↔ę`,
fleeting *e*; umlaut for German; `к→ч`, `г→ж` for Russian) plus **a closed list of
inflectional endings**.

So `Gdańsk*` catches *Gdańsku* and *Gdańska* but not *gdakanie*; `praca*` catches
*pracy* and *pracach* but not *prawo*.

The price is that the pattern is sometimes over-generous (`maj*` will also let
through the verb *mają*). That is why the preview lists every form and a click
excludes it. If `morfeusz2` happens to be installed, `morfologia.lematyzuj` will
use it, but nothing depends on it.

## What it will not do

* Get past paywalls, CAPTCHAs or logins, or disguise itself as a browser.
* Assume every site has the same CMS, theme or HTML.
* Trust somebody else's search engine without reading the text itself.

## Tests

```bash
python -m unittest discover -s tests -t .
```

72 tests: morphology in five languages, the query parser, metadata extraction,
source adapters, PDF attachments, the engine end to end and every export format. The engine is
tested against a **local fake WordPress site** (`tests/atrapa_wordpressa.py`) —
REST API with pagination, a title-only search, an archive listing, a sitemap, an
RSS feed, `robots.txt`, one article behind a subscriber cookie and a page of PDF
newsletters (real PDFs, generated without any library, one of them a scan with no
text layer) — so the suite never sends a request to anybody else's server.

## Layout

| file | role |
|---|---|
| `morfologia/` | inflection → regular expressions; one table per language |
| `zapytania.py` | the operator parser, document scoring, KWIC quotations |
| `siec.py` | the polite HTTP client (throttling, backoff, robots.txt, your credentials) |
| `ekstrakcja.py` | article text and bibliographic metadata out of HTML |
| `zrodla.py` | adapters: WordPress, Drupal, sitemap, RSS, search, listing, crawl |
| `pliki.py` | reading text out of PDF, .docx and plain-text attachments |
| `silnik.py` | orchestration: candidates → verification → hits |
| `cytowania.py` | record → RIS / CSL-JSON / BibTeX / CSV / Markdown / Zotero |
| `zotero.py` | the local connector and the Web API |
| `magazyn.py` | SQLite: corpus, runs, hits, presets |
| `serwer.py` + `web/index.html` | the interface |
| `zasoby/ikona.py` | draws the application icon, in pure Python |

The interface, the configuration keys and the command line are English;
identifiers inside the code are Polish, from the first version. They can be
renamed if it ever gets in the way.
