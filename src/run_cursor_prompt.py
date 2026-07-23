"""Generic Cursor CLI runner — one prompt per invocation.

Examples:
  # Step 1 — README markdown
  python src/run_cursor_prompt.py \\
    --prompt prompts/readme-generation-prompt.md \\
    --out data/ContosoPizza.readme.md \\
    --label "README Markdown"

  # Step 2 — intro markdown
  python src/run_cursor_prompt.py \\
    --prompt prompts/service-introduction-page.md \\
    --out data/ContosoPizza.intro.md \\
    --label "Introduction Markdown"

  # Step 3 — in-place XML comments (no --out)
  python src/run_cursor_prompt.py \\
    --prompt "prompts/prompt-cursor-xml-comments.md" \\
    --inplace \\
    --require-cs-changes \\
    --label "XML documentation comments on API endpoints"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
from cursor_cli import run_cursor_prompt

XML_EXTRA = """
## Pipeline notes for this codebase
- Prefer documenting the HTTP API project (Web API / minimal APIs), including
  endpoint maps (`MapGet` / `MapPost` / …) and any controllers if present.
- Only add/update documentation comments — do not change business logic, routes,
  or auth attributes.
- Ensure XML documentation generation is enabled on the API `.csproj`
  (`GenerateDocumentationFile`) when missing, so comments can flow into OpenAPI.
- If the project uses Microsoft.AspNetCore.OpenApi instead of Swashbuckle, still
  enable XML docs and wire comments in the project's existing OpenAPI setup
  (do not invent a second Swagger stack unless required).
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one Cursor CLI prompt against the pulled source repo. "
            "Use --out for a markdown file deliverable, or --inplace for in-repo edits. "
            "Source dir defaults to SOURCE_REPO_DIR from .env."
        )
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Path to the prompt file (absolute or relative to repo root)",
    )
    parser.add_argument(
        "--source-dir",
        "--todo-app-dir",  # legacy alias
        dest="source_dir",
        default=str(config.SOURCE_DIR),
        help=f"Pulled source repo root (default: {config.SOURCE_DIR})",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write deliverable markdown to this path (mutually exclusive with --inplace)",
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="In-place edits under the source repo (no single output file)",
    )
    parser.add_argument(
        "--label",
        default="Markdown",
        help="Short label for the deliverable (shown in the pipeline instructions)",
    )
    parser.add_argument(
        "--extra",
        default="",
        help="Optional extra instructions appended to the prompt",
    )
    parser.add_argument(
        "--xml-notes",
        action="store_true",
        help="Append standard XML-comments pipeline notes (useful with --inplace)",
    )
    parser.add_argument(
        "--require-cs-changes",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail if no .cs files changed (typical for --inplace XML step)",
    )
    parser.add_argument(
        "--model",
        default=config.CURSOR_MODEL or "auto",
        help="Cursor model id (default: CURSOR_MODEL from .env, else auto)",
    )
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass --force so the agent can write files without prompts (default: on)",
    )
    args = parser.parse_args()

    if args.out and args.inplace:
        print("[!] Use either --out or --inplace, not both.", file=sys.stderr)
        return 1
    if not args.out and not args.inplace:
        print("[!] Provide --out <path> or --inplace.", file=sys.stderr)
        return 1

    prompt_path = Path(args.prompt)
    if not prompt_path.is_absolute():
        prompt_path = config.ROOT / prompt_path

    out_path = Path(args.out) if args.out else None
    if out_path is not None and not out_path.is_absolute():
        out_path = config.ROOT / out_path

    extra = args.extra
    if args.xml_notes:
        extra = f"{extra.rstrip()}\n\n{XML_EXTRA}".strip() if extra else XML_EXTRA

    return run_cursor_prompt(
        source_dir=Path(args.source_dir),
        prompt_path=prompt_path,
        out_path=out_path,
        model=args.model,
        force=args.force,
        deliverable_label=args.label,
        extra_instructions=extra,
        require_cs_changes=args.require_cs_changes,
    )


if __name__ == "__main__":
    sys.exit(main())
