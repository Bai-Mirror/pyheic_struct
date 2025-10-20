from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..heic_file import HEICFile

class VendorHandler:
    """
    Abstract base class for vendor-specific logic.
    """
    def find_motion_photo_offset(self, heic_file: HEICFile) -> int | None:
        """
        Tries to find the byte offset of the embedded motion photo video.
        Returns the offset if found, otherwise None.
        """
        # Default behavior: no motion photo found.
        return None
