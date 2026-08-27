#!/usr/bin/env python3
"""Issues a commercial grant. For the project owner only.

A grant is a small JSON object signed with the project's private key. The
holder drops it into their Santa Studio config directory and their output
stops carrying the corner mark. Anyone can read this script; nobody without
the private key can produce a grant with it.

    python tools/issue_grant.py "Ada Lovelace" --reason "PR #14"

The key is not in this repository and must never be. Keep it somewhere you
would keep an SSH key, and if it ever leaks, generate a new one, publish the
new public key in licence.py, and every grant issued under the old one stops
working - which is the point.
"""

import argparse
import base64
import json
import os
import sys
from datetime import date

DEFAULT_KEY = os.path.expanduser("~/.santa-studio-keys/licence-signing-key.pem")


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a Santa Studio commercial grant.")
    parser.add_argument("holder", help="who the grant is for - a name or a GitHub handle")
    parser.add_argument("--reason", default="", help="why, e.g. 'PR #14 merged'")
    parser.add_argument("--key", default=DEFAULT_KEY, help="path to the private signing key")
    parser.add_argument("--out", default="", help="where to write it (default: stdout)")
    args = parser.parse_args()

    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        print("pip install cryptography", file=sys.stderr)
        return 1

    try:
        with open(args.key, "rb") as handle:
            key = serialization.load_pem_private_key(handle.read(), password=None)
    except OSError as e:
        print(f"Could not read the signing key: {e}", file=sys.stderr)
        return 1

    body = {
        "holder": args.holder,
        "reason": args.reason,
        "issued": date.today().isoformat(),
    }
    # Signed over the canonical form, so the file can be reformatted without
    # breaking and cannot be reordered to smuggle anything past the check.
    message = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    grant = {
        "grant": body,
        "signature": base64.b64encode(key.sign(message)).decode("ascii"),
    }
    text = json.dumps(grant, indent=2) + "\n"

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"Written to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
