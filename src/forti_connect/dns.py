"""DNS management (resolvectl, resolv, networksetup backends)."""

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class DnsBackend(ABC):
    """Abstract base class for DNS backends."""

    def __init__(self, config):
        self.config = config
        # Support VPN_DNS_PRIMARY / VPN_DNS_SECONDARY (Bash .env convention)
        primary   = config.get("VPN_DNS_PRIMARY")
        secondary = config.get("VPN_DNS_SECONDARY")
        if primary:
            self.dns_servers = [s for s in [primary, secondary] if s]
        else:
            self.dns_servers = config.get("VPN_DNS_SERVERS", "1.1.1.1 1.0.0.1").split()

    @abstractmethod
    def apply(self):
        """Apply VPN DNS servers."""
        pass

    @abstractmethod
    def restore(self):
        """Restore original DNS."""
        pass


class ResolvectlBackend(DnsBackend):
    """systemd-resolved backend (Linux)."""

    def __init__(self, config):
        super().__init__(config)
        self.interface = config.get("VPN_VPN_INTERFACE", "ppp0")

    def apply(self):
        """Set DNS via resolvectl."""
        for server in self.dns_servers:
            subprocess.run(
                ["resolvectl", "dns", self.interface, server],
                check=True,
                capture_output=True,
            )

    def restore(self):
        """Restore DNS via resolvectl."""
        subprocess.run(
            ["resolvectl", "dns", self.interface, "--reset"],
            check=False,
            capture_output=True,
        )


class ResolvBackend(DnsBackend):
    """Direct /etc/resolv.conf backend (Linux fallback)."""

    RESOLV_CONF = Path("/etc/resolv.conf")
    BACKUP_DIR = Path("/tmp/forti-connect-dns")

    def apply(self):
        """Backup /etc/resolv.conf and apply new DNS."""
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = self.BACKUP_DIR / "resolv.conf.backup"

        if self.RESOLV_CONF.exists():
            shutil.copy2(self.RESOLV_CONF, backup_path)

        # Write new resolv.conf
        dns_lines = "\n".join(f"nameserver {server}" for server in self.dns_servers)
        subprocess.run(
            ["sudo", "tee", str(self.RESOLV_CONF)],
            input=dns_lines.encode(),
            check=True,
            capture_output=True,
        )

    def restore(self):
        """Restore /etc/resolv.conf from backup."""
        backup_path = self.BACKUP_DIR / "resolv.conf.backup"
        if backup_path.exists():
            subprocess.run(
                ["sudo", "cp", str(backup_path), str(self.RESOLV_CONF)],
                check=False,
                capture_output=True,
            )


class NetworksetupBackend(DnsBackend):
    """macOS networksetup backend."""

    def __init__(self, config):
        super().__init__(config)
        self.service = config.get("VPN_ACTIVE_SERVICE", "Wi-Fi")

    def apply(self):
        """Set DNS via networksetup."""
        subprocess.run(
            ["networksetup", "-setdnsservers", self.service] + self.dns_servers,
            check=True,
            capture_output=True,
        )

    def restore(self):
        """Restore DNS via networksetup (empty = DHCP)."""
        subprocess.run(
            ["networksetup", "-setdnsservers", self.service, "Empty"],
            check=False,
            capture_output=True,
        )


def get_dns_backend(method, config):
    """
    Factory to get the appropriate DNS backend.

    Args:
        method: 'resolvectl', 'resolv', or 'networksetup'.
        config: Configuration dict.

    Returns:
        DnsBackend instance.
    """
    backends = {
        "resolvectl": ResolvectlBackend,
        "resolv": ResolvBackend,
        "networksetup": NetworksetupBackend,
    }

    if method not in backends:
        raise ValueError(f"Unknown DNS method: {method}")

    return backends[method](config)
