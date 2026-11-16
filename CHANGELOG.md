# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-16

### Added

- `app record FILE --id ID --date YYYY-MM-DD --minutes N`: deterministic,
  idempotent insertion of a focus session into a JSON state file, with atomic
  write via temporary file plus `os.replace`.
- `app report FILE --week-start YYYY-MM-DD`: read-only seven-day window report
  with per-day and weekly session/minute totals.
- `app --version` (`offline-focus-stats 0.1.0`) and `app --help`.
- Strict state validation: exact schema, unique ids, sorted `(date, id)` order,
  at most 10000 sessions, at most 4 MiB, strict integers, no duplicate JSON keys
  and no `NaN`/`Infinity`.
- Public black-box test suite in `tests/`, traceable to `AC-1`…`AC-14`.
- CI workflow running lint, format check and tests on Ubuntu and macOS with
  Python 3.12.

### Notes

- Runtime is the Python 3.12 standard library; there are no runtime
  dependencies and no `setup` step.
- Native Windows is out of scope for this version.
