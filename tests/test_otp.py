"""Tests for forti_connect.otp module — OTP extraction logic."""

from unittest.mock import MagicMock, patch

import pytest

from forti_connect import otp


class TestExtractOtpFromText:
    """Test OTP extraction from email body text."""

    def test_extracts_six_digit_code(self):
        assert otp.extract_otp_from_text("Your code is 482917 please enter it") == "482917"

    def test_extracts_first_six_digit_code(self):
        assert otp.extract_otp_from_text("Code: 123456 or 654321") == "123456"

    def test_returns_none_for_no_match(self):
        assert otp.extract_otp_from_text("No code here") is None

    def test_returns_none_for_empty_string(self):
        assert otp.extract_otp_from_text("") is None

    def test_returns_none_for_none_input(self):
        assert otp.extract_otp_from_text(None) is None

    def test_ignores_shorter_numbers(self):
        assert otp.extract_otp_from_text("Code: 12345") is None

    def test_ignores_longer_numbers(self):
        assert otp.extract_otp_from_text("Code: 1234567") is None

    def test_code_at_start_of_string(self):
        assert otp.extract_otp_from_text("948271 is your verification code") == "948271"

    def test_code_at_end_of_string(self):
        assert otp.extract_otp_from_text("Your verification code is 948271") == "948271"

    def test_code_on_its_own_line(self):
        assert otp.extract_otp_from_text("Your code:\n837261\nDo not share") == "837261"

    def test_realistic_fortinet_email_body(self):
        body = (
            "FortiToken Mobile\n\n"
            "Your one-time password is: 571034\n\n"
            "This code will expire in 60 seconds.\n"
            "Do not share this code with anyone."
        )
        assert otp.extract_otp_from_text(body) == "571034"


class TestFindSenderEmails:
    """Test email selector matching."""

    def test_returns_items_from_first_matching_selector(self):
        mock_page = MagicMock()
        mock_items = MagicMock()
        mock_items.count.return_value = 3
        mock_page.locator.return_value = mock_items

        result = otp.find_sender_emails(mock_page, "test@example.com")

        assert result is mock_items
        mock_page.locator.assert_called_once()

    def test_tries_second_selector_if_first_empty(self):
        mock_page = MagicMock()
        empty_items = MagicMock()
        empty_items.count.return_value = 0
        found_items = MagicMock()
        found_items.count.return_value = 2
        mock_page.locator.side_effect = [empty_items, found_items]

        result = otp.find_sender_emails(mock_page, "test@example.com")

        assert result is found_items
        assert mock_page.locator.call_count == 2

    def test_returns_none_if_no_selectors_match(self):
        mock_page = MagicMock()
        empty_items = MagicMock()
        empty_items.count.return_value = 0
        mock_page.locator.return_value = empty_items

        result = otp.find_sender_emails(mock_page, "test@example.com")

        assert result is None


class TestExtractEmailBody:
    """Test email body extraction."""

    def test_returns_text_from_first_visible_selector(self):
        mock_page = MagicMock()
        mock_el = MagicMock()
        mock_el.is_visible.return_value = True
        mock_el.inner_text.return_value = "Your OTP is 123456"

        mock_locator = MagicMock()
        mock_locator.first = mock_el
        mock_page.locator.return_value = mock_locator

        result = otp.extract_email_body(mock_page)
        assert result == "Your OTP is 123456"

    def test_returns_none_when_no_selectors_visible(self):
        mock_page = MagicMock()
        mock_el = MagicMock()
        mock_el.is_visible.side_effect = Exception("not found")

        mock_locator = MagicMock()
        mock_locator.first = mock_el
        mock_page.locator.return_value = mock_locator

        result = otp.extract_email_body(mock_page)
        assert result is None


