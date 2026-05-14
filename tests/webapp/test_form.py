"""Tests for argparse → form field introspection."""

import argparse
from pathlib import Path

from core.argparse import ScriptoriumParser
from webapp._form import FieldSpec, build_argv, fields_from_parser


def _parser(**kwargs) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(**kwargs)


class TestFieldsFromParser:
    def test_skips_help_action(self):
        parser = _parser()
        fields = fields_from_parser(parser)
        assert all(f.dest != "help" for f in fields)

    def test_positional_text(self):
        parser = _parser()
        parser.add_argument("source")
        (f,) = fields_from_parser(parser)
        assert f.dest == "source"
        assert f.is_positional is True
        assert f.widget == "text"
        assert f.required is True
        assert f.flag is None

    def test_positional_path_is_file_widget(self):
        parser = _parser()
        parser.add_argument("path", type=Path)
        (f,) = fields_from_parser(parser)
        assert f.widget == "file"

    def test_outputs_path_is_text_widget(self):
        parser = _parser()
        parser.add_argument("--outputs", type=Path)
        (f,) = fields_from_parser(parser)
        assert f.widget == "text"

    def test_positional_optional_nargs_question_mark(self):
        parser = _parser()
        parser.add_argument("output", nargs="?", default=None)
        (f,) = fields_from_parser(parser)
        assert f.required is False
        assert f.multiple is False

    def test_positional_nargs_plus_is_textarea(self):
        parser = _parser()
        parser.add_argument("timestamps", nargs="+")
        (f,) = fields_from_parser(parser)
        assert f.widget == "textarea"
        assert f.multiple is True
        assert f.required is True

    def test_positional_nargs_star_not_required(self):
        parser = _parser()
        parser.add_argument("items", nargs="*")
        (f,) = fields_from_parser(parser)
        assert f.required is False
        assert f.multiple is True

    def test_optional_text_with_default(self):
        parser = _parser()
        parser.add_argument("--name", default="alice")
        (f,) = fields_from_parser(parser)
        assert f.dest == "name"
        assert f.is_positional is False
        assert f.widget == "text"
        assert f.required is False
        assert f.default == "alice"
        assert f.flag == "--name"

    def test_optional_required_flag(self):
        parser = _parser()
        parser.add_argument("--to", required=True)
        (f,) = fields_from_parser(parser)
        assert f.required is True

    def test_choices_produce_select_widget(self):
        parser = _parser()
        parser.add_argument("--quality", choices=["low", "medium", "high"], default="medium")
        (f,) = fields_from_parser(parser)
        assert f.widget == "select"
        assert f.choices == ["low", "medium", "high"]
        assert f.default == "medium"

    def test_store_true_produces_checkbox(self):
        parser = _parser()
        parser.add_argument("--verbose", action="store_true")
        (f,) = fields_from_parser(parser)
        assert f.widget == "checkbox"
        assert f.required is False

    def test_store_false_produces_checkbox(self):
        parser = _parser()
        parser.add_argument("--no-cache", action="store_false", dest="cache")
        (f,) = fields_from_parser(parser)
        assert f.widget == "checkbox"

    def test_int_type_produces_number(self):
        parser = _parser()
        parser.add_argument("--count", type=int, default=5)
        (f,) = fields_from_parser(parser)
        assert f.widget == "number"
        assert f.default == "5"

    def test_float_type_produces_number(self):
        parser = _parser()
        parser.add_argument("--speed", type=float, default=1.0)
        (f,) = fields_from_parser(parser)
        assert f.widget == "number"

    def test_label_uses_longest_flag(self):
        parser = _parser()
        parser.add_argument("-o", "--output")
        (f,) = fields_from_parser(parser)
        assert f.flag == "--output"
        assert f.label == "Output"

    def test_hyphenated_flag_label(self):
        parser = _parser()
        parser.add_argument("--fade-in", type=float, dest="fade_in")
        (f,) = fields_from_parser(parser)
        assert f.label == "Fade in"

    def test_default_none_not_serialised(self):
        parser = _parser()
        parser.add_argument("--path", type=Path, default=None)
        (f,) = fields_from_parser(parser)
        assert f.default is None

    def test_order_preserved(self):
        parser = _parser()
        parser.add_argument("source")
        parser.add_argument("start")
        parser.add_argument("end")
        names = [f.dest for f in fields_from_parser(parser)]
        assert names == ["source", "start", "end"]

    def test_ui_label_overrides_optional_flag(self):
        parser = ScriptoriumParser()
        parser.add_argument("--audio", action="store_true", ui_label="Audio only")
        (f,) = fields_from_parser(parser)
        assert f.label == "Audio only"

    def test_ui_label_overrides_positional(self):
        parser = ScriptoriumParser()
        parser.add_argument("source", ui_label="Source file")
        (f,) = fields_from_parser(parser)
        assert f.label == "Source file"

    def test_no_ui_label_falls_back(self):
        parser = ScriptoriumParser()
        parser.add_argument("--fade-in", type=float, dest="fade_in")
        (f,) = fields_from_parser(parser)
        assert f.label == "Fade in"


