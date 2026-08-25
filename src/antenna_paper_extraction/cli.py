from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from antenna_paper_extraction.runs import create_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antenna-paper-extraction")
    subparser = parser.add_subparsers(dest="command", required=True)

    init_run = subparser.add_parser("init-run")
    init_run.add_argument("input_pdf", type=Path, help="Original PDF")
    init_run.add_argument(
        "--runs_root", type=Path, help="Runs directory", default=Path("runs")
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    print("Initialized CLI")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-run":
        create_run(args.input_pdf, args.runs_root)
        return 0

    parser.error(f"unrecognized command: {args.command}")
    return 2


if __name__ == "__main__":
    main()
