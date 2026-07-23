"""Email pipeline documentation (step 7).

Sends data/<Module>.readme.md (and optional .intro.md) to REPORT_EMAIL_TO
via SMTP settings in .env. Uses the stdlib only (smtplib + email).

Usage:
  python src/send_email.py --module ContosoPizza
  python src/send_email.py --module ContosoPizza --dry-run
"""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

import config

DATA_DIR = config.DATA_DIR


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def resolve_doc_files(module: str) -> list[Path]:
    files: list[Path] = []
    for suffix in (".readme.md", ".intro.md"):
        path = DATA_DIR / f"{module}{suffix}"
        if path.is_file() and path.stat().st_size > 0:
            files.append(path)
    return files


def build_message(
    *,
    module: str,
    to_addrs: list[str],
    from_addr: str,
    files: list[Path],
) -> EmailMessage:
    readme = next((p for p in files if p.name.endswith(".readme.md")), None)
    body = (
        readme.read_text(encoding="utf-8")
        if readme is not None
        else f"Documentation report for module '{module}'. See attachments."
    )

    msg = EmailMessage()
    msg["Subject"] = f"[Apidog pipeline] {module} documentation"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)

    for path in files:
        data = path.read_bytes()
        msg.add_attachment(
            data,
            maintype="text",
            subtype="markdown",
            filename=path.name,
        )
    return msg


def send_report(
    *,
    module: str,
    dry_run: bool = False,
) -> int:
    to_raw = _env("REPORT_EMAIL_TO") or _env("EMAIL_TO")
    to_addrs = [a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip()] if to_raw else []

    smtp_host = _env("SMTP_HOST")
    smtp_port = int(_env("SMTP_PORT", "587") or "587")
    smtp_user = _env("SMTP_USER")
    smtp_password = _env("SMTP_PASSWORD")
    from_addr = _env("SMTP_FROM") or smtp_user or (to_addrs[0] if to_addrs else "pipeline@localhost")
    use_tls = (_env("SMTP_USE_TLS", "true") or "true").lower() in {
        "1", "true", "yes", "on",
    }
    use_ssl = (_env("SMTP_USE_SSL", "false") or "false").lower() in {
        "1", "true", "yes", "on",
    }

    files = resolve_doc_files(module)
    if not files:
        print(
            f"[!] No docs to email for '{module}'. Expected:\n"
            f"      {DATA_DIR / f'{module}.readme.md'}\n"
            f"      {DATA_DIR / f'{module}.intro.md'}"
        )
        return 1

    print(f"[*] Module:  {module}")
    print(f"[*] To:      {', '.join(to_addrs) if to_addrs else '(not set)'}")
    print(f"[*] From:    {from_addr}")
    print(f"[*] Attach:  {', '.join(p.name for p in files)}")

    if not to_addrs:
        print("[!] Set REPORT_EMAIL_TO in .env (recipient address).")
        if not dry_run:
            return 1

    msg = build_message(
        module=module,
        to_addrs=to_addrs or ["unset@example.com"],
        from_addr=from_addr,
        files=files,
    )

    if dry_run:
        print("[*] Dry run - message built, not sent.")
        return 0

    if not smtp_host:
        print("[!] Set SMTP_HOST in .env.")
        return 1

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=60) as smtp:
                if smtp_user:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as smtp:
                smtp.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if smtp_user:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        print(f"[!] SMTP send failed: {e}")
        return 1

    print(f"[+] Sent documentation email for {module} to {', '.join(to_addrs)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Email data/<Module>.readme.md (+ .intro.md) using SMTP settings from .env."
        )
    )
    parser.add_argument(
        "--module",
        default=config.OPENAPI_MODULE_NAME or None,
        required=not bool(config.OPENAPI_MODULE_NAME),
        help="Module name -> data/<Module>.readme.md / .intro.md",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the message and validate files without sending",
    )
    args = parser.parse_args()
    if not args.module:
        print("[!] Provide --module or OPENAPI_MODULE_NAME.")
        return 1
    return send_report(module=args.module, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
