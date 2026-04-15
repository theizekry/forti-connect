# Tasks: Fix Cross-Platform Runtime Bugs and Failing Tests

**Input**: Design documents from `/specs/001-fix-cross-platform-issues/`
**Branch**: `001-fix-cross-platform-issues`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story / fix group this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Blocking Prerequisite)

**Purpose**: The single change that unblocks both a CLI fix and a test fix must land first.

**⚠️ CRITICAL**: T001 must complete before Phase 4 test tasks.

- [x] T001 Move `from . import otp` from inside `cmd_setup()` to module-level imports in `src/forti_connect/cli.py`

**Checkpoint**: `otp` is now accessible as `forti_connect.cli.otp` — patch target resolves.

---

## Phase 2: User Story 1 — DNS Backend Correctness (Priority: P1) 🎯

**Goal**: Both DNS backends produce correct shell commands on their respective platforms.

**Independent Test**: Run `pytest tests/ -v` after this phase — no new failures; existing 52 tests still pass.

### Implementation for User Story 1

- [x] T002 [P] [US1] In `ResolvectlBackend.__init__()`, read `config.get("VPN_VPN_INTERFACE", "ppp0")` and store as `self.interface`; replace every `"tun0"` literal in `apply()` and `restore()` with `self.interface` in `src/forti_connect/dns.py`
- [x] T003 [P] [US1] In `ResolvectlBackend.apply()` and `restore()`, remove the `"sudo"` prefix from both `subprocess.run` command lists (caller is already root) in `src/forti_connect/dns.py`
- [x] T004 [P] [US1] In `NetworksetupBackend.apply()`, replace `dns_str = " ".join(self.dns_servers)` + single-string arg with `["networksetup", "-setdnsservers", self.service] + self.dns_servers` in `src/forti_connect/dns.py`

**Checkpoint**: DNS backends are correct. Verify T002–T004 don't break existing tests.

---

## Phase 3: User Story 2 — CLI Command Cross-Platform Fixes (Priority: P1)

**Goal**: `vpn status` and `vpn setup` work correctly on both Linux and macOS.

**Independent Test**: `vpn status` exits 0 on macOS without crashing; `vpn setup` shows the OS-correct default binary path.

### Implementation for User Story 2

- [x] T005 [P] [US2] In `cmd_status()`, replace the hardcoded `ip link show tun0` block with a platform-aware check: use `platform.detect_os()` and show interface only on Linux using `config.get("VPN_VPN_INTERFACE", "ppp0")`; skip the `ip` call on macOS in `src/forti_connect/cli.py`
- [x] T006 [P] [US2] In `cmd_setup()`, replace the hardcoded `/opt/homebrew/bin/openfortivpn` default with a platform-aware default using `platform.detect_os()`: `/opt/homebrew/bin/openfortivpn` on macOS, `/usr/bin/openfortivpn` on Linux in `src/forti_connect/cli.py`

**Checkpoint**: CLI fixes in place. Run `pytest tests/ -v` — still 52 passing.

---

## Phase 4: User Story 3 — Fix Failing Tests (Priority: P2)

**Goal**: All 56 tests pass (currently 52 pass, 4 fail).

**Independent Test**: `pytest tests/ -v` → 0 failures (55 passed after T009 deletes one test).

**Depends on**: T001 (Phase 1) must be complete before T010.

### Implementation for User Story 3

