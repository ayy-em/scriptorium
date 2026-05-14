"""Argparse introspection utilities for auto-generating web forms."""

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FieldSpec:
    """Describes a single form field derived from an argparse action.

    Attributes:
        dest: Argparse dest name, used as the HTML form field name.
        label: Human-readable label for the form field.
        help: Help text shown below the field.
        widget: HTML widget type — "text", "number", "checkbox", "select", or "textarea".
        required: Whether the field must be filled in.
        default: Default value as a string, or None.
        choices: Allowed values for "select" widgets, or None.
        is_positional: True if this is a positional (not optional) argument.
        multiple: True if the field accepts multiple values (nargs='+' or nargs='*').
        flag: The longest option string (e.g. "--outputs") for optional args, or None.
    """

    dest: str
    label: str
    help: str
    widget: str
    required: bool
    default: str | None
    choices: list[str] | None
    is_positional: bool
    multiple: bool
    flag: str | None


def fields_from_parser(parser: argparse.ArgumentParser) -> list[FieldSpec]:
    """Extract form field descriptors from an ArgumentParser's registered actions.

    Skips help actions. nargs='+' and nargs='*' actions are rendered as
    textareas (one value per line).

    Args:
        parser: An ArgumentParser whose actions describe a script's interface.

    Returns:
        List of FieldSpec instances in declaration order, ready for template rendering.
    """
    specs: list[FieldSpec] = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue

        is_positional = not action.option_strings
        flag = max(action.option_strings, key=len) if action.option_strings else None
        multiple = action.nargs in ("+", "*")

        ui_label = getattr(action, "ui_label", None)

        if is_positional:
            required = action.nargs not in ("?", "*")
            label = ui_label or action.dest.replace("_", " ").capitalize()
        else:
            required = bool(getattr(action, "required", False))
            label = ui_label or flag.lstrip("-").replace("-", " ").capitalize()  # type: ignore[union-attr]

        default: str | None = None
        if action.default not in (None, argparse.SUPPRESS):
            default = str(action.default)

        choices = [str(c) for c in action.choices] if action.choices else None

        specs.append(
            FieldSpec(
                dest=action.dest,
                label=label,
                help=action.help or "",
                widget=_widget_for(action),
                required=required,
                default=default,
                choices=choices,
                is_positional=is_positional,
                multiple=multiple,
                flag=flag,
            )
        )

    return specs


def _widget_for(action: argparse.Action) -> str:
    """Determine the HTML widget type for an argparse action.

    Args:
        action: An argparse action to classify.

    Returns:
        Widget type string: "checkbox", "select", "textarea", "number", or "text".
    """
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "checkbox"
    if action.choices:
        return "select"
    if action.nargs in ("+", "*"):
        return "textarea"
    if action.type in (int, float):
        return "number"
    if action.type is Path and action.dest not in ("outputs", "inputs"):
        return "file-multi" if action.nargs == "?" else "file"
    return "text"


def build_argv(form_data: dict[str, str], field_specs: list[FieldSpec]) -> list[str]:
    """Build a CLI argv list from HTML form data and field specifications.

    Translates form field values back into positional arguments and --flags
    suitable for passing to main.py as subprocess arguments.

    Args:
        form_data: Raw form values keyed by field dest name.
        field_specs: Field descriptors from fields_from_parser().

    Returns:
        List of string arguments to pass after the script key.
    """
    argv: list[str] = []

    for spec in field_specs:
        raw = form_data.get(spec.dest, "").strip()

        if spec.widget == "checkbox":
            if raw in ("on", "true", "1", "yes"):
                argv.append(spec.flag)  # type: ignore[arg-type]
            continue

        if not raw:
            continue

        if spec.is_positional:
            if spec.multiple:
                argv.extend(v for v in (line.strip() for line in raw.splitlines()) if v)
            else:
                argv.append(raw)
        elif spec.multiple:
            values = [v for v in (line.strip() for line in raw.splitlines()) if v]
            if values:
                argv.append(spec.flag)  # type: ignore[arg-type]
                argv.extend(values)
        else:
            argv.append(spec.flag)  # type: ignore[arg-type]
            argv.append(raw)

    return argv
