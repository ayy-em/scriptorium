"""Guards on the single inline icon set.

Icon names cross a template/Python boundary: ``webapp/_icons.py`` hands names
to the browser as JSON, and ``_icons.html`` is what turns them into glyphs.
Nothing else checks that the two agree, so these tests do.
"""

from __future__ import annotations

import re

from jinja2 import Environment, FileSystemLoader
import pytest

from core.categories import CATEGORY_EXTS
from core.paths import templates_dir
from core.registry import discover
from webapp._icons import CATEGORY_ICONS, SCRIPT_ICONS, icon_for_category, icon_for_script


@pytest.fixture(scope="module")
def jinja() -> Environment:
    return Environment(loader=FileSystemLoader(str(templates_dir())), autoescape=True)


@pytest.fixture(scope="module")
def sprite(jinja: Environment) -> str:
    """Render the full symbol sprite exactly as base.html emits it."""
    return jinja.get_template("_icons.html").module.icon_sprite()


@pytest.fixture(scope="module")
def sprite_names(sprite: str) -> set[str]:
    return set(re.findall(r'<symbol id="i-([a-z-]+)"', sprite))


@pytest.fixture(scope="module")
def theme_glyphs(jinja: Environment) -> dict[str, str]:
    return jinja.get_template("_macros.html").module.THEME_GLYPHS


class TestNameResolution:
    def test_unmapped_script_has_no_icon(self):
        assert icon_for_script("nosuch.script") is None

    def test_unknown_category_has_no_icon(self):
        assert icon_for_category("holograms") is None

    def test_missing_category_has_no_icon(self):
        assert icon_for_category(None) is None

    def test_names_are_not_urls(self):
        for name in (*SCRIPT_ICONS.values(), *CATEGORY_ICONS.values()):
            assert "/" not in name and not name.endswith(".png")


class TestSpriteCoverage:
    def test_sprite_is_not_empty(self, sprite_names):
        assert len(sprite_names) > 40

    def test_every_script_icon_exists(self, sprite_names):
        missing = {n for n in SCRIPT_ICONS.values() if n not in sprite_names}
        assert not missing

    def test_every_category_icon_exists(self, sprite_names):
        missing = {n for n in CATEGORY_ICONS.values() if n not in sprite_names}
        assert not missing

    def test_every_theme_glyph_exists(self, sprite_names, theme_glyphs):
        missing = {n for n in theme_glyphs.values() if n not in sprite_names}
        assert not missing

    def test_no_symbol_pins_a_stroke_width(self, sprite):
        """Consumers set the weight per size; a pinned stroke would override it."""
        assert "stroke-width" not in sprite.split("<symbol")[1].split(">")[0]


class TestMappingCompleteness:
    def test_every_file_category_has_an_icon(self):
        assert set(CATEGORY_EXTS) <= set(CATEGORY_ICONS)

    def test_every_theme_has_a_glyph(self, theme_glyphs):
        themes = {key.split(".", 1)[0] for key in discover()}
        assert themes <= set(theme_glyphs)
