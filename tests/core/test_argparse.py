"""Tests for ScriptoriumParser ui_label support."""

from core.argparse import ScriptoriumParser


class TestScriptoriumParser:
    def test_ui_label_stored_on_action(self):
        parser = ScriptoriumParser()
        action = parser.add_argument("--audio", action="store_true", ui_label="Audio only")
        assert action.ui_label == "Audio only"

    def test_ui_label_defaults_to_none(self):
        parser = ScriptoriumParser()
        action = parser.add_argument("--verbose", action="store_true")
        assert action.ui_label is None

    def test_ui_label_on_positional(self):
        parser = ScriptoriumParser()
        action = parser.add_argument("source", ui_label="Source file")
        assert action.ui_label == "Source file"

    def test_ui_label_does_not_break_parsing(self):
        parser = ScriptoriumParser()
        parser.add_argument("--audio", action="store_true", ui_label="Audio only")
        parser.add_argument("url")
        args = parser.parse_args(["https://example.com", "--audio"])
        assert args.audio is True
        assert args.url == "https://example.com"

    def test_mixed_labelled_and_unlabelled(self):
        parser = ScriptoriumParser()
        a1 = parser.add_argument("--audio", action="store_true", ui_label="Audio only")
        a2 = parser.add_argument("--verbose", action="store_true")
        assert a1.ui_label == "Audio only"
        assert a2.ui_label is None
