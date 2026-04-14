"""OTP extraction from Outlook Web via Playwright."""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# --- Colored logging ---

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_info(msg):
    print(f"{DIM}[{_ts()}]{RESET} {CYAN}{BOLD}INFO{RESET}  {CYAN}{msg}{RESET}", file=sys.stderr)


def log_success(msg):
    print(f"{DIM}[{_ts()}]{RESET} {GREEN}{BOLD}OK{RESET}    {GREEN}{msg}{RESET}", file=sys.stderr)


def log_warn(msg):
    print(f"{DIM}[{_ts()}]{RESET} {YELLOW}{BOLD}WARN{RESET}  {YELLOW}{msg}{RESET}", file=sys.stderr)


def log_error(msg):
    print(f"{DIM}[{_ts()}]{RESET} {RED}{BOLD}ERROR{RESET} {RED}{msg}{RESET}", file=sys.stderr)


def log_dim(msg):
    print(f"{DIM}    {msg}{RESET}", file=sys.stderr)


# --- Helper functions ---


def extract_otp_from_text(text):
    """Extract a 6-digit OTP code from text. Returns the code or None."""
    if not text:
        return None
    match = re.search(r"\b\d{6}\b", text)
    return match.group(0) if match else None


# --- Email selectors ---

INBOX_SELECTORS = [
    'div[role="listbox"] div[role="option"]:has-text("{sender}")',
    'div[role="list"] div[role="listitem"]:has-text("{sender}")',
]

BODY_SELECTORS = [
    'div[role="document"]',
    'div[aria-label="Message body"]',
    "div.ReadMsgBody",
    'div[id*="UniqueMessageBody"]',
]


# --- Browser interaction functions ---


def find_sender_emails(page, sender):
    """Find email items in the inbox matching the given sender."""
    for selector_template in INBOX_SELECTORS:
        selector = selector_template.format(sender=sender)
        items = page.locator(selector)
        if items.count() > 0:
            return items
    return None


def extract_email_body(page):
    """Extract text from the currently open email in the reading pane."""
    for selector in BODY_SELECTORS:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                return el.inner_text(timeout=3000)
        except Exception:
            continue
    return None


def get_topmost_otp(page, sender):
    """Get the OTP from the topmost (first) email matching the sender, or None."""
    try:
        email_items = find_sender_emails(page, sender)
        if email_items is None:
            return None

        if email_items.count() == 0:
            return None

        # Only check the first (topmost = newest) email
        item = email_items.nth(0)
        item.click(timeout=3000)
        time.sleep(1)

        body = extract_email_body(page)
        return extract_otp_from_text(body)

    except Exception as e:
        log_warn(f"Error scanning inbox: {e}")

    return None


def refresh_inbox(page):
    """Click the refresh button to check for new emails."""
    try:
        page.click('[aria-label="Refresh"]', timeout=3000)
        time.sleep(2)
    except Exception:
        pass


def poll_for_otp(page, config):
    """Poll the inbox for a NEW OTP email. Returns the OTP code or None.

    First captures the existing (stale) OTP if any, then polls until
    a different OTP appears at the top of the inbox. On timeout, falls
    back to the stale OTP since it may actually be the current valid one
    (e.g. the email arrived before polling started).
    """
    sender = config.get("VPN_OTP_SENDER", "noreply@company.com")
    timeout = int(config.get("VPN_OTP_TIMEOUT", "30"))
    poll_interval = int(config.get("VPN_OTP_POLL_INTERVAL", "2"))

    # Capture the existing OTP (will use as fallback if no fresh one arrives)
    stale_otp = get_topmost_otp(page, sender)
    if stale_otp:
        log_info(f"Existing OTP found: {BOLD}{stale_otp}{RESET} (will use as fallback)")
    else:
        log_info("No existing OTP email, waiting for fresh one…")

    elapsed = 0
    while elapsed < timeout:
        refresh_inbox(page)

        current_otp = get_topmost_otp(page, sender)

        if current_otp and current_otp != stale_otp:
            log_success(f"Fresh OTP detected: {BOLD}{current_otp}{RESET}")
            return current_otp

        remaining = timeout - elapsed
        log_dim(f"Polling… {elapsed}s elapsed, {remaining}s remaining")
        time.sleep(poll_interval)
        elapsed += poll_interval

    # No fresh OTP arrived, but the stale one might be the valid current
    # code (e.g. the email arrived before polling started). Try it rather
    # than forcing manual entry.
    if stale_otp:
        log_warn(f"Timeout — using existing OTP as fallback: {BOLD}{stale_otp}{RESET}")
        return stale_otp

    return None


def fetch_otp(config):
    """
    Fetch OTP from Outlook Web using Playwright.

    Args:
        config: Configuration dict with VPN_* keys.

    Returns:
        OTP code (6 digits) or None on failure.
    """
    browser_profile = config.get(
        "VPN_BROWSER_PROFILE",
        str(Path.home() / ".vpn-otp-browser-profile"),
    )
    browser_visible = config.get("VPN_BROWSER_VISIBLE", "false").lower() == "true"
    sender = config.get("VPN_OTP_SENDER", "noreply@company.com")
    wait_before_inbox = int(config.get("VPN_WAIT_BEFORE_INBOX", "7"))

    print(file=sys.stderr)
    log_info(
        f"OTP Fetch  |  sender={BOLD}{sender}{RESET}  "
        f"timeout={BOLD}{config.get('VPN_OTP_TIMEOUT', '30')}s{RESET}  "
        f"headless={BOLD}{not browser_visible}{RESET}"
    )
    log_dim(f"Profile: {browser_profile}")

    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(
            user_data_dir=browser_profile,
            headless=not browser_visible,
            ignore_https_errors=True,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()

            log_info("Opening Outlook Web…")
            page.goto("https://outlook.office.com/mail/", wait_until="load")

            log_dim(f"Waiting {wait_before_inbox}s for inbox to load…")
            time.sleep(wait_before_inbox)

            otp = poll_for_otp(page, config)
            if otp:
                log_success(f"OTP ready: {BOLD}{otp}{RESET}")
                return otp

            log_error("Timed out — no OTP email found")
            return None

        finally:
            context.close()
