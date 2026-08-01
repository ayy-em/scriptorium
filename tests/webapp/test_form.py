"""Tests for argparse → form field introspection."""

import argparse
import importlib
import json
from pathlib import Path

from core.argparse import ScriptoriumParser
from core.registry import discover
from webapp._form import (
    FieldSpec,
    accepts_directory,
    batch_mode_for,
    build_argv,
    field_specs_payload,
    fields_from_parser,
    file_input_for,
    spans_full_row,
)


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


class TestFileInputFor:
    def test_finds_positional_file(self):
        parser = _parser()
        parser.add_argument("input", type=Path)
        spec = file_input_for(fields_from_parser(parser))
        assert spec is not None
        assert spec.dest == "input"

    def test_finds_inputs_flag_when_no_positional_file(self):
        parser = _parser()
        parser.add_argument("--inputs", type=Path)
        parser.add_argument("--order", choices=["a", "b"])
        spec = file_input_for(fields_from_parser(parser))
        assert spec is not None
        assert spec.dest == "inputs"

    def test_returns_none_when_script_takes_no_file(self):
        parser = _parser()
        parser.add_argument("--count", type=int)
        assert file_input_for(fields_from_parser(parser)) is None

    def test_ignores_non_file_positionals(self):
        parser = _parser()
        parser.add_argument("start")
        parser.add_argument("source", type=Path)
        spec = file_input_for(fields_from_parser(parser))
        assert spec.dest == "source"


class TestAcceptsDirectory:
    def test_true_for_optional_path_positional(self):
        parser = _parser()
        parser.add_argument("source", type=Path, nargs="?")
        assert accepts_directory(file_input_for(fields_from_parser(parser))) is True

    def test_false_for_required_single_file(self):
        parser = _parser()
        parser.add_argument("input", type=Path)
        assert accepts_directory(file_input_for(fields_from_parser(parser))) is False

    def test_true_for_inputs_flag(self):
        parser = _parser()
        parser.add_argument("--inputs", type=Path)
        assert accepts_directory(file_input_for(fields_from_parser(parser))) is True

    def test_false_for_none(self):
        assert accepts_directory(None) is False


class TestBatchModeFor:
    def test_directory_when_input_takes_a_folder(self):
        parser = _parser()
        parser.add_argument("source", type=Path, nargs="?")
        assert batch_mode_for(fields_from_parser(parser)) == "directory"

    def test_per_file_for_single_file_input(self):
        parser = _parser()
        parser.add_argument("input", type=Path)
        assert batch_mode_for(fields_from_parser(parser)) == "per_file"

    def test_per_file_when_no_file_input(self):
        parser = _parser()
        parser.add_argument("--count", type=int)
        assert batch_mode_for(fields_from_parser(parser)) == "per_file"


class TestRealScriptClassification:
    """Guards the 7 directory-native / 10 per-file split the chooser relies on."""

    def _mode(self, key):
        mod = importlib.import_module(f"scripts.{key}")
        return batch_mode_for(fields_from_parser(mod.get_parser()))

    def test_join_is_directory_native(self):
        assert self._mode("av.join") == "directory"

    def test_converters_are_directory_native(self):
        assert self._mode("formats.convert_video") == "directory"
        assert self._mode("formats.convert_audio") == "directory"

    def test_remove_bg_is_directory_native(self):
        assert self._mode("photo.remove_bg") == "directory"

    def test_trim_is_per_file(self):
        assert self._mode("av.trim") == "per_file"

    def test_transcribe_is_per_file(self):
        assert self._mode("speech.transcribe") == "per_file"


class TestFieldSpecsPayload:
    def test_adds_accepts_dir_flag(self):
        parser = _parser()
        parser.add_argument("source", type=Path, nargs="?")
        payload = field_specs_payload(fields_from_parser(parser))
        assert payload[0]["accepts_dir"] is True

    def test_preserves_every_spec_attribute(self):
        parser = _parser()
        parser.add_argument("--quality", choices=["low", "high"], default="low")
        payload = field_specs_payload(fields_from_parser(parser))
        entry = payload[0]
        assert entry["dest"] == "quality"
        assert entry["choices"] == ["low", "high"]
        assert entry["default"] == "low"
        assert entry["widget"] == "select"

    def test_is_json_serialisable(self):
        parser = _parser()
        parser.add_argument("input", type=Path)
        json.dumps(field_specs_payload(fields_from_parser(parser)))


class TestSpansFullRow:
    """Path fields get the whole row — half a row hides the ends of a path."""

    def _spec(self, dest, widget="text"):
        return FieldSpec(
            dest=dest,
            label=dest,
            help="",
            widget=widget,
            required=False,
            default=None,
            choices=None,
            is_positional=False,
            multiple=False,
            flag=f"--{dest}",
        )

    def test_output_field_is_full_width(self):
        assert spans_full_row(self._spec("output")) is True

    def test_directory_flags_are_full_width(self):
        assert spans_full_row(self._spec("inputs")) is True
        assert spans_full_row(self._spec("outputs")) is True

    def test_textarea_is_full_width(self):
        assert spans_full_row(self._spec("terms", widget="textarea")) is True

    def test_ordinary_fields_share_a_row(self):
        assert spans_full_row(self._spec("model", widget="select")) is False
        assert spans_full_row(self._spec("quality", widget="number")) is False
        assert spans_full_row(self._spec("alpha_matting", widget="checkbox")) is False


class TestEveryOutputFieldIsFullWidth:
    def test_no_script_renders_a_half_width_output(self):
        """Catches a script whose output flag uses an unexpected dest."""
        offenders = []
        for key, mod in discover().items():
            if not hasattr(mod, "get_parser"):
                continue
            for spec in fields_from_parser(mod.get_parser()):
                looks_like_a_path = spec.flag in ("--output", "--outputs", "--inputs")
                if looks_like_a_path and not spans_full_row(spec):
                    offenders.append(f"{key}:{spec.dest}")
        assert offenders == [], f"half-width path fields: {offenders}"
