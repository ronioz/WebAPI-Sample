"""Run the full Apidog docs pipeline (steps 1-7) using existing modules.

  1 pull_source.py
  2-4 run_cursor_docs.py
  5 generate_openapi.py
  6 auto_upload.py
  7 send_email.py

Usage (from repo root):
  python src/orchestrator.py
  python src/orchestrator.py --skip-docs
  python src/orchestrator.py --only pull,openapi,upload
  python src/orchestrator.py --module ContosoPizza
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import config
import auto_upload as upload_mod
import generate_openapi as openapi_mod
import pull_source as pull_mod
import run_cursor_docs as docs_mod
import send_email as email_mod

STEP_ORDER = ("pull", "docs", "openapi", "upload", "email")


def _as_exit_code(result: object) -> int:
    if result is None:
        return 0
    if isinstance(result, bool):
        return 0 if result else 1
    if isinstance(result, int):
        return result
    return 0


def _run(label: str, fn: Callable[[], object]) -> int:
    print("\n" + "=" * 60)
    print(f"[*] Pipeline step: {label}")
    print("=" * 60)
    try:
        return _as_exit_code(fn())
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1


def step_pull(*, clean: bool | None = None) -> int:
    return pull_mod.pull_source(
        config.SOURCE_REPO_URL,
        Path(config.SOURCE_DIR),
        branch=config.SOURCE_BRANCH or None,
        token=config.SOURCE_REPO_TOKEN or None,
        depth=pull_mod._default_depth(),
        clean=pull_mod._default_clean() if clean is None else clean,
    )


def step_docs(
    *,
    source_dir: Path,
    module: str,
    model: str,
    only: str | None,
    continue_on_error: bool,
) -> int:
    selected = {t.key for t in docs_mod.TASKS}
    if only:
        selected = {k.strip() for k in only.split(",") if k.strip()}
        unknown = selected - {t.key for t in docs_mod.TASKS}
        if unknown:
            print(f"[!] Unknown docs task key(s): {', '.join(sorted(unknown))}")
            return 1

    results: list[tuple[str, int]] = []
    for task in docs_mod.TASKS:
        if task.key not in selected:
            continue
        code = docs_mod.run_task(
            task,
            source_dir=source_dir,
            module=module,
            model=model,
            force=True,
        )
        results.append((task.key, code))
        if code != 0 and not continue_on_error:
            break

    print("\n=== Cursor docs summary ===")
    all_ok = True
    for key, code in results:
        status = "OK" if code == 0 else f"FAIL({code})"
        print(f"  [{status}] {key}")
        if code != 0:
            all_ok = False
    ran = {k for k, _ in results}
    for key in sorted(selected - ran):
        print(f"  [SKIP] {key}")
    return 0 if all_ok and selected <= ran else 1


def step_openapi(*, source_dir: Path, module: str, export_all: bool) -> int:
    out_dir = config.DATA_DIR
    selectors = [
        p.strip() for p in config.OPENAPI_PROJECTS.split(",") if p.strip()
    ]

    if export_all:
        return openapi_mod.export_all(
            source_dir=source_dir,
            out_dir=out_dir,
            selectors=selectors,
        )

    project = openapi_mod.resolve_project(source_dir, config.OPENAPI_PROJECT)
    module_name = openapi_mod.resolve_output_module(module, project, source_dir)
    dotnet = openapi_mod.find_dotnet()
    print(f"[*] Using dotnet: {dotnet}")
    print(f"[*] Output module key: {module_name}")
    openapi_mod.export_one(
        dotnet=dotnet,
        project=project,
        module_name=module_name,
        out_dir=out_dir,
        source_dir=source_dir,
    )
    return 0


def step_upload(*, module: str | None, export_all: bool) -> int:
    if export_all or not module:
        ok = upload_mod.upload_all_modules()
    else:
        ok = upload_mod.upload_single_module(module_name=module)
    return 0 if ok else 1


def step_email(*, module: str, dry_run: bool = False) -> int:
    return email_mod.send_report(module=module, dry_run=dry_run)


def resolve_module(cli_module: str | None) -> str:
    module = (cli_module or config.OPENAPI_MODULE_NAME or "").strip()
    if module:
        return module
    name = Path(config.SOURCE_DIR).name
    if name and name not in {".", ""}:
        return name
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run pull -> Cursor docs -> OpenAPI export -> Apidog upload -> email. "
            "Uses SOURCE_* / OPENAPI_* / Apidog / SMTP settings from .env."
        )
    )
    parser.add_argument(
        "--module",
        default=None,
        help=(
            "Module name for docs + single-API export/upload/email "
            "(default: OPENAPI_MODULE_NAME or SOURCE_REPO_DIR name)"
        ),
    )
    parser.add_argument(
        "--only",
        default=None,
        help=f"Comma-separated steps to run (default: all). Keys: {', '.join(STEP_ORDER)}",
    )
    parser.add_argument("--skip-pull", action="store_true", help="Skip step 1")
    parser.add_argument("--skip-docs", action="store_true", help="Skip steps 2-4")
    parser.add_argument("--skip-openapi", action="store_true", help="Skip step 5")
    parser.add_argument("--skip-upload", action="store_true", help="Skip step 6")
    parser.add_argument("--skip-email", action="store_true", help="Skip step 7")
    parser.add_argument(
        "--docs-only",
        default=None,
        help="Pass-through to Cursor docs: readme,intro,xml",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=config.OPENAPI_ALL,
        help="Export/upload every OpenAPI-capable API (OPENAPI_ALL)",
    )
    parser.add_argument(
        "--model",
        default=config.CURSOR_MODEL or "auto",
        help="Cursor model for docs steps (default: CURSOR_MODEL or auto)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue remaining pipeline steps after a failure",
    )
    parser.add_argument(
        "--clean-pull",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Hard-reset the clone on pull (default: on when CI=true)",
    )
    parser.add_argument(
        "--email-dry-run",
        action="store_true",
        help="Build the email without sending",
    )
    args = parser.parse_args()

    selected = set(STEP_ORDER)
    if args.only:
        selected = {k.strip() for k in args.only.split(",") if k.strip()}
        unknown = selected - set(STEP_ORDER)
        if unknown:
            print(f"[!] Unknown step(s): {', '.join(sorted(unknown))}")
            return 1
    if args.skip_pull:
        selected.discard("pull")
    if args.skip_docs:
        selected.discard("docs")
    if args.skip_openapi:
        selected.discard("openapi")
    if args.skip_upload:
        selected.discard("upload")
    if args.skip_email:
        selected.discard("email")

    if not selected:
        print("[!] No steps selected.")
        return 1

    module = resolve_module(args.module)
    source_dir = Path(config.SOURCE_DIR)
    export_all = bool(args.all)

    if "docs" in selected and not module:
        print("[!] Docs step needs --module or OPENAPI_MODULE_NAME.")
        return 1
    if "email" in selected and not module:
        print("[!] Email step needs --module or OPENAPI_MODULE_NAME.")
        return 1
    if "pull" in selected and not config.SOURCE_REPO_URL:
        print("[!] Pull step needs SOURCE_REPO_URL.")
        return 1

    print("[*] Apidog docs pipeline")
    print(f"    steps:   {', '.join(s for s in STEP_ORDER if s in selected)}")
    print(f"    source:  {source_dir}")
    print(f"    module:  {module or '(multi / map-driven)'}")
    print(f"    openapi: {'all APIs' if export_all else 'single API'}")

    results: list[tuple[str, int]] = []

    def record(name: str, code: int) -> bool:
        results.append((name, code))
        if code != 0 and not args.continue_on_error:
            return False
        return True

    if "pull" in selected:
        code = _run("1 pull_source", lambda: step_pull(clean=args.clean_pull))
        if not record("pull", code):
            return _summary(results)

    if "docs" in selected:
        if not source_dir.is_dir():
            print(f"[!] Source dir not found: {source_dir}. Run pull first.")
            if not record("docs", 1):
                return _summary(results)
        else:
            code = _run(
                "2-4 run_cursor_docs",
                lambda: step_docs(
                    source_dir=source_dir,
                    module=module,
                    model=args.model,
                    only=args.docs_only,
                    continue_on_error=args.continue_on_error,
                ),
            )
            if not record("docs", code):
                return _summary(results)

    if "openapi" in selected:
        if not source_dir.is_dir():
            print(f"[!] Source dir not found: {source_dir}. Run pull first.")
            if not record("openapi", 1):
                return _summary(results)
        else:
            code = _run(
                "5 generate_openapi",
                lambda: step_openapi(
                    source_dir=source_dir,
                    module=module,
                    export_all=export_all,
                ),
            )
            if not record("openapi", code):
                return _summary(results)

    if "upload" in selected:
        code = _run(
            "6 auto_upload",
            lambda: step_upload(module=module or None, export_all=export_all),
        )
        if not record("upload", code):
            return _summary(results)

    if "email" in selected:
        code = _run(
            "7 send_email",
            lambda: step_email(module=module, dry_run=args.email_dry_run),
        )
        record("email", code)

    return _summary(results)


def _summary(results: list[tuple[str, int]]) -> int:
    print("\n=== Pipeline summary ===")
    all_ok = True
    for name, code in results:
        status = "OK" if code == 0 else f"FAIL({code})"
        print(f"  [{status}] {name}")
        if code != 0:
            all_ok = False
    return 0 if all_ok and results else 1


if __name__ == "__main__":
    sys.exit(main())
