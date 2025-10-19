from .base_handler import VendorHandler

class SamsungHandler(VendorHandler):
    """Handles Samsung-specific HEIC features, like the embedded mpvd box."""

    def find_motion_photo_offset(self, heic_file) -> int | None:
        """
        Searches for the 'mpvd' box which contains the video data.
        """
        for box in heic_file.boxes:
            if box.type == 'mpvd':
                print(f"Samsung 'mpvd' box found at offset {box.offset}")
                # The video data starts right after the box header.
                return box.offset + 8 
        
        print("Samsung HEIC detected, but no 'mpvd' box found.")
        return None