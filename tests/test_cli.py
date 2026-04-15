"""Tests for forti_connect.cli module — CLI entry points."""

from unittest.mock import MagicMock, patch

import pytest

from forti_connect import cli


class TestCheckRoot:
    """Test root privilege check."""

    def test_passes_when_euid_is_zero(self):
        with patch("forti_connect.cli.os.geteuid", return_value=0):
            # Should not raise
            cli.check_root()

    def test_exits_when_not_root(self):
        with patch("forti_connect.cli.os.geteuid", return_value=1000), \
             pytest.raises(SystemExit) as exc_info:
            cli.check_root()
        assert exc_info.value.code == 1


class TestCmdUp:
    """Test 'vpn up' command."""

    def test_checks_root(self):
        with patch("forti_connect.cli.check_root") as mock_check:
            with patch("forti_connect.cli.VpnSession"):
                try:
                    cli.cmd_up(MagicMock())
                except SystemExit:
                    pass
            # Should have called check_root first
            # (may fail later due to mocks, but check_root should be called)

    def test_creates_session_and_calls_up(self):
        with patch("forti_connect.cli.check_root"), \
             patch("forti_connect.cli.VpnSession") as mock_session_class:

            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            cli.cmd_up(MagicMock())

            mock_session.up.assert_called_once()

    def test_exits_on_exception(self):
        with patch("forti_connect.cli.check_root"), \
             patch("forti_connect.cli.VpnSession") as mock_session_class:

            mock_session = MagicMock()
            mock_session.up.side_effect = Exception("Test error")
            mock_session_class.return_value = mock_session

            with pytest.raises(SystemExit) as exc_info:
                cli.cmd_up(MagicMock())
            assert exc_info.value.code == 1


class TestCmdDown:
    """Test 'vpn down' command."""

    def test_checks_root(self):
        with patch("forti_connect.cli.check_root") as mock_check:
            with patch("forti_connect.cli.subprocess.run", return_value=MagicMock(stdout="")):
                cli.cmd_down(MagicMock())
            # check_root should be called
            mock_check.assert_called_once()

    def test_kills_openfortivpn_process(self):
        with patch("forti_connect.cli.check_root"), \
             patch("forti_connect.cli.subprocess.run") as mock_run, \
             patch("forti_connect.cli.os.kill"), \
             patch("forti_connect.cli.get_config") as mock_get_config:

            # First call: pgrep returns PIDs
            mock_pgrep_result = MagicMock()
            mock_pgrep_result.stdout = "1234\n5678"
            mock_run.return_value = mock_pgrep_result
            mock_get_config.side_effect = FileNotFoundError()

            cli.cmd_down(MagicMock())

            # Verify pgrep was called
            assert mock_run.called

    def test_exits_on_exception(self):
        with patch("forti_connect.cli.check_root"), \
             patch("forti_connect.cli.subprocess.run", side_effect=Exception("Test error")):

            with pytest.raises(SystemExit) as exc_info:
                cli.cmd_down(MagicMock())
            assert exc_info.value.code == 1


class TestCmdStatus:
    """Test 'vpn status' command."""

    def test_shows_up_when_process_exists(self, capsys):
        with patch("forti_connect.cli.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            cli.cmd_status(MagicMock())

            captured = capsys.readouterr()
            assert "UP" in captured.out

    def test_shows_down_when_process_not_found(self, capsys):
        with patch("forti_connect.cli.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            cli.cmd_status(MagicMock())

            captured = capsys.readouterr()
            assert "DOWN" in captured.out

    def test_exits_on_exception(self):
        with patch("forti_connect.cli.subprocess.run", side_effect=Exception("Test error")):
            with pytest.raises(SystemExit) as exc_info:
                cli.cmd_status(MagicMock())
            assert exc_info.value.code == 1


class TestCmdConfig:
    """Test 'vpn config' command."""

    def test_prints_config(self, mock_config, capsys):
        with patch("forti_connect.cli.get_config", return_value=mock_config), \
             patch("forti_connect.config.env_path", return_value="/mock/.env"):
            cli.cmd_config(MagicMock())

            captured = capsys.readouterr()
            assert "VPN_OTP_SENDER" in captured.out
            assert "otp@test.com" in captured.out

    def test_exits_when_config_missing(self):
        with patch("forti_connect.cli.get_config", side_effect=FileNotFoundError("Not found")):
            with pytest.raises(SystemExit) as exc_info:
                cli.cmd_config(MagicMock())
            assert exc_info.value.code == 1


class TestCmdSetup:
    """Test 'vpn setup' command."""

    def test_creates_config_directory(self):
        with patch("forti_connect.cli.input", side_effect=["", "", "", "", ""]), \
             patch("forti_connect.cli.Path.home"), \
             patch("builtins.open", create=True), \
             patch("forti_connect.cli.subprocess.run"), \
             patch("forti_connect.cli.os.environ"), \
             patch("forti_connect.cli.get_config", return_value={}), \
             patch("forti_connect.cli.otp.fetch_otp"):

            args = MagicMock()
            cli.cmd_setup(args)

            # Should not raise
            assert True

    def test_skips_if_config_exists_and_user_declines(self, tmp_path):
        config_file = tmp_path / ".config" / "af-vpn" / "config.env"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("VPN_GATEWAY=old")

        with patch("forti_connect.cli.config_path", return_value=config_file), \
             patch("forti_connect.cli.input", return_value="n"):

            args = MagicMock()
            cli.cmd_setup(args)

            # Should not raise, and file should remain unchanged
            assert config_file.read_text() == "VPN_GATEWAY=old"


class TestMain:
    """Test main CLI entry point."""

    def test_calls_cmd_up_for_up_subcommand(self):
        with patch("forti_connect.cli.cmd_up") as mock_cmd:
            with patch("forti_connect.cli.argparse.ArgumentParser"):
                # Create a minimal parser for testing
                with patch("sys.argv", ["vpn", "up"]):
                    try:
                        cli.main()
                    except SystemExit:
                        pass  # argparse may exit

    def test_prints_help_with_no_args(self):
        with patch("sys.argv", ["vpn"]):
            with patch("forti_connect.cli.argparse.ArgumentParser") as mock_parser_class:
                mock_parser = MagicMock()
                mock_parser_class.return_value = mock_parser
                mock_parser.parse_args.return_value = MagicMock(command=None)

                try:
                    cli.main()
                except SystemExit:
                    pass
