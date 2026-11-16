"""AC-14 and the observable CLI conventions of spec section 2."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import APP, REPO_ROOT, assert_failure, assert_success, run_cli

EXPECTED_VERSION = "offline-focus-stats 0.1.0\n"


def test_ac14_version_is_exact_and_needs_no_state(tmp_path: Path) -> None:
    result = run_cli("--version", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == EXPECTED_VERSION
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_ac14_help_needs_no_state(tmp_path: Path) -> None:
    result = run_cli("--help", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "token",
    [
        "usage:",
        "app",
        "--help",
        "--version",
        "record",
        "report",
        "FILE",
        "--id",
        "--date",
        "--minutes",
        "--week-start",
        "YYYY-MM-DD",
    ],
)
def test_help_lists_every_documented_token(token: str) -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert token in result.stdout


def test_help_and_version_do_not_touch_state_file(tmp_path: Path) -> None:
    marker = tmp_path / "should-not-exist.json"
    for flag in ("--help", "--version"):
        result = run_cli(flag, cwd=tmp_path)
        assert result.returncode == 0
        assert result.stderr == ""
        assert not marker.exists()
    assert list(tmp_path.iterdir()) == []


def test_version_output_is_lf_terminated_on_one_line() -> None:
    result = run_cli("--version")
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("bogus",),
        ("record",),
        ("report",),
        ("record", "state.json"),
        ("record", "state.json", "--id", "s1", "--date", "2026-01-01"),
        ("record", "state.json", "--id", "s1", "--minutes", "25"),
        ("record", "state.json", "--date", "2026-01-01", "--minutes", "25"),
        ("report", "state.json"),
        ("record", "state.json", "--id", "s1", "--date", "2026-01-01", "--minutes", "25", "--extra"),
        ("record", "state.json", "other.json", "--id", "s1", "--date", "2026-01-01", "--minutes", "25"),
        ("report", "state.json", "--week-start", "2026-01-01", "--id", "s1"),
        ("record", "state.json", "--id", "s1", "--id", "s2", "--date", "2026-01-01", "--minutes", "25"),
    ],
)
def test_unknown_or_missing_arguments_exit_2(args, tmp_path: Path) -> None:
    result = run_cli(*args, cwd=tmp_path)
    assert_failure(result, 2)
    assert list(tmp_path.iterdir()) == []


def test_options_may_precede_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    result = run_cli("record", "--minutes", "25", "--date", "2026-01-01", "--id", "s1", str(path))
    payload = assert_success(result)
    assert payload == {"recorded": True}
    assert path.exists()


def test_success_stdout_is_single_json_line() -> None:
    result = run_cli("--version")
    assert result.stdout == EXPECTED_VERSION


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable contract")
def test_executable_app_matches_python_app() -> None:
    assert os.access(APP, os.X_OK)
    direct = subprocess.run([str(APP), "--version"], capture_output=True, encoding="utf-8", check=False)
    interpreted = subprocess.run(
        [sys.executable, str(APP), "--version"], capture_output=True, encoding="utf-8", check=False
    )
    assert direct.returncode == interpreted.returncode == 0
    assert direct.stdout == interpreted.stdout == EXPECTED_VERSION
    assert direct.stderr == interpreted.stderr == ""


def test_unicode_and_spaces_in_path(tmp_path: Path) -> None:
    directory = tmp_path / "cartella con spazi"
    directory.mkdir()
    path = directory / "stato ünïcode.json"
    assert_success(run_cli("record", str(path), "--id", "s1", "--date", "2026-01-01", "--minutes", "25"))
    report = assert_success(run_cli("report", str(path), "--week-start", "2026-01-01"))
    assert report["sessions"] == 1


def test_relative_path_from_other_cwd(tmp_path: Path) -> None:
    result = run_cli("record", "rel.json", "--id", "s1", "--date", "2026-01-01", "--minutes", "25", cwd=tmp_path)
    assert_success(result)
    assert (tmp_path / "rel.json").exists()
    assert REPO_ROOT.is_dir()
