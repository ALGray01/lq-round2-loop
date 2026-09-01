import sys
import json
import time
from rapidocr_onnxruntime import RapidOCR

def main(img_path, out_path):
    engine = RapidOCR()
    t0 = time.time()
    result, elapse = engine(img_path)
    dt = time.time() - t0
    lines = []
    if result:
        for box, text, conf in result:
            ys = [pt[1] for pt in box]
            xs = [pt[0] for pt in box]
            lines.append({"text": text, "conf": float(conf), "y": float(min(ys)), "x": float(min(xs))})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"engine": "rapidocr", "image": img_path, "seconds": dt, "lines": lines}, f, ensure_ascii=False, indent=2)
    print(f"rapidocr: {len(lines)} lines, {dt:.1f}s -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
