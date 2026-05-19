"""End-to-end + CLI tests for scripts.telegram.chat_analysis."""

import json
import subprocess
import sys
import zipfile

from scripts.telegram.chat_analysis import _slugify, chat_analysis


class TestSlugify:
    def test_basic(self):
        assert _slugify("Alice Bob") == "alice_bob"

    def test_strips_punctuation(self):
        assert _slugify("J. M.") == "j_m"

    def test_fallback_for_empty(self):
        assert _slugify("!!!") == "chat"

    def test_truncates(self):
        assert len(_slugify("x" * 100)) <= 40


class TestChatAnalysisE2E:
    def test_produces_zip_with_expected_members(self, synthetic_chat_path, tmp_path):
        out_dir = tmp_path / "outputs"
        zip_path = chat_analysis(synthetic_chat_path, out_dir)
        assert zip_path.exists()
        assert zip_path.parent == out_dir
        assert zip_path.suffix == ".zip"

        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert "chat_analytics.json" in names
        assert "chat_analytics.pdf" in names
        chart_pngs = {n for n in names if n.startswith("charts/") and n.endswith(".png")}
        assert "charts/monthly_volume.png" in chart_pngs
        assert "charts/yearly_volume.png" in chart_pngs
        assert "charts/activity_heatmap.png" in chart_pngs
        assert "charts/message_share.png" in chart_pngs
        assert "charts/word_cloud.png" in chart_pngs
        assert "charts/emoji_cloud.png" in chart_pngs

    def test_json_payload_validates(self, synthetic_chat_path, tmp_path):
        out_dir = tmp_path / "outputs"
        zip_path = chat_analysis(synthetic_chat_path, out_dir)
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open("chat_analytics.json") as fh:
                analytics = json.load(fh)
        assert analytics["schema_version"] == 1
        assert analytics["source"]["chat_name"] == "Bob"
        assert analytics["totals"]["messages_all_time"] > 0
        # The PDF and the chart PNGs are non-empty
        with zipfile.ZipFile(zip_path) as zf:
            pdf_size = zf.getinfo("chat_analytics.pdf").file_size
            heatmap_size = zf.getinfo("charts/activity_heatmap.png").file_size
        assert pdf_size > 1000
        assert heatmap_size > 1000


class TestCliInvocation:
    def test_cli_runs_against_synthetic_fixture(self, synthetic_chat_path, tmp_path):
        out_dir = tmp_path / "cli_out"
        out_dir.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "telegram.chat_analysis",
                str(synthetic_chat_path),
                "--outputs",
                str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        zips = list(out_dir.glob("*.zip"))
        assert len(zips) == 1

    def test_cli_rejects_invalid_export(self, make_chat_export, tmp_path):
        bad = make_chat_export({"name": "Group", "type": "private_group", "id": 1, "messages": []})
        out_dir = tmp_path / "cli_out"
        out_dir.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "telegram.chat_analysis",
                str(bad),
                "--outputs",
                str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Unsupported chat type" in result.stderr
