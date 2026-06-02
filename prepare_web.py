#!/usr/bin/env python3
"""Generate web_catalog.json with actual disk filenames resolved for the web viewer."""
import json, re
from pathlib import Path

ROOT = Path(__file__).parent

EXCLUDED = {"20240603181018_204592.MP4", "GH016200_1717279531098.MP4"}

def _norm(name):
    stem, ext = name.rsplit(".", 1)
    stem = stem.replace("~", "_").replace(".", "_")
    return f"{stem}.{ext.lower()}"

file_lookup = {}
for p in ROOT.iterdir():
    if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".mp4", ".mov", ".ts"}:
        file_lookup[_norm(p.name)] = p.name

with open(ROOT / "image_catalog.json", encoding="utf-8") as f:
    catalog = json.load(f)

output = []
missing = []
for entry in catalog:
    fname = entry["filename"]
    if fname in EXCLUDED:
        continue
    actual = file_lookup.get(_norm(fname))
    if actual is None:
        missing.append(fname)
        continue
    out = dict(entry)
    out["src"] = actual
    output.append(out)

with open(ROOT / "web_catalog.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Generated web_catalog.json: {len(output)} entries")
if missing:
    print(f"WARNING — {len(missing)} catalog entries had no matching file on disk:")
    for m in missing:
        print(f"  {m}")
