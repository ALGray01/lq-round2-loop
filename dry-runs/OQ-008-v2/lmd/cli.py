"""Command-line entry point: `python -m lmd build|lint|model <file.lmd>`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import model as M
from . import parser as P
from . import render_html as R


def _build_document_or_die(path: Path) -> M.Document:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: could not read {path}: {e}", file=sys.stderr)
        sys.exit(2)
    try:
        return M.build_document(source)
    except P.LmdSyntaxError as e:
        print(f"syntax error: {e}", file=sys.stderr)
        sys.exit(2)


def cmd_build(args) -> int:
    doc = _build_document_or_die(Path(args.input))
    errors = doc.errors()
    if errors and not args.force:
        print(f"refusing to build: {len(errors)} lint error(s) (use --force to build anyway)",
              file=sys.stderr)
        for issue in errors:
            print(f"  {issue}", file=sys.stderr)
        return 1
    html_out = R.render_html(doc)
    out_path = Path(args.output) if args.output else Path(args.input).with_suffix(".html")
    out_path.write_text(html_out, encoding="utf-8")
    print(f"wrote {out_path}")
    if errors:
        print(f"WARNING: built despite {len(errors)} lint error(s) due to --force", file=sys.stderr)
    for issue in doc.warnings():
        print(f"  {issue}", file=sys.stderr)
    return 0


def cmd_lint(args) -> int:
    doc = _build_document_or_die(Path(args.input))
    if not doc.issues:
        print("lint clean: 0 issues")
        return 0
    for issue in doc.issues:
        print(str(issue))
    n_err = len(doc.errors())
    n_warn = len(doc.warnings())
    print(f"{n_err} error(s), {n_warn} warning(s)")
    return 1 if n_err else 0


def _html_safe_json(data) -> str:
    """json.dumps, with </script>-breakout characters escaped.

    SPEC.md pitches the document model (this command's output) as data a
    downstream consumer can embed anywhere, and front-matter values (e.g.
    `title`) flow into it unescaped-as-JSON-but-not-as-HTML. Found by
    audit: a title containing "</script><script>alert(1)</script>" is
    perfectly valid JSON, and would execute if a downstream consumer did
    the extremely common `var m = {json};` embed inside a <script> tag
    without their own escaping -- the same mitigation major JSON-in-HTML
    embedding helpers (e.g. Django's json_script) apply by default.
    """
    text = json.dumps(data, indent=2)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def cmd_model(args) -> int:
    doc = _build_document_or_die(Path(args.input))
    data = doc.to_dict()
    text = _html_safe_json(data)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="lmd", description="Legal Markdown reference toolchain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="compile an .lmd file to styled HTML")
    p_build.add_argument("input")
    p_build.add_argument("-o", "--output")
    p_build.add_argument("--force", action="store_true",
                          help="write output even if lint errors are present")
    p_build.set_defaults(func=cmd_build)

    p_lint = sub.add_parser("lint", help="check an .lmd file for consistency issues")
    p_lint.add_argument("input")
    p_lint.set_defaults(func=cmd_lint)

    p_model = sub.add_parser("model", help="dump the resolved document model as JSON")
    p_model.add_argument("input")
    p_model.add_argument("-o", "--output")
    p_model.set_defaults(func=cmd_model)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
