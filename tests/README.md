# Public black-box tests

One command runs the whole suite:

```console
python -m pytest
```

Everything here drives the product through its public entrypoint in a
subprocess (`sys.executable app …`). No test imports `focus_stats` or any other
implementation module, and every test uses its own temporary directory.

| AC | Criterion | Where |
| --- | --- | --- |
| AC-1 | record creates one session; identical repetition returns `recorded=false` | `test_record.py::test_ac1_*` |
| AC-2 | same id with different date/minutes → exit 4, no mutation | `test_record.py::test_ac2_*` |
| AC-3 | two sessions 25 + 50 on one day → `sessions=2`, `minutes=75` | `test_report.py::test_ac3_*` |
| AC-4 | report always seven days, zeros on missing days | `test_report.py::test_ac4_*` |
| AC-5 | `start` and `start+6` count, `start+7` does not | `test_report.py::test_ac5_*` |
| AC-6 | week crossing leap-year February follows the Gregorian calendar | `test_report.py::test_ac6_*` |
| AC-7 | `N=1/480` valid; `0/481/true/decimal` invalid | `test_record.py::test_ac7_*` |
| AC-8 | broken JSON or duplicate id in state → exit 3, no overwrite | `test_state_validation.py::test_ac8_*` |
| AC-9 | write/replace failure → exit 3, original intact, empty stdout | `test_write_failure.py::test_ac9_*` |
| AC-10 | report never modifies or creates FILE; missing FILE → exit 3 | `test_report.py::test_ac10_*` |
| AC-11 | `--week-start 9999-12-25` valid, `9999-12-26` → exit 2 | `test_report.py::test_ac11_*` |
| AC-12 | 10001st session → exit 2, count and bytes preserved | `test_record.py::test_ac12_*` |
| AC-13 | state sorted by `(date, id)` after out-of-order records | `test_record.py::test_ac13_*` |
| AC-14 | `--version`/`--help` need no timer and no state file | `test_cli_contract.py::test_ac14_*` |

Additional suites:

- `test_cli_contract.py` — version/help text, argument errors (exit 2), option
  ordering, POSIX `./app` ≡ `python app`, unicode and spaced paths.
- `test_state_validation.py` — exact schema, duplicate JSON keys, `NaN`/`Infinity`,
  non-strict numbers, 4 MiB and 10000-session limits, BOM, invalid UTF-8, and
  "argument validation precedes state reading".
- `test_write_failure.py` — the portable write-failure fixture: a POSIX directory
  whose write permission is removed, skipped only when the host is privileged
  and does not enforce `chmod`.