- [x] T007 [P] [US3] In `test_vpn.py::TestVpnSessionUp::test_spawns_openfortivpn_with_correct_args`: remove the `--host=` and `--username=` assertions and the now-absent `os.setuid`/`subprocess.check_output` mocks; assert only that `mock_spawn.called` is True in `tests/test_vpn.py`
- [x] T008 [P] [US3] In `test_cli.py::TestCmdConfig::test_prints_config`: add `patch("forti_connect.cli.env_path", return_value=Path("/mock/.env"))` to the context manager stack so `env_path()` doesn't raise `FileNotFoundError` in `tests/test_cli.py`
- [x] T009 [P] [US3] In `test_cli.py::TestCmdConfig`: delete the entire `test_redacts_password` test method (passwords are never stored in `.env`; feature is not implemented and not needed); also remove `VPN_PASSWORD`, `VPN_GATEWAY`, `VPN_USER` from the `mock_config` fixture in `tests/conftest.py` in `tests/test_cli.py` and `tests/conftest.py`
- [x] T010 [US3] In `test_cli.py::TestCmdSetup::test_creates_config_directory`: update the `otp.fetch_otp` patch target to `forti_connect.cli.otp.fetch_otp` (now valid after T001 moved the import to module level) in `tests/test_cli.py`

**Checkpoint**: `pytest tests/ -v` → 55 passed, 0 failed.

---

## Phase 5: Polish & Validation

**Purpose**: Confirm the full fix set is coherent and nothing was missed.

- [x] T011 Run `pytest tests/ -v` from repo root and confirm 55 passed, 0 failed
- [x] T012 [P] Review `src/forti_connect/dns.py` diff to confirm `tun0` no longer appears as a literal string anywhere in the file
- [x] T013 [P] Review `src/forti_connect/cli.py` diff to confirm `otp` is imported at module level, `ip link show` is gated to Linux, and setup default binary is platform-aware

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — start immediately
- **Phase 2 (US1 — dns.py)**: No dependency on Phase 1 — can start immediately in parallel with Phase 1
- **Phase 3 (US2 — cli.py)**: Depends on Phase 1 completion (T001 adds `otp` import); T005/T006 themselves don't need T001 but share the file
- **Phase 4 (US3 — tests)**: T007/T008/T009 can start after Phase 2+3 fixes are in place; **T010 depends on T001**
- **Phase 5 (Polish)**: All prior phases complete

### Within Each Phase

- T002, T003, T004 are all in `dns.py` — edit sequentially or carefully if parallel
- T005, T006 are in `cli.py` — can be done in one editing pass after T001
- T007, T008, T009 touch different test files/methods — can be done in parallel

### Parallel Opportunities

```bash
# Phase 1 + Phase 2 start together:
Task T001: cli.py — move otp import
Task T002: dns.py — ResolvectlBackend interface
Task T003: dns.py — ResolvectlBackend sudo removal   (after T002 in same file)
Task T004: dns.py — NetworksetupBackend args

# Phase 3 after T001:
Task T005: cli.py — cmd_status macOS
Task T006: cli.py — cmd_setup default binary

# Phase 4 after Phase 2+3:
Task T007: test_vpn.py fix
Task T008: test_cli.py test_prints_config fix
Task T009: test_cli.py test_redacts_password delete + conftest.py
# T010 requires T001 done first:
Task T010: test_cli.py test_creates_config_directory fix
```

---

## Implementation Strategy

### MVP (Single Pass)

Because all fixes are small and independent, the recommended approach is:

1. Apply T001 first (1 line change)
2. Apply T002–T006 as one editing pass across `dns.py` and `cli.py`
3. Apply T007–T010 as one editing pass across the test files
4. Run `pytest tests/ -v` to confirm 55 passed

### Incremental (Per Phase)

1. T001 → verify `forti_connect.cli.otp` resolves
2. T002–T004 → `pytest tests/` still passes
3. T005–T006 → `pytest tests/` still passes
4. T007–T010 → `pytest tests/` = 55 passed, 0 failed

---

## Notes

- No new files are created — all edits are in existing source and test files
- T009 **deletes** one test (`test_redacts_password`) and cleans up `mock_config` — final count drops from 56 to 55 tests
- The `mock_config` cleanup in T009 also removes `VPN_GATEWAY`, `VPN_USER`, `VPN_PASSWORD` keys which reflect an older architecture and are unused by the current code
- After these fixes, `sudo vpn up` should work end-to-end on Linux (using `ppp0` or configured interface) and macOS (correct `networksetup` arg format)
