from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageTk
import cv2

def ts_filename(prefix="photo", ext="jpg"):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d-%H%M%S_%f')[:-3]}.{ext}"

def pil_from_bgr(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)

def resize_to_width(im: Image.Image, maxw: int) -> Image.Image:
    if im.width > maxw:
        ratio = maxw / im.width
        im = im.resize((maxw, int(im.height * ratio)), Image.LANCZOS)
    return im

def banner_image(lines, w=640, h=480):
    img = Image.new("RGB", (w, h), (17, 17, 17))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    total_h = sum(draw.textbbox((0,0), t, font=font)[3] for t in lines) + 10*(len(lines)-1)
    y = (h - total_h) // 2
    for t in lines:
        tw = draw.textbbox((0,0), t, font=font)[2]
        x = (w - tw)//2
        draw.text((x, y), t, fill=(200,200,200), font=font)
        y += draw.textbbox((0,0), t, font=font)[3] + 10
    return img

def save_bgr(frame_bgr, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return cv2.imwrite(str(out_path), frame_bgr)
