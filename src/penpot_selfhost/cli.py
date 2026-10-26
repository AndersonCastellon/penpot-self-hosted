"""Command line entry point of the tools container (contracts/cli.md).

Exit codes: 0 success, 1 a check failed, 2 usage error or missing prerequisite,
3 "pending" (only used by `health-verdict`).

Commands here only DECIDE on facts handed in (stdin, arguments, an injected runner). The host
script bin/penpot collects those facts from the Mac's Docker (research R11).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, TextIO, Tuple

from penpot_selfhost import composecheck, envgen, healthwait, mcpurl, preflight
from penpot_selfhost.masking import MASK, mask_url

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_PENDING = 3

DEFAULT_ROOT = Path("/work")

USAGE = """Usage: python3 -m penpot_selfhost.cli <command>

Commands: init, check, explain-up-error, check-ports, health-verdict, format-status, mcp-url"""

Runner = Callable[[List[str]], Tuple[int, str, str]]


def format_error(message: str, secrets: Iterable[str] = ()) -> str:
    """Return `message` with MCP tokens in URLs and any given secret values masked."""
    masked = mask_url(message)
    for secret in secrets:
        if secret:
            masked = masked.replace(secret, MASK)
    return masked


def default_runner(argv: List[str]) -> Tuple[int, str, str]:
    """Run a command and return (exit code, stdout, stderr)."""
    done = subprocess.run(argv, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse would call sys.exit(2) and print to the real stderr
        # argparse repeats unrecognised arguments verbatim, which would leak a token passed on the command line.
        if message.startswith("unrecognized arguments"):
            message = "unrecognized arguments (values hidden)"
        raise _UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="penpot_selfhost.cli", add_help=False)
    commands = parser.add_subparsers(dest="command", parser_class=_Parser)

    init = commands.add_parser("init", add_help=False)
    init.add_argument("--volumes", default="", help="comma-separated names of existing Docker volumes")

    commands.add_parser("check", add_help=False)
    commands.add_parser("explain-up-error", add_help=False)
    commands.add_parser("check-ports", add_help=False)
    commands.add_parser("format-status", add_help=False)

    verdict = commands.add_parser("health-verdict", add_help=False)
    verdict.add_argument("--elapsed", type=int, required=True)
    verdict.add_argument("--limit", type=int, required=True)
    verdict.add_argument("--url", default="")

    # The token is read from PENPOT_MCP_TOKEN, never from argv (arguments end up in process lists and shell history).
    mcp = commands.add_parser("mcp-url", add_help=False)
    mcp.add_argument("--port", type=int, default=mcpurl.DEFAULT_PORT)
    mcp.add_argument("--reveal", action="store_true")
    return parser


def _run_init(args, root: Path, stdout: TextIO, stderr: TextIO) -> int:
    volumes = [name for name in args.volumes.split(",") if name]
    try:
        result = envgen.generate(root, volumes)
    except envgen.EnvError as error:
        print(format_error(f".env: {error}"), file=stderr)
        return EXIT_FAILED
    if result.status == "refused":
        print(format_error(result.message), file=stderr)
        return EXIT_FAILED
    print(result.message, file=stdout)
    return EXIT_OK


def _run_check(root: Path, runner: Runner, stdout: TextIO, stderr: TextIO) -> int:
    env_file = root / ".env"
    if not env_file.exists():
        print(".env not found. Run: bin/penpot init", file=stderr)
        return EXIT_USAGE

    config_command = [
        "docker", "compose",
        "--project-directory", str(root),
        "--env-file", str(env_file),
        "-f", str(root / "docker-compose.yaml"),
        "-f", str(root / "docker-compose.override.yaml"),
        "config", "--format", "json",
    ]
    code, out, err = runner(config_command)
    if code != 0:
        print(format_error(f"docker compose config failed: {err.strip() or 'no details were reported'}"), file=stderr)
        return EXIT_FAILED

    try:
        model = json.loads(out)
    except json.JSONDecodeError:
        print("docker compose config did not return valid JSON.", file=stderr)
        return EXIT_FAILED

    violations = composecheck.check(model)
    if not violations:
        print(composecheck.summary(model), file=stdout)
        return EXIT_OK

    for violation in violations:
        print(format_error(violation), file=stderr)
    if any(violation.startswith("Port ") for violation in violations):
        _, version_out, _ = runner(["docker", "compose", "version", "--short"])
        print(preflight.compose_version_hint(version_out.strip() or "unknown"), file=stderr)
    return EXIT_FAILED


def _run_health_verdict(args, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    verdict = healthwait.evaluate(healthwait.parse_ps(stdin.read()), args.elapsed, args.limit)
    if verdict.kind == "healthy":
        suffix = f" — {args.url}" if args.url else ""
        print(verdict.message + suffix, file=stdout)
        return EXIT_OK
    if verdict.kind == "pending":
        print(verdict.message, file=stdout)
        return EXIT_PENDING
    print(format_error(verdict.message), file=stderr)
    return EXIT_FAILED


def _run_mcp_url(args, env: dict, stdout: TextIO, stderr: TextIO) -> int:
    token = env.get("PENPOT_MCP_TOKEN", "")
    if not token:
        print("Set PENPOT_MCP_TOKEN to your Penpot MCP key (bin/penpot mcp-url prompts for it).", file=stderr)
        return EXIT_USAGE
    print(mcpurl.render(args.port, token, reveal=args.reveal), file=stdout)
    return EXIT_OK


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
    env: Optional[dict] = None,
    root: Optional[Path] = None,
    runner: Optional[Runner] = None,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    in_stream: TextIO = stdin if stdin is not None else sys.stdin
    out_stream: TextIO = stdout if stdout is not None else sys.stdout
    err_stream: TextIO = stderr if stderr is not None else sys.stderr
    project_root = Path(root) if root is not None else DEFAULT_ROOT
    run_command: Runner = runner if runner is not None else default_runner

    try:
        args = _build_parser().parse_args(argv)
    except _UsageError as error:
        print(f"{error}\n{USAGE}", file=err_stream)
        return EXIT_USAGE

    if args.command is None:
        print(USAGE, file=err_stream)
        return EXIT_USAGE
    if args.command == "init":
        return _run_init(args, project_root, out_stream, err_stream)
    if args.command == "check":
        return _run_check(project_root, run_command, out_stream, err_stream)
    if args.command == "explain-up-error":
        print(preflight.explain_up_error(in_stream.read()), file=err_stream)
        return EXIT_FAILED
    if args.command == "check-ports":
        message = preflight.explain_busy_ports(preflight.parse_port_listings(in_stream.read()))
        if message is None:
            return EXIT_OK
        print(message, file=err_stream)
        return EXIT_FAILED
    if args.command == "health-verdict":
        return _run_health_verdict(args, in_stream, out_stream, err_stream)
    if args.command == "mcp-url":
        return _run_mcp_url(args, env if env is not None else dict(os.environ), out_stream, err_stream)
    if args.command == "format-status":
        print(healthwait.format_status(healthwait.parse_ps(in_stream.read())), file=out_stream)
        return EXIT_OK

    print(f"Unknown command: {args.command}\n{USAGE}", file=err_stream)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
