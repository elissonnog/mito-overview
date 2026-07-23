# Optional archive checks

This directory contains repository-only tests for future archival helpers. They
are intentionally excluded from the default `pytest` collection, source
distribution, CI acceptance, and the MitoOverview v0.3.0 GitHub release gate.

Run the current helper checks explicitly only when evaluating that optional
integration:

```bash
python -m pytest -q optional_checks/test_zenodo_reservation_capture.py
```

These tests use mocked responses and do not reserve or publish a DOI.
