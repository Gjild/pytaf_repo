---

# PyTAF — Python Test Automation Framework (Hardened Core v1, Revised)

A clone-and-run Python framework for **local, single-engineer** control of SCPI instruments and execution of RF/Electrical test plans on **dynamic benches**. The system is **CLI-only** (no GUI), supports **Windows 11** and **Ubuntu 24.04**, and is engineered for **deterministic cancellation**, **per-session I/O isolation**, **explainable safety refusals**, **durable local artifacts**, and **machine-readable results**. Plans execute **sequentially**. Supported transports are **VXI-11 (LAN)** and **USBTMC** (NI-VISA on Windows; `pyvisa-py` on Linux). A **GPIB-USB escape hatch** is provided as a **text-only, query-only, tech-preview path** via NI-VISA for legacy instruments (no energizing, no binblocks). Binary fetches use **IEEE-488.2 definite binblocks** with **per-profile proven maxima**. Every driver implements a **bounded, idempotent `safe_state()`**, and **transport teardown is treated as a safe-state fallback** with prominent visibility and re-verification on reconnect. Artifact formats are **JSONL** (canonical) with optional Zstandard compression; raw I/O trace is also **JSONL** with base64 payloads.

---

# PyTAF — Python Test Automation Framework (Hardened Core v1)

A clone-and-run Python framework for **local, single-engineer** control of SCPI instruments and execution of RF/Electrical test plans on **dynamic benches**. The system is **CLI-only**, supports **Windows 11** and **Ubuntu 24.04**, and is engineered for **deterministic cancellation**, **per-session I/O isolation**, **explainable safety refusals**, **durable local artifacts**, and **machine-readable results**. Plans execute **sequentially**. Supported transports in core are **VXI-11 (LAN)** and **USBTMC** (NI-VISA on Windows; `pyvisa-py` on Linux). **GPIB** support is available **only via a separate optional plugin package** (query-only, no energizing, no binblocks). Binary fetches use **IEEE-488.2 definite binblocks** with **per-profile proven maxima**. Every driver implements a **bounded, idempotent `safe_state()`**; **transport teardown** is treated as a safe-state fallback with **hardware state re-verification on reconnect**. Artifact formats are **JSONL** (canonical) with optional **Zstandard** compression; raw I/O trace is **JSONL** with **sidecar binary blobs** for large payloads.

---

## 0) Purpose, Scope, Non-Goals

### 0.1 Purpose

Deliver a hardened, local-first core that:

* Controls SCPI instruments via:

  * **VXI-11 (LAN)** using `pyvisa-py`. Per-profile read chunking and ladder timing.
  * **USBTMC**:

    * **Windows**: **NI-VISA**.
    * **Linux**: **`pyvisa-py`** with udev rules.
* Executes **sequential** test plans using:

  * **I/O broker subprocess** that owns all instrument sessions and **serializes I/O per session** with **priority lanes** (“control/query” vs “bulk/fetch”).
  * **Per-operation budgets**, **profile-tuned read ladders**, **zero-length storm guard** with bounded **diagnostic queries**, and **targeted reconnect**.
  * **Deterministic cancellation** on both OSes with logged escalation ladders and **PID-file tooling**.
* Enforces **absolute-dB safety** with numeric evidence:

  * **`strict` preset is default**: uncertainty math, analyzer guard (refuse-first; optional single auto-attenuation within caps), low-power RBW-aware verification.
  * **`light` preset**: envelope + low-power sanity only; **waiver-gated**.
* Produces **durable local artifacts**:

  * **Results JSONL**, **CSV (excel-safe and raw)**, **raw I/O trace JSONL + sidecar blobs**, structured logs, **results header**, **manifest**, and a **human-readable safety ledger**.
  * **Atomic writes** with Windows-specific durability; **relocation** away from cloud-synced paths recorded in manifest and bannered on CLI.

### 0.2 Scope (v1 Core)

* **OS**: Windows 11 x64; Ubuntu 24.04 x86\_64.
* **Python**: 3.11 primary; 3.12 supported (hash-pinned constraints).
* **Transports/backends (core)**:

  * VXI-11 via `pyvisa-py`.
  * USBTMC via NI-VISA (Windows).
  * USBTMC via `pyvisa-py` (Linux).
* **GPIB**: not in core; available as **separate plugin** (“GPIB escape”) providing **ASCII query-only** functions (no energizing, no binblocks).
* **Execution model**: CLI runner + **I/O broker subprocess** (default). Thread-mode fallback via env for emergency debugging.
* **Drivers & profiles**: minimal deterministic set; each driver must implement **bounded `safe_state()`** and **post-reconnect low-power gate**.
* **Trace format**: **`trace.raw.v1.jsonl[.zst]`** referencing **sidecar `.bin`** blobs for large payloads.

### 0.3 Non-Goals

* No servers, multi-user coordination, GUI, or web UI.
* No LAN scanning/mDNS/LXI auto-discovery.
* No parallel plan steps.
* No Parquet/columnar stores in core.
* No Windows USBTMC via `pyvisa-py` distribution in v1.

---

## 1) Operating Assumptions

* Single engineer; instruments may be added/removed frequently (**dynamic benches**).
* Bench configs and calibration files are **local** and version-controlled.
* Corporate egress may be restricted; **offline wheelhouse** and **hash-pinned constraints** provided.
* Cloud-redirected user profiles are common on Windows; **auto-relocation** to machine-local paths may occur.
* IPv4 preferred; IPv6 link-local supported only with **explicit scope** in addresses.

---

## 2) Compatibility Matrix (Core)

| Component              | Windows 11          | Ubuntu 24.04        |
| ---------------------- | ------------------- | ------------------- |
| Python 3.11 / 3.12     | ✅                   | ✅                   |
| VXI-11 (`pyvisa-py`)   | ✅                   | ✅                   |
| USBTMC via NI-VISA     | ✅                   | —                   |
| USBTMC via `pyvisa-py` | —                   | ✅                   |
| GPIB (plugin)          | ⚠️ separate package | ⚠️ separate package |

**Notes**

* Windows USBTMC via `pyvisa-py` is not shipped/tested in v1.
* The GPIB plugin is query-only and not part of core acceptance matrices.

---

## 3) Architecture and Execution Model

### 3.1 Processes, Isolation, and Priority Lanes

* **Main process**: CLI, plan runner, safety engine, artifact writers, watchdog, results emitter.
* **I/O broker subprocess**:

  * Owns all VISA sessions (one per instrument).
  * **Per-session queues with two lanes**:

    * **Control** (default for configuration, queries, `*OPC?`, safety probes).
    * **Bulk** (binblock fetches and other large transfers).
  * **Preemption points** (at chunk boundaries or ladder steps) allow control lane items to proceed when **bulk** would cause deadline misses.
  * Enforces budgets, read ladders, reconnect drills, diagnostics.
  * Logs **INT/TERM/KILL/CTRL\_BREAK** handling and writes a **PID file** `{run_uuid}.pid`.
* **Thread-mode fallback**: `PYTAF_BROKER=0` (debug only).

### 3.2 Timekeeping and Epochs

* The main process chooses a **monotonic epoch** (`epoch_id`, `t0_monotonic_ns`).
* Broker logs deltas relative to epoch. Broker restart rolls a new epoch; consumers must not merge across epochs.

### 3.3 IPC and Cancellation

