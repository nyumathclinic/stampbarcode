#!/usr/bin/env python3

from __future__ import annotations

import io
import re
from enum import Enum
from pathlib import Path

import typer

BARCODE_BAR_WIDTH = 0.6
BARCODE_BAR_HEIGHT = 18
BARCODE_MARGIN = 18

app = typer.Typer(add_completion=False)


class BarcodePosition(str, Enum):
    INSIDE = "inside"
    OUTSIDE = "outside"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


def parse_offset(offset_str: str | None) -> tuple[float, float]:
    """Parse offset string in format [+-][number][+-][number].
    
    Returns (lateral_offset, normal_offset).
    
    Offsets are relative to barcode orientation:
    - lateral: positive = right (in barcode coords), negative = left
    - normal: positive = up (in barcode coords), negative = down
    
    For top/bottom positions (unrotated), barcode and page axes align:
      - lateral offset → horizontal page displacement
      - normal offset → vertical page displacement
    
    For left/right positions (90° rotated):
      - Rotation +90° (left edge): lateral → vertical page displacement,
        normal → horizontal page displacement (with sign reversal)
      - Rotation -90° (right edge): lateral → vertical page displacement
        (reversed), normal → horizontal page displacement
    """
    if not offset_str:
        return (0.0, 0.0)
    
    # Parse format: [+-][number][+-][number]
    # Find the second sign to split lateral and normal offsets
    match = re.match(r'([+-]?\d+(?:\.\d+)?)\s*([+-]\d+(?:\.\d+)?)', offset_str.strip())
    if not match:
        raise ValueError(
            f"Invalid offset format: '{offset_str}'. Expected format: [+-]number[+-]number "
            "(e.g., '+10-5' or '-3.5+2.1')"
        )
    
    lateral = float(match.group(1))
    normal = float(match.group(2))
    return (lateral, normal)


def generate_codes(start: int, num: int) -> range:
    return range(start, start + num)


def output_path_for(input_path: Path, code: int, output_dir: Path | None = None) -> Path:
    target_dir = output_dir if output_dir is not None else Path.cwd()
    return target_dir / f"{input_path.stem}-{code}.pdf"


def barcode_edge_for_page(position: BarcodePosition | str, page_number: int) -> str:
    position = BarcodePosition(position)
    is_recto = page_number % 2 == 1
    if position == BarcodePosition.INSIDE:
        return "left" if is_recto else "right"
    if position == BarcodePosition.OUTSIDE:
        return "right" if is_recto else "left"
    if position == BarcodePosition.LEFT:
        return "left"
    if position == BarcodePosition.RIGHT:
        return "right"
    return position.value


def barcode_x_position(
    page_width: float,
    barcode_width: float,
    margin: float,
    page_number: int,
    position: BarcodePosition | str = BarcodePosition.INSIDE,
) -> float:
    edge = barcode_edge_for_page(position, page_number)
    if edge == "left":
        return margin
    if edge == "right":
        return page_width - margin - barcode_width
    return (page_width - barcode_width) / 2


def barcode_y_position(
    page_height: float,
    barcode_height: float,
    margin: float,
    page_number: int,
    position: BarcodePosition | str = BarcodePosition.INSIDE,
) -> float:
    edge = barcode_edge_for_page(position, page_number)
    if edge == "top":
        return page_height - margin - barcode_height
    if edge == "bottom":
        return margin
    return (page_height - barcode_height) / 2


def barcode_rotation(page_number: int, position: BarcodePosition | str = BarcodePosition.INSIDE) -> int:
    edge = barcode_edge_for_page(position, page_number)
    if edge == "left":
        return 90
    if edge == "right":
        return -90
    return 0


