"""Shared Cursor CLI runner for pipeline prompt steps (readme, intro, xml-comments, …)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import config

DEFAULT_MODEL = os.environ.get("CURSOR_MODEL", "auto")

_CLI_CANDIDATES = (
    "agent",
    "cursor-agent",
)


def find_cursor_cli() -> str:
    env = os.environ.get("CURSOR_CLI")
    if env and Path(env).is_file():
        return env
    if env and shutil.which(env):
        return env

    for name in _CLI_CANDIDATES:
        which = shutil.which(name)
        if which:
            return which

    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    extras = [
        home / ".local" / "bin" / "agent.exe",
        home / ".local" / "bin" / "agent.cmd",
        home / ".cursor" / "bin" / "agent.exe",
        local / "cursor-agent" / "agent.exe",
        local / "Programs" / "cursor" / "resources" / "app" / "bin" / "agent.cmd",
    ]
    for path in extras:
        if path.is_file():
            return str(path)

    print(
        "[!] Cursor CLI not found (`agent` / `cursor-agent`).\n"
        "    Install: https://cursor.com/docs/cli/overview\n"
        "    Windows PowerShell:\n"
        "      irm 'https://cursor.com/install?win32=true' | iex\n"
        "    Then run: agent login\n"
        "    Or set CURSOR_CLI to the full path of agent.exe."
    )
    sys.exit(1)


def load_prompt(path: Path) -> str:
    if not path.is_file():
        print(f"[!] Prompt file not found: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def resolve_workspace(source_dir: Path, out_path: Optional[Path]) -> Path:
    """Pick Cursor --workspace so deliverables stay inside the sandbox.

    In-place edits (XML comments): workspace = source clone.
    Markdown under data/: workspace = pipeline repo root (so data/ is writable),
    with instructions to analyze only source_dir.
    """
    source = source_dir.resolve()
    if out_path is None:
        return source
    out = out_path.resolve()
    try:
        out.relative_to(source)
        return source
    except ValueError:
        return config.ROOT.resolve()


def build_user_message(
    prompt_body: str,
    source_dir: Path,
    *,
    workspace: Path,
    out_path: Optional[Path] = None,
    deliverable_label: str = "Markdown",
    extra_instructions: str = "",
) -> str:
    source = source_dir.resolve()
    parts = [
        prompt_body.rstrip(),
        "",
        "---",
        "## Pipeline output (required)",
        f"- Cursor workspace root: `{workspace.resolve()}`",
        f"- Analyze **only** this source project (API projects, endpoints, auth, domain model):",
        f"  `{source}`",
        "- Do not invent files outside that source tree except for the deliverable path below.",
    ]
    if out_path is not None:
        parts.extend(
            [
                f"- Write the final {deliverable_label} to this exact file path:",
                f"  `{out_path.resolve()}`",
                "- Create parent directories if needed.",
                "- Overwrite the file if it already exists.",
                "- Do NOT only print the markdown in chat — the file on disk is the deliverable.",
                "- Do NOT regenerate OpenAPI/Swagger.",
            ]
        )
    else:
        parts.extend(
            [
                f"- Deliverable: {deliverable_label}",
                f"- Edit files **under** `{source}` only (save changes to disk).",
                "- Do NOT only print suggested patches in chat — apply the edits.",
                "- Do NOT regenerate OpenAPI/Swagger in this step "
                "(a later pipeline step exports OpenAPI).",
            ]
        )
    if extra_instructions.strip():
        parts.extend(["", extra_instructions.strip()])
    return "\n".join(parts) + "\n"


def _snapshot_cs_mtimes(root: Path) -> dict[str, float]:
    snap: dict[str, float] = {}
    for path in root.rglob("*.cs"):
        if any(part in {"bin", "obj", ".git"} for part in path.parts):
            continue
        try:
            snap[str(path.resolve())] = path.stat().st_mtime
        except OSError:
            continue
    return snap


def run_cursor_prompt(
    *,
    source_dir: Path,
    prompt_path: Path,
    out_path: Optional[Path] = None,
    model: str = DEFAULT_MODEL,
    force: bool = True,
    deliverable_label: str = "Markdown",
    extra_instructions: str = "",
    require_cs_changes: bool = False,
) -> int:
    if not source_dir.is_dir():
        print(f"[!] Source dir not found: {source_dir}. Run pull_source.py first.")
        return 1

    workspace = resolve_workspace(source_dir, out_path)
    cli = find_cursor_cli()
    prompt_body = load_prompt(prompt_path)
    message = build_user_message(
        prompt_body,
        source_dir,
        workspace=workspace,
        out_path=out_path,
        deliverable_label=deliverable_label,
        extra_instructions=extra_instructions,
    )
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    before_cs = _snapshot_cs_mtimes(source_dir) if require_cs_changes else {}

    cmd = [
        cli,
        "--print",
        "--output-format",
        "text",
        "--workspace",
        str(workspace),
        "--model",
        model,
        "--trust",
    ]
    if force:
        cmd.append("--force")

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if api_key:
        cmd.extend(["--api-key", api_key])

    print(f"[*] CLI:         {cli}")
    print(f"[*] Workspace:   {workspace}")
    print(f"[*] Source:      {source_dir.resolve()}")
    print(f"[*] Prompt:      {prompt_path.resolve()}")
    if out_path is not None:
        print(f"[*] Output:      {out_path.resolve()}")
    else:
        print("[*] Output:      in-place edits under source dir")
    print(f"[*] Model:       {model}")
    print(f"[*] Auth:        {'CURSOR_API_KEY' if api_key else 'CLI session (agent login)'}")
    print("[*] Running Cursor agent (this can take several minutes)...")

    try:
        result = subprocess.run(
            cmd,
            input=message,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(workspace),
            check=False,
        )
    except OSError as e:
        print(f"[!] Failed to start Cursor CLI: {e}", file=sys.stderr)
        return 1

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)

    if result.returncode != 0:
        print(f"[!] Cursor CLI exited with code {result.returncode}", file=sys.stderr)
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        if "resource_exhausted" in combined.lower():
            print(
                "    Cursor reported resource_exhausted (quota / capacity / transport).\n"
                "    Try:\n"
                "      1) re-run with --model auto\n"
                "      2) agent login   (or refresh CURSOR_API_KEY)\n"
                "      3) Wait a few minutes and retry (rate limit / capacity)\n"
                "      4) In %USERPROFILE%\\.cursor\\cli-config.json add:\n"
                '           { "network": { "useHttp1ForAgent": true } }\n'
                "      5) Update CLI: agent update   (or reinstall)",
                file=sys.stderr,
            )
        elif not api_key:
            print(
                "    If this is an auth error, run: agent login\n"
                "    Or set CURSOR_API_KEY in .env",
                file=sys.stderr,
            )
        return result.returncode or 1

    if out_path is not None:
        if not out_path.is_file() or out_path.stat().st_size == 0:
            print(
                f"[!] Expected file was not written: {out_path}\n"
                "    Check the agent output; the prompt requires writing that path.",
                file=sys.stderr,
            )
            return 3
        print(f"[+] Wrote {out_path} ({out_path.stat().st_size} bytes)")
        return 0

    if require_cs_changes:
        after_cs = _snapshot_cs_mtimes(source_dir)
        changed = sorted(
            {
                path
                for path, mtime in after_cs.items()
                if path not in before_cs or before_cs[path] != mtime
            }
            | (set(after_cs) - set(before_cs))
        )
        if not changed:
            print(
                "[!] No .cs files were modified under the source tree.\n"
                "    The XML-comments step must edit endpoint source files in place.",
                file=sys.stderr,
            )
            return 3
        print(f"[+] Modified {len(changed)} .cs file(s):")
        for path in changed[:20]:
            print(f"      - {path}")
        if len(changed) > 20:
            print(f"      ... and {len(changed) - 20} more")
        return 0

    print("[+] Cursor agent finished (in-place edits).")
    return 0
