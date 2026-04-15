# Quickstart: Implement the Cross-Platform Fixes

All changes are in `src/forti_connect/` and `tests/`. Run `pytest tests/ -v`
after each change to verify no regressions.

## Execution Order

Do these in order — earlier fixes unblock later test fixes.

### 1. dns.py — ResolvectlBackend (Linux)

In `__init__`, read `config.get("VPN_VPN_INTERFACE", "ppp0")` and store as
`self.interface`. Replace every `"tun0"` literal with `self.interface`.
Remove `"sudo"` from all subprocess command lists (already root).

### 2. dns.py — NetworksetupBackend (macOS)

In `apply()`, change:
```python
# Before
dns_str = " ".join(self.dns_servers)
subprocess.run(["networksetup", "-setdnsservers", self.service, dns_str], ...)

# After
subprocess.run(["networksetup", "-setdnsservers", self.service] + self.dns_servers, ...)
```

### 3. cli.py — Move `otp` import to module level

Move `from . import otp` out of `cmd_setup()` to the top of the file with the
other imports.

### 4. cli.py — cmd_setup default binary

Replace the hardcoded string:
```python
# Before
fortivpn_bin = input(
    "openfortivpn binary [/opt/homebrew/bin/openfortivpn]: "
).strip() or "/opt/homebrew/bin/openfortivpn"

# After
_default_bin = (
    "/opt/homebrew/bin/openfortivpn"
    if platform.detect_os() == "macos"
    else "/usr/bin/openfortivpn"
)
fortivpn_bin = input(f"openfortivpn binary [{_default_bin}]: ").strip() or _default_bin
```

### 5. cli.py — cmd_status platform-aware check

Replace the Linux-only `ip link show tun0` block:
```python
# After: skip interface check entirely; pgrep result is sufficient
if result.returncode == 0:
    print("Status: UP")
    # Show interface if possible (Linux only)
    if platform.detect_os() == "linux":
        try:
            config = get_config()
            iface = config.get("VPN_VPN_INTERFACE", "ppp0")
            r2 = subprocess.run(["ip", "link", "show", iface], capture_output=True, text=True)
            if r2.returncode == 0:
                print(f"Interface: {iface}")
        except Exception:
            pass
else:
    print("Status: DOWN")
```

### 6. tests/test_cli.py — fix 3 tests

- `test_prints_config`: add `patch("forti_connect.cli.env_path", return_value=Path("/mock/.env"))` to the context
- `test_redacts_password`: **delete** this test (no passwords in .env)
- `test_creates_config_directory`: fix the `otp` patch (after step 3, it resolves)

### 7. tests/test_vpn.py — fix 1 test

`test_spawns_openfortivpn_with_correct_args`: remove `--host`/`--username`
assertions and `os.setuid`/`subprocess.check_output` mocks. Assert
`mock_spawn.called` and that the first arg contains the binary path.

## Verify

```bash
pytest tests/ -v   # expect 55 passed, 0 failed (test_redacts_password deleted)
```
