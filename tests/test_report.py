"""AC-3, AC-4, AC-5, AC-6, AC-10, AC-11: the report command and week semantics."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from conftest import assert_failure, assert_success, run_cli, session, write_state


def record(path: Path, session_id: str, date: str, minutes: str):
    return run_cli("record", str(path), "--id", session_id, "--date", date, "--minutes", minutes)


def report(path: Path, week_start: str):
    return run_cli("report", str(path), "--week-start", week_start)


def all_dates(start: str) -> list[str]:
    first = datetime.date.fromisoformat(start)
    return [(first + datetime.timedelta(days=offset)).isoformat() for offset in range(7)]


def test_ac3_two_sessions_on_one_day(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(record(path, "s1", "2026-01-01", "25"))
    assert_success(record(path, "s2", "2026-01-01", "50"))
    payload = assert_success(report(path, "2026-01-01"))
    assert payload["days"][0] == {"date": "2026-01-01", "sessions": 2, "minutes": 75}
    assert payload["sessions"] == 2
    assert payload["minutes"] == 75


def test_ac4_report_always_has_seven_days_with_zeros(empty_state: Path) -> None:
    payload = assert_success(report(empty_state, "2026-01-01"))
    assert payload["start"] == "2026-01-01"
    assert [day["date"] for day in payload["days"]] == all_dates("2026-01-01")
    assert payload["days"] == [{"date": day, "sessions": 0, "minutes": 0} for day in all_dates("2026-01-01")]
    assert payload["sessions"] == 0
    assert payload["minutes"] == 0


def test_report_output_shape_and_order(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(record(path, "s1", "2026-01-03", "30"))
    result = report(path, "2026-01-01")
    assert result.returncode == 0
    assert result.stdout.startswith('{"start":"2026-01-01","days":[')
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    payload = result.json()
    assert list(payload) == ["start", "days", "sessions", "minutes"]
    assert payload["days"][2] == {"date": "2026-01-03", "sessions": 1, "minutes": 30}
    assert payload["sessions"] == 1
    assert payload["minutes"] == 30


def test_ac5_window_is_inclusive_start_and_exclusive_start_plus_seven(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(record(path, "first", "2026-01-01", "10"))
    assert_success(record(path, "last", "2026-01-07", "20"))
    assert_success(record(path, "after", "2026-01-08", "40"))
    assert_success(record(path, "before", "2025-12-31", "80"))
    payload = assert_success(report(path, "2026-01-01"))
    counts = {day["date"]: day for day in payload["days"]}
    assert counts["2026-01-01"]["minutes"] == 10
    assert counts["2026-01-07"]["minutes"] == 20
    assert "2026-01-08" not in counts
    assert "2025-12-31" not in counts
    assert payload["sessions"] == 2
    assert payload["minutes"] == 30


def test_ac6_leap_year_february(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(record(path, "leap", "2024-02-29", "45"))
    payload = assert_success(report(path, "2024-02-26"))
    assert [day["date"] for day in payload["days"]] == [
        "2024-02-26",
        "2024-02-27",
        "2024-02-28",
        "2024-02-29",
        "2024-03-01",
        "2024-03-02",
        "2024-03-03",
    ]
    assert payload["days"][3] == {"date": "2024-02-29", "sessions": 1, "minutes": 45}
    assert payload["minutes"] == 45


def test_ac6_non_leap_year_excludes_february_29(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(record(path, "x", "2023-03-05", "5"))
    assert_success(record(path, "y", "2023-02-28", "7"))
    payload = assert_success(report(path, "2023-02-26"))
    assert [day["date"] for day in payload["days"]] == [
        "2023-02-26",
        "2023-02-27",
        "2023-02-28",
        "2023-03-01",
        "2023-03-02",
        "2023-03-03",
        "2023-03-04",
    ]
    assert payload["days"][2] == {"date": "2023-02-28", "sessions": 1, "minutes": 7}
    assert payload["sessions"] == 1
    assert payload["minutes"] == 7


def test_week_start_need_not_be_monday(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_success(record(path, "s1", "2026-01-04", "15"))
    payload = assert_success(report(path, "2026-01-04"))
    assert payload["days"][0] == {"date": "2026-01-04", "sessions": 1, "minutes": 15}
    assert payload["minutes"] == 15


def test_ac10_report_does_not_create_or_modify_file(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    assert_failure(report(missing, "2026-01-01"), 3)
    assert not missing.exists()

    existing = tmp_path / "state.json"
    before = write_state(existing, {"sessions": [session("s1", "2026-01-01", 25)]})
    assert_success(report(existing, "2026-01-01"))
    assert existing.read_bytes() == before


def test_ac10_report_on_empty_valid_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": []})
    assert_success(report(path, "2026-01-01"))


@pytest.mark.parametrize(
    "start",
    ["0000-01-01", "2026-02-30", "2026-1-01", "9999-12-32", "20260101", "2026-13-01"],
)
def test_invalid_week_start_exits_2(start: str, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert_failure(report(path, start), 2)


def test_ac11_week_start_limits(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": []})
    payload = assert_success(report(path, "9999-12-25"))
    assert [day["date"] for day in payload["days"]] == [
        "9999-12-25",
        "9999-12-26",
        "9999-12-27",
        "9999-12-28",
        "9999-12-29",
        "9999-12-30",
        "9999-12-31",
    ]
    assert_failure(report(path, "9999-12-26"), 2)


def test_report_totals_are_exact_integers(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": [session(f"s{i:04d}", "2026-01-01", 480) for i in range(0, 40)]})
    payload = assert_success(report(path, "2026-01-01"))
    assert payload["minutes"] == 480 * 40
    assert isinstance(payload["minutes"], int)
    assert payload["sessions"] == 40
    for day in payload["days"]:
        assert isinstance(day["minutes"], int)
        assert isinstance(day["sessions"], int)


def test_report_does_not_wait_or_spawn(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, {"sessions": [session("s1", "2026-01-01", 25)]})
    first = assert_success(report(path, "2026-01-01"))
    second = assert_success(report(path, "2026-01-01"))
    assert first == second
