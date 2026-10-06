#!/usr/bin/env python3
"""Inject data/cells.json into tools/decyzje.template.html → tools/decyzje.html (the decisions artifact)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data = (ROOT / "data" / "cells.json").read_text(encoding="utf-8").replace("</", "<\\/")
page = (ROOT / "tools" / "decyzje.template.html").read_text(encoding="utf-8").replace("__DATA__", data)
(ROOT / "tools" / "decyzje.html").write_text(page, encoding="utf-8")
print(f"tools/decyzje.html ({len(page) // 1024} KB)")
