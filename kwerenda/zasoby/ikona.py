# -*- coding: utf-8 -*-
"""Draw the Kwerenda icon — pure Python, no image libraries required.

Produces a PNG (and an ICO wrapping it) so the desktop shortcut has a real icon
on every platform. Anti-aliasing is done by supersampling each pixel 3×3.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import List, Tuple

TLO = (250, 248, 245)          # warm paper
TLO_CIEMNE = (236, 232, 225)
ATRAMENT = (26, 23, 20)
CZERWIEN = (139, 26, 26)       # the accent used throughout the interface

Kolor = Tuple[int, int, int]
KolorA = Tuple[int, int, int, int]


def _mieszaj(spod: Kolor, wierzch: Kolor, krycie: float) -> Kolor:
    return tuple(int(round(s * (1 - krycie) + w * krycie))
                 for s, w in zip(spod, wierzch))


def _w_zaokraglonym_kwadracie(x: float, y: float, bok: float, promien: float) -> bool:
    margines = bok * 0.04
    lewa, gora = margines, margines
    prawa, dol = bok - margines, bok - margines
    if not (lewa <= x <= prawa and gora <= y <= dol):
        return False
    for cx, cy in ((lewa + promien, gora + promien), (prawa - promien, gora + promien),
                   (lewa + promien, dol - promien), (prawa - promien, dol - promien)):
        if (x < cx and y < cy) or (x > cx and y < cy) or (x < cx and y > cy) or (x > cx and y > cy):
            if abs(x - cx) > promien or abs(y - cy) > promien:
                continue
    # simple rounded-corner test
    for cx, cy, kier_x, kier_y in ((lewa + promien, gora + promien, -1, -1),
                                   (prawa - promien, gora + promien, 1, -1),
                                   (lewa + promien, dol - promien, -1, 1),
                                   (prawa - promien, dol - promien, 1, 1)):
        if (x - cx) * kier_x > 0 and (y - cy) * kier_y > 0:
            if math.hypot(x - cx, y - cy) > promien:
                return False
    return True


def _pierscien(x: float, y: float, sx: float, sy: float, r: float, grubosc: float) -> bool:
    d = math.hypot(x - sx, y - sy)
    return r - grubosc / 2 <= d <= r + grubosc / 2


def _odcinek(x: float, y: float, ax: float, ay: float, bx: float, by: float,
             grubosc: float) -> bool:
    dx, dy = bx - ax, by - ay
    dlugosc2 = dx * dx + dy * dy
    if dlugosc2 == 0:
        return math.hypot(x - ax, y - ay) <= grubosc / 2
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / dlugosc2))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy)) <= grubosc / 2


def narysuj(bok: int = 256) -> List[List[KolorA]]:
    """A magnifying glass over a page of text — a query, in one picture."""
    s = bok
    sx, sy, r = s * 0.44, s * 0.42, s * 0.235
    grubosc = s * 0.055
    uchwyt_a = (sx + r * 0.72, sy + r * 0.72)
    uchwyt_b = (s * 0.80, s * 0.80)

    # lines of "text" on the page behind the lens
    linie = [(s * 0.30, s * 0.34, s * 0.62), (s * 0.30, s * 0.43, s * 0.66),
             (s * 0.30, s * 0.52, s * 0.55)]

    piksele: List[List[KolorA]] = []
    podprobki = [(-1 / 3, -1 / 3), (0, -1 / 3), (1 / 3, -1 / 3),
                 (-1 / 3, 0), (0, 0), (1 / 3, 0),
                 (-1 / 3, 1 / 3), (0, 1 / 3), (1 / 3, 1 / 3)]

    for py in range(s):
        wiersz: List[KolorA] = []
        for px in range(s):
            akumulator = [0.0, 0.0, 0.0]
            krycie = 0.0
            for dx, dy in podprobki:
                x, y = px + 0.5 + dx, py + 0.5 + dy
                # Outside the rounded tile the icon is transparent, so the corners
                # do not show up as black squares on a desktop.
                if not _w_zaokraglonym_kwadracie(x, y, s, s * 0.18):
                    continue
                krycie += 1.0
                kolor = TLO
                # the page
                if s * 0.26 <= x <= s * 0.74 and s * 0.24 <= y <= s * 0.76:
                    kolor = TLO_CIEMNE
                for x0, y0, x1 in linie:
                    if x0 <= x <= x1 and abs(y - y0) <= s * 0.018:
                        kolor = _mieszaj(kolor, ATRAMENT, 0.55)
                # the lens brightens what it covers
                if math.hypot(x - sx, y - sy) < r - grubosc / 2:
                    kolor = _mieszaj(kolor, (255, 255, 255), 0.35)
                if _pierscien(x, y, sx, sy, r, grubosc):
                    kolor = CZERWIEN
                if _odcinek(x, y, *uchwyt_a, *uchwyt_b, grubosc * 1.15):
                    kolor = CZERWIEN
                akumulator = [a + k for a, k in zip(akumulator, kolor)]
            if krycie == 0:
                wiersz.append((0, 0, 0, 0))
            else:
                skladowe = [int(round(a / krycie)) for a in akumulator]
                wiersz.append((*skladowe, int(round(255 * krycie / len(podprobki)))))
        piksele.append(wiersz)
    return piksele


def zapisz_png(piksele: List[List[KolorA]], sciezka: Path) -> Path:
    wysokosc, szerokosc = len(piksele), len(piksele[0])
    surowe = bytearray()
    for wiersz in piksele:
        surowe.append(0)                      # filter: none
        for r, g, b, a in wiersz:
            surowe += bytes((r, g, b, a))

    def kawalek(typ: bytes, dane: bytes) -> bytes:
        return (struct.pack(">I", len(dane)) + typ + dane
                + struct.pack(">I", zlib.crc32(typ + dane) & 0xFFFFFFFF))

    naglowek = struct.pack(">IIBBBBB", szerokosc, wysokosc, 8, 6, 0, 0, 0)   # RGBA
    plik = (b"\x89PNG\r\n\x1a\n" + kawalek(b"IHDR", naglowek)
            + kawalek(b"IDAT", zlib.compress(bytes(surowe), 9))
            + kawalek(b"IEND", b""))
    sciezka.write_bytes(plik)
    return sciezka


def zapisz_ico(png: bytes, sciezka: Path, bok: int = 256) -> Path:
    """An ICO may embed a PNG directly — that is what Windows reads for 256 px."""
    naglowek = struct.pack("<HHH", 0, 1, 1)
    wpis = struct.pack("<BBBBHHII", 0 if bok >= 256 else bok, 0 if bok >= 256 else bok,
                       0, 0, 1, 32, len(png), 22)
    sciezka.write_bytes(naglowek + wpis + png)
    return sciezka


def zbuduj(katalog: Path | None = None, bok: int = 256) -> dict:
    katalog = Path(katalog or Path(__file__).parent)
    katalog.mkdir(parents=True, exist_ok=True)
    piksele = narysuj(bok)
    png = zapisz_png(piksele, katalog / "kwerenda.png")
    ico = zapisz_ico(png.read_bytes(), katalog / "kwerenda.ico", bok)
    return {"png": png, "ico": ico}


if __name__ == "__main__":
    wynik = zbuduj()
    for nazwa, sciezka in wynik.items():
        print(f"{nazwa}: {sciezka} ({sciezka.stat().st_size} B)")
