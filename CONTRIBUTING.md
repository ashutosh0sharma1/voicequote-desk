# Contributing to VoiceQuote Desk

Start with a small change that somebody can reproduce from a clean checkout. This is an experimental public source release; the README and VALIDATION.md describe the supported scope.

## Find the code

`engine.py` extracts requests and calculates Decimal totals; `app.py` persists reviewed quotes; `asr_worker.py` isolates optional speech inference.

## Useful contributions

- Expand ambiguous quantity/material fixtures without guessing a missing price.
- Improve model setup diagnostics while keeping request-time downloads disabled.
- Add a CSV export edge case with a formula-like input and verify it stays inert.

## Verify a change

Install the README dependencies, then run the relevant checks:

```sh
python -m pytest test_quotes.py -q
```

Run only checks appropriate to your change. Do not turn a unit test into a live provider call, model download, deployment or mutation of a real account. Keep optional integration acceptance explicit and report skipped prerequisites.

## Submit a pull request

Explain the observed problem, the resulting behavior, and the evidence used to verify it. Include a small synthetic reproduction for a bug. Keep unrelated formatting out of the change. Preserve upstream copyright/license notices and identify any new dependency and its license. Contributions are made under the applicable repository/source-file license.

Never include credentials, signed URLs, personal recordings, private transcripts, customer data, production exports or unlicensed media. Security reports belong in GitHub's private vulnerability reporting channel when available; do not post secrets in a public issue.
