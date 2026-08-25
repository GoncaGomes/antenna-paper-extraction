from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from antenna_paper_extraction.runs import create_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antenna-extract")
    subparser = parser.add_subparsers(dest="command", required=True)

    init_run = subparser.add_parser("init-run")
    init_run.add_argument("input_pdf", type=Path, help="Original PDF")
    init_run.add_argument(
        "--runs-root", type=Path, help="Runs directory", default=Path("runs")
    )

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

    parser.error(f"unrecognized command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
