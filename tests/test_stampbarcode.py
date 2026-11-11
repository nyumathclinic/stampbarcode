from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

import stampbarcode
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from typer.testing import CliRunner


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def plain(output: str) -> str:
    """Strip ANSI color codes, which Rich adds when it detects CI (e.g. GITHUB_ACTIONS)."""
    return ANSI_ESCAPE.sub("", output)


class StampBarcodeTests(unittest.TestCase):
    runner = CliRunner()

    def create_pdf(self, path: Path, pages: int = 1) -> None:
        pdf = canvas.Canvas(str(path), pagesize=(500, 700))
        for page_number in range(1, pages + 1):
            pdf.drawString(72, 72, f"page {page_number}")
            if page_number < pages:
                pdf.showPage()
        pdf.save()

    def read_page_content(self, path: Path, page_number: int) -> str:
        page = PdfReader(str(path)).pages[page_number - 1]
        return page.get_contents().get_data().decode("latin1")

    def test_generate_codes_increments_from_start(self) -> None:
        self.assertEqual(list(stampbarcode.generate_codes(100, 5)), [100, 101, 102, 103, 104])

    def test_code39_check_char_values(self) -> None:
        self.assertEqual(stampbarcode.code39_check_char(29999), " ")
        self.assertEqual(stampbarcode.code39_check_char(123), "6")
        self.assertEqual(stampbarcode.code39_check_char(0), "0")

    def test_code39_check_char_matches_reportlab(self) -> None:
        from reportlab.graphics.barcode import code39

        for code in (0, 7, 123, 1001, 29999, 99999, 48999, 123456789):
            with self.subTest(code=code):
                barcode = code39.Standard39(str(code), stop=1)
                barcode.validate()
                barcode.encode()
                self.assertEqual(barcode.encoded[-2], stampbarcode.code39_check_char(code))

    def test_generate_codes_skip_space_skips_space_check_chars(self) -> None:
        self.assertEqual(
            stampbarcode.generate_codes(29998, 3, stampbarcode.ChecksumMode.SKIP_SPACE),
            [29998, 30000, 30001],
        )
        self.assertEqual(
            stampbarcode.generate_codes(29998, 3, "none"), [29998, 29999, 30000]
        )

    def test_stamp_pdf_without_checksum_differs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            self.create_pdf(source)
            with_ck = Path(temp_dir) / "with.pdf"
            without_ck = Path(temp_dir) / "without.pdf"
            stampbarcode.stamp_pdf(source, with_ck, 123)
            stampbarcode.stamp_pdf(source, without_ck, 123, checksum=False)
            self.assertIn("1236", self.read_page_text(with_ck))
            self.assertNotIn("1236", self.read_page_text(without_ck))
            self.assertIn("123", self.read_page_text(without_ck))

    def read_page_text(self, path: Path) -> str:
        return PdfReader(str(path)).pages[0].extract_text()

    def test_cli_accepts_checksum_option(self) -> None:
        for mode in ("standard", "none", "skip-space", "NONE"):
            with self.subTest(mode=mode):
                result = self.invoke_with_source("--checksum", mode)
                self.assertEqual(result.exit_code, 0, result.output)

    def test_cli_rejects_invalid_checksum(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--checksum", "bogus", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for '--checksum'", plain(result.output))

    def test_run_skip_space_writes_non_contiguous_codes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            output_dir = Path(temp_dir) / "outputs"
            self.create_pdf(source)

            stampbarcode.run(
                source, 29998, 2, output_dir=output_dir,
                checksum_mode=stampbarcode.ChecksumMode.SKIP_SPACE,
            )

            self.assertEqual(
                sorted(p.name for p in output_dir.iterdir()),
                ["source-29998.pdf", "source-30000.pdf"],
            )

    def test_output_path_for_uses_stem_and_code(self) -> None:
        source = Path("/tmp/document.pdf")
        self.assertEqual(
            stampbarcode.output_path_for(source, 123),
            Path.cwd() / "document-123.pdf",
        )

    def test_output_path_for_respects_output_dir(self) -> None:
        source = Path("/tmp/document.pdf")
        self.assertEqual(
            stampbarcode.output_path_for(source, 123, Path("/tmp/out")),
            Path("/tmp/out/document-123.pdf"),
        )

    def test_barcode_x_position_inside_edge(self) -> None:
        page_width = 500
        barcode_width = 100
        margin = 20
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 1), 20)
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 2), 380)

    def test_barcode_x_position_respects_position_modes(self) -> None:
        page_width = 500
        barcode_width = 100
        margin = 20
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 1, "outside"), 380)
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 2, "outside"), 20)
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 3, "left"), 20)
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 4, "right"), 380)
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 1, "top"), 200)
        self.assertEqual(stampbarcode.barcode_x_position(page_width, barcode_width, margin, 1, "bottom"), 200)

    def test_barcode_y_position_respects_top_and_bottom_modes(self) -> None:
        page_height = 700
        barcode_height = 40
        margin = 20
        self.assertEqual(stampbarcode.barcode_y_position(page_height, barcode_height, margin, 1, "top"), 640)
        self.assertEqual(stampbarcode.barcode_y_position(page_height, barcode_height, margin, 1, "bottom"), 20)
        self.assertEqual(stampbarcode.barcode_y_position(page_height, barcode_height, margin, 1, "inside"), 330)

    def test_barcode_rotation_matches_position_modes(self) -> None:
        self.assertEqual(stampbarcode.barcode_rotation(1, "inside"), 90)
        self.assertEqual(stampbarcode.barcode_rotation(2, "inside"), -90)
        self.assertEqual(stampbarcode.barcode_rotation(1, "outside"), -90)
        self.assertEqual(stampbarcode.barcode_rotation(2, "outside"), 90)
        self.assertEqual(stampbarcode.barcode_rotation(1, "top"), 0)
        self.assertEqual(stampbarcode.barcode_rotation(1, "bottom"), 0)

    def invoke_with_source(self, *options: str):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            self.create_pdf(source)
            return self.runner.invoke(
                stampbarcode.app,
                [*options, "--output-dir", str(Path(temp_dir) / "out"), str(source)],
            )

    def test_cli_accepts_position_option(self) -> None:
        result = self.invoke_with_source("--position", "outside")
        self.assertEqual(result.exit_code, 0, result.output)

    def test_cli_accepts_barwidth_option(self) -> None:
        result = self.invoke_with_source("--barwidth", "1.2")
        self.assertEqual(result.exit_code, 0, result.output)

    def test_cli_accepts_offset_option(self) -> None:
        result = self.invoke_with_source("--offset", "-3.5+2.1")
        self.assertEqual(result.exit_code, 0, result.output)

    def test_cli_rejects_missing_input_as_usage_error(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["missing.pdf"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("Invalid value for", plain(result.output))

    def test_cli_rejects_invalid_offset_as_usage_error(self) -> None:
        result = self.invoke_with_source("--offset", "junk")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("Invalid value for '--offset'", plain(result.output))

    def test_cli_rejects_negative_start(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--start", "-1", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for '--start'", plain(result.output))

    def test_cli_version_option(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("stampbarcode", plain(result.output))

    def test_parse_offset_defaults_to_zero(self) -> None:
        self.assertEqual(stampbarcode.parse_offset(None), (0.0, 0.0))
        self.assertEqual(stampbarcode.parse_offset(""), (0.0, 0.0))

    def test_parse_offset_reads_lateral_then_normal(self) -> None:
        self.assertEqual(stampbarcode.parse_offset("+10-5"), (10.0, -5.0))
        self.assertEqual(stampbarcode.parse_offset("-3.5+2.1"), (-3.5, 2.1))
        self.assertEqual(stampbarcode.parse_offset("10+0"), (10.0, 0.0))

    def test_parse_offset_rejects_malformed_values(self) -> None:
        for value in ("junk", "10", "+10", "+10-5abc", "+10-5+2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    stampbarcode.parse_offset(value)

    def test_stamp_pdf_applies_offset_on_each_edge(self) -> None:
        expected = {
            stampbarcode.BarcodePosition.LEFT: "0 1 -1 0 41 317.82 cm",
            stampbarcode.BarcodePosition.RIGHT: "0 -1 1 0 459 382.18 cm",
            stampbarcode.BarcodePosition.TOP: "1 0 0 1 217.82 659 cm",
            stampbarcode.BarcodePosition.BOTTOM: "1 0 0 1 217.82 13 cm",
        }
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            self.create_pdf(source)
            for position, transform in expected.items():
                with self.subTest(position=position.value):
                    output = Path(temp_dir) / f"{position.value}.pdf"
                    stampbarcode.stamp_pdf(
                        source, output, 123, position, lateral_offset=10, normal_offset=-5
                    )
                    self.assertIn(transform, self.read_page_content(output, 1))

    def test_cli_rejects_non_positive_num(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--number", "0", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for", plain(result.output))

    def test_cli_rejects_too_small_barwidth(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--barwidth", "0", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for '--barwidth'", plain(result.output))

    def test_cli_rejects_invalid_position(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--position", "middle", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for '--position'", plain(result.output))

    def test_stamp_pdf_places_inside_barcodes_on_inner_edges(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            output = Path(temp_dir) / "inside.pdf"
            self.create_pdf(source, pages=2)

            stampbarcode.stamp_pdf(source, output, 123, stampbarcode.BarcodePosition.INSIDE)

            recto_content = self.read_page_content(output, 1)
            verso_content = self.read_page_content(output, 2)

            self.assertIn("0 1 -1 0 36 307.82 cm", recto_content)
            self.assertIn("0 -1 1 0 464 392.18 cm", verso_content)

    def test_stamp_pdf_places_top_barcodes_without_rotation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            output = Path(temp_dir) / "top.pdf"
            self.create_pdf(source)

            stampbarcode.stamp_pdf(source, output, 123, stampbarcode.BarcodePosition.TOP)

            content = self.read_page_content(output, 1)

            self.assertIn("1 0 0 1 207.82 664 cm", content)
            self.assertNotIn("0 1 -1 0", content)
            self.assertNotIn("0 -1 1 0", content)

    def test_stamp_pdf_custom_barwidth_changes_overlay_position(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            output = Path(temp_dir) / "top-custom-width.pdf"
            self.create_pdf(source)

            stampbarcode.stamp_pdf(source, output, 123, stampbarcode.BarcodePosition.TOP, bar_width=1.2)

            content = self.read_page_content(output, 1)

            self.assertNotIn("1 0 0 1 207.82 664 cm", content)

    def test_run_raises_when_input_missing(self) -> None:
        with self.assertRaises(FileNotFoundError):
            stampbarcode.run(Path("does-not-exist.pdf"), 0, 1)

    def test_run_writes_to_output_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            output_dir = Path(temp_dir) / "outputs"
            self.create_pdf(source)

            stampbarcode.run(source, 10, 2, output_dir=output_dir)

            self.assertTrue((output_dir / "source-10.pdf").exists())
            self.assertTrue((output_dir / "source-11.pdf").exists())


if __name__ == "__main__":
    unittest.main()
