# test.py — Interactive 5x5 detection grid (TP=green, FP=red, FN=yellow)
# SPACE=new sample | S=save (full-res) | Q/ESC=quit
#
# Smaller window + auto-fit:
#   - Default tile size is small (cell=224)
#   - Use --fit_screen to auto scale to your screen without changing the saved resolution

import argparse, random, cv2, numpy as np
from pathlib import Path
from datetime import datetime
import yaml

# ---------------- CLI ----------------
def parse_args():
    p = argparse.ArgumentParser("Interactive grid of detections (TP=green, FP=red, FN=yellow)")
    p.add_argument("--dataset", choices=["aug","no_aug"], default="aug")
    p.add_argument("--weights", required=True, help="Trained weights .pt")
    p.add_argument("--split", choices=["test","valid","val"], default="test",
                   help="Preferred split; falls back automatically if empty")
    p.add_argument("--rows", type=int, default=5)
    p.add_argument("--cols", type=int, default=5)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--iou",  type=float, default=0.50)
    p.add_argument("--device", default="auto", help="'auto', 'cpu', '0', '0,1', ...")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cell", type=int, default=224, help="Tile size (px) for each cell in the grid")
    p.add_argument("--fit_screen", action="store_true",
                   help="Auto-scale the displayed window to fit your screen (saved image stays full-res)")
    p.add_argument("--margin", type=int, default=80, help="Screen margin used with --fit_screen")
    return p.parse_args()

# ---------------- Utils ----------------
def auto_select_device(pref: str) -> str:
    if pref and pref.lower() != "auto":
        return pref
    try:
        import torch
        if torch.cuda.is_available(): return "0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available(): return "mps"
    except Exception:
        pass
    return "cpu"

def get_screen_size():
    # Try tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return int(w), int(h)
    except Exception:
        pass
    # Try Windows ctypes
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        pass
    # Fallback
    return 1366, 768

def fit_to_screen(img, margin=80):
    sw, sh = get_screen_size()
    max_w, max_h = max(200, sw - margin), max(200, sh - margin)
    h, w = img.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        disp = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return disp, scale
    return img, 1.0

def load_yaml(p: Path) -> dict:
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_class_names(data: dict) -> list[str]:
    names = data.get("names", None)
    if isinstance(names, list):
        return [str(x) for x in names]
    if isinstance(names, dict):
        items = sorted(names.items(), key=lambda kv: int(kv[0]))
        return [str(v) for _, v in items]
    nc = int(data.get("nc", 0) or 0)
    return [str(i) for i in range(nc)]

def _to_list(x):
    return x if isinstance(x, (list, tuple)) else [x]

def resolve_spec_to_paths(spec, base_dir: Path):
    """Resolve image spec(s) relative to the YAML dir, expand to files."""
    specs = _to_list(spec)
    paths = []
    for s in specs:
        p = Path(s)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        if p.is_dir():
            for ext in ("*.jpg","*.jpeg","*.png","*.bmp","*.tif","*.tiff"):
                paths.extend(p.rglob(ext))
        elif any(ch in str(p) for ch in "*?[]"):
            paths.extend(Path().glob(str(p)))
        elif p.suffix.lower()==".txt" and p.exists():
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    q = line.strip()
                    if not q: continue
                    q = Path(q)
                    if not q.is_absolute():
                        q = (p.parent / q).resolve()
                    paths.append(q)
        elif p.exists():
            paths.append(p)
    return [pp for pp in sorted(set(paths)) if pp.exists()]

def iou_xyxy(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter <= 0: return 0.0
    area_a = (ax2-ax1)*(ay2-ay1)
    area_b = (bx2-bx1)*(by2-by1)
    return inter / max(1e-9, area_a + area_b - inter)

def draw_box(img, xyxy, color, label=None, thick=2):
    x1,y1,x2,y2 = map(int, xyxy)
    cv2.rectangle(img,(x1,y1),(x2,y2),color,thick)
    if label:
        tsize = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        cv2.rectangle(img,(x1,y1-tsize[1]-6),(x1+tsize[0]+6,y1),color,-1)
        cv2.putText(img,label,(x1+3,y1-4),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,0,0),1,cv2.LINE_AA)

def pad_to_border(img, color=(0,255,0), border=6):
    return cv2.copyMakeBorder(img,border,border,border,border,cv2.BORDER_CONSTANT,value=color)

