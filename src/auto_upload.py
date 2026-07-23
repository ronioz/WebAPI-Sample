"""Upload OpenAPI specs into Apidog modules via REST import-openapi.

Default: upload every module listed in apidog_modules.json.
Spec files are resolved by name:
  data/<ModuleName>.openapi.json
  data/<ModuleName>.json

Markdown docs (readme/intro) are not uploaded — email them via send_email.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests
import urllib3

import config

BASE_URL = os.environ.get("APIDOG_BASE_URL", "").strip()
PROJECT_ID = os.environ.get("APIDOG_PROJECT_ID", "").strip()
ACCESS_TOKEN = os.environ.get("APIDOG_ACCESS_TOKEN")
MODULE_MAP_PATH = str(config.MODULE_MAP_PATH)
DATA_DIR = config.DATA_DIR


def import_url() -> str | None:
    if not BASE_URL or not PROJECT_ID:
        return None
    return f"{BASE_URL.rstrip('/')}/v1/projects/{PROJECT_ID}/import-openapi"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


VERIFY_SSL = _env_flag("APIDOG_VERIFY_SSL", default=True)
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_module_map(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"[!] Module map not found at {path}.")
        return {}
    except json.JSONDecodeError as e:
        print(f"[!] Module map {path} is not valid JSON: {e}")
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def parse_module_id(module_name: str, raw) -> Optional[int]:
    try:
        module_id = int(raw)
    except (TypeError, ValueError):
        print(f"[!] Module ID for '{module_name}' must be an integer, got {raw!r}.")
        return None
    if module_id <= 0:
        print(f"[!] Module ID for '{module_name}' must be a positive integer, got {module_id}.")
        return None
    return module_id


def list_modules(module_map: dict) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    for name, raw in module_map.items():
        module_id = parse_module_id(name, raw)
        if module_id is None:
            continue
        result.append((name, module_id))
    return result


def resolve_module_id(module_map: dict, module_name: str) -> Optional[int]:
    if module_name not in module_map:
        print(
            f"\n[!] No module ID found for '{module_name}' in {MODULE_MAP_PATH}.\n"
            f"    Create the module once in Apidog (+ -> New Module), copy its\n"
            f"    moduleId, and add \"{module_name}\": <id> to {MODULE_MAP_PATH}.\n"
        )
        return None
    return parse_module_id(module_name, module_map[module_name])


def resolve_spec_for_module(module_name: str) -> Optional[Path]:
    for candidate in (
        DATA_DIR / f"{module_name}.openapi.json",
        DATA_DIR / f"{module_name}.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def load_spec(spec_path: str | Path) -> dict:
    with open(spec_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_folder_tags(spec: dict) -> None:
    missing = []
    for path, methods in spec.get("paths", {}).items():
        for verb, op in methods.items():
            if not isinstance(op, dict):
                continue
            if "x-apidog-folder" not in op and not op.get("tags"):
                missing.append(f"{verb.upper()} {path}")
    if missing:
        print(
            f"[!] {len(missing)} endpoint(s) have no x-apidog-folder/tags "
            f"and will import into the module root:"
        )
        for item in missing[:10]:
            print(f"      - {item}")
        if len(missing) > 10:
            print(f"      ... and {len(missing) - 10} more")


def count_schemas(spec: dict) -> int:
    schemas = (spec.get("components") or {}).get("schemas") or {}
    return len(schemas) if isinstance(schemas, dict) else 0


def summarize_spec(spec: dict) -> None:
    path_count = len(spec.get("paths") or {})
    schema_count = count_schemas(spec)
    print(f"[*] Spec contents: paths={path_count} schemas={schema_count}")
    if path_count and schema_count == 0:
        print(
            "[!] Spec has endpoints but no components.schemas — "
            "Apidog will import endpoints without data models."
        )


def summarize_counters(counters: dict) -> bool:
    created = int(counters.get("endpointCreated", 0) or 0)
    updated = int(counters.get("endpointUpdated", 0) or 0)
    ignored = int(counters.get("endpointIgnored", 0) or 0)
    failed = int(counters.get("endpointFailed", 0) or 0)
    schema_created = int(counters.get("schemaCreated", 0) or 0)
    schema_updated = int(counters.get("schemaUpdated", 0) or 0)
    schema_ignored = int(counters.get("schemaIgnored", 0) or 0)
    schema_failed = int(counters.get("schemaFailed", 0) or 0)

    print(f"[+] SUCCESS. {json.dumps(counters, indent=2)}")
    print(
        f"[*] Endpoints: created={created} updated={updated} "
        f"ignored={ignored} failed={failed}"
    )
    print(
        f"[*] Schemas: created={schema_created} updated={schema_updated} "
        f"ignored={schema_ignored} failed={schema_failed}"
    )
    if failed or schema_failed:
        print("[!] Some endpoints or schemas failed to import.")
        return False
    if created == 0 and updated == 0 and schema_created == 0 and schema_updated == 0:
        print("[!] All endpoint/schema counters are zero.")
        return False
    return True


def run_import_rest(
    spec: dict,
    module_id: int,
    move_existing_endpoints: bool = False,
) -> bool:
    url = import_url()
    if url is None:
        print(
            "[!] Set APIDOG_BASE_URL and APIDOG_PROJECT_ID in .env "
            "(no hardcoded host defaults)."
        )
        return False

    validate_folder_tags(spec)
    summarize_spec(spec)

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Apidog-Api-Version": "2024-03-28",
    }
    payload = {
        "input": json.dumps(spec),
        "options": {
            "moduleId": module_id,
            "endpointOverwriteBehavior": "OVERWRITE_EXISTING",
            "schemaOverwriteBehavior": "OVERWRITE_EXISTING",
            "updateFolderOfChangedEndpoint": move_existing_endpoints,
            "prependBasePath": False,
        },
    }

    print(f"[*] REST import into module ID {module_id}: {url}")
    if not VERIFY_SSL:
        print("[!] APIDOG_VERIFY_SSL=false — TLS certificate verification is disabled.")

    try:
        response = requests.post(
            url, json=payload, headers=headers, verify=VERIFY_SSL, timeout=60,
        )
    except requests.exceptions.RequestException as e:
        print(f"\n[!] Critical Network Error: {e}")
        return False

    print(f"\n[*] Gateway Status Code: {response.status_code}")
    if response.status_code in (200, 201):
        try:
            counters = response.json().get("data", {}).get("counters", {})
            return summarize_counters(counters)
        except (ValueError, AttributeError):
            print(f"[+] SUCCESS. Raw response: {response.text}")
            return True

    print(f"[!] Push rejected.\n[*] Raw response: {response.text}")
    return False


def upload_one_module(
    module_name: str,
    module_id: int,
    spec_path: Path,
    move_existing_endpoints: bool = False,
) -> bool:
    print(f"\n=== Module {module_name} (id={module_id}) ===")
    print(f"[*] Spec: {spec_path}")
    try:
        spec = load_spec(spec_path)
    except FileNotFoundError:
        print(f"[!] Error: {spec_path} not found.")
        return False
    except json.JSONDecodeError as e:
        print(f"[!] Error: {spec_path} is not valid JSON: {e}")
        return False
    return run_import_rest(spec, module_id, move_existing_endpoints=move_existing_endpoints)


def upload_all_modules(move_existing_endpoints: bool = False) -> bool:
    if not ACCESS_TOKEN:
        print("[!] APIDOG_ACCESS_TOKEN is not set (.env or environment).")
        return False
    if not BASE_URL or not PROJECT_ID:
        print(
            "[!] Set APIDOG_BASE_URL and APIDOG_PROJECT_ID in .env "
            "(no hardcoded host defaults)."
        )
        return False

    module_map = load_module_map(MODULE_MAP_PATH)
    modules = list_modules(module_map)
    if not modules:
        print(f"[!] No valid modules in {MODULE_MAP_PATH}.")
        return False

    print(f"[*] Uploading {len(modules)} module(s) from {MODULE_MAP_PATH}")

    mapped = {name for name, _ in modules}
    orphan_openapi = sorted(
        p.name[: -len(".openapi.json")]
        for p in DATA_DIR.glob("*.openapi.json")
        if p.name[: -len(".openapi.json")] not in mapped
    )
    if orphan_openapi:
        print(
            "[*] Spec files on disk with no apidog_modules.json entry "
            "(create the Apidog module and add the id):"
        )
        for name in orphan_openapi:
            print(f'    "{name}": "<moduleId>",')

    results: list[tuple[str, str]] = []  # name, OK|FAIL|SKIP
    for name, module_id in modules:
        spec_path = resolve_spec_for_module(name)
        if spec_path is None:
            print(
                f"\n[*] Module '{name}': no spec found — skipping. Expected one of:\n"
                f"      {DATA_DIR / f'{name}.openapi.json'}\n"
                f"      {DATA_DIR / f'{name}.json'}"
            )
            results.append((name, "SKIP"))
            continue
        ok = upload_one_module(
            module_name=name,
            module_id=module_id,
            spec_path=spec_path,
            move_existing_endpoints=move_existing_endpoints,
        )
        results.append((name, "OK" if ok else "FAIL"))

    print("\n=== Summary ===")
    all_ok = True
    uploaded = 0
    for name, status in results:
        print(f"  [{status}] {name}")
        if status == "FAIL":
            all_ok = False
        elif status == "OK":
            uploaded += 1
    if uploaded == 0 and any(s == "SKIP" for _, s in results):
        print("[!] No modules uploaded (all mapped entries skipped — missing specs).")
        return False
    return all_ok


def upload_single_module(
    module_name: str,
    spec_path: Optional[str] = None,
    move_existing_endpoints: bool = False,
) -> bool:
    if not ACCESS_TOKEN:
        print("[!] APIDOG_ACCESS_TOKEN is not set (.env or environment).")
        return False
    if not BASE_URL or not PROJECT_ID:
        print(
            "[!] Set APIDOG_BASE_URL and APIDOG_PROJECT_ID in .env "
            "(no hardcoded host defaults)."
        )
        return False

    module_map = load_module_map(MODULE_MAP_PATH)
    module_id = resolve_module_id(module_map, module_name)
    if module_id is None:
        return False

    resolved = Path(spec_path) if spec_path else resolve_spec_for_module(module_name)
    if resolved is None or not resolved.is_file():
        print(
            f"[!] Module '{module_name}': no spec found. Expected one of:\n"
            f"      {DATA_DIR / f'{module_name}.openapi.json'}\n"
            f"      {DATA_DIR / f'{module_name}.json'}\n"
            f"    Or pass --spec explicitly."
        )
        return False

    return upload_one_module(
        module_name=module_name,
        module_id=module_id,
        spec_path=resolved,
        move_existing_endpoints=move_existing_endpoints,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Push OpenAPI into Apidog via REST import-openapi. "
            "With no --module, uploads every module in apidog_modules.json "
            "(expects data/<Name>.openapi.json). Markdown is emailed separately."
        )
    )
    parser.add_argument(
        "--module",
        default=None,
        help="Upload only this module key from apidog_modules.json (default: all)",
    )
    parser.add_argument(
        "--spec",
        default=None,
        help="OpenAPI JSON path (only with --module; otherwise naming convention)",
    )
    parser.add_argument(
        "--move-existing",
        action="store_true",
        help="Move existing endpoints to tagged folders on update",
    )
    args = parser.parse_args()

    if args.spec and not args.module:
        print("[!] --spec requires --module (all-modules mode uses naming convention).")
        return 1

    if args.module:
        ok = upload_single_module(
            module_name=args.module,
            spec_path=args.spec,
            move_existing_endpoints=args.move_existing,
        )
    else:
        ok = upload_all_modules(move_existing_endpoints=args.move_existing)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
