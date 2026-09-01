"""
Preprocessing pipeline recommended for hard legal scans.

Steps (each individually toggleable):
  1. Grayscale conversion
  2. Deskew (via minAreaRect on thresholded ink pixels)
  3. Denoise (fastNlMeansDenoising)
  4. CLAHE local contrast enhancement
  5. Adaptive thresholding (binarization) -- OFF by default for the
     handwriting case (binarization destroys faint pen strokes / bleed-through
     context that helps both classical and neural OCR); ON by default for
     the machine-print + redaction case (binarization sharpens dense small
     print and normalizes faded photocopy toner).
  6. Upscale small images (helps recognition of small print / footnotes)

Usage:
    python scripts/preprocess.py <input.png> <output.png> [--binarize] [--no-deskew]
"""
import sys
import argparse
import cv2
import numpy as np


def deskew(gray):
    # Ink = dark pixels. Use Otsu threshold to find the text mask, then
    # fit a minimum-area rectangle to estimate skew angle.
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if len(coords) < 100:
        return gray, 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    # Guard against wild misfires on sparse/noisy pages
    if abs(angle) > 15:
        return gray, 0.0
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return rotated, angle


def preprocess(img_bgr, binarize=True, do_deskew=True, denoise=True,
                clahe=True, upscale_if_small=True):
    log = []
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    log.append(f"grayscale: {gray.shape}")

    h, w = gray.shape[:2]
    if upscale_if_small and max(h, w) < 2000:
        scale = 2000 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        log.append(f"upscaled by {scale:.2f}x -> {gray.shape}")

    if do_deskew:
        gray, angle = deskew(gray)
        log.append(f"deskew angle: {angle:.2f} deg")

    if denoise:
        gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
        log.append("denoised (fastNlMeansDenoising)")

    if clahe:
        clahe_op = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe_op.apply(gray)
        log.append("CLAHE contrast applied")

    if binarize:
        gray = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
            blockSize=31, C=11,
        )
        log.append("adaptive threshold (binarized)")

    return gray, log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--binarize", action="store_true")
    ap.add_argument("--no-deskew", action="store_true")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--no-clahe", action="store_true")
    args = ap.parse_args()

    img = cv2.imread(args.input)
    if img is None:
        sys.exit(f"could not read {args.input}")

    out, log = preprocess(
        img,
        binarize=args.binarize,
        do_deskew=not args.no_deskew,
        denoise=not args.no_denoise,
        clahe=not args.no_clahe,
    )
    cv2.imwrite(args.output, out)
    for line in log:
        print(line)
    print("wrote", args.output)