def letterbox_square(img, size=224, bg=(30,30,30)):
    """Fit image into a square canvas, keep aspect ratio, pad with bg."""
    h, w = img.shape[:2]
    scale = min(size / max(1, w), size / max(1, h))
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((size, size, 3), bg, dtype=np.uint8)
    x = (size - nw) // 2
    y = (size - nh) // 2
    canvas[y:y+nh, x:x+nw] = resized
    return canvas

def find_label_path(img_path: Path):
    """Try multiple patterns to locate YOLO label .txt for img_path."""
    s = str(img_path)
    cands = [
        Path(s.replace("\\images\\","\\labels\\").replace("/images/","/labels/")).with_suffix(".txt"),
    ]
    split_names = {"train","val","valid","test"}
    parent = img_path.parent
    if parent.name in split_names:
        cands.append(parent/"labels"/(img_path.stem + ".txt"))
    if parent.name == "images" and parent.parent.name in split_names:
        cands.append(parent.parent/"labels"/(img_path.stem + ".txt"))
    parts = list(img_path.parts)
    if "images" in parts:
        idx = parts.index("images"); parts[idx] = "labels"
        cands.append(Path(*parts).with_suffix(".txt"))
    idx = s.rfind("/images/"); 
    if idx==-1: idx = s.rfind("\\images\\")
    if idx!=-1:
        cands.append(Path(s[:idx]+s[idx:].replace("images","labels",1)).with_suffix(".txt"))
    for p in cands:
        if p.exists(): return p
    return None

