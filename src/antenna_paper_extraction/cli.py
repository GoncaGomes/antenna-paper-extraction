from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from antenna_paper_extraction.document import convert_document_to_markdown
from antenna_paper_extraction.model_client import OpenAICompatibleClient
from antenna_paper_extraction.pages import render_pdf_pages
from antenna_paper_extraction.runs import create_run


@dataclass(frozen=True, slots=True)
class DocumentExtractorSettings:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: float


def _require_environment_variable(
    environ: Mapping[str, str],
    name: str,
) -> str:
    value = environ.get(name)

    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")

    return value.strip()


def load_document_extractor_settings(
    environ: Mapping[str, str],
) -> DocumentExtractorSettings:
    base_url = _require_environment_variable(
        environ,
        "SKYNET_BASE_URL",
    )
    api_key = _require_environment_variable(
        environ,
        "SKYNET_API_KEY",
    )
    model = _require_environment_variable(
        environ,
        "DOCUMENT_EXTRACTOR_MODEL",
    )
    timeout_value = _require_environment_variable(
        environ,
        "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS",
    )

    try:
        timeout_seconds = float(timeout_value)
    except ValueError:
        raise ValueError(
            "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS must be a positive number"
        ) from None

    if timeout_seconds <= 0:
        raise ValueError("DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS must be a positive number")

    return DocumentExtractorSettings(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


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
    render_pages.add_argument("--dpi", type=int, default=170, help="DPI")

    convert_document = subparser.add_parser("convert-document")
    convert_document.add_argument(
        "run_dir", type=Path, help="Existing run directory with rendered pages"
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

    if args.command == "render-pages":
        try:
            pages_manifest = render_pdf_pages(args.run_dir, dpi=args.dpi)
        except (OSError, ValueError, pdfium.PdfiumError) as error:
            print(f"Failed to render pages. {error}", file=sys.stderr)
            return 1

        pages_dir = (args.run_dir / "pages").resolve()

        print(f"Rendered {pages_manifest.page_count} page(s): {pages_dir}")
        return 0

    if args.command == "convert-document":
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

        try:
            settings = load_document_extractor_settings(os.environ)

            sdk_client = OpenAI(
                base_url=settings.base_url,
                api_key=settings.api_key,
                timeout=settings.timeout_seconds,
                max_retries=0,
            )

            client = OpenAICompatibleClient(sdk_client)

            document_path = convert_document_to_markdown(
                run_dir=args.run_dir,
                client=client,
                model=settings.model,
            )
        except (OSError, ValueError, OpenAIError) as error:
            print(f"Failed to convert document. {error}", file=sys.stderr)
            return 1

        print(f"Converted document: {document_path.resolve()}")
        return 0

    parser.error(f"unrecognized command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
