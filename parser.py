import struct
from typing import List, BinaryIO
from io import BytesIO

from base import Box  # Import the base Box class
from heic_types import ItemLocationBox

# The factory map remains here
BOX_TYPE_MAP = {
    'iloc': ItemLocationBox,
}

CONTAINER_BOXES = {'meta', 'moov', 'trak', 'iprp', 'ipco', 'dinf', 'fiinf', 'ipro'}
FULL_BOXES = {'meta', 'hdlr', 'pitm', 'iinf', 'iloc'}

def parse_boxes(stream: BinaryIO, max_size: int) -> List[Box]:
    """
    Parses boxes from a file stream up to a maximum size.
    Now also handles recursive parsing.
    """
    boxes = []
    start_pos_in_stream = stream.tell()
    
    while stream.tell() - start_pos_in_stream < max_size:
        current_offset_in_stream = stream.tell()
        
        header = stream.read(8)
        if len(header) < 8: break

        size = struct.unpack('>I', header[:4])[0]
        box_type = header[4:].decode('ascii', errors='ignore')
        
        header_size = 8
        if size == 1:
            largesize_header = stream.read(8)
            if len(largesize_header) < 8: break
            size = struct.unpack('>Q', largesize_header)[0]
            header_size = 16
        elif size == 0:
            size = max_size - (current_offset_in_stream - start_pos_in_stream)

        if size < header_size: break
            
        content_size = size - header_size
        
        stream.seek(current_offset_in_stream + header_size)
        raw_data = stream.read(content_size)
        if len(raw_data) < content_size: break

        # --- Factory Pattern ---
        box_class = BOX_TYPE_MAP.get(box_type, Box)
        box = box_class(size, box_type, current_offset_in_stream, raw_data)

        # --- NEW: Recursive parsing logic moved here ---
        if box.type in CONTAINER_BOXES:
            child_stream = BytesIO(box.raw_data)
            parse_size = len(box.raw_data)
            if box.type in FULL_BOXES:
                child_stream.read(4) # Skip version/flags
                parse_size -= 4
            box.children = parse_boxes(child_stream, parse_size)
        # --- End of new logic ---

        boxes.append(box)
        stream.seek(current_offset_in_stream + size)

    return boxes