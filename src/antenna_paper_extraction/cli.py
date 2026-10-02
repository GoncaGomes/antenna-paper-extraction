from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path

import pypdfium2 as pdfium
from agents.exceptions import AgentsException
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI, OpenAIError

from antenna_paper_extraction.architecture import run_architecture_agent
from antenna_paper_extraction.document import convert_document_to_markdown
from antenna_paper_extraction.figures import extract_figures
from antenna_paper_extraction.mcp_agent import ProbeError
from antenna_paper_extraction.mcp_runtime import probe
from antenna_paper_extraction.model_client import OpenAICompatibleClient
from antenna_paper_extraction.pages import render_pdf_pages
from antenna_paper_extraction.runs import create_run


@dataclass(frozen=True, slots=True)
class DocumentExtractorSettings:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ArchitectureAgentSettings:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class MCPArchitectureSettings:
    principal: ArchitectureAgentSettings
    visual_model: str
    visual_timeout_seconds: float
    server_executable: Path
    server_cwd: Path


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


def load_architecture_agent_settings(
    environ: Mapping[str, str],
) -> ArchitectureAgentSettings:
    base_url = _require_environment_variable(environ, "SKYNET_BASE_URL")
    api_key = _require_environment_variable(environ, "SKYNET_API_KEY")
    model = _require_environment_variable(environ, "ARCHITECTURE_AGENT_MODEL")
    timeout_value = _require_environment_variable(
        environ,
        "ARCHITECTURE_AGENT_TIMEOUT_SECONDS",
    )

    try:
        timeout_seconds = float(timeout_value)
    except ValueError:
        raise ValueError(
            "ARCHITECTURE_AGENT_TIMEOUT_SECONDS must be a positive finite number."
        ) from None

    if not isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(
            "ARCHITECTURE_AGENT_TIMEOUT_SECONDS must be a positive finite number."
        )

    return ArchitectureAgentSettings(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


async def _run_architecture_command(
    run_dir: Path,
    settings: ArchitectureAgentSettings,
    *,
    max_assets: int,
) -> Path:
    async with AsyncOpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        max_retries=0,
    ) as client:
        return await run_architecture_agent(
            run_dir=run_dir,
            client=client,
            model_name=settings.model,
            max_assets=max_assets,
        )


def load_mcp_architecture_settings(
    environ: Mapping[str, str],
) -> MCPArchitectureSettings:
    principal = load_architecture_agent_settings(environ)
    visual_model = _require_environment_variable(environ, "VISUAL_INSPECTION_MODEL")
    timeout_value = _require_environment_variable(
        environ, "VISUAL_INSPECTION_TIMEOUT_SECONDS"
    )
    try:
        visual_timeout_seconds = float(timeout_value)
    except ValueError:
        raise ValueError(
            "VISUAL_INSPECTION_TIMEOUT_SECONDS must be a positive finite number."
        ) from None
    if not isfinite(visual_timeout_seconds) or visual_timeout_seconds <= 0:
        raise ValueError(
            "VISUAL_INSPECTION_TIMEOUT_SECONDS must be a positive finite number."
        )
    server_executable = Path(
        _require_environment_variable(environ, "MCP_PDF_SERVER_EXECUTABLE")
    ).resolve()
    server_cwd = Path(
        _require_environment_variable(environ, "MCP_PDF_SERVER_CWD")
    ).resolve()
    if not server_executable.is_file():
        raise ValueError("MCP_PDF_SERVER_EXECUTABLE must be an existing file.")
    if not server_cwd.is_dir():
        raise ValueError("MCP_PDF_SERVER_CWD must be an existing directory.")
    return MCPArchitectureSettings(
        principal=principal,
        visual_model=visual_model,
        visual_timeout_seconds=visual_timeout_seconds,
        server_executable=server_executable,
        server_cwd=server_cwd,
    )