* IPC is binary, length-delimited, with `op_id`, `epoch_id`, and `monotonic_ns`.
* **Soft cancel**: stop scheduling; broker completes in-flight I/O within budgets; drivers receive bounded `safe_state()`.
* **Hard cancel**:

  * **Windows**: broker in **Job Object**; escalation **CTRL\_BREAK → TerminateJobObject** after grace.
  * **Linux**: `SIGINT → SIGTERM → SIGKILL` with grace windows.
* **Stray reaping**: `pytaf kill --last-run` reads the manifest’s `{run_uuid, broker_pid}` to terminate a live broker.
* **Shell conformance**: cancellation is validated under **PowerShell 7, PowerShell 5, cmd.exe, VS Code Terminal, bash, zsh**.

---

## 4) Transport and Resource Model

### 4.1 Transport SPI

```python
from typing import Protocol, Literal, Optional, Mapping
from dataclasses import dataclass

class Transport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def transact(self, tx: bytes, policy: "CmdPolicy",
                 budgets: "Budgets", cancel: "CancelToken") -> bytes: ...
    @property
    def resource(self) -> str: ...   # canonical internal URI
    @property
    def backend(self) -> str: ...    # "vxi11-py", "usbtmc-ni", "usbtmc-py"
    @property
    def diag(self) -> "TransportDiag": ...

@dataclass
class Budgets:
    write_ms: int
    complete_ms: int
    read_ms: int
    total_ms: int

@dataclass
class TransportDiag:
    bytes_tx: int
    bytes_rx: int
    last_timeout_phase: Optional[Literal["write","complete","read"]]
    reconnects: int
    zero_len_read_events: int
    zero_len_backoffs: int
    paced_writes: int
    last_diag_query_ok: Optional[bool]

class CmdPolicy(Mapping[str, object]):
    """
    Schema-validated mapping:
      framing: {mode: "text"|"def_block", max_text_bytes, max_block_bytes}
      completion: {"opc_query"|"fixed_delay_verify"}
      verify_query: Optional[str]
      completion_timeout_ms: int
      pacing: {write_pace_us, max_cmds_per_s}
      idempotent: bool
      energizes: bool
    """
    ...
```

### 4.2 Internal Resource URIs

* VXI-11: `pytaf+vxi11://<ip-or-[ipv6%scope]>/<slot>`
* USBTMC: `pytaf+usbtmc://<vid:pid>/<serial?>`

Configuration stores **canonical URIs**; VISA strings are derived per backend.

### 4.3 IPv6 Policy

* IPv6 supported only with **explicit scope** in the address (e.g., `fe80::1%12`). No automatic scope resolution logic in v1.

### 4.4 VXI-11

* Implemented via `pyvisa-py`.
* Requires **portmapper**; if absent, fail with remediation guidance.
* **Per-resource program-port mappings** are allowed when explicitly recorded in the profile with provenance metadata.
* Read path uses **profile-driven chunk sizes** (e.g., 64 KiB) and **profile-tuned ladder timing**.

### 4.5 USBTMC

* **Windows**:

  * **NI-VISA** supported; doctor verifies presence, version, and bitness.
  * VISA stack ordering is validated; mixed stacks are refused.
* **Linux**:

  * `pyvisa-py` with udev rules; doctor verifies groups/permissions and hotplug behavior.
* Read path uses profile-defined chunk sizes; ladder timing is profile-tuned.

### 4.6 Echo Transport (Test-only)

A transport-agnostic “echo” backend exercises the broker/IPC/cancellation paths without VISA. It supports:

* Deterministic latencies, fragmentation, half-close, delayed trailers.
* Simulated binblock framing and large payload flows.
* Injected faults: zero-length storms, RST-like aborts, stuck `*OPC?`.

---

## 5) SCPI Semantics and Device Determinism

### 5.1 Completion Policies and Retry Rules

* Default completion for configuration and RF state changes: `*OPC?`.
* Retunes (frequency/power) per profile choose between:

  * `opc_query` (default).
  * `fixed_delay_verify` (bounded delay then verify readbacks).
* **Retry** only for commands marked **`idempotent=true`** and **never** for **`energizes=true`**.

### 5.2 Binary Format Lock

* Before any binary fetch, drivers **force and verify** instrument data format (`FORM:DATA`, endianness).
* Linter prohibits binary fetch APIs unless **format-lock commands** executed **in the same session**.
* **Sanity binblocks** (small \~1 KiB and medium 2–4 MiB) verify framing/trailer before large transfers.

### 5.3 Analyzer Determinism

Drivers set and verify RBW, span, detector, averages, reference level, attenuation, sweep/time settings. A **ready probe** (`*OPC?` plus device-specific marker if required) confirms buffer readiness before fetch.

### 5.4 Bounded Safe State and Hardware Verifications

```python
class BaseDriver(Protocol):
    def connect(self, cancel): ...
    def idn(self, cancel) -> str: ...
    def option_set(self, cancel) -> str: ...
    def safe_state(self, cancel) -> None: ...  # bounded, idempotent
    def verify_outputs_off(self, cancel) -> None: ...  # must confirm de-energized state
    def close(self) -> None: ...
```

* `safe_state()` is bounded per device category (source/analyzer).
* On timeout, broker **tears down** the session and marks it **dirty**; transport teardown is recorded as the safe-state outcome.
* On reconnect, the driver must **verify outputs are off/muted** before any energize and pass the **low-power gate**.

### 5.5 Numeric Handling

* Raw bytes are preserved in traces.
* Numeric parsing yields `(value, unit, provenance)`; units normalized.
* Policies:

  * **strict**: dot-decimal only; `INF/NAN` refused.
  * **lenient**: comma decimal and `INF/NAN` normalized with warnings.
* Formatting for text exports:

  * Scientific with up to **12 significant digits** when `|x| ≥ 1e9` or `< 1e-6`; otherwise fixed with up to 12 fractional digits.

### 5.6 Error Queue Discipline

* On connect: capture and clear; record contents.
* Drain at step boundaries, before energize, after fetch, and on failure.

---

## 6) Safety System (Absolute-dB; `strict` Default)

### 6.1 Presets

* **`strict` (default)**: envelope with uncertainty (`k·σ`), analyzer guard (refuse-first; optional **single** auto-attenuation within bench/device caps), RBW-aware low-power verification, confirm logic.
* **`light`**: envelope without uncertainty uplift; analyzer overrange warn-only; low-power sanity with fixed SNR margin. **Use requires an explicit waiver file**.

Preset is selected per run and recorded in the manifest.

### 6.2 Calibration Ingestion and Normalization

* CSV schema: `freq_Hz,loss_dB[,sigma_dB]` with optional YAML front-matter (schema, lab, instrument serial, author, date).
* Normalization: ascending frequency, dedup keep-last with warning, strict monotonic frequency.
* Coverage: **no extrapolation** by default. Outside coverage is refused unless policy sets `flat` or `linear` and a waiver is provided.
* Uncertainty:

  * Per-row σ supported; path elements combine via **RSS** to `σ_path_dB`.
  * **Missing σ is fatal in armed runs** unless a **waiver file** is referenced. CLI flags alone are insufficient.
* Freshness: `max_cal_age_days` enforced.

### 6.3 DUT Envelope with Uncertainty

Given bench envelope `P_dut_max_dBm(f)`, path loss `L_path_src(f)` with uncertainty `σ_path_dB`, derating margin `D_dB`, and k-factor `k`:

