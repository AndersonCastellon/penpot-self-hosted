"""Masking of secrets and MCP tokens (FR-011, SC-008, data-model: McpKey)."""
import pytest

from penpot_selfhost.masking import MASK, mask_token, mask_url


@pytest.mark.parametrize("token", ["a", "abcd", "1234567"])
def test_tokens_shorter_than_eight_characters_are_fully_masked(token):
    assert mask_token(token) == MASK


@pytest.mark.parametrize("length", [8, 12, 16, 24, 64])
def test_longer_tokens_never_reveal_more_than_a_quarter_or_four_characters(length):
    token = "".join(chr(ord("a") + (i * 7) % 26) for i in range(length))
    masked = mask_token(token)

    assert masked.startswith(MASK)
    revealed = masked[len(MASK):]
    assert token.endswith(revealed)
    assert len(revealed) <= 4
    assert len(revealed) <= length // 4
    assert token not in masked


def test_an_empty_token_stays_empty():
    assert mask_token("") == ""


def test_mask_url_masks_only_the_token_value():
    url = "http://127.0.0.1:9001/mcp/stream?userToken=abcdefgh12345678&other=1"

    masked = mask_url(url)

    assert "abcdefgh12345678" not in masked
    assert masked.startswith("http://127.0.0.1:9001/mcp/stream?userToken=" + MASK)
    assert masked.endswith("&other=1")


def test_mask_url_without_a_token_is_unchanged():
    url = "http://127.0.0.1:9001/mcp/stream"

    assert mask_url(url) == url


def test_mask_url_with_a_short_token_is_fully_masked():
    assert mask_url("http://h/mcp/stream?userToken=abc") == "http://h/mcp/stream?userToken=" + MASK
