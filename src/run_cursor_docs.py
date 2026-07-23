"""Orchestrate Cursor steps 2-4 from info/tasks.md.

Runs the three prompts in order via the shared runner:
  2) readme-generation-prompt.md  -> data/<Module>.readme.md
  3) service-introduction-page.md -> data/<Module>.intro.md
  4) prompt-cursor-xml-comments   -> in-place .cs edits

Usage:
  python src/run_cursor_docs.py
  python src/run_cursor_docs.py --only readme,intro
  # (module / source dir / model come from .env — CLI flags optional)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import config
from cursor_cli import run_cursor_prompt
from run_cursor_prompt import XML_EXTRA


@dataclass(frozen=True)
class CursorTask:
    key: str
    step: int
    title: str
    prompt_name: str
    # Relative to DATA_DIR; None => in-place edits
    out_suffix: Optional[str]
    label: str
    require_cs_changes: bool = False
    extra_instructions: str = ""


# prompts for tasks.md steps 2-4 (filenames under prompts/).
TASKS: tuple[CursorTask, ...] = (
    CursorTask(
        key="readme",
        step=2,
        title="README generation",
        prompt_name="readme-generation-prompt.md",
        out_suffix=".readme.md",
        label="README Markdown",
    ),
    CursorTask(
        key="intro",
        step=3,
        title="Service introduction page",
        prompt_name="service-introduction-page.md",
        out_suffix=".intro.md",
        label="Introduction Markdown",
    ),
    CursorTask(
        key="xml",
        step=4,
        title="XML documentation comments",
        prompt_name="prompt-cursor-xml-comments.md",
        out_suffix=None,
        label="XML documentation comments on API endpoints",
        require_cs_changes=True,
        extra_instructions=XML_EXTRA,
    ),
)


def resolve_prompt(name: str) -> Path:
    path = config.PROMPTS_DIR / name
    if not path.is_file():
        # Case-insensitive fallback (Windows often fine; Linux CI may differ)
        matches = [
            p for p in config.PROMPTS_DIR.iterdir()
            if p.is_file() and p.name.lower() == name.lower()
        ]
        if matches:
            return matches[0]
        print(f"[!] Prompt not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path


def run_task(
    task: CursorTask,
    *,
    source_dir: Path,
    module: str,
    model: str,
    force: bool,
) -> int:
    out_path = (
        config.DATA_DIR / f"{module}{task.out_suffix}"
        if task.out_suffix is not None
        else None
    )
    print("\n" + "=" * 60)
    print(f"[*] Step {task.step}: {task.title} ({task.key})")
    print("=" * 60)

    return run_cursor_prompt(
        source_dir=source_dir,
        prompt_path=resolve_prompt(task.prompt_name),
        out_path=out_path,
        model=model,
        force=force,
        deliverable_label=task.label,
        extra_instructions=task.extra_instructions,
        require_cs_changes=task.require_cs_changes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Cursor documentation steps 2-4 (readme, intro, xml-comments) "
            "in order against the pulled source repo."
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
        "--module",
        default=config.OPENAPI_MODULE_NAME or None,
        required=not bool(config.OPENAPI_MODULE_NAME),
        help="Module name for data/<Module>.readme.md / .intro.md",
    )
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "Comma-separated task keys to run "
            f"(default: all). Keys: {', '.join(t.key for t in TASKS)}"
        ),
    )
    parser.add_argument(
        "--model",
        default=config.CURSOR_MODEL or "auto",
        help=f"Cursor model id (default: CURSOR_MODEL from .env, else auto)",
    )
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass --force to Cursor CLI (default: on)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run remaining tasks even if one fails",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        print(f"[!] Source dir not found: {source_dir}. Run pull_source.py first.")
        return 1
    if not args.module:
        print("[!] Provide --module or OPENAPI_MODULE_NAME.")
        return 1

    selected = {t.key for t in TASKS}
    if args.only:
        selected = {k.strip() for k in args.only.split(",") if k.strip()}
        unknown = selected - {t.key for t in TASKS}
        if unknown:
            print(f"[!] Unknown task key(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1

    results: list[tuple[str, int]] = []
    for task in TASKS:
        if task.key not in selected:
            continue
        code = run_task(
            task,
            source_dir=source_dir,
            module=args.module,
            model=args.model,
            force=args.force,
        )
        results.append((task.key, code))
        if code != 0 and not args.continue_on_error:
            break

    print("\n=== Cursor docs summary ===")
    all_ok = True
    for key, code in results:
        status = "OK" if code == 0 else f"FAIL({code})"
        print(f"  [{status}] {key}")
        if code != 0:
            all_ok = False

    ran = {k for k, _ in results}
    not_run = [t.key for t in TASKS if t.key in selected and t.key not in ran]
    for key in not_run:
        print(f"  [SKIP] {key}")

    return 0 if all_ok and not not_run else 1


if __name__ == "__main__":
    sys.exit(main())
