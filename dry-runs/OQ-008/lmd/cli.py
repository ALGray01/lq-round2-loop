import argparse
import sys
from pathlib import Path

from .errors import BuildError
from .render import build_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lmd", description="Legal-markdown reference compiler")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Compile a .md legal-markdown source file to HTML")
    build.add_argument("source", help="Path to the .md source file")
    build.add_argument("-o", "--output", required=True, help="Path to write the rendered HTML")

    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            text = Path(args.source).read_text(encoding="utf-8")
            html_out = build_html(text)
        except BuildError as e:
            print(f"lmd: build failed: {e}", file=sys.stderr)
            return 1
        except FileNotFoundError:
            print(f"lmd: no such file: {args.source}", file=sys.stderr)
            return 1

        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_out, encoding="utf-8")
        print(f"lmd: wrote {out_path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
