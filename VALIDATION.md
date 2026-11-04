# Validation

Release preparation: 2026-11-04. These are results from the clean source export on Windows; the workflow badge reports subsequent fresh Linux CI results.

## Verified

13 tests passed for extraction, quote arithmetic, validation, persistence and CSV behavior.

## Limits

Typed input is available without an ASR model. Real speech recognition was not rerun; sample recordings are generated separately.

Provider credentials were excluded from test environments. Test success does not establish production readiness or compatibility with every machine. Reproduce the documented checks after installing dependencies; report failures with synthetic fixtures and environment versions.
