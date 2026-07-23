"""Prefix OpenAPI summaries from ``Step N of M`` so Apidog's lexicographic
sidebar sort matches the documented flow order.

Apidog ignores JSON key order and sorts endpoints by name. Prefixing
``summary`` with a zero-padded step (``01. …``) is enough when descriptions
already contain ``**Step N of M**`` (from the XML-comments Cursor step).
"""

from __future__ import annotations

import re
from typing import Any

_HTTP_METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
}

_STEP_RE = re.compile(r"\*\*Step\s+(\d+)\s+of\s+(\d+)\*\*", re.IGNORECASE)
_PREFIX_RE = re.compile(r"^\s*\d{1,3}\.\s+")


def apply_step_summary_prefixes(spec: dict[str, Any]) -> dict[str, Any]:
    """Set ``summary`` to ``NN. <text>`` using Step N from each description."""
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return spec

    patched = 0
    skipped = 0
    for _path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            desc = op.get("description")
            if not isinstance(desc, str):
                skipped += 1
                continue
            match = _STEP_RE.search(desc)
            if not match:
                skipped += 1
                continue
            step = int(match.group(1))
            summary = op.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                summary = op.get("operationId") if isinstance(op.get("operationId"), str) else ""
                summary = summary or "Endpoint"
            summary = _PREFIX_RE.sub("", summary, count=1).lstrip()
            op["summary"] = f"{step:02d}. {summary}"
            patched += 1

    if patched:
        print(
            f"[*] Prefixed {patched} summary(ies) from Step N of M "
            f"for Apidog lexicographic order"
            + (f" ({skipped} without a step left unchanged)" if skipped else "")
        )
    elif skipped:
        print(
            "[*] No Step N of M found in descriptions — "
            "leaving summaries unchanged (Apidog will sort lexicographically)"
        )
    return spec
