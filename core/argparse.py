"""Custom ArgumentParser that supports a ``ui_label`` kwarg on arguments.

When ``ui_label`` is passed to ``add_argument()``, it is stored on the
resulting action object and used by the web UI form generator as the
field label instead of the auto-derived flag name.
"""

import argparse


class ScriptoriumParser(argparse.ArgumentParser):
    """ArgumentParser subclass that accepts ``ui_label`` on arguments.

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