class TestBuildArgv:
    def _specs(self, parser: argparse.ArgumentParser) -> list[FieldSpec]:
        return fields_from_parser(parser)

    def test_positional_single(self):
        parser = _parser()
        parser.add_argument("source")
        specs = self._specs(parser)
        assert build_argv({"source": "video.mp4"}, specs) == ["video.mp4"]

    def test_positional_multiple(self):
        parser = _parser()
        parser.add_argument("timestamps", nargs="+")
        specs = self._specs(parser)
        result = build_argv({"timestamps": "00:01:00\n00:02:00"}, specs)
        assert result == ["00:01:00", "00:02:00"]

    def test_optional_with_value(self):
        parser = _parser()
        parser.add_argument("--to")
        specs = self._specs(parser)
        assert build_argv({"to": "mp4"}, specs) == ["--to", "mp4"]

    def test_optional_empty_skipped(self):
        parser = _parser()
        parser.add_argument("--to")
        specs = self._specs(parser)
        assert build_argv({"to": ""}, specs) == []

    def test_checkbox_checked(self):
        parser = _parser()
        parser.add_argument("--verbose", action="store_true")
        specs = self._specs(parser)
        assert build_argv({"verbose": "on"}, specs) == ["--verbose"]

    def test_checkbox_unchecked(self):
        parser = _parser()
        parser.add_argument("--verbose", action="store_true")
        specs = self._specs(parser)
        assert build_argv({"verbose": ""}, specs) == []

    def test_select_value(self):
        parser = _parser()
        parser.add_argument("--quality", choices=["low", "high"], default="low")
        specs = self._specs(parser)
        assert build_argv({"quality": "high"}, specs) == ["--quality", "high"]

    def test_number_value(self):
        parser = _parser()
        parser.add_argument("--count", type=int)
        specs = self._specs(parser)
        assert build_argv({"count": "5"}, specs) == ["--count", "5"]

    def test_unknown_keys_ignored(self):
        parser = _parser()
        parser.add_argument("source")
        specs = self._specs(parser)
        assert build_argv({"source": "a.mp4", "bogus": "x"}, specs) == ["a.mp4"]

    def test_multiline_values_split(self):
        parser = _parser()
        parser.add_argument("items", nargs="*")
        specs = self._specs(parser)
        result = build_argv({"items": "a\nb\n\nc"}, specs)
        assert result == ["a", "b", "c"]

    def test_optional_nargs_plus(self):
        parser = _parser()
        parser.add_argument("--files", nargs="+")
        specs = self._specs(parser)
        result = build_argv({"files": "a.txt\nb.txt"}, specs)
        assert result == ["--files", "a.txt", "b.txt"]

    def test_positional_order(self):
        parser = _parser()
        parser.add_argument("input")
        parser.add_argument("output")
        specs = self._specs(parser)
        result = build_argv({"input": "in.mp4", "output": "out.mp4"}, specs)
        assert result == ["in.mp4", "out.mp4"]
