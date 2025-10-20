#!/usr/bin/env python3
"""
Utility script for converting Samsung HEIC motion photos into
Apple-compatible Live Photo pairs (HEIC + MOV) with matching ContentIdentifier.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from pyheic_struct import AppleTargetAdapter, convert_motion_photo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Samsung HEIC motion photo into an Apple-compatible Live Photo "
            "(HEIC + MOV) while keeping ContentIdentifier aligned."
        ),
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Path to the Samsung HEIC motion photo.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for the generated files. Defaults to the source directory.",
    )
    parser.add_argument(
        "--heic-name",
        type=str,
        default=None,
        help="Optional filename (without directory) for the converted HEIC.",
    )
    parser.add_argument(
        "--mov-name",
        type=str,
        default=None,
        help="Optional filename (without directory) for the converted MOV.",
    )
    parser.add_argument(
        "--skip-mov-tag",
        action="store_true",
        help="Skip writing ContentIdentifier into the MOV (no exiftool usage).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source_path = args.source.expanduser().resolve()
    if not source_path.is_file():
        print(f"Error: HEIC source file not found: {source_path}", file=sys.stderr)
        return 1

    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else source_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_mov_tag and shutil.which("exiftool") is None:
        print(
            "Error: exiftool is required to inject ContentIdentifier into the MOV. "
            "Install exiftool or use --skip-mov-tag.",
            file=sys.stderr,
        )
        return 1

    heic_filename = args.heic_name or f"{source_path.stem}_apple_compatible.HEIC"
    mov_filename = args.mov_name or f"{source_path.stem}_apple_compatible.MOV"

    heic_output = output_dir / heic_filename
    mov_output = output_dir / mov_filename

    print(f"Source HEIC: {source_path}")
    print(f"Output HEIC: {heic_output}")
    print(f"Output MOV:  {mov_output}")

    heic_path, mov_path = convert_motion_photo(
        source_path,
        vendor_hint="samsung",
        target_adapter=AppleTargetAdapter(),
        output_still=heic_output,
        output_video=mov_output,
        inject_content_id_into_mov=not args.skip_mov_tag,
    )

    print("Conversion finished successfully.")
    print(f"HEIC saved to: {heic_path}")
    if mov_path:
        print(f"MOV  saved to: {mov_path}")
    else:
        print("No MOV file generated (no embedded motion photo data found).")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
