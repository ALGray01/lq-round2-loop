"""
Preprocessing pipeline for hard scanned legal documents.

Steps: grayscale -> deskew -> denoise -> adaptive contrast (CLAHE) ->
adaptive threshold (binarize) -> upscale. Each step is optional and
controlled by flags so we can ablate which steps actually help each
OCR engine (some engines want binarized input, some want grayscale).
"""
import argparse
import cv2
import numpy as np


def deskew(gray: np.ndarray) -> np.ndarray:
    # Estimate skew from the largest text mass using minAreaRect on
    # thresholded ink pixels, then rotate to correct.
    inv = cv2.bitwise_not(gray)
    thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    # Old manuscript pages have irregular deckle edges that can fool
    # minAreaRect into large false angles; ignore implausible corrections.
    if abs(angle) > 10:
        return gray
    (h, w) = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)


def denoise(gray: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)


def clahe_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(16, 16))
    return clahe.apply(gray)


def adaptive_binarize(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 15
    )


def run_pipeline(src_path: str, dst_prefix: str, do_deskew=True, do_denoise=True,
                  do_contrast=True, do_binarize=False, upscale=1.0):
    img = cv2.imread(src_path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(src_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if upscale != 1.0:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)

    if do_deskew:
        gray = deskew(gray)
    if do_denoise:
        gray = denoise(gray)
    if do_contrast:
        gray = clahe_contrast(gray)

    out_gray_path = f"{dst_prefix}_gray.png"
    cv2.imwrite(out_gray_path, gray)

    result = {"gray": out_gray_path}
    if do_binarize:
        binimg = adaptive_binarize(gray)
        out_bin_path = f"{dst_prefix}_bin.png"
        cv2.imwrite(out_bin_path, binimg)
        result["bin"] = out_bin_path
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst_prefix")
    ap.add_argument("--no-deskew", action="store_true")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--no-contrast", action="store_true")
    ap.add_argument("--binarize", action="store_true")
    ap.add_argument("--upscale", type=float, default=1.0)
    args = ap.parse_args()

    out = run_pipeline(
        args.src, args.dst_prefix,
        do_deskew=not args.no_deskew,
        do_denoise=not args.no_denoise,
        do_contrast=not args.no_contrast,
        do_binarize=args.binarize,
        upscale=args.upscale,
    )
    print(out)
