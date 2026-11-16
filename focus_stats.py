"""offline-focus-stats — deterministic focus-session recording and weekly report.

The tool has no clock, no network and no runtime dependencies. Every command is
a pure function of its arguments and of the JSON state file it is pointed at.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import sys
import tempfile
from typing import Any

PROGRAM = "offline-focus-stats"
VERSION = "0.1.0"

MAX_SESSIONS = 10000
MAX_STATE_BYTES = 4 * 1024 * 1024
MIN_MINUTES = 1
MAX_MINUTES = 480
MIN_ID_LENGTH = 1
MAX_ID_LENGTH = 32

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_IO = 3
EXIT_CONFLICT = 4

WEEK_DAYS = 7

_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,32}", re.ASCII)
_DATE_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", re.ASCII)
_INT_RE = re.compile(r"[0-9]+", re.ASCII)

HELP_TEXT = """\
usage: app <command> [options]

offline-focus-stats 0.1.0 - deterministic focus-session recording and weekly report.

Commands:
  record FILE --id ID --date YYYY-MM-DD --minutes N
        Record one focus session in FILE. Creates FILE when missing.
  report FILE --week-start YYYY-MM-DD
        Print the seven-day totals for the week beginning at --week-start.

Options:
  --id ID                  session identifier: ASCII [A-Za-z0-9_-]{1,32}
  --date YYYY-MM-DD        session date: strict Gregorian 0001-01-01..9999-12-31
  --minutes N              focus minutes: integer 1..480
  --week-start YYYY-MM-DD  first day of the inclusive seven-day window
                           (at most 9999-12-25)
  --help                   show this help and exit
  --version                show the version and exit

