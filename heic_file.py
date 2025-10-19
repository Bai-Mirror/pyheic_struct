# pyheic_struct/heic_file.py

import os
from base import Box
from parser import parse_boxes
from heic_types import (
    ItemLocationBox, PrimaryItemBox, ItemInfoBox, ItemPropertiesBox,
    ImageSpatialExtentsBox, ItemReferenceBox # <-- Import the new class
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
        self._iref_box: ItemReferenceBox | None = None # <-- Add new instance variable
        self.handler: VendorHandler | None = None

        with open(self.filepath, 'rb') as f:
            file_size = os.fstat(f.fileno()).st_size
            self.boxes = parse_boxes(f, file_size)
            self._find_essential_boxes(self.boxes)
            self._detect_vendor()

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
            if isinstance(box, ItemReferenceBox): # <-- Find and store the 'iref' box
                self._iref_box = box
            if box.type == 'ftyp':
                self._ftyp_box = box

            if box.children:
                self._find_essential_boxes(box.children)

    # --- NEW Method for Task 3.2 ---
    def get_grid_layout(self) -> list[int] | None:
        """
        Uses 'iref' and 'pitm' to find the tile IDs for the primary grid image.
        Returns a list of item IDs that make up the grid.
        """
        primary_id = self.get_primary_item_id()
        if not primary_id:
            return None

        if not self._iref_box:
            print("Warning: 'iref' box not found. Cannot determine grid layout.")
            return None
        
        # Find the reference entry that originates from the primary item ID
        grid_tile_ids = self._iref_box.references.get(primary_id)

        if not grid_tile_ids:
            print(f"Warning: No grid reference found for primary item ID {primary_id}.")
            return None

        return grid_tile_ids

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
            property_index = assoc - 1 # Property indices are 1-based
            if 0 <= property_index < len(self._iprp_box.ipco.children):
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
                # The actual video data could be the rest of the file or a specific length
                # For now, we assume it's a reasonable chunk.
                return f.read()
        return None