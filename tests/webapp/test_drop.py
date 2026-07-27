"""Tests for the Drop-to-Discover upload endpoint and batch classification."""

from fastapi.testclient import TestClient
import pytest

from webapp.app import app

client = TestClient(app)


def _upload(names, monkeypatch, target_dir, payload=b"data"):
    """POST *names* to the drop endpoint with the session directory pinned.

    The stub mirrors the real drop_session_dir by creating the directory it
    returns, so the endpoint can write into it.

    Args:
        names: Filenames to send.
        monkeypatch: pytest monkeypatch fixture.
        target_dir: Directory the endpoint should write into.
        payload: Bytes written for every file.

    Returns:
        The httpx Response.
    """

    def _stub(session_id):
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    monkeypatch.setattr("webapp.app.drop_session_dir", _stub)
    files = [("files", (n, payload, "application/octet-stream")) for n in names]
    return client.post("/api/drop-upload", files=files)


class TestBatchValidation:
    def test_accepts_several_files_of_one_category(self, tmp_path, monkeypatch):
        response = _upload(["a.mp4", "b.mov", "c.mkv"], monkeypatch, tmp_path)
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "video"
        assert data["count"] == 3

    def test_rejects_mixed_categories(self, tmp_path, monkeypatch):
        response = _upload(["report.docx", "clip.avi"], monkeypatch, tmp_path)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "document" in detail
        assert "video" in detail

    def test_rejects_unknown_extension_in_batch(self, tmp_path, monkeypatch):
        response = _upload(["a.mp4", "b.qqq"], monkeypatch, tmp_path)
        assert response.status_code == 400
        assert ".qqq" in response.json()["detail"]

    def test_rejects_empty_upload(self):
        assert client.post("/api/drop-upload", files=[]).status_code == 422

    def test_total_size_sums_every_file(self, tmp_path, monkeypatch):
        response = _upload(["a.mp3", "b.mp3"], monkeypatch, tmp_path, payload=b"12345")
        assert response.json()["total_size"] == 10


class TestSessionIsolation:
    def test_writes_all_files_into_the_session_dir(self, tmp_path, monkeypatch):
        _upload(["one.mp3", "two.mp3"], monkeypatch, tmp_path, payload=b"abc")
        assert (tmp_path / "one.mp3").read_bytes() == b"abc"
        assert (tmp_path / "two.mp3").read_bytes() == b"abc"

    def test_strips_directory_components_from_filenames(self, tmp_path, monkeypatch):
        response = _upload(["../../escape.mp3"], monkeypatch, tmp_path)
        assert response.status_code == 200
        assert (tmp_path / "escape.mp3").exists()
        assert not (tmp_path.parent.parent / "escape.mp3").exists()

    def test_each_drop_gets_a_distinct_session_id(self, tmp_path, monkeypatch):
        first = _upload(["a.mp3"], monkeypatch, tmp_path / "s1").json()
        second = _upload(["a.mp3"], monkeypatch, tmp_path / "s2").json()
        assert first["session_id"] != second["session_id"]


class TestScriptPayload:
    @pytest.fixture
    def video_scripts(self, tmp_path, monkeypatch):
        data = _upload(["clip.mp4"], monkeypatch, tmp_path).json()
        return {s["key"]: s for s in data["scripts"]}

    def test_directory_native_scripts_are_marked(self, video_scripts):
        assert video_scripts["av.join"]["batch_mode"] == "directory"
        assert video_scripts["formats.convert_video"]["batch_mode"] == "directory"

    def test_per_file_scripts_are_marked(self, video_scripts):
        assert video_scripts["av.trim"]["batch_mode"] == "per_file"
        assert video_scripts["av.volume"]["batch_mode"] == "per_file"

    def test_custom_template_is_flagged(self, video_scripts):
        assert video_scripts["av.trim"]["has_template"] is True
        assert video_scripts["av.volume"]["has_template"] is False

    def test_file_dest_is_exposed(self, video_scripts):
        assert video_scripts["av.trim"]["file_dest"] == "input"
        assert video_scripts["av.join"]["file_dest"] == "inputs"

    def test_icon_is_null_when_artwork_missing(self, video_scripts):
        assert video_scripts["av.trim"]["icon"] is None

    def test_icon_is_resolved_when_available(self, tmp_path, monkeypatch):
        data = _upload(["voice.mp3"], monkeypatch, tmp_path).json()
        scripts = {s["key"]: s for s in data["scripts"]}
        assert scripts["speech.transcribe"]["icon"] == "/static/icons/icon-speech.png"

    def test_category_icon_present_for_audio(self, tmp_path, monkeypatch):
        data = _upload(["voice.mp3"], monkeypatch, tmp_path).json()
        assert data["category_icon"] == "/static/icons/icon-audio.png"


class TestPastedImage:
    def test_pasted_filename_is_accepted(self, tmp_path, monkeypatch):
        response = _upload(["pasted-20260727-120000.png"], monkeypatch, tmp_path)
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "image"
        assert any(s["key"] == "photo.remove_bg" for s in data["scripts"])
        assert (tmp_path / "pasted-20260727-120000.png").exists()
