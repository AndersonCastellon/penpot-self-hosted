"""Guard for FR-021: code, comments, test names and configuration are written in English.

Heuristic: no Spanish-specific characters outside docs/ and specs/. The character class is built from numeric
code points so this file does not flag itself.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# a e i o u with an acute accent, n with a tilde, and the inverted question and exclamation marks (and capitals).
SPANISH = re.compile("[" + "".join(chr(code) for code in (0xE1, 0xE9, 0xED, 0xF3, 0xFA, 0xF1, 0xBF, 0xA1, 0xC1, 0xC9, 0xCD, 0xD3, 0xDA, 0xD1)) + "]")

SCANNED = ("src", "tests", "bin", "tools", "docker-compose.override.yaml", ".env.example", "README.md", ".gitignore")
SUFFIXES = {".py", ".yaml", ".yml", ".md", ".txt", ""}


def candidate_files():
    for entry in SCANNED:
        path = ROOT / entry
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix in SUFFIXES and "__pycache__" not in child.parts:
                    yield child


def test_no_spanish_characters_in_code_tests_or_configuration():
    offenders = []
    for path in candidate_files():
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
            if SPANISH.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")

    assert offenders == [], "Spanish characters found (FR-021 requires English): " + ", ".join(offenders)
