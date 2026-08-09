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


class TestFindReportedOutputsSince:
    """Results written outside the managed tree still count.

    A file the user sent to ``~/Downloads`` is theirs to see. Modification time
    is what separates it from an input the script merely echoed.
    """

    def _tree(self, tmp_path):
        root = tmp_path / "outputs"
        (root / "av").mkdir(parents=True)
        return root

    def test_file_outside_the_root_written_during_the_run_is_reported(self, tmp_path):
        root = self._tree(tmp_path)
        elsewhere = tmp_path / "Downloads" / "transc.txt"
        elsewhere.parent.mkdir()
        elsewhere.write_text("x")
        started = elsewhere.stat().st_mtime - 1
        assert find_reported_outputs([str(elsewhere)], root, since=started) == [elsewhere.resolve()]

    def test_file_outside_the_root_predating_the_run_is_ignored(self, tmp_path):
        """This is the echoed-input case the root check used to cover alone."""
        root = self._tree(tmp_path)
        source = tmp_path / "input.m4a"
        source.write_text("x")
        started = source.stat().st_mtime + 60
        assert find_reported_outputs([str(source)], root, since=started) == []

    def test_a_file_in_the_root_still_counts_regardless_of_age(self, tmp_path):
        root = self._tree(tmp_path)
        f = root / "av" / "clip.mp4"
        f.write_text("x")
        started = f.stat().st_mtime + 60
        assert find_reported_outputs([str(f)], root, since=started) == [f.resolve()]

    def test_without_since_the_root_is_still_the_only_test(self, tmp_path):
        root = self._tree(tmp_path)
        elsewhere = tmp_path / "fresh.txt"
        elsewhere.write_text("x")
        assert find_reported_outputs([str(elsewhere)], root) == []

    def test_a_missing_file_is_not_reported_even_when_fresh(self, tmp_path):
        root = self._tree(tmp_path)
        assert find_reported_outputs([str(tmp_path / "ghost.txt")], root, since=0) == []

    def test_a_directory_is_not_reported_even_when_fresh(self, tmp_path):
        root = self._tree(tmp_path)
        d = tmp_path / "Downloads"
        d.mkdir()
        assert find_reported_outputs([str(d)], root, since=0) == []