* Predict DUT input: `P_dut_expected = P_src_set_dBm − L_path_src(f)`.
* Composite margin (`strict`): `M_dB = D_dB + k * σ_path_dB`.
* Refusal criterion: `P_dut_expected > P_dut_max_dBm(f) − M_dB`.

Artifacts include interpolants, checksums, and waiver references.

### 6.4 Analyzer Guard with Hysteresis and Persistence

* Analyzer limit `P_analyzer_max_dBm(f)`; bench and device specify attenuation caps; the **smaller** cap wins.
* Predicted analyzer input: `P_an_in = P_src_set_dBm − L_src_to_an(f) − Atten(cfg)`.
* Strategy:

  * **strict**: refuse when violation is predicted. Optional **single auto-attenuation** then confirm.
  * **light**: warn-only; no auto-atten.
* **Hysteresis latch** (default 2 dB) enforces minimum attenuation. The latch **persists across reconnects** and is recorded in the manifest; cleared only on plan reset.

### 6.5 Low-Power Verification (RBW-Aware)

* Required at session start, after reconnect, and after abort.
* Start at `low_power_check_dbm` and step up within caps; analyzer guard respected.
* Expected noise floor:

```
N_dBm ≈ -174 dBm/Hz + 10*log10(RBW_Hz) + NF_dB + detector/avg offsets
```

* Pass rule: `|measured − predicted| ≤ guard_tolerance_dB` (default 1.5 dB). If within `confirm_margin_dB` (0.5 dB), run a **single confirm sweep**.

### 6.6 Overrange Handling

* Overrange flag path defined by profile. When mismatch detected at runtime:

  * Attempt a **fallback detector** that compares adjacent sweeps for clipping.
* In `strict`, persistent overrange after confirm → **refuse** (optional auto-atten then confirm once).
* In `light`, warn-only.

---

## 7) Identity, Firmware Matching, Profiles

### 7.1 Vendor-Aware Firmware Matcher (Pluggable)

Profiles define:

* **Normalizer**: either regex capture **or a pluggable Python normalizer** (entry point) to handle vendor-specific formats (e.g., letter suffixes, non-monotone betas).
* **Comparator**: `semver_like`, `tuple`, or `lex`.
* **Ranges** and **deny-lists** of normalized versions.

### 7.2 Capability Probes and Cache

On first connect for key `(vendor, model, serial, firmware_norm, option_set, backend, chunk_bytes, ladder_signature)`:

* Validate `*OPC?` reliability.
* Verify binary fetch framing/trailer via **small + medium** binblocks.
* Verify overrange path or record fallback detector.
* Persist **capability proof records** with timestamps and parameters to `capcache.v1.jsonl`.
* Cache TTL is profile-defined; cache invalidates on any key change.

### 7.3 Driver Contracts (Excerpts)

```python
class RfSource(BaseDriver):
    def set_frequency(self, f_hz: int, cancel) -> None: ...
    def set_power_dbm(self, p_dbm: float, cancel) -> None: ...
    def rf_on(self, cancel) -> None: ...
    def rf_off(self, cancel) -> None: ...
    def wait_settled(self, cancel) -> None: ...
    def mute_enable(self, cancel) -> bool: ...
    def mute_disable(self, cancel) -> bool: ...
    def alc_hold_enable(self, cancel) -> bool: ...
    def alc_hold_disable(self, cancel) -> bool: ...

class Analyzer(BaseDriver):
    def configure_chp(self, cfg: "ChpCfg", cancel) -> None: ...
    def ready(self, cancel) -> None: ...
    def single(self, cancel) -> None: ...
    def fetch_chp_dbm(self, cancel) -> float: ...
    def overrange(self, cancel) -> bool: ...
```

---

## 8) Plan Model, Runner, Deadlines, Cancellation

### 8.1 Step API

* Decorators `@step` and `@for_each` define sequential steps.
* `ctx.emit(name, value, unit, extra=...)` writes to results.
* Resource getters provide driver instances by alias.

### 8.2 Deadlines, Floors, and Amortization

* Step deadlines propagate to driver calls.
* **Dynamic per-call floor**: calls are rejected pre-start if `remaining_ms` below `min(global_floor_ms, floor_fraction × step_deadline_ms)`.
* **Floor amortization**: surplus from earlier under-run calls accrues **credit** applied to later calls within the same step to avoid starvation near deadlines.
* **Category floors** (`fetch` > `cfg` > `query`) are profile-defined.

### 8.3 Cancellation and Reconnect

* Soft/hard cancel semantics as in §3.3.
* Reconnect requires **verify\_outputs\_off()** and **low-power gate** before any energize.
* Logs include **escalation ladders** and outcomes.

### 8.4 Linter

* Flags:

  * Missing or non-idempotent `safe_state`.
  * Calls attempted under dynamic floor without amortization credit.
  * **Binary fetch without format-lock** in the same session.
  * **Queries without read** unless explicitly allow-listed **per driver** (e.g., `*WAI`, status clears).
  * **Backend policy violations** detected statically (e.g., GPIB plugin misuse when plans/benches reference it).

---

## 9) Results, Traces, Logs, and Manifest

### 9.1 Result Files

* **`results.v1.jsonl`**: line-delimited JSON measurements (name, value, unit, context, provenance, timestamps).
* **`export/data.excel.csv`** and **`export/data.raw.csv`** are both emitted by default (stable columns; dot-decimal enforced).

### 9.2 Privacy and Sanitization

* **All textual fields** (paths, usernames, hostnames, URIs) in artifacts are optionally filtered to remove bidi controls and dangerous prefixes.
* Sanitization actions are recorded in artifact metadata.

### 9.3 Raw I/O Trace (Canonical + Sidecars)

* **`trace.raw.v1.jsonl[.zst]`** entries capture direction, timestamp, resource URI, framing, length, and:

  * For **small payloads**: base64 inline.
  * For **large payloads**: **sidecar binary files** stored as content-addressed blobs under `trace_blobs/`. JSONL references `"blob":"sha256:<digest>"` and byte ranges.
* Sidecar blob files are not compressed; rotation applies to JSONL only.

### 9.4 Logs, SCPI Transcript, Safety Ledger, and Layout

* `logs.v1.jsonl`: structured events, counters, cancellation ladders, relocation banners, and **SCPI transcripts for failed steps** (secrets redacted).
* `safety_ledger.md`: human-readable summary of safety decisions (envelope checks, attenuations, refusals, waivers).
* `layout.v1.json`: file list with sizes and SHA-256 hashes for quick integrity checks.

### 9.5 Headers, Manifest, and “latest” Link

* `results.header.json`: bench/plan IDs, profile and safety preset, backend selection, VISA stack info, environment (locale, CPU hints), baseline samples and confidence.
* `manifest.v1.json`: device identities, profile versions, backend, capability cache keys, broker PID, epochs, relocation status, **attenuation latch state**, waiver references.
* A platform-appropriate **“latest” link** (symlink on Linux; shortcut/junction on Windows) points to the run directory.

---

## 10) Durability, Rotation, Relocation

### 10.1 Atomicity

* **POSIX**: write → `fsync(fd)` → `rename()` → `fsync(dir)`.
* **Windows**: write → `FlushFileBuffers` → `MoveFileEx(MOVEFILE_WRITE_THROUGH|REPLACE_EXISTING)`; directory durability via a **hidden anchor file** that is opened and flushed to force metadata persistence.

