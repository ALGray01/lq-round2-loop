"""
Runs Docling's DocumentConverter (default layout model + default OCR
engine, RapidOCR) on a single image and writes markdown + timing.

Usage: python scripts/run_docling.py <input.png> <out_prefix>
"""
import os
# Must be set before docling/huggingface_hub is imported. Works around a
# real, reproducible Windows failure: huggingface_hub tries to symlink
# cached model files into its snapshot dir, which throws
# `OSError: [WinError 1314] A required privilege is not held by the
# client` on any account without the "Create symbolic links" privilege
# (Developer Mode off, the default). Disabling symlinks falls back to
# plain file copies.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

import sys
import time
from docling.document_converter import DocumentConverter

def main():
    inp, out_prefix = sys.argv[1], sys.argv[2]
    t0 = time.time()
    converter = DocumentConverter()
    t_init = time.time() - t0

    t1 = time.time()
    result = converter.convert(inp)
    t_infer = time.time() - t1

    md = result.document.export_to_markdown()
    with open(out_prefix + ".md", "w", encoding="utf-8") as f:
        f.write(md)

    print(f"init={t_init:.1f}s infer={t_infer:.1f}s chars={len(md)}")
    with open(out_prefix + ".meta.txt", "w") as f:
        f.write(f"init_seconds={t_init:.2f}\ninfer_seconds={t_infer:.2f}\nchars={len(md)}\n")

if __name__ == "__main__":
    main()
