"""VPN orchestration via pexpect (replaces vpn-connect.sh)."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pexpect

from . import otp, platform
from .config import get_config
from .dns import get_dns_backend


class VpnSession:
    """Manage a VPN connection lifecycle: start openfortivpn, handle OTP, apply DNS, cleanup."""

    def __init__(self, config=None):
        """
        Initialize VPN session.

        Args:
            config: Configuration dict. If None, loads from ~/.config/af-vpn/config.env.
        """
        if config is None:
            config = get_config()
        self.config = config

        self.process = None
        self.dns_backend = None
        self.os_name = platform.detect_os()

        # VPN_FORTIVPN_BIN from .env, with OS-aware fallback
        self.vpn_binary = config.get(
            "VPN_FORTIVPN_BIN",
            "/opt/homebrew/bin/openfortivpn" if self.os_name == "macos" else "/usr/bin/openfortivpn",
        )

        # Setup signal handlers for cleanup
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle SIGINT/SIGTERM: clean shutdown."""
        print(f"\n[vpn] Received signal {signum}, cleaning up…", file=sys.stderr)
        self.down()
        sys.exit(0)

    def up(self):
        """
        Start VPN connection: spawn openfortivpn, handle OTP prompt, wait for tunnel up, apply DNS.

        Raises:
            RuntimeError: If tunnel fails to come up or OTP fetch fails.
        """
        if not Path(self.vpn_binary).exists():
            raise RuntimeError(
                f"openfortivpn not found: {self.vpn_binary}\n"
                f"Install with: brew install openfortivpn (macOS) or apt install openfortivpn (Linux)"
            )

        print(f"[vpn] Starting openfortivpn ({self.vpn_binary})…", file=sys.stderr)

        # Pass the openfortivpn config file (holds host/user/password)
        vpn_config = self.config.get("VPN_CONFIG")

        cmd = [
            self.vpn_binary,
            f"--config={vpn_config}",
        ]

        try:
            # Spawn openfortivpn process
            self.process = pexpect.spawn(
                cmd[0],
                args=cmd[1:],
                timeout=60,
                encoding="utf-8",
            )

            # Optional: echo the output to stderr for debugging
            # self.process.logfile = sys.stderr

            # Watch for OTP prompt
            print("[vpn] Waiting for OTP prompt…", file=sys.stderr)
            self.process.expect(
                "Two-factor authentication token:",
                timeout=30,
            )
            print("[vpn] OTP prompt detected, fetching OTP…", file=sys.stderr)

            # Drop privileges to real user before calling Playwright
            # (since we're running as root via sudo)
            sudo_user = os.environ.get("SUDO_USER")
            if sudo_user:
                os.setuid(int(subprocess.check_output(["id", "-u", sudo_user]).decode().strip()))

            # Fetch OTP
            otp_code = otp.fetch_otp(self.config)
            if not otp_code:
                raise RuntimeError("Failed to fetch OTP")

            # Send OTP to the prompt
            self.process.sendline(otp_code)
            print(f"[vpn] OTP sent: {otp_code}", file=sys.stderr)

            # Wait for tunnel to come up
            print("[vpn] Waiting for tunnel to come up…", file=sys.stderr)
            self.process.expect(
                "Tunnel is up and running",
                timeout=30,
            )
            print("[vpn] Tunnel is UP!", file=sys.stderr)

            # Apply DNS
            dns_method = self.config.get("VPN_DNS_METHOD", "auto")
            if dns_method == "auto":
                dns_method = platform.pick_dns_method(self.os_name)
            self.config["VPN_DNS_METHOD"] = dns_method

            print(f"[vpn] Applying DNS ({dns_method})…", file=sys.stderr)
            self.dns_backend = get_dns_backend(dns_method, self.config)
            self.dns_backend.apply()

            print("[vpn] VPN is ready!", file=sys.stderr)

        except pexpect.TIMEOUT as e:
            raise RuntimeError(f"Timeout waiting for VPN prompt: {e}")
        except pexpect.EOF as e:
            raise RuntimeError(f"openfortivpn process ended unexpectedly: {e}")
        except Exception as e:
            self.down()
            raise RuntimeError(f"VPN startup failed: {e}")

    def down(self):
        """Stop VPN: terminate openfortivpn, restore DNS."""
        if self.dns_backend:
            print("[vpn] Restoring DNS…", file=sys.stderr)
            try:
                self.dns_backend.restore()
            except Exception as e:
                print(f"[vpn] Warning: DNS restore failed: {e}", file=sys.stderr)
            self.dns_backend = None

        if self.process:
            print("[vpn] Terminating openfortivpn…", file=sys.stderr)
            try:
                self.process.terminate()
                self.process.wait()
            except Exception:
                pass
            self.process = None

        print("[vpn] VPN stopped.", file=sys.stderr)

    def status(self):
        """Check if VPN is up."""
        if self.process and self.process.isalive():
            return "up"
        return "down"
