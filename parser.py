import struct
from typing import List, BinaryIO
from io import BytesIO

from base import Box
from heic_types import (
    ItemLocationBox, PrimaryItemBox, ItemInfoBox, ItemPropertiesBox,
    ItemPropertyContainerBox, ItemPropertyAssociationBox, ImageSpatialExtentsBox,
    ItemReferenceBox # <-- Import the new class
)

BOX_TYPE_MAP = {
    'iloc': ItemLocationBox,
    'pitm': PrimaryItemBox,
    'iinf': ItemInfoBox,
    'iprp': ItemPropertiesBox,
    'ipco': ItemPropertyContainerBox,
    'ipma': ItemPropertyAssociationBox,
    'ispe': ImageSpatialExtentsBox,
    'iref': ItemReferenceBox, # <-- Register the new class
}

# 'iref' is also a container.
CONTAINER_BOXES = {'meta', 'moov', 'trak', 'iprp', 'ipco', 'dinf', 'fiinf', 'ipro', 'iinf', 'iref'}
FULL_BOXES = {'meta', 'hdlr', 'pitm', 'iinf', 'iloc', 'ipma', 'ispe', 'iref'}

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

        box_class = BOX_TYPE_MAP.get(box_type, Box)
        box = box_class(size, box_type, current_offset_in_stream, raw_data)

        if box.type in CONTAINER_BOXES:
            child_stream = BytesIO(box.raw_data)
            parse_size = len(box.raw_data)
            if box.type in FULL_BOXES:
                # Skip version/flags from the beginning of the raw_data
                child_stream.read(4)
                parse_size -= 4
            box.children = parse_boxes(child_stream, parse_size)

        boxes.append(box)
        stream.seek(current_offset_in_stream + size)

    return boxes