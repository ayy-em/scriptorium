"""Custom ArgumentParser with web-UI hints and a startup arg banner.

When ``ui_label`` is passed to ``add_argument()``, it is stored on the
resulting action object and used by the web UI form generator as the
field label instead of the auto-derived flag name.

``ui_advanced=True`` marks an argument as expert-level: the web form puts it
behind a collapsed "Advanced options" section instead of in the main grid. It
changes nothing about the CLI, where every argument is equally visible.

``parse_args()`` is overridden to print resolved arguments to stderr
immediately after parsing, giving every script a startup arg banner
for free.
"""

import argparse
import sys


class ScriptoriumParser(argparse.ArgumentParser):
    """ArgumentParser subclass with ``ui_label`` and startup arg banner.

    Usage::

        parser = ScriptoriumParser(...)
        parser.add_argument("--audio", action="store_true", ui_label="Audio only")
        parser.add_argument("--tune", ui_advanced=True)
    """

    def add_argument(self, *args, **kwargs):
        """Pop the UI hints before delegating to the standard add_argument.

        Args:
            *args: Positional args forwarded to ``ArgumentParser.add_argument``.
            **kwargs: Keyword args forwarded to ``ArgumentParser.add_argument``.
                ``ui_label`` and ``ui_advanced`` are extracted and stored on the
                action object; argparse itself would reject them.

        Returns:
            The created ``argparse.Action``, with ``ui_label`` and
            ``ui_advanced`` attributes attached.
        """
        ui_label = kwargs.pop("ui_label", None)
        ui_advanced = kwargs.pop("ui_advanced", False)
        action = super().add_argument(*args, **kwargs)
        action.ui_label = ui_label  # type: ignore[attr-defined]
        action.ui_advanced = ui_advanced  # type: ignore[attr-defined]
        return action

    def parse_args(self, args=None, namespace=None):
        """Parse arguments and print resolved values to stderr.

        Args:
            args: Argument strings to parse (default: ``sys.argv[1:]``).
            namespace: Pre-existing namespace to populate.

        Returns:
            The populated ``argparse.Namespace``.
        """
        result = super().parse_args(args, namespace)
        items = vars(result)
        if items:
            for key, val in items.items():
                print(f"  {key} = {val}", file=sys.stderr)
        return result
