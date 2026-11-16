"""AC-8 and section 8 state validation: every malformed state exits 3 untouched."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import assert_failure, assert_success, make_sorted_sessions, run_cli, session, write_state

MAX_STATE_BYTES = 4 * 1024 * 1024


def record(path: Path, session_id: str = "new", date: str = "2026-01-01", minutes: str = "25"):
    return run_cli("record", str(path), "--id", session_id, "--date", date, "--minutes", minutes)


def report(path: Path, week_start: str = "2026-01-01"):
    return run_cli("report", str(path), "--week-start", week_start)


def assert_corrupt(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    assert_failure(report(path), 3)
    assert path.read_bytes() == data
    assert_failure(record(path), 3)
    assert path.read_bytes() == data


def test_empty_file_is_corrupt(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b"")


def test_ac8_broken_json(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b'{"sessions": [')


def test_ac8_duplicate_id(tmp_path: Path) -> None:
    payload = {"sessions": [session("dup", "2026-01-01", 10), session("dup", "2026-01-02", 10)]}
    assert_corrupt(tmp_path / "state.json", json.dumps(payload).encode())


def test_unsorted_state_is_invalid(tmp_path: Path) -> None:
    payload = {"sessions": [session("b", "2026-01-02", 10), session("a", "2026-01-01", 10)]}
    assert_corrupt(tmp_path / "state.json", json.dumps(payload).encode())


def test_unsorted_state_same_date_is_invalid(tmp_path: Path) -> None:
    payload = {"sessions": [session("b", "2026-01-01", 10), session("a", "2026-01-01", 10)]}
    assert_corrupt(tmp_path / "state.json", json.dumps(payload).encode())


def test_extra_top_level_field_is_invalid(tmp_path: Path) -> None:
    payload = {"sessions": [], "extra": 1}
    assert_corrupt(tmp_path / "state.json", json.dumps(payload).encode())


def test_missing_sessions_key_is_invalid(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b"{}")


def test_extra_session_field_is_invalid(tmp_path: Path) -> None:
    payload = {"sessions": [{"id": "a", "date": "2026-01-01", "minutes": 10, "note": "x"}]}
    assert_corrupt(tmp_path / "state.json", json.dumps(payload).encode())


def test_top_level_array_is_invalid(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b"[]")


def test_sessions_not_an_array_is_invalid(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b'{"sessions":{}}')


@pytest.mark.parametrize("minutes", ["25.0", "true", "null", '"25"', "0", "481", "-5"])
def test_non_strict_minutes_in_state_is_invalid(minutes: str, tmp_path: Path) -> None:
    data = ('{"sessions":[{"id":"a","date":"2026-01-01","minutes":' + minutes + "}]}").encode()
    assert_corrupt(tmp_path / "state.json", data)


def test_invalid_state_date_is_invalid(tmp_path: Path) -> None:
    data = b'{"sessions":[{"id":"a","date":"2026-02-30","minutes":10}]}'
    assert_corrupt(tmp_path / "state.json", data)


def test_invalid_state_id_is_invalid(tmp_path: Path) -> None:
    data = b'{"sessions":[{"id":"bad id","date":"2026-01-01","minutes":10}]}'
    assert_corrupt(tmp_path / "state.json", data)


def test_duplicate_json_keys_are_invalid(tmp_path: Path) -> None:
    data = b'{"sessions":[],"sessions":[]}'
    assert_corrupt(tmp_path / "state.json", data)


def test_duplicate_session_keys_are_invalid(tmp_path: Path) -> None:
    data = b'{"sessions":[{"id":"a","id":"b","date":"2026-01-01","minutes":10}]}'
    assert_corrupt(tmp_path / "state.json", data)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_invalid(literal: str, tmp_path: Path) -> None:
    data = ('{"sessions":[{"id":"a","date":"2026-01-01","minutes":' + literal + "}]}").encode()
    assert_corrupt(tmp_path / "state.json", data)


def test_invalid_utf8_is_invalid(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b'{"sessions":[{"id":"\xff"}]}')


def test_bom_is_invalid(tmp_path: Path) -> None:
    assert_corrupt(tmp_path / "state.json", b'\xef\xbb\xbf{"sessions":[]}')


def test_state_over_four_mib_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    data = b'{"sessions":[]}' + b" " * (MAX_STATE_BYTES - len(b'{"sessions":[]}') + 1)
    assert len(data) == MAX_STATE_BYTES + 1
    assert_corrupt(path, data)


def test_state_of_exactly_four_mib_with_whitespace_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    base = b'{"sessions":[]}'
    data = base + b" " * (MAX_STATE_BYTES - len(base))
    assert len(data) == MAX_STATE_BYTES
    path.write_bytes(data)
    payload = assert_success(report(path))
    assert payload["sessions"] == 0


def test_state_with_more_than_10000_sessions_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    data = json.dumps({"sessions": make_sorted_sessions(10001)}).encode()
    assert_corrupt(path, data)


def test_state_with_10000_sessions_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": make_sorted_sessions(10000)})
    payload = assert_success(report(path))
    assert payload["sessions"] == 10000
    assert payload["minutes"] == 10000


def test_valid_state_with_duplicate_dates_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": [session("a", "2026-01-01", 10), session("b", "2026-01-01", 20)]})
    payload = assert_success(report(path))
    assert payload["days"][0] == {"date": "2026-01-01", "sessions": 2, "minutes": 30}


def test_argument_validation_precedes_state_reading(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b"not json at all")
    assert_failure(record(path, session_id="bad id"), 2)
    assert_failure(record(path, minutes="0"), 2)
    assert_failure(record(path, date="2026-02-30"), 2)
    assert_failure(report(path, week_start="9999-12-26"), 2)
    assert path.read_bytes() == b"not json at all"


def test_directory_as_state_is_an_io_error(tmp_path: Path) -> None:
    directory = tmp_path / "state.json"
    directory.mkdir()
    assert_failure(report(directory), 3)
    assert_failure(record(directory), 3)


def test_record_sorts_only_into_valid_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": [session("b", "2026-01-02", 10)]})
    assert assert_success(record(path, "a", "2026-01-01", "10")) == {"recorded": True}
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == {"sessions": [session("a", "2026-01-01", 10), session("b", "2026-01-02", 10)]}
