#!/usr/bin/env python3
"""Inject data/site_data.json into site/index.template.html → site/index.html (redesign prototype)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data = (ROOT / "data" / "site_data.json").read_text(encoding="utf-8").replace("</", "<\\/")
page = (ROOT / "site" / "index.template.html").read_text(encoding="utf-8").replace("__DATA__", data)
(ROOT / "site" / "index.html").write_text(page, encoding="utf-8")
print(f"site/index.html ({len(page) // 1024} KB)")
