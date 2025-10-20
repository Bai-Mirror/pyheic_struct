"""Command line entry points for the pyheic_struct toolkit."""

from __future__ import annotations

import argparse
from pathlib import Path

from .converter import convert_samsung_motion_photo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Samsung HEIC motion photos into Apple-compatible HEIC+MOV pairs.",
    )
    parser.add_argument("source", type=Path, help="Path to the Samsung HEIC file.")
    parser.add_argument(
        "--output-heic",
        type=Path,
        default=None,
        help="Optional path for the converted HEIC file.",
    )
    parser.add_argument(
        "--output-mov",
        type=Path,
        default=None,
        help="Optional path for the extracted MOV file.",
    )
    parser.add_argument(
        "--skip-mov-tag",
        action="store_true",
        help="Skip injecting the ContentIdentifier into the MOV file (no exiftool call).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    convert_samsung_motion_photo(
        args.source,
        output_still=args.output_heic,
        output_video=args.output_mov,
        inject_content_id_into_mov=not args.skip_mov_tag,
    )
