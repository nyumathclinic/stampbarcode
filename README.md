# stampbarcode
Duplicate a PDF with serial barcode stamps

## Installation

Requires Python 3.10 or later.

```bash
pipx install stampbarcode
```

or

```bash
uv tool install stampbarcode
```

## Usage

```bash
stampbarcode [--start N] [--number N] [--barwidth FLOAT] [--position inside|outside|left|right|top|bottom] [--offset OFFSET] [--output-dir DIR] file.pdf
```

For example, to make three numbered copies of an exam:

```bash
stampbarcode --start 1001 --number 3 --output-dir stamped exam.pdf
```

This writes `stamped/exam-1001.pdf`, `stamped/exam-1002.pdf`, and `stamped/exam-1003.pdf`.

By default, this produces files named `<stem>-<code>.pdf` in the current working directory.
Use `--output-dir DIR` to write generated files to a specific directory.
Existing files with the same names are overwritten without warning.

Each output file is a stamped copy using a Code39 barcode (with the number shown
as human-readable text), and `--position` controls where the barcode is placed.
The default is `inside`: left on recto pages and right on verso pages.

`--barwidth` controls the width of each barcode bar (default: `0.6`).
Bar widths and offsets are measured in PDF points (1/72 inch).

Other position modes are `outside`, `left`, `right`, `top`, and `bottom`.

The first generated barcode is exactly `--start`, and `--number` controls how many
consecutive codes are produced.

### Barcode Position Offsets

The `--offset` option allows fine-tuning the barcode position with format `[+-]lateral[+-]normal`:

- **Lateral offset**: Moves the barcode perpendicular to its primary axis
  - Positive values move right (in barcode coordinates)
  - Negative values move left (in barcode coordinates)
  
- **Normal offset**: Moves the barcode along its primary axis
  - Positive values move up (in barcode coordinates)
  - Negative values move down (in barcode coordinates)

**Examples:** `--offset +10-5`, `--offset -3.5+2.1`, `--offset +0-15`

#### Offset Behavior by Position

All offsets are **relative to the barcode's orientation**, not the physical page:

| Position | Edge | Lateral Effect | Normal Effect |
|----------|------|----------------|---------------|
| `top` | top | moves horizontally right/left | moves vertically up/down |
| `bottom` | bottom | moves horizontally right/left | moves vertically up/down |
| `left` / recto inside | left | moves vertically down/up | moves horizontally right/left |
| `right` / verso inside | right | moves vertically up/down | moves horizontally left/right |
| `outside` recto | right | moves vertically up/down | moves horizontally left/right |
| `outside` verso | left | moves vertically down/up | moves horizontally right/left |

**Intuition:** Think of the barcode as having its own local coordinate system (lateral and normal axes). The offset moves the barcode within that system, and the effect on the page depends on the barcode's rotation.

## Limitations

- The barcode is placed using each page's media box, assuming its origin is at the lower-left corner. Pages with a `/Rotate` entry (common in scans), a shifted media box, or a smaller crop box may get a misplaced barcode.
- Only Code 39 barcodes are supported, and the bar height and margin are fixed.

## Development

Use the repo-local virtual environment for tests and editable installs:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

## License

MIT. See [LICENSE](https://github.com/nyumathclinic/stampbarcode/blob/main/LICENSE).
