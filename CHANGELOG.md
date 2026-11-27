# Changelog

## 0.4.0 — Unreleased

- Document the frozen v4 operation scope, architecture, and evaluation evidence.
- Add a synthetic, headless demonstration of pre-execution estimates, risk, partial-cell output, suggestions, and
  measured-versus-predicted results.
- Require Python 3.11 or later and pandas 3.1 or later in package metadata.
- State known failures, inconclusive outcomes, and held-out data that remains unread.

This release has not been uploaded to PyPI. To test the built distributions on TestPyPI after publication:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ nexus==0.4.0
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "nexus[dev]==0.4.0"
```

Do not upload to TestPyPI or PyPI as part of this repository task.
