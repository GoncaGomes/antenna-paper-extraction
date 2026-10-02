"""Explicit connection or evidence-agent probe for one preserved run."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from antenna_paper_extraction.mcp_agent import ProbeError
from antenna_paper_extraction.mcp_runtime import probe


def nonblank_model(value: str) -> str:
    if not value.strip():
        raise ProbeError("agent_model must be a nonblank model identifier.")
    return value.strip()


def positive_turns(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "max-turns must be a positive integer."
        ) from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError("max-turns must be a positive integer.")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--mcp-executable", type=Path, required=True)
    parser.add_argument("--mcp-cwd", type=Path, required=True)
    parser.add_argument("--agent-model", type=nonblank_model)
    parser.add_argument(
        "--agent-task", choices=("geometry", "architecture"), default="geometry"
    )
    parser.add_argument("--max-turns", type=positive_turns, default=8)
    parser.add_argument("--persist-architecture", action="store_true")
    args = parser.parse_args(argv)
    # SDK logs can include tool/error bodies. This standalone probe emits only
    # controlled diagnostics and restores logging for callers of main().
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        if args.agent_model is not None:
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        asyncio.run(
            probe(
                args.run_dir,
                args.mcp_executable,
                args.mcp_cwd,
                agent_model=args.agent_model,
                agent_task=args.agent_task,
                max_turns=args.max_turns,
                persist_architecture=args.persist_architecture,
                base_url=os.environ.get("SKYNET_BASE_URL")
                if args.agent_model
                else None,
                api_key=os.environ.get("SKYNET_API_KEY") if args.agent_model else None,
                visual_model=(
                    os.environ.get("VISUAL_INSPECTION_MODEL")
                    if args.agent_model
                    else None
                ),
                visual_timeout_seconds=(
                    os.environ.get("VISUAL_INSPECTION_TIMEOUT_SECONDS")
                    if args.agent_model
                    else None
                ),
            )
        )
    except ProbeError as error:
        print(f"Connection verification failed: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Connection verification cancelled.", file=sys.stderr)
        return 130
    except Exception:  # noqa: BLE001 -- CLI boundary excludes sensitive raw errors
        print(
            "Connection verification failed during file access; check run paths.",
            file=sys.stderr,
        )
        return 1
    finally:
        logging.disable(previous_logging_disable)
    return 0


if __name__ == "__main__":
    sys.exit(main())
