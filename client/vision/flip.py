import cv2
import os

def review_and_flip_images(folder_path):
    # Get all image files
    valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    image_files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith(valid_exts)]
    if not image_files:
        print("No images found in folder.")
        return

    print(f"Found {len(image_files)} images in {folder_path}")
    idx = 0

    while 0 <= idx < len(image_files):
        img_path = os.path.join(folder_path, image_files[idx])
        img = cv2.imread(img_path)
        if img is None:
            print(f"Cannot read: {img_path}")
            idx += 1
            continue

        cv2.imshow("Flip Tool", img)
        print(f"[{idx+1}/{len(image_files)}] {image_files[idx]}")
        key = cv2.waitKey(0)

        if key == 27:  # ESC to exit
            break
        elif key == 32:  # SPACE to flip vertically
            flipped = cv2.flip(img, 0)
            cv2.imwrite(img_path, flipped)
            print(f"Flipped and saved: {image_files[idx]}")
            idx += 1
        elif key == ord('n'):  # 'n' to skip to next
            idx += 1
        elif key == ord('b'):  # 'b' to go back
            idx = max(0, idx - 1)

    cv2.destroyAllWindows()

if __name__ == "__main__":
    folder = "D:\\uni\\ECE4191\\pics"
    review_and_flip_images(folder)
