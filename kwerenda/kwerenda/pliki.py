# -*- coding: utf-8 -*-
"""Attachments: reading the text out of PDFs and Word files.

Local party newsletters, council minutes and festival programmes are very often
published as a PDF hanging off an otherwise thin HTML page. Ignoring them means
ignoring the source, so Kwerenda follows those links, pulls the text, and treats
the file as a document in its own right — with its own citation.

PDF text is extracted with whichever backend is available, in order of quality:

1. ``pypdf`` — pure Python, the dependency we ship with;
2. ``pdfminer.six`` — better with awkward layouts, if installed;
3. ``pdftotext`` from poppler — an external binary, if on PATH.

A PDF that is a scan carries no text layer at all. That is reported as such
rather than passed on as an empty document: the difference between "this file
does not mention May Day" and "nobody has run OCR on this file" matters.
"""

from __future__ import annotations

import io
import re
import subprocess
import zipfile
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .ekstrakcja import Metadane, html_na_tekst, normalizuj_date

#: Extensions we know how to read. Everything else stays a plain link.
ROZSZERZENIA_PDF = (".pdf",)
ROZSZERZENIA_WORD = (".docx",)
ROZSZERZENIA_TEKST = (".txt", ".md", ".csv")
ROZSZERZENIA = ROZSZERZENIA_PDF + ROZSZERZENIA_WORD + ROZSZERZENIA_TEKST

TYPY_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/csv",
}


def rozszerzenie(url: str) -> str:
    sciezka = re.sub(r"[?#].*$", "", url or "").lower()
    for koncowka in ROZSZERZENIA:
        if sciezka.endswith(koncowka):
            return koncowka
    return ""


def czy_zalacznik(url: str, typ_tresci: str = "") -> bool:
    """Is this address a document we can read rather than a web page?"""
    if rozszerzenie(url):
        return True
    typ = (typ_tresci or "").split(";")[0].strip().lower()
    return typ in ("application/pdf", TYPY_MIME[".docx"])


def typ_mime(url: str) -> str:
    return TYPY_MIME.get(rozszerzenie(url), "application/octet-stream")


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

@dataclass
class WynikPliku:
    tekst: str = ""
    meta: Metadane = None                    # type: ignore[assignment]
    stron: int = 0
    silnik: str = ""
    uwaga: str = ""                          # e.g. "scan without a text layer"

    def __post_init__(self):
        if self.meta is None:
            self.meta = Metadane()


def _import_bezpieczny(nazwa: str):
    """Import that survives a broken installation, not merely a missing package.

    ``pypdf`` reaches for ``cryptography``, and on a damaged system that import
    aborts with a Rust panic — which arrives as a BaseException, sails straight
    through ``except Exception`` and would take the whole search down with it.
    A PDF backend being unavailable is never worth crashing over.
    """
    try:
        return __import__(nazwa, fromlist=["*"])
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None


def _pdf_przez_pypdf(dane: bytes) -> Optional[WynikPliku]:
    pypdf = _import_bezpieczny("pypdf")
    if pypdf is None:
        return None
    try:
        czytnik = pypdf.PdfReader(io.BytesIO(dane))
        if getattr(czytnik, "is_encrypted", False):
            try:
                czytnik.decrypt("")          # many files are "encrypted" with no password
            except Exception:
                return WynikPliku(silnik="pypdf", uwaga="the file is password protected")
        kawalki = []
        for strona in czytnik.pages:
            try:
                kawalki.append(strona.extract_text() or "")
            except Exception:
                continue
        meta = Metadane()
        try:
            info = czytnik.metadata or {}
            meta.tytul = str(info.get("/Title") or "").strip()
            autor = str(info.get("/Author") or "").strip()
            meta.autorzy = [autor] if autor else []
            meta.data = _data_pdf(str(info.get("/CreationDate") or ""))
            meta.data_modyfikacji = _data_pdf(str(info.get("/ModDate") or ""))
        except Exception:
            pass
        return WynikPliku(tekst="\n".join(kawalki), meta=meta,
                          stron=len(czytnik.pages), silnik="pypdf")
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        return WynikPliku(silnik="pypdf", uwaga=f"unreadable PDF: {exc}")


def _pdf_przez_pdfminer(dane: bytes) -> Optional[WynikPliku]:
    modul = _import_bezpieczny("pdfminer.high_level")
    if modul is None:
        return None
    try:
        tekst = modul.extract_text(io.BytesIO(dane)) or ""
        return WynikPliku(tekst=tekst, silnik="pdfminer.six")
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        return WynikPliku(silnik="pdfminer.six", uwaga=f"unreadable PDF: {exc}")


