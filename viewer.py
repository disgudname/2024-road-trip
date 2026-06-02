#!/usr/bin/env python3
"""2024 Road Trip Viewer — relive the journey."""

import tkinter as tk
import json, datetime, re, threading
from pathlib import Path
from PIL import Image, ImageTk, ImageOps
import cv2

ROOT = Path(__file__).parent

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#18100a"
PANEL   = "#241508"
STRIP   = "#0e0905"
GOLD    = "#c8893a"
CREAM   = "#f0dfc0"
DIM     = "#856848"
POLAR   = "#fffef8"
MAP_BG  = "#0c0a07"
ROUTE   = "#c8893a"
DOT_C   = "#ff7040"
STAR_C  = "#ffe066"

# ── Layout ────────────────────────────────────────────────────────────────────
W_WIN   = 1280
H_WIN   = 760
H_TOP   = 50
H_STRIP = 110
H_MAIN  = H_WIN - H_TOP - H_STRIP   # 600
W_PHOTO = 860
W_SIDE  = W_WIN - W_PHOTO            # 420
W_MAP   = W_SIDE - 24
H_MAP   = 260
THUMB_W = 90
THUMB_H = 68

MAP_N, MAP_S     = 49.5, 24.5
MAP_W_L, MAP_E_L = -125.0, -66.5


# ── Data loading ──────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    stem, ext = name.rsplit(".", 1)
    stem = stem.replace("~", "_").replace(".", "_")
    return f"{stem}.{ext.lower()}"


def _parse_iso_utc(s: str) -> datetime.datetime:
    """ISO 8601 with offset → naive UTC datetime (for sorting)."""
    s = re.sub(r"\.\d+", "", s)
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-])(\d{2}):(\d{2})$", s)
    if m:
        base = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
        delta = datetime.timedelta(hours=int(m.group(3)), minutes=int(m.group(4)))
        return base - delta if m.group(2) == "+" else base + delta
    return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def _parse_iso_local(s: str) -> datetime.datetime:
    """ISO 8601 → naive local (wall-clock) datetime (for display)."""
    s = re.sub(r"\.\d+", "", s)
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})[+-]\d{2}:\d{2}$", s)
    if m:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def _parse_ts_from_name(name: str) -> datetime.datetime | None:
    m = re.match(r"PXL_(\d{8})_(\d{6})", name)
    if m:
        try:
            return datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    m = re.match(r"(\d{14})", name)
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return None


def _parse_point(s: str):
    try:
        a, b = s.replace("°", "").split(",")
        return float(a.strip()), float(b.strip())
    except Exception:
        return None, None


def load_catalog() -> dict:
    path = ROOT / "image_catalog.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    return {e["filename"]: e for e in entries}


def load_days() -> list:
    path = ROOT / "day_by_day.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_timeline_path() -> list:
    path = ROOT / "Timeline.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    pts = []
    for seg in data["semanticSegments"]:
        if not ("2024-05-28" <= seg["startTime"] <= "2024-06-09T23:59:59"):
            continue
        for pt in seg.get("timelinePath", []):
            lat, lon = _parse_point(pt["point"])
            if lat is not None:
                pts.append((_parse_iso_utc(pt["time"]), lat, lon))
    pts.sort(key=lambda x: x[0])
    return pts


def _closest_gps(dt_utc: datetime.datetime, path_pts: list):
    if not path_pts:
        return None
    best = min(path_pts, key=lambda p: abs((p[0] - dt_utc).total_seconds()))
    return best[1], best[2]


