"""Tests for scripts.formats.convert_docs."""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.formats.convert_docs import (
    PandocMissingError,
    _dispatcher,
    convert,
)


def _make(tmp_path: Path, name: str, content: str = "hello") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestDispatcher:
    def test_txt_to_md_is_copy(self):
        assert _dispatcher(".txt", ".md").__name__ == "_copy"

    def test_md_to_txt_is_copy(self):
        assert _dispatcher(".md", ".txt").__name__ == "_copy"

    def test_pdf_to_txt_uses_pypdf(self):
        assert _dispatcher(".pdf", ".txt").__name__ == "_extract_pdf_text"

    def test_docx_to_pdf_uses_pandoc(self):
        assert _dispatcher(".docx", ".pdf").__name__ == "_pandoc_convert"

    def test_rtf_to_docx_uses_pandoc(self):
        assert _dispatcher(".rtf", ".docx").__name__ == "_pandoc_convert"

    def test_binary_doc_input_rejected(self):
        with pytest.raises(ValueError, match="binary .doc files"):
            _dispatcher(".doc", ".pdf")


class TestConvertTxtMd:
    def test_txt_to_md_copies_content(self, tmp_path: Path):
        src = _make(tmp_path, "notes.txt", "hello\nworld")
        out_dir = tmp_path / "out"

        outputs = convert(src, "md", out_dir)

        assert len(outputs) == 1
        assert outputs[0].name == "notes.md"
        assert outputs[0].read_text(encoding="utf-8") == "hello\nworld"

    def test_md_to_txt_copies_content(self, tmp_path: Path):
        src = _make(tmp_path, "doc.md", "# title\n\nbody")
        out_dir = tmp_path / "out"

        outputs = convert(src, "txt", out_dir)

        assert outputs[0].name == "doc.txt"
        assert outputs[0].read_text(encoding="utf-8") == "# title\n\nbody"


class TestConvertPandoc:
    def test_docx_to_pdf_invokes_pandoc(self, tmp_path: Path):
        src = _make(tmp_path, "report.docx")
        out_dir = tmp_path / "out"

        with (
            patch("scripts.formats.convert_docs._has_pandoc", return_value=True),
            patch("scripts.formats.convert_docs._has_weasyprint", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            outputs = convert(src, "pdf", out_dir)

        assert outputs[0].name == "report.pdf"
        args = mock_run.call_args.args[0]
        assert args[0] == "pandoc"
        assert "--standalone" in args
        assert "--pdf-engine=weasyprint" not in args

    def test_pdf_output_with_weasyprint_uses_pdf_engine(self, tmp_path: Path):
        src = _make(tmp_path, "notes.md", "# hi")
        out_dir = tmp_path / "out"

        with (
            patch("scripts.formats.convert_docs._has_pandoc", return_value=True),
            patch("scripts.formats.convert_docs._has_weasyprint", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            convert(src, "pdf", out_dir)

        args = mock_run.call_args.args[0]
        assert "--pdf-engine=weasyprint" in args

    def test_raises_when_pandoc_missing(self, tmp_path: Path):
        src = _make(tmp_path, "report.docx")

        with (
            patch("scripts.formats.convert_docs._has_pandoc", return_value=False),
            pytest.raises(PandocMissingError, match="pandoc is required"),
        ):
            convert(src, "pdf", tmp_path / "out")


class TestConvertPdfText:
    def test_pdf_to_txt_extracts_text(self, tmp_path: Path):
        src = _make(tmp_path, "paper.pdf")
        out_dir = tmp_path / "out"

        page1 = MagicMock()
        page1.extract_text.return_value = "first page"
        page2 = MagicMock()
        page2.extract_text.return_value = "second page"
        reader = MagicMock()
        reader.pages = [page1, page2]

        with patch("pypdf.PdfReader", return_value=reader):
            outputs = convert(src, "txt", out_dir)

        text = outputs[0].read_text(encoding="utf-8")
        assert "first page" in text
        assert "second page" in text


class TestBatchMode:
    def test_converts_every_file_in_directory(self, tmp_path: Path):
        inp = tmp_path / "in"
        inp.mkdir()
        _make(inp, "a.txt", "alpha")
        _make(inp, "b.md", "beta")
        out_dir = tmp_path / "out"

        outputs = convert(inp, "md", out_dir)

        names = sorted(p.name for p in outputs)
        assert names == ["a.md", "b.md"]


class TestErrors:
    def test_unsupported_target_format_rejected(self, tmp_path: Path):
        src = _make(tmp_path, "notes.md")
        with pytest.raises(ValueError, match="unsupported target format"):
            convert(src, "epub", tmp_path / "out")

    def test_pandoc_failure_propagates_in_single_file_mode(self, tmp_path: Path):
        src = _make(tmp_path, "report.docx")
        err = subprocess.CalledProcessError(returncode=1, cmd=["pandoc"], stderr="boom")

        with (
            patch("scripts.formats.convert_docs._has_pandoc", return_value=True),
            patch("subprocess.run", side_effect=err),
            pytest.raises(subprocess.CalledProcessError),
        ):
            convert(src, "pdf", tmp_path / "out")
