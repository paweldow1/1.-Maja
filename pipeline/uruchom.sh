#!/bin/sh
# Caly potok, w kolejnosci. Kazdy krok czyta output/ poprzedniego, wiec
# kolejnosc nie jest dowolna -- w szczegolnosci zastosuj_decyzje.py musi isc
# po join.py i dzielnice.py (inaczej nadpisze decyzje swiezym parsowaniem),
# a rozbij_upamietnienia.py po nim (tabela ceremonii wygrywa z decyzja).
#
# Usage: sh uruchom.sh
set -e
cd "$(dirname "$0")"

echo "=== 1. mapy"
python3 parse_warszawa.py input/warszawa/umap_backup_1-maja_warszawa9.umap
python3 parse_berlin.py input/berlin input/berlin/umap_backup_1-mai-berlin_aktualna16.umap

echo "=== 2. roczniki i frekwencja"
python3 parse_roczniki.py input/PL_1990-2019.md input/DE_1990-2019.md
python3 parse_frekwencja.py input

echo "=== 3. zlaczenie i geografia"
# before the join, so it matches on the corrected actors
python3 zastosuj_decyzje.py --miasta
python3 join.py
python3 dzielnice.py

echo "=== 4. decyzje z kartoteki"
python3 zastosuj_decyzje.py
python3 rozbij_upamietnienia.py
python3 identyfikatory.py

echo "=== 5. tabele pochodne"
python3 brakujace.py
python3 scenariusz.py
python3 pokrycie.py
python3 pole.py

echo "=== 6. dane dla kartoteki"
python3 weryfikacja_dane.py
python3 - <<'PY'
from pathlib import Path
szablon = Path("weryfikacja_szablon.html").read_text(encoding="utf-8")
dane = Path("output/weryfikacja_dane.json").read_text(encoding="utf-8")
Path("output/weryfikacja.html").write_text(szablon.replace("__DANE__", dane),
                                           encoding="utf-8")
print("weryfikacja.html gotowa")
PY