def collect_media(catalog: dict, path_pts: list) -> list:
    IMAGE_EXTS = {".jpg", ".jpeg"}
    VIDEO_EXTS = {".mp4", ".mov"}

    days = load_days()
    highlights: set[str] = set()
    day_by_date: dict[str, dict] = {}
    for d in days:
        day_by_date[d["day"]] = d
        fname = d.get("highlight", "").split("—")[0].strip().split(" ")[0].strip()
        highlights.add(fname)

    items = []
    for p in ROOT.iterdir():
        ext = p.suffix.lower()
        if ext not in IMAGE_EXTS | VIDEO_EXTS:
            continue

        is_video = ext in VIDEO_EXTS
        norm = _norm(p.name)
        meta = catalog.get(norm) or catalog.get(p.name)

        if meta and meta.get("timestamp"):
            dt_utc   = _parse_iso_utc(meta["timestamp"])
            dt_local = _parse_iso_local(meta["timestamp"])
        else:
            dt_utc = _parse_ts_from_name(p.name) or \
                     datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.UTC).replace(tzinfo=None)
            dt_local = dt_utc

        gps = (meta["lat"], meta["lon"]) if meta and meta.get("lat") else \
              _closest_gps(dt_utc, path_pts)

        day_str = meta.get("day") if meta else dt_utc.strftime("%Y-%m-%d")

        items.append({
            "path":      p,
            "dt":        dt_utc,
            "dt_local":  dt_local,
            "day":       day_str,
            "gps":       gps,
            "location":  meta["location"] if meta else None,
            "desc":      meta["description"] if meta else None,
            "is_video":  is_video,
            "highlight": p.name in highlights or norm in highlights,
            "day_meta":  day_by_date.get(day_str),
        })

    items.sort(key=lambda x: x["dt"])
    # Drop items with no catalog entry that fall outside the trip window
    TRIP_START = datetime.datetime(2024, 5, 27)
    TRIP_END   = datetime.datetime(2024, 6, 10)
    items = [i for i in items if i["location"] or (TRIP_START <= i["dt"] <= TRIP_END)]
    return items


# ── Map drawing ───────────────────────────────────────────────────────────────

def _proj(lat, lon, w, h):
    x = (lon - MAP_W_L) / (MAP_E_L - MAP_W_L) * w
    y = (MAP_N - lat) / (MAP_N - MAP_S) * h
    return x, y


def draw_map(canvas, path_pts: list, current_gps):
    canvas.delete("all")
    w, h = int(canvas["width"]), int(canvas["height"])
    canvas.create_rectangle(0, 0, w, h, fill=MAP_BG, outline="")

    for lat in range(25, 50, 5):
        y = (MAP_N - lat) / (MAP_N - MAP_S) * h
        canvas.create_line(0, y, w, y, fill="#1c1810")
    for lon in range(-120, -65, 10):
        x = (lon - MAP_W_L) / (MAP_E_L - MAP_W_L) * w
        canvas.create_line(x, 0, x, h, fill="#1c1810")

    pts = [_proj(lat, lon, w, h) for _, lat, lon in path_pts]
    if len(pts) >= 2:
        flat = [c for p in pts for c in p]
        canvas.create_line(flat, fill="#4a2d0a", width=3, smooth=True)
        canvas.create_line(flat, fill=ROUTE,    width=1, smooth=True)

    step = max(1, len(pts) // 70)
    for i in range(0, len(pts), step):
        x, y = pts[i]
        canvas.create_oval(x - 1.5, y - 1.5, x + 1.5, y + 1.5, fill=GOLD, outline="")

    if current_gps:
        x, y = _proj(*current_gps, w, h)
        canvas.create_oval(x - 8, y - 8, x + 8, y + 8, fill="#3a1a08", outline="")
        canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=DOT_C,    outline="")
        canvas.create_oval(x - 1, y - 1, x + 1, y + 1, fill="#ffffff", outline="")


# ── Video player ──────────────────────────────────────────────────────────────