def load_yolo_txt(txt_path: Path, w: int, h: int):
    boxes=[]
    if not txt_path or not txt_path.exists(): return boxes
    with open(txt_path,"r",encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5: continue
            c = int(float(parts[0]))
            cx,cy,bw,bh = map(float, parts[1:5])
            x1 = (cx - bw/2.0) * w
            y1 = (cy - bh/2.0) * h
            x2 = x1 + bw*w
            y2 = y1 + bh*h
            boxes.append((c, np.array([x1,y1,x2,y2], dtype=np.float32)))
    return boxes

def build_pairs_and_names(data_yaml_path: Path, preferred_split: str):
    """Return (pairs, split_used, class_names). Pairs are (img_path, label_path)."""
    data = load_yaml(data_yaml_path)
    base_dir = data_yaml_path.parent
    class_names = get_class_names(data)

    for split in [preferred_split, "test", "valid", "val"]:
        spec = data.get(split, None)
        if spec is None:
            continue
        img_paths = resolve_spec_to_paths(spec, base_dir)
        if not img_paths:
            continue
        pairs = []
        for ip in img_paths:
            lp = find_label_path(ip)
            if lp and lp.exists():
                pairs.append((ip, lp))
        if pairs:
            return pairs, split, class_names

    raise RuntimeError(
        "Could not find images+labels for any split among: "
        f"{[preferred_split, 'test', 'valid', 'val']}. "
        "Check your data.yaml paths and that label .txt files exist."
    )

# ---------------- Grid ----------------
def build_grid(model, batch, conf, iou_thr, device, rows, cols, cell, class_names):
    GREEN=(0,255,0); RED=(0,0,255); YELLOW=(0,255,255)
    imgs = [p for (p,_) in batch]
    results = model.predict(imgs, conf=conf, device=device, verbose=False)

    grid_tiles=[]; per_stats=[]
    for (img_path, lbl_path), res in zip(batch, results):
        img = cv2.imread(str(img_path))
        if img is None:
            tile = np.full((cell,cell,3), 40, np.uint8)
            grid_tiles.append(tile); per_stats.append((0,0,0))
            continue

        h,w = img.shape[:2]
        gt = load_yolo_txt(lbl_path, w, h)

        preds=[]
        if res and hasattr(res,"boxes") and res.boxes is not None:
            b = res.boxes
            xyxy = b.xyxy.cpu().numpy() if hasattr(b.xyxy,"cpu") else b.xyxy.numpy()
            cls  = b.cls.cpu().numpy().astype(int)
            confs= b.conf.cpu().numpy()
            preds = [(int(cls[i]), float(confs[i]), xyxy[i]) for i in range(len(xyxy))]

        # Greedy match
        used=[False]*len(gt); tp=[]; fp=[]
        for c,cf,box in sorted(preds, key=lambda t:t[1], reverse=True):
            best_iou=0.0; best=-1
            for j,(gc,gbox) in enumerate(gt):
                if used[j] or gc!=c: continue
                i = iou_xyxy(box, gbox)
                if i>best_iou: best_iou, best = i, j
            if best>=0 and best_iou>=iou_thr:
                used[best]=True; tp.append((c,cf,box,best_iou))
            else:
                fp.append((c,cf,box))
        fn=[(gc,gbox) for (u,(gc,gbox)) in zip(used,gt) if not u]

        def cname(ci:int) -> str:
            return class_names[ci] if 0 <= ci < len(class_names) else str(ci)

        show = img.copy()
        thick = max(2, int(0.002*max(h,w)))
        for c,cf,box,iou in tp: draw_box(show, box, GREEN, f"{cname(c)} {cf:.2f}", thick)
        for c,cf,box in fp:     draw_box(show, box, RED,   f"{cname(c)} {cf:.2f}", thick)
        for gc,gbox in fn:      draw_box(show, gbox, YELLOW, f"miss: {cname(gc)}", thick+1)

        border = GREEN if (len(fp)==0 and len(fn)==0) else RED
        show = pad_to_border(show, border, 6)
        show = letterbox_square(show, size=cell, bg=(32,32,32))

        txt=f"TP:{len(tp)} FP:{len(fp)} FN:{len(fn)}"
        cv2.putText(show, txt, (10,24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20,20,20), 3, cv2.LINE_AA)
        cv2.putText(show, txt, (10,24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1, cv2.LINE_AA)

        grid_tiles.append(show)
        per_stats.append((len(tp),len(fp),len(fn)))

    grid_img = np.full((rows*cell, cols*cell, 3), 20, dtype=np.uint8)
    for i, tile in enumerate(grid_tiles):
        rr = i // cols; cc = i % cols
        if rr >= rows: break
        y1, y2 = rr*cell, (rr+1)*cell
        x1, x2 = cc*cell, (cc+1)*cell
        grid_img[y1:y2, x1:x2] = tile

    TTP=sum(t for t,_,_ in per_stats)
    TFP=sum(f for _,f,_ in per_stats)
    TFN=sum(n for _,_,n in per_stats)
    prec = TTP / max(1, TTP+TFP)
    rec  = TTP / max(1, TTP+TFN)
    return grid_img, (TTP, TFP, TFN, prec, rec)

# ---------------- Main ----------------
def main():
    args = parse_args()
    random.seed(args.seed); np.random.seed(args.seed)

    device = auto_select_device(args.device)
    from ultralytics import YOLO
    model = YOLO(args.weights)

    root = Path(__file__).resolve().parent
    data_yaml = root / "data" / args.dataset / "data.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(f"Missing {data_yaml}")
    pairs, used_split, class_names = build_pairs_and_names(data_yaml, args.split)
    if not pairs:
        raise RuntimeError("No images with labels found after resolving data.yaml.")

    print(f"[info] Using split: {used_split}   total labeled images: {len(pairs)}")
    print("[info] Controls: SPACE=new sample | S=save | Q/ESC=quit")

    N = args.rows * args.cols
    idx = 0
    random.shuffle(pairs)

    out_dir = Path("eval"); out_dir.mkdir(parents=True, exist_ok=True)

    win = "Detections Grid (SPACE=new | S=save | Q/ESC=quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    while True:
        if idx + N > len(pairs):
            random.shuffle(pairs)
            idx = 0
        batch = pairs[idx:idx+N]
        idx += N

        grid_img, stats = build_grid(model, batch, args.conf, args.iou, device,
                                     args.rows, args.cols, args.cell, class_names)

        TTP, TFP, TFN, prec, rec = stats
        header = f"{args.dataset} [{used_split}]  TP={TTP} FP={TFP} FN={TFN}  P={prec:.3f} R={rec:.3f}"
        cv2.putText(grid_img, header, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,0), 3, cv2.LINE_AA)
        cv2.putText(grid_img, header, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 1, cv2.LINE_AA)

        disp = grid_img
        if args.fit_screen:
            disp, scale = fit_to_screen(grid_img, margin=args.margin)

        cv2.imshow(win, disp)
        k = cv2.waitKey(0) & 0xFF
        if k in (27, ord('q'), ord('Q')):
            break
        elif k in (ord('s'), ord('S')):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            stem = Path(args.weights).stem
            out_path = out_dir / f"grid_{args.dataset}_{used_split}_{stem}_{stamp}.png"
            cv2.imwrite(str(out_path), grid_img)  # save full-res
            print(f"[ok] Saved: {out_path}")
        else:
            # SPACE or any other key -> refresh sample
            continue

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
