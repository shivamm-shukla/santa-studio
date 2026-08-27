"""Who is allowed to use the output commercially, and how that is checked.

Santa Studio is source-available, not open source: anyone may run it and make
videos with it, but putting those videos on a channel you monetise needs a
commercial grant, and a merged pull request is what earns one. See LICENSE.

Videos carry a corner mark saying what made them. A valid grant turns it off.

What this can and cannot do, stated plainly because the alternative is
pretending:

* It **can** stop anyone issuing themselves a grant. A grant is an Ed25519
  signature over the holder's name, and only the holder of the private
  signing key can produce one. Forging is not a thing that happens.
* It **cannot** stop anyone deleting the check. This code runs on their
  machine from source they can read. Any `if` can be removed, and no amount
  of cleverness here changes that - it is the same reason DRM does not
  survive contact with an open codebase.

So this is not a lock. It makes the honest path the easy one, and makes the
other path a deliberate act against the licence rather than an accident. What
stands behind it is LICENSE and the trademark on the name, not this file.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

# The public half of the project's signing key. The private half is not in
# this repository and never will be.
SIGNING_KEY = "d5a917f7b158c13f595612c7446256a9b21adf8370031d115157fe8399b380de"

ENV_VAR = "SANTA_STUDIO_LICENCE"
FILENAME = "licence.json"


@dataclass(frozen=True)
class Grant:
    """A commercial grant, once it has been checked."""

    holder: str = ""
    reason: str = ""
    issued: str = ""
    valid: bool = False
    problem: str = ""

    @property
    def watermark(self) -> bool:
        """Whether output still carries the mark."""
        return not self.valid


def _search_paths() -> list[str]:
    """Where a grant file might be, nearest first."""
    found = []
    from_env = os.getenv(ENV_VAR, "").strip()
    if from_env and os.path.exists(from_env):
        found.append(from_env)
    try:
        import paths

        found.append(str(paths.config_dir() / FILENAME))
    except Exception:
        pass
    found.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), FILENAME))
    return found


def _token() -> str:
    """The grant token as text, from the environment or a file."""
    raw = os.getenv(ENV_VAR, "").strip()
    # The variable holds either the token itself or a path to it.
    if raw and not os.path.exists(raw):
        return raw

    for path in _search_paths():
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            continue
    return ""


def _verify(token: str) -> Grant:
    """Checks one token against the project's public key."""
    if not token:
        return Grant(problem="No commercial grant found.")

    try:
        payload = json.loads(token)
        body = payload["grant"]
        signature = base64.b64decode(payload["signature"])
    except Exception:
        return Grant(problem="That grant file is not readable.")

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        # Without the library the signature cannot be checked, and an
        # unchecked grant is not a grant.
        return Grant(problem="cryptography is not installed, so a grant cannot be checked.")

    key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(SIGNING_KEY))
    # Signed over the canonical form, so reformatting the file does not break
    # a genuine grant and reordering it does not smuggle anything past.
    message = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

    try:
        key.verify(signature, message)
    except InvalidSignature:
        return Grant(problem="That grant was not issued for this project.")
    except Exception as e:
        return Grant(problem=f"That grant could not be checked: {e}")

    return Grant(
        holder=str(body.get("holder") or "unnamed"),
        reason=str(body.get("reason") or ""),
        issued=str(body.get("issued") or ""),
        valid=True,
    )


def status() -> Grant:
    """The grant this machine holds, checked."""
    return _verify(_token())


def marks_output() -> bool:
    """Whether a video rendered now carries the corner mark."""
    return status().watermark
