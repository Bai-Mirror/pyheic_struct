# pyheic_struct/heic_file.py

import os
import math
# 1. 导入新的库
import pillow_heif
from io import BytesIO
from dataclasses import dataclass
from PIL import Image

from .base import Box
from .parser import parse_boxes
from .heic_types import (
    ItemLocationBox, PrimaryItemBox, ItemInfoBox, ItemPropertiesBox,
    ImageSpatialExtentsBox, ItemReferenceBox, ItemInfoEntryBox,
    _read_int
)
from .handlers.base_handler import VendorHandler
from .handlers.apple_handler import AppleHandler
from .handlers.samsung_handler import SamsungHandler

@dataclass
class Grid:
    rows: int
    columns: int
    output_width: int
    output_height: int

class HEICFile:
    def __init__(self, filepath: str):
        self.filepath = filepath
        pillow_heif.register_heif_opener()
        
        self._iloc_box: ItemLocationBox | None = None
        self._ftyp_box: Box | None = None
        self._iinf_box: ItemInfoBox | None = None
        self._pitm_box: PrimaryItemBox | None = None
        self._iprp_box: ItemPropertiesBox | None = None
        self._iref_box: ItemReferenceBox | None = None
        self.handler: VendorHandler | None = None
        self.boxes: list[Box] = [] # 顶层盒子

        try:
            with open(self.filepath, 'rb') as f:
                file_size = os.fstat(f.fileno()).st_size
                self.boxes = parse_boxes(f, file_size)
                self._find_essential_boxes(self.boxes)
                self._detect_vendor()
        except Exception as e:
            print(f"CRITICAL ERROR during file parsing: {e}")
            raise

    def _find_essential_boxes(self, boxes: list[Box]):
        """在解析树中查找关键盒子的快捷方式"""
        for box in boxes:
            if isinstance(box, ItemLocationBox): self._iloc_box = box
            if isinstance(box, ItemInfoBox): self._iinf_box = box
            if isinstance(box, PrimaryItemBox): self._pitm_box = box
            if isinstance(box, ItemPropertiesBox): self._iprp_box = box
            if isinstance(box, ItemReferenceBox): self._iref_box = box
            if box.type == 'ftyp': self._ftyp_box = box
            if box.children: self._find_essential_boxes(box.children)

    # --- 辅助方法 (用于修改和构建) ---

    def find_box(self, box_type: str, root_box_list: list[Box] | None = None) -> Box | None:
        """递归查找第一个匹配类型的盒子"""
        if root_box_list is None:
            root_box_list = self.boxes
            
        for box in root_box_list:
            if box.type == box_type:
                return box
            if box.children:
                found = self.find_box(box_type, root_box_list=box.children)
                if found:
                    return found
        return None

    def get_mdat_box(self) -> Box | None:
        """获取顶层的 'mdat' 盒"""
        for box in self.boxes:
            if box.type == 'mdat':
                return box
        return None

    def _remove_box_recursive(self, box_type: str, box_list: list[Box]) -> bool:
        """Helper for remove_box_by_type"""
        for i, box in enumerate(box_list):
            if box.type == box_type:
                box_list.pop(i)
                return True
            if box.children:
                if self._remove_box_recursive(box_type, box.children):
                    return True
        return False

    def remove_box_by_type(self, box_type: str) -> bool:
        """递归查找并移除第一个匹配类型的盒子"""
        return self._remove_box_recursive(box_type, self.boxes)

    # --- START V16 FIX ---
    def remove_item_by_id(self, item_id_to_remove: int):
        """
        (V16 - 垃圾回收版) 
        彻底从 iinf, iloc, ipma, iref 中删除一个 Item ID，
        并从 ipco 中删除孤立的属性，然后重写所有剩余的 ipma 索引。
        """
        print(f"Attempting to remove Item ID {item_id_to_remove} from all references (V16)...")
        
        # 1. 从 iinf (Item Info) 中删除
        if self._iinf_box:
            self._iinf_box.children = [
                c for c in self._iinf_box.children 
                if not (isinstance(c, ItemInfoEntryBox) and c.item_id == item_id_to_remove)
            ]
            self._iinf_box.entries = [
                e for e in self._iinf_box.entries 
                if e.item_id != item_id_to_remove
            ]
            print(f"  - Removed from 'iinf' box.")

        # 2. 从 iloc (Item Location) 中删除
        if self._iloc_box:
            self._iloc_box.locations = [
                loc for loc in self._iloc_box.locations 
                if loc.item_id != item_id_to_remove
            ]
            print(f"  - Removed from 'iloc' box.")

        # 3. (新) 从 iref (Item Reference) 中删除
        if self._iref_box:
            for i in range(len(self._iref_box.children) - 1, -1, -1):
                ref_box = self._iref_box.children[i]
                from_id_size = 4 if self._iref_box.version == 1 else 2
                if len(ref_box.raw_data) >= 4 + from_id_size:
                    from_id = _read_int(ref_box.raw_data, 4, from_id_size)
                    if from_id == item_id_to_remove:
                        self._iref_box.children.pop(i)
                        print(f"  - Removed 'iref' child box (type '{ref_box.type}') with from_id {from_id}.")
            
            ref_types_to_clean = list(self._iref_box.references.keys())
            for ref_type in ref_types_to_clean:
                if item_id_to_remove in self._iref_box.references[ref_type]:
                    del self._iref_box.references[ref_type][item_id_to_remove]
                    print(f"  - Removed from_id {item_id_to_remove} from 'iref.references[{ref_type}]'.")
                
                from_ids_to_clean = list(self._iref_box.references[ref_type].keys())
                for from_id in from_ids_to_clean:
                    self._iref_box.references[ref_type][from_id] = [
                        to_id for to_id in self._iref_box.references[ref_type][from_id]
                        if to_id != item_id_to_remove
                    ]
            print(f"  - Cleaned 'iref.references' of to_id {item_id_to_remove}.")

        # 4. 从 ipma 和 ipco (属性) 中删除
        if self._iprp_box and self._iprp_box.ipma and self._iprp_box.ipco:
            ipma = self._iprp_box.ipma
            ipco = self._iprp_box.ipco
            
            if item_id_to_remove not in ipma.entries:
                print(f"  - Item {item_id_to_remove} not in 'ipma'. No properties to clean.")
                return 
            
            # 4a. 找到要删除的属性索引 (1-based)
            props_to_remove = {
                assoc.property_index
                for assoc in ipma.entries[item_id_to_remove].associations
            }
            
            # 4b. 从 ipma 中删除该 Item
            del ipma.entries[item_id_to_remove]
            print(f"  - Removed Item {item_id_to_remove} from 'ipma'.")

            # 4c. 确定哪些属性是“孤儿”
            # (即，它们在 props_to_remove 中，但*不在*任何*剩余*的 item 关联中)
            all_remaining_props = set()
            for entry in ipma.entries.values():
                all_remaining_props.update(
                    assoc.property_index for assoc in entry.associations
                )
            
            orphaned_props = props_to_remove - all_remaining_props
            
            if not orphaned_props:
                print(f"  - No orphaned properties found in 'ipco' to remove.")
                return

            print(f"  - Found orphaned properties to remove from 'ipco': {orphaned_props}")
            
            # 4d. 创建一个“重映射表”
            # 我们从后往前遍历，以安全地删除
            # (索引是 1-based, 但列表是 0-based)
            orphaned_indices_0based = sorted([p - 1 for p in orphaned_props], reverse=True)
            
            # 原始 1-based 索引 -> 新 1-based 索引
            remap_table = {} 
            original_prop_count = len(ipco.children)
            
            # 4e. 从 'ipco.children' 列表中删除孤儿
            for index_0 in orphaned_indices_0based:
                if 0 <= index_0 < len(ipco.children):
                    removed_prop = ipco.children.pop(index_0)
                    print(f"    - Removed property at index {index_0+1} ({removed_prop.type}) from 'ipco'.")
                else:
                    print(f"    - Warning: Orphaned index {index_0+1} out of bounds for 'ipco'.")

            # 4f. 构建重映射表
            # (只有在 ipco 实际发生变化时才需要)
            new_prop_count = len(ipco.children)
            if new_prop_count != original_prop_count:
                print("  - Re-indexing 'ipma' associations...")
                current_new_index = 1
                current_old_index = 1
                orphaned_props_1based = set(i + 1 for i in orphaned_indices_0based)
                
                while current_old_index <= original_prop_count:
                    if current_old_index not in orphaned_props_1based:
                        remap_table[current_old_index] = current_new_index
                        current_new_index += 1
                    current_old_index += 1
                
                # 4g. 应用重映射
                for item_id, entry in ipma.entries.items():
                    new_associations = []
                    for assoc in entry.associations:
                        old_prop_index = assoc.property_index
                        if old_prop_index in remap_table:
                            assoc.property_index = remap_table[old_prop_index]
                            new_associations.append(assoc)
                        # else:
                        #   该属性已被删除 (不应发生，因为我们只删除了孤儿)
                    
                    # print(f"    - Item {item_id} associations: {entry.associations} -> {new_associations}")
                    entry.associations = new_associations
                print("  - 'ipma' re-indexing complete.")
            else:
                 print("  - No 'ipma' re-indexing needed.")
    # --- END V16 FIX ---

    def set_content_identifier(self, new_content_id: str) -> bool:
        """
        (FIXED) 在 'iinf' 盒中查找主图像的 'infe' 盒，并设置其 item_name
        """
        primary_id = self.get_primary_item_id()
        if not primary_id:
            print("Error: Cannot find primary item ID.")
            return False
            
        if not self._iinf_box:
            print("Error: Cannot find 'iinf' box shortcut (_iinf_box).")
            return False
            
        print(f"Searching for 'infe' box with primary_id = {primary_id}")
        
        # --- START FIX ---
        # 侦测我们日志中看到的 "shifted ID" 格式
        
        target_id = primary_id
        found_ids = [box.item_id for box in self._iinf_box.children if isinstance(box, ItemInfoEntryBox)]
        
        if primary_id not in found_ids:
            print(f"Warning: Primary ID {primary_id} not found directly in 'infe' list.")
            shifted_id = primary_id << 16
            if shifted_id in found_ids:
                print(f"Info: Found vendor-specific shifted ID: {shifted_id} (for {primary_id})")
                target_id = shifted_id
            else:
                print(f"Error: Could not find primary ID {primary_id} OR shifted ID {shifted_id}.")
                print(f"Available 'infe' item IDs found were: {found_ids}")
                return False
        # --- END FIX ---
            
        # 'iinf' 盒的子盒是 'infe' 盒
        for box in self._iinf_box.children:
            if isinstance(box, ItemInfoEntryBox):
                if box.item_id == target_id:
                    print(f"Success: Found 'infe' box for target ID {target_id}. Setting item_name...")
                    box.item_name = new_content_id
                    
                    # 同时更新 self._iinf_box.entries 中的数据以保持一致
                    for entry in self._iinf_box.entries:
                        if entry.item_id == target_id:
                            entry.name = new_content_id
                            break
                    return True
                    
        print(f"Error: Logic failed to find 'infe' box for target ID {target_id} even after check.")
        return False

    # --- 现有的只读方法 (无需修改) ---

    def reconstruct_primary_image(self) -> Image.Image | None:
        """
        使用 pillow-heif 重建主图像，它能自动处理网格图像。
        """
        try:
            print("Reconstructing primary image using pillow-heif...")
            image = Image.open(self.filepath)
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
        
        # 尝试直接匹配
        if 'dimg' in self._iref_box.references and primary_id in self._iref_box.references['dimg']:
            return self._iref_box.references['dimg'].get(primary_id)
        
        # 尝试匹配 "shifted" ID
        shifted_id = primary_id << 16
        if 'dimg' in self._iref_box.references and shifted_id in self._iref_box.references['dimg']:
             print("Info: Using shifted primary ID to find grid layout.")
             return self._iref_box.references['dimg'].get(shifted_id)
             
        return None

    def get_image_size(self, item_id: int) -> tuple[int, int] | None:
        if not (self._iprp_box and self._iprp_box.ipma and self._iprp_box.ipco): return None
        
        target_id = item_id
        if item_id not in self._iprp_box.ipma.entries:
            # 尝试 "shifted" ID
            shifted_id = item_id << 16
            if shifted_id in self._iprp_box.ipma.entries:
                target_id = shifted_id
            else:
                 # 尝试 "unshifted" ID (以防 item_id 本身就是 shifted 的)
                 unshifted_id = item_id & 0x0000FFFF
                 if unshifted_id in self._iprp_box.ipma.entries:
                     target_id = unshifted_id
                 else:
                    # print(f"Warning: Cannot find size associations for item ID {item_id} or variants.")
                    return None
        
        item_associations = self._iprp_box.ipma.entries[target_id].associations
        for assoc in item_associations:
            property_index = assoc.property_index - 1
            if 0 <= property_index < len(self._iprp_box.ipco.children):
                prop = self._iprp_box.ipco.children[property_index]
                if isinstance(prop, ImageSpatialExtentsBox):
                    return (prop.image_width, prop.image_height)
        return None

    def get_primary_item_id(self) -> int | None:
        if not self._pitm_box: 
            print("Warning: 'pitm' box not found.")
            return None
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
            
        target_id = item_id
        location = next((loc for loc in self._iloc_box.locations if loc.item_id == target_id), None)
        
        if not location:
            # 尝试检查 "shifted" ID
            shifted_id = item_id << 16
            location = next((loc for loc in self._iloc_box.locations if loc.item_id == shifted_id), None)
            if location:
                print(f"Info: Located item {item_id} using shifted ID {shifted_id} in 'iloc'.")
                target_id = shifted_id
            
        if not location and (item_id & 0xFFFF0000):
            # 尝试反向检查 (如果传入的 ID 已经是 shifted 的)
            unshifted_id = item_id & 0x0000FFFF
            location = next((loc for loc in self._iloc_box.locations if loc.item_id == unshifted_id), None)
            if location:
                 print(f"Info: Located item {item_id} using un-shifted ID {unshifted_id} in 'iloc'.")
                 target_id = unshifted_id

        if not location:
            print(f"Error: Item with ID {item_id} (or variants) not found in 'iloc' box.")
            return None

        if not location.extents:
             print(f"Warning: Item with ID {target_id} has no extents.")
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
            print("Found motion photo data at offset.")
            with open(self.filepath, 'rb') as f:
                f.seek(offset)
                return f.read()
        return None

    def get_thumbnail_data(self) -> bytes | None:
        print("Attempting to extract thumbnail data...")
        primary_id = self.get_primary_item_id()
        if not primary_id:
            print("Error: Could not determine primary item ID.")
            return None
        
        if not self._iref_box:
            print("Info: No 'iref' box found, cannot search for thumbnail.")
            return None

        if 'thmb' not in self._iref_box.references:
            print("Info: No 'thmb' references found in 'iref' box.")
            return None
        
        target_id = primary_id
        if primary_id not in self._iref_box.references['thmb']:
            # Lпробуйте проверить "shifted" ID
            shifted_primary_id = primary_id << 16
            if shifted_primary_id not in self._iref_box.references['thmb']:
                print(f"Info: Primary item ID {primary_id} (or shifted) has no 'thmb' reference.")
                return None
            
            print("Info: Using shifted primary ID to find thumbnail.")
            target_id = shifted_primary_id


        thumbnail_ids = self._iref_box.references['thmb'][target_id]
        if not thumbnail_ids:
            print(f"Info: Primary item ID {target_id} has 'thmb' reference, but no target IDs.")
            return None

        thumbnail_id = thumbnail_ids[0]
        print(f"Found thumbnail reference: Primary ID {target_id} -> Thumbnail ID {thumbnail_id}")
        
        thumbnail_data = self.get_item_data(thumbnail_id)
        
        if thumbnail_data:
            print(f"Successfully extracted thumbnail data (Item ID {thumbnail_id}).")
            return thumbnail_data
        else:
            print(f"Error: Failed to get data for thumbnail item ID {thumbnail_id}.")
            return None
