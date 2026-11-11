# Changelog

## Unreleased

- Add `--checksum` (`standard`, `none`, `skip-space`) to control the Code 39 check character, so numbers whose check character would be a space can be avoided.

## 0.1.0 (October 17, 2026)

First release on PyPI.

- Stamp each page of a PDF with a Code 39 barcode and write one copy per serial number (`--start`, `--number`).
- Choose the barcode edge with `--position` (`inside`, `outside`, `left`, `right`, `top`, `bottom`).
- Adjust the barcode with `--barwidth` and `--offset`.
- Write the copies to another directory with `--output-dir`.
- Show the installed version with `--version`.
