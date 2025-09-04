#!/usr/bin/env python3
"""
Fix upside-down YOLO dataset by rotating 180° and updating labels.

Source:  data/no_aug/{train,valid,test}/{images,labels}
Output:  data/no_aug_flip/{train,valid,test}/{images,labels}

YOLO bbox lines:  <cls> <x> <y> <w> <h>     (normalized)
YOLO seg lines:   <cls> x1 y1 x2 y2 ...     (normalized)
Rotation 180°:    x -> 1-x, y -> 1-y
"""

from pathlib import Path
import cv2

SRC = Path("data/no_aug")
DST = Path("data/no_aug_flip")
SPLITS = ["train", "valid", "test"]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def transform_yolo_line(line: str) -> str:
    """Apply 180° rotation to a YOLO label line (bbox or segmentation)."""
    parts = line.strip().split()
    if not parts:
        return "\n"
    cls = parts[0]
    nums = [float(x) for x in parts[1:]]
    if len(nums) == 4:
        # bbox
        x, y, w, h = nums
        x = 1 - x
        y = 1 - y
        return f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n"
    else:
        # segmentation (pairs)
        for i in range(0, len(nums), 2):
            nums[i]   = 1 - nums[i]     # x
            nums[i+1] = 1 - nums[i+1]   # y
        return " ".join([cls] + [f"{v:.6f}" for v in nums]) + "\n"

def process_split(split: str) -> None:
    src_img_dir = SRC / split / "images"
    src_lbl_dir = SRC / split / "labels"
    dst_img_dir = DST / split / "images"
    dst_lbl_dir = DST / split / "labels"

    if not src_img_dir.exists():
        return

    ensure_dir(dst_img_dir)
    ensure_dir(dst_lbl_dir)

    n_img = n_lbl = 0
    for img_path in sorted(src_img_dir.rglob("*")):
        if img_path.suffix.lower() not in IMG_EXTS:
            continue
        img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"[WARN] Cannot read {img_path}")
            continue

        # 180° rotate = flip both axes
        img_rot = cv2.flip(img, -1)
        cv2.imwrite(str(dst_img_dir / img_path.name), img_rot)
        n_img += 1

        # labels
        lbl_path = src_lbl_dir / (img_path.stem + ".txt")
        out_lbl = dst_lbl_dir / (img_path.stem + ".txt")
        if lbl_path.exists():
            lines = lbl_path.read_text().splitlines()
            with out_lbl.open("w") as f:
                for line in lines:
                    if line.strip():
                        f.write(transform_yolo_line(line))
                    else:
                        f.write("\n")
            n_lbl += 1
        else:
            # optional: create empty label file (helps some training scripts)
            out_lbl.touch()

    print(f"[{split}] wrote {n_img} images, {n_lbl} label files -> {dst_img_dir}")

def write_data_yaml():
    src_yaml = SRC / "data.yaml"
    dst_yaml = DST / "data.yaml"
    if src_yaml.exists():
        # Simple text replace keeps class names etc.
        txt = src_yaml.read_text()
        dst_yaml.write_text(txt.replace("no_aug", "no_aug_flip"))
    else:
        # Minimal YAML if the original doesn't exist
        lines = [
            f"train: { (DST/'train'/'images').as_posix() }",
            f"val: { (DST/'valid'/'images').as_posix() }",
        ]
        test_dir = DST / "test" / "images"
        if test_dir.exists():
            lines.append(f"test: { test_dir.as_posix() }")
        dst_yaml.write_text("\n".join(lines) + "\n")
    print(f"[info] Wrote {dst_yaml}")

if __name__ == "__main__":
    ensure_dir(DST)
    for split in SPLITS:
        process_split(split)
    write_data_yaml()
    print("[done] New flipped dataset at:", DST.as_posix())
