"""Export OpenAPI from the pulled .NET API into data/ (build-time only).

Single API: data/<Module>.openapi.json
Multi API (--all): one file per OpenAPI-capable Web API (Catalog.API -> Catalog).

Requires: dotnet SDK on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import config
from openapi_order import apply_step_summary_prefixes

_SKIP = {"bin", "obj", "tests", "test", "node_modules"}
_OPENAPI_PKGS = (
    "Microsoft.AspNetCore.OpenApi",
    "Microsoft.Extensions.ApiDescription.Server",
    "Swashbuckle",
)
_EXCLUDE = ("apphost", "webapp", "clientapp", "hybridapp", "webhookclient", "servicedefaults")
# ApiDescription.Server major must match the project TFM (v10 only ships tools/net10.0).
_APIDESC_VERSION = {
    6: "6.0.36",
    7: "7.0.20",
    8: "8.0.17",
    9: "9.0.6",
    10: "10.0.0",
}
_PKG_REF_RE = re.compile(
    r'Include="Microsoft\.Extensions\.ApiDescription\.Server"[^>]*Version="([^"]+)"',
    re.IGNORECASE,
)
_TFM_RE = re.compile(r"<TargetFramework>\s*net(\d+(?:\.\d+)?)", re.IGNORECASE)


def find_dotnet() -> str:
    env = os.environ.get("DOTNET_EXECUTABLE")
    if env and Path(env).is_file():
        return env
    which = shutil.which("dotnet")
    if which:
        return which
    if os.name == "nt":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            candidate = Path(base) / "dotnet" / "dotnet.exe"
            if candidate.is_file():
                return str(candidate)
    print("[!] dotnet not found. Install the .NET SDK or set DOTNET_EXECUTABLE.")
    sys.exit(1)


def read_csproj(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def path_ok(path: Path, root: Path) -> bool:
    try:
        parts = {p.lower() for p in path.relative_to(root).parts[:-1]}
    except ValueError:
        parts = {p.lower() for p in path.parts[:-1]}
    return not parts.intersection(_SKIP)


def has_openapi(text: str) -> bool:
    return any(m in text for m in _OPENAPI_PKGS)


def is_openapi_web(path: Path) -> bool:
    text = read_csproj(path)
    if "Microsoft.NET.Sdk.Web" not in text or not has_openapi(text):
        return False
    stem = path.stem.lower()
    return not any(t in stem for t in _EXCLUDE)


def module_name_for(project: Path) -> str:
    stem = project.stem
    return stem[: -len(".api")] if stem.lower().endswith(".api") else stem


def resolve_output_module(
    cli_module: str,
    project: Path,
    source_dir: Path | None = None,
) -> str:
    """Module key for data/<Name>.openapi.json — must match apidog_modules.json.

    Precedence: --module / OPENAPI_MODULE_NAME → SOURCE_REPO_DIR folder name → csproj stem.
    """
    name = (cli_module or config.OPENAPI_MODULE_NAME or "").strip()
    if name:
        return name
    if source_dir is not None:
        folder = source_dir.name.strip()
        if folder and folder not in {".", ""}:
            return folder
    return module_name_for(project)


def rel_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def run_dotnet(
    dotnet: str,
    args: list[str],
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    print(f"[*] dotnet {' '.join(args)}")
    result = subprocess.run(
        [dotnet, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )
    if check and result.returncode != 0:
        out = (result.stdout or "") + (result.stderr or "")
        if out.strip():
            print(out.rstrip())
        print(f"[!] dotnet {' '.join(args[:2])} failed (exit {result.returncode})")
        sys.exit(result.returncode or 1)
    return result


def build_env() -> dict[str, str]:
    """Allow older TFMs (e.g. net6) to run GetDocument tools on newer hosts."""
    env = os.environ.copy()
    env.setdefault("DOTNET_ROLL_FORWARD", "LatestMajor")
    env.setdefault("DOTNET_ROLL_FORWARD_ON_NO_CANDIDATE_FX", "2")
    return env


def discover_apis(source_dir: Path) -> list[Path]:
    return [
        p.resolve()
        for p in sorted(source_dir.rglob("*.csproj"))
        if path_ok(p, source_dir) and is_openapi_web(p)
    ]


def filter_apis(projects: list[Path], selectors: list[str]) -> list[Path]:
    if not selectors:
        return projects
    selected: list[Path] = []
    for raw in selectors:
        sel = raw.strip().replace("\\", "/").removesuffix(".csproj").lower()
        if not sel:
            continue
        matches = [
            p
            for p in projects
            if p.stem.lower() in {sel, f"{sel}.api"}
            or sel in str(p).replace("\\", "/").lower()
        ]
        if not matches:
            print(f"[!] No discovered API matches: {raw}")
            continue
        for m in matches:
            if m not in selected:
                selected.append(m)
    return selected


def resolve_project(source_dir: Path, project: str) -> Path:
    raw = (project or "").strip().strip("\"'")
    apis = discover_apis(source_dir)

    if not raw:
        if len(apis) == 1:
            print(f"[*] Auto-selected: {rel_to(apis[0], source_dir)}")
            return apis[0]
        if not apis:
            print(f"[!] No OpenAPI-capable Web API under {source_dir}")
            sys.exit(1)
        print("[!] Multiple APIs found; set OPENAPI_PROJECT or use --all:")
        for p in apis:
            print(f"    - {rel_to(p, source_dir)}  -> {module_name_for(p)}")
        sys.exit(1)

    path = Path(raw) if Path(raw).is_absolute() else source_dir / raw
    if path.is_file() and path.suffix.lower() == ".csproj":
        return path.resolve()

    name = Path(raw).name.removesuffix(".csproj").lower()
    matches = [p for p in apis if p.stem.lower() in {name, f"{name}.api"}]
    if not matches:
        matches = [
            p.resolve()
            for p in source_dir.rglob(f"{Path(raw).name.removesuffix('.csproj')}.csproj")
            if path_ok(p, source_dir)
        ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        print(f"[!] No .csproj for OPENAPI_PROJECT={raw!r}")
        sys.exit(1)
    print(f"[!] Ambiguous OPENAPI_PROJECT={raw!r}; set a full .csproj path:")
    for p in matches:
        print(f"    - {rel_to(p, source_dir)}")
    sys.exit(1)


def ensure_apidescription_server(dotnet: str, project: Path) -> None:
    """Ensure a TFM-compatible ApiDescription.Server package (for build-time OpenAPI)."""
    text = read_csproj(project)
    if not has_openapi(text):
        return

    tfm = _TFM_RE.search(text)
    major = int(float(tfm.group(1))) if tfm else 8
    want = _APIDESC_VERSION.get(major, f"{major}.0.0")

    match = _PKG_REF_RE.search(text)
    if match:
        have = match.group(1)
        have_major = int(have.split(".")[0]) if have.split(".")[0].isdigit() else -1
        if have_major == major:
            return
        print(f"[*] ApiDescription.Server {have} is incompatible with net{major}.0; replacing with {want}")
        subprocess.run(
            [dotnet, "remove", str(project), "package", "Microsoft.Extensions.ApiDescription.Server"],
            cwd=str(project.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    else:
        print(f"[*] Adding Microsoft.Extensions.ApiDescription.Server {want}...")

    result = subprocess.run(
        [
            dotnet, "add", str(project), "package",
            "Microsoft.Extensions.ApiDescription.Server", "--version", want,
        ],
        cwd=str(project.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        print(f"[!] Could not add ApiDescription.Server {want}: {msg[:300]}")


def load_openapi(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and "openapi" in data and isinstance(data.get("paths"), dict):
        return data
    return None


def find_generated_docs(project: Path, docs_dir: Path) -> list[Path]:
    roots = [docs_dir, project.parent / "obj"]
    cursor = project
    for _ in range(6):
        cursor = cursor.parent
        candidate = cursor / "artifacts" / "obj" / project.stem
        if candidate.is_dir():
            roots.append(candidate)
            break

    found: list[Path] = []
    seen: set[Path] = set()
    skip = ("appsettings", "launchsettings", "package", "tsconfig")
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.json"):
            if any(part.lower() in {"bin", "node_modules"} for part in path.parts):
                continue
            if any(path.stem.lower().startswith(s) for s in skip):
                continue
            resolved = path.resolve()
            if resolved in seen or load_openapi(resolved) is None:
                continue
            seen.add(resolved)
            found.append(resolved)
    return found


def pick_doc(files: list[Path], project: Path) -> Path:
    if len(files) == 1:
        return files[0]
    named = [f for f in files if f.stem.lower() == project.stem.lower()]
    return named[0] if len(named) == 1 else sorted(files, key=lambda p: p.name.lower())[0]


def add_apidog_folders(spec: dict[str, Any]) -> None:
    patched = 0
    for methods in (spec.get("paths") or {}).values():
        if not isinstance(methods, dict):
            continue
        for op in methods.values():
            if isinstance(op, dict) and not op.get("x-apidog-folder") and op.get("tags"):
                op["x-apidog-folder"] = op["tags"][0]
                patched += 1
    print(f"[*] Added x-apidog-folder on {patched} operation(s)")


def write_spec(spec: dict[str, Any], out_dir: Path, module_name: str) -> Path:
    add_apidog_folders(spec)
    apply_step_summary_prefixes(spec)
    paths = spec.get("paths") or {}
    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    print(f"[*] Spec: paths={len(paths)} schemas={len(schemas)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{module_name}.openapi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[+] Wrote {out_path}")
    return out_path


def find_fallback_spec(project: Path, source_dir: Path | None = None) -> Path | None:
    """Use a checked-in swagger/openapi JSON when build-time generation fails."""
    candidates: list[Path] = [
        project.parent / "swagger.json",
        project.parent / "openapi.json",
        project.parent.parent / "swagger.json",
        project.parent.parent / "openapi.json",
    ]
    if source_dir is not None:
        candidates.extend([source_dir / "swagger.json", source_dir / "openapi.json"])
    for path in candidates:
        if path.is_file() and load_openapi(path) is not None:
            return path.resolve()
    return None


def export_one(
    *,
    dotnet: str,
    project: Path,
    module_name: str,
    out_dir: Path,
    source_dir: Path | None = None,
) -> Path:
    print(f"[*] Project: {project}")
    print(f"[*] Module:  {module_name}")

    docs_dir = (project.parent / ".openapi-export").resolve()
    if docs_dir.exists():
        shutil.rmtree(docs_dir, ignore_errors=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    ensure_apidescription_server(dotnet, project)
    print("[*] Building with OpenAPI document generation...")
    build = run_dotnet(
        dotnet,
        [
            "build", str(project), "-c", "Release", "--no-incremental",
            "--verbosity", "minimal",
            "/p:OpenApiGenerateDocuments=true",
            "/p:OpenApiGenerateDocumentsOnBuild=true",
            # Keep the project's GenerateDocumentationFile setting — Swashbuckle
            # IncludeXmlComments fails if the XML file is missing.
            "/p:NoWarn=1570%3B1591%3BCS1570%3BCS1591",
            "/p:TreatWarningsAsErrors=false",
            "/p:NuGetAudit=false",
            f"/p:OpenApiDocumentsDirectory={docs_dir}",
        ],
        check=False,
        env=build_env(),
    )

    files = find_generated_docs(project, docs_dir)
    if not files:
        fallback = find_fallback_spec(project, source_dir)
        if fallback is not None:
            print(f"[!] Build-time OpenAPI failed; using checked-in spec: {fallback}")
            if build.returncode != 0:
                tail = "\n".join((build.stdout or "").strip().splitlines()[-8:])
                if tail:
                    print(tail)
            files = [fallback]
        else:
            if build.returncode != 0:
                print(f"[!] Build failed for {project.name} (exit {build.returncode})")
                tail = "\n".join((build.stdout or "").strip().splitlines()[-30:])
                if tail:
                    print(tail)
            else:
                print(f"[!] Build succeeded but produced no OpenAPI JSON for {project.name}.")
                # Show whether GenerateOpenApiDocuments ran at all.
                for line in (build.stdout or "").splitlines():
                    if "GenerateOpenApi" in line or "Writing document" in line or "Generating document" in line:
                        print(line)
            print("[!] No build-time OpenAPI JSON found (and no swagger.json fallback).")
            sys.exit(build.returncode or 1)

    chosen = pick_doc(files, project)
    print(f"[*] Using: {chosen}")
    spec = load_openapi(chosen)
    if spec is None:
        print(f"[!] Invalid OpenAPI document: {chosen}")
        sys.exit(1)
    return write_spec(spec, out_dir, module_name)


def print_module_map_hint(names: list[str]) -> None:
    existing: set[str] = set()
    if config.MODULE_MAP_PATH.is_file():
        try:
            raw = json.loads(config.MODULE_MAP_PATH.read_text(encoding="utf-8"))
            existing = {k for k in raw if not str(k).startswith("_")}
        except (OSError, json.JSONDecodeError):
            pass
    missing = [n for n in names if n not in existing]
    if missing:
        print("\n[*] Add these keys to apidog_modules.json:")
        for name in missing:
            print(f'    "{name}": "<moduleId>",')


def export_all(*, source_dir: Path, out_dir: Path, selectors: list[str]) -> int:
    projects = filter_apis(discover_apis(source_dir), selectors)
    if not projects:
        print(f"[!] No OpenAPI-capable API projects under {source_dir}")
        return 1

    print(f"[*] Discovered {len(projects)} API(s):")
    for project in projects:
        print(f"    - {rel_to(project, source_dir)}  -> {module_name_for(project)}")

    dotnet = find_dotnet()
    ok: list[str] = []
    failed = 0
    for project in projects:
        name = module_name_for(project)
        print(f"\n=== {name} ({project.name}) ===")
        try:
            export_one(
                dotnet=dotnet,
                project=project,
                module_name=name,
                out_dir=out_dir,
                source_dir=source_dir,
            )
            ok.append(name)
        except SystemExit as exc:
            print(f"[!] {name} failed (exit {exc.code if isinstance(exc.code, int) else 1}); continuing")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[!] {name} failed: {exc}; continuing")
            failed += 1

    print("\n=== Summary ===")
    for name in ok:
        print(f"  [OK]   {name}")
    if failed:
        print(f"  [FAIL] {failed} project(s)")
    print_module_map_hint(ok)
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build-time OpenAPI export -> data/<Module>.openapi.json (no running API)."
    )
    parser.add_argument(
        "--source-dir", "--todo-app-dir", dest="source_dir",
        default=str(config.SOURCE_DIR),
        help=f"Pulled source root (default: {config.SOURCE_DIR})",
    )
    parser.add_argument(
        "--project", default=config.OPENAPI_PROJECT or "",
        help="API csproj path or name (default: OPENAPI_PROJECT, else auto-select)",
    )
    parser.add_argument(
        "--module", default=config.OPENAPI_MODULE_NAME or "",
        help=(
            "Output key -> data/<Name>.openapi.json; must match apidog_modules.json "
            "(default: OPENAPI_MODULE_NAME, else SOURCE_REPO_DIR name, else csproj stem)"
        ),
    )
    parser.add_argument("--out-dir", default=str(config.DATA_DIR), help="Output directory")
    parser.add_argument(
        "--all", action="store_true", default=config.OPENAPI_ALL,
        help="Export every OpenAPI-capable API under the source dir",
    )
    parser.add_argument("--list-apis", action="store_true", help="List APIs and exit")
    parser.add_argument(
        "--projects", default=config.OPENAPI_PROJECTS,
        help="Filter for --all/--list-apis, e.g. Catalog.API,Ordering",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        print(f"[!] Source dir not found: {source_dir}. Run pull_source.py first.")
        return 1

    selectors = [p.strip() for p in args.projects.split(",") if p.strip()]

    if args.list_apis:
        projects = filter_apis(discover_apis(source_dir), selectors)
        if not projects:
            print(f"[!] No OpenAPI-capable API projects under {source_dir}")
            return 1
        print(f"[*] {len(projects)} API(s) under {source_dir}:")
        for project in projects:
            print(f"    - {rel_to(project, source_dir)}  -> {module_name_for(project)}")
        return 0

    if args.all:
        return export_all(source_dir=source_dir, out_dir=Path(args.out_dir), selectors=selectors)

    project = resolve_project(source_dir, args.project)
    module_name = resolve_output_module(args.module, project, source_dir)
    print(f"[*] Output module key: {module_name} (-> data/{module_name}.openapi.json)")
    print(
        "[*] Module key must match apidog_modules.json "
        "(set --module or OPENAPI_MODULE_NAME to override)."
    )
    dotnet = find_dotnet()
    print(f"[*] Using dotnet: {dotnet}")
    export_one(
        dotnet=dotnet,
        project=project,
        module_name=module_name,
        out_dir=Path(args.out_dir),
        source_dir=source_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
