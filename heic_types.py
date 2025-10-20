# pyheic_struct/heic_types.py

import struct
from base import Box

# --- A new helper class to handle multiple data locations ('extents') ---
class ItemLocation:
    def __init__(self, item_id):
        self.item_id = item_id
        self.extents = [] # Will be a list of (offset, length) tuples

    def __repr__(self):
        total_length = sum(ext[1] for ext in self.extents)
        return f"<ItemLocation ID={self.item_id} extents={len(self.extents)} total_size={total_length}>"

# --- REWRITTEN ItemLocationBox to correctly parse all item locations ---
class ItemLocationBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.locations = []
        self._parse_locations()
        
    def _parse_locations(self):
        stream = self.raw_data
        
        version_flags = struct.unpack('>I', stream[:4])[0]
        version = version_flags >> 24
        
        sizes = struct.unpack('>H', stream[4:6])[0]
        offset_size = (sizes >> 12) & 0x0F
        length_size = (sizes >> 8) & 0x0F
        base_offset_size = (sizes >> 4) & 0x0F
        
        index_size = 0
        if version == 1 or version == 2:
            index_size = sizes & 0x0F
        
        item_count = 0
        if version < 2:
            item_count = struct.unpack('>H', stream[6:8])[0]
            current_pos = 8
        else: # version == 2
            item_count = struct.unpack('>I', stream[6:10])[0]
            current_pos = 10

        for _ in range(item_count):
            item_id = 0
            # Item ID size depends on the box version
            if version < 2:
                if current_pos + 2 > len(stream): break
                item_id = struct.unpack('>H', stream[current_pos : current_pos+2])[0]
                current_pos += 2
            else: # version == 2
                if current_pos + 4 > len(stream): break
                item_id = struct.unpack('>I', stream[current_pos : current_pos+4])[0]
                current_pos += 4

            if (version == 1 or version == 2) and current_pos + 2 <= len(stream):
                current_pos += 2 # Skip construction method

            if current_pos + 2 > len(stream): break
            current_pos += 2 # Skip data_reference_index
            
            base_offset = 0
            if base_offset_size > 0:
                if current_pos + base_offset_size > len(stream): break
                base_offset = self._read_int(stream, current_pos, base_offset_size)
                current_pos += base_offset_size

            if current_pos + 2 > len(stream): break
            extent_count = struct.unpack('>H', stream[current_pos : current_pos+2])[0]
            current_pos += 2
            
            loc = ItemLocation(item_id)
            for __ in range(extent_count):
                if (version == 1 or version == 2) and index_size > 0:
                     if current_pos + index_size > len(stream): break
                     current_pos += index_size # Skip extent_index

                extent_offset = self._read_int(stream, current_pos, offset_size)
                current_pos += offset_size

                extent_length = self._read_int(stream, current_pos, length_size)
                current_pos += length_size
                
                loc.extents.append((base_offset + extent_offset, extent_length))
            self.locations.append(loc)

    def _read_int(self, data, pos, size):
        if pos + size > len(data): return 0
        if size == 0: return 0
        if size == 1: return data[pos]
        if size == 2: return struct.unpack('>H', data[pos:pos+2])[0]
        if size == 4: return struct.unpack('>I', data[pos:pos+4])[0]
        if size == 8: return struct.unpack('>Q', data[pos:pos+8])[0]
        return 0

# --- All other classes below remain unchanged ---

class ItemInfoEntry:
    def __init__(self, item_id, item_type, item_name):
        self.item_id = item_id
        self.type = item_type
        self.name = item_name
    def __repr__(self):
        return f"<ItemInfoEntry ID={self.item_id} type='{self.type}' name='{self.name}'>"

class ItemInfoBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.entries: list[ItemInfoEntry] = []
        self._parse_entries()
    def _parse_entries(self):
        if len(self.raw_data) < 6: return
        item_count = struct.unpack('>H', self.raw_data[4:6])[0]
        for infe_box in self.children:
            if infe_box.type == 'infe':
                if len(infe_box.raw_data) < 12: continue
                item_id = struct.unpack('>H', infe_box.raw_data[4:6])[0]
                item_type = infe_box.raw_data[8:12].decode('ascii').strip('\x00')
                item_name_bytes = infe_box.raw_data[12:]
                item_name = item_name_bytes.decode('utf-8', errors='ignore').strip('\x00')
                self.entries.append(ItemInfoEntry(item_id, item_type, item_name))

class PrimaryItemBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.item_id: int = 0
        self._parse_item_id()
    def _parse_item_id(self):
        if len(self.raw_data) < 6: return
        self.item_id = struct.unpack('>H', self.raw_data[4:6])[0]

class ImageSpatialExtentsBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.image_width = struct.unpack('>I', self.raw_data[4:8])[0]
        self.image_height = struct.unpack('>I', self.raw_data[8:12])[0]
    def __repr__(self):
        return f"<ImageSpatialExtentsBox width={self.image_width} height={self.image_height}>"

class ItemPropertyAssociationEntry:
    def __init__(self, item_id, association_count):
        self.item_id = item_id
        self.association_count = association_count
        self.associations = []
    def __repr__(self):
        return f"<ItemPropertyAssociationEntry item_id={self.item_id} associations={self.associations}>"

class ItemPropertyAssociationBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.entries: dict[int, ItemPropertyAssociationEntry] = {}
        self._parse_associations()

    def _parse_associations(self):
        stream = self.raw_data
        version_flags = struct.unpack('>I', stream[:4])[0]
        version = version_flags >> 24
        flags = version_flags & 0xFFFFFF
        entry_count = struct.unpack('>I', stream[4:8])[0]
        pos = 8
        item_id_size = 4 if version >= 1 else 2
        is_large_property_index = (flags & 1) == 1
        
        for _ in range(entry_count):
            if pos + item_id_size > len(stream): break
            item_id = struct.unpack('>I' if item_id_size == 4 else '>H', stream[pos:pos+item_id_size])[0]
            pos += item_id_size
            if pos + 1 > len(stream): break
            association_count = stream[pos]
            pos += 1
            entry = ItemPropertyAssociationEntry(item_id, association_count)
            for __ in range(association_count):
                prop_size = 2 if is_large_property_index else 1
                if pos + prop_size > len(stream): break
                assoc_value = struct.unpack('>H' if prop_size == 2 else '>B', stream[pos:pos+prop_size])[0]
                property_index = assoc_value & (0x7FFF if prop_size == 2 else 0x7F)
                pos += prop_size
                if property_index > 0:
                    entry.associations.append(property_index)
            self.entries[item_id] = entry

class ItemPropertyContainerBox(Box):
    pass

class ItemPropertiesBox(Box):
    @property
    def ipco(self) -> ItemPropertyContainerBox | None:
        for child in self.children:
            if isinstance(child, ItemPropertyContainerBox): return child
        return None
    @property
    def ipma(self) -> ItemPropertyAssociationBox | None:
        for child in self.children:
            if isinstance(child, ItemPropertyAssociationBox): return child
        return None

class ItemReferenceEntry:
    def __init__(self, from_id, to_ids):
        self.from_item_id = from_id
        self.to_item_ids = to_ids
    def __repr__(self):
        return f"<ItemReferenceEntry from={self.from_item_id} to={self.to_item_ids}>"

class ItemReferenceBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.references: dict[int, list[int]] = {}
        self._parse_references()
    def _parse_references(self):
        stream = self.raw_data
        version_flags = struct.unpack('>I', stream[:4])[0]
        version = version_flags >> 24
        pos = 4
        item_id_size = 4 if version == 1 else 2
        while pos < len(stream):
            if pos + 8 > len(stream): break
            ref_box_size = struct.unpack('>I', stream[pos:pos+4])[0]
            if pos + ref_box_size > len(stream): break
            if item_id_size == 4:
                from_item_id = struct.unpack('>I', stream[pos+8:pos+12])[0]
                ref_count_pos = pos + 12
            else:
                from_item_id = struct.unpack('>H', stream[pos+8:pos+10])[0]
                ref_count_pos = pos + 10
            reference_count = struct.unpack('>H', stream[ref_count_pos:ref_count_pos+2])[0]
            to_ids_pos = ref_count_pos + 2
            to_item_ids = []
            for _ in range(reference_count):
                if to_ids_pos + item_id_size > len(stream): break
                if item_id_size == 4:
                    to_id = struct.unpack('>I', stream[to_ids_pos:to_ids_pos+4])[0]
                else:
                    to_id = struct.unpack('>H', stream[to_ids_pos:to_ids_pos+2])[0]
                to_item_ids.append(to_id)
                to_ids_pos += item_id_size
            self.references[from_item_id] = to_item_ids
            pos += ref_box_size