def _pdf_przez_pdftotext(dane: bytes) -> Optional[WynikPliku]:
    try:
        wynik = subprocess.run(["pdftotext", "-layout", "-", "-"], input=dane,
                               capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if wynik.returncode != 0:
        return None
    return WynikPliku(tekst=wynik.stdout.decode("utf-8", "replace"), silnik="pdftotext")


_SILNIKI_PDF: List[Tuple[str, Callable[[bytes], Optional[WynikPliku]]]] = [
    ("pypdf", _pdf_przez_pypdf),
    ("pdfminer.six", _pdf_przez_pdfminer),
    ("pdftotext", _pdf_przez_pdftotext),
]


def dostepne_silniki() -> List[str]:
    """Which PDF backends this installation can actually use."""
    dostepne = []
    if _import_bezpieczny("pypdf") is not None:
        dostepne.append("pypdf")
    if _import_bezpieczny("pdfminer.high_level") is not None:
        dostepne.append("pdfminer.six")
    try:
        if subprocess.run(["pdftotext", "-v"], capture_output=True,
                          timeout=10).returncode in (0, 99):
            dostepne.append("pdftotext")
    except (OSError, subprocess.SubprocessError):
        pass
    return dostepne


def _data_pdf(surowa: str) -> str:
    """PDF dates look like D:20190415120000+02'00'."""
    dopasowanie = re.search(r"D?:?\s*((?:19|20)\d{2})(\d{2})?(\d{2})?", surowa or "")
    if not dopasowanie:
        return normalizuj_date(surowa)
    czesci = [dopasowanie.group(1)]
    if dopasowanie.group(2) and 1 <= int(dopasowanie.group(2)) <= 12:
        czesci.append(dopasowanie.group(2))
        if dopasowanie.group(3) and 1 <= int(dopasowanie.group(3)) <= 31:
            czesci.append(dopasowanie.group(3))
    return "-".join(czesci)


def wyciagnij_pdf(dane: bytes) -> WynikPliku:
    """Text and metadata of a PDF, trying every backend until one delivers."""
    ostatni = WynikPliku(uwaga="no PDF backend available — install pypdf")
    for _, funkcja in _SILNIKI_PDF:
        wynik = funkcja(dane)
        if wynik is None:
            continue
        ostatni = wynik
        if wynik.tekst.strip():
            break
    if not ostatni.tekst.strip() and not ostatni.uwaga:
        ostatni.uwaga = ("no text layer — the file is almost certainly a scan "
                         "and would need OCR")
    ostatni.tekst = _posprzataj(ostatni.tekst)
    return ostatni


# --------------------------------------------------------------------------
# Word and plain text
# --------------------------------------------------------------------------

def wyciagnij_docx(dane: bytes) -> WynikPliku:
    """A .docx is a zip of XML — no dependency needed to read the words out."""
    try:
        with zipfile.ZipFile(io.BytesIO(dane)) as archiwum:
            xml = archiwum.read("word/document.xml").decode("utf-8", "replace")
            rdzen = ""
            if "docProps/core.xml" in archiwum.namelist():
                rdzen = archiwum.read("docProps/core.xml").decode("utf-8", "replace")
    except Exception as exc:
        return WynikPliku(uwaga=f"unreadable .docx: {exc}", silnik="zipfile")

    xml = re.sub(r"</w:p>", "\n", xml)
    tekst = html_na_tekst(re.sub(r"<[^>]+>", " ", xml))

    meta = Metadane()
    if rdzen:
        for pole, atrybut in (("dc:title", "tytul"), ("dc:creator", "autor"),
                              ("dcterms:created", "data")):
            dopasowanie = re.search(rf"<{pole}[^>]*>(.*?)</{pole}>", rdzen, re.S)
            if not dopasowanie:
                continue
            wartosc = dopasowanie.group(1).strip()
            if atrybut == "tytul":
                meta.tytul = wartosc
            elif atrybut == "autor" and wartosc:
                meta.autorzy = [wartosc]
            else:
                meta.data = normalizuj_date(wartosc)
    return WynikPliku(tekst=_posprzataj(tekst), meta=meta, silnik="zipfile")


def wyciagnij_tekstowy(dane: bytes) -> WynikPliku:
    for kodowanie in ("utf-8", "cp1250", "latin-1"):
        try:
            return WynikPliku(tekst=_posprzataj(dane.decode(kodowanie)), silnik="text")
        except UnicodeDecodeError:
            continue
    return WynikPliku(tekst=_posprzataj(dane.decode("utf-8", "replace")), silnik="text")


def wyciagnij(url: str, dane: bytes) -> WynikPliku:
    """Dispatch on the file's extension."""
    koncowka = rozszerzenie(url)
    if koncowka in ROZSZERZENIA_WORD:
        return wyciagnij_docx(dane)
    if koncowka in ROZSZERZENIA_TEKST:
        return wyciagnij_tekstowy(dane)
    return wyciagnij_pdf(dane)


# --------------------------------------------------------------------------

def _posprzataj(tekst: str) -> str:
    """PDF extraction leaves hyphenated line breaks and ragged whitespace."""
    tekst = (tekst or "").replace("­", "")
    tekst = re.sub(r"(\w)-\n(\w)", r"\1\2", tekst)       # Familien-\nfest → Familienfest
    tekst = re.sub(r"[ \t ]+", " ", tekst)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip()


_DATA_Z_NAZWY = [
    re.compile(r"((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"),
    re.compile(r"((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])(?!\d)"),
    re.compile(r"(?<!\d)(0[1-9]|1[0-2])[-_.]((?:19|20)\d{2})(?!\d)"),
    re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)"),
]


def data_z_nazwy_pliku(url: str) -> str:
    """`info-links-05-2019.pdf` → 2019-05. Newsletters are named like that."""
    nazwa = re.sub(r"[?#].*$", "", url or "").rsplit("/", 1)[-1]
    for wzorzec in _DATA_Z_NAZWY:
        dopasowanie = wzorzec.search(nazwa)
        if not dopasowanie:
            continue
        grupy = dopasowanie.groups()
        if len(grupy) == 3:
            return f"{grupy[0]}-{grupy[1]}-{grupy[2]}"
        if len(grupy) == 2:
            rok, miesiac = (grupy if len(grupy[0]) == 4 else (grupy[1], grupy[0]))
            return f"{rok}-{miesiac}"
        return grupy[0]
    return ""
