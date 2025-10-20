# pyheic_struct/heic_file.py

import os
import math
# 1. 导入新的库
import pillow_heif
from io import BytesIO
from dataclasses import dataclass
from PIL import Image

from base import Box
from parser import parse_boxes
from heic_types import (
    ItemLocationBox, PrimaryItemBox, ItemInfoBox, ItemPropertiesBox,
    ImageSpatialExtentsBox, ItemReferenceBox
)
from handlers.base_handler import VendorHandler
from handlers.apple_handler import AppleHandler
from handlers.samsung_handler import SamsungHandler

@dataclass
class Grid:
    rows: int
    columns: int
    output_width: int
    output_height: int

class HEICFile:
    def __init__(self, filepath: str):
        self.filepath = filepath
        # 注册 HEIF/HEIC 文件格式解码器
        pillow_heif.register_heif_opener()
        
        self._iloc_box: ItemLocationBox | None = None
        self._ftyp_box: Box | None = None
        self._iinf_box: ItemInfoBox | None = None
        self._pitm_box: PrimaryItemBox | None = None
        self._iprp_box: ItemPropertiesBox | None = None
        self._iref_box: ItemReferenceBox | None = None
        self.handler: VendorHandler | None = None

        with open(self.filepath, 'rb') as f:
            file_size = os.fstat(f.fileno()).st_size
            self.boxes = parse_boxes(f, file_size)
            self._find_essential_boxes(self.boxes)
            self._detect_vendor()

    def _find_essential_boxes(self, boxes: list[Box]):
        for box in boxes:
            if isinstance(box, ItemLocationBox): self._iloc_box = box
            if isinstance(box, ItemInfoBox): self._iinf_box = box
            if isinstance(box, PrimaryItemBox): self._pitm_box = box
            if isinstance(box, ItemPropertiesBox): self._iprp_box = box
            if isinstance(box, ItemReferenceBox): self._iref_box = box
            if box.type == 'ftyp': self._ftyp_box = box
            if box.children: self._find_essential_boxes(box.children)

    # --- 2. 使用 pillow-heif 大大简化的图像重建方法 ---
    def reconstruct_primary_image(self) -> Image.Image | None:
        """
        使用 pillow-heif 重建主图像，它能自动处理网格图像。
        """
        try:
            print("Reconstructing primary image using pillow-heif...")
            # pillow-heif 让我们能像打开普通图片一样直接打开 HEIC 文件
            image = Image.open(self.filepath)
            
            # 确保图像数据被加载
            image.load() 
            
            print("Successfully reconstructed image.")
            return image
        except Exception as e:
            print(f"Failed to reconstruct image with pillow-heif: {e}")
            return None

    def get_primary_image_grid(self) -> Grid | None:
        primary_id = self.get_primary_item_id()
        if not primary_id: return None
        full_size = self.get_image_size(primary_id)
        if not full_size: return None
        full_width, full_height = full_size
        grid_tiles = self.get_grid_layout()
        if not grid_tiles: return None
        first_tile_id = grid_tiles[0]
        tile_size = self.get_image_size(first_tile_id)
        if not tile_size: return None
        tile_width, tile_height = tile_size
        if tile_width == 0 or tile_height == 0: return None
        columns = math.ceil(full_width / tile_width)
        rows = math.ceil(full_height / tile_height)
        return Grid(rows=rows, columns=columns, output_width=full_width, output_height=full_height)

    def get_grid_layout(self) -> list[int] | None:
        primary_id = self.get_primary_item_id()
        if not primary_id: return None
        if not self._iref_box: return None
        return self._iref_box.references.get(primary_id)

    def get_image_size(self, item_id: int) -> tuple[int, int] | None:
        if not (self._iprp_box and self._iprp_box.ipma and self._iprp_box.ipco): return None
        if item_id not in self._iprp_box.ipma.entries: return None
        item_associations = self._iprp_box.ipma.entries[item_id].associations
        for assoc in item_associations:
            property_index = assoc - 1
            if 0 <= property_index < len(self._iprp_box.ipco.children):
                prop = self._iprp_box.ipco.children[property_index]
                if isinstance(prop, ImageSpatialExtentsBox):
                    return (prop.image_width, prop.image_height)
        return None

    def get_primary_item_id(self) -> int | None:
        if not self._pitm_box: return None
        return self._pitm_box.item_id

    def list_items(self):
        if not self._iinf_box: return
        print("Available items in HEIC file:")
        for entry in self._iinf_box.entries: print(f"  - {entry}")

    def _detect_vendor(self):
        if self._ftyp_box:
            compatible_brands = self._ftyp_box.raw_data[4:].decode('ascii', errors='ignore')
            if 'samsung' in compatible_brands.lower(): self.handler = SamsungHandler()
            elif 'apple' in compatible_brands.lower() or 'MiHB' in compatible_brands: self.handler = AppleHandler()
            else: self.handler = VendorHandler()
        else: self.handler = VendorHandler()

    def get_item_data(self, item_id: int) -> bytes | None:
        if not self._iloc_box:
            print("Error: 'iloc' box not found.")
            return None
        location = next((loc for loc in self._iloc_box.locations if loc.item_id == item_id), None)
        if not location:
            print(f"Error: Item with ID {item_id} not found in 'iloc' box.")
            return None
        if not location.extents:
             print(f"Warning: Item with ID {item_id} has no extents.")
             return b''

        data_chunks = []
        with open(self.filepath, 'rb') as f:
            for offset, length in location.extents:
                f.seek(offset)
                data_chunks.append(f.read(length))
        return b''.join(data_chunks)

    def get_motion_photo_data(self) -> bytes | None:
        if not self.handler: self._detect_vendor()
        offset = self.handler.find_motion_photo_offset(self)
        if offset is not None:
            with open(self.filepath, 'rb') as f:
                f.seek(offset)
                return f.read()
        return None