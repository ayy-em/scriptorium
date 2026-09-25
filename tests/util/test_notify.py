"""Tests for scripts.util.notify."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.util.notify import format_duration, format_run_message, send


@pytest.fixture
def creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")


class TestSend:
    def test_returns_false_when_credentials_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert send("hello") is False

    def test_posts_to_telegram_api(self, creds: None):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = True

        with patch("scripts.util.notify.httpx.post", return_value=mock_response) as mock_post:
            ok = send("hi there")

        assert ok is True
        call = mock_post.call_args
        assert "https://api.telegram.org/botfake-token/sendMessage" == call.args[0]
        assert call.kwargs["data"] == {"chat_id": "12345", "text": "hi there"}

    def test_returns_false_on_non_2xx(self, creds: None):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = False

        with patch("scripts.util.notify.httpx.post", return_value=mock_response):
            assert send("hello") is False

    def test_returns_false_on_network_failure(self, creds: None):
        with patch("scripts.util.notify.httpx.post", side_effect=httpx.ConnectError("offline")):
            assert send("hello") is False

    def test_blank_credentials_treated_as_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  ")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
        assert send("hello") is False


class TestFormatRunMessage:
    """Script, outcome and duration: everything the phone needs, nothing else."""

    def test_done_uses_check_mark(self):
        msg = format_run_message("av.trim", "done", 1.234)
        assert "✅" in msg
        assert "av.trim" in msg
        assert "finished" in msg
        assert "1.2s" in msg

    def test_failed_uses_cross(self):
        msg = format_run_message("av.trim", "failed", 0.5)
        assert "❌" in msg
        assert "failed" in msg
        assert "0.5s" in msg


class TestFormatDuration:
    def test_seconds_keep_one_decimal(self):
        assert format_duration(0.84) == "0.8s"
        assert format_duration(59.96) == "60.0s"

    def test_minutes_pad_the_seconds(self):
        assert format_duration(65) == "1m 05s"
        assert format_duration(754.4) == "12m 34s"

    def test_hours_drop_the_seconds(self):
        assert format_duration(3600) == "1h 00m"
        assert format_duration(4321) == "1h 12m"
