# train.py
# Examples:
#   python train.py --dataset aug                      # auto: GPU if available, else CPU
#   python train.py --dataset no_aug --epochs 150
#   python train.py --dataset no_aug --device 0        # force CUDA GPU 0
#   python train.py --dataset aug --strict_v12         # require YOLOv12 or fail

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys
import os

def parse_args():
    p = argparse.ArgumentParser("Train YOLO on aug/no_aug; saves to models/")
    p.add_argument("--dataset", default="final")
    # Try v12 by default; will fall back to v11 if not supported on your install
    p.add_argument("--weights", default="yolov12n.pt",
                   help="Pretrained base; auto-download if recognized (e.g., yolov12n.pt, yolo11n.pt, yolov8n.pt)")
    p.add_argument("--strict_v12", action="store_true",
                   help="Fail instead of falling back if yolov12* is not available.")
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=-1)    # -1 = auto
    p.add_argument("--device", default="auto",
                   help="'auto' (default), GPU like '0' or '0,1', or 'cpu'")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--patience", type=int, default=50)
    p.add_argument("--lr0", type=float, default=0.01)
    p.add_argument("--name", default=None)
    return p.parse_args()

def auto_select_device(pref: str) -> str:
    """Return a device string Ultralytics/torch understands."""
    if pref and pref.lower() != "auto":
        return pref
    try:
        import torch
        # Prefer CUDA if present
        if torch.cuda.is_available():
            return "0"  # first CUDA GPU
        # (Optional) Apple MPS support
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"

def main():
    args = parse_args()
    device = auto_select_device(args.device)

    try:
        from ultralytics import YOLO, __version__ as ulx_ver
        import torch
    except Exception:
        print("[error] ultralytics not installed. Install with:\n  pip install -U ultralytics\n", file=sys.stderr)
        raise

    print(f"[info] Ultralytics {ulx_ver}")
    print(f"[info] Using device: {device}")

    root = Path(__file__).resolve().parent
    data_yaml = root / "data" / args.dataset / "data.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(f"Missing dataset YAML: {data_yaml}")

    models_dir = root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_name = args.name or f"{args.dataset}_{Path(args.weights).stem}_{stamp}"

    # Load YOLO model (prefers v12, fallback to v11)
    def _try_load(w):
        print(f"[info] Loading pretrained: {w}")
        from ultralytics import YOLO
        return YOLO(w)

    try:
        model = _try_load(args.weights)
    except Exception:
        print("[warn] Fallback to YOLOv11n.pt")
        model = _try_load("yolo11n.pt")

    # cuDNN stability
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    imgsz = args.imgsz
    batch = args.batch if args.batch > 0 else 8
    amp_mode = True

    # --- attempt training loop with fallback scaling ---
    while True:
        try:
            print(f"[info] Training with imgsz={imgsz}, batch={batch}, amp={amp_mode}")
            results = model.train(
                data=str(data_yaml),
                epochs=args.epochs,
                imgsz=imgsz,
                batch=batch,
                device=device,
                workers=args.workers,
                seed=args.seed,
                patience=args.patience,
                lr0=args.lr0,
                project=str(models_dir),
                name=run_name,
                pretrained=True,
                save=True,
                verbose=True,
                amp=amp_mode,
            )
            break  # success → exit loop

        except RuntimeError as e:
            if "out of memory" in str(e):
                torch.cuda.empty_cache()
                print("[warn] CUDA OOM → reducing batch or image size and retrying...")
                if batch > 2:
                    batch = max(1, batch // 2)
                elif imgsz > 320:
                    imgsz = int(imgsz * 0.75)
                elif amp_mode:
                    print("[warn] Disabling AMP to save VRAM")
                    amp_mode = False
                else:
                    print("[error] Still OOM even at minimal settings. Exiting.")
                    raise
            else:
                raise

    # Copy best/last weights for convenience
    run_dir = models_dir / run_name
    weights_dir = run_dir / "weights"
    for tag in ("best", "last"):
        src = weights_dir / f"{tag}.pt"
        if src.exists():
            shutil.copy2(src, models_dir / f"{run_name}_{tag}.pt")
            print(f"[info] Copied {tag} weights → {models_dir / f'{run_name}_{tag}.pt'}")

    print("\n=== Training complete ===")
    print(f"Run directory: {run_dir}")

if __name__ == "__main__":
    main()