### 10.2 Fsync Policy

* Results JSONL: line-flush + periodic fsync (configurable).
* Trace JSONL: fsync on rotation; optional periodic fsync.
* CSV, manifest, headers, ledger, layout: fsync on close.

### 10.3 Guardrails, Rotation, Compression

* Guardrails: `max_single_file_mb`, `min_free_space_mb`; proactive refusal before exhaustion.
* Rotation by time/size; optional **zstd** compression.
* Compression **stats** (ratio, time) are recorded in the manifest.

### 10.4 AV/CFA Fallback and Relocation

* On denial (Controlled Folder Access, AV, policy), results relocate to:

  * Windows: `%ProgramData%\PyTAF\cache`
  * Linux: `$XDG_DATA_HOME/pytaf` or `~/.local/share/pytaf`
* Manifest `{relocated:true, relocation_path:"..."}` and a CLI **`RELOCATED:`** banner are emitted. Exit code remains success.

### 10.5 Stale Temp Sweeper

* At startup, detection of stale temp files causes a refusal unless `--acknowledge-stale` is provided. The manifest records the acknowledgment.

---

## 11) Discover, Validate, Doctor

### 11.1 Discover

* VISA enumeration with backend attribution; output canonical resource URIs.
* No active network probing beyond VISA-exposed endpoints.

### 11.2 Validate

* Bench schema lint with **JSON Pointer** errors.
* Calibration coverage/age checks with **holes report**.
* Firmware matcher normalization/range/deny checks.
* Identity/option set must match profiles.
* Capability probes (small + medium binblock, `*OPC?`, overrange path/fallback).
* **Static backend policy checks** (e.g., plans referencing plugin-only backends without the plugin enabled).

### 11.3 Doctor

* Python and `pyvisa` presence; **VISA stack ordering** and **NI-VISA version/bitness** (Windows).
* USBTMC driver binding; Linux udev groups; **hotplug re-open** verification.
* VXI-11 reachability (host/portmapper).
* WSL detection and routing banner; Controlled-Folder/long-path probes; path budget.
* Cancel risk summary (Job Object availability, shell notes).
* **Throughput measurement** using a capability probe instead of socket hints; results cached.

---

## 12) Configuration (TOML)

### 12.1 Layering

1. Built-in defaults.
2. `bench.toml` (committed).
3. `bench.local.toml` (git-ignored) for local/risky overrides (backend selection, program-port mappings).
4. CLI `--set KEY=VALUE` / `--set-file`.
5. Env override `PYTAF_SET="..."`.

### 12.2 Bench Schema (`bench.v1`) — Excerpt

```toml
schema_version = "bench.v1"
bench_id = "labA_bench03"
project  = "rf_core_validation"

[results]
root = "C:/pytaf/results"
temp_dir = ""
rotate_trace_mb = 0
rotate_logs_mb  = 0
compress = false
excel_safe_csv = true          # both excel/raw emitted
cloud_paths_auto_relocate = true
paranoid_fsync = false
max_single_file_mb = 2048
min_free_space_mb  = 1024
short_run_ids = false
trace_mode = "jsonl"           # jsonl | off
relocation_banner = true
emit_latest_link = true

[visa]
default_vxi11_backend   = "pyvisa-py"
windows_usbtmc_backend  = "ni-visa"
linux_usbtmc_backend    = "pyvisa-py"
allow_multi_visa        = true
program_port_map_allow  = true

[timeouts]
opc_ms = 2500
opc_long_ms = 12000
epsilon_ms = 50
per_call_floor_ms = 100
per_call_floor_fraction = 0.2
safe_state_source_timeout_ms   = 2000
safe_state_analyzer_timeout_ms = 3000
abort_watchdog_ms = 1500
heartbeat_s = 2

# Per-profile read ladders supersede these defaults
[read_ladder_defaults]
phases_ms = [20, 50, 100]      # used only if profile lacks ladder

[floors_by_category]
rf     = 200
cfg    = 200
retune = 400
fetch  = 1200
sweep  = 2000
query  = 200

[pacing]
cfg_max_cmds_per_s = 10
fetch_max_cmds_per_s = 2
query_max_cmds_per_s = 5

[transport]
read_chunk_bytes_vxi11  = 65536
read_chunk_bytes_usbtmc = 32768
max_text_bytes  = 16384
max_block_bytes = 134217728
tcp_nodelay_best_effort = true

[safety]
preset = "strict"               # strict | light (waiver required)

[safety.general]
derating_margin_dB = 2.0
uncertainty_k = 2.0
guard_tolerance_dB = 1.5
confirm_margin_dB  = 0.5
low_power_check_dbm = -30.0
max_cal_age_days = 365
hysteresis_dB = 2.0
extrapolation_policy = "none"   # none | flat | linear
require_low_power_on_reconnect = true
require_low_power_on_session_start = true
auto_atten_enable = false       # profile may override within caps

[safety.analyzer_caps]
min_rbw_hz = 1000
max_rbw_hz = 300000
span_hz    = 1000000
min_atten_dB = 0
max_atten_dB = 40
max_avg = 5
overrange_strategy = "refuse_first"
confirm_sweeps_on_overrange = 1
sensitivity_dbm = -90.0
nf_dB = 5.0                     # proof metadata required in profile
detector_offset_dB = 0.0
avg_offset_dB = 0.0
snr_margin_dB = 6.0

[limits.rf_main]
bands = [
  { f_min_Hz=1.9e9, f_max_Hz=2.2e9, P_dut_max_dBm=5.0 }
]

[paths.rf_main]
cal_csv = "cal/rf_main.csv"
direction = "src_to_dut"
ref_plane = "at_dut_port"

[resources]
fsw1 = { address="TCPIP0::192.0.2.21::INSTR", driver="rs.fsw",    model="FSW",     serial="1023.4567K01" }
sma1 = { address="TCPIP0::192.0.2.20::INSTR", driver="rs.sma100b", model="SMA100B", serial="1023.4567S01" }

[aliases]
analyzer = "fsw1"
source   = "sma1"
src_path = "rf_main"
an_path  = "rf_main"

[firmware_matchers]
"Rohde&Schwarz" = { regex="(?P<maj>\\d+)\\.(?P<min>\\d+)\\.(?P<patch>\\d+)", comparator="tuple" }

[profile_overrides.rs.fsw]
max_binblock_bytes_proven = 33554432

[per_resource_features]
# Per-resource toggles for temporary relaxations/quirks
"sma1" = { allow_fixed_delay_verify=true }
```

---

## 13) CLI

```
pytaf run --mode <simulate|dry-run|armed> --bench <bench.toml> --plan <plan.py>
          [--results-root <dir>] [--results-temp-dir <dir>]
          [--set KEY=VALUE ...] [--short-run-ids]
          [--gate chp] [--waiver <waiver.yml>]
          [--extrapolation <none|flat|linear>]
          [--trace <jsonl|off>] [--csv <excel-safe|raw|both>]
          [--safety <strict|light>]
          [--seed <int>]

pytaf init [--non-interactive ...]
pytaf kill --last-run
pytaf discover [--detail]
pytaf validate --bench <bench.toml> [--plan <plan.py>] [--plan-only]
pytaf doctor [--quick] [--export <file.json>] [--patch] [--apply]
pytaf explain --results <run_dir>
pytaf plan lint [--fix]
```