class TestGetTopmostOtp:
    """Test topmost email OTP extraction."""

    def test_returns_otp_from_first_email(self):
        mock_page = MagicMock()
        mock_items = MagicMock()
        mock_items.count.return_value = 3
        mock_item = MagicMock()
        mock_items.nth.return_value = mock_item

        with patch.object(otp, "find_sender_emails", return_value=mock_items), \
             patch.object(otp, "extract_email_body", return_value="Code: 482917"), \
             patch("time.sleep"):
            result = otp.get_topmost_otp(mock_page, "test@example.com")

        assert result == "482917"
        mock_items.nth.assert_called_once_with(0)

    def test_returns_none_when_no_emails(self):
        mock_page = MagicMock()

        with patch.object(otp, "find_sender_emails", return_value=None):
            result = otp.get_topmost_otp(mock_page, "test@example.com")

        assert result is None

    def test_returns_none_when_zero_count(self):
        mock_page = MagicMock()
        mock_items = MagicMock()
        mock_items.count.return_value = 0

        with patch.object(otp, "find_sender_emails", return_value=mock_items):
            result = otp.get_topmost_otp(mock_page, "test@example.com")

        assert result is None

    def test_returns_none_when_body_has_no_otp(self):
        mock_page = MagicMock()
        mock_items = MagicMock()
        mock_items.count.return_value = 1
        mock_items.nth.return_value = MagicMock()

        with patch.object(otp, "find_sender_emails", return_value=mock_items), \
             patch.object(otp, "extract_email_body", return_value="No code here"), \
             patch("time.sleep"):
            result = otp.get_topmost_otp(mock_page, "test@example.com")

        assert result is None


class TestPollForOtp:
    """Test polling loop with stale OTP detection."""

    def test_ignores_stale_otp_and_returns_fresh(self):
        mock_page = MagicMock()
        config = {
            "VPN_OTP_SENDER": "test@example.com",
            "VPN_OTP_TIMEOUT": "60",
            "VPN_OTP_POLL_INTERVAL": "5",
        }

        # First call is stale detection, then polling returns stale twice, then fresh
        with patch.object(
            otp, "get_topmost_otp",
            side_effect=["111111", "111111", "111111", "222222"]
        ), patch.object(otp, "refresh_inbox"), \
             patch("time.sleep"):
            result = otp.poll_for_otp(mock_page, config)

        assert result == "222222"

    def test_returns_immediately_when_no_stale_and_fresh_arrives(self):
        mock_page = MagicMock()
        config = {
            "VPN_OTP_SENDER": "test@example.com",
            "VPN_OTP_TIMEOUT": "60",
            "VPN_OTP_POLL_INTERVAL": "5",
        }

        # No stale OTP, then fresh one appears
        with patch.object(
            otp, "get_topmost_otp",
            side_effect=[None, None, "123456"]
        ), patch.object(otp, "refresh_inbox"), \
             patch("time.sleep"):
            result = otp.poll_for_otp(mock_page, config)

        assert result == "123456"

    def test_returns_stale_as_fallback_on_timeout(self):
        mock_page = MagicMock()
        config = {
            "VPN_OTP_SENDER": "test@example.com",
            "VPN_OTP_TIMEOUT": "10",
            "VPN_OTP_POLL_INTERVAL": "5",
        }

        # Stale OTP exists, polling never finds fresh, but returns stale on timeout
        with patch.object(
            otp, "get_topmost_otp",
            side_effect=["111111", "111111", "111111"]  # stale, then same stale twice
        ), patch.object(otp, "refresh_inbox"), \
             patch("time.sleep"):
            result = otp.poll_for_otp(mock_page, config)

        assert result == "111111"

    def test_returns_none_when_timeout_and_no_stale(self):
        mock_page = MagicMock()
        config = {
            "VPN_OTP_SENDER": "test@example.com",
            "VPN_OTP_TIMEOUT": "10",
            "VPN_OTP_POLL_INTERVAL": "5",
        }

        # No stale, polling finds nothing
        with patch.object(
            otp, "get_topmost_otp",
            side_effect=[None, None, None]
        ), patch.object(otp, "refresh_inbox"), \
             patch("time.sleep"):
            result = otp.poll_for_otp(mock_page, config)

        assert result is None
