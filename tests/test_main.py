"""Tests for the CLI listings in main.py."""

import types
from unittest.mock import patch

import pytest

import main


def _module(title: str, *, ui_only: bool = False) -> types.ModuleType:
    mod = types.ModuleType("stub")
    mod.TITLE = title
    mod.DESCRIPTION = "does a thing"
    mod.run = lambda: None
    if ui_only:
        mod.UI_ONLY = True
    return mod


class TestListings:
    def test_all_scripts_listing_marks_ui_only(self, capsys: pytest.CaptureFixture[str]):
        scripts = {"photo.crop": _module("Crop", ui_only=True), "photo.tiny": _module("Tiny")}
        with patch.object(main, "discover", return_value=scripts):
            main._list()
        out = capsys.readouterr().out
        assert "Crop (web UI only)" in out
        assert "Tiny (web UI only)" not in out

    def test_theme_listing_marks_ui_only(self, capsys: pytest.CaptureFixture[str]):
        themes = {"photo": {"crop": _module("Crop", ui_only=True), "tiny": _module("Tiny")}}
        with (
            patch.object(main, "discover_themes", return_value=themes),
            patch.object(main, "theme_descriptions", return_value={}),
        ):
            main._list_theme("photo")
        out = capsys.readouterr().out
        assert "photo.crop" in out
        assert "Crop (web UI only)" in out
        assert "Tiny (web UI only)" not in out