def create_overlay(
    page_width: float,
    page_height: float,
    code: int,
    page_number: int,
    position: BarcodePosition = BarcodePosition.INSIDE,
    bar_width: float = BARCODE_BAR_WIDTH,
    lateral_offset: float = 0.0,
    normal_offset: float = 0.0,
) -> io.BytesIO:
    """Create PDF overlay with barcode.
    
    Args:
        lateral_offset: Offset perpendicular to barcode's primary axis.
                       Positive = right in barcode coords.
        normal_offset: Offset along barcode's primary axis.
                      Positive = up in barcode coords.
    """
    from reportlab.graphics.barcode import code39
    from reportlab.pdfgen import canvas

    packet = io.BytesIO()
    pdf_canvas = canvas.Canvas(packet, pagesize=(page_width, page_height))
    barcode = code39.Standard39(
        str(code),
        barWidth=bar_width,
        barHeight=BARCODE_BAR_HEIGHT,
        stop=1,
        humanReadable=True,
    )

    edge = barcode_edge_for_page(position, page_number)
    pdf_canvas.saveState()
    if edge == "left":
        # Counterclockwise (+90°): barcode runs vertically on the left (recto) edge.
        # After translate(tx,ty) + rotate(90), local (x,y) maps to page (tx-y, ty+x).
        # Barcode occupies page_x in [tx-H, tx], page_y in [ty, ty+W].
        # Offsets in barcode coords: lateral offset → dy, normal offset → -dx
        tx = BARCODE_MARGIN + barcode.height - normal_offset
        ty = (page_height - barcode.width) / 2 + lateral_offset
        pdf_canvas.translate(tx, ty)
        pdf_canvas.rotate(90)
    elif edge == "right":
        # Clockwise (-90°): barcode runs vertically on the right (verso) edge.
        # After translate(tx,ty) + rotate(-90), local (x,y) maps to page (tx+y, ty-x).
        # Barcode occupies page_x in [tx, tx+H], page_y in [ty-W, ty].
        # Offsets in barcode coords: lateral offset → -dy, normal offset → dx
        tx = page_width - BARCODE_MARGIN - barcode.height + normal_offset
        ty = (page_height + barcode.width) / 2 - lateral_offset
        pdf_canvas.translate(tx, ty)
        pdf_canvas.rotate(-90)
    elif edge == "top":
        # No rotation: barcode horizontal at top
        # Offsets in barcode coords: lateral offset → dx, normal offset → dy
        tx = (page_width - barcode.width) / 2 + lateral_offset
        ty = page_height - BARCODE_MARGIN - barcode.height + normal_offset
        pdf_canvas.translate(tx, ty)
    else:
        # Bottom: no rotation
        # Offsets in barcode coords: lateral offset → dx, normal offset → dy
        tx = (page_width - barcode.width) / 2 + lateral_offset
        ty = BARCODE_MARGIN + normal_offset
        pdf_canvas.translate(tx, ty)
    barcode.drawOn(pdf_canvas, 0, 0)
    pdf_canvas.restoreState()

    pdf_canvas.save()
    packet.seek(0)
    return packet


def stamp_pdf(
    input_pdf: Path,
    output_pdf: Path,
    code: int,
    position: BarcodePosition = BarcodePosition.INSIDE,
    bar_width: float = BARCODE_BAR_WIDTH,
    lateral_offset: float = 0.0,
    normal_offset: float = 0.0,
) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()

    for page_number, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_stream = create_overlay(
            width, height, code, page_number, position, bar_width,
            lateral_offset, normal_offset
        )
        overlay_page = PdfReader(overlay_stream).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    with output_pdf.open("wb") as output_stream:
        writer.write(output_stream)


def run(
    pdf_file: Path,
    start: int,
    num: int,
    position: BarcodePosition = BarcodePosition.INSIDE,
    bar_width: float = BARCODE_BAR_WIDTH,
    lateral_offset: float = 0.0,
    normal_offset: float = 0.0,
    output_dir: Path | None = None,
) -> None:
    if not pdf_file.exists():
        raise FileNotFoundError(f"Input file does not exist: {pdf_file}")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    for code in generate_codes(start, num):
        output_pdf = output_path_for(pdf_file, code, output_dir)
        stamp_pdf(pdf_file, output_pdf, code, position, bar_width,
                  lateral_offset, normal_offset)


@app.command()
def main(
    pdf_file: Path = typer.Argument(..., help="Source PDF file"),
    start: int = typer.Option(0, "--start", help="Starting barcode number"),
    num: int = typer.Option(1, "-n", "--number", min=1, help="How many stamped files to produce"),
    barwidth: float = typer.Option(
        BARCODE_BAR_WIDTH,
        "--barwidth",
        min=0.01,
        help="Barcode bar width",
    ),
    position: BarcodePosition = typer.Option(
        BarcodePosition.INSIDE,
        "--position",
        case_sensitive=False,
        help="Barcode placement: inside, outside, left, right, top, or bottom",
    ),
    offset: str = typer.Option(
        None,
        "--offset",
        help="Barcode offset as [+-]lateral[+-]normal (e.g., '+10-5' or '-3.5+2.1'). "
             "Lateral moves perpendicular to barcode axis (positive=right). "
             "Normal moves along barcode axis (positive=up). "
             "Offsets are relative to barcode orientation.",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
        help="Directory for generated PDFs. Defaults to the current working directory.",
    ),
) -> None:
    lateral_offset, normal_offset = parse_offset(offset)
    run(pdf_file, start, num, position, barwidth, lateral_offset, normal_offset, output_dir)


if __name__ == "__main__":
    app()