async def _run_mcp_architecture_command(
    run_dir: Path,
    settings: MCPArchitectureSettings,
    *,
    max_turns: int,
) -> Path:
    report_path = await probe(
        run_dir,
        settings.server_executable,
        settings.server_cwd,
        agent_model=settings.principal.model,
        agent_task="architecture",
        max_turns=max_turns,
        persist_architecture=True,
        base_url=settings.principal.base_url,
        api_key=settings.principal.api_key,
        principal_timeout_seconds=settings.principal.timeout_seconds,
        visual_model=settings.visual_model,
        visual_timeout_seconds=settings.visual_timeout_seconds,
        session_timeout_seconds=settings.visual_timeout_seconds + 60,
    )
    if report_path is None:
        raise ProbeError("MCP architecture execution did not publish a report.")
    return report_path


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
    render_pages.add_argument("--dpi", type=int, default=300, help="DPI")

    convert_document = subparser.add_parser("convert-document")
    convert_document.add_argument(
        "run_dir", type=Path, help="Existing run directory with rendered pages"
    )

    extract_figures_parser = subparser.add_parser(
        "extract-figures",
        help="Extract figures from a converted run",
        description=(
            "Detect figure regions with Docling and render crops from "
            "the preserved PDF, using converted Markdown captions."
        ),
    )
    extract_figures_parser.add_argument(
        "run_dir",
        type=Path,
        help="Existing run directory with successful document conversion",
    )
    extract_figures_parser.add_argument(
        "--scale",
        type=float,
        default=4.0,
        help="PDFium rendering scale (default: 3.0, approximately 216 DPI)",
    )
    extract_figures_parser.add_argument(
        "--margin-pt",
        type=float,
        default=2.0,
        help="Crop margin in PDF points (default: 2.0)",
    )

    extract_architecture_parser = subparser.add_parser(
        "extract-architecture",
        help="Generate an evidence-grounded architecture report",
    )
    extract_architecture_parser.add_argument(
        "run_dir",
        type=Path,
        help="Existing run directory with successful figure extraction",
    )
    extract_architecture_parser.add_argument(
        "--max-assets",
        type=int,
        default=6,
        help="Maximum assets in the single visual request (default: 6)",
    )

    mcp_architecture_parser = subparser.add_parser(
        "extract-architecture-mcp",
        help="Generate an architecture report through MCP (experimental)",
        description=(
            "Experimental MCP architecture extraction from an initialized run "
            "with successful source preservation; no baseline preprocessing required."
        ),
    )
    mcp_architecture_parser.add_argument(
        "run_dir", type=Path, help="Existing initialized run directory"
    )
    mcp_architecture_parser.add_argument(
        "--max-turns",
        type=int,
        default=80,
        help="Positive agent turn budget (default: 80)",
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

    if args.command == "extract-figures":
        try:
            manifest_path = extract_figures(
                run_dir=args.run_dir,
                scale=args.scale,
                margin_pt=args.margin_pt,
            )
        except (OSError, ValueError, RuntimeError, pdfium.PdfiumError) as error:
            print(f"Failed to extract figures. {error}", file=sys.stderr)
            return 1

        print(f"Figure manifest: {manifest_path.resolve()}")
        return 0

    if args.command == "extract-architecture":
        if args.max_assets < 1:
            parser.error("--max-assets must be positive")

        try:
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
            settings = load_architecture_agent_settings(os.environ)

            report_path = asyncio.run(
                _run_architecture_command(
                    args.run_dir,
                    settings,
                    max_assets=args.max_assets,
                )
            )

        except (
            OSError,
            ValueError,
            RuntimeError,
            OpenAIError,
            AgentsException,
        ) as error:
            print(f"Failed to extract architecture. {error}", file=sys.stderr)

            for note in getattr(error, "__notes__", ()):
                print(note, file=sys.stderr)

            return 1

        print(f"Architecture report: {report_path.resolve()}")
        return 0

    if args.command == "extract-architecture-mcp":
        if args.max_turns < 1:
            parser.error("--max-turns must be positive")

        previous_logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            # Settings errors are controlled locally; operational errors are
            # displayed only when the shared runtime has made them safe.
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
            try:
                settings = load_mcp_architecture_settings(os.environ)
            except ValueError as error:
                print(f"Failed to extract MCP architecture. {error}", file=sys.stderr)
                return 1
            report_path = asyncio.run(
                _run_mcp_architecture_command(
                    args.run_dir, settings, max_turns=args.max_turns
                )
            )
        except ProbeError as error:
            print(f"Failed to extract MCP architecture. {error}", file=sys.stderr)
            return 1
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("MCP architecture extraction cancelled.", file=sys.stderr)
            return 130
        except Exception:  # noqa: BLE001 -- exclude sensitive third-party errors
            print(
                "MCP architecture extraction failed; check configuration and run paths.",
                file=sys.stderr,
            )
            return 1
        finally:
            logging.disable(previous_logging_disable)
        print(f"MCP architecture report: {report_path.resolve()}")
        return 0

    parser.error(f"unrecognized command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
