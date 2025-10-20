from .base_handler import VendorHandler

class AppleHandler(VendorHandler):
    """
    Handles Apple-specific HEIC features.
    Apple's motion photos (Live Photos) are stored in a separate MOV file,
    so we won't find an embedded video here.
    """
    # We override the method to make it explicit that Apple files are handled,
    # even though the result is the same as the base class.
    def find_motion_photo_offset(self, heic_file) -> int | None:
        # We could add logic here later to find the ContentIdentifier
        print("Apple HEIC detected. Motion photo video is in a separate .mov file, not embedded.")
        return None