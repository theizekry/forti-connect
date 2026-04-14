"""Tests for forti_connect.vpn module — VPN orchestration."""

from unittest.mock import MagicMock, patch, call

import pytest

from forti_connect.vpn import VpnSession


class TestVpnSessionInit:
    """Test VpnSession initialization."""

    def test_initializes_with_config(self, mock_config):
        session = VpnSession(config=mock_config)
        assert session.config == mock_config
        assert session.process is None
        assert session.dns_backend is None

    def test_picks_correct_binary_path_macos(self, mock_config):
        with patch("forti_connect.vpn.platform.detect_os", return_value="macos"):
            session = VpnSession(config=mock_config)
            assert "homebrew" in session.vpn_binary

    def test_picks_correct_binary_path_linux(self, mock_config):
        with patch("forti_connect.vpn.platform.detect_os", return_value="linux"):
            session = VpnSession(config=mock_config)
            assert "openfortivpn" in session.vpn_binary


class TestVpnSessionUp:
    """Test VPN startup."""

    def test_fails_if_binary_not_found(self, mock_config):
        with patch("forti_connect.vpn.Path.exists", return_value=False):
            session = VpnSession(config=mock_config)
            with pytest.raises(RuntimeError, match="not found"):
                session.up()

    def test_spawns_openfortivpn_with_correct_args(self, mock_config):
        with patch("forti_connect.vpn.Path.exists", return_value=True), \
             patch("forti_connect.vpn.pexpect.spawn") as mock_spawn, \
             patch("forti_connect.vpn.otp.fetch_otp", return_value="123456"), \
             patch("forti_connect.vpn.os.setuid"), \
             patch("forti_connect.vpn.subprocess.check_output", return_value=b"1000"):

            mock_proc = MagicMock()
            mock_spawn.return_value = mock_proc
            mock_proc.expect.side_effect = [None, None]  # OTP prompt, then tunnel up

            session = VpnSession(config=mock_config)
            session.up()

            # Verify spawn was called with correct host
            assert mock_spawn.called
            args, kwargs = mock_spawn.call_args
            assert "--host=vpn.test.com" in args[1:]
            assert "--username=testuser" in args[1:]

    def test_handles_otp_prompt_and_sends_code(self, mock_config):
        with patch("forti_connect.vpn.Path.exists", return_value=True), \
             patch("forti_connect.vpn.pexpect.spawn") as mock_spawn, \
             patch("forti_connect.vpn.otp.fetch_otp", return_value="654321"), \
             patch("forti_connect.vpn.os.setuid"), \
             patch("forti_connect.vpn.subprocess.check_output", return_value=b"1000"), \
             patch("forti_connect.vpn.get_dns_backend"):

            mock_proc = MagicMock()
            mock_spawn.return_value = mock_proc
            mock_proc.expect.side_effect = [None, None]

            session = VpnSession(config=mock_config)
            session.up()

            # Verify OTP was sent
            mock_proc.sendline.assert_called_with("654321")

    def test_applies_dns_after_tunnel_up(self, mock_config):
        mock_dns = MagicMock()

        with patch("forti_connect.vpn.Path.exists", return_value=True), \
             patch("forti_connect.vpn.pexpect.spawn") as mock_spawn, \
             patch("forti_connect.vpn.otp.fetch_otp", return_value="123456"), \
             patch("forti_connect.vpn.os.setuid"), \
             patch("forti_connect.vpn.subprocess.check_output", return_value=b"1000"), \
             patch("forti_connect.vpn.get_dns_backend", return_value=mock_dns) as mock_get_dns:

            mock_proc = MagicMock()
            mock_spawn.return_value = mock_proc
            mock_proc.expect.side_effect = [None, None]

            session = VpnSession(config=mock_config)
            session.up()

            # Verify DNS was applied
            mock_dns.apply.assert_called_once()


class TestVpnSessionDown:
    """Test VPN shutdown."""

    def test_restores_dns_on_shutdown(self, mock_config):
        mock_dns = MagicMock()
        session = VpnSession(config=mock_config)
        session.dns_backend = mock_dns
        session.process = None

        session.down()

        mock_dns.restore.assert_called_once()

    def test_terminates_process_on_shutdown(self, mock_config):
        session = VpnSession(config=mock_config)
        mock_proc = MagicMock()
        session.process = mock_proc

        session.down()

        mock_proc.terminate.assert_called_once()

    def test_handles_failed_dns_restore_gracefully(self, mock_config):
        mock_dns = MagicMock()
        mock_dns.restore.side_effect = Exception("DNS restore failed")

        session = VpnSession(config=mock_config)
        session.dns_backend = mock_dns
        session.process = None

        # Should not raise
        session.down()

    def test_handles_missing_process_gracefully(self, mock_config):
        session = VpnSession(config=mock_config)
        session.process = None

        # Should not raise
        session.down()


class TestVpnSessionStatus:
    """Test VPN status check."""

    def test_returns_up_when_process_alive(self, mock_config):
        session = VpnSession(config=mock_config)
        mock_proc = MagicMock()
        mock_proc.isalive.return_value = True
        session.process = mock_proc

        assert session.status() == "up"

    def test_returns_down_when_process_dead(self, mock_config):
        session = VpnSession(config=mock_config)
        mock_proc = MagicMock()
        mock_proc.isalive.return_value = False
        session.process = mock_proc

        assert session.status() == "down"

    def test_returns_down_when_no_process(self, mock_config):
        session = VpnSession(config=mock_config)
        assert session.status() == "down"
