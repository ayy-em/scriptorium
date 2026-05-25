"""Custom ArgumentParser with ``ui_label`` support and startup arg banner.

When ``ui_label`` is passed to ``add_argument()``, it is stored on the
resulting action object and used by the web UI form generator as the
field label instead of the auto-derived flag name.

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
    """

    def add_argument(self, *args, **kwargs):
        """Pop ``ui_label`` before delegating to the standard add_argument.

        Args:
            *args: Positional args forwarded to ``ArgumentParser.add_argument``.
            **kwargs: Keyword args forwarded to ``ArgumentParser.add_argument``.
                ``ui_label`` is extracted and stored on the action object.

        Returns:
            The created ``argparse.Action`` with an additional ``ui_label`` attribute.
        """
        ui_label = kwargs.pop("ui_label", None)
        action = super().add_argument(*args, **kwargs)
        action.ui_label = ui_label  # type: ignore[attr-defined]
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
