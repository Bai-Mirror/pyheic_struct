import os
from base import Box
from parser import parse_boxes
from heic_types import ItemLocationBox

# Import handlers
from handlers.base_handler import VendorHandler
from handlers.apple_handler import AppleHandler
from handlers.samsung_handler import SamsungHandler

class HEICFile:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._iloc_box: ItemLocationBox = None
        self._ftyp_box: Box = None
        self.handler: VendorHandler = None # Will hold our strategy object

        with open(self.filepath, 'rb') as f:
            file_size = os.fstat(f.fileno()).st_size
            self.boxes = parse_boxes(f, file_size)
            
            self._find_essential_boxes(self.boxes)
            self._detect_vendor()

    def _find_essential_boxes(self, boxes: list[Box]):
        """Recursively search for essential boxes."""
        for box in boxes:
            if box.type == 'iloc': self._iloc_box = box
            if box.type == 'ftyp': self._ftyp_box = box
            if box.children: self._find_essential_boxes(box.children)

    def _detect_vendor(self):
        """
        Inspects the 'ftyp' box to determine the vendor and assign the correct handler.
        """
        if self._ftyp_box:
            compatible_brands = self._ftyp_box.raw_data[4:].decode('ascii', errors='ignore')
            if 'samsung' in compatible_brands.lower() or 'mpvd' in [b.type for b in self.boxes]:
                 self.handler = SamsungHandler()
                 return
            if 'apple' in compatible_brands.lower() or 'MiHB' in compatible_brands:
                 self.handler = AppleHandler()
                 return
        
        # If no specific handler is found, use the base one.
        print("Could not detect a specific vendor. Using default handler.")
        self.handler = VendorHandler()


    def get_item_data(self, item_id: int) -> bytes | None:
        # ... (this method remains unchanged) ...
        if not self._iloc_box:
            print("Error: 'iloc' box not found.")
            return None
        location = next((loc for loc in self._iloc_box.locations if loc.item_id == item_id), None)
        if not location:
            print(f"Error: Item with ID {item_id} not found in 'iloc' box.")
            return None
        with open(self.filepath, 'rb') as f:
            # IMPORTANT: iloc offsets are absolute from the start of the file.
            # The mdat box's offset is not needed for this calculation.
            f.seek(location.offset)
            data = f.read(location.length)
            return data

    def get_motion_photo_data(self) -> bytes | None:
        """
        Delegates the search for motion photo data to the assigned vendor handler.
        """
        offset = self.handler.find_motion_photo_offset(self)
        if offset is not None:
            with open(self.filepath, 'rb') as f:
                # We assume the video data goes to the end of the file from its offset
                f.seek(offset)
                return f.read()
        return None