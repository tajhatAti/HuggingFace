# Contributing

Keep Lyr Online minimal: one bounded song-to-lyrics workflow, one instant lookup, and one structured app contract.

Before pushing:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check app.py lyr_service tests scripts
python -m compileall -q app.py lyr_service scripts tests
git diff --check
```

Changes must preserve fixed external hosts, upload/duration limits, no audio execution, ephemeral outputs, one-worker GPU concurrency, Bengali Unicode handling, explicit LRC cue endings, and graceful LRCLIB/ZeroGPU failures. Never commit tokens, private audio, model caches, generated APKs, or build directories.
