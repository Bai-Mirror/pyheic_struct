from __future__ import annotations

import struct
import subprocess
from pathlib import Path

from .base import TargetAdapter


def _build_apple_maker_note(
    content_id: str,
    photo_id: str,
    *,
    capture_request_id: str | None = None,
    live_photo_video_index: int = 0,
) -> bytes:
    """
    Construct a minimal Apple MakerNote payload containing Live Photo identifiers.
    """

    def _encode_ascii(value: str) -> bytes:
        return value.encode("ascii") + b"\x00"

    normalized_content = content_id.upper()
    normalized_photo = photo_id.upper()
    normalized_request = (
        (capture_request_id or photo_id).upper()
    )

    entries: list[dict[str, object]] = [
        {"tag": 0x0001, "type": 9, "count": 1, "value": 16},  # MakerNoteVersion
        {
            "tag": 0x0011,
            "type": 2,
            "count": len(normalized_content) + 1,
            "data": _encode_ascii(normalized_content),
        },  # ContentIdentifier
        {"tag": 0x0014, "type": 9, "count": 1, "value": 12},  # ImageCaptureType (Live Photo)
        {
            "tag": 0x0017,
            "type": 16,
            "count": 1,
            "data": live_photo_video_index.to_bytes(8, "big", signed=False),
        },  # LivePhotoVideoIndex
        {"tag": 0x001F, "type": 9, "count": 1, "value": 0},  # PhotosAppFeatureFlags
        {
            "tag": 0x0020,
            "type": 2,
            "count": len(normalized_request) + 1,
            "data": _encode_ascii(normalized_request),
        },  # ImageCaptureRequestID
        {
            "tag": 0x002B,
            "type": 2,
            "count": len(normalized_photo) + 1,
            "data": _encode_ascii(normalized_photo),
        },  # PhotoIdentifier
    ]

    header = bytearray(b"Apple iOS\x00\x00\x01MM")
    header.extend(struct.pack(">H", len(entries)))

    # Compute the offset where variable-length data begins.
    data_offset_base = len(header) + len(entries) * 12 + 4
    variable_data = bytearray()
    payload = bytearray(header)

    for entry in entries:
        tag = int(entry["tag"])
        entry_type = int(entry["type"])
        count = int(entry["count"])
        data_bytes = entry.get("data")

        if data_bytes is not None:
            data_bytes = bytes(data_bytes)
            value_offset = data_offset_base + len(variable_data)
            payload.extend(struct.pack(">HHII", tag, entry_type, count, value_offset))
            variable_data.extend(data_bytes)

            # Maintain word alignment for TIFF payloads.
            if len(data_bytes) % 2:
                variable_data.extend(b"\x00")
        else:
            value = int(entry["value"]) & 0xFFFFFFFF
            payload.extend(struct.pack(">HHII", tag, entry_type, count, value))

    payload.extend(struct.pack(">I", 0))  # next IFD offset
    payload.extend(variable_data)
    return bytes(payload)


class AppleTargetAdapter(TargetAdapter):
    """
    将平面 HEIC 调整为苹果兼容格式，并在 MOV 中写入 ContentIdentifier。
    """

    name = "apple"

    APPLE_BRAND_PAYLOAD = b"heic\x00\x00\x00\x00mif1MiHBMiHEMiPrmiafheictmap"

    def apply_to_flat_heic(self, flat_heic, content_id: str, photo_id: str | None = None) -> None:
        if not flat_heic._ftyp_box:
            raise RuntimeError("Temporary HEIC file has no 'ftyp' box.")

        print("Modifying 'ftyp' box to be Apple compatible (heic, MiHB, MiHE...)...")
        flat_heic._ftyp_box.raw_data = self.APPLE_BRAND_PAYLOAD
        flat_heic._ftyp_box.size = len(self.APPLE_BRAND_PAYLOAD) + 8

        if flat_heic.set_content_identifier(content_id):
            print("Successfully set ContentIdentifier in flat HEIC.")
        else:
            raise RuntimeError("Failed to set ContentIdentifier in flat HEIC.")

        resolved_photo_id = photo_id or content_id
        maker_note_payload = _build_apple_maker_note(
            content_id,
            resolved_photo_id,
            capture_request_id=resolved_photo_id,
        )
        flat_heic.set_exif_maker_note(maker_note_payload)
        print("Embedded Apple MakerNote metadata for Live Photo pairing.")

    def post_process_mov(self, mov_path: Path, content_id: str, inject_content_id: bool) -> None:
        if not inject_content_id or not mov_path.exists():
            return

        try:
            print("Attempting to inject ContentIdentifier into .MOV file (requires exiftool)...")
            subprocess.run(
                [
                    "exiftool",
                    f"-QuickTime:ContentIdentifier={content_id}",
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
