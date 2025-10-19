from typing import List

class Box:
    """
    Represents a generic ISOBMFF box. This is a simple data container.
    """
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.size = size
        self.type = box_type
        self.offset = offset
        self.raw_data = raw_data
        self.children: List['Box'] = [] # Initially empty

    def __repr__(self) -> str:
        return f"<Box '{self.type}' size={self.size} offset={self.offset}>"