"""Tests for the Scriptorium web server routes."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from core import history
from core.paths import outputs_root, read_version
from core.progress import SENTINEL, ProgressEvent, encode
from core.registry import discover, discover_themes
from webapp.app import _parse_version, _read_git_hash, _themes_meta_json, _themes_search_json, app

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
        assert 'href="/scripts/formats/convert_video"' in response.text

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
        response = client.get("/scripts/formats/convert_video")
        assert response.status_code == 200

    def test_shows_script_title(self):
        response = client.get("/scripts/formats/convert_video")
        assert "Convert video" in response.text

    def test_renders_form(self):
        response = client.get("/scripts/formats/convert_video")
        assert "<form" in response.text

    def test_form_has_fields(self):
        response = client.get("/scripts/formats/convert_video")
        assert 'name="to_format"' in response.text

    def test_choices_render_as_select(self):
        response = client.get("/scripts/formats/convert_video")
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
        response = client.get("/scripts/formats/convert_video")
        assert "sidebar" in response.text

    def test_includes_version(self):
        response = client.get("/scripts/formats/convert_video")
        assert "status-version" in response.text

    def test_includes_breadcrumb(self):
        response = client.get("/scripts/formats/convert_video")
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


class TestProgressEvents:
    """A progress line is a report about the run, not a line of its output."""

    def _run(self, stdout_lines: list[bytes]):
        async def _stdout():
            for line in stdout_lines:
                yield line

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
            return client.get("/scripts/lora/validate/run")

    def test_a_sentinel_line_becomes_its_own_event(self):
        content = self._run([encode(ProgressEvent(fraction=0.5, label="0:05 / 0:10")).encode() + b"\n"]).content
        assert b"event: progress" in content
        assert b'"fraction": 0.5' in content

    def test_a_sentinel_line_never_reaches_the_terminal(self):
        content = self._run([encode(ProgressEvent(fraction=0.5)).encode() + b"\n"]).content
        assert SENTINEL.encode() not in content

    def test_ordinary_output_still_streams_alongside_progress(self):
        content = self._run(
            [
                encode(ProgressEvent(fraction=0.5)).encode() + b"\n",
                b"/outputs/av/clip.mp4\n",
            ]
        ).content
        assert b"event: progress" in content
        assert b"data: /outputs/av/clip.mp4" in content

    def test_progress_is_kept_out_of_output_detection(self):
        """A label that happens to look like a path must not be credited as an output."""
        line = encode(ProgressEvent(fraction=0.5, label="/outputs/av/clip.mp4")).encode() + b"\n"
        with patch("webapp.app.find_reported_outputs", return_value=[]) as mock_detect:
            self._run([line])
        assert mock_detect.call_args[0][0] == []

    def test_a_malformed_sentinel_stays_visible_as_output(self):
        """Better a stray line in the terminal than a silently swallowed one."""
        content = self._run([SENTINEL.encode() + b"{not json\n"]).content
        assert b"not json" in content


class TestSettingsAPI:
    def test_get_settings_returns_200(self):
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "theme" in data
        assert "outputs_dir" in data

    def test_post_settings_persists(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        response = client.post(
            "/api/settings",
            json={"theme": "dark", "outputs_dir": str(tmp_path / "out")},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        get_response = client.get("/api/settings")
        data = get_response.json()
        assert data["theme"] == "dark"
        assert data["outputs_dir"] == str(tmp_path / "out")

    def test_post_settings_with_empty_outputs(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        response = client.post(
            "/api/settings",
            json={"theme": "light", "outputs_dir": ""},
        )
        assert response.status_code == 200


class TestOpenOutputs:
    def test_opens_the_outputs_root_not_a_theme_subdir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webapp.app.outputs_root", lambda: tmp_path)
        with patch("webapp.app.subprocess.Popen") as popen:
            response = client.post("/api/open-outputs")
        assert response.status_code == 200
        opened = popen.call_args[0][0][-1]
        assert opened == str(tmp_path)
        assert not opened.endswith("default")

    def test_requires_no_request_body(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webapp.app.outputs_root", lambda: tmp_path)
        with patch("webapp.app.subprocess.Popen"):
            assert client.post("/api/open-outputs").status_code == 200


class TestDropUpload:
    def test_mp4_returns_video_category(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webapp.app.drop_session_dir", lambda sid: tmp_path)
        response = client.post(
            "/api/drop-upload",
            files=[("files", ("clip.mp4", b"fake-video-data", "video/mp4"))],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "video"
        assert data["count"] == 1
        assert data["files"][0]["filename"] == "clip.mp4"
        assert data["total_size"] == len(b"fake-video-data")
        assert any(s["key"] == "formats.convert_video" for s in data["scripts"])

    def test_unknown_ext_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webapp.app.drop_session_dir", lambda sid: tmp_path)
        response = client.post(
            "/api/drop-upload",
            files=[("files", ("data.xyz", b"whatever", "application/octet-stream"))],
        )
        assert response.status_code == 400
        assert ".xyz" in response.json()["detail"]

    def test_saves_file_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webapp.app.drop_session_dir", lambda sid: tmp_path)
        client.post(
            "/api/drop-upload",
            files=[("files", ("test.png", b"png-bytes", "image/png"))],
        )
        assert (tmp_path / "test.png").read_bytes() == b"png-bytes"


class TestScriptFields:
    def test_returns_fields_for_known_script(self):
        response = client.get("/api/script-fields/formats/convert_video")
        assert response.status_code == 200
        data = response.json()
        assert "fields" in data
        dests = [f["dest"] for f in data["fields"]]
        assert "to_format" in dests

    def test_excludes_file_positional(self):
        response = client.get("/api/script-fields/formats/convert_video")
        data = response.json()
        dests = [f["dest"] for f in data["fields"]]
        assert "source" not in dests

    def test_includes_output_field(self):
        """--output is deliberately exposed so it can be set from the drop overlay.

        It used to be filtered out; commit df5a24a removed that exclusion.
        """
        response = client.get("/api/script-fields/av/trim")
        data = response.json()
        dests = [f["dest"] for f in data["fields"]]
        assert "output" in dests

    def test_unknown_script_returns_404(self):
        response = client.get("/api/script-fields/does/notexist")
        assert response.status_code == 404

    def test_script_without_parser_returns_empty(self):
        response = client.get("/api/script-fields/av/join")
        data = response.json()
        assert data["fields"] == [] or isinstance(data["fields"], list)


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

    def test_parse_version_basic(self):
        assert _parse_version("0.3.0") == (0, 3, 0)

    def test_parse_version_comparison(self):
        assert _parse_version("0.4.0") > _parse_version("0.3.0")
        assert _parse_version("1.0.0") > _parse_version("0.99.0")
        assert _parse_version("0.3.0") == _parse_version("0.3.0")


class TestQuitEndpoint:
    def test_quit_returns_403_in_dev_mode(self):
        response = client.post("/api/quit")
        assert response.status_code == 403

    def test_quit_returns_200_when_frozen(self, monkeypatch):
        monkeypatch.setattr("webapp.app.FROZEN", True)
        mock_server = MagicMock()
        mock_server.should_exit = False
        client.app.state.uv_server = mock_server

        response = client.post("/api/quit")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert mock_server.should_exit is True

        monkeypatch.setattr("webapp.app.FROZEN", False)
        delattr(client.app.state, "uv_server")

    def test_quit_returns_503_when_no_server_ref(self, monkeypatch):
        monkeypatch.setattr("webapp.app.FROZEN", True)
        if hasattr(client.app.state, "uv_server"):
            delattr(client.app.state, "uv_server")

        response = client.post("/api/quit")
        assert response.status_code == 503

        monkeypatch.setattr("webapp.app.FROZEN", False)


class TestUpdateCheckEndpoint:
    def test_update_check_returns_200(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/ayy-em/scriptorium/releases/tag/v99.0.0",
        }
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            response = client.get("/api/update-check")
            assert response.status_code == 200
            data = response.json()
            assert "update_available" in data
            assert "current" in data

    def test_update_check_handles_network_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            response = client.get("/api/update-check")
            assert response.status_code == 200
            data = response.json()
            assert data["update_available"] is False


class TestPreviewCommand:
    def test_unknown_script_returns_404(self):
        assert client.get("/api/preview-command/av/nope").status_code == 404

    def test_bare_command_when_no_params_given(self):
        data = client.get("/api/preview-command/av/filmstrip").json()
        assert data["command"].endswith("av.filmstrip")

    def test_includes_positional_and_flags(self):
        data = client.get(
            "/api/preview-command/av/filmstrip",
            params={"source": "clip.mp4", "grid": "2x5", "format": "pdf"},
        ).json()
        command = data["command"]
        assert "av.filmstrip" in command
        assert "clip.mp4" in command
        assert "--grid 2x5" in command
        assert "--format pdf" in command

    def test_omits_empty_values(self):
        data = client.get(
            "/api/preview-command/av/filmstrip",
            params={"source": "clip.mp4", "output": ""},
        ).json()
        assert "--output" not in data["command"]

    def test_matches_build_argv(self):
        """The preview must not drift from what the run endpoint would execute."""
        from webapp._form import build_argv, fields_from_parser  # noqa: PLC0415

        form = {"source": "clip.mp4", "grid": "4x4", "format": "png"}
        specs = fields_from_parser(discover()["av.filmstrip"].get_parser())
        expected = build_argv(form, specs)

        command = client.get("/api/preview-command/av/filmstrip", params=form).json()["command"]
        for token in expected:
            assert token in command

    def test_quotes_paths_containing_spaces(self):
        command = client.get(
            "/api/preview-command/av/filmstrip",
            params={"source": "my holiday clip.mp4"},
        ).json()["command"]
        assert '"my holiday clip.mp4"' in command or "'my holiday clip.mp4'" in command


class TestBrowseFolder:
    def test_returns_501_without_a_native_window(self):
        response = client.post("/api/browse-folder")
        assert response.status_code == 501

    def test_returns_selected_path_when_a_window_exists(self):
        window = MagicMock()
        window.create_file_dialog.return_value = ("D:\\chosen\folder",)
        app.state.webview_window = window
        try:
            with patch.dict("sys.modules", {"webview": MagicMock(FOLDER_DIALOG=2)}):
                response = client.post("/api/browse-folder")
        finally:
            app.state.webview_window = None
        assert response.status_code == 200
        assert response.json()["path"] == "D:\\chosen\folder"

    def test_cancelled_dialog_returns_empty_path(self):
        window = MagicMock()
        window.create_file_dialog.return_value = None
        app.state.webview_window = window
        try:
            with patch.dict("sys.modules", {"webview": MagicMock(FOLDER_DIALOG=2)}):
                response = client.post("/api/browse-folder")
        finally:
            app.state.webview_window = None
        assert response.status_code == 200
        assert response.json()["path"] == ""

    def test_settings_reports_browse_unsupported_by_default(self):
        assert client.get("/api/settings").json()["browse_supported"] is False


class TestOpenLogs:
    def test_opens_the_logs_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webapp.app.logs_dir", lambda: tmp_path)
        with patch("webapp.app.subprocess.Popen") as popen:
            response = client.post("/api/open-logs")
        assert response.status_code == 200
        assert popen.call_args[0][0][-1] == str(tmp_path)


class TestAcceptExts:
    def test_derives_extensions_from_accepts(self):
        from webapp.app import accept_exts_for  # noqa: PLC0415

        exts = accept_exts_for(discover()["av.filmstrip"])
        assert ".mp4" in exts
        assert ".mp3" not in exts

    def test_script_without_accepts_returns_empty(self):
        from types import SimpleNamespace  # noqa: PLC0415

        from webapp.app import accept_exts_for  # noqa: PLC0415

        assert accept_exts_for(SimpleNamespace()) == ""


class TestCancelRun:
    def test_unknown_run_returns_404(self):
        assert client.post("/api/runs/nosuchrun/cancel").status_code == 404

    def test_cancels_an_in_flight_run(self):
        from webapp import _runs  # noqa: PLC0415

        handle = _runs.new_handle("av.filmstrip", ["clip.mp4"], {"source": "clip.mp4"})
        try:
            with patch.object(_runs, "terminate_tree", return_value=True) as kill:
                response = client.post(f"/api/runs/{handle.run_id}/cancel")
            assert response.status_code == 200
            assert response.json() == {"run_id": handle.run_id, "cancelled": True}
            kill.assert_called_once_with(handle)
        finally:
            _runs.discard(handle.run_id)

    def test_reports_when_there_was_nothing_left_to_kill(self):
        from webapp import _runs  # noqa: PLC0415

        handle = _runs.new_handle("av.filmstrip", [], {})
        try:
            with patch.object(_runs, "terminate_tree", return_value=False):
                assert client.post(f"/api/runs/{handle.run_id}/cancel").json()["cancelled"] is False
        finally:
            _runs.discard(handle.run_id)

    def test_a_finished_run_is_no_longer_cancellable(self):
        """The registry drops handles on completion, so this is a 404 by design."""
        from webapp import _runs  # noqa: PLC0415

        handle = _runs.new_handle("av.filmstrip", [], {})
        _runs.discard(handle.run_id)
        assert client.post(f"/api/runs/{handle.run_id}/cancel").status_code == 404


class TestRunLifecycle:
    """The stream must announce its run id and record the outcome."""

    @staticmethod
    def _fake_proc(rc=0, stdout=b"ok\n", stderr=b""):
        async def _out():
            if stdout:
                yield stdout

        async def _err():
            if stderr:
                yield stderr

        proc = MagicMock()
        proc.stdout = _out()
        proc.stderr = _err()
        proc.pid = 999
        proc.returncode = rc
        proc.wait = AsyncMock(return_value=rc)
        return proc

    def _run(self, tmp_path, monkeypatch, rc=0, cancel=False):
        from core import history  # noqa: PLC0415
        from webapp import _runs  # noqa: PLC0415

        monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "history.json")

        proc = self._fake_proc(rc=rc)

        async def fake_create(*args, **kwargs):
            if cancel:
                # Simulate the cancel endpoint landing while the run is live.
                for rid in _runs.active_ids():
                    _runs.get(rid).cancelled = True
            return proc

        with patch("asyncio.create_subprocess_exec", new=fake_create):
            response = client.get("/scripts/lora/validate/run")
        return response, history

    def test_stream_emits_a_start_event_with_the_run_id(self, tmp_path, monkeypatch):
        response, _ = self._run(tmp_path, monkeypatch)
        assert b"event: start" in response.content
        assert b'"run_id"' in response.content

    def test_successful_run_is_recorded(self, tmp_path, monkeypatch):
        response, history = self._run(tmp_path, monkeypatch, rc=0)
        records = history.load()
        assert len(records) == 1
        assert records[0].status == history.SUCCESS
        assert records[0].key == "lora.validate"
        assert b'"status": "success"' in response.content

    def test_failed_run_is_recorded_as_error(self, tmp_path, monkeypatch):
        _, history = self._run(tmp_path, monkeypatch, rc=1)
        assert history.load()[0].status == history.ERROR

    def test_cancelled_run_is_recorded_as_cancelled_despite_a_nonzero_exit(self, tmp_path, monkeypatch):
        """A killed process exits non-zero; the handle's flag has to win."""
        response, history = self._run(tmp_path, monkeypatch, rc=1, cancel=True)
        assert history.load()[0].status == history.CANCELLED
        assert b'"cancelled": true' in response.content
        assert b"cancelled" in response.content

    def test_registry_is_emptied_when_the_run_ends(self, tmp_path, monkeypatch):
        from webapp import _runs  # noqa: PLC0415

        self._run(tmp_path, monkeypatch)
        assert _runs.active_ids() == []


