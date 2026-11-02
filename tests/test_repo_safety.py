"""Fails if a tracked file looks like a secret or personal data. Runs on every test pass."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_PATHS = re.compile(
    r"(^|/)\.env($|\.(?!example$))|\.(pem|key|db|sqlite3?|dump|heic)$|^data/(?!\.gitkeep$)|^fixtures/demo_files/(?!\.gitkeep$)",
    re.I,
)
SECRET_PATTERNS = {
    "JWT or Supabase key": r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
    "Supabase secret key": r"sb_secret_[A-Za-z0-9_-]{10,}",
    "API key": r"\bsk-[A-Za-z0-9_-]{20,}",
    "database URL with a password": r"postgres(ql)?://[^\s:/]+:[^\s@/]+@",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "full card number": r"\b(?:\d[ -]?){15,16}\b",
}


def tracked_files():
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return result.stdout.splitlines()


def test_no_personal_or_secret_files_are_tracked():
    assert [f for f in tracked_files() if FORBIDDEN_PATHS.search(f)] == []


def test_no_secrets_in_tracked_files():
    found = []
    for name in tracked_files():
        path = ROOT / name
        if path == Path(__file__).resolve() or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        found += [f"{name}: {label}" for label, pattern in SECRET_PATTERNS.items() if re.search(pattern, text)]
    assert found == []  # names only, so a failure never prints the secret


@pytest.mark.parametrize(
    "path, blocked",
    [
        (".env", True), (".env.production", True), (".env.example", False),
        ("data/app.db", True), ("data/.gitkeep", False),
        ("fixtures/demo_files/a.pdf", True), ("fixtures/demo_files/.gitkeep", False),
        ("IMG_1.HEIC", True), ("core/parser.py", False),
    ],
)
def test_path_rule(path, blocked):
    assert bool(FORBIDDEN_PATHS.search(path)) is blocked
