"""Thin wrapper: README prompt → data/<Module>.readme.md.

Prefer `python src/run_cursor_docs.py --only readme` for the canonical pipeline path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
from cursor_cli import DEFAULT_MODEL, run_cursor_prompt

DEFAULT_PROMPT = config.PROMPTS_DIR / "readme-generation-prompt.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step 2: run the README prompt on the pulled source via Cursor CLI "
            "and write data/<Module>.readme.md."
        )
    )
    parser.add_argument(
        "--source-dir",
        "--todo-app-dir",  # legacy alias
        dest="source_dir",
        default=str(config.SOURCE_DIR),
        help=f"Pulled source repo root (default: {config.SOURCE_DIR})",
    )
    parser.add_argument(
        "--prompt",
        default=str(DEFAULT_PROMPT),
        help=f"Prompt file (default: {DEFAULT_PROMPT})",
    )
    parser.add_argument(
        "--module",
        default=config.OPENAPI_MODULE_NAME,
        help="Module name -> data/<Name>.readme.md",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Override output path (default: data/<module>.readme.md)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Cursor model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass --force so the agent can write files without prompts (default: on)",
    )
    args = parser.parse_args()

    out_path = (
        Path(args.out)
        if args.out
        else config.DATA_DIR / f"{args.module}.readme.md"
    )

    return run_cursor_prompt(
        source_dir=Path(args.source_dir),
        prompt_path=Path(args.prompt),
        out_path=out_path,
        model=args.model,
        force=args.force,
        deliverable_label="README Markdown",
    )


if __name__ == "__main__":
    sys.exit(main())