class VideoPlayer:
    def __init__(self, app: "App", path: Path):
        self._app    = app
        self._cap    = cv2.VideoCapture(str(path))
        self._fps    = max(1.0, self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self._total  = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._frame  = 0
        self._paused = False
        self._ref    = None  # PhotoImage gc guard
        self._job    = None

    def start(self):
        self._tick()

    def toggle_pause(self):
        self._paused = not self._paused
        if not self._paused:
            self._tick()

    def stop(self):
        if self._job:
            self._app.after_cancel(self._job)
            self._job = None
        self._cap.release()

    def _tick(self):
        if self._paused:
            return
        ret, bgr = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._frame = 0
            ret, bgr = self._cap.read()
        if not ret:
            return

        self._frame = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

        c = self._app._cv_photo
        cw = c.winfo_width()  or W_PHOTO
        ch = c.winfo_height() or H_MAIN

        PROG_H = 28
        max_w  = cw - 40
        max_h  = ch - PROG_H - 20
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        tk_img = ImageTk.PhotoImage(img)
        self._ref = tk_img

        c.delete("all")
        cx, cy = cw // 2, (ch - PROG_H) // 2
        c.create_image(cx, cy, anchor="center", image=tk_img)

        # Progress bar
        progress = self._frame / max(1, self._total)
        bar_y = ch - PROG_H + 4
        bar_x0, bar_x1 = 30, cw - 30
        bar_w = bar_x1 - bar_x0
        c.create_rectangle(bar_x0, bar_y, bar_x1, bar_y + 10,
                           fill="#1a1208", outline="#2a1a08")
        if bar_w > 0 and progress > 0:
            c.create_rectangle(bar_x0, bar_y, bar_x0 + int(bar_w * progress), bar_y + 10,
                               fill=GOLD, outline="")

        # Pause overlay hint
        if self._paused:
            c.create_text(cw // 2, (ch - PROG_H) // 2,
                          text="▶", font=("Georgia", 72), fill="#ffffff40")

        delay = max(1, int(1000 / self._fps))
        self._job = self._app.after(delay, self._tick)


# ── App ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("2024 Road Trip")
        self.configure(bg=BG)
        self.resizable(True, True)
        self._fullscreen = False

        print("Loading timeline…")
        self._path_pts = load_timeline_path()
        print(f"  {len(self._path_pts)} GPS path points")

        print("Loading catalog…")
        catalog = load_catalog()
        print(f"  {len(catalog)} catalog entries")

        self._media = collect_media(catalog, self._path_pts)
        print(f"  {len(self._media)} media items")

        self._idx         = 0
        self._photo_ref   = None
        self._video: VideoPlayer | None = None
        self._thumb_pil: dict[int, Image.Image | None] = {}
        self._thumb_tk:  dict[int, ImageTk.PhotoImage]  = {}
        self._strip_hits: list[tuple[int, int, int]]    = []
        self._strip_pending  = False
        self._presentation   = False

        self._build()
        self.after(50, self._show)
        threading.Thread(target=self._load_thumbs, daemon=True).start()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        bar = tk.Frame(self, bg=PANEL, height=H_TOP)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._bar_frame = bar
        tk.Label(bar, text="2 0 2 4   R O A D   T R I P",
                 font=("Georgia", 18, "bold"), bg=PANEL, fg=GOLD
                 ).place(relx=0.5, rely=0.5, anchor="center")
        self._lbl_count = tk.Label(bar, text="", font=("Courier", 10), bg=PANEL, fg=DIM)
        self._lbl_count.place(relx=0.97, rely=0.5, anchor="e")

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)
        self._main_frame = main

        self._cv_photo = tk.Canvas(main, bg=BG, highlightthickness=0)
        self._cv_photo.pack(side="left", fill="both", expand=True)
        self._cv_photo.bind("<Button-1>", self._photo_click)
        self._cv_photo.bind("<Configure>", self._on_photo_resize)

        side = tk.Frame(main, bg=PANEL, width=W_SIDE)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self._side_frame = side

        self._cv_map = tk.Canvas(side, width=W_MAP, height=H_MAP, bg=MAP_BG,
                                 highlightthickness=1, highlightbackground=GOLD)
        self._cv_map.pack(padx=12, pady=(16, 8))

        self._v_loc  = tk.StringVar()
        self._v_date = tk.StringVar()
        self._v_day  = tk.StringVar()
        self._v_desc = tk.StringVar()

        tk.Label(side, textvariable=self._v_loc, font=("Georgia", 13, "bold"),
                 bg=PANEL, fg=CREAM, wraplength=W_SIDE - 24, justify="center"
                 ).pack(pady=(6, 0))
        tk.Label(side, textvariable=self._v_date, font=("Courier", 11),
                 bg=PANEL, fg="#a08860").pack(pady=2)

        tk.Frame(side, bg=GOLD, height=1).pack(fill="x", padx=16, pady=6)

        tk.Label(side, textvariable=self._v_day, font=("Georgia", 12, "italic"),
                 bg=PANEL, fg=GOLD, wraplength=W_SIDE - 24, justify="center"
                 ).pack(pady=(0, 6))
        tk.Label(side, textvariable=self._v_desc, font=("Georgia", 11, "italic"),
                 bg=PANEL, fg="#c09a6a", wraplength=W_SIDE - 24, justify="left"
                 ).pack(padx=14, anchor="w")

        nav = tk.Frame(side, bg=PANEL)
        nav.pack(side="bottom", pady=14)
        btn = dict(bg=PANEL, fg=GOLD, font=("Georgia", 26), bd=0,
                   activebackground=PANEL, activeforeground=CREAM,
                   cursor="hand2", relief="flat")
        tk.Button(nav, text="◀", command=self._prev, **btn).pack(side="left", padx=18)
        tk.Button(nav, text="▶", command=self._next, **btn).pack(side="left", padx=18)

        strip_frame = tk.Frame(self, bg=STRIP, height=H_STRIP)
        strip_frame.pack(fill="x")
        self._strip_frame = strip_frame
        strip_frame.pack_propagate(False)
        self._cv_strip = tk.Canvas(strip_frame, bg=STRIP,
                                   height=H_STRIP, highlightthickness=0)
        self._cv_strip.pack(fill="both", expand=True)
        self._cv_strip.bind("<Button-1>", self._strip_click)
        self._cv_strip.bind("<Configure>", lambda e: self._draw_strip())

        self.bind("<Left>",   lambda e: self._prev())
        self.bind("<Right>",  lambda e: self._next())
        self.bind("<space>",  self._space_key)
        self.bind("<n>",      lambda e: self._open_note_dialog())
        self.bind("<N>",      lambda e: self._open_note_dialog())
        self.bind("<p>",      lambda e: self._toggle_presentation())
        self.bind("<P>",      lambda e: self._toggle_presentation())
        self.bind("<F11>",    lambda e: self._toggle_fullscreen())
        self.bind("<Escape>", lambda e: self._escape_key())

        self.geometry(f"{W_WIN}x{H_WIN}")

    # ── Show current item ─────────────────────────────────────────────────────

    def _show(self):
        if not self._media:
            return
        self._stop_video()
        item = self._media[self._idx]

        self._lbl_count.config(text=f"{self._idx + 1} / {len(self._media)}")

        loc = item["location"] or ""
        prefix = "★  " if item["highlight"] else "📍  "
        self._v_loc.set(f"{prefix}{loc}" if loc else "")

        # Local (wall-clock) time so it matches the catalog day label
        d = item["dt_local"]
        hour = int(d.strftime("%I"))
        ampm = d.strftime("%p")
        self._v_date.set(f"{d.strftime('%B')} {d.day}, {d.year}   {hour}:{d.strftime('%M')} {ampm}")

        dm = item["day_meta"]
        if dm:
            self._v_day.set(dm["label"])
        else:
            day0 = self._media[0]["dt"].date()
            n = (item["dt"].date() - day0).days + 1
            self._v_day.set(f"Day {n}")

        self._v_desc.set(item["desc"] or "")

        draw_map(self._cv_map, self._path_pts, item["gps"])
        self._draw_photo(item)
        self._draw_strip()

    # ── Photo / video display ─────────────────────────────────────────────────

    def _draw_photo(self, item):
        c = self._cv_photo
        c.delete("all")

        if item["is_video"]:
            vp = VideoPlayer(self, item["path"])
            self._video = vp
            vp.start()
            return

        try:
            img = ImageOps.exif_transpose(Image.open(item["path"]))

            cw = c.winfo_width()  or W_PHOTO
            ch = c.winfo_height() or H_MAIN

            BORDER_S = 18
            CAPTION  = 70
            max_w = cw - 100
            max_h = ch - 90 - CAPTION
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            pw, ph = img.size

            fw = pw + BORDER_S * 2
            fh = ph + BORDER_S + CAPTION
            fx = (cw - fw) // 2
            fy = (ch - fh) // 2

            c.create_rectangle(fx + 9, fy + 9, fx + fw + 9, fy + fh + 9, fill="#000000")
            c.create_rectangle(fx, fy, fx + fw, fy + fh, fill=POLAR, outline="")

            tk_img = ImageTk.PhotoImage(img)
            self._photo_ref = tk_img
            c.create_image(fx + BORDER_S, fy + BORDER_S, anchor="nw", image=tk_img)

            loc_raw = item.get("location") or ""
            loc_text = loc_raw.split(" — ")[0]   # strip " — VIDEO" / " — DASHCAM" etc.
            if len(loc_text) > 38:
                loc_text = loc_text[:36] + "…"
            d = item["dt_local"]
            date_text = f"{d.strftime('%b')} {d.day}, {d.year}"
            cap_top = fy + BORDER_S + ph
            c.create_text(fx + fw // 2, cap_top + 22,
                          text=loc_text, font=("Georgia", 11, "italic"), fill="#55442a")
            c.create_text(fx + fw // 2, cap_top + 46,
                          text=date_text, font=("Georgia", 9, "italic"), fill="#887050")

            if item["highlight"]:
                c.create_text(fx + fw - 12, fy + 10, text="★",
                              font=("Georgia", 14), fill=STAR_C)

        except Exception as e:
            cw = c.winfo_width()  or W_PHOTO
            ch = c.winfo_height() or H_MAIN
            c.create_text(cw // 2, ch // 2,
                          text=f"⚠  Could not load image\n{e}",
                          font=("Courier", 11), fill=DIM, width=cw - 80)

    def _stop_video(self):
        if self._video:
            self._video.stop()
            self._video = None

    # ── Film strip ────────────────────────────────────────────────────────────

    def _load_thumbs(self):
        for i, item in enumerate(self._media):
            if i in self._thumb_pil:
                continue
            if item["is_video"]:
                # Grab first frame with cv2 for the thumbnail
                try:
                    cap = cv2.VideoCapture(str(item["path"]))
                    ret, bgr = cap.read()
                    cap.release()
                    if ret:
                        img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                        img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                        self._thumb_pil[i] = img
                    else:
                        self._thumb_pil[i] = None
                except Exception:
                    self._thumb_pil[i] = None
            else:
                try:
                    img = ImageOps.exif_transpose(Image.open(item["path"]))
                    img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                    self._thumb_pil[i] = img
                except Exception:
                    self._thumb_pil[i] = None
            self._request_strip_update()

    def _request_strip_update(self):
        """Debounced strip redraw — collapses many rapid calls into one."""
        if not self._strip_pending:
            self._strip_pending = True
            self.after(80, self._flush_strip_update)

    def _flush_strip_update(self):
        self._strip_pending = False
        self._draw_strip()

    def _draw_strip(self):
        c = self._cv_strip
        c.delete("all")
        self._strip_hits.clear()
        # Don't clear _thumb_tk here — keep existing PhotoImages alive

        sw = c.winfo_width() or W_WIN
        sh = H_STRIP
        GAP = 6

        HOLE_W, HOLE_H, SPACING = 8, 14, 28
        for x in range(4, sw, SPACING):
            c.create_rectangle(x, 4, x + HOLE_W, 4 + HOLE_H,
                               fill="#000000", outline="")
            c.create_rectangle(x, sh - 4 - HOLE_H, x + HOLE_W, sh - 4,
                               fill="#000000", outline="")

        n_vis = sw // (THUMB_W + GAP) + 2
        start = max(0, self._idx - n_vis // 2)
        end   = min(len(self._media), start + n_vis)
        if end == len(self._media):
            start = max(0, end - n_vis)

        top = (sh - THUMB_H) // 2
        new_tk: dict[int, ImageTk.PhotoImage] = {}

        for j, i in enumerate(range(start, end)):
            x0 = j * (THUMB_W + GAP) + GAP
            x1 = x0 + THUMB_W

            if i == self._idx:
                c.create_rectangle(x0 - 3, top - 3, x1 + 3, top + THUMB_H + 3,
                                   fill=GOLD, outline="")

            pil = self._thumb_pil.get(i)
            if pil is not None:
                # Reuse existing PhotoImage to avoid churn
                tk_t = self._thumb_tk.get(i) or ImageTk.PhotoImage(pil)
                new_tk[i] = tk_t
                c.create_image(x0, top, anchor="nw", image=tk_t)
            else:
                fill = "#1a1208" if self._media[i]["is_video"] else "#1c1208"
                c.create_rectangle(x0, top, x1, top + THUMB_H,
                                   fill=fill, outline="#2a1a08")
                if self._media[i]["is_video"]:
                    c.create_text((x0 + x1) // 2, top + THUMB_H // 2,
                                  text="▶", font=("Georgia", 16), fill=GOLD)

            if self._media[i]["highlight"]:
                c.create_text(x1 - 4, top + 6, text="★",
                              font=("Georgia", 8), fill=STAR_C, anchor="e")

            # Overlay a small film-frame border
            c.create_rectangle(x0, top, x1, top + THUMB_H,
                               outline="#33221a", fill="")

            self._strip_hits.append((x0, x1, i))

        self._thumb_tk = new_tk  # replace; only keep visible ones

    # ── Navigation ────────────────────────────────────────────────────────────

    def _prev(self):
        if self._idx > 0:
            self._idx -= 1
            self._show()

    def _next(self):
        if self._idx < len(self._media) - 1:
            self._idx += 1
            self._show()

    def _space_key(self, _event=None):
        if self._video:
            self._video.toggle_pause()
        else:
            self._next()

    def _strip_click(self, event):
        for x0, x1, i in self._strip_hits:
            if x0 <= event.x <= x1:
                self._idx = i
                self._show()
                return

    def _photo_click(self, _):
        if self._video:
            self._video.toggle_pause()

    # ── Resize / fullscreen / presentation ───────────────────────────────────

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def _toggle_presentation(self):
        self._presentation = not self._presentation
        if self._presentation:
            self._bar_frame.pack_forget()
            self._side_frame.pack_forget()
            self._strip_frame.pack_forget()
        else:
            self._bar_frame.pack(fill="x", before=self._main_frame)
            self._side_frame.pack(side="left", fill="y")
            self._strip_frame.pack(fill="x")
        self.after(50, self._show)

    def _escape_key(self):
        if self._fullscreen:
            self._fullscreen = False
            self.attributes("-fullscreen", False)
        elif self._presentation:
            self._toggle_presentation()

    def _on_photo_resize(self, _event=None):
        if hasattr(self, "_resize_job"):
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._show)

    # ── Caption notes ─────────────────────────────────────────────────────────

    def _open_note_dialog(self):
        if not self._media:
            return
        item = self._media[self._idx]
        filename = item["path"].name
        current_desc = item["desc"] or "(no description)"

        dlg = tk.Toplevel(self)
        dlg.title("Caption Note")
        dlg.configure(bg=PANEL)
        dlg.resizable(False, False)
        dlg.grab_set()

        pad = dict(padx=16, pady=6)

        tk.Label(dlg, text=filename, font=("Courier", 9), bg=PANEL, fg=GOLD,
                 wraplength=460, justify="left").pack(anchor="w", **pad)

        tk.Frame(dlg, bg=GOLD, height=1).pack(fill="x", padx=16, pady=2)

        tk.Label(dlg, text="Current description:", font=("Georgia", 9, "bold"),
                 bg=PANEL, fg=DIM).pack(anchor="w", padx=16, pady=(8, 0))
        tk.Label(dlg, text=current_desc, font=("Georgia", 9, "italic"),
                 bg=PANEL, fg=CREAM, wraplength=460, justify="left"
                 ).pack(anchor="w", padx=16, pady=(2, 8))

        tk.Frame(dlg, bg=GOLD, height=1).pack(fill="x", padx=16, pady=2)

        tk.Label(dlg, text="Your note:", font=("Georgia", 9, "bold"),
                 bg=PANEL, fg=DIM).pack(anchor="w", padx=16, pady=(8, 0))

        txt = tk.Text(dlg, width=52, height=4, font=("Georgia", 10),
                      bg="#1a1008", fg=CREAM, insertbackground=CREAM,
                      relief="flat", padx=8, pady=6, wrap="word")
        txt.pack(padx=16, pady=(4, 12))
        txt.focus_set()

        def _save():
            note = txt.get("1.0", "end").strip()
            if note:
                notes_path = ROOT / "caption_notes.txt"
                with open(notes_path, "a", encoding="utf-8") as f:
                    f.write(f"{filename} | {note}\n")
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=PANEL)
        btn_row.pack(pady=(0, 14))
        btn = dict(font=("Georgia", 11), bd=0, relief="flat", cursor="hand2",
                   activebackground=PANEL)
        tk.Button(btn_row, text="Save", command=_save,
                  bg=GOLD, fg=BG, activeforeground=BG, **btn
                  ).pack(side="left", padx=12, ipadx=14, ipady=4)
        tk.Button(btn_row, text="Cancel", command=dlg.destroy,
                  bg=PANEL, fg=DIM, activeforeground=CREAM, **btn
                  ).pack(side="left", padx=12, ipadx=14, ipady=4)

        dlg.bind("<Return>",  lambda e: (not e.widget == txt) and _save())
        dlg.bind("<Escape>",  lambda e: dlg.destroy())


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
