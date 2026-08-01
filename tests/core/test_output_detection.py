"""Tests for reading a run's outputs back out of what it printed.

Scripts report results inconsistently — ``print(out)`` in most, a sentence in
others, nothing at all in a few — so this is a heuristic and its edges matter
more than its happy path.
"""

from core.outputs import find_reported_outputs


class TestFindReportedOutputs:
    def _tree(self, tmp_path):
        root = tmp_path / "outputs"
        (root / "av").mkdir(parents=True)
        return root

    def test_finds_a_bare_printed_path(self, tmp_path):
        root = self._tree(tmp_path)
        f = root / "av" / "clip.mp4"
        f.write_text("x")
        assert find_reported_outputs([str(f)], root) == [f.resolve()]

    def test_finds_a_path_inside_a_sentence(self, tmp_path):
        root = self._tree(tmp_path)
        f = root / "av" / "clip.mp4"
        f.write_text("x")
        assert find_reported_outputs([f"wrote {f} ok"], root) == [f.resolve()]

    def test_finds_a_path_containing_spaces(self, tmp_path):
        """Whole-line matching is what makes this work; tokenising cannot."""
        root = self._tree(tmp_path)
        f = root / "av" / "my clip.mp4"
        f.write_text("x")
        assert find_reported_outputs([str(f)], root) == [f.resolve()]

    def test_ignores_files_outside_the_outputs_root(self, tmp_path):
        """A script echoing its input must not be credited with writing it."""
        root = self._tree(tmp_path)
        outsider = tmp_path / "elsewhere.mp4"
        outsider.write_text("x")
        assert find_reported_outputs([str(outsider)], root) == []

    def test_ignores_paths_that_do_not_exist(self, tmp_path):
        root = self._tree(tmp_path)
        assert find_reported_outputs([str(root / "av" / "ghost.mp4")], root) == []

    def test_ignores_directories(self, tmp_path):
        root = self._tree(tmp_path)
        assert find_reported_outputs([str(root / "av")], root) == []

    def test_ignores_ordinary_prose(self, tmp_path):
        root = self._tree(tmp_path)
        lines = ["Converting...", "", "  ", "done in 1.2s", "100%|####| 3/3"]
        assert find_reported_outputs(lines, root) == []

    def test_reports_each_file_once_in_first_mention_order(self, tmp_path):
        root = self._tree(tmp_path)
        a, b = root / "av" / "a.mp4", root / "av" / "b.mp4"
        a.write_text("x")
        b.write_text("x")
        lines = [str(b), str(a), f"wrote {b}"]
        assert find_reported_outputs(lines, root) == [b.resolve(), a.resolve()]

    def test_strips_surrounding_quotes(self, tmp_path):
        root = self._tree(tmp_path)
        f = root / "av" / "clip.mp4"
        f.write_text("x")
        assert find_reported_outputs([f'"{f}"'], root) == [f.resolve()]

    def test_a_traversal_string_does_not_escape_the_root(self, tmp_path):
        root = self._tree(tmp_path)
        outsider = tmp_path / "secret.txt"
        outsider.write_text("x")
        escape = root / ".." / "secret.txt"
        assert find_reported_outputs([str(escape)], root) == []

    def test_empty_input_is_fine(self, tmp_path):
        assert find_reported_outputs([], self._tree(tmp_path)) == []
