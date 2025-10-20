#!/usr/bin/env python3
"""
Convert an Apple Live Photo pair (HEIC + MOV) into a single Samsung-style
Motion Photo HEIC by embedding the video track inside an `mpvd` box.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pillow_heif

from pyheic_struct import HEICBuilder, HEICFile


SAMSUNG_FTYP_PAYLOAD = b"heic\x00\x00\x00\x00mif1heic"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge an Apple Live Photo (HEIC + MOV) into a Samsung-compatible "
            "Motion Photo HEIC (with embedded mpvd video box)."
        )
    )
    parser.add_argument(
        "still",
        type=Path,
        help="Path to the Apple HEIC still image.",
    )
    parser.add_argument(
        "video",
        type=Path,
        help="Path to the corresponding MOV video.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output HEIC file. Defaults to <still>_samsung_compatible.heic",
    )
    return parser


def _validate_file(path: Path, description: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{description} not found: {resolved}")
    return resolved


def _build_mpvd_box(video_bytes: bytes) -> bytes:
    size = len(video_bytes) + 8
    return size.to_bytes(4, "big") + b"mpvd" + video_bytes


def _prepare_base_heic(still_path: Path) -> tuple[HEICFile, Path]:
    original = HEICFile(str(still_path))
    pil_image = original.reconstruct_primary_image()
    if pil_image is None:
        raise RuntimeError("Failed to reconstruct primary image from input HEIC.")

    pillow_heif.register_heif_opener()
    temp_flat_path = still_path.with_name(f"{still_path.stem}_temp_flat.heic")
    if temp_flat_path.exists():
        temp_flat_path.unlink()

    pil_image.save(
        temp_flat_path,
        format="HEIF",
        quality=95,
        save_as_brand="mif1",
    )

    heic = HEICFile(str(temp_flat_path))

    if heic._ftyp_box is None:
        raise RuntimeError("Input HEIC file does not contain an ftyp box.")

    # Samsung Motion Photos use a minimal brand list (heic/mif1).
    heic._ftyp_box.raw_data = SAMSUNG_FTYP_PAYLOAD
    heic._ftyp_box.size = len(SAMSUNG_FTYP_PAYLOAD) + 8

    return heic, temp_flat_path


def convert_live_photo(still_path: Path, video_path: Path, output_path: Path) -> Path:
    heic, temp_flat_path = _prepare_base_heic(still_path)

    try:
        builder = HEICBuilder(heic)
        builder.write(str(output_path))
    finally:
        if temp_flat_path.exists():
            temp_flat_path.unlink()

    video_bytes = video_path.read_bytes()
    if video_bytes[4:8] not in {b"ftyp", b"moov"}:
        print(
            "Warning: Video file does not look like a QuickTime/MP4 container. "
            "Samsung devices may not recognize the embedded clip.",
            file=sys.stderr,
        )

    mpvd_box = _build_mpvd_box(video_bytes)
    with output_path.open("ab") as f:
        f.write(mpvd_box)

    return output_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        still_path = _validate_file(args.still, "HEIC still")
        video_path = _validate_file(args.video, "MOV video")
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else still_path.with_name(f"{still_path.stem}_samsung_compatible.heic")
    )

    try:
        convert_live_photo(still_path, video_path, output_path)
    except Exception as exc:  # pragma: no cover - CLI diagnostic path
        print(f"Error: Conversion failed: {exc}", file=sys.stderr)
        return 1

    print("Conversion finished successfully.")
    print(f"Samsung-style Motion Photo saved to: {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
