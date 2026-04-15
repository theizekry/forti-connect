# Implementation Plan: Fix Cross-Platform Runtime Bugs and Failing Tests

**Branch**: `001-fix-cross-platform-issues` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-fix-cross-platform-issues/spec.md`

## Summary

Fix 5 runtime bugs that break the tool on Linux and macOS, and correct 4 failing
tests caused by stale mock targets and a missing password-redaction feature that
shouldn't exist. No new features — only correctness.

## Technical Context

**Language/Version**: Python 3.9+  
**Primary Dependencies**: pexpect, playwright, python-dotenv  
**Storage**: N/A (flat .env config file)  
**Testing**: pytest  
**Target Platform**: Linux (Debian/Ubuntu) + macOS  
**Project Type**: CLI tool  
**Performance Goals**: N/A  
**Constraints**: No new dependencies; must not break existing passing tests  
**Scale/Scope**: Single-user local CLI

## Constitution Check

*Constitution file is a blank template — no project-specific gates apply.*

All changes are pure bug fixes: no new abstractions, no new files (except tests),
no scope creep. Gate status: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-cross-platform-issues/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (N/A — no data model changes)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/forti_connect/
├── cli.py       # Bug fixes: cmd_status macOS, cmd_setup default binary, otp import
├── dns.py       # Bug fixes: NetworksetupBackend args, ResolvectlBackend interface + sudo
├── vpn.py       # No changes needed

tests/
├── test_cli.py  # Fix 3 stale/broken tests
├── test_vpn.py  # Fix 1 stale test
```

**Structure Decision**: Single project, existing layout — no structural changes.

---

## Phase 0: Research

### Findings

All issues were identified directly from code inspection + test run. No external research needed.

**Decision**: Fix in-place without introducing new abstractions.  
**Rationale**: Every bug is a 1–5 line fix; no shared logic to extract.  
**Alternatives considered**: Creating a `PlatformHelper` utility class — rejected (YAGNI).

---

## Phase 1: Fix Plan

### Bug Fix 1 — `ResolvectlBackend`: use configured interface, drop redundant `sudo`

**File**: `src/forti_connect/dns.py`  
**Problem**: Hardcodes `tun0` in `resolvectl dns tun0 <server>`. Config ships
`VPN_VPN_INTERFACE=ppp0` but it is never read by DNS backends. Also calls
`sudo resolvectl` when `vpn up` is already running as root — redundant.  
**Fix**:
- Accept `interface` from `config.get("VPN_VPN_INTERFACE", "ppp0")` in `ResolvectlBackend.__init__`
- Remove `sudo` prefix from `subprocess.run` calls (already root)
- Same interface fix for restore command

### Bug Fix 2 — `NetworksetupBackend.apply()`: pass DNS servers as separate args

**File**: `src/forti_connect/dns.py`  
**Problem**: `networksetup -setdnsservers <service> "1.1.1.1 1.0.0.1"` passes
all servers as one argument — macOS expects them as separate positional args.  
**Fix**: Replace `dns_str = " ".join(...)` + single arg with `*self.dns_servers`
spread: `["networksetup", "-setdnsservers", self.service] + self.dns_servers`

### Bug Fix 3 — `cmd_status`: platform-aware tunnel interface check

**File**: `src/forti_connect/cli.py`  
**Problem**: `cmd_status` uses `ip link show tun0` — `ip` does not exist on macOS.  
**Fix**:
- Detect OS via `platform.detect_os()`
- On macOS: use `ifconfig ppp0` (or skip the interface check entirely — status
  based only on `pgrep openfortivpn`)
- On Linux: keep `ip link show` but read interface from config

### Bug Fix 4 — `cmd_setup`: use OS-correct default binary path

**File**: `src/forti_connect/cli.py`  
**Problem**: Setup prompt defaults to `/opt/homebrew/bin/openfortivpn` on all
platforms.  
**Fix**: Detect OS and default to `/usr/bin/openfortivpn` on Linux,
`/opt/homebrew/bin/openfortivpn` on macOS.

### Bug Fix 5 — `cmd_setup`: move `otp` import to module level

**File**: `src/forti_connect/cli.py`  
**Problem**: `from . import otp` is inside `cmd_setup()`, so
`patch("forti_connect.cli.otp")` fails with AttributeError.  
**Fix**: Move the import to the top of `cli.py` alongside the other imports.

---

## Test Fixes

### Test Fix 1 — `test_vpn.py::test_spawns_openfortivpn_with_correct_args`

**Problem**: Test asserts `--host=vpn.test.com` and `--username=testuser` are
in `pexpect.spawn` args, but `vpn.up()` now uses `--config=<file>` and reads
credentials from that file via openfortivpn.  
**Fix**: Remove the stale host/username assertions; instead assert that
`--config=` is passed and that `pexpect.spawn` was called. Also remove the mock
for `os.setuid` and `subprocess.check_output` which no longer exist in the code.

### Test Fix 2 — `test_cli.py::test_prints_config`

**Problem**: `cmd_config` calls `env_path()` to display the path, then
`get_config()`. The test mocks `get_config` but not `env_path`, so
`env_path()` raises FileNotFoundError.  
**Fix**: Also patch `forti_connect.cli.env_path` (imported as `from .config
import env_path`) to return a dummy path. The test should assert that config
keys from the mock appear in output.

### Test Fix 3 — `test_cli.py::test_redacts_password`

**Problem**: Tests that `VPN_PASSWORD` value `testpass` is redacted to `***`.
The real config never contains `VPN_PASSWORD` (credentials are in the
openfortivpn config file). This feature was never implemented and is not needed.  
**Fix**: Remove the `test_redacts_password` test. The `mock_config` fixture also
holds `VPN_GATEWAY`, `VPN_USER`, `VPN_PASSWORD` — remove those too since they
reflect an older architecture and pollute tests.

### Test Fix 4 — `test_cli.py::test_creates_config_directory`

**Problem**: Patches `forti_connect.cli.otp` which doesn't exist at module level
(import is inside the function).  
**Fix**: After moving `from . import otp` to module level (Bug Fix 5), the
patch target resolves correctly. Update the patch to the correct new path.

---

## Complexity Tracking

No constitution violations — all fixes are minimal, surgical, in-place changes.

---

## Post-Design Constitution Check

PASS — changes reduce complexity (remove stale mocks, fix platform divergence),
add no new abstractions, and do not change the public CLI contract.
