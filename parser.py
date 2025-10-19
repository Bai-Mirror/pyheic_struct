import struct

class Box:
    """
    Represents a generic ISOBMFF box.
    """
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.size = size
        self.type = box_type
        self.offset = offset
        self.raw_data = raw_data
        self.children = [] # Will be populated for container boxes

    def __repr__(self) -> str:
        # e.g., <Box 'ftyp' size=36 offset=8>
        return f"<Box '{self.type}' size={self.size} offset={self.offset}>"

# In parser.py

from typing import List, BinaryIO

def parse_boxes(stream: BinaryIO) -> List[Box]:
    """
    Parses all top-level boxes from a file stream, handling special size cases.
    """
    boxes = []
    
    stream.seek(0, 2)
    file_size = stream.tell()
    stream.seek(0)

    while stream.tell() < file_size:
        current_offset = stream.tell()
        
        # Read the standard 8-byte header
        header = stream.read(8)
        if len(header) < 8:
            break

        size = struct.unpack('>I', header[:4])[0]
        box_type = header[4:].decode('ascii')
        
        header_size = 8
        content_size = 0

        # --- NEW: Handle special size cases ---
        if size == 1:
            # The actual size is a 64-bit integer following the type
            largesize_header = stream.read(8)
            if len(largesize_header) < 8:
                break
            size = struct.unpack('>Q', largesize_header)[0]
            header_size = 16
            content_size = size - header_size
        elif size == 0:
            # The box extends to the end of the file
            content_size = file_size - current_offset - header_size
            size = content_size + header_size
        else:
            # Standard size
            content_size = size - header_size
        # --- End of new code ---

        # Read the box's content (raw_data)
        # We need to rewind a bit if we read largesize header to get all content
        stream.seek(current_offset + header_size)
        raw_data = stream.read(content_size)
        if len(raw_data) < content_size:
            # Avoids errors on truncated files
            break

        box = Box(size, box_type, current_offset, raw_data)
        boxes.append(box)
        
        # Seek to the beginning of the next box
        stream.seek(current_offset + size)

    return boxes