**Modes**:

* `simulate` (no instrument I/O; deterministic models; **requires/records `--seed`**).
* `dry-run` (I/O suppressed; traces annotate `io:"suppressed"`).
* `armed` (hardware with safety).

**Verdict**: `PASS | REFUSE | ABORT` with run UUID and exit code.

---

## 14) Baseline Pinning and Performance Gates

### 14.1 Baseline Establishment

* Baselines are **not** captured on a single pass.
* Establish **P50** from **5 consecutive successful armed runs** within a **10-minute window** using **MAD** for outlier filtering.
* Store: sample count, window, P50, MAD, and environment hints (CPU freq, load if available) in `results.header.json` and manifest.

### 14.2 Gates

* **Reconnect latency (warm)**: first command after reconnect **≤ P50 + 250 ms** (measured after 5 warm commands; cold latency tracked separately).
* **Throughput**: measured 32 MiB binblock throughput **≥ P50 − 2 MiB/s** (median-of-medians with MAD filter).
* **Integrity**: 0 truncations/hangs across 1/8/32 MiB transfers during soaks.
* **Storm behavior**: backoff + bounded diagnostic queries → structured timeout (no livelock).
* **Safety**: envelope enforcement, analyzer guard, low-power verification, waiver adherence.

---

## 15) Conformance, Storm Guard, and Reconnect

* **Read ladders** are **profile-tuned**; default ladder used only when profiles omit them.
* **Zero-length storm guard**: `(events, window_ms)` triggers **exponential backoff** (bounded by budgets) and **N diagnostic queries** (`N` per profile; default 1). On failure: structured `IoTimeoutError`.
* **Device TCP RST** results in immediate **session dirty-mark**, close→reopen, identity re-cache, profile defaults re-apply, **verify\_outputs\_off()**, then **low-power gate** before energize.

---

## 16) Testing Strategy (v1)

* **Echo transport contract tests**: IPC framing, cancellation edges, epoch rollover, lane preemption, storm behavior.
* **Transport fakes**: half-close, delayed trailers, fragmentation, LF-after-large-only, stuck `*OPC?`, ignored terminators, USB bulk-in stall (USBTMC).
* **Mixed soak**: ≥10k transactions per backend/OS; 0 truncations; stable throughput.
* **Abort/reconnect**: mid-binblock abort → reconnect → low-power gate; warm latency vs pinned P50.
* **Cancel correctness**: exit codes under various shells (Windows PS7/PS5/cmd/VS Code; Linux bash/zsh).
* **Durability**: mid-rename kill, relocation path validations; stale temp sweeper behavior.
* **Locale**: `de_DE`, `fr_FR`, `ar_EG`, `ja_JP` runs verify dot-decimal CSV and numeric parsing policies.
* **Schema-compat**: goldens for results/logs/trace; CI ensures backward compatibility.
* **Firmware matcher corpus**: normalization/comparator/deny-list coverage.

---

## 17) Repository Layout (Core)

```
pytaf/
  pyproject.toml
  constraints/
    py311-windows.txt
    py311-linux.txt
    py312-windows.txt
    py312-linux.txt
  src/pytaf/
    broker/
      broker.py
      ipc.py
      epochs.py
      jobobjects_win.py
      pidfile.py
      lanes.py
    transport/
      spi.py
      vxi11_pyvisa.py
      usbtmc_ni.py
      usbtmc_pyvisa_linux.py
      echo.py
      framing.py
      abort.py
      storms.py
      sockets.py
    scpi/
      session.py
      policy.py
      numeric.py
      errors.py
      timing.py
    drivers/
      base.py
      generic.py
      rs/
        sma100b.py
        fsw.py
      profiles/
        schema.toml
        rs_sma100b.toml
        rs_fsw.toml
    safety/
      engine.py
      cal.py
      gating.py
    plan/
      api.py
      context.py
      param.py
      lint.py
    run/
      runner.py
      modes.py
      signals.py
      reconnect.py
      power_guard.py
      watchdog.py
      kill.py
    dataio/
      results_jsonl.py
      trace_raw_jsonl.py
      trace_blobs.py
      export_csv.py
      manifest.py
      headers.py
      durability.py
      rotation.py
      privacy.py
      layout.py
    util/
      config.py
      overlay.py
      time.py
      identity.py
      hashing.py
      logging.py
      cloud_paths.py
      schema.py
      wsl.py
      av_detection.py
      visa_detect.py
      pathlen.py
      net.py
      uris.py
      fw_matcher.py
      envset.py
      baseline.py
  cli/
    main.py
    run.py
    init.py
    kill.py
    discover.py
    validate.py
    doctor.py
    explain.py
    plan_lint.py
  tests/
    unit/
    echo_contract/
    transport_conformance/
    transport_mixed/
    reconnect/
    storms/
    acceptance/
    capability/
    perf/
    durability/
    cancel_correctness/
    schema_compat/
    locale/
    fw_matcher/
  docs/
    install_windows.md
    install_linux.md
    transports.md
    drivers.md
    profiles.md
    calibration.md
    safety_math.md
    troubleshooting.md
    usbtmc_windows_notes.md
    doctor_checks.md
    routes_ipv4_ipv6.md
    offline_wheelhouse.md
    power_policies.md
    cloud_paths.md
    wsl_usage.md
    excel_safe_csv.md
    cancellation_windows.md
    trace_blobs.md
  bench/
    example_bench.toml
    bench.local.template.toml
    cal/
      rf_main.csv
  examples/
    plan_chp.py
    plans/
      starter_pack/
        plan_template.py
        negative_examples/
  scripts/
    bootstrap_windows.ps1
    bootstrap_linux.sh
    verify_wheelhouse.py
    visa_bitness_check.ps1
```

---

## 18) Security and Privacy

* No network listeners or remote endpoints.
* Results from armed runs **auto-relocate** away from cloud paths unless allow-listed; relocation recorded and bannered.
* Privacy filter applies to **all textual fields** across artifacts; numeric/time/bytes preserved.
* Secret scanner blocks commits of secrets.
* Artifact schemas are versioned; CI enforces backward compatibility.

---

## 19) Governance, Versioning, Compatibility

* Semantic versioning for core and drivers.
* **Drivers & profiles**:

  * Drivers remain backward-compatible with prior **profile minor** versions.
  * Profile behavior changes bump **profile minor**; removals bump **major**.
* Compatibility matrix (OS × backend × device × firmware × option set) published per release. **Plugin backends** (e.g., GPIB) are documented separately.
* At runtime, when a bench uses a combination **absent** from the published matrix, the CLI emits a **warning** and records it in the header/manifest.
* Backports: critical transport/safety fixes to **N-1 minor**.
* SBOM and third-party versions recorded; on Windows, **NI-VISA version/CLSID** info is recorded in headers.

---

## 20) Exit Codes (subset)

|                 Class | Code |
| --------------------: | ---: |
|           SafetyError |   20 |
|           ConfigError |   22 |
|        TransportError |   23 |
|        IoTimeoutError |   24 |
|     ScpiProtocolError |   25 |
|  InstrumentStateError |   26 |
|             PlanError |   27 |
|          DoctorFailed |   28 |
| CapabilityProbeFailed |   30 |
|         AbortBySignal |   31 |
|   ProfilePolicyDenied |   32 |
|       RefusedByPolicy |   34 |

---

## 21) Example Device Profiles (Excerpts)

