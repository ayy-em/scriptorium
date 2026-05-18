"""Integration test against the user-provided real Telegram export.

Skipped automatically if ``tests/telegram/fixtures/chat_export/result.json``
is absent — which is the case on CI and on fresh clones.
"""

import json
import zipfile

from scripts.telegram.chat_analysis import chat_analysis


def test_real_export_runs_end_to_end(real_export_path, tmp_path):
    out_dir = tmp_path / "real_outputs"
    zip_path = chat_analysis(real_export_path, out_dir)
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "chat_analytics.json" in names
        assert "chat_analytics.pdf" in names
        with zf.open("chat_analytics.json") as fh:
            analytics = json.load(fh)
    assert analytics["totals"]["messages_all_time"] > 0
    assert len(analytics["participants"]) == 2
