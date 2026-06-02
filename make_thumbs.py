#!/usr/bin/env python3
"""Pre-generate 180x136 thumbnails for all catalog entries (photos + videos)."""
from pathlib import Path
from PIL import Image
import json

ROOT = Path(__file__).parent
THUMB_DIR = ROOT / "thumbs"
THUMB_DIR.mkdir(exist_ok=True)

TW, TH = 180, 136   # 2x for retina; displayed at 90x68

def thumb_name(src):
    return src.rsplit('.', 1)[0] + '.jpg'

def crop_and_resize(img):
    iw, ih = img.size
    if iw / ih > TW / TH:
        new_w = int(ih * TW / TH)
        img = img.crop(((iw - new_w) // 2, 0, (iw - new_w) // 2 + new_w, ih))
    else:
        new_h = int(iw * TH / TW)
        img = img.crop((0, (ih - new_h) // 2, iw, (ih - new_h) // 2 + new_h))
    return img.resize((TW, TH), Image.LANCZOS)

def photo_thumb(src_path, dest_path):
    with Image.open(src_path) as img:
        crop_and_resize(img.convert('RGB')).save(dest_path, 'JPEG', quality=78, optimize=True)

def video_thumb(src_path, dest_path):
    import cv2
    cap = cv2.VideoCapture(str(src_path))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return False
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    crop_and_resize(img).save(dest_path, 'JPEG', quality=78, optimize=True)
    return True

with open(ROOT / "web_catalog.json", encoding="utf-8") as f:
    catalog = json.load(f)

done = skipped = errors = 0
for entry in catalog:
    src = entry["src"]
    dest = THUMB_DIR / thumb_name(src)
    if dest.exists():
        skipped += 1
        continue
    src_path = ROOT / src
    if not src_path.exists():
        print(f"  MISSING  {src}")
        errors += 1
        continue
    ext = src.rsplit('.', 1)[-1].lower()
    try:
        if ext in ('jpg', 'jpeg', 'png'):
            photo_thumb(src_path, dest)
            done += 1
        elif ext in ('mp4', 'mov', 'ts'):
            if video_thumb(src_path, dest):
                done += 1
            else:
                print(f"  NO FRAME {src}")
                errors += 1
        print(f"  {done+skipped+errors}/{len(catalog)}  {src}", end='\r')
    except Exception as e:
        print(f"  ERROR    {src}: {e}")
        errors += 1

print(f"\nDone: {done} generated, {skipped} already existed, {errors} errors")