### `rs.sma100b`

```toml
[rs.sma100b]
model = "SMA100B"
numeric_policy = "strict"
rx_terminator = "\n"
max_text_bytes  = 8192
max_block_bytes = 33554432
strip_terminator = true
write_pace_us = 0
firmware_range = ">=4.0.0"
firmware_matcher_vendor = "Rohde&Schwarz"
provenance = { author="eng.team", date="2025-03-18", option_set="all" }

[rs.sma100b.transports.vxi11]
allow = true
chunk_bytes = 65536
opc_timeout_ms = 2500
max_binblock_bytes_proven = 33554432
read_ladder_ms = [20, 50, 100]

[rs.sma100b.transports.usbtmc-ni]
allow = true
chunk_bytes = 32768
opc_timeout_ms = 2500
max_binblock_bytes_proven = 33554432
read_ladder_ms = [20, 50, 100]

[rs.sma100b.completion_defaults]
retune = "opc_query"
rf     = "opc_query"
cfg    = "opc_query"

[rs.sma100b.retry_policy]
idempotent = ["*OPC?","SYST:ERR?","SOUR:FREQ?","SOUR:POW?"]
energizes  = ["SOUR:FREQ","SOUR:POW","OUTP:STAT"]

[rs.sma100b.timeouts]
safe_state_timeout_ms = 2000
```

### `rs.fsw`

```toml
[rs.fsw]
model = "FSW"
numeric_policy = "lenient"  # allows comma decimal, INF/NAN normalized with warnings
rx_terminator = "\n"
max_text_bytes  = 16384
max_block_bytes = 134217728
strip_terminator = true
write_pace_us = 1500
firmware_range = ">=3.0.0"
firmware_matcher_vendor = "Rohde&Schwarz"
provenance = { author="eng.team", date="2025-03-10", option_set="base" }

[rs.fsw.transports.vxi11]
allow = true
chunk_bytes = 65536
opc_timeout_ms = 12000
max_binblock_bytes_proven = 33554432
read_ladder_ms = [30, 60, 120]

[rs.fsw.transports.usbtmc-ni]
allow = true
chunk_bytes = 32768
opc_timeout_ms = 12000
max_binblock_bytes_proven = 33554432
read_ladder_ms = [30, 60, 120]

[rs.fsw.completion_defaults]
sweep = "opc_query"
fetch = "opc_query"
cfg   = "opc_query"

[rs.fsw.quirks]
overrange_flag     = "STAT:QUES:POW:COND?"
def_block_trailer  = "lf"
binary_format_cmds = ["FORM:DATA REAL,32", "FORM:BORD NORM"]

[rs.fsw.timeouts]
safe_state_timeout_ms = 3000

[rs.fsw.analyzer_sensitivity]
nf_dB = 5.0
detector_offset_dB = 0.0
avg_offset_dB = 0.0
snr_margin_dB = 6.0
```

---

## 22) Example Usage Flow

1. Install Python 3.11; run OS bootstrap to create venv and install **hash-pinned** wheels (wheelhouse supported).
2. On Windows, install **NI-VISA**; run `pytaf doctor --quick` to verify **version/bitness/stack ordering** and VXI-11 reachability.
3. `pytaf init` to generate `bench.local.toml` (supports non-interactive flags).
4. Connect instruments (LAN/USBTMC); ensure routing.
5. Place calibration CSVs under `bench/cal/`.
6. `pytaf validate --bench bench/example_bench.toml --plan examples/plan_chp.py`.
7. `pytaf run ... --mode simulate --seed 12345` → `--mode dry-run` → `--mode armed`.
8. Review `export/data.excel.csv`, `export/data.raw.csv`, `results.v1.jsonl`, `results.header.json`, `manifest.v1.json`, `safety_ledger.md`, `trace.raw.v1.jsonl` and `trace_blobs/`.

---


IMPLEMENTATION PHASES / STRATEGY:

---

# PyTAF — Strategic Implementation Phases (Hardened Core v1)

End-to-end plan for a **local, single-engineer, CLI-only** SCPI framework with deterministic cancellation, strict safety, durable artifacts, and profile-scoped determinism. Each phase defines **Goal**, **Scope**, **Deliverables (paths)**, and **Acceptance Gates** split into **PR** (deterministic, fast) and **Nightly** (soak/stress). Hardware-in-the-loop (HIL) jobs run on reserved lab runners; echo/fake transports run on shared CI.

---

## CI / Gating Policy

**PR Gate**

* Pre-commit: ruff/black/isort/mypy; TOML/JSON/schema lint.
* Unit + echo/fake-transport tests.
* Shell matrix cancel tests: Windows (PS7, PS5, cmd.exe, VS Code Terminal), Linux (bash, zsh).
* HIL **smoke** per OS (single vertical slice; ≤60 s each). If HIL is unavailable:

  * **Soft allowance** for up to 24h or 3 consecutive PRs (whichever first), with visible warning and **mandatory** echo/fake “signature” suite.
  * After that, **hard fail**; merges blocked until HIL returns.

**Nightly Gate**

* HIL soaks, cancel stress, durability/atomicity crash tests, locale matrix.
* Performance checks vs **pinned baselines** (P50 of 5 samples, MAD-filtered).
* Schema-compat “museum” enforcement.

---

## Phase 0 — Bootstrap, Constraints, Echo Transport, Repo Skeleton

**Goal**
Reproducible installs, deterministic test bed without VISA, scaffolding for broker/IPC verification.

**Scope**

* `pyproject.toml` with hash-pinned constraints for Py311/312 (Win/Linux).
* Local wheelhouse build/verify scripts.
* Repo skeleton and CI matrices; `TZ=UTC`, `LC_ALL=C`.
* **Echo transport** implementing: deterministic latency, fragmentation, half-close, delayed trailers, binblock simulation, zero-length storms, stuck `*OPC?`, RST-like aborts.
* `pytaf init` (interactive and non-interactive) to create `bench.local.toml`.

**Deliverables**

* `constraints/*`, `scripts/bootstrap_windows.ps1`, `scripts/bootstrap_linux.sh`, `scripts/verify_wheelhouse.py`
* `.pre-commit-config.yaml`, `noxfile.py`, CI workflows
* `src/pytaf/transport/echo.py`, `cli/init.py`
* `tests/echo_contract/*`

**Acceptance Gates**

* **PR:** Fresh clone → offline wheelhouse install with `--require-hashes`; `python -c "import pytaf"` works on both OSes; echo contract and IPC framing tests pass.
* **Nightly:** Wheelhouse integrity: built wheels match pinned hashes.

---

## Phase 1 — Core Runtime, Broker with Priority Lanes, Cancellation, Artifacts & Durability

**Goal**
Deterministic cancellation, per-session I/O isolation with **control vs bulk lanes**, durable artifacts, local-first paths.

**Scope**

* Broker subprocess: owns VISA sessions; **per-session dual-lane queues** (control/bulk) with **preemption points** at chunk/ladder boundaries; budgets; reconnect drill.
* IPC: binary length-delimited with `op_id/epoch/mono_ns`.
* Cancellation: Windows Job Object CTRL\_BREAK→Terminate; Linux INT→TERM→KILL; escalation ladder logging; PID file `{run_uuid}.pid`.
* Artifacts: results JSONL; **CSV (excel + raw)**; **trace JSONL + sidecar binary blobs**; headers; manifest; safety ledger; layout file; **“latest” link**.
* Durability: POSIX `rename+fsync`; Windows `FlushFileBuffers + MoveFileEx(WRITE_THROUGH)`; hidden directory anchor flush.
* **Stale temp sweeper**; **relocation** banner and path on AV/CFA denial.

