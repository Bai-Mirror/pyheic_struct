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