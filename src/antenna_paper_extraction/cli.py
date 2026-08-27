from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pypdfium2 as pdfium

from antenna_paper_extraction.pages import render_pdf_pages
from antenna_paper_extraction.runs import create_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antenna-extract")
    subparser = parser.add_subparsers(dest="command", required=True)

    init_run = subparser.add_parser("init-run")
    init_run.add_argument("input_pdf", type=Path, help="Original PDF")
    init_run.add_argument(
        "--runs-root", type=Path, help="Runs directory", default=Path("runs")
    )

    render_pages = subparser.add_parser("render-pages")
    render_pages.add_argument("run_dir", type=Path, help="Existing run directory")
    render_pages.add_argument("--dpi", type=int, default=200, help="DPI")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-run":
        try:
            run_dir = create_run(args.input_pdf, args.runs_root)
        except (OSError, ValueError) as e:
            print(f"Failed to create run. {e}", file=sys.stderr)
            return 1

        print(f"Created run: {run_dir.resolve()}")
        return 0

    if args.command == "render-pages":
        try:
            pages_manifest = render_pdf_pages(args.run_dir, dpi=args.dpi)
        except (OSError, ValueError, pdfium.PdfiumError) as error:
            print(f"Failed to render pages. {error}", file=sys.stderr)
            return 1

        pages_dir = (args.run_dir / "pages").resolve()

        print(f"Rendered {pages_manifest.page_count} page(s): {pages_dir}")
        return 0

    parser.error(f"unrecognized command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
