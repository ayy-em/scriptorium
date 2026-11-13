"""Tests for POST /api/show-window — how a second launch reaches the running app."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from core.instance import APP_ID, SHOW_PATH
from webapp.app import app

client = TestClient(app)


@pytest.fixture
def show_window():
    """Publish a show callback the way a GUI tier does, and remove it afterwards."""
    callback = MagicMock()
    app.state.show_window = callback
    yield callback
    del app.state.show_window


def test_shows_the_window_and_names_the_app(show_window):
    response = client.post(SHOW_PATH)
    assert response.status_code == 200
    assert response.json()["app"] == APP_ID
    show_window.assert_called_once_with()


def test_without_a_desktop_window_there_is_nothing_to_show():
    assert not hasattr(app.state, "show_window")
    assert client.post(SHOW_PATH).status_code == 503
