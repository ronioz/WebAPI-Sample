"""Pull repo into data/ folder

Designed for both local runs and GitHub Actions:
  - git from PATH (preinstalled on GHA runners); optional GIT_EXECUTABLE override
  - SOURCE_REPO_URL / SOURCE_REPO_TOKEN from env (GHA secrets), not machine-local paths
  - shallow clone and hard reset when CI=true (or --clean / --depth)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import config

# Local Windows fallbacks only — never required on Linux/macOS or GHA.
_WINDOWS_GIT_CANDIDATES = (
    Path(r"C:\Program Files\Git\cmd\git.exe"),
    Path(r"C:\Program Files\Git\bin\git.exe"),
    Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
)


def find_git() -> str:
    env_git = os.environ.get("GIT_EXECUTABLE")
    if env_git and Path(env_git).is_file():
        return env_git

    which = shutil.which("git")
    if which:
        return which

    if os.name == "nt":
        for candidate in _WINDOWS_GIT_CANDIDATES:
            if candidate.is_file():
                return str(candidate)

    print(
        "[!] git executable not found on PATH.\n"
        "    On GitHub Actions use actions/checkout's runner (git is preinstalled),\n"
        "    or install git. Locally set GIT_EXECUTABLE if git is not on PATH."
    )
    sys.exit(1)


def run_git(
    git: str,
    args: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    print(f"[*] git {' '.join(args)}")
    try:
        return subprocess.run(
            [git, *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as e:
        print(f"[!] Failed to run {git!r}: {e}")
        sys.exit(1)


def die(result: subprocess.CompletedProcess, label: str) -> None:
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip())
    print(f"[!] {label} failed (exit {result.returncode})")
    sys.exit(result.returncode or 1)


def with_auth_token(url: str, token: str | None) -> str:
    """Embed token in HTTPS git URL for private repos (GHA: SOURCE_REPO_TOKEN / GITHUB_TOKEN)."""
    if not token:
        return url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        print("[!] SOURCE_REPO_TOKEN only applies to http(s) URLs; leaving URL unchanged.")
        return url
    # Avoid logging the token: caller prints the original URL.
    netloc = parts.netloc
    if "@" in netloc:
        # Already has userinfo — replace it.
        netloc = netloc.rsplit("@", 1)[-1]
    auth_netloc = f"x-access-token:{token}@{netloc}"
    return urlunsplit((parts.scheme, auth_netloc, parts.path, parts.query, parts.fragment))


def redact_url(url: str) -> str:
    """Safe-to-print URL (strip embedded credentials)."""
    return re.sub(r"(://)([^/@]+)@", r"\1***@", url)


def resolve_default_branch(git: str, repo_dir: Path, preferred: str | None = None) -> str:
    if preferred:
        remote = run_git(
            git,
            ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{preferred}"],
            cwd=repo_dir,
        )
        if remote.returncode == 0:
            return preferred
        print(f"[!] Requested branch '{preferred}' not found on origin.")
        sys.exit(1)

    # Prefer origin/HEAD when set (works for non-main default branches).
    sym = run_git(
        git, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], cwd=repo_dir,
    )
    if sym.returncode == 0:
        ref = (sym.stdout or "").strip()
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix):
            return ref[len(prefix) :]

    for candidate in ("main", "master"):
        local = run_git(
            git, ["show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"],
            cwd=repo_dir,
        )
        if local.returncode == 0:
            return candidate
        remote = run_git(
            git,
            ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{candidate}"],
            cwd=repo_dir,
        )
        if remote.returncode == 0:
            return candidate
    print("[!] Could not resolve default branch (tried origin/HEAD, main, master).")
    sys.exit(1)


def clone_repo(git: str, url: str, target: Path, depth: int | None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone"]
    if depth is not None and depth > 0:
        args.extend(["--depth", str(depth)])
    args.extend([url, str(target)])
    result = run_git(git, args)
    if result.returncode != 0:
        die(result, "git clone")


def sync_existing(
    git: str,
    repo_dir: Path,
    branch: str | None,
    clean: bool,
    depth: int | None,
) -> None:
    fetch_args = ["fetch", "origin"]
    if depth is not None and depth > 0:
        fetch_args.extend(["--depth", str(depth)])
    fetch = run_git(git, fetch_args, cwd=repo_dir)
    if fetch.returncode != 0:
        die(fetch, "git fetch")

    resolved = resolve_default_branch(git, repo_dir, preferred=branch)

    if clean:
        # Deterministic tree for CI / automation (discard local edits).
        checkout = run_git(
            git, ["checkout", "-B", resolved, f"origin/{resolved}"], cwd=repo_dir,
        )
        if checkout.returncode != 0:
            die(checkout, f"git checkout {resolved}")
        reset = run_git(git, ["reset", "--hard", f"origin/{resolved}"], cwd=repo_dir)
        if reset.returncode != 0:
            die(reset, "git reset --hard")
        cleaned = run_git(git, ["clean", "-fdx"], cwd=repo_dir)
        if cleaned.returncode != 0:
            die(cleaned, "git clean")
    else:
        checkout = run_git(git, ["checkout", resolved], cwd=repo_dir)
        if checkout.returncode != 0:
            checkout = run_git(
                git, ["checkout", "-B", resolved, f"origin/{resolved}"], cwd=repo_dir,
            )
            if checkout.returncode != 0:
                die(checkout, f"git checkout {resolved}")

        pull = run_git(git, ["pull", "--ff-only", "origin", resolved], cwd=repo_dir)
        if pull.returncode != 0:
            die(pull, f"git pull origin {resolved}")

    print(f"[+] On branch {resolved} at {repo_dir.resolve()}")


def is_nonempty(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def is_git_repo(path: Path) -> bool:
    """True if path itself is a git work tree (not a parent repo via walk-up)."""
    git_meta = path / ".git"
    if not git_meta.exists():
        return False
    # Plain clone (.git dir) or worktree/submodule (.git file)
    return git_meta.is_dir() or git_meta.is_file()


def remove_dir(path: Path) -> None:
    """Remove a directory tree; tolerate Windows locks with a short retry."""
    last_err: OSError | None = None
    for _ in range(3):
        try:
            if not path.exists():
                return
            shutil.rmtree(path)
            return
        except OSError as e:
            last_err = e
            time.sleep(0.2)
    # Last resort: empty then rmdir
    try:
        if path.is_dir():
            for child in path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            path.rmdir()
            return
    except OSError as e:
        last_err = e
    raise OSError(f"Could not remove {path}: {last_err}")


def pull_source(
    repo: str,
    target: Path,
    *,
    branch: str | None = None,
    token: str | None = None,
    depth: int | None = None,
    clean: bool = False,
) -> int:
    if not repo:
        print("[!] Provide --repo or SOURCE_REPO_URL in the environment / .env")
        return 1

    git = find_git()
    print(f"[*] Using git: {git}")
    print(f"[*] Remote: {redact_url(repo)}")

    auth_url = with_auth_token(repo, token)
    target = Path(target)

    if is_git_repo(target):
        print(f"[*] Updating existing clone: {target.resolve()}")
        # Guard: never run git against a parent repo if .git is missing/wrong.
        top = run_git(git, ["rev-parse", "--show-toplevel"], cwd=target)
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != target.resolve():
            print(
                f"[!] {target} looks like a broken git checkout "
                f"(toplevel={((top.stdout or '').strip() or 'unknown')}). "
                "Removing and re-cloning."
            )
            try:
                remove_dir(target)
            except OSError as e:
                print(f"[!] {e}")
                return 1
        else:
            if token:
                set_url = run_git(
                    git, ["remote", "set-url", "origin", auth_url], cwd=target,
                )
                if set_url.returncode != 0:
                    die(set_url, "git remote set-url")
            sync_existing(git, target, branch=branch, clean=clean, depth=depth)
            return 0

    if target.exists():
        if is_nonempty(target):
            print(
                f"[!] {target} exists but is not a git repo. "
                "Remove it or choose another --dir / SOURCE_REPO_DIR."
            )
            return 1
        print(f"[*] Removing empty leftover folder: {target}")
        try:
            remove_dir(target)
        except OSError as e:
            print(f"[!] {e}")
            return 1

    print(f"[*] Cloning into {target.resolve()}")
    clone_repo(git, auth_url, target, depth=depth)
    sync_existing(git, target, branch=branch, clean=clean, depth=depth)
    return 0


def _default_clean() -> bool:
    # GitHub Actions / most CI set CI=true
    return os.environ.get("CI", "").lower() in ("1", "true", "yes")


def _default_depth() -> int | None:
    raw = os.environ.get("SOURCE_CLONE_DEPTH", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            print(f"[!] SOURCE_CLONE_DEPTH must be an integer, got {raw!r}")
            sys.exit(1)
    if _default_clean():
        return 1
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clone or update the source repo and switch to the default branch "
            "(or --branch). CI-friendly: uses PATH git, env secrets, shallow clone."
        )
    )
    parser.add_argument(
        "--repo",
        default=config.SOURCE_REPO_URL,
        help="Git remote URL (or set SOURCE_REPO_URL)",
    )
    parser.add_argument(
        "--dir",
        default=str(config.SOURCE_DIR),
        help=f"Local folder for the repo (default: {config.SOURCE_DIR})",
    )
    parser.add_argument(
        "--branch",
        default=config.SOURCE_BRANCH or None,
        help="Branch to checkout (or SOURCE_BRANCH; default: origin/HEAD, else main/master)",
    )
    parser.add_argument(
        "--token",
        default=config.SOURCE_REPO_TOKEN or None,
        help="HTTPS token for private repos (or SOURCE_REPO_TOKEN / GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=_default_depth(),
        help="Shallow clone/fetch depth (default: 1 when CI=true, else full history)",
    )
    parser.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=_default_clean(),
        help="Hard reset + clean (default: on when CI=true)",
    )
    args = parser.parse_args()
    return pull_source(
        args.repo,
        Path(args.dir),
        branch=args.branch,
        token=args.token,
        depth=args.depth,
        clean=args.clean,
    )


if __name__ == "__main__":
    sys.exit(main())