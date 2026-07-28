"""Tests for scripts.av.filmstrip layout maths and grid parsing."""

import pytest

from scripts.av.filmstrip import _compute_layout, _parse_grid


class TestParseGrid:
    def test_parses_rows_and_cols(self):
        assert _parse_grid("3x3") == (3, 3)

    def test_parses_non_square(self):
        assert _parse_grid("2x5") == (2, 5)

    def test_is_case_insensitive(self):
        assert _parse_grid("4X6") == (4, 6)

    @pytest.mark.parametrize("bad", ["3", "3x3x3", ""])
    def test_rejects_wrong_field_count(self, bad):
        with pytest.raises(ValueError, match="ROWSxCOLS"):
            _parse_grid(bad)

    @pytest.mark.parametrize("bad", ["axb", "3xb"])
    def test_rejects_non_numeric(self, bad):
        with pytest.raises(ValueError, match="ROWSxCOLS"):
            _parse_grid(bad)

    @pytest.mark.parametrize("bad", ["0x3", "3x0", "-1x3"])
    def test_rejects_non_positive(self, bad):
        with pytest.raises(ValueError, match=">= 1"):
            _parse_grid(bad)


class TestComputeLayout:
    def test_landscape_fills_the_landscape_box_width(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        assert (layout.frame_w, layout.frame_h) == (400, 225)

    def test_portrait_fills_the_narrower_portrait_box(self):
        layout = _compute_layout(1080, 1920, 3, 3)
        assert (layout.frame_w, layout.frame_h) == (180, 320)

    def test_portrait_uses_tighter_horizontal_spacing(self):
        """Portrait frames are narrow, so wide gaps leave the sheet mostly margin."""
        portrait = _compute_layout(1080, 1920, 3, 3)
        landscape = _compute_layout(1920, 1080, 3, 3)
        assert portrait.gap_x < landscape.gap_x
        assert portrait.pad_x < landscape.pad_x

    def test_aspect_ratio_is_preserved(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        assert layout.frame_w / layout.frame_h == pytest.approx(1920 / 1080, rel=0.01)

    def test_frames_never_exceed_their_box(self):
        for w, h in [(1920, 1080), (1080, 1920), (1000, 1000), (3840, 1600), (640, 480)]:
            layout = _compute_layout(w, h, 3, 3)
            box = (180, 400) if h > w else (400, 300)
            assert layout.frame_w <= box[0] + 1
            assert layout.frame_h <= box[1] + 1

    def test_canvas_width_accounts_for_padding_and_gaps(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        expected = 2 * layout.pad_x + 3 * layout.frame_w + 2 * layout.gap_x
        assert layout.canvas_w == expected

    def test_cell_height_leaves_room_for_the_label(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        assert layout.cell_h > layout.frame_h

    def test_grid_starts_below_the_header(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        assert layout.grid_top > 56  # _HEADER_H

    def test_more_columns_widen_the_canvas(self):
        assert _compute_layout(1920, 1080, 2, 5).canvas_w > _compute_layout(1920, 1080, 2, 3).canvas_w

    def test_more_rows_heighten_the_canvas(self):
        assert _compute_layout(1920, 1080, 4, 3).canvas_h > _compute_layout(1920, 1080, 2, 3).canvas_h

    def test_grid_shape_does_not_change_frame_size(self):
        """Frame scaling depends on the source aspect only, not the grid."""
        a = _compute_layout(1920, 1080, 3, 3)
        b = _compute_layout(1920, 1080, 2, 5)
        assert (a.frame_w, a.frame_h) == (b.frame_w, b.frame_h)

    def test_known_landscape_geometry(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        assert (layout.canvas_w, layout.canvas_h) == (1280, 875)

    def test_known_portrait_geometry(self):
        layout = _compute_layout(1080, 1920, 3, 3)
        assert (layout.canvas_w, layout.canvas_h) == (576, 1160)

    def test_layout_is_immutable(self):
        layout = _compute_layout(1920, 1080, 3, 3)
        with pytest.raises(AttributeError):
            layout.frame_w = 1
