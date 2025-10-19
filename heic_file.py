# pyheic_struct/heic_file.py

import os
from base import Box
from parser import parse_boxes
from heic_types import (
    ItemLocationBox, PrimaryItemBox, ItemInfoBox, ItemPropertiesBox,
    ImageSpatialExtentsBox
)

from handlers.base_handler import VendorHandler
from handlers.apple_handler import AppleHandler
from handlers.samsung_handler import SamsungHandler

class HEICFile:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._iloc_box: ItemLocationBox | None = None
        self._ftyp_box: Box | None = None
        self._iinf_box: ItemInfoBox | None = None
        self._pitm_box: PrimaryItemBox | None = None
        self._iprp_box: ItemPropertiesBox | None = None
        self.handler: VendorHandler | None = None

        with open(self.filepath, 'rb') as f:
            file_size = os.fstat(f.fileno()).st_size
            self.boxes = parse_boxes(f, file_size)
            self._find_essential_boxes(self.boxes)
            self._detect_vendor()

    # --- FIX: Changed 'elif' to separate 'if' statements for robustness ---
    def _find_essential_boxes(self, boxes: list[Box]):
        """Recursively search for essential boxes."""
        for box in boxes:
            if isinstance(box, ItemLocationBox):
                self._iloc_box = box
            if isinstance(box, ItemInfoBox):
                self._iinf_box = box
            if isinstance(box, PrimaryItemBox):
                self._pitm_box = box
            if isinstance(box, ItemPropertiesBox):
                self._iprp_box = box
            if box.type == 'ftyp':
                self._ftyp_box = box

            if box.children:
                self._find_essential_boxes(box.children)

    # All other methods remain unchanged
    def get_image_size(self, item_id: int) -> tuple[int, int] | None:
        """
        Gets the width and height of a given image item ID.
        """
        if not self._iprp_box or not self._iprp_box.ipma or not self._iprp_box.ipco:
            print("Warning: 'iprp' box or its sub-boxes ('ipma', 'ipco') not found.")
            return None
        
        if item_id not in self._iprp_box.ipma.entries:
            print(f"Warning: No property association found for item ID {item_id}.")
            return None
        
        item_associations = self._iprp_box.ipma.entries[item_id].associations

        for assoc in item_associations:
            property_index = assoc - 1
            if property_index < len(self._iprp_box.ipco.children):
                prop = self._iprp_box.ipco.children[property_index]
                if isinstance(prop, ImageSpatialExtentsBox):
                    return (prop.image_width, prop.image_height)
        
        print(f"Warning: 'ispe' property not found for item ID {item_id}.")
        return None

    def get_primary_item_id(self) -> int | None:
        if not self._pitm_box:
            print("Warning: 'pitm' box not found. Cannot determine primary item.")
            return None
        return self._pitm_box.item_id

    def list_items(self):
        if not self._iinf_box:
            print("Warning: 'iinf' box not found. Cannot list items.")
            return
        
        print("Available items in HEIC file:")
        for entry in self._iinf_box.entries:
            print(f"  - {entry}")

    def _detect_vendor(self):
        if self._ftyp_box:
            compatible_brands = self._ftyp_box.raw_data[4:].decode('ascii', errors='ignore')
            if 'samsung' in compatible_brands.lower() or 'mpvd' in [b.type for b in self.boxes]:
                 self.handler = SamsungHandler()
                 return
            if 'apple' in compatible_brands.lower() or 'MiHB' in compatible_brands:
                 self.handler = AppleHandler()
                 return
        
        print("Could not detect a specific vendor. Using default handler.")
        self.handler = VendorHandler()

    def get_item_data(self, item_id: int) -> bytes | None:
        if not self._iloc_box:
            print("Error: 'iloc' box not found.")
            return None
        location = next((loc for loc in self._iloc_box.locations if loc.item_id == item_id), None)
        if not location:
            print(f"Error: Item with ID {item_id} not found in 'iloc' box.")
            return None
        with open(self.filepath, 'rb') as f:
            f.seek(location.offset)
            data = f.read(location.length)
            return data

    def get_motion_photo_data(self) -> bytes | None:
        if not self.handler:
            self._detect_vendor()
        offset = self.handler.find_motion_photo_offset(self)
        if offset is not None:
            with open(self.filepath, 'rb') as f:
                f.seek(offset)
                return f.read()
        return None