"""Mask secrets and MCP tokens so they never appear in output (FR-011, SC-008)."""
import re

MASK = "****"

_TOKEN_PARAM = re.compile(r"(userToken=)([^&#\s\"']*)")


def mask_token(token: str) -> str:
    """Return a safe-to-print version of a secret token.

    Rules (see tests/unit/test_masking.py):
    - an empty token stays empty;
    - a token shorter than 8 characters is fully masked (returns MASK only);
    - a longer token is MASK followed by a suffix of the token that is at most
      4 characters and at most a quarter of the token's length.
    """
    if not token:
        return ""
    if len(token) < 8:
        return MASK
    revealed = min(4, len(token) // 4)
    return MASK + token[-revealed:]


def mask_url(url: str) -> str:
    """Mask the value of every `userToken=` query parameter in a URL or text."""
    return _TOKEN_PARAM.sub(lambda m: m.group(1) + mask_token(m.group(2)), url)
