# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A personal desktop viewer for a cross-country road trip (Charlottesville VA → Pacific Coast CA and back, May 28 – June 8, 2024). It reads photo/video metadata and displays media in a nostalgic Tkinter UI with a live route mini-map.

## Running the viewer

```
python viewer.py
```

Requires Python 3.9+ and Pillow (`pip install Pillow`). Tkinter is bundled with Python on Windows.

## Data files (all in the same directory as viewer.py)

| File | Purpose |
|---|---|
| `image_catalog.json` | 96 photo entries: filename, ISO timestamp with tz offset, lat/lon, human-readable location, one-sentence description |
| `day_by_day.json` | 11 day entries: label ("Day N — X to Y"), narrative summary, highlight photo filename, image list |
| `Timeline.json` | Full Google Maps location history (2013–2026). Only segments from `2024-05-28` to `2024-06-09` are used — ~245 segments, ~3600 GPS path points |
| `*.jpg / *.mp4` | ~123 media files; photos use Google Pixel `PXL_YYYYMMDD_HHMMSS` naming (UTC timestamps) |

## Key architecture notes

**Filename normalization**: catalog uses underscores (`PXL_…_NIGHT.jpg`) while actual files use dots (`PXL_….NIGHT.jpg`) or tildes for duplicates (`~2`). The `_norm()` function converts both to underscores for lookup.

**Timestamp authority**: `image_catalog.json` timestamps (ISO 8601 with tz offset, converted to UTC) are used over EXIF — they're pre-verified. Fallback: filename, then file mtime.

**GPS authority**: `image_catalog.json` lat/lon first, then interpolated from the nearest Timeline.json path point by UTC time.

**No reverse geocoding**: Location names are already in `image_catalog.json`. Don't add geocoding.

**Tkinter color constraint**: Only 6-digit `#rrggbb` hex colors work — no 8-digit RGBA.

## UI layout (1280×760, fixed)

```
┌─────────── top bar (50px) ────────────────────────────────────────┐
│            "2024 ROAD TRIP" title             counter             │
├────────── photo canvas (860px) ──────┬──── side panel (420px) ───┤
│                                      │  mini-map (396×210)        │
│   polaroid-style photo display       │  location / date / day     │
│   (white border, drop shadow,        │  description text          │
│    date caption, ★ badge)            │  ◀ ▶ nav buttons          │
├─────────────── film strip (110px) ────────────────────────────────┤
│  ▪▪▪ [thumb] [thumb] [★thumb] [thumb] ▪▪▪  (sprocket holes)      │
└───────────────────────────────────────────────────────────────────┘
```

Keys: ← → navigate, Space advances.
