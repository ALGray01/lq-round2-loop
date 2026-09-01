import sys
import json
import time
from paddleocr import PaddleOCR

def main(img_path, out_path):
    ocr = PaddleOCR(use_textline_orientation=True, lang="en")
    t0 = time.time()
    result = ocr.predict(img_path)
    dt = time.time() - t0
    lines = []
    for page in result:
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        boxes = page.get("rec_boxes", [])
        for i, text in enumerate(texts):
            conf = float(scores[i]) if i < len(scores) else None
            if i < len(boxes):
                box = boxes[i]
                x0, y0 = float(box[0]), float(box[1])
            else:
                x0, y0 = None, None
            lines.append({"text": text, "conf": conf, "y": y0, "x": x0})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"engine": "paddleocr", "image": img_path, "seconds": dt, "lines": lines}, f, ensure_ascii=False, indent=2)
    print(f"paddleocr: {len(lines)} lines, {dt:.1f}s -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
