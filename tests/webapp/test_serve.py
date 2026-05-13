"""Tests for the Scriptorium web server routes."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from core.paths import read_version
from webapp.app import _read_git_hash, _themes_search_json, app

client = TestClient(app)


class TestIndex:
    def test_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_lists_av_theme(self):
        response = client.get("/")
        assert "av" in response.text

    def test_lists_lora_theme(self):
        response = client.get("/")
        assert "lora" in response.text

    def test_contains_script_links(self):
        response = client.get("/")
        assert 'href="/scripts/av/convert"' in response.text

    def test_includes_version(self):
        response = client.get("/")
        assert "v0." in response.text or "v—" in response.text or "v1." in response.text

    def test_includes_themes_data_json(self):
        response = client.get("/")
        assert "__THEMES__" in response.text

    def test_includes_sidebar(self):
        response = client.get("/")
        assert "sidebar" in response.text

    def test_includes_alpine_cdn(self):
        response = client.get("/")
        assert "alpinejs" in response.text

    def test_includes_static_css(self):
        response = client.get("/")
        assert "/static/style.css" in response.text


class TestScriptDetail:
    def test_known_script_returns_200(self):
        response = client.get("/scripts/av/convert")
        assert response.status_code == 200

    def test_shows_script_title(self):
        response = client.get("/scripts/av/convert")
        assert "Convert media file" in response.text

    def test_renders_form(self):
        response = client.get("/scripts/av/convert")
        assert "<form" in response.text

    def test_form_has_fields(self):
        response = client.get("/scripts/av/convert")
        assert 'name="source"' in response.text

    def test_choices_render_as_select(self):
        response = client.get("/scripts/av/convert")
        assert "<select" in response.text

    def test_unknown_script_returns_404(self):
        response = client.get("/scripts/does/notexist")
        assert response.status_code == 404

    def test_lora_validate_renders(self):
        response = client.get("/scripts/lora/validate")
        assert response.status_code == 200
        assert "Validate" in response.text

    def test_store_true_renders_checkbox(self):
        response = client.get("/scripts/av/tag")
        assert 'type="checkbox"' in response.text

    def test_includes_sidebar(self):
        response = client.get("/scripts/av/convert")
        assert "sidebar" in response.text

    def test_includes_version(self):
        response = client.get("/scripts/av/convert")
        assert "status-version" in response.text

    def test_includes_breadcrumb(self):
        response = client.get("/scripts/av/convert")
        assert "detail-breadcrumb" in response.text


class TestRunEndpoint:
    def test_unknown_script_returns_404(self):
        response = client.get("/scripts/does/notexist/run")
        assert response.status_code == 404

    def test_known_script_streams_sse(self):
        async def _stdout():
            yield b"dataset valid.\n"

        async def _stderr():
            yield b"[lora.validate] done in 0.001s\n"

        mock_proc = MagicMock()
        mock_proc.stdout = _stdout()
        mock_proc.stderr = _stderr()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock(return_value=0)

        async def fake_create(*args, **kwargs):
            return mock_proc

        with patch("asyncio.create_subprocess_exec", new=fake_create):
            response = client.get("/scripts/lora/validate/run", params={"inputs": "/tmp/fake"})

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert b"data:" in response.content
        assert b"event: done" in response.content

    def test_run_includes_exit_code(self):
        async def _stdout():
            yield b"ok\n"

        async def _stderr():
            return
            yield  # make it an async generator

        mock_proc = MagicMock()
        mock_proc.stdout = _stdout()
        mock_proc.stderr = _stderr()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock(return_value=0)

        async def fake_create(*args, **kwargs):
            return mock_proc

        with patch("asyncio.create_subprocess_exec", new=fake_create):
            response = client.get("/scripts/lora/validate/run")

        assert b"exit 0" in response.content


class TestHelpers:
    def test_read_version_returns_string(self):
        v = read_version()
        assert isinstance(v, str)
        assert len(v) > 0

    def test_read_git_hash_returns_string(self):
        h = _read_git_hash()
        assert isinstance(h, str)
        assert len(h) > 0

    def test_read_git_hash_fallback_on_bad_cwd(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            h = _read_git_hash()
        assert h == "—"

    def test_themes_search_json_structure(self):
        themes = {"av": {"convert": MagicMock(TITLE="Convert media"), "trim": MagicMock(TITLE="Trim")}}
        result = _themes_search_json(themes)
        data = json.loads(result)
        assert "av" in data
        assert any("av.convert" in s for s in data["av"])

    def test_themes_search_json_escapes_script_tag(self):
        themes = {"av": {"x": MagicMock(TITLE="</script>evil")}}
        result = _themes_search_json(themes)
        assert "</script>" not in result
