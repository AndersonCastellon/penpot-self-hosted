"""MCP connection address and Claude Code registration command (FR-011, FR-012, FR-024)."""
from penpot_selfhost import mcpurl
from penpot_selfhost.masking import MASK

TOKEN = "abcdefgh12345678WXYZ"


def test_the_connection_url_follows_the_documented_shape():
    assert mcpurl.build_url(9001, TOKEN) == "http://127.0.0.1:9001/mcp/stream?userToken=" + TOKEN


def test_the_url_uses_the_given_port():
    assert mcpurl.build_url(9100, TOKEN).startswith("http://127.0.0.1:9100/")


def test_special_characters_in_the_token_are_percent_encoded():
    assert mcpurl.build_url(9001, "a b&c").endswith("userToken=a%20b%26c")


def test_the_registration_command_uses_user_scope_and_http_transport():
    command = mcpurl.registration_command("http://x/mcp/stream?userToken=t")

    assert command == 'claude mcp add --transport http --scope user penpot "http://x/mcp/stream?userToken=t"'


def test_the_default_output_never_contains_the_token():
    text = mcpurl.render(9001, TOKEN)

    assert TOKEN not in text
    assert "userToken=" + MASK in text
    assert "--scope user" in text


def test_a_short_token_is_fully_masked_in_the_default_output():
    text = mcpurl.render(9001, "abc")

    assert "abc" not in text.replace("abcdefgh", "")  # only the word "abc" as a token value matters
    assert "userToken=" + MASK + '"' in text


def test_reveal_prints_the_full_command_once():
    text = mcpurl.render(9001, TOKEN, reveal=True)

    assert text.count(TOKEN) == 1
    assert ('--scope user penpot "http://127.0.0.1:9001/mcp/stream?userToken=' + TOKEN + '"') in text


def test_the_output_states_the_operating_rules():
    text = mcpurl.render(9001, TOKEN).lower()

    assert "one key per user" in text
    assert "regenerating" in text and "revokes" in text
    assert "one active" in text and "tab" in text
    assert "stay open" in text


def test_the_output_tells_the_user_how_to_connect_the_plugin():
    text = mcpurl.render(9001, TOKEN)

    assert "File > MCP Server > Connect" in text
