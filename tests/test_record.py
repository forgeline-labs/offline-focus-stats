"""AC-1, AC-2, AC-7, AC-12, AC-13: the record command."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import (
    assert_failure,
    assert_success,
    make_sorted_sessions,
    run_cli,
    write_state,
)


def test_ac1_record_creates_one_session_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    first = assert_success(run_record(path, "s1", "2026-01-01", "25"))
    assert first == {"recorded": True}
    second = assert_success(run_record(path, "s1", "2026-01-01", "25"))
    assert second == {"recorded": False}
    assert read_bytes(path) == b'{"sessions":[{"id":"s1","date":"2026-01-01","minutes":25}]}\n'


def test_ac2_same_id_different_minutes_exits_4_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(run_record(path, "s1", "2026-01-01", "25"))
    before = read_bytes(path)
    assert_failure(run_record(path, "s1", "2026-01-01", "50"), 4)
    assert read_bytes(path) == before


def test_ac2_same_id_different_date_exits_4(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(run_record(path, "s1", "2026-01-01", "25"))
    before = read_bytes(path)
    assert_failure(run_record(path, "s1", "2026-01-02", "25"), 4)
    assert read_bytes(path) == before


@pytest.mark.parametrize("minutes", ["1", "480", "007", "0001"])
def test_ac7_minutes_in_range_are_accepted(minutes: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert assert_success(run_record(path, "s1", "2026-01-01", minutes)) == {"recorded": True}
    report = assert_success(run_cli_report(path, "2026-01-01"))
    assert report["minutes"] == int(minutes)


@pytest.mark.parametrize(
    "minutes",
    ["0", "481", "true", "25.0", "-1", "+25", "25_0", " 25", "25 ", "", "twenty-five", "0x19"],
)
def test_ac7_invalid_minutes_exit_2(minutes: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_failure(run_record(path, "s1", "2026-01-01", minutes), 2)
    assert not path.exists()


@pytest.mark.parametrize(
    "session_id",
    ["", "a" * 33, "with space", "emoji🙂", "semi;colon", "slash/slash", "a.b", "ñ"],
)
def test_invalid_ids_exit_2(session_id: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_failure(run_record(path, session_id, "2026-01-01", "25"), 2)
    assert not path.exists()


@pytest.mark.parametrize("session_id", ["a" * 32, "A-z_0", "s1"])
def test_valid_ids_are_accepted(session_id: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert assert_success(run_record(path, session_id, "2026-01-01", "25")) == {"recorded": True}


@pytest.mark.parametrize(
    "date",
    [
        "2026-1-01",
        "2026-01-1",
        "20260101",
        "2026-13-01",
        "2026-02-30",
        "0000-01-01",
        "10000-01-01",
        "2026-00-10",
        "2026-01-01T00:00:00",
        " 2026-01-01",
        "2026-01-01 ",
    ],
)
def test_invalid_dates_exit_2(date: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_failure(run_record(path, "s1", date, "25"), 2)
    assert not path.exists()


@pytest.mark.parametrize("date", ["0001-01-01", "9999-12-31", "2024-02-29"])
def test_boundary_dates_are_valid(date: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert assert_success(run_record(path, "s1", date, "25")) == {"recorded": True}


def test_record_does_not_consult_the_clock(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    for date in ("1900-01-01", "2999-12-31"):
        assert assert_success(run_record(path, "s" + date, date, "25")) == {"recorded": True}


def test_ac12_10001st_session_exits_2_and_preserves_bytes(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    payload = {"sessions": make_sorted_sessions(10000)}
    before = write_state(path, payload)
    assert_failure(run_record(path, "new-id", "2026-01-01", "25"), 2)
    assert read_bytes(path) == before


def test_ac12_repeat_and_conflict_are_resolved_before_the_limit(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": make_sorted_sessions(10000)})
    before = read_bytes(path)
    assert assert_success(run_record(path, "s00000", "2026-01-01", "1")) == {"recorded": False}
    assert read_bytes(path) == before
    assert_failure(run_record(path, "s00000", "2026-01-01", "2"), 4)
    assert read_bytes(path) == before


def test_ac13_state_is_sorted_after_out_of_order_records(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(run_record(path, "zzz", "2026-01-05", "10"))
    assert_success(run_record(path, "aaa", "2026-01-05", "20"))
    assert_success(run_record(path, "mmm", "2026-01-01", "30"))
    assert read_bytes(path) == (
        b'{"sessions":[{"id":"mmm","date":"2026-01-01","minutes":30},'
        b'{"id":"aaa","date":"2026-01-05","minutes":20},'
        b'{"id":"zzz","date":"2026-01-05","minutes":10}]}\n'
    )


def test_record_missing_parent_exits_3(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "state.json"
    assert_failure(run_record(path, "s1", "2026-01-01", "25"), 3)
    assert not path.exists()


def test_record_then_report_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    for index in range(5):
        assert_success(run_record(path, f"s{index}", "2026-03-02", "10"))
    report = assert_success(run_cli_report(path, "2026-03-02"))
    assert report["sessions"] == 5
    assert report["minutes"] == 50


# --- helpers -------------------------------------------------------------


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def run_record(path: Path, session_id: str, date: str, minutes: str):
    return run_cli("record", str(path), "--id", session_id, "--date", date, "--minutes", minutes)


def run_cli_report(path: Path, week_start: str):
    return run_cli("report", str(path), "--week-start", week_start)
