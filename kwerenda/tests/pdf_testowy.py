# -*- coding: utf-8 -*-
"""Build a small, real PDF — no libraries, so the tests owe nothing to one.

Produces a genuine PDF 1.4 with a text layer and document information, which is
what a party newsletter looks like to the scraper. `zbuduj_skan` produces the
opposite case: a page with no text on it at all, the way a scanned issue comes.
"""

from __future__ import annotations

from typing import List, Sequence


def _escape(tekst: str) -> bytes:
    """PDF string literals escape backslashes and both parentheses."""
    podmiana = tekst.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return podmiana.encode("cp1252", "replace")        # matches WinAnsiEncoding


def _strumien_tekstu(linie: Sequence[str]) -> bytes:
    kawalki = [b"BT", b"/F1 12 Tf", b"50 780 Td", b"14 TL"]
    for indeks, linia in enumerate(linie):
        if indeks:
            kawalki.append(b"T*")
        kawalki.append(b"(" + _escape(linia) + b") Tj")
    kawalki.append(b"ET")
    return b"\n".join(kawalki)


def zbuduj_pdf(linie: Sequence[str], tytul: str = "", autor: str = "",
               data: str = "") -> bytes:
    """A one-page PDF whose text really can be extracted."""
    return _zloz(_strumien_tekstu(linie), tytul, autor, data)


def zbuduj_skan(tytul: str = "") -> bytes:
    """A page with graphics but no text layer — what a scan looks like."""
    return _zloz(b"0.5 g\n50 700 300 60 re\nf", tytul, "", "")


def _zloz(strumien: bytes, tytul: str, autor: str, data: str) -> bytes:
    obiekty: List[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(strumien)).encode() + b" >>\nstream\n"
        + strumien + b"\nendstream",
    ]
    info = []
    if tytul:
        info.append(b"/Title (" + _escape(tytul) + b")")
    if autor:
        info.append(b"/Author (" + _escape(autor) + b")")
    if data:
        info.append(b"/CreationDate (D:" + data.encode() + b"000000+02'00')")
    obiekty.append(b"<< " + b" ".join(info) + b" >>" if info else b"<< >>")

    plik = bytearray(b"%PDF-1.4\n")
    offsety = []
    for numer, cialo in enumerate(obiekty, start=1):
        offsety.append(len(plik))
        plik += str(numer).encode() + b" 0 obj\n" + cialo + b"\nendobj\n"

    start_xref = len(plik)
    plik += b"xref\n0 " + str(len(obiekty) + 1).encode() + b"\n"
    plik += b"0000000000 65535 f \n"
    for offset in offsety:
        plik += f"{offset:010d} 00000 n \n".encode()
    plik += (b"trailer\n<< /Size " + str(len(obiekty) + 1).encode()
             + b" /Root 1 0 R /Info " + str(len(obiekty)).encode() + b" 0 R >>\n"
             b"startxref\n" + str(start_xref).encode() + b"\n%%EOF\n")
    return bytes(plik)