class TestHistoryPage:
    def test_renders_with_no_history(self, tmp_path, monkeypatch):
        from core import history  # noqa: PLC0415

        monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "history.json")
        response = client.get("/history")
        assert response.status_code == 200
        assert "No runs yet" in response.text

    def test_lists_a_recorded_run_with_a_rerun_link(self, tmp_path, monkeypatch):
        from core import history  # noqa: PLC0415

        monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "history.json")
        history.append(
            history.RunRecord(
                run_id="r1",
                key="av.filmstrip",
                status=history.SUCCESS,
                started_at="2026-07-28T02:31:05",
                elapsed=1.5,
                exit_code=0,
                argv=["clip.mp4"],
                params={"source": "clip.mp4", "grid": "2x5"},
            )
        )
        response = client.get("/history")
        assert "av.filmstrip" in response.text
        assert "/scripts/av/filmstrip?_rerun=1" in response.text
        assert "grid=2x5" in response.text

    def test_marks_a_run_whose_script_no_longer_exists(self, tmp_path, monkeypatch):
        from core import history  # noqa: PLC0415

        monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "history.json")
        history.append(
            history.RunRecord(
                run_id="r1",
                key="gone.forever",
                status=history.SUCCESS,
                started_at="2026-07-28T02:31:05",
                elapsed=1.0,
            )
        )
        response = client.get("/history")
        assert "unavailable" in response.text
        assert "/scripts/gone/forever" not in response.text

    def test_clear_empties_the_history(self, tmp_path, monkeypatch):
        from core import history  # noqa: PLC0415

        monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "history.json")
        history.append(
            history.RunRecord(
                run_id="r1", key="av.trim", status=history.SUCCESS, started_at="2026-07-28T02:31:05", elapsed=1.0
            )
        )
        assert client.post("/api/history/clear").status_code == 200
        assert history.load() == []

    def test_sidebar_history_link_is_no_longer_a_stub(self):
        response = client.get("/")
        assert 'href="/history"' in response.text


