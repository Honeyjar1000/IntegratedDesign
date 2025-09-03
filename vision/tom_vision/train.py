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
    p.add_argument("--dataset", choices=["aug", "no_aug"], default="aug")
    # Try v12 by default; will fall back to v11 if not supported on your install
    p.add_argument("--weights", default="yolov12n.pt",
                   help="Pretrained base; auto-download if recognized (e.g., yolov12n.pt, yolo11n.pt, yolov8n.pt)")
    p.add_argument("--strict_v12", action="store_true",
                   help="Fail instead of falling back if yolov12* is not available.")
    p.add_argument("--epochs", type=int, default=100)
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
    except Exception:
        print("[error] ultralytics not installed. Install with:\n  pip install -U ultralytics\n", file=sys.stderr)
        raise

    # Helpful runtime printouts
    print(f"[info] Ultralytics {ulx_ver}")
    print(f"[info] Using device: {device}")

    # Check dataset yaml
    root = Path(__file__).resolve().parent
    data_yaml = root / "data" / args.dataset / "data.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"Missing dataset YAML: {data_yaml}\n"
            "Your data/<dataset>/ must contain data.yaml with train/val paths, nc, names."
        )

    # Runs/models folder
    models_dir = root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Run name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_name = args.name or f"{args.dataset}_{Path(args.weights).stem}_{stamp}"

    # Prefer YOLOv12; fall back to YOLOv11 automatically if not supported
    want_v12 = ("12" in args.weights) and not Path(args.weights).exists()
    model = None
    tried = []

    def _try_load(w):
        print(f"[info] Loading pretrained: {w}")
        return YOLO(w)  # auto-downloads known aliases

    try:
        model = _try_load(args.weights)
        tried.append(args.weights)
    except Exception as e:
        if want_v12:
            if args.strict_v12:
                print(f"[error] Could not load '{args.weights}' (YOLOv12). "
                      f"Your Ultralytics install likely doesn't support v12 yet.\n{e}", file=sys.stderr)
                raise
            print(f"[warn] '{args.weights}' not available in this Ultralytics version. Falling back to 'yolo11n.pt'.")
            try:
                model = _try_load("yolo11n.pt")
                tried.append("yolo11n.pt")
            except Exception as e2:
                print(f"[error] Fallback to 'yolo11n.pt' also failed.\n{e2}\n"
                      "Try upgrading Ultralytics:  pip install -U ultralytics", file=sys.stderr)
                raise
        else:
            print(f"[error] Could not load '{args.weights}'.\n{e}\n"
                  "Try a known alias like 'yolo11n.pt' or upgrade Ultralytics.", file=sys.stderr)
            raise

    # Optional CUDA speedups when shapes are fixed
    try:
        import torch
        if device not in ("cpu", "mps") and torch.backends.cudnn.is_available():
            torch.backends.cudnn.benchmark = True
            print("[info] Enabled cuDNN benchmark for potential speedup.")
    except Exception:
        pass

    # Train
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,          # <-- ensure GPU is used
        workers=args.workers,
        seed=args.seed,
        patience=args.patience,
        lr0=args.lr0,
        project=str(models_dir),  # keep all runs under ./models
        name=run_name,
        pretrained=True,
        save=True,
        verbose=True,
        amp=True,               # mixed precision on GPU
    )

    # Copy convenience weights
    run_dir = models_dir / run_name
    weights_dir = run_dir / "weights"
    best = weights_dir / "best.pt"
    last = weights_dir / "last.pt"
    if best.exists():
        shutil.copy2(best, models_dir / f"{run_name}_best.pt")
    if last.exists():
        shutil.copy2(last, models_dir / f"{run_name}_last.pt")

    print("\n=== Training complete ===")
    print(f"Run directory: {run_dir}")
    print(f"Model(s) used: {', '.join(tried)}")
    if best.exists():
        print(f"Best: {best}  (copied to {models_dir / (run_name + '_best.pt')})")
    if last.exists():
        print(f"Last: {last}  (copied to {models_dir / (run_name + '_last.pt')})")

if __name__ == "__main__":
    main()
