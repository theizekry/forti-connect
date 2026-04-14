# forti-connect

Automates FortiVPN reconnection with automatic OTP retrieval from Outlook Web.
No manual token copy-paste — connect with a single command.

**Supported:** macOS · Debian · Ubuntu

---

## How It Works

1. Starts `openfortivpn` using your existing config file
2. Detects the OTP prompt automatically
3. Opens Outlook Web (headless browser), finds the OTP email, extracts the 6-digit code
4. Sends the code — tunnel comes up
5. Applies your DNS servers
6. Restores DNS cleanly on disconnect

---

## Install

### One command

```bash
curl -fsSL https://raw.githubusercontent.com/theizekry/forti-connect/main/install.sh | bash
```

Handles everything automatically: Python check, pipx, package, Playwright Firefox, and sudo PATH — on both macOS and Linux.

### Manual install

```bash
pipx install git+https://github.com/theizekry/forti-connect.git
```

Requires Python 3.9+ and [pipx](https://pipx.pypa.io).

---

## Prerequisites

Install `openfortivpn` before running `vpn setup`:

```bash
# macOS
brew install openfortivpn

# Debian / Ubuntu
sudo apt install openfortivpn
```

You also need an **openfortivpn config file** with your VPN credentials:

```ini
# ~/vpn/vpn-config  (you create this, it never leaves your machine)
host = vpn.company.com
port = 443
username = your.username
password = your-password
```

---

## First-Time Setup

Run once after installing:

```bash
vpn setup
```

This will:
1. Ask for the path to your openfortivpn config file
2. Ask for DNS servers and optional settings
3. Save a `.env` to `~/.config/forti-connect/.env`
4. Install Playwright Firefox (~300 MB, one time)
5. Open Outlook Web in a visible browser — log in once to save cookies

---

## Usage

```bash
# Connect
sudo vpn up

# Disconnect
sudo vpn down

# Check tunnel status
vpn status

# Show loaded config
vpn config
```

---

## Configuration

Settings live in `~/.config/forti-connect/.env`.
Credentials stay in your openfortivpn config file — they never touch this file.

```bash
# Path to your openfortivpn config file (holds host/username/password)
VPN_CONFIG=/path/to/vpn-config

# openfortivpn binary (auto-detected if blank)
# macOS default: /opt/homebrew/bin/openfortivpn
# Linux default: /usr/bin/openfortivpn
VPN_FORTIVPN_BIN=

# DNS pushed when tunnel comes up
VPN_DNS_PRIMARY=10.10.0.1
VPN_DNS_SECONDARY=10.10.0.2
VPN_DNS_METHOD=auto          # auto | resolvectl | resolv | networksetup

# OTP email
VPN_OTP_SENDER=DoNotReply@fortinet-notifications.com
VPN_OTP_TIMEOUT=30
VPN_OTP_POLL_INTERVAL=5
VPN_WAIT_BEFORE_INBOX=7

# Browser
VPN_BROWSER_USER_DATA_DIR=~/.vpn-otp-browser-profile
VPN_BROWSER_VISIBLE=false
```

Point to a custom `.env` location:

```bash
VPN_ENV=/path/to/.env sudo vpn up
```

---

## Security

This tool is safe to make available internally. Here is exactly what it does and does not do:

**No secrets in this repository.**
The codebase contains zero credentials, tokens, or passwords.
Your VPN credentials (host, username, password) stay in your own openfortivpn config file on your machine — `forti-connect` only receives the path to that file via `VPN_CONFIG` and passes it directly to `openfortivpn` using the `--config` flag.

**No credentials in `.env`.**
The `.env` file only holds non-sensitive settings (binary path, DNS servers, OTP sender email).
It is excluded from git via `.gitignore` and saved with `chmod 600` (readable only by you).

**No outbound connections from the code.**
The only network activity is: `openfortivpn` connecting to your VPN gateway, and Playwright opening Outlook Web in a browser to read the OTP email.
There are no analytics, telemetry, or external API calls.

**OTP codes are never stored.**
The OTP is read from Outlook, sent to `openfortivpn`, and discarded. It is never written to disk or logged to a file.

**Minimal dependencies.**
Only 3 Python packages: `playwright` (Microsoft), `python-dotenv`, and `pexpect` — all widely used and auditable.

**Privilege handling.**
`sudo` is required only because `openfortivpn` needs root to create a tunnel interface.
Before launching the Outlook browser, the tool drops privileges back to your real user (`SUDO_USER`) so Playwright never runs as root.

**install.sh is auditable.**
The installer script is in this repository. You can read it before running it:
```bash
curl -fsSL https://raw.githubusercontent.com/theizekry/forti-connect/main/install.sh | less
```

---

## Updating

```bash
pipx upgrade forti-connect
```

---

## Troubleshooting

**`vpn` not found after install**
Restart your terminal or run `source ~/.zshrc` (or `~/.bashrc`).

**`sudo vpn up` says command not found**
The installer writes `/etc/sudoers.d/af-vpn` to fix this automatically.
If it failed, run the installer again or add it manually:
```bash
sudo visudo -f /etc/sudoers.d/af-vpn
# Add: Defaults secure_path="<dirname of vpn binary>:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
```

**`openfortivpn` not found**
```bash
brew install openfortivpn      # macOS
sudo apt install openfortivpn  # Linux
```

**OTP fetch timed out**
Outlook cookies may have expired. Re-login:
```bash
vpn setup
```

**VPN connects but DNS is wrong**
Check `VPN_DNS_PRIMARY` / `VPN_DNS_SECONDARY` in `~/.config/forti-connect/.env`.
Force a specific method: `VPN_DNS_METHOD=resolvectl` (Linux) or `VPN_DNS_METHOD=networksetup` (macOS).

---

## Development

```bash
git clone https://github.com/theizekry/forti-connect.git
cd forti-connect
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```
