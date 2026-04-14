"""Platform detection and configuration (Linux vs macOS)."""

import platform
import subprocess
import sys


def detect_os():
    """Return 'linux' or 'macos' based on sys.platform."""
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform.startswith("linux"):
        return "linux"
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")


def pick_dns_method(os_name=None, method_override=None):
    """
    Pick the DNS backend based on OS and optional override.

    Args:
        os_name: 'linux' or 'macos'. If None, auto-detect.
        method_override: Force a specific method ('resolvectl', 'resolv', 'networksetup').

    Returns:
        The DNS method name to use.
    """
    if method_override:
        return method_override

    if os_name is None:
        os_name = detect_os()

    if os_name == "macos":
        return "networksetup"
    elif os_name == "linux":
        # Prefer resolvectl (systemd-resolved) if available, fallback to direct /etc/resolv.conf
        try:
            subprocess.run(["resolvectl", "--version"], capture_output=True, check=True)
            return "resolvectl"
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "resolv"
    else:
        raise ValueError(f"Unknown OS: {os_name}")


def active_network_service(os_name=None):
    """
    Get the active network service name (macOS) or interface (Linux).

    Args:
        os_name: 'linux' or 'macos'. If None, auto-detect.

    Returns:
        Service/interface name, or None if unable to determine.
    """
    if os_name is None:
        os_name = detect_os()

    if os_name == "macos":
        try:
            # Use route -n get default to find the active interface, then map to service name
            result = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Extract interface from "interface: en0" line
            for line in result.stdout.split("\n"):
                if "interface:" in line:
                    interface = line.split()[-1]
                    # Map interface to service name (e.g., en0 -> Ethernet)
                    # Common mappings: en0 -> Ethernet, en1 -> Wi-Fi, etc.
                    service_map = {
                        "en0": "Ethernet",
                        "en1": "Wi-Fi",
                    }
                    return service_map.get(interface, interface)
            return None
        except subprocess.CalledProcessError:
            return None
    elif os_name == "linux":
        try:
            # Use ip route to find default gateway interface
            result = subprocess.run(
                ["ip", "route", "show"],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("default "):
                    parts = line.split()
                    # Format: "default via X.X.X.X dev <interface>"
                    if "dev" in parts:
                        idx = parts.index("dev")
                        if idx + 1 < len(parts):
                            return parts[idx + 1]
            return None
        except subprocess.CalledProcessError:
            return None
    else:
        return None
