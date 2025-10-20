from .base_handler import VendorHandler

class SamsungHandler(VendorHandler):
    """Handles Samsung-specific HEIC features, like the embedded mpvd box."""

    def find_motion_photo_offset(self, heic_file) -> int | None:
        """
        Searches for the 'mpvd' box which contains the video data.
        """
        # --- START FIX ---
        # 使用 heic_file.find_box 进行递归搜索，因为 mpvd 嵌套在 meta 中
        mpvd_box = heic_file.find_box('mpvd')
        if mpvd_box:
            print(f"Samsung 'mpvd' box found at offset {mpvd_box.offset}")
            # 视频数据在 8 字节头部之后开始
            return mpvd_box.offset + 8
        # --- END FIX ---
        
        print("Samsung HEIC detected, but no 'mpvd' box found.")
        return None