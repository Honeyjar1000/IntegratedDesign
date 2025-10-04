from pathlib import Path

# ===================== CONFIG =====================
PI_HOST    = "172.20.10.12"               # Pi IP/hostname
PORT       = 5000
API_BASE   = f"http://{PI_HOST}:{PORT}"
STREAM_URL = f"{API_BASE}/video_feed"

# local folder to save photos
SAVE_DIR   = Path("D:/uni/ECE4179/project/client/imgs")

WINDOW_TITLE     = "Robot Control (Laptop UI)"
STREAM_RETRY_MS  = 1500                  # retry interval while waiting
LIVE_MAX_WIDTH   = 640                   # width to display live frames
PHOTO_MAX_WIDTH  = 320                   # width to display last photo
# ==================================================

SAVE_DIR.mkdir(parents=True, exist_ok=True)


# Test-NetConnection 172.20.10.9 -Port 5000     