# PyTAF Phase 1 Core

- uv-managed (lock/sync/run/build)
- Echo transport only (no VISA)
- Broker subprocess with dual lanes (control/bulk) and chunk-boundary preemption
- Cancellation ladders: Windows (CTRL_BREAK + Job Object), Linux (SIGINT→SIGTERM→SIGKILL)
- Durable artifacts: results JSONL, CSV (excel+raw), trace JSONL + sidecar blobs, headers, manifest, layout
- Safe "latest" link (junction on Windows; symlink on Linux; LATEST.txt fallback)
- Cloud/permission relocation and stale-temp gate
- Kill safety: broker-exclusive lockfile; refusal when not held
- Exit codes used: 22 (ConfigError), 23 (TransportError), 24 (IPCBodyTooLarge), 28 (StaleTempGate), 31 (AbortBySignal), 34 (RefusedByPolicy)

## CI sequence

```bash
uv lock
git diff --quiet uv.lock || (echo "uv.lock drift – commit updated lock" && exit 1)

uv sync --group dev --locked
ruff check
ruff format --check
mypy src
pytest -q

# CLI smoke (assert version prints something)
OUT="$(uv run pytaf version)"; test -n "$OUT"

uv run pytaf --help
uv run pytaf init --non-interactive --bench-dir bench
uv run pytaf run --bench bench/bench.local.toml
