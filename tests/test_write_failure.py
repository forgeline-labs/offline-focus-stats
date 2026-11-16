"""AC-9: write/replace failure is reported as exit 3 with the original intact.

The failure is simulated externally with a POSIX directory that denies writes;
no implementation detail or internal function name is involved.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import assert_failure, assert_success, is_permission_enforced, run_cli, session, write_state


def test_ac9_unwritable_directory_exits_3_without_mutation(tmp_path: Path) -> None:
    if not is_permission_enforced(tmp_path):
        pytest.skip("host does not enforce directory permissions (privileged user)")

    directory = tmp_path / "readonly"
    directory.mkdir()
    path = directory / "state.json"
    original = write_state(path, {"sessions": [session("s1", "2026-01-01", 25)]})

    directory.chmod(0o500)
    try:
        result = run_cli("record", str(path), "--id", "s2", "--date", "2026-01-02", "--minutes", "30")
        assert_failure(result, 3)
        assert path.read_bytes() == original
        assert sorted(entry.name for entry in directory.iterdir()) == ["state.json"]
    finally:
        directory.chmod(0o700)


def test_ac9_failed_write_leaves_no_temporary_file(tmp_path: Path) -> None:
    if not is_permission_enforced(tmp_path):
        pytest.skip("host does not enforce directory permissions (privileged user)")

    directory = tmp_path / "readonly"
    directory.mkdir()
    path = directory / "state.json"
    original = write_state(path, {"sessions": []})
    directory.chmod(0o500)
    try:
        assert_failure(run_cli("record", str(path), "--id", "s1", "--date", "2026-01-01", "--minutes", "25"), 3)
        assert path.read_bytes() == original
        assert list(directory.iterdir()) == [path]
    finally:
        directory.chmod(0o700)


def test_ac9_missing_parent_directory_exits_3(tmp_path: Path) -> None:
    path = tmp_path / "no-such-parent" / "state.json"
    assert_failure(run_cli("record", str(path), "--id", "s1", "--date", "2026-01-01", "--minutes", "25"), 3)
    assert not path.parent.exists()


def test_successful_write_leaves_only_the_state_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(run_cli("record", str(path), "--id", "s1", "--date", "2026-01-01", "--minutes", "25"))
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["state.json"]


def test_state_file_is_utf8_without_bom(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(run_cli("record", str(path), "--id", "s1", "--date", "2026-01-01", "--minutes", "25"))
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1
    assert b"\r\n" not in data
    assert os.name == "posix"