FILE is a UTF-8 JSON state file holding at most 10000 sessions, sorted by
(date, id) and no larger than 4 MiB. Exit codes: 0 success, 2 validation,
3 I/O or corrupt state, 4 conflicting session id.
"""


class CliError(Exception):
    """A failure that maps onto one of the documented exit codes."""

    exit_code = EXIT_USAGE

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(CliError):
    """Invalid argument or schema: exit 2."""

    exit_code = EXIT_USAGE


class StateError(CliError):
    """I/O failure or corrupt state: exit 3."""

    exit_code = EXIT_IO


class ConflictError(CliError):
    """Existing session id with different content: exit 4."""

    exit_code = EXIT_CONFLICT


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def parse_id(text: str) -> str:
    if not _ID_RE.fullmatch(text):
        raise UsageError("invalid --id: expected 1..32 ASCII characters from [A-Za-z0-9_-]")
    return text


def parse_date(text: str, label: str = "--date") -> datetime.date:
    match = _DATE_RE.fullmatch(text)
    if match is None:
        raise UsageError(f"invalid {label}: expected YYYY-MM-DD")
    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError:
        raise UsageError(f"invalid {label}: not a Gregorian calendar date") from None


def parse_minutes(text: str) -> int:
    if _INT_RE.fullmatch(text) is None:
        raise UsageError("invalid --minutes: expected an integer without sign, decimal point or spaces")
    value = int(text)
    if not MIN_MINUTES <= value <= MAX_MINUTES:
        raise UsageError(f"invalid --minutes: expected {MIN_MINUTES}..{MAX_MINUTES}")
    return value


def _decode_json(text: str) -> Any:
    def reject_constant(token: str) -> Any:
        raise ValueError(f"non-finite number {token}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (ValueError, RecursionError) as exc:
        raise StateError(f"corrupt state file: {exc}") from None


def _validate_sessions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or set(raw) != {"sessions"}:
        raise StateError("corrupt state file: top level must be an object with only 'sessions'")
    sessions = raw["sessions"]
    if not isinstance(sessions, list):
        raise StateError("corrupt state file: 'sessions' must be an array")
    if len(sessions) > MAX_SESSIONS:
        raise StateError(f"corrupt state file: more than {MAX_SESSIONS} sessions")

    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in sessions:
        if not isinstance(item, dict) or set(item) != {"id", "date", "minutes"}:
            raise StateError("corrupt state file: each session must have exactly id, date and minutes")
        session_id = item["id"]
        if not isinstance(session_id, str) or _ID_RE.fullmatch(session_id) is None:
            raise StateError("corrupt state file: invalid session id")
        session_date = item["date"]
        if not isinstance(session_date, str) or _DATE_RE.fullmatch(session_date) is None:
            raise StateError("corrupt state file: invalid session date")
        try:
            datetime.date(*(int(part) for part in _DATE_RE.fullmatch(session_date).groups()))
        except ValueError:
            raise StateError("corrupt state file: invalid session date") from None
        minutes = item["minutes"]
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise StateError("corrupt state file: session minutes must be an integer")
        if not MIN_MINUTES <= minutes <= MAX_MINUTES:
            raise StateError("corrupt state file: session minutes out of range")
        if session_id in seen_ids:
            raise StateError(f"corrupt state file: duplicate session id {session_id!r}")
        seen_ids.add(session_id)
        validated.append({"id": session_id, "date": session_date, "minutes": minutes})

    keys = [(session["date"], session["id"]) for session in validated]
    if keys != sorted(keys):
        raise StateError("corrupt state file: sessions are not sorted by (date, id)")
    return validated


def load_state(path: str, *, allow_missing: bool) -> list[dict[str, Any]]:
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_STATE_BYTES + 1)
    except FileNotFoundError:
        if allow_missing:
            return []
        raise StateError(f"cannot read state file: {path} does not exist") from None
    except OSError as exc:
        raise StateError(f"cannot read state file: {exc}") from None

    if len(data) > MAX_STATE_BYTES:
        raise StateError(f"corrupt state file: larger than {MAX_STATE_BYTES} bytes")
    if data.startswith(b"\xef\xbb\xbf"):
        raise StateError("corrupt state file: UTF-8 BOM is not allowed")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise StateError("corrupt state file: not valid UTF-8") from None
    return _validate_sessions(_decode_json(text))


def write_state(path: str, sessions: list[dict[str, Any]]) -> None:
    payload = json.dumps({"sessions": sessions}, separators=(",", ":"), ensure_ascii=False) + "\n"
    directory = os.path.dirname(os.path.abspath(path))
    scratch_fd: int | None = None
    scratch_path: str | None = None
    try:
        scratch_fd, scratch_path = tempfile.mkstemp(prefix=".focus-stats-", suffix=".tmp", dir=directory)
        with os.fdopen(scratch_fd, "wb") as handle:
            scratch_fd = None
            handle.write(payload.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(scratch_path, path)
        scratch_path = None
    except OSError as exc:
        raise StateError(f"cannot write state file: {exc}") from None
    finally:
        if scratch_fd is not None:
            with contextlib.suppress(OSError):
                os.close(scratch_fd)
        if scratch_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(scratch_path)


def cmd_record(path: str, session_id: str, session_date: datetime.date, minutes: int) -> int:
    date_text = session_date.isoformat()
    sessions = load_state(path, allow_missing=True)

    for session in sessions:
        if session["id"] == session_id:
            if session["date"] == date_text and session["minutes"] == minutes:
                _emit({"recorded": False})
                return EXIT_OK
            raise ConflictError(f"session id {session_id!r} already exists with a different date or minutes")

    if len(sessions) >= MAX_SESSIONS:
        raise UsageError(f"state file already holds the maximum of {MAX_SESSIONS} sessions")

    sessions.append({"id": session_id, "date": date_text, "minutes": minutes})
    sessions.sort(key=lambda session: (session["date"], session["id"]))
    write_state(path, sessions)
    _emit({"recorded": True})
    return EXIT_OK


def cmd_report(path: str, week_start: datetime.date) -> int:
    latest_start = datetime.date(9999, 12, 31) - datetime.timedelta(days=WEEK_DAYS - 1)
    if week_start > latest_start:
        raise UsageError(f"invalid --week-start: must not be later than {latest_start.isoformat()}")

    sessions = load_state(path, allow_missing=False)

    per_date: dict[str, list[int]] = {}
    for session in sessions:
        bucket = per_date.setdefault(session["date"], [0, 0])
        bucket[0] += 1
        bucket[1] += session["minutes"]

    days = []
    total_sessions = 0
    total_minutes = 0
    for offset in range(WEEK_DAYS):
        day_text = (week_start + datetime.timedelta(days=offset)).isoformat()
        count, minutes = per_date.get(day_text, [0, 0])
        days.append({"date": day_text, "sessions": count, "minutes": minutes})
        total_sessions += count
        total_minutes += minutes

    _emit(
        {
            "start": week_start.isoformat(),
            "days": days,
            "sessions": total_sessions,
            "minutes": total_minutes,
        }
    )
    return EXIT_OK


_OPTION_NAMES = ("--id", "--date", "--minutes", "--week-start")

_RECORD_OPTIONS = ("--id", "--date", "--minutes")
_REPORT_OPTIONS = ("--week-start",)


def _parse_options(argv: list[str], allowed: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    positional: list[str] = []
    values: dict[str, str] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in _OPTION_NAMES:
            if token not in allowed:
                raise UsageError(f"unknown option for this command: {token}")
            if token in values:
                raise UsageError(f"duplicate option: {token}")
            index += 1
            if index >= len(argv):
                raise UsageError(f"missing value for {token}")
            values[token] = argv[index]
            index += 1
        elif token.startswith("-") and token != "-":
            raise UsageError(f"unknown argument: {token}")
        else:
            positional.append(token)
            index += 1

    if len(positional) != 1:
        raise UsageError("expected exactly one FILE argument")
    return positional[0], values


def _require(values: dict[str, str], name: str) -> str:
    if name not in values:
        raise UsageError(f"missing required option: {name}")
    return values[name]


def _run(argv: list[str]) -> int:
    if not argv:
        raise UsageError("missing command (expected 'record' or 'report'); see --help")
    if argv[0] == "--help":
        sys.stdout.write(HELP_TEXT)
        sys.stdout.flush()
        return EXIT_OK
    if argv[0] == "--version":
        sys.stdout.write(f"{PROGRAM} {VERSION}\n")
        sys.stdout.flush()
        return EXIT_OK

    command = argv[0]
    if command == "record":
        path, values = _parse_options(argv[1:], _RECORD_OPTIONS)
        session_id = parse_id(_require(values, "--id"))
        session_date = parse_date(_require(values, "--date"), "--date")
        minutes = parse_minutes(_require(values, "--minutes"))
        return cmd_record(path, session_id, session_date, minutes)
    if command == "report":
        path, values = _parse_options(argv[1:], _REPORT_OPTIONS)
        week_start = parse_date(_require(values, "--week-start"), "--week-start")
        return cmd_report(path, week_start)
    raise UsageError(f"unknown command: {command}")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        return _run(argv)
    except CliError as exc:
        sys.stderr.write(f"error: {exc.message}\n")
        sys.stderr.flush()
        return exc.exit_code
