from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import stampbarcode
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from typer.testing import CliRunner


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

    def test_output_path_for_uses_stem_and_code(self) -> None:
        source = Path("/tmp/document.pdf")
        with TemporaryDirectory() as temp_dir:
            with self.runner.isolated_filesystem(temp_dir=temp_dir):
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

    def test_cli_accepts_position_option(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--position", "outside", "missing.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Input file does not exist", str(result.exception))

    def test_cli_accepts_barwidth_option(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--barwidth", "1.2", "missing.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Input file does not exist", str(result.exception))

    def test_cli_rejects_non_positive_num(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--number", "0", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for", result.output)

    def test_cli_rejects_too_small_barwidth(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--barwidth", "0", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for '--barwidth'", result.output)

    def test_cli_rejects_invalid_position(self) -> None:
        result = self.runner.invoke(stampbarcode.app, ["--position", "middle", "input.pdf"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value for '--position'", result.output)

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
