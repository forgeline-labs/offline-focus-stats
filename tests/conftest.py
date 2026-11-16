"""Shared helpers for the offline-focus-stats black-box test suite.

Every test drives the product through its public CLI in a subprocess; no test
imports ``focus_stats`` or any other implementation module.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = REPO_ROOT / "app"


class Result:
    """A finished CLI invocation."""

    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.returncode = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr

    def json(self) -> dict:
        return json.loads(self.stdout)


def run_cli(*args: object, cwd: Path | None = None) -> Result:
    completed = subprocess.run(
        [sys.executable, str(APP), *(str(arg) for arg in args)],
        capture_output=True,
        encoding="utf-8",
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )
    return Result(completed)


@pytest.fixture(name="cli")
def cli_fixture():
    return run_cli


def assert_success(result: Result) -> dict:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return result.json()


def assert_failure(result: Result, exit_code: int) -> None:
    assert result.returncode == exit_code, result.stderr
    assert result.stdout == ""
    assert result.stderr.startswith("error:")
    body = result.stderr[len("error:") :].strip()
    assert body
    assert "\n" not in body.rstrip("\n")
    assert "Traceback" not in result.stderr


def write_state(path: Path, payload: object) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    path.write_bytes(data)
    return data


def session(session_id: str, date: str, minutes: int) -> dict:
    return {"id": session_id, "date": date, "minutes": minutes}


def make_sorted_sessions(count: int, minutes: int = 1, date: str = "2026-01-01") -> list[dict]:
    """Build ``count`` sessions: one shared date, zero-padded ids in sorted order."""
    return [session(f"s{index:05d}", date, minutes) for index in range(count)]


@pytest.fixture(name="state_file")
def state_file_fixture(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


@pytest.fixture(name="empty_state")
def empty_state_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": []})
    return path


def is_permission_enforced(tmp_path: Path) -> bool:
    """Return True when chmod actually blocks writes on this host (not root)."""
    probe = tmp_path / "probe-dir"
    probe.mkdir()
    probe.chmod(0o500)
    try:
        try:
            (probe / "touch").write_text("x", encoding="utf-8")
        except OSError:
            return True
        return False
    finally:
        probe.chmod(0o700)
        for child in probe.iterdir():
            child.unlink()
        os.rmdir(probe)
