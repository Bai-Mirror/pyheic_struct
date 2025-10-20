from __future__ import annotations

from typing import TYPE_CHECKING

from .base_handler import VendorHandler

if TYPE_CHECKING:
    from ..heic_file import HEICFile
    from ..targets.base import TargetAdapter


class AppleHandler(VendorHandler):
    """
    Handles Apple-specific HEIC features.

    Apple's motion photos (Live Photos) are stored in a separate MOV file,
    so we won't find an embedded video here.
    """

    name = "apple"
    priority = 50

    @classmethod
    def matches(cls, heic_file: HEICFile) -> bool:
        brands = heic_file.get_compatible_brands()
        # 只要检测到 heic/mif1/MiHB/MiHE 等苹果常见品牌即可视为苹果文件。
        return any(brand in {"heic", "mif1", "mihb", "mihe"} for brand in brands)

    def find_motion_photo_offset(self, heic_file: HEICFile) -> int | None:
        print("Apple HEIC detected. Motion photo video is in a separate .mov file, not embedded.")
        return None

    def supports_target(self, target_adapter: TargetAdapter) -> bool:
        # Apple 文件可作为源，被转换到任意目标。目前默认支持。
        return True
