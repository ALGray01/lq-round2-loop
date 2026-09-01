"""
Builds documents/redaction_test/manafort_p3_degraded.png from the real,
unmodified Manafort sentencing-memo page 3 scan.

Two things are done to the real page, both disclosed here and in README.md:

1. A black redaction bar is drawn over one real line (list item II,
   "The Presentence Investigative Report ('PSR')"). This is a
   SYNTHETIC redaction added by this script for testing purposes -- the
   real filing was not redacted at this location. It exists so we can
   test how each OCR candidate handles a redaction box (does it hallucinate
   text under the bar, does it silently drop the line, does it choke on
   the layout).
2. Realistic scan degradation is applied on top: slight rotation (skew),
   gaussian noise, mild blur, JPEG recompression, and contrast/brightness
   reduction -- simulating what a litigator actually receives when a
   party produces a photocopied/faxed/rescanned version of a born-digital
   filing during discovery, rather than the clean PDF original.

Nothing else about the document's real text is altered.
"""
import cv2
import numpy as np
from PIL import Image
import io

SRC = "documents/raw/manafort_memo_p3.png"
OUT = "documents/redaction_test/manafort_p3_degraded.png"


def add_redaction_bar(img):
    # Coordinates picked by inspecting the 300dpi render: covers the
    # "II. The Presentence Investigative Report ('PSR')" heading line.
    h, w = img.shape[:2]
    x0, y0, x1, y1 = int(w * 0.185), int(h * 0.255), int(w * 0.86), int(h * 0.278)
    cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 0), thickness=-1)
    return img


def degrade(img):
    h, w = img.shape[:2]
    # slight rotation to simulate a crooked scan/photocopy
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, 1.4, 1.0)
    img = cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))

    # mild blur (out-of-focus copier/scanner)
    img = cv2.GaussianBlur(img, (3, 3), 0)

    # gaussian noise
    noise = np.random.normal(0, 9, img.shape).astype(np.float32)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # contrast/brightness reduction (faded toner / low-quality copy)
    img = cv2.convertScaleAbs(img, alpha=0.78, beta=18)

    # JPEG recompression artifacts at moderate quality
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=55)
    buf.seek(0)
    pil2 = Image.open(buf).convert("RGB")
    return cv2.cvtColor(np.array(pil2), cv2.COLOR_RGB2BGR)


if __name__ == "__main__":
    img = cv2.imread(SRC)
    img = add_redaction_bar(img)
    img = degrade(img)
    cv2.imwrite(OUT, img, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    print("wrote", OUT, img.shape)
