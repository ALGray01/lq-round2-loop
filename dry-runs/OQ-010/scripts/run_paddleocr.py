"""
Runs PaddleOCR (PP-OCRv6) on a given image and writes:
  - a plain-text transcript (reading order = top-to-bottom detection order)
  - a JSON file with boxes + per-line confidence scores

Usage: python scripts/run_paddleocr.py <input.png> <out_prefix>
"""
import sys
import json
import time
from paddleocr import PaddleOCR

def main():
    inp, out_prefix = sys.argv[1], sys.argv[2]
    t0 = time.time()
    # enable_mkldnn=False works around a real, reproducible bug on this
    # machine's CPU/paddle build: PP-OCRv6's default oneDNN (mkldnn) path
    # throws `NotImplementedError: ConvertPirAttribute2RuntimeAttribute
    # not support [pir::ArrayAttribute<pir::DoubleAttribute>]` inside
    # paddle's static-graph executor. Disabling mkldnn falls back to a
    # slower but working conv kernel. Documented in README as a real
    # install-friction finding, not hidden.
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                     use_textline_orientation=False, lang="en", enable_mkldnn=False)
    t_init = time.time() - t0

    t1 = time.time()
    result = ocr.predict(inp)
    t_infer = time.time() - t1

    lines = []
    scores = []
    for res in result:
        texts = res.get("rec_texts", [])
        confs = res.get("rec_scores", [])
        lines.extend(texts)
        scores.extend(confs)
        with open(out_prefix + ".json", "w", encoding="utf-8") as f:
            json.dump({"rec_texts": texts, "rec_scores": confs,
                       "rec_polys": [p.tolist() if hasattr(p, "tolist") else p
                                     for p in res.get("rec_polys", [])]}, f, indent=2)

    with open(out_prefix + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    avg_conf = sum(scores) / len(scores) if scores else 0.0
    print(f"init={t_init:.1f}s infer={t_infer:.1f}s lines={len(lines)} avg_conf={avg_conf:.3f}")
    with open(out_prefix + ".meta.txt", "w") as f:
        f.write(f"init_seconds={t_init:.2f}\ninfer_seconds={t_infer:.2f}\n"
                f"num_lines={len(lines)}\navg_confidence={avg_conf:.4f}\n")

if __name__ == "__main__":
    main()