**Deliverables**

* `src/pytaf/broker/{broker.py,ipc.py,epochs.py,jobobjects_win.py,pidfile.py,lanes.py}`
* `src/pytaf/dataio/{results_jsonl.py,export_csv.py,trace_raw_jsonl.py,trace_blobs.py,headers.py,manifest.py,layout.py,durability.py,rotation.py,privacy.py}`
* `src/pytaf/run/{runner.py,signals.py,watchdog.py,kill.py}`
* `src/pytaf/util/{logging.py,time.py,hashing.py,cloud_paths.py,pathlen.py}`
* `cli/{run.py,kill.py}`

**Acceptance Gates**

* **PR:** Echo/fakes prove soft/hard cancel correctness across shells; forced termination leaves parseable artifacts; sidecar blobs referenced by JSONL; relocation banner emitted on simulated denial; “latest” link created.
* **Nightly:** 1-hour echo soak shows no handle/thread growth; layout hashes consistent; stale temp sweeper blocks startup unless acknowledged.

---

## Phase 2 — Safety Engine (`strict` Default) and Explainability

**Goal**
Absolute-dB safety with uncertainty, analyzer guard, RBW-aware low-power verification, and explainable refusals.

**Scope**

* Calibration ingestion (`freq_Hz,loss_dB[,sigma_dB]`), normalization, freshness; RSS uncertainty; **waiver file** requirement for missing σ or extrapolation.
* Envelope math with `k·σ`; analyzer guard with bench/device caps; **single auto-atten option**; hysteresis latch **persisted** across reconnects.
* Low-power verification and confirm sweep; safety ledger.
* `explain` recomputes math bit-for-bit; embeds inputs, interpolants, checksums.

**Deliverables**

* `src/pytaf/safety/{engine.py,cal.py,gating.py}`, `cli/explain.py`
* Docs: `calibration.md`, `safety_math.md`

**Acceptance Gates**

* **PR:** Deterministic accept/confirm/refuse on fixed benches under `strict`; waiver file enforced; ledger generated; `explain` round-trip matches artifacts.
* **Nightly:** Auto-atten path respects caps, latches persist across reconnect and reset on plan reset; refusals stable across locales.

---

## Phase 3 — VXI-11 Hardware Vertical Slice (SMA100B + FSW), Format-Lock, Reconnect, Baseline Pinning

**Goal**
End-to-end hardware over VXI-11 with strict safety, format-lock, reconnect drill, warm latency/throughput **baseline pinning**.

**Scope**

* `pyvisa-py` VXI-11 transport; portmapper required; **per-resource program-port mapping** allowed with provenance.
* Drivers: R\&S SMA100B (source) and FSW (analyzer).
* Binary format lock; small + medium sanity binblocks; fetches via profile chunking & ladders.
* Reconnect drill; **verify\_outputs\_off()**; low-power gate.
* Baseline pinning: **P50 of 5 consecutive passes within 10 min, MAD-filtered**; store sample count, window, MAD, environment hints.

**Deliverables**

* `src/pytaf/transport/{vxi11_pyvisa.py,framing.py,storms.py}`
* `src/pytaf/drivers/rs/{sma100b.py,fsw.py}`, `src/pytaf/drivers/profiles/{rs_sma100b.toml,rs_fsw.toml}`
* `bench/example_bench.toml`, `examples/plan_chp.py`

**Acceptance Gates**

* **PR (per OS):** CHP 3×3 produces results+CSV+trace; **format-lock enforced** (linter fails if omitted); reconnect + low-power passes; baselines recorded (P50 + MAD).
* **Nightly:** 1/8/32 MiB transfers show 0 truncations; ≥100 open/close cycles; 32 MiB throughput ≥ baseline − 2 MiB/s (median-of-medians, MAD-filtered); warm first-cmd latency ≤ P50 + 250 ms.

---

## Phase 4 — Discover, Validate, Doctor

**Goal**
Strict bench validation and actionable diagnostics.

**Scope**

* Discover: enumerate VISA resources; output canonical URIs.
* Validate: schema lint with JSON Pointer; calibration coverage/age **holes report**; firmware normalization/range/deny; identity/option-set match; capability probes (small + medium fetch; `*OPC?`; overrange path/fallback); **static backend policy checks** (e.g., plugin backends referenced without plugin).
* Doctor: Python/pyvisa presence; **VISA stack ordering & NI-VISA version/bitness** (Windows); USBTMC binding and **udev hotplug** (Linux); VXI-11 reachability; WSL banner; CFA/long-path/path budget; cancellation risk summary; throughput measurement cached; `--patch` emits **commented JSON-Pointer edits**; `--apply` guarded by mtime+hash.

**Deliverables**

* `cli/{discover.py,validate.py,doctor.py}`
* `src/pytaf/util/{visa_detect.py,net.py,wsl.py,av_detection.py,fw_matcher.py,uris.py}`
* Docs: `doctor_checks.md`

**Acceptance Gates**

* **PR:** Misconfigs yield precise JSON Pointer errors; doctor export consistent; pointer patches apply cleanly; backend policy violations caught at validate.
* **Nightly:** Holes report validated with synthetic benches; firmware matcher corpus passes; VISA stack conflicts detected and refused.

---

## Phase 5 — VXI-11 Conformance & Failure Bounding

**Goal**
Zero truncations, bounded failure, deterministic storm behavior, clean reconnect.

**Scope**

* Profile-tuned **read ladders**; **zero-length storm guard** with exponential backoff bounded by budgets and **N diagnostic queries** (per profile).
* Fakes: half-close, delayed trailers, fragmentation, LF-after-large-only, stuck `*OPC?`, ignored terminators.
* Dirty-mark on transport drop; reconnect drill; retries limited to `idempotent=true`.

**Deliverables**

* `src/pytaf/transport/{abort.py,sockets.py}`, tests `tests/transport_conformance/*`, `tests/transport_mixed/*`

**Acceptance Gates**

* **PR:** Fragmentation/trailer/stuck-OPC tests pass; storm guard yields `IoTimeoutError` with diagnostics.
* **Nightly (per OS):** ≥10k transactions (text + 1/8/32 MiB) with **0 hangs/0 truncations**; ≥100 open/close; storm path produces a single bounded diagnostic sequence.

---

## Phase 6 — Runner, Linter, Floors with Amortization, Heartbeat

**Goal**
Deterministic scheduling with hygiene enforcement and deadline predictability.

**Scope**

* `@step`, `@for_each`; resource getters; `ctx.emit`.
* **Dynamic per-call floors** with **amortization credit** within a step; category floors per profile.
* Heartbeat logs (`step_id`, `remaining_ms`, epoch/time).
* Linter rules: missing/unsafe `safe_state`; pre-call floor violations; **binary fetch without format-lock**; **write-only allow-list** per driver; **backend policy violations**.

**Deliverables**

* `src/pytaf/plan/{api.py,context.py,param.py,lint.py}`
* `src/pytaf/run/{signals.py,watchdog.py}`

**Acceptance Gates**

