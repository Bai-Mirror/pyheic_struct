from __future__ import annotations

import subprocess
from pathlib import Path

from .base import TargetAdapter


class AppleTargetAdapter(TargetAdapter):
    """
    将平面 HEIC 调整为苹果兼容格式，并在 MOV 中写入 ContentIdentifier。
    """

    name = "apple"

    APPLE_BRAND_PAYLOAD = b"heic\x00\x00\x00\x00mif1MiHBMiHEMiPrmiafheictmap"

    def apply_to_flat_heic(self, flat_heic, content_id: str) -> None:
        if not flat_heic._ftyp_box:
            raise RuntimeError("Temporary HEIC file has no 'ftyp' box.")

        print("Modifying 'ftyp' box to be Apple compatible (heic, MiHB, MiHE...)...")
        flat_heic._ftyp_box.raw_data = self.APPLE_BRAND_PAYLOAD
        flat_heic._ftyp_box.size = len(self.APPLE_BRAND_PAYLOAD) + 8

        if flat_heic.set_content_identifier(content_id):
            print("Successfully set ContentIdentifier in flat HEIC.")
        else:
            raise RuntimeError("Failed to set ContentIdentifier in flat HEIC.")

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
