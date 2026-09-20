"""Contract test for how scripts treat the files they are given.

Archiving used to be decided per script, and the result was three behaviours at
once: most scripts left the input alone, ``formats.*`` and ``photo.remove_bg``
archived it through a guarded helper, and ``av.join`` hand-rolled a
``processed/`` directory next to whatever the user pointed at and moved their
files into it. That last one made "run this against my media library" a
destructive act.

The rule now is one sentence: a script that consumes a file archives it with
``core.paths.move_to_past_inputs``, which moves it only if it was staged inside
the shared inputs tree. This test pins the inventory so that adding a script
forces a decision rather than inheriting whichever behaviour was copied.
"""

import ast
from pathlib import Path

import pytest

from core.registry import discover

# Scripts that consume a file and must file it away when they are done with it.
ARCHIVING = {
    "av.dump_frames",
    "av.filmstrip",
    "av.join",
    "av.split",
    "av.tag",
    "av.to_anim",
    "av.trim",
    "av.video_crop",
    "av.volume",
    "formats.convert_audio",
    "formats.convert_docs",
    "formats.convert_image",
    "formats.convert_tabular",
    "formats.convert_video",
    "photo.remove_bg",
    "speech.transcribe",
    "telegram.group_analysis",
}

# Why each of the rest does not archive. A reason, not an exemption list: a new
# entry here is a claim someone can check.
NOT_ARCHIVING = {
    "downloads.download": "takes a URL, not a file",
    "sitemaps.status_check": "takes a URL, not a file",
    "util.cleanup": "manages the archive itself",
    "util.notify": "takes a message, not a file",
    "gif.make_gif": (
        "reads a directory of frames; flattening a frame set into the archive root would "
        "collide on every frame_001.png, and the frames get re-rendered at other settings"
    ),
    "lora.export_captions": "operates on a dataset directory in place",
    "lora.import_captions": "operates on a dataset directory in place",
    "lora.renumber": "operates on a dataset directory in place",
    "lora.validate": "reads a dataset without consuming it",
    "telegram.preprocess": "first step of a chain; embed_messages reads what it was given",
    "telegram.embed_messages": "middle of a chain; the export is read again by the analyses",
    "telegram.chat_analysis": "re-reads the same export on every run",
}

# The guarded helper. Anything else moving an input is the bug this test exists
# to catch.
HELPER = "move_to_past_inputs"


def _source_of(key: str) -> str:
    """Return the source text of a script module, by registry key."""
    theme, name = key.split(".", 1)
    return (Path("scripts") / theme / f"{name}.py").read_text(encoding="utf-8")


def _calls(source: str, name: str) -> bool:
    """Report whether *source* calls a function called *name*."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
            return True
    return False


def test_the_inventory_covers_every_discovered_script():
    """A new script must be classified, not silently default to either behaviour."""
    unclassified = set(discover()) - ARCHIVING - set(NOT_ARCHIVING)
    assert unclassified == set(), "unclassified script(s): decide whether they archive their input"


def test_the_inventory_does_not_name_scripts_that_are_gone():
    """Checked against the filesystem, not discovery.

    ``discover()`` skips hidden themes (``util``) and anything whose optional
    dependencies are not installed (``telegram.group_analysis`` without
    ``emoji``), so a discovery-based check would quietly stop covering exactly
    the scripts most likely to drift.
    """
    theme_and_name = (key.split(".", 1) for key in ARCHIVING | set(NOT_ARCHIVING))
    missing = [
        f"{theme}.{name}" for theme, name in theme_and_name if not (Path("scripts") / theme / f"{name}.py").is_file()
    ]
    assert missing == [], "inventory names script(s) that no longer exist"


@pytest.mark.parametrize("key", sorted(ARCHIVING))
def test_consuming_scripts_archive_through_the_guarded_helper(key):
    source = _source_of(key)
    # formats.* share one implementation in _utils.run_convert rather than
    # each calling the helper themselves.
    if key.startswith("formats."):
        source = Path("scripts/formats/_utils.py").read_text(encoding="utf-8")
    assert _calls(source, HELPER), f"{key} consumes a file but never archives it"


@pytest.mark.parametrize("key", sorted(NOT_ARCHIVING))
def test_non_consuming_scripts_leave_their_input_alone(key):
    assert not _calls(_source_of(key), HELPER), f"{key} archives despite {NOT_ARCHIVING[key]}"


@pytest.mark.parametrize("key", sorted(ARCHIVING | set(NOT_ARCHIVING)))
def test_no_script_moves_an_input_by_hand(key):
    """``shutil.move`` on an input is how av.join came to write into ~/Videos.

    Scripts may still move their own temporary files — ``av.tag`` swaps a temp
    file over the original for ``--in-place`` — so this looks for the specific
    shape that went wrong: a ``processed`` directory built by a script.
    """
    source = _source_of(key)
    assert '"processed"' not in source and "'processed'" not in source, (
        f"{key} builds its own processed/ directory; use {HELPER} so paths outside inputs/ are left alone"
    )
