"""Tests for scripts.util.notify."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.util.notify import format_run_message, send


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
    def test_done_uses_check_mark(self):
        msg = format_run_message("av.trim", "done", 1.234)
        assert "✅" in msg
        assert "av.trim" in msg
        assert "done" in msg
        assert "1.234s" in msg

    def test_failed_uses_cross(self):
        msg = format_run_message("av.trim", "failed", 0.5)
        assert "❌" in msg
        assert "failed" in msg
