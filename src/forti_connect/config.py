"""Configuration loading from .env file.

Discovery order for .env:
  1. VPN_ENV environment variable (explicit override)
  2. ~/.config/forti-connect/.env
  3. ~/.config/af-vpn/.env (legacy fallback)
  4. .env in current working directory
"""

import os
import pwd
from pathlib import Path
from dotenv import dotenv_values


def _real_home():
    """Return the real user's home directory, accounting for sudo elevation."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except KeyError:
            pass
    return Path.home()


def env_path():
    """
    Find the .env file to load.

    Returns:
        Path to the .env file.

    Raises:
        FileNotFoundError: If no .env file is found.
    """
    # 1. Explicit override via environment variable
    if os.environ.get("VPN_ENV"):
        p = Path(os.environ["VPN_ENV"]).expanduser()
        if p.exists():
            return p
        raise FileNotFoundError(f"VPN_ENV points to missing file: {p}")

    # 2. ~/.config/forti-connect/.env (real user's home, even under sudo)
    default = _real_home() / ".config" / "forti-connect" / ".env"
    if default.exists():
        return default

    # 3. ~/.config/af-vpn/.env (legacy fallback)
    legacy = _real_home() / ".config" / "af-vpn" / ".env"
    if legacy.exists():
        return legacy

    # 4. .env in current directory
    cwd = Path.cwd() / ".env"
    if cwd.exists():
        return cwd

    raise FileNotFoundError(
        "No .env file found. Checked:\n"
        f"  {default}\n"
        f"  {legacy}\n"
        f"  {cwd}\n"
        "Create one or set VPN_ENV=/path/to/.env"
    )


# Keep for backward compatibility with existing callers
def config_path():
    return env_path()


def load_config(path=None):
    """
    Load configuration from a .env file.

    Args:
        path: Explicit path to .env. If None, auto-discovers via env_path().

    Returns:
        Dict of configuration values.
    """
    p = Path(path).expanduser() if path else env_path()

    if not p.exists():
        raise FileNotFoundError(
            f"Config file not found: {p}\n"
            "Run 'vpn setup' to create it."
        )

    return dotenv_values(p)


def get_config(path=None):
    """
    Load and validate configuration with sensible defaults.

    Args:
        path: Explicit path to .env. If None, auto-discovers via env_path().

    Returns:
        Dict of validated configuration.
    """
    config = load_config(path)

    # VPN_CONFIG is required — it points to the openfortivpn config file
    # which holds host/username/password (secrets never go in .env)
    if not config.get("VPN_CONFIG"):
        raise ValueError(
            "Missing required config: VPN_CONFIG\n"
            "Set VPN_CONFIG=/path/to/vpn-config in your .env file.\n"
            "That file holds your host/username/password in openfortivpn format."
        )

    vpn_config = Path(config["VPN_CONFIG"]).expanduser()
    if not vpn_config.exists():
        raise FileNotFoundError(
            f"VPN_CONFIG file not found: {vpn_config}\n"
            "Create it with: host, username, password in openfortivpn format."
        )

    # OS-aware default for the binary path
    import sys as _sys
    _default_bin = (
        "/opt/homebrew/bin/openfortivpn"
        if _sys.platform == "darwin"
        else "/usr/bin/openfortivpn"
    )

    # Sensible defaults for optional fields (matching the Bash .env convention)
    defaults = {
        "VPN_FORTIVPN_BIN":        _default_bin,
        "VPN_DNS_METHOD":          "auto",
        "VPN_VPN_INTERFACE":       "ppp0",
        "VPN_OTP_SENDER":          "DoNotReply@fortinet-notifications.com",
        "VPN_OTP_TIMEOUT":         "30",
        "VPN_OTP_POLL_INTERVAL":   "5",
        "VPN_WAIT_BEFORE_INBOX":   "7",
        "VPN_BROWSER_USER_DATA_DIR": str(_real_home() / ".vpn-otp-browser-profile"),
        "VPN_BROWSER_VISIBLE":     "false",
    }

    for key, val in defaults.items():
        if not config.get(key):
            config[key] = val

    return config
