#!/usr/bin/env python3
"""Post digest messages to Discord. Runs in GitHub Actions only.

Usage:
    MIR_DISCORD_WEBHOOK=<url> python scripts/notify_discord.py digests/2026-07-05.json

Reads `discord_messages` from the digest JSON and posts each one in order.
Never prints the webhook URL. Exits non-zero if any message fails after retry.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MAX_LEN = 1990
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) mir-digest-ci/2.0"


def post(webhook: str, content: str) -> tuple[int, str]:
    body = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        return 0, f"{type(e).__name__}: {e}"


def clamp(s: str) -> str:
    s = (s or "").strip()
    return s if len(s) <= MAX_LEN else s[: MAX_LEN - 1].rstrip() + "…"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: notify_discord.py <digest.json>", file=sys.stderr)
        return 2
    webhook = (os.environ.get("MIR_DISCORD_WEBHOOK") or "").strip()
    if not webhook:
        print("ERROR: MIR_DISCORD_WEBHOOK is not set (repo secret missing?)", file=sys.stderr)
        return 2
    digest_path = Path(sys.argv[1])
    if not digest_path.exists():
        print(f"ERROR: digest not found: {digest_path}", file=sys.stderr)
        return 2
    data = json.loads(digest_path.read_text(encoding="utf-8-sig"))
    messages = data.get("discord_messages") or []
    if not messages:
        print("ERROR: digest has no discord_messages", file=sys.stderr)
        return 2
    for idx, msg in enumerate(messages, 1):
        content = clamp(str(msg))
        status, resp = post(webhook, content)
        if not (200 <= status < 300):
            time.sleep(3.0)
            status2, resp2 = post(webhook, content)
            if not (200 <= status2 < 300):
                print(
                    f"ERROR: Discord part {idx} failed (HTTP {status} then {status2}).\n"
                    f"first: {resp[:300]}\nsecond: {resp2[:300]}",
                    file=sys.stderr,
                )
                return 3
        time.sleep(1.5)  # be gentle with webhook rate limits
    print(f"OK: sent {len(messages)} Discord message(s) for {data.get('date', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
