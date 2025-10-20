# pyheic-struct

Utilities for inspecting, modifying, and rebuilding HEIC/HEIF files with a focus on
cross-vendor quirks between Samsung and Apple motion photos.

## Features

- Lightweight parser that exposes core ISOBMFF boxes (`ftyp`, `meta`, `iloc`, `iinf`, etc.)
- Helpers for reconstructing Samsung grid images into flat HEIC pictures
- Rebuilder that writes updated metadata and payload offsets safely
- High-level `convert_samsung_motion_photo` function to create Apple-compatible
  HEIC/MOV pairs (with optional MOV ContentIdentifier injection via `exiftool`)
- CLI tool: `pyheic-struct samsung.heic`

## Installation

```bash
pip install .
```

## Usage

```python
from pyheic_struct import convert_samsung_motion_photo

convert_samsung_motion_photo("samsung.heic")
```

Command line:

```bash
pyheic-struct samsung.heic --output-heic samsung_fixed.HEIC
```

## Development

The package targets Python 3.10+. Run the CLI in editable mode:

```bash
python -m pyheic_struct path/to/samsung.heic
```
