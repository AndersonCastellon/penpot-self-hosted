"""CLI conventions: exit codes, stderr, and no secrets in messages (contracts/cli.md)."""
import io

from penpot_selfhost import cli


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_exit_code_constants_follow_the_contract():
    assert cli.EXIT_OK == 0
    assert cli.EXIT_FAILED == 1
    assert cli.EXIT_USAGE == 2
    assert cli.EXIT_PENDING == 3


def test_no_command_is_a_usage_error_printed_to_stderr():
    code, out, err = run([])

    assert code == cli.EXIT_USAGE
    assert out == ""
    assert "Usage" in err


def test_unknown_command_is_a_usage_error_printed_to_stderr():
    code, out, err = run(["bogus"])

    assert code == cli.EXIT_USAGE
    assert out == ""
    assert "bogus" in err


def test_format_error_masks_tokens_inside_urls():
    message = cli.format_error("request to http://h/mcp/stream?userToken=abcdefgh12345678 failed")

    assert "abcdefgh12345678" not in message
    assert "userToken=****" in message


def test_format_error_masks_explicit_secret_values():
    message = cli.format_error("password hunter2hunter2hunter2 rejected", secrets=["hunter2hunter2hunter2"])

    assert "hunter2hunter2hunter2" not in message
    assert "****" in message


def test_format_error_ignores_empty_secret_values():
    assert cli.format_error("plain message", secrets=[""]) == "plain message"
