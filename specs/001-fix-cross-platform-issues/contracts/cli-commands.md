# CLI Command Contracts

## `vpn up`

- Requires root (`sudo`)
- Spawns `openfortivpn --config=<VPN_CONFIG>`
- On OTP prompt: fetches 6-digit code from Outlook Web (as `$SUDO_USER`)
- After tunnel up: applies DNS via platform-appropriate backend
- Exit 0 on success; exit 1 on any failure

## `vpn down`

- Requires root (`sudo`)
- Sends SIGTERM to all `openfortivpn` PIDs
- Restores DNS
- Exit 0 always (best-effort teardown)

## `vpn status`

- No root required
- Prints `Status: UP` or `Status: DOWN` to stdout
- On Linux only: if UP, also prints `Interface: <VPN_VPN_INTERFACE>`
- Exit 0 always (no crash on either platform)

## `vpn setup`

- No root required
- Interactive: prompts for `VPN_CONFIG` path, optional settings
- Default binary: `/opt/homebrew/bin/openfortivpn` (macOS) or `/usr/bin/openfortivpn` (Linux)
- Writes `~/.config/af-vpn/.env` with mode 600
- Runs `playwright install firefox`
- Opens Outlook Web for one-time login

## `vpn config`

- No root required
- Prints path to loaded `.env` and all config keys
- No password redaction (no passwords are stored in `.env`)
- Exit 1 if no `.env` found

## DNS Backend Contracts

### ResolvectlBackend (Linux, systemd-resolved)

```
apply:   resolvectl dns <VPN_VPN_INTERFACE> <server1> [<server2>]
restore: resolvectl dns <VPN_VPN_INTERFACE> --reset
```
No `sudo` prefix (caller is already root).

### NetworksetupBackend (macOS)

```
apply:   networksetup -setdnsservers <service> <server1> [<server2> ...]
restore: networksetup -setdnsservers <service> Empty
```
DNS servers are separate positional arguments, not a space-joined string.

### ResolvBackend (Linux fallback, /etc/resolv.conf)

```
apply:   backup /etc/resolv.conf → /tmp/af-vpn-dns/resolv.conf.backup
         write new nameserver lines to /etc/resolv.conf
restore: cp /tmp/af-vpn-dns/resolv.conf.backup /etc/resolv.conf
```
