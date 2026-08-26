#!/usr/bin/env python3
"""Create/list Resend sending domain and optionally send a test email.

Usage:
  RESEND_API_KEY=re_... python3 scripts/configure_resend.py
  python3 scripts/configure_resend.py --api-key re_... --test-to you@example.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)

DOMAIN = "optcgassistant.com"
API = "https://api.resend.com"


def _req(method: str, path: str, api_key: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "OPCG-Assistant/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise SystemExit(f"Resend {method} {path} HTTP {exc.code}: {detail}") from exc


def main() -> int:
    p = argparse.ArgumentParser(description="Configure Resend domain for OPCG")
    p.add_argument("--api-key", default="", help="Resend API key (else RESEND_API_KEY)")
    p.add_argument("--domain", default=DOMAIN)
    p.add_argument("--test-to", default="", help="Send a test email to this address")
    p.add_argument("--verify", action="store_true", help="Trigger domain verification after listing")
    args = p.parse_args()
    api_key = str(args.api_key or os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key:
        print(
            "Missing API key. Create one at https://resend.com/api-keys then:\n"
            "  python3 scripts/configure_resend.py --api-key re_... --test-to you@example.com",
            file=sys.stderr,
        )
        return 2

    listing = _req("GET", "/domains", api_key)
    domains = listing.get("data") if isinstance(listing, dict) else listing
    if not isinstance(domains, list):
        domains = []
    existing = next((d for d in domains if str(d.get("name") or "") == args.domain), None)
    if existing:
        domain_id = str(existing.get("id") or "")
        print(f"domain already in Resend: {args.domain} id={domain_id} status={existing.get('status')}")
        detail = _req("GET", f"/domains/{domain_id}", api_key) if domain_id else existing
    else:
        print(f"creating domain {args.domain} …")
        detail = _req("POST", "/domains", api_key, {"name": args.domain, "region": "us-east-1"})
        domain_id = str(detail.get("id") or "")
        print(f"created id={domain_id} status={detail.get('status')}")

    records = detail.get("records") or []
    print("\nAdd these DNS records in Cloudflare (DNS only, not proxied):\n")
    for rec in records:
        name = rec.get("name") or ""
        rtype = rec.get("type") or ""
        value = rec.get("value") or ""
        prio = rec.get("priority")
        extra = f" (priority {prio})" if prio is not None else ""
        print(f"  {rtype:6} {name:50} {value}{extra}")

    if args.verify and domain_id:
        _req("POST", f"/domains/{domain_id}/verify", api_key, {})
        print("\nTriggered verification. Re-run this script in a few minutes to check status.")

    if args.test_to:
        os.environ["RESEND_API_KEY"] = api_key
        os.environ.setdefault("RESEND_FROM", "OPCG Assistant <noreply@optcgassistant.com>")
        from email_util import send_email

        send_email(args.test_to, "OPCG Resend test", "If you received this, Resend is working.", log_prefix="resend-test")
        print(f"\nTest email requested → {args.test_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
