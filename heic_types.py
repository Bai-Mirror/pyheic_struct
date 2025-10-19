import struct
from base import Box  # <-- THIS IS THE KEY CHANGE

class ItemLocation:
    # ... (rest of this class is unchanged)
    def __init__(self, item_id, offset, length):
        self.item_id = item_id
        self.offset = offset
        self.length = length
    def __repr__(self):
        return f"<ItemLocation ID={self.item_id} offset={self.offset} length={self.length}>"

class ItemLocationBox(Box):
    # ... (rest of this class is unchanged)
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.locations = []
        self._parse_locations()
    def _parse_locations(self):
        # ... (all the parsing logic here is unchanged)
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
            current_pos += 2 # Skip construction_method
            current_pos += 2 # Skip data_reference_index
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
    """A data class for one item described in an 'iinf' box."""
    def __init__(self, item_id, item_type, item_name):
        self.item_id = item_id
        self.type = item_type
        self.name = item_name

    def __repr__(self):
        return f"<ItemInfoEntry ID={self.item_id} type='{self.type}' name='{self.name}'>"

class ItemInfoBox(Box):
    """
    A specialized class for the 'iinf' box.
    Parses its own data to build a list of all available items.
    """
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        
        self.entries: list[ItemInfoEntry] = []
        self._parse_entries()

    def _parse_entries(self):
        # 'iinf' is a FullBox, so the first 4 bytes are version/flags
        item_count = struct.unpack('>H', self.raw_data[4:6])[0]
        
        # The children are 'infe' boxes, which are parsed by the generic parser
        for infe_box in self.children:
            if infe_box.type == 'infe':
                # 'infe' is a FullBox (version, flags)
                # version = infe_box.raw_data[0]
                item_id = struct.unpack('>H', infe_box.raw_data[4:6])[0]
                item_type = infe_box.raw_data[8:12].decode('ascii').strip('\x00')
                item_name_bytes = infe_box.raw_data[12:]
                item_name = item_name_bytes.decode('utf-8', errors='ignore').strip('\x00')
                self.entries.append(ItemInfoEntry(item_id, item_type, item_name))

class PrimaryItemBox(Box):
    """
    A specialized class for the 'pitm' box.
    """
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        
        self.item_id: int = 0
        self._parse_item_id()

    def _parse_item_id(self):
        # 'pitm' is a FullBox (version, flags)
        self.item_id = struct.unpack('>H', self.raw_data[4:6])[0]