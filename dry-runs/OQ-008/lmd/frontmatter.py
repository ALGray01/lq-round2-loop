import yaml

DEFAULT_SCHEME = ["decimal", "decimal", "alpha-lower", "roman-lower"]

DEFAULTS = {
    "title": "Untitled Agreement",
    "numbering_scheme": DEFAULT_SCHEME,
    "page": {"size": "Letter", "margin": "1in"},
}


def split_front_matter(text: str) -> tuple[dict, str, int]:
    """Split leading ``---``-delimited YAML front matter from the body.

    Returns (metadata, body, body_start_line) where body_start_line is the
    1-indexed line in the original file the body starts on, so downstream
    error messages can report accurate line numbers.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return dict(DEFAULTS), text, 1

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw_meta = "\n".join(lines[1:i])
            meta = yaml.safe_load(raw_meta) or {}
            merged = dict(DEFAULTS)
            merged.update(meta)
            body = "\n".join(lines[i + 1 :])
            return merged, body, i + 2

    raise ValueError("Front matter opened with '---' but never closed")
