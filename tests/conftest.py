"""
Global pytest fixtures — applied to every test in this suite.

Clears Resend credentials from os.environ so unit tests that call
send_trip_notification() hit the stdout fallback instead of the live
Resend API.  (main.py calls load_dotenv() at import time, which would
otherwise populate os.environ from a real .env file.)
"""

import pytest


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("NOTIFICATION_EMAILS", raising=False)
