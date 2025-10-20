"""High-level conversion helpers for Samsung motion photos."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import pillow_heif

from .builder import HEICBuilder
from .handlers.base_handler import VendorHandler
from .handlers.samsung_handler import SamsungHandler
from .heic_file import HEICFile
from .heic_types import ItemInfoEntryBox


def convert_samsung_motion_photo(
    source: str | os.PathLike,
    *,
    output_still: Optional[str | os.PathLike] = None,
    output_video: Optional[str | os.PathLike] = None,
    inject_content_id_into_mov: bool = True,
) -> tuple[Path, Optional[Path]]:
    """
    Convert a Samsung motion photo into an Apple-compatible HEIC + MOV pair.

    Parameters
    ----------
    source:
        Path to the Samsung `.heic` file to convert.
    output_still:
        Optional output path for the converted HEIC. Defaults to
        ``<source>_apple_compatible.HEIC``.
    output_video:
        Optional output path for the extracted MOV. Defaults to
        ``<source>_apple_compatible.MOV``.
    inject_content_id_into_mov:
        When True (default), ``exiftool`` is invoked to set the
        ``QuickTime:ContentIdentifier`` of the generated MOV file. If
        ``exiftool`` is not available the MOV is still created without the tag.

    Returns
    -------
    (Path, Optional[Path])
        Tuple containing the path to the new HEIC file and the MOV path (if one
        was produced).
    """

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Samsung HEIC not found: {source_path}")

    base = source_path.with_suffix("")
    heic_path = Path(output_still) if output_still else Path(f"{base}_apple_compatible.HEIC")
    mov_path = Path(output_video) if output_video else Path(f"{base}_apple_compatible.MOV")
    temp_flat_path = Path(f"{base}_temp_flat.HEIC")

    print(f"--- Converting {source_path.name} to Apple format (V17 Fix) ---")

    original_heic_file = HEICFile(str(source_path))

    # Extract video data if present
    video_data = original_heic_file.get_motion_photo_data()
    if not video_data:
        if not original_heic_file.handler or isinstance(original_heic_file.handler, VendorHandler):
            print("Vendor not auto-detected. Manually checking for Samsung 'mpvd' box...")
            mpvd_box = original_heic_file.find_box('mpvd')
            if mpvd_box:
                original_heic_file.handler = SamsungHandler()
                video_data = original_heic_file.get_motion_photo_data()

    # Rebuild the primary image
    print("Reconstructing grid image from Samsung file...")
    pil_image = original_heic_file.reconstruct_primary_image()
    if not pil_image:
        raise RuntimeError("Failed to reconstruct primary image using pillow-heif.")

    new_content_id = str(uuid.uuid4()).upper()
    print(f"Generated ContentIdentifier: {new_content_id}")

    # Save MOV if video data exists
    if video_data:
        print(f"Saving extracted video data to {mov_path}...")
        mov_path.write_bytes(video_data)

        if inject_content_id_into_mov:
            try:
                print("Attempting to inject ContentIdentifier into .MOV file (requires exiftool)...")
                subprocess.run(
                    [
                        "exiftool",
                        f"-QuickTime:ContentIdentifier={new_content_id}",
                        "-overwrite_original",
                        str(mov_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print("Successfully injected ContentIdentifier into .MOV.")
            except Exception as exc:  # pragma: no cover - diagnostic path
                print("Warning: Could not inject ContentIdentifier into .MOV.")
                print("  (This is normal if 'exiftool' is not installed.)")
                print(f"  Error: {exc}")
    else:
        mov_path = None
        print("Info: No motion photo data found. Only a still HEIC will be created.")

    try:
        print(f"Saving temporary flat HEIC file to {temp_flat_path}...")
        pillow_heif.register_heif_opener()
        pil_image.save(
            temp_flat_path,
            format="HEIF",
            quality=95,
            save_as_brand="mif1",
        )
        print("Successfully created temporary flat HEIC.")
    except Exception as exc:
        if temp_flat_path.exists():
            temp_flat_path.unlink()
        raise RuntimeError(f"Failed to save temporary HEIC file: {exc}") from exc

    try:
        print("Loading temporary flat HEIC for metadata injection...")
        flat_heic_file = HEICFile(str(temp_flat_path))

        if flat_heic_file._ftyp_box:
            print("Modifying 'ftyp' box to be Apple compatible (heic, MiHB, MiHE...)...")
            apple_ftyp_raw_data = b"heic\x00\x00\x00\x00mif1MiHBMiHEMiPrmiafheictmap"
            flat_heic_file._ftyp_box.raw_data = apple_ftyp_raw_data
            flat_heic_file._ftyp_box.size = len(apple_ftyp_raw_data) + 8
        else:
            raise RuntimeError("Temporary HEIC file has no 'ftyp' box.")

        print("Checking for shifted IDs in temporary file (V17 Full Fix)...")
        if flat_heic_file._iinf_box and flat_heic_file._iloc_box and flat_heic_file._iprp_box:
            correct_ids = {loc.item_id for loc in flat_heic_file._iloc_box.locations}
            iinf_children_to_fix = [
                child
                for child in flat_heic_file._iinf_box.children
                if isinstance(child, ItemInfoEntryBox) and (child.item_id >> 16) in correct_ids
            ]

            shifted_id_map: dict[int, int] = {}

            if iinf_children_to_fix:
                print(f"  Found {len(iinf_children_to_fix)} shifted 'infe' boxes. Mapping IDs for reference...")
                for infe_box in iinf_children_to_fix:
                    unshifted_id = infe_box.item_id >> 16
                    if unshifted_id in correct_ids:
                        shifted_id_map[infe_box.item_id] = unshifted_id
                        print(f"  - Mapping 'infe' ID {infe_box.item_id} -> {unshifted_id}")
            else:
                print("  'infe' boxes seem correct. No shift detected.")

            if flat_heic_file._iprp_box.ipma:
                ipma_entries = flat_heic_file._iprp_box.ipma.entries
                keys_to_fix = [key for key in ipma_entries if key in shifted_id_map]

                if keys_to_fix:
                    print(f"  Found {len(keys_to_fix)} shifted 'ipma' entries. Fixing them...")
                    for shifted_key in keys_to_fix:
                        correct_key = shifted_id_map[shifted_key]
                        print(f"  - Fixing 'ipma' key {shifted_key} -> {correct_key}")
                        entry_data = ipma_entries.pop(shifted_key)
                        entry_data.item_id = correct_key
                        ipma_entries[correct_key] = entry_data
                else:
                    print(f"  'ipma' entries seem correct. (Keys: {list(ipma_entries.keys())})")

            if flat_heic_file._iref_box:
                iref_refs = flat_heic_file._iref_box.references
                refs_fixed = 0
                for ref_type in iref_refs:
                    keys_to_fix = [key for key in iref_refs[ref_type] if key in shifted_id_map]
                    if keys_to_fix:
                        refs_fixed += len(keys_to_fix)
                        for shifted_key in keys_to_fix:
                            correct_key = shifted_id_map[shifted_key]
                            print(f"  - Fixing 'iref' key [{ref_type}] {shifted_key} -> {correct_key}")
                            iref_refs[ref_type][correct_key] = iref_refs[ref_type].pop(shifted_key)

                if refs_fixed > 0:
                    print(f"  Fixed {refs_fixed} 'iref' entries.")
                else:
                    print("  'iref' entries seem correct.")

        if flat_heic_file.set_content_identifier(new_content_id):
            print("Successfully set ContentIdentifier in flat HEIC.")
        else:
            raise RuntimeError("Failed to set ContentIdentifier in flat HEIC.")

        print("Rebuilding flat HEIC with new metadata...")
        builder = HEICBuilder(flat_heic_file)
        builder.write(str(heic_path))

    finally:
        if temp_flat_path.exists():
            temp_flat_path.unlink()
            print(f"Cleaned up temporary file: {temp_flat_path}")

    print("--- Conversion complete ---")
    print(f"New HEIC: {heic_path}")
    if mov_path:
        print(f"New MOV:  {mov_path}")
    print("\n" + "=" * 40 + "\n")

    return heic_path, mov_path