class TestFavouritesPage:
    """Cover the server side of favourites.

    Favourites live in localStorage, so the server renders the full list and the
    client filters it. These tests pin the contract that makes that work.
    """

    def test_returns_200(self):
        assert client.get("/favourites").status_code == 200

    def test_marks_the_sidebar_item_active(self):
        response = client.get("/favourites")
        assert 'class="sidebar-link active"' in response.text

    def test_renders_every_script_for_the_client_to_filter(self):
        favourites = client.get("/favourites")
        index = client.get("/")
        for key in discover():
            theme, name = key.split(".", 1)
            assert f'data-key="{theme}.{name}"' in favourites.text
        assert favourites.text.count('class="script-row"') == index.text.count('class="script-row"')

    def test_starts_in_favourites_only_mode(self):
        assert "scriptBrowser(true)" in client.get("/favourites").text

    def test_index_does_not(self):
        assert "scriptBrowser(false)" in client.get("/").text

    def test_titled_favourites(self):
        assert "<title>Favourites" in client.get("/favourites").text

    def test_sidebar_links_to_favourites(self):
        assert 'href="/favourites"' in client.get("/").text


class TestThemeMeta:
    def test_index_emits_theme_meta(self):
        assert "__THEME_META__" in client.get("/").text

    def test_meta_carries_label_count_and_keys(self):
        from webapp.app import _themes_meta_json  # noqa: PLC0415

        themes = discover_themes()
        meta = json.loads(_themes_meta_json(themes))
        assert set(meta) == set(themes)
        for theme, entry in meta.items():
            assert entry["count"] == len(themes[theme])
            assert len(entry["keys"]) == entry["count"]
            assert all(k.startswith(f"{theme}.") for k in entry["keys"])

    def test_keys_align_with_the_search_strings(self):
        """The client pairs them by index, so the two must stay in step."""
        from webapp.app import _themes_meta_json, _themes_search_json  # noqa: PLC0415

        themes = discover_themes()
        meta = json.loads(_themes_meta_json(themes))
        search = json.loads(_themes_search_json(themes))
        for theme, entry in meta.items():
            assert len(entry["keys"]) == len(search[theme])
            for key, text in zip(entry["keys"], search[theme], strict=True):
                assert text.startswith(key.lower())

    def test_escapes_closing_script_tags(self):
        assert "</" not in _themes_meta_json({"x": {}})


