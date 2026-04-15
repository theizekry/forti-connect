"""VPN orchestration via pexpect (replaces vpn-connect.sh)."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pexpect

from . import log, otp, platform
from .log import BOLD
from .config import get_config
from .dns import get_dns_backend


class VpnSession:
    """Manage a VPN connection lifecycle: start openfortivpn, handle OTP, apply DNS, cleanup."""

    def __init__(self, config=None):
        """
        Initialize VPN session.

        Args:
            config: Configuration dict. If None, loads from ~/.config/forti-connect/.env.
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
        log.warn("Disconnecting…")
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

        log.info(f"Starting openfortivpn ({self.vpn_binary})…")

        # Pass the openfortivpn config file (holds host/user/password)
        vpn_config = self.config.get("VPN_CONFIG")

        cmd = [
            self.vpn_binary,
            f"--config={vpn_config}",
        ]

        tunnel_up = False
        try:
            # Spawn openfortivpn process
            self.process = pexpect.spawn(
                cmd[0],
                args=cmd[1:],
                timeout=60,
                encoding="utf-8",
            )

            log.info("Connecting to VPN gateway…")
            self.process.expect(
                "Two-factor authentication token:",
                timeout=30,
            )
            log.info("OTP requested — fetching from Outlook…")

            # Fetch OTP — run as the real user (not root) so Playwright works correctly
            sudo_user = os.environ.get("SUDO_USER")
            if sudo_user:
                otp_code = self._fetch_otp_as_user(sudo_user)
            else:
                otp_code = otp.fetch_otp(self.config)
            if not otp_code:
                raise RuntimeError("Failed to fetch OTP")

            log.info(f"Submitting OTP: {BOLD}{otp_code}{log.RESET}")
            self.process.sendline(otp_code)

            log.dim("Establishing tunnel…")
            self.process.expect(
                "Tunnel is up and running",
                timeout=30,
            )
            tunnel_up = True
            log.ok("Tunnel is up and running.")

            # Apply DNS
            dns_method = self.config.get("VPN_DNS_METHOD", "auto")
            if dns_method == "auto":
                dns_method = platform.pick_dns_method(self.os_name)
            self.config["VPN_DNS_METHOD"] = dns_method

            log.info(f"Applying DNS via {dns_method}…")
            self.dns_backend = get_dns_backend(dns_method, self.config)
            try:
                self.dns_backend.apply()
                for server in self.dns_backend.dns_servers:
                    log.dim(f"Nameserver: {server}")
            except Exception as dns_err:
                log.warn(f"DNS apply failed: {dns_err}")
                log.warn("Set VPN_DNS_METHOD=resolv in your .env to fix")
                self.dns_backend = None

            log.ok("VPN connected — press Ctrl+C to disconnect.")

            # Block here — keep the PTY open so openfortivpn stays alive.
            # When the user Ctrl+C's, the signal handler calls self.down().
            self.process.expect(pexpect.EOF, timeout=None)

        except pexpect.TIMEOUT as e:
            self.down()
            raise RuntimeError(f"Timeout waiting for VPN prompt: {e}")
        except pexpect.EOF as e:
            self.down()
            if tunnel_up:
                raise RuntimeError(f"VPN connection lost: {e}")
            raise RuntimeError(f"openfortivpn exited unexpectedly during startup: {e}")
        except Exception as e:
            self.down()
            raise RuntimeError(f"VPN startup failed: {e}")

    def _fetch_otp_as_user(self, sudo_user):
        """Run OTP fetch in a subprocess as the real (non-root) user.

        Uses sudo -u to preserve the correct HOME and permissions for the
        Playwright browser profile while keeping this process as root so
        we can still manage the openfortivpn child process.
        """
        import json
        import tempfile

        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(dict(self.config), f)
                tmp = f.name
            os.chmod(tmp, 0o644)

            script = ";".join([
                "import json,sys,os",
                "from forti_connect.otp import fetch_otp",
                f"c=json.load(open({json.dumps(tmp)}))",
                "r=fetch_otp(c)",
                # Write OTP then force-exit — avoids hanging on browser cleanup
                "sys.stdout.write(r or '');sys.stdout.flush();os._exit(0 if r else 1)",
            ])
            timeout = (
                int(self.config.get("VPN_OTP_TIMEOUT", "30"))
                + int(self.config.get("VPN_WAIT_BEFORE_INBOX", "7"))
                + 60  # generous buffer for browser startup/shutdown
            )
            result = subprocess.run(
                ["sudo", "-u", sudo_user, sys.executable, "-c", script],
                stdout=subprocess.PIPE,
                timeout=timeout,
            )
            return result.stdout.decode().strip() or None
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

    def down(self):
        """Stop VPN: terminate openfortivpn, restore DNS."""
        if self.dns_backend:
            log.info("Restoring DNS…")
            try:
                self.dns_backend.restore()
            except Exception as e:
                log.warn(f"DNS restore failed: {e}")
            self.dns_backend = None

        if self.process:
            log.info("Terminating openfortivpn…")
            try:
                self.process.terminate()
                self.process.wait()
            except Exception:
                pass
            self.process = None

        log.ok("VPN stopped.")

    def status(self):
        """Check if VPN is up."""
        if self.process and self.process.isalive():
            return "up"
        return "down"
