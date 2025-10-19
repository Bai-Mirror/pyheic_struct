# pyheic_struct/heic_types.py

import struct
from base import Box

# --- Existing classes (unchanged) ---

class ItemLocation:
    def __init__(self, item_id, offset, length):
        self.item_id = item_id
        self.offset = offset
        self.length = length
    def __repr__(self):
        return f"<ItemLocation ID={self.item_id} offset={self.offset} length={self.length}>"

class ItemLocationBox(Box):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.locations = []
        self._parse_locations()
    def _parse_locations(self):
        stream = self.raw_data
        version_flags = struct.unpack('>I', stream[:4])[0]
        sizes = struct.unpack('>H', stream[4:6])[0]
        offset_size = (sizes >> 12) & 0x0F
        length_size = (sizes >> 8) & 0x0F
        base_offset_size = (sizes >> 4) & 0x0F
        item_count = struct.unpack('>H', stream[6:8])[0]
        current_pos = 8
        for _ in range(item_count):
            item_id = struct.unpack('>H', stream[current_pos : current_pos+2])[0]
            current_pos += 2
            current_pos += 2
            current_pos += base_offset_size
            extent_count = struct.unpack('>H', stream[current_pos : current_pos+2])[0]
            current_pos += 2
            if extent_count > 0:
                offset = self._read_int(stream, current_pos, offset_size)
                current_pos += offset_size
                length = self._read_int(stream, current_pos, length_size)
                current_pos += length_size
                self.locations.append(ItemLocation(item_id, offset, length))
    def _read_int(self, data, pos, size):
        if size == 1: return data[pos]
        if size == 2: return struct.unpack('>H', data[pos:pos+2])[0]
        if size == 4: return struct.unpack('>I', data[pos:pos+4])[0]
        if size == 8: return struct.unpack('>Q', data[pos:pos+8])[0]
        return 0

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
        item_count = struct.unpack('>H', self.raw_data[4:6])[0]
        for infe_box in self.children:
            if infe_box.type == 'infe':
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
        self.item_id = struct.unpack('>H', self.raw_data[4:6])[0]

# --- NEW classes for Task 3.1 & 3.2 ---

class ImageSpatialExtentsBox(Box):
    """'ispe' box, contains image dimensions."""
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        # 'ispe' is a FullBox
        self.image_width = struct.unpack('>I', self.raw_data[4:8])[0]
        self.image_height = struct.unpack('>I', self.raw_data[8:12])[0]
    def __repr__(self):
        return f"<ImageSpatialExtentsBox width={self.image_width} height={self.image_height}>"

class ItemPropertyAssociationEntry:
    """Helper class for an entry in the 'ipma' box."""
    def __init__(self, item_id, association_count):
        self.item_id = item_id
        self.association_count = association_count
        self.associations = [] # List of property indices
    def __repr__(self):
        return f"<ItemPropertyAssociationEntry item_id={self.item_id} associations={self.associations}>"

class ItemPropertyAssociationBox(Box):
    """'ipma' box, maps items to their properties."""
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.entries: dict[int, ItemPropertyAssociationEntry] = {}
        self._parse_associations()

    def _parse_associations(self):
        stream = self.raw_data
        
        # A FullBox has a 4-byte header (version + flags)
        version_flags = struct.unpack('>I', stream[:4])[0]
        version = version_flags >> 24
        flags = version_flags & 0xFFFFFF
        
        entry_count = struct.unpack('>I', stream[4:8])[0]
        pos = 8

        # Determine field sizes based on the box version and flags
        item_id_size = 4 if version >= 1 else 2
        is_large_property_index = (flags & 1) == 1
        
        for _ in range(entry_count):
            # Boundary check for the item ID
            if pos + item_id_size > len(stream):
                break

            if item_id_size == 4:
                item_id = struct.unpack('>I', stream[pos:pos+4])[0]
                pos += 4
            else: # item_id_size == 2
                item_id = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
            
            # Boundary check for association_count
            if pos + 1 > len(stream):
                break
            
            association_count = stream[pos]
            pos += 1
            
            entry = ItemPropertyAssociationEntry(item_id, association_count)
            
            for __ in range(association_count):
                if is_large_property_index:
                    # 2-byte association entry
                    if pos + 2 > len(stream):
                        break # Not enough data
                    assoc_value = struct.unpack('>H', stream[pos:pos+2])[0]
                    property_index = assoc_value & 0x7FFF # Lower 15 bits
                    pos += 2
                else:
                    # 1-byte association entry
                    if pos + 1 > len(stream):
                        break # Not enough data
                    assoc_value = stream[pos]
                    property_index = assoc_value & 0x7F # Lower 7 bits
                    pos += 1

                # A property_index of 0 is not a valid index.
                if property_index > 0:
                    entry.associations.append(property_index)
            
            self.entries[item_id] = entry

class ItemPropertyContainerBox(Box):
    """'ipco' box. Just a container for property boxes like 'ispe'."""
    pass

class ItemPropertiesBox(Box):
    """'iprp' box. Container for 'ipco' and 'ipma'."""

    @property
    def ipco(self) -> ItemPropertyContainerBox | None:
        """Finds and returns the 'ipco' child box if it exists."""
        for child in self.children:
            if isinstance(child, ItemPropertyContainerBox):
                return child
        return None

    @property
    def ipma(self) -> ItemPropertyAssociationBox | None:
        """Finds and returns the 'ipma' child box if it exists."""
        for child in self.children:
            if isinstance(child, ItemPropertyAssociationBox):
                return child
        return None