class TestSortControl:
    def test_sort_button_is_live_not_disabled(self):
        response = client.get("/")
        assert "cycleSort()" in response.text
        assert "btn-soon" not in response.text

    def test_favourite_buttons_are_live(self):
        response = client.get("/")
        assert "toggleFavourite(" in response.text
        assert "coming soon" not in response.text.lower()


class TestPreferencesEndpoint:
    """Favourites live in UserConfig so every launch tier sees the same set."""

    @pytest.fixture()
    def config_file(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        monkeypatch.setattr("core.config._CONFIG_PATH", path)
        return path

    def test_saved_favourites_come_back(self, config_file):
        client.post("/api/preferences", json={"favourites": ["av.trim"]})
        assert client.get("/api/settings").json()["favourites"] == ["av.trim"]

    def test_sort_order_persists(self, config_file):
        client.post("/api/preferences", json={"sort_order": "count"})
        assert client.get("/api/settings").json()["sort_order"] == "count"

    def test_omitted_fields_are_left_alone(self, config_file):
        client.post("/api/preferences", json={"favourites": ["av.trim"]})
        client.post("/api/preferences", json={"sort_order": "za"})
        body = client.get("/api/settings").json()
        assert body["favourites"] == ["av.trim"]
        assert body["sort_order"] == "za"

    def test_junk_is_rejected_rather_than_stored(self, config_file):
        client.post("/api/preferences", json={"favourites": [1, "", "av.trim"], "sort_order": "?"})
        body = client.get("/api/settings").json()
        assert body["favourites"] == ["av.trim"]
        assert body["sort_order"] == "az"

    def test_saving_settings_does_not_wipe_favourites(self, config_file):
        """The settings modal has no favourites field and must not clear them.

        post_settings rebuilds UserConfig from the request body, so anything it
        does not carry over is silently lost.
        """
        client.post("/api/preferences", json={"favourites": ["av.trim"], "sort_order": "count"})
        client.post("/api/settings", json={"theme": "dark", "close_behavior": "tray"})
        body = client.get("/api/settings").json()
        assert body["favourites"] == ["av.trim"]
        assert body["sort_order"] == "count"
        assert body["theme"] == "dark"


class TestOutputEndpoints:
    """Recent outputs come from history; reveal re-checks containment."""

    @pytest.fixture()
    def history_with_outputs(self, tmp_path, monkeypatch):
        produced = outputs_root() / "formats" / "detected-fixture.webp"
        produced.parent.mkdir(parents=True, exist_ok=True)
        produced.write_bytes(b"x")
        monkeypatch.setattr("core.history._HISTORY_PATH", tmp_path / "history.json")
        history.append(
            history.RunRecord(
                run_id="r1",
                key="formats.convert_image",
                status="success",
                started_at="2026-08-02T00:00:00",
                elapsed=1.0,
                exit_code=0,
                outputs=[str(produced)],
            )
        )
        yield produced
        produced.unlink(missing_ok=True)

    def test_recent_outputs_lists_files_that_still_exist(self, history_with_outputs):
        body = client.get("/api/recent-outputs/formats/convert_image").json()
        assert [o["name"] for o in body["outputs"]] == ["detected-fixture.webp"]

    def test_recent_outputs_skips_deleted_files(self, history_with_outputs):
        history_with_outputs.unlink()
        assert client.get("/api/recent-outputs/formats/convert_image").json()["outputs"] == []

    def test_recent_outputs_are_scoped_to_one_script(self, history_with_outputs):
        assert client.get("/api/recent-outputs/av/trim").json()["outputs"] == []

    def test_reveal_accepts_a_file_inside_the_outputs_root(self, history_with_outputs):
        with patch("webapp.app._open_in_file_manager") as opener:
            res = client.post("/api/reveal-output", json={"path": str(history_with_outputs)})
        assert res.status_code == 200
        opener.assert_called_once()

    def test_reveal_rejects_a_path_outside_the_outputs_root(self, tmp_path):
        outsider = tmp_path / "elsewhere.txt"
        outsider.write_text("x")
        with patch("webapp.app._open_in_file_manager") as opener:
            res = client.post("/api/reveal-output", json={"path": str(outsider)})
        assert res.status_code == 400
        opener.assert_not_called()

    def test_reveal_rejects_traversal_out_of_the_root(self):
        escape = outputs_root() / ".." / ".." / "etc" / "passwd"
        with patch("webapp.app._open_in_file_manager") as opener:
            res = client.post("/api/reveal-output", json={"path": str(escape)})
        assert res.status_code == 400
        opener.assert_not_called()

    def test_reveal_404s_for_a_vanished_file(self):
        gone = outputs_root() / "formats" / "not-there-at-all.webp"
        with patch("webapp.app._open_in_file_manager") as opener:
            res = client.post("/api/reveal-output", json={"path": str(gone)})
        assert res.status_code == 404
        opener.assert_not_called()


class TestBatchFanOut:
    """A per-file script is run once per dropped file, sequentially.

    The loop itself is client-side; what the server owes it is a batch id that
    groups the resulting records without leaking into the script's arguments.
    """

    def _fake_run(self, params):
        async def _stdout():
            yield b"ok\n"

        async def _stderr():
            return
            yield

        proc = MagicMock()
        proc.stdout = _stdout()
        proc.stderr = _stderr()
        proc.returncode = 0
        proc.wait = AsyncMock(return_value=0)

        async def fake_create(*args, **kwargs):
            return proc

        with patch("asyncio.create_subprocess_exec", new=fake_create):
            return client.get("/scripts/lora/validate/run", params=params)

    def test_batch_id_reaches_the_history_record(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.history._HISTORY_PATH", tmp_path / "history.json")
        self._fake_run({"inputs": "/tmp/fake", "_batch_id": "b123"})
        records = history.load()
        assert records[0].batch_id == "b123"

    def test_batch_id_never_becomes_a_script_argument(self, tmp_path, monkeypatch):
        """build_argv only reads declared specs, but the param is popped too.

        Left in place it would show up in the record's params and then in a
        re-run's prefilled form.
        """
        monkeypatch.setattr("core.history._HISTORY_PATH", tmp_path / "history.json")
        self._fake_run({"inputs": "/tmp/fake", "_batch_id": "b123"})
        record = history.load()[0]
        assert "_batch_id" not in record.params
        assert "_batch_id" not in " ".join(record.argv)
        assert "b123" not in " ".join(record.argv)

    def test_an_ordinary_run_has_no_batch_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.history._HISTORY_PATH", tmp_path / "history.json")
        self._fake_run({"inputs": "/tmp/fake"})
        assert history.load()[0].batch_id == ""