* **PR:** Linter blocks misuse; floors enforced with amortization; cancel tests pass with expected exit codes.
* **Nightly:** 200 abort/reopen cycles; warm post-reconnect first-cmd latency ≤ P50 + 250 ms; no zombie brokers.

---

## Phase 7 — Durability, Rotation, Privacy, CSV Dual-Emit

**Goal**
Durable artifacts under AV/CFA/power loss with predictable write cost and safe human/script outputs.

**Scope**

* Fsync policies: results line-flush + periodic fsync; trace JSONL fsync on rotation; CSV/manifest/headers/ledger/layout fsync on close.
* Guardrails: `max_single_file_mb`, `min_free_space_mb`; proactive refusal on low space.
* Rotation (time/size) with optional **zstd**; **compression stats** recorded in manifest.
* **Privacy filter** for bidi controls and dangerous prefixes across all textual artifacts.
* Relocation to machine-local cache on denial; banner + manifest flags.

**Deliverables**

* Enhancements in `dataio/*`, docs `cloud_paths.md`, `excel_safe_csv.md`, `trace_blobs.md`

**Acceptance Gates**

* **PR:** Forced mid-write/rotation produces parseable artifacts; next run succeeds without manual cleanup; both `export/data.excel.csv` and `export/data.raw.csv` emitted.
* **Nightly:** CFA denial triggers relocation with `{relocated:true}`; compression stats present; trace-rate estimator error ≤ ±15% vs measured EMA.

---

## Phase 8 — Profiles, Drivers Maturation, Capability Cache & Analyzer Fallback

**Goal**
Deterministic device behavior and fast connects with cached, evidenced capabilities.

**Scope**

* Profiles: terminators, trailer, chunk caps, pacing, completion defaults, retune strategy, numeric policy, per-category timeouts incl. `safe_state`, quirks, overrange path, analyzer sensitivity params (+proof metadata), `max_binblock_bytes_proven`, retry flags, **read ladder**.
* Drivers: format-lock watchdog, CHP config, `ready()`, fetch, overrange path, bounded `safe_state()`, \*\*verify\_outputs\_off()\`.
* Capability cache key: `(vendor,model,serial,firmware_norm,option_set,backend,chunk_bytes,ladder_signature)`; TTL and invalidation; **capability proof records** in `capcache.v1.jsonl`.
* Analyzer **fallback detector** for overrange when SCPI path mismatches.

**Deliverables**

* `src/pytaf/drivers/*`, `src/pytaf/drivers/profiles/*`, cache logic and tests.

**Acceptance Gates**

* **PR:** Identity/options mismatch → validate fails; alias override recorded with warning in manifest; initial fetch always binary/trailer-correct.
* **Nightly:** Capability cache hit ratio > 90% on repeated connects; analyzer ready path verified for single/averaged sweeps; fallback detector activates on induced SCPI path change.

---

## Phase 9 — USBTMC Enablement (Linux `pyvisa-py`, Windows NI-VISA)

**Goal**
Cross-OS USBTMC with explicit, supported backends and doctor guarantees.

**Scope**

* Linux: `pyvisa-py` with udev rules; doctor checks group, permissions, and **hotplug reopen**.
* Windows: NI-VISA; doctor verifies **version/bitness** and refuses **mixed VISA stacks**; runtime records VISA version/CLSID.
* Backend selection via `bench.local.toml`; manifest records backend and chunking.

**Deliverables**

* `src/pytaf/transport/{usbtmc_pyvisa_linux.py,usbtmc_ni.py}`, docs `usbtmc_windows_notes.md`, `power_policies.md`

**Acceptance Gates**

* **PR:** Small/medium binblocks succeed per OS/backend; framing sanity verified; doctor detects stack issues.
* **Nightly:**

  * Linux/pyvisa-py: 1/8/32 MiB with 0 truncations; ≥100 open/close; hotplug reopen verified.
  * Windows/NI-VISA: soak mirrors VXI-11 gates; VISA version recorded in headers.

---

## Phase 10 — Stress, Fault Injection, Locale, Atomicity

**Goal**
Robustness under aborts, resets, kills, and locale changes.

**Scope**

* Mid-binblock abort → reconnect → low-power gate; measure **warm** first-cmd latency vs baseline.
* Random kill injection; ≥200 abort/reopen cycles; handle/thread trend monitoring.
* Device TCP RST injection; immediate dirty-mark + reconnect + verify outputs off + low-power gate.
* **Mid-rename kill** asserts atomicity and absence of orphan temps (sweeper test).
* Locale matrix: `de_DE`, `fr_FR`, `ar_EG`, `ja_JP` (comma decimal, RTL, wide chars).
* CSV dot-decimal enforcement and numeric parsing resilience.

**Deliverables**

* `tests/{reconnect,perf,cancel_correctness,locale,durability}`, metrics scripts

**Acceptance Gates**

* **Nightly:** No monotonic handle/thread growth; warm post-reconnect latency ≤ P50 + 250 ms across shells; artifacts intact; CSV dot-decimal preserved across locales; no stale temp unless acknowledged.

---

## Phase 11 — Packaging, Docs, Governance, Release

**Goal**
Consumable distribution with compatibility guarantees and reproducibility.

**Scope**

* Wheels with SBOM; embed constraints metadata; optional signed wheelhouse.
* Docs: install (Win/Linux), VISA selection/ordering, USBTMC binding/udev, transports, drivers/profiles, calibration/uncertainty, safety math, troubleshooting, WSL usage, Excel-safe CSV, cloud relocation, VXI-11 program-port mapping, cancellation semantics, trace sidecars.
* Doctests for `simulate`/`dry-run`; **starter plan pack** with positive/negative examples.
* Schema-compat goldens + schema-diff CI gate.
* Compatibility matrix (OS × backend × device × firmware × option set); runtime **warning** when a bench uses an unlisted combo.

**Deliverables**

* Wheels; docs; `GOVERNANCE.md`, `CONTRIBUTING.md`, `COMPATIBILITY.md`, `RELEASE.md`; schema-diff tool; release CI

**Acceptance Gates**

* **PR:** Doctests pass; “Getting Started” (simulate→dry-run→armed) runs from wheelhouse on both OSes; starter pack lint-clean.
* **Nightly:** Schema-diff gate preserves backward compatibility; published matrix matches tested results; release pipeline produces reproducible wheels.

---

## Phase 12 — Optional Plugin: GPIB “Escape” (Query-Only)

**Goal**
Legacy meters/counters via NI-VISA GPIB with **ASCII query-only**, isolated from core.

**Scope**

* Separate package (wheel): backend `gpib_ni_escape` with canonical URI `pytaf+gpibni://board/addr`.
* **Allowed**: idempotent ASCII queries (`energizes=false`).
* **Refused**: energizing commands, binblocks, oversized writes; linter disallows energize/fetch APIs on escape resources; **static validate** blocks misuse in benches/plans.
* Trace marks `"escape": true` for transactions.

**Deliverables**

* Plugin repo/wheel: `transport/gpib_ni_escape.py`, `drivers/gpib_escape.py`, `drivers/profiles/generic_gpib_escape.toml`; docs `gpib_escape.md`

**Acceptance Gates**

* **PR (plugin):** Queries succeed; energize/binblock attempts → exit **32 (ProfilePolicyDenied)** with clear message; validate catches misuse pre-run.
* **Nightly (plugin):** ≥100 open/close; stable query latency; trace carries `"escape": true`.

---
