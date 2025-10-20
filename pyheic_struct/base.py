# pyheic_struct/base.py

from typing import List, Optional
import struct
from io import BytesIO

class Box:
    """Generic ISOBMFF box supporting hierarchical parsing and rebuilds."""

    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.size = size
        self.type = box_type
        self.offset = offset
        self.raw_data = raw_data
        self.children: List['Box'] = []
        self.is_full_box = False  # Flag toggled by FullBox subclasses

    def __repr__(self) -> str:
        return f"<Box '{self.type}' size={self.size} offset={self.offset}>"
        
    def _post_parse_initialization(self):
        """Called by the parser after children have been assigned."""
        pass

    def build_header(self, content_size: int) -> bytes:
        """Builds the 8-byte (or 16-byte) box header."""
        header = BytesIO()
        
        # FullBox (version/flags) 数据属于 'content', 而不是 'header'
        full_box_header_size = 0
        if self.is_full_box:
            full_box_header_size = 4
            
        final_size = 8 + content_size
        
        if final_size > 4294967295:
            # 64-bit 'largesize'
            header.write(struct.pack('>I', 1))
            header.write(self.type.encode('ascii'))
            header.write(struct.pack('>Q', final_size + 8)) # 16-byte header
        else:
            # 32-bit standard size
            header.write(struct.pack('>I', final_size))
            header.write(self.type.encode('ascii'))
            
        return header.getvalue()

    def build_content(self) -> bytes:
        """Serialise the box payload (children included, header excluded)."""
        if not self.children:
            # Leaf boxes expose their stored payload verbatim.
            return self.raw_data
        
        # Container boxes rebuild each child (including headers) in order.
        content_stream = BytesIO()
        for child in self.children:
            child_data = child.build_box()
            content_stream.write(child_data)
        return content_stream.getvalue()


    def build_box(self) -> bytes:
        """Construct the full box (header + payload) and return its bytes."""
        content_data = self.build_content()
        
        header_data = self.build_header(len(content_data))
        
        self.size = len(header_data) + len(content_data)
        
        return header_data + content_data

    def find_box(self, box_type: str, recursive: bool = True) -> Optional['Box']:
        """Return the first child matching `box_type`."""
        for child in self.children:
            if child.type == box_type:
                return child
            if recursive and child.children:
                found = child.find_box(box_type, recursive=True)
                if found:
                    return found
        return None

class FullBox(Box):
    """Box variant that begins with a 4-byte version/flags header."""

    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.is_full_box = True
        self.version: int = 0
        self.flags: int = 0
        self._parse_full_box_header()

    def _parse_full_box_header(self):
        """Extract version and flags from the stored payload."""
        if len(self.raw_data) >= 4:
            version_flags = struct.unpack('>I', self.raw_data[:4])[0]
            self.version = (version_flags >> 24) & 0xFF
            self.flags = version_flags & 0xFFFFFF
        
    def build_full_box_header(self) -> bytes:
        """Serialise the 4-byte version/flags prefix."""
        version_flags = (self.version << 24) | self.flags
        return struct.pack('>I', version_flags)
    
    def build_content(self) -> bytes:
        """Serialise the FullBox payload, ensuring the header is emitted."""
        content_stream = BytesIO()
        
        content_stream.write(self.build_full_box_header())
        
        if not self.children:
            # Emit the payload following the version/flags header.
            if len(self.raw_data) >= 4:
                content_stream.write(self.raw_data[4:])
        else:
            # Container-style FullBoxes rebuild each descendant.
            for child in self.children:
                child_data = child.build_box()
                content_stream.write(child_data)
                
        return content_stream.getvalue()
