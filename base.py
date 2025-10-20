# pyheic_struct/base.py

from typing import List
import struct
from io import BytesIO

class Box:
    """
    Represents a generic ISOBMFF box.
    Now supports finding children and building (writing) data back.
    """
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.size = size
        self.type = box_type
        self.offset = offset
        self.raw_data = raw_data
        self.children: List['Box'] = []
        self.is_full_box = False # 默认不是 FullBox

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
        """
        序列化此盒的 *内容* (不包括头部)。
        对于一个通用的容器盒 (container boxes)，它会递归构建所有子盒。
        """
        if not self.children:
            # 对于一个没有子盒的简单数据盒 (如 ftyp, mdat, 或未解析的盒)
            # 只需返回它持有的原始数据。
            return self.raw_data
        
        # 对于一个容器盒 (如 'meta', 'iprp', 'ipco')
        # 递归构建每一个子盒 (完整的，包括头部) 并拼接它们
        content_stream = BytesIO()
        for child in self.children:
            child_data = child.build_box()
            content_stream.write(child_data)
        return content_stream.getvalue()

    def build_box(self) -> bytes:
        """
        构建完整的盒 (头部 + 内容)，并返回其二进制数据。
        """
        # 1. "自底向上" 构建内容
        content_data = self.build_content()
        
        # 2. 构建头部
        header_data = self.build_header(len(content_data))
        
        # 3. 更新 self.size 属性 (8字节标准头 + 内容)
        self.size = len(header_data) + len(content_data)
        
        return header_data + content_data

    def find_box(self, box_type: str, recursive: bool = True) -> 'Box' | None:
        """在子盒中查找指定类型的第一个盒子"""
        for child in self.children:
            if child.type == box_type:
                return child
            if recursive and child.children:
                found = child.find_box(box_type, recursive=True)
                if found:
                    return found
        return None

class FullBox(Box):
    """
    FullBox 是一种特殊的 Box，它在内容开头包含 4 字节的 version 和 flags
    """
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        super().__init__(size, box_type, offset, raw_data)
        self.is_full_box = True
        self.version: int = 0
        self.flags: int = 0
        self._parse_full_box_header()

    def _parse_full_box_header(self):
        """从 raw_data 中解析 version 和 flags"""
        if len(self.raw_data) >= 4:
            version_flags = struct.unpack('>I', self.raw_data[:4])[0]
            self.version = (version_flags >> 24) & 0xFF
            self.flags = version_flags & 0xFFFFFF
        
    def build_full_box_header(self) -> bytes:
        """构建 4 字节的 version/flags 头部"""
        version_flags = (self.version << 24) | self.flags
        return struct.pack('>I', version_flags)
    
    def build_content(self) -> bytes:
        """
        序列化此 FullBox 的内容。
        它首先写入 4 字节的 version/flags，然后
        再写入子盒 (如果是容器) 或 version/flags 之后的
        原始数据 (如果不是容器)。
        """
        content_stream = BytesIO()
        
        # 1. 写入 FullBox 特有的 4 字节头部
        content_stream.write(self.build_full_box_header())
        
        # 2. 写入剩余的内容
        if not self.children:
            # 对于一个没有子盒的简单 FullBox (如 'hdlr')
            # 写入 self.raw_data 中 *跳过* 4 字节 v/f 之后的部分
            if len(self.raw_data) >= 4:
                content_stream.write(self.raw_data[4:])
        else:
            # 对于一个容器 FullBox (如 'meta')
            # 递归构建每一个子盒 (与 Box.build_content 相同)
            for child in self.children:
                child_data = child.build_box()
                content_stream.write(child_data)
                
        return content_stream.getvalue()