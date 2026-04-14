"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock playwright before importing forti_connect modules
sys.modules["playwright"] = MagicMock()
sys.modules["playwright.sync_api"] = MagicMock()

# Add src to path so tests can import forti_connect
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def mock_config():
    """Provide a basic mock config dict."""
    return {
        "VPN_GATEWAY": "vpn.test.com",
        "VPN_USER": "testuser",
        "VPN_PASSWORD": "testpass",
        "VPN_OTP_SENDER": "otp@test.com",
        "VPN_DNS_SERVERS": "1.1.1.1 1.0.0.1",
        "VPN_DNS_METHOD": "auto",
        "VPN_BROWSER_VISIBLE": "false",
        "VPN_BROWSER_PROFILE": "/tmp/test-profile",
        "VPN_OTP_TIMEOUT": "30",
        "VPN_OTP_POLL_INTERVAL": "2",
    }
