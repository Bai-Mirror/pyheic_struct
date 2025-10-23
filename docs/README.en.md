# pyheic-struct (English Overview)

`pyheic-struct` exists because I needed a reliable way to convert Samsung Motion Photos into Apple-compatible Live Photos.  
It automatically produces a paired HEIC + MOV set, synchronises their `ContentIdentifier` / `PhotoIdentifier`, injects the required MakerNote fields, and makes macOS Photos or iOS treat them as a single Live Photo instead of two independent files.

The conversion pipeline is powered by a set of reusable tools for inspecting, editing, and rebuilding HEIF/HEIC containers. Even if you only need low-level diagnostics, you can reuse the parsing classes, the safety-first `HEICBuilder`, or the vendor/target adapter hooks.

---

## Highlights

- **Samsung Motion Photo → Live Photo**: export aligned HEIC and MOV files with matching identifiers.
- **Metadata completion**: write Apple-specific MakerNote fields (`ContentIdentifier`, `PhotoIdentifier`, etc.).
- **Deep HEIC inspection**: `HEICFile` exposes `ftyp`, `meta`, `iloc`, `iinf`, `iprp`, and references for debugging.
- **Safe rebuild pipeline**: `HEICBuilder` recalculates offsets and references to avoid corrupted files.
- **CLI + Python API**: run a one-shot conversion script or integrate with your own workflow.
- **Sample assets included**: compare the supplied Samsung source, converted outputs, and Apple originals.

---

## Installation

Requirements:

- Python 3.10+
- Dependencies: `Pillow>=10.0.0`, `pillow-heif>=0.15.0`, `piexif>=1.1.3`
- Optional: `exiftool-wrapper>=0.5.0`
- Recommended: system-level [ExifTool](https://exiftool.org/) (needed for MOV tagging)

Install from source:

```bash
pip install .
# or, with extras for development + exiftool-wrapper
pip install -e .[full]
```

---

### Windows & macOS standalone binaries

Need an executable without Python? Trigger the **Build Samsung Live Photo binaries** workflow in GitHub Actions (or wait for an automatic run) and download the `SamsungToLivePhoto-windows` / `SamsungToLivePhoto-macos` artifacts. Each archive ships with a short README that mirrors `packaging/README_windows.txt` and `packaging/README_macos.txt`.

To build locally on the target OS:

```bash
# Windows (PowerShell)
python -m pip install ".[full]" pyinstaller
pyinstaller --noconfirm --onefile --name SamsungToLivePhoto `
  --collect-all pillow_heif --collect-all pyheic_struct `
  scripts/samsung_to_live_photo.py

# macOS (bash/zsh)
python3 -m pip install ".[full]" pyinstaller
pyinstaller --noconfirm --onefile --name SamsungToLivePhoto \
  --collect-all pillow_heif --collect-all pyheic_struct \
  scripts/samsung_to_live_photo.py
```

The resulting executables live under `dist/`: `SamsungToLivePhoto.exe` on Windows and `SamsungToLivePhoto` on macOS.

---

## Quick Start

### CLI conversion

```bash
python3 scripts/samsung_to_live_photo.py examples/samsung.heic --output-dir output/live
```

The command writes `samsung_apple_compatible.heic` and `samsung_apple_compatible.mov` with the same UUIDs.

Key options:

| Option | Description |
| ------ | ----------- |
| `--output-dir` | Target directory (defaults to the source directory) |
| `--heic-name` / `--mov-name` | Custom output filenames |
| `--skip-mov-tag` | Skip MOV `ContentIdentifier` injection when exiftool is unavailable |

### Python API

```python
from pathlib import Path
from pyheic_struct import convert_samsung_motion_photo, HEICFile, HEICBuilder

heic_path, mov_path = convert_samsung_motion_photo(
    "examples/samsung.heic",
    output_still=Path("converted/apple_ready.HEIC"),
    output_video=Path("converted/apple_ready.MOV"),
)

rebuilt = HEICFile(str(heic_path))
rebuilt.set_content_identifier("MY-INTERNAL-ID")
HEICBuilder(rebuilt).write("converted/customized.HEIC")
```

---

## How the pipeline works

1. **Parse the original HEIC** and detect Samsung-specific structures (`mpvd`, shifted item IDs).
2. **Reconstruct the primary image** via `pillow-heif` and save a flat temporary HEIC.
3. **Extract the embedded video**, save it as MOV, and (optionally) add `ContentIdentifier` using exiftool.
4. **Fix shifted IDs and references** across `iinf`, `ipma`, and `iref`.
5. **Inject Apple metadata**: set the brand tuple, write MakerNote, `ContentIdentifier`, and `PhotoIdentifier`.
6. **Rebuild the file** with `HEICBuilder`, which recalculates offsets and cleans up temporary files.

---

## Key API reference

- `pyheic_struct.convert_motion_photo(...)`
- `pyheic_struct.convert_samsung_motion_photo(...)`
- `pyheic_struct.HEICFile`: parsing helpers, metadata mutators.
- `pyheic_struct.HEICBuilder`: safe writer after modifications.
- `pyheic_struct.handlers.VendorHandler`: extend for other Motion Photo vendors.
- `pyheic_struct.targets.AppleTargetAdapter`: writes Apple-specific metadata.

---

## Need more?

The Chinese README (default) contains additional background, step-by-step guides, and FAQ:  
[返回中文文档 / Back to Chinese](README.md)
