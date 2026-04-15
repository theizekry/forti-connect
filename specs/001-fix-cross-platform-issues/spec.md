---
feature: Fix cross-platform runtime bugs and failing tests
branch: 001-fix-cross-platform-issues
date: 2026-04-15
---

# Fix Cross-Platform Runtime Bugs and Failing Tests

## Problem

The tool has several bugs that break it on Linux and/or macOS at runtime, and the
test suite has 4 failing tests due to stale mocks and unimplemented features.

## Current Failures

### Failing Tests (4)

| Test | Root Cause |
|------|------------|
| `test_vpn.py::test_spawns_openfortivpn_with_correct_args` | Stale: checks for `--host`/`--username` args, but code now uses `--config=<file>` |
| `test_cli.py::test_prints_config` | `cmd_config` calls `env_path()` which isn't mocked; test only mocks `get_config` |
| `test_cli.py::test_redacts_password` | `cmd_config` has no password redaction; test expects `***` but there are no passwords in `.env` |
| `test_cli.py::test_creates_config_directory` | `otp` is imported inside `cmd_setup` function, not at module level — `patch("forti_connect.cli.otp")` fails |

### Runtime Bugs

| Module | Issue | Platform |
|--------|-------|----------|
| `cli.py:cmd_status` | Uses `ip link show tun0` — `ip` doesn't exist on macOS | macOS |
| `dns.py:NetworksetupBackend.apply()` | Passes DNS servers as a joined string (single arg) instead of separate args | macOS |
| `dns.py:ResolvectlBackend` | Hardcodes `tun0` interface — config says `VPN_VPN_INTERFACE=ppp0` but DNS backends ignore it | Linux |
| `dns.py:ResolvectlBackend` | Calls `sudo resolvectl` when already running as root — redundant and fragile | Linux |
| `cli.py:cmd_setup` | Defaults binary to `/opt/homebrew/bin/openfortivpn` regardless of OS | Linux |

## Goals

1. All 56 tests pass (currently 52 pass, 4 fail)
2. `sudo vpn up` works end-to-end on Linux (ppp0/tun0 interface, resolvectl or resolv)
3. `sudo vpn up` works end-to-end on macOS (networksetup DNS with correct arg format)
4. `vpn status` works on both platforms without crashing
5. `vpn setup` shows OS-correct default binary path

## Non-Goals

- No new features
- No refactoring beyond what is needed to fix the bugs
- No changes to the install.sh flow (already fixed in prior commits)

## Success Criteria

- `pytest tests/ -v` → 0 failures
- `vpn status` on macOS doesn't crash with `ip: command not found`
- `networksetup -setdnsservers` receives DNS servers as separate arguments
- `resolvectl dns` targets the interface from `VPN_VPN_INTERFACE` config
- `vpn setup` suggests `/usr/bin/openfortivpn` as default on Linux
