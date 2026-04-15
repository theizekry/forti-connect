"""CLI entry point (argparse subcommands)."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import log, otp, platform
from .config import config_path, get_config, load_config
from .vpn import VpnSession


def check_root():
    """Ensure running as root (via sudo)."""
    if os.geteuid() != 0:
        print(
            "Error: This command requires root privileges.\n"
            "Try: sudo vpn up",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_up(args):
    """vpn up — Start VPN connection."""
    check_root()
    try:
        session = VpnSession()
        session.up()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_down(args):
    """vpn down — Stop VPN connection."""
    check_root()
    try:
        # Find and kill any running openfortivpn process
        result = subprocess.run(
            ["pgrep", "-f", "openfortivpn"],
            capture_output=True,
            text=True,
        )
        if result.stdout:
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                try:
                    os.kill(int(pid), 15)  # SIGTERM
                    log.info(f"Killed openfortivpn (PID {pid})")
                except Exception as e:
                    log.warn(f"Failed to kill PID {pid}: {e}")

        # Restore DNS
        try:
            config = get_config()
            dns_method = config.get("VPN_DNS_METHOD", "auto")
            if dns_method == "auto":
                dns_method = platform.pick_dns_method()
            from .dns import get_dns_backend
            dns = get_dns_backend(dns_method, config)
            dns.restore()
            log.ok("DNS restored")
        except Exception as e:
            log.warn(f"DNS restore failed: {e}")

        log.ok("VPN stopped")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_status(args):
    """vpn status — Check VPN connection status."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "openfortivpn"],
            capture_output=True,
        )
        if result.returncode == 0:
            print("Status: UP")
            # Try to show tunnel interface (Linux only — macOS lacks `ip`)
            if platform.detect_os() == "linux":
                try:
                    config = get_config()
                    iface = config.get("VPN_VPN_INTERFACE", "ppp0")
                    r2 = subprocess.run(
                        ["ip", "link", "show", iface],
                        capture_output=True,
                        text=True,
                    )
                    if r2.returncode == 0:
                        print(f"Interface: {iface}")
                except Exception:
                    pass
        else:
            print("Status: DOWN")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_setup(args):
    """vpn setup — Interactive first-run setup."""
    from .config import env_path as find_env

    print("\n=== forti-connect Setup ===\n")

    # Determine .env location
    default_env = Path.home() / ".config" / "forti-connect" / ".env"
    try:
        existing = find_env()
        print(f"Existing .env found: {existing}")
        response = input("Reconfigure? (y/n): ").strip().lower()
        if response != "y":
            print("Skipped.")
            return
        cfg_path = existing
    except FileNotFoundError:
        cfg_path = default_env

    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # Only need the path to the openfortivpn config (secrets stay there)
    print("\nWhere is your openfortivpn config file?")
    print("(This file holds host/username/password in openfortivpn format)")
    vpn_config = input(f"VPN_CONFIG path: ").strip()

    if not vpn_config or not Path(vpn_config).expanduser().exists():
        print(f"Warning: path '{vpn_config}' does not exist yet — you can edit the .env later.", file=sys.stderr)

    # Optional settings
    _default_bin = (
        "/opt/homebrew/bin/openfortivpn"
        if platform.detect_os() == "macos"
        else "/usr/bin/openfortivpn"
    )
    print("\nOptional settings (press Enter to keep defaults):")
    fortivpn_bin = input(
        f"openfortivpn binary [{_default_bin}]: "
    ).strip() or _default_bin
    dns_primary = input("Primary DNS [leave blank to skip]: ").strip()
    dns_secondary = input("Secondary DNS [leave blank to skip]: ").strip()
    otp_sender = input(
        "OTP sender email [DoNotReply@fortinet-notifications.com]: "
    ).strip() or "DoNotReply@fortinet-notifications.com"

    # Build .env content
    lines = [
        "# forti-connect configuration",
        f"VPN_FORTIVPN_BIN={fortivpn_bin}",
        f"VPN_CONFIG={vpn_config}",
        "",
        "# DNS",
    ]
    if dns_primary:
        lines.append(f"VPN_DNS_PRIMARY={dns_primary}")
    if dns_secondary:
        lines.append(f"VPN_DNS_SECONDARY={dns_secondary}")
    lines += [
        "VPN_DNS_METHOD=auto",
        "VPN_VPN_INTERFACE=ppp0",
        "",
        "# OTP email",
        f"VPN_OTP_SENDER={otp_sender}",
        "VPN_OTP_TIMEOUT=30",
        "VPN_OTP_POLL_INTERVAL=5",
        "VPN_WAIT_BEFORE_INBOX=7",
        "",
        "# Browser (Playwright Firefox)",
        f"VPN_BROWSER_USER_DATA_DIR={Path.home() / '.vpn-otp-browser-profile'}",
        "VPN_BROWSER_VISIBLE=false",
        "",
    ]

    with open(cfg_path, "w") as f:
        f.write("\n".join(lines))
    cfg_path.chmod(0o600)
    print(f"\n✓ .env saved to {cfg_path}")

    # Install Playwright Firefox
    print("\nInstalling Playwright Firefox (this may take a minute)…")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "firefox"],
            check=True,
        )
        print("✓ Playwright Firefox installed")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Playwright install failed: {e}", file=sys.stderr)
        print("Run manually: playwright install firefox", file=sys.stderr)

    # Setup Outlook login
    print("\nOpening Outlook Web for one-time login…")
    print("Log in to Outlook in the browser that opens, then close it.")
    try:
        cfg = get_config(cfg_path)
        otp.open_browser_for_login(cfg)
        print("✓ Outlook browser session saved — you can now run: sudo vpn up")
    except Exception as e:
        print(f"Warning: Outlook setup failed: {e}", file=sys.stderr)
        print("Run 'vpn setup' again to retry.", file=sys.stderr)

    # Sudoers hint
    print("\n=== Sudoers Setup ===")
    print("To use 'sudo vpn up' without PATH issues, run once:")
    print(f"\n  sudo visudo -f /etc/sudoers.d/forti-connect")
    print(f"  # Add: Defaults secure_path=\"{Path.home()}/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\"")
    print("\nSetup complete! Run: sudo vpn up")


def cmd_login(args):
    """vpn login — Open Outlook Web to refresh the browser session (re-login)."""
    try:
        config = get_config()
        otp.open_browser_for_login(config)
        print("✓ Browser session saved.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config(args):
    """vpn config — Show current configuration."""
    from .config import env_path
    try:
        path = env_path()
        config = get_config()
        print(f".env: {path}")
        print("\nConfiguration:")
        for key, value in sorted(config.items()):
            print(f"  {key}={value}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="vpn",
        description="forti-connect: Automated FortiVPN with OTP",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # vpn up
    subparsers.add_parser("up", help="Start VPN connection (requires sudo)")

    # vpn down
    subparsers.add_parser("down", help="Stop VPN connection (requires sudo)")

    # vpn status
    subparsers.add_parser("status", help="Check VPN connection status")

    # vpn setup
    subparsers.add_parser("setup", help="Interactive first-run setup")

    # vpn login
    subparsers.add_parser("login", help="Re-open Outlook Web to refresh browser session")

    # vpn config
    subparsers.add_parser("config", help="Show current configuration")

    args = parser.parse_args()

    if args.command == "up":
        cmd_up(args)
    elif args.command == "down":
        cmd_down(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "login":
        cmd_login(args)
    elif args.command == "config":
        cmd_config(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
