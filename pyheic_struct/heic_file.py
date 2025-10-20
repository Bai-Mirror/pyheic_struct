import os
import math
import pillow_heif
from dataclasses import dataclass
from PIL import Image

from .base import Box
from .parser import parse_boxes
from .heic_types import (
    ItemLocationBox, PrimaryItemBox, ItemInfoBox, ItemPropertiesBox,
    ImageSpatialExtentsBox, ItemReferenceBox, ItemInfoEntryBox,
    _read_int
)
from .handlers import VendorHandler, resolve_handler

@dataclass
class Grid:
    rows: int
    columns: int
    output_width: int
    output_height: int

class HEICFile:
    """High-level accessor for parsed HEIC/HEIF structures."""

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
        self.boxes: list[Box] = []  # Top-level boxes

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
        """Populate shortcut pointers for commonly used boxes."""
        for box in boxes:
            if isinstance(box, ItemLocationBox): self._iloc_box = box
            if isinstance(box, ItemInfoBox): self._iinf_box = box
            if isinstance(box, PrimaryItemBox): self._pitm_box = box
            if isinstance(box, ItemPropertiesBox): self._iprp_box = box
            if isinstance(box, ItemReferenceBox): self._iref_box = box
            if box.type == 'ftyp': self._ftyp_box = box
            if box.children: self._find_essential_boxes(box.children)

    def find_box(self, box_type: str, root_box_list: list[Box] | None = None) -> Box | None:
        """Recursively locate the first box with the requested fourcc."""
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
        """Return the top-level `mdat` box, if present."""
        for box in self.boxes:
            if box.type == 'mdat':
                return box
        return None

    def get_compatible_brands(self) -> set[str]:
        """
        Return the normalized set of brands listed in the `ftyp` box.
        """
        if not self._ftyp_box or not self._ftyp_box.raw_data:
            return set()

        raw = self._ftyp_box.raw_data
        brands: set[str] = set()

        if len(raw) >= 4:
            primary = raw[:4].decode("ascii", errors="ignore").strip("\x00").lower()
            if primary:
                brands.add(primary)

        # Skip 4-byte minor version
        for offset in range(8, len(raw), 4):
            chunk = raw[offset:offset + 4]
            if len(chunk) < 4:
                break
            brand = chunk.decode("ascii", errors="ignore").strip("\x00").lower()
            if brand:
                brands.add(brand)

        return brands

    def _remove_box_recursive(self, box_type: str, box_list: list[Box]) -> bool:
        """Internal helper used by `remove_box_by_type`."""
        for i, box in enumerate(box_list):
            if box.type == box_type:
                box_list.pop(i)
                return True
            if box.children:
                if self._remove_box_recursive(box_type, box.children):
                    return True
        return False

    def remove_box_by_type(self, box_type: str) -> bool:
        """Remove the first box matching `box_type`, searching recursively."""
        return self._remove_box_recursive(box_type, self.boxes)

    def remove_item_by_id(self, item_id_to_remove: int):
        """Fully remove an item from iinf/iloc/ipma/iref and clean orphaned properties."""
        print(f"Attempting to remove Item ID {item_id_to_remove} from all references (V16)...")

        # Update iinf metadata
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

        # Update iloc entries
        if self._iloc_box:
            self._iloc_box.locations = [
                loc for loc in self._iloc_box.locations 
                if loc.item_id != item_id_to_remove
            ]
            print(f"  - Removed from 'iloc' box.")

        # Update iref relationships
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

        # Update property associations and definitions
        if self._iprp_box and self._iprp_box.ipma and self._iprp_box.ipco:
            ipma = self._iprp_box.ipma
            ipco = self._iprp_box.ipco
            
            if item_id_to_remove not in ipma.entries:
                print(f"  - Item {item_id_to_remove} not in 'ipma'. No properties to clean.")
                return 
            
            # Identify property indices referenced exclusively by the removed item.
            props_to_remove = {
                assoc.property_index
                for assoc in ipma.entries[item_id_to_remove].associations
            }
            
            # Remove the item entry itself.
            del ipma.entries[item_id_to_remove]
            print(f"  - Removed Item {item_id_to_remove} from 'ipma'.")

            # Determine which properties are now unused.
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
            
            # Remove orphaned properties from `ipco`, iterating from the end to keep indices valid.
            orphaned_indices_0based = sorted([p - 1 for p in orphaned_props], reverse=True)
            
            remap_table = {}
            original_prop_count = len(ipco.children)
            
            for index_0 in orphaned_indices_0based:
                if 0 <= index_0 < len(ipco.children):
                    removed_prop = ipco.children.pop(index_0)
                    print(f"    - Removed property at index {index_0+1} ({removed_prop.type}) from 'ipco'.")
                else:
                    print(f"    - Warning: Orphaned index {index_0+1} out of bounds for 'ipco'.")

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
                
                for item_id, entry in ipma.entries.items():
                    new_associations = []
                    for assoc in entry.associations:
                        old_prop_index = assoc.property_index
                        if old_prop_index in remap_table:
                            assoc.property_index = remap_table[old_prop_index]
                            new_associations.append(assoc)
                        # else:
                        #   The property was removed entirely (should not occur).
                    
                    # print(f"    - Item {item_id} associations: {entry.associations} -> {new_associations}")
                    entry.associations = new_associations
                print("  - 'ipma' re-indexing complete.")
            else:
                 print("  - No 'ipma' re-indexing needed.")
    def set_content_identifier(self, new_content_id: str) -> bool:
        """Locate the primary `infe` entry and update its item name with a UUID."""
        primary_id = self.get_primary_item_id()
        if not primary_id:
            print("Error: Cannot find primary item ID.")
            return False
            
        if not self._iinf_box:
            print("Error: Cannot find 'iinf' box shortcut (_iinf_box).")
            return False
            
        print(f"Searching for 'infe' box with primary_id = {primary_id}")
        
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

        # Update both the parsed box and the cached entry representation.
        for box in self._iinf_box.children:
            if isinstance(box, ItemInfoEntryBox):
                if box.item_id == target_id:
                    print(f"Success: Found 'infe' box for target ID {target_id}. Setting item_name...")
                    box.item_name = new_content_id
                    
                    for entry in self._iinf_box.entries:
                        if entry.item_id == target_id:
                            entry.name = new_content_id
                            break
                    return True
                    
        print(f"Error: Logic failed to find 'infe' box for target ID {target_id} even after check.")
        return False

    def reconstruct_primary_image(self) -> Image.Image | None:
        """Reconstruct the primary image using pillow-heif (handles grid tiles)."""
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
        
        if 'dimg' in self._iref_box.references and primary_id in self._iref_box.references['dimg']:
            return self._iref_box.references['dimg'].get(primary_id)
        
        # Fall back to Samsung-style shifted IDs.
        shifted_id = primary_id << 16
        if 'dimg' in self._iref_box.references and shifted_id in self._iref_box.references['dimg']:
             print("Info: Using shifted primary ID to find grid layout.")
             return self._iref_box.references['dimg'].get(shifted_id)
             
        return None

    def get_image_size(self, item_id: int) -> tuple[int, int] | None:
        if not (self._iprp_box and self._iprp_box.ipma and self._iprp_box.ipco): return None
        
        target_id = item_id
        if item_id not in self._iprp_box.ipma.entries:
            shifted_id = item_id << 16
            if shifted_id in self._iprp_box.ipma.entries:
                target_id = shifted_id
            else:
                 unshifted_id = item_id & 0x0000FFFF
                 if unshifted_id in self._iprp_box.ipma.entries:
                     target_id = unshifted_id
                 else:
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
        self.handler = resolve_handler(self)

    def get_item_data(self, item_id: int) -> bytes | None:
        if not self._iloc_box:
            print("Error: 'iloc' box not found.")
            return None
            
        target_id = item_id
        location = next((loc for loc in self._iloc_box.locations if loc.item_id == target_id), None)
        
        if not location:
            shifted_id = item_id << 16
            location = next((loc for loc in self._iloc_box.locations if loc.item_id == shifted_id), None)
            if location:
                print(f"Info: Located item {item_id} using shifted ID {shifted_id} in 'iloc'.")
                target_id = shifted_id
        
        if not location and (item_id & 0xFFFF0000):
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
        if not self.handler:
            self._detect_vendor()
        data = self.handler.extract_motion_video(self)
        if data is not None:
            print("Found motion photo data via vendor handler.")
        return data

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
